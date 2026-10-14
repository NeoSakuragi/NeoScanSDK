#!/usr/bin/env python3
"""T5 (2026-10-14): The Last Blade 2's impact sounds in the brawler, checked in our emulator (tools/brawler/harness.py, the
Geolith core): each hit's sound command (sound.c's queue: $1A + code) against the pick list the data names for it
(songs.json sfx "picks", LB2's hit-sound families: tools/lastbld2/hitsound_lb2.py).

  Moriya (his pack build, make LAB_PACK=moriya): his normals (the TRY chain's A press, LE_MOVE | BA_*: export_lb2
  anims[mv]['hitsnd'] -> bm_hsnd) and his specials (sp_c, LE_SPEC | pool index: handlers_lb2 step_snd -> bm_hsnd
  HS_STEP entries, fighter.c step_sound), each over 8 runs (the start delayed: the tick counter draws the list);
  Haohmaru (the game's build): his 623S / 623AB / 214A (roster hit_sfx "LB2 A8": every program hit) from neutral C / up C...

    python3 lb2_sound_proof.py moriya [OUT.json]   (default /data/tmp/lb2_t456/lb2_sound_proof.json)
    python3 lb2_sound_proof.py sword [OUT.json]    Haohmaru / Genjuro in the game's build (one core per process)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR); sys.path.insert(0, HERE)
import harness
from labdrive import Lab
import lb2_lab_proof as LP
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
SONGS = json.load(open(os.path.join(GAME, 'songs.json')))['sfx']
FROM = {(f['game'], f['cmd']): int(c, 16) for c, f in SONGS['from'].items()}
NAMES = {int(k, 16): v for k, v in SONGS['names'].items()}
def pick(name): return sorted({FROM[(SONGS['picks'][name]['game'], w)] for w in SONGS['picks'][name]['cmds']})

NORMALS = [('atk_a_far', 'LB2 A4', 50), ('atk_b_far', 'LB2 A5', 60), ('body_toss', 'LB2 A2', 100), ('atk_c_far', 'LB2 A8', 60),
           ('atk_b_crouch', 'LB2 A1', 60)]
SPECIALS = [('623A', ['LB2 A8', 'LB2 A1'], 40), ('623B', ['LB2 A9', 'LB2 A1'], 100), ('214A', ['LB2 A0', 'LB2 A1'], 60),
            ('214B', ['LB2 A4', 'LB2 A1'], 60), ('236A', ['LB2 A5'], 60), ('236B', ['LB2 A5'], 80)]
RUNS = 8

class Rec:
    def __init__(s, b):
        s.b = b; s.q, s.qt = b.syms['q'], b.syms['qt']; s.t = b.r(s.qt, 1); s.pend = None; s.hits = []
    def step(s, keys=''):
        b = s.b; hp0 = b.fget(2, 'hp')
        b.run(1, p1=keys)
        new, t = [], b.r(s.qt, 1)
        while s.t != t: new.append(b.r(s.q + s.t, 1)); s.t = (s.t + 1) & 31
        codes = []
        for v in new:
            if s.pend is not None: codes.append((s.pend, v)); s.pend = None
            elif v in (0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x16, 0x17): s.pend = v
        if b.fget(2, 'hp') < hp0: s.hits.append([v for p, v in codes if p == 0x1A and v not in (0x1E, 0x1F)])
        if b.fget(2, 'hp') < 60: b.fset(2, 'hp', b.fget(2, 'hp_max'))

def main(out='/data/tmp/lb2_t456/lb2_sound_proof.json'):
    harness.GAME = GAME
    G = json.load(open(os.path.join(GAME, 'game.json'))); names = [r['name'] for r in G['roster']]
    res, ok = [], True
    L = Lab(rom=os.path.join(GAME, 'pack-moriya.neo'), game=GAME, build='build_pack_moriya'); b = L.b
    fid = len(names); lf = b.syms['lab_fields']
    hdr = open(os.path.join(GAME, 'build_pack_moriya', 'bm_chars.h')).read()
    ba = hdr[hdr.index('enum { BA_IDLE'):].split('}')[0].split('{')[1].replace(' ', '').split(',')
    CLJ = json.load(open(os.path.join(GAME, 'build_pack_moriya', 'chainlab.json')))
    pool = [p['input'] for p in next(x for x in CLJ['fighters'] if x['name'] == 'slot')['pool']]
    L.start(fid, names.index('ryo')); b.run(30); base = b.save()

    def fire(cfg, key, gap, delay, frames=150):
        b.load(base)
        L.poke(lf['tblob'], LP.encode(dict(cfg, fighter=fid))); L.poke(lf['lstat'], [0]); L.poke(lf['tnow'], [1])
        L.poke(0, b'LAB1'); L.poke(5, [fid]); L.poke(7, [6]); b.run(3 + delay)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 90
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + gap, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', b.fget(2, 'hp_max')); b.run(1)
        r = Rec(b)
        for i in range(frames): r.step(key if i < 2 else '')
        return r.hits

    def judge(what, want, runs):
        nh = max((len(h) for h in runs), default=0)
        per = [sorted({c for h in runs if k < len(h) for c in h[k]}) for k in range(nh)]
        good = nh > 0
        for k, cs in enumerate(per):
            w = pick(want[min(k, len(want) - 1)])
            good &= bool(cs) and all(c in w for c in cs)
        res.append({'case': what, 'want': want, 'per_hit': [[f'{c:02X} {NAMES.get(c, "?")}' for c in cs] for cs in per],
                    'result': 'PASS' if good else 'FAIL'})
        print(f'{what:28} {"PASS" if good else "FAIL"}', [[f'{c:02X}' for c in cs] for cs in per], 'want', want, flush=True)
        return good

    for mv, want, gap in NORMALS:
        runs = [fire({'chain': {'entries': [0x4000 | ba.index('BA_' + mv.upper())] * 4}}, 'a', gap, d) for d in range(RUNS)]
        ok &= judge(f'moriya {mv}', [want], runs)
    for inp, want, gap in SPECIALS:
        k = next(i for i, p in enumerate(pool) if p == inp)
        runs = [fire({'slots': {'sp_c': [LP.LE_SPEC | k]}}, 'c', gap, d) for d in range(RUNS)]
        ok &= judge(f'moriya {inp}', want, runs)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, 'w'), indent=1)
    print('ALL PASS' if ok else 'FAIL')
    return ok

SWORD = [('haohmaru', 'c', 'neutral C 623AB', 50), ('haohmaru', 'Dc', 'down C 623S', 50), ('haohmaru', 'Uc', 'up C 214A', 60),
         ('genjuro', 'Dc', 'down C 623S', 50)]

def sword(out='/data/tmp/lb2_t456/lb2_sound_sword.json'):
    harness.GAME = GAME
    G = json.load(open(os.path.join(GAME, 'game.json'))); names = [r['name'] for r in G['roster']]
    L = Lab(); b = L.b; res, ok = [], True; w = pick('LB2 A8')
    for who, key, what, gap in SWORD:
        runs = []
        for d in range(RUNS):
            L.start(names.index(who), names.index('ryo')); b.run(30 + d)
            cam = b.r(b.syms['cam_x'], 2); x0 = cam + 90
            b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
            b.place(2, x=x0 + gap, z=30); b.fset(2, 'facing', 0xFF); b.run(1)
            r = Rec(b)
            for i in range(120): r.step(key if i < 2 else '')
            runs.append(r.hits)
        cs = sorted({c for h in runs for hh in h for c in hh})
        good = bool(cs) and all(c in w for c in cs)
        ok &= good; res.append({'case': f'{who} {what}', 'codes': [f'{c:02X} {NAMES.get(c, "?")}' for c in cs], 'result': 'PASS' if good else 'FAIL'})
        print(f'{who} {what:16} {"PASS" if good else "FAIL"}', [f'{c:02X}' for c in cs], flush=True)
    json.dump(res, open(out, 'w'), indent=1)
    print('ALL PASS' if ok else 'FAIL')
    return ok

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'moriya'
    sys.exit(0 if {'moriya': main, 'sword': sword}[mode](*sys.argv[2:]) else 1)
