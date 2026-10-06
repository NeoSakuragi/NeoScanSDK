#!/usr/bin/env python3
"""TODO #144 proof: Kim's specials whose effect objects the export now carries (export_kz.effects: the Hienzan
pillar '503 EFFE', 214B / 236A's 'ADH EFFE', 421A's afterimages ZANZO1 / 2) played in the brawler (harness, the
Chain Lab's standing dummy, whiff) next to Kizuna (our emulator, the recipe the export took them from).

    python3 kim144_proof.py [OUTDIR]        (default /data/tmp/kim144/out)

Per move: every frame of the special, the effect entities Kim owns (projectiles[], fighter.c: state PROJ, frame,
place from Kim) vs the export's rows for that script row (frame identical, place within 1 px), and a contact sheet
OUT/<move>.png (top Kizuna, bottom the brawler, every 3 frames from the move's first frame) -> OUT/kim144.json."""
import json, os, sys, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import cap_kz as cap, capture_kz, followups_kz
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kim144/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
MOVES = [('[2]8C', 'Dc', 'fol', '28C_w', 0x9B), ('214B', 'c', 'cap', 'sw_214B', 0x93), ('236A', 'DRc', 'cap', 'sw_236A', 0x126),
         ('421A', 'Uc', 'fol', '421A_w', 0x100)]
EVERY = 3

def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)

def kz_snaps(src, rec, frames, d):
    os.makedirs(d, exist_ok=True)
    if src == 'fol':
        p2x, seq, pokes = followups_kz.RECIPES[rec][:3]; pin = followups_kz.PIN; seq2 = ''
    else:
        p2x, seq, seq2 = capture_kz.RECIPES[rec]; pokes = None; pin = cap.nframes(seq)
    pk = [f'{f}:' + ','.join(([f'108424={p2x >> 8:02X},108425={p2x & 255:02X}'] if f < pin and p2x else []) + ([pokes] if pokes else []))
          for f in range(cap.nframes(seq))]
    pk = [p for p in pk if not p.endswith(':')]
    cap.run(seq, seq2, pokes=';'.join(pk) or None, extra={'SNAPS': ','.join(map(str, frames)), 'SNAPDIR': d}, n=4)
    return [Image.open(f'{d}/snap_{f}.ppm').convert('RGB') if os.path.exists(f'{d}/snap_{f}.ppm') else Image.new('RGB', (320, 224)) for f in frames]

def main():
    os.makedirs(OUT, exist_ok=True)
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_kizuna_kim', 'kof95_export.json')))['characters']['kim']
    caps = {'cap': json.load(open(capture_kz.OUT)), 'fol': json.load(open(followups_kz.OUT))}
    b = Brawler()
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    k = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_KIM')
    b.pick(k)
    S_PROJ = b.states.index('PROJ'); kim_addr = b.base
    res, ok_all = {}, True
    for move, keys, src, rec, anim0 in MOVES:
        sp = next(s for s in ex['specials'] if s['input'] == move)
        effs = [p for p in sp['projectiles'] if p.get('effect')]
        lab_req(b, 1, k, 0); b.run(40)
        dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
        b.place(0, x=60, z=b.fget(dm, 'z')); b.place(dm, x=296); b.fset(0, 'facing', 1); b.run(5)
        cells, started, rows_seen, bad, shown = [], False, 0, [], 0
        for f in range(200):
            b.run(1, p1=keys if f < 3 else '')
            st = b.states[b.fget(0, 'state')]
            if st != 'SPECIAL':
                if started: break
                continue
            if not started: started = True; t0 = f
            row = b.fget(0, 'srow') - 1
            want = sorted((p['rows'][row - p['spawn_row']][0], p['rows'][row - p['spawn_row']][1], p['rows'][row - p['spawn_row']][2])
                          for p in effs if 0 <= row - p['spawn_row'] < len(p['rows']))
            got = []
            kx, ky = b.fget(0, 'x'), b.fget(0, 'y')
            for i in range(8):
                if b.pget(i, 'state') == S_PROJ and b.pget(i, 'owner') == kim_addr and b.pget(i, 'frame_ovr') != 0xFFFF:
                    if any(b.pget(i, 'frame_ovr') == r[0] for p in effs for r in p['rows']):
                        got.append((b.pget(i, 'frame_ovr'), round(b.pget(i, 'x') - kx), round(b.pget(i, 'y') - ky)))
            got.sort(); rows_seen += 1; shown += len(got)
            if [g[0] for g in got] != [w[0] for w in want] or any(abs(g[1] - w[1]) > 1 or abs(g[2] - w[2]) > 1 for g, w in zip(got, want)):
                bad.append((row, got, want))
            if (f - t0) % EVERY == 0:
                p = os.path.join(OUT, '_shot.png'); b.screenshot(p); cells.append(Image.open(p).convert('RGB').resize((160, 112)))
        fr = caps[src][rec]['frames']
        s0 = next(i for i, x in enumerate(fr) if x[0][0] == anim0)
        # (a snap N shows the frame of capture row N - 2 [meas: the pillar first at snap 50, row 48])
        kzc = [im.resize((160, 112)) for im in kz_snaps(src, rec, [s0 + 2 + EVERY * i for i in range(len(cells))], f'/data/tmp/kim144/snap_{rec}')]
        C_ = 12; nch = (len(cells) + C_ - 1) // C_
        sh = Image.new('RGB', (90 + 160 * C_, 240 * nch + 14), 'white'); d = ImageDraw.Draw(sh)
        d.text((4, 2), f'{move} whiff (every {EVERY} frames from the move start): Kizuna above, the brawler below', fill='black')
        for i, (a, c) in enumerate(zip(kzc, cells)):
            y0 = 14 + 240 * (i // C_); x0 = 90 + 160 * (i % C_)
            if i % C_ == 0: d.text((4, y0 + 50), 'Kizuna', fill='black'); d.text((4, y0 + 170), 'brawler', fill='black')
            sh.paste(a, (x0, y0)); sh.paste(c, (x0, y0 + 116))
        sh.save(os.path.join(OUT, move.replace('[', '').replace(']', '') + '.png'))
        ok = started and not bad and shown > 0
        ok_all &= ok
        res[move] = {'rows': rows_seen, 'effect_frames_shown': shown, 'effects': [(p['name'], p['spawn_row'], len(p['rows'])) for p in effs],
                     'mismatch': bad[:5], 'ok': ok}
        print(f'{move:6s} rows {rows_seen} effect frames shown {shown} effects {res[move]["effects"]} {"ok" if ok else "FAIL"} {bad[:3]}')
    json.dump({'all_ok': ok_all, 'moves': res}, open(os.path.join(OUT, 'kim144.json'), 'w'), indent=1)
    print('all ok' if ok_all else 'FAILURES')

if __name__ == '__main__':
    main()
