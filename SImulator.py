import sys

# RV32I Simulator -- CO Project 2026
# Team: Ayush, Kumar, Devesh, Swami
# Run: python3 Simulator.py input.txt output.txt [readable.txt]

STACK_START = 0x00000000
STACK_END   = 0x000001FC
DATA_START  = 0x00010000
DATA_END    = DATA_START + 31 * 4
INIT_SP     = 0x17C
MAX_CYCLES  = 100000


def mask32(v):
    return v & 0xFFFFFFFF

def signed32(v):
    v = mask32(v)
    return v - (1 << 32) if v >= (1 << 31) else v

def sext(v, w):
    p = 1 << (w - 1)
    return (v & (p - 1)) - (v & p)

def to_bin(v):
    return "0b" + format(mask32(v), "032b")


def iimm(w):
    return sext((w >> 20) & 0xFFF, 12)

def simm(w):
    return sext(((w >> 25) << 5) | ((w >> 7) & 0x1F), 12)

def uimm(w):
    return w & 0xFFFFF000

def bimm(w):
    raw = (((w >> 31) & 1) << 12) | (((w >> 7)  & 1) << 11) | \
          (((w >> 25) & 0x3F) << 5) | (((w >> 8) & 0xF) << 1)
    return sext(raw, 13)

def jimm(w):
    raw = (((w >> 31) & 1) << 20) | (((w >> 12) & 0xFF) << 12) | \
          (((w >> 20) & 1) << 11)  | (((w >> 21) & 0x3FF) << 1)
    return sext(raw, 21)


def valid_mem(addr):
    if addr % 4 != 0:
        return False, f"unaligned address 0x{addr:08X} (must be 4-byte aligned)"
    in_range = (STACK_START <= addr <= STACK_END) or (DATA_START <= addr <= DATA_END)
    if not in_range:
        return False, (f"out of bounds address 0x{addr:08X} "
                       f"(valid: stack 0x{STACK_START:08X}-0x{STACK_END:08X}, "
                       f"data 0x{DATA_START:08X}-0x{DATA_END:08X})")
    return True, ""

