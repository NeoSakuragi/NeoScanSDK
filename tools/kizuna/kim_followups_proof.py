#!/usr/bin/env python3
"""Kim's multipart moves (export_kz FOLLOW, fighter.c "follow-ups") played in the brawler (harness: the game's ROM on the
Geolith core, the Chain Lab's standing dummy) next to Kizuna Encounter playing the same thing (our emulator, the
followups_kz.py recipes): whiff and connect, every follow-up input, both facings for the connect versions.

    python3 kim_followups_proof.py [OUTDIR]        (default /data/tmp/kimseq/out)

Per scenario: the parts the brawler played (bspec_t.parts, in order) vs the parts Kizuna played (its animations), the
hits on the dummy, the victim's place during a carried part vs Kizuna's (export carry), a contact sheet
OUT/<scenario>.png (top row Kizuna every N frames from the move's start, bottom row the brawler) and OUT/proof.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import cap_kz as cap, followups_kz as FK
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kimseq/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
# scenario: (keys that start it, dummy distance, follow-up presses [(part, keys, needs a hit)], Kizuna recipe, Kizuna's
# animations per part (to read its part sequence), the brawler parts expected)
KZ_PARTS = {'236C': [(0x97, 0x8E), (0x99,), (0x98,), (0x9A,)], '[2]8C': [(0x9B,), (0x9C, 0x9E), (0x9D, 0x9E)],
            '421A': [(0x100,), (0x101,)], '6246A': [(0x85,), (0x86, 0x88, 0x89)]}
SC = [('236C whiff', '236C', 'Rc', 250, [], '236C_w', [0, 1]),
      ('236C hit', '236C', 'Rc', 60, [], '236C_h', [0, 1]),
      ('236C x2 whiff', '236C', 'Rc', 250, [(0, 'Rc', 0)], '236C2_w', [0, 2, 1]),
      ('236C x2 hit', '236C', 'Rc', 60, [(0, 'Rc', 0)], '236C2_h', [0, 2, 1]),
      ('236C x3 whiff', '236C', 'Rc', 250, [(0, 'Rc', 0), (2, 'Rc', 0)], '236C3_w', [0, 2, 3, 1]),
      ('236C x3 hit', '236C', 'Rc', 60, [(0, 'Rc', 0), (2, 'Rc', 0)], '236C3_h', [0, 2, 3, 1]),
      ('[2]8C hit', '[2]8C', 'Dc', 50, [], '28C_h', [0, 1]),
      ('[2]8C down+A whiff', '[2]8C', 'Dc', 250, [(0, 'Da', 0)], '28C2_w', [0, 1]),
      ('[2]8C down+A hit', '[2]8C', 'Dc', 50, [(0, 'Da', 1)], '28C2_h', [0, 2]),
      ('421A whiff', '421A', 'Uc', 250, [], '421A_w', [0]),
      ('421A hit', '421A', 'Uc', 70, [], '421A_h', [0, 1]),
      ('6246A whiff', '6246A', 'd', 250, [], '6246A_w', [0]),
      ('6246A hit', '6246A', 'd', 60, [], '6246A_h', [0, 1])]

def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)

def kz_parts(fr, parts):
    seq = []
    for f in fr:
        a = f[0][0]
        k = next((i for i, an in enumerate(parts) if a in an and (not seq or i == seq[-1] or i not in seq)), None)
        if k is not None and (not seq or seq[-1] != k):
            if a == 0x9E and seq and seq[-1] in (1, 2): continue      # 9E belongs to the part already playing
            seq.append(k)
    return seq

def kz_snaps(rec, frames, d):
    p2x, seq, pokes = FK.RECIPES[rec]
    n = cap.nframes(seq); pk = []
    for f in range(n):
        s = ([f'108424={p2x >> 8:02X},108425={p2x & 255:02X}'] if f < FK.PIN else []) + ([pokes] if pokes else [])
        if s: pk.append(f'{f}:' + ','.join(s))
    os.makedirs(d, exist_ok=True)
    cap.run(seq, '', pokes=';'.join(pk), extra={'SNAPS': ','.join(map(str, frames)), 'SNAPDIR': d}, n=4)
    return [Image.open(f'{d}/snap_{f}.ppm').convert('RGB') if os.path.exists(f'{d}/snap_{f}.ppm') else Image.new('RGB', (320, 224)) for f in frames]

def main():
    os.makedirs(OUT, exist_ok=True)
    fc = json.load(open(FK.OUT))
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_kizuna_kim', 'kof95_export.json')))['characters']['kim']
    carry = {sp['input']: sp for sp in ex['specials']}
    b = Brawler()
    import re
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    k = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_KIM')
    b.pick(k)
    res = {}; ok_all = True
    for name, move, keys, dist, follow, rec, want in SC:
        for facing in ((1, -1) if 'hit' in name else (1,)):
            lab_req(b, 1, k, 0); b.run(40); b.fset(0, 'meter', 120)
            dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
            # the lab clamps everyone to the screen (x 24 .. 296): a whiff from the far edge, a connect with room for the
            # victim to fly forward (Kizuna's flights reach 160 px)
            dx_ = (296, 296 - dist) if dist > 100 else (130, 130 - dist)
            if facing < 0: dx_ = (320 - dx_[0], 320 - dx_[1])
            b.place(dm, x=dx_[0]); b.place(0, x=dx_[1], z=b.fget(dm, 'z')); b.fset(0, 'facing', facing & 0xFF); b.run(5)
            R = 'R' if facing > 0 else 'L'
            k0 = keys.replace('R', R)
            h0 = len(b.hits); parts = []; cells = []; pressed = set(); vdev = []; landed_rows = []
            started = False; t = 0; log = []; end_f = None
            sp = carry[move]
            for f in range(420):
                p = ''
                if f < 3: p = k0
                st = b.states[b.fget(0, 'state')]
                if st == 'SPECIAL':
                    started = True
                    part, row = b.fget(0, 'spart'), b.fget(0, 'srow') - 1
                    if not parts or parts[-1] != part: parts.append(part)
                    for j, (fp, fk, needhit) in enumerate(follow):
                        lk = next(l for l in sp['links'] if l['from'] == fp)
                        if j not in pressed and part == fp and lk['window'][0] + (0 if needhit else 2) <= row < lk['window'][1] - 2 and (not needhit or b.fget(0, 'shrow') > lk['window'][0]):   # after a hit inside the window (Kizuna: the window opens on it)
                            pressed.add(j); p = fk.replace('R', R); t = 4   # held 4 frames
                    cv = sp['carry_src'][row] if 0 <= row < len(sp['carry_src']) else None
                    if cv and b.fget(0, 'landed') and b.states[b.fget(dm, 'state')] in ('KNOCKDOWN', 'HITSTUN') and 24 < int(b.fget(dm, 'x')) < 296:   # not held by the lab's screen edges
                        vdev.append(abs((b.fget(dm, 'x') - b.fget(0, 'x')) * facing - cv[0]) + abs(b.fget(dm, 'y') - cv[1]))
                    log.append((f, part, row, int(b.fget(0, 'x')), int(b.fget(0, 'y')), b.states[b.fget(dm, 'state')], int(b.fget(dm, 'x')), int(b.fget(dm, 'y'))))
                elif started and st != 'SPECIAL':
                    end_f = f if end_f is None else end_f
                    if f > end_f + 40: break
                if t and not p: p = follow[max(pressed)][1].replace('R', R); t -= 1
                elif t: t -= 1
                b.run(1, p1=p)
                if f % 6 == 0 and facing > 0:
                    pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append(Image.open(pth).resize((160, 112)))
            hits = [(h[0], h[2], h[3]) for h in b.hits[h0:] if h[1] == dm]
            key = f'{name} {"right" if facing > 0 else "left"}'
            kzp = kz_parts(fc[rec]['frames'], KZ_PARTS[move])
            ok = parts == want and kzp == want
            ok_all &= ok
            res[key] = {'parts': parts, 'kizuna_parts': kzp, 'expected': want, 'ok': ok, 'hits': hits,
                        'kizuna_hits': sum(1 for j in range(1, len(fc[rec]['frames'])) if fc[rec]['frames'][j][1][6] < fc[rec]['frames'][j - 1][1][6]),
                        'carry_max_dev_px': max(vdev) if vdev else None, 'carry_frames': len(vdev),
                        'max_height': max((r[4] for r in log), default=0), 'victim_states': list(dict.fromkeys(r[5] for r in log))}
            print(f'{key:28s} parts {parts} kizuna {kzp} want {want} {"ok" if ok else "FAIL"} | hits {len(hits)} dmg {sum(h[1] for h in hits)} '
                  f'| kizuna life drops {res[key]["kizuna_hits"]} | carry dev {res[key]["carry_max_dev_px"]} over {len(vdev)} | victim {res[key]["victim_states"]}')
            if facing > 0:
                s0 = next(i for i, fr_ in enumerate(fc[rec]['frames']) if fr_[0][0] == KZ_PARTS[move][0][0])
                kzc = [im.resize((160, 112)) for im in kz_snaps(rec, [s0 + 6 * i for i in range(len(cells))], f'/data/tmp/kimseq/snap_{rec}')]
                C_ = 12; nch = (len(cells) + C_ - 1) // C_          # wrapped: pairs of rows (Kizuna above, brawler below)
                sh = Image.new('RGB', (90 + 160 * C_, 240 * nch + 14), 'white'); d = ImageDraw.Draw(sh)
                d.text((4, 2), name + ' (every 6 frames from the move start)', fill='black')
                for i, (a, c) in enumerate(zip(kzc, cells)):
                    y0 = 14 + 240 * (i // C_); x0 = 90 + 160 * (i % C_)
                    if i % C_ == 0: d.text((4, y0 + 50), 'Kizuna', fill='black'); d.text((4, y0 + 170), 'brawler', fill='black')
                    sh.paste(a, (x0, y0)); sh.paste(c, (x0, y0 + 116))
                sh.save(os.path.join(OUT, name.replace(' ', '_').replace('[', '').replace(']', '').replace('+', '') + '.png'))
            json.dump(log, open(os.path.join(OUT, '_log_' + key.replace(' ', '_') + '.json'), 'w'))
    json.dump({'all_ok': ok_all, 'scenarios': res}, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print('all ok' if ok_all else 'FAILURES')

if __name__ == '__main__':
    main()
