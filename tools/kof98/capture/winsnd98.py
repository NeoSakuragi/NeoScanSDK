#!/usr/bin/env python3
"""The sounds of the KOF96 / 98 / 99 win poses, frame by frame, in our emulator (note 20261016-180707-e03d, Robert's
coin pose: "I'm not sure there is the sound of the coin and Robert talking on this win pose. Decode the sound from the
original game"): wins98.py's round end (P2's life 1, P1's C, one button held through the KO picks the pose) with WLOG
on the sound mapper's scratch word (tools/brawler/voices.py SCRATCH: index, object, driver word of every sound sent).
Kept: the sounds P1 or an object P1 owns (the capture's own-object column: Robert's coin, object 361) sends while P1
plays a pose state (not 0: the round's next things, the announcer's), with P1's state and raw step (+$74 / 6) then.
voices.py list reads it: a win pose's effects (prefix $1A: the coin's flick, catch and ring) listed as the fighter's
'fx' voices on that pose's step, whatever the rest of the cast sends (the static scan's common rule does not apply).

    GAME=kof98 python3 winsnd98.py ID [ID ...]   -> wins[_<game>]/<id>_snd.txt(.wlog) + wins[_<game>]/winsnd.json
       {id: {button: [[frame from the pose's start, driver word, index, object, P1 state, P1 raw step], ...]}}"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof96', 'capture')); sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'brawler'))
import analyze as A, emu, wins98
import voices as V

GAME = wins98.GAME
WDIR = os.path.join(HERE, 'wins' if GAME == 'kof98' else f'wins_{GAME}')

def capture(cid):
    orig = emu.run
    def run(game, out, *a, **k):                         # wins98.run with WLOG on the mapper's scratch word
        k['extra'] = dict(k.get('extra') or {}, WLOG=f'{V.SCRATCH[game]:X}')
        return orig(game, out[:-4] + '_snd.txt', *a, **k)
    emu.run = run
    try: wins98.run(cid)
    finally: emu.run = orig
    return os.path.join(WDIR, f'{cid}_snd.txt')

def analyse(path):
    rows, r1, r2 = open(path).read().split('\n'), A.load(path, 1), A.load(path, 2)
    owned = lambda f: {x.split(':')[0] for x in rows[f - 1].split()[5].split(';')} if len(rows[f - 1].split()) > 5 else set()
    W = V.wlog(path + '.wlog')
    life = lambda i: r2[i][3][0x138 // 2] - (0x10000 if r2[i][3][0x138 // 2] & 0x8000 else 0)
    res = {}
    for t, b in enumerate('ABCD'):
        s = wins98.START + wins98.GAP * t
        ko = next((i for i in range(s, min(len(r2), s + wins98.GAP)) if life(i) <= 0), None)
        if ko is None: continue
        end = min(len(r1), s + wins98.GAP - 4)       # the pose: P1's states after his first 0 past the KO, to the next 0
        i0 = next((i for i in range(ko, end) if A.state_of(r1[i][3]) == 0), end)
        f0 = next((i for i in range(i0, end) if A.state_of(r1[i][3]) != 0), None)
        if f0 is None: continue
        f1 = next((i for i in range(f0, end) if A.state_of(r1[i][3]) == 0), end) - 1
        out = []
        for f, w, ix, a4 in W:                           # (a frame's row k = frame k + 1: r1[f - 1] is frame f)
            if not f0 <= f - 1 <= f1 or w >> 8 == 0: continue
            if a4 != V.P1 and f'{a4:06X}' not in owned(f): continue
            p = r1[f - 1][3]
            out.append([f - 1 - f0, f'{w:04X}', f'{ix:03X}', f'{a4:06X}', A.state_of(p), p[0x74 // 2] // 6])
        res[b] = out
    return res

if __name__ == '__main__':
    path = os.path.join(WDIR, 'winsnd.json')
    allres = json.load(open(path)) if os.path.exists(path) else {}
    for cid in map(int, sys.argv[1:]):
        allres[str(cid)] = analyse(capture(cid))
        print(cid, json.dumps(allres[str(cid)]), flush=True)
        json.dump(allres, open(path, 'w'), indent=1)
