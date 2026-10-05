#!/usr/bin/env python3
"""Cancel windows of Kim's normals, measured in our emulator: each normal (P2 in reach, so it hits) followed by a
follow-up input started k frames after the normal's button (k = 1..36): the window = the k for which the follow-up's
animation starts before the normal returns to idle (a cancel), with the frame it starts on.
    python3 cancels_kz.py [OUT.json]       (default /data/neogeo_dict/kizuna/cancels_kz.json)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import capture_kz as K
OUT = '/data/neogeo_dict/kizuna/cancels_kz.json'
NORMALS = {'close_a': ('a', 0x48), 'close_b': ('b', 0x52), 'close_c': ('c', 0x5B), 'far_a': ('a', 0x46),
           'far_b': ('b', 0x50), 'far_c': ('c', 0x5A), 'crouch_a': ('Da', 0x4B), 'crouch_b': ('Db', 0x55),
           'crouch_c': ('Dc', 0x5E), 'fwd_b': ('Rb', 0x53), 'fwd_c': ('Rc', 0x5C), 'df_c': ('DRc', 0x5F), 'bc': ('bc', 0x6E)}
FOLLOW = {'236C': ('3:D,3:DR,3:R,3:c,3:c', [0x97]), '214B': ('3:D,3:DL,3:L,3:b,3:b', [0x93]),
          '[2]8C': (None, [0x9B]), 'B': ('3:b', [0x52, 0x50, 0x55]), 'C': ('3:c', [0x5B, 0x5A, 0x5E])}

def probe(nm, fu, k):
    btn, anim = NORMALS[nm]
    pre = '2:-,'
    seq = f'{pre}3:{btn},'
    fs, fa = FOLLOW[fu]
    if fs is None: return None
    seq += f'{max(k - 3, 0) + 1}:-,{fs},80:-' if k > 3 else f'{fs},80:-'
    p2x = 300 if not nm.startswith('far') else 360
    K.RECIPES['tmp'] = (p2x, seq, '')
    fr = K.capture('tmp')
    p1 = [f[0][0] for f in fr]
    if anim not in p1: return None
    s = p1.index(anim)
    for i in range(s, len(p1)):
        if p1[i] in fa: return i - s
        if p1[i] in (0xA0, 0x0, 0x7, 0xA3) and i > s: return None
    return None

if __name__ == '__main__':
    out = {}
    for nm in NORMALS:
        for fu in FOLLOW:
            if FOLLOW[fu][0] is None: continue
            ok = []
            for k in range(1, 37):
                r = probe(nm, fu, k)
                if r is not None: ok.append([k, r])
            out[f'{nm}>{fu}'] = {'cancel': bool(ok), 'input_frames': [a for a, b in ok], 'starts_at': [b for a, b in ok]}
            print(nm, fu, [a for a, b in ok][:3], '...', [a for a, b in ok][-2:], 'starts', sorted({b for a, b in ok})[:6])
    json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else OUT, 'w'))
