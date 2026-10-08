#!/usr/bin/env python3
"""Revamp 2 / 3: the rv2-* and rv3-* scenarios (scenarios.json) played as the Player / proof clip plays them (scenario.py setup, then
do_keys and `proof` frames), our emulator's core: per recipe P1's meter / life / state / special / breaker blink / red
overlay over time, the expectation checked, and a contact sheet of every 8th frame (OUT/<id>.png).

    python3 meter_scenarios_check.py OUT_DIR [ID ...]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H, scenario as SC
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
R = json.load(open(os.path.join(HERE, 'scenarios.json')))
G = json.load(open(os.path.join(H.GAME, 'game.json'))); M = G['meter']; T = G['tiers']
ids = sys.argv[2:] or [k for k in R if k.startswith('rv2-') or k.startswith('rv3-')]
BS_THROW = 11
BS_FURY = 6

def judge(rid, tr, s0):
    sp = [t for t in tr if t['state'] == 'SPECIAL']
    first = sp[0] if sp else None
    if rid == 'rv2-meter-special': return bool(first) and first['meter'] == M['max'] - M['special'] and first['hp'] == 60
    if rid == 'rv2-meter-life': return bool(first) and first['hp'] == 60 - M['life_special'] and first['meter'] < M['special']
    if rid == 'rv2-breaker': return bool(first) and first['brk'] > 0 and first['meter'] == M['max'] - M['breaker'] and any(t['ovl'] == 1 for t in sp)
    if rid == 'rv2-breaker-life':
        pre = tr[tr.index(first) - 1] if first else None             # (the frame before: the life it paid from)
        return bool(first) and first['brk'] > 0 and first['meter'] < M['breaker'] and first['hp'] == pre['hp'] - M['life_breaker']
    if rid == 'rv2-no-breaker': return not sp and any(t['state'] == 'HITSTUN' for t in tr) and any(t['ovl'] == 2 for t in tr)
    if rid == 'rv2-fury': return bool(first) and first['spec_id'] == BS_FURY and first['fmax'] == 0 and first['meter'] == 0 and s0['dmg'] == T['fury']
    if rid == 'rv2-max-red': return bool(first) and first['spec_id'] == BS_FURY and first['fmax'] == 1 and first['meter'] == 0 and s0['dmg'] == T['max'] and first['hp'] * 100 <= 60 * M['low']
    thr = [t for t in tr if t['state'] in ('THROW', 'SPECIAL')]    # revamp 3: the throws
    inv = all(t['inv'] == 0xFF for t in thr) and bool(thr)
    if rid == 'rv3-ralf-426': return inv and thr[0]['state'] == 'THROW' and thr[0]['throw_id'] == 4 and s0['dmg'] == 12 and tr[-1]['meter'] == M['max']
    if rid == 'rv3-super-throw': return inv and thr[0]['state'] == 'THROW' and s0['dmg'] == T['super_throw'] and min(t['meter'] for t in tr) == M['max'] - M['super_throw']
    if rid == 'rv3-super-throw-empty': return inv and thr[0]['state'] == 'THROW' and s0['dmg'] == 12 and all(t['hp'] == 60 for t in tr)
    if rid == 'rv3-rosa-super': return inv and thr[0]['spec_id'] == BS_FURY and thr[0]['sthr'] == 2 and s0['dmg'] == T['super_throw'] and min(t['meter'] for t in tr) == M['max'] - M['super_throw']
    if rid == 'rv3-iori-extra': return inv and thr[0]['spec_id'] == BS_THROW and thr[0]['sthr'] == 1 and s0['dmg'] == T['special'] and tr[-1]['meter'] == M['max']
    if rid == 'rv3-throw-body': return inv and thr[0]['state'] == 'THROW' and s0['body'] > 0
    if rid == 'rv2-max-not-red': return bool(first) and first['spec_id'] == BS_FURY and first['fmax'] == 0 and s0['dmg'] == T['fury']
    return None

res = {}
b = H.Brawler(); b.game = H.GAME; ST = b.states
for rid in ids:
    rec = R[rid]
    SC.setup(b, rec)
    keys = [(int(n), k) for n, _, k in (p.partition(':') for p in rec.get('do_keys', '').split(',') if p)]
    keys.append((rec.get('proof', 90), '-'))
    tr, shots, t, s0 = [], [], 0, {'hp_hit': None, 'dmg': 0, 'body': 0}
    fo = 2
    for n, k in keys:
        for _ in range(n):
            hp2 = b.fget(fo, 'hp'); st0 = ST[b.fget(0, 'state')]; hp3 = b.fget(3, 'hp')
            shot = (t + 1) % 8 == 0 and len(shots) < 24
            if shot:                                     # (the screenshot plays this frame, its keys held)
                p = os.path.join(OUT, f'_{rid}_{t + 1}.png'); b.pad = [set(k.replace('-', '')), set()]; b.screenshot(p)
            else: b.run(1, p1=k)
            t += 1
            if b.fget(fo, 'hp') < hp2: s0['dmg'] += hp2 - b.fget(fo, 'hp')
            if b.fget(3, 'hp') < hp3: s0['body'] += hp3 - b.fget(3, 'hp')   # (rv3-throw-body: the extra dummy)
            row = {'t': t, 'state': ST[b.fget(0, 'state')], 'meter': b.fget(0, 'meter'), 'hp': b.fget(0, 'hp'), 'spec_id': b.fget(0, 'spec_id'),
                   'spec_ix': b.fget(0, 'spec_ix'), 'brk': b.fget(0, 'brk'), 'ovl': b.fget(0, 'ovl'), 'fmax': b.fget(0, 'fmax'),
                   'inv': b.fget(0, 'inv'), 'sthr': b.fget(0, 'sthr'), 'throw_id': b.fget(0, 'throw_id')}
            if row['state'] == 'HITSTUN' and st0 != 'HITSTUN': s0['hp_hit'] = row['hp']
            tr.append(row)
            if shot: shots.append((p, row))
    ok = judge(rid, tr, s0)
    res[rid] = {'ok': ok, 'damage_dealt': s0['dmg'], 'hp_after_hit': s0['hp_hit'],
                'first_special': next((x for x in tr if x['state'] == 'SPECIAL'), None), 'states': sorted({x['state'] for x in tr})}
    print(rid, 'ok' if ok else 'FAIL', json.dumps(res[rid]), flush=True)
    if shots:
        ims = [Image.open(p) for p, _ in shots]; w, h = ims[0].size; cols = 6
        S = Image.new('RGB', (cols * w, ((len(ims) + cols - 1) // cols) * (h + 14)), 'white'); d = ImageDraw.Draw(S)
        for i, (im, (p, row)) in enumerate(zip(ims, shots)):
            x, y = i % cols * w, i // cols * (h + 14); S.paste(im, (x, y + 14))
            d.text((x + 2, y + 1), f"t{row['t']} {row['state']} m{row['meter']} hp{row['hp']}", fill='black'); os.remove(p)
        S.save(os.path.join(OUT, rid + '.png'))
json.dump(res, open(os.path.join(OUT, 'scenarios_check.json'), 'w'), indent=1)
print('ALL OK' if all(v['ok'] for v in res.values()) else 'FAILURES')
