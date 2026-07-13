# A2 → A1 for the Valeton GP-50

Get **NAM A2 / A2 Lite captures onto a Valeton GP-50**, which only accepts NAM
**A1** files. There's no format "downgrade" from A2 to A1 (they're different neural
architectures — weights don't transfer). Instead this does **distillation**:

```
A2.nam ──render a DI through it──▶ y.wav ──train an A1 to reproduce y──▶ A1.nam ──▶ Valeton Suite ──▶ SnapTone ──▶ GP-50
```

The A2 model is deterministic and noise-free, so the A1 copy is typically a tighter
match to the A2 than the A2 was to the real amp. You then load the A1 `.nam` in
Valeton Suite exactly like any A1 capture and let Valeton's own converter make the
SnapTone. This pipeline never touches the SnapTone format.

## Why two virtual environments (this is load-bearing, not accidental)

| Stage | venv | NAM version | Why |
|-------|------|-------------|-----|
| 1. Render A2 | `.venv` | **0.13.0** | Only 0.13.0+ can load A2 (`SlimmableContainer`). |
| 2. Train + export A1 | `.venv-a1` | **0.12.2** | 0.13.0+ exports the **0.7.0** `.nam` format; the GP-50 needs **0.5.x**. 0.12.2 emits 0.5.x natively. |

If you train/export with 0.13.0 the file *looks* like a WaveNet A1 but uses the new
0.7.0 layer schema (nested `head`, `kernel_sizes`, activation objects) and the GP-50
converter rejects it. The 0.5.x pin is the whole reason Stage 2 is separate.
(Same pin that `arturksd/NAM-A1-local-trainer` uses for the GP-50.)

## Setup

```bash
cd /Users/drewmerc/workspace/valeton
python3 -m venv .venv     && ./.venv/bin/python     -m pip install -r a2a1/requirements-a2.txt
python3 -m venv .venv-a1  && ./.venv-a1/bin/python  -m pip install -r a2a1/requirements-a1.txt
```

The DI input is `refs/v3_0_0.wav` (the official NAM standardized input — preferred,
because the resulting A1 behaves like a normal capture). If you don't have it, make a
synthetic fallback: `./.venv/bin/python a2a1/make_di.py refs/di.wav` and pass
`--di refs/di.wav`.

## Use

```bash
# One file:
python3 a2a1/a2_to_a1.py /path/to/capture.nam

# A whole folder of A2 captures:
python3 a2a1/a2_to_a1.py /path/to/a2_folder/ -o out/

# Options: --epochs 100 (default), --di <wav>, --keep-intermediate
```

Output A1 `.nam` files land in `out/`. Then, in **Valeton Suite**: pick an empty
slot → import the `.nam` → it converts to SnapTone and pushes to the pedal.

Already-A1 files (`WaveNet` / 0.5.x) are detected and copied through untouched.

## What to expect

- **Quality:** validation ESR against the A2 teacher typically lands ~0.005–0.02 for
  the standard architecture — at or below the error of a normal real-amp capture.
  The tool prints `ESR=` per file.
- **Speed:** render ~10–15 s; training ~100 epochs ≈ 10–20 min per model on Apple
  Silicon (MPS). It uses GPU/MPS automatically. Batchable overnight.
- **Format:** every output is checked to be `version=0.5.x, WaveNet, head_size` —
  i.e. GP-50-compatible — and the check is printed (`FORMAT:`).

## Scope / limitations

- Targets the **standard** A1 WaveNet (best fidelity; runs fine on the GP-50, which
  only pairs a SnapTone with a combo-amp NAM anyway). `--arch` is a hook for smaller
  variants but only `standard` is wired up.
- Distillation is only as good as the DI's coverage. The official `v3_0_0.wav` is
  ideal; the synthetic fallback is good but not identical.
- **Compatibility is validated by format, not yet on-device.** The 0.5.x pin follows
  known GP-50 practice, but load one output in Valeton Suite to confirm on your unit.

## Sniffing the GP-50 protocol (`midi_sniff.py`)

The GP-50 is a standard USB-MIDI device (VID 0x84EF / PID 0x018A), so Valeton Suite
does everything — list/dump patches, SnapTones, IRs, and SnapTone *uploads* — over
MIDI SysEx. `midi_sniff.py` records that traffic so the protocol can be decoded
(and, eventually, a converted SnapTone grabbed off the wire — the deferred "Q2").

Runs in `.venv-midi` (python-rtmidi + mido). It only observes/forwards; it never
originates vendor commands.

```bash
# Passive: logs device->host. Reliable. Start it, then open Valeton Suite and
# "read from pedal" — the pedal's dumps are captured.
./.venv-midi/bin/python a2a1/midi_sniff.py --out cap

# Proxy (MITM): logs BOTH directions, but only if the Suite lets you pick the port.
./.venv-midi/bin/python a2a1/midi_sniff.py --proxy --out cap
#   then point Valeton Suite's MIDI port at "GP-50 Proxy" (not "GP-50").

# Re-summarize a saved capture (message counts, biggest SysEx = likely dumps):
./.venv-midi/bin/python a2a1/midi_sniff.py --analyze cap.jsonl
```

CoreMIDI limit: a passive listener sees the pedal's replies but not the Suite's
outgoing requests. For host->device without a working proxy, use Snoize
**MIDI Monitor** (its spy driver sees both directions). **Never** hand-send guessed
vendor SysEx to the pedal — a wrong opcode could overwrite a patch or factory-reset.

## Files

- `render_a2.py` — Stage 1 (0.13.0): extract A2-Full submodel, render DI, chunked to
  bound memory.
- `train_a1.py` — Stage 2 (0.12.2): train standard A1, export 0.5.x `.nam`, report ESR.
- `a2_to_a1.py` — batch orchestrator (stdlib only; shells out to both venvs).
- `make_di.py` — synthetic DI fallback.
- `midi_sniff.py` — GP-50 MIDI SysEx logger (passive / proxy / analyze).

## Credits

Built on [Neural Amp Modeler](https://github.com/sdatkinson/neural-amp-modeler)
(MIT). GP-50 0.5.x-format insight from
[`arturksd/NAM-A1-local-trainer`](https://github.com/arturksd/NAM-A1-local-trainer).
