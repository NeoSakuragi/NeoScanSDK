#!/usr/bin/env python3
"""The referee's speech in the brawler (note 20261015-221208-e03d; main.c "the referee", game.json "referee" + bonus
games[].won_by), in our emulator's core (harness.py) vs SS2's numbers (tools/samsho2/referee_ss2.py check):

    referee_proof.py GAME_DIR OUT [FIGHTER [right]]   (right: the last post on his left, the referee from the right)
      the posts game from its start (scenario mode "bonus"): nothing written at the start but the TIME / POSTS line;
      won with A, A, A (bonus_proof.play_posts: 5 posts of 12 hits in 30 s); then the speech phase by phase: the walk
      (1 px a tick), one tick standing, the jump (rising behind the player, falling in front: its ticks = SS2's 55 at
      the same speed and gravity), the landing (SS2's 8 ticks), the window opening (7 ticks), a letter every 2 ticks,
      held game.json referee.hold after the last, closing (14 ticks), then stage 2 with the fury unlocked
    screenshots OUT/*.png + OUT/sheet.png; one OK / FAIL line per check, exit 1 on any FAIL"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from bonus_proof import Proof, BN
from PIL import Image, ImageDraw

PH = ['OFF', 'WALK', 'STAND', 'RISE', 'JUMP', 'LAND', 'OPEN', 'TYPE', 'HOLD', 'CLOSE']
SS2 = {'JUMP': 55, 'LAND': 8, 'OPEN': 7, 'CLOSE': 14}   # SS2's ticks (referee_ss2.py check: frames 1040-1094 the jump
                                                       # after its first, 1095-1102 the landing, 1104-1110, 1274-1287)


def main(game, out, fighter='terry', side='auto'):
    P = Proof(game, out); b = P.b
    G = json.load(open(os.path.join(game, 'game.json'))); posts = next(x for x in G['bonus']['games'] if x['kind'] == 'break')
    ref = G['referee']; text = posts['won_text']
    P.setup(fighter=fighter, game=posts['id']); b.run(40)
    P.shot('start', 'the posts game at its start: TIME and POSTS only')
    run0 = b.run                                        # (the clock kept off its end: the speech is the point here;
    def run(*a, **k):                                   #  the ticks the bot took are printed against the game's own)
        if P.r('bonus_on') == BN['play'] and P.r('bn_clock', 2) < 600: b.w(b.syms['bn_clock'], 2, 99 * 60)
        if side == 'right' and P.r('bonus_on') == BN['play'] and P.r('bn_left') == 1 and P.r('bn_post') == 0:
            b.place(0, x=250)                           # (the last post then drops on his left: he ends on the left
                                                        #  half, the referee comes from the right: SS2's own case)
        return run0(*a, **k)
    b.run = run
    lock0, t, left = P.play_posts(fighter, 'a', limit=99 * 60)
    P.check(left == 0 and P.r('bonus_on') == BN['end'], f'{fighter} broke {posts["count"] - left} / {posts["count"]} posts ({posts["hp"]} hits each, '
            f'A, A, A) in {t} ticks (the game\'s clock: {posts["seconds"] * 60})')
    rf = b.syms['rf']
    ph = lambda: PH[b.r(rf, 1)]
    seen, cur, n, xs, shots = [], None, 0, [], {'WALK': 30, 'RISE': 0, 'JUMP': 20, 'LAND': 0, 'OPEN': 3, 'TYPE': 30, 'HOLD': 40, 'CLOSE': 6}
    for k in range(3000):
        p = ph()
        if p != cur:
            if cur: seen.append((cur, n))
            cur, n = p, 0
        if p == 'OFF' and seen: break
        if shots.get(p) == n: P.shot(f'ref_{len(seen):02d}_{p.lower()}', f'{p} +{n}')   # (a shot plays the frame)
        else: b.run(1)
        n += 1
    print('phases (ticks):', seen)
    d = dict(seen)
    P.check(d.get('WALK') == ref['from'] + ref['mark'], f"the walk in: {d.get('WALK')} ticks ({ref['from']} px outside to {ref['mark']} px inside at 1 px a tick, SS2's vx 256)")
    P.check(d.get('STAND') == 1 and d.get('RISE') == 1, 'one tick standing, then the jump (SS2)')
    for k, v in SS2.items():
        P.check(d.get(k) == v, f'{k}: {d.get(k)} ticks (SS2: {v})')
    letters = sum(len(l) for l in text)
    P.check(d.get('TYPE') == 2 * letters, f"TYPE: {d.get('TYPE')} ticks for {letters} letters (a letter every 2 ticks from the window open, SS2's MESSDISP)")
    P.check(d.get('HOLD') == ref['hold'], f"held {d.get('HOLD')} ticks after the last letter (referee.hold {ref['hold']})")
    P.check(P.r('fury_lock') == 0, 'the fury unlocked')
    P.until(lambda: P.r('bonus_on') == BN['off'] and P.r('mode') == 1, 120)
    P.check(P.r('bonus_on') == BN['off'] and P.r('mode') == 1, 'then the next stage')
    # contact sheet
    W, H = 320, 224; cols = 4; rws = (len(P.shots) + cols - 1) // cols
    sh = Image.new('RGB', (W * cols, (H + 14) * rws), 'white'); dr = ImageDraw.Draw(sh)
    for i, (p, lab) in enumerate(P.shots):
        im = Image.open(p).convert('RGB').resize((W, H)); x, y = (i % cols) * W, (i // cols) * (H + 14)
        sh.paste(im, (x, y)); dr.text((x + 2, y + H), lab, fill='black')
    sh.save(os.path.join(out, 'sheet.png'))
    print('FAILS', P.fails); return P.fails


if __name__ == '__main__':
    if len(sys.argv) < 3: sys.exit(__doc__)
    sys.exit(1 if main(*sys.argv[1:5]) else 0)
