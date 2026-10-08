#!/usr/bin/env python3
"""Retiming (docs/brawler_feel.md 6 and 8h, docs/brawler_data_model.md "Retiming"): the brawler keeps every move's
ORIGINAL timing in its data; the animation player retimes a move at run time (fighter.c "retiming"). This module is
the build's side: each move's segments (their source lengths, exported per fighter: bm_seg, chainlab.json) and
game.json's targets read into one list per move (build_tables.py: gretime[]).

Segments of a move, frame by frame as the engine plays it alone (no opponent, no hit, no button held: its whiff):
startup = the frames before its first frame with a live attack box, then for each active window (a run of frames with
one) the window and the recovery after it (to the next window, the last one to the move's end): a single-hit move
has three, left punch / pause / right punch five. A move that never strikes with its body (a projectile) takes the
step it spawns its object on as its window. A move without any has no segments (not retimable).

game.json roster[].retime = {MOVE: TARGETS}
    MOVE    a brawler move (export_bm.MOVES: "atk_c_close") or a special's input as the roster names it ("214C",
            "EX 236C", "MAX 21416C")
    TARGETS [t0, t1, ...] one per segment in order, frames (null = the source's; "1.5x" = a ratio)
          | [startup, active, recovery] (a move with more segments: active / recovery for every window)
          | {"scale": 1.5, "startup": .., "active": .. or [per window], "recovery": .. or [per window]}
          | null (the original)
A segment scaled outside BOUND is still applied; the build prints it as a hand check (and build/retime.json lists it
for the Lab)."""
import math

BOUND = (0.5, 2.0)

def segments(act):
    """per-frame active flags -> source lengths [startup, active_1, recovery_1, ..., active_n, recovery_n]; [] when
    no frame is active"""
    n = len(act); on = [i for i, a in enumerate(act) if a]
    if not on: return []
    out = [on[0]]; i = on[0]
    while i < n:
        j = i
        while j < n and act[j]: j += 1
        k = j
        while k < n and not act[k]: k += 1
        out += [j - i, k - j]; i = k
    return out

def kind(i):
    return 'startup' if i == 0 else 'active' if i % 2 else 'recovery'

def _val(v, src):
    if v is None: return src
    if isinstance(v, str):
        assert v.endswith('x'), f'retime: {v!r} (frames, null, or a ratio like "1.5x")'
        return max(1, int(round(src * float(v[:-1])))) if src else 0
    assert isinstance(v, int) and not isinstance(v, bool) and v >= 0, f'retime: {v!r}'
    return v if src else 0

def targets(spec, segs):
    """TARGETS (game.json form) -> target frames per segment; None: the original (no entry)"""
    if spec is None: return None
    n = len(segs)
    assert n, 'retime: the move has no active frame (nothing to retime)'
    if isinstance(spec, list):
        if len(spec) == n: return [_val(v, s) for v, s in zip(spec, segs)]
        assert len(spec) == 3, f'retime: {len(spec)} targets, the move has {n} segments (or give [startup, active, recovery])'
        return [_val(spec[0 if i == 0 else 1 if i % 2 else 2], s) for i, s in enumerate(segs)]
    assert isinstance(spec, dict) and set(spec) <= {'scale', 'startup', 'active', 'recovery', 'note'}, f'retime: {spec!r}'
    sc = spec.get('scale'); nwin = n // 2
    def pick(key, w):
        v = spec.get(key)
        if isinstance(v, list):
            assert len(v) == nwin, f'retime: "{key}" has {len(v)} values, the move has {nwin} windows'
            return v[w]
        return v
    out = []
    for i, s in enumerate(segs):
        v = pick('startup', 0) if i == 0 else pick('active' if i % 2 else 'recovery', (i - 1) // 2)
        out.append(_val(v, s) if v is not None else (_val(f'{sc}x', s) if sc else s))
    return out

def hand_checks(who, segs, T):
    """the segments outside BOUND (still applied)"""
    out = []
    for i, (s, t) in enumerate(zip(segs, T)):
        if s and not BOUND[0] <= t / s <= BOUND[1]:
            out.append(f'hand check: {who} segment {i} ({kind(i)}) {s} -> {t} frames ({t / s:.2f}x, outside {BOUND[0]}x-{BOUND[1]}x)')
    return out

def step_segments(flags):
    """a step animation (routes.step_flags: [(ticks, active, opens)]) -> its segments (a step shows ticks + 1 frames)"""
    return segments([a for t, a, o in flags for _ in range(t + 1)])

def rom_segments(r, var, atk):
    """a ROM special played alone (Prog) -> its segments"""
    fr, pg = play_rom(r, var, atk)
    return segments(contact_acts(fr))

# ---- ROM programs: fighter.c prog_update played alone ---------------------------------------------------------------
P = {k: i + 1 for i, k in enumerate('ANIM SET MUL MOVE FRICMOVE FALL NUDGE DEC BR RESUME RESUMEAT JMP SPAWN FXOFF END ADV '
                                     'CHECK PART EVCLR ONHIT PUT HITCLR HOLD UNHOLD SIGCLR HITOFF ADD FORM VOICE VSIG TURN '
                                     'VPHASE SCREEN HOME CATCH'.split())}
PC = {k: i for i, k in enumerate('END EVENT LAND FALL CNT HIT OFF ALWAYS STEPEV WINDOW LINK HITANY SIG7 SIG7C SIG6 FAR LOW '
                                  'WALL HELD CNTLE PASSED CAUGHT THIGH TDOWN'.split())}
KOF_OPS = {'anim': 1, 'set': 2, 'mul': 3, 'move': 4, 'fricmove': 5, 'fall': 6, 'nudge': 7, 'dec': 8, 'br': 9, 'resume': 10,
           'resume_at': 11, 'jmp': 12, 'spawn': 13, 'fxoff': 14, 'end': 15, 'adv': 16, 'check': 17, 'part': 18, 'evclr': 19,
           'onhit': 20, 'place': 21, 'hitclr': 22, 'hold': 23, 'unhold': 24, 'sigclr': 25, 'hitoff': 26, 'add': 27,
           'vsend': 29, 'vsig': 30, 'turn': 31, 'vphase': 32, 'screen': 33, 'cine': 35}   # = export_bm.P_OPS
REGS = {'vx': 0, 'vy': 1, 'g': 2, 'fric': 3, 'cnt': 4, 'h': 5}

def kof_prims(ops):
    """a KOF program's named ops (handlers98) -> (op, a, b, v) as export_bm.rom_c writes them (the timing fields)"""
    out = []
    for op in ops:
        c = KOF_OPS[op[0]]
        if op[0] == 'anim': out.append((c, op[1], 0, 0))
        elif op[0] in ('set', 'add'):
            reg = REGS[op[1]]; v = op[2]
            out.append((c, reg, 0, round(v * 65536) if reg < 3 or (reg == 5 and op[0] == 'set') else int(v)))
        elif op[0] == 'mul': out.append((c, 0, 0, op[1]))
        elif op[0] == 'nudge': out.append((c, 0, round(op[1]), round(op[2])))
        elif op[0] == 'br': out.append((c, op[1] | op[2] << 7, -1 if op[3] == 'yield' else op[3], op[4] if len(op) > 4 else 0))
        elif op[0] in ('resume_at', 'jmp'): out.append((c, 0, op[1], 0))
        elif op[0] == 'spawn': out.append((c, op[1], 0, 0))
        elif op[0] == 'vsend': out.append((c, op[1], op[2], 0))
        elif op[0] == 'sigclr': out.append((c, 0, 0, op[1]))
        elif op[0] == 'check': out.append((c, op[1], 0, 0))
        else: out.append((c, 0, 0, 0))
    return out

def fmul16(v, k):
    k &= 0xFFFF; a = -v if v < 0 else v
    a = (a >> 16) * k + (((a & 0xFFFF) * k + 0x8000) >> 16)
    return -a if v < 0 else a

class Prog:
    """one ROM special played alone, frame by frame (a port of fighter.c prog_update / pan_*: no opponent, no hit, no
    button held, no follow-up pressed: its whiff)"""
    def __init__(self, prog, anims, acts, vars_=None, var=0, vcols=0, vanim=0, nvar=0):
        self.prog, self.anims, self.acts = prog, anims, acts
        self.vars, self.var, self.vcols, self.vanim, self.nvar = vars_, var, vcols, vanim, nvar
        self.x = self.y = self.vx = self.vy = self.g = self.cnt = 0; self.fric = 0; self.facing = 1
        self.fl = set(); self.pres = 0; self.plink = 0; self.done = False; self.occ = -1
        self.frames = []; self.log = []                 # per frame: dict; log: (frame, op index, op, a, b, v)
    def enter(self):
        s = self.an['steps'][self.pstep]
        self.x -= self.facing * s.get('dx', 0) << 16    # (bstep dx = -export dx: forward +)
        self.fl.discard('event')
        if s['flags'] & 0x80: self.fl.add('event')
        self.occ += 1
    def pan_play(self, j):
        self.j = j; self.an = self.anims[j]; self.pstep = 0; self.pleft = self.an['steps'][0]['ticks'] + 1
        self.fl -= {'end', 'event'}; self.enter()
    def pan_advance(self):
        self.pleft -= 1
        if self.pleft: return
        if self.pstep + 1 < len(self.an['steps']): self.pstep += 1
        else:
            self.fl.add('end')
            if self.an['hold']: self.pleft = 1; return
            self.pstep = 0
        self.pleft = self.an['steps'][self.pstep]['ticks'] + 1; self.enter()
    def cond(self, c, v):
        s = self.an['steps'][self.pstep] if hasattr(self, 'an') else {'flags': 0}
        if c == PC['EVENT'] or c == PC['SIG7C']:
            k = 'event' if c == PC['EVENT'] else 'sig7'; e = k in self.fl; self.fl.discard(k); return e
        return {PC['END']: 'end' in self.fl, PC['LAND']: 'land' in self.fl, PC['FALL']: 'fall' in self.fl,
                PC['CNT']: self.cnt < 0, PC['STEPEV']: 'event' in self.fl, PC['WINDOW']: bool(s['flags'] & 0x2000),
                PC['LINK']: bool(self.plink & v), PC['SIG7']: 'sig7' in self.fl, PC['SIG6']: 'sig6' in self.fl,
                PC['FAR']: True, PC['LOW']: (self.y >> 16) < v, PC['CNTLE']: self.cnt <= v}.get(c, c == PC['ALWAYS'] or c > PC['TDOWN'])
    def frame(self):
        if self.done: return None
        f = len(self.frames); ppc = self.pres; spawned = []
        for _ in range(255):
            k = ppc; op, a, b, v = self.prog[ppc]; ppc += 1
            if op & 0x80: op &= 0x7F; v = self.vars[self.var * self.vcols + b]
            self.log.append((f, k, op, a, b, v))
            if op == P['ANIM']: self.pan_play(a + (self.var * self.vanim if self.nvar else 0))
            elif op == P['SET']:
                if a == 0: self.vx = v
                elif a == 1: self.vy = v
                elif a == 2: self.g = v
                elif a == 3: self.fric = v
                elif a == 5: self.y = v
                else: self.cnt = v
            elif op == P['MUL']:
                if a == 1: self.vy = fmul16(self.vy, v)
                else: self.vx = fmul16(self.vx, v)
            elif op == P['ADD']:
                if a == 0: self.vx += v
                elif a == 1: self.vy += v
                else: self.cnt += v
            elif op in (P['FRICMOVE'], P['MOVE']):
                if op == P['FRICMOVE']: self.vx = fmul16(self.vx, self.fric)
                self.x += self.facing * self.vx
            elif op == P['FALL']:
                v0 = self.vy; self.vy -= self.g; self.y += v0; self.fl -= {'land', 'fall'}
                if self.y <= 0 and a and self.y > -65536: self.y = 0
                elif self.y <= 0: self.y = 0; self.fl.add('land')
                if 'land' not in self.fl and self.vy < 0: self.fl.add('fall')
            elif op == P['NUDGE']: self.x += self.facing * (b << 16); self.y += v << 16
            elif op == P['DEC']: self.cnt -= 1
            elif op == P['BR']:
                if self.cond(a & 0x7F, v) == bool(a >> 7):
                    if b < 0: break
                    ppc = b
            elif op == P['RESUME']: self.pres = ppc
            elif op == P['RESUMEAT']: self.pres = b
            elif op == P['JMP']: ppc = b
            elif op == P['SPAWN']: spawned.append(a)
            elif op == P['FXOFF']: self.fl.add('sig7')
            elif op == P['SIGCLR']: self.fl -= {k_ for k_, bit in (('sig7', 128), ('sig6', 64)) if not v & bit}
            elif op == P['ADV']: self.pan_advance()
            elif op == P['PART']: self.plink = 0
            elif op == P['EVCLR']: self.fl.discard('event')
            elif op == P['TURN']: self.facing = -self.facing
            elif op in (P['END'], P['FORM']) or op not in P.values(): self.done = True; return None
        self.pan_advance()
        rec = {'j': self.j, 'i': self.pstep, 'occ': self.occ, 'act': self.acts[self.j][self.pstep], 'x': self.x, 'y': self.y,
               'spawn': spawned}
        self.frames.append(rec); return rec
    def run(self, limit=3000):
        while self.frame() is not None and len(self.frames) < limit: pass
        return self.frames

def rom_acts(anims, atk):
    """per anim, per step: export_bm.rom_c's live attack box (the last box loaded stays live on $0100 steps, across the
    program's anims in order)"""
    live, out = False, []
    for a in anims:
        row = []
        for s in a['steps']:
            if atk(s): live = True
            row.append(bool(s['flags'] & 0x100) and live)
        out.append(row)
    return out

def contact_acts(fr):
    """per-frame active flags: the body's live box; a move that never strikes: the step shown the frame it spawns"""
    act = [r['act'] for r in fr]
    if any(act): return act
    occ = {r['occ'] for r in fr if r['spawn']}
    return [r['occ'] in occ for r in fr]

def anim_of(r, st):
    return r['anims'][st] if st in r['anims'] else r['anims'][str(st)]

def play_rom(r, var, atk, prog=None):
    """(frames, Prog) of a ROM special r (export dict 'rom') played alone at variant row var"""
    anims = [anim_of(r, st) for st in r['states']]
    anims = [{'hold': a['mode'] == 'hold', 'steps': a['steps']} for a in anims]
    vt = r.get('vtable') or {}
    flat = [v for row in vt.get('rows') or [] for v in row]
    prog = prog or ([tuple(p[:3]) + (0 if p[3] is None else p[3],) for p in r['prims']] if r.get('prims') else kof_prims(r['ops']))
    pg = Prog(prog, anims, rom_acts(anims, atk), flat, var, vt.get('ncol', 0), vt.get('vanim', 0), vt.get('nvar', 0))
    return pg.run(), pg

