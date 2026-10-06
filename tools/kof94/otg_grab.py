#!/usr/bin/env python3
"""KOF94 "OTG command grab" study (/data/neogeo_dict/kof94/otg_grab.md).

A grappler's command grab catches a victim lying on the ground, again and again, when the first grab caught the
victim right after a light attack's hit-stun. The victim's bit +$E7 bit 3 ("hit-stun over": set by the hit reaction at
$8186 when the stun timer +$D0 runs out, cleared at $80C6 / $81BC when the reaction animation ends, and by the stand
routine at $925E) survives the grab: the thrower replaces the victim's routine (+$00) so neither the reaction's end nor
the stand routine runs, and nothing on the throw / knockdown / lying path clears it. Every command grab's catch test
(Heidern's Storm Bringer $DD40; byte-identical in Ralf $F516, Clark $10704 / $10F46, Goro $188A0 / $1955E / $19EB2,
Takuma $29142, Yuri $2ACF0):
    victim +$E1 bit 0 clear (on the ground)
    and (+$E7 bit 3 set  OR  +$E3 bit 5 clear)     <- +$E3 bit 5 = in a reaction (hit / thrown / down / wake-up)
    and +$AA == 0 (not held) and +$7B bit 3 clear (not get-up invulnerable) and distance
so a lying victim with the stale +$E7 bit 3 passes, and every OTG grab keeps it set. The same test sits in Ralf's,
Clark's, Goro's, Takuma's and Yuri's command grabs (not reproduced here).

Our emulator only (emu/neogeo_sdl --capture). States in /data/neogeo_dict/ngsdl_sta/kof94/: g<id>.state (P1 =
fighter id, made from the game's vs state by a round loss), g<id>c.state (P1 walked the opponent into the right
corner). Opponent Ryo.

    python3 otg_grab.py state GAME ID          -> g<ID>.state, g<ID>c.state
    python3 otg_grab.py trace GAME ID KIND     -> one grab (KIND raw | cancel = close A then the grab), per-frame
                                                  victim fields until it stands
    python3 otg_grab.py chain GAME ID KIND N   -> N grabs: after each, walk + the grab again on the downed victim,
                                                  earliest timing that catches; table per grab
Results 2026-10-06 (Heidern vs Ryo, corner): raw grab -> the next catch is only possible after the victim stood up
(frame 231); close A cancelled into Storm Bringer -> 10 Storm Bringers in a row on the lying victim, one every 154
frames (`chain kof94 0 cancel 10`).
KOF95 (game kof95, Heidern vs Joe): the same stale +$E7 bit 3, but the knockdown / lying animation steps set the
get-up-invulnerable bit +$7D bit 3 (step byte 5 = 08/09 vs KOF94's 00/01), so the catch test's +$7D clause rejects
the lying victim: next catch only after the wake-up protection (`chain kof95 0 cancel 3`: 29, 249, 469)."""
import os, subprocess, sys
import multiprocessing
from multiprocessing import Pool
multiprocessing.set_start_method('fork', force=True)
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
TMP = '/data/tmp/otg'
GAMES = {
    'kof94': {'neo': '/data/roms/kof94.neo', 'sta': '/data/neogeo_dict/ngsdl_sta/kof94', 'base': 'vs', 'getup': 0x7B,
              'team': (0x108232, 6), 'width': 0x6C0F0},
    'kof95': {'neo': '/data/roms/kof95.neo', 'sta': '/data/neogeo_dict/ngsdl_sta/kof95', 'base': 'vs_kyo', 'getup': 0x7D,
              'team': (0x10A843, 3), 'width': 0x79FC0},
}
LIFE_POKE = '108420=00,108421=CF'            # P2 life refilled (every 30 frames) so the loop is not ended by a KO

W = lambda o, off, n=2: int(o[off * 2:off * 2 + n * 2], 16)
S = lambda v, bits: v - (1 << bits) if v >> (bits - 1) else v

def capture(game, seq1, seq2, load, pokes='', save=None):
    out = f'{TMP}/run{os.getpid()}.txt'
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2, OUT=out, INPUT_LAG='1', LOAD=load)
    if pokes: env['POKE'] = pokes
    if save: env['SAVE'] = save
    subprocess.run([NGSDL, GAMES[game]['neo'], '--capture'], env=env, timeout=600, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    return out

def seq(parts): return ','.join(f'{n}:{i}' for i, n in parts if n > 0)

def runs(lane):
    parts = []
    for x in lane:
        if parts and parts[-1][0] == x: parts[-1] = (x, parts[-1][1] + 1)
        else: parts.append((x, 1))
    return parts

def make_state(game, cid):
    """P1's team record (object +$132..) = cid, P1 life 1, P2 walks in and punches: the next round loads cid. Saved at
    frame 820 (fight live), then P1 walks the opponent into the right corner (g<id>c)."""
    g = GAMES[game]; os.makedirs(TMP, exist_ok=True); sta = g['sta']
    a, n = g['team']
    p = '1:' + ','.join(f'{a + k:X}={cid:02X}' for k in range(n)) + ',108220=00,108221=01'
    p2 = [('L', 40)] + [('c', 4), ('-', 6)] * 8 + [('-', 1000)]
    capture(game, seq([('-', 830)]), seq(p2), f'{sta}/{g["base"]}.state', p, f'820:{sta}/g{cid}.state')
    capture(game, seq([('R', 300), ('-', 30)]), seq([('-', 330)]), f'{sta}/g{cid}.state', save=f'328:{sta}/g{cid}c.state')

def trace(game, out):
    g, rows = GAMES[game], []
    for line in open(out):
        q = line.split(); a, b = q[3], q[4]
        r = dict(f=int(q[0]), inp=q[1], st=W(a, 0x72), x=W(a, 0x18), cid=W(a, 0x182) // 4, vid=W(b, 0x182) // 4,
                 st2=W(b, 0x72), x2=W(b, 0x18), h2=S(W(b, 0x20), 16), life2=W(b, 0x120), rt2=W(b, 0, 4),
                 air=W(b, 0xE1, 1) & 1, react=(W(b, 0xE3, 1) >> 5) & 1, late=(W(b, 0xE7, 1) >> 3) & 1,
                 aa=W(b, 0xAA, 4), inv=(W(b, g['getup'], 1) >> 3) & 1, stun=S(W(b, 0xD0), 16))
        r['held'] = r['aa'] == 0xFFFFFFFF
        r['ok'] = not r['air'] and (r['late'] or not r['react']) and r['aa'] == 0 and not r['inv']   # catch test minus distance
        rows.append(r)
    return rows

# command grabs, P1 facing right (stick steps 2 frames, button 3)
HCB = [('R', 2), ('DR', 2), ('D', 2), ('DL', 2), ('L', 2)]
HCF = [('L', 2), ('DL', 2), ('D', 2), ('DR', 2), ('R', 2)]
GRABS = {'kof94': {0: ('Heidern', 'Storm Bringer 63214C', HCB + [('Lc', 3)])},
         'kof95': {0: ('Heidern', 'Storm Bringer 63214C', HCB + [('Lc', 3)])}}   # other grapplers: not studied

def lane_run(game, cid, lane, refill=True, extra=''):
    pk = [f'{f}:{LIFE_POKE}' for f in range(1, len(lane), 30)] if refill else []
    if extra: pk += [f'{f}:{extra}' for f in range(1, len(lane), 10)]
    out = capture(game, seq(runs(lane)), seq([('-', len(lane))]), f'{GAMES[game]["sta"]}/g{cid % 100}c.state', ';'.join(pk))
    rows = trace(game, out)
    return rows, [r['f'] for i, r in enumerate(rows) if r['held'] and (i == 0 or not rows[i - 1]['held'])]

def put(lane, f, parts):
    for i, k in parts:
        for _ in range(k):
            if f < len(lane): lane[f] = i
            f += 1

def first_grab(kind, motion, n=400):
    lane = ['-'] * n
    put(lane, 5, ([('a', 2), ('-', 2)] if kind == 'cancel' else []) + motion)
    return lane

def window(rows, after):
    """the victim after the grab released it (frame > after): [(first, last)] runs of frames passing the catch test
    (distance aside), the release frame, the frame it stands again (state 0, +$E3 bit 5 clear)"""
    rel = next((r['f'] for r in rows if r['f'] > after and not r['held'] and r['aa'] == 0), None)
    runs_, cur = [], None
    for r in rows:
        if rel is None or r['f'] < rel: continue
        if r['ok'] and r['react']:
            cur = [r['f'], r['f']] if cur is None else [cur[0], r['f']]
        elif cur: runs_.append(tuple(cur)); cur = None
        if r['st2'] == 0 and not r['react']: break
    if cur: runs_.append(tuple(cur))
    stand = next((r['f'] for r in rows if rel and r['f'] > rel and r['st2'] == 0 and not r['react']), None)
    return rel, runs_, stand

def _try(a):
    game, cid, head, idle, t, motion, extra = a
    mlen = sum(k for _, k in motion)
    L = list(head) + ['-'] * (t + 330 - idle)
    put(L, idle, [('R', t - mlen - idle)] + motion)
    rows, caught = lane_run(game, cid, L, extra=extra)
    return L, rows, caught

def chain(game, cid, kind, n=6, extra=''):
    """N grabs: the first raw / cancel, then each next one as early as it catches the downed victim: walk forward from
    the thrower's first idle frame, the motion, the button at frame t (t scanned). -> list of per-grab dicts"""
    motion = GRABS[game][cid][2]; mlen = sum(k for _, k in motion)
    lane = first_grab(kind, motion, 400)
    rows, caught = lane_run(game, cid, lane, extra=extra)
    if not caught: return [], rows
    out = []
    for k in range(n):
        c = caught[k]
        rel, wins, stand = window(rows, c)
        idle = next((r['f'] for r in rows if r['f'] > c + 5 and r['st'] == 0), None)
        out.append(dict(catch=c, release=rel, idle=idle, windows=wins, stand=stand, victim_state=[r['st2'] for r in rows if r['f'] == c - 1][0],
                        otg=[r['react'] for r in rows if r['f'] == c - 1][0]))
        if k == n - 1 or idle is None: break
        ts = list(range(idle + mlen, (stand or idle + 120) + 25))
        with Pool(12) as P:
            res = P.map(_try, [(game, cid, lane[:idle], idle, t, motion, extra) for t in ts])
        hit = next(((t, *r) for t, r in zip(ts, res) if len(r[2]) > k + 1), None)
        if not hit: out[-1]['next'] = None; break
        t, lane, rows, caught = hit
        out[-1]['next'] = t
    return out, rows

def show_chain(game, cid, kind, n):
    res, rows = chain(game, cid, kind, n)
    vs = {r['f']: r for r in rows}
    print(f"{game} {GRABS[game][cid][0]} {GRABS[game][cid][1]} [{kind}]: {len(res)} grabs")
    for k, g in enumerate(res):
        st = vs[g['catch']]
        print(f"  grab {k + 1}: caught frame {g['catch']} ({'OTG, ' if g['otg'] else 'standing, '}victim state before {g['victim_state']}, +$E3.5 {st['react']}, "
              f"+$E7.3 {st['late']}), released {g['release']}, thrower idle {g['idle']}, victim catchable {g['windows']},"
              f" stands {g['stand']}, next button {g.get('next')}")
    return res

def trace_one(game, cid, kind):
    motion = GRABS[game][cid][2]
    rows, caught = lane_run(game, cid, first_grab(kind, motion, 330))
    prev = None
    for r in rows:
        k = (r['st'], r['st2'], r['react'], r['late'], r['held'], r['air'], r['inv'], r['ok'])
        if k != prev:
            print(f"{r['f']:4} in={r['inp']:3} P1 st={r['st']:3} x={r['x']:4} | P2 st={r['st2']:3} x={r['x2']:4} h={r['h2']:3}"
                  f" E1.0={r['air']} E3.5={r['react']} E7.3={r['late']} +AA={r['aa']:08X} inv={r['inv']} stun={r['stun']:3}"
                  f" rt={r['rt2']:06X} catchable={int(r['ok'])}")
        prev = k
    print('caught at', caught)

if __name__ == '__main__':
    cmd, game = sys.argv[1], sys.argv[2]
    if cmd == 'state': make_state(game, int(sys.argv[3]))
    elif cmd == 'trace': trace_one(game, int(sys.argv[3]), sys.argv[4])
    elif cmd == 'chain': show_chain(game, int(sys.argv[3]), sys.argv[4], int(sys.argv[5]))
