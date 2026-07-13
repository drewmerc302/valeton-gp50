#!/usr/bin/env python3
"""Write one .prst to a device slot, gated + verified. Runs in .venv-midi (needs
mido/rtmidi). Emits a single JSON line so the web app (app/device_io.py) can parse it.

  python write_patch.py --prst FILE --slot N [--send] [--verify]

Without --send it only builds + validates (dry run). --send performs the real,
paced, ACK-checked write; --verify reads the slot name back afterward."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import device_write

PORT = "GP-50"


def read_slot_name(slot: int):
    """Read the patch-name bank and return the name at `slot` (or None)."""
    from patch import live_read

    _, replies = live_read.read_bank(0x40)
    banks = live_read.reassemble(replies)
    blob = max(banks.values(), key=len) if banks else b""
    for idx, nm in live_read.split_names(blob):
        if idx == slot:
            return nm
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prst", required=True)
    ap.add_argument("--slot", type=int, required=True)
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    out = {"ok": False, "slot": a.slot, "sent": False}
    try:
        if not 0 <= a.slot <= 99:
            raise ValueError(f"slot {a.slot} out of range 0..99")
        prst = open(a.prst, "rb").read()
        packets = device_write.build_patch_write_stream(prst, a.slot)
        ok, reason = device_write.validate_stream(packets)
        out["packets"] = len(packets)
        out["validated"] = ok
        if not ok:
            raise ValueError(f"stream failed validation: {reason}")

        if a.send:
            acks = device_write.send_stream(PORT, packets, confirm=True, validated=ok)
            out["sent"] = True
            out["acks"] = acks
            if a.verify:
                out["verified_name"] = read_slot_name(a.slot)
        out["ok"] = True
    except Exception as e:  # noqa: BLE001 — surface any failure as JSON to the caller
        out["error"] = f"{type(e).__name__}: {e}"
    print(json.dumps(out))


if __name__ == "__main__":
    main()
