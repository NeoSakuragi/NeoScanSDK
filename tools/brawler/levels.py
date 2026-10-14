#!/usr/bin/env python3
"""The Brawler Factory's LEVELS (canneji /brawler-factory/?tab=levels; Bruno 2026-10-12: "levels (music, name,
background)"): each campaign stage's name, background and song, edited in the page as a draft (the feedback service,
lab/levels), shipped by the ship service (labcfg.py ship-worker) like a fighter's sheet. Waves are not edited here.

    levels.py state GAME_DIR                 what the page shows: the stages as game.json has them, the backgrounds in
                                             the build (make_stage_ra.py STAGES), the songs in the sound ROM (songs.json,
                                             each with its preview MP3), JSON on stdout
    levels.py merge GAME_DIR DRAFT.json      the draft into game.json (only name / background / music lines rewritten),
                                             validated: a "levels: stage 2 music STAGE_HIGHWAY -> THEME_KIM" line per
                                             change, or "REFUSED: <reason>" and exit 1, game.json untouched
    levels.py previews GAME_DIR CACHE [--host H --dest DIR]
                                             a 20 s MP3 of every song not cached yet, played by the built ROM in our
                                             emulator (tools/port/capture_snd.py brawler, BRAWLER_CORE), then the cache
                                             rsync'd to H:DIR (the page's /brawler-factory/songs/)

The bonus stages (TODO T7, game.json "bonus"; build_tables.bonus_check, main.c "bonus stages") are edited here too: the
draft's optional `bonus` = {after: [stage numbers], pick_seconds, fury_lock, games: [{name, music, seconds, count | top}]}
(top = the drive chunks the gauge game's top grade adds); only the bonus block is rewritten (bonus_text).

The stage intro (voice note 20261014-192343-5d29, game.json stage_intro; build_tables.intro_of, main.c "the stage
intro") is edited here too: the draft's optional `intro` = {fade, title, title_at, title_hold, walk_at, side, from, gait,
wave_delay} (game-wide; a stage's own stages[].intro and the marks stay in game.json); only that block is rewritten.

A name: 1-12 characters A-Z 0-9 space . ! - (the fix font; build_tables.STAGE_NAME, the HUD's room before WAVE).
A background: a stage of the build wide enough for the stage's lock points (each wave's and the boss's: lock <= width
- 320, build_tables.model). A song: a songs.json song. Stage 1 plays P1's own theme instead when he has one (game.json
roster[].music, main.c stage_song): no game.json switch for that."""
import ast, copy, hashlib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
NAME = r'[A-Z0-9 .!-]{1,12}'
FIELDS = ('name', 'background', 'music')
SECONDS = 20


def backgrounds():
    """make_stage_ra.py STAGES, read without importing it (it loads Robo Army's ROM): [{i, name, w}]"""
    src = open(os.path.join(HERE, 'make_stage_ra.py')).read()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'STAGES')
    return [{'i': i, 'name': f'Robo Army area {area} street', 'w': cols * 16} for i, (area, _, cols, _) in enumerate(ast.literal_eval(node.value))]


def preview_key(s):
    return s['name'] + '-' + hashlib.sha1(f"{s['source']}|{s['cmd']}".encode()).hexdigest()[:8] + '.mp3'


def state(game):
    g = json.load(open(os.path.join(game, 'game.json')))
    songs = json.load(open(os.path.join(game, 'songs.json')))['songs']
    st = []
    for s in g['stages']:
        locks = [w['lock'] for w in s['waves']] + [s['boss']['lock']]
        st.append({**{k: s[k] for k in FIELDS}, 'need_w': max(locks) + 320})
    return {'stages': st, 'bgs': backgrounds(), 'stage1_theme': True, 'bonus': bonus_view(g), 'intro': intro_view(g),
            'songs': [{'name': s['name'], 'source': s['source'], 'what': s.get('what', '')[:160], 'preview': 'songs/' + preview_key(s)} for s in songs],
            'version': open(os.path.join(game, 'VERSION')).read().strip()}


def bonus_view(g):
    """the bonus block as the page edits it (compact: the fields Bruno tunes; kind / scene / grades stay in game.json)"""
    b = g.get('bonus')
    if not b: return None
    return {'after': b['after'], 'pick_seconds': b['pick']['seconds'], 'fury_lock': bool(b.get('fury_lock')),
            'games': [{'id': x['id'], 'kind': x['kind'], 'scene': x['scene'], 'slot': x.get('slot'), 'name': x['name'], 'music': x['music'], 'seconds': x['seconds'],
                       **({'count': x['count']} if x['kind'] == 'break' else {'top': x['chunks'][5]})} for x in b['games']]}


INTRO_EDIT = ('fade', 'title', 'title_at', 'title_hold', 'walk_at', 'side', 'from', 'gait', 'wave_delay')


def intro_view(g):
    """the stage intro as the page edits it (game.json stage_intro over build_tables.INTRO_DEFAULT)"""
    import build_tables
    v = {**build_tables.INTRO_DEFAULT, **(g.get('stage_intro') or {})}
    return {k: v[k] for k in INTRO_EDIT}


def intro_merge(g, want):
    """the page's intro view into game.json's stage_intro -> (the new block, change lines); raises ValueError(reason)"""
    import build_tables
    if not isinstance(want, dict): raise ValueError('intro: {' + ', '.join(INTRO_EDIT) + '}')
    old = intro_view(g); b = copy.deepcopy(g.get('stage_intro') or {})
    for k in INTRO_EDIT:
        if k in want: b[k] = want[k]
    try:
        for si in range(len(g['stages'])): build_tables.intro_of({**g, 'stage_intro': b}, si)
    except (AssertionError, KeyError, TypeError) as e: raise ValueError(f'intro: {e}')
    new = intro_view({'stage_intro': b})
    return b, [f'levels: intro {k} {json.dumps(old[k])} -> {json.dumps(new[k])}' for k in INTRO_EDIT if new[k] != old[k]]


def intro_text(b, ind=' '):
    """game.json's stage_intro block in its own layout (one line a field)"""
    one = lambda v: json.dumps(v, ensure_ascii=False)
    items = list(b.items())
    return [f'{ind}"stage_intro": {{'] + [f'{ind} {one(k)}: {one(v)}' + (',' if i + 1 < len(items) else '') for i, (k, v) in enumerate(items)] + [f'{ind}}},']


def bonus_merge(game, g, want):
    """the page's bonus view into game.json's bonus block -> (the new block, change lines); raises ValueError(reason)"""
    import build_tables
    old = bonus_view(g); b = copy.deepcopy(g['bonus']); ch = []
    if not isinstance(want, dict) or not isinstance(want.get('games'), list) or len(want['games']) != len(b['games']):
        raise ValueError('the bonus draft does not match the game\'s bonus games: edit it again')
    b['after'] = sorted(want.get('after', b['after'])); b['pick']['seconds'] = want.get('pick_seconds', b['pick']['seconds'])
    b['fury_lock'] = bool(want.get('fury_lock', b.get('fury_lock')))
    for x, w in zip(b['games'], want['games']):
        for k in ('name', 'music', 'seconds', 'slot') + (('count',) if x['kind'] == 'break' else ()):
            if k in w: x[k] = w[k]
        if x['kind'] == 'gauge' and 'top' in w: x['chunks'] = x['chunks'][:5] + [w['top']]
    songs = {s['name'] for s in json.load(open(os.path.join(game, 'songs.json')))['songs']}
    try: build_tables.bonus_check({**g, 'bonus': b}, songs)
    except (AssertionError, KeyError, TypeError) as e: raise ValueError(f'bonus: {e}')
    new = bonus_view({'bonus': b})
    for k in ('after', 'pick_seconds', 'fury_lock'):
        if new[k] != old[k]: ch.append(f'levels: bonus {k} {json.dumps(old[k])} -> {json.dumps(new[k])}')
    for o, n in zip(old['games'], new['games']):
        for k in n:
            if n[k] != o[k]: ch.append(f"levels: bonus {o['id']} {k} {json.dumps(o[k])} -> {json.dumps(n[k])}".replace('"', ''))
    return b, ch


def check(game, draft):
    """the draft against the game -> (new stages fields, change lines); raises ValueError(reason)"""
    S = state(game); songs = {s['name'] for s in S['songs']}; bgs = S['bgs']
    want = draft.get('stages') if isinstance(draft, dict) else None
    if not isinstance(want, list): raise ValueError('the levels draft has no stages')
    if len(want) != len(S['stages']): raise ValueError(f'the draft has {len(want)} stages, the game {len(S["stages"])}: edit it again')
    out, ch = [], []
    for i, (old, new) in enumerate(zip(S['stages'], want)):
        n = i + 1; v = {k: new.get(k, old[k]) for k in FIELDS}
        if not isinstance(v['name'], str) or not re.fullmatch(NAME, v['name']):
            raise ValueError(f'stage {n}: name {v["name"]!r}: 1-12 characters A-Z 0-9 space . ! -')
        if not isinstance(v['background'], int) or not 0 <= v['background'] < len(bgs):
            raise ValueError(f'stage {n}: background {v["background"]!r}: none in the build (0-{len(bgs) - 1})')
        if bgs[v['background']]['w'] < old['need_w']:
            raise ValueError(f'stage {n}: background {v["background"]} is {bgs[v["background"]]["w"]} px wide, its waves need {old["need_w"]}')
        if v['music'] not in songs: raise ValueError(f'stage {n}: music {v["music"]!r} is no song of songs.json')
        for k in FIELDS:
            if v[k] != old[k]: ch.append(f'levels: stage {n} {k} {json.dumps(old[k])} -> {json.dumps(v[k])}'.replace('"', ''))
        out.append(v)
    if isinstance(draft, dict) and draft.get('bonus') is not None:   # (the bonus stages: optional in a draft)
        b, bch = bonus_merge(game, json.load(open(os.path.join(game, 'game.json'))), draft['bonus'])
        if bch: ch += bch; out = (out, b)
    if isinstance(draft, dict) and draft.get('intro') is not None:   # (the stage intro: optional in a draft)
        b, ich = intro_merge(json.load(open(os.path.join(game, 'game.json'))), draft['intro'])
        if ich:
            ch += ich
            out = (out, None) if not isinstance(out, tuple) else out
            out = (out[0], out[1], b)
    return out, ch


def bonus_text(b, ind=' '):
    """game.json's bonus block in its own layout (one line a field, one line a game)"""
    one = lambda v: json.dumps(v, ensure_ascii=False)
    rows = [f'{ind}"bonus": {{'] + [f'{ind} {one(k)}: {one(v)},' for k, v in b.items() if k != 'games']
    rows += [f'{ind} "games": ['] + [f'{ind}  {one(x)}' + (',' if i + 1 < len(b['games']) else '') for i, x in enumerate(b['games'])] + [f'{ind} ]', f'{ind}}},']
    return rows


def write(game, new):
    """only the stages' name / background / music lines of game.json rewritten (the rest keeps its text); a bonus block
    changed (new = (stages, bonus)): that block rewritten (bonus_text)"""
    bonus = intro = None
    if isinstance(new, tuple): new, bonus, intro = (new + (None,))[:3]
    p = os.path.join(game, 'game.json'); text = open(p).read(); lines = text.split('\n')
    if intro is not None:
        a = next((k for k, l in enumerate(lines) if l == ' "stage_intro": {'), None)
        if a is None: a = next(k for k, l in enumerate(lines) if l == ' "stages": ['); lines[a:a] = intro_text(intro)
        else:
            e = next(k for k in range(a, len(lines)) if lines[k] == ' },')
            lines[a:e + 1] = intro_text(intro)
    if bonus is not None:
        a = next(k for k, l in enumerate(lines) if l == ' "bonus": {')
        e = next(k for k in range(a, len(lines)) if lines[k] == ' },')
        lines[a:e + 1] = bonus_text(bonus)
    i = next(k for k, l in enumerate(lines) if l.strip() == '"stages": [')
    ind = None
    for si, v in enumerate(new):
        while not re.match(r'^\s*"name": ', lines[i]) or (ind and not lines[i].startswith(ind + '"name"')): i += 1
        ind = ind or re.match(r'^(\s*)', lines[i]).group(1)
        for k in FIELDS:
            j = next(j for j in range(i, len(lines)) if lines[j].startswith(f'{ind}"{k}": '))
            lines[j] = f'{ind}"{k}": ' + json.dumps(v[k], ensure_ascii=False) + (',' if lines[j].rstrip().endswith(',') else '')
        i += 1
    out = '\n'.join(lines)
    G = json.loads(out)
    assert [{k: s[k] for k in FIELDS} for s in G['stages']] == new, 'game.json rewrite mismatch'
    assert bonus is None or G['bonus'] == bonus, 'game.json bonus rewrite mismatch'
    assert intro is None or G['stage_intro'] == intro, 'game.json stage_intro rewrite mismatch'
    open(p, 'w').write(out)


def previews(game, cache, host=None, dest=None):
    os.makedirs(cache, exist_ok=True)
    cmds = dict(re.findall(r'#define MUS_(\w+)\s+(0x[0-9A-Fa-f]+)', open(os.path.join(game, 'build', 'snd', 'songs.h')).read()))
    rom = os.path.join(game, 'brawler.neo'); made = 0
    for s in json.load(open(os.path.join(game, 'songs.json')))['songs']:
        out = os.path.join(cache, preview_key(s))
        if os.path.exists(out) or s['name'] not in cmds: continue
        tmp = os.path.join(cache, 'work', s['name'])
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        subprocess.run([sys.executable, os.path.join(REPO, 'tools', 'port', 'capture_snd.py'), 'brawler', cmds[s['name']], str(SECONDS), tmp, '--rom', rom],
                       check=True, capture_output=True)
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', tmp + '.wav', '-ar', '44100', '-b:a', '96k', out + '.part.mp3'], check=True)
        os.replace(out + '.part.mp3', out); os.remove(tmp + '.wav'); made += 1
        print('preview', os.path.basename(out), flush=True)
    if host and dest:
        subprocess.run(['rsync', '-a', '--include=*.mp3', '--exclude=*', cache + '/', f'{host}:{dest}/'], check=True)
    return made


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == 'state': return print(json.dumps(state(a[1]), ensure_ascii=False))
    if len(a) == 3 and a[0] == 'merge':
        try: new, ch = check(a[1], json.load(open(a[2])))
        except ValueError as e: print('REFUSED:', e); sys.exit(1)
        if ch: write(a[1], new)
        print('\n'.join(ch) or 'levels: no change')
        return
    if len(a) >= 3 and a[0] == 'previews':
        h = a[a.index('--host') + 1] if '--host' in a else None; d = a[a.index('--dest') + 1] if '--dest' in a else None
        return print(previews(a[1], a[2], h, d), 'new previews')
    sys.exit(__doc__)


if __name__ == '__main__':
    main()
