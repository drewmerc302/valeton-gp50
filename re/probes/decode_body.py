#!/usr/bin/env python3
"""Offline: decode the 0x41 active-body read (/tmp/active_body.bin) — identify which
patch it is and map its format against the .prst files. No device I/O."""

import sys
import os
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import patchlib

blob = open("/tmp/active_body.bin", "rb").read()
body = blob[2:] if blob[:2] == bytes([0x12, 0x41]) else blob  # strip selector echo
print(f"read body: {len(body)} bytes")
print(f"  head: {body[:28].hex(' ')}")

# any ascii name in it?
runs = []
cur = b""
for c in body:
    if 32 <= c < 127:
        cur += bytes([c])
    else:
        if len(cur) >= 3:
            runs.append(cur.decode())
        cur = b""
print(f"  ascii runs: {runs}")


def longest_run(a, b):
    best = 0
    for off in range(-24, 24):
        run = r = 0
        for i in range(len(a)):
            j = i + off
            if 0 <= j < len(b) and a[i] == b[j]:
                r += 1
                best = max(best, r)
            else:
                r = 0
    return best


# which .prst body best matches this read body?
best = (0, None, 0)
for path in glob.glob(os.path.join(patchlib.PROJECT_ROOT, "presetExports", "*.prst")):
    src = open(path, "rb").read()
    if len(src) != 552:
        continue
    run = longest_run(body, src[0x15:])
    if run > best[0]:
        best = (run, os.path.basename(path), len(src))
print(
    f"\nbest .prst match: {best[1]}  longest common run: {best[0]} bytes (of {len(body)})"
)

# align to that match and show the offset mapping of landmarks
if best[1]:
    src = open(
        os.path.join(patchlib.PROJECT_ROOT, "presetExports", best[1]), "rb"
    ).read()
    pb = src[0x15:]
    for tag, desc in [
        (b"GP50", "magic"),
        (bytes.fromhex("033028"), "model"),
        (bytes.fromhex("043040"), "param"),
    ]:
        print(f"  {desc}: read-body@{body.find(tag)}  prst-body@{pb.find(tag)}")
