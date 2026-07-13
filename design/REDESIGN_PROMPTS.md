# GP-50 Web App — Design Prompts for Claude

Paste **[SHARED BRIEF]** first, then append **one** variant (A/B/C/D). Run each in a
separate Claude conversation to get four explorable directions for the same app.

---

## [SHARED BRIEF] — paste this before any variant

You are designing a visual redesign of a companion **web app for the Valeton GP-50**,
a guitar multi-effects modeler. Produce a **single, self-contained HTML artifact** (all
CSS + JS inline, no external assets, no network calls) that renders a **clickable
prototype** of the two priority screens using the realistic mock data below. It is a
design exploration, not the production app — bake data in, make sliders drag, make tabs
and expanders work, but don't wire real endpoints.

### Hard requirements (all variants)
- **Sliders, never knobs.** Every continuous parameter is a horizontal slider
  (`<input type=range>` styled). This matches Valeton's own design language — do not
  substitute rotary/knob controls. Toggles (on/off params) are switches.
- **Theme-aware.** Support light and dark via `prefers-color-scheme` AND a manual
  toggle that stamps `data-theme` on `:root`. Both must look deliberate.
- **Design tokens as CSS custom properties** (`--bg`, `--card-bg`, `--text`, `--muted`,
  `--border`, `--accent`, `--ok`, `--track`, plus the block palette below). The real app
  ports these into its `style.css`, so name them cleanly and use them everywhere — no
  hard-coded colors in components.
- **Responsive**, no horizontal body scroll. Wide rows (the param strips) may scroll
  inside their own container if needed, but the target is desktop-first, ~1100–1400px.
- Modern, uncluttered, **easy to navigate**, and **internally consistent** — the two
  screens must feel like one product (shared nav, spacing scale, type scale, controls).

### The product (context)
The GP-50 signal chain is a **fixed 10-block chain, always in this left→right order**:

`NR → PRE → DST → AMP → CAB → EQ → MOD → DLY → RVB → SnapTone`

- Each block is **on or off** (bypass) and holds **one model** with up to **8 params**.
- **SnapTone** (internal block name "N->S") is Valeton's slot for a NAM-derived amp
  capture — treat it as the last block in the chain.
- Some block types span sub-types the UI should surface (e.g. **DST** = OD / Fuzz /
  Distortion / Bass Drive; **MOD** = Chorus / Phaser / Flanger…). Granularity shown is
  **Block · Type · Model**, e.g. "DST · OD · Green OD" — never just "DST · Drive 1".
- An **"official names" toggle** swaps the cryptic device model name for the real gear
  reference (Green OD ↔ Ibanez TS808, Foxy 30TB ↔ Vox AC-30 Top Boost). Models with no
  official reference keep their device name. Design a clean home for this toggle.
- Two **footswitches (FS1, FS2)** can each toggle up to **2 blocks** live. Blocks show
  FS1/FS2 assignment controls; a footswitch that already holds 2 blocks greys out.
- Per-patch settings: **Patch VOL** (0–100) and **BPM** (40–300).

### Block color palette (KEEP these hues; restyle how they're APPLIED)
| Block | Meaning | Hex |
|-------|---------|-----|
| NR  | Noise Gate   | `#7a7f8a` |
| PRE | Pre / comp   | `#3fb0d8` |
| DST | Drive        | `#e0733a` |
| AMP | Amp          | `#d8434a` |
| CAB | Cab / IR     | `#c9a13a` |
| EQ  | EQ           | `#6a9a3a` |
| MOD | Modulation   | `#b05ad0` |
| DLY | Delay        | `#3a6df0` |
| RVB | Reverb       | `#2f9e8f` |
| SnapTone | Amp capture | `#6d94ff` |

Today these colors appear only as a thin 3px left border on a chip — **too subtle**.
Make block identity **prominent and scannable at a glance** in whatever way suits the
variant's aesthetic (full spine, filled header, tinted panel, tab underline, etc.).

### Screen 1 — Preset Explorer (redesign)
A scrollable list of presets. Each **collapsed** row shows: preset number + name, a
"SnapTone" badge if it uses one, and its **active blocks** as color-coded Block·Type·Model
tags in chain order. **Expanding** a preset reveals, per active block:
- block header (color-coded) with the model name, an **on/off** switch, and **FS1/FS2**
  assignment buttons;
- a **clickable model chip** that opens a picker (searchable model list + a saved
  "block library" list + "save current to library");
- the block's **param sliders** laid out **on one row per block** with **consistent
  slider sizing** (today they're uneven — fix this: uniform track length, aligned labels,
  aligned value readouts, tabular-number values).
Plus a top strip of **patch settings** (Patch VOL, BPM as sliders) and a **filter bar**
(filter by active block / type / model / SnapTone; saved filter sets). Footer per preset:
"Download edited .prst" + reset.
Known pain points to fix: **slider sizing is inconsistent**, and **color coding is not
prominent enough** (only an edge chip).

### Screen 2 — Device Inspector (full overhaul)
Manages the device library. Sections:
- **Sync from device** action + a source note ("parsed from exported patches").
- **Library browser**: a segmented toggle **SnapTones ⇄ IRs/Cabs** with counts, a search
  box, a scrollable list (each item: slot #, name, "N patches" usage badge), and a
  **usage pane** showing which patches reference the selected item, with a "Clone a patch
  onto this SnapTone →" action.
- **Clone lab**: pick a source patch + one or more target SnapTones → generate importable
  `.prst` files (single or zip).
- **All patches** list with search.
This screen currently reuses generic cards and feels utilitarian — **redesign it fully**
into a polished, modeler-grade library manager while keeping all the above functions.

### Mock data to render (use/extend this)
- **Presets** (~12): e.g. `#12 "Lead"` active: DST·OD·Green OD, AMP·US Lead, CAB·4x12 V30,
  DLY·Digital, RVB·Hall, SnapTone·"MES LS II"; `#3 "Clean Verb"`: PRE·Comp, AMP·Twin,
  CAB·2x12, RVB·Spring; `#7 "Fuzz Face"`: DST·Fuzz·Big Muff, AMP·Plexi, CAB·4x12.
- **DST params (Green OD)**: Gain 40, Level 60, Tone 55, Bass 50, Mid 52, Treble 58.
- **AMP params (US Lead)**: Gain 65, Bass 48, Mid 55, Treble 60, Presence 45, Master 70.
- **RVB params (Hall)**: Mix 35, Time 60, Trail (toggle) On.
- **SnapTones** (80 slots, ~60 named): "MES LS II", "Fuzz Clean", "Twin Sparkle", …
- **IRs/Cabs** (41): factory ("4x12 V30", "2x12 Blue") + User IRs (real names).
- **Official-name pairs**: Green OD→Ibanez TS808, US Lead→Mesa Mark, Big Muff→EHX Big Muff.

### Deliverable
One HTML artifact: a top nav switching between **Preset Explorer** and **Device Inspector**
(a third "Convert" tab may be stubbed). Ship the design tokens block clearly at the top of
the `<style>`. Prioritize the two screens above. Show the palette in action. Add a short
comment block naming the type scale, spacing scale, and radius used, so it's portable.

---

## [VARIANT A] — Fractal FM3-Edit aesthetic

Anchor the look to **Fractal Audio's FM3-Edit** editor: dark-first, dense, data-forward,
built for reading a lot of state fast without feeling cramped.
- **Palette**: near-black/charcoal surfaces (`#16181d`/`#1f232b`), high-legibility light
  text, one cool accent (electric cyan or blue) for interactive/selected state. Block
  colors are the identity system.
- **Block color coding**: give each expanded block a **full-height color spine** (left
  edge, ~4–6px, solid block hue) PLUS a tinted header bar in the block hue at low alpha —
  so a scan down the chain reads as a color ladder. In the collapsed preset row, the
  active-block tags are **filled** with the block hue (not just edge-bordered).
- **Density**: tabular, compact rows; tight but even spacing; small caps section labels;
  tabular-figure numeric readouts aligned in a column to the right of each slider.
- **Sliders**: thin track, crisp accent-colored fill + small square/hairline thumb; every
  slider in a block's row is exactly the same width, labels left-aligned, values
  right-aligned in a fixed-width column.
- **Motion**: minimal, fast (80–120ms), functional. No decorative animation.
- Signature detail: a **chain overview ribbon** at the top of each preset — the 10 blocks
  as small color tiles, dim when bypassed, lit in block hue when active — mirroring
  FM3-Edit's grid.

## [VARIANT B] — Neural DSP (Quad Cortex) aesthetic

Anchor to **Neural DSP / Quad Cortex**: bold, high-contrast, spacious, few large elements
per screen, big flat color panels, minimal chrome.
- **Palette**: deep neutral background, large blocks rendered as **flat filled color
  panels** in the block hue with white/dark high-contrast text on top. Generous negative
  space. One neutral accent for controls so the block colors carry the screen.
- **Block color coding**: each block is a **large rounded tile fully filled** (or heavily
  tinted) with its hue; the model name is the hero text; params live in a panel that
  slides open below the selected tile. Collapsed preset rows show blocks as a row of
  **big color pills**.
- **Density**: low. Fewer items visible, larger touch targets, big type scale, more
  padding. Feels premium/tactile, made for a touchscreen.
- **Sliders**: chunky track, large thumb, bold accent fill, big value label. Uniform width
  within a block; comfortable hit area.
- **Motion**: smooth, slightly springy panel expand/collapse (200–260ms), tasteful.
- Signature detail: selecting a block **elevates** it (shadow/scale) and reveals its param
  panel; the rest recede. One-thing-at-a-time focus.

## [VARIANT C] — Line 6 Helix Native aesthetic

Anchor to **Line 6 Helix Native**: the signal-chain flow is the star — connected,
colorful blocks with a cable/routing metaphor, lightly skeuomorphic.
- **Palette**: dark stage-console background; blocks are glossy rounded tiles in their
  hue connected by a visible **signal cable line** threading NR→…→SnapTone. Accent used
  for the cable/selection glow.
- **Block color coding**: the **horizontal chain of connected colored blocks** is the
  primary navigation for an expanded preset — click a block in the chain to load its
  params into a strip below. Bypassed blocks read as dimmed/unlit tiles in the chain.
  Collapsed preset rows show a **mini version of the same colored chain**.
- **Density**: medium; the chain is generously sized, the param strip below is compact.
- **Sliders**: console-style horizontal faders, consistent width, with subtle tick marks;
  value readout above or beside the fader.
- **Motion**: block selection glides the param strip; cable/selection glow on hover.
- Signature detail: the always-visible **signal-flow chain** as the spine of every preset,
  with the currently-edited block highlighted and cabled to its param strip.

## [VARIANT D] — Match Valeton Suite / Mobile

Anchor to **Valeton's own Suite/Mobile** look so the web app feels native to their
ecosystem — the most familiar, least novel direction.
- **Palette**: clean flat cards on a light-neutral base (with a real dark mode), Valeton's
  **red** as the primary accent, block colors as secondary category cues. Rounded panels,
  soft borders, restrained shadows.
- **Block color coding**: category color as a **filled block header** and a matching
  left accent on cards; collapsed preset rows use solid color category tags. Keep it
  clean and flat — no gloss.
- **Density**: medium, card-based, slider-first (matches their app). Comfortable, friendly.
- **Sliders**: rounded track, red accent fill, medium thumb, value in a pill; uniform
  width per block row.
- **Motion**: subtle, conventional (card expand, toggle slide), nothing flashy.
- Signature detail: feels like an official first-party Valeton tool — consistent card
  language across Device Inspector and Preset Explorer, red accent tying it together.

---

### After you get the four artifacts
Compare, pick the direction (or mix), then I'll port the chosen design tokens + component
styles into the real app's `app/static/style.css` and the two pages, keeping all existing
functionality (edit → downloadable `.prst`, no device writes).
