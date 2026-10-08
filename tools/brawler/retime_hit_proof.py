#!/usr/bin/env python3
"""Revamp phase 2, item 4: a squeezed retimed hit connects where its source's did (fighter.c rt_probe; docs/brawler_data_model.md
"Retiming"). Revamp 1C tested collisions once a game frame: a squeezed segment (T < S) passes several source frames in
one game frame and only the frame shown had its box tested, so an attack box that reaches only on a frame passed over
missed. Now every source frame passed runs its hit test (rt_probe -> strike).

Our emulator's core (harness, Chain Lab training: the fighter against a standing dummy; targets installed at run time as
retime_proof.py does). Per move and plan (each active window squeezed to 1 frame: `win1`; the whole move at 0.5x), the
dummy at each distance 16..160 px (step 4): hit or not at the source timing, squeezed with the hit test of 1C only
(RAM rt_probe_off = 1: the test switch) and squeezed with rt_probe. Pass: wherever the source hits, the squeezed move
hits too (rt_probe); the 1C column shows the distances it lost (the limit fixed).

    python3 retime_hit_proof.py OUT                    -> OUT/retime_hit.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness, retime as RT
from retime_proof import install, training, DUMMY

TESTS = [('terry', 'a', None), ('terry', 'Rc', '214C'), ('terry', 'Dc', '623C'), ('krauser', 'a', None),
         ('haohmaru', 'Dc', '623S'), ('cheng_fu', 'Rc', '236'), ('kim', 'c', '214B'), ('ryo', 'Dc', '623A')]
DISTS = range(16, 164, 4)

def run_one(b, start, keys, dx, tab, off):
    b.load(start); install(b, tab); b.w(b.syms['rt_probe_off'], 1, 1 if off else 0)
    x0, z0 = b.fget(0, 'x'), b.fget(0, 'z'); b.place(DUMMY, x=x0 + dx, z=z0); b.run(2)
    anim, hit = None, False
    for k in range(120):
        b.run(1, p1=keys if k < 2 else '')
        if anim is None and b.states[b.fget(0, 'state')] in ('ATTACK', 'SPECIAL'): anim = b.fget(0, 'anim')
        if b.fget(DUMMY, 'hp') < 60 or b.states[b.fget(DUMMY, 'state')] in ('HITSTUN', 'KNOCKDOWN'): hit = True; break
    return hit, anim

def main(out):
    os.makedirs(out, exist_ok=True)
    G = json.load(open(os.path.join(harness.GAME, 'game.json'))); names = [r['name'] for r in G['roster']]
    lab = json.load(open(os.path.join(harness.GAME, 'build', 'chainlab.json'))); ba = lab['ba']
    F = {f['name']: f for f in lab['fighters']}
    b = harness.Brawler(tick_sync=True); rep = []
    for fname, keys, move in TESTS:
        start = training(b, names, fname); fid = names.index(fname)
        for plan in ('win1', 0.5):
            row = {'fighter': fname, 'keys': keys, 'plan': plan, 'dists': {}}
            for d in DISTS:
                src, anim = run_one(b, start, keys, d, [], False)
                if move: pool = [p['input'] for p in F[fname]['pool']]; idx = len(ba) + pool.index(move); segs = F[fname]['segs']['specials'][pool.index(move)]
                elif anim is not None: idx = anim; segs = F[fname]['segs']['moves'].get(ba[anim]) or []
                else: continue
                if not segs: continue
                T = [1 if k % 2 else s for k, s in enumerate(segs)] if plan == 'win1' else RT.targets({'scale': plan}, segs)
                old, _ = run_one(b, start, keys, d, [(fid, idx, T)], True)
                new, _ = run_one(b, start, keys, d, [(fid, idx, T)], False)
                row['move'] = move or ba[anim] if anim is not None else move
                row['dists'][d] = {'src': src, '1c': old, 'now': new, 'segs': segs, 'T': T}
            ds = row['dists']
            row['src_hits'] = [d for d, v in ds.items() if v['src']]
            row['lost_1c'] = [d for d, v in ds.items() if v['src'] and not v['1c']]
            row['lost_now'] = [d for d, v in ds.items() if v['src'] and not v['now']]
            row['ok'] = not row['lost_now']
            rep.append(row)
            print(f"{'OK ' if row['ok'] else 'BAD'} {fname:9s} {str(row.get('move')):12s} {str(plan):5s} source hits at {len(row['src_hits'])} distances, "
                  f"1C missed {row['lost_1c']}, now missed {row['lost_now']}", flush=True)
    json.dump(rep, open(os.path.join(out, 'retime_hit.json'), 'w'), indent=0)
    print('all ok:', all(r['ok'] for r in rep), '| 1C limit shown on', sum(bool(r['lost_1c']) for r in rep), 'of', len(rep), 'runs')

if __name__ == '__main__':
    main(sys.argv[1])
