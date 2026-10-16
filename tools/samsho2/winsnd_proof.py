#!/usr/bin/env python3
"""Haohmaru's win-pose sounds in the brawler vs SS2 (note 20261016-133259-e03d: "some sounds are missing from Haohmaru's
victory pose"). SS2 (winsnd_ss2.py, our emulator): each pose's own sounds, frames from its first animation's first frame
at SS2's Z80 (the round end's shared sounds every pose has, $1E $44 / $18 $7A / $1A $1A / $15 $1A / $63, left out: the
announcer and the round's). The brawler: the stage-1 clear played until each pose shows (tools/brawler/win184_proof
stage_run, a wait per process picks the pose), every ADPCM-A key-on from the pose's first frame (the Z80 port tap) with
its sample bytes; a key-on matches an SS2 sound when its bytes are that word's sample in SS2's V ROM (voices.probe: SS2's
own driver). Before the fix the brawler's poses 1-3 keyed nothing (their voice ids had no sample: export_bm voice_map).

    python3 winsnd_proof.py [OUT]           (default /data/tmp/winsnd/proof; examples/brawler built)   exit 1 on a FAIL
    python3 winsnd_proof.py --one WAIT OUT  (one run, a process of its own: one harness core a process)"""
import ctypes as C, json, os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
SS2 = {   # brawler pose -> SS2's sounds [(word, frame at SS2's Z80 from the pose's first frame)] (winsnd_ss2.py haohmaru)
    0: ('sub 3 (anim 200)', [('1A98', 14)]),
    1: ('subs 0 2 5 (198, the sword, 374)', [('1C11', 1), ('1A23', 11), ('00D0', 89), ('1C12', 128)]),
    2: ('subs 1 7 (202)', [('00D0', 36), ('1C12', 107)]),
    3: ('subs 4 6 (203)', [('1C13', 12), ('00CC', 13), ('00CC', 44), ('1A1B', 85)]),
}

def v_of(rom):
    d = open(rom, 'rb').read(); h = struct.unpack('<6I', d[4:28]); o = 0x1000 + h[0] + h[1] + h[2]
    return d[o:o + h[3] + h[4]]

def one(wait, out):
    import harness as H, scenario as SC, win184_proof as W, voices as V
    words = sorted({w for _, l in SS2.values() for w, _ in l})
    pr = V.probe('samsho2', {int(w, 16) for w in words}); sv = V.v_rom('samsho2')
    want = {w: b''.join(sv[s << 8:(e + 1) << 8] for s, e in pr[int(w, 16)]['segments'][:1]) for w in words}
    b = H.Brawler(); W._B = b
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
    S0 = SC.setup
    def setup(bb, rec):
        rec['setup']['wait'] = wait; return S0(bb, rec)
    SC.setup = setup
    frames = []
    def hook(bb, row): frames.append((row['t'], bb.frame))
    b0, log, _ = W.stage_run('haohmaru', shots_every=100000, extra=('wan', 'wpose'), hook=hook)
    fr = dict(frames)
    pr_ = [r for r in log if r['phase'] == 4 and r['mode'] == 1 and r['p0'].get('wan')]
    k = pr_[0]['p0']['wpose']; f0 = fr[pr_[0]['t']]
    bv = v_of(os.path.join(H.GAME, 'brawler.neo'))
    got = []
    for f, ch, s, e in keys:
        if f < f0 - 2: continue
        smp = bv[s << 8:(e + 1) << 8]
        w = next((w for w, x in want.items() if smp[:len(x)] == x and len(smp) >= len(x) - 256), None)
        got.append([f - f0, ch, w])
    json.dump({'wait': wait, 'pose': k, 'keyons': got}, open(out, 'w'))

def main(out):
    os.makedirs(out, exist_ok=True); res = {}; fails = 0
    for wait in range(150, 158):
        p = os.path.join(out, f'run_{wait}.json')
        subprocess.run([sys.executable, os.path.abspath(__file__), '--one', str(wait), p], check=True)
        r = json.load(open(p))
        if r['pose'] in res: continue
        k = r['pose']; label, exp = SS2[k]
        mine = [(w, f) for f, ch, w in r['keyons'] if w]
        rows = []
        for w, f in exp:                                   # each SS2 sound: the brawler's key-on of the same sample,
            m = next((g for ww, g in mine if ww == w and abs(g - (f + 1)) <= 2), None)   # SS2's Z80 frame + 1 (+-2)
            if m is not None: mine.remove((w, m))
            rows.append({'word': w, 'ss2_frame': f, 'brawler_keyon': m, 'ok': m is not None})
        ok = all(x['ok'] for x in rows)
        fails += not ok
        res[k] = {'ss2': label, 'rows': rows, 'other_keyons': r['keyons'], 'ok': ok}
        print(('OK  ' if ok else 'FAIL'), f'pose {k} = SS2 {label}:', ', '.join(f"{x['word']} SS2 {x['ss2_frame']} -> brawler {x['brawler_keyon']}" for x in rows))
        if len(res) == len(SS2): break
    fails += len(SS2) - len(res)
    json.dump(res, open(os.path.join(out, 'proof.json'), 'w'), indent=1)
    print('ALL OK' if not fails else f'{fails} FAIL')
    return not fails

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['--one']: one(int(a[1]), a[2]); sys.exit()
    sys.exit(0 if main(a[0] if a else '/data/tmp/winsnd/proof') else 1)
