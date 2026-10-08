#!/usr/bin/env python3
"""Revamp 1A: the rv1a-* scenarios (scenarios.json) played as the Player / proof clip plays them (scenario.py setup, then
do_keys and `proof` frames), our emulator's core: per recipe P1's links / throws started, the hits it landed (damage,
the victim's state), the second dummy's states, P1's hits taken, and a contact sheet of every 8th frame.

    python3 chain_scenarios_check.py OUT_DIR [ID ...]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H, scenario as SC, export_bm
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
R = json.load(open(os.path.join(HERE, 'scenarios.json')))
ids = sys.argv[2:] or [k for k in R if k.startswith(('rv1a-', 'rv3b-'))]   # (rv3b: Krauser's chain, the grab furies)
res = {}
b = H.Brawler(); b.game = H.GAME; ST = b.states
for rid in ids:
    rec = R[rid]
    SC.setup(b, rec)
    log = {'links': [], 'hits': [], 'p1_hit': 0, 'extra_states': set()}; prev = (None, None); shots = []
    keys = [(int(n), k) for n, _, k in (p.partition(':') for p in rec.get('do_keys', '').split(',') if p)]
    keys.append((rec.get('proof', 90), '-'))
    t = 0
    for n, k in keys:
        for _ in range(n):
            hp2, hp0 = b.fget(2, 'hp'), b.fget(0, 'hp')
            b.run(1, p1=k); t += 1
            s0 = ST[b.fget(0, 'state')]; nd = b.fget(0, 'node')
            if (s0 == 'ATTACK' and (prev[0] != 'ATTACK' or nd != prev[1])) or (s0 == 'THROW' and prev[0] != 'THROW'):
                log['links'].append((t, export_bm.MOVES[b.fget(0, 'anim')] if s0 == 'ATTACK' else 'THROW'))
            prev = (s0, nd)
            if b.fget(2, 'hp') < hp2: log['hits'].append((t, hp2 - b.fget(2, 'hp'), ST[b.fget(2, 'state')], round(b.fget(2, 'y'))))
            if ST[b.fget(0, 'state')] == 'HITSTUN' and b.fget(0, 'state_t') == 0: log['p1_hit'] += 1
            if rec['setup'].get('extra'): log['extra_states'].add(ST[b.fget(3, 'state')])
            if t % 8 == 0 and k == '-' and len(shots) < 24:   # (a picture runs a frame: never inside a held key)
                p = os.path.join(OUT, f'{rid}_{t:04d}.png'); b.screenshot(p); shots.append(p)
    log['extra_states'] = sorted(log['extra_states'])
    res[rid] = log
    print(rid, 'links', [m for _, m in log['links']], 'hits', [(d, s, y) for _, d, s, y in log['hits']], 'P1 hit', log['p1_hit'],
          'extra', log['extra_states'], flush=True)
    ims = [Image.open(p) for p in shots]
    if ims:
        w, h = ims[0].size; cols = 6; S = Image.new('RGB', (cols * w, ((len(ims) + cols - 1) // cols) * (h + 14)), 'white'); d = ImageDraw.Draw(S)
        for i, (im, p) in enumerate(zip(ims, shots)):
            x, y = i % cols * w, i // cols * (h + 14); S.paste(im, (x, y + 14)); d.text((x + 2, y + 1), os.path.basename(p)[:-4], fill='black')
        S.save(os.path.join(OUT, f'sheet_{rid}.png'))
        for p in shots: os.remove(p)
json.dump(res, open(os.path.join(OUT, 'scenarios1a.json'), 'w'), indent=1)
