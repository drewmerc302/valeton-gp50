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

## The gap

`0x41` returns the **active** patch only. Reading an arbitrary slot needs the preset
selected first, and the active slot's identity (to fetch its name) isn't read yet.
- Request `buf[2]` (index) is NOT the slot: `0` returns the active body; other values
  error (`14 08 00`) or return nothing.
- **Program Change did not work and coincided with a wedge** — but the wedge was
  almost certainly the probe opening/closing the MIDI port per message in a tight loop
  (8+ cycles fast), not the PC itself. Recovered with the magic-button force-shutdown.

## Rules (learned twice now)
- One persistent port. One request. SETTLE between. NEVER a tight open/close loop.
- `patch/pc_read.py` was deleted: it cycled ports per message and wedged the pedal.

## Next (careful) experiments to close the gap
1. Single persistent in+out port: send ONE Program Change, wait ~1s, read `0x41` once,
   compare the rebuilt `.prst` to that slot's export. If bodies change with PC, full
   export = loop {PC n; settle; read 0x41} for n in 0..99.
2. If PC doesn't switch the active patch, look for a slot-parameterized body read
   (e.g. slot in the request payload `[0x12, 0x41, slot]`) — decoded from a Suite
   "read patch N" capture, same as the write was.

## Files
- `patch/reconstruct_prst.py` — rebuild(name, body) -> .prst (+ 100/100 self-check).
- `patch/probe_bodies.py`, `read_body.py`, `decode_body.py`, `save_active_body.py` —
  read/decode probes (single-request, safe).
