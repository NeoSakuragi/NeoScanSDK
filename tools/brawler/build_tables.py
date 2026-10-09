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
import json, math, os, re, sys

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
MAX_SLOTS = 24                                           # main.c NA (an actor per slot)
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


SELECT_FLOOR = 158                                       # main.c: the select screen's floor (legacy slots: feet at it + z)
SELECT_W = 768                                           # main.c: the select screen's street (land.h LAND_W, KOF95's stage 2): x 0-767


def select_layout(g):
    """the select screen's group photo: {fighter: {x, y, z, facing, pose, slot}} for every selectable roster fighter (the
    Brawler Lab's Select screen tab writes it, tools/brawler/select_layout.py pulls it into game.json "select_layout"):
    x its feet on the street (world px 0 .. SELECT_W - 1: the select screen scrolls along KOF95's Neo Geo Land, its camera
    following the cursor), y its feet on the screen (px), z its draw order (0 = the back, drawn
    first), facing 'left' (the ROM sprites') or 'right', pose [frame, step] its select pose (export_bm 'watch': a KOF
    state and its step, -1 = the last), slot its place in the stick's order (left / right step through it).
    No block: the first layout (game.json select.slots: rows, x / z, facing the middle, the roster's watch poses, drawn
    back row first, a row in slot order; the stick's order = the slots' order)."""
    names = [r['name'] for r in g['roster'] if r.get('selectable', True)]
    if 'select_layout' in g:
        L = g['select_layout']
    else:
        slots = [s for s in g['select']['slots'] if s.get('fighter')]
        watch = {r['name']: r['watch'] for r in g['roster']}
        rank = {s['fighter']: k for k, s in enumerate(sorted(slots, key=lambda s: s['z']))}   # sorted() is stable: slot order in a row
        L = {s['fighter']: {'x': s['x'], 'y': SELECT_FLOOR + s['z'], 'z': rank[s['fighter']], 'facing': 'right' if s['x'] < 160 else 'left',
                            'pose': [watch[s['fighter']]['frame'], watch[s['fighter']]['step']], 'slot': k} for k, s in enumerate(slots)}
        L = {n: L[n] for n in names if n in L}
    assert sorted(L) == sorted(names), f'select_layout: every selectable roster fighter exactly once (missing {set(names) - set(L)}, extra {set(L) - set(names)})'
    assert len(L) <= MAX_SLOTS, f'select_layout: {len(L)} fighters, {MAX_SLOTS} actors at most (main.c NA)'
    for k in ('z', 'slot'):
        assert sorted(v[k] for v in L.values()) == list(range(len(L))), f'select_layout: {k} must number the fighters 0..{len(L) - 1} once each'
    for n, v in L.items():
        assert set(v) == {'x', 'y', 'z', 'facing', 'pose', 'slot'}, f'select_layout {n}: fields {sorted(v)}'
        assert 0 <= v['x'] < SELECT_W and 0 <= v['y'] <= 223 and v['facing'] in ('left', 'right'), f'select_layout {n}: {v}'
        assert len(v['pose']) == 2 and all(isinstance(x, int) for x in v['pose']), f'select_layout {n}: pose {v["pose"]}'
    return L


SEL_ROW_GAP = 16                                         # select_stick: body centres more than this apart (y) = another row
SEL_DIRS = ('right', 'left', 'up', 'down')               # the stick's four ways (main.c sel_move: sel_stick right / left, sel_vert up / down)


def select_stick(L, heads, override=None):
    """the select screen's cursor graph (TODO #187, Bruno 2026-10-07: "automatic computation of sequencing based on
    coordinates on the screen"), from the fighters' places: {fighter: {right, left, up, down: fighter}}.
    Each fighter's body centre on the screen = the middle of its feet (x, y) and its head point (heads[n]: px from the
    feet, facing left, mirrored when it faces right; export_bm bm_head / select.json, what the cursor's arrow uses).
    Rows: the centres sorted by y, a new row past a gap of SEL_ROW_GAP px. right / left = the next / previous fighter by
    centre x in the row; past the row's end the first of the next row (the last row's end: the first row), so right
    and left each walk one loop through everyone (a locked one: on past it). up / down = the fighter of the row above /
    below whose centre x is the nearest (ties: the nearer y, then the stick order); the top row's up = the bottom row,
    the bottom's down = the top; 'ups' / 'downs' = the preference behind it (every other row that way, nearest row
    first, each by that distance): a locked one is passed over for the next (main.c sel_move, the game's sel_vert).
    No dead ends, every fighter reachable. override 'order' (game.json select.stick): left / right step through the
    slots' order instead (the Lab's list, looping); up / down as above.
    The Lab computes the same (chainlab/selectrender.js stick); select_proof.py checks the two agree."""
    order = sorted(L, key=lambda n: L[n]['slot'])
    C = {}                                               # the centres, doubled (whole numbers): feet + head
    for n in order:
        v, h = L[n], heads[n]
        C[n] = (2 * v['x'] + (-h[0] if v['facing'] == 'right' else h[0]), 2 * v['y'] + h[1])
    rows = []
    for n in sorted(order, key=lambda n: (C[n][1], L[n]['slot'])):
        if rows and C[n][1] - C[rows[-1][-1]][1] <= 2 * SEL_ROW_GAP: rows[-1].append(n)
        else: rows.append([n])
    rows = [sorted(r, key=lambda n: (C[n][0], C[n][1], L[n]['slot'])) for r in rows]
    loop = order if override == 'order' else [n for r in rows for n in r]
    row_of = {n: k for k, r in enumerate(rows) for n in r}
    G = {}
    for i, n in enumerate(loop):
        def pref(step):                                  # the other rows that way (wrapping), each by distance
            out = []
            for j in range(1, len(rows)):
                out += sorted(rows[(row_of[n] + step * j) % len(rows)], key=lambda m: (abs(C[m][0] - C[n][0]), abs(C[m][1] - C[n][1]), L[m]['slot']))
            return out
        ups, downs = pref(-1), pref(1)
        G[n] = {'right': loop[(i + 1) % len(loop)], 'left': loop[i - 1], 'up': ups[0] if ups else n, 'down': downs[0] if downs else n,
                'ups': ups, 'downs': downs}
    for a in ('right', 'left'):                          # one loop through everyone: no dead end, every fighter reachable
        seen, n = set(), order[0]
        while n not in seen: seen.add(n); n = G[n][a]
        assert seen == set(L), f'select_stick: {a} misses {set(L) - seen}'
    return G


def bm_heads(build, g):
    """the select poses' head points of the build (export_bm.py -> bm_chars.c bm_head, roster order): {name: [x, y]}"""
    import re
    t = open(os.path.join(build, 'bm_chars.c')).read().split('bm_head[BC_COUNT][2] =', 1)[1].split(';', 1)[0]
    hd = [[int(a), int(b)] for a, b in re.findall(r'\{(-?\d+), (-?\d+)\}', t)]
    names = [r['name'] for r in g['roster']]
    assert len(hd) == len(names), f'bm_head: {len(hd)} entries, roster {len(names)}'
    return dict(zip(names, hd))


def bm_npals(build, g):
    """each roster fighter's palette count in the build (export_bm.py -> bm_chars.c bm_chars[].npal): {name: npal}"""
    import re
    t = open(os.path.join(build, 'bm_chars.c')).read().split('const bchar_t bm_chars[BC_COUNT] = {', 1)[1]
    n = [int(a) for a in re.findall(r'^\s*\{"[^"]*", (\d+), \d+,', t, re.M)]
    names = [r['name'] for r in g['roster']]
    assert len(n) == len(names), f'bm_chars npal: {len(n)} entries, roster {len(names)}'
    return dict(zip(names, n))


MAX_PALS = 8                                             # fighter.h: palettes a fighter loads at most


def sel_palbases(g, build):
    """the select screen's actors' palettes (main.c slot_show): back to back from 16 in slot order, each fighter its own
    count (min(npal, MAX_PALS)): ([first palette per slot], palettes in all)"""
    L = select_layout(g); npal = bm_npals(build, g); out, k = [], 16
    for n in sorted(L, key=lambda n: L[n]['slot']):
        out.append(k); k += min(npal[n], MAX_PALS)
    return out, k - 16


def watch_of(g, r):
    """a roster fighter's select pose [frame, step] and its head point (None: head_point.py finds it): the select layout's
    pose; roster[].watch.head (a hand-set point) only while the pose is the one it was set for"""
    w = [r['watch']['frame'], r['watch']['step']]
    L = select_layout(g) if r.get('selectable', True) else {}
    pose = L[r['name']]['pose'] if r['name'] in L else w
    return list(pose), (r['watch'].get('head') if list(pose) == w else None)


CHAIN_KEYS = ('about', 'window', 'buffer', 'lengths', 'totals', 'hitstop', 'juggle_cap', 'stun_player', 'guard_player',
              'stun_light', 'stun_heavy')


def chain_cfg(g, r):
    """a roster fighter's chain (revamp 1A, routes.py chain_tree): its archetype's length and damage total, the hit-stop
    scale, its finishers, its damage scale (for the entries)"""
    c = g['chain']
    a = r.get('archetype')
    assert a in ('fast', 'balanced', 'heavy'), f"roster {r['name']}: archetype {a} (fast / balanced / heavy)"
    fin = r.get('finishers') or {}
    for k in fin: assert k in ('launcher', 'down', 'neutral', 'forward', 'up', 'down_move'), f"roster {r['name']}: finishers.{k}"
    own = r.get('chain') or {}                     # (revamp 5, the chain tool's save) links: the moves before the finisher,
    for k in own: assert k in ('links', 'hitstop'), f"roster {r['name']}: chain.{k} (links / hitstop)"   # hitstop: per link + the finisher
    air = dict(AIR_DEFAULT, **(r.get('air') or {}))  # its three air attacks (Bruno 2026-10-08): forward jump + A, straight
    for k in air: assert k in AIR_DEFAULT, f"roster {r['name']}: air.{k} (forward / straight / down)"   # jump + A, down + A
    return {'archetype': a, 'length': c['lengths'][a], 'total': c['totals'][a], 'hitstop': c['hitstop'], 'finishers': fin,
            'air': air, 'specials': r.get('specials') or {},          # (revamp gold: a finisher named as a special input)
            'damage': r.get('damage', 1), **({'links': own['links']} if 'links' in own else {}),
            **({'hitstops': own['hitstop']} if 'hitstop' in own else {})}


def blitz_rows(g, build):
    """gblitz_rom: per roster fighter (bm_chars order) its four Blitz slots (roster[].blitz ff / dd / du / uu): a special of
    its pool (its index; build/chainlab.json fighters[].pool, export_bm special_pool order), 'dash' = 0xFE (its tree's dash
    entry), absent = 0xFF; a fighter without roster[].blitz: ff = 'dash', the others none (Bruno 2026-10-08)"""
    pools = {f['name']: [p['input'] for p in f['pool']] for f in json.load(open(os.path.join(build, 'chainlab.json')))['fighters']}
    out = []
    for r in g['roster']:
        bz = r.get('blitz') or {'ff': 'dash'}
        for k in bz: assert k in BLITZ_SLOTS, f"roster {r['name']}: blitz.{k} (ff / dd / du / uu)"
        row = []
        for k in BLITZ_SLOTS:
            v = bz.get(k)
            if v is None: row.append(0xFF)
            elif v == 'dash': row.append(0xFE)
            else:
                assert v in pools[r['name']], f"roster {r['name']}: blitz.{k} {v}: not in its pool ({' '.join(pools[r['name']])})"
                row.append(pools[r['name']].index(v))
        out.append((r['name'], row))
    return out


def blitz_cancels(g):
    """gblitz_can: per roster fighter (bm_chars order) per Blitz slot (BZ_FF .. BZ_UU) the slots it may cancel into on hit,
    bit k = slot k (roster[].blitz_cancel {from: [to, ...]}; Bruno 2026-10-09, note 20261009-114542-5d29: Terry's quirk
    dd -> uu); absent = none (every other Blitz -> Blitz stays forbidden, 0.8.1)"""
    out = []
    for r in g['roster']:
        bz = r.get('blitz') or {'ff': 'dash'}; row = [0] * len(BLITZ_SLOTS)
        for a, tos in (r.get('blitz_cancel') or {}).items():
            assert a in BLITZ_SLOTS and a in bz, f"roster {r['name']}: blitz_cancel.{a}: not one of its Blitz slots"
            for b in tos:
                assert b in BLITZ_SLOTS and b in bz and b != a, f"roster {r['name']}: blitz_cancel.{a} -> {b}: not another of its Blitz slots"
                row[BLITZ_SLOTS.index(a)] |= 1 << BLITZ_SLOTS.index(b)
        out.append((r['name'], row))
    return out


RUN_KEYS = ('hold_last', 'float')
def run_bobs(g):
    """grun_bob: per roster fighter its run's float (roster[].run.float {px, period}; Bruno 2026-10-09, note
    20261009-102625-5d29: Kim floats up and down a few pixels as he runs): one height a frame (px above its feet, drawn
    only: main.c draw), px x (1 - cos) / 2 over period frames, from 0 (no pop as the run starts); none = 0"""
    out, refs = [], []
    for r in g['roster']:
        run = r.get('run') or {}
        for k in run: assert k in RUN_KEYS, f"roster {r['name']}: run.{k} (hold_last / float)"
        fl = run.get('float')
        if not fl: refs.append('0'); continue
        assert set(fl) == {'px', 'period'} and 1 <= fl['px'] <= 16 and 4 <= fl['period'] <= 120, f"roster {r['name']}: run.float {fl}"
        h = [round(fl['px'] * (1 - math.cos(2 * math.pi * i / fl['period'])) / 2) for i in range(fl['period'])]
        out.append(f"static const uint8_t grun_{r['name']}[{fl['period'] + 1}] = {{ {fl['period']}, {', '.join(map(str, h))} }};")
        refs.append(f"grun_{r['name']}")
    return out + ['const uint8_t *const grun_bob[BC_COUNT] = { ' + ', '.join(refs) + ' };   /* the run\'s float per fighter: '
                  '[period, height a frame...] (roster[].run.float), 0 = none */']


def roster_export(g):
    """what the fighter export (export_bm.py) needs of each roster fighter, in bm_chars order"""
    for r in g['roster']:                          # (revamp 3b) a grab fury: provisional, Bruno's choice pending (throws1)
        if r.get('fury_grab'):
            assert r.get('fury') and r['fury'] == (r.get('throws') or {}).get('super'), \
                f"roster {r['name']}: fury_grab: its fury must be its super throw's grab (throws.super)"
    return [{'bank': r['bank'], 'name': r['name'], 'watch': watch_of(g, r)[0], 'head': watch_of(g, r)[1], 'chain': chain_cfg(g, r),
             'specials': [r['specials'].get(k) for k in SPECIAL_KEYS],
             'routes': None if r.get('routes', 'default') == 'default' else os.path.join(REPO, r['routes']),
             'voices': r.get('voices'), 'fury': r.get('fury'), 'hit_sfx': r.get('hit_sfx'), 'throws': r.get('throws'),
             **{k: r[k] for k in ('form', 'display', 'variant', 'scale', 'moves', 'anim_specials', 'fire', 'flash_pose', 'air_specials', 'down_attack', 'invincible', 'nopush', 'max', 'run') if k in r}} for r in g['roster']]


def write_if_changed(path, text):
    if os.path.exists(path) and open(path).read() == text: return False
    open(path, 'w').write(text); return True


def stage_widths(build):
    """stages[] widths in px from build/stage.h (make_stage_ra.py), None when it isn't built yet"""
    p = os.path.join(build, 'stage.h')
    if not os.path.exists(p): return None
    m = re.search(r'stages\[STAGE_COUNT\] = \{(.*)\};', open(p).read())
    return [int(e.split(',')[1]) * 16 for e in re.findall(r'\{stage\d+_map, ([^}]*)\}', m.group(1))] if m else None


def depth_columns(points, width):
    """game.json depth[background] = [[x, z], ...] (x rising): the floor's back edge as the smallest Z (px from the
    band's back) along the stage, straight lines between the points, the end points' Z past them -> one byte per 16 px
    column of the stage: the largest Z the lines reach inside it (rounded up)"""
    xs = [p[0] for p in points]
    assert xs == sorted(xs) and all(0 <= p[1] <= 64 for p in points), f'depth: {points} (x rising, z 0..64)'
    def at(x):
        if x <= xs[0]: return points[0][1]
        if x >= xs[-1]: return points[-1][1]
        k = next(i for i in range(1, len(points)) if xs[i] >= x)
        (x0, z0), (x1, z1) = points[k - 1], points[k]
        return z0 + (z1 - z0) * (x - x0) / (x1 - x0) if x1 > x0 else max(z0, z1)
    return [math.ceil(max(at(x) for x in range(c * 16, c * 16 + 16))) for c in range(width // 16)]


def depth_tables(g, build):
    """gback_rom[background] (stage.h stages[] index): its depth_columns, or 0 (no table: Z from 0)"""
    widths = stage_widths(build); dep = {k: v for k, v in g.get('depth', {}).items() if k != 'about'}
    assert widths, 'depth: build/stage.h first'
    for k in dep: assert k.isdigit() and int(k) < len(widths), f'depth: no background {k}'
    out, refs = [], []
    for n, w in enumerate(widths):
        if str(n) not in dep: refs.append('0'); continue
        cols = depth_columns(dep[str(n)], w); assert len(cols) < 256
        out.append(f'static const uint8_t gback{n}[{len(cols)}] = {{ ' + ', '.join(map(str, cols)) + ' };')
        refs.append(f'gback{n}')
    return out + [f'const uint8_t *const gback_rom[{len(widths)}] = {{ ' + ', '.join(refs) + ' };   /* the floor\'s back '
                  'edge per background (game.json depth; fighter.h zback) */']


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
        own = fs[b]['tree']                              # its fighter's tree as the game plays it (the chain core's, export_bm)
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


METER_KEYS = ('about', 'chunk', 'chunks', 'special', 'breaker', 'life_breaker', 'blink', 'fury_max', 'fury_dealt',
              'fury_taken', 'low', 'infinite', 'fury_drive', 'max_drive', 'refill_pause')
REFILL_PAUSE = {'special': 1, 'chain': 2}            # gamedata.h RP_*: meter.refill_pause names
BLITZ_KEYS = ('about', 'window', 'chord', 'damage')
BLITZ_SLOTS = ('ff', 'dd', 'du', 'uu')               # fighter.h BZ_*: forward,forward / down,down / down,up / up,up + A
JUMP_KEYS = ('about', 'crouch', 'height', 'dx', 'land_dx', 'x_scale', 'land', 'land_cancel', 'active_min', 'down_cancel', 'run_dx')
WALK_KEYS = ('about', 'fast', 'balanced', 'heavy', 'run', 'anim')
AIR_DEFAULT = {'forward': 'atk_d_jump', 'straight': 'atk_c_jump', 'down': 'atk_a_jump'}   # roster[].air (Bruno 2026-10-08:
                                                    # forward jump D, straight jump C, down + A jump A or the closest)
TIER_KEYS = ('about', 'special', 'fury', 'max', 'super_throw', 'spread', 'measured')


def dtier_tables(g, build, dmul):
    """revamp 2, the damage tiers (Bruno 2026-10-08: specials about equal across all characters +-15 %, furies +-20 %, MAX
    +-20 %, special < fury < MAX): game.json "tiers" {special, fury, max} = the whole damage of every special / fury / MAX
    on a full connect; tiers.measured (tools/brawler/damage_raw.json, damage_tiers.py --raw --save: each move's own total
    in our emulator, the scales off) -> dtier_rom[fighter] = 8.8 scales [its pool's specials, then the fury, the MAX]:
    tier / own total for each measured move; a special not measured (not on a slot: enemies' route specials) or whose
    measure found no hit keeps the fighter's damage scale (roster[].damage, TODO #203: SS2 x 3); build/dtier.json lists
    every scale (the proof's table)"""
    t = g['tiers']
    for k in t: assert k in TIER_KEYS, f'tiers: unknown field {k}'
    assert 0 < t['special'] < t['fury'] < t['max'] < 128, 'tiers: special < fury < MAX'
    sp = t['spread']                                     # the bands may not overlap: special < fury < MAX whatever the
    assert t['special'] * (100 + sp['special']) <= t['fury'] * (100 - sp['fury']) and \
        t['fury'] * (100 + sp['fury']) <= t['max'] * (100 - sp['max']), 'tiers: overlapping bands'   # rounding
    raw_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', t['measured'])
    raw = json.load(open(raw_p)) if os.path.exists(raw_p) else {}
    lab_p = os.path.join(build, 'chainlab.json')
    labj = json.load(open(lab_p)) if os.path.exists(lab_p) else {'fighters': []}
    lab = {f['name']: f for f in labj['fighters']}
    sc = lambda target, own: min(0xFFFF, (target * 256 + own // 2) // own)
    c, rows, rep = [], [], {}
    for i, r in enumerate(g['roster']):
        n = r['name']
        if n not in lab:                                 # (the first build: the export comes after) every scale 1
            rows.append('dtier_none'); continue
        pool = [p['input'] for p in lab[n]['pool']]; m = raw.get(n) or {}
        v = [dmul[i] * 256] * len(pool) + [256, 256, 256]
        e = rep[n] = {'specials': {}, 'fury': None, 'max': None, 'super_throw': None}
        for kof, x in (m.get('specials') or {}).items():
            if kof in pool and x['damage'] > 0: v[pool.index(kof)] = sc(t['special'], x['damage'])
            e['specials'][kof] = {'own': x['damage'], 'scale': v[pool.index(kof)] / 256 if kof in pool else None}
        def own(inp):                                    # a move's measured total by its input, wherever it was measured
            x = (m.get('specials') or {}).get(inp)       # (a slot special, the fury, the MAX: revamp 3 moved grab furies
            if x: return x['damage']                     # to the super throw and a MAX to the fury, Rosa's 421A)
            return next((m[k]['damage'] for k in ('fury', 'max') if m.get(k) and m[k].get('input') == inp), None)
        fury = r.get('fury'); mx = r.get('max')          # the MAX: game.json's, else 'MAX <fury>' in the pool, else the
        if fury and not mx:                              # one measured as it (TODO #152's other button), else the fury
            mm = (m.get('max') or {}).get('input') or ''
            mx = 'MAX ' + fury if 'MAX ' + fury in pool else mm if mm.startswith('MAX ') and mm in pool else fury
        sup = (r.get('throws') or {}).get('super')        # the super throw's special (revamp 3; a paired one: its tier as is)
        for k, j, tg, inp in (('fury', 0, t['fury'], fury), ('max', 1, t['max'], mx),
                              ('super_throw', 2, t['super_throw'], sup if sup in pool else None)):
            d = own(inp) if inp else None
            if d: v[len(pool) + j] = sc(tg, d)
            e[k] = {'input': inp, 'own': d, 'scale': v[len(pool) + j] / 256}
        c.append(f'static const uint16_t dtier_{i}[{len(v)}] = {{ {", ".join(map(str, v))} }};   /* {n} */')
        rows.append(f'dtier_{i}')
    wide = max([len(f['pool']) for f in labj['fighters']] + [0]) + 3
    if 'dtier_none' in rows: c.insert(0, f'static const uint16_t dtier_none[{wide}] = {{ {", ".join(["256"] * wide)} }};   /* (no export yet) */')
    c.append('const uint16_t *const dtier_rom[BC_COUNT] = { ' + ', '.join(rows) + ' };')
    json.dump(rep, open(os.path.join(build, 'dtier.json'), 'w'), indent=1)
    return c


def retime_tables(g, build):
    """game.json roster[].retime -> gretime_rom[] (fighter.h gretime_t; fighter.c "retiming"): each move's targets, one
    per segment (retime.py: its segments from build/chainlab.json, the export's); a segment outside retime.BOUND is
    built and printed as a hand check; build/retime.json lists every entry (the Lab)"""
    import retime as RT
    lab_p = os.path.join(build, 'chainlab.json')
    want = [(i, r) for i, r in enumerate(g['roster']) if r.get('retime')]
    labj = json.load(open(lab_p)) if want and os.path.exists(lab_p) else {'fighters': [], 'ba': []}
    lab = {f['name']: f for f in labj['fighters']}; ba = labj['ba']
    c, rows, rep = [], [], []
    for i, r in want:
        if r['name'] not in lab:
            print(f'retime: {r["name"]}: no build/chainlab.json yet (the fighters\' export): its targets wait for it'); continue
        L = lab[r['name']]; pool = [p['input'] for p in L['pool']]
        for move, spec in r['retime'].items():
            if spec is None: continue
            if move in ba: idx, segs = ba.index(move), L['segs']['moves'].get(move) or []
            else:
                assert move in pool, f'{r["name"]}: retime "{move}": not a brawler move nor one of its specials ({", ".join(pool)})'
                idx = len(ba) + pool.index(move); segs = L['segs']['specials'][pool.index(move)]
            assert segs, f'{r["name"]}: retime "{move}": no segments (no active frame, or a captured script: not retimed)'
            T = RT.targets(spec, segs)
            assert all(t >= 1 for t, s_ in zip(T, segs) if s_), f'{r["name"]}: retime "{move}": a segment of 0 frames {T}'
            warn = RT.hand_checks(f'{r["name"]} {move}', segs, T)
            for w in warn: print('retime:', w)
            k = len(rows)
            c.append(f'static const uint16_t gretime_t{k}[] = {{ {", ".join(map(str, T))} }};   /* {r["name"]} {move}: {segs} -> {T} */')
            rows.append(f'    {{ {i}, {len(T)}, {idx}, gretime_t{k} }},')
            rep.append({'fighter': r['name'], 'move': move, 'index': idx, 'segments': segs, 'targets': T, 'spec': spec, 'hand_check': warn})
    c.append('const gretime_t gretime_rom[] = {   /* (fighter.c "retiming") the moves given targets: fighter, segments, move, targets */\n'
             + ''.join(x + '\n' for x in rows) + '    { 0xFF, 0, 0, 0 }\n};')
    json.dump(rep, open(os.path.join(build, 'retime.json'), 'w'), indent=1)
    return c


RULE_KEYS = ('about', 'attackers', 'approach_max', 'ready', 'windup', 'rank')


def ai_rules(g):
    """game.json ai.rules (revamp 1B: attack tokens, the ready pose and wait, wind-up by damage, the rank) -> the C of
    gairules_t gai and ai_ready[BC_COUNT] (every fighter's ready stance: its own `ready.by_fighter` entry, else
    `ready.pose`; the game falls back to `ready.fallback`, then the tint pulse, when the fighter has no such step)"""
    r = g['ai']['rules']
    for k in r: assert k in RULE_KEYS, f'ai.rules: unknown field {k}'
    rd, wu, rk = r['ready'], r['windup'], r['rank']
    for k in rd: assert k in ('about', 'pose', 'fallback', 'by_fighter', 'pulse', 'wait'), f'ai.rules.ready: unknown field {k}'
    for k in wu: assert k in ('about', 'light', 'heavy', 'heavy_from', 'special_hold'), f'ai.rules.windup: unknown field {k}'
    for k in rk: assert k in ('about', 'start', 'max', 'death', 'fast', 'clean', 'fast_clear', 'every', 'wait', 'rest', 'damage'), f'ai.rules.rank: unknown field {k}'
    names = roster_names(g)
    ba = lambda m: 'BA_' + m.upper()
    def pose(p, where):
        if p == 'tint': return '0xFF', '0'
        assert isinstance(p, list) and len(p) == 2 and isinstance(p[0], str) and 0 <= p[1] < 64, f'{where}: [move, step] or "tint"'
        return ba(p[0]), str(p[1])
    for n in rd.get('by_fighter', {}): assert n in names, f'ai.rules.ready.by_fighter: {n} is not in the roster'
    wait = rd['wait']
    assert len(wait) == 32 and all(1 <= w <= 255 for w in wait), 'ai.rules.ready.wait: 32 frame counts 1-255'
    for w in ('light', 'heavy', 'special_hold'):
        v = wu[w]
        assert isinstance(v, list) and len(v) == 2 and 0 <= v[0] <= v[1] <= 120, f'ai.rules.windup.{w}: [lo, hi] frames'
    assert 1 <= wu['heavy_from'] <= 255, 'ai.rules.windup.heavy_from: 1-255'
    assert 1 <= r['attackers'] <= 6 and 1 <= r['approach_max'] <= 255 and 1 <= rd['pulse'] <= 255, 'ai.rules: attackers 1-6, approach_max / pulse 1-255'
    assert 0 <= rk['start'] <= rk['max'] <= 31, 'ai.rules.rank: 0 <= start <= max <= 31'
    for k in ('death', 'fast', 'clean', 'wait', 'rest', 'damage'): assert 0 <= rk[k] <= 32, f'ai.rules.rank.{k}: 0-32'
    assert 1 <= rk['every'] <= 65535 and 1 <= rk['fast_clear'] <= 65535, 'ai.rules.rank: every / fast_clear 1-65535 frames'
    a2, s2 = pose(rd['fallback'], 'ai.rules.ready.fallback')
    out = [f"const gairules_t gai = {{ .attackers = {r['attackers']}, .approach_max = {r['approach_max']}, .pulse = {rd['pulse']}, "
           f".ready_anim2 = {a2}, .ready_step2 = {s2}, .light_lo = {wu['light'][0]}, .light_hi = {wu['light'][1]}, "
           f".heavy_lo = {wu['heavy'][0]}, .heavy_hi = {wu['heavy'][1]}, .heavy_from = {wu['heavy_from']}, "
           f".spec_lo = {wu['special_hold'][0]}, .spec_hi = {wu['special_hold'][1]}, .rank_start = {rk['start']}, .rank_max = {rk['max']}, "
           f".rank_death = {rk['death']}, .rank_fast = {rk['fast']}, .rank_clean = {rk['clean']}, .rank_wait = {rk['wait']}, "
           f".rank_rest = {rk['rest']}, .rank_dmg = {rk['damage']}, .rank_every = {rk['every']}, .fast_clear = {rk['fast_clear']}, "
           f".wait = {{ {', '.join(map(str, wait))} }} }};"]
    rows = [pose(rd.get('by_fighter', {}).get(n, rd['pose']), f'ai.rules.ready ({n})') for n in names]
    out.append('const uint8_t ai_ready[BC_COUNT][2] = { ' + ', '.join(f'{{ {a}, {s} }}' for a, s in rows) + ' };   /* ' + ' '.join(names) + ' */')
    return out


def tables(g, build):
    M = model(g, build)
    presets = M['presets']
    h = ['/* Generated by tools/brawler/build_tables.py from examples/brawler/game.json. Do not edit. */',
         '#ifndef GAME_TABLES_H\n#define GAME_TABLES_H\n#include "bm_chars.h"\n#include "gamedata.h"\n#include "snd/songs.h"',
         f'#define GS_COUNT {len(g["stages"])}            /* campaign stages */',
         f'#define EN_COUNT {len(M["enemies"])}', f'#define AI_COUNT {len(M["ai"])}            /* the presets, then the enemies\' own rows */',
         f'#define TINT_COUNT {len(M["tints"])}',
         f'#define SEL_NSLOT {len(select_layout(g))}',
         f'#define SEL_NPAL {sel_palbases(g, build)[1]}             /* the select screen\'s actors\' palettes from 16 (sel_palbase) */',
         f'#define GAME_MUS_SELECT MUS_{g["music"]["select"]}', f'#define GAME_MUS_CLEAR MUS_{g["music"]["clear"]}',
         f'#define GAME_MUS_CONTINUE MUS_{g["music"].get("continue", g["music"]["clear"])}',
         f'#define GAME_MUS_OVER MUS_{g["music"].get("gameover", g["music"]["clear"])}',
         'enum { ' + ', '.join(f'AI_{n.upper()}' for n in presets) + ' };',
         'enum { ' + ', '.join(f'EN_{e["name"].upper()}' for e in M['enemies']) + ' };',
         'extern const gstage_t gstages_rom[GS_COUNT];', 'extern const genemy_t genemies_rom[EN_COUNT];',
         'extern const ai_preset_t ai_presets_rom[AI_COUNT];', 'extern const gtint_t gtints[TINT_COUNT];',
         'extern const sel_slot_t SEL_SLOT[SEL_NSLOT];', 'extern const uint8_t sel_fighter[SEL_NSLOT];', 'extern const uint8_t sel_palbase[SEL_NSLOT];', 'extern const uint8_t sel_stick[SEL_NSLOT][2];', 'extern const uint8_t sel_vert[SEL_NSLOT][2][SEL_NSLOT - 1];',
         'extern const uint8_t roster_unlock[BC_COUNT];',
         'extern const uint16_t *const dtier_rom[BC_COUNT];   /* the damage tiers (fighter.c "damage tiers"): per fighter, 8.8 scales: [special index], [nspec] the fury, [nspec + 1] the MAX */',
         'extern uint8_t dtier_off;                         /* (fighter.c) 1: every scale 1 (a test switch) */',
         'extern const uint8_t ai_ready[BC_COUNT][2];',
         'extern const uint8_t gblitz_rom[BC_COUNT][4];   /* per fighter its Blitz slots (BZ_FF .. BZ_UU): a special\'s pool index, BZ_DASH its dash entry, BZ_NONE */',
         'extern const int32_t gwalk_rom[BC_COUNT];       /* its walk (16.16 px a frame, by archetype) */',
         'extern const uint8_t gblitz_can[BC_COUNT][4];   /* per fighter per Blitz slot: the slots it may cancel into on hit (bit BZ_*; roster[].blitz_cancel) */',
         'extern const uint8_t *const grun_bob[BC_COUNT]; /* the run\'s float: [period, px a frame...] (roster[].run.float), 0 = none */',
         'extern const uint16_t gwalk_run;               /* run = walk x this (8.8) */',
         'extern const uint16_t gwalk_anim;              /* the walk / run animations\' rate x this (8.8) */',
         'extern const uint8_t *const gback_rom[];       /* the floor\'s back edge per background (game.json depth; fighter.h zback) */',
         f'#define DR_COUNT {len(M["dramas"])}            /* drama scenes (game.json dramas) */',
         'extern const gstagex_t gstagex_rom[GS_COUNT];', 'extern const uint8_t pb_of_fighter[BC_COUNT];', 'extern const gdrama_t gdramas[DR_COUNT ? DR_COUNT : 1];']
    c = ['/* Generated by tools/brawler/build_tables.py from examples/brawler/game.json. Do not edit. */',
         '#include <stddef.h>\n#include "bm_chars.h"\n#include "game_tables.h"\n#include "fighter.h"\n'] + layout_asserts()
    c.append('const ai_preset_t ai_presets_rom[AI_COUNT] = {\n' + '\n'.join(
        '    { ' + ', '.join(f'.{k} = {x}' for k, x in v.items()) + ' },   /* ' + n + ' */' for n, v in M['ai']) + '\n};')
    c += ai_rules(g)                                     # the enemies' shared rules (revamp 1B, gamedata.h gairules_t)
    m = g['meter']                                       # the drive meter + the hidden fury gauge (Bruno's redesign
    for k in m: assert k in METER_KEYS, f'meter: unknown field {k}'   # 2026-10-08, gamedata.h gmeter_t)
    assert 1 <= m['chunks'] <= 4 and 1 <= m['chunk'] and m['chunk'] * m['chunks'] < 65536, 'meter: chunks x chunk'
    assert 1 <= m['special'] <= m['chunks'] and 1 <= m['breaker'] <= m['chunks'], 'meter: costs within the bar'
    assert all(k in REFILL_PAUSE for k in m.get('refill_pause', [])), f"meter.refill_pause: {m.get('refill_pause')} (special / chain)"
    assert 1 <= m['life_breaker'] < 60 and 1 <= m['low'] <= 100 and 1 <= m['blink'] <= 60, 'meter values'
    assert 1 <= m['fury_max'] < 65536 and 0 <= m['fury_dealt'] <= 255 and 0 <= m['fury_taken'] <= 255, 'meter: the fury gauge'
    c.append(f"const gmeter_t gmeter = {{ .chunk = {m['chunk']}, .chunks = {m['chunks']}, .special = {m['special']}, "
             f".breaker = {m['breaker']}, .life_breaker = {m['life_breaker']}, .blink = {m['blink']}, .infinite = {1 if m.get('infinite') else 0}, "
             f".fury_max = {m['fury_max']}, .fury_dealt = {m['fury_dealt']}, .fury_taken = {m['fury_taken']}, .low = {m['low']}, .fury_drive = {m.get('fury_drive', 0)}, .max_drive = {m.get('max_drive', 0)}, "
             f".pause = {sum(REFILL_PAUSE[k] for k in m.get('refill_pause', []))} }};")
    bz = g['blitz']                                      # the Blitz (gamedata.h gblitz_t) and its slots per fighter
    for k in bz: assert k in BLITZ_KEYS, f'blitz: unknown field {k}'
    assert 2 <= bz['window'] <= 60 and 0 <= bz['chord'] <= 8 and 1 <= bz['damage'] < 128, 'blitz values'
    c.append(f"const gblitz_t gblitz = {{ .window = {bz['window']}, .chord = {bz['chord']}, "
             f".scale = {round(bz['damage'] * 256 / g['tiers']['special'])} }};   /* scale: {bz['damage']} / tiers.special {g['tiers']['special']} (8.8) */")
    c.append('const uint8_t gblitz_rom[BC_COUNT][4] = {\n' + ',\n'.join(
        '    { ' + ', '.join(f'0x{v:02X}' for v in row) + ' }   /* ' + n + ' */' for n, row in blitz_rows(g, build)) + '\n};')
    c.append('const uint8_t gblitz_can[BC_COUNT][4] = {\n' + ',\n'.join(
        '    { ' + ', '.join(f'0x{v:02X}' for v in row) + ' }   /* ' + n + ' */' for n, row in blitz_cancels(g)) + '\n};')
    c += run_bobs(g)
    jp = g['jump']                                       # the one jump (Cody's Final Fight arc, gamedata.h gjump_t)
    for k in jp: assert k in JUMP_KEYS, f'jump: unknown field {k}'
    n = len(jp['height']); sx = jp['x_scale'][0] / jp['x_scale'][1]
    assert n == len(jp['dx']) and 8 <= n <= 120 and all(0 <= v < 256 for v in jp['height']) and 1 <= jp['crouch'] <= 30, 'jump: the arc'
    assert 1 <= jp['land_cancel'] <= jp['land'] <= 60 and 1 <= jp['active_min'] <= 60 and jp['down_cancel'] in ('hit', 'any'), 'jump values'
    apex = jp['height'].index(max(jp['height']))
    fx8 = lambda v: max(0, min(65535, round(v * sx * 256)))
    c.append(f"static const uint8_t jump_h[{n}] = {{ {', '.join(map(str, jp['height']))} }};")
    c.append(f"static const uint16_t jump_dx[{n}] = {{ {', '.join(str(fx8(v)) for v in jp['dx'])} }};   /* 8.8 Neo Geo px (x {jp['x_scale'][0]} / {jp['x_scale'][1]}) */")
    c.append(f"const gjump_t gjump = {{ .crouch = {jp['crouch']}, .n = {n}, .apex = {apex}, .land = {jp['land']}, .land_cancel = {jp['land_cancel']}, "
             f".active_min = {jp['active_min']}, .down_any = {1 if jp['down_cancel'] == 'any' else 0}, .land_dx = {fx8(jp['land_dx'])}, .run_dx = {round(jp.get('run_dx', 1) * 256)}, "
             f".h = jump_h, .dx = jump_dx }};")
    wk = g['walk']                                       # walk / run by archetype (16.16), per fighter
    for k in wk: assert k in WALK_KEYS, f'walk: unknown field {k}'
    assert all(0.25 <= wk[k] <= 6 for k in ('fast', 'balanced', 'heavy')) and 1 <= wk['run'] <= 4, 'walk values'
    c.append('const int32_t gwalk_rom[BC_COUNT] = { ' + ', '.join(str(round(wk[r['archetype']] * 65536)) for r in g['roster']) +
             f' }};   /* 16.16 px a frame, by roster[].archetype */')
    c.append(f"const uint16_t gwalk_run = {round(wk['run'] * 256)};   /* run = walk x this (8.8) */")
    c.append(f"const uint16_t gwalk_anim = {round(wk.get('anim', 1) * 256)};   /* walk / run animation rate x this (8.8) */")
    c += depth_tables(g, build)
    ch = g['chain']                                      # the chain core (revamp 1A): the engine's rules (gchain_t)
    for k in ch: assert k in CHAIN_KEYS, f'chain: unknown field {k}'
    assert 1 <= ch['window'] <= 255 and 0 <= ch['buffer'] <= 60 and 1 <= ch['juggle_cap'] <= 255 and \
        all(1 <= ch[k] <= 255 for k in ('stun_player', 'guard_player', 'stun_light', 'stun_heavy')), 'chain values'
    assert set(ch['lengths']) == set(ch['totals']) == {'fast', 'balanced', 'heavy'} and all(2 <= v <= 6 for v in ch['lengths'].values()), 'chain lengths'
    assert len(ch['hitstop']) == 2 and 1 <= ch['hitstop'][0] <= ch['hitstop'][1] <= 60, 'chain hitstop'
    c.append(f"const gchain_t gchain = {{ .window = {ch['window']}, .buffer = {ch['buffer']}, .juggle_cap = {ch['juggle_cap']}, "
             f".stun_player = {ch['stun_player']}, .guard_player = {ch['guard_player']}, .stun_light = {ch['stun_light']}, "
             f".stun_heavy = {ch['stun_heavy']} }};")
    fl = g['super_flash']                                # the super flash (TODO #139): one rule for every fury
    for k in fl: assert k in ('about', 'start', 'freeze', 'white', 'anchor', 'white_colour', 'dark_colour', 'sound', 'sound_max'), f'super_flash: unknown field {k}'
    assert 1 <= fl['start'] <= 255 and 1 <= fl['white'] <= fl['freeze'] <= 255 and len(fl['anchor']) == 2, 'super_flash values'
    sfx = json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['sfx']['codes']   # (build = the game's build/)
    for k in ('sound', 'sound_max'):                     # sound_max: the MAX fury's (TODO #155), else sound
        assert fl.get(k, fl['sound']).upper() in [x.upper() for x in sfx], f"super_flash {k} {fl.get(k)}: not in songs.json sfx codes (the V ROM has no sample for it)"
    c.append(f"const gflash_t gflash = {{ .start = {fl['start']}, .freeze = {fl['freeze']}, .white = {fl['white']}, .sound = 0x{fl['sound']}, .sound_max = 0x{fl.get('sound_max', fl['sound'])}, .dx = {fl['anchor'][0]}, "
             f".dy = {fl['anchor'][1]}, .white_col = {fl['white_colour']}, .dark_col = {fl['dark_colour']} }};")
    hs = g['hit_sounds']                                 # the hit cycles, the guard and the boss KO sounds (gamedata.h
    for k in hs: assert k in ('about', 'light', 'strong', 'guard', 'boss_ko', 'scream_delay'), f'hit_sounds: unknown field {k}'   # ghitsnd_t)
    names = {v.upper(): int(k, 16) for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['sfx']['names'].items()}
    def code(v):
        assert v.upper() in names, f'hit_sounds: {v!r} is no songs.json sfx name (the V ROM has no sample for it)'
        return names[v.upper()]
    assert 1 <= len(hs['light']) <= 32 and 1 <= len(hs['strong']) <= 32 and 0 <= hs['scream_delay'] < 300, 'hit_sounds values (scream_delay inside main.c KO_SLOW)'
    for k in ('light', 'strong'):
        c.append(f"static const uint8_t hcycle_{k}[] = {{ {', '.join(f'0x{code(v):02X}' for v in hs[k])} }};   /* {', '.join(hs[k])} */")
    c.append(f"const ghitsnd_t ghitsnd = {{ .n = {{ {len(hs['light'])}, {len(hs['strong'])} }}, .guard = 0x{code(hs['guard']):02X}, "
             f".boss_ko = 0x{code(hs['boss_ko']):02X}, .scream_delay = {hs['scream_delay']}, .cycle = {{ hcycle_light, hcycle_strong }} }};")
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
    L = select_layout(g); slots = sorted(L, key=lambda n: L[n]['slot'])          # the stick's order (a form link's target: no slot)
    c.append('const sel_slot_t SEL_SLOT[SEL_NSLOT] = {   /* game.json select_layout: x, y (feet), z (draw order), face */\n    ' + '\n    '.join(
        f'{{ {L[n]["x"]}, {L[n]["y"]}, {L[n]["z"]}, {1 if L[n]["facing"] == "right" else -1} }},   /* {n} */' for n in slots) + '\n};')
    c.append('const uint8_t sel_fighter[SEL_NSLOT] = { ' + ', '.join(str(idx[n]) for n in slots) + ' };')
    c.append('const uint8_t sel_palbase[SEL_NSLOT] = { ' + ', '.join(map(str, sel_palbases(g, build)[0])) + ' };   /* each slot\'s first palette: back to back, its fighter\'s own count */')
    stick = g.get('select', {}).get('stick', 'positions')
    assert stick in ('positions', 'order'), f'game.json select.stick: {stick!r} (positions | order)'
    G = select_stick(L, bm_heads(build, g), stick)       # TODO #187: the cursor graph from the places
    c.append('const uint8_t sel_stick[SEL_NSLOT][2] = {   /* the cursor from each slot: right, left (build_tables.py select_stick, select.stick ' + stick + '; locked: on past it) */\n    ' + '\n    '.join(
        f'{{ {L[G[n]["right"]]["slot"]}, {L[G[n]["left"]]["slot"]} }},   /* {n}: ' + ' '.join(f'{d} {G[n][d]}' for d in SEL_DIRS) + ' */' for n in slots) + '\n};')
    vert = lambda n, k: ', '.join([str(L[m]['slot']) for m in G[n][k]] + ['0xFF'] * (len(L) - 1 - len(G[n][k])))
    c.append('const uint8_t sel_vert[SEL_NSLOT][2][SEL_NSLOT - 1] = {   /* up / down from each slot: the slots that way in preference (the first selectable wins), 0xFF none */\n    ' + '\n    '.join(
        f'{{ {{ {vert(n, "ups")} }}, {{ {vert(n, "downs")} }} }},   /* {n} */' for n in slots) + '\n};')
    unl = []
    for r in g['roster']:
        u = r.get('unlock', 'always')
        unl.append(0xFF if not r.get('selectable', True) else 0 if u == 'always' else u['boss_of_stage'])   # 0xFF: never
                                                                 # picked (a form link's target, main.c char_locked)
        assert u == 'always' or 1 <= u['boss_of_stage'] <= len(g['stages']), f'{r["name"]}: unlock {u}'
    c.append('const uint8_t roster_unlock[BC_COUNT] = { ' + ', '.join(map(str, unl)) + ' };   /* stage k + 1 whose boss unlocks it, 0 = always, 0xFF = never (a form) */')
    dmul = [r.get('damage', 1) for r in g['roster']]          # TODO #203: the fighter's damage scale (fighter.c fighter_hit)
    for r, k in zip(g['roster'], dmul): assert isinstance(k, int) and 1 <= k <= 4, f'{r["name"]}: damage {k} (1-4)'
    c += dtier_tables(g, build, dmul)                    # revamp 2: the damage tiers (the scale of a special not measured: dmul)
    c += retime_tables(g, build)
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
