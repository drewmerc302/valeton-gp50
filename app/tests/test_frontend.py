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
        'id="drop-zone"',
        'id="file-input"',
        'id="format-toggle"',
        'id="format-05x"',
        'id="format-070"',
        'id="epochs"',
        'id="convert-btn"',
        'id="results-section"',
        'id="results"',
    ):
        assert hook in html, f"missing hook: {hook}"


def test_format_070_present_but_disabled():
    html = client.get("/").text
    assert 'id="format-070"' in html
    # order-independent check that the 0.7.0 radio carries disabled
    start = html.index('id="format-070"')
    tag_end = html.index(">", start)
    assert "disabled" in html[start:tag_end]


def test_static_app_js_served():
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert "/api/jobs" in resp.text


def test_static_style_css_served():
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]
