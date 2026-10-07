#!/usr/bin/env python3
"""The ROM-read specials (tools/kof96/handlers98.py, export_bm rom_c, fighter.c prog_update) against KOF98, frame by frame.

    python3 romspecials_check.py GAME_DIR OUT_DIR [fighter:role[=INPUT] ...]     (an AI_OFF=1 build: the target stands still)
    BRANCHES=whiff,close,mid,wall (default whiff,close): mid = P2 112 px ahead (romspecials98.PLACE), wall = close
    with P1 as far from the wall as the brawler's start from its own (TODO #173); =INPUT plays another
    special of the fighter's pool from that slot; +LINK@T (repeatable) a follow-up press (TODO #74): LINK one of the
    special's links (its program's 'links': 'again', 'fA', 'fAB'), T the special's frame of KOF's button press
    (FOLLOW_KOF: the game's input; the brawler presses so its program reads it on the frame KOF's handler does, T +
    FOLLOW_LAG); e.g. iori:ufD+again@5+again@13, k_dash:D+fAB@12; ~H (TODO #198) the move's button held H frames past
    KOF's try (romspecials98 hold): the brawler holds it until its program has played the frames KOF's handler saw it
    held (PC_HELD), e.g. kyo:C~60, kyo:M~200

Per special and branch (whiff: nobody near; hit: an enemy standing 48 px ahead, KOF98's close-range distance), from the
special's first frame: the frame shown (ROM frame index), x from the start (forward +), height, the hits (frames the
target's life drops) and the projectile (first frame, place, speed). KOF98 side: tools/kof96/capture/romspecials98.py
(our emulator; the game's hit-stop and slowdown frames dropped: the brawler applies its own hit-stop instead). The
brawler's own hit-stop frames (P1's program did not run: srow unchanged; the hit's own frame runs) are dropped the same
way. Its objects (TODO #142, Raging Storm's pillars that never ended): every object KOF's P1 owns (its pool slots, a
freed one = +$06 $FFFF) against the brawler's P1-owned entities, followed past the move's end until they die: per object
its spawn frame, end frame and path (x, height) on the frames both show it; 'objects_ok' false when one is missing on
either side, spawns or ends more than a frame apart, or is still alive when the brawler's window (KOF's + 60) ends.
KOF96 / KOF99 fighters: KOF = (game, id). Specials by C + the stick, furies by D (2026-10-06). Contact sheets: OUT_DIR/<fighter>_<input>
_<branch>.png, KOF98 left, brawler right, every 4th frame; OUT_DIR/summary.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
from harness import Brawler
import romspecials98 as K, handlers98 as H
NPJ = 8                                                  # fighter.h: the projectile entities
FOLLOW_BLAG = 1                                          # the brawler's pad -> intent delay (frames; measured)
from PIL import Image, ImageDraw

ROLES = {'D': '4:c', 'fD': '4:Rc', 'dD': '4:Dc', 'uD': '4:Uc', 'dfD': '4:DRc', 'ufD': '4:URc', 'C': '4:d', 'M': '4:Dd'}   # M: the MAX fury (down+D, TODO #152)   # facing right (C + the stick:
# 2026-10-06; role 'C' = the fury, button D, game.json roster[].fury, TODO #139)
KOF = {'kyo': 0, 'terry': 3, 'ryo': 6, 'robert': 7, 'ralf': 10, 'mai': 16, 'yashiro': 21, 'yamazaki': 24, 'billy': 26, 'iori': 27, 'rugal': 36,
       'geese': ('kof96', 24), 'mr_big': ('kof96', 26), 'krauser': ('kof96', 25), 'goenitz': ('kof96', 28), 'k_dash': ('kof99', 0)}   # KOF98 id or (game, id)
# a follow-up's input in the game, facing right: [(frames from the button press, frames held, keys)]
FOLLOW_KOF = {('iori', 'again'): [(-4, 2, 'D'), (-2, 2, 'DL'), (0, 3, 'La')],                       # 214A (214A, 623D)
              ('kyo', 'again'): [(-8, 2, 'R'), (-6, 2, 'DR'), (-4, 2, 'D'), (-2, 2, 'DL'), (0, 3, 'La')],   # 63214A (236C)
              ('kyo', 'fA'): [(-2, 2, 'R'), (0, 6, 'Ra')],                                          # 6A (236C's 2nd)
              ('k_dash', 'fA'): [(-2, 2, 'R'), (0, 6, 'Rb')], ('k_dash', 'fAB'): [(-2, 2, 'R'), (0, 6, 'Rd')]}
FOLLOW_PAD = {'fA': ('Ra', 0), 'fAB': ('Rc', 0)}        # the brawler's pad keys, the frames its intent waits (0: no chord)
CASES = ['terry:fD', 'terry:dD', 'terry:D', 'ralf:fD', 'ralf:dD', 'ralf:uD']
EVERY = 4
DIST = {'close': 48, 'mid': 112, 'wall': 48}             # wall: KOF's P1 as far from its wall (x 736) as the brawler's from
#                                                          its own (TODO #173: a catch that grinds to the wall)                         # P2 ahead of P1 (px): romspecials98.PLACE close / mid
BRANCHES = os.environ.get('BRANCHES', 'whiff,close').split(',')

def prog_links(game, cid, inp):
    """the link names of a ROM special's program (bit k = links[k])"""
    m = K.rom96.Mem(K.rom96.load(K.rom96.GAMES[game]['neo'])[0], game)
    h, bt = H.handler_of(cid, inp, inp.startswith('EX '), game)
    return H.decode(m, h, bt, inp.startswith('EX '), cid=cid)['links']

def brawler_run(b, k, role, hit, shots, frames=300, pool=None, meter=None, follow=(), facing=1, obj_window=400, held=0):
    """follow: [(program frame that must read the press, keys, intent delay)]; facing -1: from the right, keys mirrored;
    held: the button stays down until the program has played `held` frames (its PC_HELD reads it held on those)"""
    mir = (lambda ks: ks.translate(str.maketrans('RL', 'LR'))) if facing < 0 else (lambda ks: ks)
    b.pick(k, unlock=True)                              # Rugal / Goenitz are unlocked by play
    b.run(10)
    if pool is not None:                                 # fighter:role=INPUT: the slot repointed at another special
        scr = b.syms['lab'] + 400                        # (lab.buf, unused without a Lab tree; spec_tab[fighter] -> it)
        for q in range(6): b.w(scr + q, 1, pool if q == list(ROLES).index(role) else 0xFF)
        b.w(b.syms['spec_tab'] + 4 * k, 4, scr)
    for i in range(1, 8): b.place(i, x=1000, z=0)
    x1 = 60 if facing > 0 else 260
    b.place(0, x=x1, z=30)                               # the left of the screen: room for the rushes
    if hit: b.place(2, x=x1 + facing * hit, z=30)
    if facing < 0: b.fset(0, 'facing', 0xFF)
    b.run(2)
    w = 0
    while b.states[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
    if meter is not None: b.fset(0, 'meter', meter)       # a full special meter (0.0.48: a special costs meter)
    b.hits = []
    n, keys = ROLES[role].split(':')
    rows, started, t, pfz, done = [], None, 0, 0, None
    x0 = b.fget(0, 'x'); fc = -1 if b.fget(0, 'facing') in (255, -1) else 1
    fpress = {}
    for f in range(frames):
        if f < int(n): b.pad = [set(mir(keys)), set()]
        elif held and (started is None or b.fget(0, 'srow') < held - FOLLOW_BLAG): b.pad = [{keys[-1]}, set()]   # the button
        else: b.pad = [set(), set()]
        if started is not None:                          # a follow-up: pressed so that prog_update reads it at its frame
            sr = b.fget(0, 'srow')                       # (srow = the program frames played: the next one is srow)
            for j, (pf, fk, dl) in enumerate(follow):
                if j not in fpress and (b.fget(0, 'freeze') > 1 if pf is None else sr >= pf - dl - FOLLOW_BLAG): fpress[j] = 3
                # (pf None: pressed in its hit-stop, Iori 623D's latch)
                if fpress.get(j, 0) > 0: b.pad = [set(mir(fk)), set()]; fpress[j] -= 1
        st = b.states[b.fget(0, 'state')]
        want = started is not None and (len(rows) % EVERY == 0)
        path = None
        if started is None:                              # row 0's picture (its frame is known only after it)
            path = os.path.join(shots, 'b_000.png'); b.screenshot(path)
        elif want and len(rows) // EVERY < 30:
            path = os.path.join(shots, f'b_{len(rows):03d}.png'); b.screenshot(path)
        else: b.core.retro_run(); b.frame += 1
        st = b.states[b.fget(0, 'state')]
        if started is None and st == 'SPECIAL' and b.fget(0, 'frame_ovr') != 0xFFFF: started = f; path = os.path.join(shots, 'b_000.png')
        if started is None: continue
        if done is None and st != 'SPECIAL' and f > started + 2 and (not hit or b.states[b.fget(2, 'state')] not in ('KNOCKDOWN', 'HITSTUN') or len(rows) > 400):
            done = len(rows)                             # the move is over: its objects are followed on (objects_of)
        if done is not None:
            ob = live_objs(b, x0, fc)
            if not ob or len(rows) >= obj_window: break
            rows.append({'tail': True, 'objs': ob}); continue
        sr = b.fget(0, 'srow')                           # the brawler's own hit-stop: frames its program did not run
        if rows and sr == pfz and st == 'SPECIAL': continue   # (fighter.c prog_update counts srow; the hit's own frame runs;
                                                         # past the move every frame counts: an object outliving it, TODO #152)
        pfz = sr
        pj = []
        for i in range(4):
            if b.pget(i, 'state') < len(b.states) and b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'frame_ovr') != 0xFFFF:
                pj.append((i, b.pget(i, 'frame_ovr'), round((b.pget(i, 'x') - x0) * fc, 2), round(b.pget(i, 'y'), 2)))
        rows.append({'objs': live_objs(b, x0, fc), 'spart': b.fget(0, 'plink'), 'frame': b.fget(0, 'frame_ovr'), 'x': round((b.fget(0, 'x') - x0) * fc, 2), 'h': round(b.fget(0, 'y'), 2),
                     'hp2': b.fget(2, 'hp'), 'proj': pj, 'shot': path,
                     'vx': round((b.fget(2, 'x') - x0) * fc, 2), 'vh': round(b.fget(2, 'y'), 2), 'vst': b.states[b.fget(2, 'state')]})
    return rows[:done] if done is not None else rows, rows

def live_objs(b, x0, fc):
    """P1's objects now (fighter.c projectiles[]): [(entity, frames alive, frame shown, x from the start (forward +),
    height)]"""
    out = []
    for i in range(NPJ):
        if b.pget(i, 'state') < len(b.states) and b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'owner') == b.base \
                and b.pget(i, 'frame_ovr') != 0xFFFF:
            out.append((i, b.pget(i, 'state_t'), b.pget(i, 'frame_ovr'), round((b.pget(i, 'x') - x0) * fc, 2), round(b.pget(i, 'y'), 2)))
    return out

def lives(per_frame):
    """[(key, ...) per frame] -> objects: [{'first', 'last', 'path': [(frame, x, h)], 'frame0'}]; a key present on
    consecutive frames is one object (a slot freed and taken again leaves a frame out, or its age restarts)"""
    open_, done = {}, []
    for f, objs in enumerate(per_frame):
        seen = set()
        for key, age, fr, x, h in objs:
            o = open_.get(key)
            if o is not None and (o['last'] != f - 1 or (age is not None and age < o['age'])):
                done.append(open_.pop(key)); o = None
            if o is None: o = open_[key] = {'first': f, 'last': f, 'path': [], 'frame0': fr, 'age': age}
            o['last'] = f; o['age'] = age; o['path'].append((f, x, h)); seen.add(key)
        for key in [k for k in open_ if k not in seen]: done.append(open_.pop(key))
    return sorted(done + list(open_.values()), key=lambda o: (o['first'], o['frame0']))

def objects_check(kof, bra, nk, nb, rec):
    """KOF's objects against the brawler's (TODO #142: Raging Storm's pillars lived on): per object its spawn and end
    frame (the move's kept frames from its first; +-1: the samples' tick) and its path (x from the start, height) on
    the frames both show it. nk / nb: the frames each side was followed; an object still alive at the end of the
    brawler's window fails (it never ends), one at the end of KOF's is not judged past it"""
    ko, bo = lives(kof), lives(bra)
    res, used = [], set()
    for k in ko:                                         # its brawler twin: the same spawn frame (+-1), the same first
        cand = [j for j, o in enumerate(bo) if j not in used and abs(o['first'] - k['first']) <= 1]   # ROM frame first
        cand.sort(key=lambda j: (rec(bo[j]['frame0']) != k['frame0'], abs(bo[j]['first'] - k['first'])))
        if not cand: res.append({'kof': (k['first'], k['last'], k['frame0']), 'brawler': None, 'ok': False}); continue
        j = cand[0]; used.add(j); o = bo[j]
        kp = {f: (x, h) for f, x, h in k['path']}
        both = [(f, x, h) for f, x, h in o['path'] if f in kp]
        dx = max((min(abs(x - kp[g][0]) for g in (f - 1, f, f + 1) if g in kp) for f, x, h in both), default=0)
        dh = max((min(abs(h - kp[g][1]) for g in (f - 1, f, f + 1) if g in kp) for f, x, h in both), default=0)
        k_open, b_open = k['last'] >= nk - 1, o['last'] >= nb - 1
        end_ok = not b_open and (k_open and o['last'] >= nk - 2 or not k_open and abs(o['last'] - k['last']) <= 1)
        res.append({'kof': (k['first'], k['last'], k['frame0']), 'brawler': (o['first'], o['last'], rec(o['frame0'])),
                    'kof_alive_at_end': k_open, 'brawler_alive_at_end': b_open, 'max_dx': round(dx, 2), 'max_dh': round(dh, 2),
                    'ok': abs(o['first'] - k['first']) <= 1 and end_ok})
    for j, o in enumerate(bo):
        if j not in used: res.append({'kof': None, 'brawler': (o['first'], o['last'], rec(o['frame0'])), 'brawler_alive_at_end': o['last'] >= nb - 1, 'ok': False})
    return res

def sheet(pairs, path, title):
    W, H = 160, 112
    cols = 2
    im = Image.new('RGB', (cols * (2 * W + 8) + 8, 20 + ((len(pairs) + cols - 1) // cols) * (H + 16)), 'white')
    d = ImageDraw.Draw(im); d.text((8, 4), title, fill='black')
    for i, (f, a, b) in enumerate(pairs):
        x = 8 + (i % cols) * (2 * W + 8); y = 20 + (i // cols) * (H + 16)
        for j, p in enumerate((a, b)):
            if p and os.path.exists(p): im.paste(Image.open(p).convert('RGB').resize((W, H)), (x + j * W, y + 12))
            d.rectangle([x + j * W, y + 12, x + j * W + W - 1, y + 12 + H - 1], outline='black')
        d.text((x, y), f'frame {f}: KOF98 | brawler', fill='black')
    im.save(path)

def main(game, out, cases):
    os.makedirs(out, exist_ok=True)
    roster = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    gj = {r['name']: r for r in json.load(open(os.path.join(game, 'game.json')))['roster']}
    meter = json.load(open(os.path.join(game, 'game.json')))['meter']['max']
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    summary = []
    for case in cases:
        name, role = case.split(':'); role, *fus = role.split('+'); role, _, hold = role.partition('~'); role, _, inp = role.partition('=')
        hold = int(hold or 0)                            # ~H: the button held H frames more (KOF's try)
        inp = inp or (gj[name]['fury'] if role in ('C', 'M') else gj[name]['specials'][role]); cid = KOF[name]
        sdm = role == 'M'                                # KOF98's MAX version of the fury (romspecials98 sdm)
        fus = [(fu.split('@')[0], int(fu.split('@')[1])) for fu in fus]
        pool = None
        if '=' in case:
            fi = next(f for f in json.load(open(os.path.join(game, 'build', 'chainlab.json')))['fighters'] if f['name'] == name)
            pool = [p['input'] for p in fi['pool']].index(inp)
        kg, cid = cid if isinstance(cid, tuple) else ('kof98', cid)
        links = prog_links(kg, cid, inp) if fus else []
        kfol = [(t, FOLLOW_KOF[(name, l)], 1 << links.index(l)) for l, t in fus]
        bpad = [((ROLES[role].split(':')[1], 0) if l == 'again' else FOLLOW_PAD[l]) for l, t in fus]
        for branch in BRANCHES:
            tag = f'{name}_{"MAX" if sdm else ""}{inp.replace(" ", "").replace("[", "c").replace("]", "")}' + ''.join(f'+{l}{t}' for l, t in fus) + (f'_h{hold}' if hold else '') + f'_{branch}'
            shots = os.path.join(out, 'shots', tag); os.makedirs(shots, exist_ok=True)
            dm = role in ('C', 'M')                      # a fury: KOF96's from low life, P2 jumps over the whiff, 400 frames
            try: res, game_rows, model, objs, prog = K.compare(cid, inp.replace('EX ', ''), branch, inp.startswith('EX '), quiet=True, game=kg, follow=kfol,
                                                               dm=dm, frames=400 if dm else 200, sdm=sdm, hold=hold)
            except StopIteration as e:                   # KOF's trace never entered the special (a mash input: Ralf AAAA)
                s = {'case': case, 'input': inp, 'branch': branch, 'error': f'no KOF trace {e!r}'}
                summary.append(s); print(json.dumps(s), flush=True); continue
            ref = 'kof'
            if dm and branch == 'whiff' and (res['hit_frames'] or res.get('catch') is not None) and \
                    K.whiff_jump(cid, inp.replace('EX ', ''), inp.startswith('EX '), kg) is None and res.get('catch') is not None:
                # KOF catches P2 wherever it is, even in the air (Robert's Ryuko Ranbu): its whiff is the decoded program's
                # (romspecials98's model, matched to KOF frame for frame on the catch side) -> the reference rows
                ref = 'model'
                model = H.run_model(K.rom96.Mem(K.rom96.load(K.rom96.GAMES[kg]['neo'])[0], kg), cid, prog, 400)[0]   # no hit
                game_rows = [{'f': r[0], 'state': r[1], 'frame': r[2], 'x': r[3], 'h': r[4]} for r in model]
                res = dict(res, frames_game=len(model) - 1, hit_frames=[], frozen_dropped=0, slowdown_dropped=0, objects_game=[])
            # KOF screenshots at the kept frames (every EVERY-th of the move after the dropped ones)
            want = [game_rows[i]['f'] for i in range(0, res['frames_game'], EVERY)][:30]
            K.trace(cid, inp.replace('EX ', ''), branch, inp.startswith('EX '), 400 if dm else 200, snaps=[K.START + f for f in want], snapdir=shots, game=kg, dm=dm, sdm=sdm, hold=hold,
                    p2_seq=K.follow_spec(cid, inp.replace('EX ', ''), branch, inp.startswith('EX '), kg, [(t, ev) for t, ev, mk in kfol]) if kfol else '')
            # the opponent as far ahead as KOF's was when the special started (a charge move walked P1 back first)
            gap = round(game_rows[0]['p2x'] - game_rows[0]['x']) if branch in DIST else None
            bfol = [((None if q in res['press_latched'] else pf),) + bp for q, (pf, bp) in enumerate(zip(res['press_frames'], bpad))
                    if pf is not None]   # (a press KOF latched in its hit-stop: the brawler presses in its own)   # the program frame KOF's
                                                         # handler read it on (None: lost in KOF's hit-stop, not pressed)
            br, bro = brawler_run(b, roster.index(name), role, gap, shots, pool=pool, meter=meter, follow=bfol, frames=900 if dm else 700,
                                  obj_window=len(game_rows) + 60, held=res.get('held', 0))
            rec = lambda bf: int(frames[name][bf].split(':')[1]) if bf < len(frames[name]) and frames[name][bf] else -1
            kcid = cid; rec0 = K.rom96.frame_record(K.rom96.Mem(K.rom96.load(K.rom96.GAMES[kg]['neo'])[0], kg), cid, 0)
            n = min(len(br), res['frames_game'])
            gx0 = game_rows[0]['x'] - model[0][3]
            # the harness samples RAM when a video frame ends, inside a game tick (regress.py `near`): a sample may show
            # P1 before or after this tick's update; a sample matches when it equals KOF's at that frame or one either side
            near = lambda i: range(max(0, i - 1), min(n, i + 2))
            badf = [i for i in range(n) if all(rec(br[i]['frame']) != game_rows[j]['frame'] for j in near(i))]
            dfr = len(badf)
            dx = max((min(abs(br[i]['x'] - (game_rows[j]['x'] - gx0)) for j in near(i)) for i in range(n)), default=0)
            dh = max((min(abs(br[i]['h'] - game_rows[j]['h']) for j in near(i)) for i in range(n)), default=0)
            bhits = [i for i in range(1, len(br)) if br[i]['hp2'] < br[i - 1]['hp2']]
            bp = next(((i, r['proj']) for i, r in enumerate(br) if r['proj']), None)
            seqk = [game_rows[i]['state'] for i in range(res['frames_game']) if i == 0 or game_rows[i]['state'] != game_rows[i - 1]['state']]
            s = {'x_trace': [(i, br[i]['x'], round(game_rows[i]['x'] - gx0, 2)) for i in range(0, n, 8)],
                 'case': case, 'input': inp, 'branch': branch, 'reference': ref, 'hold': hold, 'held_frames': res.get('held', 0), 'kof_frames': res['frames_game'], 'brawler_frames': len(br),
                 'kof_states': seqk, 'brawler_parts': sorted({r['spart'] for r in br}),
                 'frame_mismatch': dfr, 'bad_frames': [(i, rec(br[i]['frame']), game_rows[i]['frame']) for i in badf[:8]], 'max_dx': round(dx, 2), 'max_dh': round(dh, 2), 'kof_hits': res['hit_frames'],
                 'brawler_hits': bhits, 'kof_freeze_dropped': res['frozen_dropped'], 'kof_slowdown_dropped': res['slowdown_dropped'],
                 'kof_objects': res['objects_game'], 'brawler_proj_first': bp and [bp[0]] + [list(p) for p in bp[1]],
                 'brawler_proj_next': (br[bp[0] + 1]['proj'] if bp and bp[0] + 1 < len(br) else None)}
            if ref == 'kof':                             # its objects' lives (TODO #142)
                before = set(res.get('objects_before', ()))
                kof_pf = [[(o['base'], None, (o['rec'] - rec0) // 6, round(o['x'] - gx0, 2), o['h']) for o in g['objs'] if o['table'] == kcid
                           and not (o['base'] in before and all(any(q['base'] == o['base'] for q in game_rows[j]['objs']) for j in range(i + 1)))]
                          for i, g in enumerate(game_rows)]
                s['objects'] = objects_check(kof_pf, [[((i_,), age, fr, x, h) for i_, age, fr, x, h in r['objs']] for r in bro],
                                             len(game_rows), len(bro) if len(bro) >= len(game_rows) + 60 else 10 ** 9, rec)   # (the brawler's window
                                             # ran out: what is still alive then never ends)
                s['objects_ok'] = all(o['ok'] for o in s['objects'])
                s['objects_bad'] = [o for o in s['objects'] if not o['ok']]
            if branch in DIST:                           # the victim (2026-10-05: KOF98's own reaction, no carry): its x
                # x from where KOF's first hit found it (each side: the brawler at its hit nearest KOF's first; KOF's
                # charge moves differ in their walk-up) and height per frame, to the end of its fall (KOF: the floor, 309)
                kh = res['hit_frames'][0] if res['hit_frames'] else 0
                bh = min(bhits, key=lambda i: abs(i - kh)) if bhits else kh
                vg = [(round(g['p2x'] - game_rows[kh]['p2x'] + (br[bh]['vx'] if bh < len(br) else 0), 2), g['p2h']) for g in game_rows]
                m = min(len(br), len(vg))
                vend = next((i for i in range(1, m) if game_rows[i]['p2state'] >= 300 and game_rows[i - 1]['p2h'] > 0), m)
                s['victim_frames'] = vend
                s['victim_max_dx'] = max((min(abs(br[i]['vx'] - vg[j][0]) for j in range(max(0, i - 1), min(m, i + 2))) for i in range(kh, vend)), default=0)
                s['victim_max_dh'] = max((min(abs(br[i]['vh'] - vg[j][1]) for j in range(max(0, i - 1), min(m, i + 2))) for i in range(kh, vend)), default=0)
                s['victim'] = [(i, br[i]['vx'], br[i]['vh'], vg[i][0], vg[i][1]) for i in range(vend)]
            summary.append(s); json.dump(summary, open(os.path.join(out, 'summary.json'), 'w'), indent=1); print(json.dumps({k: v for k, v in s.items() if k != 'victim'}), flush=True)
            pairs = []
            for i in range(0, min(len(br), res['frames_game']), EVERY):
                kp = os.path.join(shots, f'snap_{K.START + game_rows[i]["f"]}.ppm')
                pairs.append((i, kp, br[i]['shot']))
            sheet(pairs[:30], os.path.join(out, tag + '.png'), f'{name} {inp} ({role}) {branch}: KOF98 (our emulator, freezes dropped) | brawler (ROM program)')
    json.dump(summary, open(os.path.join(out, 'summary.json'), 'w'), indent=1)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or CASES)
