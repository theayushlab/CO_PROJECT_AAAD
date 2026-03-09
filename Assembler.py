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
    REGISTER_MAP["x"+str(_n)] = _n

RTYPE = {
    "add":  ("0000000", "000"),  "sub":  ("0100000", "000"),
    "sll":  ("0000000", "001"),  "slt":  ("0000000", "010"),
    "sltu": ("0000000", "011"),  "xor":  ("0000000", "100"),
    "srl":  ("0000000", "101"),  "sra":  ("0100000", "101"),
    "or":   ("0000000", "110"),  "and":  ("0000000", "111"),
}

ITYPE = {
    "addi":  "000",  "slti":  "010",  "sltiu": "011",
    "xori":  "100",  "ori":   "110",  "andi":  "111",}

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


def reg_num(name):
    key = name.lower()
    if key not in REGISTER_MAP:
        raise ValueError("Unknown register: '" + name + "'")
    return format(REGISTER_MAP[key], "05b")


def remove_comment(raw_line):
    cut = raw_line.find("#")
    return raw_line[:cut].strip() if cut != -1 else raw_line.strip()


def check_label(name):
    if not name:
        raise ValueError("Label name cannot be empty")
    if not (name[0].isalpha() or name[0] == "_"):
        raise ValueError("Label '" + name + "' must begin with a letter or underscore")


def split_mem_operand(token):
    lp = token.find("(")
    if lp == -1 or token[-1] != ")":
        raise ValueError("Expected offset(register) format, got: '" + token + "'")
    base = token[lp + 1 : -1]
    if not base:
        raise ValueError("Base register missing in '" + token + "'")
    return token[:lp], base


def clamp_imm12(raw, ctx):
    v = parse_int(raw)
    if not (-2048 <= v <= 2047):
        raise ValueError(ctx + ": " + str(v) + " outside signed 12-bit range [-2048, 2047]")
    return v


def clamp_imm20(raw, ctx):
    v = parse_int(raw)
    if not (0 <= v <= 0xFFFFF):
        raise ValueError(ctx + ": " + str(v) + " outside unsigned 20-bit range [0, 1048575]")
    return v


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


def enc_rtype(op, dst, src1, src2):
    f7, f3 = RTYPE[op]
    return f7 + reg_num(src2) + reg_num(src1) + f3 + reg_num(dst) + "0110011"


def enc_itype(op, dst, src1, imm):
    f3   = ITYPE[op]
    val  = clamp_imm12(imm, op + " immediate")
    bits = format(val & 0xFFF, "012b")
    return bits + reg_num(src1) + f3 + reg_num(dst) + "0010011"


def enc_imm_shift(op, dst, src1, shamt):
    f3, f7 = IMM_SHIFT[op]
    amt = parse_int(shamt)
    if not (0 <= amt <= 31):
        raise ValueError("Shift amount must be 0-31, got " + str(amt))
    return f7 + format(amt, "05b") + reg_num(src1) + f3 + reg_num(dst) + "0010011"


def enc_load(dst, offset, base):
    val  = clamp_imm12(offset, "load offset")
    bits = format(val & 0xFFF, "012b")
    return bits+reg_num(base)+"010"+reg_num(dst)+"0000011"


def enc_store(src, offset, base):
    val  = clamp_imm12(offset, "store offset")
    bits = format(val & 0xFFF, "012b")
    upper, lower = bits[:7], bits[7:]
    return upper+reg_num(src)+reg_num(base)+"010"+lower+"0100011"


def enc_branch(op, rs1, rs2, offset):
    f3  = BRANCH[op]
    imm = parse_int(offset) & 0x1FFF
    b12   = str((imm >> 12) & 1)
    b11   = str((imm >> 11) & 1)
    b10_5 = format((imm >>  5) & 0x3F,  "06b")
    b4_1  = format((imm >>  1) & 0x0F,  "04b")
    return b12+b10_5+reg_num(rs2)+reg_num(rs1)+f3+b4_1+b11+"1100011"


def enc_jal(dst, offset):
    imm    = parse_int(offset) & 0x1FFFFF
    b20    = str((imm >> 20) & 1)
    b19_12 = format((imm >> 12) & 0xFF,  "08b")
    b11    = str((imm >> 11) & 1)
    b10_1  = format((imm >>  1) & 0x3FF, "010b")
    return b20 + b10_1 + b11 + b19_12 + reg_num(dst) + "1101111"


def enc_jalr(dst, base, imm):
    val  = clamp_imm12(imm, "jalr immediate")
    bits = format(val & 0xFFF, "012b")
    return bits + reg_num(base) + "000" + reg_num(dst) + "1100111"


def enc_utype(op, dst, imm):
    opcode = "0110111" if op == "lui" else "0010111"
    val    = clamp_imm20(imm, op + " immediate")
    bits   = format(val & 0xFFFFF, "020b")
    return bits+reg_num(dst)+opcode


def run_assembler(src_path, bin_path, txt_path=""):
    with open(src_path) as fh:
        raw_lines = fh.readlines()

    cleaned = []
    for lineno, raw in enumerate(raw_lines, start=1):
        stripped = remove_comment(raw)
        if stripped:
            cleaned.append((lineno, stripped))
    label_table = {}
    instr_list  = []
    addr        = 0

    for orig_no, text in cleaned:
        remainder = text

        while ":" in remainder:
            colon_pos = remainder.index(":")
            lbl       = remainder[:colon_pos].strip()
            remainder = remainder[colon_pos + 1:].strip()

            try:
                check_label(lbl)
            except ValueError as err:
                print("Error at line " + str(orig_no) + " : " + str(err))
                sys.exit(1)

            if lbl in label_table:
                print("Error at line " + str(orig_no) + " : Duplicate label '" + lbl + "'")
                sys.exit(1)

            label_table[lbl] = addr

        if remainder:
            instr_list.append((orig_no, remainder))
            addr += 4

    if len(instr_list) > MAX_INSTRUCTIONS:
        print(
            "Error: Program too large — "
            + str(len(instr_list)) + " instructions (limit: "
            + str(MAX_INSTRUCTIONS) + ")"
        )
        sys.exit(1)

    encoded   = []
    found_err = False
    pc        = 0

    for orig_no, instr_text in instr_list:
        parts = normalise(instr_text)
        mnem  = parts[0].lower()

        try:
            verify_operand_count(mnem, parts)

            if mnem in RTYPE:
                word = enc_rtype(mnem, parts[1], parts[2], parts[3])

            elif mnem in ITYPE:
                word = enc_itype(mnem, parts[1], parts[2], parts[3])

            elif mnem in IMM_SHIFT:
                word = enc_imm_shift(mnem, parts[1], parts[2], parts[3])

            elif mnem == "lw":
                off, base = split_mem_operand(parts[2])
                word = enc_load(parts[1], off, base)

            elif mnem == "sw":
                off, base = split_mem_operand(parts[2])
                word = enc_store(parts[1], off, base)

            elif mnem in BRANCH:
                tgt  = parts[3]
                base = (pc + 4) if OFFSET_FROM_NEXT else pc
                if tgt in label_table:
                    off = label_table[tgt] - base
                else:
                    try:
                        off = parse_int(tgt)
                    except ValueError:
                        raise ValueError("Undefined label: '" + tgt + "'")
                off  = validate_branch_off(off)
                word = enc_branch(mnem, parts[1], parts[2], off)

            elif mnem == "jal":
                tgt  = parts[2]
                base = (pc + 4) if OFFSET_FROM_NEXT else pc
                if tgt in label_table:
                    off = label_table[tgt] - base
                else:
                    try:
                        off = parse_int(tgt)
                    except ValueError:
                        raise ValueError("Undefined label: '" + tgt + "'")
                off  = validate_jal_off(off)
                word = enc_jal(parts[1], off)

            elif mnem == "jalr":
                if "(" in parts[2]:
                    off, base = split_mem_operand(parts[2])
                    word = enc_jalr(parts[1], base, off)
                elif parts[2].lower() in REGISTER_MAP:
                    word = enc_jalr(parts[1], parts[2], parts[3])
                else:
                    word = enc_jalr(parts[1], parts[3], parts[2])

            elif mnem in ("lui", "auipc"):
                word = enc_utype(mnem, parts[1], parts[2])

            else:
                raise ValueError("Unknown mnemonic: '" + mnem + "'")

            encoded.append(word)

        except Exception as ex:
            print("Error at line " + str(orig_no) + " : " + str(ex))
            found_err = True

        pc += 4

    if instr_list:
        last_no, last_text = instr_list[-1]
        last_pc    = (len(instr_list) - 1) * 4
        last_parts = normalise(last_text)

        halted = False
        if last_parts[0].lower() == "beq":
            r1 = last_parts[1].lower()
            r2 = last_parts[2].lower()
            if r1 in ("zero", "x0") and r2 in ("zero", "x0"):
                try:
                    ref = (last_pc + 4) if OFFSET_FROM_NEXT else last_pc
                    tgt = last_parts[3]
                    off = (label_table[tgt] - ref) if tgt in label_table else parse_int(tgt)
                    halted = (off == 0)
                except Exception:
                    halted = False

        if not halted:
            print("ERROR at line " + str(last_no) + ": Last instruction needs to be Virtual Hault")
            found_err = True

    if found_err:
        sys.exit(1)
    payload = "\n".join(encoded) + "\n"
    with open(bin_path, "w") as fh:
        fh.write(payload)

    if txt_path:
        with open(txt_path, "w") as fh:
            fh.write(payload)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 assembler.py <source.asm> <output.bin> [readable.txt]")
        sys.exit(1)
    extra = sys.argv[3] if len(sys.argv) > 3 else ""
    run_assembler(sys.argv[1], sys.argv[2], extra)
