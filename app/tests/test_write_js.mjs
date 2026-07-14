/*
 * Byte-for-byte parity check: app/static/webmidi_write.js vs the Python oracle
 * (patch/device_write.py) over the in-repo corpus x several slots.
 *
 *   node app/tests/test_write_js.mjs          # auto-runs write_oracle.py
 *   node app/tests/test_write_js.mjs foo.json # verify a pre-built manifest
 */
import { readFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../..");
const WW = require(resolve(here, "../static/webmidi_write.js"));

function loadCorpus() {
  const arg = process.argv[2];
  if (arg) return JSON.parse(readFileSync(arg, "utf8"));
  const py = [".venv-app/bin/python", ".venv-midi/bin/python"]
    .map((p) => resolve(repoRoot, p))
    .find((p) => existsSync(p)) || "python3";
  const oracle = resolve(here, "write_oracle.py");
  return JSON.parse(execFileSync(py, [oracle], { cwd: repoRoot, maxBuffer: 64 * 1024 * 1024 }).toString());
}

const corpus = loadCorpus();
const fromB64 = (s) => new Uint8Array(Buffer.from(s, "base64"));
const hexwire = (p) => p.map((b) => b.toString(16).padStart(2, "0")).join("");

let pass = 0, fail = 0;
const fails = [];
const check = (label, ok, detail) => { if (ok) { pass++; return; } fail++; fails.push(`${label}${detail ? " — " + detail : ""}`); };

for (const rec of corpus) {
  const prst = fromB64(rec.prstB64);
  const tag = `${rec.path}@slot${rec.slot}`;
  let stream;
  try { stream = WW.buildPatchWriteStream(prst, rec.slot); }
  catch (e) { check(`${tag} build`, false, "threw: " + e.message); continue; }

  check(`${tag} nPackets`, stream.length === rec.nPackets, `${stream.length} != ${rec.nPackets}`);
  let allMatch = stream.length === rec.packets.length;
  for (let i = 0; i < Math.min(stream.length, rec.packets.length); i++) {
    if (hexwire(stream[i]) !== rec.packets[i]) { allMatch = false; break; }
  }
  check(`${tag} packets`, allMatch);

  const [ok, reason] = WW.validateStream(stream);
  check(`${tag} validate`, ok === rec.validate[0], `js=${ok} py=${rec.validate[0]} (${reason})`);
}

// negative checks: validateStream must reject tampering
{
  const prst = fromB64(corpus[0].prstB64);
  const good = WW.buildPatchWriteStream(prst, 0);
  const flipCrc = good.map((p) => p.slice());
  flipCrc[0][1] ^= 0xff; // corrupt a nibble of packet 0's crc
  check("negative: bad CRC rejected", WW.validateStream(flipCrc)[0] === false);
  const dropLast = good.slice(0, -1);
  check("negative: short stream rejected", WW.validateStream(dropLast)[0] === false);
}

console.log(`\nvectors: ${corpus.length}`);
console.log(`checks: ${pass + fail}   pass: ${pass}   fail: ${fail}`);
if (fail) {
  console.log("\nFAILURES:");
  for (const f of fails.slice(0, 40)) console.log("  " + f);
  process.exit(1);
}
console.log("ALL PASS — webmidi_write.js builds byte-for-byte with the Python oracle.");
