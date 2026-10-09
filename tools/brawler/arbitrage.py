#!/usr/bin/env python3
"""The per-fighter ARBITRATION page's "now" data (the Brawler Lab's arbitrage.html?f=<fighter>, arbitrage.js): what the
game plays today in each slot of Bruno's A4 sheet (chain, alternate finishers, Blitz, specials, air, grab, fury), as
animation ids of the fighter's dictionary (animdict.py, review/<fighter>_anims.json, built first), read from game.json's
roster entry. The page pre-fills every slot with it, marked "now"; his picks replace it (decisions store, set
"<fighter>-arb").

    python3 tools/brawler/arbitrage.py OUT [GAME_DIR] [FIGHTER ...]   -> OUT/review/<fighter>_arb.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import build_tables

FIGHTERS = ('kim', 'krauser')                       # the fighters with an animation dictionary (animdict.DICTS)
HOLD_HIT_DEFAULT = 'engine default: his fastest close normal'   # export_bm.HOLD_DEFAULT hit None (hold_move)
HOLD_FIN_DEFAULT = 'atk_d_close'                                 # export_bm.HOLD_DEFAULT fin


def now_of(r, D, chain_len):
    """slot id -> {pieces: [hex, ...], text}: the roster entry r's moves as dictionary animations"""
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
    fin = r.get('finishers') or {}
    seq = links + ([fin['neutral']] if fin.get('neutral') else [])
    for i in range(max(chain_len, len(seq))):
        out[f'a{i + 1}'] = slot(seq[i]) if i < len(seq) else {'pieces': [], 'text': 'no link here today', 'moves': []}
    if fin.get('neutral'):
        last = out[f'a{len(seq)}']
        last['text'] = '; '.join(t for t in ('the neutral finisher', last['text']) if t)
    out['_presses'] = len(seq)
    la = fin.get('launcher')                        # the stick that plays the launcher
    out['fin_fwd'] = slot(fin.get('forward'), 'launcher' if la == 'forward' else '' if fin.get('forward') else 'the generator\'s pick')
    out['fin_up'] = slot(fin.get('up'), 'launcher' if la == 'up' else '' if fin.get('up') else 'the generator\'s pick')
    dm = fin.get('down_move')
    out['fin_down'] = slot(dm, {'sweep': 'sweep (trips)', 'slam': 'slam (bounces)'}.get(fin.get('down'), '') + (', back to back' if isinstance(dm, list) and len(dm) > 1 else ''))
    out['fin_back'] = slot('throw_c', 'the throw')
    bz = r.get('blitz') or {'ff': 'dash'}
    for k in ('ff', 'dd', 'uu', 'du'):
        v = bz.get(k)
        out['bz_' + k] = {'pieces': [], 'text': 'his dash attack (the route tree\'s dash entry)', 'moves': []} if v == 'dash' else slot(v) if v else {'pieces': [], 'text': 'empty', 'moves': []}
    sp = r.get('specials') or {}
    out['sp_c'] = slot(sp.get('D'), 'also the combo breaker')
    out['sp_fc'] = slot(sp.get('fD'))
    out['sp_dc'] = slot(sp.get('dD'))
    air = dict(build_tables.AIR_DEFAULT, **(r.get('air') or {}))
    out['air_a'] = slot(air['forward'], '' if air['straight'] == air['forward'] else f"forward jump; straight jump + A = {air['straight']} ({', '.join('$' + x for x in anims(air['straight'])) or '?'})")
    out['air_da'] = slot(air['down'])
    asp = (r.get('air_specials') or {}).get('ddA')
    out['air_dda'] = slot(asp) if asp else {'pieces': [], 'text': 'empty', 'moves': []}
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
    res = {}
    for n in names or FIGHTERS:
        p = os.path.join(out, 'review', f'{n}_anims.json')
        if not os.path.exists(p): continue
        r = next(x for x in G['roster'] if x['name'] == n)
        A = json.load(open(p))
        D = {a['id']: a for a in A['anims']}
        arch = r.get('archetype', 'balanced')
        doc = {'fighter': n, 'display': A['display'], 'archetype': arch, 'chain_len': lens[arch],
               'version': open(os.path.join(game, 'VERSION')).read().strip(), 'now': now_of(r, D, lens[arch])}
        json.dump(doc, open(os.path.join(out, 'review', f'{n}_arb.json'), 'w'), ensure_ascii=False, indent=0)
        res[n] = doc
    return res


if __name__ == '__main__':
    for n, d in build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3:] or None).items():
        print(n, d['archetype'], json.dumps(d['now'], ensure_ascii=False))
