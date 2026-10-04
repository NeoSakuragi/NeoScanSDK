#!/usr/bin/env python3
"""Song decoder + tick-exact player model of ADK's "Operation System Program for Music & Effective Sound Ver. 8.8.9"
(Ninja Master's): docs/ninjamas_sound_driver.md, docs/ninjamas_songs.md.

    python3 songadk.py M1.bin 0xD0                 summary (channels, notes, loops)
    python3 songadk.py M1.bin 0xD0 --list [TICKS]  event listing per channel (tick, address, event)
    python3 songadk.py M1.bin 0xD0 --writes [TICKS] the model's YM2610 writes, tick by tick
    python3 songadk.py M1.bin --catalog            one line per music command

The songs are MML text read by the driver as it plays: note letters A-G (+ '#' / 'b' and fine steps), 'R' rest,
'X' sample, binary length codes (1 = whole note = 192 ticks ... $C0 = 1 tick, '.' dotted, '_' tie), 'O' '<' '>'
octave, 'V' volume, '?' patch / sample, 'T' tempo, 'Q' gate, pan 'l' 's' 'r', loops '[' ']' '{' '}' '|' '*', marks
'$' '%' '(' ')', '/' back to the start, $FF end. The model is a port of the Z80 routines: every channel keeps the
driver's own 64-byte block (`blk`, same offsets as IX+n in the code), and the YM2610 writes are produced in the
order the code makes them. Code addresses are cited in the comments."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gamesadk import GAMES, game_of, music_cmds

CHANNELS = ['FM1', 'FM2', 'FM3', 'FM4', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'B']
# per header slot: the channel's RAM block ($F900 + 64n); FM1-4 $F900-$F9C0, ADPCM-A 1-6 $FA00-$FB40, ADPCM-B $FB80
FM_LEN = {}                                                  # filled from the ROM (len_tab)

def s8(v): return v - 256 if v & 0x80 else v

class M1:
    """the Z80's view: $0000-$DFFF fixed; $E000-$EFFF the 4 KB window (port $09), $F000-$F7FF the 2 KB window
    (port $08); a mode-1 / mode-2 song moves one of them onto its bank ($04DD, $0504)"""
    def __init__(self, data):
        self.d = data; self.game = game_of(data); self.g = GAMES[self.game]
        self.b08, self.b09 = 0x1E, 0x0E
    def phys(self, a):
        a &= 0xFFFF
        if 0xE000 <= a < 0xF000: return self.b09 * 0x1000 + (a - 0xE000)
        if 0xF000 <= a < 0xF800: return self.b08 * 0x800 + (a - 0xF000)
        return a
    def rd(self, a): return self.d[self.phys(a)]
    def w(self, a): return self.rd(a) | self.rd(a + 1) << 8

class Chan:
    def __init__(self, k):
        self.k, self.name = k, CHANNELS[k]
        self.b = bytearray(64)
        self.log = []                                        # (tick, pos, text)
        self.seen = {}; self.start = 0                       # stream address -> first tick read; start address
    def __getitem__(self, i): return self.b[i]
    def __setitem__(self, i, v): self.b[i] = v & 0xFF
    def w(self, i): return self.b[i] | self.b[i + 1] << 8
    def setw(self, i, v): self.b[i] = v & 0xFF; self.b[i + 1] = v >> 8 & 0xFF

class Song:
    def __init__(self, data, cmd, listing=False):
        self.m = M1(data); g = self.g = self.m.g
        e = data[g['cmd_tab2'] + 4 * cmd:g['cmd_tab2'] + 4 * cmd + 4]
        if e[0] != 0x40: raise ValueError('not a music command')
        self.cmd, self.song, self.mode = cmd, e[2], e[3]
        self.listing = listing
        self.tick = 0; self.wr = []                          # (tick, port, reg, val)
        self.f80a = 0; self.f808 = 0                         # fade: attenuation, command (never set by a song)
        self.f833 = 0x78                                     # tempo ($0241)
        self.timer = []                                      # (tick, timer A value) from 'T'
        self.ch = [Chan(k) for k in range(11)]
        self.loop_at = {}
        self.start()

    # ------------------------------------------------------------------------------------------ chip writes
    def out(self, port, reg, val): self.wr.append((self.tick, 'a' if port == 4 else 'b', reg & 0xFF, val & 0xFF))
    def note(self, c, pos, txt):
        if self.listing: c.log.append((self.tick, pos, txt))

    def start(self):
        """$04A5: reset ($0C86), bank windows, header copy ($054B / $055F), ADPCM-A master volume ($0533)"""
        m, g = self.m, self.g
        self.out(4, 0x10, 0x01); self.out(4, 0x1B, 0x00)                       # $0CE4
        for port in (4, 6):                                                     # $0D31: TL $7F, port A then B
            for r in (0x41, 0x45, 0x49, 0x4D, 0x42, 0x46, 0x4A, 0x4E): self.out(port, r, 0x7F)
        for r, v in ((0x10, 0x01), (0x1C, 0xBF), (0x1C, 0x00), (0x1B, 0x00)): self.out(4, r, v)   # $0247
        d = m.d
        for k in range(6):                                                      # $0289: ADPCM-A registers
            c = self.ch[4 + k]
            for i in range(6): c[0x1A + i] = d[g['a_init'] + 6 * k + i]
            c[0x11] = 6; c[0x14] = 6
        b = self.ch[10]; b[0x11] = b[0x14] = 4; b[0x1F] = 1; b[0x2E] = 0x48; b[0x2F] = 4   # $02B2
        self.f833 = 0x78                                                        # $0241
        for v in (1, 2, 5, 6): self.out(4, 0x28, v)                              # $02D4
        for k in range(4):                                                      # $030C
            c = self.ch[k]; t = g['fm_init'] + 4 * k
            c[0x10] = d[t]; c[0x11] = c[0x14] = d[t + 1]; c[0x12] = d[t + 2]; c[0x1F] = d[t + 3]
        if self.mode == 0:
            m.b08, m.b09 = 0x1E, 0x0E; hp = g['headers'] + 24 * self.song; mask = None
        elif self.mode == 1:
            m.b08, m.b09 = self.song, 0x0E; hp = 0xF000; mask = 0xF0
        else:
            m.b08, m.b09 = 0x1E, self.song; hp = 0xE000; mask = 0xE0
        for k, c in enumerate(self.ch):                                         # $054B / $055F + $057E
            lo, hi = m.rd(hp + 2 * k), m.rd(hp + 2 * k + 1)
            if mask is not None: hi = (((~mask & 0xFF) >> 1) & hi) | mask
            c[0] = lo; c[1] = hi; c[2] = lo; c[3] = hi
            for i in range(4, 0x10): c[i] = 0
            c[0x15] = c[0x16] = c[0x17] = 0; c[0x18] = c[0x19] = 0
            for i in (0x20, 0x21, 0x22, 0x23, 0x38, 0x3C, 0x3D, 0x3E, 0x3F): c[i] = 0
            c[0x20] = 1
            c.start = c.w(0)
        self.out(6, 0x01, 0x3F)                                                 # $0533: b $01 = $3F
        self.f80c = 0x3F

    # --------------------------------------------------------------------------------------- shared helpers
    def length_code(self, a):
        """$119A: length code -> ticks (CPIR over the 14 codes; an unknown code reads past the table)"""
        t = self.g['len_tab']; d = self.m.d
        codes = list(d[t:t + 14])
        i = codes.index(a) if a in codes else 14             # CPIR fails: HL ends at t + 14
        return d[t + i + 16] if i < 14 else d[t + 14 + 15]

    def lengths(self, c, de):
        """$1146: a length (codes, '.', '_' ties) -> IX+22 (count) and IX+28 (default). Returns DE at the next byte."""
        m = self.m; a = m.rd(de)
        if a == 0x2E:                                        # '.' alone: the default length x 1.5
            hl = c.w(0x28); hl = (hl + (hl >> 1)) & 0xFFFF; de += 1; a = m.rd(de)
        else:
            hl, de, a = self.len1(0, de)
        c.setw(0x22, hl); c.setw(0x28, hl)
        while a == 0x5F:                                     # '_': tie the next length
            de += 1
            hl, de, a = self.len1(hl, de)
            c.setw(0x22, hl); c.setw(0x28, hl)
        return de

    def len1(self, hl, de):                                  # $1185: one code + its dots ($11E0: half, quarter ...)
        m = self.m
        bc = self.length_code(m.rd(de)); hl = (hl + bc) & 0xFFFF
        de += 1; a = m.rd(de)
        while a == 0x2E:
            bc >>= 1; hl = (hl + bc) & 0xFFFF; de += 1; a = m.rd(de)
        return hl, de, a

    def deflen(self, c):                                     # $12E2: no length given -> the default
        if c.w(0x22) == 0: c[0x22] = c[0x28]; c[0x23] = c[0x29]

    def gate(self, c):                                       # $13DA: Q -> key-off countdown IX+2C
        hl = c.w(0x22); q = c[0x2B]
        if q == 0: hl = (hl - 1) & 0xFFFF
        else:
            h = hl >> 1; de = h >> 1; bc = de >> 1
            hl = {1: h + de + bc, 2: h + de, 3: h + bc, 4: h, 5: de + bc, 6: de}.get(q, h)
        c.setw(0x2C, hl)

    def loops(self, c, a, de):
        """the loop / jump commands every channel kind shares. Returns new DE, or None if a is not one of them."""
        m = self.m
        if a == 0x7B:                                        # '{' n ($1575): IX+15 = n - 1, IX+16 = here
            de += 1; v = (m.rd(de) - 1) & 0xFF
            c[0x15] = 0 if v & 0x80 else v; de += 1; c.setw(0x16, de); return de
        if a == 0x7D:                                        # '}' ($1587)
            if c[0x15]:
                c[0x15] -= 1; de = c.w(0x16); c.setw(0, de); self.mark(c, de, 'loop'); return de
            return de + 1
        if a == 0x5B:                                        # '[' n ($15AC): IX+0D, IX+0E
            de += 1; v = (m.rd(de) - 1) & 0xFF
            c[0x0D] = 0 if v & 0x80 else v; de += 1; c.setw(0x0E, de); return de
        if a == 0x5D:                                        # ']' ($15BE)
            if c[0x0D]: c[0x0D] -= 1; return c.w(0x0E)
            return de + 1
        if a == 0x2F:                                        # '/' ($15DD): back to the channel's start
            de = c.w(2); c.setw(0, de); self.mark(c, de, 'goto'); return de
        if a == 0x24: c.setw(4, de); return de + 1           # '$' ($15F6): mark (the '$' itself)
        if a == 0x25: de = c.w(4); self.mark(c, de, 'goto'); return de   # '%' ($15FE): to the mark
        if a == 0x7C:                                        # '|' n ($160B), exit to the byte after ':' (scan $1785)
            de += 1
            if c[9] == 0:
                c[9] = m.rd(de) | 0x80; de += 1; c.setw(0x0A, de)
                self.scan(c, 9, 0x0A, 0x3A)
                return de
            c[9] -= 1
            if c[9] == 0: de = c.w(0x0A); c.setw(0x0A, 0); return de
            return de + 1
        if a == 0x2A:                                        # '*' n ($163C), exit to the byte after '&'
            de += 1
            if c[6] == 0:
                c[6] = m.rd(de) | 0x80; de += 1; c.setw(7, de)
                self.scan(c, 6, 7, 0x26)
                return de
            c[6] -= 1
            if c[6] == 0: c[6] |= 0x40; return c.w(7)
            return de + 1
        if a == 0x28: de += 1; c.setw(0x18, de); return de   # '(' ($1673)
        if a == 0x29:                                        # ')' ($167B): clear the loop state, back to '('
            for i in range(4, 0x10): c[i] = 0
            c[0x15] = c[0x16] = c[0x17] = 0
            de = c.w(0x18); c.setw(0, de); self.mark(c, de, 'goto'); return de
        return None

    def scan(self, c, flag, ptr, byte):
        """$1750 -> $1785: between ticks the main loop searches (CPIR, 64 bytes a pass) from IX+ptr for the exit byte
        and leaves IX+ptr after it, bit 7 of IX+flag cleared. Modelled as done before the loop is next met
        (inferred: the passes between two ticks cover far more than the loop bodies' lengths)."""
        a = c.w(ptr)
        for _ in range(0x4000):
            if self.m.rd(a) == byte: c.setw(ptr, a + 1); c[flag] &= 0x7F; return
            a += 1

    def mark(self, c, target, kind):
        if c.name not in self.loop_at and target in c.seen and kind == 'goto':
            self.loop_at[c.name] = (c.seen[target], self.tick - c.seen[target], target)

    # ------------------------------------------------------------------------------------------------ FM
    def fm_tl(self, c, h):                                   # $14B0: carriers' TL = ~volume + relative TL + H
        n = self.m.d[self.g['carriers'] + (c[0x1D] & 7)]
        reg = 0x4C
        for k in range(n):
            a = ((~c[0x38] & 0x7F) + c[0x30 + k]) & 0xFF
            a = (a + h) & 0xFF
            if a >= 0x7F: a = 0x7F
            self.out(c[0x11], reg + c[0x10], a); reg -= 4

    def fm_tl_music(self, c):                                # $149B
        self.fm_tl(c, self.f80a)

    def fm_key(self, c, on):                                 # $1473 / $1477
        if c[0x11] == 8: return
        self.out(4, 0x28, c[0x12] | (0xF0 if on else 0))

    def fm_fnum(self, c):                                    # $1302
        self.out(c[0x11], 0xA4 + c[0x10], c[0x26] | c[0x2F])
        self.out(c[0x11], 0xA0 + c[0x10], c[0x27])

    def fm_b4(self, c): self.out(c[0x11], 0xB4 + c[0x10], c[0x1E])   # $10C2

    def load_patch(self, c, p):                              # $22BD: 40-byte patch
        m = self.m; P = self.g['patches'] + 40 * p
        c.setw(0x3A, P)
        q = [m.rd(P + i) for i in range(40)]
        b = q[0x20]                                          # $22E5
        c[0x30] = 0; c[0x31] = q[0x0E] - b; c[0x32] = q[0x17] - b; c[0x33] = q[0x05] - b
        c[0x34] = (q[0x1F] << 4 | q[0x1F] >> 4) & 0xFF | q[0x1E]
        c[0x35] = (q[0x0D] << 4 | q[0x0D] >> 4) & 0xFF | q[0x0C]
        c[0x36] = (q[0x16] << 4 | q[0x16] >> 4) & 0xFF | q[0x15]
        c[0x37] = (q[0x04] << 4 | q[0x04] >> 4) & 0xFF | q[0x03]
        c[0x1D] = q[0x25]; c[0x1E] = q[0x26]
        rr = lambda v, n: (v >> n | v << (8 - n)) & 0xFF
        rl = lambda v, n: (v << n | v >> (8 - n)) & 0xFF
        port, off = c[0x11], c[0x10]
        for k, base in enumerate((0x50, 0x58, 0x54, 0x5C)):  # $2342: operators in patch order, slots +0 +8 +4 +C
            o = 9 * k; s = base - 0x50
            self.out(port, 0x50 + s + off, q[o] | rr(q[o + 6], 2))            # KS / AR
            self.out(port, 0x60 + s + off, q[o + 1] | (0x80 if c[0x1C] else 0))   # AM / DR
            self.out(port, 0x70 + s + off, q[o + 2])                          # SR
            self.out(port, 0x80 + s + off, q[o + 3] | rl(q[o + 4], 4))        # SL / RR
            self.out(port, 0x40 + s + off, q[o + 5])                          # TL
            self.out(port, 0x30 + s + off, q[o + 7] | rl(q[o + 8], 4))        # DT / MUL
        self.out(port, 0xB0 + off, rl(q[0x24], 3) | q[0x25])
        c[0x1E] = c[0x1E] | q[0x26]
        self.out(port, 0xB4 + off, c[0x1E])

    def fm_env(self, c, step):
        """$0EF5: 'e' crescendo: every IX+0C ticks the volume IX+38 += step until it would reach IX+1A. Returns
        True when the volume changed."""
        if c[0x1A] == 0: return False
        c[0x1B] -= 1
        if c[0x1B]: return False
        c[0x1B] = c[0x0C]; b = c[0x1A]
        a = (c[0x38] + step) & 0xFF
        if a < b: c[0x38] = a; return True
        c[0x1A] = c[0x1B] = c[0x0C] = 0
        return False

    def fm_tick(self, c):                                    # $0E9F
        if not c[0x20]: return
        bc = c.w(0x22)
        if bc:
            c.setw(0x22, bc - 1)
            if self.fm_env(c, 2) and not self.f808: self.fm_tl(c, 0)      # $0EE0
            hl = c.w(0x2C)
            if not hl: return
            c.setw(0x2C, hl - 1)
            if hl - 1 == 0: self.fm_key(c, False)
            return
        self.fm_parse(c)
        c.setw(0x22, (c.w(0x22) - 1) & 0xFFFF)

    def fm_penv(self, c):                                    # $1892: pitch envelope ('p')
        if not c[0x3C]: return
        b = c[0x3C]; hl = c.w(0x3E); a = self.m.rd(hl)
        if a == 0:
            for i in (0x3C, 0x3D, 0x3E, 0x3F): c[i] = 0
            return
        c.setw(0x3E, hl + 1)
        x = (b * 4 + c[0x3D]) & 0xFF; q = 0                  # $18DC
        while x >= 10: x -= 10; q += 1
        c[0x3D] = x
        f = c[0x26] << 8 | c[0x27]
        if a == 1: return
        if a == 2: f = (f + q) & 0xFFFF
        elif a == 0xFE: f = (f - q) & 0xFFFF
        else: return
        c[0x27] = f & 0xFF; c[0x26] = f >> 8
        self.fm_fnum(c)

    def fm_pitch(self, c, a, de):
        """$1246: note letter a at de -> IX+26/27 (F-number with block bits left to IX+2F); returns DE at the note's
        last character ($132A)"""
        m, g = self.m, self.g
        c[0x24] = a
        base = m.d[g['note_base'] + a - 0x41]
        de += 1; b = 0; x = m.rd(de)                         # $132A
        if x == 0x23: b = 8; de += 1; x = m.rd(de)
        elif x == 0x62: b = 0xF8; de += 1; x = m.rd(de)
        adj = {0x6F: 2, 0x71: 0xFE, 0x74: 6, 0x75: 0xFA, 0x2B: 4, 0x2D: 0xFC}.get(x)   # $1348
        if adj is not None: c[0x25] = adj + b
        else: c[0x25] = b; de -= 1
        i = (base + c[0x25]) & 0xFF
        c[0x25] = 0
        f = m.w(g['fnum'] + i)
        f = (f + s8(c[0x39])) & 0xFFFF
        c[0x27] = f & 0xFF; c[0x26] = f >> 8
        return de

    def fm_parse(self, c):                                   # $0F26
        m = self.m; de = c.w(0)
        for _ in range(100000):
            a = m.rd(de); pos = de
            c.seen.setdefault(de, self.tick)
            if a == 0x3F:                                    # '?' patch ($1131)
                de += 1; c[0x1F] = m.rd(de); self.note(c, pos, f'patch ${c[0x1F]:02X}')
                self.load_patch(c, c[0x1F]); self.fm_tl(c, 0x7F); de += 1
            elif a == 0x54:                                  # 'T' tempo ($10D6)
                de += 1; self.tempo(m.rd(de)); self.note(c, pos, f'tempo {self.f833}'); de += 1
            elif a == 0x66:                                  # 'f' LFO ($100B)
                de += 1; v = m.rd(de); self.out(4, 0x22, (v & 7 | 8) if v else 0); self.note(c, pos, f'lfo ${v:02X}'); de += 1
            elif a == 0x76:                                  # 'v' PMS ($1024)
                de += 1; c[0x1E] = c[0x1E] & 0xF8 | m.rd(de) & 7; self.fm_b4(c); self.note(c, pos, f'pms {m.rd(de) & 7}'); de += 1
            elif a == 0x61:                                  # 'a' AMS + AM operators ($1045)
                de += 1; v = m.rd(de); c[0x1C] = v
                c[0x1E] = c[0x1E] & 0xCF | v & 0x30; self.fm_b4(c)
                iy = c.w(0x3A)
                for k, (mask, reg) in enumerate(((1, 0x60), (2, 0x68), (4, 0x64), (8, 0x6C))):
                    self.out(c[0x11], reg + c[0x10], m.rd(iy + 1 + 9 * k) | (0x80 if v & mask else 0))
                self.note(c, pos, f'ams ${v:02X}'); de += 1
            elif a in (0x6C, 0x73, 0x72):                    # pan ($10A8): l = left, s = both, r = right
                c[0x1E] = c[0x1E] & 0x3C | {0x6C: 0x80, 0x73: 0xC0, 0x72: 0x40}[a]
                self.fm_b4(c); self.note(c, pos, 'pan ' + chr(a)); de += 1
            elif a in FM_LEN or a == 0x2E:                   # length ($1140)
                de = self.lengths(c, de); self.note(c, pos, f'len {c.w(0x22)}')
            elif a == 0x51: de += 1; c[0x2B] = m.rd(de); self.note(c, pos, f'Q {c[0x2B]}'); de += 1
            elif a == 0x57:                                  # 'W' ($11EF): CSM / FM3 special mode via $27
                de += 1; v = m.rd(de); c[0x2A] = v
                self.f836 = (v | 0x40) if v else 0
                self.out(4, 0x27, 0x4F if v else 0x0F); self.note(c, pos, f'W ${v:02X}'); de += 1
            elif 0x41 <= a < 0x48:                           # note ($1216)
                if c[0x2A]: self.note(c, pos, 'FM3 special-mode note (not modelled)'); c[0x20] = 0; return
                self.deflen(c)
                de = self.fm_pitch(c, a, de)
                self.fm_fnum(c)
                self.fm_key(c, False); self.fm_key(c, True)
                self.gate(c)
                de += 1                                      # $137B: 'p' pitch envelope?
                if m.rd(de) == 0x70:
                    de += 1; n = m.rd(de) & 0x0F
                    c.setw(0x3E, m.w(self.g['penv'] + 2 * n)); c[0x3C] = m.d[self.g['penv_rate'] + c[0x24] - 0x41]
                    de += 1; self.note(c, pos, f'pitch envelope {n}')
                else:
                    for i in (0x3C, 0x3D, 0x3E, 0x3F): c[i] = 0
                self.fm_tl_music(c)
                c.setw(0, de)
                self.note(c, pos, f'note {self.fm_name(c)} len {c.w(0x22)} gate {c.w(0x2C)}')
                return
            elif a == 0x64:                                  # 'd' direct F-number ($13AD)
                self.deflen(c); c[0x24] = a
                c[0x26] = m.rd(de + 1); c[0x27] = m.rd(de + 2); de += 2
                self.fm_fnum(c); self.fm_key(c, True); self.gate(c); self.fm_tl_music(c)
                de += 1; c.setw(0, de); self.note(c, pos, f'fnum ${c[0x26]:02X}{c[0x27]:02X} len {c.w(0x22)}'); return
            elif a == 0x67: de += 1; c[0x39] = m.rd(de); self.note(c, pos, f'detune {s8(c[0x39])}'); de += 1
            elif a == 0x56:                                  # 'V' volume ($148D)
                de += 1; c[0x38] = m.rd(de) & 0x7F; self.fm_tl_music(c); self.note(c, pos, f'vol ${c[0x38]:02X}'); de += 1
            elif a == 0x65:                                  # 'e' ($14FF): rate (a length code), target volume
                de += 1; c[0x1B] = c[0x0C] = self.length_code(m.rd(de)); de += 1; c[0x1A] = m.rd(de); de += 1
                self.note(c, pos, f'env rate {c[0x0C]} to ${c[0x1A]:02X}')
            elif a == 0x52:                                  # 'R' rest ($1510)
                c[0x24] = a; self.deflen(c); self.fm_tl(c, 0x7F); self.fm_key(c, False)
                de += 1; c.setw(0, de); self.note(c, pos, f'rest len {c.w(0x22)}'); return
            elif a == 0x4F:                                  # 'O' ($154C)
                de += 1; v = min(m.rd(de), 8); c[0x2E] = v; c[0x2F] = m.d[self.g['oct_tab'] + v]; de += 1
                self.note(c, pos, f'octave {v}')
            elif a == 0x3C:                                  # '<' octave up ($153B)
                v = c[0x2E] + 1
                if v < 8: c[0x2E] = v; c[0x2F] = m.d[self.g['oct_tab'] + v]
                self.note(c, pos, f'octave up ({c[0x2E]})'); de += 1
            elif a == 0x3E:                                  # '>' octave down ($1544)
                if c[0x2E]: v = c[0x2E] - 1; c[0x2E] = v; c[0x2F] = m.d[self.g['oct_tab'] + v]
                self.note(c, pos, f'octave down ({c[0x2E]})'); de += 1
            elif a == 0x5A:                                  # 'Z' n ($1430): RR of the carriers
                n = m.d[self.g['carriers'] + (c[0x1D] & 0x0F)]; reg = 0x8C
                de += 1; h = m.rd(de) & 0x0F
                for k in range(n):
                    self.out(c[0x11], reg + c[0x10], (c[0x34 + k] & 0xF0 | h) if h else c[0x34 + k]); reg -= 4
                de += 1; self.note(c, pos, f'release {h}')
            elif a == 0x3D:                                  # '=' ($1701): $F801 (not used by the music path)
                de += 2
            elif a == 0xFE:                                  # $FE ($1712): skip to the octave's note
                de = self.fe_skip(c, de)
            elif a == 0xFF:                                  # end ($168B)
                self.fm_key(c, False)
                for i in range(4, 0x10): c[i] = 0
                c[0x15] = c[0x16] = c[0x17] = 0
                for i in (0x20, 0x21, 0x22, 0x23, 0x38, 0x3C, 0x3D, 0x3E, 0x3F): c[i] = 0
                self.note(c, pos, 'end'); return
            else:
                r = self.loops(c, a, de)
                if r is None:
                    if a == 0x29: pass
                    self.note(c, pos, f'unknown ${a:02X}: the parse returns'); return
                if a == 0x29: self.fm_key(c, False)          # ')' on FM keys off first ($166A)
                self.note(c, pos, {0x7B: '{', 0x7D: '}', 0x5B: '[', 0x5D: ']', 0x2F: '/', 0x24: '$', 0x25: '%',
                                   0x7C: '|', 0x2A: '*', 0x28: '(', 0x29: ')'}[a])
                de = r
        raise RuntimeError('runaway')

    def fe_skip(self, c, de):                                # $1712, literally
        m = self.m; b = c[0x2E]; de += 1; a = m.rd(de)
        if a == 0x4F:
            de += 1; v = min(m.rd(de), 8); c[0x2E] = v; c[0x2F] = m.d[self.g['oct_tab'] + v]; a = c[0x2F]
            if a == b: return self.fe_note(c, de)
            de += 1; a = m.rd(de)
        for _ in range(10000):
            if a == 0x3C:
                v = c[0x2E] + 1
                if v < 8: c[0x2E] = v; c[0x2F] = m.d[self.g['oct_tab'] + v]
                a = c[0x2E]
                if a == b: return self.fe_note(c, de)
            if a == 0x3E:
                if c[0x2E]: v = c[0x2E] - 1; c[0x2E] = v; c[0x2F] = m.d[self.g['oct_tab'] + v]
                if c[0x2E] == b: return self.fe_note(c, de)
            de += 1; a = m.rd(de)
        raise RuntimeError('runaway $FE')

    def fe_note(self, c, de):
        b = c[0x24]
        while True:
            de += 1
            if self.m.rd(de) == b: return de

    def tempo(self, a):                                      # $10E5 / $10F4 / $1113
        if a < 0x32: a = 0x32
        self.f833 = a
        v = self.m.w(self.g['tempo'] + 2 * (a - 0x32))
        h = (v << 6) >> 8 & 0xFF; l = v & 3
        self.out(4, 0x24, h); self.out(4, 0x25, l)
        self.timer.append((self.tick, v))

    def fm_name(self, c):
        f = (c[0x26] << 8 | c[0x27]) & 0x7FF
        return f'{chr(c[0x24])}{c[0x2E]}' + (f' (fnum {f})' if True else '')

    # ------------------------------------------------------------------------------------------- ADPCM-A
    def a_level(self, c):                                    # $27BB (channels 1-6: minus the fade)
        v = c[0x38]; lvl = (v & 0x1F) - self.f80a
        b = (v & 0xC0) | (lvl if lvl > 0 else 0)
        self.out(c[0x11], c[0x1E], b)

    def a_tick(self, c, n):                                  # $24A4
        if not c[0x20]: return
        bc = c.w(0x22)
        if not bc:
            self.a_parse(c); c.setw(0x22, (c.w(0x22) - 1) & 0xFFFF); return
        bc -= 1; c.setw(0x22, bc)
        hl = c.w(0x2C)
        if not hl:                                           # $253C: release, level - 3 per tick
            v = c[0x39]; x = v & 0x1F
            if not x: return
            x = x - 3 if x >= 3 else 0
            v = v & 0xC0 | x
            self.out(c[0x11], c[0x1E], v); c[0x39] = v
            return
        hl -= 1; c.setw(0x2C, hl)
        if not hl and not bc: self.out(c[0x11], 0x00, c[0x1F] | 0x80); return   # $2772: dump
        if c[0x3A]:                                          # $24E8: level envelope ('e')
            c[0x3C] += 1
            if c[0x3C] < c[0x3B]: return
            c[0x3C] = 0
            p = c[0x3E] << 8 | c[0x3F]; a = self.m.rd(p); p += 1; c[0x3E] = p >> 8; c[0x3F] = p
            if a == 0xFF: c[0x3A] = c[0x3B] = 0; return
            c[0x38] = c[0x38] & 0xC0 | a
            self.a_level(c)

    def a_parse(self, c):                                    # $2560
        m = self.m; de = c.w(0)
        for _ in range(100000):
            a = m.rd(de); pos = de
            c.seen.setdefault(de, self.tick)
            if a == 0x3F:                                    # '?' sample ($25D6); '?' '?' n = second table
                de += 1; v = m.rd(de)
                if v == 0x3F:
                    c[0x25] = c[0x14] = 0x3F; de += 1; c[0x13] = c[0x24] = m.rd(de)
                else: c[0x13] = c[0x24] = v; c[0x14] = c[0x25] = 0
                de += 1; self.note(c, pos, f'sample ${c[0x24]:02X}' + (' (table 2)' if c[0x25] else ''))
            elif a == 0x55:                                  # 'U' ADPCM-A master volume ($2600)
                de += 1; v = m.rd(de) & 0x3F
                if not self.f808: self.out(c[0x11], 0x01, v); self.f80c = v
                de += 1; self.note(c, pos, f'master ${v:02X}')
            elif a == 0x56:                                  # 'V' level ($2623)
                de += 1; c[0x38] = c[0x38] & 0xC0 | m.rd(de); de += 1; self.note(c, pos, f'vol ${m.rd(de - 1):02X}')
            elif a in (0x6C, 0x73, 0x72):                    # pan ($2633), written now
                c[0x38] = c[0x38] & 0x3F | {0x6C: 0x80, 0x73: 0xC0, 0x72: 0x40}[a]
                self.out(c[0x11], c[0x1E], c[0x38]); de += 1; self.note(c, pos, 'pan ' + chr(a))
            elif a == 0x65:                                  # 'e' speed n ($2658): level envelope n
                de += 1; c[0x3B] = m.rd(de); de += 1; n = m.rd(de); c[0x3A] = n
                p = m.w(self.g['a_env'] + 2 * n); c[0x3E] = p >> 8; c[0x3F] = p & 0xFF
                c[0x38] = c[0x38] & 0xC0 | m.rd(p); de += 1; self.note(c, pos, f'env {n} speed {c[0x3B]}')
            elif a == 0x51: de += 1; c[0x2B] = m.rd(de) & 0x0F; de += 1; self.note(c, pos, f'Q {c[0x2B]}')
            elif a == 0x52:                                  # 'R' ($271F): dump, level 0
                self.deflen(c); self.out(c[0x11], 0x00, c[0x1F] | 0x80); self.out(c[0x11], c[0x1E], c[0x38] & 0xC0)
                de += 1; c.setw(0, de); self.note(c, pos, f'rest len {c.w(0x22)}'); return
            elif a == 0x58:                                  # 'X' play ($2687)
                self.deflen(c)
                t = self.g['a_smp2'] if c[0x25] else self.g['a_smp']
                rec = t + 6 * c[0x24]
                for i in range(4): self.out(c[0x11], c[0x1A + i], m.rd(rec + i))   # $26D8
                c[0x39] = c[0x38]; self.a_level(c)
                self.out(c[0x11], 0x00, c[0x1F])             # $2705: key-on
                self.gate(c)
                de += 1; c.setw(0, de)
                self.note(c, pos, f'play ${c[0x24]:02X} len {c.w(0x22)} gate {c.w(0x2C)}'); return
            elif a in FM_LEN or a == 0x2E:
                de = self.lengths(c, de); self.note(c, pos, f'len {c.w(0x22)}')
            elif a == 0xFF:                                  # $2784
                if c.k - 3 != 5: self.out(c[0x11], 0x00, c[0x1F] | 0x80)
                c[0x20] = c[0x21] = c[0x22] = c[0x23] = 0
                self.note(c, pos, 'end'); return
            else:
                r = self.loops(c, a, de)
                if r is None: self.note(c, pos, f'unknown ${a:02X}: the parse returns'); return
                self.note(c, pos, {0x7B: '{', 0x7D: '}', 0x5B: '[', 0x5D: ']', 0x2F: '/', 0x24: '$', 0x25: '%',
                                   0x7C: '|', 0x2A: '*', 0x28: '(', 0x29: ')'}[a])
                de = r
        raise RuntimeError('runaway')

    # ------------------------------------------------------------------------------------------- ADPCM-B
    def b_vol(self, c):                                      # $2AFC: volume - 3.5 x fade
        f = self.f80a; x = (f * 3 + (f >> 1)) & 0xFF
        v = c[0x38] - x
        if v < 0: v = 0
        c[0x3A] = v; self.out(c[0x11], 0x1B, v)

    def b_fade(self, c):                                     # $2A95: volume down in steps of 8, then 0
        a = c[0x3A]
        while True:
            self.out(c[0x11], 0x1B, a)
            if a < 8: break
            a -= 8
        self.out(c[0x11], 0x1B, 0)

    def b_reset(self, c):                                    # $2B8D, $2BB0, $2BC8
        p = c[0x11]
        for r, v in ((0x10, 1), (0x10, 0), (0x1C, 0x80), (0x1C, 0), (0x10, 0)): self.out(p, r, v)

    def b_tick(self, c):                                     # $280E
        if not c[0x20]: return
        bc = c.w(0x22)
        if not bc:
            self.b_parse(c); c.setw(0x22, (c.w(0x22) - 1) & 0xFFFF); return
        c.setw(0x22, bc - 1)
        if self.fm_env(c, 4): self.b_vol(c)                  # $284F
        hl = c.w(0x2C)
        if not hl: return
        c.setw(0x2C, hl - 1)
        if hl - 1 == 0: self.b_fade(c)

    def b_parse(self, c):                                    # $285C
        m, g = self.m, self.g; de = c.w(0)
        for _ in range(100000):
            a = m.rd(de); pos = de
            c.seen.setdefault(de, self.tick)
            if a == 0x3F: de += 1; c[0x1F] = m.rd(de); de += 1; self.note(c, pos, f'sample ${c[0x1F]:02X}')
            elif a == 0x56: de += 1; c[0x38] = m.rd(de); de += 1; self.note(c, pos, f'vol ${c[0x38]:02X}')
            elif a == 0x65:
                de += 1; c[0x1B] = c[0x0C] = self.length_code(m.rd(de)); de += 1; c[0x1A] = m.rd(de); de += 1
                self.note(c, pos, f'env rate {c[0x0C]} to ${c[0x1A]:02X}')
            elif a in (0x6C, 0x73, 0x72):                    # pan ($2914): reg $11, IX+39 (loop flag lost)
                v = {0x6C: 0x80, 0x73: 0xC0, 0x72: 0x40}[a]; self.out(c[0x11], 0x11, v); c[0x39] = v
                de += 1; self.note(c, pos, 'pan ' + chr(a))
            elif a == 0x51: de += 1; c[0x2B] = m.rd(de) & 0x0F; de += 1; self.note(c, pos, f'Q {c[0x2B]}')
            elif a == 0x52:                                  # 'R' ($2A1E)
                self.deflen(c); self.b_fade(c); de += 1; c.setw(0, de); self.note(c, pos, f'rest len {c.w(0x22)}'); return
            elif a == 0x58:                                  # 'X' ($296C): replay the loaded sample
                self.deflen(c); self.b_reset(c); self.out(c[0x11], 0x10, 0x80 | c[0x39] & 0x10); self.gate(c)
                de += 1; c.setw(0, de); self.note(c, pos, f'replay len {c.w(0x22)}'); return
            elif a == 0x4F:                                  # 'O' ($2951)
                de += 1; v = m.rd(de); c[0x2F] = v; c[0x2E] = m.rd(g['b_oct'] + v); de += 1; self.note(c, pos, f'octave {v}')
            elif a == 0x3C:                                  # '<' ($293E)
                if c[0x2F] < 7: v = c[0x2F] + 1; c[0x2F] = v; c[0x2E] = m.rd(g['b_oct'] + v)
                self.note(c, pos, f'octave up ({c[0x2F]})'); de += 1
            elif a == 0x3E:                                  # '>' ($2948)
                if c[0x2F]: v = c[0x2F] - 1; c[0x2F] = v; c[0x2E] = m.rd(g['b_oct'] + v)
                self.note(c, pos, f'octave down ({c[0x2F]})'); de += 1
            elif 0x41 <= a < 0x48:                           # note ($2989)
                self.deflen(c); c[0x24] = a
                b = m.d[g['b_note'] + a - 0x41]
                de += 1; x = m.rd(de)                        # $1CF0
                if x == 0x23: c[0x25] = 2
                elif x == 0x62: c[0x25] = 0xFE
                elif x in (0x6F, 0x2B, 0x74, 0x71, 0x2D, 0x75): c[0x3C] = x
                else: de -= 1
                i = (b + c[0x2E] + c[0x25]) & 0xFF; c[0x25] = 0
                c[0x26] = m.rd(g['b_dn'] + i); c[0x27] = m.rd(g['b_dn'] + i + 1)
                self.b_reset(c)
                rec = g['b_smp'] + 8 * c[0x1F]
                for i in range(4): self.out(c[0x11], 0x12 + i, m.rd(rec + i))
                self.out(c[0x11], 0x19, c[0x26]); self.out(c[0x11], 0x1A, c[0x27])
                self.b_vol(c)
                self.out(c[0x11], 0x10, 0x80 | c[0x39] & 0x10)
                self.gate(c)
                de += 1; c.setw(0, de)
                self.note(c, pos, f'note {chr(a)}{c[0x2F]} (dn ${c[0x27]:02X}{c[0x26]:02X}) len {c.w(0x22)} gate {c.w(0x2C)}')
                return
            elif a in FM_LEN or a == 0x2E:
                de = self.lengths(c, de); self.note(c, pos, f'len {c.w(0x22)}')
            elif a == 0x4B:                                  # 'K' ($2A6E): sample repeat flag
                de += 1; c[0x39] = c[0x39] & 0xEF | m.rd(de) & 0x10; de += 1; self.note(c, pos, f'repeat {m.rd(de - 1) >> 4 & 1}')
            elif a == 0xFF:
                self.b_fade(c); c[0x20] = c[0x21] = c[0x22] = c[0x23] = 0; self.note(c, pos, 'end'); return
            else:
                r = self.loops(c, a, de)
                if r is None: self.note(c, pos, f'unknown ${a:02X}: the parse returns'); return
                self.note(c, pos, {0x7B: '{', 0x7D: '}', 0x5B: '[', 0x5D: ']', 0x2F: '/', 0x24: '$', 0x25: '%',
                                   0x7C: '|', 0x2A: '*', 0x28: '(', 0x29: ')'}[a])
                de = r
        raise RuntimeError('runaway')

    # ---------------------------------------------------------------------------------------------- clock
    def music_tick(self):                                    # $0E56: every second timer-A interrupt
        self.tick += 1
        for k in range(6): self.a_tick(self.ch[4 + k], k + 1)            # $2472
        self.b_tick(self.ch[10])                                          # $27F8
        for k in range(4): self.fm_tick(self.ch[k]); self.fm_penv(self.ch[k])   # $0E76 ($1892 after each)

    def running(self): return any(c[0x20] for c in self.ch)

    def run(self, ticks):
        while self.tick < ticks and self.running(): self.music_tick()
        return self

    def by_tick(self):
        out = {}
        for t, p, r, v in self.wr: out.setdefault(t, []).append((p, r, v))
        return out

for _c in (1, 2, 4, 8, 0x10, 0x20, 0x40, 3, 6, 0x0C, 0x18, 0x30, 0x60, 0xC0): FM_LEN[_c] = True   # $0FDD

def tick_hz(timer_a):
    """music ticks per second for a timer-A value: one tick per two interrupts of (1024 - v) x 18 us"""
    return 1e6 / (2 * 18 * (1024 - timer_a))

def summary(s):
    print(f'command ${s.cmd:02X}: song ${s.song:02X} mode {s.mode}, {s.tick} ticks, tempo {s.f833}')
    for c in s.ch:
        n = sum(1 for t, p, x in c.log if x.startswith(('note', 'play', 'replay', 'fnum')))
        lp = s.loop_at.get(c.name)
        print(f'  {c.name:4s} start ${c.start:04X} notes {n:5d}  ' +
              (f'loops to ${lp[2]:04X} (first at tick {lp[0]}) every {lp[1]} ticks' if lp else
               ('ends' if not c[0x20] else 'no loop in the run')))

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    if sys.argv[2] == '--catalog':
        for cmd, song, mode in music_cmds(data):
            s = Song(data, cmd).run(20000)
            lp = sorted(set(v[1] for v in s.loop_at.values()))
            print(f'${cmd:02X} song ${song:02X} mode {mode} tempo {s.f833} ticks {s.tick:5d} ' +
                  (f'loop {lp}' if s.running() else 'ends'))
        sys.exit()
    cmd = int(sys.argv[2], 16); mode = sys.argv[3] if len(sys.argv) > 3 else ''
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 20000
    s = Song(data, cmd, listing=True).run(n)
    if mode == '--list':
        for c in s.ch:
            if not c.log: continue
            print(f'== {c.name}')
            for t, p, x in c.log: print(f'{t:6d}  ${p:04X}  {x}')
    elif mode == '--writes':
        for t, ws in sorted(s.by_tick().items()): print(t, ' '.join(f'{p}{r:02X}={v:02X}' for p, r, v in ws))
    else: summary(s)
