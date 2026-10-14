#!/usr/bin/env python3
"""SS2's run frame by frame vs the brawler's (note 20261014-141702-5d29, Bruno on Genjuro: "I'm still not sure this is how
the run animation looks in Samurai Shodown 2. Can you check frame by frame?").

SS2 side, our emulator (cap_ss2: the fighter's vs state p1_CC.state, P2 poked 600 px away, forward forward held): per
frame the player's (animation, step) in RAM, its world x, the picture on the screen (its display-list entries at the
player's place, prio > 50: the definitions drawn), a screenshot. A picture is named by the (animation, step) it shows
(the majority over the run's frames), so both sides read as SS2 steps. Brawler side, harness.py (the fighter picked on
the select screen, the stage intro played, the enemies kept off): forward forward held, per frame his state / step / x
and the SS2 (animation, step) of that brawler step (export: steps' 'ss2' tag), a screenshot.

Checks per fighter: the same pictures in the same order with the same frames each from the run's first frame (the start
pose then the loop), the same x per frame (+-1 px over the run, its start standing).

    python3 run_ss2.py [names] [--out DIR]       (default haohmaru genjuro hanzo; /data/tmp/ss2run)
-> DIR/run_ss2.json (both timelines, checks), DIR/<name>_sheet.png (SS2 row over the brawler row, frame by frame)"""
import json, os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import cap_ss2 as C
from PIL import Image, ImageDraw

CAST = {'haohmaru': (0, 'haohmaru'), 'genjuro': (12, 'genjuro'), 'hanzo': (2, 'hanzo_ss2')}   # SS2 id, roster name
N = 40                                            # frames compared from the run's first frame
SEQ = '10:-,2:R,2:-,100:R,30:-'


def ss2_side(name, out):
    ch = CAST[name][0]; d = f'{out}/ss2_{name}'
    st = f'/data/neogeo_dict/samsho2/cap/p1_{ch:02d}.state'
    C.run(d + '/probe', '3:-', load=st, vram=False, sndlog=False)
    r = C.ram(d + '/probe', 1); a1, a2 = C.players(r)
    x = C.obj(r, a1)['wx'] + 600
    pk = ';'.join(f'{k}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}' for k in range(1, 120))
    C.run(d, SEQ, load=st, vram=False, sndlog=False, pokes=pk, snaps=range(1, C.nframes(SEQ) - 1))
    base = {}; rows = []
    for f in range(1, C.nframes(SEQ) - 1):
        rr = C.ram(d, f); o = C.obj(rr, a1)
        if o['anim'] not in base: base[o['anim']] = []
        pic = tuple(e['d'] for e in C.display_list(rr) if abs(e['x'] - o['x']) <= 1 and e['prio'] > 50)
        rows.append({'f': f, 'anim': o['anim'], 'step': o['step'], 'x': o['wx'], 'sx': o['x'], 'pic': pic})
    # (animation, step index) of a step address: its order of appearance in that animation (the run's steps are visited in order)
    order = collections.defaultdict(list)
    for e in rows:
        if e['step'] not in order[e['anim']]: order[e['anim']].append(e['step'])
    for e in rows: e['ram'] = (e['anim'], order[e['anim']].index(e['step']))
    votes = collections.defaultdict(collections.Counter)
    for e in rows: votes[e['pic']][e['ram']] += 1
    for e in rows: e['shows'] = votes[e['pic']].most_common(1)[0][0]
    f0 = next(k for k, e in enumerate(rows) if e['shows'][0] == 20)
    return d, rows[f0:f0 + N]


def brawler_side(name, out):
    import harness as H, re
    rn = CAST[name][1]
    global _B
    if '_B' not in globals(): _B = H.Brawler()      # (one core per process)
    b = _B
    hdr = open(os.path.join(H.GAME, 'build', 'bm_chars.h')).read()
    k = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ').index('BC_' + rn.upper())
    exp = json.load(open(os.path.join(H.GAME, 'build', f'tmp_samsho2_{name}', 'kof95_export.json')))['characters']
    exp = exp[0] if isinstance(exp, list) else next(iter(exp.values()))
    tags = [tuple(s['ss2']) for s in exp['anims']['run']['steps']]
    pic = {tuple(s['ss2']): s['frame'] for s in exp['anims']['run']['steps']}   # (SS2 step -> the exported picture)
    b.pick(k)
    OFF = b.states.index('OFF'); RUN = b.states.index('RUN')
    for _ in range(900):                               # the stage intro: on until control
        if b.r(b.syms['in_ph'], 1) == 0: break
        b.run(1)
    def quiet():
        for i in range(2, 8): b.fset(i, 'state', OFF)
        b.w(b.syms['tq_n'], 1, 0)
    for _ in range(10): quiet(); b.run(1)
    b.place(0, x=b.r(b.syms['cam_x'], 2) + 40); quiet(); b.run(2)
    keys = [''] * 2 + ['R'] * 2 + [''] * 2 + ['R'] * 80
    rows = []; d = f'{out}/br_{name}'; os.makedirs(d, exist_ok=True)
    for t, kk in enumerate(keys):
        quiet()
        p = f'{d}/f{t:03d}.png'
        b.pad = [set(kk), set()]; b.screenshot(p)          # (a frame with these keys, its picture)
        st = b.fget(0, 'state')
        rows.append({'t': t, 'state': b.states[st], 'step': b.fget(0, 'step'), 'x': b.fget(0, 'x'), 'cam': b.r(b.syms['cam_x'], 2),
                     'shows': tags[b.fget(0, 'step')] if st == RUN else None, 'png': p})
    f0 = next(k for k, e in enumerate(rows) if e['state'] == 'RUN')
    return rows[f0:f0 + N], pic


def compare(ss, br, pic):
    """pictures compared as the exported frame each SS2 step shows (two steps may show the same one: Genjuro's 66.1 / 66.3)"""
    sp = [pic.get(tuple(e['shows'])) for e in ss]; bp = [pic.get(tuple(e['shows'])) if e['shows'] else None for e in br]
    sx = [e['x'] - ss[0]['x'] for e in ss]; bx = [round(e['x'] - br[0]['x'], 2) for e in br]
    n = min(len(sp), len(bp))
    return {'pictures_equal': sp[:n] == bp[:n], 'first_diff': next((k for k in range(n) if sp[k] != bp[k]), None),
            'x_max_diff': max(abs(sx[k] - bx[k]) for k in range(n)), 'ss2_x': sx, 'brawler_x': bx, 'ss2': sp, 'brawler': bp}


def sheet(name, sd, ss, br, path):
    W, Hh = 96, 128; n = min(len(ss), len(br), 30)
    im = Image.new('RGB', (n * W, 2 * (Hh + 26) + 14), 'white'); dr = ImageDraw.Draw(im)
    dr.text((2, 0), f'{name}: SS2 (top) vs brawler (bottom), frame by frame from the run start; label = SS2 animation.step shown, x from the start', fill='black')
    for k in range(n):
        e = ss[k]; s = Image.open(f"{sd}/snap_{e['f'] + 2}.ppm")    # (the screenshot of frame f + 2 shows frame f's display list [meas])
        c = s.crop((e['sx'] - 8 - W // 2, 212 - Hh, e['sx'] - 8 + W // 2, 212))   # (304 x 224: 8 px trimmed each side)
        im.paste(c, (k * W, 14 + 26))
        dr.text((k * W + 2, 14), f"{k} {e['shows'][0]}.{e['shows'][1]}", fill='black'); dr.text((k * W + 2, 26), f"x+{e['x'] - ss[0]['x']}", fill='black')
        e = br[k]; y0 = 14 + Hh + 26
        nx = br[k + 1] if k + 1 < len(br) else None       # (the brawler's screenshot shows the tick before: the next one's)
        if nx and nx['png']:
            s = Image.open(nx['png']); sx = int(e['x'] - e['cam'])
            c = s.crop((sx - W // 2, 224 - Hh - 8, sx + W // 2, 224 - 8)); im.paste(c, (k * W, y0 + 26))
        lab = f"{e['shows'][0]}.{e['shows'][1]}" if e['shows'] else e['state']
        dr.text((k * W + 2, y0), f"{k} {lab}", fill='black'); dr.text((k * W + 2, y0 + 12), f"x+{e['x'] - br[0]['x']:.1f}", fill='black')
    im.save(path)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else '/data/tmp/ss2run'
    names = [a for a in args if a in CAST] or list(CAST)
    res = {}
    for nm in names:
        sd, ss = ss2_side(nm, out)
        br, pic = brawler_side(nm, out)
        c = compare(ss, br, pic); res[nm] = c
        sheet(nm, sd, ss, br, f'{out}/{nm}_sheet.png')
        print(nm, 'pictures', 'EQUAL' if c['pictures_equal'] else f"DIFFER at frame {c['first_diff']}", 'x max diff', c['x_max_diff'])
    ok = all(c['pictures_equal'] and c['x_max_diff'] <= 1.5 for c in res.values())
    json.dump(dict(res, ok=ok), open(f'{out}/run_ss2.json', 'w'), indent=1, default=str)
    print('ALL OK' if ok else 'FAIL', f'{out}/run_ss2.json')
