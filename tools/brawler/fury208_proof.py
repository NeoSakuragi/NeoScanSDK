#!/usr/bin/env python3
"""TODO #208 proof (feedback 20261007-124603-b3f3: "I can't trigger a fury while grabbing the opponent, using the D button.
Make it standard that you should be able to trigger a fury or a MAX fury while grabbing the opponent"): in a hold (S_GRAB,
the attacker side) D starts the fury and down+D its MAX at once, as from neutral (fighter.c fury_press, one rule): the hold
ends, the victim reels free in its held pose (S_HITSTUN, not held), the fury plays with its invincibility (INV_FURY from its
trigger to its end) and hits that victim. harness.py on a `make AI_OFF=1` build (the test drives the enemies).

    BRAWLER_CORE=<core> python3 fury208_proof.py OUT [FIGHTER ...]     (default: every roster fighter with a fury)

Per fighter: the reference (neutral D / down+D from the same place: the fury's / MAX's spec_ix); then P1 walks into the
enemy (the grab) and (1) D in the idle hold, (2) down+D in the idle hold, (3) D while a hold hit plays (A, then D 3 frames
later: the press kept through the hold hit's hit-stop); two minions behind P1 press A every frame of the fury. Pass per
case: SPECIAL the frame the press is read (after the hit-stop) with the reference's spec_ix, INV_FURY on every fury
frame, 0 life lost while it plays, the victim out of the hold (HITSTUN, held 0) that frame and hit by the fury (its life
drops before the fury ends) whenever the same fury from neutral hits a standing enemy at the hold's distance (Hanzo SS2's
WFT starts its blow further out and whiffs there from neutral too) -> OUT/fury208.json, OUT/sheet_terry.png (every 4
frames from the press)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else "/data/tmp/f208/out/f208"
ONLY = sys.argv[2:]
INV_FURY = 0xFF
VICTIM, MINIONS = 2, (3, 4)
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))


def setup(b, start, gap):
    b.load(start); st = b.states.index
    for i in range(1, 8):
        if i not in (VICTIM,) + MINIONS: b.fset(i, 'state', st('OFF'))
    for i in (0, VICTIM) + MINIONS:
        b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
    b.place(0, x=100, z=20); b.fset(0, 'facing', 1); b.fset(0, 'meter', 300)
    b.place(VICTIM, x=100 + gap, z=20); b.fset(VICTIM, 'facing', 0xFF)
    for i in MINIONS: b.place(i, x=-200 if i == 4 else 400, z=20)
    for i in (VICTIM,) + MINIONS: b.intent(i)


def minions(b, on):
    st = b.states
    x, z, fc = b.fget(0, 'x'), b.fget(0, 'z'), b.fget(0, 'facing')
    for j, i in enumerate(MINIONS):
        b.intent(VICTIM)
        if not on: b.intent(i); continue
        if st[b.fget(i, 'state')] not in ('IDLE', 'WALK', 'ATTACK'):
            b.fset(i, 'state', st.index('IDLE')); b.fset(i, 'freeze', 0); b.fset(i, 'y', 0); b.fset(i, 'inv', 0)
        b.fset(i, 'hp', 60)
        b.place(i, x=x - fc * (26 + 12 * j), z=z + 2 * j); b.fset(i, 'facing', fc & 0xFF)
        b.intent(i, press=1, face=fc & 0xFF)


def reference(b, start, keys):
    setup(b, start, 200)
    b.run(1, p1=keys); b.run(1)
    return b.fget(0, 'spec_ix') if b.states[b.fget(0, 'state')] == 'SPECIAL' else None


def neutral_close(b, start, keys, gap):
    """the same fury from neutral on a standing enemy at the hold's distance: does it hit him? (a fury that starts its
    blow further out, Hanzo SS2's WFT, whiffs there from neutral too)"""
    setup(b, start, gap); hp = b.fget(VICTIM, 'hp')
    b.run(1, p1=keys)
    for f in range(400):
        b.run(1)
        if b.fget(VICTIM, 'hp') < hp: return True
        if b.states[b.fget(0, 'state')] != 'SPECIAL' and f > 2: break
    return False


def grab(b):
    for f in range(120):
        minions(b, False); b.run(1, p1='R')
        if b.states[b.fget(0, 'state')] == 'GRAB': return f
    return None


def case(b, start, keys, during_hit, shots=None):
    setup(b, start, 40)
    if grab(b) is None: return dict(ok=None, why='no grab')
    gap = round(abs(b.fget(VICTIM, 'x') - b.fget(0, 'x')))
    minions(b, False); b.run(4)
    if during_hit:
        minions(b, False); b.run(1, p1='a'); minions(b, False); b.run(3)
        hit_playing = b.fget(0, 'srow') != 0
    else: hit_playing = None
    st = b.states
    pre = dict(p1=st[b.fget(0, 'state')], victim=st[b.fget(VICTIM, 'state')], victim_hp=b.fget(VICTIM, 'hp'), freeze=b.fget(0, 'freeze'))
    minions(b, False)                                            # (they swing once the fury runs: P1 is not invincible in the hold)
    if shots is not None:
        p = os.path.join(OUT, f'_s{len(shots):03d}.png'); b.pad = [set(keys), set()]; b.screenshot(p); shots.append(('press', p))
    else: b.run(1, p1=keys)
    minions(b, False); b.run(1)                                  # (the pad is read by the next tick)
    delay = 1                                                    # (a hold hit's hit-stop: the press kept, then the fury)
    while st[b.fget(0, 'state')] == 'GRAB' and delay < 12: minions(b, False); b.run(1); delay += 1
    first = dict(delay=delay, freeze_at_press=pre.get('freeze'),p1=st[b.fget(0, 'state')], spec_ix=b.fget(0, 'spec_ix'), inv=b.fget(0, 'inv'),
                 victim=st[b.fget(VICTIM, 'state')], victim_held=b.fget(VICTIM, 'held'), p1_held=b.fget(0, 'held'))
    rows = []; hp0 = b.fget(VICTIM, 'hp')
    for f in range(600):
        s = st[b.fget(0, 'state')]
        if s != 'SPECIAL': break
        minions(b, True)
        r = dict(inv=b.fget(0, 'inv'), hp=b.fget(0, 'hp'))
        if shots is not None and f % 4 == 3 and len(shots) < 36:
            p = os.path.join(OUT, f'_s{len(shots):03d}.png'); b.pad = [set(), set()]; b.screenshot(p); shots.append((f'+{f + 1}', p))
        else: b.run(1)
        r.update(hp_after=b.fget(0, 'hp'), st_after=st[b.fget(0, 'state')], vhp=b.fget(VICTIM, 'hp'), vst=st[b.fget(VICTIM, 'state')],
                 swings=sum(st[b.fget(i, 'state')] == 'ATTACK' for i in MINIONS))
        rows.append(r)
    during = rows[:-1]
    res = dict(gap=gap, pre=pre, hold_hit_playing=hit_playing, first=first, fury_frames=len(rows),
               not_inv=sum(r['inv'] != INV_FURY for r in rows), life_lost=sum(r['hp'] - r['hp_after'] for r in during),
               p1_hitstun=sum(r['st_after'] in ('HITSTUN', 'KNOCKDOWN') for r in during),
               minion_swing_frames=sum(r['swings'] for r in rows),
               victim_life=[hp0, rows[-1]['vhp'] if rows else hp0],
               victim_states=[s for k, s in enumerate(r['vst'] for r in rows) if k == 0 or s != rows[k - 1]['vst']])
    return res


def judge(res, ref, hits):
    if res.get('ok') is None and 'why' in res: return None
    f = res['first']
    res['victim_hit'] = res['victim_life'][1] < res['victim_life'][0]; res['neutral_close_hits'] = hits
    return (res['pre']['p1'] == 'GRAB' and f['p1'] == 'SPECIAL' and f['spec_ix'] == ref and f['inv'] == INV_FURY and
            f['victim'] == 'HITSTUN' and not f['victim_held'] and not f['p1_held'] and res['not_inv'] == 0 and
            res['life_lost'] == 0 and res['p1_hitstun'] == 0 and (res['victim_hit'] or not hits))


def sheet(cells, path, title, cols=6):
    ims = [(lab, Image.open(p).convert('RGB')) for lab, p in cells]
    if not ims: return
    w, h = ims[0][1].size
    S = Image.new('RGB', (cols * w, 20 + ((len(ims) + cols - 1) // cols) * (h + 14)), 'white'); d = ImageDraw.Draw(S)
    d.text((4, 4), title, fill='black')
    for n, (lab, im) in enumerate(ims):
        x, y = (n % cols) * w, 20 + (n // cols) * (h + 14)
        S.paste(im, (x, y + 14)); d.text((x + 2, y + 1), lab, fill='black')
    S.save(path)
    for _, p in cells: os.remove(p)


def main():
    os.makedirs(OUT, exist_ok=True)
    roster = json.load(open(os.path.join(GAME, 'game.json')))['roster']
    b = Brawler(rom=os.path.join(GAME, 'brawler.neo'), game=GAME); res = {}
    for k, r in enumerate(roster):
        if not r.get('fury') or (ONLY and r['name'] not in ONLY): continue
        b.pick(k, unlock=True); start = b.save()
        out = {'ref_fury': reference(b, start, 'd'), 'ref_max': reference(b, start, 'Dd')}
        for name, keys, dh in (('hold_D', 'd', False), ('hold_downD', 'Dd', False), ('hold_hit_D', 'd', True)):
            shots = [] if r['name'] == 'terry' and name == 'hold_D' else None
            c = case(b, start, keys, dh, shots)
            if 'gap' in c and ('close', keys, c['gap']) not in out: out[('close', keys, c['gap'])] = neutral_close(b, start, keys, c['gap'])
            c['ok'] = judge(c, out['ref_max' if keys == 'Dd' else 'ref_fury'], out.get(('close', keys, c.get('gap'))))
            out[name] = c
            if shots: sheet(shots, os.path.join(OUT, 'sheet_terry.png'),
                            f"Terry holding an enemy, full meter, D pressed in the hold: fury {c['ok'] and 'starts and hits' or 'FAIL'}"
                            f" (victim life {c['victim_life'][0]} -> {c['victim_life'][1]}; every 4 frames)")
        oks = [out[n]['ok'] for n in ('hold_D', 'hold_downD', 'hold_hit_D')]
        out['ok'] = None if all(o is None for o in oks) else all(o is not False for o in oks)
        out = {k if isinstance(k, str) else 'neutral_%s_%d_hits' % ('downD' if k[1] == 'Dd' else 'D', k[2]): v for k, v in out.items()}
        res[r['name']] = out
        print(r['name'], out['ok'], json.dumps({n: (out[n]['ok'], out[n].get('first'), out[n].get('victim_life'), out[n].get('neutral_close_hits'), out[n].get('why'))
                                                 for n in ('hold_D', 'hold_downD', 'hold_hit_D')}), flush=True)
    json.dump(res, open(os.path.join(OUT, 'fury208.json'), 'w'), indent=1)
    bad = [n for n, v in res.items() if v['ok'] is False]
    print('ALL OK' if not bad else 'FAILURES: ' + ' '.join(bad))


if __name__ == '__main__':
    main()
