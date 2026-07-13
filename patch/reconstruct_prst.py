#!/usr/bin/env python3
"""Rebuild a full 552-byte .prst from a device read (name via 0x40 + body via 0x41).

Layout decoded from the 0x41 read + 100/100 round-trip against presetExports:
  prst[0x00:0x14] = constant "GP-50" header      (HEADER below)
  prst[0x14]      = file CRC (CRC-8/0x07 over prst[0x15:])
  prst[0x15:0x19] = FF FF FF FF sentinel
  prst[0x19:0x29] = 16-byte patch name           (from the 0x40 name read)
  prst[0x29:]     = 511-byte body                (== the 0x41 body read)
No device I/O here; run as a script to re-verify the round-trip."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import patchlib

HEADER = bytes.fromhex("47502d3530000000000000000000000000000100")  # prst[0x00:0x14]
SENTINEL = b"\xff\xff\xff\xff"


def rebuild(name: str, body: bytes) -> bytes:
    """name = 0x40 read; body = 0x41 read (prst[0x29:], 511 bytes). -> full .prst."""
    nm = name.encode("latin1")[:16].ljust(16, b"\0")  # name region 0x19:0x29
    out = bytearray(HEADER + b"\x00" + SENTINEL + nm + body)
    out[patchlib.CRC_OFF] = patchlib._crc8(bytes(out[patchlib.CRC_OFF + 1 :]))
    return bytes(out)


def _verify():
    import glob

    exports = glob.glob(os.path.join(patchlib.PROJECT_ROOT, "presetExports", "*.prst"))
    prsts = {os.path.basename(p): open(p, "rb").read() for p in exports}
    prsts = {k: v for k, v in prsts.items() if len(v) == 552}
    assert all(v[:0x14] == HEADER for v in prsts.values()), "header not constant"
    assert all(v[0x15:0x19] == SENTINEL for v in prsts.values()), (
        "sentinel not constant"
    )
    ok = sum(
        rebuild(patchlib._patch_name(v, k), v[0x29:]) == v for k, v in prsts.items()
    )
    print(f"rebuilt == original: {ok}/{len(prsts)} patches")


if __name__ == "__main__":
    _verify()
