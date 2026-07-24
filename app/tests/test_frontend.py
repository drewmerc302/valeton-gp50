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


def test_convert_page_shows_preset_tool_and_nam_converter():
    """CONV-1: the page hosts both the GP-5<->GP-50 preset converter and the NAM
    A2->A1 distiller (drop zone + live progress + cancel), driven by app.js."""
    html = client.get("/").text
    for hook in (
        'id="prst-drop"',
        'id="prst-target"',
        'id="prst-convert-btn"',
        "convert_prst.js",
    ):
        assert hook in html, f"missing preset-convert hook: {hook}"
    assert "Preset Converter" in html
    # the NAM A2->A1 form is present and wired to app.js
    for hook in (
        'id="drop-zone"',
        'id="file-input"',
        'id="convert-btn"',
        'id="cancel-btn"',
        'id="epochs"',
        'class="epoch-preset"',
        'class="epoch-guide"',
        "app.js",
    ):
        assert hook in html, f"missing NAM-convert hook: {hook}"
    # default epochs preset is Standard (60)
    assert 'id="epochs" type="number" min="1" max="1000" value="60"' in html


def test_static_app_js_served():
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert "/api/jobs" in resp.text


def test_static_style_css_served():
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]
