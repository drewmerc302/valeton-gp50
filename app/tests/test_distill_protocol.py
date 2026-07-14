"""Contract tests for the engine <-> a2a1 train-script stdout seam.

Same shape as test_device_protocol: both sides import a2a1/distill_protocol,
so emit -> parse round-trips prove the seam without running torch."""

import contextlib
import io
import os
import subprocess
import sys

from a2a1 import distill_protocol as dp

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _emitted(fn, *args) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def test_emit_parse_round_trip():
    out = _emitted(dp.emit_esr, 0.044031) + _emitted(
        dp.emit_format, "OK (WaveNet 0.5.2)"
    )
    combined = "epoch 79/80 loss=0.001\n" + out + "A1_NAM: /tmp/a1.nam\n"
    assert dp.parse_esr(combined) == 0.044031
    assert dp.parse_format(combined) == "OK (WaveNet 0.5.2)"


def test_parse_absent_tokens_is_none():
    assert dp.parse_esr("no tokens here") is None
    assert dp.parse_format("") is None
    assert dp.format_ok(None) is None


def test_format_ok_verdicts():
    assert dp.format_ok("OK (WaveNet 0.5.2)") is True
    assert dp.format_ok("UNEXPECTED version 0.7.0") is False
    assert dp.format_ok("OK but UNEXPECTED head size") is False


def test_scientific_notation_esr_parses():
    line = _emitted(dp.emit_esr, 4.4e-05)
    assert dp.parse_esr(line) == 4.4e-05


def test_sibling_import_works_like_a_train_script():
    """Train scripts import distill_protocol as a sibling (sys.path[0] = a2a1/).
    Prove that import style + emit under a bare interpreter, then parse the
    real subprocess stdout exactly like engine.py does."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import distill_protocol as dp; dp.emit_format('OK (WaveNet 0.5.2)');"
            " dp.emit_esr(0.0123)",
        ],
        cwd=os.path.join(PROJECT_ROOT, "a2a1"),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    assert dp.parse_esr(proc.stdout) == 0.0123
    assert dp.format_ok(dp.parse_format(proc.stdout)) is True


def test_train_scripts_compile_and_reference_protocol():
    # torch venvs aren't importable here; at minimum the scripts must compile
    # and emit through the shared module, never raw token prints.
    for script in ("train_a1.py", "train_a1_070.py", "a2_to_a1.py"):
        path = os.path.join(PROJECT_ROOT, "a2a1", script)
        src = open(path).read()
        compile(src, script, "exec")
        assert "distill_protocol" in src, f"{script} bypasses the contract"
        assert 'print(f"DISTILL_ESR' not in src and 'print(f"FORMAT' not in src
