#!/usr/bin/env python3
"""Double Dragon's hit sparks and its super-hit screen flash (TODO #215), read in the 68000 code; checked against the
game in our emulator (emu/neogeo_sdl --capture).

    python3 sparks_dd.py [OUT.json]     (default /data/neogeo_dict/doubledr/sparks215.json: every hit of Billy, Super
                                         Billy and Cheng-Fu's specials / supers / far normals, DD vs this rule)

The spark [code]+[meas]
- Every body hit spawns one effect object (the effects module at $50000: its spawn $52302 through the jump $50066, called
  from the hit code at $263F4; a guarded hit at $265A4 with its own types 19-21; a projectile's hit spawns none: the
  object plays its own end). d0 = the type: byte[$265F2 + 4 * index + height], index = the hit's reaction index
  (export_dd.dd_reactions: the hitting step's level, the victim's combo stun, the move's category; + 2 instead of the
  combo stun when the victim is held: +$F3 bit 5, $25DCE, Cheng-Fu's super 623 flurry), height = the hitting record's
  byte 1 bits 2-3 (+$E0). Rows: 1 2 3 1 / 4 5 6 4 / 7 8 9 7 / 10 11 12 10 / 13 14 15 13 (index 4-7). Facing: the
  attacker's (d0 bit 15 = +$01 bit 5, facing left); height class 3 turns it ($263E8).
- Place (+$E2 / +$E4 of the attacker, $26AE8): x = the victim's body record's centre + half its half width toward the
  attacker, y = the attacker's attack record's centre (world).
- Script (table $52364 + 4 type): [frames w][definition w] pairs, 0 ends ($5022C); types 1-18 are 19 frames
  (4 + 5 x 3). Velocity (table $526D4 + 4 type, 8.8 px a frame: vx along its facing, vy down +); each frame
  ($522D6, from its spawn frame on): x += vx, y += vy, then 0.25 px of friction on each (+$6A = $4000; vx reaching 0
  stops both). Palette: types under 19 cycle 128-131, 128 + (frames alive & 3) ($52684); the tiles' own otherwise.
  Drawn like a fighter (dd.draw_def at its place, its facing), in front.
The flash [code]+[meas]
- A hit by a fighter whose +$F3 bit 3 is set (a super, the transformation: set by the recogniser $244C4 / $244FE)
  sets bit 7 of both fighters' hit-stop counters (+$2E: $25EFA, $88 = 8 frames). Each frame with bit 7 ($203BE) puts
  2 in $106DDE (a KO's hit: white $7FFF instead of red $4F00 in $108E7A); the vblank task ($3A8A) toggles every 2
  frames between filling every stage palette and the backdrop with that colour ($60B0) and restoring them ($60E8).
  Measured: red on the frames hit + 2, + 3, + 6, + 7 (the hit = the frame the victim's damage changes), the fighters and
  the HUD in their own colours. Not modelled in the brawler: the KO's white (64 frames) and the dizzy's 24 red frames."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dd

SCRIPTS, VELOCITY, TYPES = 0x52364, 0x526D4, 0x265F2
FRICTION = 0.25
NTYPES = 18                                       # body hits (the guard sparks 19-21, Dulton / Burnov's 22 / 23: not here)
FLASH_COL = 0x4F00                                # $20424 (the KO's: $7FFF)
FLASH_FRAMES = 8                                  # the hit-stop's count ($88 & $7F)

def script(t):
    """[(definition, frames)]"""
    p = dd.u32(SCRIPTS + 4 * t); out = []
    while dd.u16(p):
        out.append((dd.u16(p + 2), dd.u16(p))); p += 4
    return out

def velocity(t): return dd.s16(VELOCITY + 4 * t) / 256, dd.s16(VELOCITY + 4 * t + 2) / 256

def spark_type(index, height):
    """-> (type, turned): the type its hit spawns, turned = drawn / moving the other way (height class 3)"""
    return dd.u8(TYPES + 4 * min(index, 7) + height), height == 3

def track(t):
    """per frame alive (0 = the spawn frame): (definition, palette slot, dx forward, dy down) from the spawn point"""
    vx, vy = velocity(t); x = y = 0.0; out = []
    frames = [w for w, n in script(t) for _ in range(n)]
    for k, w in enumerate(frames):
        x += vx; y += vy
        if vx:                                    # ($52624: vx 0 skips both; one crossing 0 clears both / vy)
            nvx = vx - FRICTION if vx > 0 else vx + FRICTION
            if (nvx < 0) != (vx < 0) and nvx: vx = vy = 0.0
            else:
                vx = nvx
                if vy:
                    nvy = vy - FRICTION if vy > 0 else vy + FRICTION
                    vy = 0.0 if (nvy < 0) != (vy < 0) and nvy else nvy
        out.append((w, 128 + (k & 3) if t < 19 else None, x, y))
    return out

# ---- the check against the game ------------------------------------------------------------------------------------
P1, P2 = 0x10042A, 0x10052A
STATES = {0: '/data/neogeo_dict/doubledr/cap/vs.state', 1: '/data/neogeo_dict/doubledr/cap/p1_01.state',
          10: '/data/neogeo_dict/doubledr/cap/p1_10.state'}
POWER = ';'.join(f'{f}:10042A=81' for f in range(1, 80))

def _g(R, a, n=1, signed=False):
    o = a - 0x100000; v = int.from_bytes(R[o:o + n], 'big')
    return v - (1 << 8 * n) if signed and v >> (8 * n - 1) else v

FAR = ';'.join(f'{f}:100530=03,100531=00' for f in range(1, 400))   # P2 kept at x 768: the whiff

def capture(ch, seq, powered=False, far=False, snaps=None):
    """per frame: P1's animation / step, hit (P2's damage changed), sparks born (type, facing left, x, y, definition,
    palette), the backdrop; snaps: frames whose screen goes to /data/tmp/dd95/snap_<frame>.ppm"""
    import cap_dd
    pokes = ';'.join(x for x in (POWER if powered else '', FAR if far else '') if x) or None
    rows = cap_dd.run(seq, load=STATES[ch], pokes=pokes, vram=True, snaps=snaps)
    out, prev, alive = [], None, set()
    for r in rows:
        R = r['ram']; F = dd.fighter_fields(R, P1); dmg = _g(R, P2 + 0x26, 2)
        born, now, objs = [], set(), {}
        for k in range(22):
            b = 0x10062A + 256 * k
            if not R[b - 0x100000] & 0x80 or not 0x523C4 <= _g(R, b + 0x7E, 4) <= 0x52700: continue
            t = R[b + 0x53 - 0x100000]; age = _g(R, b + 0x50, 2); now.add(k)
            o = [t, bool(R[b + 1 - 0x100000] & 0x20), _g(R, b + 6, 4, True) / 65536, _g(R, b + 0xA, 4, True) / 65536,
                 _g(R, b + 4, 2), R[b + 3 - 0x100000], k]
            objs[k] = o
            if (t < 19 and age == 1) or (t >= 19 and k not in alive): born.append(o)
        alive = now
        out.append({'f': r['f'], 'anim': F['anim'], 'step': F['step'], 'hit': prev is not None and dmg != prev,
                    'e2': _g(R, P1 + 0xE2, 2, True), 'e4': _g(R, P1 + 0xE4, 2, True), 'x': F['x'], 'y': F['y'], 'vx': dd.fighter_fields(R, P2)['x'], 'left': bool(F['dir'] & 0x20),
                    'born': born, 'objs': objs, 'bd': r['pal'][0x1FFE] << 8 | r['pal'][0x1FFF]})
        prev = dmg
    return out

def moves(ch):
    """(name, keys, powered, the brawler's states: export_dd SPECIALS / MOVES) of the moves checked"""
    import commands_dd as CM, specials_dd as SD, export_dd as E
    out = []
    for name, (anims, _) in E.SPECIALS[ch].items():
        if name == 'FORM': continue
        sup = name.startswith('SUPER')
        note = name.split()[-1] + '+ABCD'
        e = next(e for e in CM.entries(ch) if CM.notation(e) == note and bool(e['flags'] & 4) == sup)
        for k, a in enumerate(anims):
            btn = 'a' if sup else 'abcd'[k]
            out.append((f'{name} {"ABCD"[k] if len(anims) > 1 else ""}'.strip(), '30:R,12:-,' + SD.inputs(e, btn) + ',170:-', sup, a))
    for b in 'bcd':                               # the far normals (A whiffs from 58 px)
        out.append((f'far {b.upper()}', '30:R,12:-,3:' + b + ',80:-', False, {'b': 18, 'c': 20, 'd': 22}[b]))
    return out

def predict(ch, a0):
    """per (anim, step) of the move's hits: (type, turned, flash) by the rule (export_dd.spark_codes)"""
    import export_dd as E
    if a0 in (18, 20, 22): return E.spark_codes(ch, E.chain(ch, a0), set(), False)   # (Cheng-Fu's far D: 22 > 43, a hop kick)
    states, caught = E.special_states(ch, a0)
    return E.spark_codes(ch, states, caught, E.is_super(ch, a0))

def check(out_path):
    res = {}
    for ch in (0, 1, 10):
        for name, seq, sup, a0 in moves(ch):
            rows = capture(ch, seq, sup); pred = predict(ch, a0)
            hits = []
            for i, r in enumerate(rows):
                if not r['hit']: continue
                red = [j - i for j in range(i, min(i + 12, len(rows))) if rows[j]['bd'] == FLASH_COL]
                want = pred.get((r['anim'], r['step']))
                got = r['born'][0] if r['born'] else None
                ok = want is not None and got is not None and got[0] == want[0] and got[1] == (r['left'] ^ want[1]) and \
                    bool(red) == want[2] and (not red or red == [2, 3, 6, 7])
                if want is None and got is None: ok = True       # (a projectile's hit: no spark, none predicted)
                life = []                                        # its life: definition, palette, place from the hit
                if got:                                          # point vs sparks_dd.track (x along its facing)
                    sgn = -1 if got[1] else 1
                    for j in range(i, len(rows)):
                        o = rows[j]['objs'].get(got[6])
                        if not o or o[0] != got[0]: break
                        life.append([o[4], o[5], round(sgn * (o[2] - r['e2']), 3), round(o[3] - r['e4'], 3)])
                    tr = [[w, pal, round(x, 3), round(y, 3)] for w, pal, x, y in track(got[0])]
                    life = life[:len(tr)]
                    track_ok = life == tr[:len(life)] and len(life) == len(tr)
                    ok = ok and track_ok
                hits.append({'frame': r['f'], 'anim': r['anim'], 'step': r['step'], 'dd': got, 'red': red,
                             'rule': list(want) if want else None, 'place': [r['e2'], r['e4']], 'life': life,
                             'track': life == tr if got else None, 'ok': ok})
            res[f'{ch} {name}'] = hits
            print(ch, name, 'ok' if all(h['ok'] for h in hits) else 'FAIL', [(h['anim'], h['step'], h['dd'] and h['dd'][0], h['rule'] and h['rule'][0], h['red']) for h in hits], flush=True)
    json.dump(res, open(out_path, 'w'), indent=1)
    bad = [k for k, v in res.items() if not all(h['ok'] for h in v)]
    print('ALL OK' if not bad else f'FAIL {bad}')
    return res

if __name__ == '__main__':
    check(sys.argv[1] if len(sys.argv) > 1 else '/data/neogeo_dict/doubledr/sparks215.json')
