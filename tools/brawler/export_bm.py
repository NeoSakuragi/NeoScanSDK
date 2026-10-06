#!/usr/bin/env python3
"""Brawler fighter data: a beat 'em up subset of each fighter's animations from the KOF dictionaries
(tools/kof96/export96.py, any of KOF96/98/99), written as const 68000 tables + the C1/C2 tiles they use.

    python3 export_bm.py OUTDIR --roster ROSTER.json             -> bm_chars.c/.h, bm_c1.bin, bm_c2.bin

ROSTER.json = build_tables.py's roster view of examples/brawler/game.json (the Makefile writes build/roster.json): per
fighter in bm_chars order, its bank spec (game:name), its select-screen 'watch' pose, its specials (the KOF input of each
of D, forward+D, down+D, up+D, or null) and its chain routes file (null: routes.default_tree()). Tools that import this
module (check_specials.py...) get the roster of examples/brawler/game.json (roster()).

Per fighter: frames (parts: dx, dy, columns, rows, flips, palette index, tile columns), animations (steps: frame, ticks,
one hurt box = union of KOF's hurt boxes, the attack box when the step has one), every colour set (16-colour palettes,
one per palette index), physics (16.16 px/frame). Boxes are KOF's: centre offset from the feet (y < 0 = up) and half
extents, in the sprites' own orientation (ROM sprites face LEFT: mirror x when the fighter faces right).
Tile numbers start at TILE_BASE (1 .. TILE_BASE - 1 hold the stage, banner and sparks)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import export96
import routes as R
import build_tables
import voices as V
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
         'blowback', 'knockdown_flight', 'knockdown_bounce', 'knockdown_fall', 'down', 'getup', 'trip', 'win_a', 'atk_c_crouch',
         'cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d',   # command normals (KOF97+: forward+A / B, down-forward+C / D)
         'blowback_n',                                 # KOF98's blowback when not a counter hit (285; blowback = 283)
         # the two jump heights (tools/kof96/capture/jumps.py, 2026-10-04): jump_* = stick held (KOF states 4/5, 8/9,
         # 12/13), hop_* = stick tapped (15/16, 17/18, 19/20), each with its own animation; air normals per jump kind
         'hop_up_rise', 'hop_up_fall', 'hop_fwd_rise', 'hop_fwd_fall', 'jump_back_rise', 'jump_back_fall',
         'hop_back_rise', 'hop_back_fall', 'atk_c_jump_diag', 'atk_d_jump_diag',
         'atk_c_hop', 'atk_d_hop', 'atk_c_hop_diag', 'atk_d_hop_diag',
         'atk_cd_jump', 'atk_cd_hop',                   # air C+D: KOF state 117, KOF98 / KOF99 hops 124 (capture/aircd.py)
         'watch',                                       # the group photo's pose (select screen): roster watch
         'atk_a_crouch', 'atk_b_crouch']                # crouch A / B (KOF 88 / 97): chain routes (Chain Lab, routes.py)
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
           'atk_cd_hop': ['atk_cd_hop', 'atk_cd_jump']}
def source(ch, m):
    """the KOF animation a brawler move plays (idle when the fighter has none)"""
    return next((ch['anims'][k] for k in SOURCES.get(m, [m]) if k in ch['anims']), None) or ch['anims']['idle']
TILE_BASE = 2048                               # our first fighter tile; 1-2047: stage (1-1535, make_stage_ra.py), banner,
                                               # shadow, corners (make_banner.py), sparks (make_sparks.py); 0 empty
SRC_BASE = export96.TILE_BASE                  # export96 numbers its tiles from here

def sb(v): return v - 256 if v > 127 else v

REACH = 96                                     # px: every normal reaches at least this far forward (beat 'em up)

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
        left, right = min(x - w, -reach), x + w
        if left < 0: right = max(right, 0)
        a = ((left + right) // 2, y, (right - left + 1) // 2, hh)
    return h, a

THROWS = ['throw_c', 'throw_d']                         # BT_* order: ground throws, close, forward+C / forward+D in KOF
# Throw speed (TODO #146 rule 1: no global multiplier): per throw in data, game.json roster[].throws.speed {key: 8.8};
# default 1x for a throw read from the ROM (tools/kof96/throwrom.py: the pilot), the captured scripts (pre-#146, the
# rest of the roster until its pass) keep the pace they had (1.5x, Bruno 2026-10-04)
THROW_SPEED, CAPTURED_THROW_SPEED = 0x100, 0x180
# Hold hits (TODO #146 rule 3): each fighter's own blows in the hold, as paired scripts (bchar_t.holds: HOLDS order):
# the move a hit takes its frames from (game.json roster[].throws.hold {hit, fin}; default close C / close D), its
# startup squeezed to HOLD_STARTUP frames (the last two poses before the blow), the blow and its follow-through as the
# game has them (at most HOLD_TAIL frames), the held victim reeling from the blow
HOLDS = ['hit', 'fin']
HOLD_DEFAULT = {'hit': 'atk_c_close', 'fin': 'atk_d_close'}
HOLD_STARTUP, HOLD_TAIL, HOLD_DX = 3, 14, 40

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
        if game == 'kof94':                             # KOF95's engine: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'kof94')); import export94
            return export94.export(names, tmp, only=set(MOVES))
        if game == 'samsho4':                           # Samurai Shodown IV: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'samsho4')); import export_ss4
            return export_ss4.export(names, tmp, only=set(MOVES),
                                     extra={n: {'watch': tuple(roster()[n]['watch'])} for n in names if n in roster()})
        if game == 'whp':                               # World Heroes Perfect: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'whp')); import export_whp
            return export_whp.export(names, tmp, only=set(MOVES),
                                     extra={n: {'watch': tuple(roster()[n]['watch'])} for n in names if n in roster()})
        if game == 'doubledr':                          # Double Dragon (Technos 1995): its own reader, the same layout
            sys.path.insert(0, os.path.join(HERE, '..', 'doubledr')); import export_dd
            return export_dd.export(names, tmp, only=set(MOVES),
                                    extra={n: {'watch': tuple(roster()[rname(game, n)]['watch']), 'scale': roster()[rname(game, n)].get('scale', 1)}
                                           for n in names if rname(game, n) in roster()})
        if game == 'kizuna':                            # Kizuna Encounter: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'kizuna')); import export_kz
            return export_kz.export(names, tmp, only=set(MOVES),
                                    extra={n: {'watch': tuple(roster()[n]['watch'])} for n in names if n in roster()})
        return export96.export(names, tmp, game, only=set(MOVES) | {k for v in SOURCES.values() for k in v} | set(THROWS) | {'specials'},
                               extra={n: {'watch': tuple(roster()[n]['watch'])} for n in names if n in roster()})
    # one block per fighter, packed into the 64K-tile pages largest first, each into the first page with room
    # (2026-10-04): a fighter's tiles share bits 16-19 (bchar_t.tile_hi -> SCB1 attribute), so a fighter must not cross
    # a page; whole game rosters per block left ~4 MB of padding at the page ends and doubled C to 32 MB when the air
    # C+D animations pushed the last tile past 16 MB. A throw's victim offsets come from the thrower's own export, the
    # victim's poses from its own (vposes), so fighters export independently.
    blocks = []                                         # (game, name, export, tmp dir)
    for game, names in games.items():
        for name in names:
            tmp = os.path.join(outdir, f'tmp_{game}_{name}')
            ex = export(game, [name], tmp)
            assert ex['tiles'] < 0x10000, f'{game}:{name}: {ex["tiles"]} tiles (a fighter must fit one 64K tile page)'
            blocks.append((game, name, ex, tmp))
    pages = [[TILE_BASE, []]]                           # per page: next free tile number, [(block, first tile)]
    for blk in sorted(blocks, key=lambda b: -b[2]['tiles']):
        n = blk[2]['tiles']
        for p, pg in enumerate(pages):
            start = max(pg[0], (p << 16) + 1)           # tile 0 = empty, and with tile_hi it means page start: blank
            if start + n <= (p + 1) << 16: break
        else:
            pages.append([(len(pages) << 16) + 1, []]); p = len(pages) - 1; pg = pages[p]; start = pg[0]
        pg[1].append((blk, start)); pg[0] = start + n
    for p, pg in enumerate(pages):
        for (game, name, ex, tmp), start in pg[1]:
            a = open(os.path.join(tmp, 'kof95_c1.bin'), 'rb').read(); b = open(os.path.join(tmp, 'kof95_c2.bin'), 'rb').read()
            n = ex['tiles']
            if len(c1) // 64 + TILE_BASE < start:       # the gap to this block (page 2's blank tile 0, or a page's end)
                g = start - TILE_BASE - len(c1) // 64; c1 += bytes(g * 64); c2 += bytes(g * 64)
            c1 += a[SRC_BASE * 64:(SRC_BASE + n) * 64]; c2 += b[SRC_BASE * 64:(SRC_BASE + n) * 64]
            chars.append((game, rname(game, name), ex['characters'][name], start - SRC_BASE))
    tile_next = TILE_BASE + len(c1) // 64
    assert tile_next <= 0x100000, f'{tile_next} tiles: past the 20-bit tile number'
    chars.sort(key=lambda c: specs.index(roster()[c[1]]['bank'] if c[1] in roster() else f'{c[0]}:{c[1]}'))   # bm_chars in the command line's order, the order
                                                          # make_hud.py gives the portraits (exports go by game)
    pad = bytearray(TILE_BASE * 64)
    open(os.path.join(outdir, 'bm_c1.bin'), 'wb').write(bytes(pad + c1))
    open(os.path.join(outdir, 'bm_c2.bin'), 'wb').write(bytes(pad + c2))
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
    bd = {'backdrop': dict(sp['backdrop'], rows=[rm(r) for r in sp['backdrop']['rows']])} if sp.get('backdrop') else {}
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
KIND_OF = {0x9C: 29, 0x19: 15, 0x3D: 16, 0x2B: 20, 0x17: 24}   # HIT_SFX rows {code, 0}
SFX_KEYS = ['A', 'B', 'C', 'D', 'CD', 'throw_c', 'throw_d']    # bchar_t.sfx order (fighter.c SX_*)

def sfx_code(n, name):
    assert name in SFX_NAMES, f'{n}: hit_sfx {name!r} is no songs.json sfx name'
    return SFX_NAMES[name]

def move_fx(n, sp, hk):
    """bspec_row_t / bproj_t / P_ANIM fx of a special's hit: kind hk (KOF's), or the sound its use asks for (a fury:
    SDM IMPACT; roster[].hit_sfx[input]); the burn stays the KOF kind's (fire kinds 11, 13, 21: the crackle $2E only they)"""
    r = roster().get(n, {}); want = (r.get('hit_sfx') or {}).get(sp['input'])
    kind = KIND_OF[sfx_code(n, want)] if want else 29 if r.get('fury') and sp['input'] in (r['fury'], 'MAX ' + r['fury']) else hk
    return kind | ((FIRE_COLOUR.get(n, 2) if hk in (11, 13, 21) else 0) << 6)

def char_sfx(n):
    """bchar_t.sfx: per SFX_KEYS the code roster[].hit_sfx gives (0: KOF's own)"""
    h = roster().get(n, {}).get('hit_sfx') or {}
    return [sfx_code(n, h[k]) if k in h else 0 for k in SFX_KEYS]

# the burn's colour: the attacker's flames (KOF98 VRAM during Kyo's and Iori's Oniyaki hits: the victim's sprites
# leave its own palette for palette $58, orange, with Kyo, $5F, purple, with Iori; both always loaded). Purple = 1,
# orange = 2 (fighter.c BURN_PAL); every fire user but Iori burns orange (inference: one flame colour per fighter)
FIRE_COLOUR = {'iori': 1}

R_CODE = {'heavy': R_HEAVY, 'knockdown': R_KNOCKDOWN}

def projectile_c(n, k, pjs, game, sp):
    """C tables of a special's projectiles (export96.projectile_entry, in spawn order): per projectile its flight
    rows, end rows and child (its trail: a bproj_t without boxes), and the array bproj_t {n}_pj{k}[]"""
    def box(b): return '{0, 0, 0, 0}' if b is None else f'{{{sb(b[0])}, {sb(b[1])}, {b[2]}, {b[3]}}}'
    q = lambda v: max(-32768, min(32767, round(v * 8)))   # 1/8 px
    out, defs = [], []
    def one(name, pj, child='0', births=(0, 0, 0), cd=(0, 0)):
        rows = ', '.join(f'{{{f}, {q(x)}, {round(y)}, {box(a[1:] if a else None)}, {box(o)}, {(1 if a else 0) | (2 if o else 0)}, 0}}'
                         for f, x, y, a, o in pj['rows'])
        end = ', '.join(f'{{{f}, {q(x)}, {round(y)}}}' for f, x, y in pj.get('end', [])) or '{0, 0, 0}'
        loop = 0xFF if pj['loop'] is None else pj['loop']
        step = pj['rows'][-1][1] - pj['rows'][-2][1] if len(pj['rows']) > 1 else 0   # the flight's per-frame step
        wrap = q(pj['rows'][-1][1] + step - pj['rows'][loop][1]) if pj['loop'] is not None else 0
        hk = pj.get('hit_kind', 1); hk = hk if 0 < hk <= 32 else 1
        fx = move_fx(n, sp, hk)
        assert len(pj['rows']) < 256 and len(pj.get('end', [])) < 256 and pj.get('spawn_row', 0) < 256, n
        out.append(f'static const bprow_t {name}_r[] = {{{rows}}};\nstatic const bpend_t {name}_e[] = {{{end}}};')
        return (f'{{{len(pj["rows"])}, {loop}, {len(pj.get("end", []))}, {pj.get("kind", 0)}, {pj.get("spawn_row", 0)}, '
                f'{pj["react"] if isinstance(pj.get("react"), int) else R_CODE.get(pj.get("react"), R_KNOCKDOWN)}, {fx}, {int(pj.get("follow") or 0)}, {round(pj.get("spawn_x", 0))}, {round(pj.get("spawn_y", 0))}, '
                f'{wrap}, {name}_r, {name}_e, {child}, {births[0]}, {births[1]}, {births[2]}, {pj.get("sig", 0)}, {q(cd[0])}, {round(cd[1])}}}')
    for j, pj in enumerate(pjs):
        c = pj.get('child'); child, births, cd = '0', (0, 0, 0), (0, 0)
        if c:                                            # its trail: born on the parent's frames b0, b1, then every
            b = c['births']; per = b[-1] - b[-2] if len(b) > 1 else 0   # period (Krauser 0, 1, 7, 13..; Iori 11, 23, 35..)
            assert len(b) < 3 or all(b[i + 1] - b[i] == per for i in range(1, len(b) - 1)), (n, b)
            out.append(f'static const bproj_t {n}_pj{k}_{j}c = ' + one(f'{n}_pj{k}_{j}c', c) + ';')
            child, births, cd = f'&{n}_pj{k}_{j}c', (b[0], b[1] if len(b) > 1 else 255, per), (c['dx'], c['dy'])
        defs.append(one(f'{n}_pj{k}_{j}', pj, child, births, cd))
    out.append(f'static const bproj_t {n}_pj{k}[] = {{' + ', '.join(defs) + '};')
    return '\n'.join(out)

P_OPS = {'anim': 1, 'set': 2, 'mul': 3, 'move': 4, 'fricmove': 5, 'fall': 6, 'nudge': 7, 'dec': 8, 'br': 9, 'resume': 10,
         'resume_at': 11, 'jmp': 12, 'spawn': 13, 'fxoff': 14, 'end': 15, 'adv': 16, 'check': 17, 'part': 18, 'evclr': 19,
         'onhit': 20, 'place': 21, 'hitclr': 22, 'hold': 23, 'unhold': 24, 'sigclr': 25, 'hitoff': 26}   # bm_chars.h P_*
P_REGS = {'vx': 0, 'vy': 1, 'g': 2, 'fric': 3, 'cnt': 4, 'h': 5}

def rom_ok(sp):
    return bool(sp.get('rom')) and 'error' not in sp['rom']

def rom_inv(sp):
    """bspec_t.inv_rows of a ROM special (frames): as down+D invincible up to its last hit or its apex"""
    r = sp['rom']; return max(r['last_hit'], r['apex']) + 1 if max(r['last_hit'], r['apex']) >= 0 else r['length']

def rom_c(n, k, sp, game):
    """a special read from the ROM (tools/kof96/handlers98.export_rom) as C: its animations (bstep_t: flags 1 attack box
    live (KOF $0100, the last box loaded), 2 hurt box, 8 event ($0080), 16 same hit ($4000)), its program (bprim_t), its
    objects (bproj_t, projectile_c). Damage: SPECIAL_DAMAGE split over the hits the whiff model opens; the hits of its
    last hitting state knock down (R_KNOCKDOWN; fighter.c: its last hit only), the earlier ones R_HEAVY, or ROM_REACT's.
    No carry: the victim flies with KOF98's reaction between hits (fighter.c kof_react)"""
    r = sp['rom']; out = []
    def bb(b): return '{0, 0, 0, 0}' if b is None else f'{{{b[0]}, {b[1]}, {b[2]}, {b[3]}}}'
    live = None
    for j, st in enumerate(r['states']):
        a = r['anims'][st]; steps = []
        for s in a['steps']:
            hb, ab = boxes(s['boxes'])
            fl = s['flags']
            if ab: live = ab
            ab = live if fl & 0x100 else None
            steps.append(f'{{{s["frame"]}, {s["ticks"]}, {(1 if ab else 0) | (2 if hb else 0) | (8 if fl & 0x80 else 0) | (16 if fl & 0x4000 else 0) | (32 if fl & 0x2000 else 0) | (64 if ab and s.get("catch") else 0) | (128 if ab and s.get("nostop") else 0) | (4 if ab and s.get("noslide") else 0)}, '
                         f'{bb(hb)}, {bb(ab)}, {-s["dx"]}, {s.get("react", 0) if ab else 0}}}')   # hy: KOF's reaction (handlers98.box_react)
        out.append(f'static const bstep_t {n}_sp{k}_a{j}[] = {{' + ', '.join(steps) + '};')
    out.append(f'static const banim_t {n}_sp{k}_an[] = {{' + ', '.join(
        f'{{{len(r["anims"][st]["steps"])}, {1 if r["anims"][st]["mode"] == "hold" else 0}, {n}_sp{k}_a{j}}}' for j, st in enumerate(r['states'])) + '};')
    if r.get('prims'):                               # a program written by its source's exporter (export_dd: the
        hk = r['hit_kind'] if 0 < r['hit_kind'] <= 32 else 1   # variant table, P_ADD / P_FORM): as given, P_ANIM's
        fx = move_fx(n, sp, hk)                      # hit effect filled in
        assert len(r['prims']) < 255, (n, sp['input'])
        out.append(f'static const bprim_t {n}_sp{k}_prog[] = {{' + ', '.join(f'{{{a}, {b}, {c}, {fx if d is None else d}}}' for a, b, c, d in r['prims']) + '};')
        vt = r.get('vtable') or {}
        if vt.get('nvar'):
            out.append(f'static const int32_t {n}_sp{k}_vars[] = {{' + ', '.join(str(v) for row in vt['rows'] for v in row) + '};')
        if r['objects']: out.append(projectile_c(n, f'{k}r', r['objects'], game, sp))
        return '\n'.join(out)
    total = sum(r['openings'].values())
    each = max(1, SPECIAL_DAMAGE // total) if total else 0
    hitting = [st for st in r['states'] if r['openings'].get(st)]
    hk = r['hit_kind'] if 0 < r['hit_kind'] <= 32 else 1
    fx = move_fx(n, sp, hk)
    ops = []
    for op in r['ops']:
        c = P_OPS[op[0]]
        if op[0] == 'anim':
            st = op[2]; react = ROM_REACT.get((n, sp['input'])) or (R_KNOCKDOWN if hitting and st == hitting[-1] else R_HEAVY)
            ops.append((c, op[1], each | react << 8, fx))
        elif op[0] == 'set':
            v = op[2]; reg = P_REGS[op[1]]
            ops.append((c, reg, 0, round(v * 65536) if reg < 3 or reg == 5 else int(v)))   # 5: the height (16.16)
        elif op[0] == 'mul': ops.append((c, 0, 0, op[1]))
        elif op[0] == 'nudge': ops.append((c, 0, round(op[1]), round(op[2])))
        elif op[0] == 'br': ops.append((c, op[1] | op[2] << 7, -1 if op[3] == 'yield' else op[3], op[4] if len(op) > 4 else 0))
        elif op[0] == 'check': ops.append((c, op[1], 1 if len(op) > 2 else 0, 0))   # b 1: the presses of its hit-stop
        elif op[0] == 'sigclr': ops.append((c, 0, 0, op[1]))
        elif op[0] in ('resume_at', 'jmp'): ops.append((c, 0, op[1], 0))
        elif op[0] == 'onhit': ops.append((c, op[2] if len(op) > 2 else 0, op[1], 0))   # a: the catch's hit-stop (its dead frames - 1)
        elif op[0] == 'place': ops.append((c, 0, 0, round(op[1])))
        elif op[0] == 'spawn': ops.append((c, op[1], 0, 0))
        else: ops.append((c, 0, 0, 0))
    assert len(ops) < 255, (n, sp['input'])
    out.append(f'static const bprim_t {n}_sp{k}_prog[] = {{' + ', '.join(f'{{{a}, {b}, {c}, {d}}}' for a, b, c, d in ops) + '};')
    if r['objects']: out.append(projectile_c(n, f'{k}r', r['objects'], game, sp))
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
           and not (name in NO_EX and sp['input'].startswith('EX '))]
    fury = fury_special(ch, name)
    out = out + [fury] if fury is not None and fury not in out else out
    fm = form_special(ch, name)                     # the form link's transition (vocabulary `form`), when it has one
    out = out + [fm] if fm is not None and fm not in out else out
    mx = fury_max_special(ch, name)                 # its MAX version (down+D, TODO #139), when the bank has one
    return out + [mx] if mx is not None and mx not in out else out


def fury_special(ch, name):
    """the fighter's fury (game.json roster[].fury: its KOF input, any condition; None = none)"""
    want = roster()[name].get('fury') if name in roster() else None
    if not want: return None
    sp = next((sp for sp in ch.get('specials', []) if sp['input'] == want), None)
    assert sp, f'{name}: no fury {want} in its bank'
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
    down+D, TODO #139); None = none (down+D plays the fury)"""
    want = roster()[name].get('fury') if name in roster() else None
    if not want: return None
    return next((sp for sp in ch.get('specials', []) if sp['input'] == 'MAX ' + want), None)


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
        if mt and mt.group(4) != '{}':               # (an empty table keeps its own place: a player that reads a
            key = (mt.group(1), mt.group(3), mt.group(4))   # 0-row object's row 0 reads what follows it, as before)
            if key in seen: ren[mt.group(2)] = seen[key]; continue
            seen[key] = mt.group(2)
        out.append(line)
    return '\n'.join(out)


def prog_only(sp):
    """a program written by its source's exporter (export_dd 'prims'): the script rows are the Brawler Lab's data only
    (chainlab.json), never played (no capture behind them to fall back to): the ROM keeps one row (bspec_t.nrows 1:
    special_pick's 'has a special'), the first program MB is full"""
    return rom_ok(sp) and bool(sp['rom'].get('prims'))

def var_c(n, k, sp):
    """bspec_t vars, nvar, vdef, vanim, vobj, vcols, vdmg, pvoice (vocabulary `variant.parameter_set`): a ROM special's
    parameter rows (export_dd vtable: one row per button), the row played (game.json roster[].variant[input], else the
    source's default: the heaviest), the program's animations / objects per row, the columns, the damage column + 1 (0
    none); pvoice 1: its voices are timed by its frames. Absent (a special without them): all zero"""
    r = sp.get('rom') or {}; vt = r.get('vtable') or {}
    if not vt.get('nvar') and not r.get('voice_frames'): return ''
    if not vt.get('nvar'): return ', 0, 0, 0, 0, 0, 0, 0, 1'
    want = (roster().get(n, {}).get('variant') or {}).get(sp['input'])
    vdef = vt['buttons'].index(want) if isinstance(want, str) else want if want is not None else vt['default']
    assert 0 <= vdef < vt['nvar'], (n, sp['input'], want)
    return f', {n}_sp{k}_vars, {vt["nvar"]}, {vdef}, {vt["vanim"]}, {vt["vobj"]}, {vt["ncol"]}, {vt["vdmg"]}, {1 if r.get("voice_frames") else 0}'

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
    rows = th['victims'].get(n) or next(iter(th['victims'].values()))   # offsets of the mirror match (see README)
    froze = set(th.get('impacts') or []) if not th.get('rom') else set()   # KOF froze there (Ryo's forward+C): the brawler's hit-stop too
    imp = set(throw_impacts(rows, game)) | froze          # blows / floor touches: damage, no freeze (KOF's)
    if th.get('rom'): imp = set(th['impacts']) | ({th['land']} if th.get('land') is not None else set())
    st = lambda r: int(r[5].split('.')[0]) if r[5] and game != 'kizuna' else -1
    if th.get('rom'): rel, land, ret = th['release'], th['land'], th['ret']
    else:
        rel = next((i for i in range(1, len(rows)) if 0 <= st(rows[i]) < THROW_FLIGHT and st(rows[i - 1]) >= THROW_FLIGHT), None)
        land = next((i for i in range(rel + 1, len(rows)) if rows[i][2] + th['timeline'][min(i, len(th['timeline']) - 1)][2] <= 0), None) if rel is not None else None
        ret = len(th['timeline'])
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

def hold_rows(ch, n, game, k, move, pkeys, dx=None):
    """a hold hit (k 'hit', or 'fin' the finisher) as a paired script: the fighter's own `move` (a normal, its frames),
    its startup squeezed to HOLD_STARTUP frames (the last poses before the active step, 1 + 2 frames), the active step
    (impact on its first frame) and what follows, at most HOLD_TAIL frames; the victim held in the throw's grab pose
    (forward+C row 0) until the blow, then reeling (BA_HIT_STAND_LIGHT; the finisher knocks it down: fighter.c), dx px
    in front (game.json roster[].throws.hold.dx; default the throw's row 0, at most HOLD_DX: in contact, Final Fight);
    the first row's victim is also the hold's own pose (fighter.c grab)"""
    dx = HOLD_DX if dx is None else dx
    a = source(ch, move); steps = a['steps']
    act, live = None, None                             # its first active step (the normals' rule: $0100 with a box loaded)
    for j, s_ in enumerate(steps):
        ab = boxes(s_['boxes'], REACH)[1]
        if ab: live = ab
        if live and s_.get('flags', 0) & 0x100: act = j; break
    if act is None: act = min(len(steps) - 1, 1)
    pre = [(steps[act - 2]['frame'], 1)] if act >= 2 else []
    pre += [(steps[act - 1]['frame'], HOLD_STARTUP - len(pre))] if act >= 1 else []
    post = [(s_['frame'], s_['ticks'] + 1) for s_ in steps[act:]]
    th = ch.get('throws', {}).get('throw_c')
    if th:
        r0 = (th['victims'].get(n) or next(iter(th['victims'].values())))[0]
        v = vocab(game, r0[5]); held = (pkeys.index(v) if r0[0] is not None and r0[0] >= 0 and v in pkeys else 255, min(r0[1], dx), r0[2], r0[3])
    else: held = (255, dx, 0, 0)
    rows = []
    for fr, d in pre:
        for _ in range(d): rows.append(f'{{{fr}, 0, 0, {held[0]}, {held[3]}, {held[1]}, {held[2]}}}')
    hit = len(rows)
    for fr, d in post:
        for _ in range(d):
            if len(rows) - hit >= HOLD_TAIL: break
            first = len(rows) == hit
            rows.append(f'{{{fr}, 0, 0, {MOVES.index("hit_stand_light")}, {32 | held[3] | (4 if first else 0)}, {held[1]}, {held[2]}}}')
    return rows

VICTIM_POSES = {g: json.load(open(os.path.join(HERE, '..', 'kof96', f'victim_poses{g[3:]}.json')))['poses']
                for g in ('kof96', 'kof98', 'kof99')}
VICTIM_POSES['kizuna'] = json.load(open(os.path.join(HERE, '..', 'kizuna', 'victim_poses_kz.json')))['poses']   # Kim's throw

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
                for r in t['victims'].get(n, []):
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
    slot_of = {m: (source(ch, m).get('slot'), len(source(ch, m)['steps'])) for m in MOVES}
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
    mp = V.mapping(roster()[n].get('voices'), sug)
    more = V.extras(n, ks, sug, mp, [(sp['input'], p['keep']) for sp, p in zip(pool, sps)])
    return ks, sug, mp, V.table(ks, sug, mp, len(V.bank(n)), n), more

def write_c(chars, outdir):
    pkeys, ptable = poses(chars)
    h = ['/* Generated by tools/brawler/export_bm.py from the KOF dictionaries. Do not edit. */',
         '#ifndef BM_CHARS_H\n#define BM_CHARS_H\n#include <stdint.h>\n',
         'typedef struct { int16_t dx, dy; uint8_t cols, rows, hflip, vflip, pal; const uint16_t *tiles; } bpart_t;   /* tiles: cols*rows column-major, 0 = empty; pal: palette index of the fighter */',
         'typedef struct { uint8_t nparts, ncols; const bpart_t *parts; } bframe_t;   /* ncols: hardware sprites the frame uses */',
         'typedef struct { int8_t x, y; uint8_t w, h; } bbox_t;                       /* centre from the feet (y<0 up), half extents; sprite faces left */',
         'typedef struct { uint16_t frame; uint8_t ticks, flags; bbox_t hurt, atk; int8_t dx; uint8_t hy; } bstep_t;   /* flags: 1 = attack box, 2 = hurt box, 4 = opens a new hit (multi-hit normals; in a ROM special: 4 the victim reels without sliding, 8 event, 16 same hit, 32 window, 64 a catch box, 128 no hit-stop: KOF\'s class 4 barrage hits, TODO #139); dx: px the fighter moves forward as the step starts (KOF\'s $FB move); hy: height in px during the step (command normals that hop: export96.cmd_frames); in a ROM special\'s anims (bspec_t.anims) the victim\'s reaction to its attack box instead, packed R_* standing | juggled << 4 (KOF\'s reaction table: tools/kof96/handlers98.box_react; 0 = the P_ANIM reaction) */',
         'typedef struct { uint8_t nsteps, hold; const bstep_t *steps; } banim_t;     /* hold: stop on the last step */',
         'typedef struct { int32_t walk, jump_vy0, gravity, jump_dx, hop_vy0, hop_gravity, hop_dx; uint8_t prejump, land; } bphys_t;   /* 16.16 px per frame (KOF ROM: export96 physics); jump_* = the regular jump (stick held), hop_* = the hop (stick tapped); jump_dx / hop_dx: horizontal speed of a forward or back jump; prejump: frames on the ground before take-off (KOF: the prejump animation, the frames in which a release makes the jump a hop); land: frames on the floor after a jump (KOF: the landing animation\'s steps at ticks + 1 frames each, + 1, measured: KOF98 4, Terry / Rugal / Goenitz 5) */',
         'typedef struct { uint16_t tframe; int16_t tx, ty; uint8_t vpose, flags; int16_t vx, vy; } bthrow_row_t;   /* one video frame of a paired script (vocabulary hold.paired_script): thrower frame + offset from its start (forward +, up +); victim posture (0xFF: none; flags 32: a BA_* animation it plays instead, its flight: blowback, knockdown...) + offset from the thrower; flags 1 = victim faces the thrower\'s way (its facing at the grab), 2 = victim drawn in front (a data override: game.json roster[].throws.front; else always behind the grabber, TODO #146), 4 = impact (the blow lands / the victim hits the floor: damage, spark, sound), 16 = the game froze there (hit-stop), 8 = the thrower has turned around (drawn mirrored; offsets stay in its grab facing) */',
         'typedef struct { uint16_t nrows, speed; const bthrow_row_t *rows; uint16_t ret, rel, land, pad; } bthrow_t;   /* speed: 8.8 script rows a frame (fighter.c throw_update); ret: the CONTROL RETURN row (the thrower acts again from it; the victim plays its rows on alone to nrows, then lies down); rel / land: the release row and the landing row (0xFFFF: none): from rel to land the victim is a thrown body (spawn.body: it knocks down the enemies it touches) */',
         'typedef struct { uint16_t frame; int16_t x, y; uint8_t same, react; bbox_t box; } bsobj_t;   /* special\'s object (projectile): frame (0xFFFF = none), offset from the fighter\'s start, faces the fighter\'s way, react: the victim\'s reaction R_* + 1 measured in the game (0: knockdown); box: none (an effect: what hits is the special\'s projectile, bspec_t.proj) */',
         'typedef struct { uint16_t frame; int16_t x, y; bbox_t atk; uint8_t hit, dmg; bsobj_t obj[2]; int16_t vx; uint8_t vy, fx; } bspec_row_t;   /* one video frame of a special: fighter frame + offset from its start (forward +, up +), body attack box; hit: 1 box live, 2 opens a new hit (vx without 4: the px a reel slides the victim, fighter.c kof_react), 4 the target is carried at vx (forward from the fighter) / vy (height; grabs only), 8 contact (no damage), 16 a hit here goes on to the continuation, bits 5-7 the victim\'s reaction R_* (export_bm special_rows); dmg: damage of the hit it opens; fx (rows opening a hit): KOF98 hit effect, bits 0-5 the hit kind (the victim\'s hit sounds, fighter.c HIT_SFX), bits 6-7 the burn (1 purple, 2 orange) */',
         'typedef struct { uint16_t frame; int16_t x, y; bbox_t atk, own; uint8_t flags, pad; } bprow_t;   /* one frame of a projectile\'s flight: frame, x from its spawn point in 1/8 px (forward +), height px, attack box (live when flags & 1: the game\'s +$90 box while +$7C bit 0), own box (the box another projectile\'s attack meets: a clash; flags & 2) */',
         'typedef struct { uint16_t frame; int16_t x, y; } bpend_t;   /* a projectile\'s end after its hit: frame, x from the impact in 1/8 px, height */',
         'typedef struct bproj { uint8_t nrows, loop, nend, kind, spawn_row, react, fx, follow; int16_t spawn_x, spawn_y, wrap_x; const bprow_t *rows; const bpend_t *end; const struct bproj *child; uint8_t child_b0, child_b1, child_period, sig; int16_t child_dx, child_dy; } bproj_t;   /* sig (TODO #139): its thrower\'s +$D1 bits 7 / 6 (fighter_t.pflags PF_SIG7 / PF_SIG6) it sets at its end, bits 5 / 4 = the same at its hit (Raging Storm\'s side effects, K\'\'s shot); follow: 1 = an effect pinned to its thrower (3: it ends at its last row) (rows: offsets from it; a ROM special\'s, ended by P_FXOFF or the special\'s end: Burn Knuckle\'s flame); bit 4: its rows run with its thrower\'s script rows (row = the thrower\'s row - spawn_row: frozen with its hit-stop), it ends when the thrower leaves them (Kizuna\'s Hienzan pillar, TODO #144: a script special\'s pinned effect, not a shot); child: the trail it spawns (no boxes) on its frames child_b0, child_b1 (255: none), then every child_period, child_dx (1/8 px, forward) / child_dy from its place then (KOF: objects owned by the projectile: Krauser\'s Blitz Ball, Iori\'s Yami Barai); a special\'s projectile (tools/kof96/projectiles96): an entity of its own from the thrower\'s script row spawn_row, at spawn_x / spawn_y (px, from the script\'s origin, forward +); rows = its flight; loop: the row the flight repeats from (0xFF: it dies when its rows end, its animation over), each repeat moving it wrap_x (1/8 px) on; kind: KOF object +$F5, 1 = travelling (its hit ends it: the end rows play), 3 = an eruption (plays on, its attack spent); react R_*, fx: hit effect (bspec_row_t.fx); dies off screen (x - camera <= -64 or >= 384: KOF96/98/99\'s own test) */',
         'typedef struct { uint8_t op, a; int16_t b; int32_t v; } bprim_t;   /* one primitive of a special read from the ROM (tools/kof96/handlers98.py, handlers98.md; export_bm rom_c): op P_*, operands a / b / v (fighter.c prog_update) */',
         'enum { P_ANIM = 1, P_SET, P_MUL, P_MOVE, P_FRICMOVE, P_FALL, P_NUDGE, P_DEC, P_BR, P_RESUME, P_RESUMEAT, P_JMP, P_SPAWN, P_FXOFF, P_END, P_ADV, P_CHECK, P_PART, P_EVCLR, P_ONHIT, P_PUT, P_HITCLR, P_HOLD, P_UNHOLD, P_SIGCLR, P_HITOFF, P_ADD, P_FORM };   /* P_ADD a = register (0 vx, 1 vy, 4 cnt) += v (16.16; gravity applied before the move: Double Dragon\'s order); P_FORM the form link\'s swap now (fighter.c form_swap: the special ends); P_MUL a = 1: vy *= v; (TODO #139) P_HITOFF its hit flag cleared (KOF +$E1 bit 7, PC_HIT); P_SIGCLR v = the +$D1 bits 7 / 6 kept (an andi: its objects\' signals cleared); P_EVCLR the step\'s event consumed (KOF: andi on +$7D); P_ONHIT b = the catch routine (KOF +$19C: a catch box\'s hit, bstep_t flags 64, runs it after a dead frame); P_PUT v = the caught victim put v px in front, facing the attacker (KOF $25032); P_HITCLR the any-hit flag cleared (KOF +$E3 bit 7, PC_HITANY); P_HOLD / P_UNHOLD the caught victim held in place / let go (KOF +$E4 bit 4: its reactions stay a standing reel while held); P_ADV the animation one more tick (the engine called again on the same state); P_CHECK a = the follow-up links read this frame (a press of link k this frame arms bit k: fighter_t.plink); P_PART the armed links cleared (a new part); bprim_t.op: P_ANIM a = bspec_t.anims index, b = damage | reaction << 8 of the hits it opens, v = hit effect; P_SET a = register (0 vx, 1 vy, 2 g: 16.16; 3 fric: 0.16; 4 cnt), v; P_MUL vx *= v / 65536; P_MOVE x += vx; P_FRICMOVE vx *= fric, x += vx; P_FALL height += vy, vy -= g (landed / falling flags); P_NUDGE b px forward, v px up; P_DEC cnt -= 1; P_BR a = condition PC_* | 0x80 when true, b = the op to go to (-1: the frame ends, it resumes next frame); P_RESUME the resume point = the next op; P_RESUMEAT b; P_JMP b; P_SPAWN a = bspec_t.robj index; P_FXOFF its attached effects end; P_END */',
         'enum { PC_END, PC_EVENT, PC_LAND, PC_FALL, PC_CNT, PC_HIT, PC_OFF, PC_ALWAYS, PC_STEPEV, PC_WINDOW, PC_LINK, PC_HITANY, PC_SIG7, PC_SIG7C, PC_SIG6, PC_FAR, PC_LOW };   /* PC_LOW the height below v px (KOF cmpi on +$20, Billy 623D); PC_FAR the target farther than v px (KOF +$BC, K\'\'s dash); PC_SIG7 / PC_SIG6 its object set +$D1 bit 7 / 6 (bproj_t sig), PC_SIG7C bit 7 consumed (bclr); PC_HITANY a hit landed since P_HITCLR; PC_STEPEV the step has KOF\'s $0080 (bstep_t flags 8, not consumed by P_EVCLR / PC_EVENT), PC_WINDOW $2000 (flags 32, a follow-up window), PC_LINK an armed link in the P_BR\'s v mask; P_BR conditions: animation over, an event step entered (consumed), landed, falling, counter < 0, the move hit, off screen, always */',
         'typedef struct { uint16_t first, end; uint8_t next, pad; } bspart_t;   /* a special\'s part: script rows [first, end), the part played when it ends (0xFF: the move ends; fighter.c "follow-ups") */',
         'typedef struct { uint8_t from, to, trig, in, dir, at; uint16_t lo, hi; } bslink_t;   /* a follow-up: from part `from` to part `to`; trig 1 a hit landed (LK_HIT), 2 a press (LK_IN: buttons `in` IN_*, stick `dir` = a C role BS_* by d_input, 0xFE the role the move started with, 0xFF any) inside the window [lo, hi) (script rows); at 1 = switch at once (LK_NOW), 0 = when the part ends */',
         'typedef struct { uint16_t nrows, inv_rows, nparts, nproj; const bspec_row_t *rows; const bproj_t *proj; const bprim_t *prog; const banim_t *anims; const bproj_t *robj; const bspart_t *parts; const bslink_t *links; uint16_t nlinks, bd_first, bd_end, bd_col[2]; int16_t sf_dx, sf_dy; uint8_t sf_anchor, sf_pad; const int32_t *vars; uint8_t nvar, vdef, vanim, vobj, vcols, vdmg, pvoice, vpad; } bspec_t;   /* vars..vdmg: the variant table (vocabulary variant.parameter_set, export_dd): nvar parameter rows of vcols columns (vars, row-major), the row its rule plays (vdef, latched at the move\'s start: fighter_t.var), its program\'s animations / objects per row (anims[a + var * vanim], robj[a + var * vobj]), the damage column + 1 (vdmg, 0 none); a bprim_t op | 0x80 takes its value from column b; pvoice 1: its voice keys are timed by its frames (a program\'s, fighter.c); sf_*: the super flash\'s optional anchor (fx.super_flash, TODO #139: an engine rule for every fury, gamedata.h gflash_t; main.c super_flash): sf_anchor 1 = the concentration plays sf_dx / sf_dy px from the fighter (KOF orientation: negative dx = forward; read from the move\'s KOF animation, handlers98.super_flash), 0 = the game-wide anchor; bd_*: its screen effect (Kizuna\'s Phoenix, export_kz FOLLOW \'backdrop\'): rows bd_first .. bd_end - 1 hide the stage and the backdrop alternates bd_col[0] / bd_col[1] every frame (main.c screen_fx; bd_end 0 = none); inv_rows: invincible for its first rows (prog: frames) when it is played as down+D (the rising reversal: fighter.c); parts / links: its follow-ups (nparts 0 = one part, the whole script; export_bm special_parts); proj: its nproj projectiles in spawn order (Geese\'s Double Reppuken: 2); prog (0 = none): the special read from the ROM, played by fighter.c prog_update from its anims (KOF step flags in bstep_t: 8 event $0080, 16 same hit $4000) and robj (its objects: projectiles, effects pinned to it); rows / proj stay its captured script (the Brawler Lab\'s data, and the fallback when prog is 0) */',
         'typedef struct { const char *name; uint8_t npal, nsets; const uint16_t *pals; const bframe_t *frames; const banim_t *anims; bphys_t phys; const bthrow_t *throws; const uint16_t *vposes; const bspec_t *specials; uint8_t tile_hi, cmds; const uint8_t *routes; uint8_t id, nspec; const uint8_t *spmap; const uint8_t *voices; uint8_t nvoice, fury, sfx[7]; const uint8_t *vmore; uint8_t fury_max, form_to, form_spec, form_trig, form_exit; const bthrow_t *holds; } bchar_t;   /* holds: its hold hits (HOLDS: a hit, the finisher), paired scripts like its throws (TODO #146); form_*: the form link (vocabulary form.change, game.json roster[].form): form_trig FT_* (0 = none) starts specials[form_spec] (the transition, role BS_FORM), whose P_FORM makes the fighter bm_chars[form_to] (life, place, facing, meter kept), back by form_exit FX_*; fury_max: the index in specials of the fury\'s MAX version (down+D, TODO #139; 0xFF = none: down+D plays the fury); vmore: a key\'s further voices, [key, voice id, at] each, 0xFF ends (voices.py extras: a special that sends several, the Phoenix shouts; played with the ROM\'s voice table only); sfx: hit sounds by use (TODO #75, game.json roster[].hit_sfx): A B C D CD normals, throw C / D impacts, 0 = KOF\'s own (fighter.c hit_sound);  voices: its voice table, VK_SPEC + nspec entries of [voice id, at] (tools/brawler/voices.py table: id 1..nvoice = its voices.json list, 0 = silent; at = the step / script row it starts on), the ROM\'s default for fighter.c voice_tab; fury: the fury\'s index in specials (button D, game.json roster fury; 0xFF = none); pals: nsets * npal * 16 colours; throws: BT_COUNT (nrows 0 = none); vposes: VP_COUNT frames (0xFFFF = none); specials: its nspec specials (export_bm special_pool order; nspec, spmap last: draw.s reads the offsets before them); spmap: the special each role plays, BS_COUNT entries (D projectile, forward+D rush, down+D rising reversal, up+D another, down-forward+D, up-forward+D: two more; 0xFF = none), the ROM\'s default for fighter.c spec_tab; tile_hi: tile number bits 16-19 of all its tiles; routes: its chain route tree (fighter.h rt_head_t, routes.py); id: its index in bm_chars; cmds: command normals it has, bit k = BA_CMD_FWD_A + k (forward+A, forward+B, down-forward+C, down-forward+D) */\n',
         'enum { ' + ', '.join(f'BA_{m.upper()}' for m in MOVES) + ', BA_COUNT };',
         'enum { ' + ', '.join(f'BC_{n.upper()}' for _, n, _, _ in chars) + ', BC_COUNT };',
         'enum { ' + ', '.join(f'BT_{t.upper()}' for t in THROWS) + ', BT_COUNT };',
         'enum { BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D, BS_DF_D, BS_UF_D, BS_COUNT };',
         f'enum {{ VP_COUNT = {len(pkeys)} }};   /* victim postures: ' + ' '.join(pkeys) + ' */',
         'enum { VK_THROW = BA_COUNT, VK_HIT = BA_COUNT + BT_COUNT, VK_KO, VK_SELECT, VK_SPEC };   /* voice keys (voices.py keys): BA_*, VK_THROW + BT_*, the events, VK_SPEC + its special\'s index in the pool */',
         'extern const bchar_t bm_chars[BC_COUNT];\n#endif']
    c = ['/* Generated by tools/brawler/export_bm.py. Do not edit. */\n#include "bm_chars.h"\n']
    cs = ['/* Generated by tools/brawler/export_bm.py. Do not edit. Every fighter\'s specials (its special_pool, in pool order):\n'
          ' * compiled as plain read-only data, so they sit in the first program MB, beside the code (bm_chars.c goes to $200000). */\n'
          '#include "bm_chars.h"\n']
    fx = lambda v: str(int(round(v * 65536)))
    def bb(b): return '{0, 0, 0, 0}' if b is None else f'{{{b[0]}, {b[1]}, {b[2]}, {b[3]}}}'
    used = {}                                            # palettes the exported frames use, renumbered 0..k-1
    pooldata = {}                                        # per fighter its pool's frame / hit data (chainlab.json)
    vdata = {}                                           # per fighter its voice keys, suggestion, mapping (chainlab.json)
    for game, n, ch, off in chars:
        used[n] = sorted({p.get('pal', 0) for fr in ch['frames'] for p in fr['parts']}) or [0]
        sets = ch['block_palettes']
        c.append(f'static const uint16_t {n}_pals[] = {{' + ', '.join(f'0x{v:04X}' for st in sets for k in used[n] for v in st[k]) + '};')
        for fi, fr in enumerate(ch['frames']):
            for pi, p in enumerate(fr['parts']):
                assert len(p['tiles'][0]) <= 32, f'{n} frame {fi}: {len(p["tiles"][0])} rows (SCB3 height and draw.s stop at 32)'
                flat = [(t + off) & 0xFFFF if t else 0 for col in p['tiles'] for t in col]   # low 16 bits; tile_hi has 16-19
                c.append(f'static const uint16_t {n}_f{fi}_p{pi}[] = {{' + ', '.join(map(str, flat)) + '};')
            c.append(f'static const bpart_t {n}_f{fi}[] = {{' + ', '.join(
                f'{{{p["dx"]}, {p["dy"]}, {len(p["tiles"])}, {len(p["tiles"][0])}, {p["hflip"]}, {p["vflip"]}, {used[n].index(p.get("pal", 0))}, {n}_f{fi}_p{pi}}}'
                for pi, p in enumerate(fr['parts'])) + '};' if fr['parts'] else f'static const bpart_t {n}_f{fi}[1];')
        c.append(f'static const bframe_t {n}_frames[] = {{' + ', '.join(
            f'{{{len(fr["parts"])}, {sum(len(p["tiles"]) for p in fr["parts"])}, {n}_f{fi}}}' for fi, fr in enumerate(ch['frames'])) + '};')
        for m in MOVES:
            a = source(ch, m)
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
            if not th: thr.append('{0, 0x100, 0, 0, 0xFFFF, 0xFFFF, 0}'); continue
            out, info = throw_rows(game, n, th, pkeys, tdata.get('front', {}).get(t))
            c.append(f'static const bthrow_row_t {n}_{t}[] = {{' + ', '.join(out) + '};')
            sp = tdata.get('speed', {}).get(t, THROW_SPEED if th.get('rom') else CAPTURED_THROW_SPEED)
            thr.append(f'{{{len(out)}, {sp}, {n}_{t}, {info["ret"]}, {info["rel"]}, {info["land"]}, 0}}')
        c.append(f'static const bthrow_t {n}_throws[BT_COUNT] = {{' + ', '.join(thr) + '};')
        hl = []
        for k in HOLDS:
            out = hold_rows(ch, n, game, k, (tdata.get('hold') or {}).get(k, HOLD_DEFAULT[k]), pkeys, (tdata.get('hold') or {}).get('dx'))
            c.append(f'static const bthrow_row_t {n}_hold_{k}[] = {{' + ', '.join(out) + '};')
            hl.append(f'{{{len(out)}, 0x100, {n}_hold_{k}, {len(out)}, 0xFFFF, 0xFFFF, 0}}')
        c.append(f'static const bthrow_t {n}_holds[{len(HOLDS)}] = {{' + ', '.join(hl) + '};')
        # every special of its pool (special_pool) is in the ROM, in pool order (bm_spec.c, the first program MB): the four
        # roles (D, forward+D, down+D, up+D) pick from it through a map ({n}_spmap, game.json's specials; fighter.c
        # spec_tab in RAM, so the Brawler Lab's Characters tab remaps them live with a data pack)
        pool = special_pool(ch, n)
        sps = [dict(special_play(sp), fighter=n) for sp in pool]
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
            if rom_ok(sp): cs.append(rom_c(n, k, sp, game))   # read from the ROM: played by its program
        assert len(sps) < 255, n
        pooldata[n] = [special_info(sp, game) for sp in sps]
        cs.append(f'const bspec_t {n}_specials[{max(1, len(sps))}] = {{' + (', '.join(
            f'{{{1 if prog_only(sp) else len(sp["script"])}, {rom_inv(sp) if rom_ok(sp) else rise_inv(sp)}, {len(sp["parts"])}, {len(played_projectiles(sp))}, {n}_sp{k}, {f"{n}_pj{k}" if played_projectiles(sp) else 0}, '
            + (f'{n}_sp{k}_prog, {n}_sp{k}_an, {f"{n}_pj{k}r" if sp["rom"]["objects"] else 0}, ' if rom_ok(sp) else '0, 0, 0, ')
            + (f'{n}_sp{k}_parts, {n}_sp{k}_links, {len(sp["links"])}' if sp['parts'] else '0, 0, 0')
            + (', %d, %d, {0x%04X, 0x%04X}' % (*sp['backdrop']['rows'], *sp['backdrop']['colours']) if sp.get('backdrop') else ', 0, 0, {0, 0}')
            + ', %d, %d, %d, 0' % flash_c(sp) + var_c(n, k, sp) + '}'
            for k, sp in enumerate(sps)) or '{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}') + '};')
        c.append(f'extern const bspec_t {n}_specials[];')
        c.append(f'static const uint8_t {n}_spmap[BS_COUNT] = {{' + ', '.join(str(spec_index(pool, sp)) for sp in pick_specials(ch, n)) + '};')
        vk, vsug, vmp, vtab, vmore = voice_data(ch, n, game, pool, sps)
        vdata[n] = {'keys': vk, 'suggest': vsug, 'map': vmp, 'nvoice': len(V.bank(n)),
                    'at': {k: v[1] for k, v in vsug.items()}, 'more': vmore}
        c.append(f'static const uint8_t {n}_voices[] = {{' + ', '.join(map(str, vtab)) + '};   /* voices.py table */')
        c.append(f'static const uint8_t {n}_vmore[] = {{' + ''.join(f'{a}, {b}, {d}, ' for a, b, d in vmore) + '0xFF};   /* voices.py extras */')
        c.append(f'static const uint16_t {n}_vposes[VP_COUNT + 1] = {{' + ', '.join(str(v if v >= 0 else 0xFFFF) for v in ptable[n]) + ', 0xFFFF};')
        c.append(f'static const banim_t {n}_anims[BA_COUNT] = {{' + ', '.join(
            f'{{{len(source(ch, m)["steps"])}, {1 if source(ch, m)["mode"] == "hold" else 0}, {n}_{m}}}' for m in MOVES) + '};')
    lab = {'ba': MOVES, 'route_moves': R.MOVE_NAMES, 'inputs': R.INPUTS, 'fighters': []}
    for ci, (game, n, ch, off) in enumerate(chars):           # chain routes: tools/brawler/routes/<n>.json or the default
        has = {m for m in MOVES if any(k in ch['anims'] for k in SOURCES.get(m, [m]))}
        sps = pick_specials(ch, n)
        tree = R.load(n, roster()[n]['routes'])
        blob = R.encode(tree, MOVES, has, [sp is not None for sp in sps])
        c.append(f'static const uint8_t {n}_routes[] = {{' + ', '.join(map(str, blob)) + '};')
        lab['fighters'].append({'id': ci, 'game': game, 'name': n, 'tree': tree, 'default': R.default_tree(), 'has': sorted(has), 'routes_file': roster()[n]['routes'] is not None,
                                'moves': {m: R.frame_data(source(ch, m)['steps']) for m in R.MOVE_NAMES if m in has},
                                'specials': {k: (sp['input'] if sp else None) for k, sp in zip(R.SPECIALS, sps)},
                                'pool': pooldata[n], 'suggest': [sp['input'] if sp else None for sp in suggest_specials(ch, n)],
                                'voices': vdata[n]})
    json.dump(lab, open(os.path.join(outdir, 'chainlab.json'), 'w'), ensure_ascii=False)
    # the voices the ROM maps (build_snd.py brings only their samples into the V ROM: songs.json "voices")
    json.dump([{'name': n, 'game': game, 'ids': sorted(set(vdata[n]['map'].values()) | {m[1] & 0x7F for m in vdata[n]['more']})} for game, n, ch, off in chars],
              open(os.path.join(outdir, 'voice_map.json'), 'w'))
    json.dump({n: [fr.get('record') for fr in ch['frames']] for game, n, ch, off in chars},   # bm frame -> 'id:ROM frame'
              open(os.path.join(outdir, 'bm_frames.json'), 'w'))                          # (romspecials_check.py)
    def form_tail(chars, ch, n):
        f = form_c(chars, ch, n)
        return ', %d, %d, %d, %d' % (f if f else (0, 0, 0, 0))   # (always written: holds follow)
    c.append('const bchar_t bm_chars[BC_COUNT] = {')
    for game, n, ch, off in chars:
        p = ch['physics']; sets = ch['block_palettes']
        p = {'hop_vy0': p['jump_vy0'], 'hop_gravity': p['gravity'], 'hop_dx': p['jump_dx'], 'prejump': 3, **p}   # KOF94/95: no hop
        land = ch['anims'].get('land') if game in ('kof96', 'kof98', 'kof99', 'kizuna', 'doubledr') else None   # SS4 / WHP: KOF's usual 4
        p['land'] = sum(s['ticks'] + 1 for s in land['steps']) + 1 if land else 4
        c.append(f'  {{"{(roster()[n].get("display") or n).upper()}", {len(used[n])}, {len(sets)}, {n}_pals, {n}_frames, {n}_anims, {{{fx(p["walk_fwd"])}, {fx(p["jump_vy0"])}, {fx(p["gravity"])}, {fx(p["jump_dx"])}, {fx(p["hop_vy0"])}, {fx(p["hop_gravity"])}, {fx(p["hop_dx"])}, {p["prejump"]}, {p["land"]}}}, {n}_throws, {n}_vposes, {n}_specials, {(off + SRC_BASE) >> 16}, {sum(1 << k for k, m in enumerate(CMDS) if m in ch['anims'])}, {n}_routes, {[q[1] for q in chars].index(n)}, {len(special_pool(ch, n))}, {n}_spmap, {n}_voices, {len(V.bank(n))}, {spec_index(special_pool(ch, n), fury_special(ch, n))}, {{{', '.join(map(str, char_sfx(n)))}}}, {n}_vmore, {spec_index(special_pool(ch, n), fury_max_special(ch, n))}{form_tail(chars, ch, n)}, {n}_holds}},')
    c.append('};')
    open(os.path.join(outdir, 'bm_chars.h'), 'w').write('\n'.join(h) + '\n')
    open(os.path.join(outdir, 'bm_chars.c'), 'w').write('\n'.join(c) + '\n')
    open(os.path.join(outdir, 'bm_spec.c'), 'w').write(dedupe_c('\n'.join(cs)) + '\n')

if __name__ == '__main__':
    outdir = sys.argv[1]
    assert sys.argv[2] == '--roster', __doc__
    specs = [r['bank'] for r in roster(sys.argv[3]).values()]
    chars, tiles = build(specs, outdir)
    for game, n, ch, off in chars:
        print(f'{game}:{n}: specials ' + ', '.join(f'{k} {sp["input"] if sp else "-"}' for k, sp in zip(('D', 'fwd+D', 'down+D', 'up+D', 'df+D', 'uf+D'), pick_specials(ch, n))) + ';', end=' ')
        print(f'{len(ch["frames"])} frames, {len([m for m in MOVES if any(k in ch["anims"] for k in SOURCES.get(m, [m]))])}/{len(MOVES)} moves, '
              f'{len(ch["block_palettes"])} colour sets, max cols '
              f'{max(sum(len(p["tiles"]) for p in f["parts"]) for f in ch["frames"])}, command normals: '
              f'{" ".join(m for m in CMDS if m in ch["anims"]) or "-"}')
    print('tiles', tiles - TILE_BASE, f'({(tiles - TILE_BASE) * 128 // 1024} KB)')
