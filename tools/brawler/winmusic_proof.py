#!/usr/bin/env python3
"""The stage clear's win music (voice note 20261011-112252-5d29: "the win music is playing twice, almost as a loop, and in
between there is some garbled sound"), in our emulator (harness.py, BRAWLER_CORE), two builds (before / after):
every byte the 68000 writes to REG_SOUND ($320000), every command the Z80 reads, the YM2610 key-ons (FM, ADPCM-A,
ADPCM-B; an FM key-on of a channel the YM2610 has not = garbage) through the Z80 port tap, and a WAV of the 20 s from
the win music's command. Scenarios (scenario.setup recipes):
  boss   stage 1, Terry kills Mr. Big: the KO sequence starts the win music (boss_ko_tick), the win pose, the drama win
         screen (long: past the song's end)
  plain  stage 1's boss taken off (state OFF): PH_END's own path starts the win music (no KO sequence), the win pose
Cause: KOF95's $30 ends in $40 (stop); port98 wrote each channel's end as $06 with no delta, and KOF98's driver reads
on after an event with no delta ($1C5E pushes $1C4F), so at the song's end every channel ran into the next channel's
bytes (status 5 again): garbage key-ons, then the song's own start again (FM1 reads FM2's stream, ...).

    python3 winmusic_proof.py BEFORE.neo AFTER.neo [OUT]       (default OUT /data/tmp/winmusic) -> OUT/proof.json"""
import ctypes as C, json, os, struct, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
OUT = sys.argv[3] if len(sys.argv) > 3 else '/data/tmp/winmusic'
RATE = 55555
REC = {'boss': {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': 0, 'wave': 5, 'wait': 150, 'alone': True,
                          'foe_hp': 1, 'gap': 50}, 'do_keys': '1:a,30:-,1:a'},
       'plain': {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': 0, 'wave': 5, 'wait': 150, 'alone': True}}}
FRAMES = 2600                                      # past the win music + 20 s

def child(tag, rom, name):
    import harness as H, scenario
    b = H.Brawler(rom=rom); b.game = H.GAME
    ev = []; audio = bytearray(); a = [0, 0]
    def wt(addr, v, s):
        if addr in (0x320000, 0x320001): ev.append((b.frame, 'M68K', v & 0xFF if s == 1 else v >> 8))
    def zt(w, port, v):
        p = port & 0xFF
        if not w and p == 0: ev.append((b.frame, 'Z80CMD', v))
        if w and p in (4, 6): a[p == 6] = v
        if w and p in (5, 7):
            r = a[p == 7]
            if p == 5 and r == 0x28 and v & 0xF0: ev.append((b.frame, 'FM' if (v & 7) in (1, 2, 5, 6) else 'FMBAD', v))
            if p == 5 and r == 0x10 and v & 0x80: ev.append((b.frame, 'B', v))
            if p == 7 and r == 0 and v and not v & 0x80: ev.append((b.frame, 'A', v))
        return v
    def batch(d, n): audio.extend(C.string_at(d, n * 4)); return n
    WT = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_int)(wt); ZT = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)(zt)
    BT = H.BATCH_CB(batch); b.core.retro_set_audio_sample_batch(BT)
    rec = REC[name]
    scenario.setup(b, rec)
    b.core.retro_neoscan_m68k_write_tap(WT); b.core.retro_neoscan_z80_tap(ZT)
    t0 = b.frame; audio.clear(); marks = {}
    for part in [p for p in rec.get('do_keys', '').split(',') if p]:
        n, k = part.split(':'); b.run(int(n), p1=k.replace('-', ''))
    if name == 'plain': b.fset(2, 'state', b.states.index('OFF'))   # the boss gone: PH_BOSS -> PH_END without the KO
    while b.frame - t0 < FRAMES:
        b.run(1)
        on = b.r(b.syms['dr_on'], 1) != 0                  # a drama's bars in (0 -> on: its start)
        if on and not marks.get('_on'): marks.setdefault('drama', []).append(b.frame - t0)
        marks['_on'] = on
    b.core.retro_neoscan_z80_tap(C.cast(None, type(ZT))); b.core.retro_neoscan_m68k_write_tap(C.cast(None, type(WT)))
    snd = [(f - t0, k, v) for f, k, v in ev]
    import re
    win = int(re.search(r'#define MUS_WIN +0x([0-9A-F]+)', open(os.path.join(H.GAME, 'build', 'snd', 'songs.h')).read()).group(1), 16)
    m68k = [(f, v) for f, k, v in snd if k == 'M68K']
    starts = [m68k[i][0] for i in range(len(m68k) - 1) if m68k[i][1] == 0x07 and m68k[i + 1][1] == win]
    nxt = [m68k[i][0] for i in range(len(m68k) - 1) if m68k[i][1] == 0x07 and m68k[i + 1][1] != win and starts and m68k[i][0] > starts[0]]
    marks['next_music'] = nxt[0] if nxt else None
    f0 = starts[0] if starts else 0
    spf = len(audio) / 4 / (b.frame - t0)               # samples a frame
    o = int(f0 * spf) * 4
    w = wave.open(os.path.join(OUT, f'{name}_{tag}.wav'), 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(bytes(audio[o:o + RATE * 20 * 4])); w.close()
    json.dump({'events': snd, 'win_starts': starts, 'marks': marks, 'win_cmd': win}, open(os.path.join(OUT, f'_{name}_{tag}.json'), 'w'))

def timeline(d):
    """per second from the win music's command: FM / ADPCM-A / ADPCM-B key-ons, garbage FM key-ons, Z80 commands"""
    f0 = d['win_starts'][0]; rows = {}
    for f, k, v in d['events']:
        s = (f - f0) // 60
        if s < 0 or s >= 20: continue
        r = rows.setdefault(s, {'FM': 0, 'A': 0, 'B': 0, 'FMBAD': 0, 'cmds': []})
        if k in r and k != 'cmds': r[k] += 1
        if k == 'Z80CMD': r['cmds'].append(f'{v:02X}')
    return rows

def rms(path):
    import numpy as np
    w = wave.open(path); x = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2).mean(1); h = RATE // 2
    return [int(np.sqrt((x[i:i + h] ** 2).mean())) for i in range(0, len(x) - h + 1, h)]

def main():
    before, after = sys.argv[1], sys.argv[2]
    if len(sys.argv) > 5: return child(sys.argv[4], {'before': before, 'after': after}[sys.argv[4]], sys.argv[5])
    import subprocess
    os.makedirs(OUT, exist_ok=True)
    res = {}; L = []; ok = True
    for name in REC:
        for tag in ('before', 'after'):
            subprocess.run([sys.executable, __file__, before, after, OUT, tag, name], check=True)
            d = json.load(open(os.path.join(OUT, f'_{name}_{tag}.json')))
            tl = timeline(d); e = rms(os.path.join(OUT, f'{name}_{tag}.wav'))
            m68k = ' '.join(f'{f}:{v:02X}' for f, k, v in d['events'] if k == 'M68K' and f >= d['win_starts'][0] - 120)
            bad = sum(r['FMBAD'] for r in tl.values())
            nm = d['marks']['next_music']; f0 = d['win_starts'][0]   # key-ons after the song's 5.4 s, before the next song
            late = sum(1 for f, k, v in d['events'] if k in ('FM', 'A', 'B', 'FMBAD') and f0 + 5.5 * 60 <= f < (nm or 1e9))
            drama = [f for f in d['marks'].get('drama', []) if f > f0]
            res[f'{name}_{tag}'] = {'win_music_sent': len(d['win_starts']), 'win_at': d['win_starts'], 'drama_at': drama, 'next_music_at': nm, 'keyons_after_song_end': late,
                                    'bad_fm_keyons': bad, 'rms_half_s': e, 'per_second': tl, 'm68k_from_win-120': m68k}
            L.append(f'{name} {tag}: win music sent {len(d["win_starts"])}x (frame {d["win_starts"]}), win drama at {drama}, next song at {nm}; key-ons from 5.5 s to the next song: {late}; '
                     f'key-ons per second FM/A/B[garbage]: ' + ' '.join(f'{s}:{r["FM"]}/{r["A"]}/{r["B"]}' + (f'[{r["FMBAD"]}]' if r['FMBAD'] else '') for s, r in sorted(tl.items())))
            L.append(f'   RMS / 0.5 s: ' + ' '.join(map(str, e)))
            if tag == 'after': ok &= len(d['win_starts']) == 1 and bad == 0 and late == 0
    res['all_ok'] = ok
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    open(os.path.join(OUT, 'proof.txt'), 'w').write('\n'.join(L) + f'\nall ok {ok}\n'); print('\n'.join(L)); print('all ok', ok)

if __name__ == '__main__': main()
