import re
import sys
from functools import reduce

HEX = re.compile(r"\b[0-9A-Fa-f]{2}\b")


def packets(path):
    out = []
    for line in open(path, errors="replace"):
        if "to gp-50" not in line.lower():
            continue
        b = [int(t, 16) for t in HEX.findall(line)]
        if 0xF0 in b:
            b = b[b.index(0xF0) :]
            if len(b) == 48 and b[3] == 0x09 and b[4] == 0x02:
                out.append(b)
    return out


def crc8_step(crc, byte, poly, refin):
    if refin:
        byte = int(f"{byte:08b}"[::-1], 2)
    crc ^= byte
    for _ in range(8):
        crc = ((crc << 1) ^ poly) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


path = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "/Users/drewmerc/Desktop/valeton_import_capture.txt"
)
pk = packets(path)
n = len(pk)

# verify nibble assumption
mx1 = max(p[1] for p in pk)
mx2 = max(p[2] for p in pk)
print(
    f"{n} packets. max ck1={mx1:#04x} max ck2={mx2:#04x}  (both<=0x0F => nibbles of 1 byte)"
)
tgt = [(p[1] << 4) | p[2] for p in pk]


# body variants (as transmitted = nibbles) INCLUDING headers
def body_nib(p):  # everything between F0 and F7 except the ck bytes
    return p[3:-1]  # 09 02 sec blk 01 03 payload...


def body_after_hdr(p):  # sec blk 01 03 payload
    return p[5:-1]


POLYS = [
    0x07,
    0x31,
    0x1D,
    0x9B,
    0xD5,
    0x2F,
    0x39,
    0x4D,
    0xA7,
    0x8D,
    0xC2,
    0x0B,
    0x49,
    0x63,
    0xE7,
]
best = []

for rn, rf in (("body_nib[3:-1]", body_nib), ("body[5:-1]", body_after_hdr)):
    # rolling crc/sum/xor over the transmitted bytes incl headers
    for poly in POLYS:
        for init in (0x00, 0xFF):
            for refin in (False, True):
                for sample in ("before", "after"):
                    crc = init
                    hits = 0
                    for i, p in enumerate(pk):
                        if sample == "before" and crc == tgt[i]:
                            hits += 1
                        for byte in rf(p):
                            crc = crc8_step(crc, byte, poly, refin)
                        if sample == "after" and crc == tgt[i]:
                            hits += 1
                    if hits > n * 0.6:
                        best.append(
                            (
                                hits,
                                f"ROLL crc8 {rn} poly={poly:#04x} init={init:#04x} refin={refin} {sample}",
                            )
                        )
    for sn, sf in (
        ("sum", lambda d: sum(d)),
        ("xor", lambda d: reduce(lambda a, c: a ^ c, d, 0)),
    ):
        for sample in ("before", "after"):
            acc = 0
            hits = 0
            for i, p in enumerate(pk):
                if sample == "before" and (acc & 0xFF) == tgt[i]:
                    hits += 1
                acc = sf(list(rf(p))) if sn == "xor" else acc + sum(rf(p))
                if sample == "after" and (acc & 0xFF) == tgt[i]:
                    hits += 1
            if hits > n * 0.6:
                best.append((hits, f"ROLL {sn} {rn} {sample}"))
    # per-packet crc over body incl headers
    for poly in POLYS:
        for init in (0x00, 0xFF):
            for refin in (False, True):
                hits = 0
                for i, p in enumerate(pk):
                    crc = init
                    for byte in rf(p):
                        crc = crc8_step(crc, byte, poly, refin)
                    if crc == tgt[i]:
                        hits += 1
                if hits > n * 0.6:
                    best.append(
                        (
                            hits,
                            f"per-pkt crc8 {rn} poly={poly:#04x} init={init:#04x} refin={refin}",
                        )
                    )

best.sort(reverse=True)
print("\n=== matches >60% ===")
for h, d in best[:15]:
    print(f"  {h}/{n}  {d}")
if not best:
    print("  none. ck sequence (8-bit):", " ".join(f"{t:02X}" for t in tgt[:32]))
