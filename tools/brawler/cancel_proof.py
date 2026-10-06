#!/usr/bin/env python3
"""TODO #143 proof: the cancel rules (fighter.c "cancels", docs/brawler_move_vocabulary.md "cancel"), per roster fighter,
in the Chain Lab's training mode (labdrive: P1 = the fighter, a dummy that never attacks), our emulator's core (harness).

    python3 cancel_proof.py OUT_DIR [FIGHTER ...]     -> OUT_DIR/cancel143.json

Per fighter:
  normal -> special   close A hits the dummy, C pressed in its hit-stop: P1 goes ATTACK -> SPECIAL with no neutral
                      frame between; whiff (far A, nobody near): the C during the normal starts nothing
  normal -> fury      the same with D: ATTACK -> SPECIAL spec_id = the fury (inv = fury's, super flash = P1);
                      whiff: nothing
  special -> fury     a ground special (slot by slot, distance by distance) whose first hit lands, D in that hit's
                      hit-stop: spec_id becomes the fury in the same SPECIAL state (flash, invincibility); the same
                      special with D before its first hit: it plays to its end, no fury
  air normal -> special  no special starts in the air (S_AIR reads A only): air A that hits + C = no special in the air"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
from labdrive import Lab

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json'))); M = G['meter']
names = [r['name'] for r in G['roster']]
only = sys.argv[2:] or names
L = Lab(); b = L.b; ST = b.states
BS_FURY = 6
SLOTS = ['', 'R', 'D', 'U', 'DR', 'UR']                 # C, forward / down / up / down-forward / up-forward + C
SFW = b.syms.get('sf_who')                              # main.c super flash: its attacker (0 none)

def st(i=0): return ST[b.fget(i, 'state')]
def run(n, k=''): b.run(n, p1=k)
def settle():
    for _ in range(900):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'shot') and not b.fget(0, 'flash') and not b.fget(0, 'chain_t'): break
        run(1)
    else: raise RuntimeError('P1 never idle')
    b.fset(0, 'meter', M['max']); b.fset(2, 'hp', 60)
def setpos(dist):
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100
    b.place(0, x=x0, z=30); b.place(2, x=x0 + dist, z=30); b.fset(0, 'facing', 1); run(2)
def flash_who():
    """the super flash for P1 within 12 frames (main.c sf_who: the fury's attacker, from its gflash.start frame)"""
    if not SFW: return None
    for _ in range(12):
        if b.r(SFW, 4): return 1
        run(1)
    return 0

def trace(n, stop=None):
    """n frames (no input): P1's (state, spec_id, inv) per frame"""
    out = []
    for _ in range(n):
        run(1); out.append((st(0), b.fget(0, 'spec_id'), b.fget(0, 'inv')))
        if stop and stop(out[-1]): break
    return out

def normal_cancel(key, whiff):
    """close A (or far A at whiff), key pressed during the normal -> what P1 does next"""
    settle(); setpos(300 if whiff else 26); h0 = len(b.hits)
    run(2, 'a')
    for _ in range(30):                                  # the normal's contact (or, whiffing, its first frames)
        if st(0) == 'ATTACK' and (whiff or b.fget(0, 'landed')): break
        run(1)
    else: return {'ok': False, 'note': 'no normal / no contact'}
    landed = b.fget(0, 'landed'); fz = b.fget(0, 'freeze'); s0 = st(0)
    run(2, key)                                          # the press (in the hit-stop when it hit)
    tr = trace(60, lambda t: t[0] != 'ATTACK')
    first = next((t for t in tr if t[0] != 'ATTACK'), tr[-1])
    fl = flash_who()
    tr2 = trace(30)
    r = {'landed': landed, 'press_in_hitstop': fz > 0, 'pressed_in': s0, 'next': first[0], 'spec_id': first[1],
         'inv': first[2], 'hits': len(b.hits) - h0}
    if whiff: r['ok'] = not landed and first[0] != 'SPECIAL' and all(t[0] != 'SPECIAL' for t in tr2)
    elif key.endswith('d') and not HAS_FURY: r['ok'] = landed and not (first[0] == 'SPECIAL' and first[1] == BS_FURY); r['note'] = 'no fury: D cancels nothing'
    elif key.endswith('d'): r['flash_p1'] = fl is not None and fl != 0; r['ok'] = landed and first[0] == 'SPECIAL' and first[1] == BS_FURY and first[2] == 0xFF and (fl is None or fl != 0)
    else: r['ok'] = landed and first[0] == 'SPECIAL' and first[1] != BS_FURY
    return r

def special_fury():
    """a ground special whose first hit lands -> D: the fury; D before the hit -> none"""
    for dist in (40, 60, 28, 80, 110):
        for sl in SLOTS:
            settle(); setpos(dist); run(1, sl + 'c'); run(1)
            if st(0) != 'SPECIAL' or b.fget(0, 'spec_id') == BS_FURY: continue
            sid = b.fget(0, 'spec_id'); hit_at = None; h0 = len(b.hits)
            for k in range(120):
                if st(0) != 'SPECIAL' or b.fget(0, 'spec_id') != sid: break
                if b.fget(0, 'freeze') and b.fget(0, 'landed') and b.fget(0, 'y') == 0 and any(h[1] == 2 for h in b.hits[h0:]): hit_at = k; break
                run(1)
            if hit_at is None: continue
            # the hit: D in its hit-stop
            run(1, 'd')
            tr = trace(40, lambda t: t[1] == BS_FURY or t[0] != 'SPECIAL')
            last = tr[-1]; fl = flash_who(); run(20)
            if not HAS_FURY:                             # no fury (game.json): D cancels nothing
                return {'slot': sl + 'C', 'dist': dist, 'then': last, 'note': 'no fury: D cancels nothing',
                        'ok': last[1] != BS_FURY}
            hit = {'slot': sl + 'C', 'dist': dist, 'spec_id': sid, 'hit_frame': hit_at, 'then': last,
                   'flash_p1': fl, 'ok': last[0] == 'SPECIAL' and last[1] == BS_FURY and last[2] == 0xFF and (fl is None or fl != 0)}
            # the same special, D on its first frames (before the hit): no fury
            settle(); setpos(dist); run(1, sl + 'c'); run(1)
            pre = {'state': st(0), 'spec_id': b.fget(0, 'spec_id')}
            run(1, 'd'); run(1)
            tr = trace(240, lambda t: t[0] != 'SPECIAL')
            pre['fury_seen'] = any(t[1] == BS_FURY for t in tr if t[0] == 'SPECIAL')
            pre['ended_in'] = tr[-1][0]
            pre['ok'] = pre['state'] == 'SPECIAL' and pre['spec_id'] == sid and not pre['fury_seen']
            return {'hit': hit, 'before_hit': pre, 'ok': hit['ok'] and pre['ok']}
    return {'ok': None, 'note': 'no ground special of this fighter lands a hit on the dummy'}

def air_special():
    for dist in (40, 56, 70):
        settle(); setpos(dist); run(3, 'Rb')
        for _ in range(20):
            if st(0) == 'AIR': break
            run(1)
        run(4); run(2, 'a')
        for _ in range(40):
            if st(0) == 'AIR_ATTACK' and b.fget(0, 'landed'): break
            if st(0) in ('LAND', 'IDLE'): break
            run(1)
        if not (st(0) == 'AIR_ATTACK' and b.fget(0, 'landed')): continue
        run(2, 'c'); seen = []
        for _ in range(60):
            seen.append((st(0), b.fget(0, 'y')))
            if st(0) in ('LAND', 'IDLE'): break
            run(1)
        air_spec = any(s == 'SPECIAL' and y > 0 for s, y in seen)
        return {'dist': dist, 'special_in_air': air_spec, 'ok': not air_spec, 'note': 'no special starts in the air'}
    return {'ok': None, 'note': 'air A never hit the dummy'}

res = {}
for ci, name in enumerate(names):
    if name not in only: continue
    L.start(ci, 1 if ci == 0 else 0); run(30)
    HAS_FURY = bool(G['roster'][ci].get('fury'))
    r = res[name] = {}
    r['normal_special_hit'] = normal_cancel('c', False)
    r['normal_special_whiff'] = normal_cancel('c', True)
    r['normal_fury_hit'] = normal_cancel('d', False)
    r['normal_fury_whiff'] = normal_cancel('d', True)
    r['special_fury'] = special_fury()
    r['air_normal_special'] = air_special()
    oks = {k: v.get('ok') for k, v in r.items()}
    r['ok'] = all(v is not False for v in oks.values())
    print(name, ' '.join(f'{k}={"ok" if v else ("n/a" if v is None else "FAIL")}' for k, v in oks.items()), flush=True)
json.dump(res, open(os.path.join(OUT, 'cancel143.json'), 'w'), indent=1, default=str)
print('all ok' if all(v['ok'] for v in res.values()) else 'FAIL', len(res), 'fighters')
