#!/usr/bin/env python3
"""TODO #211 proof: Hanzo SS2's air special (Samurai Shodown II's 4 1 2 3 + S in a jump: the shuriken; handlers_ss2
han_j4123s / shuriken, game.json roster air_special "j.4123S", fighter.c role BS_AIR + bproj_t air) in the brawler
(down+A in a jump, the A+B row) next to SS2 playing 4 1 2 3 + A+B from the same jump (shuriken_ss2.py captures,
/data/neogeo_dict/samsho2/moves/02_air.json), both in a real fight (the brawler's campaign, AI on).

    python3 hanzo211_proof.py [OUTDIR]          (default /data/tmp/hz211/out)

Per scenario (jump straight up / forward x whiff / hit), from the special's first frame (the brawler: Hanzo's height
poked to SS2's there, test only: the jumps' own arcs are not the subject):
  Hanzo: every frame's picture (the export of SS2's step), dx / height, the length (to neutral);
  the shuriken: its spawn frame, every frame's picture and place from Hanzo's place at the start, the frame it is
  stuck in the floor, which floor frames show it, the frame it is gone (Hanzo's projectile slot free: SS2's +$112);
  hits: SS2's victim reel (class 3 action 1, anim 104) / the brawler's (HITSTUN), the shuriken gone at its hit.
Then: the one-projectile rule (down+A while the shuriken is stuck in the floor = the air normal, after it = the
shuriken again), and the jumps unpoked (the press as a player makes it).
Sheets <scenario>.png: SS2 above, the brawler below, every 3 frames from 12 frames before the special. OUT/proof.json."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import cap_ss2 as C, shuriken_ss2 as S, handlers_ss2 as H
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/hz211/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
AIRJ = os.environ.get('AIRJ', '/data/neogeo_dict/samsho2/moves/02_air.json')
BS_AIR = 9                                                   # fighter.h
SS2_ANIMS = [287, 249, 26, 3]                                # han_j4123s's states (P_ANIM order)
ROW = 2                                                      # the row the roster plays (A+B: export default)
EVERY, BEFORE, AFTER = 3, 12, 108
SCEN = [('up_whiff', 'up_ab', ''), ('fwd_whiff', 'fwd_ab', 'R'), ('up_hit', 'hit_up_ab', ''), ('fwd_hit', 'hit_fwd_ab', 'R')]

def bm_tables():
    """from build/bm_spec.c: Hanzo SS2's air special's step frames per state (row ROW) and the shuriken's row frames
    (flight, floor)"""
    src = open(os.path.join(GAME, 'build', 'bm_spec.c')).read()
    chs = open(os.path.join(GAME, 'build', 'bm_chars.c')).read()
    line = next(l for l in chs.splitlines() if '"HANZO", ' in l and 'hanzo_ss2_pals' in l)
    k = int(re.search(r', (\d+)\},\s*$', line).group(1))     # bchar_t.air_spec (the last field)
    an = re.search(rf'hanzo_ss2_sp{k}_an\[\] = \{{(.*?)\}};', src).group(1)
    names = re.findall(r'\{\d+, \d+, (\w+)\}', an)
    def frames(name):
        body = re.search(rf'static const bstep_t {name}\[\] = \{{(.*?)\}};', src).group(1)
        return [int(m) for m in re.findall(r'\{(\d+), \d+, \d+, \{', body)]
    st = [frames(names[j + ROW * len(SS2_ANIMS)]) for j in range(len(SS2_ANIMS))]
    pj = re.search(rf'bproj_t hanzo_ss2_pj{k}r\[\] = \{{(.*?)\}};', src).group(1)
    rows_name = re.findall(r'\{\d+, \d+, \d+, \d+, \d+, \d+, \d+, \d+, -?\d+, -?\d+, -?\d+, (\w+), \w+, \w+, \d+, \d+, \d+, \d+, -?\d+, -?\d+, &(\w+)', pj)[ROW]
    def prow(name):
        body = re.search(rf'static const bprow_t {name}\[\] = \{{(.*?)\}};', src).group(1)
        return [int(m) for m in re.findall(r'\{(\d+), -?\d+, -?\d+, \{', body)]
    nxt = re.search(rf'static const bproj_t {rows_name[1]} = \{{\d+, \d+, \d+, \d+, \d+, \d+, \d+, \d+, -?\d+, -?\d+, -?\d+, (\w+),', src).group(1)
    return k, st, prow(rows_name[0]), prow(nxt)

def ss2_case(name):
    c = json.load(open(AIRJ))[name]; rows = c['rows']
    s0 = next(i for i, r in enumerate(rows) if r['p1']['cls'] == 1)
    x0, y0 = rows[s0]['p1']['x'], rows[s0]['p1']['y']
    out = {'s0_frame': rows[s0]['f'], 'height0': 224 - y0, 'hanzo': [], 'tama': [], 'hit': None, 'gone': None, 'floor': None,
           'victim': [], 'rows': rows, 'p2x': c['p2x']}
    for i in range(s0, len(rows)):
        r = rows[i]; p = r['p1']
        if p['cls'] == 1: out['hanzo'].append((p['a'], p['st'], p['x'] - x0, 224 - p['y']))
        t = r['tama'][0] if r['tama'] and p['proj'] else None
        if t and out['gone'] is None:
            out['tama'].append((i - s0, t['a'], t['st'], t['x'] - x0, 224 - t['y'], r['floor_drawn']))
            if t['a'] == 269 and out['floor'] is None: out['floor'] = i - s0
        if out['tama'] and not p['proj'] and out['gone'] is None: out['gone'] = i - s0
        if r['p2']['cls'] == 3:
            if out['hit'] is None: out['hit'] = i - s0
            out['victim'].append((r['p2']['sub'], r['p2']['a']))
    out['victim'] = list(dict.fromkeys(out['victim']))
    return out

def ss2_snaps(name, frames, d):
    """SS2's pictures of a case (its own emulator process)"""
    seq_, p2x = S.CASES[name]
    pk = ';'.join(f'{k}:{S.P2 + 0x4E:X}={p2x >> 8:02X},{S.P2 + 0x4F:X}={p2x & 255:02X}' for k in (1, 2))
    C.run(d, seq_, load=S.STATE, vram=False, ram=False, snaps=frames, pokes=pk)
    return [Image.open(os.path.join(d, f'snap_{f}.ppm')).convert('RGB') if os.path.exists(os.path.join(d, f'snap_{f}.ppm')) else None
            for f in frames]

def shuriken_of(b):
    """Hanzo's projectile entity (index, entity fields) or None"""
    for i in range(8):
        a = b.syms['projectiles'] + i * b.fsize
        if b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'owner') == b.base: return i
    return None

def play(b, jump, enemies, mode, gap, poke_h=None, shots=True):
    """one jump + down+A at an enemy: mode 'whiff' (every enemy kept 150 px behind him) or 'hit' (enemies[0] kept gap
    px ahead of where he jumped from, the others behind, until its hit); per frame Hanzo / the shuriken / the target,
    the index = frames from the jump press. poke_h: Hanzo's height set at the special's first frame (SS2's)."""
    e = enemies[0]; h0 = len(b.hits)
    log, cells = [], []
    air_t, press, ex = 0, None, b.fget(0, 'x') + (gap or 0)
    for f in range(240):
        if b.states[b.fget(0, 'state')] == 'AIR': air_t += 1
        k = ('b' + jump) if f < 5 else ''
        if press is None and air_t == 10: press = f              # (read a frame late: the special starts on the 11th
        if press is not None and f in (press, press + 1): k = 'Da'   # airborne frame, as SS2's)
        for i in enemies:
            if mode == 'hit' and i == e:
                if not any(h[1] == e for h in b.hits[h0:]): b.place(i, x=ex)
            else: b.place(i, x=b.fget(0, 'x') - 150)
        b.pad = [set(k), set()]
        if shots and f % EVERY == 0:
            pth = os.path.join(OUT, '_shot.png'); b.screenshot(pth); cells.append((f, Image.open(pth).convert('RGB')))
        else: b.run(1, p1=k)
        st = b.states[b.fget(0, 'state')]
        if poke_h is not None and st == 'SPECIAL' and not any(r['st'] == 'SPECIAL' for r in log): b.fset(0, 'y', poke_h)
        pj = shuriken_of(b)
        log.append({'f': f, 'bf': b.frame, 'st': st, 'role': b.fget(0, 'spec_id'), 'frame': b.fget(0, 'frame_ovr'),
                    'x': b.fget(0, 'x'), 'y': b.fget(0, 'y'), 'shot': b.fget(0, 'shot'), 'facing': b.fget(0, 'facing'),
                    'pj': None if pj is None else {'frame': b.pget(pj, 'frame_ovr'), 'x': b.pget(pj, 'x'), 'y': b.pget(pj, 'y'),
                                                   'pend': b.pget(pj, 'pend')},
                    'e_state': b.states[b.fget(e, 'state')], 'e_hp': b.fget(e, 'hp')})
        if f > 40 and st in ('IDLE', 'WALK') and log[-1]['pj'] is None and log[-1]['shot'] == 0: break
    return log, cells, press, [h for h in b.hits[h0:] if h[1] == e]

def main():
    os.makedirs(OUT, exist_ok=True)
    if not os.path.exists(AIRJ): os.system(f'{sys.executable} {os.path.join(HERE, "shuriken_ss2.py")} {AIRJ}')
    k, st, prow, frow = bm_tables()
    m265 = {}
    for (a_, s_), fr in zip(H.loop_frames(2, 265, len(prow)), prow): m265.setdefault(s_, fr)   # the flight rows' steps
    def ss2_frame(a, s):
        return st[SS2_ANIMS.index(a)][s] if a in SS2_ANIMS and s < len(st[SS2_ANIMS.index(a)]) else None
    res = {'air_spec_index': k, 'scenarios': {}}
    # SS2's pictures first (its own emulator process, one at a time)
    ss2 = {}
    for name, case, _ in SCEN:
        c = ss2_case(case); s0 = c['s0_frame']
        frames = list(range(s0 - BEFORE, s0 + AFTER, EVERY))
        ss2[case] = (c, ss2_snaps(case, frames, f'/data/tmp/hz211/snap_{case}'))
    from harness import Brawler
    b = Brawler()
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    hz = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_HANZO_SS2')
    b.pick(hz); b.run(200)
    start = b.save()
    ok_all = True
    for name, case, jump in SCEN:
        c, simg = ss2[case]
        mode = 'hit' if 'hit' in name else 'whiff'
        best = None
        for gap in ([None] if mode == 'whiff' else (90, 70, 110, 60, 130, 50, 150)):
            b.load(start); b.run(30)
            en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
            cam = b.r(b.syms['cam_x'], 2)
            b.place(0, x=cam + 80, z=b.fget(en[0], 'z')); b.fset(0, 'facing', 1)
            for i in en: b.fset(i, 'hp', 60); b.place(i, z=b.fget(0, 'z'))
            log, cells, press, hits = play(b, jump, en, mode, gap, poke_h=c['height0'])
            best = (gap, log, cells, press, hits, en)
            if mode == 'whiff' or hits: break
        gap, log, cells, press, hits, en = best
        sp = [r for r in log if r['st'] == 'SPECIAL']
        i0 = next((i for i, r in enumerate(log) if r['st'] == 'SPECIAL'), None)
        r = {'ok': False, 'gap': gap}
        if i0 is None:
            r['why'] = 'no SPECIAL'; res['scenarios'][name] = r; ok_all = False; print(name, r); continue
        x0, fc = log[i0]['x'], log[i0]['facing']
        # Hanzo, frame by frame
        bz = [(q['frame'], (q['x'] - x0) * fc, q['y']) for q in sp]
        sz = [(ss2_frame(a, s), dx, h) for a, s, dx, h in c['hanzo']]
        if mode == 'hit':                                # SS2's hit-stop (12 frames, everybody) and slow motion (each
            dd = lambda L: [q for j, q in enumerate(L) if j == 0 or (q[0], round(q[1]), round(q[2])) !=   # frame twice)
                            (L[j - 1][0], round(L[j - 1][1]), round(L[j - 1][2]))]                   # vs the brawler's
            bz, sz = dd(bz), dd(sz)                       # (its thrower never frozen): both without repeated frames
        n = min(len(bz), len(sz))
        pic = [i for i in range(n) if bz[i][0] != sz[i][0]]
        dxe = max((abs(bz[i][1] - sz[i][1]) for i in range(n)), default=0)
        dye = max((abs(bz[i][2] - sz[i][2]) for i in range(n)), default=0)
        roles = sorted({q['role'] for q in sp})
        # the shuriken
        bt = []
        for i in range(i0, len(log)):
            p = log[i]['pj']
            if p is None and bt: break
            if p is not None: bt.append((i - i0, p['frame'], (p['x'] - x0) * fc, p['y'], p['pend']))
        st_ = c['tama']
        b_spawn = bt[0][0] if bt else None
        s_spawn = st_[0][0] if st_ else None
        b_floor = next((t[0] for t in bt if t[1] in frow or (t[1] == 0xFFFF)), None)
        flight_b = [t for t in bt if b_floor is None or t[0] < b_floor]
        flight_s = [t for t in st_ if t[1] == 265]
        nf = min(len(flight_b), len(flight_s))
        tpic = [j for j in range(nf) if flight_b[j][1] != m265[flight_s[j][2]]]
        tdx = max((abs(flight_b[j][2] - flight_s[j][3]) for j in range(nf)), default=0)
        tdy = max((abs(flight_b[j][3] - flight_s[j][4]) for j in range(nf)), default=0)
        fl_b = [t[1] != 0xFFFF for t in bt if b_floor is not None and t[0] >= b_floor]
        fl_s = [t[5] for t in st_ if t[1] == 269]
        b_gone = next((i - i0 for i in range(i0 + 1, len(log)) if log[i]['shot'] == 0 and log[i - 1]['shot'] != 0), None)
        r.update({'hanzo_frames': [len(bz), len(sz)], 'hanzo_picture_mismatch': pic[:8], 'hanzo_max_dx_err': round(dxe, 2),
                  'hanzo_max_h_err': round(dye, 2), 'roles': roles, 'start_height_ss2': c['height0'],
                  'shuriken_spawn': [b_spawn, s_spawn], 'shuriken_flight_frames': [len(flight_b), len(flight_s)],
                  'shuriken_picture_mismatch': tpic[:8], 'shuriken_max_dx_err': round(tdx, 2), 'shuriken_max_h_err': round(tdy, 2),
                  'floor_at': [b_floor, c['floor']], 'floor_shown_same': fl_b == fl_s, 'floor_frames': [len(fl_b), len(fl_s)],
                  'gone_at': [b_gone, c['gone']], 'hits': [len(hits), 1 if c['hit'] is not None else 0],
                  'hit_at': [hits[0][0] - log[i0]['bf'] if hits else None, c['hit']],
                  'victim_brawler': list(dict.fromkeys(q['e_state'] for q in log[i0:])), 'victim_ss2': c['victim'],
                  'damage': 60 - min(q['e_hp'] for q in log)})
        if mode == 'whiff':
            ok = (len(bz) == len(sz) and not pic and dxe <= 1.0 and dye <= 1.0 and roles == [BS_AIR] and b_spawn == s_spawn
                  and nf == len(flight_s) and not tpic and tdx <= 1.0 and tdy <= 1.0 and b_floor == c['floor'] and fl_b == fl_s
                  and b_gone == c['gone'] and not hits)
        else:
            ok = (roles == [BS_AIR] and len(hits) == 1 and not pic and abs(len(bz) - len(sz)) <= 2 and dxe <= 2.0 and dye <= 2.0
                  and b_spawn == s_spawn and not tpic and tdx <= 1.0 and tdy <= 1.0 and 'HITSTUN' in r['victim_brawler']
                  and c['victim'][:1] == [(1, 104)] and b_floor is None and c['floor'] is None and b_gone == r['hit_at'][0])
        r['ok'] = bool(ok); ok_all &= r['ok']
        res['scenarios'][name] = r
        print(f'{name:10s} {"ok" if ok else "FAIL"}', {k_: v for k_, v in r.items() if k_ not in ('ok',)}, flush=True)
        # the sheet: SS2 above, the brawler below, aligned on the special's first frame
        bcells = {f: im for f, im in cells}
        cols = list(range(-BEFORE, AFTER, EVERY)); C_ = 12; W_, H_ = 200, 140
        nrow = (len(cols) + C_ - 1) // C_
        sh = Image.new('RGB', (70 + W_ * C_, (2 * H_ + 22) * nrow + 18), 'white'); d = ImageDraw.Draw(sh)
        d.text((4, 2), f'TODO #211 Hanzo SS2 4123+S in the air ({name}; top SS2 4123+A+B, bottom brawler down+A; frames from the special\'s first)', fill='black')
        for j, rel in enumerate(cols):
            y0 = 18 + (2 * H_ + 22) * (j // C_); xx = 70 + W_ * (j % C_)
            if j % C_ == 0: d.text((4, y0 + 60), 'SS2', fill='black'); d.text((4, y0 + H_ + 70), 'brawler', fill='black')
            if simg[j] is not None: sh.paste(simg[j].resize((W_, H_)), (xx, y0))
            fb = i0 + rel                                    # the brawler's frame index (log f) of this column
            near = min(bcells, key=lambda f: abs(f - fb)) if bcells else None
            if near is not None and abs(near - fb) <= 1: sh.paste(bcells[near].resize((W_, H_)), (xx, y0 + H_ + 4))
            d.text((xx + 2, y0 + 2 * H_ + 6), f'{rel:+d}', fill='black')
        sh.save(os.path.join(OUT, name + '.png'))
    # the one-projectile rule: a second jump + down+A while the shuriken is stuck in the floor, then after it is gone
    b.load(start); b.run(30)
    en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
    cam = b.r(b.syms['cam_x'], 2); b.place(0, x=cam + 80, z=b.fget(en[0], 'z')); b.fset(0, 'facing', 1)
    seqk = ([(i, 'b') for i in range(5)] + [(i, 'Da') for i in (13, 14)] + [(i, 'b') for i in range(100, 105)] +
            [(i, 'Da') for i in (113, 114)] + [(i, 'b') for i in range(200, 205)] + [(i, 'Da') for i in (213, 214)])
    log = []
    for f in range(300):
        k_ = dict(seqk).get(f, '')
        for i in en: b.place(i, x=b.fget(0, 'x') - 150)
        b.run(1, p1=k_)
        log.append((f, b.states[b.fget(0, 'state')], b.fget(0, 'spec_id'), b.fget(0, 'shot') != 0))
    def what(a, z):
        seg = [q for q in log if a <= q[0] < z]
        return 'BS_AIR' if any(q[1] == 'SPECIAL' and q[2] == BS_AIR for q in seg) else 'AIR_ATTACK' if any(q[1] == 'AIR_ATTACK' for q in seg) else '-'
    one = {'first': what(0, 100), 'second_while_stuck': what(100, 200), 'shot_out_at_second': log[113][3],
           'third_after_gone': what(200, 300), 'shot_out_at_third': log[213][3]}
    one['ok'] = one['first'] == 'BS_AIR' and one['second_while_stuck'] == 'AIR_ATTACK' and one['shot_out_at_second'] and \
        one['third_after_gone'] == 'BS_AIR' and not one['shot_out_at_third']
    res['one_projectile'] = one; ok_all &= one['ok']
    print('one projectile', one, flush=True)
    # the jumps unpoked (a player's press): up / forward, at the 3rd / 11th / 25th airborne frame
    free = []
    for jump in ('', 'R'):
        for at in (3, 11, 25):
            b.load(start); b.run(30)
            en = [i for i in range(1, 8) if b.states[b.fget(i, 'state')] not in ('OFF', 'DEAD') and b.fget(i, 'team') == 1]
            cam = b.r(b.syms['cam_x'], 2); b.place(0, x=cam + 80, z=b.fget(en[0], 'z')); b.fset(0, 'facing', 1)
            air_t = 0; lg = []
            for f in range(160):
                if b.states[b.fget(0, 'state')] == 'AIR': air_t += 1
                k_ = ('b' + jump) if f < 5 else 'Da' if air_t in (at - 1, at) else ''
                for i in en: b.place(i, x=b.fget(0, 'x') - 150)
                b.run(1, p1=k_)
                lg.append((b.states[b.fget(0, 'state')], b.fget(0, 'spec_id'), b.fget(0, 'y'), shuriken_of(b) is not None))
            sp = [q for q in lg if q[0] == 'SPECIAL']
            ent = {'jump': 'forward' if jump else 'up', 'airborne_frame': at, 'role': sorted({q[1] for q in sp}),
                   'height_at_start': round(sp[0][2], 1) if sp else None, 'shuriken': any(q[3] for q in lg),
                   'lands': bool(sp) and lg[-1][2] == 0}
            ent['ok'] = ent['role'] == [BS_AIR] and ent['shuriken'] and ent['lands']
            free.append(ent); ok_all &= ent['ok']
            print('unpoked', ent, flush=True)
    res['unpoked'] = free
    res['all_ok'] = bool(ok_all)
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print('ALL OK' if ok_all else 'FAILURES')

if __name__ == '__main__':
    main()
