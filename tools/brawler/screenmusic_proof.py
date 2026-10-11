#!/usr/bin/env python3
"""The music of the end screens (voice notes of 2026-10-06, TODO #154: 20261006-173221-5d29 stage clear, 20261006-173249-5d29
ending, 20261006-160529-b3f3 continue, 20261006-160539-b3f3 game over), replayed on the current build in our emulator
(harness.py, BRAWLER_CORE, the player's arcade system mvs-mvs): every music start the 68000 sends (REG_SOUND $320000:
$07 then the song), with the screen it lands on (mode / phase / cont_ov), the YM2610 key-ons per second through the Z80
port tap, and a 12 s WAV from each music start.
  clear     stage 1, Terry kills Mr. Big: the KO sequence, STAGE CLEAR, the win screen, the next stage's song
  ending    stage 5, Terry kills its boss: STAGE CLEAR, (BOSS UNLOCKED), CONGRATULATIONS (the ending)
  continue  stage 1 wave 1, 1 life point, no lives: an enemy's hit, CONTINUE? 9 -> 0, GAME OVER, back to the BIOS, a coin
            (the title's song after the fade)

    python3 screenmusic_proof.py [ROM] [OUT]     (default examples/brawler/brawler.neo, /data/tmp/screenmusic) -> OUT/proof.json"""
import ctypes as C, json, os, re, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
RATE = 55555
REC = {'clear': ({'mode': 'stage', 'fighter': 'terry', 'stage': 0, 'wave': 5, 'wait': 150, 'alone': True, 'foe_hp': 1,
                  'gap': 50}, '60:-,3:a', 2400),
       'ending': ({'mode': 'stage', 'fighter': 'terry', 'stage': 4, 'wave': 5, 'wait': 150, 'alone': True, 'foe_hp': 1,
                   'gap': 50}, '60:-,3:a', 3000),
       'continue': ({'mode': 'stage', 'fighter': 'terry', 'stage': 0, 'wave': 0, 'hp': 1, 'lives': 0}, '', 3600)}

def child(rom, out, name):
    import harness as H, scenario
    b = H.Brawler(rom=rom, options=scenario.SYSTEMS['mvs-mvs']); b.game = H.GAME; Y = b.syms
    hdr = open(os.path.join(H.GAME, 'build', 'snd', 'songs.h')).read()
    mus = {int(v, 16): n for n, v in re.findall(r'#define MUS_(\w+) +0x([0-9A-F]+)', hdr)}
    ev = []; audio = bytearray(); a = [0, 0]; afr = {}
    def wt(addr, v, s):
        if addr in (0x320000, 0x320001): ev.append((b.frame, 'M68K', v & 0xFF if s == 1 else v >> 8))
    def zt(w, port, v):
        p = port & 0xFF
        if w and p in (4, 6): a[p == 6] = v
        if w and p in (5, 7):
            r = a[p == 7]
            if p == 5 and r == 0x28 and v & 0xF0: ev.append((b.frame, 'FM', v))
            if p == 5 and r == 0x10 and v & 0x80: ev.append((b.frame, 'B', v))
            if p == 7 and r == 0 and v and not v & 0x80: ev.append((b.frame, 'A', v))
        return v
    def batch(d, n): audio.extend(C.string_at(d, n * 4)); return n
    WT = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_int)(wt); ZT = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)(zt)
    BT = H.BATCH_CB(batch); b.core.retro_set_audio_sample_batch(BT)
    s, keys, frames = REC[name]
    scenario.setup(b, {'setup': s})
    b.core.retro_neoscan_m68k_write_tap(WT); b.core.retro_neoscan_z80_tap(ZT)
    t0 = b.frame; audio.clear(); screens = []
    def scr():
        m = b.r(Y['mode'], 1)
        if m == 1:
            if b.r(Y['cont_ov'], 1): return 'CONTINUE?' if b.r(Y['cont_ov'], 1) == 1 else 'continue->gameover'
            return 'play phase %d' % b.r(Y['phase'], 1)
        return {0: 'select', 2: 'title/attract', 3: 'BOSS UNLOCKED', 4: 'ENDING', 5: 'GAME OVER'}.get(m, 'mode %d' % m)
    def step(n, k=''):
        for _ in range(n):
            b.pad = [set(k), set()]; b.core.retro_run(); b.frame += 1; afr[b.frame - t0] = len(audio)
            c = scr()
            if not screens or screens[-1][1] != c: screens.append((b.frame - t0, c))
        b.pad = [set(), set()]
    for part in [p for p in keys.split(',') if p]:
        n, k = part.split(':'); step(int(n), k.replace('-', ''))
    coin = None
    while b.frame - t0 < frames:
        step(1)                                            # continue: after GAME OVER, a coin on the BIOS's attract (the
        if name == 'continue' and coin is None and any(n == 'GAME OVER' for _, n in screens) and screens[-1][1] == 'title/attract':
            coin = b.frame - t0; step(200); step(4, 'o')   # title song must come back after the fade)
    snd = [(f - t0, k, v) for f, k, v in ev]
    m68k = [(f, v) for f, k, v in snd if k == 'M68K']
    starts = [(m68k[i][0], mus.get(m68k[i + 1][1], '%02X' % m68k[i + 1][1])) for i in range(len(m68k) - 1)
              if m68k[i][1] == 0x07 and (m68k[i + 1][1] in mus)]
    def screen_at(f):
        c = screens[0][1]
        for g, n in screens:
            if g <= f + 1: c = n
        return c
    res = {'screens': screens, 'music_starts': [(f, n, screen_at(f)) for f, n in starts],
           'stops': [f for f, v in m68k if v in (0x04, 0x20)],
           'fades': [(m68k[i][0], '%02X' % m68k[i + 1][1], screen_at(m68k[i][0])) for i in range(len(m68k) - 1) if m68k[i][1] == 0x0A]}
    import numpy as np                                     # loudness per second over the whole run (RMS of the mix)
    spf = len(audio) / 4 / max(1, b.frame - t0)
    x = np.frombuffer(bytes(audio), np.int16).reshape(-1, 2).mean(1)
    res['rms_per_s'] = [int(np.sqrt((x[int(i * 60 * spf):int((i + 1) * 60 * spf)] ** 2).mean())) for i in range(int(len(x) / spf / 60))]
    for f, n in starts:                                    # key-ons per second and a WAV from each start
        nxt = min([g for g, _ in starts if g > f] + [b.frame - t0])
        ks = [0] * ((min(nxt, f + 12 * 60) - f + 59) // 60)
        for g, k, _ in snd:
            if k in ('FM', 'A', 'B') and f <= g < f + 60 * len(ks): ks[(g - f) // 60] += 1
        res.setdefault('keyons_per_s', {})[f'{f}:{n}'] = ks
        o = afr.get(f, 0)
        w = wave.open(os.path.join(out, f'{name}_{f}_{n}.wav'), 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(bytes(audio[o:o + RATE * 12 * 4])); w.close()
    json.dump(res, open(os.path.join(out, f'_{name}.json'), 'w'), indent=1)

def main():
    import subprocess
    rom = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'examples', 'brawler', 'brawler.neo')
    out = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/screenmusic'
    if len(sys.argv) > 3: return child(rom, out, sys.argv[3])
    os.makedirs(out, exist_ok=True); res = {}
    for name in REC:                                       # one emulator at a time
        subprocess.run([sys.executable, __file__, rom, out, name], check=True)
        res[name] = json.load(open(os.path.join(out, f'_{name}.json')))
        print(name, 'screens', res[name]['screens'])
        print('   music starts (frame, song, screen):', res[name]['music_starts'], 'fades:', res[name]['fades'])
        print('   RMS per second:', res[name]['rms_per_s'])
        for k, v in res[name].get('keyons_per_s', {}).items(): print('   key-ons/s from', k, v)
    json.dump(res, open(os.path.join(out, 'proof.json'), 'w'), indent=1)

if __name__ == '__main__': main()
