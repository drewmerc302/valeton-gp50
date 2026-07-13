#!/usr/bin/env python3
"""GP-50 .prst (exported patch) decoder. Fixed 552-byte binary.
Layout: 'GP-50' magic, name @0x19, then TLV [id:u8][grp:u8][len:u16le][val].
The model-assignment block is nested record id=3 grp=0x30 (40 bytes = 10x4):
each 4-byte record = [modelIndex:u8][00][00][category:u8].
category -> module: 0=NR/PRE, 3=DST, 7/8=AMP, 0x0a=CAB, 0x0f=N->S(SnapTone),
0x04=MOD, 0x0b=DLY, 0x0c=RVB, 0x01=EQ/PRE."""

import struct
import glob
import os

EXP = "/Users/drewmerc/workspace/valeton/presetExports"
CAT = {
    0x03: "DST",
    0x07: "AMP",
    0x08: "AMP",
    0x0A: "CAB",
    0x04: "MOD",
    0x0B: "DLY",
    0x0C: "RVB",
    0x0F: "N->S",
}


def name_of(b):
    return b[0x19:0x30].split(b"\0")[0].decode("latin1", "replace")


def models_block(b):
    """return (offset, list of (idx, cat)) for the 10 model records."""
    key = bytes([0x03, 0x30, 0x28, 0x00])  # id=3 grp=0x30 len=40
    i = b.find(key)
    if i < 0:
        return -1, []
    val = b[i + 4 : i + 4 + 40]
    recs = [(val[k * 4], val[k * 4 + 3]) for k in range(10)]
    return i + 4, recs


def snaptone_slot(b):
    _, recs = models_block(b)
    for idx, cat in recs:
        if cat == 0x0F:
            return idx
    return None


if __name__ == "__main__":
    import sys

    files = sorted(glob.glob(EXP + "/*.prst"))
    # checksum hunt: which byte ranges vary; is the last record a checksum?
    print("=== per-patch model assignments (idx@category) ===")
    ns_used = {}
    for f in files:
        b = open(f, "rb").read()
        off, recs = models_block(b)
        parts = []
        for idx, cat in recs:
            mod = CAT.get(cat)
            if mod in ("N->S", "AMP", "CAB"):
                parts.append(f"{mod}={idx}")
        ns = snaptone_slot(b)
        if ns is not None:
            ns_used.setdefault(ns, []).append(os.path.basename(f))
        print(f"  {os.path.basename(f):26} {' '.join(parts)}")
    print("\n=== N->S SnapTone slots referenced by patches ===")
    for slot in sorted(ns_used):
        print(f"  slot {slot:3}: {len(ns_used[slot])} patches  e.g. {ns_used[slot][0]}")
    # trailer / checksum check: compare tail 12 bytes of two patches w/ same body len
    print("\n=== tails (last 16 bytes) of a few patches ===")
    for f in files[:6]:
        b = open(f, "rb").read()
        print(f"  {os.path.basename(f):26} {b[-16:].hex(' ')}")
