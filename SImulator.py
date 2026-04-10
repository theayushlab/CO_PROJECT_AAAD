import sys

# RV32I Simulator -- CO Project 2026
# Team: Ayush, Kumar, Devesh, Swami

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


def load_program(path):
    words = []
    with open(path) as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            if raw[:2] in ("0b", "0B"):
                raw = raw[2:]
            if len(raw) == 32 and set(raw) <= {"0", "1"}:
                words.append(int(raw, 2))
    return words


class RV32Sim:

    def __init__(self):
        self.x      = [0] * 32
        self.x[2]   = INIT_SP      # sp
        self.mem    = {}
        self.pc     = 0
        self.log    = []
        self.halted = False

        self._rtab = {
            (0, 0x00): lambda a, b, ua, ub, sh: mask32(a + b),        # add
            (0, 0x20): lambda a, b, ua, ub, sh: mask32(a - b),        # sub
            (1, 0x00): lambda a, b, ua, ub, sh: mask32(ua << sh),     # sll
            (2, 0x00): lambda a, b, ua, ub, sh: 1 if a < b else 0,    # slt
            (3, 0x00): lambda a, b, ua, ub, sh: 1 if ua < ub else 0,  # sltu
            (4, 0x00): lambda a, b, ua, ub, sh: mask32(a ^ b),        # xor
            (5, 0x00): lambda a, b, ua, ub, sh: ua >> sh,              # srl
            (5, 0x20): lambda a, b, ua, ub, sh: mask32(a >> sh),      # sra
            (6, 0x00): lambda a, b, ua, ub, sh: mask32(a | b),        # or
            (7, 0x00): lambda a, b, ua, ub, sh: mask32(a & b),        # and
        }

    def _snap(self, nxt_pc):
        cols = [to_bin(nxt_pc)] + [to_bin(v) for v in self.x]
        return " ".join(cols) + " "

def _do_rtype(self, rd, rs1, rs2, f3, f7):
        fn = self._rtab.get((f3, f7))
        if fn is None:
            return
        a, b   = signed32(self.x[rs1]), signed32(self.x[rs2])
        ua, ub = self.x[rs1], self.x[rs2]
        sh     = ub & 0x1F
        if rd:
            self.x[rd] = fn(a, b, ua, ub, sh)

    def _do_itype(self, rd, rs1, imm, f3, f7, shamt):
        a  = signed32(self.x[rs1])
        ua = self.x[rs1]
        if   f3 == 0:              v = mask32(a + imm)
        elif f3 == 1 and f7 == 0:  v = mask32(ua << shamt)
        elif f3 == 2:              v = 1 if a < imm else 0
        elif f3 == 3:              v = 1 if ua < mask32(imm) else 0
        elif f3 == 4:              v = mask32(a ^ imm)
        elif f3 == 5 and f7 == 0:  v = ua >> shamt
        elif f3 == 5 and f7 == 32: v = mask32(a >> shamt)
        elif f3 == 6:              v = mask32(a | imm)
        elif f3 == 7:              v = mask32(a & imm)
        else:                      return
        if rd:
            self.x[rd] = v

    def _step(self, word, lineno):
        op  = word & 0x7F
        rd  = (word >>  7) & 0x1F
        f3  = (word >> 12) & 0x07
        rs1 = (word >> 15) & 0x1F
        rs2 = (word >> 20) & 0x1F
        f7  = (word >> 25) & 0x7F
        nxt = self.pc + 4

        if op == 0x33:
            self._do_rtype(rd, rs1, rs2, f3, f7)

        elif op == 0x13:
            self._do_itype(rd, rs1, iimm(word), f3, f7, (word >> 20) & 0x1F)

        elif op == 0x03 and f3 == 2:    # lw
            addr = mask32(self.x[rs1] + iimm(word))
            ok, reason = valid_mem(addr)
            if not ok:
                print(f"Error at line {lineno}: Invalid memory access ({reason})")
                return None
            elif rd:
                self.x[rd] = self.mem.get(addr, 0)

        elif op == 0x23 and f3 == 2:    # sw
            addr = mask32(self.x[rs1] + simm(word))
            ok, reason = valid_mem(addr)
            if not ok:
                print(f"Error at line {lineno}: Invalid memory access ({reason})")
                return None
            else:
                self.mem[addr] = mask32(self.x[rs2])

        elif op == 0x63:    # branches
            a, b   = signed32(self.x[rs1]), signed32(self.x[rs2])
            ua, ub = self.x[rs1], self.x[rs2]
            taken = {0: ua==ub, 1: ua!=ub, 4: a<b, 5: a>=b, 6: ua<ub, 7: ua>=ub}.get(f3, False)
            if taken:
                nxt = mask32(self.pc + bimm(word))

        elif op == 0x6F:    # jal
            self.x[rd] = mask32(self.pc + 4)
            nxt = mask32(self.pc + jimm(word))

        elif op == 0x67 and f3 == 0:    # jalr
            ret = mask32(self.pc + 4)
            nxt = mask32(self.x[rs1] + iimm(word)) & 0xFFFFFFFE
            self.x[rd] = ret

        elif op == 0x37:    # lui
            if rd: self.x[rd] = uimm(word)

        elif op == 0x17:    # auipc
            if rd: self.x[rd] = mask32(self.pc + uimm(word))

        self.x[0] = 0
        return nxt
        
    def execute(self, prog):
        cycles = 0
        while cycles < MAX_CYCLES:
            slot = self.pc // 4
            if self.pc < 0 or slot >= len(prog):
                break
            word = prog[slot]
            nxt  = self._step(word, slot + 1)
            if nxt is None:
                break
            self.log.append(self._snap(nxt))
            if word == 0x00000063:  # virtual halt
                self.halted = True
                break
            self.pc = nxt
            cycles += 1

    def dump_data(self):
        out = []
        for k in range(32):
            addr = DATA_START + k * 4
            out.append("0x%08X:%s" % (addr, to_bin(self.mem.get(addr, 0))))
        return out


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 Simulator.py input.txt output.txt [readable.txt]")
        sys.exit(1)

    in_path  = sys.argv[1]
    out_path = sys.argv[2]
    rd_path  = sys.argv[3] if len(sys.argv) > 3 else None

    prog = load_program(in_path)
    if not prog:
        print("Error: no valid instructions in " + in_path)
        sys.exit(1)

    sim = RV32Sim()
    sim.execute(prog)

    lines = sim.log[:]
    if sim.halted:
        lines += sim.dump_data()

    body = "\n".join(lines) + ("\n" if lines else "")

    with open(out_path, "w") as fh:
        fh.write(body)
    if rd_path:
        with open(rd_path, "w") as fh:
            fh.write(body)


if __name__ == "__main__":
    main()

            

