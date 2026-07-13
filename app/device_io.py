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
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIDI_PY = os.path.join(PROJECT_ROOT, ".venv-midi", "bin", "python")
READER = os.path.join(PROJECT_ROOT, "patch", "read_bank_map.py")
BANK_MAP = os.path.join(PROJECT_ROOT, "patch", "bank_map.json")

_lock = threading.Lock()


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
