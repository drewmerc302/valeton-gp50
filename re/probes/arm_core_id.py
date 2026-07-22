#!/usr/bin/env python3
"""Identify the ARM core behind an HTFW region.

Answers "can this device run NAM A2-Lite natively?" by pinning the core family.
The discriminators are literal-pool constants: Thumb-2 cannot encode a 32-bit
peripheral address inline, so every access to a System Control Space register
leaves the raw address in the binary as a little-endian u32.

Run:  python re/probes/arm_core_id.py <region.bin>...
"""

import collections
import re
import struct
import sys

# System Control Space registers, keyed by which cores actually implement them.
# Cache and TCM blocks are the load-bearing ones: a Cortex-M0/M3/M4 has neither,
# so a hit there pins the core at M7 (or the much later M55/M85).
SCS = {
    "M7-only (cache maint.)": {
        0xE000EF50: "ICIALLU  (I-cache invalidate all)",
        0xE000EF58: "ICIMVAU  (I-cache invalidate by addr)",
        0xE000EF5C: "DCIMVAC  (D-cache invalidate by addr)",
        0xE000EF60: "DCISW    (D-cache invalidate by set/way)",
        0xE000EF64: "DCCMVAU  (D-cache clean by addr)",
        0xE000EF68: "DCCMVAC  (D-cache clean by addr)",
        0xE000EF6C: "DCCSW    (D-cache clean by set/way)",
        0xE000EF70: "DCCIMVAC (D-cache clean+invalidate)",
        0xE000EF74: "DCCISW   (D-cache clean+inv by set/way)",
    },
    "M7-only (TCM / cache cfg)": {
        0xE000EF90: "ITCMCR",
        0xE000EF94: "DTCMCR",
        0xE000EF98: "AHBPCR",
        0xE000EF9C: "CACR",
        0xE000EF0C: "CCSIDR-ish / cache id",
        0xE000ED78: "CCSIDR",
        0xE000ED7C: "CCSELR",
        0xE000ED80: "CTR (cache type)",
    },
    "FPU (M4F / M7 / M33)": {
        0xE000ED88: "CPACR  (coprocessor access -> FPU enable)",
        0xE000EF34: "FPCCR",
        0xE000EF38: "FPCAR",
        0xE000EF3C: "FPDSCR",
    },
    "generic Cortex-M (any)": {
        0xE000E010: "SysTick CTRL",
        0xE000E100: "NVIC ISER",
        0xE000ED00: "CPUID",
        0xE000ED04: "ICSR",
        0xE000ED08: "VTOR",
        0xE000ED0C: "AIRCR",
        0xE000ED14: "CCR",
        0xE000EDF0: "DHCSR (debug)",
    },
}

# Plausible core clocks. A literal match is weak on its own (any u32 can occur by
# chance) but the set of which ones appear is informative next to the PLL code.
CLOCKS = [
    600_000_000,
    550_000_000,
    528_000_000,
    480_000_000,
    400_000_000,
    300_000_000,
    240_000_000,
    216_000_000,
    200_000_000,
    192_000_000,
    168_000_000,
    160_000_000,
    120_000_000,
    100_000_000,
    98_304_000,
    49_152_000,
    24_576_000,
    12_288_000,  # audio-master families
]

SAMPLE_RATES = [44100, 48000, 96000, 88200, 192000]

VENDOR_HINTS = [
    b"Cortex",
    b"CMSIS",
    b"cortex",
    b"ARM ",
    b"armcc",
    b"GCC",
    b"IAR",
    b"MVsilicon",
    b"mvsilicon",
    b"Mountain View",
    b"STM32",
    b"NXP",
    b"i.MX",
    b"Analog Devices",
    b"SHARC",
    b"ADSP",
    b"Blackfin",
    b"Xtensa",
    b"HiFi",
    b"TMS320",
    b"C674",
    b"Kinetis",
    b"nRF",
    b"ESP32",
    b"Sigma",
    b"FreeRTOS",
    b"RT-Thread",
    b"ucos",
    b"uC/OS",
    b"ThreadX",
]


def u32_index(blob):
    """Every 4-byte-aligned LE u32 in the blob -> list of offsets."""
    idx = collections.defaultdict(list)
    for off in range(0, len(blob) - 3, 4):
        idx[struct.unpack_from("<I", blob, off)[0]].append(off)
    return idx


def thumb_stats(blob):
    """Rough Thumb/Thumb-2 instruction-class densities, per KB."""
    n_half = len(blob) // 2
    if not n_half:
        return {}
    counts = collections.Counter()
    for i in range(n_half):
        hw = struct.unpack_from("<H", blob, i * 2)[0]
        top5 = hw >> 11
        if top5 in (0b11101, 0b11110, 0b11111):
            counts["thumb2_32bit"] += 1
            # Coprocessor/FPU space: second halfword decides, but the first
            # halfword 0xEExx / 0xEDxx / 0xECxx is the VFP/NEON door.
            hi8 = hw >> 8
            if hi8 in (0xEE, 0xED, 0xEC):
                counts["vfp_coproc"] += 1
            if hi8 == 0xFB:
                counts["dsp_mul_ext"] += 1  # SMLAD/SMUAD/SMMUL family
        if hw == 0x4770:
            counts["bx_lr"] += 1
        if hw == 0xBF00:
            counts["nop"] += 1
    kb = len(blob) / 1024
    return {k: v / kb for k, v in counts.items()}


def vfp_precision(blob):
    """Split VFP ops into single vs double precision.

    In the VFP encoding the 'sz' bit (bit 8 of the SECOND halfword) selects
    double precision. Cortex-M4F is single-precision only; M7 may have either.
    """
    single = double = 0
    for i in range(0, len(blob) - 3, 2):
        hw1 = struct.unpack_from("<H", blob, i)[0]
        if (hw1 >> 8) != 0xEE:
            continue
        hw2 = struct.unpack_from("<H", blob, i + 2)[0]
        # coproc field = bits 8..11 of hw2; 10 = single, 11 = double
        cp = (hw2 >> 8) & 0xF
        if cp == 10:
            single += 1
        elif cp == 11:
            double += 1
    return single, double


def vector_tables(blob, idx):
    """Scan for a Cortex-M vector table: plausible initial SP then odd reset."""
    hits = []
    for off in range(0, min(len(blob), 0x20000) - 8, 4):
        sp, reset = struct.unpack_from("<II", blob, off)
        sp_ok = 0x20000000 <= sp <= 0x20200000 or 0x00000000 < sp <= 0x00100000
        if sp_ok and (reset & 1) and reset != 0xFFFFFFFF:
            hits.append((off, sp, reset))
    return hits[:6]


def report(path):
    blob = open(path, "rb").read()
    print(f"\n=== {path}  ({len(blob):,} bytes) ===")

    idx = u32_index(blob)

    for group, regs in SCS.items():
        found = [(a, n, idx[a]) for a, n in sorted(regs.items()) if a in idx]
        if found:
            print(f"  [{group}]")
            for addr, name, offs in found:
                where = ", ".join(f"0x{o:x}" for o in offs[:4])
                more = f" (+{len(offs) - 4})" if len(offs) > 4 else ""
                print(f"    0x{addr:08X}  {name:<38} x{len(offs):<3} @ {where}{more}")

    st = thumb_stats(blob)
    if st:
        print("  [instruction density, per KB]")
        for k in ("thumb2_32bit", "bx_lr", "nop", "vfp_coproc", "dsp_mul_ext"):
            print(f"    {k:<14} {st.get(k, 0):8.2f}")
    sp_, dp_ = vfp_precision(blob)
    print(f"    vfp single={sp_}  double={dp_}")

    vt = vector_tables(blob, idx)
    if vt:
        print("  [vector-table candidates]")
        for off, sp, reset in vt:
            print(f"    @0x{off:06x}  SP=0x{sp:08x}  reset=0x{reset:08x}")

    clk = [(c, len(idx[c])) for c in CLOCKS if c in idx]
    if clk:
        print("  [clock literals]")
        for c, n in clk:
            print(f"    {c:>12,}  x{n}")
    sr = [(c, len(idx[c])) for c in SAMPLE_RATES if c in idx]
    if sr:
        print("  [sample-rate literals]  " + ", ".join(f"{c}x{n}" for c, n in sr))

    hits = [h for h in VENDOR_HINTS if h in blob]
    if hits:
        print("  [vendor/toolchain strings]")
        for h in hits:
            for m in list(re.finditer(re.escape(h), blob))[:3]:
                s = blob[max(0, m.start() - 24) : m.start() + 56]
                s = re.sub(rb"[^\x20-\x7e]", b".", s).decode()
                print(f"    {h.decode():<14} {s}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        report(p)
