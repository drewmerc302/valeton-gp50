#!/usr/bin/env python3
"""FIRST real patch write: US Lead -> device index 90 (a free 'GP-50' scratch slot).

Safety gate: the outgoing stream must equal Suite's byte-for-byte-validated capture
(slot 0) in EVERY block except block 0, which may differ ONLY in the slot byte. Only
then do we send. Read back separately to confirm.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import patchlib
from patch import device_write
from patch.decode_import_capture import WRITE

TARGET_SLOT = 90  # device index; currently 'GP-50' (empty default)
PORT = "GP-50"


def wire_of(line):
    return [int(x, 16) for x in line.split()]


def buf_of(wire):
    return device_write._nib_decode(wire[1:-1])


def main():
    prst = open(patchlib.patch_file(15), "rb").read()  # US Lead source

    built0 = device_write.build_patch_write_stream(prst, 0)
    cap = [wire_of(l) for l in WRITE]
    built_t = device_write.build_patch_write_stream(prst, TARGET_SLOT)

    # --- validation gate ---
    assert built0 == cap, "builder does NOT reproduce Suite slot-0 capture"
    assert built_t[1:] == cap[1:], "target stream diverges from capture beyond block 0"
    pay0, payt = buf_of(built0[0])[4:], buf_of(built_t[0])[4:]  # payload only
    diffs = [i for i in range(min(len(pay0), len(payt))) if pay0[i] != payt[i]]
    assert diffs == [2], f"block 0 payload differs at {diffs}, expected only [2] (slot)"
    assert payt[2] == TARGET_SLOT, "slot byte not set as expected"
    validated = True
    print(
        f"VALIDATED: {len(built_t)} packets == Suite capture except slot byte = {TARGET_SLOT}"
    )
    print(
        f"target index {TARGET_SLOT} (0x{TARGET_SLOT:02x}); writing 'US Lead' over the 'GP-50' default"
    )

    acks = device_write.send_stream(PORT, built_t, confirm=True, validated=validated)
    print(f"SENT {len(built_t)} packets; device ACKs seen: {acks}/{len(built_t)}")


if __name__ == "__main__":
    main()
