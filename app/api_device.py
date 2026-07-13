"""Device inventory + patch-clone API.

Reads REAL data from the exported patch set via app.patchlib (the .prst format
is fully reverse-engineered). No live device I/O: everything is parsed from
presetExports/*.prst + the decoded model catalog. The /clone endpoints produce
edited .prst files for the user to re-import through Valeton Suite.
"""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app import blocklib, device_io, patchlib

router = APIRouter(prefix="/api/device")


@router.get("/models/{block}")
def models(block: str) -> dict:
    """Selectable models for a block type (for the model picker), with param defs."""
    return {"block": block, "models": patchlib.models_for_block(block)}


_scan_reloaded = {"pending": False}


@router.post("/scan")
def scan() -> dict:
    """Start a full device preset scan (~60-90s, one preset at a time — no bulk read
    exists). Populates device_scan/ so the Explorer reflects the live device."""
    result = device_io.scan_bank()
    if result.get("ok"):
        _scan_reloaded["pending"] = True
    return result


@router.get("/scan/status")
def scan_status() -> dict:
    """Poll scan progress. When the scan finishes, reload the inventory once so the
    freshly-scanned patches appear."""
    st = device_io.scan_status()
    if _scan_reloaded["pending"] and not st.get("running"):
        patchlib.reload()
        _scan_reloaded["pending"] = False
    return st


@router.post("/sync")
def sync() -> dict:
    """Live-read the SnapTone catalog from the pedal and refresh the inventory.
    Read-only on the device; requires it connected with Valeton Suite closed."""
    result = device_io.sync_snaptones()
    if result.get("ok"):
        patchlib.reload()
    return result


@router.get("/inventory")
def inventory() -> dict:
    return {
        "source": "exported patches (presetExports/) — not a live device read",
        "snaptones": patchlib.all_snaptones(),
        "irs": patchlib.all_irs(),
        "patches": patchlib.all_patches(),
    }


@router.get("/facets")
def facets() -> dict:
    """Active-block filter dimensions for the preset explorer (blocks, types, models)."""
    return patchlib.facets()


@router.get("/usage/snaptone/{slot}")
def usage_snaptone(slot: int) -> dict:
    st = patchlib.find_snaptone(slot)
    if st is None:
        raise HTTPException(404, f"unknown SnapTone slot {slot!r}")
    return {"snaptone": st, "patches": patchlib.patches_using_snaptone(slot)}


@router.get("/usage/ir/{slot}")
def usage_ir(slot: int) -> dict:
    ir = patchlib.find_ir(slot)
    if ir is None:
        raise HTTPException(404, f"unknown IR/cab slot {slot!r}")
    return {"ir": ir, "patches": patchlib.patches_using_ir(slot)}


class CloneRequest(BaseModel):
    patch_slot: int
    snaptone_slots: list[int]


@router.post("/clone")
def clone(req: CloneRequest) -> Response:
    """Clone one patch across N SnapTone slots. Returns a single .prst if one
    target, else a .zip. Each output is CRC-refixed and Suite-importable."""
    if not req.snaptone_slots:
        raise HTTPException(400, "no target SnapTone slots given")
    try:
        outs = [
            patchlib.clone_with_snaptone(req.patch_slot, s) for s in req.snaptone_slots
        ]
    except ValueError as e:
        raise HTTPException(400, str(e))

    if len(outs) == 1:
        fname, data = outs[0]
        return Response(
            data,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, data in outs:
            zf.writestr(fname, data)
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="clones.zip"'},
    )


class EditRequest(BaseModel):
    patch_slot: int
    params: dict[int, dict[int, float]] = {}  # {block_index: {algId: value}}
    bypass: dict[int, bool] = {}  # {block_index: active}
    settings: dict = {}  # {patch_vol, bpm}
    footswitches: dict[str, list[int]] = {}  # {"fs1": [block_idx], "fs2": [...]}
    models: dict[int, int] = {}  # {block_index: fxid} — swap a block's model


class BlockLibEntry(BaseModel):
    name: str
    block: str
    fxid: int
    model_name: str = ""
    params: dict[int, float] = {}


@router.get("/blocklib")
def blocklib_list(block: str | None = None) -> dict:
    return {"entries": blocklib.list_entries(block)}


@router.post("/blocklib")
def blocklib_add(entry: BlockLibEntry) -> dict:
    try:
        return blocklib.add_entry(
            entry.name, entry.block, entry.fxid, entry.model_name, entry.params
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/blocklib/{entry_id}")
def blocklib_delete(entry_id: str) -> dict:
    return {"deleted": blocklib.delete_entry(entry_id)}


class WriteRequest(EditRequest):
    target_slot: int  # device patch index 0..99 to overwrite
    confirm: bool = False  # must be true — the UI sets it after user confirmation


@router.post("/write")
def write_to_device(req: WriteRequest) -> dict:
    """Apply edits, then write the resulting patch DIRECTLY to the pedal at
    target_slot and verify by read-back. Overwrites that slot. Requires confirm=True.
    Uses the validated 0x1D patch-write protocol (see re/DEVICE_WRITE.md)."""
    if not req.confirm:
        raise HTTPException(400, "refusing to write: confirm=true required")
    if not 0 <= req.target_slot <= 99:
        raise HTTPException(400, f"target_slot {req.target_slot} out of range (0..99)")
    try:
        _, data = patchlib.apply_edits(
            req.patch_slot,
            {
                "params": req.params,
                "bypass": req.bypass,
                "settings": req.settings,
                "footswitches": req.footswitches,
                "models": req.models,
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    result = device_io.write_patch(data, req.target_slot)
    if result.get("ok"):
        patchlib.reload()  # inventory may have changed on the device
    return result


@router.post("/edit")
def edit(req: EditRequest) -> Response:
    """Apply parameter / bypass / patch-setting edits and return the edited .prst
    for the user to re-import via Suite. This NEVER writes to the device."""
    try:
        fname, data = patchlib.apply_edits(
            req.patch_slot,
            {
                "params": req.params,
                "bypass": req.bypass,
                "settings": req.settings,
                "footswitches": req.footswitches,
                "models": req.models,
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(
        data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
