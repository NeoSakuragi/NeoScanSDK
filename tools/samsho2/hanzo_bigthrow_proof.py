#!/usr/bin/env python3
"""The big-victim throw in the GAME's build (not the Lab): SS2 Hanzo (roster hanzo_ss2) walks into a dummy and throws it
with hold + forward + A, in our emulator (harness.py; never MAME). Against Krauser (game.json victim "big") he takes his
big-victim throw (SS2's class 4 action 4, handlers_ss2.throw_big: fighter_t.tbig 1, the victim's script =
hanzo_ss2_bigthrows), against Ryo his slash throw (tbig 0, hanzo_ss2_throws). Per row: the thrower's frames shown (its
throw script), the victim's damage and where it lands; contact sheets OUT/bigthrow_<dummy>.png (every 6th frame).

    python3 tools/samsho2/hanzo_bigthrow_proof.py [GAME_DIR] [--rom brawler.neo] [--out /data/tmp/hanzo_ss2]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR)
import harness
from labdrive import Lab


def main():
    import argparse
    from PIL import Image
    ap = argparse.ArgumentParser()
    ap.add_argument('game', nargs='?', default=os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))
    ap.add_argument('--rom', default='brawler.neo'); ap.add_argument('--build', default='build')
    ap.add_argument('--out', default='/data/tmp/hanzo_ss2')
    a = ap.parse_args(); game = os.path.abspath(a.game); harness.GAME = game
    L = Lab(rom=os.path.join(game, a.rom), game=game, build=a.build); b = L.b; ST = b.states
    names = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    os.makedirs(a.out, exist_ok=True); res = {}; ok = True
    for dummy, want in (('krauser', 1), ('ryo', 0)):
        L.start(names.index('hanzo_ss2'), names.index(dummy)); b.run(30)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 90
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.place(2, x=x0 + 34, z=30); b.fset(2, 'facing', 0xFF); b.run(2)
        for i in range(40):
            b.run(1, p1='R')
            if ST[b.fget(0, 'state')] == 'GRAB': break
        hp0 = b.fget(2, 'hp'); hmin = hp0; shots = []; tbig = thr = None; frames = []; states = []
        for i in range(160):
            b.run(1, p1='Ra' if i < 2 else '')
            s0, s2 = ST[b.fget(0, 'state')], ST[b.fget(2, 'state')]
            if s0 == 'THROW' and tbig is None: tbig = b.fget(0, 'tbig'); thr = b.fget(2, 'thr')
            hmin = min(hmin, b.fget(2, 'hp')); frames.append(b.fget(0, 'frame_ovr')); states.append((s0, s2))
            if i % 6 == 0 and i < 120:
                p = os.path.join(a.out, f'_f{i}.png'); b.screenshot(p); shots.append(Image.open(p).convert('RGB')); os.remove(p)
        big = b.syms.get('hanzo_ss2_bigthrows'); usual = b.syms.get('hanzo_ss2_throws')
        got = {'tbig': tbig, 'victim_script': 'bigthrows' if thr == big else 'throws' if thr is not None and usual <= thr < usual + 64 else hex(thr or 0),
               'damage': hp0 - hmin, 'victim_x_from_thrower': round(b.fget(2, 'x') - b.fget(0, 'x')),
               'thrower_frames': len(set(f for f in frames if f != 0xFFFF)), 'victim_states': sorted({s[1] for s in states})}
        good = tbig == want and got['damage'] > 0 and got['victim_script'] == ('bigthrows' if want else 'throws')
        ok &= good; res[dummy] = dict(got, result='PASS' if good else 'FAIL')
        print(dummy, res[dummy], flush=True)
        W, H = shots[0].size; sheet = Image.new('RGB', (W * 5, H * ((len(shots) + 4) // 5)))
        for k, im in enumerate(shots): sheet.paste(im, ((k % 5) * W, (k // 5) * H))
        sheet.save(os.path.join(a.out, f'bigthrow_{dummy}.png'))
    json.dump(res, open(os.path.join(a.out, 'bigthrow_proof.json'), 'w'), indent=1)
    print('ALL PASS' if ok else 'SOME FAIL'); sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
