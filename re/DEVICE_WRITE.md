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

## The gap (why we can't write a patch yet)

The **patch** write is orchestrated in Suite's Dart AOT (`importPreset`,
`sendData`, `EventHandler_SendData`, `ImportPresetResult`, `importPresetIndexSuccess`)
— not a clean C export — so the **patch-write command byte, the target-slot
addressing, and the framing (control/commit) are not statically recoverable**, and
they are NOT the same as the SnapTone `0x92` data stream.

We will NOT guess them: sending an unvalidated write wedged the pedal once already.

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
