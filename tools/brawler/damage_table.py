#!/usr/bin/env python3
"""Revamp phase 2: the damage tiers' table, before / after, per roster fighter (damage_tiers.py's measures).

    python3 damage_table.py RAW.json AFTER.json OUT_DIR     -> OUT_DIR/damage_table.md, damage_table.json

Before = brawler 0.5.0's rule on each move's own total (RAW.json, measured with the scales off): a special x the fighter's
roster[].damage (TODO #203), a fury / MAX as it is (0.5.0's MAX: down+D at any life). After = AFTER.json, measured on
the build. Checks: every special within tiers.spread.special % of tiers.special, every fury / MAX likewise, special <
fury < MAX per fighter; a special that never hits (0: a counter, a dodge, an opener of a follow-up) has no tier."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
G = json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))
T = G['tiers']; SP = T['spread']
raw, after, out = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), sys.argv[3]
dm = {r['name']: r.get('damage', 1) for r in G['roster']}
band = lambda k, v: abs(v - T[k]) * 100 <= SP[k] * T[k]
rows, res, bad = [], {}, []
for n, a in after.items():
    r = raw[n]; e = res[n] = {'archetype': a['archetype'], 'specials': {}, 'fury': None, 'max': None}
    for k, x in a['specials'].items():
        own = r['specials'][k]['damage']
        e['specials'][k] = {'before': own * dm[n], 'after': x['damage'], 'never_hits': own == 0,
                            'ok': own == 0 or band('special', x['damage'])}
    for k in ('fury', 'max'):
        if a.get(k): e[k] = {'input': a[k]['input'], 'before': r[k]['damage'], 'after': a[k]['damage'], 'ok': band(k, a[k]['damage'])}
    sps = [v['after'] for v in e['specials'].values() if not v['never_hits']]
    e['order_ok'] = (not e['fury'] or max(sps or [0]) < e['fury']['after']) and (not e['max'] or e['fury']['after'] < e['max']['after'])
    e['ok'] = all(v['ok'] for v in e['specials'].values()) and all(e[k]['ok'] for k in ('fury', 'max') if e[k]) and e['order_ok']
    if not e['ok']: bad.append(n)
    sp_b = ' '.join(f'{k} {v["before"]}' for k, v in e['specials'].items())
    sp_a = ' '.join(f'{k} {v["after"] if not v["never_hits"] else "-"}' for k, v in e['specials'].items())
    f = lambda k, w: str(e[k][w]) if e[k] else '-'
    rows.append(f'| {n} | {a["archetype"]} | {sp_b} | {sp_a} | {f("fury", "before")} | {f("fury", "after")} | '
                f'{f("max", "before")} | {f("max", "after")} | {"ok" if e["ok"] else "FAIL"} |')
md = [f'# Damage tiers (revamp phase 2): special {T["special"]} (+-{SP["special"]} %), fury {T["fury"]} (+-{SP["fury"]} %), '
      f'MAX {T["max"]} (+-{SP["max"]} %); chain totals fast 21 / balanced 23 / heavy 27; life 60', '',
      'Before = brawler 0.5.0 (a special x roster damage, a fury / MAX as captured; 0.5.0 played the MAX at any life). '
      'After = measured on this build (best of 6 distances, our emulator). "-" = the move never hits (no tier).', '',
      '| fighter | archetype | specials before | specials after | fury before | fury after | MAX before | MAX after | |',
      '|---|---|---|---|---|---|---|---|---|'] + rows + ['', 'ALL OK' if not bad else 'FAIL: ' + ' '.join(bad)]
os.makedirs(out, exist_ok=True)
open(os.path.join(out, 'damage_table.md'), 'w').write('\n'.join(md) + '\n')
json.dump(res, open(os.path.join(out, 'damage_table.json'), 'w'), indent=1)
print('\n'.join(md))
