#!/usr/bin/env python3
"""The numbers: Final Fight measured (rec_ff.py, FBNeo) vs the brawler measured (ff_proof.py, our emulator), per fighter.
Distances: FF's CPS1 px and the target in Neo Geo px (x 320 / 384: the same distance on a TV, game.json walk / jump
rule); heights unscaled (both 224 lines).

    python3 table_ff.py [NAME ...]   -> stdout (markdown) + /data/tmp/ffight/table_ff.json"""
import json, os, sys
REC, BRW = '/data/tmp/ffight/rec', '/data/tmp/ffight/brawler'
XS = 320 / 384

def ff(n, s): return json.load(open(f'{REC}/{n}_{s}.json'))['rows']
def br(n, s): return json.load(open(f'{BRW}/{n}_{s}.json'))['rows']

def walk(n):
    F = ff(n, 'walk'); B = br(n, 'walk')
    fv = (F[59]['P']['x'] - F[11]['P']['x']) / 48; bv = (B[59]['x'] - B[11]['x']) / 48
    return fv, bv

def jump(n, s):
    F = ff(n, s); B = br(n, s)
    fy = [r['P']['y'] - F[0]['P']['y'] for r in F]; by = [r['y'] for r in B]
    fx = [r['P']['x'] - F[0]['P']['x'] for r in F]; bx = [r['x'] for r in B]
    def m(y, x):
        up = next(i for i, v in enumerate(y) if v > 0); dn = next(i for i in range(up, len(y)) if y[i] <= 0)
        return {'crouch': up, 'air': dn - up, 'peak': max(y), 'dx': round(x[dn] - x[up - 1], 1)}
    return m(fy, fx), m(by, bx)

def special(n):
    F = ff(n, 'special'); B = br(n, 'special')
    idle = F[0]['P']['anim']
    fl = next(i for i in range(1, len(F)) if F[i]['P']['anim'] == idle)
    bl = next(i for i in range(1, len(B)) if B[i]['state'] != 'SPECIAL' and i > 1)
    return {'frames': fl - 1, 'peak': max(r['P']['y'] for r in F) - F[0]['P']['y']}, {'frames': bl, 'peak': round(max(r['y'] for r in B))}

def chain(n, s='chain'):
    F = ff(n, s); B = br(n, s)
    def ffh():
        out, hp = [], F[0]['E']['hp']
        for i, r in enumerate(F):
            if r['E']['hp'] < hp: out.append((i, hp - r['E']['hp']))
            hp = r['E']['hp']
        stop = []
        for i, _ in out:                              # attacker frozen: P's hit-stop counter (+$17) > 0 frames
            k = i; c = 0
            while k < len(F) and F[k]['P']['hs'] > 0: c += 1; k += 1
            stop.append(c)
        return out, stop
    def brh():
        out = [(i, r['dmg']) for i, r in enumerate(B) if r['dmg']]
        stop = []
        for i, _ in out:
            k = i; c = 0
            while k < len(B) and B[k]['freeze'] > 0: c += 1; k += 1
            stop.append(c)
        return out, stop
    (fh, fs), (bh, bs) = ffh(), brh()
    fa = [i for i in range(1, len(F)) if F[i]['P']['anim'] != F[i - 1]['P']['anim']]
    ba = [i for i in range(1, len(B)) if B[i]['anim'] != B[i - 1]['anim']]
    return {'hit_frames': [i for i, _ in fh], 'damage': [d for _, d in fh], 'hitstop': fs},          \
           {'hit_frames': [i for i, _ in bh], 'damage': [d for _, d in bh], 'hitstop': bs}

def throw(n, fs, bs):
    F = ff(n, fs); B = br(n, bs)
    f0 = next(i for i, r in enumerate(F) if r['P']['st'] == 8 or r['P']['anim'] in (0x10480, 0x118C0, 0x13BFA, 0x13450) and i > 2)
    fi = F[f0:]; idle = F[0]['P']['anim']
    fret = next(i for i, r in enumerate(fi) if r['P']['anim'] == idle and i > 2)
    fimp = [i for i in range(1, len(fi)) if fi[i]['E']['hp'] < fi[i - 1]['E']['hp']]
    b0 = next(i for i, r in enumerate(B) if r['state'] == 'THROW'); bi = B[b0:]
    bret = next(i for i, r in enumerate(bi) if r['state'] != 'THROW')
    bimp = [i for i in range(len(bi)) if bi[i]['dmg']]
    return {'frames': fret, 'impacts': fimp, 'damage': [fi[i - 1]['E']['hp'] - fi[i]['E']['hp'] for i in fimp]}, \
           {'frames': bret, 'impacts': bimp, 'damage': [bi[i]['dmg'] for i in bimp]}

def main():
    out = {}
    for n in sys.argv[1:] or ['guy', 'cody', 'haggar']:
        o = out[n] = {}
        fv, bv = walk(n); o['walk'] = {'ff_px_f': round(fv, 3), 'target': round(fv * XS, 3), 'brawler': round(bv, 3)}
        for s in ('jumpn', 'jumpf'):
            a, b = jump(n, s); o[s] = {'ff': a, 'target_dx': round(a['dx'] * XS, 1), 'brawler': b}
        a, b = special(n); o['special'] = {'ff': a, 'brawler': b}
        for s in ('chain', 'chain_back'):
            a, b = chain(n, s); o[s] = {'ff': a, 'brawler': b}
        for fs, bs in (('grab_fwd', 'grab_fwd'), ('grab_back', 'grab_back')) + ((('grab_jumpB', 'grab_up'),) if n == 'haggar' else ()):
            try:
                a, b = throw(n, fs, bs); o[bs] = {'ff': a, 'brawler': b}
            except StopIteration: o[bs] = 'not reached'
        a, b = chain(n, 'grab_knees'); o['knees'] = {'ff': a, 'brawler': b}
    json.dump(out, open('/data/tmp/ffight/table_ff.json', 'w'), indent=1)
    for n, o in out.items():
        print(f'\n## {n}')
        for k, v in o.items(): print(f'- {k}: {json.dumps(v)}')

if __name__ == '__main__': main()
