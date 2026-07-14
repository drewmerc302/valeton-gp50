#!/usr/bin/env python3
"""Regenerate the fxid -> model metadata rings from Valeton Suite's asset data.
Builds one ring per device: fxid_ring.json from module50_data.json (GP-50) and
fxid_ring_gp5.json from module_data.json (GP-5). The GP-5 catalog is a strict
subset of the GP-50's. `origin` = the official gear reference (e.g. Green OD ->
"Ibanez TS808"), used by the explorer's "official names" toggle."""

import json
import os
import re

SUITE_DIR = (
    "/Applications/Valeton Suite.app/Contents/Frameworks/App.framework"
    "/Versions/A/Resources/flutter_assets/assets/data"
)
# (source asset filename, output ring filename) per device
RINGS = [
    ("module50_data.json", "fxid_ring.json"),  # GP-50
    ("module_data.json", "fxid_ring_gp5.json"),  # GP-5
]


def clean_origin(o: str) -> str:
    if not o:
        return ""
    o = o.split("\n")[0].strip()  # drop "XTOMP/Ampero Name: ..." 2nd line
    o = re.sub(r"^Original:\s*", "", o).strip()  # newer Suite data prefixes "Original:"
    o = re.sub(r"\s*\(MIJ\)\s*$", "", o).strip()  # drop trailing "(MIJ)" noise
    if o.lower() in ("original", "n/a", "none", "-"):  # not a real gear reference
        return ""
    return o


def resolve_origin(entry: dict) -> str:
    """Official gear name. Some origins drop the channel (e.g. Foxy 30N and
    Foxy 30TB are both 'VOX AC30'); recover it from the description's
    '(... channel)' hint when the origin has no parenthetical of its own."""
    o = clean_origin(entry.get("origin"))
    if not o or "(" in o:
        return o
    desc = re.sub(r"<[^>]+>", "", entry.get("descriptionEn") or "")
    m = re.search(r"\(([^)]*?)\s*channel\)", desc, re.I)
    if m:
        chan = m.group(1).strip().title()  # "normal" -> "Normal", "Top Boost"
        return f"{o} ({chan})"
    return o


def unit_from_range(rng: str) -> str:
    """Extract a display unit from a valueRange like '0.10Hz-10.00Hz' -> 'Hz',
    '0-1000ms' -> 'ms'. Returns '' for plain numeric or Off/On ranges."""
    if not rng or "/" in rng:
        return ""
    m = re.search(r"[0-9.]([A-Za-z%]+)\s*$", rng)  # trailing unit on the last number
    return m.group(1) if m else ""


def params_of(entry: dict) -> list:
    """Param definitions in model order: name + algId (float-slot index) + toggle
    flag + unit. Value at runtime = float[block*8 + algId]."""
    out = []
    for p in entry.get("alg") or []:
        try:
            algid = int(p.get("algId", "-1"))
        except (TypeError, ValueError):
            algid = -1
        if algid < 0:
            continue

        def _num(x, default):
            try:
                return float(x)
            except (TypeError, ValueError):
                return default

        out.append(
            {
                "name": p.get("name"),
                "algId": algid,
                "toggle": p.get("widgetType") == 1 or (p.get("valueRange") == "Off/On"),
                "unit": unit_from_range(p.get("valueRange") or ""),
                # slider bounds are in display units == the stored float value
                "min": _num(p.get("min"), 0),
                "max": _num(p.get("max"), 100),
                "step": _num(p.get("step"), 1),
                "default": _num(p.get("defaultValue"), 0),  # applied on model change
            }
        )
    return out


def build_ring(src_name: str) -> dict:
    d = json.load(open(os.path.join(SUITE_DIR, src_name)))
    ring = {}
    for m in d["modules"]:
        for e in m["module"]:
            fx = e.get("fxid")
            if fx is None:
                continue
            ring[fx] = {
                "module": m["name"],
                "moduleId": m.get("moduleId"),
                "name": e.get("name"),
                "fxtitle": e.get("fxtitle"),
                "type": e.get("type"),
                "origin": resolve_origin(e),
                "params": params_of(e),
            }
    return ring


def main(only: str = "all"):
    """Rebuild the model rings. `only` = 'gp50' | 'gp5' | 'all'. NOTE: a fresh
    GP-50 build reflects the *currently installed* Valeton Suite data, which can
    drift from the committed fxid_ring.json (origin coverage changes between Suite
    versions) — rebuild it deliberately, not as a side effect."""
    targets = {"gp50": RINGS[0:1], "gp5": RINGS[1:2], "all": RINGS}.get(only)
    if targets is None:
        raise SystemExit(f"unknown target {only!r} (gp50|gp5|all)")
    for src_name, out_name in targets:
        out = os.path.join(os.path.dirname(__file__), out_name)
        ring = build_ring(src_name)
        json.dump({str(k): v for k, v in ring.items()}, open(out, "w"))
        withorigin = sum(1 for v in ring.values() if v["origin"])
        withparams = sum(1 for v in ring.values() if v["params"])
        print(
            f"wrote {out}: {len(ring)} models, {withorigin} origins, "
            f"{withparams} with params"
        )


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else "all")
