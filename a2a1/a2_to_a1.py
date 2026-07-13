#!/usr/bin/env python3
"""
A2 -> A1 batch converter for the Valeton GP-50.

Takes NAM A2 captures (SlimmableContainer / .nam) and produces standard A1 WaveNet
.nam files in the 0.5.x format the GP-50's NAM->SnapTone converter accepts. It does
this by distillation: render a DI through the A2 model, then train an A1 model to
reproduce it.

    A2.nam --(render DI, 0.13.0)--> y.wav --(train+export, 0.12.2)--> A1.nam

Then load the A1.nam in Valeton Suite exactly like any A1 capture.

This driver only uses the standard library; it shells out to the two venvs.

Usage:
    python3 a2_to_a1.py INPUT [-o OUTDIR] [--di DI.wav] [--epochs 80]
INPUT may be a single .nam or a directory (all *.nam inside are converted).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def default(path):
    return path if path.exists() else None


def detect_arch(nam_path):
    try:
        with open(nam_path) as fp:
            d = json.load(fp)
        return d.get("architecture"), d.get("version", "?")
    except Exception as e:
        return f"<unreadable: {e}>", "?"


def run(cmd, log_path):
    with open(log_path, "w") as log:
        p = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        log.write(p.stdout)
    return p.returncode, p.stdout


def convert_one(src, args, py_a2, py_a1):
    name = src.stem
    work = Path(args.workdir) / name
    work.mkdir(parents=True, exist_ok=True)
    arch, ver = detect_arch(src)

    result = {
        "name": name,
        "src_arch": arch,
        "esr": None,
        "fmt": None,
        "out": None,
        "note": "",
    }

    if arch == "WaveNet" and str(ver).startswith("0.5"):
        out = Path(args.outdir) / f"{name}.nam"
        shutil.copyfile(src, out)
        result.update(
            out=str(out), note="already A1 0.5.x — copied as-is", fmt=f"version={ver}"
        )
        return result
    if arch != "SlimmableContainer":
        result["note"] = f"skipped: unsupported architecture {arch!r}"
        return result

    y = work / "y.wav"
    rc, _ = run(
        [str(py_a2), str(HERE / "render_a2.py"), str(src), str(args.di), str(y)],
        work / "render.log",
    )
    if rc != 0 or not y.exists():
        result["note"] = f"render failed (rc={rc}); see {work / 'render.log'}"
        return result

    rc, out = run(
        [
            str(py_a1),
            str(HERE / "train_a1.py"),
            str(args.di),
            str(y),
            str(work),
            "--epochs",
            str(args.epochs),
            "--arch",
            args.arch,
        ],
        work / "train.log",
    )
    if rc != 0:
        result["note"] = f"train failed (rc={rc}); see {work / 'train.log'}"
        return result

    a1 = work / "a1.nam"
    if not a1.exists():
        result["note"] = f"no a1.nam produced; see {work / 'train.log'}"
        return result

    # Carry over the source's human name into metadata if present.
    _copy_name_metadata(src, a1)

    final = Path(args.outdir) / f"{name}.nam"
    shutil.copyfile(a1, final)
    m_esr = re.search(r"DISTILL_ESR:\s*([0-9.eE+-]+)", out)
    m_fmt = re.search(r"FORMAT:\s*(.+)", out)
    result.update(
        out=str(final),
        esr=float(m_esr.group(1)) if m_esr else None,
        fmt=m_fmt.group(1).strip() if m_fmt else None,
    )
    if not args.keep_intermediate:
        for f in (y,):
            f.unlink(missing_ok=True)
    return result


def _copy_name_metadata(src, a1):
    try:
        with open(src) as fp:
            s = json.load(fp)
        smeta = s.get("metadata") or {}
        with open(a1) as fp:
            d = json.load(fp)
        meta = d.get("metadata") or {}
        for k in (
            "name",
            "modeled_by",
            "gear_type",
            "gear_make",
            "gear_model",
            "tone_type",
        ):
            if smeta.get(k) and not meta.get(k):
                meta[k] = smeta[k]
        if meta:
            d["metadata"] = meta
            with open(a1, "w") as fp:
                json.dump(d, fp)
    except Exception:
        pass  # metadata is cosmetic; never fail the conversion over it


def main():
    ap = argparse.ArgumentParser(
        description="Convert NAM A2 captures to A1 for the Valeton GP-50."
    )
    ap.add_argument("input", help="A .nam file or a directory of .nam files")
    ap.add_argument("-o", "--outdir", default=str(PROJECT / "out"))
    ap.add_argument(
        "--di",
        default=str(PROJECT / "refs" / "v3_0_0.wav"),
        help="DI input wav (default: official NAM v3_0_0.wav)",
    )
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--arch", default="standard")
    ap.add_argument("--workdir", default=str(PROJECT / "work"))
    ap.add_argument("--venv-a2", default=str(PROJECT / ".venv" / "bin" / "python"))
    ap.add_argument("--venv-a1", default=str(PROJECT / ".venv-a1" / "bin" / "python"))
    ap.add_argument("--keep-intermediate", action="store_true")
    args = ap.parse_args()

    py_a2, py_a1 = Path(args.venv_a2), Path(args.venv_a1)
    for p, label in (
        (py_a2, "0.13.0 venv (--venv-a2)"),
        (py_a1, "0.12.2 venv (--venv-a1)"),
    ):
        if not p.exists():
            sys.exit(f"ERROR: {label} python not found at {p}")
    if not Path(args.di).exists():
        sys.exit(
            f"ERROR: DI file not found at {args.di} (use --di, or make_di.py for a fallback)"
        )

    inp = Path(args.input)
    files = sorted(inp.glob("*.nam")) if inp.is_dir() else [inp]
    if not files:
        sys.exit(f"No .nam files found at {inp}")
    Path(args.outdir).mkdir(parents=True, exist_ok=True)

    print(f"Converting {len(files)} file(s)  epochs={args.epochs}  DI={args.di}\n")
    results = []
    for i, src in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {src.name} ...", flush=True)
        t0 = time.time()
        r = convert_one(src, args, py_a2, py_a1)
        r["secs"] = round(time.time() - t0, 1)
        results.append(r)
        status = r["out"] or r["note"]
        esr = f"ESR={r['esr']:.4f}" if r["esr"] is not None else ""
        print(f"      -> {status}  {esr}  ({r['secs']}s)\n", flush=True)

    print("=" * 72)
    print(f"{'model':28s} {'ESR':>9s}  {'time':>7s}  result")
    for r in results:
        esr = f"{r['esr']:.4f}" if r["esr"] is not None else "-"
        tag = "OK" if r["out"] else "FAIL"
        print(f"{r['name'][:28]:28s} {esr:>9s}  {r['secs']:>6.1f}s  {tag}  {r['note']}")
    n_ok = sum(1 for r in results if r["out"])
    print(f"\n{n_ok}/{len(results)} succeeded. A1 .nam files in {args.outdir}")
    print(
        "Next: open Valeton Suite, import each .nam like any A1 capture -> SnapTone -> GP-50."
    )


if __name__ == "__main__":
    main()
