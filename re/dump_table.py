#!/usr/bin/env python
"""Read the 256-byte table at vaddr 0xf5f00 in 5868USB_arm64.dylib and test it as a
CRC-8 lookup table (try all polynomials, reflected/not)."""

import struct

DYLIB = "/Users/drewmerc/workspace/valeton/re/5868USB_arm64.dylib"
VADDR = 0x000F5F00


def vaddr_to_off(path, vaddr):
    data = open(path, "rb").read()
    magic, cputype, cpusub, filetype, ncmds, sizeofcmds, flags, reserved = (
        struct.unpack_from("<IIIIIIII", data, 0)
    )
    assert magic == 0xFEEDFACF, f"not 64-bit macho: {magic:#x}"
    off = 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            segname = data[off + 8 : off + 24].split(b"\0")[0].decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from(
                "<QQQQ", data, off + 24
            )
            (nsects,) = (
                struct.unpack_from("<I", data, off + 64 - 8 + 4) if False else (0,)
            )
            # iterate sections
            (nsects,) = struct.unpack_from("<I", data, off + 64)
            so = off + 72
            for _s in range(nsects):
                sn = data[so : so + 16].split(b"\0")[0].decode()
                segn = data[so + 16 : so + 32].split(b"\0")[0].decode()
                addr, size = struct.unpack_from("<QQ", data, so + 32)
                (soff,) = struct.unpack_from("<I", data, so + 48)
                if addr <= vaddr < addr + size:
                    return data, soff + (vaddr - addr), f"{segn},{sn}"
                so += 80
        off += cmdsize
    raise SystemExit("vaddr not found in any section")


def crc8_table(poly, refin):
    t = []
    for i in range(256):
        c = i
        if refin:
            c = int(f"{c:08b}"[::-1], 2)
        crc = c
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
        if refin:
            crc = int(f"{crc:08b}"[::-1], 2)
        t.append(crc)
    return t


def main():
    data, off, where = vaddr_to_off(DYLIB, VADDR)
    tbl = list(data[off : off + 256])
    print(f"table @ vaddr {VADDR:#x} -> file off {off:#x} (section {where})")
    print("first 32:", " ".join(f"{b:02X}" for b in tbl[:32]))
    print("unique:", len(set(tbl)))

    # test against CRC-8 tables for all polynomials
    hits = []
    for poly in range(256):
        for refin in (False, True):
            if crc8_table(poly, refin) == tbl:
                hits.append((poly, refin))
    if hits:
        for poly, refin in hits:
            print(f"*** MATCH: CRC-8 table poly={poly:#04x} refin={refin} ***")
    else:
        print(
            "no exact CRC-8 table match (may be reflected/xor variant, an S-box, or a "
            "different 256-table). Dumping full table for inspection:"
        )
        for r in range(0, 256, 16):
            print("  " + " ".join(f"{b:02X}" for b in tbl[r : r + 16]))


if __name__ == "__main__":
    main()
