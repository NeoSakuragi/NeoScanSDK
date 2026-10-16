#!/usr/bin/env python3
"""The sounds of a fighter's win poses in Samurai Shodown II, frame by frame, in our emulator (note 20261016-133259-e03d:
"some sounds are missing from Haohmaru's victory pose"). wins_ss2.play's setup (P1 wins by time over, the stick picks
the pose: subs 0-3 a round, 4-7 the match), with the sound ring decoded (mozu_ss2.queued: the words the 68000 queues
each frame, with their sound ids) and the Z80 latch (the bytes it receives); frames from the first frame of the pose's
first animation (P1 +$66). A sound id < $100 is one of the game's shared effects (voices.py samsho2_list), $100+ the
fighter's own; prefix $1C = his voice slot, $18 / $1A effect slots, $15 = silent in the driver.

    python3 winsnd_ss2.py [CHAR] [--out DIR]          (default haohmaru, /data/tmp/winsnd)
-> DIR/<char>.json {pose: {'anims', 'queued': [[frame, word, ids]], 'latch': [[frame, word]]}}"""
import json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cap_ss2 as C, wins_ss2 as WS, mozu_ss2 as MZ

def play(name, stick, match, d):
    st = WS.STATES[name]
    shutil.rmtree(d, ignore_errors=True)
    C.run(d, '4:-', load=st, vram=False, frames=[1], sndlog=False)
    r = C.ram(d, 1); a1, a2 = C.players(r)
    x = WS.u16(r, a1 - 0x100000 + 0x4E) + 50
    pk = [f'{f}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}' for f in range(1, 4)] + ['40:100AC6=01']
    if match: pk += [f'{f}:{a2 + 0xF1:X}=00' for f in (5, 100, 199)]
    shutil.rmtree(d, ignore_errors=True)
    seq = '10:-,3:a,187:-,' + f'{WS.NF - 200}:{stick}'
    C.run(d, seq, load=st, vram=False, frames=range(1, WS.NF), pokes=';'.join(pk), sndlog=True)
    anims, rams = [], []
    for f in range(1, WS.NF):
        r = C.ram(d, f)
        if r is None: continue
        a1, _ = C.players(r)
        a = WS.u16(r, a1 - 0x100000 + 0x66)
        if not anims or anims[-1][0] != a: anims.append([a, f])
        rams.append((f, r))
    snd = [l for l in open(os.path.join(d, 'snd.txt')).read().split('\n') if l.strip()] if os.path.exists(os.path.join(d, 'snd.txt')) else []
    return anims, MZ.queued(rams), MZ.latch({'snd': snd})

def main(name, out):
    ch = WS.CAST[name]; res = {}
    for p in WS.poses(ch):
        sub = p['subs'][0]; match = sub >= 4
        want = [x['anim'] for x in p['parts']]
        anims, q, lat = play(name, WS.STICK[sub & 3], match, os.path.join(out, 'cap', f'{name}_{sub}'))
        seq = [a for a, _ in anims]
        i = next(j for j in range(len(seq)) if seq[j:j + len(want)] == want)
        t0 = anims[i][1]
        res[f'sub{sub}'] = {'subs': p['subs'], 'anims': [[a, f - t0] for a, f in anims[i:]],
                            'queued': [[f - t0, w, ids] for f, w, ids in q if f >= t0 - 2],
                            'latch': [[f - t0, w] for f, w in lat if f >= t0 - 2]}
        print(name, 'subs', p['subs'], want, 'from frame', t0)
        for f, w, ids in res[f'sub{sub}']['queued']: print('   queued', f, w, ids)
        print('   latch', res[f'sub{sub}']['latch'])
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, f'{name}.json'), 'w'), indent=1)

if __name__ == '__main__':
    a = sys.argv[1:]; out = '/data/tmp/winsnd'
    if '--out' in a: i = a.index('--out'); out = a[i + 1]; del a[i:i + 2]
    main(a[0] if a else 'haohmaru', out)
