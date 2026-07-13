"""Tests for the device inspector API, now backed by REAL parsed patch data
(app/patchlib.py reading presetExports/*.prst). No device I/O — everything is
derived from the exported patch set + the decoded model catalog.
"""

from fastapi.testclient import TestClient

from app import patchlib
from app.main import app

client = TestClient(app)


def test_inventory_shape_real_data():
    body = client.get("/api/device/inventory").json()
    assert "not a live device read" in body["source"]
    assert body["snaptones"] and body["irs"] and body["patches"]
    # the export set is 100 patches
    assert len(body["patches"]) == 100
    for p in body["patches"]:
        assert {
            "slot",
            "name",
            "uses_snaptone",
            "snaptone_slot",
            "ir_slot",
            "amp_slot",
            "snaptone_name",
            "ir_name",
            "amp_name",
        } <= set(p)
    for s in body["snaptones"]:
        assert set(s.keys()) == {"slot", "name"}


def test_snaptone_patches_are_the_nam_patches():
    # SnapTone slots live at 50..67 (the NAM patches, e.g. slot 50 = MesaLS)
    body = client.get("/api/device/usage/snaptone/50").json()
    assert body["snaptone"]["slot"] == 50
    names = {p["name"] for p in body["patches"]}
    assert names == {p["name"] for p in patchlib.patches_using_snaptone(50)}
    assert all(p["uses_snaptone"] for p in body["patches"])


def test_usage_ir_excludes_snaptone_patches():
    # a SnapTone patch bypasses the CAB block, so it must never appear in IR usage
    ir_slot = patchlib.all_irs()[0]["slot"]
    body = client.get(f"/api/device/usage/ir/{ir_slot}").json()
    assert all(not p["uses_snaptone"] for p in body["patches"])


def test_usage_unknown_slot_404():
    assert client.get("/api/device/usage/snaptone/999").status_code == 404
    assert client.get("/api/device/usage/ir/9999").status_code == 404


def test_clone_single_returns_valid_prst():
    r = client.post(
        "/api/device/clone", json={"patch_slot": 76, "snaptone_slots": [50]}
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    data = r.content
    assert len(data) == 552
    off = patchlib._model_rec_offset(data, patchlib.NS_CAT)
    assert data[off] == 50  # repointed to slot 50
    assert data[patchlib.CRC_OFF] == patchlib._crc8(
        data[patchlib.CRC_OFF + 1 :]
    )  # CRC fixed


def test_clone_multiple_returns_zip():
    r = client.post(
        "/api/device/clone", json={"patch_slot": 76, "snaptone_slots": [50, 51, 52]}
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    import io
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert len(zf.namelist()) == 3


def test_clone_bad_input_400():
    assert (
        client.post(
            "/api/device/clone", json={"patch_slot": 76, "snaptone_slots": []}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/device/clone", json={"patch_slot": 999, "snaptone_slots": [50]}
        ).status_code
        == 400
    )


def test_device_page_and_static_served():
    html = client.get("/device").text
    assert "parsed from exported patches" in html
    for hook in (
        'id="kind-snaptone"',
        'id="kind-ir"',
        'id="lib-list"',
        'id="usage-list"',
        'id="clone-source"',
        'id="clone-go"',
    ):
        assert hook in html, f"missing hook: {hook}"
    assert "/api/device" in client.get("/static/device.js").text


def test_nav_links_present_on_both_pages():
    assert 'href="/device"' in client.get("/").text
    assert 'href="/"' in client.get("/device").text
