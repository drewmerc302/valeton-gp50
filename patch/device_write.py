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

import re
import sys

POLY = 0x07


def crc8(data, init=0):
    c = init
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ POLY) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def build_packet(cmd: int, index: int, payload: bytes) -> list:
    """Return wire bytes (incl F0/F7) for one host->device packet."""
    buf = [0, cmd & 0xFF, index & 0xFF, len(payload) & 0xFF, *payload]
    buf[0] = crc8(buf)
    wire = [0xF0]
    for b in buf:
        wire += [b >> 4, b & 0x0F]
    wire.append(0xF7)
    return wire


def _nib_decode(mid):
    return [(mid[i] << 4) | mid[i + 1] for i in range(0, len(mid) - 1, 2)]


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


def send_stream(port_name, packets, confirm=False, validated=False):
    """Send pre-built, VALIDATED packets to the device. Refuses otherwise.
    packets: list of wire-byte lists. Requires confirm=True and validated=True."""
    if not (confirm and validated):
        raise RuntimeError(
            "refusing to send: device writes require confirm=True and packets "
            "validated byte-for-byte against a Suite capture (see re/DEVICE_WRITE.md)"
        )
    import mido  # noqa: local import so the builder works without MIDI installed

    with mido.open_output(port_name) as out:
        for w in packets:
            out.send(mido.Message("sysex", data=w[1:-1]))


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
