"""GP-5 <-> GP-50 preset converter.

The two devices share this .prst container and, crucially, the same effect
catalog and the same 390-byte 0x02 "tone block" (identical layout and identical
effect codes — GP-5's catalog is a strict subset of the GP-50's). So a
conversion is NOT an effect-code transcode: it is a container reshape. We keep
the genuinely portable content and rewrap it in the target device's skeleton.

Portable (carried across):
  - patch name
  - the 390-byte 0x02 tone block (models + bypass + params + block settings)
  - patch VOL (0x01 settings id1) and BPM (id2)
  - footswitch masks FS1/FS2 (0x03 trailer)

Device-specific (taken from the target skeleton, not the source):
  - 20-byte header + 0xFF-block device tag
  - the 0x01 patch-settings shape (GP-50 carries 10 fields incl. non-portable
    routing/EXP defaults id5=id8=100; GP-5 carries only VOL + BPM)
  - the 0x03 trailer length (GP-50 has 2 extra mode bytes past the masks)

Direction notes:
  - GP-5 -> GP-50 is always lossless (every GP-5 model exists on the GP-50).
  - GP-50 -> GP-5 is lossless UNLESS a block uses one of the 3 GP-50-only models
    (AC Sim, C-Wah, AC cab); those have no GP-5 equivalent and are refused with a
    clear message so the user can swap the block first.

stdlib-only, like prst_format — usable from either venv.
"""

from __future__ import annotations

import struct
from typing import NamedTuple

from patch import prst_format as fmt
from patch.prst_format import DeviceProfile

# The 0x00 block is byte-identical on both devices; the 0xFF payload differs only
# in its trailing 4-byte device tag. These are the constant skeleton pieces.
BLK_FF_PREFIX = bytes.fromhex("010004000100000002000400")  # 12 bytes, then devtag
BLK_00_PAYLOAD = bytes.fromhex("011004000a0000000210040008000000")  # 16 bytes

# GP-50 non-portable settings defaults (id3..id10), confirmed constant across all
# 100 factory/user presets: id5 and id8 are 100 (levels), the rest 0. Encoded as
# (id, length, value) — id1/id2 (VOL/BPM) are filled from the source, not here.
_GP50_SETTINGS_DEFAULTS = [
    (3, 1, 0),
    (4, 4, 0),
    (5, 4, 100),
    (6, 1, 0),
    (7, 1, 0),
    (8, 1, 100),
    (9, 1, 0),
    (10, 1, 0),
]
_GP50_TRAILER_MODE = bytes([0x05, 0x05])  # 2 bytes past the FS masks (factory default)

# GP-50 models with no GP-5 equivalent: (fxid, human name). fxid = (cat<<24)|fxlow.
GP50_ONLY_FXIDS = {
    0x01000001: "PRE · AC Sim",
    0x05000008: "PRE · C-Wah",
    0x0A00003C: "CAB · AC",
}


class ConversionError(ValueError):
    """Raised when a preset cannot be converted losslessly (e.g. a GP-50-only
    model on a GP-50 -> GP-5 conversion)."""


class Problem(NamedTuple):
    block_index: int
    fxid: int
    model: str


def _tlv(tag: int, payload: bytes) -> bytes:
    return struct.pack("<HH", tag, len(payload)) + payload


def _find_tlv(prst: bytes, tag: int) -> bytes:
    """Return the payload of the first top-level TLV with `tag`, or b'' if absent."""
    off = fmt.BODY_OFF
    while off + 4 <= len(prst):
        t, ln = struct.unpack_from("<HH", prst, off)
        if t == tag:
            return prst[off + 4 : off + 4 + ln]
        off += 4 + ln
    return b""


def _read_vol_bpm(prst: bytes) -> tuple[int, int]:
    """Extract patch VOL (settings id1) and BPM (id2). Defaults 50 / 120."""
    vol, bpm = 50, 120
    i = fmt.SETTINGS_OFF
    while i + 4 <= len(prst) and prst[i + 1] == 0x20:
        rid, ln = prst[i], struct.unpack_from("<H", prst, i + 2)[0]
        if ln not in (1, 2, 4):
            break
        val = int.from_bytes(prst[i + 4 : i + 4 + ln], "little")
        if rid == 0x01:
            vol = val
        elif rid == 0x02:
            bpm = val
        i += 4 + ln
    return vol, bpm


def _read_footswitches(prst: bytes) -> tuple[int, int]:
    """Extract the FS1/FS2 block masks from the trailer. Defaults 0 / 0."""
    off = fmt.fs_offset(prst)
    if off < 0:
        return 0, 0
    fs1 = struct.unpack_from("<I", prst, off)[0]
    fs2 = struct.unpack_from("<I", prst, off + 4)[0]
    return fs1, fs2


def _settings_block(profile: DeviceProfile, vol: int, bpm: int) -> bytes:
    """Build the 0x01 patch-settings TLV for the target device."""
    if profile.key == "gp5":
        # GP-5: two 4-byte fields, VOL then BPM.
        payload = struct.pack("<BBHi", 1, 0x20, 4, vol) + struct.pack(
            "<BBHi", 2, 0x20, 4, bpm
        )
        return _tlv(0x0001, payload)
    # GP-50: VOL (1 byte) + BPM (4 bytes) + the fixed non-portable defaults.
    vol = max(0, min(255, vol))
    payload = struct.pack("<BBHB", 1, 0x20, 1, vol) + struct.pack(
        "<BBHi", 2, 0x20, 4, bpm
    )
    for rid, ln, val in _GP50_SETTINGS_DEFAULTS:
        payload += struct.pack("<BBH", rid, 0x20, ln) + int(val).to_bytes(ln, "little")
    return _tlv(0x0001, payload)


def _trailer_block(profile: DeviceProfile, fs1: int, fs2: int) -> bytes:
    """Build the 0x03 footswitch trailer TLV for the target device."""
    payload = struct.pack("<II", fs1, fs2)
    if profile.key == "gp50":
        payload += _GP50_TRAILER_MODE
    return _tlv(0x0003, payload)


def check_convertible(prst: bytes, target_key: str) -> list[Problem]:
    """Return the blocks that block a lossless conversion (empty = clean). Only
    GP-50 -> GP-5 can produce problems (GP-50-only models)."""
    target = fmt.profile_for(target_key)
    if target.key != "gp5":
        return []
    problems = []
    for k, (idx, cat, fxlow) in enumerate(fmt.model_records(prst)):
        fxid = (cat << 24) | fxlow
        if fxid in GP50_ONLY_FXIDS:
            problems.append(Problem(k, fxid, GP50_ONLY_FXIDS[fxid]))
    return problems


def convert(prst: bytes, target_key: str, *, force: bool = False) -> bytes:
    """Convert a .prst to the target device. Returns the source unchanged if it is
    already the target device. Raises ConversionError on a lossy GP-50 -> GP-5
    unless force=True (which drops the offending model to 'empty')."""
    source = fmt.detect(prst)
    target = fmt.profile_for(target_key)
    if source.key == target.key:
        return prst

    problems = check_convertible(prst, target_key)
    if problems and not force:
        names = ", ".join(f"block {p.block_index} ({p.model})" for p in problems)
        raise ConversionError(
            f"cannot convert to {target.name}: no GP-5 equivalent for {names}. "
            f"Swap the block(s) first, or force the conversion to drop them."
        )

    name = fmt.read_name(prst)
    tone = _find_tlv(prst, 0x0002)  # the 390-byte portable tone block
    if len(tone) != 390:
        raise ConversionError(
            f"unexpected tone block length {len(tone)} (expected 390)"
        )
    if problems and force:
        tone = _drop_models(tone, [p.block_index for p in problems])
    vol, bpm = _read_vol_bpm(prst)
    fs1, fs2 = _read_footswitches(prst)

    body = (
        _tlv(0x00FF, BLK_FF_PREFIX + target.devtag)
        + _tlv(0x0000, BLK_00_PAYLOAD)
        + _settings_block(target, vol, bpm)
        + _tlv(0x0002, tone)
        + _trailer_block(target, fs1, fs2)
    )
    out = bytearray(
        target.header + b"\x00" + fmt.SENTINEL + b"\0" * fmt.NAME_LEN + body
    )
    fmt.write_name(out, name)
    fmt.refix_crc(out)
    if len(out) != target.prst_len:
        raise ConversionError(
            f"built {len(out)} bytes, expected {target.prst_len} for {target.name}"
        )
    return bytes(out)


def _drop_models(tone: bytes, block_indices: list[int]) -> bytes:
    """Zero out the given block model records inside a 0x02 tone block (force mode)."""
    t = bytearray(tone)
    base = t.find(fmt.REC_MODELS)
    if base < 0:
        return bytes(t)
    base += 4
    for k in block_indices:
        rec = base + k * 4
        t[rec : rec + 4] = b"\x00\x00\x00\x00"
    return bytes(t)
