#!/usr/bin/env python3
"""TODO #166 proof: throws round 2 (Bruno's notes on 0.0.73's Geese / Terry pilot) + the death / respawn sequence. Our
emulator only: the source games through `emu/neogeo_sdl --capture` (tools/kof96/capture/emu.py), the brawler through
the Geolith harness (harness.py) on a `make AI_OFF=1` build (the test drives the enemies).

    python3 throws166_proof.py OUT_DIR [a|b|c|d|e|all]

  a  the catch is silent, the throw sound + the throw-start effect at the throw's start: per pilot throw (Terry KOF98,
     Geese KOF96, forward / back + A) the sound bytes the game queued each frame from the walk-in to the end (sound log
     OUT/a_sound.txt) next to the source game's (SNDLOG), and a sheet OUT/a_<fighter>_<throw>.png: the source game above,
     the brawler below, frame for frame from the throw's first frame (the effect's frames marked)
  b  the hold hits hit the crowd: the held enemy + two enemies standing beside it + one far away; 3 hits (hit, hit,
     finisher): who lost life / reeled / fell on which hit, sparks shown (OUT/b_<fighter>_crowd.png)
  c  the hold hit's move per fighter: every fighter's close-normal startups and the choice (build/hold_hits.json ->
     OUT/c_startups.txt), Terry's down-forward+C in the hold (OUT/c_terry_hold.png)
  d  the finisher is a normal hit: C (a special) and D (the fury) pressed in its hit-stop cancel it, the victim juggled
     (OUT/d_<fighter>_<special|fury>.png)
  f  every throw's last impact is a normal hit ("cancels" rule 4, feedback 20261006-194211-5d29): per roster fighter and
     throw (forward / back + A; its last impact row from build/bm_chars.c), C (a special) or D (the fury) pressed 12
     frames before the first legal frame (buffered), C / down+D 2 frames after it, C CANCEL_BUF + 6 before it (too early:
     nothing then): P1 SPECIAL on the first legal frame (the frame after the impact row shows, after its hit-stop: Ryo's
     freeze; the control return when the impact comes after it: Terry, Geese), the victim plays its script on to its end;
     a throw with no impact row: a C before its end does nothing (OUT/f_throws.txt, OUT/f_terry_throw_c_fury.png)
  g  Bruno's own inputs (bundle 20261006-194211-5d29, Terry): each of his throws replayed with his pads frame for frame
     from his forward / back + A to 75 frames on (mirrored when he faced left): the cancel fires on his own presses
     (OUT/g_bruno.txt, OUT/g_bruno_<frame>.png)
  k  KOF98's own special-cancel window on a normal (the model for f's window): Kyo vs Yuri (state c0), close B / close C
     then 236A, the A press on every frame around the hit: which presses cancel and when the special starts
     (OUT/k_kof98.txt)
  e  the death / respawn: P1 (Terry) on his last hit with lives left: down, blinking + the death voice, the drop from
     above the screen (untouchable), the landing knocks every enemy on screen down (OUT/e_respawn.png); with no life
     left: the blink, then the CONTINUE? overlay (OUT/e_continue.png)
OUT/summary166.json: every check."""
import json, os, shutil, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture'))
from PIL import Image, ImageDraw
import rom96, throwrom

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
WHAT = sys.argv[2] if len(sys.argv) > 2 else 'all'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
PILOT = [('terry', 'kof98', 3, 0), ('geese', 'kof96', 24, 10)]     # brawler name, game, KOF id, bm_chars index
THROWS = {'throw_c': ('Rc', 'Ra'), 'throw_d': ('Rd', 'La')}         # KOF input, brawler (forward / back + A)
SUMMARY = os.path.join(OUT, 'summary166.json')
summary = json.load(open(SUMMARY)) if os.path.exists(SUMMARY) else {}
def save(): json.dump(summary, open(SUMMARY, 'w'), indent=1)
ENEMY, CROWD, FAR = 2, (3, 4), 5

B = None
def brawler():
    global B
    if B is None:
        from harness import Brawler
        B = Brawler()
    return B

# ---- the sound queue (sound.c q / qt): the bytes queued each frame ---------------------------------------------------
class Snd:
    def __init__(self, b): self.b = b; self.qt = b.r(b.syms['qt'], 1); self.log = []
    def __call__(self, b):
        qt = b.r(b.syms['qt'], 1); out = []
        while self.qt != qt: out.append(b.r(b.syms['q'] + self.qt, 1)); self.qt = (self.qt + 1) & 31
        if out: self.log.append((b.frame, out))
        return out
def pairs(bs): return [f'{bs[i]:02X} {bs[i + 1]:02X}' for i in range(0, len(bs) - 1, 2)]

# ---- shared steps --------------------------------------------------------------------------------------------------------
def setup(b, start, x1=160):
    b.load(start); st = b.states.index
    for i in range(8):
        if b.fget(i, 'ch') == 0 or (i == 1 and b.fget(i, 'state') == st('OFF')): continue   # (P2's slot stays out of play)
        b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
        b.fset(i, 'frame_ovr', 0xFFFF); b.fset(i, 'held', 0); b.intent(i)
    b.place(0, x=x1, z=30); b.fset(0, 'facing', 1)
    b.place(ENEMY, x=x1 + 30, z=30); b.fset(ENEMY, 'facing', 0xFF)
    for j, i in enumerate((3, 4, 5)):
        if b.fget(i, 'ch'): b.place(i, x=900 + 40 * j, z=30)
    b.run(1)
def S(b, i): return b.states[b.fget(i, 'state')]
def walk_in(b, each=None):
    for f in range(60):
        b.run(1, p1='R', each=each)
        if S(b, 0) == 'GRAB': return f
    raise RuntimeError('no grab: ' + b.brief())
def screen_x(b, i):
    c = b.r(b.syms['cam_x'], 2); return b.fget(i, 'x') - (c - 65536 if c > 32767 else c)
def shot(b, path, keys='', each=None):
    b.pad = [set(keys), set()]; b.screenshot(path)
    if each: each(b)
    return Image.open(path).convert('RGB')
def crop(im, cx, w=240, h=160):
    W_, H_ = im.size; x0 = max(0, min(W_ - w, int(cx - w / 2))); y0 = H_ - h - 10
    return im.crop((x0, y0, x0 + w, y0 + h))
def sheet(title, rows_of_imgs, labels, out, names=None, cols=8):
    """rows_of_imgs: [seq, ...] (each a list of images per frame, None = none); labels: per frame index a label"""
    n = max(len(s) for s in rows_of_imgs); lab = 30; nr = len(rows_of_imgs)
    w, h = next(im.size for s in rows_of_imgs for im in s if im is not None)
    pick = list(range(n)); R = (len(pick) + cols - 1) // cols
    Sh = Image.new('RGB', (cols * (w + 6) + 70, 24 + R * (nr * (h + 2) + lab + 12)), 'white'); d = ImageDraw.Draw(Sh)
    d.text((4, 4), title, fill='black')
    for j, f in enumerate(pick):
        X = 70 + (j % cols) * (w + 6); Y = 24 + (j // cols) * (nr * (h + 2) + lab + 12)
        d.text((X + 2, Y + 2), labels[f][0] if f < len(labels) else '', fill='black')
        d.text((X + 2, Y + 15), labels[f][1] if f < len(labels) else '', fill='black')
        for k, seq in enumerate(rows_of_imgs):
            yy = Y + lab + k * (h + 2)
            if j % cols == 0 and names: d.text((4, yy + 70), names[k], fill='black')
            im = seq[f] if f < len(seq) else None
            if im is not None: Sh.paste(im, (X, yy))
            mark = f < len(labels) and labels[f][2]
            for t in range(4 if mark else 1): d.rectangle([X - 1 + t, yy - 1 + t, X + w - t, yy + h - t], outline='black')
    Sh.save(out)

# ---- (a) silent catch, throw sound + effect at the start --------------------------------------------------------------
def kof_capture(game, cid, key, d):
    """the throw in its game with SNDLOG + snapshots: (P1 state per frame, throw start frame, sound log {frame: [bytes]})"""
    import emu, analyze as A
    from timeline import seqs
    os.makedirs(d, exist_ok=True); out = os.path.join(d, 'cap.txt'); S0 = 40
    s1, s2 = seqs(f'p1 {S0} 40 R; p1 {S0 + 26} 3 {THROWS[key][0]}', S0 + 160)
    emu.run(game, out, s1, s2, ['38:108118=01,108119=B0,108318=01,108319=E8'], reload=f'c{cid}', reload_frames=[S0 - 4],
            snaps=list(range(S0 + 20, S0 + 120)), snapdir=d, timeout=900, extra={'SNDLOG': os.path.join(d, 'snd.txt')})
    r1 = A.load(out, 1)
    m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
    st = throwrom.build(m, game, cid, key, cid)['thrower_state']
    g0 = next(i for i in range(S0, len(r1)) if A.state_of(r1[i][3]) == st)
    frame0 = int(open(out).read().splitlines()[g0].split()[0])
    objs = []                                                    # the effect object (shared effects bank, state 61)
    for l in open(out).read().splitlines():
        p = l.split()
        if len(p) > 5 and any(o.split(':')[2] == '61' and o.split(':')[1] in ('29', '38') and o.split(':')[-1] != 'FFFF' for o in p[5].split(';') if o.count(':') >= 8):
            objs.append(int(p[0]) - frame0)
    seq = [(int(l.split()[0]) - frame0, int(l.split()[1], 16)) for l in open(os.path.join(d, 'snd.txt'))]
    snd = {}                                                     # one byte a frame: a prefix and its code -> one pair
    k = 0
    while k < len(seq):
        f, v = seq[k]
        if v in (0x1A, 0x1C, 0x1E) and k + 1 < len(seq): snd.setdefault(f, []).extend([v, seq[k + 1][1]]); k += 2
        else: snd.setdefault(f, []).extend([v, 0]); k += 1
    return frame0, snd, objs

def run_a():
    b = brawler(); log = summary.setdefault('a', {}); txt = []
    for name, game, cid, k in PILOT:
        b.pick(k, unlock=True); start = b.save()
        for key in THROWS:
            kd = os.path.join(OUT, f'_kof_{name}_{key}'); f0, ksnd, kobj = kof_capture(game, cid, key, kd)
            setup(b, start); snd = Snd(b)
            walk_in(b, each=snd); b.run(6, each=snd)
            catch = [x for x in snd.log]
            sd = os.path.join(OUT, f'_a_{name}_{key}'); os.makedirs(sd, exist_ok=True)
            imgs, lab, rows = [], [], []; t0 = None; snd.log = []
            for f in range(40):
                im = shot(b, os.path.join(sd, f'{f:03d}.png'), THROWS[key][1] if f < 2 else '', snd)
                if t0 is None and S(b, 0) == 'THROW': t0 = f
                on, kk = b.r(b.syms['tfx_on'], 1), b.r(b.syms['tfx_k'], 1)
                rows.append(dict(f=f, st=S(b, 0), srow=b.fget(0, 'srow'), tfx_on=on, tfx_k=kk,
                                 snd=snd.log[-1][1] if snd.log and snd.log[-1][0] == b.frame else []))
                imgs.append(crop(im, screen_x(b, 0) + 20))
            rows = rows[t0:]; imgs = imgs[t0:]
            top = []
            for f in range(len(rows)):
                p = os.path.join(kd, f'snap_{f0 + f}.ppm')
                top.append(crop(Image.open(p).convert('RGB'), 160) if os.path.exists(p) else None)
            first_fx = next((r['f'] - t0 for r in rows if r['tfx_on']), None)
            first_snd = next((r['f'] - t0 for r in rows if any(p == '1A 18' for p in pairs(r['snd']))), None)
            labels = [(f'frame {i}', ('fx %d' % r['tfx_k'] if r['tfx_on'] and r['tfx_k'] != 255 else '') +
                       (' snd ' + ','.join(pairs(r['snd'])) if r['snd'] else ''), r['tfx_on'] and r['tfx_k'] == 0) for i, r in enumerate(rows)]
            sheet(f'{name} {key}: {game} above, brawler below; frame 0 = the throw\'s first frame. KOF\'s effect object (state 61) '
                  f'from frame {kobj[0] if kobj else None}, its sound {[(f, pairs(v)) for f, v in sorted(ksnd.items()) if 0 <= f < 30]}; '
                  f'brawler: effect from frame {first_fx}, sound $1A $18 queued frame {first_snd} (thick frame: the effect\'s first)',
                  [top, imgs], labels, os.path.join(OUT, f'a_{name}_{key}.png'), ['source', 'brawler'])
            shutil.rmtree(sd); shutil.rmtree(kd)
            catch_bytes = [x for _, v in catch for x in v]
            log[f'{name}:{key}'] = dict(catch_sounds=[pairs(v) for _, v in catch], catch_silent=not any(
                                        p in ('1A 18', '1A 19') for _, v in catch for p in pairs(v)),
                                        kof_effect_frames=[kobj[0], kobj[-1]] if kobj else None,
                                        kof_sounds={f: pairs(v) for f, v in sorted(ksnd.items()) if -5 <= f < 40},
                                        brawler_effect_first=first_fx, brawler_effect_frames=sum(1 for r in rows if r['tfx_on']),
                                        brawler_throw_sound_frame=first_snd,
                                        brawler_sounds={r['f'] - t0: pairs(r['snd']) for r in rows if r['snd']})
            txt.append(f'{name} {key}: walk-in + grab + 6 frames held: {log[f"{name}:{key}"]["catch_sounds"] or "nothing"}')
            txt.append(f'   source ({game}, frame 0 = the throw): ' + '; '.join(f'{f}: {" ".join(v)}' for f, v in log[f'{name}:{key}']['kof_sounds'].items()))
            txt.append(f'   brawler (frame 0 = the throw): ' + '; '.join(f'{f}: {" ".join(v)}' for f, v in log[f'{name}:{key}']['brawler_sounds'].items()))
            save(); print(name, key, log[f'{name}:{key}'], flush=True)
    open(os.path.join(OUT, 'a_sound.txt'), 'w').write('\n'.join(txt) + '\n')

# ---- (b) the crowd: hold hits hit every enemy in reach --------------------------------------------------------------------
def hold3(b, each=None, extra=None, n=110, shots=None, cx=None):
    """grab, then A as soon as the last hit ended (3 hits); per frame a row; extra(b, f) -> keys to add"""
    walk_in(b); rows, press = [], []
    for f in range(n):
        keys = ''
        if S(b, 0) == 'GRAB' and b.fget(0, 'srow') == 0 and len(press) < 3 and (not press or f - press[-1] > 4): keys = 'a'; press.append(f)
        if extra: keys += extra(b, f)
        if shots is not None: shots.append(crop(shot(b, os.path.join(OUT, '_tmp.png'), keys, each), (cx or screen_x)(b, 0) + 20))
        else: b.run(1, p1=keys, each=each)
        rows.append({i: (S(b, i), b.fget(i, 'hp')) for i in (0, ENEMY) + CROWD + (FAR,)})
        rows[-1]['spk'] = sum(b.r(b.syms['spk'] + 10 * s, 1) for s in range(4)); rows[-1]['p1'] = (S(b, 0), b.fget(0, 'throw_id'), b.fget(0, 'srow'))
    return rows, press

def run_b():
    b = brawler(); log = summary.setdefault('b', {})
    for name, game, cid, k in PILOT:
        b.pick(k, unlock=True); start = b.save()
        setup(b, start)
        walk_in(b); vx = b.fget(ENEMY, 'x'); z = b.fget(0, 'z')
        setup(b, start)                                          # the crowd: beside the held one (its x, +-6 px deep)
        b.place(3, x=vx + 8, z=z - 6); b.place(4, x=vx - 4, z=z + 6); b.place(FAR, x=vx + 150, z=z)
        for i in (3, 4, FAR): b.fset(i, 'facing', 0xFF)
        imgs = []; rows, press = hold3(b, shots=imgs)
        hits = {i: [f for f in range(1, len(rows)) if rows[f][i][1] < rows[f - 1][i][1] or (rows[f][i][0] in ('HITSTUN', 'KNOCKDOWN') and rows[f - 1][i][0] not in ('HITSTUN', 'KNOCKDOWN'))]
                for i in (ENEMY,) + CROWD + (FAR,)}
        labels = [(f'frame {f}', ('A ' if f in press else '') + ' '.join(f'{i}:{rows[f][i][0][:4]}{rows[f][i][1]}' for i in (ENEMY,) + CROWD),
                   any(f in v for v in hits.values())) for f in range(len(rows))]
        sel = sorted(set(range(0, len(rows), 3)) | {f for v in hits.values() for f in v} | {f + 1 for v in hits.values() for f in v})
        sel = [f for f in sel if f < len(rows)]
        sheet(f'{name}: the hold, 3 hits, enemies 3 / 4 beside the held enemy 2, enemy 5 150 px away. Label: state + life '
              f'per enemy (thick: a hit landed). Hit frames {hits}', [[imgs[f] for f in sel]], [labels[f] for f in sel],
              os.path.join(OUT, f'b_{name}_crowd.png'), ['brawler'])
        out = {str(i): dict(hit_frames=v, hp_end=rows[-1][i][1], state_end=rows[-1][i][0]) for i, v in hits.items()}
        out['press'] = press; out['ok'] = all(len(hits[i]) >= 3 for i in CROWD) and not hits[FAR] and \
            all(rows[-1][i][0] in ('KNOCKDOWN', 'DOWN', 'GETUP') or any(r[i][0] == 'KNOCKDOWN' for r in rows) for i in CROWD)
        out['sparks_on_hit_frames'] = {str(f): rows[f]['spk'] for f in hits[ENEMY]}
        log[name] = out; save(); print(name, 'crowd', out, flush=True)

# ---- (c) the hold hit's move per fighter --------------------------------------------------------------------------------
def run_c():
    d = json.load(open(os.path.join(GAME, 'build', 'hold_hits.json'))); L = []
    L.append('Close-normal startups (frames before the first active step in the source game; the hold squeezes any to 3) and')
    L.append('the hold hit / finisher each fighter plays (game.json roster[].throws.hold, else the fastest close normal):')
    for n, v in d.items():
        st = ', '.join(f'{m}: {f}' for m, f in v['startups'].items())
        L.append(f'  {n:12s} hit = {v["hit"]["move"]} ({v["hit"]["why"]}), finisher = {v["fin"]["move"]} ({v["fin"]["why"]}); {st}')
    open(os.path.join(OUT, 'c_startups.txt'), 'w').write('\n'.join(L) + '\n')
    summary['c'] = {n: dict(hit=v['hit'], startups=v['startups']) for n, v in d.items()}; save()
    b = brawler(); b.pick(0, unlock=True); start = b.save(); setup(b, start)
    imgs = []; rows, press = hold3(b, shots=imgs, n=70)
    labels = [(f'frame {f}', ('A pressed ' if f in press else '') + f'{rows[f]["p1"][0]} srow {rows[f]["p1"][2]}', f in press) for f in range(len(rows))]
    sheet('Terry in the hold: hit = his down-forward+C (KOF98 Back Upper frames), hit, then the finisher (close D)', [imgs], labels,
          os.path.join(OUT, 'c_terry_hold.png'), ['brawler'], cols=10)
    print('c ok', flush=True)

# ---- (d) the finisher cancelled into a special / the fury ------------------------------------------------------------------
def run_d():
    b = brawler(); log = summary.setdefault('d', {})
    for name, game, cid, k in PILOT:
        b.pick(k, unlock=True); start = b.save()
        for what, key in (('special', 'c'), ('special_down', 'Dc'), ('fury', 'd')):
            setup(b, start); state = {'fin': None}
            def extra(b, f):
                if state['fin'] is None and S(b, 0) == 'THROW' and b.fget(0, 'throw_id') == 3: state['fin'] = f   # BT_HOLD_FIN
                return key if state['fin'] is not None and f == state['fin'] + 1 else ''
            imgs = []; rows, press = hold3(b, extra=extra, shots=imgs, n=150)
            fin = state['fin']
            sp = next((f for f in range(len(rows)) if rows[f]['p1'][0] == 'SPECIAL'), None)
            hp = [rows[f][ENEMY][1] for f in range(len(rows))]
            after = [f for f in range(1, len(rows)) if fin is not None and f > fin + 1 and hp[f] < hp[f - 1]]
            labels = [(f'frame {f}', f'P1 {rows[f]["p1"][0]} | 2: {rows[f][ENEMY][0][:5]} {rows[f][ENEMY][1]}' +
                       (f' [{key} pressed]' if fin is not None and f == fin + 1 else ''), f in (fin, sp) or f in after[:1]) for f in range(len(rows))]
            lo = max(0, (fin or 0) - 12); hi = min(len(rows), lo + 64)
            sel = list(range(lo, hi, 2))
            sheet(f'{name}: hold finisher (frame {fin}) cancelled by {key.upper()} pressed in its hit-stop: P1 SPECIAL from frame {sp}, '
                  f'the knocked-down victim hit again on frames {after[:6]} (life {hp[fin] if fin else None} -> {hp[-1]})',
                  [[imgs[f] for f in sel]], [labels[f] for f in sel], os.path.join(OUT, f'd_{name}_{what}.png'), ['brawler'])
            log[f'{name}:{what}'] = dict(finisher_frame=fin, special_from=sp, gap=(sp - fin) if sp and fin else None,
                                         victim_hits_after=after, hp_at_fin=hp[fin] if fin else None, hp_end=hp[-1],
                                         ok=bool(fin and sp and sp - fin <= 12 and after))
            save(); print(name, what, log[f'{name}:{what}'], flush=True)

# ---- (f) every throw's last impact cancels -----------------------------------------------------------------------------
CANCEL_BUF = 24                                                  # fighter.c
def throw_data():
    """build/bm_chars.c: per fighter and throw (nrows, ret, the last impact row: flags 4, None = none)"""
    import re
    src = open(os.path.join(GAME, 'build', 'bm_chars.c')).read(); rows = {}; out = {}
    for m in re.finditer(r'static const bthrow_row_t (\w+)\[\] = \{(.*?)\};\n', src):
        rows[m.group(1)] = [tuple(int(x) for x in r.split(',')) for r in re.findall(r'\{([-\d, ]+)\}', m.group(2))]
    for m in re.finditer(r'static const bthrow_t (\w+)_throws\[BT_COUNT\] = \{(.*?)\};\n', src):
        for t, (n, sp, name, ret) in zip(('throw_c', 'throw_d'), re.findall(r'\{(\d+), (\d+), (\w+), (\d+)', m.group(2))):
            imp = [i for i, r in enumerate(rows[name]) if r[4] & 4]
            out[(m.group(1), t)] = dict(nrows=int(n), ret=int(ret), last=imp[-1] if imp else None)
    return out

def throw_run(b, start, key_throw, press=None, at=None, n=260, shots=None):
    """grab, the throw (key_throw: 'Ra' / 'La' on the first frame), press `press` on frame `at` (frames from the throw's
    first frame); per frame (P1 state, spec_id, victim state, victim life, P1 srow, P1 freeze)"""
    setup(b, start); walk_in(b); rows = []
    for f in range(n):
        keys = key_throw if f == 0 else (press if press and f == at else '')
        if shots is not None: shots.append(crop(shot(b, os.path.join(OUT, '_tmp.png'), keys), screen_x(b, 0) + 20))
        else: b.run(1, p1=keys)
        rows.append((S(b, 0), b.fget(0, 'spec_id'), S(b, ENEMY), b.fget(ENEMY, 'hp'), b.fget(0, 'srow'), b.fget(0, 'freeze')))
    return rows

def run_f():
    b = brawler(); log = summary.setdefault('f', {}); L = []; TD = throw_data()
    roster = json.load(open(os.path.join(GAME, 'game.json')))['roster']
    for k, r in enumerate(roster):
        if r.get('selectable', True) is False: continue
        name = r['name']
        try: b.pick(k, unlock=True)
        except RuntimeError as e: L.append(f'{name}: not on the select screen ({e})'); continue
        start = b.save()
        for tname, key in (('throw_c', 'Ra'), ('throw_d', 'La')):
            td = TD.get((name, tname))
            try: base = throw_run(b, start, key)
            except RuntimeError as e: L.append(f'{name} {tname}: {e}'); print(L[-1]); break
            thr = [f for f in range(len(base)) if base[f][0] == 'THROW']
            if not thr or not td: L.append(f'{name} {tname}: no throw'); print(L[-1]); continue
            ret = thr[-1] + 1                                    # the frame P1 acts again
            if td['last'] is None:                               # no impact row: no cancel, a press before the end is dropped
                rows = throw_run(b, start, key, 'c', ret - 12)
                sp = next((f for f in range(len(rows)) if rows[f][0] == 'SPECIAL'), None)
                out = dict(ok=sp is None, note='no impact row: C pressed 12 frames before the control return does nothing', special_from=sp)
                log[f'{name}:{tname}'] = out; save(); L.append(f'{name} {tname}: no impact row, C +{ret - 12} -> SPECIAL {sp} {"ok" if out["ok"] else "FAIL"}'); print(L[-1]); continue
            if td['last'] < td['ret']:                           # the impact: the frame P1 shows that row; legal after its hit-stop
                imp = next(f for f in thr if base[f][4] - 1 >= td['last']); legal = imp + 1 + base[imp][5]
            else:                                                # past the control return (Terry, Geese): the victim's hit
                imp = [f for f in range(1, len(base)) if base[f][3] < base[f - 1][3]][-1]; legal = ret
            out = dict(impact=imp, control_return=ret, first_legal=legal, last_row=td['last'], ret_row=td['ret'])
            ok = True
            for what, press, at in (('C_buffered', 'c', legal - 12), ('D_buffered', 'd', legal - 12), ('C_after', 'c', legal + 2),
                                    ('D_after', 'Dd', legal + 2), ('C_too_early', 'c', legal - CANCEL_BUF - 6 - base[imp][5])):
                if at < 1: out[what] = 'n/a (the press would fall before the throw)'; continue
                rows = throw_run(b, start, key, press, at)
                sp = next((f for f in range(len(rows)) if rows[f][0] == 'SPECIAL'), None)
                if what == 'C_too_early': want = None; good = sp is None or sp > legal
                else: want = max(legal, at + 1); good = sp == want and (rows[sp][1] == 6) == ('d' in press)   # BS_FURY = BS_COUNT = 6
                vfree = rows[-1][2] != 'THROWN'                  # the victim's script went on to its end
                good = good and vfree
                out[what] = dict(press=at, special_from=sp, expected=want, spec_id=rows[sp][1] if sp is not None else None,
                                 victim_end=rows[-1][2], victim_hp_min=min(r[3] for r in rows), ok=good)
                ok = ok and good
            out['ok'] = ok; log[f'{name}:{tname}'] = out; save()
            L.append(f'{name} {tname}: last impact row {td["last"]} (control return row {td["ret"]}) shown +{imp}, P1 free +{ret}, first legal +{legal}; ' +
                     '; '.join(f'{w} pressed +{v["press"]} -> SPECIAL +{v["special_from"]} ({"fury" if v["spec_id"] == 6 else v["spec_id"]}) '
                               f'{"ok" if v["ok"] else "FAIL"}' for w, v in out.items() if isinstance(v, dict)))
            print(L[-1], flush=True)
    # Terry's forward throw cancelled into the fury: a sheet
    b.pick(0, unlock=True); start = b.save(); base = throw_run(b, start, 'Ra')
    ret = [f for f in range(len(base)) if base[f][0] == 'THROW'][-1] + 1
    imgs = []; rows = throw_run(b, start, 'Ra', 'Dd', ret - 12, n=110, shots=imgs)
    sp = next(f for f in range(len(rows)) if rows[f][0] == 'SPECIAL')
    labels = [(f'frame {f}', f'P1 {rows[f][0][:6]} | 2: {rows[f][2][:6]} {rows[f][3]}' + (' [down+D]' if f == ret - 12 else ''),
               f in (ret - 12, sp)) for f in range(len(rows))]
    sel = list(range(max(0, ret - 16), min(len(rows), ret + 30)))
    sheet(f'terry forward throw: down+D pressed on frame {ret - 12}, 12 before the control return (frame {ret}; the victim lands '
          f'the frame after): the MAX fury from frame {sp}', [[imgs[f] for f in sel]], [labels[f] for f in sel],
          os.path.join(OUT, 'f_terry_throw_c_fury.png'), ['brawler'], cols=8)
    open(os.path.join(OUT, 'f_throws.txt'), 'w').write('\n'.join(L) + '\n')
    log['all_ok'] = all(v['ok'] for kk, v in log.items() if isinstance(v, dict)); save(); print('f all ok', log['all_ok'])

# ---- (g) Bruno's own inputs, his throws -----------------------------------------------------------------------------------
BUNDLE = '/data/feedback/20261006-194211-5d29'
PADKEYS = ((0, 'a'), (8, 'b'), (1, 'c'), (9, 'd'), (4, 'U'), (5, 'D'), (6, 'L'), (7, 'R'))
def run_g():
    raw = open(os.path.join(BUNDLE, 'inputs.bin'), 'rb').read()
    _, _, W, P = struct.unpack_from('<4sIQQ', raw)
    pads = [struct.unpack_from('<HH', raw, 24 + 4 * i)[0] for i in range(P - W)]
    prep = os.path.join(OUT, 'g_throws_0077.json')               # his throws in his own replay (0.0.77): a process of
    subprocess.run([sys.executable, __file__, OUT, 'gprep'], check=True)   # its own (one libretro core per process)
    trace = json.load(open(prep))
    b = brawler(); b.pick(0, unlock=True); start = b.save(); log = summary.setdefault('g', {}); L = []
    for t in trace:
        f0, face = t['start'], t['facing']                       # his forward / back + A frame, his facing
        def keys(p):
            k = ''.join(c for bit, c in PADKEYS if p >> bit & 1)
            return k.translate(str.maketrans('LR', 'RL')) if face < 0 else k
        seq = [keys(pads[f - W]) for f in range(f0, min(P, f0 + 75))]
        imgs = []; setup(b, start); walk_in(b); rows = []
        for f, k in enumerate(seq):
            imgs.append(crop(shot(b, os.path.join(OUT, '_tmp.png'), k), screen_x(b, 0) + 20))
            rows.append((S(b, 0), b.fget(0, 'spec_id'), S(b, ENEMY), b.fget(ENEMY, 'hp')))
        sp = next((f for f in range(len(rows)) if rows[f][0] == 'SPECIAL'), None)
        cd = [(f, seq[f]) for f in range(1, len(seq)) if ('c' in seq[f] and 'c' not in seq[f - 1]) or ('d' in seq[f] and 'd' not in seq[f - 1])]
        out = dict(his_frame=f0, presses=cd, special_from=sp, spec_id=rows[sp][1] if sp is not None else None,
                   in_0077=t['special_from'], ok=(sp is not None) == bool(cd) and (sp is None or t['special_from'] is None or sp < t['special_from']))
        log[str(f0)] = out; save()
        L.append(f'his throw at frame {f0} (facing {face}): C / D presses (frame from his A: keys) {cd}; fixed build: SPECIAL from +{sp} '
                 f'({"fury" if out["spec_id"] == 6 else out["spec_id"]}); 0.0.77 (his replay): SPECIAL from +{t["special_from"]} {"ok" if out["ok"] else "FAIL"}')
        print(L[-1], flush=True)
        if cd:
            labels = [(f'+{f} {seq[f]}', f'P1 {rows[f][0][:6]} | 2: {rows[f][2][:6]} {rows[f][3]}', f == sp or any(f == c[0] for c in cd)) for f in range(len(rows))]
            sheet(f'Bruno\'s throw at frame {f0} of his bundle replayed with his own pads (thick: his C / D presses, the SPECIAL start +{sp})',
                  [[imgs[f] for f in range(20, len(rows))]], labels[20:], os.path.join(OUT, f'g_bruno_{f0}.png'), ['brawler'], cols=10)
    open(os.path.join(OUT, 'g_bruno.txt'), 'w').write('\n'.join(L) + '\n')
    log['all_ok'] = all(v['ok'] for kk, v in log.items() if isinstance(v, dict)); save(); print('g all ok', log['all_ok'])

def run_gprep():
    """his bundle replayed on its own ROM (tools/feedback/pull.py's Core): each throw P1 starts (frame, facing) and the
    frame from it P1 went SPECIAL in that build (None: not within 75 frames)"""
    sys.path.insert(0, os.path.join(HERE, '..', 'feedback')); import pull, harness, ctypes as C
    meta = json.load(open(os.path.join(BUNDLE, 'meta.json')))
    raw = open(os.path.join(BUNDLE, 'inputs.bin'), 'rb').read(); _, _, W, P = struct.unpack_from('<4sIQQ', raw)
    pads = [struct.unpack_from('<HH', raw, 24 + 4 * i) for i in range(P - W)]
    elf = '/data/tmp/rom_0077.elf'                               # the 0.0.77 build's symbols (rebuilt from 8ab9fa0: same sha256)
    lay, fsize, states, syms = harness._layout(GAME)              # (fighter_t is the same in both builds)
    syms['fighters'] = int(next(l.split()[0] for l in subprocess.run(['m68k-linux-gnu-nm', elf], capture_output=True, text=True).stdout.split('\n') if l.endswith(' fighters')), 16)
    core = pull.Core(pull.find_rom(meta), meta['system_type'], meta['hw'], meta.get('memcard', 'on'))
    core.core.retro_get_memory_data.restype = C.c_void_p; core.core.retro_get_memory_size.restype = C.c_size_t
    ram = (C.c_uint8 * core.core.retro_get_memory_size(2)).from_address(core.core.retro_get_memory_data(2))
    core.load(open(os.path.join(BUNDLE, f'snap_{W}.state'), 'rb').read())
    def fg(f):
        off, sz = lay[f]; a = syms['fighters'] + off - 0x100000
        v = int.from_bytes(bytes(ram[a:a + sz]), 'big'); return v - 256 if f == 'facing' and v > 127 else v
    out = []; prev = None
    for i, (p0, p1) in enumerate(pads):
        core.frame(p0, p1); st = states[fg('state')]
        if st == 'THROW' and prev == 'GRAB': out.append(dict(start=W + i - 1, facing=fg('facing'), special_from=None))
        if out and st == 'SPECIAL' and out[-1]['special_from'] is None and W + i - out[-1]['start'] < 75: out[-1]['special_from'] = W + i - out[-1]['start']
        prev = st
    json.dump(out, open(os.path.join(OUT, 'g_throws_0077.json'), 'w'), indent=1)

# ---- (k) KOF98's special-cancel window on a normal -------------------------------------------------------------------
def run_k():
    import emu
    from timeline import seqs
    L = ['KOF98 Kyo vs Yuri (c0), P1 x $180, P2 $1B0: the normal pressed on frame 0, 236 (2 frames each) then A on frame p;',
         'P2 life drop = the hit; P1 state 98 / 89 = close C / B, 156 = 236A (the special). Frames from the normal\'s press.']
    res = {}
    for normal in ('c', 'b'):
        spec, pokes, reload, starts, s = [], [], [], [], 40
        for p in [None] + list(range(8, 26)):
            starts.append((s, p)); reload.append(s - 4); pokes.append(f'{s - 2}:108118=01,108119=80,108318=01,108319=B0')
            spec.append(f'p1 {s} 2 {normal}')
            if p is not None: spec += [f'p1 {s + p - 6} 2 D', f'p1 {s + p - 4} 2 DR', f'p1 {s + p - 2} 2 R', f'p1 {s + p} 2 Ra']
            s += 160
        s1, s2 = seqs('; '.join(spec), s + 20); out = os.path.join(OUT, f'k_kof98_{normal}.cap')
        emu.run('kof98', out, s1, s2, pokes, reload='c0', reload_frames=reload)
        R = {}
        for line in open(out):
            q = line.split(); o = bytes.fromhex(q[3]); v = bytes.fromhex(q[4])
            R[int(q[0])] = (int.from_bytes(o[0x72:0x74], 'big'), int.from_bytes(v[0x138:0x13A], 'big'))
        rows = []
        for s0, p in starts:
            life = [R[f][1] for f in range(s0 - 1, s0 + 120)]
            hit = next((i for i in range(1, len(life)) if life[i] < life[i - 1]), None)
            sp = next((f - s0 for f in range(s0, s0 + 120) if R[f][0] == 156), None)
            rows.append(dict(press=p, hit=hit, special_from=sp))
            L.append(f'close {normal.upper()}: A on +{p}: hit +{hit}, special from +{sp}' + (f' (press {p - hit:+d} from the hit)' if p and hit else ''))
        ok = [r['press'] - r['hit'] for r in rows if r['press'] is not None and r['special_from'] is not None and r['hit']]
        res[normal] = dict(rows=rows, latest_after_hit=max(ok) if ok else None)
        L.append(f'close {normal.upper()}: latest press that cancels: {res[normal]["latest_after_hit"]} frames after the hit')
    open(os.path.join(OUT, 'k_kof98.txt'), 'w').write('\n'.join(L) + '\n'); summary['k'] = res; save(); print('\n'.join(L))

# ---- (e) death -> respawn, and the last life -> continue ------------------------------------------------------------------
def run_e():
    b = brawler(); log = summary.setdefault('e', {})
    b.pick(0, unlock=True); start = b.save()
    for case in ('respawn', 'continue'):
        setup(b, start, x1=120)
        b.w(b.syms['lives'], 1, 2 if case == 'respawn' else 0)
        b.fset(0, 'hp', 1)
        b.place(ENEMY, x=150, z=30)                              # enemy 2 hits P1; 3, 4, 5 stand on screen
        for j, i in enumerate((3, 4, 5)): b.place(i, x=200 + 40 * j, z=20 + 8 * j); b.fset(i, 'facing', 0xFF)
        snd = Snd(b); rows, imgs = [], []; cam = []
        for f in range(330):
            if f == 2: b.intent(ENEMY, press=1)
            if f == 3: b.intent(ENEMY)
            if f % 2 == 0:
                imgs.append((f, crop(shot(b, os.path.join(OUT, '_tmp.png'), '', snd), 160, 320, 200)))
            else: b.run(1, each=snd)
            rows.append(dict(p1=S(b, 0), y=round(b.fget(0, 'y')), inv=b.fget(0, 'inv'), drop=b.fget(0, 'drop'), hp=b.fget(0, 'hp'),
                             lives=b.r(b.syms['lives'], 1), cont=b.r(b.syms['cont_ov'], 1),
                             en=[S(b, i) for i in (2, 3, 4, 5)], snd=snd.log[-1][1] if snd.log and snd.log[-1][0] == b.frame else []))
            if case == 'continue' and rows[-1]['cont'] and f > 10 and len([r for r in rows if r['cont']]) > 30: break
        st = [r['p1'] for r in rows]
        dead = st.index('DEAD') if 'DEAD' in st else None
        ko = [(f, pairs(r['snd'])) for f, r in enumerate(rows) if r['snd'] and dead is not None and dead - 1 <= f <= dead + 1]
        out = dict(dead_from=dead, blink_frames=st.count('DEAD'), ko_sounds=ko)
        if case == 'respawn':
            drop = next((f for f, r in enumerate(rows) if r['drop'] == 1), None)
            land = next((f for f, r in enumerate(rows) if f > (drop or 0) and r['p1'] == 'LAND'), None)
            hit_while_falling = any(r['hp'] < 60 for r in rows[drop:land]) if drop and land else None
            downs = {i: next((f for f in range(land or 0, len(rows)) if rows[f]['en'][k] == 'KNOCKDOWN'), None) for k, i in enumerate((2, 3, 4, 5))} if land else {}
            out.update(drop_from=drop, drop_y0=rows[drop]['y'] if drop is not None else None, land=land,
                       inv_while_falling=all(r['inv'] > 0 for r in rows[drop:land]) if drop and land else None,
                       hp_lost_while_falling=hit_while_falling, lives_after=rows[-1]['lives'],
                       enemies_knocked_down={str(i): f for i, f in downs.items()},
                       ok=bool(dead and drop and land and all(v is not None for v in downs.values()) and rows[-1]['lives'] == 1))
            marks = {dead: 'DEAD (blink + KO voice)', drop: 'respawn: the drop', land: 'LAND: enemies knocked down'}
        else:
            off = next((f for f, r in enumerate(rows) if r['p1'] == 'OFF'), None)
            cont = next((f for f, r in enumerate(rows) if r['cont']), None)
            out.update(off_from=off, continue_overlay_from=cont, ok=bool(dead and off and cont and off - dead >= 60))
            marks = {dead: 'DEAD (blink + KO voice)', off: 'gone', cont: 'CONTINUE?'}
        lab = []
        for f, im in imgs:
            r = rows[f] if f < len(rows) else rows[-1]
            near = [m for k, m in marks.items() if k is not None and f <= k < f + 2]
            lab.append((f'frame {f}: P1 {r["p1"]} y{r["y"]} inv{r["inv"]}', ' '.join(near) or ' '.join(e[:4] for e in r['en']), bool(near)))
        sel = [j for j, (f, _) in enumerate(imgs) if f % 6 == 0 or lab[j][2]]
        sheet(f'Terry, {case}: P1 on his last hit (life 1, lives {2 if case == "respawn" else 0}); every 6th frame + the marked ones. '
              + json.dumps({k: v for k, v in out.items() if k != 'ko_sounds'}), [[imgs[j][1] for j in sel]], [lab[j] for j in sel],
              os.path.join(OUT, f'e_{case}.png'), ['brawler'], cols=8)
        log[case] = out; save(); print(case, out, flush=True)

if __name__ == '__main__':
    if WHAT in ('a', 'all'): run_a()
    if WHAT in ('b', 'all'): run_b()
    if WHAT in ('c', 'all'): run_c()
    if WHAT in ('d', 'all'): run_d()
    if WHAT in ('e', 'all'): run_e()
    if WHAT in ('f', 'all'): run_f()
    if WHAT in ('g', 'all'): run_g()
    if WHAT == 'gprep': run_gprep()
    if WHAT in ('k', 'all'): run_k()
    p = os.path.join(OUT, '_tmp.png')
    if os.path.exists(p): os.remove(p)
