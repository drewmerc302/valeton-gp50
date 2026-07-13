#!/usr/bin/env python
"""
Decode GP-50 name records from a SysEx capture.

Finding: text fields are nibble-encoded — each ASCII byte is sent as two SysEx
bytes (high nibble, then low nibble), so "Great" = 04 07 07 02 06 05 06 01 07 04.
This decodes those back and lists the pedal's records (presets / SnapTones / IRs),
using the per-record index byte.

Usage: python decode_names.py work/cap_read.jsonl
"""

import json
import sys
from collections import OrderedDict


def load(path):
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        r["bytes"] = [int(b, 16) for b in r["hex"].split()]
        yield r


def nibble_decode(body):
    """Pair (hi, lo) nibbles into bytes; return the byte list."""
    out = []
    for i in range(0, len(body) - 1, 2):
        hi, lo = body[i], body[i + 1]
        if hi > 0x0F or lo > 0x0F:
            out.append(None)  # not a nibble pair here
        else:
            out.append((hi << 4) | lo)
    return out


def ascii_runs(byts, minlen=3):
    runs, cur = [], ""
    for b in byts:
        if b is not None and 32 <= b < 127:
            cur += chr(b)
        else:
            if len(cur) >= minlen:
                runs.append(cur)
            cur = ""
    if len(cur) >= minlen:
        runs.append(cur)
    return runs


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "work/cap_read.jsonl"
    rows = list(load(path))

    # Group name records by (category, index). Category = bytes[3],[4]; index = byte[6].
    records = OrderedDict()
    for r in rows:
        b = r["bytes"]
        if r["len"] != 48 or len(b) < 10:
            continue
        cat = (b[3], b[4])
        idx = b[6]
        # Name is nibble-encoded somewhere in the body; try both nibble alignments
        # and the whole payload, take the longest printable run.
        body = b[1:-1]  # drop F0 / F7
        names = []
        for start in (0, 1):
            names += ascii_runs(nibble_decode(body[start:]))
        name = max(names, key=len) if names else ""
        key = (cat, idx)
        # keep the record with a decoded name if we have duplicates
        if key not in records or (name and not records[key]):
            records[key] = name

    # Report grouped by category.
    cats = {}
    for (cat, idx), name in records.items():
        cats.setdefault(cat, []).append((idx, name))
    print(f"decoded {len(records)} name records across {len(cats)} categories\n")
    for cat, items in cats.items():
        items.sort()
        print(f"=== category {cat[0]:02X} {cat[1]:02X}  ({len(items)} records) ===")
        for idx, name in items:
            print(f"  [{idx:3d}]  {name!r}")
        print()


if __name__ == "__main__":
    main()
