#!/usr/bin/env python3
"""Z80 instruction tracer for KOF96 sound driver.

Simulates Z80 execution against the M-ROM binary, tracing memory reads,
port writes (YM2610 registers), and program flow. Replicates the Geolith
emulator's memory map and bank switching exactly.

Usage: python3 z80_trace.py [--cmd 0x21] [--max-ticks 500]
"""

import struct, sys, argparse

class Z80Tracer:
    def __init__(self, mrom_path):
        with open(mrom_path, 'rb') as f:
            self.mrom = bytearray(f.read())

        # Z80 registers
        self.a = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.a2 = self.b2 = self.c2 = self.d2 = self.e2 = self.h2 = self.l2 = 0
        self.f = 0x40  # Z flag set
        self.f2 = 0
        self.ix = self.iy = 0
        self.sp = 0xFFFC
        self.pc = 0
        self.i = self.r = 0
        self.iff1 = self.iff2 = 0
        self.im = 0
        self.halted = False

        # Memory
        self.ram = bytearray(2048)  # 0xF800-0xFFFF
        self.banks = [0, 0, 0, 0]  # bank offsets

        # State
        self.cycles = 0
        self.nmi_enabled = False
        self.sound_code = 0
        self.sound_reply = 0

        # Tracing
        self.ym_writes = []
        self.song_reads = []
        self.max_instructions = 100000
        self.verbose = False
        self.trace_ym = True

    def mem_read(self, addr):
        addr &= 0xFFFF
        if addr < 0x8000:
            return self.mrom[addr]
        elif addr < 0xC000:
            return self.mrom[self.banks[0] + (addr & 0x3FFF)]
        elif addr < 0xE000:
            return self.mrom[self.banks[1] + (addr & 0x1FFF)]
        elif addr < 0xF000:
            return self.mrom[self.banks[2] + (addr & 0x0FFF)]
        elif addr < 0xF800:
            return self.mrom[self.banks[3] + (addr & 0x07FF)]
        else:
            return self.ram[addr & 0x7FF]

    def mem_write(self, addr, val):
        addr &= 0xFFFF
        val &= 0xFF
        if addr >= 0xF800:
            self.ram[addr & 0x7FF] = val

    def mem_read16(self, addr):
        return self.mem_read(addr) | (self.mem_read(addr + 1) << 8)

    def mem_write16(self, addr, val):
        self.mem_write(addr, val & 0xFF)
        self.mem_write(addr + 1, (val >> 8) & 0xFF)

    def fetch(self):
        val = self.mem_read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return val

    def fetch16(self):
        lo = self.fetch()
        hi = self.fetch()
        return (hi << 8) | lo

    def push(self, val):
        self.sp = (self.sp - 2) & 0xFFFF
        self.mem_write16(self.sp, val)

    def pop(self):
        val = self.mem_read16(self.sp)
        self.sp = (self.sp + 2) & 0xFFFF
        return val

    def get_hl(self): return (self.h << 8) | self.l
    def set_hl(self, v): self.h = (v >> 8) & 0xFF; self.l = v & 0xFF
    def get_bc(self): return (self.b << 8) | self.c
    def set_bc(self, v): self.b = (v >> 8) & 0xFF; self.c = v & 0xFF
    def get_de(self): return (self.d << 8) | self.e
    def set_de(self, v): self.d = (v >> 8) & 0xFF; self.e = v & 0xFF

    # Flags
    FLAG_C = 0x01
    FLAG_N = 0x02
    FLAG_PV = 0x04
    FLAG_H = 0x10
    FLAG_Z = 0x40
    FLAG_S = 0x80

    def set_flag(self, flag, val):
        if val: self.f |= flag
        else: self.f &= ~flag

    def get_flag(self, flag):
        return bool(self.f & flag)

    def update_flags_logic(self, result):
        result &= 0xFF
        self.set_flag(self.FLAG_S, result & 0x80)
        self.set_flag(self.FLAG_Z, result == 0)
        self.set_flag(self.FLAG_H, 0)
        self.set_flag(self.FLAG_N, 0)
        self.set_flag(self.FLAG_C, 0)
        return result

    def update_flags_arith(self, a, operand, result, sub=False):
        r = result & 0xFF
        self.set_flag(self.FLAG_S, r & 0x80)
        self.set_flag(self.FLAG_Z, r == 0)
        self.set_flag(self.FLAG_C, result & 0x100 if not sub else result < 0 or result > 0xFF)
        self.set_flag(self.FLAG_N, sub)
        self.set_flag(self.FLAG_H, ((a ^ operand ^ r) & 0x10) != 0)
        return r

    def port_read(self, port):
        port_lo = port & 0xFF
        if port_lo == 0x00:
            return self.sound_code
        elif port_lo == 0x04:
            return 0x03  # YM2610 status: Timer A + B flags set
        elif port_lo in (0x05, 0x06, 0x07):
            return 0
        elif port_lo == 0x08:
            self.banks[3] = ((port >> 8) & 0x7F) * 2048
            return 0
        elif port_lo == 0x09:
            self.banks[2] = ((port >> 8) & 0x3F) * 4096
            return 0
        elif port_lo == 0x0A:
            self.banks[1] = ((port >> 8) & 0x1F) * 8192
            return 0
        elif port_lo == 0x0B:
            self.banks[0] = ((port >> 8) & 0x0F) * 16384
            return 0
        return 0

    def port_write(self, port, val):
        port_lo = port & 0xFF
        if port_lo in (0x04, 0x05, 0x06, 0x07):
            self.ym_writes.append((self.cycles, port_lo, val))
            if self.trace_ym and port_lo in (0x05, 0x07):
                pair = 'A' if port_lo == 0x05 else 'B'
                print(f"  YM {pair}: reg 0x{self._ym_addr:02X} = 0x{val:02X}")
            if port_lo in (0x04, 0x06):
                self._ym_addr = val
        elif port_lo == 0x08:
            self.nmi_enabled = True
        elif port_lo == 0x0C:
            self.sound_reply = val
        elif port_lo == 0x18:
            self.nmi_enabled = False

    _ym_addr = 0

    def fire_nmi(self):
        if not self.nmi_enabled:
            return
        self.push(self.pc)
        self.pc = 0x0066
        self.iff2 = self.iff1
        self.iff1 = 0

    def fire_irq(self):
        if not self.iff1:
            return
        self.iff1 = self.iff2 = 0
        self.push(self.pc)
        if self.im == 1:
            self.pc = 0x0038

    def condition(self, cc):
        if cc == 0: return not self.get_flag(self.FLAG_Z)  # NZ
        if cc == 1: return self.get_flag(self.FLAG_Z)      # Z
        if cc == 2: return not self.get_flag(self.FLAG_C)  # NC
        if cc == 3: return self.get_flag(self.FLAG_C)      # C
        if cc == 4: return not self.get_flag(self.FLAG_PV) # PO
        if cc == 5: return self.get_flag(self.FLAG_PV)     # PE
        if cc == 6: return not self.get_flag(self.FLAG_S)  # P
        if cc == 7: return self.get_flag(self.FLAG_S)      # M
        return False

    def get_reg(self, r):
        return [self.b, self.c, self.d, self.e, self.h, self.l, self.mem_read(self.get_hl()), self.a][r]

    def set_reg(self, r, val):
        val &= 0xFF
        if r == 0: self.b = val
        elif r == 1: self.c = val
        elif r == 2: self.d = val
        elif r == 3: self.e = val
        elif r == 4: self.h = val
        elif r == 5: self.l = val
        elif r == 6: self.mem_write(self.get_hl(), val)
        elif r == 7: self.a = val

    def get_rp(self, rp):
        if rp == 0: return self.get_bc()
        if rp == 1: return self.get_de()
        if rp == 2: return self.get_hl()
        if rp == 3: return self.sp

    def set_rp(self, rp, val):
        val &= 0xFFFF
        if rp == 0: self.set_bc(val)
        elif rp == 1: self.set_de(val)
        elif rp == 2: self.set_hl(val)
        elif rp == 3: self.sp = val

    def step(self):
        if self.halted:
            self.cycles += 4
            return True

        pc0 = self.pc
        op = self.fetch()
        self.cycles += 4

        # --- Main opcode decode ---
        if op == 0x00: pass  # NOP
        elif op == 0x76: self.halted = True  # HALT
        elif op == 0xF3: self.iff1 = self.iff2 = 0  # DI
        elif op == 0xFB: self.iff1 = self.iff2 = 1  # EI

        # LD r, r'
        elif (op & 0xC0) == 0x40 and op != 0x76:
            dst = (op >> 3) & 7
            src = op & 7
            self.set_reg(dst, self.get_reg(src))

        # LD r, n
        elif (op & 0xC7) == 0x06:
            dst = (op >> 3) & 7
            self.set_reg(dst, self.fetch())

        # LD rp, nn
        elif (op & 0xCF) == 0x01:
            rp = (op >> 4) & 3
            self.set_rp(rp, self.fetch16())

        # LD (nn), A
        elif op == 0x32:
            self.mem_write(self.fetch16(), self.a)
        # LD A, (nn)
        elif op == 0x3A:
            self.a = self.mem_read(self.fetch16())
        # LD (nn), HL
        elif op == 0x22:
            self.mem_write16(self.fetch16(), self.get_hl())
        # LD HL, (nn)
        elif op == 0x2A:
            self.set_hl(self.mem_read16(self.fetch16()))

        # LD (BC), A
        elif op == 0x02: self.mem_write(self.get_bc(), self.a)
        # LD (DE), A
        elif op == 0x12: self.mem_write(self.get_de(), self.a)
        # LD A, (BC)
        elif op == 0x0A: self.a = self.mem_read(self.get_bc())
        # LD A, (DE)
        elif op == 0x1A: self.a = self.mem_read(self.get_de())

        # PUSH
        elif (op & 0xCF) == 0xC5:
            rp = (op >> 4) & 3
            if rp == 3: self.push((self.a << 8) | self.f)
            else: self.push(self.get_rp(rp))
        # POP
        elif (op & 0xCF) == 0xC1:
            rp = (op >> 4) & 3
            val = self.pop()
            if rp == 3: self.a = (val >> 8) & 0xFF; self.f = val & 0xFF
            else: self.set_rp(rp, val)

        # ADD A, r
        elif (op & 0xF8) == 0x80:
            r = op & 7
            v = self.get_reg(r)
            result = self.a + v
            self.a = self.update_flags_arith(self.a, v, result)
            self.set_flag(self.FLAG_C, result > 0xFF)
        # ADD A, n
        elif op == 0xC6:
            v = self.fetch()
            result = self.a + v
            self.a = self.update_flags_arith(self.a, v, result)
            self.set_flag(self.FLAG_C, result > 0xFF)

        # SUB r
        elif (op & 0xF8) == 0x90:
            r = op & 7
            v = self.get_reg(r)
            result = self.a - v
            self.a = self.update_flags_arith(self.a, v, result, sub=True)
            self.set_flag(self.FLAG_C, result < 0)
        # SUB n
        elif op == 0xD6:
            v = self.fetch()
            result = self.a - v
            self.a = self.update_flags_arith(self.a, v, result, sub=True)
            self.set_flag(self.FLAG_C, result < 0)

        # CP r
        elif (op & 0xF8) == 0xB8:
            r = op & 7
            v = self.get_reg(r)
            result = self.a - v
            self.update_flags_arith(self.a, v, result, sub=True)
            self.set_flag(self.FLAG_C, result < 0)
        # CP n
        elif op == 0xFE:
            v = self.fetch()
            result = self.a - v
            self.update_flags_arith(self.a, v, result, sub=True)
            self.set_flag(self.FLAG_C, result < 0)

        # AND r
        elif (op & 0xF8) == 0xA0:
            self.a = self.update_flags_logic(self.a & self.get_reg(op & 7))
            self.set_flag(self.FLAG_H, 1)
        # AND n
        elif op == 0xE6:
            self.a = self.update_flags_logic(self.a & self.fetch())
            self.set_flag(self.FLAG_H, 1)

        # OR r
        elif (op & 0xF8) == 0xB0:
            self.a = self.update_flags_logic(self.a | self.get_reg(op & 7))
        # OR n
        elif op == 0xF6:
            self.a = self.update_flags_logic(self.a | self.fetch())

        # XOR r
        elif (op & 0xF8) == 0xA8:
            self.a = self.update_flags_logic(self.a ^ self.get_reg(op & 7))
        # XOR n
        elif op == 0xEE:
            self.a = self.update_flags_logic(self.a ^ self.fetch())

        # INC r
        elif (op & 0xC7) == 0x04:
            r = (op >> 3) & 7
            v = (self.get_reg(r) + 1) & 0xFF
            self.set_flag(self.FLAG_Z, v == 0)
            self.set_flag(self.FLAG_S, v & 0x80)
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, (v & 0x0F) == 0)
            self.set_reg(r, v)
        # DEC r
        elif (op & 0xC7) == 0x05:
            r = (op >> 3) & 7
            v = (self.get_reg(r) - 1) & 0xFF
            self.set_flag(self.FLAG_Z, v == 0)
            self.set_flag(self.FLAG_S, v & 0x80)
            self.set_flag(self.FLAG_N, 1)
            self.set_flag(self.FLAG_H, (v & 0x0F) == 0x0F)
            self.set_reg(r, v)

        # INC rp
        elif (op & 0xCF) == 0x03:
            rp = (op >> 4) & 3
            self.set_rp(rp, (self.get_rp(rp) + 1) & 0xFFFF)
        # DEC rp
        elif (op & 0xCF) == 0x0B:
            rp = (op >> 4) & 3
            self.set_rp(rp, (self.get_rp(rp) - 1) & 0xFFFF)

        # ADD HL, rp
        elif (op & 0xCF) == 0x09:
            rp = (op >> 4) & 3
            hl = self.get_hl()
            v = self.get_rp(rp)
            result = hl + v
            self.set_flag(self.FLAG_C, result > 0xFFFF)
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, ((hl ^ v ^ result) >> 8) & 0x10)
            self.set_hl(result & 0xFFFF)

        # JP nn
        elif op == 0xC3:
            self.pc = self.fetch16()
        # JP cc, nn
        elif (op & 0xC7) == 0xC2:
            addr = self.fetch16()
            if self.condition((op >> 3) & 7):
                self.pc = addr
        # JP (HL)
        elif op == 0xE9:
            self.pc = self.get_hl()

        # JR e
        elif op == 0x18:
            e = self.fetch()
            if e > 127: e -= 256
            self.pc = (self.pc + e) & 0xFFFF
        # JR Z, e
        elif op == 0x28:
            e = self.fetch()
            if e > 127: e -= 256
            if self.get_flag(self.FLAG_Z):
                self.pc = (self.pc + e) & 0xFFFF
        # JR NZ, e
        elif op == 0x20:
            e = self.fetch()
            if e > 127: e -= 256
            if not self.get_flag(self.FLAG_Z):
                self.pc = (self.pc + e) & 0xFFFF
        # JR C, e
        elif op == 0x38:
            e = self.fetch()
            if e > 127: e -= 256
            if self.get_flag(self.FLAG_C):
                self.pc = (self.pc + e) & 0xFFFF
        # JR NC, e
        elif op == 0x30:
            e = self.fetch()
            if e > 127: e -= 256
            if not self.get_flag(self.FLAG_C):
                self.pc = (self.pc + e) & 0xFFFF

        # DJNZ e
        elif op == 0x10:
            e = self.fetch()
            if e > 127: e -= 256
            self.b = (self.b - 1) & 0xFF
            if self.b != 0:
                self.pc = (self.pc + e) & 0xFFFF

        # CALL nn
        elif op == 0xCD:
            addr = self.fetch16()
            self.push(self.pc)
            self.pc = addr
        # CALL cc, nn
        elif (op & 0xC7) == 0xC4:
            addr = self.fetch16()
            if self.condition((op >> 3) & 7):
                self.push(self.pc)
                self.pc = addr

        # RET
        elif op == 0xC9:
            self.pc = self.pop()
        # RET cc
        elif (op & 0xC7) == 0xC0:
            if self.condition((op >> 3) & 7):
                self.pc = self.pop()

        # RST
        elif (op & 0xC7) == 0xC7:
            self.push(self.pc)
            self.pc = op & 0x38

        # OUT (n), A
        elif op == 0xD3:
            port = self.fetch()
            self.port_write((self.a << 8) | port, self.a)
        # IN A, (n)
        elif op == 0xDB:
            port = self.fetch()
            self.a = self.port_read((self.a << 8) | port)

        # EX DE, HL
        elif op == 0xEB:
            de = self.get_de()
            self.set_de(self.get_hl())
            self.set_hl(de)
        # EX AF, AF'
        elif op == 0x08:
            self.a, self.a2 = self.a2, self.a
            self.f, self.f2 = self.f2, self.f
        # EXX
        elif op == 0xD9:
            self.b, self.b2 = self.b2, self.b
            self.c, self.c2 = self.c2, self.c
            self.d, self.d2 = self.d2, self.d
            self.e, self.e2 = self.e2, self.e
            self.h, self.h2 = self.h2, self.h
            self.l, self.l2 = self.l2, self.l
        # EX (SP), HL
        elif op == 0xE3:
            val = self.mem_read16(self.sp)
            self.mem_write16(self.sp, self.get_hl())
            self.set_hl(val)

        # RLCA
        elif op == 0x07:
            c = (self.a >> 7) & 1
            self.a = ((self.a << 1) | c) & 0xFF
            self.set_flag(self.FLAG_C, c)
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, 0)
        # RRCA
        elif op == 0x0F:
            c = self.a & 1
            self.a = ((self.a >> 1) | (c << 7)) & 0xFF
            self.set_flag(self.FLAG_C, c)
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, 0)
        # RLA
        elif op == 0x17:
            c = (self.a >> 7) & 1
            self.a = ((self.a << 1) | (1 if self.get_flag(self.FLAG_C) else 0)) & 0xFF
            self.set_flag(self.FLAG_C, c)
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, 0)
        # RRA
        elif op == 0x1F:
            c = self.a & 1
            self.a = ((self.a >> 1) | ((1 if self.get_flag(self.FLAG_C) else 0) << 7)) & 0xFF
            self.set_flag(self.FLAG_C, c)
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, 0)

        # SCF
        elif op == 0x37:
            self.set_flag(self.FLAG_C, 1)
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, 0)
        # CCF
        elif op == 0x3F:
            self.set_flag(self.FLAG_H, self.get_flag(self.FLAG_C))
            self.set_flag(self.FLAG_C, not self.get_flag(self.FLAG_C))
            self.set_flag(self.FLAG_N, 0)
        # CPL
        elif op == 0x2F:
            self.a = (~self.a) & 0xFF
            self.set_flag(self.FLAG_N, 1)
            self.set_flag(self.FLAG_H, 1)

        # ADC A, r
        elif (op & 0xF8) == 0x88:
            v = self.get_reg(op & 7)
            c = 1 if self.get_flag(self.FLAG_C) else 0
            result = self.a + v + c
            self.a = self.update_flags_arith(self.a, v, result)
            self.set_flag(self.FLAG_C, result > 0xFF)

        # SBC A, r
        elif (op & 0xF8) == 0x98:
            v = self.get_reg(op & 7)
            c = 1 if self.get_flag(self.FLAG_C) else 0
            result = self.a - v - c
            self.a = self.update_flags_arith(self.a, v, result, sub=True)
            self.set_flag(self.FLAG_C, result < 0)

        # LD SP, HL
        elif op == 0xF9:
            self.sp = self.get_hl()

        # CB prefix
        elif op == 0xCB:
            self._exec_cb()

        # DD prefix (IX)
        elif op == 0xDD:
            self._exec_dd()

        # FD prefix (IY)
        elif op == 0xFD:
            self._exec_fd()

        # ED prefix
        elif op == 0xED:
            self._exec_ed()

        else:
            if self.verbose:
                print(f"  UNIMPL opcode 0x{op:02X} at 0x{pc0:04X}")

        return True

    def _exec_cb(self):
        op = self.fetch()
        r = op & 7
        val = self.get_reg(r)

        if (op & 0xF8) == 0x00:  # RLC
            c = (val >> 7) & 1
            val = ((val << 1) | c) & 0xFF
            self.set_flag(self.FLAG_C, c)
        elif (op & 0xF8) == 0x08:  # RRC
            c = val & 1
            val = ((val >> 1) | (c << 7)) & 0xFF
            self.set_flag(self.FLAG_C, c)
        elif (op & 0xF8) == 0x10:  # RL
            c = (val >> 7) & 1
            val = ((val << 1) | (1 if self.get_flag(self.FLAG_C) else 0)) & 0xFF
            self.set_flag(self.FLAG_C, c)
        elif (op & 0xF8) == 0x18:  # RR
            c = val & 1
            val = ((val >> 1) | ((1 if self.get_flag(self.FLAG_C) else 0) << 7)) & 0xFF
            self.set_flag(self.FLAG_C, c)
        elif (op & 0xF8) == 0x20:  # SLA
            c = (val >> 7) & 1
            val = (val << 1) & 0xFF
            self.set_flag(self.FLAG_C, c)
        elif (op & 0xF8) == 0x28:  # SRA
            c = val & 1
            val = (val >> 1) | (val & 0x80)
            self.set_flag(self.FLAG_C, c)
        elif (op & 0xF8) == 0x38:  # SRL
            c = val & 1
            val = val >> 1
            self.set_flag(self.FLAG_C, c)
        elif (op & 0xC0) == 0x40:  # BIT
            bit = (op >> 3) & 7
            self.set_flag(self.FLAG_Z, not (val & (1 << bit)))
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, 1)
            return
        elif (op & 0xC0) == 0x80:  # RES
            bit = (op >> 3) & 7
            val &= ~(1 << bit)
        elif (op & 0xC0) == 0xC0:  # SET
            bit = (op >> 3) & 7
            val |= (1 << bit)

        self.set_flag(self.FLAG_Z, val == 0)
        self.set_flag(self.FLAG_S, val & 0x80)
        self.set_flag(self.FLAG_N, 0)
        self.set_reg(r, val)

    def _ix_iy_common(self, prefix_reg):
        op = self.fetch()

        if op == 0x21:  # LD IX/IY, nn
            val = self.fetch16()
            if prefix_reg == 'IX': self.ix = val
            else: self.iy = val
        elif op == 0x22:  # LD (nn), IX/IY
            addr = self.fetch16()
            val = self.ix if prefix_reg == 'IX' else self.iy
            self.mem_write16(addr, val)
        elif op == 0x2A:  # LD IX/IY, (nn)
            addr = self.fetch16()
            val = self.mem_read16(addr)
            if prefix_reg == 'IX': self.ix = val
            else: self.iy = val
        elif op == 0x36:  # LD (IX/IY+d), n
            d = self.fetch()
            if d > 127: d -= 256
            n = self.fetch()
            base = self.ix if prefix_reg == 'IX' else self.iy
            self.mem_write((base + d) & 0xFFFF, n)
        elif op == 0x46 or (op & 0xC7) == 0x46:  # LD r, (IX/IY+d)
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            val = self.mem_read((base + d) & 0xFFFF)
            r = (op >> 3) & 7
            self.set_reg(r, val)
        elif (op & 0xF8) == 0x70:  # LD (IX/IY+d), r
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            r = op & 7
            self.mem_write((base + d) & 0xFFFF, self.get_reg(r))
        elif op == 0x86:  # ADD A, (IX/IY+d)
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            v = self.mem_read((base + d) & 0xFFFF)
            result = self.a + v
            self.a = self.update_flags_arith(self.a, v, result)
            self.set_flag(self.FLAG_C, result > 0xFF)
        elif op == 0xBE:  # CP (IX/IY+d)
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            v = self.mem_read((base + d) & 0xFFFF)
            result = self.a - v
            self.update_flags_arith(self.a, v, result, sub=True)
            self.set_flag(self.FLAG_C, result < 0)
        elif op == 0xE1:  # POP IX/IY
            val = self.pop()
            if prefix_reg == 'IX': self.ix = val
            else: self.iy = val
        elif op == 0xE5:  # PUSH IX/IY
            val = self.ix if prefix_reg == 'IX' else self.iy
            self.push(val)
        elif op == 0x19:  # ADD IX/IY, DE
            base = self.ix if prefix_reg == 'IX' else self.iy
            result = base + self.get_de()
            self.set_flag(self.FLAG_C, result > 0xFFFF)
            self.set_flag(self.FLAG_N, 0)
            result &= 0xFFFF
            if prefix_reg == 'IX': self.ix = result
            else: self.iy = result
        elif op == 0x09:  # ADD IX/IY, BC
            base = self.ix if prefix_reg == 'IX' else self.iy
            result = base + self.get_bc()
            self.set_flag(self.FLAG_C, result > 0xFFFF)
            result &= 0xFFFF
            if prefix_reg == 'IX': self.ix = result
            else: self.iy = result
        elif op == 0xE9:  # JP (IX/IY)
            self.pc = self.ix if prefix_reg == 'IX' else self.iy
        elif op == 0xCB:  # DD CB / FD CB prefix
            d = self.fetch()
            if d > 127: d -= 256
            cb_op = self.fetch()
            base = self.ix if prefix_reg == 'IX' else self.iy
            addr = (base + d) & 0xFFFF
            val = self.mem_read(addr)
            if (cb_op & 0xC0) == 0x40:  # BIT
                bit = (cb_op >> 3) & 7
                self.set_flag(self.FLAG_Z, not (val & (1 << bit)))
                self.set_flag(self.FLAG_N, 0)
                self.set_flag(self.FLAG_H, 1)
            elif (cb_op & 0xC0) == 0x80:  # RES
                bit = (cb_op >> 3) & 7
                self.mem_write(addr, val & ~(1 << bit))
            elif (cb_op & 0xC0) == 0xC0:  # SET
                bit = (cb_op >> 3) & 7
                self.mem_write(addr, val | (1 << bit))
        elif op == 0x23:  # INC IX/IY
            if prefix_reg == 'IX': self.ix = (self.ix + 1) & 0xFFFF
            else: self.iy = (self.iy + 1) & 0xFFFF
        elif op == 0x2B:  # DEC IX/IY
            if prefix_reg == 'IX': self.ix = (self.ix - 1) & 0xFFFF
            else: self.iy = (self.iy - 1) & 0xFFFF
        elif op == 0x35:  # DEC (IX/IY+d)
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            addr = (base + d) & 0xFFFF
            v = (self.mem_read(addr) - 1) & 0xFF
            self.mem_write(addr, v)
            self.set_flag(self.FLAG_Z, v == 0)
            self.set_flag(self.FLAG_S, v & 0x80)
            self.set_flag(self.FLAG_N, 1)
        elif op == 0x34:  # INC (IX/IY+d)
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            addr = (base + d) & 0xFFFF
            v = (self.mem_read(addr) + 1) & 0xFF
            self.mem_write(addr, v)
            self.set_flag(self.FLAG_Z, v == 0)
            self.set_flag(self.FLAG_S, v & 0x80)
            self.set_flag(self.FLAG_N, 0)
        elif op == 0xF9:  # LD SP, IX/IY
            self.sp = self.ix if prefix_reg == 'IX' else self.iy
        elif op == 0x96:  # SUB (IX/IY+d)
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            v = self.mem_read((base + d) & 0xFFFF)
            result = self.a - v
            self.a = self.update_flags_arith(self.a, v, result, sub=True)
            self.set_flag(self.FLAG_C, result < 0)
        elif op == 0xA6:  # AND (IX/IY+d)
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            self.a = self.update_flags_logic(self.a & self.mem_read((base + d) & 0xFFFF))
            self.set_flag(self.FLAG_H, 1)
        elif op == 0xB6:  # OR (IX/IY+d)
            d = self.fetch()
            if d > 127: d -= 256
            base = self.ix if prefix_reg == 'IX' else self.iy
            self.a = self.update_flags_logic(self.a | self.mem_read((base + d) & 0xFFFF))
        else:
            if self.verbose:
                print(f"  UNIMPL {prefix_reg} opcode 0x{op:02X}")

    def _exec_dd(self):
        self._ix_iy_common('IX')

    def _exec_fd(self):
        self._ix_iy_common('IY')

    def _exec_ed(self):
        op = self.fetch()

        if op == 0x56:  # IM 1
            self.im = 1
        elif op == 0x46:  # IM 0
            self.im = 0
        elif op == 0x5E:  # IM 2
            self.im = 2
        elif op == 0x45 or op == 0x4D:  # RETN / RETI
            self.pc = self.pop()
            self.iff1 = self.iff2
        elif op == 0xB0:  # LDIR
            while True:
                val = self.mem_read(self.get_hl())
                self.mem_write(self.get_de(), val)
                self.set_hl((self.get_hl() + 1) & 0xFFFF)
                self.set_de((self.get_de() + 1) & 0xFFFF)
                self.set_bc((self.get_bc() - 1) & 0xFFFF)
                if self.get_bc() == 0:
                    break
            self.set_flag(self.FLAG_PV, 0)
            self.set_flag(self.FLAG_N, 0)
            self.set_flag(self.FLAG_H, 0)
        elif op == 0xA1:  # CPI
            val = self.mem_read(self.get_hl())
            result = self.a - val
            self.set_hl((self.get_hl() + 1) & 0xFFFF)
            self.set_bc((self.get_bc() - 1) & 0xFFFF)
            self.set_flag(self.FLAG_Z, (result & 0xFF) == 0)
            self.set_flag(self.FLAG_S, result & 0x80)
            self.set_flag(self.FLAG_N, 1)
            self.set_flag(self.FLAG_PV, self.get_bc() != 0)
        elif op == 0x52:  # SBC HL, DE
            hl = self.get_hl()
            de = self.get_de()
            c = 1 if self.get_flag(self.FLAG_C) else 0
            result = hl - de - c
            self.set_flag(self.FLAG_Z, (result & 0xFFFF) == 0)
            self.set_flag(self.FLAG_S, result & 0x8000)
            self.set_flag(self.FLAG_C, result < 0)
            self.set_flag(self.FLAG_N, 1)
            self.set_hl(result & 0xFFFF)
        elif op == 0x42:  # SBC HL, BC
            hl = self.get_hl()
            bc = self.get_bc()
            c = 1 if self.get_flag(self.FLAG_C) else 0
            result = hl - bc - c
            self.set_flag(self.FLAG_Z, (result & 0xFFFF) == 0)
            self.set_flag(self.FLAG_S, result & 0x8000)
            self.set_flag(self.FLAG_C, result < 0)
            self.set_flag(self.FLAG_N, 1)
            self.set_hl(result & 0xFFFF)
        elif op == 0x53:  # LD (nn), DE
            addr = self.fetch16()
            self.mem_write16(addr, self.get_de())
        elif op == 0x5B:  # LD DE, (nn)
            addr = self.fetch16()
            self.set_de(self.mem_read16(addr))
        elif op == 0x43:  # LD (nn), BC
            addr = self.fetch16()
            self.mem_write16(addr, self.get_bc())
        elif op == 0x4B:  # LD BC, (nn)
            addr = self.fetch16()
            self.set_bc(self.mem_read16(addr))
        elif op == 0x73:  # LD (nn), SP
            addr = self.fetch16()
            self.mem_write16(addr, self.sp)
        elif op == 0x7B:  # LD SP, (nn)
            addr = self.fetch16()
            self.sp = self.mem_read16(addr)
        elif op == 0x44:  # NEG
            result = -self.a
            self.set_flag(self.FLAG_C, self.a != 0)
            self.a = result & 0xFF
            self.set_flag(self.FLAG_Z, self.a == 0)
            self.set_flag(self.FLAG_S, self.a & 0x80)
            self.set_flag(self.FLAG_N, 1)
        elif op == 0x47:  # LD I, A
            self.i = self.a
        elif op == 0x57:  # LD A, I
            self.a = self.i
        elif op == 0x41:  # OUT (C), B
            self.port_write(self.get_bc(), self.b)
        elif op == 0x49:  # OUT (C), C
            self.port_write(self.get_bc(), self.c)
        elif op == 0x51:  # OUT (C), D
            self.port_write(self.get_bc(), self.d)
        elif op == 0x59:  # OUT (C), E
            self.port_write(self.get_bc(), self.e)
        elif op == 0x61:  # OUT (C), H
            self.port_write(self.get_bc(), self.h)
        elif op == 0x69:  # OUT (C), L
            self.port_write(self.get_bc(), self.l)
        elif op == 0x79:  # OUT (C), A
            self.port_write(self.get_bc(), self.a)
        elif op == 0x40:  # IN B, (C)
            self.b = self.port_read(self.get_bc())
        elif op == 0x48:  # IN C, (C)
            self.c = self.port_read(self.get_bc())
        elif op == 0x50:  # IN D, (C)
            self.d = self.port_read(self.get_bc())
        elif op == 0x58:  # IN E, (C)
            self.e = self.port_read(self.get_bc())
        elif op == 0x60:  # IN H, (C)
            self.h = self.port_read(self.get_bc())
        elif op == 0x68:  # IN L, (C)
            self.l = self.port_read(self.get_bc())
        elif op == 0x78:  # IN A, (C)
            self.a = self.port_read(self.get_bc())
        elif op == 0xA3:  # OUTI
            val = self.mem_read(self.get_hl())
            self.port_write(self.get_bc(), val)
            self.set_hl((self.get_hl() + 1) & 0xFFFF)
            self.b = (self.b - 1) & 0xFF
            self.set_flag(self.FLAG_Z, self.b == 0)
            self.set_flag(self.FLAG_N, 1)
        elif op == 0xB3:  # OTIR
            while True:
                val = self.mem_read(self.get_hl())
                self.port_write(self.get_bc(), val)
                self.set_hl((self.get_hl() + 1) & 0xFFFF)
                self.b = (self.b - 1) & 0xFF
                if self.b == 0:
                    break
            self.set_flag(self.FLAG_Z, 1)
            self.set_flag(self.FLAG_N, 1)
        else:
            if self.verbose:
                print(f"  UNIMPL ED opcode 0x{op:02X}")

    def is_main_loop(self, pc):
        """Detect if PC is at the KOF96 main loop (JP $0107 at $0112)."""
        # KOF96: main loop runs 0x0107-0x0114, JP 0x0107
        return pc == 0x0107 or pc == 0x0112

    def run_until_main_loop(self):
        """Run Z80 from reset until it reaches the main loop (init complete)."""
        self.pc = 0x0000
        count = 0
        seen_main = False
        while count < 500000:
            pc0 = self.pc
            self.step()
            count += 1
            if self.is_main_loop(pc0):
                if not seen_main:
                    print(f"Main loop reached at 0x{pc0:04X} after {count} instructions")
                    seen_main = True
                return True
            if self.halted:
                print(f"HALT at 0x{pc0:04X}")
                return True
        print(f"Did not reach main loop after {count} instructions")
        return False

    def simulate_song_command(self, cmd):
        """Simulate the 68K sending a sound command."""
        print(f"\n--- Sending command 0x{cmd:02X} ---")
        self.sound_code = cmd
        self.fire_nmi()

        # Run until main loop processes the command from ring buffer
        count = 0
        main_loop_hits = 0
        while count < 200000:
            pc0 = self.pc
            self.step()
            count += 1
            if self.is_main_loop(pc0):
                main_loop_hits += 1
                if main_loop_hits > 5:
                    print(f"Command processed in {count} instructions")
                    return True
        print(f"Command not processed after {count} instructions")
        return False

    def run_main_loop(self, max_iter=50000):
        """Run the main loop for a while, processing any queued commands."""
        count = 0
        while count < max_iter:
            pc0 = self.pc
            self.step()
            count += 1
            if self.is_main_loop(pc0):
                return count
        return -1

    def simulate_timer_tick(self):
        """Simulate one Timer A IRQ then let main loop run."""
        self.fire_irq()
        count = 0
        while count < 100000:
            pc0 = self.pc
            self.step()
            count += 1
            if self.is_main_loop(pc0):
                return count
        return -1


def main():
    parser = argparse.ArgumentParser(description='Z80 tracer for KOF96 sound driver')
    parser.add_argument('--mrom', default='examples/hello_neo/res/kof96_m1.bin')
    parser.add_argument('--cmd', default='0x21', help='Sound command to send (hex)')
    parser.add_argument('--ticks', type=int, default=50, help='Number of timer ticks')
    args = parser.parse_args()

    cmd = int(args.cmd, 16)

    z = Z80Tracer(args.mrom)
    z.trace_ym = False
    z.verbose = False

    print("=== Z80 Init ===")
    z.run_until_main_loop()
    print(f"YM writes during init: {len(z.ym_writes)}")

    # Simulate realistic execution: run instructions, periodically fire
    # NMI (for 68K commands) and IRQ (for timer ticks)
    z.iff1 = 1
    z.ym_writes.clear()

    # Send unlock (0x07) then song command via NMI
    commands = [0x07, cmd]
    cmd_idx = 0
    nmi_cooldown = 0
    irq_interval = 2000  # fire Timer A IRQ every N instructions
    irq_counter = 0
    tick_num = 0

    z.trace_ym = True
    total_steps = 0
    max_steps = args.ticks * irq_interval * 2

    print(f"\n=== Running: cmd 0x{cmd:02X}, {args.ticks} ticks ===")

    while total_steps < max_steps and tick_num < args.ticks:
        # Fire pending NMI
        if cmd_idx < len(commands) and nmi_cooldown <= 0:
            z.sound_code = commands[cmd_idx]
            z.fire_nmi()
            cmd_idx += 1
            nmi_cooldown = 500  # let it process

        # Fire Timer A IRQ periodically
        irq_counter += 1
        if irq_counter >= irq_interval and z.iff1:
            irq_counter = 0
            prev_writes = len(z.ym_writes)
            z.fire_irq()

            # Run IRQ handler to completion
            for _ in range(5000):
                z.step()
                total_steps += 1
                if z.is_main_loop(z.pc):
                    break

            new_writes = z.ym_writes[prev_writes:]
            # Filter to show only musically interesting writes
            note_writes = [w for w in new_writes if w[1] in (0x05, 0x07) and w[2] in
                          (0x28, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7)]
            if new_writes:
                # Check for key-on and frequency writes
                fm_notes = []
                for _, port, val in new_writes:
                    if port in (0x05, 0x07):
                        reg = z._ym_addr  # last address written
                fm_regs = {w[2]: None for w in new_writes if w[1] in (0x04, 0x06)}
                print(f"  Tick {tick_num}: {len(new_writes)} YM writes")

            tick_num += 1
            continue

        # Run one instruction
        z.step()
        total_steps += 1
        nmi_cooldown -= 1

    print(f"\nTotal: {total_steps} instructions, {len(z.ym_writes)} YM writes")

    # Print all YM writes grouped by tick
    print(f"\n=== All YM register writes ===")
    for cyc, port, val in z.ym_writes:
        pair = 'A' if port in (0x04, 0x05) else 'B'
        rw = 'addr' if port in (0x04, 0x06) else 'data'
        if rw == 'data':
            print(f"  cyc={cyc:6d} YM {pair} data=0x{val:02X}")


if __name__ == '__main__':
    main()
