#!/usr/bin/env python3
"""Genjuro's three-part slash (236S, his forward+C) in the brawler: the follow-ups (vocabulary branch.on_input, the
ROM's type-5 cancel: a connect + a window step, handlers_ss2.gen_236s) proven in the harness (Chain Lab training).

    python3 chain_proof_ss2.py [OUT]       (default /data/tmp/ss2/out) -> OUT/chain_genjuro.json

Cases, the dummy 48 px ahead (the slash connects) or 150 px behind (it whiffs): forward+C alone; forward+C then C
pressed every other frame (the follow-up press); per case the SS2 animations P1 shows (the special's frames mapped
back to the export's animations) and the dummy's hits. Pass: whiff = part 1 only whatever is pressed (no connect,
no cancel: SS2's +$103 rule); connect + presses = parts 2 (366) and 3 (369) follow; connect, no press = part 1 only."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
from harness import Brawler
import ss2_proof as P

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/ss2/out'
GAME = P.GAME

def main():
    b = Brawler()
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    k = bcs.index('BC_GENJURO')
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_samsho2_genjuro', 'kof95_export.json')))['characters']['genjuro']
    sp = next(s for s in ex['specials'] if s['input'] == '236S')
    of = {}                                            # exported frame -> SS2 animation of the special's states
    for st, a in sp['rom']['anims'].items():
        for s in a['steps']: of.setdefault(s['frame'], a['ss2'])
    b.pick(k)
    res = {}
    for case, dist, again in (('whiff', -150, True), ('connect', 48, False), ('connect+C', 48, True)):
        P.lab_req(b, 1, k, 0); b.run(40)
        dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
        b.place(0, x=b.fget(dm, 'x') - dist, z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
        h0 = len(b.hits); seq = []
        for f in range(160):
            keys = 'Rc' if f < 3 else ('Rc' if again and f > 6 and f % 2 == 0 else '')
            b.run(1, p1=keys)
            if b.states[b.fget(0, 'state')] == 'SPECIAL':
                a = of.get(b.fget(0, 'frame_ovr'))
                if a is not None and (not seq or seq[-1] != a): seq.append(a)
            elif seq and f > 10: break
        res[case] = {'anims': seq, 'hits': [(h[1], h[2], h[3]) for h in b.hits[h0:] if h[1] == dm]}
        print(case, res[case], flush=True)
    parts = lambda c: [a for a in res[c]['anims'] if a in (366, 369)]   # (343 / 363 / 366 share frames: the parts by
    ok = parts('whiff') == [] and parts('connect') == [] and parts('connect+C') == [366, 369]   # their own animations)
    res['ok'] = ok; print('chain', 'OK' if ok else 'FAIL')
    json.dump(res, open(os.path.join(OUT, 'chain_genjuro.json'), 'w'), indent=1)

if __name__ == '__main__':
    main()
