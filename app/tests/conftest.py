"""Shared fixtures for the test suite.

`live_server` is only used by the slow, real-browser e2e test
(test_e2e.py) — it launches the actual app (uvicorn + app.main:app) as a
subprocess against a real free port, so a real headless browser can drive
it over HTTP. The fast suite (TestClient-based) does not use this fixture.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server():
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        deadline = time.time() + 30
        ready = False
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(
                    f"app server exited early (rc={proc.returncode}):\n{out}"
                )
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except OSError:
                pass
            time.sleep(0.25)

        if not ready:
            proc.terminate()
            raise RuntimeError(
                f"app server did not become healthy at {base_url}/health within 30s"
            )

        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
