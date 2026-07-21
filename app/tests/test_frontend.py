"""Frontend serving smoke tests (T3).

Doesn't drive the UI (that's the headless e2e in T5) — just confirms the
page and its static assets are actually wired up and reachable, and that
the key DOM hooks a click-through test would need are present.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_serves_html_with_key_hooks():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text
    for hook in (
        'id="prst-drop"',
        'id="prst-target"',
        'id="prst-convert-btn"',
    ):
        assert hook in html, f"missing hook: {hook}"


def test_convert_page_shows_preset_tool_and_nam_placeholder():
    """CONV-1: the page is the GP-5<->GP-50 preset converter now — the NAM
    (A2->A1) form is gone, replaced by a placeholder pointing at its future
    standalone repo (CONV-2)."""
    html = client.get("/").text
    for hook in (
        'id="prst-drop"',
        'id="prst-target"',
        'id="prst-convert-btn"',
        "convert_prst.js",
    ):
        assert hook in html, f"missing convert hook: {hook}"
    assert "Preset Converter" in html
    assert "own repo" in html  # NAM placeholder copy
    # the NAM conversion form itself is gone from this page
    for hook in (
        'id="drop-zone"',
        'id="file-input"',
        'id="format-toggle"',
        'id="convert-btn"',
    ):
        assert hook not in html, f"stale NAM hook still present: {hook}"


def test_static_app_js_served():
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert "/api/jobs" in resp.text


def test_static_style_css_served():
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]
