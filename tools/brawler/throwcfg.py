#!/usr/bin/env python3
"""The Brawler Factory's THROWS tab (/brawler-factory/?tab=throws, factory/throws.js): the throw events of every playable
fighter (game.json unlocks: starters + rungs) edited with no token, as the "throws" draft section (the feedback service
lab/throws, server.py throws_clean; docs/character_lab.md "The Factory's Throws"). The data model is build_tables
throw_events' (docs/brawler_data_model.md roster[].throws.events): per throw (forward | back | hold_b | run) 1-3 impacts
{frame, damage share %}, held, launch {frame, dir up | away | none, size small | medium | big}; frame 1 = the throw's
first frame.

    throwcfg.py state GAME                   what the game plays: every throw row, its events (or none), its length
    throwcfg.py merge GAME DRAFT.json [--dry-run]
                                             the draft {throws: {<fighter>-<fwd | back | holdb | run>: events}} checked
                                             against the game (build_tables' own checks + the throw's length) and written
                                             into game.json (only those fighters' "throws" / "special_grab_timing" fields;
                                             events replace throws.timing for that throw: one path): "throws: ..." change
                                             lines, "throws: no change", or REFUSED: <reason> (exit 1)
    throwcfg.py pull [OUT.json]              the live draft from the VPS (labcfg.py's ssh), for a dry run on the desktop

The ship service (labcfg.py ship-worker, SECTIONS "throws") runs `merge` for a ship with throws: true (the Factory's
"Ship throws to testers" / "Ship pending changes"), then builds, runs throw_regress.py (ALL OK) with the other checks,
and posts `state` to lab/throws_game after each ship."""
import datetime, json, math, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_tables as BT
from throw_answers import set_field

KEYS = {'fwd': 'forward', 'back': 'back', 'holdb': 'hold_b', 'run': 'run'}     # row id suffix -> throws.events key
LABEL = {'fwd': 'Forward', 'back': 'Back', 'holdb': 'Hold + B', 'run': 'Run grab'}
SCRIPT = {'fwd': 'throw_c', 'back': 'throw_d', 'holdb': 'throw_x'}
ROW_ID = re.compile(r'^([a-z0-9_]+)-(fwd|back|holdb|run)$')


def beta(g):
    u = g.get('unlocks') or {}
    return list(u.get('starters') or []) + [n for r in u.get('rungs') or [] for n in r] if u else [r['name'] for r in g['roster']]


def scripts(game, n):
    """the paired throws' scripts (throw_review.scripts: build/bm_chars.c), {} without a build"""
    try:
        import throw_review
        return throw_review.scripts(game, n)
    except (OSError, AttributeError, TypeError): return {}


def rows(game, g):
    """[(row id, fighter, suffix, events key, kind, grab special or None, length in frames or None)]"""
    out = []
    for n in beta(g):
        r = next((x for x in g['roster'] if x['name'] == n), None)
        if not r: continue
        t = r.get('throws') or {}
        sc = scripts(game, n)
        ks = ['fwd', 'back'] + (['holdb'] if t.get('b') or (t.get('extra') or {}).get('b') else []) + (['run'] if (t.get('run') or {}).get('special') else [])
        for s in ks:
            k = KEYS[s]; sp = BT.event_special(r, k)
            h = sc.get(SCRIPT.get(s)) if not sp else None
            if s == 'back' and (t.get('back') == 'throw_c' or not (h or {}).get('nrows')): h = sc.get('throw_c')   # (one throw: the C one played turned)
            ln = math.ceil(h['nrows'] * 256 / h['speed']) if h and h.get('speed') else None    # (8.8 rows a frame)
            out.append((f'{n}-{s}', n, s, k, 'special' if sp else 'paired', sp, ln))
    return out


def norm(e, w='throw'):
    """an events entry as the engine reads it (build_tables event_impacts / throw_events), for comparing"""
    if not e: return None
    imps = BT.event_impacts(e, w)
    L = e['launch']
    return {'impacts': [{'frame': x['frame'], **({'damage': x['damage']} if k + 1 < len(imps) else {}), **{f: x[f] for f in BT.IMPACT_FX}} for k, x in enumerate(imps)],
            'held': e.get('held', L['frame']), 'launch': {'frame': L['frame'], 'dir': L['dir'], 'size': L.get('size', 'medium')}}


def state(game):
    g = json.load(open(os.path.join(game, 'game.json')))
    out = []
    for rid, n, s, k, kind, sp, ln in rows(game, g):
        r = next(x for x in g['roster'] if x['name'] == n)
        t = r.get('throws') or {}
        e = (t.get('events') or {}).get(k)
        old = k in (t.get('timing') or {}) or bool(sp and sp in (r.get('special_grab_timing') or {}))
        out.append({'id': rid, 'fighter': n, 'display': r.get('display') or n.upper().replace('_', ' '), 'throw': s, 'key': k,
                    'label': LABEL[s] + (f' (special {sp})' if sp else ''), 'kind': kind, 'frames': ln,
                    'events': {x: y for x, y in e.items() if x not in ('from', 'about')} if e else None, 'timing': old})
    return {'version': open(os.path.join(game, 'VERSION')).read().strip(), 'rows': out,
            'launch': {d: g.get('throw_launch', {}).get(d) for d in ('up', 'away')}, 'max_impacts': BT.EVENT_IMPS}


def clean_entry(rid, e):
    """the page's entry -> the game.json entry (fields in the data model's order; defaults left out); raises ValueError"""
    if not isinstance(e, dict): raise ValueError(f'{rid}: {{impacts, held?, launch}}')
    I = e.get('impacts')
    if not isinstance(I, list) or not I: raise ValueError(f'{rid}: at least one impact')
    imps = []
    for k, x in enumerate(I):
        if not isinstance(x, dict) or 'frame' not in x: raise ValueError(f'{rid}: impact {k + 1}: {{frame, damage?}}')
        y = {'frame': x['frame']}
        if k + 1 < len(I) and x.get('damage'): y['damage'] = x['damage']        # (the last takes what is still due)
        for f in BT.IMPACT_FX:
            if x.get(f, True) is False: y[f] = False
        imps.append(y)
    out = {'impacts': imps}
    if e.get('held') is not None: out['held'] = e['held']
    L = e.get('launch') or {}
    out['launch'] = {'frame': L.get('frame'), 'dir': L.get('dir')}
    if L.get('size'): out['launch']['size'] = L['size']
    return out


def check(game, draft, who=''):
    """the draft against the game -> (the new game.json text or None, change lines); raises ValueError(reason)"""
    path = os.path.join(game, 'game.json')
    text = open(path).read(); g = json.loads(text)
    want = draft.get('throws') if isinstance(draft, dict) else None
    if not isinstance(want, dict): raise ValueError('the throws draft has no throws')
    R = {x[0]: x for x in rows(game, g)}
    out, ch, touched = text, [], {}
    stamp = f"the Factory's Throws tab {datetime.date.today()}" + (f" (draft rev {draft['rev']}" + (f" by {draft['by']}" if draft.get('by') else '') + ')' if draft.get('rev') else '')
    for rid in sorted(want):
        if rid not in R: raise ValueError(f'{rid}: no such throw in this game (the playable fighters: {", ".join(beta(g))})')
        _, n, s, k, kind, sp, ln = R[rid]
        r = next(x for x in g['roster'] if x['name'] == n)
        e = clean_entry(rid, want[rid])
        w = f'{n} {LABEL[s].lower()}'
        try: new = norm(e, w)
        except (AssertionError, KeyError, TypeError) as x: raise ValueError(str(x) or f'{w}: launch {{frame, dir, size?}}')
        top = ln or 400
        for x in [i['frame'] for i in new['impacts']] + [new['launch']['frame'], new['held']]:
            if not 1 <= x <= top: raise ValueError(f'{w}: frame {x} is outside the throw (frames 1-{top})')
        t = r.setdefault('throws', {})
        cur = (t.get('events') or {}).get(k)
        if cur and norm(cur) == new: continue
        e['from'] = stamp
        ev = t.setdefault('events', {}); ev[k] = e
        t['events'] = {x: ev[x] for x in BT.EVENT_KEYS if x in ev}
        if k in (t.get('timing') or {}):
            del t['timing'][k]
            if not t['timing']: del t['timing']
        if sp and sp in (r.get('special_grab_timing') or {}):
            del r['special_grab_timing'][sp]
            if not r['special_grab_timing']: del r['special_grab_timing']
            touched.setdefault(n, set()).add('special_grab_timing')
        touched.setdefault(n, set()).add('throws')
        try: BT.throw_events(r, g)                                 # the data model's own checks, on the result
        except AssertionError as x: raise ValueError(str(x))
        f = lambda v: 'I' + '+'.join(str(i['frame']) + (f" ({i['damage']} %)" if 'damage' in i else '') for i in v['impacts']) + \
            f" H{v['held']} L{v['launch']['frame']} {v['launch']['dir']} {v['launch']['size']}"
        ch.append(f'throws: {w} ' + (f'{f(norm(cur))} -> ' if cur else '(no events: the engine\'s rule) -> ') + f(new))
    for n, fields in touched.items():
        r = next(x for x in g['roster'] if x['name'] == n)
        for fl in sorted(fields): out = set_field(out, n, fl, r.get(fl))
    if json.loads(out) != g: raise ValueError('the patched game.json does not read back as the edited game')
    return (out if out != text else None), ch


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == 'state': return print(json.dumps(state(a[1]), ensure_ascii=False))
    if len(a) in (3, 4) and a[0] == 'merge' and (len(a) == 3 or a[3] == '--dry-run'):
        try: new, ch = check(a[1], json.load(open(a[2])))
        except ValueError as e: print('REFUSED:', e); sys.exit(1)
        if new and len(a) == 3: open(os.path.join(a[1], 'game.json'), 'w').write(new)
        print('\n'.join(ch) or 'throws: no change')
        return
    if a[:1] == ['pull'] and len(a) <= 2:
        import labcfg
        d = labcfg.api('throws').get('draft') or {}
        s = json.dumps(d, indent=1, ensure_ascii=False)
        if len(a) == 2: open(a[1], 'w').write(s + '\n')
        return print(s)
    sys.exit(__doc__)


if __name__ == '__main__':
    main()
