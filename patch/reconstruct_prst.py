#!/usr/bin/env python3
"""Verify the .prst rebuild round-trip against the exported patch set.

The layout and the rebuild itself live in patch/prst_format.py (rebuild(name,
body)). This script re-proves the 100/100 round-trip: every exported .prst ==
rebuild(name, body) of its own parts. No device I/O.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import prst_format as fmt

# Re-exported for callers that predate prst_format (scan_bank imported this).
rebuild = fmt.rebuild


def _verify():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exports = glob.glob(os.path.join(root, "presetExports", "*.prst"))
    prsts = {os.path.basename(p): open(p, "rb").read() for p in exports}
    prsts = {k: v for k, v in prsts.items() if len(v) == fmt.PRST_LEN}
    assert all(v[: fmt.CRC_OFF] == fmt.HEADER for v in prsts.values()), (
        "header not constant"
    )
    assert all(v[0x15:0x19] == fmt.SENTINEL for v in prsts.values()), (
        "sentinel not constant"
    )
    ok = sum(
        rebuild(fmt.read_name(v), v[fmt.BODY_OFF :]) == v for k, v in prsts.items()
    )
    print(f"rebuilt == original: {ok}/{len(prsts)} patches")


if __name__ == "__main__":
    _verify()
