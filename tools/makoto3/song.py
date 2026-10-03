#!/usr/bin/env python3
"""Song decoder + tick-exact player model of the "Ver 3.0 by MAKOTO" sound driver (Fatal Fury 3, KOF94, KOF95):
docs/ff3_sound_driver.md (sections "KOF94's build", "KOF95's build"), docs/ff3_songs.md, docs/kof94_songs.md,
docs/kof95_songs.md.

    python3 song.py M1.bin 0x21                 summary (channels, notes, loop points)
    python3 song.py M1.bin 0x21 --list [TICKS]  full event listing per channel (tick, address, event, params)
    python3 song.py M1.bin 0x21 --keys [TICKS]  predicted chip events (key-on/off, F-number, sample, delta-N, TL)
    python3 song.py M1.bin --catalog            one line per music command

The game comes from the M1 ROM (games.game_of); its table addresses from games.GAMES. Code addresses below are
FF3's (KOF94's build is the same code, shifted; KOF95's a reworked build: docs/ff3_sound_driver.md).

The model ports the Z80 code where it matters for timing and the YM2610 writes:
- two clocks: timer B (value = the song's tempo byte, reg $26) runs the music, one sequencer tick per timer-B
  interrupt ($2243); timer A (value 1, 54.3 Hz, set at reset by $2B87) runs the FM software vibrato ($1C8E), the
  ADPCM-B effects ($1F2B, $1E6F) and the sound-effect channels. run() takes the interrupt sequence ('A' / 'B' per
  interrupt, measured: capture.py's "i" lines) or makes one from the two timer periods (timers()).
- per tick, channels in block order FM1-4 ($FCEC...), ADPCM-A 1-6 ($FD2C...), ADPCM-B ($FD8C), 16-byte blocks, the
  state machine at $2334 (bit 0 note on, bit 1 gate running: IX+4 gate countdown, IX+5 the rest after it);
- events read by $24EC until a note or rest ($2579), opcodes $30-$5F through the jump table $25FA;
- $40 / $47 / $55 end the interrupt at once (LD SP,($FE24) / JP $24C9): the channels after them skip the tick.
Everything here is read from the code; docs/ff3_sound_driver.md gives the addresses."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from games import GAMES, game_of, music_cmds

CHANNELS = ['FM1', 'FM2', 'FM3', 'FM4', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'B']
CODE = [1, 2, 3, 4, 8, 9, 10, 11, 12, 13, 14]            # $FE3C channel id of each header slot / block
NOTE = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
# the note byte's low nibble is the F-number table index ($7F0F): the natural notes A-F are spelled with the hex
# digits A-F, G = 0, the sharps C# D# F# G# A# = 1 2 4 5 6 (3, 7-9 unused: F-number 0). $20EB: nibble -> semitone
NIB_SEMI = [7, 1, 3, 0, 6, 8, 10, 0, 0, 0, 9, 11, 0, 2, 4, 5]
TA_UNITS, TB_UNITS = 1023, 16                             # timer periods in 18 us units: A = 1024 - 1, B = 16 * (256 - TB)

def nib_name(n):
    return {0xC: 'C', 1: 'C#', 0xD: 'D', 2: 'D#', 0xE: 'E', 0xF: 'F', 4: 'F#', 0: 'G', 5: 'G#', 0xA: 'A', 6: 'A#',
            0xB: 'B'}.get(n, f'?{n:X}')

def note_name(b):
    """FM / ADPCM-B note byte: bits 7-5 octave (= YM block: C4 = F-number 618 block 4 = 261.6 Hz), bit 4 unused,
    bits 3-0 the note code (nib_name)"""
    return f'{nib_name(b & 0x0F)}{b >> 5}' + ('+16' if b & 0x10 else '')

class M1:
    """the Z80's view: $0000-$7FFF fixed, $8000-$FFFF one of the build's 32 KB maps ($1151: bank byte [song]).
    FF3: 0 = $01B0 identity, 1 = ports $08-$0B <- $2E,$16,$0A,$04, 2 = $3E,$1E,$0E,$06; KOF94: 0 and 1"""
    def __init__(self, data):
        self.d = data; self.base = 0x8000
        self.game = game_of(data); self.g = GAMES[self.game]
    def bankset(self, n): self.base = self.g['banks'][n]
    def phys(self, a): return a if a < 0x8000 else self.base + a - 0x8000
    def rd(self, a): return self.d[self.phys(a & 0xFFFF)]
    def w(self, a): return self.rd(a) | self.rd(a + 1) << 8

def s8(v): return v - 256 if v & 0x80 else v
def s16(v): return v - 0x10000 if v & 0x8000 else v

# opcodes: name, parameter bytes, handler (jump table $25FA: 3-byte JPs, opcode - $30; $30 itself is a length, its
# entry is never reached)
OPS = {
    0x30: ('nop', 0, 0x268A), 0x31: ('loop', 1, 0x2A3B), 0x32: ('loop', 1, 0x2A3B), 0x33: ('tempo', 1, 0x281E),
    0x34: ('next', 0, 0x2A93), 0x35: ('call', 2, 0x2AAF), 0x36: ('return', 0, 0x2AC8), 0x37: ('timerA', 2, 0x2827),
    0x38: ('next', 0, 0x2A93), 0x39: ('goto', 2, 0x2A35), 0x3A: ('transpose', 1, 0x2B18), 0x3B: ('sample_fx', 1, 0x2AE0),
    0x3C: ('nop', 0, 0x268A), 0x3D: ('gatemode', 1, 0x2B02), 0x3E: ('nop', 0, 0x268A), 0x3F: ('fade', 1, 0x2B0C),
    0x40: ('stop', 0, 0x29F3), 0x41: ('halt', 0, 0x29EF), 0x42: ('restart', 0, 0x2A27), 0x43: ('b_fx', 1, 0x2AF1),
    0x44: ('pan', 1, 0x294F), 0x45: ('b_loop_off', 0, 0x2949), 0x46: ('b_mode', 1, 0x2902), 0x47: ('song', 1, 0x28F6),
    0x48: ('nop', 0, 0x268A), 0x49: ('nop', 0, 0x268A), 0x4A: ('nop', 0, 0x268A), 0x4B: ('b_pitch_fx', 8, 0x2898),
    0x4C: ('b_pitch_fx_on', 1, 0x288A), 0x4D: ('a_loops_off', 0, 0x293A), 0x4E: ('lfo', 1, 0x2881),
    0x4F: ('vib_off', 1, 0x286D), 0x50: ('reg', 2, 0x2864), 0x51: ('ssg_noise', 1, 0x285D), 0x52: ('fc37', 1, 0x2891),
    0x53: ('ssg_env', 3, 0x2845), 0x54: ('ssg_song', 1, 0x280D), 0x55: ('ssg_end', 0, 0x27F3), 0x56: ('volume', 1, 0x27EA),
    0x57: ('b_level_fx', 5, 0x279E), 0x58: ('b_fx_flag', 1, 0x278B), 0x59: ('b_stop', 0, 0x276A),
    0x5A: ('a_fx_stop', 0, 0x2714), 0x5B: ('b_level_fx_on', 1, 0x270A), 0x5C: ('fa89', 1, 0x2703),
    0x5D: ('fc37', 1, 0x26FC), 0x5E: ('b_slide', 1, 0x26F5), 0x5F: ('ssg_sweep', 1, 0x268C)}

def parse(m, pos, chan):
    """One event at pos -> dict(kind, pos, next, ...). chan = $FE3C channel id. Kinds: 'note' / 'rest' (with len,
    gate computed later), 'inst' (patch + up to three trailing bytes), 'op' (opcode), 'bad' ($60-$7F: $24EC spins)."""
    ev = {'pos': pos}
    b = m.rd(pos)
    if b == 0 or b <= 0x30:                                 # $2575 / $2579: [0, len] or [len 1-$30]
        if b == 0: pos += 1; b = m.rd(pos)
        ev['len'] = b
        f = m.rd(pos + 1)
        if f & 0x40:                                        # $25CF: rest, the next byte is skipped
            ev.update(kind='rest', flag=f); ev['next'] = pos + 3; return ev
        n = m.rd(pos + 2)
        ev.update(kind='note', tie=not f & 0x80, att=f & 0x3F, note=n); ev['next'] = pos + 3; return ev
    if b >= 0x80:                                           # $250A: patch b - $80, then optional bytes with bit 7 set
        ev.update(kind='inst', p=b - 0x80); pos += 1
        extra = []
        for _ in range(3):                                  # $252B volume, $255B octave, $2553 detune (positional)
            if m.rd(pos) & 0x80: extra.append(m.rd(pos)); pos += 1
            else: break
        ev['extra'] = extra; ev['next'] = pos; return ev
    if b >= 0x60:
        ev.update(kind='bad', op=b); ev['next'] = pos; return ev
    name, n, _ = OPS[b]
    ev.update(kind='op', op=b, name=name, args=[m.rd(pos + 1 + i) for i in range(n)])
    if b == 0x5F and chan not in (5, 6, 7): ev['args'] = []  # $269C: on other channels the byte is not consumed
    ev['next'] = pos + 1 + len(ev['args'])
    return ev

def fmt(ev, chan):
    k = ev['kind']
    if k in ('note', 'rest'):
        s = f"len {ev['len']}"
        if k == 'rest': return 'rest ' + s
        nm = note_name(ev['note']) if chan <= 4 or chan == 14 else f"smp ${ev['note']:02X}"
        return f"note {nm} (${ev['note']:02X}) att ${ev['att']:02X} {s}" + (' tie' if ev['tie'] else '')
    if k == 'inst':
        names = ['vol', 'oct', 'det']
        x = ' '.join(f'{names[i]} ${v:02X}' for i, v in enumerate(ev['extra']))
        return f"inst ${ev['p']:02X}" + (f' ({x})' if x else '')
    if k == 'bad': return f"BAD ${ev['op']:02X}"
    a = ev['args']
    if ev['op'] in (0x35, 0x39): return f"{ev['name']} ${a[0] | a[1] << 8:04X}"
    return f"{ev['name']} " + ' '.join(f'${v:02X}' for v in a)

# ------------------------------------------------------------------------------------------------ the player model

class Vib:
    """FM software vibrato record ($FC83 + 16 * channel), stepped by timer A ($1C8E); set from patch bytes $2A-$30
    ($1A2C). No FF3 patch sets a depth, so no song runs it (ported, not validated)."""
    def __init__(self): self.step = self.type = self.delay = self.depth = self.val = self.f = self.dcnt = 0; self.rnd = 0; self.scnt = self.speed = 0

class Chan:
    def __init__(self, k, sp, flags):
        self.k, self.name, self.code = k, CHANNELS[k], CODE[k]
        self.status = 0; self.flags = flags                     # IX+0, IX+1 (bit 0 on, bits 7-6 pan)
        self.vol = self.att = self.gate = self.rest = self.nib = self.trans = self.bmode = 0   # IX+2..+8
        self.hi = self.octv = self.det = 0                     # IX+D, IX+E, IX+F
        self.pos = self.start = sp
        self.loops = []; self.calls = []
        self.visited = {}; self.pending = None

class Song:
    def __init__(self, data, cmd, listing=False):
        self.m = M1(data)
        if data[self.m.g['types'] + cmd] != 2: raise ValueError('not a music command')
        self.ch = None; self.shadow = {}                      # shadow: FM register mirror {(code, reg): val}
        self.out = []                                         # chip events: (irq, tick, chan, kind, data)
        self.irq = 0; self.tick = 0
        self.cmd0 = cmd
        self.fade = 0; self.fade_speed = 0                    # $FE27, $FABE+2
        self.fe38 = self.fe39 = 0; self.fabe0 = 0             # fade accumulators, $FABE+0 (bit 3 FM done, bit 5 B done)
        self.start(cmd)
        self.ptr0, self.bank0, self.tempo0 = self.ptr, self.bank, self.tempo   # (a chained song replaces them)
        self.vib = {c: Vib() for c in (1, 2, 3, 4)}
        self.vib_off = {c: 0 for c in (1, 2, 3, 4)}           # $FC3D + id - 1 ($4F)
        self.fe40 = 0                                         # ADPCM-B sample table / sample ($46)
        self.listing = listing; self.log = []
        self.queued = []
        self.emit(None, 'start', cmd=cmd)

    def start(self, cmd):
        """$111B: the song's header -> the 11 channel blocks. Only status, flags, stream pointers, gate modes and the
        loop / call stacks are set: volume, transpose, octave, detune, ADPCM-B mode ... carry over from what played
        before (all 0 after a reset)."""
        m = self.m; i = cmd - 0x20
        self.cmd = cmd
        g = m.g
        self.bank = self.m.d[g['bank_tab'] + i]; m.bankset(self.bank)
        self.ptr = ptr = m.w(g['headers'] + 2 * i)
        # $FEF8: this song's ADPCM-A sample records (FF3); KOF94: always effect slot 0's table ($0447)
        self.smp = m.w(g['smp_tab'] + 2 * i) if g['smp_tab'] else g['smp_fixed']
        self.head = h = [m.rd(ptr + k) for k in range(0x30)]
        self.tempo = h[0x17]                                  # timer B value ($2B75)
        if not self.fade:                                     # $13D6: a fade keeps its levels
            self.fm_att, self.a_vol, self.b_vol = h[0x18], h[0x19], h[0x1A]   # $FABE+1, +6 (reg $01), +7
            self.fe38 = self.fe39 = 0
        self.sp = [h[1 + 2 * k] | h[2 + 2 * k] << 8 for k in range(11)]
        self.on = [h[0x1B + 2 * k] & 1 for k in range(11)]
        old = self.ch
        self.ch = [Chan(k, self.sp[k], h[0x1B + 2 * k] | 0xC0) for k in range(11)]
        if old:
            for a, b in zip(old, self.ch):
                for f in ('vol', 'att', 'gate', 'rest', 'nib', 'trans', 'bmode', 'hi', 'octv', 'det'): setattr(b, f, getattr(a, f))
        self.gmode = {c: 7 for c in CODE}                     # $FCDD + id ($2B63)
        self.running = True                                   # $FE2D
        self.loop_at = {}

    def emit(self, ch, kind, **kw): self.out.append((self.irq, self.tick, ch.name if ch else '-', kind, kw))

    # -- pitch: $2459 / $20CF -> index byte: bits 7-5 block, bits 4-0 F-number table entry ($7F0F)
    def pitch_index(self, ch):
        a = (ch.trans + NIB_SEMI[ch.nib]) & 0xFF            # $20CF: transpose + semitone, signed index into $2113
        e = self.m.rd(self.m.g['pitch'] + s8(a))
        return (ch.octv + ch.hi + e) & 0xFF                  # $2462: + IX+E (octave shift) + IX+D (octave)

    def fm_key(self, ch, d, e):
        """$14B5: write $28 = channel | D (D = key bits); on a key-on also the F-number (after the key-on)"""
        self.emit(ch, 'key', d=d)
        if not d & 0xF0: return
        fn = self.m.w(self.m.g['fnum'] + 2 * (e & 0x1F))
        fn = (fn + s8(ch.det)) & 0xFFFF                      # $1507: + IX+F (signed)
        hi = ((e >> 2) & 0x38 | fn >> 8) & 0xFF              # block bits OR the F-number's high byte
        self.shadow[(ch.code, 'fnum')] = hi << 8 | fn & 0xFF
        self.emit(ch, 'fnum', a4=hi, a0=fn & 0xFF)
        v = self.vib[ch.code]                                # $1E3D
        if v.delay: v.dcnt = v.delay; v.f = 0; v.scnt = v.speed
        else: v.f |= 8

    def fm_tl(self, ch):                                     # $237C: FABE+1 + IX+2 + IX+3, carry of the 2nd add only
        a = (self.fm_att + ch.vol) & 0xFF
        a2 = a + ch.att
        tl = 0x7F if a2 > 0xFF or (a2 & 0xFF) >= 0x7F else a2 & 0xFF
        self.emit(ch, 'tl', tl=tl)

    def output(self, ch):
        """$2366: after the events of a tick, the note / rest goes to the chip. D = status & $F0"""
        c = ch.code; d = ch.status & 0xF0
        if c <= 4:                                           # FM ($2372)
            e = self.pitch_index(ch)
            self.fm_tl(ch)
            if not ch.status & 8: self.fm_key(ch, 0, e)       # $17A8 with D = 0: key-off first unless a tie
            self.fm_key(ch, d, e)
        elif c < 14:                                         # ADPCM-A ($23C9 -> $162F)
            lvl = (ch.vol - ch.att) & 0xFF
            if ch.vol < ch.att: lvl = 0
            b = (ch.flags & 0xC0) | lvl
            if not d: self.emit(ch, 'adump'); return          # $17D1
            if not self.fade: self.emit(ch, 'alevel', v=b)     # $2C5C: reg $08+ch = pan | level (raw, not masked)
            if ch.status & 8: return                          # tie: the sample keeps playing
            rec = self.smp + 11 * ch.hi
            m = self.m
            info = dict(sample=ch.hi, start=m.w(rec + 1), end=m.w(rec + 3), loops=m.rd(rec + 5))
            if info['loops']: info.update(lstart=m.w(rec + 6), lend=m.w(rec + 8))
            self.emit(ch, 'akey', **info)
        else:                                                # ADPCM-B ($23EA)
            if ch.bmode == 1: e = ch.nib | ch.hi
            else: e = self.pitch_index(ch)
            vol = (self.b_vol + ch.vol) & 0xFF                # $2404: the add's carry is not tested ...
            for _ in range(3):                                # ... three subtractions of the attenuation, floor 0
                if vol < ch.att: vol = 0; break
                vol -= ch.att
            if ch.status & 4: d2 = d                          # rest: $2434
            elif ch.status & 8: d2 = 5                        # tie: $2448, D = 5
            else: d2 = d
            self.b_key(ch, d2, e, vol)
            if not ch.status & 4: self.emit(ch, 'bpan', pan=ch.flags & 0xC0)

    def b_key(self, ch, d, e, vol):                          # $1683
        if not d: self.emit(ch, 'boff'); return             # $180A: $11 = 0
        m = self.m; g = m.g
        if ch.bmode == 0:                                    # $1718 -> $1830: one sample per octave
            o = e >> 5
            smp = m.rd(self.fe40 + o)
            dn = m.w(g['b_dn_oct'] + 2 * ((e & 0x0F) | (e & 0xE0) >> 1))
        elif ch.bmode == 1:                                  # $175C: kit, the note byte is the sample
            smp = e; dn = None
        else:                                                # $16D4 -> $1856: one sample, pitched
            idx = ((((e & 0xE0) - 0x40) & 0xFF) >> 1 & 0x70) | (e & 0x0F)
            dn = m.w(g['b_dn_pitched'] + 2 * idx); smp = self.fe40 & 0xFF
        rec = g['brec'] + g['brec_size'] * smp              # $0913 (KOF94: 26-byte records)
        if dn is None: dn = m.w(rec + 10)
        if d == 5: self.emit(ch, 'bslur', deltan=dn, vol=vol); return   # $083E
        info = dict(sample=smp, deltan=dn, start=m.w(rec + 1), end=m.w(rec + 3), vol=vol, loops=m.rd(rec + 5))
        if info['loops']: info.update(lstart=m.w(rec + 6), lend=m.w(rec + 8))
        self.emit(ch, 'bkey', **info)

    def keyoff(self, ch):                                    # $17A8 with D = 0 (gate end)
        c = ch.code
        if c <= 4: self.emit(ch, 'key', d=0)
        elif c < 14: self.emit(ch, 'adump')
        else: self.emit(ch, 'boff')

    # -- one sequencer tick of one channel: $2334
    def run_channel(self, ch):
        if not ch.flags & 1: return True
        if ch.status & 1:
            if ch.status & 2:                                # $2471: gate
                ch.gate = (ch.gate - 1) & 0xFF
                if ch.gate: return True
                ch.status &= ~2
                if ch.rest:
                    if not ch.status & 8: self.keyoff(ch)
                    return True
            else:                                            # $248D: rest after the gate
                ch.rest = (ch.rest - 1) & 0xFF
                if ch.rest: return True
            ch.status &= ~1                                  # $2491 (a key-off here only for SSG channels)
        return self.read(ch)

    def read(self, ch):
        """$234C: status = (status & 8) | $F3, events until a note / rest ($24EC), then the output ($2366).
        Returns False when an opcode ended the interrupt."""
        m = self.m
        ch.status = (ch.status & 8) | 0xF3
        for _ in range(100000):
            if ch.pos == ch.pending and ch.name not in self.loop_at:
                self.loop_at[ch.name] = (ch.visited[ch.pos], self.tick - ch.visited[ch.pos], ch.pos)
                if self.listing: self.log.append((self.tick, ch.name, ch.pos, f'---- loop: back to ${ch.pos:04X} '
                                                  f'(first played at tick {ch.visited[ch.pos]}), period {self.tick - ch.visited[ch.pos]} ticks'))
            ch.visited.setdefault(ch.pos, self.tick)
            ev = parse(m, ch.pos, ch.code)
            if self.listing:
                txt = fmt(ev, ch.code)
                if ev['kind'] in ('note', 'rest'):
                    g = self.gate_of(ch, ev['len'])
                    if g != ev['len']: txt += f' gate {g}'
                self.log.append((self.tick, ch.name, ch.pos, txt))
            k = ev['kind']
            if k == 'bad': self.log.append((self.tick, ch.name, ch.pos, 'driver hangs here')); ch.flags &= ~1; return True
            ch.pos = ev['next']
            if k in ('note', 'rest'):
                self.length(ch, ev['len'])
                if k == 'rest':
                    ch.status = (ch.status & 0x0F) | 4         # $25DA
                else:
                    if ev['tie']: ch.status |= 8
                    else: ch.status &= ~8
                    ch.att = ev['att']
                    n = ev['note']
                    if ch.code <= 4 or ch.code == 14: ch.nib = n & 0x0F; ch.hi = n & 0xF0
                    else: ch.hi = n
                self.output(ch)
                return True
            if k == 'inst':
                self.instrument(ch, ev)
                continue
            r = self.execute(ch, ev)
            if r == 'abort': return False
        raise RuntimeError('runaway')

    def gate_of(self, ch, n):
        """$2B21: the gate of a length-n event under the channel's gate mode ($FCDD, opcode $3D): mode 7 = n;
        else (n >> 3) * (mode + 1), or for n < 8 the table $2CA3 [n][mode]"""
        q = (n >> 3) & 0x1F; mode = self.gmode[ch.code]
        if mode == 7: return n
        if q: return (q * (mode + 1)) & 0xFF
        return self.m.rd(self.m.g['gate'] + 8 * n + mode)

    def length(self, ch, n):
        g = self.gate_of(ch, n)
        ch.gate, ch.rest = g, (n - g) & 0xFF

    def instrument(self, ch, ev):                            # $250A
        c = ch.code
        if 1 <= c <= 4: self.load_patch(ch, ev['p'])
        x = ev['extra']
        if len(x) > 0:                                       # $252B
            if c < 8: ch.vol = (x[0] - 0x88) & 0xFF
            elif c == 14: ch.vol = (x[0] - 0xB8) & 0xFF
            elif not self.fade: ch.vol = (x[0] - 0x80) & 0xFF
        if len(x) > 1:                                       # $255B: octave shift +-(b & $0E)/2 in units of $20
            v = x[1] & 0x0F
            v = (-(v & 0x0E)) & 0xFF if v & 1 else v & 0x0E
            ch.octv = ((v >> 4 | v << 4) & 0xF0)
        if len(x) > 2: ch.det = (x[2] - 0xB8) & 0xFF          # $2553

    def load_patch(self, ch, p):                             # $18A4 (52-byte patch at $2E40 + 52p) + $1A8C (writes)
        m = self.m; a = m.g['patches'] + 52 * p
        q = [m.rd(a + i) for i in range(52)]
        self.emit(ch, 'patch', p=p, addr=a)
        v = self.vib[ch.code]                                # $1A2C
        v.type, v.delay, v.step = q[0x2A], q[0x2B], q[0x2C] | q[0x2D] << 8
        v.f = 0
        st = s8(q[0x2F])
        v.depth = (q[0x2E] * st) & 0xFFFF if q[0x2E] else 0
        v.speed = q[0x30]

    def execute(self, ch, ev):
        op, a = ev['op'], ev['args']
        c = ch.code
        guard = self.m.g.get('stack_guard')                 # KOF95: depth 4 at most, games.py
        if op in (0x31, 0x32):
            if guard and len(ch.loops) >= 4: self.log.append((self.tick, ch.name, ev['pos'], 'loop start ignored (depth 4)'))
            else:
                if len(ch.loops) >= 5: self.log.append((self.tick, ch.name, ev['pos'], 'LOOP STACK OVERFLOW'))
                ch.loops.append([a[0], ch.pos])
        elif op in (0x34, 0x38):
            if ch.loops:
                ch.loops[-1][0] = (ch.loops[-1][0] - 1) & 0xFF
                if ch.loops[-1][0]: ch.pos = ch.loops[-1][1]
                else: ch.loops.pop()
            else: self.log.append((self.tick, ch.name, ev['pos'], 'loop end with an empty stack'))
        elif op == 0x35:
            if guard and len(ch.calls) >= 4: self.log.append((self.tick, ch.name, ev['pos'], 'call ignored (depth 4)'))
            else: ch.calls.append(ch.pos); ch.pos = a[0] | a[1] << 8
        elif op == 0x36:
            if ch.calls: ch.pos = ch.calls.pop()
        elif op == 0x39: self.mark_jump(ch, a[0] | a[1] << 8); ch.pos = a[0] | a[1] << 8
        elif op == 0x42: self.mark_jump(ch, ch.start); ch.pos = ch.start
        elif op == 0x33: self.tempo = a[0]; self.emit(ch, 'tempo', tb=a[0])
        elif op == 0x37: self.emit(ch, 'timerA', r25=a[0], r24=a[1])
        elif op == 0x3A: ch.trans = (a[0] - 0x88) & 0xFF
        elif op == 0x3D: self.gmode[c] = a[0] & 7
        elif op == 0x3F: self.fade = 1; self.fade_speed = a[0]
        elif op == 0x40:                                     # $29F3: stop: keys off, B reset, A1-3 dump, end the IRQ
            self.running = False; self.emit(ch, 'stop'); return 'abort'
        elif op == 0x41: self.emit(ch, 'halt'); self.running = False; return 'abort'
        elif op == 0x44: self.pan(ch, a[0])
        elif op == 0x46:                                     # $2902
            p = a[0]
            if p < 0x40: ch.bmode = 1
            elif p < 0x80: self.fe40 = self.m.rd(self.m.g['b_single'] + p - 0x40); ch.bmode = 2
            elif p < 0xC0: self.fe40 = self.m.g['b_octtab'] + 8 * (p - 0x80); ch.bmode = 0
        elif op == 0x47:                                     # $28F6: start song p, end the IRQ
            self.queued.append((self.tick, ch.name, a[0]))
            if self.m.d[self.m.g['types'] + a[0]] == 2: self.start(a[0]); self.emit(ch, 'start', cmd=a[0])
            else: self.running = False
            return 'abort'
        elif op == 0x4E: self.emit(ch, 'lfo', v=a[0])
        elif op == 0x4F: self.vib_off[c] = a[0]
        elif op == 0x50: self.emit(ch, 'reg', r=a[0], v=a[1])
        elif op == 0x55: self.emit(ch, 'ssg_end'); return 'abort'
        elif op == 0x56: ch.vol = (a[0] - 0x80) & 0xFF
        else:
            self.emit(ch, 'op', op=op, args=a)                # opcodes no song uses: listed, not modelled
        return None

    def pan(self, ch, p):                                    # $294F
        c = ch.code; bits = (p & 3) << 6                      # AND 3, RRCA, RRCA
        if c <= 4:                                            # $298D: $B4 shadow & $3F | pan, written; IX+1 |= pan
            ch.flags |= bits
            self.emit(ch, 'pan', pan=bits)
        elif c < 14: ch.flags = ch.flags & 0x3F | bits        # ADPCM-A: only the level shadow, no write
        else: ch.flags = ch.flags & 0x3F | bits

    def mark_jump(self, ch, target):
        if ch.name not in self.loop_at and not ch.loops and not ch.calls and target in ch.visited:
            ch.pending = target

    def music_tick(self):                                    # $2243 (timer B)
        if not self.running: return
        self.tick += 1
        if self.fade and not self.fade_step(): return
        for ch in self.ch:
            if not self.run_channel(ch): return
            if self.fade: self.fade_refresh(ch)

    def fade_step(self):
        """$1AFC: $FE38 += speed; on a carry $FE39 -= 1, and a step if it was not 0 ($1B16). Returns False when the
        fade has ended the song ($1C7F -> $29F4: the stop of opcode $40, then the end of the interrupt)."""
        a = self.fe38 + self.fade_speed; self.fe38 = a & 0xFF
        if a < 0x100: return True
        was = self.fe39; self.fe39 = (self.fe39 - 1) & 0xFF
        if not was: return True
        if self.fabe0 & 0x28 == 0x28:
            self.fabe0 &= 0xC7; self.fade = 0; self.running = False; self.emit(None, 'stop'); return False
        self.fm_att = (self.fm_att + 1) & 0xFF
        if self.fm_att > 0x3C:                               # $1BCF: the six ADPCM-A channels are switched off
            for ch in self.ch[4:10]: ch.flags = 0
        if self.fm_att > 0x5A: self.fm_att = 0x7E; self.fabe0 |= 8
        for ch in self.ch[4:10]:
            ch.vol = (ch.vol - 1) & 0xFF
            if ch.vol == 0 or ch.vol & 0x80: ch.vol = 0; ch.flags = 0
        b = self.ch[10]
        b.vol = (b.vol - 5) & 0xFF
        if b.vol & 0x80: b.vol = 0
        if self.b_vol < 6: self.b_vol = 0; self.fabe0 |= 0x20
        else: self.b_vol -= 6
        return True

    def fade_refresh(self, ch):
        """after each channel's tick while fading: FM TL ($1BE5), ADPCM-A level ($1C07), ADPCM-B volume ($1C46)"""
        if not ch.flags & 1: return
        c = ch.code
        if c <= 4:
            a = ((self.fm_att + ch.vol) & 0xFF) + ch.att
            if a > 0xFF or a & 0xFF >= 0x7F: ch.flags = 0; a = 0x78
            self.emit(ch, 'tl', tl=a & 0xFF)
        elif c < 14:
            a = ch.vol - ch.att
            if a < 0: a = 1
            self.emit(ch, 'alevel', v=(ch.flags & 0xC0) | a)
        else:
            a = self.b_vol
            r = a + ch.vol                                   # negative volume: JP M on the sum; else JR C
            bad = bool(r & 0x80) if ch.vol & 0x80 else r > 0xFF
            a = r & 0xFF
            for _ in range(3):
                if bad: break
                if a < ch.att: bad = True
                a = (a - ch.att) & 0xFF
            if bad: ch.flags = 0; a = 0
            self.emit(ch, 'bvol', vol=a)

    def timer_a(self):                                       # $2194: only the FM vibrato concerns the music
        for c in (1, 2, 3, 4):
            if self.vib_off[c]: continue
            v = self.vib[c]
            if not v.depth or v.f & 4: continue
            if not v.f & 0x18:
                v.dcnt = (v.dcnt - 1) & 0xFF
                if v.dcnt: continue
                v.dcnt = v.delay
            v.f = (v.f | 0x10) & ~1
            v.scnt = (v.scnt - 1) & 0xFF
            if v.scnt: continue
            v.scnt = v.speed
            bc, de = v.step, v.depth
            if de & 0x8000: bc = (-bc) & 0xFFFF; v.f |= 1
            out = self.vib_step(v, bc, de)
            w = (self.shadow.get((c, 'fnum'), 0) + out) & 0xFFFF
            self.out.append((self.irq, self.tick, CHANNELS[c - 1], 'vib', {'a4': w >> 8, 'a0': w & 0xFF}))

    def vib_step(self, v, bc, de):
        """$1CFE: the value steps by BC towards depth DE (flag bit 0: negative depth, comparisons swapped)"""
        def up():                                            # $1D5E
            hl = (v.val + bc) & 0xFFFF; nb = hl
            x, y = (hl, de) if not v.f & 1 else (de, hl)
            if not (x - y) & 0x8000 or x == y: v.f |= 2; nb = de
            v.val = nb; return nb
        def down():                                          # $1D75
            hl = (v.val - bc) & 0xFFFF; nb = hl
            x, y = (hl, 0) if not v.f & 1 else (0, hl)
            if (x - y) & 0x8000 and x != y: v.f &= ~2; nb = 0
            v.val = nb; return nb
        t = v.type
        if t == 0:                                           # $1D1E saw
            hl = (v.val + bc) & 0xFFFF; nb = hl
            x, y = (hl, de) if not v.f & 1 else (de, hl)
            if not (x - y) & 0x8000 or x == y: v.f &= ~2; nb = 0
            v.val = nb; return nb
        if t == 1:                                           # $1D35 square
            if not v.f & 2:
                up(); return 0 if v.f & 2 else de
            down(); return de if not v.f & 2 else 0
        if t == 2: return down() if v.f & 2 else up()
        if t == 3:
            r = self.m.d[v.rnd & 0xFF]; v.rnd = (v.rnd + 1) & 0xFF
            if r & 2: return 0
            return down() if v.f & 2 else up()
        if t == 4:
            if not v.f & 2: v.f |= 2; v.val = de; return de
            r = down()
            if not v.f & 2: v.f |= 4
            return r
        if not v.f & 2: return up()
        r = down()
        if not v.f & 2: v.f |= 4
        return r

    def run(self, irqs=None, ticks=None, seq=None):
        """advance interrupts: seq = iterable of 'A' / 'B' (the measured order), else timers(); stop after `irqs`
        interrupts or `ticks` music ticks"""
        if seq is None: seq = timers(self)
        for t in seq:
            if irqs is not None and self.irq >= irqs: break
            if ticks is not None and self.tick >= ticks: break
            if irqs is None and not self.running: break
            self.irq += 1
            if t == 'B': self.music_tick()
            else: self.timer_a()
        return self

def timers(song):
    """the interrupt order from the two timer periods (18 us units), timer B starting with the song: an
    approximation of the phase (the real one depends on when the timers were started; capture.py measures it)"""
    ta = tb = 0
    while True:
        na, nb = ta + TA_UNITS, tb + TB_UNITS * (256 - song.tempo)
        if nb <= na: tb = nb; yield 'B'
        else: ta = na; yield 'A'

def catalog(data):
    rows = []
    for cmd in music_cmds(data):
        s = Song(data, cmd)
        s.run(ticks=20000)
        rows.append((cmd, s))
    return rows

def tick_hz(tempo): return 1e6 / (18 * TB_UNITS * (256 - tempo))

def summary(s):
    if s.queued:
        print(f"song ${s.cmd0:02X}: header ${s.ptr0:04X} bank set {s.bank0} timer B ${s.tempo0:02X}, chains to "
              f"${s.queued[0][2]:02X} at tick {s.queued[0][0]} (opcode $47 on {s.queued[0][1]}); from there:")
    print(f"song ${s.cmd:02X}: header ${s.ptr:04X} bank set {s.bank} timer B ${s.tempo:02X} ({tick_hz(s.tempo):.2f} ticks/s) "
          f"FM att ${s.fm_att:02X} ADPCM-A master ${s.a_vol:02X} ADPCM-B volume ${s.b_vol:02X} samples ${s.smp:04X}")
    for ch in s.ch:
        if not s.on[ch.k]: continue
        keys = [e for e in s.out if e[2] == ch.name and (e[3] in ('akey', 'bkey') or e[3] == 'key' and e[4]['d'])]
        lp = s.loop_at.get(ch.name)
        lt = f'loops to ${lp[2]:04X} (first played at tick {lp[0]}) every {lp[1]} ticks' if lp else \
            ('ends' if not s.running else 'no loop within the run')
        print(f"  {ch.name:4s} start ${s.sp[ch.k]:04X} key-ons {len(keys):4d}  {lt}")

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    if sys.argv[2] == '--catalog':
        for cmd, s in catalog(data):
            used = ' '.join(CHANNELS[k] for k in range(11) if s.on[k])
            lp = sorted(set(v[0] for v in s.loop_at.values()))
            end = f'chains to ${s.queued[0][2]:02X}' if s.queued else ('stops' if not s.running else f'loops at ticks {lp}')
            print(f"${cmd:02X} hdr ${s.ptr0:04X} bank {s.bank0} TB ${s.tempo0:02X} {tick_hz(s.tempo0):5.2f}/s ticks {s.tick:5d} "
                  f"chans {used} {end}")
        sys.exit()
    cmd = int(sys.argv[2], 16)
    mode = sys.argv[3] if len(sys.argv) > 3 else ''
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 20000
    s = Song(data, cmd, listing=(mode == '--list'))
    s.run(ticks=n)
    if mode == '--list':
        print(f"song ${s.cmd:02X}: header ${s.ptr:04X}, bank set {s.bank}, timer B ${s.tempo:02X} = {tick_hz(s.tempo):.2f} ticks/s")
        print('columns: tick, stream address (Z80, in the song\'s bank set), event; "len" = ticks from this note to the '
              "channel's next one (gate + rest, $2B21)")
        for name in CHANNELS:
            ev = [l for l in s.log if l[1] == name]
            if not ev: continue
            print(f'== {name}')
            for t, _, pos, txt in ev: print(f'{t:6d}  ${pos:04X}  {txt}')
    elif mode == '--keys':
        for irq, t, ch, kind, kw in s.out:
            print(irq, t, ch, kind, ' '.join(f'{k}={v:X}' if isinstance(v, int) else f'{k}={v}' for k, v in kw.items()))
    else: summary(s)
