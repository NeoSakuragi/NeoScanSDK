#!/usr/bin/env python3
"""AOF2's own screens around a bonus game in the brawler vs Art of Fighting 2 (notes 20261014-085447-5d29 "the classic
screen from Art of Fighting 2 showing the message 'Bonus Game!'", 20261014-085507-5d29 "the shouting in Japanese with
the kanji written on the screen", Bruno 2026-10-14 "AOF2's ORIGINAL bonus select screen"; main.c "AOF2's own screens",
tools/brawler/make_bonus.py screens). Both games in our emulator (emu/neogeo_sdl --capture: the same picture, 304 x 224):
AOF2 from power-on as tools/aof/bonus_rip.py screens (no pick: the clock picks slot 0; R, R, A: slot 2), the brawler
from scenario.py's mode "bonus" (harness state, then the capture: no input; R then A).

    bonus_screens_proof.py GAME_DIR OUT
      -> OUT/sbs.png (AOF2 | brawler, one row per moment), OUT/aof2_*.wav + brawler_*.wav (the runs' sound), OUT/report.json:
         per moment the brawler frame nearest AOF2's (mean |difference| over the picture) and its share of identical pixels
         (the middle picture is greyed on purpose: slot 1 has no game); the sound commands of both runs; the loudness per
         frame of the announcer's and the card's sounds (AOF2 vs brawler)"""
import json, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'aof'))
import harness as H, scenario
from bonus_rip import BOOT, EMU, ROM

FPS = 59.1856
GREY_X = (112, 200)                                      # the greyed middle picture (screen x): not compared
MOMENTS = [                                              # (name, AOF2 run, AOF2 frame, brawler run, brawler frames searched)
    ('BONUS GAME zooming in', 0, 2970, 0, range(0, 30)),
    ('BONUS GAME', 0, 3040, 0, range(30, 110)),
    ('SELECT: the general message', 0, 3100, 0, range(122, 200)),
    ('SELECT: slot 0\'s message', 0, 3300, 0, range(320, 420)),
    ('SELECT: the cursor frame (slot 0)', 2, 3191, 0, range(130, 300)),
    ('SELECT: cursor on slot 2 (1 skipped)', 2, 3301, 2, range(310, 360)),
    ('picked: the frame steady', 2, 3380, 2, range(425, 480)),
    ('title card: Spirit Training', 0, 3800, 0, range(800, 900)),
    ('title card: Super Death Blow', 2, 3500, 2, range(500, 640)),
]


def aof2_run(out, c):
    d = f'{out}/aof2_{c}'; os.makedirs(d, exist_ok=True)
    seq = BOOT + '1194:-,' + ('4:R,36:-,' * c + f'{160 - 40 * c}:-,4:a,1000:-' if c else '1500:-')
    fr = sorted({f for _, r, f, _, _ in MOMENTS if r == c})
    env = dict(os.environ, SEQ=seq, POKE=';'.join(f'{f}:108428=00,108429=04' for f in range(1721, 4100)), SNAPS=','.join(map(str, fr)),
               SNAPDIR=d, SNDLOG=f'{out}/aof2_{c}.snd', WAV=f'{out}/aof2_{c}.wav')
    subprocess.run(['timeout', '900', EMU, ROM, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def brawler_run(game, out, c, state):
    d = f'{out}/brawler_{c}'; os.makedirs(d, exist_ok=True)
    seq = '1000:-' if not c else '330:-,4:R,90:-,4:a,600:-'
    env = dict(os.environ, LOAD=state, SEQ=seq, SNAPS=','.join(map(str, range(0, 1000))), SNAPDIR=d,
               SNDLOG=f'{out}/brawler_{c}.snd', WAV=f'{out}/brawler_{c}.wav')
    subprocess.run(['timeout', '900', EMU, os.path.join(game, 'brawler.neo'), '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def img(p): return np.array(Image.open(p).convert('RGB')).astype(int)


def cmds(p): return [l.split()[:2] for l in open(p)] if os.path.exists(p) else []


def loud(p, f0, n):
    w = wave.open(p); r = w.getframerate(); a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2).astype(float).mean(1)
    return [int(np.sqrt(np.mean(a[int((f0 + i) * r / FPS):int((f0 + i + 1) * r / FPS)] ** 2))) for i in range(n)]


def main():
    if len(sys.argv) != 3: sys.exit(__doc__)
    game, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2]); os.makedirs(out, exist_ok=True)
    for c in (0, 2): aof2_run(out, c)
    b = H.Brawler(game=game); b.game = game
    scenario.setup(b, {'setup': {'mode': 'bonus', 'fighter': 'terry', 'game': 'pick', 'unlocked': False, 'after': 1}})
    st = f'{out}/brawler_bonus.state'; open(st, 'wb').write(b.save())
    for c in (0, 2): brawler_run(game, out, c, st)
    rep = {'moments': [], 'commands': {}}
    W, Hh = 304, 224; S = Image.new('RGB', (W * 2 + 12, len(MOMENTS) * (Hh + 16)), 'white'); D = ImageDraw.Draw(S)
    mask = np.ones((Hh, W), bool); mask[:, GREY_X[0]:GREY_X[1]] = False
    for i, (name, ra, fa, rb, fb) in enumerate(MOMENTS):
        a = img(f'{out}/aof2_{ra}/snap_{fa}.ppm')
        best = min(((np.abs(a - img(p)).mean(axis=2)[mask].mean(), f, p) for f in fb
                    for p in [f'{out}/brawler_{rb}/snap_{f}.ppm'] if os.path.exists(p)), default=None)
        d, f, p = best
        same = float((np.abs(a - img(p)).sum(axis=2) == 0)[mask].mean())
        rep['moments'].append({'moment': name, 'aof2_frame': fa, 'brawler_frame': f, 'mean_diff': round(float(d), 2), 'identical_px': round(same, 4)})
        print(f'{name}: AOF2 {fa} ~ brawler {f}: {same * 100:.1f} % identical pixels (the greyed slot 1 not counted)')
        y = i * (Hh + 16)
        D.text((2, y + 2), f'AOF2 frame {fa}: {name}', fill='black'); D.text((W + 14, y + 2), f'brawler frame {f}: {same * 100:.1f} % identical', fill='black')
        S.paste(Image.open(f'{out}/aof2_{ra}/snap_{fa}.ppm').convert('RGB'), (0, y + 16)); S.paste(Image.open(p).convert('RGB'), (W + 12, y + 16))
    S.save(f'{out}/sbs.png')
    for k in ('aof2_0', 'aof2_2', 'brawler_0', 'brawler_2'): rep['commands'][k] = [' '.join(x) for x in cmds(f'{out}/{k}.snd') if int(x[0]) > (2900 if 'aof2' in k else -1)]
    # the announcer + jingle (AOF2 $1C $AE + $33 from frame 2971) and the card's voice + gong ($1C $CD + $1A $20 from 3746)
    fb = lambda k, c: next(int(x[0]) for x in cmds(f'{out}/brawler_0.snd') if x[1] == c)
    rep['loudness'] = {'intro': {'aof2': loud(f'{out}/aof2_0.wav', 2970, 60), 'brawler': loud(f'{out}/brawler_0.wav', fb(0, 'EC') - 1, 60)},
                       'card': {'aof2': loud(f'{out}/aof2_0.wav', 3745, 120), 'brawler': loud(f'{out}/brawler_0.wav', fb(0, 'ED') - 1, 120)}}
    for k, v in rep['loudness'].items():
        print(f'{k}: loudness per frame, correlation AOF2 vs brawler {np.corrcoef(v["aof2"], v["brawler"])[0, 1]:.3f}')
    json.dump(rep, open(f'{out}/report.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
