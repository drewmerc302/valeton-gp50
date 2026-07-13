#!/usr/bin/env python3
import struct
import glob
import os

EXP = "/Users/drewmerc/workspace/valeton/presetExports"
MODULES = ["NR", "PRE", "DST", "AMP", "CAB", "EQ", "MOD", "DLY", "RVB", "N->S"]


def name_of(b):
    return b[0x19:0x30].split(b"\0")[0].decode("latin1", "replace")


def nested(b):
    """find the 390ish container holding 01/02/03/04 group-0x30 records; return {rid:val}."""
    # container starts at the byte after the 0x20-group block; scan for '01 30 04 00'
    idx = b.find(bytes([0x01, 0x30, 0x04, 0x00]))
    if idx < 0:
        return {}, idx
    out = {}
    i = idx
    while i + 4 <= len(b):
        rid, grp = b[i], b[i + 1]
        if grp != 0x30:
            break
        ln = struct.unpack_from("<H", b, i + 2)[0]
        out[rid] = b[i + 4 : i + 4 + ln]
        i += 4 + ln
    return out, idx


def decode(path):
    b = open(path, "rb").read()
    nm = name_of(b)
    rec, _ = nested(b)
    r1 = struct.unpack("<I", rec[1])[0] if 1 in rec and len(rec[1]) == 4 else None
    order = list(rec.get(2, b""))
    models = rec.get(3, b"")
    mods = {}
    if len(models) == 40:
        for pos, m in enumerate(order[:10]):
            mm = MODULES[m] if m < 10 else f"?{m}"
            mods[mm] = models[pos * 4 : pos * 4 + 4]
    return nm, r1, order, mods


# detailed view of the 4 anchor patches
for frag in ["76-VoxUlt", "57-DrewVox", "60-DM CrVox", "00-Great", "05-Pure Clean"]:
    hits = [
        f
        for f in glob.glob(EXP + "/*.prst")
        if frag.lower() in os.path.basename(f).lower()
    ]
    if not hits:
        continue
    nm, r1, order, mods = decode(hits[0])
    print(f"{os.path.basename(hits[0]):24} r1={r1}  order={order}")
    for mm, v in mods.items():
        print(f"     {mm:5} {v.hex(' ')}")
    print()

# scan all 100: which have N->S populated, and the r1 value
print("=== all patches: N->S model record + r1(01/30) ===")
for f in sorted(glob.glob(EXP + "/*.prst")):
    nm, r1, order, mods = decode(f)
    ns = mods.get("N->S", b"").hex(" ")
    print(
        f"  {os.path.basename(f):26} r1={str(r1):5} N->S=[{ns}] AMP=[{mods.get('AMP', b'').hex(' ')}] CAB=[{mods.get('CAB', b'').hex(' ')}]"
    )
