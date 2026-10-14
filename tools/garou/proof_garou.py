#!/usr/bin/env python3
"""Rock (Garou) vs the brawler, the same scenarios on both sides, every frame logged + a picture each (our emulator only:
Garou through cap_garou, the brawler through tools/brawler/harness.py with the Lab shell + his pack, make LAB_PACK=rock
-> examples/brawler/pack-rock.neo; one core per process, so each side is its own run):

  walk (forward held 60 frames), jump / jumpf (straight / forward), the normals A / far C / crouch D (Garou far A / far C /
  crouch D; the brawler's A, the up finisher slot's far C... the brawler plays them as chain / finisher pieces: its first
  A press, C pressed close = its special), every special (the brawler: its slot's input: C, forward / down / up /
  down-forward / up-forward + C, fury D), the throw (Garou close + forward + C; the brawler: walk into the dummy, forward
  + A in the hold)

    python3 proof_garou.py game [SCEN ...]      -> /data/tmp/garou_t3/proof/game_<scen>.json + png/game_<scen>/NNN.png
    python3 proof_garou.py brawler [SCEN ...]   -> /data/tmp/garou_t3/proof/brawler_<scen>.json + png/...
    python3 proof_garou.py sheet [SCEN ...]     -> /data/tmp/garou_t3/sheets/<scen>.png (Garou over the brawler)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = '/data/tmp/garou_t3/proof'; SHEETS = '/data/tmp/garou_t3/sheets'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
D = {'1': 'DL', '2': 'D', '3': 'DR', '4': 'L', '6': 'R', '7': 'UL', '8': 'U', '9': 'UR'}
def gseq(m):
    dirs = [c for c in m if c.isdigit()]; btn = ''.join(c.lower() for c in m if c.isalpha())
    return [D[d] for d in dirs for _ in range(3)] + [(D[dirs[-1]] if dirs else '') + btn] * 4

# scenario -> (Garou: state, keys; the brawler: dummy gap or None, keys (list, then idle), frames)
SCENS = {
    'walk': (('far', ['R'] * 60), (None, ['R'] * 60), 60),
    'jump': (('far', ['U'] * 30), (None, ['b']), 70),
    'jumpf': (('far', ['UR'] * 30), (None, ['Rb'] + ['R'] * 10), 70),
    'A': (('far', ['a'] * 4), (None, ['a']), 30),
    '236A': (('far', gseq('236A')), (None, ['c']), 60),
    '214A': (('far', gseq('214A')), (None, ['Rc']), 60),
    '236C': (('far', gseq('236C')), (None, ['Dc']), 70),
    '28A': (('far', ['D'] * 45 + ['Ua'] * 4), (None, ['Uc']), 75),
    '214B': (('far', gseq('214B')), (None, ['DRc']), 60),
    '28C': (('far', ['D'] * 45 + ['Uc'] * 4), (None, ['URc']), 80),
    '236236A': (('far', gseq('236236A')), (None, ['d']), 120),
    '236236B': (('far', gseq('236236B')), (None, ['Dd']), 100),
    'throw': (('close', ['R'] * 12 + ['Rc'] * 4), (60, 'grab'), 110),
}
CAM = 0x100E4C                                      # Garou's camera x (a5 - $7200 + $4C: $33A6 / $3FD2 [code], a5 = $108000)

def game(scens):
    from cap_garou import Garou, STA
    g = Garou(); os.makedirs(OUT, exist_ok=True)
    for s in scens:
        (st, keys), _, frames = SCENS[s]
        g.load(open(f'{STA}/{st}.state', 'rb').read())
        if s.startswith('236236'): g.w(0x1004BE, 1, 0x80)
        pdir = f'{OUT}/png/game_{s}'; os.makedirs(pdir, exist_ok=True)
        log, started, k = [], None, 0
        while len(log) < frames and k < 400:
            kk = keys[k] if k < len(keys) else ''
            g.pad = [set(kk), set()]
            r0 = g.rows_now()['P1']
            if started is None and (s == 'walk' or r0['anim'] not in (0, 1, 2, 3, 4, 6, 7) or (k + 1 >= len(keys) and s == 'walk')):
                started = k
            if started is not None:
                g.screenshot(f'{pdir}/{len(log):03d}.png')
                r = g.rows_now(); P = r['P1']; V = r['P2']
                log.append({'f': len(log), 'anim': P['anim'], 'step': P['step'], 'fid': P['fid'], 'x': P['x'], 'h': P['h'],
                            'v_anim': V['anim'], 'v_x': V['x'], 'v_h': V['h'], 'v_life': V['raw'][0x8E], 'keys': kk,
                            'sx': P['x'] - g.rs(CAM, 2)})
            else:
                g.core.retro_run(); g.frame += 1
            k += 1
        json.dump({'scenario': s, 'rows': log}, open(f'{OUT}/game_{s}.json', 'w'))
        print('game', s, len(log), 'frames', [f"{a:X}" for a in dict.fromkeys(r['anim'] for r in log)])

def brawler(scens):
    BR = os.path.join(HERE, '..', 'brawler')
    sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR)
    import harness
    from labdrive import Lab
    harness.GAME = GAME
    L = Lab(rom=os.path.join(GAME, 'pack-rock.neo'), game=GAME, build='build_shell'); b = L.b; ST = b.states
    G = json.load(open(os.path.join(GAME, 'game.json')))
    names = [r['name'] for r in G['roster']]; fid = len(names)
    L.start(fid, names.index('terry')); b.run(30); base = b.save()
    os.makedirs(OUT, exist_ok=True)
    for s in scens:
        _, (gap, keys), frames = SCENS[s]
        b.load(base)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + (gap if gap else 400), z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', b.fget(2, 'hp_max'))
        if s == '236236A': b.w(b.syms['prac'] + 4 + 0, 1, 1)          # PS_FURY held full (fighter.h prac_t)
        if s == '236236B': b.w(b.syms['prac'] + 4 + 1, 1, 1)          # PS_MAX: MAX ready
        b.run(2)
        pdir = f'{OUT}/png/brawler_{s}'; os.makedirs(pdir, exist_ok=True)
        log, X0, hp = [], b.fget(0, 'x'), b.fget(2, 'hp')
        for k in range(frames + 60):
            if keys == 'grab':
                gi = next((i for i, r in enumerate(log) if r['state'] == 'GRAB'), None)
                kk = 'R' if gi is None else ('Ra' if k - gi == 6 else '')
            else: kk = keys[k] if k < len(keys) else ''
            b.pad = [set(kk), set()]; b.screenshot(f'{pdir}/{k:03d}.png')
            h = b.fget(2, 'hp')
            log.append({'f': k, 'keys': kk, 'state': ST[b.fget(0, 'state')], 'anim': b.fget(0, 'anim'), 'step': b.fget(0, 'step'),
                        'x': round(b.fget(0, 'x') - X0, 3), 'y': round(b.fget(0, 'y'), 3), 'frame': b.fget(0, 'shown_frame'),
                        'd_state': ST[b.fget(2, 'state')], 'dmg': hp - h if h < hp else 0,
                        'sx': round(b.fget(0, 'x') - b.r(b.syms['cam_x'], 2))})
            hp = h
        json.dump({'scenario': s, 'rows': log}, open(f'{OUT}/brawler_{s}.json', 'w'))
        seq = []
        for r in log:
            k_ = (r['state'], r['anim'])
            if not seq or seq[-1][0] != k_: seq.append([k_, 1])
            else: seq[-1][1] += 1
        print('brawler', s, ' '.join(f'{st}/{a}x{n}' for (st, a), n in seq[:14]), '| dmg', [r['dmg'] for r in log if r['dmg']])

def sheet(scens):
    from PIL import Image, ImageDraw
    W, H, STEP, NCOL = 160, 176, 3, 12
    os.makedirs(SHEETS, exist_ok=True)
    for s in scens:
        try:
            gr = json.load(open(f'{OUT}/game_{s}.json'))['rows']; br = json.load(open(f'{OUT}/brawler_{s}.json'))['rows']
        except FileNotFoundError: continue
        b0 = next((i for i, r in enumerate(br) if r['state'] == ('GRAB' if s == 'throw' else r['state']) and
                   (s in ('walk',) or r['state'] not in ('IDLE', 'WALK'))), 0)
        n = min(len(gr), len(br) - b0)
        ks = list(range(0, n, STEP))[:NCOL * 3]
        rows = (len(ks) + NCOL - 1) // NCOL
        S = Image.new('RGB', (NCOL * (W + 4) + 70, rows * (2 * H + 40)), 'white'); d = ImageDraw.Draw(S)
        for j, k in enumerate(ks):
            c, r = j % NCOL, j // NCOL; x = 70 + c * (W + 4); y = r * (2 * H + 40)
            if c == 0: d.text((4, y + 20), 'Garou', fill='black'); d.text((4, y + H + 40), 'brawler', fill='black')
            im = Image.open(f'{OUT}/png/game_{s}/{k:03d}.png').convert('RGB')
            gx = max(W // 2, min(im.size[0] - W // 2, int(gr[k]['sx'])))
            a = im.crop((gx - W // 2, 224 - H, gx + W // 2, 224))
            R_ = br[b0 + k]
            imb = Image.open(f'{OUT}/png/brawler_{s}/{b0 + k:03d}.png').convert('RGB')
            cx = max(W // 2, min(320 - W // 2, int(R_['sx'])))
            bb = imb.crop((cx - W // 2, 224 - H, cx + W // 2, 224))
            S.paste(a, (x, y + 14)); S.paste(bb, (x, y + H + 34))
            d.rectangle([x - 1, y + 13, x + W, y + 14 + H], outline='black'); d.rectangle([x - 1, y + H + 33, x + W, y + H + 34 + H], outline='black')
            d.text((x + 2, y + 1), f"{k} {gr[k]['anim']:X}.{gr[k]['step']}", fill='black')
            d.text((x + 2, y + H + 21), f"{k} {R_['state'][:7]} {R_['anim']}.{R_['step']}", fill='black')
        p = f'{SHEETS}/{s}.png'; S.save(p); print(p)

if __name__ == '__main__':
    cmd, sc = sys.argv[1], sys.argv[2:] or list(SCENS)
    {'game': game, 'brawler': brawler, 'sheet': sheet}[cmd](sc)
