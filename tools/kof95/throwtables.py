#!/usr/bin/env python3
"""KOF95 throw tables, decoded from the ROM (2026-10-02).
A throw's code calls $4AE6 every frame with a0 = its table: 26 long pointers, one per VICTIM character id; each points to
a list of 4-byte entries, one per step of the thrower's animation (thrower +$82 = steps played, entry = steps - 1):
  [victim game state, dx (s8), dy, end flag]
The victim gets that state (its own state->slot table picks the frame, so each body has its own drawing), and is placed
at thrower x - dx (in the thrower's facing direction; the table stores it negated), height + dy (dy is signed unless
bit 0 is set). The entry with the end flag releases the victim (thrown flight, then landing, under the game's physics).
Tables are found at the code sites calling $4AE6 (lea table,a0 just before); which character owns which table is matched
against MAME captures (capture/throws/<id>.json, victim Terry).
    python3 throwtables.py           -> throw table per character + validation"""
import json, os, struct, sys
import rom
HERE = os.path.dirname(os.path.abspath(__file__))

def tables(prom):
    """every table-shaped block in the code area: 26 pointers below $80000, each to a list of entries (state >= 20)
    that ends with a non-zero end flag ($01 or $FF) within 24 entries. Which block is which throw is decided by
    matching MAME captures (the scan also yields shifted views of real tables; they do not match)."""
    out = []
    for a in range(0x8000, 0x80000 - 104, 2):
        ptrs = [struct.unpack_from('>I', prom, a + 4 * i)[0] for i in range(26)]
        if not all(0x8000 <= x < 0x80000 and x % 2 == 0 for x in ptrs): continue
        ok = True
        for x in ptrs:
            for k in range(24):
                st, dx, dy, fl = prom[x + 4 * k:x + 4 * k + 4]
                if st < 20: ok = False; break
                if fl: break
            else: ok = False
            if not ok: break
        if ok: out.append(a)
    return out

def victim_rows(prom, table, victim, limit=32, fmt='byte'):
    """entries for one victim; dx returned in the thrower's facing direction (+ = in front). fmt 'byte' = $4AE6 tables
    [state, dx, dy, flags] (flags bit 6 = victim drawn in front of the thrower, non-zero = last entry), 'word' = $4BF4
    tables [state.w, dx.w, dy.w, end.w]"""
    a = struct.unpack_from('>I', prom, table + victim * 4)[0]; out = []
    if not 0x000400 <= a < len(prom) - 8: return None
    s16 = lambda o: struct.unpack_from('>h', prom, o)[0]
    for k in range(limit):
        if fmt == 'word':
            st, dx, dy, fl = struct.unpack_from('>H', prom, a + 8 * k)[0], s16(a + 8 * k + 2), s16(a + 8 * k + 4), struct.unpack_from('>H', prom, a + 8 * k + 6)[0]
            out.append({'state': st, 'dx': -dx, 'dy': dy, 'end': fl, 'front': 0})
        else:
            st, dx, dy, fl = prom[a + 4 * k:a + 4 * k + 4]
            out.append({'state': st, 'dx': -(dx - 256 if dx > 127 else dx), 'dy': dy if dy & 1 else (dy - 256 if dy > 127 else dy),
                        'end': fl, 'front': (fl >> 6) & 1})
        if fl: break
    return out

# throws whose table was found by tapping A0 at $4AE6 / $4BF4 during the character's own throw (MAME), or that use no table
TAPPED = {'chin': ('byte', [0x15BCA]), 'goro': ('byte', [0x19B32, 0x19D8E]), 'choi': ('byte', [0x26A2C]), 'ryo': ('word', [0x2B6DC]),
          'kensou': ('strike', []), 'omega_rugal': ('byte', [0x351CE, 0x352A2])}

def match(prom, cid, throw):
    """table whose Terry-victim rows fit the captured sequence: all entry states appear in order (the first two may be
    missing: the capture can start late), and at least 2/3 of the entries also have the captured offset within 4 px
    (the game slides the victim toward some entries' positions over a few frames instead of snapping)"""
    seq = [(v['state'], v['dx'], v['dy']) for v in throw['victim']]
    best = (0, None)
    for t in TABLES or tables(prom):
        rows = victim_rows(prom, t, 15)
        if not rows or len(rows) < 3: continue
        i, found, close = 0, 0, 0
        for k, r in enumerate(rows):
            j = next((j for j in range(i, len(seq)) if seq[j][0] == r['state']), None)
            if j is None:
                if k < 2: continue
                found = -1; break
            found += 1; i = j
            if any(s == r['state'] and abs(x - r['dx']) <= 4 and abs(y - r['dy']) <= 4 for s, x, y in seq[j:j + 40]): close += 1
        if found >= 3 and close * 3 >= found * 2 and found + close > best[0]: best = (found + close, t)
    return best[1]

def predict(lists, w1, w2, prev, cam_x):
    """the game's placement of the victim for one frame (routine $4AE6/$4BF4 + the screen clamp at $3B500):
    entry = thrower steps (+$82) - 1; on a thrower step with the event flag (+$7D bit 0) the next entry is used
    (look-ahead) unless the entry is the last; while the thrower is in hit-stop (+$7B > 0) the routine does not run
    and the victim keeps its position; finally every fighter is kept between camera + 32 and + 288 (33..287 airborne)"""
    import analyze as A
    b1 = bytes(x for v in w1 for x in (v >> 8, v & 255)); b2 = bytes(x for v in w2 for x in (v >> 8, v & 255))
    if b1[0x7B] and prev is not None: return prev
    idx = max(0, ((b1[0x82] << 8) | b1[0x83]) - 1)
    state = (b2[0x72] << 8) | b2[0x73]
    # throws with several tables (Goro) use them one per thrower phase: the n-th throw state of the thrower -> table n
    if len(lists) > 1:
        ts = (b1[0x72] << 8) | b1[0x73]
        if ts not in predict.phases: predict.phases.append(ts)
        lists = [lists[min(predict.phases.index(ts), len(lists) - 1)]]
    cands = []
    for l in lists:
        if not l: continue
        e = l[min(idx, len(l) - 1)]
        if b1[0x7D] & 1 and not e['end'] and idx + 1 < len(l): e = l[idx + 1]
        cands.append(e)
    e = next((c for c in cands if c['state'] == state), cands[0] if cands else None)
    if e is None: return None
    f = 1 if A.facing_of(w1) else -1
    predict.last_end = bool(e['end'])
    x = A.x_of(w1) + f * e['dx']; y = A.y_of(w1) + e['dy']
    if cam_x is None: return (e['state'], x, y)              # no camera log: no screen clamp
    lo, hi = (cam_x + 33, cam_x + 287) if b2[0xE1] & 1 else (cam_x + 32, cam_x + 288)
    return (e['state'], min(max(x, lo), hi), y)

def validate(prom, cid, fmt, tabs):
    """mirror-match capture (capture/mirror/<id>.txt, X throws X): replay the model frame by frame from the grab to the
    release and compare state and position with what the game did"""
    import sys; sys.path.insert(0, os.path.join(HERE, 'capture')); import analyze as A
    from mirror_check import ROUND, GRAB
    base = os.path.join(HERE, 'capture', 'mirror', f'{cid}')
    r1, r2 = A.load(base + '.txt', 1), A.load(base + '.txt', 2)
    cam = {int(l.split()[0]): int(l.split()[3]) / 65536 for l in open(base + '_cam.txt') if len(l.split()) > 3}
    lists = [victim_rows(prom, t, cid, fmt=fmt) for t in tabs]
    states = {c['state'] for l in lists if l for c in l}
    g = next(i for i in range(ROUND, len(r2)) if A.state_of(r2[i][3]) in GRAB)
    tot = state_ok = ok = 0; prev = None; bad = []; released = False
    # hold throws (Chin, Choi, Goro) start with an approach the grab code places without the table: start at the first
    # frame the table reproduces
    approach = 0; predict.phases = []
    while g < len(r2) - 1:
        pr = predict(lists, r1[g][3], r2[g][3], None, cam.get(r1[g][0] - 1, 0))
        if pr and pr[0] == A.state_of(r2[g][3]) and abs(pr[1] - A.x_of(r2[g][3])) <= 1 and abs(pr[2] - A.y_of(r2[g][3])) <= 1: break
        g += 1; approach += 1
        if approach > 60: return ('no table match; victim states', sorted({A.state_of(r2[i][3]) for i in range(g - 60, g)}))
    for i in range(g, min(len(r2), g + 200)):
        w1, w2 = r1[i][3], r2[i][3]
        if A.state_of(w2) not in states: break                  # released into flight
        pr = predict(lists, w1, w2, prev, cam.get(r1[i][0] - 1, 0))      # camera moves after the fighters: last frame's
        if pr is None: break
        if released: break                                             # after the release frame: thrown flight (physics)
        released = getattr(predict, 'last_end', False)
        tot += 1; s_ok = pr[0] == A.state_of(w2); state_ok += s_ok
        good = s_ok and abs(pr[1] - A.x_of(w2)) <= 1 and abs(pr[2] - A.y_of(w2)) <= 1; ok += good
        if not good and len(bad) < 4: bad.append((i - g, A.state_of(w2), round(A.x_of(w2) - A.x_of(w1)), pr[0], round(pr[1] - A.x_of(w1))))
        prev = (A.state_of(w2), A.x_of(w2), A.y_of(w2))
    return tot, state_ok, ok, bad, f'approach {approach}f' if approach else ''

TABLES = None

if __name__ == '__main__':
    prom, _ = rom.load(); res = {}; TABLES = tables(prom)
    for cid, name in enumerate(rom.CAST):
        caps = json.load(open(os.path.join(HERE, 'capture', 'throws', f'{cid}.json')))
        found = {}
        for t in caps:
            key = 'air_throw' if t['try'].startswith('air') and t['p1_air'] else 'throw' if t['try'].startswith('ground') else None
            if key and key not in found and t['victim']:
                tab = match(prom, cid, t)
                found[key] = hex(tab) if tab else None
        if name in TAPPED:
            fmt, tabs = TAPPED[name]; found['throw'] = [fmt] + [hex(t) for t in tabs]
        else:
            found = {k: ['byte', v] if v else None for k, v in found.items()}
        res[name] = found
        g = found.get('throw')
        v = validate(prom, cid, g[0], [int(t, 16) for t in g[1:]]) if g and g[0] != 'strike' else None
        print(f'{name:12}', found, ' model replay (frames, state ok, exact, first misses):', v)
    json.dump(res, open(os.path.join(HERE, 'throw_tables.json'), 'w'), indent=1)
