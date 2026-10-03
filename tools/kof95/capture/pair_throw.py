#!/usr/bin/env python3
"""Thrower X vs victim Y in MAME (P1 team = X, P2 team = Y; both load after the first KO), one ground throw.
Prints / returns the victim's (state, step, dx, dy) per frame from the grab on.
    python3 capture/pair_throw.py THROWER VICTIM [VICTIM ...]"""
import os, sys, subprocess, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)
import analyze as A, rom
from timeline import seqs
from mirror_check import ROUND, GRAB
from neogeo.sprite_decode import r32

def capture(x, y):
    d = os.path.join(HERE, 'pairs'); os.makedirs(d, exist_ok=True); out = os.path.join(d, f'{x}_{y}.txt')
    if not os.path.exists(out):
        s1, s2 = seqs(f'p2 20 45 L; p2 70 3 c; p1 {ROUND} 60 R; p1 {ROUND + 20} 3 Rc', ROUND + 260)
        poke = (f'2:108220=0,108221=1,108222=0,108223=1,10824C=0,10824D=1,' + ','.join(f'10A8{a}={x:02X}' for a in ('43', '44', '45')) + ',' +
                ','.join(f'10A8{a}={y:02X}' for a in ('53', '54', '55')) + f';{ROUND - 2}:108118=01,108119=90,108318=01,108319=CC')
        subprocess.run(['mame', 'kof95', '-rompath', '/home/bruno/Downloads', '-state', 'a', '-video', 'none', '-sound', 'none', '-nothrottle',
                        '-skip_gameinfo', '-noplugin', 'cart_bridge', '-autoboot_script', os.path.join(HERE, 'record.lua')], env=dict(os.environ, SEQ=s1, SEQ2=s2, POKE=poke, OUT=out),
                       cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    prom, _ = rom.load(); sd = {r32(prom, 0x080080 + i * 4): i for i in range(30)}
    r1, r2 = A.load(out, 1), A.load(out, 2)
    who = lambda w: sd.get((w[0x3C // 2] << 16) | w[0x3E // 2])
    assert (who(r1[ROUND][3]), who(r2[ROUND][3])) == (x, y), (who(r1[ROUND][3]), who(r2[ROUND][3]))
    g = next((i for i in range(ROUND, len(r2)) if A.state_of(r2[i][3]) in GRAB), None)
    if g is None: return None
    seq = []
    for i in range(g, len(r2)):
        w1, w2 = r1[i][3], r2[i][3]; f = 1 if A.facing_of(w1) else -1
        s = A.state_of(w2)
        if s in (0, 45, 47) and i > g + 10: break
        seq.append((s, w2[0x74 // 2] // 6, round((A.x_of(w2) - A.x_of(w1)) * f, 1), round(A.y_of(w2) - A.y_of(w1), 1)))
    return seq

def runs(seq):
    out = []
    for s in seq:
        k = s[:2]
        if out and out[-1][0] == k: out[-1][1] += 1
        else: out.append([k, 1, s[2], s[3]])
    return out

if __name__ == '__main__':
    x = int(sys.argv[1])
    for y in map(int, sys.argv[2:]):
        try: seq = capture(x, y)
        except AssertionError as e: print(rom.CAST[y], 'swap failed', e); continue
        print(f'{rom.CAST[x]} throws {rom.CAST[y]:10}', ' '.join(f'{k[0]}.{k[1]}x{n}@{dx:+.0f},{dy:.0f}' for k, n, dx, dy in runs(seq or [])[:10]), flush=True)
