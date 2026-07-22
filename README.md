# GP-50 Converter

**Live demo:** [valeton-gp50-woad.vercel.app](https://valeton-gp50-woad.vercel.app) — zero-setup,
runs in-browser (WebMIDI), no local install needed. See [Setup](#setup) below for the full
local app with the batch converter.

A local web app that converts NAM **A2** captures to NAM **A1** `.nam` files for the
**Valeton GP-50**, in batch, with live progress — plus a read-only device usage
inspector (mocked for now). Built on the A2→A1 distillation engine in [`a2a1/`](a2a1/README.md).

> The GP-50 only accepts NAM A1. There's no A2→A1 format downgrade (different neural
> architectures), so this **distills**: render a DI through the A2 model, then train an
> A1 to reproduce it. See [`a2a1/README.md`](a2a1/README.md) for the engine details and
> [`MVP_REQUIREMENTS.md`](MVP_REQUIREMENTS.md) for scope.

## Screenshots

|  |  |
| --- | --- |
| ![Preset Explorer — full preset list with block chips](docs/screenshots/01-preset-explorer.png) **Preset Explorer** — every preset on the pedal, block chips color-coded by type. | ![Preset detail — signal chain, per-block params, live edit](docs/screenshots/02-preset-detail.png) **Preset detail** — full signal chain, per-block params, live edit straight to the pedal. |
| ![Model picker — official hardware names for a block](docs/screenshots/03-model-picker.png) **Model picker** — swap a block's model, official hardware names included. | ![Captures & IRs — templates and SnapTone captures](docs/screenshots/04-captures-and-irs.png) **Captures & IRs** — saved templates plus every SnapTone capture on the device. |
| ![SnapTone usage — which patches reference a capture](docs/screenshots/05-snaptone-usage.png) **Capture usage** — see exactly which patches reference a SnapTone. | ![Build a patch from a capture](docs/screenshots/06-build-patch.png) **Build a patch** — wrap a template around a SnapTone and write it to a slot. |
| ![Make a template from a preset](docs/screenshots/07-make-template.png) **Make a template** — save any preset's effects chain as a reusable wrapper. | ![Preset Converter — GP-5 to GP-50 conversion](docs/screenshots/08-preset-converter.png) **Preset Converter** — convert `.prst` presets between the GP-5 and GP-50. |

## Setup

Three Python venvs (the two engine venvs are pinned — see `a2a1/README.md` for why):

```bash
cd /Users/drewmerc/workspace/valeton

# engine venvs
python3 -m venv .venv     && ./.venv/bin/python     -m pip install -r a2a1/requirements-a2.txt   # NAM 0.13.0 (A2 render + 0.7.0 export)
python3 -m venv .venv-a1  && ./.venv-a1/bin/python  -m pip install -r a2a1/requirements-a1.txt   # NAM 0.12.2 (0.5.x export for GP-50)

# web app venv
python3 -m venv .venv-app && ./.venv-app/bin/python -m pip install fastapi "uvicorn[standard]" python-multipart pytest httpx
```

The default DI is `refs/v3_0_0.wav` (official NAM input). Get it via the trainer, or
generate a synthetic fallback: `./.venv/bin/python a2a1/make_di.py refs/v3_0_0.wav`.

## Run

```bash
./run.sh
```

Then open **http://127.0.0.1:8756**.

- **Convert:** drag-drop or pick `.nam` files → choose output format (**0.5.x** for the
  GP-50, or **0.7.0** for newer devices) → set epochs (or hit **Fast (test)**) →
  **Convert**. Watch per-file progress (ESR + format check); download each result.
  Then import the `.nam` into Valeton Suite like any A1 capture.
- **Device Inspector:** pick a SnapTone or IR to see which patches reference it.
  **Currently mocked** (clearly banner-flagged) — it wires to real device data once the
  GP-50 protocol RE is finished (see `a2a1/PRODUCT_IDEAS.md`).

## Tests

```bash
./.venv-app/bin/python -m pytest app/tests -q -m "not slow"   # fast unit/API/frontend suite
./.venv-app/bin/python -m pytest app/tests/test_e2e.py -q -s  # slow: real headless browser conversion + screenshots
```

## Layout

- `app/` — the FastAPI web app (engine wrapper, job API, static frontend, device stub).
- `a2a1/` — the conversion engine + GP-50 MIDI RE tooling ([README](a2a1/README.md)).
- `refs/` — sample models + the DI input.
- `MVP_REQUIREMENTS.md`, `AUTONOMY.md`, `STATUS.md` — the MVP spec, the build-loop
  protocol, and live build status.

## License

[MIT](LICENSE)

## Scope

MVP is **convert + read-only mocked device inspector**. Real device I/O (uploading to
slots, replacing SnapTones/IRs across patches) is deferred — it needs the GP-50 write
protocol + checksum, which are still being reverse-engineered. The app never touches the
physical pedal.
