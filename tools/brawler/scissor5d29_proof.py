#!/usr/bin/env python3
"""Note 20261014-142848-5d29: Kyo's 75 Shiki Kai (KOF98 236D, the brawler's down + C) with its second kick on a second
press, as KOF98 plays it (handlers98 FOLLOW_READ: $3C90E reads B / D pressed this frame on every frame of the jump's rise
145; pressed, the second kick 148 starts on the rise's $0080 step (special frame 20) or at once past it, up to the apex
(27); none, the jump lands with 146).

A. KOF98 in our emulator against the decoded program's model: the second D pressed at every frame t (whiff, and on hit
   where the hit-stop is dropped): the frame 148 starts in each (the game reads the press 6 frames after its button).
B. the brawler against KOF98 (romspecials_check: harness, frame by frame, sheets): no second press, an early one (KOF t 11:
   read on the rise's first frame -> the kick at 20 at once) and a late one (t 21 -> the kick at 27), whiff and on hit.

    python3 scissor5d29_proof.py GAME_DIR [OUT]          (default OUT /data/tmp/scissor5d29; OUT/proof.json, OUT/*.png)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
import romspecials98 as K
import romspecials_check as RC

GAME = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'examples', 'brawler')
OUT = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/scissor5d29'

def part_a():
    out = []
    for dist, ts in (('whiff', range(8, 26)), ('close', range(19, 38, 2))):
        for t in ts:
            res, game, model, _, _ = K.compare(0, '236D', dist, frames=110, quiet=True, follow=[(t, [(0, 2, 'd')], 1)])
            g = next((i for i, r in enumerate(game) if r['state'] == 148), None)
            mo = next((i for i, r in enumerate(model) if r[1] == 148), None)
            r = {'branch': dist, 'press': t, 'read': res['press_frames'], 'kof_kick2': g, 'model_kick2': mo,
                 'frame_mismatch': res['by']['frame'], 'ok': g == mo and res['by']['frame'] == 0}
            out.append(r); print(r, flush=True)
    return out

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    a = part_a()
    RC.main(GAME, OUT, ['kyo:dD', 'kyo:dD+again@11', 'kyo:dD+again@21'])
    b = json.load(open(os.path.join(OUT, 'summary.json')))
    bb = [{k: s[k] for k in ('case', 'branch', 'kof_states', 'kof_frames', 'brawler_frames', 'brawler_parts', 'frame_mismatch', 'kof_hits', 'brawler_hits')} for s in b]
    res = {'a_runs': len(a), 'a_ok': sum(r['ok'] for r in a), 'b_runs': len(bb), 'b_frame_exact': sum(s['frame_mismatch'] == 0 for s in bb), 'a': a, 'b': bb}
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print(f"A (KOF98 vs model): {res['a_ok']} / {res['a_runs']} ok; B (brawler vs KOF98, frames): {res['b_frame_exact']} / {res['b_runs']} exact; sheets {OUT}/kyo_236D*.png")
