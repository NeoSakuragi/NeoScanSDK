#!/usr/bin/env python3
"""TODO #197 proof: a fire hit in the brawler sends KOF96's fire hit. KOF96 (measured in our emulator, WLOG on its
sound mapper's word, /data/tmp/fire197/cap96): Kyo's / Iori's 623C hits send $1A $13 + $1A $1F, Iori's 236A and
Krauser's Blitz Ball hits $1A $1F alone (hit kinds 11 / 21, tools/kof96/hitsfx.py). The brawler's $2E (songs.json sfx
"from" kof96 $1A1F) must key on KOF96's $1F sample byte for byte. Each move here: played in the Chain Lab (the tap
core, the dummy in reach), the effect codes the game queued from the hit on, and every ADPCM-A key-on the Z80 makes
for them (start / end pages) with the sample bytes vs KOF96's V ROM; WAVs of what the brawler keyed on.

    python3 fire197_proof.py OUTDIR      -> OUTDIR/fire197.json, OUTDIR/brawler_<fighter>_<input>.wav"""
import ctypes as C, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness, voices as V
harness.CORE = '/data/neogeo_dict/sound/snd98/ff3/geolith_tap.so'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
KOF96_FIRE = [1272, 1313]                                     # KOF96 $1A $1F: record $4536, its own driver's key-on
MOVES = [('kyo', '623C', 34), ('iori', '623C', 34), ('krauser', '214A', 120),
         ('billy', '23624C', 60)]

def main(out, game=harness.GAME):
    os.makedirs(out, exist_ok=True)
    G = json.load(open(os.path.join(game, 'game.json'))); names = [r['name'] for r in G['roster']]
    lab = {f['name']: f for f in json.load(open(os.path.join(game, 'build', 'chainlab.json')))['fighters']}
    rep = json.load(open(os.path.join(game, 'build', 'snd', 'snd_report.json')))
    fire = rep['sfx_from']['2E']
    vb = open(os.path.join(game, 'build', 'snd', 'v1.bin'), 'rb').read(); v96 = V.v_rom('kof96')
    want = V.sample_bytes(v96, [KOF96_FIRE])
    b = harness.Brawler(game=game); S = b.syms
    log, reg = [], {}
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 6: tap.a = v
            elif p == 7:
                if tap.a == 0 and v and not v & 0x80:      # ADPCM-A key-on: each channel keyed with its registers
                    for ch in range(6):
                        if v >> ch & 1:
                            log.append((b.frame, 'key', ch, reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0),
                                        reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)))
                reg[tap.a] = v
        elif p == 0 and v: log.append((b.frame, 'cmd', v))
        return v
    tap.a = 0
    cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    for _ in range(400): b.core.retro_run()
    from chainlab.labdrive import PACK_OFF
    L = S['lab']; MAP = L + PACK_OFF
    for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
    st = b.states; res = []
    for n, inp, dist in MOVES:
        fi = names.index(n); k = [p['input'] for p in lab[n]['pool']].index(inp)
        rf = next(r for r in G['roster'] if r['name'] == n); fury = rf.get('fury')
        keys = 'Dd' if inp == f'MAX {fury}' else 'd' if inp == fury else 'c'   # the MAX version: down+D (TODO #206)
        b.w(L + 5, 1, fi); b.w(L + 6, 1, names.index('terry')); b.w(L + 4, 1, 1); b.run(30)
        b.w(S['spec_tab'] + 4 * fi, 4, MAP)
        for j in range(6): b.w(MAP + j, 1, k if j == 0 else 0xFF)
        b.fset(0, 'meter', 300); b.fset(0, 'facing', 1)
        b.place(2, x=b.fget(0, 'x') + dist, z=b.fget(0, 'z')); b.run(2)
        log.clear(); sent = []; oqt = b.r(S['qt'], 1); hit = None; burn = 0
        for f in range(260):
            b.run(1, p1=keys if f < 3 else '')
            qt = b.r(S['qt'], 1)
            while oqt != qt: sent.append((b.frame, b.r(S['q'] + oqt, 1))); oqt = (oqt + 1) & 31
            if hit is None and st[b.fget(2, 'state')] in ('HITSTUN', 'KNOCKDOWN'): hit = b.frame
            burn = max(burn, b.fget(2, 'burn'))
        # the effect codes ($1A + code) queued on the first hit's frame (the hit sounds), and their key-ons
        hf = [fr for fr, v in sent]
        codes = []
        for i, (fr, v) in enumerate(sent):
            if v == 0x1A and i + 1 < len(sent) and hit is not None and abs(fr - hit) <= 1: codes.append(sent[i + 1][1])
        keys_on = [(fr, s_, e_) for fr, kind, *x in log if kind == 'key' for (ch, s_, e_) in [x] if hit is not None and hit - 1 <= fr <= hit + 4]
        fire_keys = [(fr, s_, e_) for fr, s_, e_ in keys_on if [s_, e_] == fire['pages']]
        same = bool(fire_keys) and vb[fire['pages'][0] << 8:(fire['pages'][1] + 1) << 8] == want
        wav = None
        if fire_keys:
            wav = os.path.join(out, f'brawler_{n}_{inp}.wav'); V.write_wav(wav, vb, [fire['pages']])
        row = {'fighter': n, 'input': inp, 'hit_frame': hit, 'burn': burn, 'codes_at_hit': [f'1A{c:02X}' for c in codes],
               'adpcm_a_keyons_at_hit': [[fr, s_, e_] for fr, s_, e_ in keys_on], 'fire_keyed': bool(fire_keys),
               'sample_bytes_equal_kof96_1A1F': same, 'wav': wav,
               'ok': hit is not None and burn > 0 and 0x2E in codes and same}
        res.append(row)
        print(n, inp, 'OK' if row['ok'] else 'FAIL', 'hit', hit, 'burn', burn, 'codes', row['codes_at_hit'],
              'keyons', row['adpcm_a_keyons_at_hit'], 'kof96 bytes', same, flush=True)
    V.write_wav(os.path.join(out, 'kof96_1A1F.wav'), v96, [KOF96_FIRE])
    json.dump({'kof96_1A1F_pages': KOF96_FIRE, 'brawler_2E': fire, 'moves': res}, open(os.path.join(out, 'fire197.json'), 'w'), indent=1)
    return all(r['ok'] for r in res)

if __name__ == '__main__':
    if len(sys.argv) > 2:                                     # fighter:input:dist ... (TODO #206: Kyo's fury / MAX)
        MOVES[:] = [(a, b, int(c)) for a, b, c in (x.split(':') for x in sys.argv[2:])]
    sys.exit(0 if main(sys.argv[1]) else 1)
