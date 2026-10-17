#!/usr/bin/env python3
"""Terry's MAX = Real Bout Special's Triple Geyser shouts (note 20261017-145343-e03d; game.json roster terry prog_voices,
voices.json terry 22 / 23 borrowed from rbffspec). In our emulator (the repo's Geolith core, its Z80 port tap): Terry's
MAX (down + D) in the Chain Lab against Ryo, at point blank (the hit path) and out of reach (the whiff), P1's life 10 (the MAX's low-life rule) and the bars full; every voice
command the Z80 reads ($1C / $1B + code) with the ADPCM-A key-on it starts, the frame, P1's state, the eruptions on
screen (projectile entities alive); the played bytes (our V ROM at the key-on's start / end) against Real Bout Special's
V ROM at the voice's sample: identical. A picture at each voice, contact sheet + a WAV of each played sample.

    python3 rbsgeyser_proof.py OUTDIR [ROM]"""
import ctypes as C, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario, voices as V

CASES = [('hit', 60), ('whiff', 220)]                     # the dummy's gap (px)
KEYS = '2:Dd,260:-'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
PAIRED = {0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E}

def main(out, rom=None):
    os.makedirs(out, exist_ok=True)
    b = H.Brawler(rom=rom, options=scenario.SYSTEMS['mvs-mvs']) if rom else H.Brawler(options=scenario.SYSTEMS['mvs-mvs'])
    b.game = H.GAME
    game_dir = os.path.dirname(os.path.abspath(rom)) if rom else H.GAME
    vrom = open(os.path.join(game_dir, 'build', 'snd', 'v1.bin'), 'rb').read()
    rbs = V.v_rom('rbffspec')
    bank = {vo['id']: vo for vo in json.load(open(V.JSON))['fighters']['terry']['voices']}
    want = {i: bank[i] for i in (22, 23)}
    log, a = [], [0, 0]
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 6: a[1] = v
            elif p == 7: log.append((b.frame, 'b', a[1], v))
        elif p == 0 and v: log.append((b.frame, 'c', v, 0))
        return v
    cb = TAP(tap)
    res = {}
    npj = (b.syms['projectiles_end'] - b.syms['projectiles']) // b.fsize if 'projectiles_end' in b.syms else 8
    for name, gap in CASES:
        scenario.setup(b, {'setup': {'mode': 'lab', 'fighter': 'terry', 'dummy': 'ryo', 'gap': gap, 'drive': 'full', 'fury': 'full', 'hp': 10}})
        b.core.retro_neoscan_z80_tap(cb); del log[:]; f0 = b.frame; rows = {}; shots = {}
        def each(bb):
            alive = sum(1 for i in range(npj) if bb.states[bb.pget(i, 'state')] != 'OFF')
            rows[bb.frame] = (bb.states[bb.fget(0, 'state')], alive)
        for part in KEYS.split(','):
            n, k = part.split(':'); b.run(int(n), k.replace('-', ''), '', each)
        b.core.retro_neoscan_z80_tap(C.cast(None, TAP))
        ev, reg, wantp, pend = [], {}, None, None
        for f, kind, x, y in log:
            if kind == 'c':
                if wantp is not None:
                    if wantp in (0x1C, 0x1B): pend = (wantp, x, f)
                    wantp = None
                elif x in PAIRED: wantp = x
                continue
            reg[x] = y
            if x == 0 and not y & 0x80 and y and pend:
                ch = (y & -y).bit_length() - 1
                st, en = reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0), reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)
                e = {'frame': pend[2] - f0, 'cmd': f'{pend[0]:02X}{pend[1]:02X}', 'start': st, 'end': en, 'level': reg.get(8 + ch),
                     'p1': rows.get(pend[2], ('?', 0))[0], 'eruptions_alive': rows.get(pend[2], ('?', 0))[1], 'nbytes': (en - st + 1) << 8}
                for i, vo in want.items():
                    s0, e0 = vo['segments'][0]
                    if vrom[st << 8:(en + 1) << 8] == rbs[s0 << 8:(e0 + 1) << 8]: e.update(voice=i, rbs_cmd=vo['cmd'], bytes_equal=True)
                e['wav'] = os.path.join(out, f"{name}_{e['frame']:03d}_{e['cmd']}.wav")
                V.write_wav(e['wav'], vrom, [[st, en]])
                ev.append(e); pend = None
        er = [(f - f0, n) for f, (s, n) in sorted(rows.items())]
        starts = [f for (f, n), (_, p) in zip(er[1:], er) if n > p]   # frames an eruption entity appeared
        res[name] = {'voices': ev, 'new_entities_at': starts}
        print(name, 'entities appear at', starts)
        for e in ev: print(' ', e['frame'], e['cmd'], e.get('voice'), e.get('rbs_cmd'), 'BYTES EQUAL' if e.get('bytes_equal') else 'not an RBS voice',
                           f"${e['start']:04X}-${e['end']:04X}", e['nbytes'], 'bytes, P1', e['p1'])
        # pictures at each voice
        scenario.setup(b, {'setup': {'mode': 'lab', 'fighter': 'terry', 'dummy': 'ryo', 'gap': gap, 'drive': 'full', 'fury': 'full', 'hp': 10}})
        f0 = b.frame; at = sorted({e['frame'] + 6 for e in ev})
        b.run(2, 'Dd'); t = 2
        for k in at:
            if k > t: b.run(k - t); t = k
            b.screenshot(os.path.join(out, f'{name}_{k:03d}.png')); t += 1
        try:
            from PIL import Image, ImageDraw
            ims = [Image.open(os.path.join(out, f'{name}_{k:03d}.png')) for k in at]
            if ims:
                w, h = ims[0].size; sh = Image.new('RGB', (w * len(ims), h + 14), 'white'); d = ImageDraw.Draw(sh)
                for i, (k, im) in enumerate(zip(at, ims)):
                    sh.paste(im, (i * w, 14)); e = [x for x in ev if x['frame'] + 6 == k][0]
                    d.text((i * w + 4, 1), f"{name} f{k - 6} ${e['cmd']} voice {e.get('voice')}", fill='black')
                sh.save(os.path.join(out, f'{name}_sheet.png'))
        except ImportError: pass
    ok = all(any(e.get('voice') == 22 for e in r['voices']) and any(e.get('voice') == 23 for e in r['voices']) and
             all(e.get('bytes_equal') for e in r['voices']) for n_, r in res.items() if n_ == 'hit')
    res['ok'] = ok
    json.dump(res, open(os.path.join(out, 'report.json'), 'w'), indent=1)
    print('ALL OK' if ok else 'FAIL')
    return ok

if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None) else 1)
