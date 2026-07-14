#!/usr/bin/env python3
"""Find the minimum safe post-Program-Change settle: read scattered slots at a given
delay and verify each rebuilt body matches its export. One persistent port.

  python cadence_test.py <post_pc_delay>   # e.g. 0.35
"""

import sys
import os
import time
import glob
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import live_read
import mido

CATSEL, BODY_SEL = 0x12, 0x41
DELAY = float(sys.argv[1]) if len(sys.argv) > 1 else 0.35
SLOTS = [2, 7, 40, 55, 88, 3, 4]

ref = {}
for p in glob.glob(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "presetExports", "*.prst")
):
    m = re.match(r"(\d+)-", os.path.basename(p))
    if m:
        ref[int(m.group(1))] = open(p, "rb").read()[0x29:]

req = [0, 0x01, 0x00, 0x02, CATSEL, BODY_SEL]
req[0] = live_read.crc8(req)


def read(inp, out, wait=2.5, idle=0.12):
    for _ in inp.iter_pending():
        pass
    out.send(mido.Message("sysex", data=live_read.to_wire_data(req)))
    replies, t0, last = [], time.time(), time.time()
    while time.time() - t0 < wait:
        got = False
        for m in inp.iter_pending():
            if m.type == "sysex":
                replies.append(live_read.nib_decode(list(m.bytes())[1:-1]))
                got = True
        if got:
            last = time.time()
        elif time.time() - last > idle and replies:
            break
        time.sleep(0.01)
    banks = live_read.reassemble(replies)
    b = max(banks.values(), key=len) if banks else b""
    return b[2:] if b[:2] == bytes([CATSEL, BODY_SEL]) else b


t_start = time.time()
with mido.open_input(live_read.PORT) as inp, mido.open_output(live_read.PORT) as out:
    time.sleep(0.2)
    for slot in SLOTS:
        out.send(mido.Message("program_change", program=slot & 0x7F))
        time.sleep(DELAY)
        body = read(inp, out)
        ok = slot in ref and body == ref[slot]
        print(f"slot {slot:>2}: {len(body)}b  correct={ok}")
        time.sleep(0.05)
print(
    f"delay={DELAY}s  total {time.time() - t_start:.1f}s for {len(SLOTS)} slots "
    f"(~{(time.time() - t_start) / len(SLOTS) * 100:.0f}s for 100)"
)
