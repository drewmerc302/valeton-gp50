"""Shared JSON-list file store for the computer-side libraries.

One implementation of the persistence scaffolding (read-with-fallback, atomic
tmp-swap write, a per-store mutation lock) that blocklib (block_library.json)
and templates_store (templates.json) both sit on. Entries are dicts carrying
an "id" key; the domain modules own their entry shapes.
"""

from __future__ import annotations

import json
import os
import threading


class JsonStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def read(self) -> list:
        if not os.path.exists(self.path):
            return []
        try:
            return json.load(open(self.path))
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, entries: list) -> None:
        tmp = self.path + ".tmp"
        json.dump(entries, open(tmp, "w"), indent=2)
        os.replace(tmp, self.path)

    def append(self, entry: dict) -> dict:
        with self._lock:
            entries = self.read()
            entries.append(entry)
            self._write(entries)
        return entry

    def delete(self, entry_id: str) -> bool:
        """Remove the entry with this id. Returns False if it wasn't there."""
        with self._lock:
            entries = self.read()
            kept = [e for e in entries if e.get("id") != entry_id]
            if len(kept) == len(entries):
                return False
            self._write(kept)
        return True
