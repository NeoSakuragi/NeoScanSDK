#!/usr/bin/env python3
"""Rosa (Kizuna Encounter, character 4) for the brawler (TODO #213): her specials as programs read from Kizuna's handlers
(the 68000 code: substates_kz.py rosa, /data/neogeo_dict/kizuna/rosa/substates.json; the disassembly /data/tmp/kizuna/
p1.dis), the way Kim's are (export_kz.prog_special, TODO #133-#138): each animation the handler sets = a KzProg block
run by a frame counter from its P_ANIM, the steps' commands decoded as register writes on their first frame, the
handler's tests as branches, the victims' motions Kizuna's own reaction code (export_kz sr_*), no recorded rows.

Her command list ($604D0[4], commands_kz.py 4) and the handlers (group 2, $5FCE2):
  $25 236C  $39CF6: state 400 (5D); the step event (5D.2, a 0-tick step) -> the SHOCKWAV task ($2AB04, its state table
            $62C96: $191 = anim AD then AE moving 4.6875 px a frame, $193 = AF at its hit / 304 px from its start / off
            screen), neutral (5D plays on to its end there)
  $26 623C  $39D6C: state 404 (A0, the rising kick: A0.3 cmd 11 vx 5 vy 12 ay -0.8125); a hit landed -> the window
            (+$10C bit 3); A0 ended: 214C accepted (cond $0028) ? 406 (A2, a second kick) : 405 (A1, the fall); on the
            floor with the step event (their 0-tick step) -> neutral (the step after plays there)
  $27 j.623C $39E30 (cond bit 0: in the air): not in the brawler (one air special: j.2C)
  $28 214B  $39EDA: state +$EA ($62C9E: 435, A5; the tag-in strike 236A: $62CA6, 437, 11A); its attack step opens the
            window (+$10E bit 3: the box scan $294D8); A5 ended: a hit that caught + 236B accepted ? +$EE (410, D4) :
            + 214B accepted (cond $020A: +$1E9 bit 1) ? the victim's request $043B (its handler $33944: snapped onto Rosa,
            Hayate's thrown animation 101) and +$124 bit 0 -> +$F0 (411, D5) : +$EC (436, C2); then neutral
  $29 j.2C  $3A024 (cond $2020: in the air, 80 px up or more): state 412 (A7, the dive: cmd 9 vx 6 vy -6, looping); a hit
            landed -> the window, 413 (A8: cmd 9 vx 8 vy -8); A8: the floor -> 414 (A9) -> neutral; a hit landed (A8's own,
            after its hit-stop) with 2C accepted (cond $0028) -> 416 (D2, the rising kick), then 417 (D3); the floor ->
            state 96 (81, the landing); A7 on the floor -> A9
  $2A 421C  $3A192: on the ground 418 (A6, a hop back: cmd 12), in the air 419 (AA); airborne, then the floor with the
            step event (A6.2 / AA.5, 0-tick) -> neutral (the landing steps play there)
  $2B 63214C $3A238: state 420 (AB) + the BARRIER task ($3A280: anim AC, cmd 9 vx 1.625 from AC.7, its attack box
            AC.7-20; plays to its end) -> neutral
  $2C j.421C $3A192 in the air (AA): not in the brawler (one air special)
  $2D 421A  $3AEE0 (Kim's handler, his 421A): 144 (DB), a hit that caught -> at once 145 (DC), the victim snapped and
            frozen, thawed by her next hit; the relief call (+$180 = 2: the tag partner's jump attack, no partner here)
  $2E j.4B  $3A2D4 (cond $0A20: in the air near the stage's wall, +$104 bit 0 set by $2E584 / $2E5AE): needs a wall
  $2F 6246A $3A3D0: 422 (D6, the rush: D6.6 cmd 10 ax 1); a hit that caught -> the victim's request $043C (its handler
            $339D8: snapped onto Rosa, Hayate's thrown animation 106: still 31 frames, then nudged 80 / 47 and flying
            cmd 11 vx 0.3125 vy 15 ay -0.4375), +$124 bit 0 -> 423 (D7, the throw over her shoulder), D7 ended -> she
            turns round ($3A4B2 bchg +$0F) and 424 (D8: jumps after it, five kicks, no damage: life drops at the last
            hit only), D8 ended -> 425 (D9: a dive kick, its hit (0x29) takes the damage); a hit in the air -> the screen
            black ($27E4 = 0, $27E1 = $80) + 'FIX EFFE' (430, anim 10D, at a fixed place); the floor with the step event
            -> the screen back, 431 (119) -> neutral; whiff (D6 ended or a hit not caught) -> 429 (DE) -> neutral
  $22 / $23 6C / 4C throw (cmd $22, close): the brawler's throw (export_kz.throw); $23 421D: the tag desperation
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import kz, fighters_kz as FK
import export_kz as E

def bind(m):
    """the export_kz module in use (export_kz.py run as a script is __main__, not the imported export_kz)"""
    global E, KzProg, PC, REG, VA, R_HEAVY, R_KNOCKDOWN, SD
    E = m
    KzProg, PC, REG, VA = E.KzProg, E.PC, E.REG, E.VA
    R_HEAVY, R_KNOCKDOWN = E.R_HEAVY, E.R_KNOCKDOWN
    SD = E.SPECIAL_DAMAGE
    E.P.setdefault('turn', 31)                        # bm_chars.h P_TURN
bind(E)
VA_LIST = 32                                          # bm_chars.h VA_LIST (P_VPHASE b = the victim list, 1-based)
PROG_MOVES = ('236C', '623C', '214B', '421C', '63214C', '421A', '6246A')
STOP = (('set', REG['vx'], 0), ('set', REG['vy'], 0), ('set', REG['g'], 0))
VICTIM = 0                                            # the captures' victim (Hayate): its thrown animations

def an(n): return kz.parse_anim(E.CH << 12 | n)
def frames(n, first=0, last=None):
    st = an(n)[first:None if last is None else last + 1]; return sum(max(1, s['ticks']) for s in st)
def openings(n):
    """the hits an animation opens (a live attack box after a dead one, or a step with trailer bit 15)"""
    bif = E.boxes_in_force(n); k, prev, held = 0, False, False
    for s, bx in bif:
        live = any(E.attack(b) for b in bx)
        if live and (not prev or s['trailer'] & 0x8000 and not held): k += 1
        held |= live and bool(s['trailer'] & 0x2000)      # (Kizuna's bit 13: one hit for the animation, rom_steps once13)
        prev = live
    return k
def Prog(B, react, voices):
    """a KzProg with Kizuna's bit-13 hit rule (export_kz.rom_steps once13)"""
    K = KzProg(B, react, voices); K.once13 = True; return K
def dmg(nhits, total=SD): return max(1, total // max(1, nhits))

# ---- objects read from the ROM (no captured rows): a task playing animations of her table, moving by its steps'
# commands (velocities 1/256 px a frame, as the fighter's) ----
def object_rows(B, seq, frames_max, vx0=0.0):
    """rows [frame, x forward, height, attack box [1, cx, cy, w, h] or None, None] of an object playing seq = [(anim,
    'once' | 'loop')] (a loop repeats to frames_max), x from its spawn place (Kizuna px -> brawler px); its velocity
    from the steps' commands"""
    rows, x, y, vx, vy, ax, ay = [], 0.0, 0.0, vx0, 0.0, 0.0, 0.0
    for n, mode in seq:
        bif = E.boxes_in_force(n)
        while len(rows) < frames_max:
            for s, bx in bif:
                m = E.step_motion(s)
                if 'vx' in m: vx = m['vx']
                if 'vy' in m: vy = m['vy']
                if 'ax' in m: ax = m['ax']
                if 'ay' in m: ay = m['ay']
                for _ in range(max(1, s['ticks'])):
                    x += vx + ax / 2; vx += ax; y += vy + ay / 2; vy += ay
                    ab = next((b for b in bx if E.attack(b)), None)
                    rows.append([B.frame(s['addr']), E.sc(x), E.sc(max(0.0, y)), [1] + E.box_kof(ab) if ab else None, None])
                    if len(rows) >= frames_max: break
                if len(rows) >= frames_max: break
            if mode == 'once': break
    return rows

def shockwave(B):
    """236C's SHOCKWAV ($2AB04, table $62C96): AD then AE looping at 4.6875 px a frame (AD.0 cmd 9), its hit = AF (the
    end rows), its range 304 px from where AE starts ($2966E, +$D4 = its x then) -> rows to there (it dies at their end,
    as off screen); a travelling projectile (kind 1: its hit ends it)"""
    lim = E.sc(304)
    head = object_rows(B, [(0xAD, 'once')], 400)
    rows = object_rows(B, [(0xAD, 'once'), (0xAE, 'loop')], 400)
    x_ae = rows[len(head)][1] if len(rows) > len(head) else 0
    rows = [r for r in rows if r[1] - x_ae < lim]
    end = [[r[0], 0, 0] for r in object_rows(B, [(0xAF, 'once')], 60)]
    return {'table': 0, 'state': 0xAD, 'kind': 1, 'hit_kind': 1, 'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0, 'loop': None,
            'death': None, 'life': len(rows), 'travel': rows[-1][1], 'vx': E.sc(4.6875), 'rows': rows, 'end': end,
            'react': 'heavy', 'child': None, 'hits': {}, 'name': 'SHOCKWAV'}

def barrier(B):
    """63214C's BARRIER ($3A280, state 421: anim AC): at her place, still for AC.0-6, then 1.625 px a frame forward
    (AC.7 cmd 9) with its attack box (AC.7-20, one hit); plays to its end and dies (an eruption: kind 3, plays on, its
    attack spent)"""
    rows = object_rows(B, [(0xAC, 'once')], 200)
    return {'table': 0, 'state': 0xAC, 'kind': 3, 'hit_kind': 1, 'spawn_row': 0, 'spawn_x': 0, 'spawn_y': 0, 'loop': None,
            'death': None, 'life': len(rows), 'travel': rows[-1][1], 'vx': 0, 'rows': rows, 'end': [],
            'react': 'knockdown', 'child': None, 'hits': {}, 'name': 'BARRIER'}

# ---- the victim of her command grabs: Kizuna's victim handlers $33944 / $339D8 (requests $043B / $043C) put it on Rosa's
# place ($31E74: x / y = hers) once the grab is confirmed (+$124 bit 0) and play its thrown animation (state $10A: anim
# 101; $10B: 106) whose step commands move it; the brawler: a victim list frame by frame (bvlist_t VL_FRAMES, fighter.c
# vlist_apply) of its place from Rosa (both simulated from the ROM: her animation's commands, the victim's), its posture
# per thrown step (victim_poses_kz.json, read by eye from Hayate's frames: tools/kizuna sheets), released lying (101:
# its end, the damage there) or into its flight (106 step 6: Kizuna's flight motion, a source reaction, hittable) ----
def vframe_centre(ch, n, k):
    """the victim's thrown frame (character ch, animation n, step k) drawn facing right at x 0: (centre x, lowest px)"""
    W, H, X0, Y0 = E.W, E.H, E.X0, E.Y0
    img = np.zeros((H, W), np.uint16); kz.render_step(img, kz.parse_anim(ch << 12 | n)[k]['addr'], X0, Y0)
    ys, xs = np.nonzero(img)
    if not len(xs): return 0.0, 0.0
    return (xs.min() + xs.max()) / 2 - X0, Y0 - 1 - ys.max()

def simulate(steps, frames_max):
    """per frame (x forward, height, step index) of an animation's motion from (0, 0): its steps' commands (nudges,
    velocities, accelerations), the KzProg convention (x += v + a / 2, v += a); the height never below 0"""
    out, x, y, vx, vy, ax, ay = [], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    for k, s in enumerate(steps):
        m = E.step_motion(s)
        if 'vx' in m: vx = m['vx']
        if 'vy' in m: vy = m['vy']
        if 'ax' in m: ax = m['ax']
        if 'ay' in m: ay = m['ay']
        if 'nudge' in m: x += m['nudge'][0]; y = max(0.0, y + m['nudge'][1])
        for t in range(max(1, s['ticks'])):
            x += vx + ax / 2; vx += ax; y = max(0.0, y + vy + ay / 2); vy += ay
            out.append((x, y, k))
            if len(out) >= frames_max: return out
    return out

def victim_list(state, vanim, rosa, frames_max, release_at, release, rosa_offset=(0.0, 0.0)):
    """a victim list frame by frame: the victim (Hayate's animation vanim, victim state for its postures) from the grab,
    Rosa's motion rosa [(x, y, step)] from the same frame; entries {dx, dy, state, flags} in brawler px from Rosa
    (forward of her facing; the victim faces her, its forward = her backward), the release entry at release_at
    (flags VE_BLOW 1 | VE_REL 64 as release says)"""
    vst = kz.parse_anim(VICTIM << 12 | vanim)
    vs = []                                              # the victim's own motion: its forward = Rosa's backward
    for x, y, k in simulate(vst, frames_max):
        vs.append((-x, y, k))
    out = []
    for t in range(min(len(vs), release_at + 1)):
        vx_, vy_, k = vs[t]
        rx, ry = (rosa[t][0], rosa[t][1]) if t < len(rosa) else (rosa[-1][0], rosa[-1][1])
        cx, low = vframe_centre(VICTIM, vanim, k) if t < release_at or not release & 64 else (0.0, 0.0)   # (the thrown
        # frame is drawn off its feet: its picture's place; released, its body's own: the brawler draws its reaction)
        dx = vx_ - cx - (rx + rosa_offset[0])             # (its picture faces Rosa: mirrored, the centre the other way)
        dy = vy_ + low - (ry + rosa_offset[1])
        e = {'dx': E.sc(dx), 'dy': E.sc(max(-ry, dy)), 'state': f'{state:X}.{k}', 'flags': 0}
        if t == release_at: e['flags'] = release
        out.append(e)
    return out

# ---- the programs ----
def prog(B, inp, cap, fc, rec):
    """special inp as a program (module doc) -> rec with 'rom'"""
    react = E.hit_reactions(fc)
    V = lambda *recs: E.step_voices([fc[r]['frames'] if r in fc else cap[r]['frames'] for r in recs])
    parts = flinks = links = None
    extra = {}
    if inp == '236C':
        K = Prog(B, react, V('236C_w', '236C_h'))
        K.objects = [shockwave(B)]
        # (the handler goes back to neutral on 5D.2's event: neutral ticks the animation once more that frame [meas:
        # 236C_w 5D.3 shows 2 frames], its last step one frame more: the block's length)
        K.block('START', '5D', 0x5D, SD | R_HEAVY << 8, ends='END', spawns={3: [0]}, step_ops={3: [('adv',)]}, at=0)
    elif inp == '421C':
        K = Prog(B, react, V('421C_w', '421C_h'))
        st = K.block('START', 'A6a', 0xA6, dmg(openings(0xA6)) | R_HEAVY << 8, ends='AIR', at=0, first=0, last=1)
        st = K.block('AIR', 'A6w', 0xA6, dmg(openings(0xA6)) | R_HEAVY << 8, branches=(('br', PC['land'], 1, 'LAND'),),
                     state=st, first=2, last=2)
        K.block('LAND', 'A6b', 0xA6, 0, ends='END', enter=(('adv',),), state=dict(E.MERGE), first=3)   # (neutral, as 236C's)
    elif inp == '63214C':
        K = Prog(B, react, V('63214C_w', '63214C_h'))
        K.objects = [barrier(B)]
        K.block('START', 'AB', 0xAB, SD | R_KNOCKDOWN << 8, ends='END', spawns={0: [0]}, extra_end=1, at=0)
    elif inp == '623C':
        K = Prog(B, react, V('623C_w', '623C_h', '623C2_h'))
        def chk(K_):                                     # the window: a hit landed, then the press (214C = A here)
            g = K_.L(); return [('br', PC['hit'], 0, g), ('check', 1), g]
        st = K.block('START', 'A0', 0xA0, dmg(openings(0xA0)) | R_HEAVY << 8, ends='J', extras=chk, at=0)
        K.emit('J', ('br', PC['link'], 1, 'A2', 1), ('jmp', 'A1'))
        s1 = K.block('A1', 'A1a', 0xA1, 0, ends='A1W', state=st, first=0, last=2)
        K.block('A1W', 'A1w', 0xA1, 0, branches=(('br', PC['land'], 1, 'A1L'),), state=s1, first=3, last=3)
        K.block('A1L', 'A1b', 0xA1, 0, ends='END', state=dict(E.MERGE), first=4)
        s2 = K.block('A2', 'A2a', 0xA2, dmg(openings(0xA2)) | R_KNOCKDOWN << 8, ends='A2W', enter=(('part',),), state=st,
                     first=0, last=9)
        K.block('A2W', 'A2w', 0xA2, 0, branches=(('br', PC['land'], 1, 'A2L'),), state=s2, first=10, last=10)
        K.block('A2L', 'A2b', 0xA2, 0, ends='END', state=dict(E.MERGE), first=11)
        parts = [{'states': ['A0', 'A1a', 'A1w', 'A1b']}, {'states': ['A2a', 'A2w', 'A2b']}]
        flinks = [{'from': 0, 'to': 1, 'input': 'A'}]; links = ['A']
    elif inp == '214B':
        K = Prog(B, react, V('214B_w', '214B_h', '214B_c0_h', '214B_c1_h'))
        a0 = next(k for k, (s, bx) in enumerate(E.boxes_in_force(0xA5)) if any(E.attack(b) for b in bx))
        K.block('START', 'a', 0xA5, dmg(openings(0xA5)) | R_HEAVY << 8, ends='J', extras=(('check', 3),),
                extras_from=a0, at=0)
        # A5 ended: a hit that caught and 214B again (link 1) -> the grab, 236B (forward + A, link 2) -> D4, else C2
        K.emit('J', ('br', PC['hit'], 0, 'END0'), ('br', PC['link'], 1, 'GRAB', 1), ('br', PC['link'], 1, 'B', 2), ('jmp', 'END0'))
        K.block('END0', 'e', 0xC2, 0, ends='END', state=dict(E.MERGE), extra_end=1)
        K.block('B', 'b', 0xD4, dmg(openings(0xD4)) | R_KNOCKDOWN << 8, ends='END', enter=(('part',),), state=dict(E.MERGE),
                extra_end=1)
        K.emit('GRAB', ('part',), ('resume_at', 'GRAB2'), ('yield',))   # (+$124 bit 0 the frame after: the victim's handler)
        rosa = KzSim(0xD5).frames
        vend = sum(max(1, s['ticks']) for s in kz.parse_anim(VICTIM << 12 | 0x101)) - 1
        extra['vlists'] = [{'e': victim_list(0x10A, 0x101, rosa, 200, vend, 1 | 64), 'down': True, 'frames': True}]
        K.block('GRAB2', 'g', 0xD5, SD | R_KNOCKDOWN << 8, ends='END', enter=STOP + (('vphase', VA_LIST, 1),),
                state=dict(E.MERGE), extra_end=1)
        parts = [{'states': ['a', 'e']}, {'states': ['g']}, {'states': ['b']}]
        flinks = [{'from': 0, 'to': 1, 'input': 'again'}, {'from': 0, 'to': 2, 'input': 'fA'}]
        links = ['again', 'fA']
    elif inp == '421A':
        # (Kim's 421A handler $3AEE0: export_kz's 421A branch with her animations DB / DC)
        K = Prog(B, react, V('421A_w', '421A_h'))
        fr = fc['421A_w']['frames']; s0, e, rows = E.part_rows(fr, [0xDB], False)
        K.objects = E.effects(B, fr, rows, 0, fr[s0][0][2])
        sp0 = E.first_steps(fr, rows, K.objects, (0xDB,))
        each = dmg(openings(0xDB) + openings(0xDC))
        last = lambda n: 1 + an(n)[-1]['ticks']
        K.block('START', 'DB', 0xDB, each | R_HEAVY << 8, ends='END', branches=(('br', PC['hit'], 1, 'CATCH'),),
                spawns={k: v for (a, k), v in sp0.items()}, extra_end=last(0xDB), at=0)
        # (a hit that caught: DC from the frame after the hit-stop [meas: 421A_h DB.3 -> DC.0], not Kim's 100.4 frame first)
        def thaw(K_):
            g = K_.L(); return [('br', PC['hit'], 0, g), ('vphase', VA['thaw']), g]
        K.block('CATCH', 'DC', 0xDC, each | R_HEAVY << 8, ends='END', enter=STOP + (('vphase', VA['snap'] | VA['freeze']), ('hitoff',)),
                extras=thaw, extra_end=last(0xDC))
    elif inp == '6246A':
        K = Prog(B, react, V('6246A_w', '6246A_h'))
        fr = fc['6246A_h']['frames']
        total = E.game_damage({'damage': '6246A_h'}, fc)['damage']   # Kizuna's (its one life drop: D9's hit)
        rosa = KzSim(0xD7).frames
        rel = sum(max(1, s['ticks']) for s in kz.parse_anim(VICTIM << 12 | 0x106)[:5])   # 106 steps 0-4 still (31
        sr = E.sr_motion(0x106)                          # frames), step 5 nudged, step 6 its flight: a source reaction
        if sr not in E.SREACT: E.SREACT.append(sr)
        vl = victim_list(0x10B, 0x106, rosa, 200, rel, 64)
        extra['vlists'] = [{'e': vl, 'frames': True, 'sreact': E.SREACT.index(sr) + 1}]
        last = lambda n: 1 + an(n)[-1]['ticks']
        K.block('START', 'D6', 0xD6, 0 | R_HEAVY << 8, ends='WHIFF', branches=(('br', PC['hit'], 1, 'CATCH'),),
                at=0)
        K.block('WHIFF', 'DE', 0xDE, 0, ends='END', enter=STOP, state=dict(E.MERGE), extra_end=1)
        K.emit('CATCH', ('resume_at', 'CATCH1'), ('yield',))   # (the victim's handler confirms the grab: +$124 bit 0)
        K.emit('CATCH1', ('resume_at', 'THROW'), ('yield',))
        st = K.block('THROW', 'D7', 0xD7, 0, ends='JUMP', enter=STOP + (('vphase', VA_LIST, 1),), state=dict(E.MERGE))
        # each kick's hit ($3A576): $27E4 = $4F00 / $0000, $27E1 = $10: the stage hidden, black / red every frame,
        # 16 frames [meas: 6246A_h screens, black first]; the dive's hit in the air ($3A518): $27E4 = 0, $27E1 = $80:
        # black until she lands (+ the FIX EFFE picture: not drawn, a screen-fixed object)
        st = K.block('JUMP', 'D8', 0xD8, 0 | R_KNOCKDOWN << 8, ends='DIVE', enter=(('turn',),), state=st,
                     on_hit=(('screen', 0x80 | 16),))
        st = K.block('DIVE', 'D9a', 0xD9, total | R_KNOCKDOWN << 8, ends='D9W', enter=(('hitoff',),), on_hit=(('screen', 2),),
                     state=st, first=0, last=15)
        K.block('D9W', 'D9w', 0xD9, 0, branches=(('br', PC['land'], 1, 'LAND'),), state=st, first=16, last=16)
        K.block('LAND', '119', 0x119, 0, enter=(('screen', 0),), ends='END', state=dict(E.MERGE), extra_end=last(0x119))
        extra['backdrop'] = {'rows': [0xFFFF, 1], 'colours': [0x0000, 0x4F00]}   # (black first, then red)
    K.emit('END', ('end',))
    rom = {'states': K.states, 'anims': {k: {'mode': a['mode'], 'steps': a['steps'], 'kz_anim': a['n'], 'kz_first': a['first']}
                                         for k, a in K.anims.items()},
           'prims': K.prims(), 'objects': K.objects, 'openings': {}, 'hit_kind': 1, 'last_hit': -1, 'apex': -1,
           'length': len(rec['script']), 'now': True, 'sreact': True, 'sharepush': True}
    if parts: rom.update(parts=parts, follow_links=flinks, links=links)
    if extra.get('vlists'): rom['vlists'] = extra['vlists']
    wp = rec['parts'][0]['end'] if rec.get('parts') else len(rec['script'])
    live = [i for i in range(wp) if any(k_[0] == '1' for k_ in rec['row_boxes'][i])]
    rom['last_hit'] = live[-1] if live else -1
    peak = max(range(wp), key=lambda i: rec['script'][i][2])
    rom['apex'] = peak if rec['script'][peak][2] > 0 else -1
    out = {**rec, 'parts': [], 'links': [], 'rom': rom}
    out.pop('carry_src', None)
    out.pop('backdrop', None)
    if extra.get('backdrop'): out['backdrop'] = extra['backdrop']
    return out

# ---- j.2C, her air special (down+A in a jump: game.json air_special; vocabulary air.special) ----
AIR = {'j.2C': {'dive': 0xA7, 'land': 0xA9, 'whiff': 'j2C_w', 'hit': 'j2C_h', 'hit2': 'j2C2_h'}}
def air(B, fc):
    """$3A024 (command $29): state 412 (A7, cmd 9 vx 6 vy -6, no gravity: the dive, looping) each frame: a hit landed ->
    the window, 413 (A8, cmd 9 vx 8 vy -8; $3A086: its effect when not on the floor); the floor -> $3A164 (the next frame:
    414 = A9 -> neutral). $3A0B4 each frame of A8: the floor -> A9; a hit landed (A8's own: the window closed by it) and
    2C accepted (down+A here; presses from A7's hit on) -> 416 (D2: stop, cmd 11 vx 3 vy 7 ay -0.5625, its kick), D2
    ended -> 417 (D3: nudge -10 / 22, cmd 11 vx 2 vy -1 ay -0.375, the wait step); the floor -> 96 (81, the landing)"""
    A = AIR['j.2C']
    K = Prog(B, E.hit_reactions(fc), E.step_voices([fc[r]['frames'] for r in ('j2C_w', 'j2C_h', 'j2C2_h')]))
    K.block('START', 'A7', 0xA7, dmg(2) | R_HEAVY << 8, at=0,
            branches=(('br', PC['hit'], 1, 'HIT'), ('br', PC['land'], 1, 'LANDW')))
    K.emit('LANDW', ('move',), ('resume_at', 'A9'), ('yield',))   # (A7's last frame on the floor: it moves [meas: j2C_w])
    def a8(K_):                                          # the floor first, then its own hit (A7's cleared: P_HITOFF)
        g = K_.L()                                       # with the follow-up
        return [('br', PC['land'], 1, 'A9'), ('br', PC['hit'], 0, g), ('br', PC['link'], 1, 'D2', 1), g]
    def chk(K_):                                         # (the window: presses until A8's own hit)
        g = K_.L(); return [('br', PC['hit'], 1, g), ('check', 1), g]
    K.block('HIT', 'A8', 0xA8, dmg(2) | R_HEAVY << 8, enter=(('hitclr',), ('hitoff',), ('check', 1, 1)), branches=a8,   # (its last
            extras=chk, state=dict(E.MERGE))             # step waits for the floor: one block, the window one hit)
    K.block('A9', 'A9', 0xA9, 0, ends='END', enter=STOP, state=dict(E.MERGE), extra_end=1)
    s2 = K.block('D2', 'D2', 0xD2, SD | R_KNOCKDOWN << 8, ends='D3', enter=(('part',),),
                 branches=(('br', PC['land'], 1, 'L81'),), state=dict(E.MERGE))
    s3 = K.block('D3', 'D3a', 0xD3, 0, ends='D3W', branches=(('br', PC['land'], 1, 'L81'),), state=s2, first=0, last=3)
    K.block('D3W', 'D3w', 0xD3, 0, branches=(('br', PC['land'], 1, 'L81'),), state=s3, first=4, last=4)
    K.block('L81', '81', FK.kim_anim(E.CH, 0x82), 0, ends='END', enter=STOP, state=dict(E.MERGE), extra_end=1)
    K.emit('END', ('end',))
    rom = {'states': K.states, 'anims': {k: {'mode': a['mode'], 'steps': a['steps'], 'kz_anim': a['n'], 'kz_first': a['first']}
                                         for k, a in K.anims.items()},
           'prims': K.prims(), 'objects': K.objects, 'openings': {}, 'hit_kind': 1, 'last_hit': -1, 'apex': -1,
           'voice_frames': True, 'now': True, 'sharepush': True, 'sreact': True,
           'parts': [{'states': ['A7', 'A8', 'A9']}, {'states': ['D2', 'D3a', 'D3w', '81']}],
           'follow_links': [{'from': 0, 'to': 1, 'input': 'dA'}], 'links': ['dA']}
    # the Lab's script: the whiff as Kizuna plays it from the dive's first frame (rows = frames)
    fr = fc[A['whiff']]['frames']
    s0 = next(i for i, f in enumerate(fr) if f[0][0] == A['dive'])
    e = next(i for i in range(s0, len(fr)) if fr[i][0][0] not in (A['dive'], A['land']))
    x0 = fr[s0 - 1][0][2]
    script, rb, rs = [], [], []
    for i in range(s0, e):
        p = fr[i][0]; bx = E.step_boxes(p[5])
        script.append([B.frame(p[5]), E.sc(p[2] - x0), E.sc(p[3]), []]); rb.append(E.kof_boxes(bx))
        rs.append([p[0], p[1], 0x100 if any(E.attack(b) for b in bx) else 0, 0xFF])
    rom['length'] = len(script)
    hf = fc[A['hit2']]['frames']
    return {'input': 'j.2C', 'condition': 'normal', 'version': 'whiff', 'air': True, 'script': script, 'row_boxes': rb,
            'row_steps': rs, 'marks': [''] * len(script), 'projectiles': [], 'anims': [0xA7, 0xA8, 0xA9, 0xD2, 0xD3],
            'shape': [max(r[1] for r in script), max(r[2] for r in script), False],
            'game_hits': sum(1 for j in range(1, len(hf)) if hf[j][1][6] < hf[j - 1][1][6]), 'rom': rom}

class KzSim:
    """Rosa's own motion through an animation from its first frame (her steps' commands, as the program moves her):
    frames [(x forward, height, step)] in Kizuna px from where it starts"""
    def __init__(self, n):
        self.frames = simulate(an(n), 400)
