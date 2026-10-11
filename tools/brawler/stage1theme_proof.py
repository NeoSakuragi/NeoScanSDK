#!/usr/bin/env python3
"""Stage 1 plays the selected fighter's theme (voice note 20261011-160158-5d29: "for the first stage, the music of the
character that is selected, if it's available; Robert: KOF96's Kamikirimushi"), in our emulator (harness.py,
BRAWLER_CORE): stage 1 started the scenario way (scenario.setup, mode stage: the lab mailbox -> stage_begin) with each
fighter; every byte the 68000 writes to REG_SOUND ($320000) logged, the music command after the $07 unlock compared
with the fighter's roster music (build/snd/songs.h MUS_*) or, without one, stage 1's own song; with Robert the audio
from the command on saved (30 s) for the comparison with KOF96's own (tools/port/theme219_proof.py --only THEME_ROBERT).

    python3 stage1theme_proof.py [OUT] [--fighters a,b,...]   (default OUT /data/tmp/stage1_theme; robert, rosa, terry)
        -> OUT/stage1_<fighter>.wav (robert), OUT/stage1_proof.json"""
import ctypes as C, json, os, re, subprocess, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
a = sys.argv[1:]
FIGHTERS = a[a.index('--fighters') + 1].split(',') if '--fighters' in a else ['robert', 'rosa', 'terry']
if '--fighters' in a: del a[a.index('--fighters'):a.index('--fighters') + 2]
OUT = a[0] if a and not a[0].startswith('--') else '/data/tmp/stage1_theme'
RATE, SECONDS = 55555, 30

def child(fighter):
    import harness as H, scenario
    b = H.Brawler(); b.game = H.GAME
    ev, audio = [], bytearray()
    def wt(addr, v, s):
        if addr in (0x320000, 0x320001): ev.append((b.frame, v & 0xFF if s == 1 else v >> 8, len(audio)))
    def batch(d, n): audio.extend(C.string_at(d, n * 4)); return n
    WT = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_int)(wt); BT = H.BATCH_CB(batch)
    b.core.retro_set_audio_sample_batch(BT); b.core.retro_neoscan_m68k_write_tap(WT)
    scenario.setup(b, {'setup': {'mode': 'stage', 'fighter': fighter, 'stage': 0, 'wave': 0}})
    t0 = b.frame
    b.run(SECONDS * 60 + 60)
    b.core.retro_neoscan_m68k_write_tap(C.cast(None, type(WT)))
    pairs = [(ev[i][0], ev[i + 1][1], ev[i + 1][2]) for i in range(len(ev) - 1) if ev[i][1] == 0x07 and 0x20 <= ev[i + 1][1] < 0x60]
    before = [p for p in pairs if p[0] <= t0]                             # stage_begin ran inside setup: its song = the
    first = before[-1] if before else (pairs[0] if pairs else None)       # last one started by then
    snd_song = b.r(b.syms['snd_song'], 1)
    if fighter == 'robert' and first:
        o = first[2]
        w = wave.open(os.path.join(OUT, f'stage1_{fighter}.wav'), 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(bytes(audio[o:o + RATE * SECONDS * 4])); w.close()
    json.dump({'music_cmds': [f'${c:02X}' for _, c, _ in pairs], 'stage_song': first[1] if first else None,
               'snd_song': snd_song}, open(os.path.join(OUT, f'_s1_{fighter}.json'), 'w'))

def main():
    os.makedirs(OUT, exist_ok=True)
    import harness as H
    g = json.load(open(os.path.join(H.GAME, 'game.json')))
    mus = {m[0]: int(m[1], 16) for m in re.findall(r'#define MUS_(\w+)\s+0x([0-9A-Fa-f]+)', open(os.path.join(H.GAME, 'build', 'snd', 'songs.h')).read())}
    ros = {r['name']: r for r in g['roster']}
    res = {}
    for f in FIGHTERS:
        subprocess.run([sys.executable, __file__, '--child', f, OUT], check=True)
        d = json.load(open(os.path.join(OUT, f'_s1_{f}.json')))
        want_name = ros[f].get('music') or g['stages'][0]['music']
        ok = d['stage_song'] == mus[want_name] == d['snd_song']
        res[f] = dict(d, stage_song=f"${d['stage_song']:02X}", expected=f'{want_name} ${mus[want_name]:02X}',
                      theme=ros[f].get('music'), ok=ok)
        print(f"{f:10s} theme {str(ros[f].get('music')):16s} stage 1 song ${d['stage_song']:02X}  expected {want_name} ${mus[want_name]:02X}: {'OK' if ok else 'FAIL'}")
    res['all_ok'] = all(r['ok'] for r in res.values() if isinstance(r, dict))
    json.dump(res, open(os.path.join(OUT, 'stage1_proof.json'), 'w'), indent=1)
    print('ALL OK' if res['all_ok'] else 'FAILED')

if __name__ == '__main__':
    if sys.argv[1:2] == ['--child']: OUT = sys.argv[3]; child(sys.argv[2])
    else: main()
