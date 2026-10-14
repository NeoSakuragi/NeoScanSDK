#!/usr/bin/env python3
"""Final Fight's Guy / Cody / Haggar in the brawler (our emulator: tools/brawler/harness.py, the Geolith core; never MAME),
the Lab shell with the fighter's pack (make LAB_PACK=<f> -> examples/brawler/pack-<f>.neo), the same scenarios FF was
measured in (rec_ff.py), every frame logged (+ a picture for the side-by-side sheets, sbs_ff.py):

  walk (forward held 60 frames), jumpn / jumpf (B; forward + B), special (A+B), chain (A pressed every other frame
  against the dummy), chain_back (the same, back + A on the last link), grab_knees (walk into the dummy, A x3),
  grab_fwd / grab_back (forward / back + A in the hold), grab_up (up + A: Haggar's piledriver)

    python3 ff_proof.py NAME [SCENARIO ...] [--png]   -> /data/tmp/ffight/brawler/NAME_SCENARIO.json (+ png/...)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR)
import harness
from labdrive import Lab
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
OUT = '/data/tmp/ffight/brawler'
DUMMY = 'terry'
LINKS = {'guy': 5, 'cody': 4, 'haggar': 3}

def scen_keys(name, scen):
    """-> (dummy gap px or None (far away), a function k -> keys for frame k given the log so far, frames)"""
    n = LINKS[name]
    if scen == 'walk': return None, lambda k, log: 'R', 60
    if scen == 'jumpn': return None, lambda k, log: 'b' if k == 0 else '', 70
    if scen == 'jumpf': return None, lambda k, log: 'Rb' if k == 0 else 'R', 70
    if scen == 'special': return None, lambda k, log: 'ab' if k == 0 else '', 90
    def hits(log): return sum(1 for r in log if r.get('dmg'))
    if scen == 'chain': return 34, lambda k, log: ('a' if k % 2 == 0 else '') if hits(log) < n else '', 160
    if scen == 'chain_back':
        return 34, lambda k, log: (('La' if hits(log) >= n - 1 else 'a') if k % 2 == 0 else '') if hits(log) < n else '', 160
    if scen.startswith('grab_'):
        act = scen[5:]
        def keys(k, log):
            g = next((i for i, r in enumerate(log) if r['state'] == 'GRAB'), None)
            if g is None: return 'R'
            j = k - g
            if act == 'knees': return 'a' if j in (6, 26, 46) else ''
            if act == 'fwd': return 'Ra' if j == 6 else ''
            if act == 'back': return 'La' if 4 <= j <= 6 and j == 6 else ('L' if 2 <= j < 6 else '')
            if act == 'up': return 'Ua' if j == 6 else ''
            return ''
        return 60, keys, 260
    raise KeyError(scen)

SCENS = ['walk', 'jumpn', 'jumpf', 'special', 'chain', 'chain_back', 'grab_knees', 'grab_fwd', 'grab_back', 'grab_up']

def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('name'); ap.add_argument('scen', nargs='*'); ap.add_argument('--png', action='store_true')
    a = ap.parse_args(); f = a.name
    harness.GAME = GAME
    L = Lab(rom=os.path.join(GAME, f'pack-{f}.neo'), game=GAME, build='build_shell'); b = L.b; ST = b.states
    G = json.load(open(os.path.join(GAME, 'game.json')))
    names = [r['name'] for r in G['roster']]; fid = len(names)
    ba = json.load(open(os.path.join(GAME, f'build_pack_{f}', 'lab.json')))['ba'] if os.path.exists(os.path.join(GAME, f'build_pack_{f}', 'lab.json')) else None
    L.start(fid, names.index(DUMMY)); b.run(30); base = b.save()
    os.makedirs(OUT, exist_ok=True)
    for s in a.scen or SCENS:
        if s == 'grab_up' and f != 'haggar': continue
        b.load(base)
        gap, keys, frames = scen_keys(f, s)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + (gap if gap else 400), z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', b.fget(2, 'hp_max'))
        b.run(2)
        pdir = os.path.join(OUT, 'png', f'{f}_{s}')
        if a.png: os.makedirs(pdir, exist_ok=True)
        log = []; hp = b.fget(2, 'hp'); X0 = b.fget(0, 'x')
        for k in range(frames):
            kk = keys(k, log)
            if a.png:
                b.pad = [set(kk), set()]; b.screenshot(os.path.join(pdir, '%03d.png' % k))
            else: b.run(1, p1=kk)
            h = b.fget(2, 'hp')
            r = {'f': k, 'keys': kk, 'state': ST[b.fget(0, 'state')], 'anim': b.fget(0, 'anim'), 'step': b.fget(0, 'step'),
                 'x': round(b.fget(0, 'x') - X0, 3), 'y': round(b.fget(0, 'y'), 3), 'facing': b.fget(0, 'facing'),
                 'freeze': b.fget(0, 'freeze'), 'frame': b.fget(0, 'shown_frame'),
                 'd_state': ST[b.fget(2, 'state')], 'd_x': round(b.fget(2, 'x') - X0, 1), 'd_y': round(b.fget(2, 'y'), 1),
                 'd_hp': h, 'dmg': hp - h if h < hp else 0, 'd_freeze': b.fget(2, 'freeze'), 'cam': b.r(b.syms['cam_x'], 2) - cam,
                 'sx': round(b.fget(0, 'x') - b.r(b.syms['cam_x'], 2))}
            if ba and r['anim'] < len(ba): r['move'] = ba[r['anim']]
            log.append(r); hp = h
        json.dump({'fighter': f, 'scenario': s, 'rows': log}, open(os.path.join(OUT, f'{f}_{s}.json'), 'w'))
        seq = []
        for r in log:
            k_ = (r['state'], r.get('move', r['anim']))
            if not seq or seq[-1][0] != k_: seq.append([k_, 1])
            else: seq[-1][1] += 1
        print(s, ' '.join(f'{st}/{mv}x{n}' for (st, mv), n in seq[:16]), '| dmg', [r['dmg'] for r in log if r['dmg']])

if __name__ == '__main__': main()
