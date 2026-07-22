#!/usr/bin/env python3
"""Parse the HTFW firmware container used by Valeton GP-5 / GP-50 / GP-150."""

import struct
import sys
import math
import collections


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def parse(path):
    d = open(path, "rb").read()
    assert d[:4] == b"HTFW", f"not HTFW: {d[:4]!r}"

    magic = d[:4]
    f04 = struct.unpack_from("<I", d, 4)[0]
    total_size = struct.unpack_from("<I", d, 8)[0]
    model = d[0x0C:0x1C].split(b"\0")[0].decode()
    f1c = struct.unpack_from("<H", d, 0x1C)[0]
    ver_minor = d[0x1F]
    f20 = struct.unpack_from("<I", d, 0x20)[0]
    payload_total = struct.unpack_from("<I", d, 0x24)[0]

    print(f"=== {path.split('/')[-1]} ===")
    print(f"  magic        {magic!r}")
    print(f"  f@0x04       0x{f04:08x}  ({f04})")
    print(
        f"  size@0x08    0x{total_size:08x}  ({total_size})  file={len(d)}  match={total_size == len(d)}"
    )
    print(f"  model        {model!r}")
    print(f"  f@0x1C       0x{f1c:04x}   ver_minor@0x1F = {ver_minor}")
    print(f"  f@0x20       0x{f20:08x}")
    print(f"  payload@0x24 0x{payload_total:08x}  ({payload_total})")

    # version string region
    vs = d[0x90:0xA0]
    print(f"  ver string   {vs[:8]!r}")

    # TOC records: 16 bytes each starting at 0x30, until FFFFFFFF sentinel
    print("  --- TOC ---")
    recs = []
    off = 0x38
    while off + 16 <= len(d):
        rec = d[off : off + 16]
        if rec[:4] == b"\xff\xff\xff\xff":
            print(f"  sentinel at 0x{off:02x}")
            break
        chk, zero, rid = struct.unpack_from("<HBB", rec, 0)
        addr, roff, rlen = struct.unpack_from("<III", rec, 4)
        recs.append(
            dict(
                hdr_off=off, chk=chk, zero=zero, rid=rid, addr=addr, off=roff, len=rlen
            )
        )
        off += 16

    payload_base = len(d) - payload_total
    print(
        f"  payload_base = file_size - payload_total = 0x{payload_base:x} ({payload_base})"
    )

    cum = 0
    for r in recs:
        contiguous = r["off"] == cum
        cum = r["off"] + r["len"]
        abs_start = payload_base + r["off"]
        abs_end = abs_start + r["len"]
        in_file = abs_end <= len(d)
        blob = d[abs_start:abs_end] if in_file else b""
        ent = entropy(blob[:200000])
        print(
            f"  id=0x{r['rid']:02x} '{chr(r['rid'])}'  addr=0x{r['addr']:08x}  "
            f"off=0x{r['off']:08x} len=0x{r['len']:08x} ({r['len']:>9})  "
            f"abs=0x{abs_start:08x}-0x{abs_end:08x}  contig={contiguous} fits={in_file}  "
            f"H={ent:.2f}  chk=0x{r['chk']:04x}"
        )
    print(
        f"  cumulative end = 0x{cum:x} ({cum})  vs payload_total {payload_total}  "
        f"match={cum == payload_total}"
    )
    print()
    return d, recs, payload_base


if __name__ == "__main__":
    for p in sys.argv[1:]:
        parse(p)
