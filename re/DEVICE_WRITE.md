# GP-50 direct device-write protocol — status

Goal: write edited patches to the pedal directly (no Suite round-trip).

## Cracked and validated

**Write transport (host → device).** Every write packet is:
```
BUF  = [crc, cmd, index, length, *payload]     # crc = CRC-8/0x07 over BUF, slot 0
wire = F0 + nibble-expand(BUF, hi-first) + F7
```
`patch/device_write.py::build_packet` produces these and **reproduces a real Suite
capture byte-for-byte: 298/298** (`verify_against_capture`). So we can emit exactly
what Suite emits.

**SnapTone upload** (the one host→device write we've captured): a pure stream of
`cmd=0x92` data blocks, `index` 0…N, 19-byte payloads (last short), carrying the
~2.7 KB SnapTone. Device ACKs each with a fixed 16-byte status. No separate
control/commit packet appeared; the trailing `cmd=0x01` packets are Suite
re-reading the banks to refresh its UI.

## Patch write — CRACKED + VALIDATED (2026-07-13)

Decoded from two MIDI-Monitor captures of Suite importing the same US Lead `.prst`
to different slots (1 and 99). The Dart AOT hid it statically, but the wire tells all.

**Command `0x1D`.** Same transport as SnapTone, different command byte. Streamed as
19-byte payload blocks, index 0..28 (28×19 + 1), each nibble+CRC-8/0x07, wrapped
F0..F7. Device ACKs each block with a 16-byte status.

**Payload:**
```
device_payload = [0x11, 0x4F, slot, 0x00, 0x00, 0x00] + prst[0x19:]
```
- `0x11 0x4F` — constant marker (identical across both captures; not in the `.prst`).
- `slot` — target patch index, **0-based** (Suite "slot 1" → `0x00`, "slot 99" → `0x63`).
  NOTE: the two captures fit 0-based but are 1 apart on the display→byte mapping; the
  first real write must confirm the landing slot by read-back.
- The 6-byte header replaces the `.prst` body's leading `FF FF FF FF` sentinel; from
  `prst[0x19:]` on it is byte-identical to the file (527 bytes).

**Validation:** `patch/build_patch_write.py` rebuilds the whole stream from the US Lead
`.prst` + slot and matches the capture **29/29 packets byte-for-byte** (slot 1), and the
slot-99 header block matches. Builder lives in `device_write.build_patch_write_stream`.

No control/commit packet is needed — the `0x1D` stream self-commits; Suite's trailing
`cmd 0x01` reads (selectors 0x40/0x41) are just UI refresh.

## First real write — VERIFIED ✅ (2026-07-13)

Wrote US Lead to device **index 90** via `device_write.build_patch_write_stream` +
gated `send_stream` (`patch/do_write.py`). Result:
- 29/29 packets ACK'd by the device.
- Read-back: index 90 changed `'GP-50'` (empty default) → `'US Lead'`.
- Pedal fully responsive after — no wedge.
- **Slot byte = device index directly** (byte 0x5a → index 90). Resolved: the two
  import captures landed at indices 0 and 99, matching their slot bytes 0x00 / 0x63.

`send_stream` paces each block and waits for the device ACK (shallow-queue safety).

## Residual assumptions
- `0x11 0x4F` marker assumed constant across patches (tested with US Lead only; the
  write to a fresh slot succeeded, so it holds at least for this patch). Confirm by
  writing a different patch when convenient.

We will NOT send an unvalidated write: sending guessed traffic wedged the pedal once.
`send_stream` stays gated (confirm=True AND validated=True); first real write goes to an
empty scratch slot and is verified by read-back before touching any real patch.

## Safe path to finish it (one capture, then gated writer)

1. **Capture** Suite importing ONE `.prst` to a known empty slot (86–99), host→device,
   via MIDI Monitor spy — exactly how the SnapTone upload was captured. Read-only spy;
   no risk to the device.
2. **Decode** from the capture: the patch-write command byte, how the destination slot
   is addressed, block framing, and any control/commit packets. Diff the payload bytes
   against the 552-byte `.prst` to confirm it's the same body.
3. **Build** the patch-writer on `device_write.build_packet` (transport already proven).
4. **Validate before sending**: rebuild the whole stream for the *same* import and diff
   byte-for-byte against the captured Suite stream. Only a 100% match is allowed to send.
5. **Gate the send**: `device_write.send_stream` refuses unless `confirm=True` AND the
   packets were validated. First real write goes to an empty scratch slot; verify by
   read-back before ever touching a real patch.

## Files
- `patch/device_write.py` — packet builder (validated 298/298) + hard-gated sender.
- `re/SNAPTONE_PROTOCOL.md` — the write packet format + CRC.
- Capture to record next: `~/Desktop/valeton_patch_import.txt` (Suite patch import, spied).
