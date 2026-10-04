"""Brawler regressions, run on one ROM (one core per process):
  bleed   the same game after attract-demo lengths 0/1500/2600/3700 frames: P1's trace from the fight start (mode 1,
          attract 0) under a fixed input script must be identical for every length
  facing  14 fighters (picked on the select screen) x 13 actions: per frame P1 state + facing + x, written to JSON for a
          comparison between builds
    python3 regress.py GAME_DIR OUT.json   (GAME_DIR/brawler.neo, symbols from GAME_DIR/build/rom.elf)"""
import sys, json
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Brawler
game, out = sys.argv[1], sys.argv[2]
b = Brawler(rom=game + '/brawler.neo', game=game)
res = {}
def p1():
    return (b.states[b.fget(0, 'state')], round(b.fget(0, 'x'), 2), round(b.fget(0, 'z'), 2), round(b.fget(0, 'y'), 2),
            b.fget(0, 'facing'), b.fget(0, 'hp'), b.fget(0, 'anim'), b.fget(0, 'step'))
SCRIPT = '30:R,10:-,4:a,10:-,4:a,10:-,4:b,30:-,20:L,4:c,60:-,4:d,80:-,30:Rd,60:-,40:D,4:b,60:-,4:Ra,40:-,4:Ud,100:-'
bleed = {}
for n in (0, 1500, 2600, 3700):
    b.core.retro_reset(); b.frame = 0
    b.run(600 + n)                                         # power on, the attract demo for n frames
    b.seq('4:o,100:-,4:s,100:-,4:a')
    k = 0
    while not (b.r(b.syms['mode'], 1) == 1 and b.r(b.syms['attract'], 1) == 0):
        b.run(1); k += 1
        assert k < 2000, 'no fight'
    tr = []
    for part in SCRIPT.split(','):
        m, keys = part.split(':')
        for _ in range(int(m)): b.run(1, p1=keys); tr.append(p1())
    bleed[n] = tr
same = all(bleed[n] == bleed[0] for n in bleed)
print('bleed: identical P1 traces for 0/1500/2600/3700:', same, 'frames', len(bleed[0]))
if not same:
    for n in bleed:
        d = next((i for i, (a, c) in enumerate(zip(bleed[0], bleed[n])) if a != c), None); print(' ', n, 'first diff at', d)
res['bleed_same'] = same; res['bleed_trace'] = bleed[0]
ACTIONS = [('walk_L', '20:L,10:-'), ('walk_R', '20:R,10:-'), ('run_R', '3:R,3:-,20:R,10:-'), ('run_L', '3:L,3:-,20:L,10:-'),
           ('A', '4:a,40:-'), ('B', '4:b,40:-'), ('jump_up', '4:c,60:-'), ('jump_fwd', '4:Rc,60:-'), ('jump_back', '4:Lc,60:-'),
           ('D', '4:d,90:-'), ('fwd_D', '4:Rd,90:-'), ('down_D', '4:Dd,90:-'), ('up_D', '4:Ud,90:-')]
facing = {}
for k in range(14):
    b.pick(k)
    while b.r(b.syms['fade_in'], 1): b.run(1)       # the fight in full colour: P1 under control, phase-free
    b.run(10); st = b.save()
    name = b.char_of(0)
    for an, seq in ACTIONS:
        b.load(st)
        for i in range(1, 8): b.place(i, x=1000, z=0)
        b.place(0, x=300, z=30); b.place(2, x=260, z=30)           # an enemy behind P1 (P1 faces right)
        b.run(2)
        tr = []
        for part in seq.split(','):
            m, keys = part.split(':')
            for _ in range(int(m)): b.run(1, p1=keys); tr.append((b.states[b.fget(0, 'state')], b.fget(0, 'facing'), round(b.fget(0, 'x'), 1)))
        facing[f'{k}:{an}'] = tr
    print('fighter', k, name, 'done', flush=True)
res['facing'] = facing
json.dump(res, open(out, 'w'))
