#!/usr/bin/env python3
"""Read the GP-50 model catalog (gentle, ONE request) and write the authoritative
SnapTone slot->name map to patch/bank_map.json. The N->S SnapTone slot referenced
by a patch is an index into this catalog; user SnapTones occupy indices 50..79.

Catalog stream (selector 0x24, reply cmd 0x48): 2-byte header + 16-byte name
records from offset 2 (record index = (offset-2)//16), names null-padded ASCII."""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))
import live_read as L

# stream = [2-byte selector][80-byte occupancy array][80 x 16-byte name records]
# names start at offset 82; record index = (offset-82)//16.
NAME_START, REC = 82, 16
USER_SNAPTONE_START = 50  # 0..49 = factory amps; 50..79 = user SnapTone slots


def parse_catalog(blob):
    out = {}
    i = NAME_START
    while i + REC <= len(blob):
        idx = (i - NAME_START) // REC
        name = blob[i : i + REC].split(b"\0")[0].decode("latin1", "replace").strip()
        out[idx] = name
        i += REC
    return out


def main():
    buf, replies = L.read_bank(0x24, wait=3.0)
    banks = L.reassemble(replies)
    blob = banks.get(0x48, b"")
    if not blob:
        raise SystemExit("no catalog data — device unresponsive?")
    cat = parse_catalog(blob)
    snaptones = {
        s: n for s, n in cat.items() if s >= USER_SNAPTONE_START and n and n != "Empty"
    }
    out = {
        "source": "live device read (selector 0x24 model catalog)",
        "snaptone": {str(k): v for k, v in sorted(snaptones.items())},
    }
    path = os.path.join(os.path.dirname(__file__), "bank_map.json")
    json.dump(out, open(path, "w"), indent=2)
    print(f"catalog entries: {len(cat)}  populated user SnapTones: {len(snaptones)}")
    for s, n in sorted(snaptones.items()):
        print(f"  slot {s:3}: {n!r}")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
