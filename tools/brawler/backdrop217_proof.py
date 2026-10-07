#!/usr/bin/env python3
"""TODO #217: no screen flash tears. Every backdrop change goes out in vblank (main.c bd_set / vblank_flush), with the
stage's sprites; written mid-frame (before 0.3.5) the frame showed the old colour above the write's line and the new
one below it (Kim's Phoenix strobe: its last frame half red / half white).

    python3 backdrop217_proof.py [OUTDIR]        (default /data/tmp/bd217/out)

Each flash kind played in the Chain Lab next to a dummy, every frame screenshot: Kim's Phoenix (the KOF super flash,
then Kizuna's strobe), Terry's fury (the KOF super flash), Haohmaru's WFT (the super flash, then SS2's big-hit red),
Cheng Fu's SUPER 623 (the super flash, then Double Dragon's red strobe). Per frame and per line, the colour covering
over 70% of the line (the backdrop on a line with no stage); a flash colour = one that covers a whole screen's lines
(>= 120) in some frame of the run. Check: no frame has two flash colours each on >= 4 lines (a torn frame), and every
kind showed its flash (the frames on a flash colour > 0). OUT/backdrop217.json, sheet OUT/backdrop217_<case>.png
(the frames from 2 before the first flash frame to 2 after the last, a torn one framed)."""
import json, os, re, sys
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/bd217/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
CASES = [('kim_phoenix', 'BC_KIM', 'd'), ('terry_fury', 'BC_TERRY', 'd'), ('haohmaru_wft', 'BC_HAOHMARU', 'd'),
         ('cheng_fu_super623', 'BC_CHENG_FU', 'Dd')]
TOP, BOT = 40, 210                                       # the play field's lines (not the HUD / the fix line)

def line_cols(im):
    """per line of the play field: the colour (r, g, b) covering over 70% of it, else None"""
    a = np.asarray(im)
    out = []
    for y in range(TOP, min(BOT, a.shape[0])):
        c = Counter(map(tuple, a[y]))
        col, n = c.most_common(1)[0]
        out.append(col if n * 10 > 7 * a.shape[1] else None)
    return out

def play(b, k, keys, n=420):
    L = b.syms['lab']
    b.pick(k)
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, k); b.w(L + 6, 1, 0); b.w(L + 4, 1, 1)
    b.run(40); b.fset(0, 'meter', 120)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    b.place(dm, x=130); b.place(0, x=70, z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
    ims = []
    p = os.path.join(OUT, '_shot.png')
    for f in range(n):
        if f < 3: b.run(1, p1=keys); continue
        b.screenshot(p); ims.append(Image.open(p).convert('RGB'))
    return ims

def main():
    os.makedirs(OUT, exist_ok=True)
    b = Brawler(game=GAME)
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    res = {}
    for name, bc, keys in CASES:
        ims = play(b, bcs.index(bc), keys)
        lines = [line_cols(im) for im in ims]
        flash = set()
        for ls in lines:
            for col, n in Counter(c for c in ls if c).items():
                if n >= 120: flash.add(col)
        torn, seq, on = [], [], []
        names = {c: chr(ord('A') + i) for i, c in enumerate(sorted(flash))}
        for i, ls in enumerate(lines):
            cnt = Counter(c for c in ls if c in flash)
            big = [c for c, n in cnt.items() if n >= 4]
            if len(big) > 1: torn.append({'frame': i, 'colours': {names[c]: cnt[c] for c in big}})
            full = [c for c, n in cnt.items() if n >= 120]
            seq.append(names[full[0]] if full else ('?' if big else '-'))
            if full: on.append(i)
        res[name] = {'flash_colours': {v: k for k, v in names.items()}, 'flash_frames': len(on),
                     'sequence': ''.join(seq[max(0, on[0] - 2):on[-1] + 3]) if on else '', 'torn': torn,
                     'ok': bool(on) and not torn}
        if on:
            fr = list(range(max(0, on[0] - 2), min(len(ims), on[-1] + 3)))
            W, H, cols = 160, 112, 24
            sh = Image.new('RGB', (W * cols, 16 + (H + 14) * ((len(fr) + cols - 1) // cols)), 'white'); d = ImageDraw.Draw(sh)
            d.text((2, 2), f'TODO #217 {name}: every frame of its flash (a torn one framed)', fill='black')
            tf = {t['frame'] for t in torn}
            for j, f in enumerate(fr):
                x, y = W * (j % cols), 16 + (H + 14) * (j // cols)
                sh.paste(ims[f].resize((W, H)), (x, y))
                if f in tf: d.rectangle([x, y, x + W - 1, y + H - 1], outline='black', width=4)
                d.text((x + 2, y + H + 1), f'{f} {seq[f]}', fill='black')
            sh.save(os.path.join(OUT, f'backdrop217_{name}.png'))
        print(name, json.dumps({k: v for k, v in res[name].items() if k != 'flash_colours'}, default=str))
    res['ok'] = all(r['ok'] for r in res.values())
    json.dump(res, open(os.path.join(OUT, 'backdrop217.json'), 'w'), indent=1, default=str)
    print('ok' if res['ok'] else 'FAIL')

if __name__ == '__main__':
    main()
