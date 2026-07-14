# GP-50 device READ protocol (patch bodies) — status

Goal: read patches off the pedal so the app doesn't depend on Suite `.prst` exports.

## Cracked + proven

**Names** — selector `0x40`: bank read, returns all 100 patch names (already used by
the "Sync" reader). Request `[crc, 0x01, 0x00, 0x02, 0x12, 0x40]`, nibble+CRC-8/0x07.

**Body** — selector `0x41`: returns the **currently active** patch body, 511 bytes.
Reassembled reply is tagged cmd `0x1b`, prefixed with a 2-byte `12 41` selector echo.
The body == `prst[0x29:]` exactly.

**Full `.prst` reconstruction** (`patch/reconstruct_prst.py`): a device patch =
name (`0x40`) + body (`0x41`). The `.prst` layout:
```
0x00:0x14  constant "GP-50" header
0x14       file CRC (CRC-8/0x07 over prst[0x15:])
0x15:0x19  FF FF FF FF sentinel
0x19:0x29  16-byte patch name        <- 0x40
0x29:      511-byte body             <- 0x41
```
`rebuild(name, body)` reproduces all 100 exported `.prst` files **byte-for-byte
(100/100)**, and reproduced the live `0x41` read of the active patch (US Lead).

## Reading arbitrary slots — SOLVED (2026-07-13)

`0x41` returns the **active** patch only. To read a specific slot: **MIDI Program
Change selects the preset**, then `0x41` reads it. Confirmed: PC 2 -> `0x41` returned
an exact match for `02-Star Night.prst`.

- Request `buf[2]` (index) is NOT the slot, and a slot byte in the payload
  (`[0x12,0x41,slot]`) is ignored — `0x41` always yields the active patch.
- **There is NO bulk-body read.** Even Valeton Suite's own "select all -> export"
  loops one preset at a time at ~1 s each (user-observed). Reading the full bank is
  inherently N single reads.
- **Cadence:** ~0.15 s post-PC settle RACES (bodies merge, corrupt); 0.25 s is clean;
  the scanner uses 0.30 s + a 511-byte length check with one retry. ~65-90 s for 100.

## Rules (learned twice)
- One persistent port for the whole run. One request at a time. SETTLE between. NEVER
  a tight open/close-per-message loop — that (not Program Change) wedged the pedal.
- Deleted `patch/pc_read.py`: it cycled ports per message and wedged the pedal.

## Shipped
- `patch/scan_bank.py` — full-bank scanner: per slot {PC; settle; read 0x41; rebuild};
  emits JSON progress; writes .prst to `device_scan/`. Verified live: 100/100, 0 errors.
- App: `POST /api/device/scan` + `GET /api/device/scan/status`; patchlib prefers
  `device_scan/` over `presetExports/`; Explorer "Scan presets from device" button
  with progress bar + confirm disclaimer.

## WebMIDI validation (beta-2 risk-gate — PASSED, 2026-07-14)
The read pipeline runs unchanged in a browser over WebMIDI (Chrome/Edge). Proven
live on the connected GP-50, no Python backend in the path:
- **Permission + ports:** `requestMIDIAccess({sysex:true})` granted; the GP-50
  appears as both a MIDI input and output.
- **Names (`0x40`):** the JS codec (`crc8`/`buildRequest`/nibble `toWire`/`nibDecode`/
  `reassemble`/`splitNames`, ported in `app/static/webmidi_probe.html`) read all
  100 names — byte-identical framing to `live_read.py`.
- **Select + body (`0x41`):** Program Change to slot 0, `0x41` read, strip the
  `12 41` echo -> 511-byte body, `PRST.rebuild(name, body)` (`app/static/prst.js`)
  -> a 552-byte `.prst` **byte-for-byte identical** to `select_patch.py --refresh`
  for the same slot.
So beta-2's read/select/convert can be a static WebMIDI page. Write is still
Python-only and deliberately unported (a bad write wedges the pedal).

## Files
- `app/static/prst.js` — the .prst format + GP-5<->GP-50 convert in JS; byte-for-byte
  vs the Python oracle over 102 presets (`app/tests/test_prst_js.mjs`).
- `app/static/webmidi_probe.html` — read-only WebMIDI probe (the risk-gate above).
- `patch/reconstruct_prst.py` — rebuild(name, body) -> .prst (+ 100/100 self-check).
- `patch/scan_bank.py` — production scanner.
- `patch/cadence_test.py` — settle-timing probe (single persistent port).
- `patch/probe_bodies.py`, `read_body.py`, `decode_body.py`, `save_active_body.py`,
  `slot_body_read.py`, `pc_select_read.py` — read/decode probes (single-request, safe).
