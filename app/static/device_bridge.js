"use strict";
/*
 * device_bridge.js — one device-I/O seam for the Explorer, so the same UI works
 * with a Python backend or as a pure static WebMIDI page.
 *
 * Today it fronts the WebMIDI modules (webmidi_device.js / webmidi_write.js).
 * The /api/* paths still live in explorer.js as the fallback; the bridge is the
 * single place the live editor talks to the pedal, and the natural home for a
 * unified WebMIDI-or-/api router as the rewire proceeds.
 */
(function (root) {
  const dev = () => root.WebMidiDevice;
  const wr = () => root.WebMidiWrite;

  const Bridge = {
    webmidiAvailable: () => !!(navigator.requestMIDIAccess && root.WebMidiDevice && root.WebMidiWrite && root.PRST),
    connected: () => !!(dev() && dev().isConnected()),
    device: () => (dev() ? dev().device() : null),

    // Connect over WebMIDI (must be called from a user gesture the first time —
    // the SysEx permission prompt needs it). Returns {key,name,port}.
    async connect() {
      if (!Bridge.webmidiAvailable()) throw new Error("WebMIDI unavailable (use Chrome or Edge, and load prst.js + the webmidi modules)");
      return dev().connect();
    },

    // Read a slot's live .prst (select + 0x41 + rebuild). Uint8Array.
    async readSlotPrst(slot) {
      if (!Bridge.connected()) throw new Error("not connected");
      return dev().readSlotPrst(slot);
    },

    async selectSlot(slot) {
      if (!Bridge.connected()) throw new Error("not connected");
      return dev().selectSlot(slot);
    },

    async readNames() {
      if (!Bridge.connected()) throw new Error("not connected");
      return dev().readNames();
    },

    // Write a full .prst to a slot. The live-edit opt-in is the confirm.
    async writeSlot(slot, prst) {
      if (!Bridge.connected()) throw new Error("not connected");
      return wr().writeSlot(slot, prst, { confirm: true });
    },
  };

  root.DeviceBridge = Bridge;
})(typeof self !== "undefined" ? self : this);
