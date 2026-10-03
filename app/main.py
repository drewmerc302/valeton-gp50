"""GP-50 Converter web app.

Minimal FastAPI scaffold (T0). Routers for the convert engine, job status,
and the device-stub screen get mounted here in later tasks. The convert UI
(T3) is a static vanilla HTML/CSS/JS page served from app/static/.
"""

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app import auth
from app.api import router as api_router
from app.api_device import router as device_api_router

STATIC_DIR = Path(__file__).resolve().parent / "static"

# On a hosted backend with no pedal attached (e.g. App Runner), device I/O must
# happen in the browser over WebMIDI. DEVICE_IO_MODE=browser serves the Explorer /
# Device pages with window.__VALETON_STATIC__ set, so static_api.js intercepts the
# device endpoints in-page (bundled snapshot + WebMIDI) — while /api/device/ai/*
# and the converter still hit this backend. Default "server" = local dev with a
# pedal on the machine (server-side MIDI).
def _browser_device_io() -> bool:
    return os.environ.get("DEVICE_IO_MODE", "server").lower() == "browser"


def _page(name: str, allow_static: bool = False):
    """Serve a static HTML page. When allow_static and we're in browser device-I/O
    mode, inject the __VALETON_STATIC__ flag before the first script (same shape as
    scripts/build_static_site.mjs) so static_api.js routes device I/O to WebMIDI."""
    path = STATIC_DIR / name
    if allow_static and _browser_device_io():
        html = path.read_text(encoding="utf-8").replace(
            "<script",
            "<script>window.__VALETON_STATIC__ = true;</script>\n  <script",
            1,
        )
        return HTMLResponse(html)
    return FileResponse(path)

app = FastAPI(title="GP-50 Converter")


@app.middleware("http")
async def no_cache_static(request, call_next):
    """Force the browser to revalidate static assets so CSS/JS edits show up on
    a plain reload instead of serving a stale cached copy."""
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.middleware("http")
async def basic_auth_gate(request, call_next):
    """Gate the whole app behind HTTP Basic when APP_AUTH_PASSWORD is set (the
    hosted backend); a no-op when it isn't (local dev / static build). /health is
    always open so infra health checks pass. Registered last → runs outermost, so
    an unauthorized request is rejected before any handler work."""
    expected = auth.credentials()
    if expected and request.url.path not in auth.OPEN_PATHS:
        if not auth.check_header(request.headers.get("authorization"), expected):
            return Response(status_code=401, headers=auth.challenge_headers())
    return await call_next(request)


router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/")
def index():
    # converter landing — backend-only (runs the NAM engine), never static
    return _page("index.html")


@router.get("/device")
def device_page():
    return _page("device.html", allow_static=True)


@router.get("/explorer")
def explorer_page():
    return _page("explorer.html", allow_static=True)


app.include_router(router)
app.include_router(api_router)
app.include_router(device_api_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
