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
from typing import Optional

PRST_LEN = 552
BODY_LEN = 511

HEADER = bytes.fromhex("47502d3530000000000000000000000000000100")  # [0x00:0x14]
CRC_OFF = 0x14
SENTINEL = b"\xff\xff\xff\xff"  # [0x15:0x19]
NAME_OFF = 0x19
NAME_LEN = 16
BODY_OFF = 0x29  # NAME_OFF + NAME_LEN

REC_MODELS = bytes([0x03, 0x30, 0x28, 0x00])
REC_BYPASS = bytes([0x01, 0x30, 0x04, 0x00])
REC_PARAMS = bytes([0x04, 0x30, 0x40, 0x01])
FS_TRAILER = bytes([0x03, 0x00, 0x0A, 0x00])
SETTINGS_OFF = 0x55  # first group-0x20 patch-settings record

N_BLOCKS = 10
N_PARAM_SLOTS = 80  # N_BLOCKS x 8


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


def check_length(prst: bytes) -> None:
    if len(prst) != PRST_LEN:
        raise ValueError(f"expected a {PRST_LEN}-byte .prst, got {len(prst)}")


# --- name codec ----------------------------------------------------------------


def read_name(prst: bytes) -> str:
    return prst[NAME_OFF:BODY_OFF].split(b"\0")[0].decode("latin1", "replace").strip()


def write_name(b: bytearray, name: str) -> None:
    """Overwrite the 16-byte name region in place (does NOT refix the CRC)."""
    b[NAME_OFF:BODY_OFF] = name.encode("latin1", "replace")[:NAME_LEN].ljust(
        NAME_LEN, b"\0"
    )


def rebuild(name: str, body: bytes) -> bytes:
    """Full .prst from a device read: name (0x40 read) + 511-byte body (0x41)."""
    if len(body) != BODY_LEN:
        raise ValueError(f"expected a {BODY_LEN}-byte body, got {len(body)}")
    out = bytearray(HEADER + b"\x00" + SENTINEL + b"\0" * NAME_LEN + body)
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


def fs_offset(b: bytes) -> int:
    """Offset of the footswitch mask pair ([FS1 u32][FS2 u32]) in the trailer."""
    i = b.rfind(FS_TRAILER)
    return i + 4 if i >= 0 else -1
