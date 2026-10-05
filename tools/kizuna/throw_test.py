#!/usr/bin/env python3
"""Kim's throw (Kizuna's 6C, export_kz.throw) in the brawler: the Chain Lab training (P1 Kim, the dummy Terry), P1 walks
into the dummy (the grab), then forward+A (the throw); states, the dummy's life and a strip of screenshots.
    python3 throw_test.py [OUTDIR]        (default /data/tmp/kizuna/out/throw)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'brawler')); sys.path.insert(0, os.path.join(HERE, '..', 'brawler', 'chainlab'))
from labdrive import Lab
from PIL import Image
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kizuna/out/throw'
os.makedirs(OUT, exist_ok=True)
G = json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))
k = [r['name'] for r in G['roster']].index(sys.argv[2] if len(sys.argv) > 2 else 'kim')
L = Lab(); b = L.b; ST = b.states
L.start(k, 0); b.run(30)
cam = b.r(b.syms['cam_x'], 2); b.place(0, x=cam + 100, z=30); b.place(2, x=cam + 150, z=30); b.fset(0, 'facing', 1); b.run(2)
hp0 = b.fget(2, 'hp'); seen = []; shots = []; h0 = len(b.hits)
for f in range(200):
    keys = 'R' if f < 60 else ('Ra' if f < 63 else '')
    b.run(1, p1=keys)
    s = (ST[b.fget(0, 'state')], ST[b.fget(2, 'state')])
    if not seen or seen[-1] != s: seen.append(s)
    if f >= 60 and f % 6 == 0 and len(shots) < 18:
        p = os.path.join(OUT, f'_s{f}.png'); b.screenshot(p); shots.append(Image.open(p).crop((0, 40, 304, 224)))
print('states (P1, dummy):', seen)
print('dummy life', hp0, '->', b.fget(2, 'hp'), 'hits', b.hits[h0:])
sheet = Image.new('RGB', (304 * 6, 184 * 3), 'white')
for i, im in enumerate(shots): sheet.paste(im, ((i % 6) * 304, (i // 6) * 184))
sheet.save(os.path.join(OUT, 'throw_sheet.png'))
