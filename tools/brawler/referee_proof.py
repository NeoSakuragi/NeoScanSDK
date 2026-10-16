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
      d: D pressed in the hold: the window closes, the fighter runs at him (onto his lane) and fires his fury; as it
      fires the referee becomes his body (fighters[2] = referee.fighter, Kuroko's export, note 20261016-045652-e03d
      reopen): the WHOLE fury lands on him (WAIT: his hits counted by his life's drops = the same fury's hits on the
      practice dummy (scenario mode "lab": a standing enemy that never acts) at the same distance, Kuroko's body and
      the default dummy Ryo), his own reactions, up again (idle), then the window again with referee.hit_text typed
    screenshots OUT/*.png + OUT/sheet.png; one OK / FAIL line per check, exit 1 on any FAIL; OUT/hits.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from bonus_proof import Proof, BN
import scenario
from PIL import Image, ImageDraw

PH = ['OFF', 'WALK', 'STAND', 'RISE', 'JUMP', 'LAND', 'OPEN', 'TYPE', 'HOLD', 'CLOSE', 'WAIT']
BODY = 2                                                 # main.c RF_IDX: the referee's body's fighter slot


def lab_hits(b, fighter, dummy, gap):
    """the reference: the fury (D, gauge full) on the practice dummy (a standing enemy that never acts) gap px ahead,
    on P1's lane; its hits = the harness's hit log on it (a life drop or a fresh hit-stop: harness.Brawler.run) from
    the press to the fury's end (its life kept high once hit: the practice refills it below 20, which hid hits)"""
    scenario.setup(b, {'setup': {'mode': 'lab', 'fighter': fighter, 'dummy': dummy, 'gap': gap}})
    st = b.states
    b.fset(0, 'drive', 240 * b.r(b.syms['drive_chunks'], 1)); b.fset(0, 'fgauge', 0xFFFF); b.run(2)
    fired, seen, f0 = False, set(), b.frame; b.hits = []
    for k in range(1800):
        if st[b.fget(2, 'state')] not in ('IDLE', 'WALK') and b.fget(2, 'hp') < 1000: b.fset(2, 'hp', 30000)   # (hit: kept off the refills)
        b.run(1, p1='d' if k == 0 else '')
        s1, s0 = st[b.fget(2, 'state')], st[b.fget(0, 'state')]
        seen.add(s1); fired |= s0 == 'SPECIAL'
        if k > 30 and fired and s0 in ('IDLE', 'WALK') and s1 == 'IDLE': break
    log = [(f - f0, d) for f, i, d, _ in b.hits if i == 2 and f > f0 and d < 1000]   # (not its refill as it stands up)
    return len(log), sorted(seen), log
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
    if quirk: shots.update({'WAIT': 40})
    keys, pressed = '', False
    names = scenario.roster(game); body_ch = names.index(ref['fighter']) if quirk else None
    hp0, gap, bstates, bup, f0 = None, None, [], None, None
    for k in range(3000):
        p = ph()
        if quirk and p == 'WAIT' and b.states[b.fget(BODY, 'state')] != 'OFF' and b.char_of(BODY) == body_ch:
            h = b.fget(BODY, 'hp'); s1 = b.states[b.fget(BODY, 'state')]
            if hp0 is None: hp0 = h; gap = round(abs(b.fget(BODY, 'x') - b.fget(0, 'x'))); dz = b.fget(BODY, 'z') - b.fget(0, 'z'); f0 = b.frame - 1
            if not bstates or bstates[-1] != s1: bstates.append(s1)
        if quirk and gap is not None and p == 'OPEN' and bup is None: bup = b.states[b.fget(BODY, 'state')]   # (his window: up)
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
        hlog = [(f - f0, d) for f, j, d, _ in b.hits if j == BODY and f0 is not None and f > f0]   # (the harness's hit log)
        hits = len(hlog)
        P.check(names[i + 1:i + 2] == ['WAIT'] and gap is not None,
                f"then the fury runs at him and fires: his body (fighter {ref['fighter']}) in play {gap} px ahead, dz {dz if gap is not None else None} (WAIT {dict(seen).get('WAIT')} ticks)")
        P.check(hits > 0 and bup == 'IDLE', f"the fury on his body: {hits} hits; his states {' > '.join(bstates)}, {bup} as his window opens")
        P.check(names[i + 2:i + 6] == ['OPEN', 'TYPE', 'HOLD', 'CLOSE'] and seen[i + 3][1] == 2 * sum(len(l) for l in ref['hit_text']),
                f"up, his window again: {' / '.join(ref['hit_text'])} typed ({seen[i + 3][1] if len(seen) > i + 3 else None} ticks)")
        P.until(lambda: P.r('bonus_on') == BN['off'] and P.r('mode') == 1, 120)
        P.check(P.r('bonus_on') == BN['off'] and P.r('mode') == 1 and b.states[b.fget(BODY, 'state')] == 'OFF', 'then the next stage (his body gone)')
        seen = seen[:i]                                 # (the timing checks below: his first speech up to its hold)
        ref_hits = {}
        for dm in (ref['fighter'], 'ryo'):
            ref_hits[dm] = lab_hits(b, fighter, dm, gap)
            line = (f"the same fury on the practice dummy {dm} {gap} px ahead: {ref_hits[dm][0]} hits "
                    f"(the referee's body: {hits}); dummy states {' '.join(ref_hits[dm][1])}")
            if dm == ref['fighter']: P.check(ref_hits[dm][0] == hits, line)   # (the same body: the same hits)
            else: print('info', line)                    # (another body: its own boxes may take more or fewer)
        print('hit log (frame from the press, life lost): referee', hlog)
        for dm, v in ref_hits.items(): print(f'hit log: dummy {dm}', v[2])
        json.dump({'fighter': fighter, 'gap': gap, 'referee_hits': hits, 'referee_states': bstates, 'referee_log': hlog,
                   'dummy_hits': {k: v[0] for k, v in ref_hits.items()}, 'dummy_logs': {k: v[2] for k, v in ref_hits.items()}},
                  open(os.path.join(out, 'hits.json'), 'w'), indent=1)
    d = dict(seen)
    dl = ref.get('delay', 0)                            # (0.10.152: referee.delay ticks off screen, still, first)
    P.check(d.get('WALK') == dl + ref['from'] + ref['mark'], f"the walk in: {d.get('WALK')} ticks ({dl} still, then {ref['from']} px outside to {ref['mark']} px inside at 1 px a tick, SS2's vx 256)")
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
