#!/usr/bin/env python3
"""Proof of the Lab builds' PRACTICE MODE (examples/brawler/main.c "PRACTICE MODE", fighter.h prac_t; Bruno 2026-10-10),
in our emulator (harness, the repo's Geolith core; never MAME):

    python3 practice_proof.py [FIGHTER] [OUT]      (default robert, /data/tmp/practice; needs make LAB_FIGHTER=FIGHTER)

Power on: the build boots straight into the practice (P1 = its LAB fighter, one standing dummy). Then every menu line is
driven through the menu itself (START, the stick, A), never by poking `prac`, and its effect read back from RAM:
fury gauge full / empty, MAX ready (P1's life at gmeter.low: the red bar; down+D plays the MAX), drive infinite, P1 life
the game's / low, 3 dummies with AI (they move and attack), walk-in dummies, waves on (wave enemies walk in), dummy life
normal (a dummy's life goes down), hit boxes, reset positions, apply now (lab.tnow), the game paused while the menu is
open, and the settings kept across a reset. Screenshots: OUT/menu.png, max_ready.png, dummies_ai.png, waves.png, ..."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from harness import Brawler

F = sys.argv[1] if len(sys.argv) > 1 else 'robert'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/practice'
GAME = harness.GAME
os.makedirs(OUT, exist_ok=True)
_lay = harness._layout
harness._layout = lambda game, build='build': _lay(game, f'build_lab_{F}')
b = Brawler(rom=os.path.join(GAME, f'lab-{F}.neo'), game=GAME)
S = b.syms
PS = ['FURY', 'MAX', 'DRIVE', 'LIFE', 'DUMMIES', 'MODE', 'WAVES', 'DLIFE', 'BOXES']
PM_RESET, PM_APPLY, PM_EXIT = 9, 10, 11
ST = b.states
G = json.load(open(os.path.join(GAME, 'game.json')))
names = [r if isinstance(r, str) else r.get('name') for r in G['roster']]
M = G['meter']; FULL_DRIVE = M['chunk'] * M['chunks']; LO = 60 * M['low'] // 100
LAB_ACTIVE = 8
fails = []
def check(ok, what):
    print(('ok   ' if ok else 'FAIL ') + what)
    if not ok: fails.append(what)
def pset(k): return b.r(S['prac'] + 4 + k, 1)
def state(i): return ST[b.fget(i, 'state')]
def tap(key, hold=1, after=3): b.run(hold, key); b.run(after)
def menu_open():
    if not b.r(S['prac'] + 16, 1): tap('s')
    assert b.r(S['prac'] + 16, 1) == 1, 'the menu did not open'
def menu_row(r):
    while b.r(S['pm_row'], 1) != r: tap('D')
def menu_set(name, v, close=True):
    menu_open(); k = PS.index(name); menu_row(k)
    for _ in range(6):
        if pset(k) == v: break
        tap('R')
    assert pset(k) == v, f'{name} never reached {v}'
    if close: tap('s'); b.run(2)
def menu_do(row):
    menu_open(); menu_row(row); tap('a'); b.run(2)

# ---- boot ------------------------------------------------------------------------------------------------------------
b.core.retro_reset(); b.frame = 0
for _ in range(3000):
    b.run(1)
    if b.r(S['lab'] + LAB_ACTIVE, 1) == 1: break
b.run(60)
check(b.r(S['lab'] + LAB_ACTIVE, 1) == 1, f'boots straight into the practice (lab.active 1) at frame {b.frame}')
check(names[b.char_of(0)] == F, f'P1 is the Lab fighter ({names[b.char_of(0)]})')
check(bytes(b.r(S['prac'] + i, 1) for i in range(4)) == b'PRC1', 'prac block "PRC1" with defaults ' + str([pset(k) for k in range(9)]))
check([state(i) for i in range(2, 8)] == ['IDLE'] + ['OFF'] * 5 or state(2) in ('IDLE', 'WALK'), f'one standing dummy ({b.brief(range(2, 4))})')
b.screenshot(os.path.join(OUT, 'boot.png'))

# ---- the menu pauses the game ------------------------------------------------------------------------------------------
menu_open(); b.run(2)
t0, st0, x0 = b.r(S['game_ticks'], 4), b.fget(2, 'state_t'), b.fget(0, 'x')
b.run(30, 'R')
check(b.r(S['game_ticks'], 4) > t0 and b.fget(2, 'state_t') == st0 and b.fget(0, 'x') == x0, 'menu open: the game ticks, nothing moves (paused)')
b.screenshot(os.path.join(OUT, 'menu.png'))
tap('s'); check(b.r(S['prac'] + 16, 1) == 0, 'START closes the menu')

# ---- fury gauge ------------------------------------------------------------------------------------------------------
menu_set('FURY', 1); b.run(5); check(b.fget(0, 'fgauge') == M['fury_max'], f"fury gauge FULL: fgauge {b.fget(0, 'fgauge')}")
menu_set('FURY', 2); b.run(5); check(b.fget(0, 'fgauge') == 0, f"fury gauge EMPTY: fgauge {b.fget(0, 'fgauge')}")
menu_set('FURY', 0)

# ---- MAX ready -------------------------------------------------------------------------------------------------------
menu_set('MAX', 1); b.run(10)
check(b.fget(0, 'hp') == LO and b.fget(0, 'fgauge') == M['fury_max'] and b.fget(0, 'drive') == FULL_DRIVE,
      f"MAX READY: hp {b.fget(0, 'hp')} (= low {LO}), gauge {b.fget(0, 'fgauge')}, drive {b.fget(0, 'drive')}")
for _ in range(20):                                    # the life bar blinks red 8 / 8: shoot a red frame
    if b.r(S['hud_red'], 1) == 1: break
    b.run(1)
check(b.r(S['hud_red'], 1) == 1, 'the life bar blinks red (hud_red)')
b.screenshot(os.path.join(OUT, 'max_ready.png'))
b.run(1, 'D'); b.run(2, 'Dd'); fm = 0
for _ in range(40):
    b.run(1); fm |= b.fget(0, 'fmax')
check(fm == 1, 'down+D plays the MAX (fmax)')
b.screenshot(os.path.join(OUT, 'max_played.png'))
b.run(240)
menu_set('MAX', 0); b.run(5)

# ---- drive -----------------------------------------------------------------------------------------------------------
menu_set('DRIVE', 1); b.run(5); tap('c', 2, 30)
check(b.fget(0, 'drive') == FULL_DRIVE, f"drive INFINITE after a C special: {b.fget(0, 'drive')}")
menu_set('DRIVE', 0); b.run(120); tap('c', 2, 10)
check(b.fget(0, 'drive') < FULL_DRIVE, f"drive NORMAL: a C special spends it ({b.fget(0, 'drive')})")
b.run(200)

# ---- dummies: 3 with AI ----------------------------------------------------------------------------------------------
menu_set('LIFE', 1, close=False); menu_set('DUMMIES', 3, close=False); menu_set('MODE', 1)
b.run(2)
on = [state(i) != 'OFF' for i in range(2, 8)]
check(on == [True] * 3 + [False] * 3, f'3 dummies: {b.brief(range(2, 6))}')
xs = [b.fget(i, 'x') for i in (2, 3, 4)]; seen, hp0, low = set(), b.fget(0, 'hp'), 99
for k in range(360):
    b.run(1); seen |= {state(i) for i in (2, 3, 4)}; low = min(low, b.fget(0, 'hp'))
    if k == 150: b.screenshot(os.path.join(OUT, 'dummies_ai.png'))
moved = sum(abs(b.fget(i, 'x') - x) > 8 for i, x in zip((2, 3, 4), xs))
check(moved >= 2 and seen & {'ATTACK', 'GRAB', 'SPECIAL'}, f'AI ON: {moved} dummies moved, states seen {sorted(seen)}')
check(low < hp0, f'P1 life NORMAL: the dummies hurt P1 ({hp0} -> {low})')
menu_set('LIFE', 2); b.run(5); check(b.fget(0, 'hp') == LO, f"P1 life LOW: {b.fget(0, 'hp')}")
menu_set('LIFE', 0); b.run(5); check(b.fget(0, 'hp') == 60, f"P1 life REFILL: {b.fget(0, 'hp')}")

# ---- walk in and attack ----------------------------------------------------------------------------------------------
menu_set('MODE', 2); seen = set(); xs = [b.fget(i, 'x') for i in (2, 3, 4)]
for _ in range(200): b.run(1); seen |= {state(i) for i in (2, 3, 4)}
check('WALK' in seen and 'ATTACK' in seen, f'WALK + ATTACK: states seen {sorted(seen)}')
b.screenshot(os.path.join(OUT, 'dummies_attack.png'))

# ---- dummy life normal -----------------------------------------------------------------------------------------------
menu_set('MODE', 0, close=False); menu_set('DUMMIES', 1, close=False); menu_set('DLIFE', 1); b.run(2)
menu_do(PM_RESET); b.run(10)
check(abs(b.fget(0, 'x') - (b.r(S['cam_x'], 2) + 110)) < 2 and abs(b.fget(2, 'x') - (b.r(S['cam_x'], 2) + 190)) < 2,
      f"RESET POSITIONS: P1 x {b.fget(0, 'x'):.0f}, dummy x {b.fget(2, 'x'):.0f} (camera {b.r(S['cam_x'], 2)})")
b.fset(0, 'x', b.fget(2, 'x') - 50); b.fset(0, 'z', b.fget(2, 'z')); b.run(2)
hp0 = b.fget(2, 'hp'); low = hp0
for _ in range(8): b.run(3, 'a'); b.run(9); low = min(low, b.fget(2, 'hp'))
for _ in range(40): b.run(1); low = min(low, b.fget(2, 'hp'))
check(low < hp0 and b.fget(2, 'hp') < hp0, f"DUMMY LIFE NORMAL: its life {hp0} -> {b.fget(2, 'hp')} (not refilled)")
menu_set('DLIFE', 0); b.run(180)
check(b.fget(2, 'hp') == 60, f"DUMMY LIFE INFINITE: refilled ({b.brief(range(2, 3))}, menu {b.r(S['prac'] + 16, 1)})")

# ---- waves -----------------------------------------------------------------------------------------------------------
menu_set('WAVES', 1); n = 0
for k in range(400):
    b.run(1); n = max(n, sum(state(i) != 'OFF' for i in range(3, 8)))
    if k == 230: b.screenshot(os.path.join(OUT, 'waves.png'))
check(n >= 2, f'WAVES ON: {n} wave enemies came ({b.brief(range(2, 8))})')
menu_set('WAVES', 0); b.run(2)
check(all(state(i) == 'OFF' for i in range(3, 8)), 'WAVES OFF: the wave enemies taken off')

# ---- hit boxes, apply now ----------------------------------------------------------------------------------------------
menu_set('BOXES', 1); b.run(5); check(b.r(S['dbg_on'], 1) == 1, 'HIT BOXES ON: the box viewer (dbg_on)')
b.screenshot(os.path.join(OUT, 'boxes.png'))
menu_set('BOXES', 0); b.run(2); check(b.r(S['dbg_on'], 1) == 0, 'HIT BOXES OFF')
tn = S['lab'] + b.syms['lab_fields']['tnow']; b.w(tn, 1, 0)
menu_do(PM_APPLY); check(b.r(tn, 1) == 1 and b.r(S['prac'] + 16, 1) == 0, 'APPLY CONFIG NOW: lab.tnow = 1, the menu closed')
b.w(tn, 1, 0)
menu_do(PM_EXIT); check(b.r(S['prac'] + 16, 1) == 0, 'EXIT closes the menu')

# ---- kept across a reset -----------------------------------------------------------------------------------------------
menu_set('DUMMIES', 3, close=False); menu_set('FURY', 1); b.run(2)
want = [pset(k) for k in range(9)]
b.core.retro_reset(); b.frame = 0
for _ in range(3000):
    b.run(1)
    if b.r(S['lab'] + LAB_ACTIVE, 1) == 1: break
b.run(30)
check([pset(k) for k in range(9)] == want and sum(state(i) != 'OFF' for i in range(2, 8)) == 3 and b.fget(0, 'fgauge') == M['fury_max'],
      f'a reset keeps the settings {want}: {b.brief(range(2, 6))}')
b.screenshot(os.path.join(OUT, 'after_reset.png'))
print('ALL OK' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
