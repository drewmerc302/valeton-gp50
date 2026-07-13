#!/usr/bin/env python
"""
Valeton GP-50 MIDI SysEx logger.

Purpose: learn the Valeton Suite <-> GP-50 protocol (how it lists/dumps patches,
SnapTones, IRs, and uploads SnapTone data) by recording MIDI traffic. Everything
the editor does with the pedal is USB-MIDI SysEx, so it is all observable.

Two capture modes:

  PASSIVE (default) -- open the real "GP-50" CoreMIDI source alongside the Suite and
    log device->host messages. Reliable. Captures the pedal's replies and any dump
    the pedal sends when the Suite reads it. Does NOT see the Suite's outgoing
    requests (CoreMIDI won't let a bystander observe another app's output to a
    destination).

  PROXY  (--proxy) -- create a virtual "GP-50 Proxy" port pair, forward both ways to
    the real pedal, and log BOTH directions (H>D and D>H). Only works if you can
    point Valeton Suite at the "GP-50 Proxy" port instead of "GP-50". If the Suite
    has no MIDI-port picker and grabs the hardware directly, use passive mode + the
    Snoize "MIDI Monitor" app (its spy driver sees host->device too).

This tool only *observes/forwards*. In passive mode it sends nothing. In proxy mode
it forwards exactly what the Suite sends -- it never originates vendor commands.

Usage:
    python midi_sniff.py [--proxy] [--seconds N] [--out PREFIX] [--match GP-50]
    python midi_sniff.py --analyze PREFIX.jsonl     # re-summarize a saved capture
Run with the .venv-midi venv (python-rtmidi). Stop with Ctrl-C.
"""

import argparse
import json
import sys
import time

import rtmidi

# rtmidi message-type filters we drop as noise (real-time clock / active sensing).
NOISE = {0xF8, 0xFE, 0xFA, 0xFB, 0xFC}


def find_port(midi, match):
    for i, name in enumerate(midi.get_ports()):
        if match.lower() in name.lower():
            return i, name
    return None, None


def hexs(data):
    return " ".join(f"{b:02X}" for b in data)


class Recorder:
    def __init__(self, prefix, gap=3.0):
        self.t0 = time.time()
        self.events = []
        self.gap = gap  # idle seconds that separate one Suite action from the next
        self.last_t = None
        self.session = 0
        self.jsonl = open(f"{prefix}.jsonl", "w")
        self.txt = open(f"{prefix}.log", "w")

    def _maybe_mark_session(self, t):
        # First traffic, or traffic after an idle gap, starts a new "session" segment.
        if self.last_t is None or (t - self.last_t) > self.gap:
            self.session += 1
            marker = f"\n----- SESSION {self.session} start (t={t:.2f}s) -----"
            self.txt.write(marker + "\n")
            self.txt.flush()
            print(marker, flush=True)

    def record(self, direction, data):
        if data and data[0] in NOISE:
            return
        t = time.time() - self.t0
        self._maybe_mark_session(t)
        self.last_t = t
        is_sysex = bool(data) and data[0] == 0xF0
        rec = {
            "t": round(t, 5),
            "session": self.session,
            "dir": direction,
            "len": len(data),
            "sysex": is_sysex,
            "hex": hexs(data),
        }
        self.events.append(rec)
        self.jsonl.write(json.dumps(rec) + "\n")
        self.jsonl.flush()
        kind = f"SYSEX[{len(data)}]" if is_sysex else "msg"
        line = f"{t:9.4f}  {direction}  {kind:11s} {rec['hex']}"
        self.txt.write(line + "\n")
        self.txt.flush()
        preview = rec["hex"] if len(rec["hex"]) <= 180 else rec["hex"][:177] + "..."
        print(f"{t:9.4f}  {direction}  {kind:11s} {preview}", flush=True)

    def close(self):
        self.jsonl.close()
        self.txt.close()

    def summary(self):
        print("\n" + "=" * 60)
        print(f"captured {len(self.events)} messages")
        sysex = [e for e in self.events if e["sysex"]]
        print(f"  sysex: {len(sysex)}  other: {len(self.events) - len(sysex)}")
        by_dir = {}
        for e in self.events:
            by_dir[e["dir"]] = by_dir.get(e["dir"], 0) + 1
        print("  by direction:", by_dir)
        if sysex:
            lens = sorted({e["len"] for e in sysex})
            print("  sysex lengths seen:", lens[:20], ("..." if len(lens) > 20 else ""))
            big = sorted(sysex, key=lambda e: -e["len"])[:5]
            print("  largest sysex (likely patch/SnapTone/IR dumps):")
            for e in big:
                head = " ".join(e["hex"].split()[:12])
                print(f"    {e['len']:6d} bytes  {e['dir']}  head: {head} ...")


def analyze(path):
    events = [json.loads(l) for l in open(path)]
    r = Recorder.__new__(Recorder)
    r.events = events
    r.summary()


def passive(args, rec):
    midi_in = rtmidi.MidiIn()
    midi_in.ignore_types(sysex=False, timing=True, active_sense=True)
    idx, name = find_port(midi_in, args.match)
    if idx is None:
        sys.exit(f"No MIDI input matching {args.match!r}. Ports: {midi_in.get_ports()}")
    midi_in.open_port(idx)
    print(
        f"PASSIVE: logging device->host from {name!r}. Open Valeton Suite and read "
        f"the pedal. Ctrl-C to stop.\n"
    )

    def cb(event, _):
        rec.record("D>H", list(event[0]))

    midi_in.set_callback(cb)
    wait(args, rec)
    midi_in.close_port()


def proxy(args, rec):
    # Real device handles.
    real_in = rtmidi.MidiIn()
    real_out = rtmidi.MidiOut()
    ii, in_name = find_port(real_in, args.match)
    oi, out_name = find_port(real_out, args.match)
    if ii is None or oi is None:
        sys.exit(
            f"GP-50 not found. in={real_in.get_ports()} out={real_out.get_ports()}"
        )
    real_in.ignore_types(sysex=False, timing=True, active_sense=True)
    real_in.open_port(ii)
    real_out.open_port(oi)

    # Virtual endpoints the Suite should connect to.
    virt_out = rtmidi.MidiOut()  # a SOURCE the Suite reads (device->host to Suite)
    virt_in = rtmidi.MidiIn()  # a DEST the Suite writes (host->device from Suite)
    virt_in.ignore_types(sysex=False, timing=True, active_sense=True)
    virt_out.open_virtual_port("GP-50 Proxy")
    virt_in.open_virtual_port("GP-50 Proxy")

    def from_device(event, _):
        data = list(event[0])
        rec.record("D>H", data)
        virt_out.send_message(data)  # forward to Suite

    def from_suite(event, _):
        data = list(event[0])
        rec.record("H>D", data)
        real_out.send_message(data)  # forward to pedal

    real_in.set_callback(from_device)
    virt_in.set_callback(from_suite)
    print(
        "PROXY: created virtual port 'GP-50 Proxy'.\n"
        "  In Valeton Suite, select MIDI port 'GP-50 Proxy' (NOT 'GP-50').\n"
        "  Both directions will be logged. Ctrl-C to stop.\n"
    )
    wait(args, rec)
    for h in (real_in, virt_in):
        h.close_port()


def wait(args, rec=None):
    # Heartbeat so a long idle capture visibly stays alive; session boundaries are
    # printed by the recorder as traffic arrives.
    try:
        start = time.time()
        last_beat = start
        while True:
            if args.seconds > 0 and time.time() - start >= args.seconds:
                break
            time.sleep(0.2)
            now = time.time()
            if rec is not None and now - last_beat >= 15:
                last_beat = now
                n = len(rec.events)
                idle = (
                    "-"
                    if rec.last_t is None
                    else f"{now - start - rec.last_t:.0f}s idle"
                )
                print(f"  … listening ({n} msgs, {idle})", flush=True)
    except KeyboardInterrupt:
        print("\nstopped.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--proxy", action="store_true", help="MITM both directions via a virtual port"
    )
    ap.add_argument("--seconds", type=int, default=0, help="0 = until Ctrl-C")
    ap.add_argument(
        "--out", default="valeton_sniff", help="output prefix (.jsonl + .log)"
    )
    ap.add_argument("--match", default="GP-50", help="MIDI port name substring")
    ap.add_argument(
        "--gap",
        type=float,
        default=3.0,
        help="idle seconds that separate one Suite action into a new session marker",
    )
    ap.add_argument("--analyze", help="summarize a saved .jsonl instead of capturing")
    args = ap.parse_args()

    if args.analyze:
        analyze(args.analyze)
        return

    rec = Recorder(args.out, gap=args.gap)
    try:
        (proxy if args.proxy else passive)(args, rec)
    finally:
        rec.close()
        rec.summary()
        print(f"\nsaved: {args.out}.jsonl  {args.out}.log")


if __name__ == "__main__":
    main()
