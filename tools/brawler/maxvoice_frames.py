#!/usr/bin/env python3
"""Terry's MAX (Triple Geyser, MAX 21416C = down + D at low life) frame by frame, for the voice-timing decisions page
(note 20261017-145343-e03d, chainlab/terry_max_voices.html). In our emulator (harness.py, the repo's Geolith core), the
current build, the Chain Lab against Ryo as rbsgeyser_proof.py sets it up: P1 life 10, bars full, D + down held on
frames 0-1. Frame k = the k-th retro_run after the setup, the same clock as rbsgeyser_proof.py's voice frames (the
picture is the one that run outputs; the voices = the Z80's $1C/$1B commands read during that run).
Cases: hit (the dummy at 60 px) and whiff (220 px). Each case: every frame until Terry is back to idle for 8 frames.

    python3 maxvoice_frames.py [OUTDIR [ROM]]      (OUTDIR: chainlab/decisions-media/terry-max-voices, the page's media)
OUTDIR/<case>_big.webp (frames 272x192, 10 per row), <case>_small.webp (90x64), frames.json, voices/<id>.wav"""
import ctypes as C, json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario
from PIL import Image

CASES = [('hit', 60), ('whiff', 220)]
CROP = (0, 24, 272, 216)                              # x0 y0 x1 y1 of the 320x224 picture: Terry + the geysers
COLS = 10
SMALL = 3                                              # the strip's thumbnails: 1/3
VOICES = [22, 23, 16, 17, 18]                          # RBS $C4, $C6; KOF98 16 + 17 (the 0.10.167 MAX), 18 (236236 start)
WAVS = '/data/neogeo_dict/voices/wav/terry'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
PAIRED = {0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E}
MAXF = 400

def main(out, rom=None):
    os.makedirs(os.path.join(out, 'voices'), exist_ok=True)
    opts = scenario.SYSTEMS['mvs-mvs']
    b = H.Brawler(rom=rom, options=opts) if rom else H.Brawler(options=opts)
    b.game = H.GAME
    npj = (b.syms['projectiles_end'] - b.syms['projectiles']) // b.fsize if 'projectiles_end' in b.syms else 8
    log = []
    def tap(write, port, v):
        if not write and port & 0xFF == 0 and v: log.append((b.frame, v))
        return v
    cb = TAP(tap)
    res = {'build': open(os.path.join(H.GAME, 'VERSION')).read().strip(), 'crop': CROP, 'cols': COLS, 'small': SMALL, 'cases': {}}
    for name, gap in CASES:
        scenario.setup(b, {'setup': {'mode': 'lab', 'fighter': 'terry', 'dummy': 'ryo', 'gap': gap, 'drive': 'full', 'fury': 'full', 'hp': 10}})
        f0 = b.frame; idle0 = b.fget(0, 'state'); del log[:]
        b.core.retro_neoscan_z80_tap(cb)
        frames, pics, back = [], [], 0
        for k in range(MAXF):
            b._want_video = True; b.run(1, 'Dd' if k < 2 else ''); b._want_video = False
            data, w, h, pitch = b._video
            pics.append(Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').crop(CROP))
            st = b.states[b.fget(0, 'state')]
            alive = sum(1 for i in range(npj) if b.states[b.pget(i, 'state')] != 'OFF')
            frames.append({'state': st, 'eruptions': alive})
            back = back + 1 if (k > 10 and b.fget(0, 'state') == idle0 and not alive) else 0
            if back >= 8: break
        b.core.retro_neoscan_z80_tap(C.cast(None, TAP))
        # the voice commands each frame (the driver's paired $1C/$1B + code, as rbsgeyser_proof.py)
        want, sent = None, []
        for f, v in log:
            if want is not None:
                if want in (0x1B, 0x1C): sent.append({'frame': f - f0, 'cmd': f'{want:02X}{v:02X}'})
                want = None
            elif v in PAIRED: want = v
        appear = [k for k in range(1, len(frames)) if frames[k]['eruptions'] > frames[k - 1]['eruptions']]
        res['cases'][name] = {'n': len(frames), 'frames': frames, 'voice_cmds': sent, 'eruption_starts': appear,
                              'big': f'{name}_big.webp', 'small': f'{name}_small.webp'}
        cw, ch = CROP[2] - CROP[0], CROP[3] - CROP[1]; rows = (len(pics) + COLS - 1) // COLS
        big = Image.new('RGB', (cw * COLS, ch * rows), 'white')
        sm = Image.new('RGB', (cw // SMALL * COLS, ch // SMALL * rows), 'white')
        for i, p in enumerate(pics):
            big.paste(p, (i % COLS * cw, i // COLS * ch))
            sm.paste(p.resize((cw // SMALL, ch // SMALL), Image.LANCZOS), (i % COLS * (cw // SMALL), i // COLS * (ch // SMALL)))
        big.save(os.path.join(out, f'{name}_big.webp'), quality=70, method=6)
        sm.save(os.path.join(out, f'{name}_small.webp'), quality=85, method=6)
        print(name, len(frames), 'frames, voices', [(s['frame'], s['cmd']) for s in sent], 'eruptions at', appear)
    vj = {v['id']: v for v in json.load(open(os.path.join(HERE, 'voices.json')))['fighters']['terry']['voices']}
    res['voices'] = []
    for i in VOICES:
        shutil.copy(os.path.join(WAVS, f'{i}.wav'), os.path.join(out, 'voices', f'{i}.wav'))
        res['voices'].append({'id': i, 'cmd': vj[i]['cmd'], 'ms': vj[i]['ms'], 'game': vj[i].get('game', 'kof98'), 'wav': f'voices/{i}.wav'})
    json.dump(res, open(os.path.join(out, 'frames.json'), 'w'), indent=1)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'chainlab', 'decisions-media', 'terry-max-voices'),
         sys.argv[2] if len(sys.argv) > 2 else None)
