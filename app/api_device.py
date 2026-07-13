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

from app import patchlib

router = APIRouter(prefix="/api/device")


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
