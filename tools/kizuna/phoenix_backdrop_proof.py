#!/usr/bin/env python3
"""The Phoenix's screen effect (export_kz FOLLOW '6246A' 'backdrop', bspec_t.bd_*, main.c screen_fx) in the brawler next
to Kizuna Encounter playing it (our emulator, the followups_kz.py '6246A_h' recipe): from the launch to the dive
Kizuna hides the stage and its backdrop alternates $7DFF / $4700 every frame ($1FC46, set at $3AC5C, cleared $3ACDE).

    python3 phoenix_backdrop_proof.py [OUTDIR]        (default /data/tmp/kim76/out)

Per frame of each game: the share of the screen in the backdrop's two colours (RGB as the core shows $4700 / $7DFF).
Checks: the brawler strobes as many frames as its export's rows (bd_end - bd_first, frozen rows dropped; since TODO #138
the program switches it, P_SCREEN, bd_first 0xFFFF: as many as Kizuna's run, within 2 frames), white first,
alternating every frame, then the stage back; Kizuna's run length measured the same way. Sheet OUT/phoenix_backdrop.png:
top Kizuna, bottom the brawler, 2 frames before the strobe .. 2 after its start, and around its end."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import numpy as np
import cap_kz as cap, followups_kz as FK
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kim76/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
RED, WHITE = (122, 0, 0), (225, 255, 255)            # $4700, $7DFF on screen

def share(im):
    a = np.asarray(im.convert('RGB')).reshape(-1, 3)
    r = (a == RED).all(1).mean(); w = (a == WHITE).all(1).mean()
    return ('W' if w > 0.3 else 'R' if r > 0.3 else '-'), round(float(max(r, w)), 2)

def runs(seq):
    """[(first index, length)] of the strobe (consecutive W / R frames)"""
    out, i = [], 0
    while i < len(seq):
        if seq[i] == '-': i += 1; continue
        j = i
        while j < len(seq) and seq[j] != '-': j += 1
        out.append((i, j - i)); i = j
    return out

def kizuna(d):
    p2x, seq, pokes = FK.RECIPES['6246A_h']
    n = cap.nframes(seq); pk = []
    for f in range(n):
        s = ([f'108424={p2x >> 8:02X},108425={p2x & 255:02X}'] if f < FK.PIN else []) + ([pokes] if pokes else [])
        if s: pk.append(f'{f}:' + ','.join(s))
    fr = list(range(120, 260))
    os.makedirs(d, exist_ok=True)
    cap.run(seq, '', pokes=';'.join(pk), extra={'SNAPS': ','.join(map(str, fr)), 'SNAPDIR': d}, n=270)
    ims = [Image.open(f'{d}/snap_{f}.ppm').convert('RGB') for f in fr]
    return ims, [share(im) for im in ims]

def brawler(d):
    import re
    b = Brawler()
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    k = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_KIM')
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_kizuna_kim', 'kof95_export.json')))['characters']['kim']
    b.pick(k)
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, k); b.w(L + 6, 1, 0); b.w(L + 4, 1, 1)
    b.run(40); b.fset(0, 'meter', 120)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    b.place(dm, x=130); b.place(0, x=70, z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
    ims, rows, hits = [], [], len(b.hits)
    os.makedirs(d, exist_ok=True)
    for f in range(460):
        if f < 3: b.run(1, p1='d'); continue                # (the fury: D since 2026-10-06)
        p = os.path.join(d, '_b.png'); b.screenshot(p)
        im = Image.open(p).convert('RGB'); ims.append(im)
        st = b.states[b.fget(0, 'state')]
        rows.append((st, b.fget(0, 'spart'), b.fget(0, 'srow') - 1))
    return ims, [share(im) for im in ims], rows, [h for h in b.hits[hits:] if h[1] == dm]

def main():
    os.makedirs(OUT, exist_ok=True)
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_kizuna_kim', 'kof95_export.json')))['characters']['kim']
    sp = next(s for s in ex['specials'] if s['input'] == '6246A')
    kims, ks = kizuna('/data/tmp/kim76/kzsnap')
    bims, bs, rows, hits = brawler('/data/tmp/kim76/bshots')
    kr, br = runs([s for s, _ in ks]), runs([s for s, _ in bs])
    kseq = ''.join(s for s, _ in ks); bseq = ''.join(s for s, _ in bs)
    want = sp['backdrop']['rows'][1] - sp['backdrop']['rows'][0]
    if sp['backdrop']['rows'][0] == 0xFFFF:              # (TODO #138: the program switches it, P_SCREEN: Kizuna's own
        want = kr[0][1] - 2 if kr else 1                 # run, within 2 frames)
    ok_alt = all(c != d for c, d in zip(bseq.strip('-'), bseq.strip('-')[1:]))
    b0 = br[0][0] if br else None
    res = {'kizuna_runs': kr, 'brawler_runs': br, 'export_rows': sp['backdrop'], 'brawler_sequence': bseq.strip('-'), 'kizuna_sequence': kseq.strip('-'),
           'kizuna_first': kseq.strip('-')[:1], 'brawler_first': bseq.strip('-')[:1], 'brawler_alternates': ok_alt,
           'brawler_rows_at_start': rows[b0] if b0 is not None else None, 'brawler_hits': len(hits),
           'brawler_damage': sum(h[2] for h in hits) if hits and isinstance(hits[0][2], int) else None}
    res['ok'] = (len(br) == 1 and br[0][1] >= want and res['brawler_first'] == 'W' == res['kizuna_first'] and ok_alt)
    json.dump(res, open(os.path.join(OUT, 'phoenix_backdrop.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items()}, default=str))
    k0, k1 = kr[0][0], kr[0][0] + kr[0][1]; c0, c1 = br[0][0], br[0][0] + br[0][1]
    pick = lambda a, b: list(range(a - 2, a + 4)) + list(range(b - 3, b + 3))
    kp, bp = pick(k0, k1), pick(c0, c1)
    W, H = 240, 168
    sh = Image.new('RGB', (90 + W * len(kp), 2 * H + 40), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 2), 'Phoenix screen effect: 2 frames before the strobe .. its start, and around its end (every frame)', fill='black')
    d.text((4, 20 + H // 2), 'Kizuna', fill='black'); d.text((4, 30 + H + H // 2), 'brawler', fill='black')
    for i, (a, b_) in enumerate(zip(kp, bp)):
        sh.paste(kims[a].resize((W, H)), (90 + W * i, 16)); sh.paste(bims[b_].resize((W, H)), (90 + W * i, 26 + H))
    sh.save(os.path.join(OUT, 'phoenix_backdrop.png'))
    print('ok' if res['ok'] else 'FAIL')

if __name__ == '__main__':
    main()
