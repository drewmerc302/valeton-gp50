"""The 552-byte GP-50 .prst format — single source of truth.

Every byte offset, sentinel, record magic, and the file CRC live here and only
here. app/patchlib.py (inventory + edits), patch/device_write.py (write
payload), patch/scan_bank.py + patch/reconstruct_prst.py (rebuild from device
reads), and app/device_io.py (scan-cache naming) all consume this interface
instead of slicing bytes themselves.

Layout (decoded from the 0x41 read + 100/100 round-trip against presetExports;
see re/DEVICE_READ.md):

  prst[0x00:0x14]  constant "GP-50" header                (HEADER)
  prst[0x14]       file CRC — CRC-8/0x07 over prst[0x15:] (CRC_OFF)
  prst[0x15:0x19]  FF FF FF FF sentinel                   (SENTINEL)
  prst[0x19:0x29]  16-byte patch name, latin1, null-pad   (NAME_OFF..BODY_OFF)
  prst[0x29:]      511-byte body                          (BODY_OFF, BODY_LEN)

Body records (offsets found by magic, not fixed position):
  REC_MODELS  [03 30 28 00] + 10 x 4-byte model records [fxlow b0][b1][b2][cat]
  REC_BYPASS  [01 30 04 00] + u32 bitmask, bit k = block k active
  REC_PARAMS  [04 30 40 01] + 80 x float32 (10 blocks x 8 param slots)
  FS_TRAILER  [03 00 0A 00] + [FS1 u32][FS2 u32][2 bytes] footswitch masks

stdlib-only on purpose: imported by the web app (.venv-app) and by the MIDI
scripts (.venv-midi) alike.
"""

from __future__ import annotations

import struct
from typing import NamedTuple, Optional

PRST_LEN = 552  # GP-50 (the default device); GP-5 is 507 — see DEVICES below
BODY_LEN = 511  # GP-50 body (PRST_LEN - BODY_OFF)

HEADER = bytes.fromhex("47502d3530000000000000000000000000000100")  # GP-50 [0x00:0x14]
CRC_OFF = 0x14
SENTINEL = b"\xff\xff\xff\xff"  # [0x15:0x19]
NAME_OFF = 0x19
NAME_LEN = 16
BODY_OFF = 0x29  # NAME_OFF + NAME_LEN

REC_MODELS = bytes([0x03, 0x30, 0x28, 0x00])
REC_BYPASS = bytes([0x01, 0x30, 0x04, 0x00])
REC_PARAMS = bytes([0x04, 0x30, 0x40, 0x01])
FS_TRAILER = bytes(
    [0x03, 0x00, 0x0A, 0x00]
)  # GP-50 trailer magic (GP-5 is 03 00 08 00)
SETTINGS_OFF = (
    0x55  # first group-0x20 patch-settings record (same offset on both devices)
)

N_BLOCKS = 10
N_PARAM_SLOTS = 80  # N_BLOCKS x 8


# --- device profiles ----------------------------------------------------------
# The GP-5 and GP-50 share this .prst container, the SysEx protocol, and the
# effect catalog (GP-5's catalog is a strict subset of the GP-50's). The three
# things that differ per device are captured here: the 20-byte header, the total
# file length, and the 4-byte device tag inside the 0xFF block. Everything else
# (record magics, CRC, name codec, the 390-byte 0x02 tone block) is identical, so
# the parsing functions below are already device-agnostic.

HEADER_GP50 = HEADER
HEADER_GP5 = bytes.fromhex("47502d3500000000000000000000000000000100")  # "GP-5\0"
DEVTAG_GP50 = bytes.fromhex("47503530")  # "GP50", 0xFF-block bytes [12:16]
DEVTAG_GP5 = bytes.fromhex("0a454d51")  # GP-5 device signature


class DeviceProfile(NamedTuple):
    key: str  # stable id: "gp50" | "gp5"
    name: str  # display / factory-default patch name: "GP-50" | "GP-5"
    header: bytes  # 20-byte fixed header ([0x00:0x14])
    prst_len: int  # full .prst byte length
    devtag: bytes  # 4-byte tag inside the 0xFF block
    ring_file: str  # model catalog filename under patch/
    midi_port: str  # rtmidi port-name match for the live device
    usb_pid: int  # USB idProduct (vendor is 0x84EF on both)

    @property
    def body_len(self) -> int:
        return self.prst_len - BODY_OFF


GP50 = DeviceProfile(
    "gp50", "GP-50", HEADER_GP50, 552, DEVTAG_GP50, "fxid_ring.json", "GP-50", 0x018A
)
GP5 = DeviceProfile(
    "gp5", "GP-5", HEADER_GP5, 507, DEVTAG_GP5, "fxid_ring_gp5.json", "GP-5", 0x0184
)
DEVICES = {p.key: p for p in (GP50, GP5)}


def profile_for(key: str) -> DeviceProfile:
    try:
        return DEVICES[key]
    except KeyError:
        raise ValueError(f"unknown device {key!r} (known: {sorted(DEVICES)})")


def detect(prst: bytes) -> DeviceProfile:
    """Identify a .prst's device from its header (then length as a fallback)."""
    for p in DEVICES.values():
        if prst[: len(p.header)] == p.header:
            return p
    for p in DEVICES.values():
        if len(prst) == p.prst_len:
            return p
    raise ValueError(f"unrecognized .prst (len {len(prst)}, header {prst[:6].hex()})")


# --- CRC (shared by the file format and the SysEx wire packets) ---------------


def crc8(data, init: int = 0) -> int:
    """CRC-8, poly 0x07 (CRC-8/SMBUS), no reflection, no final XOR."""
    c = init
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def refix_crc(b: bytearray) -> None:
    """Recompute the file CRC in place after any body/name edit."""
    b[CRC_OFF] = crc8(bytes(b[CRC_OFF + 1 :]))


def check_length(prst: bytes, profile: Optional[DeviceProfile] = None) -> None:
    """Validate a .prst's length. With no profile, accept any known device;
    with one, require exactly that device's length."""
    if profile is not None:
        if len(prst) != profile.prst_len:
            raise ValueError(
                f"expected a {profile.prst_len}-byte {profile.name} .prst, "
                f"got {len(prst)}"
            )
        return
    detect(prst)  # raises ValueError if the length/header matches no known device


# --- name codec ----------------------------------------------------------------


def read_name(prst: bytes) -> str:
    return prst[NAME_OFF:BODY_OFF].split(b"\0")[0].decode("latin1", "replace").strip()


def write_name(b: bytearray, name: str) -> None:
    """Overwrite the 16-byte name region in place (does NOT refix the CRC)."""
    b[NAME_OFF:BODY_OFF] = name.encode("latin1", "replace")[:NAME_LEN].ljust(
        NAME_LEN, b"\0"
    )


def rebuild(name: str, body: bytes, profile: DeviceProfile = GP50) -> bytes:
    """Full .prst from a device read: name (0x40 read) + body (0x41). Defaults to
    GP-50; pass profile=GP5 for a 466-byte GP-5 body."""
    if len(body) != profile.body_len:
        raise ValueError(
            f"expected a {profile.body_len}-byte {profile.name} body, got {len(body)}"
        )
    out = bytearray(profile.header + b"\x00" + SENTINEL + b"\0" * NAME_LEN + body)
    write_name(out, name)
    refix_crc(out)
    return bytes(out)


# --- body records ----------------------------------------------------------------


def models_offset(b: bytes) -> int:
    """Offset of the first model record (after the REC_MODELS magic), or -1."""
    i = b.find(REC_MODELS)
    return i + 4 if i >= 0 else -1


def model_records(b: bytes) -> list:
    """The 10 per-block model records as (idx, cat, fxlow):
    idx = b0 (slot/index for N->S and AMP), cat = category byte, fxlow = the
    3-byte little-endian model index. fxid = (cat << 24) | fxlow."""
    base = models_offset(b)
    if base < 0:
        return []
    out = []
    for k in range(N_BLOCKS):
        r = b[base + k * 4 : base + k * 4 + 4]
        fxlow = r[0] | (r[1] << 8) | (r[2] << 16)
        out.append((r[0], r[3], fxlow))
    return out


def model_rec_offset(b: bytes, category: int) -> Optional[int]:
    """Offset of the 4-byte model record whose category matches, or None."""
    base = models_offset(b)
    if base < 0:
        return None
    for k in range(N_BLOCKS):
        if b[base + k * 4 + 3] == category:
            return base + k * 4
    return None


def bypass_mask(b: bytes) -> int:
    """u32 bitmask: bit k = block k active (BLOCK_NAMES order)."""
    i = b.find(REC_BYPASS)
    return struct.unpack_from("<I", b, i + 4)[0] if i >= 0 else 0


def bypass_offset(b: bytes) -> int:
    """Offset of the bypass u32 (after the REC_BYPASS magic), or -1."""
    i = b.find(REC_BYPASS)
    return i + 4 if i >= 0 else -1


def param_floats(b: bytes) -> list:
    """The 80-float parameter array: floats[block_index*8 + algId]."""
    i = b.find(REC_PARAMS)
    if i < 0:
        return [0.0] * N_PARAM_SLOTS
    return list(struct.unpack_from(f"<{N_PARAM_SLOTS}f", b, i + 4))


def params_offset(b: bytes) -> int:
    """Offset of the first param float (after the REC_PARAMS magic), or -1."""
    i = b.find(REC_PARAMS)
    return i + 4 if i >= 0 else -1


FS_TRAILER_GP5 = bytes([0x03, 0x00, 0x08, 0x00])  # GP-5 trailer (8-byte payload)


def fs_offset(b: bytes) -> int:
    """Offset of the footswitch mask pair ([FS1 u32][FS2 u32]) in the trailer.
    Handles both the GP-50 (10-byte) and GP-5 (8-byte) trailer records."""
    for magic in (FS_TRAILER, FS_TRAILER_GP5):
        i = b.rfind(magic)
        if i >= 0:
            return i + 4
    return -1
