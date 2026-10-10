#!/usr/bin/env python3
"""SS2's hit marks in the brawler (export_ss2.hit_marks, 2026-10-10): each SS2 fighter's chain (A pressed through his
route) against the Chain Lab's standing dummy, in two builds (before / after), every frame from the first hit
screenshotted; the hit-spark entities (PROJ) counted per frame -> OUT/slash_<name>.png (rows: before, after) + OUT/slash.json

    python3 slash_proof.py BEFORE.neo AFTER.neo [OUT]       (default OUT /data/tmp/ss2slash)"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
from harness import Brawler
from PIL import Image, ImageDraw
from ss2_proof import lab_req, GAME

NAMES = ['haohmaru', 'genjuro', 'hanzo_ss2']
OUT = sys.argv[3] if len(sys.argv) > 3 else '/data/tmp/ss2slash'

def play(b, name):
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    k = bcs.index('BC_' + name.upper())
    lab_req(b, 1, k, 0); b.run(40)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    b.place(0, x=b.fget(dm, 'x') - (50 if name == 'haohmaru' else 70), z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
    h0 = len(b.hits); t0 = b.frame; shots, fx = [], []
    for f in range(150):
        b.run(1, p1='a' if f % 16 < 2 and f < 64 else '')
        n = sum(1 for i in range(4) if b.pget(i, 'state') == b.states.index('PROJ'))
        fx.append(n)
        p = os.path.join(OUT, '_shot.png'); b.screenshot(p); shots.append(Image.open(p).copy())
    hits = [(h[0] - t0 - 1, h[2], h[3]) for h in b.hits[h0:]]   # (frame index in shots)
    return shots, fx, hits

def main():
    before, after = sys.argv[1], sys.argv[2]
    if len(sys.argv) > 4:                                  # (child: one build, every fighter; the core is one per process)
        tag, rom = sys.argv[4], {'before': before, 'after': after}[sys.argv[4]]
        b = Brawler(rom=rom); out = {}; play(b, NAMES[0])   # (a first run: the first Lab request after the boot shows a black screen)
        for name in NAMES:
            shots, fx, hits = play(b, name)
            for i, im in enumerate(shots): im.save(os.path.join(OUT, f'_{tag}_{name}_{i:03d}.png'))
            out[name] = [fx, hits]
        json.dump(out, open(os.path.join(OUT, f'_{tag}.json'), 'w')); return
    import subprocess
    for tag in ('before', 'after'): subprocess.run([sys.executable, __file__, before, after, OUT, tag], check=True)
    runs = {tag: json.load(open(os.path.join(OUT, f'_{tag}.json'))) for tag in ('before', 'after')}
    res = {}
    for name in NAMES:
        rows = []
        for tag in ('before', 'after'):
            fx, hits = runs[tag][name]
            shots = [Image.open(os.path.join(OUT, f'_{tag}_{name}_{i:03d}.png')) for i in range(len(fx))]
            first = next((i for i, n in enumerate(fx) if n), None)
            res.setdefault(name, {})[tag] = {'hits': hits, 'spark_frames': sum(1 for n in fx if n), 'first_spark': first}
            f0 = (hits[0][0] if hits else 20) - 1
            rows.append((tag, shots[f0:f0 + 14]))
            res[name][tag]['hits'] = [list(h) for h in hits]
        BOX = (40, 60, 280, 224); W, H = BOX[2] - BOX[0], BOX[3] - BOX[1]   # (the fighters' part of the screen, 1:1)
        sheet = Image.new('RGB', (W * 7 + 70, H * 4 + 4), 'white'); d = ImageDraw.Draw(sheet)
        for r, (tag, ims) in enumerate(rows):
            for j, im in enumerate(ims):
                y = (2 * r + j // 7) * H
                if j % 7 == 0: d.text((4, y + 4), f'{tag}\nhit {j - 1:+d}..', fill='black')
                sheet.paste(im.crop(BOX), (70 + (j % 7) * W, y))
        sheet.save(os.path.join(OUT, f'slash_{name}.png'))
        print(name, res[name], flush=True)
    json.dump(res, open(os.path.join(OUT, 'slash.json'), 'w'), indent=1)

if __name__ == '__main__':
    main()
