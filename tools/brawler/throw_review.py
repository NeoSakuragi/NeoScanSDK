#!/usr/bin/env python3
"""The THROW REVIEW page's data (note 20261016-045300-e03d round 2, Bruno: "Throws should be case by case. Robert's forward
throw is an IMPACT throw [...] the back throw is a SLAM throw [...] review the throws frame by frame so I can show you
exactly what to do and when"): every throw of every playable fighter of the beta (game.json unlocks: starters + rungs) as
the brawler plays it, captured in our emulator (harness.py through labdrive's training mode: P1 the fighter, the dummy
never attacks), every game frame at 1x, both fighters on screen.

Rows per fighter: forward + A (the forward throw), back + A (the back throw) and hold + B when the fighter has one
(game.json roster[].throws.b: Haggar's piledriver, the extra paired throw BT_XTHROW; throws.extra.b: SS2 Hanzo's Mozu
Otoshi, a grab special). Each is played from the hold (P1 walks into the dummy standing 40 px ahead, facing right).

    python3 tools/brawler/throw_review.py OUT GAME_DIR [FIGHTER ...]     (default: the beta's playable fighters)

-> OUT/review/throws/index.json   {set, fps, game_version, rows: [{id, fighter, display, throw, label, input, kind,
                                   frames, w, h, cols, sheet, now: {damage, impacts, release, handoff, ...}}]}
   OUT/review/throws/<id>.json    per frame: rows [victim row, thrower row], states, victim hp lost, height
   OUT/review/throws/<id>.webp    the frames as one sheet (cols x rows of w x h, frame k at (k % cols, k // cols))
The page: review.html?q=throws (review.js "the throw review"); answers in the feedback service's decisions store, set
"throws" (tools/brawler/throw_answers.py reads them and writes game.json roster[].throws.timing)."""
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


def build(out, game, names=None):
    from labdrive import Lab
    G = json.load(open(os.path.join(game, 'game.json')))
    order = [r['name'] for r in G['roster']]
    names = names or beta(G)
    od = os.path.join(out, 'review', 'throws'); os.makedirs(od, exist_ok=True)
    L = Lab(game=game)
    rows = []
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
                   'hp': [d['hp'] for d in data], 'vy': [d['vy'] for d in data], 'held': [d['vheld'] for d in data]}
            json.dump(per, open(os.path.join(od, rid + '.json'), 'w'), separators=(',', ':'))
            inp = {'fwd': 'forward + A in the hold', 'back': 'back + A in the hold', 'holdb': 'B in the hold'}[opt[0]]
            row = {'id': rid, 'fighter': n, 'display': R.get('display') or n.upper().replace('_', ' '), 'throw': opt[0], 'label': opt[1],
                   'input': inp, 'kind': 'paired' if sc else 'special', 'script': sname, 'frames': len(frames), 'w': w, 'h': h, 'cols': COLS,
                   'sheet': f'review/throws/{rid}.webp', 'data': f'review/throws/{rid}.json', 'now': now,
                   'speed': sc['speed'] if sc else None, 'nrows': sc['nrows'] if sc else None}
            rows.append(row)
            print(f"{rid:16s} {len(frames):3d} frames {w}x{h}  damage at {now['damage']} ({now['damage_hp']})  impacts {now.get('impacts')}  "
                  f"release {now.get('release')}  hand-off {now['handoff']} ({now['handoff_state']})", flush=True)
    ver = open(os.path.join(game, 'VERSION')).read().strip()
    json.dump({'set': SET, 'fps': 59.18, 'game_version': ver, 'dummy': DUMMY, 'rows': rows}, open(os.path.join(od, 'index.json'), 'w'), indent=1)
    return rows


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], sys.argv[3:] or None)
