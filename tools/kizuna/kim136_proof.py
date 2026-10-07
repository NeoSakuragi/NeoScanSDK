#!/usr/bin/env python3
"""TODO #136 / #138 proof: Kim's 421A (up+C) and 6246A (the D fury, the Phoenix) played by their programs with Kizuna's
victim side read from its code (export_kz: sr_motion / sr_pair the reactions, P_VPHASE the victim phases, P_SCREEN the
Phoenix's screen), next to Kizuna Encounter playing the same move (our emulator: the followups_kz recipes 421A_w /
421A_h / 6246A_w / 6246A_h), whiff and hit; then the source reactions' effect on #133's moves (hit counts before /
after) and both moves in a real fight.

    python3 kim136_proof.py [OUTDIR] [--base GAME_DIR]     (default /data/tmp/kim136/out; --base: the build before)

Per scenario, frame by frame from the move's first frame (each game's hit-stop frames dropped): Kim's picture (the
Kizuna animation + step -> the brawler frame its export made), his place (dx forward, height; Kizuna's px x 0.80), the
victim's place from Kim's start and its reaction (Kizuna's reaction animation; the brawler's source reaction's), the
hits. 421A's last two hits in Kizuna are its tag partner's (RELIEFP1, the 421A catch sets Kim's +$180 = 2: the partner
jumps in, $344EC..$34646, its jump attack hits at 101.11 and after; the brawler has no partner): Kizuna's rows are
compared up to the partner's first hit. A whiff: pictures identical, dx within 2 px (Kizuna's neutral routine moves Kim 3 px on 421A's
last frame), height within 1.5 px. A hit: the pictures in order identical, Kim's own hits as many as Kizuna's, the
victim's reactions in the same order, its place within VTOL px at that row or one either side (VTOL below) -> OUT/proof.json, contact sheets OUT/<scenario>.png (Kizuna above, the
brawler below, every 4 frames), OUT/fight_<move>_<whiff|hit>.png, OUT/hits_before_after.json."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import followups_kz as FK, export_kz as E, kim133_proof as K133, kim144_proof
from PIL import Image, ImageDraw

BASE = sys.argv[sys.argv.index('--base') + 1] if '--base' in sys.argv else None
args = [a for a in sys.argv[1:] if not a.startswith('--') and a != BASE]
OUT = args[0] if args and '--hits' not in sys.argv else '/data/tmp/kim136/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
EVERY = 4
VTOL = 24     # the victim's place vs Kizuna's, px: the bodies' push is modelled for the phased victim only (Kizuna pushes
              # its first boxes apart every frame: Kim 8 px back off the launched 9B victim at the Phoenix's 86.46, Kim
              # 9 px further on in the brawler; the ceiling snap one frame apart: 13 px up)
QUICK = bool(os.environ.get('QUICK'))                       # (development: no pictures, no fight, no before / after)
ANIMS = {'421A': (0x100, 0x101), '6246A': (0x85, 0x86, 0x88, 0x89)}
SC = [('421A whiff', '421A', 'Uc', '421A_w'), ('421A hit', '421A', 'Uc', '421A_h'),
      ('6246A whiff', '6246A', 'd', '6246A_w'), ('6246A hit', '6246A', 'd', '6246A_h')]
NOREACT = (0, 0x1B, 0x1D, 1, 2)

def sreact_anims(game):
    """bm_sreact index + 1 -> the source's reaction animation (its last field)"""
    src = open(os.path.join(game, 'build', 'bm_chars.c')).read()
    m = re.search(r'bm_sreact\[\d+\] = \{(.*?)\};', src)
    return {k + 1: int(e.split(',')[-1]) for k, e in enumerate(re.findall(r'\{([^{}]*)\}', m.group(1)))} if m else {}

def kz_side(fr, anims):
    """Kizuna's rows (hit-stop frames dropped): Kim's anim / step / dx / height, the victim's dx / height / reaction anim;
    its hits: (row, reaction anim, by Kim: his step on the frame before carries an attack box)"""
    def frozen(i):                                       # a hit-stop frame: Kim still (step, place, tick count) while
        p, q, p0, q0 = fr[i][0], fr[i][1], fr[i - 1][0], fr[i - 1][1]   # the victim is still or just hit (a new
        return [p[k] for k in (0, 1, 2, 3, 10)] == [p0[k] for k in (0, 1, 2, 3, 10)] and \
            ([q[k] for k in (0, 1, 10)] == [q0[k] for k in (0, 1, 10)] or (q[1] == 0 and q[10] == 0 and q0[10] != 0) or   # reaction's
             (q[1] == 0 and q[10] == 0 and q[0] != q0[0]))  # step 0, t 0: the same one again too, the Phoenix's 33 -> 33)
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == anims[0])
    x0 = fr[s0 - 1][0][2]
    rows = []
    for i in range(s0, len(fr)):
        p = fr[i][0]
        if p[0] not in anims: break
        if frozen(i): continue
        rows.append({'a': p[0], 's': p[1], 'dx': (p[2] - x0) * E.S, 'y': p[3] * E.S, 'i': i})
    for r in rows:
        q = fr[r['i']][1]; r.update(vdx=(q[2] - x0) * E.S, vy=q[3] * E.S, va=q[0])
    hits, partner, others = [], None, 0
    end = rows[-1]['i'] + 2
    for j in range(s0 + 1, len(fr)):
        q, q0 = fr[j][1], fr[j - 1][1]
        if (q[0] != q0[0] and q[0] not in NOREACT) or (q[0] == q0[0] and q[1] == 0 and q0[1] != 0 and q[10] == 0):
            p = fr[j - 1][0]
            bx = E.step_boxes(p[5]) if p[0] in anims else []
            k = next((t for t, r in enumerate(rows) if r['i'] >= j), len(rows))
            by_kim = any(E.attack(b) for b in bx)
            if not by_kim and j < end + 60:
                others += 1
                if partner is None: partner = k
            if by_kim: hits.append((k, q[0]))
    return s0, rows, hits, partner, others

def brawler_side(b, k, move, keys, dist, sra, first=None):
    """the brawler playing the move at the Chain Lab's dummy (dist px ahead): per frame (its hit-stop frames dropped)
    Kim's frame / dx / height, the dummy's dx / height / state / source reaction's anim; its hits on the dummy"""
    K133.lab_req(b, 1, k, 0); b.run(40); b.fset(0, 'meter', 120)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    x0 = 100 if move == '421A' else 40 if dist < 150 else 30   # (room behind Kim: 421A's catch pushes him 48 px back)
    b.place(dm, x=x0 + dist, z=30); b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.fset(dm, 'hp', 60); b.run(3)
    h0 = len(b.hits); log, cells, start, after = [], [], None, 0
    kx0 = px = b.fget(0, 'x')
    for f in range(520):
        if start is not None and (f - start) % EVERY == 0 and len(cells) < 90 and not QUICK:
            pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append(Image.open(pth).convert('RGB'))
        else: b.run(1, p1=keys if f < 3 else '')
        st = b.states[b.fget(0, 'state')]
        if st == 'SPECIAL' and start is None and (first is None or b.fget(0, 'frame_ovr') == first):   # (a fury: after
            start = f; kx0 = px                                                                     # its flash pose)
        px = b.fget(0, 'x')
        if start is None: continue
        if st != 'SPECIAL':
            after += 1
            if after > 60: break
        frz = b.fget(0, 'freeze') if st == 'SPECIAL' else b.fget(dm, 'freeze')
        if frz: continue
        ksr = b.fget(dm, 'ksr') if 'ksr' in b.layout else 0
        log.append({'special': st == 'SPECIAL', 'frame': b.fget(0, 'frame_ovr'), 'dx': b.fget(0, 'x') - kx0, 'y': b.fget(0, 'y'),
                    'vdx': b.fget(dm, 'x') - kx0, 'vy': b.fget(dm, 'y'), 'vst': b.states[b.fget(dm, 'state')], 'va': sra.get(ksr)})
    hits = [h for h in b.hits[h0:] if h[1] == dm]
    return log, hits, cells

def sheet(name, kzc, cells, out):
    C_ = 12; W_, H_ = 160, 112
    n = max(len(kzc), len(cells)); nch = (n + C_ - 1) // C_
    sh = Image.new('RGB', (80 + W_ * C_, (2 * H_ + 22) * nch + 16), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 2), f'TODO #136 / #138 Kim {name}: every {EVERY} frames from the move start; top Kizuna, bottom the brawler (program, Kizuna\'s victim code)', fill='black')
    for i in range(n):
        y0 = 16 + (2 * H_ + 22) * (i // C_); xx = 80 + W_ * (i % C_)
        if i % C_ == 0: d.text((4, y0 + 50), 'Kizuna', fill='black'); d.text((4, y0 + H_ + 56), 'brawler', fill='black')
        if i < len(kzc): sh.paste(kzc[i].resize((W_, H_)), (xx, y0))
        if i < len(cells): sh.paste(cells[i].resize((W_, H_)), (xx, y0 + H_ + 4))
        d.text((xx + 2, y0 + 2 * H_ + 6), f'+{i * EVERY}', fill='black')
    sh.save(out)

def kim_index(b, game):
    hdr = open(os.path.join(game, 'build', 'bm_chars.h')).read()
    return re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_KIM')

def main():
    os.makedirs(OUT, exist_ok=True)
    fc = json.load(open(FK.OUT))
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_kizuna_kim', 'kof95_export.json')))['characters']['kim']
    K133.ANIMS.update(ANIMS)
    pf = K133.prog_frames(ex)
    sra = sreact_anims(GAME)
    kzimg = {}                                           # (Kizuna's pictures first: one emulator at a time)
    for name, move, keys, rec in ([] if QUICK else SC):
        fr = fc[rec]['frames']; s0 = kz_side(fr, ANIMS[move])[0]
        n = (len(fr) - s0) // EVERY
        kzimg[name] = kim144_proof.kz_snaps('fol', rec, [s0 + 2 + EVERY * i for i in range(n)], f'/data/tmp/kim136/snap_{rec}')
    from harness import Brawler
    b = Brawler(); k = kim_index(b, GAME); b.pick(k)
    res, ok_all = {}, True
    for name, move, keys, rec in SC:
        fr = fc[rec]['frames']
        s0, kz, kzh, partner, others = kz_side(fr, ANIMS[move])
        cut = partner if partner is not None else len(kz)
        dist = (fr[s0][1][2] - fr[s0][0][2]) * E.S
        fmap = pf[move][0]
        log, hits, cells = brawler_side(b, k, move, keys, dist, sra, fmap.get((kz[0]['a'], kz[0]['s'])))
        want = [fmap.get((r['a'], r['s'])) for r in kz]
        br = [r for r in log if r['special']]
        hitcap = rec.endswith('_h')
        dd = lambda seq: [x for j, x in enumerate(seq) if j == 0 or x != seq[j - 1]]
        pics_kz, pics_br = dd(want[:cut]), dd([r['frame'] for r in br])
        if partner is not None: pics_br = pics_br[:len(pics_kz)]
        n = min(len(kz), len(br))
        pic = [i for i in range(min(n, cut)) if want[i] != br[i]['frame']]
        dxd = max((abs(kz[i]['dx'] - br[i]['dx']) for i in range(min(n, cut))), default=0)
        dyd = max((abs(kz[i]['y'] - br[i]['y']) for i in range(min(n, cut))), default=0)
        # the victim: its place from Kim's start and its reactions, frame for frame while both games show the move
        # (the brawler's rows after the special: its victim still flying / bouncing, as Kizuna's after its move)
        allbr = log
        m_ = min(len(kz), len(allbr), cut)
        vdev = [min(abs(kz[i]['vdx'] - allbr[j]['vdx']) + abs(kz[i]['vy'] - allbr[j]['vy']) for j in (i - 1, i, i + 1) if 0 <= j < len(allbr))
                for i in range(m_)]                      # (at that row or one either side: Kizuna's victim reads the phase
                                                         # Kim wrote on its next frame, the brawler's on the same)
        kz_re = dd([a for _, a in kzh])
        br_re = dd([a for a in (r['va'] for r in allbr) if a])
        if hitcap:
            ok = pics_kz == pics_br and len(hits) == len(kzh) and kz_re == br_re[:len(kz_re)] and (max(vdev) if vdev else 0) <= VTOL
        else:
            ok = not pic and len(kz) == len(br) and dxd <= 2 and dyd <= 1.5 and not hits
        ok_all &= ok
        res[name] = {'kizuna_recipe': rec, 'ok': ok, 'frames_kizuna': len(kz), 'frames_brawler': len(br),
                     'compared_up_to_row': cut, 'partner_first_hit_row': partner,
                     'picture_mismatch_frames': pic, 'pictures_in_order_identical': pics_kz == pics_br,
                     'kim_max_dx_diff_px': round(dxd, 2), 'kim_max_height_diff_px': round(dyd, 2),
                     'hits_kizuna_by_kim': len(kzh), 'hits_kizuna_not_kim': others,
                     'hits_brawler': len(hits), 'damage_brawler': sum(h[2] for h in hits),
                     'reactions_kizuna': [f'{a:X}' for a in kz_re], 'reactions_brawler': [f'{a:X}' for a in br_re],
                     'victim_max_dev_px': round(max(vdev), 1) if vdev else None,
                     'victim_dev_by_frame': [round(v, 1) for v in vdev],
                     'rows': [[want[i] if i < len(kz) else None, round(kz[i]['dx'], 1) if i < len(kz) else None, round(kz[i]['y'], 1) if i < len(kz) else None,
                               round(kz[i]['vdx'], 1) if i < len(kz) else None, round(kz[i]['vy'], 1) if i < len(kz) else None,
                               allbr[i]['frame'] if i < len(allbr) else None, round(allbr[i]['dx'], 1) if i < len(allbr) else None, round(allbr[i]['y'], 1) if i < len(allbr) else None,
                               round(allbr[i]['vdx'], 1) if i < len(allbr) else None, round(allbr[i]['vy'], 1) if i < len(allbr) else None]
                              for i in range(max(len(kz), len(allbr)))]}
        print(f'{name:12s} {"ok" if ok else "FAIL"} frames kz {len(kz)} br {len(br)} (to row {cut}) pic diff {pic[:6]} order {pics_kz == pics_br} '
              f'dx {dxd:.2f} dy {dyd:.2f} | hits kz(Kim) {len(kzh)} br {len(hits)} | reactions kz {res[name]["reactions_kizuna"]} br {res[name]["reactions_brawler"]} '
              f'| victim dev max {res[name]["victim_max_dev_px"]}', flush=True)
        if not QUICK: sheet(name, kzimg[name][:max(len(cells), 1)], cells, os.path.join(OUT, re.sub(r'[^A-Za-z0-9]+', '_', name) + '.png'))
    if QUICK:
        json.dump(res, open(os.path.join(OUT, 'proof_quick.json'), 'w'), indent=1); return
    K133.FIGHT[:] = [('421A', 'Uc', []), ('6246A', 'd', [])]
    K133.OUT = OUT
    res['real_fight'] = K133.real_fight(b, k)
    res['all_ok'] = bool(ok_all and all(v['ok'] for v in res['real_fight'].values()))
    import subprocess
    hb = {}
    for label, game in (('before', BASE), ('after', GAME)):
        if not game: continue
        subprocess.run([sys.executable, os.path.abspath(__file__), '--hits', game, os.path.join(OUT, f'hits_{label}.json')], check=True)
        for nm, v in json.load(open(os.path.join(OUT, f'hits_{label}.json'))).items():
            hb.setdefault(nm, {'kizuna': v['kizuna']})[label] = v['brawler']
    json.dump(hb, open(os.path.join(OUT, 'hits_before_after.json'), 'w'), indent=1)
    res['hits_before_after'] = hb
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print('ALL OK' if res['all_ok'] else 'FAILURES')

def hits_of(game, path):
    """#133's moves (kim133_proof's hit scenarios: the dummy where Kizuna's victim stood, every follow-up press) on the
    build in game: hits on the dummy vs Kizuna's -> path"""
    from harness import Brawler
    import capture_kz
    fc = json.load(open(FK.OUT))
    caps = {'cap': json.load(open(capture_kz.OUT)), 'fol': fc}
    out = {}
    ex = json.load(open(os.path.join(game, 'build', 'tmp_kizuna_kim', 'kof95_export.json')))['characters']['kim']
    pf = K133.prog_frames(ex)
    b = Brawler(game=game); k = kim_index(b, game); b.pick(k)
    for name, move, keys, src, rec, follow in K133.SC:
        if 'hit' not in name: continue
        fmap = pf[move][0]
        fr = caps[src][rec]['frames']; s0, kz = K133.kz_rows(fr, K133.ANIMS[move])
        dist = (fr[s0][1][2] - fr[s0][0][2]) * E.S
        kz_hits = sum(1 for j in range(kz[0]['i'], kz[-1]['i'] + 2) if fr[j][1][6] < fr[j - 1][1][6])
        K133.lab_req(b, 1, k, 0); b.run(40); b.fset(0, 'meter', 120)
        dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
        x0 = 40 if dist < 150 else 30
        b.place(dm, x=x0 + dist, z=30); b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.fset(dm, 'hp', 60); b.run(3)
        frames_of = lambda a: {v for (a_, s_), v in fmap.items() if a_ == a}
        h0 = len(b.hits); pressed = set(); hold = 0; hk = ''; start = None; end = 0
        for f in range(400):
            p = keys if f < 3 else ''
            st = b.states[b.fget(0, 'state')]
            if st == 'SPECIAL':
                start = f if start is None else start
                cur = b.fget(0, 'frame_ovr')
                for j, (an, fk, needhit) in enumerate(follow):
                    if j in pressed or cur not in frames_of(an): continue
                    if needhit and len(b.hits) == h0: continue
                    if an == 0x9B and cur not in {fmap[(0x9B, s_)] for s_ in range(8, 16)}: continue
                    pressed.add(j); hold, hk = 3, fk
            elif start is not None:
                end += 1
                if end > 40: break
            if hold: p = hk; hold -= 1
            b.run(1, p1=p)
        n = len([h for h in b.hits[h0:] if h[1] == dm])
        out[name] = {'kizuna': kz_hits, 'brawler': n}
        print(f'hits {game}: {name:20s} {n} (Kizuna {kz_hits})', flush=True)
    json.dump(out, open(path, 'w'), indent=1)

if __name__ == '__main__':
    if '--hits' in sys.argv: hits_of(sys.argv[sys.argv.index('--hits') + 1], sys.argv[sys.argv.index('--hits') + 2])
    else: main()
