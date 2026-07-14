/*
 * Byte-for-byte parity check: prst.js applyEdits vs Python
 * (app/patchlib.apply_edits_bytes) over the in-repo corpus x several edit specs.
 *
 *   node app/tests/test_edits_js.mjs           # auto-runs edits_oracle.py
 *   node app/tests/test_edits_js.mjs foo.json  # verify a pre-built manifest
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
  const py = [".venv-app/bin/python", ".venv-midi/bin/python"]
    .map((p) => resolve(repoRoot, p))
    .find((p) => existsSync(p)) || "python3";
  const oracle = resolve(here, "edits_oracle.py");
  return JSON.parse(execFileSync(py, [oracle], { cwd: repoRoot, maxBuffer: 64 * 1024 * 1024 }).toString());
}

const corpus = loadCorpus();
const fromB64 = (s) => new Uint8Array(Buffer.from(s, "base64"));
const b64 = (u) => Buffer.from(u).toString("base64");

let pass = 0, fail = 0;
const fails = [];
const check = (label, ok, detail) => { if (ok) { pass++; return; } fail++; fails.push(`${label}${detail ? " — " + detail : ""}`); };

for (const rec of corpus) {
  const base = fromB64(rec.baseB64);
  const tag = `${rec.path}[${rec.label}]`;
  let edited;
  try { edited = PRST.applyEdits(base, rec.edits); }
  catch (e) { check(tag, false, "threw: " + e.message); continue; }
  check(tag, b64(edited) === rec.editedB64, `len ${edited.length}`);
  // input must be untouched
  check(`${tag} no-mutate`, b64(base) === rec.baseB64);
}

console.log(`\nvectors: ${corpus.length}`);
console.log(`checks: ${pass + fail}   pass: ${pass}   fail: ${fail}`);
if (fail) {
  console.log("\nFAILURES:");
  for (const f of fails.slice(0, 40)) console.log("  " + f);
  process.exit(1);
}
console.log("ALL PASS — prst.js applyEdits is byte-for-byte with patchlib.apply_edits_bytes.");
