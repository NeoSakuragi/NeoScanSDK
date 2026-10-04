#!/usr/bin/env python3
"""KOF96 throws in MAME (state 'vs', P2 = Yuri, id 8): P1's team record ($10A846-48) is set to the character and P1's
health (+$138/+$150) to 1; after P2's hit the next round loads that character. Then forward+C and forward+D, each from
120 px... close range. While a throw holds the victim, the victim object carries the throw list (+$C2 = table base +
victim id * list size, +$C6 = list size), so each throw's table base comes straight from the capture.
    python3 capture/throws96.py ID [ID ...]   -> capture/throws/<id>.txt + summary"""
import json, os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
import analyze as A
from timeline import seqs
REC = os.path.join(HERE, '..', '..', 'kof95', 'capture', 'record.lua')
ROMPATH = '/home/bruno/roms/neogeo;/home/bruno/Downloads'
GAME = os.environ.get('GAME', 'kof96')
ROUND, GAP = int(os.environ.get("ROUND", 1100)), 300
VICTIM = {'kof96': 8, 'kof98': 8, 'kof99': 3}[GAME]       # P2 in each game's 'vs' state (Yuri; KOF99 Shingo)          # GAME=kof98: one run per fighter from its state c<id> (prep98.lua)
REC96 = os.path.join(HERE, 'record96.lua')
# both fighters midscreen (a round starts at x $149 / $249: centre $1C9), 56 px apart: P1 $1B0, P2 $1E8 (Bruno
# 2026-10-04: at P1 $180 the back throws carried the victim toward the left wall)
POS = '108118=01,108119=B0,108318=01,108319=E8'
TRIES = [('ground_c', 'p1 0 40 R; p1 26 3 Rc'), ('ground_d', 'p1 0 40 R; p1 26 3 Rd'),
         ('air_c', 'p1 0 6 UR; p2 2 6 U; p1 12 4 URc; p1 16 20 R')]

def run(cid, t):
    """one MAME run per try (written when the cart_bridge plugin still cut runs at 30 s; harmless now)"""
    out = os.path.join(HERE, 'throws', f'{cid}_{TRIES[t][0]}.txt'); os.makedirs(os.path.dirname(out), exist_ok=True)
    spec = ['p2 20 60 L', 'p2 85 3 c']; pokes = [f'2:108238=0,108239=1,108250=0,108251=1,10A846={cid:02X},10A847={cid:02X},10A848={cid:02X}',
                                                 f'{ROUND - 2}:{POS}']
    for e in TRIES[t][1].split(';'):
        w, a, n, i = e.split(); spec.append(f'{w} {int(a) + ROUND} {n} {i}')
    s1, s2 = seqs('; '.join(spec), ROUND + GAP)
    subprocess.run(['mame', 'kof96', '-rompath', ROMPATH, '-state', 'vs', '-video', 'none', '-sound', 'none', '-nothrottle',
                    '-skip_gameinfo', '-noplugin', 'cart_bridge', '-autoboot_script', REC], env=dict(os.environ, SEQ=s1, SEQ2=s2, POKE=';'.join(pokes), OUT=out),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    return out

THROWDIR = {'kof96': 'throws', 'kof98': 'throws98'}

def throwdir(): return os.path.join(HERE, THROWDIR.get(GAME, 'throws_' + GAME))

def run98(cid):
    """KOF98/KOF99: all tries in one run, each from the fighter's state c<cid> (reloaded 4 frames before the try,
    close positions poked 2 frames before); the tries start at 40 + GAP*t"""
    sys.path.insert(0, HERE); import specials96, emu
    specials96.prep(GAME, cid)
    out = os.path.join(throwdir(), f'{cid}.txt'); os.makedirs(os.path.dirname(out), exist_ok=True)
    spec, pokes, reload = [], [], []
    for t, (_, ev) in enumerate(TRIES):
        s = 40 + GAP * t; reload.append(s - 4); pokes.append(f'{s - 2}:{POS}')
        for e in ev.split(';'):
            w, a, n, i = e.split(); spec.append(f'{w} {int(a) + s} {n} {i}')
    s1, s2 = seqs('; '.join(spec), 40 + GAP * len(TRIES) + 20)
    emu.run(GAME, out, s1, s2, pokes, reload=f'c{cid}', reload_frames=reload, timeout=900)
    return out

def analyse(cid, t, path, start=None):
    global ROUND
    if start is not None: ROUND = start
    r1, r2 = A.load(path, 1), A.load(path, 2)
    assert r1[ROUND][3][0x70 // 2] == cid, f'swap failed: P1 is {r1[ROUND][3][0x70 // 2]}'
    found, seen = [], set()
    w0 = r1[ROUND][3]; stale = (w0[0xC2 // 2] << 16) | w0[0xC4 // 2]      # the thrower's +$C2 left over from earlier moves
    for i in range(ROUND, min(len(r1), len(r2), ROUND + GAP)):
        w1, w2 = r1[i][3], r2[i][3]
        c2 = (w2[0xC2 // 2] << 16) | w2[0xC4 // 2]; size = w2[0xC6 // 2]
        c1 = (w1[0xC2 // 2] << 16) | w1[0xC4 // 2]
        for side, cp, sz in (('victim', c2, size), ('thrower', c1, w1[0xC6 // 2])):     # thrower side: $1B008 mode
            if side == 'thrower' and cp == stale: continue
            if 0x200000 <= cp < 0x300000 and sz and A.state_of(w2) >= 400 and (cp, sz) not in seen:
                seen.add((cp, sz))
                found.append({'try': TRIES[t][0], 'side': side, 'thrower_state': A.state_of(w1), 'base': hex(cp - VICTIM * sz),
                              'size': sz, 'air': A.y_of(w1) > 0, 'frame': i, 'capture': os.path.basename(path)})
    return found

if __name__ == '__main__':
    res = {}
    for cid in map(int, sys.argv[1:]):
        res[cid] = []
        if GAME != 'kof96':
            path = run98(cid)
            for t in range(len(TRIES)):
                try: res[cid] += [dict(x, round=40 + GAP * t) for x in analyse(cid, t, path, start=40 + GAP * t)]
                except AssertionError as e: res[cid].append(str(e))
        else:
            for t in range(len(TRIES)):
                path = run(cid, t)
                try: res[cid] += [dict(x, round=ROUND) for x in analyse(cid, t, path)]
                except AssertionError as e: res[cid].append(str(e))
        print(cid, res[cid], flush=True)
    p = os.path.join(throwdir(), 'tables.json')                 # merged: the fighters not re-run keep theirs
    json.dump(dict(json.load(open(p)) if os.path.exists(p) else {}, **{str(k): v for k, v in res.items()}), open(p, 'w'), indent=1)
