#!/usr/bin/env python3
"""Air C+D (the jumping blowback attack) measured in the game: from a fighter's prepared state c<id>
(specials96.prep), jump straight up / forward (stick held: a jump; tapped: a hop) and press C+D on the 8th frame
after the stick, 3 frames. Prints the states P1 goes through after the press (states 80-255 = moves).
    python3 capture/aircd.py --game kof96|kof98|kof99 ID ...   -> captures/kof96/aircd_<game>/<id>.txt"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
from timeline import seqs
import analyze as A, emu
import importlib.util
_sp = importlib.util.spec_from_file_location('cap_specials96', os.path.join(HERE, 'specials96.py'))
cap = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(cap)
OUT = '/data/neogeo_dict/captures/kof96'
GAP = 160
TRIES = [('jump up', 'U', 14), ('jump fwd', 'UR', 14), ('hop up', 'U', 3), ('hop fwd', 'UR', 3)]

def run(game, cid):
    d = os.path.join(OUT, 'aircd_' + game); os.makedirs(d, exist_ok=True)
    cap.prep(game, cid)
    spec, reload, T, s = [], [], [], 40
    for name, stick, hold in TRIES:
        reload.append(s - 4)
        spec.append(f'p1 {s} {hold} {stick}')
        spec.append(f'p1 {s + 8} 3 cd')
        T.append((name, s + 8)); s += GAP
    s1, s2 = seqs('; '.join(spec), s + 20)
    out = os.path.join(d, f'{cid}.txt')
    emu.run(game, out, s1, s2, [], reload=f'c{cid}', reload_frames=reload)
    r1 = A.load(out, 1)
    for name, p in T:
        st = [A.state_of(r1[i][3]) for i in range(p - 2, min(len(r1), p + 40))]
        seq = [v for k, v in enumerate(st) if k == 0 or v != st[k - 1]]
        print(f'{game} {cid} {name}: states {seq}')

if __name__ == '__main__':
    g = sys.argv[sys.argv.index('--game') + 1]
    for c in [a for a in sys.argv[1:] if a.isdigit()]: run(g, int(c))
