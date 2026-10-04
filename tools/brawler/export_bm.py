#!/usr/bin/env python3
"""Brawler fighter data: a beat 'em up subset of each fighter's animations from the KOF dictionaries
(tools/kof96/export96.py, any of KOF96/98/99), written as const 68000 tables + the C1/C2 tiles they use.

    python3 export_bm.py OUTDIR kof98:terry kof98:kyo ...        -> bm_chars.c/.h, bm_c1.bin, bm_c2.bin

Per fighter: frames (parts: dx, dy, columns, rows, flips, palette index, tile columns), animations (steps: frame, ticks,
one hurt box = union of KOF's hurt boxes, the attack box when the step has one), every colour set (16-colour palettes,
one per palette index), physics (16.16 px/frame). Boxes are KOF's: centre offset from the feet (y < 0 = up) and half
extents, in the sprites' own orientation (ROM sprites face LEFT: mirror x when the fighter faces right).
Tile numbers start at TILE_BASE (1-1023 hold the stage, make_stage.py)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import export96

# the brawler's animation set (KOF move names); MOVES order = the BA_* enum
MOVES = ['idle', 'walk_fwd', 'run', 'prejump', 'jump_up_rise', 'jump_up_fall', 'jump_fwd_rise', 'jump_fwd_fall', 'land',
         'atk_a_close', 'atk_a_far', 'atk_b_close', 'atk_b_far', 'atk_c_close', 'atk_c_far', 'atk_d_close', 'atk_d_far',
         'atk_d_crouch', 'atk_c_jump', 'atk_d_jump', 'body_toss', 'hit_stand_light', 'hit_stand_heavy', 'hit_air',
         'blowback', 'knockdown_flight', 'knockdown_bounce', 'knockdown_fall', 'down', 'getup', 'trip', 'win_a', 'atk_c_crouch',
         'cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d',   # command normals (KOF97+: forward+A / B, down-forward+C / D)
         'blowback_n']                                 # KOF98's blowback when not a counter hit (285; blowback = 283)
CMDS = MOVES[-5:-1]                              # bchar_t.cmds bit k: the fighter has CMDS[k] (export96.CMD_NORMALS)
TILE_BASE = 1024                               # our first fighter tile; 1-1023 hold the stage (make_stage.py), 0 empty
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

def build(specs, outdir):
    """one export per game (the whole roster of that game at once, so every fighter has the frames of every victim
    posture its teammates' throws use); tiles renumbered into one space"""
    os.makedirs(outdir, exist_ok=True)
    games = {}
    for spec in specs:
        game, name = spec.split(':'); games.setdefault(game, []).append(name)
    chars, c1, c2 = [], bytearray(), bytearray()
    tile_next = TILE_BASE
    def export(game, names, tmp):
        if game == 'kof94':                             # KOF95's engine: its own reader, the same export layout
            sys.path.insert(0, os.path.join(HERE, '..', 'kof94')); import export94
            return export94.export(names, tmp, only=set(MOVES))
        return export96.export(names, tmp, game, only=set(MOVES) | set(THROWS) | {'specials'})
    blocks = []                                         # (game, names, export, tmp dir): a game's roster in one block,
    for game, names in games.items():                   # halves while its tiles overflow one 64K page (11 KOF98
        todo = [names]                                  # fighters: 67162); a throw's victim offsets come from the
        while todo:                                     # thrower's own block, the victim's poses from its own (vposes)
            ns = todo.pop(0); tmp = os.path.join(outdir, f'tmp_{game}' + (f'_{len(blocks)}' if ns != names else ''))
            ex = export(game, ns, tmp)
            if ex['tiles'] >= 0x10000 and len(ns) > 1: todo[:0] = [ns[:len(ns) // 2], ns[len(ns) // 2:]]; continue
            blocks.append((game, ns, ex, tmp))
    for game, names, ex, tmp in blocks:
        a = open(os.path.join(tmp, 'kof95_c1.bin'), 'rb').read(); b = open(os.path.join(tmp, 'kof95_c2.bin'), 'rb').read()
        n = ex['tiles']
        assert n < 0x10000, f'{game}: {n} tiles in one block (a block must fit one 64K tile page after its blank tile)'
        if tile_next >> 16 != (tile_next + n - 1) >> 16:    # keep a block inside one 64K page: its fighters' tile numbers
            gap = ((tile_next >> 16) + 1 << 16) - tile_next  # then share bits 16-19 (bchar_t.tile_hi -> SCB1 attribute)
            c1 += bytes(gap * 64); c2 += bytes(gap * 64); tile_next += gap
        if tile_next & 0xFFFF == 0:                     # tile 0 = empty, and with tile_hi it means page start: blank
            c1 += bytes(64); c2 += bytes(64); tile_next += 1
        c1 += a[SRC_BASE * 64:(SRC_BASE + n) * 64]; c2 += b[SRC_BASE * 64:(SRC_BASE + n) * 64]
        off = tile_next - SRC_BASE; tile_next += n
        chars += [(game, name, ex['characters'][name], off) for name in names]
    assert tile_next <= 0x100000, f'{tile_next} tiles: past the 20-bit tile number'
    chars.sort(key=lambda c: specs.index(f'{c[0]}:{c[1]}'))   # bm_chars in the command line's order, the order
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
                 'kyo': {'up': '624B'}}          # Kototsuki You: the run, on contact the grab and the explosion (states
                                                 # 134-140; 'EX 624D' was the same run, captured as a hit, no whiff)
ROLES = ('proj', 'rush', 'rise', 'up')

SPECIAL_DAMAGE = 8                                     # a special's damage, split over its hits (fighter.c)
R_HEAVY, R_KNOCKDOWN, R_LAUNCH = 1, 2, 3               # fighter.h R_*: the victim's reaction to a special's hit
IMPACT_ROWS = 4                                        # an impact row without a box of its step: the object's live box
                                                       # (+$90) on it and the next rows (the victim may have moved)

def victim_reaction(rs, i, end):
    """the opponent's reaction in a capture to the impact at row i (rows up to `end`, the next impact): ejected when it
    leaves the ground (height > 8) or enters a knockdown / blowback state (280-399): R_LAUNCH when it flies 48 px or
    higher, else R_KNOCKDOWN; grounded (a hit reel, states 256-279, height 0): R_HEAVY. Held states (400+: Kyo's grab
    lifts the victim) decide nothing. None: no opponent data, or no reaction seen (a guard)."""
    seen = [(r[5], r[6]) for r in rs[i + 1:min(end, i + 60)] if len(r) > 6 and r[5] is not None and r[5] < 400]
    if not seen: return None
    top = max(h for st, h in seen)
    if top > 8 or any(280 <= st < 400 for st, h in seen): return R_LAUNCH if top >= 48 else R_KNOCKDOWN
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
    Between its first and last hit the opponent's place in the capture (x from the fighter, height) is kept per row
    (carry): KOF's push boxes and juggles hold it in the move, the brawler carries its target there.
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
    objreact = victim_reaction(rs, objhits[0], next((j for j in hits if j > objhits[0]), n)) if objhits else None
    for i in range(n - 1, 0, -1):                       # a dropped row's marks go to the row it repeats
        if drop[i]: marks[i - 1] += marks[i]; marks[i] = ''
    keep = [i for i in range(n) if not drop[i]]
    carry = [None] * n                                 # the opponent's place between the move's first and last hit:
    if len(hits) > 1:                                  # KOF keeps it in the move (push boxes, juggles); the brawler
        for i in range(hits[0] + 1, hits[-1] + 1):     # carries its target there (fighter.c)
            if len(rs[i]) > 8 and rs[i][8] is not None:
                carry[i] = (max(-128, min(127, rs[i][8] - sc[i][1])), max(0, min(255, rs[i][6])))
    hitv = sp.get('version') == 'hit' and bool(hits)    # objects that hit nothing while the body landed every hit
    return dict(sp, objects_hit=not hitv or bool(objhits),   # are effects (Burn Knuckle's flames): no box
                script=[sc[i] for i in keep], row_boxes=[rb[i] for i in keep], row_steps=[rs[i] for i in keep],
                marks=[marks[i] for i in keep], react=[react[i] for i in keep], objreact=objreact,
                carry=[carry[i] for i in keep],
                cont=sum(1 for i in keep if i < cont) if cont else 0,
                stats={'freezes': len(starts), 'removed': n - len(keep),
                       'contact': (rs[hits[0]][8] - sc[hits[0]][1]) if hits and len(rs[hits[0]]) > 8 and rs[hits[0]][8] is not None else None, 'impacts': [keep.index(i) for i in impacts if i in keep],
                       'reactions': [react[i] for i in impacts]})

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
    out, prev_key, prev_act, prev_chain, prev_row = [], None, False, False, False
    rom_new = [False] * len(rb)                          # a hit the ROM opens (its step rule), hit in the capture or not
    for i, r in enumerate(sp['script']):
        hb, ab = boxes(rb[i])
        if (cont and i >= cont) or (hitv and not cont):
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
    game = lambda i: (cont and i >= cont) or (hitv and not cont)
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
    if path:
        each = max(1, SPECIAL_DAMAGE // len(path))
        for i in wins: out[i][3] = 0 if out[i][2] & 8 else each
        out[path[-1]][3] = max(1, SPECIAL_DAMAGE - each * (len(path) - 1))
    return [tuple(r) for r in out]

def hit_fx(sp, i, game):
    """bspec_row_t.fx of a row opening a hit: KOF98's hit effect the move set in the attacker (captured per row:
    +$1B8 the hit kind, the victim's hit sounds through the table at $1E208; on a fire kind the victim burns in the
    attacker's flame colour, FIRE_COLOUR); rows without it: kind 1, the heavy hit ($13). KOF96 / KOF99
    fighters: their own kind (both games' handler tables, decoded 2026-10-04, number kinds as KOF98's), played with
    KOF98's sounds since the brawler runs KOF98's driver"""
    rs = sp['row_steps'][i]
    eff = rs[9] if len(rs) > 9 and rs[9] else None
    if not eff or not eff[0] or eff[0] > 32: return 1   # KOF96 / KOF99 number their kinds as KOF98 (same handler
                                                         # tables: 1 heavy hit, 11 hit + fire); KOF99's 33-46: none in KOF98
    fire = eff[0] in (11, 13, 21)                       # the kinds whose sounds have the fire crackle $2E: only they
    return (eff[0] & 0x3F) | ((FIRE_COLOUR.get(sp.get('fighter'), 2) if fire else 0) << 6)   # burn

# the burn's colour: the attacker's flames (KOF98 VRAM during Kyo's and Iori's Oniyaki hits: the victim's sprites
# leave its own palette for palette $58, orange, with Kyo, $5F, purple, with Iori; both always loaded). Purple = 1,
# orange = 2 (fighter.c BURN_PAL); every fire user but Iori burns orange (inference: one flame colour per fighter)
FIRE_COLOUR = {'iori': 1}

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

def pick_specials(ch, name=None):
    """[projectile, rush, rise, up] (None where the fighter has no such move). The big versions first (C / D: Bruno
    2026-10-03, the long Burn Knuckle, the high dragon punch); up+D = the best special of a move not used yet (one move
    = its input motion with the punch or kick pair: 214A / 214C is one move, 214B / 214D another)."""
    c = [sp for sp in ch.get('specials', []) if sp['condition'] == 'normal' and not sp['input'].startswith('air')]
    auto = [sp for sp in c if not sp['input'].split()[0] in ('EX', 'MAX', 'Counter') and not counter_move(sp)]   # supers / EX: by override only
    big = lambda sp: sp['input'][-1:] in ('C', 'D')
    move = lambda sp: (sp['input'].rstrip('ABCD'), sp['input'][-1:] in ('A', 'C'))
    out = []
    for role in ROLES:
        want = ROLE_OVERRIDE.get(name, {}).get(role)
        pick = next((sp for sp in c if sp['input'] == want), None) if want else None
        if pick is None:
            c_all, c = c, [sp for sp in auto if sp not in out]
            if role == 'proj': cand = [(0, sp) for sp in c if special_shape(sp)[2] and special_shape(sp)[0] <= 45 and special_shape(sp)[1] <= 10]
            elif role == 'rush': cand = [(special_shape(sp)[0] - 2 * special_shape(sp)[1], sp) for sp in c if special_shape(sp)[0] >= 60 and special_shape(sp)[1] <= 30]
            elif role == 'rise': cand = [(special_shape(sp)[1] - special_shape(sp)[0] / 2, sp) for sp in c if special_shape(sp)[1] >= 25]
            else:
                used = {move(sp) for sp in out if sp}
                cand = [(0, sp) for sp in c if move(sp) not in used]
            cand.sort(key=lambda t: (not big(t[1]), -t[0]))
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
    if game not in ('kof96', 'kof97', 'kof98', 'kof99'): return []
    st = lambda r: int(r[5].split('.')[0]) if r[5] else -1
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

def frame_box(fr):
    """bounding box of a frame's sprites, as a KOF box (centre from the origin, half extents, sprite orientation)"""
    xs, ys = [], []
    for p in fr['parts']:
        w, h = len(p['tiles']) * 16, len(p['tiles'][0]) * 16
        x0 = -p['dx'] - w if p['hflip'] else p['dx']; y0 = -p['dy'] - h if p['vflip'] else p['dy']
        xs += [x0, x0 + w]; ys += [y0, y0 + h]
    if not xs: return None
    cl = lambda v: max(-128, min(127, v))
    return (cl((min(xs) + max(xs)) // 2), cl((min(ys) + max(ys)) // 2), min(255, (max(xs) - min(xs)) // 2), min(255, (max(ys) - min(ys)) // 2))

VICTIM_POSES = {g: json.load(open(os.path.join(HERE, '..', 'kof96', f'victim_poses{g[3:]}.json')))['poses']
                for g in ('kof96', 'kof98', 'kof99')}

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

def write_c(chars, outdir):
    pkeys, ptable = poses(chars)
    h = ['/* Generated by tools/brawler/export_bm.py from the KOF dictionaries. Do not edit. */',
         '#ifndef BM_CHARS_H\n#define BM_CHARS_H\n#include <stdint.h>\n',
         'typedef struct { int16_t dx, dy; uint8_t cols, rows, hflip, vflip, pal; const uint16_t *tiles; } bpart_t;   /* tiles: cols*rows column-major, 0 = empty; pal: palette index of the fighter */',
         'typedef struct { uint8_t nparts, ncols; const bpart_t *parts; } bframe_t;   /* ncols: hardware sprites the frame uses */',
         'typedef struct { int8_t x, y; uint8_t w, h; } bbox_t;                       /* centre from the feet (y<0 up), half extents; sprite faces left */',
         'typedef struct { uint16_t frame; uint8_t ticks, flags; bbox_t hurt, atk; int8_t dx; uint8_t hy; } bstep_t;   /* flags: 1 = attack box, 2 = hurt box, 4 = opens a new hit (multi-hit normals); dx: px the fighter moves forward as the step starts (KOF\'s $FB move); hy: height in px during the step (command normals that hop: export96.cmd_frames) */',
         'typedef struct { uint8_t nsteps, hold; const bstep_t *steps; } banim_t;     /* hold: stop on the last step */',
         'typedef struct { int32_t walk, jump_vy0, gravity, jump_dx; } bphys_t;     /* 16.16 px per frame */',
         'typedef struct { uint16_t tframe; int16_t tx, ty; uint8_t vpose, flags; int16_t vx, vy; } bthrow_row_t;   /* one video frame: thrower frame + offset from its start (forward +, up +); victim posture (0xFF: none) + offset from the thrower; flags 1 = victim faces the thrower\'s way (its facing at the grab), 2 = victim drawn in front, 4 = impact (the blow lands / the victim hits the floor: damage, spark, splash), 16 = the game froze there (hit-stop), 8 = the thrower has turned around (drawn mirrored; offsets stay in its grab facing) */',
         'typedef struct { uint16_t nrows; const bthrow_row_t *rows; } bthrow_t;',
         'typedef struct { uint16_t frame; int16_t x, y; uint8_t same, react; bbox_t box; } bsobj_t;   /* special\'s object (projectile): frame (0xFFFF = none), offset from the fighter\'s start, faces the fighter\'s way, react: the victim\'s reaction R_* + 1 measured in the game (0: knockdown), sprite bounds as its attack box */',
         'typedef struct { uint16_t frame; int16_t x, y; bbox_t atk; uint8_t hit, dmg; bsobj_t obj[2]; int8_t vx; uint8_t vy, fx, pad; } bspec_row_t;   /* one video frame of a special: fighter frame + offset from its start (forward +, up +), body attack box; hit: 1 box live, 2 opens a new hit, 4 the target is carried at vx (forward from the fighter) / vy (height), 8 contact (no damage), 16 a hit here goes on to the continuation, bits 5-7 the victim\'s reaction R_* (export_bm special_rows); dmg: damage of the hit it opens; fx (rows opening a hit): KOF98 hit effect, bits 0-5 the hit kind (the victim\'s hit sounds, fighter.c HIT_SFX), bits 6-7 the burn (1 purple, 2 orange) */',
         'typedef struct { uint16_t nrows, inv_rows, cont, pad; const bspec_row_t *rows; } bspec_t;   /* inv_rows: invincible for its first rows; cont: first row of the hit-confirmed continuation (0 = none): a hit on a row with hit bit 16 jumps there, reaching it ends the move */',
         'typedef struct { const char *name; uint8_t npal, nsets; const uint16_t *pals; const bframe_t *frames; const banim_t *anims; bphys_t phys; const bthrow_t *throws; const uint16_t *vposes; const bspec_t *specials; uint8_t tile_hi, cmds; } bchar_t;   /* pals: nsets * npal * 16 colours; throws: BT_COUNT (nrows 0 = none); vposes: VP_COUNT frames (0xFFFF = none); specials: BS_COUNT (D projectile, forward+D rush, down+D rising reversal, up+D another; nrows 0 = none); tile_hi: tile number bits 16-19 of all its tiles; cmds: command normals it has, bit k = BA_CMD_FWD_A + k (forward+A, forward+B, down-forward+C, down-forward+D) */\n',
         'enum { ' + ', '.join(f'BA_{m.upper()}' for m in MOVES) + ', BA_COUNT };',
         'enum { ' + ', '.join(f'BC_{n.upper()}' for _, n, _, _ in chars) + ', BC_COUNT };',
         'enum { ' + ', '.join(f'BT_{t.upper()}' for t in THROWS) + ', BT_COUNT };',
         'enum { BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D, BS_COUNT };',
         f'enum {{ VP_COUNT = {len(pkeys)} }};   /* victim postures: ' + ' '.join(pkeys) + ' */',
         'extern const bchar_t bm_chars[BC_COUNT];\n#endif']
    c = ['/* Generated by tools/brawler/export_bm.py. Do not edit. */\n#include "bm_chars.h"\n']
    fx = lambda v: str(int(round(v * 65536)))
    def bb(b): return '{0, 0, 0, 0}' if b is None else f'{{{b[0]}, {b[1]}, {b[2]}, {b[3]}}}'
    used = {}                                            # palettes the exported frames use, renumbered 0..k-1
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
            a = ch['anims'].get(m) or ch['anims']['idle']
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
        for t in THROWS:
            th = ch.get('throws', {}).get(t)
            if not th: continue
            rows = th['victims'].get(n) or next(iter(th['victims'].values()))   # offsets of the mirror match (see README)
            froze = set(th.get('impacts') or [])        # KOF froze there (Ryo's forward+C): the brawler's hit-stop too
            out = []; imp = set(throw_impacts(rows, game)) | froze   # blows / floor touches: damage, no freeze (KOF's)
            for i, (tf, tx, ty, *turned) in enumerate(th['timeline']):
                vf, vx, vy, same, front, key = rows[min(i, len(rows) - 1)]
                v = vocab(game, key)
                vp = pkeys.index(v) if vf >= 0 and v in pkeys else 255
                out.append(f'{{{tf if tf >= 0 else 0}, {tx}, {ty}, {vp}, {same | front << 1 | (4 if i in imp else 0) | (8 if turned and turned[0] else 0) | (16 if i in froze else 0)}, {vx}, {vy}}}')
            c.append(f'static const bthrow_row_t {n}_{t}[] = {{' + ', '.join(out) + '};')
        c.append(f'static const bthrow_t {n}_throws[BT_COUNT] = {{' + ', '.join(
            f'{{{len(ch["throws"][t]["timeline"])}, {n}_{t}}}' if t in ch.get('throws', {}) else '{0, 0}' for t in THROWS) + '};')
        sps = [dict(special_play(sp), fighter=n) if sp else None for sp in pick_specials(ch, n)]
        for k, sp in enumerate(sps):
            if sp is None: continue
            out = []
            for i, ((f, x, hgt, objs), (hb, ab, hit, dmg)) in enumerate(zip(sp['script'], special_rows(sp))):
                ob = []
                for of, ox, oh, same in objs[:2]:
                    b = (frame_box(ch['frames'][of]) if sp['objects_hit'] else None) or (0, 0, 0, 0)
                    ob.append(f'{{{of}, {ox}, {oh}, {same}, {sp["objreact"] + 1 if sp["objreact"] is not None else 0}, {bb(b)}}}')
                ob += ['{0xFFFF, 0, 0, 0, 0, {0, 0, 0, 0}}'] * (2 - len(ob))
                cv = sp['carry'][len(out)]
                out.append(f'{{{f}, {x}, {hgt}, {bb(ab)}, {hit | (4 if cv else 0)}, {dmg}, {{{", ".join(ob)}}}, {cv[0] if cv else 0}, '
                           f'{cv[1] if cv else 0}, {hit_fx(sp, i, game) if hit & 2 else 0}, 0}}')
            c.append(f'static const bspec_row_t {n}_sp{k}[] = {{' + ', '.join(out) + '};')
        def inv_rows(sp, k):                             # the rising reversal: invincible through its last hit row
            if ROLES[k] != 'rise': return 0                     # or its apex
            hits = [i for i, r in enumerate(special_rows(sp)) if r[1]]
            peak = max(range(len(sp['script'])), key=lambda i: sp['script'][i][2])   # a rising move: to its apex
            return max(hits[-1] + 1 if hits else 0, peak + 1 if sp['script'][peak][2] > 0 else 0) or len(sp['script'])
        c.append(f'static const bspec_t {n}_specials[BS_COUNT] = {{' + ', '.join(
            f'{{{len(sp["script"])}, {inv_rows(sp, k)}, {sp.get("cont", 0)}, 0, {n}_sp{k}}}' if sp else '{0, 0, 0, 0, 0}' for k, sp in enumerate(sps)) + '};')
        c.append(f'static const uint16_t {n}_vposes[VP_COUNT + 1] = {{' + ', '.join(str(v if v >= 0 else 0xFFFF) for v in ptable[n]) + ', 0xFFFF};')
        c.append(f'static const banim_t {n}_anims[BA_COUNT] = {{' + ', '.join(
            f'{{{len((ch["anims"].get(m) or ch["anims"]["idle"])["steps"])}, {1 if (ch["anims"].get(m) or ch["anims"]["idle"])["mode"] == "hold" else 0}, {n}_{m}}}' for m in MOVES) + '};')
    c.append('const bchar_t bm_chars[BC_COUNT] = {')
    for game, n, ch, off in chars:
        p = ch['physics']; sets = ch['block_palettes']
        c.append(f'  {{"{n.upper()}", {len(used[n])}, {len(sets)}, {n}_pals, {n}_frames, {n}_anims, {{{fx(p["walk_fwd"])}, {fx(p["jump_vy0"])}, {fx(p["gravity"])}, {fx(p["jump_dx"])}}}, {n}_throws, {n}_vposes, {n}_specials, {(off + SRC_BASE) >> 16}, {sum(1 << k for k, m in enumerate(CMDS) if m in ch['anims'])}}},')
    c.append('};')
    open(os.path.join(outdir, 'bm_chars.h'), 'w').write('\n'.join(h) + '\n')
    open(os.path.join(outdir, 'bm_chars.c'), 'w').write('\n'.join(c) + '\n')

if __name__ == '__main__':
    outdir = sys.argv[1]; specs = sys.argv[2:] or ['kof98:terry']
    chars, tiles = build(specs, outdir)
    for game, n, ch, off in chars:
        print(f'{game}:{n}: specials ' + ', '.join(f'{k} {sp["input"] if sp else "-"}' for k, sp in zip(('D', 'fwd+D', 'down+D', 'up+D'), pick_specials(ch, n))) + ';', end=' ')
        print(f'{len(ch["frames"])} frames, {len([m for m in MOVES if m in ch["anims"]])}/{len(MOVES)} moves, '
              f'{len(ch["block_palettes"])} colour sets, max cols '
              f'{max(sum(len(p["tiles"]) for p in f["parts"]) for f in ch["frames"])}, command normals: '
              f'{" ".join(m for m in CMDS if m in ch["anims"]) or "-"}')
    print('tiles', tiles - TILE_BASE, f'({(tiles - TILE_BASE) * 128 // 1024} KB)')
