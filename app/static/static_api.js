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
  const LS_LIB = "valeton_blocklib", LS_TPL = "valeton_templates", LS_SCAN = "valeton_scanCache", LS_BANKMAP = "valeton_bankMap";

  // Resolve the data dir relative to THIS script's URL, so the shim works whether
  // it's served at /static/static_api.js (backend) or ./static_api.js (a static
  // host mounted at root).
  const DATA_BASE = (() => {
    try { const s = document.currentScript && document.currentScript.src; if (s) return new URL("data/", s).href; } catch { /* fall through */ }
    return "/static/data/";
  })();
  const dataUrl = (f) => new URL(f, DATA_BASE).href;

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

  // --- scan cache (persists real device reads across reloads/tab closes) -----
  // Every slot read straight off the pedal (scan, live select, or a write we just
  // made) gets written here so a refresh never throws away real preset data —
  // only the still-unscanned slots keep showing the blank bundle. Keyed by device
  // profile so a GP-5 cache never bleeds into a GP-50 session or vice versa.
  function persistSlot(slot) {
    if (!store) return;
    const prst = store.bytes.get(slot);
    if (!prst) return;
    const cache = lsGet(LS_SCAN, {});
    if (cache.profileKey !== store.profile.key) { cache.profileKey = store.profile.key; cache.slots = {}; }
    cache.slots = cache.slots || {};
    cache.slots[slot] = { b64: bytesToB64(prst), name: store.names.get(slot) || "", ts: Date.now() };
    lsSet(LS_SCAN, cache);
  }
  // slots read within the last few minutes are treated as part of a scan the user
  // is actively resuming (e.g. after an accidental reload) — safe to skip
  // re-reading from the pedal. Older entries are just "last known" data; an
  // explicit rescan always re-reads them in case the preset changed on the device.
  const RESUME_WINDOW_MS = 5 * 60 * 1000;

  // --- data store (bundled snapshot) -----------------------------------------
  let store = null; // { profile, lib, bytes: Map(slot->Uint8Array), names: Map, snapshotName: Map }
  let invCache = null;
  let loading = null;

  async function ensureLoaded() {
    if (store) return store;
    if (loading) return loading;
    loading = (async () => {
      const snap = await realFetch(dataUrl("presets.json")).then((r) => r.json());
      const profile = PRST.profileFor(snap.device || "gp50");
      const ring = await realFetch(dataUrl(profile.ringFile)).then((r) => r.json());
      let bankMap = await realFetch(dataUrl("bank_map.json")).then((r) => r.ok ? r.json() : {}).catch(() => ({}));
      // A prior "Sync SnapTones and IRs from device" only ever lived in memory —
      // same reload-loses-it bug as the preset scan. Restore it here so real IR/
      // SnapTone names survive a refresh instead of falling back to "User IR N".
      const savedBankMap = lsGet(LS_BANKMAP, null);
      if (savedBankMap && savedBankMap.profileKey === profile.key && savedBankMap.bankMap) bankMap = savedBankMap.bankMap;
      const bytes = new Map(), names = new Map();
      for (const p of snap.presets) { bytes.set(p.slot, b64ToBytes(p.b64)); names.set(p.slot, p.name); }
      // Overlay any real device reads we've cached locally, so a reload shows the
      // user's actual presets instead of the blank bundle for every slot already
      // scanned in a prior visit.
      const cache = lsGet(LS_SCAN, null);
      let cachedCount = 0;
      if (cache && cache.profileKey === profile.key && cache.slots) {
        for (const [slotStr, entry] of Object.entries(cache.slots)) {
          try { bytes.set(Number(slotStr), b64ToBytes(entry.b64)); names.set(Number(slotStr), entry.name); cachedCount++; }
          catch { /* corrupt cache entry — skip it, keep the bundle default */ }
        }
      }
      store = { profile, ring, bankMap, lib: PatchLib.make(ring, bankMap, profile), bytes, names, cachedCount };
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

    if (path === "/api/device/inventory") {
      const inv = inventory();
      return J({
        source: `bundled snapshot (${store.bytes.size} presets)`,
        device: deviceObj(), snaptones: inv.snaptones, irs: inv.irs, patches: inv.patches,
        domains: { patch_slots: [0, 99], snaptone_slots: [0, 79], user_snaptone_slots: [50, 79], user_ir_base: 0x100000 },
      });
    }
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
        persistSlot(body.slot);
        return J({ ok: true, cache_updated: true });
      } catch (e) { return J({ ok: false, error: e.message }); }
    }

    if (path === "/api/device/write") return handleWrite(body);
    if (path === "/api/device/swap") return handleSwap(body);
    if (path === "/api/device/edit") return handleEdit(body);

    if (path === "/api/device/templates" && method === "GET") {
      return J({ templates: lsGet(LS_TPL, []).map(publicTpl) });
    }
    if (path === "/api/device/templates/from-patch") {
      const base = store.bytes.get(body.source_slot);
      if (!base) return J({ detail: `unknown slot ${body.source_slot}` }, 400);
      const patch = inventory().patches.find((p) => p.slot === body.source_slot) || {};
      const tpls = lsGet(LS_TPL, []);
      const entry = {
        id: `${Date.now().toString(36)}${tpls.length}`, name: (body.name || "").trim(),
        source_slot: body.source_slot, source_name: patch.name || "",
        summary: summaryOf(patch), body_b64: bytesToB64(base),
      };
      tpls.push(entry); lsSet(LS_TPL, tpls);
      return J(publicTpl(entry));
    }
    if ((m = path.match(/^\/api\/device\/templates\/(.+)$/)) && method === "DELETE") {
      const id = decodeURIComponent(m[1]);
      const tpls = lsGet(LS_TPL, []);
      lsSet(LS_TPL, tpls.filter((t) => t.id !== id));
      return J({ deleted: tpls.some((t) => t.id === id) });
    }
    if (path === "/api/device/build") return handleBuild(body);
    if (path === "/api/device/sync" && method === "POST") return handleSync();

    if (path === "/api/device/scan" && method === "POST") return startScan();
    if (path === "/api/device/scan/status") return J(scanState);

    return J({ detail: `static_api: unhandled ${method} ${path}` }, 404);
  }

  const publicTpl = (t) => { const { body_b64, ...rest } = t; return rest; };
  const summaryOf = (patch) => {
    const chain = (patch.blocks || []).filter((b) => b.active)
      .map((b) => ({ block: b.block, type: b.type ?? null, model: b.model ?? null, official: b.official ?? null, active: b.active }));
    return { chain, uses_snaptone: !!patch.uses_snaptone, block_count: chain.length };
  };

  // Repoint a body's N->S (SnapTone) block, optionally rename, refix CRC. Port of
  // patchlib.repoint_snaptone_body (NS_CAT = 0x0F).
  function repointSnaptone(prst, targetNsSlot, name) {
    if (!(targetNsSlot >= 0 && targetNsSlot <= 79)) throw new Error(`SnapTone slot out of range: ${targetNsSlot}`);
    const b = Uint8Array.from(prst);
    const off = PRST.modelRecOffset(b, 0x0f);
    if (off < 0) throw new Error("patch has no N->S (SnapTone) block to repoint");
    b[off] = targetNsSlot;
    if (name != null) PRST.writeName(b, name);
    PRST.refixCrc(b);
    return b;
  }

  async function handleBuild(body) {
    const tpl = lsGet(LS_TPL, []).find((t) => t.id === body.template_id);
    if (!tpl) return J({ detail: `unknown template ${body.template_id}` }, 404);
    const st = inventory().snaptones.find((s) => s.slot === body.snaptone_slot);
    const name = body.name || (st && st.name) || `NS${body.snaptone_slot}`;
    let prst;
    try { prst = repointSnaptone(b64ToBytes(tpl.body_b64), body.snaptone_slot, name); }
    catch (e) { return J({ detail: e.message }, 400); }
    if (body.download) {
      const safe = (name.match(/[A-Za-z0-9]+/g) || ["patch"]).join("") || "patch";
      return new Response(prst, { status: 200, headers: { "Content-Type": "application/octet-stream", "Content-Disposition": `attachment; filename="${safe}.prst"` } });
    }
    if (!body.confirm) return J({ ok: false, error: "confirm required" });
    if (!(body.target_slot >= 0 && body.target_slot <= 99)) return J({ ok: false, error: "target_slot 0..99 required" });
    if (!(await ensureConnected())) return J({ ok: false, error: "no device connected" });
    try {
      const r = await Bridge.writeSlot(body.target_slot, prst);
      store.bytes.set(body.target_slot, prst); store.names.set(body.target_slot, PRST.readName(prst)); invalidate();
      persistSlot(body.target_slot);
      return J({ ok: true, acks: r.acks, packets: r.sent, verified_name: PRST.readName(prst) });
    } catch (e) { return J({ ok: false, error: e.message }); }
  }

  function editsFrom(body) {
    return { params: body.params || {}, bypass: body.bypass || {}, settings: body.settings || {}, footswitches: body.footswitches || {}, models: body.models || {}, name: body.name, order: body.order };
  }

  async function handleWrite(body) {
    if (!(await ensureConnected())) return J({ ok: false, error: "no device connected" });
    const base = store.bytes.get(body.patch_slot);
    if (!base) return J({ ok: false, error: `unknown slot ${body.patch_slot}` });
    const hasEdits = ["params", "bypass", "settings", "footswitches", "models"].some((k) => body[k] && Object.keys(body[k]).length)
      || body.name != null || body.order != null;
    const prst = hasEdits ? PRST.applyEdits(base, editsFrom(body)) : base;
    const target = body.target_slot;
    try {
      const r = await Bridge.writeSlot(target, prst);
      store.bytes.set(target, prst); store.names.set(target, PRST.readName(prst)); invalidate();
      persistSlot(target);
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
      persistSlot(a); persistSlot(z);
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

  // --- SnapTone/IR catalog sync (port of patch/read_bank_map.py) --------------
  const nameAt = (blob, i, len) => { let s = ""; for (let j = i; j < i + len && j < blob.length; j++) { if (blob[j] === 0) break; s += String.fromCharCode(blob[j]); } return s.trim(); };
  // SnapTone catalog (selector 0x24): names from offset 82, 16-byte records; keep
  // user slots (>=50) that are named and not "Empty".
  function parseCatalog(blob) {
    const out = {};
    for (let i = 82; i + 16 <= blob.length; i += 16) {
      const idx = (i - 82) / 16, name = nameAt(blob, i, 16);
      if (idx >= 50 && name && name !== "Empty") out[idx] = name;
    }
    return out;
  }
  // User IR bank (selector 0x20): names from offset 22, 16-byte records; keep real
  // names (skip the generic "User IR N" defaults).
  function parseIrBank(blob) {
    const out = {};
    for (let i = 22; i + 16 <= blob.length; i += 16) {
      const idx = (i - 22) / 16, name = nameAt(blob, i, 16);
      if (name && !name.toLowerCase().startsWith("user ir")) out[idx] = name;
    }
    return out;
  }
  async function handleSync() {
    if (!(await ensureConnected())) return J({ ok: false, error: "no device connected" });
    try {
      const snaptone = parseCatalog(await Bridge.readBankBlob(0x24));
      const ir = parseIrBank(await Bridge.readBankBlob(0x20));
      store.bankMap = { source: "live device read (WebMIDI selectors 0x24 + 0x20)", snaptone, ir };
      store.lib = PatchLib.make(store.ring, store.bankMap, store.profile); // refresh names
      invalidate();
      lsSet(LS_BANKMAP, { profileKey: store.profile.key, bankMap: store.bankMap });
      return J({ ok: true, count: Object.keys(snaptone).length, ir_count: Object.keys(ir).length, snaptones: snaptone, irs: ir });
    } catch (e) { return J({ ok: false, error: e.message }); }
  }

  // --- device scan (rebuild the snapshot from the pedal over WebMIDI) ---------
  let scanState = { running: false, done: 0, total: 0, current: "", errors: 0, written: 0, error: null };
  async function startScan() {
    if (scanState.running) return J({ ok: true });
    if (!(await ensureConnected())) return J({ ok: false, error: "no device connected" });
    scanState = { running: true, done: 0, total: 100, current: "", errors: 0, written: 0, error: null };
    const cache = lsGet(LS_SCAN, null);
    const resumable = cache && cache.profileKey === store.profile.key ? cache.slots || {} : {};
    (async () => {
      try {
        const names = await Bridge.readNames();
        scanState.total = names.length || 100;
        for (const { slot, name } of names) {
          scanState.current = `#${slot} ${name}`;
          const cached = resumable[slot];
          if (cached && Date.now() - cached.ts < RESUME_WINDOW_MS) {
            // already read this slot moments ago (e.g. an interrupted scan we're
            // resuming) — reuse it instead of hitting the pedal again.
            try { store.bytes.set(slot, b64ToBytes(cached.b64)); store.names.set(slot, cached.name || name); scanState.written++; }
            catch { scanState.errors++; }
          } else {
            try {
              const prst = await Bridge.readSlotPrst(slot);
              store.bytes.set(slot, prst); store.names.set(slot, PRST.readName(prst) || name);
              scanState.written++;
              persistSlot(slot);
            } catch { scanState.errors++; }
          }
          scanState.done++;
        }
        invalidate();
      } catch (e) { scanState.error = e.message; }
      finally { scanState.running = false; }
    })();
    return J({ ok: true });
  }
  // true once every slot has real device data cached locally (not just the blank
  // bundle) — used to decide whether a reload can skip the "Please connect USB and
  // scan" empty state entirely.
  function hasFullScanCache() {
    const cache = lsGet(LS_SCAN, null);
    return !!(cache && store && cache.profileKey === store.profile.key && cache.slots && Object.keys(cache.slots).length >= 100);
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

  // Push exact bytes into the cache (used by the Explorer after a live commit/restore
  // so the row reflects them — incl. a rename — without a slow, name-losing re-read).
  function setSlotBytes(slot, prst) {
    if (!store) return;
    const u = prst instanceof Uint8Array ? prst : Uint8Array.from(prst);
    store.bytes.set(slot, u); store.names.set(slot, PRST.readName(u)); invalidate();
    persistSlot(slot);
  }

  // Every slot's current .prst bytes (fresh copies), keyed by slot. The Explorer's
  // preset-reorder flow needs the raw snapshot to compute + write the minimal diff.
  function getAllSlotBytes() {
    if (!store) return null;
    const out = {};
    for (const [slot, u] of store.bytes) out[slot] = Uint8Array.from(u);
    return out;
  }

  root.__staticApi = { handle, ensureLoaded, setSlotBytes, getAllSlotBytes, hasFullScanCache }; // for tests + Explorer cache sync
  console.log("[static_api] active — /api/device/* served client-side");
})(typeof self !== "undefined" ? self : this);
