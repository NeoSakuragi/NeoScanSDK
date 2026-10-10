#!/usr/bin/env python3
"""Brawler fighter data: a beat 'em up subset of each fighter's animations from the KOF dictionaries
(tools/kof96/export96.py, any of KOF96/98/99), written as const 68000 tables + the C1/C2 tiles they use.

    python3 export_bm.py OUTDIR --roster ROSTER.json [--lab NAME] -> bm_chars.c/.h, bm_c1.bin, bm_c2.bin

--lab NAME: the Brawler Lab's build of one fighter ("Try in game", make LAB_FIGHTER=NAME): every animation of his dictionary
in one more special of his pool, LAB (export96.lab_special; bm_lab; OUTDIR/lab.json the page's manifest).

ROSTER.json = build_tables.py's roster view of examples/brawler/game.json (the Makefile writes build/roster.json): per
fighter in bm_chars order, its bank spec (game:name), its select-screen 'watch' pose, its specials (the KOF input of each
of D, forward+D, down+D, up+D, or null) and its chain routes file (null: routes.default_tree()). Tools that import this
module (check_specials.py...) get the roster of examples/brawler/game.json (roster()).

Per fighter: frames (parts: dx, dy, columns, rows, flips, palette index, tile columns), animations (steps: frame, ticks,
one hurt box = union of KOF's hurt boxes, the attack box when the step has one), every colour set (16-colour palettes,
one per palette index), physics (16.16 px/frame). Boxes are KOF's: centre offset from the feet (y < 0 = up) and half
extents, in the sprites' own orientation (ROM sprites face LEFT: mirror x when the fighter faces right).
Tile numbers start at TILE_BASE (1 .. TILE_BASE - 1 hold the stage, banner and sparks).

The Character Lab's shell (make LAB_SHELL=1 / LAB_PACK=<f>, docs/feedback.md "Character Lab: shell and packs"): ROSTER.json
ends with the slot fighter (build_tables.add_slot: name 'slot', slot_of = its source f). It is exported as f (f's data
files: ALIAS / src()), under the C prefix slot_, with every animation of f's dictionary in its LAB special when f's game
allows it (KOF96 / 98 / 99 with tools/brawler/arb_pieces/<f>.json), its tiles in a block of SLOT_TILES of its own; its
tables never share another fighter's (dedupe_c); OUTDIR/slot.json says where its tiles are (lab_pack.py)."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import export96
import handlers98 as H
import routes as R
import retime as RT
import build_tables
import voices as V
import head_point as HP
import pal_pack as PP
PACKED = {}                                             # per fighter its palette packing (pal_pack.pack's report)
LAB = {}                                                # the Lab build (--lab NAME, make LAB_FIGHTER=NAME): {name: [(hex id,
                                                        # state)]} its dictionary's animations (arb_pieces/<name>.json)
LABINFO = {}                                            # name -> (its LAB special's pool index, its $NN ids) (write_c)
ALIAS = {}                                              # the shell's slot: {'slot': its source fighter} (roster slot_of)
SLOT_TILES = 24576                                      # the slot's C block (tiles, 3 MB): every roster fighter fits it,
                                                        # Rugal 13204, a LAB export of a KOF fighter ~9300 (Robert)
def src(n):
    """the roster name whose data files a fighter reads: the slot's source fighter, else itself"""
    return ALIAS.get(n, n)
def alias_slot(slot, f):
    """the slot exported as fighter f: the name-keyed tables of this module and of voices.py / routes.py read f's"""
    ALIAS[slot] = f
    for d in (ROLE_OVERRIDE, FIRE_COLOUR):
        if f in d: d[slot] = d[f]
    if f in NO_EX: NO_EX.add(slot)
    for (a, b), v in list(ROM_REACT.items()):
        if a == f: ROM_REACT[(slot, b)] = v
    def first(fn): return lambda name, *a, **k: fn(src(name), *a, **k)
    for fn in ('bank', 'suggest', 'extras', 'anim_extras', 'fx_bit'): setattr(V, fn, first(getattr(V, fn)))
    t = V.table; V.table = lambda ks, sug, mp, nv, name=None: t(ks, sug, mp, nv, src(name) if name else name)
    for fn in ('load', 'chain_tree'): setattr(R, fn, first(getattr(R, fn)))

def lab_entries(name):
    """the Lab build's fighter: every animation of his dictionary as (hex id, state), id order (arb_pieces/<name>.json
    "anims", the dictionary's ids and the state that addresses each: arb_compile.py pieces)"""
    lib = json.load(open(os.path.join(HERE, 'arb_pieces', name + '.json')))
    return sorted(((x, a['state']) for x, a in lib['anims'].items() if isinstance(a.get('state'), int)), key=lambda e: int(e[0], 16))
GAME_JSON = os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')
_ROSTER = None
def roster(path=None):
    """{name: roster entry} (build_tables.roster_export): from ROSTER.json when given, else from game.json"""
    global _ROSTER
    if path: _ROSTER = {r['name']: r for r in json.load(open(path))}
    elif _ROSTER is None: _ROSTER = {r['name']: r for r in build_tables.roster_export(build_tables.load(GAME_JSON))}
    return _ROSTER

# the brawler's animation set (KOF move names); MOVES order = the BA_* enum
MOVES = ['idle', 'walk_fwd', 'run', 'prejump', 'jump_up_rise', 'jump_up_fall', 'jump_fwd_rise', 'jump_fwd_fall', 'land',
         'atk_a_close', 'atk_a_far', 'atk_b_close', 'atk_b_far', 'atk_c_close', 'atk_c_far', 'atk_d_close', 'atk_d_far',
         'atk_d_crouch', 'atk_c_jump', 'atk_d_jump', 'body_toss', 'hit_stand_light', 'hit_stand_heavy', 'hit_air',
         'blowback', 'knockdown_flight', 'knockdown_bounce', 'knockdown_fall', 'down', 'getup', 'trip', 'win', 'atk_c_crouch',
         'cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d',   # command normals (KOF97+: forward+A / B, down-forward+C / D)
         'blowback_n',                                 # KOF98's blowback when not a counter hit (285; blowback = 283)
         # the two jump heights (tools/kof96/capture/jumps.py, 2026-10-04): jump_* = stick held (KOF states 4/5, 8/9,
         # 12/13), hop_* = stick tapped (15/16, 17/18, 19/20), each with its own animation; air normals per jump kind
         'hop_up_rise', 'hop_up_fall', 'hop_fwd_rise', 'hop_fwd_fall', 'jump_back_rise', 'jump_back_fall',
         'hop_back_rise', 'hop_back_fall', 'atk_c_jump_diag', 'atk_d_jump_diag',
         'atk_c_hop', 'atk_d_hop', 'atk_c_hop_diag', 'atk_d_hop_diag',
         'atk_cd_jump', 'atk_cd_hop',                   # air C+D: KOF state 117, KOF98 / KOF99 hops 124 (capture/aircd.py)
         'watch',                                       # the group photo's pose (select screen): roster watch
         'atk_a_crouch', 'atk_b_crouch',                # crouch A / B (KOF 88 / 97): chain routes (Chain Lab, routes.py)
         # World Heroes Perfect's six buttons (tools/whp/moves_whp.py, 2026-10-06): A+B = strong punch, C+D = strong kick
         # in every stance, the air A / B / A+B / C+D (vertical, diagonal), forward + C / C+D where the game has its own
         # animation, the running normals (the move + 3 / + $1B with down). Route cards (routes.MOVE_NAMES) for any
         # fighter that has them; the others never play them (routes.encode: has)
         'atk_ab_close', 'atk_ab_far', 'atk_ab_crouch', 'atk_cd_close', 'atk_cd_crouch', 'cmd_fwd_c', 'cmd_fwd_cd',
         'atk_a_jump', 'atk_a_jump_diag', 'atk_b_jump', 'atk_b_jump_diag', 'atk_ab_jump', 'atk_ab_jump_diag',
         'atk_cd_jump_diag',
         'atk_a_run', 'atk_b_run', 'atk_ab_run', 'atk_c_run', 'atk_d_run', 'atk_cd_run',
         'atk_a_run_low', 'atk_b_run_low', 'atk_ab_run_low', 'atk_c_run_low', 'atk_d_run_low', 'atk_cd_run_low',
         'walk_back']                                   # an AI fighter walking away from its target (it always faces
                                                        # it, Bruno 2026-10-08): KOF's walk-back (state 2), else source()'s
                                                        # walk played backwards
# The group photo's 'watch' pose (TODO #51, 2026-10-05): a front-facing, standing frame, one per fighter (game, name) ->
# (KOF game state, step; -1 = the animation's last, held frame). KOF94 / KOF95 had real "watching" sprites: the waiting
# teammates on the stage's edge are fighter objects (+$70 = the fighter id) in KOF95 states 155 watch, 156 / 157 react,
# 158 / 159 the round won / lost, 160 KO'd (slots 36-41 of every fighter's table, measured in our emulator); KOF96 dropped
# them and its, KOF98's and KOF99's tables have no such slot. So the pick is the closest front-facing frame among the
# intros (KOF98 / KOF99 347-354: 347 the walk-in, 348 the intro, 349-354 the special intros' frames) and the win poses
# (336-343; KOF96: its intros / wins 208-239), chosen by eye on a render of every candidate. Missing: idle.
# watch poses: Bruno's two judging rounds, 2026-10-05 (round 2 picked Billy 347 last, Mai 338 last, Robert 340 last,
# Yamazaki 349 first, Yashiro 340 last)
# The poses are data now: game.json roster[].watch {frame, step} (moved there 2026-10-05 with these picks).
CMDS = ['cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d']   # bchar_t.cmds bit k: the fighter has CMDS[k] (export96.CMD_NORMALS)
# brawler move -> the KOF moves it is taken from, first found. Air normals measured in the games (capture/jumps.py, every
# roster fighter): a regular jump plays the vertical normal (82/91/100/109) straight up and the diagonal one (84/93/102/111)
# forward; back (86/95/104/113) maps to the diagonal one's animation slot. A hop: KOF98 / KOF99 have hop normals (120-123,
# one per button, every direction); KOF96 has none, its hop plays the regular jump's normals by direction.
SOURCES = {'atk_c_hop': ['atk_c_hop', 'atk_c_jump'], 'atk_d_hop': ['atk_d_hop', 'atk_d_jump'],
           'atk_c_hop_diag': ['atk_c_hop', 'atk_c_jump_diag'], 'atk_d_hop_diag': ['atk_d_hop', 'atk_d_jump_diag'],
           'atk_cd_hop': ['atk_cd_hop', 'atk_cd_jump'],
           # the six-button air normals on a fighter without them (an air node is played whatever the fighter has:
           # fighter.c start_node): the jump's C / D / C+D
           'atk_a_jump': ['atk_a_jump', 'atk_c_jump'], 'atk_a_jump_diag': ['atk_a_jump_diag', 'atk_c_jump_diag'],
           'atk_b_jump': ['atk_b_jump', 'atk_d_jump'], 'atk_b_jump_diag': ['atk_b_jump_diag', 'atk_d_jump_diag'],
           'atk_ab_jump': ['atk_ab_jump', 'atk_d_jump'], 'atk_ab_jump_diag': ['atk_ab_jump_diag', 'atk_d_jump_diag'],
           'atk_cd_jump_diag': ['atk_cd_jump_diag', 'atk_cd_jump']}
def source(ch, m):
    """the KOF animation a brawler move plays (idle when the fighter has none; walk_back without its own: the walk's
    steps in reverse order, one object per fighter so its step array is shared)"""
    if m == 'walk_back' and 'walk_back' not in ch['anims'] and 'walk_fwd' in ch['anims']:
        w = ch['anims']['walk_fwd']
        if '_walk_rev' not in ch: ch['_walk_rev'] = dict(w, steps=list(reversed(w['steps'])))
        return ch['_walk_rev']
    return next((ch['anims'][k] for k in SOURCES.get(m, [m]) if k in ch['anims']), None) or ch['anims']['idle']
TILE_BASE = 2048                               # our first fighter tile; 1-2047: stage (1-1535, make_stage_ra.py), banner,
                                               # shadow, corners (make_banner.py), sparks (make_sparks.py); 0 empty
SRC_BASE = export96.TILE_BASE                  # export96 numbers its tiles from here

def sb(v): return v - 256 if v > 127 else v

REACH = 0                                      # px: minimum forward reach of a normal (was 96, beat 'em up reach; Bruno
                                               # 2026-10-08: "a feature that artificially makes the hitbox bigger... not
                                               # good for the gameplay": the ROM's attack boxes as drawn)

def boxes(bx, reach=0):
    """KOF step boxes -> (hurt union, attack) as (x, y, w, h) or None; reach: minimum forward reach of the attack box"""
    # KOF box key: the first hex digit is the type, 3 = hurt ('31'-'33', in every animation), 1 = attack ('11', '1B'-'1E',
    # only in attack animations; KOF96/98/99 census 2026-10-03). The second digit is not a slot: close A's attack box
    # is '1C', close C's / close D's '1D' (the old low-2-bits rule read '1D' as a hurt box: no C / D normal ever hit).
    # KOF99 '1B' = armor (it absorbs hits; only Maxima's C / D normals and C+D carry it): not an attack. KOF99 itself,
    # measured in our emulator: Maxima's close C hits twice (life 101 -> 90 at frames 132 and 150), not three times.
    hurt = [v for k, v in bx.items() if k[0] in '34']   # KOF94/95 hurt: 3x and 4x; kind = the key's first digit (rom96)
    atk = [v for k, v in bx.items() if k[0] == '1' and k.upper() != '1B']
    def norm(b): return sb(b[0]), sb(b[1]), b[2], b[3]
    h = None
    if hurt:
        l = min(sb(b[0]) - b[2] for b in hurt); r = max(sb(b[0]) + b[2] for b in hurt)
        t = min(sb(b[1]) - b[3] for b in hurt); bt = max(sb(b[1]) + b[3] for b in hurt)
        h = ((l + r) // 2, (t + bt) // 2, (r - l + 1) // 2, (bt - t + 1) // 2)
    a = None
    if atk:
        # Beat 'em up reach: the attack covers everything from the body line (x = 0) to its tip, so far normals still
        # land point blank inside a combo. Forward = negative x (ROM sprites face left); the vertical extent is kept.
        # Normals also reach at least `reach` px forward, the same for every hit of a route: KOF's boxes are made for one
        # opponent in front, so an enemy standing behind it was only reached by the longer hits and dropped out.
        x, y, w, hh = norm(atk[0])
        if reach:                                       # (the old beat 'em up reach, off since 2026-10-08)
            left, right = min(x - w, -reach), x + w
            if left < 0: right = max(right, 0)
            a = ((left + right) // 2, y, (right - left + 1) // 2, hh)
        else: a = (x, y, w, hh)
    return h, a

THROWS = ['throw_c', 'throw_d']                         # BT_* order: ground throws, close, forward+C / forward+D in KOF
THROW_X = 'throw_x'                                      # revamp phase 3: a fighter's extra paired throw, decoded from its
                                                         # source's command grab (tools/kof96/throwrom.py: KOF98 Ralf's
                                                         # 426B / D): bm_xthr[id].x, fighter.c BT_XTHROW
XT_FWD, XT_PAIRED, XT_NONE = 0xFD, 0xFE, 0xFF            # bxthr_t up / down / sup: the throw pressed (the super: forward /
                                                         # back throw played at the super tier), the paired throw_x, none
# Throw speed (TODO #146 rule 1: no global multiplier): per throw in data, game.json roster[].throws.speed {key: 8.8};
# default 1x for a throw read from the ROM (tools/kof96/throwrom.py: the pilot), the captured scripts (pre-#146, the
# rest of the roster until its pass) keep the pace they had (1.5x, Bruno 2026-10-04)
THROW_SPEED, CAPTURED_THROW_SPEED = 0x100, 0x180
# Hold hits (TODO #146 rule 3): each fighter's own blows in the hold, as paired scripts (bchar_t.holds: HOLDS order):
# the move a hit takes its frames from (game.json roster[].throws.hold {hit, fin}), its startup squeezed to
# HOLD_STARTUP frames (the last two poses before the blow), the blow and its follow-through as the game has them (at
# most HOLD_TAIL frames), the held victim reeling from the blow. Defaults (TODO #166 c): the hit = the fighter's
# fastest-startup close normal (startup = frames before its first active step in the source game, ties in
# HOLD_CANDIDATES order), the finisher = close D. build/hold_hits.json lists every fighter's startups and its choice.
HOLDS = ['hit', 'fin']
HOLD_DEFAULT = {'hit': None, 'fin': 'atk_d_close'}
HOLD_CANDIDATES = ['atk_c_close', 'atk_d_close', 'atk_b_close', 'atk_a_close']
HOLD_LOG = {}
HOLD_STARTUP, HOLD_TAIL, HOLD_DX = 3, 14, 40

# The flash pose (TODO #145, Bruno 2026-10-06; vocabulary fx.super_flash "flash pose"): a fury whose source game has
# no flash step of its own (KOF96 / 98 / 99 furies start with their $FA flash step: they keep it) plays the fighter's
# flash pose during the super flash's freeze, then the fury from its first frame. The pose = a whole animation of the
# source game, by kind (game.json roster[].flash_pose: "taunt" / "charge" / "win" / "intro", or {"anim", "first",
# "last", "head"}; absent = the game's default kind), cut to the freeze length (its last step held when shorter); the
# concentration glow is anchored on the pose's head point (head_point.py on its first step, or "head" [x, y]).
# Per source game: (animation, first step, last step or None[, flags 'fit' / 'voice']), picked on renders of every candidate (2026-10-07).
# 'fit' (TODO #189): the whole animation timed to the freeze (every step's length scaled by freeze / its length, a step
# that rounds to 0 frames dropped) instead of cut. 'voice' (TODO #189): a step that sends one of the fighter's voices in
# the source (voices.json, an 'anim' use of that animation) sends it as the pose shows that step (bfpose_t.voice); the
# other poses stay silent as in 0.0.96 (the charge sound only). SS2's rage (TODO #189, /data/neogeo_dict/samsho2/README.md "The rage-full moment"): when the POW
# gauge fills, every SS2 fighter plays class 0 action 46 = animation 140 (20-93 frames, its shout on an early step):
# the game's own "meter full" animation, the SS2 fighters' default pose.
FLASH_POSES = {
    'kizuna': {'default': 'taunt', 'taunt': (0x21, 0, None)},       # C+D taunt (README: anim 21)
    'samsho2': {'default': 'rage', 'rage': (140, 0, None, 'fit', 'voice'),   # the rage-full animation (TODO #189), timed to the freeze
                'taunt': (88, 0, None),                             # A+C held: posing with the sword (Kuroko: beckons)
                'win': (95, 0, None)},                              # the bow (4 1 2 3 6 unarmed)
    'whp': {'default': 'win', 'win': (0x00, 0, None),               # WHP has no taunt: the win pose (arms raised)
            'intro': (0x26, 0, None)},                              # the intro (arms crossed, scarf)
    'doubledr': {'default': 'charge', 'charge': (81, 0, 5),         # the power-up: anim 81's stance, the flames rising
                 'win': (100, 0, None)},                            # from his feet (steps 0-5, before the dragons)
}
def flk_of(ch):
    """the export's flicker palette (export_ss2.flicker: SS2's second layer, TODO #193): one per fighter, or None"""
    f = ch.get('flicker') or []
    assert len(f) <= 1, f'{len(f)} flicker palettes (bchar_t.flk holds one)'
    return f[0] if f else None
def flash_pose(game, n):
    """the roster fighter n's flash pose: {'anim', 'first', 'last', 'head'} or None (a KOF source: its own flash step)"""
    if game not in FLASH_POSES or not (roster().get(n) or {}).get('fury'): return None   # (no fury: no pose)
    t = FLASH_POSES[game]; v = (roster().get(n) or {}).get('flash_pose') or t['default']
    if isinstance(v, str): a, f, l, *m = t[v]; return {'anim': a, 'first': f, 'last': l, 'head': None, 'fit': 'fit' in m, 'voice': 'voice' in m}
    return {'anim': v['anim'], 'first': v.get('first', 0), 'last': v.get('last'), 'head': v.get('head'), 'fit': bool(v.get('fit')), 'voice': bool(v.get('voice'))}
def flash_extra(game, n):
    """the exporter's extra for the flash pose: {'anims': {'flash': (anim, first, last)}}"""
    fp = flash_pose(game, n)
    return {'anims': {'flash': (fp['anim'], fp['first'], fp['last'])}} if fp else {}
def flash_voices(game, n, fp):
    """{pose step index: voice id (| the fx bit)}: the fighter's voices its source sends on the pose's steps (TODO #189)"""
    out = {}
    for vo in (V.bank(n) if fp['voice'] else []):
        for u in vo['uses']:
            k = u.get('step', -1) - fp['first']
            if u['kind'] == 'anim' and u['slot'] == fp['anim'] and k >= 0 and (fp['last'] is None or u['step'] <= fp['last']):
                out.setdefault(k, vo['id'] | V.fx_bit(n, vo['id']))
    return out
def fpose_steps(ch):
    """the flash pose as [(frame, frames shown, voice)] filling the super flash's freeze: cut to it (its last step fills
    it when shorter), or with 'fit' every step scaled to it (TODO #189); a dropped step's voice goes to the next shown; [] = none"""
    if 'flash' not in ch['anims']: return []
    T, out = json.load(open(GAME_JSON))['super_flash']['freeze'], []
    st, vo = ch['anims']['flash']['steps'], {int(k): v for k, v in (ch.get('flash_voice') or {}).items()}
    if ch.get('flash_fit'):
        tot, cum, b0, carry = sum(s['ticks'] + 1 for s in st), 0, 0, 0
        for i, s in enumerate(st):
            cum += s['ticks'] + 1; b = (cum * T + tot // 2) // tot; carry = carry or vo.get(i, 0)
            if b > b0: out.append((s['frame'], b - b0, carry)); b0, carry = b, 0
        return out
    left = T
    for i, s in enumerate(st):
        k = min(s['ticks'] + 1, left); out.append((s['frame'], k, vo.get(i, 0))); left -= k
        if not left: break
    if left: out[-1] = (out[-1][0], out[-1][1] + left, out[-1][2])
    return out

def played_inputs(n):
    """the KOF inputs a roster fighter plays: its six slots and its fury (game.json roster[]; the fury's MAX version is
    exported with it). KOF's shared effects bank is exported for these only (TODO #214); a slot repointed in the Lab at
    another special of the pool plays it without them"""
    r = roster().get(n) or {}
    sp = r.get('specials') or []
    return {v for v in (sp.values() if isinstance(sp, dict) else sp) if v} | ({r['fury']} if r.get('fury') else set())

def rom_wanted(n):
    """the KOF inputs of a fighter's ROM specials on demand (handlers98.ROM_DEMAND) that export96 reads (rom_more): the
    ones the roster plays (played_inputs, its Blitz, its throws' grab specials, its down attack, form, air specials) and,
    in a Lab build of him (LAB), every unlocked piece (arb_pieces/<f>_ids.json; named_specials puts them in his pool). One
    nothing names is not read: its frames stay out of the normal game (Robert's 6426A / C, 2026-10-10)"""
    r = roster().get(n) or {}
    out = set(played_inputs(n)) | {v for v in (r.get('blitz') or {}).values() if v} | {v for v in (r.get('air_specials') or {}).values() if v}
    t = r.get('throws') or {}
    out |= {v for v in list((t.get('extra') or {}).values()) + [t.get('super')] if isinstance(v, str)}
    out |= {v for v in (r.get('max'), r.get('down_attack'), (r.get('form') or {}).get('transition')) if v}
    if n in LAB:
        import piece_ids
        out |= {p['input'] for p in piece_ids.load(src(n))['pieces'].values() if p['kind'] == 'special' and not p.get('gone')}
    return out

def build(specs, outdir):
    """one export per game (the whole roster of that game at once, so every fighter has the frames of every victim
    posture its teammates' throws use); tiles renumbered into one space"""
    os.makedirs(outdir, exist_ok=True)
    games = {}
    for spec in specs:
        game, name = spec.split(':'); games.setdefault(game, []).append(name)
    chars, c1, c2 = [], bytearray(), bytearray()
    tile_next = TILE_BASE
    def rname(game, bank):                              # the roster's name of a bank fighter (its C names, game.json
        return next((r['name'] for r in roster().values() if r['bank'] == f'{game}:{bank}'), bank)   # key): Double
                                                        # Dragon's Billy Lee is doubledr:billy, roster billy_lee
    def export(game, names, tmp):
        assert not any(n in LAB for n in names) or game in ('kof96', 'kof98', 'kof99'), f'--lab: {names} ({game}: KOF96 / 98 / 99 only)'
        if game == 'kof94':                             # KOF95's engine: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'kof94')); import export94
            return export94.export(names, tmp, only=set(MOVES))
        if game == 'samsho4':                           # Samurai Shodown IV: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'samsho4')); import export_ss4
            return export_ss4.export(names, tmp, only=set(MOVES),
                                     extra={n: {'watch': tuple(roster()[n]['watch'])} for n in names if n in roster()})
        if game == 'samsho2':                           # Samurai Shodown II: its own reader, programs from its handlers
            sys.path.insert(0, os.path.join(HERE, '..', 'samsho2')); import export_ss2
            return export_ss2.export(names, tmp, only=set(MOVES),
                                     extra={n: {'watch': tuple(roster()[n]['watch']), **flash_extra(game, n)} for n in names if n in roster()})
        if game == 'whp':                               # World Heroes Perfect: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'whp')); import export_whp
            return export_whp.export(names, tmp, only=set(MOVES),
                                     extra={n: {'watch': tuple(roster()[n]['watch']), **flash_extra(game, n)} for n in names if n in roster()})
        if game == 'doubledr':                          # Double Dragon (Technos 1995): its own reader, the same layout
            sys.path.insert(0, os.path.join(HERE, '..', 'doubledr')); import export_dd
            return export_dd.export(names, tmp, only=set(MOVES),
                                    extra={n: {'watch': tuple(roster()[rname(game, n)]['watch']), 'scale': roster()[rname(game, n)].get('scale', 1), **flash_extra(game, rname(game, n))}
                                           for n in names if rname(game, n) in roster()})
        if game == 'kizuna':                            # Kizuna Encounter: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'kizuna')); import export_kz
            return export_kz.export(names, tmp, only=set(MOVES),   # (Kim gold: roster[].scale x $CC, moves, anim_specials)
                                    extra={n: {'watch': tuple(roster()[n]['watch']), **flash_extra(game, n),
                                               **{k: roster()[n][k] for k in ('scale', 'moves', 'anim_specials', 'run') if k in roster()[n]}}
                                           for n in names if n in roster()})
        return export96.export(names, tmp, game, only=set(MOVES) | {k for v in SOURCES.values() for k in v} | set(THROWS) | {THROW_X, 'specials'},
                               extra={n: {'watch': tuple(roster()[n]['watch'])} for n in names if n in roster()},
                               shared_fx={n: played_inputs(n) for n in names},   # (only the frames used: TODO #214)
                               anim_specials={n: roster()[n]['anim_specials'] for n in names if roster().get(n, {}).get('anim_specials')},
                               slots={n: {k: int(v[1:], 16) for k, v in roster()[n].get('moves', {}).items()} for n in names if n in roster()},
                               lab={n: LAB[n] for n in names if n in LAB} or None,   # (the Lab build: export96.lab_special)
                               rom_more={n: rom_wanted(n) for n in names})
                                                # (Krauser gold: roster[].anim_specials, export96.anim_special)
    # one block per fighter, packed into the 64K-tile pages largest first, each into the first page with room
    # (2026-10-04): a fighter's tiles share bits 16-19 (bchar_t.tile_hi -> SCB1 attribute), so a fighter must not cross
    # a page; whole game rosters per block left ~4 MB of padding at the page ends and doubled C to 32 MB when the air
    # C+D animations pushed the last tile past 16 MB. A throw's victim offsets come from the thrower's own export, the
    # victim's poses from its own (vposes), so fighters export independently.
    blocks = []                                         # (game, name, export, tmp dir, roster name, tiles kept)
    def one(game, name, tmp, rn):
        ex = export(game, [name], tmp)
        pk, n = PP.pack(name, ex['characters'][name], tmp, MAX_PALS, ex['tiles'], SRC_BASE)   # (TODO #201)
        if pk['packed'] != pk['slots']:              # its palettes folded: the tiles and the export it was read from
            ex['tiles'] = n; json.dump(ex, open(os.path.join(tmp, 'kof95_export.json'), 'w'))
            print(f'{name}: {pk["slots"]} palettes folded into {pk["packed"]} (pal_pack: exact colours, '
                  f'{pk["tiles_added"]} tiles recoloured)', flush=True)
        PACKED[rn] = pk
        assert ex['tiles'] < 0x10000, f'{game}:{name}: {ex["tiles"]} tiles (a fighter must fit one 64K tile page)'
        return ex
    for game, names in games.items():
        for name in names:
            tmp = os.path.join(outdir, f'tmp_{game}_{name}')
            blocks.append((game, name, one(game, name, tmp, rname(game, name)), tmp, rname(game, name), None))
    if ALIAS:                                           # the shell's slot: its source exported again on its own (its
        slot, f = next(iter(ALIAS.items()))             # LAB special, when the Lab build takes its game: only the slot
        game, name = roster()[slot]['bank'].split(':')  # has it, the roster's fighter stays as in every pack)
        if game in ('kof96', 'kof98', 'kof99') and os.path.exists(os.path.join(HERE, 'arb_pieces', f + '.json')):
            LAB[name] = lab_entries(f)
        tmp = os.path.join(outdir, 'tmp_slot')
        ex = one(game, name, tmp, slot); LAB.pop(name, None)
        assert ex['tiles'] <= SLOT_TILES, f'the slot: {f} has {ex["tiles"]} tiles, the shell keeps {SLOT_TILES} (SLOT_TILES)'
        blocks.append((game, name, ex, tmp, slot, SLOT_TILES))
    pages = [[TILE_BASE, []]]                           # per page: next free tile number, [(block, first tile)]
    for blk in sorted(blocks, key=lambda b: -(b[5] or b[2]['tiles'])):   # (the slot: its whole block, whoever fills it)
        n = blk[5] or blk[2]['tiles']
        for p, pg in enumerate(pages):
            start = max(pg[0], (p << 16) + 1)           # tile 0 = empty, and with tile_hi it means page start: blank
            if start + n <= (p + 1) << 16: break
        else:
            pages.append([(len(pages) << 16) + 1, []]); p = len(pages) - 1; pg = pages[p]; start = pg[0]
        pg[1].append((blk, start)); pg[0] = start + n
    slot_at = None
    for p, pg in enumerate(pages):
        for (game, name, ex, tmp, rn, keep), start in pg[1]:
            a = open(os.path.join(tmp, 'kof95_c1.bin'), 'rb').read(); b = open(os.path.join(tmp, 'kof95_c2.bin'), 'rb').read()
            n = ex['tiles']
            if len(c1) // 64 + TILE_BASE < start:       # the gap to this block (page 2's blank tile 0, or a page's end)
                g = start - TILE_BASE - len(c1) // 64; c1 += bytes(g * 64); c2 += bytes(g * 64)
            c1 += a[SRC_BASE * 64:(SRC_BASE + n) * 64]; c2 += b[SRC_BASE * 64:(SRC_BASE + n) * 64]
            if keep:                                    # the slot: its whole block (blank past its tiles)
                c1 += bytes((keep - n) * 64); c2 += bytes((keep - n) * 64); slot_at = (start, keep, n)
            hch, hreg = HP.load(tmp, name)              # the select pose's head point (TODO #157: the cursor's arrow)
            ex['characters'][name]['head'] = HP.head_point(hch, hreg, (roster().get(rn) or {}).get('head'))
            fp = flash_pose(game, rn)                   # the flash pose's head (TODO #145): the glow's anchor
            if fp and 'flash' in hch['anims']:
                bp = (ex['characters'][name].get('flash_pal') or {}).get('index')   # (SS2's rage: the body's palette)
                ex['characters'][name]['flash_head'] = tuple(fp['head']) if fp.get('head') else \
                    HP.head_of(HP.pens(hch, hreg, hch['anims']['flash']['steps'][0]['frame'], bp))
                ex['characters'][name]['flash_fit'] = fp['fit']; ex['characters'][name]['flash_voice'] = flash_voices(game, rn, fp)
                # each pose step's head (TODO #191: the glow follows it as the pose moves, Haohmaru dropping into his
                # stance): the body's parts only when the source names its palette (SS2's rage: flash_pal), else the frame
                ex['characters'][name]['flash_heads'] = {str(s_['frame']): HP.head_of(HP.pens(hch, hreg, s_['frame'], bp))
                                                         for s_ in hch['anims']['flash']['steps']} if not fp.get('head') and bp is not None else {}
            for th in ex['characters'][name].get('throws', {}).values():   # a throw's own-victim rows under the roster's
                if name in th.get('victims', {}) and src(rn) != name:   # name (poses(): Billy Lee = doubledr:billy)
                    th['victims'][src(rn)] = th['victims'].pop(name)
            chars.append((game, rn, ex['characters'][name], start - SRC_BASE))
    tile_next = TILE_BASE + len(c1) // 64
    assert tile_next <= 0x100000, f'{tile_next} tiles: past the 20-bit tile number'
    chars.sort(key=lambda c: len(specs) if c[1] in ALIAS else specs.index(roster()[c[1]]['bank'] if c[1] in roster() else f'{c[0]}:{c[1]}'))   # (the slot: last)   # bm_chars in the command line's order, the order
                                                          # make_hud.py gives the portraits (exports go by game)
    pad = bytearray(TILE_BASE * 64)
    open(os.path.join(outdir, 'bm_c1.bin'), 'wb').write(bytes(pad + c1))
    open(os.path.join(outdir, 'bm_c2.bin'), 'wb').write(bytes(pad + c2))
    if slot_at:                                         # where lab_pack.py finds the slot's tiles
        json.dump({'fighter': ALIAS['slot'], 'id': len(chars) - 1, 'tile_first': slot_at[0], 'tiles_kept': slot_at[1],
                   'tiles_used': slot_at[2], 'tile_hi': slot_at[0] >> 16}, open(os.path.join(outdir, 'slot.json'), 'w'), indent=1)
    write_c(chars, outdir)
    return chars, tile_next

# Specials by role (Bruno 2026-10-03): D = a projectile, forward+D = a move travelling forward (Terry's Burn Knuckle),
# down+D = a rising invincible reversal (dragon punch, Rising Tackle...). Picked from each fighter's captured ground
# specials by what its body does (tools/kof96/specials96.py scripts: per row frame, x forward, height, objects):
# projectile = objects while the body stays put (x <= 45, height <= 10; a capture often ends before the object flies,
# so its travel is no criterion), rush = body forward >= 60 px staying low (height <= 30; scored travel - 2 x height: Terry's Burn
# Knuckle, not his Crack Shoot), rise = height >= 25, scored
# height - travel / 2. Big versions (C / D) first. ROLE_OVERRIDE: KOF input notation per fighter and role.
ROLE_OVERRIDE = {'mai': {'rise': '623D'},       # Mai: [2]8A is a wall-jump dive, not a reversal
                 'terry': {'up': '214D'},        # Crack Shoot
                 'kyo': {'up': '624B'},
                 'goenitz': {'up': '214A'}}      # his 41236 is one wind (Yonokaze) for every button, at another
                                                 # distance per button (60 / 120 / 200 px): D has 41236C. up+D: 214A
                                                 # (Yamidonari, the wind blowing forward: KOF96 hits a standing P2 at
                                                 # 20-80 px, none at 120), not 214C (its boxes are above his head, an
                                                 # anti-air: no hit on a standing P2 at any distance in KOF96, TODO #59)          # Kototsuki You: the run, on contact the grab and the explosion (states
                                                 # 134-140; 'EX 624D' was the same run, captured as a hit, no whiff)
ROLES = ('proj', 'rush', 'rise', 'up', 'df', 'uf')          # D, forward+D, down+D, up+D, down-forward+D, up-forward+D
# fighters whose EX version is another character, not more moves (Bruno 2026-10-05: the regular Rugal, not Omega Rugal,
# whose KOF98 EX specials are captured on c36x): their 'EX ...' specials are not picked
NO_EX = {'rugal'}

SPECIAL_DAMAGE = 8                                     # a special's damage, split over its hits (fighter.c)
R_HEAVY, R_KNOCKDOWN, R_LAUNCH, R_TRIP = 1, 2, 3, 4   # fighter.h R_*: the victim's reaction to a special's hit (its body
                                                       # hits: KOF98's 258 reel / 283-285 blowback / 286 launch, fighter.c
                                                       # kof_react; R_TRIP the brawler's own)
# the ROM specials whose every hit launches (KOF98 286; measured in our emulator, tools/kof96/capture/romspecials98.py close
# traces 2026-10-05: Terry's Rising Tackle 7 hits, Ralf's Bakudan Punch 3, all 286); the others: rom_c's default
ROM_REACT = {('terry', '623C'): R_LAUNCH, ('ralf', '[2]8C'): R_LAUNCH}
IMPACT_ROWS = 4                                        # an impact row without a box of its step: the object's live box
                                                       # (+$90) on it and the next rows (the victim may have moved)

def victim_reaction(rs, i, end):
    """the opponent's reaction in a capture to the impact at row i (rows up to `end`, the next impact): ejected when it
    leaves the ground (height > 8) or enters a knockdown / blowback state (280-399): R_LAUNCH when it flies 48 px or
    higher, else R_KNOCKDOWN; grounded (a hit reel, states 256-279, height 0): R_HEAVY. Held states (400+: Kyo's grab
    lifts the victim) decide nothing. None: no opponent data, or no reaction seen (a guard). 2026-10-05, the victim now
    flies with KOF98's own reaction (fighter.c kof_react): R_LAUNCH = KOF98/99's 286 launch (or a flight of 100 px and
    more: the blowback 283 / 285 peaks at 52), R_TRIP the sweep 276, else R_KNOCKDOWN."""
    seen = [(r[5], r[6]) for r in rs[i + 1:min(end, i + 60)] if len(r) > 6 and r[5] is not None and r[5] < 400]
    if not seen: return None
    top = max(h for st, h in seen)
    if seen[0][0] == 276 or (top <= 8 and any(st == 276 for st, h in seen)): return R_TRIP
    if top > 8 or any(280 <= st < 400 for st, h in seen): return R_LAUNCH if top >= 100 or any(st == 286 for st, h in seen) else R_KNOCKDOWN
    if any(256 <= st < 280 for st, h in seen): return R_HEAVY
    return None

def special_play(sp):
    """a captured special as the brawler plays it. The captures were recorded frame by frame with an opponent, and
    where the move reached it the game's hit-stop is baked in (Bruno 2026-10-04): rule = the game's contact freezes are
    hit markers, never movement. A freeze = a run of rows where P1's hit-stop counter (object +$124 high byte, $FF none)
    counts down to 0 (export96 row_steps; measured in KOF96/98/99: it starts on the row the opponent's life drops) and
    the row repeats the one before (frame, x, height, objects' places; an effect may cycle its frames in place, a row
    whose objects still travel stays). Frozen rows are
    dropped (the brawler's HITSTOP freezes only when its own hit connects); the row before a freeze whose opponent's
    life drops is the impact (mark 'i'; a freeze without damage is a grab catching, Kyo's Kototsuki You): its body box (or the object's) is made live there (the object's live box +$90 when the step has none and no
    object flies), it opens a hit if none is open, and the opponent's reaction after it (victim_reaction) is that hit's
    reaction. Opponent life drops without a freeze = an object's hit: its reaction is the objects' (objreact).
    A grab (a continuation or a contact row) keeps the opponent's place in the capture (x from the fighter, height) per
    row between its first and last hit (carry): the brawler holds its target there. Any other special lets the victim
    react on its own (Bruno 2026-10-05: never stick the victim to the attacker, throws and command grabs aside).
    -> dict like sp (script, row_boxes, row_steps, marks, cont remapped) + react (per row: R_* or None at impacts),
    objreact, stats (freezes, rows removed, impact rows, reactions)."""
    sc = sp['script']; n = len(sc)
    rb = sp.get('row_boxes') or [sp['frame_boxes'].get(r[0], sp['frame_boxes'].get(str(r[0]), {})) for r in sc]
    rs = sp.get('row_steps') or [[None, None, -1]] * n
    marks = list(sp.get('marks') or [''] * n); cont = sp.get('cont', 0)
    fz = [r[3] if len(r) > 3 else 0xFF for r in rs]
    run = [fz[i] != 0xFF and ((i > 0 and fz[i - 1] == fz[i] + 1) or (i + 1 < n and fz[i + 1] == fz[i] - 1)) for i in range(n)]
    starts = [i for i in range(1, n) if run[i] and not run[i - 1]]
    still = lambda a, b: a[:3] == b[:3] and [o[1:3] for o in a[3]] == [o[1:3] for o in b[3]]
    drop = [run[i] and i > 0 and still(sc[i], sc[i - 1]) for i in range(n)]
    # the game's other freezes (Bruno 2026-10-04: Ryo's Ko-Ou Ken holds ~10 frames after its fireball lands, a hit
    # freeze P1's +$124 does not show): KOF96/98/99 show an animation step for its ROM ticks + 1 frames (measured on
    # throws and specials); the frames of a step past ticks + 2 where nothing moves (fighter frame, place, objects)
    # are cut too
    run_key, run_n = None, 0
    for i in range(n):
        key = (rs[i][0], rs[i][1]); run_n = run_n + 1 if key == run_key else 1; run_key = key
        t = rs[i][10] if len(rs[i]) > 10 else None
        if t is not None and rs[i][2] >= 0 and run_n > t + 2 and i > 0 and still(sc[i], sc[i - 1]): drop[i] = True
    life = [r[7] if len(r) > 7 else None for r in rs]
    drops = [k for k in range(1, n) if life[k] is not None and life[k - 1] is not None and life[k] < life[k - 1]]
    if any(v is not None for v in life):               # an impact = a drop of the opponent's life: the row before
        hits = set()                                   # the freeze it starts (KOF96 drops a row into it), else
        for k in drops:                                # the row before the drop (Kyo's explosion: no freeze)
            s0 = next((s_ for s_ in starts if k - 1 <= s_ <= k + 2 or s_ <= k <= s_ + 1), None)
            hits.add((s0 if s0 is not None else k) - 1)
    else: hits = {i - 1 for i in starts}               # no opponent data: every freeze (a freeze without damage is
    hits = sorted(h for h in hits if not cont or h >= cont)   # a grab catching: Kyo's Kototsuki You); with a
                                                       # continuation, the confirming hit is the whiff's own
    objhits = [i for i in hits if sc[i][3] and not boxes(rb[i])[1]]  # an object's hit: the objects' reaction
    impacts = [i for i in hits if i not in objhits]
    react = [None] * n; rb = [dict(b) for b in rb]
    for k, i in enumerate(impacts):
        react[i] = victim_reaction(rs, i, next((j for j in hits if j > i), n))
        marks[i] += 'i'
        if not boxes(rb[i])[1] and not sc[i][3] and len(rs[i]) > 4 and rs[i][4]:
            t, bx, by, bw, bh = rs[i][4]; ram = {f'{0x10 | t if t < 16 else 0x100 | t:02X}': [bx, by, bw, bh]}
            for j in [i] + [j for j in range(i + 1, n) if not drop[j]][:IMPACT_ROWS - 1]:
                if not boxes(rb[j])[1]: rb[j].update(ram)
    if sp.get('react_src'):                            # measured by the source's own capture (Kizuna: export_kz)
        react = [r if r is not None else react[i] for i, r in enumerate(sp['react_src'])]
    objreact = victim_reaction(rs, objhits[0], next((j for j in hits if j > objhits[0]), n)) if objhits else None
    for i in range(n - 1, 0, -1):                       # a dropped row's marks go to the row it repeats
        if drop[i]: marks[i - 1] += marks[i]; marks[i] = ''
    keep = [i for i in range(n) if not drop[i]]
    slide = [None] * n                                 # a reel (R_HEAVY): how far the opponent slid in the capture, px
    for k_, i in enumerate(impacts):                   # forward, to the next hit (at most 30 rows): fighter.c kof_react
        if react[i] != R_HEAVY or len(rs[i]) <= 8 or rs[i][8] is None: continue   # slides it so far (KOF's push-back
        e = min([j for j in hits if j > i] + [i + 30, n - 1])                       # differs by move: Gatling Attack 65
        while e > i and (len(rs[e]) <= 8 or rs[e][8] is None): e -= 1                # px, Vulcan Punch none)
        slide[i] = max(-127, min(127, rs[e][8] - rs[i][8]))
    carry = [None] * n                                 # a grab: the opponent's place between its first and last hit
    grab = bool(cont) or any('c' in mk for mk in marks) or any(len(r) > 5 and r[5] is not None and r[5] >= 400 for r in rs)
    if len(hits) > 1 and grab:
        for i in range(hits[0] + 1, hits[-1] + 1):     # carries its target there (fighter.c)
            if len(rs[i]) > 8 and rs[i][8] is not None:
                carry[i] = (max(-128, min(127, rs[i][8] - sc[i][1])), max(0, min(255, rs[i][6])))
    if sp.get('carry_src'): carry = list(sp['carry_src'])   # the source's victim places (Kizuna's cinematics)
    hitv = sp.get('version') == 'hit' and bool(hits)    # objects that hit nothing while the body landed every hit
    return dict(sp, objects_hit=not hitv or bool(objhits),   # are effects (Burn Knuckle's flames): no box
                script=[sc[i] for i in keep], row_boxes=[rb[i] for i in keep], row_steps=[rs[i] for i in keep],
                marks=[marks[i] for i in keep], react=[react[i] for i in keep], objreact=objreact,
                carry=[carry[i] for i in keep], slide=[slide[i] for i in keep], keep=keep,
                cont=sum(1 for i in keep if i < cont) if cont else 0, **special_parts(sp, keep, n),
                stats={'freezes': len(starts), 'removed': n - len(keep),
                       'contact': (rs[hits[0]][8] - sc[hits[0]][1]) if hits and len(rs[hits[0]]) > 8 and rs[hits[0]][8] is not None else None, 'impacts': [keep.index(i) for i in impacts if i in keep],
                       'reactions': [react[i] for i in impacts]})

def special_parts(sp, keep, n):
    """a special's follow-ups (fighter.c "follow-ups", one mechanism): parts = script row ranges, each going on to its
    `next` part when it ends (None: the move ends); links = {from, to, on: 'hit' | 'input' | 'hit+input', input:
    'again' (the C role the move started with) or a brawler press ([n | f | d | u | df | uf] + A / AB (the special
    button C, the old name kept) / D (the fury); no
    direction = any), window [lo, hi) script rows, at: 'now' | 'end' (when the part ends)}. A source gives them
    (sp['parts'] / sp['links']: Kizuna's multipart moves, export_kz); a KOF hit-confirmed continuation (export96 cont,
    'j' rows) is two parts: a hit on a 'j' row jumps to cont now, a whiff ends there. Rows remapped to the rows played
    (keep: frozen rows dropped)."""
    rm = lambda i: sum(1 for j in keep if j < i)
    parts, links, cont = sp.get('parts'), sp.get('links'), sp.get('cont', 0)
    if not parts and cont:
        js = [i for i, mk in enumerate(sp.get('marks') or []) if 'j' in mk] or [0]
        parts = [{'first': 0, 'end': cont, 'next': None}, {'first': cont, 'end': n, 'next': None}]
        links = [{'from': 0, 'to': 1, 'on': 'hit', 'window': [js[0], js[-1] + 1], 'at': 'now'}]
    bd = {'backdrop': dict(sp['backdrop'], rows=[rm(r) for r in sp['backdrop']['rows']] if sp['backdrop']['rows'][0] != 0xFFFF
                           else sp['backdrop']['rows'])} if sp.get('backdrop') else {}   # (0xFFFF: its program's P_SCREEN, TODO #138)
    if not parts: return {'parts': [], 'links': [], **bd}
    return {**bd, 'parts': [dict(p, first=rm(p['first']), end=rm(p['end'])) for p in parts],
            'links': [dict(l, window=[rm(l['window'][0]), rm(l['window'][1])]) for l in links or []],
            'game_rows': [rm(i) for i in sp.get('game_rows') or [] if i in keep]}

LK_DIRS = {'n': 0, 'f': 1, 'd': 2, 'u': 3, 'df': 4, 'uf': 5}
def link_c(l):
    """(trig, in, dir) of a link (bslink_t): LK_HIT 1 / LK_IN 2, IN_* buttons, the stick as a C role (0xFE the
    move's own, 0xFF any)"""
    trig = (1 if 'hit' in l['on'] else 0) | (2 if 'input' in l['on'] else 0)
    if 'input' not in l['on']: return trig, 0, 0xFF
    s = l['input']
    if s == 'again': return trig, 4, 0xFE                        # IN_C: the special button
    btn = next(b for b in ('AB', 'A', 'B', 'D') if s.endswith(b))
    d = s[:-len(btn)]
    return trig, {'AB': 4, 'A': 1, 'B': 2, 'D': 8}[btn], LK_DIRS[d] if d else 0xFF

def special_rows(sp):
    """per row of a played special (special_play): (hurt, attack, hit bits, damage). Boxes from the step the fighter
    was on in the capture (export96 row_boxes: KOF's live attack box on active steps), else from the frame's boxes in
    the move's animations. Hit bits (bspec_row_t.hit): 1 attack box live, 2 it opens a new hit, 8 contact (a grab's
    reach: no damage), 16 a hit here goes on to the continuation (bspec_t.cont), bits 5-7 the victim's reaction (R_*).
    A new hit opens where an attack box starts a step after an inactive step or after one without KOF's $4000 'same
    hit' flag (the rule of the normals), or at an impact (mark 'i') without a box on the row before; rows without a
    known step: after a row without a box. A hit version (export96 version 'hit': the capture reached the opponent)
    and a hit-confirmed continuation hit where the game did: a run of rows with a box is live only when the game hit
    inside it (impacts 'i', continuation hits 'h'), opening at the run's start and again at each later hit in it, so
    the move hits as many times as it landed at point blank (Terry's Rising Tackle: 7) and an opponent anywhere along
    the box's run is reached (the capture's opponent was pushed along: Ralf's charge hits it 82 px on).
    Reaction: the one measured at an impact inside the hit (special_play), else the last hit of the script ejects
    (R_KNOCKDOWN) and the earlier ones keep the victim on the ground (R_HEAVY). Damage: SPECIAL_DAMAGE split over the
    hits of the move's hit path (with a continuation: one hit to confirm, then the continuation's), the last takes
    the rest."""
    rb = sp['row_boxes']; rs = sp['row_steps']; marks = sp['marks']; react = sp.get('react') or [None] * len(rb)
    cont = sp.get('cont', 0); hitv = sp.get('version') == 'hit' and any('i' in mk for mk in marks)
    grows = set(sp.get('game_rows') or [])           # rows that hit where the game hit (a source's connect parts)
    out, prev_key, prev_act, prev_chain, prev_row = [], None, False, False, False
    rom_new = [False] * len(rb)                          # a hit the ROM opens (its step rule), hit in the capture or not
    for i, r in enumerate(sp['script']):
        hb, ab = boxes(rb[i])
        if (cont and i >= cont) or (hitv and not cont) or i in grows:
            new = ab is not None and ('h' in marks[i] or 'i' in marks[i])
            if rs[i][2] >= 0 and (rs[i][0], rs[i][1]) != prev_key:
                rom_new[i] = ab is not None and not (prev_act and prev_chain); new = new or rom_new[i]
                prev_key, prev_act, prev_chain = (rs[i][0], rs[i][1]), ab is not None, bool(rs[i][2] & 0x4000)
        elif rs[i][2] >= 0:
            key = (rs[i][0], rs[i][1])
            if key != prev_key:
                new = ab is not None and not (prev_act and prev_chain)
                prev_key, prev_act, prev_chain = key, ab is not None, bool(rs[i][2] & 0x4000)
            else: new = False
        else:
            new = ab is not None and not prev_row; prev_key, prev_act, prev_chain = None, ab is not None, False
        if 'i' in marks[i] and ab is not None and not prev_row: new = True
        prev_row = ab is not None
        out.append([hb, ab, (1 if ab else 0) | (2 if new else 0) | (8 if 'c' in marks[i] else 0) | (16 if 'j' in marks[i] else 0), 0])
    game = lambda i: (cont and i >= cont) or (hitv and not cont) or i in grows
    i = 0
    while i < len(out):                                  # a run of boxes is live when the ROM made it live (an active
        if out[i][1] is None or not game(i): i += 1; continue   # step: Ralf's [4]6C first punch, which the capture
        j = i                                            # whiffed: Bruno 2026-10-04 "rely on rom data") or the game hit
        while j < len(out) and out[j][1] is not None and game(j): j += 1   # inside it; it opens at the run's start,
        hits_in = [k for k in range(i, j) if 'h' in marks[k] or 'i' in marks[k]]   # at each ROM step that opens a
        rom = any(rs[k][2] >= 0 for k in range(i, j))    # hit and at each later hit of the game in it
        for k in range(i, j):
            if not hits_in and not rom: out[k][1] = None; out[k][2] &= ~3
            else: out[k][2] = out[k][2] & ~2 | (2 if k == i or k in hits_in[1:] or rom_new[k] else 0)
        i = j
    wins = [i for i, r in enumerate(out) if r[2] & 2]
    for k, w in enumerate(wins):                         # the reaction measured inside this hit, else the default
        end = wins[k + 1] if k + 1 < len(wins) else len(out)
        got = next((react[i] for i in range(w, end) if react[i] is not None and out[i][1] is not None), None)
        rc = got if got is not None else (R_KNOCKDOWN if k == len(wins) - 1 else R_HEAVY)
        out[w][2] |= rc << 5
    if cont:
        pre = [i for i in wins if i < cont and not out[i][2] & 8]
        path = pre[:1] + [i for i in wins if i >= cont]
    else: path = wins
    if sp.get('damage') and wins:                        # the source game's own damage for the whole move (Kizuna's
        each = max(1, sp['damage'] // len(wins))         # desperation moves, in the brawler's life: export_kz FOLLOW
        for i in wins: out[i][3] = each                  # 'damage'), split over its hits, the last takes the rest
        out[wins[-1]][3] = max(1, sp['damage'] - each * (len(wins) - 1))
        return [tuple(r) for r in out]
    if sp.get('parts') and not cont:                     # a source's parts (Kizuna): each part deals the damage of a
        for p in sp['parts']:                            # special, split over its own hits
            ph = [i for i in wins if p['first'] <= i < p['end']]
            if not ph: continue
            each = max(1, SPECIAL_DAMAGE // len(ph))
            for i in ph: out[i][3] = each
            out[ph[-1]][3] = max(1, SPECIAL_DAMAGE - each * (len(ph) - 1))
        return [tuple(r) for r in out]
    if path:
        each = max(1, SPECIAL_DAMAGE // len(path))
        for i in wins: out[i][3] = 0 if out[i][2] & 8 else each
        out[path[-1]][3] = max(1, SPECIAL_DAMAGE - each * (len(path) - 1))
    return [tuple(r) for r in out]

def rise_inv(sp):
    """bspec_t.inv_rows: the rows a special is invincible for when it plays as down+D, the rising reversal (fighter.c
    applies it to that role only): through its last hit row or its apex"""
    hits = [i for i, r in enumerate(special_rows(sp)) if r[1]]
    peak = max(range(len(sp['script'])), key=lambda i: sp['script'][i][2])   # a rising move: to its apex
    return max(hits[-1] + 1 if hits else 0, peak + 1 if sp['script'][peak][2] > 0 else 0) or len(sp['script'])


def special_info(sp, game):
    """a played special's data for the Brawler Lab's Characters tab: input, rows (frames at 1x), the rows that open a hit
    with their damage and the fighter frame there, the first live attack row (body or projectile), invincible rows as
    down+D, its projectile (first flight frame), the continuation row"""
    rows = special_rows(sp)
    hits = [[i, r[3], sp['script'][i][0]] for i, r in enumerate(rows) if r[2] & 2]
    pj = sp['projectiles'][0] if real_projectile(sp) else None
    spawn = sum(1 for i in sp['keep'] if i < pj['spawn_row']) if pj else None
    live = [i for i, r in enumerate(rows) if r[2] & 1]
    first = min([i for i in live] + ([spawn] if pj else [])) if live or pj else None
    sh = special_shape(sp)
    return {'input': sp['input'], 'rows': len(sp['script']), 'hits': hits, 'first': first, 'inv': rise_inv(sp),
            'cont': sp.get('cont', 0), 'proj': None if pj is None else {'row': spawn, 'frame': pj['rows'][0][0], 'kind': pj.get('kind', 0),
                                                                        'travel': round(pj.get('travel') or 0)},
            'pose': sp['script'][spawn if pj else (hits[0][0] if hits else len(sp['script']) // 2)][0],
            'travel': round(sh[0]), 'height': round(sh[1])}


def spec_index(pool, sp):
    """a special's index in its fighter's pool (bchar_t.specials), 0xFF = none"""
    return 0xFF if sp is None else next(k for k, q in enumerate(pool) if q is sp)


def hit_fx(sp, i, game):
    """bspec_row_t.fx of a row opening a hit: KOF98's hit effect the move set in the attacker (captured per row:
    +$1B8 the hit kind, the victim's hit sounds through the table at $1E208; on a fire kind the victim burns in the
    attacker's flame colour, FIRE_COLOUR); rows without it: kind 1, the heavy hit ($13). KOF96 / KOF99
    fighters: their own kind (both games' handler tables, decoded 2026-10-04, number kinds as KOF98's), played with
    KOF98's sounds since the brawler runs KOF98's driver"""
    rs = sp['row_steps'][i]
    eff = rs[9] if len(rs) > 9 and rs[9] else None
    if not eff or not eff[0] or eff[0] > 32: return move_fx(sp.get('fighter'), sp, 1)   # KOF96 / KOF99 number their kinds as KOF98 (same handler
                                                         # tables: 1 heavy hit, 11 hit + fire); KOF99's 33-46: none in KOF98
    return move_fx(sp.get('fighter'), sp, eff[0] & 0x3F)

# Hit sounds by use (TODO #75, Bruno's listening): a fury's hits (roster[].fury, every fighter's C) play $9C SDM IMPACT;
# roster[].hit_sfx sets the sound of a special (its KOF input), a normal's button (A B C D CD: fighter.c hit_sound) or
# a throw (throw_c / throw_d: its impacts) by songs.json sfx name: Haohmaru's sword slashes $2B SLASH, Krauser's back
# breaker $3D BACK BREAK. A special's sound is a KOF98 hit kind (fighter.c HIT_SFX): the kind playing that code alone.
SFX_NAMES = {v: int(k, 16) for k, v in json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'songs.json')))['sfx']['names'].items()}
KIND_OF = {0x9C: 29, 0x19: 15, 0x3D: 16, 0x2B: 20, 0x17: 24, 0x2E: 21}   # HIT_SFX rows {code, 0} ($2E FIRE HIT: Kyo's fury, TODO #206)
KIND_OF.update({SFX_NAMES['94 DRAGON HIT']: 33, SFX_NAMES['94 SUPER HIT']: 34, SFX_NAMES['94 KNUCKLE HIT']: 35})   # Bruno's
# impact-sound picks (2026-10-09, songs.json sfx "from" KOF94): HIT_SFX rows {code, 0xFF}, the code alone (no fire crackle added)
SFX_KEYS = ['A', 'B', 'C', 'D', 'CD', 'throw_c', 'throw_d']    # bchar_t.sfx order (fighter.c SX_*)

def sfx_code(n, name):
    assert name in SFX_NAMES, f'{n}: hit_sfx {name!r} is no songs.json sfx name'
    return SFX_NAMES[name]

def move_fx(n, sp, hk, element=0, state=None):
    """bspec_row_t / bproj_t / P_ANIM fx of a special's hit: kind hk (KOF's), or the sound its use asks for (a fury:
    SDM IMPACT; roster[].hit_sfx[input]); the burn: the hitting animation's element when it has one (a ROM program's
    state / object: handlers98.fire_element, KOF98's own rule, TODO #206: Kyo's Orochinagi hits with kind 7 and burns),
    else the KOF kind's (fire kinds 11, 13, 21: the crackle $2E only they). A hit_sfx entry {"states": [...], "sound": name}
    sets the sound of the hits its ROM program plays in those states only (state: the 'anim' op's; Bruno 2026-10-09: the
    dragon-punch part of Ryo's and Robert's fury), its other hits keep the rules"""
    r = roster().get(n, {}); want = (r.get('hit_sfx') or {}).get(sp['input'])
    if isinstance(want, dict):
        assert set(want) == {'states', 'sound'}, f'{n}: hit_sfx {sp["input"]}: {{"states": [...], "sound": name}}'
        want = want['sound'] if state in want['states'] else None
    kind = KIND_OF[sfx_code(n, want)] if want else 29 if r.get('fury') and sp['input'] in (r['fury'], 'MAX ' + r['fury']) else hk
    fire = hk in (11, 13, 21) or sp['input'] in (r.get('fire') or ())   # roster[].fire: specials whose hits burn though
    burn = H.BURN_OF.get(element) or (FIRE_COLOUR.get(n, 2) if fire else 0)   # their game's kind is not a fire one (TODO #163)
    return kind | burn << 6

def char_sfx(n):
    """bchar_t.sfx: per SFX_KEYS the code roster[].hit_sfx gives (0: KOF's own)"""
    h = roster().get(n, {}).get('hit_sfx') or {}
    return [sfx_code(n, h[k]) if k in h else 0 for k in SFX_KEYS]

# the burn's colour: the attacker's flames (KOF98 VRAM during Kyo's and Iori's Oniyaki hits: the victim's sprites
# leave its own palette for palette $58, orange, with Kyo, $5F, purple, with Iori; both always loaded). Purple = 1,
# orange = 2 (fighter.c BURN_RAMP: TODO #188 b, the burnt victim is drawn with the cycled ramp $F8 / $F9, measured in
# our emulator: Kyo on Terry and Yuri, Billy Kane's 23624C ring on Yuri); every fire user but Iori burns orange (inference: one flame colour per fighter)
FIRE_COLOUR = {'iori': 1}

R_CODE = {'heavy': R_HEAVY, 'knockdown': R_KNOCKDOWN}

MAX_PALS = int(re.search(r'#define MAX_PALS\s+(\d+)', open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'fighter.h')).read()).group(1))

class pal_slots:
    """a fighter's palette slots (TODO #198): the export's palettes its frames use, those with the same colours in every
    colour set as one slot (KOF98 Kyo's effect palette $B81 = his body palette 18: 9 -> 8). `keys` = one export palette
    per slot, in order; `index(p)` = the slot of export palette p. The game loads MAX_PALS slots per fighter (fighter.h):
    a part past them is drawn with the next fighter's colours (Kyo's EX 236A flame, palette 37: Bruno's
    20261007-114149-b3f3), so the export says so. A fighter over it has had its palettes folded before (pal_pack.py,
    TODO #201: Rugal 11 -> 8); one that still does not fit is named with the frames of each palette."""
    def __init__(self, n, used, sets):
        self.keys, self.slot = [], {}
        for k in used:
            same = next((j for j, q in enumerate(self.keys) if all(st[q] == st[k] for st in sets)), None)
            if same is None: self.keys.append(k); same = len(self.keys) - 1
            self.slot[k] = same
        if len(self.keys) > MAX_PALS:
            print(f'{n}: {len(self.keys)} palettes, the game loads {MAX_PALS}: slots {MAX_PALS}+ show other colours', flush=True)
            for k, frs in ((PACKED.get(n) or {}).get('over') or {}).items():
                print(f'  palette {k}: frames {frs}', flush=True)
    def index(self, k): return self.slot[k]
    def __len__(self): return len(self.keys)

FRAME_COLS = {}                                         # per fighter: each exported frame's hardware sprites (bframe_t ncols)
def projectile_c(n, k, pjs, game, sp):
    """C tables of a special's projectiles (export96.projectile_entry, in spawn order): per projectile its flight
    rows, end rows and child (its trail: a bproj_t without boxes), and the array bproj_t {n}_pj{k}[]"""
    fcols = FRAME_COLS[n]
    def pj_cols(pj):                                     # bproj_t cols (TODO #216): its widest frame over its rows, end
        w, seen = 0, set()                               # rows and its child chain (the trail, a boomerang's pole), as
        while pj and id(pj) not in seen:                # main.c pj_scan read them on the spawn's tick (8 effects born
            seen.add(id(pj))                             # at once: 38 raster lines)
            w = max([w] + [fcols[r[0]] for r in pj['rows'] + pj.get('end', []) if 0 <= r[0] < len(fcols)])
            pj = pj.get('child') or (pj['boom']['seg'] if pj.get('boom') else None)
        return w
    def box(b): return '{0, 0, 0, 0}' if b is None else f'{{{sb(b[0])}, {sb(b[1])}, {b[2]}, {b[3]}}}'
    q = lambda v: max(-32768, min(32767, round(v * 8)))   # 1/8 px
    out, defs = [], []
    def one(name, pj, child='0', births=(0, 0, 0), cd=(0, 0), nxt='0'):
        rows = ', '.join(f'{{{f}, {q(x)}, {round(y)}, {box(a[1:] if a else None)}, {box(o)}, {(1 if a else 0) | (2 if o else 0) | (4 if pj.get('rearm') and rest and rest[0] else 0)}, 0}}'
                         for f, x, y, a, o, *rest in pj['rows'])   # flags 4: the row re-arms its hit (object.phase)
        end = ', '.join(f'{{{f}, {q(x)}, {round(y)}}}' for f, x, y in pj.get('end', [])) or '{0, 0, 0}'
        loop = 0xFF if pj['loop'] is None else pj['loop']
        step = pj['rows'][-1][1] - pj['rows'][-2][1] if len(pj['rows']) > 1 else 0   # the flight's per-frame step
        wrap = q(pj['rows'][-1][1] + step - pj['rows'][loop][1]) if pj['loop'] is not None else 0
        if pj.get('wrap') is not None: wrap = q(pj['wrap'])   # its own repeat step (SS2 Hanzo's fire: 160 px a cycle, TODO #193)
        bm = pj.get('boom')                              # spawn.boomerang (kind 4): wrap_x = its speed (1/8 px a frame)
        if bm: wrap = q(bm['speed'])
        hk = pj.get('hit_kind', 1); hk = hk if 0 < hk <= 32 else 1
        fx = move_fx(n, sp, hk, pj.get('element', 0))
        assert len(pj['rows']) < 256 and len(pj.get('end', [])) < 256 and pj.get('spawn_row', 0) < 256, n
        out.append(f'static const bprow_t {name}_r[] = {{{rows}}};\nstatic const bpend_t {name}_e[] = {{{end}}};')
        return (f'{{{len(pj["rows"])}, {loop}, {len(pj.get("end", []))}, {pj.get("kind", 0)}, {pj.get("spawn_row", 0)}, '
                f'{pj["react"] if isinstance(pj.get("react"), int) else R_CODE.get(pj.get("react"), R_KNOCKDOWN)}, {fx}, {int(pj.get("follow") or 0)}, {round(pj.get("spawn_x", 0))}, {round(pj.get("spawn_y", 0))}, '
                f'{wrap}, {name}_r, {name}_e, {child}, {births[0]}, {births[1]}, {births[2]}, {pj.get("sig", 0)}, {q(cd[0])}, {round(cd[1])}, '
                f'{nxt}, {pj.get("phase_hits", 0)}, {pj.get("stop", 0)}, {1 if pj.get("hitnext") else 0}, ' +
                (f'0, {bm["range"]}, {bm["catch"]}, {bm["seg_min"]}, {bm["hover"]}, {bm["held"]}, {bm["segs"]}, {bm["gap"]}, 0, 0'
                 if bm else   # a boomerang's flight (spawn.boomerang)
                 f'{1 if pj.get("away") else 0}, 0, 0, 0, 0, 0, 0, 0, {1 if pj.get("air") else 0}, {1 if pj.get("back") else 0}') +
                                                         # ppad 1: its victims sent away from its thrower (TODO #193); air
                                                         # 1: born in the air (TODO #211, SS2 Hanzo's shuriken); back 1:
                                                         # behind its owner (TODO #214)
                f', {pj_cols(pj)}, {pj.get("vhits", 0)}' + '}')   # cols: its widest frame (main.c depth_sort's block,
                                                         # TODO #216); vhits: a piercing object's hits on each victim
    for j, pj in enumerate(pjs):
        c = pj.get('child'); child, births, cd = '0', (0, 0, 0), (0, 0)
        if pj.get('boom'):                               # a boomerang's pole segments: their bproj_t (kind 5) as its
            sg = pj['boom']['seg']                       # child, placed by it (fighter.c boom_segs), never born as a trail
            out.append(f'static const bproj_t {n}_pj{k}_{j}s = ' + one(f'{n}_pj{k}_{j}s', sg) + ';')
            child, births = f'&{n}_pj{k}_{j}s', (255, 255, 0)
        def child_c(name, c):                            # its trail: born on the parent's frames b0, b1, then every
            b = c['births']; per = b[-1] - b[-2] if len(b) > 1 else 0   # period (Krauser 0, 1, 7, 13..; Iori 11, 23, 35..)
            assert len(b) < 3 or all(b[i + 1] - b[i] == per for i in range(1, len(b) - 1)), (n, b)
            sub = child_c(name + 'c', c['child']) if c.get('child') else ('0', (0, 0, 0), (0, 0))   # its own (Kyo's MAX
            out.append(f'static const bproj_t {name} = ' + one(name, c, *sub) + ';')                # flames, TODO #202)
            return f'&{name}', (b[0], b[1] if len(b) > 1 else 255, per), (c['dx'], c['dy'])
        if c: child, births, cd = child_c(f'{n}_pj{k}_{j}c', c)
        def phase_c(name, ph):                           # its next phase (object.phase): what it becomes on its
            nx_ = phase_c(name + 'n', ph['next']) if ph.get('next') else '0'   # thrower's signal, or at its hit
            out.append(f'static const bproj_t {name} = ' + one(name, ph, nxt=nx_) + ';')   # (hitnext: Kaiser Wave's
            return '&' + name                                                       # chain, TODO #173)
        nxt = phase_c(f'{n}_pj{k}_{j}n', pj['next']) if pj.get('next') else '0'
        defs.append(one(f'{n}_pj{k}_{j}', pj, child, births, cd, nxt))
    out.append(f'static const bproj_t {n}_pj{k}[] = {{' + ', '.join(defs) + '};')
    return '\n'.join(out)

P_OPS = {'anim': 1, 'set': 2, 'mul': 3, 'move': 4, 'fricmove': 5, 'fall': 6, 'nudge': 7, 'dec': 8, 'br': 9, 'resume': 10,
         'resume_at': 11, 'jmp': 12, 'spawn': 13, 'fxoff': 14, 'end': 15, 'adv': 16, 'check': 17, 'part': 18, 'evclr': 19,
         'onhit': 20, 'place': 21, 'hitclr': 22, 'hold': 23, 'unhold': 24, 'sigclr': 25, 'hitoff': 26, 'add': 27, 'vsend': 29,
         'vsig': 30, 'turn': 31, 'vphase': 32, 'screen': 33, 'cine': 35, 'lanim': 36}   # bm_chars.h P_*
P_REGS = {'vx': 0, 'vy': 1, 'g': 2, 'fric': 3, 'cnt': 4, 'h': 5}

def rom_ok(sp):
    return bool(sp.get('rom')) and 'error' not in sp['rom']

def rom_inv(sp):
    """bspec_t.inv_rows of a ROM special (frames): as down+D invincible up to its last hit or its apex"""
    r = sp['rom']; return max(r['last_hit'], r['apex']) + 1 if max(r['last_hit'], r['apex']) >= 0 else r['length']

def vlists_c(n, k, r, game):
    """a catch's victim script (vocabulary hold.victim_list, TODO #173): bvent_t / bvlist_t arrays, KOF's lists
    (handlers98) or SS2's (handlers_ss2.VL: their own flight / release velocities)"""
    out = []
    if r.get('vlists'):                                # a catch's victim script (hold.victim_list, TODO #173)
        def vl_parts(l):                               # a KOF list: its entries; an SS2 list (handlers_ss2.VL): a dict
            if isinstance(l, list): return l, 0, 0, 0, 0   # with its own flight / release velocities (8.8, vy down)
            c = 4 if l.get('catch') else 0             # VL_CATCH (TODO #216): started by P_CATCH only (the cine's list)
            if l.get('fly'): vx, vy, g = l['fly']; return l['e'], 1 | c, vx, -vy, g
            if l.get('rel'): vx, vy, *g = l['rel']; return l['e'], 2 | c, vx, -vy, g[0] if g else 0   # (g: its own fall, KOF's victim routine)
            if l.get('frames'):                        # (TODO #213, Kizuna's command grabs: tools/kizuna/rosa_kz.py)
                return l['e'], 8 | (16 if l.get('sreact') else 0) | (32 if l.get('down') else 0), \
                    SR_BASE[n][l['sreact'] - 1] + 1 if l.get('sreact') else 0, 0, 0   # VL_FRAMES, VL_SREACT (vx = bm_sreact + 1), VL_DOWN
            if l.get('stand'): return l['e'], 64 | c, 0, 0, 0   # VL_STAND (TODO #220): its release leaves the victim standing, held
            return l['e'], c, 0, 0, 0
        for j, l in enumerate(r['vlists']):
            l = vl_parts(l)[0]
            out.append(f'static const bvent_t {n}_sp{k}_ve{j}[] = {{' + ', '.join(
                f'{{{e["dx"]}, {e["dy"]}, {vpose(game, e["state"])}, {(1 if e["flags"] & 1 else 0) | (2 if e["flags"] & 2 else 0) | (4 if e.get("turn") else 0) | (8 if e.get("front") else 0) | (64 if e["flags"] & 64 else 0) | (e.get("burn", 0) << 4)}}}'
                for e in l) + '};')
        out.append(f'static const bvlist_t {n}_sp{k}_vl[] = {{' + ', '.join(
            f'{{{len(e)}, {fl}, {n}_sp{k}_ve{j}, {vx}, {vy}, {g}}}' for j, (e, fl, vx, vy, g) in enumerate(map(vl_parts, r['vlists']))) + ', {0, 0, 0, 0, 0, 0}};')   # (n 0: the end)
    return out

def hspk_rows(k, r):
    """bchar_t.hspk entries of a ROM special k (TODO #215): [k, state index, step, spark code] of its steps with one"""
    out = [(k, j, i, s_['spark']) for j, st in enumerate(r['states']) for i, s_ in enumerate(r['anims'][st]['steps']) if s_.get('spark')]
    assert all(k < 0xFE and j < 256 and i < 256 for k, j, i, _ in out), k
    return out
SREACTS = []                                       # the game's source reactions (bm_sreact, TODO #136): every fighter's
SR_BASE = {}                                       # export 'sreacts' list (write_c), one entry per distinct motion (TODO
                                                   # #213: Rosa's are mostly Kim's, Kizuna's victim code is the same for
                                                   # all): per fighter its list's index -> bm_sreact's (0-based)
def sr_hy(n, v):
    """a source-reaction step's hy (the fighter's sreacts indexes + 1, standing | airborne << 4) in bm_sreact"""
    if not v: return 0
    lo, hi = v & 15, v >> 4
    lo, hi = (SR_BASE[n][lo - 1] + 1 if lo else 0), (SR_BASE[n][hi - 1] + 1 if hi else 0)
    assert lo <= 15 and hi <= 15, (n, 'bm_sreact: more than 15 source reactions')
    return lo | hi << 4

def sreact_c():
    """bm_sreact[] (TODO #136, vocabulary reaction.source_motion): the source reactions as the brawler plays them"""
    fx = lambda v: int(round(v * 65536))
    return ['const bsreact_t bm_sreact[%d] = {' % max(1, len(SREACTS)) + ', '.join(
        f'{{{fx(r["vx"])}, {fx(r["ax"])}, {fx(r["vy"])}, {fx(-r["ay"])}, {fx(r["bvx"])}, {fx(r["bvy"])}, {fx(-r["bay"])}, {r["r"]}, {r["n"]}, '
        f'{0xFF if r["land"] < 0 else r["land"]}, {r["anim"] & 0xFF}}}' for r in SREACTS) + (' {0}' if not SREACTS else '') + '};']

def rom_c(n, k, sp, game, vres=None):
    """a special read from the ROM (tools/kof96/handlers98.export_rom) as C: its animations (bstep_t: flags 1 attack box
    live (KOF $0100, the last box loaded), 2 hurt box, 8 event ($0080), 16 same hit ($4000)), its program (bprim_t), its
    objects (bproj_t, projectile_c). Damage: SPECIAL_DAMAGE split over the hits the whiff model opens; the hits of its
    last hitting state knock down (R_KNOCKDOWN; fighter.c: its last hit only), the earlier ones R_HEAVY, or ROM_REACT's.
    No carry: the victim flies with KOF98's reaction between hits (fighter.c kof_react)"""
    r = sp['rom']; out = []
    vh = (roster().get(n) or {}).get('max_hits') if sp.get('max_of') else None   # game.json roster[].max_hits (Krauser
    if vh:                                             # gold, Bruno 2026-10-09): its MAX's travelling objects pierce,
        assert 2 <= vh <= 4, f'{n}: max_hits {vh} (2-4)'   # vh hits on each victim, re-armed PROJ_REHIT frames after
        for ob in r['objects']:                        # each (bproj_t vhits, fighter.c strike); its victims sent away
            if ob['kind'] == 1: ob.update(vhits=vh, stop=H.PROJ_REHIT, away=1)   # from him (ppad 1: the last hit lands
                                                       # with the wave past the victim's middle)
    def bb(b): return '{0, 0, 0, 0}' if b is None else f'{{{b[0]}, {b[1]}, {b[2]}, {b[3]}}}'
    live = None
    kof = kof_prog(sp, game)                           # KOF96 / 98 / 99: a step's hurt box counts only with its $0200 flag
    for j, st in enumerate(r['states']):               # (TODO #205: the boxes stay loaded across steps, $0200 says the
        a = r['anims'][st]; steps = []                 # step has one; Kyo's EX 421D 774 / 775 / 776 have none: KOF98's
        for s in a['steps']:                           # 11 untouchable frames; tools/kof96/handlers98.react_hurt's rule)
            hb, ab = boxes(s['boxes'])
            fl = s['flags']
            if kof and not fl & 0x200: hb = None
            if ab: live = ab
            ab = live if fl & 0x100 else None
            steps.append(f'{{{s["frame"]}, {s["ticks"]}, {(1 if ab else 0) | (2 if hb else 0) | (8 if fl & 0x80 else 0) | (16 if fl & 0x4000 else 0) | (32 if fl & 0x2000 else 0) | (64 if ab and s.get("catch") else 0) | (128 if ab and s.get("nostop") else 0) | (4 if ab and s.get("noslide") else 0) | (4 if r.get("sreact") and s.get("push") else 0)}, '
                         f'{bb(hb)}, {bb(ab)}, {-s["dx"]}, {(sr_hy(n, s.get("react", 0)) if r.get("sreact") else s.get("react", 0)) if ab else 0}}}')   # hy: KOF's reaction (handlers98.box_react) / a source reaction
        out.append(f'static const bstep_t {n}_sp{k}_a{j}[] = {{' + ', '.join(steps) + '};')
    out.append(f'static const banim_t {n}_sp{k}_an[] = {{' + ', '.join(
        f'{{{len(r["anims"][st]["steps"])}, {1 if r["anims"][st]["mode"] == "hold" else 0}, {n}_sp{k}_a{j}}}' for j, st in enumerate(r['states'])) + '};')
    if r.get('prims'):                               # a program written by its source's exporter (export_dd: the
        hk = r['hit_kind'] if 0 < r['hit_kind'] <= 32 else 1   # variant table, P_ADD / P_FORM): as given, P_ANIM's
        fx = move_fx(n, sp, hk)                      # hit effect filled in
        assert len(r['prims']) < 0x7FFF, (n, sp['input'])
        out.append(f'static const bprim_t {n}_sp{k}_prog[] = {{' + ', '.join(f'{{{a}, {b}, {c}, {fx if d is None else d}}}' for a, b, c, d in r['prims']) + '};')
        vt = r.get('vtable') or {}
        if vt.get('nvar'):
            out.append(f'static const int32_t {n}_sp{k}_vars[] = {{' + ', '.join(str(v) for row in vt['rows'] for v in row) + '};')
        if r['objects']: out.append(projectile_c(n, f'{k}r', r['objects'], game, sp))
        out += vlists_c(n, k, vl_row(n, sp), game)
        # its steps' sounds and spawns (World Heroes Perfect's step commands 4 / 9, export_whp: TODO #147), each row's
        # animation its own entries: bchar_t.pvox / pfx as KOF's $FC / $FA records
        sp['_pvox'] = [(k, j, i, v) for j, st in enumerate(r['states']) for i, s_ in enumerate(r['anims'][st]['steps'])
                       for v in [vres(w) if vres else 0 for w in s_.get('voices', [])] if v]
        sp['_pfx'] = [(k, j, i, o) for j, i, o in r.get('step_fx', [])]
        sp['_hspk'] = hspk_rows(k, r)
        return '\n'.join(out)
    total = sum(r['openings'].values())
    each = max(1, SPECIAL_DAMAGE // total) if total else 0
    hitting = [st for st in r['states'] if r['openings'].get(st)]
    hk = r['hit_kind'] if 0 < r['hit_kind'] <= 32 else 1
    ops = []
    for op in r['ops']:
        c = P_OPS[op[0]]
        if op[0] == 'lanim':                                   # the Lab build's LAB special (export96.lab_special): each
            st = op[2]; o_ = r['openings'].get(st, 0)          # animation's hits as its own animation special "kof":
            ops.append((c, max(1, SPECIAL_DAMAGE // o_) if o_ else 0, R_KNOCKDOWN if o_ else R_HEAVY,   # damage | the
                        op[1] << 8 | move_fx(n, sp, hk, (r.get('elements') or {}).get(st, 0), st)))   # reaction, index << 8 | fx
        elif op[0] == 'anim':
            st = op[2]; react = ROM_REACT.get((n, sp['input'])) or r.get('react') or (R_KNOCKDOWN if hitting and st == hitting[-1] else R_HEAVY)
                                                       # (r react: an animation special's, export96.anim_special)
            ops.append((c, op[1], each | react << 8, move_fx(n, sp, hk, (r.get('elements') or {}).get(st, 0), st)))
        elif op[0] == 'set':
            v = op[2]; reg = P_REGS[op[1]]
            ops.append((c, reg, 0, round(v * 65536) if reg < 3 or reg == 5 else int(v)))   # 5: the height (16.16)
        elif op[0] == 'mul': ops.append((c, 0, 0, op[1]))
        elif op[0] == 'add':                                   # P_ADD a = register += v (the charge counter: cnt)
            reg = P_REGS[op[1]]; ops.append((c, reg, 0, round(op[2] * 65536) if reg < 3 else int(op[2])))
        elif op[0] == 'nudge': ops.append((c, 0, round(op[1]), round(op[2])))
        elif op[0] == 'br': ops.append((c, op[1] | op[2] << 7, -1 if op[3] == 'yield' else op[3], op[4] if len(op) > 4 else 0))
        elif op[0] == 'check': ops.append((c, op[1], {'hl': 1, 'now': 2}[op[2]] if len(op) > 2 else 0, 0))   # b 1: the presses
                                                       # of its hit-stop; 2: none of them (a mash, TODO #220)
        elif op[0] == 'sigclr': ops.append((c, 0, 0, op[1]))
        elif op[0] in ('resume_at', 'jmp'): ops.append((c, 0, op[1], 0))
        elif op[0] == 'onhit': ops.append((c, op[2] if len(op) > 2 else 0, op[1], 0))   # a: the catch's hit-stop (its dead frames - 1)
        elif op[0] == 'cine': ops.append((c, op[2], op[1], op[3]))   # P_CATCH: a dead frames, b the routine, v its victim list
        elif op[0] == 'place': ops.append((c, 0, 0, round(op[1])))
        elif op[0] == 'spawn': ops.append((c, op[1], 0, 0))
        elif op[0] == 'vsend': ops.append((c, vres(op[1]) if vres else 0, op[2], 0))   # P_VOICE: id (0 silent), frames later
        else: ops.append((c, 0, 0, 0))
    assert len(ops) < 255 or r.get('lab'), (n, sp['input'])   # (the LAB special: 4 ops an animation, P_LANIM's 16-bit index)
    out.append(f'static const bprim_t {n}_sp{k}_prog[] = {{' + ', '.join(f'{{{a}, {b}, {c}, {d}}}' for a, b, c, d in ops) + '};')
    if r['objects']: out.append(projectile_c(n, f'{k}r', r['objects'], game, sp))
    out += vlists_c(n, k, vl_row(n, sp), game)
    pv = [(j, i, vres(ix)) for j, st in enumerate(r['states']) for i, s in enumerate(r['anims'][st]['steps'])
          for ix in s.get('voices', [])] if vres else []
    sp['_pvox'] = [(k, j, i, v) for j, i, v in pv if v and j < 256]   # its steps' voices (KOF's $FC records): bchar_t.pvox
                                                       # (byte indices: the LAB special's animations past 255 are silent)
    sp['_pfx'] = [(k, j, i, o) for j, i, o in r.get('step_fx', [])]   # its steps' effects (KOF's $FA records): bchar_t.pfx
    sp['_hspk'] = hspk_rows(k, r)
    assert all(j < 256 and i < 256 for _, j, i, _ in sp['_pvox']), n
    return '\n'.join(out)

def special_shape(sp):
    if sp.get('shape'): return tuple(sp['shape'])        # what the move does on its own (its whiff, export96)
    sc = sp['script'][:sp.get('cont') or None]
    return max(r[1] for r in sc), max(r[2] for r in sc), any(r[3] for r in sc)

def counter_move(sp):
    """a counter / reflector stance (Geese's Atemi-nage, Yamazaki's Bai-gaeshi): its attack boxes catch, they do not
    strike. Measured: in its close-range capture (opponent standing 48 px in front) the move stays in place (<= 10 px)
    with a live attack box and lands no hit. (Inference: KOF's catch boxes are not told apart from strikes by their box
    type or step flags in the data decoded so far.)"""
    return sp.get('game_hits') == 0 and special_shape(sp)[0] <= 10 and any(
        k[0] == '1' for b in sp.get('row_boxes', []) for k in b)

def real_projectile(sp):
    """the special throws a projectile that reaches someone (tools/kof96/projectiles96: an object with a live attack
    box): a travelling one (object kind 1) or an eruption that hit P2 at one of the measured distances"""
    return any(not pj.get('effect') and (pj['kind'] == 1 or any((h.get('hits') or 0) > 0 for h in pj['hits'].values()))
               for pj in sp.get('projectiles', []))

def played_projectiles(sp):
    """the entities a played special spawns (bspec_t.proj, in spawn order): its projectiles when one of them is real
    (real_projectile), then its pinned effects (`effect`: spawn.pinned_effect of a script special, no box: Kizuna's
    Hienzan pillar, TODO #144; they never make the special a projectile one)"""
    return ([pj for pj in sp.get('projectiles', []) if not pj.get('effect')] if real_projectile(sp) else []) + \
        [pj for pj in sp.get('projectiles', []) if pj.get('effect')]

def special_pool(ch, name=None):
    """the specials a role may take: ground specials of the normal condition (an EX-is-another-character fighter's EX
    ones left out); then the fighter's fury (game.json roster[].fury, TODO #71: a KOF DM / SDM, an SS4 rage move; the C
    button, bchar_t.fury) when it is not one of them"""
    out = [sp for sp in ch.get('specials', []) if sp['condition'] == 'normal' and not sp['input'].replace('EX ', '').startswith('air')
           and not sp.get('air') and not (name in NO_EX and sp['input'].startswith('EX '))]
    fury = fury_special(ch, name)
    out = out + [fury] if fury is not None and fury not in out else out
    for _, air in air_specials(ch, name):          # its air specials (a press in a jump, TODO #200 / #221), table order
        out = out + [air] if air not in out else out
    fm = form_special(ch, name)                     # the form link's transition (vocabulary `form`), when it has one
    out = out + [fm] if fm is not None and fm not in out else out
    mx = fury_max_special(ch, name)                 # its MAX version (down+D, TODO #139), when the bank has one
    out = out + [mx] if mx is not None and mx not in out else out
    dn = down_special(ch, name)                     # its down attack (up / down + A at a lying opponent, TODO #218),
    out = out + [dn] if dn is not None and dn not in out else out   # last: the others keep their indices
    for sp in throw_specials(ch, name):             # the grab specials its throws play (revamp 3), when not in it
        out = out + [sp] if sp not in out else out
    for sp in named_specials(ch, name):             # a DM a slot names / an unlocked piece of a Lab build, last
        out = out + [sp] if sp not in out else out
    return out


def named_specials(ch, name):
    """the specials of another condition the pool still takes (Robert's Haoh Shoukou Ken, the first DM unlocked in the
    Workshop, 2026-10-10): the ones the roster's slots name (game.json roster[].specials: a sheet's S- id on a slot,
    arb_compile.py) and, in a Lab build (the fighter carries the LAB special: make LAB_FIGHTER=<f>, the shell's / a pack's
    slot), every unlocked special (arb_pieces/<f>_ids.json S- ids: the TRY blob names them by pool index, chainlab/
    tryit.js). Each read from the ROM (a program); the normal game's pools are unchanged by it"""
    have = ch.get('specials', [])
    want = [w for w in ((roster().get(name) or {}).get('specials') or []) if w]
    if any(sp['input'] == 'LAB' for sp in have):
        import piece_ids
        reg = piece_ids.load(src(name))
        want += [p['input'] for i, p in sorted(reg['pieces'].items()) if p['kind'] == 'special' and not p.get('gone')]
    out = []
    for w in want:
        sp = next((sp for sp in have if sp['input'] == w and rom_ok(sp)), None)
        if sp is not None and sp not in out and sp['condition'] != 'normal': out.append(sp)
    return out


def throw_cfg(name):
    """game.json roster[].throws (speed, front, hold; revamp 3: extra {u, d}, super)"""
    return (roster().get(name) or {}).get('throws') or {} if name in roster() else {}

def throw_specials(ch, name):
    """revamp phase 3 (Bruno 2026-10-08, docs/brawler_feel.md 8h: no command-grab inputs; grab specials become throws): the
    specials of its bank its throws play, from the hold (game.json roster[].throws.extra {u, d}: hold + up / down + A) and
    the super throw (throws.super: hold + forward / back + C with the meter), each read from the ROM (its program catches
    the held victim); 'throw_x' names the paired extra throw instead (THROW_X). In throws order: extra, then super"""
    t = throw_cfg(name); out = []
    for key, inp in list((t.get('extra') or {}).items()) + [('super', t.get('super'))]:
        assert key in ('u', 'd', 'super'), f'{name}: throws.extra key {key!r} (u = hold + up + A, d = hold + down + A)'
        if not inp or inp == THROW_X: continue
        sp = next((sp for sp in ch.get('specials', []) if sp['input'] == inp), None)
        assert sp and rom_ok(sp), f'{name}: throw {inp}: no special read from the ROM in its bank'
        if sp not in out: out.append(sp)
    return out

def xthr_c(ch, n):
    """bm_xthr[id] (bxthr_t): {its throw_x (0 none), up, down (hold + up / down + A), sup (the super throw), 0}: a special's
    index in its pool, XT_PAIRED its throw_x, XT_FWD (sup only) the throw pressed at the super tier, XT_NONE none"""
    t = throw_cfg(n); pool = special_pool(ch, n); has_x = THROW_X in ch.get('throws', {})
    def one(inp, none):
        if not inp: return none
        if inp == THROW_X:
            assert has_x, f'{n}: throws name {THROW_X}, its bank has none (tools/kof96/throwrom.py PILOT)'
            return XT_PAIRED
        return spec_index(pool, next(sp for sp in ch['specials'] if sp['input'] == inp))
    ex = t.get('extra') or {}
    return f'{{{f"&{n}_xthrow" if has_x else "0"}, {one(ex.get("u"), XT_NONE)}, {one(ex.get("d"), XT_NONE)}, {one(t.get("super"), XT_FWD)}, 0}}'


def fury_special(ch, name):
    """the fighter's fury (game.json roster[].fury: its KOF input, any condition; None = none)"""
    want = roster()[name].get('fury') if name in roster() else None
    if not want: return None
    sp = next((sp for sp in ch.get('specials', []) if sp['input'] == want), None)
    assert sp, f'{name}: no fury {want} in its bank'
    return sp


AIR_KEY = re.compile(r'^(dd|)(|f|d|u|df|uf)([AC])$')   # an air_specials key: "dd" (the Blitz's down,down tap in the
AIR_SLOTS = ('', 'f', 'd', 'u', 'df', 'uf')      # jump, any stick at the press) or the stick's slot (the ground's six C
AIR_A = 0x10                                     # slots, BS_D .. BS_UF_D) + the button; bm_chars.h AIR_A: an air table
AIR_DD = 0x20                                    # entry's button A (else C); AIR_DD: down,down + the button (Bruno
                                                 # 2026-10-09, note 20261009-102708-5d29: Kim's j.2B on down,down + A)

def air_specials(ch, name):
    """the fighter's air specials (game.json roster[].air_specials {key: input}, TODO #200 / #221: specials of its bank
    its source plays from a jump, read from the ROM as programs: Kizuna's j.2B / j.2C / j.623C / j.421C, SS2's
    j.4123S): [(key, special)] in the table's order; a press of the key's button with the stick in its slot in a jump
    plays it (fighter.c air_pick, role BS_AIR, bchar_t.air)"""
    want = roster()[name].get('air_specials') if name in roster() else None
    out = []
    for key, inp in (want or {}).items():
        assert AIR_KEY.match(key) and not (key.startswith('dd') and len(key) > 3), f'{name}: air_specials key {key!r} (slot "", f, d, u, df, uf or dd + A or C)'
        sp = next((sp for sp in ch.get('specials', []) if sp['input'] == inp), None)
        assert sp and rom_ok(sp), f'{name}: no air special {inp} read from the ROM in its bank'
        out.append((key, sp))
    return out

def air_table(ch, name):
    """bchar_t.air: [input, special index] per air special, 0xFF ends; input = slot | AIR_A for the A button"""
    pool = special_pool(ch, name); out = []
    for key, sp in air_specials(ch, name):
        m = AIR_KEY.match(key)
        out += [AIR_SLOTS.index(m.group(2)) | (AIR_A if m.group(3) == 'A' else 0) | (AIR_DD if m.group(1) else 0), spec_index(pool, sp)]
    return out + [0xFF]


def down_special(ch, name):
    """the fighter's down attack (game.json roster[].down_attack: an input of its bank, a special its source plays at a
    lying opponent, read from the ROM as a program: Double Dragon's 8 / 2 + button, export_dd 'DOWN 8/2'; TODO #218): up
    / down + A on the ground with an opponent lying in reach (fighter.c, role BS_DOWNATK, bchar_t.down_spec); None = none"""
    want = roster()[name].get('down_attack') if name in roster() else None
    if not want: return None
    sp = next((sp for sp in ch.get('specials', []) if sp['input'] == want), None)
    assert sp and rom_ok(sp), f'{name}: no down attack {want} read from the ROM in its bank'
    return sp


def form_special(ch, name):
    """the form link's transition move (game.json roster[].form.transition: an input of its bank; None = no form)"""
    f = roster()[name].get('form') if name in roster() else None
    if not f: return None
    sp = next((sp for sp in ch.get('specials', []) if sp['input'] == f['transition']), None)
    assert sp, f'{name}: no form transition {f["transition"]} in its bank'
    return sp

FORM_TRIG = {'down+D full meter': 1}                 # bchar_t.form_trig (fighter.c FT_*)
FORM_EXIT = {'life': 1, 'stage': 2, 'never': 3}      # bchar_t.form_exit (fighter.c FX_*)
def form_c(chars, ch, n):
    """bchar_t form_to, form_spec, form_trig, form_exit (docs/brawler_move_vocabulary.md "form"); None: no form"""
    f = roster()[n].get('form')
    if not f: return None
    names = [q[1] for q in chars]
    assert f['target'] in names, f'{n}: form target {f["target"]} is not in the roster'
    assert set(f.get('carry', [])) <= {'life', 'position', 'facing', 'meter'}, (n, f.get('carry'))
    return (names.index(f['target']), spec_index(special_pool(ch, n), form_special(ch, n)), FORM_TRIG[f['trigger']], FORM_EXIT[f['exit']])

def fury_max_special(ch, name):
    """the fury's MAX version (export96: 'MAX <fury input>', the handler's +$E4 bit 0 path with the fury's own button;
    down+D, TODO #139); else the same command's MAX on another button when that one is read from the ROM (TODO #152: a
    fury whose own button has no MAX in the bank; never a captured MAX: no recorded specials); None = none (down+D
    plays the fury)"""
    want = roster()[name].get('fury') if name in roster() else None
    if not want: return None
    sps = ch.get('specials', [])
    mx = roster()[name].get('max')                  # game.json roster[].max (TODO #212): a source without KOF's MAX
    if mx:                                          # level names its down+D fury itself (Double Dragon's Cheng-Fu:
        sp = next((sp for sp in sps if sp['input'] == mx), None)   # two supers, the 623 one the bigger)
        assert sp and rom_ok(sp), f'{name}: no max {mx} read from the ROM in its bank'
        return sp
    return next((sp for sp in sps if sp['input'] == 'MAX ' + want and sp.get('rom')), None) or \
        next((sp for sp in sps if sp['input'] == 'MAX ' + want), None) or \
        next((sp for b in 'ABCD' for sp in sps if want[-1] in 'ABCD' and sp['input'] == 'MAX ' + want[:-1] + b and sp.get('rom')), None)


def dedupe_c(text):
    """identical static const tables written once (a MAX fury's script and projectiles are its DM's, TODO #139: bm_spec.c
    lives in the first program MB): a later one-line definition with the same type and body as an earlier one is
    dropped and its name replaced by the first's in what follows"""
    import re
    rx = re.compile(r'^static const (\w+) (\w+)(\[\d*\]) = (.*);$')
    seen, ren, out = {}, {}, []
    word = re.compile(r'\b\w+\b')
    for line in text.split('\n'):
        if ren: line = word.sub(lambda mt: ren.get(mt.group(0), mt.group(0)), line)
        mt = rx.match(line)
        if mt and mt.group(4) != '{}' and not mt.group(2).startswith('slot_'):   # (the shell's slot: its own tables only)               # (an empty table keeps its own place: a player that reads a
            key = (mt.group(1), mt.group(3), mt.group(4))   # 0-row object's row 0 reads what follows it, as before)
            if key in seen: ren[mt.group(2)] = seen[key]; continue
            seen[key] = mt.group(2)
        out.append(line)
    return '\n'.join(out)


def step_voiced(sp):
    """a program written by its source's exporter whose steps carry their sound records (export_whp, TODO #147)"""
    return prog_only(sp) and any(s_.get('voices') for a in sp['rom']['anims'].values() for s_ in a['steps'])

def prog_only(sp):
    """a program written by its source's exporter (export_dd 'prims'): the script rows are the Brawler Lab's data only
    (chainlab.json), never played (no capture behind them to fall back to): the ROM keeps one row (bspec_t.nrows 1:
    special_pick's 'has a special'), the first program MB is full"""
    return rom_ok(sp) and bool(sp['rom'].get('prims'))

def vdef_of(n, sp):
    """the variant row a ROM special plays: game.json roster[].variant[input] (a button letter / strength / index), else
    the source's default (the heaviest)"""
    vt = sp['rom']['vtable']
    want = (roster().get(n, {}).get('variant') or {}).get(sp['input'])
    names = vt['buttons'] if not isinstance(want, str) or want in vt['buttons'] else vt.get('strengths') or vt['buttons']   # a button letter, or a
    vdef = names.index(want) if isinstance(want, str) else want if want is not None else vt['default']   # strength (low / mid / high: WHP)
    assert 0 <= vdef < vt['nvar'], (n, sp['input'], want)
    return vdef

def vl_row(n, sp):
    """the special's ROM data with the victim lists of the row it plays (handlers_ss2: vlists_rows when its rows' victims
    fly differently, Hanzo's Mozu Otoshi, TODO #193)"""
    r = sp['rom']
    return dict(r, vlists=r['vlists_rows'][vdef_of(n, sp)]) if r.get('vlists_rows') else r

def var_c(n, k, sp):
    """bspec_t vars, nvar, vdef, vanim, vobj, vcols, vdmg, pvoice (vocabulary `variant.parameter_set`): a ROM special's
    parameter rows (export_dd vtable: one row per button), the row played (game.json roster[].variant[input], else the
    source's default: the heaviest), the program's animations / objects per row, the columns, the damage column + 1 (0
    none); pvoice 1: its voices are timed by its frames. Absent (a special without them): all zero"""
    r = sp.get('rom') or {}; vt = r.get('vtable') or {}
    if not vt.get('nvar') and not r.get('voice_frames'): return ''
    if not vt.get('nvar'): return ', 0, 0, 0, 0, 0, 0, 0, 1'
    vdef = vdef_of(n, sp)
    return f', {n}_sp{k}_vars, {vt["nvar"]}, {vdef}, {vt["vanim"]}, {vt["vobj"]}, {vt["ncol"]}, {vt["vdmg"]}, {1 if r.get("voice_frames") else 0}'

def vl_c(n, k, sp):
    """var_c's fields, then bspec_t.sflags and vlists when the special has a victim script (TODO #173) or flags"""
    v = var_c(n, k, sp)
    vl = rom_ok(sp) and sp['rom'].get('vlists'); fl = (1 if (rom_ok(sp) and sp['rom'].get('nopush')) or sp['input'] in roster().get(n, {}).get('nopush', ()) else 0) | (2 if rom_ok(sp) and sp['rom'].get('bighit') else 0) | (4 if rom_ok(sp) and sp['rom'].get('now') else 0) | (8 if rom_ok(sp) and sp['rom'].get('sharepush') else 0) | \
         (16 if sp['input'] in roster().get(n, {}).get('invincible', ()) else 0) | \
         (32 if rom_ok(sp) and sp['rom'].get('sreact') else 0)   # SF_INV (TODO #202), SF_SREACT (TODO #136)
    if not vl and not fl: return v
    return (v or ', 0, 0, 0, 0, 0, 0, 0, 0') + f', {fl}, ' + (f'{n}_sp{k}_vl' if vl else '0')   # (sflags, then the lists)

PKEYS = []                                         # the victim postures (poses(): VP_* order), set by write_c
def vpose(game, state):
    """a KOF victim state's posture index (its step 0; VP_*), 0xFF: none (the victim keeps its reel); a key with its
    step ('anim.step': SS2's victim lists) as it is"""
    v = vocab(game, state if '.' in str(state) else f'{state}.0')
    return PKEYS.index(v) if v in PKEYS else 0xFF

def flash_c(sp):
    """bspec_t sf_dx, sf_dy, sf_anchor: the super flash's anchor when the move has one (fx.super_flash is an engine
    rule, game.json super_flash; the only per-move datum is this optional anchor): the offset its KOF animation's $FA
    command gives the concentration (handlers98.super_flash: px from the fighter, KOF orientation); 0, 0, 0 = none
    (the game-wide anchor)"""
    f = sp.get('flash') or (sp.get('rom') or {}).get('flash')
    return (f['dx'], f['dy'], 1) if f else (0, 0, 0)


def pick_specials(ch, name):
    """[D, forward+D, down+D, up+D, down-forward+D, up-forward+D] as the roster says (game.json roster[].specials: KOF inputs; None = no special)"""
    out = []
    for role, want in zip(ROLES, roster()[name]['specials']):
        sp = next((sp for sp in special_pool(ch, name) if sp['input'] == want), None) if want else None
        assert sp or not want, f'{name}: no special {want} for {role}'
        out.append(sp)
    return out


def suggest_specials(ch, name=None):
    """[projectile, rush, rise, up] (None where the fighter has no such move): the automatic pick that filled game.json's
    specials (2026-10-05), for the lab to suggest. The big versions first (C / D: Bruno
    2026-10-03, the long Burn Knuckle, the high dragon punch); up+D = the best special of a move not used yet (one move
    = its input motion with the punch or kick pair: 214A / 214C is one move, 214B / 214D another). A KOF98 fighter and
    its EX version are one fighter (Bruno 2026-10-04: same normals, the EX adds specials): the pool is both versions'
    specials ('EX ...' inputs, captured on the EX state c<id>x). D = the fighter's real projectile (real_projectile): a
    travelling one first (EX Terry's Power Wave over his Round Wave eruption), big button first, the longest travel.
    down-forward+D / up-forward+D (Bruno 2026-10-05, the two slots added to the four): the best special of a move the
    roster's four slots (game.json) and the slot before do not use (one move = its motion and the punch or kick pair, EX
    or not; Samurai Shodown's A / B / C are one slash; a projectile of another kind is another move: EX Terry's 236C
    Power Wave travels, his 236C Round Wave erupts): down-forward+D a second projectile first, then an anti-air (rise),
    then a command move (any other); up-forward+D an anti-air first, then a projectile, then a command move; only moves
    that hit the standing opponent in KOF's close-range capture (game_hits not 0: a special out of a hold connects)."""
    c = special_pool(ch, name)
    can_hit = lambda sp: real_projectile(sp) or any(k[0] == '1' and k.upper() != '1B' for b in sp.get('row_boxes', []) for k in b)
    auto = [sp for sp in c if not sp['input'].split()[0] in ('MAX', 'Counter') and sp['condition'] == 'normal' and not counter_move(sp) and can_hit(sp)]
    # supers: by override only; a move that can hit nothing (no attack box, no projectile: K''s 236D, whose object never
    # hits in KOF99 either; Orochi Yashiro's EX 214C) is not picked
    big = lambda sp: sp['input'][-1:] in ('C', 'D')
    move = lambda sp: (sp['input'].replace('EX ', '').rstrip('ABCD'), sp['input'][-1:] in ('A', 'C'))
    out = []
    for role in ROLES:
        want = ROLE_OVERRIDE.get(name, {}).get(role)
        pick = next((sp for sp in c if sp['input'] == want), None) if want else None
        if pick is None:
            c_all, c = c, [sp for sp in auto if sp not in out]
            if role == 'proj':
                cand = [((sp['projectiles'][0]['kind'] != 1, not big(sp), -sp['projectiles'][0]['travel']), sp) for sp in c if real_projectile(sp)]
                cand.sort(key=lambda t: t[0])
                pick = cand[0][1] if cand else None
                c = c_all; out.append(pick); continue
            elif role == 'rush': cand = [(special_shape(sp)[0] - 2 * special_shape(sp)[1], sp) for sp in c if special_shape(sp)[0] >= 60 and special_shape(sp)[1] <= 30 and not real_projectile(sp)]
            elif role == 'rise': cand = [(special_shape(sp)[1] - special_shape(sp)[0] / 2, sp) for sp in c if special_shape(sp)[1] >= 25]
            elif role in ('df', 'uf'):
                ss = name in roster() and roster()[name]['bank'].startswith('samsho')   # A / B / C: one slash, three strengths
                mv = lambda sp: (sp['input'].replace('EX ', '').rstrip('ABCD'), ss or sp['input'][-1:] in ('A', 'C'))
                pk = lambda sp: sp['projectiles'][0]['kind'] if real_projectile(sp) else None
                same = lambda a, b: mv(a) == mv(b) and not (pk(a) and pk(b) and pk(a) != pk(b))   # two projectiles of
                                                                 # another kind: two moves (EX Terry's Power Wave / Round Wave)
                mapped = [sp for sp in (pick_specials(ch, name)[:4] if name in roster() else out[:4]) + out[4:] if sp]
                twin = {sp['input']: sp for sp in c_all}
                gh = lambda sp: sp.get('game_hits') if (sp.get('game_hits') or 0) >= 0 or sp['input'].replace('EX ', '') not in twin \
                    else twin[sp['input'].replace('EX ', '')].get('game_hits')   # an EX move not captured: its twin's
                c = [sp for sp in auto if not any(same(sp, m) for m in mapped) and gh(sp) != 0]   # a whiff on KOF's
                                                                 # close-range standing opponent: no (a hold's special)
                kind = lambda sp: 0 if real_projectile(sp) else 1 if special_shape(sp)[1] >= 25 else 2   # proj, rise, command
                rank = {'df': (0, 1, 2), 'uf': (1, 0, 2)}[role]
                cand = [(-rank.index(kind(sp)), sp) for sp in c]
            else:
                used = {move(sp) for sp in out if sp}
                cand = [(0, sp) for sp in c if move(sp) not in used]
            cand.sort(key=lambda t: (-t[0], not big(t[1])) if role in ('df', 'uf') else (not big(t[1]), -t[0]))
            pick = cand[0][1] if cand else None
            c = c_all
        out.append(pick)
    return out

# Throw impacts (Bruno 2026-10-03): the moment a throw's blow lands (Terry's punch, Ralf's headbutt), else the moment the
# victim touches the ground. From the victim's KOF states in the captured script (KOF96-99 numbering): a strike = the
# victim entering a hit reaction (416-418, 426, 427) or a launch (283) straight from being held (424, 425, 432, 433) or
# from the previous blow (multi-hit throws: one impact per blow); no strike = the first ground touch after it was in the
# air (height back to 0, or state 309, the floor bounce).
HELD = {424, 425, 432, 433}
STRIKE = {416, 417, 418, 426, 427}

def throw_impacts(rows, game):
    if game not in ('kof96', 'kof97', 'kof98', 'kof99', 'kizuna'): return []
    st = lambda r: int(r[5].split('.')[0]) if r[5] and game != 'kizuna' else -1   # Kizuna (Kim's toss): the landing only
    out = []; prev = None
    for i, r in enumerate(rows):
        s = st(r)
        if prev is not None and s != prev and prev in HELD | STRIKE and (s in STRIKE or (s == 283 and prev in HELD)):
            out.append(i)
        prev = s
    if out: return out
    air = False
    for i, r in enumerate(rows):
        if r[2] >= 16: air = True
        if air and (r[2] <= 0 or st(r) == 309): return [i]
    return []

THROW_FLIGHT = 380                                     # victim states below: off the throw list (KOF96-99's list poses are 385+)

def throw_rows(game, n, th, pkeys, front=None):
    """a throw's paired script rows (C initializers) and its points: ret (control return), rel (release), land. A throw
    read from the ROM (tools/kof96/throwrom.py) brings them decoded, its flight states as the brawler's knockdown
    animations by their place in the flight code (rows[6]; a posture of the vocabulary when the state has one); a
    captured one (pre-#146) ends where it ended (ret = its last row) and gets rel / land from its rows: the first row
    off the throw list after one on it, the first floor touch after that (the thrown-body rule is the engine's, for every
    throw). front: [first, end) rows the victim is drawn in front of the thrower (a data override; else behind)"""
    rows = th['victims'].get(src(n)) or next(iter(th['victims'].values()))   # offsets of the mirror match (see README)
    froze = set(th.get('impacts') or []) if not th.get('rom') else set()   # KOF froze there (Ryo's forward+C): the brawler's hit-stop too
    imp = set(throw_impacts(rows, game)) | froze          # blows / floor touches: damage, no freeze (KOF's)
    if th.get('rom'): imp = set(th['impacts']) | ({th['land']} if th.get('land') is not None else set())
    st = lambda r: int(r[5].split('.')[0]) if r[5] and game != 'kizuna' else -1
    if th.get('rom'): rel, land, ret = th['release'], th['land'], th['ret']
    else:
        rel = next((i for i in range(1, len(rows)) if 0 <= st(rows[i]) < THROW_FLIGHT and st(rows[i - 1]) >= THROW_FLIGHT), None)
        land = next((i for i in range(rel + 1, len(rows)) if rows[i][2] + th['timeline'][min(i, len(th['timeline']) - 1)][2] <= 0), None) if rel is not None else None
        ret = len(th['timeline'])
    if th.get('rom') and th.get('body'): rel, land = th['body']   # a second release (Ralf's 426B slam): the body from it
    nrows = max(len(th['timeline']), len(rows)) if th.get('rom') else len(th['timeline'])
    out = []
    for i in range(nrows):
        tf, tx, ty, *turned = th['timeline'][min(i, len(th['timeline']) - 1)]
        r = rows[min(i, len(rows) - 1)]
        vf, vx, vy, same, _front, key = r[:6]
        role = r[6] if len(r) > 6 else None
        v = vocab(game, key); fl = 0
        if role and not (v in pkeys and vf is not None and vf >= 0): vp = MOVES.index(role); fl = 32   # its flight: a BA_* animation
        else: vp = pkeys.index(v) if vf is not None and vf >= 0 and v in pkeys else 255
        fl |= same | (2 if front and front[0] <= i < front[1] else 0) | (4 if i in imp else 0) | (8 if turned and turned[0] else 0) | (16 if i in froze else 0)
        out.append(f'{{{tf if tf is not None and tf >= 0 else 0}, {tx}, {ty}, {vp}, {fl}, {vx}, {vy}}}')
    nn = lambda x: 0xFFFF if x is None else x
    return out, {'ret': min(ret, nrows), 'rel': nn(rel), 'land': nn(land)}

# The throw-start effect (fx.throw_start, TODO #166 a): every throw shows KOF96/98's effect (state 61 of the shared
# effects bank, make_sparks.py build_flash -> throwfx.h) with its sound, on the row and at the offset its own
# animation's $FA command gives (tools/kof96/throwrom.throw_fx: Terry's forward+C / D row 3, 40 px forward, 78 up); a
# throw without one (Geese's back throw, the non-KOF fighters') takes its other throw's, else THROW_FX_DEFAULT (Terry's)
THROW_FX_DEFAULT = {'row': 3, 'dx': 40, 'dy': 78}
def throw_fx_of(ch, t):
    own = (ch.get('throws', {}).get(t) or {}).get('fx')
    if own: return own
    other = next((th.get('fx') for k, th in ch.get('throws', {}).items() if k in THROWS and th.get('fx')), None)
    return other or THROW_FX_DEFAULT

def active_step(steps):
    """a normal's first active step (the normals' rule: $0100 with an attack box loaded), None = none"""
    live = None
    for j, s_ in enumerate(steps):
        ab = boxes(s_['boxes'], REACH)[1]
        if ab: live = ab
        if live and s_.get('flags', 0) & 0x100: return j
    return None

def startup(ch, move):
    """frames before a normal's first active step in its source game (steps show ticks + 1 frames), None = no such
    move / never active"""
    if not any(k in ch['anims'] for k in SOURCES.get(move, [move])): return None
    steps = source(ch, move)['steps']; act = active_step(steps)
    return None if act is None else sum(s_['ticks'] + 1 for s_ in steps[:act])

def hold_move(ch, n, tdata, k):
    """the move hold hit k plays: game.json's choice, else (the hit) the fastest-startup close normal"""
    st = {m: startup(ch, m) for m in HOLD_CANDIDATES + ['cmd_df_c', 'cmd_df_d', 'cmd_fwd_a', 'cmd_fwd_b']}
    want = (tdata.get('hold') or {}).get(k)
    if want is None: want = HOLD_DEFAULT[k]
    how = 'game.json' if (tdata.get('hold') or {}).get(k) else 'default'
    if want is None:
        c = [(st[m], i, m) for i, m in enumerate(HOLD_CANDIDATES) if st[m] is not None]
        want = min(c)[2] if c else 'atk_c_close'; how = 'fastest close normal'
    HOLD_LOG.setdefault(n, {'startups': {m: v for m, v in st.items() if v is not None}})[k] = {'move': want, 'why': how}
    return want

def hold_rows(ch, n, game, k, move, pkeys, dx=None, startup=None, multi=False):
    """a hold hit (k 'hit', or 'fin' the finisher) as a paired script: the fighter's own `move` (a normal, its frames),
    its startup squeezed to HOLD_STARTUP frames (the last poses before the active step, 1 + 2 frames), the active step
    (impact on its first frame) and what follows, at most HOLD_TAIL frames; the victim held in the throw's grab pose
    (forward+C row 0) until the blow, then reeling (BA_HIT_STAND_LIGHT; the finisher knocks it down: fighter.c), dx px
    in front (game.json roster[].throws.hold.dx; default the throw's row 0, at most HOLD_DX: in contact, Final Fight);
    the first row's victim is also the hold's own pose (fighter.c grab). multi (game.json roster[].throws.hold.multi
    [k, ...]): every hit of the move is an impact (each active step after the first: $0100 with an attack box, the
    normals' rule), the tail kept to the last one; the finisher's victim reels at each and is knocked down only at the
    last (fighter.c victim_rows: Kim's $6E, two kicks, Bruno 20261009-011518-5d29)"""
    dx = HOLD_DX if dx is None else dx
    su = HOLD_STARTUP if startup is None else startup   # game.json roster[].throws.hold.startup {k: frames} (Terry's hit: 2)
    a = source(ch, move); steps = a['steps']
    act = active_step(steps)
    hstep = act if act is not None else 0xFF
    if act is None: act = min(len(steps) - 1, 1)
    pre = [(steps[act - 2]['frame'], 1)] if act >= 2 and su >= 2 else []
    pre += [(steps[act - 1]['frame'], su - len(pre))] if act >= 1 and su > len(pre) else []
    post = [(s_['frame'], s_['ticks'] + 1) for s_ in steps[act:]]
    hits = [0]                                          # the impacts: frames after the blow's first (multi: every hit)
    if multi and hstep != 0xFF:
        t = 0
        for j, s_ in enumerate(steps[act:]):
            if j and s_.get('flags', 0) & 0x100 and boxes(s_['boxes'], REACH)[1]: hits.append(t)
            t += s_['ticks'] + 1
    tail = max(HOLD_TAIL, hits[-1] + 1)
    th = ch.get('throws', {}).get('throw_c')
    if th:
        r0 = (th['victims'].get(src(n)) or next(iter(th['victims'].values())))[0]
        v = vocab(game, r0[5]); held = (pkeys.index(v) if r0[0] is not None and r0[0] >= 0 and v in pkeys else 255, min(r0[1], dx), r0[2], r0[3])
        if th.get('grab_frame') is not None:            # SS2's turned grab (TODO #188 a): the hold is its picture mirrored,
            held = (held[0], min(-r0[1], dx), r0[2], r0[3] ^ 1)   # the victim in front facing him (bthrow_t.gframe)
    else: held = (255, dx, 0, 0)
    rows = []
    for fr, d in pre:
        for _ in range(d): rows.append(f'{{{fr}, 0, 0, {held[0]}, {held[3]}, {held[1]}, {held[2]}}}')
    hit = len(rows)
    for fr, d in post:
        for _ in range(d):
            if len(rows) - hit >= tail: break
            first = len(rows) - hit in hits
            rows.append(f'{{{fr}, 0, 0, {MOVES.index("hit_stand_light")}, {32 | held[3] | (4 if first else 0)}, {held[1]}, {held[2]}}}')
    return rows, (MOVES.index(move) if move in MOVES else 0xFF, hstep)

VICTIM_POSES = {g: json.load(open(os.path.join(HERE, '..', 'kof96', f'victim_poses{g[3:]}.json')))['poses']
                for g in ('kof96', 'kof98', 'kof99')}
VICTIM_POSES['kizuna'] = json.load(open(os.path.join(HERE, '..', 'kizuna', 'victim_poses_kz.json')))['poses']   # Kim's throw
VICTIM_POSES['whp'] = json.load(open(os.path.join(HERE, '..', 'whp', 'victim_poses_whp.json')))['poses']   # Hanzou's throws (TODO whp6)
VICTIM_POSES['samsho2'] = json.load(open(os.path.join(HERE, '..', 'samsho2', 'victim_poses_ss2.json')))['poses']   # SS2's throws
VICTIM_POSES['doubledr'] = json.load(open(os.path.join(HERE, '..', 'doubledr', 'victim_poses_dd.json')))['poses']   # Billy Lee's throws (TODO #194)

FAMILY = {'grabbed': 'standing', 'hunched': 'standing', 'hit_reel': 'standing', 'bent_back': 'standing', 'standing': 'standing',
          'launched': 'air', 'horizontal': 'air', 'curled': 'air',
          'falling': 'head_down', 'inverted': 'head_down', 'inverted_diagonal': 'head_down', 'lying': 'floor'}

FALLBACK_MOVE = {'standing': 'hit_stand_heavy', 'air': 'blowback', 'head_down': 'knockdown_fall', 'floor': 'down'}

def vocab(game, key):
    """a victim 'state.step' of a game -> its portable posture name 'posture:angle' (tools/kof96/victim_poses*.json):
    state numbers differ between games (KOF99 re-uses 432 for a launched pose, a grabbed one in KOF98), postures don't"""
    p = VICTIM_POSES[game].get(key)
    return f'{p[0]}:{p[1]}' if p else None

def poses(chars):
    """victim postures (portable names) used by any throw, and each fighter's frame for them, taken from the throws of
    its own game that have it as the victim. A posture it has no frame for takes its frame for the same posture at the
    nearest angle, else the nearest angle of the same family (FAMILY), else the family's brawler animation
    (FALLBACK_MOVE: heavy hit, blowback, knockdown fall, down)."""
    keys = sorted({vocab(g, r[5]) for g, _, ch, _ in chars for t in ch.get('throws', {}).values()
                   for rows in t['victims'].values() for r in rows if r[0] >= 0 and vocab(g, r[5])})
    table = {}
    for gv, n, chv, _ in chars:
        m = {}
        for g, _, ch, _ in chars:
            if g != gv: continue
            for t in ch.get('throws', {}).values():
                for r in t['victims'].get(src(n), []):
                    v = vocab(g, r[5])
                    if r[0] >= 0 and v: m.setdefault(v, r[0])
        row = []
        for k in keys:
            if k in m: row.append(m[k]); continue
            post, ang = k.rsplit(':', 1)
            near = [(abs(int(a) - int(ang)), f) for v, f in m.items() for p_, a in [v.rsplit(':', 1)] if p_ == post] or \
                   [(abs(int(a) - int(ang)), f) for v, f in m.items() for p_, a in [v.rsplit(':', 1)]
                    if FAMILY.get(p_) == FAMILY.get(post)]
            if not near:                                 # nothing in its throws: the family's brawler animation
                a = chv['anims'].get(FALLBACK_MOVE[FAMILY.get(post, 'standing')])
                near = [(0, a['steps'][-1]['frame'])] if a else []
            row.append(min(near)[1] if near else -1)
        table[n] = row
    return keys, table

def voice_data(ch, n, game, pool, sps):
    """the fighter's voice keys, KOF's own voice per key (voices.py suggest), the roster's mapping (game.json voices) and
    its voice table bytes"""
    slot_of = {m: ('parts', source(ch, m)['parts']) if source(ch, m).get('parts') else (source(ch, m).get('slot'), len(source(ch, m)['steps']))
               for m in MOVES}
    throw_rows = {}
    for t in THROWS:
        th = ch.get('throws', {}).get(t)
        if not th: continue
        st = [s['frame'] for s in ch['anims'][t]['steps']]; k, rows = 0, []
        for r in th['timeline']:
            if k + 1 < len(st) and r[0] == st[k + 1]: k += 1
            rows.append(k)
        throw_rows[t] = (ch['anims'][t]['slot'], rows)
    sug = V.suggest(n, game, slot_of, throw_rows, [(sp['input'], p['keep']) for sp, p in zip(pool, sps)])
    ks = V.keys(MOVES, THROWS, [sp['input'] for sp in pool])
    pv = {sp['input']: prog_voices(n, game, p) for sp, p in zip(pool, sps) if (kof_prog(p, game) or step_voiced(p))
          and not p['rom'].get('voice_frames')}          # (SS2's: the key keeps its frame-timed voice, its step voices
                                                         # are the connect's further ones: handlers_ss2.special)
    for inp, vs in pv.items():                           # a ROM special (KOF's, or WHP's step-voiced programs: TODO #181):
                                                         # its program's own voices (TODO #163), the
        if vs: sug['special:' + inp] = [vs[0], 0]        # key's suggestion = the first it sends
        else: sug.pop('special:' + inp, None)
    mp = V.mapping(roster()[n].get('voices'), sug)
    more = V.extras(n, ks, sug, mp, [(sp['input'], p['keep']) for sp, p in zip(pool, sps) if sp['input'] not in pv])
    more = sorted(more + V.anim_extras(n, ks, sug, mp, 'win', slot_of['win']))   # the win pose's further voices (#184)
    return ks, sug, mp, V.table(ks, sug, mp, len(V.bank(n)), n), more

def kof_prog(sp, game):
    """a KOF96 / 98 / 99 special played from its ROM program (its voices sent by the program: TODO #163)"""
    return game in H.SOUND_MAPPER and rom_ok(sp) and not sp['rom'].get('prims')

def voice_of_index(n, game):
    """sound index -> the fighter's voice id (voices.json, by driver word; 0: not one of its voices); a game without
    KOF's sound mapper (World Heroes Perfect, TODO #147): its steps' sound records hold the word itself"""
    of = {c: vo['id'] for vo in V.bank(n) for c in vo['cmds']}
    if game not in H.SOUND_MAPPER: return lambda w: of.get(f'{w:04X}', 0)
    m = V.mem(game)
    return lambda ix: of.get(f'{H.sound_word(m, ix):04X}', 0)

def prog_voices(n, game, sp):
    """the voice ids a KOF ROM special's program sends, the first it sends first: its code's sends now, its steps'
    $FC records (anim order), its code's sends later"""
    vi = voice_of_index(n, game); r = sp['rom']
    ops = r.get('ops') or []                                       # (a program written by its exporter: no ops, its
    now = [vi(op[1]) for op in ops if op[0] == 'vsend' and not op[2]]   # sends are its steps': WHP's, TODO #181)
    steps = [vi(ix) for st in r['states'] for s in r['anims'][st]['steps'] for ix in s.get('voices', [])]
    later = [vi(op[1]) for op in ops if op[0] == 'vsend' and op[2]]
    ids = [i for i in now + steps + later if i]                    # its own effects (channel 'fx', TODO #168) after
    return [i for i in ids if not V.fx_bit(n, i)] + [i for i in ids if V.fx_bit(n, i)]   # its voices: the key's suggestion is a voice

def prog_voice_res(n, game, inp, sug, mp):
    """a KOF ROM special's send -> the voice id it plays (fx bit included; 0: silent): the roster keeps the key's
    suggestion (game.json voices "kof"): its own; another voice picked for the key: that one in place of the first
    (suggested) voice, the others silent; the key silenced or no voices: none"""
    vi = voice_of_index(n, game); key = 'special:' + inp
    def res(ix):
        i = vi(ix)
        if not i or key not in mp: return 0
        if mp[key] != sug.get(key, [None])[0]: i = mp[key] if i == sug.get(key, [None])[0] else 0
        return i | V.fx_bit(n, i) if i else 0
    return res

SEGS = {}                                              # per fighter: its moves' segments (BA_* order, then its specials)
def move_segments(ch, n, sps):
    """each move's segments (retime.py) as the engine plays it alone: the brawler moves (their animation's steps), then
    its specials in pool order (a ROM special: its program played; a captured script: none, not retimed)"""
    out = [RT.step_segments(R.step_flags(source(ch, m)['steps'])) for m in MOVES]
    atk = lambda s_: boxes(s_['boxes'])[1] is not None
    for sp in sps:
        if not rom_ok(sp) or sp['rom'].get('lab'): out.append([]); continue   # (the Lab build's LAB special: not retimed)
        var = vdef_of(n, sp) if (sp['rom'].get('vtable') or {}).get('nvar') else 0
        out.append(RT.rom_segments(sp['rom'], var, atk))
    return out

def seg_table(segs):
    """bm_seg's table of one fighter: [moves, offset per move (0 = none)], then [n, lengths...] per move"""
    head, data = [len(segs)], []
    for sg in segs:
        if not sg: head.append(0); continue
        assert len(sg) < 256 and all(v < 0x10000 for v in sg), sg
        head.append(1 + len(segs) + len(data)); data += [len(sg)] + sg
    return head + data

def write_c(chars, outdir):
    pkeys, ptable = poses(chars); PKEYS[:] = pkeys
    SREACTS.clear(); SR_BASE.clear()
    for _, n_, ch_, _ in chars:                          # the source reactions (TODO #136): one table, each fighter's
        SR_BASE[n_] = []                                 # entries mapped into it, a motion already there shared (#213)
        for r_ in ch_.get('sreacts') or []:
            if r_ not in SREACTS: SREACTS.append(r_)
            SR_BASE[n_].append(SREACTS.index(r_))
    # KOF's shared effects bank (TODO #214): its frames' palettes are absolute (KOF98 palette RAM 80-127), one budget
    # for every fighter (SFX_NPAL at fighter.h SFX_PAL), not the fighter's MAX_PALS: a part keeps 0x80 | its index
    sfx_cols = {(game, int(k)): v for game, n, ch, off in chars for k, v in (ch.get('shared_palettes') or {}).items()}
    sfx_keys = sorted(sfx_cols)
    sfx_max = int(re.search(r'#define SFX_NPAL_MAX\s+(\d+)', open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'fighter.h')).read()).group(1))
    assert len(sfx_keys) <= sfx_max, f'{len(sfx_keys)} shared effect palettes, the game loads {sfx_max} (fighter.h SFX_NPAL_MAX)'
    def part_pal(game, n, p):
        return 0x80 | sfx_keys.index((game, p['spal'])) if 'spal' in p else used[n].index(p.get('pal', 0))
    h = ['/* Generated by tools/brawler/export_bm.py from the KOF dictionaries. Do not edit. */',
         '#ifndef BM_CHARS_H\n#define BM_CHARS_H\n#include <stdint.h>\n',
         'typedef struct { int16_t dx, dy; uint8_t cols, rows, hflip, vflip, pal; const uint16_t *tiles; } bpart_t;   /* tiles: cols*rows column-major, 0 = empty, then 3 trim words a column (t, top, first tile copied: draw.s, the sprite budget); pal: palette index of the fighter */',
         'typedef struct { uint8_t nparts, ncols; const bpart_t *parts; } bframe_t;   /* ncols: hardware sprites the frame uses */',
         'typedef struct { int8_t x, y; uint8_t w, h; } bbox_t;                       /* centre from the feet (y<0 up), half extents; sprite faces left */',
         'typedef struct { uint16_t frame; uint8_t ticks, flags; bbox_t hurt, atk; int8_t dx; uint8_t hy; } bstep_t;   /* flags: 1 = attack box, 2 = hurt box, 4 = opens a new hit (multi-hit normals; in a ROM special: 4 the victim reels without sliding (under SF_SREACT: its body box is a push box, Kizuna\'s type 5), 8 event, 16 same hit, 32 window, 64 a catch box, 128 no hit-stop: KOF\'s class 4 barrage hits, TODO #139); dx: px the fighter moves forward as the step starts (KOF\'s $FB move); hy: height in px during the step (command normals that hop: export96.cmd_frames); in a ROM special\'s anims (bspec_t.anims) the victim\'s reaction to its attack box instead, packed R_* standing | juggled << 4 (KOF\'s reaction table: tools/kof96/handlers98.box_react; 0 = the P_ANIM reaction) */',
         'typedef struct { uint8_t nsteps, hold; const bstep_t *steps; } banim_t;     /* hold: stop on the last step */',
         'typedef struct { int32_t walk, jump_vy0, gravity, jump_dx, hop_vy0, hop_gravity, hop_dx; uint8_t prejump, land; } bphys_t;   /* 16.16 px per frame (KOF ROM: export96 physics); jump_* = the regular jump (stick held), hop_* = the hop (stick tapped); jump_dx / hop_dx: horizontal speed of a forward or back jump; prejump: frames on the ground before take-off (KOF: the prejump animation, the frames in which a release makes the jump a hop); land: frames on the floor after a jump (KOF: the landing animation\'s steps at ticks + 1 frames each, + 1, measured: KOF98 4, Terry / Rugal / Goenitz 5) */',
         'typedef struct { uint16_t tframe; int16_t tx, ty; uint8_t vpose, flags; int16_t vx, vy; } bthrow_row_t;   /* one video frame of a paired script (vocabulary hold.paired_script): thrower frame + offset from its start (forward +, up +); victim posture (0xFF: none; flags 32: a BA_* animation it plays instead, its flight: blowback, knockdown...) + offset from the thrower; flags 1 = victim faces the thrower\'s way (its facing at the grab), 2 = victim drawn in front (a data override: game.json roster[].throws.front; else always behind the grabber, TODO #146), 4 = impact (the blow lands / the victim hits the floor: damage, spark, sound), 16 = the game froze there (hit-stop), 8 = the thrower has turned around (drawn mirrored; offsets stay in its grab facing) */',
         'typedef struct { uint16_t nrows, speed; const bthrow_row_t *rows; uint16_t ret, rel, land, fx_row; int16_t fx_dx, fx_dy; uint8_t hanim, hstep; uint16_t gframe, stun; uint8_t hsfx, turn; } bthrow_t;   /* turn (Krauser gold 2026-10-09, game.json roster[].throws.back = "throw_c"): an empty BT_THROW_D whose back throw is its C throw played turned (fighter.c throw_start: the victim over to its back at the grab, as the mirrored back throw of a chain); hsfx: a hold hit\'s sound, a normal button\'s (SX_A + 1 .. SX_CD + 1; 0 = its move\'s own: game.json roster[].throws.hold.sfx);  speed: 8.8 script rows a frame (fighter.c throw_update); ret: the CONTROL RETURN row (the thrower acts again from it; the victim plays its rows on alone to nrows, then lies down); rel / land: the release row and the landing row (0xFFFF: none): from rel to land the victim is a thrown body (spawn.body: it knocks down the enemies it touches); fx_row / fx_dx / fx_dy: the throw-start effect (fx.throw_start, TODO #166: KOF96/98\'s effect state 61 + its sound) on that row, px forward / up from the thrower (0xFFFF: none: the hold hits); hanim / hstep: a hold hit\'s move (BA_*) and its active step, whose attack box hits the crowd around the held victim (0xFF: none); gframe: the thrower\'s hold pose (throw C only; 0xFFFF: the throw\'s first row: SS2\'s turned grab has its own, TODO #188 a); stun: a stun strike (TODO #212, Double Dragon\'s Cheng-Fu: no damage, no impact): at its end the victim stands dizzy in its heavy reel for stun frames, open to any hit (fighter.c victim_end, fighter_t.dizzy; 0 = a throw) */',
         'typedef struct { uint16_t frame; int16_t x, y; uint8_t same, react; bbox_t box; } bsobj_t;   /* special\'s object (projectile): frame (0xFFFF = none), offset from the fighter\'s start, faces the fighter\'s way, react: the victim\'s reaction R_* + 1 measured in the game (0: knockdown); box: none (an effect: what hits is the special\'s projectile, bspec_t.proj) */',
         'typedef struct { uint16_t frame; int16_t x, y; bbox_t atk; uint8_t hit, dmg; bsobj_t obj[2]; int16_t vx; uint8_t vy, fx; } bspec_row_t;   /* one video frame of a special: fighter frame + offset from its start (forward +, up +), body attack box; hit: 1 box live, 2 opens a new hit (vx without 4: the px a reel slides the victim, fighter.c kof_react), 4 the target is carried at vx (forward from the fighter) / vy (height; grabs only), 8 contact (no damage), 16 a hit here goes on to the continuation, bits 5-7 the victim\'s reaction R_* (export_bm special_rows); dmg: damage of the hit it opens; fx (rows opening a hit): KOF98 hit effect, bits 0-5 the hit kind (the victim\'s hit sounds, fighter.c HIT_SFX), bits 6-7 the burn (1 purple, 2 orange) */',
         'typedef struct { uint16_t frame; int16_t x, y; bbox_t atk, own; uint8_t flags, pad; } bprow_t;   /* one frame of a projectile\'s flight: frame, x from its spawn point in 1/8 px (forward +), height px, attack box (live when flags & 1: the game\'s +$90 box while +$7C bit 0), own box (the box another projectile\'s attack meets: a clash; flags & 2) */',
         'typedef struct { uint16_t frame; int16_t x, y; } bpend_t;   /* a projectile\'s end after its hit: frame, x from the impact in 1/8 px, height from the impact\'s (the end plays where the hit was, TODO #164) */',
         'typedef struct bproj { uint8_t nrows, loop, nend, kind, spawn_row, react, fx, follow; int16_t spawn_x, spawn_y, wrap_x; const bprow_t *rows; const bpend_t *end; const struct bproj *child; uint8_t child_b0, child_b1, child_period, sig; int16_t child_dx, child_dy; const struct bproj *next; uint8_t hits, stop, hitnext, ppad; int16_t brange, bcatch, bsegmin; uint8_t bhover, bheld, bseg, bgap; uint8_t air, back, cols, vhits; } bproj_t;   /* vhits (Krauser gold 2026-10-09, game.json roster[].max_hits: his MAX Kaiser Wave): 0, or a travelling object that pierces: it hits each victim vhits times (the last with its react, the others a reel R_HEAVY; its damage split over them), frozen stop frames after each hit, then re-armed for every victim it is not done with (fighter_t.vcnt / vdone; fighter.c strike), flying on; cols (TODO #216): its widest frame (hardware sprites) over its rows, end rows and child chain, measured by the export (main.c depth_sort: the pool block of a new definition); back 1 (TODO #214, KOF\'s +$2C < 0: an effect of the shared bank drawn behind its owner, Iori 624D\'s smoke): drawn behind a fighter at the same Z (fighter_t.zfront -1); air 1 (TODO #211, an air projectile: SS2 Hanzo\'s shuriken thrown from a jump): its rows\' heights count from its thrower\'s height at its spawn (fighter_t.py0), and the frame after its height reaches the floor it becomes its next phase there (its floor rows: the shuriken stuck in the floor; no next: it ends); ppad 1 (TODO #193): its hit sends the victim away from its thrower, not from where it stands (SS2 Hanzo\'s rage flame, its column beyond the victim: SS2 throws it on away from him); kind 4 = spawn.boomerang (TODO #176, SS2 Kuroko\'s flag, object 27 $4C274; fighter.c boom_update): it flies out wrap_x (1/8 px) a frame from spawn_x px ahead of its thrower until brange px from him, or until its first hit / clash (its attack then spent), hovers there bhover + 1 frames, flies back at the same speed until bcatch px from him, signals him (sig, at the catch, not at its end) and stays bheld + 1 frames in his hand; rows = its animation (x unused; loop = the row it holds); bseg pole segments (child: their bproj_t, kind 5, placed by it) bgap px apart behind it, never nearer him than bsegmin px; it ends with its thrower\'s special (proj[]), never off screen; hitnext 1 (TODO #173, Rugal\'s Kaiser Wave: KOF\'s hit routine steps a state list, +$C2): next is the phase it becomes at its hit (where it is, frozen stop frames, re-armed), not at its thrower\'s signal; next / hits / stop (vocabulary object.phase, TODO #152): the phase it becomes when its thrower sets +$D1 bit 7 (P_FXOFF: a pinned effect launched instead of ended, from where it is: Billy Kane\'s fire ring), that phase\'s hits before its end rows (0 / 1: its first hit ends it; KOF\'s +$138) and the frames it stays frozen after a hit with hits left (then re-armed); bprow_t flags 4: the row re-arms its hit (KOF: the object clears its +$E2 bit 7 on an event step: it hits again); sig (TODO #139): its thrower\'s +$D1 bits 7 / 6 (fighter_t.pflags PF_SIG7 / PF_SIG6) it sets at its end, bits 5 / 4 = the same at its hit (Raging Storm\'s side effects, K\'\'s shot); follow: 1 = an effect pinned to its thrower (3: it ends at its last row) (rows: offsets from it; a ROM special\'s, ended by P_FXOFF or the special\'s end: Burn Knuckle\'s flame); bit 4: its rows run with its thrower\'s script rows (row = the thrower\'s row - spawn_row: frozen with its hit-stop), it ends when the thrower leaves them (Kizuna\'s Hienzan pillar, TODO #144: a script special\'s pinned effect, not a shot); bit 16: pinned to its thrower\'s caught victim (fighter_t.target) instead (SS2\'s WFT card wind, object 27); child: the trail it spawns (no boxes) on its frames child_b0, child_b1 (255: none), then every child_period, child_dx (1/8 px, forward) / child_dy from its place then (KOF: objects owned by the projectile: Krauser\'s Blitz Ball, Iori\'s Yami Barai); a special\'s projectile (tools/kof96/projectiles96): an entity of its own from the thrower\'s script row spawn_row, at spawn_x / spawn_y (px, from the script\'s origin, forward +); rows = its flight; loop: the row the flight repeats from (0xFF: it dies when its rows end, its animation over), each repeat moving it wrap_x (1/8 px) on; kind: KOF object +$F5, 1 = travelling (its hit ends it: the end rows play), 3 = an eruption (plays on, its attack spent); react R_*, fx: hit effect (bspec_row_t.fx); dies off screen (x - camera <= -64 or >= 384: KOF96/98/99\'s own test) */',
         'typedef struct { uint8_t op, a; int16_t b; int32_t v; } bprim_t;   /* one primitive of a special read from the ROM (tools/kof96/handlers98.py, handlers98.md; export_bm rom_c): op P_*, operands a / b / v (fighter.c prog_update) */',
         'enum { P_ANIM = 1, P_SET, P_MUL, P_MOVE, P_FRICMOVE, P_FALL, P_NUDGE, P_DEC, P_BR, P_RESUME, P_RESUMEAT, P_JMP, P_SPAWN, P_FXOFF, P_END, P_ADV, P_CHECK, P_PART, P_EVCLR, P_ONHIT, P_PUT, P_HITCLR, P_HOLD, P_UNHOLD, P_SIGCLR, P_HITOFF, P_ADD, P_FORM, P_VOICE, P_VSIG, P_TURN, P_VPHASE, P_SCREEN, P_HOME, P_CATCH, P_LANIM };   /* P_LANIM (the Lab build\'s LAB special, export96.lab_special) = P_ANIM with a 16-bit animation index: a = damage, b = reaction, v = bspec_t.anims index << 8 | hit effect; P_CATCH (TODO #216, KOF98 $3F8A: the engine\'s throw on the held opponent, Iori 23624C\'s finisher) the catch now: a dead frames (0: the routine from the next frame), then the routine b; its victim takes list v (bspec_t.vlists, 1-based), held (PF_HOLD) from the routine\'s start; P_VPHASE (TODO #136, vocabulary hold.victim_phase) a = VA_* bits on its target (Kizuna: the victim\'s +$1AF phases, $2CD06; fighter.c vphase): VA_SNAP placed at the attacker\'s place, VA_FREEZE / VA_THAW its body held still (its reaction paused, its velocity kept) / free, VA_MIRROR / VA_UNMIRROR its body moved by the attacker\'s moves mirrored in x; P_SCREEN a = 1 / 0: the special\'s screen effect (bspec_t.bd_col, bd_first 0xFFFF) on / off (Kizuna $27E1, the Phoenix); P_HOME (TODO #218, vocabulary attack.down) a = a shift: vx = the distance to its down attack\'s target (whole px) >> a (turned to face it), vz = its depth >> a (fighter.c; Double Dragon\'s leap $23070: << 10 = >> 6, a 64-frame flight); P_VPHASE (TODO #136, vocabulary hold.victim_phase) a = VA_* bits on its target (Kizuna: the victim\'s +$1AF phases, $2CD06; fighter.c vphase): VA_SNAP placed at the attacker\'s place, VA_FREEZE / VA_THAW its body held still (its reaction paused, its velocity kept) / free, VA_MIRROR / VA_UNMIRROR its body moved by the attacker\'s moves mirrored in x; P_SCREEN a = 1 / 0: the special\'s screen effect (bspec_t.bd_col, bd_first 0xFFFF) on / off (Kizuna $27E1, the Phoenix); P_VSIG (TODO #173) the caught victim takes its next list (KOF: +$D1 bit 7 on the opponent; bspec_t.vlists); P_TURN the attacker turns around (KOF eori #1, +$31: speeds stay forward +); P_VOICE (TODO #163) a = voice id (0 silent), b = 0: now, else b frames later (KOF +$1B4 / +$1B6; fighter.c prog_voice); P_ADD a = register (0 vx, 1 vy, 4 cnt) += v (16.16; gravity applied before the move: Double Dragon\'s order); P_FORM the form link\'s swap now (fighter.c form_swap: the special ends); P_MUL a = 1: vy *= v; (TODO #139) P_HITOFF its hit flag cleared (KOF +$E1 bit 7, PC_HIT); P_SIGCLR v = the +$D1 bits 7 / 6 kept (an andi: its objects\' signals cleared); P_EVCLR the step\'s event consumed (KOF: andi on +$7D); P_ONHIT b = the catch routine (KOF +$19C: a catch box\'s hit, bstep_t flags 64, runs it after a dead frame); P_PUT v = the caught victim put v px in front, facing the attacker (KOF $25032); P_HITCLR the any-hit flag cleared (KOF +$E3 bit 7, PC_HITANY); P_HOLD / P_UNHOLD the caught victim held in place / let go (KOF +$E4 bit 4: its reactions stay a standing reel while held); P_ADV the animation one more tick (the engine called again on the same state); P_CHECK a = the follow-up links read this frame (a press of link k this frame arms bit k: fighter_t.plink); P_PART the armed links cleared (a new part); bprim_t.op: P_ANIM a = bspec_t.anims index, b = damage | reaction << 8 of the hits it opens, v = hit effect; P_SET a = register (0 vx, 1 vy, 2 g: 16.16; 3 fric: 0.16; 4 cnt), v; P_MUL vx *= v / 65536; P_MOVE x += vx; P_FRICMOVE vx *= fric, x += vx; P_FALL height += vy, vy -= g (landed / falling flags); P_NUDGE b px forward, v px up; P_DEC cnt -= 1; P_BR a = condition PC_* | 0x80 when true, b = the op to go to (-1: the frame ends, it resumes next frame); P_RESUME the resume point = the next op; P_RESUMEAT b; P_JMP b; P_SPAWN a = bspec_t.robj index; P_FXOFF its attached effects end; P_END */',
         'enum { PC_END, PC_EVENT, PC_LAND, PC_FALL, PC_CNT, PC_HIT, PC_OFF, PC_ALWAYS, PC_STEPEV, PC_WINDOW, PC_LINK, PC_HITANY, PC_SIG7, PC_SIG7C, PC_SIG6, PC_FAR, PC_LOW, PC_WALL, PC_HELD, PC_CNTLE, PC_PASSED, PC_CAUGHT, PC_THIGH, PC_TDOWN };   /* PC_TDOWN (TODO #218) its down attack\'s target still lies (DD $230FA: else the fall); PC_THIGH (TODO #136) its target above v px and held by no victim phase (fighter.c vphase: Kizuna $3AC92, the Phoenix\'s ceiling); PC_PASSED (SS2 $563F4) its opponent (the target, else the nearest on its lane) no longer ahead of it by more than v px; PC_WALL (TODO #173) the fighter at the wall (KOF98 $18092, the stage\'s x 32 / 736; the brawler: the screen-edge wall, fighter.c wall_lo / wall_hi); PC_HELD the special\'s button held (KOF and.b (fp): a charge); PC_CNTLE the counter <= v (KOF\'s charge level tests); PC_LOW the height below v px (KOF cmpi on +$20, Billy 623D); PC_FAR the target farther than v px (KOF +$BC, K\'\'s dash); PC_SIG7 / PC_SIG6 its object set +$D1 bit 7 / 6 (bproj_t sig), PC_SIG7C bit 7 consumed (bclr); PC_HITANY a hit landed since P_HITCLR; PC_STEPEV the step has KOF\'s $0080 (bstep_t flags 8, not consumed by P_EVCLR / PC_EVENT), PC_WINDOW $2000 (flags 32, a follow-up window), PC_LINK an armed link in the P_BR\'s v mask; P_BR conditions: animation over, an event step entered (consumed), landed, falling, counter < 0, the move hit, off screen, always */',
         'typedef struct { uint16_t first, end; uint8_t next, pad; } bspart_t;   /* a special\'s part: script rows [first, end), the part played when it ends (0xFF: the move ends; fighter.c "follow-ups") */',
         'typedef struct { uint8_t from, to, trig, in, dir, at; uint16_t lo, hi; } bslink_t;   /* a follow-up: from part `from` to part `to`; trig 1 a hit landed (LK_HIT), 2 a press (LK_IN: buttons `in` IN_*, stick `dir` = a C role BS_* by d_input, 0xFE the role the move started with, 0xFF any) inside the window [lo, hi) (script rows); at 1 = switch at once (LK_NOW), 0 = when the part ends */',
         'typedef struct { int8_t dx, dy; uint8_t pose, flags; } bvent_t;   /* a caught victim\'s place for one attacker step (KOF98 $25372 lists, TODO #173): px from the attacker (its facing\'s way), height, posture VP_* (0xFF: its reel), flags VE_* */',
         'typedef struct { uint8_t n, flags; const bvent_t *e; int16_t vx, vy, g; } bvlist_t;   /* one list: entry k for the attacker\'s step k (the last for later steps); n 0 ends the table; flags VL_FLY: placed at its first entry once, then the victim flies on its own (vx forward of the attacker, vy up, g its gravity: 8.8 px / frame), posture held (SS2\'s rage-move victims, handlers_ss2.VL); VL_VEL: its release entry sends the victim off at vx / vy (else KOF\'s blowback) */',
         'enum { VL_FLY = 1, VL_VEL = 2, VL_CATCH = 4, VL_FRAMES = 8, VL_SREACT = 16, VL_DOWN = 32, VL_STAND = 64 };   /* VL_STAND (TODO #220): its release entry leaves the victim standing in its reel, still held (PF_HOLD) until a hit lets it go (KOF98 Yamazaki MAX 236236C: state 329); VL_CATCH (TODO #216): a list P_CATCH starts (KOF98\'s engine throw on the held victim), never a catch routine\'s start; (TODO #213, Kizuna\'s command grabs: tools/kizuna/rosa_kz.py) VL_FRAMES: entry k for the k-th frame of the list (from the P_VPHASE VA_LIST that started it), not the attacker\'s step; VL_SREACT: its release sends the victim into source reaction vx (bm_sreact index + 1: Kizuna\'s thrown flight, hittable when its source\'s steps carry boxes); VL_DOWN: its release lays it down (S_DOWN, then it gets up: Kizuna\'s thrown victim lying at its animation\'s end) */',
         '#define HY_HOLD 0x80   /* bstep_t.hy of a ROM special: KOF\'s hold hit (attack box $36, TODO #220; handlers98.HOLD_BOX): its victim held in place by the attacker (PF_HOLD), reeling; a later hit by another box lets it go with that hit\'s reaction */',
         'enum { SF_NOPUSH = 1, SF_BIGHIT = 2, SF_NOW = 4, SF_SHARE = 8, SF_INV = 16, SF_SREACT = 32 };   /* bspec_t.sflags (SF_SREACT (TODO #136, vocabulary reaction.source_motion): its anims\' bstep_t.hy are source reactions, bm_sreact index + 1 standing | airborne << 4 (fighter.c src_react: Kizuna\'s reaction animations\' motions); SF_INV: invincible from its first frame to its end, the fury\'s rule (INV_FURY): game.json roster[].invincible, Bruno\'s call per move (TODO #202: Kyo\'s EX 421D), fighter.c start_special; SF_SHARE: its body and a standing opponent ahead share the push, half each: Kizuna\'s j.2B dives on pushing its victim (TODO #200), on the ground too since TODO #136 (Kizuna\'s push for every program of Kim\'s: the Phoenix\'s rush at half speed), fighter.c combat; SF_BIGHIT: SS2\'s big hit on its connect, fighter.c big_hit; SF_NOW: its program runs from the special\'s start frame, SS2\'s action routine in the frame the action is set: fighter.c start_special, TODO #191) */',
         'enum { VE_BLOW = 1, VE_KO = 2, VE_TURN = 4, VE_FRONT = 8, VE_BURN = 48, VE_REL = 64 };   /* bvent_t.flags: a blow (damage, hit sound), the KO check, faces the attacker\'s way, drawn in front, the burn of its blow (bits 4-5: BURN_RAMP colour 1 purple / 2 orange, KOF\'s victim routine $17AC0: Iori 624), the release (its flight) */',
         'typedef struct { uint16_t nrows, inv_rows, nparts, nproj; const bspec_row_t *rows; const bproj_t *proj; const bprim_t *prog; const banim_t *anims; const bproj_t *robj; const bspart_t *parts; const bslink_t *links; uint16_t nlinks, bd_first, bd_end, bd_col[2]; int16_t sf_dx, sf_dy; uint8_t sf_anchor, sf_pad; const int32_t *vars; uint8_t nvar, vdef, vanim, vobj, vcols, vdmg, pvoice, sflags; const bvlist_t *vlists; } bspec_t;   /* sflags SF_NOPUSH: its attacker pushes nobody standing in its path (SS2: the action descriptor\'s byte 4 bit 7 -> +$FF, the players\' push $CC14 skipped: Genjuro\'s 236S slides through); vlists (TODO #173, vocabulary hold.victim_list): a catch\'s victim script, its lists in the order the program\'s P_VSIG steps through them (list 0 from the catch routine\'s start; fighter.c vlist_apply); vars..vdmg: the variant table (vocabulary variant.parameter_set, export_dd): nvar parameter rows of vcols columns (vars, row-major), the row its rule plays (vdef, latched at the move\'s start: fighter_t.var), its program\'s animations / objects per row (anims[a + var * vanim], robj[a + var * vobj]), the damage column + 1 (vdmg, 0 none); a bprim_t op | 0x80 takes its value from column b; pvoice 1: its voice keys are timed by its frames (a program\'s, fighter.c); sf_*: the super flash\'s optional anchor (fx.super_flash, TODO #139: an engine rule for every fury, gamedata.h gflash_t; main.c super_flash): sf_anchor 1 = the concentration plays sf_dx / sf_dy px from the fighter (KOF orientation: negative dx = forward; read from the move\'s KOF animation, handlers98.super_flash), 0 = the game-wide anchor; bd_*: its screen effect (Kizuna\'s Phoenix, export_kz FOLLOW \'backdrop\'): rows bd_first .. bd_end - 1 hide the stage and the backdrop alternates bd_col[0] / bd_col[1] every frame (main.c screen_fx; bd_end 0 = none); inv_rows: invincible for its first rows (prog: frames) when it is played as down+D (the rising reversal: fighter.c); parts / links: its follow-ups (nparts 0 = one part, the whole script; export_bm special_parts); proj: its nproj projectiles in spawn order (Geese\'s Double Reppuken: 2); prog (0 = none): the special read from the ROM, played by fighter.c prog_update from its anims (KOF step flags in bstep_t: 8 event $0080, 16 same hit $4000) and robj (its objects: projectiles, effects pinned to it); rows / proj stay its captured script (the Brawler Lab\'s data, and the fallback when prog is 0) */',
         'typedef struct { uint16_t frame; uint8_t n, voice; int16_t hx, hy; } bfpose_t;   /* a flash pose step (TODO #145): its frame, the frames it shows, the voice sent as it shows (TODO #189: its source sends it on that step; id | fx bit, 0 none), its head point (TODO #191: px from the feet, facing left; the glow\'s anchor while it shows) */\n',
         'typedef struct { const char *name; uint8_t npal, nsets; const uint16_t *pals; const bframe_t *frames; const banim_t *anims; bphys_t phys; const bthrow_t *throws; const uint16_t *vposes; const bspec_t *specials; uint8_t tile_hi, cmds; const uint8_t *routes; uint8_t id, nspec; const uint8_t *spmap; const uint8_t *voices; uint8_t nvoice, fury, sfx[7]; const uint8_t *vmore; uint8_t fury_max, form_to, form_spec, form_trig, form_exit; const bthrow_t *holds; const uint8_t *pvox; const uint8_t *pfx; const bfpose_t *fpose; uint8_t nfpose; int8_t fhead[2]; const uint16_t *fpal; uint8_t fpal_ix; uint8_t flk_ix; const uint16_t *flk; uint8_t nair, down_spec; } bchar_t;   /* nair (TODO #221, vocabulary air.special, game.json roster[].air_specials): its air specials\' count; the table is bm_air[id] (outside bchar_t, whose 128 bytes index by a shift): [input, special index] each, 0xFF ends; input = the stick\'s slot (BS_D .. BS_UF_D, the ground\'s six C slots) | AIR_A for the A button (else C): that press in a jump plays it (role BS_AIR, fighter.c air_pick: an A one in the air normal\'s place, no meter; a C one a C special\'s meter); down_spec (TODO #218, vocabulary attack.down, game.json roster[].down_attack): the index in specials of its down attack, played by up / down + A on the ground at an opponent lying in reach (role BS_DOWNATK, no meter; 0xFF = none); flk (TODO #193, SS2\'s second-layer flicker): the colours its palette flk_ix shows every other frame, 16 per colour set (flk_ix 0xFF = none; fighter.c flicker); fpose (TODO #145, fx.super_flash "flash pose"): its flash pose, nfpose steps [frame, frames shown] filling the super flash\'s freeze (0 = none: the fury plays under the flash, KOF\'s own flash step), fhead the pose\'s head point (px from the feet, facing left): the concentration\'s anchor (each step\'s own: bfpose_t hx / hy); fpal (TODO #191): the colours of its palette fpal_ix while the pose shows, 16 per colour set (SS2\'s rage palette; fpal_ix 0xFF = none); pfx (TODO #173, vocabulary anim.step_spawn): its KOF ROM specials\' step effects, [special index, anim index, step, robj index] each, 0xFF ends: the effect object the animation\'s $FA record spawns as the program enters that step (fighter.c pan_fx); pvox (TODO #163): its KOF ROM specials\' step voices, [special index, anim index, step, voice id] each, 0xFF ends: sent as the special\'s program enters that step (KOF\'s $FC records; its code\'s own sends are P_VOICE ops; fighter.c pan_voices); holds: its hold hits (HOLDS: a hit, the finisher), paired scripts like its throws (TODO #146); form_*: the form link (vocabulary form.change, game.json roster[].form): form_trig FT_* (0 = none) starts specials[form_spec] (the transition, role BS_FORM), whose P_FORM makes the fighter bm_chars[form_to] (life, place, facing, meter kept), back by form_exit FX_*; fury_max: the index in specials of the fury\'s MAX version (down+D, TODO #139; 0xFF = none: down+D plays the fury); vmore: a key\'s further voices, [key, voice id, at] each, 0xFF ends (voices.py extras: a special that sends several, the Phoenix shouts; played with the ROM\'s voice table only); sfx: hit sounds by use (TODO #75, game.json roster[].hit_sfx): A B C D CD normals, throw C / D impacts, 0 = KOF\'s own (fighter.c hit_sound);  voices: its voice table, VK_SPEC + nspec entries of [voice id, at] (tools/brawler/voices.py table: id 1..nvoice = its voices.json list, 0 = silent; at = the step / script row it starts on), the ROM\'s default for fighter.c voice_tab; fury: the fury\'s index in specials (button D, game.json roster fury; 0xFF = none); pals: nsets * npal * 16 colours; throws: BT_COUNT (nrows 0 = none); vposes: VP_COUNT frames (0xFFFF = none); specials: its nspec specials (export_bm special_pool order; nspec, spmap last: draw.s reads the offsets before them); spmap: the special each role plays, BS_COUNT entries (D projectile, forward+D rush, down+D rising reversal, up+D another, down-forward+D, up-forward+D: two more; 0xFF = none), the ROM\'s default for fighter.c spec_tab; tile_hi: tile number bits 16-19 of all its tiles; routes: its chain route tree (fighter.h rt_head_t, routes.py); id: its index in bm_chars; cmds: command normals it has, bit k = BA_CMD_FWD_A + k (forward+A, forward+B, down-forward+C, down-forward+D) */\n',
         'enum { ' + ', '.join(f'BA_{m.upper()}' for m in MOVES) + ', BA_COUNT };',
         'enum { ' + ', '.join(f'BC_{n.upper()}' for _, n, _, _ in chars) + ', BC_COUNT };',
         'enum { ' + ', '.join(f'BT_{t.upper()}' for t in THROWS) + ', BT_COUNT };',
         'enum { BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D, BS_DF_D, BS_UF_D, BS_COUNT };',
         f'enum {{ AIR_A = {AIR_A}, AIR_DD = {AIR_DD} }};   /* bchar_t.air: an entry\'s button A (else C), AIR_DD: on down,down + the button (intent_t.blitz BZ_DD), its low nibble the stick\'s slot BS_* */',
         f'enum {{ VP_COUNT = {len(pkeys)} }};   /* victim postures: ' + ' '.join(pkeys) + ' */',
         'enum { VK_THROW = BA_COUNT, VK_HIT = BA_COUNT + BT_COUNT, VK_KO, VK_SELECT, VK_SPEC };   /* voice keys (voices.py keys): BA_*, VK_THROW + BT_*, the events, VK_SPEC + its special\'s index in the pool */',
         'typedef struct { const uint8_t *map; const bproj_t *sparks; } bhspark_t;   /* (TODO #215, vocabulary fx.hit_spark) a fighter\'s source game\'s own hit sparks (Double Dragon: tools/doubledr/sparks_dd.py; map 0 = none: the engine\'s KOF98 spark): map = [where (its special index, 0xFE a normal: its BA_ animation), animation index (a special\'s anims), step, spark] each, 0xFF ends, in its bank; a hit landing on that step spawns sparks[(spark & 0x3F) - 1] (an effect object, bproj_t kind PK_FX) at its game\'s hit point (fighter.c hit_spark); spark 0x40 = turned (the other way), 0x80 = the screen strobe (DD\'s super hits: fighter.c hitflash) */',
         'typedef const uint8_t *bair_t;   /* (TODO #221) */',
         'typedef struct { const bthrow_t *x; uint8_t up, down, sup, pad; } bxthr_t;   /* (revamp 3, game.json roster[].throws extra / super) a fighter\'s throws beyond forward / back: x = its extra paired throw (0 none: tools/kof96/throwrom.py, Ralf\'s 426B); up / down = hold + up / down + A, sup = the super throw (hold + forward / back + C with the meter): a special\'s index in its pool (a grab special played from its ROM program on the held victim, role BS_THROW), XT_PAIRED its x, XT_FWD (sup) the throw pressed at the super tier, XT_NONE none (up / down: the hold hit) */',
         f'enum {{ XT_FWD = {XT_FWD}, XT_PAIRED = {XT_PAIRED}, XT_NONE = {XT_NONE} }};',
         'extern const bxthr_t bm_xthr[BC_COUNT];   /* (revamp 3) by bchar_t.id (outside bchar_t, whose 128 bytes index by a shift) */',
         'typedef const uint16_t *bseg_t;   /* (retiming) */', 'extern const bseg_t bm_seg[BC_COUNT];   /* (retiming, retime.py) by bchar_t.id: [BA_COUNT + nspec, offset of each move (BA_* then its specials; 0 = no segments)], then per move [n, the source frames of its n segments: startup, active 1, recovery 1, ...] (fighter.c rt_*) */',
         'extern const bair_t bm_air[BC_COUNT];   /* (TODO #221) by bchar_t.id: its air specials, [input, special index] each, 0xFF ends (bchar_t.nair entries) */',
         'enum { HS_HOLD = 0xF0 };   /* bm_hsnd key of a hold script: HS_HOLD + its index in bchar_t.holds (hit, fin) */',
         'extern const bair_t bm_hsnd[BC_COUNT];   /* (Kim\'s hit sounds, Bruno 2026-10-09) by bchar_t.id: its hits\' own sounds, [key, n, n sound commands] each, 0xFF ends; key = a move (BA_*: routes.py hit_sounds, a route node\'s "sound" list) or HS_HOLD + k (game.json roster[].throws.hold.sound {hit, fin}); a command per hit of the move / impact of the script, in order (fighter.c own_sound; a hit past the list: the engine\'s rule) */',
         'extern const bhspark_t bm_hspark[BC_COUNT];   /* by bchar_t.id (bm_spec.c: the first program MB; outside bchar_t, whose 128 bytes index by a shift) */',
         'typedef struct { int32_t vx, ax, vy, g, bvx, bvy, bg; uint8_t r, n, land, anim; } bsreact_t;   /* a source reaction (TODO #136, vocabulary reaction.source_motion; tools/kizuna/export_kz.sr_motion: Kizuna\'s reaction animations\' step commands, decoded from its hit code): the victim\'s motion when a SF_SREACT special\'s step hits it, 16.16 px a frame, x away from the attacker: vx += ax a frame while a reel slides (n frames), a flight vy -= g a frame to the floor (it lands where its next move would take it under, without moving), land frames on the floor (0xFF: none, the brawler\'s own landing), then the bounce bvx / bvy / bg; r: the victim\'s posture R_* (| 8: hittable in its flight, its source\'s reaction steps carry boxes); anim: the source\'s reaction animation (Hayate\'s, for reading) */',
         'extern const bsreact_t bm_sreact[];',
         'enum { VA_SNAP = 1, VA_FREEZE = 2, VA_THAW = 4, VA_MIRROR = 8, VA_UNMIRROR = 16, VA_LIST = 32 };   /* P_VPHASE bits (fighter.c vphase); VA_LIST (TODO #213): its caught target follows the special\'s victim list b (1-based, bspec_t.vlists) from now, held (PF_HOLD) */',
         'extern const bchar_t bm_chars[BC_COUNT];',
         f'#define SFX_NPAL {len(sfx_keys)}   /* KOF\'s shared effects bank (TODO #214): its palettes the exported frames use, '
         + ', '.join(f'{g} {k}' for g, k in sfx_keys) + ' (main.c loads them at SFX_PAL, fighter.h; a part\'s pal | 0x80 = one of them) */',
         'extern const uint16_t bm_sfx_pals[];',
         'extern const int8_t bm_head[BC_COUNT][2];   /* the head of each fighter\'s select pose (BA_WATCH), px from the feet, facing left (head_point.py; game.json roster[].watch.head): where the select cursor points */\n#endif']
    c = ['/* Generated by tools/brawler/export_bm.py. Do not edit. */\n#include "bm_chars.h"\n',
         'const uint16_t bm_sfx_pals[] = {' + ', '.join(f'0x{v:04X}' for g, k in sfx_keys for v in sfx_cols[(g, k)]) + ('' if sfx_keys else '0') + '};   /* SFX_NPAL palettes (KOF\'s shared effects bank, TODO #214) */\n']
    cs = ['/* Generated by tools/brawler/export_bm.py. Do not edit. Every fighter\'s specials (its special_pool, in pool order):\n'
          ' * compiled as plain read-only data, so they sit in the first program MB, beside the code (bm_chars.c goes to $200000). */\n'
          '#include "bm_chars.h"\n']
    fx = lambda v: str(int(round(v * 65536)))
    def bb(b): return '{0, 0, 0, 0}' if b is None else f'{{{b[0]}, {b[1]}, {b[2]}, {b[3]}}}'
    used = {}                                            # palettes the exported frames use, renumbered 0..k-1
    pooldata = {}                                        # per fighter its pool's frame / hit data (chainlab.json)
    vdata = {}                                           # per fighter its voice keys, suggestion, mapping (chainlab.json)
    for game, n, ch, off in chars:
        FRAME_COLS[n] = [sum(len(p['tiles']) for p in fr['parts']) for fr in ch['frames']]   # (= its bframe_t ncols)
        sets = ch['block_palettes']
        used[n] = pal_slots(n, sorted({p.get('pal', 0) for fr in ch['frames'] for p in PP.own_parts(fr)}) or [0], sets)
        c.append(f'static const uint16_t {n}_pals[] = {{' + ', '.join(f'0x{v:04X}' for st in sets for k in used[n].keys for v in st[k]) + '};')
        for fi, fr in enumerate(ch['frames']):
            for pi, p in enumerate(fr['parts']):
                assert len(p['tiles'][0]) <= 32, f'{n} frame {fi}: {len(p["tiles"][0])} rows (SCB3 height and draw.s stop at 32)'
                flat = [(t + off) & 0xFFFF if t else 0 for col in p['tiles'] for t in col]   # low 16 bits; tile_hi has 16-19
                rows = len(p['tiles'][0])                # each column's trim (TODO #158 / #170, the sprite budget: draw.s
                ptop = -p['dy'] - rows * 16 if p['vflip'] else p['dy']   # shows only its rows from the first to the last
                for col in p['tiles']:                   # non-empty tile, so its sprite counts on fewer lines): 3 words,
                    nz = [r for r, t in enumerate(col) if t]   # t = (-top << 7) | rows shown (the SCB3 from the feet; 0: an
                    if not nz: flat += [0, 0, 0]; continue   # empty column), top (px from the feet), the first tile copied
                    ns = nz[-1] - nz[0] + 1                  # (byte offset in the column; vflip: copied backwards from it)
                    top = ptop + 16 * (rows - nz[0] - ns if p['vflip'] else nz[0])
                    flat += [((-top) & 0x1FF) << 7 | ns, top & 0xFFFF, 2 * (nz[0] + ns if p['vflip'] else nz[0])]
                c.append(f'static const uint16_t {n}_f{fi}_p{pi}[] = {{' + ', '.join(map(str, flat)) + '};')
            c.append(f'static const bpart_t {n}_f{fi}[] = {{' + ', '.join(
                f'{{{p["dx"]}, {p["dy"]}, {len(p["tiles"])}, {len(p["tiles"][0])}, {p["hflip"]}, {p["vflip"]}, {part_pal(game, n, p)}, {n}_f{fi}_p{pi}}}'
                for pi, p in enumerate(fr['parts'])) + '};' if fr['parts'] else f'static const bpart_t {n}_f{fi}[1];')
        c.append(f'static const bframe_t {n}_frames[] = {{' + ', '.join(
            f'{{{len(fr["parts"])}, {sum(len(p["tiles"]) for p in fr["parts"])}, {n}_f{fi}}}' for fi, fr in enumerate(ch['frames'])) + '};')
        arr = {}                                                 # one step array per source animation: a move the
        for m in MOVES:                                          # fighter lacks shares its fallback's (idle)
            a = source(ch, m)
            if id(a) in arr: continue
            arr[id(a)] = f'{n}_{m}'
            steps, live, prev_act, prev_chain = [], None, False, False
            for s in a['steps']:
                hb, ab = boxes(s['boxes'], REACH)
                # KOF step flags: $0100 = attack active (the last attack box stays live on every active step, a box command
                # only comes when it changes), $4000 = the next active step continues this hit. An active step after an
                # inactive one, or after one without $4000, opens a new hit: Terry / Chang close C, Yamazaki close D hit
                # twice (KOF98 measured: 52 of 54 normals match the rule; Billy's staff close D hits twice, rule says once)
                # A box command on an inactive step only loads the box (live from the next active step): Yamazaki's 6A
                # loads it on an inactive step between its two hits (KOF98: 2 hits, 3 when it counted), K''s crouch D (KOF99: 1)
                fl = s.get('flags', 0); act = bool(fl & 0x100)
                if ab: live = ab
                ab = live if act else None
                new = ab is not None and not (prev_act and prev_chain)
                prev_act, prev_chain = ab is not None, bool(fl & 0x4000)
                fwd = -s.get('dx', 0); assert -128 <= fwd <= 127, (n, m, fwd)   # KOF x: negative = forward
                steps.append(f'{{{s["frame"]}, {s["ticks"]}, {(1 if ab else 0) | (2 if hb else 0) | (4 if new else 0)}, {bb(hb)}, {bb(ab)}, {fwd}, {s.get('hy', 0)}}}')
            c.append(f'static const bstep_t {n}_{m}[] = {{' + ', '.join(steps) + '};')
        tdata = (roster().get(n) or {}).get('throws') or {}
        thr = []
        for t in THROWS:
            th = ch.get('throws', {}).get(t)
            if t == 'throw_d' and tdata.get('back') == 'throw_c': th = None   # (the back throw = C's turned: bthrow_t turn)
            if not th: thr.append('{0, 0x100, 0, 0, 0xFFFF, 0xFFFF, 0xFFFF, 0, 0, 0xFF, 0xFF, 0xFFFF, 0, 0, %d}' % (t == 'throw_d' and tdata.get('back') == 'throw_c')); continue
            out, info = throw_rows(game, n, th, pkeys, tdata.get('front', {}).get(t))
            c.append(f'static const bthrow_row_t {n}_{t}[] = {{' + ', '.join(out) + '};')
            sp = tdata.get('speed', {}).get(t, THROW_SPEED if th.get('rom') else CAPTURED_THROW_SPEED)
            tfx = throw_fx_of(ch, t)
            thr.append(f'{{{len(out)}, {sp}, {n}_{t}, {info["ret"]}, {info["rel"]}, {info["land"]}, {tfx["row"]}, {tfx["dx"]}, {tfx["dy"]}, 0xFF, 0xFF, {0xFFFF if th.get('grab_frame') is None else th['grab_frame']}, {th.get('stun', 0)}}}')
        c.append(f'static const bthrow_t {n}_throws[BT_COUNT] = {{' + ', '.join(thr) + '};')
        th = ch.get('throws', {}).get(THROW_X)               # its extra paired throw (revamp 3: Ralf's 426B), bm_xthr
        if th:
            out, info = throw_rows(game, n, th, pkeys, tdata.get('front', {}).get(THROW_X))
            c.append(f'static const bthrow_row_t {n}_{THROW_X}[] = {{' + ', '.join(out) + '};')
            sp = tdata.get('speed', {}).get(THROW_X, THROW_SPEED if th.get('rom') else CAPTURED_THROW_SPEED)
            tfx = throw_fx_of(ch, THROW_X)
            c.append(f'static const bthrow_t {n}_xthrow = {{{len(out)}, {sp}, {n}_{THROW_X}, {info["ret"]}, {info["rel"]}, {info["land"]}, {tfx["row"]}, {tfx["dx"]}, {tfx["dy"]}, 0xFF, 0xFF, 0xFFFF, 0}};')
        hl = []
        for k in HOLDS:
            hd = tdata.get('hold') or {}
            out, (ha, hs) = hold_rows(ch, n, game, k, hold_move(ch, n, tdata, k), pkeys, hd.get('dx'), (hd.get('startup') or {}).get(k),
                                     k in (hd.get('multi') or []))
            c.append(f'static const bthrow_row_t {n}_hold_{k}[] = {{' + ', '.join(out) + '};')
            hsx = (hd.get('sfx') or {}).get(k)          # its hit sound as a normal button's (game.json hold.sfx {k: 'A'}): SX_* + 1
            hsx = 0 if hsx is None else ['A', 'B', 'C', 'D', 'CD'].index(hsx) + 1
            hl.append(f'{{{len(out)}, 0x100, {n}_hold_{k}, {len(out)}, 0xFFFF, 0xFFFF, 0xFFFF, 0, 0, {ha}, {hs}, 0xFFFF, 0, {hsx}}}')
        c.append(f'static const bthrow_t {n}_holds[{len(HOLDS)}] = {{' + ', '.join(hl) + '};')
        # every special of its pool (special_pool) is in the ROM, in pool order (bm_spec.c, the first program MB): the four
        # roles (D, forward+D, down+D, up+D) pick from it through a map ({n}_spmap, game.json's specials; fighter.c
        # spec_tab in RAM, so the Brawler Lab's Characters tab remaps them live with a data pack)
        pool = special_pool(ch, n)
        sps = [dict(special_play(sp), fighter=n) for sp in pool]
        vk, vsug, vmp, vtab, vmore = voice_data(ch, n, game, pool, sps)   # (before the specials: their programs send voices)
        for k, sp in enumerate(sps):
            pjs = [dict(pj, spawn_row=sum(1 for i in sp['keep'] if i < pj['spawn_row']))   # spawn rows in the script as
                   for pj in played_projectiles(sp)]                                     # played (frozen rows dropped)
            for pj, q in zip(pjs, played_projectiles(sp)):   # an effect running with the script rows: the kept ones
                if pj.get('follow', 0) & 4:
                    pj['rows'] = [q['rows'][i - q['spawn_row']] for i in sp['keep'] if 0 <= i - q['spawn_row'] < len(q['rows'])]
            pframes = {r[0] for pj in pjs for r in pj['rows'] + pj['end'] + (pj['child']['rows'] if pj['child'] else [])}
            if pjs:                                      # the projectile entities draw and hit; the script keeps
                cs.append(projectile_c(n, k, pjs, game, sp))  # the other objects (effects: they hit nothing)
            out = []
            rows_ = special_rows(sp); opens = [i for i, r in enumerate(rows_) if r[2] & 2] + [len(rows_)]
            sl = {}                                      # a hit's reel slide (px, the opponent's in the capture): its
            for a_, b_ in zip(opens, opens[1:]):         # opening row's vx when it carries nothing
                sl[a_] = next((sp['slide'][j] for j in range(a_, b_) if sp['slide'][j] is not None), 0)
            for i, ((f, x, hgt, objs), (hb, ab, hit, dmg)) in enumerate(zip(sp['script'], rows_)):
                ob = []
                objs = [o for o in objs if o[0] not in pframes]
                for of, ox, oh, same in objs[:2]:
                    b = (0, 0, 0, 0)                     # script objects are effects: what hits is a projectile
                    ob.append(f'{{{of}, {ox}, {oh}, {same}, {sp["objreact"] + 1 if sp["objreact"] is not None else 0}, {bb(b)}}}')
                ob += ['{0xFFFF, 0, 0, 0, 0, {0, 0, 0, 0}}'] * (2 - len(ob))
                cv = sp['carry'][len(out)]
                out.append(f'{{{f}, {x}, {hgt}, {bb(ab)}, {hit | (4 if cv else 0)}, {dmg}, {{{", ".join(ob)}}}, {cv[0] if cv else sl.get(i, 0)}, '
                           f'{cv[1] if cv else 0}, {hit_fx(sp, i, game) if hit & 2 else 0}}}')
            if prog_only(sp): out = out[:1]               # (its program plays it: one row in the ROM, prog_only)
            cs.append(f'static const bspec_row_t {n}_sp{k}[] = {{' + ', '.join(out) + '};')
            if sp['parts']:                              # its follow-ups (fighter.c "follow-ups")
                cs.append(f'static const bspart_t {n}_sp{k}_parts[] = {{' + ', '.join(
                    f'{{{p["first"]}, {p["end"]}, {0xFF if p["next"] is None else p["next"]}, 0}}' for p in sp['parts']) + '};')
                cs.append(f'static const bslink_t {n}_sp{k}_links[] = {{' + ', '.join(
                    '{%d, %d, %d, %d, %d, %d, %d, %d}' % ((l['from'], l['to']) + link_c(l) + (1 if l['at'] == 'now' else 0, l['window'][0], l['window'][1]))
                    for l in sp['links']) + '};')
            if rom_ok(sp) and sp['rom'].get('follow_links'):   # a ROM special's follow-ups: its program decides (P_CHECK, PC_LINK);
                rp = sp['rom']['parts']; st_ = sp['rom']['states']   # links bit k = the press of link k (in / dir), parts
                sp['parts'] = [{'first': st_.index(p['states'][0]), 'end': st_.index(p['states'][-1]) + 1, 'next': None} for p in rp]   # their states (anims)
                sp['links'] = [{'from': l['from'], 'to': l['to'], 'on': 'input', 'input': l['input'], 'at': 'end', 'window': [0, 0xFFFF]}
                               for l in sp['rom']['follow_links']]
                # bit k of a P_CHECK / PC_LINK mask = the k-th distinct input (handlers98.FOLLOW_INPUTS order)
                order = sp['rom']['links']; sp['links'].sort(key=lambda l: order.index(l['input']))
                byin = {}
                for l in sp['links']: byin.setdefault(l['input'], l)
                sp['links'] = [byin[i] for i in order if i in byin] + [l for l in sp['links'] if byin.get(l['input']) is not l]
                cs.append(f'static const bspart_t {n}_sp{k}_parts[] = {{' + ', '.join(
                    f'{{{p["first"]}, {p["end"]}, 0xFF, 0}}' for p in sp['parts']) + '};')
                cs.append(f'static const bslink_t {n}_sp{k}_links[] = {{' + ', '.join(
                    '{%d, %d, %d, %d, %d, %d, %d, %d}' % ((l['from'], l['to']) + link_c(l) + (0, l['window'][0], l['window'][1]))
                    for l in sp['links']) + '};')
            if rom_ok(sp): cs.append(rom_c(n, k, sp, game, prog_voice_res(n, game, pool[k]['input'], vsug, vmp) if kof_prog(sp, game) or step_voiced(sp) else None))   # read from the ROM: played by its program
        assert len(sps) < 255, n
        for k, sp in enumerate(sps):                     # the Lab build's LAB special: its index and its animations' ids
            if sp['input'] == 'LAB' and rom_ok(sp) and sp['rom'].get('lab'): LABINFO[n] = (k, sp['rom']['lab_ids'])
        pooldata[n] = [special_info(sp, game) for sp in sps]
        cs.append(f'const bspec_t {n}_specials[{max(1, len(sps))}] = {{' + (', '.join(
            f'{{{1 if prog_only(sp) else len(sp["script"])}, {rom_inv(sp) if rom_ok(sp) else rise_inv(sp)}, {len(sp["parts"])}, {len(played_projectiles(sp))}, {n}_sp{k}, {f"{n}_pj{k}" if played_projectiles(sp) else 0}, '
            + (f'{n}_sp{k}_prog, {n}_sp{k}_an, {f"{n}_pj{k}r" if sp["rom"]["objects"] else 0}, ' if rom_ok(sp) else '0, 0, 0, ')
            + (f'{n}_sp{k}_parts, {n}_sp{k}_links, {len(sp["links"])}' if sp['parts'] else '0, 0, 0')
            + (', %d, %d, {0x%04X, 0x%04X}' % (*sp['backdrop']['rows'], *sp['backdrop']['colours']) if sp.get('backdrop') else
               ', 0, 0, {0x%04X, 0}' % sp['rom']['bighit_col'] if rom_ok(sp) and sp['rom'].get('bighit_col') is not None else ', 0, 0, {0, 0}')   # (SS2's big hit:
                                                         # its backdrop colour, fighter.c big_hit; TODO #193)
            + ', %d, %d, %d, 0' % flash_c(sp) + vl_c(n, k, sp) + '}'
            for k, sp in enumerate(sps)) or '{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}') + '};')
        c.append(f'extern const bspec_t {n}_specials[];')
        c.append(f'static const uint8_t {n}_pvox[] = {{' + ''.join(f'{a}, {b}, {d}, {e}, ' for sp in sps for a, b, d, e in sp.get('_pvox', ())) + '0xFF};   /* its ROM specials\' step voices */')
        c.append(f'static const uint8_t {n}_pfx[] = {{' + ''.join(f'{a}, {b}, {d}, {e}, ' for sp in sps for a, b, d, e in sp.get('_pfx', ())) + '0xFF};   /* its ROM specials\' step effects */')
        hsk = [(0xFE, mi, i, st_['spark']) for mi, m in enumerate(MOVES) for i, st_ in enumerate(source(ch, m)['steps']) if st_.get('spark')] + \
              [e for sp in sps for e in sp.get('_hspk', ())]    # its source's hit sparks (TODO #215): normals, then specials
        if ch.get('hit_sparks'):
            assert hsk and all(0 < (e[3] & 0x3F) <= len(ch['hit_sparks']) for e in hsk), n
            c.append(f'const uint8_t {n}_hspk[] = {{' + ''.join(f'{a}, {b}, {d}, {e}, ' for a, b, d, e in hsk) + '0xFF};   /* its hit sparks: where, animation, step, spark */')
            cs.append(projectile_c(n, 'hs', ch['hit_sparks'], game, {'input': 'HIT SPARK'}) + f'\nextern const uint8_t {n}_hspk[];')
        segs = move_segments(ch, n, sps)                         # each move's segments (retiming, fighter.c rt_*)
        SEGS[n] = segs
        c.append(f'static const uint16_t {n}_seg[] = {{' + ', '.join(map(str, seg_table(segs))) + '};   /* its moves\' segments (retime.py): [moves, offset per move (0 none)...], then [n, source frames...] */')
        c.append(f'static const uint8_t {n}_air[] = {{' + ', '.join(map(str, air_table(ch, n))) + '};   /* its air specials (TODO #221) */')
        c.append(f'static const uint8_t {n}_spmap[BS_COUNT] = {{' + ', '.join(str(spec_index(pool, sp)) for sp in pick_specials(ch, n)) + '};')
        vdata[n] = {'keys': vk, 'suggest': vsug, 'map': vmp, 'nvoice': len(V.bank(n)),
                    'at': {k: v[1] for k, v in vsug.items()}, 'more': vmore,
                    'prog': sorted({res(ix) & 0x7F for q, sp in zip(pool, sps) if kof_prog(sp, game) or step_voiced(sp)
                                    for res in [prog_voice_res(n, game, q['input'], vsug, vmp)]
                                    for ix in [op[1] for op in sp['rom'].get('ops') or [] if op[0] == 'vsend'] +
                                              [x for st in sp['rom']['states'] for s_ in sp['rom']['anims'][st]['steps'] for x in s_.get('voices', [])]} - {0})}
        c.append(f'static const uint8_t {n}_voices[] = {{' + ', '.join(map(str, vtab)) + '};   /* voices.py table */')
        c.append(f'static const uint8_t {n}_vmore[] = {{' + ''.join(f'{a}, {b}, {d}, ' for a, b, d in vmore) + '0xFF};   /* voices.py extras */')
        c.append(f'static const uint16_t {n}_vposes[VP_COUNT + 1] = {{' + ', '.join(str(v if v >= 0 else 0xFFFF) for v in ptable[n]) + ', 0xFFFF};')
        fps = fpose_steps(ch)                                    # the flash pose (TODO #145)
        hd = lambda a: (ch.get('flash_heads') or {}).get(str(a)) or ch.get('flash_head', (0, 0))   # (each step's head)
        c.append(f'static const bfpose_t {n}_fpose[{max(1, len(fps))}] = {{' + (', '.join(f'{{{a}, {k}, {v}, {hd(a)[0]}, {hd(a)[1]}}}' for a, k, v in fps) or '{0, 0, 0, 0, 0}') + '};')
        fpl = ch.get('flash_pal')                                # the pose's own palette (TODO #191: SS2's rage colours)
        c.append(f'static const uint16_t {n}_fpal[{16 * len(ch["block_palettes"]) if fpl else 1}] = {{' +
                 (', '.join(f'0x{v:04X}' for row in fpl['sets'] for v in row) if fpl else '0') + '};')
        fk = flk_of(ch)                                         # SS2's second-layer flicker (TODO #193)
        c.append(f'static const uint16_t {n}_flk[{16 * len(ch["block_palettes"]) if fk else 1}] = {{' +
                 (', '.join(f'0x{v:04X}' for row in fk['sets'] for v in row) if fk else '0') + '};')
        c.append(f'static const banim_t {n}_anims[BA_COUNT] = {{' + ', '.join(
            f'{{{len(source(ch, m)["steps"])}, {1 if source(ch, m)["mode"] == "hold" else 0}, {arr[id(source(ch, m))]}}}' for m in MOVES) + '};')
    lab = {'ba': MOVES, 'route_moves': R.MOVE_NAMES, 'inputs': R.INPUTS, 'fighters': []}
    for ci, (game, n, ch, off) in enumerate(chars):           # chain routes: tools/brawler/routes/<n>.json or the default
        has = {m for m in MOVES if any(k in ch['anims'] for k in SOURCES.get(m, [m]))}
        sps = pick_specials(ch, n)
        base = R.load(n, roster()[n]['routes'])
        tree = R.chain_tree(n, base, roster()[n].get('chain'), has)   # the chain core (revamp 1A)
        blob = R.encode(tree, MOVES, has, [sp is not None for sp in sps])
        c.append(f'static const uint8_t {n}_routes[] = {{' + ', '.join(map(str, blob)) + '};')
        hsnd = [(MOVES.index(m), v) for m, v in R.hit_sounds(tree).items()]   # its hits' own sounds (bm_hsnd)
        hsd = ((roster()[n].get('throws') or {}).get('hold') or {}).get('sound') or {}
        for k, v in hsd.items():
            assert k in HOLDS, f'{n}: throws.hold.sound: {k} (hit / fin)'
            hsnd.append((0xF0 + HOLDS.index(k), R.sound_codes({'move': f'hold {k}', 'sound': v})))
        c.append(f'static const uint8_t {n}_hsnd[] = {{' + ''.join(f'{k}, {len(v)}, ' + ''.join(f'0x{x:02X}, ' for x in v) for k, v in hsnd) + '0xFF};   /* its hits\' own sounds */')
        lab['fighters'].append({'id': ci, 'game': game, 'name': n, 'tree': tree, 'default': R.default_tree(), 'has': sorted(has), 'routes_file': roster()[n]['routes'] is not None,
                                'moves': {m: R.frame_data(source(ch, m)['steps']) for m in R.MOVE_NAMES if m in has},
                                'segs': {'moves': {m: v for m, v in zip(MOVES, SEGS[n][:len(MOVES)]) if v}, 'specials': SEGS[n][len(MOVES):]},
                                'specials': {k: (sp['input'] if sp else None) for k, sp in zip(R.SPECIALS, sps)},
                                'pool': pooldata[n], 'suggest': [sp['input'] if sp else None for sp in suggest_specials(ch, n)],
                                'voices': vdata[n],
                                # the chain tool (revamp 5, chainlab/chaintool.js): the chain's config and per move the
                                # base node a named link takes (routes.chain_piece), so the page assembles chains as chain_tree
                                'chain_cfg': roster()[n].get('chain'), 'chain_base': R.chain_base(base, has)})
    json.dump(lab, open(os.path.join(outdir, 'chainlab.json'), 'w'), ensure_ascii=False)
    # the voices the ROM maps (build_snd.py brings only their samples into the V ROM: songs.json "voices")
    json.dump([{'name': n, 'game': game, 'ids': sorted(set(vdata[n]['map'].values()) | {m[1] & 0x7F for m in vdata[n]['more']} | set(vdata[n]['prog']) | {v & 0x7F for _, _, v in fpose_steps(ch) if v}), **({'slot_of': src(n)} if n in ALIAS else {})} for game, n, ch, off in chars],
              open(os.path.join(outdir, 'voice_map.json'), 'w'))
    json.dump({n: [fr.get('record') for fr in ch['frames']] for game, n, ch, off in chars},   # bm frame -> 'id:ROM frame'
              open(os.path.join(outdir, 'bm_frames.json'), 'w'))                          # (romspecials_check.py)
    json.dump(HOLD_LOG, open(os.path.join(outdir, 'hold_hits.json'), 'w'), indent=1)   # startups + hold hit choices (#166 c)
    def form_tail(chars, ch, n):
        f = form_c(chars, ch, n)
        return ', %d, %d, %d, %d' % (f if f else (0, 0, 0, 0))   # (always written: holds follow)
    for game, n, ch, off in chars:                           # the shell's slot: its name in its own area (lab_pack.py)
        if n in ALIAS: c.append(f'static const char {n}_name[16] = "{(roster()[n].get("display") or src(n)).upper()[:15]}";')
    c.append('const bchar_t bm_chars[BC_COUNT] = {')
    for game, n, ch, off in chars:
        p = ch['physics']; sets = ch['block_palettes']
        p = {'hop_vy0': p['jump_vy0'], 'hop_gravity': p['gravity'], 'hop_dx': p['jump_dx'], 'prejump': 3, **p}   # KOF94/95: no hop
        land = ch['anims'].get('land') if game in ('kof96', 'kof98', 'kof99', 'kizuna', 'doubledr', 'samsho2') else None   # SS4 / WHP: KOF's usual 4
        p['land'] = sum(s['ticks'] + 1 for s in land['steps']) + 1 if land else 4
        c.append(f'  {{{n + "_name" if n in ALIAS else chr(34) + (roster()[n].get("display") or n).upper() + chr(34)}, {len(used[n])}, {len(sets)}, {n}_pals, {n}_frames, {n}_anims, {{{fx(p["walk_fwd"])}, {fx(p["jump_vy0"])}, {fx(p["gravity"])}, {fx(p["jump_dx"])}, {fx(p["hop_vy0"])}, {fx(p["hop_gravity"])}, {fx(p["hop_dx"])}, {p["prejump"]}, {p["land"]}}}, {n}_throws, {n}_vposes, {n}_specials, {(off + SRC_BASE) >> 16}, {sum(1 << k for k, m in enumerate(CMDS) if m in ch['anims'])}, {n}_routes, {[q[1] for q in chars].index(n)}, {len(special_pool(ch, n))}, {n}_spmap, {n}_voices, {len(V.bank(n))}, {spec_index(special_pool(ch, n), fury_special(ch, n))}, {{{', '.join(map(str, char_sfx(n)))}}}, {n}_vmore, {spec_index(special_pool(ch, n), fury_max_special(ch, n))}{form_tail(chars, ch, n)}, {n}_holds, {n}_pvox, {n}_pfx, {n}_fpose, {len(fpose_steps(ch))}, {{{', '.join(map(str, ch.get('flash_head', (0, 0))))}}}, {n}_fpal, {used[n].index(ch['flash_pal']['index']) if ch.get('flash_pal') else 0xFF}, {used[n].index(flk_of(ch)['index']) if flk_of(ch) else 0xFF}, {n}_flk, {len(air_specials(ch, n))}, {spec_index(special_pool(ch, n), down_special(ch, n))}}},')
    c.append('};')
    c.append('const bseg_t bm_seg[BC_COUNT] = {' + ', '.join(f'{n}_seg' for _, n, _, _ in chars) + '};   /* (retiming) */')
    c.append('const bair_t bm_air[BC_COUNT] = {' + ', '.join(f'{n}_air' for _, n, _, _ in chars) + '};   /* (TODO #221) */')
    c.append('const bair_t bm_hsnd[BC_COUNT] = {' + ', '.join(f'{n}_hsnd' for _, n, _, _ in chars) + '};   /* (hit sounds) */')
    c.append('const bxthr_t bm_xthr[BC_COUNT] = {' + ', '.join(xthr_c(ch, n) for _, n, ch, _ in chars) + '};   /* (revamp 3) */')
    c += sreact_c()
    # the Lab build (make LAB_FIGHTER=<f>, fighter.c "Lab: try in game"): its fighter, his LAB special's pool index, the
    # $NN of its animations (bspec_t.anims order; the page names an animation by $NN, the game finds its index here);
    # every other build: none (0xFF)
    lf = next(((ci, n) for ci, (_, n, _, _) in enumerate(chars) if n in LABINFO), None)
    h[-1:-1] = ['typedef struct { uint8_t fighter, spec; uint16_t n; const uint16_t *ids; } blab_t;   /* the Lab build (fighter.c '
                '"Lab: try in game"): its fighter (0xFF: not a Lab build), his LAB special (pool index), its n animations\' $NN */',
                'extern const blab_t bm_lab;']                # (before the last entry: its #endif)
    if lf:
        ci, n = lf; k, ids = LABINFO[n]
        li = f'{n}_lab_ids' if n in ALIAS else 'bm_lab_ids'   # (the shell's slot: its table in its own area)
        c.append(f'static const uint16_t {li}[] = {{' + ', '.join(f'0x{v:X}' for v in ids) + '};')
        c.append(f'const blab_t bm_lab = {{{ci}, {k}, {len(ids)}, {li}}};')
        ch = next(ch_ for _, n_, ch_, _ in chars if n_ == n)
        json.dump({'fighter': n, 'id': ci, 'spec': k, 'anims': ['%X' % v for v in ids], 'left_out': ch.get('lab_bad', []),
                   'pool': [sp['input'] for sp in special_pool(ch, n)], 'throws': THROWS, 'ba': MOVES,
                   'moves': {m: '%X' % ch['anims'][m]['slot'] for m in MOVES if m in ch['anims'] and isinstance(ch['anims'][m].get('slot'), int)},
                   'fighters': [n_ for _, n_, _, _ in chars]},
                  open(os.path.join(outdir, 'lab.json'), 'w'), indent=1)
    else: c.append('const blab_t bm_lab = {0xFF, 0xFF, 0, 0};')
    c.append('const int8_t bm_head[BC_COUNT][2] = {' + ', '.join(f'{{{ch["head"][0]}, {ch["head"][1]}}}' for _, _, ch, _ in chars) + '};')
    open(os.path.join(outdir, 'bm_chars.h'), 'w').write('\n'.join(h) + '\n')
    open(os.path.join(outdir, 'bm_chars.c'), 'w').write('\n'.join(c) + '\n')
    cs.append('const bhspark_t bm_hspark[BC_COUNT] = {' + ', '.join(f'{{{n}_hspk, {n}_pjhs}}' if ch.get('hit_sparks') else '{0, 0}'
                                                              for _, n, ch, _ in chars) + '};   /* (TODO #215) */')
    open(os.path.join(outdir, 'bm_spec.c'), 'w').write(dedupe_c('\n'.join(cs)) + '\n')

if __name__ == '__main__':
    outdir = sys.argv[1]
    assert sys.argv[2] == '--roster', __doc__
    specs = [r['bank'] for r in roster(sys.argv[3]).values() if not r.get('slot_of')]
    for r in roster().values():
        if r.get('slot_of'): alias_slot(r['name'], r['slot_of'])
    if sys.argv[4:5] == ['--lab'] and sys.argv[5:6] != ['']:   # the Lab build (make LAB_FIGHTER=<f>): every animation of
        LAB[sys.argv[5]] = lab_entries(sys.argv[5])            # his dictionary in his LAB special (export96.lab_special)
    chars, tiles = build(specs, outdir)
    for game, n, ch, off in chars:
        print(f'{game}:{n}: specials ' + ', '.join(f'{k} {sp["input"] if sp else "-"}' for k, sp in zip(('D', 'fwd+D', 'down+D', 'up+D', 'df+D', 'uf+D'), pick_specials(ch, n))) + ';', end=' ')
        print(f'{len(ch["frames"])} frames, {len([m for m in MOVES if any(k in ch["anims"] for k in SOURCES.get(m, [m]))])}/{len(MOVES)} moves, '
              f'{len(ch["block_palettes"])} colour sets, max cols '
              f'{max(sum(len(p["tiles"]) for p in f["parts"]) for f in ch["frames"])}, command normals: '
              f'{" ".join(m for m in CMDS if m in ch["anims"]) or "-"}')
    print('tiles', tiles - TILE_BASE, f'({(tiles - TILE_BASE) * 128 // 1024} KB)')
