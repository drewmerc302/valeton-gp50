#!/usr/bin/env python
"""Pin CRC-8 poly=0x07 (confirmed from the dylib table). Sweep init/xorout/range,
per-packet and rolling, to match ck=(b1<<4)|b2."""

import re
import sys

HEX = re.compile(r"\b[0-9A-Fa-f]{2}\b")

# CRC-8/0x07 table (MSB-first, refin=False)
TBL = []
for i in range(256):
    c = i
    for _ in range(8):
        c = ((c << 1) ^ 0x07) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    TBL.append(c)


def crc(data, init):
    c = init
    for b in data:
        c = TBL[(c ^ (b & 0xFF)) & 0xFF]
    return c


def packets(path):
    out = []
    for line in open(path, errors="replace"):
        if "to gp-50" not in line.lower():
            continue
        b = [int(t, 16) for t in HEX.findall(line)]
        if 0xF0 in b:
            b = b[b.index(0xF0) :]
            if len(b) == 48 and b[3] == 0x09 and b[4] == 0x02:
                out.append(b)
    return out


def dec(p):
    pl = p[9:-1]
    return [((pl[i] & 0xF) << 4) | (pl[i + 1] & 0xF) for i in range(0, len(pl) - 1, 2)]


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
    )
    pk = packets(path)
    n = len(pk)
    tgt = [(p[1] << 4) | p[2] for p in pk]

    def rng(p, name):
        d = dec(p)
        return {
            "dec": d,
            "sec,blk+dec": [p[5], p[6]] + d,
            "blk+dec": [p[6]] + d,
            "09,02,sec,blk,01,03+dec": [0x09, 0x02, p[5], p[6], 0x01, 0x03] + d,
            "F0,0,0,09,02,sec,blk,01,03+dec": [
                0xF0,
                0,
                0,
                0x09,
                0x02,
                p[5],
                p[6],
                0x01,
                0x03,
            ]
            + d,
            "nibble[9:-1]": p[9:-1],
            "nibble[3:-1]": p[3:-1],
        }[name]

    rnames = [
        "dec",
        "sec,blk+dec",
        "blk+dec",
        "09,02,sec,blk,01,03+dec",
        "F0,0,0,09,02,sec,blk,01,03+dec",
        "nibble[9:-1]",
        "nibble[3:-1]",
    ]

    best = []
    # (A) per-packet, sweep init + xorout
    for rn in rnames:
        for init in range(256):
            counts = {}
            for i, p in enumerate(pk):
                c = crc(rng(p, rn), init)
                x = c ^ tgt[i]
                counts[x] = counts.get(x, 0) + 1
            xo, hits = max(counts.items(), key=lambda kv: kv[1])
            if hits > n * 0.8:
                best.append(
                    (
                        hits,
                        f"per-pkt CRC8/0x07 range={rn} init={init:#04x} xorout={xo:#04x}",
                    )
                )

    # (B) rolling continuous over a stream, sample before/after, sweep init
    def streams(p):
        d = dec(p)
        return {
            "dec": d,
            "nibble[9:-1]": list(p[9:-1]),
            "hdr+dec": [p[5], p[6]] + d,
            "hdr+nibble": [p[5], p[6]] + list(p[9:-1]),
        }

    for sn in ("dec", "nibble[9:-1]", "hdr+dec", "hdr+nibble"):
        for init in range(256):
            for sample in ("before", "after"):
                c = init
                hits = 0
                for i, p in enumerate(pk):
                    if sample == "before" and c == tgt[i]:
                        hits += 1
                    for b in streams(p)[sn]:
                        c = TBL[(c ^ (b & 0xFF)) & 0xFF]
                    if sample == "after" and c == tgt[i]:
                        hits += 1
                if hits > n * 0.8:
                    best.append(
                        (
                            hits,
                            f"ROLLING CRC8/0x07 stream={sn} init={init:#04x} {sample}",
                        )
                    )

    best.sort(reverse=True)
    print(f"{n} packets, poly=0x07 pinned. Results >80%:")
    for h, d in best[:15]:
        print(f"  {h}/{n}  {d}")
    if not best:
        print(
            "  none >80%. Best per-packet residual was <=80% — try including F7 or a per-packet nonce."
        )


if __name__ == "__main__":
    main()
