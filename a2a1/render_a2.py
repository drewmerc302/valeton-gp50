#!/usr/bin/env python
"""
Stage 1 of the A2->A1 pipeline: render a DI signal through a NAM A2 capture.

RUN THIS WITH THE 0.13.0 VENV (the only one that can load A2 / SlimmableContainer).

An A2 .nam is a "SlimmableContainer" holding one or more ordinary WaveNet
submodels. The highest-`max_value` submodel is A2-Full (best quality); we extract
it, load it via the stable init_from_nam WaveNet path, and render the DI through
it. Output y is sample-aligned to the input (zero latency) so Stage 2 can train
with delay=0.

Usage:
    python render_a2.py <a2.nam> <di.wav> <out_y.wav>
"""

import json
import sys

import numpy as np
import soundfile as sf
import torch

from nam.models import init_from_nam

CHUNK = 480_000  # 10 s at 48 kHz; bounds peak memory for long files / big models


def load_teacher(nam_path):
    with open(nam_path) as fp:
        d = json.load(fp)
    arch = d.get("architecture")
    top_sr = d.get("sample_rate", 48000)
    if arch == "SlimmableContainer":
        subs = d["config"]["submodels"]
        full = max(subs, key=lambda s: s["max_value"])["model"]
        inner = {
            "architecture": full["architecture"],
            "config": full["config"],
            "weights": full["weights"],
            "sample_rate": full.get("sample_rate", top_sr),
        }
    elif arch in ("WaveNet", "LSTM", "Linear"):
        # Already an ordinary model (e.g. an A1 file) — render it directly.
        inner = {
            "architecture": arch,
            "config": d["config"],
            "weights": d["weights"],
            "sample_rate": top_sr,
        }
    else:
        raise SystemExit(f"Unsupported architecture for rendering: {arch!r}")
    model = init_from_nam(inner)
    model.eval()
    return model


def render(model, x):
    """Full-length, sample-aligned render, chunked to bound memory."""
    rf = model.receptive_field
    x = np.asarray(x, dtype=np.float32)
    xpad = np.concatenate([np.zeros(rf - 1, dtype=np.float32), x])
    xpad_t = torch.from_numpy(xpad)
    outs = []
    pos = 0
    n = len(x)
    with torch.no_grad():
        while pos < n:
            end = min(pos + CHUNK, n)
            seg = xpad_t[pos : end + rf - 1]
            y_seg = model(seg, pad_start=False)
            outs.append(y_seg.cpu().numpy())
            pos = end
    y = np.concatenate(outs)
    assert len(y) == n, f"render length {len(y)} != input {n}"
    return y


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: render_a2.py <a2.nam> <di.wav> <out_y.wav>")
    a2_path, di_path, out_path = sys.argv[1:4]

    x, sr = sf.read(di_path, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x[:, 0]  # mono
    model = load_teacher(a2_path)
    if model.sample_rate is not None and int(model.sample_rate) != int(sr):
        print(
            f"WARNING: DI sample rate {sr} != model sample rate {model.sample_rate}",
            file=sys.stderr,
        )

    y = render(model, x)
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    # Write 24-bit PCM to match the NAM/Valeton ecosystem. Guard against clipping.
    if peak > 0.999:
        print(f"NOTE: teacher output peak {peak:.3f} near full scale", file=sys.stderr)
    sf.write(out_path, y, int(sr), subtype="PCM_24")
    print(
        f"rendered {len(y)} samples  rf={model.receptive_field}  peak={peak:.4f}  -> {out_path}"
    )


if __name__ == "__main__":
    main()
