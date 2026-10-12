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

A name: 1-12 characters A-Z 0-9 space . ! - (the fix font; build_tables.STAGE_NAME, the HUD's room before WAVE).
A background: a stage of the build wide enough for the stage's lock points (each wave's and the boss's: lock <= width
- 320, build_tables.model). A song: a songs.json song. Stage 1 plays P1's own theme instead when he has one (game.json
roster[].music, main.c stage_song): no game.json switch for that."""
import ast, hashlib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
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
    return {'stages': st, 'bgs': backgrounds(), 'stage1_theme': True,
            'songs': [{'name': s['name'], 'source': s['source'], 'what': s.get('what', '')[:160], 'preview': 'songs/' + preview_key(s)} for s in songs],
            'version': open(os.path.join(game, 'VERSION')).read().strip()}


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
    return out, ch


def write(game, new):
    """only the stages' name / background / music lines of game.json rewritten (the rest keeps its text)"""
    p = os.path.join(game, 'game.json'); text = open(p).read(); lines = text.split('\n')
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
