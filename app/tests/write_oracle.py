"""Emit expected host->device patch-write streams for the in-repo corpus, as a
JSON manifest on stdout. The JS port (app/static/webmidi_write.js) is checked
byte-for-byte against this by app/tests/test_write_js.mjs.

The Python builder (patch/device_write.build_patch_write_stream) is itself verified
29/29 against real GP-50 Suite captures, so this transitively pins the JS to Suite.
"""

import base64
import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from patch import device_write as dw  # noqa: E402
from patch import prst_format as fmt  # noqa: E402

SLOTS = [0, 1, 7, 42, 99]


def corpus() -> list[str]:
    paths = []
    paths += sorted(glob.glob(os.path.join(ROOT, "presetExports", "*.prst")))[:12]
    paths += sorted(
        glob.glob(os.path.join(ROOT, "app", "tests", "fixtures", "gp5", "*.prst"))
    )
    return paths


def hexwire(packet: list) -> str:
    return "".join(f"{b:02x}" for b in packet)


def records() -> list:
    out = []
    for path in corpus():
        with open(path, "rb") as fh:
            prst = fh.read()
        src = fmt.detect(prst)
        for slot in SLOTS:
            stream = dw.build_patch_write_stream(prst, slot)
            ok, reason = dw.validate_stream(stream)
            out.append(
                {
                    "path": os.path.relpath(path, ROOT),
                    "srcKey": src.key,
                    "slot": slot,
                    "prstB64": base64.b64encode(prst).decode(),
                    "packets": [hexwire(p) for p in stream],
                    "nPackets": len(stream),
                    "validate": [ok, reason],
                }
            )
    return out


if __name__ == "__main__":
    print(json.dumps(records()))
