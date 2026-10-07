#!/usr/bin/env python3
"""KOF96 / KOF98 export in the same JSON layout as tools/kof95/export.py (so tools/kof95/gallery.py renders it):
characters -> frames (parts: dx, dy, flips, tile columns, 'pal' = index into the character's block_palettes), anims
(steps with ticks, boxes), palettes (regular + second colour set), physics. Tiles go to kof95_c1/c2.bin.
Moves are named game states (labelled in MAME, capture/labels.py).
    python3 export96.py [--game kof98] OUTDIR [all | name ...]"""
import json, os, struct, sys
import rom96, throwscripts96, specials96, commands96, projectiles96, handlers98

HERE = os.path.dirname(os.path.abspath(__file__))
TILE_BASE = 256
CAST = ['kyo', 'benimaru', 'goro', 'terry', 'andy', 'joe', 'ryo', 'robert', 'yuri', 'leona', 'ralf', 'clark', 'athena', 'kensou',
        'chin', 'kasumi', 'mai', 'king', 'kim', 'chang', 'choi', 'iori', 'mature', 'vice', 'geese', 'krauser', 'mr_big', 'chizuru',
        'goenitz']
# move -> game state, labelled on Kyo vs Yuri (capture/labels.py)
MOVES = {
    'idle': 0, 'walk_fwd': 1, 'walk_back': 2, 'prejump': 3, 'jump_up_rise': 4, 'jump_up_fall': 5, 'land': 6,
    'jump_fwd_rise': 8, 'jump_fwd_fall': 9, 'jump_back_rise': 12, 'jump_back_fall': 13,
    # the hop (stick tapped: released before take-off), own states and animations (capture/jumps.py, KOF96/98/99)
    'hop_up_rise': 15, 'hop_up_fall': 16, 'hop_fwd_rise': 17, 'hop_fwd_fall': 18, 'hop_back_rise': 19, 'hop_back_fall': 20,
    'crouch_down': 21, 'crouch': 23, 'crouch_up': 22, 'run_start': 48, 'run': 49, 'run_stop': 50,
    'backstep_start': 51, 'backstep': 52, 'backstep_land': 53,
    'guard_stand_in': 26, 'guard_stand': 27, 'guard_stand_out': 28, 'guard_crouch_in': 32, 'guard_crouch': 33,
    'atk_a_close': 80, 'atk_a_far': 81, 'atk_a_jump': 82, 'atk_a_jump_diag': 84, 'atk_a_crouch': 88,
    'atk_b_close': 89, 'atk_b_far': 90, 'atk_b_jump': 91, 'atk_b_jump_diag': 93, 'atk_b_crouch': 97,
    'atk_c_close': 98, 'atk_c_far': 99, 'atk_c_jump': 100, 'atk_c_jump_diag': 102, 'atk_c_crouch': 106,
    'atk_d_close': 107, 'atk_d_far': 108, 'atk_d_jump': 109, 'atk_d_jump_diag': 111, 'atk_d_crouch': 115,
    'body_toss': 116, 'atk_cd_jump': 117,          # air C+D (capture/aircd.py, 2026-10-04: every jump and KOF96's hop)
    'hit_stand_light': 256, 'hit_stand_heavy': 262, 'hit_crouch_light': 264, 'hit_crouch_heavy': 266,
    'blowback': 288, 'blowback_n': 288, 'knockdown_flight': 298, 'knockdown_bounce': 334, 'knockdown_fall': 343, 'down': 355,
    'getup': 66, 'trip': 327,
}

def palettes(m, cid):
    """16 regular + 16 mirror palettes of the character's block: palette n at bank 1 $200002 + n*32, body = $100 + id*$20"""
    get = lambda n: [0] + [m.u16(0x200002 + n * 32 + 2 * i, 1) for i in range(1, 16)]
    base = 0x100 + cid * 0x20
    return [get(base + k) for k in range(16)], [get(base + 16 + k) for k in range(16)]

def jump_physics(walk, vy0, gravity, prejump):
    """16.16 table values -> the physics of both jumps (px per frame). Decoded from the code (KOF96 $EF24, KOF98 $13E2A,
    KOF99 $E578, same routine): the prejump loads launch speed +$58 and gravity +$5C from the jump table and the
    horizontal speed +$50 from the walk table; a hop (stick released before take-off) sets flag +$E0 bit 3 and takes
    vy -= vy >> 2 (lsr.l #2): 3/4 of the launch speed, the same gravity and horizontal speed. Measured in the games
    (capture/jumps.py, 14 fighters x 6 jump kinds): every launch speed, gravity and |dx| equal to the bit.
    prejump = frames on the ground: the prejump animation's steps at ticks + 1 frames each, + 1 (measured, all 14)."""
    f = lambda v: v / 65536
    return {'walk_fwd': f(walk), 'walk_back': f(walk), 'jump_vy0': f(vy0), 'gravity': f(gravity), 'jump_dx': f(walk),
            'hop_vy0': f(vy0 - (vy0 >> 2)), 'hop_gravity': f(gravity), 'hop_dx': f(walk), 'prejump': prejump}

def prejump_frames(m, cid, slot):
    steps, _ = rom96.parse_anim(m, rom96.anim_addr(m, cid, slot))
    return sum(s[0] + 1 for s in steps) + 1

def physics(m, cid, prejump=0):
    return jump_physics(m.u32(0x6E8EE + 4 * cid), m.u32(0x6E96E + 8 * cid), m.u32(0x6E972 + 8 * cid), prejump)

CAST98 = ['kyo', 'benimaru', 'daimon', 'terry', 'andy', 'joe', 'ryo', 'robert', 'yuri', 'leona', 'ralf', 'clark', 'athena',
          'kensou', 'chin', 'chizuru', 'mai', 'king', 'kim', 'chang', 'choi', 'yashiro', 'shermie', 'chris', 'yamazaki', 'mary',
          'billy', 'iori', 'mature', 'vice', 'heidern', 'takuma', 'saisyu', 'heavy_d', 'lucky', 'brian', 'rugal', 'shingo']
# labelled on Kyo vs Yuri (GAME=kof98 capture/labels.py): KOF96's numbering except run/backstep/roll and the knockdowns
MOVES98 = dict(MOVES)
for k in ('run_start', 'run', 'run_stop', 'backstep_start', 'backstep', 'backstep_land', 'blowback', 'blowback_n', 'knockdown_flight',
          'knockdown_bounce', 'knockdown_fall', 'down', 'getup', 'trip'): del MOVES98[k]
MOVES98.update({'hop_up_rise': 15, 'hop_up_fall': 16, 'hop_fwd_rise': 17, 'hop_fwd_fall': 18,
                # hop normals (KOF97+: one per button for every hop direction; KOF96's hop plays the jump's normals)
                'atk_a_hop': 120, 'atk_b_hop': 121, 'atk_c_hop': 122, 'atk_d_hop': 123, 'atk_cd_hop': 124,
                'run_start': 45, 'run': 46, 'run_stop': 47, 'backstep_start': 48, 'backstep': 49, 'backstep_land': 50,
                'roll_start': 51, 'roll': 52, 'roll_end': 53,
                # blowback: 283 a counter hit, 285 not (C+D captured on Yuri, 2026-10-04)
                'blowback': 283, 'blowback_n': 285, 'knockdown_flight': 287, 'knockdown_bounce': 309, 'knockdown_fall': 313, 'down': 328,
                'getup': 72, 'trip': 307, 'hit_air': 308, 'air_land': 279,
                # win poses: the button held at the KO picks one (MAME, all 38 fighters: tools/kof98/capture/wins98.py)
                'win_a': 336, 'win_a_hold': 337, 'win_b': 338, 'win_b_hold': 339,
                'win_c': 340, 'win_c_hold': 341, 'win_d': 342, 'win_d_hold': 343})

# The round win (brawler 'win', TODO #184): the states the winner goes through after the KO, as the game plays them
# (tools/kof98/capture/wins98.py, GAME=kof96 / kof98 / kof99: A held at the KO, as the brawler's pick): KOF98 / KOF99
# 336 then 337 (its end) for every fighter; KOF96 209 (slot 65), Geese 209 then 232. One animation: the states' steps
# one after the other, 'parts' = [slot, first step, steps] (the voices' places, brawler/voices.py)
WINS = {g: os.path.join(HERE, '..', 'kof98', 'capture', d, 'wins.json') for g, d in
        (('kof96', 'wins_kof96'), ('kof98', 'wins'), ('kof99', 'wins_kof99'))}
def win_states(game, cid):
    p = WINS.get(game)
    seq = (json.load(open(p)).get(str(cid)) or {}).get('A') if p and os.path.exists(p) else None
    if seq: return [st for st, _ in seq[1:] if st]           # the attack that won it first, idle (0) between / after
    return [209] if game == 'kof96' else [336, 337]

PAL_ROM = {'kof98': 0x2D77F0, 'kof99': 0x2D77F0, 'kof97': 0x2CFFF0}   # bank 2; KOF97's from its copy of KOF98's loader ($4AD6)
def pal_rom98(m, n): return [0] + [m.u16(PAL_ROM[m.game] + n * 32 + 2 * i, 2) for i in range(1, 16)]
def palettes98(m, cid, used):
    """KOF98: palette n at bank 2 $2D77F0 + n*32 (loader $518A). Sprite palette byte 16+k = body palette k, at
    n = $100 + id*$40 + $10*set + k (four colour sets A-D, chosen at character select, team record +7..9);
    32+k = effect palette k, at n = $B80 + id*$10 + k (one for all sets). Checked against palette RAM in a fight
    (P1 slots 16/32, P2 48/64). `used` = the palette bytes the exported frames use, in index order;
    returns colour sets A-D, one palette per used byte (effects are the same in every set)."""
    # KOF99 (palette RAM dumped in our emulator, bank 1): body n = $100 + id*$20 + $10*set, TWO colour sets
    # (select with B = set 1), effects n = $520 + id*$10
    body, step, sets, eff = (0x100, 0x20, 2, 0x520) if m.game == 'kof99' else (0x100, 0x40, 4, 0xB80)
    def n(b, s): return body + cid * step + 0x10 * s + (b - 16) if b < 32 else eff + cid * 0x10 + (b - 32)
    return [[pal_rom98(m, n(b, s)) for b in used] for s in range(sets)]

PHYS = {'kof98': (0xABFC8, 0xAC060), 'kof99': (0xB51C4, 0xB524C),     # walk table, jump (vy, gravity) table
        'kof97': (0xA3710, 0xA3790)}                                    # KOF97: KOF98's values for the shared cast, found by them

def physics98(m, cid, prejump=0):
    w, j = PHYS[m.game]
    return jump_physics(m.u32(w + 4 * cid), m.u32(j + 8 * cid), m.u32(j + 4 + 8 * cid), prejump)

# KOF99 (name table at $BCC88): KOF98's engine
# KOF99 states, labelled in our emulator (GAME=kof99 capture/labels.py): KOF98's except the C+D blowback (285)
MOVES99 = dict(MOVES98, blowback=285)
# KOF97: KOF98's states through KOF97's per-fighter map ($AFBCA), checked on Terry's and Orochi's frames (the bosses'
# maps send missing moves to what they have); the win poses are elsewhere (336 is a knockdown frame): not exported
MOVES97 = {k: v for k, v in MOVES98.items() if not k.startswith('win_')}
CAST97 = CAST98[:28] + ['iori_riot', 'leona_orochi', 'orochi', 'shingo']
del MOVES99['win_d'], MOVES99['win_d_hold']     # KOF99: three win poses; holding D picks one of A-C (wins98.py, all 34)
CAST99 = ['k_dash', 'maxima', 'benimaru', 'shingo', 'terry', 'andy', 'joe', 'mai', 'ryo', 'robert', 'yuri', 'takuma',
          'leona', 'ralf', 'clark', 'whip', 'athena', 'kensou', 'chin', 'bao', 'king', 'mary', 'kasumi', 'xiangfei', 'kim',
          'chang', 'choi', 'jhun', 'kyo', 'kyo_1', 'iori', 'krizalid', 'krizalid_2', 'kyo_2']

# Command normals (forward+A, forward+B, down-forward+C, down-forward+D: KOF97+), per fighter: not in the recogniser's
# lists, the normal-attack code reads stick + button. Their states were found by playing them in the game
# (capture/cmdnormals.py -> cmdnormals_<game>.json: fighter -> move -> [state, hits at point blank]); a fighter without
# one for an input has no entry (the game plays the plain normal there).
CMD_NORMALS = {g: json.load(open(os.path.join(HERE, f'cmdnormals_{g}.json'))) for g in ('kof98', 'kof99')
               if os.path.exists(os.path.join(HERE, f'cmdnormals_{g}.json'))}

def cmd_frames(m, cid, rows, slot_of, add_frame):
    """a command normal that goes through several states (Mai's / Billy's hops: code moves the fighter up and forward
    between animation steps) as one animation from its captured frames (capture/cmdnormals.py rows: state, raw step,
    frame record, x forward, height): each run of frames on one KOF step = one step (ticks = its frames), split where
    the height changes; the step's own flags and box commands on its first piece, the pieces before the last carry
    KOF's $4000 'same hit' so a split step stays one hit window. dx = the capture's forward travel (KOF x: negative =
    forward), hy = height in px."""
    parsed, groups = {}, []
    for st, ri, rec, x, h in rows:
        if groups and groups[-1][0] == (st, ri, h): groups[-1][1] += 1
        else: groups.append([(st, ri, h), 1, x])
    steps, prev_x, prev_key = [], 0, None
    for k, ((st, ri, h), n, x) in enumerate(groups):
        if st not in parsed:
            parsed[st] = {s_[4]: s_ for s_ in rom96.parse_anim(m, rom96.anim_addr(m, cid, slot_of(cid, st)))[0]}
        t, fi, fl, b, _, _ = parsed[st][ri]
        first = (st, ri) != prev_key
        last = k + 1 == len(groups) or groups[k + 1][0][:2] != (st, ri)
        steps.append({'frame': add_frame(fi), 'ticks': n, 'flags': fl if last else fl | 0x4000, 'dx': -(x - prev_x),
                      'hy': h, 'boxes': {f'{kk:02X}': v for kk, v in b.items() if first or kk >> 4 != 1 and kk < 0x100}})
        prev_x, prev_key = x, (st, ri)
    return {'slot': slot_of(cid, rows[0][0]), 'mode': 'hold', 'steps': steps, 'captured': True}

def step_boxes(m, cid, sp, slot_of, raw):
    """per row of a capture, (boxes, [state, raw index, step flags]): the step P1 was on (captured state + raw index =
    object +$74 / 6) gives its hurt boxes and, while the step is active (KOF step flag $0100), the attack box: the
    last one stays live on every active step, a box command only comes when it changes, and it stays in the object
    across states. A box on an inactive step is not an attack (Geese's Jaei-ken: the $0630 step after the dash, the
    game's three hits are the dash and the two $07xx steps). A step not found (a capture without steps) falls back to
    the frame's boxes in the move's animations (raw), flags -1. Row step: [state, raw index, flags, P1's hit-stop
    counter (+$124 high byte, $FF none), P1's live box (+$90: type x y w h), P2's state, height, life, x from P1's
    start, KOF98's hit effect [kind +$1B8, burn +$1BA], the step's ROM ticks] (None: a
    capture without them)."""
    out, live, parsed = [], None, {}
    for (f, x, h, objs), ps in zip(sp['rows'], sp.get('steps') or [[None, None]] * len(sp['rows'])):
        s_, ri = ps[0], ps[1]
        extra = ([ps[5], ps[4], ps[2], ps[6], ps[3], ps[7]] if len(ps) > 7 else [0xFF, None, None, None, None, None]) + \
            [ps[8] if len(ps) > 8 else None]
        if s_ is not None and s_ not in parsed:
            try: parsed[s_] = {st_[4]: st_ for st_ in rom96.parse_anim(m, rom96.anim_addr(m, cid, slot_of(cid, s_)))[0]}
            except Exception: parsed[s_] = {}
        step = parsed.get(s_, {}).get(ri)
        if step is None:
            out.append((raw.get(f, {}), [s_, ri, -1] + extra + [None])); continue
        b = {f'{k:02X}': v for k, v in step[3].items()}
        atk = {k: v for k, v in b.items() if k[0] == '1'}
        hurt = {k: v for k, v in b.items() if k[0] != '1'}
        if atk: live = atk
        atk = live if step[2] & 0x100 and live else {}
        out.append(({**hurt, **atk}, [s_, ri, step[2]] + extra + [step[0]]))   # + the step's ROM ticks
    return out

CONT_HIT_ROWS = 4          # a continuation's hit stays live this many rows (the brawler's victim may have moved a little)

def special_entry(m, cid, sp, add, slot_of, game):
    """one captured special -> its script (export layout). Rows: [frame, x from start, height, objects]; row_boxes /
    row_steps per row (step_boxes); marks per row, letters: 'c' contact (the move's grab reaches the opponent, no
    damage), 'j' a hit here goes on to the continuation, 'h' a hit of the continuation (opens a new hit). cont = 0, or
    the first row of the hit-confirmed continuation. version: 'hit' (the script is a capture where the move reached
    the opponent: the close-range one when it landed hits, or a far one a long rush still reached; the game's contact
    freezes are in it, export_bm.special_play turns them into hit markers), 'whiff', or 'whiff+continuation'.

    Hit-confirmed continuations: when the move's close-range capture (sp['close'], P2 in reach) goes through special
    states its whiff does not (Geese's Jaei-ken: dash 146, then 148 149 on contact; Kyo's Kototsuki You: run 135, then
    grab 137 138 140), the script is the whiff (all of it: a miss plays as in the game) followed by the close capture
    from its first different state on (x relative to the contact point). The fighter jumps to `cont` when it hits
    during the whiff, before its last state (the recovery); reaching `cont` without a hit ends the move. The
    continuation's hits are the game's: one per drop of P2's life in the close capture, live on the row before the
    drop for CONT_HIT_ROWS rows (not counting the game's hit-stop rows), the box of the step if active, else the object's live box at that row (+$90; Kyo's
    explosion is dealt by code while the victim is held, its box sits on the victim). A whiff without any attack box
    before its recovery (a running grab: KOF tests contact by code) gets the continuation's first box as contact box
    (inference: the reach of KOF's own contact test is not decoded)."""
    def entry_states(e, n):
        st = e['states']
        return [[s, (st[k + 1][0] if k + 1 < len(st) else n) - t, slot_of(cid, s)] for k, (t, s) in enumerate(st)]
    def raw_boxes(states):
        raw = {}                                    # boxes per ROM frame in the move's own animations
        for s_, d_, sl in states:
            try: steps_, _ = rom96.parse_anim(m, rom96.anim_addr(m, cid, sl))
            except Exception: continue
            for t, fi, fl, b, ri, _ in steps_: raw.setdefault(fi, {f'{k:02X}': v for k, v in b.items()})
        return raw
    H, k, version, shape = sp.get('close'), None, 'whiff', None   # shape: the whiff's (travel, height, objects)
    if H:
        wp = [s for t, s in sp['states'] if specials96.special_state(game, s)]
        hs = [(t, s) for t, s in H['states'] if specials96.special_state(game, s)]
        k = next((i for i, (t, s) in enumerate(hs) if i >= len(wp) or wp[i] != s), None)
        if not k:                                   # no continuation: the hit version is the script when it hit
            shape = (max(r[1] for r in sp['rows']), max(r[2] for r in sp['rows']), any(r[3] for r in sp['rows']))
            if game_hits(H): sp = dict(sp, rows=H['rows'], steps=H['steps'], states=H['states'])
            H = None
    if game_hits(sp): version = 'hit'               # (a long rush also reached P2 in the far capture)
    states = entry_states(sp, len(sp['rows'])); raw = raw_boxes(states)
    rows = [list(r) for r in sp['rows']]; sb = step_boxes(m, cid, sp, slot_of, raw)
    marks = [''] * len(rows); cont = 0
    if H:
        h0 = hs[k][0]                           # first row of the continuation in the close capture
        hstates = entry_states(H, len(H['rows'])); hraw = raw_boxes(hstates)
        hsb = step_boxes(m, cid, H, slot_of, hraw)
        bx = H['rows'][h0 - 1][1]               # contact point: x of the row before
        last = max(t for t, s in sp['states'] if specials96.special_state(game, s))   # the whiff's recovery state starts here
        if not any(kk[0] == '1' for b, _ in sb[:last] for kk in b):
            first = next((b for b, _ in hsb[h0:] if any(kk[0] == '1' for kk in b)), None)
            if first:
                fa = {kk: v for kk, v in first.items() if kk[0] == '1'}
                for i in range(last):
                    sb[i] = ({**sb[i][0], **fa}, sb[i][1]); marks[i] = 'c'
        for i in range(last): marks[i] += 'j'
        cont = len(rows)
        life = [ps[3] for ps in H['steps']]
        hit_rows = {i - 1 for i in range(max(h0, 1), len(life)) if life[i] < life[i - 1]}
        live_of = {}                                # row -> the hit row whose box is live on it (the hit row,
        for j in sorted(hit_rows):                  # then CONT_HIT_ROWS - 1 rows past the game's hit-stop)
            i, n = j, 0
            while i < len(H['rows']) and n < CONT_HIT_ROWS:
                live_of[i] = j; n += i == j or H['steps'][i][5] == 0xFF; i += 1
        crow, cmark = [], []
        for i in range(h0, len(H['rows'])):
            f, x, h, objs = H['rows'][i]
            b, st_ = hsb[i]
            atk = {kk: v for kk, v in b.items() if kk[0] == '1'}
            hurt = {kk: v for kk, v in b.items() if kk[0] != '1'}
            if i in live_of:
                j = live_of[i]
                if not atk:
                    t_, bxx, byy, bw, bh = H['steps'][j][4]
                    atk = {f'{0x10 | t_ if t_ < 16 else 0x100 | t_:02X}': [bxx, byy, bw, bh]}
            else: atk = {}
            crow.append([f, x - bx, h, [[of, ox - bx, oh, same] for of, ox, oh, same in objs]])
            sb.append(({**hurt, **atk}, st_)); marks.append('h' if i in hit_rows else '')
        rows += crow
        states += [[s, d, sl] for s, d, sl in entry_states(H, len(H['rows'])) if s in {s_ for t_, s_ in hs[k:]}]
        raw.update({f: b for f, b in hraw.items() if f not in raw})
    script = [[add(f), x, h, [[add(of), ox, oh, same] for of, ox, oh, same in objs]] for f, x, h, objs in rows]
    fb = {add(f): raw[f] for f, x, h, objs in rows if f in raw}   # boxes of the frames the script shows
    return {'slot': sp['cmd'], 'input': sp['input'], 'condition': sp['condition'], 'button': sp['button'],
            'state': sp['state'], 'states': states, 'script': script, 'frame_boxes': fb,
            'row_boxes': [b for b, _ in sb], 'row_steps': [st_ for _, st_ in sb], 'marks': marks, 'cont': cont,
            'game_hits': game_hits(H) if H else game_hits(sp) if sp.get('close') or version == 'hit' else -1,
            'version': 'whiff+continuation' if cont else version, 'shape': shape}

def projectile_entry(m, cid, d, add, slot_of):
    """a projectile (one of projectiles96.definition's) in export terms: frames through the fighter's own frame list (the
    projectile is drawn from its table +$70, the fighter's own for every roster projectile), per flight row [frame, x
    from the spawn point (px, forward +), height, live attack box (KOF box type, x, y, w, h: the game's +$90 slot 0
    while +$7C bit 0) or None, its own box (slot 1, key '31': the box another projectile's attack meets, a clash) or
    None]; child: the trail it spawns (same rows; births = its frames that spawn one, dx / dy from its place then);
    end rows (after its hit: [frame, x from the impact, height]); the victim's reaction measured after the hit
    (P2's states: 256-279 a grounded hit reel, 280-399 knocked down)"""
    parsed = {}
    def step(tid, st, raw):
        assert tid == cid, (cid, tid, st)               # drawn from the fighter's own frames
        if st not in parsed: parsed[st] = {s_[4]: s_ for s_ in rom96.parse_anim(m, rom96.anim_addr(m, cid, slot_of(cid, st)))[0]}
        return parsed[st][raw]
    def flight(rs): return [[add(step(tid, st, raw)[1]), x, y, box, step(tid, st, raw)[3].get(0x31)] for tid, st, raw, x, y, fl, box in rs]
    rows = flight(d['rows'])
    c = d.get('child')
    child = c and {'rows': flight(c['rows']), 'loop': c['loop'], 'births': c['births'], 'dx': c['dx'], 'dy': c['dy']}
    hit = next((h for k, h in sorted(d['hits'].items(), key=lambda kv: -int(kv[0])) if h.get('hits')), None)
    end = [[add(step(tid, st, raw)[1]), x, y] for tid, st, raw, x, y in (hit['end_rows'] if hit else [])]
    react = None
    if hit:
        rs = [r for r in hit['reaction'] if r]
        react = 'knockdown' if any(280 <= r < 400 for r in rs) else 'heavy' if any(256 <= r < 280 for r in rs) else None
    return {k: d[k] for k in ('table', 'state', 'kind', 'hit_kind', 'spawn_row', 'spawn_x', 'spawn_y', 'loop', 'death',
                              'life', 'travel', 'vx')} | {'rows': rows, 'end': end, 'react': react, 'child': child,
            'hits': {k: {kk: v.get(kk) for kk in ('hits', 'frame', 'x', 'damage', 'victim_stop', 'owner_frozen')} for k, v in d['hits'].items()}}

def game_hits(e):
    """hits a capture landed: drops of P2's life (object +$138) while the move plays"""
    life = [ps[3] for ps in e.get('steps', []) if len(ps) > 3]
    return sum(1 for i in range(1, len(life)) if life[i] < life[i - 1])

def export(names, outdir, game='kof96', only=None, extra=None):
    """only: a set of move names to export (a game's subset, e.g. the brawler's); then no other slots, throws or specials.
    extra: {name: {move: (state, step)}} more moves for one fighter, each a single held frame (the animation's step
    `step`, -1 = its last): the brawler's 'watch' pose (export_bm.WATCH)"""
    prom, crom = rom96.load(rom96.GAMES[game]['neo']); m = rom96.Mem(prom, game)
    k98 = game in ('kof97', 'kof98', 'kof99')           # KOF97 and KOF99 use KOF98's layout
    cast, moves = {'kof97': (CAST97, MOVES97), 'kof98': (CAST98, MOVES98), 'kof99': (CAST99, MOVES99)}.get(game, (CAST, MOVES))
    mp = None if k98 else rom96.shared_map(m)
    def slot_of(cid, st): return rom96.state_slot(m, cid, st) if k98 else mp[st]
    tile_map, out = {}, {'game': game, 'tile_base': TILE_BASE, 'characters': {}}
    def our_tile(code):
        if code is None: return 0
        if code not in tile_map: tile_map[code] = TILE_BASE + len(tile_map)
        return tile_map[code]
    adders = {}
    for name in names:
        cid = cast.index(name)
        frames, index, used = [], {}, []
        def add_frame(fidx, cid=cid, frames=frames, index=index, used=used):
            if fidx not in index:
                index[fidx] = len(frames); parts = []
                for p in rom96.frame_parts(m, cid, fidx):
                    sd = rom96.sdef(m, cid, p['sdef'])
                    if not sd['cols']: continue
                    if k98:                         # index into the character's used palette bytes
                        b = sd['pal'] if 16 <= sd['pal'] < 48 else 16
                        if b not in used: used.append(b)
                        pal = used.index(b)
                    else: pal = (sd['pal'] - 16) % 16 if 16 <= sd['pal'] < 112 else 0
                    parts.append({'dx': p['dx'], 'dy': p['dy'], 'hflip': p['hflip'], 'vflip': p['vflip'], 'pal': pal,
                                  'tiles': [[our_tile(t) for t in col] for col in sd['cols']]})
                frames.append({'record': f'{cid}:{fidx}', 'parts': parts})
            return index[fidx]
        anims = {}
        cmd_def = CMD_NORMALS.get(game, {}).get(name, {})
        cmds = {k: v[0] for k, v in cmd_def.items() if len(v) < 3}
        for move, v in cmd_def.items():                 # a command normal through several states (a hop): its frames
            if len(v) < 3 or (only is not None and move not in only): continue
            anims[move] = cmd_frames(m, cid, v[2], slot_of, add_frame) | {'state': v[0]}
        for move, state in list(moves.items()) + list(cmds.items()):
            if only is not None and move not in only: continue
            slot = slot_of(cid, state)
            try: steps, mode = rom96.parse_anim(m, rom96.anim_addr(m, cid, slot))
            except Exception: continue
            anims[move] = {'slot': slot, 'state': state, 'mode': mode, 'steps': [
                {'frame': add_frame(fi), 'ticks': t, 'flags': fl, 'dx': dx, 'boxes': {f'{k:02X}': v for k, v in b.items()}} for t, fi, fl, b, ri, dx in steps]}
        if game != 'kof97' and (only is None or 'win' in only):
            parts, wsteps = [], []
            for st in win_states(game, cid):
                slot = slot_of(cid, st); steps, mode = rom96.parse_anim(m, rom96.anim_addr(m, cid, slot))
                parts.append([slot, len(wsteps), len(steps)])
                wsteps += [{'frame': add_frame(fi), 'ticks': t, 'flags': fl, 'dx': dx, 'boxes': {f'{k:02X}': v for k, v in b.items()}}
                           for t, fi, fl, b, ri, dx in steps]
            anims['win'] = {'slot': parts[0][0], 'state': win_states(game, cid)[0], 'parts': parts, 'mode': 'hold', 'steps': wsteps}
        for move, (state, step) in (extra or {}).get(name, {}).items():
            slot = slot_of(cid, state); steps, mode = rom96.parse_anim(m, rom96.anim_addr(m, cid, slot))
            t, fi, fl, b, ri, dx = steps[step]
            anims[move] = {'slot': slot, 'state': state, 'mode': 'hold', 'steps': [{'frame': add_frame(fi), 'ticks': 1, 'flags': 0, 'dx': 0, 'boxes': {}}]}
        # every other animation slot of the table, with the game states that select it (intros, win poses, phases...)
        inv = {}
        for st in range(512):
            try: inv.setdefault(slot_of(cid, st), []).append(st)
            except Exception: pass
        named = {a['slot'] for a in anims.values()}
        for slot in (range(512) if only is None else []):
            if slot in named: continue
            try:
                a = m.u32(m.u32(m.g['anims'] + cid * 4) + slot * 4)
                if not (0x080000 <= a < 0x300000): continue
                steps, mode = rom96.parse_anim(m, a)
            except Exception: continue
            if not steps: continue
            try:                                        # frames decodable, else not an animation (past the table)
                for t, fi, fl, b, ri in steps:
                    for p in rom96.frame_parts(m, cid, fi): rom96.sdef(m, cid, p['sdef'])
            except Exception: continue
            anims[f'slot_{slot}'] = {'slot': slot, 'states': inv.get(slot, []), 'mode': mode, 'steps': [
                {'frame': add_frame(fi), 'ticks': t, 'flags': fl, 'dx': dx, 'boxes': {f'{k:02X}': v for k, v in b.items()}} for t, fi, fl, b, ri, dx in steps]}
        out['characters'][name] = {'id': cid, 'effect_palettes': {}, 'frames': frames, 'anims': anims,
                                   'physics': (physics98 if k98 else physics)(m, cid, prejump_frames(m, cid, slot_of(cid, 3))), 'throws': {}, 'specials': [],
                                   'palette_bytes': used}
        adders[name] = add_frame
        print(f'{name}: {len(frames)} frames, {len(anims)} animations', flush=True)
    # throws for every victim exported here (throwscripts96.py): the thrower's own animation + a per-video-frame script
    have_throws = os.path.exists(os.path.join(HERE, 'capture', throwscripts96.TDIR.get(game, 'throws_' + game), 'tables.json'))
    if only is not None and not (only & {'throw_c', 'throw_d', 'air_throw'}): have_throws = False
    found = throwscripts96.all_throws(m, mp, [cast.index(n) for n in names]) if have_throws else {}
    if only is None or only & {'throw_c', 'throw_d'}:          # the pilot's throws read from the ROM (throwrom.py, TODO
        import throwrom                                         # #146): they replace the captured scripts
        found.update(throwrom.all_throws(m, game, [cast.index(n) for n in names]))
    import throwrom
    for cid, d in found.items():
        name = cast[cid]
        if name not in names: continue
        ch = out['characters'][name]
        for key, b in d.items():
            if only is not None and key not in only: continue
            st = b['thrower_state']; sl = slot_of(cid, st)
            steps, mode = rom96.parse_anim(m, rom96.anim_addr(m, cid, sl))
            ch['anims'][key] = {'slot': sl, 'state': st, 'mode': mode, 'steps': [
                {'frame': adders[name](fi), 'ticks': t, 'dx': dx, 'boxes': {f'{k:02X}': v for k, v in bx.items()}} for t, fi, fl, bx, ri, dx in steps]}
            timeline = [[adders[name](t[0]) if t[0] is not None else -1] + list(t[1:]) for t in b['timeline']]
            victims = {cast[v]: [[adders[cast[v]](r[0]) if r[0] is not None else -1] + r[1:] for r in rows]
                       for v, rows in b['victims'].items() if cast[v] in adders}
            ch['throws'][key] = {'slot': sl, 'inputs': b['inputs'], 'table': b['lists'], 'hold': b.get('hold', False),
                                 'timeline': timeline, 'victims': victims, 'impacts': b.get('impacts', []),
                                 'fx': throwrom.throw_fx(m, game, cid, sl)}   # the throw-start effect (TODO #166)
            if b.get('rom'):                                    # read from the ROM: its decoded points + conversion sheet
                ch['throws'][key].update({k: b[k] for k in ('release', 'land', 'down', 'end', 'ret', 'sheet')}, rom=True)
        print(f'{name}: throws {list(d)}', flush=True)
    # specials captured in our emulator (capture/specials96.py): frames of the fighter and of its projectiles, both in its own list
    # (a filtered export takes them when `only` names 'specials'; each then carries frame_boxes: the boxes of every frame
    #  of its own state animations, so a player of the script knows when the fighter's body hits)
    for name in (names if only is None or 'specials' in only else []):
        cid = cast.index(name); add = adders[name]; sps = []
        pdefs = projectiles96.definitions(game, cid)     # capture/projectiles.py: the move's projectile, by identity
        for sp in specials96.load(m, cid):
            e = special_entry(m, cid, sp, add, slot_of, game)
            if sp['input'] in pdefs: e['projectiles'] = [projectile_entry(m, cid, d, add, slot_of) for d in pdefs[sp['input']]]
            t0 = 0; starts = []                                      # the super flash its animations start (a DM's;
            for s_, d_, sl_ in e['states']: starts.append((s_, t0)); t0 += d_   # handlers98.super_flash)
            e['flash'] = handlers98.super_flash(m, cid, starts)
            if handlers98.ROM_GAME.get(name, 'kof98') == game and sp['input'] in handlers98.ROM_SPECIALS.get(name, ()):   # read from the ROM:
                e['rom'] = handlers98.export_rom(m, cid, sp['input'], add)                  # its handler's program
                e['flash'] = e['rom'].get('flash') or e['flash']
            sps.append(e)
            if 'rom' in e and any(v['sdm'] for v in e['rom'].get('variants', [])) and not e['input'].startswith('MAX '):
                # a DM's MAX version (TODO #139, down+D): the same handler with +$E4 bit 0 set, this button's path (the
                # handler's own button test decides A / C: handlers98.md "Super flash"); its script = the DM's capture
                # (the Lab's data; the game plays the program)
                rom = handlers98.export_rom(m, cid, 'MAX ' + sp['input'], add)
                if 'error' not in rom: sps.append(dict(e, input='MAX ' + sp['input'], rom=rom, flash=rom['flash'], max_of=sp['input']))
        out['characters'][name]['specials'] = sps
        try:                                            # the decoded command list (inputs), captured or not
            out['characters'][name]['commands'] = [commands96.notation(p) for k, p in
                                                   enumerate(commands96.patterns(m, commands96.lists(m, cid)[1])) if p and k >= 3]
        except Exception: pass
        print(f'{name}: {len(sps)} specials', flush=True)
    for name in names:                              # palettes last: KOF98 lists the palette bytes the frames use
        ch = out['characters'][name]; cid = cast.index(name)
        sets = palettes98(m, cid, ch['palette_bytes'] or [16]) if k98 else list(palettes(m, cid))
        ch.update({'palette': sets[0][0], 'palette_mirror': sets[min(1, len(sets) - 1)][0], 'block_palettes': sets})
        if k98: ch['palette_sets'] = [st[ch['palette_bytes'].index(16) if 16 in ch['palette_bytes'] else 0] for st in sets]
    out['tiles'] = len(tile_map)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * (TILE_BASE + len(tile_map)))
    for code, ours in tile_map.items(): region[ours * 128:(ours + 1) * 128] = crom[code * 128:(code + 1) * 128]
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))       # file names the gallery reads
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    args = sys.argv[1:]; game = 'kof96'
    if args[:1] == ['--game']: game = args[1]; args = args[2:]
    outdir = args[0]; names = args[1:] or ['kyo']
    if names == ['all']: names = {'kof98': CAST98, 'kof99': CAST99}.get(game, CAST)
    o = export(names, outdir, game); print('tiles', o['tiles'], f"({o['tiles'] * 128 // 1024} KB)")
