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
SCAN_DIR = os.path.join(PROJECT_ROOT, "device_scan")  # populated by a live device scan
FXID_RING = os.path.join(PROJECT_ROOT, "patch", "fxid_ring.json")
BANK_MAP = os.path.join(PROJECT_ROOT, "patch", "bank_map.json")


def _source_dir() -> str:
    """Prefer a fresh device scan (device_scan/) over manual Suite exports."""
    if glob.glob(os.path.join(SCAN_DIR, "*.prst")):
        return SCAN_DIR
    return EXPORT_DIR


NS_CAT, CAB_CAT = 0x0F, 0x0A
AMP_CATS = (0x07, 0x08)

# blocks in bitmask/model-record order (bit i = block i active)
BLOCK_NAMES = ["NR", "PRE", "DST", "AMP", "CAB", "EQ", "MOD", "DLY", "RVB", "N->S"]
USER_IR_BASE = 0x100000  # CAB fxlow >= this => a User IR slot (0x0A10xxxx fxid)


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
    settings: dict  # patch-level settings (patch_vol, bpm)


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


def _patch_settings(b: bytes) -> dict:
    """Patch-level settings from the group-0x20 records. id=1 Patch VOL, id=2 BPM
    are confirmed against hardware; ids 3-10 (EXP / footswitch assignments) are
    not yet decoded (need multi-preset diffs) so are omitted rather than guessed."""
    out = {}
    i = 0x55
    while i + 4 <= len(b) and b[i + 1] == 0x20:
        rid = b[i]
        ln = struct.unpack_from("<H", b, i + 2)[0]
        if ln not in (1, 2, 4):
            break
        val = struct.unpack_from("<i", b[i + 4 : i + 4 + ln].ljust(4, b"\0"))[0]
        if rid == 0x01:
            out["patch_vol"] = val
        elif rid == 0x02:
            out["bpm"] = val
        i += 4 + ln
    fs1, fs2 = _footswitches(b)
    out["fs1"] = fs1
    out["fs2"] = fs2
    return out


FS_TRAILER = bytes([0x03, 0x00, 0x0A, 0x00])  # id=3 grp=0 len=10 trailer record


def _fs_offset(b: bytes) -> int:
    """Offset of the FS mask pair in the trailer ([FS1 u32][FS2 u32][2 bytes])."""
    i = b.rfind(FS_TRAILER)
    return i + 4 if i >= 0 else -1


def _footswitches(b: bytes):
    """Footswitch assignments -> (fs1_blocks, fs2_blocks) as block-index lists.
    Each is a 10-bit block bitmask (<=2 bits); trailer record id=3 grp=0."""
    off = _fs_offset(b)
    if off < 0:
        return [], []
    a = struct.unpack_from("<I", b, off)[0]
    c = struct.unpack_from("<I", b, off + 4)[0]
    return (
        [i for i in range(10) if a >> i & 1],
        [i for i in range(10) if c >> i & 1],
    )


def _param_floats(b: bytes) -> list:
    """The 80-float parameter array (record id=4 grp=0x30, len 0x140) = 10 blocks
    x 8 float32 slots. A param's value = floats[block_index*8 + algId]."""
    i = b.find(bytes([0x04, 0x30, 0x40, 0x01]))
    if i < 0:
        return [0.0] * 80
    return list(struct.unpack_from("<80f", b, i + 4))


def _fmt_param(value: float, toggle: bool, unit: str) -> str:
    if toggle:
        return "On" if round(value) != 0 else "Off"
    v = str(int(round(value))) if abs(value - round(value)) < 1e-4 else f"{value:.2f}"
    return f"{v} {unit}".strip() if unit else v


def _params_for(entry: Optional[dict], floats: list, block_index: int) -> list:
    if not entry:
        return []
    out = []
    base = block_index * 8
    for p in entry.get("params") or []:
        slot = base + p["algId"]
        if slot >= len(floats):
            continue
        val = floats[slot]
        out.append(
            {
                "name": p["name"],
                "value": round(val, 2),
                "display": _fmt_param(val, p["toggle"], p.get("unit", "")),
                "toggle": p["toggle"],
                "unit": p.get("unit", ""),
                "algId": p["algId"],
                "min": p.get("min", 0),
                "max": p.get("max", 100),
                "step": p.get("step", 1),
            }
        )
    return out


def _block_label(block: str, btype: Optional[str], name: Optional[str]) -> str:
    """'BLOCK · Type · Model' — type omitted for single-type blocks or when absent."""
    parts = [block]
    if btype and block in _multi_type_blocks():
        parts.append(btype)
    if name:
        parts.append(name)
    return " · ".join(parts)


def _blocks_for(b: bytes, ns_label: dict) -> list[dict]:
    """Per-block detail: name, active flag, model type + model, and a display
    label 'BLOCK · Type · Model' (type omitted for single-type blocks)."""
    mask = _bypass_mask(b)
    recs = _model_block(b)
    floats = _param_floats(b)
    out = []
    for k, block in enumerate(BLOCK_NAMES):
        idx, cat, fxlow = recs[k] if k < len(recs) else (0, 0, 0)
        official = None
        if block == "N->S":
            e = _model_entry(NS_CAT, idx)  # N->S param defs (Gain/VOL/Bass/Mid/Treble)
            model = ns_label.get(idx) if idx else None
            btype = "SnapTone"
            fxid = (NS_CAT << 24) | idx if idx else 0
        else:
            e = _model_entry(cat, fxlow)
            model = (e.get("name") or e.get("fxtitle")) if e else None
            btype = e.get("type") if e else None
            official = (e.get("origin") or None) if e else None
            if block == "CAB":
                model = _cab_name(fxlow) or model  # prefer real User IR device name
            fxid = (cat << 24) | fxlow if fxlow or cat else 0

        out.append(
            {
                "block": block,
                "active": bool(mask >> k & 1),
                "type": btype,
                "model": model,
                "official": official,  # official gear reference (Green OD -> Ibanez TS808)
                "index": idx,
                "fxid": fxid,  # (cat<<24)|fxlow — current model id (for library/model-swap)
                "label": _block_label(block, btype, model),
                "label_official": _block_label(
                    block, btype, official or model
                ),  # falls back to device name
                "params": _params_for(e, floats, k),
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
def _bank_irs() -> dict:
    """User-IR slot -> real device name (from bank_map.json 'ir'), if synced."""
    if os.path.exists(BANK_MAP):
        return {int(k): v for k, v in json.load(open(BANK_MAP)).get("ir", {}).items()}
    return {}


def _cab_name(fxlow: int) -> Optional[str]:
    """Resolve a CAB reference to a name. Factory cabs via the catalog; User IRs
    prefer the real device name (bank_map) over the generic 'User IR N'."""
    if fxlow >= USER_IR_BASE:
        slot = fxlow - USER_IR_BASE
        return _bank_irs().get(slot) or f"User IR {slot + 1}"
    return _model_name(CAB_CAT, fxlow)


@lru_cache(maxsize=1)
def _load() -> tuple:
    patches: list[Patch] = []
    raw: dict[int, bytes] = {}
    for path in sorted(glob.glob(os.path.join(_source_dir(), "*.prst"))):
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
                ir_name=_cab_name(cab) or f"Cab #{cab}",
                amp_name=_model_name(amp_cat, amp) or f"Amp #{amp}",
                blocks=[],  # filled below (needs the SnapTone slot->name map)
                settings=_patch_settings(b),
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
        # User IRs: prefer the real device name (bank_map) over "User IR N"
        name = _cab_name(fxlow) if is_user else (e.get("name") or e.get("fxtitle"))
        irs.append(
            Ir(
                slot=fxlow,
                name=name or f"Cab #{fxlow}",
                type=e.get("type") or "",
                is_user_ir=is_user,
                used=use_count.get(fxlow, 0),
            )
        )
    irs.sort(key=lambda i: (i["is_user_ir"], i["slot"]))

    return patches, snaptones, irs


def reload() -> None:
    """Drop caches so the next read reflects an updated bank_map.json / exports."""
    _load.cache_clear()
    _bank_labels.cache_clear()
    _bank_irs.cache_clear()


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
            d = blocks.setdefault(blk["block"], {"types": set(), "models": {}})
            if blk["type"]:
                d["types"].add(blk["type"])
            if blk["model"]:
                d["models"][blk["model"]] = {
                    "official": blk.get("official"),
                    "type": blk.get("type"),
                }  # model -> {official|None, type|None}
    order = {b: i for i, b in enumerate(BLOCK_NAMES)}
    return {
        "blocks": [
            {
                "block": b,
                "types": sorted(blocks[b]["types"]),
                # each model carries official + type so the picker can narrow by type
                "models": [
                    {
                        "model": m,
                        "official": blocks[b]["models"][m]["official"],
                        "type": blocks[b]["models"][m]["type"],
                    }
                    for m in sorted(blocks[b]["models"])
                ],
            }
            for b in sorted(blocks, key=lambda x: order.get(x, 99))
        ]
    }


def models_for_block(block: str) -> list[dict]:
    """All selectable models for a block type, for the model picker. Each carries
    its param definitions (name/algId/default/min/max/step/toggle) so the UI can
    apply defaults on selection. N->S lists the device's loaded SnapTones."""
    if block == "N->S":
        ns_params = (_model_entry(NS_CAT, 0) or {}).get("params", [])
        out = []
        for s in all_snaptones():
            out.append(
                {
                    "fxid": (NS_CAT << 24) | s["slot"],
                    "name": s["name"],
                    "official": None,
                    "type": "SnapTone",
                    "label": _block_label(block, "SnapTone", s["name"]),
                    "label_official": _block_label(block, "SnapTone", s["name"]),
                    "params": ns_params,
                }
            )
        return out
    out = []
    for fxid, e in _ring().items():
        if e.get("module") != block:
            continue
        fxlow = fxid & 0xFFFFFF
        name = (
            _cab_name(fxlow) if block == "CAB" else (e.get("name") or e.get("fxtitle"))
        )
        official = e.get("origin") or None
        btype = e.get("type") or ""
        nm = name or f"#{fxlow}"
        out.append(
            {
                "fxid": fxid,
                "name": nm,
                "official": official,
                "type": btype,
                "label": _block_label(block, btype, nm),
                "label_official": _block_label(block, btype, official or nm),
                "params": e.get("params", []),
            }
        )
    out.sort(key=lambda m: (m["fxid"] & 0x100000, m["name"]))  # factory before user IR
    return out


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
    return os.path.join(_source_dir(), p["file"]) if p else None


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


NAME_OFF = 0x19  # 16-byte patch name region prst[0x19:0x29], latin1, null-padded


def set_patch_name(b: bytearray, name: str) -> None:
    """Overwrite the 16-byte patch-name region in place (does NOT refix the CRC)."""
    b[NAME_OFF : NAME_OFF + 16] = name.encode("latin1", "replace")[:16].ljust(16, b"\0")


def repoint_snaptone_body(
    prst: bytes, target_ns_slot: int, name: Optional[str] = None
) -> bytes:
    """Return a full .prst with its N->S (SnapTone) block repointed at
    `target_ns_slot`, optionally renamed, CRC refixed. Works on any 552-byte body
    (a live patch OR a stored template) — this is the shared build engine. Raises
    if the body has no N->S block or the slot is out of range."""
    if len(prst) != 552:
        raise ValueError(f"expected a 552-byte .prst, got {len(prst)}")
    if not (0 <= target_ns_slot <= 79):
        raise ValueError(f"SnapTone slot out of range: {target_ns_slot}")
    b = bytearray(prst)
    off = _model_rec_offset(b, NS_CAT)
    if off is None:
        raise ValueError("patch has no N->S (SnapTone) block to repoint")
    b[off] = target_ns_slot
    if name is not None:
        set_patch_name(b, name)
    b[CRC_OFF] = _crc8(b[CRC_OFF + 1 :])
    return bytes(b)


def apply_edits(patch_slot: int, edits: dict) -> tuple[str, bytes]:
    """Produce an edited .prst (for Suite re-import — never a device write) with
    changed parameter values, block bypass states, and patch VOL/BPM. CRC refixed.

    edits = {
      "params":   {block_index: {algId: value}},   # float param values
      "bypass":   {block_index: bool},              # block on/off
      "settings": {"patch_vol": int, "bpm": int},
    }
    """
    src = patch_file(patch_slot)
    if src is None:
        raise ValueError(f"unknown patch slot {patch_slot}")
    b = bytearray(open(src, "rb").read())

    # 0. block MODEL changes (record 03 30): each block k's model = 4 bytes
    #    [fxlow b0][b1][b2][category]. fxid = (category<<24)|fxlow.
    mb = b.find(bytes([0x03, 0x30, 0x28, 0x00]))
    for blk, fxid in (edits.get("models") or {}).items():
        if mb < 0:
            break
        rec = mb + 4 + int(blk) * 4
        fxid = int(fxid)
        b[rec] = fxid & 0xFF
        b[rec + 1] = (fxid >> 8) & 0xFF
        b[rec + 2] = (fxid >> 16) & 0xFF
        b[rec + 3] = (fxid >> 24) & 0xFF

    # 1. parameter floats (record 04 30, 10 blocks x 8 slots)
    fi = b.find(bytes([0x04, 0x30, 0x40, 0x01]))
    if fi < 0 and edits.get("params"):
        raise ValueError("no parameter array in patch")
    base = fi + 4
    for blk, params in (edits.get("params") or {}).items():
        for alg, value in params.items():
            slot = int(blk) * 8 + int(alg)
            if 0 <= slot < 80:
                struct.pack_into("<f", b, base + slot * 4, float(value))

    # 2. bypass bitmask (record 01 30)
    mi = b.find(bytes([0x01, 0x30, 0x04, 0x00]))
    if mi >= 0 and edits.get("bypass"):
        mask = struct.unpack_from("<I", b, mi + 4)[0]
        for blk, on in edits["bypass"].items():
            bit = 1 << int(blk)
            mask = (mask | bit) if on else (mask & ~bit)
        struct.pack_into("<I", b, mi + 4, mask & 0xFFFFFFFF)

    # 3. patch-level settings (group 0x20 records: id1 VOL 1-byte, id2 BPM 4-byte)
    s = edits.get("settings") or {}
    if s:
        i = 0x55
        while i + 4 <= len(b) and b[i + 1] == 0x20:
            rid = b[i]
            ln = struct.unpack_from("<H", b, i + 2)[0]
            if ln not in (1, 2, 4):
                break
            if rid == 0x01 and "patch_vol" in s and ln == 1:
                b[i + 4] = max(0, min(100, int(s["patch_vol"])))
            elif rid == 0x02 and "bpm" in s and ln == 4:
                struct.pack_into("<i", b, i + 4, int(s["bpm"]))
            i += 4 + ln

    # 4. footswitch assignments (trailer FS1/FS2 masks, <=2 blocks each)
    fs = edits.get("footswitches") or {}
    if fs:
        off = _fs_offset(b)
        if off >= 0:
            for key, slot_off in (("fs1", 0), ("fs2", 4)):
                if key in fs:
                    blocks = list(fs[key])[:2]  # device allows at most 2 per FS
                    mask = 0
                    for bi in blocks:
                        mask |= 1 << int(bi)
                    struct.pack_into("<I", b, off + slot_off, mask)

    b[CRC_OFF] = _crc8(b[CRC_OFF + 1 :])
    stem = os.path.basename(src).replace(".prst", "")
    return f"{stem}__edited.prst", bytes(b)
