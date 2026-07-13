"""Conversion engine: run NAM A2->A1 batch jobs with progress callbacks.

Wraps the existing two-venv distillation pipeline as an importable,
callback-driven job runner. Rendering always happens in the 0.13.0 venv
(the only one that can load the A2 SlimmableContainer format); training
happens in whichever venv produces the requested output format:

    output_format='0.5x':
        A2.nam --(render, .venv/0.13.0)--> y.wav
               --(train+export, .venv-a1/0.12.2, a2a1/train_a1.py)--> A1.nam (0.5.x)

    output_format='0.7.0':
        A2.nam --(render, .venv/0.13.0)--> y.wav
               --(train+export, .venv/0.13.0, a2a1/train_a1_070.py)--> A1.nam (0.7.0)

Already-A1 0.5.x files are detected and copied through untouched (regardless
of requested output_format — no re-distillation of already-compatible files).
This module does no device I/O of any kind — it only shells out to the local
training venvs and touches the filesystem.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
A2A1_DIR = PROJECT_ROOT / "a2a1"
DEFAULT_VENV_A2 = PROJECT_ROOT / ".venv" / "bin" / "python"
DEFAULT_VENV_A1 = PROJECT_ROOT / ".venv-a1" / "bin" / "python"
DEFAULT_DI = PROJECT_ROOT / "refs" / "v3_0_0.wav"
DEFAULT_OUT_DIR = PROJECT_ROOT / "out"

_ESR_RE = re.compile(r"DISTILL_ESR:\s*([0-9.eE+-]+)")
_FORMAT_RE = re.compile(r"FORMAT:\s*(.+)")


@dataclass
class FileState:
    """Per-file conversion state, updated in place and handed to progress_cb."""

    input_path: str
    name: str
    status: str = "queued"  # queued|detecting|rendering|training|done|failed
    progress: float = 0.0  # 0.0-1.0, coarse
    esr: Optional[float] = None
    output_path: Optional[str] = None
    format_ok: Optional[bool] = None
    error: Optional[str] = None
    src_arch: Optional[str] = None


ProgressCallback = Callable[[FileState], None]


@dataclass
class ConvertJob:
    """A batch conversion request plus the live per-file state list."""

    input_paths: List[Path]
    di_path: Path = DEFAULT_DI
    epochs: int = 80
    output_format: str = "0.5x"  # '0.5x' | '0.7.0'
    out_dir: Path = DEFAULT_OUT_DIR
    venv_a2: Path = DEFAULT_VENV_A2
    venv_a1: Path = DEFAULT_VENV_A1
    files: List[FileState] = field(default_factory=list)

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


def detect_architecture(nam_path: Path) -> Tuple[Optional[str], str]:
    """Read a .nam file's JSON header. Returns (architecture, version)."""
    with open(nam_path) as fp:
        d = json.load(fp)
    return d.get("architecture"), str(d.get("version", "?"))


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _update(state: FileState, progress_cb: ProgressCallback, **changes) -> None:
    for k, v in changes.items():
        setattr(state, k, v)
    progress_cb(state)


def _format_ok(fmt_text: Optional[str]) -> Optional[bool]:
    if not fmt_text:
        return None
    return "OK" in fmt_text and "UNEXPECTED" not in fmt_text


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

        _update(state, progress_cb, status="rendering", progress=0.2)
        render_result = _run(
            [
                str(job.venv_a2),
                str(A2A1_DIR / "render_a2.py"),
                str(src),
                str(job.di_path),
                str(y_wav),
            ]
        )
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

        _update(state, progress_cb, status="training", progress=0.5)
        if job.output_format == "0.7.0":
            train_venv = job.venv_a2
            train_script = A2A1_DIR / "train_a1_070.py"
        else:
            train_venv = job.venv_a1
            train_script = A2A1_DIR / "train_a1.py"
        train_result = _run(
            [
                str(train_venv),
                str(train_script),
                str(job.di_path),
                str(y_wav),
                str(workdir),
                "--epochs",
                str(job.epochs),
                "--arch",
                "standard",
            ]
        )
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
        m_esr = _ESR_RE.search(combined)
        m_fmt = _FORMAT_RE.search(combined)
        esr_val = float(m_esr.group(1)) if m_esr else None
        fmt_text = m_fmt.group(1).strip() if m_fmt else None

        _update(
            state,
            progress_cb,
            status="done",
            progress=1.0,
            output_path=str(dest),
            esr=esr_val,
            format_ok=_format_ok(fmt_text),
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
    if not job.venv_a1.exists():
        raise FileNotFoundError(f"0.12.2 venv python not found at {job.venv_a1}")
    if not job.di_path.exists():
        raise FileNotFoundError(f"DI file not found at {job.di_path}")

    for state in job.files:
        try:
            _convert_one(state, job, progress_cb)
        except Exception as e:  # never let one file kill the batch
            state.status = "failed"
            state.error = f"unexpected error: {e}"
            progress_cb(state)

    return job
