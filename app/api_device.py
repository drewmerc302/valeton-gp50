"""Device inventory + patch-clone API.

Reads REAL data from the exported patch set via app.patchlib (the .prst format
is fully reverse-engineered). No live device I/O: everything is parsed from
presetExports/*.prst + the decoded model catalog. The /clone endpoints produce
edited .prst files for the user to re-import through Valeton Suite.
"""

from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app import blocklib, device_io, patchlib, templates_store
from patch import convert as prst_convert
from patch import prst_format

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


@router.get("/status")
def status() -> dict:
    """Is a Valeton device connected right now, and which one? Read-only; the
    Explorer uses this to decide whether clicking a preset selects it on the pedal."""
    return device_io.device_status()


class SelectRequest(BaseModel):
    slot: int  # device preset index 0..99


@router.post("/select")
def select(req: SelectRequest) -> dict:
    """Select preset `slot` on the connected device (MIDI Program Change) and pull
    its live state back into that slot's cache. Non-destructive — changes the active
    patch, writes nothing to the device. Needs a device connected."""
    result = device_io.select_patch(req.slot)
    if result.get("cache_updated"):
        patchlib.reload()  # so the next /inventory reflects the freshly-read slot
    return result


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
        "device": patchlib.device(),  # {key, name, usb_pid, prst_len} — detected
        "snaptones": patchlib.all_snaptones(),
        "irs": patchlib.all_irs(),
        "patches": patchlib.all_patches(),
        # slot domains, so no frontend re-derives ranges or sentinels
        "domains": {
            "patch_slots": [0, patchlib.PATCH_SLOT_MAX],
            "snaptone_slots": [0, patchlib.SNAPTONE_SLOT_MAX],
            "user_snaptone_slots": [
                patchlib.USER_SNAPTONE_START,
                patchlib.SNAPTONE_SLOT_MAX,
            ],
            "user_ir_base": patchlib.USER_IR_BASE,
        },
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
    name: str | None = None  # rename the patch (16-char device limit)
    order: list[int] | None = (
        None  # chain order: permutation of 0..9 model-record indices
    )


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


# --- patch templates: save a whole effects chain, build a patch from a capture ---


class TemplateFromPatch(BaseModel):
    name: str
    source_slot: int


@router.get("/templates")
def templates_list() -> dict:
    return {"templates": templates_store.list_entries()}


@router.post("/templates/from-patch")
def templates_from_patch(req: TemplateFromPatch) -> dict:
    """Save device patch `source_slot`'s full effects chain as a named template."""
    try:
        return templates_store.add_from_patch(req.name, req.source_slot)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/templates/{template_id}")
def templates_delete(template_id: str) -> dict:
    return {"deleted": templates_store.delete_entry(template_id)}


class BuildRequest(BaseModel):
    template_id: str
    snaptone_slot: int
    target_slot: int | None = None  # required when writing to the device
    name: str | None = None  # patch name; defaults to the SnapTone's name
    confirm: bool = False  # required for a device write
    download: bool = False  # true -> return the .prst instead of writing
    allow_unverified: bool = False  # override the GP-5 unverified-write gate


@router.post("/build", response_model=None)
def build(req: BuildRequest) -> Response | dict:
    """Build a patch from a template + a SnapTone: stamp the template's effects
    chain onto the chosen capture (repoint N->S, refix CRC). With download=true,
    return the .prst. Otherwise write it to target_slot on the pedal (confirm=true)."""
    body = templates_store.body_of(req.template_id)
    if body is None:
        raise HTTPException(404, f"unknown template {req.template_id!r}")
    st = patchlib.find_snaptone(req.snaptone_slot)
    name = req.name or (st or {}).get("name") or f"NS{req.snaptone_slot}"
    try:
        prst = patchlib.repoint_snaptone_body(body, req.snaptone_slot, name=name)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if req.download:
        safe = "".join(c for c in name if c.isalnum()) or "patch"
        return Response(
            prst,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe}.prst"'},
        )

    if not req.confirm:
        raise HTTPException(400, "refusing to write: confirm=true required")
    if req.target_slot is None or not 0 <= req.target_slot <= patchlib.PATCH_SLOT_MAX:
        raise HTTPException(400, "target_slot 0..99 required to write to the device")
    result = device_io.write_patch(
        prst, req.target_slot, allow_unverified=req.allow_unverified
    )
    if result.get("ok"):
        patchlib.reload()
    return result


class WriteRequest(EditRequest):
    target_slot: int  # device patch index 0..99 to overwrite
    confirm: bool = False  # must be true — the UI sets it after user confirmation
    allow_unverified: bool = False  # override the GP-5 unverified-write gate


@router.post("/write")
def write_to_device(req: WriteRequest) -> dict:
    """Apply edits, then write the resulting patch DIRECTLY to the pedal at
    target_slot and verify by read-back. Overwrites that slot. Requires confirm=True.
    Uses the validated 0x1D patch-write protocol (see re/DEVICE_WRITE.md)."""
    if not req.confirm:
        raise HTTPException(400, "refusing to write: confirm=true required")
    if not 0 <= req.target_slot <= patchlib.PATCH_SLOT_MAX:
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
                "name": req.name,
                "order": req.order,
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    result = device_io.write_patch(
        data, req.target_slot, allow_unverified=req.allow_unverified
    )
    if result.get("ok"):
        patchlib.reload()  # inventory may have changed on the device
    return result


class SwapRequest(BaseModel):
    slot_a: int
    slot_b: int
    confirm: bool = False
    allow_unverified: bool = False  # override the GP-5 unverified-write gate


@router.post("/swap")
def swap(req: SwapRequest) -> dict:
    """Swap two device slots (A<->B), non-destructive. Reads both bodies first, then
    writes each into the other's slot. Requires confirm=True."""
    if not req.confirm:
        raise HTTPException(400, "refusing to swap: confirm=true required")
    if req.slot_a == req.slot_b:
        raise HTTPException(400, "pick two different slots")
    fa, fb = patchlib.patch_file(req.slot_a), patchlib.patch_file(req.slot_b)
    if not fa or not fb:
        raise HTTPException(404, "one or both slots are not in the inventory")
    body_a, body_b = open(fa, "rb").read(), open(fb, "rb").read()  # read both up front
    r1 = device_io.write_patch(
        body_a, req.slot_b, allow_unverified=req.allow_unverified
    )
    if not r1.get("ok"):
        return {
            "ok": False,
            "error": f"swap aborted before any change: {r1.get('error')}",
        }
    r2 = device_io.write_patch(
        body_b, req.slot_a, allow_unverified=req.allow_unverified
    )
    patchlib.reload()
    if not r2.get("ok"):
        return {
            "ok": False,
            "error": f"HALF-SWAPPED: slot {req.slot_b} updated but slot {req.slot_a} "
            f"write failed ({r2.get('error')}). Re-run to finish.",
        }
    return {"ok": True, "slot_a": req.slot_a, "slot_b": req.slot_b}


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
                "name": req.name,
                "order": req.order,
            },
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(
        data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# --- GP-5 <-> GP-50 preset conversion --------------------------------------------


def _target_for(source_key: str, target: str) -> str:
    """Resolve target='auto' to the opposite device of the source."""
    if target == "auto":
        return "gp5" if source_key == "gp50" else "gp50"
    return target


@router.post("/convert/inspect")
async def convert_inspect(
    files: list[UploadFile] = File(...),
    target: str = Form("auto"),
) -> dict:
    """Detect each uploaded .prst's device and report what a conversion WOULD do
    (target device + any blocks with no equivalent). Returns no file data — the UI
    uses this to preview a batch before committing."""
    out = []
    for f in files:
        data = await f.read()
        try:
            src = prst_format.detect(data)
        except ValueError as e:
            out.append({"name": f.filename, "ok": False, "error": str(e)})
            continue
        tgt_key = _target_for(src.key, target)
        problems = prst_convert.check_convertible(data, tgt_key)
        out.append(
            {
                "name": f.filename,
                "ok": True,
                "source_key": src.key,
                "source_name": src.name,
                "patch_name": prst_format.read_name(data),
                "target_key": tgt_key,
                "target_name": prst_format.profile_for(tgt_key).name,
                "same_device": src.key == tgt_key,
                "problems": [
                    {"block_index": p.block_index, "model": p.model} for p in problems
                ],
            }
        )
    return {"files": out}


@router.post("/convert")
async def convert_prst(
    files: list[UploadFile] = File(...),
    target: str = Form("auto"),
    force: bool = Form(False),
) -> Response:
    """Convert uploaded .prst files between GP-5 and GP-50. target='auto' sends each
    file to the opposite device. One file -> a .prst; many -> a .zip. A lossy
    GP-50 -> GP-5 (a GP-50-only model) is refused with 400 unless force=true."""
    if target not in ("auto", "gp5", "gp50"):
        raise HTTPException(400, f"bad target {target!r} (auto|gp5|gp50)")
    outs: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read()
        try:
            src = prst_format.detect(data)
            tgt_key = _target_for(src.key, target)
            conv = prst_convert.convert(data, tgt_key, force=force)
        except (ValueError, prst_convert.ConversionError) as e:
            raise HTTPException(400, f"{f.filename}: {e}")
        stem = (f.filename or "patch").rsplit("/", 1)[-1]
        if stem.lower().endswith(".prst"):
            stem = stem[:-5]
        tgt_name = prst_format.profile_for(tgt_key).name
        outs.append((f"{stem}__{tgt_name}.prst", conv))

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
        headers={"Content-Disposition": 'attachment; filename="converted.zip"'},
    )
