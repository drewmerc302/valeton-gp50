# GP-50 Companion App — Idea Capture & Feasibility

Brainstorm capture (2026-07-13). Not a commitment; a feasibility map grounded in what
we've already proven. Status of the engine so far:

- **A2→A1 distillation works** (ESR ~0.007), outputs GP-50-accepted 0.5.x `.nam`. Import
  confirmed on real hardware.
- **GP-50 protocol partially mapped** (read side): standard USB-MIDI; name records are
  48-byte SysEx `F0 [ck×2] [cat×2] 00 [idx] 01 03 [nibble-ASCII] F7`; category codes for
  patches / amps / IRs / SnapTone slots; text is nibble-encoded. Reads return metadata
  only — no binary comes back from the pedal.

## The one thing that gates everything on the write side

**The 2-byte checksum** (bytes 1–2 of each record) and **the host→device write/upload
command set**. Reading never needs them; every *write* feature (4, 5, 6) does — you
can't send a packet the pedal accepts without reproducing its checksum. The pending
**MIDI Monitor spy capture of an import** is what cracks both (gives upload format +
many checksum examples to reverse). Until then, write features are "unknown," not "no."

## Features, grouped by risk

### Read-only / pure-software (lower risk)

**1. Batch A2→A1 GUI (drop N files, pick 0.5.x vs 0.7.0 output).**
Feasible now — the conversion engine exists (`a2_to_a1.py`). Work is the GUI + wiring
the two venvs behind it, and exposing an output-format toggle (0.5.x via 0.12.2 export,
0.7.0 via 0.13.0 export — both already in-repo). No protocol needed. **v1.**

**7. Live conversion progress.**
Feasible now. Training already emits per-epoch ESR + checkpoints; surface that as a
progress bar/log per file. Pairs with #1. **v1.**

**2. "Which patches use this SnapTone?" / 3. "…this IR?"**
Needs the **patch-body decode**: read each patch record and find the field that
references its SnapTone-slot and IR-slot indices. We captured patch *name* records, not
the full patch body yet — need one more read capture (open/read every patch) and map
where slot references live. Read-only, so no checksum needed. **Feasible with ~1 more
capture + RE session.** v1.5.

### Write-to-device (higher risk — needs checksum + write protocol + care)

**4. Copy converted `.nam` into a user-selectable slot, warn which patches are affected.**
Two parts: (a) the SnapTone **upload** protocol (from the spy capture), (b) the
"affected patches" warning = reuse #2's patch→slot map. Writing to hardware — needs the
checksum cracked and careful validation. **Feasible after spy capture + checksum, but
this is where hardware risk starts.** v2.

**5. Replace the SnapTone on all patches with a new one. / 6. Same for IRs.**
Needs: patch-body decode (#2/#3) to find references + **patch-write** commands to rewrite
those references + checksum. Bulk writes to many patches = highest blast radius. Must
have: dry-run/preview, per-patch backup (read original first), undo. **Feasible but the
riskiest; do last.** v2.

## Cross-cutting unknowns (the RE backlog)

1. **Checksum algorithm** (bytes 1–2). Gates all writes. Crack via spy-capture examples.
2. **Upload/write SysEx format** (host→device). From the spy capture.
3. **Patch body layout** — where a patch stores its SnapTone-slot + IR-slot + amp refs.
   From a full patch read capture.
4. **Slot model** — how many SnapTone/IR slots, index ranges, empty-slot marker.
   (Early read hints: cat `00 05` = SnapTone/User-IR, cat `01 0B` mostly-empty bank.)

## Risk notes (name them now)

- **Bricking / corruption:** bad writes could corrupt a patch or the slot table. Non-
  negotiable before any write feature: full read-back backup of every target, checksum
  verified against many real examples, dry-run mode, and an on-device factory-reset
  escape documented.
- **Checksum wrong-guess = rejected or misapplied writes.** Validate against ≥dozens of
  captured real packets before trusting it.
- **Firmware variance:** protocol may differ across GP-50 firmware (this unit reports a
  fixed 14-byte descriptor `0B 05 00 01 … 03 01 04 …`). Gate on that descriptor.
- **Distribution:** a tool that writes to Valeton hardware is unofficial; ship with
  clear "at your own risk," and never bundle Valeton firmware/assets.

## Suggested phasing

- **v1 (safe, shippable):** #1 batch convert + #7 progress. Pure software, no device writes.
- **v1.5 (read-only device):** #2/#3 usage inspector. Needs patch-body read decode only.
- **v2 (writes):** #4 upload-to-slot, then #5/#6 bulk replace. Only after checksum +
  write protocol are cracked and a backup/dry-run/undo safety layer exists.

## Immediate next RE step

Spy-capture a Suite **import** (host→device) with MIDI Monitor → decode the SnapTone
upload + harvest checksum examples. Unblocks #4 and the whole v2 line.
