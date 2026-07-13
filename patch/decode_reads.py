#!/usr/bin/env python3
"""Decode the GP-50 name-READ request/reply protocol from a MIDI Monitor capture.
Wire format (cracked earlier): F0 + nibble-expand(BUF, hi-first) + F7, where
BUF = [crc, cmd, index, length, *data], crc = CRC-8/0x07 over BUF with crc byte=0."""

import re
import sys


def crc8(data, init=0):
    c = init
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def nib_decode(mid):
    """mid = list of wire bytes between F0 and F7 -> BUF bytes (hi,lo pairs)."""
    return [(mid[i] << 4) | mid[i + 1] for i in range(0, len(mid) - 1, 2)]


def frames(path):
    for ln in open(path):
        if "GP-50" not in ln or "F7" not in ln:
            continue
        direction = (
            "H>D" if "To GP-50" in ln else ("D>H" if "From GP-50" in ln else "?")
        )
        m = re.search(r"F0((?:\s+[0-9A-Fa-f]{2})+)\s+F7", ln)
        if not m:
            continue
        wire = [int(x, 16) for x in m.group(1).split()]
        yield direction, wire


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_bank_read.txt"
    )
    rows = list(frames(path))
    print(f"{len(rows)} frames\n=== H>D requests (nibble-decoded BUF + CRC check) ===")
    for i, (d, wire) in enumerate(rows):
        if d != "H>D":
            continue
        buf = nib_decode(wire)
        crc, cmd = buf[0], buf[1] if len(buf) > 1 else None
        chk = crc8([0] + buf[1:])
        ok = "OK" if chk == crc else f"BAD(want {chk:#04x})"
        # peek next reply
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        rep = ""
        if nxt and nxt[0] == "D>H":
            rb = nib_decode(nxt[1])
            rep = f"-> reply BUF[{len(rb)}] head={' '.join(f'{x:02x}' for x in rb[:6])}"
        print(
            f"  cmd={cmd:#04x} idx={buf[2]:#04x} len={buf[3]} data={[hex(x) for x in buf[4:]]} crc {ok}  {rep}"
        )


if __name__ == "__main__":
    main()
