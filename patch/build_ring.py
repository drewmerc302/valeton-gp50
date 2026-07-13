#!/usr/bin/env python3
"""Regenerate patch/fxid_ring.json (fxid -> model metadata) from Valeton Suite's
module50_data.json. Includes `origin` = the official gear reference (e.g. Green OD
-> "Ibanez TS808"), used by the explorer's "official names" toggle. Cabs/reverbs
have no origin and stay as their device name."""

import json
import os
import re

SUITE = (
    "/Applications/Valeton Suite.app/Contents/Frameworks/App.framework"
    "/Versions/A/Resources/flutter_assets/assets/data/module50_data.json"
)
OUT = os.path.join(os.path.dirname(__file__), "fxid_ring.json")


def clean_origin(o: str) -> str:
    if not o:
        return ""
    o = o.split("\n")[0].strip()  # drop "XTOMP/Ampero Name: ..." 2nd line
    o = re.sub(r"\s*\(MIJ\)\s*$", "", o).strip()  # drop trailing "(MIJ)" noise
    if o.lower() in ("original", "n/a", "none", "-"):  # not a real gear reference
        return ""
    return o


def main():
    d = json.load(open(SUITE))
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
                "origin": clean_origin(e.get("origin")),
            }
    json.dump({str(k): v for k, v in ring.items()}, open(OUT, "w"))
    withorigin = sum(1 for v in ring.values() if v["origin"])
    print(f"wrote {OUT}: {len(ring)} models, {withorigin} with an official origin")


if __name__ == "__main__":
    main()
