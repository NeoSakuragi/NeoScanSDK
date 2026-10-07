#!/usr/bin/env python3
"""SNK Sound Driver song decoder + tick-exact player model: KOF98's v1.7 (docs/kof98_sound_driver.md, docs/kof98_songs.md)
and Kizuna Encounter's Ver 0.0 (docs/kizuna_sound_driver.md, docs/kizuna_songs.md); games98.py holds each build's
table addresses and the behaviours that differ, the build is told from the M1 ROM. Addresses below are KOF98's.

    python3 song98.py M1.bin 0x21                 summary (channels, notes, loop points)
    python3 song98.py M1.bin 0x21 --list          full event listing per channel (tick, address, opcode, params)
    python3 song98.py M1.bin 0x21 --keys [IRQS]   predicted chip events (key-on/off, F-number, sample, delta-N, TL)
    python3 song98.py M1.bin --catalog            one line per music command

The model ports the Z80 code instruction by instruction where it matters for timing and the YM2610 writes:
- timer A IRQ ($194C) -> tempo accumulator ($2605): acc += tempo; a sequencer tick when acc >= 208 (acc -= 208);
- per tick, channels in block order FM1-4, ADPCM-A 1-6, ADPCM-B ($19E0..$1ACF), the channel state machine at $1BB5
  (status 1 read, 3 rest countdown, 4 note, 5 other event; IX+4/5 length, IX+6/7 rest-after-gate or tie overhang);
- $0C / $30 (queue a command) abort the rest of the tick ($218A: LD SP,($FD0C) / JP $1BA5);
- the two LFO-style effects per channel ($1775) after the channels when $FDB8 is set ($1AD2).
Everything here is read from the code; docs/kof98_sound_driver.md gives the addresses."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from games98 import GAMES, game_of

CHANNELS = ['FM1', 'FM2', 'FM3', 'FM4', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'B']
CODE = [1, 2, 3, 4, 8, 9, 10, 11, 12, 13, 14]           # $FD17 channel number of each header slot
NOTE = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def fm_note_name(n):
    """FM note byte: $18 + 12*block + semitone ($2BC8); block b semitone 0 = C(b) (block 4 C = F-num 618 = 261.6 Hz)"""
    if not 0x18 <= (n & 0x7F) < 0x78: return f'?{n:02X}'
    k = (n & 0x7F) - 0x18
    return f'{NOTE[k % 12]}{k // 12}'

def lin_name(n):
    """linear note number, same scale as FM ($18 = C0, $48 = C4); ADPCM-B notes in scaled mode count from the root"""
    return f'{NOTE[n % 12]}{n // 12 - 2}'

def b_note_name(n):
    """ADPCM-B note byte (music mode): high nibble octave, low nibble semitone ($0981, delta-N table $2B2A)"""
    s = n & 0x0F
    return f'{NOTE[s] if s < 12 else "s%d" % s}{(n >> 4) & 7}'

class M1:
    def __init__(self, data, banksets=0x2708):
        if banksets == 0x2708 and data[0x1131] == 0x21 and data[0x1134] == 0x19:   # KOF98's code: the table the driver
            banksets = data[0x1132] | data[0x1133] << 8          # loads ($1131 LD HL,nn; the brawler moves it, TODO #219)
        self.d = data; self.sets = banksets; self.win = {0x8000: 0x8000, 0xC000: 0xC000, 0xE000: 0xE000, 0xF000: 0xF000}
    def bankset(self, n):
        b = self.d[self.sets + 4 * n:self.sets + 4 * n + 4]     # values for ports $08, $09, $0A, $0B
        self.win = {0xF000: b[0] * 0x800, 0xE000: b[1] * 0x1000, 0xC000: b[2] * 0x2000, 0x8000: b[3] * 0x4000}
    def phys(self, a):
        if a < 0x8000: return a
        for base, size in ((0x8000, 0x4000), (0xC000, 0x2000), (0xE000, 0x1000), (0xF000, 0x800)):
            if base <= a < base + size: return self.win[base] + a - base
        raise ValueError(f'RAM read {a:04X}')
    def rd(self, a): return self.d[self.phys(a & 0xFFFF)]
    def w(self, a): return self.rd(a) | self.rd(a + 1) << 8

def varlen(m, pos):
    """$25C5 -> (value, has_delta, new pos). A byte >= $C0 is not consumed (no delta)."""
    b = m.rd(pos)
    if b >= 0xC0: return 0, False, pos
    if b < 0x80: return b, True, pos + 1
    return (b & 0x3F) << 7 | (m.rd(pos + 1) & 0x7F), True, pos + 2
    # ($25D5: E = b1 with bit 7 <- bit 0 of b0, D = (b0 >> 1) & $3F: value = (b0 & $3F) << 7 | b1 & $7F; b0 bit 6 = 0 here)

# opcode names (jump table $1C8A, handler address)
OPNAMES = {
    0x00: ('note', 0x1DCB), 0x01: ('rest', 0x1D67), 0x02: ('rest2', 0x1D67), 0x03: ('instrument', 0x2050),
    0x04: ('nop04', 0x1D67), 0x05: ('pitchbend', 0x2090), 0x06: ('end', 0x1D68), 0x07: ('loop', 0x20E8),
    0x08: ('next', 0x2100), 0x09: ('call', 0x211E), 0x0A: ('return', 0x2135), 0x0B: ('goto', 0x216B),
    0x0C: ('command', 0x2170), 0x0D: ('sampletable', 0x2191), 0x0E: ('untie', 0x1D5E), 0x0F: ('key', 0x21D1),
    0x10: ('tempo', 0x21D7), 0x11: ('lfo', 0x21DF), 0x12: ('fx_on', 0x21E6), 0x13: ('fx_on', 0x21E6),
    0x14: ('fx_set', 0x2244), 0x15: ('fx_set', 0x2244), 0x16: ('restart', 0x23BD), 0x17: ('clr_bloop', 0x23C4),
    0x18: ('clr_aloop', 0x23C9), 0x19: ('nop19', 0x1D67), 0x1A: ('ssg_mixer', 0x23D9), 0x1B: ('ssg_env', 0x23FC),
    0x1C: ('nop1C', 0x1D67), 0x1D: ('transpose', 0x2412), 0x1E: ('sample_fx', 0x2420), 0x1F: ('nop1F', 0x1D67),
    0x20: ('nop20', 0x1D67), 0x21: ('fx_on', 0x21E6), 0x22: ('fx_set', 0x2244), 0x23: ('bendrange', 0x230F),
    0x24: ('volume_set', 0x2318), 0x25: ('level', 0x231E), 0x26: ('scaled', 0x2341), 0x27: ('basenote', 0x2346),
    0x28: ('ams_pms', 0x2373), 0x29: ('bsplit', 0x23A6), 0x2A: ('note_nogate', 0x1DCB), 0x2B: ('nop2B', 0x1D67),
    0x2C: ('volume', 0x1F57), 0x2D: ('modlevel', 0x1EFE), 0x2E: ('detune', 0x1EA4), 0x2F: ('rnd_range', 0x1EAC),
    0x30: ('rnd_command', 0x1EDD), 0x31: ('pan_LR', 0x1F12), 0x32: ('pan_L', 0x1F17), 0x33: ('pan_R', 0x1F1C),
    0x34: ('patch_inline', 0x2430)}

# Ver 0.0 (Kizuna, jump table $1C3E): the same opcodes up to $2E except these; no $2F-$34
OPNAMES_V00 = {k: v for k, v in OPNAMES.items() if k < 0x2F} | {
    0x01: ('skip2', 0x1E17), 0x04: ('skip1', 0x1F96), 0x0E: ('nop0E', 0x1CFA), 0x1F: ('cmd_type4', 0x232B),
    0x20: ('cmd_type5', 0x233B), 0x2B: ('pan', 0x1E38)}

def s8(v): return v - 256 if v & 0x80 else v

def parse(m, pos, chan, running, ops='v17'):
    """One event at pos -> dict(delta, has_delta, op, args, pos, next). chan = $FD17 channel number; ops = the
    driver's opcode set (games98)."""
    ev = {'pos': pos}
    d, has, pos = varlen(m, pos)
    ev['delta'], ev['has_delta'] = d, has
    b = m.rd(pos)
    if b & 0xC0 == 0xC0: op = b & 0x3F; pos += 1; ev['explicit'] = True
    else: op = running; ev['explicit'] = False
    ev['op'] = op
    a = {}
    if op is None or op not in (OPNAMES_V00 if ops == 'v00' else OPNAMES):
        ev['args'] = {'error': f'opcode {op}'}; ev['next'] = pos; return ev
    if ops == 'v00' and op in (0x01, 0x04, 0x1F, 0x20, 0x29, 0x2B):
        if op == 0x01: a['p'], a['p2'] = m.rd(pos), m.rd(pos + 1); pos += 2
        else: a['p'] = m.rd(pos); pos += 1
    elif op in (0x00, 0x2A):
        if op == 0x00:
            g, gh, pos = varlen(m, pos); a['gate'] = g; a['gate_present'] = gh
        a['note'] = m.rd(pos); a['vel'] = m.rd(pos + 1); pos += 2
    elif op in (0x03, 0x07, 0x0C, 0x0D, 0x0F, 0x10, 0x11, 0x1A, 0x1D, 0x1E, 0x24, 0x25, 0x27, 0x28, 0x2C, 0x2D, 0x2E,
                0x30, 0x12, 0x13, 0x21):
        a['p'] = m.rd(pos); pos += 1
    elif op in (0x05, 0x23):
        a['lo'], a['hi'] = m.rd(pos), m.rd(pos + 1); pos += 2
    elif op == 0x29:
        a['split'], a['hibase'] = m.rd(pos), m.rd(pos + 1); pos += 2
    elif op in (0x09, 0x0B):
        a['addr'] = m.w(pos); pos += 2
    elif op == 0x1B:
        a['r0D'], a['r0B'], a['r0C'] = m.rd(pos), m.rd(pos + 1), m.rd(pos + 2); pos += 3
    elif op == 0x2F:
        a['slot'], a['low'], a['high'] = m.rd(pos), m.rd(pos + 1), m.rd(pos + 2); pos += 3
    elif op in (0x14, 0x15, 0x22):
        sel = m.rd(pos); pos += 1; a['sel'] = sel
        if sel == 0:     # pitch effect ($F7F3 record): type, delay, depth16, step16 (type 6: count, -), speed [+ table]
            t, dl = m.rd(pos), m.rd(pos + 1)
            depth = m.w(pos + 2); step = m.w(pos + 4); spd = m.rd(pos + 6); pos += 7
            a.update(type=t, delay=dl, depth=depth, step=step, speed=spd)
            if t == 6 and ops != 'v00':  # (Ver 0.0, $2168: no inline table, the depth word is its address)
                n = step & 0xFF; a['table'] = [m.w(pos + 2 * i) for i in range(n)]; a['table_at'] = pos; pos += 2 * n
        elif ops == 'v00':  # level effect ($21B7) / sel >= 2: the 4 operator level effects ($21F7), one record each:
            recs = []       # type, delay, depth8, step, speed
            for _ in range(1 if sel == 1 else 4):
                recs.append(dict(zip(('type', 'delay', 'depth', 'step', 'speed'), (m.rd(pos + i) for i in range(5)))))
                pos += 5
            a.update(recs[0]); a['recs'] = recs
        elif sel == 1:   # level effect ($F85B record): type, delay, depth8, count, speed + count words (always)
            t, dl, dp, n, spd = (m.rd(pos + i) for i in range(5)); pos += 5
            a.update(type=t, delay=dl, depth=dp, count=n, speed=spd)
            a['table'] = [m.w(pos + 2 * i) for i in range(n)]; a['table_at'] = pos; pos += 2 * n
    elif op == 0x34:
        a['patch_at'] = pos; a['patch'] = bytes(m.rd(pos + i) for i in range(41)); pos += 41
    ev['args'] = a
    ev['next'] = pos
    return ev

def fmt_args(ev, chan, ops='v17'):
    """human-readable parameters"""
    op, a = ev['op'], ev['args']
    if 'error' in a: return a['error']
    if ops == 'v00':
        if op == 0x2B: return {3: 'L+R', 2: 'L', 1: 'R', 0: 'off'}[a['p'] & 3] + f" (${a['p']:02X})"
        if op == 0x29: return f"split note ${a['p']:02X}-$18"
        if op in (0x01, 0x04): return ' '.join(f'${a[k]:02X}' for k in ('p', 'p2') if k in a) + ' (ignored)'
        if op in (0x1F, 0x20): return f"command ${a['p']:02X}"
        if op in (0x14, 0x15, 0x22) and a['sel'] >= 1:
            return (f"{'level fx' if a['sel'] == 1 else 'operator level fx'} type {a['type']} delay {a['delay']} "
                    f"depth {s8(a['depth'])} step {a['step']} speed {a['speed']}")
    if op in (0x00, 0x2A):
        n = a['note']
        nm = fm_note_name(n) if chan <= 4 else (f'smp {n:02X}' if chan < 14 else lin_name(n))
        g = ''
        if op == 0:
            g = f" gate {a['gate']}"
            if ev['has_delta'] and a['gate'] > ev['delta']: g += ' (slur: tied into the next note)'
        return f"{nm} (${n:02X}) vel ${a['vel']:02X}{g}"
    if op == 0x05:
        v = (a['lo'] & 0x7F | (a['hi'] & 0x7F) << 7) - 0x2000
        return f"bend {v:+d} (raw {a['lo']:02X} {a['hi']:02X})"
    if op == 0x23: return f"range ${a['lo'] | a['hi'] << 8:04X} per 1/4 semitone"
    if op == 0x29: return f"split note ${a['split']:02X}-$18, high base ${a['hibase']:02X}"
    if op in (0x09, 0x0B): return f"${a['addr']:04X}"
    if op == 0x1B: return f"R0D=${a['r0D']:02X} R0B=${a['r0B']:02X} R0C=${a['r0C']:02X}"
    if op == 0x2F: return f"slot {a['slot']}: commands ${a['low']:02X}-${a['high']:02X}"
    if op in (0x14, 0x15, 0x22):
        if a['sel'] == 0:
            s = f"pitch fx type {a['type']} delay {a['delay']} depth {s16(a['depth'])} step {a['step']} speed {a['speed']}"
            if a['type'] == 6: s = f"pitch fx table x{len(a['table'])} delay {a['delay']} speed {a['speed']} {a['table']}"
            return s
        if a['sel'] == 1:
            return (f"level fx type {a['type']} delay {a['delay']} depth {a['depth']} speed {a['speed']} "
                    f"table {a['table']}")
        return f"sel {a['sel']} (ignored)"
    if op == 0x34: return 'patch ' + a['patch'].hex()
    if op == 0x03 and chan <= 4: return f"${a['p']:02X} (FM patch)"
    if op == 0x03 and chan == 14: return f"${a['p']:02X} (ADPCM-B instrument)"
    if op == 0x0D: return f"${a['p']:02X} (ADPCM-A sample table {a['p']})"
    if op in (0x2C, 0x24): return f"${a['p']:02X}"
    if op == 0x27: return f"${a['p']:02X}" + (' (FM transpose %+d)' % s8((a['p'] - 0x18) & 0xFF) if chan <= 4 else ' (ADPCM-B root note)')
    if op in (0x12, 0x13, 0x21):
        p = a['p']; parts = []
        if p & 1: parts.append('pitch fx ' + ('on' if p & 2 else 'off'))
        if p & 4: parts.append('level fx ' + ('on' if p & 8 else 'off'))
        return ', '.join(parts) or 'no change'
    if op == 0x2E: return f"F-num {s8((a['p'] - 0x40) & 0xFF):+d}"
    if op == 0x1D:
        p = a['p']; v = -(p & 0x3F) if p & 0x40 else p & 0x3F
        return f"{v:+d} semitones"
    if op == 0x0F: return f"${a['p']:02X}" + (' (ADPCM-B mode)' if chan == 14 else f' (transpose {s8(a["p"]):+d})')
    if op == 0x25:
        bias = 0x88 if chan < 8 else (0x80 if chan < 14 else 0xB8)
        return f"{s8((a['p'] - bias) & 0xFF):+d} (raw ${a['p']:02X})"
    if 'p' in a: return f"${a['p']:02X}"
    return ''

def s16(v): return v - 0x10000 if v & 0x8000 else v

# ------------------------------------------------------------------------------------------------ the player model

class Fx:
    """one effect record (13 bytes at $F7F3 / $F85B + 13*index), engine $1775"""
    def __init__(self): self.f = 0; self.pos = 0; self.type = 0; self.depth = 0; self.step = 0; self.delay = 0
    dcnt = 0; val = 0; speed = 0; scnt = 0
    def restart(self):                                      # $188F
        self.f &= 0x11
        dl = self.delay - 1
        if dl <= 0: self.f |= 2; dl = 0
        self.dcnt = dl & 0xFF; self.scnt = self.speed; self.val = 0
    def on_key(self):                                       # $18BB
        if not self.f & 1: return False
        if self.f & 0x20: self.f &= ~0x20; self.restart(); return True
        if self.delay: self.restart(); return True
        return False
    def tick(self, m):
        """-> new value or None ($1775)"""
        if self.depth == 0 or self.f & 0x28: return None
        if not self.f & 2:
            self.dcnt = (self.dcnt - 1) & 0xFF
            if self.dcnt: return None
            self.f |= 2
        self.scnt = (self.scnt - 1) & 0xFF
        if self.scnt: return None
        self.scnt = self.speed
        bc, hl, de = self.step, self.val, self.depth
        t = self.type & 0x0F
        def tri(hl, bc):                                     # $1819
            if not self.f & 4:
                hl = (hl + bc) & 0xFFFF; r = (hl - de) & 0xFFFF
                if not r & 0x8000: self.f |= 4; return de    # $184A
                return hl
            hl = (hl - bc) & 0xFFFF; nd = (-de) & 0xFFFF; r = (hl - nd) & 0xFFFF
            if r == 0 or r & 0x8000: self.f &= ~4; return nd
            return hl
        def saw(hl, bc):                                     # $1868
            hl = (hl + bc) & 0xFFFF; r = (hl - de) & 0xFFFF
            if r == 0: return hl
            if not r & 0x8000: self.f &= ~4; return (-de) & 0xFFFF   # $1855
            return hl
        if t == 0: v = saw(hl, bc)
        elif t == 1:
            if not self.f & 4: self.f |= 4; v = de
            else: self.f &= ~4; v = (-de) & 0xFFFF
        elif t == 2: v = tri(hl, bc)
        elif t == 3:
            a = m.d[self.pos & 0xFF]; self.pos = (self.pos + 1) & 0xFF
            v = 0 if a & 2 else tri(hl, bc)
        elif t == 4:
            v = saw(hl, bc)
            if v & 0x8000: self.f |= 8; v = 0
        elif t == 5:
            v = tri(hl, bc)
            if v == 0 or v & 0x8000: self.f |= 8; v = 0
        else:                                                # table, ping-pong, sign flips every cycle
            c, b = self.step & 0xFF, self.step >> 8
            addr = (2 * c + de) & 0xFFFF
            if not self.f & 4:
                a = c + 1
                if a >= b: self.f |= 4; a -= 2
            else:
                a = c - 1
                if a < 0: self.f &= ~4; self.f ^= 0x10; a = 1
            self.step = (self.step & 0xFF00) | (a & 0xFF)
            v = m.w(addr)
        self.val = v & 0xFFFF
        return self.val if not self.f & 0x10 else (-self.val) & 0xFFFF

class Chan:
    def __init__(self, k, sp):
        self.k, self.name, self.code = k, CHANNELS[k], CODE[k]
        self.status = 1 if sp else 0
        self.op = 0xFF; self.note = 0xFF; self.vel = 0; self.c1 = 0; self.c2 = 0; self.flags = 0xC1
        self.pos = self.start = sp; self.loops = []; self.calls = []
        self.key = 0; self.vol = 0; self.off = 0; self.fdet = 0     # IX+9, IX+10, IX+11, IX+0F
        self.level = 0                                            # IX+0E
        self.visited = {}                                         # event address -> first tick read
        self.pending = None                                       # loop target after a backward $0B / $16
        self.grp = 0; self.logname = self.name                    # Ver 0.0 sequenced effect blocks: group 1, 'fxA5'

class Song:
    def __init__(self, data, cmd, listing=False):
        self.game = game_of(data); self.g = g = GAMES[self.game]
        self.v00 = g['ops'] == 'v00'
        self.m = m = M1(data, g['banksets'])
        self.cmd = cmd
        idx = cmd - 0x20
        self.ptr = ptr = g['song20'] if idx == 0 else m.w(g['songs'] + 2 * idx)
        if not ptr: raise ValueError('no song')
        self.bank = m.rd(m.w(0x2E06) + idx); m.bankset(self.bank)
        self.head = [m.rd(ptr + i) for i in range(0x0E)]
        self.tempo = self.head[0x0B]
        self.fm_att, self.b_att = self.head[0x0C], self.head[0x0D]    # $F8AF+1 (FM TL add), +4 (ADPCM-B volume add)
        self.sp = [m.w(ptr + 0x0E + 2 * k) if self.head[k] else 0 for k in range(11)]
        self.ch = [Chan(k, self.sp[k]) for k in range(11)]
        self.acc = 0; self.irq = 0; self.tick = 0
        self.fdb8 = 0; self.fd9c = 0; self.bendrange = 0xAA
        self.atab = [m.w(0x2E0E)] * 6; self.aflag = [0] * 6        # $FD6C / $FD7E (set by $0D)
        self.fd20, self.fd21, self.fd22 = 0x3C, 0x24, 0             # ADPCM-B base notes / split
        if self.v00: self.fd21 = 0x3C                               # ($FDF0, $FDF1, $FDF2: $1145)
        self.bsmp = [None, None, None]                              # $FD1A / $FD1C / $FD1E record addresses
        self.f9de = 0; self.f9dd = 0; self.b1b = 0                 # b1b: last value written to ADPCM-B volume $1B
        self.shadow = {}                                            # FM shadow regs per channel: {(code, reg): val}
        self.fx1 = {c: Fx() for c in (1, 2, 3, 4, 14)}; self.fx2 = {c: Fx() for c in (1, 2, 3, 4, 14)}
        self.opfx = {c: [Fx() for _ in range(4)] for c in (1, 2, 3, 4)}   # Ver 0.0: $F8A9 + $34*(c-1) + 13*op
        self.optl = {c: [0] * 4 for c in (1, 2, 3, 4)}              # $FE73: the patch's TLs, S1 S2 S3 S4
        # Ver 0.0 sample effects started by the songs (opcode $1E): the three ADPCM-A effect channels A4-A6
        self.efx = [dict(state=0, prio=0, until=0) for _ in range(3)]   # $FAB0 + 5*i: bit 0 one-shot, bit 1 sequence
        self.ech = [None] * 3                                       # sequence blocks $FD3D / $FD64 / $FD8B (group 1)
        self.eatab = [m.w(0x2E0E)] * 3; self.eaflag = [0] * 3       # their sample tables ($FE48, $FE54)
        self.tempo1 = self.acc1 = 0; self.f987 = 0; self.grp = 0    # group 1 tempo $FE5D / acc $FE5F, level add
        self.opmask = {c: 0 for c in (1, 2, 3, 4)}                  # $FE84: the patch's modulators ($261C)
        self.fdbb = [[0, 0, 0] for _ in range(8)]
        self.listing = listing; self.log = []                       # (tick, chan, pos, text)
        self.out = []                                               # chip events: (irq, tick, chan, kind, data)
        self.loop_at = {}                                           # chan -> (tick of the jump, target, target tick)
        self.queued = []

    # -- chip writes the model predicts (kept short: what validation compares)
    def emit(self, ch, kind, **kw): self.out.append((self.irq, self.tick, ch.name if ch else '-', kind, kw))

    def fm_tl(self, ch):                                        # $2003 (music mode: level = vel + IX+11 + header +$0C)
        a = self.level_index(ch, self.g['lv_fm'])
        a = (a + self.fm_att) & 0xFF
        if a >= 0x7F: a = 0x7F
        ch.level = a
        self.emit(ch, 'tl', tl=a)

    def level_index(self, ch, table, vel=None):                # $1F79 (vel: Garou's level effect enters at $1F8C)
        vel = ch.vel if vel is None else vel
        if ch.flags & 1: return (vel + ch.off) & 0xFF
        if vel == 0: return self.m.rd(table)
        a = (((vel * (ch.vol & 0x7F)) & 0xFFFF) << 1 >> 8) - 1      # (7 bits of the volume: 7 shift-adds)
        return self.m.rd(table + (a & 0xFF))

    def fm_pitch(self, ch, fine, key):
        """$2447 / $244A: D = $F0 (key) with fine E; returns after the F-num and key-on writes"""
        if key and self.fd9c & 1 and not self.fd9c & 2: return       # tie into the same note: nothing
        n = (ch.key + ch.note) & 0xFF
        if not ch.flags & 1: n = (n + ch.off) & 0xFF
        n &= 0x7F
        v = self.m.rd(self.g['notes'] + n)
        if v >= 0xC0:                                           # $2533 CP $C0 / RET NC: carry clear, so the caller
            self.emit(ch, 'badnote', note=n)                    # goes on with HL at the note table entry: the word
            fn = (self.m.w(self.g['notes'] + n) + s8(ch.fdet & 0xFF)) & 0xFFFF   # there ($FFFF) + detune, the block
            word = fn | (ch.note & 7) << 11                     # = the note byte's low 3 bits (B, $24B1)
        else:
            blk = v & 7
            if ch.flags & 1 and ch.vol:
                blk = (blk + ch.vol) & 0xFF
                if blk >= 8: self.emit(ch, 'badblock', note=n); return
            idx = ((v & 0xF0) >> 1) + fine
            fn = self.m.w(self.g['fnum'] + (idx & 0xFF))               # 8-bit offset: a bend below semitone 0 wraps
            fn = (fn + s8(ch.fdet & 0xFF)) & 0xFFFF
            word = fn | (blk << 11)
        c = ch.code
        if c <= 4:
            self.shadow[(c, 'fnum')] = word
            self.emit(ch, 'fnum', block=(word >> 11) & 7, fnum=word & 0x7FF, hi=word >> 8 & 0xFF)   # hi: the byte written to $A4
        else:                                                   # $05 on ADPCM: the FM path is not guarded: port B
            self.emit(ch, 'bogus_fnum', reg_hi=0xA4 + c - 2, reg_lo=0xA0 + c - 2, word=word)  # regs $A4/$A0 + (ch-2)
        if self.fdb8:                                           # $24D1: restart the effects (records by $149E)
            for r in self.fx_records(c): r.on_key()
            if self.v00 and c <= 4:                             # ($23FA: the 4 operator records too)
                for r in self.opfx[c]: r.on_key()
        if self.fd9c & 2: return                               # legato into another note: no key-on write
        if c <= 4: self.emit(ch, 'keyon')
        else: self.emit(ch, 'bogus_key', reg28=((c - 2) | 4 | 0xF0) & 0xFF)

    def fx_records(self, c):
        """the two effect records $149E gives channel c ($F7F3 / $F85B + 13*index): index = c (FM), c+1 (>= 5), $41/13 = 5
        for ADPCM-B; ADPCM-A's indexes land on other channels' records"""
        idx = 5 if c == 14 else (c + 1 if c >= 5 else c)
        rec = []
        for base, table in ((0, self.fx1), (8, self.fx2)):          # fx2 area = fx1 area + 8 records
            j = idx + base
            if 1 <= j <= 4: rec.append(self.fx1[j])
            elif j == 5: rec.append(self.fx1[14])
            elif 9 <= j <= 12: rec.append(self.fx2[j - 8])
            elif j == 13: rec.append(self.fx2[14])
        return rec

    def keyon(self, ch):                                        # $1E37 / $1E39 with D = $F0
        c = ch.code
        if c <= 4:
            self.fm_tl(ch); self.fm_pitch(ch, 0, True)
        elif c < 14:
            if self.fd9c == 1 or self.v00 and self.fd9c & 1: return   # $1E5E: tie into the same sample (Ver 0.0
            # $1DE5: any tie, FE6C bit 0)
            self.a_note(ch)
        else:
            self.b_note(ch, keyon=True)

    def keyoff(self, ch):                                       # $1E39 with D = 0
        c = ch.code
        if c <= 4: self.emit(ch, 'keyoff')
        elif c < 14:
            if self.v00 and self.fd9c & 1: return               # Ver 0.0 $1DE5: no key-off while the last note-on
            if self.v00 and c >= 11:                            # anywhere was a tie (FE6C bit 0); $0318 as a_note
                st = self.efx[c - 11]['state']
                if (st & 1 if self.grp else st): return
            self.emit(ch, 'adump')
        else:
            if self.v00:
                if self.fd9c & 1 and not (self.g.get('b_legato_keyon') and self.fd9c & 2 and not ch.flags & 1):
                    self.b_note(ch, keyon=False)                # $1E12: the tie path ($079B) instead of a key-off
                else: self.emit(ch, 'boff')                     # Ver 0.1: a slur into another note is a key-off here
                                                                # (the note-on keys the sample again; KOF96 $2C measured)
                return
            if ch.flags & 1 and self.fd9c & 2: return           # $1E9B (FD9C is global: the last note-on anywhere)
            self.emit(ch, 'boff')

    def a_note(self, ch):                                       # $035D -> $1FD5 (level) -> $03F5 -> $0232 / $02C8
        c = ch.code - 8
        if self.v00 and c >= 3:                                 # $0318: an effect owns A4-A6: the music's notes
            st = self.efx[c - 3]['state']                       # are skipped; a sequence's only by a one-shot
            if (st & 1 if self.grp else st): return
        lvl = self.level_index(ch, self.g['lv_a'])
        lvl = (lvl + (self.f987 if self.grp else 0)) & 0x1F    # + $F8AF+3 (0 in songs); group 1: + its record's
        ch.level = lvl
        pan = ch.flags & 0xC0
        tab = self.atab[c]; big = self.aflag[c] & 1
        if self.grp: tab = self.eatab[c - 3]; big = self.eaflag[c - 3]
        rec = tab + (11 if big else 6) * ch.note
        m = self.m
        start, end = m.w(rec + 1), m.w(rec + 3)
        info = dict(sample=ch.note, start=start, end=end, pan=pan, level=lvl, table=tab)
        if big:
            info['loops'] = m.rd(rec + 5)                     # 11-byte record: + loop count, loop start, loop end
            if info['loops']: info['end'] = m.w(rec + 8); info['lstart'] = m.w(rec + 6); info['tail_end'] = m.w(rec + 3)
            if self.v00: info['rec_level'] = m.rd(rec + 10)     # $0277: the record's own pan|level, written next
        self.emit(ch, 'akey', **info)

    def b_note(self, ch, keyon):                                # $1E77 -> $0825
        m = self.m
        b = ch.note
        if ch.flags & 1: b = (b + ch.vol) & 0xFF
        lv = self.level_index(ch, self.g['lv_b'])
        self.f9dd = (lv + self.b_att) & 0xFF
        d5 = bool(self.fd9c & 1)
        if self.g.get('b_legato_keyon') and self.fd9c & 2 and not ch.flags & 1:
            d5 = False                                           # Ver 1.0 $1FFC: a slur into another note, outside
            # note mode, keys the sample on again instead of the tie path
        mode = ch.key
        if mode == 1:                                            # $088E: drum kit, the note picks the record
            rec = m.w(self.g['b_rec']) + 13 * b; dn = m.w(rec + 10)
        else:
            if mode == 0: rec, base = self.bsmp[0], self.fd20    # $0881: one sample, root note $FD20
            elif self.v00:                                       # $0714: high sample with the plain root, low
                if ((b - 0x18) & 0xFF) >= self.fd22: rec, base = self.bsmp[2], self.fd20   # with the octave root
                else: rec, base = self.bsmp[1], self.fd21
            elif ((b - 0x18) & 0xFF) >= self.fd22: rec, base = self.bsmp[2], self.fd21   # split: high sample
            else: rec, base = self.bsmp[1], self.fd20
            if ch.flags & 1:                                     # $0981: note = octave << 4 | semitone
                o = (b & 0x70) >> 4; s = b & 0x0F
            else:                                                # $093A: semitones from the root, +12 ...
                a = (b - base) & 0xFF
                own = m.w(rec + 10)                              # ... except two sample rates the code singles out
                six = 0x6EB3 - (self.v00 and own > 0x375A)       # Ver 0.0 $07FA: no OR A before the second SBC,
                if own == 0x375A: a = (a - 12) & 0xFF            # the first one's borrow counts: $6EB3 itself
                elif own != six: a = (a + 12) & 0xFF             # gets +12 (only $6EB2 would not)
                a &= 0x7F; o, s = a // 12, a % 12
            dn = m.w(self.g['b_dn'] + 24 * (o & 7) + 2 * (s & 0x0F))
        fx2on = self.fx2[14].f & 1                               # level effect on: the key-on leaves $1B to it
        if d5:                                                   # $08F0: tie: volume, and the pitch if another note
            if not fx2on: self.b1b = self.f9dd; self.emit(ch, 'bvol', vol=self.f9dd)
            if self.fd9c & 2: self.f9de = dn; self.emit(ch, 'bpitch', deltan=dn)
            self.fd9c = 0
            return
        self.f9de = dn
        start = m.w(rec + 1) if rec is not None else None
        end = m.w(rec + 3) if rec is not None else None
        if not fx2on: self.b1b = self.f9dd
        self.emit(ch, 'bkey', note=b, deltan=dn, start=start, end=end, vol=self.b1b, pan=ch.flags & 0xC0)
        self.fx1[14].on_key(); self.fx2[14].on_key()

    # -- one sequencer tick of one channel: $1BB5
    def run_channel(self, ch):
        st = ch.status
        if st == 0: return True
        if st == 1: return self.read(ch)
        if st == 2: return True
        if st == 3:
            ch.c2 = (ch.c2 - 1) & 0xFFFF
            if ch.c2 == 0: ch.c2 = 1; return self.read(ch)     # (expired counters are not stored back: stay 1)
            return True
        if ch.flags & 0x20 and self.g['overhang']:               # tie overhang ($1BE0; Ver 0.0 has none)
            ch.c2 = (ch.c2 - 1) & 0xFFFF
            if ch.c2 == 0:
                ch.c2 = 1; ch.flags &= ~0x20; self.keyoff(ch)
        ch.c1 = (ch.c1 - 1) & 0xFFFF
        if ch.c1: return True
        ch.c1 = 1
        if st != 4: return self.read(ch)
        if ch.flags & 0x10:
            ch.flags |= 0x20; return self.read(ch)
        if ch.c2:                                               # rest after the gate
            ch.status = 3; ch.flags &= ~0x20; self.keyoff(ch); return True
        ch.flags &= ~0x20; self.keyoff(ch)
        return self.read(ch)

    def read(self, ch):
        """$1C3F/$1C4F: events until one with a non-zero delta; returns False if the tick was aborted"""
        m = self.m
        for _ in range(10000):
            if ch.pos == ch.pending and ch.logname not in self.loop_at:
                self.loop_at[ch.logname] = (ch.visited[ch.pos], self.tick - ch.visited[ch.pos], ch.pos)
                if self.listing: self.log.append((self.tick, ch.logname, ch.pos, f'---- loop: back to ${ch.pos:04X} '
                                                  f'(first played at tick {ch.visited[ch.pos]}), period {self.tick - ch.visited[ch.pos]} ticks'))
            ch.visited.setdefault(ch.pos, self.tick)
            ev = parse(m, ch.pos, ch.code, ch.op, self.g['ops'])
            if ev['has_delta']: ch.c1 = ev['delta']
            chain = not (ev['has_delta'] and ev['delta'])
            op = ev['op']
            if 'error' in ev['args']:
                self.log.append((self.tick, ch.logname, ch.pos, f"ERROR {ev['args']['error']}")); ch.status = 0; return True
            ch.op = op
            ch.status = 5
            if self.listing:
                self.log.append((self.tick, ch.logname, ch.pos, f"{'+%d' % ev['delta'] if ev['has_delta'] else '  '}"
                                 f" {(OPNAMES_V00 if self.v00 else OPNAMES)[op][0]:12s} {fmt_args(ev, ch.code, self.g['ops'])}"))
            ch.pos = ev['next']
            r = self.execute(ch, ev)
            if r == 'abort': return False
            if ch.status == 0 and op == 0x06: return True
            if not chain: return True
        raise RuntimeError('runaway chain')

    def execute(self, ch, ev):
        op, a, m = ev['op'], ev['args'], self.m
        c = ch.code
        if self.v00 and op in (0x01, 0x04, 0x0E, 0x1F, 0x20, 0x29, 0x2B, 0x2C, 0x27, 0x14, 0x15, 0x22, 0x12, 0x13,
                               0x21, 0x05):
            return self.execute_v00(ch, ev)
        if op in (0x00, 0x2A):                                   # $1DCB
            C = 1 if ch.flags & 0x20 else 0
            self.fd9c = C
            ch.flags &= 0xCF
            if op != 0: ch.c2 = 0
            else:
                g = a['gate']
                if ch.c1 == g: ch.c2 = 0
                elif ch.c1 > g: ch.c2 = ch.c1 - g; ch.c1 = g
                else: ch.c2 = (g - ch.c1) & 0xFFFF; ch.flags |= 0x10
            ch.status = 4
            if C and ch.note != a['note']: self.fd9c = 2 | C
            ch.note, ch.vel = a['note'], a['vel']
            self.keyon(ch)
        elif op == 0x03:
            if c <= 4: self.load_patch(ch, m.w(0x2E0C) + 41 * a['p'])
            elif c == 14:
                p = a['p']
                br = m.w(self.g['b_rec'])
                self.bsmp[0] = br + 13 * m.rd(m.w(0x2E08) + p)
                pr = m.w(0x2E0A) + 2 * p
                self.bsmp[1] = br + 13 * m.rd(pr); self.bsmp[2] = br + 13 * m.rd(pr + 1)
                self.emit(ch, 'binst', inst=p)
        elif op == 0x34:
            if c <= 4: self.load_patch(ch, a['patch_at'])
        elif op == 0x05:
            v = (a['lo'] & 0x7F | (a['hi'] & 0x7F) << 7) + 0xE000 & 0xFFFF
            if v == 0: fine, note = 0, ch.note
            else:
                sign = 1
                if v & 0x8000: v = (-v) & 0xFFFF; sign = -1
                note, cc = ch.note, 2
                while True:
                    v -= self.bendrange
                    if v <= 0: break
                    cc += 2
                    if cc & 8: cc = 0; note = (note + sign) & 0xFF
                fine = cc if sign > 0 else -cc
            save = ch.note; ch.note = note
            self.fm_pitch(ch, fine, True); ch.note = save
        elif op == 0x06:                                         # $1D68: FM keeps sounding; A dumped; B reset
            ch.status = 0
            if self.v00 and 11 <= c < 14:                        # $1D3B: A4-A6 kept while an effect owns them;
                e = self.efx[c - 11]                             # a sequence's end clears its own bit first
                if self.grp: e['state'] &= ~2
                if not e['state']: self.emit(ch, 'adump')
            elif 8 <= c < 14: self.emit(ch, 'adump')
            elif c == 14: self.emit(ch, 'bstop')
        elif op == 0x07:
            if a['p']: ch.loops.append([a['p'], ch.pos])
        elif op == 0x08:
            if ch.loops:
                ch.loops[-1][0] -= 1
                if ch.loops[-1][0] & 0xFF: ch.pos = ch.loops[-1][1]
                else: ch.loops.pop()
        elif op == 0x09: ch.calls.append(ch.pos); ch.pos = a['addr']
        elif op == 0x0A:
            if ch.calls: ch.pos = ch.calls.pop()
        elif op == 0x0B:
            self.mark_jump(ch, a['addr']); ch.pos = a['addr']
        elif op == 0x16:
            self.mark_jump(ch, ch.start); ch.pos = ch.start
        elif op == 0x0C:
            self.queued.append((self.tick, ch.name, a['p'])); self.emit(ch, 'command', cmd=a['p']); return 'abort'
        elif op == 0x2F:
            s = (a['slot'] - 1) & 7; cnt = (a['high'] - a['low'] + 1) & 0xFF
            b = cnt; z = 0
            while z < 8 and not (b << z) & 0x80: z += 1
            self.fdbb[s] = [a['low'], cnt, 0xFF >> z]
        elif op == 0x30:
            self.emit(ch, 'command', cmd='random %s' % self.fdbb[(a['p'] - 1) & 7]); return 'abort'
        elif op == 0x0D:
            t = m.w(0x2E0E + 2 * a['p'])
            if t and self.grp and c >= 11:                       # $20BA: group 1 uses its own tables
                self.eatab[c - 11] = t; self.eaflag[c - 11] = 1 if a['p'] == self.g['big_slot'] else 0
            elif t and c >= 8 and c < 14:
                self.atab[c - 8] = t; self.aflag[c - 8] = 1 if a['p'] == self.g['big_slot'] else 0
        elif op == 0x0E: ch.flags &= 0xCF
        elif op == 0x0F: ch.key = a['p']
        elif op == 0x1D:
            p = a['p']; ch.key = (-(p & 0x3F)) & 0xFF if p & 0x40 else p & 0x3F
        elif op == 0x10:                                         # $257B: the tempo of the channel's group
            if self.grp: self.tempo1 = a['p']; self.acc1 = 0
            else: self.tempo = a['p']; self.acc = 0
        elif op == 0x11: self.emit(ch, 'lfo', reg22=a['p'])
        elif op in (0x12, 0x13, 0x21):
            p = a['p']
            for bit, fx in ((0, self.fx1), (2, self.fx2)):
                if p >> bit & 1 and c in fx:
                    r = fx[c]; r.f = (r.f & 0x10) | (p >> (bit + 1) & 1)
                    if r.f & 1: self.fdb8 = 1; r.restart()
        elif op in (0x14, 0x15, 0x22):
            if a['sel'] == 0 and c in self.fx1:
                r = self.fx1[c]; r.type = a['type']; r.delay = a['delay']; r.speed = a['speed']
                r.f &= ~0x10; depth = a['depth']
                if depth & 0x8000: r.f |= 0x10; depth = (-depth) & 0xFFFF
                r.depth = depth; r.step = a['step']
                if a['type'] == 6: r.depth = a['table_at']; r.step = (len(a['table']) << 8)
                if r.f & 1: self.fdb8 = 1; r.restart()
            elif a['sel'] == 1 and c in self.fx2:
                r = self.fx2[c]; r.type = a['type']; r.delay = a['delay']; r.speed = a['speed']
                r.f &= ~0x10
                if a['depth'] & 0x80: r.f |= 0x10
                r.depth = a['table_at']; r.step = len(a['table']) << 8
                if r.f & 1: self.fdb8 = 1; r.restart()
        elif op == 0x23: self.bendrange = a['lo'] | a['hi'] << 8
        elif op == 0x24: ch.vol = a['p']
        elif op == 0x2C:
            ch.vol = a['p']
            if ch.note != 0xFF:
                if c <= 4: self.fm_tl(ch)
                elif c == 14:
                    self.f9dd = self.b1b = (self.level_index(ch, self.g['lv_b']) + self.b_att) & 0xFF; self.emit(ch, 'bvol', vol=self.f9dd)
                else:                                         # $1FE8 -> $05D5: reg $08+ch = pan | level
                    ch.level = self.level_index(ch, self.g['lv_a']) & 0x1F
                    self.emit(ch, 'alevel', level=ch.level, pan=ch.flags & 0xC0)
        elif op == 0x25:
            bias = 0x88 if c < 8 else (0x80 if c < 14 else 0xB8)
            ch.off = (a['p'] - bias) & 0xFF
        elif op == 0x26: ch.flags &= ~1
        elif op == 0x27:
            if c < 5: ch.off = (a['p'] - 0x18) & 0xFF
            elif c == 14: self.fd20 = a['p']
        elif op == 0x29:
            if c == 14: self.fd22 = (a['split'] - 0x18) & 0xFF; self.fd21 = a['hibase']
        elif op == 0x2D:
            if c <= 4: self.emit(ch, 'modtl', tl=a['p'])
        elif op == 0x2E: ch.fdet = (a['p'] - 0x40) & 0xFF
        elif op in (0x31, 0x32, 0x33):
            ch.flags = (ch.flags & 0x3F) | {0x31: 0xC0, 0x32: 0x80, 0x33: 0x40}[op]
            if c <= 4: self.emit(ch, 'pan', pan=ch.flags & 0xC0)
        elif op == 0x28: self.emit(ch, 'ams_pms', p=a['p'])
        elif op == 0x1E:
            self.emit(ch, 'sample_fx', code=a['p'])
            if self.v00: self.sample_fx(a['p'])
        elif op in (0x1A, 0x1B): self.emit(ch, 'ssg', **a)
        return None

    def execute_v00(self, ch, ev):
        """the opcodes Ver 0.0 handles differently (jump table $1C3E)"""
        op, a, m = ev['op'], ev['args'], self.m
        c = ch.code
        if op == 0x2B:                                           # $1E38: pan = p bits 1-0 -> flag bits 7-6
            ch.flags = (ch.flags & 0x3F) | (a['p'] << 6 & 0xC0)
            if 1 <= c <= 4: self.emit(ch, 'pan', pan=ch.flags & 0xC0)
        elif op == 0x2C:                                         # $1E78: volume, then the level at once ($1EE1)
            ch.vol = a['p']
            if c <= 4: self.fm_tl(ch)
            elif c == 14: self.f9dd = (self.level_index(ch, self.g['lv_b']) + self.b_att) & 0xFF   # $1F31: $FAAD,
            elif c >= 8:                                         # written at the next key-on
                ch.level = self.level_index(ch, self.g['lv_a']) & 0x1F
                self.emit(ch, 'alevel', level=ch.level, pan=ch.flags & 0xC0)
        elif op == 0x27:                                         # $2241
            if 1 <= c < 5: ch.off = (a['p'] - 0x18) & 0xFF
            elif c == 14:
                self.fd20 = (a['p'] - 0x18) & 0xFF; self.fd21 = self.fd20 // 12 * 12
        elif op == 0x29:                                         # $22A5: split only
            if c == 14: self.fd22 = (a['p'] - 0x18) & 0xFF
        elif op in (0x1F, 0x20):                                 # $232B / $233B: a type 4 / type 5 command now
            self.emit(ch, 'command', cmd=a['p'])
        elif op == 0x05:                                         # $1F99 / $1FB2: as KOF98's, but the count stops
            v = (a['lo'] & 0x7F | (a['hi'] & 0x7F) << 7) + 0xE000 & 0xFFFF   # only below 0 and restarts at 2
            if v == 0: fine, note = 0, ch.note
            else:
                sign = 1
                if v & 0x8000: v = (-v) & 0xFFFF; sign = -1
                note, cc = ch.note, 2
                while True:
                    v -= self.bendrange
                    if v < 0: break
                    cc += 2
                    if cc & 8: cc = 2; note = (note + sign) & 0xFF
                fine = cc if sign > 0 else -cc
            save = ch.note; ch.note = note
            self.fm_pitch(ch, fine, True); ch.note = save
        elif op in (0x12, 0x13, 0x21):                           # $20ED: bits 0-1 pitch, 2-3 level, 4-5 operators
            p = a['p']
            for bit, recs in ((0, self.fx1.get(c)), (2, self.fx2.get(c)), (4, self.opfx.get(c))):
                if not p >> bit & 1 or recs is None: continue
                for r in (recs if isinstance(recs, list) else [recs]):
                    r.f = (r.f & 0x10) | (p >> (bit + 1) & 1)
                    if r.f & 1: self.fdb8 = 1; r.restart()
        elif op in (0x14, 0x15, 0x22):                           # $215F
            sel = a['sel']
            if sel == 0:
                r = self.fx1.get(c)
                if r is None: return None
                r.type = a['type']; r.delay = a['delay']; r.speed = a['speed']
                r.f &= ~0x10; depth = a['depth']
                if depth & 0x8000: r.f |= 0x10; depth = (-depth) & 0xFFFF
                r.depth = depth; r.step = a['step']
                if r.f & 1: self.fdb8 = 1; r.restart()
            else:
                recs = [self.fx2.get(c)] if sel == 1 else self.opfx.get(c)
                if not recs or recs[0] is None: return None
                for r, d in zip(recs, a['recs']):
                    r.type = d['type']; r.delay = d['delay']; r.speed = d['speed']
                    r.f &= ~0x10; depth = d['depth']
                    if depth & 0x80: r.f |= 0x10; depth = (-depth) & 0xFF
                    r.depth = depth; r.step = d['step']
                    if r.f & 1: self.fdb8 = 1; r.restart()
        return None                                              # $01, $04, $0E: nothing

    def fx_alloc(self, prio):
        """$0413: an ADPCM-A effect channel (0-2 = A4-A6) for a sound of this priority, or None: the first free one,
        else the busy one with the highest priority value not below the new one (the last of equals)"""
        best, pick = prio, None
        for i, e in enumerate(self.efx):
            if not e['state']: return i
            if e['prio'] >= best:
                pick = i
                if i < 2: best = e['prio']                       # ($0469: A6 does not update the bound)
        return pick

    def sample_fx(self, code):
        """opcode $1E (Ver 0.0, $0195): a one-shot sample (code < $F0: slot 0's 6-byte record) or a sequenced effect
        ($F0-$FF: record [priority][level add][stream] at games98 'seqfx', $04D9) on an effect channel"""
        m = self.m
        if code < 0xF0:
            rec = m.w(0x2E0E) + 6 * code
            i = self.fx_alloc(m.rd(rec))
            if i is None: return
            e = self.efx[i]; e['prio'] = m.rd(rec); e['state'] |= 1  # $03FB
            start, end = m.w(rec + 1), m.w(rec + 3)
            # the end-of-sample flag frees it ($02BB -> $0303); its time is inferred from the length: 2 nibbles a
            # byte at 8 MHz / 432 (18.5 kHz), polled by the next timer interrupt
            e['until'] = self.irq + int((end - start + 1) * 512 * 432 / 8e6 * 166.83) + 1
            lv = m.rd(rec + 5)
            self.out.append((self.irq, self.tick, CHANNELS[7 + i], 'akey',
                             dict(sample=code, start=start, end=end, pan=lv & 0xE0, level=lv & 0x1F, table=rec, fx=True)))
            return
        rec = m.w(self.g['seqfx'] + 2 * (code - 0xF0))
        if not rec: return
        i = self.fx_alloc(m.rd(rec))
        if i is None: return
        e = self.efx[i]; e['prio'] = m.rd(rec); e['state'] |= 2  # $0571
        sp = m.w(rec + 2)
        ch = Chan(7 + i, sp); ch.grp = 1; ch.logname = 'fx' + ch.name
        self.ech[i] = ch if sp else None
        self.eatab[i] = m.w(0x2E0E); self.eaflag[i] = 0          # $04FD
        if sp: self.f987 = m.rd(rec + 1); self.tempo1 = 0x5A     # $055B: group 1 tempo 90 (its accumulator runs on)

    def end_flags(self):
        """$02BB at the start of the interrupt: a one-shot whose sample ended frees its channel (state 1 only)"""
        for e in self.efx:
            if e['state'] == 1 and self.irq >= e['until']: e['state'] = 0

    def group1(self):
        """$1AC8: the sequenced effect blocks, with their own tempo accumulator ($2545), FE69 = 1"""
        hl = self.acc1 + self.tempo1
        if hl < 0xD0: self.acc1 = hl; return True
        self.acc1 = hl - 0xD0
        self.grp = 1
        try:
            for i, ch in enumerate(self.ech):
                if ch and self.efx[i]['state'] & 2 and ch.status:
                    if not self.run_channel(ch): return False
        finally: self.grp = 0
        return True

    def load_patch(self, ch, addr):                              # $130C / $132A + $14B6
        m = self.m; c = ch.code
        p = [m.rd(addr + i) for i in range(41)]
        self.emit(ch, 'patch', addr=addr, alg=p[28] & 7, fb=(p[28] >> 3) & 7)
        if self.v00:                                             # $127A: TLs S1 S2 S3 S4, modulator mask ($1427);
            # a patch's effects do not set $FE88 (effects running): only $12 / $14 do ($178A)
            self.optl[c] = [p[4], p[6], p[5], p[7]]; self.opmask[c] = m.rd(self.g['modmask'] + (p[28] & 7))
        b = p[30]
        r = self.fx1[c]; r.f = 0; r.type = b & 0x0F; r.delay = p[31]
        if r.type != 6:
            r.depth = p[32] | p[33] << 8
            if p[33] & 0x80: r.f |= 0x10
            r.step = p[34] | p[35] << 8
            if r.step: r.speed = p[36]; r.f |= 0x21; self.fdb8 |= not self.v00 or self.g.get("patch_fx", False)
        else:
            r.depth = (m.w(self.g['fx6']) + 2 * (p[32] | p[33] << 8)) & 0xFFFF
            r.depth = m.w(r.depth); r.step = p[34] << 8
            if p[34]: r.speed = p[36]; r.f |= 0x21; self.fdb8 |= not self.v00 or self.g.get("patch_fx", False)
        r2 = self.fx2[c]; r2.f = 0; r2.type = b >> 4; r2.delay = p[37]
        if r2.type != 6:
            r2.depth = p[38]
            if p[38] & 0x80: r2.f |= 0x10
            r2.step = p[39]
            if p[39]: r2.speed = p[40]; r2.f |= 0x21; self.fdb8 |= not self.v00 or self.g.get("patch_fx", False)
        else:
            r2.depth = m.w(m.w(self.g['fx6']) + 2 * p[38]); r2.step = p[39] << 8
            if p[39]: r2.speed = p[40]; r2.f |= 0x21; self.fdb8 |= not self.v00 or self.g.get("patch_fx", False)

    def mark_jump(self, ch, target):
        if ch.logname not in self.loop_at and not ch.loops and not ch.calls and target in ch.visited:
            ch.pending = target

    def fx_tick(self):                                            # $1AD8: $16DB, $18D3, $0A3E, $0A76
        for c in (1, 2, 3, 4):
            r = self.fx1[c]
            if r.f & 1:
                v = r.tick(self.m)
                if v is not None:
                    w = (self.shadow.get((c, 'fnum'), 0) + v) & 0xFFFF
                    self.out.append((self.irq, self.tick, CHANNELS[c - 1], 'vib', {'block': (w >> 11) & 7, 'fnum': w & 0x7FF,
                                                                                 'hi': w >> 8 & 0xFF}))   # the whole byte to $A4: a
                    # bend below F-number 0 writes $FF there (Real Bout 2's $33)
        for c in (1, 2, 3, 4):
            r = self.fx2[c]
            if r.f & 1:
                v = r.tick(self.m)
                if v is not None:                                 # $1924 -> $2003: the TL is recomputed without it
                    ch = self.ch[c - 1]
                    if self.g.get('fm_level_fx'):                  # Garou $1948: velocity + value ($0AB6) -> $1F8C
                        a = (self.level_index(ch, self.g['lv_fm'], (v + ch.vel) & 0xFF) + self.fm_att) & 0xFF
                        ch.level = 0x7F if a >= 0x7F else a
                    self.out.append((self.irq, self.tick, CHANNELS[c - 1], 'tl', {'tl': ch.level, 'fx2': True}))
        if self.v00:                                             # $184C: operator level effects, on the patch's
            for c in (1, 2, 3, 4):                               # modulators only: TL = the patch's TL + value
                for i, r in enumerate(self.opfx[c]):
                    if not (self.opmask[c] >> i & 1 and r.f & 1): continue
                    v = r.tick(self.m)
                    if v is not None:
                        self.out.append((self.irq, self.tick, CHANNELS[c - 1], 'optl',
                                         {'reg': (0x40, 0x48, 0x44, 0x4C)[i], 'tl': (self.optl[c][i] + v) & 0xFF}))
        r = self.fx1[14]
        if r.f & 1:
            v = r.tick(self.m)
            if v is not None:
                self.out.append((self.irq, self.tick, 'B', 'bpitch', {'deltan': ((self.f9de or 0) + v) & 0xFFFF, 'fx': True}))
        r = self.fx2[14]
        if r.f & 1:
            v = r.tick(self.m)
            if v is not None:
                self.b1b = self.f9dd = (v + self.ch[10].vel) & 0xFF
                self.out.append((self.irq, self.tick, 'B', 'bvol', {'vol': self.b1b, 'fx': True}))

    def run(self, irqs=None, ticks=None):
        """advance timer-A IRQs (irqs) or sequencer ticks (ticks)"""
        while True:
            if irqs is not None and self.irq >= irqs: break
            if ticks is not None and self.tick >= ticks: break
            if irqs is None and all(c.status == 0 for c in self.ch): break   # (the driver keeps ticking: effects run on)
            self.irq += 1
            if self.v00: self.end_flags()
            hl = (self.acc + self.tempo) & 0xFFFF                # 16-bit (HL): a tempo above 208 carries on in acc and
            if hl < 0xD0:                                       # wraps every 65536 / (tempo - 208) IRQs: one tick lost (KOF96 $29, tempo 240: every 2048)
                self.acc = hl
                if self.v00: self.group1()
                continue
            self.acc = hl - 0xD0
            self.tick += 1
            aborted = False
            for ch in self.ch:
                if not self.run_channel(ch): aborted = True; break
            if not aborted and self.fdb8: self.fx_tick()
            if not aborted and self.v00: self.group1()
        return self

def catalog(data):
    m = M1(data)
    rows = []
    from games98 import music_cmds
    for cmd in music_cmds(data):
        try: s = Song(data, cmd, listing=False)
        except ValueError: rows.append((cmd, None)); continue
        s.run(ticks=60000)
        rows.append((cmd, s))
    return rows

def summary(s):
    print(f"song ${s.cmd:02X}: ptr ${s.ptr:04X} bank set {s.bank} tempo {s.tempo} (tick {166.83 * s.tempo / 208:.2f} Hz) "
          f"FM att ${s.fm_att:02X} B att ${s.b_att:02X}")
    for ch in s.ch:
        if not s.sp[ch.k]: continue
        keys = [e for e in s.out if e[2] == ch.name and e[3] in ('keyon', 'akey', 'bkey')]
        lp = s.loop_at.get(ch.name)
        lt = f'loops to ${lp[2]:04X} (first played at tick {lp[0]}) every {lp[1]} ticks' if lp else \
            ('ends' if ch.status == 0 else 'no loop within the run')
        print(f"  {ch.name:4s} start ${s.sp[ch.k]:04X} key-ons {len(keys):4d}  {lt}")

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    if sys.argv[2] == '--catalog':
        for cmd, s in catalog(data):
            if s is None: print(f'${cmd:02X} -'); continue
            used = ' '.join(CHANNELS[k] for k in range(11) if s.sp[k])
            lp = sorted(set(v[0] for v in s.loop_at.values()))
            print(f"${cmd:02X} ptr ${s.ptr:04X} bank {s.bank} tempo {s.tempo:3d} chans {used} loops at ticks {lp}")
        sys.exit()
    cmd = int(sys.argv[2], 16)
    mode = sys.argv[3] if len(sys.argv) > 3 else ''
    s = Song(data, cmd, listing=(mode == '--list'))
    s.run(ticks=int(sys.argv[4]) if len(sys.argv) > 4 and mode != '--keys' else (None if mode == '--keys' else 20000),
          irqs=int(sys.argv[4]) if mode == '--keys' and len(sys.argv) > 4 else None)
    if mode == '--list':
        print(f"song ${s.cmd:02X}: header ${s.ptr:04X}, bank set {s.bank}, tempo {s.tempo} = {166.83 * s.tempo / 208:.2f} ticks/s, "
              f"FM attenuation ${s.fm_att:02X}, ADPCM-B volume add ${s.b_att:02X}")
        print('columns: tick (sequencer ticks from the start), stream address (Z80, in the song\'s bank set), "+n" = this '
              'event\'s length (ticks until the next event of the channel), opcode, parameters')
        for name in CHANNELS:
            ev = [l for l in s.log if l[1] == name]
            if not ev: continue
            print(f'== {name}')
            for t, _, pos, txt in ev: print(f'{t:6d}  ${pos:04X}  {txt}')
    elif mode == '--keys':
        for irq, t, ch, kind, kw in s.out:
            print(irq, t, ch, kind, ' '.join(f'{k}={v:X}' if isinstance(v, int) else f'{k}={v}' for k, v in kw.items()))
    else: summary(s)
