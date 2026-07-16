"use strict";
/*
 * prst.js — the .prst format + GP-5 <-> GP-50 conversion, in the browser.
 *
 * A faithful port of patch/prst_format.py + patch/convert.py, so the editor and
 * the preset converter can run 100% client-side (no Python backend) for the
 * WebMIDI static-web build. Byte-for-byte verified against the Python oracle
 * over the whole preset corpus (see app/tests/test_prst_js.mjs).
 *
 * Exposes window.PRST in the browser and module.exports under node (for tests).
 */
(function (root) {
  // --- constants (from prst_format.py) --------------------------------------
  const NAME_OFF = 0x19, NAME_LEN = 16, BODY_OFF = 0x29, CRC_OFF = 0x14;
  const SETTINGS_OFF = 0x55, N_BLOCKS = 10, N_PARAM_SLOTS = 80;
  const SENTINEL = [0xff, 0xff, 0xff, 0xff];
  const REC_MODELS = [0x03, 0x30, 0x28, 0x00];
  const REC_BYPASS = [0x01, 0x30, 0x04, 0x00];
  const REC_ORDER = [0x02, 0x30, 0x0a, 0x00]; // 10-byte chain-order permutation (see re/DEVICE_BLOCKORDER.md)
  const REC_PARAMS = [0x04, 0x30, 0x40, 0x01];
  const FS_TRAILER = [0x03, 0x00, 0x0a, 0x00];
  const FS_TRAILER_GP5 = [0x03, 0x00, 0x08, 0x00];

  const hx = (s) => Uint8Array.from(s.match(/../g).map((h) => parseInt(h, 16)));
  const HEADER_GP50 = hx("47502d3530000000000000000000000000000100");
  const HEADER_GP5 = hx("47502d3500000000000000000000000000000100");
  const DEVTAG_GP50 = hx("47503530");
  const DEVTAG_GP5 = hx("0a454d51");

  const GP50 = { key: "gp50", name: "GP-50", header: HEADER_GP50, prstLen: 552, devtag: DEVTAG_GP50, ringFile: "fxid_ring.json", usbPid: 0x018a };
  const GP5 = { key: "gp5", name: "GP-5", header: HEADER_GP5, prstLen: 507, devtag: DEVTAG_GP5, ringFile: "fxid_ring_gp5.json", usbPid: 0x0184 };
  const DEVICES = { gp50: GP50, gp5: GP5 };
  const bodyLen = (p) => p.prstLen - BODY_OFF;
  const profileFor = (key) => { const p = DEVICES[key]; if (!p) throw new Error(`unknown device ${key}`); return p; };

  // --- byte helpers ----------------------------------------------------------
  const u8 = (b) => (b instanceof Uint8Array ? b : Uint8Array.from(b));
  const dv = (b) => new DataView(u8(b).buffer, u8(b).byteOffset, u8(b).byteLength);
  function indexOf(hay, needle, from = 0) {
    hay = u8(hay);
    outer: for (let i = from; i <= hay.length - needle.length; i++) {
      for (let j = 0; j < needle.length; j++) if (hay[i + j] !== needle[j]) continue outer;
      return i;
    }
    return -1;
  }
  function lastIndexOf(hay, needle) {
    hay = u8(hay);
    for (let i = hay.length - needle.length; i >= 0; i--) {
      let ok = true;
      for (let j = 0; j < needle.length; j++) if (hay[i + j] !== needle[j]) { ok = false; break; }
      if (ok) return i;
    }
    return -1;
  }
  const concat = (...arrs) => {
    const parts = arrs.map(u8); const n = parts.reduce((s, a) => s + a.length, 0);
    const out = new Uint8Array(n); let o = 0;
    for (const a of parts) { out.set(a, o); o += a.length; }
    return out;
  };
  const u16le = (v) => Uint8Array.of(v & 0xff, (v >> 8) & 0xff);
  const u32le = (v) => Uint8Array.of(v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, (v >> 24) & 0xff);
  const intLE = (b) => { let v = 0; for (let i = b.length - 1; i >= 0; i--) v = v * 256 + b[i]; return v; };

  // --- CRC (shared with the SysEx wire packets) ------------------------------
  function crc8(bytes, init = 0) {
    let c = init;
    for (const b of bytes) { c ^= b; for (let i = 0; i < 8; i++) c = (c & 0x80) ? ((c << 1) ^ 0x07) & 0xff : (c << 1) & 0xff; }
    return c;
  }
  function refixCrc(b) { b[CRC_OFF] = crc8(u8(b).subarray(CRC_OFF + 1)); }

  function detect(prst) {
    prst = u8(prst);
    for (const p of Object.values(DEVICES)) {
      let hit = true;
      for (let i = 0; i < p.header.length; i++) if (prst[i] !== p.header[i]) { hit = false; break; }
      if (hit) return p;
    }
    for (const p of Object.values(DEVICES)) if (prst.length === p.prstLen) return p;
    throw new Error(`unrecognized .prst (len ${prst.length})`);
  }

  // --- name codec ------------------------------------------------------------
  function readName(prst) {
    prst = u8(prst); let s = "";
    for (let i = NAME_OFF; i < BODY_OFF; i++) { if (prst[i] === 0) break; s += String.fromCharCode(prst[i]); }
    return s.trim();
  }
  function writeName(b, name) {
    for (let i = 0; i < NAME_LEN; i++) b[NAME_OFF + i] = i < name.length ? name.charCodeAt(i) & 0xff : 0;
  }

  // Full .prst from a live device read: name (0x40) + body (0x41). Mirrors
  // prst_format.rebuild — used to turn a WebMIDI slot read into a .prst.
  function rebuild(name, body, profile = GP50) {
    body = u8(body);
    if (body.length !== bodyLen(profile)) throw new Error(`expected a ${bodyLen(profile)}-byte ${profile.name} body, got ${body.length}`);
    const out = concat(profile.header, Uint8Array.of(0), SENTINEL, new Uint8Array(NAME_LEN), body);
    writeName(out, name);
    refixCrc(out);
    return out;
  }

  // --- body records ----------------------------------------------------------
  const modelsOffset = (b) => { const i = indexOf(b, REC_MODELS); return i >= 0 ? i + 4 : -1; };
  function modelRecords(b) {
    b = u8(b); const base = modelsOffset(b); if (base < 0) return [];
    const out = [];
    for (let k = 0; k < N_BLOCKS; k++) {
      const r = b.subarray(base + k * 4, base + k * 4 + 4);
      out.push([r[0], r[3], r[0] | (r[1] << 8) | (r[2] << 16)]); // [idx, cat, fxlow]
    }
    return out;
  }
  function modelRecOffset(b, category) {
    const base = modelsOffset(b);
    if (base < 0) return -1;
    for (let k = 0; k < N_BLOCKS; k++) if (b[base + k * 4 + 3] === category) return base + k * 4;
    return -1;
  }
  const bypassOffset = (b) => { const i = indexOf(b, REC_BYPASS); return i >= 0 ? i + 4 : -1; };
  const orderOffset = (b) => { const i = indexOf(b, REC_ORDER); return i >= 0 ? i + 4 : -1; };
  const paramsOffset = (b) => { const i = indexOf(b, REC_PARAMS); return i >= 0 ? i + 4 : -1; };
  // Chain (signal-path) order: 10-byte permutation, order[chainPos] = model-record
  // index at that position. Records stay in fixed storage order; only this permutes.
  // Missing record -> identity 0..9 (canonical order).
  function readOrder(b) {
    b = u8(b); const o = orderOffset(b);
    if (o < 0) return Array.from({ length: N_BLOCKS }, (_, i) => i);
    return Array.from(b.subarray(o, o + N_BLOCKS));
  }
  function isPermutation(order) {
    if (!order || order.length !== N_BLOCKS) return false;
    const seen = new Set();
    for (const v of order) { if (!Number.isInteger(v) || v < 0 || v >= N_BLOCKS || seen.has(v)) return false; seen.add(v); }
    return true;
  }
  function writeOrder(b, order) {
    if (!isPermutation(order)) throw new Error(`chain order must be a permutation of 0..${N_BLOCKS - 1}`);
    const o = orderOffset(b);
    if (o < 0) throw new Error("patch has no chain-order record");
    for (let i = 0; i < N_BLOCKS; i++) b[o + i] = order[i];
  }
  function bypassMask(b) { const o = bypassOffset(b); return o >= 0 ? dv(b).getUint32(o, true) : 0; }
  function paramFloats(b) {
    const o = paramsOffset(b), d = dv(b), out = [];
    for (let i = 0; i < N_PARAM_SLOTS; i++) out.push(o < 0 ? 0 : d.getFloat32(o + i * 4, true));
    return out;
  }
  function fsOffset(b) {
    for (const magic of [FS_TRAILER, FS_TRAILER_GP5]) { const i = lastIndexOf(b, magic); if (i >= 0) return i + 4; }
    return -1;
  }
  function findTLV(prst, tag) {
    prst = u8(prst); const d = dv(prst); let off = BODY_OFF;
    while (off + 4 <= prst.length) {
      const t = d.getUint16(off, true), ln = d.getUint16(off + 2, true);
      if (t === tag) return prst.subarray(off + 4, off + 4 + ln);
      off += 4 + ln;
    }
    return new Uint8Array(0);
  }

  // --- conversion (from convert.py) ------------------------------------------
  const BLK_FF_PREFIX = hx("010004000100000002000400"); // 12 bytes, then devtag
  const BLK_00_PAYLOAD = hx("011004000a0000000210040008000000");
  const GP50_SETTINGS_DEFAULTS = [[3, 1, 0], [4, 4, 0], [5, 4, 100], [6, 1, 0], [7, 1, 0], [8, 1, 100], [9, 1, 0], [10, 1, 0]];
  const GP50_TRAILER_MODE = Uint8Array.of(0x05, 0x05);
  const GP50_ONLY_FXIDS = { 0x01000001: "PRE · AC Sim", 0x05000008: "PRE · C-Wah", 0x0a00003c: "CAB · AC" };

  const tlv = (tag, payload) => concat(u16le(tag), u16le(payload.length), payload);

  function readVolBpm(prst) {
    prst = u8(prst); const d = dv(prst); let vol = 50, bpm = 120, i = SETTINGS_OFF;
    while (i + 4 <= prst.length && prst[i + 1] === 0x20) {
      const rid = prst[i], ln = d.getUint16(i + 2, true);
      if (![1, 2, 4].includes(ln)) break;
      const val = intLE(prst.subarray(i + 4, i + 4 + ln));
      if (rid === 1) vol = val; else if (rid === 2) bpm = val;
      i += 4 + ln;
    }
    return [vol, bpm];
  }
  function readFootswitches(prst) {
    const off = fsOffset(prst); if (off < 0) return [0, 0];
    const d = dv(prst); return [d.getUint32(off, true), d.getUint32(off + 4, true)];
  }
  function settingsBlock(profile, vol, bpm) {
    if (profile.key === "gp5") {
      const payload = concat(Uint8Array.of(1, 0x20), u16le(4), u32le(vol), Uint8Array.of(2, 0x20), u16le(4), u32le(bpm));
      return tlv(0x0001, payload);
    }
    vol = Math.max(0, Math.min(255, vol));
    let payload = concat(Uint8Array.of(1, 0x20), u16le(1), Uint8Array.of(vol & 0xff), Uint8Array.of(2, 0x20), u16le(4), u32le(bpm));
    for (const [rid, ln, val] of GP50_SETTINGS_DEFAULTS) {
      const vb = new Uint8Array(ln); let v = val; for (let k = 0; k < ln; k++) { vb[k] = v & 0xff; v = Math.floor(v / 256); }
      payload = concat(payload, Uint8Array.of(rid, 0x20), u16le(ln), vb);
    }
    return tlv(0x0001, payload);
  }
  function trailerBlock(profile, fs1, fs2) {
    let payload = concat(u32le(fs1), u32le(fs2));
    if (profile.key === "gp50") payload = concat(payload, GP50_TRAILER_MODE);
    return tlv(0x0003, payload);
  }
  function checkConvertible(prst, targetKey) {
    const target = profileFor(targetKey); if (target.key !== "gp5") return [];
    const out = [];
    modelRecords(prst).forEach(([idx, cat, fxlow], k) => {
      const fxid = (cat << 24) | fxlow;
      if (GP50_ONLY_FXIDS[fxid]) out.push({ blockIndex: k, fxid, model: GP50_ONLY_FXIDS[fxid] });
    });
    return out;
  }
  function dropModels(tone, blockIndices) {
    tone = Uint8Array.from(tone); let base = indexOf(tone, REC_MODELS); if (base < 0) return tone;
    base += 4;
    for (const k of blockIndices) for (let j = 0; j < 4; j++) tone[base + k * 4 + j] = 0;
    return tone;
  }
  function convert(prst, targetKey, { force = false } = {}) {
    prst = u8(prst);
    const source = detect(prst), target = profileFor(targetKey);
    if (source.key === target.key) return prst;
    const problems = checkConvertible(prst, targetKey);
    if (problems.length && !force) {
      const names = problems.map((p) => `block ${p.blockIndex} (${p.model})`).join(", ");
      throw new Error(`cannot convert to ${target.name}: no GP-5 equivalent for ${names}. Swap the block(s) first, or force the conversion to drop them.`);
    }
    const name = readName(prst);
    let tone = findTLV(prst, 0x0002);
    if (tone.length !== 390) throw new Error(`unexpected tone block length ${tone.length} (expected 390)`);
    if (problems.length && force) tone = dropModels(tone, problems.map((p) => p.blockIndex));
    const [vol, bpm] = readVolBpm(prst);
    const [fs1, fs2] = readFootswitches(prst);
    const body = concat(
      tlv(0x00ff, concat(BLK_FF_PREFIX, target.devtag)),
      tlv(0x0000, BLK_00_PAYLOAD),
      settingsBlock(target, vol, bpm),
      tlv(0x0002, tone),
      trailerBlock(target, fs1, fs2)
    );
    const out = concat(target.header, Uint8Array.of(0), SENTINEL, new Uint8Array(NAME_LEN), body);
    writeName(out, name);
    refixCrc(out);
    if (out.length !== target.prstLen) throw new Error(`built ${out.length} bytes, expected ${target.prstLen} for ${target.name}`);
    return out;
  }

  // Apply an edit spec to a .prst, returning a NEW edited .prst (input untouched).
  // Verbatim port of patchlib.apply_edits_bytes; edits = {params, bypass, settings,
  // footswitches, models} as built by the Explorer editor.
  function applyEdits(prst, edits) {
    const b = Uint8Array.from(prst);
    const d = dv(b);
    edits = edits || {};

    // 0. block model changes: 4 bytes [b0][b1][b2][cat], fxid = (cat<<24)|low
    const mb = modelsOffset(b);
    if (mb >= 0) {
      for (const [blk, fxid] of Object.entries(edits.models || {})) {
        const rec = mb + Number(blk) * 4, f = Number(fxid) >>> 0;
        b[rec] = f & 0xff; b[rec + 1] = (f >> 8) & 0xff; b[rec + 2] = (f >> 16) & 0xff; b[rec + 3] = (f >> 24) & 0xff;
      }
    }

    // 1. parameter floats (10 blocks x 8 slots)
    const fi = paramsOffset(b);
    const params = edits.params || {};
    if (fi < 0 && Object.keys(params).length) throw new Error("no parameter array in patch");
    for (const [blk, ps] of Object.entries(params)) {
      for (const [alg, value] of Object.entries(ps)) {
        const slot = Number(blk) * 8 + Number(alg);
        if (slot >= 0 && slot < N_PARAM_SLOTS) d.setFloat32(fi + slot * 4, Number(value), true);
      }
    }

    // 2. bypass bitmask
    const mi = bypassOffset(b);
    if (mi >= 0 && edits.bypass && Object.keys(edits.bypass).length) {
      let mask = d.getUint32(mi, true);
      for (const [blk, on] of Object.entries(edits.bypass)) {
        const bit = 1 << Number(blk);
        mask = on ? (mask | bit) : (mask & ~bit);
      }
      d.setUint32(mi, mask >>> 0, true);
    }

    // 3. patch settings (group 0x20: id1 VOL, id2 BPM)
    const s = edits.settings || {};
    if (Object.keys(s).length) {
      let i = SETTINGS_OFF;
      while (i + 4 <= b.length && b[i + 1] === 0x20) {
        const rid = b[i], ln = d.getUint16(i + 2, true);
        if (![1, 2, 4].includes(ln)) break;
        if (rid === 0x01 && s.patch_vol !== undefined) {
          let vol = Math.max(0, Math.min(100, Math.trunc(Number(s.patch_vol))));
          for (let k = 0; k < ln; k++) { b[i + 4 + k] = vol & 0xff; vol = Math.floor(vol / 256); }
        } else if (rid === 0x02 && s.bpm !== undefined && ln === 4) {
          d.setInt32(i + 4, Math.trunc(Number(s.bpm)), true);
        }
        i += 4 + ln;
      }
    }

    // 4. footswitch masks (fs1 at +0, fs2 at +4, <=2 blocks each)
    const fs = edits.footswitches || {};
    if (Object.keys(fs).length) {
      const off = fsOffset(b);
      if (off >= 0) {
        for (const [key, so] of [["fs1", 0], ["fs2", 4]]) {
          if (fs[key]) {
            let mask = 0;
            fs[key].slice(0, 2).forEach((bi) => { mask |= 1 << Number(bi); });
            d.setUint32(off + so, mask >>> 0, true);
          }
        }
      }
    }

    // 5. patch name (16-byte name region)
    if (edits.name != null) writeName(b, String(edits.name));

    // 6. chain (signal-path) order — 10-byte permutation of the model records
    if (edits.order != null) writeOrder(b, edits.order);

    refixCrc(b);
    return b;
  }

  // Factory-default empty preset ("GP-50" blank), captured verbatim from the
  // device's empty slots — all 23 empty factory slots are byte-identical, so this
  // is the one canonical blank. Slot-independent (the slot is a write-time arg, not
  // stored in the .prst), so the same bytes clear any slot. Used by "Clear Preset".
  const BLANK_B64 = {
    gp50: "R1AtNTAAAAAAAAAAAAAAAAAAAQCv/////0dQLTUwAAAAAAAAAAAAAAD/ABAAAQAEAAEAAAACAAQAR1A1MAAAEAABEAQACgAAAAIQBAAIAAAAAQA7AAEgAQAyAiAEAHgAAAADIAEAAAQgBAAAAAAABSAEAGQAAAAGIAEAAAcgAQAACCABAGQJIAEAAAogAQAAAgCGAQEwBAAAAAAAAjAKAAABAgkDBAUGBwgDMCgAGwAAAAAAAAAAAAADAQAABwEAAAo1AAABAAAABAAAAAsLAAAMAAAADwQwQAEAAKBBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAoEEAAEhCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgQgAAjEIAAEhCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPBBAABIQgAASEIAAAAAAAAAAAAAAAAAAAAAAAAAAAAASEIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEhCAAAAAAAAAAAAAEhCAAAAPwAASEIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAoEEAAPpDAADwQQAAAAAAAAAAAAAAAAAAAAAAAAAAAADwQQAAAAAAAEhCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEhCAABIQgAASEIAAEhCAABIQgAAAAAAAAAAAAAAAAMACgAAAAAAAAAAAAUF",
  };
  const b64bytes = (s) =>
    typeof atob === "function"
      ? Uint8Array.from(atob(s), (c) => c.charCodeAt(0))
      : Uint8Array.from(Buffer.from(s, "base64"));
  // A fresh copy of the factory-default blank .prst for a device (default GP-50).
  function blankPrst(key = "gp50") {
    const b64 = BLANK_B64[typeof key === "object" && key ? key.key : key];
    if (!b64) throw new Error(`no factory blank preset for device ${key}`);
    return b64bytes(b64);
  }

  const API = {
    NAME_OFF, BODY_OFF, NAME_LEN, CRC_OFF, SETTINGS_OFF, N_BLOCKS, N_PARAM_SLOTS,
    GP50, GP5, DEVICES, profileFor, bodyLen,
    crc8, refixCrc, detect, readName, writeName, rebuild,
    modelsOffset, modelRecords, modelRecOffset, bypassOffset, orderOffset, paramsOffset, bypassMask, paramFloats, fsOffset, findTLV,
    readOrder, writeOrder, isPermutation,
    readVolBpm, readFootswitches, checkConvertible, convert, applyEdits,
    BLANK_B64, blankPrst,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.PRST = API;
})(typeof self !== "undefined" ? self : this);
