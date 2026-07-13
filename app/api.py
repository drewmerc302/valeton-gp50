"""Batch conversion job API (T2).

POST /api/jobs launches a background conversion (engine.run_job) and returns
immediately with a job_id; GET endpoints poll the in-memory job store. Real
conversions take minutes and shell out to subprocesses, so they MUST NOT run
on the request thread — see `job_executor` below.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Callable, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import engine
from app.engine import ConvertJob, FileState

router = APIRouter(prefix="/api")

WORK_DIR = engine.PROJECT_ROOT / "work" / "jobs"

# job_id -> ConvertJob. Mutations to this dict (inserts) are guarded by
# _jobs_lock; FileState mutations inside a job happen in place on the
# background thread and are read without locking (stale-by-a-poll is fine).
_jobs: Dict[str, ConvertJob] = {}
_jobs_lock = threading.Lock()


def _run_and_isolate(job: ConvertJob) -> None:
    def _progress_cb(state: FileState) -> None:
        # FileState objects live in job.files, which GET handlers read
        # directly, so there's nothing else to update here.
        pass

    try:
        engine.run_job(job, _progress_cb)
    except Exception as e:
        # Job-level misconfiguration (bad output_format, missing venv/DI)
        # raises before any per-file work starts; surface it on every file
        # rather than leaving them stuck at 'queued'.
        for state in job.files:
            if state.status not in ("done", "failed"):
                state.status = "failed"
                state.error = f"job failed: {e}"


def _background_executor(job: ConvertJob) -> None:
    threading.Thread(target=_run_and_isolate, args=(job,), daemon=True).start()


# Swappable so tests can run job execution synchronously and hermetically
# (no threads, no subprocesses) by monkeypatching this name.
job_executor: Callable[[ConvertJob], None] = _background_executor


def _get_job_or_404(job_id: str) -> ConvertJob:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"unknown job_id {job_id!r}")
    return job


@router.post("/jobs")
async def create_job(
    files: List[UploadFile] = File(...),
    epochs: int = Form(100),
    output_format: str = Form("0.5x"),
    di: str = Form("default"),
) -> dict:
    if not files:
        raise HTTPException(400, "no files uploaded")
    for f in files:
        if not (f.filename or "").lower().endswith(".nam"):
            raise HTTPException(400, f"not a .nam file: {f.filename!r}")

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    in_dir = job_dir / "in"
    out_dir = job_dir / "out"
    in_dir.mkdir(parents=True, exist_ok=True)

    input_paths = []
    for f in files:
        dest = in_dir / Path(f.filename).name  # basename only, no path traversal
        dest.write_bytes(await f.read())
        input_paths.append(dest)

    # MVP: custom DI upload is out of scope (see MVP_REQUIREMENTS.md); the
    # `di` field is accepted for forward-compat but always resolves to the
    # default reference DI.
    job = ConvertJob(
        input_paths=input_paths,
        di_path=engine.DEFAULT_DI,
        epochs=epochs,
        output_format=output_format,
        out_dir=out_dir,
    )

    with _jobs_lock:
        _jobs[job_id] = job

    job_executor(job)

    return {
        "job_id": job_id,
        "files": [{"name": s.name, "status": s.status} for s in job.files],
    }


@router.get("/jobs")
def list_jobs() -> dict:
    with _jobs_lock:
        items = list(_jobs.items())
    jobs = []
    for job_id, job in items:
        counts: Dict[str, int] = {}
        for s in job.files:
            counts[s.status] = counts.get(s.status, 0) + 1
        jobs.append({"job_id": job_id, "total": len(job.files), "counts": counts})
    return {"jobs": jobs}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = _get_job_or_404(job_id)
    return {
        "job_id": job_id,
        "output_format": job.output_format,
        "epochs": job.epochs,
        "files": [
            {
                "name": s.name,
                "status": s.status,
                "progress": s.progress,
                "esr": s.esr,
                "format_ok": s.format_ok,
                "error": s.error,
                "src_arch": s.src_arch,
                "output_available": bool(s.output_path)
                and Path(s.output_path).exists(),
            }
            for s in job.files
        ],
    }


@router.get("/jobs/{job_id}/download/{name}")
def download(job_id: str, name: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    safe_name = Path(name).name
    if safe_name.endswith(".nam"):
        safe_name = safe_name[: -len(".nam")]

    state = next((s for s in job.files if s.name == safe_name), None)
    if state is None or state.status != "done" or not state.output_path:
        raise HTTPException(404, f"output not available for {name!r}")

    out_path = Path(state.output_path)
    if not out_path.exists():
        raise HTTPException(404, f"output file missing for {name!r}")

    return FileResponse(
        out_path, filename=f"{safe_name}.nam", media_type="application/octet-stream"
    )
