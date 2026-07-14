"""The wire contract for the device_io <-> patch-scripts subprocess seam.

app/device_io.py runs the MIDI scripts (write_patch.py, scan_bank.py,
read_bank_map.py) as subprocesses in .venv-midi and consumes their stdout.
Both sides import THIS module, so the schema is defined exactly once:

- scripts build events/results with the constructors below and print them
  with emit() — one JSON object per line, machine-readable stdout only
  (human commentary goes to stderr);
- device_io recovers them with parse_event_line() / parse_result().

stdlib-only on purpose: imported by the web app (.venv-app) and by the MIDI
scripts (.venv-midi) alike. Contract tests (test_device_protocol.py) exercise
emit -> parse round-trips with no hardware.
"""

from __future__ import annotations

import json
import sys

# --- event / result constructors -------------------------------------------------


def write_result(
    ok: bool,
    slot: int,
    sent: bool,
    *,
    packets: int | None = None,
    validated: bool | None = None,
    acks: int | None = None,
    verified_name: str | None = None,
    error: str | None = None,
) -> dict:
    """Terminal result of write_patch.py (one line, last on stdout)."""
    out = {"ok": ok, "slot": slot, "sent": sent}
    for k, v in (
        ("packets", packets),
        ("validated", validated),
        ("acks", acks),
        ("verified_name", verified_name),
        ("error", error),
    ):
        if v is not None:
            out[k] = v
    return out


def scan_start(total: int) -> dict:
    return {"event": "start", "total": total}


def scan_slot(i: int, slot: int, name: str, ok: bool, done: int, total: int) -> dict:
    """Progress: one preset read (ok) or failed after retry (not ok)."""
    return {
        "event": "slot",
        "i": i,
        "slot": slot,
        "name": name,
        "ok": ok,
        "done": done,
        "total": total,
    }


def scan_done(written: int, errors: int, outdir: str) -> dict:
    return {"event": "done", "written": written, "errors": errors, "outdir": outdir}


def sync_result(
    ok: bool,
    *,
    snaptones: dict | None = None,
    irs: dict | None = None,
    error: str | None = None,
) -> dict:
    """Terminal result of read_bank_map.py: the slot->name maps themselves,
    so the caller does not have to re-read bank_map.json as a side effect."""
    out: dict = {"ok": ok}
    if snaptones is not None:
        out["snaptones"] = snaptones
        out["count"] = len(snaptones)
    if irs is not None:
        out["irs"] = irs
        out["ir_count"] = len(irs)
    if error is not None:
        out["error"] = error
    return out


def select_result(
    ok: bool, slot: int, *, device: dict | None = None, error: str | None = None
) -> dict:
    """Terminal result of select_patch.py (a non-destructive Program Change)."""
    out: dict = {"ok": ok, "slot": slot}
    if device is not None:
        out["device"] = device
    if error is not None:
        out["error"] = error
    return out


def status_result(
    connected: bool, *, device: dict | None = None, port: str | None = None
) -> dict:
    """Terminal result of device_status.py: is a Valeton device connected, and which."""
    return {"connected": connected, "device": device, "port": port}


# --- emit (script side) -----------------------------------------------------------


def emit(obj: dict, stream=None) -> None:
    """Print one machine-readable JSON line (flushed) to stdout."""
    print(json.dumps(obj), file=stream or sys.stdout, flush=True)


# --- parse (device_io side) --------------------------------------------------------


def parse_event_line(line: str) -> dict | None:
    """One streamed progress line -> event dict, or None for non-protocol noise."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        ev = json.loads(line)
    except ValueError:
        return None
    return ev if isinstance(ev, dict) else None


def parse_result(stdout_text: str, fallback_error: str = "no result") -> dict:
    """Terminal result = the LAST JSON line on stdout (stray prints tolerated).
    Returns a structured {ok: False, error} if none is found."""
    for line in reversed((stdout_text or "").strip().splitlines()):
        ev = parse_event_line(line)
        if ev is not None:
            return ev
    return {"ok": False, "error": fallback_error}


def friendly_error(message: str) -> str:
    """Map raw script/stderr failure text to the message the UI should show."""
    msg = (message or "").strip()
    if "no ports" in msg.lower():
        return "pedal not found — connect it via USB and close Valeton Suite"
    return msg or "device operation failed"
