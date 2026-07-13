"""Tests for the read-only device usage-inspector stub (T4).

Everything here is backed by the in-memory MOCK fixture in
app/device_stub.py — no device I/O, no MIDI, no serial. See that module's
docstring for the mock-to-real seam.
"""

from fastapi.testclient import TestClient

from app import device_stub
from app.main import app

client = TestClient(app)


def test_inventory_shape():
    resp = client.get("/api/device/inventory")
    assert resp.status_code == 200
    body = resp.json()

    assert body["snaptones"]
    assert body["irs"]
    assert body["patches"]

    for s in body["snaptones"]:
        assert set(s.keys()) == {"slot", "name"}
    for i in body["irs"]:
        assert set(i.keys()) == {"slot", "name"}
    for p in body["patches"]:
        assert set(p.keys()) == {"slot", "name", "snaptone_slot", "ir_slot"}

    assert len(body["patches"]) == 16


def test_usage_snaptone_returns_referencing_patches():
    # slot 0 (Blackstar) is shared by several patches in the fixture.
    resp = client.get("/api/device/usage/snaptone/0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["snaptone"] == {"slot": 0, "name": "Blackstar"}

    expected_names = {p["name"] for p in device_stub.PATCHES if p["snaptone_slot"] == 0}
    assert {p["name"] for p in body["patches"]} == expected_names
    assert len(body["patches"]) > 1


def test_usage_snaptone_unused_slot_returns_empty_list():
    # slot 4 (Vox AC30) is deliberately unused in the fixture.
    resp = client.get("/api/device/usage/snaptone/4")
    assert resp.status_code == 200
    assert resp.json()["patches"] == []


def test_usage_snaptone_unknown_slot_404():
    resp = client.get("/api/device/usage/snaptone/999")
    assert resp.status_code == 404


def test_usage_ir_returns_referencing_patches():
    resp = client.get("/api/device/usage/ir/2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ir"] == {"slot": 2, "name": "British Stack"}

    expected_names = {p["name"] for p in device_stub.PATCHES if p["ir_slot"] == 2}
    assert {p["name"] for p in body["patches"]} == expected_names
    assert len(body["patches"]) > 1


def test_usage_ir_unknown_slot_404():
    resp = client.get("/api/device/usage/ir/999")
    assert resp.status_code == 404


def test_device_page_serves_mock_banner_and_hooks():
    resp = client.get("/device")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    html = resp.text

    assert "MOCK DATA" in html
    assert "not a live device read" in html

    for hook in (
        'id="kind-snaptone"',
        'id="kind-ir"',
        'id="item-select"',
        'id="usage-list"',
    ):
        assert hook in html, f"missing hook: {hook}"


def test_device_page_static_js_served():
    resp = client.get("/static/device.js")
    assert resp.status_code == 200
    assert "/api/device" in resp.text


def test_nav_links_present_on_both_pages():
    convert_html = client.get("/").text
    device_html = client.get("/device").text
    assert 'href="/device"' in convert_html
    assert 'href="/"' in device_html
