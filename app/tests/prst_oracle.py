"""Emit expected .prst parse + GP-5<->GP-50 conversion results for the in-repo
preset corpus, as a JSON manifest on stdout. The JS port (app/static/prst.js) is
checked byte-for-byte against this by app/tests/test_prst_js.mjs.

Corpus is repo-local only (presetExports/ + app/tests/fixtures/gp5/) so the test
runs from a clean checkout with no external files.
"""

import base64
import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from patch import convert as conv  # noqa: E402
from patch import prst_format as fmt  # noqa: E402


def corpus() -> list[str]:
    paths = []
    paths += sorted(glob.glob(os.path.join(ROOT, "presetExports", "*.prst")))
    paths += sorted(
        glob.glob(os.path.join(ROOT, "app", "tests", "fixtures", "gp5", "*.prst"))
    )
    return paths


def b64(x) -> str:
    return base64.b64encode(bytes(x)).decode()


def record(path: str) -> dict:
    with open(path, "rb") as fh:
        prst = fh.read()
    try:
        src = fmt.detect(prst)
    except ValueError as e:
        return {"path": path, "error": str(e)}
    other = "gp5" if src.key == "gp50" else "gp50"
    rec = {
        "path": os.path.relpath(path, ROOT),
        "srcKey": src.key,
        "name": fmt.read_name(prst),
        "models": [list(m) for m in fmt.model_records(prst)],
        "bypass": fmt.bypass_mask(prst),
        "order": fmt.read_order(prst),
        "params": fmt.param_floats(prst),
        "fsOff": fmt.fs_offset(prst),
        "volBpm": list(conv._read_vol_bpm(prst)),
        "fs": list(conv._read_footswitches(prst)),
        "target": other,
        "problems": [list(p) for p in conv.check_convertible(prst, other)],
        "prstB64": b64(prst),
    }
    try:
        rec["convB64"] = b64(conv.convert(prst, other))
        rec["convErr"] = None
    except conv.ConversionError as e:
        rec["convB64"] = None
        rec["convErr"] = str(e)
        rec["convForceB64"] = b64(conv.convert(prst, other, force=True))
    return rec


if __name__ == "__main__":
    print(json.dumps([record(p) for p in corpus()]))
