#!/usr/bin/env python3
"""Proof of note 20261011-114113-5d29 (Double Dragon's dash, game.json roster[].run {"mode": "dash", "air_buttons":
true}; fighter.c dash_air): in the Chain Lab (labdrive: P1 = the fighter, a dummy), our emulator's core (harness).

    python3 dd_dash_proof.py OUT_DIR [FIGHTER ...]     -> OUT_DIR/dd_dash.json, screenshots

Per fighter (default: the DD fighters + Kim + Terry):
  dash      forward,forward and nothing more: the run state over the dash's course (run.dash: start + frames), its
            travel (dx px), the body on the floor (y 0) all along, back to neutral on its own
  A / dA    A (down+A) in its airborne frames: AIR_ATTACK on the forward jump's attack (the tree's air_cd; down+A air_b),
            in the air (y > 0), the dummy hit when its hit window opens in the air (Cheng-Fu's j.D opens past his
            dash's air: cut first, no hit); at the dash's end standing at once (IDLE / WALK on the frame y is 0
            again, the air move cut: no air pose on the ground, no LAND; the reopen of the note);
  A_late / dA_late  the same pressed 3 frames before the course's end (the air move still playing there): standing on
            the landing frame -> OUT_DIR/end_<fighter>_<tag>.png (that frame)
  B / C / D a press in its airborne frames (no air special): nothing, the dash goes on (RUN to its end)
  without air_buttons (Kim): A in the dash = his dash attack (ATTACK), as before; a fighter with a run (Terry): RUN
  while forward is held."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import export_bm, routes as RT
from labdrive import Lab

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json')))
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
names = [r['name'] for r in G['roster']]
only = sys.argv[2:] or [r['name'] for r in G['roster'] if r['bank'].startswith('doubledr:')] + ['kim', 'terry']
MOVES = export_bm.MOVES
L = Lab(); b = L.b; ST = b.states
def st(i=0): return ST[b.fget(i, 'state')]
def run(n, k=''): b.run(n, p1=k)

def fresh(ci, gap=300):
    """the lab on this fighter, the dummy gap px ahead on its lane (300: out of the dash's reach), both standing"""
    L.start(ci, 1 if ci == 0 else 0); run(30)
    for _ in range(300):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK'): break
        run(1)
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 60
    b.place(0, x=x0, z=30); b.place(2, x=x0 + gap, z=30); b.fset(0, 'facing', 1); b.fset(2, 'facing', -1); run(2)
    return x0

def dash_in():
    """forward, forward: -> frames until the run state (0 = the frame it entered)"""
    run(2, 'R'); run(2); run(1, 'R')
    for k in range(6):
        if st(0) == 'RUN': return k
        run(1, 'R')
    raise RuntimeError('no run: ' + b.brief((0,)))

res = {}
for name in only:
    ci = names.index(name); r = G['roster'][ci]; run_cfg = r.get('run') or {}
    d = run_cfg.get('dash'); airb = bool(run_cfg.get('air_buttons'))
    out = res[name] = {'run': {k: v for k, v in run_cfg.items() if k != 'about'}}
    if not d:                                                 # a run: forward held keeps it
        fresh(ci); dash_in(); x0 = b.fget(0, 'x'); run(30, 'R')
        out['run_held'] = {'state': st(0), 'dx': round(b.fget(0, 'x') - x0), 'ok': st(0) == 'RUN' and b.fget(0, 'x') - x0 > 30}
        continue
    tree = CL['fighters'][ci]['tree']
    # the dash alone
    x0 = fresh(ci); dash_in(); xs = b.fget(0, 'x'); trace = []
    for k in range(d['start'] + d['frames'] + 30):
        trace.append((st(0), round(b.fget(0, 'x') - xs), round(b.fget(0, 'y'), 2)))
        if st(0) not in ('RUN',): break
        if k == d['start'] + d['frames'] // 2: b.screenshot(os.path.join(OUT, f'{name}_dash.png'))   # (a frame, as run(1))
        else: run(1)
    nrun = sum(1 for t in trace if t[0] == 'RUN')
    out['dash'] = {'run_frames': nrun, 'dx': trace[-1][1], 'y_max': max(t[2] for t in trace), 'end': trace[-1][0],
                   'ok': trace[-1][0] in ('IDLE', 'WALK') and abs(trace[-1][1] - d['dx']) <= 2 and max(t[2] for t in trace) == 0}
    # A / down+A / B / C / D in the airborne frames (the 6th)
    for tag, keys in (('A', 'a'), ('dA', 'Da'), ('B', 'b'), ('C', 'c'), ('D', 'd'), ('A_late', 'a'), ('dA_late', 'Da')):
        if tag.endswith('_late') and not airb: continue
        fresh(ci, 300 if tag.endswith('_late') else 90); b.hits.clear(); dash_in(); xs = b.fget(0, 'x')   # (late: the dummy out of reach, no grab)
        run(d['start'] + (d['frames'] - 3 if tag.endswith('_late') else 5) - 1); hp0 = b.fget(2, 'hp')
        snaps = []
        run(1, keys)
        for _ in range(2):                                     # (the press read on the next tick)
            if st(0) != 'RUN': break
            run(1)
        first = (st(0), MOVES[b.fget(0, 'anim')], round(b.fget(0, 'y'), 2), b.fget(0, 'node'))
        if tag == 'A' and name in only[:3]:
            b.screenshot(os.path.join(OUT, f'{name}_dashA_1.png')); run(3); b.screenshot(os.path.join(OUT, f'{name}_dashA_2.png'))
        seen, ymax, landed_at, ground_air, at_land, active = set(), 0, None, 0, None, False
        for k in range(d['frames'] + 40):
            seen.add(st(0)); y = b.fget(0, 'y'); ymax = max(ymax, y)
            if st(0) == 'AIR_ATTACK' and b.fget(0, 'aact'): active = True   # its hit window reached in the air
            if st(0) in ('AIR_ATTACK', 'AIR') and y <= 0 and ymax > 0: ground_air += 1   # an air pose on the floor
            if ymax > 0 and y <= 0 and landed_at is None:     # the landing frame: standing?
                landed_at = k; lx = round(b.fget(0, 'x') - xs); at_land = (st(0), MOVES[b.fget(0, 'anim')])
                if tag.endswith('_late'): b.screenshot(os.path.join(OUT, f'end_{name}_{tag}.png'))
            if st(0) in ('IDLE', 'WALK') and k > 2: break
            run(1)
        hit = b.fget(2, 'hp') < hp0
        e = {'first': first, 'states': sorted(seen), 'y_max': round(ymax, 1), 'dummy_hit': hit, 'end': st(0),
             'at_landing': at_land, 'air_pose_on_ground': ground_air, 'active_in_air': active}
        if tag in ('A_late', 'dA_late'):
            e['want'] = 'standing on the landing frame (IDLE / WALK), no air pose on the ground'
            e['ok'] = first[0] == 'AIR_ATTACK' and first[2] > 0 and at_land is not None and at_land[0] in ('IDLE', 'WALK') and not ground_air and 'LAND' not in seen
        elif tag in ('A', 'dA'):
            if airb:
                ent = 'air_cd' if tag == 'A' else 'air_b'; want = tree['entries'].get(ent) or RT.default_tree()['entries'][ent]
                wmv = (want or {}).get('move', '').replace('_jump', '')
                e['want'] = f'AIR_ATTACK {wmv}_*'; e['land_dx'] = lx if landed_at is not None else None
                e['ok'] = (first[0] == 'AIR_ATTACK' and first[1].startswith(wmv) and first[2] > 0 and (hit or not active) and 'LAND' not in seen
                           and at_land is not None and at_land[0] in ('IDLE', 'WALK') and not ground_air)
            else:
                e['want'] = 'ATTACK / SPECIAL (his run + A: the ff Blitz / dash attack)'; e['ok'] = first[0] in ('ATTACK', 'SPECIAL')
        else:
            if airb:
                e['want'] = 'RUN (nothing: the dash goes on)'; e['ok'] = first[0] == 'RUN' and not seen & {'AIR', 'PREJUMP', 'SPECIAL', 'AIR_ATTACK'}
            else: e['want'] = '(Kim: the ground rules)'; e['ok'] = True
        out[tag] = e
    out['ok'] = all(v.get('ok', True) for v in out.values() if isinstance(v, dict))
json.dump(res, open(os.path.join(OUT, 'dd_dash.json'), 'w'), indent=1)
for n, v in res.items():
    print(n, 'OK' if v.get('ok', v.get('run_held', {}).get('ok')) else 'FAIL')
    for k, e in v.items():
        if isinstance(e, dict) and k != 'run': print('  ', k, e)
