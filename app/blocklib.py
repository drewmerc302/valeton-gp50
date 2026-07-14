"""User Block Library — Fractal-style saved block settings, stored computer-side.

A library entry captures a block's model + parameter values under a user name
(e.g. "TS808 Clean Boost"), scoped to a block type so it only applies to matching
blocks. Persisted as JSON at block_library.json in the project root (via the
shared JsonStore). No device I/O.
"""

from __future__ import annotations

import os
import uuid

from app.jsonstore import JsonStore

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_store = JsonStore(os.path.join(PROJECT_ROOT, "block_library.json"))


def list_entries(block: str | None = None) -> list:
    return [e for e in _store.read() if block is None or e.get("block") == block]


def add_entry(name: str, block: str, fxid: int, model_name: str, params: dict) -> dict:
    """Save a block config. params = {algId: value}. Returns the stored entry."""
    if not name.strip():
        raise ValueError("name required")
    return _store.append(
        {
            "id": uuid.uuid4().hex[:12],
            "name": name.strip(),
            "block": block,
            "fxid": int(fxid),
            "model_name": model_name,
            "params": {str(k): float(v) for k, v in (params or {}).items()},
        }
    )


def delete_entry(entry_id: str) -> bool:
    return _store.delete(entry_id)
