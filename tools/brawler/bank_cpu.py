#!/usr/bin/env python3
"""TODO #174 frame-time measure: the game's own CPU % (main.c hud: 100 - the idle spins of the worst frame in each
16-tick window, wait_cycles) through the whole campaign, our emulator's core (harness). Power on -> coin -> START -> select
(the first fighter) -> per stage, per wave: P1 fights it for FIGHT frames (A, C + the stick, D: specials, furies,
projectiles; life refilled), then the wave is cleared (test poke: enemies OFF) as in campaign29; the boss fights for
FIGHT frames too. Per stage: the worst window, the mean, the windows; the same inputs every run (deterministic), so
two builds compare window for window.

    python3 bank_cpu.py OUT.json [GAME_DIR]      (GAME_DIR/brawler.neo, symbols from GAME_DIR/build/rom.elf)"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from harness import Brawler, GAME

FIGHT = 600
PATTERN = ['4:a', '8:-', '4:a', '8:-', '4:a', '12:-', '4:c', '30:-', '4:Rc', '30:-', '4:d', '60:-', '4:Dc', '30:-', '4:Uc', '40:-']
out = sys.argv[1]; game = sys.argv[2] if len(sys.argv) > 2 else GAME
b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game); S = b.syms; ST = b.states
OFF, DEAD = ST.index('OFF'), ST.index('DEAD')
def r1(n): return b.r(S[n], 1)
win = []                                                  # (hud_tick window end, CPU %)
last = {'tick': None, 'spins': None}
def watch(bb):
    bb.fset(0, 'hp', 60); bb.fset(0, 'meter', 120)
    t = bb.r(S['hud_tick'], 2); s = bb.r(S['hud_min_spins'], 2)
    if last['tick'] is not None and t != last['tick'] and (t & 15) == 0 and last['spins'] not in (None, 0xFFFF):
        idle = (last['spins'] * 7) >> 8
        win.append(0 if idle >= 100 else 100 - idle)
    last['tick'] = t; last['spins'] = s
def run(n, p1=''): b.run(n, p1=p1, each=watch)
def until(cond, n, p1='', what=''):
    for k in range(n):
        if cond(): return k
        run(1, p1)
    raise RuntimeError('timeout: ' + what)
def enemies(): return [i for i in range(2, 8) if b.fget(i, 'state') != OFF]
def fight(frames):
    k = 0
    while k < frames:
        for part in PATTERN:
            n, keys = part.split(':'); n = int(n); run(n, '' if keys == '-' else keys); k += n
b.core.retro_reset(); b.run(600)
b.seq('4:o,100:-,4:s,100:-,4:a')
until(lambda: r1('mode') == 1, 600, what='fight')
res = []
for st in range(5):
    assert r1('camp') == st, r1('camp')
    w0 = len(win); rec = {'stage': st + 1, 'waves': []}
    for w in range(5):
        until(lambda: r1('phase') == 0 and len(enemies()) > 0, 600, 'R', 'wave')
        a = len(win); fight(FIGHT)
        rec['waves'].append({'enemies': len(enemies()), 'windows': win[a:]})
        until(lambda: ST[b.fget(0, 'state')] in ('IDLE', 'WALK'), 900, what='P1 free')
        for i in range(2, 8): b.fset(i, 'state', OFF)          # test poke: the wave beaten
        until(lambda: r1('phase') == 1, 10, what='GO')
        until(lambda: r1('phase') != 1, 2000, 'R', 'next lock')
    until(lambda: r1('phase') == 2, 10, what='boss')
    a = len(win); fight(FIGHT); rec['boss'] = win[a:]
    until(lambda: ST[b.fget(0, 'state')] in ('IDLE', 'WALK') and ST[b.fget(2, 'state')] in ('IDLE', 'WALK'), 3000, what='P1 free')
    b.fset(2, 'hp', 0); b.fset(2, 'state', DEAD); b.fset(2, 'state_t', 0)   # test poke: the boss beaten
    until(lambda: r1('phase') == 4, 900, what='clear')
    ws = win[w0:]; rec['max'] = max(ws); rec['mean'] = round(sum(ws) / len(ws), 1)
    print(f"stage {st + 1}: CPU worst {rec['max']} %, mean {rec['mean']} % over {len(ws)} windows")
    res.append(rec)
    until(lambda: r1('mode') != 1 or r1('camp') != st, 900, what='after clear')
    if r1('mode') == 3: b.seq('4:a'); until(lambda: r1('mode') != 3, 400, what='unlock end')
    if st < 4: until(lambda: r1('mode') == 1 and r1('camp') == st + 1, 600, what='next stage')
json.dump(res, open(out, 'w'))
busiest = max(res, key=lambda r: r['mean'])
print(f"busiest stage {busiest['stage']}: worst {busiest['max']} %, mean {busiest['mean']} %")
