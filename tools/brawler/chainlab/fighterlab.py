#!/usr/bin/env python3
"""The FIGHTER LAB's cast data (lab.html, fighterlab.js; Bruno 2026-10-10: "one page for the whole cast: pick a character,
then Info, Workshop, Assembly", one template for every fighter). From game.json's roster and what the site already holds
(make_site.py's output: review/<f>_anims.json from animdict.py, review/<f>_workshop.json from workshop.py,
review/<f>_arb.json from arbitrage.py, review/<f>.json from review_build.py), it writes:

  OUT/cast.json        {version, built, engines (the source games with a dictionary builder), fighters: [one per roster
                        fighter, roster order: name, display, bank, game, scale, archetype, chain length, music theme,
                        face / win portrait URLs, what the site has for him (dictionary, workshop counts, knobs, sheet,
                        review, Lab build), the engine note when his game is not decoded]}
  OUT/faces/<f>.png    his HUD portrait exactly as the game draws it (labpub.hud_face: make_hud.portrait, x4)
  OUT/faces/<f>_win.png  his big portrait (the drama / win screens: roster win_portrait, else game.json portraits ->
                        /data/neogeo_dict/portraits/big_<bank>.png) when there is one

What changes live (the pack in the catalogue, the live config revision) the page reads from the server itself.
Re-runnable on a built site: python3 fighterlab.py OUT [GAME_DIR]   (make_site.py runs it last)."""
import datetime, json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness

PORTRAITS = '/data/neogeo_dict/portraits/'
GAME_NAMES = {'kof94': 'The King of Fighters \'94', 'kof95': 'The King of Fighters \'95', 'kof96': 'The King of Fighters \'96',
              'kof98': 'The King of Fighters \'98', 'kof99': 'The King of Fighters \'99', 'kizuna': 'Kizuna Encounter',
              'samsho2': 'Samurai Shodown II', 'samsho4': 'Samurai Shodown IV', 'whp': 'World Heroes Perfect',
              'doubledr': 'Double Dragon (Neo Geo)'}


def jload(p):
    try: return json.load(open(p))
    except (OSError, ValueError): return None


def theme(G, songs, r):
    """his music theme: roster[].music when set, else the songs.json THEME_* that names him (THEME_<NAME>, or a shared
    THEME_RYO_ROBERT; never another roster fighter's own: THEME_HANZO_SS2 is not WHP Hanzo's)"""
    if r.get('music'):
        m = r['music']; s = next((s for s in songs if s['name'] == m), None) if isinstance(m, str) else None
        return dict(name=m, **({k: s[k] for k in ('source', 'cmd', 'what') if k in s} if s else {}), set_in='roster') if isinstance(m, str) else m
    key = r['name'].upper(); others = {x['name'].upper() for x in G['roster']} - {key}
    th = [s for s in songs if s['name'].startswith('THEME_') and s['name'][6:] not in others]
    for s in sorted(th, key=lambda s: s['name'][6:] != key):
        n = s['name']; rest = n[6:]
        if rest == key or key in rest.split('_') or ('_' in key and key in rest):
            return {'name': n, 'source': s.get('source'), 'cmd': s.get('cmd'), 'what': s.get('what'), 'set_in': 'songs.json'}
    disp = (r.get('display') or r['name']).replace('_', ' ').title()
    for s in th:                                      # (a shared theme: "Geese's, Krauser's and Mr. Big's theme")
        if s['name'].startswith('THEME_') and (disp + "'s") in (s.get('what') or ''):
            return {'name': s['name'], 'source': s.get('source'), 'cmd': s.get('cmd'), 'what': s.get('what'), 'set_in': 'songs.json'}
    return None


def build(out, game):
    G = json.load(open(os.path.join(game, 'game.json')))
    songs = (jload(os.path.join(game, 'songs.json')) or {}).get('songs', [])
    ver = open(os.path.join(game, 'VERSION')).read().strip()
    import animdict
    engines = set(animdict.DICTS.values())             # the source games with a dictionary builder (+ any dictionary on the site)
    for r in G['roster']:
        D = jload(os.path.join(out, 'review', r['name'] + '_anims.json'))
        if D: engines.add(r['bank'].split(':')[0])
    engines = sorted(engines)
    lens = G['chain']['lengths']
    faces = os.path.join(out, 'faces'); os.makedirs(faces, exist_ok=True)
    try: import labpub
    except Exception: labpub = None
    cast = []
    for r in G['roster']:
        n = r['name']; gm, bn = r['bank'].split(':')
        e = {'name': n, 'display': (r.get('display') or n).upper(), 'bank': r['bank'], 'game': gm,
             'game_name': GAME_NAMES.get(gm, gm), 'scale': r.get('scale', 1.0), 'archetype': r.get('archetype'),
             'chain_len': len((r.get('chain') or {}).get('links') or []) + 1 if (r.get('chain') or {}).get('links') else lens.get(r.get('archetype')),
             'chain_custom': bool((r.get('chain') or {}).get('links')), 'selectable': r.get('selectable', True) is not False,
             'unlock': r.get('unlock'), 'music': theme(G, songs, r), 'about': r.get('about')}
        # the HUD face (the game's own pixels), the big portrait
        e['face'] = None
        if labpub:
            try:
                p = labpub.hud_face(r['bank']); shutil.copy(p, os.path.join(faces, n + '.png')); e['face'] = f'faces/{n}.png'
            except Exception as x: e['face_error'] = f'{type(x).__name__}: {x}'[:160]
        wp = r.get('win_portrait')
        src = (wp if wp and os.path.isabs(wp) else os.path.join(PORTRAITS, wp)) if isinstance(wp, str) else None
        if not src and n in (G.get('portraits') or {}): src = PORTRAITS + 'big_' + G['portraits'][n].replace(':', '_') + '.png'
        e['win'] = None
        if src and os.path.exists(src):
            shutil.copy(src, os.path.join(faces, n + '_win.png')); e['win'] = f'faces/{n}_win.png'
        e['win_source'] = 'roster win_portrait' if wp else 'game.json portraits' if e['win'] else None
        # what the site holds for him
        D = jload(os.path.join(out, 'review', n + '_anims.json'))
        e['dictionary'] = {'anims': len(D.get('anims', [])), 'game': D.get('game')} if D else None
        W = jload(os.path.join(out, 'review', n + '_workshop.json'))
        if W:
            c = W.get('counts', {})
            e['workshop'] = {'unlocked': c.get('unlocked', 0), 'locked': c.get('locked', 0), 'throws_unlocked': c.get('throws_unlocked', 0),
                             'throws_locked': c.get('throws_locked', 0), 'knobs': sum(len(p.get('knobs') or []) for p in W.get('specials', []) if p.get('id'))}
        else: e['workshop'] = None
        e['sheet'] = os.path.exists(os.path.join(out, 'review', n + '_arb.json'))
        e['review'] = os.path.exists(os.path.join(out, 'review', n + '.json'))
        e['engine_decoded'] = gm in engines
        e['engine_note'] = None if gm in engines else f'{GAME_NAMES.get(gm, gm)}\'s engine is not decoded yet: no animation dictionary, so no Workshop or Assembly for {e["display"]} today.'
        cast.append(e)
    doc = {'version': ver, 'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'engines': engines, 'fighters': cast}
    json.dump(doc, open(os.path.join(out, 'cast.json'), 'w'), ensure_ascii=False)
    print(f'cast.json: {len(cast)} fighters, {sum(1 for c in cast if c["dictionary"])} with a dictionary, '
          f'{sum(1 for c in cast if c["face"])} HUD faces, {sum(1 for c in cast if c["win"])} win portraits')
    return doc


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else harness.GAME)
