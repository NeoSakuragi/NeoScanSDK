#!/usr/bin/env python3
"""Note 20261014-142848-5d29: Kyo's 75 Shiki Kai (KOF98 236D, the brawler's down + C) with its second kick on a second
press, as KOF98 plays it (handlers98 FOLLOW_READ: $3C90E reads B / D pressed this frame on every frame of the jump's rise
145; pressed, the second kick 148 starts on the rise's $0080 step (special frame 20) or at once past it, up to the apex
(27); none, the jump lands with 146).

A. KOF98 in our emulator against the decoded program's model: the second D pressed at every frame t (whiff, and on hit
   where the hit-stop is dropped): the frame 148 starts in each (the game reads the press 6 frames after its button).
B. the brawler against KOF98 (romspecials_check: harness, frame by frame, sheets): no second press, an early one (KOF t 11:
   read on the rise's first frame -> the kick at 20 at once) and a late one (t 21 -> the kick at 27), whiff and on hit.

C. the reopen (Bruno: "it comes out even if the first one whiffs; no need for down C, just C in the air"): the brawler
   alone, the note's scenario: C alone (and down + C) at frame k of the move, whiff and hit: the second kick for every k
   from the first kick to the apex (handlers98 FOLLOW_BUF: any press since the move's start; link 'AB' = C, any stick),
   none without one or past the apex; on a hit both kicks connect. (The B rows' 'close' branch no longer reaches its
   dummy in romspecials_check's campaign set-up since the stage intro: brawler_hits [] there for every fighter.)

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

def part_c():
    """the reopen (Bruno: "it comes out even if the first one whiffs; no need for down C, just C in the air"): in the
    brawler, the note's scenario (Ryo far: whiff), down + C then C ALONE at frame k of the move (0 = the down + C
    frame's next), and down + C again at k: the second kick (the program's part 1) comes for every k from the first kick
    to the apex; none without a second press; a press after the apex gives none (KOF's reads end there)"""
    import harness as H, scenario
    b = H.Brawler(); b.game = scenario.GAME
    rec = json.load(open(os.path.join(HERE, 'scenarios.json')))['20261014-142848-5d29']
    st = b.states
    hit = {'setup': dict(rec['setup'], gap=50)}         # (and on a hit: Ryo 50 px ahead, the first kick connects)
    hit['setup'].pop('x', None)
    out = []
    for branch, r_, keys, ks in (('whiff', rec, 'c', [None, 1, 3, 6, 10, 14, 18, 21, 26, 40]), ('whiff', rec, 'Dc', [3, 14]),
                                 ('hit', hit, 'c', [None, 3, 14])):
        for k in ks:
            scenario.setup(b, r_)
            parts, frames, began, hits, hp = set(), [], None, 0, b.fget(2, 'hp')
            for f in range(200):
                p1 = 'Dc' if f < 2 else (keys if k is not None and k + 2 <= f < k + 4 else '')
                b.run(1, p1=p1)
                s0 = st[b.fget(0, 'state')]
                h = b.fget(2, 'hp'); hits += h < hp; hp = h
                if s0 == 'SPECIAL':
                    began = f if began is None else began
                    parts.add(b.fget(0, 'plink') & 1); frames.append(b.fget(0, 'frame_ovr'))   # (plink bit 0: the
                                                                    # second kick's link taken, romspecials_check's parts)
                elif began is not None: break
            if k is None: none_frames = frames
            out.append({'branch': branch, 'press': keys, 'at': k, 'parts': sorted(parts), 'kick2': 1 in parts and frames != none_frames,
                        'frames': len(frames), 'hits': hits})
            print(out[-1], flush=True)
    want = lambda r: r['at'] is not None and r['at'] <= 26     # (from the first kick to the apex: the rise's last read)
    return [dict(r, ok=r['kick2'] == want(r) and (r['branch'] == 'whiff' or r['hits'] == 1 + r['kick2'])) for r in out]


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    if os.environ.get('SCISSOR_PART_C'):                 # (the harness core is one per process: part C in its own)
        json.dump(part_c(), open(os.path.join(OUT, 'part_c.json'), 'w'), indent=1); sys.exit(0)
    import subprocess
    subprocess.run([sys.executable, os.path.abspath(__file__), GAME, OUT], env=dict(os.environ, SCISSOR_PART_C='1'), check=True)
    c = json.load(open(os.path.join(OUT, 'part_c.json')))
    print(f"C (brawler, whiff, C alone / down + C at frame k): {sum(r['ok'] for r in c)} / {len(c)} as wanted", flush=True)
    a = part_a()
    RC.main(GAME, OUT, ['kyo:dD', 'kyo:dD+AB@11', 'kyo:dD+AB@21'])
    b = json.load(open(os.path.join(OUT, 'summary.json')))
    bb = [{k: s[k] for k in ('case', 'branch', 'kof_states', 'kof_frames', 'brawler_frames', 'brawler_parts', 'frame_mismatch', 'kof_hits', 'brawler_hits')} for s in b]
    res = {'a_runs': len(a), 'a_ok': sum(r['ok'] for r in a), 'b_runs': len(bb), 'b_frame_exact': sum(s['frame_mismatch'] == 0 for s in bb), 'a': a, 'b': bb, 'c_runs': len(c), 'c_ok': sum(r['ok'] for r in c), 'c': c}
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print(f"A (KOF98 vs model): {res['a_ok']} / {res['a_runs']} ok; B (brawler vs KOF98, frames): {res['b_frame_exact']} / {res['b_runs']} exact; C (brawler, whiff, C alone): {res['c_ok']} / {res['c_runs']} as wanted; sheets {OUT}/kyo_236D*.png")
    ok = res['a_ok'] == res['a_runs'] and res['b_frame_exact'] == res['b_runs'] and res['c_ok'] == res['c_runs']
    print('ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)
