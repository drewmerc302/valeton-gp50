# CONTEXT — domain language for the Valeton Companion

Use these terms exactly; they map 1:1 to modules and UI copy.

## Domain

- **Device** — the GP-5 or the GP-50. Siblings: same .prst container, same
  SysEx protocol, same effect catalog (GP-5's is a strict subset of the GP-50's).
  A **device profile** (`prst_format.DeviceProfile`, keys `gp5`/`gp50`) carries
  the three things that differ: 20-byte header, .prst length (507 vs 552), and
  the 0xFF-block device tag. `prst_format.detect()` identifies a .prst's device.
- **Patch** — one device preset slot (index 0–99). Serialized as a **.prst**
  file (layout: `patch/prst_format.py`; 552 B on GP-50, 507 B on GP-5). A patch
  whose name is the factory default (the device name, `"GP-50"` / `"GP-5"`) is
  an **empty slot** (safe write target).
- **Preset conversion (GP-5 ↔ GP-50)** — reshaping a .prst between devices
  (`patch/convert.py`). Not an effect transcode: the 390-byte 0x02 tone block +
  name + VOL/BPM/footswitches are portable and rewrapped in the target skeleton.
  GP-5 → GP-50 is always lossless; GP-50 → GP-5 refuses (unless forced) when a
  block uses one of the 3 GP-50-only models. Surfaced on the Convert page's
  "Preset" sub-tab.
- **SnapTone** — a NAM capture loaded on the device (user slots 50–79 of the
  amp catalog). The tone core of a patch. Referenced by a patch's **N→S**
  block (category 0x0F, slot index; 0 = none — a SnapTone bypasses AMP+CAB).
- **User IR** — a user-uploaded cabinet impulse response. In fxid space these
  live at CAB fxlow ≥ 0x100000 ("User IR N" = slot N−1). Real device names come
  from a sync (bank_map).
- **Template** — a saved whole-patch effects chain ("effects wrapper", e.g.
  "Metal", "80s Clean") stored computer-side in templates.json. **Build a
  patch from a capture** = stamp a template onto a SnapTone (repoint its N→S,
  refix CRC) and write the result to a slot.
- **Block** — one of the 10 chain positions (NR PRE DST AMP CAB EQ MOD DLY RVB
  N→S). A block references a **model** by fxid = (category << 24) | fxlow; the
  decoded catalog is per-device (`patch/fxid_ring.json` for GP-50,
  `patch/fxid_ring_gp5.json` for GP-5), both built by `patch/build_ring.py`.
- **Block-library entry** — one saved block (model + params), the block-level
  sibling of a template. Stored in block_library.json.
- **bank_map** — `patch/bank_map.json`: authoritative device names for
  SnapTone slots and User IRs, produced only by a live sync
  (`patch/read_bank_map.py`).
- **Scan** — the ~60–90 s one-preset-at-a-time full read of the device into
  `device_scan/` (no bulk read exists). **Sync** — the quick catalog/IR name
  read that refreshes bank_map.
- **Refit / A2→A1** — distilling a NAM A2 capture into the 0.5.x A1
  architecture the GP-50 accepts (a2a1/, the Convert page).

## Architecture seams

- **prst_format** (`patch/prst_format.py`) — the .prst byte layout: offsets,
  CRC-8/0x07, name codec, record magics, rebuild(), plus the device profiles
  (GP-5/GP-50) and detect(). The only module allowed to know offsets.
  Golden-file tested against presetExports/ and the GP-5 fixtures.
- **convert** (`patch/convert.py`) — GP-5 ↔ GP-50 preset reshaping (see the
  domain term). stdlib-only; round-trip tested against both corpora.
- **device_protocol** (`patch/device_protocol.py`) — the stdout wire schema
  between app/device_io.py and the MIDI subprocess scripts. Both sides import
  it; contract-tested without hardware.
- **ui_core** (`app/static/ui_core.js`, `window.UI`) — page-agnostic frontend
  primitives (toast, confirm/prompt modals, fetch helpers, downloads, User-IR
  threshold). Preset Explorer and Device Inspector are its two adapters.
  Empty-slot truth and slot domains come from the backend inventory
  (`patch.empty`, `inventory.domains`) — no frontend re-derives them.
- **distill_protocol** (`a2a1/distill_protocol.py`) — the stdout token
  contract (DISTILL_ESR:/FORMAT:) between app/engine.py and the a2a1 train
  scripts. Both sides import it; contract-tested without torch.
- **jsonstore** (`app/jsonstore.py`) — shared JSON-list persistence (atomic
  tmp-swap + lock) under blocklib and templates_store.
- **patchlib** (`app/patchlib.py`) — inventory + edit semantics layered on
  prst_format: catalog resolution, SnapTone identity, usage, clone/repoint.
  Device-aware: detects the source presets' device (`_device()`) and loads the
  matching ring; `inventory.device` drives the UI's device badge.
- **patch/** — hardened device-I/O runtime only; archived RE probes live in
  `re/probes/` (not product code).
