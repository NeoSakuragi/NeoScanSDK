#!/usr/bin/env python3
"""World Heroes Perfect's six buttons, read from the code: which animation every button plays in every stance (the
normals), the ground specials' three strengths, the throws. Generic: a fighter is its row (display object +$6004 - 1,
the select roster order: Dragon 0, Hanzou 1, ...) and its animation character (whp.base); every table below is
indexed by the row, so the next fighter imports the same way. Labels: [code] read in the disassembly, [meas] measured.

The buttons [code $2E25C]: the buttons pressed within 3 frames make one chord (+$6049: A 1, B 2, C 4, D 8). Six
chords attack: A / B = light / heavy punch, C / D = light / heavy kick, A+B = strong punch, C+D = strong kick
(BUTTONS: button, chord, strength). Strengths are named low / mid / high (light / heavy / strong).

The normals (the press handler $34C34, called from the ground and air press code $34998 / $35536 / $38808 ...):
  ground [code $34C36]: word[$349C0 + 32 chord + 2 (stick & 14)] = the animation (relative) for neutral / down /
    left / right (U is masked off: the air has its own handler), then the chord's handler (table $34C7A by chord):
      - the special command scan first ($30C6E; +$6D = the chord), then
      - running (the current animation is the run, $0C): the move + 3 (+ $18 more with down held, $35326): the run
        normals ($43 / $5B for A) [code $34FD6 ...: the immediates checked by normals()];
      - a direction held: the strong and heavy presses (B, A+B, D, C+D: d0 != 0) try the throw first ($315B0);
        then $3535C: + 1 when the stick points away from the opponent (back); then $353BC: + $18 when the opponent is
        within the close reach: |dx| < (byte[$34594 + 32 row + (anim - $40)] + byte[$34574 + victim row]) << 8
        (1/128 px; only for animations $40-$57: the standing ones);
      - crouching (stick down): the table's down entry ($70-$76; some rows add 4 with forward on the kicks, $35282).
  air [code $36FBA, table $36FCE by chord]: the vertical jump's normal while the jump animation is the straight
    one ($10), the diagonal one otherwise: A $80 / $88, B $81 / $89, A+B $82 / $8A, C $84 / $8C, D $85 / $8D, C+D
    $86 / $8E (immediates read by air_normals(); rows 2 / 5 / 8 / 11 / 12 / 19 have extra down-held air moves).
The ground specials: handlers_whp.special_commands (the punch list $2E40C: A / B / A+B, the kick list $2E60C: C / D /
C+D; one animation triple per command, $31126 picks it by the press) -> specials(): every command's three rows.
The throws [code $315B0]: the strong chords with a direction held near a standing opponent: A+B (+$6D 3) count
byte[$302C4 + row] / animation byte[$302E4 + row]; C+D (+$6D 12) $30344 / $30364; in the air (A+B) $30404 / $30444
($30424 with +$6C); 0 = no throw. The reach: +$72 = byte[$31808 / $31828 (A+B forward / back), $31848 / $31868 (C+D)
+ row], a box set of $30488 tested by $3190E. The count: +$6E = count - 1; $31AA0: forward held -> 0 (the forward
throw, the table's animation), back held -> kept, then 1 -> the animation + 2 (the back throw) ($31718). Both fighters
get +$60D5 bit 3 (thrown / throwing). The victim [code $159D8, command 16 [w anim][w table]]: the first word (when
not 0) makes the victim play that animation (relative to its own base: $14E held); each throw step's command 16 places
it: long[long[$5D528] + 64 (row) + 4 table] -> by victim row -> 8 bytes a step (+$60DC): [victim def][dy][dx][mode]
(1/128 px; mode 0: the victim at the thrower + (dx forward, dy up)); command 18 [w anim] ($15BA8) lets it go: the
victim plays that animation (its thrown flight, $F0 / $F3)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import whp, handlers_whp as H

m = whp.m
BUTTONS = [('A', 1, 'low'), ('B', 2, 'mid'), ('AB', 3, 'high'), ('C', 4, 'low'), ('D', 8, 'mid'), ('CD', 12, 'high')]
STRENGTH = {'A': 'low', 'B': 'mid', 'AB': 'high', 'C': 'low', 'D': 'mid', 'CD': 'high'}
KIND = {'A': 'punch', 'B': 'punch', 'AB': 'punch', 'C': 'kick', 'D': 'kick', 'CD': 'kick'}
GROUND_TABLE = 0x349C0
CLOSE_REACH, VICTIM_REACH = 0x34594, 0x34574
AIR_TABLE = 0x36FCE
STICK = {'neutral': 0, 'down': 2, 'left': 4, 'right': 8}
RUN = 0x0C                                       # the run animation (relative) [code $34FD6: cmpiw #12]
JUMP_UP = 0x10                                   # the straight jump [code $3717A: cmpiw #16]

def ground_entry(chord, stick):
    return m.u16(GROUND_TABLE + 32 * chord + 2 * (stick & 14))

def close_reach(row, rel, victim_row):
    """px: the close normal's reach (byte[$34594 + 32 row + rel - $40] + the victim row's byte[$34574]) << 8 / 128"""
    a = m.u8(CLOSE_REACH + 32 * row + ((rel - 0x40) & 31)); b = m.s8(VICTIM_REACH + victim_row) if hasattr(m, 's8') else m.u8(VICTIM_REACH + victim_row)
    if b >= 0x80: b -= 0x100
    return (a + b) * 256 / 128

def air_normals():
    """{chord: (vertical, diagonal)} from the air handler's immediates ($36FBA: jump table by chord; each handler ends
    `movew #diag,%d0` / `movew #vert,%d0` before the store at $372F2; the row-specific down-held moves left out)"""
    out = {}
    for b, chord, _ in BUTTONS:
        h = m.u32(AIR_TABLE + 4 * chord)
        ins = H.dis(h, h + 0x120)
        imms = []
        for pc in sorted(ins):
            mn, op, nx = ins[pc]
            if mn == 'movew' and op.endswith(',%d0') and op.startswith('#'):
                imms.append(H.imm(op.split(',')[0]))
            if mn == 'braw' and op == '0x372f2' and len(imms) >= 2 and imms[-1] in range(0x80, 0x90) and imms[-2] in range(0x80, 0x90):
                break
        v = [x for x in imms if 0x80 <= x < 0x90]
        assert len(v) >= 2, (b, [hex(x) for x in imms])
        dia, ver = v[-2], v[-1]
        assert ver + 8 == dia, (b, hex(ver), hex(dia))
        out[b] = (ver, dia)
    return out

def normals(row, char, victim_row=None):
    """every normal of the fighter by button x stance -> [dict(button, chord, strength, kind, stance, rel, addr,
    same_as (an earlier stance with the same animation data), close_px (the reach that makes it close))]"""
    victim_row = row if victim_row is None else victim_row
    air = air_normals(); out = []
    seen = {}
    def add(b, chord, stance, rel, **kw):
        a = whp.anim_addr(char, rel)
        d = dict(button=b, chord=chord, strength=STRENGTH[b], kind=KIND[b], stance=stance, rel=rel, addr=a,
                 same_as=seen.get((b, a)), **kw)
        seen.setdefault((b, a), stance); out.append(d)
    for b, chord, _ in BUTTONS:
        far = ground_entry(chord, STICK['neutral']); fdir = ground_entry(chord, STICK['right'])
        assert ground_entry(chord, STICK['left']) == fdir, b
        add(b, chord, 'far', far)
        add(b, chord, 'far_fwd', fdir)
        add(b, chord, 'far_back', fdir + 1)
        add(b, chord, 'close', far + 0x18, close_px=close_reach(row, far, victim_row))
        add(b, chord, 'close_fwd', fdir + 0x18, close_px=close_reach(row, fdir, victim_row))
        add(b, chord, 'close_back', fdir + 1 + 0x18, close_px=close_reach(row, fdir + 1, victim_row))
        add(b, chord, 'crouch', ground_entry(chord, STICK['down']))
        add(b, chord, 'jump_up', air[b][0])
        add(b, chord, 'jump_diag', air[b][1])
        add(b, chord, 'run', far + 3)
        add(b, chord, 'run_low', far + 3 + 0x18)
    return out

def check_run_immediates():
    """the run normals' immediates in the six ground handlers = the table's neutral entry + 3 / + $1B [code]"""
    found = {}
    for b, chord, _ in BUTTONS:
        h = m.u32(0x34C7A + 4 * chord); ins = H.dis(h, h + 0x80); imms = []
        for pc in sorted(ins):
            mn, op, nx = ins[pc]
            if mn == 'movew' and op.endswith(',%a5@(102)') and op.startswith('#'): imms.append(H.imm(op.split(',')[0]))
            if len(imms) == 2: break
        far = ground_entry(chord, 0)
        assert imms == [far + 3, far + 0x1B], (b, [hex(x) for x in imms], hex(far))
        found[b] = imms
    return found

# brawler move names (export_whp): button -> name part; the stances that are their own move
PART = {'A': 'a', 'B': 'b', 'AB': 'ab', 'C': 'c', 'D': 'd', 'CD': 'cd'}
def brawler_name(n):
    """the brawler move a WHP normal is exported as (docs/brawler_data_model.md 'World Heroes Perfect'), None when it is
    the same animation as another stance's (n['same_as'])"""
    if n['same_as'] is not None: return None
    p = PART[n['button']]; s = n['stance']
    if s == 'far': return 'body_toss' if p == 'cd' else f'atk_{p}_far'
    if s in ('far_fwd', 'close_fwd'): return f'cmd_fwd_{p}'
    if s in ('far_back', 'close_back'): return f'cmd_back_{p}'
    if s == 'close': return f'atk_{p}_close'
    if s == 'crouch': return f'atk_{p}_crouch'
    if s == 'jump_up': return f'atk_{p}_jump'
    if s == 'jump_diag': return f'atk_{p}_jump_diag'
    if s == 'run': return f'atk_{p}_run'
    if s == 'run_low': return f'atk_{p}_run_low'
    raise KeyError(s)

# ---- specials ------------------------------------------------------------------------------------------------------
NOTATION = {'punch': 'P', 'kick': 'K'}
def specials(row, char):
    """every ground special command of the row with its three strength rows: dict(input (numpad + P / K), list,
    command, motion, rows [dict(button, strength, rel, addr)], distinct (the rows' different animations), hero)"""
    out = []
    for lst, cm in H.special_commands(row):
        presses = H.SPECIAL_LISTS[lst][1]
        num = ''.join({'N': '5', 'U': '8', 'D': '2', 'L': '4', 'R': '6', 'DR': '3', 'DL': '1', 'UR': '9', 'UL': '7'}[H.DIRS[d]] for d, _ in cm['motion'])
        rows = [dict(button=p, strength=STRENGTH[p], rel=a, addr=whp.anim_addr(char, a)) for p, a in zip(presses, cm['anims'])]
        out.append(dict(input=num + NOTATION[lst], list=lst, command=cm['index'], motion=cm['motion'], term=cm['term'],
                        rows=rows, distinct=len({r['addr'] for r in rows}),
                        hero=[dict(button=p, rel=a) for p, a in zip(presses, cm['hero'])] if cm['hero'] else None))
    return out

# ---- throws --------------------------------------------------------------------------------------------------------
THROW_TABLES = {'AB': (0x302C4, 0x302E4, 0x31808, 0x31828), 'CD': (0x30344, 0x30364, 0x31848, 0x31868)}
AIR_THROW = (0x30404, 0x30444)
VICTIM_SCRIPT = 0x5D528
def throws(row, char):
    """the row's throws: [dict(chord, dir ('forward' / 'back'), rel, reach_set, count)] (forward = $31AA0 clears the
    count: the table's animation; back = the count kept: count 2 -> + 2) + the air throw"""
    out = []
    for ch, (tc, ta, rf, rb) in THROW_TABLES.items():
        cnt, an = m.u8(tc + row), m.u8(ta + row)
        if not cnt or not an: continue
        out.append(dict(chord=ch, dir='forward', rel=an, count=cnt, reach_set=m.u8(rf + row)))
        out.append(dict(chord=ch, dir='back', rel=an + 2 if cnt == 2 else an, count=cnt, reach_set=m.u8(rb + row)))
    if m.u8(AIR_THROW[0] + row): out.append(dict(chord='AB', dir='air', rel=m.u8(AIR_THROW[1] + row), count=m.u8(AIR_THROW[0] + row), reach_set=None))
    return out

def victim_script(row, table, victim_row, n):
    """command 16's placement entries: [(victim def, dx forward px, dy up px, mode)] for the thrower's steps 0..n-1"""
    a = m.u32(m.u32(VICTIM_SCRIPT) + 64 * row + 4 * table)
    b = m.u32(a + 4 * victim_row)
    return [(m.u16(b + 8 * s), m.s16(b + 8 * s + 4) / 128, m.s16(b + 8 * s + 2) / 128, m.u16(b + 8 * s + 6)) for s in range(n)]

def throw_victim_cmds(char, rel):
    """the throw animation's victim commands: (start anim (relative, the victim's), table, [steps with cmd 16],
    (release step, release anim) from command 18)"""
    E = [e for e in H.entries(char, rel) if e['ctrl'] is None]
    st = [i for i, e in enumerate(E) if any(c == 16 for c, a in e['cmds'])]
    first = next(a for c, a in E[0]['cmds'] if c == 16)
    rel_ = next(((i, int(a, 16)) for i, e in enumerate(E) for c, a in e['cmds'] if c == 18), None)
    return int(first[:4], 16), int(first[4:], 16), st, rel_

# ---- the throw model -------------------------------------------------------------------------------------------------
IMPACT_FLAG = 0x00800000                         # step flags long +$60D4..D7: +$60D5 bit 7 on the throw's damage step
                                                 # [code + meas: the victim's life drops as that step starts]
VICTIM_LYING = 0x1C                              # the thrown flight's landing goes to the lying animation [code: $F0 / $F3
                                                 # step 6, command 24 $1C]
def throw_model(name, rel, victim_row, victim_char, victim_name=None, turn=False):
    """a throw played from the ROM, facing right from x 0: per frame dict(t: the thrower's model frame (handlers_whp.play:
    anim, step, defw, x, y; None once its move is over), v: dict(defw, x, y, anim, step, phase 'held' / 'flight' /
    'down'), impact) + the points (release, land, down, end: frame indices). Held: the victim at the thrower + command
    16's entry for the thrower's step (victim def, dx forward, dy up); from command 18's step: the victim plays its
    release animation (handlers_whp.play of the victim's character from its place, its x mirrored: it faces the
    thrower, or away when turn: the back throw, +$6E set: $394BA turns the victim at the release; its landing on the
    floor line), until the lying animation."""
    char = H.CHARS[name]; row = H.ROWS[name]
    t = H.play(name, rel, hooks=False)
    vstart, table, held_steps, (rel_step, rel_anim) = throw_victim_cmds(char, rel)
    nst = max(held_steps) + 1
    script = victim_script(row, table, victim_row, nst)
    E = [e for e in H.entries(char, rel) if e['ctrl'] is None]
    out = []; release = None; vname = victim_name or name
    for k, r in enumerate(t):
        if r['anim'] != rel or r['step'] >= rel_step:
            release = k; break
        d, dx, dy, mode = script[min(r['step'], nst - 1)]
        assert mode == 0, (rel, r['step'], mode)
        first = k == 0 or t[k - 1]['step'] != r['step']
        out.append(dict(t=r, v=dict(defw=d, x=r['x'] + dx, y=r['y'] + dy, anim=vstart, step=0, phase='held'),
                        impact=first and bool(E[r['step']]['flags'] & IMPACT_FLAG)))
    x0, y0 = out[-1]['v']['x'], out[-1]['v']['y']
    fl = H.play(vname, rel_anim, hooks=False, y0=y0); sgn = 1 if turn else -1
    v = []
    for q in fl:
        if q['anim'] == VICTIM_LYING:
            v.append(dict(defw=q['defw'], x=x0 + sgn * q['x'], y=0.0, anim=q['anim'], step=q['step'], phase='down')); break
        v.append(dict(defw=q['defw'], x=x0 + sgn * q['x'], y=q['y'], anim=q['anim'], step=q['step'], phase='flight'))
    land = next((i for i, q in enumerate(v) if i and q['anim'] == rel_anim and v[i - 1]['step'] < 4 <= q['step']), None)
    n = max(len(t) - release, len(v))
    for i in range(n):
        r = t[release + i] if release + i < len(t) else None
        out.append(dict(t=r, v=v[min(i, len(v) - 1)], impact=False))
    return {'frames': out, 'release': release, 'land': release + land if land is not None else None,
            'down': release + len(v) - 1, 'end': len(t), 'rel': rel, 'release_anim': rel_anim, 'victim_start': vstart,
            'table': table}

if __name__ == '__main__':
    row, char = 1, 0
    print('run immediates', {k: [hex(x) for x in v] for k, v in check_run_immediates().items()})
    for n in normals(row, char):
        print(f"{n['button']:2s} {n['strength']:4s} {n['stance']:10s} ${n['rel']:03X} @{n['addr']:X}"
              f"{'  = ' + n['same_as'] if n['same_as'] else ''}{'  close < %.0f px' % n['close_px'] if 'close_px' in n else ''}  -> {brawler_name(n)}")
    for s in specials(row, char):
        print(s['input'], s['command'], [(r['button'], r['strength'], hex(r['rel'])) for r in s['rows']], 'distinct', s['distinct'], 'hero', s['hero'])
    for t in throws(row, char):
        print('throw', t, throw_victim_cmds(char, t['rel']))
