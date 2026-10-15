#!/usr/bin/env python3
"""The unlock ladder (game.json unlocks, main.c "the unlock ladder"; Bruno 2026-10-15, decisions set unlocks), played in
our emulator (harness.py, the arcade system mvs-mvs = SNK's MVS BIOS, a fresh save dir = a fresh battery RAM):

  1. power on, coin, the title: CHALLENGERS -> the ladder screen (fresh: the 2 starters in colour, 10 silhouettes),
     back to the title; NEW GAME -> the select screen (2 selectable, the others silhouettes; the cursor walk reaches
     only the starters)
  2. a game clear x5 (scenario.py's stage mode: the last stage, its boss at 1 life, killed; then the ending passed with
     START, as a player does): each clear's ladder screen (the new rung revealed: silhouette -> white flash -> colour,
     NEW CHALLENGERS!), then the hand-back to the BIOS (which commits the MVS backup RAM)
  3. after clear 1: a POWER CYCLE (the core writes the .nv and loads it again): the title's CHALLENGERS screen and the
     select screen show 4 fighters (save.rungs = 1 read back from the battery RAM)
  4. after clear 5: the ladder complete (12 / 12, ALL FIGHTERS UNLOCKED), a 6th clear unlocks nothing more
  5. the reset: A+B+C+D held 2 s on the title -> SAVE DATA CLEARED, the MVS hand-back 90 ticks later, power cycle:
     the ladder fresh again
  6. the attract demo plays a ladder fighter whatever the save (unaffected)

    python3 unlock_proof.py [GAME_DIR] [OUT]      (default examples/brawler, /data/tmp/unlock) -> OUT/*.png, OUT/proof.txt"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario, build_tables

GAME = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'examples', 'brawler'))
OUT = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/unlock'
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.png'): os.remove(os.path.join(OUT, f))
G = build_tables.load(os.path.join(GAME, 'game.json')); U = build_tables.unlocks(G); NST = len(G['stages'])
names = [r['name'] for r in G['roster']]
H.OPTIONS.update(scenario.SYSTEMS['mvs-mvs'])
b = H.Brawler(rom=os.path.join(GAME, 'brawler.neo'), game=GAME); b.game = GAME; Y = b.syms
lines, bad = [], 0


def say(t, ok=True):
    global bad
    bad += not ok; lines.append(('OK   ' if ok else 'FAIL ') + t); print(lines[-1], flush=True)


def mode(): return b.r(Y['mode'], 1)
def rungs(): return b.r(Y['save'] + 9, 1)
def shot(tag): p = os.path.join(OUT, tag + '.png'); b.screenshot(p); return p


def wait(cond, what, n=6000, keys=''):
    for _ in range(n):
        if cond(): return
        if keys: b.run(1, keys)
        else: b.core.retro_run(); b.frame += 1           # (no hit log: the RAM is the BIOS's at power-on)
    raise SystemExit(f'never reached {what}')


def to_title():
    """power on (or after a reset) -> a coin -> the title with its menu"""
    for _ in range(500): b.core.retro_run(); b.frame += 1   # (power on: the BIOS's RAM, then the game's)
    wait(lambda: mode() == 2, 'the attract', 3000)
    for _ in range(200): b.core.retro_run(); b.frame += 1
    b.seq('4:o,100:-')
    for _ in range(6):
        if mode() == 2 and not b.r(Y['attract'], 1): break
        b.seq('4:s,60:-')
    wait(lambda: mode() == 2 and not b.r(Y['attract'], 1), 'the title')
    b.run(40)


def title_pick(item):
    """the title's cursor onto item (main.c TI_NEW 0, TI_CONT 1, TI_LAD 2), then A"""
    for k in range(8):
        if b.r(Y['title_item'] + b.r(Y['title_sel'], 1), 1) == item: break
        b.seq('4:D,12:-' if k < 4 else '4:U,12:-')
    assert b.r(Y['title_item'] + b.r(Y['title_sel'], 1), 1) == item, 'title: no such line'
    b.seq('4:a,2:-')


def ladder_view(tag):
    title_pick(2)
    wait(lambda: mode() == 7, 'the ladder screen', 60)
    b.run(40); p = shot(tag)
    b.seq('4:a,30:-')
    say(f'{tag}: the ladder from the title (save.rungs {rungs()}), back to the title: mode {mode()}', mode() == 2)
    return p


def select_view(tag):
    title_pick(0); b.seq('4:s,2:-')
    wait(lambda: mode() == 0 and b.r(Y['sel_phase'], 1) == 0, 'the select screen', 600)
    b.run(60); shot(tag)
    nslot = Y and b.nslot
    sc = [b.r(Y['slot_ch'] + i, 1) for i in range(nslot)]
    seen, c = [], None                                   # the cursor walk: right until it loops
    for _ in range(nslot + 1):
        c = b.r(Y['cursor'], 1)
        if c in seen: break
        seen.append(c); b.run(4, 'R'); b.run(12)
    got = [names[sc[s]] for s in seen]
    want = U['starters'] + U['ladder'][:U['rung_size'] * rungs()]
    say(f'{tag}: {nslot} fighters on the select screen, the cursor reaches {len(got)}: {" ".join(got)}', sorted(got) == sorted(want) and nslot == len(U['all']))
    return got


def clear(k):
    """a game clear: the last stage, its boss at 1 life killed (scenario stage mode), the ending passed with START"""
    r0 = rungs()
    scenario.setup(b, {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': NST - 1, 'wave': len(G['stages'][-1]['waves']),
                                 'wait': 150, 'alone': True, 'foe_hp': 1, 'gap': 36}})
    for _ in range(12):                                   # jabs until the boss (1 life) is down
        if b.r(Y['phase'], 1) != 2 or mode() != 1: break
        b.seq('3:a,25:-')
    wait(lambda: mode() == 4, 'the ending', 4000)
    r1 = rungs()
    for _ in range(4000):                                 # the ending's screens, START every 70 frames
        if mode() == 7: break
        b.run(1, 's' if b.frame % 70 == 0 else '')
    assert mode() == 7, 'no ladder screen after the ending'
    new = b.r(Y['lad_new'], 1)
    say(f'clear {k}: save.rungs {r0} -> {r1} at the game clear, the ladder screen shows rung {new} new', r1 == min(r0 + 1, len(U['rungs'])) and new == (r1 if r1 > r0 else 0))
    for t, at in (('a', 30), ('b', 64), ('c', 70), ('d', 76), ('e', 90), ('f', 200)):
        while b.r(Y['lad_t'], 2) < at: b.run(1)
        shot(f'clear{k}_{t}_t{at}')
    b.run(260 - b.r(Y['lad_t'], 2)); b.seq('4:a,2:-')
    wait(lambda: mode() != 7, 'the hand-back', 600)
    say(f'clear {k}: A after the reveal -> back to the BIOS (mode {mode()})')


b.core.retro_reset(); b.frame = 0
to_title()
say(f'fresh save: save.rungs {rungs()}', rungs() == 0)
ladder_view('ladder_fresh')
got = select_view('select_fresh')
clear(1)
b.power_cycle(); b.frame = 0
to_title()
say(f'power cycle after clear 1: save.rungs {rungs()} read back from the battery RAM (.nv)', rungs() == 1)
ladder_view('ladder_after1')
select_view('select_after1')
for k in range(2, 6): clear(k)
b.power_cycle(); b.frame = 0
to_title()
say(f'power cycle after clear 5: save.rungs {rungs()}', rungs() == len(U['rungs']))
ladder_view('ladder_all')
select_view('select_all')
clear(6)
b.power_cycle(); b.frame = 0
to_title()
for _ in range(130): b.run(1, 'abcd')
b.run(20); shot('title_cleared')
wait(lambda: mode() != 2 or b.r(Y['attract'], 1), 'the MVS hand-back after SAVE DATA CLEARED', 200)
say('A+B+C+D 2 s on the title: SAVE DATA CLEARED, then the hand-back to the BIOS (commits the battery RAM)')
b.run(300); b.power_cycle(); b.frame = 0
to_title()
say(f'power cycle after the reset: save.rungs {rungs()}', rungs() == 0)
ladder_view('ladder_reset')
# the attract demo: a ladder fighter even with nothing unlocked
b.core.retro_reset(); b.frame = 0
wait(lambda: mode() == 1 and b.r(Y['attract'], 1), 'the attract demo', 3000)
for _ in range(60): b.core.retro_run(); b.frame += 1
c = names[b.char_of(0)]
say(f'attract demo with a fresh save plays {c} (the ladder\'s cast, whatever the save)', c in U['all'])
lines.append(f'{bad} failure(s)')
open(os.path.join(OUT, 'proof.txt'), 'w').write('\n'.join(lines) + '\n')
print('ALL OK' if not bad else f'{bad} FAILED')
sys.exit(1 if bad else 0)
