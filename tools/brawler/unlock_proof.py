#!/usr/bin/env python3
"""The unlock ladder (game.json unlocks, main.c "the unlock ladder"; Bruno 2026-10-15, decisions set unlocks), played in
our emulator (harness.py, the arcade system mvs-mvs = SNK's MVS BIOS, a fresh save dir = a fresh battery RAM):

  0. the ladder screen's places (build_tables.ladder_places): every ladder fighter on ONE line (one feet y), in ladder
     order left to right at the fixed pitch (unlocks.screen.pitch), full size; a row wider than the TV scrolls
  1. power on, coin, the title: NEW GAME only (MVS), NO ladder line in its menu (Bruno 2026-10-15: "only show this at
     the end of the game when there is an unlocking") and no CONTINUE STAGE, even after clears (Bruno 2026-10-15: "There
     is no resume: every new game starts from stage 1"); NEW GAME -> the select screen (ONLY the 2 starters drawn, on their places for 2:
     build_tables.select_layers, select.auto: spread with no overlap; the cursor walk reaches only them; the same after each power cycle: 4, 12)
  2. a game clear x5 (scenario.py's stage mode: the last stage, its boss at 1 life, killed; then the ending passed with
     START, as a player does): each clear's ladder screen (the new rung revealed: silhouette -> white flash -> colour,
     NEW CHALLENGERS!), every fighter at full size, the camera panned so the new rung's feet x are on the TV once the
     flash starts, then the hand-back to the BIOS (which commits the MVS backup RAM)
  3. after clear 1: a POWER CYCLE (the core writes the .nv and loads it again): the select screen shows 4 fighters
     (save.rungs = 1 read back from the battery RAM)
  4. after the last rung's clear (3 in the beta: Haohmaru + Hanzo, Kyo + Kim, Haggar alone) the ladder complete, one more clear unlocks nothing: NO ladder screen, the ending hands
     straight back to the BIOS (the title / demo again)
  5. the reset: A+B+C+D held 2 s on the title -> SAVE DATA CLEARED, the MVS hand-back 90 ticks later, power cycle:
     save.rungs 0 again
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
LAYERS = build_tables.select_layers(G, None, os.path.join(GAME, 'build'))                # the select screen's layout per unlocked count
P = build_tables.ladder_places(U, U['screen'])          # the ladder screen: one line, ladder order, evenly spaced
dx = [b2[2] - a[2] for a, b2 in zip(P, P[1:])]
lines_pre = [f'ladder screen places: {len(P)} fighters, feet y {sorted({e[3] for e in P})}, x {P[0][2]}-{P[-1][2]} step {min(dx)}-{max(dx)}, '
             f'order {" ".join(e[0] for e in P)}']
PITCH = dict(build_tables.LADDER_SCREEN, **(U['screen'] or {}))['pitch']
ok_pre = len({e[3] for e in P}) == 1 and [e[0] for e in P] == U['all'] and set(dx) == {PITCH} and 8 <= P[0][2]
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


def title_check(tag):
    """the title: no menu at all (Bruno 2026-10-15: "when you play Final Fight there is no NEW GAME"): PRESS START only;
    a screenshot of it"""
    n = b.r(Y['title_n'], 1) if 'title_n' in Y else 1
    shot('title_' + tag.replace(' ', '_'))
    say(f'{tag}: the title has no menu (menu lines: {n}; START goes to the select)', n <= 1)


def title_pick(item):
    """START from the title (no menu since 2026-10-15): item must be 0, the new game"""
    assert item == 0, 'the title has no menu'
    b.seq('4:a,2:-')


def on_screen(new):
    """the camera (cam_x) at the moment: the new rung's feet x on the TV (x 8-311) -> (ok, cam, their screen x)"""
    cam = b.r(Y['cam_x'], 2); cam -= 0x10000 if cam >= 0x8000 else 0
    sx = [e[2] - cam for e in P if e[1] == new]
    return all(24 <= x <= 296 for x in sx), cam, sx


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
    want = U['starters'] + [f for c in U['rungs'][:rungs()] for f in c]
    say(f'{tag}: {nslot} select slots, the cursor reaches {len(got)}: {" ".join(got)}', sorted(got) == sorted(want) and nslot == len(U['all']))
    act = [b.r(Y['slot_act'] + i, 1) for i in range(nslot)]   # only the unlocked ones drawn (Bruno 2026-10-15: no silhouettes)
    drawn = [names[sc[s]] for s in range(nslot) if act[s] != 0xFF]
    lay = b.r(Y['sel_lay'], 1); n, base, Ln = LAYERS[lay]
    rom = [b.sel_slots()[base + s] for s in range(n)]; od = sorted(Ln, key=lambda m: Ln[m]['slot'])
    exp = [(Ln[m]['x'], Ln[m]['y'], Ln[m]['z'], 1 if Ln[m]['facing'] == 'right' else -1) for m in od]
    E = build_tables.sel_extents(os.path.join(GAME, 'build'), G, od); S = {m: build_tables.sel_spans(E[m], Ln[m]) for m in od}
    ov = sum(build_tables.sel_overlap(S[x], S[y]) for i, x in enumerate(od) for y in od[i + 1:])
    say(f'{tag}: drawn {len(drawn)} ({" ".join(drawn)}), layer {lay}: places {base}-{base + n - 1} (feet x {rom[0][0]}-{rom[-1][0]}; '
        f'= select_layers: {rom == exp}), the drawn poses\' overlap {ov} px (select.auto: 0)',
        drawn == want and n == len(want) and rom == exp and (ov == 0 or not G.get('select', {}).get('auto')))
    return got


def clear(k):
    """a game clear: the last stage, its boss at 1 life killed (scenario stage mode), the ending passed with START; the
    ladder screen only when it unlocked a rung"""
    r0 = rungs()
    scenario.setup(b, {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': NST - 1, 'wave': len(G['stages'][-1]['waves']),
                                 'wait': 150, 'alone': True, 'foe_hp': 1, 'gap': 36}})
    for _ in range(80):                                   # jabs until the boss (1 life) is down (0.10.109: he guards; the guard breaks on its hit limit)
        if b.r(Y['phase'], 1) != 2 or mode() != 1: break
        b.seq('3:a,25:-')
    wait(lambda: mode() == 4, 'the ending', 4000)
    r1 = rungs()
    for _ in range(4000):                                 # the ending's screens, START every 70 frames
        if mode() in (7, 1, 2): break                     # (the ladder; or the title / attract demo after the hand-back)
        b.run(1, 's' if b.frame % 70 == 0 else '')
    if r1 == r0:                                          # nothing unlocked: no ladder screen
        say(f'clear {k}: save.rungs {r0} -> {r1} (all unlocked), NO ladder screen: the hand-back to the BIOS (mode {mode()})', mode() in (1, 2))
        shot(f'clear{k}_after')
        return
    assert mode() == 7, 'no ladder screen after the ending'
    new = b.r(Y['lad_new'], 1)
    say(f'clear {k}: save.rungs {r0} -> {r1} at the game clear, the ladder screen shows rung {new} new', r1 == min(r0 + 1, len(U['rungs'])) and new == (r1 if r1 > r0 else 0))
    for t, at in (('a', 30), ('b', 64), ('c', 70), ('d', 76), ('e', 90), ('f', 200)):
        while b.r(Y['lad_t'], 2) < at: b.run(1)
        p = shot(f'clear{k}_{t}_t{at}')
        if t in ('d', 'f'):
            ok, cam, sx = on_screen(new)
            say(f'clear {k} t{at}: camera x {cam}, rung {new} at screen x {sx}', ok)
    b.run(260 - b.r(Y['lad_t'], 2)); b.seq('4:a,2:-')
    wait(lambda: mode() != 7, 'the hand-back', 600)
    say(f'clear {k}: A after the reveal -> back to the BIOS (mode {mode()})')


say(lines_pre[0], ok_pre)
b.core.retro_reset(); b.frame = 0
to_title()
say(f'fresh save: save.rungs {rungs()}', rungs() == 0)
title_check('fresh')
got = select_view('select_fresh')
clear(1)
b.power_cycle(); b.frame = 0
to_title()
say(f'power cycle after clear 1: save.rungs {rungs()} read back from the battery RAM (.nv)', rungs() == 1)
title_check('after clear 1')
select_view('select_after1')
NR = len(U['rungs'])
for k in range(2, NR + 1): clear(k)
b.power_cycle(); b.frame = 0
to_title()
say(f'power cycle after clear {NR} (the last rung): save.rungs {rungs()}', rungs() == NR)
title_check(f'after clear {NR}')
select_view('select_all')
clear(NR + 1)
b.power_cycle(); b.frame = 0
to_title()
for _ in range(130): b.run(1, 'abcd')
b.run(20); shot('title_cleared')
wait(lambda: mode() != 2 or b.r(Y['attract'], 1), 'the MVS hand-back after SAVE DATA CLEARED', 200)
say('A+B+C+D 2 s on the title: SAVE DATA CLEARED, then the hand-back to the BIOS (commits the battery RAM)')
b.run(300); b.power_cycle(); b.frame = 0
to_title()
say(f'power cycle after the reset: save.rungs {rungs()}', rungs() == 0)
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
