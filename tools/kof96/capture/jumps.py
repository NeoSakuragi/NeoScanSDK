#!/usr/bin/env python3
"""Jumps measured in the game: the regular jump (stick held up) and the hop (up tapped), each vertical / forward / back,
and the air normals in each of the six jump kinds. Per fighter, from its prepared state c<id> (specials96.prep; P1 x
$100 facing right, P2 x $260 standing; P1 moved to x $180), each try reloads the state; P1 faces right, so forward = R.
    python3 capture/jumps.py --game kof96|kof98|kof99 ID ...       -> jumps_<game>/<id>.txt + .json (raw tries)
    python3 capture/jumps.py --game kof98 --tap ID                 -> calibration: up held 1..8 frames (where a hop ends)
    python3 capture/jumps.py --game kof98 --table [ID ...]         -> jumps_<game>.json: per fighter and try, P1's rows
        [state, raw step, frame record, x forward from the press, height] from the press until it stands again, and
        the states it went through (tools/kof96/jumps_<game>.json, export96.JUMPS)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
from timeline import seqs
import analyze as A, emu
import importlib.util
_sp = importlib.util.spec_from_file_location('cap_specials96', os.path.join(HERE, 'specials96.py'))
cap = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(cap)    # the capture one, not ../specials96.py
OUT = '/data/neogeo_dict/captures/kof96'
GAP = 110
HOP_TAP = 3             # frames up is held for a hop (--tap: KOF96/98/99 hop when up is released within the take-off)
AIR_PRESS = 10          # an air normal: the button pressed this many frames after the stick (rising, past take-off)
KINDS = [('jump_up', 'U', 20), ('jump_fwd', 'UR', 20), ('jump_back', 'UL', 20),
         ('hop_up', 'U', HOP_TAP), ('hop_fwd', 'UR', HOP_TAP), ('hop_back', 'UL', HOP_TAP)]

def tries():
    out = [{'kind': k, 'stick': st, 'hold': n, 'button': None} for k, st, n in KINDS]
    for k, st, n in KINDS:
        for b in 'abcd': out.append({'kind': k, 'stick': st, 'hold': n, 'button': b})
    return out

def tap_tries():
    return [{'kind': f'tap{n}', 'stick': 'U', 'hold': n, 'button': None} for n in range(1, 9)] + \
           [{'kind': f'tapfwd{n}', 'stick': 'UR', 'hold': n, 'button': None} for n in range(1, 9)]

def odir(game): return os.path.join(OUT, 'jumps_' + game)

def run(game, cid, T, tag=''):
    os.makedirs(odir(game), exist_ok=True)
    cap.prep(game, cid)
    spec, reload, pokes = [], [], []
    s = 40
    for tr in T:
        reload.append(s - 4); tr['start'] = s
        pokes.append(f'{s - 2}:108118=01,108119=80')     # P1 x $180: room for a back jump (at $100 the screen edge
                                                          # held it: KOF98 back jumps went straight up)
        spec.append(f'p1 {s} {tr["hold"]} {tr["stick"]}')
        if tr['button']: spec.append(f'p1 {s + AIR_PRESS} 3 {tr["button"]}')
        s += GAP
    s1, s2 = seqs('; '.join(spec), s + 20)
    out = os.path.join(odir(game), f'{cid}{tag}.txt')
    emu.run(game, out, s1, s2, pokes, reload=f'c{cid}', reload_frames=reload)
    json.dump(T, open(os.path.join(odir(game), f'{cid}{tag}.json'), 'w'), indent=1)

def analyse(game, cid, tag=''):
    """per try: P1's rows from the press until it stands on the floor again in a ground state (idle, walk, crouch), and
    the states it went through"""
    path = os.path.join(odir(game), f'{cid}{tag}.txt'); T = json.load(open(os.path.join(odir(game), f'{cid}{tag}.json')))
    r1 = A.load(path, 1)
    res = []
    for tr in T:
        s = tr['start']; x0 = A.x_of(r1[s][3]); rows, states = [], []
        for i in range(s, min(len(r1), s + GAP - 4)):
            w = r1[i][3]; st = A.state_of(w)
            rows.append([st, w[0x74 // 2] // 6, A.frame_of(w), round(A.x_of(w) - x0, 3), round(A.y_of(w), 3)])
            if not states or states[-1] != st: states.append(st)
            if i > s + 4 and st in (0, 1, 2, 21, 22, 23) and len(states) > 2: rows.pop(); break
        res.append(dict(tr, states=states, rows=rows))
    return res

if __name__ == '__main__':
    args = sys.argv[1:]; game = 'kof98'
    if args[:1] == ['--game']: game = args[1]; args = args[2:]
    import export96
    cast = {'kof98': export96.CAST98, 'kof99': export96.CAST99}.get(game, export96.CAST)
    if args[:1] == ['--tap']:
        for cid in map(int, args[1:]):
            run(game, cid, tap_tries(), '_tap')
            for r in analyse(game, cid, '_tap'):
                print(r['kind'], r['states'], 'apex', max(row[4] for row in r['rows']), 'air', sum(1 for row in r['rows'] if row[4] > 0))
    elif args[:1] == ['--table']:
        ids = list(map(int, args[1:])) or [c for c in range(len(cast)) if os.path.exists(os.path.join(odir(game), f'{c}.txt'))]
        table = {cast[cid]: analyse(game, cid) for cid in ids}
        json.dump(table, open(os.path.join(OUT, f'jumps_{game}.json'), 'w'))
        for name, res in table.items():
            print(f'{name:10} ' + '  '.join(f'{r["kind"]}{r["button"] or ""}:{"/".join(map(str, r["states"]))}' for r in res))
    else:
        for cid in map(int, args):
            run(game, cid, tries()); print(cid, 'done', flush=True)
