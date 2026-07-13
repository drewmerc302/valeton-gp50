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

import json
import os
import subprocess
import tempfile
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIDI_PY = os.path.join(PROJECT_ROOT, ".venv-midi", "bin", "python")
READER = os.path.join(PROJECT_ROOT, "patch", "read_bank_map.py")
WRITER = os.path.join(PROJECT_ROOT, "patch", "write_patch.py")
SCANNER = os.path.join(PROJECT_ROOT, "patch", "scan_bank.py")
SCAN_DIR = os.path.join(PROJECT_ROOT, "device_scan")
BANK_MAP = os.path.join(PROJECT_ROOT, "patch", "bank_map.json")

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
    Returns {ok, count, snaptones|error}. Never raises: device problems become
    a structured error the UI can show."""
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
            err = (proc.stderr or proc.stdout or "").strip()
            if "no ports available" in err or "no ports" in err:
                return {
                    "ok": False,
                    "error": "pedal not found — connect it via USB and close Valeton Suite",
                }
            msg = err.splitlines()[-1:] or ["read failed"]
            return {"ok": False, "error": msg[0]}
        try:
            bank = json.load(open(BANK_MAP))
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"read succeeded but bank_map unreadable: {e}",
            }
        snaps = bank.get("snaptone", {})
        irs = bank.get("ir", {})
        return {
            "ok": True,
            "count": len(snaps),
            "ir_count": len(irs),
            "snaptones": snaps,
            "irs": irs,
        }
    finally:
        _lock.release()


def write_patch(prst: bytes, slot: int, timeout: float = 30.0) -> dict:
    """Write a 552-byte .prst to device patch index `slot` (0..99), then read the
    slot name back to verify. Gated + paced in the subprocess. Returns
    {ok, sent, acks, verified_name|error}. Never raises."""
    if not 0 <= slot <= 99:
        return {"ok": False, "error": f"slot {slot} out of range (0..99)"}
    if len(prst) != 552:
        return {"ok": False, "error": f"expected a 552-byte .prst, got {len(prst)}"}
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
        out = (proc.stdout or "").strip().splitlines()
        try:
            result = json.loads(out[-1]) if out else {}
        except (ValueError, IndexError):
            err = (proc.stderr or proc.stdout or "write failed").strip().splitlines()
            result = {"ok": False, "error": err[-1] if err else "write failed"}
        # friendly-ize a missing pedal whether it surfaced structured or on stderr
        if not result.get("ok") and "no ports" in str(result.get("error", "")).lower():
            result["error"] = (
                "pedal not found — connect it via USB and close Valeton Suite"
            )
        return result
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        _lock.release()


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
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
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
            if "no ports" in msg.lower():
                msg = "pedal not found — connect it via USB and close Valeton Suite"
            _set_scan(error=msg)
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
