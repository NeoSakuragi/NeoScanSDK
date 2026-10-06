#!/usr/bin/env python3
"""A Kizuna fighter's proposed brawler slots and starter routes (TODO #77: NOT in game.json, Bruno picks who goes in):

    python3 picks_kz.py NAME     -> tools/kizuna/picks/NAME.json (the six A+B slots + the C fury, game.json roster
                                    'specials' / 'fury' form), tools/brawler/routes/NAME.json (routes v4, Kim's layout)

Slots from what each special does in its captures (catalogue_kz: the whiff with P2 walked away, the far capture with P2
standing 160 px off): C fury = its life <= 96 desperation of condition bit 14 (6246A for most); up = its other
desperation move (bit 10, 421A); A+B (D) = a move that hits P2 160 px off without travelling there (a projectile or a
long reach), else its first special; forward = the longest travel staying low; down = the highest rise; down-forward /
up-forward = the remaining ones in command-list order (the tag-in strike, bit 6, last). Kim's own picks (game.json)
follow the same rule.
Routes: Kim's tree (routes/kim.json) for this fighter's normals and Kizuna's measured rules (cancels_kz: which normals
cancel into which special; the chain close A > B > C of its capture): a chain step is kept when its capture plays it,
a special ending is added where the normal before it cancels into that special."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import fighters_kz as FK, commands_kz
ROUTES = os.path.join(HERE, '..', 'brawler', 'routes')
PICKS = os.path.join(HERE, 'picks')
SLOT_IN = {'D': 'AB', 'fD': 'fAB', 'dD': 'dAB', 'uD': 'uAB', 'dfD': 'dfAB', 'ufD': 'ufAB'}

def picks(name):
    ch = FK.CAST[name]
    cat = json.load(open(FK.path(name, 'moves'))); mv = cat['moves']
    plan = json.load(open(FK.path(name, 'follow')))
    cond = {}
    for c in commands_kz.commands(ch): cond.setdefault(c['notation'], c['cond'])
    sp = list(plan['specials'])
    def m(n, kind):
        low = '_low' if f'sw_{n}_low' in mv else ''
        return mv.get(f'sw_{n}{low}' if kind == 'w' else f'cmd_{n}{low}') or {}
    fury = next((n for n in sp if cond[n] & 0x4000), None)
    up = next((n for n in sp if cond[n] & 0x0400 and n != fury), None)
    rest = [n for n in sp if n not in (fury, up)]
    rest.sort(key=lambda n: bool(cond[n] & 0x40))                   # the tag-in strike last
    out = {'uD': up}
    def take(n): rest.remove(n); return n
    reach = [n for n in rest if m(n, 'f').get('hits') and abs(m(n, 'w').get('dx', 0)) < 60]
    out['D'] = take(reach[0]) if reach else (take(rest[0]) if rest else None)
    rush = sorted((n for n in rest if m(n, 'w').get('dx', 0) >= 60 and m(n, 'w').get('height', 0) <= 30), key=lambda n: -m(n, 'w')['dx'])
    out['fD'] = take(rush[0]) if rush else None
    rise = sorted((n for n in rest if m(n, 'w').get('height', 0) >= 25), key=lambda n: -m(n, 'w')['height'])
    out['dD'] = take(rise[0]) if rise else None
    for k in ('fD', 'dD', 'uD', 'dfD', 'ufD'):
        if out.get(k) is None: out[k] = take(rest[0]) if rest else None
    return {'specials': {k: out[k] for k in ('D', 'fD', 'dD', 'uD', 'dfD', 'ufD')}, 'fury': fury,
            'why': {n: {'whiff_dx': m(n, 'w').get('dx'), 'whiff_height': m(n, 'w').get('height'), 'far_hits': len(m(n, 'f').get('hits') or []),
                        'cond': f'{cond[n]:04X}', 'parts': len(plan['follow'][n]['parts']) if n in plan['follow'] else 1} for n in sp},
            'not_used': [n for n in sp if n not in out.values() and n != fury]}

def routes(name, pk):
    ch = FK.CAST[name]
    cat = json.load(open(FK.path(name, 'moves')))['moves']
    canc = json.load(open(FK.path(name, 'cancels')))
    ka = lambda n: f'{FK.kim_anim(ch, n):X}'
    slot = {v: k for k, v in pk['specials'].items() if v}
    def end(normal):                                     # a special this normal cancels into, as a route node
        for k, v in canc.items():
            nm, fu = k.split('>')
            if nm == normal and v['cancel'] and fu in slot: return {'special': slot[fu], 'input': SLOT_IN[slot[fu]]}
    def chain(rec, anims): return all(a in cat.get(rec, {}).get('anims', []) for a in anims)
    L = lambda mv, inp, w='light', e='none': {'move': mv, 'weight': w, 'effect': e, 'input': inp}
    R = []
    if chain('chain_abc', [ka(0x48), ka(0x52), ka(0x5B)]):
        R.append([L('atk_a_close', 'cA'), L('atk_b_close', 'A'), L('atk_c_close', 'A', 'strong', 'knockdown')])
    elif chain('chain_ac', [ka(0x48), ka(0x5B)]):
        R.append([L('atk_a_close', 'cA'), L('atk_c_close', 'A', 'strong', 'knockdown')])
    for nm, mv_, prev in (('close_b', 'atk_b_close', [L('atk_a_close', 'cA')]), ('close_c', 'atk_c_close', [L('atk_a_close', 'cA')]),
                          ('far_b', 'atk_b_far', []), ('crouch_c', 'atk_c_crouch', [L('atk_a_crouch', 'dA')])):
        e = end(nm)
        if e: R.append(prev + [L(mv_, 'A' if prev else ('A' if 'far' in nm else 'cA'), 'strong' if mv_.startswith('atk_c') else 'light'), e])
    R.append([L('atk_a_close', 'cA'), L('atk_c_jump', 'B', 'strong'), L('atk_cd_jump', 'A', 'strong', 'knockdown')])
    R.append([L('atk_b_far', 'A'), L('atk_c_far', 'A', 'strong', 'knockdown')] if chain('chain_bc', [ka(0x52), ka(0x5B)]) else [L('atk_b_far', 'A')])
    R.append([L('atk_a_crouch', 'dA'), L('atk_b_crouch', 'dA'), L('atk_d_crouch', 'dA', 'strong', 'trip')])
    R += [[L('cmd_fwd_b', 'fA', 'strong', 'knockdown')], [L('cmd_df_c', 'dfA', 'light', 'trip')], [L('atk_d_far', 'bA', 'strong', 'knockdown')]]
    # one tree (routes.py): the same inputs must lead to the same hit; a route that parts from another on an input
    # another one already took gets the next free one of fA / dA / bA there, else it is left out
    seen, out = {}, []
    for r in R:
        r = [dict(x) for x in r]; ok = True
        for j, x in enumerate(r):
            key = tuple(y['input'] for y in r[:j + 1]); what = x.get('move') or 'sp ' + x['special']
            if seen.get(key, what) != what:
                for alt in ('fA', 'dA', 'bA'):
                    k2 = key[:-1] + (alt,)
                    if seen.get(k2, what) == what and 'move' in x: x['input'] = alt; key = k2; break
                else: ok = False; break
        if not ok: continue
        for j, x in enumerate(r): seen[tuple(y['input'] for y in r[:j + 1])] = x.get('move') or 'sp ' + x['special']
        out.append(r)
    R = out
    return {'fighter': name,
            'note': f"{FK.NAMES[ch]}'s starter routes (TODO #77, tree v4; not in the build): Kim's tree for his normals, chain steps kept where "
                    "Kizuna's capture plays them (close A > B > C), special endings where Kizuna cancels that normal into the special "
                    "(tools/kizuna/cancels_kz.py), the slots of tools/kizuna/picks. For Bruno to rearrange in the Chain Lab.",
            'routes': R}

if __name__ == '__main__':
    name = sys.argv[1]
    pk = picks(name)
    os.makedirs(PICKS, exist_ok=True)
    json.dump({'fighter': name, 'bank': f'kizuna:{name}', **pk}, open(os.path.join(PICKS, f'{name}.json'), 'w'), indent=1)
    rt = routes(name, pk)
    with open(os.path.join(ROUTES, f'{name}.json'), 'w') as f:
        f.write('{\n "fighter": ' + json.dumps(rt['fighter']) + ',\n "note": ' + json.dumps(rt['note'], ensure_ascii=False) + ',\n "routes": [\n'
                + ',\n'.join('  ' + json.dumps(r) for r in rt['routes']) + '\n ]\n}\n')
    print(name, pk['specials'], 'fury', pk['fury'], 'unused', pk['not_used'], '|', len(rt['routes']), 'routes')
