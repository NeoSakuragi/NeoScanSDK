#!/usr/bin/env python3
"""Throws audit (docs/throws_audit.md): every throw path's thrower / victim per frame in the brawler, diffed against the
decoded source path (the paired script's rows = the source game's per-frame thrower / victim record as its importer
exported it; a victim list's entries = the source's per-step victim placement), plus the KOF98 raw captures for the
KOF98 paired throws (the source game itself, our emulator: tools/kof96/capture/throws98/<id>.txt).
Our emulator only (Geolith harness, `make AI_OFF=1` build), one core per process.

    BRAWLER_CORE=<core> python3 throws_audit.py OUT run CASE [CASE ...]   each case in its own process -> OUT/<case>.json
        CASE = thrower:action[:scene[:victim_slot]]   action fwd | back | up (the hold's up + A) | chain (the chain's back
        throw) | hold (3 hold hits); scene mid (default: the thrower placed so the throw's whole path is on screen) | edge
        (the screen's edge ~100 px past the thrower on the victim's side); victim_slot = fighter index (2 Ryo, 3 Ralf,
        4 Yashiro, 5 WHP Hanzo, 7 Rugal; default 2)
    python3 throws_audit.py OUT src98 KOF98ID throw_c|throw_d NAME    KOF98 raw capture vs the exported rows -> OUT/src98_*.json
    python3 throws_audit.py OUT ana CASE [CASE ...]                    the diff again on cases already run (+ sheets)
    python3 throws_audit.py OUT side98 KOF98ID throw_c|throw_d CASE k,k,..   KOF98 itself (our emulator, screenshots) and
        the brawler case side by side at the throw's frames k -> OUT/side_*.png
    python3 throws_audit.py OUT static                                every roster throw's data vs the engine's rules: rows
        below the floor, reach, the hold -> row 0 jump per slot, the engine's re-derived flight vs the rows; KOF's per-victim
        throw lists vs the mirror match the brawler plays -> OUT/static.json
    python3 throws_audit.py OUT compare BEFORE_DIR AFTER_DIR [AFTER2_DIR]   the conflicts measured per case in each run
        (metrics(): start jump, teleport, pair separation, floating, offset error per phase, a list's attacker jump) ->
        OUT/compare.json + a table on stdout

The source path (since throws part 1, 2026-10-12): a KOF victim of the thrower's game is checked against ITS OWN list
(build/bm_chars.c bm_vthr: the script's rows + the victim's deltas), any other against the script's rows (the mirror
match: its posture anchors are the brawler's, not a source). THROWS_REF=<build dir> reads the data from another build
(the before run analysed against the after build's source rows: `ana` with THROWS_REF).
"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
REF = os.environ.get('THROWS_REF') or os.path.join(GAME, 'build')     # the data (bm_chars.c / .h, bm_spec.c)
FIELDS = ['state', 'srow', 'x', 'y', 'z', 'facing', 'shown_frame', 'frame_ovr', 'zfront', 'anim', 'freeze', 'throw_x0',
          'throw_id', 'vlist', 'vent', 'pstep', 'spec_ix', 'spec_id', 'pcatch', 'held', 'pflags', 'speed', 'acc']
KEY = {'fwd': 'Ra', 'back': 'La', 'up': 'Ua'}


# ---- the exported data (build/bm_chars.c, build/bm_spec.c) ----------------------------------------------------------
def _ints(s): return [int(v, 0) for v in re.findall(r'-?0x[0-9A-Fa-f]+|-?\d+', s)]


def data():
    c = open(os.path.join(REF, 'bm_chars.c')).read()
    rows = {m.group(1): [tuple(_ints(r)) for r in re.findall(r'\{([^{}]*)\}', m.group(2))]
            for m in re.finditer(r'static const bthrow_row_t (\w+)\[\] = \{(.*?)\};', c, re.S)}
    def th(ent):
        f = [x.strip() for x in ent.split(',')]
        if f[2] == '0': return None
        return dict(nrows=int(f[0], 0), speed=int(f[1], 0), rows=rows[f[2]], ret=int(f[3], 0), rel=int(f[4], 0),
                    land=int(f[5], 0), gframe=int(f[11], 0) if len(f) > 11 else 0xFFFF)
    out = {}
    for m in re.finditer(r'static const bthrow_t (\w+)_throws\[BT_COUNT\] = \{(.*?)\};', c, re.S):
        e = re.findall(r'\{([^{}]*)\}', m.group(2)); out.setdefault(m.group(1), {})['throw_c'] = th(e[0]); out[m.group(1)]['throw_d'] = th(e[1])
    for m in re.finditer(r'static const bthrow_t (\w+)_holds\[2\] = \{(.*?)\};', c, re.S):
        e = re.findall(r'\{([^{}]*)\}', m.group(2)); out.setdefault(m.group(1), {})['hold_hit'] = th(e[0]); out[m.group(1)]['hold_fin'] = th(e[1])
    for m in re.finditer(r'static const bthrow_t (\w+)_xthrow = \{(.*?)\};', c, re.S):
        out.setdefault(m.group(1), {})['throw_x'] = th(m.group(2))
    vp = {m.group(1): _ints(m.group(2)) for m in re.finditer(r'static const uint16_t (\w+)_vposes\[VP_COUNT \+ 1\] = \{(.*?)\};', c, re.S)}
    h = open(os.path.join(REF, 'bm_chars.h')).read()
    keys = re.search(r'enum \{ VP_COUNT = \d+ \};\s*/\* victim postures: (.*?) \*/', h).group(1).split()
    s = open(os.path.join(REF, 'bm_spec.c')).read()
    ve = {m.group(1): [tuple(_ints(r)) for r in re.findall(r'\{([^{}]*)\}', m.group(2))]
          for m in re.finditer(r'static const bvent_t (\w+)\[\] = \{(.*?)\};', s, re.S)}
    vl = {}
    for m in re.finditer(r'static const bvlist_t (\w+)_vl\[\] = \{(.*?)\};', s, re.S):
        L = []
        for r in re.findall(r'\{([^{}]*)\}', m.group(2)):
            f = [x.strip() for x in r.split(',')]
            L.append(dict(n=int(f[0], 0), flags=int(f[1], 0), e=ve.get(f[2], []), vx=int(f[3], 0), vy=int(f[4], 0), g=int(f[5], 0)))
        vl[m.group(1)] = L
    bc = [x.strip()[3:].lower() for x in re.search(r'enum \{ (BC_\w+(?:, BC_\w+)*), BC_COUNT \};', h).group(1).split(',')]
    vr = {m.group(1): [tuple(_ints(r)) for r in re.findall(r'\{([^{}]*)\}', m.group(2))]
          for m in re.finditer(r'static const bvrow_t (\w+)\[\] = \{(.*?)\};', c, re.S)}
    for m in re.finditer(r'static const bvthr_t (\w+)_(throw_c|throw_d|throw_x)_vthr\[\] = \{(.*?)\};', c, re.S):
        for e in re.findall(r'\{(\d+), 0, \d+, (\w+)\}', m.group(3)):
            th = out.get(m.group(1), {}).get(m.group(2))
            if th: th.setdefault('per_victim', {})[bc[int(e[0])]] = vr[e[1]]
    return out, vp, keys, vl


def victim_rows(th, vic):
    """the source path for this victim: the script's rows with its own list's deltas (bm_vthr), else the rows as they are"""
    P = th.get('per_victim', {}).get(vic)
    if not P: return th['rows'], False
    R = []
    for i, r in enumerate(th['rows']):
        vp, fl, dx, dy = P[min(i, len(P) - 1)]
        R.append((r[0], r[1], r[2], r[3] if vp == 0xFE else vp, (r[4] & ~1) | (fl & 1), r[5] + dx, r[6] + dy) + tuple(r[7:]))
    return R, True


# ---- one case in the brawler ----------------------------------------------------------------------------------------
def snap(b, i):
    d = {k: b.fget(i, k) for k in FIELDS if k in b.layout}
    d['state'] = b.states[d['state']]
    if 'throw_x0' in d: v = d['throw_x0']; d['throw_x0'] = (v - (1 << 32) if v & 0x80000000 else v) / 65536   # (16.16)
    return d


def case(spec, out, shots):
    import harness as H
    p = spec.split(':'); who, act = p[0], p[1]
    scene = p[2] if len(p) > 2 else 'mid'; V = int(p[3]) if len(p) > 3 else 2
    b = H.Brawler(tick_sync=True)
    names = [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
    b.pick(names.index(who), unlock=True)
    st = b.states.index
    for i in range(1, 8):                                    # everyone off but the victim
        if not b.fget(i, 'ch'): continue
        b.fset(i, 'state', st('IDLE' if i == V else 'OFF')); b.fset(i, 'hp', 120); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0)
        b.fset(i, 'y', 0); b.fset(i, 'frame_ovr', 0xFFFF); b.fset(i, 'held', 0); b.intent(i)
        if i != V: b.place(i, x=2000, z=30)
    b.fset(0, 'hp', 120)
    b.run(2)
    cam = lambda: (lambda v: v - 65536 if v >= 32768 else v)(b.r(b.syms['cam_x'], 2))
    c0 = cam()
    # the thrower faces right; scene picks where: mid, edge (left edge behind it: a back throw goes there), wall (right)
    back = act == 'back' or act == 'chain'                    # (the victim lands behind the thrower)
    x1 = c0 + ({'mid': 250, 'edge': 70}[scene] if back else {'mid': 60, 'edge': 200}[scene])   # mid: the throw's whole
                                                             # room on screen; edge: the screen's edge 100-ish px past it
    b.place(0, x=x1, z=30); b.fset(0, 'facing', 1)
    b.place(V, x=x1 + (60 if act == 'chain' else 34), z=30); b.fset(V, 'facing', 0xFF)
    b.run(2)
    if act == 'chain':                                       # the chain to its back throw: A x links, then back + A
        b.fset(0, 'drive', 480)
        frames = []
        for f in range(200):
            b.run(1, p1='a' if f % 6 == 0 and f < 30 else ('La' if 30 <= f < 33 else ''))
            if b.states[b.fget(0, 'state')] == 'THROW': break
        else: raise RuntimeError('no chain throw: ' + b.brief())
    else:
        for f in range(80):
            b.run(1, p1='R')
            if b.states[b.fget(0, 'state')] == 'GRAB': break
        else: raise RuntimeError('no grab: ' + b.brief())
    rows = [dict(f=-1, cam=cam(), t=snap(b, 0), v=snap(b, V))]   # the hold, before the throw
    if shots: os.makedirs(os.path.join(out, spec.replace(':', '_')), exist_ok=True)
    for f in range(240):
        k = KEY.get(act, '') if f == 0 else ''
        if act == 'hold': k = 'a' if f in (0, 30, 60) else ''
        if shots: b.pad = [set(k), set()]; b.screenshot(os.path.join(out, spec.replace(':', '_'), f'{f:03d}.png'))
        else: b.run(1, p1=k)
        rows.append(dict(f=f, cam=cam(), t=snap(b, 0), v=snap(b, V)))
        if f > 20 and rows[-1]['v']['state'] in ('DOWN', 'GETUP', 'IDLE') and rows[-1]['t']['state'] in ('IDLE', 'WALK'): break
    res = dict(case=spec, thrower=who, victim=names[b.char_of(V)], floor_top=b.r(b.syms['floor_top'], 2), rows=rows)
    json.dump(res, open(os.path.join(out, spec.replace(':', '_') + '.json'), 'w'))
    return res


# ---- the diff ---------------------------------------------------------------------------------------------------------
def analyse(res, D, VP, VPK, VL):
    rows = res['rows']; who, vic = res['thrower'], res['victim']
    rep = dict(case=res['case'], victim=vic, events=[], frames=[])
    t0 = next((r for r in rows if r['f'] >= 0 and r['t']['state'] == 'THROW'), None)
    sp0 = next((r for r in rows if r['f'] >= 0 and r['t']['state'] == 'SPECIAL'), None)
    hold = rows[0]
    if t0:                                               # ---- a paired script (throw, extra paired throw, hold hit)
        tid = t0['t']['throw_id']
        key = {0: 'throw_c', 1: 'throw_d', 2: 'hold_hit', 3: 'hold_fin', 4: 'throw_x'}.get(tid)
        th = D[who][key]; R, own = victim_rows(th, vic); face = 1 if t0['t']['facing'] > 0 else -1
        rep['own_rows'] = own
        x0 = t0['t']['throw_x0']
        if abs(x0) > 65536: x0 = (x0 - (1 << 32) if x0 & 0x80000000 else x0) / 65536   # (a raw 16.16 record)
        spd = th['speed'] / 256
        rep.update(throw=key, nrows=th['nrows'], ret=th['ret'], rel=th['rel'], land=th['land'], speed=th['speed'])
        # the hold -> the throw's row 0: the victim's offset and picture jump
        hv = (hold['v']['x'] - hold['t']['x']) * (1 if hold['t']['facing'] > 0 else -1)
        rep['hold_to_row0'] = dict(hold_dx=round(hv, 1), row0_dx=R[0][5], hold_tframe=hold['t']['shown_frame'], row0_tframe=R[0][0],
                                   hold_vframe=hold['v']['shown_frame'], hold_facing=hold['t']['facing'], throw_facing=face)
        start = rows.index(t0); last = lastk = 0
        for r in rows[start:]:
            k = r['f'] - t0['f']                                 # the row shown: the script's own clock (the thrower's
            if r['t']['state'] == 'THROW': i = r['t']['srow'] - 1   # row, else the victim's, then the source's time from
            elif r['v']['state'] == 'THROWN': i = r['v']['srow'] - 1   # the last row either showed: hit-stops excluded)
            else: i = last + int((k - lastk) * spd)
            if r['t']['state'] == 'THROW' or r['v']['state'] == 'THROWN': last, lastk = i, k
            if i >= th['nrows']: i = th['nrows'] - 1
            if i < 0: i = 0
            s = R[i]; tfr, tx, ty, vpo, fl, vx, vy = s[:7]
            T, Vv = r['t'], r['v']
            want_t = x0 + face * tx; want_v = x0 + face * (tx + vx); want_vy = ty + vy
            want_vf = None if fl & 32 or vpo == 0xFF else VP[vic][vpo] if vpo < len(VP[vic]) else None
            want_vface = face if fl & 1 else -face
            phase = 'held' if (th['rel'] == 0xFFFF or i < th['rel']) else ('flight' if th['land'] == 0xFFFF or i <= th['land'] else 'after')
            if i < SWAP and phase == 'held': phase = 'swap'
            e = dict(f=k, row=i, phase=phase, tstate=T['state'], vstate=Vv['state'], cam=r['cam'], want_vy=want_vy, v_y=Vv['y'],
                     v_x=Vv['x'], t_xw=T['x'],
                     t_x=round(T['x'] - want_t, 1) if T['state'] == 'THROW' else None,
                     t_y=round(T['y'] - ty, 1) if T['state'] == 'THROW' else None,
                     v_dx=round(Vv['x'] - want_v, 1), v_dy=round(Vv['y'] - want_vy, 1),
                     v_off=round((Vv['x'] - T['x']) * face, 1), want_off=vx if T['state'] == 'THROW' else None,
                     v_face_ok=(Vv['facing'] > 0) == (want_vface > 0),
                     v_frame=Vv['shown_frame'], want_vframe=want_vf, vpose=vpo, vkey=VPK[vpo] if vpo < len(VPK) else None,
                     t_frame=T['shown_frame'], want_tframe=tfr, vanim=Vv['anim'], vfreeze=Vv['freeze'], tfreeze=T['freeze'])
            rep['frames'].append(e)
            if k > th['nrows'] / spd + 40: break
        rep['hold_v'] = (hold['v']['x'], hold['v']['y']); rep['hold_t'] = hold['t']['x']
    elif sp0:                                            # ---- a grab special: its victim lists
        ix = sp0['t']['spec_ix']; L = VL.get(f'{who}_sp{ix}', [])
        rep.update(special=ix, lists=[dict(n=l['n'], flags=l['flags']) for l in L])
        start = rows.index(sp0)
        for r in rows[start:]:
            T, Vv = r['t'], r['v']; face = 1 if T['facing'] > 0 else -1
            li = T['vlist']; e = dict(f=r['f'] - sp0['f'], tstate=T['state'], vstate=Vv['state'], vlist=li, pstep=T['pstep'],
                                     pcatch=T['pcatch'], off=round((Vv['x'] - T['x']) * face, 1), dy=round(Vv['y'] - T['y'], 1),
                                     vy=round(Vv['y'], 1), v_frame=Vv['shown_frame'], vface=Vv['facing'], tface=T['facing'], cam=r['cam'],
                                     t_x=round(T['x'], 1), v_x=round(Vv['x'], 1), zfront=Vv['zfront'])
            if li and not li & 0x80 and li - 1 < len(L) and L[li - 1]['n'] and not L[li - 1]['flags'] & 1:   # (VL_FRAMES: per frame)
                ent = L[li - 1]['e'][min(T['pstep'], L[li - 1]['n'] - 1)]
                e.update(want_off=ent[0], want_dy=ent[1], want_vframe=VP[vic][ent[2]] if ent[2] < len(VP[vic]) else None,
                         vkey=VPK[ent[2]] if ent[2] < len(VPK) else None)
            rep['frames'].append(e)
    return rep


def summary(rep):
    F = rep['frames']; s = dict(case=rep['case'], victim=rep['victim'])
    if 'throw' in rep:
        s.update({k: rep[k] for k in ('throw', 'nrows', 'ret', 'rel', 'land', 'speed', 'hold_to_row0')})
        bad = lambda f, k, tol=1.5: f.get(k) is not None and abs(f[k]) > tol
        for ph in ('held', 'flight', 'after'):
            P = [f for f in F if f['phase'] == ph]
            if not P: continue
            s[ph] = dict(frames=len(P), victim_x_off=sum(bad(f, 'v_dx') for f in P), victim_y_off=sum(bad(f, 'v_dy') for f in P),
                         max_vx=max(abs(f['v_dx']) for f in P), max_vy=max(abs(f['v_dy']) for f in P),
                         thrower_off=sum(bad(f, 't_x') or bad(f, 't_y') for f in P),
                         facing_bad=sum(not f['v_face_ok'] for f in P if f['vstate'] == 'THROWN'),
                         vframe_bad=sum(f['want_vframe'] is not None and f['v_frame'] != f['want_vframe'] for f in P if f['vstate'] == 'THROWN'),
                         tframe_bad=sum(f['t_frame'] != f['want_tframe'] for f in P if f['tstate'] == 'THROW'),
                         first_bad=next((f['f'] for f in P if bad(f, 'v_dx') or bad(f, 'v_dy')), None))
        jumps = []
        for a, b_ in zip(F, F[1:]):                         # the victim's per-frame step vs the source's step there
            if a['vstate'] in ('THROWN', 'KNOCKDOWN') or b_['vstate'] in ('THROWN', 'KNOCKDOWN'):
                d = abs((b_['v_dx'] - a['v_dx'])) + abs(b_['v_dy'] - a['v_dy'])
                if d > 6: jumps.append((b_['f'], b_['row'], a['vstate'], b_['vstate'], round(d, 1)))
        s['divergence_steps'] = jumps[:8]
    else:
        G = [f for f in F if 'want_off' in f]
        s.update(special=rep.get('special'), lists=rep.get('lists'), listed_frames=len(G),
                 off_bad=sum(abs(f['off'] - f['want_off']) > 1.5 for f in G), dy_bad=sum(abs(f['dy'] - f['want_dy']) > 1.5 for f in G),
                 vframe_bad=sum(f['want_vframe'] is not None and f['v_frame'] != f['want_vframe'] for f in G),
                 y_below_floor=sum(f['vy'] < 0 for f in F), first=[(f['f'], f['vlist'], f['pstep'], f['off'], f.get('want_off'), f['dy'], f.get('want_dy'))
                                                                    for f in G if abs(f['off'] - f['want_off']) > 1.5 or abs(f['dy'] - f['want_dy']) > 1.5][:6])
    return s


def metrics(rep):
    """the audit's conflicts as numbers, one case (docs/throws_audit.md "After"): start_jump = the victim's / thrower's
    largest move in one frame over the throw's first rows (the hold -> row 0 swap, the pair's placement: was one frame);
    teleport = the largest one-frame jump of the victim off its source path (|d dx| + |d dy| between two frames, px);
    sep = the largest pair separation error while both are in the script (victim - thrower vs the row's offset, px);
    floating = the largest height above its source of a victim whose source row is below the floor (px); held / flight /
    after = the largest |dx|, |dy| off the source per phase; swap rows apart (the swap segment, by design). A victim list:
    off / dy entries off, the attacker's largest one-frame move, frames below the floor"""
    F = rep['frames']; m = dict(case=rep['case'], victim=rep['victim'])
    if 'throw' in rep:
        m['own_rows'] = rep.get('own_rows')
        hv, ht = rep.get('hold_v'), rep.get('hold_t')
        vx = [hv[0]] + [f['v_x'] for f in F] if hv else [f['v_x'] for f in F]
        tx = [ht] + [f['t_xw'] for f in F] if ht is not None else [f['t_xw'] for f in F]
        n0 = max(SWAP, 1) + 1
        m['start_jump_v'] = round(max(abs(b - a) for a, b in zip(vx[:n0], vx[1:n0 + 1])), 1)
        m['start_jump_t'] = round(max(abs(b - a) for a, b in zip(tx[:n0], tx[1:n0 + 1])), 1)
        steps = [abs(b['v_dx'] - a['v_dx']) + abs(b['v_dy'] - a['v_dy']) for a, b in zip(F, F[1:]) if b['phase'] != 'swap']
        m['teleport'] = round(max(steps), 1) if steps else 0
        S = [abs(f['v_off'] - f['want_off']) for f in F if f['tstate'] == 'THROW' and f['vstate'] == 'THROWN' and f['want_off'] is not None and f['phase'] != 'swap']
        m['sep'] = round(max(S), 1) if S else 0
        FL = [f['v_y'] - f['want_vy'] for f in F if f['want_vy'] < 0 and f['vstate'] == 'THROWN']
        m['floating'] = round(max(FL), 1) if FL else 0
        for ph in ('held', 'flight', 'after'):
            P = [f for f in F if f['phase'] == ph]
            if P: m[ph] = (round(max(abs(f['v_dx']) for f in P), 1), round(max(abs(f['v_dy']) for f in P), 1))
    else:
        G = [f for f in F if 'want_off' in f]
        m['off_bad'] = sum(abs(f['off'] - f['want_off']) > 1.5 for f in G); m['dy_bad'] = sum(abs(f['dy'] - f['want_dy']) > 1.5 for f in G)
        m['max_off'] = round(max((abs(f['off'] - f['want_off']) for f in G), default=0), 1)
        m['max_dy'] = round(max((abs(f['dy'] - f['want_dy']) for f in G), default=0), 1)
        m['attacker_jump'] = round(max((abs(b['t_x'] - a['t_x']) for a, b in zip(F, F[1:])), default=0), 1)
        m['below_floor'] = sum(f['vy'] < 0 for f in F)
    return m


SWAP = 0                                                     # (main: game.json throw_swap.frames)


# ---- the KOF98 source itself --------------------------------------------------------------------------------------------
def src98(cid, key, name):
    """the KOF98 raw capture (P1 = the thrower, P2 = Yuri) vs the exported rows: per frame the victim's place relative to
    the thrower's throw origin, thrower x / y, the facing; from the frame the victim enters its thrown state"""
    sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture')); import analyze as A
    p = os.path.join(HERE, '..', 'kof96', 'capture', 'throws98', f'{cid}.txt')
    r1, r2 = A.load(p, 1), A.load(p, 2)
    lo = 40 if key == 'throw_c' else 340
    g0 = next(i for i in range(lo, len(r2)) if A.state_of(r2[i][3]) >= 400)
    while g0 > lo and A.state_of(r1[g0 - 1][3]) == A.state_of(r1[g0][3]): g0 -= 1      # the thrower's throw state's first frame
    face = 1 if A.facing_of(r1[g0][3]) else -1
    x0 = A.x_of(r1[g0][3]); y0 = A.y_of(r1[g0][3])
    D, _, _, _ = data(); R = D[name][key]['rows']
    out = []
    for k in range(min(len(R) + 30, len(r1) - g0)):
        w1, w2 = r1[g0 + k][3], r2[g0 + k][3]
        sx = (A.x_of(w2) - x0) * face; tx = (A.x_of(w1) - x0) * face
        e = dict(k=k, tstate=A.state_of(w1), vstate=A.state_of(w2), t_x=round(tx, 2), v_x=round(sx, 2), v_y=round(A.y_of(w2) - y0, 2),
                 t_y=round(A.y_of(w1) - y0, 2))
        if k < len(R): e.update(row_tx=R[k][1], row_vx=R[k][1] + R[k][5], row_vy=R[k][2] + R[k][6])
        out.append(e)
    return dict(id=cid, key=key, name=name, facing=face, frames=out,
                diffs=[(e['k'], e['v_x'] - e['row_vx'], e['v_y'] - e['row_vy']) for e in out if 'row_vx' in e and
                       (abs(e['v_x'] - e['row_vx']) > 1.5 or abs(e['v_y'] - e['row_vy']) > 1.5)][:12])


# ---- the static audit: every roster throw's data vs the engine's rules (no emulator) ---------------------------------
GRAVITY_KD = 0x5000 / 65536                                  # fighter.c (the knockdown's gravity, px / frame^2)


def engine_flight(th):
    """the brawler's flight from the release (fighter.c thrown_release + update S_KNOCKDOWN kmode 0), frame by frame from
    the release row's place, vs the rows rel.. (the source's own flight); -> per-frame (dx, dy) and the landing"""
    R, rel, n = th['rows'], th['rel'], th['nrows']
    le = th['land'] if th['land'] < n and th['land'] > rel else n - 1
    r, e = R[rel], R[le]
    dx = (e[1] + e[5]) - (r[1] + r[5]); y0 = r[2] + r[6]
    spd = th['speed'] or 256
    t = max(1, (le - rel) * 256 // spd)
    vx = int(abs(dx) * 256 // t) / 256 * (1 if dx >= 0 else -1)
    vy = t * GRAVITY_KD / 2 - (y0 / t if y0 > 0 else 0)
    x, y, out = r[1] + r[5], max(0, y0), []
    k = 0
    while True:
        k += 1; y += vy; vy -= GRAVITY_KD; x += vx
        i = min(n - 1, rel + k * spd // 256); s = R[i]
        out.append((k, i, round(x - (s[1] + s[5]), 1), round(max(0, y) - max(0, s[2] + s[6]), 1)))
        if y <= 0 or k > 200: break
    dec = (R[min(n - 1, rel + 1)][1] + R[min(n - 1, rel + 1)][5] - r[1] - r[5], R[min(n - 1, rel + 1)][2] + R[min(n - 1, rel + 1)][6] - y0)
    return dict(t=t, derived_v=(round(vx, 2), round(t * GRAVITY_KD / 2 - (y0 / t if y0 > 0 else 0), 2)), decoded_v=dec,
                land_frame=k, land_row_frames=t, max_dx=max(abs(o[2]) for o in out), max_dy=max(abs(o[3]) for o in out), path=out)


def static_audit():
    D, VP, VPK, VL = data()
    roster = json.load(open(os.path.join(GAME, 'game.json')))['roster']
    rep = {}
    for r in roster:
        n = r['name']; T = D.get(n, {}); hold0 = (T.get('hold_hit') or {}).get('rows', [None])[0]
        out = {}
        for key, th in T.items():
            if not th or not th['nrows']: continue
            R = th['rows']; o = dict(nrows=th['nrows'], speed=th['speed'], ret=th['ret'], rel=th['rel'], land=th['land'])
            neg = [(i, x[2] + x[6]) for i, x in enumerate(R) if x[2] + x[6] < 0]
            o['below_floor_rows'] = len(neg); o['below_floor_min'] = min((v for _, v in neg), default=0)
            o['reach'] = max(abs(x[1] + x[5]) for x in R); o['thrower_travel'] = max(abs(x[1]) for x in R)
            o['turned_rows'] = sum(1 for x in R if x[4] & 8)
            if key in ('throw_c', 'throw_d', 'throw_x') and hold0:
                land = th['land'] if th['land'] < th['nrows'] else th['nrows'] - 1
                behind = (R[land][5] < 0) if th['land'] < th['nrows'] else (R[-1][1] + R[-1][5] < 0)
                for slot in (('fwd', 'back') if key != 'throw_x' else ('asis',)):
                    turned = slot != 'asis' and behind != (slot == 'back')
                    v0 = -R[0][5] if turned else R[0][5]           # the victim's row-0 place, in the hold's facing
                    o[f'hold_jump_{slot}'] = dict(hold_dx=hold0[5], row0_dx=v0, jump=abs(v0 - hold0[5]), turned=turned,
                                                  hold_tframe=th.get('gframe') if th.get('gframe', 0xFFFF) != 0xFFFF else None,
                                                  row0_tframe=R[0][0])
            if th['rel'] < th['nrows']:
                ef = engine_flight(th); ef.pop('path'); o['release'] = ef
            out[key] = o
        rep[n] = out
    return rep


def mirror_spread(game, names, pool):
    """KOF96 / 98 / 99 exports: a throw's rows as the brawler uses them (the thrower's mirror match, export_bm.throw_rows)
    vs the same throw's rows for each other victim of the game (KOF's per-victim throw lists): the victim's offset
    difference over the held rows (before the release) and the victim states that differ"""
    ex = json.load(open(f'/data/neogeo_dict/exports/{game}/kof95_export.json'))['characters']
    out = {}
    for n in names:
        ch = ex.get(n)
        if not ch: continue
        for key in ('throw_c', 'throw_d'):
            th = ch.get('throws', {}).get(key)
            if not th: continue
            V = th['victims']; mine = V.get(n) or next(iter(V.values()))
            st = lambda x: int(x[5].split('.')[0]) if x[5] else -1
            rel = next((i for i in range(1, len(mine)) if 0 <= st(mine[i]) < 400 and st(mine[i - 1]) >= 400), len(mine))
            res = {}
            for v in pool:
                if v == n or v not in V: continue
                o = V[v]; m = min(rel, len(o), len(mine))
                dx = max(abs(o[i][1] - mine[i][1]) for i in range(m)); dy = max(abs(o[i][2] - mine[i][2]) for i in range(m))
                sd = sum(1 for i in range(m) if o[i][5] != mine[i][5])
                res[v] = (dx, dy, sd)
            out[f'{n}:{key}'] = dict(held_rows=rel, per_victim=res, worst=max(res.values(), key=lambda t: max(t[0], t[1])) if res else None)
    return out


# ---- contact sheet -----------------------------------------------------------------------------------------------------
def sheet(out, spec, rep, floor_top):
    """the brawler's frames (screenshots) with the source path drawn over them: red = where the decoded source puts the
    victim's origin this frame (a cross) and its whole path (dots), blue = the brawler's victim origin and path, green =
    the thrower's origin; frames picked where the brawler leaves the source (|dx| or |dy| > 2, a picture / facing
    mismatch), with context"""
    from PIL import Image, ImageDraw
    d = os.path.join(out, spec.replace(':', '_'))
    F = rep['frames']; res = json.load(open(os.path.join(out, spec.replace(':', '_') + '.json')))
    rows = {r['f']: r for r in res['rows']}
    f0 = F[0]['f']; base = next(r['f'] for r in res['rows'] if r['f'] >= 0 and r['t']['state'] in ('THROW', 'SPECIAL'))
    def scr(x, y, z, cam): return (x - cam - 8, floor_top + z - y - 8)
    paired = 'throw' in rep
    pick = []
    for f in F:
        if paired:
            div = abs(f['v_dx']) > 2 or abs(f['v_dy']) > 2 or (f['want_vframe'] is not None and f['vstate'] == 'THROWN' and f['v_frame'] != f['want_vframe'])
        else:
            div = 'want_off' in f and (abs(f['off'] - f['want_off']) > 1.5 or abs(f['dy'] - f['want_dy']) > 1.5) or f['vy'] < 0
        if div: pick.append(f['f'])
    if not pick: pick = [f['f'] for f in F[::6]]
    sel = sorted(set(pick[:1] + pick[::max(1, len(pick) // 10)][:10] + [max(0, pick[0] - 2)]))[:12]
    tiles = []
    for k in sel:
        fn = os.path.join(d, f'{base + k:03d}.png')
        if not os.path.exists(fn): continue
        im = Image.open(fn).convert('RGB'); g = ImageDraw.Draw(im)
        r = rows[base + k]; cam = r['cam']; T, Vv = r['t'], r['v']
        if paired:
            for e in F:                                     # the source path (red dots) and the brawler's (blue)
                rr = rows.get(base + e['f'])
                if not rr: continue
                sx, sy = scr(rr['v']['x'] - e['v_dx'], rr['v']['y'] - e['v_dy'], rr['v']['z'], cam)
                g.point((sx, sy), fill=(255, 0, 0))
                bx, by = scr(rr['v']['x'], rr['v']['y'], rr['v']['z'], cam); g.point((bx, by), fill=(0, 0, 255))
            e = next(e for e in F if e['f'] == k)
            sx, sy = scr(Vv['x'] - e['v_dx'], Vv['y'] - e['v_dy'], Vv['z'], cam)
            g.line((sx - 5, sy, sx + 5, sy), fill=(255, 0, 0)); g.line((sx, sy - 5, sx, sy + 5), fill=(255, 0, 0))
            lab = f"f{k} row{e['row']} {e['phase']} dx{e['v_dx']:+.0f} dy{e['v_dy']:+.0f}" + (' FRAME' if e['want_vframe'] is not None and e['vstate'] == 'THROWN' and e['v_frame'] != e['want_vframe'] else '')
        else:
            e = next(e for e in F if e['f'] == k)
            if 'want_off' in e:
                sx, sy = scr(T['x'] + (1 if T['facing'] > 0 else -1) * e['want_off'], T['y'] + e['want_dy'], Vv['z'], cam)
                g.line((sx - 5, sy, sx + 5, sy), fill=(255, 0, 0)); g.line((sx, sy - 5, sx, sy + 5), fill=(255, 0, 0))
            lab = f"f{k} L{e['vlist']} s{e['pstep']} off{e['off']:+.0f}/{e.get('want_off')} dy{e['dy']:+.0f}/{e.get('want_dy')}"
        bx, by = scr(Vv['x'], Vv['y'], Vv['z'], cam)
        g.line((bx - 5, by, bx + 5, by), fill=(0, 0, 255)); g.line((bx, by - 5, bx, by + 5), fill=(0, 0, 255))
        tx, ty = scr(T['x'], T['y'], T['z'], cam)
        g.line((tx - 4, ty - 4, tx + 4, ty + 4), fill=(0, 200, 0)); g.line((tx - 4, ty + 4, tx + 4, ty - 4), fill=(0, 200, 0))
        g.rectangle((0, 0, im.width, 11), fill=(255, 255, 255)); g.text((2, 0), lab, fill=(0, 0, 0))
        tiles.append(im)
    if not tiles: return None
    W, Hh = tiles[0].size; cols = 4; n = len(tiles)
    S = Image.new('RGB', (W * cols, Hh * ((n + cols - 1) // cols)), (255, 255, 255))
    for i, t in enumerate(tiles): S.paste(t, ((i % cols) * W, (i // cols) * Hh))
    p = os.path.join(out, 'sheet_' + spec.replace(':', '_') + '.png'); S.save(p); return p


# ---- source vs brawler, side by side (KOF98 in our emulator) -------------------------------------------------------------
def srcshots98(out, cid, key, case_spec, ks):
    """KOF98 itself: the throw played from the fighter's state c<cid> (P2 Yuri), as tools/kof96/capture/throws96.py run98
    does, with a screenshot every frame (neogeo_sdl --capture SNAPS); then a sheet: per k in ks (frames from the throw's
    first frame) the source's screen (left) and the brawler case's screen (right, its throw's frame k)"""
    from PIL import Image, ImageDraw
    cap = os.path.join(HERE, '..', 'kof96', 'capture'); sys.path.insert(0, cap); sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture'))
    os.environ['GAME'] = 'kof98'
    import emu, analyze as A
    from timeline import seqs
    s0 = 40; ev = {'throw_c': 'p1 0 40 R; p1 26 3 Rc', 'throw_d': 'p1 0 40 R; p1 26 3 Rd'}[key]
    spec = []
    for e in ev.split(';'):
        w, a, n, i = e.split(); spec.append(f'{w} {int(a) + s0} {n} {i}')
    s1, s2 = seqs('; '.join(spec), s0 + 260)
    d = os.path.join(out, f'src98_{cid}_{key}'); os.makedirs(d, exist_ok=True)
    txt = os.path.join(d, 'cap.txt')
    emu.run('kof98', txt, s1, s2, [f'{s0 - 2}:108118=01,108119=B0,108318=01,108319=E8'], reload=f'c{cid}', reload_frames=[s0 - 4],
            snaps=range(s0, s0 + 250), snapdir=d, timeout=900)
    r2 = A.load(txt, 2); r1 = A.load(txt, 1)
    g0 = next(i for i in range(s0, len(r2)) if A.state_of(r2[i][3]) >= 400)
    while A.state_of(r1[g0 - 1][3]) == A.state_of(r1[g0][3]): g0 -= 1
    res = json.load(open(os.path.join(out, case_spec.replace(':', '_') + '.json')))
    base = next(r['f'] for r in res['rows'] if r['f'] >= 0 and r['t']['state'] == 'THROW')
    tiles = []
    for k in ks:
        a = os.path.join(d, f'snap_{g0 + k}.ppm'); b = os.path.join(out, case_spec.replace(':', '_'), f'{base + k:03d}.png')
        if not (os.path.exists(a) and os.path.exists(b)): continue
        A_ = Image.open(a).convert('RGB'); B_ = Image.open(b).convert('RGB')
        t = Image.new('RGB', (A_.width + B_.width + 4, max(A_.height, B_.height) + 12), (255, 255, 255))
        t.paste(A_, (0, 12)); t.paste(B_, (A_.width + 4, 12))
        ImageDraw.Draw(t).text((2, 0), f'k={k}  KOF98 (left)  |  brawler {case_spec} (right)', fill=(0, 0, 0))
        tiles.append(t)
    if not tiles: return None
    S = Image.new('RGB', (tiles[0].width * 2, tiles[0].height * ((len(tiles) + 1) // 2)), (255, 255, 255))
    for i, t in enumerate(tiles): S.paste(t, ((i % 2) * t.width, (i // 2) * t.height))
    p = os.path.join(out, f'side_{cid}_{key}_{case_spec.replace(":", "_")}.png'); S.save(p); return p


def main():
    global SWAP
    out, cmd = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    SWAP = (json.load(open(os.path.join(GAME, 'game.json'))).get('throw_swap') or {}).get('frames', 0)
    if cmd == 'compare':                                     # compare DIR DIR [DIR]: the metrics side by side
        res = {}
        for d in sys.argv[3:]:
            for f in sorted(os.listdir(d)):
                if f.startswith('rep_') and f.endswith('.json'):
                    r = json.load(open(os.path.join(d, f))); res.setdefault(r['case'], {})[os.path.basename(d.rstrip('/'))] = metrics(r)
        json.dump(res, open(os.path.join(out, 'compare.json'), 'w'), indent=1)
        for c, v in res.items(): print(c, json.dumps(v))
        return
    if cmd == 'one':                                         # (a child process: one core)
        case(sys.argv[3], out, shots=True); return
    if cmd == 'src98':
        r = src98(int(sys.argv[3]), sys.argv[4], sys.argv[5])
        json.dump(r, open(os.path.join(out, f'src98_{sys.argv[5]}_{sys.argv[4]}.json'), 'w'), indent=1)
        print(json.dumps(dict(r, frames=None)))
        return
    if cmd == 'side98':                                      # side98 KOF98ID KEY CASE k,k,...
        print(srcshots98(out, int(sys.argv[3]), sys.argv[4], sys.argv[5], [int(k) for k in sys.argv[6].split(',')])); return
    if cmd == 'static':                                      # the data audit (no emulator) -> OUT/static.json
        rep = static_audit()
        pool = ['terry', 'ryo', 'ralf', 'robert', 'yamazaki', 'billy', 'kyo', 'iori', 'mai', 'yashiro', 'rugal']
        rep['_mirror_kof98'] = mirror_spread('kof98', pool, pool)
        rep['_mirror_kof96'] = mirror_spread('kof96', ['geese', 'mr_big', 'krauser', 'goenitz'], ['geese', 'mr_big', 'krauser', 'goenitz'])
        json.dump(rep, open(os.path.join(out, 'static.json'), 'w'), indent=1); return
    D, VP, VPK, VL = data()
    if cmd in ('run', 'ana'):                                # ana: the diff again on the cases already run
        allrep = {}
        for spec in sys.argv[3:]:
            if cmd == 'run': subprocess.run([sys.executable, __file__, out, 'one', spec], check=True)
            res = json.load(open(os.path.join(out, spec.replace(':', '_') + '.json')))
            rep = analyse(res, D, VP, VPK, VL)
            json.dump(rep, open(os.path.join(out, 'rep_' + spec.replace(':', '_') + '.json'), 'w'), indent=1)
            s = summary(rep); s['metrics'] = metrics(rep); allrep[spec] = s
            s['sheet'] = sheet(out, spec, rep, res['floor_top'])
            print(json.dumps(s), flush=True)
        p = os.path.join(out, 'summary.json')
        old = json.load(open(p)) if os.path.exists(p) else {}
        old.update(allrep); json.dump(old, open(p, 'w'), indent=1)


if __name__ == '__main__':
    main()
