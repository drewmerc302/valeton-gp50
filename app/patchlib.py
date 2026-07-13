"""Real GP-50 inventory, parsed from the exported patch set (presetExports/).

Replaces the old mock in device_stub. No device I/O: reads the 100 exported
.prst files + patch/fxid_ring.json (the model catalog decoded from Valeton
Suite). This is possible because the .prst format is fully reverse-engineered
(see patch/prst.py, patch/REFIT_FINDINGS.md).

A patch references its blocks by device SLOT / model index, not by identity:
model record = [modelIndex:u8][00 00][category:u8], and fxid = (category<<24)|idx.
- N->S (category 0x0f) = SnapTone slot (0 = none; a SnapTone disables AMP+CAB)
- CAB  (category 0x0a) = cab / IR model
- AMP  (category 0x07/0x08) = amp model

`bank_map.json` (written by patch/live_read once the device is read) overrides
SnapTone slot labels with authoritative device names when present.
"""

from __future__ import annotations

import glob
import json
import os
import re
import struct
from functools import lru_cache
from typing import Optional, TypedDict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT_DIR = os.path.join(PROJECT_ROOT, "presetExports")
FXID_RING = os.path.join(PROJECT_ROOT, "patch", "fxid_ring.json")
BANK_MAP = os.path.join(PROJECT_ROOT, "patch", "bank_map.json")

NS_CAT, CAB_CAT = 0x0F, 0x0A
AMP_CATS = (0x07, 0x08)


class SnapTone(TypedDict):
    slot: int
    name: str


class Ir(TypedDict):
    slot: int
    name: str


class Patch(TypedDict):
    slot: int
    name: str
    file: str
    uses_snaptone: bool
    snaptone_slot: int  # N->S slot (0 = none)
    ir_slot: int  # CAB model index
    amp_slot: int  # AMP model index
    snaptone_name: str
    ir_name: str
    amp_name: str


@lru_cache(maxsize=1)
def _ring() -> dict:
    if not os.path.exists(FXID_RING):
        return {}
    return {int(k): v for k, v in json.load(open(FXID_RING)).items()}


def _model_name(category: int, idx: int) -> Optional[str]:
    fxid = (category << 24) | idx
    e = _ring().get(fxid)
    if e:
        return e.get("name") or e.get("fxtitle")
    return None


def _model_block(b: bytes):
    i = b.find(bytes([0x03, 0x30, 0x28, 0x00]))
    if i < 0:
        return []
    val = b[i + 4 : i + 4 + 40]
    return [(val[k * 4], val[k * 4 + 3]) for k in range(10)]


def _patch_name(b: bytes, path: str) -> str:
    nm = b[0x19:0x30].split(b"\0")[0].decode("latin1", "replace").strip()
    return nm or re.sub(r"^\d+-", "", os.path.basename(path)).replace(".prst", "")


def _slot_from_filename(path: str) -> int:
    m = re.match(r"(\d+)-", os.path.basename(path))
    return int(m.group(1)) if m else -1


@lru_cache(maxsize=1)
def _bank_labels() -> dict:
    if os.path.exists(BANK_MAP):
        return {
            int(k): v for k, v in json.load(open(BANK_MAP)).get("snaptone", {}).items()
        }
    return {}


@lru_cache(maxsize=1)
def _load() -> tuple:
    patches: list[Patch] = []
    for path in sorted(glob.glob(os.path.join(EXPORT_DIR, "*.prst"))):
        b = open(path, "rb").read()
        recs = _model_block(b)
        by_cat = {cat: idx for idx, cat in recs}
        ns = next((idx for idx, cat in recs if cat == NS_CAT), 0)
        cab = next((idx for idx, cat in recs if cat == CAB_CAT), 0)
        amp = next((idx for idx, cat in recs if cat in AMP_CATS), 0)
        amp_cat = next((cat for _, cat in recs if cat in AMP_CATS), 0x07)
        patches.append(
            Patch(
                slot=_slot_from_filename(path),
                name=_patch_name(b, path),
                file=os.path.basename(path),
                uses_snaptone=ns != 0,
                snaptone_slot=ns,
                ir_slot=cab,
                amp_slot=amp,
                snaptone_name="",  # filled below
                ir_name=_model_name(CAB_CAT, cab) or f"Cab #{cab}",
                amp_name=_model_name(amp_cat, amp) or f"Amp #{amp}",
            )
        )

    # SnapTone identity: label each used N->S slot by the patches that use it,
    # overridden by authoritative device names from bank_map.json when present.
    dev = _bank_labels()
    used: dict[int, list[str]] = {}
    for p in patches:
        if p["snaptone_slot"]:
            used.setdefault(p["snaptone_slot"], []).append(p["name"])
    snaptones: list[SnapTone] = []
    for slot in sorted(used):
        label = dev.get(slot) or "/".join(sorted(used[slot]))
        snaptones.append(SnapTone(slot=slot, name=label))
    slot_label = {s["slot"]: s["name"] for s in snaptones}
    for p in patches:
        p["snaptone_name"] = (
            slot_label.get(p["snaptone_slot"], "") if p["snaptone_slot"] else ""
        )

    # IR/Cab inventory: every distinct CAB model referenced by a patch.
    irs: list[Ir] = []
    for cab in sorted({p["ir_slot"] for p in patches}):
        irs.append(Ir(slot=cab, name=_model_name(CAB_CAT, cab) or f"Cab #{cab}"))

    return patches, snaptones, irs


def all_patches() -> list[Patch]:
    return list(_load()[0])


def all_snaptones() -> list[SnapTone]:
    return list(_load()[1])


def all_irs() -> list[Ir]:
    return list(_load()[2])


def find_snaptone(slot: int) -> Optional[SnapTone]:
    return next((s for s in all_snaptones() if s["slot"] == slot), None)


def find_ir(slot: int) -> Optional[Ir]:
    return next((i for i in all_irs() if i["slot"] == slot), None)


def patches_using_snaptone(slot: int) -> list[Patch]:
    return [p for p in all_patches() if p["snaptone_slot"] == slot]


def patches_using_ir(slot: int) -> list[Patch]:
    # only amp+cab patches "use" a cab; a SnapTone patch bypasses the CAB block
    return [p for p in all_patches() if p["ir_slot"] == slot and not p["uses_snaptone"]]


def patch_file(slot: int) -> Optional[str]:
    p = next((p for p in all_patches() if p["slot"] == slot), None)
    return os.path.join(EXPORT_DIR, p["file"]) if p else None


# --- clone / edit (features 5/6): repoint a patch's SnapTone, refix the CRC ---

CRC_OFF = 0x14  # byte 0x14 = CRC-8/0x07 over body[0x15:]


def _crc8(data, init=0):
    c = init
    for byte in data:
        c ^= byte
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def _model_rec_offset(b: bytes, category: int) -> Optional[int]:
    i = b.find(bytes([0x03, 0x30, 0x28, 0x00]))
    if i < 0:
        return None
    base = i + 4
    for k in range(10):
        if b[base + k * 4 + 3] == category:
            return base + k * 4
    return None


def clone_with_snaptone(patch_slot: int, target_ns_slot: int) -> tuple[str, bytes]:
    """Return (filename, .prst bytes) for `patch_slot` repointed at N->S
    `target_ns_slot`. One index byte changed + CRC refixed. Raises on bad input."""
    src = patch_file(patch_slot)
    if src is None:
        raise ValueError(f"unknown patch slot {patch_slot}")
    if not (0 <= target_ns_slot <= 79):
        raise ValueError(f"SnapTone slot out of range: {target_ns_slot}")
    b = bytearray(open(src, "rb").read())
    off = _model_rec_offset(b, NS_CAT)
    if off is None:
        raise ValueError(f"patch {patch_slot} has no N->S (SnapTone) block")
    b[off] = target_ns_slot
    b[CRC_OFF] = _crc8(b[CRC_OFF + 1 :])
    label = (find_snaptone(target_ns_slot) or {}).get("name") or f"NS{target_ns_slot}"
    stem = os.path.basename(src).replace(".prst", "")
    safe = re.sub(r"[^A-Za-z0-9]+", "", label)[:12]
    return f"{stem}__{safe}.prst", bytes(b)
