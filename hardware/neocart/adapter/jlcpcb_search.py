#!/usr/bin/env python3
"""Search JLCPCB parts database via their API."""
import json, urllib.request, sys

def search(keyword, size=20):
    url = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
    data = json.dumps({"keyword": keyword, "pageSize": size, "pageNum": 1}).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

if __name__ == "__main__":
    keyword = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "74HC165 SOIC-16"
    results = search(keyword)
    parts = results.get('data', {}).get('componentPageInfo', {}).get('list', [])

    for p in parts:
        stock = p.get('stockCount', 0)
        if stock == 0: continue
        code = p.get('componentCode', '')
        model = p.get('componentModelEn', '')[:35]
        spec = p.get('componentSpecificationEn', '')[:25]
        prices = p.get('componentPrices', [{}])
        price = prices[0].get('productPrice', 0) if prices else 0
        desc = p.get('describe', '')[:60]
        lib = p.get('componentLibraryType', '')
        print(f"{code:<14} ${price:<8.4f} stock:{stock:<6} {lib:<8} {model}")
        print(f"  {desc}")
