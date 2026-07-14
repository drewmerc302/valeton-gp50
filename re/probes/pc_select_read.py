#!/usr/bin/env python3
"""GENTLE single-shot: does MIDI Program Change select the active preset?
ONE persistent port. Send ONE Program Change, wait, do ONE 0x41 body read. Nothing
else — no loops, no open/close churn (that wedged the pedal before).

  python pc_select_read.py <program>   # default 2 (Star Night)
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import live_read
import mido

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 2
READ_CMD, CATSEL, BODY_SEL = 0x01, 0x12, 0x41


def main():
    req = [0, READ_CMD, 0x00, 0x02, CATSEL, BODY_SEL]
    req[0] = live_read.crc8(req)
    replies = []
    with (
        mido.open_input(live_read.PORT) as inp,
        mido.open_output(live_read.PORT) as out,
    ):
        time.sleep(0.2)
        for _ in inp.iter_pending():
            pass  # drain
        out.send(mido.Message("program_change", program=TARGET & 0x7F))  # select preset
        time.sleep(1.0)  # let it switch
        for _ in inp.iter_pending():
            pass  # drain any switch chatter
        out.send(
            mido.Message("sysex", data=live_read.to_wire_data(req))
        )  # read active body
        t0 = last = time.time()
        while time.time() - t0 < 3.0:
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
    body = blob[2:] if blob[:2] == bytes([CATSEL, BODY_SEL]) else blob
    open("/tmp/pc_body.bin", "wb").write(body)
    print(
        f"PC {TARGET}: body {len(body)} bytes -> /tmp/pc_body.bin; head={body[:16].hex(' ')}"
    )


if __name__ == "__main__":
    main()
