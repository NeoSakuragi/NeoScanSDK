#!/usr/bin/env python3
"""SS2 Hanzo's BREAKER in the game's build (Bruno 2026-10-10: the warp move "is going to be his BREAKER special"; the
breaker = always the fighter's neutral C special, docs/brawler_gold.md): game.json hanzo_ss2 specials.D = 63214BCD,
Ninpou Utsusemi (handlers_ss2.han_63214bcd: gone, P_WARP onto his target, the spinning drop). In our emulator
(harness.py; never MAME): the training dummy (Ryo) hits Hanzo, in the reel he presses C or A+B:
  drive full   the breaker starts (SPECIAL, pool 63214BCD), costs game.json meter.breaker chunks of drive, no life,
               blinks white (ovl 1); he reappears on the dummy (x within 10 px of it) and the drop hits it
  no drive     the same move, life_breaker life instead, blinks red (ovl 2)
Neutral C (not in a reel) is the same special, paid as a C special (meter.special chunks).
    python3 tools/samsho2/hanzo_breaker_proof.py [GAME_DIR] [--out /data/tmp/hanzo_ss2]   -> OUT/breaker_proof.json + sheets"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR)
import harness
from labdrive import Lab, PACK_STAT_OFF


def main():
    import argparse
    from PIL import Image
    ap = argparse.ArgumentParser()
    ap.add_argument('game', nargs='?', default=os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))
    ap.add_argument('--out', default='/data/tmp/hanzo_ss2')
    a = ap.parse_args(); game = os.path.abspath(a.game); harness.GAME = game
    G = json.load(open(os.path.join(game, 'game.json'))); M = G['meter']; DFULL = M['chunk'] * M['chunks']
    names = [r['name'] for r in G['roster']]
    CL = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
    pool = [p['input'] for p in next(x for x in CL['fighters'] if x['name'] == 'hanzo_ss2')['pool']]
    L = Lab(rom=os.path.join(game, 'brawler.neo'), game=game); b = L.b; ST = b.states
    L.start(names.index('hanzo_ss2'), names.index('ryo')); b.run(30); base = b.save()
    st = lambda i=0: ST[b.fget(i, 'state')]
    res, ok = {}, True
    for case, drive, keys, reel in (('breaker C, drive full', DFULL, 'c', True), ('breaker A+B, drive full', DFULL, 'ab', True),
                                    ('breaker C, no drive', 0, 'c', True), ('neutral C, drive full', DFULL, 'c', False)):
        got = None
        for dist in (26, 32, 20, 38):
            b.load(base)
            cam = b.r(b.syms['cam_x'], 2); x0 = cam + 120
            b.w(L.lab + PACK_STAT_OFF + 1, 1, 1)          # lab.p1_life: P1's life left to the game
            b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.place(2, x=x0 + dist, z=30); b.fset(2, 'facing', 0xFF)
            b.fset(2, 'hp', 60); b.fset(0, 'drive', drive); b.fset(0, 'hp', 60); b.run(2)
            if reel:
                b.intent(2, press=1, face=0xFF); b.run(1)
                for _ in range(40):
                    if st() == 'HITSTUN': break
                    b.run(1)
                if st() != 'HITSTUN': continue
                for _ in range(20):
                    if not b.fget(0, 'freeze'): break
                    b.run(1)
            hp0, d0, dhp0 = b.fget(0, 'hp'), b.fget(0, 'drive'), b.fget(2, 'hp')
            b.run(1, p1=keys); b.run(1, p1=keys)
            spec = pool[b.fget(0, 'spec_ix')] if st() == 'SPECIAL' and b.fget(0, 'spec_ix') < len(pool) else st()
            ovl, dmin, xs, shots = [], dhp0, [], []
            for k in range(140):
                if st() != 'SPECIAL': break
                ovl.append(b.fget(0, 'ovl')); xs.append(round(b.fget(0, 'x') - b.fget(2, 'x'))); dmin = min(dmin, b.fget(2, 'hp'))
                if k % 8 == 0:
                    p = os.path.join(a.out, '_b.png'); b.screenshot(p); shots.append(Image.open(p).convert('RGB')); os.remove(p)
                b.run(1)
            paid_life = reel and d0 < M['breaker'] * M['chunk']
            cost = M['breaker'] if reel else M['special']
            got = dict(special=spec, drive_spent=d0 - b.fget(0, 'drive') if not paid_life else 0, life_paid=hp0 - b.fget(0, 'hp'),
                       blink=sorted(set(ovl)), nearest_dx=min((abs(x) for x in xs), default=None), dummy_damage=dhp0 - dmin, frames=len(ovl))
            want_blink = 2 if paid_life else 1 if reel else None
            good = spec == '63214BCD' and got['dummy_damage'] > 0 and got['nearest_dx'] is not None and got['nearest_dx'] <= 10 and \
                (got['life_paid'] == M['life_breaker'] if paid_life else got['life_paid'] == 0) and \
                (want_blink is None or want_blink in got['blink'])
            if not paid_life: good = good and got['drive_spent'] >= cost * M['chunk'] - 8   # (the refill pauses in a special)
            got['result'] = 'PASS' if good else 'FAIL'; ok &= good
            if shots:
                W, H = shots[0].size; S = Image.new('RGB', (W * 6, H * ((len(shots) + 5) // 6)))
                for k, im in enumerate(shots): S.paste(im, ((k % 6) * W, (k // 6) * H))
                S.save(os.path.join(a.out, 'breaker_' + case.replace(', ', '_').replace(' ', '_').replace('+', '') + '.png'))
            break
        res[case] = got or {'result': 'FAIL', 'why': 'the dummy never hit him'}; ok &= got is not None
        print(case, res[case], flush=True)
    json.dump(res, open(os.path.join(a.out, 'breaker_proof.json'), 'w'), indent=1)
    print('ALL PASS' if ok else 'SOME FAIL'); sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
