#!/usr/bin/env python3
"""Per-try comparison of two captures of the same tries (e.g. MAME vs our emulator): each try aligned at P1's first
frame out of its starting state; frames where the game lost a frame (P1 +$1D2 not advancing: slowdown) skipped; per
frame P1 state, steps +$80, frame record, x from the move's start, height, facing, P2 state, P2 hit (life dropped), P2 x
from P1, and P1-owned objects spawned in the try (id:state:steps:record:x:height:facing; NOOBJ=1 leaves them out).
Prints the differing tries, then totals: identical / differing, start lags, damage and lost-frame differences.
usage: cmp_captures.py A.txt B.txt tries.json [gap] [all]"""
import sys, json, os
def rows(p):
    d = {}
    for line in open(p):
        q = line.split(); d[int(q[0])] = q
    return d
def W(o, off): return int(o[off * 2:off * 2 + 4], 16)
def S(v): return v - 65536 if v >= 32768 else v
def tup(r, x0, pre=()):
    """objects: the ones not there before the move (pre: base:id), without the shadow (P1's frame a frame late)"""
    o1, o2 = r[3], r[4]
    objs = []
    if len(r) > 5 and r[5] != '-':
        for ob in r[5].split(';'):
            b, i, st, sp, rec, x, h, fc = ob.split(':')
            if f'{b}:{i}:{st}:{sp}:{rec}' in pre or (i, st, sp) == ('0', '0', '0'): continue     # the shadow: P1's frame a frame late
            objs.append((i, st, sp, rec, int(x) - x0, h, fc))
    return (W(o1, 0x72), W(o1, 0x80), W(o1, 0x28) & 0xFF, W(o1, 0x2A), S(W(o1, 0x18)) - x0, S(W(o1, 0x20)), W(o1, 0x30) & 1,
            W(o2, 0x72), W(o2, 0x138), S(W(o2, 0x18)) - S(W(o1, 0x18)), tuple(sorted(objs)))
NAMES = ['p1state', 'p1steps', 'rec_hi', 'rec', 'x', 'h', 'face', 'p2state', 'p2hit', 'p2dx', 'objs']
def seq(R, s, end):
    st0 = W(R[s][3], 0x72)
    f0 = next((f for f in range(s, end) if W(R[f][3], 0x72) != st0), None)
    if f0 is None: return None, []
    x0 = S(W(R[f0 - 1][3], 0x18))
    r = R[s - 3]; pre = {':'.join(ob.split(':')[:5]) for ob in r[5].split(';')} if len(r) > 5 and r[5] != '-' else set()
    out = []; stalls = 0
    for f in range(f0, end):                             # P2 life -> hit (life dropped this frame); damage apart
        if W(R[f][3], 0x1D2) == W(R[f - 1][3], 0x1D2): stalls += 1; continue   # a game frame lost (slowdown): P1's
        t = list(tup(R[f], x0, pre)); t[8] = W(R[f][4], 0x138) < W(R[f - 1][4], 0x138); out.append(tuple(t))  # +$1D2
    STALLS.append(stalls)
    return f0, out
def damage(R, s, end): return W(R[s][4], 0x138) - min(W(R[f][4], 0x138) for f in range(s, end))
a, b, T = rows(sys.argv[1]), rows(sys.argv[2]), json.load(open(sys.argv[3]))
ok = bad = 0; lags = {}; dmg = []; STALLS = []; stalld = []
for k, tr in enumerate(T):
    s = tr['start']; gap = tr.get('gap', int(sys.argv[4]) if len(sys.argv) > 4 else 220)
    end = s + gap - 8
    fa, sa = seq(a, s, end); fb, sb = seq(b, s, end)
    if fa is None or fb is None:
        if len(sys.argv) > 5 or bad <= 12: print(k, tr.get('notation', tr.get('kind', tr.get('input'))), 'no move', fa, fb); bad += 1; continue
    lags[fa - fb] = lags.get(fa - fb, 0) + 1
    if STALLS[-2] != STALLS[-1]: stalld.append((k, STALLS[-2], STALLS[-1]))
    da, db = damage(a, s, end), damage(b, s, end)
    if da != db: dmg.append((k, da, db))
    n = min(len(sa), len(sb))
    NOOBJ = os.environ.get('NOOBJ')
    diff = [i for i in range(n) if (sa[i][:-1] != sb[i][:-1] if NOOBJ else sa[i] != sb[i])]
    if not diff: ok += 1; continue
    bad += 1; i = diff[0]
    fields = [NAMES[j] for j in range(len(NAMES)) if sa[i][j] != sb[i][j]]
    if len(sys.argv) > 5 or bad <= 12: print(k, tr.get('notation', tr.get('kind', tr.get('input'))), tr.get('button'), 'air' if tr.get('air') else '', f'lag {fa - fb}',
          f'first diff +{i} ({len(diff)}/{n} frames) in {fields}: {[sa[i][NAMES.index(x)] for x in fields]} vs {[sb[i][NAMES.index(x)] for x in fields]}')
print(f'tries identical {ok}, differing {bad}; start lags (A - B): {lags}; total damage differs in {len(dmg)}: {dmg}; game frames lost (slowdown) differ in {stalld} (try, A, B)')
