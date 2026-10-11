#!/usr/bin/env python3
"""Samurai Shodown II's impact sounds (voice note 20261011-055133-5d29, Bruno on Hanzo's strong slash: "this attack in
Samurai Shodown 2 has a specific distinct sound for impact, the big slash sound"). Read in the 68000 code [code] and
measured in our emulator [meas]:

- A hit (routine $BC1A) starts the hit mark ATR-MARK ($C724), whose first run ($C914) sends the sounds: the victim's
  hurt voice ($5BA4, d1 = 3: the victim's voice list; P2 Haohmaru's $1C $19 in the captures) and the IMPACT: the
  attacker's +$10B & $7F -> byte $C99C[...]; bit 7 set = a sound id itself, else an impact class -> $5A9C: list long
  $5AC4[class] = [mask word][base id word][mask + 1 bytes]: id = base + byte[RNG ($A84E) & mask] -> word $5FD2[id]
  (the driver command, sent by $5FB0). A guarded hit ($C91C, +$FD set) takes the guard tables $C9B0 / $C9C4 / $C9D8.
- +$10B is the FLAG BYTE of the action entry the move plays ($277BC: the entry [flag][handler 24 bits][word] of the
  action table $28310, commands_ss2.descriptor): the impact sound is the MOVE's, not the attack box's type (the type
  picks the hit mark only). The same byte picks the whiff swing at the move's start ($275D6: $C9EC[byte] -> $5A9C).
- Classes (ids -> SS2 driver one-byte ADPCM-A commands $C0-$FF: code $6D8A[cmd - $C0], record slot 0 $3EED + 11 code):
  0 cut S $C0 $C1 $C2 (mask 3: $C0 twice), 1 cut L $C3-$C8 (mask 7: $C3 $C4 twice), 2 cut M $C9 $CA $CB (mask 3),
  3 blunt $D1 $D2 (mask 3: 1 2 2 1), 4 kick $D3, 5 the whiff swing $CC, 6 $D4-$D6, 7 $CD-$CF.

    python3 hitsound_ss2.py ss2 [OUT]          Haohmaru / Genjuro / Hanzo close A / B / A+B / D against P2 Haohmaru in
                                               SS2 (capture_cmds.py's vs states, P2 at 56 px): the sound commands on the
                                               hit's frames, the attacker's +$10B -> OUT/ss2_hits.json
    python3 hitsound_ss2.py table              per fighter: each brawler move's SS2 impact (hit_sound: export_ss2's 'ss2snd')
OUT default /data/tmp/ss2sound."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import neo2 as N

IMPACT = 0xC99C                       # +$10B & $7F -> impact class (bit 7: a sound id)
CLASSES = 0x5AC4                      # class -> [mask][base id][bytes]
SOUND_WORD = 0x5FD2                   # id -> driver command word ($5F5E queue)
NAMES = {0: 'SLASH S', 1: 'SLASH L', 2: 'SLASH M', 3: 'BLUNT', 4: 'KICK'}   # the classes the fighters' normals use

def impact_cmds(flag):
    """the driver commands one hit of a move with action flag byte `flag` sends as its impact, in SS2's pick list
    (a power-of-two list: SS2 picks list[RNG & mask]); [] = none"""
    k = flag & 0x7F
    if not k: return []
    c = N.u8(IMPACT + k)
    if c & 0x80: return [N.u16(SOUND_WORD + 2 * c)]
    t = N.u32(CLASSES + 4 * c); mask, base = N.u16(t), N.u16(t + 2)
    return [N.u16(SOUND_WORD + 2 * (base + N.u8(t + 4 + i))) for i in range(mask + 1)]

def impact_class(flag):
    k = flag & 0x7F
    return None if not k or N.u8(IMPACT + k) & 0x80 else N.u8(IMPACT + k)

_flags = {}
def action_flag(ch, anim):
    """the flag bytes of the action entries that play animation `anim` (every table of the fighter, both weapon
    modes; [] if none: a specials' animation may be played by entries of several flags)"""
    if ch not in _flags:
        import commands_ss2 as K
        m = _flags[ch] = {}
        for mode in (0, 1):
            for cls in range(8):
                for sub in range(64):
                    try: d = K.descriptor(ch, mode, cls, sub)
                    except ValueError: d = None            # (sub past the table's end: not a descriptor)
                    for f, h, w in (d['entries'] if d else []):
                        if not w & 0x8000 and f: m.setdefault(w & 0x3FF, set()).add(f)
    return sorted(_flags[ch].get(anim, ()))

def hit_sound(ch, anim):
    """the impact a hit of animation `anim` sends in SS2: its pick list of driver commands ('00C3', ...); None when no
    action entry plays it or its entries' impacts differ (Haohmaru's 230: flags 4 and 15, both class 3: one list)"""
    lists = {tuple(impact_cmds(f)) for f in action_flag(ch, anim)} - {()}
    return [f'{w:04X}' for w in lists.pop()] if len(lists) == 1 else None

def ss2(out):
    import capture_cmds as K
    obj_row = K.obj_row
    K.obj_row = lambda o: dict(obj_row(o), b10b=o[0x10B])
    jobs = [('close_a', '3:a'), ('close_b', '3:b'), ('close_ab', '3:ab'), ('close_d', '3:d')]
    res = {}
    for name, ch in (('haohmaru', 0), ('genjuro', 12), ('hanzo', 2)):
        st = f'{K.STA}/p1_{ch:02d}.state'; d0 = '/data/tmp/samsho2/cc_probe'   # (capture_cmds.run_char, the jobs alone)
        K.C.run(d0, '3:-', load=st, vram=False, sndlog=False); r0 = K.C.ram(d0, 1); a1, a2 = K.C.players(r0)
        rows = K._run_chunk([(n, s, None) for n, s in jobs], st, r0, a1, a2, ch)
        for m in rows:
            r = m['rows']; anims = []
            for x in r:
                if not anims or anims[-1] != x['p1']['a']: anims.append(x['p1']['a'])
            atk = next((a for a in anims if a >= 200), None)
            hit = [(x['f'], [f'{v:02X}' for v in x['snd']]) for x in r if x['snd'] and x['f'] > 15]
            flag = next((x['p1']['b10b'] for x in r if x['p1']['a'] == atk), None)
            res.setdefault(name, {})[m['name']] = {
                'anim': atk, 'b10b': flag, 'class': impact_class(flag or 0), 'impact_list': [f'{w:04X}' for w in impact_cmds(flag or 0)],
                'action_flag_rom': action_flag(ch, atk) if atk is not None else None, 'sounds_after_swing': hit}
            print(name, m['name'], res[name][m['name']], flush=True)
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'ss2_hits.json'), 'w'), indent=1)

def table():
    import export_ss2 as X
    for name, ch in X.CAST.items():
        if name == 'kuroko': continue
        print(name, {mv: hit_sound(ch, a) for mv, (a, _, _) in X.MOVES.items() if mv.startswith('atk_') or mv == 'body_toss'})

if __name__ == '__main__':
    a = sys.argv[1:] or ['table']
    if a[0] == 'ss2': ss2(a[1] if len(a) > 1 else '/data/tmp/ss2sound')
    else: table()
