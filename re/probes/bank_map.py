#!/usr/bin/env python3
"""Decode the GP-50 device bank (slot -> name) from a Suite read capture.
Name record = 48-byte SysEx: F0 ck1 ck2 cat_hi cat_lo 00 index 01 03 .. then
nibble-ASCII name at fixed offset b[21], hi-nibble first, null-padded.
Category codes: 06 0A=patches, 04 08=amps, 01 02=cab/IR, 00 05=SnapTone(N->S)."""

import json
import sys
from collections import OrderedDict


def load(path):
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        r["b"] = [int(x, 16) for x in r["hex"].split()]
        yield r


def _run_at(b, off):
    out = []
    i = off
    while i + 1 < len(b) - 1:  # stop before F7
        hi, lo = b[i], b[i + 1]
        c = (hi << 4) | lo
        if hi > 0xF or lo > 0xF or c == 0 or not (32 <= c < 127):
            break
        out.append(c)
        i += 2
    return bytes(out).decode("latin1", "replace")


def decode_name(b):
    # name offset varies per record; take the longest printable nibble-ASCII run
    best = ""
    for off in range(9, len(b) - 4):
        s = _run_at(b, off)
        if len(s) > len(best):
            best = s
    return best


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "work/cap_read.jsonl"
    recs = OrderedDict()
    for r in load(path):
        b = r["b"]
        if r.get("len") != 48 or len(b) < 22:
            continue
        cat = (b[3], b[4])
        idx = b[6]
        nm = decode_name(b)
        key = (cat, idx)
        if key not in recs or (nm and not recs[key]):
            recs[key] = nm
    cats = {}
    for (cat, idx), nm in recs.items():
        cats.setdefault(cat, {})[idx] = nm
    CATNAME = {
        (0x06, 0x0A): "PATCHES",
        (0x04, 0x08): "AMP",
        (0x01, 0x02): "CAB/IR",
        (0x00, 0x05): "SNAPTONE(N->S)",
        (0x01, 0x0B): "?",
    }
    for cat in sorted(cats):
        label = CATNAME.get(cat, "?")
        items = sorted(cats[cat].items())
        named = [(i, n) for i, n in items if n]
        print(
            f"=== cat {cat[0]:02X} {cat[1]:02X}  {label}  ({len(named)}/{len(items)} named) ==="
        )
        for i, n in items:
            if n:
                print(f"  slot {i:3}: {n!r}")
        print()


if __name__ == "__main__":
    main()
