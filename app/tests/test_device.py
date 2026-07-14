"""Tests for the device inspector API, now backed by REAL parsed patch data
(app/patchlib.py reading presetExports/*.prst). No device I/O — everything is
derived from the exported patch set + the decoded model catalog.
"""

from fastapi.testclient import TestClient

from app import patchlib
from app.main import app
from patch import prst_format as fmt

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
    assert fmt.param_floats(d)[2 * 8 + 0] == 88.0
    assert bool(fmt.bypass_mask(d) >> 5 & 1) is True
    assert patchlib._patch_settings(bytes(d))["patch_vol"] == 70
    assert d[fmt.CRC_OFF] == fmt.crc8(d[fmt.CRC_OFF + 1 :])  # CRC refixed


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
    assert d[fmt.CRC_OFF] == fmt.crc8(d[fmt.CRC_OFF + 1 :])


def test_edit_leaves_other_params_untouched():
    from app import patchlib

    orig = fmt.param_floats(open(patchlib.patch_file(15), "rb").read())
    d = client.post(
        "/api/device/edit", json={"patch_slot": 15, "params": {2: {0: 88}}}
    ).content
    now = fmt.param_floats(d)
    # only DST/Gain (index 16) changed
    diffs = [i for i in range(80) if abs(orig[i] - now[i]) > 1e-6]
    assert diffs == [2 * 8 + 0]


def test_patch_write_stream_reproduces_suite_capture():
    """The patch-write builder must reproduce Suite's real import stream byte-for-byte
    (regression lock on the cracked 0x1D protocol). No device I/O."""
    from patch import device_write
    from patch.decode_import_capture import WRITE

    prst = open(patchlib.patch_file(15), "rb").read()  # US Lead source
    built = device_write.build_patch_write_stream(prst, 0)  # Suite "slot 1" = index 0
    captured = [[int(x, 16) for x in line.split()] for line in WRITE]
    assert built == captured  # 29 packets, exact wire match
    # slot byte lives at payload[2] of block 0; changing slot changes only that byte
    b0, b90 = (
        device_write.build_patch_write_stream(prst, 0),
        device_write.build_patch_write_stream(prst, 90),
    )
    assert b0[1:] == b90[1:]  # body blocks unchanged
    assert b0[0] != b90[0]  # header block differs (slot + its CRC)


def test_block_detail_carries_fxid_roundtrips_to_catalog():
    from app import patchlib

    great = next(p for p in patchlib.all_patches() if p["name"] == "GreatPedal")
    dst = next(b for b in great["blocks"] if b["block"] == "DST" and b["active"])
    assert dst["fxid"]  # non-zero for a populated block
    # the block's fxid must exist in the selectable-model catalog for its type
    models = patchlib.models_for_block("DST")
    match = next((m for m in models if m["fxid"] == dst["fxid"]), None)
    assert match is not None
    assert match["name"] == dst["model"]


def test_models_for_block_carry_labels():
    from app import patchlib

    models = patchlib.models_for_block("DST")
    m = models[0]
    assert {"fxid", "name", "label", "label_official", "params"} <= set(m)
    assert m["label"].startswith("DST · ")
    ns = patchlib.models_for_block("N->S")
    assert ns and all(x["label"].startswith("N->S · ") for x in ns)


def test_edit_swaps_model_record():
    from app import patchlib

    # pick a DST model different from what patch 15 currently has
    orig = open(patchlib.patch_file(15), "rb").read()
    cur = patchlib._blocks_for(orig, {})[2]["fxid"]
    target = next(m for m in patchlib.models_for_block("DST") if m["fxid"] != cur)
    r = client.post(
        "/api/device/edit",
        json={"patch_slot": 15, "models": {2: target["fxid"]}},
    )
    assert r.status_code == 200
    d = r.content
    assert len(d) == 552
    assert patchlib._blocks_for(bytes(d), {})[2]["fxid"] == target["fxid"]
    assert d[fmt.CRC_OFF] == fmt.crc8(d[fmt.CRC_OFF + 1 :])


def test_blocklib_crud_roundtrip():
    from app import blocklib

    before = len(blocklib.list_entries("DST"))
    entry = client.post(
        "/api/device/blocklib",
        json={
            "name": "Test TS808 Boost",
            "block": "DST",
            "fxid": patchlib_fxid_for_dst(),
            "model_name": "Green OD",
            "params": {0: 42, 1: 55},
        },
    ).json()
    assert entry["id"] and entry["name"] == "Test TS808 Boost"
    listed = client.get("/api/device/blocklib?block=DST").json()["entries"]
    assert len(listed) == before + 1
    assert any(e["id"] == entry["id"] for e in listed)
    # stored params keyed by str(algId)
    saved = next(e for e in listed if e["id"] == entry["id"])
    assert saved["params"]["0"] == 42.0
    assert (
        client.delete(f"/api/device/blocklib/{entry['id']}").json()["deleted"] is True
    )
    assert len(client.get("/api/device/blocklib?block=DST").json()["entries"]) == before


def patchlib_fxid_for_dst():
    from app import patchlib

    return patchlib.models_for_block("DST")[0]["fxid"]


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


def test_write_endpoint_requires_confirm():
    r = client.post(
        "/api/device/write",
        json={"patch_slot": 15, "target_slot": 90, "confirm": False},
    )
    assert r.status_code == 400
    assert "confirm" in r.json()["detail"].lower()


def test_write_endpoint_rejects_bad_target():
    r = client.post(
        "/api/device/write",
        json={"patch_slot": 15, "target_slot": 200, "confirm": True},
    )
    assert r.status_code == 400


def test_write_endpoint_applies_edits_and_writes(monkeypatch):
    # hermetic: capture the .prst handed to the device, no MIDI/subprocess
    from app import device_io, patchlib

    captured = {}

    def fake_write(prst, slot, timeout=30.0, allow_unverified=False):
        captured["prst"] = prst
        captured["slot"] = slot
        return {
            "ok": True,
            "sent": True,
            "acks": 29,
            "packets": 29,
            "verified_name": "US Lead",
        }

    monkeypatch.setattr(device_io, "write_patch", fake_write)
    r = client.post(
        "/api/device/write",
        json={
            "patch_slot": 15,
            "params": {2: {0: 88}},
            "target_slot": 90,
            "confirm": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["acks"] == 29
    # the bytes sent are a valid 552-byte .prst with the edit applied + CRC fixed
    assert captured["slot"] == 90
    assert len(captured["prst"]) == 552
    assert fmt.param_floats(captured["prst"])[2 * 8 + 0] == 88.0
    d = captured["prst"]
    assert d[fmt.CRC_OFF] == fmt.crc8(d[fmt.CRC_OFF + 1 :])


def test_swap_requires_confirm_and_distinct():
    assert (
        client.post("/api/device/swap", json={"slot_a": 1, "slot_b": 2}).status_code
        == 400
    )
    assert (
        client.post(
            "/api/device/swap", json={"slot_a": 1, "slot_b": 1, "confirm": True}
        ).status_code
        == 400
    )


def test_swap_writes_both_bodies(monkeypatch):
    # hermetic: capture the (bytes, slot) pairs handed to the device
    from app import device_io, patchlib

    calls = []

    def fake_write(prst, slot, timeout=30.0, allow_unverified=False):
        calls.append(
            (slot, len(prst), prst[0x19:0x29].split(b"\0")[0].decode("latin1"))
        )
        return {"ok": True, "sent": True, "acks": 29}

    monkeypatch.setattr(device_io, "write_patch", fake_write)
    assert patchlib.patch_file(15) and patchlib.patch_file(3)  # fixtures exist
    r = client.post(
        "/api/device/swap", json={"slot_a": 15, "slot_b": 3, "confirm": True}
    )
    assert r.status_code == 200 and r.json()["ok"]
    # two writes: slot_a's body -> slot_b, and slot_b's body -> slot_a
    targets = sorted(c[0] for c in calls)
    assert targets == [3, 15]
    assert all(c[1] == 552 for c in calls)


def test_scan_endpoints(monkeypatch):
    # hermetic: fake the background scan + status (no MIDI/subprocess)
    from app import device_io

    monkeypatch.setattr(device_io, "scan_bank", lambda: {"ok": True, "started": True})
    r = client.post("/api/device/scan").json()
    assert r["ok"] and r["started"]

    states = iter(
        [
            {
                "running": True,
                "done": 40,
                "total": 100,
                "current": "Metal Lica",
                "errors": 0,
                "written": 0,
                "error": None,
            },
            {
                "running": False,
                "done": 100,
                "total": 100,
                "current": "US Lead",
                "errors": 0,
                "written": 100,
                "error": None,
            },
        ]
    )
    monkeypatch.setattr(device_io, "scan_status", lambda: next(states))
    assert client.get("/api/device/scan/status").json()["running"] is True
    final = client.get("/api/device/scan/status").json()
    assert final["running"] is False and final["written"] == 100


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


def test_status_endpoint_reports_connection(monkeypatch):
    from app import device_io

    monkeypatch.setattr(
        device_io,
        "device_status",
        lambda: {
            "connected": True,
            "device": {"key": "gp50", "name": "GP-50"},
            "port": "GP-50",
        },
    )
    body = client.get("/api/device/status").json()
    assert body["connected"] is True and body["device"]["name"] == "GP-50"


def test_select_endpoint_selects_and_reloads_on_refresh(monkeypatch):
    from app import device_io, patchlib

    seen = {}
    monkeypatch.setattr(
        device_io,
        "select_patch",
        lambda slot: (
            seen.update(slot=slot)
            or {
                "ok": True,
                "slot": slot,
                "device": {"key": "gp50", "name": "GP-50"},
                "cache_updated": True,
            }
        ),
    )
    reloaded = {"n": 0}
    monkeypatch.setattr(
        patchlib, "reload", lambda: reloaded.update(n=reloaded["n"] + 1)
    )
    body = client.post("/api/device/select", json={"slot": 7}).json()
    assert body["ok"] and body["slot"] == 7 and seen["slot"] == 7
    assert reloaded["n"] == 1  # cache_updated -> inventory reload


def test_select_endpoint_no_reload_when_cache_unchanged(monkeypatch):
    from app import device_io, patchlib

    monkeypatch.setattr(
        device_io,
        "select_patch",
        lambda slot: {"ok": True, "slot": slot, "cache_updated": False},
    )
    reloaded = {"n": 0}
    monkeypatch.setattr(
        patchlib, "reload", lambda: reloaded.update(n=reloaded["n"] + 1)
    )
    client.post("/api/device/select", json={"slot": 3})
    assert reloaded["n"] == 0


def test_select_endpoint_surfaces_no_device(monkeypatch):
    from app import device_io

    monkeypatch.setattr(
        device_io,
        "select_patch",
        lambda slot: {"ok": False, "slot": slot, "error": "no Valeton device found"},
    )
    body = client.post("/api/device/select", json={"slot": 2}).json()
    assert body["ok"] is False and "no Valeton device" in body["error"]


def test_explorer_page_served():
    html = client.get("/explorer").text
    assert 'id="preset-list"' in html and 'id="filter-bar"' in html
    assert 'id="save-filter"' in html and 'id="saved-filters"' in html
    js = client.get("/static/explorer.js").text
    assert "/api/device" in js
    assert "gp50_savedFilters" in js  # saved filter sets persist to localStorage
    assert 'id="device-conn"' in html  # live-connection indicator for click-to-select


def test_shared_ui_core_loaded_by_both_pages():
    # ui_core.js is the shared seam: both pages load it before their own scripts,
    # and neither page re-implements its primitives.
    for route in ("/explorer", "/device"):
        html = client.get(route).text
        assert "ui_core.js" in html, f"{route} missing the shared core"
    core = client.get("/static/ui_core.js").text
    assert "window.UI" in core
    for prim in (
        "toast",
        "confirmDialog",
        "promptDialog",
        "isUserIrSlot",
    ):
        assert prim in core
    # the explorer no longer hand-rolls alert()/its own confirm modal
    js = client.get("/static/explorer.js").text
    assert "alert(" not in js
    assert "window.confirm" not in js
    # one User-IR threshold, defined in the core only
    assert "0x100000" in core
    assert "0xfffff" not in client.get("/static/device_a.js").text


def test_inventory_exposes_slot_semantics():
    # the backend owns the empty-slot truth and the slot domains; frontends
    # consume answers instead of re-deriving sentinels/ranges.
    body = client.get("/api/device/inventory").json()
    doms = body["domains"]
    assert doms["patch_slots"] == [0, 99]
    assert doms["snaptone_slots"] == [0, 79]
    assert doms["user_snaptone_slots"] == [50, 79]
    assert doms["user_ir_base"] == 0x100000
    for p in body["patches"]:
        assert isinstance(p["empty"], bool)
        assert p["empty"] == (p["name"].strip().upper() == "GP-50")
    # no frontend file re-derives the "GP-50" sentinel
    for js in ("ui_core.js", "device_core.js", "device_a.js", "explorer.js"):
        text = client.get(f"/static/{js}").text
        assert 'toUpperCase() === "GP-50"' not in text, f"{js} re-derives empty"


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
    off = fmt.model_rec_offset(data, patchlib.NS_CAT)
    assert data[off] == 50  # repointed to slot 50
    assert data[fmt.CRC_OFF] == fmt.crc8(data[fmt.CRC_OFF + 1 :])  # CRC fixed


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


def _a_snaptone_patch():
    """A device patch that uses a SnapTone (has an N->S block to repoint)."""
    inv = client.get("/api/device/inventory").json()
    p = next(p for p in inv["patches"] if p["uses_snaptone"])
    other = next(s["slot"] for s in inv["snaptones"] if s["slot"] != p["snaptone_slot"])
    return p, other


def test_template_from_patch_then_build_download():
    from app import patchlib

    p, other_st = _a_snaptone_patch()
    tmpl = client.post(
        "/api/device/templates/from-patch",
        json={"name": "Test Overnight", "source_slot": p["slot"]},
    ).json()
    assert tmpl["id"] and tmpl["summary"]["uses_snaptone"] is True
    assert "body_b64" not in tmpl  # heavy body stripped from responses
    try:
        # build onto a DIFFERENT SnapTone, download the .prst (no device write)
        r = client.post(
            "/api/device/build",
            json={
                "template_id": tmpl["id"],
                "snaptone_slot": other_st,
                "download": True,
            },
        )
        assert r.status_code == 200
        prst = r.content
        assert len(prst) == 552
        off = fmt.model_rec_offset(bytearray(prst), patchlib.NS_CAT)
        assert prst[off] == other_st  # N->S repointed to the chosen capture
        assert prst[fmt.CRC_OFF] == fmt.crc8(prst[fmt.CRC_OFF + 1 :])
        # named after the target SnapTone
        st_name = next(
            s["name"]
            for s in client.get("/api/device/inventory").json()["snaptones"]
            if s["slot"] == other_st
        )
        assert prst[0x19:0x29].split(b"\0")[0].decode("latin1") == st_name[:16]
    finally:
        client.delete(f"/api/device/templates/{tmpl['id']}")


def test_build_write_requires_confirm():
    p, other_st = _a_snaptone_patch()
    tmpl = client.post(
        "/api/device/templates/from-patch",
        json={"name": "Test Confirm", "source_slot": p["slot"]},
    ).json()
    try:
        # no download + no confirm -> refused, device untouched
        r = client.post(
            "/api/device/build",
            json={
                "template_id": tmpl["id"],
                "snaptone_slot": other_st,
                "target_slot": 95,
            },
        )
        assert r.status_code == 400
    finally:
        client.delete(f"/api/device/templates/{tmpl['id']}")


def test_repoint_engine_guards():
    from app import patchlib

    p, _ = _a_snaptone_patch()
    body = open(patchlib.patch_file(p["slot"]), "rb").read()
    # out-of-range SnapTone slot rejected
    try:
        patchlib.repoint_snaptone_body(body, 99)
        assert False, "expected ValueError for slot 99"
    except ValueError:
        pass
    # wrong length rejected
    try:
        patchlib.repoint_snaptone_body(body[:100], 50)
        assert False, "expected ValueError for short body"
    except ValueError:
        pass


def test_device_page_and_static_served():
    html = client.get("/device").text
    assert 'id="st-grid"' in html
    assert "device_core.js" in html, "missing DeviceCore"
    assert 'id="build-btn"' in html
    # make-a-template-from-preset entry point lives on the page
    assert 'id="tmpl-new-btn"' in html
    assert 'id="tmpl-modal"' in html
    # focused on user tone management: no factory-cab section
    assert 'id="cab-grid"' not in html
    # the alternate layout variants were dropped
    assert client.get("/device-b").status_code == 404
    assert client.get("/device-c").status_code == 404
    # shared engine talks to the real API
    assert "/api/device" in client.get("/static/device_core.js").text
    assert "openBuildModal" in client.get("/static/device_core.js").text


def test_nav_links_present_on_both_pages():
    assert 'href="/device"' in client.get("/").text
    assert 'href="/"' in client.get("/device").text
