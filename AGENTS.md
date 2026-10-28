# AGENTS.md — Valeton GP-50 Editor

Guidance for AI coding agents (and humans) working in this repo. This is the
cross-tool source of truth; `CLAUDE.md` points here.

## What this is

A browser-based editor for the **Valeton GP-50** (and its sibling **GP-5**),
built by reverse-engineering the pedal's MIDI SysEx protocol from scratch — no
vendor SDK, no drivers, no backend. The shipped app is pure static files driving
the device live over **WebMIDI** (Chrome/Edge only; WebMIDI needs a secure
context). A local FastAPI server exists only for development and the legacy
in-repo NAM converter.

Live demo: https://valeton-gp50-woad.vercel.app

## Repository map

| Path | Role |
|------|------|
| `app/` | FastAPI dev server (`app/main.py`) + the vanilla-JS frontend in `app/static/`. This is the product. |
| `app/static/` | Shipped client: `explorer.js` (Preset Explorer), `prst.js` (.prst codec), `webmidi_device.js` / `webmidi_write.js` (device I/O), `patchlib.js`, `static_api.js` (in-page WebMIDI adapter for the zero-backend build), `ui_core.js` (`window.UI` primitives). |
| `patch/` | **Hardened device-I/O runtime** (Python): `prst_format.py`, `convert.py`, `device_protocol.py`, `device_write.py`, plus live-read/scan scripts. Product code. |
| `a2a1/` | NAM **A2→A1 distillation** pipeline (the legacy converter). Torch-heavy; runs in `.venv`. |
| `re/` | Reverse-engineering notes + throwaway probe scripts (`re/probes/`, `re/*.md`, Ghidra `.java`). **Not product code** — archival. |
| `scripts/` | `build_static_data.mjs` (data bundle) + `build_static_site.mjs` (assembles `dist/`). |
| `refs/` | Reference `.nam` model files for tests. |
| `docs/`, `design/` | Screenshots, design docs, distribution/roadmap notes. |
| `graphify-out/` | Generated knowledge graph (gitignored). Open `graph.html`; see `GRAPH_REPORT.md`. |

Top-level `*.md` (CONTEXT, STATUS, BACKLOG, DEPLOY, AUTONOMY, MVP_REQUIREMENTS)
are project memory/planning docs — read them, don't treat them as code.

## Architecture seams (respect these)

Read `CONTEXT.md` first — it is the domain glossary (Device, Patch/.prst,
SnapTone, User IR, Template, Block, bank_map, Scan vs Sync, Refit). The seams:

- **`patch/prst_format.py`** — the ONLY module that knows .prst byte offsets
  (552 B GP-50 / 507 B GP-5), CRC-8/0x07, name codec, device profiles, `detect()`.
  Golden-file tested. Never hardcode an offset anywhere else.
- **`patch/convert.py`** — GP-5 ↔ GP-50 preset reshaping. stdlib-only; round-trip
  tested against both corpora. GP-5→GP-50 is lossless; GP-50→GP-5 refuses on
  GP-50-only models unless forced.
- **`patch/device_protocol.py`** — the stdout wire contract between
  `app/device_io.py` and the MIDI subprocess scripts. Both sides import it.
- **`a2a1/distill_protocol.py`** — the stdout token contract (`DISTILL_ESR:` /
  `FORMAT:`) between `app/engine.py` and the a2a1 train scripts.
- **`app/static/ui_core.js`** (`window.UI`) — page-agnostic frontend primitives.
  Empty-slot truth and slot domains come from the backend inventory
  (`patch.empty`, `inventory.domains`) — no frontend re-derives them.
- **`app/patchlib.py`** — inventory + edit semantics on top of prst_format;
  device-aware (loads the matching `fxid_ring*.json`).

**Parity invariant:** the JS `.prst` codec (`app/static/prst.js`,
`webmidi_write.js`, `patchlib.js`) must stay byte-for-byte identical to the
Python runtime (`patch/prst_format.py`, `device_write.py`, `patchlib.py`). The
`*_js.mjs` tests enforce this against Python "oracle" scripts. If you change one
side, change and re-test the other.

## Build / run / test

Python dev server (needs `.venv-app`):

```bash
# one-time: python3 -m venv .venv-app && ./.venv-app/bin/python -m pip install \
#   fastapi "uvicorn[standard]" python-multipart pytest httpx
./run.sh          # serves http://127.0.0.1:8756 with autoreload
```

Static site (what actually ships; also the Vercel build):

```bash
node scripts/build_static_data.mjs   # refresh app/static/data/ bundle first
node scripts/build_static_site.mjs   # -> dist/   (Vercel runs the site step)
```

Tests:

```bash
# Python fast suite (default; excludes the slow browser e2e)
./.venv-app/bin/python -m pytest -m "not slow"
./.venv-app/bin/python -m pytest -m slow      # real headless-browser e2e (test_e2e.py)

# JS parity tests are standalone scripts, run with node (each auto-runs its Python oracle):
node app/tests/test_prst_js.mjs
node app/tests/test_write_js.mjs
node app/tests/test_edits_js.mjs
node app/tests/test_reorder_js.mjs
node app/tests/test_patchlib_js.mjs
```

The `a2a1/` pipeline uses its own `.venv` (NAM 0.13.0) and
`a2a1/requirements-*.txt`; see `a2a1/README.md`. It is not needed for editor work.

## Hard rules

- **Never send MIDI to, read from, or write the physical pedal from an automated
  run.** Device I/O against real hardware is human-gated. Device write is
  capture-verified for the GP-50 only (`device_write.WRITE_VERIFIED`); GP-5 write
  is gated behind `allow_unverified`. See `AUTONOMY.md` for the full guardrail set.
- **Work on a branch, never commit directly to `master`.** `master` is Vercel's
  production branch. Commit only on green (tests pass).
- **Every claim needs evidence** — run the tests and paste output; don't assert
  "looks good".
- **Stay in scope.** `re/` and `re/probes/` are archival RE artifacts, not a place
  to add features. `MVP_REQUIREMENTS.md` / `BACKLOG.md` scope the product.
- Changing .prst layout, the wire protocol, or the distill token contract is a
  cross-cutting change — update the seam module, its golden/oracle test, and the
  JS counterpart together.

## Conventions

- Backend: Python 3, FastAPI, stdlib-first in `patch/` (no heavy deps in the
  runtime path). Frontend: vanilla ES modules, no framework, no bundler — files
  are served/copied as-is.
- Match the surrounding module's style; these files carry dense domain comments —
  keep that density when editing.
- Commit messages in this repo use Conventional Commits (`docs:`, `chore:`,
  `feat:`, `fix:`).

## Where to look first

- Domain terms / mental model → `CONTEXT.md`
- Current state & known follow-ups → `STATUS.md`, `BACKLOG.md`
- Protocol/RE details → `re/DEVICE_READ.md`, `re/DEVICE_WRITE.md`,
  `re/SNAPTONE_PROTOCOL.md`, `re/DEVICE_BLOCKORDER.md`
- Hosting/deploy decisions → `DEPLOY.md`
- Whole-repo map / relationships → `graphify-out/graph.html`
