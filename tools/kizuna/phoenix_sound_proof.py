#!/usr/bin/env python3
"""Kim's Phoenix (6246A, C) in the brawler with its sound, in our emulator's core with the Z80 port tap (the build
voice_proof.py uses): the Chain Lab training (Kim against a dummy at point blank, the move connects), every voice
command the Z80 reads ($1C + code) with the ADPCM-A key-on it starts, the script row Kim was on, and the check: the
sample keyed on = Kizuna's own sample of that voice (voices.json, from Kizuna's driver: kim_voices.json) byte for byte;
Kizuna's own sounds for the move (export_kz.special_sounds: script row, word); the game's audio as a WAV.

    python3 phoenix_sound_proof.py [OUTDIR]        (default /data/tmp/phoenix/out: phoenix_brawler.wav, sound.json)"""
import ctypes as C, json, os, re, struct, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import harness, voices as V, export_kz as E
harness.CORE = '/data/neogeo_dict/sound/snd98/ff3/geolith_tap.so'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/phoenix/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))

def main():
    os.makedirs(OUT, exist_ok=True)
    rep = json.load(open(os.path.join(GAME, 'build', 'snd', 'snd_report.json')))['voices']
    codes = {int(c): int(i) for i, c in rep['fighters']['kim']['codes'].items()}   # driver code -> Kim's voice id
    bank = json.load(open(V.JSON))['fighters']['kim']['voices']
    b = harness.Brawler(game=GAME)
    log, a, pcm = [], [0, 0], []
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 4: a[0] = v
            elif p == 6: a[1] = v
            elif p == 7: log.append((b.frame, 'b', a[1], v))
        elif p == 0 and v: log.append((b.frame, 'c', v, 0))
        return v
    cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    def batch(d, n): pcm.append(C.string_at(d, 4 * n)); return n
    b._cbs[3] = harness.BATCH_CB(batch); b.core.retro_set_audio_sample_batch(b._cbs[3])
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    k = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_KIM')
    b.pick(k)
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, k); b.w(L + 6, 1, 0); b.w(L + 4, 1, 1)
    b.run(40); b.fset(0, 'meter', 120)
    dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
    b.place(dm, x=130); b.place(0, x=70, z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
    pcm.clear(); f0 = b.frame; h0 = len(b.hits); rows = {}; started = False; end = None
    for f in range(480):
        st = b.states[b.fget(0, 'state')]
        if st == 'SPECIAL': started = True; rows[b.frame] = (b.fget(0, 'spart'), b.fget(0, 'srow') - 1)
        elif started and end is None: end = f
        if end is not None and f > end + 120: break
        b.run(1, p1='c' if f < 3 else '')
    hits = [h for h in b.hits[h0:] if h[1] == dm]
    raw = b''.join(pcm)
    with wave.open(os.path.join(OUT, 'phoenix_brawler.wav'), 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(55556); w.writeframes(raw)   # Geolith's audio rate
    vrom = open(os.path.join(GAME, 'build', 'snd', 'v1.bin'), 'rb').read()
    m1 = open(os.path.join(GAME, 'build', 'snd', 'm1.bin'), 'rb').read()
    kzv = V.v_rom('kizuna')
    played, want, pending, reg = [], None, None, {}
    for f, kind, x, y in log:
        if f < f0: continue
        if kind == 'c':
            if want is not None:
                if want == 0x1C: pending = (x, f)
                want = None
            elif 0x14 <= x <= 0x1E: want = x
            continue
        reg[x] = y
        if x == 0 and y and not y & 0x80 and pending:
            ch = (y & -y).bit_length() - 1
            st = reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0); en = reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)
            r = 0x484C + 6 * pending[0]
            if (st, en) != (m1[r + 1] | m1[r + 2] << 8, m1[r + 3] | m1[r + 4] << 8): continue
            vid = codes.get(pending[0]); vo = bank[vid - 1] if vid else None
            row = rows.get(pending[1]) or rows.get(pending[1] - 1)
            e = {'frame': pending[1] - f0, 'code': f'{pending[0]:02X}', 'voice': vid, 'kizuna_word': vo and vo['cmd'],
                 'part_row': row, 'ms': vo and vo['ms']}
            if vo:
                s0, e0 = vo['segments'][0]
                e['bytes_equal'] = vrom[st << 8:(en + 1) << 8] == kzv[s0 << 8:(e0 + 1) << 8]
            played.append(e); pending = None
    fc = json.load(open(E.FOLLOWUPS)); cap = json.load(open(E.CAPTURE))
    kz_sounds = [(r_, f'{w_:04X}') for r_, w_ in E.special_sounds('6246A', cap, fc)]
    res = {'hits': len(hits), 'damage': sum(h[2] for h in hits), 'voices_played': played,
           'kizuna_sounds_by_row': kz_sounds, 'wav': os.path.join(OUT, 'phoenix_brawler.wav'),
           'cry_1A68': any(p_['kizuna_word'] == '1A68' and p_.get('bytes_equal') for p_ in played)}
    json.dump(res, open(os.path.join(OUT, 'sound.json'), 'w'), indent=1)
    print('hits', res['hits'], 'damage', res['damage'])
    for p_ in played: print('  voice', p_)
    print('Kizuna sounds (row, word):', kz_sounds)
    print('cry $1A68 played, bytes equal to Kizuna\'s:', res['cry_1A68'])

if __name__ == '__main__':
    main()
