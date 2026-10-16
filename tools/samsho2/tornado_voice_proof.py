#!/usr/bin/env python3
"""Haohmaru's tornado voice in the brawler (note 20261016-131850-e03d round 3; Bruno: "since we sped up the startup,
Haohmaru's voice for this special is split in two and the second part overlaps the first"). Ougi Senpuu Retsuzan
(down + C, SS2 236AB) says two samples: SS2's $1A $90 at its first frame and $1A $91 later. The note's recipe
(tools/brawler/scenarios.json, the Lab) in our emulator (harness.py): every ADPCM-A key-on the Z80 makes (the Z80 port
tap), each matched to SS2's two samples by its bytes (SS2's V ROM pages, voices.json), timed from the special's first
frame; and the frame the tornado leaves (its projectile's first frame). OK: both parts keyed on once, the second no
sooner than the first's length (no cut, no overlap), the tornado on TORNADO frames after the special's first.

    python3 tornado_voice_proof.py [ROM] [OUT]      (default examples/brawler/brawler.neo, /data/tmp/tornado_voice)
-> OUT/proof.json"""
import ctypes as C, json, math, os, struct, sys
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

def main(rom, out):
    rec = SC.recipes()[NOTE]
    vj = {v['cmd']: v for v in json.load(open(V.JSON))['fighters']['haohmaru']['voices']}
    sv = V.v_rom('samsho2')
    want = {c: V.sample_bytes(sv, vj[c]['segments']) for c in PARTS}
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
    ok = all(len(on[c]) == 1 for c in PARTS) and on[PARTS[1]][0] - on[PARTS[0]][0] >= math.ceil(lens[PARTS[0]]) and \
        (TORNADO is None or shot - sp == TORNADO)
    res = {'rom': rom, 'special_frame': sp, 'special_frames': end - sp, 'tornado_frame': shot - sp, 'keyons': rows,
           'part_keyons': on, 'part_frames': lens,
           'part_ms': {c: round(len(want[c]) * 2 / V.RATE * 1000) for c in PARTS}, 'ok': ok}
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'proof.json'), 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('special_frames', 'tornado_frame', 'part_keyons', 'part_frames', 'part_ms', 'ok')}))
    return ok

if __name__ == '__main__':
    a = sys.argv[1:]
    sys.exit(0 if main(a[0] if a else os.path.join(SC.GAME, 'brawler.neo'), a[1] if len(a) > 1 else '/data/tmp/tornado_voice') else 1)
