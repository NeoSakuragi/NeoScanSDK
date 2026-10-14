#!/usr/bin/env python3
"""The effect objects of the KOF96 / 98 / 99 win poses (note 20261011-225104-5d29, Bruno: "a lot of win poses of Yuri
and Kyo embed flames, but I don't see them here ... Terry throwing his cap"), captured in our emulator (emu.py,
neogeo_sdl --capture): wins98.py's round end (P2's life 1, P1's C, one button held through the KO picks the pose) with
the object pool dumped every frame of the pose (RAMDUMP, capture/projectiles.py's reader), so every object the winner
owns (+$84 = P1, or an object of his) born after the KO is listed: what it is (table +$70, state +$72, raw step), where
(x forward from P1, height), and the pose step P1 was on when it was born. Screenshots every SNAP_EVERY frames.

    GAME=kof98 python3 winfx98.py OUTDIR [--compact] ID [ID ...]   (--compact: winfx.json from OUTDIR's captures)
                                                     -> OUTDIR/<game>_<id>.json + OUTDIR/<game>_<id>_<button>/snap_*.ppm
                                                        + wins[_<game>]/winfx.json (compact(): what export96 reads)

Per button: {'p1': [[frame from the KO, state, raw step, x, height] ...], 'objects': [{'born', 'owner', 'frames': [[f, table,
state, raw step, steps, x, height, vx, step flags, box, kind, hit-stop, hit kind, routine] ...]}]} (projectiles.run_try's
row layout; x / height from P1's place at the KO, forward +)."""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
K96 = os.path.join(HERE, '..', '..', 'kof96', 'capture')
sys.path.insert(0, K96); sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
import analyze as A, specials96, emu, projectiles as PJ
from timeline import seqs

GAME = os.environ.get('GAME', 'kof98')
START, GAP = 40, 540
FROM = 200                                               # dumps from START + FROM (the pose starts ~290 after START)
SNAP_EVERY = 3

def run_button(cid, b, outdir):
    specials96.prep(GAME, cid)
    work = f'/data/tmp/winfx/work/{GAME}_{cid}_{b}'; os.makedirs(work, exist_ok=True)
    out = os.path.join(work, 'cap.txt')
    for f in glob.glob(out + '*'): os.remove(f)
    spec = [f'p1 {START} 3 c', f'p1 {START + 12} {GAP - 30} {b}']
    s1, s2 = seqs('; '.join(spec), START + GAP)
    pokes = [f'{START - 2}:108118=01,108119=80,108318=01,108319=B0,{emu.life_pokes(GAME, 0x108300, 1)}']
    frames = range(START + FROM, START + GAP)
    dumps = ';'.join(f'{f}:{PJ.POOL:X}:{PJ.NOBJ * 0x200:X}' for f in frames)
    snapdir = os.path.join(outdir, f'{GAME}_{cid}_{b}'); os.makedirs(snapdir, exist_ok=True)
    emu.run(GAME, out, s1, s2, pokes, start=f'c{cid}', extra={'RAMDUMP': dumps},
            snaps=list(range(START + FROM, START + GAP, SNAP_EVERY)), snapdir=snapdir)
    r1, r2 = A.load(out, 1), A.load(out, 2)
    life = lambda i: r2[i][3][0x138 // 2] - (0x10000 if r2[i][3][0x138 // 2] & 0x8000 else 0)
    ko = next(i for i in range(START, len(r2)) if life(i) <= 0)
    w0 = r1[ko][3]; x0 = A.x_of(w0); f0 = 1 if A.facing_of(w0) else -1
    dump = lambda f: bytes.fromhex(open(f'{out}.ram{f}_{PJ.POOL:X}').read().strip())
    pre = {o['base']: o['own'] for o in (PJ.obj(dump(frames[0]), PJ.POOL + k * 0x200) for k in range(PJ.NOBJ)) if o['alive']}
    mine, born, objs, p1 = {PJ.P1}, {}, [], []
    for f in frames:
        if f >= len(r1): break
        w = r1[f][3]
        p1.append([f - ko, A.state_of(w), w[0x74 // 2] // 6, round((A.x_of(w) - x0) * f0, 2), round(A.y_of(w), 2), PJ.s16(w[0x1C // 2])])
        db = dump(f)
        for o in (PJ.obj(db, PJ.POOL + k * 0x200) for k in range(PJ.NOBJ)):
            k = o['base']
            if not o['alive']:
                born.pop(k, None); pre.pop(k, None); continue
            if k in pre and pre[k] == o['own']: continue      # alive before the pose (a slot reused by another owner: new)
            pre.pop(k, None)
            if k not in born:
                if o['own'] not in mine: continue
                born[k] = len(objs); objs.append({'base': k, 'owner': o['own'], 'born': f - ko, 'p1': p1[-1][1:3], 'frames': []}); mine.add(k)
            objs[born[k]]['frames'].append([f - ko, o['id'], o['st'], o['raw'], o['steps'], round((o['x'] / 65536 - x0) * f0, 3),
                                            round(o['y'] / 65536, 3), round(o['vx'] / 65536 * f0, 4), o['fl'], o['box'], o['kind'],
                                            o['hs'], o['hk'], o['rt'], o['face'], PJ.s16(int.from_bytes(db[k - PJ.POOL + 0x2C:k - PJ.POOL + 0x2E], 'big')),
                                            PJ.s16(int.from_bytes(db[k - PJ.POOL + 0x1C:k - PJ.POOL + 0x1E], 'big'))])
        for k in [k for k in mine if k != PJ.P1 and k not in born]: mine.discard(k)
    for f in glob.glob(out + '.ram*'): os.remove(f)
    return {'ko': ko, 'snap0': START + FROM, 'p1': p1, 'objects': objs}

def compact(res):
    """the effect objects of each button's pose for the export (export96 win_objects): the ones born while P1 plays a
    pose state (not 0: the round's next things), each {'state', 'raw' (P1's step as it was born), 'delay' (frames since P1
    entered that step), 'back' (+$2C < 0: drawn behind him), 'rows': [[table, state, raw step, x, height] a frame] (x / height
    from P1's place that frame, x forward; the height = +$20 + P1's +$1C - its +$1C: KOF's
    placement puts an effect record's y in +$1C, $36C12; the object's facing = P1's in every capture: 'turned' rows would be flagged)}"""
    out = {}
    for b, r in res.items():
        at = {row[0]: row for row in r['p1']}; objs = []
        for o in r['objects']:
            p = at[o['born']]
            if not p[1]: continue
            d = 0
            while at.get(o['born'] - d - 1, [None, None, None])[1:3] == p[1:3]: d += 1
            rows = []
            for fr in o['frames']:
                q = at[fr[0]]
                if not q[1]: break                                # P1's pose is over (KOF then sets up the next
                                                                  # round: P1 moved, his places mean nothing)
                rows.append([fr[1], fr[2], fr[3], round(fr[5] - q[3], 2), round(fr[6] + q[5] - fr[16] - q[4], 2)])
            objs.append({'state': p[1], 'raw': p[2], 'delay': d, 'back': int(o['frames'][0][15] < 0), 'rows': rows})
        out[b.upper()] = objs
    return out

FXJSON = os.path.join(HERE, 'wins' if GAME == 'kof98' else f'wins_{GAME}', 'winfx.json')
if __name__ == '__main__':
    outdir = sys.argv[1]; os.makedirs(outdir, exist_ok=True)
    allfx = json.load(open(FXJSON)) if os.path.exists(FXJSON) else {}
    if sys.argv[2:3] == ['--compact']:                    # winfx.json again from the captures already in OUTDIR
        for cid in map(int, sys.argv[3:]):
            allfx[str(cid)] = compact(json.load(open(os.path.join(outdir, f'{GAME}_{cid}.json'))))
        json.dump(allfx, open(FXJSON, 'w'), separators=(',', ':')); sys.exit()
    for cid in map(int, sys.argv[2:]):
        res = {b: run_button(cid, b, outdir) for b in ('abc' if GAME == 'kof99' else 'abcd')}
        json.dump(res, open(os.path.join(outdir, f'{GAME}_{cid}.json'), 'w'))
        allfx[str(cid)] = compact(res)
        json.dump(allfx, open(FXJSON, 'w'), separators=(',', ':'))
        print(GAME, cid, {b: [(o['born'], o['p1'], hex(o['frames'][0][1]), o['frames'][0][2], len(o['frames'])) for o in r['objects']]
                          for b, r in res.items()}, flush=True)
