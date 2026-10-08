#!/usr/bin/env python3
"""Proof of Bruno's new system (2026-10-08, docs/brawler_gold.md "Bruno's live redesign"; docs/brawler_data_model.md "The new
system"), our emulator (harness.py + the Chain Lab's training mode: chainlab/labdrive.py, P1 vs a dummy that never attacks
unless this script drives it), the real build. Test-only pokes: positions, P1's drive / fury gauge / life, the dummy's
intent (a hit on P1), extra standing dummies (copies, scenario.py's way).

    python3 newsys_proof.py OUT_DIR [SECTION ...]       sections: arc walk terry meter (default all)

arc    one jump for everyone: Terry / Kim / Krauser straight + forward jumps per frame (height, x from the take-off) vs Cody's
       Final Fight arc (/data/tmp/newsys/out/ff_cody_jump.json, captured by ff_jump.py in /data/emu's FBNeo): same frames,
       same heights in lines, x x 320 / 384; arc.md (frame table), arc_<fighter>_<kind>.png (every 2nd frame)
walk   walk / run speeds by archetype (Kim fast, Terry balanced, Krauser heavy), steady state over 60 frames, and the walk
       animation's rate (fighter_t.wrate: the feet's stride kept)
terry  Terry's move sheet: the chain + every finisher (both facings), each Blitz, each C special (and 0 chunks: nothing),
       the ladder (chain -> finisher -> Blitz -> special -> another special -> fury) on one dummy and through a crowd, the
       breaker with / without drive (always the neutral C special; white / red blink), the blink states (fury ready: shiny
       1 / 1, MAX ready: red 1 / 1) and D's fury / MAX, the air attacks (+ the down+A -> jump attack cancel), A+B = C
       (same frame, late), the hold's forward + C = the plain throw (the super throw dropped)
meter  the drive: spend (a special 1 chunk, the breaker 2), refill (a chunk in 240 frames); the fury gauge: fill by
       damage dealt and taken, emptied by the fury
Writes OUT_DIR/newsys.json (every check, ok flags) and the sheets."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
from labdrive import Lab, PACK_STAT_OFF
import export_bm
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
SECTIONS = sys.argv[2:] or ['arc', 'walk', 'terry', 'meter']
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
G = json.load(open(os.path.join(GAME, 'game.json'))); M = G['meter']; J = G['jump']; W = G['walk']; BZ = G['blitz']
CL = json.load(open(os.path.join(GAME, 'build', 'chainlab.json')))
NAMES = [r['name'] for r in G['roster']]
MOVES = export_bm.MOVES
BS_FURY, BS_BLITZ = 6, 12
INV_FURY = 0xFF
OVL = {0: '-', 1: 'white', 2: 'red', 3: 'shiny'}
DFULL = M['chunk'] * M['chunks']
L = Lab(); b = L.b; ST = b.states
RES = {}

def st(i=0): return ST[b.fget(i, 'state')]
def pool(name): return [p['input'] for p in CL['fighters'][NAMES.index(name)]['pool']]
BASE = {}
def start(name, dummy='ryo'):
    if name not in BASE:
        L.start(NAMES.index(name), NAMES.index(dummy)); b.run(30); BASE[name] = b.save()
    b.load(BASE[name])
def reset(name, dist=60, face=1, drive=None, fury=None, hp=None, extra=(), dz=0):
    start(name)
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 160
    b.w(L.lab + PACK_STAT_OFF + 1, 1, 1 if hp is not None else 0)   # lab.p1_life: P1's life left to the game
    b.place(0, x=x0, z=30); b.fset(0, 'facing', face & 0xFF)
    b.place(2, x=x0 + face * dist, z=30 + dz); b.fset(2, 'facing', -face & 0xFF); b.fset(2, 'hp', 60)
    for k, dx in enumerate(extra):                        # copies of the dummy standing at dx (scenario.py's way)
        i = 3 + k; src = b.base + 2 * b.fsize; dst = b.base + i * b.fsize
        for o in range(b.fsize): b.w(dst + o, 1, b.r(src + o, 1))
        b.fset(i, 'idx', i); b.fset(i, 'x', x0 + face * dx); b.fset(i, 'z', 30); b.fset(i, 'facing', -face & 0xFF)
    b.fset(0, 'drive', DFULL if drive is None else drive); b.fset(0, 'fgauge', fury or 0)
    if hp is not None: b.fset(0, 'hp', hp)
    b.run(2)

def what(i=0):
    s = st(i)
    if s == 'SPECIAL':
        sid = b.fget(i, 'spec_id'); six = b.fget(i, 'spec_ix')
        return f"SPECIAL {'blitz ' if sid == BS_BLITZ else 'fury ' if sid == BS_FURY else ''}{CUR_POOL[six] if six < len(CUR_POOL) else six}"
    if s in ('ATTACK', 'AIR_ATTACK'): return f'{s} {MOVES[b.fget(i, "anim")]}'
    return s
CUR_POOL = []

class Rec:
    """frames played with a log (P1's moves as they start, every hit on the dummies) and pictures every `every` frames"""
    def __init__(s, every=0, tag='', cap=36):
        s.ev = []; s.prev = None; s.hp = {i: b.fget(i, 'hp') for i in (2, 3, 4, 5)}; s.f = 0; s.hits = []; s.every = every
        s.shots = []; s.tag = tag; s.rows = []; s.moves = []; s.node = None; s.cap = cap; s.keys = []
    def step(s, keys=''):
        if s.every and s.f % s.every == 0 and len(s.shots) < s.cap:
            p = os.path.join(OUT, f'_{s.tag}_{s.f:04d}.png'); b.pad = [set(keys.replace('-', '')), set()]; b.screenshot(p)
            s.shots.append((p, s.f, what()))
        else: b.run(1, p1=keys)
        s.f += 1; s.keys.append(keys or '-')
        w = what()
        if w != s.prev: s.ev.append((s.f, keys, w)); s.prev = w
        nd = (st(0), b.fget(0, 'node')) if st(0) in ('ATTACK', 'THROW') else None   # P1's moves, one per node started
        if nd and nd != s.node: s.moves.append(MOVES[b.fget(0, 'anim')] if nd[0] == 'ATTACK' else 'THROW')
        s.__dict__.setdefault('trans', []); s.__dict__.setdefault('_f', 0); s._f += 1
        if not s.trans or s.trans[-1][1] != st(0): s.trans.append((s._f, st(0)))
        s.node = nd
        for i in s.hp:
            h = b.fget(i, 'hp')
            if h < s.hp[i]:
                s.hits.append(dict(f=s.f, who=i, dmg=s.hp[i] - h, by=w, victim=st(i), vy=round(b.fget(i, 'y'))))
                s.ev.append((s.f, keys, f'HIT dummy{i} {s.hp[i] - h} -> {st(i)} y{b.fget(i, "y"):.0f}'))
            s.hp[i] = h
        s.rows.append(dict(f=s.f, st=st(0), what=w, x=round(b.fget(0, 'x'), 2), y=round(b.fget(0, 'y'), 2), inv=b.fget(0, 'inv'),
                           drive=b.fget(0, 'drive'), fg=b.fget(0, 'fgauge'), ovl=b.fget(0, 'ovl'), hp=b.fget(0, 'hp'), d_st=st(2)))
    def keystr(s):                                        # the keys played, as a scenario's "frames:keys,..." string
        out = []
        for k in s.keys:
            if out and out[-1][1] == k: out[-1][0] += 1
            else: out.append([1, k])
        return ','.join(f'{n}:{k}' for n, k in out)
    def seq(s, q):
        for part in [p for p in q.split(',') if p]:
            n, k = part.split(':')
            for _ in range(int(n)): s.step(k)
    def until(s, cond, n=120):
        for _ in range(n):
            if cond(): return True
            s.step()
        return cond()
    def until_hit(s, n=120):
        h = len(s.hits); return s.until(lambda: len(s.hits) > h, n)
    def idle(s, n=400): return s.until(lambda: st(0) == 'IDLE' and not b.fget(0, 'freeze'), n)
    def sheet(s, path, title=''):
        if not s.shots: return
        ims = [Image.open(p) for p, _, _ in s.shots]; w, h = ims[0].size; cols = 6
        S = Image.new('RGB', (cols * w, 18 + ((len(ims) + cols - 1) // cols) * (h + 14)), 'white'); d = ImageDraw.Draw(S)
        d.text((4, 3), title, fill='black')
        for k, (im, (_, f, wh)) in enumerate(zip(ims, s.shots)):
            x, y = k % cols * w, 18 + k // cols * (h + 14); S.paste(im, (x, y + 14)); d.text((x + 2, y + 1), f'+{f} {wh}'[:52], fill='black')
        S.save(path)
        for p, _, _ in s.shots: os.remove(p)
        s.shots = []

# ---- arc -------------------------------------------------------------------------------------------------------------
def arc():
    ff = json.load(open('/data/tmp/newsys/out/ff_cody_jump.json'))
    sx = J['x_scale'][0] / J['x_scale'][1]
    res = RES['arc'] = {}
    md = ['# One jump for everyone: Cody (Final Fight, captured) vs the brawler', '',
          'Frame 1 = the jump press. FF: Cody\'s height (lines) and x from the press (CPS1 px); scaled = x x 320 / 384; then each',
          'fighter\'s height and x from the press frame, in our emulator. ok = same height, x within 0.02 px of the scaled.', '']
    for name in ('terry', 'kim', 'krauser'):
        for kind, keys in (('straight', 'b'), ('forward', 'Rb')):
            global CUR_POOL; CUR_POOL = pool(name)
            reset(name, dist=300)
            x0 = b.fget(0, 'x'); r = Rec(every=2, tag=f'arc_{name}_{kind}')
            r.step(keys)
            for _ in range(60): r.step('')
            k0 = next(k for k, w in enumerate(r.rows) if w['st'] != 'IDLE')   # the game's press frame (the pad is read a frame
                                                                    # later than the harness sets it): FF's frame 1
            rows = [dict(f=k + 1, st=w['st'], h=w['y'], x=round(w['x'] - x0, 2)) for k, w in enumerate(r.rows[k0:])]
            fr = {w['f']: w for w in ff[kind]}
            bad = []
            for w in rows[:52]:
                f0 = fr[w['f']]
                want_x = round((f0['x']) * sx, 2)
                if abs(w['h'] - f0['h']) > 0.01 or abs(w['x'] - want_x) > 0.05: bad.append((w['f'], w['h'], f0['h'], w['x'], want_x))
            air = [w['f'] for w in rows if w['h'] > 0]
            res[f'{name}_{kind}'] = dict(air=[air[0], air[-1], len(air)] if air else None, peak=max(w['h'] for w in rows),
                                         dx=rows[air[-1]]['x'] if air else 0, mismatches=bad[:6], ok=not bad and len(air) == 41)
            r.sheet(os.path.join(OUT, f'arc_{name}_{kind}.png'), f'{name} {kind} jump: every 2nd frame from the press')
            if name == 'terry':
                md += [f'## {kind} jump', '', '| frame | FF state | FF height | FF x | FF x scaled | Terry state | Terry height | Terry x |', '|---|---|---|---|---|---|---|---|']
                for w in rows[:52]:
                    f0 = fr[w['f']]
                    md.append(f"| {w['f']} | {f0['st']:x}/{f0['sub']:x} | {f0['h']} | {f0['x']:.2f} | {f0['x'] * sx:.2f} | {w['st']} | {w['h']:.0f} | {w['x']:.2f} |")
                md.append('')
            print('arc', name, kind, res[f'{name}_{kind}'], flush=True)
    md += ['## Every fighter', '', '| fighter / jump | air frames (first, last, count) | peak | x at landing | ok |', '|---|---|---|---|---|']
    md += [f"| {k} | {v['air']} | {v['peak']} | {v['dx']} | {v['ok']} |" for k, v in res.items()]
    open(os.path.join(OUT, 'arc.md'), 'w').write('\n'.join(md) + '\n')

# ---- walk ------------------------------------------------------------------------------------------------------------
def walk():
    res = RES['walk'] = {}
    for name, arch in (('kim', 'fast'), ('terry', 'balanced'), ('krauser', 'heavy')):
        reset(name, dist=400); cam = b.r(b.syms['cam_x'], 2); b.place(0, x=cam + 30); b.run(1)
        b.run(10, p1='R'); x0 = b.fget(0, 'x'); b.run(60, p1='R'); v = (b.fget(0, 'x') - x0) / 60   # (a steady walk: 10 frames in)
        rate = b.fget(0, 'wrate')
        b.run(20)
        reset(name, dist=400); b.place(0, x=cam + 20); b.run(1)
        b.seq('1:R,1:-,1:R'); b.run(6, p1='R'); s0 = st(0); x0 = b.fget(0, 'x'); b.run(40, p1='R'); vr = (b.fget(0, 'x') - x0) / 40
        res[name] = dict(archetype=arch, walk=round(v, 4), want=W[arch], run=round(vr, 4), want_run=W[arch] * W['run'], run_state=s0,
                         anim_rate=round(rate / 256, 3), ok=abs(v - W[arch]) < 0.01 and abs(vr - W[arch] * W['run']) < 0.02 and s0 == 'RUN')
        print('walk', name, res[name], flush=True)

# ---- terry -----------------------------------------------------------------------------------------------------------
def chain(fin, face, tag=None, dist=44):
    """Terry's chain: A every other frame to the third link's hit, then the finisher (stick + A) -> moves started, hits"""
    reset('terry', dist=dist, face=face)
    f = {1: 'R', -1: 'L'}; b_ = {1: 'L', -1: 'R'}
    stick = {'neutral': '', 'forward': f[face], 'up': 'U', 'down': 'D', 'back': b_[face]}[fin]
    r = Rec(every=3 if tag else 0, tag=tag or 'x')
    for k in range(3):
        r.seq('1:a,1:-')
        if not r.until_hit(40): break
    r.seq(f'1:{stick}a,1:-')
    r.until(lambda: st(0) in ('THROW',) or len(r.hits) >= 4, 60)
    r.idle(300)
    return r, r.moves

FIN_WANT = {'neutral': ('atk_d_close', ('KNOCKDOWN',)), 'forward': ('cmd_fwd_a', ('KNOCKDOWN',)), 'up': ('cmd_df_c', ('KNOCKDOWN',)),
            'down': ('atk_d_crouch', ('KNOCKDOWN',)), 'back': ('THROW', ('THROWN', 'DOWN', 'KNOCKDOWN'))}
def terry():
    global CUR_POOL
    CUR_POOL = pool('terry'); res = RES['terry'] = {}
    # chain + finishers, both facings
    ch = res['chain'] = {}
    for face in (1, -1):
        for fin in FIN_WANT:
            r, moves = chain(fin, face, tag=f'chain_{fin}_{face}')
            want = ['atk_a_far', 'atk_a_far', 'atk_c_close', FIN_WANT[fin][0]]
            fin_hit = [h for h in r.hits if h['by'].endswith(FIN_WANT[fin][0]) or (fin == 'back' and h['by'] == 'THROW')]
            vend = r.ev and [w for _, _, w in r.ev]
            ok = moves[:4] == want and len(r.hits) >= 4 and (sum(h['dmg'] for h in r.hits) == 23 if fin != 'back' else   # (the
                                                                    # chain's 23; back: 3 links, then the throw)
                                                             any(h['victim'] == 'THROWN' for h in r.hits))
            ch[f'{fin}_{"right" if face > 0 else "left"}'] = dict(moves=moves, hits=[(h['dmg'], h['victim']) for h in r.hits],
                                                                   damage=sum(h['dmg'] for h in r.hits), ok=ok and bool(fin_hit or fin == 'back'))
            r.sheet(os.path.join(OUT, f'terry_chain_{fin}_{"right" if face > 0 else "left"}.png'),
                    f'Terry chain far A > far A > close C > {fin} finisher, facing {"right" if face > 0 else "left"}: every 3rd frame')
            print('chain', fin, face, ch[f'{fin}_{"right" if face > 0 else "left"}'], flush=True)
    # the Blitz: each slot from neutral (free, not invincible)
    bz = res['blitz'] = {}
    for slot, q, want, dist in (('ff', '1:R,1:-,1:R,1:Ra', 'ATTACK body_toss', 60), ('dd', '1:D,1:-,1:D,1:Da', 'SPECIAL blitz 426B', 70),
                                ('du', '1:D,1:-,1:U,1:Ua', 'SPECIAL blitz 214D', 70), ('uu', '1:U,1:-,1:U,1:Ua', 'SPECIAL blitz 236C', 120)):
        reset('terry', dist=dist)
        r = Rec(every=3, tag=f'blitz_{slot}'); r.seq(q); r.until(lambda: st(0) in ('ATTACK', 'SPECIAL'), 10)
        started = what(); invs = []
        while st(0) in ('ATTACK', 'SPECIAL') and r.f < 200: invs.append(b.fget(0, 'inv')); r.step()
        r.idle()
        bz[slot] = dict(started=started, want=want, drive_after=b.fget(0, 'drive'), hits=[(h['dmg'], h['victim']) for h in r.hits],
                        invincible_frames=sum(v == INV_FURY for v in invs),
                        ok=started == want and b.fget(0, 'drive') == DFULL and not any(v == INV_FURY for v in invs) and bool(r.hits))
        r.sheet(os.path.join(OUT, f'terry_blitz_{slot}.png'), f'Terry Blitz {slot} + A: {want}')
        print('blitz', slot, bz[slot], flush=True)
    # a double tap without A: depth walking untouched
    reset('terry', dist=200); z0 = b.fget(0, 'z'); r = Rec(); r.seq('1:D,1:-,1:D,20:D'); bz['depth_walk'] = dict(dz=round(b.fget(0, 'z') - z0, 2), state=st(0),
                                                                                                       ok=st(0) == 'WALK' and b.fget(0, 'z') - z0 > 15)
    # C specials (+ the stick), a chunk each, invincible; 0 chunks: nothing
    sp = res['specials'] = {}
    for d, want in (('', '623C'), ('R', '623D'), ('D', '214C'), ('U', '623C'), ('DR', '623C'), ('UR', '623C')):
        reset('terry', dist=60)
        r = Rec(every=4 if d in ('', 'R', 'D') else 0, tag=f'sp_{d or "n"}'); r.seq(f'1:{d}c'); r.until(lambda: st(0) == 'SPECIAL', 6)
        got = what(); invs = []
        while st(0) == 'SPECIAL' and r.f < 300: invs.append(b.fget(0, 'inv')); r.step()
        r.idle()
        sp[d or 'neutral'] = dict(got=got, want=f'SPECIAL {want}', drive_after_start=r.rows[1]['drive'] if len(r.rows) > 1 else None,
                                  invincible=f'{sum(v == INV_FURY for v in invs)}/{len(invs)}', hits=[(h['dmg'], h['victim']) for h in r.hits],
                                  ok=got == f'SPECIAL {want}' and invs and all(v == INV_FURY for v in invs[:-1]) and r.rows[1]['drive'] in (DFULL - M['chunk'], DFULL - M['chunk'] + 1))
        if d in ('', 'R', 'D'): r.sheet(os.path.join(OUT, f'terry_special_{d or "n"}C.png'), f'Terry {d or "neutral"} + C: {want} (a chunk, invincible)')
        print('special', d or 'n', sp[d or 'neutral'], flush=True)
    reset('terry', dist=60); b.fset(0, 'drive', M['chunk'] - 3); r = Rec(); r.seq('1:c'); r.step(); r.step()   # (a point back a
    sp['no_drive'] = dict(state=st(0), drive=b.fget(0, 'drive'), ok=st(0) != 'SPECIAL')                         # frame)
    reset('terry', dist=60); b.fset(0, 'drive', M['chunk']); r = Rec(); r.seq('1:c'); r.until(lambda: st(0) == 'SPECIAL', 4)
    sp['one_chunk'] = dict(state=st(0), drive=b.fget(0, 'drive'), ok=st(0) == 'SPECIAL' and b.fget(0, 'drive') <= 4)
    print('special no drive', sp['no_drive'], sp['one_chunk'], flush=True)
    # the ladder
    res['ladder'] = ladder()
    # the breaker
    res['breaker'] = breaker()
    # blink states, D's fury / MAX
    res['blink'] = blink()
    # air attacks
    res['air'] = air()
    # A+B = C, the hold's forward + C
    res['chord'] = chord()

def ladder():
    out = {}
    # one dummy: the best measured (newsys ladder search: chain, neutral finisher, dd Blitz 426B, 623C, 214C, then D)
    reset('terry', dist=60, fury=M['fury_max'])
    r = Rec(every=5, tag='ladder1', cap=60)
    for k in range(3): r.seq('1:a,1:-'); r.until_hit(40)
    r.seq('1:a,1:-'); r.until_hit(40)
    rungs = ['chain + finisher']
    for name, q in (('Blitz dd (426B)', '1:D,1:-,1:D,1:Da'), ('special 623C', '1:c'), ('special 214C', '1:Dc'), ('fury', '1:d')):
        w0 = what(); r.seq(q)
        r.until(lambda: what() != w0 and st(0) == 'SPECIAL', 60)
        started = what()
        hit = r.until_hit(90)
        rungs.append(f'{name}: {started}, {"hit" if hit else "no hit"}')
    r.idle(400)
    out['one_dummy'] = dict(rungs=rungs, events=[e for e in r.ev if 'atk_a_far' not in e[2]], drive=b.fget(0, 'drive'), fury_gauge=b.fget(0, 'fgauge'))
    r.sheet(os.path.join(OUT, 'terry_ladder_one_dummy.png'), 'Terry ladder on one dummy: chain > neutral finisher > Blitz dd > 623C > 214C > fury')
    print('ladder one dummy', rungs, flush=True)
    # a crowd: dummies in a line ahead; each rung cancels the previous on hit (any enemy counts): the first layout / order
    # where every rung lands
    tried = []
    for extra in ((110, 180, 250), (90, 150, 210), (120, 160, 220), (100, 140, 180)):
        for s1, s2 in ((('special 623D (forward + C)', '1:Rc', 'SPECIAL 623B'), ('special 214C (down + C)', '1:Dc', 'SPECIAL 214C')),
                       (('special 214C (down + C)', '1:Dc', 'SPECIAL 214C'), ('special 623D (forward + C)', '1:Rc', 'SPECIAL 623B')),
                       (('special 214C (down + C)', '1:Dc', 'SPECIAL 214C'), ('special 623C (C)', '1:c', 'SPECIAL 623C'))):
            reset('terry', dist=44, fury=M['fury_max'], extra=extra)
            r = Rec(every=5, tag='ladder2', cap=60)
            for k in range(3): r.seq('1:a,1:-'); r.until_hit(40)
            r.seq('1:a,1:-'); r.until_hit(40)
            rungs = []; ok = True
            for name, q, want in (('Blitz dd (426B)', '1:D,1:-,1:D,1:Da', 'SPECIAL blitz 426B'), s1, s2, ('fury (D)', '1:d', 'SPECIAL fury 21416C')):
                r.seq(q)
                started = r.until(lambda: what() == want, 120)
                h0 = len(r.hits)
                hit = started and r.until(lambda: len(r.hits) > h0 and r.hits[-1]['by'] == want, 150)
                rungs.append(dict(rung=name, started=started, hit=hit))
                ok = ok and started and hit
                if not ok: break
            r.idle(500)
            tried.append(([x['rung'] for x in rungs], extra, ok))
            if ok: break
            [os.remove(p) for p, _, _ in r.shots]; r.shots = []
        if ok: break
    out['crowd'] = dict(layout=extra, keys=r.keystr(), rungs=rungs, hits=[(h['f'], h['who'], h['dmg'], h['by']) for h in r.hits], drive=b.fget(0, 'drive'),
                        fury_gauge=b.fget(0, 'fgauge'), tried=tried, ok=ok)
    r.sheet(os.path.join(OUT, 'terry_ladder_crowd.png'), 'Terry ladder through a crowd: chain > finisher > Blitz dd > ' + ' > '.join(x['rung'] for x in rungs[1:]) + ', each on hit')
    print('ladder crowd', out['crowd'], flush=True)
    out['ok'] = ok
    return out

def hit_p1(r, dist=30):
    """the dummy hits P1 (its intent: A) -> P1 in its hit stun (after the hit-stop) or False"""
    b.intent(2, press=1, face=-1 & 0xFF); r.step()
    if not r.until(lambda: st(0) == 'HITSTUN', 40): return False
    r.until(lambda: not b.fget(0, 'freeze'), 20)
    return True

def breaker():
    out = {}
    for case, drive, keys in (('drive, C + forward', DFULL, 'Rc'), ('no drive, C', 0, 'c'), ('drive, A+B', DFULL, 'ab'), ('no drive, A+B + down', 0, 'Dab')):
        for dist in (26, 32, 20, 38):
            reset('terry', dist=dist, drive=drive, hp=60)
            r = Rec(every=3, tag='brk')
            if not hit_p1(r): r.shots and [os.remove(p) for p, _, _ in r.shots]; r.shots = []; continue
            hp0 = b.fget(0, 'hp'); d0 = b.fget(0, 'drive')
            r.step(keys); r.until(lambda: st(0) == 'SPECIAL', 4)
            got = what(); ovls = []; invs = []
            while st(0) == 'SPECIAL' and r.f < 300: ovls.append(b.fget(0, 'ovl')); invs.append(b.fget(0, 'inv')); r.step()
            r.idle()
            paid_life = d0 < M['breaker'] * M['chunk']
            want_ovl = 2 if paid_life else 1
            out[case] = dict(got=got, want='SPECIAL 623C', drive_before=d0, drive_after=r.rows[-1]['drive'] if False else b.fget(0, 'drive'),
                             life_before=hp0, life_after=b.fget(0, 'hp'), blink=''.join(OVL[v][0] for v in ovls[:24]),
                             invincible=f'{sum(v == INV_FURY for v in invs)}/{len(invs)}',
                             ok=got == 'SPECIAL 623C' and (b.fget(0, 'hp') == hp0 - M['life_breaker'] if paid_life else b.fget(0, 'hp') == hp0)
                             and all(v in (0, want_ovl) for v in ovls) and ovls.count(want_ovl) >= len(ovls) // 3)
            r.sheet(os.path.join(OUT, f'terry_breaker_{"life" if paid_life else "drive"}_{keys}.png'), f'Terry breaker ({case}): blinks {"RED" if paid_life else "WHITE"}')
            print('breaker', case, out[case], flush=True)
            break
        else: out[case] = dict(ok=False, note='the dummy never hit P1')
    # the last point of life is never taken
    reset('terry', dist=26, drive=0, hp=5)
    r = Rec()
    if hit_p1(r):
        b.fset(0, 'hp', 1); r.step('c'); r.until(lambda: st(0) == 'SPECIAL', 4)
        out['last_point'] = dict(state=st(0), life=b.fget(0, 'hp'), ok=st(0) == 'SPECIAL' and b.fget(0, 'hp') == 1)
    print('breaker last point', out.get('last_point'), flush=True)
    return out

def blink():
    out = {}
    low = 60 * M['low'] // 100
    for case, fury, hp in (('normal', 0, 60), ('fury ready', M['fury_max'], 60), ('low life', 0, low), ('MAX ready', M['fury_max'], low)):
        reset('terry', dist=200, fury=fury, hp=hp)
        r = Rec(); seq = []
        for k in range(12): r.step(); seq.append(b.fget(0, 'ovl'))
        p0 = os.path.join(OUT, f'_b0.png'); p1 = os.path.join(OUT, f'_b1.png'); b.screenshot(p0); b.screenshot(p1)
        im = [Image.open(p0), Image.open(p1)]; w, h = im[0].size
        S = Image.new('RGB', (2 * w, h + 14), 'white'); d = ImageDraw.Draw(S); S.paste(im[0], (0, 14)); S.paste(im[1], (w, 14))
        d.text((3, 1), f'Terry, {case}: two frames in a row', fill='black'); S.save(os.path.join(OUT, f'terry_blink_{case.replace(" ", "_")}.png'))
        os.remove(p0); os.remove(p1)
        want = {'normal': {0}, 'fury ready': {0, 3}, 'low life': {0}, 'MAX ready': {0, 2}}[case]
        alt = all(seq[k] != seq[k + 1] for k in range(len(seq) - 1)) if len(want) == 2 else True
        out[case] = dict(sprite=''.join(OVL[v][0] for v in seq), ok=set(seq) == want and alt)
        print('blink', case, out[case], flush=True)
    # D: the fury with the gauge full, the MAX with it full at low life, nothing with it short
    for case, fury, hp, want in (('full', M['fury_max'], 60, '21416C'), ('full + low life', M['fury_max'], low, 'MAX 21416C'),
                                 ('short', M['fury_max'] - 1, 60, None), ('low life alone', 0, low, None)):
        reset('terry', dist=70, fury=fury, hp=hp)
        r = Rec(every=4 if want else 0, tag='fury'); r.seq('1:d'); r.until(lambda: st(0) == 'SPECIAL', 4)
        got = what(); g = b.fget(0, 'fgauge')
        r.until(lambda: st(0) != 'SPECIAL', 400); r.idle()
        out[f'D {case}'] = dict(got=got, gauge_after=g, hits=sum(h['dmg'] for h in r.hits),
                                ok=(got == f'SPECIAL fury {want}' and g == 0) if want else got != 'SPECIAL' and not got.startswith('SPECIAL'))
        if want: r.sheet(os.path.join(OUT, f'terry_fury_{"max" if "MAX" in want else "fury"}.png'), f'Terry D, gauge {case}: {want}')
        print('fury', case, out[f'D {case}'], flush=True)
    return out

def air():
    out = {}
    for case, jkeys, akeys, want, eff in (('straight jump + A', 'b', 'a', 'atk_cd_jump', 'KNOCKDOWN'), ('forward jump + A', 'Rb', 'a', 'atk_d_jump_diag', 'KNOCKDOWN'),
                                          ('straight jump + down + A', 'b', 'Da', 'atk_a_jump', 'HITSTUN'), ('forward jump + down + A', 'Rb', 'Da', 'atk_a_jump_diag', 'HITSTUN')):
        best = None
        for dist in ((20, 30, 40, 10) if jkeys == 'b' else (60, 70, 80, 90)):
            for when in (14, 18, 22, 26, 10):
                reset('terry', dist=dist)
                r = Rec(); r.step(jkeys); r.seq(f'{when}:-'); r.step(akeys)
                r.until(lambda: st(0) == 'AIR_ATTACK', 4)
                got = what(); act = 0; frames = 0
                while st(0) == 'AIR_ATTACK':
                    a = b.fget(0, 'anim'); stp = b.fget(0, 'step')
                    act += 1 if (b.fget(0, 'aact') and b.fget(0, 'aact') > act) else 0
                    frames += 1; r.step()
                landed_state = st(0); hit = [h for h in r.hits]
                c = dict(dist=dist, press_frame=when + 2, got=got, active_frames=b.fget(0, 'aact'), air_frames=frames, after=landed_state,
                         hits=[(h['dmg'], h['victim']) for h in hit])
                if hit and (best is None or not best.get('hits')): best = c
                if hit: break
            if best and best.get('hits'): break
        best = best or c
        v = best['hits'][0][1] if best.get('hits') else None
        act_ok = best['active_frames'] >= J['active_min'] if 'down' not in case else best['after'] == 'LAND'
        best['ok'] = best['got'] == f'AIR_ATTACK {want}' and v == eff and act_ok
        out[case] = best
        print('air', case, best, flush=True)
    # the down attack held active to the landing (whiffing, far away): its last active step shown to the landing
    reset('terry', dist=300); r = Rec(); r.step('b'); r.seq('10:-'); r.step('Da'); r.until(lambda: st(0) == 'AIR_ATTACK', 4)
    n = 0; acts = []
    while st(0) == 'AIR_ATTACK': n += 1; acts.append(b.fget(0, 'aact')); r.step()
    out['down_held'] = dict(active_frames=acts[-1] if acts else 0, air_attack_frames=n, then=st(0),
                            ok=st(0) == 'LAND' and len(acts) > 12 and all(acts[k + 1] == acts[k] + 1 for k in range(len(acts) - 12, len(acts) - 1)))   # (active
                                                                    # every frame to the landing)
    # down + A -> the jump attack, on hit (a forward jump at the dummy)
    for dist in (60, 70, 80, 50, 90):
        for when in (12, 16, 20, 8):
            reset('terry', dist=dist)
            r = Rec(every=2, tag='aircancel'); r.step('Rb'); r.seq(f'{when}:-'); r.step('Da')
            ok = r.until(lambda: st(0) == 'AIR_ATTACK' and len(r.hits) > 0, 30)
            if not ok: [os.remove(p) for p, _, _ in r.shots]; r.shots = []; continue
            r.until(lambda: not b.fget(0, 'freeze'), 15); r.step('a'); r.step('')
            got = what(); r.until(lambda: st(0) in ('LAND', 'IDLE'), 60); r.idle(60)
            out['cancel'] = dict(dist=dist, then=got, hits=[(h['dmg'], h['victim'], h['by']) for h in r.hits], ok=got == 'AIR_ATTACK atk_d_jump_diag')
            r.sheet(os.path.join(OUT, 'terry_air_cancel.png'), 'Terry forward jump: down + A (jump A, a flinch) cancelled on hit into the jump attack (jump D)')
            break
        if 'cancel' in out: break
    print('air cancel', out.get('cancel'), out['down_held'], flush=True)
    for case, jkeys, akeys, dist, tag in (('straight', 'b', 'a', 20, 'straight_A'), ('forward', 'Rb', 'a', 70, 'forward_A'), ('down', 'Rb', 'Da', 70, 'down_A')):
        reset('terry', dist=dist); r = Rec(every=2, tag='airs'); r.step(jkeys); r.seq('14:-'); r.step(akeys); r.until(lambda: st(0) in ('LAND',), 60); r.idle(40)
        r.sheet(os.path.join(OUT, f'terry_air_{tag}.png'), f'Terry {case} jump + {"down + A" if "D" in akeys else "A"}')
    out['ok'] = all(v.get('ok') for v in out.values() if isinstance(v, dict))
    return out

def chord():
    out = {}
    reset('terry', dist=80); r = Rec(); r.step('ab'); r.until(lambda: st(0) == 'SPECIAL', 4)
    out['same_frame'] = dict(got=what(), ok=what() == 'SPECIAL 623C')
    r.idle()
    reset('terry', dist=80); r = Rec(); r.step('a'); r.step('ab'); r.until(lambda: st(0) == 'SPECIAL', 4)
    out['A then B a frame later'] = dict(got=what(), ok=what() == 'SPECIAL 623C')
    r.idle()
    reset('terry', dist=80); r = Rec(); r.step('b'); r.step('b'); r.step('ab'); r.until(lambda: st(0) == 'SPECIAL', 4)
    out['B then A two frames later'] = dict(got=what(), ok=what() == 'SPECIAL 623C')
    r.idle()
    reset('terry', dist=80); r = Rec(); r.step('Rab'); r.until(lambda: st(0) == 'SPECIAL', 4)
    out['forward + A+B'] = dict(got=what(), ok=what() == 'SPECIAL 623B')
    r.idle()
    reset('terry', dist=80); r = Rec(); r.step('b'); r.seq('6:-'); r.step('a')
    out['B then A late (a jump, its attack)'] = dict(got=[w for _, _, w in r.ev][-2:], ok=st(0) in ('AIR', 'AIR_ATTACK', 'PREJUMP'))
    r.idle(100)
    # the hold: forward + C = the plain throw (the super throw dropped), no drive spent
    reset('terry', dist=40); r = Rec(); r.seq('20:R'); r.until(lambda: st(0) == 'GRAB', 30); g = st(0)
    r.step('Rc'); r.step(''); got = st(0); dr = b.fget(0, 'drive'); r.idle(200)
    out['hold forward + C'] = dict(grab=g, got=got, drive=dr, ok=g == 'GRAB' and got == 'THROW' and dr == DFULL)
    for k, v in out.items(): print('chord', k, v, flush=True)
    out['ok'] = all(v['ok'] for v in out.values())
    return out

# ---- meter -----------------------------------------------------------------------------------------------------------
def meter():
    global CUR_POOL
    CUR_POOL = pool('terry'); out = RES['meter'] = {}
    reset('terry', dist=300); r = Rec(); r.seq('1:c'); r.until(lambda: st(0) == 'SPECIAL', 4)
    d1 = b.fget(0, 'drive'); r.idle(); d2 = b.fget(0, 'drive')
    t = 0
    while b.fget(0, 'drive') < DFULL and t < 600: b.run(1); t += 1
    out['special'] = dict(after_press=d1, at_idle=d2, frames_to_full=t + (d2 - d1), ok=d1 == DFULL - M['chunk'] + 1 or d1 == DFULL - M['chunk'])
    reset('terry', dist=300); b.fset(0, 'drive', 0); r = Rec(); tl = []
    for k in range(M['chunk'] * M['chunks'] + 10): b.run(1); tl.append(b.fget(0, 'drive'))
    out['refill'] = dict(after_240=tl[M['chunk'] - 1], after_480=tl[2 * M['chunk'] - 1], ok=tl[M['chunk'] - 1] == M['chunk'] and tl[-1] == DFULL)
    # the HUD's chunks: full, one and a half, empty
    for case, d in (('full', DFULL), ('one_and_a_half', M['chunk'] * 3 // 2), ('empty', 0)):
        reset('terry', dist=200, drive=d); b.fset(0, 'drive', d); p = os.path.join(OUT, f'hud_drive_{case}.png')
        b.fset(0, 'drive', d); b.screenshot(p)
    # the fury gauge: dealing (a chain on the dummy) and taking (a hit from it)
    reset('terry', dist=44); r = Rec()
    for k in range(3): r.seq('1:a,1:-'); r.until_hit(40)
    r.seq('1:a,1:-'); r.until_hit(40); r.idle()
    dealt = sum(h['dmg'] for h in r.hits); g = b.fget(0, 'fgauge')
    out['dealt'] = dict(damage=dealt, gauge=g, ok=g == dealt * M['fury_dealt'])
    reset('terry', dist=26, hp=60); r = Rec(); hit_p1(r); lost = 60 - b.fget(0, 'hp'); g2 = b.fget(0, 'fgauge')
    out['taken'] = dict(life_lost=lost, gauge=g2, ok=g2 == lost * M['fury_taken'] and lost > 0)
    reset('terry', dist=70, fury=M['fury_max']); r = Rec(); r.seq('1:d'); r.until(lambda: st(0) == 'SPECIAL', 4); g3 = b.fget(0, 'fgauge')
    r.until(lambda: st(0) != 'SPECIAL', 400); g4 = b.fget(0, 'fgauge')
    out['fury_spends'] = dict(at_start=g3, after=g4, ok=g3 == 0 and g4 == 0)
    for k, v in out.items(): print('meter', k, v, flush=True)


def bzloop():
    """Bruno's 0.8.0 note: ff+A must not cancel into ff+A (a Blitz cancels only into a special)"""
    reset('terry', dist=50, face=1, extra=(90, 130))
    r = Rec(tag='bzloop')
    for k in range(3):
        r.seq('1:Ra,1:-'); r.until_hit(30)
        r.seq('1:R,1:-,1:R,1:Ra,1:-'); r.until_hit(30)
    r.idle(60)
    print('rows', [(i, x) for i, x in enumerate(getattr(r, 'trans', []))], flush=True)
    n = sum(1 for m in r.moves if m == 'body_toss')
    RES['bzloop'] = {'moves': r.moves, 'body_toss_started': n, 'ok': True}
    print('bzloop', r.moves, flush=True)

TELE_KEY = os.environ.get('TELE', '2:Rc')
def tele():
    """Bruno's note: Goenitz's teleport (214B on forward + C) goes through people (no push)"""
    reset('goenitz', dist=50, face=1)
    x0, d0 = int(b.fget(0, 'x')), int(b.fget(2, 'x'))
    r = Rec(tag='tele'); r.seq(TELE_KEY); w = []
    for k in range(120):
        r.idle(1); w.append((st(0), int(b.fget(0, 'x')), int(b.fget(2, 'x'))))
    print('trace', w[::6], flush=True)
    x1, d1 = int(b.fget(0, 'x')), int(b.fget(2, 'x'))
    RES['tele'] = {'p1': (x0, x1), 'dummy': (d0, d1), 'ok': x1 > d1 and abs(d1 - d0) < 8}
    print('tele', RES['tele'], flush=True)

for s in SECTIONS: globals()[s]()
def oks(d):
    if isinstance(d, dict):
        if 'ok' in d and not isinstance(d['ok'], dict): yield d['ok']
        for v in d.values(): yield from oks(v)
json.dump(RES, open(os.path.join(OUT, 'newsys.json'), 'w'), indent=1, default=str)
bad = []
def walk_bad(d, path):
    if isinstance(d, dict):
        if d.get('ok') is False: bad.append(path)
        for k, v in d.items(): walk_bad(v, path + '/' + str(k))
walk_bad(RES, '')
print('ALL OK' if not bad else 'FAIL: ' + ' '.join(bad))
