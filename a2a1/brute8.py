#!/usr/bin/env python
"""
Crack the GP-50 upload checksum as an 8-bit value: ck = (bytes[1]<<4)|bytes[2].
Tests per-packet and ROLLING (cumulative) 8-bit sum/xor/crc8 families.
"""

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


def dec(p):
    pl = p[9:-1]
    return [((pl[i] & 0xF) << 4) | (pl[i + 1] & 0xF) for i in range(0, len(pl) - 1, 2)]


def crc8_step(crc, byte, poly, refin):
    if refin:
        byte = int(f"{byte:08b}"[::-1], 2)
    crc ^= byte
    for _ in range(8):
        crc = ((crc << 1) ^ poly) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


CRC8_POLYS = [0x07, 0x31, 0x1D, 0x9B, 0xD5, 0x2F, 0x39, 0x4D, 0xA7, 0x8D, 0xC2]


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
    )
    pk = packets(path)
    n = len(pk)
    tgt = [((p[1] << 4) | p[2]) for p in pk]
    print(f"{n} packets. ck(8bit) first 8: {' '.join(f'{t:02X}' for t in tgt[:8])}")

    # per-packet data variants
    def variants(p):
        d = dec(p)
        return {
            "dec": d,
            "sec,blk+dec": [p[5], p[6]] + d,
            "blk+dec": [p[6]] + d,
        }

    best = []

    # (A) per-packet CRC8 / sum8 / xor8
    for vn in ("dec", "sec,blk+dec", "blk+dec"):
        for poly in CRC8_POLYS:
            for init in (0x00, 0xFF):
                for refin in (False, True):
                    for xorout in (0x00, 0xFF):
                        hits = 0
                        for p in pk:
                            crc = init
                            for byte in variants(p)[vn]:
                                crc = crc8_step(crc, byte, poly, refin)
                            if (crc ^ xorout) == ((p[1] << 4) | p[2]):
                                hits += 1
                        if hits > n * 0.6:
                            best.append(
                                (
                                    hits,
                                    f"per-pkt crc8 poly={poly:#04x} init={init:#04x} refin={refin} xorout={xorout:#04x} range={vn}",
                                )
                            )
        # sum8 / xor8
        for name, fn in (
            ("sum8", lambda d: sum(d) & 0xFF),
            ("negsum8", lambda d: (-sum(d)) & 0xFF),
            (
                "xor8",
                lambda d: __import__("functools").reduce(lambda a, c: a ^ c, d, 0),
            ),
        ):
            hits = sum(1 for p in pk if fn(variants(p)[vn]) == ((p[1] << 4) | p[2]))
            if hits > n * 0.6:
                best.append((hits, f"per-pkt {name} range={vn}"))

    # (B) ROLLING over cumulative decoded stream, sampled per packet
    for poly in CRC8_POLYS:
        for init in (0x00, 0xFF):
            for refin in (False, True):
                for sample in ("before", "after"):
                    crc = init
                    hits = 0
                    for p in pk:
                        if sample == "before" and crc == ((p[1] << 4) | p[2]):
                            hits += 1
                        for byte in dec(p):
                            crc = crc8_step(crc, byte, poly, refin)
                        if sample == "after" and crc == ((p[1] << 4) | p[2]):
                            hits += 1
                    if hits > n * 0.6:
                        best.append(
                            (
                                hits,
                                f"ROLLING crc8 poly={poly:#04x} init={init:#04x} refin={refin} sample={sample}",
                            )
                        )
    # rolling sum8 (before/after)
    for sample in ("before", "after"):
        s = 0
        hits = 0
        for p in pk:
            if sample == "before" and (s & 0xFF) == ((p[1] << 4) | p[2]):
                hits += 1
            s += sum(dec(p))
            if sample == "after" and (s & 0xFF) == ((p[1] << 4) | p[2]):
                hits += 1
        if hits > n * 0.6:
            best.append((hits, f"ROLLING sum8 sample={sample}"))

    best.sort(reverse=True)
    print("\n=== matches >60% ===")
    if best:
        for h, desc in best[:15]:
            print(f"  {h:3d}/{n}  {desc}")
    else:
        print(
            "  none >60% — checksum still not identified (try including sec/cmd, or rolling incl headers)"
        )


if __name__ == "__main__":
    main()
