#!/usr/bin/env python3
"""Task #2 probe: does selector 0x41 return patch BODY data? (Suite reads it right
after a patch write.) One hardened read, inspect the reassembled blob."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import live_read

sel = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x41
wait = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0

buf, replies = live_read.read_bank(sel, wait=wait)
banks = live_read.reassemble(replies)
print(
    f"selector {sel:#04x}: {len(replies)} reply frames, reassembled cmds: {[hex(c) for c in banks]}"
)
for cmd, blob in banks.items():
    print(f"  cmd {cmd:#04x}: {len(blob)} bytes")
    print(f"    head: {blob[:32].hex(' ')}")
    for tag, desc in [
        (b"GP50", "magic"),
        (bytes.fromhex("033028"), "model rec"),
        (bytes.fromhex("043040"), "param rec"),
    ]:
        pos = blob.find(tag)
        print(f"    {desc}: {'@' + str(pos) if pos >= 0 else 'not found'}")
    # printable name-ish runs
    printable = bytes(c if 32 <= c < 127 else 0x2E for c in blob[:120])
    print(f"    ascii: {printable.decode('latin1')}")
