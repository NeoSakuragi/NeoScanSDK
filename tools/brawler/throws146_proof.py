#!/usr/bin/env python3
"""TODO #146 proof: the throw system rebuilt, pilot Terry (KOF98) and Geese (KOF96). Our emulator only: the source game
through `emu/neogeo_sdl --capture` (tools/kof96/capture/emu.py, snapshots), the brawler through the Geolith harness
(harness.py) on a `make AI_OFF=1` build (the test drives the enemies).

    python3 throws146_proof.py OUT_DIR [kof|brawler|hold|group|all]

  kof      each pilot throw played in its game (the fighter's reload state c<id>, P2 close: Yuri), every frame
           snapshotted; the walk of tools/kof96/throwrom.py checked against the capture (thrower state / step / x,
           victim state / x / height)
  brawler  the same throw in the brawler (P1 walks into an enemy: the grab, then forward+A / back+A): per frame P1 /
           victim state, frame, place, draw order; contact sheets OUT/<fighter>_<throw>.png: the source game above, the
           brawler below, frame for frame from the throw's first frame, the release, the landing and the CONTROL RETURN
           frame marked (a thick frame + its label); the conversion sheet OUT/<fighter>_<throw>_sheet.txt
  hold     the 3-hit hold (hit, hit, finisher) and the hold rule (no escape while hit, escape ~1.5 s after the last hit),
           contact sheet OUT/<fighter>_hold.png
  group    each throw into a group of 3 enemies standing in its path: how many fall (thrown body, spawn.body)
OUT/summary.json: every timing and check; OUT/timings.txt the readable log."""
import json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture'))
from PIL import Image, ImageDraw
import rom96, throwrom

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
WHAT = sys.argv[2] if len(sys.argv) > 2 else 'all'
PILOT = [('terry', 'kof98', 3, 0), ('geese', 'kof96', 24, 10)]     # brawler name, game, KOF id, bm_chars index
THROWS = {'throw_c': ('Rc', 'Ra'), 'throw_d': ('Rd', 'La')}         # KOF input (forward+C / forward+D), brawler (fwd / back + A)
SUMMARY = os.path.join(OUT, 'summary.json')
summary = json.load(open(SUMMARY)) if os.path.exists(SUMMARY) else {}
def save(): json.dump(summary, open(SUMMARY, 'w'), indent=1)

# ---- the source game ---------------------------------------------------------------------------------------------------
POS = '108118=01,108119=B0,108318=01,108319=E8'            # P1 $1B0, P2 $1E8: midscreen, close (capture/throws96.py)
def kof_capture(game, cid, key):
    """the throw in its game: (rows [(P1 state, step, x, P2 state, x, height)], first throw frame index, snapshot dir)"""
    import emu, analyze as A
    from timeline import seqs
    d = os.path.join(OUT, f'kof_{game}_{cid}_{key}'); os.makedirs(d, exist_ok=True)
    out = os.path.join(d, 'cap.txt'); S = 40
    s1, s2 = seqs(f'p1 {S} 40 R; p1 {S + 26} 3 {THROWS[key][0]}', S + 260)
    emu.run(game, out, s1, s2, [f'{S - 2}:{POS}'], reload=f'c{cid}', reload_frames=[S - 4],
            snaps=list(range(S + 20, S + 230)), snapdir=d, timeout=900)
    r1, r2 = A.load(out, 1), A.load(out, 2)
    st = throwrom.build(rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game), game, cid, key, cid)['thrower_state']
    g0 = next(i for i in range(S, len(r1)) if A.state_of(r1[i][3]) == st)
    rows = [(A.state_of(r1[i][3]), r1[i][3][0x80 // 2], round(A.x_of(r1[i][3]), 1), A.state_of(r2[i][3]), round(A.x_of(r2[i][3]), 1),
             round(A.y_of(r2[i][3]), 1)) for i in range(g0, min(len(r1), g0 + 160))]
    frame0 = int(open(out).read().splitlines()[g0].split()[0])
    return rows, frame0, d

def kof_snap(d, frame):
    p = os.path.join(d, f'snap_{frame}.ppm')
    return Image.open(p).convert('RGB') if os.path.exists(p) else None

def kof_check(game, cid, key):
    """the walk vs the capture in our emulator: the victim there is P2 of the reload state (Yuri, id 8)"""
    rows, f0, d = kof_capture(game, cid, key)
    m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
    w, W = throwrom.walk(m, game, cid, key, 8)
    bad, n = [], 0
    x0 = rows[0][2]
    for r in w:
        if r['f'] >= len(rows): break
        g = rows[r['f']]
        if not r['t'][6]:
            if (g[0], g[1]) != (r['t'][0], r['t'][1]) or abs(g[2] - x0 - r['t'][3]) > 1: bad.append((r['f'], 'thrower', g[:3], r['t'][:4]))
        if not r['v'][5]:
            if g[3] != r['v'][0] or abs(g[4] - x0 - r['v'][2]) > 1 or abs(g[5] - r['v'][3]) > 1: bad.append((r['f'], 'victim', g[3:], r['v'][:4]))
        n += 1
    return dict(frames=n, mismatches=len(bad), first=bad[:6], kof_frame0=f0, dir=d)

# ---- the brawler ---------------------------------------------------------------------------------------------------------
B = None
def brawler():
    global B
    if B is None:
        from harness import Brawler
        B = Brawler()
    return B

ENEMY, GROUP = 2, (3, 4, 5)
def setup(b, start, x1=160):
    b.load(start); st = b.states.index
    for i in range(8):
        if b.fget(i, 'ch') == 0: continue
        b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
        b.fset(i, 'frame_ovr', 0xFFFF); b.fset(i, 'held', 0); b.intent(i)
    b.place(0, x=x1, z=30); b.fset(0, 'facing', 1)
    b.place(ENEMY, x=x1 + 30, z=30); b.fset(ENEMY, 'facing', 0xFF)
    for j, i in enumerate(GROUP):
        if b.fget(i, 'ch'): b.place(i, x=900 + 40 * j, z=30)
    b.run(1)

def p1row(b):
    S = b.states
    return dict(st=S[b.fget(0, 'state')], fr=b.fget(0, 'frame_ovr'), x=round(b.fget(0, 'x'), 1), y=round(b.fget(0, 'y'), 1),
                face=b.fget(0, 'facing'), zf=b.fget(0, 'zfront'), srow=b.fget(0, 'srow'),
                vst=S[b.fget(ENEMY, 'state')], vfr=b.fget(ENEMY, 'frame_ovr'), vanim=b.fget(ENEMY, 'anim'),
                vx=round(b.fget(ENEMY, 'x'), 1), vy=round(b.fget(ENEMY, 'y'), 1), vzf=b.fget(ENEMY, 'zfront'),
                vhp=b.fget(ENEMY, 'hp'), vsrow=b.fget(ENEMY, 'srow'))

def walk_in(b):
    """P1 walks into the enemy: the grab"""
    for f in range(60):
        b.run(1, p1='R')
        if b.states[b.fget(0, 'state')] == 'GRAB': return f
    raise RuntimeError('no grab: ' + b.brief())

def brawler_throw(k, start, key, shots_dir, n=150, shots=True):
    b = brawler(); setup(b, start); walk_in(b); b.run(6)
    rows, imgs = [], []
    b.pad = [set(THROWS[key][1]), set()]
    for f in range(n):
        keys = THROWS[key][1] if f < 2 else ''
        if shots:
            b.pad = [set(keys), set()]; p = os.path.join(shots_dir, f'b_{f:03d}.png'); b.screenshot(p); imgs.append(p)
        else: b.run(1, p1=keys)
        rows.append(p1row(b)); rows[-1]['cx'] = screen_x(b, 0)
        if f > 10 and rows[-1]['st'] not in ('THROW',) and rows[-1]['vst'] in ('DOWN', 'GETUP', 'IDLE') and f > 40: break
    t0 = next(i for i, r in enumerate(rows) if r['st'] == 'THROW')
    return rows[t0:], imgs[t0:] if shots else []

# ---- sheets ----------------------------------------------------------------------------------------------------------------
def label_box(d, x, y, w, h, thick):
    for t in range(thick): d.rectangle([x + t, y + t, x + w - 1 - t, y + h - 1 - t], outline='black')

def crop(im, cx, w=240, h=160):
    """a window of the frame around world-screen x cx (both fighters), the floor near its bottom"""
    W_, H_ = im.size; x0 = max(0, min(W_ - w, int(cx - w / 2))); y0 = H_ - h - 10
    return im.crop((x0, y0, x0 + w, y0 + h))

def sheet(title, top, bottom, marks, out, every=3, cols=8):
    """top / bottom: per frame an image (or None); marks: {frame: label}; frames every `every` + every marked frame"""
    n = max(len(top), len(bottom))
    pick = sorted(set(range(0, n, every)) | {f for f in marks if f < n})
    w, h = 240, 160; lab = 30
    if not top: return sheet1(title, bottom, marks, out, every, cols)
    rows_ = (len(pick) + cols - 1) // cols
    S = Image.new('RGB', (cols * (w + 6) + 70, 24 + rows_ * (2 * h + lab + 14)), 'white'); d = ImageDraw.Draw(S)
    d.text((4, 4), title, fill='black')
    for j, f in enumerate(pick):
        X = 70 + (j % cols) * (w + 6); Y = 24 + (j // cols) * (2 * h + lab + 14)
        if j % cols == 0: d.text((4, Y + lab + 4), 'source', fill='black'); d.text((4, Y + lab + h + 6), 'brawler', fill='black')
        d.text((X + 2, Y + 2), f'frame {f}', fill='black')
        if f in marks: d.text((X + 2, Y + 15), marks[f], fill='black')
        for k, (seq, yy) in enumerate(((top, Y + lab), (bottom, Y + lab + h + 2))):
            im = seq[f] if f < len(seq) else None
            if im is not None: S.paste(im, (X, yy))
            else: d.text((X + 60, yy + 70), '(over)', fill='black')
            label_box(d, X - 1, yy - 1, w + 2, h + 2, 5 if 'CONTROL' in marks.get(f, '') else 1)
    S.save(out)

def sheet1(title, seq, marks, out, every, cols):
    w, h = seq[0].size if seq else (240, 160)
    """one row of pictures per line (no source game)"""
    pick = sorted(set(range(0, len(seq), every)) | {f for f in marks if f < len(seq)})
    lab = 30; rows_ = (len(pick) + cols - 1) // cols
    S = Image.new('RGB', (cols * (w + 6) + 10, 24 + rows_ * (h + lab + 8)), 'white'); d = ImageDraw.Draw(S)
    d.text((4, 4), title, fill='black')
    for j, f in enumerate(pick):
        X = 6 + (j % cols) * (w + 6); Y = 24 + (j // cols) * (h + lab + 8)
        d.text((X + 2, Y + 2), f'frame {f}', fill='black')
        if f in marks: d.text((X + 2, Y + 15), marks[f], fill='black')
        S.paste(seq[f], (X, Y + lab)); label_box(d, X - 1, Y + lab - 1, w + 2, h + 2, 4 if 'HIT' in marks.get(f, '') else 1)
    S.save(out)

def conv_sheet(name, game, cid, key, b_, path):
    s = b_['sheet']; L = []
    L.append(f'{name} {key} ({game} id {cid}): {INPUTS[key]} - read from the ROM (tools/kof96/throwrom.py), no capture')
    L.append(f'  code: thrower {s["code"]["thrower"]}, victim {s["code"]["victim"]}; victim list {s["list"]["base"]} x {s["list"]["size"]} bytes (KOF entry per thrower step)')
    L.append(f'  thrower state {s["thrower_state"]}; rows {s["rows"]} (1 row = 1 frame at speed 1x)')
    L.append(f'  impacts (entry flag 1: a blow): {s["impacts"]}; release (entry flag $40) row {s["release"]}; landing row {s["land"]}')
    L.append(f'  the code\'s end (jmp neutral) row {s["code_end"]}; victim lying (its part ends) row {s["down"]}')
    L.append(f'  CONTROL RETURN row {s["ret"]}: {s["ret_why"]}')
    L.append('  victim flight (the code\'s states -> the brawler\'s knockdown animations): ' + '; '.join(s['flight']))
    L.append('  the walk:'); L += ['    ' + x for x in s['walk']]
    L.append('  rows: row | thrower state.step frame x | victim state.step dx dy | marks')
    for i, (tl, v) in enumerate(zip(b_['timeline'], b_['victims'][cid])):
        r = b_['raw'][i]; mk = []
        if i in s['impacts']: mk.append('BLOW')
        if i == s['release']: mk.append('RELEASE')
        if i == s['land']: mk.append('LAND')
        if i == s['ret']: mk.append('CONTROL RETURN')
        if i == s['code_end']: mk.append('code end')
        if i == s['down']: mk.append('victim down')
        L.append(f'    {i:3d} | {r["t"][0]}.{r["t"][1]} f{tl[0]} x{tl[1]:+d}{" turned" if tl[3] else ""} | {v[5]} {v[1]:+d} {v[2]:+d}{" (" + v[6] + ")" if len(v) > 6 and v[6] else ""} | {" ".join(mk)}')
    open(path, 'w').write('\n'.join(L) + '\n')
INPUTS = throwrom.INPUTS

def screen_x(b, i):
    c = b.r(b.syms['cam_x'], 2) if 'cam_x' in b.syms else 0
    return b.fget(i, 'x') - (c - 65536 if c > 32767 else c)

def run_throws():
    from harness import Brawler
    b = brawler(); log = summary.setdefault('throws', {})
    for name, game, cid, k in PILOT:
        b.pick(k, unlock=True); start = b.save()
        m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
        for key in THROWS:
            built = throwrom.build(m, game, cid, key, cid)
            conv_sheet(name, game, cid, key, built, os.path.join(OUT, f'{name}_{key}_sheet.txt'))
            kc = kof_check(game, cid, key)
            krows, f0, kd = kof_capture(game, cid, key) if False else (None, kc['kof_frame0'], kc['dir'])
            top = []
            for f in range(160):
                im = kof_snap(kd, f0 + f)
                top.append(crop(im, 160) if im else None)
            sd = os.path.join(OUT, f'_b_{name}_{key}'); os.makedirs(sd, exist_ok=True)
            rows, imgs = brawler_throw(k, start, key, sd)
            bottom = []
            for r, p in zip(rows, imgs):
                im = Image.open(p).convert('RGB'); bottom.append(crop(im, r['cx'] + 20))
            # the brawler's measured points: thrower leaves THROW (control return), victim's release / landing / down
            ret_b = next((i for i, r in enumerate(rows) if r['st'] != 'THROW'), None)
            down_b = next((i for i, r in enumerate(rows) if r['vst'] == 'DOWN'), None)
            behind = all(r['zf'] == 1 and r['vzf'] == 0 for r in rows[:ret_b or len(rows)])
            marks = {built['ret']: 'CONTROL RETURN (chosen)'}
            if built['release'] is not None: marks[built['release']] = 'RELEASE'
            if built['land'] is not None: marks[built['land']] = marks.get(built['land'], '') + ' LAND'
            for i in built['impacts']: marks[i] = (marks.get(i, '') + ' BLOW').strip()
            if built['end'] != built['ret']: marks[built['end']] = (marks.get(built['end'], '') + ' (KOF code end)').strip()
            sheet(f'{name} {key} ({INPUTS[key]}): {game} above (victim: its reload state P2), brawler below (victim: the stage\'s enemy). '
                  f'Frame 0 = the throw\'s first frame. Control return row {built["ret"]} ({built["sheet"]["ret_why"]})',
                  top, bottom, marks, os.path.join(OUT, f'{name}_{key}.png'))
            shutil.rmtree(sd)
            log[f'{name}:{key}'] = dict(kof_walk_vs_capture=kc, rows=built['sheet']['rows'], impacts=built['impacts'],
                                        release=built['release'], land=built['land'], victim_down=built['down'],
                                        kof_code_end=built['end'], control_return=built['ret'], why=built['sheet']['ret_why'],
                                        brawler_thrower_frames=ret_b, brawler_victim_down=down_b, victim_behind=behind,
                                        brawler_rows=[[r['st'], r['fr'], r['x'], r['y'], r['vst'], r['vx'], r['vy'], r['vzf'], r['zf'], r['vhp']] for r in rows])
            save()
            print(name, key, 'walk vs game:', kc['frames'], 'frames,', kc['mismatches'], 'mismatches; control return', built['ret'],
                  'brawler thrower frames', ret_b, 'victim down at', down_b, 'behind', behind, flush=True)

def run_hold():
    b = brawler(); log = summary.setdefault('hold', {})
    for name, game, cid, k in PILOT:
        b.pick(k, unlock=True); start = b.save()
        # 1. three hits (hit, hit, finisher), each pressed once the last is over
        setup(b, start); walk_in(b)
        sd = os.path.join(OUT, f'_h_{name}'); os.makedirs(sd, exist_ok=True)
        rows, imgs, press_at = [], [], []
        for f in range(120):
            r = p1row(b); keys = ''
            if r['st'] == 'GRAB' and r['srow'] == 0 and len(press_at) < 3 and (not press_at or f - press_at[-1] > 4): keys = 'a'; press_at.append(f)
            p = os.path.join(sd, f'h_{f:03d}.png'); b.pad = [set(keys), set()]; b.screenshot(p); imgs.append(p)
            rows.append(p1row(b)); rows[-1]['cx'] = screen_x(b, 0)
            if f > 20 and rows[-1]['st'] in ('IDLE', 'WALK') : break
        hits = [i for i in range(1, len(rows)) if rows[i]['vhp'] < rows[i - 1]['vhp']]
        bottom = [crop(Image.open(p).convert('RGB'), r['cx'] + 20) for p, r in zip(imgs, rows)]
        marks = {f: 'A pressed' for f in press_at}
        for i in hits: marks[i] = (marks.get(i, '') + ' HIT').strip()
        sheet(f'{name}: the hold, 3 hits (hit, hit, finisher: knockdown). A pressed as soon as the last hit ended', [], bottom, marks,
              os.path.join(OUT, f'{name}_hold.png'), every=2)
        shutil.rmtree(sd)
        startup = [h - p for p, h in zip(press_at, hits)]
        fin_state = rows[hits[-1] + 2]['vst'] if len(hits) >= 3 and hits[-1] + 2 < len(rows) else None
        # 2. the hold rule: no hits -> the victim breaks free at GRAB_TIME; hits keep it (a hit every 40 frames: still
        #    held 90 frames after the grab)
        setup(b, start); walk_in(b); g = 0
        while b.states[b.fget(0, 'state')] == 'GRAB' and g < 300: b.run(1); g += 1
        free_after = g
        setup(b, start); walk_in(b); g = 0; held_long = None
        last_hit_end = None
        for f in range(400):
            b.run(1, p1='a' if f in (40, 100) else '')
            if f > 100 and last_hit_end is None and b.fget(0, 'srow') == 0: last_hit_end = f
            if b.states[b.fget(0, 'state')] != 'GRAB': held_long = f; break
        log[name] = dict(press_frames=press_at, hit_frames=hits, startup_frames=startup, hp=[r['vhp'] for r in rows][-1],
                         victim_after_finisher=fin_state, escape_without_hits_after=free_after,
                         two_hits_at_40_100_hold_ends_at=held_long, last_hit_ended_at=last_hit_end,
                         escape_after_last_hit=(held_long - last_hit_end) if held_long and last_hit_end else None)
        save(); print(name, 'hold:', log[name], flush=True)

def run_group():
    """each throw into 3 enemies standing where its body comes down (its landing point from the decoded script, and 30 px
    either side along the throw), on P1's depth line +-4: how many fall, when, life lost; a picture every 4 frames"""
    b = brawler(); log = summary.setdefault('group', {})
    for name, game, cid, k in PILOT:
        b.pick(k, unlock=True); start = b.save()
        m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
        for key in THROWS:
            built = throwrom.build(m, game, cid, key, cid)
            L = built['land']; landx = built['timeline'][min(L, len(built['timeline']) - 1)][1] + built['victims'][cid][L][1]
            setup(b, start, x1=60 if landx > 0 else 250)        # room on the screen (the camera holds it)
            have = [i for i in GROUP if b.fget(i, 'ch')][:3]
            walk_in(b); b.run(4)
            x0 = b.fget(0, 'x'); d = 1 if landx > 0 else -1
            placed = [landx - 30 * d, landx, landx + 30 * d]
            for j, i in enumerate(have):
                b.place(i, x=x0 + placed[j], z=b.fget(0, 'z') + (j - 1) * 4); b.fset(i, 'facing', (-d) & 0xFF)
            b.run(1)
            hp0 = {i: b.fget(i, 'hp') for i in have}; fell = {}; shots = []
            sd = os.path.join(OUT, f'_g_{name}_{key}'); os.makedirs(sd, exist_ok=True)
            for f in range(120):
                keys = THROWS[key][1] if f < 2 else ''
                if f % 4 == 0 and f <= 96:
                    p = os.path.join(sd, f'{f:03d}.png'); b.pad = [set(keys), set()]; b.screenshot(p); shots.append((f, p, screen_x(b, 0)))
                else: b.run(1, p1=keys)
                for i in have:
                    if b.states[b.fget(i, 'state')] == 'KNOCKDOWN' and i not in fell: fell[i] = f
            seq = [crop(Image.open(p).convert('RGB'), cx + landx / 2, 300, 170) for f, p, cx in shots]
            sheet1(f'{name} {key}: thrown into 3 enemies standing at {placed} px (its landing point and 30 px either side); '
                   f'fell: {len(fell)} (frames {sorted(fell.values())}); a picture every 4 frames (label k = frame 4k)', seq, {}, os.path.join(OUT, f'{name}_{key}_group.png'), 1, 9)
            shutil.rmtree(sd)
            log[f'{name}:{key}'] = dict(group=len(have), fell=len(fell), fell_frames=sorted(fell.values()),
                                        hp_lost=[hp0[i] - b.fget(i, 'hp') for i in have], placed_dx=placed)
            save(); print(name, key, 'group of', len(have), '-> fell', len(fell), log[f'{name}:{key}'], flush=True)

def run_roster():
    """every roster fighter: grab, both throws, a 3-hit hold: the thrower acts again, the victim lies down, the victim
    behind the grabber on every held / thrown frame (the generic rules apply roster-wide)"""
    b = brawler(); log = summary.setdefault('roster', {})
    names = [r['name'] for r in json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))['roster']]
    for k, name in enumerate(names):
        if os.environ.get('ONLY') and name not in os.environ['ONLY'].split(','): continue
        b.pick(k, unlock=True); start = b.save(); out = {}
        try: setup(b, start, x1=140); walk_in(b)
        except RuntimeError:                                       # no throw script: no grab (SS4 / WHP / Kizuna fighters)
            log[name] = dict(ok=None, why='no throw: walking into an enemy does not grab'); save(); print(name, log[name]); continue
        for key in THROWS:
            setup(b, start, x1=140); walk_in(b); b.run(3)
            ret = down = None; behind = True
            for f in range(300):
                b.run(1, p1=THROWS[key][1] if f < 2 else '')
                r = p1row(b)
                if r['st'] == 'THROW' and not (r['zf'] == 1 and r['vzf'] == 0): behind = False
                if ret is None and r['st'] != 'THROW' and f > 1: ret = f
                if down is None and r['vst'] == 'DOWN': down = f
                if ret is not None and down is not None: break
            out[key] = dict(control_return=ret, victim_down=down, behind=behind, hp=b.fget(ENEMY, 'hp'))
        setup(b, start, x1=140); walk_in(b); hits = 0; hp0 = b.fget(ENEMY, 'hp'); vst = None
        for f in range(150):
            b.run(1, p1='a' if f % 6 == 0 else '')
            if b.states[b.fget(0, 'state')] not in ('GRAB', 'THROW'): break
        out['hold'] = dict(hp_lost=hp0 - b.fget(ENEMY, 'hp'), victim=b.states[b.fget(ENEMY, 'state')], frames=f)
        out['ok'] = all(out[t]['control_return'] and out[t]['victim_down'] and out[t]['behind'] for t in THROWS) and out['hold']['victim'] == 'KNOCKDOWN'
        log[name] = out; save(); print(name, out, flush=True)

if __name__ == '__main__':
    if WHAT in ('kof',):
        for name, game, cid, k in PILOT:
            for key in THROWS:
                kc = kof_check(game, cid, key); summary.setdefault('kof', {})[f'{name}:{key}'] = kc; save(); print(name, key, kc)
    if WHAT in ('brawler', 'all'): run_throws()
    if WHAT in ('hold', 'all'): run_hold()
    if WHAT in ('group', 'all'): run_group()
    if WHAT in ('roster', 'all'): run_roster()
