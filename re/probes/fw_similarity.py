#!/usr/bin/env python3
"""Measure byte-level code sharing between GP-5 and GP-50 region 'b' (MVsilicon app core).

No disassembler needed: find long common byte runs, then report how much of the
protocol neighbourhood (anchored on the CRC-8/0x07 table) is byte-identical.
"""

import sys

K = 32  # index window
MINRUN = 48  # minimum reported common run
STRIDE = 4  # index stride on the reference


def crc8_table(poly=0x07):
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = ((c << 1) ^ poly) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
        t.append(c)
    return bytes(t)


def common_runs(a, b):
    """Yield (a_off, b_off, length) for maximal common runs >= MINRUN."""
    idx = {}
    for i in range(0, len(b) - K, STRIDE):
        idx.setdefault(hash(b[i : i + K]), []).append(i)

    runs = []
    i = 0
    while i < len(a) - K:
        cands = idx.get(hash(a[i : i + K]))
        if not cands:
            i += 1
            continue
        best = None
        for j in cands:
            if a[i : i + K] != b[j : j + K]:
                continue
            # extend right
            e = K
            while i + e < len(a) and j + e < len(b) and a[i + e] == b[j + e]:
                e += 1
            # extend left
            s = 0
            while i - s > 0 and j - s > 0 and a[i - s - 1] == b[j - s - 1]:
                s += 1
            length = e + s
            if best is None or length > best[2]:
                best = (i - s, j - s, length)
        if best and best[2] >= MINRUN:
            runs.append(best)
            i = best[0] + best[2]
        else:
            i += 1
    return runs


def coverage(runs, total, lo=None, hi=None):
    """Bytes of `a` covered by runs, optionally restricted to [lo,hi)."""
    marks = bytearray(total)
    for ao, bo, ln in runs:
        for x in range(ao, min(ao + ln, total)):
            marks[x] = 1
    if lo is None:
        return sum(marks), total
    return sum(marks[lo:hi]), hi - lo


if __name__ == "__main__":
    pa, pb = sys.argv[1], sys.argv[2]
    a = open(pa, "rb").read()
    b = open(pb, "rb").read()
    T = crc8_table()
    ca, cb = a.find(T), b.find(T)
    print(f"A = {pa.split('/')[-1]}  {len(a)} bytes, crc8 table @0x{ca:x}")
    print(f"B = {pb.split('/')[-1]}  {len(b)} bytes, crc8 table @0x{cb:x}")

    runs = common_runs(a, b)
    tot, n = coverage(runs, len(a))
    print(f"\ncommon runs >= {MINRUN}B: {len(runs)}")
    print(f"global coverage of A: {tot}/{n} = {100 * tot / n:.1f}%")

    for win in (0x2000, 0x8000, 0x20000):
        lo, hi = max(0, ca - win), min(len(a), ca + win)
        cov, span = coverage(runs, len(a), lo, hi)
        print(
            f"protocol nbhd +/-0x{win:<6x} [0x{lo:x}-0x{hi:x}]: "
            f"{cov}/{span} = {100 * cov / span:.1f}% identical"
        )

    near = [r for r in runs if abs(r[0] - ca) < 0x8000]
    near.sort(key=lambda r: -r[2])
    print("\nlongest common runs near the CRC table:")
    for ao, bo, ln in near[:12]:
        print(
            f"  A@0x{ao:06x}  B@0x{bo:06x}  len={ln:>6}  (delta {ao - ca:+d} from crc tbl)"
        )

    biggest = sorted(runs, key=lambda r: -r[2])[:10]
    print("\nlongest common runs overall:")
    for ao, bo, ln in biggest:
        print(f"  A@0x{ao:06x}  B@0x{bo:06x}  len={ln:>6}")
