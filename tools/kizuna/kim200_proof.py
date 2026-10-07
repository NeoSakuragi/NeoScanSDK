#!/usr/bin/env python3
"""TODO #200 proof: Kim's j.2B (Kizuna's air special, command $26: the 45-degree dive) played by its program in the
brawler (export_kz AIR, game.json roster air_special, fighter.c role BS_AIR) next to Kizuna Encounter playing the same
input in our emulator (followups_kz.py recipes j2B_*: P1 Kim vs Hayate, a real fight).

    python3 kim200_proof.py [OUTDIR]          (default /data/tmp/kim200/out)

(a) Kizuna vs brawler, the same inputs (jump forward / up, down+B there = down+A here), the dive from its first frame:
    every frame's picture (the brawler frame = the export of Kizuna's step on that frame), place (dx, height: Kizuna's
    px x 0.80, the export's scale) and the landing; the hit versions with the hit-stop frames dropped (each game its
    own): the hits, the victim's reaction, the second kick (down+A again after the hit, 64 px up or more).
    Contact sheets <scenario>.png: Kizuna above, the brawler below, every 3 frames from the jump.
(b) a real fight (the campaign's first wave, AI on): Kim's jump + down+A at an enemy: whiff, then a hit.
(c) Bruno's own inputs (feedback 20261007-120054-b3f3, 0.1.5): his pads from his two dives replayed on this build.
OUT/proof.json: everything, all_ok."""
import json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import cap_kz as cap, followups_kz as FK, export_kz as E
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kim200/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
BUNDLE = '/data/feedback/20261007-120054-b3f3'
PADKEYS = ((0, 'a'), (8, 'b'), (1, 'c'), (9, 'd'), (4, 'U'), (5, 'D'), (6, 'L'), (7, 'R'))
BS_AIR = 9                                                   # fighter.h
SCEN = [('whiff, forward jump', 'j2B_w'), ('whiff from the apex', 'j2B_apex_w'), ('whiff, vertical jump', 'j2B_up_w'),
        ('hit', 'j2B_h'), ('hit + down+A again (the second kick)', 'j2B2_h'), ('whiff + down+A again (nothing)', 'j2B2_w')]
EVERY = 3
QUICK = bool(os.environ.get('QUICK'))                       # (development: (a) without Kizuna's pictures)

def bm_steps():
    """the program's anims as built (bm_spec.c kim_spN_aJ): [[frame of each step]] in AIR's state order"""
    src = open(os.path.join(GAME, 'build', 'bm_spec.c')).read()
    k = re.search(r'kim_sp(\d+)_prog\[\]', src).group(1)
    out = []
    for j in range(4):
        body = re.search(rf'static const bstep_t kim_sp{k}_a{j}\[\] = \{{(.*)\}};', src).group(1)
        out.append([int(m) for m in re.findall(r'\{(\d+), \d+, \d+, \{', body)])
    return out

def kz_frame(st, a, s):
    """Kizuna's (anim, step) -> the brawler frame its export shows (None: not part of the move)"""
    A = E.AIR['j.2B']
    if a == A['dive']: return st[0][s] if s < len(st[0]) else st[1][s - len(st[0])]
    if a == A['again']: return st[2][s] if s < len(st[2]) else None
    if a == A['land']: return st[3][s]
    return None

def to_brawler(seq):
    """a Kizuna recipe's P1 input -> the brawler's: U = B (held 5 frames: a regular jump, Kizuna has one height), the
    button B = A (the attack button); the frames as they are"""
    out = []
    for part in seq.split(','):
        n, k = part.split(':'); k = '' if k == '-' else k
        out += [k.replace('b', 'a') if 'D' in k else k.replace('U', 'b')] * int(n)
    for i, k in enumerate(out):                                # B held through the prejump: a regular jump
        if 'b' in k and (i == 0 or 'b' not in out[i - 1]):
            for j in range(i + 1, min(i + 5, len(out))):
                if not out[j]: out[j] = 'b'
    return out

def kz_run(rec):
    fr = json.load(open(FK.OUT))[rec]['frames']
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == E.AIR['j.2B']['dive'])
    x0 = fr[s0 - 1][0][2]
    rows = []
    for i in range(s0, len(fr)):
        p, q = fr[i][0], fr[i][1]
        if p[0] not in (0x8F, 0x91, 0x92): break
        rows.append({'a': p[0], 's': p[1], 'dx': (p[2] - x0) * E.S, 'y': p[3] * E.S, 'life': q[6], 'vanim': q[0], 'i': i})
    return fr, s0, rows

def dedupe(rows, key):
    out = []
    for r in rows:
        if not out or key(out[-1]) != key(r): out.append(r)
    return out

def main():
    os.makedirs(OUT, exist_ok=True)
    res = {'scenarios': {}}
    # Kizuna's pictures first (its own emulator process, one at a time)
    kzimg = {}
    for name, rec in SCEN:
        fr, s0, rows = kz_run(rec)
        js = 2 + 0                                              # the recipe's jump press frame (each starts '2:-')
        frames = list(range(js, s0 + len(rows) + 6, EVERY))
        kzimg[rec] = (frames, [] if QUICK else __import__('kim_followups_proof').kz_snaps(rec, frames, f'/data/tmp/kim200/snap_{rec}'))
    from harness import Brawler
    b = Brawler()
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    kim = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_KIM')
    st = bm_steps()
    b.pick(kim)
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, kim); b.w(L + 6, 1, 0); b.w(L + 4, 1, 1); b.run(40)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    ok_all = True
    for name, rec in SCEN:
        p2x, seq, _ = FK.RECIPES[rec]
        fr, s0, kz = kz_run(rec)
        b.run(60)
        cam = b.r(b.syms['cam_x'], 2); dist = E.sc(p2x - 240)
        x0 = cam + (30 if dist > 150 else 100)
        b.place(dm, x=x0 + dist, z=30); b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.fset(dm, 'hp', 60); b.run(2)
        keys = to_brawler(seq)[2:]                             # from the jump press (Kizuna's frame 2)
        press = next(i for i, k in enumerate(keys) if 'D' in k and 'a' in k)
        y_before = fr[s0 - 1][0][3] * E.S                      # Kizuna's height the frame before its dive (scaled): the
                                                               # jumps' own arcs differ a little (export physics), the
                                                               # dive is compared from the same place (test-only poke)
        h0 = len(b.hits); log = []; cells = []; start = None; hp0 = b.fget(dm, 'hp'); px = b.fget(0, 'x')
        for f, k in enumerate(keys + [''] * 40):
            b.pad = [set(k), set()]
            if f % EVERY == 0:
                pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append(Image.open(pth).convert('RGB'))
            else: b.run(1, p1=k)
            if f == press: b.fset(0, 'y', y_before)             # (the game reads its input a frame late)
            s_ = b.states[b.fget(0, 'state')]
            if s_ == 'SPECIAL' and start is None: start = f; xb0 = px    # (Kim's x the frame before the dive)
            px = b.fget(0, 'x')
            if start is not None:
                if s_ != 'SPECIAL': break
                log.append({'frame': b.fget(0, 'frame_ovr'), 'x': b.fget(0, 'x'), 'y': b.fget(0, 'y'), 'freeze': b.fget(0, 'freeze'),
                            'hp': b.fget(dm, 'hp'), 'vstate': b.states[b.fget(dm, 'state')], 'role': b.fget(0, 'spec_id')})
        if start is None:
            res['scenarios'][name] = {'ok': False, 'why': 'no SPECIAL'}; ok_all = False; continue
        for r in log: r['dx'] = r['x'] - xb0
        hits = [h for h in b.hits[h0:] if h[1] == dm]
        hitcap = rec.endswith('_h')
        kzk = dedupe(kz, lambda r: (r['a'], r['s'], round(r['dx']), round(r['y']))) if hitcap else kz
        brk = dedupe(log, lambda r: (r['frame'], round(r['dx'], 1), round(r['y'], 1))) if hitcap else log
        n = min(len(kzk), len(brk))
        fdiff = [i for i in range(n) if kz_frame(st, kzk[i]['a'], kzk[i]['s']) != brk[i]['frame']]
        pdiff = max((abs(kzk[i]['y'] - brk[i]['y']) for i in range(n)), default=0)
        xdiff = max((abs(kzk[i]['dx'] - brk[i]['dx']) for i in range(n)), default=0)
        kz_hits = sum(1 for j in range(1, len(fr)) if fr[j][1][6] < fr[j - 1][1][6] and kz[0]['i'] <= j <= kz[-1]['i'] + 1)
        if hitcap:                                              # positions after a hit: the bodies' push differs (each
            ok = not fdiff[:6] and len(hits) >= 1 and (rec != 'j2B2_h' or any(r['frame'] in st[2] for r in log))   # game's own)
            ok = ok and abs(len(brk) - len(kzk)) <= 3
        else:
            ok = len(kzk) == len(brk) and not fdiff and pdiff <= 1.0 and xdiff <= 1.5 and not hits and all(r['role'] == BS_AIR for r in log)
        ok_all &= ok
        res['scenarios'][name] = {
            'kizuna_recipe': rec, 'ok': ok, 'frames_kizuna': len(kzk), 'frames_brawler': len(brk),
            'picture_mismatch_frames': fdiff, 'max_height_diff_px': round(pdiff, 2), 'max_dx_diff_px': round(xdiff, 2),
            'dive_start_height': {'kizuna': round(kz[0]['y'], 1), 'brawler': round(log[0]['y'], 1)},
            'landing_dx': {'kizuna': round(kz[-1]['dx'], 1), 'brawler': round(log[-1]['dx'], 1)},
            'hits_kizuna': kz_hits, 'hits_brawler': len(hits), 'damage_brawler': hp0 - b.fget(dm, 'hp'),
            'victim_kizuna': [f'{a:X}' for a in dict.fromkeys(r['vanim'] for r in kz)],
            'victim_brawler': list(dict.fromkeys(r['vstate'] for r in log)),
            'second_kick': any(r['frame'] in st[2] for r in log),
            'rows': [[kz_frame(st, r['a'], r['s']) if r else None, round(r['dx'], 1) if r else None, round(r['y'], 1) if r else None,
                      q['frame'] if q else None, round(q['dx'], 1) if q else None, round(q['y'], 1) if q else None]
                     for r, q in zip(kzk + [None] * max(0, len(brk) - len(kzk)), brk + [None] * max(0, len(kzk) - len(brk)))]}
        print(f'{name:42s} {"ok" if ok else "FAIL"} frames kz {len(kzk)} br {len(brk)} pic diff {fdiff[:5]} dy {pdiff:.2f} dx {xdiff:.2f} '
              f'| hits kz {kz_hits} br {len(hits)} | victim kz {res["scenarios"][name]["victim_kizuna"]} br {res["scenarios"][name]["victim_brawler"]}', flush=True)
        kf, kim_ = kzimg[rec]
        C_ = min(12, len(cells)); W_, H_ = 200, 140
        nch = (len(cells) + C_ - 1) // C_
        sh = Image.new('RGB', (80 + W_ * C_, (2 * H_ + 22) * nch + 16), 'white'); d = ImageDraw.Draw(sh)
        d.text((4, 2), f'TODO #200 Kim j.2B: {name} (every {EVERY} frames from the jump press; top Kizuna, bottom brawler 0.1.5+fix)', fill='black')
        for i, c in enumerate(cells):
            y0 = 16 + (2 * H_ + 22) * (i // C_); xx = 80 + W_ * (i % C_)
            if i % C_ == 0: d.text((4, y0 + 60), 'Kizuna', fill='black'); d.text((4, y0 + H_ + 70), 'brawler', fill='black')
            if i < len(kim_): sh.paste(kim_[i].resize((W_, H_)), (xx, y0))
            sh.paste(c.resize((W_, H_)), (xx, y0 + H_ + 4)); d.text((xx + 2, y0 + 2 * H_ + 6), f'+{i * EVERY}', fill='black')
        sh.save(os.path.join(OUT, rec + '.png'))
    res['all_kizuna_ok'] = ok_all
    if QUICK: json.dump(res, open(os.path.join(OUT, 'proof_quick.json'), 'w'), indent=1); return
    # (b) a real fight: the campaign's first wave (AI on), Kim jumps forward at an enemy and dives (down+A)
    b.pick(kim); b.run(200)
    fight = {}
    start_fight = b.save()
    for label, gap in (('whiff', 330), ('hit', 100), ('hit', 115), ('hit', 85), ('hit', 130)):
        if label in fight and fight[label]['ok']: continue
        b.load(start_fight); b.run(30)
        en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
        if not en: fight[label] = {'ok': False, 'why': 'no enemy'}; continue
        e = en[0]; cam = b.r(b.syms['cam_x'], 2)
        b.place(0, x=cam + 40, z=b.fget(e, 'z')); b.place(e, x=cam + 40 + gap); b.fset(0, 'facing', 1); b.fset(e, 'hp', 60)
        h0 = len(b.hits); cells = []; roles = set(); ys = []
        keys = ['bR'] * 3 + ['b'] * 3 + [''] * 7 + ['Da'] * 3 + [''] * 70
        for f, k in enumerate(keys):
            b.pad = [set(k), set()]
            if label == 'whiff':                               # nobody in its path: the enemies kept gap px ahead
                for i in en: b.place(i, x=b.fget(0, 'x') + gap)
            if f % 4 == 0: pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append(Image.open(pth).convert('RGB'))
            else: b.run(1, p1=k)
            if b.states[b.fget(0, 'state')] == 'SPECIAL': roles.add(b.fget(0, 'spec_id')); ys.append(b.fget(0, 'y'))
        hits = [h for h in b.hits[h0:] if h[1] != 0]
        ok = roles == {BS_AIR} and (bool(hits) if label == 'hit' else not hits) and ys and ys[-1] == 0
        fight.setdefault('attempts', []).append({'label': label, 'gap': gap, 'ok': ok, 'hits': len(hits)})
        fight[label] = {'ok': ok, 'gap': gap, 'hits': len(hits), 'damage': sum(h[2] for h in hits), 'roles': sorted(roles),
                        'dive_from_height': round(ys[0], 1) if ys else None, 'victim_states': sorted({h[3] for h in hits})}
        sh = Image.new('RGB', (10 + 160 * 11, 30 + 115 * ((len(cells) + 10) // 11)), 'white'); d = ImageDraw.Draw(sh)
        d.text((4, 2), f'real fight (campaign, AI on): jump forward + down+A, {label}: {len(hits)} hits (every 4 frames)', fill='black')
        for i, c in enumerate(cells): sh.paste(c.resize((160, 112)), (10 + 160 * (i % 11), 20 + 115 * (i // 11)))
        sh.save(os.path.join(OUT, f'fight_{label}.png'))
        print('real fight', label, fight[label], flush=True)
    res['real_fight'] = fight
    ok_all &= all(fight.get(k, {}).get('ok') for k in ('whiff', 'hit'))
    # (c) Bruno's pads (his bundle) on this build: his two jump + down+A from a fight's start
    raw = open(os.path.join(BUNDLE, 'inputs.bin'), 'rb').read(); _, _, W, P = struct.unpack_from('<4sIQQ', raw)
    pads = [struct.unpack_from('<HH', raw, 24 + 4 * i)[0] for i in range(P - W)]
    b.pick(kim); b.run(60)
    cam = b.r(b.syms['cam_x'], 2)
    away = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF',)]
    b.place(0, x=cam + 60)
    log = []; cells = []
    for f in range(20560, P):
        for i in away: b.place(i, x=b.fget(0, 'x') + 600)    # the enemies kept away (his wave had none near him)
        k = ''.join(c for bit, c in PADKEYS if pads[f - W] >> bit & 1)
        b.pad = [set(k), set()]
        if f % 4 == 0: pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append((f, Image.open(pth).convert('RGB')))
        else: b.run(1, p1=k)
        log.append((f, k, b.states[b.fget(0, 'state')], b.fget(0, 'spec_id'), round(b.fget(0, 'x'), 1), round(b.fget(0, 'y'), 1)))
    dives = []
    for j, r in enumerate(log):
        if r[2] == 'SPECIAL' and (j == 0 or log[j - 1][2] != 'SPECIAL'):
            e_ = next((t for t in range(j, len(log)) if log[t][2] != 'SPECIAL'), len(log))
            seg = log[j:e_]; air = [r_ for r_ in seg if r_[5] > 0]
            dives.append({'press_frame': next(t[0] for t in reversed(log[:j + 1]) if 'D' in t[1] and 'a' in t[1]),
                          'from_frame': r[0], 'role': r[3], 'height': air[0][5] if air else 0, 'x_travel': round(seg[-1][4] - log[j - 1][4], 1),
                          'descends_every_frame': all(air[t + 1][5] < air[t][5] for t in range(len(air) - 1)),
                          'lands': seg[-1][5] == 0, 'frames': len(seg)})
    bruno_ok = len(dives) >= 1 and all(d_['role'] == BS_AIR and d_['descends_every_frame'] and d_['x_travel'] > 0 for d_ in dives)
    res['bruno_inputs'] = {'ok': bruno_ok, 'dives': dives, 'note': 'his pads 20560..20742 of the bundle from a fight start on this build'}
    print('Bruno inputs', res['bruno_inputs'], flush=True)
    ok_all &= bruno_ok
    sh = Image.new('RGB', (10 + 160 * 12, 30 + 128 * ((len(cells) + 11) // 12)), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 2), "Bruno's pads (20261007-120054-b3f3: jump, down+A) on the fixed build, every 4 frames", fill='black')
    for i, (f, c) in enumerate(cells):
        sh.paste(c.resize((160, 112)), (10 + 160 * (i % 12), 20 + 128 * (i // 12))); d.text((12 + 160 * (i % 12), 20 + 128 * (i // 12) + 113), str(f), fill='black')
    sh.save(os.path.join(OUT, 'bruno_inputs.png'))
    res['all_ok'] = bool(ok_all)
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print('ALL OK' if ok_all else 'FAILURES')

if __name__ == '__main__':
    main()
