"""User Patch Templates — saved whole-patch effects "skeletons", stored computer-side.

A template captures a full patch body (the entire block chain + params + bypass
states + patch settings) under a user name (e.g. "Metal", "80s Clean"). It's the
patch-level sibling of the Block Library: where a library entry is one saved block,
a template is one saved effects wrapper. You then "build a patch from a capture" by
stamping a template onto a SnapTone — the template's N->S block is repointed at the
chosen capture and the result is written to the pedal (see app.patchlib.repoint_
snaptone_body). Persisted as JSON at templates.json in the project root; the 552-byte
source body is stored base64. No device I/O here.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import uuid

from app import patchlib
from patch import prst_format

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_PATH = os.path.join(PROJECT_ROOT, "templates.json")

_lock = threading.Lock()


def _read() -> list:
    if not os.path.exists(LIB_PATH):
        return []
    try:
        return json.load(open(LIB_PATH))
    except (json.JSONDecodeError, OSError):
        return []


def _write(entries: list) -> None:
    tmp = LIB_PATH + ".tmp"
    json.dump(entries, open(tmp, "w"), indent=2)
    os.replace(tmp, LIB_PATH)


def _summary_of(patch: dict) -> dict:
    """A compact, display-only description of a patch's effects chain for the card."""
    chain = [
        {
            "block": b["block"],
            "type": b.get("type"),
            "model": b.get("model"),
            "official": b.get("official"),
            "active": b.get("active"),
        }
        for b in patch.get("blocks", [])
        if b.get("active")
    ]
    return {
        "chain": chain,
        "uses_snaptone": patch.get("uses_snaptone", False),
        "block_count": len(chain),
    }


def _public(entry: dict) -> dict:
    """Strip the heavy base64 body for list responses."""
    return {k: v for k, v in entry.items() if k != "body_b64"}


def list_entries() -> list:
    return [_public(e) for e in _read()]


def get_entry(entry_id: str) -> dict | None:
    return next((e for e in _read() if e.get("id") == entry_id), None)


def add_from_patch(name: str, source_slot: int) -> dict:
    """Save the current body of device patch `source_slot` as a named template."""
    if not name.strip():
        raise ValueError("name required")
    path = patchlib.patch_file(source_slot)
    if path is None:
        raise ValueError(f"unknown patch slot {source_slot}")
    body = open(path, "rb").read()
    try:
        prst_format.check_length(body)
    except ValueError:
        raise ValueError(
            f"patch {source_slot} is not a {prst_format.PRST_LEN}-byte .prst"
        )
    patch = next((p for p in patchlib.all_patches() if p["slot"] == source_slot), None)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "name": name.strip(),
        "source_slot": source_slot,
        "source_name": (patch or {}).get("name", ""),
        "summary": _summary_of(patch or {}),
        "body_b64": base64.b64encode(body).decode("ascii"),
    }
    with _lock:
        entries = _read()
        entries.append(entry)
        _write(entries)
    return _public(entry)


def body_of(entry_id: str) -> bytes | None:
    e = get_entry(entry_id)
    return base64.b64decode(e["body_b64"]) if e else None


def delete_entry(entry_id: str) -> bool:
    with _lock:
        entries = _read()
        kept = [e for e in entries if e.get("id") != entry_id]
        if len(kept) == len(entries):
            return False
        _write(kept)
    return True
