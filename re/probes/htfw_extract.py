#!/usr/bin/env python3
"""Extract HTFW regions to disk and fingerprint each one."""

import os
import re
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


def regions(d):
    payload_total = struct.unpack_from("<I", d, 0x24)[0]
    base = len(d) - payload_total
    out = []
    off = 0x38
    while True:
        rec = d[off : off + 16]
        if rec[:4] == b"\xff\xff\xff\xff":
            break
        rid = rec[3]
        addr, roff, rlen = struct.unpack_from("<III", rec, 4)
        start = base + roff
        out.append((rid, addr, d[start : start + rlen], start))
        off += 16
    return out


def fingerprint(rid, addr, blob, start, outdir, tag):
    name = f"{tag}_{chr(rid)}_{addr:08x}.bin"
    path = os.path.join(outdir, name)
    open(path, "wb").write(blob)

    print(
        f"  region '{chr(rid)}' addr=0x{addr:08x} len={len(blob):>9} H={entropy(blob[:400000]):.2f}"
    )
    print(f"    first32 {blob[:32].hex(' ')}")

    # ARM Cortex-M vector table heuristic: initial SP then reset vector (thumb, odd)
    if len(blob) >= 8:
        sp, reset = struct.unpack_from("<II", blob, 0)
        cm = (0x20000000 <= sp <= 0x20200000 or 0x1000_0000 <= sp <= 0x3000_0000) and (
            reset & 1
        )
        print(f"    cortex-m? sp=0x{sp:08x} reset=0x{reset:08x} -> {cm}")

    # printable strings
    strs = re.findall(rb"[\x20-\x7e]{6,}", blob)
    print(f"    strings: {len(strs)}")
    for s in strs[:8]:
        print(f"      {s[:70].decode('ascii', 'replace')}")
    return path


if __name__ == "__main__":
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    for p in sys.argv[2:]:
        d = open(p, "rb").read()
        model = d[0x0C:0x1C].split(b"\0")[0].decode()
        tag = model.replace("-", "")
        print(f"=== {model} ===")
        for rid, addr, blob, start in regions(d):
            fingerprint(rid, addr, blob, start, outdir, tag)
        print()
