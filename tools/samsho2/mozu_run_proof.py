#!/usr/bin/env python3
"""The run Mozu Otoshi's whistle in the brawler vs SS2 (note 20261016-100735-e03d round 2; mozu_ss2.py RUN / whistle:
SS2's $1C $4E, sent by the brake the frame before the catch, reaches the Z80 13 frames after it). The note's own recipe
(tools/brawler/scenarios.json: the Lab, Hanzo runs into Ryo with a full drive bar), in our emulator (harness.py): per
frame P1's state, the bytes sound.c writes to the Z80's latch (its ring: q / qh) and every ADPCM-A key-on the Z80
makes (the Z80 port tap: start / end pages); the key-on whose sample bytes are SS2's $1C $4E sample (pages 22334-22348
of SS2's V ROM, the pages its own driver keys on: voices.probe) and its frame from the grab (the frame before the
special's first) vs SS2's from its catch.

    python3 mozu_run_proof.py [ROM] [OUT]      (default examples/brawler/brawler.neo, /data/tmp/mozu_whistle)
-> OUT/proof.json"""
import ctypes as C, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import harness, voices as V, scenario as SC
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
NOTE = '20261016-100735-e03d'
SS2_PAGES = (22334, 22348)                      # $1C $4E: record $54ED + 11 x $4E (slot 2), keyed by SS2's own driver
SS2_LATCH = 13                                  # its code byte at the Z80, frames after the catch (mozu_ss2.py whistle)

def v_of(rom):
    d = open(rom, 'rb').read(); h = struct.unpack('<6I', d[4:28]); o = 0x1000 + h[0] + h[1] + h[2]
    return d[o:o + h[3] + h[4]]

def main(rom, out):
    rec = SC.recipes()[NOTE]
    b = harness.Brawler(rom=rom); S = b.syms; b.game = SC.GAME
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
    states, latch = {}, []
    qh = b.r(S['qh'], 1)
    seq = [(int(n), k.replace('-', '')) for n, k in (p.split(':') for p in rec['do_keys'].split(',') if p)] + [(int(rec['proof']), '')]
    for n, k in seq:
        for _ in range(n):
            b.run(1, p1=k)
            states[b.frame] = b.states[b.fget(0, 'state')]
            h = b.r(S['qh'], 1)
            while qh != h: latch.append((b.frame, b.r(S['q'] + qh, 1))); qh = (qh + 1) & 31
    sp = min(f for f, s in states.items() if s == 'SPECIAL'); grab = sp - 1
    sv, bv = V.v_rom('samsho2'), v_of(rom)
    want = sv[SS2_PAGES[0] << 8:(SS2_PAGES[1] + 1) << 8]
    rows = [{'frame': f - grab, 'ch': ch, 'pages': [s, e], 'bytes': (e - s + 1) << 8,
             'equal_ss2_1C4E': bv[s << 8:(e + 1) << 8] == want} for f, ch, s, e in keys if f >= grab - 5]
    hit = [r for r in rows if r['equal_ss2_1C4E']]
    lat = [[f - grab, f'{x:02X}'] for f, x in latch if f >= grab - 5]
    res = {'rom': rom, 'grab_frame': grab, 'special_first_frame': 1, 'keyons': rows, 'latch': lat,
           'whistle': hit[0] if hit else None, 'ss2_latch_frame': SS2_LATCH,
           'ok': len(hit) == 1 and hit[0]['frame'] - SS2_LATCH in (0, 1)}   # (the Z80 keys on in the frame it reads the
    os.makedirs(out, exist_ok=True)                                         # code, or the next)
    json.dump(res, open(os.path.join(out, 'proof.json'), 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('grab_frame', 'whistle', 'ss2_latch_frame', 'ok')}))
    print('latch', lat[:40]); print('keyons', [(r['frame'], r['pages'], r['equal_ss2_1C4E']) for r in rows][:20])
    return res['ok']

if __name__ == '__main__':
    a = sys.argv[1:]
    sys.exit(0 if main(a[0] if a else os.path.join(SC.GAME, 'brawler.neo'), a[1] if len(a) > 1 else '/data/tmp/mozu_whistle') else 1)
