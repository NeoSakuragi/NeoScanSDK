#!/usr/bin/env python3
"""TODO #184 proof: the stage clear's win pose in real runs of the brawler (harness.py, the repo's core), against each
source game's own round win (our emulator).

    python3 win184_proof.py OUT [--only name,...] [--no-source]

1. Every roster fighter: campaign stage 1 from its boss (lab req 4, scenario.py's setup: the boss walks in, alone, life
   1, P1 in front of it), P1 presses A until the boss dies, then the run goes on to the next screen with P1 mashing
   A-D and the stick through the clear (the input is off: nothing may change the pose). Logged per frame: the phase,
   P1's state / animation / step / facing / x, the sound bytes the game sends (sound.c's queue: q[qh] each time qh
   moves). Checks: STAGE CLEAR, then the win (BA_WIN) from step 0 to its last step in order, facing the middle of the
   screen, its voice (snd/voices.h code of the fighter's 'win' key) sent at its step when it has one, nothing else
   started during the pose, the next screen (stage 2 / BOSS UNLOCKED) after the pose's end + WIN_HOLD.
2. Two players (P2 joins with a coin + START before the boss): both pose.
3. Source captures (our emulator): KOF98 Terry, KOF96 Geese, KOF99 K' (tools/kof98/capture/wins98.py's run, A held at
   the KO, snapshots); SS2 / WHP / Kizuna / Double Dragon: wins184.py's snapshots.
Out: OUT/results.json, OUT/sheet_<family>.png (source above, brawler below, from each one's pose start), OUT/roster.png
(every fighter's pose: first frame, middle, last), OUT/clear_<fighter>.png (a stage clear's frames), OUT/two_players.png."""
import json, os, re, sys, subprocess
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H, scenario as SC

GAME = H.GAME
FAMILIES = [  # family, roster fighter, source capture (wins184 key or KOF (game, cid))
    ('KOF98', 'terry', ('kof98', 3)), ('KOF96', 'geese', ('kof96', 24)), ('KOF99', 'k_dash', ('kof99', 0)),
    ('SS2', 'haohmaru', 'ss2:haohmaru'), ('WHP', 'hanzo', 'whp:hanzo'), ('Kizuna', 'kim', 'kz:kim'),
    ('DD', 'billy_lee', 'dd:billy_lee')]
SRC = '/data/tmp/win184/src'
WIN_HOLD = 45                                            # main.c

def roster():
    return [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]

def ba_win():
    h = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    return int(re.search(r'\bBA_WIN\s*=\s*(\d+)', h).group(1)) if re.search(r'\bBA_WIN\s*=\s*(\d+)', h) else \
        re.findall(r'\bBA_(\w+)', h[h.index('BA_IDLE'):]).index('WIN')

def voice_code(name):
    """the fighter's 'win' voice: (id, step, the bytes it sends) from the build (bm_chars.c <name>_voices [id, at] at key
    BA_WIN, snd/voices.h's code for that id); (0, 0, None) when it has none"""
    c = open(os.path.join(GAME, 'build', 'bm_chars.c')).read()
    m = re.search(r'static const uint8_t %s_voices\[\] = \{([^}]*)\}' % name, c)
    v = [int(x) for x in m.group(1).split(',')]
    vid, at, fx = v[2 * BA] & 0x7F, v[2 * BA + 1], v[2 * BA] & 0x80   # bit 7: an effect, on the other slot (fighter.c voice_id)
    if not vid: return 0, 0, None
    h = open(os.path.join(GAME, 'build', 'snd', 'voices.h')).read()
    k = roster().index(name)
    codes = [int(x) for x in re.search(r'vcode_%d\[\] = \{([^}]*)\}' % k, h).group(1).split(',')]
    code = codes[vid]
    return vid, at, [(0x17 if code >> 8 else 0x1E) if fx else (0x1B if code >> 8 else 0x1C), code & 0xFF]

def sim_frames(b):
    data, w, h, pitch = b._video
    return Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')

_B = None
def stage_run(name, two=False, shots_every=4):
    """one campaign stage-1 clear with fighter `name`; returns (log, shots {frame: image})"""
    global _B
    if _B is None: _B = H.Brawler()                     # one core per process; setup resets it (retro_reset)
    b = _B
    nw = len(json.load(open(os.path.join(GAME, 'game.json')))['stages'][0]['waves'])
    rec = {'setup': {'mode': 'stage', 'fighter': name, 'stage': 0, 'wave': nw, 'wait': 150, 'alone': True,
                     'foe_hp': 1, 'gap': 50}}
    if two:                                              # P2 joins (a coin in slot 2, START) before the boss
        rec['setup']['pre'] = ''
    b.game = GAME; SC.setup(b, rec)
    if two:
        b.run(4, p2='o'); b.run(30); b.run(4, p2='s'); b.run(90)
        b.fset(1, 'x', b.fget(2, 'x') - 120); b.fset(1, 'z', b.fget(2, 'z')); b.run(1)
    qh0 = b.r(b.syms['qh'], 1)
    log, shots, t = [], {}, 0
    b._want_video = True
    camp0 = b.r(b.syms['camp'], 1)
    keys = ['a', 'b', 'c', 'd', 'L', 'R', 'U', 'D', 'ab', 'cd', 'abcd']
    while t < 2400:
        ph = b.r(b.syms['phase'], 1)
        if ph < 3: p1 = 'a' if t % 8 < 3 else ''          # the killing hit (PH_BOSS: phase 2)
        else: p1 = keys[t // 5 % len(keys)] if t % 5 < 2 else ''   # the stage clear: everything pressed (input off)
        p2 = p1 if two else ''
        b.run(1, p1=p1, p2=p2)
        qh = b.r(b.syms['qh'], 1); snd = []
        while qh0 != qh: snd.append(b.r(b.syms['q'] + qh0, 1)); qh0 = (qh0 + 1) & 31
        row = {'t': t, 'mode': b.r(b.syms['mode'], 1), 'camp': b.r(b.syms['camp'], 1), 'phase': ph, 'snd': snd,
               'cam': b.r(b.syms['cam_x'], 2), 'boss_hp': b.fget(2, 'hp')}
        for i in (0, 1):
            row[f'p{i}'] = {k: b.fget(i, k) for k in ('state', 'anim', 'step', 'facing', 'x', 'y', 'anim_done')}
        log.append(row)
        if row['mode'] != 1 or row['camp'] != camp0: break
        if ph == 4 and (t % shots_every == 0): shots[t] = sim_frames(b)
        t += 1
    b._want_video = False
    return b, log, shots

def check(b, name, log, two=False):
    """the run's facts and the rule's checks"""
    clr = next((r['t'] for r in log if r['phase'] == 4), None)
    end = log[-1]
    res = {'fighter': name, 'stage_clear_t': clr, 'next_t': end['t'], 'next_mode': end['mode'], 'next_camp': end['camp']}
    for i in ((0, 1) if two else (0,)):
        k = f'p{i}'
        pose = [r for r in log if r[k]['anim'] == BA and r['phase'] == 4 and r['mode'] == 1]
        if not pose: res[k] = {'posed': False}; continue
        st = [r[k]['step'] for r in pose]
        mono = all(b2 >= a for a, b2 in zip(st, st[1:]))
        t0, t_done = pose[0]['t'], next((r['t'] for r in pose if r[k]['anim_done']), None)
        sx = pose[0][k]['x'] - (pose[0]['cam'] - 65536 if pose[0]['cam'] > 32767 else pose[0]['cam'])
        want_face = 1 if sx < 160 else -1
        after = [r for r in log if r['t'] >= t0 and r['phase'] == 4 and r['mode'] == 1]
        res[k] = {'posed': True, 'pose_start_t': t0, 'pose_done_t': t_done, 'steps_seen': sorted(set(st)), 'last_step': st[-1],
                  'steps_in_order': mono, 'facing': pose[0][k]['facing'], 'faces_middle': pose[0][k]['facing'] == want_face,
                  'anim_kept': all(r[k]['anim'] == BA for r in after), 'state_kept': all(r[k]['state'] == after[0][k]['state'] for r in after),
                  'frames_after_done': end['t'] - (t_done or end['t'])}
        if i == 0:
            vid, at, bs = voice_code(name)
            stream = [(r['t'], x) for r in log if r['t'] >= t0 for x in r['snd']]     # one byte a frame (sound.c)
            sent = [stream[j][0] for j in range(len(stream) - 1) if bs and [stream[j][1], stream[j + 1][1]] == bs]
            res[k]['voice'] = {'id': vid, 'at_step': at, 'bytes': bs, 'sent_t': sent[:3],
                               'sent_at_step': [next(r[k]['step'] for r in log if r['t'] == t) for t in sent[:1]]}
        p = res[k]; v = p.get('voice', {})
        p['ok'] = bool(p['steps_in_order'] and p['last_step'] == max(p['steps_seen']) and p['faces_middle'] and p['anim_kept']
                       and p['state_kept'] and p['frames_after_done'] >= WIN_HOLD - 1   # the done frame is the hold's first
                       and (not v.get('id') or v.get('sent_at_step') == [v.get('at_step')]))
    return res

BA = None

def crop_player(im, x, cam):
    sx = int(x - cam)
    l = max(0, min(320 - 160, sx - 80))
    return im.crop((l, 24, l + 160, 224))

def source_snaps(key, out):
    """the source's frames from its pose start: [(frame offset, image)]"""
    if isinstance(key, tuple):
        game, cid = key
        return kof_snaps(game, cid, out)
    d = json.load(open(os.path.join(SRC, 'wins184.json')))[key]
    t0 = d['anims'][-1][1] if key != 'dd:billy_lee' else d['anims'][-2][1]
    g, n = key.split(':'); dd = os.path.join(SRC, f'{g}_{n}')
    fr = sorted(int(f[5:-4]) for f in os.listdir(dd) if f.startswith('snap_'))
    return [(f - t0, Image.open(os.path.join(dd, f'snap_{f}.ppm')).convert('RGB')) for f in fr if f >= t0 - 6]

def kof_snaps(game, cid, out):
    sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture')); sys.path.insert(0, os.path.join(HERE, '..', 'kof95', 'capture'))
    import emu, specials96, analyze as A
    from timeline import seqs
    specials96.prep(game, cid)
    d = os.path.join(out, 'src', f'{game}_{cid}'); os.makedirs(d, exist_ok=True)
    s = 40; spec = [f'p1 {s} 3 c', f'p1 {s + 12} 510 a']
    pokes = [f'{s - 2}:108118=01,108119=80,108318=01,108319=B0,{emu.life_pokes(game, 0x108300, 1)}']
    s1, s2 = seqs('; '.join(spec), s + 560)
    path = os.path.join(d, 'cap.txt')
    emu.run(game, path, s1, s2, pokes, reload=f'c{cid}', reload_frames=[s - 4], snaps=list(range(s + 40, s + 556, 3)), snapdir=d)
    r1 = A.load(path, 1)
    win = {'kof96': 209}.get(game, 336)
    t0 = next(i for i in range(len(r1)) if A.state_of(r1[i][3]) == win)
    fr = sorted(int(f[5:-4]) for f in os.listdir(d) if f.startswith('snap_'))
    return [(f - t0, Image.open(os.path.join(d, f'snap_{f}.ppm')).convert('RGB')) for f in fr if f >= t0 - 3]

def label(im, text):
    im = im.copy(); dr = ImageDraw.Draw(im); dr.rectangle((0, 0, im.width, 12), fill=(255, 255, 255)); dr.text((2, 1), text, fill=(0, 0, 0)); return im

def row_of(pairs, offsets, w=160):
    out = []
    for o in offsets:
        im = min(pairs, key=lambda p: abs(p[0] - o))[1] if pairs else Image.new('RGB', (w, 200), 'white')
        out.append(im)
    return out

def grid(rows, titles, path, cell=(160, 200)):
    W = cell[0] * max(len(r) for r in rows); Hh = (cell[1] + 14) * len(rows)
    s = Image.new('RGB', (W, Hh), 'white'); dr = ImageDraw.Draw(s)
    for j, (r, tt) in enumerate(zip(rows, titles)):
        y = j * (cell[1] + 14); dr.text((2, y + 1), tt, fill=(0, 0, 0))
        for i, im in enumerate(r):
            s.paste(im.resize(cell), (i * cell[0], y + 14))
            dr.rectangle((i * cell[0], y + 14, (i + 1) * cell[0] - 1, y + 14 + cell[1] - 1), outline=(0, 0, 0))
    s.save(path)

def main():
    global BA
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
    BA = ba_win()
    names = only or roster()
    results, poses = {}, {}
    for n in names:
        b, log, shots = stage_run(n)
        res = check(b, n, log); results[n] = res
        p = res['p0']
        print(n, json.dumps(res), flush=True)
        if p.get('posed'):
            t0, td = p['pose_start_t'], p['pose_done_t'] or p['pose_start_t']
            cam = lambda t: (lambda c: c - 65536 if c > 32767 else c)(log[t]['cam'])
            x = log[t0]['p0']['x']
            ks = sorted(shots)
            pick = lambda t: crop_player(shots[min(ks, key=lambda k: abs(k - t))], x, cam(t0))
            poses[n] = [pick(t0), pick((t0 + td) // 2), pick(td + 2)]
            seq = [k for k in ks if k >= t0 - 8][::max(1, len([k for k in ks if k >= t0 - 8]) // 12)][:12]
            grid([[shots[k] for k in seq[:6]], [shots[k] for k in seq[6:12]]], [f'{n}: stage clear, frames {seq[:6]}', f'frames {seq[6:12]}'],
                 os.path.join(out, f'clear_{n}.png'), cell=(320, 224))
            json.dump(log, open(os.path.join(out, f'log_{n}.json'), 'w'))
    json.dump(results, open(os.path.join(out, 'results.json'), 'w'), indent=1)
    if poses:
        rows = [poses[n] for n in names if n in poses]
        W = 3 * 120; s = Image.new('RGB', (6 * 3 * 100, ((len(rows) + 5) // 6) * 166), 'white'); dr = ImageDraw.Draw(s)
        for k, n in enumerate([n for n in names if n in poses]):
            x0, y0 = (k % 6) * 300, (k // 6) * 166
            for j, im in enumerate(poses[n]): s.paste(im.resize((100, 125)), (x0 + j * 100, y0 + 14))
            dr.text((x0 + 2, y0 + 1), f'{n}: win start / middle / end', fill=(0, 0, 0))
            dr.rectangle((x0, y0, x0 + 299, y0 + 139), outline=(0, 0, 0))
        s.save(os.path.join(out, 'roster.png'))
    if '--two' in sys.argv:
        b, log, shots = stage_run(names[0], two=True)
        res = check(b, names[0], log, two=True); results['two_players'] = res
        print('two players', json.dumps(res), flush=True)
        ks = sorted(shots); seq = ks[::max(1, len(ks) // 8)][:8]
        grid([[shots[k] for k in seq[:4]], [shots[k] for k in seq[4:8]]], ['two players: both pose', ''], os.path.join(out, 'two_players.png'), cell=(320, 224))
        json.dump(results, open(os.path.join(out, 'results.json'), 'w'), indent=1)
    if '--no-source' not in sys.argv:
        for fam, n, key in FAMILIES:
            if n not in names: continue
            src = source_snaps(key, out)
            log = json.load(open(os.path.join(out, f'log_{n}.json')))
            t0 = results[n]['p0']['pose_start_t']; cam = log[t0]['cam']; cam = cam - 65536 if cam > 32767 else cam
            x = log[t0]['p0']['x']
            b2 = sorted((t - t0, im) for t, im in stage_shots(n, out).items())
            offs = [0, 12, 30, 60, 100, 160]
            grid([row_of(src, offs), row_of(b2, offs)], [f'{fam} ({n}): the source game, frames {offs} from its win animation\'s start',
                 f'the brawler: the stage clear, the same frames from the win animation\'s start'],
                 os.path.join(out, f'sheet_{fam}.png'), cell=(320, 224))

def stage_shots(n, out):
    """the stage-clear screenshots again (a second run, every frame; the harness is deterministic)"""
    b, log, shots = stage_run(n, shots_every=1)
    return shots

if __name__ == '__main__':
    main()
