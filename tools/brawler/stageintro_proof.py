#!/usr/bin/env python3
"""The stage intro (voice note 20261014-192343-5d29; game.json stage_intro, main.c "the stage intro"), in our emulator
(harness.py): the real path (coin, START, the select screen, A) for 1P and 2P, stage 1, then stage 1 cleared (phase
poked to PH_END, its enemies taken off) -> the bonus pick + game (left to time out) -> stage 2's intro. Per tick: the
intro phase (in_ph), every fighter's state, the players' x, the camera. Checks: during the fade nobody on screen (every
fighter OFF) and the stage palettes rise from black; the players appear outside the screen edge, walk in with the input
locked (P1 holds left + A all through the walk: the walk goes on), stop on their marks; no enemy before the first
wave's spawn, which comes wave_delay ticks after the arrival. Contact sheet per start.

    python3 stageintro_proof.py [ROM] [OUT]      (default examples/brawler/brawler.neo, /data/tmp/stageintro) -> OUT/proof.json, OUT/*.png"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H
from PIL import Image, ImageDraw

ROM = sys.argv[1] if len(sys.argv) > 1 else os.path.join(H.GAME, 'brawler.neo')
OUT = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/stageintro'
os.makedirs(OUT, exist_ok=True)
G = json.load(open(os.path.join(H.GAME, 'game.json')))
SHOTS = [2, 12, 24, 40, 100, 150, 175, 200]           # ticks from the stage's start (+ the arrival, the first wave)


def u8(b, n): return b.r(b.syms[n], 1)
def lum(p): import numpy as np; return float(np.asarray(Image.open(p).convert('L'), dtype=float).mean())


def watch(b, tag, stage, hold_keys='La'):
    """from the tick the intro starts: the timeline, the shots, the checks"""
    OFF = b.states.index('OFF')
    while u8(b, 'in_ph') != 1: b.run(1)
    t0 = b.frame; tl = []; shots = []; arrive = wave = None
    two = u8(b, 'pl_on') and b.r(b.syms['pl_on'] + 1, 1)
    while True:
        t = b.frame - t0; ph = u8(b, 'in_ph')
        st = [b.fget(i, 'state') for i in range(8)]
        tl.append({'t': t, 'ph': ph, 'on': [i for i in range(8) if st[i] != OFF], 'x': [round(b.fget(i, 'x'), 1) for i in range(2)],
                   'cam': b.r(b.syms['cam_x'], 2)})
        if ph == 3 and arrive is None: arrive = t
        if ph == 0 and wave is None: wave = t
        want = t in SHOTS or (arrive is not None and t == arrive) or (wave is not None and t == wave + 30)
        if want:
            p = os.path.join(OUT, f'{tag}_{t:03d}.png'); b.screenshot(p); shots.append((t, ph, p))
        else: b.run(1, hold_keys if ph == 2 else '')        # (the walk: P1 holds left + A, the script's intents win)
        if wave is not None and t >= wave + 30: break
        if t > 1500: break
    fade = [e for e in tl if e['ph'] == 1]
    walk = [e for e in tl if e['ph'] == 2]
    ck = {'nobody_in_fade': all(not e['on'] for e in fade),
          'fade_rises': lum(shots[0][2]) < 0.3 * lum(shots[3][2]),
          'start_outside': bool(walk) and all(walk[0]['x'][p] - walk[0]['cam'] < 0 for p in range(1 + bool(two))),
          'walk_forward': bool(walk) and all(walk[k + 1]['x'][0] >= walk[k]['x'][0] for k in range(len(walk) - 1)),
          'no_enemy_before_wave': all(not [i for i in e['on'] if i >= 2] for e in tl if e['ph'] != 0),
          'enemies_after_wave': bool([i for i in tl[-1]['on'] if i >= 2]),
          'arrived_on_marks': arrive is not None and all(abs(tl[arrive]['x'][p] - tl[arrive]['cam'] - G['stage_intro']['marks'][p][0]) <= 1 for p in range(1 + bool(two))),
          'two_players': bool(two)}
    return {'tag': tag, 'stage': stage, 'walk_start': walk[0]['t'] if walk else None, 'arrive': arrive, 'wave': wave, 'checks': ck,
            'ok': all(v for k, v in ck.items() if k != 'two_players'), 'shots': shots}


def clear_stage(b):
    """stage 1 cleared at once: its enemies off, phase PH_END; then on through the clear, the bonus, to stage 2"""
    OFF = b.states.index('OFF')
    for i in range(2, 8): b.fset(i, 'state', OFF)
    b.w(b.syms['tq_n'], 1, 0); b.w(b.syms['phase'], 1, 3)
    for _ in range(9000):
        b.run(1, 'a' if b.frame % 40 < 2 else '')         # (A: through the screens; the gauge game's one press)
        if u8(b, 'in_ph') == 1 and u8(b, 'camp') == 1: return
    raise SystemExit('stage 2 never started')


def sheet(res, path):
    rows = [r for r in res]
    W, Hh = 160, 112; cols = max(len(r['shots']) for r in rows)
    im = Image.new('RGB', (cols * W, len(rows) * (Hh + 14)), 'white'); d = ImageDraw.Draw(im)
    for y, r in enumerate(rows):
        for x, (t, ph, p) in enumerate(r['shots']):
            s = Image.open(p).resize((W, Hh)); im.paste(s, (x * W, y * (Hh + 14) + 14))
            d.text((x * W + 2, y * (Hh + 14)), f"{r['tag']} t{t} {['play', 'fade', 'walk', 'wait'][ph]}", fill='black')
    im.save(path)


def main():
    res = []
    b = H.Brawler(rom=ROM)
    for two in (0, 1):
        b.core.retro_reset()
        b.seq('600:-,4:o,30:-,4:o,100:-,4:s,100:-' if two else '600:-,4:o,100:-,4:s,100:-')
        if two: b.run(4, '', 's'); b.run(60)
        b.run(4, 'a', 'a' if two else '')
        tag = '2p' if two else '1p'
        res.append(watch(b, tag + '_stage1', 1))
        clear_stage(b)
        res.append(watch(b, tag + '_stage2', 2))
    sheet(res, os.path.join(OUT, 'sheet.png'))
    for r in res: print(r['tag'], 'OK' if r['ok'] else 'FAIL', 'walk', r['walk_start'], 'arrive', r['arrive'], 'wave', r['wave'], r['checks'])
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print(os.path.join(OUT, 'sheet.png'))
    sys.exit(0 if all(r['ok'] for r in res) else 1)


if __name__ == '__main__':
    main()
