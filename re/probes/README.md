# re/probes/ — archived RE probe scripts

**Not product code.** These are the one-off probes and parallel decoders used while
reverse-engineering the GP-50 (.prst format, read/write protocol, CRC). They were
moved out of `patch/` so the runtime surface is unambiguous.

The hardened runtime modules live in `patch/`:
`live_read`, `device_write`, `scan_bank`, `read_bank_map`, `write_patch`,
`reconstruct_prst`, `build_ring` (build-time), `decode_import_capture` (test fixture).

Notes:
- These scripts ran from `patch/` originally; their relative paths and
  `sys.path` inserts are stale here. Fix up before rerunning one.
- `prst_reassign.py` used to write `patch/bank_map.json` by an inferred path —
  superseded by `read_bank_map.py` (live device read). Do not resurrect its writer.
- The canonical protocol docs are `re/DEVICE_READ.md`, `re/DEVICE_WRITE.md`,
  `re/SNAPTONE_PROTOCOL.md`, `re/REFIT_FINDINGS.md`, `re/HTFW_FORMAT.md`.

The HTFW firmware-container tools (`htfw_parse.py`, `htfw_extract.py`,
`isa_fingerprint.py`, `find_proto.py`, `fw_similarity.py`) are self-contained and
take paths as argv — unlike the older probes above, they run as-is from anywhere.
See `re/HTFW_FORMAT.md`.
