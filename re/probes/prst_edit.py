#!/usr/bin/env python3
"""Edit a GP-50 .prst: reassign the N->S SnapTone slot (feature 5) or the
CAB IR/model index (feature 6). Changes exactly one byte in the model block.
The SnapTone/IR must already be loaded on the device at the target slot -
exported .prst files do NOT carry third-party SnapTone/IR binaries."""

import struct
import sys
import os

CATS = {0x0F: "N->S", 0x0A: "CAB", 0x07: "AMP", 0x08: "AMP"}
CRC_OFF = 0x14  # byte 0x14 = CRC-8/0x07 over body[0x15:]


def crc8(data, init=0):
    c = init
    for byte in data:
        c ^= byte
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def refix_crc(b):
    nb = bytearray(b)
    nb[CRC_OFF] = crc8(nb[CRC_OFF + 1 :])
    return bytes(nb)


def model_block_off(b):
    i = b.find(bytes([0x03, 0x30, 0x28, 0x00]))
    if i < 0:
        raise ValueError("model block (03 30 28 00) not found")
    return i + 4


def records(b):
    off = model_block_off(b)
    return off, [(off + k * 4, b[off + k * 4], b[off + k * 4 + 3]) for k in range(10)]


def get(b, category):
    off, recs = records(b)
    for roff, idx, cat in recs:
        if cat == category:
            return roff, idx
    return None, None


def set_index(b, category, new_idx):
    roff, cur = get(b, category)
    if roff is None:
        raise ValueError(f"no record with category {category:#x} in this patch")
    nb = bytearray(b)
    nb[roff] = new_idx
    return refix_crc(nb), cur


def show(path):
    b = open(path, "rb").read()
    off, recs = records(b)
    print(f"{os.path.basename(path)}  ({len(b)} bytes)")
    for roff, idx, cat in recs:
        tag = CATS.get(cat, f"cat{cat:#x}")
        star = (
            "  <-- SnapTone" if cat == 0x0F else ("  <-- IR/cab" if cat == 0x0A else "")
        )
        print(f"   @0x{roff:03x} {tag:5} index={idx}{star}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "show":
        show(a[1])
        sys.exit()
    # usage: prst_edit.py snaptone <in.prst> <slot> <out.prst>
    #        prst_edit.py ir       <in.prst> <idx>  <out.prst>
    cmd, inp, val, outp = a[0], a[1], int(a[2]), a[3]
    cat = 0x0F if cmd == "snaptone" else 0x0A
    b = open(inp, "rb").read()
    nb, cur = set_index(b, cat, val)
    open(outp, "wb").write(nb)
    ndiff = sum(1 for x, y in zip(b, nb) if x != y)
    print(f"{cmd}: category {cat:#x} index {cur} -> {val}")
    print(f"wrote {outp}  ({ndiff} byte(s) changed)")
