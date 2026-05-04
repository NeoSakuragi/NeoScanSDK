#!/usr/bin/env python3
"""
Z80 Disassembler for Neo Geo M1 (sound driver) ROM analysis.
Supports all standard Z80 opcode prefixes: unprefixed, CB, DD, FD, ED, DDCB, FDCB.
"""

import sys
import struct

# ─── Operand encoding helpers ────────────────────────────────────────────────

def _r8(n):
    """Decode a 3-bit register field."""
    return ("B","C","D","E","H","L","(HL)","A")[n & 7]

def _r16(n):
    """Decode a 2-bit register-pair field (BC,DE,HL,SP)."""
    return ("BC","DE","HL","SP")[(n >> 4) & 3]

def _r16af(n):
    """Decode a 2-bit register-pair field (BC,DE,HL,AF) for PUSH/POP."""
    return ("BC","DE","HL","AF")[(n >> 4) & 3]

def _cc(n):
    """Decode condition code."""
    return ("NZ","Z","NC","C","PO","PE","P","M")[(n >> 3) & 7]

def _alu(n):
    """Decode ALU operation mnemonic."""
    return ("ADD A,","ADC A,","SUB ","SBC A,","AND ","XOR ","OR ","CP ")[(n >> 3) & 7]

def _rot(n):
    """Decode CB-prefix rotation/shift mnemonic."""
    return ("RLC","RRC","RL","RR","SLA","SRA","SLL","SRL")[(n >> 3) & 7]

# ─── Neo Geo YM2610 I/O port annotations ────────────────────────────────────

NEO_IO_PORTS = {
    0x00: "YM2610_STATUS_A",
    0x01: "YM2610_STATUS_A",   # mirror sometimes used for read
    0x04: "NMI_ENABLE",
    0x08: "YM2610_ADDR_A",
    0x09: "YM2610_DATA_A",
    0x0A: "YM2610_ADDR_B",
    0x0B: "YM2610_DATA_B",
    0x0C: "BANK_SWITCH",
    0x80: "TO_68K",            # response to 68k
}

def port_comment(port):
    name = NEO_IO_PORTS.get(port)
    return f"  ; {name}" if name else ""

# ─── Unprefixed opcode table (256 entries) ───────────────────────────────────

def decode_unprefixed(opcode, data, pos):
    """
    Decode one unprefixed Z80 instruction.
    Returns (mnemonic_string, byte_count_including_opcode, comment).
    data[pos] == opcode already consumed conceptually; extra bytes start at data[pos+1].
    """
    x = (opcode >> 6) & 3
    y = (opcode >> 3) & 7
    z = opcode & 7
    p = (opcode >> 4) & 3
    q = (opcode >> 3) & 1

    comment = ""

    # ── x == 0 ──
    if x == 0:
        if z == 0:
            if y == 0: return ("NOP", 1, "")
            if y == 1: return ("EX AF,AF'", 1, "")
            if y == 2:
                d = struct.unpack_from("b", data, pos+1)[0]
                target = (pos + 2 + d) & 0xFFFF
                return (f"DJNZ ${target:04X}", 2, "")
            if y == 3:
                d = struct.unpack_from("b", data, pos+1)[0]
                target = (pos + 2 + d) & 0xFFFF
                return (f"JR ${target:04X}", 2, "")
            # y == 4..7: JR cc, d
            d = struct.unpack_from("b", data, pos+1)[0]
            target = (pos + 2 + d) & 0xFFFF
            cc = ("NZ","Z","NC","C")[y - 4]
            return (f"JR {cc},${target:04X}", 2, "")
        if z == 1:
            if q == 0:
                nn = struct.unpack_from("<H", data, pos+1)[0]
                return (f"LD {_r16(opcode)},${nn:04X}", 3, "")
            else:
                return (f"ADD HL,{_r16(opcode)}", 1, "")
        if z == 2:
            if q == 0:
                if p == 0: return ("LD (BC),A", 1, "")
                if p == 1: return ("LD (DE),A", 1, "")
                if p == 2:
                    nn = struct.unpack_from("<H", data, pos+1)[0]
                    return (f"LD (${nn:04X}),HL", 3, "")
                if p == 3:
                    nn = struct.unpack_from("<H", data, pos+1)[0]
                    return (f"LD (${nn:04X}),A", 3, "")
            else:
                if p == 0: return ("LD A,(BC)", 1, "")
                if p == 1: return ("LD A,(DE)", 1, "")
                if p == 2:
                    nn = struct.unpack_from("<H", data, pos+1)[0]
                    return (f"LD HL,(${nn:04X})", 3, "")
                if p == 3:
                    nn = struct.unpack_from("<H", data, pos+1)[0]
                    return (f"LD A,(${nn:04X})", 3, "")
        if z == 3:
            if q == 0:
                return (f"INC {_r16(opcode)}", 1, "")
            else:
                return (f"DEC {_r16(opcode)}", 1, "")
        if z == 4:
            return (f"INC {_r8(y)}", 1, "")
        if z == 5:
            return (f"DEC {_r8(y)}", 1, "")
        if z == 6:
            n = data[pos+1]
            return (f"LD {_r8(y)},${n:02X}", 2, "")
        if z == 7:
            mnemonics = ("RLCA","RRCA","RLA","RRA","DAA","CPL","SCF","CCF")
            return (mnemonics[y], 1, "")

    # ── x == 1 ── LD r,r' (and HALT)
    if x == 1:
        if z == 6 and y == 6:
            return ("HALT", 1, "")
        return (f"LD {_r8(y)},{_r8(z)}", 1, "")

    # ── x == 2 ── ALU A, r
    if x == 2:
        return (f"{_alu(opcode)}{_r8(z)}", 1, "")

    # ── x == 3 ──
    if x == 3:
        if z == 0:
            return (f"RET {_cc(opcode)}", 1, "")
        if z == 1:
            if q == 0:
                return (f"POP {_r16af(opcode)}", 1, "")
            else:
                if p == 0: return ("RET", 1, "")
                if p == 1: return ("EXX", 1, "")
                if p == 2: return ("JP (HL)", 1, "")
                if p == 3: return ("LD SP,HL", 1, "")
        if z == 2:
            nn = struct.unpack_from("<H", data, pos+1)[0]
            return (f"JP {_cc(opcode)},${nn:04X}", 3, "")
        if z == 3:
            if y == 0:
                nn = struct.unpack_from("<H", data, pos+1)[0]
                return (f"JP ${nn:04X}", 3, "")
            if y == 1:
                return None  # CB prefix handled elsewhere
            if y == 2:
                n = data[pos+1]
                comment = port_comment(n)
                return (f"OUT (${n:02X}),A", 2, comment)
            if y == 3:
                n = data[pos+1]
                comment = port_comment(n)
                return (f"IN A,(${n:02X})", 2, comment)
            if y == 4: return ("EX (SP),HL", 1, "")
            if y == 5: return ("EX DE,HL", 1, "")
            if y == 6: return ("DI", 1, "")
            if y == 7: return ("EI", 1, "")
        if z == 4:
            nn = struct.unpack_from("<H", data, pos+1)[0]
            return (f"CALL {_cc(opcode)},${nn:04X}", 3, "")
        if z == 5:
            if q == 0:
                return (f"PUSH {_r16af(opcode)}", 1, "")
            else:
                if p == 0:
                    nn = struct.unpack_from("<H", data, pos+1)[0]
                    return (f"CALL ${nn:04X}", 3, "")
                if p == 1: return None  # DD prefix
                if p == 2: return None  # ED prefix
                if p == 3: return None  # FD prefix
        if z == 6:
            n = data[pos+1]
            return (f"{_alu(opcode)}${n:02X}", 2, "")
        if z == 7:
            addr = y * 8
            return (f"RST ${addr:02X}", 1, "")

    return None


# ─── CB prefix ───────────────────────────────────────────────────────────────

def decode_cb(data, pos):
    """Decode CB-prefixed instruction. pos points to the CB byte."""
    op = data[pos+1]
    x = (op >> 6) & 3
    y = (op >> 3) & 7
    z = op & 7
    r = _r8(z)
    if x == 0:
        return (f"{_rot(op)} {r}", 2, "")
    elif x == 1:
        return (f"BIT {y},{r}", 2, "")
    elif x == 2:
        return (f"RES {y},{r}", 2, "")
    else:
        return (f"SET {y},{r}", 2, "")


# ─── ED prefix ───────────────────────────────────────────────────────────────

ED_SIMPLE = {
    0x44: "NEG", 0x4C: "NEG", 0x54: "NEG", 0x5C: "NEG",
    0x64: "NEG", 0x6C: "NEG", 0x74: "NEG", 0x7C: "NEG",
    0x45: "RETN", 0x55: "RETN", 0x65: "RETN", 0x75: "RETN",
    0x5D: "RETN", 0x6D: "RETN", 0x7D: "RETN",
    0x4D: "RETI",
    0x46: "IM 0", 0x4E: "IM 0/1", 0x56: "IM 1", 0x5E: "IM 2",
    0x66: "IM 0", 0x6E: "IM 0/1", 0x76: "IM 1", 0x7E: "IM 2",
    0x47: "LD I,A", 0x4F: "LD R,A",
    0x57: "LD A,I", 0x5F: "LD A,R",
    0x67: "RRD", 0x6F: "RLD",
    0xA0: "LDI", 0xA1: "CPI", 0xA2: "INI", 0xA3: "OUTI",
    0xA8: "LDD", 0xA9: "CPD", 0xAA: "IND", 0xAB: "OUTD",
    0xB0: "LDIR", 0xB1: "CPIR", 0xB2: "INIR", 0xB3: "OTIR",
    0xB8: "LDDR", 0xB9: "CPDR", 0xBA: "INDR", 0xBB: "OTDR",
}

def decode_ed(data, pos):
    """Decode ED-prefixed instruction. pos points to the ED byte."""
    op = data[pos+1]
    x = (op >> 6) & 3
    y = (op >> 3) & 7
    z = op & 7
    p = (op >> 4) & 3
    q = (op >> 3) & 1

    if op in ED_SIMPLE:
        return (ED_SIMPLE[op], 2, "")

    if x == 1:
        if z == 0:
            r = _r8(y) if y != 6 else "(C)"
            return (f"IN {r},(C)", 2, "")
        if z == 1:
            r = _r8(y) if y != 6 else "0"
            return (f"OUT (C),{r}", 2, "")
        if z == 2:
            if q == 0:
                return (f"SBC HL,{_r16(op)}", 2, "")
            else:
                return (f"ADC HL,{_r16(op)}", 2, "")
        if z == 3:
            nn = struct.unpack_from("<H", data, pos+2)[0]
            if q == 0:
                return (f"LD (${nn:04X}),{_r16(op)}", 4, "")
            else:
                return (f"LD {_r16(op)},(${nn:04X})", 4, "")

    # fallback: unknown ED xx
    return (f"DB $ED,${op:02X}", 2, "  ; (undefined ED)")


# ─── DD / FD prefix (IX / IY) ───────────────────────────────────────────────

def _ix_r8(n, ireg):
    """Like _r8 but (HL) becomes (IX+d) placeholder."""
    base = ("B","C","D","E",f"{ireg}H",f"{ireg}L",f"({ireg}+d)","A")
    return base[n & 7]

def decode_ddfd(data, pos, ireg):
    """
    Decode DD or FD prefixed instruction. ireg is 'IX' or 'IY'.
    pos points to the DD/FD byte.
    """
    prefix = data[pos]
    if pos + 1 >= len(data):
        return (f"DB ${prefix:02X}", 1, "  ; (truncated)")
    op = data[pos+1]

    # DD CB / FD CB: indexed bit operations
    if op == 0xCB:
        if pos + 3 >= len(data):
            return (f"DB ${prefix:02X},$CB", 2, "  ; (truncated)")
        d = struct.unpack_from("b", data, pos+2)[0]
        op2 = data[pos+3]
        x2 = (op2 >> 6) & 3
        y2 = (op2 >> 3) & 7
        z2 = op2 & 7
        disp = f"+${d:02X}" if d >= 0 else f"-${-d:02X}"
        target = f"({ireg}{disp})"
        if x2 == 0:
            mnem = _rot(op2)
            if z2 == 6:
                return (f"{mnem} {target}", 4, "")
            else:
                return (f"{mnem} {target},{_r8(z2)}", 4, "  ; undocumented")
        elif x2 == 1:
            return (f"BIT {y2},{target}", 4, "")
        elif x2 == 2:
            if z2 == 6:
                return (f"RES {y2},{target}", 4, "")
            else:
                return (f"RES {y2},{target},{_r8(z2)}", 4, "  ; undocumented")
        else:
            if z2 == 6:
                return (f"SET {y2},{target}", 4, "")
            else:
                return (f"SET {y2},{target},{_r8(z2)}", 4, "  ; undocumented")

    # Map the opcode as if unprefixed, then substitute HL->IX/IY, (HL)->(IX+d)
    x = (op >> 6) & 3
    y = (op >> 3) & 7
    z = op & 7
    p = (op >> 4) & 3
    q = (op >> 3) & 1

    # Instructions that use (HL) with displacement
    needs_disp = False

    # ── x==0 ──
    if x == 0:
        if z == 1:
            if q == 0:
                nn = struct.unpack_from("<H", data, pos+2)[0]
                if p == 2:
                    return (f"LD {ireg},${nn:04X}", 4, "")
            else:
                if p == 2:
                    return (f"ADD {ireg},{ireg}", 2, "")
                # ADD IX,BC / ADD IX,DE / ADD IX,SP
                rr = ("BC","DE",ireg,"SP")[p]
                return (f"ADD {ireg},{rr}", 2, "")
        if z == 2:
            if p == 2:
                if q == 0:
                    nn = struct.unpack_from("<H", data, pos+2)[0]
                    return (f"LD (${nn:04X}),{ireg}", 4, "")
                else:
                    nn = struct.unpack_from("<H", data, pos+2)[0]
                    return (f"LD {ireg},(${nn:04X})", 4, "")
        if z == 3:
            if p == 2:
                if q == 0:
                    return (f"INC {ireg}", 2, "")
                else:
                    return (f"DEC {ireg}", 2, "")
        if z == 4:
            if y == 4:
                return (f"INC {ireg}H", 2, "  ; undocumented")
            if y == 5:
                return (f"INC {ireg}L", 2, "  ; undocumented")
            if y == 6:
                d = struct.unpack_from("b", data, pos+2)[0]
                disp = f"+${d:02X}" if d >= 0 else f"-${-d:02X}"
                return (f"INC ({ireg}{disp})", 3, "")
        if z == 5:
            if y == 4:
                return (f"DEC {ireg}H", 2, "  ; undocumented")
            if y == 5:
                return (f"DEC {ireg}L", 2, "  ; undocumented")
            if y == 6:
                d = struct.unpack_from("b", data, pos+2)[0]
                disp = f"+${d:02X}" if d >= 0 else f"-${-d:02X}"
                return (f"DEC ({ireg}{disp})", 3, "")
        if z == 6:
            if y == 4:
                n = data[pos+2]
                return (f"LD {ireg}H,${n:02X}", 3, "  ; undocumented")
            if y == 5:
                n = data[pos+2]
                return (f"LD {ireg}L,${n:02X}", 3, "  ; undocumented")
            if y == 6:
                d = struct.unpack_from("b", data, pos+2)[0]
                n = data[pos+3]
                disp = f"+${d:02X}" if d >= 0 else f"-${-d:02X}"
                return (f"LD ({ireg}{disp}),${n:02X}", 4, "")

    # ── x==1 ── LD r,r' with IX substitution
    if x == 1:
        if op == 0x76:
            # HALT - not affected by DD/FD prefix, treat as NOP-prefixed HALT
            return ("HALT", 2, "  ; DD/FD prefixed")
        # Any operand referencing (HL) slot uses (IX+d)
        if z == 6 or y == 6:
            if z == 6 and y == 6:
                return ("HALT", 2, "  ; DD/FD prefixed")
            if z == 6:
                # LD r, (IX+d)
                d = struct.unpack_from("b", data, pos+2)[0]
                disp = f"+${d:02X}" if d >= 0 else f"-${-d:02X}"
                dst = _r8(y)
                return (f"LD {dst},({ireg}{disp})", 3, "")
            if y == 6:
                # LD (IX+d), r
                d = struct.unpack_from("b", data, pos+2)[0]
                disp = f"+${d:02X}" if d >= 0 else f"-${-d:02X}"
                src = _r8(z)
                return (f"LD ({ireg}{disp}),{src}", 3, "")
        # IXH/IXL undocumented LD
        if (y == 4 or y == 5) and (z == 4 or z == 5):
            src = f"{ireg}H" if z == 4 else f"{ireg}L"
            dst = f"{ireg}H" if y == 4 else f"{ireg}L"
            return (f"LD {dst},{src}", 2, "  ; undocumented")
        if y == 4 or y == 5:
            dst = f"{ireg}H" if y == 4 else f"{ireg}L"
            src = _r8(z)
            return (f"LD {dst},{src}", 2, "  ; undocumented")
        if z == 4 or z == 5:
            src = f"{ireg}H" if z == 4 else f"{ireg}L"
            dst = _r8(y)
            return (f"LD {dst},{src}", 2, "  ; undocumented")

    # ── x==2 ── ALU with (IX+d) or IXH/IXL
    if x == 2:
        alu = _alu(op)
        if z == 6:
            d = struct.unpack_from("b", data, pos+2)[0]
            disp = f"+${d:02X}" if d >= 0 else f"-${-d:02X}"
            return (f"{alu}({ireg}{disp})", 3, "")
        if z == 4:
            return (f"{alu}{ireg}H", 2, "  ; undocumented")
        if z == 5:
            return (f"{alu}{ireg}L", 2, "  ; undocumented")

    # ── x==3 ──
    if x == 3:
        if z == 1:
            if q == 0 and p == 2:
                return (f"POP {ireg}", 2, "")
            if q == 1:
                if p == 0:
                    # DD/FD don't affect RET, but some assemblers emit it
                    pass
                if p == 2:
                    return (f"JP ({ireg})", 2, "")
                if p == 3:
                    return (f"LD SP,{ireg}", 2, "")
        if z == 3:
            if y == 4:
                return (f"EX (SP),{ireg}", 2, "")
        if z == 5:
            if q == 0 and p == 2:
                return (f"PUSH {ireg}", 2, "")

    # Fallback: prefix is ignored, decode as unprefixed
    result = decode_unprefixed(op, data, pos+1)
    if result:
        mnem, size, comment = result
        return (mnem, 1 + size, comment + "  ; (DD/FD ignored)")

    return (f"DB ${prefix:02X},${op:02X}", 2, "  ; (undefined DD/FD)")


# ─── Main disassembly engine ────────────────────────────────────────────────

def disassemble_one(data, pos):
    """
    Disassemble one instruction at data[pos].
    Returns (mnemonic, total_byte_count, comment_string).
    """
    if pos >= len(data):
        return ("DB ???", 0, "  ; beyond data")

    op = data[pos]

    # ── Prefix dispatch ──
    if op == 0xCB:
        return decode_cb(data, pos)
    if op == 0xED:
        return decode_ed(data, pos)
    if op == 0xDD:
        return decode_ddfd(data, pos, "IX")
    if op == 0xFD:
        return decode_ddfd(data, pos, "IY")

    result = decode_unprefixed(op, data, pos)
    if result:
        return result

    return (f"DB ${op:02X}", 1, "  ; (undefined)")


def disassemble_range(data, start, end, base_addr=0):
    """
    Disassemble from data[start] to data[end-1].
    base_addr is the address corresponding to data[0].
    Yields (address, raw_bytes_hex, mnemonic, comment) tuples.
    """
    pos = start
    while pos < end and pos < len(data):
        addr = base_addr + pos
        mnem, size, comment = disassemble_one(data, pos)
        if size == 0:
            size = 1  # safety: never get stuck
        raw = data[pos:pos+size]
        raw_hex = " ".join(f"{b:02X}" for b in raw)
        yield (addr, raw_hex, mnem, comment)
        pos += size


def format_disassembly(data, start, end, base_addr=0):
    """Return formatted disassembly lines."""
    lines = []
    for addr, raw_hex, mnem, comment in disassemble_range(data, start, end, base_addr):
        line = f"  {addr:04X}:  {raw_hex:<14s}  {mnem}"
        if comment:
            # pad to column 42 for aligned comments
            line = line.ljust(50) + comment
        lines.append(line)
    return "\n".join(lines)


# ─── CLI entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <binary> <start_hex> <end_hex>")
        sys.exit(1)

    binpath = sys.argv[1]
    start = int(sys.argv[2], 16)
    end = int(sys.argv[3], 16)

    with open(binpath, "rb") as f:
        data = f.read()

    print(format_disassembly(data, start, end))
