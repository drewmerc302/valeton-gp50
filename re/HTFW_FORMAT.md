# HTFW firmware container (GP-5 / GP-50 / GP-150) — cracked 2026-07-22

Valeton/Hotone ship device firmware as a single `.bin` with an `HTFW` magic. The
container is fully decoded and validated byte-exactly against three files:

| file | model | size | regions |
|---|---|---|---|
| `GP-5 Firmware V1.0.6.bin`   | `GP-5`   | 2,094,404 | 5 (`c g f b e`) |
| `GP-50 Firmware V1.0.5.bin`  | `GP-50`  | 2,261,024 | 5 (`c g f b e`) |
| `GP-150 Firmware V1.0.5.bin` | `GP-150` | 8,371,564 | 7 (`b c d e f g h`) |

Firmware is downloadable from valeton.net without owning the device.

## Header

```
0x00  char[4]  "HTFW"
0x04  u32      checksum//unknown (differs per build)
0x08  u32      total file size            <- exact match on all 3 files
0x0C  char[16] model string, NUL-padded   ("GP-5", "GP-50", "GP-150")
0x1C  u16      0x0156 (constant on all 3)
0x1F  u8       firmware MINOR version     <- 6 for GP-5 V1.0.6, 5 for the V1.0.5s.
                                             Tracks the version, NOT the device.
0x20  u32      0x00050000 (GP-5/GP-50), 0x00070000 (GP-150)
0x24  u32      payload total size
0x38  ...      TOC records, 16 bytes each
      ...      terminated by FF FF FF FF
```

## TOC record (16 bytes)

```
+0x00 u16  checksum of the region
+0x02 u8   0x00
+0x03 u8   region id, ASCII ('b','c','d','e','f','g','h')
+0x04 u32  load address
+0x08 u32  offset  (relative to payload_base)
+0x0C u32  length
```

`payload_base = filesize - payload_total` (0x88 for GP-5/GP-50, 0xA8 for GP-150).
Regions are contiguous — each `offset` equals the previous `offset+length`, and the
cumulative end equals `payload_total` exactly on all three files.

Note the first region starts at `payload_base`, so it swallows the `FF FF FF FF`
sentinel and the `V1xx` version string that follow the TOC — same
"sentinel then data" convention the `.prst` format uses.

## Region map

GP-5 and GP-50 use an **identical layout — same ids, same load addresses**:

| id | load addr | role |
|---|---|---|
| `c` | 0x200000 | ARM Thumb. HAL/RTOS — `..\Source\driver\spi.c`, `uart.c`, SIGABRT/heap asserts |
| `g` | 0x240000 | ARM Thumb, no strings (DSP/math) |
| `f` | 0x280000 | cab/IR data — cab names in plaintext ("TWD CP 1x8", "Dark VIT 1x12") |
| `b` | 0x000000 | **main application** (see below) |
| `e` | 0x190000 | factory presets — names in plaintext ("GreatPedal", "Neo Soul", "Power Lead"). 0x2D000 on BOTH devices |

GP-150 has its own 7-region map (`b`@0x38000 5.1MB, `c`@0x740000, `d`@0x800000,
`e`@0x9c0000, `f`@0xa80000, `g`@0 (H=7.99, compressed), `h`@0).

## Region `b` — the application core, and why it is a dead end for RE

Region `b` holds the code we actually care about. Source paths recovered from its
assert strings (GP-50 build; the GP-5 V1.0.6 build strips most of them):

```
../UserSources/PC_BT_Comm/ProtocolAnalysis.c     <- the protocol command parser
../UserSources/Components/MIDI/MidiTask.c
../UserSources/Components/MIDI/MidiWinGlobalCallback.c
../UserSources/UserData/UserData.c , Data.c
../UserSources/GUI/...  , ../bt_audio_app_src/main.c , att_server.c
```

It also contains the CRC-8/0x07 table (GP-5 @0xbd868, GP-50 @0xbc66c).

**Architecture: MVsilicon B1 SDK (Mountain View Silicon)** — a proprietary BT-audio
SoC core, NOT ARM (0.00 `bx lr`/KB vs ~3/KB in regions `c`/`g`). BLE stack `8.7.1`
on both devices (GP-50 built Nov 21 2025, GP-5 Jun 26 2025).

Ghidra 12.1.1 ships **no processor module** for it, and no public RE of the ISA was
found. A SLEIGH spec would be a multi-week project.

## GP-5 vs GP-50 similarity — measured, and NOT sufficient for the write gate

`re/probes/fw_similarity.py` compares the two `b` regions:

- 46.4% of GP-5's app core is byte-identical to GP-50's (2068 runs >= 48B).
- Protocol neighbourhood around the CRC table: ~52% identical.
- **But** the identical run *containing* the CRC-8 table is only **305 bytes**, and it
  starts exactly at the table: it is the 256-byte table plus adjacent string data
  ("Uart DMA Rx", a source path). The code immediately *before* the table differs
  completely. The shared bytes there are data, not the handler.

46% is the expected overlap for two builds of the same vendor SDK. It does not isolate
and cannot speak to the `0x1D` bulk-write handler.

**Conclusion: firmware RE does NOT justify flipping `WRITE_VERIFIED["gp5"]`.** The gate
stays closed. See `re/DEVICE_WRITE.md` — GP-50's `0x1D` was originally cracked by live
MIDI capture precisely *because* static analysis of the Dart AOT app failed. Capture
remains the only route that has ever worked here.

## Caveat on opcode searching

Searching a 1.2MB region for 2-byte markers (`11 4F`, `11 43`, ...) is **statistical
noise** — a random 2-byte pattern occurs ~19x per 1.2MB by chance. Only the 256-byte
CRC table match is meaningful. `find_proto.py` prints both; read it with that in mind.

## Scripts (`re/probes/`)

- `htfw_parse.py <fw.bin>...` — parse+validate the header and TOC.
- `htfw_extract.py <outdir> <fw.bin>...` — split regions to disk, fingerprint each
  (entropy, Cortex-M vector-table heuristic, strings).
- `isa_fingerprint.py <regiondir>` — count ARM Thumb / A32 / MIPS encodings per region.
- `find_proto.py <regiondir>` — locate the CRC-8/0x07 table and protocol opcodes.
- `fw_similarity.py <regionA.bin> <regionB.bin>` — common-run analysis between two
  builds, anchored on the CRC table.

Firmware `.bin`s are NOT committed (2-8MB each); re-download from valeton.net.
