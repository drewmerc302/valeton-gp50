# GP-50 block (signal-chain) order — reverse-engineered 2026-07-16

Cracked how the `.prst` encodes the effect-block CHAIN ORDER, via read-diff on live
hardware (no export needed — device body reads over WebMIDI). Method: read slot 47
"Bass Drive" as a baseline (A), reorder ONE block on the hardware and save, read
again (C), diff.

## The finding

Chain order is a dedicated body record — a **sibling of the bypass/models/params
records**, previously undecoded:

```
tag  marker         len   payload
0x01 01 30 04 00    4     bypass bitmask (u32)
0x02 02 30 0a 00    10    CHAIN ORDER  ← this
0x03 03 30 28 00    40    model records (10 × 4 bytes)
0x04 04 30 40 01    320   param floats (80 × f32)
```

- **REC_ORDER marker = `02 30 0A 00`**, 10-byte payload. Find it structurally by the
  marker (don't hardcode an offset; it sat at 0xA0 in this preset but the TLV layout
  can shift).
- Payload = a **permutation of 0..9**. `order[position]` = the **block index** (into
  the fixed-order model records) that occupies that chain position. Array index =
  signal-chain position.
- The model records themselves stay in **fixed storage order** and do NOT move when
  you reorder — only this array + the CRC change.

## Evidence (slot 47, "Bass Drive")

Single move on the hardware: RVB dragged from last → first. Diff A vs C = **11 bytes**:
the CRC at 0x14, and the 10 order bytes.

```
A (RVB last):  [0, 1, 2, 9, 3, 4, 5, 6, 7, 8]
C (RVB first): [8, 0, 1, 2, 9, 3, 4, 5, 6, 7]   # block 8 rotated to front, rest shift +1
```

Nothing else changed. Reconstructing A's order onto C's bytes + `refixCrc` reproduces
A **byte-for-byte** (CRC included) — so a reorder is: rewrite the 10 order bytes,
refix the CRC (0x14), write via the existing cmd-0x1D path. Verified byte-level; the
0x1D write path is already hardware-validated (29/29 ACKs, byte-exact readback).

## Category → block, and the movable/immutable split

Each model record's category byte (`r[3]`, the fxid high byte) classifies the block:

| cat  | block   | class      |
|------|---------|------------|
| 0x00 | NR, PRE | **movable** (both share cat 0x00) |
| 0x04 | MOD     | **movable** |
| 0x0b | DLY     | **movable** |
| 0x0c | RVB     | **movable** |
| 0x01 | EQ      | immutable core |
| 0x03 | DST     | immutable core |
| 0x07 | AMP     | immutable core |
| 0x0a | CAB     | immutable core |
| 0x0f | N->S    | immutable core |

## The constraint model (matches the Valeton Mobile app)

- The 5 core blocks **[DST · N→S · AMP · CAB · EQ]** stay contiguous, fixed internal
  order — an atomic run in the chain. (In A they occupy chain positions 2–6 as block
  indices 2,9,3,4,5.)
- The 5 movables **[NR, PRE, MOD, DLY, RVB]** distribute before/after that run, in any
  order. Arrangement space = 5! orderings × 6 insert points for the core = **720**.
- A movable can never land *between* two core blocks.

## Open / to confirm next

- **Multi-block + split** case: confirm a movable placed AFTER the core (and a split,
  some movables before + some after) is still just this one array (expected — it's a
  full permutation, so it already covers every arrangement). Grab one split capture to
  be sure.
- **Live write of a constructed reorder** on hardware (not just replaying a captured
  blob) — pending; construction is proven byte-identical to a real device save, so
  this is expected to pass.
- Our decoder is currently **order-blind** (`patchlib` assigns block names by fixed
  record position and ignores REC_ORDER) — so the Explorer currently MISREADS any
  reordered preset's chain. Decode should read REC_ORDER to show the true chain.
