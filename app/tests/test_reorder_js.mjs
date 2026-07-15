/*
 * Property tests for the preset-reorder planner (explorer.js planReorder).
 *
 * planReorder is pure and lives inside the Explorer IIFE (which can't be required
 * in node — it touches the DOM at load). This mirrors the exact algorithm and
 * asserts the invariants the device write path relies on. The live end-to-end test
 * additionally checks window.__reorderTest.planReorder against this reference on a
 * real device snapshot, so drift between the two is caught.
 *
 *   node app/tests/test_reorder_js.mjs
 */

// --- reference: byte-identical to explorer.js ------------------------------
function eqBytes(a, z) { if (!a || !z || a.length !== z.length) return false; for (let i = 0; i < a.length; i++) if (a[i] !== z[i]) return false; return true; }
function planReorder(snapBytes, order) {
  const writes = [];
  for (let dest = 0; dest < order.length; dest++) {
    const bytes = snapBytes[order[dest]];
    if (!eqBytes(bytes, snapBytes[dest])) writes.push({ slot: dest, from: order[dest], bytes });
  }
  return writes;
}

// --- helpers ----------------------------------------------------------------
// synthetic 100-slot snapshot: each slot's "bytes" is a unique 1-byte array,
// except a few deliberate duplicates to exercise the byte-equality short-circuit.
function makeSnap(dupes = {}) {
  const snap = {};
  for (let i = 0; i < 100; i++) snap[i] = Uint8Array.of(i);
  for (const [slot, val] of Object.entries(dupes)) snap[slot] = Uint8Array.of(val);
  return snap;
}
// apply a plan to a fresh device state (start = identity), return final slot->val.
function applyPlan(snap, order) {
  const dev = {}; for (let i = 0; i < 100; i++) dev[i] = snap[i]; // pre-reorder device
  for (const w of planReorder(snap, order)) dev[w.slot] = w.bytes;  // writes from snapshot
  return dev;
}

let pass = 0, fail = 0; const fails = [];
const ok = (label, cond, detail) => { if (cond) pass++; else { fail++; fails.push(`${label}${detail ? " — " + detail : ""}`); } };

// 1. identity order → zero writes
{
  const snap = makeSnap();
  const order = [...Array(100).keys()];
  ok("identity.noWrites", planReorder(snap, order).length === 0);
}

// 2. adjacent swap → exactly 2 writes, correct result
{
  const snap = makeSnap();
  const order = [...Array(100).keys()]; [order[3], order[4]] = [order[4], order[3]];
  const w = planReorder(snap, order);
  ok("swap.count", w.length === 2, `got ${w.length}`);
  const dev = applyPlan(snap, order);
  ok("swap.result3", dev[3][0] === 4);
  ok("swap.result4", dev[4][0] === 3);
}

// 3. far swap (3 ↔ 80) → 2 writes
{
  const snap = makeSnap();
  const order = [...Array(100).keys()]; [order[3], order[80]] = [order[80], order[3]];
  ok("farSwap.count", planReorder(snap, order).length === 2);
}

// 4. insert-move (pull slot 3 → position 7, shift 4..7 up) → span = 5 writes
{
  const snap = makeSnap();
  const order = [...Array(100).keys()];
  order.splice(7, 0, order.splice(3, 1)[0]); // move item at 3 to index 7
  const w = planReorder(snap, order);
  ok("insert.count", w.length === 5, `got ${w.length} (slots ${w.map((x) => x.slot)})`);
  // every displaced destination gets the ORIGINAL bytes of its assigned origin
  const dev = applyPlan(snap, order);
  ok("insert.correct", dev[7][0] === 3 && dev[3][0] === 4 && dev[6][0] === 7);
}

// 5. full reverse → 100 writes, and result is exactly reversed
{
  const snap = makeSnap();
  const order = [...Array(100).keys()].reverse();
  ok("reverse.count", planReorder(snap, order).length === 100);
  const dev = applyPlan(snap, order);
  let good = true; for (let i = 0; i < 100; i++) if (dev[i][0] !== 99 - i) good = false;
  ok("reverse.correct", good);
}

// 6. writes == displaced count (minimality) for a random permutation
{
  const snap = makeSnap();
  const order = [...Array(100).keys()];
  // deterministic shuffle (no Math.random): rotate a window
  const seg = order.splice(20, 30); order.splice(50, 0, ...seg.reverse());
  const displaced = order.reduce((n, from, dest) => n + (from !== dest ? 1 : 0), 0);
  ok("minimal.eqDisplaced", planReorder(snap, order).length === displaced, `writes ${planReorder(snap, order).length} vs displaced ${displaced}`);
}

// 7. byte-identical presets swapping positions → NO write (blanks case)
{
  const snap = makeSnap({ 90: 200, 91: 200 }); // slots 90,91 identical
  const order = [...Array(100).keys()]; [order[90], order[91]] = [order[91], order[90]];
  ok("dupSwap.noWrite", planReorder(snap, order).length === 0, "identical presets should not write");
}

// 8. order-independence: writing from the immutable snapshot, apply in reverse
{
  const snap = makeSnap();
  const order = [...Array(100).keys()];
  order.splice(10, 0, order.splice(60, 1)[0]); // a spanning move
  const plan = planReorder(snap, order);
  const devF = {}; for (let i = 0; i < 100; i++) devF[i] = snap[i];
  for (const w of plan) devF[w.slot] = w.bytes;               // forward
  const devR = {}; for (let i = 0; i < 100; i++) devR[i] = snap[i];
  for (const w of [...plan].reverse()) devR[w.slot] = w.bytes; // reverse
  let same = true; for (let i = 0; i < 100; i++) if (devF[i][0] !== devR[i][0]) same = false;
  ok("orderIndependent", same, "result must not depend on write order");
}

console.log(`\nreorder planner: checks ${pass + fail}   pass ${pass}   fail ${fail}`);
if (fail) { console.log("FAILURES:"); fails.forEach((f) => console.log("  " + f)); process.exit(1); }
console.log("ALL PASS — planReorder is minimal-write, correct, and order-independent.");
