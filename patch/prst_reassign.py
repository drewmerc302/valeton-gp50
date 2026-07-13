#!/usr/bin/env python3
"""By-identity SnapTone/IR reassignment across GP-50 patches (features 5 & 6).

Patches reference SnapTones/IRs by device SLOT, not identity. This tool lets you
operate by NAME: it resolves name->slot from an identity map (the export set, plus
an optional authoritative device map at patch/bank_map.json), edits the N->S
(SnapTone) or CAB (IR) index byte, refixes the .prst CRC, and writes new files.
Re-import the outputs via Suite. Never overwrites source patches.

  map                                  show SnapTone/IR identity map
  reassign <patch.prst> --to <name|#N> [--out F]   repoint one patch's SnapTone
  swap --from <name|#N> --to <name|#N> [--in DIR] [--out DIR]   batch across all patches
  set-ir <patch.prst> --to #N [--out F]            repoint one patch's CAB/IR
"""

import sys
import os
import re
import glob
import json
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from prst import models_block, CAT  # noqa
import prst_edit  # noqa

EXP_DEFAULT = os.path.join(os.path.dirname(__file__), "..", "presetExports")
MAP_JSON = os.path.join(os.path.dirname(__file__), "bank_map.json")
NS_CAT, CAB_CAT = 0x0F, 0x0A


def patch_label(path):
    return re.sub(r"^\d+-", "", os.path.basename(path)).replace(".prst", "")


def snaptone_of(b):
    _, recs = models_block(b)
    for idx, cat in recs:
        if cat == NS_CAT:
            return idx
    return None


def build_map(expdir):
    """slot -> label, inferred from patches that use each SnapTone; merged with
    the authoritative device map if patch/bank_map.json exists."""
    m = {}
    for f in sorted(glob.glob(os.path.join(expdir, "*.prst"))):
        s = snaptone_of(open(f, "rb").read())
        if s:  # 0 = no SnapTone
            m.setdefault(s, set()).add(patch_label(f))
    labels = {s: "/".join(sorted(v)) for s, v in m.items()}
    if os.path.exists(MAP_JSON):
        dev = json.load(open(MAP_JSON)).get("snaptone", {})
        for k, v in dev.items():
            labels[int(k)] = v  # authoritative device name wins
    return labels


def resolve(token, labels):
    """'#57' or a name substring -> slot number."""
    token = token.strip()
    if token.startswith("#"):
        return int(token[1:], 0)
    hits = [s for s, lbl in labels.items() if token.lower() in lbl.lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(
            f"no SnapTone matches {token!r}; known: {sorted(labels.items())}"
        )
    raise SystemExit(
        f"{token!r} is ambiguous: {[(s, labels[s]) for s in hits]} — use #slot"
    )


def cmd_map(a):
    labels = build_map(a.exp)
    print("SnapTone identity map (device N->S slot -> label):")
    for s in sorted(labels):
        print(f"  #{s:<3} {labels[s]}")
    auth = (
        "yes"
        if os.path.exists(MAP_JSON)
        else "no (inferred from patch names; run live_read once device is back)"
    )
    print(f"\nauthoritative device map present: {auth}")


def _write(inp, cat, slot, out):
    b = open(inp, "rb").read()
    nb, cur = prst_edit.set_index(b, cat, slot)
    open(out, "wb").write(nb)
    return cur


def cmd_reassign(a):
    labels = build_map(a.exp)
    slot = resolve(a.to, labels)
    out = a.out or os.path.join(
        os.path.dirname(a.patch),
        os.path.basename(a.patch).replace(".prst", f"__NS{slot}.prst"),
    )
    cur = _write(a.patch, NS_CAT, slot, out)
    print(
        f"{os.path.basename(a.patch)}: SnapTone slot {cur} -> {slot} ({labels.get(slot, '?')})"
    )
    print(f"wrote {out}  (CRC refixed) — re-import via Suite")


def cmd_setir(a):
    slot = int(a.to.lstrip("#"), 0)
    out = a.out or os.path.join(
        os.path.dirname(a.patch),
        os.path.basename(a.patch).replace(".prst", f"__CAB{slot}.prst"),
    )
    cur = _write(a.patch, CAB_CAT, slot, out)
    print(f"{os.path.basename(a.patch)}: CAB/IR index {cur} -> {slot}")
    print(f"wrote {out}  (CRC refixed) — re-import via Suite")


def cmd_swap(a):
    labels = build_map(a.exp)
    src, dst = resolve(a.getattr_from, labels), resolve(a.to, labels)
    outdir = a.out or os.path.join(a.indir, "_swapped")
    os.makedirs(outdir, exist_ok=True)
    n = 0
    for f in sorted(glob.glob(os.path.join(a.indir, "*.prst"))):
        b = open(f, "rb").read()
        if snaptone_of(b) == src:
            out = os.path.join(outdir, os.path.basename(f))
            _write(f, NS_CAT, dst, out)
            n += 1
            print(f"  {os.path.basename(f)}: SnapTone {src} -> {dst}")
    print(
        f"\n{n} patch(es) repointed {src}({labels.get(src, '?')}) -> {dst}({labels.get(dst, '?')})"
    )
    print(f"outputs in {outdir} — re-import via Suite")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("map",):
        sp = sub.add_parser(name)
        sp.add_argument("--exp", default=EXP_DEFAULT)
    r = sub.add_parser("reassign")
    r.add_argument("patch")
    r.add_argument("--to", required=True)
    r.add_argument("--out")
    r.add_argument("--exp", default=EXP_DEFAULT)
    s = sub.add_parser("set-ir")
    s.add_argument("patch")
    s.add_argument("--to", required=True)
    s.add_argument("--out")
    s.add_argument("--exp", default=EXP_DEFAULT)
    w = sub.add_parser("swap")
    w.add_argument("--from", dest="getattr_from", required=True)
    w.add_argument("--to", required=True)
    w.add_argument("--in", dest="indir", default=EXP_DEFAULT)
    w.add_argument("--out")
    w.add_argument("--exp", default=EXP_DEFAULT)
    a = p.parse_args()
    {"map": cmd_map, "reassign": cmd_reassign, "set-ir": cmd_setir, "swap": cmd_swap}[
        a.cmd
    ](a)


if __name__ == "__main__":
    main()
