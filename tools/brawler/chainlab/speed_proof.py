#!/usr/bin/env python3
"""Chain Lab speed proof in our emulator's core (harness; never MAME), on the training mode:
  timing   every route move of a fighter at 1x, whiffed: frames in ATTACK and the step shown each frame vs KOF's
           ticks + 1 per step (routes.play_steps at 0x100, which is the export's ticks + 1 summed)
  hits     multi-hit moves and specials (route enders) at 1x / 2x / 4x: hits landed on the dummy, per speed
  throw    a forward throw on the dummy: per frame from the throw's start, thrower frame / x / y / facing, victim
           frame / x / y / life -> JSON, for a comparison between builds (today's 1.5x vs the speed mechanism)
    python3 speed_proof.py GAME_DIR timing|hits|throw OUT.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
from labdrive import Lab, BUF_OFF
game, what, out = sys.argv[1:4]
L = Lab(game=game); b = L.b; ST = b.states
data = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
FI = {f['name']: i for i, f in enumerate(data['fighters'])}
sys.path.insert(0, os.path.join(game, '..', '..', 'tools', 'brawler'))
import routes, export_bm

def tree_blob(fname, tree):
    f = data['fighters'][FI[fname]]
    return list(routes.encode(tree, export_bm.MOVES, set(f['has'])))

def start(fname, tree=None, dummy='ryo'):
    L.start(FI[fname], FI[dummy], tree_blob(fname, tree) if tree else None)

res = {}
if what == 'timing':
    f = data['fighters'][FI['terry']]; rows = []
    for m in routes.MOVE_NAMES:
        if m not in f['has']: continue
        start('terry', {'links': {'A': {'move': m}}})
        b.place(2, x=1000)                                   # the dummy out of reach (lab_flow keeps it on screen, far)
        b.run(3)
        shown = []; k = 0
        b.run(1, p1='a')
        while ST[b.fget(0, 'state')] != 'ATTACK' and k < 10: b.run(1, p1='a'); k += 1
        while ST[b.fget(0, 'state')] == 'ATTACK':
            shown.append(b.fget(0, 'step')); b.run(1)
        kof = sum(t + 1 for t, a, n in f['moves'][m]['steps'])
        model = routes.play_steps([tuple(x) for x in f['moves'][m]['steps']])
        # the harness samples RAM when the video frame ends, which falls inside P1's update, after its anim_tick and
        # before its state machine (harness.py / regress.py: the sample's place in the tick): sample k shows frame k's
        # step with frame k - 1's state, so the samples are the model one frame on (and the last step once more)
        model = model[1:] + model[-1:]
        rows.append({'move': m, 'brawler_frames': len(shown), 'kof_frames': kof, 'steps_match_model': shown == model,
                     'shown': shown})
        print(f'{m:14s} brawler {len(shown):3d}  KOF {kof:3d}  {"OK" if len(shown) == kof and shown == model else "DIFF"}')
    res['timing'] = rows
elif what == 'hits':
    cases = [('terry', 'atk_c_close', None), ('terry', 'cmd_fwd_a', None), ('terry', 'cmd_df_c', None), ('ralf', 'atk_c_close', None)]
    cases += [('ralf', 'atk_a_close', k) for k in routes.SPECIALS] + [('terry', 'atk_a_close', k) for k in routes.SPECIALS]   # close A, then the special as the route's ender
    rows = []
    for fname, m, sp in cases:
        r = {'fighter': fname, 'move': m, 'special': sp}
        for spd in (1, 2, 4):
            if sp: tree = {'links': {'A': {'move': 'atk_a_close', 'links': {sp: {'special': sp, 'speed': spd}}}}}
            else: tree = {'links': {'A': {'move': m, 'speed': spd}}}
            start(fname, tree)
            b.run(3)
            if sp: b.run(2, p1='a'); b.run(4); b.run(2, p1='D' if sp == 'dD' else 'U' if sp == 'uD' else 'R' if sp == 'fD' else ''); b.run(2, p1=('D' if sp == 'dD' else 'U' if sp == 'uD' else 'R' if sp == 'fD' else '') + 'd')
            else: b.run(2, p1='a')
            b.run(260)
            ev = L.events()
            hits = [e for e in ev if e[1] == 'HIT']
            r[f'x{spd}'] = {'normal_hits': sum(1 for e in hits if e[2] != 0xFF), 'special_hits': sum(1 for e in hits if e[2] == 0xFF),
                            'special_started': any(e[1] == 'SPECIAL' for e in ev)}
        same = r['x1'] == r['x2'] == r['x4']
        r['same'] = same; rows.append(r)
        print(fname, m, sp or '', {k: (v['normal_hits'], v['special_hits'], v['special_started']) for k, v in r.items() if k[0] == 'x'}, 'SAME' if same else 'DIFF')
    res['hits'] = rows
elif what == 'throw':
    start('terry')
    b.run(3)
    k = 0
    while ST[b.fget(0, 'state')] != 'GRAB' and k < 200: b.run(1, p1='R'); k += 1
    b.run(1); b.run(2, p1='Ra')
    tr = []
    while ST[b.fget(0, 'state')] != 'THROW': b.run(1)
    for _ in range(120):
        tr.append([ST[b.fget(0, 'state')], b.fget(0, 'frame_ovr'), round(b.fget(0, 'x'), 3), round(b.fget(0, 'y'), 3), b.fget(0, 'facing'),
                   ST[b.fget(2, 'state')], b.fget(2, 'frame_ovr'), round(b.fget(2, 'x'), 3), round(b.fget(2, 'y'), 3), b.fget(2, 'hp')])
        b.run(1)
    res['throw'] = tr
    print('grab after', k, 'frames; throw frames', sum(1 for t in tr if t[0] == 'THROW'), 'victim hp', [t[9] for t in tr][::10])
json.dump(res, open(out, 'w'))
