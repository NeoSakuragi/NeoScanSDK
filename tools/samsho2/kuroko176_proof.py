#!/usr/bin/env python3
"""TODO #176 follow-up proof: Kuroko's flag boomerang (6 3 2 1 4 A, spawn.boomerang) and his two parodies that the
palette budget had kept out (1 2 6 BC, 2 1 4 1 6 BC), in the brawler (the harness: the game's ROM on the Geolith core,
Kuroko picked on the select screen, the Chain Lab's standing dummy, the pad) against SS2 in our emulator
(boomerang_ss2.py: /data/tmp/kuroko176/ss2/<case>.json + its screenshots).

    python3 kuroko176_proof.py [OUTDIR]          (default /data/tmp/kuroko176/out; run boomerang_ss2.py first)

Boomerang cases (SS2's: Kuroko 243, P2 at 400 = 157 px, or poked):
  whiff  the dummy 280 px away (SS2: P2 poked to 560): out of the flag's reach
  out    the dummy 157 px away: the flag hits it going out, stops there, hovers, comes back
  back   the dummy 280 px away, then put 147 px from him 33 frames after the flag appeared (SS2: P2 poked to 390 at
         frame 76): in the flag's return path
Per case, from the flag's first frame: Kuroko's SS2 animation (his program's state), the flag's distance from him and
its pole segments' (brawler entity x - his x vs SS2 object x - his x), the hits on the dummy; equal = every frame the
same. Sheets: brawler screenshots / SS2 screenshots, every 2nd frame from the move's start -> boomerang_<case>.png,
parody_<input>.png, kuroko176.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kuroko176/out'
SS2 = '/data/tmp/kuroko176/ss2'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))

def lab_req(b, req, fighter, dummy):
    L = b.syms['lab']
    for i, ch in enumerate(b'LAB1'): b.w(L + i, 1, ch)
    b.w(L + 5, 1, fighter); b.w(L + 6, 1, dummy); b.w(L + 4, 1, req)

_steps = {}
def ss2_step(a, addr):
    """the index of SS2 step `addr` in Kuroko's animation a"""
    import ss2
    if a not in _steps: _steps[a] = {x['addr']: i for i, x in enumerate(ss2.parse_anim(17, a, 400))}
    return _steps[a].get(addr)

def ss2_case(case):
    """SS2's timeline from the flag's first frame (or the move's start): per frame Kuroko's animation and step, the
    flag's distance from him, its segments', P2 hit (class 3), the slow motion ($8AD3 / $8AC9: a hit's half speed,
    not modelled by the brawler: its own hit-stop)"""
    rows = json.load(open(f'{SS2}/{case}.json'))
    s0 = next(i for i, q in enumerate(rows) if q['p1']['cls'] == 1)
    f0 = next((i for i, q in enumerate(rows) if q['flag']), s0)
    tl = []
    for q in rows[f0:]:
        p1 = q['p1']
        fl = q['flag']
        tl.append(dict(f=q['f'], anim=p1['a'] if p1['cls'] == 1 else None, step=ss2_step(p1['a'], p1['st']) if p1['cls'] == 1 else None,
                       flag=fl['x'] - p1['x'] if fl else None,
                       segs=sorted(g['x'] - p1['x'] for g in q['segs']) if fl else [], hit=q['p2']['cls'] == 3))
        if p1['cls'] != 1: break
    return rows, s0, f0, tl

def snaps(case, f_from, n, every=2):
    out = []
    for f in range(f_from, f_from + n * every, every):
        p = f'{SS2}/{case}/snap_{f}.ppm'
        out.append(Image.open(p).convert('RGB').resize((160, 112)) if os.path.exists(p) else Image.new('RGB', (160, 112), 'white'))
    return out

def sheet(path, strips):
    W = 160 * max(len(c) for _, c in strips) + 150
    img = Image.new('RGB', (W, 112 * len(strips)), 'white'); d = ImageDraw.Draw(img)
    for i, (nm, cs) in enumerate(strips):
        d.text((4, i * 112 + 4), nm, fill='black')
        for j, c in enumerate(cs): img.paste(c, (150 + j * 160, i * 112))
    img.save(path)

def main():
    os.makedirs(OUT, exist_ok=True)
    b = Brawler(rom=os.path.join(GAME, 'brawler.neo'), game=GAME)
    import re
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    k = bcs.index('BC_KUROKO')
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_samsho2_kuroko', 'kof95_export.json')))['characters']['kuroko']
    roster = {r['name']: r for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']}['kuroko']
    sps = {sp['input']: sp for sp in ex['specials']}
    fexp = {}                                          # SS2 (animation, step) -> the exported frame (the boomerang's
    for st, a in sps['63214A']['rom']['anims'].items():   # program states)
        for s in a['steps']: fexp[tuple(s['ss2'])] = s['frame']
    role_keys = {'D': 'c', 'fD': 'Rc', 'dD': 'Dc', 'uD': 'Uc', 'dfD': 'DRc', 'ufD': 'URc'}
    keys_of = lambda inp: role_keys[next(r for r, v in roster['specials'].items() if v == inp)]
    PROJ = b.states.index('PROJ')
    b.pick(k)
    res = {'slots': roster['specials']}

    def setup(gap, facing=1):
        lab_req(b, 1, k, 0); b.run(40)
        assert b.char_of(0) == k, 'P1 is not Kuroko'
        dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
        cam = b.r(b.syms['cam_x'], 2); cam = cam - 65536 if cam > 32767 else cam
        x0 = cam + (16 if facing > 0 else 304)            # (both inside the screen's walls, 16 / 304: gap <= 280)
        b.place(0, x=x0); b.place(dm, x=x0 + facing * gap, z=b.fget(0, 'z'))
        b.fset(0, 'facing', facing & 0xFF); b.fset(dm, 'facing', -facing & 0xFF); b.run(5)
        assert abs(b.fget(dm, 'x') - b.fget(0, 'x') - facing * gap) < 1, ('gap', b.fget(0, 'x'), b.fget(dm, 'x'))
        return dm

    def play(keys, frames, dm, gap=None, pokes=(), shots_from=None):
        """the pad's keys 4 frames, then nothing; per frame Kuroko / the flag / its segments / the dummy; screenshots every
        2nd frame from the special's start"""
        tl, cells, h0, start = [], [], len(b.hits), None
        for f in range(frames):
            for pf, dx in pokes:
                if f == pf: b.place(dm, x=b.fget(0, 'x') + dx)
            shot = start is not None and f > start and (f - start) % 2 == 0 and len(cells) < 40   # (SS2's: from its 3rd frame too)
            if shot:
                p = os.path.join(OUT, '_shot.png'); b.pad = [set(keys) if f < 4 else set(), set()]; b.screenshot(p)
                cells.append(Image.open(p).resize((160, 112)))
            else: b.run(1, p1=keys if f < 4 else '')
            st = b.states[b.fget(0, 'state')]
            if start is None and st == 'SPECIAL': start = f
            ents = [i for i in range(8) if b.pget(i, 'state') == PROJ and b.pget(i, 'owner') == b.base]
            by = {}
            for i in ents: by.setdefault(b.pget(i, 'pdef'), []).append(i)
            flag = next((v[0] for v in by.values() if len(v) == 1), None)
            segs = sorted(i for v in by.values() if len(v) == 2 for i in v)
            x = b.fget(0, 'x'); fc = 1 if b.fget(0, 'facing') == 1 else -1
            tl.append(dict(f=f, gf=b.frame, state=st, frame=b.fget(0, 'frame_ovr') if st == 'SPECIAL' else None,
                           flag=round(fc * (b.pget(flag, 'x') - x)) if flag is not None else None,
                           phase=b.pget(flag, 'pstep') if flag is not None else None,
                           segs=sorted(round(fc * (b.pget(i, 'x') - x)) for i in segs) if flag is not None else [],
                           dummy=b.states[b.fget(dm, 'state')]))
        hits = [(h[0], h[1], h[2], h[3]) for h in b.hits[h0:]]
        return tl, cells, hits

    # ---- the boomerang ---------------------------------------------------------------------------------------------
    cases = {'whiff': dict(gap=280), 'out': dict(gap=157), 'back': dict(gap=280, poke=33, to=147)}
    res['boomerang'] = {}
    for case, c in cases.items():
        rows, s0, f0, sref = ss2_case(case)
        dm = setup(c['gap'])
        tl0, cells, hits = play(keys_of('63214A'), 150, dm)
        if c.get('poke') is not None:                     # replay with the dummy moved into the return path
            dm = setup(c['gap'])
            first = None
            # the flag's first frame in this run (deterministic: the same as the first run's)
            first = next(t['f'] for t in tl0 if t['flag'] is not None)
            tl0, cells, hits = play(keys_of('63214A'), 150, dm, pokes=[(first + c['poke'], c['to'])])
        bf = next(i for i, t in enumerate(tl0) if t['flag'] is not None)
        bt = [dict(frame=t['frame'], flag=t['flag'], segs=t['segs']) for t in tl0[bf:bf + len(sref)]]
        st = [dict(frame=fexp.get((t['anim'], t['step'])), flag=t['flag'], segs=t['segs']) for t in sref]
        same = [a == s for a, s in zip(bt, st)]
        dedup = lambda xs: [x for i, x in enumerate(xs) if i == 0 or x != xs[i - 1]]
        bhit = [h[0] for h in hits if h[1] != 0]
        start_b = next(i for i, t in enumerate(tl0) if t['state'] == 'SPECIAL')
        out = dict(frames=len(st), equal_frames=sum(same), first_diff=next((i for i, x in enumerate(same) if not x), None),
                   brawler_hits=[(h[0] - tl0[bf]['gf'], h[2], h[3]) for h in hits if h[1] != 0],
                   ss2_hit_frames=[i for i, t in enumerate(sref) if t['hit'] and (i == 0 or not sref[i - 1]['hit'])],
                   brawler_flag=[t['flag'] for t in bt], ss2_flag=[t['flag'] for t in st],
                   brawler_frames=[t['frame'] for t in bt], ss2_frames=[t['frame'] for t in st],
                   flag_path_equal=dedup([t['flag'] for t in bt]) == dedup([t['flag'] for t in st]),
                   pose_order_equal=dedup([t['frame'] for t in bt]) == dedup([t['frame'] for t in st]),
                   ss2_slow_frames=[i for i, q in enumerate(rows[f0:f0 + len(st)]) if q.get('slow')],
                   brawler_move_frames=sum(1 for t in tl0 if t['state'] == 'SPECIAL'),
                   ss2_move_frames=sum(1 for q in rows if q['p1']['cls'] == 1))
        if out['first_diff'] is not None:
            i = out['first_diff']; out['diff'] = {'brawler': bt[i], 'ss2': st[i], 'at': i}
        res['boomerang'][case] = out
        print('boomerang', case, {k_: v for k_, v in out.items() if not k_.endswith(('_flag', '_frames'))}, flush=True)
        sheet(os.path.join(OUT, f'boomerang_{case}.png'),
              [(f'brawler {case}', cells), (f'SS2 {case}', snaps(case, rows[s0]['f'] + 2, len(cells)))])

    # ---- the two parodies --------------------------------------------------------------------------------------------
    res['parodies'] = {}
    for inp, case in (('126BC', 'p42'), ('214161BC', 'p46')):
        rows, s0, _, _ = ss2_case(case)
        dm = setup(157)
        tl0, cells, hits = play(keys_of(inp), 130, dm)
        ss2_hits = [q['f'] - rows[s0]['f'] for i, q in enumerate(rows[s0:]) if q['p2']['cls'] == 3 and rows[s0 + i - 1]['p2']['cls'] != 3]
        start_b = next(i for i, t in enumerate(tl0) if t['state'] == 'SPECIAL')
        res['parodies'][inp] = dict(keys=keys_of(inp), brawler_hits=[(h[0] - tl0[start_b]['gf'], h[2], h[3]) for h in hits if h[1] != 0],
                                    ss2_hits=ss2_hits, brawler_move_frames=sum(1 for t in tl0 if t['state'] == 'SPECIAL'),
                                    ss2_move_frames=sum(1 for q in rows if q['p1']['cls'] == 1))
        print('parody', inp, res['parodies'][inp], flush=True)
        sheet(os.path.join(OUT, f'parody_{inp}.png'), [(f'brawler {inp}', cells), (f'SS2 {inp}', snaps(case, rows[s0]['f'] + 2, len(cells)))])
    json.dump(res, open(os.path.join(OUT, 'kuroko176.json'), 'w'), indent=1)

if __name__ == '__main__':
    main()
