#!/usr/bin/env python3
"""KOF98 win poses: from each fighter's state c<id> (prep98.lua), P2's life is set to 1, P1 hits with C at close range,
and one button (A, B, C or D) is held through the round's end; the game picks the winner's pose by that button.
Recorded with tools/kof96/capture/record96.lua; the states P1 enters after the KO are the win pose.
    python3 wins98.py ID [ID ...]   -> wins/<id>.txt + wins/wins.json {id: {button: [states]}}"""
import json, os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
K96 = os.path.join(HERE, '..', '..', 'kof96', 'capture')
sys.path.insert(0, K96); sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
import analyze as A, specials96
from timeline import seqs
GAP, START = 540, 40

GAME = os.environ.get('GAME', 'kof98')                  # GAME=kof99: same capture in our emulator

def run(cid):
    import emu
    specials96.prep(GAME, cid)
    out = os.path.join(HERE, 'wins' if GAME == 'kof98' else f'wins_{GAME}', f'{cid}.txt'); os.makedirs(os.path.dirname(out), exist_ok=True)
    g = emu.GAMES[GAME]; spec, pokes, reload = [], [], []
    for t, b in enumerate('abcd'):
        s = START + GAP * t; reload.append(s - 4)
        pokes.append(f'{s - 2}:108118=01,108119=80,108318=01,108319=B0,{emu.life_pokes(GAME, 0x108300, 1)}')
        spec += [f'p1 {s} 3 c', f'p1 {s + 12} {GAP - 30} {b}']
    s1, s2 = seqs('; '.join(spec), START + GAP * 4 + 20)
    emu.run(GAME, out, s1, s2, pokes, reload=f'c{cid}', reload_frames=reload)
    return out

def analyse(path):
    r1, r2 = A.load(path, 1), A.load(path, 2)
    res = {}
    for t, b in enumerate('ABCD'):
        s = START + GAP * t
        life = lambda i: r2[i][3][0x138 // 2] - (0x10000 if r2[i][3][0x138 // 2] & 0x8000 else 0)
        ko = next((i for i in range(s, min(len(r2), s + GAP)) if life(i) <= 0), None)     # life goes negative
        if ko is None: res[b] = None; continue
        seq = []
        for i in range(ko, min(len(r1), s + GAP - 4)):
            st = A.state_of(r1[i][3])
            if not seq or seq[-1][0] != st: seq.append([st, i - ko])
        res[b] = seq
    return res

if __name__ == '__main__':
    path = os.path.join(HERE, 'wins' if GAME == 'kof98' else f'wins_{GAME}', 'wins.json')
    allres = json.load(open(path)) if os.path.exists(path) else {}
    for cid in map(int, sys.argv[1:]):
        allres[str(cid)] = analyse(run(cid))
        print(cid, {b: [s for s, _ in v] if v else None for b, v in allres[str(cid)].items()}, flush=True)
        json.dump(allres, open(path, 'w'), indent=1)
