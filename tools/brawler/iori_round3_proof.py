#!/usr/bin/env python3
"""Iori round 3 (game 0.10.67), in our emulator: the brawler (harness.py, BRAWLER_CORE) against KOF98
(tools/kof96/capture/romspecials98.trace, neogeo_sdl --capture):
  1. rekka (note 20261012-032513-5d29: "the second rekka hit doesn't really move forward on the X axis"): a pressed
     SEQUENCE's parts, each part's x travel per frame from its start, brawler vs KOF98, for Iori's dd + A (214C>142 /
     >146 / >149, 214C Aoi Hana) and Kyo's ff + A (236A>156 / >158 / >162, the same SEQUENCE path). The parts are pressed
     at the same frame of each part on both sides (KOF98: the move's input again; the brawler: A); a part's travel is
     compared over the frames it played on both sides. Root cause fixed: a part alone lost the motion factors its handler
     set before it (handlers98.part_factors: Iori 214C's friction $EC00, set once by the first part; the second part's
     `fricmove` read 0, vx *= 0)
  2. crossup (note 20261011-210422-5d29's second reopen: "the cross-up moves do not launch the enemy, keep the enemy on
     the ground"): back + A in a forward jump past Ryo = KOF98's j.4B Yuri Ori (state 183) hits him behind Iori; he
     stays on the ground in hit-stun (no KNOCKDOWN, height 0), as KOF98's P2 (state 262, the standing reel, height 0)
    python3 iori_round3_proof.py [OUT]     (default /data/tmp/iori3) -> OUT/proof.json + sheets, exit 1 on a FAIL"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
sys.path.insert(1, os.path.join(HERE, '..', 'kof96', 'capture')); sys.path.insert(2, os.path.join(HERE, '..', 'kof96'))
import harness
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/iori3'
GAME = harness.GAME
gj = json.load(open(os.path.join(GAME, 'game.json'))); NAMES = [r['name'] for r in gj['roster']]
ROM = os.path.join(GAME, 'brawler.neo')
SEQ = {'iori': ('214C', 27, ['D', '', 'D', 'Da'], ['214C>142', '214C>146', '214C>149']),
       'kyo': ('236A', 0, ['R', '', 'R', 'Ra'], ['236A>156', '236A>158', '236A>162'])}
PRESS = 20                # the next press this many frames into a part (single frame; both sides)
TOL = 1.0                 # px

def pool(name):
    return [p['input'] for p in next(x for x in json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))['fighters']
                                     if x['name'] == name)['pool']]

_LAB = []
def lab():
    from labdrive import Lab
    if not _LAB: _LAB.append(Lab(rom=ROM, game=GAME))     # (one core a process)
    return _LAB[0]

def travel(series, k, walk=()):
    """the last part's own travel: x at its last row - x on the row before its first (series [(part index, x)]); walk:
    the rows (indices) of a walk before it, whose step KOF still applies on the special's first frame (Kyo's 236A: the
    6 of the motion walks him, state 1, 3.08 px a frame; his part 1's first row = that step + its own first dx)"""
    i0 = next(i for i, (p, x) in enumerate(series) if p == k)
    last = max(i for i, (p, x) in enumerate(series) if p == k)
    base = series[i0 - 1][1] + (series[i0 - 1][1] - series[i0 - 2][1] if i0 - 1 in walk else 0)
    return round(series[last][1] - base, 2), last - i0 + 1

def brawler_last(name, presses, shots):
    """the sequence with `presses` more presses (0: part 1 alone to its end; 1: part 2 to its end; 2: part 3)"""
    L = lab(); b = L.b; ST = b.states; P = pool(name)
    L.start(NAMES.index(name), NAMES.index('ryo')); b.run(30)
    x0 = b.r(b.syms['cam_x'], 2) + 30
    b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
    b.place(2, x=x0 + 400, z=90); b.run(2)                       # the dummy out of the way: the whiff's travel
    keys = SEQ[name][2]; series, names, t_part, cur, ended = [], [], 0, None, False
    os.makedirs(shots, exist_ok=True)
    for f in range(240):
        k = keys[f] if f < len(keys) else ''
        if cur is not None and len(names) <= presses and t_part == PRESS: k = 'a'
        b.run(1, p1=k)
        s = ST[b.fget(0, 'state')]
        w = P[b.fget(0, 'spec_ix')] if s == 'SPECIAL' else None
        if w is not None and w != cur: names.append(w); t_part = 0
        if w is not None: t_part += 1
        if cur is not None and w is None: ended = True
        cur = w
        series.append((len(names) - 1 if w is not None else -1, b.fget(0, 'x')))
        if presses == 2 and f % 3 == 0: b.screenshot(f'{shots}/b_{f:03d}.png')
        if ended: break
    return names, series

def kof98_last(name, presses):
    import romspecials98 as R, rom96
    inp, cid = SEQ[name][0], SEQ[name][1]
    m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98')
    tr = R.try_for(m, cid, inp); ev = tr['events']; o0 = ev[-1][0]
    rel = [(o - o0, n, k) for o, n, k in ev]
    fol = [(PRESS * (j + 1), rel) for j in range(presses)]
    fs = R.follow_spec(cid, inp, 'whiff', False, 'kof98', fol) if fol else ''
    run0 = R.C.emu.run                                          # P2 kept 150 px ahead of P1 from part 3's start: the
    def run(game, out, s1, s2, pokes, **kw):                     # whole rekka travels 255 px, the screen keeps KOF's
        p2 = [f'{R.START + f}:108318=02,108319=80' for f in range(PRESS * 2, 200)]   # two fighters within it: P1 lands on
        return run0(game, out, s1, s2, list(pokes) + p2, **kw)   # P2 (x 599) and is pushed back 8.5 px otherwise
    R.C.emu.run = run
    try: rows, _, _ = R.trace(cid, inp, 'whiff', frames=200, p2_seq=fs)
    finally: R.C.emu.run = run0
    part_of = {s: k for k, ss in enumerate(PART_STATES[name]) for s in ss}
    return ([(part_of.get(r['state'], -1), r['x']) for r in rows], sorted({part_of[r['state']] for r in rows if r['state'] in part_of}),
            {i for i, r in enumerate(rows) if r['state'] == 1})   # (KOF98 state 1: the walk forward)

PART_STATES = {'iori': [(142, 144), (146, 148), (149, 150, 152)], 'kyo': [(156, 157), (158, 159), (162, 163)]}

def rekka():
    out = {}
    for name in SEQ:
        rows = []
        for k in range(3):
            names, bs = brawler_last(name, k, os.path.join(OUT, f'brawler_{name}'))
            ks, kparts, walk = kof98_last(name, k)
            row = {'part': SEQ[name][3][k], 'brawler_parts': names, 'kof98_parts': kparts}
            if len(names) == k + 1 and kparts == list(range(k + 1)):
                (tb, nb), (tk, nk) = travel(bs, k), travel(ks, k, walk)
                row.update(brawler_px=tb, kof98_px=tk, frames=[nb, nk])
                row['ok'] = names == SEQ[name][3][:k + 1] and abs(tb - tk) <= TOL
            rows.append(row)
        out[name] = rows
    return dict(out, **{'pass': all(r.get('ok') for v in out.values() for r in v)})

def kof98_crossup():
    """KOF98 (c27 reload state: Iori, Ryo 48 px ahead): a forward jump, back (now R: the opponent behind) + B past him"""
    import emu, specials96 as C
    S = 40; d = os.path.join(OUT, 'kof98_yuriori'); os.makedirs(d, exist_ok=True)
    s1, s2 = C.seqs(f'p1 {S} 9 UR; p1 {S + 16} 30 R; p1 {S + 22} 3 Rb', S + 90)
    out = emu.run('kof98', f'{d}/run.txt', s1, s2, [f'{S - 2}:108118=01,108119=80,108318=01,108319=B0'], reload='c27',
                  reload_frames=[S - 4], snaps=[S + k for k in range(20, 70, 2)], snapdir=d)
    rows = []
    for line in open(out):
        p = line.split(); f = int(p[0])
        if f < S: continue
        o = bytes.fromhex(p[3]); q = bytes.fromhex(p[4])
        w = lambda b_, a: struct.unpack('>H', b_[a:a + 2])[0]; s = lambda b_, a: struct.unpack('>h', b_[a:a + 2])[0]
        rows.append({'f': f - S, 'p1': w(o, 0x72), 'p1x': w(o, 0x18), 'p2': w(q, 0x72), 'p2x': w(q, 0x18), 'p2h': s(q, 0x20), 'p2life': w(q, 0x138)})
    hit = next((r for r in rows if r['p2life'] != rows[0]['p2life']), None)
    after = [r for r in rows if hit and r['f'] >= hit['f']][:30]
    return {'p1_states': sorted({r['p1'] for r in rows}), 'hit_frame': hit and hit['f'], 'behind': bool(hit and hit['p2x'] < hit['p1x']),
            'p2_states_after': sorted({r['p2'] for r in after}), 'p2_max_height': max([r['p2h'] for r in after] or [0])}

def crossup():
    import re
    L = lab(); b = L.b; ST = b.states
    L.start(NAMES.index('iori'), NAMES.index('ryo')); b.run(30)
    x0 = b.r(b.syms['cam_x'], 2) + 120
    b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
    b.place(2, x=x0 + 60, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', 120); b.run(2)
    ba = re.search(r'enum \{ (BA_[^}]*), BA_COUNT \}', open(os.path.join(GAME, 'build', 'bm_chars.h')).read()).group(1).split(', ')
    d = os.path.join(OUT, 'brawler_crossup'); os.makedirs(d, exist_ok=True)
    hp = b.fget(2, 'hp'); moves = set(); hit = None; states = set(); top = 0.0
    for k in range(110):
        b.run(1, p1='Rb' if k < 2 else ('La' if 28 <= k < 30 else ''))
        if ST[b.fget(0, 'state')] == 'AIR_ATTACK': moves.add(ba[b.fget(0, 'anim')])
        if hit is None and b.fget(2, 'hp') < hp:
            hit = {'frame': k, 'behind': (b.fget(2, 'x') - b.fget(0, 'x')) * (1 if b.fget(0, 'facing') == 1 else -1) < 0}
        if hit is not None and k < hit['frame'] + 40:
            states.add(ST[b.fget(2, 'state')]); top = max(top, b.fget(2, 'y'))
        if k % 2 == 0 and 20 <= k < 80: b.screenshot(f'{d}/b_{k:03d}.png')
    kof = kof98_crossup()
    return {'brawler': {'moves': sorted(moves), 'hit': hit, 'victim_states': sorted(states), 'victim_max_height': top},
            'kof98': kof,
            'pass': bool(hit and hit['behind']) and any(m.startswith('BA_ATK_AB_JUMP') for m in moves) and
                    'KNOCKDOWN' not in states and top == 0 and 'HITSTUN' in states and
                    183 in kof['p1_states'] and kof['behind'] and kof['p2_max_height'] == 0}

PARTS = {'rekka': rekka, 'crossup': crossup}
if __name__ == '__main__':
    import subprocess
    os.makedirs(OUT, exist_ok=True)
    if len(sys.argv) > 2:                                # one part in its own process (one core a process)
        json.dump(PARTS[sys.argv[2]](), open(os.path.join(OUT, f'_{sys.argv[2]}.json'), 'w')); sys.exit(0)
    R = {}
    for k in PARTS:
        subprocess.run([sys.executable, __file__, OUT, k], check=True)
        R[k] = json.load(open(os.path.join(OUT, f'_{k}.json')))
    json.dump(R, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    for k, v in R.items(): print(k, 'PASS' if v['pass'] else 'FAIL', json.dumps({x: y for x, y in v.items() if x != 'pass'})[:900])
    ok = all(v['pass'] for v in R.values()); print('ALL OK' if ok else 'FAIL'); sys.exit(0 if ok else 1)
