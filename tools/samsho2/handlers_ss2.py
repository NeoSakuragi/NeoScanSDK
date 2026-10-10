#!/usr/bin/env python3
"""Samurai Shodown II's special moves and throws read from the ROM: each command result's action handlers (the
descriptor list of $28310: per entry an animation and a 68000 routine, stepped by +$F9) decoded into the brawler's
program ops (bprim_t, fighter.c prog_update), one parameter row per button (vocabulary variant.table: A / B / A+B), and
the throws into paired scripts (vocabulary hold.paired_script). No capture is played: captures (moves/CC.json) only
check the programs (`python3 handlers_ss2.py check`: the brawler's prog_update ported below, against the game's
frames). Labels: [code] read in the disassembly (/data/tmp/samsho2/p1.dis), [meas] measured in our emulator.

The engine [code]:
  frame order  the player's action routine ($27620): the entry +$F9 of the action's list sets the animation (+$66; a
               word with bit 15 = a parameter +$DE, the animation stays), then calls the entry's routine; then the
               dispatcher's gravity: +$EE = 1 -> vy += the table's gravity ($46BAE $3205: entry 5 = 131 / 256 px),
               +$EE < 0 -> the routine applies its own (+$D0 / +$D2: $2B988 / $2B774); landing ($27802: vy >= 0 and
               y >= 224 -> y 224, vx = vy = 0, +$EE = 0); then x += vx, y += vy (8.8 with the fraction in +$55 /
               +$59, $A572 / $A586); then the animation clock ($3470: a step shows ticks + 1 frames; a new animation
               starts at its first step in the frame it is set; on the last frame of the last step the $00 command
               holds it and sets +$FA, the end flag). A step's $20 command is a drawing offset while it shows (+$60,
               cleared every frame); a routine calling $2B7D0 moves the body by it.
  routines     a routine runs every frame until it advances +$F9 (the next entry: next frame's animation and routine).
               The shared ones: $2B7F6 the animation ended -> next entry; $2B802 ended -> back to neutral (+$E6 = 0);
               $2B81E velocities 0; $2B92A vy >= 0 (the apex) -> next; $2B85A landed -> next; $2B958 the attack
               connected (+$115 bit 7, cleared: bclr); $46BAE (word): vx / vy from the fighter's table long $6A500
               [+$64] (entry = low byte + 16, bit 13: + 8 in another mode), bit 12 clear: +$EE = 1 (gravity), bit 11:
               next entry, bit 10: neutral, bit 9: values only; $46C2E: vx / vy from an address, +$EE = 1; $46C4A:
               vx and its deceleration +$D0; $46C64: vx += +$D0 until it crosses 0; $31306: spawn an object of type d0
               (table $313A8: per type a routine; the object starts at its thrower's place, +$F0 = the variant).
  cancels      a command of type 5 ($319A6) is taken during a move when the move connected (+$103, kept from action to
               action within class 1) and the shown step has +$74 bit 3 (its flags word's $0800: the cancel window), unless the
               allow table $6CA32 forbids that pair: Genjuro's slash chain.
  -> brawler   an entry = P_ANIM (its animation, when it has one) + its once-only writes + P_RESUME, then the frame
               loop: its conditions (P_BR), the physics (P_ADD vy: the gravity before the move, as SS2; P_MOVE;
               P_FALL with no gravity of its own; landing: velocities 0), the frame's end. A condition met: that
               frame's physics, then the next entry from the next frame (P_RESUMEAT). The animation's first step gets
               one more tick when the animation has more (the brawler's clock counts the start frame, SS2's shows it).
Every special's per-entry decode, with the routine addresses, is in the functions below."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss2, neo2 as N

P = {'anim': 1, 'set': 2, 'mul': 3, 'move': 4, 'fricmove': 5, 'fall': 6, 'nudge': 7, 'dec': 8, 'br': 9, 'resume': 10,
     'resume_at': 11, 'jmp': 12, 'spawn': 13, 'fxoff': 14, 'end': 15, 'adv': 16, 'check': 17, 'part': 18, 'evclr': 19,
     'onhit': 20, 'put': 21, 'hitclr': 22, 'hold': 23, 'unhold': 24, 'sigclr': 25, 'hitoff': 26, 'add': 27, 'form': 28,
     'voice': 29, 'vsig': 30, 'lanim': 36, 'warp': 37}        # bm_chars.h P_*
REG = {'vx': 0, 'vy': 1, 'g': 2, 'fric': 3, 'cnt': 4, 'h': 5}
PC = {'end': 0, 'event': 1, 'land': 2, 'fall': 3, 'cnt': 4, 'hit': 5, 'off': 6, 'always': 7, 'stepev': 8, 'window': 9,
      'link': 10, 'hitany': 11, 'sig7c': 13, 'passed': 20, 'caught': 21}
R_HEAVY, R_KNOCKDOWN, R_LAUNCH = 1, 2, 3
SPECIAL_DAMAGE = 8                                # export_bm.SPECIAL_DAMAGE
GRAVITY = 131                                     # 8.8 px / frame^2: the table entry 5 ($46BAE $3205) [code]

def vtab(ch, i):
    """the fighter's velocity table entry i ($46BAE: [vx][vy] 8.8, vx forward, vy down)"""
    base = N.u32(0x6A500 + 4 * ch)
    return N.s16(base + 4 * i), N.s16(base + 4 * i + 2)

def vword(ch, w):
    """$46BAE's word w -> (vx, vy) in 8.8 (entry = low byte + 16: bit 13 clear)"""
    assert not w & 0x2000
    return vtab(ch, (w & 0xFF) + 16)

def bx(v): return v << 8                          # 8.8 forward -> 16.16 forward
def by(v): return -(v << 8)                       # 8.8 down -> 16.16 up

# ---- the decoded specials -------------------------------------------------------------------------------------------
# An entry: anim (SS2 animation, None = a parameter entry: the animation goes on), init (ops of its first frame),
# conds [(condition, target)] in the routine's order: 'end' (+$FA), ('step', k) (a step flagged 0x80: the shown step
# +$7C tested), 'land' (+$EE 0), 'apex' (vy >= 0), 'hit' ($2B958), 'cnt' (the routine's counter: decremented, < 0),
# 'now' (the routine advances at once), ('link', mask) (a type-5 cancel: connected + a window step + the link's press);
# targets: an entry index, 'next', 'end' (neutral), 'now:N' (entry N in the same frame: the routine sets +$66 itself);
# phys: 'ground' (x += vx), 'grav' (+$EE 1), 'air' (+$EE < 0, nothing added), ('custom', ax, ay) (+$EE < 0, the
# routine adds +$D0 / +$D2), ('decel', dv) (the routine's $46C64 on vx); init: ('set', reg, v), ('spawn', k),
# ('nudge', px), ('part',).
def E(anim=None, init=(), conds=(), phys='ground', flags=None, part=None, react=None, catch=None, grab=None, voice=()):
    """catch: the entry index of the catch routine: this entry's attack steps are catch boxes (no damage, the victim
    held: fighter.c's catch, KOF +$19C), the routine starts after the hit-stop and the victim follows the move's victim
    lists (VL below). grab: a catch box of its own on every step of the entry's animation (KOF box [cx, cy, hw, hh]):
    a command grab SS2 tests by distance, not by a box (Hanzo's Mozu Otoshi, GRAB_BOX). anim: an SS2 animation, or
    (animation, first step, last step): those steps alone (a pose held). voice: sound ids the routine itself sends
    ($5FB0) in the frame this entry's animation starts, sent as its first step is entered (a state the whiff never
    reaches: special's step voices)"""
    return {'anim': anim, 'init': list(init), 'conds': list(conds), 'phys': phys, 'flags': flags or {}, 'part': part,
            'react': react, 'catch': catch, 'grab': grab, 'voice': list(voice)}

def hao_236s(v):
    """Senpuu Retsu Zan, 2 3 6 + A / B / A+B -> results 41-43, descriptors $35470 / $3547C / $35488 [code]:
    entry 0 anim 14 / 15 / 18, routine $35494: velocities 0, at step 6 (+$7C == 6) spawn object type 2 (the tornado,
    +$F0 = the button) and next; entry 1 $354C2: the animation's end -> neutral"""
    a = (14, 15, 18)[v]
    return [E(a, [('set', 'vx', 0)], [(('step', 6), 'next', [('spawn', 0)])], flags={6: 0x80}),
            E(None, conds=[('end', 'end')])], [('tornado', v)]

def hao_623s(v):
    """Kogetsu Zan, 6 2 3 + A / B / A+B -> results 38-40 ($352EE / $35318 / $35342) [code]:
    0 anim 249 / 256 / 257 $3536C: +$D4 = button; $46BAE($1009 + b) = entry 25 + b: vx (bit 12: no gravity), spawn
      object type 1 (the crescent, its +$F0 = b; A+B: also the flash object 61); next
    1 $353C0 (param): the end -> next
    2 anim 260 / 261 / 264 $353C8: $46BAE($080C + b): the jump (entry 28 + b), gravity on, next (bit 11)
    3 $353E2 (param): the apex (vy >= 0) -> next (and a hit of its crescent: object 62, the hit flash)
    4 anim 265 $35414: $46BAE($080F + 2b) entry 31 + 2b: vx / vy; the next entry's pair: +$D0 / +$D2 (its own
      acceleration), +$EE = $80
    5 $35448 (param): until landed, vx += +$D0, vy += +$D2 ($2B988, $2B774) -> next
    6 anim 3 (landing) $35462: the end -> neutral
    The crescent ($30056, type 1) follows him while his animation is the one it was born on ($30092: owner +$66
    unchanged), then is launched where it is ($300B6: $46BAE($1215 + b): 1 / 16 - 3 / 16 px a frame) and ends with its
    animation (27 frames). The brawler pins it to him for its whole life (the acceptance of TODO #148: the effect
    stays with him; SS2 leaves it drifting where he took off)."""
    a0, a1 = (249, 256, 257)[v], (260, 261, 264)[v]
    vx0 = vword(0, 0x1009 + v)[0]; jx, jy = vword(0, 0x80C + v)
    fx, fy = vword(0, 0x80F + 2 * v); ax, ay = vtab(0, 0x0F + 16 + 2 * v + 1)
    return [E(a0, [('set', 'vx', bx(vx0)), ('set', 'vy', 0), ('spawn', 0)], [('now', 'next')]),
            E(None, conds=[('end', 'next')]),
            E(a1, [('set', 'vx', bx(jx)), ('set', 'vy', by(jy))], [('now', 'next')], phys='grav'),
            E(None, conds=[('apex', 'next')], phys='grav'),
            E(265, [('set', 'vx', bx(fx)), ('set', 'vy', by(fy))], [('now', 'next')], phys='air'),
            E(None, conds=[('land', 'next')], phys=('custom', ax, ay)),
            E(3, conds=[('end', 'end')])], [('crescent', v)]

def hao_623k(v):
    """6 2 3 + C / D / C+D -> results 48-50 ($3557E / $355A2 / $355C6) [code]: the leaping kick
    0 anim 295 $355EA: velocities 0, the end -> next     1 anim 308 $355F8: $46BAE($081B + b) entry 43 + b: the leap
    2 $3560E (param): the end -> next                    3 anim 309 / 312 / 313 $35616: the end -> next
    4 anim 316 / 317 / 318 $3561E: landed -> next        5 anim 319 / 320 / 321 $35630: the end -> crouch (class 0
    action 4: neutral here)"""
    jx, jy = vword(0, 0x81B + v)
    return [E(295, [('set', 'vx', 0)], [('end', 'next')]),
            E(308, [('set', 'vx', bx(jx)), ('set', 'vy', by(jy))], [('now', 'next')], phys='grav'),
            E(None, conds=[('end', 'next')], phys='grav'),
            E((309, 312, 313)[v], conds=[('end', 'next')], phys='grav'),
            E((316, 317, 318)[v], conds=[('land', 'next')], phys='grav'),
            E((319, 320, 321)[v], conds=[('end', 'end')])], []

def hao_236k(v):
    """2 3 6 + C / D / C+D -> results 44-46 ($35536, one descriptor for the three) [code]: anim 293 $3553C:
    velocities 0, the end -> neutral (the same move for every button)"""
    return [E(293, [('set', 'vx', 0)], [('end', 'end')])], []

def hao_214a(v):
    """Sake Kougeki, 2 1 4 + A -> result 47 ($35550) [code]: anim 328, routine $3555C: at step 6 +$118 = -1,
    velocities 0 ($2B81E), the end -> neutral ($2B802). The list's second entry (anim 329, the same routine) is the
    other weapon mode's (descriptor lists hold both: jump_moves), never reached from the first: SS2 is neutral the
    frame after 328 ends (moves/00.json result 47: class 1 for 52 frames = 328's length; TODO #191 found the brawler
    playing 329 after it, 99 frames)"""
    return [E(328, [('set', 'vx', 0)], [('end', 'end')])], []

# SS2's big hit (TODO #188 c): Haohmaru's WFT routine on a connect ($354E8 $2B958 -> $354FA) calls $2B9DE with
# $6A672 = (31, 0, 0, 48): the backdrop ($108A86 -> $401FFE every frame, $172C) red for 48 frames ($8AE2), and its hit
# (the hit routine's big-hit branch $26CB0: +$FB = 32 to both, the slow-motion counter $8AC8 = 30) holds both 40
# frames, then the whole game runs at half speed for 30 [meas: our emulator, /data/tmp/b188/out/c_ss2_*: his step
# held frames 63-103, then a step every 4 frames to 133; the victim in its hit pose 414 until 139, then thrown]
BIGHIT = {('haohmaru', 'WFT'), ('hanzo', 'WFT')}
# the big hit's backdrop ($2B9DE: r, g, b 0-31 through $2BA16; export_bm: bspec_t.bd_col[0], fighter.c big_hit): Haohmaru
# $6A672 (31, 0, 0) = $4F00 (fighter.h BIGHIT_COL), Hanzo's flame $6A9EA (0, 0, 4) = $0002
BIGHIT_COL = {('hanzo', 'WFT'): 0x0002}

def hao_wft(v):
    """Tenha Seiou Zan (the weapon-flipping technique), 6 3 2 1 4 6 + A in rage -> result 37 ($354D0) [code]:
    anim 333 $354DC: velocities 0, the end -> neutral; a connect ($2B958) flashes the screen ($2B9DE, colours
    $6A672) and sets the opponent's weapon loss (+$B8: not modelled); entry 1 $3551A: the end -> neutral"""
    return [E(333, [('set', 'vx', 0)], [('end', 'end')])], []

def gen_214s(v):
    """the card wave, 2 1 4 + A / B / A+B -> results 38-40 ($56328 / $5633A / $5634C) [code]:
    0 anim 290 / 291 / 292 $5635E: velocities 0, the shout object 78 (+$D4 = $2E8); next
    1 $5637A (param): from step 9 (+$7C >= 9): spawn object type 10 (the card wave, +$F0 = b), next
    2 $5639E: the end -> neutral"""
    a = (290, 291, 292)[v]
    return [E(a, [('set', 'vx', 0)], [('now', 'next')], flags={k: 0x80 for k in range(9, 64)}),
            E(None, conds=[(('step', 9), 'next', [('spawn', 0)])]),
            E(None, conds=[('end', 'end')])], [('cards', v)]

def gen_623s(v):
    """6 2 3 + A / B / A+B -> results 50-52 ($56724 / $56748 / $5676C) [code]: the rising slash
    0 anim 316 / 317 / 318 $56790: the shout object 78 ($2E7)   1 $567A6: the end -> next
    2 anim 319 $567AC: the body moved by the last step's offset ($2B7D0: 9 / 21 / 64 px: a move at that vx), the jump from the table $6B57E + 4 b
      ($46C2E, +$EE 1), next   3 $567A6: the end -> next   4 anim 261 $567D6: landed -> velocities 0, next
    5 anim 3 $567F0: the end -> neutral"""
    a = (316, 317, 318)[v]
    jx, jy = N.s16(0x6B57E + 4 * v), N.s16(0x6B57E + 4 * v + 2)
    last = ss2.parse_anim(12, a)[-1]
    mv = next((c[1] for c in last['cmds'] if c[0] == 'move'), 0)
    return [E(a, [('set', 'vx', 0)], [('now', 'next')]),
            E(None, conds=[('end', 'next')]),
            E(319, [('set', 'vx', mv << 16), ('move_now',), ('set', 'vx', bx(jx)), ('set', 'vy', by(jy))], [('now', 'next')], phys='grav'),
            E(None, conds=[('end', 'next')], phys='grav'),
            E(261, conds=[('land', 'next')], phys='grav'),
            E(3, conds=[('end', 'end')])], []

def decel_frames(v0, dv):
    """frames $46C64 adds dv to v0 before it zeroes it (|vx| < |dv| after the add -> 0)"""
    n, v = 0, v0
    while v:
        v += dv; n += 1
        if abs(v) < abs(dv): v = 0
    return n - 1

def gen_236s(v):
    """the three-part slash, 2 3 6 + A / B / A+B -> results 41-43 ($563AA), then 2 1 4 / 2 3 6 + a button inside it:
    the type-5 cancel entries (results 44-46 from 41-43, 47-49 from 44-46: the allow table $6CA32) [code]:
    part 1: 0 anim 343 $563C2: +$D4 = b, vx = word $6B536[b] (8 px a frame), +$D6 = the count; next ($2B81A)
            1 $563F4 (param): the opponent reached / passed (its x - his, his facing's way, >= 0), else the count runs out
              -> vx + deceleration from $6B54E[b]
              ($46C4A), next
            2 anim 363 $56448: a connect -> the sparks (objects 23), the shout $200; the deceleration ($46C64) every
              frame; the end -> neutral; its steps 1-4 are the cancel window (+$74 bit 3: the flags word's $0800)
    part 2: the same from $564FA ($6B542[b]: 8 / 10 / 11 px a frame), anim 366 $5657C (window steps 1-5)
    part 3: anim 369 $5662E: velocities 0, $56664: the end -> neutral
    No push between the players while it plays (descriptor byte 4 = $80 -> +$FF bit 7: $CC14 skipped): he slides
    through his opponent (the brawler: SF_NOPUSH).
    The brawler: one special of three parts, the follow-up = C again (the cancel's press) inside a window step after a
    connect; the button row latched at the start serves the three parts."""
    out = []
    for k, (tab, a) in enumerate(((0x6B536, 363), (0x6B542, 366))):
        vx, cnt = N.s16(tab + 4 * v), N.s16(tab + 4 * v + 2)
        dvx, dd = N.s16(0x6B54E + 4 * v), N.s16(0x6B54E + 4 * v + 2)
        base = len(out)
        out += [E(343, ([('part',)] if k else []) + [('set', 'vx', bx(vx)), ('set', 'cnt', cnt)], [('now', base + 1)], part=k),
                E(None, conds=[('passed', base + 2), ('cnt', base + 2)], part=k),
                E(a, [('set', 'vx', bx(dvx)), ('set', 'cnt', decel_frames(dvx, dd))],
                  [(('link', 1), 'part%d' % (k + 1)), ('end', 'end')], phys=('decel', bx(dd)), part=k,
                  flags={i: 0x2000 for i, s in enumerate(ss2.parse_anim(12, a)) if s['flags'] & 0x0800})]
    out += [E(369, [('part',), ('set', 'vx', 0)], [('end', 'end')], part=2)]
    return out, []

def VL(entries, fly=None, rel=None):
    """a caught victim's list (vocabulary hold.victim_list; fighter.c vlist_apply): entries [(dx, dy, posture key
    'anim.step' of victim_poses_ss2.json, flags)] one per attacker step (the last for later steps), placed at the
    attacker + (dx forward, dy up) every frame; fly = (vx, vy, g) 8.8 SS2 words (vx forward of the attacker, vy DOWN,
    g the reaction gravity): placed at its first entry once, then it flies on its own velocities (posture held); rel =
    (vx, vy) the release's velocity (8.8, vy DOWN) for an entry flagged 64 (instead of KOF's blowback)"""
    out = {'e': [dict(dx=e[0], dy=e[1], state=e[2], flags=e[3], turn=bool(e[4]) if len(e) > 4 else False) for e in entries]}
    for e in out['e']:                                # (turn: it faces the attacker's way, VE_TURN: Hanzo's grab)
        if not e['turn']: del e['turn']
    if fly: out['fly'] = list(fly)
    if rel: out['rel'] = list(rel)
    return out

def voff(a, k):
    """the drawing offset (its $20 command: dx forward, dy up) of step k of the victim's animation a: the victim stands
    at its place and is DRAWN there + the offset (SS2's art); a routine's $2B7D0 then moves the body by the last one.
    The brawler's victims are not SS2 characters: Haohmaru's animations (table 0; every character has these victim
    animations) are the reference [code]"""
    mv = next((c for c in ss2.parse_anim(0, a, 400)[k]['cmds'] if c[0] == 'move'), ('move', 0, 0))
    return mv[1], -mv[2]

REACT_G = N.s16(N.u32(0x6A500) + 4 * 5)          # $277F2 / $2792C: a reaction (class 3) falls with word 0 of the
                                                # gravity entry 5 (93 / 256 px), the others with word 1 (131) [code]

WFT_FIT = 0.33                                    # Genjuro's WFT heights in the brawler (gen_wft)

def gen_wft(v):
    """the rage move, 6 3 2 1 4 6 + A in rage -> result 37 ($5613C) [code]:
    0 anim 12 $5616C: velocities 0; from step [$6B4F6] (8) on without a connect: the afterimages (5 objects 26),
      next (1: $561F2 the end -> neutral); a connect before ($2B958): the opponent caught (+$D4 = 0: its stage, object
      27 the vortex on it), animation 13 at once and entry 4 (an opponent with +$FD (guarding) gets entry 2: anim 71,
      no catch: the brawler has no guard)
    4 anim 13 $56218: its end -> the leap ($46C2E: vx / vy from $6B4E2, gravity), the count 16, next
    5 anim 14 $56238: the count runs out -> velocities 0, +$EE = $80 (he hangs: no gravity), the opponent's stage 1
    6 anim 24 $56262: the spin (its slashes: 5 attack steps); its end -> the fall ($6B4E6, gravity), voice $206 ($1ACE,
      the last word of his line: move.w #$206 + jsr $5FB0 at $562A8; measured in our emulator: $1A $CE sent in the
      frames the fall's anim 261 starts, after the five step voices $200-$204), the opponent's stage 2 (released,
      disarmed: +$B8)
    7 anim 261 $562D4 ($2B85A): landed -> the landing action (class 0 action 18), neutral here.
    The victim (its class 3 action 36, $28310 -> $56ABA, the same for every character) [code]:
    0 anim 464 $56ABA: velocities 0, at its catcher's place ($2B7A2) + 80 px forward, 16 up, facing its way, its own
      hit-stop +$FB = 12, the flight $6B4EA (vx -0.5: back toward him, vy 12 up) with the reaction gravity (93 / 256)
    1 $56B04: flies until his stage 1 -> velocities 0, next   2 anim 498 $56B34: no gravity, at his place ($2B7A2)
    3 $56B4A: at his place every frame until his stage 2 -> the flight $6B4EE (vx +1, vy 8 down), disarmed ($297D8)
    4 anim 464: lands ($2B83A) -> the bounce $6B4F2, anim 466, then 468 and lying (the brawler's own landing).
    The brawler: anim 12's attack steps catch (no damage), the victim lists = the victim's entries 0-1 (fly), 2-3 (at
    him) and 4 (the release), his stages = P_VSIG."""
    lim = N.u16(0x6B4F6)
    jx, jy = N.s16(0x6B4E2), N.s16(0x6B4E4); fx, fy = N.s16(0x6B4E6), N.s16(0x6B4E8)
    # the carry height (TODO #185): SS2's camera follows the spin up (126 px, the victim 175 - 220); the brawler's camera
    # never moves vertically, so every vertical velocity and gravity of the move is scaled by WFT_FIT: the same timing
    # (the count 16, the stages), every height x WFT_FIT (the spin at 42 px, its victim on screen under the HUD)
    q = lambda v: round(v * WFT_FIT); g = ('custom', 0, q(GRAVITY))
    ents = [E(12, [('set', 'vx', 0)], [(('step', lim), 1)], flags={k: 0x80 for k in range(lim, 64)}, catch=2),
            E(None, conds=[('end', 'end')]),
            E(13, [('set', 'vx', 0), ('spawn', 0)], [('end', 3)]),
            E(14, [('set', 'vx', bx(jx)), ('set', 'vy', by(q(jy))), ('set', 'cnt', 16)], [('cnt', 4)], phys=g),
            E(None, [('set', 'vx', 0), ('set', 'vy', 0), ('vsig',)], [('now', 5)], phys='air'),
            E(24, [('fxoff',), ('spawn', 1)], conds=[('end', 6)], phys='air'),
            E(None, [('set', 'vx', bx(fx)), ('set', 'vy', by(q(fy))), ('vsig',)], [('now', 7)], phys=g),
            E(261, conds=[('land', 'end')], phys=g, voice=[0x206])]   # $206: entry 6's send, the frame 261 starts
    vl = [VL([(80, 16, '464.0', 0)], fly=(N.s16(0x6B4EA), q(N.s16(0x6B4EC)), q(REACT_G))),   # $56AE2: + 80, - 16
          VL([voff(498, 0) + ('498.0', 0)]),                       # at him, drawn at 498's offset
          VL([voff(498, 1) + ('464.0', 64)], rel=(N.s16(0x6B4EE), N.s16(0x6B4F0)))]   # moved by it ($2B7D0), the flight
    return ents, [('wind', 0), ('wind2', 0)], vl


# ---- Kuroko (table 17, the referee: the hidden character; his specials are the other fighters' moves done with his
# flags, the "parodies") [code] -------------------------------------------------------------------------------------
# results 39-46 share one descriptor ($593A6): anim 29 (the flag throw), routine $593B2: velocities 0, from step 7 the
# result's own object(s) through the table $593E2 (one routine per result), and its sound; $593DC: the end -> neutral.
# The objects: type 25 ($4C12A, +$D4 = which: its animation / end animation / place from the table $4C182, its vx from
# $6BB0E) and type 24 ($4C07C: animation 46 at 72 px, 56 up, then 49 flying at $6BB20).
KUR_PARODY = {39: ([4], 175), 40: ([0, 1], 173), 41: ([5], 174), 42: ([6], 172), 43: ([7], 175), 44: (['crescent'], 174),
              45: ([2, 3], 222), 46: ([8], 174)}     # result -> the type 25 objects' +$D4 (or type 24), the sound id

def kur_parody(result):
    def fn(v):
        objs, snd = KUR_PARODY[result]
        os_ = [('kcrescent', 0) if o == 'crescent' else ('kparody', o) for o in objs]
        return [E(29, [('set', 'vx', 0)], [(('step', 7), 'next', [('spawn', k) for k in range(len(os_))] + [('snd', snd)])], flags={7: 0x80}),
                E(None, conds=[('end', 'end')])], os_
    fn.__doc__ = f"Kuroko's result {result} ($593B2 + $593E2[{result - 39}]): anim 29, objects {KUR_PARODY[result][0]}, sound ${KUR_PARODY[result][1]:02X}"
    return fn

def kur_flag(anim):
    def fn(v):
        """Kuroko 6 + A+B+C / B+C+D -> results 48 / 49 ($59546 / $5954C): anim 3 / 5 (the flag sweep with its arc),
        routine $59552: velocities 0, the end -> neutral"""
        return [E(anim, [('set', 'vx', 0)], [('end', 'end')])], []
    return fn

def kur_ccccc(v):
    """Kuroko C C C C C -> result 47 ($594E4) [code]: 0 anim 25 $59502: velocities 0, the shout object 78 ($2FB), next;
    1 $59518: the end -> next; 2 anim 67 $5951E: spawn object type 26 (the ghost: anim 73 pinned to him while this
    action lasts, $4C248; its attack steps hit), the count $6BB22 (49), next; 3 $59532: the count -> next;
    4 anim 79 $59540: the end -> neutral"""
    return [E(25, [('set', 'vx', 0)], [('now', 'next')]),
            E(None, conds=[('end', 'next')]),
            E(67, [('spawn', 0), ('set', 'cnt', N.s16(0x6BB22))], [('now', 'next')]),
            E(None, conds=[('cnt', 'next')]),
            E(79, conds=[('end', 'end')])], [('kghost', 0)]

def kur_boomerang(v):
    """Kuroko's flag boomerang, 6 3 2 1 4 + A -> result 50 ($5955E) [code]: 0 anim 15 $59576: velocities 0, the end ->
    next; 1 anim 17 $59582: spawn object type 27 (the flag: kboomerang), sound $E8, his +$D4 = 0, next at once;
    2 $595A2 (param): his +$D4 set (the flag's catch, $4C3F4) -> next; 3 anim 24 $595B0: the end -> neutral. Measured
    (boomerang_ss2.py, whiff): anim 17 and the flag from frame 43, the catch at 89, anim 24 from 91, neutral at 118"""
    return [E(15, [('set', 'vx', 0)], [('end', 'next')]),
            E(17, [('spawn', 0)], [('now', 'next')]),
            E(None, conds=[('sig', 'next')]),
            E(24, conds=[('end', 'end')])], [('kboomerang', 0)]

def kur_rage(maxv):
    def fn(v):
        """Kuroko's rage moves: 6 3 2 1 4 6 + A+B -> 37 ($591E0), 6 4 1 2 3 6 + C+D -> 38 ($59216) [code]:
        0 anim 58 $59258: vx $6BAFA (6 px), the count $6BAFC (32), sound $51; next
        1 $5927C: a connect ($2B958) -> the victim caught (an opponent with +$FD, guarding: entry 3 checks its
          reaction, the brawler has no guard), anim 60 at once (entry 4), the count $6BB00 (128), +$D6 = 0; the count
          runs out -> the deceleration $6BAFE, next
        2 anim 68 $592E6: vx += -64 / 256 until it stops -> neutral (the whiff)
        4 anim 60 $59326: the dance (13 attack steps); its end -> +$D6 = 1 (the victim's signal), next
        38 only: anim 13 $59346: the count (128 frames: the pose) -> +$D6 = 0, then anim 60 again ($59326)
        anim 7 $59358: the end -> next; anim 9 $59364: the leap ($46C2E: $6BB02), sound $B7, the screen flash;
        $59392: the apex -> next; anim 11 $593A0: landed -> neutral.
        The victim (class 3 action 115 / 116 = result + $34E, $28310 -> $5978C) [code]: 0 anim 580: velocities 0, AT
        Kuroko's place ($2B7A2), facing his way; 1 $597C8: there every frame until his +$D6 -> next; (116: 2 anim 586
        $59800: its count $6BB00 (his pose) -> next; 3 $597C8 anim 580 again); anim 588 $59814: its end -> disarmed
        ($297D8), next; anim 464 $59828: the flight $6BB06 (4 px forward, 10 up) from its offset; landed -> the bounce
        $6BB0A, anim 466, 468, lying (the brawler's own landing). Anim 588 (3 / 2 / 3 frames) plays with his anim 7
        (3 / 2 / 3): one victim entry per step of it; the flight starts with his anim 9.
        The brawler: anim 58's attack steps catch (no damage), his +$D6 signals = P_VSIG, the dance's hits on the
        caught one keep it where the lists put it (and reel the crowd in place: fighter.c's hold)."""
        vx, cnt, dv = N.s16(0x6BAFA), N.s16(0x6BAFC), N.s16(0x6BAFE)
        jx, jy = N.s16(0x6BB02), N.s16(0x6BB04)
        n = decel_frames(vx, dv)
        ents = [E(58, [('set', 'vx', bx(vx)), ('set', 'cnt', cnt)], [('now', 'next')], catch=3),
                E(None, conds=[('cnt', 2)]),
                E(68, [('set', 'cnt', n)], [('cnt', 'end')], phys=('accel', bx(dv))),
                E(60, [('set', 'vx', 0), ('set', 'cnt', N.s16(0x6BB00))], [('end', 'next')])]
        vl = [VL([voff(580, 0) + ('580.0', 0)])]                   # at him, drawn at its animation's offset
        if maxv:
            ents += [E(13, [('vsig',)], conds=[('cnt', 'next')]), E(60, [('vsig',)], conds=[('end', 'next')])]
            vl += [VL([voff(586, 0) + ('586.0', 0)]), VL([voff(580, 0) + ('580.0', 0)])]
        ents += [E(7, [('vsig',)], conds=[('end', 'next')]),
                 E(9, [('set', 'vx', bx(jx)), ('set', 'vy', by(jy)), ('vsig',)], [('now', 'next')], phys='grav'),
                 E(None, conds=[('apex', 'next')], phys='grav'),
                 E(11, conds=[('land', 'end')], phys='grav')]
        vl += [VL([voff(588, k) + ('588.%d' % k, 0) for k in range(3)]),
               VL([voff(588, 2) + ('464.0', 64)], rel=(N.s16(0x6BB06), N.s16(0x6BB08)))]   # moved by 588's last ($2B7D0)
        return ents, [], vl
    return fn

# ---- Hattori Hanzo (table 2), TODO #193 [code] + [meas: /data/tmp/hanzo193/cap_mozu.json, moves/02.json] ------------
def han_6321s(v):
    """6 3 2 1 + A / B / A+B -> results 38-40 ($36CE6 / $36CF2 / $36CFE) [code]: entry 0 anim 206 / 214 / 217, routine
    $36D2E: +$118 = -1, velocities 0; at step 6 (+$7C == 6) spawn object type 6 (the fire, its +$F0 = the button;
    $8ACE = b + 1: a camera / effect level, not modelled), next; entry 1 $36D70: the end -> neutral"""
    a = (206, 214, 217)[v]
    return [E(a, [('set', 'vx', 0)], [(('step', 6), 'next', [('spawn', 0)])], flags={6: 0x80}),
            E(None, conds=[('end', 'end')])], [('bakuen', v)]

def han_wft(v):
    """the rage move, 6 3 2 1 4 6 + D in rage -> result 37 ($36D7E) [code]: entry 0 anim 292 $36D90 (the routine sets 292
    again every frame): velocities 0 ($2B81A), spawn object type 7 (the flame, wftflame), next; entry 1 $36DB0 (param):
    at step 5 $8ACE = 4, next; entry 2 $36DD4: the end -> neutral (from step 12 +$118 = -1: $36DEC). The hit is the
    flame's (object 7's hit routine $30752: the backdrop, the weapon lost)"""
    return [E(292, [('set', 'vx', 0), ('spawn', 0)], [('now', 'next')]),
            E(None, conds=[('end', 'end')])], [('wftflame', 0)]

def han_j4123s(v):
    """the air special (TODO #211), 4 1 2 3 + A / B / A+B in a jump (type 2 entries 9-11, one projectile at a time: b4 bit 1)
    -> results 48-50, one list $36BF2 [code]; the three buttons differ only by the shuriken's flight [meas: shuriken_ss2.py]:
    0 anim 287 $36C3A: velocities 0 ($2B81E), +$EE = $80 (no gravity: he hangs where the jump was), the end -> next
    1 anim 249 $36C4E: at step 1 (+$7C == 1) spawn object type 5 (the shuriken, its +$F0 = the button) unless his
      projectile is out (+$112), next      2 $36C76 (param): the end -> next
    3 anim 26 $36C7E: +$118 = -1; $46BAE($0800 | $36CB6[b]) = entry 24 / 26 / 28 (the same for every button): the recoil
      hop, vx -304 (backward) vy -796 (up), next (bit 11); the next entry's pair -> +$D4 / +$D6 (0, 76), +$EE = $80
    4 $36CBA (param): landed (+$EE 0) -> next, else vx += +$D4, vy += +$D6 (his own gravity)
    5 anim 3 $36CD8 (the landing): the end -> neutral ($2B802)
    The jump's own speed is dropped at entry 0 (a forward jump stops: the hop goes back from where he threw)."""
    e = N.u8(0x36CB6 + v) + 16
    (rx, ry), (ax, ay) = vtab(2, e), vtab(2, e + 1)
    return [E(287, [('set', 'vx', 0), ('set', 'vy', 0)], [('end', 'next')], phys='air'),
            E(249, conds=[(('step', 1), 'next', [('spawn', 0)])], phys='air', flags={1: 0x80}),
            E(None, conds=[('end', 'next')], phys='air'),
            E(26, [('set', 'vx', bx(rx)), ('set', 'vy', by(ry))], [('now', 'next')], phys='air'),
            E(None, conds=[('land', 'next')], phys=('custom', ax, ay)),
            E(3, conds=[('end', 'end')])], [('shuriken', v)]

# Mozu Otoshi's grab [code]: the MOZU-SPS task ($36E74 -> $3702E, every frame while it lives) catches the opponent when
# |his x - its x| < word $6A8AA[2 b + its posture] (69 px for every button and posture) and both stand on the floor,
# free ($37288). The brawler's catch is a box against the victim's hurt box: GRAB_BOX reaches 69 px from his x to the
# centre of a body 30 px half-wide (a KOF fighter's): a catch box 30 px forward, 5 px half-wide, the body's height.
GRAB_BOX = [-35, -42, 5, 42]
MOZU_TOP = 64                                     # Mozu Otoshi's leaps fitted to the brawler's screen (TODO #185's rule)

def han_623k(v):
    """Mozu Otoshi, 6 2 3 + C / D / C+D -> results 43-45 (one list $36DFC; the same code for Galford, his tables at
    $6AADA..) [code]:
    0 anim 296 $36E74: velocities 0, the MOZU-SPS task (the grab test above), next   1 $36EA8: the end -> neutral (a whiff:
      one frame). The task's catch: the opponent (class 3 action 33, anim 490) at his x, facing his way, its entry kept
      equal to his (+$F9) until his entry 6 ($370B4); he goes on at entry 2
    2 anim 58 $36EB6: +$D4 = -1 when his previous action was class 0 action 30 / 41 (+$C6), else 0; the end -> next
    3 $36EE0 (param): the leap $36F46[b] -> [vx (only with +$D4: 0 from a stand), vy, the second leap's vx / vy, the hold
      +$D7]: vy, gravity on, next
    4 anim 60 $36F5E: the afterimages (effect 16 every 6 frames: not modelled); the apex -> next
    5 anim 62 $36F74: landed -> the slam: the victim's damage (+$106 from $6A8E6), its hit-stop and the game's +$D7 (14 /
      14 / 21 frames; doubled by the slow motion $8ACE: not modelled), effect 14 (Hanzo's fire, anim 244, sound $14D),
      sound $80, next
    6 anim 38 $36FF8: the second leap (vx / vy from +$D8 / +$DA), gravity, next   7 $37010: the end -> next
    8 $37018: the apex -> next   9 anim 26 $37020: landed -> the landing (class 0 action 18: neutral here)
    The victim (class 3 action 33, the same list for every character: $370DE) [code + meas]: anim 490 / 490 / 492 / 494 with
    his entries 0-5 (at his place, facing his way, drawn by its animations' $20 offsets), at his entry 6 its own
    ($37168): the flight $371D8[b] (2 px forward, 6 / 7 / 10 up, burning: anim 460), a bounce ($371F8) and lying.
    The brawler: anim 296 catches (GRAB_BOX), the victim lists follow his animations (P_VSIG at each), the slam = a blow
    with the hold +$D7 in his landing pose (62's first step), the release at 38 with the default row's flight; the
    heights x MOZU_TOP / the rise (velocities and gravity: the same timing; SS2's camera follows him 160 px up)"""
    tab = N.u32(0x36F46 + 4 * v)
    vx, vy, vx2, vy2, _, hold = (N.s16(tab + 2 * i) for i in range(6))
    top = (vy / 256) ** 2 / (2 * GRAVITY / 256)
    q = min(1.0, MOZU_TOP / top); f = lambda w: round(w * q); g = ('custom', 0, f(GRAVITY))
    return [E(296, [('set', 'vx', 0)], [('now', 'next')], catch=2, grab=GRAB_BOX),
            E(None, conds=[('caught', None), ('end', 'end')]),
            E(58, [('set', 'vx', 0)], [('end', 'next')]),
            E(None, [('set', 'vy', by(f(vy)))], [('now', 'next')], phys=g),
            E(60, [('vsig',)], conds=[('apex', 'next')], phys=g),
            E(62, [('vsig',)], conds=[('land', 'next', [('spawn', 0), ('snd', 0x80), ('snd', 0x14D)])], phys=g),
            E((62, 0, 0), [('vsig',), ('set', 'cnt', hold & 0xFF)], conds=[('cnt', 'next')]),
            E(38, [('vsig',), ('set', 'vx', bx(vx2)), ('set', 'vy', by(f(vy2)))], [('now', 'next')], phys=g),
            E(None, conds=[('end', 'next')], phys=g),
            E(None, conds=[('apex', 'next')], phys=g),
            E(26, conds=[('land', 'end')], phys=g)], [('mozufire', 0)], mozu_lists(v)

# ---- Hanzo's other specials (Character Lab hanzo_ss2, 2026-10-10): the recogniser's every result (commands_ss2.py 2) ---
# 6 4 1 2 3 6 + A / B -> results 41 / 42, Ninpou Kage Bunshin; 6 3 2 1 4 + B+C+D -> 46, Ninpou Utsusemi (the secret
# move: the teleport above the opponent); 6 4 6 4 6 4 2 + B+C+D -> 51, Ninpou Kagemai (the invisibility). The same lists
# serve Galford (char 3, his tables at $6AB1A / $6ABC6..): `han_*` read Hanzo's tables. [code] + [meas: moves/02.json
# cmd7 / cmd8 / cmd6 / cmd5]
KB_X = (80, 240)                                  # $37530: screen left + 80 / + 240 (d0 / d1: A = him at 80 and the
                                                  # clone at 240, B = swapped: action 42 exchanges them, `cmpb +$E7`)
def han_641236s(v):
    """Ninpou Kage Bunshin, 6 4 1 2 3 6 + A / B -> results 41 / 42, one list $37452 (its first 11 entries: armed) [code]:
    0 anim 12 $374D6: velocities 0 ($2B81E), the end -> next
    1 anim 15 $374E4: the timer +$24 = word $6A8F6[0] (12; the task scheduler counts +$24 down every frame, $1570),
      next   2 $374F2 ($2B936): the timer at 0 -> next
    3 anim 14 $374FA: the end -> $8ADF + 1, +$24 = $6A8F6[1] (64), next
    4 anim 80 $37514 (nothing drawn: he is gone): x = the opponent's x; $8ACC = 0 (always in our captures) or the timer
      at 0 -> next [meas: one frame]
    5 anim 19 $37530: +$118 = -1, sound $E7, spawn object 8 (the clone, $30774), him at the screen's left + 80 and the
      clone at + 240 facing each other (B: swapped), effect 92 (smoke) at both places, next
    6 $375D0 (param): the end -> next   7 anim 19 again, the end -> next   8 $375D8: +$24 = $6A8F6[2] (60), next
    9 $375EE (param): the stance: a direction -> neutral, a button -> an attack (class 1 action 31 + $2C0E6[button]: his
      far A / far B / far A+B / crouch C / crouch D), the clone gone or the timer at 0 -> next
    10 anim 25 $3764E: the end -> neutral
    Measured (cmd7 / cmd8, P2 at 400): 162 frames; anim 80 one frame (x = 400), him at x 243 facing right (A) / 403
    facing left (B), anim 19 14 + 1 + 1 frames, the stance 60, anim 25 15 (B: P2 guards it at 177: 25 is a slash).
    The brawler: P_WARP (screen mode, the camera's left + 80 / + 240, turned to the screen's middle), the clone an
    effect 160 px ahead of him facing him (kclone); the stance's follow-ups and the smoke are not modelled."""
    t = [N.s16(0x6A8F6 + 2 * i) for i in range(3)]
    return [E(12, [('set', 'vx', 0)], [('end', 'next')]),
            E(15, [('set', 'cnt', t[0] - 1)], [('cnt', 'next')]),
            E(14, conds=[('end', 'next')]),
            E(80, [('warp', 1, 0, KB_X[v])], [('now', 'next')]),
            E(19, [('spawn', 0)], [('end', 'next')]),
            E((19, 0, 0), [('set', 'cnt', t[2] - 1)], [('cnt', 'next')]),
            E(25, conds=[('end', 'end')])], [('kclone', v)]

UTSU_TOP = 128                                    # px: Utsusemi's drop fitted to the brawler's screen (SS2: 195 above the
                                                  # floor, its camera follows; the timing kept: gravity x the same factor)
def han_63214bcd(v):
    """Ninpou Utsusemi (the secret teleport), 6 3 2 1 4 + B+C+D -> result 46, list $37928 [code]:
    0 anim 14 $37A00: velocities 0; the end -> +$CC = $6A9A2 (Hanzo's), the timer +$24 = its word 0 (0), next
    1 anim 80 $37A6C: the timer at 0 and the opponent on the floor -> $37B94: at the opponent's x, then $2B77E: 5 px
      back (his facing), height = -$6A95A[opponent's character].y (195 for most, 259 for Earthquake, 204 Haohmaru, 185
      Nakoruru: the victim's size picks it), vy = word 2 (0), gravity on, effect 20, next
    2 anim 195 $37AAE (the spinning drop): a hit ($2B958) -> the bounce $37B1C[stick: none / back / forward / both] (vx
      -4 / -4 / +5 / 0, vy 9 / 9 / 9 / 11 up), next; landed without one -> entry 5
    3 anim 22 $37B5C: +$118 = -1; its end or landed -> next   4 anim 26 $37B7A: landed -> next
    5 anim 3 $37B86: +$118 = 1, the end -> neutral
    Measured (cmd6, P2 at 400): anim 14 30 frames, gone one frame, at x 395 height 204 (P2 Haohmaru), 195 falling 24
    frames, P2 hit (class 3 action 3), the bounce back to x 331, landed at 251 (SS2's hit slow motion stretches it).
    The brawler: P_WARP (target mode: the one he hit, else the nearest opponent, 5 px short of it, the normal victim's
    height 195 fitted x UTSU_TOP / 195; SS2's Earthquake row 259 not used), the neutral stick's bounce. His BREAKER
    (game.json roster hanzo_ss2 specials.D: the neutral C special, Bruno 2026-10-10)"""
    tab = N.u32(0x37B1C)                              # (the neutral stick's bounce)
    bvx, bvy = N.s16(tab), N.s16(tab + 2)
    dx, h = N.s16(0x6A95A + 4 * 0), -N.s16(0x6A95A + 4 * 0 + 2)        # (Haohmaru's row: dx -5)
    hn, hb = -N.s16(0x6A95A + 4 * 2 + 2), -N.s16(0x6A95A + 4 * 8 + 2)   # a normal victim (195) / Earthquake (259)
    q = UTSU_TOP / hn; f = lambda w: round(w * q); g = ('custom', 0, f(GRAVITY))
    return [E(14, [('set', 'vx', 0)], [('end', 'next')]),
            E(80, [('warp', 0, dx, f(hn)), ('set', 'vx', 0), ('set', 'vy', 0)], [('now', 'next')]),
            E(195, conds=[('hit', 'next'), ('land', 5)], phys=g),
            E(22, [('set', 'vx', bx(bvx)), ('set', 'vy', by(f(bvy)))], [('end', 'next'), ('land', 'next')], phys=g),
            E(26, conds=[('land', 'next')], phys=g),
            E(3, conds=[('end', 'end')])], []

def han_6464642bcd(v):
    """Ninpou Kagemai (the invisibility), 6 4 6 4 6 4 2 + B+C+D -> result 51, list $37386 [code]: entry 0 $373A4: +$118
    = -1; +$88 bit 7 (the object hidden: the task scheduler's blink bit, $1584) cleared if it was set (he shows again:
    +$D4 = 0) else +$D4 = -1 (he goes invisible), the animation from $37432 (+$D4 set) / $3743A [entry][mode] (204 then 14 to vanish),
    velocities 0; 1 $373CE: the end -> next; 2 $373D6: the second animation (14), next; 3 $373E2: the end -> next;
    4 $373EA: going invisible: object 18 (his hidden marker) in $8A6A, neutral. Measured (cmd5): 204 48 frames, 14 30,
    80 in all. The brawler plays the vanishing (204 then 14); the hidden state itself (the opponent's AI and hits not
    seeing him) is not modelled: the brawler has no invisible fighter"""
    a0 = N.u16(0x37432); a1 = N.u16(0x37432 + 4)          # (+$D4 = -1: vanishing; $3743A = 14, 204: showing again)
    return [E(a0, [('set', 'vx', 0)], [('end', 'next')]),
            E(a1, conds=[('end', 'end')])], []

def kclone(B, v):
    """Kage Bunshin's clone, object 8 ($30774) [code]: Hanzo's anim 289 (his stance, the clone's one step) while he is in
    the move ($307B6: his class 1), blinking (+$22 = 2); hit ($C670): anim 104 (the log: utsusemi) for $6A8F6[3] frames,
    then it falls (369) and is gone. The brawler: 289 drawn turned (facing him) 160 px ahead of him from the warp to the
    move's end (anim 19 twice, the stance, anim 25: 14 + 1 + 60 + 15 frames); no box (the log is not modelled)"""
    st = ss2.parse_anim(2, 289, 400)[0]
    fr = B.frame(st, mirror=True)
    n = 14 + 1 + N.s16(0x6A8F6 + 4) + 15
    return {'kind': 3, 'rows': [[fr, 160, 0, None, None] for _ in range(n)], 'loop': None, 'end': [], 'react': 0,
            'hit_kind': 1, 'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0,
            'travel': 0, 'name': 'KCLONE', 'ss2': {'object': 8, 'anim': 289}}

def mozu_lists(v):
    """the victim of Mozu Otoshi (VL; handlers_ss2.voff: Haohmaru's offsets, every character's victim animations): at his
    place facing his way; lists: 490 (his 58), 492 (his 60), 494 (his 62, step by step), the slam (a blow, his held pose),
    the release (460 burning: the flight $371D8[b], 8.8 vy down)"""
    rv = N.u32(0x371D8 + 4 * v)
    t = lambda a, k, fl=0: voff(a, k) + ('%d.%d' % (a, k), fl, 1)
    return [VL([t(490, 0), t(490, 1)]), VL([t(492, 0)]), VL([t(494, k) for k in range(4)]),
            VL([t(494, 0, 1)]), VL([(0, 0, '460.0', 64, 1)], rel=(N.s16(rv), N.s16(rv + 2)))]

# fighter -> its specials: input -> (decoder, buttons, the command results per button (moves/CC.json's entries))
SPECIALS = {
    'haohmaru': {'236S': (hao_236s, 3, (41, 42, 43)), '623S': (hao_623s, 3, (38, 39, 40)), '623K': (hao_623k, 3, (48, 49, 50)),
                 '236K': (hao_236k, 1, (44,)), '214A': (hao_214a, 1, (47,)), 'WFT': (hao_wft, 1, (37,))},
    'genjuro': {'214S': (gen_214s, 3, (38, 39, 40)), '236S': (gen_236s, 3, (41, 42, 43)), '623S': (gen_623s, 3, (50, 51, 52)),
                'WFT': (gen_wft, 1, (37,))},
    'hanzo': {'6321S': (han_6321s, 3, (38, 39, 40)), '623K': (han_623k, 3, (43, 44, 45)), 'WFT': (han_wft, 1, (37,)),
              'j.4123S': (han_j4123s, 3, (48, 49, 50)),      # (j.: an air special, TODO #211: game.json air_special)
              # the rest of his recogniser (Character Lab 2026-10-10): Lab pieces only (LAB_ONLY: not in the game's pool)
              '641236S': (han_641236s, 2, (41, 42)), '63214BCD': (han_63214bcd, 1, (46,)), '6464642BCD': (han_6464642bcd, 1, (51,))},
    # (input = the recogniser's own: commands_ss2.py 17; 2026-10-07: 61236A is result 41 and 214161BC result 46, the
    # export had them swapped)
    'kuroko': {'236A': (kur_parody(39), 1, (39,)), '16A': (kur_parody(40), 1, (40,)), '61236A': (kur_parody(41), 1, (41,)),
               '126BC': (kur_parody(42), 1, (42,)), '236B': (kur_parody(43), 1, (43,)), '2363214A': (kur_parody(44), 1, (44,)),
               '214A': (kur_parody(45), 1, (45,)), '214161BC': (kur_parody(46), 1, (46,)), 'CCCCC': (kur_ccccc, 1, (47,)),
               '6ABC': (kur_flag(3), 1, (48,)), '6BCD': (kur_flag(5), 1, (49,)), '63214A': (kur_boomerang, 1, (50,)),
               'RAGE': (kur_rage(False), 1, (37,)), 'MAX RAGE': (kur_rage(True), 1, (38,))},
}
CHAR = {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17, 'hanzo': 2}
LAB_ONLY = {('hanzo', '641236S'), ('hanzo', '6464642BCD')}   # (63214BCD: in the game, his breaker)   # decoded for the Character Lab (its
                                                  # pieces, condition 'lab'): the normal game's pools take 'normal' only
NAMES = {'hanzo': {'6321S': 'Ninpou Bakuen Ryuu', '623K': 'Ninpou Mozu Otoshi', 'WFT': 'Ninpou Tenma Fukumetsu (rage)',
                   'j.4123S': 'Ninpou Reppuu Shuriken (air)', '641236S': 'Ninpou Kage Bunshin', '63214BCD': 'Ninpou Utsusemi',
                   '6464642BCD': 'Ninpou Kagemai'}}   # SNK's names (snk.fandom.com "Hanzo Hattori/Move List", read through
                                                  # its API 2026-10-10: Bakuenryuu f-hcb... S, Mozu Otoshi close 623 K, Kage
                                                  # Bunshin 641236 A / B (SS II-V), Tenma Fukumetsu hcb-f D (SS II's rage
                                                  # move); the air shuriken, Utsusemi and Kagemai under their later games'
                                                  # names: SS II's inputs here are the ROM's)

def version_input(inp, k, nv):
    """one button version's own input: '6321S' -> '6321A' / '6321B' / '6321AB', '623K' -> '623C' / '623D' / '623CD',
    'j.4123S' -> 'j.4123A' ... (the S- piece of that version, Character Lab: each version its own piece)"""
    b = (['C', 'D', 'CD'] if inp[-1] == 'K' else ['A', 'B', 'AB'])[k]
    return inp[:-1] + b

# ---- the program: entries -> ops --------------------------------------------------------------------------------------
CUR = {'ch': 0}
def end_ev(a):
    """the animation's last step has 0 ticks: its end is its event (rom_steps)"""
    if isinstance(a, tuple):
        st = ss2.parse_anim(CUR['ch'], a[0], 400)[a[1]:None if a[2] is None else a[2] + 1]
        return len(st) > 1 and st[-1]['ticks'] == 0
    st = ss2.parse_anim(CUR['ch'], a, 400)
    return len(st) > 1 and st[-1]['ticks'] == 0

def compile_prog(ents):
    """[(op, operands...)] with labels; anims (SS2 animation of each state, in P_ANIM order); spawns"""
    ops, states = [], []
    def tgt(i, t):
        if t is None: return None
        if t == 'next': return ('E', i + 1)
        if t == 'end': return 'END'
        if isinstance(t, str) and t.startswith('part'):
            return ('E', next(j for j, e in enumerate(ents) if e['part'] == int(t[4:])))
        return ('E', int(str(t).split(':')[-1]))
    def airborne(e):
        p = e['phys']; return p in ('grav', 'air') or (isinstance(p, tuple) and p[0] == 'custom')
    def integrate(e, tag):
        """the frame's move with the velocities it starts with (SS2 integrates before the routine runs), then the
        landing of an airborne body (SS2: after the routine; seen by the routine the next frame: 'land' is tested
        before this)"""
        out = [('move',)]
        if airborne(e):
            out += [('fall',), ('br', 'land', 0, ('L', tag)), ('set', 'vx', 0), ('set', 'vy', 0), ('label', ('L', tag))]
        return out
    def routine_phys(e, tag):
        """what the routine and the dispatcher do to the velocities after the conditions: gravity, its own
        acceleration, the deceleration ($46C64: vx += dv until it crosses 0: a count of frames)"""
        p = e['phys']
        if p == 'grav': return [('add', 'vy', by(GRAVITY))]
        if isinstance(p, tuple) and p[0] == 'custom': return [('add', 'vx', bx(p[1])), ('add', 'vy', by(p[2]))]
        if isinstance(p, tuple) and p[0] == 'accel': return [('add', 'vx', p[1])]
        if isinstance(p, tuple) and p[0] == 'decel':
            return [('dec',), ('br', 'cnt', 0, ('D', tag)), ('set', 'vx', 0), ('jmp', ('M', tag)), ('label', ('D', tag)),
                    ('add', 'vx', p[1]), ('label', ('M', tag))]
        return []
    cur = None
    for i, e in enumerate(ents):
        landc = [(k, cnd) for k, cnd in enumerate(e['conds']) if cnd[0] == 'land']
        ops.append(('label', ('E', i)))
        for k, cnd in landc: ops.append(('br', 'land', 1, ('S', i, k)))
        ops += integrate(e, (i, 'e'))
        ops.append(('label', ('I', i)))               # an immediate switch (the routine sets +$66 itself) lands here
        if e['anim'] is not None: cur = e['anim']; ops.append(('anim', len(states))); states.append((i, e['anim']))
        if e.get('catch') is not None: ops.append(('onhit', ('I', e['catch'])))   # its catch routine (P_ONHIT)
        for o in e['init']:
            if o[0] == 'set': ops.append(('set', o[1], o[2]))
            elif o[0] == 'spawn': ops.append(('spawn', o[1]))
            elif o[0] == 'part': ops.append(('part',))
            elif o[0] == 'move_now': ops.append(('move',))
            elif o[0] == 'vsig': ops.append(('vsig',))
            elif o[0] == 'fxoff': ops.append(('fxoff',))
            elif o[0] == 'warp': ops.append(('warp', o[1], o[2], o[3]))   # P_WARP a = mode (1 screen, 0 target), b dx, v
            else: raise ValueError(o)
        ops += [('resume_at', ('LP', i)), ('jmp', ('R', i)), ('label', ('LP', i))]
        for k, cnd in landc: ops.append(('br', 'land', 1, ('S', i, k)))
        ops += integrate(e, (i, 'l'))
        ops.append(('label', ('R', i)))
        sw = []; now = None
        for k, cnd in enumerate(e['conds']):
            c, t = cnd[:2]; extra = [('spawn', o[1]) for o in (cnd[2] if len(cnd) > 2 else []) if o[0] == 'spawn']
            T = tgt(i, t)
            if c == 'land': sw.append((('S', i, k), T, extra, False)); continue
            if c == 'caught': ops.append(('br', 'caught', 1, 'yield')); continue   # caught: wait for the catch routine
            if c == 'now': now = (T, extra); break
            if isinstance(t, str) and t.startswith('now:'):
                ops.append(('br', {'hit': 'hit'}[c], 1, ('I', int(t[4:])))); continue
            if isinstance(c, tuple) and c[0] == 'link':
                ops += [('br', 'window', 0, ('NL', i, k)), ('br', 'hit', 0, ('NL', i, k)), ('check', c[1]),
                        ('br', 'link', 1, ('I', T[1]), c[1]), ('label', ('NL', i, k))]
                continue
            if c == 'passed':                         # its opponent reached / passed ($563F4): that frame's physics, then T
                ops.append(('br', 'passed', 1, ('S', i, k), 0)); sw.append((('S', i, k), T, extra, True)); continue
            if c == 'cnt': ops.append(('dec',)); cond = 'cnt'
            else: cond = {'end': 'end', 'apex': 'fall', 'hit': 'hit', 'sig': 'sig7c'}.get(c) or ('stepev' if c[0] == 'step' else None)
            if c == 'end' and end_ev(cur): ops.append(('br', 'stepev', 1, ('S', i, k)))
            ops.append(('br', cond, 1, ('S', i, k))); sw.append((('S', i, k), T, extra, True))
        # back to neutral (target 'END'): SS2's routine clears the class (+$E6 = 0) in the frame its condition holds, so
        # the program ends in that frame (P_END: prog_end), not on the next one (TODO #191: one of the two extra frames)
        if now: ops += now[1] + (routine_phys(e, (i, 'n')) + [('resume_at', now[0]), ('br', 'always', 1, 'yield')] if now[0] != 'END' else [('jmp', 'END')])
        else: ops += routine_phys(e, (i, 'loop')) + [('br', 'always', 1, 'yield')]
        for lab, T, extra, ph in sw:
            ops += [('label', lab)] + extra + ((routine_phys(e, lab) if ph else []) + [('resume_at', T), ('br', 'always', 1, 'yield')] if T != 'END' else [('jmp', 'END')])
    ops += [('label', ('E', len(ents))), ('label', 'END'), ('end',)]
    return ops, states

def assemble(ops):
    lab, out = {}, []
    for o in ops:
        if o[0] == 'label': lab[o[1]] = len(out)
        else: out.append(o)
    res = []
    for o in out:
        if o[0] == 'br': res.append(('br', o[1], o[2], -1 if o[3] == 'yield' else lab[o[3]]) + tuple(o[4:]))
        elif o[0] in ('jmp', 'resume_at', 'onhit'): res.append((o[0], lab[o[1]]))
        else: res.append(o)
    return res

def encode(o):
    """(op, a, b, v) of an assembled op"""
    n = o[0]
    if n == 'anim': return (P['anim'], o[1], 0, 0)
    if n in ('set', 'add'): return (P[n], REG[o[1]], 0, o[2])
    if n == 'br': return (P['br'], PC[o[1]] | (0x80 if o[2] else 0), o[3], o[4] if len(o) > 4 else 0)
    if n in ('jmp', 'resume_at'): return (P[n], 0, o[1], 0)
    if n == 'onhit': return (P[n], 0, o[1], 0)       # a = the catch's dead frames - 1 (none: SS2 sets the routine's
                                                    # animation in the frame of the connect)
    if n == 'fall': return (P['fall'], 1, 0, 0)          # a 1: SS2's landing ($27802: y > 224, the floor line itself is
                                                        # not a landing; fighter.c P_FALL, TODO #191)
    if n == 'spawn': return (P['spawn'], o[1], 0, 0)
    if n == 'check': return (P['check'], o[1], 0, 0)
    if n == 'nudge': return (P['nudge'], 0, o[1], 0)
    if n == 'warp': return (P['warp'], o[1], o[2], o[3])
    return (P[n], 0, 0, 0)

# ---- the brawler's player, ported from fighter.c (prog_update, pan_*), for check() and the hit counts ----------------
class Play:
    """one special's program played alone (no opponent: no hit), per frame the state (anim index, step, x, y)"""
    def __init__(self, prims, anims, vars_=None, var=0, vcols=0, vanim=0):
        self.prims, self.anims, self.vars, self.var, self.vcols, self.vanim = prims, anims, vars_, var, vcols, vanim
        self.x = self.y = self.vx = self.vy = self.pg = self.cnt = 0
        self.flags = set(); self.pres = 0; self.done = False; self.spawns = []; self.rows = []; self.srow = 0
        self.landed = False; self.plink = 0; self.spend = 0
        self.sig_after = {}                               # spawn index -> frames from its spawn to its signal (alone:
        self.sig_at = None                                # a boomerang's catch, boomerang_model); the frame it is seen
    def pan_enter(self):
        s = self.an['steps'][self.pstep]
        self.flags.discard('event')
        if s['flags'] & 0x80: self.flags.add('event')      # (the export's KOF flags: rom_c makes 0x80 bstep 8)
    def pan_play(self, k):
        self.ai = k; self.an = self.anims[k]; self.pstep = 0; self.pleft = self.an['steps'][0]['ticks'] + 1
        self.flags -= {'end', 'event'}; self.pan_enter()
    def pan_advance(self):
        self.pleft -= 1
        if self.pleft: return
        if self.pstep + 1 < len(self.an['steps']): self.pstep += 1
        else:
            self.flags.add('end')
            if self.an['hold']: self.pleft = 1; return
            self.pstep = 0
        self.pleft = self.an['steps'][self.pstep]['ticks'] + 1; self.pan_enter()
    def cond(self, c, v):
        s = self.an['steps'][self.pstep] if hasattr(self, 'an') else {'flags': 0}   # (an air program tests its landing
                                                                                       # before its first P_ANIM)
        return {PC['stepev']: 'event' in self.flags, PC['end']: 'end' in self.flags, PC['land']: 'land' in self.flags,
                PC['fall']: 'fall' in self.flags, PC['cnt']: self.cnt < 0, PC['hit']: self.landed,
                PC['window']: bool(s['flags'] & 0x2000), PC['link']: bool(self.plink & v), PC['always']: True,
                PC['passed']: False,                       # (alone: no opponent to pass)
                PC['caught']: False,                       # (alone: nobody caught)
                PC['sig7c']: self.sig_at is not None and self.srow - 1 >= self.sig_at}[c]
    def frame(self):
        if self.done: return None
        self.srow += 1; ppc = self.pres
        for _ in range(96):
            op, a, b, v = self.prims[ppc]; ppc += 1
            if op & 0x80: op &= 0x7F; v = self.vars[self.var * self.vcols + b]
            if op == P['anim']: self.pan_play(a + self.var * self.vanim)
            elif op == P['set']:
                if a == 0: self.vx = v
                elif a == 1: self.vy = v
                elif a == 2: self.pg = v
                elif a == 5: self.y = v
                elif a == 4: self.cnt = v
            elif op == P['add']:
                if a == 0: self.vx += v
                elif a == 1: self.vy += v
                else: self.cnt += v
            elif op == P['move']: self.x += self.vx
            elif op == P['fall']:
                v0 = self.vy; self.vy -= self.pg; self.y += v0; self.flags -= {'land', 'fall'}
                if self.y <= 0 and a and self.y > -65536: self.y = 0     # (SS2's floor line: not a landing, fighter.c)
                elif self.y <= 0: self.y = 0; self.flags.add('land')
                if 'land' not in self.flags and self.vy < 0: self.flags.add('fall')
            elif op == P['nudge']: self.x += b << 16; self.y += v << 16
            elif op == P['warp']:                         # (alone: a target mode warp keeps x, rises to the normal
                if a & 1: self.x = (v - 160) << 16        # victim's height; a screen one: x from the screen's middle)
                else: self.y = v << 16
            elif op == P['dec']: self.cnt -= 1
            elif op == P['br']:
                if self.cond(a & 0x7F, v) == bool(a >> 7):
                    if b < 0: break
                    ppc = b
            elif op == P['resume']: self.pres = ppc
            elif op == P['resume_at']: self.pres = b
            elif op == P['jmp']: ppc = b
            elif op == P['spawn']:
                self.spawns.append((self.srow - 1, a, self.x))
                if a in self.sig_after: self.sig_at = self.srow - 1 + self.sig_after[a] + 1   # (its update after his: seen
                                                                                               # the next frame)
            elif op == P['check']: self.plink |= self.spend & a
            elif op == P['part']: self.plink = 0
            elif op == P['end']: self.done = True; return None
        self.spend = 0
        self.pan_advance()
        return (self.ai, self.pstep, self.x / 65536, self.y / 65536)

# ---- objects (projectiles, effects) -----------------------------------------------------------------------------------
def attack_recs(st): return [l for w, l in st['boxes'] if w & 0x8000]

def obj_rows(B, ch, frames, x0=0.0, vx=0.0, y0=0.0):
    """rows of an object: frames = [(SS2 anim, step)] per frame; x from its spawn place (forward), y height"""
    import export_ss2 as X
    rows, x = [], x0
    for k, (a, i) in enumerate(frames):
        st = ss2.parse_anim(ch, a, 400)[i]
        atk = attack_recs(st)
        box = X.kof_box(atk) if atk else None
        rows.append([B.frame(st), round(x, 3), y0, [1] + box if box else None, box])
        x += vx
    return rows

def play_anim(ch, a, frames=None, loop=False):
    """[(a, step)] per frame of animation a played from its start (ticks + 1 frames a step), its end frame included
    (the frame +$FA is seen); loop: one cycle"""
    st = ss2.parse_anim(ch, a, 400); out = []
    for i, s in enumerate(st): out += [(a, i)] * (s['ticks'] + 1)
    return out

def tornado(B, v):
    """Haohmaru's object type 2 ($301DC) [code]: born 16 px ahead ($2B77E), animation $30274[16 b + 0] (19: the
    launch, 3 steps) in place; at its end ($30210) vx from $46BAE($1218 + b) (entry 40 + b: 3.6 / 4.8 / 6 px), the
    flight animation (59, looping: 2 frames on, 1 off its box), until off screen ($2B992); on a hit of a spinning victim
    ($302CC: class 3 action $82-$84) animation [2] (62 / 80), then [3] (81 / 240) for $6A6CE[b] (64) frames, then [4]
    (241 / 245) and the end"""
    idx = [N.u16(0x30274 + 16 * v + 2 * k) for k in range(6)]
    vx = vword(0, 0x1218 + v)[0] / 256
    launch = play_anim(0, idx[0]); flight = play_anim(0, idx[1])
    rows = obj_rows(B, 0, launch, 16.0) + obj_rows(B, 0, flight, 16.0 + vx, vx)
    cnt = N.s16(0x6A6CE + 2 * v)
    end = play_anim(0, idx[2]) + [(idx[3], s) for k in range(cnt + 1) for s in [play_anim(0, idx[3])[k % len(play_anim(0, idx[3]))][1]]] + play_anim(0, idx[4])
    endr = [[r[0], 0, 0] for r in obj_rows(B, 0, end)]
    return {'kind': 1, 'rows': rows, 'loop': len(launch), 'end': endr, 'react': 'knockdown', 'hit_kind': 1,
            'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0,
            'travel': 300, 'vx': vx, 'name': 'SENPUDAN', 'ss2': {'type': 2, 'anims': idx}}

def crescent(B, v):
    """Haohmaru's object type 1 ($30056) [code]: animation $300EC[b] (268 / 269 / 282: 27 steps, one frame each, its
    attack boxes on steps 2, 12-14) at its thrower's place; pinned to him (follow 3: it ends with its last row)"""
    a = N.u16(0x300EC + 2 * v)
    rows = obj_rows(B, 0, play_anim(0, a))
    return {'kind': 3, 'rows': rows, 'loop': None, 'end': [], 'react': 'knockdown', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 3, 'travel': 0,
            'name': 'KOGETSU', 'ss2': {'type': 1, 'anim': a}}

def cards(B, v):
    """Genjuro's object type 10 ($4B46C) [code]: animation 264 (8 steps looping) 76 px ahead, 59 up; vx $6B512[b]
    (2.6 / 4.6 / 6.6 px), a life of $6B514[b] (32) frames ($4B4EC), then it breaks (animation $4B4D2[b]: 267 / 268 / 269,
    and 3 objects 28: the falling cards); a hit: velocity 0, the break animation in place ($4B55A)"""
    vx = N.s16(0x6B512 + 4 * v) / 256; life = N.s16(0x6B514 + 4 * v)
    brk = N.u16(0x4B4D2 + 2 * v)
    cyc = play_anim(12, 264)
    fl = [cyc[k % len(cyc)] for k in range(life + 2)]
    rows = obj_rows(B, 12, fl, 76 + vx, vx, 59) + [r[:3] + [None, None] for r in obj_rows(B, 12, play_anim(12, brk), 76 + vx * (life + 2), 0, 59)]
    endr = [[r[0], 0, 0] for r in obj_rows(B, 12, play_anim(12, brk))]   # in place: at the hit's height (bpend_t y from it, TODO #164)
    return {'kind': 1, 'rows': rows, 'loop': None, 'end': endr, 'react': 'knockdown', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0, 'travel': vx * (life + 2),
            'vx': vx, 'name': 'CARDS', 'ss2': {'type': 10, 'anim': 264, 'break': brk}}


def kparody(B, k):
    """Kuroko's object type 25 ($4C12A) [code]: +$D4 = k picks [animation][end animation][dx][dy] at $4C182 + 8 k (its
    place from his: dx forward, dy up), vx = word $6BB0E[k]; it flies looping its animation until off screen ($4C1CA);
    a hit: velocity 0, the end animation in place ($4C1E0)"""
    a, end, dx, dy = (N.u16(0x4C182 + 8 * k + 2 * i) for i in range(4))
    dy = dy - 65536 if dy & 0x8000 else dy
    vx = N.s16(0x6BB0E + 2 * k) / 256
    cyc = play_anim(17, a)
    if len(cyc) < 2: cyc = cyc * 2                # a one-frame animation (object 8: anim 41) as two rows: the loop's
                                                  # wrap is the rows' own step (export_bm), one row stood still
    rows = obj_rows(B, 17, cyc, dx + vx, vx, -dy)
    endr = [[r[0], 0, 0] for r in obj_rows(B, 17, play_anim(17, end))]   # in place: at the hit's height (bpend_t y from it, TODO #164)
    return {'kind': 1, 'rows': rows, 'loop': 0, 'end': endr, 'react': 'knockdown', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0, 'travel': 300, 'vx': vx,
            'name': f'PARODY{k}', 'ss2': {'type': 25, 'which': k, 'anim': a, 'end': end}}

def kcrescent(B, k):
    """Kuroko's object type 24 ($4C07C) [code]: animation 46 72 px ahead, 56 up; at its end ($4C0B4) animation 49
    flying at word $6BB20 (8 px), until off screen; a hit: animation 55 in place ($4C0EE)"""
    vx = N.s16(0x6BB20) / 256
    first = play_anim(17, 46); cyc = play_anim(17, 49)
    rows = obj_rows(B, 17, first, 72, 0, 56) + obj_rows(B, 17, cyc, 72 + vx, vx, 56)
    endr = [[r[0], 0, 0] for r in obj_rows(B, 17, play_anim(17, 55))]   # in place: at the hit's height (bpend_t y from it, TODO #164)
    return {'kind': 1, 'rows': rows, 'loop': len(first), 'end': endr, 'react': 'knockdown', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0, 'travel': 300, 'vx': vx,
            'name': 'KCRESCENT', 'ss2': {'type': 24}}

def kghost(B, k):
    """Kuroko's object type 26 ($4C21C) [code]: animation 73 at his place, following him ($4C248: his x / y every frame)
    while his action is C C C C C's; its attack steps hit (an effect pinned to him: follow 1, ended with the move)"""
    rows = obj_rows(B, 17, play_anim(17, 73))
    return {'kind': 3, 'rows': rows, 'loop': None, 'end': [], 'react': 'knockdown', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 1, 'travel': 0,
            'name': 'KGHOST', 'ss2': {'type': 26, 'anim': 73}}

# Kuroko's flag (object type 27, $4C274) [code] + [meas: boomerang_ss2.py, /data/tmp/kuroko176/ss2]: the brawler's
# spawn.boomerang (bproj_t kind 4, fighter.c boom_update)
BOOM = dict(speed=N.s16(0x6BB26) / 256,           # vx = word $6BB26 (8 px a frame; back: the same, negated: $4C37A)
            spawn=99 + 8,                         # placed 99 px ahead ($4C2A8), shown after its first move: 107 [meas]
            range=220, catch=104,                 # $4C326 cmpi #220 (out), $4C3C0 cmpi #104 (back), both on |x + vx - his x|
            hover=N.s16(0x6BB28),                 # +$D6 = word $6BB28 (16): subq / bpl: 17 frames, then back
            held=1,                               # +$D6 = 1 at the catch ($4C400): 2 more frames in his hand ($4C42C)
            height=32,                            # y - 32 ($4C2B8)
            segs=2, gap=48, seg_min=64)           # 2 objects 40 (+$D4 48 / 96) behind it, never nearer him than 64 ($4EC50)

def boomerang_model(hit=None):
    """the flag's distance from its thrower per frame from its first shown frame (its phases, as fighter.c boom_update
    and SS2's routines): hit = the frame index of its hit (None: a whiff) -> (dists, the catch frame index)"""
    b = BOOM; x = b['spawn']; v = b['speed']; ph = 'out'; cnt = b['hover']; out = [x]; catch = None; t = 0
    while True:
        t += 1; nx = x + v
        if ph == 'out':
            if abs(nx) >= b['range']: x, v, ph = b['range'], 0, 'hover'
            else: x = nx
        elif ph == 'hover':
            cnt -= 1
            if cnt < 0: v = -b['speed']; x += v; ph = 'back'
        elif ph == 'back':
            if abs(nx) <= b['catch']: x, v, ph, cnt, catch = b['catch'], 0, 'held', b['held'], t
            else: x = nx
        else:
            cnt -= 1
            if cnt < 0: return out, catch
        if hit is not None and t == hit and ph == 'out': v, ph = 0, 'hover'
        out.append(x)

def kboomerang(B, k):
    """Kuroko's flag, 6 3 2 1 4 A (object type 27, $4C274) [code]: animation 19 of his table (4 steps with the attack
    record $B113: [-6][10][-4][4] x 4 px, then a held step without one: live 15 frames, the out leg) 32 px up; it flies out
    8 px a frame from 107 px ahead to 220 px from him ($4C2F8), hovers 17 frames ($4C358), flies back at 8 px ($4C398) to
    104 px from him: the catch (his +$D4: his routine goes on), 2 more frames, gone ($4C410). Its hit ($31478[27] =
    $4C47E) or clash ($316E8[27] = $4C440): stopped where it is, the hover again with its count, then back. Its attack
    is spent by its first hit (+$102 bit 7 survives its steps; cleared only by a new animation, which never comes) and
    its animation holds its last step (no attack record) from the 16th frame on: SS2's flag hits only on its way out
    [meas: /data/tmp/kuroko176/ss2 back.json: P2 put in its return path, not hit]. Kuroko out of the move: gone at once
    ($4C434). The pole: 2 segments (effect objects 40, $4E72E: animation 23) 48 / 96 px behind it, never nearer him than
    64 px ($4EC50)"""
    b = BOOM
    rows = obj_rows(B, 17, play_anim(17, 19), 0, 0, b['height'])
    seg = obj_rows(B, 17, play_anim(17, 23)[:1], 0, 0, b['height'])
    segd = {'kind': 5, 'rows': [r[:3] + [None, None] for r in seg], 'loop': 0, 'end': [], 'react': 'knockdown', 'hit_kind': 1,
            'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0, 'travel': 0,
            'name': 'KFLAGPOLE', 'ss2': {'type': 40, 'anim': 23}}
    return {'kind': 4, 'rows': rows, 'loop': len(rows) - 1, 'end': [], 'react': 0, 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': b['spawn'], 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 128, 'follow': 0, 'travel': b['range'],
            'vx': b['speed'], 'name': 'KFLAG', 'boom': dict(b, seg=segd),
            'ss2': {'type': 27, 'anim': 19, 'pole': 23}}

def wind(B, k):
    """Genjuro's object 27 ($43A3C[27] = $4DAF8) in its first phase [code]: animation 38 then 39 (looping) of his table,
    re-placed every frame at its +$D4 = the caught opponent + (0, 48 up) ($4DB6E): the card wind around the victim,
    until his stage 1 (+$D8, $56272): pinned to the caught victim (follow 16), ended by P_FXOFF at his spin"""
    first = play_anim(12, 38); cyc = play_anim(12, 39)
    rows = obj_rows(B, 12, first + cyc, 0, 0, 48)
    return {'kind': 3, 'rows': rows, 'loop': len(first), 'end': [], 'react': 'knockdown', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 1 | 16, 'travel': 0,
            'name': 'WFTWIND', 'ss2': {'type': 27, 'anims': [38, 39]}}

def wind2(B, k):
    """object 27's second phase ($4DB4A): animation 32 placed once at its thrower + (80 forward, 64 up), ended by its
    animation's end ($4EC98); he hangs still meanwhile: pinned to him, ended at its last row (follow 3)"""
    rows = obj_rows(B, 12, play_anim(12, 32), 80, 0, 64)
    return {'kind': 3, 'rows': rows, 'loop': None, 'end': [], 'react': 'knockdown', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 3, 'travel': 0,
            'name': 'WFTCARDS', 'ss2': {'type': 27, 'anim': 32}}

def bakuen(B, v):
    """Hanzo's fire (6 3 2 1 + S), object type 6 ($30568) [code]: 12 px ahead on the floor ($2B77E), animation / next
    animation $305BE[b] (242 / 282, 243 / 283, 236 / 286: a flame arc, its attack steps 1-5) and effect 13 (anim 237, the
    burst) where it stands; each time its animation ends ($305EA: +$FA) it moves 80 px on, effect 13 again, the two
    animations swapped; off screen ($2B992) it is gone; a hit ($30624): the victim's place on the floor, anim 244 (the fire
    columns) to its end. The brawler: the rows of both animations (the second 80 px on), the loop repeating them 160 px
    on (wrap), the burst as its trail (child) born where each animation starts; its end rows where it hit"""
    a, b = N.u16(0x305BE + 4 * v), N.u16(0x305BE + 4 * v + 2)
    ra, rb = play_anim(2, a), play_anim(2, b)
    assert len(ra) == len(rb)
    rows = obj_rows(B, 2, ra, 12.0) + obj_rows(B, 2, rb, 92.0)
    endr = [[r[0], 0, 0] for r in obj_rows(B, 2, play_anim(2, 244))]
    burst = obj_rows(B, 2, play_anim(2, 237))
    child = {'kind': 3, 'rows': [r[:3] + [None, None] for r in burst], 'loop': None, 'end': [], 'react': 'knockdown',
             'hit_kind': 1, 'follow': 0, 'births': [0, len(ra), 2 * len(ra)], 'dx': 0, 'dy': 0, 'name': 'BAKUENFX'}
    return {'kind': 1, 'rows': rows, 'loop': 0, 'wrap': 160, 'end': endr, 'react': 'knockdown', 'hit_kind': 1,
            'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0, 'child': child, 'hits': {}, 'sig': 0, 'follow': 0, 'travel': 300,
            'vx': 80 / len(ra), 'name': 'BAKUEN', 'ss2': {'type': 6, 'anims': [a, b], 'burst': 237, 'end': 244}}

def wftflame(B, k):
    """Hanzo's rage move's flame, object type 7 ($306EC) [code]: 105 px ahead ($30704), anim 293 (the fire running on the
    floor), at its end anim 294 (the flame column: attack steps 1, 3, 5, 7) ($3071E), at its end gone ($3073A); its hit
    ($30752): the backdrop (0, 0, 4) = $0002 for 48 frames ($2B9DE, $6A9EA) and the victim's weapon lost (+$B8: not
    modelled); the hit is SS2's big hit (BIGHIT: the victim held, then the slow motion) [meas: P2's anim 124 held 78
    frames, his 292 lasts 128 frames for its 74]"""
    rows = obj_rows(B, 2, play_anim(2, 293) + play_anim(2, 294), 105)
    return {'kind': 3, 'rows': rows, 'loop': None, 'end': [], 'react': 'knockdown', 'hit_kind': 1, 'spawn_row': 0,
            'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0, 'travel': 0, 'away': True,
            'name': 'WFTFLAME', 'ss2': {'type': 7, 'anims': [293, 294]}}   # away: its victim thrown on away from him [meas:
                                                                       # cap_mozu.json close_rage_wft, P2 at 43 / 147 px]

def loop_frames(ch, a, n):
    """[(a, step)] for n frames of a looping animation (its last step's end command 'loop') as SS2 shows it [meas:
    shuriken_ss2.py, the shuriken's 265 in flight: steps 0-6 two frames each, step 7 one, then step 0 three, 1-6 two,
    7 one, ...]: the loop's step shows one frame less, the first step one more from the second pass on (the cycle keeps
    its length)"""
    st = ss2.parse_anim(ch, a, 400); out = []; again = False
    while len(out) < n:
        for i, s_ in enumerate(st):
            out += [(a, i)] * (s_['ticks'] + 1 - (i == len(st) - 1) + (i == 0 and again))
        again = True
    return out[:n]

SHURIKEN_DROP = 320                               # px the flight's rows reach below its spawn (a jump's height + more)
def shuriken(B, v):
    """Hanzo's air special's shuriken, object type 5 ($30396) [code] + [meas: shuriken_ss2.py, /data/tmp/hz211]:
    born at his place + (12 forward, 31 up) ($2B77E with $303C2 / $303C6), animation $303FA[b] = 265 (8 steps of 2
    frames: the spinning star, its attack box on steps 1-7, looping as SS2 loops: loop_frames); velocity $46BAE($30400[b]) = entry 30 / 32 / 34
    ((192, 1024) / (192, 1104) / (192, 960): 0.75 px forward, 4.0 / 4.3 / 3.75 px down a frame) and the next entry's
    pair as its acceleration +$D0 / +$D2 ((67, 28) / (67, 7) / (67, 3) / 256 px a frame); every frame v += a, then
    p += v (8.8, its spawn frame too: the first frame shows it moved once). Routine $30404: a hit ($C670) -> $30504
    (gone; SS2's blood is its generic hit effect: the brawler's own hit effect here); on the floor (y >= 224, tested
    before the move: one frame shows it below the floor) -> anim 269 (stuck in the floor, no box) at 224 in place
    ($30458: its 2 frames), then +$22 = $80 / +$24 = 60 ($3047A): shown on frames 0-3 of the floor, then every other
    frame, gone at frame 62 (+$112 cleared: the next shuriken may fly). The victim: class 3 action 1 (anim 104, the
    light standing reel). The brawler: 'air' rows (heights from his height at the spawn: an air projectile, fighter.c
    proj_row), its floor phase as 'next' (fighter.c proj_update: started where the flight reached the floor)"""
    a = N.u16(0x303FA + 2 * v); e = N.u8(0x30400 + v) + 16
    (vx, vy), (ax, ay) = vtab(2, e), vtab(2, e + 1); v0 = [vx, vy]
    sx, sy = N.s16(0x303C2), N.s16(0x303C6)             # (12, -31): forward, down
    anim = loop_frames(2, a, 250)
    X, Y, rows = sx << 8, sy << 8, []
    while True:
        vx += ax; vy += ay; X += vx; Y += vy
        f_, i_ = anim[len(rows)]
        r = obj_rows(B, 2, [(f_, i_)])[0]
        rows.append([r[0], X >> 8, -(Y >> 8)] + r[3:])
        if (Y >> 8) > SHURIKEN_DROP or len(rows) >= 250: break
    fl = obj_rows(B, 2, [(269, 0)] * 62)
    floor = [[0xFFFF if k > 3 and k % 2 == 0 else r[0], 0, 0, None, None] for k, r in enumerate(fl)]
    nxt = {'kind': 1, 'rows': floor, 'loop': None, 'end': [], 'react': 0, 'hit_kind': 1, 'spawn_row': 0, 'spawn_x': 0,
           'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0, 'travel': 0, 'name': 'SHURIKENFL'}
    return {'kind': 1, 'rows': rows, 'loop': None, 'end': [], 'react': 0, 'hit_kind': 1, 'spawn_row': 0, 'spawn_x': 0,
            'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0, 'travel': 300, 'air': True, 'next': nxt,
            'name': 'SHURIKEN', 'ss2': {'type': 5, 'anim': a, 'floor': 269, 'v': v0, 'a': [ax, ay]}}

def mozufire(B, k):
    """Mozu Otoshi's slam: effect 14 ($4509A) [code]: Hanzo's anim 244 (the fire columns) where he lands, sound $14D,
    gone at its end; no box (the blow is the victim list's)"""
    rows = obj_rows(B, 2, play_anim(2, 244))
    return {'kind': 3, 'rows': [r[:3] + [None, None] for r in rows], 'loop': None, 'end': [], 'react': 'knockdown',
            'hit_kind': 1, 'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0, 'child': None, 'hits': {}, 'sig': 0, 'follow': 0,
            'travel': 0, 'name': 'MOZUFIRE', 'ss2': {'effect': 14, 'anim': 244}}

OBJECTS = {'kclone': kclone, 'shuriken': shuriken, 'bakuen': bakuen,'wftflame': wftflame, 'mozufire': mozufire, 'kboomerang': kboomerang, 'wind': wind, 'wind2': wind2, 'tornado': tornado, 'crescent': crescent, 'cards': cards, 'kparody': kparody, 'kcrescent': kcrescent, 'kghost': kghost}

# ---- a special -> export96 layout --------------------------------------------------------------------------------------
def rom_steps(B, ch, a, flags, react, catch=False, grab=None):
    import export_ss2 as X
    st = X.anim_steps(B, ch, *a) if isinstance(a, tuple) else X.anim_steps(B, ch, a)
    for i, s in enumerate(st):
        s['flags'] |= flags.get(i, 0)
        if grab: s['boxes'] = dict(s['boxes'], **{'11': list(grab)}); s['flags'] |= 0x100
        if react and s['flags'] & 0x100: s['react'] = react
        if catch and s['flags'] & 0x100: s['catch'] = True
    if len(st) > 1:
        st[0]['ticks'] += 1                           # the start frame shows the first step (see the module doc)
        if st[-1]['ticks']: st[-1]['ticks'] -= 1      # +$FA on the last step's last frame: the brawler's PF_END comes
        else: st[-1]['flags'] |= 0x80                 # a frame after it; a 0-tick last step: its event (end_ev)
    return st

def openings(steps):
    out, prev = [], None
    for s in steps:
        atk = bool(s['flags'] & 0x100)
        out.append(atk and not (prev is not None and prev['flags'] & 0x100 and prev['flags'] & 0x4000))
        prev = s
    return out

def special(B, ch, name, inp, vdef=None):
    """vdef None: the special with its variant table (A / B / A+B), the heaviest played by default; vdef k: version k
    alone as its own special (input version_input, condition 'version': the Character Lab's piece, never in the game's
    pool unless a roster slot names it)"""
    fn, nv, results = SPECIALS[name][inp]
    CUR['ch'] = ch
    full = [fn(v) for v in range(nv)]
    progs = [r[:2] for r in full]
    vlists = full[-1][2] if len(full[-1]) > 2 else []
    vrows = [r[2] if len(r) > 2 else [] for r in full]   # each row's (export_bm.vl_row picks the row the roster plays)
    comp = [compile_prog(e) for e, _ in progs]
    asm = [assemble(o) for o, _ in comp]
    assert all(len(x) == len(asm[0]) for x in asm), (name, inp, [len(x) for x in asm])
    enc = [[encode(o) for o in x] for x in asm]
    default = nv - 1 if vdef is None else vdef        # the heaviest button: A+B (export_dd's rule); a version: its own
    cols, prims = [], []
    for pos in range(len(enc[0])):
        ops_ = [e[pos] for e in enc]
        assert all(o[:3] == ops_[0][:3] for o in ops_), (name, inp, pos, ops_)
        if len({o[3] for o in ops_}) > 1:
            cols.append([o[3] for o in ops_]); o = ops_[default]
            prims.append((o[0] | 0x80, o[1], len(cols) - 1, o[3]))
        else: prims.append(ops_[default])
    states, anims_d, objects, nh = [], {}, [], []
    for v, ((ents, objs), (_, sts)) in enumerate(zip(progs, comp)):
        h = 0
        for j, (ei, a) in enumerate(sts):
            k = f'{v}:{j}:{a}'; states.append(k)
            steps = rom_steps(B, ch, a, ents[ei]['flags'], ents[ei]['react'], ents[ei].get('catch') is not None, ents[ei].get('grab'))
            anims_d[k] = {'mode': 'hold', 'steps': steps, 'ss2': a}
            h += sum(openings(steps))
        nh.append(h)
        objects += [OBJECTS[o](B, ov) for o, ov in objs]
    nstate = len(comp[0][1]); nobj = len(progs[0][1])
    assert all(len(s) == nstate for _, s in comp)
    each = [max(1, SPECIAL_DAMAGE // max(1, n)) for n in nh]
    vdmg = 0
    if nv > 1:
        cols.append(each); vdmg = len(cols)
    # P_ANIM's operand: damage | reaction << 8 (the entry's react, else the last hitting state knocks down)
    sts0 = comp[default][1]; ents0 = progs[default][0]
    hitting = [j for j, (ei, a) in enumerate(sts0) if any(openings(anims_d[f'{default}:{j}:{a}']['steps']))]
    def pa(p):
        j = p[1]; ei = sts0[j][0]
        react = ents0[ei]['react'] or (R_KNOCKDOWN if hitting and j == hitting[-1] else R_HEAVY)
        return (p[0], p[1], each[default] | react << 8, None)
    prims = [pa(p) if p[0] == P['anim'] else p for p in prims]
    # the brawler's player on the default row: length, apex, last hit (bspec_t inv_rows), the script for the Lab
    anims_l = [{'steps': anims_d[s]['steps'], 'hold': True} for s in states]
    pl = Play(prims, anims_l, [v for row in zip(*cols) for v in row] if cols else None, default, len(cols), nstate)
    for a_, o_ in enumerate(objects[default * nobj:(default + 1) * nobj]):
        if o_['kind'] == 4: pl.sig_after[a_] = boomerang_model()[1]   # alone: its whiff's catch
    rows = []
    while len(rows) < 600:
        r = pl.frame()
        if r is None: break
        rows.append(r)
    script = [[anims_l[r[0]]['steps'][r[1]]['frame'], int(r[2]), int(r[3]), []] for r in rows] or [[0, 0, 0, []]]
    rb = [anims_l[r[0]]['steps'][r[1]]['boxes'] for r in rows] or [{}]
    rs = [[r[0], r[1], anims_l[r[0]]['steps'][r[1]]['flags'], 0xFF] for r in rows] or [[0, 0, 0, 0xFF]]
    opens = [i for i, r in enumerate(rows) if (i == 0 or rows[i - 1][:2] != r[:2]) and openings(anims_l[r[0]]['steps'])[r[1]]]
    snd = []                                           # the step sounds ($08 / $0C: id, the middle pan) by frame, as played
    spawn_snd = [o[1] for e in ents0 for c in e['conds'] if len(c) > 2 for o in c[2] if o[0] == 'snd']
    for (srow, a_, x_) in pl.spawns[:1]:               # a routine's own send with its spawn (Kuroko's parodies)
        snd += [[srow, i_] for i_ in spawn_snd]
    for i, r in enumerate(rows):
        if i and rows[i - 1][:2] == r[:2]: continue
        a_ = anims_d[states[r[0]]]['ss2']
        st = ss2.parse_anim(ch, a_[0], 400)[a_[1] + r[1]] if isinstance(a_, tuple) else ss2.parse_anim(ch, a_, 400)[r[1]]
        snd += [[i, c[1] + (1 if c[0] == 'sound_pan' else 0)] for c in st['cmds'] if c[0] in ('sound', 'sound_pan')]
    # the states its whiff never reaches (a connect's: Genjuro's WFT spin, anim 24, one word of his line on each of its
    # five slashes, $20B-$20F = $1AC8-$1ACC; feedback 20261009-224005-b3f3): their steps' own voices ($08 / $0C with a
    # fighter id >= $100, voices.py's rule; the driver word) ride the steps (export_bm step_voiced -> bspec_t.pvox,
    # fighter.c pan_voices: sent as the program enters the step, where SS2 sends them); the whiff's stay timed by its
    # frames (voice_frames, voices.py 'special' uses)
    # (+ the routine's own sends as a state starts, E voice: Genjuro's last word $206 = $1ACE as the fall starts)
    seen = {r[0] % nstate for r in rows}; code_voices = []
    for s in states:
        v_, j_ = map(int, s.split(':')[:2])
        if j_ in seen: continue
        code = progs[v_][0][comp[v_][1][j_][0]]['voice']
        if v_ == default: code_voices += [[s, 0, i] for i in code]   # (voices.py list: in the fighter's bank)
        for k_i, s_ in enumerate(anims_d[s]['steps']):
            a_, k_ = s_['ss2']
            ids = (code if k_i == 0 else []) + [c[1] + (1 if c[0] == 'sound_pan' else 0) for c in ss2.parse_anim(ch, a_, 400)[k_]['cmds'] if c[0] in ('sound', 'sound_pan')]
            vs = [N.u16(0x5FD2 + 2 * i) for i in ids if i >= 0x100]
            if vs: s_['voices'] = vs
    apex = max(range(len(rows)), key=lambda i: rows[i][3]) if rows else 0
    pj = []
    for (srow, a, x) in pl.spawns:
        o = objects[default * nobj + a]
        if o['kind'] == 1: pj.append(dict(o, spawn_row=srow, spawn_x=x))
    parts = sorted({e['part'] for e in ents0 if e['part'] is not None})
    rom = {'states': states, 'anims': anims_d, 'prims': [list(p) for p in prims], 'objects': objects, 'openings': {},
           'hit_kind': 1, 'last_hit': opens[-1] if opens else -1, 'apex': apex if rows and rows[apex][3] > 0 else -1,
           'length': len(rows), 'voice_frames': True,
           'vtable': {'rows': [list(r) for r in zip(*cols)] if cols else [], 'ncol': len(cols), 'nvar': nv if nv > 1 else 0,
                      'default': default, 'vanim': nstate, 'vobj': nobj, 'vdmg': vdmg,
                      'buttons': ['A', 'B', 'AB'][:nv] if inp[-1] != 'K' else ['C', 'D', 'CD'][:nv], 'results': list(results),
                      'hits': nh}}
    if vlists: rom['vlists'] = vlists                 # the caught victim's lists (VL), P_VSIG steps through them
    if vlists and any(v != vlists for v in vrows): rom['vlists_rows'] = vrows
    import commands_ss2 as K
    if K.descriptor(ch, 0, 1, results[default])['b'][0] & 0x80: rom['nopush'] = True   # descriptor byte 4 bit 7 -> +$FF:
                                                       # no push between the players ($CC14) while it plays [code]
    if (name, inp) in BIGHIT: rom['bighit'] = True        # its connect: SS2's big-hit pause (export_bm SF_BIGHIT)
    if (name, inp) in BIGHIT_COL: rom['bighit_col'] = BIGHIT_COL[(name, inp)]
    rom['now'] = True                                  # its program's first frame = the special's first (export_bm SF_NOW:
                                                       # SS2's action routine runs in the frame the action is set; TODO #191)
    if parts:                                          # follow-ups (the slash chain): its parts, the press 'again'
        rom['parts'] = [{'states': [states[j] for j, (ei, a) in enumerate(sts0) if ents0[ei]['part'] == p]} for p in parts]
        rom['follow_links'] = [{'from': p, 'to': p + 1, 'input': 'again'} for p in parts[:-1]]
        rom['links'] = ['again']
    cond = 'version' if vdef is not None else 'lab' if (name, inp) in LAB_ONLY else 'normal'
    return {'input': inp if vdef is None else version_input(inp, vdef, nv), 'condition': cond, 'version': 'whiff', 'script': script,
            'name': NAMES.get(name, {}).get(inp), 'base_input': inp, 'row_boxes': rb, 'row_steps': rs,
            'marks': [''] * len(script), 'projectiles': pj, 'anims': [a for _, a in sts0],
            'shape': [max(r[1] for r in script), max(r[2] for r in script), bool(pj)], 'game_hits': len(opens),
            'rom': rom, 'ss2': {'results': list(results), 'sounds': snd, 'code_sounds': spawn_snd, 'code_voices': code_voices},
            **({'air': True} if inp.startswith('j.') else {})}   # an air special (j.: export_bm air_special, TODO #211)

# ---- the Character Lab's LAB special (export96.lab_special's SS2 twin): EVERY animation of the fighter's dictionary
# (tools/brawler/arb_pieces/<f>.json "anims": its $NN = the SS2 animation number) as one special of his pool, each
# animation played on its own as the brawler plays an animation (rom_steps: its steps, boxes, the start frame's extra
# tick), its hits SPECIAL_DAMAGE split over its openings; one program block per animation, [P_LANIM j, P_RESUME, P_BR
# end yield, P_END], so the game starts animation j at op 4 j (fighter.c "Lab: try in game"). Only the Lab's builds
def lab_special(B, ch, entries):
    """entries [(hex id, animation number)] -> (the LAB special, the ids it could not read)"""
    import export_ss2 as X
    have = set(B.pals)                                # the palette keys his game export already draws with: an animation
    def raw_pals(a):                                  # needing another one is left out (the brawler loads 8 per fighter:
        out = set()                                   # export_ss2.pack_palettes must fold them all; one flicker palette)
        for s_ in ss2.parse_anim(ch, a, 400):
            for li, w in enumerate(s_['layers']):
                byc = {}
                for col in ss2.sprite_cells(w & 0x7FFF)[1]:
                    for c in col:
                        if not c: continue
                        t, at = c; code = t | (at >> 4 & 0xF) << 16
                        if code: byc.setdefault((at ^ (w >> 15)) >> 8, set()).add(code)   # (drawn cells; Builder.layer's keys)
                out |= {X.flicker_key(ch, p, cs) if li == 1 else p for p, cs in byc.items()}
        return out
    anims, states, ids, prims, bad = {}, [], [], [], []
    for x, a in entries:
        try:
            extra = raw_pals(a) - have
            if extra: raise ValueError(f'palettes {sorted(extra)} beyond the 8 the fighter keeps')
            st = rom_steps(B, ch, a, {}, None)
            if not st: raise ValueError('no steps')
        except Exception as e:
            bad.append((x, str(e)[:60])); continue
        o = sum(openings(st))
        k = f'L{len(states)}:{a}'; anims[k] = {'mode': 'hold', 'steps': st, 'ss2': a}
        prims += [[P['lanim'], max(1, SPECIAL_DAMAGE // o) if o else 0, R_KNOCKDOWN if o else R_HEAVY, len(states) << 8],
                  [P['resume'], 0, 0, 0], [P['br'], PC['end'], -1, 0], [P['end'], 0, 0, 0]]
        states.append(k); ids.append(int(x, 16))
    s0 = anims[states[0]]['steps']
    rom = {'states': states, 'anims': anims, 'prims': prims, 'objects': [], 'openings': {}, 'hit_kind': 1, 'last_hit': -1,
           'apex': -1, 'length': 0, 'vtable': {}, 'lab': True, 'lab_ids': ids, 'now': True}
    return {'input': 'LAB', 'condition': 'normal', 'version': 'whiff', 'script': [[s0[0]['frame'], 0, 0, []]], 'row_boxes': [{}],
            'row_steps': [[0, 0, 0, 0xFF]], 'marks': [''], 'projectiles': [], 'anims': [ids[0]], 'shape': [0, 0, False],
            'game_hits': 0, 'rom': rom, 'ss2': {'results': [], 'sounds': [], 'code_sounds': [], 'code_voices': []}}, bad

# decoded but not exported (none since 2026-10-07: Kuroko's 10 palettes fit the brawler's 8 by export_ss2.pack_palettes)
NOT_EXPORTED = {}

def specials(B, ch, name, versions=False):
    """the fighter's specials (variant tables); versions: then each button version of a multi-button one as its own
    special (special vdef: the Character Lab's pieces)"""
    out = [special(B, ch, name, inp) for inp in SPECIALS[name] if inp not in NOT_EXPORTED.get(name, ())
           and (versions or (name, inp) not in LAB_ONLY)]   # (the Lab-only ones: never drawn into the game's export)
    if versions:
        out += [special(B, ch, name, inp, k) for inp, (_, nv, _) in SPECIALS[name].items()
                if inp not in NOT_EXPORTED.get(name, ()) and nv > 1 for k in range(nv)]
    return out

# ---- throws ------------------------------------------------------------------------------------------------------------
# class 4 action -> (the thrower's animation, the victim's class 5 action): Haohmaru close + forward + A+B (action 1:
# the slash throw, anim 274) and + D / C+D (2 / 3: the kick throw, anim 346); Genjuro: the slash throw for all three
# (descriptors $28310 class 4: $2E38C / $2D420 / $2E3A4 + $2D1EC) [code]
THROWS = {'haohmaru': {'throw_c': (274, 1), 'throw_d': (346, 2)}, 'genjuro': {'throw_c': (274, 1), 'throw_d': (274, 1)},
          'kuroko': {'throw_c': (27, 1), 'throw_d': (27, 1)},   # Kuroko: one throw (class 4 actions 0-3: anim 27)
          'hanzo': {'throw_c': (274, 1, 1), 'throw_d': (346, 2, 2)}}   # Hanzo (TODO #193): the slash throw then his leap
                                                # back (class 4 action 1's list goes on: throw_leap), the kick throw

# the thrower's leap after the throw (Hanzo's class 4 action 1, list $2CD7C [code]): $2CD4C the animation's end -> next;
# anim 34 $2CD54: the body moved by its step's offset ($2B7D0), next; $46BAA (param $8878): vx / vy from the fighter's table
# (entry $78 + 16: 4 px back, 12.5 up), gravity, next; $2CD60: 34's end -> next; anim 38 $2CD68: the apex -> next;
# $2CD74: landed -> the landing (class 0 action 18, anim 178). Measured (moves/02.json close_throw_6ab): 274 to frame
# 63, 34 from 64, the leap from 66 (the throw's slow motion moves him every other frame for 10 frames: not modelled),
# 38 at the apex, landed at 115 176 px behind, 178 to 131. The height x FIT_TOP / its apex (TODO #185's rule, SS2's camera
# follows him 134 px up), the same timing
LEAP = (0x2CD4C, 0x2CD54, 0x46BAA, 0x2CD60, 0x2CD68, 0x2CD74)
FIT_TOP = 64

def throw_leap(ch, sub, a, B):
    """the thrower's rows after its throw animation [(frame, x forward, height)], [] when its list ends with it"""
    import commands_ss2 as K, export_ss2 as X
    ents = K.descriptor(ch, 0, 4, sub)['entries']
    k0 = next(i for i, (_, h, w) in enumerate(ents) if not w & 0x8000 and w & 0x3FF == a)
    rest = [h for _, h, w in ents[k0 + 1:k0 + 1 + len(LEAP)]]
    if tuple(rest) != LEAP: return []
    up, fall, word = ents[k0 + 2][2] & 0x3FF, ents[k0 + 5][2] & 0x3FF, ents[k0 + 3][2]
    vx, vy = vtab(ch, (word & 0xFF) + 16)
    q = min(1.0, FIT_TOP / ((vy / 256) ** 2 / (2 * GRAVITY / 256))); vy = round(vy * q); g = GRAVITY * q
    seq = lambda an: [(an, i) for i, s_ in enumerate(ss2.parse_anim(ch, an, 400)) for _ in range(s_['ticks'] + 1)]
    su, sf = seq(up), seq(fall)
    mv = next((c[1] for c in ss2.parse_anim(ch, up, 400)[0]['cmds'] if c[0] == 'move'), 0)
    x, y, vxf, vyf, out, n, cur, k = float(mv), 0.0, 0.0, 0.0, [], 0, su, 0
    fr = lambda an, i: B.frame(ss2.parse_anim(ch, an, 400)[i])
    while True:
        if n >= 2: x += vxf; y -= vyf                  # SS2: the frame's move with the velocities it starts with
        if n == 1: vxf, vyf = vx / 256, vy / 256        # $46BAA's frame: the velocities set, the move from the next
        elif n >= 2: vyf += g / 256                     # the dispatcher's gravity
        if n >= 2 and y < 0 and vyf > 0: break          # landed (y past the floor)
        if cur is su and k >= len(su): cur, k = sf, 0  # 34's end -> 38
        if cur is sf and k >= len(sf): k = len(sf) - 1
        an, i = cur[k]; out.append((fr(an, i), round(x), max(0, round(y)))); k += 1; n += 1
    land = seq(178)
    out += [(fr(an, i), round(x), 0) for an, i in land]
    return out


def victim_list(ch, sub):
    """the victim's class 5 action `sub` entries: the THROWER's list ($28310 class 5 of its character: Haohmaru thrown by
    Genjuro plays Genjuro's 514 with Genjuro's velocity entry $8843 [meas: the captures close_throw_*]) [code]"""
    import commands_ss2 as K
    d = K.descriptor(ch, 0, 5, sub)
    return [(h, w) for _, h, w in d['entries']]

def throw(B, ch, name, key):
    """a throw as a paired script read from the ROM [code]:
    thrower: its animation to the end ($2D420: the end -> neutral, the body moved by the last step's offset): the
      control return = that frame;
    victim (class 5, the action of the throw, descriptor list): $2E2FE its thrown animation (the thrower's character's
      own frames for it here) placed by its steps' $20 offsets from the thrower's place, to its end; $2E30A the body
      moved by the last offset, the flight animation 220; $2E316 / $2E338 + $46B90: vx / vy from the THROWER's table
      (the entry word's low byte + 16), gravity; landed ($2E322 / $2E344) -> the next (a bounce: another velocity,
      animation 220) or 222, lying ($2E35A); then the get-up.
    Impacts: the thrower's step with the cut (its second sound: $111 / $110 / $210, after the grab's $024) and every landing."""
    a, sub = THROWS[name][key][:2]
    ents = victim_list(ch, sub)
    tst = ss2.parse_anim(ch, a, 100)
    tl = []
    for i, s in enumerate(tst): tl += [i] * (s['ticks'] + 1)
    tl += [tl[-1]]                                    # +$FA's frame: the routine ends the throw the next frame
    import export_ss2 as X
    th_steps = X.anim_steps(B, ch, a, mirror=True)       # the thrower turned on the steps SS2 draws mirrored
    timeline = [[th_steps[i]['frame'], 0, 0, 0] for i in tl]
    snd = [i for i, s in enumerate(tst) if any(c[0] == 'sound' for c in s['cmds'])]
    cut = snd[1]                                      # the cut: the step of its second sound (the first, $024: the grab)
    impacts = [tl.index(cut)]
    rows = []; x = y = 0.0; vx = vy = 0.0; lastmv = (0, 0); land = None; rel = None; fa = 220
    vt = lambda w: vtab(ch, (w & 0xFF) + 16)
    def flight_row(n):
        if fa == 220: return [-1, round(x), round(y), 1, 0, f'220.{min(n, 1)}', 'knockdown_flight']
        fs = ss2.parse_anim(ch, fa, 100); seq = [i for i, s in enumerate(fs) for _ in range(s['ticks'] + 1)]
        i = seq[min(n, len(seq) - 1)]
        return [B.frame(fs[i]), round(x), round(y), 1, 0, f'{fa}.{i}', None]
    k = 0
    while k < len(ents):
        h, w = ents[k]
        if h == 0x2E2FE:                              # the thrown animation, placed by its steps' offsets, to its end
            va = w & 0x3FF
            vs = ss2.parse_anim(ch, va, 100)
            for i, s in enumerate(vs):
                mv = next(((c[1], c[2]) for c in s['cmds'] if c[0] == 'move'), (0, 0))
                for _ in range(s['ticks'] + 1):
                    rows.append([B.frame(s), mv[0], -mv[1], 1, 0, f'{va}.{i}', None]); lastmv = mv
            rows.append(rows[-1][:])                  # +$FA's frame
            k += 1
        elif h == 0x2E30A:                            # the flight animation, the body moved by the last offset
            x += lastmv[0]; y += -lastmv[1]
            fa = w & 0x3FF; k += 1
        elif h in (0x2E316, 0x2E338):                 # a velocity from the thrower's table, gravity, to the landing
            wvx, wvy = vt(w); vx, vy = wvx / 256, -wvy / 256
            if rel is None: rel = len(rows)
            if k + 1 < len(ents) and not ents[k + 1][1] & 0x8000 and h == 0x2E338: fa = ents[k + 1][1] & 0x3FF
            n = 0
            while True:
                if n: vy -= GRAVITY / 256
                x += vx; y += vy
                if y <= 0: y = 0
                rows.append(flight_row(n)); n += 1
                if y <= 0 and vy < 0: break
            impacts.append(len(rows) - 1); land = land if land is not None else len(rows) - 1
            k += 2                                    # the velocity entry and its landing wait
        elif h == 0x2E35A:                            # lying (222) to its end
            ln = sum(s['ticks'] + 1 for s in ss2.parse_anim(ch, 222))
            rows += [[-1, round(x), 0, 1, 0, '222.1', 'down'] for _ in range(ln)]
            k += 1
        else: k += 1
    if len(THROWS[name][key]) > 2:                    # the thrower's own leap after it (throw_leap): its rows, the
        lp = throw_leap(ch, THROWS[name][key][2], a, B)   # victim's offsets made relative to where the thrower is
        timeline += [[f_, x_, y_, 0] for f_, x_, y_ in lp]
        for i, r in enumerate(rows):
            t = timeline[min(i, len(timeline) - 1)]; r[1] -= t[1]; r[2] -= t[2]
    ret = len(timeline)
    anim = {'slot': a, 'mode': 'hold', 'steps': th_steps}
    return {'slot': a, 'inputs': 'close + forward + ' + ('A+B' if key == 'throw_c' else 'D / C+D'), 'table': [], 'hold': False,
            'rom': True, 'timeline': timeline, 'victims': {name: rows}, 'impacts': sorted(set(impacts)),
            'release': rel, 'land': land, 'ret': ret, 'anim': anim, 'ss2': {'anim': a, 'victim_action': sub},
            'turned': bool(tst[0]['flags'] & 0x8000),          # the grab drawn turned: the victim behind him (export_bm hold_rows)
            # the brawler's hold (TODO #188 a): SS2 has none (its throw swaps the victim behind the thrower on its first
            # frame and is over in ~50); a hold drawn that way kept both swapped for seconds ("reverse orientation"). The
            # hold is SS2's grab picture mirrored: this step unturned, the victim in front facing him; forward / back + A
            # then plays the throw from its first row (the swap) exactly as SS2
            'grab_frame': B.frame(tst[0], mirror=False) if tst[0]['flags'] & 0x8000 else None}

# ---- the victim's size: SS2's other throws (Character Lab 2026-10-10, Bruno: "special regular throws against
# EARTHQUAKE, who is too big to be thrown") [code] -------------------------------------------------------------------
# The throw test ($2C5A8, every frame both players are close, NAGE1 task $2C722): the thrower's +$108 = the buttons just
# pressed ($26B16[+$EB >> 4]: A 1, B 2, A+B 3, C 4, D 5, C+D 6), a ground throw takes B / A+B / D / C+D ($2C6A8), with
# the stick toward or away (+$E9 & 12), within word $2FFA40[thrower] px (Hanzo 62, Earthquake 72) of the opponent, both
# standing. Then $2C75C: the thrower's class 4 action = 4 when the VICTIM's character (+$64) is 8 (Earthquake) or 17
# (Kuroko), else $2C852[+$108] (B 0, A+B 1, D 2, C+D 3); the victim takes class 5 with the same action. Air throws
# ($2C8D2: a thrower with an air table, $2CA42: Nakoruru, Hanzo, Galford, Sieger; both airborne, B / A+B): $2CB22
# (7 / 8) or, against Earthquake / Kuroko, $2CB2A (9 / 10). The same test picks the sword clash's action ($C2BE: 6 vs
# them, else 5). Every fighter's class 4 action 4 is the same handler ($2D420) on its anim 270 and every class 5
# action 4 the same victim list ($2DF6E ...): SS2's "too big to be thrown" throw is generic. Hanzo's air lists 9 / 10
# equal 7 / 8 (the big victim changes nothing in the air).
BIG_CHARS = (8, 17)                               # $2C770 / $2C778: Earthquake, Kuroko
BIG_ACTION = 4

def throw_big(B, ch, name):
    """the throw against a big victim (class 4 action 4 / class 5 action 4), a paired script [code]:
    thrower $2D420: its anim 270 to the end (the slide under him, then the rising kick: attack steps 3 and 9), then
      neutral (the body moved by the last step's offset);
    victim (its OWN animations, numbered alike for every character; Earthquake's table read here, his offsets): $2DF6E
      anim 474 (staggered, drawn 45 px in front: its steps' $20) to its end; $2DF7A anim 464 (falling back), the body
      moved by the offset; $2DF86 the push: vx / vy = words $6C7EE (4 px forward, 4 up: its facing is the thrower's, so
      away from him), gravity; $2DFAC landed; $2DFBE the bounce $6C7F2 (1.5 forward, 1 up); $2DFE0 anim 466 landed
      (+$FF bit 7: down); $2DFF8 anim 468 to its end; $2E36C / $2E37A lying $6C7F6 frames, the get-up.
    Impacts: the thrower's two attack steps (the slide, the kick), the landing"""
    import export_ss2 as X, commands_ss2 as K
    VC = BIG_CHARS[0]                                 # the victim class's own animations (Earthquake's)
    def fv(an, k):                                    # the victim's frame: the thrower's own drawing of that animation
        st_ = ss2.parse_anim(ch, an, 100)             # step (a fighter is its own victim in the export: throw())
        return B.frame(st_[min(k, len(st_) - 1)])
    a = K.descriptor(ch, 0, 4, BIG_ACTION)['entries'][0][2] & 0x3FF
    tst = ss2.parse_anim(ch, a, 100)
    tl = []
    for i, s_ in enumerate(tst): tl += [i] * (s_['ticks'] + 1)
    tl += [tl[-1]]
    th_steps = X.anim_steps(B, ch, a, mirror=True)
    timeline = [[th_steps[i]['frame'], 0, 0, 0] for i in tl]
    atk_steps = [i for i, s_ in enumerate(tst) if attack_recs(s_)]
    impacts = sorted({tl.index(i) for i in atk_steps if not i or not attack_recs(tst[i - 1])})
    rows = []; x = y = 0.0; last = 0
    for k, s_ in enumerate(ss2.parse_anim(VC, 474, 100)):   # staggered in front of him
        mv = next((c[1] for c in s_['cmds'] if c[0] == 'move'), 0); last = mv
        rows += [[fv(474, k), mv, 0, 1, 0, f'474.{k}', None] for _ in range(s_['ticks'] + 1)]
    rows.append(rows[-1][:])
    x = float(last)                                   # $2DF7A: moved by the offset
    fs = ss2.parse_anim(VC, 464, 100); seq = [i for i, s_ in enumerate(fs) for _ in range(s_['ticks'] + 1)]
    rel = len(rows); land = None
    for vxw, vyw, an in ((N.s16(0x6C7EE), N.s16(0x6C7F0), 464), (N.s16(0x6C7F2), N.s16(0x6C7F4), 466)):
        vx, vy = vxw / 256, -vyw / 256; n = 0
        while True:
            if n: vy -= GRAVITY / 256
            x += vx; y += vy
            if y <= 0: y = 0
            k = seq[min(n, len(seq) - 1)] if an == 464 else 0
            rows.append([fv(an, k), round(x), round(y), 1, 0, f'{an}.{k}', None]); n += 1
            if y <= 0 and vy < 0: break
        impacts.append(len(rows) - 1); land = land if land is not None else len(rows) - 1
    for an in (466, 468):
        for k, s_ in enumerate(ss2.parse_anim(VC, an, 100)):
            rows += [[fv(an, k), round(x), 0, 1, 0, f'{an}.{k}', 'down' if an == 468 else None] for _ in range(s_['ticks'] + 1)]
    return {'slot': a, 'inputs': 'close + forward / back + B / A+B / D / C+D against a big victim', 'table': [], 'hold': False,
            'rom': True, 'timeline': timeline, 'victims': {name: rows}, 'impacts': sorted(set(impacts)), 'release': rel,
            'land': land, 'ret': len(timeline), 'anim': {'slot': a, 'mode': 'hold', 'steps': th_steps},
            'ss2': {'anim': a, 'victim_action': BIG_ACTION, 'victim_class': [ss2.NAMES[c] for c in BIG_CHARS]},
            'turned': bool(tst[0]['flags'] & 0x8000), 'grab_frame': None, 'big': True}

AIR_TOP = 64                                      # px: the air throw's height in the brawler (FIT_TOP's rule)
def throw_air(B, ch, name, act=7):
    """the air throw (class 4 action 7: B, 8: A+B, the same frames: 309 / 341 are one picture; SNK's Kuutengeki, close
    + forward + B in the air) as a paired script [code]:
    thrower 0 $2D4D8 anim 295 (the grab and the roll), held in the air (+$EE = $80, velocities 0), the victim's entry
      kept equal to his (both lists step together); the end -> next   1 $2D50C: the drop: vy = word $6AA06[1] (16 px a
      frame down), its own gravity word 0 (0), next   2 $2D55A: landed -> effect 70, $8ACE = 3, velocities 0, next
      3 anim 309 / 341 (the slam, 6 frames)   4 anim 34 $2D5B6: the body moved by the offset, the hop: $6AA06[2] / [3]
      (3 px back, 10 up), gravity   5 the end -> next   6 the apex -> next   7 anim 38: landed -> neutral;
    victim $2E2A2 (entries 0-3): at his place and speed, anim 516 (grabbed, rolled over, head down) then 518 (slammed);
      $2E2C6 anim 466 moved by the offset; $2E2D2 its flight from the thrower's table entry $77 (3 forward, 5 up),
      gravity; landed; anim 468; the get-up.
    The brawler has no air grab: the throw starts from the hold, a rise to AIR_TOP px (his jump's gravity) in 295's first
    step comes first, then the ROM's script"""
    import export_ss2 as X, commands_ss2 as K
    ents = K.descriptor(ch, 0, 4, act)['entries']; vents = K.descriptor(ch, 0, 5, act)['entries']
    grab, slam, hop, land_a = ents[0][2] & 0x3FF, ents[3][2] & 0x3FF, ents[4][2] & 0x3FF, ents[7][2] & 0x3FF
    g = GRAVITY / 256
    tab = 0x6AA06
    drop = N.s16(tab + 2) / 256; hvx, hvy = N.s16(tab + 4) / 256, -N.s16(tab + 6) / 256
    v0 = (2 * g * AIR_TOP) ** 0.5
    fr = lambda a, i: B.frame(ss2.parse_anim(ch, a, 400)[i])
    seq = lambda a: [(a, i) for i, s_ in enumerate(ss2.parse_anim(ch, a, 400)) for _ in range(s_['ticks'] + 1)]
    def vseq(a):
        out = []
        for i, s_ in enumerate(ss2.parse_anim(ch, a, 400)):
            mv = next(((c[1], c[2]) for c in s_['cmds'] if c[0] == 'move'), (0, 0))
            out += [(a, i, mv[0], mv[1])] * (s_['ticks'] + 1)
        return out
    T, V = [], []; y = 0.0; vy = v0
    v516 = vseq(vents[0][2] & 0x3FF); v518 = vseq(vents[3][2] & 0x3FF)
    fv = lambda a, i: fr(a, min(i, len(ss2.parse_anim(ch, a, 400)) - 1))   # the victim's frame (its own drawing)
    while True:                                       # the rise (the brawler's): 295's first step, the victim grabbed
        y += vy; vy -= g
        T.append([fr(grab, 0), 0, round(y), 0]); V.append([fv(516, 0), v516[0][2], -v516[0][3], 1, 0, '516.0', None])
        if vy <= 0: break
    for k, (a_, i) in enumerate(seq(grab)):           # entry 0: the roll, held
        T.append([fr(a_, i), 0, round(y), 0]); va, vi, mx, my = v516[min(k, len(v516) - 1)]
        V.append([fv(516, vi), mx, -my, 1, 0, f'516.{vi}', None])
    nlast = len(ss2.parse_anim(ch, grab, 400)) - 1
    while y > 0:                                      # entries 1-2: the drop
        y = max(0.0, y - drop); T.append([fr(grab, nlast), 0, round(y), 0])
        V.append([fv(516, v516[-1][1]), v516[-1][2], -v516[-1][3], 1, 0, f'516.{v516[-1][1]}', None])
    impacts = [len(T) - 1]
    for a_, i in seq(slam):                           # entry 3: the slam
        T.append([fr(a_, i), 0, 0, 0]); V.append([fv(518, 0), v518[0][2], -v518[0][3], 1, 0, '518.0', None])
    q = min(1.0, FIT_TOP / (hvy ** 2 / (2 * g)))       # the hop's height x FIT_TOP / its apex (throw_leap's rule)
    x = 0.0; vx, vy = hvx, hvy * q; nh = len(seq(hop)); hs = seq(hop); k = 0     # entries 4-7: his hop back
    while True:
        x += vx; y += vy; vy -= g * q
        if y <= 0 and vy < 0: break
        a_, i = hs[min(k, nh - 1)]
        T.append([fr(a_, i), round(x), max(0, round(y)), 0]); k += 1
    for a_, i in seq(land_a): T.append([fr(a_, i), round(x), 0, 0])
    # the victim from the slam on: 466 moved by the offset, its flight from the thrower's entry $77, 468, lying
    ox = float(v518[0][2]); vxw, vyw = vtab(ch, (vents[5][2] & 0xFF) + 16)
    rel = len(V); vx, vy, yv = vxw / 256, -vyw / 256, 0.0; n = 0
    while True:
        if n: vy -= g
        ox += vx; yv += vy
        if yv <= 0: yv = 0
        V.append([fv(466, 0), round(ox), round(yv), 1, 0, '466.0', None]); n += 1
        if yv <= 0 and vy < 0: break
    land = len(V) - 1; impacts.append(land)
    for k2, s_ in enumerate(ss2.parse_anim(ch, 468, 100)):
        V += [[fv(468, k2), round(ox), 0, 1, 0, f'468.{k2}', 'down'] for _ in range(s_['ticks'] + 1)]
    for i in range(rel, len(V)):                      # after the release: offsets from where the thrower is drawn
        t = T[min(i, len(T) - 1)]; V[i][1] -= t[1]; V[i][2] -= t[2]
    return {'slot': grab, 'inputs': 'close + forward + B / A+B in the air (from the hold here)', 'table': [], 'hold': False,
            'rom': True, 'timeline': T, 'victims': {name: V}, 'impacts': sorted(set(impacts)), 'release': rel, 'land': land,
            'ret': len(T), 'anim': {'slot': grab, 'mode': 'hold', 'steps': X.anim_steps(B, ch, grab)},
            'ss2': {'anims': [grab, slam, hop, land_a], 'victim_action': act, 'air': True},
            'turned': False, 'grab_frame': None}

AIR_THROWS = {'hanzo': 7}                         # $2CA42: the fighters with an air throw (Nakoruru, Galford, Sieger too)

def throws(B, ch, name, lab=False):
    """the fighter's throws: throw_c / throw_d (B / A+B, D / C+D); with lab (the Character Lab's pack) also SS2's
    Earthquake throw (class 4 action 4, throw_big) as his extra paired throw 'throw_x' (T-003: a plain piece, no
    automatic choice by the victim: Bruno 2026-10-10, "the engine doesn't need that, just look up the throw and decode
    it"). The air throw (throw_air, T-004) is decoded but not in the pack: the engine plays three paired throws (C, D,
    the extra one)"""
    out = {k: throw(B, ch, name, k) for k in THROWS[name]}
    if lab: out['throw_x'] = throw_big(B, ch, name)
    return out

# ---- check: the programs against the game's frames --------------------------------------------------------------------
def check(names=('haohmaru', 'genjuro')):
    """every special's every button row played by the brawler's player (Play) against the capture of that command
    (moves/CC.json: P1's animation, step and place per frame) from the frame the action starts to the frame it ends
    or the opponent is hit (its hit-stop is not the move's); per row: frames compared, animation / step mismatches,
    the worst x / height error"""
    import export_ss2 as X
    res = {}
    for name in names:
        ch = CHAR[name]; B = X.Builder(ch)
        caps = {m['entry']['result']: m for m in json.load(open(f'/data/neogeo_dict/samsho2/moves/{ch:02d}.json')) if m['entry']}
        rage = {m['entry']['result']: m for m in json.load(open(f'/data/neogeo_dict/samsho2/moves/{ch:02d}_rage.json')) if m['entry']}
        air_p = f'/data/neogeo_dict/samsho2/moves/{ch:02d}_air.json'   # the air specials from a vertical jump (shuriken_ss2.py:
        air = json.load(open(air_p)) if os.path.exists(air_p) else {}   # +$7C is the step index there, TODO #211)
        for inp, (fn, nv, results) in SPECIALS[name].items():
            sp = special(B, ch, name, inp); r = sp['rom']
            cols = r['vtable']['ncol']; vars_ = [v for row in r['vtable']['rows'] for v in row] if cols else None
            for v in range(nv):
                jair = inp.startswith('j.')
                cap = air.get('up_' + ('a', 'b', 'ab')[v]) if jair else (rage if inp == 'WFT' or 'RAGE' in inp else caps).get(results[v])
                if cap is None: res[f'{name} {inp} {v}'] = 'no capture'; continue
                stidx = {}
                def sidx(a, addr):
                    if jair: return addr                 # (the air capture holds the step index)
                    if a not in stidx: stidx[a] = {s['addr']: i for i, s in enumerate(ss2.parse_anim(ch, a, 400))}
                    return stidx[a].get(addr)
                cr = cap['rows']
                s0 = next(i for i, q in enumerate(cr) if q['p1']['cls'] == 1)
                x0 = cr[s0]['p1']['x']                   # (frame 0 still moves by the walk's last velocity)
                anims_l = [{'steps': r['anims'][s]['steps'], 'hold': True, 'ss2': r['anims'][s]['ss2']} for s in r['states']]
                pl = Play(r['prims'], anims_l, vars_, v, cols, r['vtable']['vanim'])
                if jair:                                 # from the jump: its height where the move starts (fighter.c
                    pl.y = (224 - cr[s0]['p1']['y']) << 16   # start_special drops the jump's speed: SS2 moves once more
                                                             # with it in that frame, the brawler starts where SS2 is then)
                n = bad = over = 0; ex = ey = 0; first_bad = None
                for i in range(s0, len(cr)):           # (the program's first frame = SS2's first: rom['now'], SF_NOW)
                    q = cr[i]['p1']
                    if cr[i]['p2']['cls'] == 3: break
                    f = pl.frame()
                    if f is None: break
                    if q['cls'] != 1: over += 1; break           # (SS2 is back to neutral: the program still runs)
                    a_b = anims_l[f[0]]['ss2']; st_b = f[1]
                    n += 1
                    if (a_b, st_b) != (q['a'], sidx(q['a'], q['st'])):
                        bad += 1
                        if first_bad is None: first_bad = (i - s0, (a_b, st_b), (q['a'], sidx(q['a'], q['st'])))
                    ex = max(ex, abs(f[2] - (q['x'] - x0))); ey = max(ey, abs(f[3] - (224 - q['y'])))
                game_end = next((i for i in range(s0, len(cr)) if cr[i]['p1']['cls'] != 1 or cr[i]['p2']['cls'] == 3), len(cr)) - s0
                ln = n + over
                while pl.frame() is not None and ln < 2000: ln += 1   # its length: the program to its end
                res[f'{name} {inp} {"ABC"[v] if nv > 1 else ""}'] = dict(frames=n, length=ln, game_frames=game_end, mismatch=bad,
                                                                         first=first_bad, x_err=round(ex, 2), y_err=round(ey, 2))
    return res

if __name__ == '__main__':
    if sys.argv[1:2] == ['check']:
        for k, v in check(tuple(sys.argv[2:]) or ('haohmaru', 'genjuro')).items(): print(k, v)
