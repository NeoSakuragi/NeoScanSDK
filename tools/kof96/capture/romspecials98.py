#!/usr/bin/env python3
"""KOF98 specials traced in our emulator for the ROM-derived specials study (tools/kof96/handlers98.md): one try per
run from the fighter's state c<id> (c<id>x for EX), P2 far (whiff) or next to P1 (hit), every frame P1's object (+$00
the coroutine resume address = which part of the state handler runs, state +$72, animation step +$74 / 6, frame
record +$28, x +$18, height +$20, vx +$50, vy +$58, +$E1 flags, +$1B8 hit kind), P2's state / life / x / height, and
P1-owned pool objects (projectiles). Optional WLOG addresses (P1's object fields) give the writing PCs.

    python3 capture/romspecials98.py CID INPUT [close|far] [ex]     (INPUT as specials96 notation: 214C, 623C, [4]6C)
    import romspecials98 as R; rows = R.trace(cid, '214C', 'close')"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)
import rom96, emu, specials96 as C
OUT = '/data/tmp/romspecials/traces'
START = 40                                       # the try's first input frame (the state is reloaded at START - 4)
PLACE = {'whiff': ('00', 'E0', '02', 'E0'), 'far': ('01', '00', '02', '60'), 'close': ('01', '80', '01', 'B0'), 'mid': ('01', '80', '01', 'F0')}

def try_for(m, cid, inp, ex=False):
    """the specials96 try (events) whose notation (specials96.notation of its events, ground) is inp"""
    import importlib.util
    spec = importlib.util.spec_from_file_location('specials96_top', os.path.join(HERE, '..', 'specials96.py'))
    S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)      # the notation (capture/ has its namesake)
    for tr in C.tries(m, cid, 1 if ex else 0):
        if tr['air']: continue
        if S.notation(tr['events']) == inp.replace('EX ', ''): return tr
    raise KeyError(inp)

def w16(o, a): return struct.unpack('>H', o[a:a + 2])[0]
def s16(o, a): return struct.unpack('>h', o[a:a + 2])[0]
def s32(o, a): return struct.unpack('>i', o[a:a + 4])[0]
def u32(o, a): return struct.unpack('>I', o[a:a + 4])[0]

def trace(cid, inp, dist='far', ex=False, frames=200, wlog=(), p2_seq='', game='kof98', snaps=(), snapdir=None):
    m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
    tr = try_for(m, cid, inp, ex)
    os.makedirs(OUT, exist_ok=True)
    tag = f'{cid}{"x" if ex else ""}_{inp.replace("[", "c").replace("]", "")}_{dist}'
    out = os.path.join(OUT, tag + '.txt')
    spec = [f'p1 {START + off} {n} {keys}' for off, n, keys in tr['events'] if keys]
    if p2_seq: spec.append(p2_seq)
    s1, s2 = C.seqs('; '.join(spec), START + frames)
    x1h, x1l, x2h, x2l = PLACE[dist]
    pokes = [f'{START - 2}:108118={x1h},108119={x1l},108318={x2h},108319={x2l}']
    extra = {'WLOG': ','.join(f'{a:X}' for a in wlog)} if wlog else {}
    C.emu.run(game, out, s1, s2, pokes, reload=f'c{cid}{"x" if ex else ""}', reload_frames=[START - 4], extra=extra,
              snaps=snaps, snapdir=snapdir)
    rows = []
    rec0 = rom96.frame_record(m, cid, 0)
    for line in open(out):
        p = line.split()
        f = int(p[0])
        if f < START: continue
        o = bytes.fromhex(p[3]); q = bytes.fromhex(p[4])
        objs = []
        for ob in (p[5].split(';') if len(p) > 5 and p[5] != '-' else []):
            base, tab, st, steps, rec, x, h, fc = ob.split(':')
            objs.append({'base': base, 'table': int(tab), 'state': int(st), 'rec': int(rec, 16), 'x': int(x), 'h': int(h)})
        rows.append({'f': f - START, 'pc': u32(o, 0), 'state': w16(o, 0x72), 'step': w16(o, 0x74) // 6,
                     'frame': (u32(o, 0x28) - rec0) // 6 if 0x200000 <= u32(o, 0x28) < 0x300000 else -1,
                     'x': w16(o, 0x18) + o[0x1A] / 256, 'h': s16(o, 0x20) + o[0x22] / 256, 'vx': s32(o, 0x50) / 65536,
                     'vy': s32(o, 0x58) / 65536, 'e1': o[0xE1], 'e2': o[0xE2], 'kind': o[0x1B8], 'hs': o[0x124],
                     'p2state': w16(q, 0x72), 'p2life': w16(q, 0x138), 'p2x': w16(q, 0x18), 'p2h': s16(q, 0x20),
                     'facing': o[0x31] & 1, 'tick': w16(o, 0x1D2), 'objs': objs, 'raw': o})
    wl = []
    if wlog and os.path.exists(out + '.wlog'):
        wl = [l.split() for l in open(out + '.wlog')]
    return rows, wl, out

HITSTOP_PCS = range(0x1B2C4, 0x1B400)            # the hit-stop routine the engine swaps in (+$00) while the attacker freezes
HITSTOP = {'kof98': HITSTOP_PCS, 'kof96': range(0x14B9E, 0x14CC0), 'kof99': range(0x164E0, 0x16600)}

def special(st): return 128 <= st < 256 or st >= 480

def compare(cid, inp, dist='whiff', ex=False, frames=200, quiet=False, game='kof98'):
    """the game (trace) against the decoded program's model (handlers98.run_model), frame by frame from the first
    special state: P1 state, ROM frame, x from the start, height; objects: first frame, state, frame, x, height.
    Game frames inside the engine's hit-stop (+$00 in $1B2C4..) are dropped (the brawler applies its own); the
    model learns 'hit' on the frame the game's P2 life drops."""
    import handlers98 as H
    m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
    rows, _, _ = trace(cid, inp, dist, ex, frames, game=game)
    try: h, b = H.handler_of(cid, inp, ex, game); prog = H.decode(m, h, b, ex)
    except KeyError: h = prog = None             # a captured special (no ROM handler): the game's rows only
    k0 = next(i for i, r in enumerate(rows) if special(r['state']))
    hs = HITSTOP[game]
    froze = [i > k0 and r['pc'] in hs and rows[i - 1]['pc'] in hs for i, r in enumerate(rows)]
    lost = [i > 0 and r['tick'] == rows[i - 1]['tick'] for i, r in enumerate(rows)]   # the game lost the frame (slowdown:
    game = [r for i, r in enumerate(rows) if i >= k0 and not froze[i] and not lost[i]]   # P1 +$1D2 did not advance)
    frozen = sum(froze[k0:]); slow = sum(lost[k0:])
    hits = [i for i in range(1, len(game)) if game[i]['p2life'] < game[i - 1]['p2life']]
    model, objs = H.run_model(m, cid, prog, frames, hit_at=hits[0] if hits else None) if prog else ([(0, game[0]['state'], game[0]['frame'], 0.0, 0.0)], [])
    x0 = game[0]['x'] - model[0][3]               # aligned on the first frame
    end = next((i for i, r in enumerate(game) if not special(r['state'])), len(game))
    n = min(end, len(model)); bad = []; nb = {'frame': 0, 'x': 0, 'h': 0}
    for i in range(n):
        g, mo = game[i], model[i]
        gx, gh = round(g['x'] - x0, 2), round(g['h'], 2)
        d = {'frame': (g['state'], g['frame']) != (mo[1], mo[2]), 'x': abs(gx - mo[3]) > 1.01, 'h': abs(gh - mo[4]) > 0.51}
        for k in d: nb[k] += d[k]
        if any(d.values()): bad.append((i, (g['state'], g['frame'], gx, gh), mo[1:5]))
    res = {'input': inp, 'dist': dist, 'ex': ex, 'handler': f'${h:X}' if h else None, 'frames_game': end, 'frames_model': len(model),
           'mismatch': len(bad), 'by': nb, 'first_bad': bad[:4], 'hits_game': len(hits), 'hit_frames': hits, 'frozen_dropped': frozen, 'slowdown_dropped': slow,
           'states': sorted({r['state'] for r in game[:end]})}
    before = {o['base'] for o in rows[k0 - 1]['objs']}
    born = {}
    rec0 = rom96.frame_record(m, cid, 0)
    for i, g in enumerate(game[:end + 60]):
        for o in g['objs']:
            if o['base'] in before: continue
            if o['table'] != cid: continue
            born.setdefault(o['base'], []).append((i, o['state'], (o['rec'] - rec0) // 6, round(o['x'] - x0), o['h']))
    res['objects_game'] = [v[:2] for v in born.values()]
    res['objects_model'] = [c.rows[:2] for c in objs if c.rows]
    if not quiet: print(json.dumps(res, default=str))
    return res, game, model, objs, prog

if __name__ == '__main__':
    if sys.argv[1] == 'compare':
        compare(int(sys.argv[2]), sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else 'whiff', 'ex' in sys.argv[5:]); sys.exit()
    cid, inp = int(sys.argv[1]), sys.argv[2]
    dist = sys.argv[3] if len(sys.argv) > 3 else 'far'; ex = 'ex' in sys.argv[4:]
    rows, wl, out = trace(cid, inp, dist, ex)
    prev = None
    for r in rows:
        k = (r['pc'], r['state'])
        print(f"{r['f']:4d} pc={r['pc']:06X} st={r['state']:3d} step={r['step']:2d} fr={r['frame']:4d} x={r['x']:7.2f} h={r['h']:6.2f} "
              f"vx={r['vx']:6.2f} vy={r['vy']:6.2f} e1={r['e1']:02X} hs={r['hs']:02X} p2={r['p2state']:3d} life={r['p2life']:3d} "
              f"p2x={r['p2x']} objs={len(r['objs'])}" + ('' if k != prev else ' .'))
        prev = k
