#!/usr/bin/env python3
"""Scan all (or a range of) presets off the device into .prst files, emitting one
JSON progress line per slot so the web app can show a progress bar.

Reading is inherently one-at-a-time (no bulk read exists — even Suite loops ~1s/slot):
per slot -> Program Change to select, settle, read 0x41 body, rebuild with the 0x40
name. Bodies are validated (must be 511 bytes) with one retry. ONE persistent port.

  python scan_bank.py [start] [end] [outdir]   # inclusive 0..99; default 0 99 device_scan/
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import live_read, prst_format
import mido

CATSEL, BODY_SEL = 0x12, 0x41
POST_PC = 0.30  # settle after preset switch (0.15 races; 0.25 clean; 0.30 = margin)
BODY_LEN = prst_format.BODY_LEN


def _read(inp, out, req, wait=2.5, idle=0.15):
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
    return max(banks.values(), key=len) if banks else b""


def _body(inp, out, body_req):
    blob = _read(inp, out, body_req)
    return blob[2:] if blob[:2] == bytes([CATSEL, BODY_SEL]) else blob


def emit(**kw):
    print(json.dumps(kw), flush=True)


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 99
    outdir = (
        sys.argv[3]
        if len(sys.argv) > 3
        else os.path.join(os.path.dirname(os.path.dirname(__file__)), "device_scan")
    )
    os.makedirs(outdir, exist_ok=True)

    body_req = [0, 0x01, 0x00, 0x02, CATSEL, BODY_SEL]
    body_req[0] = live_read.crc8(body_req)
    name_req = [0, 0x01, 0x00, 0x02, CATSEL, 0x40]
    name_req[0] = live_read.crc8(name_req)

    total = end - start + 1
    emit(event="start", total=total)
    written = errors = 0
    with (
        mido.open_input(live_read.PORT) as inp,
        mido.open_output(live_read.PORT) as out,
    ):
        time.sleep(0.2)
        names = dict(live_read.split_names(_read(inp, out, name_req)))
        time.sleep(0.2)
        for i, slot in enumerate(range(start, end + 1)):
            out.send(mido.Message("program_change", program=slot & 0x7F))
            time.sleep(POST_PC)
            body = _body(inp, out, body_req)
            if len(body) != BODY_LEN:  # race/short -> one retry with more settle
                time.sleep(0.4)
                body = _body(inp, out, body_req)
            nm = names.get(slot, f"slot{slot}")
            if len(body) != BODY_LEN:
                errors += 1
                emit(
                    event="slot",
                    i=i,
                    slot=slot,
                    name=nm,
                    ok=False,
                    done=i + 1,
                    total=total,
                )
                continue
            prst = prst_format.rebuild(nm, body)
            safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in nm)
            open(os.path.join(outdir, f"{slot:02d}-{safe}.prst"), "wb").write(prst)
            written += 1
            emit(
                event="slot", i=i, slot=slot, name=nm, ok=True, done=i + 1, total=total
            )
            time.sleep(0.05)
    emit(event="done", written=written, errors=errors, outdir=outdir)


if __name__ == "__main__":
    main()
