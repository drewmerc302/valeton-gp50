#!/usr/bin/env python3
"""GP-50 host->device write TRANSPORT (packet builder) + a hard-gated sender.

The wire format is cracked (see re/SNAPTONE_PROTOCOL.md): each packet is
  BUF = [crc, cmd, index, length, *payload]     # crc = CRC-8/0x07 over BUF, slot 0
  wire = F0 + nibble-expand(BUF, hi-first) + F7
This module builds byte-identical packets (verified below against a real Suite
capture) but DOES NOT send speculative writes: send_stream() refuses unless the
caller passes confirm=True AND every packet was validated against captured bytes.

SAFETY: the pedal wedged once from unvalidated traffic. Never send a guessed
write command. A patch write needs its command byte + slot addressing decoded
from a Suite patch-import capture first (see re/DEVICE_WRITE.md)."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch.prst_format import (  # noqa: E402
    NAME_OFF,
    DeviceProfile,
    check_length,
    crc8,
    detect,
)

# Which devices' WRITE protocol is capture-verified. The read protocol (0x40/0x41)
# is confirmed shared, and the .prst container + CRC are identical, so the write
# format below is very likely shared too — but the write COMMAND byte, the 0x11 0x4F
# header, and the 19-byte block size were only ever confirmed against GP-50 Suite
# captures. Until a GP-5 patch-import is captured, a GP-5 write reuses the GP-50
# constants on faith; send_stream() refuses it unless explicitly allowed. See
# re/DEVICE_WRITE.md.
WRITE_VERIFIED = {"gp50": True, "gp5": False}


def build_packet(cmd: int, index: int, payload: bytes) -> list:
    """Return wire bytes (incl F0/F7) for one host->device packet."""
    buf = [0, cmd & 0xFF, index & 0xFF, len(payload) & 0xFF, *payload]
    buf[0] = crc8(buf)
    wire = [0xF0]
    for b in buf:
        wire += [b >> 4, b & 0x0F]
    wire.append(0xF7)
    return wire


PATCH_WRITE_CMD = 0x1D  # host->device patch write (decoded from Suite import captures)
PATCH_BLOCK = 19  # payload bytes per write block
PATCH_HDR = bytes([0x11, 0x4F])  # constant marker before the slot byte


def _expected_payload_len(profile: DeviceProfile) -> int:
    """Reassembled write payload = 6-byte header + prst[NAME_OFF:]."""
    return 6 + (profile.prst_len - NAME_OFF)


def build_patch_write_stream(prst: bytes, slot: int) -> list:
    """Reconstruct Suite's exact patch-import stream for writing `prst` to `slot`.

    Validated byte-for-byte (29/29) against two real GP-50 Suite captures (US Lead
    -> slots 1 and 99). Device-agnostic in shape — the payload is prst[NAME_OFF:],
    so a 507-byte GP-5 .prst yields a shorter stream automatically. Format:
      device_payload = [0x11, 0x4F, slot, 0x00, 0x00, 0x00] + prst[0x19:]
      (the 6-byte header replaces the .prst body's leading FF FF FF FF sentinel;
       `slot` is the 0-based device index)
    streamed as PATCH_WRITE_CMD in 19-byte blocks, index 0..N.
    Returns wire-byte packets (each incl F0/F7). Does NOT send — see send_stream."""
    if not 0 <= slot <= 0xFF:
        raise ValueError(f"slot out of range: {slot}")
    check_length(prst, detect(prst))  # a recognized GP-5 or GP-50 .prst
    payload = PATCH_HDR + bytes([slot, 0x00, 0x00, 0x00]) + prst[NAME_OFF:]
    return [
        build_packet(PATCH_WRITE_CMD, i // PATCH_BLOCK, payload[i : i + PATCH_BLOCK])
        for i in range(0, len(payload), PATCH_BLOCK)
    ]


def _nib_decode(mid):
    return [(mid[i] << 4) | mid[i + 1] for i in range(0, len(mid) - 1, 2)]


def validate_stream(packets: list) -> tuple:
    """Confirm a patch-write stream is well-formed before sending (the gate for
    arbitrary edited patches, since they can't match a Suite capture). Checks every
    packet's CRC, that cmd is the patch-write command, indices are contiguous from 0,
    and the reassembled payload has the expected header + a length matching a known
    device (GP-50 or GP-5). Returns (ok, reason)."""
    payload = bytearray()
    for i, w in enumerate(packets):
        if not w or w[0] != 0xF0 or w[-1] != 0xF7:
            return False, f"packet {i}: not F0..F7 framed"
        buf = _nib_decode(w[1:-1])
        if len(buf) < 4:
            return False, f"packet {i}: truncated"
        crc, cmd, index, length = buf[0], buf[1], buf[2], buf[3]
        if crc8(buf[1:]) != crc:
            return False, f"packet {i}: bad CRC"
        if cmd != PATCH_WRITE_CMD:
            return (
                False,
                f"packet {i}: cmd {cmd:#04x} != patch-write {PATCH_WRITE_CMD:#04x}",
            )
        if index != i:
            return False, f"packet {i}: non-contiguous index {index}"
        if length != len(buf) - 4:
            return False, f"packet {i}: length {length} != payload {len(buf) - 4}"
        payload += bytes(buf[4 : 4 + length])
    from patch.prst_format import DEVICES

    valid_lens = {_expected_payload_len(p): p.name for p in DEVICES.values()}
    if len(payload) not in valid_lens:
        return (
            False,
            f"payload {len(payload)} bytes, expected one of "
            f"{sorted(valid_lens)} (GP-50/GP-5)",
        )
    if payload[:2] != PATCH_HDR:
        return False, f"payload header {payload[:2].hex()} != {PATCH_HDR.hex()}"
    return True, "ok"


def verify_against_capture(path: str) -> tuple:
    """Rebuild every host->device packet in a MIDI Monitor capture from its
    decoded (cmd,index,payload) and confirm it matches the captured wire bytes."""
    ok = bad = 0
    for ln in open(path, errors="ignore"):
        if "F7" not in ln:
            continue
        is_hd = ("To " in ln or "to " in ln) and "From" not in ln
        if not is_hd:
            continue
        m = re.search(r"F0((?:\s+[0-9A-Fa-f]{2})+)\s+F7", ln)
        if not m:
            continue
        wire = [0xF0] + [int(x, 16) for x in m.group(1).split()] + [0xF7]
        buf = _nib_decode(wire[1:-1])
        if len(buf) < 4:
            continue
        rebuilt = build_packet(buf[1], buf[2], bytes(buf[4 : 4 + buf[3]]))
        if rebuilt == wire:
            ok += 1
        else:
            bad += 1
    return ok, bad


def _infer_device_key(packets: list):
    """Best-effort device key from a stream's reassembled payload length, or None."""
    from patch.prst_format import DEVICES

    total = 0
    for w in packets:
        if not w or w[0] != 0xF0 or w[-1] != 0xF7:
            return None
        buf = _nib_decode(w[1:-1])
        if len(buf) >= 4:
            total += buf[3]  # per-packet payload length
    for p in DEVICES.values():
        if _expected_payload_len(p) == total:
            return p.key
    return None


def send_stream(
    port_name,
    packets,
    confirm=False,
    validated=False,
    ack_wait=0.15,
    allow_unverified=False,
):
    """Send pre-built, VALIDATED packets to the device. Refuses otherwise.

    packets: list of wire-byte lists. Requires confirm=True and validated=True.
    Also refuses a stream for a device whose write protocol is not capture-verified
    (WRITE_VERIFIED) unless allow_unverified=True — the GP-5 write command/header are
    assumed identical to the GP-50's but have never been confirmed against a GP-5
    capture, and blind-sending a wrong opcode has wedged this hardware before.
    Paces like Suite: after each block, wait for the device's ACK sysex (up to
    ack_wait s) before the next block — the device has a shallow MIDI queue and
    overrunning it has wedged the pedal. Returns the count of ACKs seen."""
    if not (confirm and validated):
        raise RuntimeError(
            "refusing to send: device writes require confirm=True and packets "
            "validated byte-for-byte against a Suite capture (see re/DEVICE_WRITE.md)"
        )
    if not allow_unverified:
        key = _infer_device_key(packets)
        if key is not None and not WRITE_VERIFIED.get(key, False):
            raise RuntimeError(
                f"refusing to send: the {key} patch-write protocol is not "
                f"capture-verified (write command/header assumed from the GP-50). "
                f"Capture a GP-5 Suite import to confirm, or pass "
                f"allow_unverified=True to override at your own risk."
            )
    import time
    import mido  # noqa: local import so the builder works without MIDI installed

    acks = 0
    with mido.open_input(port_name) as inp, mido.open_output(port_name) as out:
        time.sleep(0.1)
        for _ in inp.iter_pending():
            pass  # drain
        for w in packets:
            out.send(mido.Message("sysex", data=w[1:-1]))
            t0 = time.time()
            while time.time() - t0 < ack_wait:
                if any(m.type == "sysex" for m in inp.iter_pending()):
                    acks += 1
                    break
                time.sleep(0.005)
    return acks


if __name__ == "__main__":
    cap = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
    )
    ok, bad = verify_against_capture(cap)
    print(
        f"builder reproduces captured host->device packets: {ok} ok, {bad} mismatched"
    )
