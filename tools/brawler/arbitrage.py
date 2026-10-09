#!/usr/bin/env python3
"""The per-fighter ARBITRATION page's "now" data (the Brawler Lab's arbitrage.html?f=<fighter>, arbitrage.js): what the
game plays today in each slot of Bruno's A4 sheet (chain, alternate finishers, Blitz, air Blitz, specials, air specials,
air, grab, fury), as animation ids of the fighter's dictionary (animdict.py, review/<fighter>_anims.json, built first), read from game.json's
roster entry. The page pre-fills every slot with it, marked "now"; his picks replace it (decisions store, set
"<fighter>-arb").

    python3 tools/brawler/arbitrage.py OUT [GAME_DIR] [FIGHTER ...]   -> OUT/review/<fighter>_arb.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import build_tables

FIGHTERS = ('kim', 'krauser', 'robert')                     # the fighters with an animation dictionary (animdict.DICTS)
HOLD_HIT_DEFAULT = 'engine default: his fastest close normal'   # export_bm.HOLD_DEFAULT hit None (hold_move)
HOLD_FIN_DEFAULT = 'atk_d_close'                                 # export_bm.HOLD_DEFAULT fin


def generated(lab, n):
    """what the build's chain generator made for fighter n (build/chainlab.json: routes.chain_tree's summary, the
    specials' slots, the route tree's entries): the chain links, finishers {neutral, forward, up, down_move} as move
    names (a list: back to back; a special as its input), the dash entry's move. None without a build."""
    f = next((x for x in (lab or {}).get('fighters', []) if x['name'] == n), None)
    if not f or not (f['tree'].get('chain') or {}).get('links'): return None
    ch, sps = f['tree']['chain'], f.get('specials') or {}
    def move(v):
        v = v.rsplit(' (', 1)[0]                     # 'atk_d_far (launch)' -> 'atk_d_far'
        if v == 'throw': return None
        if v.startswith('special '): return sps.get(v[8:])
        ms = v.split(' > ')
        return ms if len(ms) > 1 else ms[0]
    fin = {('down_move' if k == 'down' else k): move(v) for k, v in ch['finishers'].items() if k != 'back'}
    return {'links': ch['links'], 'finishers': fin, 'dash': ((f['tree'].get('entries') or {}).get('dash') or {}).get('move')}


def now_of(r, D, chain_len, gen=None):
    """slot id -> {pieces: [hex, ...], text}: the roster entry r's moves as dictionary animations; what the roster does
    not name (a fighter on the default chain) from the build's generator (gen = generated())"""
    moves = r.get('moves') or {}
    def anims(name):
        if not name: return []
        if name.startswith('$'): return [name[1:].upper()] if name[1:].upper() in D else []
        if name in moves: return anims(moves[name])
        return [a['id'] for a in D.values() if name in (a.get('exported') or []) and a['status'] == 'ok']
    tags = {k[1:].upper(): v for k, v in (r.get('anim_specials') or {}).items()}
    def slot(names, text=''):
        names = names if isinstance(names, list) else [names]
        ps = [x for n in names for x in anims(n)]
        t = [text] if text else []
        t += [f'${p}: {tags[p]}' for p in ps if p in tags]
        if not ps and names and names[0] and not text: t.append(f'{names[0]} (no animation found)')
        return {'pieces': ps, 'text': '; '.join(t), 'moves': [n for n in names if n]}
    out = {}
    links = list((r.get('chain') or {}).get('links') or [])
    own = r.get('finishers') or {}
    gl = (gen or {}).get('links') or []
    gfin = (gen or {}).get('finishers') or {}
    fin = dict(own, **{k: gfin[k] for k in ('neutral', 'forward', 'up', 'down_move') if not own.get(k) and gfin.get(k)})
    pick = lambda k: '' if own.get(k) or not gfin.get(k) else 'the generator\'s pick'   # (the roster names none)
    gtxt = 'the generator\'s pick' if not links and gl else ''
    links = links or list(gl)
    seq = links + ([fin['neutral']] if fin.get('neutral') else [])
    for i in range(max(chain_len, len(seq))):
        out[f'a{i + 1}'] = slot(seq[i], gtxt if i < len(links) else '') if i < len(seq) else {'pieces': [], 'text': 'no link here today', 'moves': []}
    if fin.get('neutral'):
        last = out[f'a{len(seq)}']
        last['text'] = '; '.join(t for t in ('the neutral finisher', pick('neutral'), last['text']) if t)
    out['_presses'] = len(seq)
    la = fin.get('launcher')                        # the stick that plays the launcher
    j = lambda *t: ', '.join(x for x in t if x)
    out['fin_fwd'] = slot(fin.get('forward'), j('launcher' if la == 'forward' else '', pick('forward')) if fin.get('forward') else 'the generator\'s pick')
    out['fin_up'] = slot(fin.get('up'), j('launcher' if la == 'up' else '', pick('up')) if fin.get('up') else 'the generator\'s pick')
    dm = fin.get('down_move')
    out['fin_down'] = slot(dm, j({'sweep': 'sweep (trips)', 'slam': 'slam (bounces)'}.get(fin.get('down'), '') + (', back to back' if isinstance(dm, list) and len(dm) > 1 else ''), pick('down_move')))
    out['fin_df'] = {'pieces': [], 'text': 'empty', 'moves': []}
    out['fin_back'] = slot('throw_c', 'the throw')
    bz = r.get('blitz') or {'ff': 'dash'}
    for k in ('ff', 'dd', 'uu', 'du'):
        v = bz.get(k)
        dash = (gen or {}).get('dash')
        out['bz_' + k] = (slot(dash, 'his dash attack (the route tree\'s dash entry)') if dash else {'pieces': [], 'text': 'his dash attack (the route tree\'s dash entry)', 'moves': []}) if v == 'dash' else slot(v) if v else {'pieces': [], 'text': 'empty', 'moves': []}
    sp = r.get('specials') or {}
    out['sp_c'] = slot(sp.get('D'), 'also the combo breaker')
    out['sp_fc'] = slot(sp.get('fD'))
    out['sp_dc'] = slot(sp.get('dD'))
    air = dict(build_tables.AIR_DEFAULT, **(r.get('air') or {}))
    out['air_a'] = slot(air['forward'], '' if air['straight'] == air['forward'] else f"forward jump; straight jump + A = {air['straight']} ({', '.join('$' + x for x in anims(air['straight'])) or '?'})")
    out['air_da'] = slot(air['down'])
    asp = r.get('air_specials') or {}             # air Blitz = '<dd>A' entries, air specials = '<stick>C' (docs/brawler_data_model.md)
    for k in ('ff', 'dd', 'uu', 'du'):
        out['air_bz_' + k] = slot(asp[k + 'A']) if asp.get(k + 'A') else {'pieces': [], 'text': 'empty', 'moves': []}
    for k, key in (('c', 'C'), ('fc', 'fC'), ('dc', 'dC')):
        out['air_sp_' + k] = slot(asp[key]) if asp.get(key) else {'pieces': [], 'text': 'empty', 'moves': []}
    hold = (r.get('throws') or {}).get('hold') or {}
    out['grab_hit'] = slot(hold['hit']) if hold.get('hit') else {'pieces': [], 'text': HOLD_HIT_DEFAULT, 'moves': []}
    out['grab_fin'] = slot(hold.get('fin') or HOLD_FIN_DEFAULT, '' if hold.get('fin') else 'engine default')
    out['grab_fwd'] = slot('throw_c', 'the normal throw')
    out['grab_back'] = slot('throw_c', 'the normal throw, turned')
    out['fury'] = slot(r.get('fury'))
    out['max'] = slot(r['max']) if r.get('max') else {'pieces': [], 'text': 'the same fury (down + D in low life)', 'moves': []}
    return out


def build(out, game=None, names=None):
    game = game or os.path.join(REPO, 'examples', 'brawler')
    G = json.load(open(os.path.join(game, 'game.json')))
    lens = G['chain']['lengths']
    lp = os.path.join(game, 'build', 'chainlab.json')            # the build's generated chains (export_bm.py)
    lab = json.load(open(lp)) if os.path.exists(lp) else None
    res = {}
    for n in names or FIGHTERS:
        p = os.path.join(out, 'review', f'{n}_anims.json')
        if not os.path.exists(p): continue
        r = next(x for x in G['roster'] if x['name'] == n)
        A = json.load(open(p))
        D = {a['id']: a for a in A['anims']}
        arch = r.get('archetype', 'balanced')
        doc = {'fighter': n, 'display': A['display'], 'archetype': arch, 'chain_len': lens[arch],
               'version': open(os.path.join(game, 'VERSION')).read().strip(), 'now': now_of(r, D, lens[arch], generated(lab, n))}
        json.dump(doc, open(os.path.join(out, 'review', f'{n}_arb.json'), 'w'), ensure_ascii=False, indent=0)
        res[n] = doc
    return res


if __name__ == '__main__':
    for n, d in build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3:] or None).items():
        print(n, d['archetype'], json.dumps(d['now'], ensure_ascii=False))
