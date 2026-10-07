#!/usr/bin/env python3
"""TODO #191 (a): every Samurai Shodown II move's length and step timing in the brawler vs SS2, both in our emulator.

    python3 timing191.py ss2 [haohmaru genjuro kuroko]       SS2's whiffs -> /data/tmp/ss2t191/ss2/<name>.json
    python3 timing191.py brawler OUT.json [names]            the brawler's (a built examples/brawler; BRAWLER_CORE)
    python3 timing191.py table BEFORE.json AFTER.json OUTDIR   -> OUTDIR/timing191.json + timing191.txt

The move's length = the frames the fighter is in it: SS2 class 1 (+$E6, the action routine's class: set the frame the
action starts, 0 again the frame its routine goes back to neutral); the brawler S_SPECIAL (start_special's frame
included, prog_end's not) / S_ATTACK for a normal. Specials: every command result of the fighter's exported specials,
every button row, played with the opponent out of reach (SS2: P2 poked 300 px away; the brawler: the Chain Lab dummy
260 px away), the furies in SS2's rage (+$F0 = 32); normals: SS2's far A / B / C / D / A+B / C+D (moves/CC.json, P2
160 px away: whiffs) vs the brawler's exported far normals played alone (fighter_t.frame_ovr per frame). Steps: per
frame of the move the SS2 (animation, step) shown, mapped to the exported frame; equal = the same frames on the same
frame numbers from the move's start."""
import json, os, sys, glob, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
WORK = '/data/tmp/ss2t191'
CHAR = {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17}
NORMALS = {'atk_a_far': 'far_a', 'atk_b_far': 'far_b', 'atk_c_far': 'far_c', 'atk_d_far': 'far_d', 'body_toss': 'far_ab'}
FAR = int(os.environ.get("SS2_FAR", 300))  # px between the players in SS2's whiffs

def ss2_whiffs(name):
    """every exported special's command results played in SS2 with P2 out of reach -> {input: [{v, result, frames,
    seq: [(anim, step index)] per class-1 frame}]}"""
    import cap_ss2 as C, commands_ss2 as K, handlers_ss2 as H, ss2
    from capture_cmds import seq_for, parse_hex, obj_row
    ch = CHAR[name]
    ents = {e['result']: e for e in K.command_list(ch)}
    jobs = []
    for inp, (fn, nv, results) in H.SPECIALS[name].items():
        for v, res in enumerate(results):
            e = ents.get(res)
            if e is None: continue
            sq = seq_for(e).split(',')            # (a press repeated, C C C C C: a frame each, released a frame between)
            if len(sq) > 1 and len({x.split(':')[1] for x in sq}) == 1: sq = ','.join(['1:' + sq[0].split(':')[1]] * len(sq)).replace(',', ',1:-,')
            else: sq = ','.join(sq)
            jobs.append((inp, v, res, sq, inp == 'WFT' or 'RAGE' in inp))
    state = f'/data/neogeo_dict/samsho2/cap/p1_{ch:02d}.state'
    d0 = f'{WORK}/probe'; C.run(d0, '3:-', load=state, vram=False, sndlog=False)
    r = C.ram(d0, 1); a1, a2 = C.players(r)
    SEG, LEAD = 400, 12
    out = {}
    for c0 in range(0, len(jobs), 4):
        chunk = jobs[c0:c0 + 4]
        lanes, pokes, reload = [], [], []
        for j, (inp, v, res, sq, rage) in enumerate(chunk):
            base = j * SEG; reload.append(base)
            body = f'{LEAD}:-,{sq}'; lanes.append(body + f',{SEG - C.nframes(body)}:-')
            x = C.s16(r, a1 - 0x100000 + 0x4E) + FAR
            pokes.append(';'.join(f'{base + k}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}' for k in range(1, 4)))
            if rage: pokes.append(';'.join(f'{base + k}:{a1 + 0xF0:X}=20' for k in range(1, 4)))
        seq = ','.join(lanes); total = C.nframes(seq)
        d = f'{WORK}/cap_{name}'; os.makedirs(d, exist_ok=True)
        for f in glob.glob(f'{d}/cap.txt*'): os.remove(f)
        rd = ';'.join(f'{f}:{a1:X}:120;{f}:{a2:X}:120' for f in range(total))
        env = dict(os.environ, SEQ=seq, SEQ2=f'{total}:-', OUT=f'{d}/cap.txt', LOAD=state, RAMDUMP=rd, POKE=';'.join(pokes))
        if len(reload) > 1: env.update(RELOAD=','.join(map(str, reload[1:])), RELOAD_STATE=state)
        subprocess.run([C.NGSDL, C.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=7200)
        for j, (inp, v, res, sq, rage) in enumerate(chunk):
            rows = []
            for f in range(j * SEG + 1, (j + 1) * SEG):
                o1 = parse_hex(f'{d}/cap.txt.ram{f}_{a1:06X}'); o2 = parse_hex(f'{d}/cap.txt.ram{f}_{a2:06X}')
                if o1 is None: continue
                rows.append((obj_row(o1), obj_row(o2)))
            # (the move: from the first class-1 frame to the first frame after it that is not)
            s0 = next((i for i, (p, _) in enumerate(rows) if p['cls'] == 1), None)
            if s0 is None: out.setdefault(inp, []).append(dict(v=v, result=res, frames=None)); continue
            e = next((i for i in range(s0, len(rows)) if rows[i][0]['cls'] != 1), None)
            idx = {}
            def sidx(a, addr):
                if a not in idx: idx[a] = {s['addr']: i for i, s in enumerate(ss2.parse_anim(ch, a, 400))}
                return idx[a].get(addr)
            seqf = [(p['a'], sidx(p['a'], p['st'])) for p, _ in rows[s0:e]]
            ys = [224 - p['y'] for p, _ in rows[s0:e]]
            xs = [p['x'] - rows[s0][0]['x'] for p, _ in rows[s0:e]]
            out.setdefault(inp, []).append(dict(v=v, result=res, frames=(e - s0) if e is not None else None,
                                                hit=any(q['cls'] == 3 for _, q in rows[s0:e]), seq=seqf, y=ys, x=xs,
                                                after=[rows[e][0]['a'], sidx(rows[e][0]['a'], rows[e][0]['st'])] if e is not None else None))
        for f in glob.glob(f'{d}/cap.txt.ram*'): os.remove(f)
    # normals: the captures' far whiffs
    caps = {m['name']: m for m in json.load(open(f'/data/neogeo_dict/samsho2/moves/{ch:02d}.json')) if not m['entry']}
    norm = {}
    for mv, cn in NORMALS.items():
        cr = caps[cn]['rows']
        s0 = next(i for i, q in enumerate(cr) if q['p1']['cls'] == 1)
        e = next(i for i in range(s0, len(cr)) if cr[i]['p1']['cls'] != 1)
        idx = {s['addr']: i for i, s in enumerate(ss2.parse_anim(ch, cr[s0]['p1']['a'], 400))}
        norm[mv] = dict(capture=cn, frames=e - s0, seq=[(q['p1']['a'], idx.get(q['p1']['st'])) for q in cr[s0:e]],
                        hit=any(q['p2']['cls'] == 3 for q in cr[s0:e]))
    return {'specials': out, 'normals': norm}

def brawler(names):
    """the brawler's moves alone in the Chain Lab training (P1 = the fighter): every special of the pool at slot C
    neutral (spec_tab poked to a pack whose first slot is that special; the row poked in its start frame), the dummy
    260 px away (a fury too, as a slot special: its program without the super flash's freeze)"""
    import harness
    from chainlab.labdrive import PACK_OFF
    G = json.load(open(os.path.join(GAME, 'game.json'))); roster = [r['name'] for r in G['roster']]
    lab = {f['name']: f for f in json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))['fighters']}
    b = harness.Brawler(game=GAME); S = b.syms
    for _ in range(400): b.core.retro_run()
    L = S['lab']; MAP = L + PACK_OFF
    for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
    out = {}
    for name in names:
        fi = roster.index(name); pool = [p['input'] for p in lab[name]['pool']]
        ex = json.load(open(os.path.join(GAME, 'build', f'tmp_samsho2_{name}', 'kof95_export.json')))['characters'][name]
        nvar = {sp['input']: max(1, len((sp['rom'].get('vtable') or {}).get('rows') or [None])) for sp in ex['specials']}
        res = {}
        for inp in pool:
            for v in range(nvar.get(inp, 1)):
                b.w(L + 5, 1, fi); b.w(L + 6, 1, roster.index('terry')); b.w(L + 4, 1, 1)
                b.run(30)
                b.w(S['spec_tab'] + 4 * fi, 4, MAP)
                for j in range(6): b.w(MAP + j, 1, pool.index(inp) if j == 0 else 0xFF)
                b.fset(0, 'meter', 120); b.fset(0, 'facing', 1)
                b.place(2, x=b.fget(0, 'x') + 260, z=b.fget(0, 'z') + 40)
                b.run(2)
                keys = 'c'                         # (a fury too: as a slot special, no super flash freeze)
                f0 = None; tl = []
                for f in range(900):
                    b.run(1, p1=keys if f < 3 else '')
                    st = b.states[b.fget(0, 'state')]
                    if f0 is None and st == 'SPECIAL':
                        f0 = f
                        if nvar.get(inp, 1) > 1 and v != b.fget(0, 'var'):
                            # another button row: the row is latched at the start and an SS2 program's first frame
                            # runs in the start frame (SF_NOW), so the program is restarted with the row poked: the
                            # next frame is its first (this one not counted)
                            b.fset(0, 'var', v); b.fset(0, 'pres', 0); b.fset(0, 'srow', 0); b.fset(0, 'pflags', 0)
                            b.fset(0, 'pcnt', 0); b.fset(0, 'vx', 0); b.fset(0, 'vy', 0); t0 = b.fget(0, 'throw_x0'); b.fset(0, 'x', (t0 - (1 << 32) if t0 & 0x80000000 else t0) / 65536)
                            continue
                    if f0 is not None:
                        if st != 'SPECIAL': break
                        tl.append([b.fget(0, 'frame_ovr'), b.fget(0, 'srow'), b.fget(0, 'freeze'), b.fget(0, 'spec_ix')])
                ix = tl[0][3] if tl else None
                # frames of the move: the S_SPECIAL frames, less those the program did not run (a fury's flash pose, its
                # freeze: srow unchanged after the program's first frame)
                run = 1 + sum(1 for k in range(1, len(tl)) if tl[k][1] != tl[k - 1][1]) if tl else None
                res.setdefault(inp, []).append(dict(v=v, frames=len(tl), prog_frames=run, frame_seq=[t[0] for t in tl],
                                                    srow=[t[1] for t in tl], spec_ix=ix, expect_ix=pool.index(inp)))
                print(name, inp, v, 'frames', len(tl), 'program', run, flush=True)
                b.run(120)
        # normals: A from neutral (the route's root link: far, down, forward), the dummy out of reach; S_ATTACK frames
        import export_bm
        norm = {}
        for keys in ('a', 'Da', 'Ra'):
            b.w(L + 5, 1, fi); b.w(L + 6, 1, roster.index('terry')); b.w(L + 4, 1, 1)
            b.run(30); b.fset(0, 'facing', 1)
            b.place(2, x=b.fget(0, 'x') + 260, z=b.fget(0, 'z') + 40)
            b.run(2)
            f0 = None; tl = []
            for f in range(300):
                b.run(1, p1=keys if f < 2 else '')
                st = b.states[b.fget(0, 'state')]
                if f0 is None and st == 'ATTACK': f0 = f
                if f0 is not None:
                    if st != 'ATTACK': break
                    tl.append([b.fget(0, 'anim'), b.fget(0, 'step')])
            mv = export_bm.MOVES[tl[0][0]] if tl and tl[0][0] < len(export_bm.MOVES) else None
            a = ex['anims'].get(mv) if mv else None
            norm[keys] = dict(move=mv, frames=len(tl), steps=[t[1] for t in tl], ss2_anim=a['slot'] if a else None,
                              ss2_len=sum(s['ticks'] + 1 for s in a['steps']) if a else None)
            print(name, 'normal', keys, norm[keys]['move'], 'frames', len(tl), 'ss2 anim', norm[keys]['ss2_anim'], norm[keys]['ss2_len'], flush=True)
            b.run(60)
        out[name] = {'specials': res, 'normals': norm}
    return out

def ss2_ref(name, inp, v, res, far):
    """SS2's whiff of this row: the vs-state capture (moves/CC.json, P2 160 px away: the distance every check uses)
    when it whiffs, else the far one (timing191 ss2); a row that hits in both: the decoded length (handlers_ss2.check:
    the program frame-identical to SS2 up to the hit) -> (frames, seq or None, source)"""
    import ss2
    ch = CHAR[name]
    caps = {m['entry']['result']: m for m in json.load(open(f'/data/neogeo_dict/samsho2/moves/{ch:02d}.json')) if m['entry']}
    rage = {m['entry']['result']: m for m in json.load(open(f'/data/neogeo_dict/samsho2/moves/{ch:02d}_rage.json')) if m['entry']}
    cap = (rage if inp == 'WFT' or 'RAGE' in inp else caps).get(res)
    import handlers_ss2 as H
    ents = H.SPECIALS[name][inp][0](v)[0]
    a0 = ents[0]['anim']                          # (a capture whose class-1 frames are another action: not this move;
    taken = True
    if cap and cap['rows'] and next((q['p1']['a'] for q in cap['rows'] if q['p1']['cls'] == 1), None) != a0: cap = None; taken = False   # Kuroko's
                                                  # C C C C C is never taken in our captures: SS2 plays its far C)
    if cap:
        cr = cap['rows']; s0 = next((i for i, q in enumerate(cr) if q['p1']['cls'] == 1), None)
        if s0 is not None:
            e = next((i for i in range(s0, len(cr)) if cr[i]['p1']['cls'] != 1), None)
            if e is not None and not any(cr[i]['p2']['cls'] == 3 for i in range(s0, e)):
                idx = {}
                def sidx(a, addr):
                    if a not in idx: idx[a] = {s['addr']: i for i, s in enumerate(ss2.parse_anim(ch, a, 400))}
                    return idx[a].get(addr)
                return e - s0, [(q['p1']['a'], sidx(q['p1']['a'], q['p1']['st'])) for q in cr[s0:e]], 'SS2 160 px'
    f = next((x for x in far.get(inp, []) if x['v'] == v and x.get('seq') and x['seq'][0][0] == a0), None)
    air = any(e['phys'] != 'ground' and not (isinstance(e['phys'], tuple) and e['phys'][0] in ('decel', 'accel')) for e in ents)
    # (a move that leaves the ground: not from the far whiff: SS2's rise depends on the players' distance, measured:
    # Haohmaru 623S A+B... 68 / 74 / 99 frames at 160 px, 66 / 71 / 97 at 200 and 300 px, peak 75 -> 69 px)
    if f and f['frames'] and not f['hit'] and not air: return f['frames'], [tuple(s) for s in f['seq']], f'SS2 {FAR} px'
    if f is None and not taken: return None, None, 'not taken'
    return None, None, 'SS2 hits (no whiff)'

def table(before, after, od):
    import handlers_ss2 as H
    B0, B1 = json.load(open(before)), json.load(open(after))
    chk = H.check(tuple(CHAR))
    rows, lines = [], []
    hdr = f'{"fighter":9s} {"move":10s} {"row":3s} {"SS2":>4s} {"source":20s} {"before":>6s} {"after":>5s} {"diff":>4s}  steps (after: frames on SS2 frame / compared)'
    lines.append(hdr)
    for name in CHAR:
        ss = json.load(open(f'{WORK}/ss2/{name}.json'))
        ex = json.load(open(os.path.join(GAME, 'build', f'tmp_samsho2_{name}', 'kof95_export.json')))['characters'][name]
        fmap = {}
        for sp in ex['specials']:
            for k, a in sp['rom']['anims'].items():
                for s in a['steps']: fmap.setdefault((sp['input'], tuple(s['ss2'])), s['frame'])
        import handlers_ss2 as H2
        for inp, (fn, nv, results) in H2.SPECIALS[name].items():
            for v in range(nv):
                b0 = next(x for x in B0[name]['specials'][inp] if x['v'] == v)
                b1 = next(x for x in B1[name]['specials'][inp] if x['v'] == v)
                n, seq, src = ss2_ref(name, inp, v, results[v], ss['specials'])
                c = chk.get(f'{name} {inp} {"ABC"[v] if nv > 1 else ""}')
                if n is None and src == 'not taken': n, src = c['length'], 'decoded (never taken)'
                elif n is None and isinstance(c, dict): n, src = c['length'], f'decoded (hits at {c["game_frames"]})'
                same = cmp = None
                if seq:                              # from the start frame (SS2's first frame; the brawler's start
                    want = [fmap.get((inp, tuple(s))) for s in seq]   # frame shows no step yet: from frame 1)
                    got = b1['frame_seq']
                    cmp = min(len(want), len(got)) - 1
                    same = sum(1 for k in range(1, cmp + 1) if want[k] == got[k])
                row = dict(fighter=name, move=inp, row='ABC'[v] if nv > 1 else '', ss2=n, source=src, before=b0['frames'],
                           after=b1['frames'], diff_before=None if n is None else b0['frames'] - n,
                           diff_after=None if n is None else b1['frames'] - n, steps_same=same, steps_compared=cmp)
                rows.append(row)
                lines.append(f'{name:9s} {inp:10s} {row["row"]:3s} {n if n is not None else "-":>4} {src:20s} {b0["frames"]:>6} {b1["frames"]:>5} '
                             f'{row["diff_after"] if n is not None else "-":>4}  ' + (f'{same}/{cmp}' if seq else ''))
        for keys, x in B1[name]['normals'].items():
            x0 = B0[name]['normals'][keys]
            nm = next((cn for mv, cn in NORMALS.items() if mv == x['move']), None)
            n = ss['normals'][x['move']]['frames'] if x['move'] in ss['normals'] else x['ss2_len']
            src = f'SS2 capture {nm}' if nm else f'SS2 anim {x["ss2_anim"]} length'
            rows.append(dict(fighter=name, move=f'normal {keys} ({x["move"]})', ss2=n, source=src, before=x0['frames'],
                             after=x['frames'], diff_before=x0['frames'] - n, diff_after=x['frames'] - n))
            lines.append(f'{name:9s} {"A " + keys:10s} {"":3s} {n:>4} {src[:20]:20s} {x0["frames"]:>6} {x["frames"]:>5} {x["frames"] - n:>4}  {x["move"]}')
    os.makedirs(od, exist_ok=True)
    json.dump({'rows': rows, 'check': chk}, open(os.path.join(od, 'timing191.json'), 'w'), indent=1)
    open(os.path.join(od, 'timing191.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'ss2':
        os.makedirs(f'{WORK}/ss2', exist_ok=True)
        for n in sys.argv[2:] or list(CHAR):
            r = ss2_whiffs(n); json.dump(r, open(f'{WORK}/ss2/{n}.json', 'w'))
            for inp, rows in r['specials'].items(): print(n, inp, [(x['v'], x['frames'], x.get('hit')) for x in rows], flush=True)
            for mv, x in r['normals'].items(): print(n, mv, x['frames'], x['hit'])
    elif cmd == 'brawler':
        json.dump(brawler(sys.argv[3:] or list(CHAR)), open(sys.argv[2], 'w'))
    elif cmd == 'table':
        table(sys.argv[2], sys.argv[3], sys.argv[4])
