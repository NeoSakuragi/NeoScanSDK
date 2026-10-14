#!/usr/bin/env python3
"""AOF2 Spirit Training, a failed grade vs the top grade, measured in our emulator (note 20261014-133606-5d29, Bruno: "the
real sound from the original game when it's FAILED" and "a charging, concentrating, gathering energy animation played
just before the attack"). From the bonus select state (/data/tmp/t7/aof2_sel.state: A picks Spirit Training at frame 4),
A on the gauge at frame P; SNDLOG = every byte the 68000 sends to REG_SOUND, a screenshot every 2 frames.

Measured (P = 509 / 521: grade 2, failed; P = 541: grade 5, the pass): Ryo stands ~7 frames, then his concentration pose
(hands together, the glow) until his punch; the punch's sends ($15 $45 $D5, $1C $12 his shout, $1A $BA the blow on the
tree) come at P + 61 on a fail and P + 121 on the pass (the concentration lasts twice as long). On a fail, from that
blow B: $1C $14 (Ryo's hurt voice, B + 105: he shakes his hand), 13 x $1A $C6 / $C7 (the leaves, B + 109 .. 170), the fail
jingle $2E at B + 277 and the result (BONUS) at ~B + 284. On the pass the tree's crack / fall ($1A $B7 / $B8:
tree_snd_proof.py). -> OUT/ki_fail.json (per run: P, the sends relative to P and to B), OUT/p<P>/snap_*.ppm

    python3 ki_fail.py [OUT]           (default /data/tmp/kifail)"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
EMU = os.path.normpath(os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl'))
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kifail'
RUNS = {509: 'fail', 521: 'fail', 541: 'pass'}


def run(P):
    d = f'{OUT}/p{P}'; os.makedirs(d, exist_ok=True)
    env = dict(os.environ, LOAD='/data/tmp/t7/aof2_sel.state', SEQ=f'4:a,{P - 4}:-,4:a,1100:-', SNDLOG=f'{d}/snd.log',
               SNAPS=','.join(map(str, range(480, 1700, 2))), SNAPDIR=d)
    subprocess.run(['timeout', '900', EMU, '/data/roms/aof2.neo', '--capture'], env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    rows = [(int(l.split()[0]), l.split()[1]) for l in open(f'{d}/snd.log') if l.strip()]
    rows = [(f, c) for f, c in rows if f > P and c != '6A']          # ($6A: the clock's tick every 60 frames)
    B = next(f for f, c in rows if c == '15')                        # the punch's first send
    return {'press': P, 'blow': B, 'blow_after_press': B - P, 'sends': [(f - P, f - B, c) for f, c in rows]}


if __name__ == '__main__':
    res = {P: dict(run(P), grade=k) for P, k in RUNS.items()}
    for P, r in res.items(): print(P, r['grade'], 'blow at press +', r['blow_after_press'], [(b, c) for _, b, c in r['sends']][:40])
    json.dump(res, open(f'{OUT}/ki_fail.json', 'w'), indent=1)
