#!/usr/bin/env python3
"""Write one .prst to a device slot, gated + verified. Runs in .venv-midi (needs
mido/rtmidi). Emits a single JSON line so the web app (app/device_io.py) can parse it.

  python write_patch.py --prst FILE --slot N [--send] [--verify]

Without --send it only builds + validates (dry run). --send performs the real,
paced, ACK-checked write; --verify reads the slot name back afterward."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import device_protocol, device_write
from patch.prst_format import detect


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
    ap.add_argument(
        "--allow-unverified",
        action="store_true",
        help="override the write-protocol gate for a device that isn't "
        "capture-verified (GP-5). Risk: unconfirmed opcodes may disrupt the device.",
    )
    a = ap.parse_args()

    out = {"packets": None, "validated": None, "acks": None, "verified_name": None}
    sent = False
    try:
        if not 0 <= a.slot <= 99:
            raise ValueError(f"slot {a.slot} out of range 0..99")
        prst = open(a.prst, "rb").read()
        src = detect(prst)  # raises on an unrecognized .prst
        packets = device_write.build_patch_write_stream(prst, a.slot)
        ok, reason = device_write.validate_stream(packets)
        out["packets"] = len(packets)
        out["validated"] = ok
        if not ok:
            raise ValueError(f"stream failed validation: {reason}")

        if a.send:
            from patch import live_read

            port, connected = live_read.find_port()
            if src.key != connected.key:
                raise ValueError(
                    f"{a.prst} is a {src.name} preset but the connected device is "
                    f"{connected.name} — convert it first (patch/convert.py)"
                )
            if (
                not device_write.WRITE_VERIFIED.get(connected.key)
                and not a.allow_unverified
            ):
                raise ValueError(
                    f"{connected.name} patch-write protocol is not capture-verified "
                    f"(command/header assumed from the GP-50). Refusing. Capture a "
                    f"{connected.name} Suite import to confirm, or pass "
                    f"--allow-unverified to override at your own risk."
                )
            acks = device_write.send_stream(
                port,
                packets,
                confirm=True,
                validated=ok,
                allow_unverified=a.allow_unverified,
            )
            sent = True
            out["acks"] = acks
            if a.verify:
                out["verified_name"] = read_slot_name(a.slot)
        result = device_protocol.write_result(True, a.slot, sent, **out)
    except Exception as e:  # noqa: BLE001 — surface any failure as JSON to the caller
        result = device_protocol.write_result(
            False, a.slot, sent, error=f"{type(e).__name__}: {e}", **out
        )
    device_protocol.emit(result)


if __name__ == "__main__":
    main()
