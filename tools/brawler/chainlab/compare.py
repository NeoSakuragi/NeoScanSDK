#!/usr/bin/env python3
"""Compare two Chain Lab traces (labdrive.py: the desktop core; proof_node.js / the page: the browser's core):
per frame lab frame + P1 / dummy (state, anim, step, x, hp), the lab events, the combo readout.
    python3 compare.py A.json B.json"""
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
ta, tb = a['trace'], b['trace']
diff = [i for i in range(min(len(ta), len(tb))) if ta[i] != tb[i]]
ea, eb = [list(e) for e in a['events']], [list(e) for e in b['events']]
print(f'trace: {len(ta)} / {len(tb)} frames, {len(diff)} differ' + (f' (first at {diff[0]}: {ta[diff[0]]} vs {tb[diff[0]]})' if diff else ''))
print(f'events: {len(ea)} / {len(eb)}, identical: {ea == eb}; combo {a["combo"]} / {b["combo"]}')
hits = [e for e in ea if e[1] == 'HIT']
print('hit sequence (frame, node, damage):', [(e[0], e[2], e[4]) for e in hits])
sys.exit(0 if not diff and ea == eb and len(ta) == len(tb) and a['combo'] == b['combo'] else 1)
