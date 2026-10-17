#!/usr/bin/env python3
"""Omega Rugal (2026-10-17: KOF98 Rugal's EX version as a fighter of his own, tools/kof96/export96.py FORMS) in the
brawler, our emulator (harness, the repo's Geolith core; never MAME), on the normal build (make):

    python3 omega_proof.py boss [OUT] [SECONDS]   the boss fight check: the lab's enemy test (mailbox req 3, main.c
                                                  lab_enemy: the enemy definition OMEGA_RUGAL with its boss AI, P1 =
                                                  Terry, whose life the lab refills) for SECONDS (default 40): Terry
                                                  presses A / C / D in turn at close range; per frame Omega's state,
                                                  special (pool index -> input), life, Terry's life; pass = Omega walks,
                                                  attacks, plays specials and hits Terry, Terry's hits take his life;
                                                  OUT/boss.png (every 2 s), OUT/boss.json

The specials against KOF98 (each one, KOF98 left / brawler right): romspecials_check.py GAME OUT omega_rugal:D ...
(a fighter the select screen does not show plays in the Chain Lab training: romspecials_check.lab_pick, dummy Terry).
Default OUT /data/tmp/omega/proof."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Brawler, GAME
from PIL import Image, ImageDraw

OUT = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/omega/proof'
G = json.load(open(os.path.join(GAME, 'game.json')))
NAMES = [r['name'] for r in G['roster']]
ENEMIES = [e['name'] for e in G['enemies']]
LAB_REQ, LAB_FIGHTER, LAB_DUMMY_, LAB_ACTIVE = 4, 5, 6, 8      # fighter.h lab_t offsets (scenario.py)
BOSS = 2                                                       # main.c LAB_DUMMY: the enemy test's fighter slot

def lab(b, req, fighter, dummy):
    a = b.syms['lab']
    b.core.retro_reset(); b.frame = 0
    for _ in range(600): b.core.retro_run()
    b.frame = 600
    for i, v in enumerate(b'LAB1'): b.w(a + i, 1, v)
    b.w(a + LAB_FIGHTER, 1, fighter); b.w(a + LAB_DUMMY_, 1, dummy); b.w(a + LAB_REQ, 1, req)
    for _ in range(3000):
        b.core.retro_run(); b.frame += 1
        if b.r(a + LAB_ACTIVE, 1) == (2 if req == 3 else 1): return
    raise RuntimeError('the game never took the lab request')

def pool_inputs():
    """Omega's pool as the build has it (build/chainlab.json: the specials his slots / fury / air table index)"""
    f = next(f for f in json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))['fighters'] if f['name'] == 'omega_rugal')
    return [p['input'] for p in f['pool']]

def boss(seconds=40):
    os.makedirs(OUT, exist_ok=True)
    b = Brawler()
    lab(b, 3, NAMES.index('terry'), ENEMIES.index('OMEGA_RUGAL'))
    om = NAMES.index('omega_rugal')
    assert b.char_of(BOSS) == om, f'slot {BOSS} is {NAMES[b.char_of(BOSS)]}, not Omega Rugal'
    pool = pool_inputs()
    rows, shots, hp0 = [], [], b.fget(BOSS, 'hp')
    keys = ['a', '', 'a', '', 'c', '', '', 'a', 'a', '', 'Rc', '', 'd', '']
    for f in range(seconds * 60):
        # Terry walks to Omega and attacks in turn (8 frames a press, a pause between)
        dx = b.fget(BOSS, 'x') - b.fget(0, 'x')
        k = keys[(f // 8) % len(keys)] if abs(dx) < 90 else ('R' if dx > 0 else 'L')
        if f % 120 == 0: b.fset(0, 'fgauge', 0)                 # (the fury rarely: Omega's life lasts the run)
        if f % 60 == 0 and len(shots) < 40:
            p = os.path.join(OUT, f'boss_{f:05d}.png'); b.pad = [set(k), set()]; b.screenshot(p); shots.append((f, p))
        else: b.run(1, p1=k)
        st = b.states[b.fget(BOSS, 'state')]
        sid = b.fget(BOSS, 'spec_ix') if 'spec_ix' in b.layout else None
        rows.append({'f': f, 'st': st, 'spec': pool[sid] if st == 'SPECIAL' and sid is not None and sid < len(pool) else None,
                     'hp': b.fget(BOSS, 'hp'), 'p1hp': b.fget(0, 'hp'), 'p1st': b.states[b.fget(0, 'state')],
                     'x': round(b.fget(BOSS, 'x'), 1), 'p1x': round(b.fget(0, 'x'), 1)})
    states = {}
    for r in rows: states[r['st']] = states.get(r['st'], 0) + 1
    specs = sorted({r['spec'] for r in rows if r['spec']})
    p1_hits = sum(1 for i in range(1, len(rows)) if rows[i]['p1hp'] < rows[i - 1]['p1hp'])
    boss_hits = sum(1 for i in range(1, len(rows)) if rows[i]['hp'] < rows[i - 1]['hp'])
    walked = states.get('WALK', 0) + states.get('RUN', 0)
    attacked = sum(v for k, v in states.items() if k.startswith('ATTACK') or k in ('SPECIAL', 'FURY', 'THROW', 'GRAB'))
    res = {'frames': len(rows), 'boss_life_start': hp0, 'boss_life_end': rows[-1]['hp'], 'boss_states': states,
           'boss_specials': specs, 'hits_on_terry': p1_hits, 'hits_on_boss': boss_hits,
           'pass': bool(walked and attacked and p1_hits and boss_hits)}
    json.dump({'summary': res, 'rows': rows}, open(os.path.join(OUT, 'boss.json'), 'w'))
    W, H = 320, 224
    cols = 5; n = len(shots); im = Image.new('RGB', (cols * W, ((n + cols - 1) // cols) * (H + 14)), 'white'); d = ImageDraw.Draw(im)
    for j, (f, p) in enumerate(shots):
        x, y = (j % cols) * W, (j // cols) * (H + 14)
        im.paste(Image.open(p).convert('RGB').resize((W, H)), (x, y + 14)); d.text((x + 2, y), f'{f / 60:.0f} s  {rows[min(f, len(rows) - 1)]["st"]}', fill='black')
    im.save(os.path.join(OUT, 'boss.png'))
    for f, p in shots: os.remove(p)
    print(json.dumps(res, indent=1))
    return res['pass']

if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'boss'
    if what == 'boss': ok = boss(int(sys.argv[3]) if len(sys.argv) > 3 else 40)
    else: raise SystemExit(__doc__)
    print('ALL OK' if ok else 'FAIL'); sys.exit(0 if ok else 1)
