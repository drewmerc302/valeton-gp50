#!/usr/bin/env python
"""
Brute-force the GP-50 upload checksum: bytes[1],[2] of each 48-byte write packet
  F0 [ck1] [ck2] 09 02 [sec] [blk] 01 03 [payload...] F7
Tries many (byte-range x algorithm x output-mapping) combos and reports match counts.

Usage: python brute_checksum.py ~/Desktop/valeton_import_capture.txt
"""

import re
import sys
import zlib
from functools import reduce

HEX = re.compile(r"\b[0-9A-Fa-f]{2}\b")


def packets(path):
    out = []
    for line in open(path, errors="replace"):
        if "to gp-50" not in line.lower():
            continue
        b = [int(t, 16) for t in HEX.findall(line)]
        if 0xF0 not in b:
            continue
        b = b[b.index(0xF0) :]
        if len(b) == 48 and b[3] == 0x09 and b[4] == 0x02:
            out.append(b)
    return out


def nibdec(p):
    return bytes(
        ((p[i] & 0xF) << 4) | (p[i + 1] & 0xF) for i in range(0, len(p) - 1, 2)
    )


# ---- output mappings: value -> (ck1, ck2), both must be 7-bit ----
def maps(v):
    v &= 0xFFFF
    return {
        "14:hi7,lo7": ((v >> 7) & 0x7F, v & 0x7F),
        "14:lo7,hi7": (v & 0x7F, (v >> 7) & 0x7F),
        "byte:hi,lo&7f": ((v >> 8) & 0x7F, v & 0x7F),
        "byte:lo,hi&7f": (v & 0x7F, (v >> 8) & 0x7F),
    }


# ---- algorithms: bytes -> 16-bit value ----
def sum16(d):
    return sum(d) & 0xFFFF


def xor8(d):
    return reduce(lambda a, c: a ^ c, d, 0)


def fletcher16(d, mod=255):
    s1 = s2 = 0
    for c in d:
        s1 = (s1 + c) % mod
        s2 = (s2 + s1) % mod
    return (s2 << 8) | s1


def crc16(d, poly, init, refin, refout):
    crc = init
    for c in d:
        if refin:
            c = int(f"{c:08b}"[::-1], 2)
        crc ^= c << 8
        for _ in range(8):
            crc = (
                ((crc << 1) ^ poly) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
            )
    if refout:
        crc = int(f"{crc:016b}"[::-1], 2)
    return crc


def roland_pair(d):
    # Roland-style: single 7-bit (128 - sum) & 7F; pair with xor for 2nd byte
    s = (128 - (sum(d) & 0x7F)) & 0x7F
    return (s << 8) | (xor8(d) & 0x7F)


ALGOS = {
    "sum": sum16,
    "xor(with 0)": lambda d: xor8(d),
    "fletcher16/255": lambda d: fletcher16(d, 255),
    "fletcher16/127": lambda d: fletcher16(d, 127),
    "fletcher16/128": lambda d: fletcher16(d, 128),
    "adler32&ffff": lambda d: zlib.adler32(bytes(x & 0xFF for x in d)) & 0xFFFF,
    "crc16-ccitt": lambda d: crc16(d, 0x1021, 0x0000, False, False),
    "crc16-ccitt-ffff": lambda d: crc16(d, 0x1021, 0xFFFF, False, False),
    "crc16-ibm": lambda d: crc16(d, 0x8005, 0x0000, False, False),
    "crc16-modbus": lambda d: crc16(d, 0x8005, 0xFFFF, True, True),
    "crc16-xmodem": lambda d: crc16(d, 0x1021, 0x0000, False, False),
    "roland-pair": roland_pair,
}


def ranges(p, prevp):
    return {
        "payload[9:-1]": p[9:-1],
        "decoded(payload)": list(nibdec(p[9:-1])),
        "[5:-1]": p[5:-1],
        "[6:-1]": p[6:-1],
        "[3:-1]": p[3:-1],
        "sec,blk+decoded": [p[5], p[6]] + list(nibdec(p[9:-1])),
        "prev.payload[9:-1]": prevp[9:-1] if prevp else [],
        "prev.decoded": list(nibdec(prevp[9:-1])) if prevp else [],
    }


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
    )
    pk = packets(path)
    n = len(pk)
    targets = [(p[1], p[2]) for p in pk]
    print(f"{n} upload packets. block0 ck = {targets[0][0]:02X} {targets[0][1]:02X}")

    results = []
    rnames = list(ranges(pk[0], None).keys())
    for rn in rnames:
        for an, af in ALGOS.items():
            for mn in ("14:hi7,lo7", "14:lo7,hi7", "byte:hi,lo&7f", "byte:lo,hi&7f"):
                hits = 0
                for i, p in enumerate(pk):
                    prev = pk[i - 1] if i > 0 else None
                    data = ranges(p, prev)[rn]
                    try:
                        v = af(data)
                    except Exception:
                        v = -1
                    if maps(v)[mn] == targets[i]:
                        hits += 1
                if hits > n * 0.5:
                    results.append((hits, rn, an, mn))

    results.sort(reverse=True)
    print("\n=== hypotheses matching >50% of packets ===")
    if not results:
        print("  NONE > 50%. Top 12 overall:")
        # recompute best without threshold
        allr = []
        for rn in rnames:
            for an, af in ALGOS.items():
                for mn in (
                    "14:hi7,lo7",
                    "14:lo7,hi7",
                    "byte:hi,lo&7f",
                    "byte:lo,hi&7f",
                ):
                    hits = 0
                    for i, p in enumerate(pk):
                        prev = pk[i - 1] if i > 0 else None
                        data = ranges(p, prev)[rn]
                        try:
                            v = af(data)
                        except Exception:
                            v = -1
                        if maps(v)[mn] == targets[i]:
                            hits += 1
                    allr.append((hits, rn, an, mn))
        allr.sort(reverse=True)
        for hits, rn, an, mn in allr[:12]:
            print(f"  {hits:3d}/{n}  range={rn:20s} algo={an:18s} map={mn}")
    else:
        for hits, rn, an, mn in results[:20]:
            print(f"  {hits:3d}/{n}  range={rn:20s} algo={an:18s} map={mn}")


if __name__ == "__main__":
    main()
