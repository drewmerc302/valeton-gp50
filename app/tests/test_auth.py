"""HTTP Basic Auth gate — enabled only when APP_AUTH_PASSWORD is set.

The gate protects the hosted backend (pages + the costly Bedrock AI endpoint).
Disabled by default so local dev and the static build are unaffected.
"""

import base64

from fastapi.testclient import TestClient

from app import auth
from app.main import app

client = TestClient(app)

PW = "s3cr3t-c0mplex-p@ss"


def _basic(user, pw):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


# ── gate disabled (default) ──────────────────────────────────────────────────


def test_no_gate_when_password_unset(monkeypatch):
    monkeypatch.delenv("APP_AUTH_PASSWORD", raising=False)
    assert client.get("/explorer").status_code == 200
    assert client.get("/health").status_code == 200


# ── gate enabled ─────────────────────────────────────────────────────────────


def test_gate_blocks_without_credentials(monkeypatch):
    monkeypatch.setenv("APP_AUTH_PASSWORD", PW)
    r = client.get("/explorer")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"].startswith("Basic ")


def test_gate_allows_correct_credentials(monkeypatch):
    monkeypatch.setenv("APP_AUTH_PASSWORD", PW)
    r = client.get("/explorer", headers=_basic("valeton", PW))
    assert r.status_code == 200


def test_gate_rejects_wrong_password(monkeypatch):
    monkeypatch.setenv("APP_AUTH_PASSWORD", PW)
    assert client.get("/explorer", headers=_basic("valeton", "nope")).status_code == 401


def test_gate_custom_username(monkeypatch):
    monkeypatch.setenv("APP_AUTH_PASSWORD", PW)
    monkeypatch.setenv("APP_AUTH_USER", "igor")
    assert client.get("/explorer", headers=_basic("igor", PW)).status_code == 200
    assert client.get("/explorer", headers=_basic("valeton", PW)).status_code == 401


def test_gate_covers_ai_endpoint(monkeypatch):
    """The whole point: the Bedrock endpoint must not be reachable unauthenticated."""
    monkeypatch.setenv("APP_AUTH_PASSWORD", PW)
    assert client.get("/api/device/ai/status").status_code == 401
    assert client.get("/api/device/ai/status", headers=_basic("valeton", PW)).status_code == 200


def test_health_stays_open_under_gate(monkeypatch):
    """Infra health checks (ALB HTTP /health) must pass without credentials."""
    monkeypatch.setenv("APP_AUTH_PASSWORD", PW)
    assert client.get("/health").status_code == 200


# ── check_header unit ────────────────────────────────────────────────────────


def test_check_header_edge_cases():
    exp = ("valeton", PW)
    assert auth.check_header(None, exp) is False
    assert auth.check_header("Bearer x", exp) is False
    assert auth.check_header("Basic !!!not-base64!!!", exp) is False
    assert auth.check_header("Basic " + base64.b64encode(b"no-colon").decode(), exp) is False
    good = "Basic " + base64.b64encode(f"valeton:{PW}".encode()).decode()
    assert auth.check_header(good, exp) is True
