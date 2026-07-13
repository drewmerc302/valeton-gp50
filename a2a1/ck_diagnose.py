#!/usr/bin/env python
"""Diagnose what the GP-50 upload checksum (bytes[1],[2]) depends on."""

import re
import sys

HEX = re.compile(r"\b[0-9A-Fa-f]{2}\b")


def packets(path):
    out = []
    for line in open(path, errors="replace"):
        if "to gp-50" not in line.lower():
            continue
        b = [int(t, 16) for t in HEX.findall(line)]
        if 0xF0 not in b:
            continue
        b = b[b.index(0xF0) :]
        if len(b) == 48 and b[3] == 0x09 and b[4] == 0x02:
            out.append(b)
    return out


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
    )
    pk = packets(path)
    n = len(pk)

    # Split into imports at ck reset to (0,0)
    zero_starts = [i for i, p in enumerate(pk) if (p[1], p[2]) == (0, 0)]
    print(f"{n} packets; ck==(0,0) at packet indices: {zero_starts}")

    # (1) content determinism: do identical (payload) -> identical ck?
    from collections import defaultdict

    by_payload = defaultdict(set)
    for p in pk:
        by_payload[tuple(p[9:-1])].add((p[1], p[2]))
    multi = {k: v for k, v in by_payload.items() if len(v) > 1}
    print(
        f"\n(1) distinct payloads: {len(by_payload)}; payloads mapping to >1 ck: {len(multi)}"
    )
    zero_payload = tuple([0] * len(pk[0][9:-1]))
    print(
        f"    all-zero payload -> cks: {sorted(by_payload.get(zero_payload, set()))[:10]}"
    )

    # (2) is ck a function of (sec,blk)?
    by_pos = defaultdict(set)
    for p in pk:
        by_pos[(p[5], p[6])].add((p[1], p[2]))
    pos_multi = sum(1 for v in by_pos.values() if len(v) > 1)
    print(
        f"\n(2) (sec,blk) positions: {len(by_pos)}; positions with >1 ck: {pos_multi} "
        f"(0 => ck is pure fn of position)"
    )

    # (3) running/cumulative hypotheses, per-import (reset at ck==0,0)
    bounds = zero_starts + [n]
    print("\n(3) cumulative running-sum test (per import segment):")
    for s_i in range(len(zero_starts)):
        seg = pk[bounds[s_i] : bounds[s_i + 1]]
        # cumulative sum of all payload bytes in prior packets
        run = 0
        ok_sum = 0
        run_dec = 0
        ok_dec = 0
        for i, p in enumerate(seg):
            ck = (p[1], p[2])
            # predict from running state BEFORE adding this packet
            pred_sum = ((run >> 7) & 0x7F, run & 0x7F)
            if pred_sum == ck:
                ok_sum += 1
            if (run & 0x7F, (run >> 7) & 0x7F) == ck:
                ok_dec += 1
            run = (run + sum(p[9:-1])) & 0x3FFF
        print(
            f"  import seg {s_i} ({len(seg)} pkts): cumsum(payload) hi,lo match={ok_sum}, lo,hi match={ok_dec}"
        )

    # (4) show the ck sequence for the first segment to eyeball a pattern (LFSR/PRNG?)
    seg0 = pk[bounds[0] : bounds[1]]
    print("\n(4) ck sequence, import 0 (idx: sec/blk -> ck1 ck2, payload_nonzero?):")
    for p in seg0[:24]:
        nz = any(x for x in p[9:-1])
        print(f"    {p[5]}/{p[6]:2d} -> {p[1]:02X} {p[2]:02X}  payload_nonzero={nz}")


if __name__ == "__main__":
    main()
