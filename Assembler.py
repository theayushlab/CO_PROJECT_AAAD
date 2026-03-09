import sys

OFFSET_FROM_NEXT = False

MAX_INSTRUCTIONS = 64

REGISTER_MAP = {
    "zero": 0,  "ra":  1,  "sp":  2,  "gp":  3,  "tp":  4,
    "t0":   5,  "t1":  6,  "t2":  7,  "s0":  8,  "fp":  8,
    "s1":   9,  "a0": 10,  "a1": 11,  "a2": 12,  "a3": 13,
    "a4":  14,  "a5": 15,  "a6": 16,  "a7": 17,  "s2": 18,
    "s3":  19,  "s4": 20,  "s5": 21,  "s6": 22,  "s7": 23,
    "s8":  24,  "s9": 25, "s10": 26, "s11": 27,  "t3": 28,
    "t4":  29,  "t5": 30,  "t6": 31,
}
for _n in range(32):
    REGISTER_MAP["x" + str(_n)] = _n
RTYPE = {
    "add":  ("0000000", "000"),  "sub":  ("0100000", "000"),
    "sll":  ("0000000", "001"),  "slt":  ("0000000", "010"),
    "sltu": ("0000000", "011"),  "xor":  ("0000000", "100"),
    "srl":  ("0000000", "101"),  "sra":  ("0100000", "101"),
    "or":   ("0000000", "110"),  "and":  ("0000000", "111"),
}

ITYPE = {
    "addi":  "000",  "slti":  "010",  "sltiu": "011",
    "xori":  "100",  "ori":   "110",  "andi":  "111",
}

IMM_SHIFT = {
    "slli": ("001", "0000000"),
    "srli": ("101", "0000000"),
    "srai": ("101", "0100000"),
}

BRANCH = {
    "beq":  "000",  "bne":  "001",
    "blt":  "100",  "bge":  "101",
    "bltu": "110",  "bgeu": "111",
}
_MIN_OPS = {}
for _k in RTYPE:     _MIN_OPS[_k] = 3
for _k in ITYPE:     _MIN_OPS[_k] = 3
for _k in IMM_SHIFT: _MIN_OPS[_k] = 3
for _k in BRANCH:    _MIN_OPS[_k] = 3
_MIN_OPS.update({"lw": 2, "sw": 2, "jal": 2, "jalr": 2, "lui": 2, "auipc": 2})




def parse_int(token):
    if isinstance(token, int):
        return token
    return int(token, 0)









def remove_comment(raw_line):
    cut = raw_line.find("#")
    return raw_line[:cut].strip() if cut != -1 else raw_line.strip()


def check_label(name):
    if not name:
        raise ValueError("Label name cannot be empty")
    if not (name[0].isalpha() or name[0] == "_"):
        raise ValueError("Label '" + name + "' must begin with a letter or underscore")


























def validate_branch_off(val):
    v = parse_int(val)
    if v % 2:
        raise ValueError("Branch offset must be 2-byte aligned, got " + str(v))
    if not (-4096 <= v <= 4094):
        raise ValueError("Branch offset " + str(v) + " out of [-4096, 4094]")
    return v


def validate_jal_off(val):
    v = parse_int(val)
    if v % 2:
        raise ValueError("JAL offset must be 2-byte aligned, got " + str(v))
    lo, hi = -(1 << 20), (1 << 20) - 2
    if not (lo <= v <= hi):
        raise ValueError("JAL offset " + str(v) + " out of range")
    return v


















def verify_operand_count(mnemonic, parts):
    needed = _MIN_OPS.get(mnemonic, 0)
    got    = len(parts) - 1
    if got < needed:
        raise ValueError(
            "'" + mnemonic + "' needs " + str(needed) +
            " operand(s), got " + str(got)
        )


def normalise(line):
    return line.replace(",", " ").split()
























































































































































































































































































































.
