#!/usr/bin/env python3
"""ONE gentle read of the active patch body (selector 0x41) -> /tmp/active_body.bin.
Single request via the hardened reader; decode happens offline afterward."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import live_read

_, replies = live_read.read_bank(0x41, wait=4.0)
banks = live_read.reassemble(replies)
blob = max(banks.values(), key=len) if banks else b""
open("/tmp/active_body.bin", "wb").write(blob)
print(f"saved {len(blob)} bytes to /tmp/active_body.bin; head={blob[:24].hex(' ')}")
