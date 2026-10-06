#!/usr/bin/env python3
"""Fury -> MAX cancel and the fury's objects (feedback 20261006-174005-5d29, branch.cancel rule 3): at the cancel the
fury's own objects (shots, eruptions, pinned effects) end, so the MAX spawns whole. Per fighter (Chain Lab training,
labdrive, a dummy that never attacks): the MAX from neutral (its P1-owned objects per frame: the reference), then the
fury at the dummy, down+D after its first hit until the MAX starts: the fury's objects alive the frame after the cancel
(must be 0) and the MAX's objects per frame from its start (the same births as the reference's: frames and counts); screenshots of both
MAXes at the same frames -> OUT/<fighter>_maxcancel.png

    python3 maxcancel_objects_proof.py OUT [FIGHTER ...]      (default geese billy krauser)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
from labdrive import Lab
from PIL import Image, ImageDraw

OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
G = json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))
names = [r['name'] for r in G['roster']]
L = Lab(); b = L.b; ST = b.states
BS_FURY = 6

def st(i=0): return ST[b.fget(i, 'state')]
def objs(): return [i for i in range(8) if ST[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'owner') == b.base]
def setpos(dist):
    for _ in range(600):
        if st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK'): break
        b.run(1)
    cam = b.r(b.syms['cam_x'], 2); x0 = cam + 60
    b.place(0, x=x0, z=30); b.place(2, x=x0 + dist, z=30); b.fset(0, 'facing', 1); b.fset(2, 'hp', 120); b.run(2)

def spawns(cnt):
    """[(frame, objects born then)]: the frames the count of objects rises"""
    return [(k, c - (cnt[k - 1] if k else 0)) for k, c in enumerate(cnt) if c > (cnt[k - 1] if k else 0)]

def max_run(shots, tag):
    """from the MAX's first frame: P1-owned objects per frame until it ends, screenshots every 8 frames"""
    ix = b.fget(0, 'spec_ix'); cnt, pics = [], []
    for k in range(400):
        if st(0) != 'SPECIAL' or b.fget(0, 'spec_ix') != ix: break
        if k % 8 == 0 and len(pics) < 12:
            p = os.path.join(shots, f'{tag}_{k:03d}.png'); b.screenshot(p); pics.append(p)
        else: b.run(1)
        cnt.append(len(objs()))
    return cnt, pics

res = {}
for name in sys.argv[2:] or ['geese', 'billy', 'krauser']:
    L.start(names.index(name), 0); b.run(60)
    shots = os.path.join(OUT, name); os.makedirs(shots, exist_ok=True)
    setpos(300); b.run(1, 'Dd'); b.run(1)
    ref, ref_pics = max_run(shots, 'neutral')
    b.run(300)
    r = {'max_from_neutral_objects_peak': max(ref, default=0)}
    for dist in (40, 60, 80, 110):
        setpos(dist); h0 = len(b.hits); b.run(1, 'd'); b.run(1)
        fx = b.fget(0, 'spec_ix'); before = 0; cancel_at = None
        for k in range(300):
            if st(0) != 'SPECIAL': break
            if b.fget(0, 'spec_ix') != fx: cancel_at = k; break
            before = max(before, len(objs()))
            hit = any(h[1] == 2 for h in b.hits[h0:])
            b.run(1, 'Dd' if hit and k % 2 == 0 else '')
        if cancel_at is None: b.run(300); continue
        fury_left = len(objs())                           # the frame the MAX starts: the fury's objects must be gone
        cnt, pics = max_run(shots, 'cancel')
        n = min(len(cnt), len(ref))
        r.update(dist=dist, fury_objects_peak=before, cancel_after=cancel_at, objects_at_cancel=fury_left,
                 max_objects=cnt[:n], ref_objects=ref[:n], spawns=spawns(cnt), ref_spawns=spawns(ref),
                 ok=fury_left == 0 and spawns(cnt) == spawns(ref))   # (the same births; the dummy may end a shot early)
        ims = [Image.open(p) for p in ref_pics] + [Image.open(p) for p in pics]
        w, h = ims[0].size; cols = max(len(ref_pics), len(pics))
        sheet = Image.new('RGB', (w * cols, h * 2 + 40), 'white'); d = ImageDraw.Draw(sheet)
        d.text((4, 2), f'{name}: MAX from neutral (top) | MAX out of the fury (bottom), every 8th frame from its start', fill='black')
        for i, p in enumerate(ref_pics): sheet.paste(Image.open(p), (i * w, 20))
        for i, p in enumerate(pics): sheet.paste(Image.open(p), (i * w, h + 40))
        sheet.save(os.path.join(OUT, f'{name}_maxcancel.png'))
        break
    else: r.update(ok=None, note='the fury never hit the dummy')
    res[name] = r
    print(name, json.dumps({k: v for k, v in r.items() if k not in ('max_objects', 'ref_objects')}), flush=True)
json.dump(res, open(os.path.join(OUT, 'maxcancel.json'), 'w'), indent=1)
print('all ok' if all(v.get('ok') for v in res.values()) else 'FAIL')
