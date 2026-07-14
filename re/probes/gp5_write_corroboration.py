#!/usr/bin/env python3
"""GP-5 write-protocol corroboration from public community projects (2026-07-14).

Question: without a physical GP-5, can another project confirm the opcodes our
GP-5 write path assumes (cmd 0x1D, header 0x11 0x4F, 19-byte chunks, CRC-8/0x07)?

Sources read (host->device SysEx, verbatim):
  - helvecioneto/gp5-wc  ble_sysex.json   (concrete GP-5 SysEx byte strings)
  - solispensa/Chocotone GP5Protocol.cpp/.h (gp5_crc8 poly 0x07; MSG_TYPE 0x01/0x02;
    FUNC 0x40 names / 0x41 params; edit-command family)
  - Builty/TonexOneController MidiCommands.md (CC map; same function codes)

This script re-proves the transport match with OUR crc8 and shows exactly what is
and isn't confirmed. Run: python re/probes/gp5_write_corroboration.py

RESULT (see re/DEVICE_WRITE.md "Cross-project corroboration"):
  PROVEN identical: CRC-8/0x07, nibble/addzero hi-first framing, the read protocol
  (cmd 0x01 + catsel 0x12 + selectors 0x40/0x41/0x24/0x20), and the [0x11,0x4X]
  edit-command family (0x43 select / 0x47 effect / 0x48 param / 0x49 toggle).
  Our patch-write header 0x11 0x4F fits that family.
  STILL OPEN: no public repo uploads a full preset (all are CC/edit controllers),
  so the bulk-write cmd 0x1D + 19-byte chunking are unconfirmed for the GP-5 ->
  the WRITE_VERIFIED["gp5"] gate stays shut.
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from patch import live_read  # noqa: E402
from patch.prst_format import crc8  # noqa: E402 — OUR GP-50 CRC-8/0x07

# helvecioneto/gp5-wc ble_sysex.json, verbatim (8080 = BLE-MIDI header; F0..F7 core).
GP5_WC_SYSEX = {
    "start_sync": "8080F0000E00010000000201020400F7",
    "request_patch_list": "8080f0030500010000000201020204f7",
    "request_ir_list": "8080F0020900010000000201020200F7",
    "request_current_patch_number": "8080F0000700010000000201020403F7",
    "request_patch_data": "8080f0000900010000000201020401f7",
}

# gp5-wc host->device edit-command family (command_template, pre-addzero real bytes).
GP5_WC_EDIT_CMDS = {
    "change_patch (select)": "0100061143{SLOT}000000",
    "change_effect": "01000e11470{BLOCK}0000000{BLOCK}000000{EFFECT}",
    "change_parameter": "01000e1148{BLOCK}000000{PARAM}000000{FLOAT}",
    "toggle_block": "01000a11490{EFFECT}0000000{STATUS}000000",
}


def nib_decode(transmitted):
    return [
        (transmitted[i] << 4) | transmitted[i + 1]
        for i in range(0, len(transmitted) - 1, 2)
    ]


def parse(hexstr):
    b = bytes.fromhex(hexstr)
    return nib_decode(list(b[b.index(0xF0) + 1 : b.rindex(0xF7)]))


def main():
    print("=== 1. OUR crc8 reproduces gp5-wc's GP-5 CRC bytes? ===")
    all_ok = True
    for name, hx in GP5_WC_SYSEX.items():
        buf = parse(hx)
        stated, mine = buf[0], crc8([0] + buf[1:])
        ok = stated == mine
        all_ok &= ok
        print(
            f"  {name:30} CRC stated={stated:#04x} ours={mine:#04x} {'OK' if ok else 'FAIL'}"
        )
    print(f"  --> transport identical: {all_ok}")

    print("\n=== 2. GP-5 request_patch_data vs OUR read_bank(0x41) ===")
    gp5 = parse(GP5_WC_SYSEX["request_patch_data"])
    ours = live_read.build_request(0x41)
    print(f"  GP-5: {[hex(x) for x in gp5]}")
    print(f"  ours: {[hex(x) for x in ours]}")
    print(f"  --> byte-identical: {gp5 == ours}")

    print("\n=== 3. GP-5 [0x11, 0x4X] command family (our write uses 0x4F) ===")
    for name, tmpl in GP5_WC_EDIT_CMDS.items():
        # first 3 real bytes = cmd,index,len; bytes[3:5] = [0x11, subop]
        prefix = tmpl[:10]  # covers cmd,index,len,0x11,subop as hex
        subop = tmpl[8:10]
        print(f"  {name:26} envelope [0x11, 0x{subop}, ...]")
    print("  our GP-50 patch-write        envelope [0x11, 0x4F, slot, 0,0,0] + body")

    print("\n=== 4. Unconfirmed (gate stays) ===")
    print("  bulk patch-WRITE cmd 0x1D + 19-byte chunking: no public repo uploads a")
    print("  full preset. WRITE_VERIFIED['gp5'] must stay False until a GP-5 Suite")
    print("  patch-import is captured and verify_against_capture() reproduces it.")
    assert all_ok and gp5 == ours, "transport corroboration FAILED"
    print("\ncorroboration holds.")


if __name__ == "__main__":
    main()
