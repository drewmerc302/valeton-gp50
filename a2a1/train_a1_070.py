#!/usr/bin/env python
"""
Stage 2 (0.7.0 variant) of the A2->A1 pipeline: train a standard A1 WaveNet to
match the rendered teacher audio, and export a 0.7.0-format .nam.

RUN THIS WITH THE 0.13.0 VENV (.venv). Version matters: 0.13.0+ exports the
0.7.0 .nam format (newer devices only). For 0.5.x output, use
a2a1/train_a1.py under .venv-a1/0.12.2 instead — that path is unchanged.

The 0.13.0 WaveNet model_config uses a different (newer) schema than 0.12.2:
each layers_configs entry has a nested "head" rechannel object
({"out_channels", "kernel_size", "bias"}) instead of the old flat
head_size/gated/head_bias keys.

Inputs:
    di.wav  = the exact DI used in Stage 1 (x)
    y.wav   = Stage 1's rendered teacher output (target)
They are sample-aligned (delay=0).

Usage:
    python train_a1_070.py <di.wav> <y.wav> <outdir> [--epochs N] [--arch standard]
"""

import argparse
import json
import shutil
from pathlib import Path

import distill_protocol  # sibling module: the engine <-> train stdout contract
import numpy as np
import soundfile as sf
import torch

from nam.models import init_from_nam
from nam.train import full as nam_full

# Standard A1 WaveNet, 0.13.0 schema (nested "head" rechannel per layer array).
# Matches the known-good standard-A1 config for the 0.7.0 export path.
STD_DILATIONS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]


def model_config(arch: str) -> dict:
    if arch != "standard":
        raise SystemExit(f"only 'standard' arch is wired up (got {arch!r})")
    return {
        "net": {
            "name": "WaveNet",
            "config": {
                "layers_configs": [
                    {
                        "condition_size": 1,
                        "input_size": 1,
                        "channels": 16,
                        "head": {
                            "out_channels": 8,
                            "kernel_size": 1,
                            "bias": False,
                        },
                        "kernel_size": 3,
                        "dilations": STD_DILATIONS,
                        "activation": "Tanh",
                    },
                    {
                        "condition_size": 1,
                        "input_size": 16,
                        "channels": 8,
                        "head": {
                            "out_channels": 1,
                            "kernel_size": 1,
                            "bias": True,
                        },
                        "kernel_size": 3,
                        "dilations": STD_DILATIONS,
                        "activation": "Tanh",
                    },
                ],
                "head_scale": 0.02,
            },
        },
        "optimizer": {"lr": 0.004},
        "lr_scheduler": {"class": "ExponentialLR", "kwargs": {"gamma": 0.993}},
    }


def data_config(di: str, y: str, n_samples: int) -> dict:
    # Time split: reserve the tail for validation. Digital render => delay=0.
    val_len = min(1_500_000, n_samples // 5)
    split = n_samples - val_len
    return {
        "train": {"ny": 8192, "stop_samples": split},
        "validation": {"ny": None, "start_samples": split},
        "common": {
            "x_path": di,
            "y_path": y,
            "delay": 0,
            "allow_unequal_lengths": False,
            "require_input_pre_silence": None,
        },
    }


def learning_config(epochs: int) -> dict:
    if torch.cuda.is_available():
        dev = {"accelerator": "gpu", "devices": 1}
    elif torch.backends.mps.is_available():
        dev = {"accelerator": "mps", "devices": 1}
    else:
        dev = {}
    return {
        "train_dataloader": {
            "batch_size": 16,
            "shuffle": True,
            "pin_memory": True,
            "drop_last": True,
            "num_workers": 0,
        },
        "val_dataloader": {},
        "trainer": {"max_epochs": epochs, **dev},
    }


def esr(pred: np.ndarray, target: np.ndarray) -> float:
    num = float(np.sum((target - pred) ** 2))
    den = float(np.sum(target**2)) + 1e-12
    return num / den


def validate_format(nam_path: Path) -> str:
    with open(nam_path) as fp:
        d = json.load(fp)
    ver = d.get("version", "?")
    arch = d.get("architecture")
    layers = d.get("config", {}).get("layers", [])
    last_layer = layers[-1] if layers else {}
    has_head = isinstance(last_layer.get("head"), dict)
    ok = ver.startswith("0.7") and arch == "WaveNet" and has_head
    tag = "OK (0.7.0 export)" if ok else "!! UNEXPECTED FORMAT"
    return f"version={ver} arch={arch} head={has_head} -> {tag}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("di")
    ap.add_argument("y")
    ap.add_argument("outdir")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--arch", default="standard")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    info = sf.info(args.y)
    n_samples = info.frames

    mc = model_config(args.arch)
    dc = data_config(args.di, args.y, n_samples)
    lc = learning_config(args.epochs)

    nam_full.main(dc, mc, lc, outdir, no_show=True, make_plots=False)

    exported = outdir / "model.nam"
    if not exported.exists():
        raise SystemExit(f"training did not produce {exported}")

    # Distillation quality: ESR of trained A1 vs teacher over the validation tail.
    val_len = min(1_500_000, n_samples // 5)
    split = n_samples - val_len
    x, _ = sf.read(args.di, dtype="float32", always_2d=False)
    yt, _ = sf.read(args.y, dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x[:, 0]
    if yt.ndim > 1:
        yt = yt[:, 0]
    with open(exported) as fp:
        student = init_from_nam(json.load(fp))
    student.eval()
    with torch.no_grad():
        y_pred = (
            student(torch.from_numpy(np.asarray(x, np.float32)), pad_start=True)
            .cpu()
            .numpy()
        )
    e = esr(y_pred[split:], yt[split:])

    final = outdir / "a1.nam"
    shutil.copyfile(exported, final)
    distill_protocol.emit_format(validate_format(final))
    distill_protocol.emit_esr(float(e))
    print(f"A1_NAM: {final}")


if __name__ == "__main__":
    main()
