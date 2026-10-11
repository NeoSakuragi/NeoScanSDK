#!/usr/bin/env python3
"""The staff roll's smooth scroll (note 20261006-173249-5d29; main.c "the ending" EN_STAFF, tools/brawler/staff_roll.py),
in our emulator (harness.py, BRAWLER_CORE, mvs-mvs, a fresh save): ending_proof's recipe (stage 5, FIGHTER kills the
boss, no input) to the STAFF ROLL, then every frame of it as a picture. Checks:
  1. motion: each frame = the previous one moved up by d px (the whole picture, rows entering at the bottom aside), d
     in {0, 1}; never more (no 8 px jump), never a mismatch (no tearing, no flicker); the picture's total travel = the
     roll's (END_STAFF_N - 1 + 14) * 8 px; en_px follows the pictures
  2. layout: the pictures at en_px = 8 n vs the fix roll's (0.10.51) at the same row: OLD_DIR's shots (ending_proof of
     the fix build), each matched to its best n (pixels differing by more than 16 a channel: the fix roll's opaque
     near-black cells aside, 0)
Out: OUT/frames/fNNNN.png (every frame), OUT/strip.png (a frame strip: 16 frames, 4 in a row, 2 x zoom on the
credit lines at y 96-160), OUT/proof.json.

    python3 staffroll_proof.py [ROM] [OUT] [FIGHTER] [OLD_DIR]   (default brawler.neo, /data/tmp/staffroll, terry,
                                                                  /data/tmp/ending/terry)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np
from PIL import Image


def main():
    a = sys.argv[1:]
    rom = a[0] if a else os.path.join(HERE, '..', '..', 'examples', 'brawler', 'brawler.neo')
    out = a[1] if len(a) > 1 else '/data/tmp/staffroll'
    name = a[2] if len(a) > 2 else 'terry'
    old = a[3] if len(a) > 3 else '/data/tmp/ending/' + name
    import harness as H, scenario
    b = H.Brawler(rom=rom, options=scenario.SYSTEMS['mvs-mvs']); b.game = H.GAME; Y = b.syms
    scenario.setup(b, {'setup': {'mode': 'stage', 'fighter': name, 'stage': 4, 'wave': 5, 'wait': 150, 'alone': True,
                                 'foe_hp': 1, 'gap': 50}})
    fd = os.path.join(out, 'frames'); os.makedirs(fd, exist_ok=True)
    for f in os.listdir(fd): os.remove(os.path.join(fd, f))
    b.seq('60:-,3:a')
    for _ in range(4000):                                    # to the staff roll
        b.pad = [set(), set()]; b.core.retro_run(); b.frame += 1
        if b.r(Y['mode'], 1) == 4 and b.r(Y['en_st'], 1) == 1: break
    else: sys.exit('no staff roll')
    hdr = open(os.path.join(H.GAME, 'build', 'game_tables.h')).read()
    n_lines = int(hdr.split('#define END_STAFF_N ')[1].split()[0])
    travel = (n_lines - 1 + 14) * 8
    pics, px = [], []
    while b.r(Y['mode'], 1) == 4 and b.r(Y['en_st'], 1) == 1:
        p = os.path.join(fd, 'f%04d.png' % len(pics))
        px.append(b.r(Y['en_px'], 2))                        # what this frame shows (the VRAM queue: a frame late)
        b.screenshot(p); pics.append(np.asarray(Image.open(p).convert('RGB')).astype(np.int16))
    # the last picture: the roll hidden (a tick before the thanks screen), never the roll and the thanks text at once
    last_blank = not pics[-1][:160].any()                   # (the thanks text: fix rows 21 + at y 168)
    pics, px = pics[:-1], px[:-1]
    # 1. motion
    lum = [p.max(axis=2) for p in pics]
    ds, bad = [], []
    for i in range(1, len(lum)):
        a0, a1 = lum[i - 1], lum[i]
        for d in range(0, 17):
            if np.array_equal(a1[:a1.shape[0] - d], a0[d:]): break
        else: d = None
        ds.append(d)
        if d not in (0, 1): bad.append((i, d))
    moved = sum(d for d in ds if d)
    # en_px vs the pictures: the shift between frames = the change of en_px shown
    lag = [g for g in (0, 1, 2) if all(d == px[i - g] - px[i - g - 1] for i, d in enumerate(ds, 1) if i - g - 1 >= 0)]
    px_ok = bool(lag)
    # 2. layout vs the fix roll's shots
    lay = []
    if os.path.isdir(old):
        g = lag[0] if lag else 0                             # en_px as the picture shows it
        at8 = {px[i - g]: pics[i] for i in range(g, len(pics)) if px[i - g] % 8 == 0}
        for f in sorted(os.listdir(old)):
            if 'STAFF_ROLL' not in f: continue
            o = np.asarray(Image.open(os.path.join(old, f)).convert('RGB')).astype(np.int16)
            best = min(((int((np.abs(o - p).max(axis=2) > 16).sum()), q) for q, p in at8.items()))
            lay.append({'old': f, 'en_px': best[1], 'row': best[1] // 8, 'pixels_differing': best[0]})
    # the strip: 16 frames from en_px 200, 4 in a row, rows 96-160 at 2 x
    k0 = next(i for i in range(len(px)) if px[i] >= 200)
    tiles = [Image.fromarray(pics[k].astype(np.uint8)).crop((40, 96, 280, 160)).resize((480, 128), Image.NEAREST)
             for k in range(k0, min(k0 + 16, len(pics)))]
    strip = Image.new('RGB', (480 * 4 + 12, 128 * 4 + 12), (255, 255, 255))
    for i, t in enumerate(tiles): strip.paste(t, ((i % 4) * 484, (i // 4) * 132))
    strip.save(os.path.join(out, 'strip.png'))
    r = {'frames': len(pics), 'en_px': [px[0], px[-1]], 'travel_expected': travel, 'picture_travel': moved,
         'shift_counts': {str(k): ds.count(k) for k in sorted(set(ds), key=str)}, 'bad_frames': bad[:20],
         'en_px_matches_pictures': px_ok, 'picture_lag_frames': lag, 'last_frame_blank': last_blank,
         'layout_vs_fix_roll': lay, 'strip_frames': [k0, k0 + len(tiles) - 1]}
    json.dump(r, open(os.path.join(out, 'proof.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in r.items() if k != 'layout_vs_fix_roll'}))
    for l in lay: print('  ', l)
    ok = not bad and moved == travel - px[0] and px_ok and last_blank and lay and all(l['pixels_differing'] == 0 for l in lay)
    print('ALL OK' if ok else 'FAIL')


if __name__ == '__main__': main()
