#!/usr/bin/env python3
"""Haohmaru's tornado voice in the brawler vs Samurai Shodown II (note 20261016-131850-e03d rounds 3-4; Bruno, round 4:
"now it's a little too slow, check the timing of the sound in the original game and apply the same timing here").
Ougi Senpuu Retsuzan (down + C, SS2 236AB) says two samples, SS2's $1A $90 and $1A $91.
SS2 (`ss2`): the move from Haohmaru's vs state (cap/p1_00.state) in our emulator (the tap core, makoto3/capture.py
Sound): the commands the Z80 reads and every ADPCM-A key-on (channel, sample bytes vs voices.json's), timed from the
special's first frame (P1 class 1 action 43, +$E6 / +$E7). Measured: $1A $90 keyed at +1 (channel 3), $1A $91 at +41
(channel 5): 40 frames apart, the first (60.5 frames) still sounding: SS2 overlaps its two parts, nothing is cut.
The brawler: the note's recipe (tools/brawler/scenarios.json, the Lab) in our emulator (harness.py): every ADPCM-A
key-on the Z80 makes (the Z80 port tap), each matched to SS2's two samples by its bytes (SS2's V ROM pages,
voices.json), timed from the special's first frame; and the frame the tornado leaves (its projectile's first frame).
OK: both parts keyed on once, the second as many frames after the first as in SS2, the tornado on TORNADO frames
after the special's first.

    python3 tornado_voice_proof.py [ROM] [OUT]      (default examples/brawler/brawler.neo, /data/tmp/tornado_voice)
    python3 tornado_voice_proof.py ss2 [OUT]        SS2 alone -> OUT/ss2.json
-> OUT/proof.json (+ OUT/ss2.json)"""
import ctypes as C, json, os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import harness, voices as V, scenario as SC
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
NOTE = '20261016-131850-e03d'
FPS = 59.185                                          # the MVS frame rate
PARTS = ('1A90', '1A91')
TORNADO = 16                                          # the tornado's frame from the special's first (0.10.143, measured)

def v_of(rom):
    d = open(rom, 'rb').read(); h = struct.unpack('<6I', d[4:28]); o = 0x1000 + h[0] + h[1] + h[2]
    return d[o:o + h[3] + h[4]]

SS2_STATE = '/data/neogeo_dict/samsho2/cap/p1_00.state'          # Haohmaru P1 (mkvs.py)
SS2_SEQ = '11:-,3:D,3:DR,3:R,3:Rab,200:-'                           # 236 + A+B (moves/00.json cmd14)
SS2_SPECIAL = (1, 43)                                              # P1 +$E6 / +$E7 while the tornado special runs

def wanted():
    vj = {v['cmd']: v for v in json.load(open(V.JSON))['fighters']['haohmaru']['voices']}
    sv = V.v_rom('samsho2')
    return {c: V.sample_bytes(sv, vj[c]['segments']) for c in PARTS}, sv

def ss2(out):
    """SS2's own timing (module docstring) -> OUT/ss2.json"""
    sys.path.insert(0, os.path.join(HERE, '..', 'makoto3'))
    import capture as K, cap_ss2 as CS
    want, sv = wanted()
    s = K.Sound(rom=CS.NEO); s.load(open(SS2_STATE, 'rb').read())
    c = s.core; c.retro_get_memory_data.restype = C.c_void_p; c.retro_get_memory_size.restype = C.c_size_t
    ram = (C.c_uint8 * c.retro_get_memory_size(2)).from_address(c.retro_get_memory_data(2))
    keys, cmds, reg = [], [], {}
    def tap(write, port, v):
        p = port & 0xFF
        if write and p == 6: tap.a = v
        elif write and p == 7:
            if tap.a == 0 and v and not v & 0x80:
                for ch in range(6):
                    if v >> ch & 1:
                        keys.append((s.frame, ch, reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0),
                                     reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)))
            reg[tap.a] = v
        elif not write and p == 0 and v: cmds.append((s.frame, v))
        return v
    tap.a = 0; s._cbs[6] = K.TAP(tap); c.retro_neoscan_z80_tap(s._cbs[6])
    s.run(1); a1 = CS.players(bytes(ram))[0] - 0x100000
    st = {}
    for part in SS2_SEQ.split(','):
        n, k = part.split(':')
        for _ in range(int(n)): s.run(1, k); st[s.frame] = (ram[a1 + 0xE6], ram[a1 + 0xE7])
    sp = min(f for f, x in st.items() if x == SS2_SPECIAL)
    end = min(f for f, x in st.items() if f > sp and x != SS2_SPECIAL)
    rows = [{'frame': f - sp, 'ch': ch, 'pages': [a, e], 'part': next((p for p in PARTS if sv[a << 8:(e + 1) << 8] == want[p]), None)}
            for f, ch, a, e in keys if f >= sp]
    res = {'special_frames': end - sp, 'commands': [[f - sp, f'{v:02X}'] for f, v in cmds if f >= sp],
           'keyons': rows, 'part_keyons': {p: [r['frame'] for r in rows if r['part'] == p] for p in PARTS},
           'part_channels': {p: [r['ch'] for r in rows if r['part'] == p] for p in PARTS}}
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'ss2.json'), 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('special_frames', 'part_keyons', 'part_channels')}))
    return res

def main(rom, out):
    subprocess.run([sys.executable, os.path.abspath(__file__), 'ss2', out], check=True)   # (one core per process)
    s2 = json.load(open(os.path.join(out, 'ss2.json')))
    rec = SC.recipes()[NOTE]
    want, sv = wanted()
    b = harness.Brawler(rom=rom); b.game = SC.GAME
    keys, reg = [], {}
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 6: tap.a = v
            elif p == 7:
                if tap.a == 0 and v and not v & 0x80:
                    for ch in range(6):
                        if v >> ch & 1:
                            keys.append((b.frame, ch, reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0),
                                         reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)))
                reg[tap.a] = v
        return v
    tap.a = 0; cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    SC.setup(b, rec)
    states, proj = {}, {}
    for n, k in [(2, 'Dc'), (200, '')]:                # the recipe's first press: down + C, then hands off
        for _ in range(n):
            b.run(1, p1=k)
            states[b.frame] = b.states[b.fget(0, 'state')]
            proj[b.frame] = any(b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'pdef') for i in range(8))
    sp = min(f for f, s in states.items() if s == 'SPECIAL')
    end = min(f for f, s in states.items() if f > sp and s != 'SPECIAL')
    shot = min(f for f, p in proj.items() if p and f >= sp)
    bv = v_of(rom)
    rows = []
    for f, ch, s, e in keys:
        if f < sp - 2: continue
        got = bv[s << 8:(e + 1) << 8]
        part = next((c for c in PARTS if got == want[c]), None)
        rows.append({'frame': f - sp, 'ch': ch, 'pages': [s, e], 'part': part})
    on = {c: [r['frame'] for r in rows if r['part'] == c] for c in PARTS}
    lens = {c: round(len(want[c]) * 2 / V.RATE * FPS, 1) for c in PARTS}
    gap = lambda k: k[PARTS[1]][0] - k[PARTS[0]][0]
    ok = all(len(on[c]) == 1 and len(s2['part_keyons'][c]) == 1 for c in PARTS) and gap(on) == gap(s2['part_keyons']) and \
        (TORNADO is None or shot - sp == TORNADO)
    res = {'rom': rom, 'special_frame': sp, 'special_frames': end - sp, 'tornado_frame': shot - sp, 'keyons': rows,
           'part_keyons': on, 'ss2_part_keyons': s2['part_keyons'], 'gap': gap(on), 'ss2_gap': gap(s2['part_keyons']),
           'part_frames': lens,
           'part_ms': {c: round(len(want[c]) * 2 / V.RATE * 1000) for c in PARTS}, 'ok': ok}
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'proof.json'), 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('special_frames', 'tornado_frame', 'part_keyons', 'ss2_part_keyons', 'gap', 'ss2_gap', 'part_frames', 'ok')}))
    return ok

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['ss2']: ss2(a[1] if len(a) > 1 else '/data/tmp/tornado_voice'); sys.exit()
    sys.exit(0 if main(a[0] if a else os.path.join(SC.GAME, 'brawler.neo'), a[1] if len(a) > 1 else '/data/tmp/tornado_voice') else 1)
