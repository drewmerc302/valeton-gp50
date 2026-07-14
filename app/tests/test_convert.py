"""patch/convert.py + prst_format device profiles — GP-5 <-> GP-50 conversion.

Ground-truth fixtures: the 100 GP-50 exports in presetExports/ and two real GP-5
presets in app/tests/fixtures/gp5/. Conversion must preserve the portable tone
content (name, the 390-byte 0x02 block, VOL/BPM, footswitches) and produce a
CRC-valid file of the target device's length.
"""

import glob
import os
import struct

import pytest

from patch import convert, device_write as dw, prst_format as fmt

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
GP50_FILES = sorted(glob.glob(os.path.join(PROJECT_ROOT, "presetExports", "*.prst")))
GP5_FILES = sorted(
    glob.glob(os.path.join(os.path.dirname(__file__), "fixtures", "gp5", "*.prst"))
)


def _portable(prst):
    """The content a conversion MUST preserve."""
    return (
        fmt.read_name(prst),
        convert._find_tlv(prst, 0x0002),
        convert._read_vol_bpm(prst),
        convert._read_footswitches(prst),
    )


def _crc_ok(prst):
    return fmt.crc8(prst[0x15:]) == prst[0x14]


# --- device detection ---------------------------------------------------------


def test_detect_gp50_exports():
    assert GP50_FILES
    for f in GP50_FILES:
        assert fmt.detect(open(f, "rb").read()).key == "gp50"


def test_detect_gp5_fixtures():
    assert GP5_FILES
    for f in GP5_FILES:
        assert fmt.detect(open(f, "rb").read()).key == "gp5"


def test_detect_rejects_garbage():
    with pytest.raises(ValueError):
        fmt.detect(b"\x00" * 300)


def test_profiles_distinct():
    assert fmt.GP50.prst_len == 552 and fmt.GP5.prst_len == 507
    assert fmt.GP50.body_len == 552 - fmt.BODY_OFF
    assert fmt.GP5.body_len == 507 - fmt.BODY_OFF
    assert fmt.GP50.header != fmt.GP5.header


# --- conversion round-trips ---------------------------------------------------


def test_gp5_to_gp50_is_byte_perfect_roundtrip():
    """GP-5 is the subset device, so GP-5 -> GP-50 -> GP-5 loses nothing."""
    for f in GP5_FILES:
        src = open(f, "rb").read()
        conv = convert.convert(src, "gp50")
        assert fmt.detect(conv).key == "gp50" and len(conv) == 552 and _crc_ok(conv)
        assert _portable(conv) == _portable(src)
        assert convert.convert(conv, "gp5") == src


def test_gp50_to_gp5_preserves_portable_content():
    """GP-50 -> GP-5 keeps tone/name/vol/bpm/fs (only GP-50-only trailer mode
    bytes are dropped, which GP-5 has no field for)."""
    converted = skipped = 0
    for f in GP50_FILES:
        src = open(f, "rb").read()
        if convert.check_convertible(src, "gp5"):
            skipped += 1
            continue
        conv = convert.convert(src, "gp5")
        assert fmt.detect(conv).key == "gp5" and len(conv) == 507 and _crc_ok(conv)
        assert _portable(conv) == _portable(src)
        assert _portable(convert.convert(conv, "gp50")) == _portable(src)
        converted += 1
    assert converted > 0


def test_same_device_is_identity():
    for f in GP5_FILES:
        b = open(f, "rb").read()
        assert convert.convert(b, "gp5") == b
    for f in GP50_FILES[:3]:
        b = open(f, "rb").read()
        assert convert.convert(b, "gp50") == b


# --- lossy refusal + force ----------------------------------------------------


def test_gp50_only_model_refused_then_forced():
    """A GP-50 preset using a GP-50-only model (AC Sim / C-Wah / AC cab) can't go
    to the GP-5 losslessly: refuse by default, drop the block under force."""
    offender = next(
        (
            f
            for f in GP50_FILES
            if convert.check_convertible(open(f, "rb").read(), "gp5")
        ),
        None,
    )
    if offender is None:
        pytest.skip("no GP-50-only-model preset in the corpus")
    src = open(offender, "rb").read()
    with pytest.raises(convert.ConversionError):
        convert.convert(src, "gp5")
    forced = convert.convert(src, "gp5", force=True)
    assert fmt.detect(forced).key == "gp5" and _crc_ok(forced)
    # every dropped block's model record is zeroed
    for prob in convert.check_convertible(src, "gp5"):
        idx, cat, fxlow = fmt.model_records(forced)[prob.block_index]
        assert (idx, cat, fxlow) == (0, 0, 0)


def test_gp5_target_never_flags_gp5_source():
    for f in GP5_FILES:
        assert convert.check_convertible(open(f, "rb").read(), "gp50") == []


def test_converted_settings_shape_matches_target():
    """The rebuilt 0x01 settings block has the target device's field shape."""
    src = open(GP5_FILES[0], "rb").read()
    conv = convert.convert(src, "gp50")
    payload = convert._find_tlv(conv, 0x0001)
    ids = []
    i = 0
    while i + 4 <= len(payload):
        ids.append(payload[i])
        i += 4 + struct.unpack_from("<H", payload, i + 2)[0]
    assert ids == list(range(1, 11))  # GP-50 carries fields id1..id10


# --- device write path (build/validate/gate; no hardware) ---------------------


def _reassembled_payload_len(packets):
    return sum(dw._nib_decode(w[1:-1])[3] for w in packets)


def test_write_stream_builds_and_validates_for_both_devices():
    for files, prst_len in ((GP50_FILES, 552), (GP5_FILES, 507)):
        prst = open(files[0], "rb").read()
        packets = dw.build_patch_write_stream(prst, 7)
        ok, reason = dw.validate_stream(packets)
        assert ok, reason
        # payload = 6-byte header + prst[NAME_OFF:]
        assert _reassembled_payload_len(packets) == 6 + (prst_len - fmt.NAME_OFF)
        first = dw._nib_decode(packets[0][1:-1])
        assert bytes(first[4:6]) == dw.PATCH_HDR and first[6] == 7  # header + slot


def test_gp50_stream_unchanged_29_packets():
    """Regression guard: the GP-50 stream is still the byte-verified 29-packet form."""
    prst = open(GP50_FILES[0], "rb").read()
    assert len(dw.build_patch_write_stream(prst, 0)) == 29


def test_send_gate_refuses_unverified_gp5():
    gp5_stream = dw.build_patch_write_stream(open(GP5_FILES[0], "rb").read(), 3)
    with pytest.raises(RuntimeError, match="not.*verified|verified"):
        dw.send_stream("port", gp5_stream, confirm=True, validated=True)
    # allow_unverified bypasses the gate (then fails later on the bogus port)
    with pytest.raises(Exception) as ei:
        dw.send_stream(
            "no-such-port",
            gp5_stream,
            confirm=True,
            validated=True,
            allow_unverified=True,
        )
    assert "capture-verified" not in str(ei.value)


def test_write_verified_map():
    assert dw.WRITE_VERIFIED == {"gp50": True, "gp5": False}
