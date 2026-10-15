#!/usr/bin/env python3
"""Hanzo's Mozu Otoshi (6 2 3 + C / D / C+D) CONNECTING in Samurai Shodown II, measured in our emulator (notes
20261015-212217-e03d / 212313: "too slow, in the real game the character goes out of the screen or very high, and his
voice"). P1 Hanzo (cap/p1_02.state), P2 poked GAP px in front of him, the command played; per frame both players'
class / action (+$E6 / +$E7), animation, world x / height, the camera, and every sound word the 68000 sends.

    python3 mozu_ss2.py [C|D|CD ...] [--out DIR]      (default all three; /data/tmp/mozu_ss2)
-> DIR/mozu_<b>.json (rows, sounds) + DIR/<b>/snap*.png every 4th frame"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cap_ss2 as C

STATE = '/data/neogeo_dict/samsho2/cap/p1_02.state'
GAP = 50
SEQ = {'C': '10:-,3:R,3:D,3:DR,3:DRc,200:-', 'D': '10:-,3:R,3:D,3:DR,3:DRd,200:-', 'CD': '10:-,3:R,3:D,3:DR,3:DRcd,200:-'}

def side(r, a):
    o = C.obj(r, a); b = a - 0x100000
    return dict(cls=r[b + 0xE6], act=r[b + 0xE7], anim=o['anim'], wx=o['wx'], wy=o['wy'], x=o['x'], y=o['y'], face=o['facing'])

def capture(btn, out):
    d = os.path.join(out, btn)
    C.run(d + '/probe', '3:-', load=STATE, vram=False, sndlog=False)
    r = C.ram(d + '/probe', 1); a1, a2 = C.players(r)
    x = C.obj(r, a1)['wx'] + GAP
    n = C.nframes(SEQ[btn])
    pk = ';'.join(f'{k}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}' for k in range(1, 12))
    C.run(d, SEQ[btn], load=STATE, vram=False, pokes=pk, snaps=range(4, n - 1, 4))
    rows = []
    for f in range(1, n - 1):
        rr = C.ram(d, f)
        if rr is None: continue
        rows.append({'f': f, 'p1': side(rr, a1), 'p2': side(rr, a2)})
    snd = open(os.path.join(d, 'snd.txt')).read().split('\n') if os.path.exists(os.path.join(d, 'snd.txt')) else []
    json.dump({'button': btn, 'gap': GAP, 'rows': rows, 'snd': [l for l in snd if l.strip()]},
              open(os.path.join(out, f'mozu_{btn}.json'), 'w'), indent=0)
    return rows, snd

if __name__ == '__main__':
    a = sys.argv[1:]; out = '/data/tmp/mozu_ss2'
    if '--out' in a: i = a.index('--out'); out = a[i + 1]; del a[i:i + 2]
    for b in a or ['C', 'D', 'CD']:
        rows, snd = capture(b, out)
        print(b, len(rows), 'frames;', len(snd), 'sound lines')
