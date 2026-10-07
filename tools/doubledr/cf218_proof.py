#!/usr/bin/env python3
"""TODO #218: Cheng-Fu's far D chain (DD 22 > 43 > 41: the hop kick after the first move) and his down attack (DD's 8 / 2
+ a button: 124 > 125, step handler 28, the homing leap onto the lying opponent) in the brawler (harness: the game's ROM
on the Geolith core), against Double Dragon itself in our emulator (emu/neogeo_sdl --capture), in a real fight.

    python3 cf218_proof.py [OUTDIR]          (default /data/tmp/cf218/out)

far D   DD: p1_10.state, P1 walked in to 58 px (hit) / P2 poked to x 768 (whiff), D tapped; the brawler: the campaign's first
        wave (AI on), forward + A (the route's far D) at an enemy 58 px in front (hit) / kept 300 px away (whiff).
down    DD: 214 D knocks P2 down DIZZY (its damage accumulator +$FC poked to $3300 before the hit: DD's down attack needs
        the opponent lying dizzy, +$F3 bit 2 in 71-74), then 2 + D held; the whiff = P2's dizzy flag cleared 20 frames
        into the leap (DD: the fall, anim 35). The brawler: 214 (C) knocks the enemy down, down + A as soon as he stands
        (an enemy lying in reach); the whiff = the target poked out of its lying state (S_GETUP) 20 frames into the leap.
Compared, per move: P1's pictures as runs (DD's definition per frame vs the brawler's exported frame = DD's definition),
the heights (airborne frames: DD's RAM y vs the brawler's), the hits and their frames from the move's start (the hit-stops
differ: DD 10-16, the brawler 7), DD's hit spark per hit (type: its 19 frames' definitions + palettes frame by frame vs
the brawler's spark entity, export_dd hit_sparks), the afterimages (DD: character 14 animation 86 objects born; the
brawler: its ghost entities), the victim's pop (DD's 119 heights vs the brawler's) and the abort.
Sheets: sheet_<move>_<label>.png (DD above, the brawler below, every 2nd / 4th frame from the move's start), strip_<move>.png
(every frame from the hit - 1 to + 20: the spark). -> OUTDIR/proof.json"""
import json, math, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import dd, cap_dd, commands_dd as CM, specials_dd as SD, sparks_dd as SK
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/cf218/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
STATE = '/data/neogeo_dict/doubledr/cap/p1_10.state'
P1, P2 = 0x10042A, 0x10052A
FAR = ';'.join(f'{f}:100530=03,100531=00' for f in range(1, 400))   # DD's P2 kept at x 768 (+$06): no contact
DIZZY = ';'.join(f'{f}:100626=33,100627=00' for f in range(1, 50))  # P2 +$FC = $3300: the 214 D's hit dizzies
GAP = 58
LEAP_ABORT = 20                                                     # the whiff: the target up this many frames into the leap

def g(R, a, n=1, signed=False):
    o = a - 0x100000; v = int.from_bytes(R[o:o + n], 'big')
    return v - (1 << 8 * n) if signed and v >> (8 * n - 1) else v

def entry(note): return next(e for e in CM.entries(10) if CM.notation(e) == note and not e['flags'] & 4)

def dd_rows(seq, pokes=None, snaps=None):
    """per frame (RAM after it): P1 anim / step / definition / x / height, P2 anim / height / damage, sparks born (as
    sparks_dd.capture), afterimages born (character 14 animation 86), the backdrop"""
    rows = cap_dd.run(seq, load=STATE, pokes=pokes, vram=True, snaps=snaps)
    out, alive, ghosts = [], set(), set()
    for r in rows:
        R = r['ram']; F = dd.fighter_fields(R, P1); G = dd.fighter_fields(R, P2)
        born, now, objs, gb = [], set(), {}, 0
        for k in range(22):
            b = 0x10062A + 256 * k
            if not R[b - 0x100000] & 0x80 and not R[b - 0x100000] & 1: continue
            if R[b + 0x1B - 0x100000] == 14 and g(R, b + 0x1C, 2) == 86 and R[b - 0x100000] & 1:
                key = (k, g(R, b + 6, 2), g(R, b + 0xA, 2))
                if key not in ghosts: gb += 1
                ghosts.add(key)
            if not R[b - 0x100000] & 0x80 or not 0x523C4 <= g(R, b + 0x7E, 4) <= 0x52700: continue
            t = R[b + 0x53 - 0x100000]; age = g(R, b + 0x50, 2); now.add(k)
            o = [t, bool(R[b + 1 - 0x100000] & 0x20), g(R, b + 6, 4, True) / 65536, g(R, b + 0xA, 4, True) / 65536,
                 g(R, b + 4, 2), R[b + 3 - 0x100000], k]
            objs[k] = o
            if (t < 19 and age == 1) or (t >= 19 and k not in alive): born.append(o)
        alive = now
        out.append({'f': r['f'], 'anim': F['anim'], 'step': F['step'], 'def': F['def_'], 'x': F['x'], 'y': 488 - F['y'],
                    'p2anim': G['anim'], 'p2y': 488 - G['y'], 'dmg': g(R, P2 + 0x26, 2), 'born': born, 'objs': objs,
                    'ghosts_born': gb, 'bd': r['pal'][0x1FFE] << 8 | r['pal'][0x1FFF]})
    return out

def shots(t0, n, step):
    out = {}
    for f in range(t0, t0 + n, step):
        p = f'/data/tmp/dd95/snap_{f}.ppm'
        if os.path.exists(p): out[f] = Image.open(p).convert('RGB'); os.remove(p)
    return out

def runs(seq):
    out = []
    for v in seq:
        if out and out[-1][0] == v: out[-1][1] += 1
        else: out.append([v, 1])
    return out

def spark_life(rows, i, born):
    life = []
    for j in range(i, min(i + 24, len(rows))):
        o = rows[j]['objs'].get(born[6])
        if not o or o[0] != born[0]: break
        life.append([o[4], o[5]])
    return life

def dd_play(move, label):
    """-> record, the DD screens by frame"""
    if move == 'far D':
        pre = '45:L,15:-,' if label == 'whiff' else '30:R,12:-,'
        seq = pre + '3:d,120:-'; t0 = cap_dd.nframes(pre); pokes = FAR if label == 'whiff' else None
        start_anim, end_anims = 22, (0, 1, 2, 3)
    else:                                               # 214 D (dizzies, knocks down), 131 frames, then 2 + D
        pre = '30:R,12:-,' + SD.inputs(entry('214+ABCD'), 'd') + ',131:-,6:D,'
        seq = pre + '3:Dd,200:-'; t0 = cap_dd.nframes(pre) - 8; pokes = DIZZY
        if label == 'whiff':                            # P2's dizzy flag cleared from 20 frames into the leap on (the
            leap = t0 + 8 + 10                          # leap starts 10 frames into 124: model_dd)
            pokes += ';' + ';'.join(f'{f}:10061D=80' for f in range(leap + LEAP_ABORT, leap + 200))
        start_anim, end_anims = 124, (0, 1, 2, 3)
    every = 1
    rows = dd_rows(seq, pokes, snaps=','.join(str(f) for f in range(t0, t0 + 200, every)))
    sc = shots(t0, 200, every)
    s = next(i for i, r in enumerate(rows) if r['anim'] == start_anim and i >= t0 - 2)
    e = next((i for i in range(s + 1, len(rows)) if rows[i]['anim'] in end_anims), len(rows))
    rec = {'frames': e - s, 'anims': [a for a, _ in runs([r['anim'] for r in rows[s:e]])],
           'pictures': runs([str(r['def']) for r in rows[s:e]]), 'heights': [r['y'] for r in rows[s:e]],
           'travel': abs(rows[e - 1]['x'] - rows[s]['x']), 'ghosts': sum(r['ghosts_born'] for r in rows[s:e]),
           'hits': [], 'red_frames': sum(1 for r in rows[s:e] if r['bd'] == SK.FLASH_COL)}
    for i in range(s, min(e + 10, len(rows))):
        if rows[i]['dmg'] != rows[i - 1]['dmg']:
            born = rows[i]['born'][0] if rows[i]['born'] else None
            rec['hits'].append({'at': i - s, 'anim': [rows[i]['anim'], rows[i]['step']], 'damage': rows[i]['dmg'] - rows[i - 1]['dmg'],
                                'spark': born[0] if born else None, 'life': spark_life(rows, i, born) if born else [],
                                'victim_anims': [a for a, _ in runs([r['p2anim'] for r in rows[i:i + 60]])]})
    if move == 'down' and rec['hits']:                  # the victim's pop: its heights from the hit's next frame on
        i = s + rec['hits'][0]['at']
        k = next(j for j in range(i, len(rows)) if rows[j]['p2y'] > 0)
        rec['victim_pop'] = [rows[j]['p2y'] for j in range(k, k + 22)]
    rec['sparks'] = sum(len(r['born']) for r in rows[s:e])
    return rec, {f - rows[s]['f']: im for f, im in sc.items()}

def bank():
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_doubledr_cheng_fu', 'kof95_export.json')))['characters']['cheng_fu']
    return ex

def br_play(b, start, move, label, ex, ba):
    """the brawler in the campaign's first wave (AI on), its picture / height / hits / sparks / ghosts per frame"""
    sparks = {fi for h in ex['hit_sparks'] for fi in (r[0] for r in h['rows'])}
    b.load(start); b.run(30)
    en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
    e = en[0]; cam = b.r(b.syms['cam_x'], 2)
    gap = 300 if (label == 'whiff' and move == 'far D') else GAP
    b.place(0, x=cam + 60, z=b.fget(e, 'z')); b.place(e, x=cam + 60 + gap); b.fset(0, 'facing', 1); b.fset(e, 'hp', 90)
    for i in en[1:]: b.place(i, x=cam + 600)
    st = lambda i: b.states[b.fget(i, 'state')]
    if move == 'down':                                  # 214 (C) knocks it down, then down + A as soon as he can act
        b.run(3, p1='c')
        for _ in range(200):
            for i in en[1:]: b.place(i, x=b.fget(0, 'x') + 400)
            if st(e) == 'DOWN' and st(0) in ('IDLE', 'WALK'): break
            b.run(1)
        keys = 'Da'
    else: keys = 'Ra'
    h0 = len(b.hits); rows = []; leap = None
    for f in range(200):
        kk = keys if f < 3 else ''
        if label == 'whiff' and move == 'far D':
            for i in en: b.place(i, x=b.fget(0, 'x') + 300)
        else:
            for i in en[1:]: b.place(i, x=b.fget(0, 'x') + 400)
        if move == 'down' and label == 'whiff' and leap is not None and f == leap + LEAP_ABORT and st(e) == 'DOWN':
            b.fset(e, 'state', b.states.index('GETUP'))  # (its target up: the special ends, he falls)
        b.pad = [set(kk), set()]
        p = os.path.join(OUT, '_shot.png'); b.screenshot(p); im = Image.open(p).convert('RGB')
        s0 = st(0); a = b.fget(0, 'anim'); stp = b.fget(0, 'step'); fo = b.fget(0, 'frame_ovr')
        if fo != 0xFFFF: fr = fo
        else:
            mv = ba[a] if a < len(ba) else None
            an = ex['anims'].get(mv) if mv else None
            fr = an['steps'][stp]['frame'] if an and stp < len(an['steps']) else None
        if move == 'down' and leap is None and s0 == 'SPECIAL' and b.fget(0, 'y') > 0: leap = f
        pj = []
        for k in range(8):
            if b.states[b.pget(k, 'state')] != 'PROJ': continue
            pj.append((k, b.pget(k, 'frame_ovr'), b.pget(k, 'state_t')))
        rows.append({'f': f, 'frame': b.frame, 'state': s0, 'spec': b.fget(0, 'spec_id'), 'pic': ex['frames'][fr]['record'] if fr is not None and fr < len(ex['frames']) else None,
                     'y': b.fget(0, 'y'), 'x': b.fget(0, 'x'), 'vy': b.fget(e, 'y'), 'vstate': st(e), 'pj': pj, 'im': im})
    s = next(i for i, r in enumerate(rows) if r['state'] in ('ATTACK', 'SPECIAL'))
    en_ = next((i for i in range(s + 1, len(rows)) if rows[i]['state'] in ('IDLE', 'WALK')), len(rows))
    hits = [h for h in b.hits[h0:] if h[1] == e]
    rec = {'frames': en_ - s, 'pictures': runs([r['pic'] for r in rows[s:en_]]), 'heights': [round(r['y'], 2) for r in rows[s:en_]],
           'travel': round(abs(rows[en_ - 1]['x'] - rows[s]['x']), 2), 'hits': [], 'states': [x for x, _ in runs([r['state'] for r in rows[s:en_]])]}
    born = []                                           # projectile entities born (a spark or an afterimage)
    for j in range(s, en_ + 1 if en_ < len(rows) else en_):
        prev = {k: (fo, t) for k, fo, t in rows[j - 1]['pj']} if j else {}
        for k, fo, t in rows[j]['pj']:
            if k not in prev or t < prev[k][1]: born.append((j, k, fo))
    rec['ghosts'] = sum(1 for _, _, fo in born if fo not in sparks)
    rec['sparks'] = sum(1 for _, _, fo in born if fo in sparks)
    for h in hits:
        i = next((j for j, r in enumerate(rows) if r['frame'] == h[0]), None)
        if i is None: continue
        sp = next(((j, k, fo) for j, k, fo in born if fo in sparks and j >= i - 1), None)
        life = []; lag = 0
        if sp:
            for j in range(sp[0], min(sp[0] + 40, len(rows))):
                q = next((x for x in rows[j]['pj'] if x[0] == sp[1]), None)
                if not q or q[2] < len(life) - 1: break
                if q[2] == len(life) - 1: lag += 1; continue
                fr_ = ex['frames'][q[1]]['layers'][0] if q[1] < len(ex['frames']) else None
                life.append([fr_[0], fr_[3]] if fr_ else None)
        rec['hits'].append({'at': i - s, 'damage': h[2], 'victim_state': h[3], 'life': life, 'lag_frames': lag})
    if move == 'down' and hits:
        i = next(j for j, r in enumerate(rows) if r['frame'] == hits[0][0])
        k = next((j for j in range(i, len(rows)) if rows[j]['vy'] > 0), None)
        rec['victim_pop'] = [round(rows[j]['vy'], 2) for j in range(k, min(k + 22, len(rows)))] if k else []
        rec['victim_states'] = [x for x, _ in runs([r['vstate'] for r in rows[i:]])]
    return rec, {r['f'] - rows[s]['f']: r['im'] for r in rows}

def sheet(name, ddim, brim, n, every, info):
    C_, W_, H_ = 12, 160, 112
    cells = list(range(-every, n, every)); nch = (len(cells) + C_ - 1) // C_
    sh = Image.new('RGB', (60 + W_ * C_, (2 * H_ + 18) * nch + 30), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 2), f'TODO #218 Cheng-Fu {name}: every {every} frames from the move\'s first frame; top Double Dragon, bottom the brawler (real fight). {info}', fill='black')
    for i, t in enumerate(cells):
        y0 = 30 + (2 * H_ + 18) * (i // C_); x0 = 60 + W_ * (i % C_)
        if i % C_ == 0: d.text((4, y0 + 50), 'DD', fill='black'); d.text((4, y0 + H_ + 50), 'brawler', fill='black')
        if t in ddim: sh.paste(ddim[t].resize((W_, H_)), (x0, y0))
        if t in brim: sh.paste(brim[t].resize((W_, H_)), (x0, y0 + H_ + 2))
        d.text((x0 + 2, y0 + 2 * H_ + 4), f'{t:+d}', fill='black')
    sh.save(os.path.join(OUT, 'sheet_' + re.sub(r'[^A-Za-z0-9]+', '_', name) + '.png'))

def strip(name, ddim, brim, dd_at, br_at):
    W, H = 160, 112; cols = 22
    sh = Image.new('RGB', (W * cols, 2 * H + 32), 'white'); d = ImageDraw.Draw(sh)
    d.text((2, 2), f'TODO #218 {name}: every frame from the hit - 1 (top Double Dragon, bottom the brawler): the spark', fill='black')
    for c, k in enumerate(range(-1, 21)):
        if dd_at + k in ddim: sh.paste(ddim[dd_at + k].resize((W, H)), (W * c, 16))
        if br_at + k in brim: sh.paste(brim[br_at + k].resize((W, H)), (W * c, 16 + H))
        d.text((W * c + 2, 18 + 2 * H), f'{k:+d}', fill='black')
    sh.save(os.path.join(OUT, 'strip_' + re.sub(r'[^A-Za-z0-9]+', '_', name) + '.png'))

def align(ddp, brp):
    """the two picture runs from the move's first DD picture (the brawler's start frame still shows the picture before:
    its ROM special's program runs from the next frame), the first run's length left out (DD's RAM after a frame = the
    state the next frame draws: compare_dd's convention) -> (DD frames, brawler frames) as flat lists"""
    while brp and brp[0][0] != ddp[0][0]: brp = brp[1:]
    a = [p for p, k in ddp[1:] for _ in range(k)]; b = [p for p, k in brp[1:] for _ in range(k)]
    return a, b

def check(move, label, ddr, br):
    why = []
    a, b_ = align(ddr['pictures'], br['pictures'])
    n = (ddr['hits'][0]['at'] - ddr['pictures'][0][1]) if ddr['hits'] else len(a)   # (up to the first hit: the hit-stops differ)
    if move == 'down' and label == 'whiff':             # (up to the abort: then DD's fall 35, the brawler's jump fall)
        leap = {str(st['def_']) for st in dd.steps(10, 124)[1]}
        n = next((i for i, p in enumerate(a) if p not in leap), len(a))
    if a[:n] != b_[:n] or (label == 'whiff' and move == 'far D' and a != b_):
        why.append(f'pictures DD {runs(a[:n])} brawler {runs(b_[:n])}')
    if move == 'down' and label == 'hit':               # the leap, its afterimages, the victim's pop (DD: whole px, the
        if ddr['ghosts'] != br['ghosts']: why.append(f'afterimages DD {ddr["ghosts"]} brawler {br["ghosts"]}')   # RAM's
        hd = [h for h in ddr['heights'] if h > 0]; hb = [math.ceil(h) for h in br['heights'] if h > 0]   # 488 - int y)
        if len(hd) != len(hb) or any(abs(x - y) > 1 for x, y in zip(hd, hb)): why.append(f'leap heights DD {hd} brawler {hb}')
        k = ddr['victim_pop'].index(0) + 1 if 0 in ddr['victim_pop'] else len(ddr['victim_pop'])   # (to its landing:
        vb = [math.ceil(h) for h in br.get('victim_pop', [])][:k]                   # then DD's 71 bounce, the brawler's own)
        if ddr['victim_pop'][:k] != vb: why.append(f'victim pop DD {ddr["victim_pop"][:k]} brawler {vb}')
    if move == 'far D' and label == 'whiff':
        hd = [h for h in ddr['heights'] if h > 0]; hb = [h for h in br['heights'] if h > 0]   # (DD whole px, the
        if len(hd) != len(hb) or any(abs(x - y) > 1 for x, y in zip(hd, hb)):                 # brawler's hy = the
            why.append(f'hop heights DD {hd} brawler {hb}')                                   # model's rounded)
    if len(ddr['hits']) != len(br['hits']): why.append(f'hits DD {len(ddr["hits"])} brawler {len(br["hits"])}')
    for hd, hb in zip(ddr['hits'], br['hits']):
        if hd['life'] != hb['life']: why.append(f'spark DD {hd["life"][:2]}.. brawler {hb["life"][:2]}..')
    if label == 'whiff' and (br['hits'] or ddr['hits'] or br['sparks'] or ddr['sparks']): why.append('a whiff hit')
    if move == 'down' and label == 'whiff':             # the abort: both fall at the frame the target gets up (DD: 35)
        if 35 not in ddr['anims'] or 'AIR' not in br['states']: why.append('no fall after the abort')
    return why

def main():
    os.makedirs(OUT, exist_ok=True)
    b = Brawler(game=GAME)
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    ba = [x.strip()[3:].lower() for x in re.search(r'enum \{ (BA_IDLE[^}]*)\}', hdr).group(1).split(',')]
    ba = [x.split('=')[0].strip() for x in ba]
    ex = bank()
    b.pick(bcs.index('BC_CHENG_FU')); b.run(200); start = b.save()
    res = {}
    for move in ('far D', 'down'):
        for label in ('hit', 'whiff'):
            ddr, ddim = dd_play(move, label)
            br, brim = br_play(b, start, move, label, ex, ba)
            why = check(move, label, ddr, br)
            res[f'{move} {label}'] = {'ok': not why, 'why': why, 'dd': ddr, 'brawler': br}
            every = 2 if move == 'far D' else 4
            sheet(f'{move} {label}', ddim, brim, max(ddr['frames'], br['frames']) + 8, every,
                  f"DD {len(ddr['hits'])} hits {ddr['frames']} f | brawler {len(br['hits'])} hits {br['frames']} f")
            if label == 'hit':
                for k, (hd, hb) in enumerate(zip(ddr['hits'], br['hits'])):
                    strip(f'{move} hit {k + 1}', ddim, brim, hd['at'], hb['at'])
            print(f'{move:6s} {label:5s} {"ok" if not why else "FAIL"} DD {ddr["frames"]} f {ddr["anims"]} hits {[(h["at"], h["spark"]) for h in ddr["hits"]]} '
                  f'ghosts {ddr["ghosts"]} | brawler {br["frames"]} f {br["states"]} hits {[(h["at"], h["victim_state"]) for h in br["hits"]]} ghosts {br["ghosts"]} {why[:3]}', flush=True)
            json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1, default=str)
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    bad = [k for k, v in res.items() if not v['ok']]
    print('ALL OK' if not bad else f'FAIL {bad}')

if __name__ == '__main__':
    main()
