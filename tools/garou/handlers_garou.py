#!/usr/bin/env python3
"""Garou's specials, supers and throw for Rock as brawler programs (bprim_t, fighter.c prog_update): the op model of
tools/lastbld2/handlers_lb2.py (one program state per run of frames with one motion: one velocity + one acceleration
in x and in height).

Where the motion comes from: Garou drives a move from a DESCRIPTOR (+$D4, bank $29174[char], table $2C118[char] +
$B80, indexed by the move id +$BA and the sub-index +$FA: [anim word][control words]...) and the animation player
($11C9E: step records + durations, decoded in garou.py, frame for frame = the game: check_timeline.py). The descriptor
interpreter (its velocity / landing / loop control words) is NOT decoded: the motion of each move is the game's own play
in our emulator (capture_garou.py: x / height per frame; the object velocity registers +$34 / +$3C hold the constants
the move code loads), cut into constant-velocity / constant-acceleration segments (handlers_lb2.segments). The frames,
boxes and step timing come from the ROM (the capture gives which animation step shows on each frame; each step's frame,
offsets and boxes are read from the step records). Effect objects (Reppuken's wave, Raging Storm's pillars) are his
own animations played by $100600+ tasks: their frames / boxes from the ROM, their place per frame from the capture.

Classification (docs/brawler_move_vocabulary.md, no recorded specials): every special = existing library pieces:
motion segments (P_SET vx / vy / g + P_MOVE / P_FALL), a travelling projectile (bproj_t kind 1: Reppuken, its loop
and impact), placed effects (kind 3: Raging Storm's pillars, Reppuken C's charge), button versions as separate
specials. Not imported: Rage Run's follow-ups (Type Dunk / Shift / stop), the command grab / counter 236B / 236D (a grab
would hold the victim: only throws may; not decoded), the Neo-Max, Garou's Break / feint / T.O.P. / Just Defend.

Labels: [code] read in the disassembly (/data/tmp/garou_t3/p0.dis), [meas] measured in our emulator, [inf] inferred."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'lastbld2'))
sys.path.insert(0, os.path.join(HERE, '..', 'samsho2'))
import garou as G
import handlers_ss2 as HS
import handlers_lb2 as HL                      # segments / assemble / encode / standard_reacts: one path with LB2

P, REG, PC = HS.P, HS.REG, HS.PC
R_HEAVY, R_KNOCKDOWN = HS.R_HEAVY, HS.R_KNOCKDOWN
SPECIAL_DAMAGE = HS.SPECIAL_DAMAGE
CAPTURE = '/data/neogeo_dict/garou/rock_capture.json'
_CAP = None
def cap():
    global _CAP
    if _CAP is None: _CAP = json.load(open(CAPTURE))
    return _CAP

# input -> name (SNK's names; the inputs read in our emulator: capture_garou.MOVES). Supers need the gauge (+$BE).
SPECIALS = {'rock': {
    '236A': 'Reppuken (A)', '236C': 'Reppuken (C)',
    '28A': 'Rising Tackle (A)', '28C': 'Rising Tackle (C)',
    '214A': 'Hard Edge (A)', '214C': 'Hard Edge (C)',
    '214B': 'Rage Run (B)', '214D': 'Rage Run (D)',
    '236236A': 'Raging Storm (A)', '236236C': 'Raging Storm (C)',
    '236236B': 'Shine Knuckle (B)', '236236D': 'Shine Knuckle (D)',
}}
REACH = 470                                    # px: a travelling projectile's rows until this far (off any screen)

def boxes_of(ch, rows, key=lambda r: (r['anim'], r['step'])):
    """per row the step's boxes, flag $08 = the boxes stay as they were (the step loader $11F04)"""
    out, cur = [], []
    for r in rows:
        st = G.step(ch, *key(r))
        if not st['f76'] & 0x08: cur = st['boxes']
        out.append((st, cur))
    return out

def model_rows(ch, rows):
    """capture rows -> export_garou.collapse rows (the step record, the boxes) + x / h for the segments"""
    bx = boxes_of(ch, rows)
    return [{'anim': r['anim'], 'step': r['step'], 'st': st, 'boxes': b, 'x': r['x'], 'h': r['h']} for r, (st, b) in zip(rows, bx)]

# ---- objects ----
def object_tracks(rows):
    """[[(row index, obj)]] of the move's objects in birth order: a task's frames while it runs (one track until a
    frame gap: a re-used task starts another); its trailing frames after its animation ran out (+$7E bit 7: the task
    stays, nothing drawn) dropped. One object may play several animations (Reppuken: $6B > $6C > $78)"""
    tr = {}
    for i, r in enumerate(rows):
        for o in r['objs']: tr.setdefault(o['task'], []).append((i, o))
    out = []
    for t, lst in tr.items():
        cur = [lst[0]]
        for a, b in zip(lst, lst[1:]):
            if b[0] != a[0] + 1: out.append(cur); cur = []
            cur.append(b)
        out.append(cur)
    out = [[x for x in tk[:max(k for k, (_, o) in enumerate(tk) if not o.get('ended')) + 1]] for tk in out
           if any(not o.get('ended') for _, o in tk)]
    return sorted(out, key=lambda tk: tk[0][0])

def effect_object(B, ch, track, rows):
    """a track of an object -> bproj_t dict: x from the owner's place on its first frame (forward +), up +; a moving
    one (vx) = kind 1: its flight rows (the looping animation carried on at its speed to REACH px), its impact animation
    (the object's next animation once it stops) as end rows; a still one = a placed effect (kind 3)"""
    import export_garou as X
    i0, o0 = track[0]
    ox = rows[i0]['x']
    objs = [o for _, o in track]
    bx = boxes_of(ch, objs)
    moving = [k for k, o in enumerate(objs) if abs(o['vx']) > 0.01]
    def row(o, st, b, dx=0.0):
        atk = [v for v in b if X.is_attack(v[0])]; box = X.kof_box(atk) if atk else None
        return [B.step_frame(ch, st), round(o['x'] - ox + dx, 2), round(o['h']), [1] + box if box else None, None, 0]
    base = {'loop': None, 'end': [], 'hit_kind': 1, 'react': 'heavy', 'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0,
            'child': None, 'sig': 0, 'next': None, 'stop': 0, 'rearm': 0, 'hits': {}}
    if moving and any(X.is_attack(v[0]) for _, b in bx for v in b):   # a projectile (a moving hitter); a moving
                                                                    # effect without hits keeps its measured rows (placed)
        a, b = moving[0], moving[-1]
        fl = [row(o, st, bb) for o, (st, bb) in zip(objs[:b + 1], bx[:b + 1])]
        vx = objs[b]['vx']; anim = objs[b]['anim']
        tl = X.timeline(ch, anim, loop=True)          # carry the loop on at its speed
        k = next((j for j, r in enumerate(tl) if r['step'] == objs[b]['step']), 0)
        last = objs[b]; t = 0
        while fl[-1][1] < REACH and len(fl) < 250:
            t += 1; k = (k + 1) % len(tl)
            st = tl[k]['st']; bb = tl[k]['boxes']
            fl.append(row(last, st, bb, vx * t))
        end = [[B.step_frame(ch, st), round(o['x'] - objs[b]['x'] - vx), 0] for o, (st, bb) in zip(objs[b + 1:], bx[b + 1:])]
        return dict(base, kind=1, rows=fl, end=end, travel=fl[-1][1], vx=vx, name=f'GAROU_{anim:X}',
                    garou={'anims': sorted({o['anim'] for o in objs}), 'vx': vx, 'flight_rows_measured': b + 1})
    fl = [row(o, st, bb) for o, (st, bb) in zip(objs, bx)]
    return dict(base, kind=3, rows=fl, follow=0, placed=True, react='knockdown', name=f'GAROU_{objs[0]["anim"]:X}',
                garou={'anims': sorted({o['anim'] for o in objs})})

# ---- a special ----
def program(B, ch, rows):
    import export_garou as X
    mr = model_rows(ch, rows)
    segs, dx, dh = HL.segments(mr, [])
    tracks = object_tracks(rows)
    births = [(t[0][0], j) for j, t in enumerate(tracks)]
    objects = [effect_object(B, ch, t, rows) for t in tracks]
    ops, states, anims_d, step_fx = [], [], {}, []
    for i, (a, b) in enumerate(segs):
        n = b - a + 1
        cuts = {k - a for k, _ in births if a <= k <= b}
        steps = X.collapse(B, ch, mr[a:b + 1], cuts)
        for k, j in births:
            if a <= k <= b: step_fx.append((i, HL.step_of(steps, k - a), j))
        steps[0]['ticks'] += 1                        # the brawler's clock (handlers_lb2.program)
        if steps[-1]['ticks']: steps[-1]['ticks'] -= 1
        key = f'{i}:{rows[a]["anim"]:x}.{a}'
        anims_d[key] = {'mode': 'hold', 'steps': steps, 'garou': [rows[a]['anim'], a, b]}
        states.append(key)
        vx = dx[a]; ax = (dx[a + 1] - dx[a]) if n > 1 else 0.0
        vh = dh[a]; ah = (dh[a + 1] - dh[a]) if n > 1 else 0.0
        air = any(mr[j]['h'] > 0 for j in range(a, b + 1)) or (a and mr[a - 1]['h'] > 0)
        ops += [('label', ('E', i)), ('anim', i), ('set', 'vx', round(vx * 65536)), ('set', 'cnt', n - 1)]
        if air: ops += [('set', 'vy', round(vh * 65536)), ('set', 'g', round(-ah * 65536))]
        ops += [('resume',), ('move',)]
        if ax: ops.append(('add', 'vx', round(ax * 65536)))
        if air: ops.append(('fall',))
        ops += [('dec',), ('br', 'cnt', 1, ('S', i)), ('br', 'always', 1, 'yield'),
                ('label', ('S', i)), ('resume_at', ('E', i + 1)), ('br', 'always', 1, 'yield')]
    ops += [('label', ('E', len(segs))), ('label', 'END'), ('end',)]
    return ops, states, anims_d, segs, objects, sorted(set(step_fx))

def special(B, ch, name, inp):
    rows = cap()[inp]
    ops, states, anims_d, segs, objects, step_fx = program(B, ch, rows)
    prims = [HL.encode(o) for o in HL.assemble(ops)]
    nh = sum(sum(HL.openings(anims_d[s]['steps'])) for s in states) + sum(1 for o in objects if any(r[3] for r in o['rows']))
    each = max(1, SPECIAL_DAMAGE // max(1, nh))
    hitting = [j for j, s in enumerate(states) if any(HL.openings(anims_d[s]['steps']))]
    for p in prims:
        if p[0] == P['anim']:
            j = p[1]; react = R_KNOCKDOWN if hitting and j == hitting[-1] else R_HEAVY
            p[2] = each | react << 8
    for j, s in enumerate(states):
        HL.standard_reacts(anims_d[s]['steps'], R_KNOCKDOWN if hitting and j == hitting[-1] else R_HEAVY)
    anims_l = [{'steps': anims_d[s]['steps'], 'hold': True} for s in states]
    pl = HS.Play([tuple(p) for p in prims], anims_l)
    prow = []
    while len(prow) < 900:
        r = pl.frame()
        if r is None: break
        prow.append(r)
    script = [[anims_l[r[0]]['steps'][r[1]]['frame'], int(r[2]), int(r[3]), []] for r in prow] or [[0, 0, 0, []]]
    rb = [anims_l[r[0]]['steps'][r[1]]['boxes'] for r in prow] or [{}]
    rs = [[r[0], r[1], anims_l[r[0]]['steps'][r[1]]['flags'], 0xFF] for r in prow] or [[0, 0, 0, 0xFF]]
    opens = [i for i, r in enumerate(prow) if (i == 0 or prow[i - 1][:2] != r[:2]) and HL.openings(anims_l[r[0]]['steps'])[r[1]]]
    apex = max(range(len(prow)), key=lambda i: prow[i][3]) if prow else 0
    rom = {'states': states, 'anims': anims_d, 'prims': prims, 'objects': objects, 'step_fx': step_fx, 'openings': {},
           'hit_kind': 1, 'last_hit': opens[-1] if opens else -1, 'apex': apex if prow and prow[apex][3] > 0 else -1,
           'length': len(prow), 'voice_frames': True, 'now': True,
           'vtable': {'rows': [], 'ncol': 0, 'nvar': 0, 'default': 0, 'vanim': len(states), 'vobj': 0, 'vdmg': 0,
                      'buttons': [], 'results': [-1], 'hits': [nh]}}
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'name': SPECIALS[name][inp],
            'base_input': inp, 'row_boxes': rb, 'row_steps': rs, 'marks': [''] * len(script), 'projectiles': [],
            'anims': sorted({r['anim'] for r in rows}), 'shape': [max(r[1] for r in script), max(r[2] for r in script), False],
            'game_hits': len(opens), 'rom': rom,
            'garou': {'segments': segs, 'frames': len(rows), 'objects': [o['garou'] for o in objects]},
            'ss2': {'results': [], 'sounds': [], 'code_sounds': [], 'code_voices': []}}

def specials(B, ch, name, lab=False, inputs=None):
    return [special(B, ch, name, inp) for inp in SPECIALS[name]]

# ---- win pose [meas]: P2 KO'd by a stand B / C from close.state (life poked to 1): ~170 frames after the KO P1 plays
# anim $206 (142 frames), both buttons
WINS = {'rock': [0x206]}
def win_anims(B, ch, name):
    import export_garou as X
    return {('win' if k == 0 else f'win_{k + 1}'): {'slot': a, 'mode': 'hold', 'steps': X.anim_steps(B, ch, a)}
            for k, a in enumerate(WINS.get(name, []))}

# ---- the throw [meas] -----------------------------------------------------------------------------------------------
# close (walked in from close.state) + forward / back + C: the thrower's anims $51 > $52; the victim plays its OWN
# anims $236 (held, carried behind him, over his head) > $2A1 (the landing bounce) > $1FB (lying) > $17E (getting up),
# turned to his facing; the damage at the landing (Terry's life 120 -> 106 [meas]). The victim's frames here = Rock's
# own frames for those anims (Rock thrown by Rock: every character's table has them at the same numbers [meas: Terry's
# play, Rock's ROM table]); victim_poses_garou.json names the postures.
THROW = {'rock': {'anims': (0x51, 0x52), 'victim': (0x236, 0x2A1), 'name': 'Rock throw (close + forward / back + C)'}}

def throw(B, ch, name):
    import export_garou as X
    t = THROW[name]; rows = cap()['throw']
    mr = model_rows(ch, [r for r in rows if r['anim'] in t['anims']])
    steps = X.collapse(B, ch, mr)
    timeline = [[B.step_frame(ch, r['st']), round(r['x']), round(r['h']), 0] for r in mr]
    vrows = []; land = rel = None; life0 = rows[0]['v']['life']
    for i, r in enumerate(rows):
        v = r['v']
        dx, dy = round(v['x'] - r['x']), round(v['h'] - r['h'])
        same = 1 if v['face'] == 0 else 0
        if v['anim'] in t['victim']:
            st = G.step(ch, v['anim'], v['step'])
            if rel is None and v['anim'] == t['victim'][0] and dx > 0: rel = i
            if land is None and v['life'] < life0: land = i
            vrows.append([B.step_frame(ch, st), dx, dy, same, 0, f"{v['anim']}.{v['step']}", None])
        elif v['anim'] in (0x1FB, 0x17E):
            vrows.append([-1, dx, 0, same, 0, f"{v['anim']}.{v['step']}", 'down' if v['anim'] == 0x1FB else 'getup'])
        elif vrows:
            break
        else:                                         # the grab's first frame (still standing)
            st = G.step(ch, t['victim'][0], 0)
            vrows.append([B.step_frame(ch, st), dx, dy, same, 0, f"{t['victim'][0]}.0", None])
    return {'slot': t['anims'][0], 'inputs': t['name'], 'table': [], 'hold': False, 'rom': True, 'timeline': timeline,
            'victims': {name: vrows}, 'impacts': [land] if land is not None else [], 'release': rel, 'land': land,
            'ret': len(timeline), 'anim': {'slot': t['anims'][0], 'mode': 'hold', 'steps': steps},
            'garou': {'anims': list(t['anims']), 'victim': list(t['victim']), 'damage': life0 - rows[-1]['v']['life']},
            'turned': False, 'grab_frame': None, 'name': t['name']}

def throws(B, ch, name):
    """throw_c / throw_d (forward / back + A in the brawler's hold): Garou's one throw, forward or back + C, both slots"""
    if name not in THROW: return {}
    th = throw(B, ch, name)
    return {'throw_c': th, 'throw_d': json.loads(json.dumps(th))}

# ---- check: the programs against the game, frame by frame ---------------------------------------------------------------
def check(name='rock'):
    import export_garou as X
    ch = X.CAST[name]; B = X.Builder(ch); res = {}
    for inp in SPECIALS[name]:
        sp = special(B, ch, name, inp); rows = cap()[inp]
        sc = sp['script']; n = min(len(sc), len(rows)); eq = 0; bad = None
        for k in range(n):
            g = B.frames[sc[k][0]]['garou']['fid']
            ok = g == rows[k]['fid'] and abs(sc[k][1] - int(rows[k]['x'])) <= 1 and abs(sc[k][2] - int(rows[k]['h'])) <= 1
            eq += ok
            if not ok and bad is None: bad = (k, g, sc[k][1], sc[k][2], rows[k]['fid'], round(rows[k]['x'], 1), round(rows[k]['h'], 1))
        res[inp] = dict(game=len(rows), program=len(sc), equal=eq, first_bad=bad, states=len(sp['rom']['states']),
                        objects=len(sp['rom']['objects']))
        print(inp, res[inp])
    return res

if __name__ == '__main__': check()
