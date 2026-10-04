#!/usr/bin/env python3
"""Projectiles of KOF96 / KOF98 / KOF99 specials, from the captures of capture/projectiles.py (our emulator, the
object pool dumped every frame). How the games do it: tools/kof98/README.md "Projectiles".

    definitions(m, game, cid) -> {input: projectile}         (normal + EX inputs, 'EX ...', of the fighter)
    python3 projectiles96.py [--game kof98] ID ...            -> the inventory table of the fighter's projectile moves

A projectile = an object born during the move (owner +$84 = the fighter, followed by identity, never by pool slot)
whose attack box slot is live at some frame (+$7C bit 0 with a box in +$90). Per projectile:
  state / table      its game state (+$72) on the table +$70 (always the fighter's own for this roster)
  spawn_row          frame of its birth, counted from the fighter's first special state (= the row of the special's
                     script, specials96: the scripts start there), spawn_x / spawn_y from the fighter's x at that row
  rows               per frame of its free flight (P2 held off the ground: capture --dist free): [table, state, raw step,
                     x from the spawn point (forward +, px), height, step flags +$7C, live attack box (type x y w h) or
                     None]; loop: the row the flight repeats from once the rows end (a looping flight: it dies off
                     screen), None when it dies at the end of its rows (its animation ended)
  death              'anim' (its animation ended: +$7C bit 15), 'offscreen' (x - camera <= -64 or >= 384: the games'
                     shared test KOF96 $129B0 / KOF98 $180B6 / KOF99 $1328C), 'alive' (still flying at the capture's end)
  kind               object +$F5: 1 = a travelling projectile (ends on its first hit), 3 = an eruption (plays on)
  hit_kind           +$1B8: the victim's hit sounds (tools/kof96/hitsfx.py)
  hits               per distance d (P2 standing d px ahead of the fighter): {frame, x, hits (drops of P2's life
                     while it lives), reaction (P2's states after), end_rows (after the hit: [table, state, raw, x from
                     the impact, height]), owner_frozen (the fighter's hit-stop counter at the impact)}"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rom96, specials96

DIR = '/data/neogeo_dict/captures/kof96'
DISTS = (60, 120, 200)

def _load(game, cid, tag):
    p = os.path.join(DIR, f'projectiles_{game}', f'{cid}{tag}.json')
    return {t['input']: t for t in json.load(open(p))} if os.path.exists(p) else {}

def _live(f): return bool(f[8] & 0x100 and f[9][0])

def _projectile(t):
    """the projectile of a try: the first-born object with a live attack box"""
    obs = [o for o in t['objects'] if any(_live(f) for f in o['frames'])]
    return min(obs, key=lambda o: o['born']) if obs else None

def _g0(game, t):
    return next((i for i, r in enumerate(t['rows']) if specials96.special_state(game, r[0][0])), None)

def _period(rows, start):
    """smallest P such that rows[start:] repeat with period P (state, raw step and per-frame motion), else None"""
    seq = [(r[1], r[2]) for r in rows[start:]]
    dx = [round(rows[k][3] - rows[k - 1][3], 3) for k in range(max(start, 1), len(rows))]
    for P in range(1, len(seq) // 2 + 1):
        if all(seq[k] == seq[k + P] for k in range(len(seq) - P)) and all(dx[k] == dx[k + P] for k in range(len(dx) - P)):
            return P
    return None

def definition(game, t, free, dist_tries, m=None):
    """the projectile of the move tried in `t` (far capture), flight from `free`, hits from `dist_tries` {d: try}"""
    m = m or rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
    parsed = {}
    def rom_active(f):                                     # the ROM step's active flag ($0100) of a captured frame
        tid, st, raw = f[1], f[2], f[3]
        if (tid, st) not in parsed:
            parsed[tid, st] = {s_[4]: s_[2] for s_ in rom96.parse_anim(m, rom96.anim_addr(m, tid, rom96.state_slot(m, tid, st)))[0]}
        return bool(parsed[tid, st].get(raw, 0) & 0x100)
    src = free or t
    ob = _projectile(src)
    if ob is None: return None
    g0 = _g0(game, src)
    if g0 is None: return None
    F = ob['frames']
    born = F[0][0]
    p1x = src['rows'][g0][0][2]
    x0, y0 = F[0][5], F[0][6]
    rows = [[f[1], f[2], f[3], round(f[5] - x0, 3), round(f[6], 2), f[8], f[9] if _live(f) else None] for f in F]
    last = F[-1]; cam = src['rows'][last[0]][2] if last[0] < len(src['rows']) else None
    if last[8] & 0x8000: death = 'anim'
    elif cam is not None and (last[5] - cam + abs(last[7]) >= 384 or last[5] - cam - abs(last[7]) <= -64): death = 'offscreen'
    else: death = 'alive'
    loop = None
    if death != 'anim':                                    # a looping flight: repeat its last period (the state the
        st = rows[-1][1]                                   # flight ends in, from where it entered it)
        s0 = next(k for k in range(len(rows) - 1, -1, -1) if rows[k][1] != st) + 1 if any(r[1] != st for r in rows) else 0
        P = None
        for a in range(s0, len(rows) - 2):
            P = _period(rows, a)
            if P: s0 = a; break
        loop = len(rows) - P if P else len(rows) - 1
        if P: rows = rows[:s0 + P] if s0 + P < len(rows) else rows; loop = s0
    d = {'table': F[0][1], 'state': F[0][2], 'kind': F[0][10], 'hit_kind': F[0][12], 'spawn_row': born - g0,
         'spawn_x': round(x0 - p1x, 2), 'spawn_y': y0, 'rows': rows, 'loop': loop, 'death': death,
         'life': len(F), 'travel': round(F[-1][5] - x0, 2), 'vx': F[-1][7], 'hits': {},
         'death_sx': round(last[5] - cam, 1) if cam is not None else None}   # screen x where it died (x - camera)
    flight = {(r[0], r[1]) for r in rows}
    for dist, dt in dist_tries.items():
        o = next((o for o in dt['objects'] if (o['frames'][0][1], o['frames'][0][2]) == (d['table'], d['state'])), None) \
            or _projectile(dt)                             # by identity (a hit on its first live frame clears the box
        if o is None: continue                             # bit at once: it may never be seen live)
        fr = {f[0]: f for f in o['frames']}
        life = [r[1][4] for r in dt['rows']]               # its hits: P2's life drops while its attack box was live,
        drops = [k for k in range(1, len(life)) if life[k] < life[k - 1] and   # or spent (a step the ROM makes active
                 any(j in fr and (_live(fr[j]) or (fr[j][9][0] and rom_active(fr[j]))) for j in (k - 1, k))]   # whose bit the hit cleared)
        if not drops: d['hits'][dist] = {'hits': 0}; continue
        k = drops[0]
        imp = fr.get(k) or fr.get(k - 1)
        after = [f for f in o['frames'] if f[0] >= k]
        end = [f for f in after if (f[1], f[2]) not in flight]
        p2 = [r[1][0] for r in dt['rows'][k:k + 40]]
        d['hits'][dist] = {'frame': k - (_g0(game, dt) or 0), 'x': round(imp[5] - o['frames'][0][5], 2), 'hits': len(drops),
                           'damage': life[k - 1] - life[k], 'reaction': sorted(set(p2)), 'victim_stop': dt['rows'][k][1][5],
                           'owner_frozen': dt['rows'][k][0][5] != 255,
                           'end_rows': [[f[1], f[2], f[3], round(f[5] - imp[5], 3), round(f[6], 2)] for f in end],
                           'after_hit_live': sum(1 for f in after if _live(f) and (f[1], f[2]) in flight)}
    return d

def definitions(game, cid):
    out = {}; m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
    for tag in ('', 'x'):
        far = _load(game, cid, tag); free = _load(game, cid, tag + '_dfree')
        dists = {dd: _load(game, cid, f'{tag}_d{dd}') for dd in DISTS}
        for inp, t in far.items():
            if inp not in free: continue
            d = definition(game, t, free[inp], {dd: dists[dd][inp] for dd in DISTS if inp in dists[dd]}, m)
            if d: out[inp] = d
    return out

if __name__ == '__main__':
    args = sys.argv[1:]; game = 'kof98'
    if args[:1] == ['--game']: game = args[1]; args = args[2:]
    for cid in map(int, args):
        for inp, d in definitions(game, cid).items():
            h = d['hits']
            print(f"{cid} {inp:10} st {d['state']} kind {d['kind']} spawn row {d['spawn_row']} x {d['spawn_x']} y {d['spawn_y']} "
                  f"vx {d['vx']} life {d['life']} travel {d['travel']} death {d['death']} loop {d['loop']}/{len(d['rows'])} hk {d['hit_kind']} | " +
                  ' '.join(f"d{k}: {v.get('hits')} hit" + (f" @{v['frame']} x{v['x']} dmg{v['damage']} r{v['reaction'][:3]} stop{v['victim_stop']} own{int(v['owner_frozen'])} end{len(v['end_rows'])} live{v['after_hit_live']}" if v.get('hits') else '') for k, v in h.items()))
