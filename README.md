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

`work/screenshots/` — convert page (empty / in-progress / done) and the device inspector.

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
