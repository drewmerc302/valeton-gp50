# Adding GP-150 / GP-180 support — research + roadmap

Research done 2026-07-22. Everything below is **already established** — pick this up
without redoing it. Sources: `/Applications/Valeton Mobile.app`, the GP-150 manual,
3 sample GP-150 `.prst` files, and GP-5/GP-50/GP-150 firmware (see
`re/HTFW_FORMAT.md`).

Origin: a Reddit commenter asked "Will it be possible to add later support for
GP 180/150 tones?"

---

## Part 1 — What is already known (do not re-derive)

### 1.1 GP-180 almost certainly shares GP-150's engine

The **Valeton Mobile** app (`/Applications/Valeton Mobile.app`, distinct from the
desktop "Valeton Suite" app) is a Flutter iOS build in a Mac Catalyst wrapper;
internal Dart package name is `gp_5`. Assets live at:

```
/Applications/Valeton Mobile.app/Wrapper/Runner.app/Frameworks/App.framework/flutter_assets/assets/data/
    module_data.json      (1.0MB)  GP-5
    module50_data.json    (935KB)  GP-50
    module150_data.json   (2.0MB)  GP-150
    gp5D.json             (22KB)
```

**There is no `module180_data.json`.** The compiled Dart binary has `GP-180`,
`GP-180_id`, `icon_gp180`, `isGp150`, `isNotGP150` symbols but only ever loads
`module150_data.json` (`Module150Provider`, `module150Path`,
`package:gp_5/model/module150_pattern.dart`). Read: GP-180 is a chassis variant of
GP-150 (more I/O, more switches), not a different DSP/effect engine. Consistent with
the two being launched and reviewed as a pair.

**Catalog is therefore already in hand** — `module150_data.json` is flat unencrypted
JSON, same structure as `module50_data.json` (`{"modules":[{"name","moduleId",
"module":[{"fxid","fxtitle","name","type","origin","alg":[...]}]}]}`). No
decompilation needed. Extract from the user's own install at runtime — never
redistribute (same rule as `module50_data.json`).

### 1.2 One shared SysEx codec across all four devices

The Dart binary exposes `encodeToMIDSysEx2` / `decodeToMIDSysEx2` as shared
functions — one codec serving GP-5/GP-50/GP-150/GP-180, not per-model
reimplementations.

**But shared codec does NOT imply shared container** — proven below in 1.3, where
GP-150's `.prst` turns out to be a completely different layout. Do not assume
protocol symmetry from symbol names. (This is the same trap that keeps the GP-5
write gate closed; see `re/HTFW_FORMAT.md`.)

### 1.3 GP-150 `.prst` is a DIFFERENT container — not a GP-5/GP-50 variant

Measured from 3 samples (`162852_105Rhythm2.prst`, `162855_103Clean.prst`,
`162900_104Rhythm.prst`), all **1128 bytes**:

| | GP-5 | GP-50 | GP-150 |
|---|---|---|---|
| length | 507 | 552 | **1128** |
| ASCII magic | `GP-5\0` | `GP-50\0` | **none** |
| name offset | 0x19 | 0x19 | **0x2C** |

The only ASCII in a GP-150 file is the patch name itself. GP-5/GP-50's whole
identification scheme (20-byte magic header, CRC-8/0x07 at 0x14, `FF FF FF FF`
sentinel at 0x15) is absent.

Established so far:

- **Name** at `0x2C`, ASCII, zero-padded. (Field width unconfirmed — none of the 3
  sample names are long enough to find the end.)
- **Byte `0x04`** and **bytes `0x0E-0x0F`** vary per file — candidate patch id /
  length / checksum. Unidentified.
- **Module-order array at `0x78`**: 12 bytes, an exact permutation of 0-11. The
  manual's MIDI CC list (CC48-59) gives the module index order:
  `NR(0) PRE(1) WAH(2) DST(3) NS(4) AMP(5) CAB(6) EQ(7) MOD(8) DLY(9) RVB(10) VOL(11)`.
  All 3 samples decode to the same order: `AMP, NR, PRE, WAH, DST, NS, CAB, EQ, MOD,
  DLY, RVB, VOL` (`[5,0,1,2,3,4,6,7,8,9,10,11]`).
  Structurally analogous to GP-50's `REC_ORDER` (`re/DEVICE_BLOCKORDER.md`).
  **UNCONFIRMED** — 3 samples all showing the identical order is equally consistent
  with (a) a real chain-order array none of these presets reordered, or (b) a
  coincidental byte run. See step 2 to settle it.
- **Param block**: past `0x84`, the per-file diffs fall in a regular ~0x30-0x40 byte
  cadence — fixed-stride module/param records, same idea as GP-50's 390-byte 0x02
  block, different stride.

Reproduce with:
`python3 -c "import sys; ..."` — or just diff the three files; the diff-range script
used is inlined in the session log (2026-07-22).

### 1.4 Firmware is obtainable and decoded

`re/HTFW_FORMAT.md` has the full container spec. GP-150 firmware parses cleanly:
7 regions (`b`@0x38000 5.1MB main app, `c`@0x740000, `d`@0x800000, `e`@0x9c0000,
`f`@0xa80000, `g`@0 (entropy 7.99 — compressed), `h`@0). Same `HTFW` magic as
GP-5/GP-50, so GP-150 is the same firmware generation — **not** the old
GP-100/GP-200 Roland-DT1 generation.

**Firmware is a dead end for protocol RE**: the app core runs on an MVsilicon B1
(Mountain View Silicon) BT-audio SoC. Ghidra has no processor module for it and no
public RE of the ISA exists. Do not sink time here.

### 1.5 The manual is a decoding key — use it

`GP-150_Online Manual_EN_Firmware V1.0.5.pdf`, 83 pages. **Filename contains a
non-breaking space (`\xa0`) between "GP-150_Online" and "Manual"** — plain shell
paths will fail; use the exact bytes.

- **pp. 77-78** — MIDI Control Information List. Gives the 12 module slots in index
  order (this is what decoded the `0x78` array), plus CC assignments for patch
  volume, EXP, quick-access knobs, looper, drum machine, tempo.
- **pp. 36-73** — Effect List: ~40 effects with names, types, and per-param
  descriptions. Correlate against `module150_data.json` fxids.
- **pp. 74-76** — Factory SnapTone files.

### 1.6 Unexplored leads

- `hotone_developer_kit.framework` — native arm64 dylib in the Mobile app bundle,
  likely the real protocol/BLE SDK. Never opened. **Highest-value unexplored item**;
  unlike the Dart AOT code it is native ARM64 and Ghidra-analyzable.
- `https://www.hotoneaudio.com/updater/user/modelData?productId=` — string found in
  the app binary. Model catalogs may be fetchable server-side by productId.
- GP-150 firmware region `g` is compressed (entropy 7.99) — unexamined.

---

## Part 2 — Roadmap

Ordered by dependency. Steps 1-4 need **no hardware**; steps 5+ do.

### GP150-1 — Get more sample presets (blocking everything)

3 samples is not enough to separate fixed bytes from variable ones. Need:

- **≥20 GP-150 presets**, ideally including factory presets and heavily-edited ones.
- **≥1 pair that differs only by a chain reorder** — this alone settles the `0x78`
  hypothesis (1.3). Without it, the module-order finding stays unproven.
- **≥3 GP-180 presets** — to confirm GP-180 emits the same container as GP-150.
  If GP-180 files are also 1128 bytes with the same field offsets, one code path
  covers both, and the 1.1 conclusion is confirmed from data rather than inference.
- **≥1 preset with a long (15-16 char) name** — pins the name field width.

Source: Reddit (the original commenter), Valeton's forum/FB groups, or the factory
preset dump in firmware region `e` equivalent.

### GP150-2 — Map the GP-150 container

With samples in hand, port the GP-50 method:

- Diff-cluster the corpus to separate fixed / per-preset / per-param bytes.
- Identify the checksum: locate it and the covered range. GP-5/GP-50 use CRC-8/0x07
  over `prst[0x15:]` stored at `0x14` — **do not assume GP-150 matches**; brute-force
  offset/range/algorithm (`re/probes/crc07_crack.py` is the prior art, and
  `re/verify_crc.py`).
- Confirm the `0x78` order array against the reorder pair.
- Map the param block: stride, record layout, and which bytes are fxid vs value.
  Cross-reference `module150_data.json` fxids and the manual's Effect List.
- Deliverable: a `re/DEVICE_GP150.md` spec + a decoder that round-trips every
  sample **byte-for-byte** (the GP-50 bar was 100/100; hold to it).

### GP150-3 — Refactor the device abstraction (required before GP-150 lands)

`patch/prst_format.py` currently **cannot** express GP-150:

- `NAME_OFF = 0x19` and `BODY_OFF = 0x29` are **module-level constants**, used
  directly by `patch_name()`, `set_patch_name()`, `rebuild()`, and by
  `patch/device_write.py` (payload is `prst[NAME_OFF:]`).
- `DeviceProfile` assumes a fixed 20-byte magic header (`header: bytes`), and
  `detect()` matches on that header then falls back to length. GP-150 has no magic —
  detection must fall back to length (1128) or a structural signature.

Work: move `name_off` / `body_off` (and header-optionality) into `DeviceProfile`,
update every consumer, keep GP-50 as the back-compat default. Then verify GP-5 and
GP-50 still round-trip byte-for-byte (existing fixtures + `app/tests/test_convert.py`).
Do this refactor **before** adding GP-150, not during.

### GP150-4 — Catalog + ring build

- Extend `patch/build_ring.py` with a `gp150` target reading `module150_data.json`
  → `fxid_ring_gp150.json`.
- Note the existing warning: a GP-50 ring rebuild drifts from the committed ring
  because the installed Suite's origin data changed. Build **only** the gp150 target;
  do not casually regenerate the others.
- Extraction must read from the user's own Valeton Mobile / Suite install at runtime.
  Never commit or redistribute Valeton's JSON.

### GP150-5 — Read path (needs hardware or a capture)

- Confirm USB VID/PID and MIDI port name for GP-150/GP-180 (GP-5 = 0x84EF/0x0184,
  GP-50 = 0x84EF/0x018A; GP-150/180 unknown). `patch/live_read.find_port()` resolves
  by port name and needs a new match.
- Confirm the read selectors (`0x40` names / `0x41` active body) behave as on
  GP-5/GP-50. Likely shared given the single codec, but verify — 1.3 is the standing
  proof that "shared app" ≠ "shared layout".

### GP150-6 — Write path (gated; do not shortcut)

Follow the same discipline that governs GP-5: **capture first, then build, then
validate byte-for-byte, then gate.** Add `WRITE_VERIFIED["gp150"] = False` from the
start and refuse writes until a real Suite/Mobile import capture is reproduced
exactly. See `re/DEVICE_WRITE.md` — sending guessed traffic wedged the pedal once.

### GP150-7 — UI / product surface

Device badge, converter matrix (GP-150↔GP-180 is likely a no-op or a trivial
reshape; GP-150↔GP-50 is a genuine transcode across different containers and
probably different effect catalogs — scope separately, do not assume it is
achievable losslessly).

---

## Traps (learned the hard way — do not repeat)

- **2-byte opcode searches in multi-MB binaries are statistical noise** (~19 random
  hits per 1.2MB). Only long, exact matches mean anything.
- **Shared symbol names / a shared app prove nothing about container layout.**
  GP-150 is the counter-example (1.3).
- **The GP-150 manual filename has a non-breaking space** — quote the exact bytes.
- **Do not attempt firmware disassembly of the app core** (MVsilicon B1, no tooling).
- **Do not attempt Dart AOT disassembly** — already tried and failed on GP-50; wire
  capture is what cracked it (`re/DEVICE_WRITE.md`).
