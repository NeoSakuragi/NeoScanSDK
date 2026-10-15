#!/usr/bin/env python3
"""The Brawler Factory's ROSTER & SELECT (canneji /brawler-factory/, Characters tab; Bruno 2026-10-12: "Go"): which
fighters are playable and where they stand on the select screen, edited in the page as a draft (the feedback service,
lab/roster), shipped by the ship service (labcfg.py SECTIONS "roster") like the Levels / Game sections.

    roster.py state GAME_DIR               what the page shows: every fighter (the roster's, the Lab-only ones: game.json
                                           roster_benched entries with "lab": true), selectable or not, his face, his
                                           stage-1 theme, his lock, his place; the free place a new one would take; the
                                           room left (C ROM, P banks: bank_proof.py on the build), JSON on stdout
    roster.py merge GAME_DIR DRAFT.json    the draft {selectable: {fighter: true | false}, layout: {fighter: {x, y, z,
                                           facing, pose, slot}} (optional: the Select screen editor's), unlocks:
                                           {starters, ladder, rung_size} (optional: the unlock ladder)} into game.json:
                                           a Lab-only fighter moved onto the roster (or back), select_layout rewritten,
                                           validated: "roster: moriya selectable" / "select: moriya at place 10 of 25
                                           (x 728, y 210)" lines, or "REFUSED: <reason>" and exit 1, game.json untouched

Checks (merge): a fighter made selectable is a Lab-only one with a bank and a face (make_hud.py: PORTRAITS
<game>_<name>_square.png or .png); taken off the roster only one that came from the Lab (nothing else in game.json names
him: no enemy, form, story, drama); at most MAX selectable (main.c NA: the select screen's sprite blocks); every
selectable fighter exactly one place (build_tables.select_layout), the stick's walk reaching every one (select_stick).
A fighter without a place in the draft takes the free place (free_place). His stage-1 theme: his roster "music" when
songs.json has it, else the stage's song; no song is dropped from the sound ROM to make room (the page says so). The
C ROM / bank room is checked by the ship's own build + bank_proof.py (ALL OK).

The unlock ladder (game.json unlocks, Bruno 2026-10-15; build_tables.unlocks): while it is there, only its fighters (the
starters + the ladder) stand on the select screen; the draft's `unlocks` rewrites its starters / ladder / rung_size lines
(build_tables.unlocks' checks: roster fighters, each once, whole rungs), a fighter new on the ladder takes the free place,
one taken off it leaves the select screen (an enemy only). "unlocks: ..." lines say what changed."""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import build_tables, select_layout

PORTRAITS = '/data/neogeo_dict/portraits/'
MAX = build_tables.MAX_SLOTS
ROWS = (184, 197, 210)                                   # the layout's three street lines (feet y)
X_MIN, X_MAX = 40, 728                                   # a free place's x: the whole fighter on the screen at the street's ends
C_CAP = 32 << 20                                         # C ROM: 16 + 16 MB (neobuild)


def face(r):
    g, n = r['bank'].split(':')
    return next((f for f in (f'{PORTRAITS}{g}_{n}_square.png', f'{PORTRAITS}{g}_{n}.png') if os.path.exists(f)), None)


def songs(game): return {s['name'] for s in json.load(open(os.path.join(game, 'songs.json')))['songs']}


def free_place(L, y_rows=ROWS):
    """the street spot farthest from every placed fighter's feet (x, then rows weighted 2.2: the rows are 13 px apart
    for ~29 px between neighbours), x in X_MIN..X_MAX; ties: the smaller x -> (x, y)"""
    best = None
    for y in y_rows:
        for x in range(X_MIN, X_MAX + 1):
            d = min((((x - v['x']) ** 2 + (2.2 * (y - v['y'])) ** 2) for v in L.values()), default=1e9)
            if best is None or d > best[0]: best = (d, x, y)
    return best[1], best[2]


def place(L, n, pose):
    """n into layout L at the free place: its slot after the fighter before it along the street's walk (x order,
    wrapping), drawn by its row (front rows over back rows)"""
    x, y = free_place(L)
    order = sorted(L, key=lambda m: L[m]['slot'])
    prev = max((m for m in order if L[m]['x'] <= x), key=lambda m: L[m]['x'], default=order[-1] if order else None)
    at = order.index(prev) + 1 if prev else 0
    order.insert(at, n)
    zs = sorted(L, key=lambda m: L[m]['z'])
    zat = sum(1 for m in zs if L[m]['y'] <= y)           # behind every fighter of a nearer row
    zs.insert(zat, n)
    out = {m: dict(L[m]) for m in L}
    out[n] = {'x': x, 'y': y, 'z': 0, 'facing': 'left' if x > 384 else 'right', 'pose': pose, 'slot': 0}
    for k, m in enumerate(order): out[m]['slot'] = k
    for k, m in enumerate(zs): out[m]['z'] = k
    return out


def room(game):
    """the build's room: C ROM bytes used / cap (build/rom_c1.bin = C1 = C2's size), P: each bank's and MB1's free bytes
    (bank_proof.py's lines; None when there is no build)"""
    c1 = os.path.join(game, 'build', 'rom_c1.bin')
    out = {'c_used': 2 * os.path.getsize(c1) if os.path.exists(c1) else None, 'c_cap': C_CAP, 'p': [], 'ok': None}
    if not os.path.exists(os.path.join(game, 'brawler.neo')): return out
    r = subprocess.run([sys.executable, os.path.join(HERE, 'bank_proof.py'), game], capture_output=True, text=True)
    for m in re.finditer(r'^(bank \d+|MB1): ([\d,]+) bytes used, ([\d,]+) free', r.stdout, re.M):
        out['p'].append({'name': m.group(1), 'used': int(m.group(2).replace(',', '')), 'free': int(m.group(3).replace(',', ''))})
    out['ok'] = 'ALL OK' in r.stdout
    return out


def state(game, with_room=True):
    g = json.load(open(os.path.join(game, 'game.json'))); S = songs(game)
    L = build_tables.select_layout(g); lab = build_tables.lab_only(g); U = build_tables.unlocks(g)
    order = sorted(L, key=lambda n: L[n]['slot'])
    rung = {}
    if U:
        rung = {n: 0 for n in U['starters']}
        for k, r in enumerate(U['rungs']): rung.update({n: k + 1 for n in r})
    fs = []
    for r in g['roster'] + list(lab.values()):
        n = r['name']; sel = n in L or (bool(U) and r.get('selectable', True) and n not in lab)   # (the ladder: a roster
        if not sel and n not in lab: continue            # fighter off it is still in the roster) (a form's other half: never)
        mu = r.get('music')
        fs.append({'name': n, 'display': r.get('display') or n.upper().replace('_', ' '), 'bank': r['bank'], 'selectable': sel,
                   'lab': n in lab, 'from_lab': bool(r.get('from_lab')), 'face': bool(face(r)), 'locked': rung.get(n, 0) > 0 if U else r.get('unlock', 'always') != 'always',
                   'unlock': r.get('unlock', 'always'), 'rung': rung.get(n) if U else None, 'music': mu, 'music_ok': bool(mu and mu in S),
                   'place': order.index(n) + 1 if n in L else None, 'pose': [r['watch']['frame'], r['watch']['step']]})
    return {'fighters': fs, 'layout': L, 'max': MAX,
            'unlocks': {k: U[k] for k in ('starters', 'ladder', 'rung_size')} if U else None, 'stick': g['select'].get('stick', 'positions'),
            'free': dict(zip(('x', 'y'), free_place(L))), 'room': room(game) if with_room else None,
            'version': open(os.path.join(game, 'VERSION')).read().strip()}


# ---- game.json text: an entry moved between "roster" and "roster_benched".fighters, the rest of the file untouched -----
def _array_items(text, key_at):
    """the array starting after text[key_at:] 'KEY': [ ... ] -> (its [ index, its ] index, [(start, end) of each item])"""
    dec = json.JSONDecoder(); i = text.index('[', key_at); spans = []; k = i + 1
    while True:
        while text[k] in ' \t\n,': k += 1
        if text[k] == ']': return i, k, spans
        _, e = dec.raw_decode(text, k); spans.append((k, e)); k = e


def _reindent(item, frm, to):
    return '\n'.join((' ' * to + l[frm:]) if l.startswith(' ' * frm) else l for l in item.split('\n'))


def move(text, n, to_roster):
    """game.json text with fighter n's entry moved: benched -> the roster's end (its "lab" flag dropped, "from_lab":
    true added: the Factory may send him back), or roster -> roster_benched.fighters' end ("lab": true again)"""
    arr = lambda t, roster: t.index('\n "roster": [') if roster else t.index('"fighters": [', t.index('\n "roster_benched":'))
    _, _, items = _array_items(text, arr(text, not to_roster))
    s, e = next((s, e) for s, e in items if json.loads(text[s:e])['name'] == n)
    ent = json.loads(text[s:e]); ind_src = s - text.rfind('\n', 0, s) - 1
    body = text[s:e].split('\n')                        # the entry's own lines, kept as written
    assert body[0] == '{' and body[-1].strip() == '}', f'{n}: its game.json entry is not one key a line'
    lines = [l.rstrip(',') for l in body[1:-1] if not re.match(r'\s*"(lab|from_lab)": ', l)]
    k = s                                                # cut it out with the comma before it (or after it: the first)
    while text[k - 1] in ' \t\n': k -= 1
    if text[k - 1] == ',': cut = (k - 1, e)
    else:
        f = e
        while text[f] in ' \t\n': f += 1
        cut = (s, f + 1) if text[f] == ',' else (k, e)
    t2 = text[:cut[0]] + text[cut[1]:]
    _, _, items2 = _array_items(t2, arr(t2, to_roster))
    last_s, last_e = items2[-1]; ind = last_s - t2.rfind('\n', 0, last_s) - 1
    keep = [_reindent(l, ind_src + 1, ind + 1) for l in lines]
    if to_roster: keep.append(' ' * (ind + 1) + '"from_lab": true'); ent.pop('lab', None); ent['from_lab'] = True
    else: keep.insert(1, ' ' * (ind + 1) + '"lab": true'); ent.pop('from_lab', None); ent = {'name': n, 'lab': True, **{k: v for k, v in ent.items() if k not in ('name', 'lab')}}
    out = t2[:last_e] + ',\n' + ' ' * ind + '{\n' + ',\n'.join(keep) + '\n' + ' ' * ind + '}' + t2[last_e:]
    G = json.loads(out); want = json.loads(text)
    if to_roster:
        want['roster_benched']['fighters'] = [r for r in want['roster_benched']['fighters'] if r['name'] != n]; want['roster'].append(ent)
    else:
        want['roster'] = [r for r in want['roster'] if r['name'] != n]; want['roster_benched']['fighters'].append(ent)
    assert G == want, f'game.json rewrite mismatch moving {n}'
    return out


def named_elsewhere(g, n):
    """the places other than his roster entry and select_layout that name fighter n (enemies, forms, stories, dramas...)"""
    h = dict(g); h['roster'] = [r for r in g['roster'] if r['name'] != n]; h.pop('select_layout', None); h.pop('roster_benched', None)
    h['select'] = {k: v for k, v in g['select'].items() if k != 'slots'}
    hits = []
    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == n: hits.append(path + k)
                walk(v, path + k + '.')
        elif isinstance(x, list):
            for i, v in enumerate(x): walk(v, f'{path}{i}.')
        elif x == n or (isinstance(x, str) and x.split(':')[-1] == n and ':' not in n and x.count(':') == 0): hits.append(path.rstrip('.'))
    walk(h, '')
    return hits


def check(game, draft):
    """the draft against the game -> (changes: [(fighter, to_roster)], the new layout, change lines); ValueError(reason)"""
    g = json.load(open(os.path.join(game, 'game.json'))); S = songs(game)
    lab = build_tables.lab_only(g); ros = {r['name']: r for r in g['roster']}
    L0 = build_tables.select_layout(g)
    if not isinstance(draft, dict): raise ValueError('the roster draft is no object')
    want = draft.get('selectable') or {}
    if not isinstance(want, dict): raise ValueError('selectable: {fighter: true | false}')
    moves, lines = [], []
    for n, on in sorted(want.items()):
        if on is True and n in L0 or on is False and n not in L0 and n in lab: continue
        if on is True:
            if n not in lab: raise ValueError(f'{n}: no Lab-only fighter of that name (roster_benched "lab": true)')
            r = lab[n]
            if not r.get('bank'): raise ValueError(f'{n}: no bank (his export)')
            if not face(r): raise ValueError(f'{n}: no face ({PORTRAITS}{r["bank"].replace(":", "_")}_square.png: tools/brawler/portraits.py)')
            moves.append((n, True)); lines.append(f'roster: {n} selectable')
            mu = r.get('music')
            lines.append(f'roster: {n} stage 1 theme {mu}' if mu and mu in S else
                         f'roster: {n} stage 1 theme: the stage song ({mu + " is " if mu else "his theme is "}not in the sound ROM; no song dropped to fit it)')
        elif on is False:
            if n not in ros: raise ValueError(f'{n}: not on the roster')
            if not ros[n].get('from_lab'): raise ValueError(f'{n}: only a fighter the Factory brought from the Lab goes back there')
            el = named_elsewhere(g, n)
            if el: raise ValueError(f'{n}: game.json still names him ({", ".join(el[:4])}): not taken off')
            moves.append((n, False)); lines.append(f'roster: {n} back to the Lab only')
        else: raise ValueError(f'selectable.{n}: true or false')
    sel = (set(L0) | {n for n, t in moves if t}) - {n for n, t in moves if not t}
    U0 = build_tables.unlocks(g); Ud = draft.get('unlocks'); U = U0
    if Ud is not None:
        if not U0: raise ValueError('unlocks: game.json has no unlocks block (the ladder is switched off)')
        if not isinstance(Ud, dict) or set(Ud) != {'starters', 'ladder', 'rung_size'}: raise ValueError('unlocks: {starters, ladder, rung_size}')
        on = {r['name'] for r in g['roster'] if r.get('selectable', True)} | {n for n, t in moves if t}
        on -= {n for n, t in moves if not t}
        g2 = dict(g, roster=[{'name': n} for n in sorted(on)], unlocks=dict(g['unlocks'], **Ud))
        try: U = build_tables.unlocks(g2)
        except AssertionError as e: raise ValueError(str(e))
        for k, w in (('starters', 'the starters'), ('ladder', 'the ladder'), ('rung_size', 'a rung')):
            if Ud[k] != U0[k]: lines.append(f'unlocks: {w} ' + (' '.join(Ud[k]) if k != 'rung_size' else f'{Ud[k]} fighters'))
    if U:                                                # (the ladder: only its fighters on the screen, every one)
        on = ({r['name'] for r in g['roster'] if r.get('selectable', True)} | {n for n, t in moves if t}) - {n for n, t in moves if not t}
        sel = {n for n in on if n in U['all']}
    if len(sel) > MAX: raise ValueError(f'{len(sel)} selectable fighters: the select screen has {MAX} places (main.c NA, its sprites)')
    D = draft.get('layout')
    L = {n: dict(v) for n, v in (D if isinstance(D, dict) and D else L0).items() if n in sel}
    if D and not isinstance(D, dict): raise ValueError('layout: {fighter: {x, y, z, facing, pose, slot}}')
    for n in L:
        if set(L[n]) != set(select_layout.KEYS): raise ValueError(f'layout {n}: fields {sorted(L[n])}')
    # renumber (a fighter gone from the draft) then a free place for each one without one
    for k in ('slot', 'z'):
        for i, n in enumerate(sorted(L, key=lambda m: L[m][k])): L[n][k] = i
    for n in sorted(sel - set(L)):
        r = lab.get(n) or ros[n]
        L = place(L, n, [r['watch']['frame'], r['watch']['step']])
    order = sorted(L, key=lambda n: L[n]['slot'])
    for n in order:                                      # the new ones, then what changed for the others
        v, was = L[n], L0.get(n)
        if was is None: lines.append(f'select: {n} at place {v["slot"] + 1} of {len(L)} (x {v["x"]}, y {v["y"]})')
        else:
            ch = [f'{k} {was[k]} -> {v[k]}' for k in ('x', 'y', 'facing', 'pose') if was[k] != v[k]]
            if ch: lines.append(f'select: {n} ' + ', '.join(ch))
    old = [n for n in order if n in L0]
    if old != [n for n in sorted(L0, key=lambda m: L0[m]['slot']) if n in L]:
        lines.append('select: the stick order ' + ' > '.join(old))
    if [n for n in sorted(L, key=lambda m: L[m]['z']) if n in L0] != [n for n in sorted(L0, key=lambda m: L0[m]['z']) if n in L]:
        lines.append('select: the draw order changed')
    # the stick's walk reaches everyone (build_tables.select_stick; heads: the build's, else a standing fighter's)
    try: heads = build_tables.bm_heads(os.path.join(game, 'build'), g)
    except Exception: heads = {}
    G = build_tables.select_stick(L, {n: heads.get(n, [0, -80]) for n in L}, g['select'].get('stick'))
    for d in ('right', 'left'):
        seen, n = set(), order[0]
        while n not in seen: seen.add(n); n = G[n][d]
        if seen != set(L): raise ValueError(f'the stick ({d}) does not reach {", ".join(sorted(set(L) - seen))}')
    return moves, L, lines, (Ud if Ud is not None and U0 and any(Ud[k] != U0[k] for k in Ud) else None)


def unlocks_text(text, U):
    """game.json text with its unlocks block's starters / rung_size / ladder lines rewritten (one line each)"""
    k = text.index('\n "unlocks": {'); e = text.index('\n }', k)
    blk = text[k:e]
    for f in ('starters', 'rung_size', 'ladder'):
        blk, n = re.subn(r'(\n  "' + f + r'": )[^\n]*?(,?)$', lambda m: m.group(1) + json.dumps(U[f]) + m.group(2), blk, count=1, flags=re.M)
        assert n == 1, f'unlocks.{f}: not one line'
    return text[:k] + blk + text[e:]


def write(game, moves, L, U=None):
    p = os.path.join(game, 'game.json'); text = open(p).read()
    for n, t in moves: text = move(text, n, t)
    if U: text = unlocks_text(text, U)
    open(p + '.part', 'w').write(text)
    try:
        select_layout.write(p + '.part', L)              # (build_tables.select_layout's checks on the moved roster)
    except AssertionError as e:
        os.remove(p + '.part'); raise ValueError(f'select layout: {e}')
    os.replace(p + '.part', p)


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == 'state': return print(json.dumps(state(a[1], '--no-room' not in a), ensure_ascii=False))
    if len(a) == 3 and a[0] == 'merge':
        try:
            moves, L, ch, U = check(a[1], json.load(open(a[2])))
            if ch: write(a[1], moves, L, U)
        except ValueError as e: print('REFUSED:', e); sys.exit(1)
        print('\n'.join(ch) or 'roster: no change')
        return
    sys.exit(__doc__)


if __name__ == '__main__':
    main()
