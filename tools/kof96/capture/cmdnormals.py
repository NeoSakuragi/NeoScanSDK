#!/usr/bin/env python3
"""Command normals (forward+A, forward+B, down-forward+C, down-forward+D: the KOF97+ pattern) measured in the game.
They are not in the recogniser's lists (commands96.py): the normal-attack code reads stick + button itself, so they are
found by playing them. Per fighter, from its prepared state c<id> (specials96.prep), each input is tried twice: close
(P1 x $180, P2 x $1B0, 48 px: the hit version, P2 idle so it does not guard) and far (P1 x $100, P2 x $260). Input: the
direction held 14 frames, the button pressed on its 4th frame for 3 frames (P1 faces right: forward = R).
Also tried (table only): 3A, 3B, 6C, 6D far (close 6C / 6D are throws).
    python3 capture/cmdnormals.py --game kof98|kof99 ID ...   -> cmdnormals_<game>/<id>.txt + .json (raw), and
    python3 capture/cmdnormals.py --game kof98 --table [ID ...] -> cmdnormals_<game>.json: per fighter and input, the
    states P1 went through (first = the move's state), P2 life drops (hits) and the frames they came at (close tries),
    P2's states after the first hit; and tools/kof96/cmdnormals_<game>.json (export96.CMD_NORMALS): fighter -> move ->
    [state, hits at point blank] + for a move through several states (the hops: Mai's, Billy's, Andy's forward+B) its
    frames in the far try, [state, raw step, frame record, x forward, height] each (P1 faces right: x grows forward)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
from timeline import seqs
import analyze as A, rom96, emu
import importlib.util
_sp = importlib.util.spec_from_file_location('cap_specials96', os.path.join(HERE, 'specials96.py'))
cap = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(cap)    # the capture one, not ../specials96.py
OUT = '/data/neogeo_dict/captures/kof96'
GAP = 160
TRIES = [('6A', 'R', 'a', True), ('6B', 'R', 'b', True), ('3C', 'DR', 'c', True), ('3D', 'DR', 'd', True),
         ('6A', 'R', 'a', False), ('6B', 'R', 'b', False), ('3C', 'DR', 'c', False), ('3D', 'DR', 'd', False),
         ('3A', 'DR', 'a', False), ('3B', 'DR', 'b', False), ('6C', 'R', 'c', False), ('6D', 'R', 'd', False),
         # reference: the plain normals at the same ranges (5A / 5B close, 2C / 2D)
         ('5A', '', 'a', True), ('5B', '', 'b', True), ('2C', 'D', 'c', True), ('2D', 'D', 'd', True)]

def odir(game): return os.path.join(OUT, 'cmdnormals_' + game)

def run(game, cid):
    os.makedirs(odir(game), exist_ok=True)
    cap.prep(game, cid)
    spec, pokes, reload, T = [], [], [], []
    s = 40
    for inp, stick, btn, close in TRIES:
        reload.append(s - 4)
        if close: pokes.append(f'{s - 2}:108118=01,108119=80,108318=01,108319=B0')
        if stick: spec.append(f'p1 {s} 14 {stick}')
        spec.append(f'p1 {s + 3} 3 {stick}{btn}')
        T.append({'input': inp, 'close': close, 'start': s}); s += GAP
    s1, s2 = seqs('; '.join(spec), s + 20)
    out = os.path.join(odir(game), f'{cid}.txt')
    emu.run(game, out, s1, s2, pokes, reload=f'c{cid}', reload_frames=reload)
    json.dump(T, open(os.path.join(odir(game), f'{cid}.json'), 'w'), indent=1)

def analyse(game, cid):
    """per try: the states P1 goes through from the press until it is back in idle / crouch (or 120 frames), P2's
    life drops (frames from the press)"""
    path = os.path.join(odir(game), f'{cid}.txt'); T = json.load(open(os.path.join(odir(game), f'{cid}.json')))
    r1, r2 = A.load(path, 1), A.load(path, 2)
    res = []
    for tr in T:
        s = tr['start'] + 3
        states, drops, p2, rows = [], [], [], []
        x0 = None
        for i in range(s, min(len(r1) - 1, s + 130)):
            w = r1[i][3]; st = A.state_of(w)
            if 80 <= st < 256:                            # P1's frames in the move: [state, raw step (+$74 / 6),
                if x0 is None: x0 = A.x_of(w)             # frame record, x forward from the move's start, height]
                rows.append([st, w[0x74 // 2] // 6, A.frame_of(w), round(A.x_of(w) - x0), round(A.y_of(w))])
            if i > s + 4 and st in (0, 1, 21, 22, 23) and states: break
            if st not in (0, 1, 2, 21, 22, 23) and (not states or states[-1] != st): states.append(st)
            if r2[i][3][0x138 // 2] < r2[i - 1][3][0x138 // 2]: drops.append(i - s)
            v = A.state_of(r2[i][3])
            if drops and v not in (0, 1, 2) and (not p2 or p2[-1] != v): p2.append(v)
        res.append(dict(tr, states=states, hits=len(drops), drop_frames=drops, p2_states=p2, rows=rows,
                        damage=r2[s - 1][3][0x138 // 2] - r2[min(len(r2) - 1, s + 129)][3][0x138 // 2]))
    return res

if __name__ == '__main__':
    args = sys.argv[1:]; game = 'kof98'
    if args[:1] == ['--game']: game = args[1]; args = args[2:]
    import export96
    cast = {'kof98': export96.CAST98, 'kof99': export96.CAST99}[game]
    if args[:1] == ['--table']:
        ids = list(map(int, args[1:])) or [c for c in range(len(cast)) if os.path.exists(os.path.join(odir(game), f'{c}.txt'))]
        table = {}
        for cid in ids:
            res = analyse(game, cid); table[cast[cid]] = res
            print(f'{cid:2} {cast[cid]:10} ' + '  '.join(f'{r["input"]}{"c" if r["close"] else "f"}:{"/".join(map(str, r["states"][:3]))}'
                                                         f'{"x" + str(r["hits"]) if r["close"] else ""}' for r in res))
        json.dump(table, open(os.path.join(OUT, f'cmdnormals_{game}.json'), 'w'), indent=1)
        # compact table for export96 (CMD_NORMALS): a command normal = the far try's first state is not a plain normal
        # (80-116) and the close try starts in the same state; hits = P2's life drops in the close try
        compact = {}
        for name, res in table.items():
            far = {r['input']: r for r in res if not r['close']}; close = {r['input']: r for r in res if r['close']}
            for inp, move in (('6A', 'cmd_fwd_a'), ('6B', 'cmd_fwd_b'), ('3C', 'cmd_df_c'), ('3D', 'cmd_df_d')):
                st = far[inp]['states'][:1]
                if st and not 80 <= st[0] <= 116 and st[0] < 256 and close[inp]['states'][:1] == st:
                    compact.setdefault(name, {})[move] = [st[0], close[inp]['hits']] + (
                        [far[inp]['rows']] if len(far[inp]['states']) > 1 else [])   # several states (a hop): its frames
        json.dump(compact, open(os.path.join(HERE, '..', f'cmdnormals_{game}.json'), 'w'), indent=0)
    else:
        for cid in map(int, args):
            run(game, cid); print(cid, 'done', flush=True)
