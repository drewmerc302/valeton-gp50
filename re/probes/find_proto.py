#!/usr/bin/env python3
"""Locate protocol artifacts (CRC-8/0x07 table, command opcodes) in extracted HTFW regions."""

import os
import sys


def crc8_table(poly=0x07):
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = ((c << 1) ^ poly) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
        t.append(c)
    return bytes(t)


def findall(hay, needle):
    out, i = [], hay.find(needle)
    while i != -1:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


TABLE = crc8_table()

# Protocol markers from re/DEVICE_WRITE.md
PATTERNS = {
    "crc8_0x07_table(full256)": TABLE,
    "crc8_table_first32": TABLE[:32],
    "hdr_11_4F(write)": bytes([0x11, 0x4F]),
    "hdr_11_43(select)": bytes([0x11, 0x43]),
    "hdr_11_47(chg_effect)": bytes([0x11, 0x47]),
    "hdr_11_48(chg_param)": bytes([0x11, 0x48]),
    "hdr_11_49(toggle)": bytes([0x11, 0x49]),
    "read_bank_0x41seq": bytes([0x09, 0x01, 0x00, 0x02, 0x12, 0x41]),
}

if __name__ == "__main__":
    d = sys.argv[1]
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".bin"):
            continue
        blob = open(os.path.join(d, fn), "rb").read()
        hits = {}
        for name, pat in PATTERNS.items():
            h = findall(blob, pat)
            if h:
                hits[name] = h
        if hits:
            print(f"--- {fn} ({len(blob)} bytes) ---")
            for name, h in hits.items():
                show = ", ".join(f"0x{x:x}" for x in h[:12])
                more = f" ...(+{len(h) - 12})" if len(h) > 12 else ""
                print(f"    {name:28} x{len(h):<5} @ {show}{more}")
