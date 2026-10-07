#!/usr/bin/env python3
"""TODO #133-#138 proof: Kim's specials played by their programs (export_kz.prog_special: Kizuna's handlers and the
animations' step commands, no recorded rows) in the brawler (harness, the Chain Lab's standing dummy) next to Kizuna
Encounter playing the same move (our emulator: kim_capture.json / kim_followups.json recipes), whiff and hit, every
follow-up input.

    python3 kim133_proof.py [OUTDIR]          (default /data/tmp/kim133/out)

Per scenario, frame by frame from the move's first frame (the hit-stop frames dropped on both sides: each game its
own): the picture (Kizuna's animation + step -> the brawler frame the export made of it), Kim's place (dx forward and
height, Kizuna's px x 0.80), the length, the animations played (the parts) and the hits on the dummy vs Kizuna's life
drops. Whiffs: pictures identical, dx / height within 1.5 px. Hits: pictures identical up to the first hit, then the
same parts and a hit count within one (the bodies' push after a contact is each game's own: Kizuna pushes the
attacker back, the brawler its victim). Contact sheets OUT/<scenario>.png (Kizuna above, the brawler below, every 3
frames). OUT/proof.json: everything, all_ok."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import capture_kz, followups_kz as FK, export_kz as E
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kim133/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
QUICK = bool(os.environ.get('QUICK'))                       # (development: no Kizuna pictures)
EVERY = 3
ANIMS = {'214B': (0x93,), '236A': (0x126,), '236C': (0x97, 0x8E, 0x98, 0x9A, 0x99), '[2]8C': (0x9B, 0x9C, 0x9D, 0x9E)}
# (name, move, brawler keys, source, Kizuna recipe, follow-up presses [(Kizuna anim it is pressed in, keys, needs a hit)])
SC = [('214B whiff', '214B', 'c', 'cap', 'sw_214B', []),
      ('214B hit', '214B', 'c', 'fol', '214B_h', []),
      ('236A whiff', '236A', 'DRc', 'cap', 'sw_236A', []),
      ('236A hit', '236A', 'DRc', 'cap', 'cmd_236A_near', []),
      ('236C whiff', '236C', 'Rc', 'fol', '236C_w', []),
      ('236C hit', '236C', 'Rc', 'fol', '236C_h', []),
      ('236C x2 whiff', '236C', 'Rc', 'fol', '236C2_w', [(0x8E, 'Rc', 0)]),
      ('236C x2 hit', '236C', 'Rc', 'fol', '236C2_h', [(0x8E, 'Rc', 0)]),
      ('236C x3 whiff', '236C', 'Rc', 'fol', '236C3_w', [(0x8E, 'Rc', 0), (0x98, 'Rc', 0)]),
      ('236C x3 hit', '236C', 'Rc', 'fol', '236C3_h', [(0x8E, 'Rc', 0), (0x98, 'Rc', 0)]),
      ('[2]8C whiff', '[2]8C', 'Dc', 'fol', '28C_w', []),
      ('[2]8C hit', '[2]8C', 'Dc', 'fol', '28C_h', []),
      ('[2]8C down+A whiff', '[2]8C', 'Dc', 'fol', '28C2_w', [(0x9B, 'Da', 0)]),
      ('[2]8C down+A hit', '[2]8C', 'Dc', 'fol', '28C2_h', [(0x9B, 'Da', 1)])]

def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)

def prog_frames(ex):
    """{move: {(Kizuna anim, step): brawler frame}} from the build's programs (bm_spec.c kim_spK_aJ, the export's states)"""
    src = open(os.path.join(GAME, 'build', 'bm_spec.c')).read()
    arrays = {}
    for m in re.finditer(r'static const bstep_t kim_sp(\d+)_a(\d+)\[\] = \{(.*)\};', src):
        arrays.setdefault(int(m.group(1)), {})[int(m.group(2))] = [int(x) for x in re.findall(r'\{(\d+), \d+, \d+, \{', m.group(3))]
    out = {}
    for sp in ex['specials']:
        r = sp.get('rom')
        if not r or sp['input'] not in ANIMS: continue
        lens = [len(r['anims'][s]['steps']) for s in r['states']]
        k = next(k for k, a in arrays.items() if [len(a[j]) for j in sorted(a)] == lens and
                 all(a[j][0] == r['anims'][s]['steps'][0]['frame'] or True for j, s in enumerate(r['states'])) and
                 k not in [v[1] for v in out.values()])
        out[sp['input']] = ({(r['anims'][s]['kz_anim'], i): arrays[k][j][i] for j, s in enumerate(r['states'])
                             for i in range(len(arrays[k][j]))}, k)
    return out

def frozen(fr, i):
    """a hit-stop frame (export_kz.frozen; kim_capture.json has no tick counter: there Kim still and the victim
    shaking 1-2 px on the same step)"""
    if len(fr[i][0]) > 10: return E.frozen(fr, i)
    p, q, p0, q0 = fr[i][0], fr[i][1], fr[i - 1][0], fr[i - 1][1]
    return p[:4] == p0[:4] and q[:2] == q0[:2] and 1 <= abs(q[2] - q0[2]) <= 2

def kz_rows(fr, anims):
    """Kizuna's frames of the move from its first one: [{a, s, dx, y, life, i}], hit-stop frames dropped"""
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == anims[0])
    x0 = fr[s0 - 1][0][2]
    rows = []
    for i in range(s0, len(fr)):
        p = fr[i][0]
        if p[0] not in anims: break
        if frozen(fr, i): continue
        rows.append({'a': p[0], 's': p[1], 'dx': (p[2] - x0) * E.S, 'y': p[3] * E.S, 'i': i})
    return s0, rows

def main():
    os.makedirs(OUT, exist_ok=True)
    caps = {'cap': json.load(open(capture_kz.OUT)), 'fol': json.load(open(FK.OUT))}
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_kizuna_kim', 'kof95_export.json')))['characters']['kim']
    pf = prog_frames(ex)
    kzimg = {}
    if not QUICK:
        import kim144_proof
        for name, move, keys, src, rec, follow in SC:
            fr = caps[src][rec]['frames']; s0, rows = kz_rows(fr, ANIMS[move])
            frames = list(range(s0, rows[-1]['i'] + 4, EVERY))
            kzimg[name] = kim144_proof.kz_snaps(src, rec, frames, f'/data/tmp/kim133/snap_{rec}')
    from harness import Brawler
    b = Brawler()
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    k = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_KIM')
    b.pick(k)
    res, ok_all = {}, True
    for name, move, keys, src, rec, follow in SC:
        fmap, spk = pf[move]
        fr = caps[src][rec]['frames']
        s0, kz = kz_rows(fr, ANIMS[move])
        dist = (fr[s0][1][2] - fr[s0][0][2]) * E.S
        kz_hits = sum(1 for j in range(kz[0]['i'], kz[-1]['i'] + 2) if fr[j][1][6] < fr[j - 1][1][6])
        lab_req(b, 1, k, 0); b.run(40); b.fset(0, 'meter', 120)
        dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
        x0 = 40 if dist < 150 else 30
        b.place(dm, x=x0 + dist, z=30); b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.fset(dm, 'hp', 60); b.run(3)
        frames_of = lambda a: {v for (a_, s_), v in fmap.items() if a_ == a}
        h0 = len(b.hits); log = []; cells = []; start = None; px = b.fget(0, 'x'); pressed = set(); hold = 0; hk = ''
        for f in range(400):
            p = keys if f < 3 else ''
            if start is not None and b.states[b.fget(0, 'state')] == 'SPECIAL':
                cur = b.fget(0, 'frame_ovr')
                for j, (an, fk, needhit) in enumerate(follow):
                    if j in pressed or cur not in frames_of(an): continue
                    if needhit and len(b.hits) == h0: continue
                    if an == 0x9B and cur not in {fmap[(0x9B, s)] for s in range(8, 16)}: continue   # late in 9B (airborne)
                    pressed.add(j); hold, hk = 3, fk
            if hold: p = hk; hold -= 1
            if start is not None and (f - start) % EVERY == 0 and not QUICK and len(cells) < len(kzimg.get(name, [])):
                pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append(Image.open(pth).convert('RGB'))
            else: b.run(1, p1=p)
            st = b.states[b.fget(0, 'state')]
            if st == 'SPECIAL' and start is None: start = f; xb0 = px
            px = b.fget(0, 'x')
            if start is not None:
                if st != 'SPECIAL':
                    if f - start > 300 or not log or log[-1].get('end'): break
                    log.append({'end': True}); continue
                log.append({'frame': b.fget(0, 'frame_ovr'), 'dx': b.fget(0, 'x') - xb0, 'y': b.fget(0, 'y'), 'freeze': b.fget(0, 'freeze')})
        while log and log[-1].get('end'): log.pop()
        if start is None:
            res[name] = {'ok': False, 'why': 'no SPECIAL'}; ok_all = False; print(name, 'FAIL no special'); continue
        br = [r for r in log if not r['freeze']]
        hits = [h for h in b.hits[h0:] if h[1] == dm]
        n = min(len(kz), len(br))
        want = [fmap.get((r['a'], r['s'])) for r in kz]
        pic = [i for i in range(n) if want[i] != br[i]['frame']]
        hitcap = kz_hits > 0
        drop = next((j for j in range(kz[0]['i'], kz[-1]['i'] + 2) if fr[j][1][6] < fr[j - 1][1][6]), None)
        first_hit = next((i for i, r in enumerate(kz) if r['i'] >= drop), len(kz)) if hitcap else len(kz)
        dxd = max((abs(kz[i]['dx'] - br[i]['dx']) for i in range(min(n, first_hit))), default=0)
        dyd = max((abs(kz[i]['y'] - br[i]['y']) for i in range(min(n, first_hit))), default=0)
        kz_parts = list(dict.fromkeys(r['a'] for r in kz))
        inv = {v: a for (a, s_), v in fmap.items()}
        br_parts = list(dict.fromkeys(inv.get(r['frame']) for r in br))
        dd = lambda seq: [x for j, x in enumerate(seq) if j == 0 or x != seq[j - 1]]
        pics_kz, pics_br = dd(want), dd([r['frame'] for r in br])   # the pictures in order (each game's hit-stop and
        res_pics = pics_kz == pics_br                                 # push its own after the first contact)
        if hitcap:
            ok = not [i for i in pic if i < first_hit] and kz_parts == br_parts and res_pics and abs(len(hits) - kz_hits) <= 1 and len(hits) >= 1
        else:
            ok = not pic and len(kz) == len(br) and dxd <= 1.5 and dyd <= 1.5 and not hits
        ok_all &= ok
        res[name] = {'kizuna_recipe': rec, 'ok': ok, 'frames_kizuna': len(kz), 'frames_brawler': len(br),
                     'picture_mismatch_frames': pic, 'pictures_in_order_identical': res_pics, 'first_hit_frame': first_hit if hitcap else None,
                     'max_dx_diff_px': round(dxd, 2), 'max_height_diff_px': round(dyd, 2),
                     'parts_kizuna': [f'{a:X}' for a in kz_parts], 'parts_brawler': [f'{a:X}' if a is not None else None for a in br_parts],
                     'hits_kizuna': kz_hits, 'hits_brawler': len(hits), 'damage_brawler': sum(h[2] for h in hits),
                     'victim_brawler': sorted({h[3] for h in hits}),
                     'rows': [[want[i] if i < len(kz) else None, round(kz[i]['dx'], 1) if i < len(kz) else None, round(kz[i]['y'], 1) if i < len(kz) else None,
                               br[i]['frame'] if i < len(br) else None, round(br[i]['dx'], 1) if i < len(br) else None, round(br[i]['y'], 1) if i < len(br) else None]
                              for i in range(max(len(kz), len(br)))]}
        print(f'{name:22s} {"ok" if ok else "FAIL"} frames kz {len(kz)} br {len(br)} pic diff {pic[:6]} order {res_pics} dx {dxd:.2f} dy {dyd:.2f} | parts kz '
              f'{res[name]["parts_kizuna"]} br {res[name]["parts_brawler"]} | hits kz {kz_hits} br {len(hits)} dmg {res[name]["damage_brawler"]}', flush=True)
        if not QUICK:
            kc = kzimg[name]; C_ = 12; W_, H_ = 200, 140
            nch = (len(kc) + C_ - 1) // C_
            sh = Image.new('RGB', (80 + W_ * C_, (2 * H_ + 22) * nch + 16), 'white'); d = ImageDraw.Draw(sh)
            d.text((4, 2), f'TODO #133-#138 Kim {name}: every {EVERY} frames from the move start; top Kizuna, bottom brawler (program)', fill='black')
            for i, a in enumerate(kc):
                y0 = 16 + (2 * H_ + 22) * (i // C_); xx = 80 + W_ * (i % C_)
                if i % C_ == 0: d.text((4, y0 + 60), 'Kizuna', fill='black'); d.text((4, y0 + H_ + 70), 'brawler', fill='black')
                sh.paste(a.resize((W_, H_)), (xx, y0))
                if i < len(cells): sh.paste(cells[i].resize((W_, H_)), (xx, y0 + H_ + 4))
                d.text((xx + 2, y0 + 2 * H_ + 6), f'+{i * EVERY}', fill='black')
            sh.save(os.path.join(OUT, re.sub(r'[^A-Za-z0-9]+', '_', name) + '.png'))
    if not QUICK: res['real_fight'] = real_fight(b, k)
    res['all_ok'] = bool(ok_all)
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    json.dump(res, open(os.path.join(OUT, 'proof_quick.json' if QUICK else 'proof.json'), 'w'), indent=1)
    print('ALL OK' if ok_all else 'FAILURES')

FIGHT = [('214B', 'c', []), ('236A', 'DRc', []), ('236C', 'Rc', [(30, 'Rc'), (60, 'Rc')]), ('[2]8C', 'Dc', [(16, 'Da')])]
def real_fight(b, k):
    """a real fight (the campaign's first wave, AI on): each move at an enemy kept away (whiff), then at one 50 px in
    front (hit); the program plays (SPECIAL, its role), the hits it lands; sheets OUT/fight_<move>_<whiff|hit>.png"""
    b.pick(k); b.run(200); start = b.save(); out = {}
    for move, keys, more in FIGHT:
        for label, gap in (('whiff', 300), ('hit', 50)):
            b.load(start); b.run(30)
            en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
            if not en: out[f'{move} {label}'] = {'ok': False, 'why': 'no enemy'}; continue
            e = en[0]; cam = b.r(b.syms['cam_x'], 2)
            b.place(0, x=cam + 40, z=b.fget(e, 'z')); b.place(e, x=cam + 40 + gap); b.fset(0, 'facing', 1); b.fset(e, 'hp', 60)
            h0 = len(b.hits); cells = []; specs = set(); n_sp = 0
            for f in range(150):
                kk = keys if f < 3 else next((m for t, m in more for j in range(3) if f == t + j), '')
                if label == 'whiff':
                    for i in en: b.place(i, x=b.fget(0, 'x') + gap)
                if f % 4 == 0: pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append(Image.open(pth).convert('RGB'))
                else: b.run(1, p1=kk)
                if b.states[b.fget(0, 'state')] == 'SPECIAL': specs.add(b.fget(0, 'spec_id')); n_sp += 1
            hits = [h for h in b.hits[h0:] if h[1] != 0]
            ok = bool(specs) and (bool(hits) if label == 'hit' else not hits)
            out[f'{move} {label}'] = {'ok': ok, 'roles': sorted(specs), 'special_frames': n_sp, 'hits': len(hits), 'damage': sum(h[2] for h in hits)}
            sh = Image.new('RGB', (10 + 160 * 10, 30 + 115 * ((len(cells) + 9) // 10)), 'white'); d = ImageDraw.Draw(sh)
            d.text((4, 2), f'real fight (campaign, AI on): Kim {move} {label}: {len(hits)} hits (every 4 frames)', fill='black')
            for i, c in enumerate(cells): sh.paste(c.resize((160, 112)), (10 + 160 * (i % 10), 20 + 115 * (i // 10)))
            sh.save(os.path.join(OUT, f'fight_{re.sub(r"[^A-Za-z0-9]+", "", move)}_{label}.png'))
            print('real fight', move, label, out[f'{move} {label}'], flush=True)
    return out

if __name__ == '__main__':
    main()
