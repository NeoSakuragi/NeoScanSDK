#!/usr/bin/env python3
"""THROW REGRESSION PROOF (note 20261016-134631-e03d: "the slam throws are inconsistent: sometimes Terry goes until the
end of the animation, sometimes the animation is cut short"): every throw of every playable fighter (game.json unlocks:
starters + rungs), played in our emulator's core (harness.py, the Chain Lab: P1 the fighter, Ryo the dummy 40 px ahead,
walked into for the hold), under every input pattern a player gives a throw, both facings; then the screen edges,
the enemy thrower and Haggar's MAX chain. One rule is checked (fighter.c "THE THROW'S END"):

  * the throw plays whole: the thrower's script reaches its control return (bthrow_t.ret; a grab special: its
    program's end), the same frames after the damage frame for every pattern without a follow-up, both facings, at the
    screen edges;
  * its damage lands once, on its declared row (game.json throws.timing damage_row, else the engine's slam row); its
    victim is handed to the engine on its declared row (fighter_t.eject: a SLAM's bounce = its damage row, an IMPACT's
    glue row);
  * the only early exit is a deliberate follow-up: a D press after the damage with the meter for the fury (rule 4: the
    fury starts), and a lone A press after the slam: on the floor after a slam that bounced its victim (the jab, for the
    juggle), in the air in a throw that keeps its air attack (SS2 Hanzo's forward throw's leap: the jump's A).
Also: SS2 Hanzo's run Mozu Otoshi (the run grab), Haggar's MAX chain (5 throws, each one's damage once, the last played
whole), an enemy thrower (the dummy Terry, intents written here, throwing Robert: AI throws never follow up).

Patterns (from the throw's first frame; "after" = 8 frames after the damage frame):
  none     nothing after the throw input              fwd / back  the stick held forward / back throughout
  mashA    A pressed every 4 frames throughout          held       D held from before the grab, the throw's A kept held
  Dnometer D pressed once after, no meter (buys nothing)  Aafter   A pressed once after (the follow-up)
  Dafter   D pressed once after, meter full (the fury cancel)

BRUNO'S EVENTS (THE THROW REVIEW round 2, review.html?q=throws2; game.json roster[].throws.events, build_tables
throw_events): for every throw with events, every pattern without a follow-up, both facings, frame N = the throw's
frame (1 = its first frame, as the page numbers them):
  impact  the damage lands once, on frame `impact`
  launch  the victim leaves the thrower's script on frame `launch.frame` (not before), and goes its `dir` over the next
          LAUNCH_WATCH frames: up = it rises (dy >= LAUNCH_MIN px, more than it moves sideways), away = it moves away from
          the thrower (dx >= LAUNCH_MIN px, more than it rises), none = it does not rise (dy <= 1)
  held    the victim is held (fighter_t.held) up to frame `held` (default the launch); from there to the launch it does
          not move (its place and height kept)
--events FILE: the events of an answers file instead (set "throws2"'s format: tools/brawler/throw_answers.py pull2 /
propose), to measure a build against answers not applied yet; --events-only: only these checks (pattern none, both
facings): one line per throw, the table "his answer | the build does | OK / WRONG".

    python3 tools/brawler/throw_regress.py [--game GAME_DIR] [--only terry,haggar] [-v] [--events FILE] [--events-only]
GAME_DIR: the build (examples/brawler: brawler.neo + build/ + fighter.h; another build's copy to test it). One line per
case (PASS / FAIL + why), then "ALL OK (n cases)" or "FAILED k / n"; exit 0 only when all pass. ~45 s.
2026-10-16: 0.10.141 FAILED 41 / 309 (every slam throw and grab special cut by a mashed A or a D that buys nothing:
Bruno's "sometimes cut short"); the fix (THE THROW'S END): ALL OK."""
import argparse, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))

DUMMY = 'ryo'
AFTER = 8                     # frames after the damage frame for the "after" presses
NOCUT = ('none', 'fwd', 'back', 'mashA', 'held', 'Dnometer')
PATTERNS = NOCUT + ('Aafter', 'Dafter')
TM_KEY = {'fwd': 'forward', 'back': 'back', 'holdb': 'hold_b'}
MAXF = 400
LAUNCH_WATCH = 6              # frames after the launch its direction is read over
LAUNCH_MIN = 4                # px the victim must go its way in them


def beta(G):
    u = G['unlocks']
    return list(u['starters']) + [n for r in u['rungs'] for n in r]


class Run:
    def __init__(self, game):
        import harness
        harness.OPTIONS.update({'geolith_system_type': 'mvs', 'geolith_region': 'us'})
        from labdrive import Lab
        self.G = json.load(open(os.path.join(game, 'game.json')))
        self.order = [r['name'] for r in self.G['roster']]
        METER.update(self.G['meter'])
        self.L = Lab(game=game); self.b = self.L.b; self.ST = self.b.states
        import throw_review
        self.scripts = {n: throw_review.scripts(game, n) for n in beta(self.G)}
        self.blob = {}

    def st(self, i): return self.ST[self.b.fget(i, 'state')]

    def start(self, fighter, dummy):
        k = (fighter, dummy)
        if k not in self.blob:
            self.L.start(self.order.index(fighter), self.order.index(dummy)); self.b.run(30)
            self.blob[k] = self.b.save()
        self.b.load(self.blob[k])

    def settle(self):
        b = self.b
        for _ in range(900):
            if self.st(0) == 'IDLE' and self.st(2) in ('IDLE', 'WALK') and not b.fget(0, 'freeze'): return
            b.run(1)
        raise RuntimeError('no settle: ' + b.brief((0, 2)))

    def place(self, face, where='mid', gap=40):
        b = self.b
        cam = b.r(b.syms['cam_x'], 2)
        x0 = {'mid': cam + 140, 'edgeL': cam + 40, 'edgeR': cam + 280}[where]
        if face < 0: x0 = {'mid': cam + 180, 'edgeL': cam + 40 + gap, 'edgeR': cam + 280}[where]
        b.place(0, x=x0, z=30); b.place(2, x=x0 + face * gap, z=30)
        b.fset(0, 'facing', face & 0xFF); b.fset(2, 'facing', (-face) & 0xFF)
        b.fset(2, 'hp', 60); b.fset(0, 'drive', 0); b.fset(0, 'fgauge', 0)
        b.run(2)


METER = {}
def meter_full(b):
    """the drive chunks and the fury gauge full (scenario.py's "full": game.json meter chunk x chunks / fury_max)"""
    b.fset(0, 'drive', METER['chunk'] * METER['chunks']); b.fset(0, 'fgauge', METER['fury_max'])


def throw_case(R, n, kind, pattern, face, where='mid'):
    """one throw from the hold -> the per-frame record and the verdict inputs"""
    b = R.b
    R.start(n, DUMMY); R.settle(); R.place(face, where)
    fw, bk = ('R', 'L') if face > 0 else ('L', 'R')
    pre = 'd' if pattern == 'held' else ''
    for _ in range(80):
        if R.st(0) == 'GRAB': break
        b.run(1, fw + pre)
    else: raise RuntimeError(f'no hold: {b.brief((0, 2))}')
    b.run(2, pre)
    if pattern == 'Dafter': meter_full(b)
    if kind == 'rungrab': raise RuntimeError('rungrab: own setup')
    tk = {'fwd': fw + 'a', 'back': bk + 'a', 'holdb': 'b'}[kind]
    return play(R, tk, pattern, fw, bk, pre)


def play(R, tk, pattern, fw, bk, pre, thrower=0, victim=2, drive=None):
    """the throw input (2 frames), then the pattern, every frame recorded until the thrower is out of its throw and
    the victim down (or MAXF)"""
    b = R.b
    rec = []; started = None; mode = None; dmg_at = None; prev_hp = b.fget(victim, 'hp'); prev_td = 0; out_at = None
    for t in range(MAXF):
        keys = tk if t < 2 else ''
        held_stick = {'fwd': fw, 'back': bk}.get(pattern, '')
        if t >= 2:
            keys = held_stick
            if pattern == 'mashA' and t % 4 < 2: keys += 'a'
            if pattern == 'held': keys += 'a'
            if dmg_at is not None and pattern in ('Aafter', 'Dafter', 'Dnometer') and dmg_at + AFTER <= t < dmg_at + AFTER + 2:
                keys += 'a' if pattern == 'Aafter' else 'd'
        keys += pre
        if drive: drive(t)
        b.run(1, keys if thrower == 0 else '')
        s0, sv = R.st(thrower), R.st(victim)
        hp, td = b.fget(victim, 'hp'), b.fget(victim, 'throw_dealt')
        if started is None and s0 in ('THROW', 'SPECIAL'): started = t; mode = s0
        # the damage: a paired throw's own count (fighter_t.throw_dealt, from 0 at its start: the Chain Lab refills P1's
        # life), a grab special's: the life lost
        drop = 0 if started is None else max(0, td - prev_td) if mode == 'THROW' else max(0, prev_hp - hp)
        r = {'t': t, 'keys': keys, 'th': s0, 'srow': b.fget(thrower, 'srow'), 'tid': b.fget(thrower, 'throw_id'), 'v': sv,
             'vsrow': b.fget(victim, 'srow'), 'hp_drop': drop, 'slam': b.fget(victim, 'slam'), 'eject': b.fget(victim, 'eject'),
             'spec': b.fget(thrower, 'spec_id') if s0 == 'SPECIAL' else None, 'ty': b.fget(thrower, 'y'),
             'vx': b.fget(victim, 'x'), 'vyp': b.fget(victim, 'y'), 'vheld': 1 if b.fget(victim, 'held') else 0, 'tx': b.fget(thrower, 'x')}
        prev_hp = hp; prev_td = td if started is not None else 0
        if started is None:
            if t > 30: raise RuntimeError('no throw: ' + b.brief((0, 2)))
            continue
        rec.append(r)
        if r['hp_drop'] and dmg_at is None: dmg_at = t
        if out_at is None and s0 != mode: out_at = t
        if out_at is not None and t > out_at + 6 and sv not in ('THROWN', 'KNOCKDOWN'): break
    return rec


def verdict(rec, special=False):
    """-> dict: frames in the throw, last row, exit state, damage events (frame, row) before the exit, hand-off"""
    st0 = (rec[0]['th'], rec[0].get('spec'))                 # (a cancel's special / fury is out of the throw)
    end = next((k for k, r in enumerate(rec) if (r['th'], r.get('spec')) != st0), len(rec))
    inside, first_out = rec[:end], rec[end] if end < len(rec) else None
    dmg = [(k, r['vsrow'] - 1, r['hp_drop']) for k, r in enumerate(rec) if r['hp_drop'] and k <= end]
    hand = next(((k, r['vsrow'] - 1, r['v']) for k, r in enumerate(rec) if r['v'] != 'THROWN'), None) if not special else \
        next(((k, None, r['v']) for k, r in enumerate(rec) if r['v'] not in ('GRABBED', 'HITSTUN', 'THROWN') and k > 0), None)
    return {'frames': end, 'last_srow': inside[-1]['srow'] if inside else None, 'exit': first_out['th'] if first_out else None,
            'dmg': dmg, 'hand': hand, 'slam': rec[0]['slam'], 'eject': rec[0]['eject'], 'tid': rec[0]['tid'],
            'tail': end - dmg[0][0] if dmg else None,   # ground: on the floor before the "after" press (the A follow-up's rule)
            'ground': bool(dmg) and dmg[0][0] + AFTER - 1 < len(rec) and rec[dmg[0][0] + AFTER - 1].get('ty', 0) <= 0}


def check_case(R, n, kind, pattern, face, V, ref, special, bounce, script):
    """-> list of failure reasons ([] = PASS)"""
    bad = []
    # the A follow-up: on the floor after a bouncing slam (the jab), in the air in a throw that keeps its air attack
    # (game.json keeps_air_attack "throw_c" / "throw_d": the jump's A in its leap)
    slot = {0: 'throw_c', 1: 'throw_d'}.get(V['tid'])
    air = not special and slot in (next(r for r in R.G['roster'] if r['name'] == n).get('keeps_air_attack') or [])
    a_exit = 'ATTACK' if V['ground'] else 'AIR_ATTACK'
    cut_expected = pattern == 'Dafter' or (pattern == 'Aafter' and ((bounce and V['ground']) or (air and not V['ground'])))
    if len(V['dmg']) != 1: bad.append(f"damage {len(V['dmg'])} times {V['dmg']}")
    if not special:
        tm = (next(r for r in R.G['roster'] if r['name'] == n).get('throws') or {}).get('timing', {}).get(TM_KEY[kind])
        want = tm['damage_row'] if tm else V['slam']
        if V['dmg'] and V['dmg'][0][1] != want: bad.append(f"damage on row {V['dmg'][0][1]}, declared {want}")
        if tm and V['eject'] != 0xFFFF and V['hand'] and V['hand'][1] != V['eject']: bad.append(f"hand-off on row {V['hand'][1]}, declared {V['eject']}")
    if cut_expected:
        if pattern == 'Dafter' and V['exit'] != 'SPECIAL': bad.append(f"D with the meter: no fury cancel (exit {V['exit']})")
        if pattern == 'Aafter' and (V['exit'] != a_exit or V['tail'] is None or V['tail'] > AFTER + 1): bad.append(f"A after the slam: no follow-up (exit {V['exit']}, {V['tail']} frames after the damage)")
    else:
        if script is not None and not special and V['last_srow'] is not None and V['last_srow'] + 2 < script['ret']:
            bad.append(f"cut at row {V['last_srow'] - 1} of {script['ret']} ({V['exit']})")
        if ref is not None and (V['tail'], V['last_srow']) != (ref['tail'], ref['last_srow']):
            bad.append(f"end: {V['tail']} frames after the damage, last row {V['last_srow']} (pattern none: {ref['tail']}, {ref['last_srow']}; exit {V['exit']})")
    return bad


def events_of(R, n, kind, override=None):
    """Bruno's events for this throw: {impact, launch: {frame, dir, size?}, held?} or None (game.json throws.events, or
    --events FILE: an answers file, set "throws2"'s format, by row id <fighter>-<fwd | back | holdb>)"""
    if override is not None:
        a = override.get(f'{n}-{kind}')
        if not a or a.get('choice') != 0: return None
        import throw_answers
        p = throw_answers.parse2(a)
        if not all(k in p for k in ('impact', 'launch', 'dir')): return None
        e = {'impact': p['impact'], 'launch': {'frame': p['launch'], 'dir': p['dir']}}
        if p.get('held'): e['held'] = p['held']
        return e
    r = next(x for x in R.G['roster'] if x['name'] == n)
    return ((r.get('throws') or {}).get('events') or {}).get(TM_KEY[kind])


def events_check(rec, ev, special=False):
    """-> (what the build does in words, [failure reasons]) for one throw's record against Bruno's events"""
    out = rec[0]['v']
    inside = ('THROWN',) if not special else ('GRABBED', 'HITSTUN', 'THROWN')
    dmg = [k + 1 for k, r in enumerate(rec) if r['hp_drop']]
    left = next((k + 1 for k, r in enumerate(rec) if k > 0 and r['v'] not in inside), None)
    bad, did = [], []
    did.append(f"damage {'+'.join(map(str, dmg)) or 'none'}")
    if dmg != [ev['impact']]: bad.append(f"impact: damage on frame(s) {dmg or 'none'}, his impact frame {ev['impact']}")
    L = ev['launch']['frame']; d = ev['launch']['dir']; H = ev.get('held', L)
    did.append(f'let go {left}')
    if left != L: bad.append(f"launch: the victim leaves the throw on frame {left}, his launch frame {L}")
    if not special:
        lost = next((k + 1 for k, r in enumerate(rec[:H]) if not r['vheld']), None)
        if lost is not None and lost < min(H, left or H): bad.append(f"held: let go on frame {lost}, held until {H}")
    if H < L:                                            # held -> launch: it stays where it is
        seg = rec[H - 1:L - 1]
        if seg and len({(round(r['vx']), round(r['vyp'])) for r in seg}) > 1:
            bad.append(f"held {H} -> launch {L}: the victim moves (should stay put)")
    if left is not None and left - 1 + LAUNCH_WATCH < len(rec):
        a, z = rec[left - 1], rec[left - 1 + LAUNCH_WATCH]
        away = 1 if a['vx'] >= a['tx'] else -1
        dx = (z['vx'] - a['vx']) * away; dy = z['vyp'] - a['vyp']
        how = 'up' if dy >= LAUNCH_MIN and abs(dx) <= dy else 'away' if dx >= LAUNCH_MIN and dx > dy else 'none' if dy <= 1 else 'other'
        did.append(f'then {how} (dx {dx:+.0f}, dy {dy:+.0f} px in {LAUNCH_WATCH} frames)')
        if how != d: bad.append(f"launch direction: {how} (dx {dx:+.0f}, dy {dy:+.0f} px), his {d}")
    return ', '.join(did), bad


def throws_of(R, n):
    t = next(r for r in R.G['roster'] if r['name'] == n).get('throws') or {}
    out = ['fwd', 'back']
    if t.get('b') or (t.get('extra') or {}).get('b'): out.append('holdb')
    return out


def is_bounce(R, n, kind, special):
    r = next(x for x in R.G['roster'] if x['name'] == n)
    sb = R.G.get('slam_bounce') or {}
    if special:
        e = (r.get('special_grab_timing') or {})
        return any(v.get('kind') == 'slam' and v.get('bounce', True) is not False for v in e.values()) and sb.get('vy')
    tm = ((r.get('throws') or {}).get('timing') or {}).get(TM_KEY[kind])
    return bool(tm and tm.get('kind') == 'slam' and tm.get('bounce', True) is not False and sb.get('vy'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))
    ap.add_argument('--only', default='')
    ap.add_argument('-v', action='store_true')
    ap.add_argument('--events', default=None)
    ap.add_argument('--events-only', action='store_true')
    a = ap.parse_args()
    EV = json.load(open(a.events)) if a.events else None
    t0 = time.time()
    R = Run(a.game)
    names = [x for x in a.only.split(',') if x] or beta(R.G)
    n_ok = n_all = 0
    def report(label, bad, V):
        nonlocal n_ok, n_all
        n_all += 1; n_ok += not bad
        extra = f"  [{V['frames']} frames, damage row {V['dmg'][0][1] if V['dmg'] else '-'} at +{V['dmg'][0][0] if V['dmg'] else '-'}, end +{V['tail']} after it, last row {V['last_srow']}, exit {V['exit']}]" if a.v or bad else ''
        print(f"{'PASS' if not bad else 'FAIL'} {label}{': ' + '; '.join(bad) if bad else ''}{extra}", flush=True)
    if a.events_only:
        for n in names:
            for kind in throws_of(R, n):
                ev = events_of(R, n, kind, EV)
                if not ev: print(f'---- {n} {kind}: no events'); continue
                his = f"impact {ev['impact']}, launch {ev['launch']['frame']} {ev['launch']['dir']}" + (f", held {ev['held']}" if ev.get('held') else '')
                for face in (1, -1):
                    rec = throw_case(R, n, kind, 'none', face)
                    did, bad = events_check(rec, ev, rec[0]['th'] == 'SPECIAL')
                    n_all += 1; n_ok += not bad
                    print(f"{'OK   ' if not bad else 'WRONG'} {n} {kind} {'right' if face > 0 else 'left '} | his: {his} | build: {did}" + (f" | {'; '.join(bad)}" if bad else ''), flush=True)
        print(f"{'ALL OK' if n_ok == n_all else 'FAILED %d /' % (n_all - n_ok)} ({n_all} cases, {time.time() - t0:.0f} s)")
        sys.exit(0 if n_ok == n_all else 1)
    for n in names:
        for kind in throws_of(R, n):
            ev = events_of(R, n, kind, EV)
            for face in (1, -1):
                ref = None; refs = {}
                for pattern in PATTERNS:
                    rec = throw_case(R, n, kind, pattern, face)
                    special = rec[0]['th'] == 'SPECIAL'
                    V = verdict(rec, special)
                    sname = {0: 'throw_c', 1: 'throw_d', 4: 'throw_x'}.get(V['tid'])
                    script = None if special else R.scripts[n].get(sname)
                    bad = check_case(R, n, kind, pattern, face, V, ref, special, is_bounce(R, n, kind, special), script)
                    if ev and pattern in NOCUT: bad += events_check(rec, ev, special)[1]   # (Bruno's events: every pattern without a follow-up)
                    if pattern == 'none': ref = V
                    refs[pattern] = V
                    report(f"{n} {kind} {'right' if face > 0 else 'left'} {pattern}", bad, V)
                if face > 0: R_ref = ref
                else:
                    bad = [] if (ref['tail'], ref['last_srow']) == (R_ref['tail'], R_ref['last_srow']) else [f"facing left ends {ref['tail']} / row {ref['last_srow']}, right {R_ref['tail']} / row {R_ref['last_srow']}"]
                    report(f"{n} {kind} both facings alike", bad, ref)
            for where in ('edgeL', 'edgeR'):
                for face in (1, -1):
                    rec = throw_case(R, n, kind, 'none', face, where)
                    special = rec[0]['th'] == 'SPECIAL'
                    V = verdict(rec, special)
                    bad = [] if (V['tail'], V['last_srow'], len(V['dmg'])) == (R_ref['tail'], R_ref['last_srow'], 1) else \
                        [f"at {where}: end {V['tail']} / row {V['last_srow']}, damage x{len(V['dmg'])} (mid: {R_ref['tail']} / row {R_ref['last_srow']})"]
                    report(f"{n} {kind} {where} {'right' if face > 0 else 'left'}", bad, V)
    if not a.only or 'hanzo_ss2' in names:
        for pattern in ('none', 'fwd', 'mashA', 'Dnometer', 'Aafter'):
            V, bad = rungrab_case(R, pattern)
            report(f"hanzo_ss2 run grab (Mozu Otoshi) {pattern}", bad, V)
    if not a.only or 'haggar' in names:
        for pattern in ('none', 'fwd', 'mashA', 'Dnometer'):
            V, bad = max_chain_case(R, pattern)
            report(f"haggar MAX chain {pattern}", bad, V)
    for kind in ('fwd', 'back'):
        for pattern in ('none', 'mashA', 'fwd'):
            V, bad = enemy_case(R, kind, pattern)
            report(f"enemy thrower (terry on robert) {kind} {pattern}", bad, V)
    print(f"{'ALL OK' if n_ok == n_all else 'FAILED %d /' % (n_all - n_ok)} ({n_all} cases, {time.time() - t0:.0f} s)")
    sys.exit(0 if n_ok == n_all else 1)


RUNGRAB_REF = {}
def rungrab_case(R, pattern):
    """SS2 Hanzo's run Mozu Otoshi (game.json roster hanzo_ss2 run grab): a run of 30 frames into Ryo grabs into it"""
    b = R.b
    R.start('hanzo_ss2', DUMMY); R.settle(); R.place(1, gap=40)
    cam = b.r(b.syms['cam_x'], 2); b.place(0, x=cam + 20); b.place(2, x=cam + 296); meter_full(b)   # (the run grab costs a
    b.run(2, 'R'); b.run(3, ''); b.run(2, 'R')                                                     # drive chunk)
    for _ in range(120):
        if R.st(0) == 'SPECIAL': break
        b.run(1, 'R')
    else: raise RuntimeError('run grab: no special: ' + b.brief((0, 2)))
    if pattern != 'Dafter': b.fset(0, 'drive', 0); b.fset(0, 'fgauge', 0)
    rec = play(R, 'R', pattern, 'R', 'L', '')
    V = verdict(rec, True)
    bad = []
    if len(V['dmg']) != 1: bad.append(f"damage {len(V['dmg'])} times")
    if pattern == 'Aafter' and V['ground']:
        if V['exit'] != 'ATTACK' or V['tail'] is None or V['tail'] > AFTER + 1: bad.append(f"A after the slam: no follow-up (exit {V['exit']})")
    elif pattern == 'none': RUNGRAB_REF['v'] = V
    elif (V['tail'], V['frames']) != (RUNGRAB_REF['v']['tail'], RUNGRAB_REF['v']['frames']):
        bad.append(f"end {V['tail']} frames after the damage, {V['frames']} in all (none: {RUNGRAB_REF['v']['tail']}, {RUNGRAB_REF['v']['frames']}; exit {V['exit']})")
    return V, bad


MAX_REF = {}
def max_chain_case(R, pattern):
    """Haggar's MAX (down+D, the meter full): pieces, then the chain's 5 throws on the reeling Ryo; each throw's damage
    once, the last one played whole whatever the pattern"""
    b = R.b
    R.start('haggar', DUMMY); R.settle(); R.place(1, gap=34); meter_full(b)
    R.L.poke(16 + 64 * 6 + 16 + 128 * 24 + 1, [1]); b.fset(0, 'hp', 10)   # low life (the MAX's red state; lab.p1_life:
    b.run(2, 'Dd')                                                         # the lab's P1 keeps it, scenario.py hp)
    throws, t, last = [], 0, None
    prev = None; mprev = None; prev_hp = b.fget(2, 'hp'); prev_td = 0
    for t in range(1400):
        keys = {'fwd': 'R'}.get(pattern, '')
        if pattern == 'mashA' and t % 4 < 2: keys += 'a'
        if pattern == 'Dnometer' and throws and t % 30 == 0: b.fset(0, 'drive', 0); b.fset(0, 'fgauge', 0); keys += 'd'
        b.run(1, keys)
        s0, mc, hp, td = R.st(0), b.fget(0, 'mchn'), b.fget(2, 'hp'), b.fget(2, 'throw_dealt')
        new = s0 == 'THROW' and (prev != 'THROW' or (mc != mprev and mc))   # a chain throw starts (mchn: its index + 1)
        if new: throws.append({'t': t, 'tid': b.fget(0, 'throw_id'), 'dmg': 0, 'rows': []})
        if throws and s0 == 'THROW': throws[-1]['rows'].append(b.fget(0, 'srow'))
        if new and hp < prev_hp and len(throws) > 1: throws[-2]['dmg'] += 1   # (a chain throw's damage lands as the next grabs)
        elif not new and throws and (td > prev_td or hp < prev_hp): throws[-1]['dmg'] += 1   # (throw_dealt: from 0 at each
        prev_hp = hp; mprev = mc; prev_td = 0 if new else td                 # throw's start; the lab refills the dummy's life)
        if throws and prev == 'THROW' and s0 != 'THROW': last = {'exit': s0, 't': t}; break
        prev = s0
    V = {'frames': len(throws[-1]['rows']) if throws else 0, 'dmg': [(0, 0, 0)] * (throws[-1]['dmg'] if throws else 0),
         'tail': throws[-1]['rows'][-1] if throws else None, 'last_srow': throws[-1]['rows'][-1] if throws else None,
         'exit': last and last['exit'], 'throws': len(throws), 'per': [x['dmg'] for x in throws]}
    bad = []
    want = len(next(r for r in R.G['roster'] if r['name'] == 'haggar')['max_chain']['throws'])
    if len(throws) != want: bad.append(f"{len(throws)} chain throws, {want} declared")
    if any(x['dmg'] != 1 for x in throws): bad.append(f"each chain throw's damage once: {[x['dmg'] for x in throws]}")
    if pattern == 'none': MAX_REF['v'] = V
    elif MAX_REF.get('v') and (V['frames'], V['last_srow']) != (MAX_REF['v']['frames'], MAX_REF['v']['last_srow']):
        bad.append(f"last throw: {V['frames']} frames to row {V['last_srow']} (none: {MAX_REF['v']['frames']} to row {MAX_REF['v']['last_srow']})")
    return V, bad


ENEMY_REF = {}
def enemy_case(R, kind, pattern):
    """the dummy Terry (team 1, intents written by the test: in a Chain Lab fight nothing else writes them) walks into P1
    (Robert), grabs and throws him; P1's pattern while thrown changes nothing"""
    b = R.b
    R.start('robert', 'terry'); R.settle(); R.place(1, gap=60)
    ia = b.syms['in'] + 2 * b.syms['sizeof_intent']
    def intent(dx=0, press=0, grab=1):
        for off, v in ((0, dx & 0xFF), (1, 0), (2, press), (5, grab), (6, 1)): b.w(ia + off, 1, v)
    for _ in range(90):
        intent(-1); b.run(1)
        if R.st(2) == 'GRAB': break
    else: raise RuntimeError('enemy: no hold: ' + b.brief((0, 2)))
    b.fset(0, 'hp', 60)
    face = b.fget(2, 'facing')
    def drive(t): intent((face if kind == 'fwd' else -face) if t < 2 else 0, 1 if t == 0 else 0)
    rec = []
    pk = {'mashA': lambda t: 'a' if t % 4 < 2 else '', 'fwd': lambda t: 'L'}.get(pattern, lambda t: '')
    started = None; prev_hp = b.fget(0, 'hp'); prev_td = 0
    for t in range(MAXF):
        drive(t); b.run(1, pk(t))
        s2, s0 = R.st(2), R.st(0); hp = b.fget(0, 'hp')
        r = {'th': s2, 'srow': b.fget(2, 'srow'), 'tid': b.fget(2, 'throw_id'), 'v': s0, 'vsrow': b.fget(0, 'srow'),
             'hp_drop': max(0, b.fget(0, 'throw_dealt') - prev_td) if started is not None or s2 == 'THROW' else 0,
             'slam': b.fget(0, 'slam'), 'eject': b.fget(0, 'eject')}
        prev_hp = hp; prev_td = b.fget(0, 'throw_dealt')
        if started is None and s2 == 'THROW': started = t
        if started is not None:
            rec.append(r)
            if s2 != 'THROW' and len(rec) > 8 and s0 not in ('THROWN', 'KNOCKDOWN'): break
    if not rec: raise RuntimeError('enemy: no throw: ' + b.brief((0, 2)))
    V = verdict(rec)
    bad = []
    if len(V['dmg']) != 1: bad.append(f"damage {len(V['dmg'])} times")
    tm = (next(r for r in R.G['roster'] if r['name'] == 'terry').get('throws') or {}).get('timing', {}).get(TM_KEY[kind])
    want = tm['damage_row'] if tm else V['slam']
    if V['dmg'] and V['dmg'][0][1] != want: bad.append(f"damage on row {V['dmg'][0][1]}, declared {want}")
    sname = {0: 'throw_c', 1: 'throw_d', 4: 'throw_x'}.get(V['tid'])
    sc = R.scripts.get('terry', {}).get(sname)
    if sc and V['last_srow'] + 2 < sc['ret']: bad.append(f"cut at row {V['last_srow'] - 1} of {sc['ret']}")
    key = kind
    if pattern == 'none': ENEMY_REF[key] = V
    elif (V['tail'], V['last_srow']) != (ENEMY_REF[key]['tail'], ENEMY_REF[key]['last_srow']):
        bad.append(f"end {V['tail']} / row {V['last_srow']} (none: {ENEMY_REF[key]['tail']} / row {ENEMY_REF[key]['last_srow']})")
    return V, bad


if __name__ == '__main__':
    main()
