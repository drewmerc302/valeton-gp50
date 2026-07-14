#!/usr/bin/env python3
"""One safe read of the device patch-name bank (selector 0x40). Prints the tail
slots so we can pick a free scratch slot + capture a baseline for write read-back."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import live_read

buf, replies = live_read.read_bank(0x40)
banks = live_read.reassemble(replies)
# the patch-name stream is the largest reassembled blob
blob = max(banks.values(), key=len) if banks else b""
names = live_read.split_names(blob)
print(f"got {len(names)} patch-name records")
for idx, nm in names:
    if idx >= 80 or idx <= 2:  # show head + tail (candidate scratch slots)
        print(f"  slot idx {idx:>3} (0x{idx:02x}): {nm!r}")
