#!/usr/bin/env python3
"""Revamp phase 3 proof (Bruno 2026-10-08, docs/brawler_feel.md 8h: no command-grab inputs; every fighter's throws as data;
grab specials become throws; with meter a throw becomes its super version): every roster fighter's throw options from
the hold, both facings, in the Chain Lab's training mode (labdrive: P1 = the fighter, the dummy never attacks) in our
emulator's core (harness).

    python3 throws_rv3_proof.py OUT_DIR [FIGHTER ...]   -> OUT_DIR/throws_rv3.json, OUT_DIR/throws_<fighter>.png

Per fighter, P1 walks into the dummy (the hold), then: forward + A, back + A (its paired throws), up + A / down + A (its
extra throw, game.json roster[].throws.extra: a grab special's program or its paired throw_x; none: the hold hit),
forward / back + C with a full meter (the super throw: throws.super, else the throw pressed at the super tier) and
forward + C with no meter (the plain forward throw, nothing paid). Checked per option: what played (a paired throw BT_*,
a special by its input, its role), the dummy's damage, the meter spent, P1 untouchable (inv = INV_FURY) on every frame
of the throw (a paired throw: to its control return; a special: to its end), and for the throws that throw a body, a
second enemy (a copy of the dummy, slot 3) standing where the body comes down is knocked down by it while P1's target
gets no chain window from it (no chain credit). Sheets: one row per option and facing, a shot every SHOT_EVERY frames."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
from labdrive import Lab
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json')))
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
POOL = {f['name']: [p['input'] for p in f['pool']] for f in CL['fighters']}
names = [r['name'] for r in G['roster']]
RO = {r['name']: r for r in G['roster']}
only = sys.argv[2:] or [n for n in names if RO[n].get('selectable', True)]
L = Lab(); b = L.b; ST = b.states
INV_FURY = 0xFF
BS_FURY, BS_THROW = 6, 11                                     # fighter.h (BS_COUNT 6; BS_THROW = BS_COUNT + 5)
BT_NAMES = {0: 'forward throw (C)', 1: 'back throw (D)', 4: 'extra paired throw (throw_x)'}
STHROW, SDMG, THROW_DMG = G['meter']['super_throw'], G['tiers']['super_throw'], 12
import re
SRC = open(os.path.join(GAME, 'build', 'bm_chars.c')).read()
def windows(n):
    """its paired throws' thrown-body rows [rel, land) by throw_id (bthrow_t: nrows, speed, rows, ret, rel, land, ...)"""
    out = {}
    m = re.search(r'static const bthrow_t %s_throws\[BT_COUNT\] = \{(.*)\};' % n, SRC)
    for k, t in enumerate(re.findall(r'\{(\d+), \w+, \w+, (\d+), (\w+), (\w+),', m.group(1))): out[k] = (int(t[2], 0), int(t[3], 0))
    m = re.search(r'static const bthrow_t %s_xthrow = \{(\d+), \w+, \w+, (\d+), (\w+), (\w+),' % n, SRC)
    if m: out[4] = (int(m.group(3), 0), int(m.group(4), 0))
    return out
SHOT_EVERY, SHOTS = 10, 16

def st(i=0): return ST[b.fget(i, 'state')]
def run(n, k=''): b.run(n, p1=k)
def settle():
    for _ in range(900):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'freeze'): break
        run(1)
    else: raise RuntimeError('never idle: ' + b.brief((0, 2)))

def hold(face):
    """P1 walks into the dummy standing 40 px ahead (face 1: to the right) -> in the hold"""
    settle()
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 150
    b.place(0, x=x0, z=30); b.place(2, x=x0 + 40 * face, z=30); b.fset(0, 'facing', face & 0xFF); b.fset(2, 'facing', -face & 0xFF)
    b.fset(2, 'hp', 60); run(2)
    k = 'R' if face > 0 else 'L'
    for _ in range(60):
        if st(0) == 'GRAB': break
        run(1, k)
    else: raise RuntimeError('no hold: ' + b.brief((0, 2)))
    run(2)

def second():
    """a second enemy (a copy of the idle dummy, slot 3), out of the way until placed"""
    base = b.base; src = base + 2 * b.fsize; dst = base + 3 * b.fsize
    for o in range(b.fsize): b.w(dst + o, 1, b.r(src + o, 1))
    b.fset(3, 'idx', 3); b.place(3, x=b.fget(2, 'x') + 400, z=30); b.fset(3, 'hp', 60); b.fset(3, 'facing', 1)

OPTIONS = [('fA', 'forward + A', 'f', 'a', 300), ('bA', 'back + A', 'b', 'a', 300), ('uA', 'up + A', 'U', 'a', 300),
           ('dA', 'down + A', 'D', 'a', 300), ('fC', 'forward + C, meter 300', 'f', 'c', 300),
           ('bC', 'back + C, meter 300', 'b', 'c', 300), ('fC0', 'forward + C, meter 0', 'f', 'c', 0)]

def play(n, opt, face, shots=None, body_x=None):
    key, label, stick, btn, meter = opt
    if body_x is not None: settle(); second()
    hold(face)
    if body_x is not None: b.place(3, x=b.fget(0, 'x') + body_x, z=30); b.fset(3, 'facing', face & 0xFF)
    b.fset(0, 'meter', meter); b.fset(0, 'meter_t', 0)
    k = {'f': 'R' if face > 0 else 'L', 'b': 'L' if face > 0 else 'R'}.get(stick, stick) + btn
    m0 = meter; h0 = len(b.hits); x0 = b.fget(0, 'x')
    run(2, k)
    r = {'option': key, 'label': label, 'facing': 'right' if face > 0 else 'left', 'states': [], 'inv_frames': 0, 'act_frames': 0}
    r['meter_spent'] = m0 - b.fget(0, 'meter')                  # (at the press: the gauge refills a point every 4 frames)
    if st(0) == 'GRAB' and b.fget(0, 'xwait'):                 # a paired super throw: its super flash over the hold first
        r['flash_frames'] = b.fget(0, 'xwait') + 2
        while b.fget(0, 'xwait'): run(1)
        run(1)
    s0, sid, six, sthr = st(0), b.fget(0, 'spec_id'), b.fget(0, 'spec_ix'), b.fget(0, 'sthr')
    if s0 == 'THROW': r['played'] = BT_NAMES.get(b.fget(0, 'throw_id'), f'throw {b.fget(0, "throw_id")}')
    elif s0 == 'SPECIAL':
        r['played'] = f'special {POOL[n][six]}' + (' (super throw, as a fury)' if sthr == 2 else ' (extra throw)' if sid == BS_THROW else f' (role {sid})')
    elif s0 == 'GRAB': r['played'] = 'hold hit'
    else: r['played'] = s0
    r['thr_dmg'] = b.fget(2, 'thr_dmg') if s0 == 'THROW' else None
    pics, low, body = [], [], {'states': set(), 'hp': None}
    t = 0; ymax = 0; chain_t = 0; dz_ = 0
    for t in range(2, 600):
        s = st(0)
        if s in ('THROW', 'SPECIAL'):
            r['act_frames'] += 1; r['inv_frames'] += b.fget(0, 'inv') == INV_FURY
        if s not in r['states']: r['states'].append(s)
        tb = b.fget(2, 'tb_by'); vs = st(2); vy = b.fget(2, 'y'); ymax = max(ymax, vy); dz_ = max(dz_, b.fget(2, 'dizzy'))
        if vs == 'THROWN': w = WIN.get(b.fget(2, 'throw_id')); act = w is not None and w[0] != 0xFFFF and w[0] <= b.fget(2, 'srow') - 1 < w[1]
        else: act = bool(tb) and vs == 'KNOCKDOWN' and vy > 0 and not b.fget(2, 'kfloor')
        if act: low.append((round(vy), b.fget(2, 'x') - x0))   # the thrown body's frames (fighter.c combat), from P1's x at the press
        if body_x is not None: body['states'].add(st(3)); chain_t = chain_t or b.fget(0, 'chain_t')
        if shots is not None and t % SHOT_EVERY == 0 and len(pics) < SHOTS:
            p = os.path.join(OUT, f'_s{len(pics)}.png'); b.screenshot(p); pics.append(Image.open(p).copy()); os.unlink(p)
        else: run(1)
        if t > 20 and st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and (shots is None or len(pics) >= SHOTS): break
    r['frames'] = t
    r['damage'] = sum(d for f_, i_, d, s_ in b.hits[h0:] if i_ == 2)   # (the training dummy's life is topped up)
    r['victim_max_height'] = round(ymax)
    r['invincible'] = r['act_frames'] > 0 and r['inv_frames'] == r['act_frames']
    r['body_frames'] = len(low)
    r['low_body_dx'] = [round(x) for y_, x in low if y_ < 40]   # (in time order: where the body comes down low)
    r['stun'] = dz_
    if body_x is not None:
        body['states'] = sorted(body['states']); body['hp'] = sum(d for f_, i_, d, s_ in b.hits[h0:] if i_ == 3); body['no_chain_credit'] = not chain_t
        r['second_enemy'] = body
    if shots is not None: shots.append((f'{label}, facing {r["facing"]}: {r["played"]}, damage {r["damage"]}', pics))
    return r

def sheet(n, rows):
    w, h = 160, 112
    W = Image.new('RGB', (SHOTS * (w + 4) + 4, len(rows) * (h + 22) + 4), 'white'); d = ImageDraw.Draw(W)
    for i, (title, pics) in enumerate(rows):
        y = 4 + i * (h + 22); d.text((4, y), title, fill='black')
        for k, im in enumerate(pics):
            W.paste(im.resize((w, h)), (4 + k * (w + 4), y + 14))
            d.rectangle((4 + k * (w + 4) - 1, y + 13, 4 + k * (w + 4) + w, y + 14 + h), outline='black')
    W.save(os.path.join(OUT, f'throws_{n}.png'))

res = json.load(open(os.path.join(OUT, 'throws_rv3.json'))) if os.path.exists(os.path.join(OUT, 'throws_rv3.json')) else {}
for n in only:
    fi = names.index(n)
    L.start(fi, 1 if fi == 0 else 0); run(30)
    WIN = windows(n)
    blob = b.save()
    out = {'throws': RO[n].get('throws', {}), 'options': []}
    rows = []
    x = (RO[n].get('throws') or {}).get('extra') or {}
    for opt in OPTIONS:
        for face in (1, -1):
            b.load(blob)
            want_shots = opt[0] in ('fA', 'bA', 'fC', 'bC', 'fC0') or (opt[0] == 'uA' and 'u' in x) or (opt[0] == 'dA' and 'd' in x)
            r = play(n, opt, face, rows if want_shots else None)
            if r['low_body_dx'] and opt[0] != 'fC0':            # a thrown body coming down low: a second enemy there
                for bx in (r['low_body_dx'][-1], r['low_body_dx'][len(r['low_body_dx']) // 2]):   # (its landing, then midway)
                    b.load(blob)
                    r2 = play(n, opt, face, None, body_x=bx)
                    r['second_enemy'] = dict(r2.get('second_enemy', {}), placed_dx=bx)
                    if 'KNOCKDOWN' in r['second_enemy']['states']: break
            elif opt[0] != 'fC0' and r['played'] != 'hold hit':
                r['body_note'] = 'no thrown-body phase in its data' if not r['body_frames'] else 'its body never comes down low (above 40 px)'
            # checks
            ex = x.get('u' if opt[0] == 'uA' else 'd') if opt[0] in ('uA', 'dA') else None
            sup = (RO[n].get('throws') or {}).get('super')
            if opt[0] in ('fA', 'bA'): want = 'throw'
            elif opt[0] in ('uA', 'dA'): want = 'hold hit' if not ex else 'throw_x' if ex == 'throw_x' else 'special ' + ex
            elif opt[0] == 'fC0': want = 'forward throw (C)'
            else: want = 'super ' + (sup or 'throw pressed')
            p = r['played']
            okp = (want == 'throw' and 'throw' in p and 'special' not in p) or (want == 'hold hit' and p == 'hold hit') or \
                  (want == 'throw_x' and 'throw_x' in p) or (want.startswith('special ') and p.startswith(want) and 'extra' in p) or \
                  (want == 'forward throw (C)' and p.startswith('forward throw')) or \
                  (want.startswith('super ') and ((sup == 'throw_x' and 'throw_x' in p) or (not sup and 'throw' in p and 'special' not in p) or
                                                  (sup and sup != 'throw_x' and p.startswith('special ' + sup) and 'super' in p)))
            r['want'] = want
            r['ok_played'] = okp
            r['ok_meter'] = r['meter_spent'] == (STHROW if opt[0] in ('fC', 'bC') else 0)
            r['ok_inv'] = p == 'hold hit' or r['invincible']
            r['ok_damage'] = p == 'hold hit' or r['damage'] > 0 or (r['stun'] > 0 and 'special' not in p)   # (a stun strike: Cheng-Fu)
            if opt[0] in ('fC', 'bC') and r['thr_dmg'] is not None: r['ok_damage'] = r['ok_damage'] and r['thr_dmg'] == SDMG
            if 'second_enemy' in r: r['ok_body'] = 'KNOCKDOWN' in r['second_enemy']['states'] and r['second_enemy']['no_chain_credit']
            r['ok'] = all(v for k_, v in r.items() if k_.startswith('ok_'))
            out['options'].append(r)
            print(f"{n:10s} {opt[0]:4s} {r['facing']:5s} {p:52s} dmg {r['damage']:2d} meter {r['meter_spent']:3d} inv {r['inv_frames']}/{r['act_frames']}"
                  + (f" body {r['second_enemy']['states']}" if 'second_enemy' in r else '') + ('' if r['ok'] else '  <-- CHECK'), flush=True)
    out['ok'] = all(o['ok'] for o in out['options'])
    res[n] = out
    sheet(n, rows)
    json.dump(res, open(os.path.join(OUT, 'throws_rv3.json'), 'w'), indent=1)
print('ALL OK' if all(v['ok'] for v in res.values()) else 'NOT OK: ' + ', '.join(k for k, v in res.items() if not v['ok']))
