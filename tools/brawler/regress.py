"""Brawler regressions, run on one ROM (one core per process):
  bleed   the same game after attract-demo lengths 0/1500/2600/3700 frames: P1's trace from the fight start (mode 1,
          attract 0) under a fixed input script must be identical for every length (to the frame-sampling jitter,
          see `near`)
  facing  every roster fighter (CHARS of the Makefile) (picked on the select screen) x 13 actions: per frame P1 state + facing + x, written to JSON for a
          comparison between builds
    python3 regress.py GAME_DIR OUT.json   (GAME_DIR/brawler.neo, symbols from GAME_DIR/build/rom.elf)"""
import sys, json, re
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Brawler
game, out = sys.argv[1], sys.argv[2]
b = Brawler(rom=game + '/brawler.neo', game=game)
res = {}
def p1():
    return (b.states[b.fget(0, 'state')], round(b.fget(0, 'x'), 2), round(b.fget(0, 'z'), 2), round(b.fget(0, 'y'), 2),
            b.fget(0, 'facing'), b.fget(0, 'hp'), b.fget(0, 'anim'), b.fget(0, 'step'))
SCRIPT = '30:R,10:-,4:a,10:-,4:a,10:-,4:b,30:-,20:L,4:c,60:-,4:d,80:-,30:Rd,60:-,40:D,4:b,60:-,4:Ra,40:-,4:Ud,100:-'
bleed = {}; ticks = {}                                     # ticks: game ticks done since the fight start, per frame
for n in (0, 1500, 2600, 3700):
    b.core.retro_reset(); b.frame = 0
    b.run(600 + n)                                         # power on, the attract demo for n frames
    b.seq('4:o,100:-,4:s,100:-,4:a')
    k = 0
    while not (b.r(b.syms['mode'], 1) == 1 and b.r(b.syms['attract'], 1) == 0):
        b.run(1); k += 1
        assert k < 2000, 'no fight'
    tr = []; tk = []; t0 = b.r(b.syms['hud_tick'], 2)
    for part in SCRIPT.split(','):
        m, keys = part.split(':')
        for _ in range(int(m)): b.run(1, p1=keys); tr.append(p1()); tk.append((b.r(b.syms['hud_tick'], 2) - t0) & 0xFFFF)
    bleed[n] = tr; ticks[n] = tk
# The harness reads RAM when a video frame ends, and that instant falls inside the game's tick, about where P1's
# update runs (the vblank flush before it varies with last frame's VRAM commands, the BIOS's SYSTEM_IO with the host
# clock): a sample shows P1 before or after this tick's update. Measured 2026-10-05: hud_tick advances one per frame
# identically in every run while a jump's y read 17.72, 4.76, 4.76 in one and 17.72, 11.5, 4.76 in another (flaky
# between runs of the same ROM). So a trace matches when every sample equals the other trace's at the same frame or
# one either side, and the game ticks done per frame (hud_tick) are exactly the same (a lag frame more or less, e.g.
# a slow first tick depending on what the demo left, shifts every later sample: caught here) = `same`; `strict` is the
# frame-exact comparison, kept for information. A bleed of state shows as a lasting difference, also caught.
def near(a, b):                    # frame by frame: one side's sample is the other's at that frame or one either side
    return len(a) == len(b) and all(a[i] in b[max(0, i - 1):i + 2] or b[i] in a[max(0, i - 1):i + 2] for i in range(len(a)))
strict = all(bleed[n] == bleed[0] for n in bleed)
same = all(near(bleed[n], bleed[0]) and ticks[n] == ticks[0] for n in bleed)
print('bleed: P1 traces for 0/1500/2600/3700 the same (+-1 frame sampling):', same, 'frame-exact:', strict, 'frames', len(bleed[0]))
if not strict:
    for n in bleed:
        d = next((i for i, (a, c) in enumerate(zip(bleed[0], bleed[n])) if a != c), None); print(' ', n, 'first exact diff at', d)
res['bleed_same'] = same; res['bleed_strict'] = strict; res['bleed_trace'] = bleed[0]
ACTIONS = [('walk_L', '20:L,10:-'), ('walk_R', '20:R,10:-'), ('run_R', '3:R,3:-,20:R,10:-'), ('run_L', '3:L,3:-,20:L,10:-'),
           ('A', '4:a,40:-'), ('B', '4:b,40:-'), ('jump_up', '4:c,60:-'), ('jump_fwd', '4:Rc,60:-'), ('jump_back', '4:Lc,60:-'),
           ('D', '4:d,90:-'), ('fwd_D', '4:Rd,90:-'), ('down_D', '4:Dd,90:-'), ('up_D', '4:Ud,90:-')]
facing = {}
NCHARS = len(re.search(r"^CHARS\s*=\s*(.+)$", open(os.path.join(game, "Makefile")).read(), re.M).group(1).split())
for k in range(NCHARS):
    b.pick(k, unlock=True)                         # campaign builds: the bosses are locked until beaten
    while b.r(b.syms['fade_in'], 1): b.run(1)       # the fight in full colour: P1 under control, phase-free
    b.run(10); st = b.save()
    name = b.char_of(0)
    for an, seq in ACTIONS:
        b.load(st)
        for i in range(1, 8): b.place(i, x=1000, z=0)
        b.place(0, x=300, z=30); b.place(2, x=260, z=30)           # an enemy behind P1 (P1 faces right)
        b.run(2)
        w = 0                                                      # out of any hit taken before the placement
        while b.states[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
        tr = []
        for part in seq.split(','):
            m, keys = part.split(':')
            for _ in range(int(m)): b.run(1, p1=keys); tr.append((b.states[b.fget(0, 'state')], b.fget(0, 'facing'), round(b.fget(0, 'x'), 1)))
        facing[f'{k}:{an}'] = tr
    print('fighter', k, name, 'done', flush=True)
res['facing'] = facing
json.dump(res, open(out, 'w'))
