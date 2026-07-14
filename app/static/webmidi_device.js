"use strict";
/*
 * webmidi_device.js — read/select client for the GP-5 / GP-50 over WebMIDI.
 *
 * The browser-side twin of patch/live_read.py + patch/select_patch.py: same
 * CRC-8/0x07, same nibble framing, same reassembly. Proven byte-for-byte against
 * the Python path on live hardware (see re/DEVICE_READ.md, the WebMIDI section).
 *
 * READ + SELECT ONLY. There is deliberately no write path here — a bad write can
 * wedge the pedal (power-cycle to recover), so writes stay on the gated Python
 * path until that's validated as carefully as reads were.
 *
 * Needs window.PRST (prst.js) for device profiles + rebuild(). Chrome/Edge only.
 *
 *   const dev = await WebMidiDevice.connect();      // {key,name}; throws if none
 *   const names = await WebMidiDevice.readNames();  // [{slot,name}, ...]
 *   await WebMidiDevice.selectSlot(7);              // Program Change (non-destructive)
 *   const prst = await WebMidiDevice.readSlotPrst(7); // select + 0x41 + rebuild -> Uint8Array
 */
(function (root) {
  const PRST = root.PRST;
  const CATSEL = 0x12;
  const SEL_NAMES = 0x40;
  const SEL_BODY = 0x41;
  // Cadence, mirrored from live_read.py: the pedal has a shallow input queue and
  // wedges if requests outrun it. One at a time, settle after each.
  const POST_PC_MS = 300; // settle after a Program Change before reading
  const IDLE_MS = 400; // reply stream considered done after this much quiet
  const READ_TIMEOUT_MS = 2500;
  const SETTLE_MS = 200; // quiet gap after each request completes

  // --- SysEx codec (port of live_read.py) -----------------------------------
  function crc8(bytes) {
    let c = 0;
    for (const b of bytes) { c ^= b; for (let i = 0; i < 8; i++) c = (c & 0x80) ? ((c << 1) ^ 0x07) & 0xff : (c << 1) & 0xff; }
    return c;
  }
  function buildRequest(selector) {
    const buf = [0, 0x01, 0x00, 0x02, CATSEL, selector];
    buf[0] = crc8(buf);
    return buf;
  }
  const toWire = (buf) => buf.flatMap((b) => [b >> 4, b & 0xf]);
  const nibDecode = (arr) => {
    const out = [];
    for (let i = 0; i + 1 < arr.length; i += 2) out.push((arr[i] << 4) | arr[i + 1]);
    return out;
  };
  function reassemble(replies) {
    const byCmd = new Map();
    for (const b of replies) {
      if (b.length < 4) continue;
      if (!byCmd.has(b[1])) byCmd.set(b[1], []);
      byCmd.get(b[1]).push([b[2], b.slice(4)]);
    }
    const out = new Map();
    for (const [cmd, chunks] of byCmd) {
      chunks.sort((a, z) => a[0] - z[0]);
      out.set(cmd, chunks.flatMap((c) => c[1]));
    }
    return out;
  }
  function splitNames(blob, hdr = 2, rec = 20) {
    const names = [];
    const dv = new DataView(new Uint8Array(blob).buffer);
    for (let i = hdr; i + rec <= blob.length; i += rec) {
      const idx = dv.getUint32(i, true);
      let nm = "";
      for (let j = i + 4; j < i + rec; j++) { if (blob[j] === 0) break; nm += String.fromCharCode(blob[j]); }
      names.push({ slot: idx, name: nm.trim() });
    }
    return names;
  }

  // GP-50 first so the "GP-5" substring can't shadow it.
  const findPort = (map) => {
    const ports = [...map.values()];
    return ports.find((p) => (p.name || "").includes("GP-50"))
      || ports.find((p) => (p.name || "").includes("GP-5")) || null;
  };
  const profileForPort = (name) =>
    (name || "").includes("GP-50") ? PRST.GP50 : PRST.GP5;

  // --- connection state ------------------------------------------------------
  let access = null, input = null, output = null, profile = null;
  let namesCache = null;
  let chain = Promise.resolve(); // serializes all device requests (one at a time)

  function assertReady() {
    if (!input || !output) throw new Error("not connected — call WebMidiDevice.connect() first");
    if (!root.PRST) throw new Error("prst.js (window.PRST) is not loaded");
  }

  // Run `fn` after every previously-queued request has finished + settled.
  function serialize(fn) {
    const run = chain.then(fn, fn);
    chain = run.then(
      () => new Promise((r) => setTimeout(r, SETTLE_MS)),
      () => new Promise((r) => setTimeout(r, SETTLE_MS))
    );
    return run;
  }

  // One request/reply exchange: send `wire`, collect nibble-decoded SysEx frames
  // until the stream goes idle, reassemble, return the longest blob.
  function exchange(wire) {
    return new Promise((resolve, reject) => {
      const replies = [];
      const handler = (e) => {
        const d = Array.from(e.data);
        if (d[0] === 0xf0 && d[d.length - 1] === 0xf7) replies.push(nibDecode(d.slice(1, -1)));
      };
      input.onmidimessage = handler;
      try { output.send(wire); }
      catch (err) { input.onmidimessage = null; return reject(err); }
      const t0 = performance.now(); let last = t0, seen = 0;
      const tick = () => {
        if (replies.length > seen) { seen = replies.length; last = performance.now(); }
        const now = performance.now();
        if (now - t0 > READ_TIMEOUT_MS || (seen > 0 && now - last > IDLE_MS)) {
          input.onmidimessage = null;
          const banks = reassemble(replies);
          const blob = [...banks.values()].sort((a, z) => z.length - a.length)[0] || [];
          return resolve({ blob, frames: replies.length });
        }
        setTimeout(tick, 25);
      };
      tick();
    });
  }

  async function connect() {
    if (!navigator.requestMIDIAccess) throw new Error("this browser has no WebMIDI (use Chrome or Edge)");
    access = await navigator.requestMIDIAccess({ sysex: true });
    input = findPort(access.inputs);
    output = findPort(access.outputs);
    if (!input || !output) throw new Error("no GP-5 / GP-50 MIDI port found — connect it and close Valeton Suite");
    profile = profileForPort(input.name);
    namesCache = null;
    return { key: profile.key, name: profile.name, port: input.name };
  }

  const isConnected = () => !!(input && output);
  const device = () => (profile ? { key: profile.key, name: profile.name } : null);

  function readNames() {
    assertReady();
    return serialize(async () => {
      const { blob } = await exchange([0xf0, ...toWire(buildRequest(SEL_NAMES)), 0xf7]);
      namesCache = splitNames(blob);
      return namesCache;
    });
  }

  function selectSlot(slot) {
    assertReady();
    if (!(slot >= 0 && slot <= 99)) throw new Error(`slot ${slot} out of range 0..99`);
    return serialize(async () => {
      output.send([0xc0, slot & 0x7f]); // Program Change — non-destructive
      await new Promise((r) => setTimeout(r, POST_PC_MS));
    });
  }

  // Read the CURRENTLY active patch body (0x41) and rebuild a .prst. `name` labels
  // the patch (the device body carries no name). One retry on a short/raced read.
  function readActivePrst(name = "") {
    assertReady();
    return serialize(async () => {
      const wire = [0xf0, ...toWire(buildRequest(SEL_BODY)), 0xf7];
      const strip = (blob) => (blob[0] === CATSEL && blob[1] === SEL_BODY ? blob.slice(2) : blob);
      const wantLen = PRST.bodyLen(profile);
      let body = strip((await exchange(wire)).blob);
      if (body.length !== wantLen) {
        await new Promise((r) => setTimeout(r, 400));
        body = strip((await exchange(wire)).blob);
      }
      if (body.length !== wantLen) {
        throw new Error(`body read landed ${body.length} bytes (expected ${wantLen})`);
      }
      return PRST.rebuild(name, body, profile);
    });
  }

  // Select slot `slot`, then read its body back as a .prst. Uses the cached name
  // from readNames() (fetched once if not already cached).
  async function readSlotPrst(slot) {
    assertReady();
    if (!namesCache) await readNames();
    const hit = (namesCache || []).find((n) => n.slot === slot);
    await selectSlot(slot);
    return readActivePrst(hit ? hit.name : `slot${slot}`);
  }

  root.WebMidiDevice = {
    connect, disconnect: () => { input = output = access = profile = namesCache = null; },
    isConnected, device, readNames, selectSlot, readActivePrst, readSlotPrst,
    // exposed for tests / the probe
    _codec: { crc8, buildRequest, toWire, nibDecode, reassemble, splitNames, findPort },
  };
})(typeof self !== "undefined" ? self : this);
