"""User Block Library — Fractal-style saved block settings, stored computer-side.

A library entry captures a block's model + parameter values under a user name
(e.g. "TS808 Clean Boost"), scoped to a block type so it only applies to matching
blocks. Persisted as JSON at block_library.json in the project root. No device I/O.
"""

from __future__ import annotations

import json
import os
import threading
import uuid

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_PATH = os.path.join(PROJECT_ROOT, "block_library.json")

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


def list_entries(block: str | None = None) -> list:
    entries = _read()
    return [e for e in entries if block is None or e.get("block") == block]


def add_entry(name: str, block: str, fxid: int, model_name: str, params: dict) -> dict:
    """Save a block config. params = {algId: value}. Returns the stored entry."""
    if not name.strip():
        raise ValueError("name required")
    entry = {
        "id": uuid.uuid4().hex[:12],
        "name": name.strip(),
        "block": block,
        "fxid": int(fxid),
        "model_name": model_name,
        "params": {str(k): float(v) for k, v in (params or {}).items()},
    }
    with _lock:
        entries = _read()
        entries.append(entry)
        _write(entries)
    return entry


def delete_entry(entry_id: str) -> bool:
    with _lock:
        entries = _read()
        kept = [e for e in entries if e.get("id") != entry_id]
        if len(kept) == len(entries):
            return False
        _write(kept)
    return True
