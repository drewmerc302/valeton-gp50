# GP-50 write-packet protocol (reverse-engineered)

Recovered from `5868USB.dylib::getMidiMessage` (Ghidra) + verified against a MIDI
Monitor spy capture of two SnapTone imports (**298/298 packets match**).

## Packet format (host → device)

Every host→device SysEx is built from a small **pre-nibble buffer `BUF`**, then each
byte is split into two 4-bit nibbles (hi first) and wrapped in `F0 … F7`:

```
BUF (bytes, before nibble-encoding):
  [0]  CHECKSUM   (CRC-8, see below)
  [1]  command    (0x92 for SnapTone data-write blocks; other ops use other values)
  [2]  block index  (0,1,2,… running within the transfer)
  [3]  length     (# of payload data bytes; 0x13 = 19 for full blocks)
  [4…] payload    ([3] data bytes)

wire = 0xF0, then for each byte b in BUF: (b >> 4), (b & 0x0F), then 0xF7
```

So a 19-byte-payload block is `4 + 19 = 23` BUF bytes → `2*23 = 46` nibbles →
`48` bytes on the wire (`F0 … F7`). The device ACKs each with a fixed 16-byte status
`F0 0B 02 00 01 00 00 00 03 01 04 00 08 00 00 F7`.

## Checksum — SOLVED

**CRC-8, polynomial 0x07 (CRC-8/SMBUS), init 0x00, no reflection, no final XOR.**
Computed over the **entire `BUF`** — command, index, length, and payload — with the
checksum byte `BUF[0]` held at `0` during the computation. The 256-entry table lives in
the dylib at vaddr `0xf5f10` (shared with the bundled FLAC decoder, which also uses
CRC-8/0x07). Reference code (`a2a1`-style):

```python
TBL = build_crc8_table(0x07)              # standard CRC-8/SMBUS table
def checksum(buf):                        # buf[0] is the (zeroed) checksum slot
    c = 0
    for b in buf:
        c = TBL[c ^ b]
    return c                              # -> nibble-split into wire bytes 1,2
```

Verified: `re/verify_crc.py` → 298/298.

## What this unblocks
- We can now **build valid write packets ourselves** (compute the CRC, nibble-encode,
  frame). This is the gate for the device-write product features (5/6 reassign/replace,
  and 4 once SnapTone payloads can be generated).
- **Still open:** how the ~2.7 KB SnapTone payload itself is produced from a NAM (the
  refit). That runs on the worker thread `threadEntryProc` in `5868USB.dylib` — next
  Ghidra target. Until then, SnapTone payloads must come from a Suite conversion (capture).

## Files
- `re/5868USB_arm64.dylib` — extracted arm64 slice analyzed in Ghidra.
- `re/DecompileValeton.java`, `re/FindCrcUser.java` — Ghidra headless scripts.
- `re/ghidra_valeton_out.txt`, `re/ghidra_crc_user.txt` — decompiler output.
- `re/dump_table.py` (confirm poly), `re/crc07_crack.py`, `re/verify_crc.py` (298/298).
