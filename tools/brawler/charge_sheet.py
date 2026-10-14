#!/usr/bin/env python3
"""The Ki training's concentration per fighter (note 20261014-133606-5d29, Bruno: "in the original game there is a
charging / concentrating / gathering-energy animation played just before the attack; find the equivalent in our game"):
every selectable fighter + Haggar in the Ki training (scenario.py mode "bonus"), A pressed, his BA_CHARGE pose shot
at several ticks of the concentration. Which source each one plays: KOF96 the power charge
(states 60 + 61), KOF98 / 99 the power-up (state 77; export96), SS2 the rage (anim 140, export_ss2), the others their win pose (export_bm SOURCES).

    python3 charge_sheet.py [GAME_DIR] [OUT]     (default examples/brawler, /data/tmp/charge_sheet) -> OUT/sheet.png, OUT/charge.json"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario
from PIL import Image, ImageDraw

GAME = sys.argv[1] if len(sys.argv) > 1 else H.GAME
OUT = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/charge_sheet'
AT = [4, 14, 30, 50, 70]                          # ticks into the concentration (after charge.stand)
W, Hh = 112, 150


def main():
    os.makedirs(OUT, exist_ok=True)
    g = json.load(open(os.path.join(GAME, 'game.json')))
    ki = next(x for x in g['bonus']['games'] if x['kind'] == 'gauge'); cg = ki['charge']
    names = [r['name'] for r in g['roster'] if r.get('selectable', True) and r['name'] != 'billy_super']
    src = {}
    for n in names:
        game = next(r['bank'] for r in g['roster'] if r['name'] == n).split(':')[0]
        src[n] = 'power charge (60 + 61)' if game == 'kof96' else 'power-up (77)' if game.startswith('kof') else 'rage (140)' if game == 'samsho2' else 'flash pose / win (fallback)'
    ba = re.search(r'enum \{ (BA_IDLE[^}]*)\}', open(os.path.join(GAME, 'build', 'bm_chars.h')).read()).group(1).replace(' ', '').split(',')
    b = H.Brawler(game=GAME); b.game = GAME
    rows, res = [], {}
    for n in names:
        scenario.setup(b, {'setup': {'mode': 'bonus', 'fighter': n, 'game': ki['id'], 'unlocked': True, 'after': 1}})
        b.run(40); b.run(1, p1='a'); b.run(cg['stand'])
        shots, anims, t = [], [], 0
        for a in AT:
            b.run(a - t - 1); t = a
            p = f'{OUT}/{n}_{a}.png'; b.screenshot(p)
            sx = int(b.fget(0, 'x')) - b.r(b.syms['cam_x'], 2); shots.append((p, sx)); anims.append(ba[b.fget(0, 'anim')])
        res[n] = {'source': src[n], 'anims': anims, 'ok': all(a == 'BA_CHARGE' for a in anims)}
        rows.append((n, shots))
        print(n, src[n], 'OK' if res[n]['ok'] else anims)
    im = Image.new('RGB', (W * (len(AT) + 1), (Hh + 2) * len(rows)), 'white'); d = ImageDraw.Draw(im)
    for y, (n, shots) in enumerate(rows):
        d.text((4, y * (Hh + 2) + 4), n, fill='black'); d.text((4, y * (Hh + 2) + 18), src[n], fill='black')
        for x, (p, sx) in enumerate(shots):
            c = Image.open(p).crop((sx - W // 2, 224 - Hh, sx + W // 2, 224)); im.paste(c, ((x + 1) * W, y * (Hh + 2)))
            d.text(((x + 1) * W + 2, y * (Hh + 2) + 2), f'+{AT[x]}', fill='white')
    im.save(f'{OUT}/sheet.png')
    json.dump(res, open(f'{OUT}/charge.json', 'w'), indent=1)
    print('ALL OK' if all(r['ok'] for r in res.values()) else 'FAIL', f'{OUT}/sheet.png')


if __name__ == '__main__': main()
