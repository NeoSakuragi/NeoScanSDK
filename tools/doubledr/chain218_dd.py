#!/usr/bin/env python3
"""TODO #218: Cheng-Fu's far D chain (22 > 43 > 41) and his down attack (8 / 2 + button -> 124 > 125) measured in Double
Dragon in our emulator (emu/neogeo_sdl --capture), next to the model (model_dd).

    python3 chain218_dd.py far        the far D: tapped / held / mashed, hit and whiff (P2 poked away)
    python3 chain218_dd.py down       the down attack: P2 knocked down by the far D, then 2 + button / 8 + button
-> per frame P1 anim / step / x / y and P2 anim / damage; /data/neogeo_dict/doubledr/chain218.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_dd as c, dd, model_dd as M
P1, P2 = 0x10042A, 0x10052A
STATE = '/data/neogeo_dict/doubledr/cap/p1_10.state'
FAR = ';'.join(f'{f}:100530=03,100531=00' for f in range(1, 400))
OUT = '/data/neogeo_dict/doubledr/chain218.json'

def g(R, a, n=1, signed=False):
    o = a - 0x100000; v = int.from_bytes(R[o:o + n], 'big')
    return v - (1 << 8 * n) if signed and v >> (8 * n - 1) else v

def rows(seq, far=False, pokes=None, snaps=None):
    pk = ';'.join(x for x in (FAR if far else '', pokes or '') if x) or None
    out = []
    for r in c.run(seq, load=STATE, pokes=pk, snaps=snaps):
        R = r['ram']; F = dd.fighter_fields(R, P1); G = dd.fighter_fields(R, P2)
        out.append(dict(f=r['f'], a=F['anim'], s=F['step'], d=F['def_'], x=F['x'], y=488 - F['y'], left=bool(F['dir'] & 0x20),
                        a2=G['anim'], s2=G['step'], x2=G['x'], y2=488 - G['y'], dmg=g(R, P2 + 0x26, 2), snd=r['snd'],
                        f3=g(R, P2 + 0xF3), f7=g(R, P1 + 0xF7), vx=g(R, P1 + 0xE, 4, True) / 65536, vy=g(R, P1 + 0x12, 4, True) / 65536))
    return out

def anims(rs):
    out = []
    for q in rs:
        if not out or out[-1] != q['a']: out.append(q['a'])
    return out

def summary(rs, t0):
    a = [q for q in rs if q['f'] >= t0]
    s = next((i for i, q in enumerate(a) if q['a'] not in (0, 1, 2, 3)), None)
    if s is None: return {'anims': []}
    e = next((i for i in range(s, len(a)) if a[i]['a'] in (0, 1, 2, 3)), len(a))
    hits = [[a[i]['f'] - a[s]['f'], a[i]['a'], a[i]['s'], a[i]['dmg'] - a[i - 1]['dmg']] for i in range(s + 1, len(a)) if a[i]['dmg'] != a[i - 1]['dmg']]
    return {'anims': anims(a[s:e]), 'frames': e - s, 'hits': hits, 'p2': anims([dict(a=q['a2']) for q in a[s:]]),
            'dx': a[e - 1]['x'] - a[s]['x'], 'peak': max(q['y'] for q in a[s:e]),
            'track': [[q['a'], q['s'], q['d'], abs(q['x'] - a[s]['x']), q['y']] for q in a[s:e]]}

def far():
    res = {}
    for label, btn, far_ in (('tap', '3:d', False), ('tap1', '1:d', False), ('held', '60:d', False), ('whiff', '3:d', True),
                             ('whiff_held', '60:d', True)):
        pre = '30:R,12:-,' if not far_ else '20:-,'
        t0 = c.nframes(pre)
        rs = rows(pre + btn + ',140:-', far=far_)
        res[label] = summary(rs, t0)
        print(label, res[label]['anims'], res[label]['frames'], 'hits', res[label]['hits'], 'p2', res[label]['p2'][:8], flush=True)
    m = M.play(10, 22)
    res['model'] = [[r['anim'], r['step'], r['def_'], r['x'], r['y']] for r in m]
    return res

if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'far'
    old = json.load(open(OUT)) if os.path.exists(OUT) else {}
    old[what] = far() if what == 'far' else None
    json.dump(old, open(OUT, 'w'), indent=1)
