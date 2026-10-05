#!/usr/bin/env python3
"""Kim in a crowded scene of the brawler (harness: the game's ROM on our emulator's core): picked on the select screen,
the first wave with 6 enemies walked into (smaller waves cleared), then P1 and the 6 enemies pushed together (x within 120 px) for
240 frames of play (the enemies' AI attacks, P1 presses A every 50 frames; the crowd re-placed every 40). Per frame from VRAM: sprites per
scanline (every sprite with a height, SCB3, and its X on screen: the LSPC's 96 limit), the brawler's own line-guard
count (fighters hidden this frame, main.c guard_hidden); screenshots of the busiest frames.

    python3 crowd_test.py [OUTDIR] [--fury]   (default /data/tmp/kizuna/out/crowd; --fury: P1 fires the Phoenix (C, meter
                                              full) in the crowd at frame 20 and 140: its flames, 13 + 12 sprites)"""
import json, os, sys, numpy as np, ctypes as C
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
from harness import Brawler
FURY = '--fury' in sys.argv
ARGS = [a for a in sys.argv[1:] if a != '--fury']
OUT = ARGS[0] if ARGS else '/data/tmp/kizuna/out/crowd'

def per_line(v):
    cnt = np.zeros(512, int); sy = sh = 0; sx = 0
    for s in range(1, 381):
        scb3 = v[0x8200 + s]
        if scb3 & 0x40: sx = (sx + 16) & 0x1FF
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7
        if not sh: continue
        top = (496 - sy) & 0x1FF
        for y in range(min(sh, 32) * 16): cnt[(top + y) & 0x1FF] += 1
    return cnt[16:240]                                  # the visible lines (224 from 16)

def main():
    os.makedirs(OUT, exist_ok=True)
    b = Brawler(); S = b.syms
    names = json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))['roster']
    k = [r['name'] for r in names].index('kim')
    b.pick(k, unlock=True)
    b.core.retro_get_memory_data.restype = C.c_void_p
    vram = (C.c_uint16 * 65536).from_address(b.core.retro_get_memory_data(101))
    OFF = b.states.index('OFF')
    for t in range(6000):                               # waves walked into; smaller waves cleared (enemies set OFF,
        alive = [i for i in range(2, 8) if b.fget(i, 'state') != OFF]   # the campaign proof's test-only poke) until
        if len(alive) == 6: break                       # one brings 6 enemies at once
        if alive and t % 120 == 119:
            for i in alive: b.fset(i, 'state', OFF)
        b.run(1, p1='R'); b.fset(0, 'hp', 60)
    en = [i for i in range(2, 8) if b.fget(i, 'state') != OFF]
    print('enemies on the stage', len(en), 'stage', b.r(S['camp'], 1) if 'camp' in S else '?')
    cam = b.r(S['cam_x'], 2); x0 = cam + 110; z0 = b.fget(0, 'z'); b.place(0, x=x0, z=z0)
    rows = []; best = []
    for f in range(300 if FURY else 240):
        spec = FURY and b.states[b.fget(0, 'state')] == 'SPECIAL'
        if f % 40 == 0 and not spec:                     # the crowd kept together: re-placed every 40 frames
            b.place(0, x=x0, z=z0)
            for j, i in enumerate(en): b.place(i, x=x0 - 60 + 24 * j + (40 if j >= 2 else 0), z=z0 + (j % 3) * 6)
        if FURY and f in (20, 140): b.fset(0, 'meter', 120); b.fset(0, 'facing', 1)
        if FURY: b.fset(0, 'inv', 2)                     # the crowd's hits don't stop the Phoenix
        b.run(1, p1=('c' if FURY and f % 120 in range(20, 23) else '') or ('a' if f % 50 < 3 and not FURY else ''))
        b.fset(0, 'hp', 60)
        v = list(vram)
        pl = per_line(v)
        hid = b.r(S['guard_hidden'], 1) if 'guard_hidden' in S else None
        shown = [i for i in range(8) if b.fget(i, 'state') != OFF]
        cols = {i: b.fget(i, 'ncols') for i in shown}
        pj = {i: b.pget(i, 'ncols') for i in range(8) if b.pget(i, 'state') != OFF}   # the pool's entities
        rows.append({'f': f, 'max_line': int(pl.max()), 'hidden': hid, 'cols': cols, 'kim_cols': cols.get(0), 'pool_cols': pj,
                     'spr_top': max([b.fget(i, 'spr') + b.fget(i, 'ncols') for i in range(8) if b.fget(i, 'state') != OFF] +
                                    [b.pget(i, 'spr') + b.pget(i, 'ncols') for i in range(8) if b.pget(i, 'state') != OFF])})
        best.append((int(pl.max()), f))
        if f in (60, 120, 180) or (FURY and f % 10 == 0): b.screenshot(os.path.join(OUT, f'crowd_{f}.png'))
    best.sort(reverse=True)
    mx = best[0]
    res = {'frames': len(rows), 'max_sprites_on_a_line': mx[0], 'at_frame': mx[1],
           'frames_with_a_fighter_hidden': sum(1 for r in rows if r['hidden']),
           'kim_cols_max': max(r['kim_cols'] or 0 for r in rows),
           'fighters_cols_max_sum': max(sum(r['cols'].values()) for r in rows),
           'pool_cols_max_sum': max(sum(r['pool_cols'].values()) for r in rows),
           'highest_sprite_used': max(r['spr_top'] for r in rows), 'rows': rows}
    json.dump(res, open(os.path.join(OUT, 'crowd.json'), 'w'))
    print({k: v for k, v in res.items() if k != 'rows'})

if __name__ == '__main__':
    main()
