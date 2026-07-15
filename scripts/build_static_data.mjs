/*
 * Bundle the data a zero-backend Explorer needs into app/static/data/:
 *   fxid_ring.json / fxid_ring_gp5.json  — model catalogs (copied from patch/)
 *   bank_map.json                        — SnapTone/User-IR device names (if present)
 *   presets.json                         — a preset snapshot {device, presets:[{slot,name,b64}]}
 *
 * The snapshot is a browse seed; a live "Scan from device" rebuilds it over
 * WebMIDI. Source dir mirrors the backend: device_scan/ if populated, else
 * presetExports/.
 *
 *   node scripts/build_static_data.mjs
 */
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync, copyFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");
const PRST = (await import(resolve(repo, "app/static/prst.js"))).default
  || require(resolve(repo, "app/static/prst.js"));

// --live bundles YOUR pedal (device_scan/ + your SnapTone/IR names). Default is
// the shippable FACTORY set: presetExports/ + an empty bank_map (no custom names).
const LIVE = process.argv.includes("--live");

const outDir = resolve(repo, "app/static/data");
mkdirSync(outDir, { recursive: true });

// model catalogs (always) + bank_map (only in --live; factory ships empty)
for (const f of ["fxid_ring.json", "fxid_ring_gp5.json"]) {
  const src = resolve(repo, "patch", f);
  if (existsSync(src)) copyFileSync(src, resolve(outDir, f));
  else console.warn(`(skip missing ${f})`);
}
const bankSrc = resolve(repo, "patch", "bank_map.json");
if (LIVE && existsSync(bankSrc)) copyFileSync(bankSrc, resolve(outDir, "bank_map.json"));
else writeFileSync(resolve(outDir, "bank_map.json"), JSON.stringify({ source: "factory (no custom names)", snaptone: {}, ir: {} }));

// preset snapshot
function sourceDir() {
  if (LIVE) {
    const scan = resolve(repo, "device_scan");
    if (existsSync(scan) && readdirSync(scan).some((f) => f.endsWith(".prst"))) return scan;
  }
  return resolve(repo, "presetExports");
}
const dir = sourceDir();
const files = readdirSync(dir).filter((f) => f.endsWith(".prst")).sort();
let deviceKey = "gp50";
const presets = files.map((f) => {
  const bytes = new Uint8Array(readFileSync(resolve(dir, f)));
  try { deviceKey = PRST.detect(bytes).key; } catch { /* keep default */ }
  const m = f.match(/^(\d+)-/);
  return {
    slot: m ? Number(m[1]) : -1,
    name: PRST.readName(bytes) || f.replace(/^\d+-/, "").replace(/\.prst$/, ""),
    b64: Buffer.from(bytes).toString("base64"),
  };
});

writeFileSync(resolve(outDir, "presets.json"), JSON.stringify({
  device: deviceKey,
  source: dir.endsWith("device_scan") ? "device_scan" : "presetExports",
  count: presets.length,
  presets,
}));
console.log(`wrote app/static/data/presets.json (${presets.length} presets, device ${deviceKey}, ${LIVE ? "LIVE snapshot" : "factory"}) + catalogs`);
if (!LIVE) console.log("  factory bundle: presetExports/ + empty bank_map (no custom names). Use --live to bundle your pedal.");
