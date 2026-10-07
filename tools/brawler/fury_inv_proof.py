#!/usr/bin/env python3
"""The fury's invincibility (Bruno 2026-10-06: "make sure for all furies, there is full invincibility when triggering
them"; fighter.c INV_FURY, set in start_special) proven for every roster fighter with a fury (game.json "fury"),
harness.py on a `make AI_OFF=1` build (the test drives the enemies' intents).

Per fighter: P1 fires the fury (D, meter full) at one enemy standing in front (the connect case) and again with the
enemy off P1's depth line (the whiff); from the first frame of the fury two minions stand behind P1 pressing A every
frame (knocked minions re-stood) until the fury ends, then on for 150 frames. Pass, both cases: INV_FURY on every frame
of the fury from its trigger, 0 life lost / no hitstun while it plays, a hit taken after it ends (hittable again). Also
the enemy side: an enemy with a fury fired by its intent (D) is INV_FURY from its first frame to its end.
Kim: OUT/kim_phoenix.png, his Phoenix with the minions swinging through him.

    python3 fury_inv_proof.py [OUTDIR [FIGHTER ...]]        (default /data/tmp/furyinv/out, every fighter)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/furyinv/out'
INV_FURY = 0xFF
VICTIM, MINIONS = 2, (3, 4)

def setup(b, k, start, d, whiff):
    b.load(start)
    st = b.states.index
    for i in (0, VICTIM) + MINIONS:
        b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
    b.place(0, x=100, z=20); b.fset(0, 'facing', 1); b.fset(0, 'meter', 120)
    b.place(VICTIM, x=100 + d, z=20 + (60 if whiff else 0)); b.fset(VICTIM, 'facing', -1)
    for i in MINIONS: b.place(i, x=-200 if i == 4 else 400, z=20)   # out of the way until they swing
    for i in (VICTIM,) + MINIONS: b.intent(i)

def minions(b, on):
    st = b.states
    x, z, fc = b.fget(0, 'x'), b.fget(0, 'z'), b.fget(0, 'facing')
    for j, i in enumerate(MINIONS):
        if not on: b.intent(i); continue
        if st[b.fget(i, 'state')] not in ('IDLE', 'WALK', 'ATTACK'):   # knocked by the fury: stood up again
            b.fset(i, 'state', st.index('IDLE')); b.fset(i, 'freeze', 0); b.fset(i, 'y', 0); b.fset(i, 'inv', 0)
        b.fset(i, 'hp', 60)
        b.place(i, x=x - fc * (26 + 12 * j), z=z + 2 * j); b.fset(i, 'facing', fc & 0xFF)
        b.intent(i, press=1, face=fc & 0xFF)

def play(b, shots=None):
    """fire the fury; returns per-frame rows until 150 frames after it ends"""
    rows, started, end = [], None, None
    for f in range(600):
        st = b.states[b.fget(0, 'state')]
        inv = b.fget(0, 'inv')
        if started is None and st == 'SPECIAL': started = f
        if started is not None and end is None and st != 'SPECIAL': end = f
        minions(b, started is not None)
        hp = b.fget(0, 'hp')
        keys = 'd' if f < 3 else ''
        if shots is not None and started is not None and end is None and f % 4 == 0:
            p = os.path.join(OUT, f'_k{f}.png'); b.pad = [set(keys), set()]; b.screenshot(p); shots.append(p)
        else: b.run(1, p1=keys)
        rows.append(dict(f=f, st=st, inv=inv, hp=hp, hp_after=b.fget(0, 'hp'), st_after=b.states[b.fget(0, 'state')],
                         mst=[b.states[b.fget(i, 'state')] for i in MINIONS]))
        if end is not None and f - end > 150: break
        if started is None and f > 60: break
    return rows, started, end

def judge(rows, started, end):
    if started is None or end is None: return dict(ok=False, why='no fury')
    fury = [r for r in rows if started <= r['f'] < end]
    not_inv = [r['f'] - started for r in fury if r['inv'] != INV_FURY]
    during = [r for r in rows if started <= r['f'] < end - 1]   # frame end-1: the script ended in its update (special_end
                                                                # cleared it), its combat came after: the fury is over
    lost = sum(r['hp'] - r['hp_after'] for r in during)
    stun = [r['f'] for r in during if r['st_after'] in ('HITSTUN', 'KNOCKDOWN')]
    swings = sum(1 for r in during for m in r['mst'] if m == 'ATTACK')
    after = [r for r in rows if r['f'] >= end and (r['hp_after'] < r['hp'] or r['st_after'] == 'HITSTUN')]
    return dict(ok=not not_inv and lost == 0 and not stun and bool(after) and swings > 0, fury_frames=end - started,
                not_inv_frames=not_inv[:8], hp_lost_during=lost, hitstun_during=stun, minion_swing_frames=swings,
                hit_after_end_in=(after[0]['f'] - end) if after else None)

def enemy_fury(b, start):
    """the enemy VICTIM fires its fury by intent (D): INV_FURY from its first frame to its end"""
    b.load(start); st = b.states
    for i in (0, VICTIM) + MINIONS: b.fset(i, 'state', st.index('IDLE')); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
    b.place(0, x=60, z=20); b.place(VICTIM, x=200, z=80); b.fset(VICTIM, 'facing', -1)
    for i in MINIONS: b.place(i, x=-200 if i == 4 else 400, z=20); b.intent(i)
    started, frames = None, []
    for f in range(400):
        b.intent(VICTIM, press=8 if f < 2 else 0); b.run(1)
        s = st[b.fget(VICTIM, 'state')]
        if s == 'SPECIAL' and b.fget(VICTIM, 'spec_id') == 6: started = f if started is None else started; frames.append(b.fget(VICTIM, 'inv'))
        elif started is not None: break
    if started is None: return dict(ok=None, why='no enemy fury')
    return dict(ok=all(v == INV_FURY for v in frames), frames=len(frames), not_inv=sum(v != INV_FURY for v in frames))

def sheet(paths, out):
    ims = [Image.open(p) for p in paths[:24]]
    if not ims: return
    w, h = ims[0].size; cols = 6; rws = (len(ims) + cols - 1) // cols
    S = Image.new('RGB', (cols * w, rws * (h + 14)), 'white'); d = ImageDraw.Draw(S)
    for n, (im, p) in enumerate(zip(ims, paths)):
        x, y = (n % cols) * w, (n // cols) * (h + 14)
        S.paste(im, (x, y + 14)); d.text((x + 2, y + 1), 'frame ' + p.split('_k')[1][:-4], fill='black')
    S.save(out)
    for p in paths: os.remove(p)

def main():
    os.makedirs(OUT, exist_ok=True)
    roster = json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))['roster']
    b = Brawler(); res = {}
    for k, r in enumerate(roster):
        if not r.get('fury') or (sys.argv[2:] and r['name'] not in sys.argv[2:]): continue
        b.pick(k, unlock=True); start = b.save()
        out = dict(fury=r['fury'])
        for case, whiff in (('connect', False), ('whiff', True)):
            setup(b, k, start, 60, whiff)
            shots = [] if r['name'] == 'kim' and not whiff else None
            out[case] = judge(*play(b, shots))
            if shots: sheet(shots, os.path.join(OUT, 'kim_phoenix.png'))
        out['enemy'] = enemy_fury(b, start)
        out['ok'] = out['connect']['ok'] and out['whiff']['ok'] and out['enemy']['ok'] is not False
        res[r['name']] = out
        print(r['name'], 'ok' if out['ok'] else 'FAIL', out['connect'], out['whiff'], out['enemy'], flush=True)
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print('ALL OK' if all(v['ok'] for v in res.values()) else 'FAILURES: ' + ' '.join(n for n, v in res.items() if not v['ok']))

if __name__ == '__main__':
    main()
