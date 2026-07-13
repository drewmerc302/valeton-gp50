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

# blocks in bitmask/model-record order (bit i = block i active)
BLOCK_NAMES = ["NR", "PRE", "DST", "AMP", "CAB", "EQ", "MOD", "DLY", "RVB", "N->S"]


class SnapTone(TypedDict):
    slot: int
    name: str


class Ir(TypedDict):
    slot: int  # CAB model index (fxid low bytes); user IRs use the 0x10xxxx range
    name: str
    type: str
    is_user_ir: bool
    used: int  # how many patches reference it


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
    blocks: list  # per-block detail (see _blocks_for)


@lru_cache(maxsize=1)
def _ring() -> dict:
    if not os.path.exists(FXID_RING):
        return {}
    return {int(k): v for k, v in json.load(open(FXID_RING)).items()}


def _model_entry(category: int, fxlow: int) -> Optional[dict]:
    return _ring().get((category << 24) | fxlow)


def _model_name(category: int, fxlow: int) -> Optional[str]:
    e = _model_entry(category, fxlow)
    return (e.get("name") or e.get("fxtitle")) if e else None


@lru_cache(maxsize=1)
def _multi_type_blocks() -> frozenset:
    """blocks whose model catalog spans >1 type (so the type adds info, e.g.
    DST -> OD/Fuzz/Distortion). RVB/DLY/EQ/NR have one type -> omit it."""
    by_block: dict[str, set] = {}
    for e in _ring().values():
        by_block.setdefault(e.get("module"), set()).add(e.get("type"))
    return frozenset(b for b, ts in by_block.items() if len(ts) > 1)


def _model_block(b: bytes):
    """Per-block model record = [b0][b1][b2][category]. Returns (idx, cat, fxlow):
    idx = b0 (the slot/index for N->S and AMP), cat = category, and fxlow = the
    full 3-byte little-endian model index (b0|b1<<8|b2<<16) used to resolve names.
    Factory models have b1=b2=0 (fxlow==idx); User IRs set b2 (fxid 0x0A10xxxx)."""
    i = b.find(bytes([0x03, 0x30, 0x28, 0x00]))
    if i < 0:
        return []
    val = b[i + 4 : i + 4 + 40]
    out = []
    for k in range(10):
        r = val[k * 4 : k * 4 + 4]
        fxlow = r[0] | (r[1] << 8) | (r[2] << 16)
        out.append((r[0], r[3], fxlow))
    return out


def _bypass_mask(b: bytes) -> int:
    """u32 bitmask (record id=1 grp=0x30): bit k = block k active (BLOCK_NAMES order)."""
    i = b.find(bytes([0x01, 0x30, 0x04, 0x00]))
    return struct.unpack_from("<I", b, i + 4)[0] if i >= 0 else 0


def _blocks_for(b: bytes, ns_label: dict) -> list[dict]:
    """Per-block detail: name, active flag, model type + model, and a display
    label 'BLOCK · Type · Model' (type omitted for single-type blocks)."""
    mask = _bypass_mask(b)
    recs = _model_block(b)
    out = []
    for k, block in enumerate(BLOCK_NAMES):
        idx, cat, fxlow = recs[k] if k < len(recs) else (0, 0, 0)
        if block == "N->S":
            model = ns_label.get(idx) if idx else None
            btype = "SnapTone"
        else:
            e = _model_entry(cat, fxlow)
            model = (e.get("name") or e.get("fxtitle")) if e else None
            btype = e.get("type") if e else None
        parts = [block]
        if btype and block in _multi_type_blocks():
            parts.append(btype)
        if model:
            parts.append(model)
        out.append(
            {
                "block": block,
                "active": bool(mask >> k & 1),
                "type": btype,
                "model": model,
                "index": idx,
                "label": " · ".join(parts),
            }
        )
    return out


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
    raw: dict[int, bytes] = {}
    for path in sorted(glob.glob(os.path.join(EXPORT_DIR, "*.prst"))):
        b = open(path, "rb").read()
        recs = _model_block(b)
        ns = next((idx for idx, cat, _ in recs if cat == NS_CAT), 0)
        cab = next((fx for _, cat, fx in recs if cat == CAB_CAT), 0)
        amp = next((fx for _, cat, fx in recs if cat in AMP_CATS), 0)
        amp_cat = next((cat for _, cat, _ in recs if cat in AMP_CATS), 0x07)
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
                blocks=[],  # filled below (needs the SnapTone slot->name map)
            )
        )
        raw[patches[-1]["slot"]] = b

    # SnapTone identity: union of (slots referenced by patches) and (all populated
    # device slots from bank_map.json). Device names are authoritative; slots that
    # no patch references (orphans) still appear so they can be clone targets.
    dev = _bank_labels()
    used: dict[int, list[str]] = {}
    for p in patches:
        if p["snaptone_slot"]:
            used.setdefault(p["snaptone_slot"], []).append(p["name"])
    snaptones: list[SnapTone] = []
    for slot in sorted(set(used) | set(dev)):
        label = dev.get(slot) or "/".join(sorted(used[slot]))
        snaptones.append(SnapTone(slot=slot, name=label))
    slot_label = {s["slot"]: s["name"] for s in snaptones}
    for p in patches:
        p["snaptone_name"] = (
            slot_label.get(p["snaptone_slot"], "") if p["snaptone_slot"] else ""
        )
        p["blocks"] = _blocks_for(raw[p["slot"]], slot_label)

    # IR/Cab inventory: the FULL catalog (factory cabs + all User IR slots),
    # not just what patches happen to reference. Sorted factory-first, then
    # User IRs; each carries a usage count for the inspector.
    use_count: dict[int, int] = {}
    for p in patches:
        if not p["uses_snaptone"]:  # SnapTone patches bypass the CAB block
            use_count[p["ir_slot"]] = use_count.get(p["ir_slot"], 0) + 1
    irs: list[Ir] = []
    for fxid, e in _ring().items():
        if e.get("module") != "CAB":
            continue
        fxlow = fxid & 0xFFFFFF
        is_user = "User IR" in (e.get("name") or "")
        irs.append(
            Ir(
                slot=fxlow,
                name=e.get("name") or e.get("fxtitle") or f"Cab #{fxlow}",
                type=e.get("type") or "",
                is_user_ir=is_user,
                used=use_count.get(fxlow, 0),
            )
        )
    irs.sort(key=lambda i: (i["is_user_ir"], i["slot"]))

    return patches, snaptones, irs


def all_patches() -> list[Patch]:
    return list(_load()[0])


def facets() -> dict:
    """Distinct active-block dimensions for the explorer's filters:
    which blocks are used, and per block the set of types and models seen."""
    blocks: dict[str, dict] = {}
    for p in all_patches():
        for blk in p["blocks"]:
            if not blk["active"]:
                continue
            d = blocks.setdefault(blk["block"], {"types": set(), "models": set()})
            if blk["type"]:
                d["types"].add(blk["type"])
            if blk["model"]:
                d["models"].add(blk["model"])
    order = {b: i for i, b in enumerate(BLOCK_NAMES)}
    return {
        "blocks": [
            {
                "block": b,
                "types": sorted(blocks[b]["types"]),
                "models": sorted(blocks[b]["models"]),
            }
            for b in sorted(blocks, key=lambda x: order.get(x, 99))
        ]
    }


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
