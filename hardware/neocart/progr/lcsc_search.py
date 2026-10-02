#!/usr/bin/env python3
"""Search JLCPCB's parts library: lcsc_search.py "keyword" [n]  -> code, mfr part, package, lib type, stock, price breaks."""
import json, subprocess, sys
URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
kw = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
out = subprocess.run(['curl', '-s', '-m', '30', '-X', 'POST', URL, '-H', 'Content-Type: application/json', '-H', 'User-Agent: Mozilla/5.0',
                      '-d', json.dumps({"keyword": kw, "pageSize": n, "pageNum": 1})], capture_output=True, text=True).stdout
lst = ((json.loads(out or '{}').get('data') or {}).get('componentPageInfo') or {}).get('list') or []
for p in lst:
    pr = [(x['startNumber'], x['productPrice']) for x in (p.get('componentPrices') or [])][:3]
    print(f"{p.get('componentCode'):<10} {str(p.get('componentModelEn'))[:28]:<28} {str(p.get('componentSpecificationEn'))[:30]:<30} {p.get('componentLibraryType'):<7} stock {p.get('stockCount'):<7} {pr}")
