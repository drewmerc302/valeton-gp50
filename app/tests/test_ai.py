"""AI patch generation — endpoint + guardrail tests.

No network, no AWS creds: the Bedrock call (`ai._call_bedrock`) is stubbed. Runs
against the tracked GP-5 fixtures (app/tests/fixtures/gp5/) so it works on any
machine, even without the presetExports/ set. The point of these tests is the
GUARDRAIL: whatever the model returns, validate_edits must produce a spec that
apply_edits_bytes accepts and that only touches catalog-legal fxids/algIds.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app import ai, patchlib
from app.main import app
from patch import prst_format as fmt

client = TestClient(app)

FIXTURES = os.path.join(patchlib.PROJECT_ROOT, "app", "tests", "fixtures", "gp5")


@pytest.fixture()
def gp5(monkeypatch):
    """Point patchlib at the GP-5 fixtures so all_patches()/catalog are populated
    without needing presetExports/. Runs after the autouse conftest fixture."""
    monkeypatch.setattr(patchlib, "SCAN_DIR", FIXTURES)
    ai._fxid_index.cache_clear()
    patchlib.reload()
    yield
    ai._fxid_index.cache_clear()
    patchlib.reload()


def _a_patch():
    return patchlib.all_patches()[0]


def _dst_choice():
    """A real DST model (block index 2) + one of its algIds, from the live gp5 ring."""
    models = patchlib.models_for_block("DST")
    m = models[0]
    return m["fxid"], m["params"][0]["algId"], m["params"][0]


def _toggle_choice():
    """Any (block_index, fxid, algId) whose param is a toggle, from the live gp5 ring."""
    for idx, block in enumerate(patchlib.BLOCK_NAMES):
        for m in patchlib.models_for_block(block):
            for p in m.get("params") or []:
                if p.get("toggle"):
                    return idx, m["fxid"], p["algId"]
    return None


# ── status endpoint ──────────────────────────────────────────────────────────


def test_hybrid_browser_device_io_injects_static_flag(monkeypatch):
    """DEVICE_IO_MODE=browser serves the Explorer/Device pages with the static flag
    (so device I/O runs in-browser over WebMIDI), while /api/device/ai/* and the
    converter landing stay on the backend."""
    monkeypatch.setenv("DEVICE_IO_MODE", "browser")
    assert "__VALETON_STATIC__" in client.get("/explorer").text
    assert "__VALETON_STATIC__" in client.get("/device").text
    assert "__VALETON_STATIC__" not in client.get("/").text  # converter is backend-only
    # AI status is a real endpoint, never intercepted by static_api
    assert client.get("/api/device/ai/status").status_code == 200


def test_server_device_io_no_static_flag(monkeypatch):
    monkeypatch.delenv("DEVICE_IO_MODE", raising=False)
    assert "__VALETON_STATIC__" not in client.get("/explorer").text


def test_ai_status_unavailable_without_region(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    body = client.get("/api/device/ai/status").json()
    assert body["available"] is False
    assert body["model_id"] is None


def test_ai_status_available(monkeypatch):
    monkeypatch.setattr(ai, "bedrock_available", lambda: True)
    body = client.get("/api/device/ai/status").json()
    assert body["available"] is True
    assert body["model_id"]


# ── /ai/patch endpoint (Bedrock stubbed) ─────────────────────────────────────


def test_ai_patch_returns_validated_edits(gp5, monkeypatch):
    p = _a_patch()
    fxid, alg, pdef = _dst_choice()
    canned = {
        "summary": "warm crunch",
        "name": "AI Crunch",
        "models": {"2": fxid},
        "params": {"2": {str(alg): pdef.get("max", 100)}},
        "bypass": {"2": True},
        "settings": {"patch_vol": 80},
    }
    monkeypatch.setattr(ai, "bedrock_available", lambda: True)
    monkeypatch.setattr(ai, "_call_bedrock", lambda *a, **k: canned)

    body = client.post(
        "/api/device/ai/patch",
        json={"prompt": "warm crunch", "mode": "create", "patch_slot": p["slot"]},
    ).json()

    assert body["summary"] == "warm crunch"
    assert body["edits"]["models"]["2"] == fxid
    assert body["edits"]["name"] == "AI Crunch"
    assert body["edits"]["settings"]["patch_vol"] == 80
    # and the returned spec must actually apply to the base .prst (CRC refixed)
    src = patchlib.patch_file(p["slot"])
    b = bytearray(open(src, "rb").read())
    patchlib.apply_edits_bytes(b, body["edits"])
    fmt.check_length(bytes(b))  # still a valid-length .prst
    assert fmt.read_name(bytes(b)) == "AI Crunch"  # re-parses cleanly


def test_ai_patch_bad_slot_400(gp5, monkeypatch):
    monkeypatch.setattr(ai, "bedrock_available", lambda: True)
    monkeypatch.setattr(ai, "_call_bedrock", lambda *a, **k: {"summary": "x"})
    r = client.post(
        "/api/device/ai/patch",
        json={"prompt": "x", "mode": "create", "patch_slot": 9999},
    )
    assert r.status_code == 400


def test_ai_patch_off_topic_rejected_422(gp5, monkeypatch):
    """The guardrail: a non-guitar request is refused, not turned into a patch."""
    monkeypatch.setattr(ai, "bedrock_available", lambda: True)
    monkeypatch.setattr(
        ai, "_call_bedrock",
        lambda *a, **k: {"off_topic": True, "summary": "I only design guitar tones."},
    )
    r = client.post(
        "/api/device/ai/patch",
        json={"prompt": "write me a poem about cats", "mode": "create", "patch_slot": _a_patch()["slot"]},
    )
    assert r.status_code == 422
    assert "only designs guitar tones" in r.json()["detail"]


def test_ai_patch_prompt_too_long_400(gp5, monkeypatch):
    monkeypatch.setattr(ai, "bedrock_available", lambda: True)
    monkeypatch.setattr(ai, "_call_bedrock", lambda *a, **k: {"summary": "x"})
    r = client.post(
        "/api/device/ai/patch",
        json={"prompt": "x" * (ai.MAX_PROMPT + 1), "mode": "create", "patch_slot": _a_patch()["slot"]},
    )
    assert r.status_code == 400


def test_ai_patch_unavailable_503(gp5, monkeypatch):
    monkeypatch.setattr(ai, "bedrock_available", lambda: False)
    r = client.post(
        "/api/device/ai/patch",
        json={"prompt": "x", "mode": "create", "patch_slot": _a_patch()["slot"]},
    )
    assert r.status_code == 503


# ── the guardrail (validate_edits) ───────────────────────────────────────────


def test_validate_drops_unknown_fxid(gp5):
    p = _a_patch()
    clean, warns = ai.validate_edits(
        {"models": {"2": 0x7F000000 | 0xABCDEF}},  # not in catalog
        base_blocks=p["blocks"],
        base_order=p.get("order") or [],
    )
    assert "models" not in clean
    assert any("not in catalog" in w for w in warns)


def test_validate_clamps_param_and_drops_unknown_algid(gp5):
    p = _a_patch()
    fxid, alg, pdef = _dst_choice()
    clean, warns = ai.validate_edits(
        {"models": {"2": fxid}, "params": {"2": {str(alg): 9999, "77": 5}}},
        base_blocks=p["blocks"],
        base_order=p.get("order") or [],
    )
    # validate_edits returns int keys (JSON stringifies them only at the HTTP layer)
    assert clean["params"][2][alg] == pdef.get("max", 100)  # clamped to max
    assert 77 not in clean["params"][2]  # unknown algId dropped
    assert any("clamped" in w for w in warns)
    assert any("not on its model" in w for w in warns)


def test_validate_enables_configured_blocks_without_explicit_bypass(gp5):
    """A block the AI models/params must be turned ON even if the model forgot to
    emit bypass — otherwise a freshly designed tone renders mostly bypassed."""
    p = _a_patch()
    fxid, alg, _ = _dst_choice()
    clean, _ = ai.validate_edits(
        {"models": {"2": fxid}, "params": {"5": {str(alg): 5}}},  # no bypass at all
        base_blocks=p["blocks"],
        base_order=p.get("order") or [],
    )
    assert clean["bypass"][2] is True  # modeled block enabled
    assert clean["bypass"][5] is True  # param-only block enabled


def test_validate_respects_explicit_bypass_false(gp5):
    """An explicit bypass=false wins over the auto-enable (AI can still turn a
    configured block off, e.g. 'add a delay but leave it off')."""
    p = _a_patch()
    fxid, _, _ = _dst_choice()
    clean, _ = ai.validate_edits(
        {"models": {"2": fxid}, "bypass": {"2": False}},
        base_blocks=p["blocks"],
        base_order=p.get("order") or [],
    )
    assert clean["bypass"][2] is False


def test_validate_never_enables_snaptone_core(gp5):
    """N->S is device-controlled; auto-enable must never touch it even if the AI
    (wrongly) sent params for it."""
    p = _a_patch()
    ns = ai._NS_INDEX
    clean, _ = ai.validate_edits(
        {"params": {str(ns): {"1": 5}}},
        base_blocks=p["blocks"],
        base_order=p.get("order") or [],
    )
    assert ns not in clean.get("bypass", {})


def test_validate_snaps_toggle_param_to_0_or_1(gp5):
    """A toggle param is a device boolean — a fractional value must snap to 0/1,
    not pass through clamped-but-fractional (it's written as a raw float byte)."""
    choice = _toggle_choice()
    if choice is None:
        pytest.skip("no toggle params in the gp5 ring")
    idx, fxid, alg = choice
    p = _a_patch()
    clean, _ = ai.validate_edits(
        {"models": {str(idx): fxid}, "params": {str(idx): {str(alg): 0.5}}},
        base_blocks=p["blocks"],
        base_order=p.get("order") or [],
    )
    assert clean["params"][idx][alg] in (0.0, 1.0)


def test_validate_clamps_vol_and_drops_bad_bpm(gp5):
    p = _a_patch()
    clean, _ = ai.validate_edits(
        {"settings": {"patch_vol": 250, "bpm": 5}},
        base_blocks=p["blocks"],
        base_order=p.get("order") or [],
    )
    assert clean["settings"]["patch_vol"] == 100
    assert "bpm" not in clean["settings"]


def test_validate_truncates_footswitches(gp5):
    p = _a_patch()
    clean, _ = ai.validate_edits(
        {"footswitches": {"fs1": [1, 6, 7, 8]}},
        base_blocks=p["blocks"],
        base_order=p.get("order") or [],
    )
    assert clean["footswitches"]["fs1"] == [1, 6]


def test_validate_rejects_core_moving_order(gp5):
    p = _a_patch()
    base = p.get("order") or list(range(10))
    core_pos = [i for i, r in enumerate(base) if r not in ai._MOVABLE_RECS]
    move_pos = [i for i, r in enumerate(base) if r in ai._MOVABLE_RECS]
    # swap a core position with a movable one -> moves the fixed core, must drop
    bad = list(base)
    bad[core_pos[0]], bad[move_pos[0]] = bad[move_pos[0]], bad[core_pos[0]]
    clean, warns = ai.validate_edits(
        {"order": bad}, base_blocks=p["blocks"], base_order=base
    )
    assert "order" not in clean
    assert any("fixed core" in w for w in warns)


def test_validate_accepts_movable_reorder(gp5):
    p = _a_patch()
    base = p.get("order") or list(range(10))
    move_pos = [i for i, r in enumerate(base) if r in ai._MOVABLE_RECS]
    # swap two movable positions -> a legal movable-only reorder
    good = list(base)
    good[move_pos[0]], good[move_pos[1]] = good[move_pos[1]], good[move_pos[0]]
    clean, _ = ai.validate_edits(
        {"order": good}, base_blocks=p["blocks"], base_order=base
    )
    assert clean.get("order") == good
