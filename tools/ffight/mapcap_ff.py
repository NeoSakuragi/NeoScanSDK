#!/usr/bin/env python3
"""Capture Final Fight's between-rounds city map in FBNeo (the study harness /data/emu/harness/lr.py, no MAME).

The map is drawn on the round-clear screen ("ROUND n CLEAR!") over the stage, on the scroll1 (8x8) layer.
Game flow read in the 68000 code (main state word $FF8000, jump table $4C90):
  6 in game -> (round end flag $FF8129 bit 7) 8: next sub-area ($FF80BF+1; table $5482 = sub-areas per round)
  -> past the last one: 10 ($4E92): waits for $FF8129 to clear (the round-clear sequence), then $54BA:
  sequence index $FF80C1+1, round $FF80BE = table $54FC [round, bonus flag] = (0,0) (1,0) (6,1) (2,0) (3,0) (7,1)
  (4,0) (5,0) (8,0) (9,0): Slum, Subway, bonus car, West Side, Industrial, bonus glass, Bay Area, Uptown.
So any round's clear screen = a running game state + $FF80BE / $FF80C1 set + $FF80BF = last sub-area +
$FF8129 = $80.  Usage: mapcap_ff.py BASE_STATE OUT_DIR  (BASE_STATE: any in-game FBNeo state of ffight)
Writes OUT_DIR/clear_<seq>.state + .png at the frame the map is fully up (300 frames after the trigger).
"""
import os, sys
sys.path.insert(0, '/data/study/ffight/scripts')
from ffl import core, w8, w16, rb, rw   # noqa: E402

SEQ = [(0, 0), (1, 0), (6, 1), (2, 0), (3, 0), (7, 1), (4, 0), (5, 0)]
SUBS = [3, 4, 3, 2, 1, 3, 1, 1]          # table $5482: sub-areas per round id

_C = None
def capture(base, out, seq, wait=300):
    global _C
    if _C is None: _C = core()             # one core per process
    c = _C; c.load(open(base, 'rb').read())
    rnd = SEQ[seq][0]
    w8(c, 0xFF80BE, rnd); w8(c, 0xFF80C1, seq); w8(c, 0xFF80BF, SUBS[rnd] - 1); w8(c, 0xFF8129, 0x80)
    c.run(wait)
    open(f'{out}/clear_{seq}.state', 'wb').write(c.save()); c.png(f'{out}/clear_{seq}.png')
    r = c.ram(); return rw(r, 0xFF8000), rb(r, 0xFF80BE)

if __name__ == '__main__':
    base, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
    for k in range(len(SEQ)):
        print(k, SEQ[k], capture(base, out, k))
