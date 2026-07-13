# GP-50 companion — distribution & expansion strategy

Status: **thinking doc, no decision yet** (2026-07-13). Captures the full options
analysis so the thread isn't lost. Nothing here is committed to.

---

## 0. Why this exists (the founding job)

This started from a concrete, narrow pain: **NAM capture vendors (e.g. Amalgam Audio)
ship A2-only captures and don't release A1 at all** — not even the A1 version the Valeton
GP-50 can import. Drew wants to *buy and use that gear* on the GP-50, even if only via an
A1 approximation. Almost certainly other GP-50 owners want the same.

From that seed it **ballooned** into a much more full-featured editor than Valeton's own
bare-bones Suite/Mobile (Preset Explorer, param editor, block library, model swap,
footswitches, direct device read/write, copy/paste/swap).

Keep this straight when deciding scope: **the converter is the founding job; the editor is
scope creep** — valuable, delightful, but not the original problem. That tension drives
everything below.

---

## 1. The core realization: this is 3 products, not 1

They have *opposite* distribution profiles. Do not ship them as one thing.

| Product | Needs | Distribution difficulty | Valeton-IP risk |
|---|---|---|---|
| **A. NAM A2→A1 converter** | torch (~2 GB), two NAM pins (0.13.0 render / 0.12.2 export) | **Hard** (heavy ML; the venv sprawl lives *entirely here*) | **Low** — NAM format is open (MIT); the distillation is our own work |
| **B. Device manager** (read/write patches, STs, IRs over USB-MIDI) | native USB-MIDI + the physical pedal | **Medium** (native MIDI + hardware, light deps) | Medium (protocol RE) |
| **C. Preset Explorer / editor** (parse `.prst`, filter, edit) | nothing — pure data | **Trivial** (no server, ML, or device) | **Higher** — uses model catalog derived from Valeton's `module50_data.json` |

**Two tensions worth staring at:**
1. The **founding job (A) is the hardest to ship**; the **scope-creep (C) is the easiest**.
2. The converter (A) is the **legally cleanest** (NAM is open); the editor (C) is the
   **legally riskiest** (Valeton-derived catalog). They invert on both axes.

The multi-venv pain Drew flagged is **only product A**. B and C never touch torch or NAM.

---

## 2. Distribution options — pros / cons

**1. Status quo (git clone + venvs)** — ✅ zero work, full power. ❌ technical users only;
multi-venv + torch + rtmidi setup is a non-starter for a guitarist. Not real distribution.

**2. Docker / compose** — ✅ encapsulates venvs, reproducible. ❌ **USB passthrough is broken
on Mac/Windows Docker Desktop** → can't do device I/O where users are; torch image multi-GB;
guitarists don't run Docker. Helps ~nobody here.

**3. Native desktop app — Tauri (preferred) or Electron, optional Python sidecar** — ✅
double-click install per OS, reuse the web UI, native MIDI; **Tauri ~10 MB if MIDI is done in
Rust and Python is skipped**. ❌ bundling torch (for A) → GB+ binary; per-OS **code-signing/
notarization** (Apple $99/yr + notarize; Windows cert ~$100–400/yr or scary warnings); cross-OS
maintenance. Sweet spot: Tauri for **B + C only**, converter separate.

**4. PyInstaller / py2app frozen binaries** — ✅ one file, no Docker. ❌ torch + native rtmidi
are painful to freeze, huge, fragile; per-OS + signing anyway. Worse than Tauri for a UI app.

**5. Hosted web service (cloud)** — ✅ zero client install for **C**, and crucially can host
**A** (upload A2 `.nam` → get A1 `.nam`/`.prst`) so users never install torch. ❌ **cloud can't
touch a USB pedal** (B is always local); GPU/compute cost for A; users upload their tones
(privacy); ongoing $$. Cheap/near-free for static C on Pages/Netlify.

**6. Split architecture (recommended)** = 5a + 5b + 5c:
- **5a — C as a pure client-side web app.** Reimplement the `.prst` parser in JS/WASM (format
  fully understood), drag-drop a Suite export or scanned bank, filter/edit/download. Zero
  install, any OS, no Python. ~2–4 days. Widest reach, lowest friction.
- **5b — B as a small Tauri helper.** USB-MIDI natively in Rust (`midir`); the protocol is
  ~100 lines (nibble+CRC, `0x1D` write, `0x40`/`0x41` reads, Program Change select). Drops
  Python + rtmidi for the device path entirely. ~1–2 weeks + signing. Mac first, then Win.
- **5c — A as a hosted service** (upload A2 → get A1) *or* a power-user CLI. Torch on a server,
  not the client. This is the piece that actually solves the founding Amalgam problem for
  everyone, and it's legally clean (NAM open-source).

---

## 3. iOS feasibility

The wrinkle worth noting: **Valeton Mobile is BLE-only. A USB editor is a gap Valeton doesn't
fill** — a real niche ("the USB editor Valeton doesn't ship").

Sober reality:
- **None of the current stack runs on iOS** (Python/FastAPI/torch/rtmidi all gone). iOS = a
  **from-scratch Swift rewrite**: the protocol over **CoreMIDI** + a Swift `.prst` parser + new UI.
- **Transport**: CoreMIDI sees USB-MIDI via USB-C (iPad / iPhone 15+) or a Lightning Camera
  Connection Kit; the same SysEx should work. **Feasibility hinges on a physical test that the
  GP-50 enumerates as a CoreMIDI device on iOS** (and/or whether it does BLE-MIDI).
- **NAM conversion can't come along** (torch won't run on-device) → drop A on iOS or back it
  with the hosted service.
- **App Store risk**: shipping a reverse-engineered editor for someone else's hardware invites
  review scrutiny + IP questions.
- Effort: **weeks-to-months**, zero code reuse. v2+, and only if desktop proves demand.

---

## 4. Cross-cutting risks (the real blockers, not the packaging)

1. **Legal / IP — biggest.** The editor's model catalog (`patch/fxid_ring.json`) is derived
   from Valeton Suite's `module50_data.json`, their copyrighted asset. **Redistributing it is
   the sharpest risk.** Fix: at first run, locate the user's own `Valeton Suite.app` and
   extract/build the ring *locally* (they must own Suite; they do). **Never ship Valeton's
   files.** The converter (A) does not have this problem — NAM is open.
2. **Firmware variance — N=1.** We RE'd against *one* pedal's firmware. Another owner's
   firmware could shift offsets/commands → a write could **corrupt or wedge their pedal**.
   Mitigation: detect firmware version; ship **read-only until the write path is validated for
   that version**; gate writes hard; backup-before-write.
3. **Wedge liability.** The tool can freeze-until-power-cycle a stranger's pedal, and they
   won't know the magic-button recovery. Distribute writes as explicit beta + ship the recovery
   doc + default to read-only/backup-first.
4. **macOS-only so far.** Windows/Linux untested; the app assumes Mac paths + CoreMIDI. Rust
   `midir` (in a Tauri build) fixes cross-platform cleanly.

---

## 5. Suggested phasing (given the founding job)

Because the founding job is the **converter**, don't let the editor's easy win bury it.

- **v1a — Hosted A2→A1 converter** (upload A2 `.nam` → download A1 `.nam`/`.prst`). Solves the
  actual Amalgam pain for everyone, no client install, legally clean. This is the mission.
- **v1b — Static client-side Explorer/editor (C).** Ship wide; no device, minimal legal
  exposure (local-extract rule). Proves the editor demand and is a strong companion.
- **v1.5 — Tauri desktop helper for device read/scan (B), read-first.** Add write behind a
  firmware-gated beta + mandatory backup.
- **v2 — iOS Swift app (C + B over CoreMIDI)** if desktop demand is real; converter stays a
  service. Fills the USB gap Valeton Mobile leaves.

---

## 6. The open decision

**Which job is the product?**
- "Get A2-only captures (Amalgam etc.) onto the GP-50" → **A, hosted converter** — the founding
  mission; heavy but legally clean; hostable so users install nothing.
- "Any GP-50 owner organizes/filters/edits presets" → **C, static web** — easiest, widest, but
  Valeton-catalog legal care needed.
- "Enthusiasts manage the pedal live over USB" → **B, native helper** — firmware risk owned.

Can't optimize all three into one distributable. Leaning: **A (hosted) is the mission, C is the
companion that ships almost for free, B is the enthusiast beta.** But no decision yet — this doc
exists so the thread survives until Drew picks.
