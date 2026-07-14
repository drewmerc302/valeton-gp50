#!/usr/bin/env python3
"""Live GP-50 bank reader. SENDS ONLY cmd=0x01 read requests (byte-identical to
Valeton Suite's, CRC-8/0x07 verified) and collects the streamed name reply.
Read-only: never sends any write/commit opcode. Gated on a patch-dump self-test.

Usage:
  python live_read.py selftest          # send [0x12,0x40], expect 100 patch names
  python live_read.py scan              # probe candidate bank selectors
  python live_read.py read <hexsel>     # read one bank selector (e.g. 0x30)
"""

import os
import sys
import time
import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch.prst_format import GP5, GP50, crc8  # noqa: E402 — shared CRC-8/0x07

PORT = "GP-50"  # fallback name; find_port() resolves the actual connected device
READ_CMD = 0x01
CATSEL = 0x12  # constant data[0] in Suite's name-read requests


def find_port_optional():
    """(port_name, DeviceProfile) for a physically connected Valeton device, or
    (None, None) if none is present. Checks GP-50 first so its name isn't shadowed
    by the "GP-5" substring."""
    try:
        names = mido.get_input_names()
    except Exception:  # noqa: BLE001 — no backend/ports available
        return None, None
    for name in names:
        if "GP-50" in name:
            return name, GP50
    for name in names:
        if "GP-5" in name:
            return name, GP5
    return None, None


def find_port():
    """Resolve the connected Valeton MIDI port -> (port_name, DeviceProfile).
    The read protocol (selectors 0x40/0x41, CRC-8/0x07, nibble framing) is shared
    by the GP-5 and GP-50, so a scan/sync works on either once the right port is
    opened. Falls back to (PORT, GP50) when no device is found (legacy default)."""
    name, prof = find_port_optional()
    return (name, prof) if name else (PORT, GP50)


def build_request(selector):
    buf = [0, READ_CMD, 0x00, 0x02, CATSEL, selector]
    buf[0] = crc8(buf)  # crc over buf with crc byte held 0
    return buf  # BUF; wire = F0 + nibble-expand + F7


def to_wire_data(buf):
    out = []
    for b in buf:
        out += [b >> 4, b & 0xF]
    return out  # mido wraps with F0/F7


def nib_decode(mid):
    return [(mid[i] << 4) | mid[i + 1] for i in range(0, len(mid) - 1, 2)]


# SAFETY: the GP-50 has a shallow MIDI input queue. Firing requests faster than it
# drains them WEDGES the firmware (needs a power cycle). Rules, learned the hard way:
#   - one request at a time; wait for its reply stream to go idle before the next
#   - SETTLE gap after every request; hard cap on requests per invocation
#   - NEVER blind-sweep a wide selector range. Use only the known bank selectors.
SETTLE = 0.5  # seconds of quiet after each read before the next request
MAX_REQUESTS = 12  # per invocation; refuse to exceed
KNOWN_SELECTORS = {
    0x40: "patches",
    0x24: "amp",
    0x20: "cab/IR",
    0x1C: "snaptone",
    0x41: "misc",
}
_sent = 0


def read_bank(selector, wait=2.0):
    global _sent
    if _sent >= MAX_REQUESTS:
        raise RuntimeError(
            f"request cap {MAX_REQUESTS} reached this run — stop and re-run deliberately"
        )
    _sent += 1
    buf = build_request(selector)
    replies = []
    port, _profile = find_port()
    with mido.open_input(port) as inp, mido.open_output(port) as out:
        time.sleep(0.15)
        for _ in inp.iter_pending():
            pass  # drain
        out.send(mido.Message("sysex", data=to_wire_data(buf)))
        t0 = time.time()
        last = t0
        while time.time() - t0 < wait:
            got = False
            for m in inp.iter_pending():
                if m.type == "sysex":
                    replies.append(nib_decode(list(m.bytes())[1:-1]))
                    got = True
            if got:
                last = time.time()
            elif time.time() - last > 0.4 and replies:
                break  # stream idle -> done
            time.sleep(0.02)
    time.sleep(SETTLE)  # let the device fully drain before any next request
    return buf, replies


def reassemble(replies):
    # group by reply cmd (buf[1]); the streaming bank cmd has many chunks w/ incrementing idx
    from collections import defaultdict

    by_cmd = defaultdict(list)
    for b in replies:
        if len(b) >= 4:
            by_cmd[b[1]].append((b[2], b[4:]))  # (idx, data)
    out = {}
    for cmd, chunks in by_cmd.items():
        chunks.sort()
        data = []
        for idx, d in chunks:
            data += d
        out[cmd] = bytes(data)
    return out


def split_names(blob, hdr=2, rec=20):
    # stream = [2-byte selector echo] + records of [u32le index][16-byte name]
    import struct

    names = []
    i = hdr
    while i + rec <= len(blob):
        idx = struct.unpack_from("<I", blob, i)[0]
        nm = blob[i + 4 : i + rec].split(b"\0")[0].decode("latin1", "replace").strip()
        names.append((idx, nm))
        i += rec
    return names


def show(selector, buf, replies):
    wire = "F0 " + " ".join(f"{x:02x}" for x in to_wire_data(buf)) + " F7"
    print(f"selector {selector:#04x}  request wire: {wire}")
    print(f"  {len(replies)} reply frames")
    banks = reassemble(replies)
    for cmd, blob in banks.items():
        cat = f"{cmd >> 4:02x} {cmd & 0xF:02x}"
        names = split_names(blob)
        print(
            f"  reply cmd={cmd:#04x} (cat {cat})  {len(blob)} bytes  ~{len(names)} names"
        )
        for slot, nm in names[:80]:
            print(f"      slot {slot:3}: {nm!r}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if mode == "selftest":
        buf, replies = read_bank(0x40)
        show(0x40, buf, replies)
        banks = reassemble(replies)
        names = split_names(banks.get(0x6A, b""))
        ok = any("GreatPedal" in n for _, n in names)
        print(
            "\nSELF-TEST:",
            "PASS (patch names match)"
            if ok
            else "FAIL — investigate before proceeding",
        )
    elif mode == "scan":
        # only the known bank selectors, one at a time with SETTLE between (never sweep)
        for sel in KNOWN_SELECTORS:
            buf, replies = read_bank(sel, wait=2.5)
            show(sel, buf, replies)
            print()
    elif mode == "read":
        sel = int(sys.argv[2], 0)
        buf, replies = read_bank(sel, wait=3.0)
        show(sel, buf, replies)


if __name__ == "__main__":
    main()
