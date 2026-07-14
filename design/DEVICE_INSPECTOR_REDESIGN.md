# Device Inspector redesign + user templates — build brief

Autonomous overnight build spec. Written 2026-07-13 22:28 EDT. Approved direction:
**registry + device-writing build workflow.** Design language = the new Preset
Explorer (Variant D tokens, app-bar, cards, blue sliders, iOS switches, centered
modal, no-cache static). Deliver a few layout OPTIONS for morning review.

## Schedule (this session, warm cache)
- 5h token window resets ~00:00 EDT (2026-07-14). **Kickoff at 00:03:37 EDT
  (epoch 1784001817).** Bridge wakeups keep context cached until then — do NOT
  add wasteful every-30-min pings; 2 chained hops already keep the cache warm.
- On each wakeup: `date +%s` vs 1784001817. If `now >= kickoff`, BUILD. Else
  ScheduleWakeup for the remaining minutes and stop.

## Who this is for
A user who knows nothing about the app and just wants to (1) see the SnapTones
(NAM captures) and user IRs they loaded onto the pedal, and (2) find where each
custom file is used — or that it's unused and safe to overwrite.

## Purpose (one line)
"What custom captures & cabs do I have loaded, and what depends on each — and
let me wrap any capture in a saved effects template to make a gig-ready patch."

## Data model (verified)
- SnapTones: `/api/device/inventory` → `snaptones[] {slot(50–79), name}`. 25 loaded.
  Real user names ("MES LS II" = Mesa Lone Star capture).
- IRs/Cabs: `irs[] {slot, name}` — 41 = 21 factory cabs (TWD CP 1x8…) + 20
  `User IR n`. **Must visually separate user IRs from factory cabs** (factory
  cabs already live in Explorer's block picker; consider dropping them here).
- Usage: `/api/device/usage/snaptone/{slot}` and `/usage/ir/{slot}` →
  `{patches[]}`. A SnapTone patch bypasses CAB, so ir-usage excludes ST patches.
- Clone core: `patchlib.clone_with_snaptone(patch_slot, target_ns_slot)` — takes a
  patch's full effects chain, repoints ONLY the N->S block index, refixes CRC-8/0x07
  at 0x14, returns `.prst`. The capture is never touched. THIS is the template engine.
- Write path: `app/device_io.write_patch(prst, slot)` (subprocess → device, mirrors
  to device_scan/). Reuse for device-writing builds. `_lock` serializes.

## Rename the confusing feature
"Clone a patch onto a SnapTone" reads as overwriting the capture — backwards.
It PRODUCES A NEW PATCH THAT USES the capture. Correct verb = **wrap / build**.
New name: **"Build a patch from a capture"** (template = effects wrapper,
SnapTone = tone core, output = wrapper stamped on core).

## User templates (new — mirrors block library)
Block library = one saved block. Template = one saved whole-patch effects skeleton,
named "Metal" / "80s clean". Store like blocklib:
- `app/templates_store.py` + `templates.json` at root (pattern = app/blocklib.py:
  _read/_write/list/add/delete, uuid ids, threadlock).
- **v1 storage = Option A (faithful & safe):** template = `{id, name, source_slot,
  body_b64 (the source patch's full .prst or 511-byte body), block_summary[] (for
  display: block·type·model + official)}`. Build = clone_with_snaptone logic on the
  stored body → set N->S to chosen ST, set patch name, refix CRC. (Option B =
  structured per-block rebuild for recombination w/ block library — future, needs a
  body writer, error-prone. Not v1.)
- API: `GET/POST/DELETE /api/device/templates`; `POST /api/device/templates/from-patch
  {slot, name}`; `POST /api/device/build {template_id, snaptone_slot, target_slot,
  confirm}` → writes to device (reuse write path) OR `?download=1` returns .prst.

## Explorer CTA (new)
Add **"★ Create template from"** to each preset row's action bar (next to
Copy/Swap/Download/Write), same styling as "Save current to library". Prompts for a
name, POSTs /templates/from-patch. Keep it consistent with the block-library UX.

## Layout options to build (a few, for morning review)
Serve each as its own route so they're clickable side by side, e.g. `/device`
(chosen default) plus `/device-a`, `/device-b`, `/device-c` mockups. All in Suite
design language, theme-aware, no-cache.
- **A — Registry-first:** hero = searchable SnapTone + IR cards (tabbed or 2-col),
  each card = name + "used by N patches" badge (or "⚠ unused"); click → dependency
  drawer. "Build from capture" = secondary button on each card → modal (template ×
  slot). Clean, calm, discovery-oriented.
- **B — Two-pane manager:** left rail = asset list (STs / user IRs / factory cabs
  sections), right = detail (usage list + inline "Build a patch from this capture":
  template picker → target slot → Write). File-manager mental model.
- **C — Build-forward:** top = "Build a patch" 3-step strip (Template → SnapTone →
  Slot → Write), below = registry w/ usage. Payoff action front and center.
Pick distinct enough layouts that the morning review is a real choice, not 3 skins.

## Guardrails / failure modes (design against)
- Silent dependency break: writing over a slot N patches use → warn "⚠ N patches
  use this" in the build/overwrite confirm (centered modal). Usage view is the net.
- Empty vs loaded ST slots: can we tell? If build targets/points at an empty ST,
  what does the pedal do? Detect & warn if possible; otherwise note the risk.
- Bulk write blast radius: build across many captures → many preset writes. Explicit
  confirm + per-target slot picker. No blind bulk device writes.
- Never wedge the pedal (persistent port, paced). All device I/O via device_io.

## Device testing (AUTHORIZED)
User left the GP-50 connected overnight and OK'd a real device write to an empty
slot to test the build-from-capture → write path end-to-end.
- **Empty/default slots (name "GP-50"): 77–98.** Use **95** as the primary test
  target, **96** as backup. Slot 99 = "US Lead" (prior test), leave it.
- Verify by read-back after write (scan or read that slot), then confirm the built
  patch = chosen template's chain with N->S pointed at the chosen SnapTone.
- One write at a time, paced, persistent port (device_io). NEVER blind-sweep / wedge.
- After testing, note which slot(s) were written in the morning summary so the user
  can reclaim them.

## Execution notes
- Branch `mvp-converter` only. Commit incrementally (Write msg to /tmp/msg.txt →
  `git commit -F`). Server: uvicorn app.main:app --port 8765 (restart on py change;
  static is no-cache). Verify: node --check JS, py ast parse, curl via python urllib
  (RTK corrupts curl). Browser screenshots fail extension-side — don't block on them.
- 3 independent HTML variants can be parallel Agent subagents (allowed) if it saves
  wall-clock; backend (store + endpoints) is shared, build it first.
- Leave a concise summary of the variants + how to view them for the morning.
