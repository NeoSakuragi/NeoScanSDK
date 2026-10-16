#!/usr/bin/env python3
"""The run Mozu Otoshi's whistle in the brawler vs SS2 (note 20261016-100735-e03d; mozu_ss2.py RUN / whistle). Round 3
(Bruno on 0.10.140's $1C $4E: "it's a sound effect, not Hanzo's voice"): the whistle is SS2's shared effect $1A $2B,
queued at the leap and every 5 frames; SS2's Z80 gets it at catch + 15 17 19 21 23 27 32 37 42 47 52 (WANT). The
note's own recipe (tools/brawler/scenarios.json: the Lab, Hanzo runs into Ryo with a full drive bar), in our emulator
(harness.py): per frame P1's state, the bytes sound.c writes to the Z80's latch (its ring: q / qh) and every ADPCM-A
key-on the Z80 makes (the Z80 port tap: start / end pages); each key-on whose sample bytes are SS2's $1A $2B sample
(its pages in SS2's V ROM, keyed by SS2's own driver: voices.probe) and its frame from the grab (the frame before the
special's first) vs SS2's from its catch; and no key-on of SS2's $1C $4E (the dropped voice).

    python3 mozu_run_proof.py [ROM] [OUT]      (default examples/brawler/brawler.neo, /data/tmp/mozu_whistle)
-> OUT/proof.json"""
import ctypes as C, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import harness, voices as V, scenario as SC
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
NOTE = '20261016-100735-e03d'
WANT = [15, 17, 19, 21, 23, 27, 32, 37, 42, 47, 52]   # $1A $2B's code byte at SS2's Z80, frames after the catch
VOICE_PAGES = (22334, 22348)                          # $1C $4E (round 2's voice, dropped)

def v_of(rom):
    d = open(rom, 'rb').read(); h = struct.unpack('<6I', d[4:28]); o = 0x1000 + h[0] + h[1] + h[2]
    return d[o:o + h[3] + h[4]]

def main(rom, out):
    rec = SC.recipes()[NOTE]
    seg = V.probe('samsho2', {0x1A2B})[0x1A2B]['segments'][0]
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
    want = sv[seg[0] << 8:(seg[1] + 1) << 8]; vwant = sv[VOICE_PAGES[0] << 8:(VOICE_PAGES[1] + 1) << 8]
    rows = [{'frame': f - grab, 'ch': ch, 'pages': [s, e], 'bytes': (e - s + 1) << 8,
             'whistle': bv[s << 8:(e + 1) << 8] == want, 'voice_1C4E': bv[s << 8:(e + 1) << 8] == vwant} for f, ch, s, e in keys if f >= grab - 5]
    got = [r['frame'] for r in rows if r['whistle']]
    lat = [[f - grab, f'{x:02X}'] for f, x in latch if f >= grab - 5]
    res = {'rom': rom, 'grab_frame': grab, 'ss2_pages_1A2B': seg, 'keyons': rows, 'latch': lat,
           'whistle_keyons': got, 'ss2_latch_frames': WANT,
           'voice_keyons': [r['frame'] for r in rows if r['voice_1C4E']],
           'ok': len(got) == len(WANT) and all(g - w in (0, 1) for g, w in zip(got, WANT)) and not any(r['voice_1C4E'] for r in rows)}
    # (the Z80 keys on in the frame it reads the code, or the next)
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'proof.json'), 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('grab_frame', 'whistle_keyons', 'ss2_latch_frames', 'voice_keyons', 'ok')}))
    return res['ok']

if __name__ == '__main__':
    a = sys.argv[1:]
    sys.exit(0 if main(a[0] if a else os.path.join(SC.GAME, 'brawler.neo'), a[1] if len(a) > 1 else '/data/tmp/mozu_whistle') else 1)
