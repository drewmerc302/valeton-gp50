# Device Inspector redesign — morning summary (overnight build)

Built while you were away. Everything below is committed on `mvp-converter`, tested,
and hardware-verified on your connected pedal. Server is running on :8765.

## What to look at first (they're live — just click)
- **http://localhost:8765/device**   — Variant A · Registry (the default)
- **http://localhost:8765/device-b**  — Variant B · Manager
- **http://localhost:8765/device-c**  — Variant C · Build
- Layout-switcher pills at the top of each let you flip between them.
- **My pick: Variant A** for your stated user ("knows nothing, wants to manage
  captures + see what's used"). It's the most scannable — every capture is a card
  with a usage badge and a one-click Build. C's build-strip is the best *action*
  surface; a nice future move is grafting C's strip onto A. B (manager) is denser
  and better once you have a lot of assets, but leads with more whitespace.

## The rename you asked for
"Clone a patch onto a SnapTone" → **"Build a patch from a capture."**
Mental model now explicit everywhere: **template = effects wrapper**, **SnapTone =
tone core**, **output = a new patch** written to a slot you choose. The capture is
never overwritten.

## User templates (your idea)
- New **"★ Create template from"** button on every preset row in Preset Explorer
  (expand a preset → action bar). Names it like a block-library entry ("Metal",
  "80s Clean") and saves the whole effects chain.
- In Device Inspector you pick **template × SnapTone × slot → write to device**.
- Stored in `templates.json` (gitignored, like block_library.json). Storage is the
  faithful 552-byte source body + a display summary; build repoints the N->S block
  and refixes the CRC (shared engine `patchlib.repoint_snaptone_body`).
- I left **2 sample templates** so you can try Build immediately:
  "80s Clean (sample)" (Gate·Boost·Chorus·Spring) and "Simple Verb (sample)"
  (Gate·Room). Delete them with the ✕ — they're just demos.

## Guardrails
- Overwrite guard: writing to a non-empty slot warns "⚠ #N is not empty… (K patches
  reference material here)" before the confirm.
- Empty vs occupied slots split in the target picker (your 77–98 defaults show as
  "empty"). Build defaults to the first empty slot.
- Factory cabs separated from your user IRs (own section / collapsed).
- Every device write goes through the paced, gated `device_io` path — no blind
  sweeps, pedal never wedged.

## Device writes I made (test slots — reclaim anytime)
Authorized empty defaults only:
- **Slot 95** ← built "GBSN G20 I" (template MesaLS + SnapTone 55) — via API.
- **Slot 96** ← built "BCAT ER30" (sample template + SnapTone 51) — via the actual
  Variant C **Build & write** button, to prove the full UI→pedal path.
Both read back correctly on the pedal. Rescan or overwrite them whenever.

## Verification
- 49 unit/integration tests green (+ hardware-write tests + e2e).
- e2e renders Variant A in real Chromium (cards + usage badges + build CTA).
- Click-throughs in Chromium: the Explorer template CTA creates a template, and the
  Variant C build strip writes to the pedal (read-back confirmed).
- Screenshots in `work/screenshots/` (04 = A, 05 = B, 06 = C, 07 = CTA modal).

## Commits
- `991a959` templates backend (store, endpoints, device write, repoint engine)
- `e32a969` Device Inspector redesign + 3 layout variants (shared engine)
- `86a7cfc` Explorer "★ Create template from" CTA

## Open questions — ALL ANSWERED (2026-07-14)
1. Layout: **A (Registry) won.** B/C deleted (routes 404, files removed) plus a
   9-point feedback round — see commit `01a5634`.
2. Built-patch naming: **SnapTone name default stands** (current behavior,
   `/api/device/build` `name = req.name or snaptone.name`). No combo, no
   template-name default.
3. Bulk build: **skipped for now.** Deliberate scope cut, not an oversight —
   revisit only if one-at-a-time building proves tedious in real use.
