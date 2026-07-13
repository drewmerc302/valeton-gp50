#!/usr/bin/env python3
"""Reconstruct the GP-50 patch-write stream from a .prst + target slot, and VALIDATE
it reproduces Suite's captured host->device bytes exactly.

Decoded format (from two Suite patch-import captures of US Lead -> slots 1 and 99):
  device_payload = [0x11, 0x4F, slot, 0x00, 0x00, 0x00] + prst[0x15+4:]
    (the 6-byte header replaces the .prst body's leading FF FF FF FF sentinel;
     byte[2] = target slot, 0-based)
  stream: cmd 0x1D, 19-byte blocks, index 0..N, nibble+CRC-8/0x07, wrapped F0..F7.
This module only builds/validates. Sending stays gated in device_write.send_stream."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import patchlib
from patch import device_write
from patch.decode_import_capture import WRITE, decode
from patch.compare_slots import BLK0

build_patch_write_stream = device_write.build_patch_write_stream  # canonical builder


def wire_of(line: str) -> list:
    return [int(x, 16) for x in line.split()]


def main():
    prst = open(patchlib.patch_file(15), "rb").read()  # US Lead source
    print(f"US Lead .prst: {len(prst)} bytes")

    # where do the header bytes 0x11 0x4F come from? peek at the .prst header
    print(f".prst[0x0E:0x1A] = {prst[0x0E:0x1A].hex(' ')}")

    # --- validate slot 1: rebuild == captured, packet by packet ---
    # Suite's "slot 1" import sent slot byte 0x00 -> the slot byte is 0-based.
    built = build_patch_write_stream(prst, 0)
    cap = [wire_of(l) for l in WRITE]
    print(f"\nslot 1 (byte 0): built {len(built)} packets, captured {len(cap)}")
    ok = sum(1 for b, c in zip(built, cap) if b == c)
    print(f"  byte-for-byte match: {ok}/{len(cap)}")
    if ok != len(cap):
        for i, (b, c) in enumerate(zip(built, cap)):
            if b != c:
                print(
                    f"  MISMATCH block {i}:\n    built={bytes(b).hex(' ')}\n    capt ={bytes(c).hex(' ')}"
                )
                break

    # --- validate slot 99: block 0 header ---
    built99_blk0 = build_patch_write_stream(prst, 99)[0]
    cap99_blk0 = wire_of(BLK0[99])
    print(f"\nslot 99 block 0 match: {built99_blk0 == cap99_blk0}")

    print(
        "\nRESULT: patch-write reconstruction is",
        "VALIDATED ✅"
        if ok == len(cap) and built99_blk0 == cap99_blk0
        else "NOT matching ❌",
    )


if __name__ == "__main__":
    main()
