#!/usr/bin/env python
"""
Test the big hypothesis: are SnapTone weights the source .nam weights repackaged as
float32? Reconstruct each import's byte stream, then search it for the source model's
weights packed as little-endian float32.

Usage: python analyze_weights.py ~/Desktop/valeton_import_capture.txt
"""

import json
import re
import struct
import sys

HEX = re.compile(r"\b[0-9A-Fa-f]{2}\b")
SRC = {
    "A2->A1 (out/A2.nam)": "/Users/drewmerc/workspace/valeton/out/A2.nam",
    "wavenet_a1_standard": "/Users/drewmerc/workspace/valeton/refs/wavenet_a1_standard.nam",
}


def data_packets(path):
    """Return 48-byte cmd=09 02 host->device packets in capture order."""
    pkts = []
    for line in open(path, errors="replace"):
        if "to gp-50" not in line.lower():
            continue
        b = [int(t, 16) for t in HEX.findall(line)]
        if 0xF0 not in b:
            continue
        i = b.index(0xF0)
        b = b[i:]
        if len(b) == 48 and b[3] == 0x09 and b[4] == 0x02:
            pkts.append(b)
    return pkts


def nib(payload):
    return bytes(
        ((payload[i] & 0xF) << 4) | (payload[i + 1] & 0xF)
        for i in range(0, len(payload) - 1, 2)
    )


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
    )
    pkts = data_packets(path)
    stream = b"".join(nib(p[9:-1]) for p in pkts)
    print(f"{len(pkts)} data packets -> {len(stream)} reconstructed bytes total")

    # Split into imports at the magic header 11 25 00 00 00 00
    magic = bytes([0x11, 0x25, 0x00, 0x00, 0x00, 0x00])
    starts = [m.start() for m in re.finditer(re.escape(magic), stream)]
    print(f"magic {magic.hex(' ')} at offsets: {starts}")
    segs = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(stream)
        segs.append(stream[s:e])
    for k, seg in enumerate(segs):
        # header: 11 25, then bytes, then a 10-ish char name
        name = bytes(c for c in seg[10:26] if 32 <= c < 127).decode("latin1", "replace")
        print(
            f"\n-- import {k}: {len(seg)} bytes, header {seg[:10].hex(' ')}, name~{name!r}"
        )

    # Load source weights, pack as float32 LE, search each segment.
    for label, p in SRC.items():
        d = json.load(open(p))
        w = d.get("weights", [])
        print(f"\n=== source {label}: {len(w)} weights ===")
        if not w:
            continue
        blob = struct.pack("<%df" % len(w), *[float(x) for x in w])
        # search full stream and each segment
        found_full = stream.find(blob[:64])  # first 16 weights as a probe
        print(f"  first-16-weights probe (64B) found in full stream at: {found_full}")
        for k, seg in enumerate(segs):
            pos = seg.find(blob[:64])
            if pos >= 0:
                # how much of the full weight blob matches from here?
                tail = seg[pos:]
                match_len = 0
                for i in range(min(len(tail), len(blob))):
                    if tail[i] != blob[i]:
                        break
                    match_len += 1
                print(
                    f"  -> MATCH in import {k} at offset {pos}: {match_len}/{len(blob)} weight-bytes contiguous"
                )
        # also try: maybe stored as float32 but the .nam lists them in a different order/scale
        # quick stat compare: decode segment floats and compare value sets
    # Characterize each segment's weight region (skip 32B header+name) as float32.
    import statistics as st

    for k, seg in enumerate(segs):
        body = seg[32:]
        n = len(body) // 4
        fl = struct.unpack("<%df" % n, body[: n * 4])
        finite = [f for f in fl if f == f and abs(f) < 1e30]
        frac = sum(1 for f in finite if abs(f) < 10) / max(1, len(fl))
        rng = (
            f"min={min(finite):.3g} max={max(finite):.3g} mean={st.mean(finite):.3g}"
            if finite
            else "n/a"
        )
        print(
            f"\nimport {k} weight-region: {n} float32; sane(|f|<10)={frac:.0%}; {rng}"
        )
        print(f"  first 12 floats: {[round(f, 4) for f in fl[:12]]}")


if __name__ == "__main__":
    main()
