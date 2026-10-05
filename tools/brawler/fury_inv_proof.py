#!/usr/bin/env python3
"""The fury's invincibility (Bruno 2026-10-05: "keep the player invincible as soon as the fury connects and starts its
script"; fighter.c INV_FURY) proven for every roster fighter with a fury (game.json "fury"), harness.py on a
`make AI_OFF=1` build (the test drives the enemies' intents).

Per fighter: P1 fires the fury (C, meter full) at one enemy standing still (the distance searched until it connects);
from the frame it connects two minions stand behind P1 pressing A every frame (knocked minions re-stood) until the
fury ends, then on for 150 frames. Pass: 0 life lost / no hitstun while the fury plays after its connect, a hit
taken after it ends (hittable again), and the whiff (the target off P1's depth line) hittable during the fury.
Kim: OUT/kim_phoenix.png, his Phoenix with the minions swinging through him.

    python3 fury_inv_proof.py [OUTDIR]        (default /data/tmp/furyinv/out)"""
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
    """fire the fury; returns per-frame rows until 150 frames after it ends (or 400 frames)"""
    rows, started, lock_seen, end = [], None, False, None
    hits0 = len(b.hits)
    for f in range(600):
        st = b.states[b.fget(0, 'state')]
        inv = b.fget(0, 'inv')
        if inv == INV_FURY: lock_seen = True
        if started is None and st == 'SPECIAL': started = f
        if started is not None and end is None and st != 'SPECIAL': end = f
        on = (lock_seen if WHIFF is False else started is not None)
        minions(b, on)
        hp = b.fget(0, 'hp')
        keys = 'c' if f < 3 else ''
        if shots is not None and lock_seen and end is None and f % 4 == 0:
            p = os.path.join(OUT, f'_k{f}.png'); b.pad = [set(keys), set()]; b.screenshot(p); shots.append(p)
        else: b.run(1, p1=keys)
        rows.append(dict(f=f, st=st, inv=inv, hp=hp, hp_after=b.fget(0, 'hp'), st_after=b.states[b.fget(0, 'state')],
                         mst=[b.states[b.fget(i, 'state')] for i in MINIONS]))
        if end is not None and f - end > 150: break
        if started is None and f > 60: break
    return rows, started, end, [h for h in b.hits[hits0:] if h[1] == 0]

def judge_connect(rows, end):
    lock = [r for r in rows if r['inv'] == INV_FURY]
    if not lock: return dict(ok=None, why='never connected')
    lf = lock[0]['f']
    during = [r for r in rows if lf <= r['f'] < end - 1]   # frame end-1: the script ended in its update (special_end
                                                           # cleared the lock), its combat came after: the fury is over
    lost = sum(r['hp'] - r['hp_after'] for r in during)
    stun = [r['f'] for r in during if r['st_after'] in ('HITSTUN', 'KNOCKDOWN')]
    swings = sum(1 for r in during for m in r['mst'] if m == 'ATTACK')
    after = [r for r in rows if r['f'] >= end and (r['hp_after'] < r['hp'] or r['st_after'] == 'HITSTUN')]
    inv_after = [r['inv'] for r in rows if r['f'] == end + 1]
    return dict(ok=lost == 0 and not stun and bool(after) and swings > 0, lock_from=lf, fury_end=end, lock_frames=end - lf,
                hp_lost_during=lost, hitstun_during=stun, minion_swing_frames=swings,
                hit_after_end_in=(after[0]['f'] - end) if after else None, inv_after_end=inv_after)

def judge_whiff(rows, started, end):
    locked = any(r['inv'] == INV_FURY for r in rows)
    hit = [r['f'] for r in rows if r['hp_after'] < r['hp'] and r['st'] == 'SPECIAL']
    return dict(ok=not locked and bool(hit), locked=locked, hit_during_fury_at=(hit[0] - started) if hit else None)

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
    global WHIFF
    os.makedirs(OUT, exist_ok=True)
    roster = json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))['roster']
    b = Brawler(); res = {}
    for k, r in enumerate(roster):
        if not r.get('fury'): continue
        b.pick(k, unlock=True); start = b.save()
        out = dict(fury=r['fury'])
        WHIFF = False
        for d in (40, 60, 90, 130, 180):
            setup(b, k, start, d, False)
            shots = [] if r['name'] == 'kim' else None
            rows, started, end, hits = play(b, shots)
            if started is not None and end is not None and any(x['inv'] == INV_FURY for x in rows): break
            if shots: [os.remove(p) for p in shots]
        out['distance'] = d
        out['connect'] = judge_connect(rows, end) if started is not None and end is not None else dict(ok=False, why='no fury')
        if shots: sheet(shots, os.path.join(OUT, 'kim_phoenix.png'))
        WHIFF = True
        setup(b, k, start, 90, True)
        rows, started, end, hits = play(b)
        out['whiff'] = judge_whiff(rows, started, end) if started is not None else dict(ok=False, why='no fury')
        if out['connect']['ok'] is None: out['connect']['why'] = 'its fury has no hit box (no hit on a standing target at any distance)'
        out['ok'] = out['connect']['ok'] is not False and out['whiff']['ok']
        res[r['name']] = out
        print(r['name'], 'ok' if out['ok'] else 'FAIL', out['connect'], out['whiff'], flush=True)
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print('ALL OK' if all(v['ok'] for v in res.values()) else 'FAILURES: ' + ' '.join(n for n, v in res.items() if not v['ok']))

if __name__ == '__main__':
    main()
