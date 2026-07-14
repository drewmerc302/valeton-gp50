# CONTEXT — domain language for the GP-50 Companion

Use these terms exactly; they map 1:1 to modules and UI copy.

## Domain

- **Patch** — one of the 100 device preset slots (index 0–99). Serialized as a
  552-byte **.prst** file (layout: `patch/prst_format.py`). A patch whose name
  is the factory default `"GP-50"` is an **empty slot** (safe write target).
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
  N→S). A block references a **model** by fxid = (category << 24) | fxlow;
  the decoded catalog is `patch/fxid_ring.json`.
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
  CRC-8/0x07, name codec, record magics, rebuild(). The only module allowed
  to know offsets. Golden-file tested against presetExports/.
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
- **patch/** — hardened device-I/O runtime only; archived RE probes live in
  `re/probes/` (not product code).
