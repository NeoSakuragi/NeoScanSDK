#!/usr/bin/env python3
"""Billy's up-forward + C = EX Billy's 214C (note 20261006-160912-b3f3; Bruno 2026-10-12: "the diagonal cane is qcb + P
with EX Billy"), our emulator only (harness.py + the Chain Lab's training mode, one core, this process).

    python3 billy_qcb_proof.py GAME_DIR [OUT]   up-forward + C from idle with the dummy (Ryo) at several gaps, standing and
                                                held in the air (state AIR at a height: a jumping enemy): the special that
                                                starts (the pool's input), Ryo's life lost to it; a screenshot every 2
                                                frames of the 100 px gap, Ryo 70 px up (OUT/ufc_NNN.png, sheet OUT/ufc.png),
                                                the staff object's (PROJ entity) place per frame -> OUT/ufc.json
EX Billy's 214C is an anti-air in KOF98: the staff's attack box rides its tip, high on the diagonal, and misses a standing
opponent at any distance there too (romspecials_check billy:ufD, branches whiff / close / near / mid: KOF98 0 hits). PASS =
it starts everywhere and hits the airborne dummy 80 / 100 / 120 px ahead (nearer, the tip is past him: no hit). Exit status 1 on a FAIL."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
from kyo_round3_proof import sheet

def main(game, out):
    import harness
    harness.GAME = game
    from labdrive import Lab
    os.makedirs(out, exist_ok=True)
    G = json.load(open(os.path.join(game, 'game.json'))); names = [r['name'] for r in G['roster']]
    rr = next(r for r in G['roster'] if r['name'] == 'billy'); want = rr['specials']['ufD']
    CL = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
    pool = [p['input'] for p in next(x for x in CL['fighters'] if x['name'] == 'billy')['pool']]
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))['billy']
    L = Lab(rom=os.path.join(game, 'brawler.neo'), game=game); b = L.b; ST = b.states
    L.start(names.index('billy'), names.index('ryo')); b.run(30); base = b.save()
    res = {'slot': 'specials.ufD', 'want': want, 'tries': []}; ok, air_hit = True, False
    for gap, H in [(g, h) for h in (0, 70) for g in (40, 60, 80, 100, 120)]:
        b.load(base); cam = b.r(b.syms['cam_x'], 2); x0 = cam + 120
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.place(2, x=x0 + gap, z=30); b.fset(2, 'facing', 0xFF)
        b.fset(2, 'hp', 60); b.run(2)
        hp = b.fget(2, 'hp'); starts, hits, rows, cells = [], [], [], []
        for f in range(90):
            k = 'URc' if f < 4 else ''
            if H and f < 40: b.fset(2, 'state', ST.index('AIR')); b.fset(2, 'y', H); b.fset(2, 'vy', 0)
            if f % 2 == 0 and (gap, H) == (100, 70):
                p = os.path.join(out, f'ufc_{f:03d}.png'); b.pad = [set(k), set()]; b.screenshot(p); cells.append((f'f{f}', p))
            else: b.run(1, p1=k)
            s = ST[b.fget(0, 'state')]
            w = f'SPECIAL {pool[b.fget(0, "spec_ix")]}' if s == 'SPECIAL' else s
            if not starts or starts[-1] != w: starts.append(w)
            h = b.fget(2, 'hp')
            if h < hp: hits.append((f, w, hp - h, ST[b.fget(2, 'state')]))
            hp = h
            objs = []
            for j in range(8):
                if ST[b.pget(j, 'state')] != 'PROJ': continue
                fo = b.pget(j, 'frame_ovr')
                objs.append({'x': round(b.pget(j, 'x') - b.fget(0, 'x'), 1), 'h': round(b.pget(j, 'y'), 1),
                             'frame': frames[fo] if fo < len(frames) else fo})
            sf = b.fget(0, 'shown_frame')
            rows.append({'f': f, 'state': w, 'shown': frames[sf] if sf < len(frames) else None, 'objs': objs})
        hit = any(h[1] == f'SPECIAL {want}' for h in hits)
        good = f'SPECIAL {want}' in starts and (hit or not H or gap < 80)   # (the tip passes over a jumper nearer)
        res['tries'].append({'gap': gap, 'height': H, 'hit': hit, 'ok': good, 'starts': starts, 'hits': hits, 'rows': rows})
        if cells: sheet(cells, os.path.join(out, 'ufc.png'), f'Billy up-forward + C ({want}) vs Ryo {gap} px ahead, {H} px up, every 2 frames', cols=9)
        print(gap, H, 'OK' if good else 'FAIL', starts, hits, flush=True)
        ok &= good; air_hit |= hit and H > 0
    ok &= air_hit
    json.dump(res, open(os.path.join(out, 'ufc.json'), 'w'), indent=1)
    print('ufc:', 'OK' if ok else 'FAIL')
    return ok

if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/billy_qcb') else 1)
