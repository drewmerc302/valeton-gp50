"""The stdout contract between the conversion engine and the a2a1 train scripts.

app/engine.py runs train_a1.py / train_a1_070.py as subprocesses (in their own
torch venvs) and recovers two facts from their output: the distillation ESR and
the exported-file format verdict. Both sides import THIS module so the token
format is defined exactly once — a train script emits with emit_esr()/
emit_format(), the engine (and the a2_to_a1.py CLI) recovers them with
parse_esr()/parse_format().

stdlib-only on purpose: imported by the web app (.venv-app) and by the torch
training venvs (.venv 0.13.0 / .venv-a1 0.12.2) alike.
"""

from __future__ import annotations

import re

ESR_TOKEN = "DISTILL_ESR:"
FORMAT_TOKEN = "FORMAT:"

_ESR_RE = re.compile(re.escape(ESR_TOKEN) + r"\s*([0-9.eE+-]+)")
_FORMAT_RE = re.compile(re.escape(FORMAT_TOKEN) + r"\s*(.+)")


def emit_esr(esr: float) -> None:
    print(f"{ESR_TOKEN} {esr:.6f}")


def emit_format(verdict: str) -> None:
    print(f"{FORMAT_TOKEN} {verdict}")


def parse_esr(text: str) -> float | None:
    m = _ESR_RE.search(text or "")
    return float(m.group(1)) if m else None


def parse_format(text: str) -> str | None:
    m = _FORMAT_RE.search(text or "")
    return m.group(1).strip() if m else None


def format_ok(fmt_text: str | None) -> bool | None:
    """The format verdict line reads e.g. "OK (WaveNet 0.5.2)" or contains
    "UNEXPECTED ..." on a mismatch; None = no verdict seen."""
    if not fmt_text:
        return None
    return "OK" in fmt_text and "UNEXPECTED" not in fmt_text
