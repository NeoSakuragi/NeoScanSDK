#!/usr/bin/env python3
"""Whole specials as the brawler plays them ON HIT (the gold question pages, 2026-10-08: "see each move end to end"):
per fighter, every special of its pool on a C slot (C + a direction) and its fury (D), pressed in the Lab's dummy fight
(harness, the Chain Lab request) with the dummy in reach; its follow-up keys tapped every few frames, so a rush plays
all its parts and a move whose rest comes on contact (a catch, a fury's sequence) plays it. Per game frame from the
special's first frame to its end (hit-stop frames kept: the move's real timing): the fighter's drawing, its place
(x forward, y up, px from the start) and the frames a hit landed. The victim is not drawn.

    python3 tools/brawler/full_clips.py [--merge] GAME_DIR FIGHTER ...   -> GAME_DIR/build/full_clips.json (merged per
                                                                           fighter; --merge: per move, for a 2nd build
                                                                           with other moves on the slots)
The fury's MAX (pool 'MAX <fury>') is played too: D with the gauge full at low life.

review_build.py reads it for the full-<input slug> clips; a special it lacks (an air special, no slot) plays its
program alone (pieces.py special(): its whiff)."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SLOT_KEYS = {'D': 'c', 'fD': 'Rc', 'dD': 'Dc', 'uD': 'Uc', 'dfD': 'DRc', 'ufD': 'URc'}   # P1 faces right: R = forward
TAP = 6                                                       # a follow-up press every TAP frames while the move plays
DIST = 56                                                     # the dummy's distance (px ahead)


def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)


def play(b, k, keys, fury=False, low=False):
    lab_req(b, 1, k, 0); b.run(40)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    x0 = 100
    b.place(dm, x=x0 + DIST, z=30); b.place(0, x=x0, z=30); b.fset(0, 'facing', 1); b.fset(dm, 'hp', 120); b.run(3)
    if fury: b.fset(0, 'fgauge', 0xFFFF)
    if low: b.fset(0, 'hp', 4)                                # low life + the gauge full: D = the MAX
    h0 = len(b.hits); out, start, kx0, ky0 = [], None, 0, 0
    for f in range(700):
        tap = f < 3 or (start is not None and (f - start) % TAP < 1)
        b.run(1, p1=keys if tap else '')
        st = b.states[b.fget(0, 'state')]
        if start is None:
            if st == 'SPECIAL': start = f; kx0 = b.fget(0, 'x'); ky0 = b.fget(0, 'y')
            elif f > 60: return None
            else: continue
        if st != 'SPECIAL': break
        hit = any(h[0] == b.frame and h[1] == dm for h in b.hits[h0:])
        out.append({'frame': b.fget(0, 'frame_ovr'), 'x': round(b.fget(0, 'x') - kx0), 'y': round(b.fget(0, 'y') - ky0),
                    'live': hit, 'atk': (0, 0, 0, 0)})
    return out


def main(game, names):
    from harness import Brawler
    G = json.load(open(os.path.join(game, 'game.json')))
    lab = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
    hdr = open(os.path.join(game, 'build', 'bm_chars.h')).read()
    order = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    path = os.path.join(game, 'build', 'full_clips.json')
    res = json.load(open(path)) if os.path.exists(path) else {}
    b = Brawler(game=game)
    for name in names:
        ros = next(r for r in G['roster'] if r['name'] == name)
        pool = next(f for f in lab['fighters'] if f['name'] == name)['pool']
        k = order.index('BC_' + name.upper()); b.pick(k, unlock=True)            # bosses too (Krauser)
        got = {}
        for slot, inp in (ros.get('specials') or {}).items():
            if inp and inp not in got and slot in SLOT_KEYS and any(p['input'] == inp for p in pool):
                fr = play(b, k, SLOT_KEYS[slot])
                if fr: got[inp] = fr
        if ros.get('fury') and any(p['input'] == ros['fury'] for p in pool):
            fr = play(b, k, 'd', fury=True)
            if fr: got[ros['fury']] = fr
        if ros.get('fury') and any(p['input'] == 'MAX ' + ros['fury'] for p in pool):
            fr = play(b, k, 'd', fury=True, low=True)
            if fr: got['MAX ' + ros['fury']] = fr
        res[name] = dict(res.get(name, {}), **got) if MERGE else got
        print(name, {i: len(v) for i, v in got.items()})
    json.dump(res, open(path, 'w'), separators=(',', ':'))


MERGE = False
if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['--merge']: MERGE = True; a = a[1:]          # keep the fighter's other moves (a 2nd build with other slots)
    main(a[0], a[1:])
