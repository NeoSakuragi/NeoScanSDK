#!/usr/bin/env python3
"""The Last Blade 2's special moves and throws as brawler programs (bprim_t, fighter.c prog_update), read from the ROM.

LB2 keeps a special's logic in DATA [code]: the recogniser's result is a row of the move table ($A0000[row * 256 +
state class - 1]), the move is a descriptor (bank 2, $76554[char] + 16 move: animation numbers and control words), and
each animation is a bytecode script (frames + ticks per style, velocities / accelerations with their frame counts,
landings and button waits, boxes, sounds, effect objects). model_lb2.py plays that data exactly as the 68000 code does
(check_model.py: every special's frame, x and height equal to the game's in our emulator). A special's program is
generated from that play: one program state per run of frames whose motion is one velocity + one acceleration (the
script's segments), its steps the frames shown in it; each state = P_ANIM, the velocities, a frame count, then per
frame P_MOVE / P_ADD (x: v += a before the move, LB2's $2BC9C order) and P_FALL (height), P_DEC, the next state when
the count runs out. `check` plays every program with the brawler's own player (handlers_ss2.Play, a port of fighter.c
prog_update) against the model, frame by frame. Each button version is its own special (input '214A', '214B' ...: one
S- piece each). Throws: the paired script of the thrower's animation and the victim's own thrown animation.

Labels: [code] read in the disassembly (/data/tmp/lastbld2/*.dis), [meas] measured in our emulator."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'samsho2'))
import lb2 as L, model_lb2 as M
import handlers_ss2 as HS                       # the brawler's op numbers (bm_chars.h P_* / PC_*) and its player (Play)

P, REG, PC = HS.P, HS.REG, HS.PC
R_HEAVY, R_KNOCKDOWN, R_LAUNCH = HS.R_HEAVY, HS.R_KNOCKDOWN, HS.R_LAUNCH
SPECIAL_DAMAGE = HS.SPECIAL_DAMAGE

# ---- the recogniser ($3144A) ---------------------------------------------------------------------------------------
# per character long $76C14[char] -> per button class ($76B74[buttons >> 4]: A 1, B 2, C 3, D 4, A+B 5) a linked list of
# entries [long next][type: window $76C04 (0 23, 1 39, 2 15, 3 19 frames)][pattern bytes]: a byte with low nibble F is
# an op (high nibble, $76B84: 0 charge [frames][dirs], 1 desperation (Power / EX, gauge full, life < 65), 2 super
# (gauge full, or life < 65), 3 Speed / EX gauge full, 4 [cls] state class ==, 5 [h] height <=, 6 on the ground,
# 7 always, 8 [cls] state class !=, 9 [x] (a sound), 10 [cls] class <, 11 [cls] class >=, 12 [k] sub-condition $76BC4,
# 13 gauge >= 64, 14 refused, 15 [row] matched: the result row); else a stick direction (1 up, 2 down, 4 back, 8
# forward once turned to the opponent), the most recent first.
DIRS = {0: '5', 1: '8', 2: '2', 4: '4', 8: '6', 5: '7', 6: '1', 9: '9', 10: '3'}
BUTTON_CLASS = {1: 'A', 2: 'B', 3: 'C', 4: 'D', 5: 'AB'}

def commands(ch):
    """[(buttons, input numpad oldest first, ops [(op, arg)], row)] of the character's recogniser lists"""
    t = L.u32(0x76C14 + 4 * (ch & 31)); out = []
    for bc, bn in BUTTON_CLASS.items():
        a = L.u32(t + 4 * bc)
        for _ in range(64):
            if not a: break
            nxt = L.u32(a); q = a + 5; dirs, ops, row = [], [], None
            for _ in range(40):
                c = L.u8(q); q += 1
                if c & 15 == 15:
                    op = c >> 4
                    if op == 15: row = L.u8(q); break
                    if op == 14: break
                    arg = None
                    if op == 0: arg = (L.u8(q), L.u8(q + 1)); q += 2
                    elif op in (4, 5, 8, 9, 10, 11, 12): arg = L.u8(q); q += 1
                    ops.append((op, arg))
                else: dirs.append(c & 15)
            if row is not None:
                out.append((bn, ''.join(DIRS.get(d, '?') for d in reversed(dirs)), ops, row))
            a = nxt
    return out

# ---- Moriya's specials (SNK's names: snk.fandom.com "Moriya Minakata/Move List", read through its API 2026-10-12;
# /data/neogeo_dict/lastbld2/moriya_movelist_wiki.txt). input -> (row, style, name). The rows from the recogniser
# lists (commands(1)); the move = $A0000[row][class 1] (standing), its descriptor and animations [code]:
#   236A  row $77 -> move $90 [801B 8001 9002 00B6]: Ittou Tsukikage, A (the first slash; again 236A x2 from its window)
#   236B  row $78 -> $91 [801B 8001 9002 00B9]      623A row $79 -> $92 [8001 9002 00B4]: Ittou Shingetsu
#   623B  row $7A -> $93 [8001 9004 00B5]: Ittou Shingetsu Ri
#   214A/B/C rows $7B-$7D -> $94-$96 [8001 0092 (A2C6 9CC5: farther than 176 / 96 px -> moves $C6 / $C5) 8001 0094]:
#         Ittou Oboro (high / mid / low); the stand-by: anim $92's segment $84xx holds while the button is held
#   412A/B/C rows $7E-$80 -> $97-$99 [8001 00B3 8009 / 800A / 800B 00AF / 00B0]: Taitou Hogetsu, the teleport (sub-ops
#         9 / 10 / 11: placed 288 short of / 80 short of / 110 past the opponent: P_WARP)
#   64123AB row $86 -> $9F [8001 800D 00A0 8001 00A1]: Kassatsu Izayoi Gekka (super: gauge full or life < 65)
#   641236B row $8A -> $A3 [8001 801B 800D 00A2]: Kassatsu Midare Setsugekka (desperation: Power / EX, gauge, low life)
#   22A / 22B rows $8C / $8D -> $A5 / $A6 [800D 8001 01C1 01C4 / 01C2 01C5]: Kassatsu Byakuya (Speed / EX's super)
SPECIALS = {
    'moriya': {
        '236A': (0x77, 0, 'Ittou Tsukikage'), '236B': (0x78, 0, 'Ittou Tsukikage'),
        '623A': (0x79, 0, 'Ittou Shingetsu'), '623B': (0x7A, 0, 'Ittou Shingetsu Ri'),
        '214A': (0x7B, 0, 'Ittou Oboro (high)'), '214B': (0x7C, 0, 'Ittou Oboro (mid)'), '214C': (0x7D, 0, 'Ittou Oboro (low)'),
        '412A': (0x7E, 0, 'Taitou Hogetsu (back)'), '412B': (0x7F, 0, 'Taitou Hogetsu (forward)'), '412C': (0x80, 0, 'Taitou Hogetsu (behind)'),
        '64123AB': (0x86, 0, 'Kassatsu Izayoi Gekka (super)'), '641236B': (0x8A, 0, 'Kassatsu Midare Setsugekka (desperation)'),
        '22A': (0x8C, 1, 'Kassatsu Byakuya (Speed super)'), '22B': (0x8D, 1, 'Kassatsu Byakuya (Speed super)'),
    }}
# ---- the impact sounds (T5, 2026-10-14) ---------------------------------------------------------------------------------
# LB2's hit code ($3AF7E) picks a hit's sound from a FAMILY: a class word $A0nn ($7A198[strength][kind]: the attack box's
# strength and its hit word $70270[box type]) -> $2948E's table -> a function that draws list[RNG $3E30 & mask] [code];
# the lists are songs.json sfx "picks" 'LB2 A0' .. 'LB2 A9' (read from those functions). Which family each of Moriya's hits
# uses is MEASURED in our emulator (tools/lastbld2/hitsound_lb2.py: every move hitting P2 over 8-12 RNG states, the $17
# codes it queues; the family = the smallest list holding them all) [meas]: the slashes A0-A5 / A8-A9 by weight, the kicks
# A8 / A9. Normals: his animation -> family (export_lb2: anims[mv]['hitsnd']); specials: per LB2 hit in order (a new hit =
# a new attack box type), the last one repeating -> rom['step_snd'] (export_bm: the step's own pick list, fighter.c
# step_sound). Byakuya's stage pieces (Speed / EX chain, not measured: their gauge / style set-up) take the chain's slash
# family A1 [inf].
NORMAL_SND = {0x30: 'A8', 0x31: 'A4', 0x34: 'A5', 0x35: 'A8', 0x36: 'A9', 0x37: 'A4', 0x38: 'A1', 0x39: 'A8', 0x3A: 'A9',
              0x3B: 'A4', 0x3C: 'A0', 0x3D: 'A8', 0x91: 'A2'}
SPECIAL_SND = {'moriya': {
    '236A': ['A5'], '236B': ['A5'], '236A>BD': ['A1'], '236A>BE': ['A1'], '236B>BA': ['A1'], '236B>CA': ['A1'], '236B>9B': ['A1'],
    '623A': ['A8', 'A1'], '623A>B2': ['A1'], '623B': ['A9', 'A1'], '214A': ['A0', 'A1'], '214B': ['A4', 'A1'], '214C': ['A4', 'A1'],
    '64123AB': ['A4'] * 5 + ['A0', 'A4'] * 5, '641236B': ['A5'], '641236B>B1': ['A1', 'A1', 'A5', 'A1', 'A1', 'A1', 'A1', 'A8', 'A1'],
    '22A': ['A0'], '22B': ['A0'], **{f'22A>{m:X}': ['A1'] for m in range(0xD4, 0xDD)}}}

def step_sounds(rom, fams):
    """[(state index, step, 'LB2 <family>')] for every step with an attack box: LB2 hit k = the k-th opening that does
    not continue the step right before it with the same attack box types (the steps' 'lb2_atk': a box re-written with
    other coordinates is the same hit, 623A's $AB), fams[k] (the last repeating)"""
    out, k, prev = [], -1, None
    for j, st in enumerate(rom['states']):
        steps = rom['anims'][st]['steps']
        op = openings(steps)
        for i, s in enumerate(steps):
            t = tuple(s.get('lb2_atk') or ())
            if not t: prev = None; continue
            if op[i] and t != prev: k += 1
            prev = t
            out.append((j, i, 'LB2 ' + fams[min(max(k, 0), len(fams) - 1)]))
    return out

# the descriptor's teleports -> P_WARP (a = 0: at its target, b px short of it, turned to it; model_lb2.WARP)
WARP_B = {9: 288, 10: 80, 11: -110}

# ---- the follow-ups [code] (2026-10-12) -------------------------------------------------------------------------------
# A FOLLOW-UP is another move the transition table starts from the state class the move's own script set ($92): while
# that class holds, $A0000[row * 256 + class - 1] maps the next input row to a new move (the standing class 1 maps the
# same rows to the plain moves). Rows: 9 A, $12 B, $1B C (the stick neutral; 9 rows a button), $77 / $78 the
# recogniser's 236A / 236B results ($77 also 236C in the classes of $76BC4 sub-condition 6: 152 154 155 158 166 168).
#   Ittou Tsukikage A: $90 (class 184) -$77-> $BD (class 185) -$77-> $BE: the three slashes (236A x3)
#   Ittou Tsukikage B: $91 (class 173) -$78-> $BA (186) -$78-> $CA (187) -$78-> $9B: the four slashes (236B x4)
#   Kassatsu Byakuya: $A5 / $A6 (class 144 from its slash $1C4) -9-> $D4 (145) -$12-> $D5 (146) -$1B-> $D6 (147): stage 1
#     A B C; from $D6 -9-> $D7 (148) -$12-> $D8 (149) -$1B-> $D9 (150): stage 2 route 1 A B C; from $D9 -9-> $DA (151)
#     -$12-> $DB (152) -$77-> $DC: stage 3 route 1 A B 236C (the other routes, not imported: $D6 -2C-> $E1 .. $EB, $D9 -C->
#     $DD $DE $DF $E0)
# The brawler plays a chain as a PRESSED SEQUENCE (game.json roster[].seq_press, docs/brawler_gold.md): each piece = the
# move alone (its descriptor from its start: the model's play), its follow-up point (PF_EVENT, step flag $80) = the
# first frame of its class window after its last attack frame in that window (the slash out whole; LB2 takes the next
# input anywhere in the window), the window's last frame when it attacks to its end.
# ON HIT [code]: the hit code ($3732C) reads the attacker's hit record, word [$7935E + 4 char] (bank 3) + ((attack box
# type - $A0) * 64 + victim box type & 63) * 2 -> +$F4 / +$F6; $37424: byte 1 = the attacker's next move (unless the
# word is $FFFF / $FF0x) -> +$198, started by $37DA6 ($2EA3E) the next frame. Kassatsu Midare Setsugekka's run ($A3 ->
# anim $A2, box type $A3): every standing body type ($C0 / $C4: words $3DB1 / $3EB1) -> move $B1 = anim $A5, the
# slashing sequence (measured: P1 move $B1 the frame after the run connects, P2 life 256 -> 224). -> roster[].hit_next.
#   Ittou Shingetsu -> Ittou Sougetsu (2026-10-14, T6): $92 sets class 78 in Speed / EX only (Power: no class, no
#     follow-up); from class 78 row $7A (the recogniser's 623B) -> $B2 (anim $BF, the second rising slash), the window =
#     Shingetsu's whole play (class 78 on every frame). Shingetsu's Power and Speed frames, x and heights are identical
#     (model rows equal but the class), so its piece keeps the Power program and the chain reads Speed's classes
#     (FOLLOW_STYLE); Sougetsu is played from its Speed data (the style that has it). $B2 sets no class: no third piece.
FOLLOW = {'moriya': {'236A': [0x77, 0x77], '236B': [0x78, 0x78, 0x78], '623A': [0x7A],
                     '22A': [0x09, 0x12, 0x1B, 0x09, 0x12, 0x1B, 0x09, 0x12, 0x77]}}
FOLLOW_STYLE = {'moriya': {'623A': 1}}            # the style whose classes carry the follow-up (default: the special's)
HIT_NEXT = {'moriya': {'641236B': 0xA3}}           # the special -> its attack box type (the hit record's row)
FOLLOW_NAMES = {0xBD: 'Ittou Tsukikage (A, 2nd slash)', 0xBE: 'Ittou Tsukikage (A, 3rd slash)',
                0xBA: 'Ittou Tsukikage (B, 2nd slash)', 0xCA: 'Ittou Tsukikage (B, 3rd slash)', 0x9B: 'Ittou Tsukikage (B, 4th slash)',
                0xD4: 'Kassatsu Byakuya stage 1 (A)', 0xD5: 'Kassatsu Byakuya stage 1 (B)', 0xD6: 'Kassatsu Byakuya stage 1 (C)',
                0xD7: 'Kassatsu Byakuya stage 2 route 1 (A)', 0xD8: 'Kassatsu Byakuya stage 2 route 1 (B)',
                0xD9: 'Kassatsu Byakuya stage 2 route 1 (C)', 0xDA: 'Kassatsu Byakuya stage 3 route 1 (A)',
                0xDB: 'Kassatsu Byakuya stage 3 route 1 (B)', 0xDC: 'Kassatsu Byakuya stage 3 route 1 (236C)',
                0xB1: 'Kassatsu Midare Setsugekka (on hit)', 0xB2: 'Ittou Sougetsu (Shingetsu follow-up)'}

def classes(ch, move, mode):
    rows, _ = move_rows(ch, move, mode)
    return rows

def window(rows, cls):
    """the follow-up point of a move's rows for the transition from state class cls: frame index (module comment)"""
    w = [k for k, r in enumerate(rows) if r['cls'] == cls]
    atk = [k for k in w if any(0 < v[0] < 0xC0 for v in r_boxes(rows[k]))]
    after = [k for k in w if not atk or k > atk[-1]]
    return after[0] if after else w[-1]

def r_boxes(r): return r['boxes'].values()

def chain(ch, move, mode, seq_rows):
    """[(move, follow-up frame of the move before it)]: the moves the rows start in turn from move (module comment)"""
    out, cur = [], move
    for row in seq_rows:
        rows = classes(ch, cur, mode)
        cands = [c for c in dict.fromkeys(r['cls'] for r in rows) if c != 1 and M.transition(row, c)
                 and M.transition(row, c) != M.transition(row, 1)]
        assert len(cands) == 1, (hex(cur), hex(row), cands)
        nxt = M.transition(row, cands[0]); out.append((nxt, window(rows, cands[0]))); cur = nxt
    return out

def hit_next_move(ch, box_type, victim_types=(0xC0, 0xC4)):
    t = L.u32(0x7935E + 4 * (ch & 31))
    ws = {L.u16(t + ((box_type - 0xA0) * 64 + (v & 63)) * 2, 3) for v in victim_types}
    nx = {w & 0xFF for w in ws if w != 0xFFFF and w >> 8 != 0xFF}
    assert len(nx) == 1, ws
    return nx.pop()

_FP = {}
def follow_pieces(name):
    """-> (pieces {input: (move, style, name)}, events {input: follow-up frame index | 'all'}): every follow-up piece
    ('236A>BD': the move $BD after 236A) and the follow-up point of each piece a next one follows (bases included)"""
    if name in _FP: return _FP[name]
    import export_lb2 as X
    ch = X.CAST[name]
    pieces, events = {}, {}
    for base, seq in FOLLOW.get(name, {}).items():
        row, mode, _ = SPECIALS[name][base]
        mode = FOLLOW_STYLE.get(name, {}).get(base, mode)
        prev = base
        for mv, ev in chain(ch, move_of(row), mode, seq):
            events[prev] = ev
            inp = f'{base}>{mv:X}'; pieces[inp] = (mv, mode, FOLLOW_NAMES.get(mv, f'{SPECIALS[name][base][2]} follow-up ${mv:X}'))
            prev = inp
    for base, bt in HIT_NEXT.get(name, {}).items():
        row, mode, _ = SPECIALS[name][base]
        mv = hit_next_move(ch, bt)
        events[base] = 'all'; pieces[f'{base}>{mv:X}'] = (mv, mode, FOLLOW_NAMES.get(mv, f'on hit ${mv:X}'))
    _FP[name] = (pieces, events)
    return _FP[name]

def move_of(row, cls=1): return M.transition(row, cls)

# ---- a move as frames (the model) -> program states --------------------------------------------------------------------
def move_rows(ch, move, mode=0):
    """model rows of a move from its first frame to the frame before neutral (anim 0 again: the descriptor's end)"""
    o = M.Obj(ch, mode, opp_dx=0); o.start_move(move)
    rows = []
    for _ in range(900):
        r = o.frame()
        if rows and r['anim'] == 0 and getattr(o, 'done', False): break
        rows.append(r)
    return rows, o.events

def segments(rows, events):
    """runs of frames with one motion (constant velocity + acceleration in x and in height) and no teleport inside:
    [(first, last)]"""
    warps = {e[0] for e in events if e[1] == 'warp'}
    x = [0.0] + [r['x'] for r in rows]; h = [0.0] + [r['h'] for r in rows]
    dx = [x[k + 1] - x[k] for k in range(len(rows))]; dh = [h[k + 1] - h[k] for k in range(len(rows))]
    segs, s = [], 0
    for k in range(1, len(rows)):
        n = k - s
        cut = k in warps
        if not cut and n >= 2:
            ax0, ah0 = dx[s + 1] - dx[s], dh[s + 1] - dh[s]
            cut = abs((dx[k] - dx[k - 1]) - ax0) > 1e-6 or abs((dh[k] - dh[k - 1]) - ah0) > 1e-6
        if cut: segs.append((s, k - 1)); s = k
    segs.append((s, len(rows) - 1))
    return segs, dx, dh

def openings(steps): return HS.openings(steps)

def standard_reacts(steps, base):
    sys.path.insert(0, os.path.join(HERE, '..', 'samsho2'))
    import export_ss2 as X
    X.standard_reacts(steps, base)

# ---- the effect objects a script spawns [code] ------------------------------------------------------------------------
# $AE / $9A -> task OBJ LNK ($2D8F6): one more FRAME (word 4 = a frame id of the spawner's table) drawn at the spawner's
# place + (x, y) while the spawner shows the step it was born on ($2D99E: its +$B8 / +$C6 unchanged, else it frees itself):
# the trails of Ittou Tsukikage. Word 2's high byte + the spawner's +$62: drawn in front (+) / behind (-). -> a bproj_t
# pinned for its step (follow 9, handlers98's step effects), one row looping.
# $AD / $99, $AF / $A3 -> task CO-ANIM ($2D4EA / $2DB24): an ANIMATION (word 4) of character byte 1 (his own table, or 24 =
# the common effects: the super flash) started at the spawner's place + (x, y), facing his way, playing on where it was
# born (its own script's motion, boxes: Shingetsu's crescent, Oboro's streaks) -> a placed effect (bproj_t air PJ_PLACED),
# its rows = model_lb2's play of that animation, its attack boxes live.
# $AA / $B2 (CO-ZLINK $2DDC6) / $A7 / $B0 (CO-SLINK $2DC8E): character 25's animation + $76434[stage] & 7: the stage's
# own dust: NOT imported (the brawler's stages are not LB2's).
# The 22-byte forms pick their (word 4, x, y) triple by style ($2CE60 / $2D036: Power +4, Speed +10, EX +16).
SPAWN_KIND = {0xAE: 'lnk', 0x9A: 'lnk', 0xAD: 'anim', 0x99: 'anim', 0xAF: 'anim', 0xA3: 'anim',
              0xAA: 'dust', 0xB2: 'dust', 0xA7: 'dust', 0xB0: 'dust', 0xA8: 'other', 0xB1: 'other', 0xA9: 'other', 0xB3: 'other'}

def spawn_info(op, b, mode=0):
    s16 = lambda k: M.s16(b[k] << 8 | b[k + 1])
    k = 4 + (6 * (0 if mode == 0 else 1) if len(b) == 22 else 0)
    return {'kind': SPAWN_KIND.get(op, 'other'), 'op': op, 'char': b[1] & 31, 'prio': M.s8(b[2]), 'word': (b[k] << 8 | b[k + 1]),
            'fwd': -s16(k + 2), 'up': -s16(k + 4)}

def effect_object(B, ch, info):
    import export_lb2 as X
    base = {'loop': None, 'end': [], 'kind': 3, 'hit_kind': 1, 'react': 'knockdown', 'spawn_row': 0, 'spawn_x': 0,
            'spawn_y': 0, 'child': None, 'sig': 0, 'next': None, 'stop': 0, 'rearm': 0,
            **({'back': True} if info['prio'] < 0 else {}), 'lb2': info}
    if info['kind'] == 'lnk':
        fid = info['word'] & 0xFFF
        return dict(base, rows=[[B.frame(fid), info['fwd'], info['up'], None, None, 0]], loop=0, follow=9, name=f'LNK{fid:X}')
    ce = info['char']; a = info['word'] & 0x1FF
    trows, _ = X.timeline(ce, a, limit=240)
    rows = []
    for r in trows:
        atk = [v for v in r['boxes'].values() if 0 < v[0] < 0xC0]
        box = X.kof_box(atk) if atk else None
        rows.append([B.frame(r['frame'], ce), round(info['fwd'] + r['x']), round(info['up'] + r['h']), [1] + box if box else None, box, 0])
    return dict(base, rows=rows, follow=0, placed=True, name=f'FX{ce}_{a:X}')

def step_of(steps, k):
    """the step (of collapse's list, before the clock adjustment) showing frame k of its state"""
    t = 0
    for i, s in enumerate(steps):
        t += s['ticks'] + 1
        if k < t: return i
    return len(steps) - 1

def program(B, ch, move, mode=0, name='', event=None):
    """-> (ops, states, anims_d, rows, segs, events, objects, step_fx) for a move; event: its follow-up point (a frame
    index: the step starting there gets the event flag $80 = PF_EVENT; 'all': every step), follow_pieces"""
    import export_lb2 as X
    rows, ev = move_rows(ch, move, mode)
    segs, dx, dh = segments(rows, ev)
    objects, okeys, step_fx = [], {}, []
    warps = {e[0]: e[2] for e in ev if e[1] == 'warp'}
    ops, states, anims_d = [], [], {}
    for i, (a, b) in enumerate(segs):
        n = b - a + 1
        spf = {e[0] - a for e in ev if e[1] == 'spawn' and a <= e[0] <= b and SPAWN_KIND.get(e[2]) in ('lnk', 'anim')}
        if isinstance(event, int) and a <= event <= b: spf = spf | {event - a}
        steps = X.collapse(B, rows[a:b + 1], spf)
        if event == 'all':
            for st in steps: st['flags'] |= 0x80
        elif isinstance(event, int) and a <= event <= b:
            steps[step_of(steps, event - a)]['flags'] |= 0x80
        for e in ev:                                  # its spawns: an object each (deduped), born as its step starts
            if e[1] != 'spawn' or not a <= e[0] <= b: continue
            info = spawn_info(e[2], e[3], mode)
            if info['kind'] not in ('lnk', 'anim'): continue
            key = (info['kind'], info['char'], info['word'], info['fwd'], info['up'], info['prio'])
            if key not in okeys: okeys[key] = len(objects); objects.append(effect_object(B, ch, info))
            step_fx.append((i, step_of(steps, e[0] - a), okeys[key]))
        steps[0]['ticks'] += 1                        # the brawler's clock: P_ANIM's frame advances once (handlers_ss2
        if steps[-1]['ticks']: steps[-1]['ticks'] -= 1   # rom_steps: the start frame shows the first step)
        k = f'{i}:{rows[a]["anim"]:x}.{a}'
        anims_d[k] = {'mode': 'hold', 'steps': steps, 'lb2': [rows[a]['anim'], a, b]}
        states.append(k)
        vx = dx[a]; ax = (dx[a + 1] - dx[a]) if n > 1 else 0.0
        vh = dh[a]; ah = (dh[a + 1] - dh[a]) if n > 1 else 0.0
        air = any(rows[j]['h'] > 0 for j in range(a, b + 1)) or (a and rows[a - 1]['h'] > 0)
        ops.append(('label', ('E', i)))
        if a in warps: ops.append(('warp', 0, WARP_B[warps[a]], 0))
        ops.append(('anim', i))
        ops += [('set', 'vx', round(vx * 65536)), ('set', 'cnt', n - 1)]
        if air: ops += [('set', 'vy', round(vh * 65536)), ('set', 'g', round(-ah * 65536))]
        ops.append(('resume',))
        # every frame of the state: v += a then the move (x); the height's P_FALL moves then accelerates, so its vy
        # starts at the first frame's displacement
        ops.append(('move',))
        if ax: ops.append(('add', 'vx', round(ax * 65536)))
        if air: ops.append(('fall',))
        ops += [('dec',), ('br', 'cnt', 1, ('S', i)), ('br', 'always', 1, 'yield'),
                ('label', ('S', i)), ('resume_at', ('E', i + 1)), ('br', 'always', 1, 'yield')]
    ops += [('label', ('E', len(segs))), ('label', 'END'), ('end',)]
    return ops, states, anims_d, rows, segs, ev, objects, sorted(set(step_fx))

def assemble(ops):
    lab, out = {}, []
    for o in ops:
        if o[0] == 'label': lab[o[1]] = len(out)
        else: out.append(o)
    res = []
    for o in out:
        if o[0] == 'br': res.append(('br', o[1], o[2], -1 if o[3] == 'yield' else lab[o[3]]))
        elif o[0] in ('jmp', 'resume_at'): res.append((o[0], lab[o[1]]))
        else: res.append(o)
    return res

def encode(o):
    n = o[0]
    if n == 'anim': return [P['anim'], o[1], 0, 0]
    if n in ('set', 'add'): return [P[n], REG[o[1]], 0, o[2]]
    if n == 'br': return [P['br'], PC[o[1]] | (0x80 if o[2] else 0), o[3], 0]
    if n in ('jmp', 'resume_at'): return [P[n], 0, o[1], 0]
    if n == 'fall': return [P['fall'], 1, 0, 0]
    if n == 'warp': return [P['warp'], o[1], o[2], o[3]]
    return [P[n], 0, 0, 0]

def special(B, ch, name, inp):
    pieces, events = follow_pieces(name)
    if inp in pieces: move, mode, sname = pieces[inp]; row = None
    else: row, mode, sname = SPECIALS[name][inp]; move = move_of(row)
    ops, states, anims_d, rows, segs, ev, objects, step_fx = program(B, ch, move, mode, inp, events.get(inp))
    prims = [encode(o) for o in assemble(ops)]
    nh = sum(sum(openings(anims_d[s]['steps'])) for s in states)
    each = max(1, SPECIAL_DAMAGE // max(1, nh))
    hitting = [j for j, s in enumerate(states) if any(openings(anims_d[s]['steps']))]
    for p in prims:
        if p[0] == P['anim']:
            j = p[1]; react = R_KNOCKDOWN if hitting and j == hitting[-1] else R_HEAVY
            p[2] = each | react << 8
    for j, s in enumerate(states):
        standard_reacts(anims_d[s]['steps'], R_KNOCKDOWN if hitting and j == hitting[-1] else R_HEAVY)
    # the brawler's player on it: length, apex, its rows (the Lab's script)
    anims_l = [{'steps': anims_d[s]['steps'], 'hold': True} for s in states]
    pl = HS.Play([tuple(p) for p in prims], anims_l)
    prow = []
    while len(prow) < 900:
        r = pl.frame()
        if r is None: break
        prow.append(r)
    script = [[anims_l[r[0]]['steps'][r[1]]['frame'], int(r[2]), int(r[3]), []] for r in prow] or [[0, 0, 0, []]]
    rb = [anims_l[r[0]]['steps'][r[1]]['boxes'] for r in prow] or [{}]
    rs = [[r[0], r[1], anims_l[r[0]]['steps'][r[1]]['flags'], 0xFF] for r in prow] or [[0, 0, 0, 0xFF]]
    opens = [i for i, r in enumerate(prow) if (i == 0 or prow[i - 1][:2] != r[:2]) and openings(anims_l[r[0]]['steps'])[r[1]]]
    apex = max(range(len(prow)), key=lambda i: prow[i][3]) if prow else 0
    snd = [[e[0], e[2]] for e in ev if e[1] == 'snd']
    fams = SPECIAL_SND.get(name, {}).get(inp)
    rom = {'states': states, 'anims': anims_d, 'prims': prims, 'objects': objects, 'step_fx': step_fx, 'openings': {}, 'hit_kind': 1,
           'last_hit': opens[-1] if opens else -1, 'apex': apex if prow and prow[apex][3] > 0 else -1,
           'length': len(prow), 'voice_frames': True, 'now': True,
           'vtable': {'rows': [], 'ncol': 0, 'nvar': 0, 'default': 0, 'vanim': len(states), 'vobj': 0, 'vdmg': 0,
                      'buttons': [], 'results': [row if row is not None else -1], 'hits': [nh]}}
    if fams: rom['step_snd'] = step_sounds(rom, fams)
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'name': sname, 'base_input': inp,
            'row_boxes': rb, 'row_steps': rs, 'marks': [''] * len(script), 'projectiles': [],
            'anims': sorted({r['anim'] for r in rows}), 'shape': [max(r[1] for r in script), max(r[2] for r in script), False],
            'game_hits': len(opens), 'rom': rom,
            'lb2': {'row': row, 'move': move, 'style': mode, 'descriptor': M.descriptor(ch, move), 'sounds': snd,
                    'segments': segs},
            'ss2': {'results': [row] if row is not None else [], 'sounds': [], 'code_sounds': [], 'code_voices': []}}

def specials(B, ch, name, lab=False, inputs=None):
    return [special(B, ch, name, inp) for inp in list(SPECIALS[name]) + list(follow_pieces(name)[0])]

# ---- the Character Lab's LAB special: every animation of the dictionary as its own program block (export96 /
# handlers_ss2.lab_special's twin): [P_LANIM j, P_RESUME, P_BR end yield, P_END]
def lab_special(B, ch, entries):
    import export_lb2 as X
    anims, states, ids, prims, bad = {}, [], [], [], []
    for x, a in entries:
        try:
            st = X.anim_steps(B, ch, a, lnk=False)   # (T4: the dictionary without trails, export_lb2.anim_steps)
            if not st: raise ValueError('no steps')
        except Exception as e:
            bad.append((x, str(e)[:60])); continue
        o = sum(openings(st))
        standard_reacts(st, R_KNOCKDOWN if o else R_HEAVY)
        k = f'L{len(states)}:{a}'; anims[k] = {'mode': 'hold', 'steps': st, 'lb2': a}
        prims += [[P['lanim'], max(1, SPECIAL_DAMAGE // o) if o else 0, R_KNOCKDOWN if o else R_HEAVY, len(states) << 8],
                  [P['resume'], 0, 0, 0], [P['br'], PC['end'], -1, 0], [P['end'], 0, 0, 0]]
        states.append(k); ids.append(int(x, 16))
    s0 = anims[states[0]]['steps']
    rom = {'states': states, 'anims': anims, 'prims': prims, 'objects': [], 'openings': {}, 'hit_kind': 1, 'last_hit': -1,
           'apex': -1, 'length': 0, 'vtable': {}, 'lab': True, 'lab_ids': ids, 'now': True}
    return {'input': 'LAB', 'condition': 'normal', 'version': 'whiff', 'script': [[s0[0]['frame'], 0, 0, []]], 'row_boxes': [{}],
            'row_steps': [[0, 0, 0, 0xFF]], 'marks': [''], 'projectiles': [], 'anims': [ids[0]], 'shape': [0, 0, False],
            'game_hits': 0, 'rom': rom, 'ss2': {'results': [], 'sounds': [], 'code_sounds': [], 'code_voices': []}}, bad

# ---- win poses [meas]: the round's KO -> about 316 frames later the winner's move $65 (anim $65: Moriya sheathes, the
# sword's flash; measured from vs.state, P2 KO'd by a stand B). The descriptor table's next ones ($66 [8016 0066], $67-$6E)
# are other poses not reached by a plain KO in our captures: not taken
WINS = {'moriya': [0x65]}
def win_anims(B, ch, name):
    import export_lb2 as X
    out = {}
    for k, a in enumerate(WINS.get(name, [])):
        out['win' if k == 0 else f'win_{k + 1}'] = {'slot': a, 'mode': 'hold', 'steps': X.anim_steps(B, ch, a)}
    return out

# ---- throws [code]+[meas] -----------------------------------------------------------------------------------------------
# C+D (or forward / back + C+D) from standing = move $3F [D800 003F]: control word op $2C ($30184) runs throw test 0
# ($76A24[0] = $30670): the opponent within word $76AE4[char] px (40 for everyone, $30436: on the ground, not already
# thrown, its body box $C0 / $C4 near) -> the thrower's move $3E (anim $3E) and the VICTIM's move $76AA4[thrower's char]
# (Moriya: $145) in the victim's OWN table (every character has a "thrown by X" move for each thrower), the victim
# turned to face the thrower ($3021A eori #1 +$41) at the thrower's place. Its descriptor [$145 $11D $16 0]: the thrown
# animation (drawing offsets $83 while held, then the $84 flight $8000: 8 px a frame, 8.81 px up, gravity 0.53, to the
# landing: the damage, measured life 256 -> 228 at the landing frame), lying ($11D), getting up ($16). SNK's name:
# Samidare (close back / forward + C+D, snk.fandom.com "Moriya Minakata/Move List").
THROW = {'moriya': {'move': 0x3E, 'victim': 0x145, 'name': 'Samidare', 'range': 40}}

def throw(B, ch, name):
    import export_lb2 as X
    t = THROW[name]
    trows, _ = move_rows(ch, t['move'])
    steps = X.collapse(B, trows)
    timeline = [[B.frame(r['frame']), 0, 0, r['turned']] for r in trows]
    vrows, _ = move_rows(ch, t['victim'])
    rows, rel, land = [], None, None
    for i, r in enumerate(vrows):
        if r['anim'] == t['victim']:
            # the victim faces the thrower: its forward = the thrower's backward; its drawing offset is the art's
            dx = round(r['disp'][0] - r['x']); dy = round(-r['disp'][1] + r['h'])
            if rel is None and r['h'] > 0: rel = i
            if rel is not None and land is None and r['h'] <= 0 and i > rel: land = i
            rows.append([B.frame(r['frame']), dx, dy, r['turned'], 0, f"{t['victim']}.{r['step']}", None])
        else:                                         # lying ($11D), then the get-up ($16): the brawler's own postures
            rows.append([-1, round(-r['x']), 0, r['turned'], 0, f"{r['anim']}.{r['step']}", 'down' if r['anim'] == 0x11D else 'getup'])
    return {'slot': t['move'], 'inputs': f"close + forward / back + C+D ({t['name']})", 'table': [], 'hold': False,
            'rom': True, 'timeline': timeline, 'victims': {name: rows}, 'impacts': [land] if land is not None else [],
            'release': rel, 'land': land, 'ret': len(timeline),
            'anim': {'slot': t['move'], 'mode': 'hold', 'steps': steps},
            'lb2': {'move': t['move'], 'victim_move': t['victim'], 'range': t['range']}, 'turned': False, 'grab_frame': None,
            'name': t['name']}

def throws(B, ch, name):
    """throw_c / throw_d (the brawler's forward / back + A in the hold): Moriya has one throw (Samidare, both
    directions in LB2), both slots play it (Genjuro SS2's rule)"""
    if name not in THROW: return {}
    th = throw(B, ch, name)
    return {'throw_c': th, 'throw_d': json.loads(json.dumps(th))}

# ---- check: the programs against the model, frame by frame ------------------------------------------------------------
def check(name='moriya'):
    import export_lb2 as X
    ch = X.CAST[name]; B = X.Builder(ch); res = {}
    pieces = follow_pieces(name)[0]
    for inp in list(SPECIALS[name]) + list(pieces):
        sp = special(B, ch, name, inp)
        mv, mode = (pieces[inp][0], pieces[inp][1]) if inp in pieces else (move_of(SPECIALS[name][inp][0]), SPECIALS[name][inp][1])
        rows, ev = move_rows(ch, mv, mode)
        warps = sorted(e[0] for e in ev if e[1] == 'warp')
        sc = sp['script']; n = min(len(sc), len(rows)); eq = 0; bad = None
        for k in range(n):
            fid = B.frames[sc[k][0]]['lb2']['frame']
            ok = fid == rows[k]['frame'] and (warps or abs(sc[k][1] - int(rows[k]['x'])) <= 1) and abs(sc[k][2] - int(rows[k]['h'])) <= 1
            eq += ok
            if not ok and bad is None: bad = (k, fid, sc[k][1], sc[k][2], rows[k]['frame'], round(rows[k]['x'], 1), round(rows[k]['h'], 1))
        res[inp] = dict(model=len(rows), program=len(sc), equal=eq, first_bad=bad, states=len(sp['rom']['states']))
        print(inp, res[inp])
    return res

if __name__ == '__main__':
    if sys.argv[1:2] == ['commands']:
        for c in commands(int(sys.argv[2]) if len(sys.argv) > 2 else 1): print(c, hex(move_of(c[3])))
    else: check()
