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
     'voice': 29, 'vsig': 30}                                 # bm_chars.h P_*
REG = {'vx': 0, 'vy': 1, 'g': 2, 'fric': 3, 'cnt': 4, 'h': 5}
PC = {'end': 0, 'event': 1, 'land': 2, 'fall': 3, 'cnt': 4, 'hit': 5, 'off': 6, 'always': 7, 'stepev': 8, 'window': 9,
      'link': 10, 'hitany': 11, 'passed': 20}
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
def E(anim=None, init=(), conds=(), phys='ground', flags=None, part=None, react=None, catch=None):
    """catch: the entry index of the catch routine: this entry's attack steps are catch boxes (no damage, the victim
    held: fighter.c's catch, KOF +$19C), the routine starts after the hit-stop and the victim follows the move's victim
    lists (VL below)"""
    return {'anim': anim, 'init': list(init), 'conds': list(conds), 'phys': phys, 'flags': flags or {}, 'part': part,
            'react': react, 'catch': catch}

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
    """Sake Kougeki, 2 1 4 + A -> result 47 ($35550) [code]: anim 328 then 329, routine $3555C each: velocities 0,
    the end -> next (the first) / neutral"""
    return [E(328, [('set', 'vx', 0)], [('end', 'next')]), E(329, [('set', 'vx', 0)], [('end', 'end')])], []

# SS2's big hit (TODO #188 c): Haohmaru's WFT routine on a connect ($354E8 $2B958 -> $354FA) calls $2B9DE with
# $6A672 = (31, 0, 0, 48): the backdrop ($108A86 -> $401FFE every frame, $172C) red for 48 frames ($8AE2), and its hit
# (the hit routine's big-hit branch $26CB0: +$FB = 32 to both, the slow-motion counter $8AC8 = 30) holds both 40
# frames, then the whole game runs at half speed for 30 [meas: our emulator, /data/tmp/b188/out/c_ss2_*: his step
# held frames 63-103, then a step every 4 frames to 133; the victim in its hit pose 414 until 139, then thrown]
BIGHIT = {('haohmaru', 'WFT')}

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
    out = {'e': [dict(dx=dx, dy=dy, state=st, flags=fl) for dx, dy, st, fl in entries]}
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
    6 anim 24 $56262: the spin (its slashes: 5 attack steps); its end -> the fall ($6B4E6, gravity), voice $206, the
      opponent's stage 2 (released, disarmed: +$B8)
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
            E(261, conds=[('land', 'end')], phys=g)]
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

# fighter -> its specials: input -> (decoder, buttons, the command results per button (moves/CC.json's entries))
SPECIALS = {
    'haohmaru': {'236S': (hao_236s, 3, (41, 42, 43)), '623S': (hao_623s, 3, (38, 39, 40)), '623K': (hao_623k, 3, (48, 49, 50)),
                 '236K': (hao_236k, 1, (44,)), '214A': (hao_214a, 1, (47,)), 'WFT': (hao_wft, 1, (37,))},
    'genjuro': {'214S': (gen_214s, 3, (38, 39, 40)), '236S': (gen_236s, 3, (41, 42, 43)), '623S': (gen_623s, 3, (50, 51, 52)),
                'WFT': (gen_wft, 1, (37,))},
    'kuroko': {'236A': (kur_parody(39), 1, (39,)), '16A': (kur_parody(40), 1, (40,)), '214161BC': (kur_parody(41), 1, (41,)),
               '126BC': (kur_parody(42), 1, (42,)), '236B': (kur_parody(43), 1, (43,)), '2363214A': (kur_parody(44), 1, (44,)),
               '214A': (kur_parody(45), 1, (45,)), '61236A': (kur_parody(46), 1, (46,)), 'CCCCC': (kur_ccccc, 1, (47,)),
               '6ABC': (kur_flag(3), 1, (48,)), '6BCD': (kur_flag(5), 1, (49,)), 'RAGE': (kur_rage(False), 1, (37,)),
               'MAX RAGE': (kur_rage(True), 1, (38,))},
}
CHAR = {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17}

# ---- the program: entries -> ops --------------------------------------------------------------------------------------
CUR = {'ch': 0}
def end_ev(a):
    """the animation's last step has 0 ticks: its end is its event (rom_steps)"""
    st = ss2.parse_anim(CUR['ch'], a, 400)
    return len(st) > 1 and st[-1]['ticks'] == 0

def compile_prog(ents):
    """[(op, operands...)] with labels; anims (SS2 animation of each state, in P_ANIM order); spawns"""
    ops, states = [], []
    def tgt(i, t):
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
            else: cond = {'end': 'end', 'apex': 'fall', 'hit': 'hit'}.get(c) or ('stepev' if c[0] == 'step' else None)
            if c == 'end' and end_ev(cur): ops.append(('br', 'stepev', 1, ('S', i, k)))
            ops.append(('br', cond, 1, ('S', i, k))); sw.append((('S', i, k), T, extra, True))
        if now: ops += now[1] + routine_phys(e, (i, 'n')) + [('resume_at', now[0]), ('br', 'always', 1, 'yield')]
        else: ops += routine_phys(e, (i, 'loop')) + [('br', 'always', 1, 'yield')]
        for lab, T, extra, ph in sw:
            ops += [('label', lab)] + extra + (routine_phys(e, lab) if ph else []) + [('resume_at', T), ('br', 'always', 1, 'yield')]
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
    if n == 'spawn': return (P['spawn'], o[1], 0, 0)
    if n == 'check': return (P['check'], o[1], 0, 0)
    if n == 'nudge': return (P['nudge'], 0, o[1], 0)
    return (P[n], 0, 0, 0)

# ---- the brawler's player, ported from fighter.c (prog_update, pan_*), for check() and the hit counts ----------------
class Play:
    """one special's program played alone (no opponent: no hit), per frame the state (anim index, step, x, y)"""
    def __init__(self, prims, anims, vars_=None, var=0, vcols=0, vanim=0):
        self.prims, self.anims, self.vars, self.var, self.vcols, self.vanim = prims, anims, vars_, var, vcols, vanim
        self.x = self.y = self.vx = self.vy = self.pg = self.cnt = 0
        self.flags = set(); self.pres = 0; self.done = False; self.spawns = []; self.rows = []; self.srow = 0
        self.landed = False; self.plink = 0; self.spend = 0
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
        s = self.an['steps'][self.pstep]
        return {PC['stepev']: 'event' in self.flags, PC['end']: 'end' in self.flags, PC['land']: 'land' in self.flags,
                PC['fall']: 'fall' in self.flags, PC['cnt']: self.cnt < 0, PC['hit']: self.landed,
                PC['window']: bool(s['flags'] & 0x2000), PC['link']: bool(self.plink & v), PC['always']: True,
                PC['passed']: False}[c]                    # (alone: no opponent to pass)
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
                if self.y <= 0: self.y = 0; self.flags.add('land')
                elif self.vy < 0: self.flags.add('fall')
            elif op == P['nudge']: self.x += b << 16; self.y += v << 16
            elif op == P['dec']: self.cnt -= 1
            elif op == P['br']:
                if self.cond(a & 0x7F, v) == bool(a >> 7):
                    if b < 0: break
                    ppc = b
            elif op == P['resume']: self.pres = ppc
            elif op == P['resume_at']: self.pres = b
            elif op == P['jmp']: ppc = b
            elif op == P['spawn']: self.spawns.append((self.srow - 1, a, self.x))
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

OBJECTS = {'wind': wind, 'wind2': wind2, 'tornado': tornado, 'crescent': crescent, 'cards': cards, 'kparody': kparody, 'kcrescent': kcrescent, 'kghost': kghost}

# ---- a special -> export96 layout --------------------------------------------------------------------------------------
def rom_steps(B, ch, a, flags, react, catch=False):
    import export_ss2 as X
    st = X.anim_steps(B, ch, a)
    for i, s in enumerate(st):
        s['flags'] |= flags.get(i, 0)
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

def special(B, ch, name, inp):
    fn, nv, results = SPECIALS[name][inp]
    CUR['ch'] = ch
    full = [fn(v) for v in range(nv)]
    progs = [r[:2] for r in full]
    vlists = full[-1][2] if len(full[-1]) > 2 else []
    comp = [compile_prog(e) for e, _ in progs]
    asm = [assemble(o) for o, _ in comp]
    assert all(len(x) == len(asm[0]) for x in asm), (name, inp, [len(x) for x in asm])
    enc = [[encode(o) for o in x] for x in asm]
    default = nv - 1                                  # the heaviest button: A+B (export_dd's rule)
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
            steps = rom_steps(B, ch, a, ents[ei]['flags'], ents[ei]['react'], ents[ei].get('catch') is not None)
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
        st = ss2.parse_anim(ch, anims_d[states[r[0]]]['ss2'], 400)[r[1]]
        snd += [[i, c[1] + (1 if c[0] == 'sound_pan' else 0)] for c in st['cmds'] if c[0] in ('sound', 'sound_pan')]
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
    import commands_ss2 as K
    if K.descriptor(ch, 0, 1, results[default])['b'][0] & 0x80: rom['nopush'] = True   # descriptor byte 4 bit 7 -> +$FF:
                                                       # no push between the players ($CC14) while it plays [code]
    if (name, inp) in BIGHIT: rom['bighit'] = True        # its connect: SS2's big-hit pause (export_bm SF_BIGHIT)
    if parts:                                          # follow-ups (the slash chain): its parts, the press 'again'
        rom['parts'] = [{'states': [states[j] for j, (ei, a) in enumerate(sts0) if ents0[ei]['part'] == p]} for p in parts]
        rom['follow_links'] = [{'from': p, 'to': p + 1, 'input': 'again'} for p in parts[:-1]]
        rom['links'] = ['again']
    return {'input': inp, 'condition': 'normal', 'version': 'whiff', 'script': script, 'row_boxes': rb, 'row_steps': rs,
            'marks': [''] * len(script), 'projectiles': pj, 'anims': [a for _, a in sts0],
            'shape': [max(r[1] for r in script), max(r[2] for r in script), bool(pj)], 'game_hits': len(opens),
            'rom': rom, 'ss2': {'results': list(results), 'sounds': snd, 'code_sounds': spawn_snd}}

# decoded but not exported: a fighter's palettes must fit the brawler's 8 (MAX_PALS); Kuroko's moves need 10 together:
# the smoke dud (61236A: palette 178) and the energy ball (126BC: palette 39) stay out (their decode is above)
NOT_EXPORTED = {'kuroko': {'61236A', '126BC'}}

def specials(B, ch, name):
    return [special(B, ch, name, inp) for inp in SPECIALS[name] if inp not in NOT_EXPORTED.get(name, ())]

# ---- throws ------------------------------------------------------------------------------------------------------------
# class 4 action -> (the thrower's animation, the victim's class 5 action): Haohmaru close + forward + A+B (action 1:
# the slash throw, anim 274) and + D / C+D (2 / 3: the kick throw, anim 346); Genjuro: the slash throw for all three
# (descriptors $28310 class 4: $2E38C / $2D420 / $2E3A4 + $2D1EC) [code]
THROWS = {'haohmaru': {'throw_c': (274, 1), 'throw_d': (346, 2)}, 'genjuro': {'throw_c': (274, 1), 'throw_d': (274, 1)},
          'kuroko': {'throw_c': (27, 1), 'throw_d': (27, 1)}}   # Kuroko: one throw (class 4 actions 0-3: anim 27)

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
    a, sub = THROWS[name][key]
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

def throws(B, ch, name):
    return {k: throw(B, ch, name, k) for k in THROWS[name]}

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
        for inp, (fn, nv, results) in SPECIALS[name].items():
            sp = special(B, ch, name, inp); r = sp['rom']
            cols = r['vtable']['ncol']; vars_ = [v for row in r['vtable']['rows'] for v in row] if cols else None
            for v in range(nv):
                cap = (rage if inp == 'WFT' or 'RAGE' in inp else caps).get(results[v])
                if cap is None: res[f'{name} {inp} {v}'] = 'no capture'; continue
                stidx = {}
                def sidx(a, addr):
                    if a not in stidx: stidx[a] = {s['addr']: i for i, s in enumerate(ss2.parse_anim(ch, a, 400))}
                    return stidx[a].get(addr)
                cr = cap['rows']
                s0 = next(i for i, q in enumerate(cr) if q['p1']['cls'] == 1)
                x0 = cr[s0]['p1']['x']                   # (frame 0 still moves by the walk's last velocity)
                anims_l = [{'steps': r['anims'][s]['steps'], 'hold': True, 'ss2': r['anims'][s]['ss2']} for s in r['states']]
                pl = Play(r['prims'], anims_l, vars_, v, cols, r['vtable']['vanim'])
                n = bad = 0; ex = ey = 0; first_bad = None
                for i in range(s0, len(cr)):
                    q = cr[i]['p1']
                    if cr[i]['p2']['cls'] == 3: break
                    f = pl.frame()
                    if f is None or q['cls'] != 1: break
                    a_b = anims_l[f[0]]['ss2']; st_b = f[1]
                    n += 1
                    if (a_b, st_b) != (q['a'], sidx(q['a'], q['st'])):
                        bad += 1
                        if first_bad is None: first_bad = (i - s0, (a_b, st_b), (q['a'], sidx(q['a'], q['st'])))
                    ex = max(ex, abs(f[2] - (q['x'] - x0))); ey = max(ey, abs(f[3] - (224 - q['y'])))
                game_end = next((i for i in range(s0, len(cr)) if cr[i]['p1']['cls'] != 1 or cr[i]['p2']['cls'] == 3), len(cr)) - s0
                res[f'{name} {inp} {"ABC"[v] if nv > 1 else ""}'] = dict(frames=n, game_frames=game_end, mismatch=bad,
                                                                         first=first_bad, x_err=round(ex, 2), y_err=round(ey, 2))
    return res

if __name__ == '__main__':
    if sys.argv[1:2] == ['check']:
        for k, v in check().items(): print(k, v)
