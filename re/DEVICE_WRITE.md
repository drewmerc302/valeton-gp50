# GP-50 direct device-write protocol — status

Goal: write edited patches to the pedal directly (no Suite round-trip).

## GP-5 status (2026-07-14)

The write path in `patch/device_write.py` is now device-parametric: the payload is
`prst[NAME_OFF:]`, so a 507-byte GP-5 .prst builds a valid 26-packet stream (vs the
GP-50's 29) and `validate_stream` accepts either device's payload length. **BUT the
write COMMAND (0x1D), the `0x11 0x4F` header, and the 19-byte block size were only
ever confirmed against GP-50 Suite captures.** They are almost certainly shared (the
read protocol 0x40/0x41 is confirmed shared, the .prst container + CRC are identical),
but until a GP-5 Suite patch-import is captured this is unverified. `WRITE_VERIFIED =
{gp50: True, gp5: False}` gates it: `send_stream` (and the CLI / device_io / API)
refuse a GP-5 write unless `allow_unverified=True`. To verify: capture a GP-5 import
with MIDI Monitor, run `device_write.verify_against_capture(path)`, and flip
`WRITE_VERIFIED["gp5"]` once it reproduces byte-for-byte.

### Cross-project corroboration (2026-07-14, from public GP-5 repos)

Read the actual source of the community GP-5 projects (helvecioneto/gp5-wc's
`ble_sysex.json`, solispensa/Chocotone's `GP5Protocol.cpp/.h`, Builty/
TonexOneController). What they prove vs. what stays open:

**Proven identical to our GP-50 (mathematically, not by assertion):**
- Our `prst_format.crc8` (CRC-8/0x07, init 0) reproduces all 6 of gp5-wc's GP-5
  SysEx CRC bytes exactly. Nibble/"addzero" hi-first encoding + `F0..F7` framing
  match. (`gp5_crc8` in Chocotone is the same poly-0x07 loop.)
- GP-5 `request_patch_data` decodes to `[0x09,0x01,0x00,0x02,0x12,0x41]` —
  byte-identical to our `live_read.read_bank(0x41)`. Read selectors 0x40 (names),
  0x41 (body), 0x24 (snaptone), 0x20 (IR) all match. Message type 0x01=command,
  0x02=response, same as ours.
- The host->device edit command envelope `[0x11, 0x4X, ...]` is a GP-5 family:
  0x43 change-patch(select), 0x47 change-effect, 0x48 change-param, 0x49
  toggle-block (all cmd=0x01, concrete bytes in gp5-wc). Our patch-WRITE header
  `[0x11, 0x4F]` fits this family (0x4F is an unused slot in the observed set).

**Still open (the gate stays):** NO public repo uploads a full preset — they are
footswitch/controllers that SELECT patches (CC or `[0x11,0x43]`) and edit blocks
in place (`[0x11,0x47/0x48/0x49]`). So our bulk patch-write specifics — cmd `0x1D`
(vs. the cmd=0x01 the edit commands use) and the 19-byte chunking — are NOT
confirmed for the GP-5 by anyone. Confidence rose from "assumed" to "transport +
read + command-family proven shared; only the bulk-write opcode/chunking
unconfirmed." Not enough to flip the gate.

**Alternate GP-5 write route (parked, NOT the plan):** a patch could be rebuilt on
the selected slot by streaming the documented in-place edit commands (`[0x11,0x47]`
per block model, `[0x11,0x48]` per param, `[0x11,0x49]` per toggle) — every one has
concrete confirmed bytes. BUT this would be a *second, different* write engine, and
the design preference is ONE unified write path across both devices, not two. So
this stays a documented fallback only — reach for it solely if the bulk 0x1D write
turns out not to work on a GP-5 and can't be made to. Preferred path to unblock GP-5
writes remains: capture a GP-5 Suite import, confirm the bulk 0x1D stream against it.

Re-run the corroboration any time: `python re/probes/gp5_write_corroboration.py`.

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
