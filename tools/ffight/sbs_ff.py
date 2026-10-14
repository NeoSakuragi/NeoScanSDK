#!/usr/bin/env python3
"""Side-by-side proof sheets: Final Fight (FBNeo, rec_ff.py --png) over the brawler (our emulator, ff_proof.py --png),
the same scenario, frame by frame from the same moment (the first input; the hold's first frame for the grab cases),
one crop around the fighter every STEP frames. Labels: frame number, FF's animation address / the brawler's state and
move. Black on white, solid borders (e-ink).

    python3 sbs_ff.py [NAME ...]   -> /data/tmp/ffight/sheets/<name>_<scenario>.png"""
import json, os, sys
from PIL import Image, ImageDraw
REC, BRW, OUT = '/data/tmp/ffight/rec', '/data/tmp/ffight/brawler', '/data/tmp/ffight/sheets'
PAIRS = [('walk', 'walk'), ('jumpn', 'jumpn'), ('jumpf', 'jumpf'), ('special', 'special'), ('chain', 'chain'),
         ('chain_back', 'chain_back'), ('grab_knees', 'grab_knees'), ('grab_fwd', 'grab_fwd'), ('grab_back', 'grab_back'),
         ('grab_jumpB', 'grab_up'),
         ('grab_idle', 'grab_idle'), ('grab_walkf', 'grab_walkf'), ('grab_walkb', 'grab_walkb'), ('grab_walkud', 'grab_walkud'),   # the walk
         ('grab_walkdiag', 'grab_walkdiag'), ('grab_walkthrow', 'grab_walkthrow'), ('grab_walkjump', 'grab_walkjump')]   # in the hold
W, H, STEP, NCOL = 160, 176, 3, 12

def ff_start(rows, scen):
    if scen.startswith('grab'): return next(i for i, r in enumerate(rows) if r['P']['st'] == 2)
    return 0

def br_start(rows, scen):
    if scen.startswith('grab'): return next(i for i, r in enumerate(rows) if r['state'] == 'GRAB')
    return 0

def crop(img, cx, feet):
    out = Image.new('RGB', (W, H), 'white')
    box = (cx - W // 2, feet - H + 16, cx + W // 2, feet + 16)
    out.paste(img.crop(box), (0, 0))
    return out

def sheet(name, fs, bs):
    fr = json.load(open(f'{REC}/{name}_{fs}.json'))['rows']; br = json.load(open(f'{BRW}/{name}_{bs}.json'))['rows']
    f0, b0 = ff_start(fr, fs), br_start(br, bs)
    n = min(len(fr) - f0, len(br) - b0)
    ks = list(range(0, n, STEP))[:NCOL * 4]
    rows = (len(ks) + NCOL - 1) // NCOL
    S = Image.new('RGB', (NCOL * (W + 4) + 70, rows * (2 * H + 40)), 'white'); d = ImageDraw.Draw(S)
    for j, k in enumerate(ks):
        c, r = j % NCOL, j // NCOL; x = 70 + c * (W + 4); y = r * (2 * H + 40)
        if c == 0: d.text((4, y + 20), 'FF', fill='black'); d.text((4, y + H + 40), 'brawler', fill='black')
        P = fr[f0 + k]['P']
        im = Image.open(f'{REC}/png/{name}_{fs}/{f0 + k:03d}.png').convert('RGB')
        a = crop(im, P['x'] - P['cam'] - 64, 263 - P['y'] + P.get('camy', 0))
        R_ = br[b0 + k]
        imb = Image.open(f'{BRW}/png/{name}_{bs}/{b0 + k:03d}.png').convert('RGB')
        b = crop(imb, R_['sx'], 206 - int(R_['y']))
        S.paste(a, (x, y + 14)); S.paste(b, (x, y + H + 34))
        d.rectangle([x - 1, y + 13, x + W, y + 14 + H], outline='black'); d.rectangle([x - 1, y + H + 33, x + W, y + H + 34 + H], outline='black')
        d.text((x + 2, y + 1), f"{k} {P['anim']:05X}", fill='black')
        d.text((x + 2, y + H + 21), f"{k} {R_['state'][:6]} {str(R_.get('move', R_['anim']))[:12]}", fill='black')
    os.makedirs(OUT, exist_ok=True)
    p = f'{OUT}/{name}_{fs}.png'; S.save(p); return p

if __name__ == '__main__':
    for n in sys.argv[1:] or ['guy', 'cody', 'haggar']:
        for fs, bs in PAIRS:
            if not (os.path.exists(f'{REC}/{n}_{fs}.json') and os.path.exists(f'{BRW}/{n}_{bs}.json')): continue
            print(sheet(n, fs, bs))
