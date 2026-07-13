#!/usr/bin/env python
"""
Structural decoder for a GP-50 SysEx capture (.jsonl from midi_sniff.py).
Read-only analysis: group by length, find constant vs varying byte positions,
extract ASCII (names), and segment by session. No device interaction.

Usage: python decode_sniff.py work/cap_read.jsonl
"""

import json
import sys
from collections import Counter, defaultdict


def load(path):
    rows = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        r["bytes"] = [int(b, 16) for b in r["hex"].split()]
        rows.append(r)
    return rows


def ascii_run(b):
    out = []
    for x in b:
        out.append(chr(x) if 32 <= x < 127 else ".")
    return "".join(out)


def col_analysis(msgs):
    """Per-position: constant value or '..' if it varies."""
    n = min(len(m) for m in msgs)
    cols = []
    for i in range(n):
        vals = {m[i] for m in msgs}
        cols.append(f"{next(iter(vals)):02X}" if len(vals) == 1 else "..")
    return cols


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "work/cap_read.jsonl"
    rows = load(path)
    print(f"loaded {len(rows)} messages from {path}")

    # Sessions
    sess = defaultdict(list)
    for r in rows:
        sess[r.get("session", 0)].append(r)
    print(f"\nsessions: {len(sess)}")
    for s, rs in sorted(sess.items()):
        lens = Counter(r["len"] for r in rs)
        span = f"{rs[0]['t']:.1f}-{rs[-1]['t']:.1f}s"
        print(f"  session {s}: {len(rs)} msgs  {span}  lengths={dict(lens)}")

    # Group by length
    by_len = defaultdict(list)
    for r in rows:
        by_len[r["len"]].append(r["bytes"])
    print("\n=== per-length structure (constant bytes shown, '..' varies) ===")
    for L in sorted(by_len):
        msgs = by_len[L]
        cols = col_analysis(msgs)
        print(f"\nlen {L}  (x{len(msgs)})")
        print("  template:", " ".join(cols))
        # show 4 distinct examples
        seen = set()
        shown = 0
        for m in msgs:
            key = tuple(m)
            if key in seen:
                continue
            seen.add(key)
            hexs = " ".join(f"{x:02X}" for x in m)
            print(f"    {hexs}")
            print(f"      ascii: {ascii_run(m)}")
            shown += 1
            if shown >= 4:
                break

    # ASCII strings across everything (names)
    print("\n=== ASCII runs >=3 chars (candidate names) ===")
    found = Counter()
    for r in rows:
        b = r["bytes"]
        cur = ""
        for x in b:
            if 32 <= x < 127:
                cur += chr(x)
            else:
                if len(cur) >= 3:
                    found[cur] += 1
                cur = ""
        if len(cur) >= 3:
            found[cur] += 1
    for s, c in found.most_common(40):
        print(f"  {c:4d}x  {s!r}")
    if not found:
        print("  (none — names are not sent as raw ASCII in this capture)")


if __name__ == "__main__":
    main()
