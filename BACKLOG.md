# Valeton Companion — Backlog

Planned work, not yet implemented. Grouped by area. Check off as shipped.
IDs are stable so we can burn down incrementally.

## Preset Explorer

- [ ] **EXP-1** — Remove `(29/29 ACKs)` from the write-success message. Keep
  `Written to slot N — slot now reads "X"`. The ACK count is debug noise that
  confuses users. (Also audit the Clear / Live / reorder success toasts for the
  same `(acks/sent)` string.)
- [ ] **EXP-2** — Remove the top-bar `⇅ Reorder` button. Inline row drag
  (reorderMode via the grip) is now the entry point, so the button is redundant.
- [ ] **EXP-3** — Active-state highlight is red and collides with the red DST block
  bar. Change the active background to **neon bright green** so it contrasts against
  every block color, on all rows. (Pin down the exact element first: the
  footswitch-active state and/or `.preset-active` / active-block highlight — several
  red accents may need switching.)
- [ ] **EXP-4** — Make the drag grip (hamburger) **bigger**. It's too small to grab.
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

- [ ] **CAP-1** — Move the **Templates** pane above the **SnapTones** pane, so it's
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

- [ ] **CONV-1** — Rename "NAM and Preset Converter" → **"Preset Converter"**
  (page title + nav). Remove the NAM converter pane; replace it with a link to the
  future standalone NAM repo. (Static build already strips NAM; this removes it from
  the backend page too and updates naming.)
- [ ] **CONV-2** *(separate project, later)* — Spin the NAM converter out into its
  own repo. Not now — just the placeholder. Repo/link target TBD; CONV-1's link
  points here once it exists.

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
