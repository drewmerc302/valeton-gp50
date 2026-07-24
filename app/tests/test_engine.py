"""Fast, hermetic tests for app.engine.

All subprocess.run calls into the .venv render+train scripts are monkeypatched
with canned output, so these tests never run a real conversion (no torch, no
NAM training). The one exception is architecture detection, which reads
refs/A2.nam's JSON header directly (no model load).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app import engine
from app.engine import ConvertJob, FileState, detect_architecture, run_job

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _write_nam(path: Path, architecture: str, version: str) -> None:
    path.write_text(
        json.dumps(
            {
                "version": version,
                "architecture": architecture,
                "config": {"layers": [{"head_size": 8}]},
                "weights": [],
                "sample_rate": 48000,
            }
        )
    )


def _make_job(tmp_path, input_paths, **overrides) -> ConvertJob:
    di = tmp_path / "di.wav"
    di.write_bytes(b"RIFF....WAVEfmt ")  # never read for real; subprocess is mocked
    kwargs = dict(
        input_paths=input_paths,
        di_path=di,
        epochs=1,
        out_dir=tmp_path / "out",
        venv_a2=Path(sys.executable),
        venv_a1=Path(sys.executable),
    )
    kwargs.update(overrides)
    return ConvertJob(**kwargs)


def _collect_cb():
    events = []

    def cb(state: FileState) -> None:
        events.append((state.name, state.status))

    return cb, events


def _fake_subprocess_ok(cmd, **kwargs):
    """Canned success for render_a2.py and the 0.13.0 train_a1_070.py stage
    (the 0.5x path transcodes its 0.7.0 export down in-process, emitting 0.5.x)."""
    cmd = [str(c) for c in cmd]
    script = cmd[1]
    if "render_a2.py" in script:
        y_out = Path(cmd[4])
        y_out.write_bytes(b"fake wav bytes")
        return subprocess.CompletedProcess(
            cmd, 0, stdout="rendered 1000 samples\n", stderr=""
        )
    if "train_a1_070.py" in script:
        outdir = Path(cmd[4])
        a1 = outdir / "a1.nam"
        _write_nam(a1, "WaveNet", "0.5.4")
        stdout = (
            "FORMAT: version=0.5.4 arch=WaveNet head_size=True -> OK (GP-50 compatible)\n"
            "DISTILL_ESR: 0.012345\n"
            f"A1_NAM: {a1}\n"
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
    raise AssertionError(f"unexpected command: {cmd}")


def _fake_subprocess_render_fails_for_bad(cmd, **kwargs):
    """Like _fake_subprocess_ok, but render_a2.py fails whenever the source
    file's stem is 'bad' — used to test per-file failure isolation."""
    cmd = [str(c) for c in cmd]
    script = cmd[1]
    if "render_a2.py" in script:
        src = Path(cmd[2])
        if src.stem == "bad":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="render boom")
        y_out = Path(cmd[4])
        y_out.write_bytes(b"fake wav bytes")
        return subprocess.CompletedProcess(
            cmd, 0, stdout="rendered 1000 samples\n", stderr=""
        )
    if "train_a1_070.py" in script:
        return _fake_subprocess_ok(cmd, **kwargs)
    raise AssertionError(f"unexpected command: {cmd}")


# --- architecture detection (reads refs/A2.nam directly, no conversion) ---


def test_detect_architecture_a2_reference_file():
    a2_path = PROJECT_ROOT / "refs" / "A2.nam"
    arch, version = detect_architecture(a2_path)
    assert arch == "SlimmableContainer"
    assert version  # some version string is present


def test_detect_architecture_already_a1(tmp_path):
    p = tmp_path / "already_a1.nam"
    _write_nam(p, "WaveNet", "0.5.4")
    arch, version = detect_architecture(p)
    assert arch == "WaveNet"
    assert version == "0.5.4"


# --- happy path: A2 distillation, mocked subprocess ---


def test_a2_distillation_happy_path(tmp_path, monkeypatch):
    monkeypatch.setattr(engine.subprocess, "run", _fake_subprocess_ok)

    src = tmp_path / "capture.nam"
    _write_nam(src, "SlimmableContainer", "0.7.0")

    job = _make_job(tmp_path, [src])
    cb, events = _collect_cb()
    run_job(job, cb)

    state = job.files[0]
    assert state.status == "done"
    assert state.src_arch == "SlimmableContainer"
    assert state.esr == pytest.approx(0.012345)
    assert state.format_ok is True
    assert state.output_path is not None
    assert Path(state.output_path).exists()
    assert Path(state.output_path).name == "capture.nam"
    # status transitions were reported in order, ending in 'done'
    statuses = [s for _, s in events]
    assert statuses == ["detecting", "rendering", "training", "done"]


# --- already-A1 0.5.x passthrough ---


def test_already_a1_passthrough(tmp_path, monkeypatch):
    def _boom(cmd, **kwargs):
        raise AssertionError("subprocess should not be invoked for passthrough files")

    monkeypatch.setattr(engine.subprocess, "run", _boom)

    src = tmp_path / "already_a1.nam"
    _write_nam(src, "WaveNet", "0.5.0")

    job = _make_job(tmp_path, [src])
    cb, events = _collect_cb()
    run_job(job, cb)

    state = job.files[0]
    assert state.status == "done"
    assert state.src_arch == "WaveNet"
    assert state.format_ok is True
    assert state.esr is None  # no distillation happened, no ESR to report
    assert Path(state.output_path).read_text() == src.read_text()


# --- per-file failure isolation ---


def test_failing_file_does_not_kill_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(engine.subprocess, "run", _fake_subprocess_render_fails_for_bad)

    good = tmp_path / "good.nam"
    bad = tmp_path / "bad.nam"
    _write_nam(good, "SlimmableContainer", "0.7.0")
    _write_nam(bad, "SlimmableContainer", "0.7.0")

    job = _make_job(tmp_path, [good, bad])
    cb, events = _collect_cb()
    run_job(job, cb)  # must not raise

    by_name = {s.name: s for s in job.files}
    assert by_name["good"].status == "done"
    assert by_name["bad"].status == "failed"
    assert "render boom" in by_name["bad"].error
    assert by_name["bad"].output_path is None


def test_unsupported_architecture_isolated(tmp_path, monkeypatch):
    def _boom(cmd, **kwargs):
        raise AssertionError(
            "subprocess should not be invoked for unsupported architectures"
        )

    monkeypatch.setattr(engine.subprocess, "run", _boom)

    src = tmp_path / "mystery.nam"
    _write_nam(src, "LSTM", "0.5.0")

    job = _make_job(tmp_path, [src])
    cb, events = _collect_cb()
    run_job(job, cb)

    state = job.files[0]
    assert state.status == "failed"
    assert "unsupported" in state.error.lower()


# --- 0.7.0 output format: wired to train_a1_070.py in the .venv (0.13.0) venv ---


def _fake_subprocess_070(cmd, **kwargs):
    """Canned success for render_a2.py and train_a1_070.py (0.7.0 export)."""
    cmd = [str(c) for c in cmd]
    script = cmd[1]
    if "render_a2.py" in script:
        y_out = Path(cmd[4])
        y_out.write_bytes(b"fake wav bytes")
        return subprocess.CompletedProcess(
            cmd, 0, stdout="rendered 1000 samples\n", stderr=""
        )
    if "train_a1_070.py" in script:
        outdir = Path(cmd[4])
        a1 = outdir / "a1.nam"
        _write_nam(a1, "WaveNet", "0.7.0")
        stdout = (
            "FORMAT: version=0.7.0 arch=WaveNet head=True -> OK (0.7.0 export)\n"
            "DISTILL_ESR: 0.062862\n"
            f"A1_NAM: {a1}\n"
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
    raise AssertionError(f"unexpected command: {cmd}")


def test_output_format_0_7_0_invokes_train_a1_070(tmp_path, monkeypatch):
    monkeypatch.setattr(engine.subprocess, "run", _fake_subprocess_070)

    src = tmp_path / "capture.nam"
    _write_nam(src, "SlimmableContainer", "0.7.0")

    job = _make_job(tmp_path, [src], output_format="0.7.0")
    cb, events = _collect_cb()
    run_job(job, cb)  # must not raise NotImplementedError

    state = job.files[0]
    assert state.status == "done"
    assert state.esr == pytest.approx(0.062862)
    assert state.format_ok is True
    assert Path(state.output_path).exists()
    statuses = [s for _, s in events]
    assert statuses == ["detecting", "rendering", "training", "done"]


def test_0_5x_path_uses_train_a1_070_in_venv_a2(tmp_path, monkeypatch):
    """The 0.12.2 venv is retired: the 0.5x (GP-50) path now trains + exports in
    the 0.13.0 venv via train_a1_070.py --format 0.5x, transcoding in-process."""
    seen = {}

    def _capture(cmd, **kwargs):
        cmd = [str(c) for c in cmd]
        if "train_a1_070.py" in cmd[1]:
            seen["train_cmd"] = cmd
        return _fake_subprocess_ok(cmd, **kwargs)

    monkeypatch.setattr(engine.subprocess, "run", _capture)

    src = tmp_path / "capture.nam"
    _write_nam(src, "SlimmableContainer", "0.7.0")
    job = _make_job(tmp_path, [src], output_format="0.5x")
    cb, _ = _collect_cb()
    run_job(job, cb)

    assert job.files[0].status == "done"
    train_cmd = seen["train_cmd"]
    assert train_cmd[0] == str(job.venv_a2)  # 0.13.0 venv, not venv_a1
    assert "--format" in train_cmd
    assert train_cmd[train_cmd.index("--format") + 1] == "0.5x"


def test_unknown_output_format_raises_value_error(tmp_path):
    src = tmp_path / "capture.nam"
    _write_nam(src, "SlimmableContainer", "0.7.0")

    job = _make_job(tmp_path, [src], output_format="bogus")
    cb, _ = _collect_cb()
    with pytest.raises(ValueError):
        run_job(job, cb)
