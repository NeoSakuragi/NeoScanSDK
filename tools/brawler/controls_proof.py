#!/usr/bin/env python3
"""TODO #71 proof: the controls revamp (A attack, B jump / jump-cancel, A+B special, C fury) and the special meter, per
roster fighter, in the Chain Lab's training mode (labdrive: P1 = the fighter, a dummy that never attacks unless this
script drives it), our emulator's core (harness). Test-only pokes: the dummy's position, its intent for the one press
that hits P1, P1's meter set before a test (full, 59, 0).

    python3 controls_proof.py OUT_DIR [FIGHTER ...]     -> OUT_DIR/controls71.json, shots, sheet_fury.png

Per fighter: A from far / close / crouch / forward (the route tree's root link the game picked vs the tree), air A /
down+A / up+A, B jumps (vertical / forward / back), a B jump-cancel link in a route (its air node played by A), A+B in
each of the six slots chorded A-then-B and B-then-A inside the window and A, B outside it (no special), C fury with a
full meter and refused at 59, meter drain / refill numbers, a special out of a hit (double cost, white flash)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import routes as RT, export_bm
from labdrive import Lab
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json'))); M = G['meter']
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
MOVES = export_bm.MOVES
names = [r['name'] for r in G['roster']]
only = sys.argv[2:] or names
L = Lab(); b = L.b; ST = b.states
SLOT_DIR = {'D': '', 'fD': 'R', 'dD': 'D', 'uD': 'U', 'dfD': 'DR', 'ufD': 'UR'}
BS_FURY = 6

def st(i=0): return ST[b.fget(i, 'state')]
def run(n, k=''): b.run(n, p1=k)
def settle(meter=None):
    for _ in range(600):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'shot') and not b.fget(0, 'flash') and not b.fget(0, 'chain_t'): break
        run(1)
    else: raise RuntimeError('P1 never idle: ' + b.brief((0, 2)))
    if meter is not None: b.fset(0, 'meter', meter); b.fset(0, 'meter_t', 0)   # (and the frames toward the next point)
def setpos(dist, dz=0):
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100                 # P1 on screen at the training spot, the dummy dist px ahead
    b.place(0, x=x0, z=30); b.place(2, x=x0 + dist, z=30 + dz); b.fset(0, 'facing', 1); run(2)
def watch(n, want):
    """up to n frames: the first frame P1's state is in want -> (state, anim name, frame)"""
    for k in range(n):
        if st(0) in want: return st(0), MOVES[b.fget(0, 'anim')], k
        run(1)
    return st(0), None, None
def expect(tree, inputs):
    """the move the game should pick at the root for these candidate inputs (fighter.c next_node's fallback order)"""
    for k in inputs:
        nd = tree['links'].get(k)
        if nd: return nd.get('move') or 'special:' + nd['special']
def bpath(tree):
    """the shortest route (inputs from the root) to a node with a B link -> (inputs, its B node)"""
    q = [([k], nd) for k, nd in tree['links'].items()]
    while q:
        p, nd = q.pop(0)
        if 'B' in (nd.get('links') or {}): return p, nd['links']['B']
        q += [(p + [k], c) for k, c in (nd.get('links') or {}).items() if k != 'B' and 'move' in c]
    return None, None
KEYS = {'A': 'a', 'cA': 'a', 'dA': 'Da', 'fA': 'Ra', 'bA': 'La', 'dfA': 'DRa'}

res = {}; fury_shots = []
for ci, name in enumerate(names):
    if name not in only: continue
    F = CL['fighters'][ci]; tree = RT.load(name, os.path.join(HERE, '..', '..', G['roster'][ci]['routes'])
                                            if G['roster'][ci].get('routes', 'default') != 'default' else None)
    L.start(ci, 1 if ci == 0 else 0); run(30)
    r = res[name] = {'normals': {}, 'air': {}, 'jumps': {}, 'slots': {}, 'fury': {}, 'meter': {}}
    # ---- A from each position -------------------------------------------------------------------------------------
    for pos, dist, keys, cand in (('far', 70, 'a', ['A']), ('close', 28, 'a', ['cA', 'A']), ('crouch', 28, 'Da', ['dA', 'cA', 'A']),
                                  ('forward far', 70, 'Ra', ['fA', 'A'])):
        settle(M['max']); setpos(dist); run(3, keys); s, mv, _ = watch(12, ('ATTACK',))
        r['normals'][pos] = {'got': mv, 'want': expect(tree, cand), 'ok': mv == expect(tree, cand)}
    for pos, keys, ent in (('air A', 'a', 'air_a'), ('air down+A', 'Da', 'air_b'), ('air up+A', 'Ua', 'air_cd')):
        settle(M['max']); setpos(90); run(10, 'b'); watch(30, ('AIR',)); run(6); run(3, keys)
        s, mv, _ = watch(10, ('AIR_ATTACK',))
        want = (tree['entries'].get(ent) or RT.default_tree()['entries'][ent])['move'].replace('_jump', '')
        r['air'][pos] = {'got': mv, 'want': want + '_*', 'ok': bool(mv) and mv.startswith(want)}
    # ---- B jumps ------------------------------------------------------------------------------------------------------
    for d, keys in (('vertical', 'b'), ('forward', 'Rb'), ('back', 'Lb')):
        settle(M['max']); setpos(100); x0 = b.fget(0, 'x'); run(10, keys)
        s, _, _ = watch(20, ('AIR',)); jd = b.fget(0, 'jump_dir'); watch(120, ('LAND',))
        r['jumps'][d] = {'state': s, 'jump_dir': jd, 'dx': round(b.fget(0, 'x') - x0), 'facing': b.fget(0, 'facing'),
                         'ok': s == 'AIR' and jd == {'vertical': 0, 'forward': 1, 'back': 2}[d]}
    # ---- a B jump-cancel link -------------------------------------------------------------------------------------------
    path, bnode = bpath(tree)
    jc = r['jump_cancel'] = {'route': path + ['B', 'A'] if path else None}
    if path:
        for dist in ((28, 24, 34) if path[0] == 'cA' else (46, 52, 58)):
            settle(M['max']); setpos(dist); h0 = len([h for h in b.hits if h[1] == 2]); ok = True
            for k in path:
                n0 = b.fget(0, 'node') if st(0) == 'ATTACK' else -1
                run(3, KEYS[k])
                for _ in range(60):                       # its node started (a press in hit-stop waits) and hit
                    if st(0) == 'ATTACK' and b.fget(0, 'node') != n0 and b.fget(0, 'landed'): break
                    run(1)
                else: ok = False; break
            if not ok: continue
            run(3, 'b'); s, _, _ = watch(25, ('PREJUMP', 'AIR')); an = b.fget(0, 'air_node')
            watch(20, ('AIR',)); run(4); run(3, 'a'); s2, mv, _ = watch(10, ('AIR_ATTACK',))
            hit = False
            for _ in range(40):
                if any(h[1] == 2 for h in b.hits[h0:]) and st(0) == 'AIR_ATTACK' and b.fget(0, 'landed'): hit = True; break
                if st(0) not in ('AIR_ATTACK',): break
                run(1)
            jc.update({'dist': dist, 'jump': s, 'air_node': an, 'air_move': mv, 'want': bnode['move'], 'air_hit': hit,
                       'ok': s in ('PREJUMP', 'AIR') and an != 0 and bool(mv) and mv.startswith(bnode['move'].replace('_jump', ''))})
            break
        else: jc['ok'] = False; jc['note'] = 'the route never hit the dummy'
    # ---- A+B: six slots, both chord orders, and outside the window ----------------------------------------------------
    for slot, dk in SLOT_DIR.items():
        want = RT.SPECIALS.index(slot) if F['specials'][slot] else None
        out = {}
        for order, seq in (('A-B +1', [(1, 'a'), (1, 'ab')]), ('B-A +1', [(1, 'b'), (1, 'ab')]), ('A-B +2', [(2, 'a'), (1, 'ab')]),
                           ('B-A +2', [(2, 'b'), (1, 'ab')])):
            settle(M['max']); setpos(80)
            for n, k in seq: run(n, dk + k)
            s, _, _ = watch(6, ('SPECIAL',)); sid = b.fget(0, 'spec_id')
            out[order] = {'state': s, 'spec_id': sid, 'meter': b.fget(0, 'meter'),
                          'ok': s == 'SPECIAL' and (want is None or sid == want) and b.fget(0, 'meter') == M['max'] - M['special']}
        settle(M['max']); setpos(80); run(1, dk + 'a'); run(2, dk + 'a'); run(1, dk + 'ab'); seen = set()
        for _ in range(40): seen.add(st(0)); run(1)
        out['A then B +3 (outside)'] = {'states': sorted(seen), 'ok': 'SPECIAL' not in seen and 'ATTACK' in seen}
        r['slots'][slot] = {'kof': F['specials'][slot], 'want': want, **out}
    # ---- C: the fury ------------------------------------------------------------------------------------------------------
    fury = G['roster'][ci].get('fury')
    settle(M['max']); setpos(60); run(3, 'c'); s, _, _ = watch(6, ('SPECIAL',))
    r['fury'] = {'kof': fury, 'full': {'state': s, 'spec_id': b.fget(0, 'spec_id'), 'meter': b.fget(0, 'meter')}}
    if fury:
        run(20); p = os.path.join(OUT, f'fury_{name}.png'); b.screenshot(p); fury_shots.append((name, fury, p))
    settle(M['fury_min'] - 1); run(3, 'c'); seen = set()
    for _ in range(20): seen.add(st(0)); run(1)
    r['fury']['at_59'] = {'states': sorted(seen), 'meter': b.fget(0, 'meter')}
    r['fury']['ok'] = (s == 'SPECIAL' and r['fury']['full']['spec_id'] == BS_FURY and r['fury']['full']['meter'] == M['max'] - M['fury']
                       and 'SPECIAL' not in seen) if fury else (s != 'SPECIAL' and 'SPECIAL' not in seen)
    # ---- meter numbers: refill ------------------------------------------------------------------------------------------
    settle(0); m0 = b.fget(0, 'meter'); run(100); r['meter']['refill_100_frames'] = b.fget(0, 'meter') - m0
    r['meter']['ok'] = r['meter']['refill_100_frames'] in (100 // M['refill'], 100 // M['refill'] - 1)
    # ---- a special out of a hit: double cost, white flash -----------------------------------------------------------------
    hd = r['hit_special'] = {'ok': False}
    for dist in (26, 32, 20, 38):
        settle(M['max']); setpos(dist); b.intent(2, press=1, face=-1); run(1)
        if watch(40, ('HITSTUN',))[0] != 'HITSTUN': continue
        while b.fget(0, 'freeze'): run(1)
        run(1, 'a'); run(1, 'ab'); s, _, _ = watch(4, ('SPECIAL',))
        hd.update({'dist': dist, 'state': s, 'meter': b.fget(0, 'meter'), 'flash': b.fget(0, 'flash'), 'want_meter': M['max'] - M['hit_mul'] * M['special']})
        if ci == 0 or name in ('ryo', 'haohmaru'): b.screenshot(os.path.join(OUT, f'flash_{name}.png'))
        run(M['flash'] + 2); hd['flash_after'] = b.fget(0, 'flash')
        hd['ok'] = s == 'SPECIAL' and hd['meter'] == hd['want_meter'] and hd['flash'] > 0 and hd['flash_after'] == 0
        break
    if ci == 0: settle(70); setpos(120); run(10); b.screenshot(os.path.join(OUT, 'hud_meter.png'))
    oks = {'normals': all(v['ok'] for v in r['normals'].values()), 'air': all(v['ok'] for v in r['air'].values()),
           'jumps': all(v['ok'] for v in r['jumps'].values()), 'jump_cancel': jc.get('ok'),
           'slots': all(o['ok'] for v in r['slots'].values() for k, o in v.items() if isinstance(o, dict)),
           'fury': r['fury']['ok'], 'meter': r['meter']['ok'], 'hit_special': hd['ok']}
    r['ok'] = oks
    print(name, ' '.join(f'{k}={"ok" if v else "FAIL"}' for k, v in oks.items()), flush=True)
json.dump(res, open(os.path.join(OUT, 'controls71.json'), 'w'), indent=1)
if fury_shots:                                            # one sheet: each fighter's fury 20 frames in
    ims = [Image.open(p) for _, _, p in fury_shots]; w, h = ims[0].size; cols = 6
    sheet = Image.new('RGB', (w * cols, (h + 14) * ((len(ims) + cols - 1) // cols)), 'white'); d = ImageDraw.Draw(sheet)
    for i, ((n, f, _), im) in enumerate(zip(fury_shots, ims)):
        x, y = i % cols * w, i // cols * (h + 14); sheet.paste(im, (x, y + 14)); d.text((x + 4, y + 1), f'{n} fury {f}', fill='black')
    sheet.save(os.path.join(OUT, 'sheet_fury.png'))
