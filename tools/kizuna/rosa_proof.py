#!/usr/bin/env python3
"""TODO #213 proof: Rosa's specials played by their programs (rosa_kz.py: Kizuna's handlers, no recorded rows) in the
brawler (harness, the Chain Lab's dummy) next to Kizuna Encounter playing the same move (our emulator: the followups_kz
recipes of /data/neogeo_dict/kizuna/rosa/followups.json), whiff and hit, every follow-up; then each move in a real fight.

    python3 rosa_proof.py [OUTDIR] [--game GAME_DIR]      (default /data/tmp/rosa213/out; QUICK=1: no pictures, no fight)

Per scenario, frame by frame from the move's first frame (each game's hit-stop frames dropped): Rosa's picture (the
Kizuna animation + step -> the brawler frame its program shows for it), her place (dx forward, height; Kizuna px x 0.80),
the hits on the victim (Kizuna: its life drops / new reactions while the move plays, by her or her objects; the brawler:
the harness hit log on the dummy), the victim's reactions in order (Kizuna's reaction animations; the brawler's source
reactions, bm_sreact), the victim's place from her start. A whiff: pictures identical frame for frame, dx within 2 px,
height within 1.5 px, no hit (a projectile's / object's own flight excepted: 236C's shockwave reaches Kizuna's far P2).
A hit: the pictures in order identical, as many hits as Kizuna, the reactions in the same order. Contact sheets
OUT/<scenario>.png (Kizuna above, the brawler below, every 4 frames), OUT/fight_<move>_<whiff|hit>.png, OUT/proof.json."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import cap_kz as cap, followups_kz as FU, fighters_kz as FK, export_kz as E
from PIL import Image, ImageDraw

args = [a for a in sys.argv[1:] if not a.startswith('--')]
GAME = sys.argv[sys.argv.index('--game') + 1] if '--game' in sys.argv else os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
args = [a for a in args if a != GAME]
OUT = args[0] if args else '/data/tmp/rosa213/out'
QUICK = bool(os.environ.get('QUICK'))
ONLY = os.environ.get('ONLY')
EVERY = 4
NOREACT = (0, 0x1B, 0x1D, 1, 2, 7, 8)
GRAB = (0x101, 0x106)                               # the victim's thrown animations (her grabs' requests): no hit
AIR = 'AIR'                                          # j.2C: a jump forward, down+A at Kizuna's height
# (name, move, keys, Kizuna recipe, follow-up presses [(Kizuna anim it is pressed in, keys, needs a hit)], Rosa's anims)
SC = [('236C whiff', '236C', 'c', '236C_w', [], (0x5D,)),
      ('236C hit', '236C', 'c', '236C_h', [], (0x5D,)),
      ('421C whiff', '421C', 'Uc', '421C_m', [], (0xA6,)),
      ('421C hit', '421C', 'Uc', '421C_h', [], (0xA6,)),
      ('63214C whiff', '63214C', 'DRc', '63214C_w', [], (0xAB,)),
      ('63214C hit', '63214C', 'DRc', '63214C_h', [], (0xAB,)),
      ('623C whiff', '623C', 'Dc', '623C_w', [], (0xA0, 0xA1)),
      ('623C hit', '623C', 'Dc', '623C_h', [], (0xA0, 0xA1)),
      ('623C 214C hit', '623C', 'Dc', '623C2_h', [(0xA0, 'a', 1)], (0xA0, 0xA2)),
      ('214B whiff', '214B', 'Rc', '214B_w', [], (0xA5, 0xC2)),
      ('214B hit', '214B', 'Rc', '214B_h', [], (0xA5, 0xC2)),
      ('214B 236B hit', '214B', 'Rc', '214B_c1_h', [(0xA5, 'Ra', 1)], (0xA5, 0xD4)),
      ('214B 214B grab', '214B', 'Rc', '214B_c0_h', [(0xA5, 'Rc', 1)], (0xA5, 0xD5)),
      ('421A whiff', '421A', 'Dd', '421A_w', [], (0xDB, 0xDC)),
      ('421A hit', '421A', 'Dd', '421A_h', [], (0xDB, 0xDC)),
      ('6246A whiff', '6246A', 'd', '6246A_w', [], (0xD6, 0xDE)),
      ('6246A hit', '6246A', 'd', '6246A_h', [], (0xD6, 0xD7, 0xD8, 0xD9, 0x119)),
      ('j.2C whiff', 'j.2C', AIR, 'j2C_w', [], (0xA7, 0xA9)),
      ('j.2C hit', 'j.2C', AIR, 'j2C_h', [], (0xA7, 0xA8, 0xA9)),
      ('j.2C 2C hit', 'j.2C', AIR, 'j2C2_h', [(0xA7, 'Da', 1)], (0xA7, 0xA8, 0xD2, 0xD3, 0x81))]   # (Kizuna's press: in A7's hit-stop)
PARTNER = {(0xDB, 0xDC): (0xDC, 11)}                # 421A ($3AEE0, Kim's handler): the catch calls the tag partner
                                                     # (+$180 = 2, RELIEFP1): its jump attack lands the hits from DC.11 on
                                                     # (as Kim's from 101.11, TODO #136; the victim 90 px past her box)
PROJ_REACH = {'236C'}
DUMMY = [0]                                          # the Lab dummy: Kim (Kizuna's own boxes, the captures' victim is
DUMMY_NAME = os.environ.get('DUMMY', 'BC_KIM')       # Hayate; DUMMY=BC_TERRY: a KOF one)                                # its object travels on to Kizuna's far P2 (a whiff's hit allowed)

def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)

class LabHits:
    """P1's hits as the game logs them for the Chain Lab (lab_t.ev ring: LE_HIT, victim idx, damage; fighter.c
    lab_note): every hit counted, 0 damage too (the harness's own log needs a life drop or a fresh hit-stop)"""
    def __init__(self, b): self.b = b; self.L = b.syms['lab']; self.seen = b.r(self.L + 9, 1); self.hits = []
    def poll(self):
        n = self.b.r(self.L + 9, 1)
        while self.seen != n:
            e = self.L + 16 + 6 * (self.seen % 64)
            if self.b.r(e + 2, 1) == 1: self.hits.append((self.b.r(e, 2), self.b.r(e + 4, 1), self.b.r(e + 5, 1)))
            self.seen = (self.seen + 1) & 0xFF

def prog_frames(ex, n='rosa'):
    """{move: {(Kizuna anim, step): brawler frame}} from the build's programs (bm_spec.c rosa_spK_aJ)"""
    src = open(os.path.join(GAME, 'build', 'bm_spec.c')).read()
    arrays = {}
    for m in re.finditer(r'static const bstep_t %s_sp(\d+)_a(\d+)\[\] = \{(.*)\};' % n, src):
        arrays.setdefault(int(m.group(1)), {})[int(m.group(2))] = [int(x) for x in re.findall(r'\{(\d+), \d+, \d+, \{', m.group(3))]
    out, used = {}, set()
    for sp in ex['specials']:
        r = sp.get('rom')
        if not r or not r.get('prims'): continue
        lens = [len(r['anims'][s]['steps']) for s in r['states']]
        firsts = [r['anims'][s]['steps'][0]['frame'] for s in r['states']]
        k = next(k for k, a in arrays.items() if k not in used and [len(a[j]) for j in sorted(a)] == lens
                 and [a[j][0] for j in sorted(a)] == firsts)
        used.add(k)
        out[sp['input']] = ({(r['anims'][s]['kz_anim'], r['anims'][s].get('kz_first', 0) + i): arrays[k][j][i]
                             for j, s in enumerate(r['states']) for i in range(len(arrays[k][j]))}, k)
    return out

def frozen(fr, i):
    """a hit-stop frame of Kizuna's: Rosa still (step, place, tick count) while the victim is still or just hit"""
    p, q, p0, q0 = fr[i][0], fr[i][1], fr[i - 1][0], fr[i - 1][1]
    return [p[k] for k in (0, 1, 2, 3, 10)] == [p0[k] for k in (0, 1, 2, 3, 10)] and \
        ([q[k] for k in (0, 1, 10)] == [q0[k] for k in (0, 1, 10)] or (q[1] == 0 and q[10] == 0 and q0[10] != 0) or
         (q[1] == 0 and q[10] == 0 and q[0] != q0[0]))

def kz_side(fr, anims):
    """Kizuna's rows (hit-stop frames dropped): Rosa's anim / step / dx / height and the victim's dx / height /
    reaction; its hits (row, reaction anim) while she plays the move (+2 frames)"""
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == anims[0])
    x0 = fr[s0 - 1][0][2]; sgn = -1 if fr[s0][0][4] else 1
    rows = []
    for i in range(s0, len(fr)):
        p = fr[i][0]
        if p[0] not in anims: break
        if frozen(fr, i): continue
        q = fr[i][1]
        rows.append({'a': p[0], 's': p[1], 'dx': sgn * (p[2] - x0) * E.S, 'y': p[3] * E.S, 'i': i,
                     'vdx': sgn * (q[2] - x0) * E.S, 'vy': q[3] * E.S, 'va': q[0]})
    end = rows[-1]['i'] + 2 if rows else s0
    hits, others = [], []
    for j in range(s0 + 1, min(len(fr), end + 1)):
        q, q0 = fr[j][1], fr[j - 1][1]
        if q[0] not in NOREACT + GRAB and ((q[0] != q0[0]) or (q[1] == 0 and q0[1] != 0 and q[10] == 0)) or q[6] < q0[6]:
            k = next((t for t, r in enumerate(rows) if r['i'] >= j), len(rows))
            p = fr[j - 1][0]
            mine = any(E.attack(b) for b in E.step_boxes(p[5])) or any(o[1] >> 12 == 4 and any(E.attack(b) for b in E.step_boxes(o[6]))
                                                                        for o in fr[j - 1][2])
            if q0[0] in GRAB: mine = True                # (a thrown victim's damage: her grab's, its handler deals it)
            if (hits and hits[-1][2] == j - 1) or (others and others[-1][2] == j - 1): continue
            pa = PARTNER.get(anims)                     # (421A: its relief call's partner hits from DC.11 on)
            if pa and (p[0], p[1]) >= pa and p[0] == pa[0]: mine = False
            (hits if mine else others).append((k, q[0], j))
    return s0, rows, hits, others

def kz_snaps(rec, frames, d):
    """Kizuna's screen on those capture frames (the recipe replayed with SNAPS)"""
    os.makedirs(d, exist_ok=True)
    p2x, seq, pokes = FU.RECIPES[rec][:3]; hold = FU.RECIPES[rec][3] if len(FU.RECIPES[rec]) > 3 else ''
    n = cap.nframes(seq)
    pk = FU.pokes_of(rec, n)
    cap.run(seq, f'{n}:{hold}' if hold else '', pokes=';'.join(pk) or None, load=FK.state('rosa'),
            extra={'SNAPS': ','.join(map(str, frames)), 'SNAPDIR': d}, n=max(frames) + 2)
    return [Image.open(f'{d}/snap_{f}.ppm').convert('RGB') if os.path.exists(f'{d}/snap_{f}.ppm') else Image.new('RGB', (320, 224)) for f in frames]

def sreact_anims():
    src = open(os.path.join(GAME, 'build', 'bm_chars.c')).read()
    m = re.search(r'bm_sreact\[\d+\] = \{(.*?)\};', src)
    return {k + 1: int(e.split(',')[-1]) for k, e in enumerate(re.findall(r'\{([^{}]*)\}', m.group(1)))} if m else {}

def brawler_side(b, k, move, keys, dist, follow, fmap, sra, first, jump_h=None, x0=None, y0=None, name=''):
    """the brawler playing the move at the Chain Lab's dummy (dist px ahead): per frame (hit-stop frames dropped) her
    frame / dx / height, the dummy's dx / height / source reaction's anim; the hits on the dummy; follow-up presses
    when her frame is one of that Kizuna animation's (after a hit when asked)"""
    lab_req(b, 1, k, DUMMY[0]); b.run(40); b.fset(0, 'meter', 120)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    if x0 is None: x0 = 120 if move == '421C' else 200 if (move == '6246A' or 'grab' in name) and dist < 150 else 40 if dist < 150 else 30   # (room behind her: the hop, her throws)
    b.place(dm, x=x0 + dist, z=30); b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.fset(dm, 'hp', 60); b.run(3)
    h0 = len(b.hits); log, cells, start, after = [], [], None, 0
    lh = LabHits(b)
    frames_of = lambda a: {v for (a_, s_), v in fmap.items() if a_ == a}
    pressed = set(); hold = 0; hk = ''; kx0 = px = b.fget(0, 'x'); jumped = None
    for f in range(600):
        p = ''
        if keys == AIR:                                  # a jump forward, down+A at Kizuna's dive height
            if f < 3: p = 'Rb'
            elif start is None and b.fget(0, 'y') >= jump_h and jumped is None: jumped = f
            if jumped is not None and f < jumped + 3 and start is None: p = 'Da'
        elif f < 3: p = keys
        st = b.states[b.fget(0, 'state')]
        if start is not None and st == 'SPECIAL':
            cur = b.fget(0, 'frame_ovr')
            for j, (an, fk, needhit) in enumerate(follow):
                if j in pressed or cur not in frames_of(an): continue
                if needhit and len([h for h in b.hits[h0:] if h[1] == dm]) == 0: continue
                pressed.add(j); hold, hk = 3, fk
        if hold: p = hk; hold -= 1
        if start is not None and (f - start) % EVERY == 0 and not QUICK and len(cells) < 90:
            pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append(Image.open(pth).convert('RGB'))
        else: b.run(1, p1=p)
        lh.poll()
        st = b.states[b.fget(0, 'state')]
        if st == 'SPECIAL' and start is None and (first is None or b.fget(0, 'frame_ovr') == first):
            start = f; kx0 = px
            if keys == AIR:                              # (the dive from Kizuna's height, its victim where Kizuna's was)
                b.fset(0, 'y', y0); b.place(dm, x=b.fget(0, 'x') + dist)
        px = b.fget(0, 'x')
        if start is None: continue
        if st != 'SPECIAL':
            after += 1
            if after > 40: break
        frz = b.fget(0, 'freeze') if st == 'SPECIAL' else b.fget(dm, 'freeze')
        if frz: continue
        ksr = b.fget(dm, 'ksr') if 'ksr' in b.layout else 0
        log.append({'special': st == 'SPECIAL', 'frame': b.fget(0, 'frame_ovr'), 'dx': b.fget(0, 'x') - kx0,
                    'y': b.fget(0, 'y'), 'vdx': b.fget(dm, 'x') - kx0, 'vy': b.fget(dm, 'y'), 'vst': b.states[b.fget(dm, 'state')],
                    'va': sra.get(ksr) if b.states[b.fget(dm, 'state')] in ('HITSTUN', 'KNOCKDOWN') else None})
    hits = [h for h in lh.hits if h[1] == dm]
    return log, hits, cells

def sheet(name, kzc, cells, out):
    C_ = 12; W_, H_ = 160, 112
    n = max(len(kzc), len(cells)); nch = (n + C_ - 1) // C_
    sh = Image.new('RGB', (80 + W_ * C_, (2 * H_ + 22) * max(1, nch) + 16), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 2), f'TODO #213 Rosa {name}: every {EVERY} frames from the move start; top Kizuna, bottom the brawler (program)', fill='black')
    for i in range(n):
        y0 = 16 + (2 * H_ + 22) * (i // C_); xx = 80 + W_ * (i % C_)
        if i % C_ == 0: d.text((4, y0 + 50), 'Kizuna', fill='black'); d.text((4, y0 + H_ + 56), 'brawler', fill='black')
        if i < len(kzc): sh.paste(kzc[i].resize((W_, H_)), (xx, y0))
        if i < len(cells): sh.paste(cells[i].resize((W_, H_)), (xx, y0 + H_ + 4))
        d.text((xx + 2, y0 + 2 * H_ + 6), f'+{i * EVERY}', fill='black')
    sh.save(out)

def main():
    os.makedirs(OUT, exist_ok=True)
    E.setup('rosa'); FU.setup('rosa')
    fc = json.load(open(FK.path('rosa', 'followups')))
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_kizuna_rosa', 'kof95_export.json')))['characters']['rosa']
    pf = prog_frames(ex)
    sra = sreact_anims()
    sc = [s for s in SC if not ONLY or re.search(ONLY, s[0])]
    kzimg = {}
    for name, move, keys, rec, follow, anims in ([] if QUICK else sc):   # (Kizuna's pictures first: one emulator at a time)
        fr = fc[rec]['frames']; s0 = kz_side(fr, anims)[0]
        kzimg[name] = kz_snaps(rec, [s0 + 2 + EVERY * i for i in range((len(fr) - s0 - 4) // EVERY)], f'/data/tmp/rosa213/snap_{rec}')
    from harness import Brawler
    b = Brawler(game=GAME)
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    k = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_ROSA')
    DUMMY[0] = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index(DUMMY_NAME)
    b.pick(k)
    res, ok_all = {}, True
    for name, move, keys, rec, follow, anims in sc:
        fr = fc[rec]['frames']
        s0, kz, kzh, kzo = kz_side(fr, anims)
        dist = abs(fr[s0][1][2] - fr[s0][0][2]) * E.S
        fmap = pf[move][0]
        want = [fmap.get((r['a'], r['s'])) for r in kz]
        jh = fr[s0 - 1][0][3] * E.S if keys == AIR else None; y0 = fr[s0][0][3] * E.S
        log, hits, cells = brawler_side(b, k, move, keys, dist, follow, fmap, sra, want[0], jh, y0=y0, name=name)
        br = [r for r in log if r['special']]
        dd = lambda seq: [x for j, x in enumerate(seq) if j == 0 or x != seq[j - 1]]
        pics_kz, pics_br = dd(want), dd([r['frame'] for r in br])
        n = min(len(kz), len(br))
        pic = [i for i in range(n) if want[i] != br[i]['frame']]
        dxd = max((abs(kz[i]['dx'] - br[i]['dx']) for i in range(n)), default=0)
        dyd = max((abs(kz[i]['y'] - br[i]['y']) for i in range(n)), default=0)
        kz_re = dd([a for _, a, _ in kzh if a not in NOREACT + GRAB])
        br_re = dd([a for a in (r['va'] for r in log) if a])
        m_ = min(len(kz), len(log))
        vdev = [min(abs(kz[i]['vdx'] - log[j]['vdx']) + abs(kz[i]['vy'] - log[j]['vy']) for j in (i - 1, i, i + 1) if 0 <= j < len(log))
                for i in range(m_)]
        hitcap = rec.endswith('_h') or 'grab' in name
        if hitcap:
            ok = pics_kz == pics_br and len(hits) == len(kzh)
        else:
            ok = not pic and len(kz) == len(br) and dxd <= 2 and dyd <= 1.5 and (not hits or move in PROJ_REACH)
        ok_all &= ok
        res[name] = {'kizuna_recipe': rec, 'ok': ok, 'frames_kizuna': len(kz), 'frames_brawler': len(br),
                     'picture_mismatch_frames': pic, 'pictures_in_order_identical': pics_kz == pics_br,
                     'max_dx_diff_px': round(dxd, 2), 'max_height_diff_px': round(dyd, 2),
                     'hits_kizuna': len(kzh), 'hits_kizuna_partner': len(kzo), 'hits_brawler': len(hits), 'damage_brawler': sum(h[2] for h in hits),
                     'reactions_kizuna': [f'{a:X}' for a in kz_re], 'reactions_brawler': [f'{a:X}' for a in br_re],
                     'victim_max_dev_px': round(max(vdev), 1) if vdev else None,
                     'rows': [[want[i] if i < len(kz) else None, round(kz[i]['dx'], 1) if i < len(kz) else None, round(kz[i]['y'], 1) if i < len(kz) else None,
                               br[i]['frame'] if i < len(br) else None, round(br[i]['dx'], 1) if i < len(br) else None, round(br[i]['y'], 1) if i < len(br) else None]
                              for i in range(max(len(kz), len(br)))],
                     'victim_rows': [[kz[i]['va'] if i < len(kz) else None, round(kz[i]['vdx'], 1) if i < len(kz) else None, round(kz[i]['vy'], 1) if i < len(kz) else None,
                                      log[i]['vst'] if i < len(log) else None, log[i]['va'] if i < len(log) else None,
                                      round(log[i]['vdx'], 1) if i < len(log) else None, round(log[i]['vy'], 1) if i < len(log) else None]
                                     for i in range(max(len(kz), len(log)))]}
        print(f'{name:16s} {"ok" if ok else "FAIL"} frames kz {len(kz)} br {len(br)} pic diff {pic[:8]} order {pics_kz == pics_br} '
              f'dx {dxd:.2f} dy {dyd:.2f} | hits kz {len(kzh)} br {len(hits)} | reactions kz {res[name]["reactions_kizuna"]} br {res[name]["reactions_brawler"]} '
              f'| victim dev {res[name]["victim_max_dev_px"]}', flush=True)
        if not QUICK: sheet(name, kzimg[name][:max(len(cells), 1)], cells, os.path.join(OUT, re.sub(r'[^A-Za-z0-9]+', '_', name) + '.png'))
    if not QUICK and not ONLY: res['real_fight'] = real_fight(b, k)
    res['all_ok'] = bool(ok_all and all(v['ok'] for v in res.get('real_fight', {}).values()))
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    json.dump(res, open(os.path.join(OUT, 'proof_quick.json' if QUICK or ONLY else 'proof.json'), 'w'), indent=1)
    print('ALL OK' if res['all_ok'] else 'FAILURES')

FIGHT = [('236C', 'c', []), ('214B', 'Rc', []), ('623C', 'Dc', []), ('421C', 'Uc', []), ('63214C', 'DRc', []),
         ('6246A', 'd', []), ('421A', 'Dd', []), ('214B 236B', 'Rc', [(14, 'Ra')]), ('214B grab', 'Rc', [(14, 'Rc')])]
def real_fight(b, k):
    """a real fight (the campaign's first wave, AI on): each move at an enemy kept away (whiff), then at one in front
    (hit); the program plays (SPECIAL), the hits it lands; sheets OUT/fight_<move>_<whiff|hit>.png"""
    b.pick(k); b.run(200); start = b.save(); out = {}
    for move, keys, more in FIGHT:
        for label, gap in (('whiff', 300), ('hit', 50)):
            b.load(start); b.run(30)
            en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
            if not en: out[f'{move} {label}'] = {'ok': False, 'why': 'no enemy'}; continue
            e = en[0]; cam = b.r(b.syms['cam_x'], 2)
            b.place(0, x=cam + 40, z=b.fget(e, 'z')); b.place(e, x=cam + 40 + gap); b.fset(0, 'facing', 1); b.fset(e, 'hp', 60)
            h0 = len(b.hits); cells = []; specs = set(); n_sp = 0
            for f in range(200):
                kk = keys if f < 3 else next((m for t, m in more for j in range(3) if f == t + j), '')
                if label == 'whiff':
                    for i in en: b.place(i, x=b.fget(0, 'x') + gap)
                if f % 4 == 0: pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append(Image.open(pth).convert('RGB'))
                else: b.run(1, p1=kk)
                if b.states[b.fget(0, 'state')] == 'SPECIAL': specs.add(b.fget(0, 'spec_id')); n_sp += 1
            hits = [h for h in b.hits[h0:] if h[1] != 0]
            ok = bool(specs) and (bool(hits) if label == 'hit' else (not hits or move == '236C'))
            out[f'{move} {label}'] = {'ok': ok, 'roles': sorted(specs), 'special_frames': n_sp, 'hits': len(hits), 'damage': sum(h[2] for h in hits)}
            sh = Image.new('RGB', (10 + 160 * 10, 30 + 115 * ((len(cells) + 9) // 10)), 'white'); d = ImageDraw.Draw(sh)
            d.text((4, 2), f'real fight (campaign, AI on): Rosa {move} {label}: {len(hits)} hits (every 4 frames)', fill='black')
            for i, c in enumerate(cells): sh.paste(c.resize((160, 112)), (10 + 160 * (i % 10), 20 + 115 * (i // 10)))
            sh.save(os.path.join(OUT, f'fight_{re.sub(r"[^A-Za-z0-9]+", "", move)}_{label}.png'))
            print('real fight', move, label, out[f'{move} {label}'], flush=True)
    return out

if __name__ == '__main__':
    main()
