#!/usr/bin/env python3
"""TODO #139 proof: the super flash (fx.super_flash, tools/kof96/handlers98.md "Super flash") of Terry's fury 21416C and
MAX fury (down+D) in the brawler next to KOF98's own screens, and the freeze.

    python3 superflash_proof.py [OUT_DIR]      (default /data/tmp/superflash/out; the normal build, AI on)

A. KOF98 in our emulator (capture/romspecials98.trace, every frame a snapshot; MAX: KOF98's MAX mode held, sdm=True)
   and the brawler's Chain Lab (Terry against the training dummy, D / down+D), one picture per frame from each
   fury's first frame: per frame the stage area's mean grey (white backdrop > 240, dark stage < 12) -> the flash's
   frames in both, and a sheet KOF98 | brawler at the same fury frames (sheet_dm.png, sheet_max.png).
B. The freeze, in the campaign's first fight (the game's own enemies, AI on): Terry throws his Power Wave (C), then
   his fury (D); every frame of the flash every other entity (enemies: x, z, height, state, its frame counter, the
   frame shown; the projectile pool: x, height, row) is the same as on the flash's first frame, and Terry moves on
   -> freeze.json. Test-only pokes: P1's life kept full, Terry placed near the wave."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
from PIL import Image, ImageDraw
OUT = next((a for a in sys.argv[1:] if not a.startswith('--')), '/data/tmp/superflash/out')
os.makedirs(OUT, exist_ok=True)
N = 40                                                   # fury frames shown / measured
SHEET = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 29, 30, 32]

def grey(im, box=(180, 55, 240, 75)):
    """the mean grey of a patch of the stage (the stage's place, away from the fighters and the HUD)"""
    px = list(im.convert('L').crop(box).getdata()); return sum(px) / len(px)

def kind(g): return 'white' if g > 240 else 'dark' if g < 12 else 'stage'

KOF_PIC = 3          # KOF98's snapshot of capture frame START + f0 + 3 is the first to show the fury's first pose
                     # (Terry's DM frame $C4: the three before show the pose before; the brawler's first screenshot
                     # after the fury's first frame shows it): fury frame k = KOF snapshot f0 + 3 + k = brawler picture k
def kof(sdm):
    """KOF98: Terry 21416C (DM / SDM): snapshot n shows the picture the core output for capture frame n; the fury's
    first frame = the first row in a special state (its trace row f = capture frame START + f)"""
    import romspecials98 as R
    d = os.path.join(OUT, 'kof_max' if sdm else 'kof_dm'); os.makedirs(d, exist_ok=True)
    rows, _, _ = R.trace(3, '21416C', 'far', frames=N + 30, dm=True, sdm=sdm, snaps=list(range(R.START, R.START + N + 50)), snapdir=d)
    f0 = next(r['f'] for r in rows if R.special(r['state']))
    st = next(r['state'] for r in rows if R.special(r['state']))
    p2 = [(r['p2state'], r['p2x']) for r in rows if f0 <= r['f'] < f0 + N]
    ims = [Image.open(os.path.join(d, f'snap_{R.START + f0 + KOF_PIC + k}.ppm')).convert('RGB') for k in range(N)]
    return {'state': st, 'first_row': f0, 'p2_frozen_states': sorted(set(p2))}, ims

def brawler(keys, lab):
    """the Chain Lab: Terry (fighter 0) faces the dummy 140 px away, D (or down+D) pressed; pictures from the fury's
    first frame (state SPECIAL, state_t 1: the frame its program first runs)"""
    b = lab.b
    lab.start(0, 1); b.run(30)
    cam = b.r(b.syms['cam_x'], 2); b.place(0, x=cam + 90, z=30); b.place(2, x=cam + 230, z=30); b.fset(0, 'facing', 1); b.run(4)
    b.run(1, p1=keys)
    while not (b.states[b.fget(0, 'state')] == 'SPECIAL' and b.fget(0, 'state_t') >= 1): b.run(1)
    ims, rec = [], []
    tmp = os.path.join(OUT, 'tmp.png')
    for k in range(N):                                   # screenshot(): the next frame, as the game shows it
        rec.append({'k': k, 'state_t': b.fget(0, 'state_t'), 'sf_t': b.r(b.syms['sf_flash_t'], 1), 'sf_on': b.r(b.syms['sf_who'], 4) != 0,
                    'spec_ix': b.fget(0, 'spec_ix'), 'dummy_x': round(b.fget(2, 'x'), 3)})
        b.screenshot(tmp); ims.append(Image.open(tmp).convert('RGB'))
    return rec, ims

def runs(ims):
    ks = [kind(grey(im)) for im in ims]
    first = lambda k: next((i for i, x in enumerate(ks) if x == k), None)
    return {'kinds': ''.join(x[0] for x in ks), 'white_from': first('white'), 'white_frames': ks.count('white'),
            'dark_from': first('dark'), 'dark_frames': ks.count('dark'),
            'stage_back': next((i for i in range(len(ks)) if ks[i] == 'stage' and i > (first('dark') or 0)), None)}

def sheet(name, a, b_, title):
    w, h = a[0].size; cols = 3
    rows_ = (len(SHEET) + cols - 1) // cols
    S = Image.new('RGB', (cols * (2 * w + 12), rows_ * (h + 16) + 18), 'white'); d = ImageDraw.Draw(S)
    d.text((4, 3), title, fill='black')
    for i, k in enumerate(SHEET):
        x, y = i % cols * (2 * w + 12), 18 + i // cols * (h + 16)
        d.text((x + 4, y + 2), f'fury frame {k}: KOF98 | brawler', fill='black')
        S.paste(a[k], (x, y + 14)); S.paste(b_[k], (x + w + 2, y + 14))
    S.save(os.path.join(OUT, name))

FREEZE = '--freeze' in sys.argv                         # part B runs in a process of its own (one core per process)
res = {}
if not FREEZE:
  from labdrive import Lab
  lab = Lab()
  for tag, sdm, keys in (('dm', False, 'd'), ('max', True, 'Dd')):
    kinfo, kims = kof(sdm)
    brec, bims = brawler(keys, lab)
    res[tag] = {'kof98': {**kinfo, **runs(kims)}, 'brawler': {**runs(bims), 'spec_ix': brec[0]['spec_ix'],
                                                              'dummy_moved': len({r['dummy_x'] for r in brec if r['sf_on']}) > 1}}
    sheet(f'sheet_{tag}.png', kims, bims, f'Terry {"MAX " if sdm else ""}21416C ({"down+D" if sdm else "D"}): KOF98 (left) | brawler (right), same fury frames')
    print(tag, json.dumps(res[tag]))
  json.dump(res, open(os.path.join(OUT, 'part_a.json'), 'w'))
  import subprocess
  sys.exit(subprocess.run([sys.executable, os.path.abspath(__file__), OUT, '--freeze']).returncode)
res = json.load(open(os.path.join(OUT, 'part_a.json')))

# ---- B: the freeze in the campaign's first fight ---------------------------------------------------------------------
from harness import Brawler
b = Brawler()
def keep(bb): bb.fset(0, 'hp', 60)
b.to_fight(); ST = b.states
for _ in range(900):                                     # walk right until an enemy is on screen near Terry
    b.run(1, p1='R', each=keep)
    near = [i for i in range(2, 8) if ST[b.fget(i, 'state')] not in ('OFF', 'DEAD') and abs(b.fget(i, 'x') - b.fget(0, 'x')) < 200]
    if near: break
b.run(1, each=keep)
cam = b.r(b.syms['cam_x'], 2)                            # Terry at the screen's right edge, on a lane away from the
zs = [b.fget(i, 'z') for i in near]                      # enemies, facing left: his wave flies the whole screen
b.place(0, x=cam + 300, z=0 if min(zs) > 30 else 60); b.fset(0, 'facing', -1); b.run(1, each=keep)
b.run(2, p1='c', each=keep)                              # C neutral: Terry's Power Wave (EX 236C)
for _ in range(120):                                     # its wave in flight, Terry back to idle
    b.run(1, each=keep)
    if ST[b.fget(0, 'state')] == 'IDLE' and any(ST[b.pget(i, 'state')] == 'PROJ' for i in range(8)): break
else: print('no wave in flight when Terry recovered', b.brief())
def snap_all():
    en = {i: (round(b.fget(i, 'x'), 3), round(b.fget(i, 'z'), 3), round(b.fget(i, 'y'), 3), ST[b.fget(i, 'state')], b.fget(i, 'state_t'),
              b.fget(i, 'anim'), b.fget(i, 'step'), b.fget(i, 'frame_ovr')) for i in range(1, 8) if ST[b.fget(i, 'state')] != 'OFF'}
    pj = {i: (round(b.pget(i, 'x'), 3), round(b.pget(i, 'y'), 3), b.pget(i, 'prow'), b.pget(i, 'frame_ovr')) for i in range(8) if ST[b.pget(i, 'state')] == 'PROJ'}
    return en, pj
b.run(1, p1='d', each=keep)
frames = []
for k in range(60):
    on = b.r(b.syms['sf_who'], 4) != 0
    en, pj = snap_all()
    frames.append({'k': k, 'sf_on': on, 'sf_t': b.r(b.syms['sf_flash_t'], 1), 'cam_x': b.r(b.syms['cam_x'], 2), 'terry': (round(b.fget(0, 'x'), 3), b.fget(0, 'state_t')),
                   'enemies': {str(i): v for i, v in en.items()}, 'proj': {str(i): v for i, v in pj.items()}})
    if k in (0, 6, 20, 40): b.screenshot(os.path.join(OUT, f'freeze_{k:02d}.png')); frames[-1]['shot'] = True
    else: b.run(1, each=keep)
on = [f for f in frames if f['sf_on']]
ref = on[0] if on else None
same = ref is not None and all(f['enemies'] == ref['enemies'] and f['proj'] == ref['proj'] and f['cam_x'] == ref['cam_x'] for f in on)
moved_after = any(f['enemies'] != ref['enemies'] or f['proj'] != ref['proj'] for f in frames if not f['sf_on'] and f['k'] > on[-1]['k']) if on else False
res['freeze'] = {'flash_frames': len(on), 'enemies': len(ref['enemies']) if ref else 0, 'projectiles': len(ref['proj']) if ref else 0,
                 'all_frozen_during_flash': same, 'terry_moved': len({f['terry'] for f in on}) > 1, 'world_moves_after': moved_after}
res['ok'] = {'freeze': same and res['freeze']['projectiles'] > 0 and res['freeze']['enemies'] > 0 and res['freeze']['terry_moved'] and moved_after,
             'dm_flash': res['dm']['brawler']['white_frames'] > 0 and res['dm']['brawler']['dark_frames'] > 0,
             'max_is_max': res['max']['brawler']['spec_ix'] != res['dm']['brawler']['spec_ix']}
json.dump({'summary': res, 'freeze_frames': frames}, open(os.path.join(OUT, 'superflash.json'), 'w'), indent=1)
print('freeze', json.dumps(res['freeze'])); print('ok', res['ok'])
