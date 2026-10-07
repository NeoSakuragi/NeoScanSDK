#!/usr/bin/env python3
"""TODO #145 proof: the flash pose (vocabulary fx.super_flash "flash pose"; fighter.c flash_pose, export_bm FLASH_POSES).

    python3 flash145_proof.py [OUT] [--game DIR] [--only a,b]     (default /data/tmp/flash145/out; normal build, AI on)

Per fighter (Kim, Haohmaru, Genjuro, Kuroko, Hanzo, Billy Lee: furies from sources without a flash step; Terry: KOF98,
his own $FA flash step), in a real fight (harness.pick: the select screen, the campaign's first stage, its AI enemies):
P1 walks right until an enemy is near, is placed 50 px in front of it facing it with a full meter, presses D. Every
frame until 150 after the fury: P1 (state, state_t, frame shown, fpose), the flash (sf_who, sf_flash_t, sf_dx / sf_dy),
the enemies' life. Pass for a pose fighter: the flash runs gflash.freeze frames; on each of them P1 shows the pose's
frame for that frame (build/bm_chars.c {name}_fpose, expanded) and nothing of the fury runs (x, y, no hit); the glow's
anchor = the pose's head (bchar_t.fhead); the fury's first frame comes on the frame after the freeze; an enemy loses
life to it (the fury connects). Terry: fpose never set, the anchor his move's own. Sheets: OUT/<name>_flash.png (every
2nd frame of the freeze, the head point marked in red beside the picture's frame: a cross at the expected place) and
OUT/<name>_fury.png (after the freeze to the first hit + 12). OUT/<name>_trace.json (per frame), OUT/flash145.json."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Brawler
from PIL import Image, ImageDraw

args = [a for a in sys.argv[1:]]
GAME = None; ONLY = None
if '--game' in args: i = args.index('--game'); GAME = args[i + 1]; del args[i:i + 2]
if '--only' in args: i = args.index('--only'); ONLY = args[i + 1].split(','); del args[i:i + 2]
OUT = args[0] if args else '/data/tmp/flash145/out'
os.makedirs(OUT, exist_ok=True)
FIGHTERS = ['kim', 'haohmaru', 'genjuro', 'kuroko', 'hanzo', 'billy_lee', 'terry']
game_dir = GAME or os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
gj = json.load(open(os.path.join(game_dir, 'game.json')))
ROSTER = [r['name'] for r in gj['roster']]
FREEZE = gj['super_flash']['freeze']
bmc = open(os.path.join(game_dir, 'build', 'bm_chars.c')).read()

def fpose(n):
    m = re.search(r'static const bfpose_t %s_fpose\[\d+\] = \{(.*?)\};' % n, bmc)
    if not m: return []
    st = [tuple(map(int, x)) for x in re.findall(r'\{(\d+), (\d+)(?:, \d+)?\}', m.group(1))]
    return [fr for fr, k in st for _ in range(k) if k]

def fhead(n):
    m = re.search(r'\{"[^"]*", .*?%s_fpose, (\d+), \{(-?\d+), (-?\d+)\}\}' % n, bmc)
    return (int(m.group(2)), int(m.group(3))) if m and int(m.group(1)) else None

def s16(v): return v - 0x10000 if v & 0x8000 else v

b = Brawler(rom=os.path.join(game_dir, 'brawler.neo'), game=game_dir)
ST = b.states
def keep(bb): bb.fset(0, 'hp', 60)
def enemies(): return [i for i in range(2, 8) if ST[b.fget(i, 'state')] not in ('OFF', 'DEAD')]

def run_one(name):
    k = ROSTER.index(name)
    b.pick(k, unlock=True)
    for _ in range(900):                                 # walk right until an enemy is on screen near P1
        b.run(1, p1='R', each=keep)
        near = [i for i in enemies() if abs(b.fget(i, 'x') - b.fget(0, 'x')) < 200 and ST[b.fget(i, 'state')] in ('IDLE', 'WALK', 'RUN')]
        if near: break
    e = min(near, key=lambda i: abs(b.fget(i, 'x') - b.fget(0, 'x')))
    ex, ez = b.fget(e, 'x'), b.fget(e, 'z')
    cam = b.r(b.syms['cam_x'], 2)
    side = -1 if ex - cam > 160 else 1                   # P1 on the side of the enemy with room on the screen
    b.place(0, x=ex + side * 50, z=ez); b.fset(0, 'facing', (-side) & 0xFF); b.fset(0, 'meter', 120); keep(b)
    b.run(1, each=keep)
    hp0 = {i: b.fget(i, 'hp') for i in enemies()}
    rows, shots_flash, shots_fury, started, flash_end, first_hit, end = [], [], [], None, None, None, None
    b.pad = [{'d'}, set()]
    for f in range(400):
        st = ST[b.fget(0, 'state')]
        sf = b.r(b.syms['sf_who'], 4) != 0
        row = dict(f=f, st=st, state_t=b.fget(0, 'state_t'), frame=b.fget(0, 'frame_ovr'), fpose=b.fget(0, 'fpose') if 'fpose' in b.layout else None,
                   x=round(b.fget(0, 'x'), 3), y=round(b.fget(0, 'y'), 3), spec_id=b.fget(0, 'spec_id'), sf=sf,
                   sf_t=b.r(b.syms['sf_flash_t'], 1), sf_dx=s16(b.r(b.syms['sf_dx'], 2)), sf_dy=s16(b.r(b.syms['sf_dy'], 2)),
                   cam=b.r(b.syms['cam_x'], 2), z=round(b.fget(0, 'z'), 3), facing=b.fget(0, 'facing'),
                   ft=s16(b.r(b.syms['floor_top'], 2)), hp={i: b.fget(i, 'hp') for i in hp0})
        rows.append(row)
        if started is None and st == 'SPECIAL' and row['spec_id'] == 6: started = f
        if started is not None and flash_end is None and not sf and row['sf_t'] >= FREEZE: flash_end = f   # a row = RAM
                                                                 # after frame f - 1: the freeze's last frame resets sf_who
        if started is not None and first_hit is None and any(row['hp'][i] < hp0[i] for i in hp0): first_hit = f
        if started is not None and end is None and st != 'SPECIAL': end = f
        keys = 'd' if f < 2 else ''
        shoot = started is not None and ((sf and (f - started) % 2 == 0 and len(shots_flash) < 14) or
                                         (flash_end is not None and not sf and (first_hit is None or f <= first_hit + 12) and (f - flash_end) % 3 == 0 and len(shots_fury) < 21))
        if shoot:
            p = os.path.join(OUT, f'_{name}_{f}.png'); b.pad = [set(keys), set()]; b.screenshot(p)
            (shots_flash if sf else shots_fury).append((p, row))
        else: b.run(1, p1=keys, each=keep)
        if end is not None and f > end + 30: break
    json.dump(rows, open(os.path.join(OUT, f'{name}_trace.json'), 'w'))
    return rows, started, flash_end, first_hit, end, shots_flash, shots_fury

def sheet(shots, out, title, head=None):
    if not shots: return
    ims = [Image.open(p).convert('RGB') for p, _ in shots]
    w, h = ims[0].size; cols = 7; rws = (len(ims) + cols - 1) // cols
    S = Image.new('RGB', (cols * (w + 4), rws * (h + 14) + 16), 'white'); d = ImageDraw.Draw(S)
    d.text((4, 2), title, fill='black')
    for n, (im, (p, r)) in enumerate(zip(ims, shots)):
        x, y = (n % cols) * (w + 4), 16 + (n // cols) * (h + 14)
        S.paste(im, (x, y + 14)); d.text((x + 2, y + 1), f'frame {r["f"]}  flash t {r["sf_t"]}' if r['sf'] else f'frame {r["f"]}', fill='black')
        if head is not None and r['sf']:                 # the expected head point: red ticks on the picture's edges
            hx = r['x'] - r['cam'] + (-head[0] if r['facing'] == 1 else head[0]); hy = r['ft'] + r['z'] - r['y'] + head[1]
            d.line([x + hx, y + 14, x + hx, y + 18], fill='red'); d.line([x + hx, y + 14 + h - 4, x + hx, y + 14 + h], fill='red')
            d.line([x, y + 14 + hy, x + 4, y + 14 + hy], fill='red'); d.line([x + w - 4, y + 14 + hy, x + w, y + 14 + hy], fill='red')
        os.remove(p)
    S.save(out)

res = {}
for name in FIGHTERS:
    if ONLY and name not in ONLY: continue
    rows, started, flash_end, first_hit, end, sh_f, sh_u = run_one(name)
    pose, head = fpose(name), fhead(name)
    r = dict(started=started, flash_frames=None,
             first_hit_after_flash=(first_hit - flash_end) if first_hit is not None and flash_end else None,
             fury_frames=(end - started) if end and started is not None else None)
    fs = next((i for i, x in enumerate(rows) if x['sf']), None)   # the first row after the flash's first frame
    if started is not None and flash_end:
        fl = rows[fs:flash_end + 1]                      # after each of the freeze's frames (the last: sf_who reset)
        r['flash_frames'] = len(fl)
        r['anchor'] = sorted({(x['sf_dx'], x['sf_dy']) for x in fl})
        if pose:
            r['pose_frames_ok'] = [x['frame'] for x in fl] == pose
            r['still_in_freeze'] = len({(x['x'], x['y']) for x in fl}) == 1
            r['no_hit_in_freeze'] = all(x['hp'] == fl[0]['hp'] for x in fl)
            r['anchor_is_head'] = r['anchor'] == [tuple(head)]
            r['fury_after_freeze'] = rows[flash_end + 1]['fpose'] == 0xFF and rows[flash_end + 1]['state_t'] == gj['super_flash']['start'] \
                and rows[flash_end + 1]['frame'] not in pose   # the frame after the freeze: the fury's first, as under a KOF flash
            r['head'] = head
        else:
            r['fpose_never_set'] = all(x['fpose'] in (0, None) for x in rows[started:end or len(rows)])
    r['connects'] = first_hit is not None
    r['ok'] = bool(r['connects'] and r.get('flash_frames') == FREEZE and (all(r[k] for k in ('pose_frames_ok', 'still_in_freeze', 'no_hit_in_freeze', 'anchor_is_head', 'fury_after_freeze')) if pose else r.get('fpose_never_set', True)))
    res[name] = r
    sheet(sh_f, os.path.join(OUT, f'{name}_flash.png'), f'{name}: the super flash (every 2nd frame): the flash pose, the glow on its head (red ticks: the head point)' if pose else f'{name}: the super flash (KOF98: its own flash step, unchanged)', head)
    sheet(sh_u, os.path.join(OUT, f'{name}_fury.png'), f'{name}: after the flash, the fury in a real fight (first hit at frame {first_hit})')
    print(name, 'ok' if r['ok'] else 'FAIL', json.dumps(r), flush=True)
json.dump(res, open(os.path.join(OUT, 'flash145.json' if not GAME else 'flash145_game.json'), 'w'), indent=1)
print('ALL OK' if all(v['ok'] for v in res.values()) else 'FAILURES: ' + ' '.join(n for n, v in res.items() if not v['ok']))
