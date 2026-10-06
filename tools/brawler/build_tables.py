#!/usr/bin/env python3
"""The brawler's data layer: examples/brawler/game.json -> the tables the game reads (docs/brawler_data_model.md).

    build_tables.py chars  GAME.json              print the roster's bank specs (the Makefile's CHARS, bm_chars order)
    build_tables.py roster GAME.json OUT.json     the fighter export's inputs (bank, watch pose, specials, routes), written
                                                  only when they changed (export_bm.py re-runs only then)
    build_tables.py tables GAME.json BUILD_DIR    BUILD_DIR/game_tables.h + game_tables.c (gamedata.h types)
    build_tables.py format GAME.json              rewrite the file in its canonical layout (one line per spawn, slot...)
    build_tables.py pack GAME.json BUILD_DIR OUT  the Brawler Lab's data pack (stages, enemies, AI rows, version 2: the
                                                  roster section, the fighters' specials by role: gamedata.h
                                                  gdpack_t) for lab.load 3, from a game.json the running ROM was built with
                                                  or an edit of it (same roster, same stage count)
    build_tables.py labstages GAME.json BUILD_DIR OUT.json   the Brawler Lab Stages tab's data (pack_base bytes, names, songs)
    build_tables.py labenemies GAME.json OUT.json            the Brawler Lab Enemies tab's data (enemies, AI presets, tints,
                                                             the routes files its enemies use, the schema's names)

Everything is checked against the build: names resolve (fighters, enemies, AI presets, tints, songs), counts fit the
engine (6 enemies at once, 19 select slots), lock points inside the stage (build/stage.h widths)."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
SPECIAL_KEYS = ['D', 'fD', 'dD', 'uD', 'dfD', 'ufD']    # bchar_t.spmap order (BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D, BS_DF_D, BS_UF_D)
AI_FLAGS = {'token': 1, 'grab': 2, 'projectile': 4, 'reversal': 8, 'specials': 16, 'jump_in': 32, 'full_speed': 64, 'air_cd': 128,
            'boss_moves': 8 | 16 | 32}                    # gamedata.h AIF_*
AI_FIELDS = ['rest_shift', 'rest_random', 'rest_add', 'rest_start', 'rest_attack', 'rest_special', 'rest_throw', 'grab_plan',
             'attack_dx', 'hover_dx', 'hover_go_dx', 'hover_go_dz', 'range_min', 'range_max', 'range_dz', 'spec_min',
             'spec_max', 'spec_dz', 'press_gap', 'hold_gap', 'rev_dx', 'rev_dz', 'rest_rev', 'bspec_min', 'bspec_max',
             'bspec_dz', 'rush_dx', 'rest_bspec', 'jump_min', 'jump_max', 'jump_dz', 'jump_chance', 'rest_jump', 'air_b_dx', 'hop_dx', 'hop_chance']
CHANCE_MASKS = {'follow_ups': 'follow_mask', 'rev_chance': 'rev_mask', 'bspec_chance': 'bspec_mask'}   # "1 in N" -> mask N-1
MAX_ENEMIES = 6                                          # main.c NF - 2
MAX_SLOTS = 19                                           # main.c NA (an actor per slot)
SP_WALK_IN, SP_LEFT, SP_NOT_BOSS = 1, 2, 4               # gamedata.h gspawn_t.flags; rank in bits 4-7
GE_FIGHTER_NAME, GE_SPAWN = 1, 0xFF                      # gamedata.h genemy_t
GD_VERSION, GD_MAX = 7, 4096                             # gamedata.h data pack (2: + the roster section, 3: + voices, 4: + triggers, 5: + AI hop_*,
                                                         # 6: 6 roles per fighter, route trees version 3; 7: route trees version 4)
TW = {'camera_x': 1, 'wave_clear': 2, 'time': 3}         # gamedata.h TW_*, TA_*
TA = {'spawn': 1, 'lock': 2, 'music': 3, 'drama': 4, 'end_stage': 5}
TW_STAGE, MAX_TRIGGERS = 0xFF, 32
DR_LINES, DR_COLS, DR_SPEAKER = 3, 34, 16                # gamedata.h gscene_t; the name plate's length


def load(path): return json.load(open(path))


def roster_names(g): return [r['name'] for r in g['roster']]


def chars(g): return [r['bank'] for r in g['roster']]


def roster_export(g):
    """what the fighter export (export_bm.py) needs of each roster fighter, in bm_chars order"""
    return [{'bank': r['bank'], 'name': r['name'], 'watch': [r['watch']['frame'], r['watch']['step']],
             'specials': [r['specials'].get(k) for k in SPECIAL_KEYS],
             'routes': None if r.get('routes', 'default') == 'default' else os.path.join(REPO, r['routes']),
             'voices': r.get('voices'), 'fury': r.get('fury'), 'hit_sfx': r.get('hit_sfx')} for r in g['roster']]


def write_if_changed(path, text):
    if os.path.exists(path) and open(path).read() == text: return False
    open(path, 'w').write(text); return True


def stage_widths(build):
    """stages[] widths in px from build/stage.h (make_stage_ra.py), None when it isn't built yet"""
    p = os.path.join(build, 'stage.h')
    if not os.path.exists(p): return None
    m = re.search(r'stages\[STAGE_COUNT\] = \{(.*)\};', open(p).read())
    return [int(e.split(',')[1]) * 16 for e in re.findall(r'\{stage\d+_map, ([^}]*)\}', m.group(1))] if m else None


def songs(build):
    """MUS_* name -> driver command, from build/snd/songs.h (the pack needs the numbers)"""
    p = os.path.join(build, 'snd', 'songs.h')
    return {m[0]: int(m[1], 0) for m in re.findall(r'#define MUS_(\w+)\s+(0x[0-9A-Fa-f]+|\d+)', open(p).read())} if os.path.exists(p) else {}


def ai_row(n, p):
    """an AI preset (game.json form) -> the ai_preset_t fields"""
    fl = 0
    for f in p.get('flags', []): fl |= AI_FLAGS[f]
    v = {'flags': fl}
    for k in AI_FIELDS: v[k] = p.get(k, 0)
    for k, m in CHANCE_MASKS.items():
        ch = p.get(k, 1 if k == 'follow_ups' else 0)
        if k == 'follow_ups': v[m] = (1 << ch.bit_length()) - 1 if ch else 0   # follow-up presses: 0..N (N = 2^k - 1)
        else:
            assert ch == 0 or (ch & (ch - 1)) == 0, f'AI {n}: {k} must be 1 in a power of two'
            v[m] = ch - 1 if ch else 0
    pc = p.get('proj_chance', 512)                       # the projectile: 1 in N a frame in range (two random bytes)
    assert pc >= 1 and (pc & (pc - 1)) == 0 and pc <= 65536, f'AI {n}: proj_chance must be a power of two'
    v['proj_mask'], v['proj_mask2'] = min(pc, 256) - 1, max(pc >> 8, 1) - 1
    for k, x in v.items(): assert 0 <= x <= 255, f'AI {n}: {k} = {x} (0-255)'
    return v


def enemy_tree(e, g, build, idx):
    """an enemy's trimmed move list: None (its fighter's own tree), a routes.ENEMY_PRESETS name or a routes file, encoded
    against every fighter it may be (each must have the moves)"""
    m = e.get('moves', 'own')
    if m == 'own': return None
    import routes as R
    lab = json.load(open(os.path.join(build, 'chainlab.json')))
    fs = {f['name']: f for f in lab['fighters']}
    bases = e['pool'] if e['base'] == 'pool' else [e['base'] if e['base'] in idx else e['stand_in']]
    blob = None
    for b in bases:
        r = g['roster'][idx[b]]
        own = R.load(b, None if r.get('routes', 'default') == 'default' else os.path.join(REPO, r['routes']))
        tree = R.enemy_preset(m, own) if not m.endswith('.json') else R.load(b, os.path.join(REPO, m))
        x = R.encode(tree, lab['ba'], set(fs[b]['has']))
        assert blob is None or x == blob, f'enemy {e["name"]}: its tree differs between its fighters'
        blob = x
    return blob


def palette(e, n):
    """an enemy's colours: set (GE_SPAWN = the spawn's), tint name (None = the spawn's), 16 custom colours or None"""
    pal = e.get('palette') or {}
    for k in pal: assert k in ('set', 'tint', 'custom'), f'enemy {n}: palette {k}'
    cu = pal.get('custom')
    if cu is not None:
        cu = [int(str(c), 0) for c in cu]
        assert len(cu) == 16 and all(0 <= c <= 0xFFFF for c in cu), f'enemy {n}: custom = 16 Neo Geo colours (0-$FFFF)'
    return pal.get('set', GE_SPAWN if cu is None and 'tint' not in pal else 0), pal.get('tint'), cu


def model(g, build):
    """game.json -> the tables as numbers (one source for the C tables and the lab's data pack)"""
    names = roster_names(g)
    idx = {n: i for i, n in enumerate(names)}
    enemies = g['enemies']; en_idx = {e['name']: i for i, e in enumerate(enemies)}
    presets = g['ai']['presets']
    tints = ['none'] + list(g['tints']); tint_idx = {n: i for i, n in enumerate(tints)}
    widths = stage_widths(build); mus = songs(build)
    assert len(names) == len(set(names)), 'roster: a name twice'
    assert len(en_idx) == len(enemies), 'enemies: a name twice'
    M = {'names': names, 'tints': tints, 'ai': [], 'enemies': [], 'stages': [], 'presets': list(presets)}
    M['dramas'] = dramas(g)
    dr_idx = {n: i for i, n in enumerate(g.get('dramas', {}))}
    for n, p in presets.items(): M['ai'].append((n, ai_row(n, p)))
    def row(name, preset, over):                        # an AI row: the preset, or the preset with overrides (own row)
        assert preset in presets, f'enemy {name}: no AI preset {preset}'
        if not over: return list(presets).index(preset)
        v = ai_row(name, {**presets[preset], **over})
        for i, (_, w) in enumerate(M['ai']):
            if w == v: return i
        M['ai'].append((f'{name}_{preset}', v)); return len(M['ai']) - 1
    for e in enemies:
        n = e['name']
        name = e.get('hud', n)
        assert name == 'fighter' or re.fullmatch(r'[A-Z0-9_ .!-]{1,10}', name), f'enemy {n}: HUD name 1-10 characters (A-Z 0-9 _ . ! -)'
        for k in e: assert k in ('name', 'base', 'pool', 'stand_in', 'life', 'power', 'ai', 'attract_ai', 'ai_over', 'palette', 'moves', 'hud'), f'enemy {n}: unknown field {k}'
        if e['base'] == 'pool':
            pl = [idx[x] for x in e['pool']]
            assert pl == sorted(pl), f'enemy {n}: list the pool in roster order'
            base = 0xFF
        else:
            b = e['base'] if e['base'] in idx else e.get('stand_in')
            assert b in idx, f'enemy {n}: neither {e["base"]} nor its stand-in is in the roster'
            base, pl = idx[b], []
        over = e.get('ai_over') or {}
        for k in over: assert k in AI_FIELDS or k in CHANCE_MASKS or k in ('flags', 'proj_chance'), f'enemy {n}: ai_over {k}'
        st, ti, cu = palette(e, n)
        assert ti is None or ti in tint_idx, f'enemy {n}: no tint {ti}'
        assert st == GE_SPAWN or 0 <= st < 255, f'enemy {n}: palette set {st}'
        assert 1 <= e['life'] <= 32767 and 0 <= e.get('power', 0) <= 255, f'enemy {n}: life 1-32767, power 0-255'
        M['enemies'].append({'name': n, 'base': base, 'pool': pl, 'ai': row(n, e['ai'], over),
                             'attract_ai': row(n, e.get('attract_ai', e['ai']), over), 'power': e.get('power', 0),
                             'set': st, 'tint': GE_SPAWN if ti is None else tint_idx[ti], 'flags': GE_FIGHTER_NAME if name == 'fighter' else 0,
                             'life': e['life'], 'hud': None if name == 'fighter' else name.replace('_', ' '), 'pal': cu, 'moves': enemy_tree(e, g, build, idx)})
    assert len(M['ai']) <= 255, 'at most 255 AI rows'
    def spawn(d, where):
        e = d['enemy']; assert e in en_idx, f'{where}: no enemy {e}'
        fl, x = 0, d.get('x', 0)
        if 'walk_in' in d:
            w = d['walk_in']; fl |= SP_WALK_IN | (SP_LEFT if w['side'] == 'left' else 0) | (w.get('rank', 0) << 4)
            assert w['side'] in ('left', 'right') and 0 <= w.get('rank', 0) < 16, where
        if d.get('not_boss'): fl |= SP_NOT_BOSS
        return {'enemy': en_idx[e], 'pick': d.get('pick', 0), 'set': d.get('set', 0), 'tint': tint_idx[d.get('tint', 'none')],
                'x': x, 'z': d['z'], 'flags': fl}
    for si, s in enumerate(g['stages']):
        ww = widths[s['background']] if widths else None
        sp, wv = [], []
        for wi, w in enumerate(s['waves']):
            assert 1 <= len(w['spawns']) <= MAX_ENEMIES, f'stage {si + 1} wave {wi + 1}: 1-{MAX_ENEMIES} spawns'
            assert ww is None or 0 <= w['lock'] <= ww - 320, f'stage {si + 1} wave {wi + 1}: lock {w["lock"]} outside 0-{ww - 320}'
            assert wi == 0 or w['lock'] >= s['waves'][wi - 1]['lock'], f'stage {si + 1}: lock points go forward'
            wv.append({'lock': w['lock'], 'seed': int(str(w['seed']), 0), 'first': len(sp), 'n': len(w['spawns'])})
            sp += [spawn(d, f'stage {si + 1} wave {wi + 1}') for d in w['spawns']]
        b = s['boss']; nb = len(sp)
        assert len(b['minions']) <= MAX_ENEMIES - 1, f'stage {si + 1}: at most {MAX_ENEMIES - 1} minions with the boss'
        assert ww is None or b['lock'] <= ww - 320, f'stage {si + 1}: boss lock past the end'
        sp += [spawn(d, f'stage {si + 1} boss') for d in b['minions']]
        trig = [trigger(t, f'stage {si + 1} trigger {k + 1}', len(s['waves']), en_idx, tint_idx, mus, dr_idx, ww)
                for k, t in enumerate(s.get('triggers', []))]
        assert len(trig) <= MAX_TRIGGERS, f'stage {si + 1}: at most {MAX_TRIGGERS} triggers'
        assert b.get('drama') is None or b['drama'] in dr_idx, f'stage {si + 1}: no drama {b.get("drama")}'
        be = enemies[en_idx[b['enemy']]]
        unl = 1 if be['base'] in idx and g['roster'][idx[be['base']]].get('unlock') == {'boss_of_stage': si + 1} else 0
        M['stages'].append({'name': s['name'], 'bg': s['background'], 'music': s['music'], 'power': s.get('power', 0), 'waves': wv,
                            'spawns': sp, 'boss': en_idx[b['enemy']], 'boss_song': b['song'], 'unlock': unl, 'boss_lock': b['lock'],
                            'boss_x': b['x'], 'boss_z': b['z'], 'boss_seed': int(str(b['seed']), 0), 'boss_first': nb, 'nmin': len(b['minions']),
                            'music_n': mus.get(s['music']), 'boss_song_n': mus.get(b['song']), 'triggers': trig,
                            'drama': dr_idx[b['drama']] if b.get('drama') else 0xFF})
    return M


def trigger(t, where, nwaves, en_idx, tint_idx, mus, dr_idx, ww):
    """a stage trigger (game.json form) -> the gtrigger_t fields (music: the song name, its command filled by the caller
    that has build/snd/songs.h: 'music_n')"""
    for k in t: assert k in ('when', 'do', 'note'), f'{where}: unknown field {k}'
    w, d = t['when'], t['do']
    assert isinstance(w, dict) and len([k for k in w if k in TW]) == 1, f'{where}: when = one of {list(TW)}'
    for k in w: assert k in TW or k == 'wave', f'{where}: when {k}'
    kind = next(k for k in w if k in TW)
    wave = TW_STAGE; at = 0
    def wv(v):
        v = nwaves if v == 'boss' else v
        assert isinstance(v, int) and 0 <= v <= nwaves, f'{where}: wave {v} (0-{nwaves - 1} or "boss")'
        return v
    if kind == 'camera_x':
        at = w['camera_x']; assert isinstance(at, int) and 0 <= at <= (ww - 320 if ww else 32767), f'{where}: camera_x {at}'
    elif kind == 'wave_clear': wave = wv(w['wave_clear'])
    else:
        at = w['time']; assert isinstance(at, int) and 0 <= at <= 32767, f'{where}: time {at} (ticks, 0-32767)'
        if 'wave' in w: wave = wv(w['wave'])
    if d == 'end_stage': d = {'end_stage': True}
    assert isinstance(d, dict) and len(d) == 1 and next(iter(d)) in TA, f'{where}: do = one of {list(TA)}'
    act, v = next(iter(d.items()))
    r = {'when': TW[kind], 'wave': wave, 'at': at, 'action': TA[act], 'n': 0, 'arg': 0, 'delay': 0,
         'sp': {'enemy': 0, 'pick': 0, 'set': 0, 'tint': 0, 'x': 0, 'z': 0, 'flags': 0}, 'music': None}
    if act == 'spawn':
        for k in v: assert k in ('enemy', 'side', 'count', 'delay', 'z', 'pick', 'set', 'tint', 'not_boss'), f'{where}: spawn {k}'
        assert v['enemy'] in en_idx, f'{where}: no enemy {v["enemy"]}'
        assert v.get('side', 'right') in ('left', 'right'), f'{where}: side'
        n, dl, z = v.get('count', 1), v.get('delay', 0), v.get('z', 20)
        assert 1 <= n <= MAX_ENEMIES and 0 <= dl <= 32767 and 0 <= z <= 61, f'{where}: count 1-{MAX_ENEMIES}, delay 0-32767, z 0-61'
        assert v.get('tint', 'none') in tint_idx, f'{where}: no tint {v.get("tint")}'
        fl = SP_WALK_IN | (SP_LEFT if v.get('side') == 'left' else 0) | (SP_NOT_BOSS if v.get('not_boss') else 0)
        r.update(n=n, delay=dl, sp={'enemy': en_idx[v['enemy']], 'pick': v.get('pick', 0), 'set': v.get('set', 0),
                                    'tint': tint_idx[v.get('tint', 'none')], 'x': 0, 'z': z, 'flags': fl})
    elif act == 'lock':
        assert isinstance(v, int) and 0 <= v <= 32767, f'{where}: lock {v}'
        r['arg'] = v
    elif act == 'music':
        assert not mus or v in mus, f'{where}: no song {v}'
        r['music'] = v; r['arg'] = mus.get(v, 0)
    elif act == 'drama':
        assert v in dr_idx, f'{where}: no drama {v}'
        r['arg'] = dr_idx[v]
    return r


def dramas(g):
    """game.json's dramas (name -> scenes) checked: portraits by name (game.json portraits), lines the fix font can show"""
    ports = list(g.get('portraits', {}))
    out = []
    for n, scenes in g.get('dramas', {}).items():
        assert re.fullmatch(r'[a-z0-9_]+', n) and 1 <= len(scenes) <= 8, f'drama {n}: a name a-z 0-9 _, 1-8 scenes'
        rows = []
        for k, sc in enumerate(scenes):
            w = f'drama {n} scene {k + 1}'
            for f in sc: assert f in ('speaker', 'side', 'portrait', 'lines', 'lines_by', 'wait'), f'{w}: unknown field {f}'
            who = {'$P1': 1, '$P2': 2}.get(sc['speaker'], 0)
            p = sc.get('portrait')
            assert p is None or (p in ports and not who), f'{w}: no portrait {p} (game.json portraits: {ports}; "$P1" / "$P2" use their own)'
            assert sc.get('side', 'right') in ('left', 'right'), f'{w}: side'
            by = dict(sc.get('lines_by', {}))
            assert not by or who, f'{w}: lines_by only for "$P1" / "$P2"'
            assert not ('lines' in sc and '*' in by), f'{w}: lines and lines_by "*" both give the default'
            lines = sc['lines'] if 'lines' in sc else by.pop('*', None)
            assert lines is not None, f'{w}: lines (or lines_by "*"): the lines of every other fighter'
            names = [r['name'] for r in g['roster']]
            for k in by: assert k in names, f'{w}: lines_by {k}: not a roster fighter'
            for ls in [lines] + list(by.values()):
                assert 1 <= len(ls) <= DR_LINES, f'{w}: 1-{DR_LINES} lines'
                for t in ls: assert all(0x20 <= ord(c) < 0x7F for c in t) and len(t) <= DR_COLS, f'{w}: {t!r}: ASCII, at most {DR_COLS} characters'
            assert all(0x20 <= ord(c) < 0x7F for c in sc['speaker']) and 1 <= len(sc['speaker']) <= DR_SPEAKER, f'{w}: speaker 1-{DR_SPEAKER} characters'
            wait = sc.get('wait', 120); assert 0 <= wait <= 32767, f'{w}: wait (ticks)'
            rows.append({'portrait': 0xFF if p is None else ports.index(p), 'side': 1 if sc.get('side', 'right') == 'right' else 0,
                         'speaker': sc['speaker'], 'lines': lines, 'wait': wait, 'who': who,
                         'by': [(names.index(k), v) for k, v in by.items()]})
        out.append((n, rows))
    return out


# binary layouts (gamedata.h; game_tables.c asserts each offset, so a struct change fails the build until these follow)
AI_ORDER = ['flags', 'rest_shift', 'rest_random', 'rest_add', 'rest_start', 'rest_attack', 'rest_special', 'rest_throw', 'grab_plan',
            'attack_dx', 'hover_dx', 'hover_go_dx', 'hover_go_dz', 'range_min', 'range_max', 'range_dz', 'spec_min', 'spec_max', 'spec_dz',
            'follow_mask', 'press_gap', 'hold_gap', 'rev_dx', 'rev_dz', 'rev_mask', 'rest_rev', 'bspec_min', 'bspec_max', 'bspec_dz',
            'bspec_mask', 'rush_dx', 'rest_bspec', 'jump_min', 'jump_max', 'jump_dz', 'jump_chance', 'rest_jump', 'air_b_dx',
            'hop_dx', 'hop_chance', 'proj_mask', 'proj_mask2']
EN_LAYOUT = [('base', 0, 'B'), ('ai', 1, 'B'), ('attract_ai', 2, 'B'), ('power', 3, 'B'), ('npool', 4, 'B'), ('set', 5, 'B'),
             ('tint', 6, 'B'), ('flags', 7, 'B'), ('life', 8, 'h'), ('pool', 10, 'I'), ('name', 14, 'I'), ('pal', 18, 'I'), ('moves', 22, 'I')]
EN_SIZE = 26
ST_LAYOUT = [('bg', 0, 'B'), ('music', 1, 'B'), ('power', 2, 'B'), ('nwaves', 3, 'B'), ('waves', 4, 'I'), ('spawns', 8, 'I'),
             ('boss', 12, 'B'), ('boss_song', 13, 'B'), ('unlock', 14, 'B'), ('boss_z', 15, 'B'), ('boss_lock', 16, 'h'),
             ('boss_x', 18, 'h'), ('boss_seed', 20, 'H'), ('boss_first', 22, 'B'), ('nmin', 23, 'B')]
ST_SIZE, WAVE_SIZE, SPAWN_SIZE, PACK_HEAD = 24, 6, 8, 20
TRIG_SIZE, SX_SIZE = 18, 8                                # gtrigger_t, gstagex_t


def layout_asserts():
    out = [f'_Static_assert(sizeof(ai_preset_t) == {len(AI_ORDER)}, "build_tables.py AI_ORDER");']
    out += [f'_Static_assert(offsetof(ai_preset_t, {k}) == {i}, "build_tables.py AI_ORDER");' for i, k in enumerate(AI_ORDER)]
    out += [f'_Static_assert(offsetof(genemy_t, {k}) == {o}, "build_tables.py EN_LAYOUT");' for k, o, _ in EN_LAYOUT]
    out += [f'_Static_assert(offsetof(gstage_t, {k}) == {o}, "build_tables.py ST_LAYOUT");' for k, o, _ in ST_LAYOUT]
    out += [f'_Static_assert(sizeof(gstage_t) == {ST_SIZE} && sizeof(gwave_t) == {WAVE_SIZE} && sizeof(gspawn_t) == {SPAWN_SIZE}, "build_tables.py sizes");']
    return out


def c_str(s): return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def tables(g, build):
    M = model(g, build)
    presets = M['presets']
    h = ['/* Generated by tools/brawler/build_tables.py from examples/brawler/game.json. Do not edit. */',
         '#ifndef GAME_TABLES_H\n#define GAME_TABLES_H\n#include "bm_chars.h"\n#include "gamedata.h"\n#include "snd/songs.h"',
         f'#define GS_COUNT {len(g["stages"])}            /* campaign stages */',
         f'#define EN_COUNT {len(M["enemies"])}', f'#define AI_COUNT {len(M["ai"])}            /* the presets, then the enemies\' own rows */',
         f'#define TINT_COUNT {len(M["tints"])}',
         f'#define SEL_NSLOT {len(g["select"]["slots"])}',
         f'#define GAME_MUS_SELECT MUS_{g["music"]["select"]}', f'#define GAME_MUS_CLEAR MUS_{g["music"]["clear"]}',
         f'#define GAME_MUS_CONTINUE MUS_{g["music"].get("continue", g["music"]["clear"])}',
         f'#define GAME_MUS_OVER MUS_{g["music"].get("gameover", g["music"]["clear"])}',
         f'#define AI_TOKENS {g["ai"]["tokens"]}',
         'enum { ' + ', '.join(f'AI_{n.upper()}' for n in presets) + ' };',
         'enum { ' + ', '.join(f'EN_{e["name"].upper()}' for e in M['enemies']) + ' };',
         'extern const gstage_t gstages_rom[GS_COUNT];', 'extern const genemy_t genemies_rom[EN_COUNT];',
         'extern const ai_preset_t ai_presets_rom[AI_COUNT];', 'extern const gtint_t gtints[TINT_COUNT];',
         'extern const sel_slot_t SEL_SLOT[SEL_NSLOT];', 'extern const uint8_t sel_fighter[SEL_NSLOT];',
         'extern const uint8_t roster_unlock[BC_COUNT];',
         f'#define DR_COUNT {len(M["dramas"])}            /* drama scenes (game.json dramas) */',
         'extern const gstagex_t gstagex_rom[GS_COUNT];', 'extern const uint8_t pb_of_fighter[BC_COUNT];', 'extern const gdrama_t gdramas[DR_COUNT ? DR_COUNT : 1];']
    c = ['/* Generated by tools/brawler/build_tables.py from examples/brawler/game.json. Do not edit. */',
         '#include <stddef.h>\n#include "bm_chars.h"\n#include "game_tables.h"\n#include "fighter.h"\n'] + layout_asserts()
    c.append('const ai_preset_t ai_presets_rom[AI_COUNT] = {\n' + '\n'.join(
        '    { ' + ', '.join(f'.{k} = {x}' for k, x in v.items()) + ' },   /* ' + n + ' */' for n, v in M['ai']) + '\n};')
    m = g['meter']                                       # the special meter (TODO #71): every value a frame / point count
    for k in m: assert k in ('about', 'max', 'special', 'fury', 'fury_min', 'refill', 'hit_mul', 'flash', 'infinite'), f'meter: unknown field {k}'
    assert 0 < m['special'] <= m['max'] < 65536 and 0 < m['fury'] <= m['max'] and m['fury_min'] <= m['max'] and \
        1 <= m['refill'] <= 255 and 1 <= m['hit_mul'] <= 8 and 0 <= m['flash'] <= 255, 'meter values'
    c.append(f"const gmeter_t gmeter = {{ .max = {m['max']}, .special = {m['special']}, .fury = {m['fury']}, "
             f".fury_min = {m['fury_min']}, .refill = {m['refill']}, .hit_mul = {m['hit_mul']}, .flash = {m['flash']}, .infinite = {1 if m.get('infinite') else 0} }};")
    fl = g['super_flash']                                # the super flash (TODO #139): one rule for every fury
    for k in fl: assert k in ('about', 'start', 'freeze', 'white', 'anchor', 'white_colour', 'dark_colour', 'sound'), f'super_flash: unknown field {k}'
    assert 1 <= fl['start'] <= 255 and 1 <= fl['white'] <= fl['freeze'] <= 255 and len(fl['anchor']) == 2, 'super_flash values'
    sfx = json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['sfx']['codes']   # (build = the game's build/)
    assert fl['sound'].upper() in [x.upper() for x in sfx], f"super_flash sound {fl['sound']}: not in songs.json sfx codes (the V ROM has no sample for it)"
    c.append(f"const gflash_t gflash = {{ .start = {fl['start']}, .freeze = {fl['freeze']}, .white = {fl['white']}, .sound = 0x{fl['sound']}, .dx = {fl['anchor'][0]}, "
             f".dy = {fl['anchor'][1]}, .white_col = {fl['white_colour']}, .dark_col = {fl['dark_colour']} }};")
    c.append('const gtint_t gtints[TINT_COUNT] = {\n    { 0, 0, 0, { 0, 0, 0 } },   /* none: its own colour set */\n' + '\n'.join(
        f'    {{ {t["mix"]}, {t["mul"]}, {t["shift"]}, {{ {", ".join(map(str, t["add"]))} }} }},   /* {n} */' for n, t in g['tints'].items()) + '\n};')
    erows = []
    for e in M['enemies']:
        ln = e['name'].lower()
        if e['pool']: c.append(f'static const uint8_t pool_{ln}[] = {{ {", ".join(map(str, e["pool"]))} }};')
        if e['pal']: c.append(f'static const uint16_t pal_{ln}[16] = {{ {", ".join(f"0x{x:04X}" for x in e["pal"])} }};')
        if e['moves']: c.append(f'static const uint8_t moves_{ln}[{len(e["moves"])}] __attribute__((aligned(2))) = {{ {", ".join(map(str, e["moves"]))} }};')
        erows.append(f'    {{ .base = {e["base"]}, .ai = {e["ai"]}, .attract_ai = {e["attract_ai"]}, .power = {e["power"]}, .npool = {len(e["pool"])}, '
                     f'.set = {e["set"]}, .tint = {e["tint"]}, .flags = {e["flags"]}, .life = {e["life"]}, .pool = {"pool_" + ln if e["pool"] else 0}, '
                     f'.name = {c_str(e["hud"]) if e["hud"] else 0}, .pal = {"pal_" + ln if e["pal"] else 0}, .moves = {"moves_" + ln if e["moves"] else 0} }},   /* {e["name"]} */')
    c.append('const genemy_t genemies_rom[EN_COUNT] = {\n' + '\n'.join(erows) + '\n};')
    rows = []
    for si, s in enumerate(M['stages']):
        c.append(f'static const gspawn_t stage{si}_spawns[] = {{\n    ' + ',\n    '.join(
            f'{{ .enemy = {d["enemy"]}, .pick = {d["pick"]}, .set = {d["set"]}, .tint = {d["tint"]}, .x = {d["x"]}, .z = {d["z"]}, .flags = 0x{d["flags"]:02X} }}'
            for d in s['spawns']) + '\n};')
        c.append(f'static const gwave_t stage{si}_waves[] = {{\n    ' + ',\n    '.join(
            f'{{ .lock = {w["lock"]}, .seed = 0x{w["seed"]:04X}, .first = {w["first"]}, .n = {w["n"]} }}' for w in s['waves']) + '\n};')
        rows.append(f'    {{ .bg = {s["bg"]}, .music = MUS_{s["music"]}, .power = {s["power"]}, .nwaves = {len(s["waves"])}, '
                    f'.waves = stage{si}_waves, .spawns = stage{si}_spawns, .boss = {s["boss"]}, .boss_song = MUS_{s["boss_song"]}, '
                    f'.unlock = {s["unlock"]}, .boss_lock = {s["boss_lock"]}, .boss_x = {s["boss_x"]}, .boss_z = {s["boss_z"]}, .boss_seed = 0x{s["boss_seed"]:04X}, '
                    f'.boss_first = {s["boss_first"]}, .nmin = {s["nmin"]} }},   /* {s["name"]} */')
    c.append('const gstage_t gstages_rom[GS_COUNT] = {\n' + '\n'.join(rows) + '\n};')
    xrows = []
    for si, s in enumerate(M['stages']):
        if s['triggers']:
            c.append(f'static const gtrigger_t stage{si}_triggers[] = {{\n    ' + ',\n    '.join(
                f'{{ .when = {t["when"]}, .wave = {t["wave"]}, .at = {t["at"]}, .action = {t["action"]}, .n = {t["n"]}, '
                f'.arg = {"MUS_" + t["music"] if t["music"] else t["arg"]}, .delay = {t["delay"]}, .sp = {{ .enemy = {t["sp"]["enemy"]}, '
                f'.pick = {t["sp"]["pick"]}, .set = {t["sp"]["set"]}, .tint = {t["sp"]["tint"]}, .x = 0, .z = {t["sp"]["z"]}, .flags = 0x{t["sp"]["flags"]:02X} }} }}'
                for t in s['triggers']) + '\n};')
        xrows.append(f'    {{ .trig = {f"stage{si}_triggers" if s["triggers"] else 0}, .ntrig = {len(s["triggers"])}, .drama = {s["drama"]} }},   /* {s["name"]} */')
    c.append('const gstagex_t gstagex_rom[GS_COUNT] = {\n' + '\n'.join(xrows) + '\n};')
    drows = []
    for di, (dn, scenes) in enumerate(M['dramas']):
        for k, sc in enumerate(scenes):
            if sc['by']: c.append(f'static const gsceneby_t drama{di}_{k}_by[] = {{ ' + ', '.join(
                f'{{ .fighter = {f}, .nlines = {len(ls)}, .line = {{ {", ".join(c_str(t) for t in ls)} }} }}' for f, ls in sc['by']) + ' };')
        c.append(f'static const gscene_t drama{di}[] = {{\n    ' + ',\n    '.join(
            f'{{ .portrait = {sc["portrait"]}, .side = {sc["side"]}, .nlines = {len(sc["lines"])}, .who = {sc["who"]}, .wait = {sc["wait"]}, '
            f'.nby = {len(sc["by"])}, .speaker = {c_str(sc["speaker"])}, .line = {{ {", ".join(c_str(t) for t in sc["lines"])} }}, '
            f'.by = {f"drama{di}_{k}_by" if sc["by"] else 0} }}' for k, sc in enumerate(scenes)) + '\n};')
        drows.append(f'    {{ .n = {len(scenes)}, .scene = drama{di} }},   /* {dn} */')
    ports = list(g.get('portraits', {}))
    c.append('const uint8_t pb_of_fighter[BC_COUNT] = { ' + ', '.join(str(ports.index(n)) if n in ports else '0xFF' for n in M['names']) +
             ' };   /* each roster fighter\'s big portrait (game.json portraits, by its name), 0xFF none */')
    c.append('const gdrama_t gdramas[DR_COUNT ? DR_COUNT : 1] = {\n' + ('\n'.join(drows) if drows else '    { 0 }') + '\n};')
    names = M['names']; idx = {n: i for i, n in enumerate(names)}
    slots = g['select']['slots']
    assert len(slots) <= MAX_SLOTS and sorted(idx[s['fighter']] for s in slots if s.get('fighter')) == list(range(len(names))), \
        'select: every roster fighter in exactly one slot'
    c.append('const sel_slot_t SEL_SLOT[SEL_NSLOT] = {\n    ' + ', '.join(f'{{ {s["x"]}, {s["z"]}, {s["row"]} }}' for s in slots) + '\n};')
    c.append('const uint8_t sel_fighter[SEL_NSLOT] = { ' + ', '.join(str(idx[s['fighter']]) if s.get('fighter') else '0xFF' for s in slots) + ' };')
    unl = []
    for r in g['roster']:
        u = r.get('unlock', 'always')
        unl.append(0 if u == 'always' else u['boss_of_stage'])
        assert u == 'always' or 1 <= u['boss_of_stage'] <= len(g['stages']), f'{r["name"]}: unlock {u}'
    c.append('const uint8_t roster_unlock[BC_COUNT] = { ' + ', '.join(map(str, unl)) + ' };   /* stage k + 1 whose boss unlocks it, 0 = always */')
    h.append('#endif')
    write_if_changed(os.path.join(build, 'game_tables.h'), '\n'.join(h) + '\n')
    write_if_changed(os.path.join(build, 'game_tables.c'), '\n'.join(c) + '\n')


def pack_base(M):
    """the pack's first part (everything but the stages): the header's room, the AI rows, the enemies with their pools,
    names, palettes and trees; the Brawler Lab's Stages tab appends the stages to these bytes as pack_stages does"""
    import struct
    out = bytearray(PACK_HEAD)
    def put(data, align=2):
        while len(out) % align: out.append(0)
        o = len(out); out.extend(data); return o
    def rec(layout, size, v):
        b = bytearray(size)
        for k, o, f in layout: struct.pack_into('>' + f, b, o, v[k])
        return b
    ai_o = put(bytes(b for _, v in M['ai'] for b in (v[k] for k in AI_ORDER)))
    ens = []
    for e in M['enemies']:
        v = dict(e, npool=len(e['pool']))
        v['pool'] = put(bytes(e['pool']), 1) if e['pool'] else 0
        v['name'] = put(e['hud'].encode() + b'\0', 1) if e['hud'] else 0
        v['pal'] = put(struct.pack('>16H', *e['pal'])) if e['pal'] else 0
        v['moves'] = put(e['moves']) if e['moves'] else 0
        ens.append(v)
    en_o = put(b''.join(rec(EN_LAYOUT, EN_SIZE, v) for v in ens))
    return out, en_o, ai_o


def spec_map(g, build):
    """the pack's roster section: per roster fighter (bm_chars order) the special each role plays (D, forward+D, down+D,
    up+D, down-forward+D, up-forward+D) as an index in its pool (build/chainlab.json fighters[].pool, export_bm special_pool order), 0xFF = none"""
    pools = {f['name']: [p['input'] for p in f['pool']] for f in json.load(open(os.path.join(build, 'chainlab.json')))['fighters']}
    out = []
    for r in g['roster']:
        for k in SPECIAL_KEYS:
            want = r['specials'].get(k)
            assert want is None or want in pools[r['name']], f"{r['name']}: no special {want} for {k} (its pool: {' '.join(pools[r['name']])})"
            out.append(0xFF if want is None else pools[r['name']].index(want))
    return bytes(out)


def voice_tabs(g, build):
    """the pack's voices part: per roster fighter its voice table (voices.py table) when game.json's roster[].voices
    gives another table than the ROM's (build/chainlab.json fighters[].voices: keys, KOF's suggestion, the ROM's map), else
    None (the ROM's)"""
    import voices as V
    fs = {f['name']: f['voices'] for f in json.load(open(os.path.join(build, 'chainlab.json')))['fighters']}
    out = []
    for r in g['roster']:
        d = fs[r['name']]
        mp = V.mapping(r.get('voices'), d['suggest'])
        t, rom = V.table(d['keys'], d['suggest'], mp, d['nvoice']), V.table(d['keys'], d['suggest'], d['map'], d['nvoice'])
        out.append(bytes(t) if t != rom else None)
    return out


def pack_stages(M, out, en_o, ai_o, spmap, vtabs=None):
    """the stages after pack_base's bytes, the roster section (spec_map), then the header (chainlab/stagepack.js pack is the
    same code)"""
    import struct
    def put(data, align=2):
        while len(out) % align: out.append(0)
        o = len(out); out.extend(data); return o
    nsp = max(len(s['spawns']) for s in M['stages'])
    sts = []
    for s in M['stages']:
        assert s['music_n'] is not None and s['boss_song_n'] is not None, 'pack: build/snd/songs.h missing a song'
        sp = s['spawns'] + [s['spawns'][-1]] * (nsp - len(s['spawns']))      # padded: every stage holds nspawns
        v = dict(s, music=s['music_n'], boss_song=s['boss_song_n'], nwaves=len(s['waves']))
        v['spawns'] = put(b''.join(struct.pack('>BBBBhBB', d['enemy'], d['pick'], d['set'], d['tint'], d['x'], d['z'], d['flags']) for d in sp))
        v['waves'] = put(b''.join(struct.pack('>hHBB', w['lock'], w['seed'], w['first'], w['n']) for w in s['waves']))
        sts.append(v)
    st = bytearray()
    for v in sts:
        b = bytearray(ST_SIZE)
        for k, o, f in ST_LAYOUT: struct.pack_into('>' + f, b, o, v[k])
        st += b
    st_o = put(st)
    ro_o = put(bytes(spmap) + bytes(2 * len(vtabs or [])))   # version 2: the roster section (the specials by role);
    for i, t in enumerate(vtabs or []):                 # version 3: + per fighter its voice table's offset (0: the ROM's)
        if t is not None: struct.pack_into('>H', out, ro_o + len(spmap) + 2 * i, put(t, 1))
    tro = [put(b''.join(trig_bytes(t) for t in s['triggers'])) if s['triggers'] else 0 for s in M['stages']]   # version 4
    sx_o = put(b''.join(struct.pack('>IBBH', o, len(s['triggers']), s['drama'], 0) for o, s in zip(tro, M['stages'])))
    while len(out) % 2: out.append(0)
    assert len(out) <= GD_MAX, f'pack: {len(out)} bytes (at most {GD_MAX})'
    struct.pack_into('>2sBBBBHHHHHHH', out, 0, b'GD', GD_VERSION, len(sts), len(M['enemies']), len(M['ai']), len(out), st_o, en_o, ai_o, nsp, ro_o, sx_o)
    return bytes(out)


def trig_bytes(t):
    """gtrigger_t, big-endian (stagepack.js trigBytes)"""
    import struct
    d = t['sp']
    return struct.pack('>BBhBBHHBBBBhBB', t['when'], t['wave'], t['at'], t['action'], t['n'], t['arg'], t['delay'],
                       d['enemy'], d['pick'], d['set'], d['tint'], d['x'], d['z'], d['flags'])


def pack(g, build):
    """the lab's data pack (gamedata.h gdpack_t): stages, enemies and AI rows, pointers as offsets from its start"""
    M = model(g, build)
    return pack_stages(M, *pack_base(M), spec_map(g, build), voice_tabs(g, build))


def lab_stages(g, build):
    """what the Brawler Lab's Stages tab needs to build packs in the page: pack_base's bytes, the enemies (name, base,
    pool, the stage whose boss unlocks its fighter), tints, songs (MUS_* commands), the ROM's stage widths"""
    M = model(g, build)
    out, en_o, ai_o = pack_base(M)
    idx = {n: i for i, n in enumerate(M['names'])}
    ens = []
    for e in g['enemies']:
        b = e['base'] if e['base'] == 'pool' or e['base'] in idx else e.get('stand_in')
        u = g['roster'][idx[b]].get('unlock') if b in idx else None
        ens.append({'name': e['name'], 'base': b, 'pool': e.get('pool', []), 'life': e['life'],
                    'unlock_of': u['boss_of_stage'] if isinstance(u, dict) else 0})
    return {'base': out.hex(), 'en_o': en_o, 'ai_o': ai_o, 'nai': len(M['ai']), 'enemies': ens, 'tints': M['tints'],
            'songs': songs(build), 'widths': stage_widths(build), 'stages': g['stages'], 'roster': M['names'],
            'max_enemies': MAX_ENEMIES, 'gd_max': GD_MAX, 'spmap': list(spec_map(g, build)), 'dramas': list(g.get('dramas', {}))}


def lab_enemies(g):
    """what the Brawler Lab's Enemies tab needs to build the pack's first part in the page (chainlab/enemypack.js, the
    same rules and bytes as model()'s enemy half and pack_base): the enemies and AI presets in game.json form, the tints,
    the roster (names, the stage whose boss unlocks each), the routes files the enemies use, the schema's constants"""
    files = {e['moves']: json.load(open(os.path.join(REPO, e['moves']))) for e in g['enemies'] if str(e.get('moves', '')).endswith('.json')}
    return {'enemies': g['enemies'], 'presets': g['ai']['presets'], 'tints': g['tints'], 'roster': roster_names(g),
            'unlock': [r['unlock']['boss_of_stage'] if isinstance(r.get('unlock'), dict) else 0 for r in g['roster']],
            'route_files': files, 'ai_flags': AI_FLAGS, 'ai_fields': AI_FIELDS, 'chance_masks': CHANCE_MASKS, 'ai_order': AI_ORDER,
            'move_presets': ['own'] + __import__('routes').ENEMY_PRESETS, 'max_name': 10}


def fmt(o, depth=0):
    """game.json's layout: a container that fits 120 characters on one line (a spawn, a slot, a watch pose), the others open"""
    if isinstance(o, (dict, list)) and o and len(json.dumps(o, ensure_ascii=False)) + depth > 120:
        pad = ' ' * (depth + 1)
        if isinstance(o, dict):
            items = [f'{pad}{json.dumps(k)}: {fmt(v, depth + 1)}' for k, v in o.items()]
            return '{\n' + ',\n'.join(items) + '\n' + ' ' * depth + '}'
        return '[\n' + ',\n'.join(pad + fmt(v, depth + 1) for v in o) + '\n' + ' ' * depth + ']'
    return json.dumps(o, ensure_ascii=False)


if __name__ == '__main__':
    cmd, path = sys.argv[1], sys.argv[2]
    g = load(path)
    if cmd == 'chars': print(' '.join(chars(g)))
    elif cmd == 'roster': write_if_changed(sys.argv[3], json.dumps(roster_export(g), indent=1) + '\n')
    elif cmd == 'tables': tables(g, sys.argv[3])
    elif cmd == 'format': open(path, 'w').write(fmt(g) + '\n')
    elif cmd == 'pack': open(sys.argv[4], 'wb').write(pack(g, sys.argv[3]))
    elif cmd == 'labstages': json.dump(lab_stages(g, sys.argv[3]), open(sys.argv[4], 'w'))
    elif cmd == 'labenemies': json.dump(lab_enemies(g), open(sys.argv[3], 'w'))
    else: sys.exit(__doc__)
