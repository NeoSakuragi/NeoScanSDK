#!/usr/bin/env python3
"""The THROW REVIEW page's data (note 20261016-045300-e03d round 2, Bruno: "Throws should be case by case. Robert's forward
throw is an IMPACT throw [...] the back throw is a SLAM throw [...] review the throws frame by frame so I can show you
exactly what to do and when"): every throw of every playable fighter of the beta (game.json unlocks: starters + rungs) as
the brawler plays it, captured in our emulator (harness.py through labdrive's training mode: P1 the fighter, the dummy
never attacks), every game frame at 1x, both fighters on screen.

Rows per fighter: forward + A (the forward throw), back + A (the back throw) and hold + B when the fighter has one
(game.json roster[].throws.b: Haggar's piledriver, the extra paired throw BT_XTHROW; throws.extra.b: SS2 Hanzo's Mozu
Otoshi, a grab special). Each is played from the hold (P1 walks into the dummy standing 40 px ahead, facing right).

    python3 tools/brawler/throw_review.py OUT GAME_DIR [FIGHTER ...] [--set SET] [--prev PREV_INDEX.json]
        (default: the beta's playable fighters, set "throws"). --set throws2 (the THROW REVIEW v2, review.html?q=throws2:
        Bruno 2026-10-16 "back to the drawing board": impact / launch / held as separate events) writes OUT/review/throws2/
        and links each row to the capture he judged before (--prev: that set's index.json, e.g. 0.10.130's
        review/throws/index.json: row.prev = its sheet / data / frames, served next to it).

-> OUT/review/<set>/index.json   {set, fps, game_version, rows: [{id, fighter, display, throw, label, input, kind,
                                   frames, w, h, cols, sheet, now: {damage, impacts, release, handoff, ...}}]}
   OUT/review/throws/<id>.json    per frame: rows [victim row, thrower row], states, victim hp lost, height
   OUT/review/throws/<id>.webp    the frames as one sheet (cols x rows of w x h, frame k at (k % cols, k // cols))
The page: review.html?q=throws (review.js "the throw review"); answers in the feedback service's decisions store, set
"throws" (tools/brawler/throw_answers.py reads them and writes game.json roster[].throws.timing).

    python3 tools/brawler/throw_review.py OUT GAME_DIR [BOSS ...] --set bossthrows [--prev LEGACY/index.json]
        THE BOSS THROWS (2026-10-17, review.html?q=bossthrows): each boss fighter throwing Terry the AI's way, its
        command grabs too (build_boss below), one frame per game tick; --set bossthrows_legacy on a build without the
        events = the old rule's capture (the page's second capture, throwcfg.py defaults' input)."""
import json, os, re, sys
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))

SET = 'throws'               # the decisions store's set (review.js, throw_answers.py)
DUMMY = 'ryo'                # the victim (note 20261016-045300-e03d's scenario: Robert on Ryo)
COLS = 10                    # frames a sheet row
MAX_FRAMES = 240
NAMES = {('haggar', 'holdb'): 'Hold + B: piledriver', ('hanzo_ss2', 'holdb'): 'Hold + B: Mozu Otoshi (special 623K)'}


def beta(G):
    u = G['unlocks']
    return list(u['starters']) + [n for r in u['rungs'] for n in r]


def scripts(game, n):
    """{throw_c / throw_d / throw_x: {nrows, speed, ret, rel, land, impacts: [rows], turn}} from build/bm_chars.c"""
    src = open(os.path.join(game, 'build', 'bm_chars.c')).read()
    def rows(name):
        m = re.search(r'static const bthrow_row_t %s\[\] = \{(.*?)\};' % re.escape(name), src)
        if not m: return []
        return [[int(x, 0) for x in r.split(',')] for r in re.findall(r'\{([^{}]*)\}', m.group(1))]
    def head(t):
        v = [x.strip() for x in t.split(',')]
        return {'nrows': int(v[0], 0), 'speed': int(v[1], 0), 'rows_name': v[2], 'ret': int(v[3], 0), 'rel': int(v[4], 0), 'land': int(v[5], 0),
                'turn': int(v[14], 0) if len(v) > 14 else 0}
    out = {}
    m = re.search(r'static const bthrow_t %s_throws\[BT_COUNT\] = \{(.*?)\};' % n, src)
    for k, t in enumerate(re.findall(r'\{([^{}]*)\}', m.group(1))): out[('throw_c', 'throw_d')[k]] = head(t)
    m = re.search(r'static const bthrow_t %s_xthrow = \{([^{}]*)\};' % n, src)
    if m: out['throw_x'] = head(m.group(1))
    for k, h in out.items():
        rs = rows(h['rows_name']) if h['rows_name'] != '0' else []
        h['impacts'] = [i for i, r in enumerate(rs) if r[4] & 4]     # bthrow_row_t flags 4: an impact (spark, sound)
        h['heights'] = [r[2] + r[6] for r in rs]                     # the victim's height (ty + vy) by row
        del h['rows_name']
    return out


def options(G, n):
    """the rows of fighter n: (key, label, stick, button, script name)"""
    t = (next(r for r in G['roster'] if r['name'] == n).get('throws') or {})
    out = [('fwd', 'Forward throw', 'f', 'a', 'throw_c'), ('back', 'Back throw', 'b', 'a', 'throw_d')]
    if t.get('b'): out.append(('holdb', NAMES.get((n, 'holdb'), 'Hold + B throw'), '', 'b', 'throw_x'))
    elif (t.get('extra') or {}).get('b'): out.append(('holdb', NAMES.get((n, 'holdb'), 'Hold + B: special ' + t['extra']['b']), '', 'b', None))
    return out


def capture(L, n, opt, sc):
    """one throw from the hold, every frame -> (frames [PIL], per-frame data)"""
    b = L.b; ST = b.states
    st = lambda i: ST[b.fget(i, 'state')]
    for _ in range(900):                                          # settle
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'freeze'): break
        b.run(1)
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 140
    b.place(0, x=x0, z=30); b.place(2, x=x0 + 40, z=30); b.fset(0, 'facing', 1); b.fset(2, 'facing', 0xFF)
    b.fset(2, 'hp', 60); b.run(2)
    for _ in range(60):
        if st(0) == 'GRAB': break
        b.run(1, 'R')
    else: raise RuntimeError(f'{n}: no hold: ' + b.brief((0, 2)))
    b.run(2)
    key, label, stick, btn, sname = opt
    k = {'f': 'R', 'b': 'L'}.get(stick, '') + btn
    b._want_video = True
    frames, data, started, h0 = [], [], False, len(b.hits)
    down = 0
    for t in range(MAX_FRAMES + 40):
        b.run(1, k if t < 2 else '')
        s0, s2 = st(0), st(2)
        if not started:
            if s0 in ('THROW', 'SPECIAL'): started = True
            elif t > 20: raise RuntimeError(f'{n} {key}: no throw: ' + b.brief((0, 2)))
            else: continue
        data_w, data_h, pitch = b._video[1], b._video[2], b._video[3]
        im = Image.frombuffer('RGBX', (data_w, data_h), b._video[0], 'raw', 'BGRX', pitch, 1).convert('RGB')
        cam = b.r(b.syms['cam_x'], 2)
        frames.append(im)
        data.append({'t': st(0), 'v': s2, 'tid': b.fget(0, 'throw_id'), 'trow': b.fget(0, 'srow') - 1, 'vrow': b.fget(2, 'srow') - 1,
                     'vheld': 1 if b.fget(2, 'held') else 0, 'vy': round(b.fget(2, 'y')), 'hp': 0, 'frame': b.frame,
                     'sx': [round(b.fget(0, 'x')) - cam, round(b.fget(2, 'x')) - cam], 'spec': b.fget(0, 'spec_ix') if s0 == 'SPECIAL' else None})
        down = down + 1 if s2 in ('DOWN', 'GETUP', 'IDLE', 'WALK') and s0 not in ('THROW', 'SPECIAL', 'GRAB') else 0
        if down >= 12 or len(frames) >= MAX_FRAMES: break
    b._want_video = False
    f0 = data[0]['frame']
    for fr, i, d, s in b.hits[h0:]:
        if i == 2 and d > 0 and 0 <= fr - f0 < len(data): data[fr - f0]['hp'] += d
    return frames, data


def now_of(data, sc):
    """the current build's timing, by frame (0-based): damage, impact rows passed (spark / sound), the thrown body's start
    (release row), the hand-off (the victim the engine's body)"""
    out = {'damage': [k for k, d in enumerate(data) if d['hp']], 'damage_hp': [d['hp'] for d in data if d['hp']]}
    thrown = [k for k, d in enumerate(data) if d['v'] == 'THROWN']
    hand = thrown[-1] + 1 if thrown and thrown[-1] + 1 < len(data) else None
    if sc:
        prev, imp, rel = -1, [], None
        for k, d in enumerate(data):
            if d['v'] != 'THROWN' and k != hand: continue            # (the hand-off frame plays its rows too)
            if any(prev < r <= d['vrow'] for r in sc['impacts']): imp.append(k)
            if rel is None and sc['rel'] != 0xFFFF and d['vrow'] >= sc['rel']: rel = k
            prev = d['vrow']
        out['impacts'] = imp
        out['release'] = rel
    out['handoff'] = hand
    out['handoff_state'] = data[out['handoff']]['v'] if out['handoff'] is not None else None
    return out


def build(out, game, names=None, set_=SET, prev=None):
    from labdrive import Lab
    G = json.load(open(os.path.join(game, 'game.json')))
    order = [r['name'] for r in G['roster']]
    names = names or beta(G)
    od = os.path.join(out, 'review', set_); os.makedirs(od, exist_ok=True)
    L = Lab(game=game)
    rows = []
    PV = {r['id']: r for r in json.load(open(prev))['rows']} if prev else {}
    pver = json.load(open(prev))['game_version'] if prev else None
    for n in names:
        fi = order.index(n); di = order.index(DUMMY)
        L.start(fi, di); L.b.run(30)
        blob = L.b.save()
        S = scripts(game, n)
        R = next(r for r in G['roster'] if r['name'] == n)
        for opt in options(G, n):
            L.b.load(blob)
            frames, data = capture(L, n, opt, S)
            sname = opt[4]
            if sname == 'throw_d' and (S['throw_d']['nrows'] == 0 or S['throw_d']['turn']): sname = 'throw_c'   # (an empty D: C played turned)
            if sname and data[0]['t'] != 'THROW': sname = None
            sc = S.get(sname) if sname else None
            W, H = frames[0].size                                  # the whole screen (a lying body is wide; the
            x0, x1, y0, y1 = 0, W, 0, H                            # life bars show the damage landing)
            w, h = x1 - x0, y1 - y0
            nr = -(-len(frames) // COLS)
            sheet = Image.new('RGB', (COLS * w, nr * h), 'white')
            for k, im in enumerate(frames): sheet.paste(im.crop((x0, y0, x1, y1)), ((k % COLS) * w, (k // COLS) * h))
            rid = f'{n}-{opt[0]}'
            sheet.save(os.path.join(od, rid + '.webp'), lossless=True, quality=100, method=4)
            now = now_of(data, sc)
            per = {'id': rid, 'rows': [[d['vrow'], d['trow']] for d in data], 'states': [[d['t'], d['v']] for d in data],
                   'hp': [d['hp'] for d in data], 'vy': [d['vy'] for d in data], 'held': [d['vheld'] for d in data], 'sx': [d['sx'] for d in data]}
            json.dump(per, open(os.path.join(od, rid + '.json'), 'w'), separators=(',', ':'))
            inp = {'fwd': 'forward + A in the hold', 'back': 'back + A in the hold', 'holdb': 'B in the hold'}[opt[0]]
            row = {'id': rid, 'fighter': n, 'display': R.get('display') or n.upper().replace('_', ' '), 'throw': opt[0], 'label': opt[1],
                   'input': inp, 'kind': 'paired' if sc else 'special', 'script': sname, 'frames': len(frames), 'w': w, 'h': h, 'cols': COLS,
                   'sheet': f'review/{set_}/{rid}.webp', 'data': f'review/{set_}/{rid}.json', 'now': now,
                   'speed': sc['speed'] if sc else None, 'nrows': sc['nrows'] if sc else None}
            if rid in PV:                                          # the capture he judged (its frames match this one's up
                p = PV[rid]                                        # to the first difference: same setup, same inputs)
                row['prev'] = {k: p[k] for k in ('game_version', 'frames', 'w', 'h', 'cols', 'sheet', 'data', 'now') if k in p}
                row['prev']['game_version'] = pver
            rows.append(row)
            print(f"{rid:16s} {len(frames):3d} frames {w}x{h}  damage at {now['damage']} ({now['damage_hp']})  impacts {now.get('impacts')}  "
                  f"release {now.get('release')}  hand-off {now['handoff']} ({now['handoff_state']})", flush=True)
    ver = open(os.path.join(game, 'VERSION')).read().strip()
    json.dump({'set': set_, 'fps': 59.18, 'game_version': ver, 'dummy': DUMMY, 'rows': rows}, open(os.path.join(od, 'index.json'), 'w'), indent=1)
    return rows


# ---- THE BOSS THROWS (Bruno 2026-10-17: "Remember how we adjusted the throws for players - let's do it for the bosses as
# well"): the throws the bosses' AI plays on a player, each as the boss plays it on Terry (P1, the victim), captured the
# same way (every game frame, the whole screen). The AI (ai.c) throws only from its hold, always forward + A (the hold's
# "after two hits maybe a throw", the grab counter's throw); its command grabs are the furies / MAX whose program catches
# (a victim script: bspec_t.vlists), played by a boss in its red period (MAX first, red_max of them, then the fury). Rows:
#   <fighter>-fwd    the forward throw of every boss fighter (game.json enemies with ai "boss", their base fighter; the
#                    other enemies on that base, e.g. the finale's GHOST_BIG, play the same data: one path)
#   <fighter>-fury / -max   a fury / MAX that catches (Rugal's Gigantic Pressure, Omega Rugal's EX 236236C): judged on the
#                    page, not yet on the events model (applies: false: the engine's events cover a grab special on hold
#                    + B / the run grab only)
BOSS_SET = 'bossthrows'
VICTIM = 'terry'
BOSS_GAP = 60                  # px between them for a fury / MAX (the AI fires its red fury within boss_ai.red.dx)
P1_LIFE = 16 + 64 * 6 + 16 + 128 * 24 + 1   # fighter.h lab_t.p1_life: 1 = P1's life left to the game (the life bar shows it)


def boss_fighters(G):
    """[(fighter, [enemy names on it])]: the base fighters of the enemies with the boss AI, in game.json enemies order, each
    with every enemy using it (bosses first)"""
    out = {}
    for e in G['enemies']:
        if e.get('ai') == 'boss' and e.get('base') not in (None, 'pool'): out.setdefault(e['base'], [])
    for e in G['enemies']:
        if e.get('base') in out: out[e['base']].append(e['name'])
    return list(out.items())


def grab_specials(game, n):
    """{'fury' | 'max': pool index} of fighter n's fury / MAX whose program catches (a victim script in build/bm_spec.c)"""
    cl = json.load(open(os.path.join(game, 'build', 'chainlab.json')))['fighters']
    pool = [p['input'] for p in next(f for f in cl if f['name'] == n)['pool']]
    G = json.load(open(os.path.join(game, 'game.json')))
    fury = next(r for r in G['roster'] if r['name'] == n).get('fury')
    src = open(os.path.join(game, 'build', 'bm_spec.c')).read()
    m = re.search(r'const bspec_t %s_specials\[\d+\] = \{(.*?)\};\n' % re.escape(n), src, re.S)
    ents, d, cur = [], 0, ''
    for c in (m.group(1) if m else ''):                          # (its entries: the top-level {...} of the array)
        if c == '{': d += 1
        if d: cur += c
        if c == '}':
            d -= 1
            if not d: ents.append(cur); cur = ''
    out = {}
    for k, inp in (('fury', fury), ('max', 'MAX ' + fury if fury else None)):
        if inp in pool:
            ix = pool.index(inp)
            if ix < len(ents) and re.search(r'_vl\s*\}$', ents[ix]): out[k] = ix   # (bspec_t.vlists, its last field)
    return out


def boss_options(game, G, n):
    """the rows of boss fighter n: (key, label, kind, pool index or None)"""
    out = [('fwd', 'Forward throw', 'paired', None)]
    gs = grab_specials(game, n)
    fury = next(r for r in G['roster'] if r['name'] == n).get('fury')
    if 'max' in gs: out.append(('max', f'MAX {fury} (command grab)', 'special', gs['max']))
    if 'fury' in gs: out.append(('fury', f'Fury {fury} (command grab)', 'special', gs['fury']))
    return out


def capture_boss(L, n, opt, game):
    """the boss (the dummy, slot 2, intents written here: nothing else writes them in a Chain Lab fight) throws Terry (P1)
    -> (frames, per-frame data); frame 1 = the throw's (the special's) first frame, then one per game tick: the engine's
    own frame clock (a lag frame, the tick not run, is no frame of the throw: KRAUSER's throw start lags one)"""
    import throw_regress as TR
    b = L.b; ST = b.states
    st = lambda i: ST[b.fget(i, 'state')]
    ia = b.syms['in'] + 2 * b.syms['sizeof_intent']
    def intent(dx=0, press=0, grab=0, dz=0):
        for off, v in ((0, dx & 0xFF), (1, dz & 0xFF), (2, press), (5, grab), (6, 1)): b.w(ia + off, 1, v)
    for _ in range(900):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK') and not b.fget(0, 'freeze'): break
        b.run(1)
    key, label, kind, pix = opt
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 120
    gap = 60 if key == 'fwd' else BOSS_GAP
    b.place(0, x=x0, z=30); b.place(2, x=x0 + gap, z=30); b.fset(0, 'facing', 1); b.fset(2, 'facing', 0xFF)
    L.poke(P1_LIFE, [1]); b.fset(0, 'hp', b.fget(0, 'hp_max') or 120)
    b.run(2)
    if key == 'fwd':
        for _ in range(90):
            intent(-1, 0, 1); b.run(1)
            if st(2) == 'GRAB': break
        else: raise RuntimeError(f'{n}: no hold: ' + b.brief((0, 2)))
        intent(); b.run(2)
        for _ in range(30):                                       # (the hold's own hit-stop over: the AI throws hold_gap
            if not b.fget(2, 'freeze') and not b.fget(0, 'freeze'): break   # frames after a hold hit)
            intent(); b.run(1)
        face = -1 if b.fget(2, 'facing') < 0 else 1
        drive = lambda t: intent(face if t < 1 else 0, 1 if t == 0 else 0)   # (the AI: forward + A one frame, ai.c)
        mode = 'THROW'
    else:
        drive = lambda t: intent(-1 if t < 2 else 0, 8 if t == 0 else 0, 0, 1 if key == 'max' else 0)   # D / down + D
        mode = 'SPECIAL'
    FX = TR.Fx(b)
    b._want_video = True
    frames, data, started = [], [], False
    down = 0; hp0 = b.fget(0, 'hp'); prev_td = 0
    gt = b.syms['game_ticks']; lag = 0
    for t in range(MAX_FRAMES * 3):
        tk = b.r(gt, 4)
        drive(t); b.run(1); fx = FX.frame()
        if b.r(gt, 4) == tk:                                      # a lag frame (the game's tick did not run: the screen
            lag += 1; continue                                    # holds): not a frame of the throw's clock
        s2, s0 = st(2), st(0)
        if not started:
            if s2 == mode: started = True
            elif t > 20: raise RuntimeError(f'{n} {key}: no {mode.lower()}: ' + b.brief((0, 2)))
            else: hp0 = b.fget(0, 'hp'); continue
        im = Image.frombuffer('RGBX', (b._video[1], b._video[2]), b._video[0], 'raw', 'BGRX', b._video[3], 1).convert('RGB')
        cam = b.r(b.syms['cam_x'], 2)
        hp = b.fget(0, 'hp'); td = b.fget(0, 'throw_dealt')
        lost = (max(0, td - prev_td) if mode == 'THROW' else max(0, hp0 - hp)); prev_td = td; hp0 = hp
        frames.append(im)
        data.append({'t': s2, 'v': s0, 'trow': b.fget(2, 'srow') - 1, 'vrow': b.fget(0, 'srow') - 1, 'vheld': 1 if b.fget(0, 'held') else 0,
                     'vy': round(b.fget(0, 'y')), 'hp': lost, 'frame': b.frame, 'sx': [round(b.fget(2, 'x')) - cam, round(b.fget(0, 'x')) - cam],
                     'catch': 1 if mode == 'SPECIAL' and b.fget(2, 'pflags') & 32 else 0, 'tid': b.fget(2, 'throw_id'),
                     'vx': round(b.fget(0, 'x'), 2), 'vyf': round(b.fget(0, 'y'), 2), 'spark': fx['spark'], 'sfx': fx['sfx'], 'shake': fx['shake']})
        down = down + 1 if s0 in ('DOWN', 'GETUP', 'IDLE', 'WALK') and s2 not in ('THROW', 'SPECIAL', 'GRAB') else 0
        if down >= 12 or len(frames) >= (MAX_FRAMES if mode == 'THROW' else 2 * MAX_FRAMES): break
    b._want_video = False
    if data: data[0]['lag'] = lag
    return frames, data


def boss_now(data, sc):
    """today's play of a boss throw by frame (0-based): damage frames, the impacts (spark / sound), the hand-off (the victim
    no longer in the throw), its state there; a command grab: the catch and release frames"""
    out = {'damage': [k for k, d in enumerate(data) if d['hp']], 'damage_hp': [d['hp'] for d in data if d['hp']],
           'sparks': [k for k, d in enumerate(data) if d['spark']], 'shakes': [k for k, d in enumerate(data) if d['shake']]}
    if data[0]['t'] == 'THROW':
        thrown = [k for k, d in enumerate(data) if d['v'] == 'THROWN']
        out['handoff'] = thrown[-1] + 1 if thrown and thrown[-1] + 1 < len(data) else None
        prev, imp = -1, []
        for k, d in enumerate(data):
            if d['v'] != 'THROWN' and k != out['handoff']: continue
            if sc and any(prev < r <= d['vrow'] for r in sc['impacts']): imp.append(k)
            prev = d['vrow']
        out['impacts'] = imp
    else:
        held = [k for k, d in enumerate(data) if d['catch']]
        out['catch'] = held[0] if held else None
        out['handoff'] = held[-1] + 1 if held and held[-1] + 1 < len(data) else None
        out['impacts'] = out['damage']
    out['handoff_state'] = data[out['handoff']]['v'] if out['handoff'] is not None else None
    return out


def defaults_of(now):
    """today's play of a paired throw -> the events that play it the same (frames 1-based): impacts = the frames of its
    script's impact rows (their spark, sound and hurt voice) and of its damage (on a frame without an impact row: silent,
    no spark), the damage whole on the last (the slam), no screen shake (a throw without events has none); held = launch =
    the frame the victim leaves the script, launch "land" (the landing hand-off: the knockdown's floor bounce there, as
    today). None: not expressible (more impacts than the model's 3, damage before a later impact, no hand-off, or not a
    paired throw)"""
    import build_tables as BT
    if 'catch' in now: return None
    imp = sorted(set(now['impacts']) | set(now['damage']))
    if now['handoff'] is None or not imp or len(imp) > BT.EVENT_IMPS or len(now['damage']) != 1: return None
    if now['damage'][0] != imp[-1]: return None                                 # (damage before a later impact: no)
    L = now['handoff'] + 1
    if imp[-1] + 1 > L: return None
    e = {'impacts': [dict({'frame': k + 1}, **({} if k in now['impacts'] else {'spark': False, 'sound': False}), shake=False) for k in imp]}
    e['launch'] = {'frame': L, 'dir': 'land'}
    return e


def build_boss(out, game, set_=BOSS_SET, prev=None, names=None):
    """the boss throw review's data: OUT/review/<set>/ (index.json rows as build()'s + boss, enemies, applies, proposed:
    the events the game plays (game.json throws.events) or, none there, the ones today's play gives (defaults_of))"""
    from labdrive import Lab
    G = json.load(open(os.path.join(game, 'game.json')))
    order = [r['name'] for r in G['roster']]
    od = os.path.join(out, 'review', set_); os.makedirs(od, exist_ok=True)
    L = Lab(game=game)
    PV = {r['id']: r for r in json.load(open(prev))['rows']} if prev else {}
    pver = json.load(open(prev))['game_version'] if prev else None
    rows = []
    for n, users in boss_fighters(G):
        if names and n not in names: continue
        L.start(order.index(VICTIM), order.index(n)); L.b.run(30)
        blob = L.b.save()
        S = scripts(game, n)
        R = next(r for r in G['roster'] if r['name'] == n)
        for opt in boss_options(game, G, n):
            L.b.load(blob)
            frames, data = capture_boss(L, n, opt, game)
            sname = {0: 'throw_c', 1: 'throw_d', 4: 'throw_x'}.get(data[0]['tid']) if opt[2] == 'paired' else None
            sc = S.get(sname) if sname else None
            w, h = frames[0].size
            nr = -(-len(frames) // COLS)
            sheet = Image.new('RGB', (COLS * w, nr * h), 'white')
            for k, im in enumerate(frames): sheet.paste(im, ((k % COLS) * w, (k // COLS) * h))
            rid = f'{n}-{opt[0]}'
            sheet.save(os.path.join(od, rid + '.webp'), lossless=True, quality=100, method=4)
            now = boss_now(data, sc)
            per = {'id': rid, 'rows': [[d['vrow'], d['trow']] for d in data], 'states': [[d['t'], d['v']] for d in data],
                   'hp': [d['hp'] for d in data], 'vy': [d['vy'] for d in data], 'held': [d['vheld'] for d in data], 'sx': [d['sx'] for d in data],
                   'spark': [d['spark'] for d in data], 'sfx': [d['sfx'] for d in data], 'shake': [d['shake'] for d in data],
                   'catch': [d['catch'] for d in data], 'vx': [d['vx'] for d in data], 'vyf': [d['vyf'] for d in data]}
            json.dump(per, open(os.path.join(od, rid + '.json'), 'w'), separators=(',', ':'))
            ev = ((R.get('throws') or {}).get('events') or {}).get('forward') if opt[0] == 'fwd' else None
            disp = R.get('display') or users[0].replace('_', ' ').replace('MR ', 'MR. ')
            inp = {'fwd': f'{disp} holds Terry, then forward + A (the AI\'s only throw: from its hold, ai.c)',
                   'max': f'{disp} in his red period (low life): down + D, his first fury there (the MAX)',
                   'fury': f'{disp} in his red period (low life): D, his later furies there'}[opt[0]]
            row = {'id': rid, 'fighter': n, 'display': disp, 'throw': opt[0], 'label': opt[1], 'input': inp, 'kind': opt[2],
                   'script': sname, 'frames': len(frames), 'w': w, 'h': h, 'cols': COLS, 'sheet': f'review/{set_}/{rid}.webp',
                   'data': f'review/{set_}/{rid}.json', 'now': now, 'speed': sc['speed'] if sc else None, 'nrows': sc['nrows'] if sc else None,
                   'boss': True, 'enemies': users, 'applies': opt[2] == 'paired', 'pool_ix': opt[3],
                   'game_events': {x: y for x, y in ev.items() if x not in ('from', 'about')} if ev else None,
                   'proposed': {x: y for x, y in ev.items() if x not in ('from', 'about')} if ev else defaults_of(now)}
            if rid in PV:
                p = PV[rid]
                row['prev'] = {k: p[k] for k in ('frames', 'w', 'h', 'cols', 'sheet', 'data', 'now') if k in p}
                row['prev']['game_version'] = pver
                row['prev']['label'] = p.get('cap_label') or ''
            rows.append(row)
            print(f"{rid:18s} {len(frames):3d} frames  damage at {now['damage']} ({now['damage_hp']})  impacts {now.get('impacts')}  "
                  f"sparks {now['sparks']}  hand-off {now['handoff']} ({now['handoff_state']})" + (f"  catch {now.get('catch')}" if 'catch' in now else '')
                  + f"  proposed {json.dumps(row['proposed'])}", flush=True)
    ver = open(os.path.join(game, 'VERSION')).read().strip()
    json.dump({'set': set_, 'fps': 59.18, 'game_version': ver, 'dummy': VICTIM, 'boss': True, 'rows': rows},
              open(os.path.join(od, 'index.json'), 'w'), indent=1)
    return rows


if __name__ == '__main__':
    a = sys.argv[1:]
    kw = {}
    for o, k in (('--set', 'set_'), ('--prev', 'prev')):
        if o in a: i = a.index(o); kw[k] = a[i + 1]; del a[i:i + 2]
    if kw.get('set_', '').startswith(BOSS_SET): build_boss(a[0], a[1], names=a[2:] or None, **kw)
    else: build(a[0], a[1], a[2:] or None, **kw)
