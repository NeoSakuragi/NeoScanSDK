#!/usr/bin/env python3
"""The music flow and the GO buzz (voice notes 20261011-114853-5d29 and 20261011-114459-5d29), in our emulator (harness.py,
BRAWLER_CORE, the player's arcade system mvs-mvs): every byte the 68000 writes to REG_SOUND ($320000), every command the
Z80 reads, the YM2610's key-ons (FM, ADPCM-A, ADPCM-B) and SSG writes through the Z80 port tap, and a 20 s WAV per step:
  attract  power on, no credit: the logo (17 s) and the demo fight: no music command at all (the BIOS's own resets only)
  coin     a coin on the logo: the title, KOF94's coin song (MUS_TITLE) and the coin sound
  start    START on the title: the select screen, KOF95's select song (MUS_SELECT)
  go       stage 1, wave 1's enemies taken off: GO -> blinks; each time it shows the Z80 reads SSG_GO and the SSG plays
           it, while the stage song's key-ons go on (no music command re-sent)

    python3 musicflow_proof.py [ROM] [OUT]     (default examples/brawler/brawler.neo, /data/tmp/musicflow) -> OUT/proof.json"""
import ctypes as C, json, os, re, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario
RATE = 55555

def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else os.path.join(H.GAME, 'brawler.neo')
    out = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/musicflow'
    os.makedirs(out, exist_ok=True)
    hdr = open(os.path.join(H.GAME, 'build', 'snd', 'songs.h')).read()
    mus = {int(v, 16): n for n, v in re.findall(r'#define MUS_(\w+) +0x([0-9A-F]+)', hdr)}
    ssg = {n: int(v, 16) for n, v in re.findall(r'#define SSG_(\w+) +0x([0-9A-F]+)', hdr)}
    b = H.Brawler(rom=rom, options=scenario.SYSTEMS['mvs-mvs']); b.game = H.GAME; Y = b.syms
    ev = []; audio = bytearray(); a = [0, 0]; mark = {}
    def wt(addr, v, s):
        if addr in (0x320000, 0x320001): ev.append((b.frame, 'M68K', v & 0xFF if s == 1 else v >> 8))
    def zt(w, port, v):
        p = port & 0xFF
        if not w and p == 0: ev.append((b.frame, 'Z80CMD', v))
        if w and p in (4, 6): a[p == 6] = v
        if w and p in (5, 7):
            r = a[p == 7]
            if p == 5 and r <= 0x0D: ev.append((b.frame, 'SSG', r))
            if p == 5 and r == 0x28 and v & 0xF0: ev.append((b.frame, 'FM', v))
            if p == 5 and r == 0x10 and v & 0x80: ev.append((b.frame, 'B', v))
            if p == 7 and r == 0 and v and not v & 0x80: ev.append((b.frame, 'A', v))
        return v
    afr = {}
    def batch(d, n): audio.extend(C.string_at(d, n * 4)); return n
    WT = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_int)(wt); ZT = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)(zt)
    BT = H.BATCH_CB(batch); b.core.retro_set_audio_sample_batch(BT)
    b.core.retro_neoscan_m68k_write_tap(WT); b.core.retro_neoscan_z80_tap(ZT)
    def run(n, keys=''):
        b.pad = [set(keys), set()]                         # (not b.run: its hit log reads fighters before the boot)
        for _ in range(n): b.core.retro_run(); b.frame += 1; afr[b.frame] = len(audio)
        b.pad = [set(), set()]
    def until(cond, what, limit=4000):
        for _ in range(limit):
            if cond(): return b.frame
            run(1)
        raise RuntimeError('never reached ' + what)
    def wav(name, f0, sec=20):
        o = afr.get(f0, 0)
        w = wave.open(os.path.join(out, name + '.wav'), 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(bytes(audio[o:o + RATE * sec * 4])); w.close()
    def starts(f0, f1):
        """music starts (snd_music: $07 then the song) the 68000 wrote in [f0, f1)"""
        m = [(f, v) for f, k, v in ev if k == 'M68K' and f0 <= f < f1]
        return [(f, mus[m[i + 1][1]]) for i, (f, v) in enumerate(m[:-1]) if v == 0x07 and m[i + 1][1] in mus]
    def per_s(f0, f1, kinds=('FM', 'A', 'B')):
        r = [0] * ((f1 - f0 + 59) // 60)
        for f, k, _ in ev:
            if k in kinds and f0 <= f < f1: r[(f - f0) // 60] += 1
        return r
    res = {}
    # power on: the logo, the demo
    b.core.retro_reset(); b.frame = 0; run(1)
    mode = lambda: b.r(Y['mode'], 1); attract = lambda: b.r(Y['attract'], 1)
    f_logo = until(lambda: mode() == 2 and attract() == 2, 'the attract logo')
    f_demo = until(lambda: mode() == 1 and attract() == 1, 'the demo fight', 2000)
    run(600)
    f_end = b.frame
    wav('attract', f_logo)
    m68k = [f'{f}:{v:02X}' for f, k, v in ev if k == 'M68K' and f < f_end]
    res['attract'] = {'logo_at': f_logo, 'demo_at': f_demo, 'until': f_end, 'music_starts': starts(0, f_end),
                      'm68k_sound_bytes': m68k[:40], 'music_keyons_per_s_logo': per_s(f_logo, f_demo),
                      'ok': not starts(0, f_end) and not any(per_s(f_logo, f_demo, ('FM', 'B')))}
    # a coin: the title
    f_coin = b.frame; run(4, 'o'); f_title = until(lambda: mode() == 2 and attract() == 0, 'the title', 600)
    run(20 * 60 + 30)
    wav('coin_title', f_coin)
    st = starts(f_coin, b.frame); cmds = [f'{v:02X}@{f - f_coin}' for f, k, v in ev if k == 'Z80CMD' and f >= f_coin][:12]
    res['coin'] = {'title_at': f_title - f_coin, 'music_starts': [(f - f_coin, n) for f, n in st], 'z80_commands': cmds,
                   'coin_sound': any(k == 'Z80CMD' and v == ssg['COIN'] for f, k, v in ev if f >= f_coin),
                   'keyons_per_s': per_s(f_coin, b.frame), 'ok': [n for _, n in st] == ['TITLE']}
    # START: the select
    f_start = b.frame
    for _ in range(6):
        if mode() == 0: break
        run(4, 's'); run(60)
    f_sel = until(lambda: mode() == 0, 'the select screen', 600)
    run(20 * 60 + 30)
    wav('start_select', f_start)
    st = starts(f_start, b.frame)
    res['start'] = {'select_at': f_sel - f_start, 'music_starts': [(f - f_start, n) for f, n in st],
                    'keyons_per_s': per_s(f_start, b.frame), 'ok': [n for _, n in st] == ['SELECT']}
    # stage cleared, GO blinking (P1 stands: the camera never reaches the next lock, the GO keeps blinking)
    ev.clear(); audio.clear(); afr.clear()
    scenario.setup(b, {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': 0, 'wave': 0}})
    run(120)
    f_kill = b.frame
    def go(): return b.r(Y['phase'], 1) == 1
    for _ in range(600):
        if go(): break
        for i in range(2, 8): b.fset(i, 'state', b.states.index('OFF'))
        b.w(Y['tq_n'], 1, 0); run(1)
    f_go = until(go, 'GO')
    run(20 * 60 + 30)
    wav('go', f_go)
    reads = [f - f_go for f, k, v in ev if k == 'Z80CMD' and v == ssg['GO'] and f >= f_go]
    gaps = sorted({reads[i + 1] - reads[i] for i in range(len(reads) - 1)})
    ssg_after = [sum(1 for f, k, _ in ev if k == 'SSG' and r + f_go <= f < r + f_go + 12) for r in reads]
    st = starts(f_kill - 200, b.frame)
    kps = per_s(f_go, f_go + 20 * 60)
    res['go'] = {'go_at': f_go - f_kill, 'go_cue_reads': reads, 'gaps_frames': gaps, 'ssg_writes_in_12_frames_after': ssg_after,
                 'music_starts_around': [(f - f_go, n) for f, n in st], 'music_keyons_per_s': kps,
                 'ok': len(reads) >= 30 and gaps == [32] and min(ssg_after) > 10 and not [n for f, n in st if f >= f_go]
                       and min(kps) > 0}
    res['all_ok'] = all(r['ok'] for r in res.values())
    json.dump(res, open(os.path.join(out, 'proof.json'), 'w'), indent=1)
    for k, r in res.items():
        if k != 'all_ok': print(k, 'OK' if r['ok'] else 'FAIL', {x: y for x, y in r.items() if x not in ('m68k_sound_bytes', 'ok')})
    print('all ok', res['all_ok'])
    return res['all_ok']

if __name__ == '__main__': sys.exit(0 if main() else 1)
