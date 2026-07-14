#!/usr/bin/env python3
"""Select a preset on the connected device via MIDI Program Change, and
optionally read its live state back. Runs in .venv-midi. Emits one JSON line for
app/device_io.py.

  python select_patch.py --slot N [--refresh]

Program Change is NON-DESTRUCTIVE — it only changes which preset is active, it
cannot overwrite or corrupt anything — so this needs no confirm/gate (unlike a
patch write). Works on both devices: the GP-50 is confirmed (every scan selects
this way); the GP-5 responds to standard MIDI PC too.

--refresh also reads the just-selected preset's name (0x40) + body (0x41) — the
same one-at-a-time read the full scan uses — and returns the rebuilt .prst as
base64 so the caller can refresh that one slot's cache without a whole rescan."""

import argparse
import base64
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import device_protocol, live_read, prst_format

CATSEL, NAME_SEL, BODY_SEL = 0x12, 0x40, 0x41
POST_PC = 0.30  # settle after the preset switch before reading (matches scan_bank)


def _read(inp, out, selector, wait=2.5, idle=0.15):
    """Send a read request for `selector`, collect the reply stream, reassemble."""
    import mido

    req = [0, 0x01, 0x00, 0x02, CATSEL, selector]
    req[0] = live_read.crc8(req)
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


def _read_slot(port, profile, slot):
    """PC-selected slot's rebuilt .prst, or None if the read didn't land clean."""
    import mido

    with mido.open_input(port) as inp, mido.open_output(port) as out:
        time.sleep(0.15)
        names = dict(live_read.split_names(_read(inp, out, NAME_SEL)))
        out.send(mido.Message("program_change", program=slot & 0x7F))
        time.sleep(POST_PC)
        blob = _read(inp, out, BODY_SEL)
        body = blob[2:] if blob[:2] == bytes([CATSEL, BODY_SEL]) else blob
        if len(body) != profile.body_len:  # race/short -> one retry with more settle
            time.sleep(0.4)
            blob = _read(inp, out, BODY_SEL)
            body = blob[2:] if blob[:2] == bytes([CATSEL, BODY_SEL]) else blob
        if len(body) != profile.body_len:
            return None, names.get(slot)
        nm = names.get(slot, f"slot{slot}")
        return prst_format.rebuild(nm, body, profile), nm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, required=True)
    ap.add_argument("--refresh", action="store_true", help="also read live state back")
    a = ap.parse_args()
    try:
        if not 0 <= a.slot <= 99:
            raise ValueError(f"slot {a.slot} out of range 0..99")
        port, profile = live_read.find_port_optional()
        if port is None:
            raise RuntimeError("no Valeton device found — connect it and close Suite")
        dev = {"key": profile.key, "name": profile.name}
        if a.refresh:
            prst, nm = _read_slot(port, profile, a.slot)
            extra = {"name": nm}
            if prst is not None:
                extra["prst_b64"] = base64.b64encode(prst).decode("ascii")
                extra["refreshed"] = True
            else:
                extra["refreshed"] = False  # selected fine, read didn't land
            result = device_protocol.select_result(True, a.slot, device=dev)
            result.update(extra)
        else:
            import mido

            with mido.open_output(port) as out:
                out.send(mido.Message("program_change", program=a.slot & 0x7F))
            result = device_protocol.select_result(True, a.slot, device=dev)
    except Exception as e:  # noqa: BLE001 — surface any failure as JSON
        result = device_protocol.select_result(
            False, a.slot, error=f"{type(e).__name__}: {e}"
        )
    device_protocol.emit(result)


if __name__ == "__main__":
    main()
