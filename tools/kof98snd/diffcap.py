#!/usr/bin/env python3
"""Compare two ymtap.lua captures from the same save state (quiet = music only, fight = music + effects): writes
only in one run, frame by frame, classed by YM2610 unit. MAME is deterministic from a state, so the difference is
what the effects added (and the music writes they displaced).
    python3 diffcap.py QUIET.txt FIGHT.txt"""
import sys
from collections import Counter, defaultdict

def frames(path):
    out, f = defaultdict(Counter), 0
    for l in open(path):
        p = l.split()
        if p[0] == 'f': f = int(p[1])
        elif p[0] in 'ab': out[f][(p[0], int(p[1], 16), int(p[2], 16))] += 1
    return out

def unit(port, reg):
    if port == 'a':
        if reg <= 0x0D: return 'SSG'
        if reg == 0x1C: return 'flag reset'           # ADPCM end-flag reset (bit per channel, then 0)
        if 0x10 <= reg <= 0x1B: return 'ADPCM-B'
        if reg in (0x22, 0x24, 0x25, 0x26, 0x27): return 'timer/LFO'
        if reg == 0x28: return 'FM key'
        return 'FM ch1-2'
    if reg <= 0x2D: return 'ADPCM-A'
    return 'FM ch3-4'

def diff(qpath, fpath):
    q, f = frames(qpath), frames(fpath)
    added, removed = defaultdict(list), defaultdict(list)
    for fr in sorted(set(q) | set(f)):
        a = f[fr] - q[fr]; r = q[fr] - f[fr]
        for (port, reg, val), n in a.items(): added[unit(port, reg)].append((fr, port, reg, val))
        for (port, reg, val), n in r.items(): removed[unit(port, reg)].append((fr, port, reg, val))
    return added, removed

if __name__ == '__main__':
    added, removed = diff(sys.argv[1], sys.argv[2])
    print('only with effects (added):'); [print(f'  {u:10} {len(v):5}  first frames {sorted({x[0] for x in v})[:10]}') for u, v in sorted(added.items())]
    print('only without (displaced music):'); [print(f'  {u:10} {len(v):5}  first frames {sorted({x[0] for x in v})[:10]}') for u, v in sorted(removed.items())]
