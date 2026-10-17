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
             'bspec_dz', 'rush_dx', 'rest_bspec', 'jump_min', 'jump_max', 'jump_dz', 'jump_chance', 'rest_jump', 'air_b_dx', 'hop_dx', 'hop_chance',
             'aa_dx', 'aa_dz', 'aa_chance', 'aa_react', 'punish_chance', 'punish_react', 'rush_min', 'rush_max', 'rush_chance']
AI_MOVES = {'roles': 1, 'flank': 2}                       # gamedata.h AIM_* (a preset's "moves": the situations it reads)
CHANCE_MASKS = {'follow_ups': 'follow_mask', 'rev_chance': 'rev_mask', 'bspec_chance': 'bspec_mask'}   # "1 in N" -> mask N-1
MAX_ENEMIES = 6                                          # main.c NF - 2
MAX_SLOTS = 25                                           # main.c NA (an actor per slot): (381 - SEL_SPR 57 - the barriers 21) / SEL_COLS 12
SP_WALK_IN, SP_LEFT, SP_NOT_BOSS = 1, 2, 4               # gamedata.h gspawn_t.flags; rank in bits 4-7
GE_FIGHTER_NAME, GE_SPAWN, GE_DOUT_SH = 1, 0xFF, 1        # gamedata.h genemy_t
GD_VERSION, GD_MAX = 8, 4096                             # gamedata.h data pack (2: + the roster section, 3: + voices, 4: + triggers, 5: + AI hop_*,
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
    rung_size, rungs: [[fighter]], all: starters + ladder}. starters: playable from the start; the rungs: one per game
    clear (the last stage's boss beaten), in order, either `rungs` = [[fighter, ...], ...] (each its own size, 1-6:
    Bruno 2026-10-15, the beta's last rung is Haggar alone) or `ladder` cut `rung_size` at a time; every other roster
    fighter is off the select screen (an enemy only). Each must be a selectable roster fighter. rung_size returned:
    the rungs' size when they are all one size, else None."""
    u = g.get('unlocks')
    if not u: return None
    for k in u: assert k in ('about', 'starters', 'ladder', 'rung_size', 'rungs', 'screen', 'show_next', 'locked_name', 'locked_text', 'locked_text_about'), f'unlocks: unknown field {k}'
    v = u.get('locked_name', '')                         # (Bruno 2026-10-17: the next rung as silhouettes on the select)
    assert isinstance(v, str) and len(v) <= 38 and all(0x20 <= ord(ch) < 0x7F for ch in v), 'unlocks.locked_name: ASCII, 38 characters at most'
    v = u.get('locked_text', [])                         # (note 20261017-114857-e03d: lines over the silhouette, above its cursor)
    assert isinstance(v, list) and len(v) <= 3 and all(isinstance(t, str) and 1 <= len(t) <= 16 and all(0x20 <= ord(ch) < 0x7F for ch in t) for t in v), \
        'unlocks.locked_text: up to 3 lines, ASCII, 16 characters at most each'
    assert isinstance(u.get('show_next', False), bool), 'unlocks.show_next: true | false'
    names = [r['name'] for r in g['roster'] if r.get('selectable', True)]
    st = list(u.get('starters') or [])
    assert st, 'unlocks.starters: at least one fighter'
    if 'rungs' in u:
        assert 'ladder' not in u and 'rung_size' not in u, 'unlocks: rungs, or ladder + rung_size, not both'
        rg = [list(r) for r in u['rungs']]
        assert rg and all(isinstance(r, list) and 1 <= len(r) <= 6 for r in rg), 'unlocks.rungs: [[fighter, ...], ...], 1-6 a rung'
        la = [f for r in rg for f in r]; n = len(rg[0]) if all(len(r) == len(rg[0]) for r in rg) else None
    else:
        la, n = list(u.get('ladder') or []), u.get('rung_size')
        assert isinstance(n, int) and 1 <= n <= 6, f'unlocks.rung_size {n!r}: 1-6'
        assert len(la) % n == 0, f'unlocks.ladder: {len(la)} fighters, not whole rungs of {n}'
        rg = [la[i:i + n] for i in range(0, len(la), n)]
    al = st + la
    dup = sorted({f for f in al if al.count(f) > 1})
    assert not dup, f'unlocks: {", ".join(dup)} twice'
    for f in al: assert f in names, f'unlocks: {f} is not a selectable roster fighter'
    assert len(al) <= LADDER_MAX, f'unlocks: {len(al)} fighters, {LADDER_MAX} at most (main.c NA)'
    scr = u.get('screen') or {}
    for k, v in scr.items(): assert k in LADDER_SCREEN and isinstance(v, int), f'unlocks.screen.{k} {v!r} (feet, margin, pitch: px)'
    assert 40 <= scr.get('pitch', 90) <= 200, 'unlocks.screen.pitch: 40-200 px'
    return {'starters': st, 'ladder': la, 'rung_size': n, 'rungs': rg, 'all': al, 'screen': scr}


BUILD_DEFAULT = os.path.join(REPO, 'examples', 'brawler', 'build')
SEL_AUTO = {'feet': [196, 204], 'gap': 6, 'pitch': 100, 'margin': 16}   # game.json select.auto defaults (select_auto)
SEL_TV = (8, 312)                                        # the screen x a TV shows (the LSPC's 8 .. 311)
_SEL_EXT = {}


def sel_extents(build, g, names):
    """each fighter's select pose as the game draws it, facing LEFT (the ROM sprites'): its opaque pixels' span per row,
    {name: {dy: (l, r)}} (px from the feet, l .. r inclusive; chainlab/select_images.py's picture of the build's
    'watch' frame = the select screen's, select_proof pixel for pixel)"""
    key = os.path.abspath(build)
    if key not in _SEL_EXT:
        sys.path.insert(0, os.path.join(HERE, 'chainlab'))
        import numpy as np, base64
        import select_images as SI
        rom = SI.Rom(build); E = {}
        for n in [r['name'] for r in g['roster'] if r.get('selectable', True)]:
            w = rom.arr(f'{n}_watch')
            if not w: continue
            fi = int(re.findall(r'\{(\d+), (\d+), (\d+), \{', w)[-1][0])
            fr = SI.left_frame(SI.rom_parts(rom, n, fi, rom.tile_hi[n]), rom.tile)
            a = np.frombuffer(base64.b64decode(fr['pix']), np.uint8).reshape(fr['h'], fr['w']) & 15
            E[n] = {}
            for y in range(fr['h']):
                c = np.nonzero(a[y])[0]
                if len(c): E[n][y - fr['oy']] = (int(c[0]) - fr['ox'], int(c[-1]) - fr['ox'])
        _SEL_EXT[key] = E
    E = _SEL_EXT[key]
    for n in names: assert n in E, f'select: no select pose for {n} in {build}'
    return E


def sel_spans(e, v):
    """a fighter's opaque spans on the street at its place v ({x, y, facing}): {screen y: (l, r)}; facing right mirrors
    as draw.s (x -> 2 ox - 1 - x: offset c -> -c - 1)"""
    return {v['y'] + dy: ((v['x'] - r - 1, v['x'] - l - 1) if v['facing'] == 'right' else (v['x'] + l, v['x'] + r)) for dy, (l, r) in e.items()}


def sel_overlap(a, b):
    """two fighters' overlap on the screen in pixels (their spans' common pixels, row by row)"""
    return sum(max(0, min(a[y][1], b[y][1]) - max(a[y][0], b[y][0]) + 1) for y in a if y in b)


def select_auto(g, names, E, L):
    """the select screen's places for the n fighters `names` (in the stick's order), automatic (Bruno's note
    20261015-135645-e03d: "Characters are bunched up together... avoid overlap as much as possible"): one line along the
    street, left to right in order, the left half facing right, the right half left (the middle one: left), feet y
    alternating select.auto.feet (a front / back stagger; the front one drawn over, the middle ones over the ends).
    x: each fighter as close to the previous one as its pose allows with `gap` px between their drawn pixels (row by row:
    sel_extents, against every one before it), but never closer than an even pitch U = the TV's width minus 2 x `margin`
    shared over the n - 1 steps, at most `pitch` px (2-4 fighters: evenly spaced on one screen); the whole run centred on
    the street (SELECT_W / 2). Wider than the screen (6 fighters: ~450 px of bodies): the camera pans along the group
    (select_cams). -> {fighter: {x, y, z, facing, pose, slot}} (pose: L's)."""
    o = g.get('select', {}).get('auto'); o = o if isinstance(o, dict) else {}
    for k in o: assert k in SEL_AUTO or k == 'about', f'select.auto.{k}: one of {sorted(SEL_AUTO)}'
    a = dict(SEL_AUTO, **{k: v for k, v in o.items() if k in SEL_AUTO})
    n = len(names); fe = a['feet']
    P = {f: {'x': 0, 'y': fe[k % len(fe)], 'facing': 'right' if 2 * k < n - 1 else 'left'} for k, f in enumerate(names)}
    def span(f): return sel_spans(E[f], P[f])
    for k, f in enumerate(names): P[f]['x'] = k * a['pitch']   # a fixed even spacing (Bruno 2026-10-15: "just space
                                                                # them evenly with a fixed number, big enough")
    S = [span(f) for f in names]
    A, B = min(l for s in S for l, r in s.values()), max(r for s in S for l, r in s.values())
    dx = SELECT_W // 2 - (A + B + 1) // 2
    out = {}
    for k, f in enumerate(names): out[f] = dict(P[f], x=P[f]['x'] + dx, pose=L[f]['pose'], slot=k)
    for z, f in enumerate(sorted(names, key=lambda f: (out[f]['y'], -abs(2 * names.index(f) - (n - 1))))): out[f]['z'] = z
    for f, v in out.items(): assert 0 <= v['x'] < SELECT_W, f'select.auto: {f} at x {v["x"]} off the street'
    return {f: {k: out[f][k] for k in ('x', 'y', 'z', 'facing', 'pose', 'slot')} for f in names}


def select_cams(Ln, E, cam_max):
    """a layout's camera range (main.c sel_cam_goal, selectrender.js camFor): the group's drawn pixels A .. B on the
    street; fitting the TV with `margin` px each side: the camera fixed on its middle (lo = hi), else the cursor-centred
    camera kept inside A - 16 .. B + 16 (no empty street past the group's ends); inside 0 .. cam_max -> (lo, hi)"""
    S = [sel_spans(E[f], v) for f, v in Ln.items()]
    A, B = min(l for s in S for l, r in s.values()), max(r for s in S for l, r in s.values())
    m = SEL_AUTO['margin']; tv0, tv1 = SEL_TV
    if B - A + 1 <= tv1 - tv0 - 2 * m: lo = hi = (A + B + 1) // 2 - 160
    else: lo, hi = A - tv0 - m, B + 1 + m - tv1
    lo, hi = (max(0, min(cam_max, v)) for v in (lo, hi))
    return lo, max(lo, hi)


def select_layers(g, L=None, build=None):
    """the select screen's layouts by unlocked count (Bruno 2026-10-15: "only the available characters show up"):
    [(n, base, Ln)] per layer, base = the layer's first place in SEL_SLOT (the layers' places back to back: SEL_NPLACE).
    No unlocks block: one layer, every slot (n = all, base 0, L). With the unlock ladder: layer r = r rungs unlocked
    (0 .. len(rungs)); its n = starters + the first r rungs' fighters = the first n of the ladder order (slots 0 .. n - 1);
    game.json select.auto (note 20261015-135645-e03d): their places laid out by select_auto for that count (spread, no
    overlap); without it the n CONSECUTIVE places of the hand layout (select_layout), centred ((all - n) // 2 on). Ln =
    {fighter: its place} (slot 0 .. n - 1, z 0 ..): the layer's own cursor graph (select_stick) is computed on it; main.c
    draws only those n (a locked one is not drawn)."""
    L = L or select_layout(g); U = unlocks(g); order = sorted(L, key=lambda n: L[n]['slot'])
    if not U: return [(len(L), 0, L)]
    assert order == U['all'], f'select_layout: the slots must follow the ladder order {U["all"]} (got {order})'
    auto = g.get('select', {}).get('auto')
    E = sel_extents(build or BUILD_DEFAULT, g, order) if auto else None
    out, base = [], 0
    for r in range(len(U['rungs']) + 1):
        n = len(U['starters']) + sum(len(c) for c in U['rungs'][:r])
        if auto: Ln = select_auto(g, order[:n], E, L)
        else:
            c = (len(order) - n) // 2
            Ln = {f: dict(L[order[c + k]], slot=k, pose=L[f]['pose']) for k, f in enumerate(order[:n])}
            for i, f in enumerate(sorted(Ln, key=lambda m: Ln[m]['z'])): Ln[f]['z'] = i
        out.append((n, base, Ln)); base += n
    return out


def select_shown(g, build=None):
    """the layout the select screen shows with everyone unlocked (select_layers' last layer: with select.auto the
    build's own places; else select_layout): what the Factory's Select screen editor opens as "the game's layout" and
    select_proof compares"""
    return select_layers(g, None, build)[-1][2]


LADDER_SCREEN = {'feet': 200, 'margin': 40, 'pitch': 90}   # unlocks.screen defaults (ladder_places)


def ladder_places(U, scr=None):
    """the unlock ladder screen's places (main.c ladder_start; Bruno 2026-10-15: "every character on the same horizontal
    axis", then "same idea as the select screen: make them spaced enough, from left to right; if the characters are too
    far to the right, just scroll"): every ladder fighter (starters, then the rungs) at full size on ONE line, feet at
    screen y `feet`, in ladder order left to right at a fixed `pitch` px feet to feet, the first `margin` px from the
    left; a row narrower than the TV centred on it, a wider one panned by the camera (ladder_cam_max, main.c lad_camera);
    each in its select pose facing the middle; drawn from the ends inward (the middle ones in front where the bodies
    overlap) -> [(fighter, rung 0 = starters, world x, y, z, face)]"""
    s = dict(LADDER_SCREEN, **(scr or {})); al = U['all']; n = len(al); out = []
    rung = {f: 0 for f in U['starters']}
    for k, c in enumerate(U['rungs']): rung.update({f: k + 1 for f in c})
    w = (n - 1) * s['pitch']
    x0 = 160 - w // 2 if w <= 320 - 2 * s['margin'] else s['margin']
    for k, f in enumerate(al): out.append([f, rung[f], x0 + k * s['pitch'], s['feet'], 0, 1 if 2 * k < n - 1 else -1])
    for z, e in enumerate(sorted(out, key=lambda e: (-abs(2 * al.index(e[0]) - (n - 1)), e[2]))): e[4] = z
    return [tuple(e) for e in out]


def ladder_cam_max(U, scr=None):
    """the ladder camera's right end (main.c LAD_CAM_MAX): the last fighter's feet `margin` px from the TV's right edge"""
    s = dict(LADDER_SCREEN, **(scr or {})); P = ladder_places(U, scr)
    return max(0, P[-1][2] + s['margin'] - 320) if P else 0


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
              'stun_light', 'stun_heavy', 'juggle_reset_button')
JUGGLE_RESET = {None: 0, 'C': 1}                         # chain.juggle_reset_button -> gchain.jreset (gamedata.h JR_*)


def chain_cfg(g, r):
    """a roster fighter's chain (revamp 1A, routes.py chain_tree): its archetype's length and damage total, the hit-stop
    scale, its finishers, its damage scale (for the entries)"""
    c = g['chain']
    a = r.get('archetype')
    assert a in ('fast', 'balanced', 'heavy'), f"roster {r['name']}: archetype {a} (fast / balanced / heavy)"
    fin = r.get('finishers') or {}
    for k in fin: assert k in ('launcher', 'down', 'neutral', 'forward', 'up', 'down_move', 'df_move'), f"roster {r['name']}: finishers.{k}"
    own = r.get('chain') or {}                     # (revamp 5, the chain tool's save) links: the moves before the finisher,
    for k in own: assert k in ('links', 'hitstop', 'length', 'keep', 'keep_about'), f"roster {r['name']}: chain.{k} (links / hitstop / length / keep)"   # hitstop: per link + the finisher
    assert isinstance(own.get('keep', False), bool), f"roster {r['name']}: chain.keep true / false"   # keep: every link and
                                                     # finisher plays to its end on hit (routes.py 'keep', RF_KEEP)
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
            **({'hitstops': own['hitstop']} if 'hitstop' in own else {}), **({'keep': True} if own.get('keep') else {})}


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


def xthr_cost(g):
    """gxthr_cost: per roster fighter (bm_chars order) the drive chunks each hold extra costs (note 20261017-015547-e03d, SS2
    Hanzo's Mozu Otoshi on B in the hold: "make this special throw consume like one meter"): roster[].throws.extra_cost
    {u / d / b: chunks 0-4} -> (u, d, b); unset 0 = free, as before. fighter.c hold_update: a player's hold extra (up / down
    + A, B) that costs comes out only with that many chunks in the drive (paid, no flash); short of them
    the press does nothing and the hold goes on. Enemies pay nothing (the meter is the players')"""
    out = []
    for r in g['roster']:
        t = r.get('throws') or {}
        e = t.get('extra_cost') or {}
        w = f"roster {r['name']}: throws.extra_cost"
        for k, v in e.items():
            if k == 'about': continue
            assert k in ('u', 'd', 'b'), f'{w}: key {k!r} (u = hold + up + A, d = hold + down + A, b = hold + B)'
            assert (t.get('extra') or {}).get(k), f'{w}.{k}: no throws.extra.{k} to pay for'
            assert isinstance(v, int) and 0 <= v <= 4, f'{w}.{k}: 0-4 drive chunks'
        out.append((r['name'], tuple(e.get(k, 0) for k in ('u', 'd', 'b'))))
    return out

def run_grab(g, build):
    """grun_grab: per roster fighter (bm_chars order) its run grab (note 20261016-100735-e03d, SS2 Hanzo's Mozu Otoshi out of
    a run: "performed AUTOMATICALLY if Hanzo is running into an opponent for at least 30 frames; at the moment of the grab,
    if there is at least 1 meter, this special Mozu Otoshi, with the blue special tint"): roster[].throws.run {special: a
    grab special of its bank (export_bm throw_specials puts it in the pool), frames: the run's frames at least (1-255), cost:
    drive chunks (1-4)} -> (its pool index, frames, cost); none: (0xFF, 0, 0). fighter.c try_grab: a player whose run
    (S_RUN, not a dash) has lasted `frames` grabs with that special instead of the hold when its drive holds `cost`
    chunks (paid, the special's blue flash); short of them, the hold as before"""
    fl = json.load(open(os.path.join(build, 'chainlab.json')))['fighters']
    pools = {f['name']: [p['input'] for p in f['pool']] for f in fl}
    out = []
    for r in g['roster']:
        e = (r.get('throws') or {}).get('run')
        if not e: out.append((r['name'], (0xFF, 0, 0))); continue
        w = f"roster {r['name']}: throws.run"
        for k in e: assert k in ('special', 'frames', 'cost', 'about'), f'{w}: unknown field {k}'
        assert e.get('special') in pools[r['name']], f"{w}.special {e.get('special')}: not in its pool ({' '.join(map(str, pools[r['name']]))})"
        assert isinstance(e.get('frames'), int) and 1 <= e['frames'] <= 255, f'{w}.frames: 1-255 run frames'
        assert isinstance(e.get('cost', 1), int) and 1 <= e.get('cost', 1) <= 4, f'{w}.cost: 1-4 drive chunks'
        ix = pools[r['name']].index(e['special'])
        assert ix < 0xFF, f'{w}: pool index {ix}'
        out.append((r['name'], (ix, e['frames'], e.get('cost', 1))))
    return out


def special_sounds(g, build, snames):
    """gspec_snd: roster[].special_sounds {special input: [{sfx: songs.json sfx name, at: [program frames]}], about} ->
    [(roster index = bchar_t.id, the special's pool index, frame, sfx code)], by fighter then special then frame.
    fighter.c spec_sounds: the frame a special's program reaches fighter_t.srow == at, the effect is sent (note
    20261016-100735-e03d round 3: SS2's $1A $2B whistle at the run Mozu Otoshi's leap and its repeats)"""
    fl = json.load(open(os.path.join(build, 'chainlab.json')))['fighters']
    pools = {f['name']: [p['input'] for p in f['pool']] for f in fl}
    out = []
    for i, r in enumerate(g['roster']):
        for inp, lst in (r.get('special_sounds') or {}).items():
            if inp == 'about': continue
            w = f"roster {r['name']}: special_sounds.{inp}"
            assert inp in pools[r['name']], f"{w}: not in its pool ({' '.join(map(str, pools[r['name']]))})"
            for e in lst:
                for k in e: assert k in ('sfx', 'at'), f'{w}: unknown field {k}'
                assert e['sfx'].upper() in snames, f"{w}: {e['sfx']!r} is no songs.json sfx name (the V ROM has no sample for it)"
                assert all(isinstance(t, int) and 1 <= t <= 0xFFFF for t in e['at']), f'{w}.at: program frames 1-65535'
                out += [(i, pools[r['name']].index(inp), t, snames[e['sfx'].upper()]) for t in e['at']]
    return sorted(out)


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


def blitz_hits(g):
    """gblitz_hit: per roster fighter (bm_chars order) its Blitz played as a tree node, [0] the dash entry (a slot 'dash'),
    [1] a normal's blitz entry (a slot naming a move): [vy, vx, recovery] (roster[].blitz_hit {slot: {launch, recovery}};
    note 20261017-141149-e03d, Haggar's run + A: "make the bounce not as high: high -> medium, medium -> low; after the
    impact add four frames of recovery"): launch = a size of game.json throw_launch.up (small / medium / big) for the
    victim its hit knocks down from the ground (16.16 px a frame up / away; the engine's own knockdown, vy 7 vx 2, is
    throw_launch.up.big), recovery = frames it holds its last pose after its animation, before control comes back
    (fighter.c fighter_hit / S_ATTACK); [0, 0, 0] = none (the engine's knockdown, no extra recovery)"""
    up = g['throw_launch']['up']
    out = []
    for r in g['roster']:
        bz = r.get('blitz') or {'ff': 'dash'}; row = [[0, 0, 0], [0, 0, 0]]
        for k, v in (r.get('blitz_hit') or {}).items():
            if k == 'about': continue
            assert k in BLITZ_SLOTS and k in bz, f"roster {r['name']}: blitz_hit.{k}: not one of its Blitz slots"
            sl = bz[k]
            assert sl == 'dash' or (isinstance(sl, str) and BLITZ_NORMAL.match(sl)), \
                f"roster {r['name']}: blitz_hit.{k}: its Blitz {sl} is a special (blitz_hit: the dash entry or a normal)"
            assert set(v) <= {'launch', 'recovery', 'about'}, f"roster {r['name']}: blitz_hit.{k}: launch / recovery"
            L = v.get('launch')
            assert L is None or L in up, f"roster {r['name']}: blitz_hit.{k}.launch: one of throw_launch.up {' / '.join(up)}"
            rc = v.get('recovery', 0)
            assert isinstance(rc, int) and 0 <= rc <= 60, f"roster {r['name']}: blitz_hit.{k}.recovery 0-60 frames"
            row[0 if sl == 'dash' else 1] = [round(up[L]['vy'] * 65536) if L else 0, round(up[L]['vx'] * 65536) if L else 0, rc]
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
             **{k: r[k] for k in ('form', 'stage_end_form', 'display', 'variant', 'scale', 'moves', 'anim_specials', 'fire', 'flash_pose', 'charge_from', 'air_specials', 'blitz', 'down_attack', 'invincible', 'juggle', 'hit_react', 'source_flight', 'keeps_air_attack', 'proj_react', 'together', 'seq_press', 'seq_hit', 'hit_next', 'nopush', 'max', 'proj_hits', 'special_final_area', 'special_grab_timing', 'box_both_sides', 'box_trim', 'run', 'slot_of', 'swing', 'win_fx_off', 'voice_whole', 'prog_voices') if k in r}} for r in g['roster']]


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
    mv = 0
    for f in p.get('moves', []): assert f in AI_MOVES, f'AI {n}: moves {f} ({list(AI_MOVES)})'; mv |= AI_MOVES[f]
    v['moves'] = mv
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


AI_ROLES = ['projectile', 'anti_air', 'rush']                # gamedata.h AR_* (ai_roles[fighter][AR_*] = a special slot BS_*)


def ai_roles(g, lab):
    """ai_roles[BC_COUNT][AR_COUNT]: per roster fighter (bm_chars order) the special slot (BS_D .. BS_UF_D: neutral, f, d,
    u, df, uf + C) the enemy AI plays as its projectile / anti-air / rush (ai.c "situations", Bruno 2026-10-16: the
    enemies' wide range of moves), 0xFF none. Read from the export (build/chainlab.json fighters[].pool: each slot's
    special's travel, height, first hit, projectile): projectile = a slot whose special throws one (a travelling one
    first, then an eruption); anti-air = a rising special (height >= 35 px, travel <= 140 px, its first hit by frame 12,
    no travelling projectile), the highest and quickest; rush = a forward one (travel >= 80 px, height <= 50 px, first
    hit by frame 24, no projectile), the longest and quickest. roster[].ai_roles {"projectile": "dD", ...: a slot key,
    or null = none} overrides the pick"""
    fl = {f['name']: f for f in lab['fighters']}
    out = []
    for r in g['roster']:
        f = fl.get(r['name']); row = [0xFF] * len(AI_ROLES)
        if f:
            pool = {p['input']: p for p in f['pool']}
            sl = []
            for k, key in enumerate(SPECIAL_KEYS):
                v = (f.get('specials') or {}).get(key)
                if isinstance(v, list): v = v[0]
                if v in pool: sl.append((k, pool[v]))
            first = lambda p: p['first'] if p['first'] is not None else 99
            row[0] = min(((p['proj']['kind'] != 1, k) for k, p in sl if p['proj']), default=(0, 0xFF))[1]
            row[1] = min(((p['travel'] / 2 + 4 * first(p) - p['height'], k) for k, p in sl
                          if p['height'] >= 35 and p['travel'] <= 140 and first(p) <= 12 and not (p['proj'] and p['proj']['kind'] == 1)),
                         default=(0, 0xFF))[1]
            row[2] = min(((2 * p['height'] + 2 * first(p) - p['travel'], k) for k, p in sl
                          if p['travel'] >= 80 and p['height'] <= 50 and first(p) <= 24 and not p['proj']), default=(0, 0xFF))[1]
        for k, v in (r.get('ai_roles') or {}).items():
            if k == 'about': continue
            assert k in AI_ROLES, f"roster {r['name']}: ai_roles.{k} ({AI_ROLES})"
            assert v is None or v in SPECIAL_KEYS, f"roster {r['name']}: ai_roles.{k} = {v!r} (a slot {SPECIAL_KEYS} or null)"
            row[AI_ROLES.index(k)] = 0xFF if v is None else SPECIAL_KEYS.index(v)
        out.append((r['name'], row))
    return out


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
        for k in e: assert k in ('name', 'base', 'pool', 'stand_in', 'life', 'power', 'ai', 'attract_ai', 'ai_over', 'palette', 'moves', 'hud', 'boss_ai', 'damage_out', 'damage_about'), f'enemy {n}: unknown field {k}'
        if e['base'] == 'pool':
            pl = [idx[x] for x in e['pool']]
            assert pl == sorted(pl), f'enemy {n}: list the pool in roster order'
            base = 0xFF
        else:
            b = e['base'] if e['base'] in idx else e.get('stand_in')
            assert b in idx, f'enemy {n}: neither {e["base"]} nor its stand-in is in the roster'
            base, pl = idx[b], []
        over = e.get('ai_over') or {}
        for k in over: assert k in AI_FIELDS or k in CHANCE_MASKS or k in ('flags', 'proj_chance', 'moves'), f'enemy {n}: ai_over {k}'
        st, ti, cu = palette(e, n)
        assert ti is None or ti in tint_idx, f'enemy {n}: no tint {ti}'
        assert st == GE_SPAWN or 0 <= st < 255, f'enemy {n}: palette set {st}'
        assert 1 <= e['life'] <= 32767 and 0 <= e.get('power', 0) <= 255, f'enemy {n}: life 1-32767, power 0-255'
        do = e.get('damage_out', 1)                    # its outgoing damage (note 20261016-180551-e03d: bosses x 0.5), in eighths
        assert isinstance(do, (int, float)) and 1 <= round(do * 8) <= 8 and abs(do * 8 - round(do * 8)) < 1e-9, \
            f'enemy {n}: damage_out 0.125-1 in eighths (x its every hit, throw, chip, thrown body)'
        dout = 8 - round(do * 8)                       # (genemy_t flags GE_DOUT: 0 = whole)
        M['enemies'].append({'name': n, 'base': base, 'pool': pl, 'ai': row(n, e['ai'], over),
                             'attract_ai': row(n, e.get('attract_ai', e['ai']), over), 'power': e.get('power', 0),
                             'set': st, 'tint': GE_SPAWN if ti is None else tint_idx[ti], 'flags': (GE_FIGHTER_NAME if name == 'fighter' else 0) | dout << GE_DOUT_SH,
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
        st0 = s.get('start', 0)                          # (Bruno 2026-10-17: the final stage starts further into its background)
        assert isinstance(st0, int) and 0 <= st0 <= (ww - 320 if ww else 32767) and (not s['waves'] or st0 <= s['waves'][0]['lock']), \
            f'stage {si + 1}: start {st0}: 0..width - 320, at most the first wave\'s lock'
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
        fz = b.get('finale')                             # (Bruno 2026-10-17: a second boss fight in the same stage, main.c "the finale")
        fin = None
        if fz:
            for k in fz: assert k in ('about', 'enemy', 'song', 'drama', 'x', 'z', 'seed', 'minions'), f'stage {si + 1}: boss.finale: unknown field {k}'
            assert fz['enemy'] in en_idx and (not mus or fz['song'] in mus) and (fz.get('drama') is None or fz['drama'] in dr_idx), \
                f'stage {si + 1}: boss.finale: enemy / song / drama unknown'
            assert len(fz['minions']) <= MAX_ENEMIES - 1, f'stage {si + 1}: boss.finale: at most {MAX_ENEMIES - 1} minions'
            assert ww is None or b['lock'] - 24 <= fz['x'] <= b['lock'] + 340, f'stage {si + 1}: boss.finale.x: at the boss lock\'s screen'
            fin = {'boss': en_idx[fz['enemy']], 'song': fz['song'], 'drama': dr_idx[fz['drama']] if fz.get('drama') else 0xFF,
                   'x': fz['x'], 'z': fz['z'], 'seed': int(str(fz['seed']), 0),
                   'spawns': [spawn(d, f'stage {si + 1} finale', b['lock']) for d in fz['minions']]}
        M['stages'].append({'name': s['name'], 'bg': s['background'], 'music': s['music'], 'power': s.get('power', 0), 'waves': wv, 'finale': fin,
                            'spawns': sp, 'boss': en_idx[b['enemy']], 'boss_song': b['song'], 'unlock': unl, 'boss_lock': b['lock'],
                            'boss_x': b['x'], 'boss_z': b['z'], 'boss_seed': int(str(b['seed']), 0), 'boss_first': nb, 'nmin': len(b['minions']),
                            'music_n': mus.get(s['music']), 'boss_song_n': mus.get(b['song']), 'triggers': trig,
                            'drama': dr_idx[b['drama']] if b.get('drama') else 0xFF, 'start': st0})
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
            'hop_dx', 'hop_chance', 'proj_mask', 'proj_mask2', 'moves', 'aa_dx', 'aa_dz', 'aa_chance', 'aa_react',
            'punish_chance', 'punish_react', 'rush_min', 'rush_max', 'rush_chance']
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


METER_KEYS = ('about', 'chunk', 'chunks', 'max_chunks', 'max_chunks_about', 'special', 'breaker', 'life_breaker', 'blink', 'fury_max', 'fury_dealt',
              'fury_taken', 'low', 'infinite', 'fury_drive', 'max_drive', 'refill_pause', 'special_flash', 'breaker_when',
              'breaker_fury', 'breaker_about')
BREAKER_WHEN = {'hitstun': 1, 'grabbed': 2, 'thrown': 4}           # gamedata.h BK_*: meter.breaker_when / breaker_fury names
WAKE_KEYS = ('about', 'special', 'fury', 'from', 'ai_chance', 'ai_dx', 'ai_dz')
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


TIMING_KEYS = ('forward', 'back', 'hold_b')             # gamedata.h TM_FWD / TM_BACK / TM_HOLD_B
TIMING_KINDS = ('impact', 'slam')


def slam_bounce(e, dflt, w):
    """a SLAM's ground bounce (note 20261016-095622-e03d, the tester: "at the moment of the slam (the victim hits the
    ground), make the victim bounce a bit, so that I can continue juggling a bit"): game.json "slam_bounce" {vy, vx} =
    every slam's (a paired throw's throws.timing kind slam, a grab special's special_grab_timing); an entry's own
    "bounce" {vy, vx} | false overrides it. vy px a frame up, vx px a frame away from the thrower (fighter.c
    slam_bounce) -> (vy, vx) 8.8, (0, 0) none"""
    b = e.get('bounce', dflt)
    if b is False or b is None: return (0, 0)
    assert isinstance(b, dict), f'{w}.bounce: {{vy, vx}} | false'
    for k in b: assert k in ('about', 'vy', 'vx'), f'{w}.bounce: unknown field {k}'
    assert isinstance(b.get('vy'), (int, float)) and 0.5 <= b['vy'] <= 12, f'{w}.bounce.vy: 0.5-12 px a frame up'
    assert isinstance(b.get('vx', 0), (int, float)) and -8 <= b.get('vx', 0) <= 8, f'{w}.bounce.vx: -8..8 px a frame away'
    return (round(b['vy'] * 256), round(b.get('vx', 0) * 256))


EVENT_DIRS = ('up', 'away', 'back', 'none')         # back: away's flight the opposite horizontal way (TE_BACK)
LAUNCH_TABLE = {'back': 'away'}                         # the throw_launch entry a dir's speeds come from (back = away's)
ENGINE_PLAYS_EVENTS = True                              # fighter.c plays throws.events (THE THROW EVENTS)
EVENT_SIZES = ('small', 'medium', 'big')
EVENT_KEYS = TIMING_KEYS + ('run',)                     # + the run grab's special (roster[].throws.run.special)


EVENT_IMPS = 3                                          # gamedata.h EV_IMPS: impacts a throw at most
IMPACT_FX = ('spark', 'sound', 'shake')                 # gamedata.h EVF_SPARK / EVF_SOUND / EVF_SHAKE


def event_impacts(e, w):
    """a throw's impacts, checked: [{frame, damage, spark, sound, shake}] (throws.events.<k>.impacts; a lone "impact": N is
    the one-entry list [{frame: N}]); damage = its share of the throw's damage in % (default 0, the last one: all that is
    still due, so by default the whole damage on the last impact); spark / sound / shake default true"""
    assert ('impact' in e) != ('impacts' in e), f'{w}: impacts [{{frame, damage?, spark?, sound?, shake?}}, ...] (or one impact: N)'
    L = e['impacts'] if 'impacts' in e else [{'frame': e['impact']}]
    assert isinstance(L, list) and 1 <= len(L) <= EVENT_IMPS, f'{w}.impacts: 1-{EVENT_IMPS} impacts'
    out, prev, tot = [], 0, 0
    for n, x in enumerate(L):
        wi = f'{w}.impacts[{n}]'
        assert isinstance(x, dict), f'{wi}: {{frame, damage?, spark?, sound?, shake?}}'
        for f in x: assert f in ('frame', 'damage') + IMPACT_FX + ('about',), f'{wi}: unknown field {f}'
        fr = x.get('frame')
        assert isinstance(fr, int) and not isinstance(fr, bool) and 1 <= fr <= 400, f'{wi}.frame: a throw frame 1-400'
        assert fr > prev, f'{wi}.frame {fr}: after the impact before it (frame {prev})'
        prev = fr
        d = x.get('damage', 0)
        assert isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 100, f'{wi}.damage: its share of the throw\'s damage, 0-100 %'
        for f in IMPACT_FX: assert x.get(f, True) in (True, False), f'{wi}.{f}: true | false'
        if n + 1 < len(L): tot += d
        out.append({'frame': fr, 'damage': d, **{f: x.get(f, True) for f in IMPACT_FX}})
    assert tot <= 100, f'{w}.impacts: the shares before the last add up to {tot} % (100 at most)'
    assert 'damage' not in L[-1] or tot + L[-1]['damage'] == 100, f'{w}.impacts: the last takes what is still due ({100 - tot} %)'
    return out


def throw_events(r, g=None):
    """roster[].throws.events (THE THROW REVIEW round 2, Bruno 2026-10-16 after 0.10.142: "define WHEN THE IMPACT occurs
    (the visual + the sound), and separately WHEN THE ACTUAL LAUNCH occurs (ejecting the victim up, or ejecting it
    sideways) [...] Separate these concerns"; written by tools/brawler/throw_answers.py apply2 from review.html?q=throws2):
    per throw (forward | back | hold_b | run) {impacts: [{frame, damage?, spark?, sound?, shake?}, ...] (or impact: N),
    held?: N, launch: {frame: N, dir: up | away | back | none, size?: small | medium | big}, from?, about?}, N = the throw's frame
    (1 = its first frame, every game frame from its start counted, as the review page numbers them). Four concerns, each
    its own field, never mixed:
      the grab motion  the throw's script (paired: bthrow_t rows) / the grab special's victim lists: where both are
      impacts  1-3 (Kyo's: a blow, then his slam), each on its frame: its share of the throw's damage (damage %, the last
               all that is still due: by default the whole damage on the last), its spark, its sound, the screen shake
               (game.json throw_shake), each true unless false (event_impacts)
      held     the victim stays in the thrower's grip (the grab motion) until that frame; from there to the launch it
               stays where it is, in its pose (default: the launch frame)
      launch   the release and its trajectory: the engine takes the victim over on that frame and sends it: up (a pop),
               away (along the throw's way, from the thrower), back (away's flight the opposite horizontal way, toward the
               thrower's side: notes 20261016-140504-8a04 / 140505-8a05, SS2 Hanzo's throws), none (where it is: on the floor it lies, in the air it
               falls); size picks game.json throw_launch[dir][size] {vy, vx} px a frame (default medium)
    The thrower always plays its whole animation (THE THROW'S END). Replaces throws.timing / slam_bounce /
    special_grab_timing for that throw (one path: a throw has events or timing, never both). hold_b = the paired hold + B
    throw (throws.b) or the grab special on hold + B (throws.extra.b); run = the run grab's special (throws.run.special),
    its frames from the special's first. -> {key: checked entry, its impacts as event_impacts lists them}"""
    ev = (r.get('throws') or {}).get('events') or {}
    tm = (r.get('throws') or {}).get('timing') or {}
    w0 = f"roster {r['name']}: throws.events"
    assert isinstance(ev, dict), f'{w0} = {{forward | back | hold_b | run: {{...}}}}'
    out = {}
    for k, e in ev.items():
        w = f'{w0}.{k}'
        assert k in EVENT_KEYS, f"{w}: one of {', '.join(EVENT_KEYS)}"
        assert k not in tm, f'{w}: and throws.timing.{k}: one path (events replace timing)'
        sp = event_special(r, k)
        if k == 'hold_b': assert (r.get('throws') or {}).get('b') or sp, f'{w}: no hold + B throw (throws.b / throws.extra.b)'
        if k == 'run': assert sp, f'{w}: no run grab (throws.run.special)'
        assert not sp or sp not in (r.get('special_grab_timing') or {}), f'{w}: and special_grab_timing.{sp}: one path (events replace it)'
        for f in e: assert f in ('impact', 'impacts', 'launch', 'held', 'from', 'about'), f'{w}: unknown field {f}'
        def fr(x, what): assert isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 400, f'{w}.{what}: a throw frame 1-400'
        imps = event_impacts(e, w)
        L = e.get('launch')
        assert isinstance(L, dict), f'{w}.launch: {{frame, dir, size?}}'
        for f in L: assert f in ('frame', 'dir', 'size'), f'{w}.launch: unknown field {f}'
        fr(L.get('frame'), 'launch.frame')
        assert L.get('dir') in EVENT_DIRS, f"{w}.launch.dir: one of {', '.join(EVENT_DIRS)}"
        assert L.get('size', 'medium') in EVENT_SIZES, f"{w}.launch.size: one of {', '.join(EVENT_SIZES)}"
        if 'held' in e:
            fr(e['held'], 'held')
            assert e['held'] <= L['frame'], f"{w}.held {e['held']}: not after its launch (frame {L['frame']})"
        assert imps[-1]['frame'] <= L['frame'], f"{w}: impact frame {imps[-1]['frame']} after its launch (frame {L['frame']})"
        out[k] = dict(e, impacts=imps)
        out[k].pop('impact', None)
    if ev and g is not None:
        tl = g.get('throw_launch')
        assert isinstance(tl, dict), 'game.json throw_launch {up | away: {small | medium | big: {vy, vx}}}: the launches the events name'
        for d in ('up', 'away'):
            for z in EVENT_SIZES:
                v = (tl.get(d) or {}).get(z)
                assert isinstance(v, dict) and isinstance(v.get('vy'), (int, float)) and isinstance(v.get('vx'), (int, float)), f'throw_launch.{d}.{z}: {{vy, vx}}'
    return out


def event_special(r, k):
    """the grab special an events key names for roster entry r (hold_b: throws.extra.b, run: throws.run.special), else None"""
    t = r.get('throws') or {}
    if k == 'hold_b' and not t.get('b'): return (t.get('extra') or {}).get('b')
    if k == 'run': return (t.get('run') or {}).get('special')
    return None


def event_rows(g, build):
    """THE THROW EVENTS -> (gthrow_ev rows [fighter][TM_*], gsg_ev rows [fighter][hold_b, run]) as C (gamedata.h gthrev_t
    {held, lch, dir, n, vy, vx, ifr[], ish[], ifl[]}, gsgev_t {ix, pad, e}); no events: n 0, ix 0xFF"""
    fl = json.load(open(os.path.join(build, 'chainlab.json')))['fighters']
    pools = {f['name']: [p['input'] for p in f['pool']] for f in fl}
    tl = g.get('throw_launch') or {}
    z3 = '{ ' + ', '.join(['0'] * EVENT_IMPS) + ' }'
    def ev(e):
        if not e: return '{ 0, 0, TE_NONE, 0, 0, 0, %s, %s, %s }' % (z3, z3, z3)
        L = e['launch']; d = L['dir']; I = e['impacts']
        v = (tl.get(LAUNCH_TABLE.get(d, d)) or {}).get(L.get('size', 'medium')) or {'vy': 0, 'vx': 0}
        pad = lambda xs: '{ ' + ', '.join(map(str, xs + [0] * (EVENT_IMPS - len(xs)))) + ' }'
        fx = [' | '.join(f'EVF_{f.upper()}' for f in IMPACT_FX if x[f]) or '0' for x in I]
        return '{ %d, %d, TE_%s, %d, %d, %d, %s, %s, %s }' % (e.get('held', L['frame']), L['frame'], d.upper(), len(I), round(v['vy'] * 256),
            round(v['vx'] * 256), pad([x['frame'] for x in I]), pad([x['damage'] for x in I]), pad(fx))
    tr, sr = [], []
    for r in g['roster']:
        E = throw_events(r, g)
        tr.append('{ ' + ', '.join(ev(None if event_special(r, k) else E.get(k)) for k in TIMING_KEYS) + f' }}   /* {r["name"]} */')
        cells = []
        for k in ('hold_b', 'run'):
            sp = event_special(r, k)
            if not sp or k not in E: cells.append('{ 0xFF, 0, ' + ev(None) + ' }'); continue
            assert sp in pools[r['name']], f"roster {r['name']}: throws.events.{k}: its special {sp} not in its pool"
            cells.append('{ %d, 0, %s }' % (pools[r['name']].index(sp), ev(E[k])))
        sr.append('{ ' + ', '.join(cells) + f' }}   /* {r["name"]} */')
    return tr, sr


def throw_timing(r, g=None):
    """roster[].throws.timing (note 20261016-045300-e03d round 2, Bruno: "throws should be case by case"; written by
    tools/brawler/throw_answers.py from the throw review, review.html?q=throws): per throw {kind impact | slam, damage_row,
    eject_row?, glue_row?, about?, from?} in its script's rows -> [(dmg, hand, kind)] by TM_* (gamedata.h gthrtm_t). dmg = damage_row;
    hand = an IMPACT's eject_row (default its damage_row), not before its glue_row; a SLAM: its glue_row, else none (the
    throw_handoff rule). No entry: 0xFFFF both (the 0.10.129 rule: fighter.c slam_row). A SLAM also gets its ground
    bounce (bvy, bvx: slam_bounce below, note 20261016-095622-e03d; 0 0 none)"""
    tm = (r.get('throws') or {}).get('timing') or {}
    assert isinstance(tm, dict), f"roster {r['name']}: throws.timing = {{forward | back | hold_b: {{...}}}}"
    for k in tm: assert k in TIMING_KEYS, f"roster {r['name']}: throws.timing.{k}: one of {', '.join(TIMING_KEYS)}"
    out = []
    for k in TIMING_KEYS:
        e = tm.get(k)
        if not e: out.append(('0xFFFF', '0xFFFF', 'TK_NONE', 0, 0)); continue
        w = f"roster {r['name']}: throws.timing.{k}"
        for f in e: assert f in ('kind', 'damage_row', 'eject_row', 'glue_row', 'bounce', 'about', 'from'), f'{w}: unknown field {f}'
        assert e.get('kind') in TIMING_KINDS, f"{w}.kind: one of {', '.join(TIMING_KINDS)}"
        for f in ('damage_row', 'eject_row', 'glue_row'):
            assert f not in e or (isinstance(e[f], int) and 0 <= e[f] < 0xFFFF), f'{w}.{f}: a script row'
        assert 'damage_row' in e, f'{w}.damage_row: the row its damage lands on'
        assert e['kind'] == 'impact' or 'eject_row' not in e, f'{w}: eject_row is an IMPACT throw\'s'
        hand = max(e.get('eject_row', e['damage_row']), e.get('glue_row', 0)) if e['kind'] == 'impact' else e.get('glue_row', 0xFFFF)
        assert e['kind'] == 'slam' or 'bounce' not in e, f'{w}: bounce is a SLAM throw\'s'
        bv = slam_bounce(e, (g or {}).get('slam_bounce'), w) if e['kind'] == 'slam' else (0, 0)
        out.append((str(e['damage_row']), '0xFFFF' if hand == 0xFFFF else str(hand), 'TK_' + e['kind'].upper()) + bv)
    return out


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
            elif k != 'super_throw': v[len(pool) + j] = round((fs if k == 'fury' else ms) * 256)   # not measured (note
                                                         # 20261015-144500-e03d, Haggar): its own damage times the scale
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


RULE_KEYS = ('about', 'attackers', 'approach_max', 'ready', 'windup', 'rank', 'group', 'variety', 'one_special', 'one_special_about')

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
    for k in rk: assert k in ('about', 'easing_about', 'start', 'max', 'death', 'fast', 'clean', 'fast_clear', 'every', 'wait', 'rest', 'damage'), f'ai.rules.rank: unknown field {k}'
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
    gp, vr = r.get('group') or {}, r.get('variety') or {}   # the group's lanes / spacing, the knockdown's variety (note
    for k in gp: assert k in ('about', 'lane_dz', 'lane_near', 'spacing_dx', 'spacing_dz'), f'ai.rules.group: unknown field {k}'   # 20261017-013009-e03d)
    for k in vr: assert k in ('about', 'knockdown_dz', 'getup_frames'), f'ai.rules.variety: unknown field {k}'
    for k, v in list(gp.items()) + list(vr.items()):
        if k != 'about': assert isinstance(v, int) and 0 <= v <= (64 if k in ('lane_dz', 'knockdown_dz') else 120), f'ai.rules.group / variety.{k}: {v}'
    a2, s2 = pose(rd['fallback'], 'ai.rules.ready.fallback')
    out = [f"const gairules_t gai = {{ .attackers = {r['attackers']}, .approach_max = {r['approach_max']}, .pulse = {rd['pulse']}, "
           f".ready_anim2 = {a2}, .ready_step2 = {s2}, .light_lo = {wu['light'][0]}, .light_hi = {wu['light'][1]}, "
           f".heavy_lo = {wu['heavy'][0]}, .heavy_hi = {wu['heavy'][1]}, .heavy_from = {wu['heavy_from']}, "
           f".spec_lo = {wu['special_hold'][0]}, .spec_hi = {wu['special_hold'][1]}, .rank_start = {rk['start']}, .rank_max = {rk['max']}, "
           f".rank_death = {rk['death']}, .rank_fast = {rk['fast']}, .rank_clean = {rk['clean']}, .rank_wait = {rk['wait']}, "
           f".rank_rest = {rk['rest']}, .rank_dmg = {rk['damage']}, .rank_every = {rk['every']}, .fast_clear = {rk['fast_clear']}, "
           f".wait = {{ {', '.join(map(str, wait))} }}, "
           f".lane_dz = {gp.get('lane_dz', 0)}, .lane_near = {gp.get('lane_near', 0)}, .sep_dx = {gp.get('spacing_dx', 0)}, .sep_dz = {gp.get('spacing_dz', 0)}, "
           f".kd_dz = {vr.get('knockdown_dz', 0)}, .down_var = {vr.get('getup_frames', 0)}, .one_special = {1 if r.get('one_special') else 0} }};"]
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
BONUS_KEYS = ('about', 'after', 'intro', 'pick', 'card', 'fury_lock', 'over_music', 'win_music', 'games', 'games_benched', 'after_about')
MAXC_N = 6                                               # roster[].max_chain: at most this many throws
BONUS_GAME_KEYS = {'gauge': ('id', 'name', 'kind', 'scene', 'slot', 'voice', 'music', 'seconds', 'step', 'grades', 'grades_about', 'chunks', 'pass_reward', 'win_grade', 'fall_sounds', 'blows', 'charge', 'punch_sound', 'fail_sounds', 'fail_result', 'show_name'),
                   'break': ('id', 'name', 'kind', 'scene', 'slot', 'voice', 'music', 'seconds', 'seconds_about', 'count', 'breaks_with', 'unlock', 'hp', 'lesson', 'won_text', 'won_ticks', 'show_name', 'won_by', 'bonus_about', 'damage_at', 'layout', 'pile')}
BONUS_BLOWS = {'jab': 'JAB', 'finisher': 'FIN', 'forward': 'FWD'}   # a gauge game's blows: fighter.h BL_* (fighter_blow)
GB_FALL_SND = 6                                         # gamedata.h GB_FALL_SND: a gauge game's fall_sounds
GB_FAIL_SND = 16                                        # gamedata.h GB_FAIL_SND: its fail_sounds ('VOICE HIT': GB_VOICE_HIT)
GB_TRUNKS = 8                                           # gamedata.h GB_TRUNKS: a break game's pile (4 sprites a trunk)
PILE_KEYS = ('about', 'spacing_about', 'lift', 'lift_about', 'trunk_h', 'reach', 'hp', 'damage_at', 'trunks')
TRUNK_W = 48                                            # main.c BN_SOLID_W: a post's wood (x + 8 .. + 56 of its 64 px)
GB_PASS_N = 4                                          # gamedata.h GB_PASS_N: a gauge game's pass_reward.chunks (clears)
REF_LINE = 20                                            # the referee's window: letters a line (main.c "the referee", REF_TXT_MID: 6 px to its border; 13 columns, referee_ss2.py WIN_EXTRA)
REF_KEYS = ('about', 'delay', 'delay_about', 'mark', 'from', 'hold', 'hit_text', 'fury_dx', 'fighter', 'life', 'hit_about', 'jump_sound', 'land_sound', 'sound_about')
POST_DMG = 3                                             # make_bonus.py post: AOF2's intact post + its 3 cracked pictures
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
    for k in p: assert k in ('seconds', 'music', 'won', 'won_about'), f'bonus.pick: unknown field {k}'
    assert p.get('won', 'offered') in ('offered', 'greyed'), "bonus.pick.won: offered | greyed (a game won at an earlier stop)"
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
            pr = x.get('pass_reward')                    # (notes 20261016-133045 / -135212-e03d: the pass's chunks per clear,
            if pr is not None:                           #  its big headline per chunks added)
                for k in pr: assert k in ('about', 'chunks', 'text'), f"bonus game {x['id']}: pass_reward: unknown field {k}"
                assert 1 <= len(pr['chunks']) <= GB_PASS_N and all(isinstance(v, int) and 0 <= v <= 4 for v in pr['chunks']), \
                    f"bonus game {x['id']}: pass_reward.chunks: 1-{GB_PASS_N} values 0-4 (the n-th clear's chunks)"
                assert len(pr['text']) == max(pr['chunks']) + 1 and all(isinstance(t, str) and t for t in pr['text']), \
                    f"bonus game {x['id']}: pass_reward.text: one line per chunks added 0..{max(pr['chunks'])}"
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
            da = x.get('damage_at', [])
            assert isinstance(da, list) and len(da) <= POST_DMG and all(isinstance(v, int) and 1 <= v < x.get('hp', 1) for v in da) and da == sorted(set(da)), \
                f"bonus game {x['id']}: damage_at: up to {POST_DMG} rising hit counts 1..hp-1 (the post's cracked pictures 1-{POST_DMG})"
            assert x.get('layout', 'drop') in ('drop', 'pile'), f"bonus game {x['id']}: layout drop | pile"
            if x.get('layout') == 'pile':                 # (note 20261017-063200-e03d: a pile held up by the trunks under it)
                pl = x.get('pile') or {}
                for k in pl: assert k in PILE_KEYS, f"bonus game {x['id']}: pile: unknown field {k}"
                tr, th, php = pl.get('trunks') or [], pl.get('trunk_h', 64), pl.get('hp', x.get('hp', 1))
                assert isinstance(th, int) and 32 <= th <= 128 and th % 2 == 0, f"bonus game {x['id']}: pile.trunk_h 32-128, even (SCB2's shrink th * 2 - 1)"
                assert isinstance(php, int) and 1 <= php <= 30, f"bonus game {x['id']}: pile.hp 1-30"
                assert isinstance(pl.get('reach', 32), int) and 0 <= pl.get('reach', 32) <= 96, f"bonus game {x['id']}: pile.reach 0-96 px"
                pda = pl.get('damage_at', [])
                assert isinstance(pda, list) and len(pda) <= POST_DMG and all(isinstance(v, int) and 1 <= v < php for v in pda) and pda == sorted(set(pda)), \
                    f"bonus game {x['id']}: pile.damage_at: up to {POST_DMG} rising hit counts 1..hp-1"
                assert 1 <= len(tr) <= GB_TRUNKS and all(isinstance(t, list) and len(t) == 2 and isinstance(t[0], int) and isinstance(t[1], int)
                                                         and -8 <= t[0] <= 264 and 0 <= t[1] <= 3 for t in tr), \
                    f"bonus game {x['id']}: pile.trunks: 1-{GB_TRUNKS} [x -8..264 (the post's left edge on screen), layer 0-3]"
                lift = pl.get('lift', 0)
                assert isinstance(lift, int) and 0 <= lift <= 64, f"bonus game {x['id']}: pile.lift 0-64 px"
                assert 224 - lift - (max(t[1] for t in tr) + 1) * th >= -272, \
                    f"bonus game {x['id']}: pile: its top layer over y -272 (note 20261017-121458-e03d: over the screen's top is fine, the 9-bit sprite Y (496 - y) would wrap it onto the screen's bottom lines at 224 - 512)"
                for i, (tx, tl) in enumerate(tr):
                    assert all(abs(tx - ux) >= TRUNK_W for j, (ux, ul) in enumerate(tr) if j != i and ul == tl), \
                        f"bonus game {x['id']}: pile.trunks[{i}]: overlaps another trunk of layer {tl} (x {TRUNK_W} px apart at least)"
                    assert tl == 0 or any(ul == tl - 1 and abs(tx - ux) < TRUNK_W for ux, ul in tr), \
                        f"bonus game {x['id']}: pile.trunks[{i}]: nothing under it in layer {tl - 1} (it rests on a trunk less than {TRUNK_W} px across)"
            assert isinstance(x.get('won_ticks', 300), int) and 120 <= x.get('won_ticks', 300) <= 1200, f"bonus game {x['id']}: won_ticks 120-1200"
            for k in ('lesson', 'won_text'):
                t = x.get(k, [])
                assert isinstance(t, list) and len(t) <= 3 and all(isinstance(l, str) and len(l) <= 38 and all(0x20 <= ord(ch) < 0x7F for ch in l) for l in t), \
                    f"bonus game {x['id']}: {k}: up to 3 lines, ASCII, 38 characters each"
            assert x.get('won_by', 'box') in ('box', 'referee'), f"bonus game {x['id']}: won_by box | referee"
            if x.get('won_by') == 'referee':                 # (his window: 13 tiles, REF_LINE letters)
                assert x.get('won_text') and all(len(l) <= REF_LINE for l in x['won_text']), \
                    f"bonus game {x['id']}: won_by referee: won_text = his 1-3 lines, {REF_LINE} characters each"
        assert isinstance(x.get('show_name', True), bool), f"bonus game {x['id']}: show_name true | false"
    assert not b.get('fury_lock') or any(x.get('unlock') == 'fury' for x in gs) and b['after'], \
        'bonus.fury_lock: no game unlocks the fury (it would stay locked)'
    return b


def bonus_tables(g, songs_known, sfx_names):
    """game.json "bonus" -> gbonus (gamedata.h gbonus_t, main.c "bonus stages"); sfx_names: songs.json sfx name -> code"""
    b = bonus_check(g, songs_known, sfx_names)
    # (a game with unlock fury alone is fine: the fury free (the select cheat), nothing to pick, main.c stage_next skips
    #  the bonus: bonus_open; Bruno 2026-10-17, the posts alone after stage 1)
    code = lambda v: sfx_names[v.upper()] if v else 0
    c = ['static const uint8_t gbonus_after[GS_COUNT] = { ' + ', '.join('1' if s + 1 in b['after'] else '0' for s in range(len(g['stages']))) + ' };   /* bonus.after */']
    rows = []
    for x in b['games']:
        f = [f".name = {c_str(x['name'])}", f".kind = {BONUS_KINDS[x['kind']]}", f".scene = {BONUS_SCENES.index(x['scene'])}",
             f".music = MUS_{x['music']}", f".seconds = {x['seconds']}", f".slot = {x['slot']}", f".voice = 0x{code(x.get('voice')):02X}"]
        if x['kind'] == 'gauge':
            f += [f".step = {x['step']}", '.grades = { ' + ', '.join(map(str, x['grades'])) + ' }', '.chunks = { ' + ', '.join(map(str, x['chunks'])) + ' }',
                  f".win_grade = {x.get('win_grade', 5)}",
                  f".pass_n = {len((x.get('pass_reward') or {}).get('chunks', []))}",
                  '.pass_chunks = { ' + (', '.join(map(str, (x.get('pass_reward') or {}).get('chunks', []))) or '0') + ' }',
                  '.pass_text = { ' + (', '.join(c_str(t) for t in (x.get('pass_reward') or {}).get('text', [])) or '0') + ' }',
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
                  f".hp = {x.get('hp', 1)}", '.dmg_at = { ' + ', '.join(str(v) for v in (x.get('damage_at', []) + [255] * POST_DMG)[:POST_DMG]) + ' }', f".won_ticks = {x.get('won_ticks', 300)}",
                  '.lesson = ' + ln('lesson', ['ONLY YOUR FURY BREAKS THE POSTS!', 'FURY  =  D', 'MAX  =  DOWN + D  AT LOW LIFE']),
                  '.won_text = ' + ln('won_text', ['FURY + FURY MAX UNLOCKED ON D']), f".referee = {1 if x.get('won_by') == 'referee' else 0}"]
            if x.get('layout') == 'pile':                # (the pile's own count / hp / damage: the drop's kept for a compare)
                pl = x['pile']; tr = pl['trunks']; php = pl.get('hp', x.get('hp', 1))
                f = [v for v in f if not v.startswith(('.count =', '.hp =', '.dmg_at ='))]
                f += [f".count = {len(tr)}", f".hp = {php}", '.dmg_at = { ' + ', '.join(str(v) for v in (pl.get('damage_at', []) + [255] * POST_DMG)[:POST_DMG]) + ' }',
                      '.layout = BL_PILE', f".trunk_h = {pl.get('trunk_h', 64)}", f".trunk_reach = {pl.get('reach', 32)}", f".trunk_lift = {pl.get('lift', 0)}",
                      '.trunk_x = { ' + ', '.join(str(t[0]) for t in tr) + ' }', '.trunk_layer = { ' + ', '.join(str(t[1]) for t in tr) + ' }']
        f.append(f".show_name = {1 if x.get('show_name', True) else 0}")
        rows.append('{ ' + ', '.join(f) + ' }')
    c.append(f"const gbonus_t gbonus = {{ .ngames = {len(b['games']) if b['after'] else 0}, .pick_seconds = {b['pick']['seconds']}, "
             f".pick_music = MUS_{b['pick']['music']}, .over_music = MUS_{b.get('over_music', b['pick']['music'])}, "
             f".win_music = MUS_{b.get('win_music', b.get('over_music', b['pick']['music']))}, "
             f".fury_lock = {1 if b.get('fury_lock') and b['after'] else 0}, .after = gbonus_after, .pick_won = {1 if b['pick'].get('won') == 'greyed' else 0}, "
             f".intro_music = MUS_{b.get('intro', {}).get('music', b['pick']['music'])}, .intro_voice = 0x{code(b.get('intro', {}).get('voice')):02X}, "
             f".intro_at = {b.get('intro', {}).get('at', 0)}, .intro_ticks = {b.get('intro', {}).get('ticks', 122)}, "
             f".card_ticks = {b.get('card', {}).get('ticks', 186)}, .card_sound = 0x{code(b.get('card', {}).get('sound')):02X}, "
             f".games = {{ {', '.join(rows)} }} }};")
    r = g.get('referee') or {}
    for k in r: assert k in REF_KEYS, f'referee: unknown field {k}'
    rv = {'delay': 0, 'mark': 96, 'from': 48, 'hold': 124, 'fury_dx': 56, 'life': 999,
          **{k: v for k, v in r.items() if k not in ('about', 'delay_about', 'hit_about', 'hit_text', 'fighter', 'jump_sound', 'land_sound', 'sound_about')}}
    assert all(isinstance(v, int) and not isinstance(v, bool) for v in rv.values()), 'referee: delay / mark / from / hold / fury_dx / life: integers'
    ht = r.get('hit_text', [])
    assert isinstance(ht, list) and len(ht) <= 3 and all(isinstance(l, str) and 0 < len(l) <= REF_LINE and all(0x20 <= ord(ch) < 0x7F for ch in l) for l in ht), \
        f'referee: hit_text = his 1-3 lines after the fury hits him ([]: no D quirk), {REF_LINE} characters each'
    body = r.get('fighter')                              # the D quirk's victim: a roster fighter (note 20261016-045652-e03d)
    assert not ht or body in roster_names(g), f'referee: fighter = the roster fighter the fury hits (the D quirk: hit_text), got {body!r}'
    assert 24 <= rv['fury_dx'] <= 160 and 200 <= rv['life'] <= 30000, \
        "referee: fury_dx 24-160 px, life 200-30000 (never KO'd by a fury)"
    assert 40 <= rv['mark'] <= 160 and 32 <= rv['from'] <= 120 and 30 <= rv['hold'] <= 1200, \
        'referee: mark 40-160 px from his edge, from 32-120 px outside it, hold 30-1200 ticks'
    assert 0 <= rv['delay'] <= 600, 'referee: delay 0-600 ticks before he starts walking in'
    c.append('static const char *const gref_hit_text[3] = { ' + ', '.join(c_str(l) for l in (ht + ['', '', ''])[:3]) + ' };')
    c.append(f"const gref_t gref = {{ .mark = {rv['mark']}, .from = {rv['from']}, .hold = {rv['hold']}, .fury_dx = {rv['fury_dx']}, "
             f".fighter = {'BC_' + body.upper() if ht else 0}, .life = {rv['life']}, "
             f".hit = {1 if ht else 0}, .hit_text = gref_hit_text, .delay = {rv['delay']}, "
             f".jump_sound = 0x{code(r.get('jump_sound')):02X}, .land_sound = 0x{code(r.get('land_sound')):02X} }};   /* game.json referee */")
    return c


MAP_DISTRICTS = ('SLUM', 'PARK', 'WEST SIDE', 'INDUSTRIAL AREA', 'BAY AREA', 'UP TOWN')   # make_map.DISTRICTS
GM_STOPS = 6                                             # gamedata.h GM_STOPS
MAP_KEYS = ('about', 'x', 'y', 'start_ticks', 'clear_ticks', 'clear_at', 'clear_at_about', 'clear_text_at', 'clear_text_at_about', 'skip_after', 'blink', 'start_text', 'clear_text',
            'final_clear_text', 'clear_text_about', 'stops_about', 'colours_about', 'start_text_about')
# (next_text / next_bonus / final_text, the line under the clear's map: gone, note 20261017-150757-e03d)


def map_stops(g):
    """the map's stops = the campaign's stages in play, in order (note 20261017-114940-e03d: 'only the levels of the
    campaign'), each from its stages[].map {name, district, label}; g['stages'] already the campaign (load)"""
    return [s.get('map') for s in g['stages']]


def map_tables(g):
    """game.json "map" (main.c "the map", tools/brawler/make_map.py the picture) -> gmap + the stop of each stage / bonus"""
    m = g.get('map')
    n = len(g['stages']); bo = g.get('bonus') or {}; after = bo.get('after', []) if bo.get('games') else []
    if not m:
        return ['#define GMAP_ON 0'], ['const gmap_t gmap = { 0 };']
    for k in m: assert k in MAP_KEYS, f'map: unknown field {k}'
    ok = lambda s, k: isinstance(s, str) and len(s) <= k and all(0x20 <= ord(ch) < 0x7F for ch in s)
    for k in ('start_text', 'clear_text', 'final_clear_text'):
        assert ok(m.get(k, ''), 38), f'map.{k}: ASCII, 38 characters at most'
    assert isinstance(m['x'], int) and isinstance(m['y'], int) and m['x'] % 8 == 0 and m['y'] % 8 == 0 and 0 <= m['x'] <= 64 and 16 <= m['y'] <= 120, \
        'map.x / y: the top left in 8 px steps (x 0-64: the 256 px map on the 320 px screen; y 16-120)'
    for k in ('start_ticks', 'clear_ticks'): assert isinstance(m[k], int) and 0 <= m[k] <= 900, f'map.{k}: 0-900 ticks (0: not shown then)'
    assert isinstance(m.get('clear_at', 0), int) and 0 <= m.get('clear_at', 0) <= 600, 'map.clear_at: 0-600 ticks'
    assert isinstance(m.get('clear_text_at', 0), int) and 0 <= m.get('clear_text_at', 0) < m['clear_ticks'] or not m['clear_ticks'], \
        'map.clear_text_at: 0 .. clear_ticks - 1 ticks (the headline inside the map\'s time)'
    assert isinstance(m.get('skip_after', 30), int) and 0 <= m.get('skip_after', 30) <= 600 and 2 <= m.get('blink', 6) <= 60, 'map: skip_after 0-600, blink 2-60'
    assert 'stops' not in m, 'map.stops: gone (note 20261017-114940-e03d): each stage in play carries its stop (stages[].map)'
    st = map_stops(g)
    assert 1 <= len(st) <= GM_STOPS, f'map: 1-{GM_STOPS} stages in play (a stop each)'
    for k, s in enumerate(st):
        assert isinstance(s, dict), f'stage {k + 1} (in play): no map stop (stages[].map {{name, district, label}})'
        for f in s: assert f in ('name', 'district', 'label'), f'stage {k + 1}: map: unknown field {f}'
        assert re.fullmatch(r"[A-Z0-9 .!'-]{1,14}", s['name']), f'stage {k + 1}: map.name 1-14 characters A-Z 0-9 space . ! \' -'
        assert s['district'] in MAP_DISTRICTS, f'map stop {s["name"]}: district {s["district"]!r} ({" | ".join(MAP_DISTRICTS)})'
        lc, lr = s['label']
        assert 0 <= lc and lc + len(s['name']) <= 32 and 0 <= lr <= 10, f'map stop {s["name"]}: label [column, row] inside the 32 x 11 cell map'
    rows = ', '.join(f'{{ {c_str(s["name"])}, {s["label"][0]}, {s["label"][1]} }}' for s in st)
    c = [f'const gmap_t gmap = {{ .x = {m["x"]}, .y = {m["y"]}, .start_ticks = {m["start_ticks"]}, .clear_ticks = {m["clear_ticks"]}, '
         f'.skip_after = {m.get("skip_after", 30)}, .clear_at = {m.get("clear_at", 0)}, .clear_text_at = {m.get("clear_text_at", 0)}, .blink = {m.get("blink", 6)}, .nstops = {len(st)}, '
         f'.start_text = {c_str(m.get("start_text", ""))}, .clear_text = {c_str(m.get("clear_text", ""))}, '
         f'.final_clear_text = {c_str(m.get("final_clear_text", ""))}, .stops = {{ {rows} }} }};   /* game.json map; stop k = stage k in play */']
    return ['#define GMAP_ON 1'], c


CHEAT_KEYS = ('UP', 'DOWN', 'LEFT', 'RIGHT', 'A', 'B', 'C', 'D')   # neo_input.h JOY_* (cheats.stage_clear_keys)


def cheat_tables(g):
    """game.json "cheats" (Bruno's test cheats: main.c select_tick, stage_cheat) + the select's locked rung texts"""
    ch = g.get('cheats') or {}
    for k in ch: assert k in ('about', 'hold', 'stage_clear_hold', 'stage_clear_keys', 'stage_clear_keys_about'), f'cheats: unknown field {k}'
    assert 30 <= ch.get('hold', 120) <= 600 and 30 <= ch.get('stage_clear_hold', 180) <= 600, 'cheats: hold / stage_clear_hold 30-600 ticks'
    keys = ch.get('stage_clear_keys', ['DOWN', 'A', 'B', 'C', 'D'])     # (note 20261017-131927-e03d: DOWN + A + D, the
    assert keys and len(set(keys)) == len(keys) and set(keys) <= set(CHEAT_KEYS) and set(keys) & {'A', 'B', 'C', 'D'}, \
        f'cheats.stage_clear_keys {keys}: distinct names of {" ".join(CHEAT_KEYS)}, at least one button'   # touchscreen's reach)
    U = g.get('unlocks') or {}
    return [f'#define CHEAT_HOLD {ch.get("hold", 120)}   /* cheats.hold: each of a select cheat\'s two holds, ticks */',
            f'#define CHEAT_STAGE_HOLD {ch.get("stage_clear_hold", 180)}   /* cheats.stage_clear_hold */',
            '#define CHEAT_STAGE_KEYS (' + ' | '.join('JOY_' + k for k in keys) + ')   /* cheats.stage_clear_keys: held together */',
            f'#define UNL_SHOW_NEXT {1 if U.get("show_next") else 0}   /* unlocks.show_next: the next rung as silhouettes on the select */',
            f'#define UNL_LOCKED_NAME {c_str(U.get("locked_name", ""))}',
            f'#define UNL_LOCKED_LINES {len(U.get("locked_text", []))}   /* unlocks.locked_text: lines over a highlighted silhouette */',
            '#define UNL_LOCKED_TEXT { ' + ', '.join(c_str(t) for t in U.get('locked_text', [])) + (' ' if U.get('locked_text') else '0 ') + '}']


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
    'stage_clear': None,                       # won_text[0], a gauge game's pass_reward.text; the stage clear's: map.clear_text /
                                               # final_clear_text, STAGE CLEAR without them: main.c clear_head), else the default here, a
    'game_over': 'GAME OVER',                  # use's "text" over it
    'time_over': 'TIME OVER',
    'bonus_won': None,
    'ladder': 'NEW CHALLENGERS!',              # the unlock ladder screen after a game clear that unlocked a rung
    'bonus_meter': None,                       # a gauge game's pass: the chunks it gave (note 20261016-135212-e03d)
    'max_cancel': 'MAX CANCEL',                # the fury -> MAX cancel's freeze (game.json max_cancel, note 20261016-133443-e03d)
    'map_start': None,                         # the map's start_text (STAGE {n}) at a stage's start (note 20261017-114940-e03d)
}
BIG_KEYS = ('y', 'pitch', 'text', 'exit', 'still')


def clear_head(g, k):
    """stage k's clear headline (main.c clear_head; notes 20261017-131927-e03d reopened / 20261017-150757-e03d): the last
    stage map.final_clear_text, else map.clear_text with {n} = k + 1; neither: STAGE CLEAR"""
    m = g.get('map') or {}
    t = (m.get('final_clear_text') if k + 1 >= len(g['stages']) else '') or m.get('clear_text', '')
    return t.replace('{n}', str(k + 1)) or 'STAGE CLEAR'
BIG_CYCLE = {'shown': 0, 'hidden': 1, 'white': 2}   # main.c BT_SHOWN / BT_HIDDEN / BT_WHITE
BIG_CYC_N = 6                                  # gamedata.h GBIG_CYC


def big_tables(g):
    """game.json big_text (Bruno 2026-10-14, Savage Reign's letters: tools/brawler/make_bigfont.py) -> gbig[BIG_USES]: per
    screen whether its headline is drawn in the big font (a use listed) and where (y, line pitch), whether it leaves after
    the standard animation (exit) or plays none (still); a use not listed keeps the fix layer's line. big_text.headline ->
    gbig_anim: the one animation every big message plays (note 20261016-133635-e03d: slide in, blink, hold, slide out).
    Every text a use can draw is checked against the font's characters."""
    from make_bigfont import CHARS, SPACE, font
    adv = {c: a.shape[1] for c, (a, _) in font().items()}; adv[' '] = SPACE
    B = {k: v for k, v in (g.get('big_text') or {}).items() if k not in ('about', 'headline')}
    for k, v in B.items():
        assert k in BIG_USES, f'big_text: unknown use {k} ({", ".join(BIG_USES)})'
        for f in v: assert f in BIG_KEYS, f'big_text.{k}: unknown field {f} ({", ".join(BIG_KEYS)})'
        assert 'text' not in v or BIG_USES[k], f'big_text.{k}: its text is the screen\'s own (no "text")'
        assert isinstance(v.get('exit', True), bool) and isinstance(v.get('still', False), bool), f'big_text.{k}: exit / still: true | false'
    hl = (g.get('big_text') or {}).get('headline') or {}
    for k in hl: assert k in ('about', 'slide_in', 'blink', 'blink_cycle', 'hold', 'slide_out'), f'big_text.headline: unknown field {k}'
    an = {k: hl.get(k, d) for k, d in (('slide_in', 16), ('blink', 0), ('hold', 120), ('slide_out', 16))}
    for k, x in an.items(): assert isinstance(x, int) and 0 <= x <= 600, f'big_text.headline.{k} {x!r}: 0-600 ticks'
    cyc = hl.get('blink_cycle', ['shown', 'hidden'])
    assert 1 <= len(cyc) <= BIG_CYC_N and all(c in BIG_CYCLE for c in cyc), \
        f"big_text.headline.blink_cycle: 1-{BIG_CYC_N} of {' | '.join(BIG_CYCLE)}"
    gauge = [x for x in (g.get('bonus') or {}).get('games', []) if x.get('pass_reward')]
    texts = {'stage_intro': [intro_of(g, si)['title'] for si in range(len(g['stages']))],
             'bonus_won': [b['won_text'][0] for b in (g.get('bonus') or {}).get('games', []) if b.get('won_text')],
             'bonus_meter': [t for x in gauge for t in x['pass_reward']['text']],
             'map_start': [(g.get('map') or {}).get('start_text', '').replace('{n}', str(k + 1)) for k in range(len(g['stages']))],
             'stage_clear': [clear_head(g, k) for k in range(len(g['stages']))]}
    assert not gauge or 'bonus_meter' in B, 'big_text.bonus_meter: a gauge game with pass_reward draws its result in the big font'
    assert not (g.get('max_cancel') or {}).get('on', True) or not g.get('max_cancel') or 'max_cancel' in B, 'big_text.max_cancel: the MAX cancel draws its text in the big font'
    rows = []
    for k, dflt in BIG_USES.items():
        v = B.get(k)
        if v is None: rows.append(f'    {{ 0, 0, 0, 0, 0, 0 }},   /* {k}: the fix layer */'); continue
        y, pi = v.get('y', 80), v.get('pitch', 44)
        for f, x, lo, hi in (('y', y, 0, 176), ('pitch', pi, 32, 64)):
            assert isinstance(x, int) and lo <= x <= hi, f'big_text.{k}.{f} {x!r}: {lo}-{hi}'
        t = v.get('text', dflt)
        for s in ([t] if dflt else texts[k]):
            bad = sorted({c for c in s.upper() if c not in CHARS})
            assert s and not bad, f'big_text.{k}: {s!r}: the big font has no {"".join(bad)!r} (it draws {CHARS!r})'
            words = [w for w in re.split(r' {2,}', s.upper().strip())]
            for w in (words if sum(adv[c] for c in s.upper().strip()) > 304 else [s.upper().strip()]):
                assert sum(adv[c] for c in w) <= 304, f'big_text.{k}: {w!r} is wider than 304 px (two lines at most: they break at a double space)'
            assert len(words) <= 2, f'big_text.{k}: {s!r}: two lines at most'
        rows.append(f'    {{ {c_str(t) if dflt else 0}, {y}, {pi}, 1, {1 if v.get("exit", True) else 0}, {1 if v.get("still", False) else 0} }},   /* {k} */')
    h = ['typedef struct {                  /* a screen\'s headline in the big font (game.json big_text; main.c "big text") */',
         '    const char *text;             /* 0 = the screen\'s own text */',
         '    int16_t y;                    /* the glyphs\' top on screen (48 px cells) */',
         '    uint8_t pitch;                /* px between two lines */',
         '    uint8_t on;                   /* 0: this screen keeps the fix layer\'s line */',
         '    uint8_t exit, still;          /* exit 0: it stays after the headline\'s hold; still 1: no animation (shown in place) */',
         '} gbig_t;',
         f'#define GBIG_CYC {BIG_CYC_N}',
         'typedef struct {                  /* big_text.headline: the one animation of every big message (note 20261016-133635-e03d) */',
         '    uint16_t slide_in, blink, hold, slide_out;   /* ticks: in from the right, blinking, held, out to the left */',
         '    uint8_t ncyc, cyc[GBIG_CYC];  /* the blink\'s frames, repeated: BT_SHOWN / BT_HIDDEN / BT_WHITE */',
         '} gbig_anim_t;',
         'enum { ' + ', '.join(f'BIG_{k.upper()}' for k in BIG_USES) + ', BIG_USES };',
         'extern const gbig_t gbig[BIG_USES];',
         'extern const gbig_anim_t gbig_anim;']
    return h, ['const gbig_t gbig[BIG_USES] = {', '\n'.join(rows), '};',
               f"const gbig_anim_t gbig_anim = {{ {an['slide_in']}, {an['blink']}, {an['hold']}, {an['slide_out']}, {len(cyc)}, "
               f"{{ {', '.join(str(BIG_CYCLE[c]) for c in cyc)} }} }};"]


def tables(g, build):
    M = model(g, build)
    presets = M['presets']
    h = ['/* Generated by tools/brawler/build_tables.py from examples/brawler/game.json. Do not edit. */',
         '#ifndef GAME_TABLES_H\n#define GAME_TABLES_H\n#include "bm_chars.h"\n#include "gamedata.h"\n#include "snd/songs.h"',
         f'#define GS_COUNT {len(g["stages"])}            /* campaign stages */',
         f'#define GM_MAX_CHUNKS {g["meter"].get("max_chunks", 4)}       /* meter.max_chunks: the drive bar\'s most chunks */',
         f'#define EN_COUNT {len(M["enemies"])}', f'#define AI_COUNT {len(M["ai"])}            /* the presets, then the enemies\' own rows */',
         f'#define TINT_COUNT {len(M["tints"])}',
         f'#define SEL_NSLOT {len(select_layout(g))}',
         f'#define SEL_NLAY {len(select_layers(g, None, build))}             /* the select screen\'s layouts: one per unlocked count (select_layers; the ladder: rungs + 1) */',
         f'#define SEL_NPLACE {sum(e[0] for e in select_layers(g, None, build))}             /* their places, back to back (SEL_SLOT) */',
         f'#define SEL_NPAL {sel_palbases(g, build)[1]}             /* the select screen\'s actors\' palettes from 16 (sel_palbase) */',
         f'#define GAME_MUS_TITLE MUS_{g["music"].get("title", g["music"]["select"])}',
         f'#define GAME_MUS_SELECT MUS_{g["music"]["select"]}', f'#define GAME_MUS_CLEAR MUS_{g["music"]["clear"]}', f'#define GAME_MUS_CLEAR_FRAMES {int(g["music"].get("clear_frames", 0))}   /* the clear song\'s length: PH_CLEAR\'s next screen waits for it */',
         f'#define GAME_CREDIT_START_TICKS {int(round(float((g.get("credit") or {}).get("start_timeout_s", 0)) * 60))}   /* game.json credit.start_timeout_s: the title after a credit starts the game by itself (0 = never; main.c title_tick) */',
         f'#define GAME_CREDIT_START_SHOWN {1 if (g.get("credit") or {}).get("shown", True) else 0}   /* credit.shown: the seconds counting down beside PRESS START */',
         f'#define GAME_CREDIT_MVS_ONLY {1 if (g.get("credit") or {}).get("mvs_only", True) else 0}',
         f'#define GAME_SEL_TIME_TICKS {int(round(float(g["select"].get("time_limit_s", 0)) * 60))}   /* game.json select.time_limit_s: the select picks for the players by itself (0 = never; main.c select_tick) */',
         f'#define GAME_SEL_TIME_SHOWN {1 if g["select"].get("time_limit_shown") else 0}   /* select.time_limit_shown (not drawn yet: no timer font) */',
         f'#define GAME_SEL_TIME_MVS_ONLY {1 if g["select"].get("time_limit_mvs_only", True) else 0}',
         f'#define GAME_MUS_CONTINUE MUS_{g["music"].get("continue", g["music"]["clear"])}',
         (f'#define GAME_MUS_OVER 0   /* GAME OVER: no song, the continue song fades out ($0A + speed, KOF98) */\n#define GAME_OVER_FADE 0x2C'
          if g['music'].get('gameover') == 'FADE' else f'#define GAME_MUS_OVER MUS_{g["music"].get("gameover", g["music"]["clear"])}\n#define GAME_OVER_FADE 0'),
         'enum { ' + ', '.join(f'AI_{n.upper()}' for n in presets) + ' };',
         'enum { ' + ', '.join(f'EN_{e["name"].upper()}' for e in M['enemies']) + ' };',
         'extern const char *const gstage_names[GS_COUNT];   /* game.json stages[].name: the HUD, GAME OVER */',
         'extern const gstage_t gstages_rom[GS_COUNT];', 'extern const gfinale_t gfinale[GS_COUNT];', 'extern const genemy_t genemies_rom[EN_COUNT];',
         'extern const ai_preset_t ai_presets_rom[AI_COUNT];', 'extern const gbossai_t *const gbossai_rom[EN_COUNT];   /* (T9) a boss\'s own AI layer per enemy, 0 = none (gamedata.h) */', 'extern const gtint_t gtints[TINT_COUNT];',
         'extern const int8_t gtint_lut[TINT_COUNT - 1][1024];   /* fighter.c tint_colour: tint t\'s (l * mix + c) * mul >> shift at [t - 1][l * 32 + c] */',
         'extern const sel_slot_t SEL_SLOT[SEL_NPLACE];', 'extern const int16_t sel_lay_cam[SEL_NLAY][2];', 'extern const uint8_t sel_fighter[SEL_NSLOT];', 'extern const uint8_t sel_palbase[SEL_NSLOT];', 'extern const uint8_t sel_lay_n[SEL_NLAY], sel_lay_base[SEL_NLAY];', 'extern const uint8_t sel_stick[SEL_NLAY][SEL_NSLOT][2];', 'extern const uint8_t sel_vert[SEL_NLAY][SEL_NSLOT][2][SEL_NSLOT - 1];',
         'extern const uint8_t roster_unlock[BC_COUNT];',
         'extern const uint8_t roster_music[BC_COUNT];   /* the fighter\'s theme (game.json roster[].music), 0 = none: main.c stage_song */',
         'extern const uint16_t *const dtier_rom[BC_COUNT];   /* the damage tiers (fighter.c "damage tiers"): per fighter, 8.8 scales: [special index], [nspec] the fury, [nspec + 1] the MAX */',
         'extern uint8_t dtier_off;                         /* (fighter.c) 1: every scale 1 (a test switch) */',
         'extern const uint8_t ai_ready[BC_COUNT][2];',
         'extern const uint8_t ai_roles[BC_COUNT][AR_COUNT];   /* the special slot (BS_*) each fighter plays as an enemy\'s projectile / anti-air / rush (AR_*; 0xFF none; build_tables ai_roles) */',
         'extern const uint8_t gblitz_rom[BC_COUNT][4];   /* per fighter its Blitz slots (BZ_FF .. BZ_UU): a special\'s pool index, BZ_DASH its dash entry, BZ_NORMAL its blitz entry, BZ_NONE */',
         'extern const uint8_t gfury_wait[BC_COUNT];   /* 1: the fury (D) holds its first frame through the super flash\'s freeze, its move after (roster[].fury_flash, default wait for a sequence fury: fighter.c flash_pose) */',
         'extern const uint8_t gfury_area[BC_COUNT][3];  /* the fury\'s final hit as an area hit (roster[].fury_final_area; fighter.c fury_area): [front, back, depth] px, 0 = none */',
         'extern const int32_t gwalk_rom[BC_COUNT];       /* its walk (16.16 px a frame, by archetype) */',
         'extern const int32_t gblitz_hit[BC_COUNT][2][3];   /* per fighter its Blitz played as the dash entry [0] / a normal\'s blitz entry [1]: [vy, vx, recovery] (16.16 px a frame, frames; roster[].blitz_hit; fighter.c fighter_hit, S_ATTACK), vy 0 = the engine\'s knockdown */',
         'extern const int32_t gblitz_slide[BC_COUNT][4][3];   /* per fighter per Blitz slot: its slide [frames, first frame\'s glide, its loss a frame] (16.16 px; roster[].blitz_slide; fighter.c blitz_slide), frames 0 = none */',
         'extern const uint8_t gblitz_can[BC_COUNT][4];   /* per fighter per Blitz slot: the slots it may cancel into on hit (bit BZ_*; roster[].blitz_cancel) */',
         'extern const uint8_t *const grun_bob[BC_COUNT]; /* the run\'s float: [period, px a frame...] (roster[].run.float), 0 = none */',
         'extern const uint8_t *const grun_dash[BC_COUNT]; /* the dash: [start, frames, x..., height..., air_buttons] (roster[].run.mode dash), 0 = a run */',
         'extern const uint16_t gwalk_run;               /* run = walk x this (8.8) */',
         'extern const uint16_t gwalk_anim;              /* the walk / run animations\' rate x this (8.8) */',
         'extern const int32_t grun_spd[BC_COUNT];       /* the run at its source\'s speed (16.16; roster[].run.speed), 0 = walk x gwalk_run */',
         'extern const uint16_t grun_anim[BC_COUNT];     /* the run animation\'s rate = the walk\'s x this (8.8; game.json walk.run_anim / walk.anim, 256 for a roster[].walk_rate fighter) */',
         f'typedef struct {{ uint8_t fast, n; uint16_t rate; uint8_t kind[{MAXC_N}], dmg[{MAXC_N}]; uint16_t hsc[{MAXC_N}]; }} gmaxc_t;   /* the MAX\'s tail (game.json roster[].max_chain; fighter.c "the MAX chain"): its first `fast` pieces at rate (8.8), then n throws: kind 0 forward / 1 back / 2 the hold B throw, damage, height scale (8.8, 0 = 1x) */',
         'extern const gmaxc_t gmax_chain[BC_COUNT];',
         'extern const uint8_t gfury_box[BC_COUNT];     /* the fury\'s and MAX\'s attack boxes: half extents times this (game.json roster[].fury_box_scale; fighter.c strike) */',
         'extern const uint8_t gfury_back[BC_COUNT];    /* 1: the fury\'s and MAX\'s attack boxes reach back to the fighter\'s body, close range connects (game.json roster[].fury_box_back; fighter.c strike) */',
         'extern const uint8_t *const gbox_back[BC_COUNT];   /* per fighter [special index, px] pairs, 0xFF ends (0 = none): that special\'s body attack boxes reach back to px behind the fighter\'s own x (game.json roster[].box_back; fighter.c strike, reach_back) */',
         'extern const uint8_t gfury_throw[BC_COUNT];   /* the fury closes with the hold B throw on its reeling victim, this damage (game.json roster[].fury_throw; 0 = none; fighter.c fury_throw) */',
         'extern const uint8_t ghold_timeout[BC_COUNT];   /* the holder hold timeout (game.json roster[].hold_timeout): 0 stand (the victim let go on its feet), 1 knockdown (it falls on its back, no damage); fighter.c hold_update */',
         'extern const uint8_t gthrow_air[BC_COUNT];     /* bit BT_*: that throw\'s thrower, airborne after its release (SS2 Hanzo\'s leap back), takes the jump\'s controls on A (game.json roster[].keeps_air_attack "throw_c" / "throw_d"; fighter.c throw_air) */',
         'extern const uint8_t gxthr_cost[BC_COUNT][3];   /* the hold extras\' price (game.json roster[].throws.extra_cost, note 20261017-015547-e03d; fighter.c hold_update): drive chunks for [up + A, down + A, B] (0 free) */',
         'extern const uint8_t grun_grab[BC_COUNT][3];   /* the run grab (game.json roster[].throws.run, note 20261016-100735-e03d; fighter.c try_grab): [its grab special\'s pool index (0xFF none), run frames before it, drive chunks it costs] */',
         'extern const int16_t gsgt_bounce[BC_COUNT][2];   /* a grab special\'s slam bounce (vy, vx 8.8 px a frame; game.json slam_bounce, special_grab_timing.bounce; fighter.c slam_bounce) */',
         'extern const gthrev_t gthrow_ev[BC_COUNT][TM_COUNT];   /* THE THROW EVENTS of a paired throw (game.json roster[].throws.events; gamedata.h gthrev_t, fighter.c; imp 0: none) */',
         'extern const gsgev_t gsg_ev[BC_COUNT][2];   /* THE THROW EVENTS of a grab special: [0] hold + B (throws.extra.b), [1] the run grab (throws.run.special); ix its pool index, 0xFF none */',
         'extern const gshake_t gthrow_shake;   /* the screen shake at a throw\'s impact (game.json throw_shake) */',
         'extern const gthrtm_t gthrow_tm[BC_COUNT][TM_COUNT];   /* a throw\'s damage row and hand-off row as Bruno judged it (game.json roster[].throws.timing; gamedata.h gthrtm_t, fighter.c throw_start; 0xFFFF: the rule) */',
         'extern const uint8_t gthrow_keep[BC_COUNT];    /* 1: the chain\'s back throw whose thrown body hits another enemy keeps the chain one link in (game.json roster[].throw_keeps_chain, Final Fight Haggar\'s quirk; fighter.c chain_throw) */',
         'extern const uint16_t gclear_walk[BC_COUNT];   /* the stage clear: instead of the win pose he walks to this screen x (game.json roster[].clear_walk.to; 0 = none: the win pose; CLEAR_WALK_OFF = "off": right until his whole picture has left the screen, the screen edges not holding him; main.c win_tick) */',
         '#define CLEAR_WALK_OFF 0xFFFF',
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
    lab_p = os.path.join(build, 'chainlab.json')         # the enemy AI's specials by situation (ai_roles; the export's)
    rl = ai_roles(g, json.load(open(lab_p)) if os.path.exists(lab_p) else {'fighters': []})
    c.append('const uint8_t ai_roles[BC_COUNT][AR_COUNT] = { ' + ', '.join('{ ' + ', '.join(f'0x{x:02X}' for x in row) + ' }' for _, row in rl) +
             ' };   /* projectile, anti-air, rush slots (BS_*; 0xFF none): ' + ' '.join(n for n, _ in rl) + ' */')
    c += boss_tables(g)                                  # the guard's rules + the bosses' own layer (T9)
    m = g['meter']                                       # the drive meter + the hidden fury gauge (Bruno's redesign
    for k in m: assert k in METER_KEYS, f'meter: unknown field {k}'   # 2026-10-08, gamedata.h gmeter_t)
    mx = m.get('max_chunks', 4)                         # the bar's most chunks (a bonus game's reward up to it; main.c
    assert mx in (1, 3, 5, 15), 'meter.max_chunks: 1, 3, 5 or 15 (a chunk = the 15-cell life bar / max_chunks, whole cells)'   # MAX_CHUNKS)
    assert 1 <= m['chunks'] <= mx and 1 <= m['chunk'] and m['chunk'] * mx < 65536, 'meter: chunks x chunk'
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
             f".pause = {sum(REFILL_PAUSE[k] for k in m.get('refill_pause', []))}, "
             f".brk_in = {sum(BREAKER_WHEN[k] for k in m.get('breaker_when', ['hitstun', 'grabbed']))}, "
             f".brk_fury = {sum(BREAKER_WHEN[k] for k in m.get('breaker_fury', []))} }};")
    for k in m.get('breaker_when', []) + m.get('breaker_fury', []):
        assert k in BREAKER_WHEN, f'meter.breaker_when / breaker_fury: {k!r} ({", ".join(BREAKER_WHEN)})'
    wk = g.get('wakeup') or {}                           # the wake-up reversal (note 20261017-012714-e03d; gamedata.h gwake_t)
    for k in wk: assert k in WAKE_KEYS, f'wakeup: unknown field {k}'
    assert isinstance(wk.get('special', False), bool) and isinstance(wk.get('fury', False), bool), 'wakeup.special / fury: true / false'
    for k in ('from', 'ai_chance', 'ai_dx', 'ai_dz'):
        assert isinstance(wk.get(k, 0), int) and 0 <= wk.get(k, 0) <= 255, f'wakeup.{k}: 0-255'
    c.append(f"const gwake_t gwake = {{ .flags = {(1 if wk.get('special') else 0) | (2 if wk.get('fury') else 0)}, .from = {wk.get('from', 0)}, "
             f".ai_chance = {wk.get('ai_chance', 0)}, .ai_dx = {wk.get('ai_dx', 0)}, .ai_dz = {wk.get('ai_dz', 0)} }};   /* game.json wakeup */")
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
    c.append('const int32_t gblitz_hit[BC_COUNT][2][3] = {\n' + ',\n'.join(
        '    { ' + ', '.join('{ %d, %d, %d }' % tuple(v) for v in row) + ' }   /* ' + n + ' */' for n, row in blitz_hits(g)) + '\n};')
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
    for r in g['roster']:                                # roster[].special_grab_timing {input: {kind, damage_frame, glue_frame}}
        for inp, e in (r.get('special_grab_timing') or {}).items():   # (export_bm special_grab_timing, fighter.c vlist_place)
            w = f"roster {r['name']}: special_grab_timing.{inp}"
            for k in e: assert k in ('kind', 'damage_frame', 'glue_frame', 'bounce', 'from'), f"{w}: unknown field {k}"
            assert e.get('kind') == 'slam', f"{w}: kind 'slam' (one damage, at the slam)"
            for k in ('damage_frame', 'glue_frame'):
                assert k not in e or (isinstance(e[k], int) and 1 <= e[k] <= 255), f"{w}.{k}: a program frame 1-255"
            assert 'damage_frame' in e or 'glue_frame' in e, f"{w}: damage_frame and / or glue_frame"
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
    ta, tk, cw = [], [], []                              # the throws' air control (note 20261015-212313-e03d: SS2
    for r in g['roster']:                                # Hanzo's leap back after his forward throw, "make him
        ka = r.get('keeps_air_attack') or []             # controllable: air attacks or Blitz"): keeps_air_attack's
        bad = [k for k in ka if k.startswith('throw_') and k not in ('throw_c', 'throw_d')]   # throw names, as bits
        assert not bad, f"roster {r['name']}: keeps_air_attack {bad}: throw_c | throw_d"
        ta.append(str((1 if 'throw_c' in ka else 0) | (2 if 'throw_d' in ka else 0)))
        v = r.get('throw_keeps_chain', False)            # Final Fight Haggar's quirk (note 20261015-224938-e03d)
        assert v in (True, False), f"roster {r['name']}: throw_keeps_chain true | false"
        tk.append('1' if v else '0')
        w = r.get('clear_walk')                          # Final Fight's stage end (note 20261015-224745-e03d)
        if w is None: cw.append('0'); continue
        for k in w: assert k in ('about', 'to'), f"roster {r['name']}: clear_walk: unknown field {k}"
        if w['to'] == 'off': cw.append('CLEAR_WALK_OFF'); continue   # (note 20261015-224745-e03d reopen: "walk all
                                                         # the way out of the screen, like he's going to the next stage")
        assert isinstance(w['to'], int) and 160 <= w['to'] <= 360, f"roster {r['name']}: clear_walk.to {w['to']} (screen x 160-360, or 'off')"
        cw.append(str(w['to']))
    c.append('const uint8_t gthrow_air[BC_COUNT] = { ' + ', '.join(ta) + ' };')
    for r in g['roster']:                                # (THE THROW REVIEW round 2: until fighter.c plays the events, a
        assert not throw_events(r, g) or ENGINE_PLAYS_EVENTS, (f"roster {r['name']}: throws.events: this engine does not play them yet (fighter.c "   # game
            "reads throws.timing): refused, so Bruno's answers are never silently ignored")      # with them is refused)
    c.append('const gthrtm_t gthrow_tm[BC_COUNT][TM_COUNT] = {\n    ' + ',\n    '.join(
        '{ ' + ', '.join('{ %s, %s, %s, 0, %d, %d }' % t for t in throw_timing(r, g)) + f' }}   /* {r["name"]} */' for r in g['roster']) + '\n};')
    er, sr = event_rows(g, build)                        # THE THROW EVENTS (throw_events; fighter.c)
    c.append('const gthrev_t gthrow_ev[BC_COUNT][TM_COUNT] = {\n    ' + ',\n    '.join(er) + '\n};')
    c.append('const gsgev_t gsg_ev[BC_COUNT][2] = {\n    ' + ',\n    '.join(sr) + '\n};')
    sh = g.get('throw_shake') or {'frames': 0, 'px': 0}
    for k in sh: assert k in ('about', 'frames', 'px'), f'throw_shake: unknown field {k}'
    assert isinstance(sh.get('frames'), int) and 0 <= sh['frames'] <= 60 and isinstance(sh.get('px'), int) and 0 <= sh['px'] <= 8, 'throw_shake {frames 0-60, px 0-8}'
    c.append('const gshake_t gthrow_shake = { %d, %d };' % (sh['frames'], sh['px']))
    c.append('const uint8_t gxthr_cost[BC_COUNT][3] = {\n    ' + ',\n    '.join(
        '{ %d, %d, %d }' % t + f'   /* {n} */' for n, t in xthr_cost(g)) + '\n};')
    c.append('const uint8_t grun_grab[BC_COUNT][3] = {\n    ' + ',\n    '.join(
        '{ %d, %d, %d }' % t + f'   /* {n} */' for n, t in run_grab(g, build)) + '\n};')
    sb = []                                              # a grab special's slam bounce (special_grab_timing, slam_bounce)
    for r in g['roster']:
        bv = {slam_bounce(e, g.get('slam_bounce'), f"roster {r['name']}: special_grab_timing.{inp}")
              for inp, e in (r.get('special_grab_timing') or {}).items()}
        assert len(bv) <= 1, f"roster {r['name']}: special_grab_timing: one bounce for all its grab specials"
        sb.append('{ %d, %d }' % (bv.pop() if bv else (0, 0)) + f'   /* {r["name"]} */')
    c.append('const int16_t gsgt_bounce[BC_COUNT][2] = {\n    ' + ',\n    '.join(sb) + '\n};   /* (vy, vx) 8.8 px a frame */')
    c.append('const uint8_t gthrow_keep[BC_COUNT] = { ' + ', '.join(tk) + ' };')
    c.append('const uint16_t gclear_walk[BC_COUNT] = { ' + ', '.join(cw) + ' };')
    ft = []                                              # the fury's closing throw (note 20261014-171937-5d29, Haggar:
    for r in g['roster']:                                # "at the very end of everything, add the piledriver"): after the
        e = r.get('fury_throw')                          # fury's last piece its reeling victim is grabbed and thrown by
        if not e: ft.append(f'0   /* {r["name"]} */'); continue   # the hold's B throw (roster[].throws.b, bm_xthr x)
        for k in e: assert k in ('about', 'throw', 'damage'), f"roster {r['name']}: fury_throw: unknown field {k}"
        assert e.get('throw') == 'b' and (r.get('throws') or {}).get('b'), f"roster {r['name']}: fury_throw.throw 'b' needs roster[].throws.b"
        assert isinstance(e.get('damage'), int) and 1 <= e['damage'] <= 60, f"roster {r['name']}: fury_throw.damage 1-60"
        ft.append(f'{e["damage"]}   /* {r["name"]} */')
    c.append('const uint8_t gfury_throw[BC_COUNT] = {\n    ' + ',\n    '.join(ft) + '\n};')
    fb = []                                              # the fury's attack box scale (note 20261015-144945-e03d, Mr. Big:
    for r in g['roster']:                                # "the hitbox is too small, it keeps whiffing, make it three times
        v = r.get('fury_box_scale', 1)                   # bigger"): roster[].fury_box_scale = the half extents of every
        assert isinstance(v, int) and 1 <= v <= 4, f"roster {r['name']}: fury_box_scale 1-4"   # attack box of his fury
        fb.append(f'{v}   /* {r["name"]} */')            # and MAX, their bodies and objects (fighter.c strike), times it
    c.append('const uint8_t gfury_box[BC_COUNT] = {\n    ' + ',\n    '.join(fb) + '\n};')
    fk = []                                              # the fury's boxes reach back to its body (note 20261017-012812-e03d,
    for r in g['roster']:                                # Mr. Big: "if I'm close to Mr. Big, I will not get hit by his super
        v = r.get('fury_box_back', False)                # special move"): roster[].fury_box_back = every attack box of his
        assert isinstance(v, bool), f"roster {r['name']}: fury_box_back true / false"   # fury and MAX (body and objects)
        fk.append(f'{1 if v else 0}   /* {r["name"]} */')   # stretched back to his own body, whoever he fights for
    c.append('const uint8_t gfury_back[BC_COUNT] = {\n    ' + ',\n    '.join(fk) + '\n};')
    pools = {f['name']: [None if p.get('seq') else p['input'] for p in f['pool']]   # a special's boxes reaching behind
             for f in json.load(open(os.path.join(build, 'chainlab.json')))['fighters']}   # (note 20261017-122233-e03d,
    bb = []                                              # Terry's Rising Tackle: "so it also touches the people behind"):
    for r in g['roster']:                                # roster[].box_back = {input: px}: every body attack box of that
        e = {k: v for k, v in (r.get('box_back') or {}).items() if k != 'about'}   # special stretched back to px behind
        if not e: bb.append(f'0   /* {r["name"]} */'); continue   # his own x (fighter.c reach_back; the fury_box_back
        row = []                                         # stretch is the same with px 0)
        for inp, px in e.items():
            assert inp in pools[r['name']], f"roster {r['name']}: box_back {inp}: not in its pool ({' '.join(map(str, pools[r['name']]))})"
            assert isinstance(px, int) and 0 <= px <= 64, f"roster {r['name']}: box_back {inp}: px 0-64"
            row += [pools[r['name']].index(inp), px]
        c.append(f'static const uint8_t gbb_{r["name"]}[] = {{ ' + ', '.join(map(str, row + [0xFF])) + ' };')
        bb.append(f'gbb_{r["name"]}   /* {r["name"]} */')
    c.append('const uint8_t *const gbox_back[BC_COUNT] = {\n    ' + ',\n    '.join(bb) + '\n};')
    mc = []                                              # the MAX's own tail (Bruno 2026-10-15, Haggar's MAX: "jab, jab,
    for r in g['roster']:                                # finisher x 3, 50 % faster, the spin, back throw x 3, a half-height
        me = r.get('max_chain')                           # piledriver, a piledriver"): roster[].max_chain = the fury's
        if not me: mc.append(f'{{0}}   /* {r["name"]} */'); continue   # sequence played as the MAX with its first
        for k in me: assert k in ('about', 'fast_pieces', 'rate', 'throws'), f"roster {r['name']}: max_chain: unknown field {k}"
        assert isinstance(r.get('fury'), list), f"roster {r['name']}: max_chain needs a fury sequence (roster[].fury a list)"
        fp, rt, ts = me.get('fast_pieces', 0), me.get('rate', 1), me.get('throws') or []   # fast_pieces at `rate`, then
        assert isinstance(fp, int) and 0 <= fp <= len(r['fury']), f"roster {r['name']}: max_chain.fast_pieces 0-{len(r['fury'])}"
        assert isinstance(rt, (int, float)) and 1 <= rt <= 2, f"roster {r['name']}: max_chain.rate 1-2"
        assert 1 <= len(ts) <= MAXC_N, f"roster {r['name']}: max_chain.throws 1-{MAXC_N}"   # its reeling victim grabbed
        kd, dm, hs = [], [], []                          # and thrown by each of `throws` in turn, each throw's victim
        for mt in ts:                                     # grabbed again where it is (no launch before the last one):
            for k in mt: assert k in ('throw', 'damage', 'height'), f"roster {r['name']}: max_chain.throws: unknown field {k}"
            assert mt['throw'] in ('back', 'forward', 'b'), f"roster {r['name']}: max_chain.throws: throw back | forward | b"
            assert mt['throw'] != 'b' or (r.get('throws') or {}).get('b'), f"roster {r['name']}: max_chain throw b needs roster[].throws.b"
            assert isinstance(mt.get('damage'), int) and 1 <= mt['damage'] <= 60, f"roster {r['name']}: max_chain.throws damage 1-60"
            ht = mt.get('height', 1); assert isinstance(ht, (int, float)) and 0.25 <= ht <= 1, f"roster {r['name']}: max_chain.throws height 0.25-1"
            kd.append(str({'forward': 0, 'back': 1, 'b': 2}[mt['throw']])); dm.append(str(mt['damage'])); hs.append(str(round(ht * 256) if ht < 1 else 0))
        mc.append(f'{{{fp}, {len(ts)}, {round(rt * 256)}, {{{", ".join(kd)}}}, {{{", ".join(dm)}}}, {{{", ".join(hs)}}}}}   /* {r["name"]} */')
    c.append('const gmaxc_t gmax_chain[BC_COUNT] = {\n    ' + ',\n    '.join(mc) + '\n};')
    c += depth_tables(g, build)
    ch = g['chain']                                      # the chain core (revamp 1A): the engine's rules (gchain_t)
    for k in ch: assert k in CHAIN_KEYS, f'chain: unknown field {k}'
    assert 1 <= ch['window'] <= 255 and 0 <= ch['buffer'] <= 60 and 1 <= ch['juggle_cap'] <= 255 and \
        all(1 <= ch[k] <= 255 for k in ('stun_player', 'guard_player', 'stun_light', 'stun_heavy')), 'chain values'
    assert set(ch['lengths']) == set(ch['totals']) == {'fast', 'balanced', 'heavy'} and all(2 <= v <= 6 for v in ch['lengths'].values()), 'chain lengths'
    assert ch.get('juggle_reset_button') in JUGGLE_RESET, f"chain.juggle_reset_button: one of {list(JUGGLE_RESET)}"
    assert len(ch['hitstop']) == 2 and 1 <= ch['hitstop'][0] <= ch['hitstop'][1] <= 60, 'chain hitstop'
    c.append(f"const gchain_t gchain = {{ .window = {ch['window']}, .buffer = {ch['buffer']}, .juggle_cap = {ch['juggle_cap']}, "
             f".stun_player = {ch['stun_player']}, .guard_player = {ch['guard_player']}, .stun_light = {ch['stun_light']}, "
             f".stun_heavy = {ch['stun_heavy']}, .jreset = {JUGGLE_RESET[ch.get('juggle_reset_button')]} }};")
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
    snames = {v.upper(): int(k, 16) for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))['sfx']['names'].items()}
    mc = g.get('max_cancel') or {}                       # the fury -> MAX cancel (note 20261016-133443-e03d, gamedata.h gmaxcan_t)
    for k in mc: assert k in ('about', 'on', 'window', 'backdrop', 'sound'), f'max_cancel: unknown field {k}'
    assert mc.get('window', 'hit') in ('hit', 'any'), "max_cancel.window: 'hit' | 'any'"
    assert isinstance(mc.get('on', True), bool), 'max_cancel.on: true | false'
    assert not mc.get('sound') or mc['sound'].upper() in snames, f"max_cancel.sound {mc.get('sound')!r}: no songs.json sfx name"
    c.append(f"const gmaxcan_t gmaxcan = {{ .on = {1 if mc and mc.get('on', True) else 0}, .any = {1 if mc.get('window') == 'any' else 0}, "
             f".sound = 0x{snames[mc['sound'].upper()] if mc.get('sound') else 0:02X}, .backdrop = {mc.get('backdrop', '0x0000')} }};")
    c.append('const gspsnd_t gspec_snd[] = {')            # roster[].special_sounds (note 20261016-100735-e03d round 3)
    for n, ix, at, code in special_sounds(g, build, snames): c.append(f'    {{ {n}, {ix}, {at}, 0x{code:02X} }},')
    c.append('    { 0xFF, 0, 0, 0 } };')
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
        xrows.append(f'    {{ .trig = {f"stage{si}_triggers" if s["triggers"] else 0}, .ntrig = {len(s["triggers"])}, .drama = {s["drama"]}, .start = {s["start"]} }},   /* {s["name"]} */')
    c.append('const gstagex_t gstagex_rom[GS_COUNT] = {\n' + '\n'.join(xrows) + '\n};')
    frows = []                                           # the finales (ROM only: a Lab pack's stages keep the ROM's)
    for si, s in enumerate(M['stages']):
        f = s['finale']
        if not f: frows.append(f'    {{ 0 }},   /* {s["name"]} */'); continue
        if f['spawns']:
            c.append(f'static const gspawn_t stage{si}_finale_spawns[] = {{\n    ' + ',\n    '.join(
                f'{{ .enemy = {d["enemy"]}, .pick = {d["pick"]}, .set = {d["set"]}, .tint = {d["tint"]}, .x = {d["x"]}, .z = {d["z"]}, .flags = 0x{d["flags"]:02X} }}'
                for d in f['spawns']) + '\n};')
        frows.append(f'    {{ .on = 1, .boss = {f["boss"]}, .song = MUS_{f["song"]}, .drama = {f["drama"]}, .nmin = {len(f["spawns"])}, '
                     f'.x = {f["x"]}, .z = {f["z"]}, .seed = 0x{f["seed"]:04X}, .spawns = {f"stage{si}_finale_spawns" if f["spawns"] else 0} }},   /* {s["name"]} */')
    c.append('const gfinale_t gfinale[GS_COUNT] = {   /* stages[].boss.finale (main.c "the finale") */\n' + '\n'.join(frows) + '\n};')
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
    lay = select_layers(g, L, build); E = sel_extents(build, g, slots)
    cam_max = int(re.search(r'#define LAND_CAM_MAX (\d+)', open(os.path.join(build, 'land.h')).read()).group(1))
    c.append('const sel_slot_t SEL_SLOT[SEL_NPLACE] = {   /* the places, layer after layer (select_layers: game.json select.auto, else select_layout): x, y (feet), z (draw order), face */\n    ' + '\n    '.join(
        f'{{ {Ln[m]["x"]}, {Ln[m]["y"]}, {Ln[m]["z"]}, {1 if Ln[m]["facing"] == "right" else -1} }},   /* layer {r} ({n}): {m} */'
        for r, (n, base, Ln) in enumerate(lay) for m in sorted(Ln, key=lambda m: Ln[m]['slot'])) + '\n};')
    c.append('const int16_t sel_lay_cam[SEL_NLAY][2] = { ' + ', '.join('{ %d, %d }' % select_cams(Ln, E, cam_max) for n, base, Ln in lay) +
             ' };   /* each layer\'s camera range (select_cams: lo = hi, the group fits the screen) */')
    c.append('const uint8_t sel_fighter[SEL_NSLOT] = { ' + ', '.join(str(idx[n]) for n in slots) + ' };')
    c.append('const uint8_t sel_palbase[SEL_NSLOT] = { ' + ', '.join(map(str, sel_palbases(g, build)[0])) + ' };   /* each slot\'s first palette: back to back, its fighter\'s own count */')
    stick = g.get('select', {}).get('stick', 'positions')
    assert stick in ('positions', 'order'), f'game.json select.stick: {stick!r} (positions | order)'
    heads = bm_heads(build, g); N = len(L)
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
    rung_of = {f: k + 1 for k, r in enumerate(U['rungs']) for f in r} if U else {}
    for r in g['roster']:
        u = r.get('unlock', 'always')
        if U:                                            # the ladder: 0 a starter, $80 + k rung k (1-based), 0xFF off the
            n = r['name']                                # select screen (an enemy only)
            unl.append(0xFF if not r.get('selectable', True) or n not in U['all'] else 0 if n in U['starters'] else
                       0x80 + rung_of[n])
            continue
        unl.append(0xFF if not r.get('selectable', True) else 0 if u == 'always' else u['boss_of_stage'])   # 0xFF: never
                                                                 # picked (a form link's target, main.c char_locked)
        assert u == 'always' or 1 <= u['boss_of_stage'] <= len(g['stages']), f'{r["name"]}: unlock {u}'
    c.append('const uint8_t roster_unlock[BC_COUNT] = { ' + ', '.join(map(str, unl)) + ' };   /* stage k + 1 whose boss unlocks it, '
             '0 = always, $80 + k = the unlock ladder\'s rung k, 0xFF = never (a form; with the ladder: off the select screen) */')
    P = ladder_places(U, U['screen']) if U else []
    h += [f'#define LAD_N {len(P)}            /* the unlock ladder (game.json unlocks): its fighters, starters first; 0 = none */',
          f'#define LAD_RUNGS {len(U["rungs"]) if U else 0}             /* rungs (each its own size: lad_rung) */',
          f'#define LAD_CAM_MAX {ladder_cam_max(U, U["screen"]) if U else 0}             /* the ladder screen\'s camera: 0 .. this (a row wider than the TV: ladder_cam_max) */',
          'extern const uint8_t lad_fighter[LAD_N ? LAD_N : 1], lad_rung[LAD_N ? LAD_N : 1], lad_slot[LAD_N ? LAD_N : 1];',
          'extern const sel_slot_t lad_pos[LAD_N ? LAD_N : 1];']
    if P:
        c.append('const uint8_t lad_fighter[LAD_N] = { ' + ', '.join(str(idx[e[0]]) for e in P) + ' };   /* ' + ' '.join(e[0] for e in P) + ' */')
        c.append('const uint8_t lad_rung[LAD_N] = { ' + ', '.join(str(e[1]) for e in P) + ' };   /* 0 the starters, k rung k */')
        c.append('const uint8_t lad_slot[LAD_N] = { ' + ', '.join(str(L[e[0]]['slot']) for e in P) + ' };   /* its select slot (its palettes: sel_palbase) */')
        c.append('const sel_slot_t lad_pos[LAD_N] = { ' + ', '.join(f'{{ {e[2]}, {e[3]}, {e[4]}, {e[5]} }}' for e in P) + ' };   /* world x (the camera 0 .. LAD_CAM_MAX), feet y, draw order, face */')
    else:
        c += ['const uint8_t lad_fighter[1], lad_rung[1], lad_slot[1];', 'const sel_slot_t lad_pos[1];']
    SJ = json.load(open(os.path.join(os.path.dirname(os.path.abspath(build)), 'songs.json')))
    known = {x['name'] for x in SJ['songs']}
    benched = {x['name'] for x in (SJ.get('songs_benched') or {}).get('songs', [])}   # kept, not in the sound ROM: a
    for r in g['roster']:                                # theme there = none in this build (stage 1 plays its own song)
        assert r.get('music') is None or r['music'] in known | benched, f"{r['name']}: music {r['music']!r} is no songs.json song"
    c.append('const uint8_t roster_music[BC_COUNT] = { ' + ', '.join(f"MUS_{r['music']}" if r.get('music') in known and not r.get('slot_of') else '0' for r in g['roster'])   # (a Lab build's slot: none, the shell and every pack the same)
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
    eh, ec = map_tables(g)
    h += eh; c += ec
    h += cheat_tables(g)
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
    sx_o = put(b''.join(struct.pack('>IBBh', o, len(s['triggers']), s['drama'], s['start']) for o, s in zip(tro, M['stages'])))
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
            'route_files': files, 'ai_flags': AI_FLAGS, 'ai_fields': AI_FIELDS, 'chance_masks': CHANCE_MASKS, 'ai_order': AI_ORDER, 'ai_moves': AI_MOVES,
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
