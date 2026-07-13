"""GP-50 Converter web app.

Minimal FastAPI scaffold (T0). Routers for the convert engine, job status,
and the device-stub screen get mounted here in later tasks. The convert UI
(T3) is a static vanilla HTML/CSS/JS page served from app/static/.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.api_device import router as device_api_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="GP-50 Converter")

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/device", response_class=FileResponse)
def device_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "device.html")


app.include_router(router)
app.include_router(api_router)
app.include_router(device_api_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
