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
MAX_SLOTS = 25                                           # main.c NA (an actor per slot): (381 - SEL_SPR 57 - the barriers 21) / SEL_COLS 12
SP_WALK_IN, SP_LEFT, SP_NOT_BOSS = 1, 2, 4               # gamedata.h gspawn_t.flags; rank in bits 4-7
GE_FIGHTER_NAME, GE_SPAWN = 1, 0xFF                      # gamedata.h genemy_t
GD_VERSION, GD_MAX = 7, 4096                             # gamedata.h data pack (2: + the roster section, 3: + voices, 4: + triggers, 5: + AI hop_*,
                                                         # 6: 6 roles per fighter, route trees version 3; 7: route trees version 4)
TW = {'camera_x': 1, 'wave_clear': 2, 'time': 3}         # gamedata.h TW_*, TA_*
TA = {'spawn': 1, 'lock': 2, 'music': 3, 'drama': 4, 'end_stage': 5}
TW_STAGE, MAX_TRIGGERS = 0xFF, 32
DR_LINES, DR_COLS, DR_SPEAKER = 3, 34, 16                # gamedata.h gscene_t; the name plate's length


def load(path):
    """game.json; in a Character Lab shell build (BRAWLER_SLOT=<f>, examples/brawler/Makefile LAB_SHELL / LAB_PACK) with
    the slot fighter added last (add_slot)"""
    g = json.load(open(path))
    g['stages'] = campaign(g)
    if os.environ.get('BRAWLER_SLOT'): add_slot(g, os.environ['BRAWLER_SLOT'])
    return g


def campaign(g):
    """the stages in play, in order (Bruno 2026-10-15, the beta's 4 stages): game.json stages[] without the ones switched
    off ("off": true), each with its boss from boss_order when there is one: the n-th stage in play fights the boss block
    (of any stage, on or off) whose enemy is boss_order.bosses[n] (its enemy, song, minions, drama, seed, z), at the
    stage's own boss lock and x (its length). Without boss_order each stage keeps its own boss."""
    on = [s for s in g['stages'] if not s.get('off')]
    assert on, 'stages: every stage is off'
    bo = (g.get('boss_order') or {}).get('bosses')
    if not bo: return on
    blocks = {}
    for s in g['stages']: blocks.setdefault(s['boss']['enemy'], s['boss'])
    assert len(bo) == len(on), f'boss_order: {len(bo)} bosses for {len(on)} stages in play'
    assert len(set(bo)) == len(bo), 'boss_order: a boss twice'
    out = []
    for s, e in zip(on, bo):
        assert e in blocks, f'boss_order: no stage boss block fights {e} (stages[].boss.enemy: {sorted(blocks)})'
        out.append(dict(s, boss=dict(blocks[e], lock=s['boss']['lock'], x=s['boss']['x'])))
    return out


SLOT = 'slot'                                            # the shell's slot fighter's roster name (its C prefix)
SLOT_SEC = ' __attribute__((section(".labslot")))'       # its tables of game_tables.c: the shell's fixed slot area
SLOT_RT_ROWS = 16                                        # gretime_rom rows kept for it (the rest: never matched)


def add_slot(g, f):
    """the Character Lab's shell (docs/feedback.md "Character Lab: shell and packs"): one roster entry more, last (index
    BC_COUNT - 1), a copy of fighter f's named 'slot' (slot_of = f: the exporters read f's data for it), never on the
    select screen. Everything else of the roster stays as it is, so the bytes outside the slot's regions are the same
    whoever fills the slot (tools/brawler/lab_pack.py checks it). A LAB-ONLY fighter (a roster_benched entry with "lab":
    true, LB2 Moriya 2026-10-12) takes the slot too: in no normal build (the game's bytes unchanged), only in his pack."""
    src = next((r for r in g['roster'] if r['name'] == f), None) or lab_only(g).get(f)
    assert src, f'BRAWLER_SLOT={f}: not a roster fighter nor a Lab-only one (roster_benched "lab": true)'
    assert not src.get('form'), f'BRAWLER_SLOT={f}: a form link (its other form is another roster fighter) cannot take the slot'
    r = json.loads(json.dumps(src))
    r.update(name=SLOT, slot_of=f, display=src.get('display') or f, selectable=False)
    g['roster'].append(r)


def lab_only(g):
    """{name: entry} of the Lab-only fighters: roster_benched entries with "lab": true (never exported into the game; the
    Character Lab's slot takes them: add_slot)"""
    return {r['name']: r for r in (g.get('roster_benched') or {}).get('fighters', []) if r.get('lab')}


def fighter(g, name):
    """a fighter's game.json entry by name: the roster's, else a Lab-only one's (lab_only), else None"""
    return next((r for r in g['roster'] if r['name'] == name), None) or lab_only(g).get(name)


def data_name(r):
    """the roster name a fighter's own data files use (damage_raw.json, voices.json...): the slot's source fighter's"""
    return r.get('slot_of', r['name'])


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
    U = unlocks(g)
    if U: names = [n for n in names if n in U['all']]  # the unlock ladder: only its fighters on the select screen
    if 'select_layout' in g:
        L = g['select_layout']
        if U:                                            # (renumbered: slot / z 0.. in their order)
            L = {n: dict(v) for n, v in L.items() if n in names}
            for k in ('slot', 'z'):
                for i, n in enumerate(sorted(L, key=lambda m: L[m][k])): L[n][k] = i
            if sorted(L) == sorted(U['all']):            # the places (by slot) taken in ladder order: place k = U['all'][k]
                P = [L[n] for n in sorted(L, key=lambda m: L[m]['slot'])]   # (its x, y, z, facing; the pose stays the fighter's)
                L = {n: dict(P[k], pose=L[n]['pose']) for k, n in enumerate(U['all'])}
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


LADDER_MAX = 25                                          # main.c NA: the ladder screen's actors (one a fighter)


def unlocks(g):
    """game.json "unlocks" (Bruno 2026-10-15, the beta build's unlock ladder; main.c "the unlock ladder") checked: None
    (no block: every selectable fighter from the start, a boss by its roster unlock boss_of_stage) or {starters, ladder,
    rung_size, rungs: [[fighter]], all: starters + ladder}. starters: playable from the start; ladder: the fighters
    unlocked in this order, rung_size at a time, one rung per game clear (the last stage's boss beaten); every other
    roster fighter is off the select screen (an enemy only). Each must be a selectable roster fighter."""
    u = g.get('unlocks')
    if not u: return None
    for k in u: assert k in ('about', 'starters', 'ladder', 'rung_size', 'screen'), f'unlocks: unknown field {k}'
    names = [r['name'] for r in g['roster'] if r.get('selectable', True)]
    st, la, n = list(u.get('starters') or []), list(u.get('ladder') or []), u.get('rung_size')
    assert isinstance(n, int) and 1 <= n <= 6, f'unlocks.rung_size {n!r}: 1-6'
    assert st, 'unlocks.starters: at least one fighter'
    assert len(la) % n == 0, f'unlocks.ladder: {len(la)} fighters, not whole rungs of {n}'
    al = st + la
    dup = sorted({f for f in al if al.count(f) > 1})
    assert not dup, f'unlocks: {", ".join(dup)} twice'
    for f in al: assert f in names, f'unlocks: {f} is not a selectable roster fighter'
    assert len(al) <= LADDER_MAX, f'unlocks: {len(al)} fighters, {LADDER_MAX} at most (main.c NA)'
    scr = u.get('screen') or {}
    for k, v in scr.items(): assert k in LADDER_SCREEN and isinstance(v, int), f'unlocks.screen.{k} {v!r} (feet, from, to: px)'
    return {'starters': st, 'ladder': la, 'rung_size': n, 'rungs': [la[i:i + n] for i in range(0, len(la), n)], 'all': al, 'screen': scr}


def select_layers(g, L=None):
    """the select screen's layouts by unlocked count (Bruno 2026-10-15: "only the available characters show up"):
    [(n, base, Ln)] per layer. No unlocks block: one layer, every slot (n = all, base 0, L). With the unlock ladder:
    layer r = r rungs unlocked (0 .. len(rungs)); its n = starters + r x rung_size fighters = the first n of the ladder
    order (slots 0 .. n - 1), standing on n CONSECUTIVE places of the full layout, centred: places base .. base + n - 1
    (the places in slot order = along the street), base = (all - n) // 2. The layout's left half faces right, its right
    half left, so a centred run still faces the middle. Ln = {fighter: its place} (slot 0 .. n - 1, z renumbered 0 ..):
    the layer's own cursor graph (select_stick) is computed on it; main.c draws only those n (a locked one is not drawn)."""
    L = L or select_layout(g); U = unlocks(g); order = sorted(L, key=lambda n: L[n]['slot'])
    if not U: return [(len(L), 0, L)]
    assert order == U['all'], f'select_layout: the slots must follow the ladder order {U["all"]} (got {order})'
    out = []
    for r in range(len(U['rungs']) + 1):
        n = len(U['starters']) + r * U['rung_size']; base = (len(order) - n) // 2
        Ln = {f: dict(L[order[base + k]], slot=k, pose=L[f]['pose']) for k, f in enumerate(order[:n])}
        for i, f in enumerate(sorted(Ln, key=lambda m: Ln[m]['z'])): Ln[f]['z'] = i
        out.append((n, base, Ln))
    return out


LADDER_SCREEN = {'feet': 200, 'from': 46, 'to': 289}     # unlocks.screen defaults (ladder_places)


def ladder_places(U, scr=None):
    """the unlock ladder screen's places (main.c ladder_start; Bruno 2026-10-15: "every character on the same horizontal
    axis"): every ladder fighter (starters, then the rungs) on ONE line, feet at screen y `feet`, in ladder order left to
    right, evenly spaced from screen x `from` to `to` (their feet; the TV shows x 8-311), each in its select pose facing
    the middle; drawn from the ends inward (the middle ones in front where the bodies overlap) -> [(fighter, rung 0 =
    starters, x, y, z, face)]"""
    s = dict(LADDER_SCREEN, **(scr or {})); al = U['all']; n = len(al); out = []
    rung = {f: 0 for f in U['starters']}
    for k, c in enumerate(U['rungs']): rung.update({f: k + 1 for f in c})
    for k, f in enumerate(al):
        x = round(s['from'] + (s['to'] - s['from']) * k / (n - 1)) if n > 1 else (s['from'] + s['to']) // 2
        out.append([f, rung[f], x, s['feet'], 0, 1 if 2 * k < n - 1 else -1])
    for z, e in enumerate(sorted(out, key=lambda e: (-abs(2 * al.index(e[0]) - (n - 1)), e[2]))): e[4] = z
    return [tuple(e) for e in out]


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
    n = [int(a) for a in re.findall(r'^\s*\{(?:"[^"]*"|slot_name), (\d+), \d+,', t, re.M)]
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
    L = select_layout(g) if r.get('selectable', True) or r.get('slot_of') else {}
    pose = L[data_name(r)]['pose'] if data_name(r) in L else w
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
    for k in fin: assert k in ('launcher', 'down', 'neutral', 'forward', 'up', 'down_move', 'df_move'), f"roster {r['name']}: finishers.{k}"
    own = r.get('chain') or {}                     # (revamp 5, the chain tool's save) links: the moves before the finisher,
    for k in own: assert k in ('links', 'hitstop', 'length'), f"roster {r['name']}: chain.{k} (links / hitstop / length)"   # hitstop: per link + the finisher
    air = air_of(r)                                  # its three air attacks (Bruno 2026-10-08): forward jump + A, straight
    for k in air: assert k in AIR_DEFAULT or k == 'back', f"roster {r['name']}: air.{k} (forward / straight / down / back)"   # jump + A, down + A
                                                     # (back: back + A in any jump, note 20261011-210422-5d29; absent = none)
    n = own.get('length', 4)                         # (Bruno 2026-10-10: "4 by default, I add / remove presses": the archetype no
                                                     # longer sets the length; every fighter's own chain.length, 4 when absent)
    assert isinstance(n, int) and 2 <= n <= 8, f"roster {r['name']}: chain.length {n} (2-8)"
    return {'archetype': a, 'length': n, 'total': c['totals'][a], 'hitstop': c['hitstop'], 'finishers': fin,
            'air': air, 'specials': r.get('specials') or {},          # (revamp gold: a finisher named as a special input)
            **({'dash': blitz_normal(r)} if blitz_normal(r) else {}),     # (a normal as a Blitz: the tree's blitz entry plays it)
            'damage': r.get('damage', 1), **({'links': own['links']} if 'links' in own else {}),
            **({'hitstops': own['hitstop']} if 'hitstop' in own else {})}


BLITZ_NORMAL = re.compile(r'^(atk_[a-d]{1,2}_(close|far|crouch)|body_toss|cmd_\w+)$')   # a Blitz slot naming a ground normal


def blitz_normal(r):
    """the ground normal a roster entry's Blitz names (roster[].blitz: a move name, arb_compile's 'a normal as the Blitz';
    at most one: the tree's blitz entry plays it, routes.chain_tree cfg 'dash'), else None"""
    ns = {v for v in (r.get('blitz') or {}).values() if isinstance(v, str) and BLITZ_NORMAL.match(v)}
    assert len(ns) <= 1, f"roster {r['name']}: blitz names two normals {sorted(ns)} (one dash entry)"
    return ns.pop() if ns else None


def blitz_rows(g, build):
    """gblitz_rom: per roster fighter (bm_chars order) its four Blitz slots (roster[].blitz ff / dd / du / uu): a special of
    its pool (its index; build/chainlab.json fighters[].pool, export_bm special_pool order), 'dash' = 0xFE (its tree's dash
    entry), a normal's move name = 0xFD (its tree's blitz entry: routes.chain_tree), absent = 0xFF; a fighter without roster[].blitz: ff = 'dash', the others none (Bruno 2026-10-08)"""
    fl = json.load(open(os.path.join(build, 'chainlab.json')))['fighters']
    pools = {f['name']: [None if p.get('seq') else p['input'] for p in f['pool']] for f in fl}   # (a sequence's pieces: by their slot)
    seqs = {f['name']: {p['seq']: i for i, p in enumerate(f['pool']) if p.get('seq') and p['seq_i'] == 0} for f in fl}
    out = []
    for r in g['roster']:
        bz = r.get('blitz') or {'ff': 'dash'}
        for k in bz: assert k in BLITZ_SLOTS, f"roster {r['name']}: blitz.{k} (ff / dd / du / uu)"
        row = []
        for k in BLITZ_SLOTS:
            v = bz.get(k)
            if v is None: row.append(0xFF)
            elif isinstance(v, list):                                       # a SEQUENCE (export_bm.sequences): its first
                assert f'blitz.{k}' in seqs[r['name']], f"roster {r['name']}: blitz.{k} {v}: no sequence in its pool"   # piece
                row.append(seqs[r['name']][f'blitz.{k}'])
            elif v == 'dash': row.append(0xFE)                             # BZ_DASH: the tree's dash entry
            elif BLITZ_NORMAL.match(v): row.append(0xFD)                    # BZ_NORMAL: a normal's move name, the tree's
                                                                            # blitz entry (rt_head_t.pad[0]) plays it
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


def blitz_slides(g):
    """gblitz_slide: per roster fighter (bm_chars order) per Blitz slot (BZ_FF .. BZ_UU) its slide [frames, v0, dv]
    (roster[].blitz_slide {slot: {px, frames}}; Bruno 2026-10-14, note 20261014-192939-5d29: "for the forward-forward A
    blitz, in addition to this move, add a small sliding forward motion"): from the Blitz's start the fighter glides px
    forward over frames frames, fast first and slowing to a stop (fighter.c blitz_slide), on top of the move's own motion;
    a hit-stop holds it, any other state (a cancel, a hit taken) ends it; v0 = the first frame's glide 2 px / (frames + 1)
    and dv = v0 / frames what it loses a frame (16.16 px: the 68000 has no 32-bit divide); absent = [0, 0, 0] (none)"""
    out = []
    for r in g['roster']:
        bz = r.get('blitz') or {'ff': 'dash'}; row = [[0, 0, 0] for _ in BLITZ_SLOTS]
        for k, v in (r.get('blitz_slide') or {}).items():
            assert k in BLITZ_SLOTS and k in bz, f"roster {r['name']}: blitz_slide.{k}: not one of its Blitz slots"
            assert set(v) <= {'px', 'frames', 'about'}, f"roster {r['name']}: blitz_slide.{k}: px / frames"
            assert 1 <= v['px'] <= 127 and 1 <= v['frames'] <= 60, f"roster {r['name']}: blitz_slide.{k}: px 1-127, frames 1-60"
            v0 = round(2 * v['px'] * 65536 / (v['frames'] + 1))           # frame k glides v0 - k dv (16.16 px)
            row[BLITZ_SLOTS.index(k)] = [v['frames'], v0, v0 // v['frames']]
        out.append((r['name'], row))
    return out


RUN_KEYS = ('hold_last', 'float', 'last_step', 'mode', 'dash', 'air_buttons', 'speed', 'about')
def run_bobs(g):
    """grun_bob: per roster fighter its run's float (roster[].run.float {px, period}; Bruno 2026-10-09, note
    20261009-102625-5d29: Kim floats up and down a few pixels as he runs): one height a frame (px above its feet, drawn
    only: main.c draw), px x (1 - cos) / 2 over period frames, from 0 (no pop as the run starts); none = 0.
    grun_dash: roster[].run.mode "dash" (note 20261009-102625-5d29 reopened on 0.10.8: "a dash motion, the kind of dash
    we had in KOF94 / 95; dash and run are two different things"): forward, forward = one burst over a fixed distance
    that ends on its own, not a run. run.dash {start, frames, dx, height}: start frames on the ground (the crouch), then
    frames in the air covering dx px at a steady speed on a parabola height px high (drawn only, like the float), then
    the animation's last step (the landing) and back to neutral: [start, frames, x1..xF (px from the take-off),
    h1..hF, air]; the export stretches the run animation's airborne step to match (export_kz, export_dd); none = 0.
    run.air_buttons (note 20261011-114113-5d29, Double Dragon's fighters): air = 1, the dash's airborne frames count as
    a jump for the buttons (fighter.c dash_air: A / C play his air moves, the rest of the course in the air), else 0"""
    out, refs, drefs = [], [], []
    for r in g['roster']:
        run = r.get('run') or {}
        for k in run: assert k in RUN_KEYS, f"roster {r['name']}: run.{k} ({' / '.join(RUN_KEYS)})"
        assert run.get('mode', 'run') in ('run', 'dash'), f"roster {r['name']}: run.mode {run['mode']} (run / dash)"
        assert run.get('air_buttons') in (None, True, False) and (not run.get('air_buttons') or run.get('mode') == 'dash'), \
            f"roster {r['name']}: run.air_buttons: true / false, only with mode dash"
        if run.get('mode') == 'dash':
            d = run['dash']
            assert set(d) == {'start', 'frames', 'dx', 'height'} and 0 <= d['start'] <= 8 and 4 <= d['frames'] <= 60 and \
                1 <= d['dx'] <= 255 and 0 <= d['height'] <= 32 and not run.get('float') and not run.get('hold_last'), \
                f"roster {r['name']}: run.dash {d} (start 0-8, frames 4-60, dx 1-255, height 0-32; no float / hold_last)"
            F = d['frames']
            xs = [round(d['dx'] * i / F) for i in range(1, F + 1)]
            hs = [round(d['height'] * 4 * i * (F - i) / (F * F)) for i in range(1, F + 1)]
            out.append(f"static const uint8_t gdash_{r['name']}[{3 + 2 * F}]{SLOT_SEC if r.get('slot_of') else ''} = {{ {d['start']}, {F}, {', '.join(map(str, xs + hs + [int(bool(run.get('air_buttons')))]))} }};")
            drefs.append(f"gdash_{r['name']}")
        else: drefs.append('0')
        fl = run.get('float')
        if not fl: refs.append('0'); continue
        assert set(fl) == {'px', 'period'} and 1 <= fl['px'] <= 16 and 4 <= fl['period'] <= 120, f"roster {r['name']}: run.float {fl}"
        h = [round(fl['px'] * (1 - math.cos(2 * math.pi * i / fl['period'])) / 2) for i in range(fl['period'])]
        out.append(f"static const uint8_t grun_{r['name']}[{fl['period'] + 1}]{SLOT_SEC if r.get('slot_of') else ''} = {{ {fl['period']}, {', '.join(map(str, h))} }};")
        refs.append(f"grun_{r['name']}")
    return out + ['const uint8_t *const grun_bob[BC_COUNT] = { ' + ', '.join(refs) + ' };   /* the run\'s float per fighter: '
                  '[period, height a frame...] (roster[].run.float), 0 = none */',
                  'const uint8_t *const grun_dash[BC_COUNT] = { ' + ', '.join(drefs) + ' };   /* the dash per fighter: '
                  '[start, frames, x a frame..., height a frame..., air_buttons] (roster[].run.mode dash), 0 = a run */']


def run_anim(wk, r):
    """the run animation's rate relative to the walk's (8.8; note 20261014-141702-5d29, Genjuro: "the run animation is
    playing too fast"): the walk's rate (fighter.c walk_rate) = the walk speed / the source's walk x walk.anim, the 1.5
    boost Bruno chose for the WALK (2026-10-08); the run had it too, so its steps went by at the source's own pace (SS2
    Genjuro: 3 frames a step, as SS2) while the body covers 3.25 px a frame instead of SS2's 5.09: the legs spun. The
    run plays at walk.run_anim instead of walk.anim (1: the source's stride on the floor, the feet keep their ground).
    A roster[].walk_rate fighter keeps its fixed rate for both (Final Fight's: its source has no run). roster[].run_anim
    overrides walk.run_anim for a source whose run is not twice its walk (the brawler's walk.run): the feet keep their
    ground at walk.run x the source's walk / the source's run (note 20261014-164517-5d29, LB2 Moriya: walk 2.125, run
    3.0 px a frame [meas] -> 1.42)"""
    if 'walk_rate' in r: return 256
    ra = r.get('run_anim', wk.get('run_anim', wk.get('anim', 1)))
    assert isinstance(ra, (int, float)) and 0.25 <= ra <= 4, f"roster {r['name']}: run_anim {ra} (0.25-4)"
    return round(ra / wk.get('anim', 1) * 256)


def run_speed(r):
    """roster[].run.speed (note 20261014-141702-5d29, Bruno on SS2 Genjuro: "check frame by frame"): the run moves at its
    source's own measured speed (px a frame) and its animation plays at its steps' own ticks (fighter.c run_rate 0x100):
    the source's run frame for frame, its feet on the floor. -> 16.16, 0 = the rule (the walk x walk.run, run_anim)"""
    v = (r.get('run') or {}).get('speed')
    if v is None: return 0
    assert isinstance(v, (int, float)) and 1 <= v <= 12 and (r.get('run') or {}).get('mode', 'run') == 'run', \
        f"roster {r['name']}: run.speed {v} (1-12 px a frame, a run)"
    return round(v * 65536)


def walk_phys(g, r):
    """roster[].walk_rate (note 20261014-084140-5d29, Final Fight's Haggar: "the walk plays too fast"): the walk / run
    animations' rate, fixed (1 = its steps' own ticks, the source's measured cadence) instead of the engine's rule (its
    archetype's speed / its source's walk x walk.anim, fighter.c walk_rate). -> the bphys_t walk (px a frame) that makes
    the rule give it: archetype speed x walk.anim / walk_rate"""
    w = r['walk_rate']
    assert isinstance(w, (int, float)) and 0.25 <= w <= 4, f"roster {r['name']}: walk_rate {w} (0.25-4)"
    wk = g['walk']
    return wk[r['archetype']] * wk.get('anim', 1) / w


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
             **({'walk_phys': walk_phys(g, r)} if 'walk_rate' in r else {}),
             **{k: r[k] for k in ('form', 'stage_end_form', 'display', 'variant', 'scale', 'moves', 'anim_specials', 'fire', 'flash_pose', 'charge_from', 'air_specials', 'blitz', 'down_attack', 'invincible', 'juggle', 'source_flight', 'keeps_air_attack', 'together', 'seq_press', 'seq_hit', 'hit_next', 'nopush', 'max', 'proj_hits', 'special_final_area', 'run', 'slot_of', 'swing', 'win_fx_off') if k in r}} for r in g['roster']]


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
    M['win_drama'] = dr_idx[g['win_drama']] if g.get('win_drama') else 0xFF   # the stage clear's (after the win poses)
    assert g.get('win_drama') is None or all(sc['who'] for sc in M['dramas'][M['win_drama']][1]), 'win_drama: "$P1" / "$P2" scenes only'
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
        for k in e: assert k in ('name', 'base', 'pool', 'stand_in', 'life', 'power', 'ai', 'attract_ai', 'ai_over', 'palette', 'moves', 'hud', 'boss_ai'), f'enemy {n}: unknown field {k}'
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
    def spawn(d, where, lock):
        e = d['enemy']; assert e in en_idx, f'{where}: no enemy {e}'
        fl, x = 0, d.get('x', 0)
        # (voice note 20261014-192343-5d29: "the enemies are popping on the screen") nobody appears inside the screen: a
        # world-x spawn lies outside the camera at its lock point (lock-24 .. lock+340, main.c spawn_x's walk-in edges)
        assert 'walk_in' in d or not (lock - 24 < x < lock + 340), \
            f'{where}: x {x} is inside the screen at lock {lock}: use walk_in (or an x outside {lock - 24}..{lock + 340})'
        if 'walk_in' in d:
            w = d['walk_in']; fl |= SP_WALK_IN | (SP_LEFT if w['side'] == 'left' else 0) | (w.get('rank', 0) << 4)
            assert w['side'] in ('left', 'right') and 0 <= w.get('rank', 0) < 16, where
        if d.get('not_boss'): fl |= SP_NOT_BOSS
        return {'enemy': en_idx[e], 'pick': d.get('pick', 0), 'set': d.get('set', 0), 'tint': tint_idx[d.get('tint', 'none')],
                'x': x, 'z': d['z'], 'flags': fl}
    for si, s in enumerate(g['stages']):
        assert re.fullmatch(STAGE_NAME, s['name']), f'stage {si + 1}: name {s["name"]!r}: 1-12 characters (A-Z 0-9 space . ! -)'
        ww = widths[s['background']] if widths else None
        sp, wv = [], []
        for wi, w in enumerate(s['waves']):
            assert 1 <= len(w['spawns']) <= MAX_ENEMIES, f'stage {si + 1} wave {wi + 1}: 1-{MAX_ENEMIES} spawns'
            assert ww is None or 0 <= w['lock'] <= ww - 320, f'stage {si + 1} wave {wi + 1}: lock {w["lock"]} outside 0-{ww - 320}'
            assert wi == 0 or w['lock'] >= s['waves'][wi - 1]['lock'], f'stage {si + 1}: lock points go forward'
            wv.append({'lock': w['lock'], 'seed': int(str(w['seed']), 0), 'first': len(sp), 'n': len(w['spawns'])})
            sp += [spawn(d, f'stage {si + 1} wave {wi + 1}', w['lock']) for d in w['spawns']]
        b = s['boss']; nb = len(sp)
        assert len(b['minions']) <= MAX_ENEMIES - 1, f'stage {si + 1}: at most {MAX_ENEMIES - 1} minions with the boss'
        assert ww is None or b['lock'] <= ww - 320, f'stage {si + 1}: boss lock past the end'
        sp += [spawn(d, f'stage {si + 1} boss', b['lock']) for d in b['minions']]
        trig = [trigger(t, f'stage {si + 1} trigger {k + 1}', len(s['waves']), en_idx, tint_idx, mus, dr_idx, ww)
                for k, t in enumerate(s.get('triggers', []))]
        assert len(trig) <= MAX_TRIGGERS, f'stage {si + 1}: at most {MAX_TRIGGERS} triggers'
        assert b.get('drama') is None or b['drama'] in dr_idx, f'stage {si + 1}: no drama {b.get("drama")}'
        be = enemies[en_idx[b['enemy']]]
        unl = 1 if be['base'] in idx and g['roster'][idx[be['base']]].get('unlock') == {'boss_of_stage': si + 1} and not g.get('unlocks') else 0
                                                         # (the unlock ladder: no other unlock, no BOSS UNLOCKED)
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
            for f in sc: assert f in ('speaker', 'side', 'portrait', 'lines', 'lines_by', 'wait', 'if_portrait'), f'{w}: unknown field {f}'
            who = {'$P1': 1, '$P2': 2}.get(sc['speaker'], 0)
            p = sc.get('portrait')
            assert p is None or (p in ports and not who), f'{w}: no portrait {p} (game.json portraits: {ports}; "$P1" / "$P2" use their own)'
            assert sc.get('side', 'right') in ('left', 'right'), f'{w}: side'
            by = dict(sc.get('lines_by', {}))
            assert not by or who, f'{w}: lines_by only for "$P1" / "$P2"'
            assert not sc.get('if_portrait') or who, f'{w}: if_portrait only for "$P1" / "$P2"'
            assert not ('lines' in sc and '*' in by), f'{w}: lines and lines_by "*" both give the default'
            lines = sc['lines'] if 'lines' in sc else by.pop('*', None)
            assert lines is not None, f'{w}: lines (or lines_by "*"): the lines of every other fighter'
            names = [r['name'] for r in g['roster']]
            for k in by: assert k in names, f'{w}: lines_by {k}: not a roster fighter'
            for ls in [lines] + list(by.values()):
                assert len(ls) <= DR_LINES and (ls or sc.get('if_portrait')), f'{w}: 1-{DR_LINES} lines (0: an if_portrait scene)'
                for t in ls: assert all(0x20 <= ord(c) < 0x7F for c in t) and len(t) <= DR_COLS, f'{w}: {t!r}: ASCII, at most {DR_COLS} characters'
            assert all(0x20 <= ord(c) < 0x7F for c in sc['speaker']) and 1 <= len(sc['speaker']) <= DR_SPEAKER, f'{w}: speaker 1-{DR_SPEAKER} characters'
            wait = sc.get('wait', 120); assert 0 <= wait <= 32767, f'{w}: wait (ticks)'
            rows.append({'portrait': 0xFF if p is None else ports.index(p), 'side': 1 if sc.get('side', 'right') == 'right' else 0,
                         'speaker': sc['speaker'], 'lines': lines, 'wait': wait, 'who': who, 'if_portrait': 1 if sc.get('if_portrait') else 0,
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
STAGE_NAME = r'[A-Z0-9 .!-]{1,12}'                      # a stage's name: the HUD (main.c hud_wave) + GAME OVER, fix font
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
              'fury_taken', 'low', 'infinite', 'fury_drive', 'max_drive', 'refill_pause', 'special_flash')
REFILL_PAUSE = {'special': 1, 'chain': 2, 'blitz': 4}            # gamedata.h RP_*: meter.refill_pause names
BLITZ_KEYS = ('about', 'window', 'chord', 'damage')
BLITZ_SLOTS = ('ff', 'dd', 'du', 'uu')               # fighter.h BZ_*: forward,forward / down,down / down,up / up,up + A
JUMP_KEYS = ('about', 'crouch', 'height', 'dx', 'land_dx', 'x_scale', 'land', 'land_cancel', 'active_min', 'down_cancel', 'run_dx')
WALK_KEYS = ('about', 'fast', 'balanced', 'heavy', 'run', 'anim', 'run_anim')
AIR_DEFAULT = {'forward': 'atk_d_jump', 'straight': 'atk_c_jump', 'down': 'atk_a_jump'}   # roster[].air (Bruno 2026-10-08:
                                                    # forward jump D, straight jump C, down + A jump A or the closest)
AIR_BANK = {'samsho2': {'forward': 'atk_cd_jump', 'straight': 'atk_cd_jump', 'down': 'atk_ab_jump'}}   # a bank game's own
                                                    # standard (Bruno 2026-10-11, voice note 20261011-112029-5d29: every SS2
                                                    # fighter's jump + A = SS2's air A+B, jump + down + A = its air C+D, the
                                                    # high kick; tools/samsho2/export_ss2.py air_moves exports those names)


def air_of(r):
    """a roster entry's three air attacks: AIR_DEFAULT, its bank game's AIR_BANK, its own roster[].air (in that order)"""
    return {**AIR_DEFAULT, **AIR_BANK.get(str(r.get('bank', '')).split(':')[0], {}), **(r.get('air') or {})}
TIER_KEYS = ('about', 'special', 'fury', 'max', 'super_throw', 'spread', 'measured')


TBODY_KEYS = ('about', 'damage', 'hitstop', 'body_hitstop', 'floor', 'depth', 'sound', 'players')
TBODY_KINDS = {'throw_c': 'BT_THROW_C', 'throw_d': 'BT_THROW_D', 'throw_x': 'TBK_XTHROW', 'special': 'TBK_SPECIAL'}


def tbody_tables(g, build):
    """the thrown body (Bruno's note 20261014-132326-5d29, "like in Final Fight"; gamedata.h gtbody_t, fighter.c "thrown
    bodies"): game.json "throw_body" = the game's rule (every throw of every fighter), roster[].throws.body = per-throw
    overrides {"throw_c" | "throw_d" | "throw_x" | "special": {fields to change} | false (that throw's body hits nobody)}.
    Fields: damage, hitstop (the one hit), body_hitstop (the body's own), floor (frames it still hits once on the floor:
    the impact), depth (px), sound (songs.json sfx code), players (bool: thrown bodies hit players too)"""
    tb = g.get('throw_body')
    sfx = json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['sfx']['codes']
    def row(d, base, what):
        if d is False: return dict(base, on=0)
        assert isinstance(d, dict), f'{what}: an object or false'
        for k in d: assert k in TBODY_KEYS, f'{what}: unknown field {k}'
        r = dict(base, on=1)
        for k, f in (('damage', 'dmg'), ('hitstop', 'stop'), ('body_hitstop', 'bstop'), ('floor', 'floor'), ('depth', 'depth')):
            if k in d:
                hi = 127 if k == 'floor' else 255
                assert isinstance(d[k], int) and 0 <= d[k] <= hi, f'{what}.{k}: 0-{hi}'
                r[f] = d[k]
        if 'sound' in d:
            assert str(d['sound']).upper() in [x.upper() for x in sfx], f"{what}.sound {d['sound']}: not in songs.json sfx codes"
            r['snd'] = int(str(d['sound']), 16)
        if 'players' in d: r['players'] = 1 if d['players'] else 0
        return r
    lit = lambda r: (f"{{ .on = {r['on']}, .dmg = {r['dmg']}, .stop = {r['stop']}, .bstop = {r['bstop']}, .floor = {r['floor']}, "
                     f".depth = {r['depth']}, .snd = 0x{r['snd']:02X}, .players = {r['players']} }}")
    # (absent: the rule before the note: 6 damage, hit-stop 7, the flight only, 12 px, $15, players never)
    base = row(tb if tb is not None else {}, dict(on=1, dmg=6, stop=7, bstop=0, floor=0, depth=12, snd=0x15, players=0), 'throw_body')
    c = [f'const gtbody_t gtbody = {lit(base)};']
    ov = []
    for i, r in enumerate(g['roster']):
        b = (r.get('throws') or {}).get('body')
        if b is None: continue
        assert isinstance(b, dict), f"{r['name']}: throws.body = {{kind: {{...}} | false}}"
        for k, d in b.items():
            assert k in TBODY_KINDS, f"{r['name']}: throws.body.{k}: one of {', '.join(TBODY_KINDS)}"
            ov.append(f"{{ {i}, {TBODY_KINDS[k]}, {lit(row(d, base, r['name'] + ': throws.body.' + k))} }}")
    ov.append('{ 0xFF, 0, { 0 } }')
    c.append('const gtbody_ovr_t gtbody_ovr[] = { ' + ', '.join(ov) + ' };')
    return c


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
        pool = [p['input'] for p in lab[n]['pool']]; m = raw.get(data_name(r)) or {}
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
        if isinstance(fury, list): fury = ' > '.join(fury)   # (a fury SEQUENCE, note 20261014-171937-5d29: measured as one
                                                         #  move under this name, damage_tiers.py)
        if fury and not mx:                              # one measured as it (TODO #152's other button), else the fury
            mm = (m.get('max') or {}).get('input') or ''
            mx = 'MAX ' + fury if 'MAX ' + fury in pool else mm if mm.startswith('MAX ') and mm in pool else fury
        sup = (r.get('throws') or {}).get('super')        # the super throw's special (revamp 3; a paired one: its tier as is)
        fs = r.get('fury_damage_scale', 1)               # roster[].fury_damage_scale: this fighter's fury and MAX deal their
        assert isinstance(fs, (int, float)) and 0.5 <= fs <= 4, f'{n}: fury_damage_scale {fs} (0.5-4)'   # tier times it
        ms = r.get('max_damage_scale', fs)               # roster[].max_damage_scale: the MAX's own (default: the fury's)
        assert isinstance(ms, (int, float)) and 0.5 <= ms <= 4, f'{n}: max_damage_scale {ms} (0.5-4)'
        for k, j, tg, inp in (('fury', 0, round(t['fury'] * fs), fury), ('max', 1, round(t['max'] * ms), mx),
                              ('super_throw', 2, t['super_throw'], sup if sup in pool else None)):
            d = own(inp) if inp else None
            if d: v[len(pool) + j] = sc(tg, d)
            e[k] = {'input': inp, 'own': d, 'target': tg, 'scale': v[len(pool) + j] / 256}
        c.append(f'static const uint16_t dtier_{i}[{len(v)}]{SLOT_SEC if r.get("slot_of") else ""} = {{ {", ".join(map(str, v))} }};   /* {n} */')
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
            for ix in [idx] + ([len(ba) + j for j, q in enumerate(pool) if q == move and len(ba) + j != idx] if move not in ba else []):
                k = len(rows)                            # (every pool entry of that special: a sequence's piece too,
                                                         #  export_bm.sequences, Bruno 2026-10-11)
                c.append(f'static const uint16_t gretime_t{k}[]{SLOT_SEC if r.get("slot_of") else ""} = {{ {", ".join(map(str, T))} }};   /* {r["name"]} {move}: {segs} -> {T} */')
                rows.append(f'    {{ {i}, {len(T)}, {ix}, gretime_t{k} }},')
                rep.append({'fighter': r['name'], 'move': move, 'index': ix, 'segments': segs, 'targets': T, 'spec': spec, 'hand_check': warn})
    if any(r.get('slot_of') for r in g['roster']):      # the shell: the slot's rows (last) padded to SLOT_RT_ROWS with
        ns = sum(1 for e in rep if e['fighter'] == SLOT)  # rows no fighter matches (0xFE), so the table's size and the
        assert ns <= SLOT_RT_ROWS, f'retime: the slot has {ns} retimed moves, the shell keeps {SLOT_RT_ROWS}'   # rows stay
        rows += ['    { 0xFE, 0, 0, 0 },'] * (SLOT_RT_ROWS - ns)
    c.append('const gretime_t gretime_rom[] = {   /* (fighter.c "retiming") the moves given targets: fighter, segments, move, targets */\n'
             + ''.join(x + '\n' for x in rows) + '    { 0xFF, 0, 0, 0 }\n};')
    json.dump(rep, open(os.path.join(build, 'retime.json'), 'w'), indent=1)
    return c


RULE_KEYS = ('about', 'attackers', 'approach_max', 'ready', 'windup', 'rank')

# ---- T9 (Bruno 2026-10-15, tougher bosses): ai.guard (the guard's engine rules, fighter.c "guard") and enemies[].boss_ai
# (a boss's own layer, ai.c "the boss layer"; gamedata.h gbossai_t) ----
GUARD_KEYS = ('about', 'stun', 'push', 'chip')
BOSS_KEYS = {'about': None, 'guard': ('chance', 'dx', 'dz', 'hold', 'max', 'rest'), 'run': ('chance', 'from', 'stop'),
             'grab': ('immune', 'counter', 'delay'), 'red': ('low', 'rest', 'dx', 'max'), 'combos': None, 'ready_shift': None}
CO_KINDS = {'A': 1, 'C': 2, 'D': 3, 'run': 4, 'jump': 5, 'grab': 6}    # gamedata.h CO_*
CO_STICKS = {'': 0, 'f': 1, 'b': 2, 'u': 3, 'd': 4, 'df': 5, 'uf': 6}  # gamedata.h CS_*
BC_MAX, BC_OPS = 10, 8


def combo_ops(text, where):
    """a combo string ("A A fA C", "run A", "jump A A", "A dC D", "grab") -> its op bytes (CO_* | CS_* << 3)"""
    ops = []
    for t in text.split():
        if t in ('run', 'jump', 'grab'): ops.append(CO_KINDS[t]); continue
        m = re.fullmatch(r'(df|uf|f|b|u|d)?([ACD])', t)
        assert m, f'{where}: {t!r} (A / C / D after an optional stick f b u d df uf, or run / jump / grab)'
        ops.append(CO_KINDS[m.group(2)] | CO_STICKS[m.group(1) or ''] << 3)
    assert 1 <= len(ops) <= BC_OPS, f'{where}: 1-{BC_OPS} presses'
    assert all((o & 7) not in (4, 5) for o in ops[1:]), f'{where}: run / jump only first'
    assert all((o & 7) != 6 for o in ops[:-1]), f'{where}: grab only last'
    return ops


def boss_ai(e, n):
    """enemies[].boss_ai -> the gbossai_t fields (None: no boss layer)"""
    b = e.get('boss_ai')
    if not b: return None
    for k in b: assert k in BOSS_KEYS, f'enemy {n}: boss_ai.{k}'
    for k, ks in BOSS_KEYS.items():
        if ks: assert all(x in ks or x == 'about' for x in b.get(k, {})), f'enemy {n}: boss_ai.{k}: {list(b.get(k, {}))} ({ks})'
    g, r, gr, rd = b.get('guard', {}), b.get('run', {}), b.get('grab', {}), b.get('red', {})
    v = {'guard_chance': g.get('chance', 0), 'guard_dx': g.get('dx', 80), 'guard_dz': g.get('dz', 12), 'guard_hold': g.get('hold', 16),
         'guard_max': g.get('max', 3), 'guard_rest': g.get('rest', 30), 'run_chance': r.get('chance', 0), 'run_from': r.get('from', 100),
         'run_stop': r.get('stop', 44), 'grab_immune': gr.get('immune', 0), 'grab_counter': gr.get('counter', 0),
         'counter_delay': gr.get('delay', 8), 'red_low': rd.get('low', 0), 'red_rest': (rd.get('rest', 480) + 3) >> 2, 'red_dx': rd.get('dx', 100),
         'red_max': rd.get('max', 1), 'ready_shift': b.get('ready_shift', 0)}
    assert 0 <= rd.get('rest', 480) <= 1020, f'enemy {n}: boss_ai.red.rest: 0-1020 frames (kept in 4-frame units)'
    for k, x in v.items(): assert isinstance(x, int) and 0 <= x <= 255, f'enemy {n}: boss_ai {k} = {x} (0-255)'
    assert v['grab_immune'] + v['grab_counter'] <= 256, f'enemy {n}: boss_ai.grab immune + counter <= 256'
    assert v['red_low'] <= 100, f'enemy {n}: boss_ai.red.low: a % of its life'
    assert v['ready_shift'] <= 5, f'enemy {n}: boss_ai.ready_shift 0-5'
    cs = b.get('combos', [])
    assert len(cs) <= BC_MAX, f'enemy {n}: at most {BC_MAX} combos'
    v['combos'] = [combo_ops(c, f'enemy {n}: combo {c!r}') for c in cs]
    return v


def boss_tables(g):
    """the C of gguard (ai.guard) and gbossai_rom[EN_COUNT] (enemies[].boss_ai)"""
    gd = g['ai'].get('guard', {})
    for k in gd: assert k in GUARD_KEYS, f'ai.guard: unknown field {k}'
    st, pu, ch = gd.get('stun', 12), gd.get('push', 2), gd.get('chip', 64)
    assert 1 <= st <= 60 and 0 <= pu <= 8 and 0 <= ch <= 255, 'ai.guard: stun 1-60, push 0-8, chip 0-255'
    out = [f'const gguard_t gguard = {{ .stun = {st}, .push = {pu}, .chip = {ch} }};   /* game.json ai.guard (fighter.c "guard") */']
    refs = []
    for i, e in enumerate(g['enemies']):
        v = boss_ai(e, e['name'])
        if not v: refs.append('0'); continue
        cs = v.pop('combos')
        rows = ', '.join('{ ' + ', '.join(f'0x{o:02X}' for o in c) + ' }' for c in cs) or '{ 0 }'
        out.append(f'static const gbossai_t gboss_{i} = {{ ' + ', '.join(f'.{k} = {x}' for k, x in v.items()) +
                   f', .ncombo = {len(cs)}, .combo = {{ {rows} }} }};   /* {e["name"]}: ' + ' | '.join(e['boss_ai'].get('combos', [])) + ' */')
        refs.append(f'&gboss_{i}')
    out.append(f'const gbossai_t *const gbossai_rom[{len(refs)}] = {{ ' + ', '.join(refs) + ' };   /* per enemy (genemy_rom order) */')
    return out


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


END_COLS = 34                                            # main.c "the ending": the story box's and the staff roll's width
END_KEYS = {'about', 'music', 'staff_music', 'story', 'staff', 'thanks'}


def wrap(text, cols):
    """sentences -> lines of at most cols characters (words kept whole)"""
    out, cur = [], ''
    for w in text.split():
        assert len(w) <= cols, f'{w!r}: longer than {cols}'
        if cur and len(cur) + 1 + len(w) > cols: out.append(cur); cur = w
        else: cur = f'{cur} {w}' if cur else w
    return out + ([cur] if cur else [])


def ending_tables(g):
    """game.json "ending" (main.c "the ending"): its songs, timings, each roster fighter's story (wrapped to END_COLS,
    '*' for any other), the staff roll's line count (its lines are drawn as sprite tiles by staff_roll.py), the thanks
    screen's lines"""
    e = g['ending']
    for k in e: assert k in END_KEYS, f'ending: unknown field {k}'
    st, sf, th = e['story'], e['staff'], e['thanks']
    names = [r['name'] for r in g['roster']]
    fs = st['fighters']
    assert '*' in fs, 'ending.story.fighters: "*" (any other fighter) missing'
    for n in fs: assert n == '*' or n in names, f'ending.story.fighters: {n} is not a roster fighter'
    def ok(t, w): assert all(0x20 <= ord(ch) < 0x7F for ch in t), f'ending {w}: {t!r}: ASCII only'
    for k in ('min', 'type', 'hold'): assert 1 <= st[k] <= 32767, f'ending.story.{k}'
    for k in ('min', 'step', 'hold'): assert 1 <= sf[k] <= 32767, f'ending.staff.{k}'
    for k in ('min', 'time'): assert 1 <= th[k] <= 32767, f'ending.thanks.{k}'
    assert 0 <= th.get('fade', 0) <= 255, 'ending.thanks.fade'
    h = [f'#define GAME_MUS_ENDING MUS_{e["music"]}   /* game.json ending: the story screen\'s song */',
         f'#define GAME_MUS_STAFF MUS_{e["staff_music"]}    /* the staff roll\'s */',
         f'#define END_STORY_MIN {st["min"]}', f'#define END_STORY_TYPE {st["type"]}', f'#define END_STORY_HOLD {st["hold"]}',
         f'#define END_STAFF_MIN {sf["min"]}', f'#define END_STAFF_STEP {sf["step"]}', f'#define END_STAFF_HOLD {sf["hold"]}',
         f'#define END_THANKS_MIN {th["min"]}', f'#define END_THANKS_TIME {th["time"]}', f'#define END_THANKS_FADE {th.get("fade", 0)}',
         f'#define END_STAFF_N {len(sf["lines"])}', f'#define END_THANKS_N {len(th["lines"])}',
         f'#define END_COLS {END_COLS}',
         'extern const char *const *const gend_story[BC_COUNT];   /* per fighter its story\'s lines (wrapped), 0-terminated */',
         'extern const char *const gend_thanks[END_THANKS_N];']
    c, keys = [], {}
    for n, sents in fs.items():
        assert 4 <= len(sents) <= 5, f'ending.story.fighters.{n}: 4-5 sentences'
        lines = []
        for t in sents: ok(t, f'story {n}'); lines += wrap(t, END_COLS)
        keys[n] = f'gend_story_{"any" if n == "*" else n}'
        c.append(f'static const char *const {keys[n]}[] = {{ ' + ', '.join(c_str(t) for t in lines) + ', 0 };')
    c.append('const char *const *const gend_story[BC_COUNT] = { ' + ', '.join(keys.get(n, keys['*']) for n in names) + ' };')
    for t in sf['lines'] + th['lines']: ok(t, 'staff / thanks'); assert len(t.lstrip('^')) <= END_COLS, f'ending: {t!r}: at most {END_COLS} characters'
                                                    # (the staff roll's pictures: staff_roll.py, sprite tiles)
    c.append('const char *const gend_thanks[END_THANKS_N] = { ' + ', '.join(c_str(t) for t in th['lines']) + ' };')
    return h, c


BONUS_SCENES = ('tree', 'posts')                         # make_bonus.py SCENES, in its order (bonus.h BONUS_*)
BONUS_KINDS = {'gauge': 'BK_GAUGE', 'break': 'BK_BREAK'}
BONUS_KEYS = ('about', 'after', 'intro', 'pick', 'card', 'fury_lock', 'over_music', 'win_music', 'games')
BONUS_GAME_KEYS = {'gauge': ('id', 'name', 'kind', 'scene', 'slot', 'voice', 'music', 'seconds', 'step', 'grades', 'chunks', 'win_grade', 'fall_sounds', 'blows', 'charge', 'punch_sound', 'fail_sounds', 'fail_result'),
                   'break': ('id', 'name', 'kind', 'scene', 'slot', 'voice', 'music', 'seconds', 'count', 'breaks_with', 'unlock', 'hp', 'lesson', 'won_text', 'won_ticks')}
BONUS_BLOWS = {'jab': 'JAB', 'finisher': 'FIN', 'forward': 'FWD'}   # a gauge game's blows: fighter.h BL_* (fighter_blow)
GB_FALL_SND = 6                                         # gamedata.h GB_FALL_SND: a gauge game's fall_sounds
GB_FAIL_SND = 16                                        # gamedata.h GB_FAIL_SND: its fail_sounds ('VOICE HIT': GB_VOICE_HIT)
BONUS_SLOTS = (0, 2)                                     # AOF2's select slots whose title card is ripped (make_bonus.py CARDS)
BONUS_SLOT_NAMES = ('SPIRIT TRAINING', 'STRENGTH TRAINING', 'SUPER DEATH BLOW')   # AOF2's games in its slots 0-2


def bonus_check(g, songs_known, sfx_names=None):
    """game.json "bonus" checked -> the values the tables write (levels.py checks a draft with it too); raises
    AssertionError(reason). sfx_names (songs.json sfx names, upper case): the sounds checked too"""
    b = g.get('bonus') or {'after': [], 'games': [], 'pick': {'seconds': 9, 'music': g['music']['select']}, 'fury_lock': False}
    for k in b: assert k in BONUS_KEYS, f'bonus: unknown field {k}'
    n = len(g['stages'])
    assert isinstance(b['after'], list) and all(isinstance(s, int) and 1 <= s < n for s in b['after']), \
        f"bonus.after: stage numbers 1-{n - 1} (a bonus needs a stage after it): {b['after']}"
    assert len(set(b['after'])) == len(b['after']), 'bonus.after: a stage twice'
    p = b['pick']
    assert isinstance(p.get('seconds'), int) and 3 <= p['seconds'] <= 9, "bonus.pick.seconds: 3-9 (AOF2's clock: one digit)"
    for k, v in (('bonus.pick.music', p.get('music')), ('bonus.over_music', b.get('over_music', p.get('music'))),
                 ('bonus.win_music', b.get('win_music', b.get('over_music', p.get('music'))))):
        assert v in songs_known, f'{k}: {v!r} is no songs.json song'
    gs = b['games']
    assert 1 <= len(gs) <= 3 or not b['after'], 'bonus.games: 1-3 games'
    def snd(k, v):
        assert sfx_names is None or v is None or v.upper() in sfx_names, f'{k}: {v!r} is no songs.json sfx name (the V ROM has no sample for it)'
    i, c = b.get('intro', {}), b.get('card', {})
    for k in i: assert k in ('music', 'voice', 'at', 'ticks'), f'bonus.intro: unknown field {k}'
    for k in c: assert k in ('ticks', 'sound'), f'bonus.card: unknown field {k}'
    assert i.get('music', p.get('music')) in songs_known, f"bonus.intro.music: {i.get('music')!r} is no songs.json song"
    assert 0 <= i.get('at', 0) < i.get('ticks', 122) <= 255 and 30 <= c.get('ticks', 186) <= 255, 'bonus.intro: at < ticks <= 255; bonus.card.ticks 30-255'
    snd('bonus.intro.voice', i.get('voice')); snd('bonus.card.sound', c.get('sound'))
    sl = [x.get('slot') for x in gs]
    assert all(s in BONUS_SLOTS for s in sl) and len(set(sl)) == len(sl), \
        f"bonus.games: slot = AOF2's select slot, one game each, of {' | '.join(f'{s} ({BONUS_SLOT_NAMES[s]})' for s in BONUS_SLOTS)}: {sl}"
    for x in gs:
        kind = x.get('kind'); assert kind in BONUS_KINDS, f"bonus game {x.get('id')}: kind {kind!r} (gauge | break)"
        for k in x: assert k in BONUS_GAME_KEYS[kind], f"bonus game {x['id']}: unknown field {k} for kind {kind}"
        assert re.fullmatch(r'[A-Z0-9 .!-]{1,18}', x['name']), f"bonus game {x['id']}: name 1-18 characters A-Z 0-9 space . ! -"
        assert x['scene'] in BONUS_SCENES, f"bonus game {x['id']}: scene {x['scene']!r} ({' | '.join(BONUS_SCENES)})"
        assert x['music'] in songs_known, f"bonus game {x['id']}: music {x['music']!r} is no songs.json song"
        snd(f"bonus game {x['id']}: voice", x.get('voice'))
        assert isinstance(x['seconds'], int) and 5 <= x['seconds'] <= 99, f"bonus game {x['id']}: seconds 5-99"
        if kind == 'gauge':
            gr = x['grades']; ch = x['chunks']
            assert 1 <= x['step'] <= 16, f"bonus game {x['id']}: step 1-16"
            assert len(gr) == 5 and all(a < b for a, b in zip([0] + gr, gr)) and gr[-1] <= 127, f"bonus game {x['id']}: grades: 5 rising powers 1-127"
            assert len(ch) == 6 and all(isinstance(v, int) and 0 <= v <= 3 for v in ch), f"bonus game {x['id']}: chunks: 6 values 0-3 (grade 0-5)"
            assert x.get('win_grade', 5) in range(1, 6), f"bonus game {x['id']}: win_grade 1-5 (the lowest grade that passes)"
            bl = x.get('blows', ['jab'] * 6)
            assert len(bl) == 6 and all(v in BONUS_BLOWS for v in bl), f"bonus game {x['id']}: blows: 6 slots (grade 0-5) of {' | '.join(BONUS_BLOWS)}"
            fs = x.get('fall_sounds') or []
            assert len(fs) <= GB_FALL_SND and all(isinstance(t, int) and 0 <= t < 255 for t, _ in fs) and \
                [t for t, _ in fs] == sorted(t for t, _ in fs), f"bonus game {x['id']}: fall_sounds: up to {GB_FALL_SND} [tick 0-254, sfx name], ticks rising"
            for _, v in fs: snd(f"bonus game {x['id']}: fall_sounds", v)
            cg = x.get('charge') or {}                   # (note 20261014-133606-5d29: AOF2's concentration before the blow)
            assert set(cg) <= {'about', 'stand', 'fail', 'pass'} and all(isinstance(cg.get(k, 0), int) for k in ('stand', 'fail', 'pass')) and \
                0 <= cg.get('stand', 0) <= cg.get('fail', 0) <= 600 and cg.get('stand', 0) <= cg.get('pass', 0) <= 600, \
                f"bonus game {x['id']}: charge {{stand, fail, pass}}: ticks from the press, stand <= fail / pass <= 600"
            snd(f"bonus game {x['id']}: punch_sound", x.get('punch_sound'))
            fl = x.get('fail_sounds') or []
            assert len(fl) <= GB_FAIL_SND and all(isinstance(t, int) and 0 <= t < 255 for t, _ in fl) and \
                [t for t, _ in fl] == sorted(t for t, _ in fl), f"bonus game {x['id']}: fail_sounds: up to {GB_FAIL_SND} [tick 0-254, sfx name | 'VOICE HIT'], ticks rising"
            for _, v in fl:
                if v.upper() != 'VOICE HIT': snd(f"bonus game {x['id']}: fail_sounds", v)
            assert isinstance(x.get('fail_result', 58), int) and 20 <= x.get('fail_result', 58) <= 600, f"bonus game {x['id']}: fail_result 20-600"
        else:
            assert isinstance(x['count'], int) and 1 <= x['count'] <= 20, f"bonus game {x['id']}: count 1-20"
            assert x['breaks_with'] in ('fury', 'any') and x['unlock'] in ('fury', 'none'), f"bonus game {x['id']}: breaks_with fury | any, unlock fury | none"
            assert isinstance(x.get('hp', 1), int) and 1 <= x.get('hp', 1) <= 30, f"bonus game {x['id']}: hp 1-30 (hits a post takes)"
            assert isinstance(x.get('won_ticks', 300), int) and 120 <= x.get('won_ticks', 300) <= 1200, f"bonus game {x['id']}: won_ticks 120-1200"
            for k in ('lesson', 'won_text'):
                t = x.get(k, [])
                assert isinstance(t, list) and len(t) <= 3 and all(isinstance(l, str) and len(l) <= 38 and all(0x20 <= ord(ch) < 0x7F for ch in l) for l in t), \
                    f"bonus game {x['id']}: {k}: up to 3 lines, ASCII, 38 characters each"
    assert not b.get('fury_lock') or any(x.get('unlock') == 'fury' for x in gs) and b['after'], \
        'bonus.fury_lock: no game unlocks the fury (it would stay locked)'
    return b


def bonus_tables(g, songs_known, sfx_names):
    """game.json "bonus" -> gbonus (gamedata.h gbonus_t, main.c "bonus stages"); sfx_names: songs.json sfx name -> code"""
    b = bonus_check(g, songs_known, sfx_names)
    code = lambda v: sfx_names[v.upper()] if v else 0
    c = ['static const uint8_t gbonus_after[GS_COUNT] = { ' + ', '.join('1' if s + 1 in b['after'] else '0' for s in range(len(g['stages']))) + ' };   /* bonus.after */']
    rows = []
    for x in b['games']:
        f = [f".name = {c_str(x['name'])}", f".kind = {BONUS_KINDS[x['kind']]}", f".scene = {BONUS_SCENES.index(x['scene'])}",
             f".music = MUS_{x['music']}", f".seconds = {x['seconds']}", f".slot = {x['slot']}", f".voice = 0x{code(x.get('voice')):02X}"]
        if x['kind'] == 'gauge':
            f += [f".step = {x['step']}", '.grades = { ' + ', '.join(map(str, x['grades'])) + ' }', '.chunks = { ' + ', '.join(map(str, x['chunks'])) + ' }',
                  f".win_grade = {x.get('win_grade', 5)}",
                  '.blows = { ' + ', '.join('BL_' + BONUS_BLOWS[v] for v in x.get('blows', ['jab'] * 6)) + ' }']   # (fighter.h BL_*)
            fs = x.get('fall_sounds') or []              # (the tree's sounds as it falls: AOF2's, ticks from the blow)
            f += [f".nfall = {len(fs)}", '.fall_t = { ' + ', '.join(str(t) for t, _ in fs) + ' }' if fs else '.fall_t = { 0 }',
                  '.fall_sfx = { ' + ', '.join(f'0x{code(v):02X}' for _, v in fs) + ' }' if fs else '.fall_sfx = { 0 }']
            cg = x.get('charge') or {}; fl = x.get('fail_sounds') or []
            fcode = lambda v: 'GB_VOICE_HIT' if v.upper() == 'VOICE HIT' else f'0x{code(v):02X}'
            f += [f".chg_stand = {cg.get('stand', 0)}", f".chg_blow = {{ {cg.get('fail', 0)}, {cg.get('pass', 0)} }}",
                  f".punch_sfx = 0x{code(x.get('punch_sound')):02X}", f".nfail = {len(fl)}",
                  '.fail_t = { ' + (', '.join(str(t) for t, _ in fl) or '0') + ' }', '.fail_sfx = { ' + (', '.join(fcode(v) for _, v in fl) or '0') + ' }',
                  f".fail_result = {x.get('fail_result', 58)}"]
        else:
            ln = lambda k, d: '{ ' + ', '.join(c_str(l) for l in (x.get(k, d) + ['', '', ''])[:3]) + ' }'
            f += [f".count = {x['count']}", f".breaks = {'BB_FURY' if x['breaks_with'] == 'fury' else 'BB_ANY'}", f".unlock = {'BU_FURY' if x['unlock'] == 'fury' else 'BU_NONE'}",
                  f".hp = {x.get('hp', 1)}", f".won_ticks = {x.get('won_ticks', 300)}",
                  '.lesson = ' + ln('lesson', ['ONLY YOUR FURY BREAKS THE POSTS!', 'FURY  =  D', 'MAX  =  DOWN + D  AT LOW LIFE']),
                  '.won_text = ' + ln('won_text', ['FURY + FURY MAX UNLOCKED ON D'])]
        rows.append('{ ' + ', '.join(f) + ' }')
    c.append(f"const gbonus_t gbonus = {{ .ngames = {len(b['games']) if b['after'] else 0}, .pick_seconds = {b['pick']['seconds']}, "
             f".pick_music = MUS_{b['pick']['music']}, .over_music = MUS_{b.get('over_music', b['pick']['music'])}, "
             f".win_music = MUS_{b.get('win_music', b.get('over_music', b['pick']['music']))}, "
             f".fury_lock = {1 if b.get('fury_lock') and b['after'] else 0}, .after = gbonus_after, "
             f".intro_music = MUS_{b.get('intro', {}).get('music', b['pick']['music'])}, .intro_voice = 0x{code(b.get('intro', {}).get('voice')):02X}, "
             f".intro_at = {b.get('intro', {}).get('at', 0)}, .intro_ticks = {b.get('intro', {}).get('ticks', 122)}, "
             f".card_ticks = {b.get('card', {}).get('ticks', 186)}, .card_sound = 0x{code(b.get('card', {}).get('sound')):02X}, "
             f".games = {{ {', '.join(rows)} }} }};")
    return c


def tint_lut(tints):
    """the minion tints precomputed (CPU budget B, docs/brawler_cpu_budget.md: the boss wave's spawn tinted its minions'
    palettes with 6 multiplies a colour, a 4-frame freeze): per tint, for every luminance l and channel c (0-31), what
    fighter.c computed: (int16)((l * mix + c) * mul) >> shift; the game adds the channel's cast and clamps to 0-31. Kept
    within -64..96 (the same result after a cast of at most +-32 and the clamp: int8)"""
    rows = []
    for n, t in tints.items():
        assert all(-32 <= a <= 32 for a in t['add']), f'tint {n}: a cast past +-32'
        v = []
        for l in range(32):
            for ch in range(32):
                m = ((l * t['mix'] + ch) * t['mul']) & 0xFFFF
                m = m - 0x10000 if m & 0x8000 else m
                v.append(max(-64, min(96, m >> t['shift'])))
        rows.append(f'    {{   /* {n} */\n' + '\n'.join('        ' + ', '.join(str(x) for x in v[i:i + 32]) + ',' for i in range(0, 1024, 32)) + '\n    },')
    return 'const int8_t gtint_lut[TINT_COUNT - 1][1024] = {\n' + '\n'.join(rows) + '\n};'


INTRO_KEYS = ('fade', 'title', 'title_at', 'title_hold', 'walk_at', 'side', 'from', 'marks', 'gait', 'wave_delay')
INTRO_DEFAULT = {'fade': 32, 'title': '{name} START', 'title_at': 16, 'title_hold': 120, 'walk_at': 136, 'side': 'left', 'from': 48,
                 'marks': [[60, 40], [40, 10]], 'gait': 'walk', 'wave_delay': 20}


def intro_of(g, si):
    """stage si's intro (note 20261014-192343-5d29; main.c "the stage intro"): game.json stage_intro (game-wide) with the
    stage's own stages[].intro over it, checked -> the dict with every key, the title formatted ({name} = the stage's)"""
    base = {k: v for k, v in (g.get('stage_intro') or {}).items() if k != 'about'}
    own = g['stages'][si].get('intro') or {}
    for w, d in (('stage_intro', base), (f'stages[{si}].intro', own)):
        for k in d: assert k in INTRO_KEYS, f'{w}: unknown field {k}'
    v = {**INTRO_DEFAULT, **base, **own}; n = f'stage {si + 1} intro'
    num = lambda k, lo, hi: isinstance(v[k], int) and not isinstance(v[k], bool) and lo <= v[k] <= hi
    for k, lo, hi in (('fade', 0, 255), ('title_at', 0, 1000), ('title_hold', 0, 1000), ('walk_at', 0, 1000), ('from', 0, 120), ('wave_delay', 0, 1000)):
        assert num(k, lo, hi), f'{n}: {k} {v[k]!r}: {lo}-{hi}'
    assert v['side'] in ('left', 'right'), f'{n}: side left | right'
    assert v['gait'] in ('walk', 'run'), f'{n}: gait walk | run'
    m = v['marks']
    assert isinstance(m, list) and len(m) == 2 and all(isinstance(x, list) and len(x) == 2 and 16 <= x[0] <= 300 and 0 <= x[1] <= 80 for x in m), \
        f'{n}: marks [[x, z] P1, [x, z] P2], x 16-300 px from that side, z 0-80'
    t = v['title'].replace('{name}', g['stages'][si]['name']) if isinstance(v['title'], str) else None
    assert t is not None and len(t) <= 38 and all(0x20 <= ord(ch) < 0x7F for ch in t), f'{n}: title {v["title"]!r}: ASCII, 0-38 characters'
    return {**v, 'title': t}


def intro_tables(g):
    h = ['typedef struct {                  /* a stage\'s intro (game.json stage_intro / stages[].intro; main.c "the stage intro") */',
         '    const char *title;            /* the fix layer\'s line ("" = none) */',
         '    uint16_t title_at, title_hold, walk_at, wave_delay;   /* ticks from the stage\'s start; shown; the walk in; after the walk: the first wave */',
         '    uint8_t fade, side, run, from;   /* palette fade-in ticks (0 = a cut); 1 = in from the right; the run, not the walk; px outside the edge */',
         '    uint8_t mark_x[2], mark_z[2]; /* P1, P2: where the walk stops (px from that side\'s edge, depth) */',
         '} gintro_t;', 'extern const gintro_t gintro[GS_COUNT];']
    rows = []
    for si in range(len(g['stages'])):
        v = intro_of(g, si); m = v['marks']
        rows.append(f"    {{ {c_str(v['title'])}, {v['title_at']}, {v['title_hold']}, {v['walk_at']}, {v['wave_delay']}, {v['fade']}, "
                    f"{1 if v['side'] == 'right' else 0}, {1 if v['gait'] == 'run' else 0}, {v['from']}, {{ {m[0][0]}, {m[1][0]} }}, {{ {m[0][1]}, {m[1][1]} }} }}")
    return h, ['const gintro_t gintro[GS_COUNT] = {', ',\n'.join(rows), '};']


BIG_USES = {                                   # game.json big_text: the screens whose headline the big font can draw (main.c
    'stage_intro': None,                       # "big text"); text None = the screen's own (stage_intro.title, the bonus's
    'stage_clear': 'STAGE CLEAR',              # won_text[0]), else the default here, a use's "text" over it
    'game_over': 'GAME OVER',
    'time_over': 'TIME OVER',
    'bonus_won': None,
    'ladder': 'NEW CHALLENGERS!',              # the unlock ladder screen after a game clear that unlocked a rung
}
BIG_KEYS = ('y', 'slide', 'blink', 'pitch', 'text')


def big_tables(g):
    """game.json big_text (Bruno 2026-10-14, Savage Reign's letters: tools/brawler/make_bigfont.py) -> gbig[BIG_USES]: per
    screen whether its headline is drawn in the big font (a use listed) and how (y, slide-in, blink, line pitch); a use
    not listed keeps the fix layer's line. Every text a use can draw is checked against the font's characters."""
    from make_bigfont import CHARS, SPACE, font
    adv = {c: a.shape[1] for c, (a, _) in font().items()}; adv[' '] = SPACE
    B = {k: v for k, v in (g.get('big_text') or {}).items() if k != 'about'}
    for k, v in B.items():
        assert k in BIG_USES, f'big_text: unknown use {k} ({", ".join(BIG_USES)})'
        for f in v: assert f in BIG_KEYS, f'big_text.{k}: unknown field {f} ({", ".join(BIG_KEYS)})'
        assert 'text' not in v or BIG_USES[k], f'big_text.{k}: its text is the screen\'s own (no "text")'
    texts = {'stage_intro': [intro_of(g, si)['title'] for si in range(len(g['stages']))],
             'bonus_won': [b['won_text'][0] for b in (g.get('bonus') or {}).get('games', []) if b.get('won_text')]}
    rows = []
    for k, dflt in BIG_USES.items():
        v = B.get(k)
        if v is None: rows.append(f'    {{ 0, 0, 0, 0, 0, 0 }},   /* {k}: the fix layer */'); continue
        y, sl, bl, pi = v.get('y', 80), v.get('slide', 0), v.get('blink', 0), v.get('pitch', 44)
        for f, x, lo, hi in (('y', y, 0, 176), ('slide', sl, 0, 120), ('blink', bl, 0, 120), ('pitch', pi, 32, 64)):
            assert isinstance(x, int) and lo <= x <= hi, f'big_text.{k}.{f} {x!r}: {lo}-{hi}'
        t = v.get('text', dflt)
        for s in ([t] if dflt else texts[k]):
            bad = sorted({c for c in s.upper() if c not in CHARS})
            assert s and not bad, f'big_text.{k}: {s!r}: the big font has no {"".join(bad)!r} (it draws {CHARS!r})'
            words = [w for w in re.split(r' {2,}', s.upper().strip())]
            for w in (words if sum(adv[c] for c in s.upper().strip()) > 304 else [s.upper().strip()]):
                assert sum(adv[c] for c in w) <= 304, f'big_text.{k}: {w!r} is wider than 304 px (two lines at most: they break at a double space)'
            assert len(words) <= 2, f'big_text.{k}: {s!r}: two lines at most'
        rows.append(f'    {{ {c_str(t) if dflt else 0}, {y}, {sl}, {bl}, {pi}, 1 }},   /* {k} */')
    h = ['typedef struct {                  /* a screen\'s headline in the big font (game.json big_text; main.c "big text") */',
         '    const char *text;             /* 0 = the screen\'s own text */',
         '    int16_t y;                    /* the glyphs\' top on screen (48 px cells) */',
         '    uint8_t slide, blink, pitch;  /* ticks sliding in from the right (0 = in place); blink half-period (0 = steady); px between two lines */',
         '    uint8_t on;                   /* 0: this screen keeps the fix layer\'s line */',
         '} gbig_t;',
         'enum { ' + ', '.join(f'BIG_{k.upper()}' for k in BIG_USES) + ', BIG_USES };',
         'extern const gbig_t gbig[BIG_USES];']
    return h, ['const gbig_t gbig[BIG_USES] = {', '\n'.join(rows), '};']


def tables(g, build):
    M = model(g, build)
    presets = M['presets']
    h = ['/* Generated by tools/brawler/build_tables.py from examples/brawler/game.json. Do not edit. */',
         '#ifndef GAME_TABLES_H\n#define GAME_TABLES_H\n#include "bm_chars.h"\n#include "gamedata.h"\n#include "snd/songs.h"',
         f'#define GS_COUNT {len(g["stages"])}            /* campaign stages */',
         f'#define EN_COUNT {len(M["enemies"])}', f'#define AI_COUNT {len(M["ai"])}            /* the presets, then the enemies\' own rows */',
         f'#define TINT_COUNT {len(M["tints"])}',
         f'#define SEL_NSLOT {len(select_layout(g))}',
         f'#define SEL_NLAY {len(select_layers(g))}             /* the select screen\'s layouts: one per unlocked count (select_layers; the ladder: rungs + 1) */',
         f'#define SEL_NPAL {sel_palbases(g, build)[1]}             /* the select screen\'s actors\' palettes from 16 (sel_palbase) */',
         f'#define GAME_MUS_TITLE MUS_{g["music"].get("title", g["music"]["select"])}',
         f'#define GAME_MUS_SELECT MUS_{g["music"]["select"]}', f'#define GAME_MUS_CLEAR MUS_{g["music"]["clear"]}',
         f'#define GAME_MUS_CONTINUE MUS_{g["music"].get("continue", g["music"]["clear"])}',
         (f'#define GAME_MUS_OVER 0   /* GAME OVER: no song, the continue song fades out ($0A + speed, KOF98) */\n#define GAME_OVER_FADE 0x2C'
          if g['music'].get('gameover') == 'FADE' else f'#define GAME_MUS_OVER MUS_{g["music"].get("gameover", g["music"]["clear"])}\n#define GAME_OVER_FADE 0'),
         'enum { ' + ', '.join(f'AI_{n.upper()}' for n in presets) + ' };',
         'enum { ' + ', '.join(f'EN_{e["name"].upper()}' for e in M['enemies']) + ' };',
         'extern const char *const gstage_names[GS_COUNT];   /* game.json stages[].name: the HUD, GAME OVER */',
         'extern const gstage_t gstages_rom[GS_COUNT];', 'extern const genemy_t genemies_rom[EN_COUNT];',
         'extern const ai_preset_t ai_presets_rom[AI_COUNT];', 'extern const gbossai_t *const gbossai_rom[EN_COUNT];   /* (T9) a boss\'s own AI layer per enemy, 0 = none (gamedata.h) */', 'extern const gtint_t gtints[TINT_COUNT];',
         'extern const int8_t gtint_lut[TINT_COUNT - 1][1024];   /* fighter.c tint_colour: tint t\'s (l * mix + c) * mul >> shift at [t - 1][l * 32 + c] */',
         'extern const sel_slot_t SEL_SLOT[SEL_NSLOT];', 'extern const uint8_t sel_fighter[SEL_NSLOT];', 'extern const uint8_t sel_palbase[SEL_NSLOT];', 'extern const uint8_t sel_lay_n[SEL_NLAY], sel_lay_base[SEL_NLAY];', 'extern const uint8_t sel_stick[SEL_NLAY][SEL_NSLOT][2];', 'extern const uint8_t sel_vert[SEL_NLAY][SEL_NSLOT][2][SEL_NSLOT - 1];',
         'extern const uint8_t roster_unlock[BC_COUNT];',
         'extern const uint8_t roster_music[BC_COUNT];   /* the fighter\'s theme (game.json roster[].music), 0 = none: main.c stage_song */',
         'extern const uint16_t *const dtier_rom[BC_COUNT];   /* the damage tiers (fighter.c "damage tiers"): per fighter, 8.8 scales: [special index], [nspec] the fury, [nspec + 1] the MAX */',
         'extern uint8_t dtier_off;                         /* (fighter.c) 1: every scale 1 (a test switch) */',
         'extern const uint8_t ai_ready[BC_COUNT][2];',
         'extern const uint8_t gblitz_rom[BC_COUNT][4];   /* per fighter its Blitz slots (BZ_FF .. BZ_UU): a special\'s pool index, BZ_DASH its dash entry, BZ_NORMAL its blitz entry, BZ_NONE */',
         'extern const uint8_t gfury_wait[BC_COUNT];   /* 1: the fury (D) holds its first frame through the super flash\'s freeze, its move after (roster[].fury_flash, default wait for a sequence fury: fighter.c flash_pose) */',
         'extern const uint8_t gfury_area[BC_COUNT][3];  /* the fury\'s final hit as an area hit (roster[].fury_final_area; fighter.c fury_area): [front, back, depth] px, 0 = none */',
         'extern const int32_t gwalk_rom[BC_COUNT];       /* its walk (16.16 px a frame, by archetype) */',
         'extern const int32_t gblitz_slide[BC_COUNT][4][3];   /* per fighter per Blitz slot: its slide [frames, first frame\'s glide, its loss a frame] (16.16 px; roster[].blitz_slide; fighter.c blitz_slide), frames 0 = none */',
         'extern const uint8_t gblitz_can[BC_COUNT][4];   /* per fighter per Blitz slot: the slots it may cancel into on hit (bit BZ_*; roster[].blitz_cancel) */',
         'extern const uint8_t *const grun_bob[BC_COUNT]; /* the run\'s float: [period, px a frame...] (roster[].run.float), 0 = none */',
         'extern const uint8_t *const grun_dash[BC_COUNT]; /* the dash: [start, frames, x..., height..., air_buttons] (roster[].run.mode dash), 0 = a run */',
         'extern const uint16_t gwalk_run;               /* run = walk x this (8.8) */',
         'extern const uint16_t gwalk_anim;              /* the walk / run animations\' rate x this (8.8) */',
         'extern const int32_t grun_spd[BC_COUNT];       /* the run at its source\'s speed (16.16; roster[].run.speed), 0 = walk x gwalk_run */',
         'extern const uint16_t grun_anim[BC_COUNT];     /* the run animation\'s rate = the walk\'s x this (8.8; game.json walk.run_anim / walk.anim, 256 for a roster[].walk_rate fighter) */',
         'extern const uint8_t gfury_throw[BC_COUNT];   /* the fury closes with the hold B throw on its reeling victim, this damage (game.json roster[].fury_throw; 0 = none; fighter.c fury_throw) */',
         'extern const uint8_t ghold_timeout[BC_COUNT];   /* the holder hold timeout (game.json roster[].hold_timeout): 0 stand (the victim let go on its feet), 1 knockdown (it falls on its back, no damage); fighter.c hold_update */',
         'extern const uint16_t ghold_walk[BC_COUNT];    /* the walk in the hold (game.json roster[].hold_walk.speed: x its walk, 8.8; 0 = none: it stands; fighter.c hold_walk) */',
         'extern const uint8_t *const gback_rom[];       /* the floor\'s back edge per background (game.json depth; fighter.h zback) */',
         f'#define DR_COUNT {len(M["dramas"])}            /* drama scenes (game.json dramas) */',
         f'#define DR_WIN {M["win_drama"]}              /* the stage clear\'s drama (game.json win_drama), 0xFF none */',
         'extern const gstagex_t gstagex_rom[GS_COUNT];', 'extern const uint8_t pb_of_fighter[BC_COUNT];', 'extern const gdrama_t gdramas[DR_COUNT ? DR_COUNT : 1];']
    c = ['/* Generated by tools/brawler/build_tables.py from examples/brawler/game.json. Do not edit. */',
         '#include <stddef.h>\n#include "bm_chars.h"\n#include "game_tables.h"\n#include "fighter.h"\n'] + layout_asserts()
    c.append('const ai_preset_t ai_presets_rom[AI_COUNT] = {\n' + '\n'.join(
        '    { ' + ', '.join(f'.{k} = {x}' for k, x in v.items()) + ' },   /* ' + n + ' */' for n, v in M['ai']) + '\n};')
    c += ai_rules(g)                                     # the enemies' shared rules (revamp 1B, gamedata.h gairules_t)
    c += boss_tables(g)                                  # the guard's rules + the bosses' own layer (T9)
    m = g['meter']                                       # the drive meter + the hidden fury gauge (Bruno's redesign
    for k in m: assert k in METER_KEYS, f'meter: unknown field {k}'   # 2026-10-08, gamedata.h gmeter_t)
    assert 1 <= m['chunks'] <= 4 and 1 <= m['chunk'] and m['chunk'] * m['chunks'] < 65536, 'meter: chunks x chunk'
    assert 1 <= m['special'] <= m['chunks'] and 1 <= m['breaker'] <= m['chunks'], 'meter: costs within the bar'
    assert all(k in REFILL_PAUSE for k in m.get('refill_pause', [])), f"meter.refill_pause: {m.get('refill_pause')} (special / chain / blitz)"
    assert 1 <= m['life_breaker'] < 60 and 1 <= m['low'] <= 100 and 1 <= m['blink'] <= 60, 'meter values'
    sf = m.get('special_flash', {})                    # a paid C special's blue flash (Bruno 2026-10-10)
    assert 0 <= sf.get('frames', 0) <= 120 and len(sf.get('tint', [0, 0, 31])) == 3 and all(0 <= x <= 31 for x in sf.get('tint', [0, 0, 31])), 'meter.special_flash'
    assert 1 <= m['fury_max'] < 65536 and 0 <= m['fury_dealt'] <= 255 and 0 <= m['fury_taken'] <= 255, 'meter: the fury gauge'
    c.append(f"const gmeter_t gmeter = {{ .chunk = {m['chunk']}, .chunks = {m['chunks']}, .special = {m['special']}, "
             f".breaker = {m['breaker']}, .life_breaker = {m['life_breaker']}, .blink = {m['blink']}, .infinite = {1 if m.get('infinite') else 0}, "
             f".fury_max = {m['fury_max']}, .fury_dealt = {m['fury_dealt']}, .fury_taken = {m['fury_taken']}, .low = {m['low']}, .fury_drive = {m.get('fury_drive', 0)}, .max_drive = {m.get('max_drive', 0)}, "
             f".sflash = {sf.get('frames', 0)}, .stint = {{ {', '.join(str(x) for x in sf.get('tint', [0, 0, 31]))} }}, "
             f".pause = {sum(REFILL_PAUSE[k] for k in m.get('refill_pause', []))} }};")
    bz = g['blitz']                                      # the Blitz (gamedata.h gblitz_t) and its slots per fighter
    for k in bz: assert k in BLITZ_KEYS, f'blitz: unknown field {k}'
    assert 2 <= bz['window'] <= 60 and 0 <= bz['chord'] <= 8 and 1 <= bz['damage'] < 128, 'blitz values'
    c.append(f"const gblitz_t gblitz = {{ .window = {bz['window']}, .chord = {bz['chord']}, "
             f".scale = {round(bz['damage'] * 256 / g['tiers']['special'])} }};   /* scale: {bz['damage']} / tiers.special {g['tiers']['special']} (8.8) */")
    c.append('const uint8_t gblitz_rom[BC_COUNT][4] = {\n' + ',\n'.join(
        '    { ' + ', '.join(f'0x{v:02X}' for v in row) + ' }   /* ' + n + ' */' for n, row in blitz_rows(g, build)) + '\n};')
    fw = []                                              # the fury's wait for the super flash (Bruno results-1014, Haggar:
    for r in g['roster']:                                # "make him wait a bit during the freeze animation"): a fury that is
        ff = r.get('fury_flash', 'wait' if isinstance(r.get('fury'), list) else 'move')   # a sequence of pieces waits
        assert ff in ('wait', 'move'), f"roster {r['name']}: fury_flash wait | move"      # (its first piece's first frame
        fw.append(('1' if ff == 'wait' else '0') + f'   /* {r["name"]} */')               # held through the freeze)
    c.append('const uint8_t gfury_wait[BC_COUNT] = {\n    ' + ',\n    '.join(fw) + '\n};')
    c.append('const uint8_t gblitz_can[BC_COUNT][4] = {\n' + ',\n'.join(
        '    { ' + ', '.join(f'0x{v:02X}' for v in row) + ' }   /* ' + n + ' */' for n, row in blitz_cancels(g)) + '\n};')
    c.append('const int32_t gblitz_slide[BC_COUNT][4][3] = {\n' + ',\n'.join(
        '    { ' + ', '.join('{ %d, %d, %d }' % tuple(v) for v in row) + ' }   /* ' + n + ' */' for n, row in blitz_slides(g)) + '\n};')
    import knobs                                         # piece knobs (fighter.c "knobs"): shipped rows + the catalogue
    c += knobs.c_tables(g, build, SLOT_SEC)
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
    fa = []                                              # roster[].fury_final_area (note 20261009-235250-b3f3; was
    for r in g['roster']:                                # fury_end_burn, Kim's, note 20261009-231252-b3f3, dropped)
        e = r.get('fury_final_area') or {}
        for k in e: assert k in ('about', 'front', 'back', 'depth', 'blows'), f"roster {r['name']}: fury_final_area: unknown field {k}"
        assert not e or (all(1 <= e[k] <= 255 for k in ('front', 'back')) and 1 <= e['depth'] <= 127), \
            f"roster {r['name']}: fury_final_area: front / back 1-255 px, depth 1-127 px"
        assert e.get('blows', 'last') in ('last', 'all'), f"roster {r['name']}: fury_final_area: blows 'last' or 'all'"
        fa.append(f"{{ {e.get('front', 0)}, {e.get('back', 0)}, {e.get('depth', 0) | (0x80 if e.get('blows') == 'all' else 0)} }}")
    for r in g['roster']:                                # roster[].special_final_area {input: the same fields} (note
        for inp, e in (r.get('special_final_area') or {}).items():   # 20261011-230030-5d29; export_bm special_area)
            for k in e: assert k in ('about', 'front', 'back', 'depth', 'blows'), f"roster {r['name']}: special_final_area.{inp}: unknown field {k}"
            assert all(isinstance(e.get(k), int) and 1 <= e[k] <= 255 for k in ('front', 'back')) and isinstance(e.get('depth'), int) and 1 <= e['depth'] <= 127, \
                f"roster {r['name']}: special_final_area.{inp}: front / back 1-255 px, depth 1-127 px"
            assert e.get('blows', 'last') in ('last', 'all'), f"roster {r['name']}: special_final_area.{inp}: blows 'last' or 'all'"
    c.append('const uint8_t gfury_area[BC_COUNT][3] = { ' + ', '.join(fa) + ' };   /* [front, back, depth | 0x80 = every blow] px per fighter */')
    c.append('const int32_t gwalk_rom[BC_COUNT] = { ' + ', '.join(str(round(wk[r['archetype']] * 65536)) for r in g['roster']) +
             f' }};   /* 16.16 px a frame, by roster[].archetype */')
    c.append(f"const uint16_t gwalk_run = {round(wk['run'] * 256)};   /* run = walk x this (8.8) */")
    c.append(f"const uint16_t gwalk_anim = {round(wk.get('anim', 1) * 256)};   /* walk / run animation rate x this (8.8) */")
    c.append('const uint16_t grun_anim[BC_COUNT] = { ' + ', '.join(str(run_anim(wk, r)) for r in g['roster']) +
             ' };   /* the run animation\'s rate = the walk\'s x this (8.8), run_anim */')
    c.append('const int32_t grun_spd[BC_COUNT] = { ' + ', '.join(str(run_speed(r)) for r in g['roster']) +
             ' };   /* the run at its source\'s own speed (16.16 px a frame; roster[].run.speed), 0 = walk x gwalk_run */')
    hw = []
    for r in g['roster']:                                # the walk in the hold (note 20261014-171133-5d29)
        hwr = r.get('hold_walk')
        if hwr is None: hw.append('0'); continue
        for k in hwr: assert k in ('about', 'speed'), f"roster {r['name']}: hold_walk: unknown field {k}"
        assert isinstance(hwr['speed'], (int, float)) and 0 < hwr['speed'] <= 2, f"roster {r['name']}: hold_walk.speed {hwr['speed']} (0-2, x its walk)"
        hw.append(str(round(hwr['speed'] * 256)))
    c.append('const uint16_t ghold_walk[BC_COUNT] = { ' + ', '.join(hw) + ' };   /* x its walk (8.8), 0 = no walk in the hold */')
    hb = []                                              # the hold's timeout (note 20261014-193405-5d29, Bruno: "if the
    for r in g['roster']:                                # grab times out for Haggar, the character falls on his back"):
        v = r.get('hold_timeout', 'stand')               # stand = both let go, the victim on its feet on the floor;
        assert v in ('stand', 'knockdown'), f"roster {r['name']}: hold_timeout stand | knockdown"   # knockdown = it falls
        hb.append(('1' if v == 'knockdown' else '0') + f'   /* {r["name"]} */')   # on its back (no damage)
    c.append('const uint8_t ghold_timeout[BC_COUNT] = {\n    ' + ',\n    '.join(hb) + '\n};')
    ft = []                                              # the fury's closing throw (note 20261014-171937-5d29, Haggar:
    for r in g['roster']:                                # "at the very end of everything, add the piledriver"): after the
        e = r.get('fury_throw')                          # fury's last piece its reeling victim is grabbed and thrown by
        if not e: ft.append(f'0   /* {r["name"]} */'); continue   # the hold's B throw (roster[].throws.b, bm_xthr x)
        for k in e: assert k in ('about', 'throw', 'damage'), f"roster {r['name']}: fury_throw: unknown field {k}"
        assert e.get('throw') == 'b' and (r.get('throws') or {}).get('b'), f"roster {r['name']}: fury_throw.throw 'b' needs roster[].throws.b"
        assert isinstance(e.get('damage'), int) and 1 <= e['damage'] <= 60, f"roster {r['name']}: fury_throw.damage 1-60"
        ft.append(f'{e["damage"]}   /* {r["name"]} */')
    c.append('const uint8_t gfury_throw[BC_COUNT] = {\n    ' + ',\n    '.join(ft) + '\n};')
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
    ho = g.get('throw_handoff', 'release')               # throws part 1 (docs/throws_audit.md "After", gamedata.h
    assert ho in ('release', 'landing'), f"throw_handoff: 'release' or 'landing', not {ho!r}"   # gthrow_t)
    sw = g.get('throw_swap', {})
    for k in sw: assert k in ('about', 'frames', 'arc', 'glide_px'), f'throw_swap: unknown field {k}'
    assert 0 <= sw.get('frames', 0) <= 30 and 0 <= sw.get('arc', 0) <= 64, 'throw_swap: frames 0-30, arc 0-64 px'
    assert 0 <= sw.get('glide_px', 0) <= 64, 'throw_swap: glide_px 0-64'
    c.append(f"const gthrow_t gthrow = {{ .handoff = {'TH_LANDING' if ho == 'landing' else 'TH_RELEASE'}, "
             f".swap_n = {sw.get('frames', 0)}, .swap_arc = {sw.get('arc', 0)}, .glide_px = {sw.get('glide_px', 0)} }};")
    c += tbody_tables(g, build)                          # the thrown body (note 20261014-132326-5d29, gamedata.h gtbody_t)
    fl = g['super_flash']                                # the super flash (TODO #139): one rule for every fury
    for k in fl: assert k in ('about', 'start', 'freeze', 'white', 'anchor', 'white_colour', 'dark_colour', 'sound', 'sound_max'), f'super_flash: unknown field {k}'
    assert 1 <= fl['start'] <= 255 and 1 <= fl['white'] <= fl['freeze'] <= 255 and len(fl['anchor']) == 2, 'super_flash values'
    sfx = json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['sfx']['codes']   # (build = the game's build/)
    for k in ('sound', 'sound_max'):                     # sound_max: the MAX fury's (TODO #155), else sound
        assert fl.get(k, fl['sound']).upper() in [x.upper() for x in sfx], f"super_flash {k} {fl.get(k)}: not in songs.json sfx codes (the V ROM has no sample for it)"
    c.append(f"const gflash_t gflash = {{ .start = {fl['start']}, .freeze = {fl['freeze']}, .white = {fl['white']}, .sound = 0x{fl['sound']}, .sound_max = 0x{fl.get('sound_max', fl['sound'])}, .dx = {fl['anchor'][0]}, "
             f".dy = {fl['anchor'][1]}, .white_col = {fl['white_colour']}, .dark_col = {fl['dark_colour']} }};")
    hs = g['hit_sounds']                                 # the hit cycles, the guard and the boss KO sounds (gamedata.h
    for k in hs: assert k in ('about', 'light', 'strong', 'guard', 'boss_ko', 'bounce', 'scream_delay', 'hurt_voice', 'rest_music'), f'hit_sounds: unknown field {k}'   # ghitsnd_t)
    names = {v.upper(): int(k, 16) for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['sfx']['names'].items()}
    def code(v):
        assert v.upper() in names, f'hit_sounds: {v!r} is no songs.json sfx name (the V ROM has no sample for it)'
        return names[v.upper()]
    assert 1 <= len(hs['light']) <= 32 and 1 <= len(hs['strong']) <= 32 and 0 <= hs['scream_delay'] < 300, 'hit_sounds values (scream_delay inside main.c KO_SLOW)'
    assert 0 <= hs['rest_music'] <= 224, 'hit_sounds.rest_music: 0..224 frames (main.c ko_wt, + the queued bytes)'
    rep = os.path.join(build, 'snd', 'snd_report.json')   # the landing sample's length (build_snd: ADPCM-A bytes, 2 samples
    if os.path.exists(rep):                               # each at 18.5 kHz): the music never over its tail (note 20261014-172113-5d29)
        sb = json.load(open(rep)).get('sfx_from', {}).get(f"{code(hs['bounce']):02X}", {}).get('bytes')
        if sb:
            fr = -(-sb * 2 * 60 // 18518)
            assert hs['rest_music'] >= fr, f"hit_sounds.rest_music {hs['rest_music']}: the bounce sample {hs['bounce']} lasts {fr} frames"
    hv = hs.get('hurt_voice', ['hit'])                   # when the hurt voice plays (gamedata.h HV_*): every hit, the launch, the landing
    assert set(hv) <= {'hit', 'launch', 'land'}, f'hit_sounds.hurt_voice {hv}: hit / launch / land'
    hurt = sum(b for k, b in (('hit', 1), ('launch', 2), ('land', 4)) if k in hv)
    for k in ('light', 'strong'):
        c.append(f"static const uint8_t hcycle_{k}[] = {{ {', '.join(f'0x{code(v):02X}' for v in hs[k])} }};   /* {', '.join(hs[k])} */")
    c.append(f"const ghitsnd_t ghitsnd = {{ .n = {{ {len(hs['light'])}, {len(hs['strong'])} }}, .guard = 0x{code(hs['guard']):02X}, "
             f".boss_ko = 0x{code(hs['boss_ko']):02X}, .bounce = 0x{code(hs['bounce']):02X}, .scream_delay = {hs['scream_delay']}, .hurt = {hurt}, .rest_music = {hs['rest_music']}, .cycle = {{ hcycle_light, hcycle_strong }} }};")
    c.append('const gtint_t gtints[TINT_COUNT] = {\n    { 0, 0, 0, { 0, 0, 0 } },   /* none: its own colour set */\n' + '\n'.join(
        f'    {{ {t["mix"]}, {t["mul"]}, {t["shift"]}, {{ {", ".join(map(str, t["add"]))} }} }},   /* {n} */' for n, t in g['tints'].items()) + '\n};')
    c.append(tint_lut(g['tints']))
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
    c.append('const char *const gstage_names[GS_COUNT] = { ' + ', '.join(json.dumps(s['name']) for s in M['stages']) + ' };')
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
            f'.nby = {len(sc["by"])}, .flags = {sc["if_portrait"]}, .speaker = {c_str(sc["speaker"])}, .line = {{ {", ".join(c_str(t) for t in sc["lines"])} }}, '
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
    heads = bm_heads(build, g); lay = select_layers(g, L); N = len(L)
    sticks, verts = [], []
    for r, (n, base, Ln) in enumerate(lay):              # a cursor graph per layer (select_layers: the unlocked count)
        G = select_stick(Ln, heads, stick)               # TODO #187: the cursor graph from the places
        sl = sorted(Ln, key=lambda m: Ln[m]['slot'])
        sticks.append(f'  {{ /* layer {r}: {n} fighters, places {base}-{base + n - 1} */\n    ' + '\n    '.join(
            [f'{{ {Ln[G[m]["right"]]["slot"]}, {Ln[G[m]["left"]]["slot"]} }},   /* {m}: ' + ' '.join(f'{d} {G[m][d]}' for d in SEL_DIRS) + ' */' for m in sl] +
            [f'{{ {k}, {k} }},   /* (not shown) */' for k in range(n, N)]) + '\n  }')
        vert = lambda m, k: ', '.join([str(Ln[t]['slot']) for t in G[m][k]] + ['0xFF'] * (N - 1 - len(G[m][k])))
        none = ', '.join(['0xFF'] * (N - 1)) or '0xFF'
        verts.append(f'  {{ /* layer {r} */\n    ' + '\n    '.join(
            [f'{{ {{ {vert(m, "ups")} }}, {{ {vert(m, "downs")} }} }},   /* {m} */' for m in sl] +
            [f'{{ {{ {none} }}, {{ {none} }} }},' for k in range(n, N)]) + '\n  }')
    c.append('const uint8_t sel_lay_n[SEL_NLAY] = { ' + ', '.join(str(e[0]) for e in lay) + ' };   /* each layer\'s fighters: slots 0 .. n - 1 (select_layers) */')
    c.append('const uint8_t sel_lay_base[SEL_NLAY] = { ' + ', '.join(str(e[1]) for e in lay) + ' };   /* its first place: slot s stands at SEL_SLOT[base + s] */')
    c.append('const uint8_t sel_stick[SEL_NLAY][SEL_NSLOT][2] = {   /* per layer, the cursor from each slot: right, left (build_tables.py select_stick, select.stick ' + stick + '; locked: on past it) */\n' + ',\n'.join(sticks) + '\n};')
    c.append('const uint8_t sel_vert[SEL_NLAY][SEL_NSLOT][2][SEL_NSLOT - 1] = {   /* per layer, up / down from each slot: the slots that way in preference (the first selectable wins), 0xFF none */\n' + ',\n'.join(verts) + '\n};')
    unl = []; U = unlocks(g)
    for r in g['roster']:
        u = r.get('unlock', 'always')
        if U:                                            # the ladder: 0 a starter, $80 + k rung k (1-based), 0xFF off the
            n = r['name']                                # select screen (an enemy only)
            unl.append(0xFF if not r.get('selectable', True) or n not in U['all'] else 0 if n in U['starters'] else
                       0x80 + 1 + U['ladder'].index(n) // U['rung_size'])
            continue
        unl.append(0xFF if not r.get('selectable', True) else 0 if u == 'always' else u['boss_of_stage'])   # 0xFF: never
                                                                 # picked (a form link's target, main.c char_locked)
        assert u == 'always' or 1 <= u['boss_of_stage'] <= len(g['stages']), f'{r["name"]}: unlock {u}'
    c.append('const uint8_t roster_unlock[BC_COUNT] = { ' + ', '.join(map(str, unl)) + ' };   /* stage k + 1 whose boss unlocks it, '
             '0 = always, $80 + k = the unlock ladder\'s rung k, 0xFF = never (a form; with the ladder: off the select screen) */')
    P = ladder_places(U, U['screen']) if U else []
    h += [f'#define LAD_N {len(P)}            /* the unlock ladder (game.json unlocks): its fighters, starters first; 0 = none */',
          f'#define LAD_RUNGS {len(U["rungs"]) if U else 0}', f'#define LAD_RUNG {U["rung_size"] if U else 0}             /* fighters a rung */',
          'extern const uint8_t lad_fighter[LAD_N ? LAD_N : 1], lad_rung[LAD_N ? LAD_N : 1], lad_slot[LAD_N ? LAD_N : 1];',
          'extern const sel_slot_t lad_pos[LAD_N ? LAD_N : 1];']
    if P:
        c.append('const uint8_t lad_fighter[LAD_N] = { ' + ', '.join(str(idx[e[0]]) for e in P) + ' };   /* ' + ' '.join(e[0] for e in P) + ' */')
        c.append('const uint8_t lad_rung[LAD_N] = { ' + ', '.join(str(e[1]) for e in P) + ' };   /* 0 the starters, k rung k */')
        c.append('const uint8_t lad_slot[LAD_N] = { ' + ', '.join(str(L[e[0]]['slot']) for e in P) + ' };   /* its select slot (its palettes: sel_palbase) */')
        c.append('const sel_slot_t lad_pos[LAD_N] = { ' + ', '.join(f'{{ {e[2]}, {e[3]}, {e[4]}, {e[5]} }}' for e in P) + ' };   /* screen x, feet y, draw order, face */')
    else:
        c += ['const uint8_t lad_fighter[1], lad_rung[1], lad_slot[1];', 'const sel_slot_t lad_pos[1];']
    known = {x['name'] for x in json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['songs']}
    for r in g['roster']:                                # voice note 20261011-160158-5d29: stage 1 plays P1's theme
        assert r.get('music') is None or r['music'] in known, f"{r['name']}: music {r['music']!r} is no songs.json song"
    c.append('const uint8_t roster_music[BC_COUNT] = { ' + ', '.join(f"MUS_{r['music']}" if r.get('music') and not r.get('slot_of') else '0' for r in g['roster'])   # (a Lab build's slot: none, the shell and every pack the same)
             + ' };   /* roster[].music: the fighter\'s theme (its MUS_* command), 0 = none: stage 1 then plays its own song */')
    dmul =[r.get('damage', 1) for r in g['roster']]          # TODO #203: the fighter's damage scale (fighter.c fighter_hit)
    for r, k in zip(g['roster'], dmul): assert isinstance(k, int) and 1 <= k <= 4, f'{r["name"]}: damage {k} (1-4)'
    c += dtier_tables(g, build, dmul)                    # revamp 2: the damage tiers (the scale of a special not measured: dmul)
    c += retime_tables(g, build)
    eh, ec = ending_tables(g)
    h += eh; c += ec
    eh, ec = intro_tables(g)
    h += eh; c += ec
    eh, ec = big_tables(g)
    h += eh; c += ec
    c += bonus_tables(g, known, {v.upper(): int(k, 16) for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['sfx']['names'].items()})
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
    fl = json.load(open(os.path.join(build, 'chainlab.json')))['fighters']
    pools = {f['name']: [None if p.get('seq') else p['input'] for p in f['pool']] for f in fl}   # (a sequence's pieces: by their slot)
    seqs = {f['name']: {p['seq']: i for i, p in enumerate(f['pool']) if p.get('seq') and p['seq_i'] == 0} for f in fl}
    out = []
    for r in g['roster']:
        for k in SPECIAL_KEYS:
            want = r['specials'].get(k)
            if isinstance(want, list):                                      # a SEQUENCE (export_bm.sequences): its first piece
                assert f'specials.{k}' in seqs[r['name']], f"{r['name']}: specials.{k} {want}: no sequence in its pool"
                out.append(seqs[r['name']][f'specials.{k}']); continue
            assert want is None or want in pools[r['name']], f"{r['name']}: no special {want} for {k} (its pool: {' '.join(map(str, pools[r['name']]))})"
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
    g = load(path) if cmd != 'format' else json.load(open(path))   # (format: the file as written, every stage)
    if cmd == 'chars': print(' '.join(chars(g)))
    elif cmd == 'roster': write_if_changed(sys.argv[3], json.dumps(roster_export(g), indent=1) + '\n')
    elif cmd == 'tables': tables(g, sys.argv[3])
    elif cmd == 'format': open(path, 'w').write(fmt(g) + '\n')
    elif cmd == 'pack': open(sys.argv[4], 'wb').write(pack(g, sys.argv[3]))
    elif cmd == 'labstages': json.dump(lab_stages(g, sys.argv[3]), open(sys.argv[4], 'w'))
    elif cmd == 'labenemies': json.dump(lab_enemies(g), open(sys.argv[3], 'w'))
    else: sys.exit(__doc__)
