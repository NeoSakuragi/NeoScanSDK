#!/usr/bin/env python3
"""The Brawler Factory's GAME tab (canneji /brawler-factory/?tab=game; Bruno 2026-10-12: "the main game meta", only what
recompiles safely with no tokens): the game-wide numbers and texts of game.json, edited in the page as a draft (the
feedback service, lab/game), shipped by the ship service (labcfg.py ship-worker, the "game" section) like a fighter's
sheet. Every knob is a value build_tables.py turns into a table the engine already reads: no new code, no new data.

    gamecfg.py state GAME_DIR              what the page shows: every knob (its group, name, unit, range, step, default,
                                           the value game.json has now), JSON on stdout
    gamecfg.py merge GAME_DIR DRAFT.json   the draft {values: {knob id: value}} into game.json (only those values' text
                                           rewritten, the rest of the file untouched), validated (the ranges below =
                                           build_tables.py's asserts, plus their cross rules): a "game: <name> 6 -> 8"
                                           line per change, or "REFUSED: <reason>" and exit 1, game.json untouched

A knob id is its game.json path, dotted ("throw_swap.frames", "ending.story.fighters.terry"). The default: the value
the game shipped with when the Game tab was made (2026-10-12; a story's / the thanks line's: the game's text then).
Left out (need new code or new data): chain lengths / totals / hit-stop (every fighter's routes are generated from
them: routes.py), the jump arc, the depth lines, AI presets, hit sounds, the title / game name, continues / credits
(main.c constants, not game.json), gravity / knockdown physics (fighter.c constants)."""
import json, os, re, sys

G = 'Meter', 'Combat', 'Physics', 'Throws', 'Texts'
# (group, id, name, unit, default, min, max, step): ranges = build_tables.py's asserts, narrowed to what makes sense
NUM = [
    ('Meter', 'meter.chunks', 'drive chunks', 'chunks', 2, 1, 4, 1),
    ('Meter', 'meter.chunk', 'chunk refill', 'frames', 240, 30, 1200, 10),
    ('Meter', 'meter.special', 'C special cost', 'chunks', 1, 1, 4, 1),
    ('Meter', 'meter.breaker', 'breaker cost', 'chunks', 2, 1, 4, 1),
    ('Meter', 'meter.life_breaker', 'breaker life cost (no drive)', 'life', 12, 1, 59, 1),
    ('Meter', 'meter.fury_drive', 'fury drive cost', 'chunks', 1, 0, 4, 1),
    ('Meter', 'meter.max_drive', 'MAX drive cost', 'chunks', 2, 0, 4, 1),
    ('Meter', 'meter.fury_max', 'fury gauge size', 'points', 100, 10, 1000, 5),
    ('Meter', 'meter.fury_dealt', 'fury per damage dealt', 'points', 1, 0, 10, 1),
    ('Meter', 'meter.fury_taken', 'fury per damage taken', 'points', 2, 0, 10, 1),
    ('Meter', 'meter.low', 'MAX: life at most', '%', 25, 1, 100, 1),
    ('Meter', 'meter.blink', 'breaker blink', 'frames', 4, 1, 60, 1),
    ('Meter', 'meter.special_flash.frames', 'C special blue flash', 'frames', 10, 0, 120, 1),
    ('Combat', 'tiers.special', 'special damage', 'life', 12, 1, 127, 1),
    ('Combat', 'tiers.fury', 'fury damage', 'life', 30, 1, 127, 1),
    ('Combat', 'tiers.max', 'MAX damage', 'life', 45, 1, 127, 1),
    ('Combat', 'blitz.damage', 'Blitz damage', 'life', 8, 1, 127, 1),
    ('Combat', 'blitz.window', 'Blitz double-tap window', 'frames', 12, 2, 60, 1),
    ('Combat', 'blitz.chord', 'Blitz A chord', 'frames', 3, 0, 8, 1),
    ('Combat', 'chain.window', 'chain window', 'frames', 35, 1, 120, 1),
    ('Combat', 'chain.buffer', 'chain buffer', 'frames', 5, 0, 60, 1),
    ('Combat', 'chain.juggle_cap', 'juggle limit', 'hits', 5, 1, 20, 1),
    ('Combat', 'chain.stun_player', 'player hit stun', 'frames', 16, 1, 120, 1),
    ('Combat', 'chain.guard_player', 'player guard window', 'frames', 20, 1, 120, 1),
    ('Combat', 'chain.stun_light', 'enemy stun, light', 'frames', 28, 1, 120, 1),
    ('Combat', 'chain.stun_heavy', 'enemy stun, heavy', 'frames', 32, 1, 120, 1),
    ('Combat', 'super_flash.freeze', 'super flash freeze', 'frames', 28, 1, 255, 1),
    ('Combat', 'super_flash.white', 'super flash white', 'frames', 4, 1, 255, 1),
    ('Physics', 'walk.fast', 'walk, fast', 'px/f', 1.75, 0.25, 6, 0.005),
    ('Physics', 'walk.balanced', 'walk, balanced', 'px/f', 1.625, 0.25, 6, 0.005),
    ('Physics', 'walk.heavy', 'walk, heavy', 'px/f', 1.54, 0.25, 6, 0.005),
    ('Physics', 'walk.run', 'run = walk x', 'x', 2, 1, 4, 0.05),
    ('Physics', 'walk.anim', 'walk anim rate x', 'x', 1.5, 0.25, 4, 0.05),
    ('Physics', 'jump.crouch', 'jump crouch', 'frames', 7, 1, 30, 1),
    ('Physics', 'jump.land', 'jump landing', 'frames', 7, 1, 60, 1),
    ('Physics', 'jump.land_cancel', 'landing cancel from', 'frames', 2, 1, 60, 1),
    ('Physics', 'jump.active_min', 'air attack active min', 'frames', 12, 1, 60, 1),
    ('Physics', 'jump.run_dx', 'run jump distance x', 'x', 2, 0.5, 4, 0.05),
    ('Throws', 'throw_swap.frames', 'side switch length', 'frames', 6, 0, 30, 1),
    ('Throws', 'throw_swap.arc', 'side switch arc', 'px', 16, 0, 64, 1),
]
CHOICE = [
    ('Throws', 'throw_handoff', 'throw hand-off', 'landing', ['release', 'landing']),
    ('Physics', 'jump.down_cancel', 'down-attack cancel', 'hit', ['hit', 'any']),
]
END_COLS = 34                                       # build_tables.END_COLS
SENT_MAX = 160                                      # a story sentence (the box scrolls; the P ROM's room)


def at(g, path):
    for k in path.split('.'): g = g[int(k)] if isinstance(g, list) else g[k]
    return g


def knobs(g):
    """every knob, its game value: [{id, group, name, kind, ...}]"""
    out = [dict(id=i, group=gr, name=n, kind='num', unit=u, default=d, min=lo, max=hi, step=st, value=at(g, i)) for gr, i, n, u, d, lo, hi, st in NUM]
    out += [dict(id=i, group=gr, name=n, kind='choice', default=d, options=o, value=at(g, i)) for gr, i, n, d, o in CHOICE]
    names = {r['name']: r.get('display', r['name']) for r in g['roster']}
    for f, s in g['ending']['story']['fighters'].items():
        out.append(dict(id='ending.story.fighters.' + f, group='Texts', name='ending: ' + ('any other fighter' if f == '*' else names.get(f, f)),
                        kind='story', min=4, max=5, value=s))
    for k, t in enumerate(g['ending']['thanks']['lines']):
        out.append(dict(id=f'ending.thanks.lines.{k}', group='Texts', name='thanks screen' + (f' line {k + 1}' if k else ''), kind='line', max=END_COLS, value=t))
    return out


def state(game):
    g = json.load(open(os.path.join(game, 'game.json')))
    return {'groups': G, 'knobs': knobs(g), 'version': open(os.path.join(game, 'VERSION')).read().strip()}


def ascii_ok(t): return isinstance(t, str) and all(0x20 <= ord(c) < 0x7F for c in t)


def check(game, draft):
    """the draft against the game -> ({id: new value}, change lines); raises ValueError(reason)"""
    g = json.load(open(os.path.join(game, 'game.json')))
    want = draft.get('values') if isinstance(draft, dict) else None
    if not isinstance(want, dict): raise ValueError('the game draft has no values')
    K = {k['id']: k for k in knobs(g)}
    new, ch = {}, []
    for i, v in want.items():
        k = K.get(i)
        if not k: raise ValueError(f'{i}: no such knob in this game')
        if k['kind'] == 'num':
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not k['min'] <= v <= k['max']:
                raise ValueError(f'{k["name"]}: {v!r} is out of {k["min"]}-{k["max"]} {k["unit"]}')
            n = round((v - k['min']) / k['step'])
            if abs(k['min'] + n * k['step'] - v) > 1e-6: raise ValueError(f'{k["name"]}: {v} is not a multiple of {k["step"]}')
            if isinstance(k['default'], int) and isinstance(k['step'], int): v = int(v)
        elif k['kind'] == 'choice':
            if v not in k['options']: raise ValueError(f'{k["name"]}: {v!r} is not one of {", ".join(k["options"])}')
        elif k['kind'] == 'story':
            if not isinstance(v, list) or not 4 <= len(v) <= 5: raise ValueError(f'{k["name"]}: 4 or 5 sentences')
            for s in v:
                if not ascii_ok(s) or not s.strip() or len(s) > SENT_MAX or any(len(w) > END_COLS for w in s.split()):
                    raise ValueError(f'{k["name"]}: {s!r}: 1-{SENT_MAX} plain ASCII characters, no word over {END_COLS}')
        elif k['kind'] == 'line':
            if not ascii_ok(v) or len(v.lstrip('^')) > END_COLS: raise ValueError(f'{k["name"]}: {v!r}: at most {END_COLS} plain ASCII characters')
        if v != k['value']:
            new[i] = v
            sh = lambda x: json.dumps(x) if k['kind'] in ('story', 'line') else str(x)
            ch.append(f'game: {k["name"]} {sh(k["value"])} -> {sh(v)}' if k['kind'] != 'story' else f'game: {k["name"]} rewritten')
    cur = {i: new.get(i, k['value']) for i, k in K.items()}      # build_tables.py's cross rules, on the result
    c = lambda i: cur[i]
    if c('meter.chunk') * c('meter.chunks') >= 65536: raise ValueError('meter: chunks x chunk refill must stay under 65536')
    for i in ('meter.special', 'meter.breaker', 'meter.fury_drive', 'meter.max_drive'):
        if c(i) > c('meter.chunks'): raise ValueError(f'{K[i]["name"]} {c(i)} is more than the {c("meter.chunks")} drive chunks')
    if not c('tiers.special') < c('tiers.fury') < c('tiers.max'): raise ValueError('damage: special < fury < MAX')
    sp = g['tiers']['spread']
    if c('tiers.special') * (100 + sp['special']) > c('tiers.fury') * (100 - sp['fury']) or c('tiers.fury') * (100 + sp['fury']) > c('tiers.max') * (100 - sp['max']):
        raise ValueError(f'damage: the bands overlap (special +-{sp["special"]} %, fury +-{sp["fury"]} %, MAX +-{sp["max"]} %): spread them further')
    if c('super_flash.white') > c('super_flash.freeze'): raise ValueError('super flash: white at most the freeze')
    if c('jump.land_cancel') > c('jump.land'): raise ValueError('jump: landing cancel at most the landing')
    return new, ch


def span(text, path):
    """the [start, end) of the value at path in the JSON text"""
    dec = json.JSONDecoder()
    def ws(i):
        while text[i].isspace(): i += 1
        return i
    i = ws(0)
    for key in path.split('.'):
        if text[i] == '{':
            i = ws(i + 1)
            while True:
                k, i = dec.raw_decode(text, i); i = ws(i); assert text[i] == ':'; i = ws(i + 1)
                if k == key: break
                i = ws(dec.raw_decode(text, i)[1]); assert text[i] == ',', f'{path}: no {key}'; i = ws(i + 1)
        else:
            assert text[i] == '['; i = ws(i + 1)
            for _ in range(int(key)): i = ws(dec.raw_decode(text, i)[1]); assert text[i] == ','; i = ws(i + 1)
    return i, dec.raw_decode(text, i)[1]


def write(game, new):
    """only those values' text rewritten (the rest of game.json keeps its text)"""
    p = os.path.join(game, 'game.json'); text = open(p).read()
    for i, v in new.items():
        a, b = span(text, i); old = text[a:b]; s = json.dumps(v, ensure_ascii=False)
        if isinstance(v, list) and '\n' in old:          # (a list laid out one item a line keeps that layout)
            ind = re.match(r'\[\s*?\n([ \t]*)', old).group(1); end = re.search(r'\n([ \t]*)\]$', old).group(1)
            s = '[\n' + ',\n'.join(ind + json.dumps(x, ensure_ascii=False) for x in v) + '\n' + end + ']'
        text = text[:a] + s + text[b:]
    g = json.loads(text)
    assert all(at(g, i) == v for i, v in new.items()), 'game.json rewrite mismatch'
    open(p, 'w').write(text)


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == 'state': return print(json.dumps(state(a[1]), ensure_ascii=False))
    if len(a) == 3 and a[0] == 'merge':
        try: new, ch = check(a[1], json.load(open(a[2])))
        except ValueError as e: print('REFUSED:', e); sys.exit(1)
        if new: write(a[1], new)
        print('\n'.join(ch) or 'game: no change')
        return
    sys.exit(__doc__)


if __name__ == '__main__':
    main()
