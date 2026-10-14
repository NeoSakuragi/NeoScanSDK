#!/usr/bin/env python3
"""Final Fight's special (attack + jump) as a brawler program (bprim_t, fighter.c prog_update), the op model of
tools/lastbld2/handlers_lb2.py: one program state per run of frames with one motion.

[meas] rec_ff.py 'special' (16.16 heights of P1 in FF): frame 1 on the ground, then Guy / Cody hop (vy0 6 / 7 px,
gravity 0.33203125 = $5500, applied before the move: the first air frame rises vy0 - g) back to the floor, then FF's
landing crouch (the jump's: 6 + 1 frames); Haggar's lariat stays on the ground for its whole animation. No travel.
States: 0 = the first frame, 1 = the animation's rest (the hop), 2 = the landing.

    python3 handlers_ff.py [NAME ...]   the programs played by the brawler's own player (handlers_ss2.Play, a port of
                                        fighter.c prog_update) vs FF's measured heights (rec_ff 'special')"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'samsho2'))
import handlers_ss2 as HS

SPECIAL = {'guy': 0xFF86, 'cody': 0x11EBE, 'haggar': 0x13600}
SPECIAL_ARC = {'guy': (6.0, 0.33203125), 'cody': (7.0, 0.33203125), 'haggar': None}

def assemble(ops):
    lab, out = {}, []
    for o in ops:
        if o[0] == 'label': lab[o[1]] = len(out)
        else: out.append(o)
    res = []
    for o in out:
        if o[0] == 'br': res.append(('br', o[1], o[2], -1 if o[3] == 'yield' else lab[o[3]]))
        elif o[0] in ('jmp', 'resume_at'): res.append((o[0], lab[o[1]]))
        else: res.append(o)
    return res

def encode(o):
    P, REG, PC = HS.P, HS.REG, HS.PC; n = o[0]
    if n == 'anim': return [P['anim'], o[1], 0, 0]
    if n in ('set', 'add'): return [P[n], REG[o[1]], 0, o[2]]
    if n == 'br': return [P['br'], PC[o[1]] | (0x80 if o[2] else 0), o[3], 0]
    if n in ('jmp', 'resume_at'): return [P[n], 0, o[1], 0]
    if n == 'fall': return [P['fall'], 1, 0, 0]
    return [P[n], 0, 0, 0]

def frames_of(X, spec):
    """an animation as video frames: [(entry, frame addr)], each entry its t frames"""
    ents, _ = X.entries(spec)
    return [(e, fa) for e, fa, t, at in ents for _ in range(t)]

def collapse(X, B, name, rows, one_hit=True):
    steps = []
    for e, fa in rows:
        if steps and steps[-1]['ff'][0] == e: steps[-1]['ticks'] += 1; continue
        bx = X.kof_boxes(fa, name)
        steps.append({'frame': B.frame(fa), 'ticks': 0, 'flags': 0x100 if '11' in bx else 0, 'dx': 0, 'boxes': bx, 'ff': [e, fa]})
    for i, s in enumerate(steps):                   # FF hits once per move: consecutive attack steps = one hit
        if one_hit and s['flags'] & 0x100 and i + 1 < len(steps) and steps[i + 1]['flags'] & 0x100: s['flags'] |= 0x4000
    return steps

# FURY PIECES (note 20261014-171937-5d29, Bruno: "a completely new fury for Haggar, Final Fight has none: jab, jab,
# finisher, x3, then the special; nothing launches but the very last hit of the special, which does seven or eight
# hits"): his own animations as ground programs of their own, played back to back by game.json roster[].fury = the list
# (export_bm sequences, fighter.c seq_next). input -> (animation, frames kept (None: the whole), damage a hit, reaction
# of the last hit (the others a reel), each attack step a hit of its own). Cuts = FF's chain cadence [meas rec_ff
# haggar chain]: a jab link starts 2 frames after the hit entry's first (entries 0-1 = 8 frames, then the hit: 10), the
# finisher keeps its hit entry whole (entries 0-1 = 10 frames + 5). The spin: $13600's 8 attack steps, one hit each
# (FF's lariat hits once: rec_ff special_hit, $00 on its hit), the last a knockdown. Damage: jab 1 x 6 + finisher 3 x 3
# + spin 1 x 8 + the closing piledriver 7 (roster[].fury_throw) = 30 (game.json tiers.fury)
PIECES = {'haggar': {'P.JAB': (0x1397C, 10, 1, 'reel', False), 'P.FIN': (0x13A94, 15, 3, 'reel', False),
                     'P.AJ8': (0x13600, None, 1, 'reel', True)}}   # (the reopen: the spin's 8 hits all reel, 1 each;
                                                                    # the piledriver closes: game.json roster[].fury_throw)

def pieces(X, B, name):
    out = []
    for inp, (anim, keep, dmg, last, multi) in (PIECES.get(name) or {}).items():
        sp = special(X, B, name, anim=anim, keep=keep, multi=multi, dmg=dmg,
                     react=HS.R_KNOCKDOWN if last == 'knockdown' else HS.R_HEAVY, piece=True)
        sp.update(input=inp, base_input=inp, condition='piece', name=f'Fury piece {inp} (${anim:X})')
        out.append(sp)
    return out

def special(X, B, name, anim=None, keep=None, multi=False, dmg=None, react=None, piece=False):
    import export_ss2 as XS
    anim = anim or SPECIAL[name]
    rows = frames_of(X, anim); arc = SPECIAL_ARC[name] if anim == SPECIAL[name] else None
    ents = X.entries(anim)[0]
    if ents[-1][3] == 0xFF:                         # the end entry ($FF): the move ends on its first frame [meas]
        rows = rows[:len(rows) - ents[-1][2] + 1]
    if keep: rows = rows[:keep]
    react = HS.R_KNOCKDOWN if react is None else react
    if arc:                                         # the hop: its air frames (y > 0) as FF's 16.16 arc gives them, then
        vy, g, y, air = arc[0], arc[1], 0.0, 0      # the landing crouch (the jump's: 6 + 1 frames) on the floor
        while True:
            vy -= g; y += vy
            if int(y) <= 0: break                       # (FF lands when the whole pixels reach the floor)
            air += 1
        land = frames_of(X, X.MOVES[name]['land'])
        land = land + [(-1, land[-1][1])]
        segs = [rows[:1], rows[1:1 + air], land]
    else: segs = [rows[:1], rows[1:]]
    states, anims_d, ops = [], {}, []
    for i, sg in enumerate(segs):
        steps = collapse(X, B, name, sg, one_hit=not multi)
        steps[0]['ticks'] += 1                      # the brawler's clock: P_ANIM shows step 0 once more (handlers_lb2)
        if steps[-1]['ticks']: steps[-1]['ticks'] -= 1
        k = f'{i}:{anim:x}'; states.append(k); anims_d[k] = {'mode': 'hold', 'steps': steps}
        air = bool(arc) and i == 1
        ops += [('label', ('E', i)), ('anim', i), ('set', 'vx', 0), ('set', 'cnt', len(sg) - 1)]
        if arc and i == 2: ops.append(('set', 'h', 0))
        if air: ops += [('set', 'vy', round((arc[0] - arc[1]) * 65536)), ('set', 'g', round(arc[1] * 65536))]
        ops += [('resume',), ('move',)] + ([('fall',)] if air else []) + [
            ('dec',), ('br', 'cnt', 1, ('S', i)), ('br', 'always', 1, 'yield'),
            ('label', ('S', i)), ('resume_at', ('E', i + 1)), ('br', 'always', 1, 'yield')]
    ops += [('label', ('E', len(segs))), ('label', 'END'), ('end',)]
    prims = [encode(o) for o in assemble(ops)]
    nh = sum(sum(HS.openings(anims_d[s]['steps'])) for s in states)
    for p in prims:
        if p[0] == HS.P['anim']: p[2] = (dmg or max(1, HS.SPECIAL_DAMAGE // max(1, nh))) | react << 8
    for s in states: XS.standard_reacts(anims_d[s]['steps'], react)
    if piece:                                       # a fury piece's reels never slide the victim (FF's hits push nobody:
        for s in states:                            # Bred's x stays 528 through Haggar's whole chain, rec_ff chain) -> bstep_t
            for st in anims_d[s]['steps']:          # flags 4 (export_bm 'noslide'): the dance keeps it in his reach
                if st['flags'] & 0x100: st['noslide'] = True
    anims_l = [{'steps': anims_d[s]['steps'], 'hold': True} for s in states]
    prow = play(prims, anims_l)
    st = lambda r: anims_l[r[0]]['steps'][r[1]]
    script = [[st(r)['frame'], int(r[2]), int(r[3]), []] for r in prow]
    opens = [i for i, r in enumerate(prow) if (i == 0 or prow[i - 1][:2] != r[:2]) and HS.openings(anims_l[r[0]]['steps'])[r[1]]]
    apex = max(range(len(prow)), key=lambda i: prow[i][3]) if prow else 0
    rom = {'states': states, 'anims': anims_d, 'prims': prims, 'objects': [], 'step_fx': [], 'openings': {}, 'hit_kind': 1,
           'last_hit': opens[-1] if opens else -1, 'apex': apex if prow and prow[apex][3] > 0 else -1,
           'length': len(prow), 'voice_frames': True, 'now': True,
           'vtable': {'rows': [], 'ncol': 0, 'nvar': 0, 'default': 0, 'vanim': len(states), 'vobj': 0, 'vdmg': 0,
                      'buttons': [], 'results': [-1], 'hits': [nh]}}
    return {'input': 'AJ', 'condition': 'normal', 'version': 'whiff', 'script': script, 'name': 'Special (attack + jump)',
            'base_input': 'AJ', 'row_boxes': [st(r)['boxes'] for r in prow],
            'row_steps': [[r[0], r[1], st(r)['flags'], 0xFF] for r in prow],
            'marks': [''] * len(script), 'projectiles': [], 'anims': [anim],
            'shape': [max(r[1] for r in script), max(r[2] for r in script), False], 'game_hits': len(opens), 'rom': rom,
            'ff': {'anim': anim, 'arc': arc, 'frames': len(prow)},
            'ss2': {'results': [], 'sounds': [], 'code_sounds': [], 'code_voices': []}}

def play(prims, anims_l):
    pl = HS.Play([tuple(p) for p in prims], anims_l); out = []
    while len(out) < 400:
        r = pl.frame()
        if r is None: break
        out.append(r)
    return out

def check(names):
    """the program's heights vs FF's (rec_ff special: the frames from the press, the press frame left out)"""
    import export_ff as X
    res = {}
    for n in names:
        B = X.Builder(n); sp = special(X, B, n)
        h = [r[2] for r in sp['script']]
        o = json.load(open(f'/data/tmp/ffight/rec/{n}_special.json')); P = [r['P'] for r in o['rows']]
        ff_h = [p['y'] - P[0]['y'] for p in P[1:]]
        ffa = [p['anim'] for p in P[1:]]
        idle = X.MOVES[n]['idle']
        end = next(i for i, a in enumerate(ffa) if a == idle)          # FF back in its idle = the move's end
        same = sum(1 for a, b in zip(h, ff_h[:end]) if abs(a - b) <= 1)
        res[n] = {'brawler_frames': len(h), 'ff_frames': end, 'heights_equal': same, 'peak': [max(h), max(ff_h)]}
        print(n, res[n])
    return res

if __name__ == '__main__': check(sys.argv[1:] or list(SPECIAL))
