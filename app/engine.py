"""Conversion engine: run NAM A2->A1 batch jobs with progress callbacks.

Wraps the single-venv distillation pipeline as an importable, callback-driven
job runner. Everything runs in the 0.13.0 venv (the only one that can load the
A2 SlimmableContainer format). Both output formats train + export there; the
0.5.x path transcodes the native 0.7.0 export down for the GP-50, in-process,
with no torch and no retraining (see a2a1/nam_transcode.py):

    output_format='0.5x':
        A2.nam --(render, .venv/0.13.0)--> y.wav
               --(train+export 0.7.0, .venv/0.13.0, a2a1/train_a1_070.py)
               --(transcode 0.7.0 -> 0.5.x, in-process)--> A1.nam (0.5.x, GP-50)

    output_format='0.7.0':
        A2.nam --(render, .venv/0.13.0)--> y.wav
               --(train+export, .venv/0.13.0, a2a1/train_a1_070.py)--> A1.nam (0.7.0)

Already-A1 0.5.x files are detected and copied through untouched (regardless
of requested output_format — no re-distillation of already-compatible files).
This module does no device I/O of any kind — it only shells out to the local
0.13.0 venv and touches the filesystem.

The 0.12.2 venv (`venv_a1`) is retired; the field is kept only for backward
compatibility and is unused.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from a2a1 import distill_protocol

PROJECT_ROOT = Path(__file__).resolve().parent.parent
A2A1_DIR = PROJECT_ROOT / "a2a1"
DEFAULT_VENV_A2 = PROJECT_ROOT / ".venv" / "bin" / "python"
DEFAULT_VENV_A1 = PROJECT_ROOT / ".venv-a1" / "bin" / "python"
DEFAULT_DI = PROJECT_ROOT / "refs" / "v3_0_0.wav"
DEFAULT_OUT_DIR = PROJECT_ROOT / "out"


@dataclass
class FileState:
    """Per-file conversion state, updated in place and handed to progress_cb."""

    input_path: str
    name: str
    status: str = "queued"  # queued|detecting|rendering|training|done|failed|cancelled
    progress: float = 0.0  # 0.0-1.0; advances per training epoch
    esr: Optional[float] = None
    output_path: Optional[str] = None
    format_ok: Optional[bool] = None
    error: Optional[str] = None
    src_arch: Optional[str] = None
    detail: Optional[str] = None  # human hint, e.g. "Epoch 42/100"
    eta_seconds: Optional[float] = None  # estimated time remaining for this file


ProgressCallback = Callable[[FileState], None]


@dataclass
class ConvertJob:
    """A batch conversion request plus the live per-file state list."""

    input_paths: List[Path]
    di_path: Path = DEFAULT_DI
    epochs: int = 60
    output_format: str = "0.5x"  # '0.5x' | '0.7.0'
    out_dir: Path = DEFAULT_OUT_DIR
    venv_a2: Path = DEFAULT_VENV_A2
    venv_a1: Path = DEFAULT_VENV_A1
    files: List[FileState] = field(default_factory=list)
    # Cancellation: request_cancel() sets the event and kills any in-flight
    # subprocess. The run loop checks `cancelled` at every stage boundary.
    _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _proc_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _current_proc: Optional[subprocess.Popen] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.input_paths = [Path(p) for p in self.input_paths]
        self.di_path = Path(self.di_path)
        self.out_dir = Path(self.out_dir)
        self.venv_a2 = Path(self.venv_a2)
        self.venv_a1 = Path(self.venv_a1)
        if not self.files:
            self.files = [
                FileState(input_path=str(p), name=p.stem) for p in self.input_paths
            ]

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def request_cancel(self) -> None:
        """Flag the job cancelled and SIGTERM the running stage's process group.

        Safe to call from another thread (the API request thread). A stage that
        hasn't started yet sees the flag and is skipped; a running render/train
        subprocess is terminated so we don't wait out a 20-minute train.
        """
        self._cancel_event.set()
        with self._proc_lock:
            proc = self._current_proc
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass


def detect_architecture(nam_path: Path) -> Tuple[Optional[str], str]:
    """Read a .nam file's JSON header. Returns (architecture, version)."""
    with open(nam_path) as fp:
        d = json.load(fp)
    return d.get("architecture"), str(d.get("version", "?"))


def _run(cmd: List[str], job: ConvertJob) -> subprocess.CompletedProcess:
    """Run a stage subprocess, registering it on the job so request_cancel() can
    kill it. `start_new_session=True` gives it its own process group so a SIGTERM
    reaches any children. If the job is already cancelled, returns rc=-1 without
    launching."""
    with job._proc_lock:
        if job._cancel_event.is_set():
            return subprocess.CompletedProcess(cmd, -1, "", "cancelled")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        job._current_proc = proc
    try:
        out, err = proc.communicate()
    finally:
        with job._proc_lock:
            job._current_proc = None
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def _run_streaming(
    cmd: List[str], job: ConvertJob, on_line
) -> subprocess.CompletedProcess:
    """Like `_run`, but calls `on_line(line)` for each stdout line as it arrives
    (stderr merged in) so callers can react to live progress tokens. Returns a
    CompletedProcess with the full captured output in `.stdout`."""
    with job._proc_lock:
        if job._cancel_event.is_set():
            return subprocess.CompletedProcess(cmd, -1, "", "cancelled")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered so progress lines arrive promptly
            start_new_session=True,
        )
        job._current_proc = proc
    lines: List[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            try:
                on_line(line)
            except Exception:
                pass  # a progress-callback hiccup must never kill the conversion
        proc.wait()
    finally:
        with job._proc_lock:
            job._current_proc = None
    return subprocess.CompletedProcess(cmd, proc.returncode, "".join(lines), "")


def _update(state: FileState, progress_cb: ProgressCallback, **changes) -> None:
    for k, v in changes.items():
        setattr(state, k, v)
    progress_cb(state)


def _convert_one(
    state: FileState, job: ConvertJob, progress_cb: ProgressCallback
) -> None:
    src = Path(state.input_path)

    _update(state, progress_cb, status="detecting", progress=0.05)
    try:
        arch, version = detect_architecture(src)
    except Exception as e:
        _update(state, progress_cb, status="failed", error=f"could not read .nam: {e}")
        return
    state.src_arch = arch

    # Already-A1 0.5.x: pass through untouched.
    if arch == "WaveNet" and version.startswith("0.5"):
        job.out_dir.mkdir(parents=True, exist_ok=True)
        dest = job.out_dir / f"{state.name}.nam"
        try:
            shutil.copyfile(src, dest)
        except Exception as e:
            _update(state, progress_cb, status="failed", error=f"copy failed: {e}")
            return
        _update(
            state,
            progress_cb,
            status="done",
            progress=1.0,
            output_path=str(dest),
            format_ok=True,
        )
        return

    if arch != "SlimmableContainer":
        _update(
            state,
            progress_cb,
            status="failed",
            error=f"unsupported source architecture {arch!r} (version {version})",
        )
        return

    # A2 -> A1 distillation: render (0.13.0 venv), then train/export in the
    # venv that matches the requested output format.
    with tempfile.TemporaryDirectory(prefix=f"gp50_{state.name}_") as workdir_s:
        workdir = Path(workdir_s)
        y_wav = workdir / "y.wav"

        _update(
            state,
            progress_cb,
            status="rendering",
            progress=0.2,
            detail="Rendering teacher signal (~1 min)…",
        )
        render_result = _run(
            [
                str(job.venv_a2),
                str(A2A1_DIR / "render_a2.py"),
                str(src),
                str(job.di_path),
                str(y_wav),
            ],
            job,
        )
        if job.cancelled:
            _update(state, progress_cb, status="cancelled", error="cancelled by user")
            return
        if render_result.returncode != 0 or not y_wav.exists():
            _update(
                state,
                progress_cb,
                status="failed",
                error=(
                    f"render failed (rc={render_result.returncode}): "
                    f"{render_result.stderr or render_result.stdout}"
                ),
            )
            return

        _update(
            state,
            progress_cb,
            status="training",
            progress=0.5,
            detail=f"Training 0/{job.epochs}",
        )

        # Live per-epoch progress: train_a1_070.py emits "DISTILL_PROGRESS: d/total"
        # per epoch; map it into the 0.5–0.95 band and estimate remaining time from
        # the average epoch duration so far.
        train_started = time.monotonic()

        def _on_train_line(line: str) -> None:
            prog = distill_protocol.parse_progress(line)
            if prog is None:
                return
            done, total = prog
            if total <= 0:
                return
            elapsed = time.monotonic() - train_started
            eta = (elapsed / done) * (total - done) if done > 0 else None
            _update(
                state,
                progress_cb,
                progress=0.5 + 0.45 * (done / total),
                detail=f"Training {done}/{total}",
                eta_seconds=eta,
            )

        # Both output formats now train + export in the 0.13.0 venv; the 0.5.x path
        # transcodes the 0.7.0 export down in-process (see a2a1/nam_transcode.py).
        # The 0.12.2 venv is no longer part of the pipeline.
        train_result = _run_streaming(
            [
                str(job.venv_a2),
                str(A2A1_DIR / "train_a1_070.py"),
                str(job.di_path),
                str(y_wav),
                str(workdir),
                "--epochs",
                str(job.epochs),
                "--arch",
                "standard",
                "--format",
                job.output_format,
            ],
            job,
            _on_train_line,
        )
        if job.cancelled:
            _update(state, progress_cb, status="cancelled", error="cancelled by user")
            return
        if train_result.returncode != 0:
            _update(
                state,
                progress_cb,
                status="failed",
                error=(
                    f"train failed (rc={train_result.returncode}): "
                    f"{train_result.stderr or train_result.stdout}"
                ),
            )
            return

        a1_nam = workdir / "a1.nam"
        if not a1_nam.exists():
            _update(
                state,
                progress_cb,
                status="failed",
                error=f"train reported success but no a1.nam produced: {train_result.stdout}",
            )
            return

        job.out_dir.mkdir(parents=True, exist_ok=True)
        dest = job.out_dir / f"{state.name}.nam"
        try:
            shutil.copyfile(a1_nam, dest)
        except Exception as e:
            _update(state, progress_cb, status="failed", error=f"copy failed: {e}")
            return

        combined = train_result.stdout + "\n" + train_result.stderr
        fmt_text = distill_protocol.parse_format(combined)

        _update(
            state,
            progress_cb,
            status="done",
            progress=1.0,
            detail=None,
            eta_seconds=None,
            output_path=str(dest),
            esr=distill_protocol.parse_esr(combined),
            format_ok=distill_protocol.format_ok(fmt_text),
        )


def run_job(job: ConvertJob, progress_cb: ProgressCallback) -> ConvertJob:
    """Run every file in `job` through detection + conversion.

    Per-file failures (subprocess crash, bad output, unsupported architecture)
    are isolated to that file's FileState (status='failed') and never raise
    out of this function — the rest of the batch keeps going.

    Job-level misconfiguration (unknown output_format, missing venvs or
    DI) raises immediately, before any file work starts.
    """
    if job.output_format not in ("0.5x", "0.7.0"):
        raise ValueError(f"unknown output_format {job.output_format!r}")
    if not job.venv_a2.exists():
        raise FileNotFoundError(f"0.13.0 venv python not found at {job.venv_a2}")
    if not job.di_path.exists():
        raise FileNotFoundError(f"DI file not found at {job.di_path}")

    for state in job.files:
        if job.cancelled:
            # Job cancelled: mark anything not already finished as cancelled and
            # stop starting new work.
            if state.status not in ("done", "failed", "cancelled"):
                _update(
                    state, progress_cb, status="cancelled", error="cancelled by user"
                )
            continue
        try:
            _convert_one(state, job, progress_cb)
        except Exception as e:  # never let one file kill the batch
            state.status = "failed"
            state.error = f"unexpected error: {e}"
            progress_cb(state)

    return job
