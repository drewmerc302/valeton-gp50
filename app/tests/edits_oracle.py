"""Emit expected apply-edits results for the in-repo corpus, as a JSON manifest.
The JS port (app/static/prst.js applyEdits) is checked byte-for-byte against this
by app/tests/test_edits_js.mjs.
"""

import base64
import copy
import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from app import patchlib  # noqa: E402
from patch import prst_format as fmt  # noqa: E402

# A spread of edit specs exercising every branch of apply_edits_bytes.
EDIT_SETS = [
    {
        "label": "params",
        "edits": {"params": {"0": {"0": 42.0, "1": 7.5}, "2": {"3": 100.0}}},
    },
    {"label": "bypass", "edits": {"bypass": {"0": True, "1": False, "3": True}}},
    {"label": "settings", "edits": {"settings": {"patch_vol": 73, "bpm": 132}}},
    {"label": "settings-clamp", "edits": {"settings": {"patch_vol": 250}}},
    {"label": "footswitches", "edits": {"footswitches": {"fs1": [0, 2], "fs2": [5]}}},
    {"label": "models", "edits": {"models": {"0": 0x0A00003C, "4": 0x01000001}}},
    {
        "label": "combined",
        "edits": {
            "params": {"1": {"0": 12.0, "2": 88.0}},
            "bypass": {"2": False},
            "settings": {"patch_vol": 40, "bpm": 90},
            "footswitches": {"fs1": [1], "fs2": [3, 4]},
            "models": {"5": 0x05000008},
        },
    },
]


def corpus() -> list[str]:
    paths = sorted(glob.glob(os.path.join(ROOT, "presetExports", "*.prst")))[:12]
    paths += sorted(
        glob.glob(os.path.join(ROOT, "app", "tests", "fixtures", "gp5", "*.prst"))
    )
    return paths


def records() -> list:
    out = []
    for path in corpus():
        with open(path, "rb") as fh:
            base = fh.read()
        src = fmt.detect(base)
        for es in EDIT_SETS:
            b = bytearray(base)
            patchlib.apply_edits_bytes(b, copy.deepcopy(es["edits"]))
            out.append(
                {
                    "path": os.path.relpath(path, ROOT),
                    "srcKey": src.key,
                    "label": es["label"],
                    "edits": es["edits"],
                    "baseB64": base64.b64encode(base).decode(),
                    "editedB64": base64.b64encode(bytes(b)).decode(),
                }
            )
    return out


if __name__ == "__main__":
    print(json.dumps(records()))
