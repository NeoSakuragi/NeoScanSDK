#!/usr/bin/env python3
"""specials.json -> the per-special A / B / C / D parameter sets side by side (markdown), for the README.
Per button: anim | ROM: header vx / vy (px/f, art faces left: negative = forward), level bits, ROM frames,
damage vs Jimmy (table x 18) | measured: frames to idle, hits, total damage, dx / rise (px)."""
import json, dd
D = json.load(open('/data/neogeo_dict/doubledr/specials.json'))

def cell(v):
    if not v: return '-'
    if 'rom' not in v:
        if not v.get('triggered'): return 'n/t'
        return f"throw: {v['frames']}f {len(v['hits'])}h {v['damage']}"
    r = v['rom'][0]
    vel = ' / '.join(f"{p['vx']:+g},{p['vy']:+g}" for p in v['rom'] if p['vx'] or p['vy']) or '0'
    chain = '>'.join(str(p['anim']) for p in v['rom'])
    rom = f"a{chain} L{max(p['level'] for p in v['rom'])} v {vel} {sum(p['frames'] for p in v['rom'])}f"
    if not v.get('triggered'): return rom + ' / n/t'
    return f"{rom} / {v['frames']}f {len(v['hits'])}h {v['damage']} dx{v['dx']} up{v['rise']}"

out = []
for ch, d in D.items():
    out.append(f"\n**{d['name']}** (ch {ch})\n\n| input | A | B | C | D |\n|---|---|---|---|---|")
    for e in d['entries']:
        if e['flags'] & 4:
            v = e['variants'].get('A'); out.append(f"| {e['notation']} SUPER (A+B, powered) | {cell(v)} | same | same | same |"); continue
        out.append(f"| {e['notation']}{' (mash)' if e['flags'] & 2 else ''} | " + ' | '.join(cell(e['variants'].get(b)) for b in 'ABCD') + ' |')
open('/data/neogeo_dict/doubledr/specials_table.md', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
