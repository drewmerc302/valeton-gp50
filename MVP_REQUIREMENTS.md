# GP-50 Converter — MVP Requirements (AGREED 2026-07-13)

Agreed scope for the autonomous build. Decisions locked with Drew:
**converter MVP + read-only device stub**, **FastAPI local web app**, **full-auto loop**.

## Product
Local web app: convert NAM **A2** captures to NAM **A1** `.nam` for the Valeton GP-50,
in batch, with live progress. Plus a read-only "usage inspector" stub (mocked data now,
wired to real device captures later).

## In scope (build these)

### Convert (feature 1)
- Input: drag-drop OR file-pick ≥1 `.nam`. Auto-detect architecture (A2 `SlimmableContainer`
  / A1 `WaveNet` / already-0.5.x). Already-A1 files pass through (optionally re-export).
- Engine: existing two-venv distillation (`.venv` 0.13.0 render, `.venv-a1` 0.12.2 train).
- **Output-format toggle: 0.5.x (GP-50; train/export in 0.12.2) vs 0.7.0 (newer devices;
  train/export in 0.13.0).** Both are A1 WaveNet; differ only in serialization.
- DI: default `refs/v3_0_0.wav`; allow custom upload or synthetic (`make_di.py`). Epochs
  configurable (default 100; a "fast" preset for quick tests).
- Batch queue: process N files; **one file failing never kills the batch**.
- Output: converted `.nam` to a chosen dir; carry source name metadata; format-validated.

### Progress (feature 7)
- Per-file state: queued → rendering → training (epoch X/N, live ESR) → done/failed.
- Overall progress; per-file ESR + final format-check result; error text on failure.

### Read-only device stub (features 2/3, mocked)
- "Usage inspector" screen: pick a SnapTone or IR (from a fixture built from the decoded
  inventory), list patches that reference it. **Mocked data + a clear "MOCK — not live
  device" banner.** Structured so real capture data drops in later behind the same interface.

## Out of scope (do NOT build; hardware-gated)
- Any real device I/O: reading the live pedal, uploading NAM/SnapTone, writing/replacing
  patches (features 4/5/6). Blocked on the 2-byte checksum + write protocol + captures only
  Drew can produce. **The loop must never send MIDI to or write the physical pedal.**

## Non-functional
- macOS Apple Silicon; reuses existing venvs; a fresh `.venv-app` for the web server deps.
- Cross-platform-friendly code; no reliance on a display for core logic.
- Reproducible; `run.sh` (or documented command) launches the app.

## Acceptance criteria (the loop is "done" when ALL pass, with evidence)
1. Through the UI: sample `refs/A2.nam` → valid **0.5.x** A1, format-check OK, live progress shown.
2. Batch of ≥2 files completes; a deliberately-bad input surfaces an error without crashing others.
3. Both output formats (0.5.x via 0.12.2, 0.7.0 via 0.13.0) produce load-valid A1 `.nam`.
4. Usage-inspector stub renders mocked SnapTone/IR→patch mapping with the MOCK banner.
5. Automated test suite green; a **headless end-to-end** test drives a real conversion via
   the HTTP API and asserts output validity; UI screenshot captured for Drew to review.
6. Sample conversion ESR under threshold (fast preset < 0.05; full run < 0.015).
7. `run.sh` launches the app; README documents setup + usage.

## Known limits (flag, don't fail on)
- Visual/aesthetic polish can't be fully self-verified without Drew's eye — loop verifies
  logic + endpoints + screenshots; Drew judges looks later.
- Full 100-epoch conversions are slow (~10-20 min each); tests use the fast preset.
