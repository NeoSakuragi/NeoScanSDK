#!/usr/bin/env python3
"""Side-by-side sheet: Moriya's moves in The Last Blade 2 (our emulator, vs.state, P2 kept away) and in the brawler (the
Lab shell + his pack, our emulator, the piece fired from a slot override against a training dummy), every STEP-th frame
from the move's first frame, cropped around him.
    python3 sbs_lb2.py game OUT          (one core per process: the game side)
    python3 sbs_lb2.py brawler OUT       (the brawler side)
    python3 sbs_lb2.py sheet OUT         -> OUT/sbs.png"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MOVES = [('236B', '3:D,3:DR,3:R,3:b', 'Ittou Tsukikage B'), ('623A', '3:R,3:D,3:DR,3:a', 'Ittou Shingetsu'),
         ('214B', '3:D,3:DL,3:L,3:b', 'Ittou Oboro (mid)')]
STEP, N = 4, 12

def game(out):
    import play_lb2 as PL
    from PIL import Image
    os.makedirs(out, exist_ok=True)
    for inp, seq, _ in MOVES:
        g = PL.core(); g.load_state(f'{PL.STA}/vs.state'); g.frame = 0
        keys = PL.expand('2:-,' + seq + ',140:-')
        start = None
        for f, k in enumerate(keys):
            g.pad = [set(k), set()]
            g.w(PL.P2 + 0x80, 2, (g.r(PL.P1 + 0x80) + 250) & 0xFFFF)
            if start is None and g.r(PL.P1 + 0x72) not in range(9):
                start = f
            if start is not None and (f - start) % STEP == 0 and (f - start) // STEP < N:
                g.screenshot(f'{out}/game_{inp}_{(f - start) // STEP:02d}.png')
            else: g.core.retro_run(); g.frame += 1

def brawler(out):
    sys.path.insert(0, os.path.join(HERE, '..', 'brawler', 'chainlab')); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
    import harness
    from labdrive import Lab
    import lb2_lab_proof as LP
    game = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')); harness.GAME = game
    L = Lab(rom='/data/tmp/lb2lab/shell_moriya.neo', game=game, build='build_shell'); b = L.b
    G = json.load(open(os.path.join(game, 'game.json'))); fid = len(G['roster'])
    CLJ = json.load(open(os.path.join(game, 'build_pack_moriya', 'chainlab.json')))
    pool = [p['input'] for p in next(x for x in CLJ['fighters'] if x['name'] == 'slot')['pool']]
    lf = b.syms['lab_fields']
    names = [r['name'] for r in G['roster']]
    L.start(fid, names.index('ryo')); b.run(30); base = b.save()
    os.makedirs(out, exist_ok=True)
    for inp, seq, _ in MOVES:
        b.load(base)
        blob = LP.encode({'slots': {'sp_c': [LP.LE_SPEC | pool.index(inp)]}, 'fighter': fid})
        L.poke(lf['tblob'], blob); L.poke(lf['lstat'], [0]); L.poke(lf['tnow'], [1]); L.poke(0, b'LAB1'); L.poke(5, [fid]); L.poke(7, [6])
        b.run(3)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 90
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + 250, z=30); b.fset(2, 'facing', 0xFF); b.run(2)
        started = None
        for i in range(160):
            if started is None and b.states[b.fget(0, 'state')] == 'SPECIAL': started = i
            if started is not None and (i - started) % STEP == 0 and (i - started) // STEP < N:
                b.screenshot(f'{out}/brawler_{inp}_{(i - started) // STEP:02d}.png')
            else: b.run(1, p1='c' if i < 2 else '')

def sheet(out):
    from PIL import Image, ImageDraw
    rows = []
    for inp, _, name in MOVES:
        for side in ('game', 'brawler'):
            ims = []
            for k in range(N):
                p = f'{out}/{side}_{inp}_{k:02d}.png'
                if not os.path.exists(p): continue
                im = Image.open(p).convert('RGB')
                ims.append(im.crop((0, 40, 240, 224)) if side == 'game' else im.crop((0, 40, 240, 224)))
            if not ims: continue
            w, h = ims[0].size
            row = Image.new('RGB', (w * len(ims) // 2 + 120, h // 2), 'white')
            d = ImageDraw.Draw(row); d.text((4, 4), f'{inp}\n{name}\n{side}', fill='black')
            for k, im in enumerate(ims): row.paste(im.resize((w // 2, h // 2)), (120 + k * w // 2, 0))
            rows.append(row)
    W = max(r.size[0] for r in rows); H = sum(r.size[1] + 4 for r in rows)
    sh = Image.new('RGB', (W, H), 'white'); y = 0
    for r in rows: sh.paste(r, (0, y)); y += r.size[1] + 4
    sh.save(f'{out}/sbs.png'); print(f'{out}/sbs.png', sh.size)

if __name__ == '__main__':
    {'game': game, 'brawler': brawler, 'sheet': sheet}[sys.argv[1]](sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/lastbld2/sbs')
