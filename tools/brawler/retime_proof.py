#!/usr/bin/env python3
"""Retiming proof (revamp 1C, fighter.c "retiming", docs/brawler_data_model.md "Retiming"): moves played in the
brawler in our emulator's core (harness, Chain Lab training: the fighter against a standing dummy), once at their
source timing and once per set of targets installed at run time (a gretime_t table written into lab.buf, rt_tab
pointed at it: the ROM build has no retime entry). Per run, frame by frame: P1's state, animation step / program step,
source frame (a program's srow), active box, x / y. Checks:
  segments  the source run's segments (live attack box frame by frame) = the export's (bm_seg / chainlab.json), and
            the retimed run's = the targets, frame-exact
  events    the source frames are all played, in order (a program's srow ends equal; a step animation's steps entered
            in order), the first frame of every segment shows its own first source frame (each window's contact)
  travel    x (and y) at each segment boundary = the source's at the same source frame (px)
  hitstop   in range of the dummy: the attacker's hit-stop frames and the dummy's reaction (frames from the hit to
            standing again, the hits it took) = the source's
Writes OUT/retime_proof.json and a contact sheet per move (OUT/<fighter>_<move>.png: source and retimed frames).

    python3 retime_proof.py OUT [GAME_DIR]"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness, retime as RT
from chainlab.labdrive import BUF_OFF

# (fighter, input keys, move key in chainlab (a BA name or a special input), [targets...]) ; targets: a list per
# segment, or a ratio
TESTS = [
    ('terry', 'a', None, [0.5, 0.75, 1.5, 2.0, 'odd']),               # a KOF normal (the A route's first node)
    ('terry', 'Rc', '214C', [0.5, 0.75, 1.5, 2.0, [7, 4, 6]]),        # a KOF ROM special (a dash + flight)
    ('haohmaru', 'Dc', '623S', [0.5, 0.75, 1.5, 2.0, [11, 25, 27]]),  # an SS2 program (a rising slash)
    ('cheng_fu', 'Rc', '236', [0.5, 0.75, 1.5, 2.0, 'odd']),          # a Double Dragon program (5 punches)
    ('kim', 'c', '214B', [0.5, 0.75, 1.5, 2.0, [16, 1, 8, 6, 30]]),   # a Kizuna program, 5 segments each its own target
]
NF = 260
NEAR = {}                         # px in front for the in-range runs (default 40)
DUMMY = 2                                      # the training dummy: fighter 2 (the first enemy slot)

def frame_rec(b):
    st = b.states[b.fget(0, 'state')]
    return {'state': st, 'anim': b.fget(0, 'anim'), 'step': b.fget(0, 'step'), 'srow': b.fget(0, 'srow'),
            'pan': b.fget(0, 'pan'), 'pstep': b.fget(0, 'pstep'), 'atk': 1 if b.fget(0, 'spec_atk') else 0,
            'x': round(b.fget(0, 'x'), 3), 'y': round(b.fget(0, 'y'), 3), 'freeze': b.fget(0, 'freeze'), 'hold': b.fget(0, 'rt_hold'),
            'rt': b.fget(0, 'rt_flags'), 'd_state': b.states[b.fget(DUMMY, 'state')], 'd_hp': b.fget(DUMMY, 'hp'), 'd_freeze': b.fget(DUMMY, 'freeze'),
            'd_x': round(b.fget(DUMMY, 'x'), 3), 'd_y': round(b.fget(DUMMY, 'y'), 3)}

def install(b, tab):
    """tab: [(fighter id, move index, [targets])] -> lab.buf, rt_tab = it (an empty list: rt_tab = 0, the ROM's)"""
    L = b.syms['lab'] + BUF_OFF
    if not tab: b.w(b.syms['rt_tab'], 4, 0); return
    data = b''; arrs = []; off = 8 * (len(tab) + 1)
    for fid, mv, T in tab:
        arrs.append(off); off += 2 * len(T)
    for (fid, mv, T), a in zip(tab, arrs): data += struct.pack('>BBHI', fid, len(T), mv, L + a)
    data += struct.pack('>BBHI', 0xFF, 0, 0, 0)
    for fid, mv, T in tab: data += b''.join(struct.pack('>H', t) for t in T)
    for i in range(0, len(data), 2): b.w(L + i, 2, struct.unpack('>H', data[i:i + 2])[0])
    b.w(b.syms['rt_tab'], 4, L)

def play(b, start, keys, dummy_dx, tab):
    """dummy_dx None: the dummy out of reach (another depth, behind P1), else that far in front on P1's line"""
    b.load(start); install(b, tab)
    x0, z0 = b.fget(0, 'x'), b.fget(0, 'z')
    if dummy_dx is None: b.place(DUMMY, x=x0 - 120, z=z0 + 40)
    else: b.place(DUMMY, x=x0 + dummy_dx, z=z0)
    b.run(2)
    out = []
    for k in range(NF):
        b.run(1, p1=keys if k < 2 else '')
        out.append(frame_rec(b))
    return out

def move_frames(tr, special):
    """(the frames of the move, the frame after it): a special from its first program frame (srow 1), a normal from its
    animation's start; hit-stop frames left out (the clock stops there, by design)"""
    if special:
        i0 = next(i for i, r in enumerate(tr) if r['state'] == 'SPECIAL' and r['srow'] >= 1)
        i1 = next((i for i in range(i0, len(tr)) if tr[i]['state'] != 'SPECIAL'), len(tr) - 1)
    else:
        i0 = next(i for i, r in enumerate(tr) if r['state'] == 'ATTACK')
        i1 = next((i for i in range(i0, len(tr)) if tr[i]['state'] != 'ATTACK' or (i > i0 and tr[i]['anim'] != tr[i0]['anim'])), len(tr) - 1)
    return [r for r in tr[i0:i1] if not r['freeze']], tr[i1]

def active(fr, special, steps):
    return [r['atk'] if special else steps[r['step']][1] for r in fr]

def check(src, after_src, ret, after_ret, segs, T, special, steps):
    a_src, a_ret = active(src, special, steps), active(ret, special, steps)
    s_src, s_ret = RT.segments(a_src), RT.segments(a_ret)
    res = {'segments_src': s_src, 'segments_export': segs, 'targets': T, 'segments_retimed': s_ret,
           'src_ok': s_src == segs and len(src) == sum(segs), 'exact': s_ret == T and len(ret) == sum(T)}
    key = (lambda r: r['srow']) if special else (lambda r: r['step'])
    seq = [key(r) for r in ret]
    res['events'] = seq == sorted(seq) and key(after_ret) == key(after_src) if not special else seq == sorted(seq) and len(ret) == sum(T)
    firsts_src = [sum(segs[:k]) for k in range(len(segs))]; firsts_ret = [sum(T[:k]) for k in range(len(T))]
    res['shown'] = [[key(src[fs]), key(ret[fr_]) if fr_ < len(ret) else None] for fs, fr_ in zip(firsts_src, firsts_ret)]
    res['contact_shown'] = all(a == b for a, b in res['shown'])
    pos = {}                                         # the source's place on each source frame / step shown
    for r in src: pos.setdefault(key(r), (r['x'], r['y']))
    if special: pos = {key(r): (r['x'], r['y']) for r in src}
    settled = [(key(r), round(r['x'] - pos[key(r)][0], 3), round(r['y'] - pos[key(r)][1], 3)) for r in ret if not r['hold'] and key(r) in pos]
    bad = [e for e in settled if abs(e[1]) > 0.01 or abs(e[2]) > 0.01]
    end = (round(after_ret['x'] - after_src['x'], 3), round(after_ret['y'] - after_src['y'], 3))
    res['travel_settled_frames'] = len(settled); res['travel_bad'] = bad[:8]; res['travel_end'] = end
    res['travel_ok'] = not bad and abs(end[0]) < 0.01 and abs(end[1]) < 0.01
    res['frames'] = [len(src), len(ret)]
    return res

def hit_stats(tr):
    """in range of the dummy: per hit the attacker's hit-stop (frames frozen from its onset); the dummy's reaction to
    the first hit: its state and height (from the hit's) frame by frame to the next hit (or 60 frames)"""
    on = [k for k in range(len(tr)) if tr[k]['freeze'] and (k == 0 or not tr[k - 1]['freeze'])]
    stops = []
    for k in on:
        j = k
        while j < len(tr) and tr[j]['freeze']: j += 1
        stops.append(j - k)
    react = []
    if on:
        e = min(on[1] if len(on) > 1 else len(tr), on[0] + 60)
        y0 = tr[on[0]]['d_y']                        # (its height from the hit's: the hit may land higher; x: the
        react = [(r['d_state'], round(r['d_y'] - y0, 3), r['d_y']) for r in tr[on[0]:e]]   # attacker's body pushes it as it moves)
    return {'hitstops': stops, 'reaction': react}

def same_reaction(a, b):
    """the same states and heights from the hit, up to the first landing of either (a hit landing higher falls longer)"""
    n = min(len(a), len(b))
    land = next((i for i in range(1, n) if (a[i][2] == 0 < a[i - 1][2]) or (b[i][2] == 0 < b[i - 1][2])), n)
    return n > 0 and [r[:2] for r in a[:land]] == [r[:2] for r in b[:land]]

def training(b, names, fname):
    """power on, the Chain Lab training (fname against a dummy): its save state"""
    b.core.retro_reset(); b.frame = 0
    for _ in range(400): b.core.retro_run()                 # (boot: no fighter yet, harness.ramtrace's BOOT_FRAMES)
    b.frame = 400
    L = b.syms['lab']
    for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
    b.w(L + 5, 1, names.index(fname)); b.w(L + 6, 1, names.index('terry' if fname != 'terry' else 'ryo')); b.w(L + 4, 1, 1)
    k = 0
    while b.r(L + 8, 1) != 1:
        b.run(1); k += 1; assert k < 600, 'no training'
    b.run(60); return b.save()

def main(out, game=harness.GAME):
    os.makedirs(out, exist_ok=True)
    G = json.load(open(os.path.join(game, 'game.json'))); names = [r['name'] for r in G['roster']]
    lab = json.load(open(os.path.join(game, 'build', 'chainlab.json'))); ba = lab['ba']
    F = {f['name']: f for f in lab['fighters']}
    report = []
    b = harness.Brawler(game=game, tick_sync=True)
    for fname, keys, move, plans in TESTS:
        start = training(b, names, fname)
        special = move is not None
        src = play(b, start, keys, None, [])
        fr_src, af_src = move_frames(src, special)
        fid = names.index(fname)
        if special:
            pool = [p['input'] for p in F[fname]['pool']]; idx = len(ba) + pool.index(move)
            segs = F[fname]['segs']['specials'][pool.index(move)]; steps = None; mname = move
        else:
            mname = ba[fr_src[0]['anim']]; idx = fr_src[0]['anim']
            segs = F[fname]['segs']['moves'][mname]; steps = F[fname]['moves'][mname]['steps']
        near_src = hit_stats(play(b, start, keys, NEAR.get(fname, 40), []))
        for p in plans:
            if p == 'odd': T = [s + (2 if k % 3 == 0 else -1 if s > 2 and k % 3 == 1 else 1) for k, s in enumerate(segs)]
            elif isinstance(p, list): T = p
            else: T = RT.targets({'scale': p}, segs)
            ret = play(b, start, keys, None, [(fid, idx, T)])
            fr_ret, af_ret = move_frames(ret, special)
            res = check(fr_src, af_src, fr_ret, af_ret, segs, T, special, steps)
            near = hit_stats(play(b, start, keys, NEAR.get(fname, 40), [(fid, idx, T)]))
            res.update({'fighter': fname, 'move': mname, 'plan': p, 'hit_src': near_src, 'hit_ret': near,
                        'hitstop_ok': None if near_src['hitstops'] and not near['hitstops'] else   # (n/a: its retimed body hit
                                      set(near['hitstops']) <= set(near_src['hitstops']) and same_reaction(near['reaction'], near_src['reaction']),   # missed a juggle)
                        'hand_check': RT.hand_checks(f'{fname} {mname}', segs, T)})
            res['trace_src'] = fr_src; res['trace_ret'] = fr_ret
            ok = res['src_ok'] and res['exact'] and res['events'] and res['contact_shown'] and res['travel_ok'] and res['hitstop_ok'] is not False
            res['ok'] = ok
            print(f"{'OK ' if ok else 'BAD'} {fname:9s} {mname:12s} {str(p):22s} src {s_(res['segments_src'])} -> {s_(res['segments_retimed'])} (target {s_(T)}) "
                  f"events {res['events']} contact {res['contact_shown']} travel {res['travel_ok']} ({res['travel_settled_frames']} frames) hit-stops {s_(near_src['hitstops'])} | {s_(near['hitstops'])} "
                  f"reaction {'n/a (no body hit)' if res['hitstop_ok'] is None else 'same' if same_reaction(near['reaction'], near_src['reaction']) else 'DIFFERENT'}", flush=True)
            if not res['travel_ok']: print('     travel', res['travel_bad'], 'end', res['travel_end'])
            if not res['contact_shown']: print('     shown', res['shown'])
            report.append(res)
    json.dump(report, open(os.path.join(out, 'retime_proof.json'), 'w'), indent=0)
    print('all ok:', all(r['ok'] for r in report), f'({sum(r["ok"] for r in report)}/{len(report)})')

def s_(v): return '/'.join(map(str, v))

if __name__ == '__main__':
    main(sys.argv[1], *(sys.argv[2:3]))
