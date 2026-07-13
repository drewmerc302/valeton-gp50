"""Fast, hermetic tests for app.api.

job_executor is monkeypatched with a synchronous fake that walks a job's
files straight to 'done' (with a fake esr/format_ok and a dummy output file
on disk) — no threads, no subprocesses, no torch. The job store and work
directory are reset per test so tests never touch the real work/jobs/ dir
or leak state between each other.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import api
from app.main import app

client = TestClient(app)


def _nam_bytes(
    architecture: str = "SlimmableContainer", version: str = "0.7.0"
) -> bytes:
    return json.dumps(
        {
            "version": version,
            "architecture": architecture,
            "config": {"layers": [{"head_size": 8}]},
            "weights": [],
            "sample_rate": 48000,
        }
    ).encode()


def _fake_executor(job) -> None:
    """Synchronous stand-in for the real background executor."""
    job.out_dir.mkdir(parents=True, exist_ok=True)
    for state in job.files:
        state.status = "done"
        state.progress = 1.0
        state.esr = 0.01234
        state.format_ok = True
        state.src_arch = "SlimmableContainer"
        out_path = job.out_dir / f"{state.name}.nam"
        out_path.write_bytes(b"FAKE-A1-NAM-BYTES:" + state.name.encode())
        state.output_path = str(out_path)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_jobs", {})
    monkeypatch.setattr(api, "job_executor", _fake_executor)
    monkeypatch.setattr(api, "WORK_DIR", tmp_path / "jobs")
    yield


def test_create_job_single_file():
    resp = client.post(
        "/api/jobs",
        files={"files": ("capture.nam", _nam_bytes(), "application/octet-stream")},
        data={"epochs": "5", "output_format": "0.5x"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "job_id" in body and body["job_id"]
    assert body["files"] == [{"name": "capture", "status": "done"}]


def test_get_job_status_reaches_done():
    create_resp = client.post(
        "/api/jobs",
        files={"files": ("capture.nam", _nam_bytes(), "application/octet-stream")},
    )
    job_id = create_resp.json()["job_id"]

    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["output_format"] == "0.5x"
    assert body["epochs"] == 100
    assert len(body["files"]) == 1
    f = body["files"][0]
    assert f["name"] == "capture"
    assert f["status"] == "done"
    assert f["esr"] == pytest.approx(0.01234)
    assert f["format_ok"] is True
    assert f["src_arch"] == "SlimmableContainer"
    assert f["output_available"] is True


def test_download_returns_output_bytes():
    create_resp = client.post(
        "/api/jobs",
        files={"files": ("capture.nam", _nam_bytes(), "application/octet-stream")},
    )
    job_id = create_resp.json()["job_id"]

    resp = client.get(f"/api/jobs/{job_id}/download/capture")
    assert resp.status_code == 200
    assert resp.content == b"FAKE-A1-NAM-BYTES:capture"


def test_download_unknown_name_404():
    create_resp = client.post(
        "/api/jobs",
        files={"files": ("capture.nam", _nam_bytes(), "application/octet-stream")},
    )
    job_id = create_resp.json()["job_id"]

    resp = client.get(f"/api/jobs/{job_id}/download/nope")
    assert resp.status_code == 404


def test_non_nam_upload_rejected_400():
    resp = client.post(
        "/api/jobs",
        files={"files": ("capture.txt", b"not a nam file", "text/plain")},
    )
    assert resp.status_code == 400


def test_unknown_job_404():
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404


def test_batch_of_two_files():
    resp = client.post(
        "/api/jobs",
        files=[
            ("files", ("one.nam", _nam_bytes(), "application/octet-stream")),
            ("files", ("two.nam", _nam_bytes(), "application/octet-stream")),
        ],
    )
    assert resp.status_code == 200
    body = resp.json()
    job_id = body["job_id"]
    assert {f["name"] for f in body["files"]} == {"one", "two"}

    status = client.get(f"/api/jobs/{job_id}").json()
    statuses = {f["name"]: f["status"] for f in status["files"]}
    assert statuses == {"one": "done", "two": "done"}

    for name in ("one", "two"):
        dl = client.get(f"/api/jobs/{job_id}/download/{name}")
        assert dl.status_code == 200
        assert dl.content == f"FAKE-A1-NAM-BYTES:{name}".encode()


def test_list_jobs():
    r1 = client.post(
        "/api/jobs",
        files={"files": ("a.nam", _nam_bytes(), "application/octet-stream")},
    )
    job_id = r1.json()["job_id"]

    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert any(j["job_id"] == job_id and j["total"] == 1 for j in jobs)
