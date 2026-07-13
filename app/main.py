"""GP-50 Converter web app.

Minimal FastAPI scaffold (T0). Routers for the convert engine, job status,
and the device-stub screen get mounted here in later tasks.
"""

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse

from app.api import router as api_router

app = FastAPI(title="GP-50 Converter")

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return (
        "<!doctype html><html><head><title>GP-50 Converter</title></head>"
        "<body><h1>GP-50 Converter</h1></body></html>"
    )


app.include_router(router)
app.include_router(api_router)
