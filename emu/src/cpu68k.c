#include "cpu68k.h"
#include "neogeo.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

cpu68k_t cpu;

/* ================================================================
   Helpers
   ================================================================ */

#define MASK8  0xFF
#define MASK16 0xFFFF
#define MASK32 0xFFFFFFFF

#define SIGN8(v)  ((int8_t)(v))
#define SIGN16(v) ((int16_t)(v))
#define SIGN32(v) ((int32_t)(v))

static inline uint16_t fetch16(void) {
    uint16_t v = mem_read16(cpu.pc & 0xFFFFFF);
    cpu.pc += 2;
    cpu.cycles += 4;
    return v;
}

static inline uint32_t fetch32(void) {
    uint16_t hi = fetch16();
    uint16_t lo = fetch16();
    return (hi << 16) | lo;
}

/* Condition codes */
static void set_flags_log8(uint8_t r) {
    cpu.sr &= ~(SR_N|SR_Z|SR_V|SR_C);
    if (r == 0) cpu.sr |= SR_Z;
    if (r & 0x80) cpu.sr |= SR_N;
}
static void set_flags_log16(uint16_t r) {
    cpu.sr &= ~(SR_N|SR_Z|SR_V|SR_C);
    if (r == 0) cpu.sr |= SR_Z;
    if (r & 0x8000) cpu.sr |= SR_N;
}
static void set_flags_log32(uint32_t r) {
    cpu.sr &= ~(SR_N|SR_Z|SR_V|SR_C);
    if (r == 0) cpu.sr |= SR_Z;
    if (r & 0x80000000) cpu.sr |= SR_N;
}

static void set_flags_add8(uint8_t s, uint8_t d, uint32_t r) {
    cpu.sr &= ~(SR_X|SR_N|SR_Z|SR_V|SR_C);
    uint8_t r8 = r;
    if (r8 == 0) cpu.sr |= SR_Z;
    if (r8 & 0x80) cpu.sr |= SR_N;
    if (r & 0x100) cpu.sr |= SR_C | SR_X;
    if ((~(s^d) & (r8^d)) & 0x80) cpu.sr |= SR_V;
}
static void set_flags_add16(uint16_t s, uint16_t d, uint32_t r) {
    cpu.sr &= ~(SR_X|SR_N|SR_Z|SR_V|SR_C);
    uint16_t r16 = r;
    if (r16 == 0) cpu.sr |= SR_Z;
    if (r16 & 0x8000) cpu.sr |= SR_N;
    if (r & 0x10000) cpu.sr |= SR_C | SR_X;
    if ((~(s^d) & (r16^d)) & 0x8000) cpu.sr |= SR_V;
}
static void set_flags_add32(uint32_t s, uint32_t d, uint64_t r) {
    cpu.sr &= ~(SR_X|SR_N|SR_Z|SR_V|SR_C);
    uint32_t r32 = r;
    if (r32 == 0) cpu.sr |= SR_Z;
    if (r32 & 0x80000000) cpu.sr |= SR_N;
    if (r & 0x100000000ULL) cpu.sr |= SR_C | SR_X;
    if ((~(s^d) & (r32^d)) & 0x80000000) cpu.sr |= SR_V;
}
static void set_flags_sub8(uint8_t s, uint8_t d, uint32_t r) {
    cpu.sr &= ~(SR_X|SR_N|SR_Z|SR_V|SR_C);
    uint8_t r8 = r;
    if (r8 == 0) cpu.sr |= SR_Z;
    if (r8 & 0x80) cpu.sr |= SR_N;
    if (r & 0x100) cpu.sr |= SR_C | SR_X;
    if (((s^d) & (r8^d)) & 0x80) cpu.sr |= SR_V;
}
static void set_flags_sub16(uint16_t s, uint16_t d, uint32_t r) {
    cpu.sr &= ~(SR_X|SR_N|SR_Z|SR_V|SR_C);
    uint16_t r16 = r;
    if (r16 == 0) cpu.sr |= SR_Z;
    if (r16 & 0x8000) cpu.sr |= SR_N;
    if (r & 0x10000) cpu.sr |= SR_C | SR_X;
    if (((s^d) & (r16^d)) & 0x8000) cpu.sr |= SR_V;
}
static void set_flags_sub32(uint32_t s, uint32_t d, uint64_t r) {
    cpu.sr &= ~(SR_X|SR_N|SR_Z|SR_V|SR_C);
    uint32_t r32 = r;
    if (r32 == 0) cpu.sr |= SR_Z;
    if (r32 & 0x80000000) cpu.sr |= SR_N;
    if (r & 0x100000000ULL) cpu.sr |= SR_C | SR_X;
    if (((s^d) & (r32^d)) & 0x80000000) cpu.sr |= SR_V;
}

static void set_flags_cmp8(uint8_t s, uint8_t d) {
    uint32_t r = (uint32_t)d - (uint32_t)s;
    set_flags_sub8(s, d, r);
}
static void set_flags_cmp16(uint16_t s, uint16_t d) {
    uint32_t r = (uint32_t)d - (uint32_t)s;
    set_flags_sub16(s, d, r);
}
static void set_flags_cmp32(uint32_t s, uint32_t d) {
    uint64_t r = (uint64_t)d - (uint64_t)s;
    set_flags_sub32(s, d, r);
}

/* ================================================================
   Effective Address resolution
   ================================================================ */

static uint32_t ea_addr(int mode, int reg, int size) {
    switch (mode) {
    case 2: return cpu.a[reg];
    case 5: return cpu.a[reg] + SIGN16(fetch16());
    case 6: {
        uint16_t ext = fetch16();
        int xreg = (ext >> 12) & 7;
        int32_t disp = SIGN8(ext & 0xFF);
        int32_t xval;
        if (ext & 0x8000)
            xval = (ext & 0x0800) ? (int32_t)cpu.a[xreg] : SIGN16(cpu.a[xreg] & 0xFFFF);
        else
            xval = (ext & 0x0800) ? (int32_t)cpu.d[xreg] : SIGN16(cpu.d[xreg] & 0xFFFF);
        return cpu.a[reg] + disp + xval;
    }
    case 7:
        switch (reg) {
        case 0: return SIGN16(fetch16());
        case 1: return fetch32();
        case 2: { uint32_t base = cpu.pc; return base + SIGN16(fetch16()); }
        case 3: {
            uint32_t base = cpu.pc;
            uint16_t ext = fetch16();
            int xreg = (ext >> 12) & 7;
            int32_t disp = SIGN8(ext & 0xFF);
            int32_t xval;
            if (ext & 0x8000)
                xval = (ext & 0x0800) ? (int32_t)cpu.a[xreg] : SIGN16(cpu.a[xreg] & 0xFFFF);
            else
                xval = (ext & 0x0800) ? (int32_t)cpu.d[xreg] : SIGN16(cpu.d[xreg] & 0xFFFF);
            return base + disp + xval;
        }
        }
        break;
    }
    return 0;
}

static int ea_inc_size(int size) {
    if (size == 0) return 2;
    if (size == 1) return 2;
    return 4;
}

static uint32_t ea_read(int mode, int reg, int size) {
    switch (mode) {
    case 0:
        if (size == 0) return cpu.d[reg] & 0xFF;
        if (size == 1) return cpu.d[reg] & 0xFFFF;
        return cpu.d[reg];
    case 1:
        if (size == 1) return cpu.a[reg] & 0xFFFF;
        return cpu.a[reg];
    case 3: {
        uint32_t a = cpu.a[reg];
        int inc = (size == 0) ? 1 : (size == 1) ? 2 : 4;
        if (size == 0 && reg == 7) inc = 2;
        cpu.a[reg] += inc;
        if (size == 0) return mem_read8(a);
        if (size == 1) return mem_read16(a);
        return mem_read32(a);
    }
    case 4: {
        int dec = (size == 0) ? 1 : (size == 1) ? 2 : 4;
        if (size == 0 && reg == 7) dec = 2;
        cpu.a[reg] -= dec;
        uint32_t a = cpu.a[reg];
        if (size == 0) return mem_read8(a);
        if (size == 1) return mem_read16(a);
        return mem_read32(a);
    }
    case 7:
        if (reg == 4) {
            if (size == 0) return fetch16() & 0xFF;
            if (size == 1) return fetch16();
            return fetch32();
        }
        /* fall through for abs/PC-relative */
    default: {
        uint32_t a = ea_addr(mode, reg, size);
        if (size == 0) return mem_read8(a);
        if (size == 1) return mem_read16(a);
        return mem_read32(a);
    }
    }
}

static void ea_write(int mode, int reg, int size, uint32_t val);

/* Read EA and save the resolved address for later write-back */
static uint32_t ea_saved_addr;

static uint32_t ea_read_rmw(int mode, int reg, int size) {
    if (mode == 0 || mode == 1) return ea_read(mode, reg, size);
    if (mode == 3 || mode == 4) return ea_read(mode, reg, size);
    if (mode == 7 && reg == 4) return ea_read(mode, reg, size);
    ea_saved_addr = ea_addr(mode, reg, size);
    if (size == 0) return mem_read8(ea_saved_addr);
    if (size == 1) return mem_read16(ea_saved_addr);
    return mem_read32(ea_saved_addr);
}

static void ea_write_rmw(int mode, int reg, int size, uint32_t val) {
    if (mode == 0 || mode == 1) { ea_write(mode, reg, size, val); return; }
    if (mode == 3 || mode == 4) { ea_write(mode, reg, size, val); return; }
    if (size == 0) mem_write8(ea_saved_addr, val);
    else if (size == 1) mem_write16(ea_saved_addr, val);
    else mem_write32(ea_saved_addr, val);
}

static void ea_write(int mode, int reg, int size, uint32_t val) {
    switch (mode) {
    case 0:
        if (size == 0) { cpu.d[reg] = (cpu.d[reg] & 0xFFFFFF00) | (val & 0xFF); return; }
        if (size == 1) { cpu.d[reg] = (cpu.d[reg] & 0xFFFF0000) | (val & 0xFFFF); return; }
        cpu.d[reg] = val; return;
    case 1:
        if (size == 1) cpu.a[reg] = SIGN16(val);
        else cpu.a[reg] = val;
        return;
    case 3: {
        int inc = (size == 0) ? 1 : (size == 1) ? 2 : 4;
        if (size == 0 && reg == 7) inc = 2;
        uint32_t a = cpu.a[reg];
        cpu.a[reg] += inc;
        if (size == 0) mem_write8(a, val);
        else if (size == 1) mem_write16(a, val);
        else mem_write32(a, val);
        return;
    }
    case 4: {
        int dec = (size == 0) ? 1 : (size == 1) ? 2 : 4;
        if (size == 0 && reg == 7) dec = 2;
        cpu.a[reg] -= dec;
        uint32_t a = cpu.a[reg];
        if (size == 0) mem_write8(a, val);
        else if (size == 1) mem_write16(a, val);
        else mem_write32(a, val);
        return;
    }
    default: {
        uint32_t a = ea_addr(mode, reg, size);
        if (size == 0) mem_write8(a, val);
        else if (size == 1) mem_write16(a, val);
        else mem_write32(a, val);
        return;
    }
    }
}

/* ================================================================
   Exception processing
   ================================================================ */

static void push32(uint32_t v) { cpu.a[7] -= 4; mem_write32(cpu.a[7], v); }
static void push16(uint16_t v) { cpu.a[7] -= 2; mem_write16(cpu.a[7], v); }

static void exception(int vector) {
    if (!(cpu.sr & SR_S)) {
        cpu.usp = cpu.a[7];
        cpu.a[7] = cpu.ssp;
    }
    push32(cpu.pc);
    push16(cpu.sr);
    cpu.sr |= SR_S;
    cpu.sr &= ~SR_T;
    cpu.pc = mem_read32(vector * 4);
    cpu.cycles += 34;
}

static int check_condition(int cc) {
    int c = cpu.sr & SR_C, v = cpu.sr & SR_V, z = cpu.sr & SR_Z, n = cpu.sr & SR_N;
    switch (cc) {
    case 0: return 1;                    /* T */
    case 1: return 0;                    /* F */
    case 2: return !c && !z;             /* HI */
    case 3: return c || z;               /* LS */
    case 4: return !c;                   /* CC */
    case 5: return c != 0;              /* CS */
    case 6: return !z;                   /* NE */
    case 7: return z != 0;              /* EQ */
    case 8: return !v;                   /* VC */
    case 9: return v != 0;              /* VS */
    case 10: return !n;                  /* PL */
    case 11: return n != 0;             /* MI */
    case 12: return (n&&v)||(!n&&!v);    /* GE */
    case 13: return (n&&!v)||(!n&&v);    /* LT */
    case 14: return (n&&v&&!z)||(!n&&!v&&!z); /* GT */
    case 15: return z||(n&&!v)||(!n&&v); /* LE */
    }
    return 0;
}

/* ================================================================
   Instruction execution
   ================================================================ */

uint32_t ppc[8]; int pi;
static void exception(int vector);
static void op_unimplemented(uint16_t op) {
    static int ulog;
    if (ulog < 5) {
        printf("ILLEGAL $%04X PC=$%06X → exception 4\n", op, cpu.pc-2);
        ulog++;
    }
    cpu.pc -= 2; /* back up to the illegal instruction */
    exception(4); /* illegal instruction exception */
}

static void execute_one(void) {
    uint16_t op = fetch16();
    int group = op >> 12;

    switch (group) {

    case 0x0: { /* ORI, ANDI, SUBI, ADDI, EORI, CMPI, BTST/BCHG/BCLR/BSET */
        int hi = (op >> 8) & 0xF;
        int mode = (op >> 3) & 7;
        int reg = op & 7;
        int size = (op >> 6) & 3;

        if (hi == 0x0 && size != 3) { /* ORI */
            uint32_t imm = (size==0) ? fetch16()&0xFF : (size==1) ? fetch16() : fetch32();
            if (mode == 7 && reg == 4) { /* ORI to CCR/SR */
                if (size == 0) cpu.sr |= (imm & 0x1F);
                else cpu.sr |= imm;
            } else {
                uint32_t d = ea_read_rmw(mode, reg, size);
                uint32_t r = d | imm;
                ea_write_rmw(mode, reg, size, r);
                if (size==0) set_flags_log8(r); else if (size==1) set_flags_log16(r); else set_flags_log32(r);
            }
        } else if (hi == 0x2 && size != 3) { /* ANDI */
            uint32_t imm = (size==0) ? fetch16()&0xFF : (size==1) ? fetch16() : fetch32();
            if (mode == 7 && reg == 4) {
                if (size == 0) cpu.sr &= (imm | 0xFFE0);
                else cpu.sr &= imm;
            } else {
                uint32_t d = ea_read_rmw(mode, reg, size);
                uint32_t r = d & imm;
                ea_write_rmw(mode, reg, size, r);
                if (size==0) set_flags_log8(r); else if (size==1) set_flags_log16(r); else set_flags_log32(r);
            }
        } else if (hi == 0x4 && size != 3) { /* SUBI */
            uint32_t imm = (size==0) ? fetch16()&0xFF : (size==1) ? fetch16() : fetch32();
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint64_t r = (uint64_t)d - (uint64_t)imm;
            ea_write_rmw(mode, reg, size, r);
            if (size==0) set_flags_sub8(imm,d,r); else if (size==1) set_flags_sub16(imm,d,r); else set_flags_sub32(imm,d,r);
        } else if (hi == 0x6 && size != 3) { /* ADDI */
            uint32_t imm = (size==0) ? fetch16()&0xFF : (size==1) ? fetch16() : fetch32();
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint64_t r = (uint64_t)d + (uint64_t)imm;
            ea_write_rmw(mode, reg, size, r);
            if (size==0) set_flags_add8(imm,d,r); else if (size==1) set_flags_add16(imm,d,r); else set_flags_add32(imm,d,r);
        } else if (hi == 0xA && size != 3) { /* EORI */
            uint32_t imm = (size==0) ? fetch16()&0xFF : (size==1) ? fetch16() : fetch32();
            if (mode == 7 && reg == 4) {
                if (size == 0) cpu.sr ^= (imm & 0x1F);
                else cpu.sr ^= imm;
            } else {
                uint32_t d = ea_read_rmw(mode, reg, size);
                uint32_t r = d ^ imm;
                ea_write_rmw(mode, reg, size, r);
                if (size==0) set_flags_log8(r); else if (size==1) set_flags_log16(r); else set_flags_log32(r);
            }
        } else if (hi == 0xC && size != 3) { /* CMPI */
            uint32_t imm = (size==0) ? fetch16()&0xFF : (size==1) ? fetch16() : fetch32();
            uint32_t d = ea_read_rmw(mode, reg, size);
            if (size==0) set_flags_cmp8(imm,d); else if (size==1) set_flags_cmp16(imm,d); else set_flags_cmp32(imm,d);
        } else if (hi == 0x8) { /* BTST/BCHG/BCLR/BSET (immediate) */
            int bit = fetch16() & (mode == 0 ? 31 : 7);
            int bop = (op >> 6) & 3;
            uint32_t d = ea_read(mode, reg, mode == 0 ? 2 : 0);
            cpu.sr = (cpu.sr & ~SR_Z) | ((d & (1 << bit)) ? 0 : SR_Z);
            if (bop == 1) d ^= (1 << bit);
            else if (bop == 2) d &= ~(1 << bit);
            else if (bop == 3) d |= (1 << bit);
            if (bop) ea_write(mode, reg, mode == 0 ? 2 : 0, d);
        } else if ((op & 0x0138) == 0x0108) { /* MOVEP */
            op_unimplemented(op);
        } else if (op & 0x0100) { /* BTST/BCHG/BCLR/BSET (register) */
            int breg = (op >> 9) & 7;
            int bit = cpu.d[breg] & (mode == 0 ? 31 : 7);
            int bop = (op >> 6) & 3;
            uint32_t d = ea_read(mode, reg, mode == 0 ? 2 : 0);
            cpu.sr = (cpu.sr & ~SR_Z) | ((d & (1 << bit)) ? 0 : SR_Z);
            if (bop == 1) d ^= (1 << bit);
            else if (bop == 2) d &= ~(1 << bit);
            else if (bop == 3) d |= (1 << bit);
            if (bop) ea_write(mode, reg, mode == 0 ? 2 : 0, d);
        } else {
            op_unimplemented(op);
        }
        break;
    }

    case 0x1: { /* MOVE.B */
        int dst_reg = (op >> 9) & 7;
        int dst_mode = (op >> 6) & 7;
        int src_mode = (op >> 3) & 7;
        int src_reg = op & 7;
        uint32_t val = ea_read(src_mode, src_reg, 0);
        set_flags_log8(val);
        ea_write(dst_mode, dst_reg, 0, val);
        break;
    }

    case 0x2: { /* MOVE.L / MOVEA.L */
        int dst_reg = (op >> 9) & 7;
        int dst_mode = (op >> 6) & 7;
        int src_mode = (op >> 3) & 7;
        int src_reg = op & 7;
        uint32_t val = ea_read(src_mode, src_reg, 2);
        if (dst_mode == 1) {
            cpu.a[dst_reg] = val;
        } else {
            set_flags_log32(val);
            ea_write(dst_mode, dst_reg, 2, val);
        }
        break;
    }

    case 0x3: { /* MOVE.W / MOVEA.W */
        int dst_reg = (op >> 9) & 7;
        int dst_mode = (op >> 6) & 7;
        int src_mode = (op >> 3) & 7;
        int src_reg = op & 7;
        uint32_t val = ea_read(src_mode, src_reg, 1);
        if (dst_mode == 1) {
            cpu.a[dst_reg] = SIGN16(val);
        } else {
            set_flags_log16(val);
            ea_write(dst_mode, dst_reg, 1, val);
        }
        break;
    }

    case 0x4: { /* Misc: CLR, NEG, NOT, TST, LEA, PEA, JSR, JMP, RTS, RTE, NOP, MOVEM, SWAP, EXT, TRAP, LINK, UNLK, MOVE SR/CCR */
        int mode = (op >> 3) & 7;
        int reg = op & 7;

        if (op == 0x4E71) { /* NOP */
            break;
        } else if (op == 0x4E72) { /* STOP #xxxx */
            cpu.sr = fetch16();
            cpu.stopped = 1;
        } else if (op == 0x4E75) { /* RTS */
            cpu.pc = mem_read32(cpu.a[7]); cpu.a[7] += 4;
        } else if (op == 0x4E73) { /* RTE */
            cpu.sr = mem_read16(cpu.a[7]); cpu.a[7] += 2;
            cpu.pc = mem_read32(cpu.a[7]); cpu.a[7] += 4;
            if (!(cpu.sr & SR_S)) { cpu.ssp = cpu.a[7]; cpu.a[7] = cpu.usp; }
        } else if (op == 0x4E77) { /* RTR */
            cpu.sr = (cpu.sr & 0xFF00) | (mem_read16(cpu.a[7]) & 0xFF); cpu.a[7] += 2;
            cpu.pc = mem_read32(cpu.a[7]); cpu.a[7] += 4;
        } else if ((op & 0xFFF0) == 0x4E40) { /* TRAP */
            exception(32 + (op & 0xF));
        } else if ((op & 0xFFF0) == 0x4E50) { /* LINK */
            push32(cpu.a[reg]);
            cpu.a[reg] = cpu.a[7];
            cpu.a[7] += SIGN16(fetch16());
        } else if ((op & 0xFFF0) == 0x4E58) { /* UNLK */
            cpu.a[7] = cpu.a[reg];
            cpu.a[reg] = mem_read32(cpu.a[7]); cpu.a[7] += 4;
        } else if ((op & 0xFFF0) == 0x4E60) { /* MOVE USP */
            if (op & 8) cpu.a[reg] = cpu.usp;
            else cpu.usp = cpu.a[reg];
        } else if ((op & 0xFFC0) == 0x4E80) { /* JSR */
            uint32_t a = ea_addr(mode, reg, 0);
            push32(cpu.pc);
            cpu.pc = a;
        } else if ((op & 0xFFC0) == 0x4EC0) { /* JMP */
            cpu.pc = ea_addr(mode, reg, 0);
        } else if ((op & 0xF1C0) == 0x41C0) { /* LEA */
            int areg = (op >> 9) & 7;
            cpu.a[areg] = ea_addr(mode, reg, 0);
        } else if ((op & 0xFFF8) == 0x4840) { /* SWAP */
            uint32_t v = cpu.d[reg];
            cpu.d[reg] = (v >> 16) | (v << 16);
            set_flags_log32(cpu.d[reg]);
        } else if ((op & 0xFFC0) == 0x4840 && mode >= 2) { /* PEA */
            push32(ea_addr(mode, reg, 0));
        } else if ((op & 0xFFC0) == 0x4AC0) { /* TAS */
            uint32_t d = ea_read(mode, reg, 0);
            set_flags_log8(d);
            ea_write(mode, reg, 0, d | 0x80);
        } else if ((op & 0xFFC0) == 0x40C0) { /* MOVE SR to EA */
            ea_write(mode, reg, 1, cpu.sr);
        } else if ((op & 0xFFC0) == 0x44C0) { /* MOVE to CCR */
            cpu.sr = (cpu.sr & 0xFF00) | (ea_read(mode, reg, 1) & 0xFF);
        } else if ((op & 0xFFC0) == 0x46C0) { /* MOVE to SR */
            uint16_t old = cpu.sr;
            cpu.sr = ea_read(mode, reg, 1);
            if ((old & SR_S) && !(cpu.sr & SR_S)) { cpu.ssp = cpu.a[7]; cpu.a[7] = cpu.usp; }
            if (!(old & SR_S) && (cpu.sr & SR_S)) { cpu.usp = cpu.a[7]; cpu.a[7] = cpu.ssp; }
        } else if ((op & 0xFF00) == 0x4200) { /* CLR */
            int size = (op >> 6) & 3;
            ea_write(mode, reg, size, 0);
            cpu.sr = (cpu.sr & ~(SR_N|SR_V|SR_C)) | SR_Z;
        } else if ((op & 0xFF00) == 0x4400) { /* NEG */
            int size = (op >> 6) & 3;
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint64_t r = 0 - (uint64_t)d;
            ea_write_rmw(mode, reg, size, r);
            if (size==0) set_flags_sub8(d,0,r); else if (size==1) set_flags_sub16(d,0,r); else set_flags_sub32(d,0,r);
        } else if ((op & 0xFF00) == 0x4600) { /* NOT */
            int size = (op >> 6) & 3;
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint32_t r = ~d;
            ea_write_rmw(mode, reg, size, r);
            if (size==0) set_flags_log8(r); else if (size==1) set_flags_log16(r); else set_flags_log32(r);
        } else if ((op & 0xFF00) == 0x4A00) { /* TST */
            int size = (op >> 6) & 3;
            uint32_t d = ea_read_rmw(mode, reg, size);
            if (size==0) set_flags_log8(d); else if (size==1) set_flags_log16(d); else set_flags_log32(d);
        } else if ((op & 0xFB80) == 0x4880) { /* MOVEM */
            int dir = (op >> 10) & 1;
            int sz = (op >> 6) & 1;
            int inc = sz ? 4 : 2;
            uint16_t mask = fetch16();
            if (dir == 0) { /* register to memory */
                if (mode == 4) { /* predecrement */
                    for (int i = 15; i >= 0; i--) {
                        if (mask & (1 << i)) {
                            cpu.a[reg] -= inc;
                            if (sz) mem_write32(cpu.a[reg], i < 8 ? cpu.d[i] : cpu.a[i-8]);
                            else mem_write16(cpu.a[reg], i < 8 ? cpu.d[i] : cpu.a[i-8]);
                        }
                    }
                } else {
                    uint32_t a = ea_addr(mode, reg, 0);
                    for (int i = 0; i < 16; i++) {
                        if (mask & (1 << i)) {
                            if (sz) mem_write32(a, i < 8 ? cpu.d[i] : cpu.a[i-8]);
                            else mem_write16(a, i < 8 ? cpu.d[i] : cpu.a[i-8]);
                            a += inc;
                        }
                    }
                }
            } else { /* memory to register */
                uint32_t a = (mode == 3) ? cpu.a[reg] : ea_addr(mode, reg, 0);
                for (int i = 0; i < 16; i++) {
                    if (mask & (1 << i)) {
                        uint32_t v = sz ? mem_read32(a) : SIGN16(mem_read16(a));
                        if (i < 8) cpu.d[i] = v; else cpu.a[i-8] = v;
                        a += inc;
                    }
                }
                if (mode == 3) cpu.a[reg] = a;
            }
        } else if ((op & 0xFFF8) == 0x4880) { /* EXT.W */
            cpu.d[reg] = (cpu.d[reg] & 0xFFFF0000) | (uint16_t)(int16_t)(int8_t)(cpu.d[reg] & 0xFF);
            set_flags_log16(cpu.d[reg]);
        } else if ((op & 0xFFF8) == 0x48C0) { /* EXT.L */
            cpu.d[reg] = (int32_t)(int16_t)(cpu.d[reg] & 0xFFFF);
            set_flags_log32(cpu.d[reg]);
        } else if ((op & 0xFF00) == 0x4000) { /* NEGX */
            int size = (op >> 6) & 3;
            uint32_t d = ea_read_rmw(mode, reg, size);
            int x = (cpu.sr & SR_X) ? 1 : 0;
            uint64_t r = 0 - (uint64_t)d - x;
            ea_write_rmw(mode, reg, size, r);
            if (size==0) set_flags_sub8(d,0,r); else if (size==1) set_flags_sub16(d,0,r); else set_flags_sub32(d,0,r);
            if ((size==0 && (r&0xFF)) || (size==1 && (r&0xFFFF)) || (size==2 && (r&0xFFFFFFFF)))
                cpu.sr &= ~SR_Z;
        } else {
            op_unimplemented(op);
        }
        break;
    }

    case 0x5: { /* ADDQ / SUBQ / Scc / DBcc */
        int mode = (op >> 3) & 7;
        int reg = op & 7;
        int size = (op >> 6) & 3;
        int data = (op >> 9) & 7; if (data == 0) data = 8;

        if (size == 3) { /* Scc / DBcc */
            int cc = (op >> 8) & 0xF;
            if (mode == 1) { /* DBcc */
                if (!check_condition(cc)) {
                    int16_t disp = SIGN16(fetch16());
                    uint16_t cnt = (cpu.d[reg] & 0xFFFF) - 1;
                    cpu.d[reg] = (cpu.d[reg] & 0xFFFF0000) | cnt;
                    if (cnt != 0xFFFF) cpu.pc = cpu.pc - 2 + disp;
                } else {
                    cpu.pc += 2;
                }
            } else { /* Scc */
                ea_write(mode, reg, 0, check_condition(cc) ? 0xFF : 0x00);
            }
        } else if (op & 0x0100) { /* SUBQ */
            if (mode == 1) {
                cpu.a[reg] -= data;
            } else {
                uint32_t d = ea_read_rmw(mode, reg, size);
                uint64_t r = (uint64_t)d - data;
                ea_write_rmw(mode, reg, size, r);
                if (size==0) set_flags_sub8(data,d,r); else if (size==1) set_flags_sub16(data,d,r); else set_flags_sub32(data,d,r);
            }
        } else { /* ADDQ */
            if (mode == 1) {
                cpu.a[reg] += data;
            } else {
                uint32_t d = ea_read_rmw(mode, reg, size);
                uint64_t r = (uint64_t)d + data;
                ea_write_rmw(mode, reg, size, r);
                if (size==0) set_flags_add8(data,d,r); else if (size==1) set_flags_add16(data,d,r); else set_flags_add32(data,d,r);
            }
        }
        break;
    }

    case 0x6: { /* Bcc / BSR / BRA */
        int cc = (op >> 8) & 0xF;
        int8_t disp8 = op & 0xFF;
        uint32_t base = cpu.pc;  /* PC after opcode fetch = instruction + 2 */
        int32_t disp;
        if (disp8 == 0) { disp = SIGN16(fetch16()); }
        else if (disp8 == -1) { disp = (int32_t)fetch32(); }
        else { disp = disp8; }
        uint32_t target = base + disp;

        if (cc == 1) { /* BSR */
            push32(cpu.pc);
            cpu.pc = target;
        } else if (cc == 0) { /* BRA */
            cpu.pc = target;
        } else {
            if (check_condition(cc)) cpu.pc = target;
        }
        break;
    }

    case 0x7: { /* MOVEQ */
        int dreg = (op >> 9) & 7;
        cpu.d[dreg] = SIGN8(op & 0xFF);
        set_flags_log32(cpu.d[dreg]);
        break;
    }

    case 0x8: { /* OR / DIVU / DIVS */
        int dreg = (op >> 9) & 7;
        int mode = (op >> 3) & 7;
        int reg = op & 7;
        int size = (op >> 6) & 3;
        int dir = (op >> 8) & 1;

        if (size == 3) { /* DIVU/DIVS */
            uint32_t src = ea_read(mode, reg, 1);
            if (src == 0) { exception(5); break; }
            if (op & 0x0100) { /* DIVS */
                int32_t dd = (int32_t)cpu.d[dreg];
                int16_t ss = (int16_t)src;
                int32_t quot = dd / ss;
                int16_t rem = dd % ss;
                if (quot < -32768 || quot > 32767) { cpu.sr |= SR_V; }
                else { cpu.d[dreg] = ((uint16_t)rem << 16) | ((uint16_t)quot); cpu.sr &= ~SR_V; set_flags_log16(quot); }
            } else { /* DIVU */
                uint32_t dd = cpu.d[dreg];
                uint16_t ss = src;
                uint32_t quot = dd / ss;
                uint16_t rem = dd % ss;
                if (quot > 0xFFFF) { cpu.sr |= SR_V; }
                else { cpu.d[dreg] = (rem << 16) | (quot & 0xFFFF); cpu.sr &= ~SR_V; set_flags_log16(quot); }
            }
            cpu.sr &= ~SR_C;
        } else if (dir) { /* OR Dn,<ea> */
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint32_t r = d | cpu.d[dreg];
            ea_write_rmw(mode, reg, size, r);
            if (size==0) set_flags_log8(r); else if (size==1) set_flags_log16(r); else set_flags_log32(r);
        } else { /* OR <ea>,Dn */
            uint32_t s = ea_read_rmw(mode, reg, size);
            uint32_t r = cpu.d[dreg] | s;
            if (size==0) { cpu.d[dreg]=(cpu.d[dreg]&0xFFFFFF00)|(r&0xFF); set_flags_log8(r); }
            else if (size==1) { cpu.d[dreg]=(cpu.d[dreg]&0xFFFF0000)|(r&0xFFFF); set_flags_log16(r); }
            else { cpu.d[dreg]=r; set_flags_log32(r); }
        }
        break;
    }

    case 0x9: { /* SUB / SUBA */
        int dreg = (op >> 9) & 7;
        int mode = (op >> 3) & 7;
        int reg = op & 7;
        int size = (op >> 6) & 3;
        int dir = (op >> 8) & 1;

        if (size == 3) { /* SUBA */
            int sz = dir ? 2 : 1;
            uint32_t s = ea_read(mode, reg, sz);
            if (sz == 1) s = SIGN16(s);
            cpu.a[dreg] -= s;
        } else if (dir && mode <= 1) { /* SUBX */
            int x = (cpu.sr & SR_X) ? 1 : 0;
            uint32_t s, d;
            if (mode == 0) { s = cpu.d[reg]; d = cpu.d[dreg]; }
            else { int inc = (size==0)?1:(size==1)?2:4; cpu.a[reg]-=inc; s=size==0?mem_read8(cpu.a[reg]):size==1?mem_read16(cpu.a[reg]):mem_read32(cpu.a[reg]); cpu.a[dreg]-=inc; d=size==0?mem_read8(cpu.a[dreg]):size==1?mem_read16(cpu.a[dreg]):mem_read32(cpu.a[dreg]); }
            uint64_t r = (uint64_t)d - (uint64_t)s - x;
            if (mode == 0) { if(size==0) cpu.d[dreg]=(cpu.d[dreg]&0xFFFFFF00)|(r&0xFF); else if(size==1) cpu.d[dreg]=(cpu.d[dreg]&0xFFFF0000)|(r&0xFFFF); else cpu.d[dreg]=r; }
            else { if(size==0) mem_write8(cpu.a[dreg],r); else if(size==1) mem_write16(cpu.a[dreg],r); else mem_write32(cpu.a[dreg],r); }
            if(size==0) set_flags_sub8(s,d,r); else if(size==1) set_flags_sub16(s,d,r); else set_flags_sub32(s,d,r);
            if ((size==0&&(r&0xFF))||(size==1&&(r&0xFFFF))||(size==2&&(r&0xFFFFFFFF))) cpu.sr&=~SR_Z;
        } else if (dir) { /* SUB Dn,<ea> */
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint64_t r = (uint64_t)d - cpu.d[dreg];
            ea_write_rmw(mode, reg, size, r);
            if(size==0) set_flags_sub8(cpu.d[dreg],d,r); else if(size==1) set_flags_sub16(cpu.d[dreg],d,r); else set_flags_sub32(cpu.d[dreg],d,r);
        } else { /* SUB <ea>,Dn */
            uint32_t s = ea_read_rmw(mode, reg, size);
            uint64_t r = (uint64_t)cpu.d[dreg] - (uint64_t)s;
            if(size==0) { set_flags_sub8(s,cpu.d[dreg],r); cpu.d[dreg]=(cpu.d[dreg]&0xFFFFFF00)|(r&0xFF); }
            else if(size==1) { set_flags_sub16(s,cpu.d[dreg],r); cpu.d[dreg]=(cpu.d[dreg]&0xFFFF0000)|(r&0xFFFF); }
            else { set_flags_sub32(s,cpu.d[dreg],r); cpu.d[dreg]=r; }
        }
        break;
    }

    case 0xA: /* Line A */
        exception(10);
        break;

    case 0xB: { /* CMP / CMPA / EOR */
        int dreg = (op >> 9) & 7;
        int mode = (op >> 3) & 7;
        int reg = op & 7;
        int size = (op >> 6) & 3;
        int dir = (op >> 8) & 1;

        if (size == 3) { /* CMPA */
            int sz = dir ? 2 : 1;
            uint32_t s = ea_read(mode, reg, sz);
            if (sz == 1) s = SIGN16(s);
            set_flags_cmp32(s, cpu.a[dreg]);
        } else if (dir && mode == 1) { /* CMPM */
            int inc = (size==0)?1:(size==1)?2:4;
            uint32_t s = size==0?mem_read8(cpu.a[reg]):size==1?mem_read16(cpu.a[reg]):mem_read32(cpu.a[reg]); cpu.a[reg]+=inc;
            uint32_t d = size==0?mem_read8(cpu.a[dreg]):size==1?mem_read16(cpu.a[dreg]):mem_read32(cpu.a[dreg]); cpu.a[dreg]+=inc;
            if(size==0) set_flags_cmp8(s,d); else if(size==1) set_flags_cmp16(s,d); else set_flags_cmp32(s,d);
        } else if (dir) { /* EOR */
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint32_t r = d ^ cpu.d[dreg];
            ea_write_rmw(mode, reg, size, r);
            if(size==0) set_flags_log8(r); else if(size==1) set_flags_log16(r); else set_flags_log32(r);
        } else { /* CMP */
            uint32_t s = ea_read_rmw(mode, reg, size);
            if(size==0) set_flags_cmp8(s, cpu.d[dreg]); else if(size==1) set_flags_cmp16(s, cpu.d[dreg]); else set_flags_cmp32(s, cpu.d[dreg]);
        }
        break;
    }

    case 0xC: { /* AND / MULU / MULS / EXG */
        int dreg = (op >> 9) & 7;
        int mode = (op >> 3) & 7;
        int reg = op & 7;
        int size = (op >> 6) & 3;
        int dir = (op >> 8) & 1;

        if (size == 3) { /* MULU/MULS */
            uint32_t s = ea_read(mode, reg, 1);
            if (op & 0x0100) {
                cpu.d[dreg] = (int32_t)(int16_t)(cpu.d[dreg]&0xFFFF) * (int32_t)(int16_t)s;
            } else {
                cpu.d[dreg] = (uint32_t)(cpu.d[dreg]&0xFFFF) * (uint32_t)(s&0xFFFF);
            }
            set_flags_log32(cpu.d[dreg]);
            cpu.sr &= ~(SR_V|SR_C);
        } else if ((op & 0xF1F8) == 0xC140) { /* EXG Dx,Dy */
            uint32_t t = cpu.d[dreg]; cpu.d[dreg] = cpu.d[reg]; cpu.d[reg] = t;
        } else if ((op & 0xF1F8) == 0xC148) { /* EXG Ax,Ay */
            uint32_t t = cpu.a[dreg]; cpu.a[dreg] = cpu.a[reg]; cpu.a[reg] = t;
        } else if ((op & 0xF1F8) == 0xC188) { /* EXG Dx,Ay */
            uint32_t t = cpu.d[dreg]; cpu.d[dreg] = cpu.a[reg]; cpu.a[reg] = t;
        } else if (dir) { /* AND Dn,<ea> */
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint32_t r = d & cpu.d[dreg];
            ea_write_rmw(mode, reg, size, r);
            if(size==0) set_flags_log8(r); else if(size==1) set_flags_log16(r); else set_flags_log32(r);
        } else { /* AND <ea>,Dn */
            uint32_t s = ea_read_rmw(mode, reg, size);
            uint32_t r = cpu.d[dreg] & s;
            if(size==0) { cpu.d[dreg]=(cpu.d[dreg]&0xFFFFFF00)|(r&0xFF); set_flags_log8(r); }
            else if(size==1) { cpu.d[dreg]=(cpu.d[dreg]&0xFFFF0000)|(r&0xFFFF); set_flags_log16(r); }
            else { cpu.d[dreg]=r; set_flags_log32(r); }
        }
        break;
    }

    case 0xD: { /* ADD / ADDA */
        int dreg = (op >> 9) & 7;
        int mode = (op >> 3) & 7;
        int reg = op & 7;
        int size = (op >> 6) & 3;
        int dir = (op >> 8) & 1;

        if (size == 3) { /* ADDA */
            int sz = dir ? 2 : 1;
            uint32_t s = ea_read(mode, reg, sz);
            if (sz == 1) s = SIGN16(s);
            cpu.a[dreg] += s;
        } else if (dir && mode <= 1) { /* ADDX */
            int x = (cpu.sr & SR_X) ? 1 : 0;
            uint32_t s, d;
            if (mode == 0) { s = cpu.d[reg]; d = cpu.d[dreg]; }
            else { int inc=(size==0)?1:(size==1)?2:4; cpu.a[reg]-=inc; s=size==0?mem_read8(cpu.a[reg]):size==1?mem_read16(cpu.a[reg]):mem_read32(cpu.a[reg]); cpu.a[dreg]-=inc; d=size==0?mem_read8(cpu.a[dreg]):size==1?mem_read16(cpu.a[dreg]):mem_read32(cpu.a[dreg]); }
            uint64_t r = (uint64_t)d + (uint64_t)s + x;
            if (mode==0) { if(size==0) cpu.d[dreg]=(cpu.d[dreg]&0xFFFFFF00)|(r&0xFF); else if(size==1) cpu.d[dreg]=(cpu.d[dreg]&0xFFFF0000)|(r&0xFFFF); else cpu.d[dreg]=r; }
            else { if(size==0) mem_write8(cpu.a[dreg],r); else if(size==1) mem_write16(cpu.a[dreg],r); else mem_write32(cpu.a[dreg],r); }
            if(size==0) set_flags_add8(s,d,r); else if(size==1) set_flags_add16(s,d,r); else set_flags_add32(s,d,r);
            if ((size==0&&(r&0xFF))||(size==1&&(r&0xFFFF))||(size==2&&(r&0xFFFFFFFF))) cpu.sr&=~SR_Z;
        } else if (dir) { /* ADD Dn,<ea> */
            uint32_t d = ea_read_rmw(mode, reg, size);
            uint64_t r = (uint64_t)d + cpu.d[dreg];
            ea_write_rmw(mode, reg, size, r);
            if(size==0) set_flags_add8(cpu.d[dreg],d,r); else if(size==1) set_flags_add16(cpu.d[dreg],d,r); else set_flags_add32(cpu.d[dreg],d,r);
        } else { /* ADD <ea>,Dn */
            uint32_t s = ea_read_rmw(mode, reg, size);
            uint64_t r = (uint64_t)cpu.d[dreg] + s;
            if(size==0) { set_flags_add8(s,cpu.d[dreg],r); cpu.d[dreg]=(cpu.d[dreg]&0xFFFFFF00)|(r&0xFF); }
            else if(size==1) { set_flags_add16(s,cpu.d[dreg],r); cpu.d[dreg]=(cpu.d[dreg]&0xFFFF0000)|(r&0xFFFF); }
            else { set_flags_add32(s,cpu.d[dreg],r); cpu.d[dreg]=r; }
        }
        break;
    }

    case 0xE: { /* Shift/Rotate */
        int dreg = (op >> 9) & 7;
        int reg = op & 7;
        int size = (op >> 6) & 3;
        int dir = (op >> 8) & 1; /* 0=right, 1=left */
        int ir = (op >> 5) & 1;  /* 0=count in field, 1=count in register */
        int type = (op >> 3) & 3;

        if (size == 3) { /* memory shift (1-bit) */
            uint32_t a = ea_addr((op>>3)&7, reg, 1);
            uint16_t d = mem_read16(a);
            int cnt = 1;
            cpu.sr &= ~(SR_V);
            if (type == 0) { /* ASR/ASL */
                if (dir) { cpu.sr = (cpu.sr&~(SR_C|SR_X)) | ((d&0x8000)?SR_C|SR_X:0); d <<= 1; }
                else { cpu.sr = (cpu.sr&~(SR_C|SR_X)) | ((d&1)?SR_C|SR_X:0); d = (int16_t)d >> 1; }
            } else if (type == 1) { /* LSR/LSL */
                if (dir) { cpu.sr = (cpu.sr&~(SR_C|SR_X)) | ((d&0x8000)?SR_C|SR_X:0); d <<= 1; }
                else { cpu.sr = (cpu.sr&~(SR_C|SR_X)) | ((d&1)?SR_C|SR_X:0); d >>= 1; }
            } else if (type == 2) { /* ROXR/ROXL */
                int x = (cpu.sr & SR_X) ? 1 : 0;
                if (dir) { cpu.sr = (cpu.sr&~(SR_C|SR_X)) | ((d&0x8000)?SR_C|SR_X:0); d = (d<<1)|x; }
                else { cpu.sr = (cpu.sr&~(SR_C|SR_X)) | ((d&1)?SR_C|SR_X:0); d = (d>>1)|(x<<15); }
            } else { /* ROR/ROL */
                if (dir) { cpu.sr = (cpu.sr&~SR_C) | ((d&0x8000)?SR_C:0); d = (d<<1)|(d>>15); }
                else { cpu.sr = (cpu.sr&~SR_C) | ((d&1)?SR_C:0); d = (d>>1)|(d<<15); }
            }
            mem_write16(a, d);
            set_flags_log16(d);
            if (cpu.sr & SR_C) cpu.sr |= SR_C; /* keep C from shift */
        } else { /* register shift */
            int cnt = ir ? (cpu.d[dreg] & 63) : (dreg == 0 ? 8 : dreg);
            uint32_t d;
            uint32_t msb;
            if (size == 0) { d = cpu.d[reg] & 0xFF; msb = 0x80; }
            else if (size == 1) { d = cpu.d[reg] & 0xFFFF; msb = 0x8000; }
            else { d = cpu.d[reg]; msb = 0x80000000; }

            cpu.sr &= ~SR_V;
            if (cnt == 0) { cpu.sr &= ~SR_C; /* no shift: C cleared, X unchanged */
                if (size==0) set_flags_log8(d); else if (size==1) set_flags_log16(d); else set_flags_log32(d);
                break;
            }

            for (int i = 0; i < cnt; i++) {
                cpu.sr &= ~(SR_C|SR_X);
                switch (type) {
                case 0: /* ASR/ASL */
                    if (dir) { if (d & msb) cpu.sr |= SR_C|SR_X; d <<= 1; }
                    else { if (d & 1) cpu.sr |= SR_C|SR_X; if (size==0) d=(uint8_t)((int8_t)d>>1); else if(size==1) d=(uint16_t)((int16_t)d>>1); else d=(uint32_t)((int32_t)d>>1); }
                    break;
                case 1: /* LSR/LSL */
                    if (dir) { if (d & msb) cpu.sr |= SR_C|SR_X; d <<= 1; }
                    else { if (d & 1) cpu.sr |= SR_C|SR_X; d >>= 1; }
                    break;
                case 2: { /* ROXR/ROXL */
                    int x = (cpu.sr & SR_X) ? 1 : 0;
                    if (dir) { if (d & msb) cpu.sr |= SR_C|SR_X; else cpu.sr &= ~(SR_C|SR_X); d = (d<<1)|x; }
                    else { if (d & 1) cpu.sr |= SR_C|SR_X; else cpu.sr &= ~(SR_C|SR_X); d = (d>>1)|(x ? msb : 0); }
                    break;
                }
                case 3: /* ROR/ROL */
                    if (dir) { cpu.sr = (cpu.sr&~SR_C)|((d&msb)?SR_C:0); d = (d<<1)|((d&msb)?1:0); }
                    else { cpu.sr = (cpu.sr&~SR_C)|((d&1)?SR_C:0); d = (d>>1)|((d&1)?msb:0); }
                    break;
                }
            }

            if (size == 0) { cpu.d[reg] = (cpu.d[reg]&0xFFFFFF00)|(d&0xFF); set_flags_log8(d); }
            else if (size == 1) { cpu.d[reg] = (cpu.d[reg]&0xFFFF0000)|(d&0xFFFF); set_flags_log16(d); }
            else { cpu.d[reg] = d; set_flags_log32(d); }
            if (cpu.sr & SR_C) cpu.sr |= SR_C;
        }
        break;
    }

    case 0xF: /* Line F */
        exception(11);
        break;

    default:
        op_unimplemented(op);
        break;
    }
}

/* ================================================================
   Public interface
   ================================================================ */

void cpu_init(void) {
    memset(&cpu, 0, sizeof(cpu));
}

void cpu_reset(void) {
    cpu.sr = 0x2704;
    cpu.a[7] = mem_read32(0);
    cpu.ssp = cpu.a[7];
    cpu.pc = mem_read32(4);
    cpu.halted = 0;
    cpu.stopped = 0;
    cpu.cycles = 0;
}

int cpu_execute(int target_cycles) {
    cpu.cycles = 0;
    while (cpu.cycles < target_cycles && !cpu.halted) {
        if (cpu.stopped) { cpu.cycles = target_cycles; break; }

        /* Check interrupts */
        if (cpu.irq_level > 0) {
            int mask = (cpu.sr >> SR_ISHIFT) & 7;
            if (cpu.irq_level > mask || cpu.irq_level == 7) {
                int vec = 24 + cpu.irq_level;
                uint32_t vec_addr = mem_read32(vec * 4);
                cpu.stopped = 0;
                if (!(cpu.sr & SR_S)) { cpu.usp = cpu.a[7]; cpu.a[7] = cpu.ssp; }
                push32(cpu.pc);
                push16(cpu.sr);
                cpu.sr = (cpu.sr & ~SR_IMASK) | (cpu.irq_level << SR_ISHIFT);
                cpu.sr |= SR_S;
                cpu.sr &= ~SR_T;
                cpu.pc = vec_addr;
                cpu.cycles += 44;
            }
        }

        execute_one();
    }
    return cpu.cycles;
}

void cpu_set_irq(int level) {
    cpu.irq_level = level;
}

uint32_t cpu_get_reg(int r) {
    if (r >= CPU_D0 && r <= CPU_D7) return cpu.d[r];
    if (r >= CPU_A0 && r <= CPU_A7) return cpu.a[r - CPU_A0];
    if (r == CPU_PC) return cpu.pc;
    if (r == CPU_SR) return cpu.sr;
    if (r == CPU_USP) return cpu.usp;
    if (r == CPU_SSP) return cpu.ssp;
    return 0;
}

void cpu_set_reg(int r, uint32_t v) {
    if (r >= CPU_D0 && r <= CPU_D7) cpu.d[r] = v;
    else if (r >= CPU_A0 && r <= CPU_A7) cpu.a[r - CPU_A0] = v;
    else if (r == CPU_PC) cpu.pc = v;
    else if (r == CPU_SR) cpu.sr = v;
    else if (r == CPU_USP) cpu.usp = v;
    else if (r == CPU_SSP) cpu.ssp = v;
}
