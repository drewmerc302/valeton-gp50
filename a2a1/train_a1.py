#!/usr/bin/env python
"""
Stage 2 of the A2->A1 pipeline: train a standard A1 WaveNet to match the rendered
teacher audio, and export a 0.5.x-format .nam that the Valeton GP-50 accepts.

RUN THIS WITH THE 0.12.2 VENV. Version matters: 0.13.0+ exports the 0.7.0 .nam
format, which the GP-50 rejects. 0.12.2 natively exports 0.5.x.

Inputs:
    di.wav  = the exact DI used in Stage 1 (x)
    y.wav   = Stage 1's rendered teacher output (target)
They are sample-aligned (delay=0).

Usage:
    python train_a1.py <di.wav> <y.wav> <outdir> [--epochs N] [--arch standard]
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from nam.models import init_from_nam
from nam.train import full as nam_full

# Standard A1 WaveNet (matches NAM's nam_full_configs/models/wavenet.json @ 0.12.2).
# "standard" is the safe, well-supported A1 that the GP-50 converter expects.
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
                        "head_size": 8,
                        "kernel_size": 3,
                        "dilations": STD_DILATIONS,
                        "activation": "Tanh",
                        "gated": False,
                        "head_bias": False,
                    },
                    {
                        "condition_size": 1,
                        "input_size": 16,
                        "channels": 8,
                        "head_size": 1,
                        "kernel_size": 3,
                        "dilations": STD_DILATIONS,
                        "activation": "Tanh",
                        "gated": False,
                        "head_bias": True,
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
    layer0 = d["config"]["layers"][0]
    ok = ver.startswith("0.5") and arch == "WaveNet" and "head_size" in layer0
    tag = "OK (GP-50 compatible)" if ok else "!! UNEXPECTED FORMAT"
    return f"version={ver} arch={arch} head_size={'head_size' in layer0} -> {tag}"


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
    print(f"FORMAT: {validate_format(final)}")
    print(f"DISTILL_ESR: {e:.6f}")
    print(f"A1_NAM: {final}")


if __name__ == "__main__":
    main()
