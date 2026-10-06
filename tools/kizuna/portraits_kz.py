#!/usr/bin/env python3
"""Kim Young Mok's portraits in Kizuna Encounter, read from the screens that show them (VRAM + palette RAM dumped by
our emulator, emu/neogeo_sdl --capture VRAMDUMP / PALDUMP): every portrait is made of sprites. Per portrait: the
sprite slots inside its rectangle with a cell in its palettes, a PNG in its own colours (transparent where no sprite
pixel), a JSON with the raw data (tiles, attributes, palettes), into /data/neogeo_dict/portraits/ (kizuna_kim_<kind>
.png / .json), and the HUD-size square (28x28, the fight HUD face) make_hud.py takes as kizuna_kim_square.png.

    python3 portraits_kz.py [DUMPDIR]          (default /data/tmp/kizuna/portraits: the boot capture is made there)
    python3 portraits_kz.py --char NAME        any fighter: its slot of the grid (GRID; P1's cursor walked there:
                                               down for the bottom row, then right), its face = the $Fx palette most of
                                               the face's cells use, its big art = palettes $A0-$AF; the HUD face from
                                               its vs state. Shishioh is "KING LION" on the grid (獅子王); Jyazu (the
                                               boss, character 12) has no slot: HUD face only.

Screens (2026-10-05): the tag team select with P1's cursor moved down onto Kim (frame 1395 of the boot below; the
screen names him "KIM YOUNG MOK" under his big art): 'select' his face in the bottom row of the grid, 'big' his
standing art with the name; 'hud' the fight HUD face (the vs state, P1 top left)."""
import json, os, sys, subprocess, numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kz, cap_kz, fighters_kz as FK

OUT = '/data/neogeo_dict/portraits'
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
SEL = 1395
# kind: (source, rectangle x0, y0, x1, y1 in VRAM x / screen y, palettes kept (None: all), palettes dropped, where)
PORTRAITS = {'select': ('sel', 40, 168, 88, 210, {0xF0}, set(), "tag team select grid, bottom row first face (palette $F0)"),
             'big': ('sel', 40, 50, 130, 190, {0xA0, 0xA1}, set(), "tag team select: his standing art under P1's cursor (palettes $A0, $A1)")}
GRID = {'rosa': (0, 0), 'gozu': (0, 1), 'shishioh': (0, 2), 'chung': (0, 3), 'hayate': (0, 4),     # (row, column)
        'kim': (1, 0), 'mezu': (1, 1), 'gordon': (1, 2), 'joker': (1, 3), 'eagle': (1, 4)}            # [meas] 2026-10-06
NAME, VS_STATE = 'kim', cap_kz.VS
HUD = (8, 16, 32, 40)                 # the fight HUD face (P1, top left): fix-layer tiles, taken from the screenshot (304 px wide)

def rle(lane):
    runs = []
    for x in lane:
        if runs and runs[-1][1] == x: runs[-1][0] += 1
        else: runs.append([1, x])
    return ','.join(f'{n}:{x}' for n, x in runs)

def boot(d):
    """coins 600 / 650, starts 720 / 760, A every 20 frames 801-1099 (skips the how-to-play screens), P1 down at 1300
    (the cursor onto Kim, bottom left)"""
    n = SEL + 2; p1, p2 = ['-'] * n, ['-'] * n
    for f in range(600, 606): p1[f] = 'o'
    for f in range(650, 656): p2[f] = 'o'
    for f in range(720, 726): p1[f] = 's'
    for f in range(760, 766): p2[f] = 's'
    for f in range(801, 1100):
        if f % 20 < 3: p1[f] = p2[f] = 'a'
    r, c = GRID.get(NAME, (None, 0))
    t = 1250
    if r is None: n = 0                               # no slot: the HUD face only
    if r:
        for f in range(t, t + 6): p1[f] = 'D'
        t += 20
    for k in range(c):
        for f in range(t, t + 6): p1[f] = 'R'
        t += 20
    if (r, c) == (0, 0):                              # the first slot: its art shows grey until the cursor moves onto
        for f in range(t, t + 6): p1[f] = 'R'         # it (Rosa): right and back
        for f in range(t + 20, t + 26): p1[f] = 'L'
    os.makedirs(d, exist_ok=True)
    env = dict(os.environ, SEQ=rle(p1), SEQ2=rle(p2), OUT=f'{d}/boot.txt', VRAMDUMP=f'{SEL}:{d}/vram_sel.bin',
               PALDUMP=f'{SEL}:{d}/pal_sel.bin', SNAPS=str(SEL), SNAPDIR=d)
    if n: subprocess.run([NGSDL, kz.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    env = dict(os.environ, SEQ='4:-', OUT=f'{d}/fight.txt', LOAD=VS_STATE, VRAMDUMP=f'2:{d}/vram_fight.bin',
               PALDUMP=f'2:{d}/pal_fight.bin', SNAPS='2', SNAPDIR=d)
    subprocess.run([NGSDL, kz.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)

def setup(name):
    """another fighter: its grid slot's rectangles; face palette and big-art palettes found in main"""
    global NAME, VS_STATE
    NAME, VS_STATE = name, FK.state(name)
    if name == 'kim' or name not in GRID: PORTRAITS.clear() if name not in GRID else None; return
    r, c = GRID[name]
    PORTRAITS['select'] = ('sel', 40 + 48 * c, 168 if r else 12, 88 + 48 * c, 210 if r else 54, 'face', set(),
                           f"tag team select grid, row {r} column {c}")
    PORTRAITS['big'] = ('sel', 10, 40, 170, 200, set(range(0xA0, 0xB0)), set(), "tag team select: its standing art under P1's cursor")

def main(d):
    if not os.path.exists(f'{d}/vram_fight.bin'): boot(d)
    os.makedirs(OUT, exist_ok=True)
    for kind, (src, x0, y0, x1, y1, keep, drop, where) in PORTRAITS.items():
        if keep == 'face':                           # the $Fx palette most cells in the face's rectangle use
            from collections import Counter
            v0 = list(kz.vram_words(f'{d}/vram_{src}.bin')); cnt = Counter()
            for s_, sx, top, sh, s2 in kz.chains(v0):
                if not sh or s2 & 0xFFF != 0xFFF: continue
                top = top - 512 if top > 300 else top
                for k in range(min(sh, 32)):
                    if v0[s_ * 64 + 2 * k] and x0 <= sx < x1 and y0 <= top + 16 * k < y1 and v0[s_ * 64 + 2 * k + 1] >> 12 == 0xF:
                        cnt[v0[s_ * 64 + 2 * k + 1] >> 8] += 1
            keep = {cnt.most_common(1)[0][0]}
        v = list(kz.vram_words(f'{d}/vram_{src}.bin'))
        pal = kz.pal_bank(f'{d}/pal_{src}.bin', 1)
        if not any(pal[16:]): pal = kz.pal_bank(f'{d}/pal_{src}.bin', 0)
        sl = []
        for s, sx, top, sh, s2 in kz.chains(v):
            if not sh or s2 & 0xFFF != 0xFFF: continue
            top = top - 512 if top > 300 else top
            if sx < x1 and sx + 16 > x0 and top < y1 and top + min(sh, 32) * 16 > y0: sl.append((s, sx, top, min(sh, 32)))
        for s, *_ in sl:
            for r in range(32):
                p = v[s * 64 + 2 * r + 1] >> 8
                if (keep is not None and p not in keep) or p in drop: v[s * 64 + 2 * r] = 0; v[s * 64 + 2 * r + 1] &= 0xFF00
        sl = [t for t in sl if any(v[t[0] * 64 + 2 * r] for r in range(t[3]))]
        img, _ = kz.vram_index(v, slots={s for s, *_ in sl})
        img = img[y0:y1, x0:x1]
        rgb = kz.colorize(img, pal)
        rgba = np.dstack([rgb, np.where(img > 0, 255, 0).astype(np.uint8)])
        ys, xs = np.nonzero(img); bx0, by0 = int(xs.min()), int(ys.min())
        rgba = rgba[by0:ys.max() + 1, bx0:xs.max() + 1]; X0, Y0 = x0 + bx0, y0 + by0
        Image.fromarray(rgba, 'RGBA').save(f'{OUT}/kizuna_{NAME}_{kind}.png')
        tiles = [{'slot': s, 'x': int(x - X0), 'y': int(y - Y0),
                  'cells': [[v[s * 64 + 2 * r] | (v[s * 64 + 2 * r + 1] >> 4 & 0xF) << 16, v[s * 64 + 2 * r + 1]] for r in range(rows)]}
                 for s, x, y, rows in sl]
        pals = sorted({c[1] >> 8 for t in tiles for c in t['cells'] if c[0]})
        json.dump({'game': 'kizuna', 'name': NAME, 'kind': kind, 'where': where,
                   'rect': [X0, Y0, X0 + rgba.shape[1], Y0 + rgba.shape[0]], 'size': [rgba.shape[1], rgba.shape[0]],
                   'sprites': tiles, 'palettes': {str(p): list(pal[p * 16:p * 16 + 16]) for p in pals}},
                  open(f'{OUT}/kizuna_{NAME}_{kind}.json', 'w'))
        print(kind, len(sl), 'sprites, palettes', [hex(p) for p in pals], rgba.shape[1], 'x', rgba.shape[0], '->', f'{OUT}/kizuna_{NAME}_{kind}.png')
    Image.open(f'{d}/snap_2.ppm').crop(HUD).save(f'{OUT}/kizuna_{NAME}_hud.png')
    print('hud (fix layer, from the screenshot)', HUD, '->', f'{OUT}/kizuna_{NAME}_hud.png')
    sel = f'{OUT}/kizuna_{NAME}_select.png'
    face = Image.open(sel if 'select' in PORTRAITS else f'{OUT}/kizuna_{NAME}_hud.png').convert('RGBA')
    w, h = face.size; c = min(w, h)
    sq = face.crop(((w - c) // 2, (h - c) // 2, (w - c) // 2 + c, (h - c) // 2 + c)).resize((28, 28), Image.LANCZOS)
    bg = Image.new('RGBA', sq.size, (24, 40, 104, 255)); bg.alpha_composite(sq)
    bg.save(f'{OUT}/kizuna_{NAME}_square.png')

if __name__ == '__main__':
    av = sys.argv[1:]
    if '--char' in av:
        i = av.index('--char'); setup(av[i + 1]); del av[i:i + 2]
        if not av: av = [f'/data/tmp/kizuna/portraits_{NAME}']
    main(av[0] if av else '/data/tmp/kizuna/portraits')
