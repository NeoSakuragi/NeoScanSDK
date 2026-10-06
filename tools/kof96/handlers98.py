#!/usr/bin/env python3
"""KOF98 special moves read from the ROM: the 68000 state handler of a special, decoded into a small program of engine
primitives (catalogue: handlers98.md), plus a model that plays it (the KOF98 animation engine's timing, the handler's
motion) so a decoded special can be checked against the game frame by frame and exported to the brawler.

A fighter object runs a coroutine: +$00 holds the address its code resumes at each frame. A special's handler (picked by
the move code: `move.l #handler, $198(a4)`, e.g. Terry 214A/C Burn Knuckle $428BE) is straight-line code: set fields
(states +$D2.., speeds +$50 / +$58 / +$5C, hit kind +$1B8, damage tables +$108 / +$EF), start a state's animation
(`move.w state, $72(a4)`, `move.w #-1, $78(a4)`, `jsr $5BA6`), then `move.l #R, (a4)` (resume at R from now on) and a
frame loop at R whose conditional branches to the character's yield routine (`jsr $5BA6` animate, `jsr $16F98`, boxes,
`jmp $600E`; one copy per character: Terry $427CC, Ralf $4FC54) end the frame. The decoder walks that code with the
button / facing / EX flag concrete (the facing is right: forward speeds come out positive) and turns it into ops:

  ('anim', state)               the state's animation from its first step (engine $5BB0 via $5BA6)
  ('set', reg, value)           vx (+$50), vy (+$58), g (+$5C), fric (+$54 word, a 0.16 factor), cnt (a counter word)
  ('mul', k)                    vx *= k / 65536 ($36A0 on vx)
  ('move',)                     x += vx
  ('fricmove',)                 vx *= fric, x += vx ($24A2A)
  ('fall',)                     height += vy, vy -= g; landed: height 0 ($37E0)
  ('nudge', dx, dy)             x / height += px (forward +)
  ('dec',)                      cnt -= 1
  ('br', cond, when, target)    branch when cond == when; target 'yield' = the frame ends there (resumes next frame)
  ('resume',)                   the coroutine's resume point: the next op (`move.l #R, (a4)`)
  ('jmp', addr)                 goto (a loop back: Vulcan Punch)
  ('spawn', k, dx, dy)          object k of the decode's 'objects' at x + dx (forward +), height + dy ($24944)
  ('end',) / ('free',)          back to the neutral routine ($25182) / an object frees itself ($34A8)
  ('fxoff',)                    the move's attached effects end (owner +$D1 bit 7: Burn Knuckle's flame watches it)
  bookkeeping kept for the record: ('sound', n) $7A98, ('hitkind', k) +$1B8, ('gauge', n) $155F4, ('stats',) $18C1C,
  ('land',) $15F2C landing dust, ('follow',) $24A02 an effect pinned to its owner, ('inflight',) / ('release',)
  $24A7C / $24A5E the one-projectile-in-flight bit (owner +$E1 bit 5), ('flag', ...) other field writes, ('call', a)
  an unknown routine.
  ('adv',)                      the animate call on the state already playing: one more step tick
  ('check', mask) / ('part',)   a follow-up input check (FOLLOW_CHECKS) / the request cleared (a new part)
Conditions: 'end' (animation over, +$7C bit 7), 'event' (+$7D bit 7: a step with flag $0080 was entered; consumed),
'evstep' (tst.b +$7D: the step has $0080), 'window' (+$7C bit 5: $2000), 'link:<mask>' (a follow-up link armed),
'land' (the last fall landed), 'falling' (vy < 0 after the last fall), 'cnt' (the counter went negative), 'off'
(off screen, $180B6), 'hit' (+$E1 bit 7: this attack connected), 'input' (a button pressed again: mash loops).

    python3 handlers98.py CID INPUT [ex]     e.g. 3 214C; 10 [4]6C; 3 236C ex  -> the ops, the objects, a model run"""
import json, os, re, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import rom96

P1S = {'kof98': '/data/tmp/romspecials/kof98_p.bin', 'kof96': '/data/tmp/romspecials/kof96_p.bin',
       'kof99': '/data/tmp/romspecials/kof99_p.bin'}       # the de-swapped P1 per game (written on first use)
P1 = P1S['kof98']

ROUTINES = {0x248A8: 'init', 0x7A98: 'sound', 0x155F4: 'gauge', 0x18C1C: 'stats', 0x37E0: 'fall', 0x36A0: 'mulfn',
            0x24A2A: 'fricmove', 0x24944: 'spawnfn', 0x24A02: 'follow', 0x24A7C: 'inflight', 0x24A5E: 'release',
            0x180B6: 'offfn', 0x15F2C: 'land', 0x24FE4: 'chain', 0x25182: 'end', 0x34A8: 'free', 0x5BA6: 'animfn',
            0x24926: 'init', 0x248AE: 'init', 0x16B26: 'face', 0x16AEC: 'face', 0x176AE: 'clrinput', 0x1B03C: 'voice',
            0x33A8: 'random', 0x1EB20: 'superflash', 0x3F8A: 'superflash', 0x1813A: 'superflash', 0x24A9A: 'ownerflag',
            0x24AA0: 'ownerflag', 0x24FF6: 'chain', 0x25002: 'chain', 0x2500E: 'chain', 0x2501A: 'chain', 0x25026: 'chain',
            0x24F2C: 'stats', 0x24F34: 'stats', 0x24F3C: 'stats', 0x250C6: 'flags', 0x24F52: 'clrinput',
            0x24D80: 'dmcheck', 0x2505A: 'flags', 0x25032: 'place', 0x16034: 'voice', 0x1603A: 'voice', 0x19AB4: 'superflash', 0x19AE0: 'superflash', 0x25088: 'superflash'}
BOOKKEEPING = ('follow', 'inflight', 'release', 'land', 'stats', 'init', 'chain', 'face', 'clrinput', 'voice', 'superflash',
               'ownerflag', 'flags', 'trail')
# KOF96 / KOF99: the same engine family, the same object fields; the routines at their own addresses (found by their
# code: KOF98's bytes, or the calls in the specials' handlers next to KOF98's)
ROUTINES96 = {0x1A756: 'init', 0x6AA8: 'sound', 0x12CB0: 'stats', 0x2F34: 'fall', 0x2DF4: 'mulfn', 0x1A88C: 'fricmove',
              0x1A7CA: 'spawnfn', 0x1A864: 'follow', 0x1A8C2: 'inflight', 0x1A8A4: 'release', 0x2B2C: 'random',
              0x2C2C: 'free', 0x4D50: 'animfn', 0x11644: 'face', 0x12044: 'clrinput', 0x1ACB4: 'clrinput', 0x14A3C: 'voice',
              0x12A34: 'superflash', 0x1AC8E: 'stats', 0x1AC96: 'stats', 0x1AC9E: 'stats', 0x1A8E0: 'ownerflag',
              0x1ADE2: 'end', 0x10C04: 'voice', 0x10CCC: 'voice', 0x17316: 'voice', 0x17330: 'voice', 0x14A2A: 'voice',
              0x13AB2: 'trail', 0x1A8E6: 'ownerflag', 0x129B0: 'offfn', 0x1AB70: 'dmcheck'}
ROUTINES99 = {0x1F5BC: 'init', 0x1F5C2: 'init', 0x6352: 'sound', 0xFF84: 'gauge', 0x13C96: 'stats', 0x446A: 'animfn',
              0x12884: 'clrinput', 0x1F660: 'spawnfn', 0x21BE: 'fall', 0x207E: 'mulfn', 0x1D42: 'random', 0x1EA4: 'free',
              0x2A4C: 'superflash', 0x1337E: 'superflash', 0x1AB7A: 'superflash', 0x160F6: 'voice', 0x1F760: 'follow',
              0x1F7E8: 'release', 0x1F834: 'inflight', 0x1FE18: 'stats', 0x1FE20: 'stats', 0x1FE28: 'stats',
              0x1FE3E: 'clrinput', 0x1FFB2: 'flags', 0x200A8: 'end', 0x1F7B4: 'fricmove', 0x10BE2: 'voice', 0x14C14: 'trail',
              0x1ADBE: 'zero', 0x1FA32: 'zero', 0x1FC48: 'dmcheck'}   # zero: a follow-up / cancel input check: none (returns d0 = 0)
GAME_ROUTINES = {'kof98': ROUTINES, 'kof96': ROUTINES96, 'kof99': ROUTINES99}
YIELD2 = {'kof98': (0x16F98, 0x1718E), 'kof96': (0x11A54, 0x11C16), 'kof99': (0x12092, 0x12366)}   # the yield routine's call after animate
TEST_FIELDS = {0x7C: 'end', 0x7D: 'evstep', 0xE1: 'hit', 0xE3: 'hitany'}   # +$E3 bit 7: a hit landed since the code cleared it   # tst.b +$7D: the current step has $0080 (not consumed; bclr is 'event')
# Follow-up inputs (TODO #74): the routines a handler calls to read the player's follow-up command, by game. 'latch' (KOF98
# Iori 214A/C $710F2: 214 + A or C sets +$D1 bit 7, the handler tests the bit; FOLLOW_LATCH names the handlers and the
# field), 'fwdBD' (KOF99 $1ADBE: forward + B or D this frame -> d0 non-zero, d1 bit 7 = D; K' 236A/C and 623C). Each
# becomes ('check', mask): the brawler's link presses seen this frame (bit k = FOLLOW_INPUTS[kind][k]) join the move's
# armed set, and the tests become ('br', 'link:<mask>', ...) on that set; ('part',) = the handler clears its request (a
# new part: the armed set empties). Brute force in our emulator (capture/followups98.py): the handler sees a press
# FOLLOW_LAG frames after its button frame (KOF98 4, KOF99 5: the games' input paths), on exactly the frames it calls
# the check (Iori: every frame of the part from its second; K': the steps with $2000, +$7C bit 5 'window').
FOLLOW_CHECKS = {'kof98': {0x710F2: 'latch'}, 'kof99': {0x1ADBE: 'fwdBD'}}
FOLLOW_LATCH = {('kof98', 0x70E42): 0xD1}
FOLLOW_INPUTS = {'latch': ['again'], 'fwdBD': ['fA', 'fAB']}      # the brawler's press per link bit (export_bm link_c)
FOLLOW_LAG = {'kof98': 4, 'kof99': 5}

class Decoder:
    def __init__(self, m):
        self.m = m; self.ins = {}; self.game = getattr(m, 'game', 'kof98'); self.P1 = P1S[self.game]; self.cid = None
        self.R = GAME_ROUTINES[self.game]; self.animfn = next(a for a, n in self.R.items() if n == 'animfn')
        if not os.path.exists(self.P1):
            os.makedirs(os.path.dirname(self.P1), exist_ok=True); open(self.P1, 'wb').write(m.p[:0x100000])

    def at(self, a):
        if a not in self.ins:
            out = subprocess.run(['m68k-linux-gnu-objdump', '-D', '-b', 'binary', '-m', 'm68k', f'--start-address={a}',
                                  f'--stop-address={a + 0x200}', self.P1], capture_output=True, text=True).stdout.splitlines()
            lines = []
            for l in out:
                p = l.split('\t')
                if len(p) >= 3 and re.match(r'^\s*[0-9a-f]+:$', p[0]):
                    txt = ' '.join(p[2:]).strip().split(None, 1)
                    lines.append((int(p[0].strip()[:-1], 16), txt[0], txt[1] if len(txt) > 1 else ''))
            for k, (ad, mn, opd) in enumerate(lines[:-1]):
                if ad not in self.ins: self.ins[ad] = (mn, split_ops(opd), lines[k + 1][0])
        return self.ins[a]

    def events(self, st):
        """the steps with $0080 in state st's animation (0: unknown state or fighter)"""
        if self.cid is None or st is None: return 0
        try: return sum(1 for s_ in rom96.parse_anim(self.m, rom96.anim_addr(self.m, self.cid, rom96.state_slot(self.m, self.cid, st)))[0] if s_[2] & 0x80)
        except Exception: return 0

    def animates(self, a, n=4):
        """the code at a calls the animate routine within its first n instructions (a resume point that starts its own
        state: no animate left to the yield)"""
        for _ in range(n):
            mn, ops, nx = self.at(a)
            if mn == 'jsr' and imm(ops[0]) == self.animfn: return True
            if mn[0] in 'bj' and mn != 'jsr': return False
            a = nx
        return False

    def is_yield(self, a):
        """a character's yield routine: animate ($5BA6), then $16F98 / $1718E (+ boxes), jmp $600E"""
        mn, ops, nx = self.at(a)
        if mn == 'jsr' and self.R.get(imm(ops[0])) == 'zero':           # a cancel check (no input: none), then the yield
            mn2, ops2, _ = self.at(nx)
            return mn2.startswith('beq') and self.is_yield(imm(ops2[0]))
        if mn != 'jsr' or imm(ops[0]) != self.animfn: return False
        mn2, ops2, _ = self.at(nx)
        return mn2 == 'jsr' and imm(ops2[0]) in YIELD2[self.game]

def split_ops(s):
    out, depth, cur = [], 0, ''
    for c in s:
        if c == '(' : depth += 1
        if c == ')': depth -= 1
        if c == ',' and depth == 0: out.append(cur); cur = ''
        else: cur += c
    if cur: out.append(cur)
    return out

def imm(o):
    o = o.lstrip('#')
    return int(o, 16) if o.startswith('0x') else int(o) if re.match(r'^-?\d+$', o) else None

def field(o, reg='a4'):
    """'%a4@(80)' -> 80, '%a4@' -> 0, else None"""
    mt = re.match(rf'^%{reg}@(?:\((-?\d+)\))?$', o)
    return (int(mt.group(1)) if mt.group(1) else 0) if mt else None

SIZE = {'b': 1, 'w': 2, 'l': 4}

class Fields:
    """the object's fields the decode knows, byte by byte (big-endian, as the 68000 reads them)"""
    def __init__(self): self.b = {}; self.k = {}      # k: byte -> (mask, bits) known bits of an unknown byte (andi / ori)
    def put(self, off, v, size):
        for i in range(size): self.k.pop(off + i, None)
        if not isinstance(v, int): [self.b.pop(off + i, None) for i in range(size)]; return
        v &= (1 << 8 * size) - 1
        for i in range(size): self.b[off + i] = (v >> 8 * (size - 1 - i)) & 0xFF
    def get(self, off, size, signed=True):
        if any(off + i not in self.b for i in range(size)): return None
        v = 0
        for i in range(size): v = v << 8 | self.b[off + i]
        return v - (1 << 8 * size) if signed and v >> (8 * size - 1) else v
    def bit(self, off, b):
        if off in self.b: return self.b[off] >> b & 1
        mk, bits = self.k.get(off, (0, 0))
        return bits >> b & 1 if mk >> b & 1 else None
    def setbits(self, off, op, v):
        mk, bits = self.k.get(off, (0, 0))
        if op == 'or': self.k[off] = (mk | v, bits | v)
        else: self.k[off] = (mk | (~v & 0xFF), bits & v)

def decode(m, addr, button='C', ex=False, fields=None, dec=None, depth=0, cid=None):
    """the handler at addr -> {'addr', 'ops': [(addr, op)], 'objects': [decoded object routines]}. fields: an object's
    inherited fields (spawn offsets +$D2 / +$D4, vx, end state +$D8, hit routine +$19C)"""
    dec = dec or Decoder(m)
    if cid is not None: dec.cid = cid
    F = Fields()                                     # facing right, the button, EX, on the ground
    # a human player (+$170 bit 7 clear: no CPU random follow-up), no motion recognised during the move (+$1AC-$1AF: the
    # follow-up windows' bits) and, past the first frame, no new button press (the input record a3 / fp reads 0)
    for off, v, sz_ in [(0x31, 1, 1), (0x1A4, 0x10 << 'ABCD'.index(button), 1), (0x1D6, 1 if ex else 0, 1), (0xC8, 0, 2),
                        (0x170, 0, 1), (0x1AC, 0, 4)] + list(fields or []):
        F.put(off, v, sz_)
    D = {}; A0 = None; ops = []; objects = []; seen = set(); cc = None
    latch = FOLLOW_LATCH.get((dec.game, addr)) if depth == 0 else None; res_val = [None]; follow = [None]
    cnt_field = None; work = [addr]; pending_child = None
    def emit(a, *op): ops.append((a, op))
    def flush_child():
        nonlocal pending_child
        if pending_child is None: return
        ch, at = pending_child; pending_child = None
        if depth >= 3: emit(at, 'spawndeep', ch['routine']); return        # an object spawning itself (Kyo's fury)
        objects.append(decode(m, ch['routine'], button, ex, ch['fields'], dec, depth + 1))
        objects[-1].update(state=next((v for o_, v, s_ in ch['fields'] if o_ == 0x72), None), dx=ch['dx'], dy=ch['dy'])
        emit(at, 'spawn', len(objects) - 1, ch['dx'], ch['dy'])
    def val(o, size=2):
        """an operand's value: int, ('f', off) for an a4 field read at run time / not known, None"""
        if o.startswith('#'): return imm(o)
        f = field(o)
        if f in (0x50, 0x58): return ('f', f)                          # speeds: read at run time
        if f is not None:
            v = F.get(f, size); return ('f', f) if v is None else v
        if re.match(r'^%d\d$', o): return D.get(o)
        if field(o, 'a3') is not None or o.startswith('%fp@'):           # the buttons pressed (a3 = the input record): the
            return 0 if resumed[0] else F.get(0x1A4, 1, False)           # special's own on its first frame, then none
        if o == '%a0@' and isinstance(A0, int) and A0 < 0x100000:       # a ROM table (a state list: +$32 / +$C2 pointers)
            return int.from_bytes(m.p[A0:A0 + size], 'big')
        for r_ in ('a0', 'a1', 'a2'):                                   # the same through a1 / a2 (Power Geyser's pillar
            base_ = A0 if r_ == 'a0' else D.get('%' + r_)                # states, Blaster Wave's offsets, Raging Storm's
            d_ = field(o, r_)                                           # records: (aN) / n(aN))
            if d_ is not None and isinstance(base_, int) and base_ < 0x100000:
                return int.from_bytes(m.p[base_ + d_:base_ + d_ + size], 'big')
        return None
    def store(f, v, size, a):
        nonlocal cnt_field
        if f == 0x00: return
        if isinstance(v, tuple) and v[0] == 'mul': emit(a, 'mul', v[2]); F.put(f, None, size); return
        if isinstance(v, tuple) and v[0] == 'f' and v[1] == f: return
        F.put(f, v, size); stored_at[f] = len(ops)
        if f == 0x19C and depth == 0 and isinstance(v, int) and size == 4 and F.bit(0xE1, 6) == 0:   # a fighter's catch
            emit(a, 'onhit', K(v)); push(v)            # routine (TODO #139): the engine runs it after a catch box's hit-stop
                                                       # (box $38 / $39, $1B9F6) unless +$E1 bit 6 is set (a catch spent: the
                                                       # handler clears it to catch; Kyo's 214A does not, KOF's own trace
                                                       # shows no catch then)
        regs = {0x50: 'vx', 0x58: 'vy', 0x5C: 'g', 0x54: 'fric', 0x20: 'h'}
        if f in regs and size >= 2 and not isinstance(v, tuple):
            x = v / 65536 if size == 4 else (v & 0xFFFF)
            if f == 0x54: x = v & 0xFFFF
            if f == 0x20: x = v / 65536 if size == 4 else v   # the height set (clr.l +$20: a catch puts it on the floor)
            emit(a, 'set', regs[f], x)
        elif f == 0x1B8: emit(a, 'hitkind', v)
        elif f == cnt_field: emit(a, 'set', 'cnt', v)
    a = addr; budget = 4000; work = []; pos = {}
    # loops run at decode time: a field the handler steps once per pass (a repeat count `subq; bne` after the frame loop
    # ended, a state-table pointer `addq #2`) is concrete, so each pass is its own copy of the code: an op's place is
    # (address, the loop fields' values) and a pass with other values walks the code again (unrolled)
    loopvars = {}; yielded = False; stack = []; resumed = [False]; stored_at = {}
    # a call into the fighter's own code (a follow-up check, a shared part) is walked inline: an op's place also
    # carries the return addresses
    def K(t): return (t, tuple((o_, F.get(o_, s_)) for o_, s_ in sorted(loopvars.items())) +   # (+ the scratch fields
                      tuple(F.b.get(o_) for o_ in list(range(0xC2, 0xE0)) + [0x36, 0x37, 0x38, 0x39]),   # $C2-$DF: states,
                      tuple(stack))                  # speeds; +$36: the next part's code, Iori's 214A)
    def push(t): work.append((K(t), dict(F.b), dict(F.k), dict(D), A0, dict(loopvars), list(stack)))
    def yres(a):
        # a yield while a loop field changed since the resume point was set (Blaster Wave's wave count, stepped on the
        # frames its event fires): the next frame resumes at that point with the new values, a place of its own
        # (at most once per event step of the state playing: the values step on its events, Terry's pillar table is
        # longer than the C version's one pillar)
        r = D.get('_res')
        if r is None or r[2] == lv() or r[3] >= dec.events(F.get(0x78, 2)): return
        k = K(r[0]); emit(a, 'resume_at', k); D['_res'] = (r[0], k, lv(), r[3] + 1); push(r[0])
    def lv(): return tuple((o_, F.get(o_, s_)) for o_, s_ in sorted(loopvars.items()))
    while budget:
        budget -= 1
        if a is None:
            while work and work[0][0] in seen: work.pop(0)
            if not work: break
            (a, _, _), F.b, F.k, D, A0, loopvars, stack = work.pop(0); yielded = False; cc = None
        k_ = K(a)
        if k_ in seen:
            emit(a, 'jmp', k_); a = None; continue
        mn, o, nx = dec.at(a)
        if pending_child is not None and not any('%a1@' in x for x in o): flush_child()
        seen.add(k_); pos[k_] = len(ops)
        base = mn.rstrip('bwl') if mn[-1:] in 'bwl' and mn not in ('jsr', 'jmp', 'bclr', 'tstl') else mn
        sz = SIZE.get(mn[-1:], 4)
        if pending_child is not None and not any('%a1@' in x for x in o): flush_child()
        if mn == 'jsr' or mn == 'jmp':
            mt = re.match(r'^%pc@\((0x[0-9a-f]+)\)$', o[0])
            t = imm(o[0]) if o[0].startswith('0x') else int(mt.group(1), 16) if mt else None
            if t is None and o[0] == '%a0@':
                if isinstance(A0, tuple) and A0[0] == 'res' and isinstance(A0[1], int): a = A0[1]; continue   # move.l X, (a4);
                emit(a, 'jmp', 'resume'); a = None; continue                    # movea.l (a4), a0; jmp (a0): X now
            fk = FOLLOW_CHECKS.get(dec.game, {}).get(t)
            if fk and mn == 'jsr':                                              # a follow-up input check
                follow[0] = fk
                if fk == 'latch': emit(a, 'check', 1)
                else: emit(a, 'check', 3); D['%d0'] = ('link', 3); cc = ('link:3', 'Zinv'); D['%d1'] = ('linkd1',)
                a = nx; continue
            name = dec.R.get(t)
            if mn == 'jmp' and dec.is_yield(t): yres(a); emit(a, 'br', None, True, 'yield'); a = None; continue
            if name == 'end': emit(a, 'end'); a = None; continue
            if name == 'free': emit(a, 'free'); a = None; continue
            if mn == 'jmp': a = t; continue
            if name is None and t is not None and t >= 0x30000 and len(stack) < 4:   # the fighter's own subroutine: inline
                stack.append(nx); a = t; continue
            if name == 'sound': emit(a, 'sound', D.get('%d0'))
            elif name == 'gauge': emit(a, 'gauge', F.get(0x1DE, 2))
            elif name == 'animfn':                     # the engine restarts the animation when the state (+$72) differs
                st_ = F.get(0x72, 2)                       # from the one playing (+$78; -1 forces it), else advances it
                if st_ is not None and F.get(0x78, 2) is not None and F.get(0x78, 2) == st_: emit(a, 'adv')
                else: emit(a, 'anim', st_)
                F.put(0x78, st_, 2)
            elif name == 'fall': emit(a, 'fall'); cc = ('land', 'Z'); D['%d1'] = ('falling',)
            elif name == 'mulfn': D['%d0'] = ('mul', D.get('%d0'), (D.get('%d1') or 0) & 0xFFFF)
            elif name == 'fricmove': emit(a, 'fricmove')
            elif name == 'offfn': emit(a, 'offscreen'); cc = ('off', 'N')
            elif name == 'spawnfn':
                d5, d6 = D.get('%d5', 0), D.get('%d6', 0)
                d5 = d5 - 0x10000 if isinstance(d5, int) and d5 > 0x7FFF else d5
                d6 = d6 - 0x10000 if isinstance(d6, int) and d6 > 0x7FFF else d6
                cf = [(0x72, D.get('%d3'), 2), (0xD2, d5 if not F.get(0x31, 1) & 1 else -d5, 2), (0xD4, d6, 2), (0x31, F.get(0x31, 1), 1),
                      (0x1A4, F.get(0x1A4, 1), 1), (0x1D6, F.get(0x1D6, 1), 1)]
                pending_child = ({'routine': A0, 'fields': cf, 'dx': -d5, 'dy': d6}, a)   # dx forward +
            elif name == 'random': emit(a, 'random'); D['%d0'] = ('random',)
            elif name == 'place':                      # the opponent put d0 px in front, facing the attacker (a catch)
                emit(a, 'place', (D.get('%d0') or 0) / 65536)
            elif name == 'zero': D['%d0'] = 0; cc = ('val', 0)
            elif name == 'dmcheck':                    # a desperation move's power check (TODO #139): the brawler's
                D['%d0'] = 2; cc = ('val', 2); F.setbits(0xE4, 'and', 0xFE)   # fury = a plain DM (2; no SDM: +$E4 bit 0)
            elif name in BOOKKEEPING: emit(a, name)
            else: emit(a, 'call', t)
            a = nx; continue
        if mn == 'lea':
            mt = re.match(r'%pc@\((0x[0-9a-f]+)\)', o[0])
            if mt and o[1] == '%a0': A0 = int(mt.group(1), 16)
            mt = re.match(r'^%(a[12])@\((-?\d+)\)$', o[0])                    # lea n(a2), a2: a record pointer steps
            if mt and o[1] == '%' + mt.group(1) and isinstance(D.get(o[1]), int): D[o[1]] += int(mt.group(2))
            a = nx; continue
        if mn in ('nop', 'rts'):
            if mn == 'rts' and stack: a = stack.pop(); continue
            if mn == 'rts': emit(a, 'rts'); a = None; continue
            a = nx; continue
        if mn[0] == 'b' and mn[:3] not in ('btst', 'bcl', 'bse', 'bch') and mn not in ('bclr', 'btst'):
            cond = mn[1:3]; t = imm(o[0])
            if cond == 'ra':
                if dec.is_yield(t): yres(a); emit(a, 'br', None, True, 'yield'); a = None; continue
                a = t; continue
            # condition: concrete flags (cc = ('val', v)) or an abstract one (cc = (name, flag))
            if cc and cc[0] == 'valn':                                      # only bit 7 known (tst.b): N, not Z
                cc = ('val', cc[1]) if cond in ('mi', 'pl') else (cc[2], 'N')
            if cc and cc[0] == 'val':
                v = cc[1]
                taken = {'eq': v == 0, 'ne': v != 0, 'pl': v >= 0, 'mi': v < 0}[cond]
                a = t if taken else nx; continue
            if cc is None or cond not in ('eq', 'ne', 'mi', 'pl'):        # a test this decoder does not model
                tgt = 'yield' if dec.is_yield(t) else K(t)
                if tgt != 'yield': push(t)
                else: yielded = True; yres(a)
                emit(a, 'br', f'cc_{cond}@{a:X}' if cc is None else f'{cc[0]}_{cond}', True, tgt); a = nx; continue
            name, flag = cc
            when = {'eq': True, 'ne': False, 'mi': True, 'pl': False}[cond]   # taken when flag (Z or N) == when
            # map flag polarity to the condition's truth: N/Z set means the condition holds
            truth = not when if flag == 'Zinv' else when                         # btst: Z set = the bit is clear
            if name == 'event_z': name, truth = 'event', not when                # bclr: Z set = the bit was clear
            if name == 'cnt': truth = when                                        # N after subq: went negative
            tgt = 'yield' if dec.is_yield(t) else K(t)
            if tgt != 'yield': push(t)
            else: yielded = True; yres(a)
            emit(a, 'br', name, truth, tgt)
            a = nx; continue
        if base in ('tst',):
            f = field(o[0])
            f0 = field(o[0], 'a0')
            if latch is not None and f == latch and sz == 1: cc = ('link:1', 'N')   # the follow-up request (bit 7)
            elif f0 is not None and A0 == 'owner': cc = ({0xD1: 'owner_fxoff'}.get(f0, f'owner_{f0:X}'), 'N')
            elif f is not None and f in TEST_FIELDS: cc = (TEST_FIELDS[f], 'N')
            elif f is not None and F.get(f, sz) is not None: cc = ('val', F.get(f, sz))
            elif f is not None and sz == 1 and F.bit(f, 7) is not None: cc = ('valn', -F.bit(f, 7), 'f%X' % f)
            elif o[0] == '%d1' and D.get('%d1') == ('falling',): cc = ('falling', 'N')
            elif o[0].startswith('%d') and isinstance(D.get(o[0]), int): cc = ('val', D[o[0]])
            else: cc = ('f%X' % (f if f is not None else -1), 'N')
            a = nx; continue
        if mn == 'btst':
            b = imm(o[0]); f = field(o[1])
            if o[1] == '%d1' and b == 7 and D.get('%d1') == ('linkd1',): cc = ('link:2', 'Zinv')   # fwdBD: D, not B
            elif f == 0x7C and b == 5: cc = ('window', 'Zinv')             # the current step has $2000 (a follow-up window)
            elif f is not None and b < 8 and F.bit(f, b) is not None: cc = ('val', F.bit(f, b))
            elif o[1].startswith('%fp@') or field(o[1], 'a3') is not None: cc = ('val', 0 if resumed[0] else 1)
            elif field(o[1], 'a0') is not None and A0 == 'owner': cc = (f'owner_{field(o[1], "a0"):X}.{b}', 'Zinv')
            else: cc = ('f%X.%d' % (f if f is not None else -1, b), 'Zinv')
            a = nx; continue
        if mn == 'bclr':
            f = field(o[1]); b = imm(o[0])
            cc = ('event_z', 'Z') if f == 0x7D and b == 7 else ('f%X.%d' % (f or 0, b), 'Z')
            a = nx; continue
        if base == 'move' or base == 'movea' or mn.startswith('move'):
            if mn == 'moveq': D[o[1]] = imm(o[0]); a = nx; continue
            src, dst = o
            v = val(src, sz)
            if not dst.startswith('%a') or dst.startswith('%a4@') or dst.startswith('%a1@'):   # move sets N / Z
                cc = ('val', v) if isinstance(v, int) else (f'mv{src}', 'N')
            if dst == '%a0' and field(src) == 0x84: A0 = 'owner'; a = nx; continue
            if dst == '%a0' and src == '%a4@': A0 = ('res', res_val[0]); a = nx; continue
            if dst == '%a0' and field(src) is not None: A0 = v if isinstance(v, int) else None; a = nx; continue
            if dst in ('%a1', '%a2'): D[dst] = v if isinstance(v, int) else None; a = nx; continue
            if dst == '%a4@': res_val[0] = v if isinstance(v, int) else None
            if dst == '%a4@' and isinstance(v, int) and F.get(0x72, 2) is not None and F.get(0x78, 2) is not None \
                    and F.get(0x72, 2) != F.get(0x78, 2) and 0 < F.get(0x72, 2) < 0x400 \
                    and not dec.animates(v):                                          # a new state left to the yield's
                emit(a, 'anim', F.get(0x72, 2)); F.put(0x78, F.get(0x72, 2), 2)           # animate call (Ryo's 178)
            if dst == '%a4@' and isinstance(v, int):                      # move.l #R, (a4): the resume point
                if v == nx: emit(a, 'resume'); D['_res'] = (v, K(v), lv(), 0)
                else: emit(a, 'resume_at', K(v)); push(v); D['_res'] = (v, K(v), lv(), 0)
                yielded = False; resumed[0] = True
                a = nx; continue
            fd = field(dst)
            if fd is not None:
                store(fd, v if not (isinstance(v, tuple) and v[0] == 'f' and fd == 0x50) else v, sz, a)
                if fd == 0x72: pass
                a = nx; continue
            fa1 = field(dst, 'a1')
            if fa1 is not None and pending_child is not None:
                if isinstance(v, tuple) and v[0] == 'f': v = F.get(v[1], sz)
                pending_child[0]['fields'].append((fa1, v, sz))
                a = nx; continue
            if re.match(r'^%d\d$', dst):
                D[dst] = v if not isinstance(v, tuple) or v[0] != 'f' else ('f', v[1]); a = nx; continue
            a = nx; continue
        if base in ('add', 'addq', 'sub') and len(o) == 2:
            fd = field(o[1]); v = val(o[0], sz)
            if base == 'sub' and fd == 0x58: a = nx; continue
            if fd == 0x18:
                if isinstance(v, tuple) and v[0] in ('f', 'mul') and (v[1] == 0x50 or v[1] == ('f', 0x50)): emit(a, 'move')
                elif isinstance(v, int): emit(a, 'nudge', v if sz == 2 else v / 65536, 0)
                else: emit(a, 'nudge?', v)
            elif fd == 0x20:
                if isinstance(v, int): emit(a, 'nudge', 0, v)
                else: emit(a, 'nudgey?', v)
            elif o[1].startswith('%d') and isinstance(D.get(o[1]), int) and isinstance(v, int): D[o[1]] += v
            elif fd is not None and base == 'addq' and isinstance(v, int) and F.get(fd, sz) is not None:   # a table pointer steps
                F.put(fd, F.get(fd, sz) + v, sz); loopvars[fd] = sz
            a = nx; continue
        if mn in ('subqw', 'subqb', 'subql') and field(o[1]) is None:      # a register: a loop counter within the frame
            v = imm(o[0])
            if isinstance(D.get(o[1]), int): D[o[1]] -= v; cc = ('val', D[o[1]])
            else: cc = ('dreg', 'N')
            a = nx; continue
        if mn in ('subqw', 'subqb', 'subql') and (yielded or 0 < (F.get(field(o[1]), sz) or 0) <= 8) and \
                F.get(field(o[1]), sz) is not None and field(o[1]) not in (0x50, 0x58):   # (or a small count: Blaster Wave's 4 waves)
            fd = field(o[1]); nv = F.get(fd, sz) - imm(o[0])                 # a repeat count, once per pass (the frame loop
            F.put(fd, nv, sz); loopvars[fd] = sz; cc = ('val', nv)          # ended before it): concrete, the passes unrolled
            a = nx; continue
        if mn in ('subqw', 'subqb', 'subql'):
            fd = field(o[1])
            cnt_field = fd; emit(a, 'dec'); cc = ('cnt', 'N')
            if F.get(fd, sz) is not None:                # value known: the counter is set where the field was written
                at = stored_at.get(fd, 0)                    # (or at the start: a field the spawner gave an object)
                ops.insert(at, (a, ('set', 'cnt', F.get(fd, sz))))
                for k in pos:
                    if pos[k] >= at: pos[k] += 1
                for k in stored_at:
                    if stored_at[k] >= at: stored_at[k] += 1
            a = nx; continue
        if mn in ('asrl', 'lsrl') and o[1].startswith('%d') and isinstance(imm(o[0]), int) and \
                isinstance(D.get(o[1]), tuple) and D[o[1]] == ('f', 0x50):      # vx >> n (Ryo's catch: the rush at vx / 4)
            D[o[1]] = ('mul', ('f', 0x50), 65536 >> imm(o[0])); a = nx; continue
        if mn == 'swap' and isinstance(D.get(o[0]), int):                 # a register's two words (a DM's state pairs)
            v = D[o[0]] & 0xFFFFFFFF; D[o[0]] = (v >> 16 | v << 16) & 0xFFFFFFFF; a = nx; continue
        if base == 'neg':
            fd = field(o[0])
            if fd is not None and F.get(fd, sz) is not None: store(fd, -F.get(fd, sz), sz, a)
            elif o[0].startswith('%d') and isinstance(D.get(o[0]), int): D[o[0]] = -D[o[0]]
            a = nx; continue
        if base in ('clr',):
            fd = field(o[0])
            if fd is not None: store(fd, 0, sz, a)
            elif o[0].startswith('%d'): D[o[0]] = 0
            a = nx; continue
        if base in ('ori', 'andi', 'or', 'and'):
            fd = field(o[1]); v = imm(o[0]) if o[0].startswith('#') else val(o[0], sz)   # and.b (fp), d0: the buttons held
            v = v if isinstance(v, int) else None                                         # (none past the first frame)
            if fd is not None:
                if latch is not None and fd == latch and base == 'andi' and not v & 0x80: emit(a, 'part')   # request cleared
                elif fd == 0xD1 and base == 'ori' and v & 0x80: emit(a, 'fxoff')
                elif fd == 0xE3 and base == 'andi' and not v & 0x80: emit(a, 'hitclr')   # +$E3 bit 7 cleared
                elif fd == 0xE4 and base == 'ori' and v & 0x10 and depth == 0: emit(a, 'hold')       # +$E4 bit 4: the
                elif fd == 0xE4 and base == 'andi' and not v & 0x10 and depth == 0: emit(a, 'unhold') # caught victim held
                elif fd == 0x7D and base == 'andi' and not v & 0x80: emit(a, 'evclr')   # the event consumed (tst + andi:
                elif fd in (0x7C, 0x7D) and base == 'andi': pass                          # Mr. Big's Blaster Wave)
                if F.get(fd, sz) is not None: F.put(fd, (F.get(fd, sz) | v) if base.startswith('or') else (F.get(fd, sz) & v), sz)
                elif sz == 1 and isinstance(v, int): F.setbits(fd, 'or' if base.startswith('or') else 'and', v & 0xFF)
                emit(a, 'flag', base, fd, v & 0xFF)
            elif o[1].startswith('%d') and isinstance(D.get(o[1]), int) and isinstance(v, int):
                D[o[1]] = (D[o[1]] | v) if base.startswith('or') else (D[o[1]] & v); cc = ('val', D[o[1]])
            elif o[1].startswith('%d'):
                cc = (f'{base}_{D.get(o[1])[0] if isinstance(D.get(o[1]), tuple) else "d"}', 'Z'); D[o[1]] = None
            a = nx; continue
        if base == 'cmpi':
            if o[1].startswith('%d') and isinstance(D.get(o[1]), int) and isinstance(imm(o[0]), int):   # a known register
                cc = ('val', (D[o[1]] & 0xFFFF) - imm(o[0])); a = nx; continue                        # (dmcheck's d0)
            a = nx; cc = ('cmp', 'Z'); continue
        emit(a, 'unknown', mn, o); a = nx
    if pending_child is not None: flush_child()
    hit = None
    hr = F.get(0x19C, 4, False)
    if hr and depth > 0 and depth < 3 and not (fields and any(o_ == -1 for o_, v, s_ in fields)):   # an object's hit routine (travelling ones)
        keep = [(o_, F.get(o_, 2), 2) for o_ in (0x72, 0xD2, 0xD4, 0xD8) if F.get(o_, 2) is not None]
        hit = decode(m, hr, button, ex, keep + [(0x50, F.get(0x50, 4), 4), (-1, 0, 1)], dec, depth + 1)
    prune(ops, pos)
    return {'addr': addr, 'ops': ops, 'pos': pos, 'objects': objects, 'hit': hit, 'kind': F.get(0xF5, 1), 'follow': follow[0],
            'vx': (F.get(0x50, 4) or 0) / 65536, 'fields': {o_: F.get(o_, 2) for o_ in (0x72, 0xD2, 0xD4, 0xD8)}}

def prune(ops, pos):
    """a branch on a test the decoder does not model whose two ways meet again before anything but bookkeeping (the
    follow-up / cancel checks with no input: both ways reach the same op) is no branch: dropped (('flag', 'pruned'))"""
    skip = {'sound', 'gauge', 'stats', 'flag', 'init', 'land', 'chain', 'face', 'clrinput', 'voice', 'superflash',
            'ownerflag', 'flags', 'trail', 'random'}
    def lands(i):
        seen = set()
        while i < len(ops) and i not in seen:
            seen.add(i); op = ops[i][1]
            if op[0] in skip: i += 1
            elif op[0] == 'jmp' and isinstance(op[1], tuple) and op[1] in pos: i = pos[op[1]]
            else: return i
        return i
    clean = {None, 'end', 'event', 'evstep', 'window', 'land', 'falling', 'cnt', 'off', 'hit', 'owner_fxoff'}
    for _ in range(4):
        for i, (a, op) in enumerate(ops):
            if op[0] == 'br' and op[1] not in clean and not str(op[1]).startswith('link:') and op[3] != 'yield' and op[3] in pos and lands(i + 1) == lands(pos[op[3]]):
                ops[i] = (a, ('flag', 'pruned', op[1]))

def show(d, ind=''):
    for a, op in d['ops']:
        print(f'{ind}{a:06X} ' + ' '.join(str(x) if not isinstance(x, int) or abs(x) < 256 else f'${x:X}' for x in op))
    for k, ob in enumerate(d['objects']):
        print(f'{ind}object {k}: routine ${ob["addr"]:X}, state {ob.get("state")}, at +{ob["dx"]} / {ob["dy"]}, kind {ob["kind"]}')
        show(ob, ind + '    ')
    if d.get('hit'):
        print(f'{ind}on its hit: ${d["hit"]["addr"]:X}'); show(d['hit'], ind + '    ')

# ---- the handler of a captured special ------------------------------------------------------------------------------
CAP = os.path.join(HERE, 'capture', 'specials98')
CAPS = {'kof98': CAP, 'kof96': os.path.join(HERE, 'capture', 'specials'), 'kof99': os.path.join(HERE, 'capture', 'specials_kof99')}

def handler_of(cid, inp, ex=False, game='kof98'):
    """(handler address, button) of a special as captured (capture/specials98: the move code's +$198 on the try's first
    special frame). inp in specials96 notation ('214C', '[4]6C'); 'EX ...' = the EX version (c<id>x, '_ex' file)"""
    import importlib.util
    spec = importlib.util.spec_from_file_location('specials96_top', os.path.join(HERE, 'specials96.py'))
    S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
    tag = '_ex' if ex or inp.startswith('EX ') else ''
    inp = inp.replace('EX ', '')
    T = json.load(open(os.path.join(CAPS[game], f'{cid}{tag}.json'))); L = open(os.path.join(CAPS[game], f'{cid}{tag}.txt')).read().splitlines()
    for t in T:
        if t['air'] or S.notation(t['events']) != inp: continue
        for f in range(t['start'], t['start'] + t.get('gap', 220)):
            o = bytes.fromhex(L[f - 1].split()[3]); st = struct.unpack('>H', o[0x72:0x74])[0]
            if S.special_state(game, st): return struct.unpack('>I', o[0x198:0x19C])[0], t['button']
    raise KeyError((cid, inp))

# ---- the model: a decoded program played with the KOF98 animation engine's timing --------------------------------------
class Obj:
    """one object playing ops. Per frame: the handler runs from its resume point until a branch to the yield routine,
    then the animation engine advances (a step shows ticks + 1 frames; the frame a state starts counts as the first
    of its first step; past the last step: +$7C bit 7 'end', a hold stays, a loop restarts)"""
    def __init__(self, m, cid, prog, x=0.0, h=0.0, vx=0.0):
        self.m, self.cid, self.prog = m, cid, prog
        self.ops = [op for a, op in prog['ops']]; self.addrs = [a for a, op in prog['ops']]
        self.pc = 0; self.x, self.h, self.vx, self.vy, self.g, self.fric, self.cnt = x, h, vx, 0.0, 0.0, 0, 0
        self.state = None; self.steps = None; self.step = 0; self.left = 0; self.done = False; self.event = False
        self.landed = False; self.falling = False; self.hit = False; self.over = False; self.spawned = []; self.mode = 'hold'
        self.fxoff = False; self.owner = None; self.off = False
        self.hitpc = None; self.hitany = False; self.dead = 0; self.go = None   # a catch routine (onhit), +$E3 bit 7
        self.presses = {}; self.f = 0; self.links = 0            # follow-ups: {frame: link bits seen then}, the armed set,
        self.switch = False; self.parts = [[]]                   # the states per part (a taken link branch: the next anim
                                                                 # starts a part)
    def play(self, st):
        self.state = st
        self.steps, self.mode = rom96.parse_anim(self.m, rom96.anim_addr(self.m, self.cid, rom96.state_slot(self.m, self.cid, st)))
        self.step = 0; self.left = self.steps[0][0] + 1; self.done = False
        self.event = bool(self.steps[0][2] & 0x80); self.x += -self.steps[0][5]
    def advance(self):
        if self.steps is None: return
        self.left -= 1
        if self.left > 0: return
        if self.step + 1 < len(self.steps):
            self.step += 1
        else:
            self.done = True
            if self.mode == 'hold': self.left = 1; return
            self.step = 0
        t, fi, fl, bx, raw, dx = self.steps[self.step]
        self.left = t + 1; self.x += -dx
        self.event = bool(fl & 0x80)                  # the engine copies the step's flags to +$7C / +$7D ($5C4A)
    def cond(self, c):
        if c == 'end': return self.done
        if c == 'event':
            e = self.event; self.event = False; return e
        if c == 'land': return self.landed
        if c == 'falling': return self.falling
        if c == 'cnt': return self.cnt < 0
        if c == 'off': return self.off
        if c == 'hit': return self.hit
        if c == 'hitany': return self.hitany
        if c == 'owner_fxoff': return self.owner is not None and self.owner.fxoff
        if c == 'evstep': return self.event           # +$7D bit 7: the step's $0080 unless the code cleared it
        if c == 'window': return self.steps is not None and bool(self.steps[self.step][2] & 0x2000)
        if isinstance(c, str) and c.startswith('link:'): return bool(self.links & int(c[5:]))
        return False
    def frame(self, cam=0):
        """one frame of handler code; returns at the yield"""
        n = 0
        while not self.over:
            n += 1
            if n > 500: raise RuntimeError('no yield')
            op = self.ops[self.pc]; k = op[0]; self.pc += 1
            if k == 'anim':
                self.play(op[1])
                if self.switch: self.parts.append([]); self.switch = False
                if op[1] not in self.parts[-1]: self.parts[-1].append(op[1])
            elif k == 'set':
                if op[1] == 'vx': self.vx = op[2]
                elif op[1] == 'vy': self.vy = op[2]
                elif op[1] == 'g': self.g = op[2]
                elif op[1] == 'fric': self.fric = op[2]
                elif op[1] == 'cnt': self.cnt = op[2]
                elif op[1] == 'h': self.h = op[2]
            elif k == 'mul': self.vx = self.vx * op[1] / 65536
            elif k == 'move': self.x += self.vx
            elif k == 'fricmove': self.vx = self.vx * self.fric / 65536; self.x += self.vx
            elif k == 'fall':
                v0 = self.vy; self.vy -= self.g; self.h += v0
                self.landed = self.h <= 0; self.falling = self.vy < 0 and not self.landed
                if self.landed: self.h = 0
            elif k == 'nudge': self.x += op[1]; self.h += op[2]
            elif k == 'dec': self.cnt -= 1
            elif k == 'offscreen': sx = self.x - cam if cam is not None else 0; self.off = sx <= -64 or sx >= 384
            elif k == 'resume': self.resume = self.pc
            elif k == 'resume_at': self.resume = self.prog['pos'][op[1]]
            elif k == 'br':
                take = True if op[1] is None else (self.cond(op[1]) == op[2])
                if take and isinstance(op[1], str) and op[1].startswith('link:') and op[2]: self.switch = True
                if take:
                    if op[3] == 'yield': self.pc = self.resume; return
                    self.pc = self.prog['pos'][op[3]]
            elif k == 'jmp':
                if op[1] == 'resume': self.pc = self.resume; return
                self.pc = self.prog['pos'][op[1]]
            elif k == 'spawn': self.spawned.append((op[1], op[2], op[3]))
            elif k in ('end', 'free', 'rts'): self.over = True; return
            elif k == 'fxoff': self.fxoff = True
            elif k == 'evclr': self.event = False
            elif k == 'onhit': self.hitpc = self.prog['pos'][op[1]]
            elif k == 'hitclr': self.hitany = False
            elif k == 'adv': self.advance()
            elif k == 'check': self.links |= self.presses.get(self.f, 0) & op[1]
            elif k == 'part': self.links = 0
            elif k == 'follow' and self.owner is not None: self.x = self.owner.x + self.ofs[0]; self.h = self.owner.h + self.ofs[1]
    def tick(self, cam=0):
        self.spawned = []
        if self.dead:                                 # the catch's hit-stop frame: no code, no animation
            self.dead -= 1; self.f += 1
            if not self.dead: self.pc = self.resume = self.go
            return
        self.frame(cam)
        if not self.over: self.advance()
        self.f += 1
    def shown(self):
        if self.steps is None: return None
        return self.steps[self.step][1]

def run_model(m, cid, prog, frames=200, x=0.0, hit_at=None, cam=-160, presses=None, hits=(), catch_at=None):
    """the program played alone (a whiff): per frame (state, ROM frame index, x, height, spawns [(object, x, h, vx)]);
    its objects played as their own Obj from their spawn frame (rows per object: frame, state, ROM frame, x, height)"""
    o = Obj(m, cid, prog, x=x); o.resume = 0; rows = []; objs = []; o.presses = presses or {}
    for f in range(frames):
        if hit_at is not None and f == hit_at: o.hit = True
        if f in hits: o.hitany = True                 # +$E3 bit 7: every hit (the game's life drops)
        if catch_at is not None and f == catch_at + 1 and o.hitpc is not None:   # a catch box connected at catch_at:
            o.dead = 1; o.go = o.hitpc; o.hitpc = None                             # one dead frame, then its routine
        o.tick(cam)
        sp = []
        for k, dx, dy in o.spawned:
            ob = prog['objects'][k]; fl = ob['fields']
            c = Obj(m, cid, ob, x=o.x, h=o.h, vx=ob['vx'])   # the spawner copies the thrower's place; the routine offsets it
            c.resume = 0; c.born = f; c.rows = []; c.owner = o; c.ofs = (dx, dy); objs.append(c); sp.append(k)
        for c in objs:
            if c.over or c.born == f and False: continue
            if c.born < f or True:
                if not c.rows or c.born < f: pass
        for c in objs:
            if c.over: continue
            if c.born == f: c.frame(cam)              # its first frame: its code runs, its animation does not advance
            else: c.tick(cam)
            if not c.over: c.rows.append((f, c.state, c.shown(), round(c.x, 2), round(c.h, 2)))
        rows.append((f, o.state, o.shown(), round(o.x, 2), round(o.h, 2), sp))
        if o.over: break
    return rows, objs

# ---- export: a decoded special for the brawler (export96 -> tools/brawler/export_bm.py) ---------------------------------
# The specials played from the ROM in the brawler (prototype, 2026-10-05): KOF98 input per fighter. Everything else keeps
# its captured script. A special qualifies when its program uses only the ops below (BODY_OPS) and its objects decode.
ROM_SPECIALS = {'terry': {'214C', '623C', 'EX 236C', '236C', '214D', '623D', '426B', '623A', '623B', '21416C'},
                'ralf': {'[4]6C', '[2]8C', '[4]6D', '[4]6A', '[2]8A', '[4]6B', '23624C'},
                'ryo': {'236A', '623A', '236D', 'EX 623A', '624D', '23624C'}, 'robert': {'EX 236C', '624D', '623C', '623D', '23624C'},
                'yamazaki': {'623C', '623D', '623B'}, 'billy': {'623C', '426C', '214B', '236236C'}, 'kyo': {'623C', '214A', 'EX 236A', '236C', '21426C'},
                'iori': {'236A', '623D', '214A'}, 'mai': {'236A', '426D', '214C', '623D', 'EX 214D', '623A', '21426D'},
                'yashiro': {'214B', '214D', '426A', '624C', '624A', '623A'}, 'rugal': {'236A', '6426D', '6426B'},
                'geese': {'236C', '623C', '623A', '236A'}, 'mr_big': {'236A', '63214C', '623A', '623C', 'AAAA', '63214D'},
                'krauser': {'214A', '214B', '41236B', '236D'}, 'goenitz': {'41236A', '41236B', '41236C', '41236D', '214B'},
                'k_dash': {'236C', '214D', '623C', '236B', '623A', '236D'}}
ROM_GAME = {'geese': 'kof96', 'mr_big': 'kof96', 'krauser': 'kof96', 'goenitz': 'kof96', 'k_dash': 'kof99'}   # else kof98
BODY_OPS = {'anim', 'set', 'mul', 'move', 'fricmove', 'fall', 'nudge', 'dec', 'br', 'resume', 'resume_at', 'jmp',
            'spawn', 'fxoff', 'end', 'hitkind', 'adv', 'check', 'part', 'evclr', 'onhit', 'place', 'hitclr', 'hold', 'unhold'}
DROP_OPS = {'sound', 'gauge', 'stats', 'flag', 'init', 'land', 'chain', 'face', 'clrinput', 'voice', 'superflash',
            'ownerflag', 'flags', 'trail'}
CONDS = {None: 7, 'end': 0, 'event': 1, 'land': 2, 'falling': 3, 'cnt': 4, 'hit': 5, 'off': 6, 'evstep': 8, 'window': 9,
         'link': 10, 'hitany': 11}                     # fighter.h PC_*; 'link:<mask>' -> PC_LINK with the mask
HITSTOP_TABLES = {'kof98': 0x1DCCC, 'kof96': 0x16E20, 'kof99': 0x19832}   # by the step's flags bits 4-6 (KOF98 $1DC52):
def no_stop(m, fl):                                    # attacker / victim hit-stop frames; all 0 (class 4, KOF96 also
    t = HITSTOP_TABLES.get(m.game)                     # 6): a barrage hit, nobody stops and the victim reels in place
    return t is not None and not any(m.u8(t + 4 * ((fl & 0x70) >> 4) + k) for k in range(3))   # (Ralf's 164, Ryo's 181)
# the attack box that catches: $37 on a step with $4000 (+$7C bit 6: Ryo's 178): after its hit-stop the engine runs the
# attacker's +$19C routine (KOF98 $1B9F6 on the attacker's +$AA; boxes $38 / $39 clear the attacker's +$AA at the hit,
# $3C00: Kyo's 214A hits on in KOF's trace; $37 without $4000 catches only after tests on the victim, not modelled)
def is_catch(box, fl):
    return box == 0x37 and bool(fl & 0x4000)
def cond_id(c): return CONDS['link'] if isinstance(c, str) and c.startswith('link:') else CONDS[c]
def cond_ok(c): return c in CONDS or isinstance(c, str) and c.startswith('link:')

def anim_steps(m, cid, st):
    return rom96.parse_anim(m, rom96.anim_addr(m, cid, rom96.state_slot(m, cid, st)))

def follow_parts(m, cid, prog, links, frames=300):
    """a follow-up special's parts and links as the brawler lists them (bspart_t / bslink_t; the program decides at run
    time): the model run with no press (part 0) and with each link pressed throughout; a part = the states played
    between two link switches. -> parts [{'states', 'next': None}], links [{'from', 'to', 'input'}]"""
    parts, out = [], []
    def part(sts):
        for i, p in enumerate(parts):
            if p['states'][0] == sts[0]:
                p['states'] += [s_ for s_ in sts if s_ not in p['states']]; return i
        parts.append({'states': list(sts), 'next': None}); return len(parts) - 1
    o = Obj(m, cid, prog); o.resume = 0
    for f in range(frames):
        o.tick()
        if o.over: break
    part(o.parts[0])
    for k, inp in enumerate(links):
        o = Obj(m, cid, prog); o.resume = 0; o.presses = {f: 1 << k for f in range(frames)}
        for f in range(frames):
            o.tick()
            if o.over: break
        ix = [part(p) for p in o.parts if p]
        for a_, b_ in zip(ix, ix[1:]):
            if not any(l['from'] == a_ and l['to'] == b_ and l['input'] == inp for l in out): out.append({'from': a_, 'to': b_, 'input': inp})
    return parts, out

def openings(m, cid, prog, frames=300, presses=None):
    """the whiff model run: per state the hit windows it opens (an active step, $0100, entered when the step before
    was not active-and-chained ($4000), a state's first step counting as new), the frame of the last opening, the apex
    frame, the frames played. presses: the follow-up presses ({frame: link bits})"""
    o = Obj(m, cid, prog); o.resume = 0; o.presses = presses or {}
    per, last, prev, peak, top = {}, -1, None, 0, -1
    live, caught = None, None                          # a catch (TODO #139): its routine counted as if every hit lands
    for f in range(frames):
        st0, step0 = o.state, o.step
        if caught is not None and f == caught + 1: o.dead = 1; o.go = o.hitpc; o.hitpc = None
        o.tick()
        if o.over: return per, last, peak, f
        if o.steps is not None and (o.state, o.step) != (st0, step0) or f == 0:
            fl = o.steps[o.step][2]
            ids = [k_ & 0xFF for k_ in o.steps[o.step][3] if k_ >= 0x100]
            if ids: live = ids[-1]
            p = prev if o.state == st0 else None
            if fl & 0x100 and not (p is not None and p & 0x100 and p & 0x4000):
                per[o.state] = per.get(o.state, 0) + 1; last = f
                if o.hitpc is not None and is_catch(live, fl) and caught is None: caught = f; o.hit = True
                if caught is not None: o.hitany = True
            prev = fl
        if o.h > top: top, peak = o.h, f
    return per, last, peak, frames

def object_rows(m, cid, ob, owner_x=0.0, frames=240):
    """an object's flight from the model: rows [rom frame, x from the thrower's place at the spawn (forward +),
    height, live attack box (type x y w h) or None, own box (slot 1) or None], loop (row the flight repeats from, None:
    it ends), follow (pinned to its owner: x / height are offsets from it)"""
    c = Obj(m, cid, ob, x=0.0, h=0.0, vx=ob['vx']); c.resume = 0
    follow = any(op[0] == 'follow' for a, op in ob['ops'])
    offs = any(op[0] == 'offscreen' for a, op in ob['ops'])   # it flies until off screen: a looping flight repeats
    # (one whose program ends it itself, a counter / its animations (Goenitz's Yonokaze), plays to its end)
    if follow: c.owner = Obj(m, cid, {'ops': [], 'objects': []}); c.ofs = (ob['dx'], ob['dy'])
    rows, live, seen = [], None, {}
    for f in range(frames):
        if f == 0: c.frame(None)                      # never off screen: the brawler tests that itself
        else: c.tick(None)
        if c.over: break
        t, fi, fl, bx, raw, dx = c.steps[c.step]
        atk = {k: v for k, v in bx.items() if k < 0x30 or k >= 0x100}
        if atk: live = next(iter(atk.items()))
        a = [live[0] & 0x3F if live[0] < 0x100 else live[0] & 0xFF] + list(live[1]) if live and fl & 0x100 else None
        rows.append([fi, round(c.x, 3), round(c.h, 3), a, bx.get(0x31)])
        if offs and c.mode == 'loop' and c.done and c.step == 0 and c.left == c.steps[0][0] + 1:   # one full cycle played:
            cyc = sum(s[0] + 1 for s in c.steps)                                        # the flight repeats it
            return rows[:-1], len(rows) - 1 - cyc, follow
    return rows, None, follow

def export_rom(m, cid, inp, add, game='kof98'):
    """a special's ROM program in export terms (export96 calls it for ROM_SPECIALS; tools/brawler/export_bm.py compiles
    it): ops (bookkeeping dropped, branch targets as op indices), anims {state: steps (frame = export index via add,
    ticks, flags, dx, boxes)}, per state the hits it opens (whiff model), objects (flight rows for export_bm's
    projectile tables), hit kind, the frame of the last hit / the apex (the rising reversal's invincibility)"""
    ex = inp.startswith('EX ')
    h, b = handler_of(cid, inp, ex, m.game)
    prog = decode(m, h, b, ex, cid=cid)
    bad = [op for a, op in prog['ops'] if op[0] not in BODY_OPS | DROP_OPS or (op[0] == 'br' and not cond_ok(op[1]))
           or (op[0] == 'anim' and op[1] is None)]
    if bad: return {'error': f'ops {bad[:3]}'}
    kept, idx = [], {}
    for i, (a, op) in enumerate(prog['ops']):
        idx[i] = len(kept)
        if op[0] not in DROP_OPS: kept.append((a, op))
    def target(t): return 'yield' if t == 'yield' else idx[prog['pos'][t]]
    ops, hitkind, states = [], 1, []
    idx_of = {id(op): i for i, (a, op) in enumerate(prog['ops'])}
    hk_end = min([prog['pos'][op[1]] for a, op in prog['ops'] if op[0] == 'onhit'] or [len(prog['ops'])])
    for a, op in kept:
        k = op[0]
        if k == 'hitkind':                             # the move's last (a catch routine's own kinds not: they come
            if idx_of[id(op)] < hk_end: hitkind = op[1]   # after its entry)
            continue
        if k == 'br': ops.append(('br', cond_id(op[1]), 1 if op[2] else 0, target(op[3])) + ((int(op[1][5:]),) if cond_id(op[1]) == CONDS['link'] else ()))
        elif k == 'jmp': ops.append(('br', CONDS[None], 1, 'yield') if op[1] == 'resume' else ('jmp', idx[prog['pos'][op[1]]]))
        elif k == 'resume_at': ops.append(('resume_at', idx[prog['pos'][op[1]]]))
        elif k == 'onhit': ops.append(('onhit', idx[prog['pos'][op[1]]]))
        elif k == 'anim':
            if op[1] not in states: states.append(op[1])
            ops.append(('anim', states.index(op[1]), op[1]))
        else: ops.append(op)
    # hitkind ops were removed after indexing: re-index (they are never branch targets in the studied handlers)
    rem = [i for i, (a, op) in enumerate(kept) if op[0] == 'hitkind']
    def fix(t): return t if t == 'yield' else t - sum(1 for r in rem if r < t)
    ops = [(o[0], o[1], o[2], fix(o[3])) + tuple(o[4:]) if o[0] == 'br' else (o[0], fix(o[1])) if o[0] in ('jmp', 'resume_at', 'onhit') else o for o in ops]
    anims = {}
    for st in states + [ob.get('state') for ob in prog['objects']] + ([prog['objects'][0]['hit']['fields'].get(0x72)] if False else []):
        if st is None or st in anims: continue
        steps, mode = anim_steps(m, cid, st)
        anims[st] = {'mode': mode, 'steps': [{'frame': add(fi), 'ticks': t, 'flags': fl, 'dx': dx, 'boxes': {f'{k_:02X}': v for k_, v in bx.items()}}
                                             for t, fi, fl, bx, raw, dx in steps]}
    live = None                                                # each step's reaction (box_react) by the attack box live
    for st in states:                                          # on it (the last one loaded: rom_c's rule), packed
        for s in anims[st]['steps']:
            ids = [int(k[1:], 16) for k in s['boxes'] if k[0] == '1' and len(k) == 3]
            if ids: live = ids[-1]
            s['react'] = box_react(m, live, cid) if live is not None and s['flags'] & 0x100 else 0
            s['catch'] = 1 if is_catch(live, s['flags']) and s['flags'] & 0x100 else 0
            s['nostop'] = 1 if s['flags'] & 0x100 and no_stop(m, s['flags']) else 0
    per, last, peak, length = openings(m, cid, prog)
    links = FOLLOW_INPUTS.get(prog.get('follow'), [])
    for k in range(len(links)):                                # a follow-up's hits: the run with link k pressed throughout
        pk = openings(m, cid, prog, presses={f: 1 << k for f in range(300)})[0]
        for st, n_ in pk.items(): per[st] = max(per.get(st, 0), n_)
    objs = []
    for k, ob in enumerate(prog['objects']):
        rows, loop, follow = object_rows(m, cid, ob)
        end = []
        if ob.get('hit'):                                      # its hit routine: the end animation in place
            ho = Obj(m, cid, ob['hit']); ho.resume = 0
            for f in range(120):
                if f == 0: ho.frame(None)
                else: ho.tick(None)
                if ho.over or ho.steps is None: break
                end.append([add(ho.shown()), 0, 0])
        objs.append({'rows': [[add(r[0])] + r[1:] for r in rows], 'loop': loop, 'end': end, 'kind': ob['kind'] or 3,
                     'follow': follow, 'hit_kind': hitkind, 'react': 'knockdown', 'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0,
                     'child': None, 'state': ob.get('state')})
    return {'handler': h, 'button': b, 'ops': ops, 'states': states, 'anims': anims, 'openings': per, 'last_hit': last,
            'apex': peak, 'length': length, 'objects': objs, 'hit_kind': hitkind, 'links': links,
            **(dict(zip(('parts', 'follow_links'), follow_parts(m, cid, prog, links))) if links else {})}

# The victim's reaction to a hit, as KOF98 picks it (read 2026-10-05, our emulator + the ROM; KOF99 has the same code
# and the same reaction lists 0-79). The collision ($3A84) stores the attack box's id (+$90, the box's first byte) in the
# victim's +$AD; its hit routine ($1B4F4) picks a reaction index +$12F from a table by that id and the victim's
# situation +$12E (0-3 on the ground, 2 standing; 4-8 in the air, 6 = juggled in a launch): ids $18+ at
# T1 + (id - $18) * 36 + situation (+18 / +9 for counter hits and other flags, not taken here), ids under $18 at
# T0 + (id - $0C) * 72 + situation (the body box: +$AC = 1). Index -> handler $1BA3A[i] (the victim's states $B2ED2[i],
# its speeds $1BAE2[i]), grouped here by handler as the brawler's reactions (fighter.h R_*): 0-21 / 77-81 the reel
# (258-271, 280; speed 13.5 px x 0.828), 22-25 the sweep (276), 26-37 / 44-49 the blowback (283-286: vx 14, vy 7),
# 38-43 / 56-59 the launch (285 / 286 / 299: vx 2, vy 17.25), 50-53 the launch straight up (vx 0), 60-61 the slam
# down (303 / 304: vx 6, vy -10). Measured on Terry 214D (2 reels, ids $19 / $1F), 623A (5 launches, $28), 623B ($23
# blowback, then $30 slams the airborne victim down), 214C ($1B blowback), Robert 624D (reels $19 / $18), Ryo 623A
# ($27 launch), Yashiro 214D ($31 sweep), Yamazaki 623D ($35 reel 280).
REACT_TABLES = {'kof98': (0xB320C, 0xB356C, 0xB2ED2), 'kof99': (0xBBEB6, 0xBC216, 0xBBB62)}   # T0, T1, the states lists
R_HEAVY, R_KNOCKDOWN, R_LAUNCH, R_TRIP, R_SLAM, R_LIFT = 1, 2, 3, 4, 6, 7      # fighter.h R_*

def react_index(m, box, air):
    """KOF's reaction index (+$12F) for a hit by attack box id `box` on a standing (air False: situation 2) or juggled
    (air True: 6) victim; None: no table (KOF96) or an id outside it"""
    if m.game not in REACT_TABLES or not 0x0C <= box < 0x40: return None
    t0, t1, _ = REACT_TABLES[m.game]; e = 6 if air else 2
    return m.u8(t1 + (box - 0x18) * 36 + e) if box >= 0x18 else m.u8(t0 + (box - 0x0C) * 72 + e)

def react_class(rx):
    """a reaction index -> the brawler's reaction (R_*), by KOF's handler group"""
    if rx is None: return None
    if rx <= 21 or 77 <= rx <= 81: return R_HEAVY
    if rx <= 25: return R_TRIP
    if 38 <= rx <= 43 or 56 <= rx <= 59: return R_LAUNCH
    if 50 <= rx <= 53: return R_LIFT
    if rx in (60, 61): return R_SLAM
    return R_KNOCKDOWN

def react_hurt(m, cid, rx):
    """the victim keeps a hurt box in reaction rx (KOF's juggle rule: the reaction's first state, read on fighter cid,
    has the $0200 flag on its first step: 258-271 reels, 286 / 288 / 293; 276 sweep, 283 / 285 / 287 blowback and
    launch, 303 slam have none: nothing hits it until it is down)"""
    c2 = REACT_TABLES[m.game][2]; st = m.u16(c2 + m.u16(c2 + 2 * rx))
    return bool(anim_steps(m, cid, st)[0][0][2] & 0x200)

def box_react(m, box, cid):
    """the brawler's packed reaction for a hit by attack box `box`: standing | juggled << 4, each R_* | 8 when the
    victim stays hittable in it (react_hurt; 0 = no table)"""
    out = 0
    for k, air in ((0, False), (4, True)):
        rx = react_index(m, box, air)
        if rx is None: return 0
        out |= (react_class(rx) | (8 if react_hurt(m, cid, rx) else 0)) << k
    return out

CLEAN_CONDS = {None, 'end', 'event', 'land', 'falling', 'cnt', 'off', 'hit', 'owner_fxoff'}

def census(m):
    """every handler the move code installs (`move.l #h, $198(a4)` anywhere in P1), decoded with button C: how many
    decode with no unknown routine, condition, loop or state table, and what the rest need"""
    import collections
    p = m.p; hs = set()
    for a in range(0, 0x100000 - 8, 2):
        if p[a:a + 2] == b'\x29\x7c' and p[a + 6:a + 8] == b'\x01\x98':
            v = struct.unpack('>I', p[a + 2:a + 6])[0]
            if 0x30000 <= v < 0x100000: hs.add(v)
    dec = Decoder(m); issues = collections.Counter(); clean = 0
    for h in sorted(hs):
        found = set()
        def walk(d):
            for a, op in d['ops']:
                if op[0] in ('call', 'unknown', 'nudge?', 'nudgey?'): found.add(op[0] if op[0] != 'call' else f'call ${op[1] or 0:X}')
                if op[0] == 'anim' and op[1] is None: found.add('state table')
                if op[0] == 'br' and op[1] not in CLEAN_CONDS: found.add(f'cond {op[1]}')
                if op[0] == 'jmp' and op[1] != 'resume': found.add('loop')
            for ob in d['objects']: walk(ob)
            if d.get('hit'): walk(d['hit'])
        try: walk(decode(m, h, 'C', False, None, dec))
        except Exception as e: found.add('error')
        clean += not found
        issues.update({k.split(' ')[0] if k.startswith('call') else k for k in found})
    return len(hs), clean, issues

if __name__ == '__main__':
    if sys.argv[1] == '--census':
        m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98')
        n, clean, issues = census(m)
        print(f'{n} handlers, {clean} decode cleanly; the rest need: {issues.most_common()}'); sys.exit()
    cid, inp = int(sys.argv[1]), sys.argv[2]; ex = 'ex' in sys.argv[3:]
    m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98')
    h, b = handler_of(cid, inp, ex)
    print(f'{cid} {inp}: handler ${h:X} button {b}')
    d = decode(m, h, b, ex); show(d)
    rows, objs = run_model(m, cid, d)
    for r in rows: print(*r)
    for c in objs: print('object', c.prog['addr'], c.rows[:3], '...', len(c.rows))
