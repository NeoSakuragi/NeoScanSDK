#!/usr/bin/env python3
"""Live JLCPCB part prices for the v2 BOM at several board quantities (parts only; board and fees are quoted separately)."""
import importlib.util, json, os, subprocess, time
from collections import Counter
HERE = os.path.abspath(os.environ.get('PRICE_DIR', os.path.dirname(os.path.abspath(__file__))))   # PRICE_DIR: any board folder with a design.py
spec = importlib.util.spec_from_file_location('design', os.path.join(HERE, 'design.py')); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
need = Counter(); val = {}
for r, pt in d.PARTS.items():
    if pt['lcsc'] and not r.startswith('JP') and r != 'J1': need[pt['lcsc']] += 1; val[pt['lcsc']] = pt['value']
info = {}
for code in need:
    out = subprocess.run(['curl', '-s', '-m', '30', '-X', 'POST', URL, '-H', 'Content-Type: application/json', '-H', 'User-Agent: Mozilla/5.0',
                          '-d', json.dumps({"keyword": code, "pageSize": 5, "pageNum": 1})], capture_output=True, text=True).stdout
    lst = ((json.loads(out or '{}').get('data') or {}).get('componentPageInfo') or {}).get('list') or []
    p = next((x for x in lst if x.get('componentCode') == code), None)
    info[code] = dict(stock=p.get('stockCount'), lib=p.get('componentLibraryType'), prices=[(x['startNumber'], x['productPrice']) for x in p.get('componentPrices') or []]) if p else None
    time.sleep(0.2)
def unit(code, qty):
    pr = info[code]['prices']; best = pr[0][1]
    for start, price in pr:
        if qty >= start: best = price
    return best
res = {'parts': {}, 'per_board': {}}
for code, n in need.items():
    res['parts'][code] = dict(value=val[code], per_board=n, **info[code])
for boards in (5, 30, 100):
    tot = 0.0
    for code, n in need.items():
        q = n * boards; tot += unit(code, q) * q
    res['per_board'][boards] = round(tot / boards, 2)
res['extended_unique'] = sorted(val[c] for c in need if info[c]['lib'] != 'base')
res['basic_unique'] = sorted(val[c] for c in need if info[c]['lib'] == 'base')
res['placements_per_board'] = sum(need.values())
res['joints_per_board'] = sum(len(pads) for pads in [[p for net, lst in d.NETS.items() for r, p in lst if r == ref] for ref in d.PARTS if d.PARTS[ref]['lcsc'] and not ref.startswith('JP') and ref != 'J1'])
json.dump(res, open(os.path.join(HERE, 'out', 'bom_prices.json'), 'w'), indent=1)
for code, p in res['parts'].items(): print(f"{p['value']:<16} {code:<9} x{p['per_board']:<3} {p['lib']:<7} stock {p['stock']:<7} {p['prices'][:3]}")
print('parts per board:', res['per_board'], '| placements', res['placements_per_board'], '| joints', res['joints_per_board'])
print('extended:', res['extended_unique']); print('basic:', res['basic_unique'])
