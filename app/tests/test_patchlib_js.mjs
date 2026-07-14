/*
 * Field parity check: patchlib.js (client-side decode) vs the live backend
 * /api/device/{inventory,facets,models}. Decodes the same .prst source the app
 * uses (device_scan/ or presetExports/) with the same ring + bank_map.
 *
 *   (backend running on :8756)  node app/tests/test_patchlib_js.mjs [baseURL]
 *
 * Structural fields compared exactly; param `value` tolerant to 2-dp float
 * rounding (Python round() vs JS), which is display-only.
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, resolve, basename } from "node:path";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../..");
const PRST = require(resolve(here, "../static/prst.js"));
const PatchLib = require(resolve(here, "../static/patchlib.js"));

const base = process.argv[2] || "http://127.0.0.1:8756";

function sourceDir() {
  const scan = resolve(repoRoot, "device_scan");
  if (existsSync(scan) && readdirSync(scan).some((f) => f.endsWith(".prst"))) return scan;
  return resolve(repoRoot, "presetExports");
}
const slotOf = (f) => { const m = f.match(/^(\d+)-/); return m ? Number(m[1]) : -1; };
const fallbackName = (f) => f.replace(/^\d+-/, "").replace(/\.prst$/, "");

function loadPresets() {
  const dir = sourceDir();
  return readdirSync(dir).filter((f) => f.endsWith(".prst")).sort().map((f) => ({
    slot: slotOf(f), name: fallbackName(f),
    bytes: new Uint8Array(readFileSync(resolve(dir, f))),
  }));
}

let pass = 0, fail = 0;
const fails = [];
const check = (label, ok, detail) => { if (ok) { pass++; return; } fail++; if (fails.length < 60) fails.push(`${label}${detail ? " — " + detail : ""}`); };

function cmpParams(tag, a, b) {
  check(`${tag} paramCount`, a.length === b.length, `${a.length} vs ${b.length}`);
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    const x = a[i], y = b[i];
    for (const k of ["name", "algId", "toggle", "unit", "min", "max", "step"]) {
      check(`${tag} p${i}.${k}`, x[k] === y[k], `${JSON.stringify(x[k])} vs ${JSON.stringify(y[k])}`);
    }
    check(`${tag} p${i}.value`, Math.abs((x.value ?? 0) - (y.value ?? 0)) <= 0.011, `${x.value} vs ${y.value}`);
  }
}

const ring = JSON.parse(readFileSync(resolve(repoRoot, "patch/fxid_ring.json"), "utf8"));
const bankMapPath = resolve(repoRoot, "patch/bank_map.json");
const bankMap = existsSync(bankMapPath) ? JSON.parse(readFileSync(bankMapPath, "utf8")) : {};

const lib = PatchLib.make(ring, bankMap, PRST.GP50);
const presets = loadPresets();
const inv = lib.inventory(presets);
const jsBySlot = Object.fromEntries(inv.patches.map((p) => [p.slot, p]));

// --- inventory ---
const apiInv = await (await fetch(`${base}/api/device/inventory`)).json();
check("patch count", apiInv.patches.length === inv.patches.length, `api ${apiInv.patches.length} js ${inv.patches.length}`);
for (const ap of apiInv.patches) {
  const jp = jsBySlot[ap.slot];
  const tag = `#${ap.slot}`;
  if (!jp) { check(`${tag} present`, false); continue; }
  for (const k of ["name", "empty", "uses_snaptone", "snaptone_slot", "ir_slot", "amp_slot", "ir_name", "amp_name", "snaptone_name"]) {
    check(`${tag}.${k}`, JSON.stringify(jp[k]) === JSON.stringify(ap[k]), `${JSON.stringify(jp[k])} vs ${JSON.stringify(ap[k])}`);
  }
  check(`${tag}.settings`, JSON.stringify(jp.settings) === JSON.stringify(ap.settings), `${JSON.stringify(jp.settings)} vs ${JSON.stringify(ap.settings)}`);
  check(`${tag} blockCount`, jp.blocks.length === ap.blocks.length);
  for (let i = 0; i < Math.min(jp.blocks.length, ap.blocks.length); i++) {
    const jb = jp.blocks[i], ab = ap.blocks[i];
    for (const k of ["block", "active", "type", "model", "official", "index", "fxid", "label", "label_official"]) {
      check(`${tag} b${i}.${k}`, JSON.stringify(jb[k]) === JSON.stringify(ab[k]), `${JSON.stringify(jb[k])} vs ${JSON.stringify(ab[k])}`);
    }
    cmpParams(`${tag} b${i}`, jb.params, ab.params);
  }
}

// --- snaptones + irs (Captures page) ---
check("snaptones", JSON.stringify(inv.snaptones) === JSON.stringify(apiInv.snaptones), "snaptone list differs");
check("irs", JSON.stringify(inv.irs) === JSON.stringify(apiInv.irs), "ir list differs");

// --- facets ---
const apiFac = await (await fetch(`${base}/api/device/facets`)).json();
const jsFac = lib.facets(inv.patches);
check("facets", JSON.stringify(jsFac) === JSON.stringify(apiFac), "facet structure differs");

// --- models per block ---
for (const block of PatchLib.BLOCK_NAMES) {
  const apiM = await (await fetch(`${base}/api/device/models/${encodeURIComponent(block)}`)).json();
  const jsM = lib.modelsForBlock(block, inv.snaptones);
  check(`models[${block}] count`, jsM.length === (apiM.models || []).length, `js ${jsM.length} api ${(apiM.models || []).length}`);
  for (let i = 0; i < Math.min(jsM.length, (apiM.models || []).length); i++) {
    const jm = jsM[i], am = apiM.models[i];
    for (const k of ["fxid", "name", "official", "type", "label", "label_official"]) {
      check(`models[${block}] ${i}.${k}`, JSON.stringify(jm[k]) === JSON.stringify(am[k]), `${JSON.stringify(jm[k])} vs ${JSON.stringify(am[k])}`);
    }
  }
}

console.log(`\npresets: ${inv.patches.length}`);
console.log(`checks: ${pass + fail}   pass: ${pass}   fail: ${fail}`);
if (fail) {
  console.log("\nFAILURES:");
  for (const f of fails) console.log("  " + f);
  process.exit(1);
}
console.log("ALL PASS — patchlib.js decode matches the backend /api field-for-field.");
