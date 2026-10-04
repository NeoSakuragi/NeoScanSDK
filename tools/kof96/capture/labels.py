#!/usr/bin/env python3
"""Label KOF96 game states by playing actions in our emulator (emu.py, state 'vs': Kyo P1 vs Yuri P2) and recording P1's (or P2's)
state sequence per action. The state -> slot map is shared by every character, so a label is valid for the cast.
    python3 capture/labels.py   -> prints per action: states (frames) -> slots"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
import analyze as A, rom96, emu
from timeline import seqs
GAME = os.environ.get('GAME', 'kof96')          # GAME=kof98: same actions on KOF98 (state 'vs', Kyo vs Yuri)
GAP = 110
# (name, who acts, events relative to the segment start); P1 starts at the left facing right
ACTIONS = [
    ('crouch', 'p1', 'p1 0 40 D'), ('jump back', 'p1', 'p1 0 6 UL'), ('run', 'p1', 'p1 0 3 R; p1 6 30 R'),
    ('backstep', 'p1', 'p1 0 3 L; p1 6 4 L'), ('roll fwd AB', 'p1', 'p1 0 3 Rab'), ('roll back AB', 'p1', 'p1 0 3 Lab'),
    ('stand A far', 'p1', 'p1 0 3 a'), ('stand B far', 'p1', 'p1 0 3 b'), ('stand C far', 'p1', 'p1 0 3 c'), ('stand D far', 'p1', 'p1 0 3 d'),
    ('crouch A', 'p1', 'p1 0 20 D; p1 6 3 Da'), ('crouch B', 'p1', 'p1 0 20 D; p1 6 3 Db'), ('crouch C', 'p1', 'p1 0 20 D; p1 6 3 Dc'), ('crouch D', 'p1', 'p1 0 20 D; p1 6 3 Dd'),
    ('jump A', 'p1', 'p1 0 6 U; p1 14 3 a'), ('jump B', 'p1', 'p1 0 6 U; p1 14 3 b'), ('jump C', 'p1', 'p1 0 6 U; p1 14 3 c'), ('jump D', 'p1', 'p1 0 6 U; p1 14 3 d'),
    ('jump diag A', 'p1', 'p1 0 6 UR; p1 14 3 a'), ('jump diag C', 'p1', 'p1 0 6 UR; p1 14 3 c'),
    ('C+D', 'p1', 'p1 0 3 cd'),
]
CLOSE = [('close A', 'p1 0 3 a'), ('close B', 'p1 0 3 b'), ('close C', 'p1 0 3 c'), ('close D', 'p1 0 3 d')]
HITS = [('hit light (P2 A)', 'p2 0 3 a'), ('hit heavy (P2 C)', 'p2 0 3 c'), ('crouch hit light', 'p1 0 40 D; p2 6 3 a'),
        ('crouch hit heavy', 'p1 0 40 D; p2 6 3 c'), ('sweep', 'p2 0 20 D; p2 6 3 Dd'), ('blowback (P2 C+D)', 'p2 0 3 cd'),
        ('guard stand', 'p1 0 40 L; p2 4 3 a'), ('guard crouch', 'p1 0 40 DL; p2 4 3 Da'), ('air hit', 'p1 0 6 U; p2 6 3 c')]

def run(segments, out, start_x):
    spec, pokes = [], []
    t0 = 120
    for k, (name, ev) in enumerate(segments):
        s = t0 + k * GAP
        pokes.append(f'{s - 2}:108118={start_x[0] >> 8:02X},108119={start_x[0] & 255:02X},108318={start_x[1] >> 8:02X},108319={start_x[1] & 255:02X}')
        for e in ev.split(';'):
            w, a, n, i = e.split(); spec.append(f'{w} {int(a) + s} {n} {i}')
    s1, s2 = seqs('; '.join(spec), t0 + GAP * len(segments) + 20)
    import emu
    emu.run(GAME, out, s1, s2, pokes, timeout=900)
    return t0

def report(segments, out, t0, who):
    prom, _ = rom96.load(rom96.GAMES[GAME]['neo']); m = rom96.Mem(prom, GAME)
    cid = 0 if who == 1 else emu.GAMES[GAME]['victim']      # P1 (Kyo; KOF99 K') / P2 (Yuri; KOF99 Shingo)
    mp = [rom96.state_slot(m, cid, st) for st in range(512)]
    r = A.load(out, who)
    for k, (name, _) in enumerate(segments):
        s = t0 + k * GAP; seq = []
        for n, _, _, w in r[s:s + GAP - 5]:
            st = A.state_of(w)
            if not seq or seq[-1][0] != st: seq.append([st, 1])
            else: seq[-1][1] += 1
        print(f'{name:20} P{who}:', ' '.join(f'{st}({n})->{mp[st] if st < len(mp) else "?"}' for st, n in seq if st))

if __name__ == '__main__':
    segs = [(n, e) for n, _, e in ACTIONS]
    t0 = run(segs, f'/tmp/claude-1000/{GAME}_labels.txt', (0x150, 0x1E0)); report(segs, f'/tmp/claude-1000/{GAME}_labels.txt', t0, 1)
    t0 = run(CLOSE, f'/tmp/claude-1000/{GAME}_close.txt', (0x180, 0x1A8)); report(CLOSE, f'/tmp/claude-1000/{GAME}_close.txt', t0, 1)
    t0 = run(HITS, f'/tmp/claude-1000/{GAME}_hits.txt', (0x180, 0x1B0)); report(HITS, f'/tmp/claude-1000/{GAME}_hits.txt', t0, 1)
