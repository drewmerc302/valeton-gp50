"""Optional LIVE device read for the web app.

The app is normally file-based (reads presetExports/). This module lets the
"Sync from device" button pull the authoritative SnapTone catalog straight off
the pedal — without the Valeton Suite or the CLI — by running the hardened,
tested reader (patch/read_bank_map.py) as a subprocess in the MIDI venv.

Subprocess isolation is deliberate: MIDI/rtmidi lives in .venv-midi, not the web
venv, and the reader has its own request cap + settle to avoid wedging the pedal.
A module lock serializes syncs so two requests can't hit the device at once.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading

from patch import device_protocol as proto
from patch import prst_format

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIDI_PY = os.path.join(PROJECT_ROOT, ".venv-midi", "bin", "python")
READER = os.path.join(PROJECT_ROOT, "patch", "read_bank_map.py")
WRITER = os.path.join(PROJECT_ROOT, "patch", "write_patch.py")
SCANNER = os.path.join(PROJECT_ROOT, "patch", "scan_bank.py")
SCAN_DIR = os.path.join(PROJECT_ROOT, "device_scan")

_lock = threading.Lock()
_scan_lock = threading.Lock()
_scan = {
    "running": False,
    "done": 0,
    "total": 100,
    "current": "",
    "written": 0,
    "errors": 0,
    "error": None,
}


def sync_snaptones(timeout: float = 25.0) -> dict:
    """Read the SnapTone catalog from the pedal and refresh patch/bank_map.json.
    Returns the reader's sync_result ({ok, count, ir_count, snaptones, irs} or
    {ok: False, error}). Never raises: device problems become a structured
    error the UI can show."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "error": "a device sync is already running"}
    try:
        if not os.path.exists(MIDI_PY):
            return {"ok": False, "error": "MIDI environment (.venv-midi) not found"}
        try:
            proc = subprocess.run(
                [MIDI_PY, READER],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": "device did not respond (is it connected and Suite closed?)",
            }
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "read failed").strip()
            return {
                "ok": False,
                "error": proto.friendly_error(err.splitlines()[-1] if err else ""),
            }
        result = proto.parse_result(proc.stdout, fallback_error="read failed")
        if not result.get("ok"):
            result["error"] = proto.friendly_error(str(result.get("error", "")))
        return result
    finally:
        _lock.release()


def write_patch(prst: bytes, slot: int, timeout: float = 30.0) -> dict:
    """Write a 552-byte .prst to device patch index `slot` (0..99), then read the
    slot name back to verify. Gated + paced in the subprocess. Returns
    {ok, sent, acks, verified_name|error}. Never raises."""
    if not 0 <= slot <= 99:
        return {"ok": False, "error": f"slot {slot} out of range (0..99)"}
    try:
        prst_format.check_length(prst)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not _lock.acquire(blocking=False):
        return {"ok": False, "error": "a device operation is already running"}
    tmp = None
    try:
        if not os.path.exists(MIDI_PY):
            return {"ok": False, "error": "MIDI environment (.venv-midi) not found"}
        fd, tmp = tempfile.mkstemp(suffix=".prst")
        with os.fdopen(fd, "wb") as f:
            f.write(prst)
        try:
            proc = subprocess.run(
                [
                    MIDI_PY,
                    WRITER,
                    "--prst",
                    tmp,
                    "--slot",
                    str(slot),
                    "--send",
                    "--verify",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": "device did not respond (connected? Suite closed?)",
            }
        fallback = (proc.stderr or proc.stdout or "write failed").strip().splitlines()
        result = proto.parse_result(
            proc.stdout, fallback_error=fallback[-1] if fallback else "write failed"
        )
        if not result.get("ok"):
            result["error"] = proto.friendly_error(str(result.get("error", "")))
        if result.get("ok"):
            _cache_write(
                slot, prst
            )  # keep the local scan cache in sync with the device
        return result
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        _lock.release()


def _cache_write(slot: int, prst: bytes) -> None:
    """Mirror a device write into the device_scan/ cache so the Explorer reflects it
    without a re-scan. No-op unless a scan cache already exists."""
    import glob

    if not glob.glob(os.path.join(SCAN_DIR, "*.prst")):
        return
    name = prst_format.read_name(prst) or f"slot{slot}"
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
    for old in glob.glob(os.path.join(SCAN_DIR, f"{slot:02d}-*.prst")):
        os.remove(old)
    with open(os.path.join(SCAN_DIR, f"{slot:02d}-{safe}.prst"), "wb") as f:
        f.write(prst)


def scan_status() -> dict:
    with _scan_lock:
        return dict(_scan)


def _set_scan(**kw):
    with _scan_lock:
        _scan.update(kw)


def _run_scan():
    """Background: run the scanner subprocess, stream its JSON progress into _scan.
    Writes a fresh .prst per slot into device_scan/; patchlib then prefers that dir."""
    import shutil

    try:
        if os.path.isdir(SCAN_DIR):
            shutil.rmtree(SCAN_DIR)  # start clean so a partial old scan isn't mixed in
        os.makedirs(SCAN_DIR, exist_ok=True)
        proc = subprocess.Popen(
            [MIDI_PY, SCANNER, "0", "99", SCAN_DIR],
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for line in proc.stdout:
            ev = proto.parse_event_line(line)
            if ev is None:
                continue
            if ev.get("event") == "slot":
                _set_scan(
                    done=ev["done"],
                    total=ev["total"],
                    current=ev.get("name", ""),
                    errors=_scan["errors"] + (0 if ev.get("ok") else 1),
                )
            elif ev.get("event") == "done":
                _set_scan(written=ev.get("written", 0))
        proc.wait(timeout=10)
        if proc.returncode not in (0, None):
            err = (proc.stderr.read() or "").strip().splitlines()
            msg = err[-1] if err else f"scanner exited {proc.returncode}"
            _set_scan(error=proto.friendly_error(msg))
    except Exception as e:  # noqa: BLE001
        _set_scan(error=f"{type(e).__name__}: {e}")
    finally:
        _set_scan(running=False)
        _lock.release()


def scan_bank() -> dict:
    """Start a full 100-preset device scan in the background (~60-90s). Poll
    scan_status() for progress. Returns immediately."""
    if not os.path.exists(MIDI_PY):
        return {"ok": False, "error": "MIDI environment (.venv-midi) not found"}
    if not _lock.acquire(blocking=False):
        return {"ok": False, "error": "a device operation is already running"}
    with _scan_lock:
        _scan.update(
            running=True, done=0, total=100, current="", written=0, errors=0, error=None
        )
    threading.Thread(target=_run_scan, daemon=True).start()
    return {"ok": True, "started": True}
