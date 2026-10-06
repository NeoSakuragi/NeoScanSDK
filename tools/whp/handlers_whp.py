#!/usr/bin/env python3
"""World Heroes Perfect's desperation moves (DMs) read from the ROM: the command and its condition, the animation steps,
the character's step hooks (68000 code), and a model that plays a DM from them, checked against the game frame by
frame in our emulator (the spirit of tools/kof96/handlers98.py and tools/kizuna/substates_kz.py: the move is the ROM's
logic; captures only check it). Labels: [code] read in the disassembly, [meas] measured in our emulator.

The command [code]
  A fighter's row = display object +$6004 - 1 (Dragon 0, Hanzou 1, ...: the select roster order, not the animation
  character: Hanzou's animations are character 0, base $180). Each frame the button scan ($2E25C) gathers the buttons
  pressed within 3 frames into +$6049 (A 1, B 2, C 4, D 8); the press handler ($34C32 / $38986) copies them to +$607E
  when +$607D is set: the life flag, set by the damage routine ($4D9CC) when the life byte +$600C drops below 97 (of
  192: under half). With +$607E set the command scan ($30DEA) looks the chord up in the row's list ($30E88: 4 chords per
  row, Hanzou A+C) and tries the row's DM commands ($2E80C facing right, $2E90C facing left; 8 indices into $2F40C).
  A command `FF [dir window]... FC a a a h h h` ($3109A): the input ring +$6200 is read backwards from the newest entry,
  each direction (U 1, D 2, L 4, R 8, 0 = neutral) found exactly within its window of entries; then the animation is
  a (+$100: relative) or, while the hero gauge is full (+$6A13), h.
  Hero gauge [code]: +$6A16 the target (hits add to it, $38B3E), +$6A18 the shown value counting up to it; at 223 the
  gauge is full: +$6A13 set ($2D190). Playing $120-$127 or the hero DMs ($12A / $12B) empties it ($38AA2 / $38B30); the
  plain DM ($128 / $129) does not.
Animation entries [code $15696 / $154F6]: +$60DC numbers every entry (a drawn step, $FFFD, a $FFFE loop, a $FFxx goto),
  and a goto does not end the list: the entries after it are reached by step number (the hit branch of $128 is 13..).
  Commands used here: 2 / 3 ($0101: x / y offsets from the def), 4 sound, 8 attack box set, 9 effect spawn (routine
  long[$59602 + 4k]), 13 pose by vertical speed, 23 on a hit go to step n of this animation (+$60E2 bit 7, +$60B2;
  checked first in the next frame's update, $1531A), 24 on landing go to (animation, step) (+$60E2 bit 0, $15296: the
  landing test $2E1EA), 28 / 29 / 30 / 31 vy / vx / ay / ax (+$0C / +$0E / +$10 / +$12, x ones negated facing left).
Step hooks [code]: after the animation update the character's hook routine runs ($35D3C: by +$6004; Hanzou $35FEA): per
  (animation, step) tests and actions, decoded by hook_paths() below (the victim = the other player, $3102A)."""
import os, re, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import whp

m = whp.m
PBIN = '/data/tmp/whp/p.bin'
ROWS = {'hanzo': 1}                               # +$6004 - 1 (the command / hook tables' row)
CHARS = {'hanzo': 0}                              # the animation character (whp.base)
BTN_TABLE, DM_CMDS, CMD_PTRS = 0x30E88, (0x2E80C, 0x2E90C), 0x2F40C
HOOK_DISPATCH = 0x35D3C                           # cmpib #k, +$6004 / beqw hook_k ...
LIFE_GATE_AT = 0x4D9CC                            # cmpib #97, +$600C: under it +$607D is set
FLOOR = 0x4800                                    # the floor's y word in the vs. state [meas] (fp+$4102 with the camera at rest)

def u8(a): return m.u8(a)
def u16(a): return m.u16(a)
def s16(a): return m.s16(a)
def u32(a): return m.u32(a)

# ---- the command ----------------------------------------------------------------------------------------------------
DIRS = {0: 'N', 1: 'U', 2: 'D', 4: 'L', 8: 'R', 0x0A: 'DR', 0x06: 'DL', 0x09: 'UR', 0x05: 'UL'}
def parse_command(i):
    """command i of $2F40C ($3109A): {'motion': [(dir, window entries)] oldest first, 'term': the byte after the motion
    (FC: a hero triple follows, FE: also needs +$604D clear, FF: plain; $310D8), 'anims': (a, a, a), 'hero': (h, h, h)
    or None}"""
    a = u32(CMD_PTRS + 4 * i); assert u8(a) == 0xFF, f'command {i}: not a motion ({u8(a):02X})'
    a += 1; mot = []
    while u8(a) < 0x80: mot.append((u8(a), u8(a + 1))); a += 2
    term = u8(a)
    assert term in (0xFC, 0xFE, 0xFF), f'command {i}: {term:02X} after the motion'
    rel = lambda v: 0x100 + v if v < 0x80 else v
    an = tuple(rel(u8(a + 1 + k)) for k in range(3))
    he = tuple(rel(u8(a + 4 + k)) for k in range(3)) if term == 0xFC else None
    return {'index': i, 'addr': u32(CMD_PTRS + 4 * i), 'motion': mot[::-1], 'term': term, 'anims': an, 'hero': he}

# the ground specials ($30CA2): the new presses +$6D (+$6001 bits 4-7: A 1, B 2, C 4, D 8, $30B38) pick a list per
# row: A / B / A+B ($30CE2: list $2E40C facing right / $2E50C left, 8 command indices per row) or C / D / C+D ($30D20:
# $2E60C / $2E70C); the anims triple is indexed by the press (A, B, A+B; C, D, C+D: $31126), the hero triple instead
# while the hero gauge is full (+$6A13, command byte FC: $310E4)
SPECIAL_LISTS = {'punch': ((0x2E40C, 0x2E50C), ('A', 'B', 'AB')), 'kick': ((0x2E60C, 0x2E70C), ('C', 'D', 'CD'))}
def special_commands(row):
    """the row's ground special commands facing right: [(list, command)] (parse_command; commands not of the motion form
    left out)"""
    out = []
    for name, ((right, _), _) in SPECIAL_LISTS.items():
        for k in range(8):
            i = u8(right + 8 * row + k)
            if not i: continue
            try: out.append((name, parse_command(i)))
            except AssertionError: pass
    return out

def dm_command(row):
    """the row's desperation command(s): chords (button masks), the commands facing right / left, the life gate"""
    chords = [b for b in (u8(BTN_TABLE + 4 * row + k) for k in range(4)) if b]
    right = [parse_command(i) for i in (u8(DM_CMDS[0] + 8 * row + k) for k in range(8)) if i]
    left = [parse_command(i) for i in (u8(DM_CMDS[1] + 8 * row + k) for k in range(8)) if i]
    assert u16(LIFE_GATE_AT) == 0x0C28 and u16(LIFE_GATE_AT + 4) == 0x600C, 'life gate moved'
    return {'chords': chords, 'right': right, 'left': left, 'life_below': u16(LIFE_GATE_AT + 2) & 0xFF, 'life_max': 0xC0}

def chord_name(b): return '+'.join(k for i, k in enumerate('ABCD') if b >> i & 1)
def notation(cmd, chord):
    """KOF-style numpad notation of a facing-right command (5 = the neutral entry the game requires)"""
    num = {'N': '5', 'U': '8', 'D': '2', 'L': '4', 'R': '6', 'DR': '3', 'DL': '1', 'UR': '9', 'UL': '7'}
    return ''.join(num[DIRS[d]] for d, _ in cmd['motion']) + chord_name(chord).replace('+', '')

# ---- animation entries -----------------------------------------------------------------------------------------------
def entries(char, rel, maxn=96):
    """every entry of an animation numbered as the engine numbers +$60DC: dict(n, addr, ctrl None / 'loop' / 'goto' /
    'end', defw, flags, cmds [(k, args hex)], ticks; loop: count, step; goto: anim (None = back to neutral), step).
    Goto entries do not end the list (later entries are reached by step number); 'end' ($FFFF) does."""
    a = whp.anim_addr(char, rel); out = []; last = None
    nxt = whp.anim_addr(char, rel + 1)
    for n in range(maxn):
        if a >= nxt > whp.anim_addr(char, rel): break
        st = a; w = u16(a); a += 2
        if w >= 0xFF00 and w != 0xFFFD:
            if w == 0xFFFF: out.append(dict(n=n, addr=st, ctrl='end')); break
            if w == 0xFFFE: out.append(dict(n=n, addr=st, ctrl='loop', count=u8(a), step=u8(a + 1))); a += 2; continue
            an, sp = u16(a), u16(a + 2); a += 4
            out.append(dict(n=n, addr=st, ctrl='goto', anim=None if an == 0xFFFF else an, step=sp)); continue
        d = last if w == 0xFFFD else w; last = d
        fl = u32(a); a += 4; cmds = []
        while True:
            c = s16(a); a += 2
            if c >= 0: ticks = c & 0xFF; break
            k = -c // 4; nb = whp.CMD_ARGS.get(k, 0)
            cmds.append((k, bytes(u8(a + i) for i in range(nb)).hex())); a += nb
        out.append(dict(n=n, addr=st, ctrl=None, defw=d, flags=fl, cmds=cmds, ticks=ticks))
    return out

# ---- the step hooks (68000 code) ---------------------------------------------------------------------------------------
_dis = {}
def dis(a, b):
    """{addr: (mnemonic, operands, next addr)} for [a, b) (objdump of the de-swapped P ROM, P1 half)"""
    if not os.path.exists(PBIN):
        os.makedirs(os.path.dirname(PBIN), exist_ok=True); open(PBIN, 'wb').write(m.p)
    if (a, b) in _dis: return _dis[(a, b)]
    out = subprocess.run(['m68k-linux-gnu-objdump', '-D', '-b', 'binary', '-m', 'm68k:68000', f'--start-address={a}',
                          f'--stop-address={b}', PBIN], capture_output=True, text=True).stdout
    ins, prev = {}, None
    for l in out.splitlines():
        mm = re.match(r'\s*([0-9a-f]+):\t[0-9a-f ]+\t(\S+)\s*(.*)', l)
        if not mm: continue
        ad = int(mm.group(1), 16); ins[ad] = [mm.group(2), mm.group(3).strip(), None]
        if prev is not None: ins[prev][2] = ad
        prev = ad
    _dis[(a, b)] = ins
    return ins

def hook_routine(row):
    """the row's step hook routine: the dispatcher's `cmpib #row+1, +$6004 / beqw R`"""
    ins = dis(HOOK_DISPATCH, HOOK_DISPATCH + 0x100)
    pc = HOOK_DISPATCH
    while pc in ins:
        mn, op, nx = ins[pc]
        if mn == 'cmpib' and op == f'#{row + 1},%a5@(24580)':
            mn2, op2, _ = ins[nx]; assert mn2 == 'beqw'
            return int(op2, 16)
        if mn == 'rts': break
        pc = nx
    raise KeyError(f'row {row}: no hook routine')

RTS_AT = 0x321C4                                  # a shared `rts` the hooks branch to
GOTO_STEP = 0x3878A                               # set animation +$66 (relative) at step +$6A ($15404)
def imm(s): v = int(s.lstrip('#'), 0); return v
BR = {'beq': lambda c: c == 0, 'bne': lambda c: c != 0, 'bcs': lambda c: c < 0, 'bcc': lambda c: c >= 0,
      'bls': lambda c: c <= 0, 'bhi': lambda c: c > 0}

def hook_paths(row, anim, step, facing=1):
    """the hook routine's paths for this animation (relative) and step, facing right (1) or left (-1): [(conds,
    actions)]. Concrete: the animation / step compares, the facing tests. Symbolic (both ways, a condition each):
    ('y>=', px) the height above the floor, ('x<=', bound, px) / ('x>=', bound, px) the x against the screen bounds
    fp+$4106 (left) / fp+$4104 (right), ('vanim<', n) the victim's animation (relative). Actions: ('at_victim',) x / y
    := the victim's, ('dy', px) / ('dx', px forward), ('floor',) y := the floor, ('flash', n) fp+$30B0 := n, ('goto',
    anim, step)."""
    start = hook_routine(row)
    ins = dis(start, start + 0x800)
    paths = []
    def walk(pc, conds, acts, regs, cmp_, n=0):
        while n < 400:
            n += 1
            if pc == RTS_AT or pc not in ins: paths.append((conds, acts)); return
            mn, op, nx = ins[pc]
            base = mn[:-1] if mn[-1] in 'ws' and mn[:-1] in BR or mn[:-1] in ('bra',) else mn
            if mn == 'rts': paths.append((conds, acts)); return
            if mn == 'movew' and op in ('%a5@(24794),%d7', '%a5@(24794),%d0'): regs[op[-2:]] = ('anim',)
            elif mn == 'subw' and op in ('%a5@(100),%d7', '%a5@(100),%d0', '%a0@(100),%d0'): pass
            elif mn == 'cmpiw' and op.endswith('%d7') or (mn == 'cmpiw' and op.endswith('%d0') and regs.get('d0') == ('anim',)):
                cmp_ = anim - imm(op.split(',')[0])
            elif mn == 'cmpib' and op.endswith('%a5@(24796)'): cmp_ = step - imm(op.split(',')[0])
            elif mn == 'movew' and op == '%a5@,%d6': regs['d6'] = ('y',)
            elif mn == 'subw' and op == '%fp@(16642),%d6': regs['d6'] = ('dy',)
            elif mn == 'movew' and op == '%a5@,%d0': regs['d0'] = ('y',)
            elif mn == 'subw' and op == '%fp@(16642),%d0': regs['d0'] = ('dy',)
            elif mn == 'cmpiw' and (op.endswith('%d6') and regs.get('d6') == ('dy',) or op.endswith('%d0') and regs.get('d0') == ('dy',)):
                cmp_ = ('dy', imm(op.split(',')[0]) / 128)
            elif mn == 'movew' and op == '%a5@(2),%d1': regs['d1'] = ('x',)
            elif mn == 'movew' and op in ('%fp@(16644),%d2', '%fp@(16646),%d2'):
                regs['d2'] = ('left' if '16644' in op else 'right', 0)   # fp+$4104 / $4106: the x range ($5400 / $CC00)
            elif mn in ('addiw', 'subiw') and op.endswith('%d2') and isinstance(regs.get('d2'), tuple):
                v = imm(op.split(',')[0]) * (1 if mn == 'addiw' else -1)
                regs['d2'] = (regs['d2'][0], regs['d2'][1] + v / 128)
            elif mn == 'cmpw' and op == '%d2,%d1': cmp_ = ('x', regs['d2'])
            elif mn == 'jsr' and op == '0x3102a': regs['a0'] = 'victim'
            elif mn == 'movew' and op == '%a0@(24794),%d0': regs['d0'] = ('vanim',)
            elif mn == 'cmpiw' and op.endswith('%d0') and regs.get('d0') == ('vanim',): cmp_ = ('vanim', imm(op.split(',')[0]))
            elif mn == 'btst' and op == '#7,%a5@(33)': cmp_ = 0 if facing > 0 else 1   # Z set when the flip bit is clear
            elif mn == 'movel' and op == '%a0@,%a5@': acts = acts + [('at_victim',)]
            elif mn == 'movew' and re.match(r'#-?\d+,%d[01]$', op): regs[op[-2:]] = imm(op.split(',')[0])
            elif mn == 'negw' and op in ('%d0', '%d1'): regs[op[1:]] = -regs[op[1:]]
            elif mn == 'addw' and op == '%d0,%a5@': acts = acts + [('dy', regs['d0'] / 128)]
            elif mn == 'addw' and op in ('%d1,%a5@(2)', '%d0,%a5@(2)'): acts = acts + [('dx', facing * regs[op[1:3]] / 128)]
            elif mn == 'movew' and op == '%fp@(16642),%a5@': acts = acts + [('floor',)]
            elif mn == 'moveb' and op.endswith(',%fp@(12464)'): acts = acts + [('flash', imm(op.split(',')[0]))]
            elif mn == 'movew' and op in ('%d0,%a5@(102)', '%d7,%a5@(102)'): regs['goto_anim'] = anim
            elif mn == 'moveb' and op.endswith(',%a5@(106)'): regs['goto_step'] = imm(op.split(',')[0])
            elif mn in ('jmp', 'braw', 'bras') and op == hex(GOTO_STEP):
                paths.append((conds, acts + [('goto', regs.get('goto_anim', anim), regs.get('goto_step', 0))])); return
            elif mn in ('bras', 'braw'): pc = int(op, 16); continue
            elif mn[:-1] in BR or mn[:-1] in ('bls', 'bhi'):
                kind = mn[:-1]; tgt = int(op, 16)
                if isinstance(cmp_, int):
                    if BR[kind](cmp_): pc = tgt; continue
                elif isinstance(cmp_, tuple):
                    what = cmp_[0]
                    if what == 'dy':                          # unsigned y - floor vs the immediate: bcs = below it
                        lo, hi = ('y<', cmp_[1]), ('y>=', cmp_[1])
                        yes, no = (lo, hi) if kind == 'bcs' else (hi, lo) if kind == 'bcc' else (None, None)
                    elif what == 'x':                          # cmpw d2,d1: x vs the bound
                        b = cmp_[1]
                        if kind == 'bls': yes, no = ('x<=', b[0], b[1]), ('x>', b[0], b[1])
                        elif kind == 'bcc': yes, no = ('x>=', b[0], b[1]), ('x<', b[0], b[1])
                        else: yes = no = None
                    elif what == 'vanim':
                        yes, no = (('vanim<', cmp_[1]), ('vanim>=', cmp_[1])) if kind == 'bcs' else \
                                  (('vanim>=', cmp_[1]), ('vanim<', cmp_[1])) if kind == 'bcc' else (None, None)
                    if yes is None: raise ValueError(f'{pc:X}: {mn} on {cmp_}')
                    walk(tgt, conds + [yes], list(acts), dict(regs), cmp_, n)
                    conds = conds + [no]
                else: raise ValueError(f'{pc:X}: {mn} without a compare')
            elif mn == 'moveq' and op == '#0,%d0': regs['d0'] = 0
            elif mn in ('jmp',): raise ValueError(f'{pc:X}: jmp {op}')
            else: acts = acts + [('?', pc, mn, op)]
            pc = nx
        raise RuntimeError('hook walk too long')
    walk(start, [], [], {}, None)
    return [(c, a) for c, a in paths if a or c]

def hook_table(row, anims, maxstep=64):
    """{(anim, step): [(conds, actions)]} for the steps where the hook does something"""
    out = {}
    for a in anims:
        for s in range(maxstep):
            p = [(c, ac) for c, ac in hook_paths(row, a, s) if ac]
            if p: out[(a, s)] = p
    return out

# ---- the model ---------------------------------------------------------------------------------------------------------
def held(cond, st):
    """a hook condition against the model's state (x px from the screen bounds: st['edge_after'] frames of the jump)"""
    k = cond[0]
    if k == 'y>=': return st['y'] >= cond[1]
    if k == 'y<': return st['y'] < cond[1]
    if k in ('x<=', 'x>', 'x>=', 'x<'):              # WHP: the jump back reaches a screen bound (fp+$4104 / $4106); the
        near = st['air'] >= st['edge_after']          # model: after edge_after frames of flight (no fixed screen in a brawl)
        if cond[1] == 'left': return near if k == 'x<=' else not near     # facing right he jumps back to the left bound
        return k == 'x<'                              # the right bound: never reached
    if k == 'vanim<': return st['vanim'] < cond[1]
    if k == 'vanim>=': return st['vanim'] >= cond[1]
    raise ValueError(cond)

def play(name, rel, victim=(0.0, 0.0), hit_frames=(), edge_after=8, vanim=0xFF, maxf=400, xmin=None, stop_frames=(), first_ticks=False):
    """the DM played by the model, facing right, from x 0 on the floor: per frame dict(anim, step, defw, x, y (px, up),
    live (attack box set or None), spawns [effect k], flash). victim = its (x, y) px or a function of the model's frame
    (the hooks place Hanzou from it); hit_frames = the frames whose attack box connects (the caller's contact; the
    model's own frame numbers: the game shows the contact frame, moves on one more update, then the hit-stop, which the
    model leaves out; the update after it takes the landing branch first, the hit branch ($1531A) next); vanim =
    the victim's animation (relative) when the hit check runs (WHP: $30-$3F = a guard: the dive bounces off).
    Engine rules [code, meas]: a step shows ticks + 1 frames; each frame: the pending landing / hit branch ($151FE),
    else the step timer; the hooks; then the motion y += vy + ay / 2, vy += ay (x likewise; [meas]: the first frame of
    a jump rises vy + ay / 2); a landing (vy < 0 and y + vy + ay at or below the floor, $2E1EA) is taken in the next
    frame's update. stop_frames = the frames whose contact drops the victim's life (the game's damage, $4C17C): when
    the attacker stands still there (+$0C / +$10 longs: no velocity, no acceleration) the step's tick counter is cleared
    (clrb +$60E0, $4C188): the step ends with the hit-stop (the hero rising's uppercut, step 2). first_ticks: the move
    starts before the frame's animation update runs, its first step shows ticks frames [meas: the 623 commands, $104 /
    $105 / $120-$122; the DM, 236 and 214 show ticks + 1]. x moves x += vx, vx += ax ($9C46: no half step, [meas] on
    the hero rising's ax); y keeps the measured vy + ay / 2."""
    char = CHARS[name]; row = ROWS[name]
    st = dict(anim=rel, step=-1, left=0, x=0.0, y=0.0, vx=0.0, vy=0.0, ax=0.0, ay=0.0, land=None, onhit=None, loops={},
              air=0, edge_after=edge_after, vanim=vanim, defw=None, box=None, live=False, hit=False, hit_seen=False)
    ents = {rel: entries(char, rel)}
    out = []
    def enter(anim, step):
        """$15404 / $15696: set (anim, step), then run entries from it until a drawn step"""
        st['anim'] = anim
        if anim not in ents: ents[anim] = entries(char, anim)
        st['step'] = step; st['land'] = None; st['onhit'] = None; st['loops'] = {}
        run_entries()
    def run_entries():
        spawns = []
        for _ in range(64):
            E = ents[st['anim']]
            if st['step'] >= len(E): st['over'] = True; return spawns
            e = E[st['step']]
            if e['ctrl'] == 'loop':
                k = e['n']
                if e['count'] == 0: st['step'] = e['step']; continue
                c = st['loops'].get(k)
                if c is None: st['loops'][k] = e['count']; st['step'] = e['step']; continue
                c -= 1
                if c > 0: st['loops'][k] = c; st['step'] = e['step']; continue
                del st['loops'][k]; st['step'] += 1; continue
            if e['ctrl'] == 'goto':
                if e['anim'] is None: st['over'] = True; return spawns
                st['anim'] = e['anim']
                if e['anim'] not in ents: ents[e['anim']] = entries(char, e['anim'])
                st['step'] = e['step']; st['land'] = st['onhit'] = None; st['loops'] = {}; continue
            if e['ctrl'] == 'end': st['over'] = True; return spawns
            st['defw'] = e['defw']; st['left'] = e['ticks'] + 1; st['live'] = bool(e['flags'] & 0x800)
            for k, args in e['cmds']:
                v = int(args, 16) if args else 0
                sv = v - 0x10000 if v >= 0x8000 and len(args) == 4 else v
                if k in (2, 3):                       # velocities / accelerations from tables ($15E6C / $15F40):
                    a_, b_ = int(args[:2], 16), int(args[2:], 16)   # index 0 keeps the field, 1 = 0
                    ty, tx = (0x5D504, 0x5D508) if k == 2 else (0x5D50C, 0x5D510)
                    if a_: st['vy' if k == 2 else 'ay'] = s16(u32(ty) + 2 * a_) / 128
                    if b_: st['vx' if k == 2 else 'ax'] = s16(u32(tx) + 2 * b_) / 128
                elif k == 8: st['box'] = v
                elif k == 9: spawns.append(v)
                elif k == 28: st['vy'] = sv / 128
                elif k == 29: st['vx'] = sv / 128
                elif k == 30: st['ay'] = sv / 128
                elif k == 31: st['ax'] = sv / 128
                elif k == 24: st['land'] = (v >> 16, v & 0xFF)
                elif k == 23: st['onhit'] = v
            st['pending_spawns'] = st.get('pending_spawns', []) + spawns
            return spawns
        raise RuntimeError('entry loop')
    st['over'] = False
    enter(rel, 0)
    if first_ticks: st['left'] -= 1                  # entered before the frame's animation update [meas]
    landed_next = False
    for f in range(maxf):
        if f > 0:
            if landed_next and st['land']:                 # the landing branch ($15296)
                a, s = st['land']; st['y'] = 0.0; st['vx'] = st['vy'] = st['ax'] = st['ay'] = 0.0
                enter(a, s)
            elif st['hit'] and st['onhit'] is not None:    # the hit branch ($1531A)
                enter(st['anim'], st['onhit']); st['hit'] = False
            st['left'] -= 1                                # the step timer runs in the same frame (a branch's step
            if st['left'] <= 0:                            # shows ticks frames [code $151FE returns Z: d0 popped 0])
                st['step'] += 1; run_entries()
            if st['hit_seen']: st['hit'] = True; st['hit_seen'] = False   # the damage routine runs after this
            if st['over']: break                           # update: the flag (+$6033) is read one update later
        landed_next = False
        flash = 0
        for conds, acts in hook_table_cached(row, st['anim']).get((st['anim'], st['step']), []):
            if not all(held(c, st) for c in conds): continue
            for a in acts:
                if a[0] == 'at_victim': st['x'], st['y'] = victim(f) if callable(victim) else victim
                elif a[0] == 'dy': st['y'] += a[1]
                elif a[0] == 'dx': st['x'] += a[1]
                elif a[0] == 'floor': st['y'] = 0.0
                elif a[0] == 'flash': flash = a[1]
                elif a[0] == 'goto': enter(a[1], a[2])
            break
        # the motion
        st['y'] += st['vy'] + st['ay'] / 2; st['vy'] += st['ay']
        st['x'] += st['vx']; st['vx'] += st['ax']        # x: the motion routine's own order ($9C46) [code + meas]
        if xmin is not None and st['x'] < xmin: st['x'] = xmin; st['air'] = max(st['air'], edge_after)   # WHP's bound
        if st['y'] > 0 or st['vy'] > 0: st['air'] += 1
        if st['land'] and st['vy'] < 0 and st['y'] + st['vy'] + st['ay'] <= 0: landed_next = True   # $2E1FA: y + vy + ay
        sp = st.pop('pending_spawns', [])
        out.append(dict(f=f, anim=st['anim'], step=st['step'], defw=st['defw'], x=st['x'], y=st['y'],
                        live=st['box'] if st['live'] else None, spawns=sp, flash=flash))
        if f in hit_frames: st['hit_seen'] = True
        if f in stop_frames and not (st['vx'] or st['vy'] or st['ax'] or st['ay']): st['left'] = 1   # $4C188
    return out

_hooks = {}
def hook_table_cached(row, anim):
    if (row, anim) not in _hooks: _hooks[(row, anim)] = hook_table(row, [anim])
    return _hooks[(row, anim)]

# ---- captures (the check only) ------------------------------------------------------------------------------------------
DM_SEQ = '2:-,3:R,2:-,3:L,3:D,3:Rac,'             # 6 5 4 2 6 + A+C (the motion, then the chord with the last direction)
SR_SEQ = '2:-,3:R,3:D,3:DRab,3:ab,'               # 6 2 3 + A+B (capture_whp.m): the hero gauge full -> $122
# recipe: (P1's inputs, P2's inputs, hero gauge full[, P2 pinned at x px, for n frames])
RECIPES = {'dm_hit': (DM_SEQ + '300:-', '', False), 'dm_whiff': (DM_SEQ + '200:-', '2:-,40:R', False),
           'dmh_hit': (DM_SEQ + '400:-', '', True), 'dmh_whiff': (DM_SEQ + '200:-', '2:-,40:R', True),
           'sr_hit': (SR_SEQ + '400:-', '', True, 240, 14), 'sr_whiff': (SR_SEQ + '200:-', '', True)}
# the move each recipe plays (relative animation) and the animations that belong to it (its landing)
REL = {'dm': 0x128, 'dmh': 0x12A, 'sr': 0x122}
MOVE_ANIMS = {'dm': (0x128, 0x129, 0x1B, 0x19), 'dmh': (0x12A, 0x12B, 0x1B, 0x19), 'sr': (0x122, 0x18)}
def rec_move(rec): return rec.rsplit('_', 1)[0]
# the reference geometry: the vs. state's round-start places. Hit: P2 stands at 376, Hanzou's jump back reaches the
# screen bound (fp+$4104 + 10 px) after 8 frames of flight [meas]; whiff: P2 walks away first, Hanzou starts pinned at
# the bound (x -10.5 px from his start: the hang comes at the first frame 48 px up). The hero rising ($122) runs no
# hooks: no geometry (hit: P2 pinned 57 px in front for the motion's frames; whiff: P2 stays at 376).
GEOMETRY = {'dm_hit': dict(edge_after=8), 'dm_whiff': dict(edge_after=99, xmin=-10.5),
            'dmh_hit': dict(edge_after=8), 'dmh_whiff': dict(edge_after=99, xmin=-10.5), 'sr_hit': dict(first_ticks=True), 'sr_whiff': dict(first_ticks=True)}
FX_TASKS = {0x5A: 'kanji', 0x5D: 'smoke', 0x7A: 'clone', 0x71: 'clone (hero)', 0x77: 'sparkle'}   # the DM's own effects (task +$2E) [meas]: $7A = $8F's mirrored clone of the last dash, $71 = $86's second Hanzou diving from above (hero DM)
SR_FX_TASKS = {0x20: 'dragon'}                    # the hero rising's own effect [meas] (command 9 $13 at step 2: task $20,
                                                  # $C070 the flash at the fist, then the ice dragon around Hanzou $C060-$C06C,
                                                  # drawn every other frame: the frames between it is parked off screen)
def fx_tasks(rec): return SR_FX_TASKS if rec_move(rec) == 'sr' else FX_TASKS
def pokes(rec):
    """the recipe's RAM pokes (emu POKE): P1's life under the gate, the hero gauge full, P2 pinned"""
    seq, seq2, hero, *p2x = RECIPES[rec]
    pf = {f: '10600C=50,10607D=FF' + (',106A13=FF,106A16=00,106A17=DF,106A18=00,106A19=DF' if hero else '') for f in range(4)}
    if p2x and p2x[0]:                                # P2 pinned at x p2x[0] px for p2x[1] frames (capture_whp's way)
        for f in range(p2x[1]):
            pf[f] = (pf[f] + ',' if f in pf else '') + f'100102={p2x[0] * 128 >> 8 & 255:02X},100103={p2x[0] * 128 & 255:02X}'
    return ';'.join(f'{f}:{v}' for f, v in sorted(pf.items()))

def capture(rec, keep=None, vram=False):
    """a DM in our emulator from the vs. state (cap_whp.VS: Hanzou P1 at x 200 facing right, Fuuma P2 at 376), P1's life
    under the gate (+$600C := 80, +$607D := $FF; hero: the gauge full, +$6A13 / +$6A16 / +$6A18) -> per frame dict(p1,
    p2: anim (relative), step, def, x / y words, flip, live, box, life; floor (fp+$4102), camx (word fp+$21A: the scroll
    [meas]; fp+$232 jumps during the DM), fx: the effect pool ($100400 + $80 k: task +$2E, def, x, y, flip), flash
    (fp+$30B0), freeze (fp+$4141: the hero DM's freeze), backdrop (palette $1FFE), vram)"""
    import cap_whp as cap, glob, shutil, tempfile
    seq, seq2 = RECIPES[rec][:2]
    n = max(cap.nframes(seq), cap.nframes(seq2) if seq2 else 0)
    d = keep or tempfile.mkdtemp(dir='/data/tmp'); os.makedirs(d, exist_ok=True)
    for f in glob.glob(f'{d}/cap.txt*') + glob.glob(f'{d}/vram*.bin'): os.remove(f)
    pk = pokes(rec)
    rd = ';'.join(f'{f}:100000:3000;{f}:106000:3000;{f}:1030B0:2;{f}:108200:40;{f}:10C100:48' for f in range(1, n))
    env = dict(os.environ, SEQ=seq, SEQ2=seq2, OUT=f'{d}/cap.txt', LOAD=cap.VS, RAMDUMP=rd, POKE=pk,
               PALDUMP=','.join(str(f) for f in range(1, n)))
    if vram: env['VRAMDUMP'] = ';'.join(f'{f}:{d}/vram{f}.bin' for f in range(1, n))
    subprocess.run([cap.NGSDL, cap.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    rd_ = lambda f, a: cap.parse(open(f'{d}/cap.txt.ram{f}_{a}').read())
    U, S = cap.u16, cap.s16
    rows = []
    for f in range(1, n):
        try: o, a, g, c, fl = rd_(f, '100000'), rd_(f, '106000'), rd_(f, '108200'), rd_(f, '10C100'), rd_(f, '1030B0')
        except FileNotFoundError: continue
        pal = open(f'{d}/cap.txt.pal{f}', 'rb').read() if os.path.exists(f'{d}/cap.txt.pal{f}') else b''
        def fighter(k):
            b = k * 0x100
            return dict(anim=U(a, b + 0xDA) - U(o, b + 0x64), step=a[b + 0xDC], defw=U(o, b + 8), x=U(o, b + 2), y=U(o, b),
                        flip=o[b + 0x21] >> 7, live=a[b + 0xD6] >> 3 & 1, box=U(a, b + 0xF8), life=a[b + 0x0C], tick=U(a, b + 0xE0),
                        pal=o[b + 0x20], add=U(o, b + 0x2C), flags=o[b + 0x21], offs=(S(o, b + 0x14), S(o, b + 0x16)))
        fx = []
        for b in range(0x400, 0x3000, 0x80):
            if not o[b + 0x28] or not U(o, b + 8): continue
            fx.append(dict(slot=b, task=U(o, b + 0x2E), defw=U(o, b + 8), x=U(o, b + 2), y=U(o, b), flip=o[b + 0x21] >> 7,
                           flags=o[b + 0x21], add=U(o, b + 0x2C), pal=o[b + 0x20], offs=(S(o, b + 0x14), S(o, b + 0x16))))
        rows.append(dict(f=f, p1=fighter(0), p2=fighter(1), floor=U(c, 2), camx=S(g, 0x1A), fx=fx, flash=U(fl, 0), freeze=c[0x41],
                         backdrop=U(pal, 0x1FFE) if len(pal) >= 0x2000 else None, vram=f'{d}/vram{f}.bin' if vram else None))
    if not keep: shutil.rmtree(d)
    return rows

def reference(rec, rows=None):
    """a capture as the model's frames: from the DM's first frame, WHP's freezes left out (the hit-stop: a frame after a
    life drop where Hanzou did not change; the hero DM's freeze fp+$4141) -> dict(frames [dict(p1 [anim, step, def, x,
    y], p2 [x, y] (px from Hanzou's start, y up), life, fx [[task, def, x, y, flip]], backdrop)], hits [frame indices
    whose contact drops P2's life: the frame before the drop], rel)"""
    rows = rows if rows is not None else capture(rec)
    rel0 = REL[rec_move(rec)]; own = MOVE_ANIMS[rec_move(rec)]; tasks = fx_tasks(rec)
    s0 = next(i for i, r in enumerate(rows) if r['p1']['anim'] == rel0)
    x0, _ = world(rows[s0])
    keep, drops = [], []
    for i in range(s0, len(rows)):
        r = rows[i]; p = r['p1']
        if p['anim'] not in own: break
        if r.get('freeze'): continue
        if i > s0:
            q = rows[i - 1]['p1']
            if r['p2']['life'] < rows[i - 1]['p2']['life']: drops.append(len(keep))
            if (p['anim'], p['step'], p['defw'], world(r)) == (q['anim'], q['step'], q['defw'], world(rows[i - 1])) and \
               drops and len(keep) - drops[-1] < 3: continue
        keep.append(i)
    out = []
    for i in keep:
        r = rows[i]; p = r['p1']; x, y = world(r); vx, vy = world(r, 'p2')
        out.append(dict(f=r['f'], p1=[p['anim'], p['step'], p['defw'], round(x - x0, 3), round(y, 3)],
                        p2=[round(vx - x0, 3), round(vy, 3)], life=r['p2']['life'], backdrop=r['backdrop'],
                        fx=[[o['task'], o['defw'], round(o['x'] / 128 + r['camx'] - x0, 3), round((o['y'] - r['floor']) / 128, 3), o['flip']]
                            for o in r['fx'] if o['task'] in tasks]))
    return {'rel': rel0, 'frames': out, 'hits': [d - 1 for d in drops]}

def check(ref, rec):
    """the model against a reference: (frames compared, mismatches [(k, capture, model)]); the hit at the reference's
    first contact, the victim where the reference had it, the geometry of the recipe"""
    fr = ref['frames']
    vic = lambda k: tuple(fr[min(k, len(fr) - 1)]['p2'])
    mod = play('hanzo', ref['rel'], victim=vic, hit_frames=set(ref['hits'][:1]), stop_frames={h + 1 for h in ref['hits']},
               **GEOMETRY[rec])
    bad = []
    for k in range(max(len(mod), len(fr))):
        a = mod[k] if k < len(mod) else None; c = fr[k]['p1'] if k < len(fr) else None
        ok = a and c and [a['anim'], a['step'], a['defw']] == c[:3] and abs(a['x'] - c[3]) < 1.01 and abs(a['y'] - c[4]) < 1.01
        if not ok: bad.append((k, c, a and [a['anim'], a['step'], a['defw'], round(a['x'], 1), round(a['y'], 1)]))
    return max(len(mod), len(fr)), bad

REF = '/data/neogeo_dict/whp/hanzo_dm_capture.json'

def world(r, who='p1'):
    """(x, y) px of a fighter in the stage: x = word / 128 + the scroll, y = (word - floor) / 128 (the camera moves the
    floor's y word too)"""
    p = r[who]; return p['x'] / 128 + r['camx'], (p['y'] - r['floor']) / 128

if __name__ == '__main__':
    if '--capture' in sys.argv or '--check' in sys.argv:
        import json
        if '--capture' in sys.argv:
            refs = {rec: reference(rec) for rec in RECIPES}
            json.dump(refs, open(REF, 'w')); print('wrote', REF)
        refs = json.load(open(REF))
        for rec, ref in refs.items():
            n, bad = check(ref, rec)
            print(f"{rec}: model vs WHP {n - len(bad)} / {n} frames identical (anim, step, def, x, y within 1 px); hits at {ref['hits']}",
                  bad[:3] if bad else '')
        sys.exit(0)
    name = 'hanzo'; row = ROWS[name]
    c = dm_command(row)
    print('DM chords', [chord_name(b) for b in c['chords']], f"life below {c['life_below']} of {c['life_max']}")
    for cm in c['right']:
        print(f"  command {cm['index']} @{cm['addr']:X}: motion {[(DIRS[d], w) for d, w in cm['motion']]} anims "
              f"{[hex(a) for a in cm['anims']]} hero {[hex(a) for a in cm['hero']]}  = {notation(cm, c['chords'][0])}")
    print('ground specials (facing right; a triple per press, the hero triple with the gauge full):')
    for lst, cm in special_commands(row):
        presses = SPECIAL_LISTS[lst][1]
        print(f"  {lst} command {cm['index']} @{cm['addr']:X} {cm['term']:02X}: motion {[(DIRS[d], w) for d, w in cm['motion']]} "
              f"{dict(zip(presses, map(hex, cm['anims'])))} hero {dict(zip(presses, map(hex, cm['hero']))) if cm['hero'] else None}")
    print(f'hook routine {hook_routine(row):X}')
    for a in sorted({x for cm in c['right'] for x in cm['anims'] + cm['hero']} | {0x129, 0x12B}):
        for (an, s), p in sorted(hook_table(row, [a]).items()):
            for conds, acts in p: print(f'  {an:X} step {s}: if {conds} -> {acts}')
