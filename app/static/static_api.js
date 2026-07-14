"use strict";
/*
 * static_api.js — serve the /api/device/* surface client-side, so the Explorer
 * runs with no Python backend. Activated by ?static=1 or window.__VALETON_STATIC__.
 *
 * It intercepts window.fetch: /api/device/* is answered from a bundled snapshot
 * (app/static/data/) decoded by patchlib.js, with device I/O over DeviceBridge
 * (WebMIDI) and the block library in localStorage. Everything else falls through
 * to the real fetch. The Explorer's own code is untouched — it still "calls the
 * backend"; the backend is just in the page now.
 */
(function (root) {
  const STATIC = (() => {
    try { return new URLSearchParams(location.search).has("static") || root.__VALETON_STATIC__ === true; }
    catch { return root.__VALETON_STATIC__ === true; }
  })();
  if (!STATIC) return;

  const PRST = root.PRST, PatchLib = root.PatchLib, Bridge = root.DeviceBridge;
  const realFetch = root.fetch.bind(root);
  const LS_LIB = "valeton_blocklib", LS_TPL = "valeton_templates";

  // once the user has interacted, status checks may connect WebMIDI (needs a
  // gesture); before that, don't auto-prompt on page load.
  let userEngaged = false;
  const engage = () => { userEngaged = true; };
  for (const ev of ["pointerdown", "keydown", "click"]) root.addEventListener(ev, engage, { capture: true });

  const J = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });
  const b64ToBytes = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const bytesToB64 = (u) => btoa(String.fromCharCode.apply(null, u));
  const lsGet = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
  const lsSet = (k, v) => localStorage.setItem(k, JSON.stringify(v));

  // --- data store (bundled snapshot) -----------------------------------------
  let store = null; // { profile, lib, bytes: Map(slot->Uint8Array), names: Map, snapshotName: Map }
  let invCache = null;
  let loading = null;

  async function ensureLoaded() {
    if (store) return store;
    if (loading) return loading;
    loading = (async () => {
      const snap = await realFetch("/static/data/presets.json").then((r) => r.json());
      const profile = PRST.profileFor(snap.device || "gp50");
      const ring = await realFetch(`/static/data/${profile.ringFile}`).then((r) => r.json());
      const bankMap = await realFetch("/static/data/bank_map.json").then((r) => r.ok ? r.json() : {}).catch(() => ({}));
      const bytes = new Map(), names = new Map();
      for (const p of snap.presets) { bytes.set(p.slot, b64ToBytes(p.b64)); names.set(p.slot, p.name); }
      store = { profile, lib: PatchLib.make(ring, bankMap, profile), bytes, names };
      return store;
    })();
    return loading;
  }

  const presetList = () => [...store.bytes.keys()].sort((a, z) => a - z)
    .map((slot) => ({ slot, bytes: store.bytes.get(slot), name: store.names.get(slot) }));
  const inventory = () => (invCache ||= store.lib.inventory(presetList()));
  const invalidate = () => { invCache = null; };
  const deviceObj = () => ({ key: store.profile.key, name: store.profile.name, usb_pid: store.profile.usbPid, prst_len: store.profile.prstLen });

  // --- device I/O helpers (WebMIDI) ------------------------------------------
  async function ensureConnected() {
    if (Bridge.connected()) return true;
    if (!Bridge.webmidiAvailable() || !userEngaged) return false;
    try { await Bridge.connect(); return true; } catch { return false; }
  }

  // --- endpoint handlers ------------------------------------------------------
  async function handle(method, path, body) {
    await ensureLoaded();

    if (path === "/api/device/inventory") return J({ patches: inventory().patches, device: deviceObj() });
    if (path === "/api/device/facets") return J(store.lib.facets(inventory().patches));

    let m;
    if ((m = path.match(/^\/api\/device\/models\/(.+)$/))) {
      const block = decodeURIComponent(m[1]);
      return J({ models: store.lib.modelsForBlock(block, inventory().snaptones) });
    }

    if (path === "/api/device/blocklib" && method === "GET") return J({ entries: lsGet(LS_LIB, []) });
    if (path === "/api/device/blocklib" && method === "POST") {
      const entries = lsGet(LS_LIB, []);
      const entry = { id: `${Date.now()}-${entries.length}`, ...body };
      entries.push(entry); lsSet(LS_LIB, entries);
      return J(entry);
    }
    if ((m = path.match(/^\/api\/device\/blocklib\/(.+)$/)) && method === "DELETE") {
      lsSet(LS_LIB, lsGet(LS_LIB, []).filter((e) => e.id !== decodeURIComponent(m[1])));
      return J({ ok: true });
    }

    if (path === "/api/device/status") {
      await ensureConnected();
      const connected = Bridge.connected();
      return J({ connected, device: connected ? Bridge.device() : deviceObj(), port: connected ? Bridge.device().name : null });
    }

    if (path === "/api/device/select") {
      if (!(await ensureConnected())) return J({ ok: false, error: "no device connected (click ‘No device’ to connect)" });
      try {
        await Bridge.selectSlot(body.slot);
        const live = await Bridge.readSlotPrst(body.slot); // pull live state into cache
        store.bytes.set(body.slot, live); invalidate();
        return J({ ok: true, cache_updated: true });
      } catch (e) { return J({ ok: false, error: e.message }); }
    }

    if (path === "/api/device/write") return handleWrite(body);
    if (path === "/api/device/swap") return handleSwap(body);
    if (path === "/api/device/edit") return handleEdit(body);

    if (path === "/api/device/templates/from-patch") {
      const tpls = lsGet(LS_TPL, []);
      tpls.push({ id: `${Date.now()}`, name: body.name, source_slot: body.source_slot });
      lsSet(LS_TPL, tpls);
      return J({ ok: true });
    }

    if (path === "/api/device/scan" && method === "POST") return startScan();
    if (path === "/api/device/scan/status") return J(scanState);

    return J({ detail: `static_api: unhandled ${method} ${path}` }, 404);
  }

  function editsFrom(body) {
    return { params: body.params || {}, bypass: body.bypass || {}, settings: body.settings || {}, footswitches: body.footswitches || {}, models: body.models || {} };
  }

  async function handleWrite(body) {
    if (!(await ensureConnected())) return J({ ok: false, error: "no device connected" });
    const base = store.bytes.get(body.patch_slot);
    if (!base) return J({ ok: false, error: `unknown slot ${body.patch_slot}` });
    const hasEdits = ["params", "bypass", "settings", "footswitches", "models"].some((k) => body[k] && Object.keys(body[k]).length);
    const prst = hasEdits ? PRST.applyEdits(base, editsFrom(body)) : base;
    const target = body.target_slot;
    try {
      const r = await Bridge.writeSlot(target, prst);
      store.bytes.set(target, prst); store.names.set(target, PRST.readName(prst)); invalidate();
      return J({ ok: true, acks: r.acks, packets: r.sent, verified_name: PRST.readName(prst) });
    } catch (e) { return J({ ok: false, error: e.message }); }
  }

  async function handleSwap(body) {
    if (!(await ensureConnected())) return J({ ok: false, error: "no device connected" });
    const a = body.slot_a, z = body.slot_b;
    const ba = store.bytes.get(a), bz = store.bytes.get(z);
    if (!ba || !bz) return J({ ok: false, error: "unknown slot" });
    try {
      await Bridge.writeSlot(z, ba);
      await Bridge.writeSlot(a, bz);
      store.bytes.set(z, ba); store.bytes.set(a, bz);
      const na = store.names.get(a), nz = store.names.get(z);
      store.names.set(a, nz); store.names.set(z, na); invalidate();
      return J({ ok: true });
    } catch (e) { return J({ ok: false, error: e.message }); }
  }

  function handleEdit(body) {
    const base = store.bytes.get(body.patch_slot);
    if (!base) return J({ detail: `unknown slot ${body.patch_slot}` }, 400);
    const prst = PRST.applyEdits(base, editsFrom(body));
    const stem = (store.names.get(body.patch_slot) || `slot${body.patch_slot}`).replace(/\s+/g, "_");
    return new Response(prst, { status: 200, headers: { "Content-Type": "application/octet-stream", "Content-Disposition": `attachment; filename="${stem}__edited.prst"` } });
  }

  // --- device scan (rebuild the snapshot from the pedal over WebMIDI) ---------
  let scanState = { running: false, done: 0, total: 0, current: "", errors: 0, written: 0, error: null };
  async function startScan() {
    if (scanState.running) return J({ ok: true });
    if (!(await ensureConnected())) return J({ ok: false, error: "no device connected" });
    scanState = { running: true, done: 0, total: 100, current: "", errors: 0, written: 0, error: null };
    (async () => {
      try {
        const names = await Bridge.readNames();
        scanState.total = names.length || 100;
        for (const { slot, name } of names) {
          scanState.current = `#${slot} ${name}`;
          try {
            const prst = await Bridge.readSlotPrst(slot);
            store.bytes.set(slot, prst); store.names.set(slot, PRST.readName(prst) || name);
            scanState.written++;
          } catch { scanState.errors++; }
          scanState.done++;
        }
        invalidate();
      } catch (e) { scanState.error = e.message; }
      finally { scanState.running = false; }
    })();
    return J({ ok: true });
  }

  // --- install the interceptor ------------------------------------------------
  root.fetch = function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
    if (path.startsWith("/api/device/")) {
      const method = (init && init.method) || (typeof input === "object" && input.method) || "GET";
      let body = {};
      if (init && init.body) { try { body = JSON.parse(init.body); } catch { body = {}; } }
      return handle(method.toUpperCase(), path, body).catch((e) => J({ ok: false, error: String(e && e.message || e) }, 500));
    }
    return realFetch(input, init);
  };

  root.__staticApi = { handle, ensureLoaded }; // for tests
  console.log("[static_api] active — /api/device/* served client-side");
})(typeof self !== "undefined" ? self : this);
