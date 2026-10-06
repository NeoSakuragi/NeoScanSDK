#!/usr/bin/env python3
"""Decoder + interrupt-exact model of Technos' "SDC_NGSS" sound driver (R. Ashworth; Double Dragon 1995, Super Dodge
Ball 1996): docs/doubledr_sound_driver.md, docs/doubledr_songs.md.

    python3 song_ngss.py M1.bin 0xE2                 summary (channels, notes, loop points)
    python3 song_ngss.py M1.bin 0xE2 --list [PASSES] event listing per channel (pass, tick, address, event)
    python3 song_ngss.py M1.bin 0xE2 --writes [PASSES]  the model's YM2610 writes, pass by pass
    python3 song_ngss.py M1.bin --catalog            one line per sound command (music, voices, effects)

The model is a port of the Z80 code operating on the driver's own RAM layout (a bytearray for $F800-$FFFF: the 14
channel blocks of $4E bytes at $F800, the globals at $FC44-$FCA5), so shared state (the loop stack in a block's
bytes 0-3, the master attenuation, the command ring the songs write into) behaves as on the Z80. Addresses in the
comments are Double Dragon's.

Clock: timer B (value $EB, set once at reset, $174C) interrupts at 165.3 Hz; the interrupt only counts ($0236). The
main loop ($00E0) runs one *pass* per interrupt: one command from the ring ($16D4), then the 14 channel updates in
the order ADPCM-A 1-6, FM 1-4, ADPCM-B, SSG A-C, then the fade ($08F5). Each channel has its own tempo accumulator
(IX+$11 += IX+$12, a tick on the carry): ticks/s = 165.3 x tempo / 256.

pass(): one main-loop pass; writes are (pass, port, reg, val), port 'a' / 'b'."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from games_ngss import GAMES, game_of, entry, music_cmds

BLOCKS = [0xF800 + 0x4E * i for i in range(14)]
CODES = [0x11, 0x12, 0x15, 0x16, 0x20, 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x80, 0x81, 0x82]
NAMES = ['FM1', 'FM2', 'FM3', 'FM4', 'B', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'SSGA', 'SSGB', 'SSGC']
ORDER = [5, 6, 7, 8, 9, 10, 0, 1, 2, 3, 4, 11, 12, 13]      # the main loop's update order ($00F4-$016F)
NOTE = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
PASS_HZ = 8e6 / 144 / (16 * (256 - 0xEB))                   # 165.34 Hz

OPS = {0x00: ('tempo', 1), 0x01: ('inst', 1), 0x02: ('pan', 1), 0x03: ('nop2', 2), 0x04: ('vol', 1),
       0x05: ('volslide', 2), 0x06: ('voltab', 1), 0x07: ('vol+', 0), 0x08: ('vol-', 0), 0x09: ('octave', 1),
       0x0A: ('oct+', 0), 0x0B: ('oct-', 0), 0x0C: ('gate', 1), 0x0D: ('loop', 1), 0x0E: ('next', 2),
       0x0F: ('break', 2), 0x10: ('detune', 2), 0x11: ('transpose', 1), 0x12: ('slide', 2), 0x13: ('jump', 3),
       0x14: ('nop', 0), 0x15: ('vibrato', 4), 0x16: ('nop', 0), 0x17: ('vibdelay', 1), 0x18: ('vib_on', 0),
       0x19: ('vib_off', 0), 0x1A: ('nop', 0), 0x1B: ('nop', 0), 0x1C: ('portaspeed', 1), 0x1D: ('porta', 1),
       0x1E: ('reply', 1), 0x1F: ('sys', 1)}

def note_name(n): return f'{NOTE[n % 12]}{n // 12}'

def s16(v): return v - 0x10000 if v & 0x8000 else v

def mul(a, b):
    """$17F5: A x B -> (B high, A low)"""
    p = (a & 0xFF) * (b & 0xFF); return p >> 8, p & 0xFF

def div(de, bc):
    """$1821: DE / BC, 16 steps of shift-and-subtract (BC = 0 gives $FFFF)"""
    hl = 0; q = 0
    for _ in range(16):
        top = de >> 15 & 1; de = de << 1 & 0xFFFF
        hl = (hl << 1 | top) & 0xFFFF
        if hl >= bc: hl -= bc; q = (q << 1 | 1) & 0xFFFF
        else: q = q << 1 & 0xFFFF
    return q

class Driver:
    def __init__(self, data, listing=False):
        self.d = data; self.game = game_of(data); self.g = GAMES[self.game]
        self.v11 = self.g['v11']
        self.blocks = BLOCKS if not self.v11 else [0xF800 + 0x4F * i for i in range(14)]
        self.VOL, self.VOLF = (0x0D, 0x0C) if self.v11 else (0x0E, 0x0D)   # volume (8.8: integer, fraction)
        self.page = 0                                       # Super Dodge Ball: the sound's page ($FC5D, block +$4E)
        self.ram = bytearray(0x800)
        self.bank = 2                                       # port $0B window ($8000-$BFFF), 16 KB banks
        self.writes = []; self.npass = 0
        self.listing = listing; self.log = []               # (pass, block, tick, pos, text)
        self.ticks = [0] * 14
        self.started = {}                                   # pass at which each sound command started
        self.ended = {}                                     # block -> pass its stream ended
        self.loops = {}                                     # block -> [(pass, tick, target)] jumps back
        self.seen = {}                                      # (block, stream address) -> the tick it was first read

    # -- memory
    def r(self, a): return self.ram[a - 0xF800]
    def w(self, a, v): self.ram[a - 0xF800] = v & 0xFF
    def G(self, a):
        """a global by its Double Dragon address -> this build's (Super Dodge Ball: +$0E below $FC4F, +$0F from it:
        the blocks grew to $4F bytes and the sound's page byte $FC5D was inserted)"""
        return a if not self.v11 else a + (0x0E if a < 0xFC4F else 0x0F)
    def gr(self, a): return self.r(self.G(a))
    def gw(self, a, v): self.w(self.G(a), v)
    def rom(self, a):
        a &= 0xFFFF
        if a < 0x8000: return self.d[a]
        if a < 0xC000: return self.d[(self.bank * 0x4000 + a - 0x8000) % len(self.d)]
        return self.d[a % len(self.d)]                       # $C000-$F7FF: the boot windows show the ROM as is
    def setbank(self, a): self.bank = (a + 2) & 0xFF          # $1747

    def ym(self, p, reg, val): self.writes.append((self.npass, p, reg & 0xFF, val & 0xFF))

    # -- block field access (IX)
    def f(self, k): return self.ram[self.ix - 0xF800 + k]
    def sf(self, k, v): self.ram[self.ix - 0xF800 + k] = v & 0xFF
    def setb(self, k, bit): self.sf(k, self.f(k) | 1 << bit)
    def resb(self, k, bit): self.sf(k, self.f(k) & ~(1 << bit))
    def bit(self, k, bit): return self.f(k) >> bit & 1

    def rd(self):
        """$0DFF: the next stream byte (HL')"""
        v = self.rom(self.hl); self.hl = (self.hl + 1) & 0xFFFF; return v

    def note(self, text, pos=None):
        if self.listing:
            b = self.blocks.index(self.ix)
            self.log.append((self.npass, b, self.ticks[b], self.pos if pos is None else pos, text))

    # ------------------------------------------------------------------------------------------- commands
    def push(self, cmd):
        """$16A4: a byte into the command ring (what NMI does for the 68000's commands, and opcode $FF 3/4/5/B)"""
        if not cmd: return
        i = self.gr(0xFC4F); self.gw(0xFC66 + i, cmd); self.gw(0xFC4F, (i + 1) & 0x3F)

    def pop(self):
        """$16BA -> the next ring byte or 0"""
        if self.gr(0xFC4F) == self.gr(0xFC51): return 0
        i = self.gr(0xFC51); self.gw(0xFC51, (i + 1) & 0x3F); return self.gr(0xFC66 + i)

    def command(self):
        """$16D4: one command per pass; $F0-$FF take the next ring byte as their argument"""
        if not self.gr(0xFC53):
            c = self.pop()
            if not c: return
            if c < 0xF0:
                self.gw(0xFC4E, c); self.page = 0; self.start(); return
            self.gw(0xFC53, c)
        a = self.pop()
        if not a: return
        c = self.gr(0xFC53) & 0x0F; self.gw(0xFC53, 0)
        if self.v11 and c in (0x0A, 0x0B):                  # $1754 / $175F: start a page-1 / page-2 sound
            self.gw(0xFC4E, a); self.page = c - 9; self.start(); return
        if self.v11 and c in (0, 0x0C, 0x0D):               # $176A ...: stop by sound id and page ($10AF)
            self.gw(0xFC4E, a); self.stop_code(a, 0 if c == 0 else c - 0x0B); return
        if c == 0: self.stop_where(5, a)                    # $110D stop by sound id
        elif c == 1: self.stop_where(6, a, active=True)     # $11C7 by priority
        elif c == 2: self.stop_where(7, a, active=True)     # $12D4 by class
        elif c == 3: self.silence()                         # $1680
        elif c in (4, 8): self.atten(a)                     # $0C24
        elif c == 5: self.gw(0xFC4B, a); self.gw(0xFC4C, 0)   # $0C39 fade speed
        elif c == 6: self.fade_reset()                      # $0C41
        elif c == 7: raise NotImplementedError('$F7 (sample test, $0C4F)')
        else: raise NotImplementedError('$F9-$FF ($0210: driver reset with a wait)')

    def atten(self, a):
        self.gw(0xFC65, ~a & 0x7F); self.dirty_all()

    def dirty_all(self):                                    # $0C2B: volume dirty on all 14 blocks
        for b in self.blocks: self.w(b + 8, self.r(b + 8) | 0x80)

    def fade_reset(self):                                   # $0C41
        self.gw(0xFC64, 0); self.gw(0xFC65, 0); self.gw(0xFC4B, 0); self.gw(0xFC4C, 0); self.dirty_all()

    def silence(self):
        """$1680: keys off and sample resets on every channel ($1698), every block inactive"""
        self.reset_chip()
        self.gw(0xFC61, 0); self.gw(0xFC62, 0)
        for b in self.blocks: self.w(b + 5, 0)

    def reset_chip(self):                                   # $1698 = $1765 $17BD $17C9 $17DF
        for c in (1, 2, 5, 6): self.ym('a', 0x28, c)
        self.ym('a', 0x22, 0)
        for base in (0x81, 0x85, 0x89, 0x8D):
            self.ym('a', base, 0xFF); self.ym('b', base, 0xFF); self.ym('a', base + 1, 0xFF); self.ym('b', base + 1, 0xFF)
        self.ym('b', 0x00, 0xBF); self.ym('b', 0x01, 0x3F)
        for r, v in ((0x10, 1), (0x10, 0), (0x1C, 0x80), (0x1C, 0)): self.ym('a', r, v)
        for r, v in ((0x08, 0), (0x09, 0), (0x0A, 0), (0x07, 0xF8)): self.ym('a', r, v)

    def stop_where(self, k, v, active=False):
        """$110D / $11C7 / $12D4: every block whose byte k equals v ($110D does not test activity first)"""
        for b in self.blocks:
            if active and not self.r(b + 5): continue
            if self.r(b + k) == v: self.stop_block(b)

    def stop_code(self, code, page):
        """Super Dodge Ball $10AF: every block whose page and sound id match"""
        for b in self.blocks:
            if self.r(b + 0x4E) == page and self.r(b + 5) == code: self.stop_block(b)

    def stop_block(self, b):
        """$0FAD: inactive, reply bit cleared, key-off with fast release ($07A4)"""
        self.w(b + 5, 0); self.gw(0xFC61, self.gr(0xFC61) & ~self.r(b + 0x43))
        self.keyoff_stop(self.r(b + 4))

    def start(self):
        """$14CF: start sound $FC4E: its table entry, the kill range, the channels it claims ($1517 / $159E)"""
        cmd = self.gr(0xFC4E); t = (self.g['table'] + 3 * (self.page << 8 | cmd)) & 0xFFFF
        de = self.d[t] << 8 | self.d[t + 1]; a = self.d[t + 2]
        hl = 0x8000 + de
        if hl > 0xFFFF: return
        self.setbank(a)
        B, C, D, E = (self.rom(hl + i) for i in range(4))
        mask = self.rom(hl + 5) | self.rom(hl + 4) << 8      # $FC47 low, $FC48 high
        self.gw(0xFC47, mask); self.gw(0xFC48, mask >> 8)
        ptr = hl + 6
        self.gw(0xFC55, E); self.gw(0xFC56, D); self.gw(0xFC5B, a)
        self.kill(B, C)
        self.started.setdefault(cmd, self.npass)
        if mask == 0x100:                                   # $159E: one of ADPCM-A 4-6
            iy = self.alloc_a46()
            if self.r(iy + 5) and E < self.r(iy + 6): return
            self.init_block(iy, ptr); ptr += 2
            self.w(iy + 7, D); self.w(iy + 6, E); self.w(iy + 5, cmd)
            if self.v11: self.w(iy + 0x4E, self.page)
            self.w(iy + 0x3A, a)
            return
        for i, b in enumerate(self.blocks):
            if not mask >> i & 1: continue
            if self.r(b + 5) and E < self.r(b + 6): ptr += 2; continue
            self.init_block(b, ptr); ptr += 2
            self.w(b + 7, D); self.w(b + 6, E); self.w(b + 0x3A, a); self.w(b + 5, cmd)
            if self.v11: self.w(b + 0x4E, self.page)
        if D == 0: self.fade_reset()                        # $1554: class 0 (music) resets the fade

    def kill(self, lo, hi):
        """$1567: stop every active block whose class is in [lo, hi]"""
        for b in self.blocks:
            if self.r(b + 5) and lo <= self.r(b + 7) <= hi:
                self.gw(0xFC61, self.gr(0xFC61) & ~self.r(b + 0x43))
                self.keyoff_stop(self.r(b + 4)); self.w(b + 5, 0)

    def alloc_a46(self):
        """$15C8: the first free of ADPCM-A 4-6, else the one with the lowest priority (ties: the lower block)"""
        B = self.blocks
        for b in B[8:11]:
            if self.r(b + 5) == 0: return b
        best = B[10]; a = self.r(best + 6)
        for b in (B[9], B[8]):
            if a >= self.r(b + 6): a = self.r(b + 6); best = b
        return best

    def init_block(self, b, ptr):
        """$15F6: stream = the offset word's address + the offset; defaults"""
        off = self.rom(ptr) << 8 | self.rom(ptr + 1)
        sp = (ptr + off) & 0xFFFF
        self.w(b + 0x0A, sp); self.w(b + 0x0B, sp >> 8)
        for k, v in ((0x45, 1), (0x19, 0x7F), (self.VOL, 0x7F), (0x1A, 8), (0x43, 8), (0x12, 0x49), (0x13, 0x30),
                     (0x42, 0xC0), (0x44, 0xC0), (0x08, 0x80), (0x33, 0), (0x48, 0), (0x17, 0), (0x18, 0), (0x29, 0),
                     (0x28, 0), (0x11, 0), (0x14, 0), (0x4B, 0), (0x1B, 1), (0x1D, 1)):
            self.w(b + k, v)
        i = self.blocks.index(b); self.ticks[i] = 0; self.ended.pop(i, None); self.loops.pop(i, None)
        for k in [k for k in self.seen if k[0] == i]: del self.seen[k]

    # ------------------------------------------------------------------------------------------- the pass
    def pass_(self):
        self.npass += 1
        self.gw(0xFC44, 0); self.gw(0xFC62, 0)
        self.command()
        for i in ORDER: self.update(i)
        self.fade()

    def fade(self):
        """$08F5: $FC64 += speed every pass; past $7FFF the fade ends and stops the blocks under the master
        attenuation ($13E1)"""
        c = self.gr(0xFC4B)
        if not c: return
        bc = c | self.gr(0xFC4C) << 8
        hl = (self.gr(0xFC64) | self.gr(0xFC65) << 8) + bc & 0xFFFF
        if hl & 0x8000:
            self.gw(0xFC4B, 0); self.gw(0xFC4C, 0)
            for b in self.blocks:
                if self.r(b + 5) and self.r(b + 0x45) & 0x80: self.stop_block(b)
            return
        self.gw(0xFC64, hl); self.gw(0xFC65, hl >> 8); self.dirty_all()

    def update(self, i):
        """$0557 (ADPCM-A) / $02A9 (FM) / $02D8 (ADPCM-B) / $0307 (SSG)"""
        self.ix = self.blocks[i]
        if not self.f(5): return
        self.gw(0xFC62, self.f(5))
        acc = self.f(0x11) + self.f(0x12); self.sf(0x11, acc)
        if acc > 0xFF:
            self.ticks[i] += 1
            code = CODES[i]
            if code & 0x40: self.tick_a(code); return       # returns past $0333 only when the stream ended
            self.tick(code)                                 # (an end returns here too, $0F93: the effects still run)
            if self.bit(8, 1): self.vibrato()
            if self.bit(8, 5): self.pitch(code)
            if self.bit(8, 7): self.level(code)
        self.reply()

    def reply(self):                                        # $0333: the note's reply pulse (68000 side only)
        a = self.f(0x44)
        if a & 0x80: return
        a = (a - 1) & 0xFF; self.sf(0x44, a)
        if a & 0x80: self.gw(0xFC61, self.gr(0xFC61) ^ self.f(0x43))

    def load_stream(self):
        self.setbank(self.f(0x3A))
        self.hl = self.f(0x0A) | self.f(0x0B) << 8

    def save_stream(self):
        self.sf(0x0A, self.hl); self.sf(0x0B, self.hl >> 8)

    def read_note(self, b, fm):
        """$0379 / $0599: note byte b: bits 3-0 = semitone above the octave base, bit 5 = keep the length, bit 4 =
        tie (no gate countdown), bit 6 = reply pulse"""
        n = (b & 0x0F) + self.f(0x13) + self.f(0x14)
        if fm: n += self.f(0x18)
        self.sf(0x16, n)
        if fm: self.sf(0x15, self.f(0x17))
        if not b & 0x20: self.sf(0x1C, self.rd() + 1)
        if b & 0x10: self.setb(8, 4)
        if b & 0x40:
            self.gw(0xFC61, self.gr(0xFC61) | self.f(0x43)); self.sf(0x44, 7)
        ln = self.f(0x1C); self.sf(0x1D, ln)
        hi, lo = mul(self.f(0x1A), ln)
        g = ((hi << 8 | lo) >> 3) & 0xFF
        self.sf(0x1B, g or 1)
        self.save_stream()
        return n & 0xFF

    def tick(self, code):
        """$0347: one tick of an FM / ADPCM-B / SSG block"""
        self.sf(4, code)
        if not self.bit(8, 4):
            self.sf(0x1B, self.f(0x1B) - 1)
            if not self.f(0x1B): self.keyoff(code)
        self.sf(0x1D, self.f(0x1D) - 1)
        if self.f(0x1D): self.cont(); return
        self.sf(8, self.f(8) & 0xE3)
        self.load_stream()
        i = self.blocks.index(self.ix)
        while True:
            self.pos = self.hl; b = self.rd()
            self.seen.setdefault((i, self.pos), self.ticks[i])
            if b < 0x80:
                n = self.read_note(b, True)
                if self.listing:
                    nm = note_name(n) if code & 0x10 or code & 0x80 else f'{n}'
                    self.note(f'note {nm} (${b:02X}) len {self.f(0x1C)} gate {self.f(0x1B)}' + (' tie' if b & 0x10 else ''))
                self.sf(0x20, 0); self.sf(0x21, 0); self.sf(0x22, 0)  # $0461
                f8 = self.f(8); self.setb(8, 5)
                if f8 & 1: self.cont(); return              # legato: the key stays on
                self.sf(0x2D, 0); self.sf(0x2E, 0)
                if f8 & 2:
                    self.sf(0x35, 0); self.sf(0x36, 0)
                    self.sf(0x33, self.f(0x29)); self.sf(0x34, self.f(0x2B))
                    self.sf(0x2F, self.f(0x31)); self.sf(0x30, self.f(0x32))
                if f8 & 0x40: self.patch(code)
                if self.f(0x45) & 1: self.pan(code)
                self.keyon(code); return
            if b < 0xE0:
                ln = (b & 0x7F) + 1; self.sf(0x1D, ln); self.sf(0x1B, ln); self.save_stream()
                self.note(f'rest len {ln}'); return
            if self.op(b & 0x1F, code): return              # the stream ended

    def tick_a(self, code):
        """$056B: one tick of an ADPCM-A block (note = sample number, no detune / slides / vibrato)"""
        self.sf(4, code)
        if not self.bit(8, 4):
            self.sf(0x1B, self.f(0x1B) - 1)
            if not self.f(0x1B): self.keyoff(code)
        self.sf(0x1D, self.f(0x1D) - 1)
        if not self.f(0x1D):
            self.resb(8, 4)
            self.load_stream()
            i = self.blocks.index(self.ix)
            while True:
                self.pos = self.hl; b = self.rd()
                self.seen.setdefault((i, self.pos), self.ticks[i])
                if b < 0x80:
                    n = self.read_note(b, False)
                    self.note(f'sample {n} tab {self.f(0x41)} (${b:02X}) len {self.f(0x1C)} gate {self.f(0x1B)}' + (' tie' if b & 0x10 else ''))
                    if self.f(8) & 1: self.volslide()
                    else:
                        if self.f(0x45) & 1: self.pan(code)
                        self.keyon(code)
                    break
                if b < 0xE0:
                    ln = (b & 0x7F) + 1; self.sf(0x1D, ln); self.sf(0x1B, ln); self.save_stream()
                    self.note(f'rest len {ln}'); break
                if self.op(b & 0x1F, code): return          # $0F93: POP DE returns from $0557 itself
        else:
            self.volslide()
        if self.bit(8, 7): self.level(code)                 # $061E
        self.reply()

    def volslide(self):
        if self.f(0x28):                                    # $04C3
            self.setb(8, 7)
            V, F = self.VOL, self.VOLF
            v = (self.f(F) | self.f(V) << 8) + (self.f(0x26) | self.f(0x27) << 8)
            self.sf(F, v); self.sf(V, v >> 8)
            self.sf(0x28, self.f(0x28) - 1)
            if not self.f(0x28): self.sf(V, self.f(0x25))

    def cont(self):
        """$04AD: a tick inside a note: volume slide, then the pitch slide or the portamento"""
        self.volslide()
        if self.bit(8, 3):                                  # $04E4
            a = self.f(0x20) + self.f(0x1E); self.sf(0x20, a); c = a >> 8
            a = self.f(0x21) + self.f(0x1F) + c; self.sf(0x21, a); c = a >> 8
            self.sf(0x22, self.f(0x22) + self.f(0x23) + c)
            self.setb(8, 5)
        elif self.bit(8, 2):                                # $0504
            d = self.f(0x24)
            bc = self.f(0x15) | self.f(0x16) << 8
            hl = (self.f(0x1E) | self.f(0x1F) << 8) - bc
            if hl & 0xFFFF == 0: return
            neg = hl < 0 or (hl & 0x8000)
            hl &= 0xFFFF
            if hl & 0x8000: hl = (-hl) & 0xFFFF
            h1, _ = mul(hl & 0xFF, d)
            h2, l2 = mul(hl >> 8, d)
            a = l2 + h1; c = a >> 8
            B = h2 + c; cy = B >> 8; B &= 0xFF
            bc = B << 8 | a & 0xFF
            if B == 0: bc += 1
            if neg: hl = (0 - bc - cy) & 0xFFFF
            else: hl = bc
            v = (hl + (self.f(0x15) | self.f(0x16) << 8)) & 0xFFFF
            self.sf(0x15, v); self.sf(0x16, v >> 8); self.setb(8, 5)

    # -- opcodes ($03EF jump table $0401). True = the stream ended (the block stopped)
    def op(self, k, code):
        name, n = OPS[k]
        pos = self.pos
        if self.listing:                                    # the operands as read (a jump moves HL before the log)
            args = ' '.join(f'${self.rom(pos + 1 + j):02X}' for j in range(n + (1 if k == 0x1F and self.rom(pos + 1) in (0, 3, 4, 5, 0x0B) else 0)))
        if k == 0x00: self.sf(0x12, self.rd())
        elif k == 0x01: self.sf(0x41, self.rd()); self.setb(8, 6)
        elif k == 0x02:
            a = self.rd(); i = (a - 256 if a & 0x80 else a) >> 5
            self.sf(0x42, self.rom(self.g['pan_tab'] + (i & 0xFF))); self.sf(0x45, self.f(0x45) | 1)
        elif k == 0x03: self.rd(); self.rd()
        elif k == 0x04:
            a = self.rd()
            if self.v11 and a & 0x80: self.sf(0x0E, a & 0x7F)  # $0DD6: the step of $E7 / $E8
            else: self.sf(self.VOL, a); self.sf(0x28, 0); self.setb(8, 7)
        elif k == 0x05:
            n_ = self.rd(); self.sf(0x28, n_)
            v = self.rd(); self.sf(0x25, v)
            diff = v - self.f(self.VOL)
            if diff >= 0: q = div(diff << 8, n_)
            else: q = (-div(((-diff) & 0xFF) << 8, n_)) & 0xFFFF
            self.sf(0x26, q); self.sf(0x27, q >> 8); self.sf(self.VOLF, 0)
        elif k == 0x06:
            a = self.rd()
            if not a & 0x80: a = self.rom(self.g['voltab'] + a)
            self.sf(self.VOL, a & 0x7F); self.setb(8, 7)
        elif k == 0x07:
            if self.v11:                                    # $0E33: + the step, $7F at most
                a = self.f(0x0D) + self.f(0x0E); self.sf(0x0D, 0x7F if a & 0x80 else a)
            else: self.sf(0x0E, self.f(0x0E) + 1)
            self.setb(8, 7)
        elif k == 0x08:
            if self.v11:                                    # $0E46: - the step, 0 at least
                a = self.f(0x0D) - self.f(0x0E); self.sf(0x0D, max(a, 0))
            else: self.sf(0x0E, self.f(0x0E) - 1)
            self.setb(8, 7)
        elif k == 0x09: self.sf(0x13, self.rd() * 12)
        elif k == 0x0A:
            if self.f(0x13) < 0x54: self.sf(0x13, self.f(0x13) + 12)
        elif k == 0x0B:
            if self.f(0x13): self.sf(0x13, self.f(0x13) - 12)
        elif k == 0x0C: self.sf(0x1A, self.rd())
        elif k == 0x0D:
            a = self.rd(); self.sf(self.f(0x48), a); self.sf(0x48, self.f(0x48) + 1)
        elif k == 0x0E:
            de = self.rd() << 8; de |= self.rd()
            sp = (self.f(0x48) - 1) & 0xFF
            self.sf(sp, self.f(sp) - 1)
            if self.f(sp): self.hl = (self.hl + de) & 0xFFFF
            else: self.sf(0x48, self.f(0x48) - 1)
        elif k == 0x0F:
            de = self.rd() << 8; de |= self.rd()
            sp = (self.f(0x48) - 1) & 0xFF
            if self.f(sp) == 1:
                self.sf(sp, 0); self.sf(0x48, self.f(0x48) - 1)
                self.hl = (self.hl + de + 2) & 0xFFFF
        elif k == 0x10: self.sf(0x18, self.rd()); self.sf(0x17, self.rd())
        elif k == 0x11: self.sf(0x14, self.rd())
        elif k == 0x12:
            b = self.rd(); a = self.rd()
            v = (b << 8 | a) << 2
            if b & 0x80: v |= 0xFC0000                      # C = $FF, its low bits shifted in
            self.sf(0x1E, v); self.sf(0x1F, v >> 8); self.sf(0x23, v >> 16); self.setb(8, 3)
        elif k == 0x13:
            cnt = self.rd(); hi = self.rd()
            if not hi:
                self.note('end', pos); return self.end(code)
            de = hi << 8 | self.rd()
            target = (self.hl + de) & 0xFFFF
            if self.listing: self.note(f'jump ${target:04X}' + (f' x{cnt}' if cnt else ''), pos)
            i = self.blocks.index(self.ix); self.loops.setdefault(i, []).append((self.npass, self.ticks[i], target))
            self.hl = target
            if not cnt: return False
            if not self.f(0x4B): self.sf(0x4B, cnt); return False
            self.sf(0x4B, self.f(0x4B) - 1)
            if self.f(0x4B): return False
            return self.end(code)
        elif k == 0x15:
            self.sf(0x2C, self.rd()); self.sf(0x2A, self.rd())
            c = self.rd(); dd = self.rd()
            self.sf(0x2B, dd); self.sf(0x34, dd)
            q = div(c << 8, dd)
            self.sf(0x31, q); self.sf(0x32, q >> 8); self.sf(0x2F, q); self.sf(0x30, q >> 8)
        elif k == 0x17: self.sf(0x29, self.rd())
        elif k == 0x18:
            self.sf(0x34, self.f(0x2B)); self.sf(0x2F, self.f(0x31)); self.sf(0x30, self.f(0x32))
            self.sf(0x35, 0); self.sf(0x36, 0); self.setb(8, 1)
        elif k == 0x19: self.sf(0x2D, 0); self.sf(0x2E, 0); self.resb(8, 1)
        elif k == 0x1C: self.sf(0x24, self.rd())
        elif k == 0x1D:
            self.sf(0x1F, self.rd() + self.f(0x14) + self.f(0x18)); self.sf(0x1E, self.f(0x17)); self.setb(8, 2)
        elif k == 0x1E: self.sf(0x43, self.rom(self.g['bits'] + self.rd()))
        elif k == 0x1F: self.sys(self.rd(), code)
        if self.listing and k not in (0x13,):
            self.note(f'{name} {args}' if args else name, pos)
        return False

    def sys(self, a, code):
        """opcode $FF a ($1052 table $1060)"""
        if a == 0:
            self.rd()
            if code & 0x80: raise NotImplementedError('$FF 00 (SSG noise period from register E)')
        elif a in (1, 2):
            if not code & 0x80: return
            ch = code & 7
            v = ((0xF7, 0xEF, 0xDF) if a == 1 else (0xFE, 0xFD, 0xFB))[min(ch, 2)]
            self.ym('a', 0x07, v)
        elif a == 3: self.push(0xF0); self.push(self.rd())
        elif a == 4:
            x = self.rd()
            if x != self.f(5): self.push(x)
        elif a == 5: self.push(0xF5); self.push(self.rd())
        elif a == 0x0B: self.push(0xF2); self.push(self.rd())
        elif a == 0x0C: self.sf(0x45, self.f(0x45) | 0x80)
        elif a == 0x0D: self.sf(0x45, self.f(0x45) & 0x7F)

    def end(self, code):
        """$0F93: the block stops (inactive, reply bit cleared, key-off with fast release)"""
        i = self.blocks.index(self.ix); self.ended[i] = self.npass
        self.sf(5, 0); self.gw(0xFC61, self.gr(0xFC61) & ~self.f(0x43))
        self.keyoff_stop(self.f(4))
        return True

    # ------------------------------------------------------------------------------------------- output stage
    def fm_port(self, code):
        ch = code & 0x0F
        return ('a', ch) if ch < 5 else ('b', ch - 4)

    def keyon(self, code):
        """$063A"""
        self.setb(8, 0)
        if code & 0x40:                                     # $0677 ADPCM-A
            c = code & 0x3F; smp = self.f(0x16); tab = self.f(0x41)
            if tab >= 6: return
            iy = self.g['a_tabs'] + (tab << 9) + (((smp * 2) & 0xFF) << 1)
            bit = self.rom(self.g['bits'] + c)
            self.ym('a', 0x1C, bit); self.ym('a', 0x1C, 0)
            for r, o in ((0x10, 1), (0x18, 0), (0x20, 3), (0x28, 2)): self.ym('b', r + c, self.rom(iy + o))
            self.ym('b', 0x00, bit)
        elif code & 0x20:                                   # $06E3 ADPCM-B
            iy = self.f(0x37) | self.f(0x38) << 8
            for r, v in ((0x1B, 0), (0x10, 1), (0x1C, 0x80), (0x1C, 0), (0x10, 0), (0x11, self.f(0x42))):
                self.ym('a', r, v)
            for r, o in ((0x12, 3), (0x13, 2), (0x14, 5), (0x15, 4)): self.ym('a', r, self.rom(iy + o))
            self.pitch(code); self.level(code)
            self.ym('a', 0x10, 0x80)
        elif code & 0x80:                                   # $0660 SSG
            self.ym('a', 0x08 + (code & 0x0F), (self.vol() if self.v11 else self.f(0x0E)) >> 3)  # SDB $05DF: attenuated
            self.pitch(code)
        else:
            self.ym('a', 0x28, code & 0x0F | 0xF0)
            self.pitch(code)

    def keyoff(self, code):
        """$0750: the gate ran out"""
        self.resb(8, 0)
        if code & 0x40: self.ym('b', 0x00, self.rom(self.g['bits'] + (code & 0x3F)) | 0x80)
        elif code & 0x20:
            for r, v in ((0x1B, 0), (0x10, 1), (0x1C, 0x80), (0x1C, 0), (0x10, 0)): self.ym('a', r, v)
        elif code & 0x80: self.ym('a', 0x08 + (code & 0x0F), 0)
        else: self.ym('a', 0x28, code & 0x0F)

    def keyoff_stop(self, code):
        """$07A4: FM key-off + release $FF on the four operators; the others as $0750 (ADPCM-B: $10 = 0 only)"""
        if code & 0x10:
            ch = code & 0x0F
            self.ym('a', 0x28, ch)
            if ch < 5:
                for k in range(4): self.ym('a', 0x80 + ch + 4 * k, 0xFF)
            else:
                for k in range(4): self.ym('b', 0x7C + ch + 4 * k, 0xFF)
        elif code & 0x40: self.ym('b', 0x00, self.rom(self.g['bits'] + (code & 0x3F)) | 0x80)
        elif code & 0x20: self.ym('a', 0x10, 0)
        else: self.ym('a', 0x08 + (code & 0x0F), 0)

    def patch(self, code):
        """$0917: FM patch ($0944, 26 bytes) or ADPCM-B instrument ($0926, 6 bytes)"""
        self.resb(8, 6)
        if code & 0x10:
            base = self.g['patches_ff'] if self.gr(0xFC4E) == 0xFF else self.g['patches']
            hl = (base + 26 * self.f(0x41)) & 0xFFFF
            fbalg = self.rom(hl) & 0x3F; self.sf(0x46, fbalg)
            e = self.rom(self.g['carriers'] + (fbalg & 7)); self.sf(0x47, e)
            p, o = self.fm_port(code)
            hl += 2
            reg = 0x30 + o
            for _ in range(4): self.ym(p, reg, self.rom(hl)); hl += 1; reg += 4
            self.sf(0x37, hl); self.sf(0x38, hl >> 8)
            for _ in range(4):
                v = self.rom(hl); hl += 1
                if e & 1: v = 0x7F
                e >>= 1
                self.ym(p, reg, v); reg += 4
            for _ in range(16): self.ym(p, reg, self.rom(hl)); hl += 1; reg += 4
            self.ym(p, 0xB0 + o, fbalg)
            self.setb(8, 7)
        elif code & 0x20:
            hl = self.g['b_inst'] + 6 * self.f(0x41)
            self.sf(0x37, hl); self.sf(0x38, hl >> 8)
            self.sf(0x4A, self.rom(hl)); self.sf(0x49, self.rom(hl + 1))

    def pan(self, code):
        """$09DA"""
        self.sf(0x45, self.f(0x45) & 0xFE)
        if code & 0x40: self.ym('b', 0x08 + (code & 0x3F), self.alevel())
        elif code & 0x20: self.ym('a', 0x11, self.f(0x42))
        elif code & 0x80: return
        else:
            p, o = self.fm_port(code); self.ym(p, 0xB4 + o, self.f(0x42))

    def vol(self):
        a = self.f(self.VOL)
        if self.f(0x45) & 0x80:
            a -= self.gr(0xFC65)
            if a < 0: a = 0
        return a

    def alevel(self): return (self.vol() >> 2) | self.f(0x42)

    def level(self, code):
        """$0B4C FM carrier TLs, $0BB4 ADPCM-B $1B, $0BD0 ADPCM-A level, $0BF8 SSG (only while the note is on)"""
        self.resb(8, 7)
        if code & 0x40: self.ym('b', 0x08 + (code & 0x3F), self.alevel())
        elif code & 0x20: self.ym('a', 0x1B, self.vol() * 2)
        elif code & 0x80:
            if not self.bit(8, 0): return
            self.ym('a', 0x08 + (code & 0x0F), self.vol() >> 3)
        else:
            b = self.rom(self.g['vol'] + self.vol())
            hl = self.f(0x37) | self.f(0x38) << 8
            p, o = self.fm_port(code); e = self.f(0x47)
            for k in range(4):
                if e >> k & 1:
                    t = self.rom(hl + k)
                    self.ym(p, 0x40 + o + 4 * k, (t - b) if t < b else 0x7F)

    def pitch(self, code):
        """$0A2D FM F-number, $0AA2 ADPCM-B delta-N, $0AF7 SSG period: note.fine + vibrato + slide"""
        self.resb(8, 5)
        hl = ((self.f(0x15) | self.f(0x16) << 8) + (self.f(0x2D) | self.f(0x2E) << 8)
              + (self.f(0x21) | self.f(0x22) << 8)) & 0xFFFF
        if code & 0x20:
            hl = (hl + (self.f(0x49) | self.f(0x4A) << 8)) & 0xFFFF
            d, e = hl >> 8, hl & 0xFF
            t = self.g['b_dn'] + 4 * d
            c, _ = mul(self.rom(t), d)
            h2, l2 = mul(self.rom(t + 1), e)
            a = l2 + c; bc = ((h2 + (a >> 8)) & 0xFF) << 8 | a & 0xFF
            v = ((self.rom(t + 2) | self.rom(t + 3) << 8) + bc) & 0xFFFF
            self.ym('a', 0x19, v); self.ym('a', 0x1A, v >> 8)
        elif code & 0x80:
            d, e = hl >> 8, hl & 0xFF
            t = self.g['ssg'] + 4 * d
            c, _ = mul(self.rom(t), e)
            h2, l2 = mul(self.rom(t + 1), d)
            a = l2 + c; bc = ((h2 + (a >> 8)) & 0xFF) << 8 | a & 0xFF
            v = ((self.rom(t + 2) | self.rom(t + 3) << 8) - bc) & 0xFFFF
            r = (code & 7) * 2
            self.ym('a', r, v); self.ym('a', r + 1, v >> 8)
        else:
            d, e = hl >> 8, hl & 0xFF
            octv, semi = divmod(d, 12)
            t = self.g['fnum'] + 4 * semi
            c, _ = mul(self.rom(t), e)
            v = (self.rom(t + 2) | self.rom(t + 3) << 8) + c
            if v >> 8 >= 4 and v & 0xFF >= 0xD3: v = (v - 0x4D3) | 0x800
            hi = (octv * 8 + (v >> 8)) & 0xFF
            p, o = self.fm_port(code)
            self.ym(p, 0xA4 + o, hi); self.ym(p, 0xA0 + o, v)

    def vibrato(self):
        """$081A: delay, phase += speed x 128, depth ramp at each phase wrap, then the waveform ($2C: 0 / 1 = triangle
        (the driver's result keeps the phase byte as its low byte), 2 = triangle, 3+ = square)"""
        if self.f(0x33): self.sf(0x33, self.f(0x33) - 1); return
        self.setb(8, 5)
        bc = self.f(0x2A) << 7 & 0xFFFF
        hl = (self.f(0x35) | self.f(0x36) << 8) + bc
        carry = hl > 0xFFFF
        if carry: hl = 0
        self.sf(0x35, hl); self.sf(0x36, hl >> 8)
        c = hl >> 8
        if carry and self.f(0x34):
            a = self.f(0x2F) + self.f(0x31); self.sf(0x2F, a)
            self.sf(0x30, self.f(0x30) + self.f(0x32) + (a >> 8))
            self.sf(0x34, self.f(0x34) - 1)
        w = self.f(0x2C)
        if w >= 3:
            v = self.f(0x30) * 8
            if c & 0x80: v = -v
            v &= 0xFFFF; self.sf(0x2D, v); self.sf(0x2E, v >> 8); return
        if w == 2:
            a = c
            if c & 0x80: a = (-a) & 0xFF
            a = (a * 2) & 0xFF
            if a & 0x80: a = (-a) & 0xFF
            a >>= 2
            b, a = mul(a, self.f(0x30)); v = (b << 8 | a) >> 2
            if c & 0x80: v = (-v) & 0xFFFF
            self.sf(0x2D, v); self.sf(0x2E, v >> 8); return
        d = 0x80 if w == 1 else 0
        a = c ^ 0xFF if c & 0x80 else c
        a = ((a * 2) & 0xFF) >> 2
        b, a = mul(a, self.f(0x30)); v = (b << 8 | a) >> 2
        b = v >> 8
        a = c ^ d
        if a & 0x80: v = (-(b << 8 | a)) & 0xFFFF
        else: v = b << 8 | a
        self.sf(0x2D, v); self.sf(0x2E, v >> 8)

# ------------------------------------------------------------------------------------------------- song runs
class Song:
    """one sound command played from a reset driver: the command is read before pass 1"""
    def __init__(self, data, cmd, listing=False):
        self.d = data; self.cmd = cmd
        self.drv = Driver(data, listing)
        if cmd > 0xFF: self.drv.push(0xF9 + (cmd >> 8)); self.drv.push(cmd & 0xFF)   # SDB pages 1-2: $FA / $FB
        else: self.drv.push(cmd)
        self.e = entry(data, cmd)

    def run(self, passes):
        for _ in range(passes):
            self.drv.pass_()
            if not any(self.drv.r(b + 5) for b in self.drv.blocks) and self.drv.npass > 4 and self.drv.gr(0xFC4F) == self.drv.gr(0xFC51):
                break
        return self

    @property
    def writes(self): return self.drv.writes
    @property
    def log(self): return self.drv.log

    def active(self): return any(self.drv.r(b + 5) for b in self.drv.blocks)

    def loop_ticks(self):
        """channel name -> (loop tick, length): the first jump back to an address the channel already played (the
        target's first tick, the jump's tick minus it)"""
        out = {}
        for i, js in self.drv.loops.items():
            for q, t, target in js:
                if (i, target) in self.drv.seen and self.drv.seen[(i, target)] < t:
                    L = self.drv.seen[(i, target)]; out[NAMES[i]] = (L, t - L); break
        return out

    def tempo(self):
        return self.drv.r(self.drv.blocks[self.e['streams'][0][0]] + 0x12)

def loop_passes(data, cmd, limit=60000):
    """passes to the point where every looping channel has jumped back once (or the song ended), from a listing run"""
    s = Song(data, cmd).run(limit)
    if not s.active(): return s.drv.npass, False
    first = [v[0][0] for v in s.drv.loops.values() if v]
    return (max(first) if first else s.drv.npass), True

def summary(data, cmd):
    e = entry(data, cmd)
    s = Song(data, cmd, listing=True)
    n, loops = loop_passes(data, cmd)
    s.run(n + 1)
    print(f'sound ${cmd:02X}: bank {e["bank"]} ${e["addr"]:04X}, class {e["cls"]} priority ${e["prio"]:02X} kills '
          f'{e["kill"][0]:02X}-{e["kill"][1]:02X}, mask ${e["mask"]:04X}; {n} passes ({n / PASS_HZ:.1f} s) to '
          + ('the loop' if loops else 'the end'))
    for b, addr in e['streams']:
        ev = [x for x in s.log if x[1] == b]
        notes = sum(1 for x in ev if x[4].startswith(('note', 'sample')))
        print(f'  {NAMES[b]:5s} ${addr:04X}: {notes} notes, {s.drv.ticks[b]} ticks' +
              (f', jump at pass {s.drv.loops[b][0][0]}' if s.drv.loops.get(b) else '') +
              (f', ends at pass {s.drv.ended[b]}' if b in s.drv.ended else ''))

def listing(data, cmd, passes):
    s = Song(data, cmd, listing=True).run(passes)
    for p, b, t, pos, txt in sorted(s.log, key=lambda x: (x[1], x[0])):
        print(f'{NAMES[b]:5s} pass {p:5d} tick {t:4d} ${pos:04X}  {txt}')

def catalog(data):
    for c in range(0xF0):
        e = entry(data, c)
        if not e: continue
        print(f'${c:02X} bank {e["bank"]} ${e["addr"]:04X} class {e["cls"]:02X} prio {e["prio"]:02X} kill '
              f'{e["kill"][0]:02X}-{e["kill"][1]:02X} channels ' + ' '.join(NAMES[b] for b, _ in e['streams']) +
              (' (one of A4-A6)' if e['mask'] == 0x100 else ''))

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    if sys.argv[2] == '--catalog': catalog(data); sys.exit()
    cmd = int(sys.argv[2], 16)
    if '--list' in sys.argv:
        i = sys.argv.index('--list'); listing(data, cmd, int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 3000)
    elif '--writes' in sys.argv:
        i = sys.argv.index('--writes'); n = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 300
        s = Song(data, cmd).run(n); last = None
        for q, p, r, v in s.writes:
            if q != last: print(f'-- pass {q}'); last = q
            print(f'  {p} {r:02X} {v:02X}')
    else: summary(data, cmd)
