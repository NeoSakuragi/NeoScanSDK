#!/usr/bin/env python3
"""The referee's speech in the brawler (note 20261015-221208-e03d; main.c "the referee", game.json "referee" + bonus
games[].won_by), in our emulator's core (harness.py) vs SS2's numbers (tools/samsho2/referee_ss2.py check):

    referee_proof.py GAME_DIR OUT [FIGHTER [right|auto [d]]]   (right: the last post on his left, the referee from the
      right; d: the D quirk, round 2 of the note: D while his message is held)
      the posts game from its start (scenario mode "bonus"): nothing written at the start but the TIME / POSTS line;
      won with A, A, A (bonus_proof.play_posts: count posts of hp hits in 30 s; each post's picture = AOF2's cracked
      one games[].damage_at says for the hits it took); then the speech phase by phase: the walk
      (1 px a tick), one tick standing, the jump (rising behind the player, falling in front: its ticks = SS2's 55 at
      the same speed and gravity), the landing (SS2's 8 ticks), the window opening (7 ticks), a letter every 2 ticks,
      held game.json referee.hold after the last, closing (14 ticks), then stage 2 with the fury unlocked.
      d: D pressed in the hold: the window closes, the fighter runs at him and fires his fury, it strikes him: his
      flight (FLY), lying referee.down_ticks (DOWN), the get-up (GETUP), the window again with referee.hit_text typed
    screenshots OUT/*.png + OUT/sheet.png; one OK / FAIL line per check, exit 1 on any FAIL"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from bonus_proof import Proof, BN
from PIL import Image, ImageDraw

PH = ['OFF', 'WALK', 'STAND', 'RISE', 'JUMP', 'LAND', 'OPEN', 'TYPE', 'HOLD', 'CLOSE', 'WAIT', 'FLY', 'DOWN', 'GETUP']
SS2 = {'JUMP': 55, 'LAND': 8, 'OPEN': 7, 'CLOSE': 14}   # SS2's ticks (referee_ss2.py check: frames 1040-1094 the jump
                                                       # after its first, 1095-1102 the landing, 1104-1110, 1274-1287)


def main(game, out, fighter='terry', side='auto', quirk=''):
    P = Proof(game, out); b = P.b
    G = json.load(open(os.path.join(game, 'game.json'))); posts = next(x for x in G['bonus']['games'] if x['kind'] == 'break')
    ref = G['referee']; text = posts['won_text']
    P.setup(fighter=fighter, game=posts['id']); b.run(40)
    P.shot('start', 'the posts game at its start: TIME and POSTS only')
    run0 = b.run                                        # (the clock kept off its end: the speech is the point here;
    imgs = {}                                           #  the ticks the bot took are printed against the game's own)
    def run(*a, **k):                                   # (and every post's picture against the hits it took)
        if P.r('bonus_on') == BN['play'] and P.r('bn_post') == 2 and not P.r('bn_thud') == 16:
            imgs.setdefault(posts['hp'] - P.r('bn_hp'), set()).add(P.r('bn_img'))
        if P.r('bonus_on') == BN['play'] and P.r('bn_clock', 2) < 600: b.w(b.syms['bn_clock'], 2, 99 * 60)
        if side == 'right' and P.r('bonus_on') == BN['play'] and P.r('bn_left') == 1 and P.r('bn_post') == 0:
            b.place(0, x=250)                           # (the last post then drops on his left: he ends on the left
                                                        #  half, the referee comes from the right: SS2's own case)
        return run0(*a, **k)
    b.run = run
    lock0, t, left = P.play_posts(fighter, 'a', limit=99 * 60)
    P.check(left == 0 and P.r('bonus_on') == BN['end'], f'{fighter} broke {posts["count"] - left} / {posts["count"]} posts ({posts["hp"]} hits each, '
            f'A, A, A) in {t} ticks (the game\'s clock: {posts["seconds"] * 60})')
    da = posts.get('damage_at', [])
    want = {k: sum(1 for v in da if k >= v) for k in imgs}
    P.check(all(imgs[k] == {want[k]} for k in imgs) and len(set(want.values())) == len(da) + 1,
            f"the post's picture by hits taken (damage_at {da}): " + ', '.join(f'{k}: {sorted(imgs[k])}' for k in sorted(imgs)))
    rf = b.syms['rf']
    ph = lambda: PH[b.r(rf, 1)]
    seen, cur, n, xs, shots = [], None, 0, [], {'WALK': 30, 'RISE': 0, 'JUMP': 20, 'LAND': 0, 'OPEN': 3, 'TYPE': 30, 'HOLD': 40, 'CLOSE': 6}
    if quirk: shots.update({'WAIT': 10, 'FLY': 8, 'DOWN': 20, 'GETUP': 6})
    keys, pressed = '', False
    for k in range(3000):
        p = ph()
        if p != cur:
            if cur: seen.append((cur, n))
            cur, n = p, 0
        if p == 'OFF' and seen: break
        keys = 'd' if quirk and p == 'HOLD' and n == 30 and not pressed else ''   # (D a while into his held message)
        pressed |= keys == 'd'
        if shots.get(p) == n and not keys and len([s for s, _ in seen if s == p]) < 2 - (p == 'CLOSE'):
            P.shot(f'ref_{len(seen):02d}_{p.lower()}', f'{p} +{n}')   # (a shot plays the frame)
        else: b.run(1, p1=keys)
        n += 1
    print('phases (ticks):', seen)
    if quirk:
        names = [s for s, _ in seen]
        P.check(names[:9] == ['WALK', 'STAND', 'RISE', 'JUMP', 'LAND', 'OPEN', 'TYPE', 'HOLD', 'CLOSE'] and seen[7][1] == 32,
                'the speech, D pressed 30 ticks into the held message (read the next tick): the window closes')
        i = names.index('CLOSE')
        P.check(names[i + 1:i + 5] == ['WAIT', 'FLY', 'DOWN', 'GETUP'], f"then the fury runs at him and strikes him: {names[i + 1:i + 5]} (WAIT {dict(seen).get('WAIT')} ticks)")
        P.check(dict(seen).get('DOWN') == ref['down_ticks'] + 5, f"lying {dict(seen).get('DOWN')} ticks (referee.down_ticks {ref['down_ticks']} + 5: SS2's landing step)")
        P.check(names[i + 5:i + 9] == ['OPEN', 'TYPE', 'HOLD', 'CLOSE'] and seen[i + 6][1] == 2 * sum(len(l) for l in ref['hit_text']),
                f"up, his window again: {' / '.join(ref['hit_text'])} typed ({seen[i + 6][1]} ticks)")
        P.until(lambda: P.r('bonus_on') == BN['off'] and P.r('mode') == 1, 120)
        P.check(P.r('bonus_on') == BN['off'] and P.r('mode') == 1, 'then the next stage')
        seen = seen[:i]                                 # (the timing checks below: his first speech up to its hold)
    d = dict(seen)
    P.check(d.get('WALK') == ref['from'] + ref['mark'], f"the walk in: {d.get('WALK')} ticks ({ref['from']} px outside to {ref['mark']} px inside at 1 px a tick, SS2's vx 256)")
    P.check(d.get('STAND') == 1 and d.get('RISE') == 1, 'one tick standing, then the jump (SS2)')
    for k, v in SS2.items():
        if quirk and k == 'CLOSE': continue             # (the first close cut by the D)
        P.check(d.get(k) == v, f'{k}: {d.get(k)} ticks (SS2: {v})')
    letters = sum(len(l) for l in text)
    P.check(d.get('TYPE') == 2 * letters, f"TYPE: {d.get('TYPE')} ticks for {letters} letters (a letter every 2 ticks from the window open, SS2's MESSDISP)")
    if not quirk:
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
    sys.exit(1 if main(*sys.argv[1:6]) else 0)
