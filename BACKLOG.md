# Valeton Companion — Backlog

Planned work, not yet implemented. Grouped by area. Check off as shipped.
IDs are stable so we can burn down incrementally.

## Preset Explorer

- [x] **EXP-1** — Remove `(29/29 ACKs)` from the write-success message. Keep
  `Written to slot N — slot now reads "X"`. The ACK count is debug noise that
  confuses users. (Also audit the Clear / Live / reorder success toasts for the
  same `(acks/sent)` string.)
- [x] **EXP-2** — Remove the top-bar `⇅ Reorder` button. Inline row drag
  (reorderMode via the grip) is now the entry point, so the button is redundant.
- [x] **EXP-3** — Active-state highlight is red and collides with the red DST block
  bar. Change the active background to **neon bright green** so it contrasts against
  every block color, on all rows. (Pin down the exact element first: the
  footswitch-active state and/or `.preset-active` / active-block highlight — several
  red accents may need switching.)
- [x] **EXP-4** — Make the drag grip (hamburger) **bigger**. It's too small to grab.
- [x] **EXP-6** — On the collapsed preset row header, **hide** disengaged (bypassed)
  blocks instead of dimming them — clears the clutter of dimmed chips. Expanded row
  is unchanged (disengaged blocks still shown, collapsed-by-default). Only the
  header chip-row filters out inactive blocks.
- [x] **EXP-7** — Expanded preset detail view wastes a lot of horizontal space on
  wide screens: block cards are full-width, so a block with only 1-4 params (e.g.
  CAB · VOL only) leaves a huge dead strip to the right of its slider. Explore
  layout alternatives — 2-col grid (params stacked vertically per block), 3-col
  grid, wrap-to-fill params in the existing single column, sidebar-nav +
  detail-pane — as visual mockups (Claude Designer / artifact) before committing to
  a redesign in code. Decision: **3-col grid** wins — see EXP-8.
- [ ] **EXP-8** — Implement the 3-col grid layout for the expanded preset detail
  (winner of EXP-7's exploration — mockup: https://claude.ai/code/artifact/f97d619d-49be-4b3d-ad9e-79b3390df34a,
  "3-column grid" tab). Blocks pack 3-per-row via CSS grid (`grid-auto-flow: row
  dense`), params stack vertically inside each card instead of the current
  horizontal row. Breakpoints: 3-col ≥1400px, 2-col ≥900px, 1-col below (today's
  behavior, unchanged). Touches `renderDetail()`'s per-block loop and the
  `.block-detail` / `.param-grid` CSS in `explorer.js` / `style.css`.
- [ ] **EXP-5** — Multi-select + bulk actions:
  - [ ] **EXP-5a** — Checkbox per preset row, to the right of the drag grip.
  - [ ] **EXP-5b** — Select all / none control.
  - [ ] **EXP-5c** — Top action bar (top-right, above the "Show real hardware
    names" toggle) that enables when ≥1 row is selected, with **Reset selected**
    and **Export selected**.
  - [ ] **EXP-5d** — Reset selected → confirm dialog stating the count
    ("Clear N presets to blank?") → clears each to the factory blank.
  - [ ] **EXP-5e** — Export selected → choose save location (File System Access API,
    Chrome-only) + a **Save all as .zip** option. Needs a zip step (JSZip or a small
    hand-rolled store-only zip).

## Captures & IRs

- [x] **CAP-1** — Move the **Templates** pane above the **SnapTones** pane, so it's
  obvious where/how to create a preset.
- [ ] **CAP-2** — In the "List Presets" modal (per SnapTone), add reset controls so a
  user can zero presets before deleting a SnapTone:
  - [ ] **CAP-2a** — "Reset preset" button next to each listed patch (clear to blank).
  - [ ] **CAP-2b** — "Reset all patches with this SnapTone" at the top.
- [ ] **CAP-3** — Replace-SnapTone in the same modal:
  - [ ] **CAP-3a** — "Replace SnapTone" per patch — pick a different existing ST.
  - [ ] **CAP-3b** — "Replace all listed" — set one new ST across all listed patches.
- [ ] **CAP-4** — "Replace with new SnapTone" — **upload** a new ST and assign it
  (per patch / all), instead of only picking an existing one. Bigger: needs a
  SnapTone upload/write path to the device.

## Preset Converter (page rename)

- [x] **CONV-1** — Rename "NAM and Preset Converter" → **"Preset Converter"**
  (page title + nav). Remove the NAM converter pane; replace it with a link to the
  future standalone NAM repo. (Static build already strips NAM; this removes it from
  the backend page too and updates naming.)
- [ ] **CONV-2** *(separate project, later)* — Spin the NAM converter out into its
  own repo. Not now — just the placeholder. Repo/link target TBD; CONV-1's link
  points here once it exists.

## GP-150 / GP-180 support

Full research + roadmap: **`design/GP150_GP180_SUPPORT.md`** — read that first; the
catalog, container findings and dead ends are already established, don't re-derive.
Origin: a Reddit commenter asked whether GP-150/180 tones could be supported later.

- [ ] **GP150-1** — Collect samples (blocks everything else). Need ≥20 GP-150 presets,
  **≥1 pair differing only by a chain reorder** (settles the `0x78` module-order
  hypothesis), ≥3 GP-180 presets (confirms GP-180 shares GP-150's container), and one
  preset with a 15-16 char name (pins the name field width). No hardware needed.
- [ ] **GP150-2** — Map the GP-150 container: diff-cluster the corpus, crack the
  checksum (offset/range/algo — do NOT assume GP-5/GP-50's CRC-8/0x07 at 0x14),
  confirm the `0x78` order array, map the param block against `module150_data.json`.
  Deliverable: `re/DEVICE_GP150.md` + a byte-for-byte round-tripping decoder.
- [ ] **GP150-3** — Refactor `patch/prst_format.py` **before** adding GP-150:
  `NAME_OFF`/`BODY_OFF` are module-level constants and `DeviceProfile` assumes a fixed
  20-byte magic header — GP-150 has its name at 0x2C and no magic, so it cannot be
  expressed today. Move the offsets into `DeviceProfile`, keep GP-50 the default,
  re-verify GP-5/GP-50 round-trips.
- [ ] **GP150-4** — `build_ring.py gp150` → `fxid_ring_gp150.json` from
  `module150_data.json` (extract from the user's own install; never redistribute).
- [ ] **GP150-5** — Read path: find GP-150/180 USB PID + MIDI port name, verify the
  `0x40`/`0x41` selectors behave as on GP-5/GP-50. Needs hardware or a capture.
- [ ] **GP150-6** — Write path: gated from day one (`WRITE_VERIFIED["gp150"]=False`),
  capture → build → byte-for-byte validate → only then send. Same discipline as GP-5.
- [ ] **GP150-7** — UI/product surface: device badge, converter matrix. GP-150↔GP-50
  is a real transcode across different containers, not a reshape — scope separately.

## Carried over (prior sessions / surfaced during RE)

- [ ] **PLAT-1** — Hosting decision (parked in DEPLOY.md). Leaning: private repo +
  Cloudflare Pages direct upload of `dist/`, open/unlisted URL.
- [ ] **REORD-1** — Bank-backup **import/restore** to complement the reorder export
  (the reorder modal dumps all 100 as JSON; there's no way to restore it yet).
- [ ] **REORD-2** — Live-fire the reorder **rollback/retry** path on hardware (coded,
  never device-tested; inducing a real mid-write failure is risky).
- [ ] **BLK-1** — Confirm block-order generalizes to **split / multi-move**
  arrangements (capture one split; open item in re/DEVICE_BLOCKORDER.md). Expected
  fine — it's a full permutation.
- [ ] **BLK-2** — Confirm the real **pointer-drag** on the chain strip
  (HTML5 DnD couldn't be automated; validated via DOM-reorder + real write instead).
- [ ] **WRITE-1** — Write-reliability under tab throttling: add **readback-verify +
  auto-retry** on device writes (saw 28/29 ACKs + an occasional stale read when the
  tab was backgrounded; writes still persisted, but a verify loop would make it
  robust). Broader than any one feature.
- [ ] **SNAP-1** — SnapTone conversion-quality investigation: Valeton Suite's NAM→
  SnapTone conversion uses a bundled training/reamp signal (`nam_input_wav.wav` in
  the app bundle, 44.1kHz/16-bit dual-mono, 70s) instead of the NAM community
  standard `T3K-sweep-v3.wav` (48kHz/24-bit mono, 190s — same DI a2a1 already
  trains against, `refs/v3_0_0.wav`). Swapped it in Suite.app (Mac): app doesn't
  choke on the format/duration mismatch, import works, and the resulting SnapTone
  is audibly different (much less gain/volume than Valeton's stock conversion on
  the same source patch) — confirms the training signal is load-bearing for
  conversion quality, contrary to the Reddit OP's guess that swapping it
  "wouldn't solve anything." Not yet known which is *more accurate* — untested:
  level-match both conversions first (raw "more gain" bias isn't meaningful
  on its own), then A/B both against a ground-truth render of the same `.nam`
  in a real NAM plugin (EQ curve + dynamics, not just loudness). Source:
  reddit.com/r/guitarpedals/comments/1mqtgdb.
