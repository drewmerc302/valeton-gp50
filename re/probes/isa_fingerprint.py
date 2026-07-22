#!/usr/bin/env python3
"""Statistical ISA fingerprint: count characteristic instruction encodings per region."""

import os
import sys

# ARM Thumb / Thumb-2 characteristic encodings (little-endian byte pairs)
THUMB = {
    "bx lr      (70 47)": b"\x70\x47",
    "push r4-7,lr(f0 b5)": b"\xf0\xb5",
    "pop  r4-7,pc(f0 bd)": b"\xf0\xbd",
    "push.w      (2d e9)": b"\x2d\xe9",
    "pop.w       (bd e8)": b"\xbd\xe8",
    "push lr     (00 b5)": b"\x00\xb5",
    "pop  pc     (00 bd)": b"\x00\xbd",
}
# ARM (A32) little-endian: bx lr = e1 2f ff 1e -> LE bytes 1e ff 2f e1
ARM32 = {
    "bx lr   (1e ff 2f e1)": b"\x1e\xff\x2f\xe1",
    "push lr (04 e0 2d e5)": b"\x04\xe0\x2d\xe5",
}
# MIPS / other
MISC = {
    "jr ra  MIPS-LE(08 00 e0 03)": b"\x08\x00\xe0\x03",
    "jr ra  MIPS-BE(03 e0 00 08)": b"\x03\xe0\x00\x08",
}


def count(hay, needle):
    n, i = 0, hay.find(needle)
    while i != -1:
        n += 1
        i = hay.find(needle, i + 1)
    return n


if __name__ == "__main__":
    d = sys.argv[1]
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".bin"):
            continue
        blob = open(os.path.join(d, fn), "rb").read()
        kb = len(blob) / 1024
        print(f"--- {fn} ({len(blob)} bytes) ---")
        for label, group in (("THUMB", THUMB), ("ARM32", ARM32), ("MISC", MISC)):
            parts = []
            for name, pat in group.items():
                c = count(blob, pat)
                if c:
                    parts.append(f"{name}={c} ({c / kb:.2f}/KB)")
            if parts:
                print(f"  {label}: " + "; ".join(parts))
        print()
