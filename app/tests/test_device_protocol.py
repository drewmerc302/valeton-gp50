"""Contract tests for the device_io <-> patch-scripts subprocess seam.

Both sides of the wire import patch/device_protocol.py; these tests prove the
emit -> parse round-trip and then exercise the REAL seam: device_io spawning a
subprocess and consuming its stdout — with fake transport scripts standing in
for the pedal, and one genuine dry-run of write_patch.py (no --send needs no
MIDI stack)."""

import glob
import os
import subprocess
import sys
import time

from app import device_io
from patch import device_protocol as proto

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _an_export() -> str:
    return sorted(glob.glob(os.path.join(PROJECT_ROOT, "presetExports", "*.prst")))[0]


# --- pure round-trips ---------------------------------------------------------


def test_write_result_round_trip():
    r = proto.write_result(
        True, 90, True, packets=29, validated=True, acks=29, verified_name="US Lead"
    )
    parsed = proto.parse_result(
        "stray human line\n" + __import__("json").dumps(r) + "\n"
    )
    assert parsed == r


def test_scan_events_round_trip():
    for ev in (
        proto.scan_start(100),
        proto.scan_slot(3, 3, "Power Lead", True, 4, 100),
        proto.scan_done(99, 1, "/tmp/x"),
    ):
        line = __import__("json").dumps(ev)
        assert proto.parse_event_line(line) == ev
    assert proto.parse_event_line("INFO: not protocol") is None
    assert proto.parse_event_line("") is None


def test_parse_result_takes_last_json_line_and_survives_noise():
    good = proto.write_result(True, 5, False, packets=29, validated=True)
    stdout = "\n".join(
        ["debug noise", '{"event": "slot", "ok": true}', __import__("json").dumps(good)]
    )
    assert proto.parse_result(stdout) == good
    # no JSON at all -> structured error, never an exception
    r = proto.parse_result("complete garbage", fallback_error="write failed")
    assert r == {"ok": False, "error": "write failed"}


def test_friendly_error_maps_missing_pedal():
    assert "pedal not found" in proto.friendly_error("RuntimeError: no ports available")
    assert "pedal not found" in proto.friendly_error("No Ports")
    assert proto.friendly_error("something else") == "something else"
    assert proto.friendly_error("") == "device operation failed"


# --- the real seam: write_patch.py dry-run under this interpreter ---------------


def test_write_patch_script_dry_run_emits_contract():
    """Run the actual script (no --send: builds + validates only, no MIDI import)
    and parse its stdout exactly the way device_io does."""
    proc = subprocess.run(
        [
            sys.executable,
            os.path.join("patch", "write_patch.py"),
            "--prst",
            _an_export(),
            "--slot",
            "7",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    result = proto.parse_result(proc.stdout)
    assert result["ok"] is True
    assert result["slot"] == 7 and result["sent"] is False
    assert result["packets"] == 29 and result["validated"] is True


def test_write_patch_script_bad_slot_is_structured_error():
    proc = subprocess.run(
        [
            sys.executable,
            os.path.join("patch", "write_patch.py"),
            "--prst",
            _an_export(),
            "--slot",
            "150",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    result = proto.parse_result(proc.stdout)
    assert result["ok"] is False and "out of range" in result["error"]


# --- device_io end-to-end against fake transport scripts -------------------------


def _fake_script(tmp_path, name: str, body: str) -> str:
    p = tmp_path / name
    p.write_text(body)
    return str(p)


def test_device_io_write_patch_parses_fake_writer(tmp_path, monkeypatch):
    ok_line = (
        "import sys, os\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from patch import device_protocol as proto\n"
        "print('stray suite-style noise')\n"
        "proto.emit(proto.write_result(True, 12, True, packets=29, validated=True,"
        " acks=29, verified_name='FakeName'))\n"
    )
    monkeypatch.setattr(device_io, "MIDI_PY", sys.executable)
    monkeypatch.setattr(device_io, "WRITER", _fake_script(tmp_path, "w.py", ok_line))
    monkeypatch.setattr(device_io, "SCAN_DIR", str(tmp_path / "scan"))  # no cache
    prst = open(_an_export(), "rb").read()
    r = device_io.write_patch(prst, 12)
    assert r["ok"] is True and r["verified_name"] == "FakeName" and r["acks"] == 29


def test_device_io_write_patch_friendly_error_from_fake_writer(tmp_path, monkeypatch):
    err_line = (
        "import sys, os\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from patch import device_protocol as proto\n"
        "proto.emit(proto.write_result(False, 12, False,"
        " error='RuntimeError: no ports available'))\n"
    )
    monkeypatch.setattr(device_io, "MIDI_PY", sys.executable)
    monkeypatch.setattr(device_io, "WRITER", _fake_script(tmp_path, "w.py", err_line))
    prst = open(_an_export(), "rb").read()
    r = device_io.write_patch(prst, 12)
    assert r["ok"] is False and "pedal not found" in r["error"]


def test_device_io_sync_parses_fake_reader(tmp_path, monkeypatch):
    body = (
        "import sys, os\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from patch import device_protocol as proto\n"
        "print('human detail', file=sys.stderr)\n"
        "proto.emit(proto.sync_result(True, snaptones={'50': 'MES LS II'},"
        " irs={'0': 'American T'}))\n"
    )
    monkeypatch.setattr(device_io, "MIDI_PY", sys.executable)
    monkeypatch.setattr(device_io, "READER", _fake_script(tmp_path, "r.py", body))
    r = device_io.sync_snaptones()
    assert r["ok"] is True
    assert r["count"] == 1 and r["ir_count"] == 1
    assert r["snaptones"] == {"50": "MES LS II"}


def test_device_io_sync_maps_reader_crash_to_friendly_error(tmp_path, monkeypatch):
    body = "import sys\nprint('no ports available', file=sys.stderr)\nsys.exit(1)\n"
    monkeypatch.setattr(device_io, "MIDI_PY", sys.executable)
    monkeypatch.setattr(device_io, "READER", _fake_script(tmp_path, "r.py", body))
    r = device_io.sync_snaptones()
    assert r["ok"] is False and "pedal not found" in r["error"]


def test_device_io_scan_streams_fake_scanner_events(tmp_path, monkeypatch):
    body = (
        "import sys, os\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from patch import device_protocol as proto\n"
        "proto.emit(proto.scan_start(3))\n"
        "proto.emit(proto.scan_slot(0, 0, 'US Lead', True, 1, 3))\n"
        "proto.emit(proto.scan_slot(1, 1, 'Neo Soul', False, 2, 3))\n"
        "proto.emit(proto.scan_slot(2, 2, 'Star Night', True, 3, 3))\n"
        "proto.emit(proto.scan_done(2, 1, sys.argv[3]))\n"
    )
    monkeypatch.setattr(device_io, "MIDI_PY", sys.executable)
    monkeypatch.setattr(device_io, "SCANNER", _fake_script(tmp_path, "s.py", body))
    monkeypatch.setattr(device_io, "SCAN_DIR", str(tmp_path / "scan"))
    r = device_io.scan_bank()
    assert r == {"ok": True, "started": True}
    deadline = time.time() + 10
    while time.time() < deadline:
        st = device_io.scan_status()
        if not st["running"]:
            break
        time.sleep(0.05)
    st = device_io.scan_status()
    assert st["running"] is False
    assert st["done"] == 3 and st["errors"] == 1 and st["written"] == 2
    assert st["error"] is None
