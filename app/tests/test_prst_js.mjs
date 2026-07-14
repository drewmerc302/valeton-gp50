/*
 * Byte-for-byte parity check: app/static/prst.js vs the Python oracle
 * (patch/prst_format.py + patch/convert.py) over the in-repo preset corpus.
 *
 *   node app/tests/test_prst_js.mjs            # auto-runs prst_oracle.py
 *   node app/tests/test_prst_js.mjs foo.json   # verify a pre-built manifest
 *
 * Auto mode shells out to the repo venv's python to build the manifest, so a
 * clean checkout can run it with no manual step.
 */
import { readFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../..");
const PRST = require(resolve(here, "../static/prst.js"));

function loadCorpus() {
  const arg = process.argv[2];
  if (arg) return JSON.parse(readFileSync(arg, "utf8"));
  const py = [".venv-app/bin/python", ".venv-midi/bin/python", "python3"]
    .map((p) => (p.includes("/") ? resolve(repoRoot, p) : p))
    .find((p) => !p.includes("/") || existsSync(p)) || "python3";
  const oracle = resolve(here, "prst_oracle.py");
  const json = execFileSync(py, [oracle], { cwd: repoRoot, maxBuffer: 64 * 1024 * 1024 });
  return JSON.parse(json.toString("utf8"));
}
const corpus = loadCorpus();

const b64 = (u8) => Buffer.from(u8).toString("base64");
const fromB64 = (s) => new Uint8Array(Buffer.from(s, "base64"));
const eqBytes = (a, z) => a.length === z.length && a.every((v, i) => v === z[i]);

let pass = 0, fail = 0;
const fails = [];
const check = (path, label, ok, detail) => {
  if (ok) { pass++; return; }
  fail++; fails.push(`${path} :: ${label}${detail ? " — " + detail : ""}`);
};

for (const rec of corpus) {
  if (rec.error) { check(rec.path, "python-detect", false, rec.error); continue; }
  const prst = fromB64(rec.prstB64);

  // detect
  let dev;
  try { dev = PRST.detect(prst); } catch (e) { check(rec.path, "detect", false, e.message); continue; }
  check(rec.path, "detect.key", dev.key === rec.srcKey, `${dev.key} != ${rec.srcKey}`);

  // name
  check(rec.path, "readName", PRST.readName(prst) === rec.name, `"${PRST.readName(prst)}" != "${rec.name}"`);

  // model records
  const models = PRST.modelRecords(prst);
  check(rec.path, "modelRecords", JSON.stringify(models) === JSON.stringify(rec.models),
    JSON.stringify(models));

  // bypass mask
  const dvv = new DataView(prst.buffer, prst.byteOffset, prst.byteLength);
  const bo = PRST.bypassOffset(prst);
  const bypass = bo >= 0 ? dvv.getUint32(bo, true) : 0;
  check(rec.path, "bypassMask", bypass === rec.bypass, `${bypass} != ${rec.bypass}`);

  // params (float32 x 80)
  const po = PRST.paramsOffset(prst);
  const params = [];
  if (po >= 0) for (let k = 0; k < PRST.N_PARAM_SLOTS; k++) params.push(dvv.getFloat32(po + k * 4, true));
  const pOk = params.length === rec.params.length &&
    params.every((v, i) => Object.is(v, rec.params[i]) || Math.abs(v - rec.params[i]) < 1e-12);
  check(rec.path, "params", pOk);

  // fs offset + vol/bpm + fs masks
  check(rec.path, "fsOffset", PRST.fsOffset(prst) === rec.fsOff, `${PRST.fsOffset(prst)} != ${rec.fsOff}`);
  const vb = PRST.readVolBpm(prst);
  check(rec.path, "volBpm", vb[0] === rec.volBpm[0] && vb[1] === rec.volBpm[1], JSON.stringify(vb));
  const fs = PRST.readFootswitches(prst);
  check(rec.path, "footswitches", fs[0] === rec.fs[0] && fs[1] === rec.fs[1], JSON.stringify(fs));

  // problems
  const probs = PRST.checkConvertible(prst, rec.target)
    .map((p) => [p.blockIndex, p.fxid, p.model]);
  check(rec.path, "checkConvertible", JSON.stringify(probs) === JSON.stringify(rec.problems),
    JSON.stringify(probs));

  // conversion (byte-for-byte)
  if (rec.convB64) {
    let conv;
    try { conv = PRST.convert(prst, rec.target); }
    catch (e) { check(rec.path, "convert", false, "threw: " + e.message); continue; }
    check(rec.path, "convert.bytes", b64(conv) === rec.convB64,
      eqBytes(conv, fromB64(rec.convB64)) ? "" : `len ${conv.length} vs ${fromB64(rec.convB64).length}`);
  } else {
    // python refused -> JS must refuse too
    let threw = false;
    try { PRST.convert(prst, rec.target); } catch { threw = true; }
    check(rec.path, "convert.refuse", threw, "JS did not refuse a lossy conversion");
    if (rec.convForceB64) {
      const forced = PRST.convert(prst, rec.target, { force: true });
      check(rec.path, "convert.force", b64(forced) === rec.convForceB64);
    }
  }
}

console.log(`\ncorpus: ${corpus.length} presets`);
console.log(`checks: ${pass + fail}   pass: ${pass}   fail: ${fail}`);
if (fail) {
  console.log("\nFAILURES:");
  for (const f of fails.slice(0, 40)) console.log("  " + f);
  if (fails.length > 40) console.log(`  … +${fails.length - 40} more`);
  process.exit(1);
}
console.log("ALL PASS — prst.js is byte-for-byte with the Python oracle.");
