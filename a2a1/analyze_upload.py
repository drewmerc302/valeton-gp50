#!/usr/bin/env python
"""
Analyze a MIDI Monitor capture of GP-50 SnapTone uploads (host->device).

Upload packet (48B): F0 [ck1] [ck2] 09 02 00 [block_idx] 01 03 [payload...] F7
Goal: confirm structure, split the two imports (block_idx resets), reconstruct each
SnapTone byte stream (payload is nibble-encoded), and hunt the 2-byte checksum.

Usage: python analyze_upload.py ~/Desktop/valeton_import_capture.txt
"""

import re
import sys
from collections import Counter

HEX = re.compile(r"\b[0-9A-Fa-f]{2}\b")


def parse(path):
    rows = []
    for line in open(path, errors="replace"):
        low = line.lower()
        if "to gp-50" in low:
            d = "H>D"
        elif "from gp-50" in low:
            d = "D>H"
        else:
            continue
        # take the hex frame = the run of 2-hex tokens starting at F0
        toks = HEX.findall(line)
        b = [int(t, 16) for t in toks]
        if 0xF0 in b:
            i = b.index(0xF0)
            j = b.index(0xF7, i) if 0xF7 in b[i:] else len(b)
            rows.append((d, b[i : j + 1]))
    return rows


def nibbles_to_bytes(payload):
    out = bytearray()
    for i in range(0, len(payload) - 1, 2):
        out.append(((payload[i] & 0xF) << 4) | (payload[i + 1] & 0xF))
    return bytes(out)


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
    )
    rows = parse(path)
    up = [b for d, b in rows if d == "H>D"]
    ack = [b for d, b in rows if d == "D>H"]
    print(f"packets: {len(up)} H>D (upload), {len(ack)} D>H (ack)")

    # ACK uniqueness
    acks = Counter(tuple(a) for a in ack)
    print(
        f"distinct ACKs: {len(acks)}; most common: {' '.join(f'{x:02X}' for x in acks.most_common(1)[0][0])}"
    )

    # Upload structure: verify the fixed header positions
    lens = Counter(len(b) for b in up)
    print(f"upload packet lengths: {dict(lens)}")
    # header signature bytes 3,4,5,7,8 (0-indexed) across all upload packets
    for pos in (3, 4, 5, 7, 8):
        vals = Counter(b[pos] for b in up if len(b) > pos)
        print(f"  byte[{pos}] values: {dict(vals)}")

    # block_idx = byte[6]; find import boundaries where idx resets
    idxs = [b[6] for b in up]
    resets = [i for i in range(1, len(idxs)) if idxs[i] <= idxs[i - 1] and idxs[i] == 0]
    print(f"\nblock_idx starts at {idxs[0]}, resets at packet #: {resets}")
    # split into imports at resets
    bounds = [0] + resets + [len(up)]
    imports = [up[bounds[k] : bounds[k + 1]] for k in range(len(bounds) - 1)]
    print(f"imports detected: {len(imports)} (sizes: {[len(im) for im in imports]})")

    for k, im in enumerate(imports):
        idx_seq = [p[6] for p in im]
        contiguous = idx_seq == list(range(len(im))) or idx_seq == list(
            range(idx_seq[0], idx_seq[0] + len(im))
        )
        # reconstruct payload stream (nibble-decoded), payload = bytes[9:-1]
        stream = b"".join(nibbles_to_bytes(p[9:-1]) for p in im)
        print(
            f"\nimport {k}: {len(im)} packets, idx {idx_seq[0]}..{idx_seq[-1]} "
            f"(contiguous={contiguous}), reconstructed {len(stream)} bytes"
        )
        print(f"  first 32 recon bytes: {stream[:32].hex(' ')}")

    # CHECKSUM HUNT on byte[1],byte[2]
    print("\n=== checksum hunt (ck = bytes[1],[2]) ===")
    cks = [(b[1], b[2]) for b in up]
    print(
        "first 6 (idx:ck): "
        + ", ".join(f"{up[i][6]}:{cks[i][0]:02X}{cks[i][1]:02X}" for i in range(6))
    )

    def hyp(name, fn):
        hits = sum(1 for b in up if fn(b) == (b[1], b[2]))
        print(f"  {name:42s}: {hits}/{len(up)} match")

    def body_after_ck(b):
        return b[3:-1]  # exclude F0, ck1, ck2, F7

    def whole_body(b):
        return b[
            1:-1
        ]  # everything between F0 and F7 incl ck (for self-checks it won't; use for sum-with-ck-0)

    def sum14(data):
        s = sum(data) & 0x3FFF
        return (s >> 7, s & 0x7F)

    def sum14_swap(data):
        s = sum(data) & 0x3FFF
        return (s & 0x7F, s >> 7)

    hyp("sum14(bytes after ck..before F7) hi,lo", lambda b: sum14(body_after_ck(b)))
    hyp("sum14(bytes after ck) lo,hi", lambda b: sum14_swap(body_after_ck(b)))
    hyp("sum14(payload[9:-1]) hi,lo", lambda b: sum14(b[9:-1]))
    hyp("sum14(payload[9:-1]) lo,hi", lambda b: sum14_swap(b[9:-1]))
    hyp(
        "(sum payload &7F, sum>>7)",
        lambda b: (sum(b[9:-1]) & 0x7F, (sum(b[9:-1]) >> 7) & 0x7F),
    )
    hyp(
        "xor payload -> (x&7F, x>>? )",
        lambda b: (
            __import__("functools").reduce(lambda a, c: a ^ c, b[9:-1], 0) & 0x7F,
            0,
        ),
    )
    hyp("sum(idx..before F7) hi,lo", lambda b: sum14(b[6:-1]))
    hyp("sum(payload nibble-decoded bytes)", lambda b: sum14(nibbles_to_bytes(b[9:-1])))


if __name__ == "__main__":
    main()
