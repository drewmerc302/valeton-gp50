#!/usr/bin/env python3
"""Diff the header (block 0) of two patch-import captures of the SAME .prst written
to different slots -> isolates the target-slot field."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch.decode_import_capture import decode, crc8

# block 0 of each capture (same US Lead .prst; slots differ)
BLK0 = {
    1: "F0 01 0B 01 0D 00 00 01 03 01 01 04 0F 00 00 00 00 00 00 00 00 05 05 05 03 02 00 04 0C 06 05 06 01 06 04 00 00 00 00 00 00 00 00 00 00 00 00 F7",
    99: "F0 04 07 01 0D 00 00 01 03 01 01 04 0F 06 03 00 00 00 00 00 00 05 05 05 03 02 00 04 0C 06 05 06 01 06 04 00 00 00 00 00 00 00 00 00 00 00 00 F7",
}

bufs = {}
for slot, line in BLK0.items():
    buf = decode(line)
    crc, cmd, idx, length = buf[0], buf[1], buf[2], buf[3]
    pl = bytes(buf[4 : 4 + length])
    ok = crc8(buf[1:]) == crc
    bufs[slot] = pl
    print(
        f"slot {slot:>3}: crc={crc:#04x} cmd={cmd:#04x} idx={idx} len={length} crc_ok={ok}"
    )
    print(f"          payload: {pl.hex(' ')}")

a, b = bufs[1], bufs[99]
diffs = [(i, a[i], b[i]) for i in range(min(len(a), len(b))) if a[i] != b[i]]
print(f"\ndiffering payload bytes (slot1 vs slot99): {diffs}")
for i, va, vb in diffs:
    print(f"  payload[{i}]: slot1={va} (0x{va:02x})  slot99={vb} (0x{vb:02x}={vb}d)")
