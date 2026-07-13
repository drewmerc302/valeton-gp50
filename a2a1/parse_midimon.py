#!/usr/bin/env python
"""
Normalize a Snoize MIDI Monitor capture (text export) into midi_sniff-style .jsonl,
so the existing decoders (decode_sniff.py / decode_names.py) work on it.

MIDI Monitor is the way to capture host->device (the SnapTone UPLOAD), which passive
CoreMIDI can't see. Export: in MIDI Monitor, Edit > Select All, Edit > Copy, paste into
a plain-text file; save it; pass it here.

This parser is format-tolerant: it pulls hex byte tokens from each line, reassembles
F0..F7 SysEx frames (a frame may span lines), and tags direction. Direction heuristic:
lines mentioning "spy" or "->" toward the device are host->device (H>D); otherwise D>H.
Override with --dir if the heuristic is wrong for your export.

Usage:
    python parse_midimon.py capture.txt -o work/cap_import
    python parse_midimon.py capture.txt -o work/cap_import --dir H>D   # force all
Then:
    python decode_sniff.py work/cap_import.jsonl
    python decode_names.py work/cap_import.jsonl
"""

import argparse
import json
import re

HEX = re.compile(r"\b[0-9A-Fa-f]{2}\b")


def guess_dir(line):
    low = line.lower()
    if "spy" in low or "output to" in low or "destination" in low or "->" in low:
        return "H>D"
    if "<-" in low or "source" in low or "input" in low:
        return "D>H"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("-o", "--out", default="work/cap_import")
    ap.add_argument(
        "--dir", choices=["H>D", "D>H"], help="force direction for all frames"
    )
    args = ap.parse_args()

    # Collect (direction_hint, bytes) per line, then reassemble F0..F7 frames.
    tokens = []  # list of (dir_hint, byte)
    for line in open(args.infile, errors="replace"):
        # Skip obvious header/time-only lines but still scan for hex.
        d = args.dir or guess_dir(line)
        for tok in HEX.findall(line):
            tokens.append((d, int(tok, 16)))

    frames = []
    cur = None
    cur_dir = None
    for d, b in tokens:
        if b == 0xF0:
            cur = [b]
            cur_dir = d
        elif cur is not None:
            cur.append(b)
            if cur_dir is None and d is not None:
                cur_dir = d
            if b == 0xF7:
                frames.append((cur_dir or "?", cur))
                cur = None
                cur_dir = None

    with open(f"{args.out}.jsonl", "w") as fp:
        for i, (d, b) in enumerate(frames):
            rec = {
                "t": round(
                    i * 0.001, 5
                ),  # no real timestamps in text export; use order
                "session": 1,
                "dir": d,
                "len": len(b),
                "sysex": True,
                "hex": " ".join(f"{x:02X}" for x in b),
            }
            fp.write(json.dumps(rec) + "\n")

    dirs = {}
    for d, _ in frames:
        dirs[d] = dirs.get(d, 0) + 1
    print(f"parsed {len(frames)} SysEx frames -> {args.out}.jsonl")
    print("by direction:", dirs)
    if frames:
        big = max(frames, key=lambda f: len(f[1]))
        print(
            f"largest frame: {len(big[1])} bytes ({big[0]}) — likely the SnapTone payload"
        )


if __name__ == "__main__":
    main()
