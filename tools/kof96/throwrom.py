#!/usr/bin/env python3
"""Throws read from the ROM (TODO #146, pilot: KOF98 Terry, KOF96 Geese): the throw's code and tables played, no capture.

How KOF96 / KOF98 run a throw (Terry forward+C, KOF98 $43B52; Geese forward+C, KOF96 $4AB20): ONE routine in the
thrower's code block serves both fighters. The hit system installs it on both objects; `bclr #5, +$E0` tells them apart.
  thrower (bit 5 was set): bookkeeping, the throw's state (+$D2: Terry 198 / 199, Geese 174 / 175) restarted, then a
  frame loop: `tst +$D1` (broken: never here), `tst +$7D` -> `eori #1, +$31` (the reverse throw turns around on its
  event step: Terry / Geese forward+D), `tst +$7C` (the animation over) -> `jmp` the neutral routine (KOF98 $251F8 /
  $25182, KOF96 $1AE0C / $1ADE2): the thrower can act again. Its x moves only by its animation's steps ($FB).
  victim (bit 5 clear): `lea list base, a0; move #size, d0; jsr setlist` (KOF98 $24B22: list = base + map[victim id] *
  size, map $24B46; KOF96 $1A980: base + id * size) into +$C2; +$D2 = -1; a frame loop: `jsr check` (KOF98 $24B6C,
  KOF96 $1A99C: the throw broken -> 0 here), `jsr place` (KOF98 $25372, KOF96 $1AF72: the victim put at the thrower +
  entry (thrower +$80 - 1): x, height, state +$72, flags +$D4; d0 = 1 when the thrower's step changed since +$D2, then
  flag bit 0 = damage + hit effect, bit 1 = KO check), `beq yield`, `btst #6, +$D4` (flag $40: the release) -> the
  flight: +$C2 = its state list, +$C6 = its parameters (vx, gravity, vy, [vy of the bounce], [friction, frames]), maybe
  `eori #1, +$12C` (+$12C bit 0 = the thrower faced right; the flight's vx is negated by it: thrown forward / backward),
  then a shared flight routine (KOF98 $51284 friction + fall, $40906 fall + bounce; KOF96 $2BF28 fall + bounce, $2FB4C):
  `move.l +$50, d0; add.l d0, +$18` (x += vx), `jsr fall` (height += vy, vy -= g; 0 = landed), the list's next state
  on falling / landing / the animation's end, a second vy for the floor bounce, then `jmp` the get-up.
The walk below EXECUTES that code (a small 68000 subset on the object's bytes: moves, tst / btst / bit ops, sub / add /
neg / clr, branches, the engine routines as models: animate (a step shows ticks + 1 frames, step moves $FB), fall,
the 16.16 multiply $36A0 / $2DF4, place, setlist; any other jsr = bookkeeping (sound, damage, effects, gauge) with d0 =
0) for both objects frame by frame: thrower first, as P1 runs before P2. The thrower faces right at x 0 (forward = +x).

Output per throw (throwscripts96.build's shape, so export96 / export_bm take it as they took the captured scripts):
timeline [thrower frame, x, height, turned], victims {id: [frame, dx, dy, same facing, front, 'state.step']} plus the
decoded points: 'release' (row of the list's $40 entry: the victim flies), 'land' (first floor touch after it),
'down' (the victim's flight reaches its lying state: its part of the script ends), 'end' (the thrower's code jumps to
neutral), 'impacts' (rows of entries with flag bit 0: the blows), 'roles' (per victim row from the release: the
brawler knockdown animation its flight state plays, by its place in the flight code: rise / fall / floor / bounce /
down), 'ret' (the CONTROL RETURN row, chosen below) and 'sheet' (the conversion sheet: what the code does, row by row).

Control return (Bruno's rule 8): the thrower acts again at the earliest of its animation's step starts at or after
the last impact (the last blow, or the victim's landing, a few frames later: RET_AFTER_LAND) where its follow-through
is complete, never inside a step (no mid-pose cut), and never later than its code's own end (no idle tail): if its
code ends before that point, its end is the return (KOF lets the thrower act then: Terry's forward+D turns around and
is free while the victim still flies).

    python3 throwrom.py [check]      the pilot's four throws, against the captures (thrower state / step / x, victim
                                     state / x / height, frame by frame up to the victim lying down)"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rom96, throwtables96 as T, handlers98 as H

RET_AFTER_LAND = 3                       # frames after the victim's landing the throw may end (Bruno: "a few frames")

# The throw-start effect (TODO #166 a, decoded 2026-10-06; the blue streaks over the victim as a throw starts). The
# thrower's throw animation carries an effect command, record [$FA][kind][x:16][y:16] (Terry KOF98 198 / 199 and Geese
# KOF96 174: $FA $34 after step 0; Geese's 175 has none). The animation engine's handler (KOF98 $5D1C) spawns an
# effect object: routine = table $36382[kind] (kind $34 -> $3709E), owner = the thrower, x / y = the record's offsets
# from it (sprite orientation: x -40 = 40 px forward, y -78 = 78 px up). Routine $3709E: sound index $80 through $7A98
# (table $A9BCE[$80] = $1A $18), then effect id 38 (the shared effects bank) state 61 played once (8 steps, 27 frames,
# palette 90), freed 2 frames after its last step. KOF96: the same command, kind and state (effects id 29), its own
# sound code ($1A $31). Measured in our emulator (Terry forward+C / D, Geese forward+C): the object exists from the
# throw's row 3 = the frame before the step after the command starts. Kind $35 = state 62, sound $81 ($1A $19).
THROW_FX_KINDS = {'kof96': {0x34}, 'kof98': {0x34}}

def throw_fx(m, game, cid, slot):
    """the throw-start effect command of a throw animation -> {'row', 'dx' (px forward), 'dy' (px up), 'kind'} or None"""
    kinds = THROW_FX_KINDS.get(game)
    if not kinds: return None
    a = rom96.anim_addr(m, cid, slot); t = 0
    for i in range(300):
        b0, b1 = m.u8(a + 6 * i), m.u8(a + 6 * i + 1)
        if b0 in (0xFE, 0xFF): return None
        if b0 == 0xFA and b1 in kinds:
            return {'row': max(0, t - 1), 'dx': -s(m.u16(a + 6 * i + 2), 2), 'dy': -s(m.u16(a + 6 * i + 4), 2), 'kind': b1}
        if b0 < 0x80: t += b0 + 1
    return None
# the engine per game: routines the walk models, the neutral routines that end the thrower, the list setters
ENGINE = {
    'kof98': {'animate': 0x5BA6, 'fall': 0x37E0, 'mul': 0x36A0, 'place': 0x25372, 'setlist': 0x24B22, 'check': 0x24B6C,
              'listmap': 0x24B46, 'neutral': {0x25182, 0x251F8}, 'getup': {0x1AC1E}},
    'kof96': {'animate': 0x4D50, 'fall': 0x2F34, 'mul': 0x2DF4, 'place': 0x1AF72, 'setlist': 0x1A980, 'check': 0x1A99C,
              'listmap': None, 'neutral': {0x1ADE2, 0x1AE0C}, 'getup': set()},
}
# the pilot (Bruno 2026-10-06: Geese and Terry first, reviewed, then the roster): (game, KOF id) -> {key: (list base,
# list size)} as tables.json found them; the code is found from the base (the `lea base, a0` of the victim's path)
PILOT = {('kof98', 3): {'throw_c': (0x257B80, 24), 'throw_d': (0x257F10, 32)},
         ('kof96', 24): {'throw_c': (0x23FDDA, 32), 'throw_d': (0x24017A, 20)}}
INPUTS = {'throw_c': 'forward+C (close)', 'throw_d': 'forward+D (close)'}

def s(v, n): return v - (1 << 8 * n) if v >> (8 * n - 1) else v

class Obj:
    """an object's bytes (+$00..+$1FF) and its animation (the engine's own fields: +$72 state, +$78 the one playing,
    +$7C bit 7 end, +$7D bit 7 event, +$80 step counter from 1)"""
    def __init__(self, m, cid, name):
        self.m, self.cid, self.name = m, cid, name; self.b = bytearray(0x200); self.steps = None; self.left = 0
        self.pc = None; self.done = None; self.anims = []          # (frame, state) of every animation started
    def get(self, off, n, signed=True):
        v = int.from_bytes(self.b[off:off + n], 'big'); return s(v, n) if signed else v
    def put(self, off, v, n): self.b[off:off + n] = (v & ((1 << 8 * n) - 1)).to_bytes(n, 'big')
    @property
    def x(self): return self.get(0x18, 4) / 65536
    @property
    def h(self): return self.get(0x20, 4) / 65536
    @property
    def facing(self): return 1 if self.b[0x31] & 1 else -1
    def step_move(self, dx):                   # KOF's $FB: sprite orientation (faces left): negative = forward
        if dx: self.put(0x18, self.get(0x18, 4) + (-dx if self.facing > 0 else dx) * 65536, 4)
    def animate(self, frame):
        st = self.get(0x72, 2, False)
        if self.steps is None or self.get(0x78, 2) != st:          # a new state (or +$78 = -1: restart)
            self.put(0x78, st, 2); self.anims.append((frame, st))
            self.steps, self.mode = rom96.parse_anim(self.m, rom96.anim_addr(self.m, self.cid, rom96.state_slot(self.m, self.cid, st)))
            self.step = 0; self.left = self.steps[0][0] + 1; self.b[0x7C] = 0
            self.b[0x7D] = 0x80 if self.steps[0][2] & 0x80 else 0; self.put(0x80, 1, 2); self.step_move(self.steps[0][5])
            return
        self.left -= 1
        if self.left > 0: return
        if self.step + 1 < len(self.steps): self.step += 1
        else:
            self.b[0x7C] |= 0x80
            if self.mode == 'hold': self.left = 1; return
            self.step = 0
        t, fi, fl, bx, raw, dx = self.steps[self.step]
        self.left = t + 1; self.put(0x80, self.step + 1, 2); self.step_move(dx)
        self.b[0x7D] = 0x80 if fl & 0x80 else 0
    def shown(self): return self.steps[self.step][1] if self.steps else None

class Walk:
    """both objects' code, frame by frame (a 68000 subset over objdump's text of the de-swapped P1)"""
    def __init__(self, m, game, cid, victim):
        self.m, self.game, self.E = m, game, ENGINE[game]; self.dec = H.Decoder(m); self.dec.cid = cid
        self.t = Obj(m, cid, 'thrower'); self.v = Obj(m, victim, 'victim'); self.vid = victim
        self.t.b[0x31] = 1; self.v.b[0x31] = 0                     # thrower faces right, the victim faces it
        self.v.b[0x12C] = 1                                         # +$12C bit 0: the thrower faced right (measured)
        self.v.put(0x18, 40 * 65536, 4)                             # (overwritten by the first placement)
        self.frame = 0; self.log = []                               # the conversion sheet's raw lines
        self.entry = None; self.release = None; self.rel_flags = None

    # operands
    def ea(self, o, o_, R, size):
        """an operand's value (size bytes, signed)"""
        if o.startswith('#'): v = H.imm(o); return s(v & ((1 << 8 * size) - 1), size)
        if o.startswith('%d') or o.startswith('%a') and '@' not in o: return R.get(o, 0)
        a = self.addr(o, o_, R)
        if a[0] == 'obj': return a[1].get(a[2], size)
        return s(self.rom(a[1], size), size)
    def addr(self, o, o_, R):
        mt = re.match(r'^%(a\d)@(?:\((-?\d+)\))?$', o)
        if not mt:
            v = H.imm(o)
            if v is not None: return ('rom', v)
            raise ValueError(o)
        reg, off = '%' + mt.group(1), int(mt.group(2) or 0)
        if reg == '%a4': return ('obj', o_, off)
        base = R.get(reg)
        if isinstance(base, tuple): return ('obj', base[1], off)     # a pointer to an object (+$B6: the thrower)
        return ('rom', base + off)
    def rom(self, a, size):
        return {1: self.m.u8, 2: self.m.u16, 4: self.m.u32}[size](a)
    def store(self, o, o_, R, v, size):
        if o.startswith('%d') or o.startswith('%a') and '@' not in o: R[o] = v; return
        a = self.addr(o, o_, R)
        if a[0] != 'obj': raise ValueError('rom write ' + o)
        a[1].put(a[2], v, size)

    def run(self, o, frame):
        """o's code from its resume point to its yield (or its end)"""
        R = {}; cc = (0, 4); a = o.pc; n = 0
        while True:
            n += 1
            if n > 400: raise RuntimeError(f'{o.name}: no yield from {o.pc:X}')
            mn, ops, nx = self.dec.at(a)
            sz = {'b': 1, 'w': 2, 'l': 4}.get(mn[-1], 4) if mn[-1] in 'bwl' and mn not in ('jsr', 'nop', 'rts') else 4
            base = mn[:-1] if mn[-1] in 'bwl' and len(mn) > 3 and mn not in ('negl',) else mn
            if mn in ('negl', 'negw', 'negb'): base = 'neg'
            if mn.startswith('move') and mn != 'moveq' and not mn.startswith('moveal'):
                if ops[1] == '%a4@' and ops[0].startswith('#'):          # move.l #R, (a4): the resume point
                    o.pc = H.imm(ops[0]); a = nx; continue
                v = self.ea(ops[0], o, R, sz); self.store(ops[1], o, R, v, sz); cc = (v, sz)
                if o is self.v and ops[1] == '%a4@(212)': pass
            elif mn == 'moveq': R[ops[1]] = H.imm(ops[0]); cc = (R[ops[1]], 4)
            elif mn == 'moveal':
                src = ops[0]
                if src == '%a4@(182)': R[ops[1]] = ('objptr', self.t)
                else: R[ops[1]] = self.ea(src, o, R, 4) & 0xFFFFFFFF
            elif mn == 'lea':
                v = H.imm(ops[0]); R[ops[1]] = v
            elif base in ('tst',): cc = (self.ea(ops[0], o, R, sz), sz)
            elif mn == 'btst':
                b = H.imm(ops[0]); v = self.ea(ops[1], o, R, 1) & 0xFF; cc = ((v >> b) & 1, 1)
            elif mn == 'bclr':
                b = H.imm(ops[0]); v = self.ea(ops[1], o, R, 1) & 0xFF; cc = ((v >> b) & 1, 1); self.store(ops[1], o, R, v & ~(1 << b), 1)
            elif base in ('eori', 'andi', 'ori', 'subq', 'addq', 'add', 'sub', 'addi', 'subi'):
                d = ops[1]; v = self.ea(d, o, R, sz); w = self.ea(ops[0], o, R, sz)
                r = {'eori': v ^ w, 'andi': v & w, 'ori': v | w, 'subq': v - w, 'subi': v - w, 'sub': v - w,
                     'addq': v + w, 'addi': v + w, 'add': v + w}[base]
                r = s(r & ((1 << 8 * sz) - 1), sz); self.store(d, o, R, r, sz); cc = (r, sz)
            elif base == 'neg': v = -self.ea(ops[0], o, R, sz); self.store(ops[0], o, R, v, sz); cc = (v, sz)
            elif base == 'clr': self.store(ops[0], o, R, 0, sz); cc = (0, sz)
            elif mn in ('nop',): pass
            elif mn == 'jsr':
                t = H.imm(ops[0]) if not ops[0].startswith('%pc') else int(re.search(r'0x[0-9a-f]+', ops[0]).group(0), 16)
                cc = self.call(t, o, R, frame)
            elif mn == 'jmp':
                t = H.imm(ops[0]) if ops[0][0] != '%' else None
                if t is None: raise RuntimeError(f'{o.name}: jmp {ops[0]} at {a:X}')
                if o is self.t and t in self.E['neutral']: o.done = frame; self.log.append((frame, 'thrower', f'jmp ${t:X}: neutral, the thrower acts')); return
                if o is self.v and self.release is not None and (t in self.E['getup'] or not self.flight_code(t)):
                    o.done = frame; self.log.append((frame, 'victim', f'jmp ${t:X}: its get-up')); return
                if o is self.v and self.release is None and self.flight_code(t):
                    self.log.append((frame, 'victim', f'jmp ${t:X}: the flight routine'))
                a = t; continue
            elif mn[0] == 'b' and mn[:3] not in ('bts', 'bcl', 'bse', 'bch'):
                cond = mn[1:3]; t = H.imm(ops[0]); v = cc[0]
                take = {'ra': True, 'eq': v == 0, 'ne': v != 0, 'pl': v >= 0, 'mi': v < 0}[cond]
                if take:
                    if self.dec.is_yield(t): self.call(self.E['animate'], o, R, frame); return
                    a = t; continue
            else: raise RuntimeError(f'{o.name}: {mn} {ops} at {a:X}')
            a = nx

    def flight_code(self, t):
        """the shared flight routines start with field loads from +$C6 / clr height; the get-up routines don't"""
        mn, ops, _ = self.dec.at(t)
        return mn.startswith('move') and ('%a4@(194)' in ops or '%a4@(198)' in ops) or mn == 'clrl' and ops == ['%a4@(32)']

    def call(self, t, o, R, frame):
        E = self.E
        if t == E['animate']: o.animate(frame); return (0, 4)
        if t == E['fall']:                                          # height += vy; vy -= g; landed: height 0, d0 = 0
            vy, g = o.get(0x58, 4), o.get(0x5C, 4); o.put(0x58, vy - g, 4)
            R['%d1'] = -1 if vy - g < 0 else 1
            h = o.get(0x20, 4) + vy
            if h <= 0: o.put(0x20, 0, 4); R['%d0'] = 0; R['%d1'] = 0; return (0, 4)
            o.put(0x20, h, 4); R['%d0'] = -1; return (-1, 4)
        if t == E['mul']:                                           # d0 * d1 (word, 0.16) / 65536, rounded (KOF $36A0)
            d0, d1 = R.get('%d0', 0), R.get('%d1', 0) & 0xFFFF; neg = d0 < 0; d0 = abs(d0)
            r = ((d0 >> 16) * d1) + (((d0 & 0xFFFF) * d1 + 0x8000) >> 16); R['%d0'] = -r if neg else r; return (R['%d0'], 4)
        if t == E['setlist']:                                       # list = base + map[victim id] * size
            k = self.m.u8(E['listmap'] + self.vid) if E['listmap'] else self.vid
            self.list = (R['%a0'], R.get('%d0', 0) & 0xFFFF); o.put(0xC2, self.list[0] + k * self.list[1], 4); o.put(0xC6, self.list[1], 2)
            self.log.append((frame, 'victim', f'list ${self.list[0]:X} + {k} x {self.list[1]}')); return (0, 4)
        if t == E['place']: return self.place(frame, R)
        if t == E['check']: R['%d0'] = 0; return (0, 4)             # the throw is not broken
        R['%d0'] = 0; return (0, 4)                                 # bookkeeping (sound, damage, effects, gauge, KO)

    def place(self, frame, R):
        t, v = self.t, self.v
        step = t.get(0x80, 2)
        e = T.entries(self.m, self.list[0], self.list[1], self.vid)
        x = e[min(max(0, step - 1), len(e) - 1)]
        v.put(0x18, t.get(0x18, 4) + x['dx'] * t.facing * 65536, 4); v.put(0x20, t.get(0x20, 4) + x['dy'] * 65536, 4)
        v.put(0x72, x['state'], 2); v.b[0xD4] = x['flags']
        same = x.get('turn', 0) if self.game != 'kof96' else 0
        v.b[0x31] = (1 if t.facing > 0 else 0) if same else (0 if t.facing > 0 else 1)
        self.entry = (step - 1, x)
        if v.get(0xD2, 2) == step: R['%d0'] = 0; return (0, 4)
        v.put(0xD2, step, 2); R['%d0'] = 1
        if x['flags'] & 1: self.log.append((frame, 'victim', f'entry {step - 1}: state {x["state"]}, flag 1: damage + hit effect (a blow)'))
        if x['flags'] & 64: self.release = frame; self.log.append((frame, 'victim', f'entry {step - 1}: state {x["state"]}, flag $40: the release'))
        return (1, 4)

def find_code(m, game, base):
    """(thrower path, victim path) of the throw whose victim path loads list `base`"""
    p1 = open(H.P1S[game], 'rb').read() if os.path.exists(H.P1S[game]) else None
    if p1 is None: H.Decoder(m); p1 = open(H.P1S[game], 'rb').read()
    pat = bytes([0x41, 0xF9]) + base.to_bytes(4, 'big')            # lea base, a0
    k = p1.find(pat); assert k > 0, hex(base)
    dec = H.Decoder(m)
    for a in range(k - 2, k - 0x200, -2):                          # bclr #5, +$E0 ; beq victim path
        if p1[a:a + 6] == bytes([0x08, 0xAC, 0x00, 0x05, 0x00, 0xE0]):
            mn, ops, nx = dec.at(a + 6)
            vt = H.imm(ops[0]); assert mn.startswith('beq') and vt < k, (hex(a), mn)
            return nx, vt
    raise KeyError(hex(base))

def walk(m, game, cid, key, victim, frames=200):
    """the throw played from its code: per frame (thrower, victim) snapshots + the walk's points"""
    base, size = PILOT[(game, cid)][key]
    tpath, vpath = find_code(m, game, base)
    W = Walk(m, game, cid, victim); W.t.pc, W.v.pc = tpath, vpath
    W.t.put(0x18, 0, 4); W.v.put(0x18, 40 * 65536, 4)
    W.log.append((0, 'thrower', f'code ${tpath:X} (bclr #5, +$E0 set)')); W.log.append((0, 'victim', f'code ${vpath:X}'))
    out = []
    for f in range(frames):
        W.frame = f
        if W.t.done is None: W.run(W.t, f)
        if W.v.done is None: W.run(W.v, f)
        out.append({'f': f, 't': (W.t.get(0x72, 2, False), W.t.get(0x80, 2), W.t.shown(), W.t.x, W.t.h, W.t.facing, W.t.done is not None),
                    'v': (W.v.get(0x72, 2, False), W.v.step if W.v.steps else 0, W.v.x, W.v.h, W.v.facing, W.v.done is not None),
                    'vframe': W.v.shown(), 'rel': W.release is not None and f >= W.release, 'entry': W.entry[0] if W.release is None or f <= W.release else None,
                    'vflags': W.entry[1]['flags'] if W.entry and (W.release is None or f <= W.release) else 0})
        if W.t.done is not None and W.v.done is not None: break
    return out, W

def build(m, game, cid, key, victim):
    """throwscripts96.build's shape from the code; plus release / land / down / end / ret / roles / sheet"""
    rows, W = walk(m, game, cid, key, victim)
    rel = next((r['f'] for r in rows if r['rel']), None)
    land = next((r['f'] for r in rows if rel is not None and r['f'] > rel and r['v'][3] <= 0), None)
    end = W.t.done
    # the victim's flight by its place in the code: every animation its flight starts, in order; the one started on
    # the frame it jumps to its get-up is the get-up (dropped); the last before it = the lying state (its part of the
    # script ends there: the brawler's own down / get-up take over); before it: rise (until it falls), fall, the floor
    # touch (started on the landing frame), the bounce (any later one in the air)
    vanims = [(f, st) for f, st in W.v.anims if rel is not None and f >= rel and f != W.v.done]
    down = vanims[-1][0] if vanims else (land if land is not None else len(rows) - 1)
    falling_from = next((r['f'] for r in rows if rel is not None and r['f'] > rel and r['v'][3] < rows[r['f'] - 1]['v'][3]), None)
    segs = []                                                   # (first frame, state, brawler animation)
    for f, st in vanims:
        if f == down: role = 'down'
        elif land is None or f < land: role = 'blowback' if falling_from is None or f < falling_from else 'knockdown_flight'
        elif f == land: role = 'knockdown_bounce'
        else: role = 'knockdown_fall'
        segs.append((f, st, role))
    def role_at(f):
        r_ = [x for x in segs if x[0] <= f]
        return r_[-1][2] if r_ else None
    impacts = sorted({r['f'] for r in rows if r['entry'] is not None and r['vflags'] & 1 and (r['f'] == 0 or rows[r['f'] - 1]['entry'] != r['entry'])})
    last = max([i for i in impacts] + ([land + RET_AFTER_LAND] if land is not None else []))
    # control return: the first thrower step start at or after `last`, at the latest its code's end
    starts = [r['f'] for r in rows if r['f'] > 0 and r['f'] <= (end or len(rows)) and (r['t'][1] != rows[r['f'] - 1]['t'][1] or r['t'][0] != rows[r['f'] - 1]['t'][0])]
    cand = [f for f in starts if f >= last]
    ret = min(cand[0], end) if cand and end is not None else (end if end is not None else len(rows))
    why = (f'the code\'s own end (frame {end}) comes before the follow-through point' if ret == end and (not cand or cand[0] >= end)
           else f'the step starting at frame {ret} (first step start at or after the last impact, frame {last})')
    nrows = max(down, ret)
    timeline, victims = [], []
    for r in rows[:nrows]:
        st, stp, fr, x, h, fc, dn = r['t']
        timeline.append((fr, round(x), round(h), int(fc < 0)))
        vst, vstep, vx, vh, vfc, _ = r['v']
        role = role_at(r['f']) if rel is not None and r['f'] >= rel else None
        victims.append([r['vframe'], round(vx - x), round(vh - h), int(vfc == 1), 0, f'{vst}.{vstep}', role])
    sheet = {'code': {'thrower': f'${find_code(m, game, PILOT[(game, cid)][key][0])[0]:X}', 'victim': f'${find_code(m, game, PILOT[(game, cid)][key][0])[1]:X}'},
             'list': {'base': f'${PILOT[(game, cid)][key][0]:X}', 'size': PILOT[(game, cid)][key][1]},
             'thrower_state': rows[0]['t'][0], 'rows': nrows, 'impacts': impacts, 'release': rel, 'land': land,
             'down': down, 'code_end': end, 'ret': ret, 'ret_why': why, 'flight': [f'frame {f}: state {st} -> {r_}' for f, st, r_ in segs],
             'walk': [f'{f:3d} {who}: {txt}' for f, who, txt in W.log]}
    return {'timeline': timeline, 'victims': {victim: victims}, 'thrower_state': rows[0]['t'][0], 'impacts': impacts,
            'lists': [{'side': 'victim', 'base': hex(PILOT[(game, cid)][key][0]), 'size': PILOT[(game, cid)][key][1]}],
            'release': rel, 'land': land, 'down': down, 'end': end, 'ret': ret, 'sheet': sheet, 'rom': True, 'raw': rows[:nrows]}

def all_throws(m, game, cids, victims=None):
    """{thrower id: {key: built}} for the pilot fighters among cids (victim: the thrower itself, the brawler's mirror)"""
    out = {}
    for (g, cid), keys in PILOT.items():
        if g != game or cid not in cids: continue
        out[cid] = {k: dict(build(m, game, cid, k, cid), inputs=INPUTS[k]) for k in keys}
    return out

# ---- the check: the walk against the captures (victim Yuri, the canonical captures) --------------------------------
CAPS = {('kof98', 3, 'throw_c'): ('throws98/3.txt', 40), ('kof98', 3, 'throw_d'): ('throws98/3.txt', 340),
        ('kof96', 24, 'throw_c'): ('throws/24_ground_c.txt', 1400), ('kof96', 24, 'throw_d'): ('throws/24_ground_d.txt', 1400)}
def check(m, game, cid, key, quiet=False):
    sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture')); import analyze as A
    cap, start = CAPS[(game, cid, key)]; p = os.path.join(HERE, 'capture', cap)
    r1, r2 = A.load(p, 1), A.load(p, 2)
    g0 = next(i for i in range(start, len(r2)) if A.state_of(r2[i][3]) >= 400)
    victim = 8
    rows, W = walk(m, game, cid, key, victim)
    x0 = A.x_of(r1[g0][3]); bad = []; n = 0
    for r in rows:
        i = g0 + r['f']
        if i >= len(r1): break
        w1, w2 = r1[i][3], r2[i][3]
        game_t = (A.state_of(w1), w1[0x80 // 2], round(A.x_of(w1) - x0))
        game_v = (A.state_of(w2), round(A.x_of(w2) - x0), round(A.y_of(w2)))
        mod_t = (r['t'][0], r['t'][1], round(r['t'][3])) if not r['t'][6] else None
        mod_v = (r['v'][0], round(r['v'][2]), round(r['v'][3]))
        if mod_t is not None and (A.state_of(w1) != mod_t[0] or w1[0x80 // 2] != mod_t[1] or abs(game_t[2] - mod_t[2]) > 1): bad.append((r['f'], 'thrower', game_t, mod_t))
        if r['v'][5]: continue
        if game_v[0] != mod_v[0] or abs(game_v[1] - mod_v[1]) > 1 or abs(game_v[2] - mod_v[2]) > 1: bad.append((r['f'], 'victim', game_v, mod_v))
        n += 1
    if not quiet:
        print(f'{game} {cid} {key}: {n} frames, {len(bad)} mismatches; release {W.release}, thrower end {W.t.done}, victim end {W.v.done}')
        for b in bad[:8]: print('  ', b)
    return n, bad

if __name__ == '__main__':
    for (g, cid), keys in PILOT.items():
        m = rom96.Mem(rom96.load(rom96.GAMES[g]['neo'])[0], g)
        for k in keys:
            if sys.argv[1:] == ['check']: check(m, g, cid, k)
            else:
                b = build(m, g, cid, k, cid)
                print(g, cid, k, json.dumps({x: b['sheet'][x] for x in ('rows', 'impacts', 'release', 'land', 'down', 'code_end', 'ret', 'ret_why', 'flight')}))
