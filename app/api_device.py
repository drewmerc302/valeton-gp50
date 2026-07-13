"""Read-only device usage-inspector API (T4).

Serves the MOCK inventory from app.device_stub — see that module's
docstring for the mock-to-real seam. No device I/O of any kind happens
here; this is purely reading an in-memory Python fixture.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import device_stub

router = APIRouter(prefix="/api/device")


@router.get("/inventory")
def inventory() -> dict:
    return {
        "snaptones": device_stub.SNAPTONES,
        "irs": device_stub.IRS,
        "patches": device_stub.PATCHES,
    }


@router.get("/usage/snaptone/{slot}")
def usage_snaptone(slot: int) -> dict:
    snaptone = device_stub.find_snaptone(slot)
    if snaptone is None:
        raise HTTPException(404, f"unknown SnapTone slot {slot!r}")
    return {
        "snaptone": snaptone,
        "patches": device_stub.patches_using_snaptone(slot),
    }


@router.get("/usage/ir/{slot}")
def usage_ir(slot: int) -> dict:
    ir = device_stub.find_ir(slot)
    if ir is None:
        raise HTTPException(404, f"unknown IR slot {slot!r}")
    return {
        "ir": ir,
        "patches": device_stub.patches_using_ir(slot),
    }
