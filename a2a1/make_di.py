#!/usr/bin/env python
"""
Fallback DI generator, for when you don't have the official NAM input file.

Prefer the official v3_0_0.wav (it's what real captures use, so the resulting A1
behaves identically to a normal capture). This synthetic signal is a reasonable
substitute: exponential sine sweeps and pink-ish noise at several amplitudes plus
transient bursts and silences, to excite the amp model across its full frequency
and dynamic range. Deterministic (fixed seed) so runs are reproducible.

Usage:
    python make_di.py out_di.wav [--seconds 180]
Run with either venv (needs only numpy + soundfile).
"""

import argparse

import numpy as np
import soundfile as sf

SR = 48000


def sweep(dur, f0, f1, amp, sr=SR):
    n = int(dur * sr)
    t = np.arange(n) / sr
    k = (f1 / f0) ** (1.0 / dur)
    phase = 2 * np.pi * f0 * (k**t - 1) / np.log(k)
    return (amp * np.sin(phase)).astype(np.float32)


def pink(n, rng):
    # Voss-ish: filter white noise toward a 1/f slope via cumulative smoothing.
    white = rng.standard_normal(n).astype(np.float32)
    b = np.array([0.049922, -0.095993, 0.050612, -0.004408], dtype=np.float32)
    a = np.array([1.0, -2.494956, 2.017265, -0.522189], dtype=np.float32)
    from scipy.signal import lfilter

    y = lfilter(b, a, white).astype(np.float32)
    y /= np.max(np.abs(y)) + 1e-9
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=180.0)
    args = ap.parse_args()
    rng = np.random.default_rng(1234)

    parts = [
        np.zeros(int(0.5 * SR), np.float32)
    ]  # lead-in silence for alignment checks
    for amp in (0.05, 0.15, 0.4, 0.8):
        parts.append(sweep(6.0, 20, 20000, amp))
        parts.append(np.zeros(int(0.1 * SR), np.float32))
    for amp in (0.1, 0.3, 0.7):
        seg = pink(int(8 * SR), rng) * amp
        parts.append(seg.astype(np.float32))
        parts.append(np.zeros(int(0.15 * SR), np.float32))
    # Note-like decaying tones across the guitar range at varying levels.
    for f in (82.41, 110, 146.83, 196, 246.94, 329.63, 440, 587.33, 880):
        n = int(1.2 * SR)
        t = np.arange(n) / SR
        env = np.exp(-t * 3.0).astype(np.float32)
        amp = 0.2 + 0.6 * rng.random()
        tone = (
            amp
            * env
            * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t))
        )
        parts.append(tone.astype(np.float32))
    # Transient bursts (pick attacks).
    for _ in range(20):
        n = int(0.05 * SR)
        burst = (rng.standard_normal(n).astype(np.float32)) * (0.3 + 0.6 * rng.random())
        burst *= np.exp(-np.arange(n) / SR * 80).astype(np.float32)
        parts.append(burst)
        parts.append(np.zeros(int(0.1 * SR), np.float32))

    sig = np.concatenate(parts)
    target = int(args.seconds * SR)
    if len(sig) < target:
        reps = int(np.ceil(target / len(sig)))
        sig = np.tile(sig, reps)
    sig = sig[:target]
    peak = np.max(np.abs(sig)) + 1e-9
    sig = (sig / peak * 0.9).astype(np.float32)  # normalize below full scale
    sf.write(args.out, sig, SR, subtype="PCM_24")
    print(f"wrote {len(sig)} samples ({len(sig) / SR:.1f}s) @ {SR} -> {args.out}")


if __name__ == "__main__":
    main()
