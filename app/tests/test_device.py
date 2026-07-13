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
            "blocks",
        } <= set(p)
    for s in body["snaptones"]:
        assert set(s.keys()) == {"slot", "name"}


def test_block_detail_and_facets():
    from app import patchlib

    # a known amp patch has a resolved Block · Type · Model chain
    great = next(p for p in patchlib.all_patches() if p["name"] == "GreatPedal")
    labels = [b["label"] for b in great["blocks"] if b["active"]]
    assert any("DST · OD ·" in x for x in labels)  # Drive · type · model granularity
    assert any(x.startswith("AMP · ") for x in labels)

    # a SnapTone patch's N->S block carries the device SnapTone name
    vox = next(p for p in patchlib.all_patches() if p["name"] == "VoxUltNAM")
    ns = next(b for b in vox["blocks"] if b["block"] == "N->S" and b["active"])
    assert ns["model"] == "VX UL10 Ed"

    fac = client.get("/api/device/facets").json()
    dst = next(b for b in fac["blocks"] if b["block"] == "DST")
    assert "OD" in dst["types"] and "Fuzz" in dst["types"]


def test_user_ir_uses_device_name_when_synced():
    from app import patchlib

    # bank_map.json carries real device IR names (from a live 0x20 read); a patch
    # referencing a User IR should show that name, not the generic "User IR N".
    tc = next(p for p in patchlib.all_patches() if p["name"] == "Twin Clean")
    cab = next(b for b in tc["blocks"] if b["block"] == "CAB")
    assert cab["model"] and not cab["model"].startswith("User IR")


def test_facets_models_carry_official():
    fac = client.get("/api/device/facets").json()
    amp = next(b for b in fac["blocks"] if b["block"] == "AMP")
    assert amp["models"] and isinstance(amp["models"][0], dict)
    assert {"model", "official"} <= set(amp["models"][0])


def test_block_params_decode_against_hardware():
    # US Lead (preset 15) — values verified against Suite Edit screenshots
    from app import patchlib

    p = next(x for x in patchlib.all_patches() if x["name"] == "US Lead")
    by = {b["block"]: b for b in p["blocks"]}
    pre = {pr["name"]: pr["display"] for pr in by["PRE"]["params"]}
    assert pre == {"Sustain": "20", "Attack": "30", "VOL": "50", "Clip": "10"}
    amp = {pr["name"]: pr["display"] for pr in by["AMP"]["params"]}
    assert amp["Middle"] == "40" and amp["Treble"] == "60" and amp["Bright"] == "On"
    mod = {pr["name"]: pr["display"] for pr in by["MOD"]["params"]}
    assert mod["Rate"] == "0.50 Hz" and mod["Sync"] == "Off"
    rvb = {pr["name"]: pr["display"] for pr in by["RVB"]["params"]}
    assert rvb["Trail"] == "Off"  # algId-based mapping, not positional
    assert p["settings"]["patch_vol"] == 50 and p["settings"]["bpm"] == 120
    # footswitch assignments (US Lead: FS1=DST(block 2), FS2=DLY(block 7))
    assert p["settings"]["fs1"] == [2] and p["settings"]["fs2"] == [7]


def test_edit_endpoint_writes_params_bypass_settings():
    from app import patchlib

    r = client.post(
        "/api/device/edit",
        json={
            "patch_slot": 15,
            "params": {2: {0: 88}},  # DST block, algId 0 (Gain) -> 88
            "bypass": {5: True},  # activate EQ block
            "settings": {"patch_vol": 70},
        },
    )
    assert r.status_code == 200
    d = r.content
    assert len(d) == 552
    assert patchlib._param_floats(d)[2 * 8 + 0] == 88.0
    assert bool(patchlib._bypass_mask(d) >> 5 & 1) is True
    assert patchlib._patch_settings(bytes(d))["patch_vol"] == 70
    assert d[patchlib.CRC_OFF] == patchlib._crc8(
        d[patchlib.CRC_OFF + 1 :]
    )  # CRC refixed


def test_edit_footswitch_assignment_max_two():
    from app import patchlib

    d = client.post(
        "/api/device/edit",
        json={
            "patch_slot": 15,
            "footswitches": {"fs1": [0, 3], "fs2": [8]},
        },
    ).content
    fs1, fs2 = patchlib._footswitches(bytes(d))
    assert fs1 == [0, 3] and fs2 == [8]
    assert d[patchlib.CRC_OFF] == patchlib._crc8(d[patchlib.CRC_OFF + 1 :])


def test_edit_leaves_other_params_untouched():
    from app import patchlib

    orig = patchlib._param_floats(open(patchlib.patch_file(15), "rb").read())
    d = client.post(
        "/api/device/edit", json={"patch_slot": 15, "params": {2: {0: 88}}}
    ).content
    now = patchlib._param_floats(d)
    # only DST/Gain (index 16) changed
    diffs = [i for i in range(80) if abs(orig[i] - now[i]) > 1e-6]
    assert diffs == [2 * 8 + 0]


def test_official_names_origin():
    from app import patchlib

    great = next(p for p in patchlib.all_patches() if p["name"] == "GreatPedal")
    dst = next(b for b in great["blocks"] if b["block"] == "DST" and b["active"])
    assert dst["official"] == "Ibanez TS808"  # Green OD -> official reference
    assert dst["label_official"] == "DST · OD · Ibanez TS808"
    # a model without an official reference keeps its device name
    rvb = next(b for b in great["blocks"] if b["block"] == "RVB" and b["active"])
    assert rvb["official"] is None
    assert rvb["label_official"] == rvb["label"]


def test_sync_endpoint_reports_device_result(monkeypatch):
    # hermetic: fake the device read (no MIDI, no subprocess)
    from app import device_io

    monkeypatch.setattr(
        device_io,
        "sync_snaptones",
        lambda: {"ok": True, "count": 3, "snaptones": {"50": "MES LS II"}},
    )
    body = client.post("/api/device/sync").json()
    assert body["ok"] and body["count"] == 3


def test_sync_endpoint_surfaces_device_error(monkeypatch):
    from app import device_io

    monkeypatch.setattr(
        device_io,
        "sync_snaptones",
        lambda: {"ok": False, "error": "device did not respond"},
    )
    body = client.post("/api/device/sync").json()
    assert body["ok"] is False and "did not respond" in body["error"]


def test_explorer_page_served():
    html = client.get("/explorer").text
    assert 'id="preset-list"' in html and 'id="filter-bar"' in html
    assert 'id="save-filter"' in html and 'id="saved-filters"' in html
    js = client.get("/static/explorer.js").text
    assert "/api/device" in js
    assert "gp50_savedFilters" in js  # saved filter sets persist to localStorage


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
