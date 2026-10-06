#!/usr/bin/env python3
"""Hanzou's special sounds (TODO #181) in the brawler vs World Heroes Perfect's own sound log, both in our emulator.

    python3 sound_proof.py OUTDIR      (a built examples/brawler; BRAWLER_CORE = the Geolith core)

WHP: every exported special's three rows (low / mid / high, moves_whp.specials, specials_check's whiff recipes), the
fury (the hero rising $122: handlers_whp sr_whiff / sr_hit) and its MAX (the hero DM $12A: dmh_whiff / dmh_hit) played
from the vs state with SNDLOG: the bytes written to REG_SOUND ($FC + a byte = one word), each word with the frame its
first byte was written (log frame + 1; frame 0 = the move's first animation frame) and Hanzou's animation / step then.
The brawler: the same move in the Chain Lab training (P1 Hanzou, the dummy out of reach: whiff; at point blank: close),
the row forced (fighter_t.var poked before the program's first frame), every voice the game queued (P1's voice prefix +
code -> his voice id -> voices.json word; fx voices on the other prefix), its frame from the special's first update and
the script row it was sent on (a scripted move: export row_steps -> WHP animation / step).
The steps: the brawler's program step each frame = the model's (handlers_whp.play, frame-identical to WHP:
specials_check), from the special's first update. Checked: the words of his bank (voices.json hanzo: his voices and own effects) WHP sends, in order, = the brawler's;
a program special (frame-identical to WHP, specials_check) at the same frames; a scripted one (the fury held through
the brawler's super flash, the MAX's ninja sequence) on the same WHP steps. WHP's other words (the common landing $51,
swings $0B, the launch $65, hit sounds, the victim's cries) are listed, not played by the brawler (no move plays them).
-> OUTDIR/sound_proof.json, a line per move and row"""
import json, os, sys, subprocess
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import cap_whp as cap, specials_check as SC, moves_whp as MW, handlers_whp as H, export_whp as E
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
NAME = 'hanzo'
WORK = '/data/tmp/whp181'
BANK = {int(v['cmd'], 16): v for v in json.load(open(os.path.join(HERE, '..', 'brawler', 'voices.json')))['fighters'][NAME]['voices']}

def words_of(log):
    """[(frame of the first byte, word)]: $FC + the next byte = one word"""
    out, k = [], 0
    while k < len(log):
        f, b = log[k]
        if b == 0xFC and k + 1 < len(log): out.append((f, 0xFC00 | log[k + 1][1])); k += 2
        else: out.append((f, b)); k += 1
    return out

def sndlog(path): return [(int(l.split()[0]), int(l.split()[1], 16)) for l in open(path)]

def whp_special(args):
    sp, row = args
    inp = E.special_input(sp); d = os.path.join(WORK, f'{inp}_{row["button"]}'); os.makedirs(d, exist_ok=True)
    seq, seq2 = SC.recipe(sp, row)
    rows = cap.run(seq, seq2, span=0x200, extra={'SNDLOG': os.path.join(d, 'snd.txt')})
    p1 = {r['f']: cap.obj(r, 0) for r in rows}
    f0 = next(f for f in sorted(p1) if p1[f]['anim'] - p1[f]['base'] == row['rel'])
    n = len(H.play(NAME, row['rel'], first_ticks=inp in E.FIRST_TICKS, maxf=400))   # the move until neutral
    ws = []
    for f, w in words_of(sndlog(os.path.join(d, 'snd.txt'))):
        k = f + 1 - f0                                   # (a write in frame n is logged as n - 1)
        if 0 <= k < n:
            o = p1.get(f + 1); ws.append([k, f'{w:04X}', [o['anim'] - o['base'], o['step']] if o else None])
    return (inp, row['button']), {'strength': row['strength'], 'frames': n, 'sent': ws}

def whp_fury(rec):
    seq, seq2 = H.RECIPES[rec][:2]
    n = max(cap.nframes(seq), cap.nframes(seq2) if seq2 else 0)
    d = os.path.join(WORK, f'fury_{rec}'); os.makedirs(d, exist_ok=True)
    rd = ';'.join(f'{f}:100000:100;{f}:106000:100' for f in range(1, n))
    env = dict(os.environ, SEQ=seq, SEQ2=seq2, OUT=f'{d}/cap.txt', LOAD=cap.VS, RAMDUMP=rd, POKE=H.pokes(rec), SNDLOG=d + '/snd.txt')
    subprocess.run([cap.NGSDL, cap.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    p1 = {}
    for f in range(1, n):
        p = f'{d}/cap.txt.ram{f}_100000'
        if not os.path.exists(p): continue
        o = cap.parse(open(p).read()); a = cap.parse(open(f'{d}/cap.txt.ram{f}_106000').read())
        p1[f] = [cap.u16(a, 0xDA) - cap.u16(o, 0x64), a[0xDC]]
    rel = H.REL[H.rec_move(rec)]
    f0 = next(f for f in sorted(p1) if p1[f][0] == rel)
    # the step that sent a word: the last step entered by then whose entry carries it (command 4): ADK's driver takes
    # one byte a frame, so a step's second send ($FCA8 then $39: 3 bytes) is written frames after the step started
    def sender(f, w):
        for g in range(f, f0 - 1, -1):
            a, s = p1.get(g) or (None, None)
            if a is None or (g - 1 in p1 and p1[g - 1] == [a, s]): continue
            if any(c == 4 and int(x, 16) == w for c, x in H.entries(H.CHARS[NAME], a)[s].get('cmds') or []): return [a, s]
        return None
    ws = [[f + 1 - f0, f'{w:04X}', sender(f + 1, w), p1.get(f + 1)] for f, w in words_of(sndlog(d + '/snd.txt')) if f + 1 >= f0]
    return rec, {'sent': ws}

def brawler_runs(jobs):
    """jobs: [(input, row or None, keys, case)] -> {job: [[frame, word, script row], ...]}"""
    import harness
    G = json.load(open(os.path.join(GAME, 'game.json'))); names = [r['name'] for r in G['roster']]
    rep = json.load(open(os.path.join(GAME, 'build', 'snd', 'snd_report.json')))['voices']
    lab = {f['name']: f for f in json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))['fighters']}
    ov = rep.get('overflow') or {'prefixes': []}
    P1 = {int(rep['prefixes'][0], 16): 0} | ({int(ov['prefixes'][0], 16): 0x100} if ov['prefixes'] else {})
    P1E = {int(rep['prefixes'][1], 16): 0} | ({int(ov['prefixes'][1], 16): 0x100} if len(ov['prefixes']) > 1 else {})
    code_of = {int(c): int(i) for i, c in rep['fighters'][NAME]['codes'].items()}
    ids = {v['id']: k for k, v in BANK.items()}
    b = harness.Brawler(game=GAME); S = b.syms
    for _ in range(400): b.core.retro_run()
    from chainlab.labdrive import PACK_OFF
    L = S['lab']; MAP = L + PACK_OFF
    for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
    fi = names.index(NAME); pool = [p['input'] for p in lab[NAME]['pool']]
    out = {}
    for job in jobs:
        inp, row, keys, case = job
        b.w(L + 5, 1, fi); b.w(L + 6, 1, names.index('terry')); b.w(L + 4, 1, 1)
        b.run(30)
        b.w(S['spec_tab'] + 4 * fi, 4, MAP)
        for j in range(6): b.w(MAP + j, 1, pool.index(inp) if j == 0 else 0xFF)
        b.fset(0, 'meter', 120); b.fset(0, 'facing', 1)
        if case == 'close': b.place(2, x=b.fget(0, 'x') + 34, z=b.fget(0, 'z'))
        else: b.place(2, x=b.fget(0, 'x') + 260, z=b.fget(0, 'z') + 40)
        b.run(2)
        f0 = end = None; sent = []; srows = {}; steps = []; oqt = b.r(S['qt'], 1); poked = None
        for f in range(700):
            b.run(1, p1=keys if f < 3 else '')
            qt = b.r(S['qt'], 1)
            while oqt != qt: sent.append((b.frame, b.r(S['q'] + oqt, 1))); oqt = (oqt + 1) & 31
            st = b.states[b.fget(0, 'state')]
            if f0 is None and st == 'SPECIAL':
                f0 = b.frame; poked = b.fget(0, 'srow')
                assert b.fget(0, 'spec_ix') == pool.index(inp), (job, b.fget(0, 'spec_ix'))
                if row is not None: b.fset(0, 'var', row)
            if f0 is not None and end is None and st != 'SPECIAL': end = b.frame
            srows[b.frame] = b.fget(0, 'srow') if st == 'SPECIAL' else None
            if f0 is not None and end is None: steps.append(b.fget(0, 'pstep'))
            if end is not None and b.frame > end + 40: break
        ws, want = [], None
        for fr, v in sent:
            if want is not None:
                i = code_of.get(v | want[0])
                if i and f0 is not None and fr >= f0 and (not want[2] or BANK[ids[i & 0x7F]].get('channel') == 'fx'):
                    sr = srows.get(want[1])
                    ws.append([want[1] - f0 - 1, f'{ids[i & 0x7F]:04X}', sr - 1 if sr else None])
                want = None
            elif v in P1: want = (P1[v], fr, 0)
            elif v in P1E: want = (P1E[v], fr, 1)
        out[job] = {'sent': ws, 'srow_at_poke': poked, 'frames': (end or b.frame) - f0 if f0 else None, 'steps': steps}
    return out

def main(od):
    os.makedirs(od, exist_ok=True); os.makedirs(WORK, exist_ok=True)
    ex = json.load(open(os.path.join(GAME, 'build', f'tmp_whp_{NAME}', 'kof95_export.json')))['characters'][NAME]
    exsp = {s['input']: s for s in ex['specials']}
    sps = [sp for sp in MW.specials(H.ROWS[NAME], H.CHARS[NAME]) if E.special_input(sp) in exsp]
    with ThreadPoolExecutor(1) as tp:
        whp = dict(tp.map(whp_special, [(sp, r) for sp in sps for r in sp['rows']]))
        fury = dict(tp.map(whp_fury, ['sr_whiff', 'sr_hit', 'dmh_whiff', 'dmh_hit']))
    G = json.load(open(os.path.join(GAME, 'game.json'))); fury_inp = next(r for r in G['roster'] if r['name'] == NAME)['fury']
    jobs = [(E.special_input(sp), v, 'c', 'whiff') for sp in sps for v in range(len(sp['rows']))]
    jobs += [(fury_inp, None, 'd', c) for c in ('whiff', 'close')] + [('MAX ' + fury_inp, None, 'Dd', c) for c in ('whiff', 'close')]
    br = brawler_runs(jobs)
    res, ok_all = {'specials': {}, 'furies': {}}, True
    for sp in sps:
        inp = E.special_input(sp)
        for v, r in enumerate(sp['rows']):
            w = whp[(inp, r['button'])]; g = br[(inp, v, 'c', 'whiff')]
            ours = [[k, x] for k, x, _ in g['sent']]
            want = [[k, x] for k, x, _ in w['sent'] if int(x, 16) in BANK]
            # the steps shown: the brawler's program step (fighter_t.pstep, from its first update) = the run of the
            # model's frame (export_whp: a step per run of (anim, step, def)); the Koryuu Ha's steps are its animation's
            mod = H.play(NAME, r['rel'], first_ticks=inp in E.FIRST_TICKS, maxf=400)
            run, j = [], -1
            for i, q in enumerate(mod):
                key = (q['anim'], q['step']) if inp == '236P' else (q['anim'], q['step'], q['defw'])
                if i == 0 or key != prev: j += 1
                prev = key; run.append(q['step'] if inp == '236P' else j)
            got = g['steps'][1:len(run) + 1]
            step_bad = [[k, a, c] for k, (a, c) in enumerate(zip(got, run)) if a != c]
            ok = ours == want and g['srow_at_poke'] == 0 and not step_bad and len(got) == len(run)
            ok_all &= ok
            res['specials'][f'{inp}:{r["button"]}'] = {'strength': r['strength'], 'ok': ok, 'whp_bank_sends': want, 'brawler_sends': ours,
                                                       'whp_all_sends': w['sent'], 'brawler_frames': g['frames'], 'whp_frames': w['frames'],
                                                       'steps_compared': len(got), 'step_mismatches': step_bad[:5]}
            print(f'{inp:7s} {r["button"]:2s} {r["strength"]:4s}', 'OK  ' if ok else 'DIFF', 'whp', want, 'brawler', ours,
                  f'| steps {len(got) - len(step_bad)}/{len(run)}', '| not played:', [x for k, x, _ in w['sent'] if int(x, 16) not in BANK], flush=True)
    rs = {s: exsp[s]['row_steps'] for s in (fury_inp, 'MAX ' + fury_inp)}
    for inp, recs in ((fury_inp, ('sr_whiff', 'sr_hit')), ('MAX ' + fury_inp, ('dmh_whiff', 'dmh_hit'))):
        for case, rec in zip(('whiff', 'close'), recs):
            g = br[(inp, None, 'd' if inp == fury_inp else 'Dd', case)]
            ours = [[x, rs[inp][r][:2] if r is not None and r < len(rs[inp]) else None, k] for k, x, r in g['sent']]
            want = [[x, st, k] for k, x, st, _ in fury[rec]['sent'] if int(x, 16) in BANK]   # [word, the step that sent it, frame]
            ok = [o[:2] for o in ours] == [x[:2] for x in want]
            ok_all &= ok
            res['furies'][f'{inp} {case}'] = {'whp_capture': rec, 'ok': ok, 'whp_bank_sends': want, 'brawler_sends': ours,
                                              'whp_all_sends': fury[rec]['sent']}
            print(f'{inp} {case:5s}', 'OK  ' if ok else 'DIFF', 'whp [word, step, frame]', want, 'brawler', ours, flush=True)
    res['ok'] = ok_all
    json.dump(res, open(os.path.join(od, 'sound_proof.json'), 'w'), indent=1)
    print('ALL OK' if ok_all else 'DIFFERENCES', '->', os.path.join(od, 'sound_proof.json'))

if __name__ == '__main__':
    main(sys.argv[1])
