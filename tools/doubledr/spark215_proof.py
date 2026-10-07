#!/usr/bin/env python3
"""TODO #215: Double Dragon's own hit sparks and super-hit red strobe in the brawler (harness: the game's ROM on the Geolith
core), against Double Dragon itself in our emulator (emu/neogeo_sdl --capture), per move of Cheng-Fu, Billy Lee and
Super Billy, hit and whiff, in a real fight (the campaign's first wave, AI on, an enemy 58 px in front / kept 300 px away).

    python3 spark215_proof.py [OUTDIR]          (default /data/tmp/dd215/out)

Per hit, aligned on it (DD: the frame the victim's damage changes; the brawler: the frame its life drops):
- spark: DD's effect object (definition, palette) frame by frame from the hit vs the brawler's spark entity (its frame's
  definition layer, export_dd hit_sparks) frame by frame: the same sequence on the same frames;
- on screen (the pictures, both games' Geolith screens): the frame the spark first shows (pixels in its palettes'
  colours) and the frames the screen is red (over a third of it $4F00): DD's red 2, 3, 6, 7 frames after its spark shows,
  the brawler's the same (its whole picture shows a frame earlier than DD's, whose vblank draws the previous frame's
  definitions; 'red' in DD's record = its palette RAM, for the record);
- place: the spark's point from the attacker (DD +$E2 / +$E4; the brawler: the entity's x / height at its row 0);
- strip_<move>.png: DD (top) and the brawler (bottom) every frame from the hit - 1 to + 20, the first two hits.
Whiffs: no spark, no red, in both. Colours: the spark frames are exported frames (billy_proof / cheng_proof frames: pen +
palette index = DD's drawing), their palettes 128-131 = DD's palette RAM at the hit (checked here) -> OUTDIR/sparks.json"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler')); sys.path.insert(0, os.path.join(HERE, '..', 'kizuna'))
import dd, cap_dd, commands_dd as CM, specials_dd as SD, sparks_dd as SK, export_dd as E
from harness import Brawler
from kim_proof import lab_req
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/dd215/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
GAP = 58
# roster name -> (bank, DD character, [(move, brawler keys, DD command entry, DD button)])
CASES = {'cheng_fu': ('cheng_fu', 10, [('SUPER 623', 'Dd', 'S 623+ABCD', 'a'), ('SUPER 236', 'd', 'S 236+ABCD', 'a'),
                                       ('236 D', 'Rc', '236+ABCD', 'd'), ('214 D', 'c', '214+ABCD', 'd'), ('623 D', 'Dc', '623+ABCD', 'd')]),
         'billy_lee': ('billy', 0, [('SUPER 236', 'd', 'S 236+ABCD', 'a'), ('623 D', 'Dc', '623+ABCD', 'd'),
                                    ('236 D', 'Rc', '236+ABCD', 'd'), ('214 D', 'c', '214+ABCD', 'd')]),
         'billy_super': ('billy_super', 1, [('623 D', 'Dc', '623+ABCD', 'd'), ('214 D', 'Uc', '214+ABCD', 'd')])}

def entry(ch, note):
    sup = note.startswith('S ')
    return next(e for e in CM.entries(ch) if CM.notation(e) == (note[2:] if sup else note) and bool(e['flags'] & 4) == sup)

def dd_play(ch, note, btn, label):
    e = entry(ch, note); sup = bool(e['flags'] & 4)
    pre = '45:L,15:-,' if label == 'whiff' else '30:R,12:-,'
    seq = pre + SD.inputs(e, btn) + ',200:-'
    t0 = cap_dd.nframes(pre + SD.inputs(e, btn)) - 3
    rows = SK.capture(ch, seq, sup, far=label == 'whiff', snaps=','.join(str(f) for f in range(t0, t0 + 200)))
    shots = {}
    for f in range(t0, t0 + 200):
        p = f'/data/tmp/dd95/snap_{f}.ppm'
        if os.path.exists(p): shots[f] = Image.open(p).convert('RGB'); os.remove(p)
    hits = []
    for i, r in enumerate(rows):
        if not r['hit'] or i < t0 - 2: continue
        born = r['born'][0] if r['born'] else None
        life = []
        if born:
            for j in range(i, min(i + 24, len(rows))):
                o = rows[j]['objs'].get(born[6])
                if not o or o[0] != born[0]: break
                life.append([o[4], o[5]])
        hits.append({'frame': r['f'], 'type': born[0] if born else None, 'life': life,
                     'red': [j - i for j in range(i, min(i + 12, len(rows))) if rows[j]['bd'] == SK.FLASH_COL],
                     'point': [abs(r['e2'] - r['x']), r['y'] - r['e4']],   # (px forward, up from P1's feet)
                     'from_victim': abs(r['e2'] - r['vx']),               # (px toward the attacker from the victim)
                     'screen': visible([shots.get(r['f'] + k) for k in range(-1, 13)])})   # (what the picture shows)
    sparks = sum(len(r['born']) for r in rows)
    reds = sum(1 for r in rows if r['bd'] == SK.FLASH_COL)
    return {'hits': hits, 'sparks': sparks, 'red_frames': reds}, shots

def spark_frames(bank):
    ex = json.load(open(os.path.join(GAME, 'build', f'tmp_doubledr_{bank}', 'kof95_export.json')))['characters'][bank]
    ids = {r[0] for h in ex['hit_sparks'] for r in h['rows']}
    return {fi: (ex['frames'][fi]['layers'][0][0], ex['frames'][fi]['layers'][0][3]) for fi in ids}, ex

SPARK_RGB = None
def spark_px(im):
    """pixels of the screen in the spark palettes' colours (128-131, palette RAM: the same in both games' pictures)"""
    global SPARK_RGB
    import numpy as np
    if SPARK_RGB is None:
        pr = E.palram(); SPARK_RGB = {dd.color(pr[16 * s_ + k]) for s_ in (128, 129, 130, 131) for k in range(1, 16)}
    a = np.asarray(im); m = np.zeros(a.shape[:2], bool)
    for c in SPARK_RGB: m |= (a == c).all(-1)
    return int(m.sum())

def visible(ims):
    """the screens from the hit - 1 to + 12 (None: missing): the first frame the spark shows (its colours' pixels up by
    40 over the hit - 1's), the red ones"""
    n = [spark_px(im) if im is not None else None for im in ims]
    first = next((k - 1 for k, v in enumerate(n) if k and v is not None and n[0] is not None and v > n[0] + 40), None)
    rd = [k - 1 for k, im in enumerate(ims) if im is not None and red(im)]
    return {'spark': first, 'red': rd, 'red_from_spark': [k - first for k in rd] if first is not None else None}

def red(im):
    """the screen red: over a third of it DD's red ($4F00 = (142, 0, 0) on screen)"""
    import numpy as np
    a = np.asarray(im.resize((80, 56))).astype(int)
    return int(((a[..., 0] > 100) & (a[..., 1] < 30) & (a[..., 2] < 30)).sum()) * 3 > 80 * 56

def br_play(b, start, keys, label, sf, pre=None, gap=GAP):
    b.load(start); b.run(30)
    if pre: pre(b)
    en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
    e = en[0]; cam = b.r(b.syms['cam_x'], 2); gap = 300 if label == 'whiff' else gap
    b.place(0, x=cam + 40, z=b.fget(e, 'z')); b.place(e, x=cam + 40 + gap); b.fset(0, 'facing', 1); b.fset(e, 'hp', 90)
    b.fset(0, 'meter', 120)
    for i in en[1:]: b.place(i, x=cam + 600)
    h0 = len(b.hits); rows = []
    for f in range(200):
        b.pad = [set(keys) if f < 3 else set(), set()]          # (screenshot: one frame with these keys, its picture)
        p = os.path.join(OUT, '_shot.png'); b.screenshot(p); im = Image.open(p).convert('RGB')
        if label == 'whiff':
            for i in en: b.place(i, x=b.fget(0, 'x') + 300)
        else:
            for i in en[1:]: b.place(i, x=b.fget(0, 'x') + 400)
        sp = []
        for k in range(8):
            if b.states[b.pget(k, 'state')] != 'PROJ': continue
            fo = b.pget(k, 'frame_ovr')
            if fo in sf: sp.append([sf[fo][0], sf[fo][1], round(b.pget(k, 'x') - b.fget(0, 'x'), 2), round(b.pget(k, 'y') - b.fget(0, 'y'), 2), k, b.pget(k, 'state_t'), round(abs(b.pget(k, 'x') - b.fget(e, 'x')), 2)])
        rows.append({'frame': b.frame, 'im': im, 'red': red(im), 'sparks': sp})
    hits = [h for h in b.hits[h0:] if h[1] == e]
    out = []
    for h in hits:
        i = next((j for j, r in enumerate(rows) if r['frame'] == h[0]), None)
        if i is None: continue
        first = rows[i]['sparks']
        new = [s for s in first if not any(q[4] == s[4] for q in (rows[i - 1]['sparks'] if i else []))]
        life = []
        if new:
            k = new[0][4]
            for j in range(i, min(i + 24, len(rows))):
                s = next((q for q in rows[j]['sparks'] if q[4] == k), None)
                if not s or s[5] != j - i: break           # (its entity taken by the next spark: a new life)
                life.append(s[:2])
        out.append({'frame': h[0], 'screen': visible([rows[i + k]['im'] if 0 <= i + k < len(rows) else None for k in range(-1, 13)]),
                    'life': life, 'point': new[0][2:4] if new else None, 'from_victim': new[0][6] if new else None,
                    'red': [j - i for j in range(i, min(i + 12, len(rows))) if rows[j]['red']]})
    return {'hits': out, 'sparks': sum(1 for j, r in enumerate(rows) for s in r['sparks'] if not j or not any(q[4] == s[4] for q in rows[j - 1]['sparks'])),
            'red_frames': sum(r['red'] for r in rows)}, rows

def strip(name, ddr, ddshots, br, brrows):
    W, H = 160, 112; cells = []
    for hd, hb in list(zip(ddr['hits'], br['hits']))[:2]:
        ib = next(j for j, r in enumerate(brrows) if r['frame'] == hb['frame'])
        for k in range(-1, 21):
            cells.append((k, ddshots.get(hd['frame'] + k), brrows[ib + k]['im'] if 0 <= ib + k < len(brrows) else None))
    if not cells: return
    cols = 22
    sh = Image.new('RGB', (W * cols, (2 * H + 16) * ((len(cells) + cols - 1) // cols) + 16), 'white'); d = ImageDraw.Draw(sh)
    d.text((2, 2), f'TODO #215 {name}: every frame from the hit - 1 (top Double Dragon, bottom the brawler), the first two hits', fill='black')
    for j, (k, a, c) in enumerate(cells):
        x, y = W * (j % cols), 16 + (2 * H + 16) * (j // cols)
        if a: sh.paste(a.resize((W, H)), (x, y))
        if c: sh.paste(c.resize((W, H)), (x, y + H))
        d.text((x + 2, y + 2 * H + 2), f'{k:+d}', fill='black')
    sh.save(os.path.join(OUT, 'strip_' + re.sub(r'[^A-Za-z0-9]+', '_', name) + '.png'))

def main():
    os.makedirs(OUT, exist_ok=True)
    b = Brawler(game=GAME)
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    res = {'palettes': {}, 'moves': {}}
    pr = E.palram()
    for rname, (bank, ch, moves) in CASES.items():
        sf, ex = spark_frames(bank)
        pals = ex['block_palettes'][0]; keys = ex['modes']['palettes']
        res['palettes'][rname] = all(pals[keys.index(str(s))][1:] == pr[16 * s + 1:16 * s + 16] for s in (128, 129, 130, 131))
        if rname == 'billy_super':                         # the form: Billy's transformation (down+D, full meter) first
            b.pick(bcs.index('BC_BILLY_LEE')); b.run(200)
            def pre(b_):
                b_.fset(0, 'meter', 120); b_.run(3, p1='Dd'); b_.run(150)
                assert b_.char_of(0) == bcs.index('BC_BILLY_SUPER'), b_.char_of(0)
        else:
            b.pick(bcs.index('BC_' + rname.upper())); b.run(200); pre = None
        start = b.save()
        for move, keys_, note, btn in moves:
            for label in ('hit', 'whiff'):
                ddr, shots = dd_play(ch, note, btn, label)
                for gap in (GAP, 90, 40, 120):             # (a move that whiffs from 58 px in the brawler: Super
                    br, rows = br_play(b, start, keys_, label, sf, pre, gap)   # Billy's flying kick)
                    if label == 'whiff' or br['hits']: break
                ok = True; why = []; pairs = []; unmatched = []; off = 0
                if label == 'whiff':
                    ok = ddr['sparks'] == br['sparks'] == 0 and ddr['red_frames'] == br['red_frames'] == 0
                else:                                      # each DD hit with the brawler's hit spawning the same
                    left = [h for h in br['hits'] if h['life']]   # spark, in order (a hit the other game's distance
                    for k, hd in enumerate(ddr['hits']):   # adds or loses: reported, not compared)
                        j = next((j for j, hb in enumerate(left) if hb['life'][:1] == hd['life'][:1]), None)
                        if j is None: unmatched.append(f'DD hit {k} ({hd["life"][:1]}): no such hit in the brawler'); continue
                        hb = left[j]; left = left[j + 1:]; pairs.append((hd, hb))
                        if hd['life'] != hb['life']: why.append(f'hit {k}: spark DD {hd["life"]} brawler {hb["life"]}')
                        if k == 0: off = (hd['screen']['spark'] or 0) - (hb['screen']['spark'] or 0)   # (DD's picture: a frame later)
                        if k == 0 and hd['screen']['red_from_spark'] != hb['screen']['red_from_spark'] or \
                                hd['screen']['red'] != [r + off for r in hb['screen']['red']]: why.append(f'hit {k}: on screen DD {hd["screen"]} brawler {hb["screen"]}')
                    ok = not why and bool(pairs)
                br['gap'] = gap; br['matched_hits'] = len(pairs); br['unmatched'] = unmatched   # (Cheng-Fu's 236 D: 5 of DD's 6, TODO #212's reach)
                res['moves'][f'{rname} {move} {label}'] = {'ok': ok, 'why': why, 'dd': ddr, 'brawler': br}
                print(f'{rname:12s} {move:10s} {label:5s} {"ok" if ok else "FAIL"} DD {len(ddr["hits"])} hits {ddr["sparks"]} sparks {ddr["red_frames"]} red | '
                      f'brawler {len(br["hits"])} hits {br["sparks"]} sparks {br["red_frames"]} red, {len(pairs)} matched (gap {gap}) {why[:3]} {unmatched}', flush=True)
                if label == 'hit': strip(f'{rname} {move}', ddr, shots, br, rows)
                json.dump(res, open(os.path.join(OUT, 'sparks.json'), 'w'), indent=1, default=str)
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    bad = [k for k, v in res['moves'].items() if not v['ok']]
    print('palettes = DD:', res['palettes'], '|', 'ALL OK' if not bad else f'FAIL {bad}')

if __name__ == '__main__':
    main()
