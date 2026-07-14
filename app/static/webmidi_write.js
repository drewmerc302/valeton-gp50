"use strict";
/*
 * webmidi_write.js — host->device patch WRITE transport for the browser.
 *
 * Port of patch/device_write.py: builds the exact packet stream Valeton Suite
 * sends on a patch import, and gate-sends it over WebMIDI. Kept separate from
 * webmidi_device.js (read/select) because writing is the one operation that can
 * wedge the pedal — this file carries all of that risk and all of its gates.
 *
 * The pure builder/validator (buildPatchWriteStream / validateStream) are
 * verified byte-for-byte against the Python oracle (app/tests/test_write_js.mjs),
 * whose builder is in turn verified 29/29 against real GP-50 Suite captures.
 *
 * writeSlot() REFUSES unless: confirm===true, the stream validates, and the
 * device's write protocol is capture-verified (WRITE_VERIFIED) — mirroring
 * device_write.send_stream. GP-5 write is unverified and refused unless
 * allowUnverified is set. Needs window.PRST and (to send) window.WebMidiDevice.
 */
(function (root) {
  const PRST = root.PRST || (typeof module !== "undefined" && module.exports ? require("./prst.js") : null);

  const PATCH_WRITE_CMD = 0x1d; // host->device patch write (from Suite import captures)
  const PATCH_BLOCK = 19; // payload bytes per write block
  const PATCH_HDR = [0x11, 0x4f]; // constant marker before the slot byte
  const NAME_OFF = 0x19;
  // Which devices' WRITE protocol is capture-verified (see device_write.py).
  const WRITE_VERIFIED = { gp50: true, gp5: false };
  const ACK_WAIT_MS = 150; // wait for the device ACK after each block (shallow queue)

  const crc8 = (bytes) => PRST.crc8(bytes);
  const nibDecode = (mid) => {
    const out = [];
    for (let i = 0; i + 1 < mid.length; i += 2) out.push((mid[i] << 4) | mid[i + 1]);
    return out;
  };
  const expectedPayloadLen = (profile) => 6 + (profile.prstLen - NAME_OFF);

  function buildPacket(cmd, index, payload) {
    const buf = [0, cmd & 0xff, index & 0xff, payload.length & 0xff, ...payload];
    buf[0] = crc8(buf);
    const wire = [0xf0];
    for (const b of buf) wire.push(b >> 4, b & 0x0f);
    wire.push(0xf7);
    return wire;
  }

  // Suite's exact patch-import stream for writing `prst` to `slot`. The 6-byte
  // header replaces the .prst body's leading FF FF FF FF sentinel; payload is
  // prst[0x19:], streamed in 19-byte blocks, index 0..N. Returns wire packets;
  // does NOT send.
  function buildPatchWriteStream(prst, slot) {
    prst = prst instanceof Uint8Array ? prst : Uint8Array.from(prst);
    if (!(slot >= 0 && slot <= 0xff)) throw new Error(`slot out of range: ${slot}`);
    const profile = PRST.detect(prst); // throws if not a known GP-5/GP-50 .prst
    if (prst.length !== profile.prstLen) {
      throw new Error(`expected a ${profile.prstLen}-byte ${profile.name} .prst, got ${prst.length}`);
    }
    const payload = [...PATCH_HDR, slot, 0x00, 0x00, 0x00, ...prst.subarray(NAME_OFF)];
    const packets = [];
    for (let i = 0; i < payload.length; i += PATCH_BLOCK) {
      packets.push(buildPacket(PATCH_WRITE_CMD, Math.floor(i / PATCH_BLOCK), payload.slice(i, i + PATCH_BLOCK)));
    }
    return packets;
  }

  // Confirm a stream is well-formed before sending. Mirrors validate_stream.
  function validateStream(packets) {
    const payload = [];
    for (let i = 0; i < packets.length; i++) {
      const w = packets[i];
      if (!w || w[0] !== 0xf0 || w[w.length - 1] !== 0xf7) return [false, `packet ${i}: not F0..F7 framed`];
      const buf = nibDecode(w.slice(1, -1));
      if (buf.length < 4) return [false, `packet ${i}: truncated`];
      const [crc, cmd, index, length] = buf;
      if (crc8(buf.slice(1)) !== crc) return [false, `packet ${i}: bad CRC`];
      if (cmd !== PATCH_WRITE_CMD) return [false, `packet ${i}: cmd ${cmd} != patch-write ${PATCH_WRITE_CMD}`];
      if (index !== i) return [false, `packet ${i}: non-contiguous index ${index}`];
      if (length !== buf.length - 4) return [false, `packet ${i}: length ${length} != payload ${buf.length - 4}`];
      for (let j = 0; j < length; j++) payload.push(buf[4 + j]);
    }
    const validLens = {};
    for (const p of Object.values(PRST.DEVICES)) validLens[expectedPayloadLen(p)] = p.name;
    if (!(payload.length in validLens)) {
      return [false, `payload ${payload.length} bytes, expected one of ${Object.keys(validLens).sort()} (GP-50/GP-5)`];
    }
    if (payload[0] !== PATCH_HDR[0] || payload[1] !== PATCH_HDR[1]) {
      return [false, `payload header ${payload[0]},${payload[1]} != ${PATCH_HDR}`];
    }
    return [true, "ok"];
  }

  function inferDeviceKey(packets) {
    let total = 0;
    for (const w of packets) {
      if (!w || w[0] !== 0xf0 || w[w.length - 1] !== 0xf7) return null;
      const buf = nibDecode(w.slice(1, -1));
      if (buf.length >= 4) total += buf[3];
    }
    for (const p of Object.values(PRST.DEVICES)) if (expectedPayloadLen(p) === total) return p.key;
    return null;
  }

  // Gate-send a patch write to `slot`. REFUSES unless confirm===true, the stream
  // validates, and the device's write protocol is verified. Paces like Suite:
  // one block, wait for the device ACK (up to ACK_WAIT_MS), then the next.
  async function writeSlot(slot, prst, { confirm = false, allowUnverified = false } = {}) {
    const dev = root.WebMidiDevice;
    if (!dev || !dev.isConnected()) throw new Error("not connected — WebMidiDevice.connect() first");
    const packets = buildPatchWriteStream(prst, slot);
    const [ok, reason] = validateStream(packets);
    if (!ok) throw new Error(`refusing to send: stream did not validate (${reason})`);
    if (!confirm) throw new Error("refusing to send: writeSlot requires { confirm: true }");
    if (!allowUnverified) {
      const key = inferDeviceKey(packets);
      if (key && !WRITE_VERIFIED[key]) {
        throw new Error(`refusing to send: the ${key} patch-write protocol is not capture-verified. Pass { allowUnverified: true } to override at your own risk.`);
      }
    }
    return dev._sendStream(packets, { confirm: true, validated: true, ackWaitMs: ACK_WAIT_MS });
  }

  const API = {
    PATCH_WRITE_CMD, PATCH_BLOCK, PATCH_HDR, WRITE_VERIFIED,
    buildPacket, buildPatchWriteStream, validateStream, expectedPayloadLen, inferDeviceKey, writeSlot,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.WebMidiWrite = API;
})(typeof self !== "undefined" ? self : this);
