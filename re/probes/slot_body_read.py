#!/usr/bin/env python3
"""Test a SLOT-ADDRESSED body read: put the slot in the request PAYLOAD
([0x12, 0x41, slot], length 3) instead of the index byte. If this returns any slot's
body directly — no Program Change, no active-preset change — that's how Suite reads
the whole bank fast. One persistent port, one request per slot, settle between."""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import live_read
import mido

CATSEL, BODY_SEL = 0x12, 0x41


def req_for(slot, payload):
    buf = [0, 0x01, 0x00, len(payload)] + payload
    buf[0] = live_read.crc8(buf)
    return buf


def read(inp, out, buf, wait=3.0):
    for _ in inp.iter_pending():
        pass
    out.send(mido.Message("sysex", data=live_read.to_wire_data(buf)))
    replies = []
    t0 = last = time.time()
    while time.time() - t0 < wait:
        got = False
        for m in inp.iter_pending():
            if m.type == "sysex":
                replies.append(live_read.nib_decode(list(m.bytes())[1:-1]))
                got = True
        if got:
            last = time.time()
        elif time.time() - last > 0.4 and replies:
            break
        time.sleep(0.02)
    banks = live_read.reassemble(replies)
    return max(banks.values(), key=len) if banks else b""


def identify(body):
    import glob
    import re

    body = body[2:] if body[:2] == bytes([CATSEL, BODY_SEL]) else body
    for p in glob.glob(
        os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "presetExports", "*.prst"
        )
    ):
        if open(p, "rb").read()[0x29:] == body:
            return os.path.basename(p), len(body)
    return f"(no exact match, {len(body)}b, head {body[:8].hex()})", len(body)


with mido.open_input(live_read.PORT) as inp, mido.open_output(live_read.PORT) as out:
    time.sleep(0.2)
    for slot in [2, 7, 40]:
        blob = read(inp, out, req_for(slot, [CATSEL, BODY_SEL, slot]))
        who, n = identify(blob)
        print(f"payload [12 41 {slot:02x}] -> {n}b: {who}")
        time.sleep(live_read.SETTLE)
