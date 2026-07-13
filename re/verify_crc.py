#!/usr/bin/env python
"""Verify the recovered checksum: CRC-8/0x07, init=0, over the full nibble-DECODED
message buffer with byte[0] (the checksum slot) set to 0. Per getMidiMessage()."""

import re
import sys

HEX = re.compile(r"\b[0-9A-Fa-f]{2}\b")
TBL = []
for i in range(256):
    c = i
    for _ in range(8):
        c = ((c << 1) ^ 0x07) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    TBL.append(c)


def crc8(buf, init=0):
    c = init
    for b in buf:
        c = TBL[(c ^ (b & 0xFF)) & 0xFF]
    return c


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
    )
    ok = tot = 0
    fails = []
    for line in open(path, errors="replace"):
        low = line.lower()
        if "to gp-50" not in low:
            continue
        b = [int(t, 16) for t in HEX.findall(line)]
        if 0xF0 not in b:
            continue
        b = b[b.index(0xF0) :]
        if b[-1] != 0xF7:
            continue
        mid = b[1:-1]  # between F0 and F7 (nibble stream)
        if len(mid) % 2:
            continue
        dec = [
            ((mid[i] & 0xF) << 4) | (mid[i + 1] & 0xF) for i in range(0, len(mid), 2)
        ]
        wire_crc = dec[0]
        buf = dec[:]
        buf[0] = 0
        got = crc8(buf, 0)
        tot += 1
        if got == wire_crc:
            ok += 1
        else:
            if len(fails) < 5:
                fails.append((wire_crc, got, bytes(dec[:6]).hex(" ")))
    print(
        f"CRC-8/0x07 init=0 over full decoded buf (crc-byte zeroed): {ok}/{tot} match"
    )
    for wc, gc, head in fails:
        print(f"  MISS wire={wc:02X} got={gc:02X} head={head}")


if __name__ == "__main__":
    main()
