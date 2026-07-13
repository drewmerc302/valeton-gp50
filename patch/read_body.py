#!/usr/bin/env python3
"""Task #2: read a single patch BODY from the device via selector 0x41, with the
patch index in the request's index byte. Confirms 0x41 is a per-slot body read.

  python read_body.py <slot>
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import live_read

READ_CMD, CATSEL, BODY_SEL = 0x01, 0x12, 0x41


def read_body(slot: int, wait=4.0):
    buf = [0, READ_CMD, slot & 0xFF, 0x02, CATSEL, BODY_SEL]
    buf[0] = live_read.crc8(buf)
    replies = []
    import time
    import mido

    with (
        mido.open_input(live_read.PORT) as inp,
        mido.open_output(live_read.PORT) as out,
    ):
        time.sleep(0.15)
        for _ in inp.iter_pending():
            pass
        out.send(mido.Message("sysex", data=live_read.to_wire_data(buf)))
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
    time.sleep(live_read.SETTLE)
    banks = live_read.reassemble(replies)
    blob = max(banks.values(), key=len) if banks else b""
    return blob


slot = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0
blob = read_body(slot)
# strip the 2-byte [0x12,0x41] selector echo -> body
body = blob[2:] if blob[:2] == bytes([CATSEL, BODY_SEL]) else blob
name = body[6:22].split(b"\0")[0].decode("latin1", "replace") if len(body) > 22 else "?"
print(f"slot {slot}: {len(blob)} bytes blob, body {len(body)}; name-ish={name!r}")
print(f"  head: {body[:24].hex(' ')}")
