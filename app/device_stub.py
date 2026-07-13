"""MOCK GP-50 device inventory (T4).

This is 100% mocked data — no MIDI, no serial, no USB, no contact with a
physical pedal anywhere in this module. The names are drawn from the
decoded-but-unverified GP-50 factory inventory (SnapTone captures, IR/cab
slots, and the 16 factory patches), reassembled here as a plausible,
internally-consistent fixture: some SnapTones/IRs are shared by several
patches, and some are unused, so the "usage inspector" has something
interesting to show.

TODO(real-device): this module is the seam. When SnapTone upload capture,
the 2-byte checksum, and the patch-body decode are cracked (see
AUTONOMY.md / STATUS.md "Blocked-on-Drew"), replace SNAPTONES/IRS/PATCHES
with data read from the live device and keep `patches_using_snaptone` /
`patches_using_ir` with these exact signatures — app/api_device.py should
not need to change at all.
"""

from __future__ import annotations

from typing import TypedDict


class SnapTone(TypedDict):
    slot: int
    name: str


class Ir(TypedDict):
    slot: int
    name: str


class Patch(TypedDict):
    slot: int
    name: str
    snaptone_slot: int
    ir_slot: int


SNAPTONES: list[SnapTone] = [
    {"slot": 0, "name": "Blackstar"},
    {"slot": 1, "name": "Fender Twin"},
    {"slot": 2, "name": "Marshall Plexi"},
    {"slot": 3, "name": "Mesa Rectifier"},
    {"slot": 4, "name": "Vox AC30"},  # unused by any factory patch
]

IRS: list[Ir] = [
    {"slot": 0, "name": "American Tweed"},
    {"slot": 1, "name": "British Alu"},
    {"slot": 2, "name": "British Stack"},
    {"slot": 3, "name": "Tweed Combo"},
    {"slot": 4, "name": "YA FTWN 212"},
    {"slot": 5, "name": "YA MES 212"},  # unused by any factory patch
]

# snaptone_slot/ir_slot are deliberately reused across several patches so
# the usage inspector has non-trivial many-to-one mappings to display.
PATCHES: list[Patch] = [
    {"slot": 0, "name": "GreatPedal", "snaptone_slot": 0, "ir_slot": 0},
    {"slot": 1, "name": "Neo Soul", "snaptone_slot": 1, "ir_slot": 3},
    {"slot": 2, "name": "Star Night", "snaptone_slot": 2, "ir_slot": 2},
    {"slot": 3, "name": "Power Lead", "snaptone_slot": 2, "ir_slot": 2},
    {"slot": 4, "name": "Heavy Dist", "snaptone_slot": 3, "ir_slot": 4},
    {"slot": 5, "name": "Pure Clean", "snaptone_slot": 0, "ir_slot": 0},
    {"slot": 6, "name": "Smooth", "snaptone_slot": 1, "ir_slot": 3},
    {"slot": 7, "name": "Blues", "snaptone_slot": 1, "ir_slot": 0},
    {"slot": 8, "name": "Big J", "snaptone_slot": 3, "ir_slot": 4},
    {"slot": 9, "name": "Solo", "snaptone_slot": 2, "ir_slot": 1},
    {"slot": 10, "name": "Wah", "snaptone_slot": 0, "ir_slot": 1},
    {"slot": 11, "name": "Hard Rock", "snaptone_slot": 3, "ir_slot": 2},
    {"slot": 12, "name": "Luxury", "snaptone_slot": 0, "ir_slot": 0},
    {"slot": 13, "name": "UK Fuzz", "snaptone_slot": 2, "ir_slot": 2},
    {"slot": 14, "name": "UK Stack", "snaptone_slot": 2, "ir_slot": 1},
    {"slot": 15, "name": "70 Britain", "snaptone_slot": 3, "ir_slot": 4},
]


def find_snaptone(slot: int) -> SnapTone | None:
    return next((s for s in SNAPTONES if s["slot"] == slot), None)


def find_ir(slot: int) -> Ir | None:
    return next((i for i in IRS if i["slot"] == slot), None)


def patches_using_snaptone(slot: int) -> list[Patch]:
    return [p for p in PATCHES if p["snaptone_slot"] == slot]


def patches_using_ir(slot: int) -> list[Patch]:
    return [p for p in PATCHES if p["ir_slot"] == slot]
