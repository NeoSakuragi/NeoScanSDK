#!/usr/bin/env python3
"""The fighter export's palette packer (TODO #201): a fighter whose frames use more palettes than the game loads
(fighter.h MAX_PALS: a part past them is drawn with the next fighter's colours, KOF98 Rugal 11) gets them folded, with
the exact colours, into at most MAX_PALS. export_bm.build runs it on every export (KOF94-99, SS4, WHP, Kizuna, DD; SS2
folds its own: export_ss2.pack_palettes) before the tiles are placed; a fighter already inside the budget is untouched.

The rule. A palette's colour = its 16 words in every colour set (a tuple: KOF98 has four sets). Palettes with the same
colours in every set are one (TODO #198, export_bm.pal_slots). A palette folds into a host when the colours its tiles'
pens use, together with the host's, number at most 15 (pen 0 is transparent): a pen whose colour the host already
uses maps to that pen, any other keeps its number when the host leaves it unused, else takes the lowest unused one.
The folded palette's tiles are copied with their pens renumbered (only when a pen moves; a tile shared with another
palette keeps its original); its parts take the host's palette; the host's unused pens take the folded colours. Every
pixel shows the colour it showed before, in every colour set (proof: pal201_proof.py pixels). The packing is an exact
search (fewest copied tiles among the partitions into at most MAX_PALS groups, branch and bound); the body palette (the
export's first used palette: an enemy's custom palette and its tint replace slot 0, fighter.c fighter_src_pal), a flash
pose's palette and a flicker palette (SS2) never fold. What does not fit is reported, frames and palettes.

    python3 pal_pack.py BUILD_DIR       every fighter export in BUILD_DIR/tmp_*: palettes used, slots, packed slots"""
import json, os, sys
import numpy as np

PENS = 15                                               # pens 1-15 (0 = transparent)

def tile_pens(raw):
    """the pens of a 128-byte C tile as the export holds it (C1 / C2 bytes interleaved: groups of 4 bytes x 8 pixels,
    the bytes hold pen bits 0, 2, 1, 3; neo2.tile) -> 256 pens in that byte order"""
    out = []
    for g in range(0, 128, 4):
        b0, b2, b1, b3 = raw[g:g + 4]
        out += [(b0 >> i & 1) | (b1 >> i & 1) << 1 | (b2 >> i & 1) << 2 | (b3 >> i & 1) << 3 for i in range(8)]
    return out

def tile_recolour(raw, m):
    """the tile with pen q drawn as pen m[q] (pens not in m unchanged)"""
    pens = tile_pens(raw); out = bytearray(128)
    for g in range(32):
        for i in range(8):
            q = pens[g * 8 + i]; q = m.get(q, q)
            out[g * 4] |= (q & 1) << i; out[g * 4 + 1] |= (q >> 2 & 1) << i
            out[g * 4 + 2] |= (q >> 1 & 1) << i; out[g * 4 + 3] |= (q >> 3 & 1) << i
    return bytes(out)

def load_region(tmp):
    """the export's C tiles (kof95_c1 / c2.bin) as one bytearray, 128 bytes a tile"""
    c1 = open(os.path.join(tmp, 'kof95_c1.bin'), 'rb').read(); c2 = open(os.path.join(tmp, 'kof95_c2.bin'), 'rb').read()
    reg = bytearray(len(c1) * 2); reg[0::2] = c1; reg[1::2] = c2
    return reg

def save_region(tmp, reg):
    open(os.path.join(tmp, 'kof95_c1.bin'), 'wb').write(bytes(reg[0::2]))
    open(os.path.join(tmp, 'kof95_c2.bin'), 'wb').write(bytes(reg[1::2]))

def pen_set(reg, t):
    """the pens (1-15) tile t uses"""
    b = np.frombuffer(bytes(reg[t * 128:(t + 1) * 128]), np.uint8).reshape(32, 4)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, 0] | bits[:, 2] << 1 | bits[:, 1] << 2 | bits[:, 3] << 3
    return {int(q) for q in np.unique(pen) if q}

def own_parts(fr):
    """a frame's parts drawn with the fighter's palettes: a part of KOF's shared effects bank ('spal', TODO #214) has an
    absolute palette of the shared budget (export_bm SFX_PAL), never folded"""
    return [p for p in fr['parts'] if 'spal' not in p]

def usage(ch, reg):
    """{palette: (pens its parts' tiles use, tiles, frames)}"""
    use, pens_of = {}, {}
    for fi, fr in enumerate(ch['frames']):
        for p in own_parts(fr):
            k = p.get('pal', 0); u = use.setdefault(k, (set(), set(), set())); u[2].add(fi)
            for col in p['tiles']:
                for t in col:
                    if not t: continue
                    if t not in pens_of: pens_of[t] = pen_set(reg, t)
                    u[0].update(pens_of[t]); u[1].add(t)
    return use

def slots(used, sets):
    """the identical-colour slots (export_bm.pal_slots' rule): [export palettes of slot 0, of slot 1, ...]"""
    keys, out = [], []
    for k in used:
        j = next((j for j, q in enumerate(keys) if all(st[q] == st[k] for st in sets)), None)
        if j is None: keys.append(k); out.append([k])
        else: out[j].append(k)
    return out

def colour(sets, k, q): return tuple(st[k][q] for st in sets)

def fold_group(group, use, sets):
    """a group's packing: host = group[0] keeps its pens; each other palette in order maps its pens (see the rule) ->
    (pen maps {palette: {q: r}}, the host's pens {r: colour}) or None when more than 15 colours"""
    host = group[0]
    taken = {q: colour(sets, host, q) for q in use[host][0]}
    maps = {}
    for k in group[1:]:
        m = {}
        for q in sorted(use[k][0]):
            c = colour(sets, k, q)
            same = next((r for r, cr in taken.items() if cr == c), None)
            if same is not None: m[q] = same; continue
            if q not in taken: m[q] = q; taken[q] = c; continue
            free = next((r for r in range(1, PENS + 1) if r not in taken), None)
            if free is None: return None
            m[q] = free; taken[free] = c
        maps[k] = m
    return maps, taken

def group_cost(group, use, sets):
    """tiles copied by a group's best host order (any of its palettes as the host), or None: (cost, ordered group)"""
    best = None
    for h in group:
        order = [h] + [k for k in group if k != h]
        r = fold_group(order, use, sets)
        if r is None: continue
        cost = sum(len(use[k][1]) for k, m in r[0].items() if any(q != v for q, v in m.items()))
        if best is None or cost < best[0]: best = (cost, order)
    return best

def plan(items, use, sets, limit, fixed):
    """the partition of `items` (one export palette per slot) into at most `limit` groups, each fitting 15 colours,
    with the fewest copied tiles; `fixed` items stay alone -> [ordered group, ...] or None"""
    cols = {k: {colour(sets, k, q) for q in use[k][0]} for k in items}
    order = sorted(items, key=lambda k: (k not in fixed, -len(cols[k]), k))
    best = [None, None]
    def dfs(i, groups, gcols):
        if len(groups) > limit: return
        if best[0] is not None and sum(c for c, _ in groups) >= best[0]: return
        if i == len(order):
            best[0] = sum(c for c, _ in groups); best[1] = [g for _, g in groups]; return
        k = order[i]
        if k not in fixed:
            for j, (c, g) in enumerate(groups):
                if g[0] in fixed or len(gcols[j] | cols[k]) > PENS: continue
                r = group_cost(g + [k], use, sets)
                if r is None: continue
                groups[j] = (r[0], r[1]); gc = gcols[j]; gcols[j] = gc | cols[k]
                dfs(i + 1, groups, gcols)
                groups[j] = (c, g); gcols[j] = gc
        if len(groups) < limit:
            groups.append((0, [k])); gcols.append(cols[k])
            dfs(i + 1, groups, gcols)
            groups.pop(); gcols.pop()
    dfs(0, [], [])
    return best[1]

def pack(name, ch, tmp, limit, n_tiles, tile_base):
    """fold the export's palettes (ch: its character entry, tmp: its dir) to at most `limit` slots; rewrites the parts'
    palettes, the host colours (ch['block_palettes']) and appends the recoloured tiles to tmp's C files ->
    {'name', 'used', 'slots', 'packed', 'tiles_added', 'groups', 'over': {palette: frames} when it still does not fit}"""
    sets = ch['block_palettes']
    used = sorted({p.get('pal', 0) for fr in ch['frames'] for p in own_parts(fr)}) or [0]
    sl = slots(used, sets)
    res = {'name': name, 'used': len(used), 'slots': len(sl), 'packed': len(sl), 'tiles_added': 0, 'groups': []}
    if len(sl) <= limit: return res, n_tiles
    rep = {k: g[0] for g in sl for k in g}                     # identical palettes: their slot's first
    for fr in ch['frames']:
        for p in own_parts(fr): p['pal'] = rep[p.get('pal', 0)]
    reg = load_region(tmp)
    assert len(reg) >= 128 * (tile_base + n_tiles), (name, len(reg) // 128, tile_base + n_tiles)
    del reg[128 * (tile_base + n_tiles):]                      # (export_bm.build copies the tiles up to there)
    use = usage(ch, reg)
    items = [g[0] for g in sl]
    fixed = {items[0]}                                         # the body palette, a flash pose's, a flicker palette
    for extra in (ch.get('flash_pal'), *(ch.get('flicker') or [])):
        if extra: fixed.add(rep.get(extra['index'], extra['index']))
    for extra in (ch.get('flash_pal'), *(ch.get('flicker') or [])):   # (their parts now name the slot's first)
        if extra: extra['index'] = rep.get(extra['index'], extra['index'])
    groups = plan(items, use, sets, limit, fixed)
    if groups is None:                                          # what does not fit: every slot's frames
        res['over'] = {k: sorted(use[k][2]) for k in items}
        return res, n_tiles
    for g in groups:
        if len(g) == 1: continue
        maps, taken = fold_group(g, use, sets)
        host = g[0]
        for r, c in taken.items():                              # the host's pens take the folded colours
            for s, st in enumerate(sets): st[host][r] = c[s]
        for k, m in maps.items():
            moved = any(q != r for q, r in m.items())
            cache = {}
            def copy(t):
                if not t or not moved: return t
                if t not in cache:
                    cache[t] = tile_base + n_tiles + res['tiles_added']; res['tiles_added'] += 1
                    reg.extend(tile_recolour(reg[t * 128:(t + 1) * 128], m))
                return cache[t]
            for fr in ch['frames']:
                for p in own_parts(fr):
                    if p['pal'] != k: continue
                    p['tiles'] = [[copy(t) for t in col] for col in p['tiles']]
                    p['pal'] = host
        res['groups'].append({'host': host, 'folded': {k: {str(q): r for q, r in m.items()} for k, m in maps.items()}})
    assert len(reg) == 128 * (tile_base + n_tiles + res['tiles_added'])
    save_region(tmp, reg)
    res['packed'] = len(groups)
    return res, n_tiles + res['tiles_added']

if __name__ == '__main__':
    import glob
    for d in sorted(glob.glob(os.path.join(sys.argv[1], 'tmp_*'))):
        ex = json.load(open(os.path.join(d, 'kof95_export.json')))
        for n, ch in ex['characters'].items():
            reg = load_region(d); use = usage(ch, reg); used = sorted(use)
            print(f'{os.path.basename(d)[4:]:24s} palettes used {len(used):2d}, slots {len(slots(used, ch["block_palettes"])):2d}')
