#!/usr/bin/env python3
"""Projectiles of KOF96 / KOF98 / KOF99 specials, captured in our emulator (emu.py, neogeo_sdl --capture) with the
object pool dumped every frame (RAMDUMP), so a projectile is followed by what it is, not by its pool slot.

Pool (KOF98 code, tools/kof98/README.md "Projectiles"): objects at $100100 + n*$200; alloc $3434 links an object into
the run list, free $34A8 unlinks it and writes $FFFF to +$06 (the memory is not cleared: a freed projectile keeps its
last fields, which is why the old captures saw "finished" objects linger). An object is alive while +$06 != $FFFF.
A P1 object = owner (+$84) is P1 ($108100) or another P1 object born in the try (sub-objects).

    python3 capture/projectiles.py [--game kof98] [--ex] [--inputs 236A,236C] [--dist free,60,120,200] ID ...
        -> /data/neogeo_dict/captures/kof96/projectiles<game>/<id>[x].json: per ground special try (capture/specials96
           tries: the same inputs) P1's rows and every P1 object born during the try, per frame while alive

Each try: the fighter's state c<id> (c<id>x = EX), the input at frame START, P2 standing where the state has it (far,
~256 px) or, with --dist, P2 placed d px in front of P1 at frame START - 2 (one file per distance: <id>[x]_d<d>.json),
or 'free': P2 held 200 px up every frame, so a projectile flies until its own end (anim end, off screen).
Rows also carry the camera x ($10B084, forward from P1's x at the press: KOF98's off-screen test $180B6 reads it).
Per frame of an object: [frame from the press, alive, table +$70, state +$72, raw step +$74/6, steps +$80, x +$18
(16.16, forward from P1's x at the press), height +$20, vx +$50, step flags +$7C/+$7D, live box +$90 (type x y w h),
kind +$F5, hit-stop +$124, hit kind +$1B8, routine +$00]. P1 / P2 rows: [state, raw step, x forward, height,
life +$138, hit-stop +$124, frame record]."""
import json, os, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'kof95', 'capture'))
from timeline import seqs
import rom96, emu
import importlib.util as _iu                              # capture/specials96 (tries, motion, prep: the specials
_sp = _iu.spec_from_file_location('cap_specials96', os.path.join(HERE, 'specials96.py'))   # capture's own inputs);
cap = _iu.module_from_spec(_sp); _sp.loader.exec_module(cap)                         # ../specials96 = analysis

POOL, NOBJ = 0x100100, 48                                 # dumped: $100100-$106100 (48 objects)
START, FRAMES = 40, 300                                   # press at START; a 2.5 px/frame projectile crosses 750 px
P1, P2 = 0x108100, 0x108300
CAMERA = {'kof96': 0x10B07E, 'kof98': 0x10B084, 'kof99': 0x10B038}   # camera x: the off-screen test (KOF96 $129B0, KOF98
                                                          # $180B6, KOF99 $1328C, one routine) reads it at a5 ($108000) + $307E / $3084 / $3038
TMP = '/data/tmp/projectiles96'
OUT = '/data/neogeo_dict/captures/kof96'

def s32(v): return v - (1 << 32) if v >= 1 << 31 else v
def s16(v): return v - 65536 if v >= 32768 else v

def obj(b, base):
    o = base - POOL
    w = lambda a: int.from_bytes(b[o + a:o + a + 2], 'big')
    l = lambda a: int.from_bytes(b[o + a:o + a + 4], 'big')
    return {'base': base, 'alive': w(6) != 0xFFFF and l(0) != 0, 'rt': l(0), 'id': w(0x70), 'st': w(0x72), 'raw': w(0x74) // 6,
            'steps': w(0x80), 'x': s32(l(0x18)), 'y': s32(l(0x20)), 'vx': s32(l(0x50)), 'fl': w(0x7C), 'own': l(0x84) & 0xFFFFFF,
            'box': [b[o + 0x90 + k] for k in range(5)], 'kind': b[o + 0xF5], 'hs': b[o + 0x124], 'hk': b[o + 0x1B8],
            'face': b[o + 0x31] & 1}

def fighter_row(w, x0, f0):
    """[state, raw step, x forward from x0, height, life, hit-stop, frame record] of a fighter object (capture words)"""
    x = (w[0x18 // 2] << 16 | w[0x1A // 2]); x = s32(x) / 65536
    y = s32(w[0x20 // 2] << 16 | w[0x22 // 2]) / 65536
    return [w[0x72 // 2], w[0x74 // 2] // 6, round((x - x0) * f0, 2), round(y, 2), w[0x138 // 2], w[0x124 // 2] >> 8,
            (w[0x28 // 2] << 16 | w[0x2A // 2]) & 0xFFFFFF]

def run_try(game, state, events, dist=None, n=FRAMES, tag='t', p2='', roots=(P1,)):
    """one try from the state: P1 objects born after the press, followed every frame; p2: P2's inputs ('p2 frame n
    keys; ...', timeline.seqs form: a clash test throws P2's projectile too); roots: whose objects (P1, P2: both)"""
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, f'{game}_{state}_{tag}.txt')
    for f in glob.glob(out + '*'): os.remove(f)
    spec = '; '.join([f'p1 {START + o} {k} {keys}' for o, k, keys in events if keys] + ([p2] if p2 else []))
    s1, s2 = seqs(spec, START + n)
    pokes = []
    first = START - 2
    dumps = ';'.join(f'{f}:{POOL:X}:{NOBJ * 0x200:X};{f}:{CAMERA[game]:X}:4' for f in range(first, START + n))
    extra = {'RAMDUMP': dumps}
    if dist == 'free':                                    # free flight: P2 held 200 px up every frame (nothing on
        pokes = [f'{f}:{P2 + 0x20:X}=00,{P2 + 0x21:X}=C8' for f in range(first, START + n)]   # the ground to hit)
    elif dist is not None:                                # P2 d px in front of P1 (P1's x read from the state: one run)
        emu.run(game, out, *seqs('', START), [], start=state)
        import analyze as A
        x1 = A.x_of(A.load(out, 1)[START - 3][3]); x2 = int(x1) + dist
        pokes = [f'{START - 2}:{P2 + 0x18:X}={x2 >> 8:02X},{P2 + 0x19:X}={x2 & 255:02X}']
        for f in glob.glob(out + '*'): os.remove(f)
    emu.run(game, out, s1, s2, pokes, start=state, extra=extra)
    import analyze as A
    r1, r2 = A.load(out, 1), A.load(out, 2)
    dump = lambda f: bytes.fromhex(open(f'{out}.ram{f}_{POOL:X}').read().strip())
    w0 = r1[START][3]; x0 = A.x_of(w0); f0 = 1 if A.facing_of(w0) else -1
    pre = {o['base'] for o in (obj(dump(first), POOL + k * 0x200) for k in range(NOBJ)) if o['alive']}
    mine, rows, objs = set(roots), [], {}
    born = {}
    for f in range(START, START + n):
        if f >= len(r1): break
        b = dump(f)
        cam = int(open(f'{out}.ram{f}_{CAMERA[game]:X}').read().strip()[:4], 16)
        rows.append([fighter_row(r1[f][3], x0, f0), fighter_row(r2[f][3], x0, f0), round((cam - x0) * f0, 2)])
        cur = [obj(b, POOL + k * 0x200) for k in range(NOBJ)]
        for o in cur:
            k = o['base']
            if not o['alive']:
                if k in born: born.pop(k)                 # freed: the next object here is another one
                continue
            if k in pre: continue                         # alive before the press: not this move's
            if k not in born:
                if o['own'] not in mine: continue
                born[k] = len(objs); objs[born[k]] = {'base': k, 'owner': o['own'], 'born': f - START, 'frames': []}
                mine.add(k)
            ob = objs[born[k]]
            ob['frames'].append([f - START, o['id'], o['st'], o['raw'], o['steps'], round((o['x'] / 65536 - x0) * f0, 3),
                                 round(o['y'] / 65536, 3), round(o['vx'] / 65536 * f0, 4), o['fl'], o['box'], o['kind'],
                                 o['hs'], o['hk'], o['rt']])
        for k in [k for k in mine if k not in roots and k not in born]: mine.discard(k)
    for f in glob.glob(out + '*'): os.remove(f)
    return {'rows': rows, 'objects': list(objs.values())}

def capture(game, cid, ex=False, dists=(None,), inputs=None):
    prom, _ = rom96.load(rom96.GAMES[game]['neo']); m = rom96.Mem(prom, game)
    state = f'c{cid}{"x" if ex else ""}'
    if not emu.state_exists(game, state): cap.prep(game, cid, ex)
    import specials96 as an
    T = [t for t in cap.tries(m, cid, ex=1 if ex else 0) if not t['air']]
    if inputs: T = [t for t in T if ('EX ' if ex else '') + an.notation(t['events']) in inputs]
    d = os.path.join(OUT, f'projectiles_{game}'); os.makedirs(d, exist_ok=True)
    for dist in dists:
        res = []
        for k, t in enumerate(T):
            r = run_try(game, state, t['events'], dist, tag=f'{k}')
            res.append({'cmd': t['cmd'], 'button': t['button'], 'input': ('EX ' if ex else '') + an.notation(t['events']),
                        'events': t['events'], 'dist': dist, **r})
            print(cid, state, dist, res[-1]['input'], len(r['objects']), 'objects', flush=True)
        name = f'{cid}{"x" if ex else ""}' + (f'_d{dist}' if dist is not None else '')
        json.dump(res, open(os.path.join(d, name + '.json'), 'w'))

if __name__ == '__main__':
    args = sys.argv[1:]; game = 'kof98'; ex = False; dists = (None,); inputs = None
    while args and args[0].startswith('--'):
        if args[0] == '--game': game = args[1]; args = args[2:]
        elif args[0] == '--ex': ex = True; args = args[1:]
        elif args[0] == '--inputs': inputs = args[1].split(','); args = args[2:]
        elif args[0] == '--dist': dists = [v if v == 'free' else int(v) for v in args[1].split(',')]; args = args[2:]
    for cid in map(int, args): capture(game, cid, ex, dists, inputs)
