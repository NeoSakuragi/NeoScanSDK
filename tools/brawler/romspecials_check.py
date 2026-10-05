#!/usr/bin/env python3
"""The ROM-read specials (tools/kof96/handlers98.py, export_bm rom_c, fighter.c prog_update) against KOF98, frame by frame.

    python3 romspecials_check.py GAME_DIR OUT_DIR [fighter:role ...]     (an AI_OFF=1 build: the target stands still)

Per special and branch (whiff: nobody near; hit: an enemy standing 48 px ahead, KOF98's close-range distance), from the
special's first frame: the frame shown (ROM frame index), x from the start (forward +), height, the hits (frames the
target's life drops) and the projectile (first frame, place, speed). KOF98 side: tools/kof96/capture/romspecials98.py
(our emulator; the game's hit-stop and slowdown frames dropped: the brawler applies its own hit-stop instead). The
brawler's own hit-stop frames (P1 freeze) are dropped the same way and counted. Contact sheets: OUT_DIR/<fighter>_<input>
_<branch>.png, KOF98 left, brawler right, every 4th frame; OUT_DIR/summary.json."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
from harness import Brawler
import romspecials98 as K
from PIL import Image, ImageDraw

ROLES = {'D': '4:d', 'fD': '4:Rd', 'dD': '4:Dd', 'uD': '4:Ud'}
KOF = {'terry': 3, 'ralf': 10}
CASES = ['terry:fD', 'terry:dD', 'terry:D', 'ralf:fD', 'ralf:dD', 'ralf:uD']
EVERY = 4

def brawler_run(b, k, role, hit, shots, frames=200):
    b.pick(k)
    while b.r(b.syms['fade_in'], 1): b.run(1)
    b.run(10)
    for i in range(1, 8): b.place(i, x=1000, z=0)
    b.place(0, x=60, z=30)                               # the left of the screen: room for the rushes
    if hit: b.place(2, x=108, z=30)
    b.run(2)
    w = 0
    while b.states[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
    b.hits = []
    n, keys = ROLES[role].split(':')
    rows, started, t, pfz = [], None, 0, 0
    x0 = b.fget(0, 'x'); fc = b.fget(0, 'facing')
    for f in range(frames):
        if f < int(n): b.pad = [set(keys), set()]
        else: b.pad = [set(), set()]
        st = b.states[b.fget(0, 'state')]
        want = started is not None and (len(rows) % EVERY == 0)
        path = None
        if started is None:                              # row 0's picture (its frame is known only after it)
            path = os.path.join(shots, 'b_000.png'); b.screenshot(path)
        elif want and len(rows) // EVERY < 30:
            path = os.path.join(shots, f'b_{len(rows):03d}.png'); b.screenshot(path)
        else: b.core.retro_run(); b.frame += 1
        st = b.states[b.fget(0, 'state')]
        if started is None and st == 'SPECIAL' and b.fget(0, 'frame_ovr') != 0xFFFF: started = f; path = os.path.join(shots, 'b_000.png')
        if started is None: continue
        if st != 'SPECIAL' and f > started + 2: break
        fz = b.fget(0, 'freeze')
        if fz or pfz: pfz = fz; continue                 # the brawler's own hit-stop (its last frame reads 0)
        pfz = fz
        pj = []
        for i in range(4):
            if b.pget(i, 'state') < len(b.states) and b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'frame_ovr') != 0xFFFF:
                pj.append((i, b.pget(i, 'frame_ovr'), round((b.pget(i, 'x') - x0) * fc, 2), round(b.pget(i, 'y'), 2)))
        rows.append({'frame': b.fget(0, 'frame_ovr'), 'x': round((b.fget(0, 'x') - x0) * fc, 2), 'h': round(b.fget(0, 'y'), 2),
                     'hp2': b.fget(2, 'hp'), 'proj': pj, 'shot': path})
    return rows

def sheet(pairs, path, title):
    W, H = 160, 112
    cols = 2
    im = Image.new('RGB', (cols * (2 * W + 8) + 8, 20 + ((len(pairs) + cols - 1) // cols) * (H + 16)), 'white')
    d = ImageDraw.Draw(im); d.text((8, 4), title, fill='black')
    for i, (f, a, b) in enumerate(pairs):
        x = 8 + (i % cols) * (2 * W + 8); y = 20 + (i // cols) * (H + 16)
        for j, p in enumerate((a, b)):
            if p and os.path.exists(p): im.paste(Image.open(p).convert('RGB').resize((W, H)), (x + j * W, y + 12))
            d.rectangle([x + j * W, y + 12, x + j * W + W - 1, y + 12 + H - 1], outline='black')
        d.text((x, y), f'frame {f}: KOF98 | brawler', fill='black')
    im.save(path)

def main(game, out, cases):
    os.makedirs(out, exist_ok=True)
    roster = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    gj = {r['name']: r for r in json.load(open(os.path.join(game, 'game.json')))['roster']}
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    summary = []
    for case in cases:
        name, role = case.split(':'); inp = gj[name]['specials'][role]; cid = KOF[name]
        for branch in ('whiff', 'close'):
            tag = f'{name}_{inp.replace(" ", "").replace("[", "c").replace("]", "")}_{branch}'
            shots = os.path.join(out, 'shots', tag); os.makedirs(shots, exist_ok=True)
            res, game_rows, model, objs, prog = K.compare(cid, inp.replace('EX ', ''), branch, inp.startswith('EX '), quiet=True)
            # KOF screenshots at the kept frames (every EVERY-th of the move after the dropped ones)
            want = [game_rows[i]['f'] for i in range(0, res['frames_game'], EVERY)][:30]
            K.trace(cid, inp.replace('EX ', ''), branch, inp.startswith('EX '), snaps=[K.START + f for f in want], snapdir=shots)
            br = brawler_run(b, roster.index(name), role, branch == 'close', shots)
            rec = lambda bf: int(frames[name][bf].split(':')[1]) if bf < len(frames[name]) and frames[name][bf] else -1
            n = min(len(br), res['frames_game'])
            gx0 = game_rows[0]['x'] - model[0][3]
            # the harness samples RAM when a video frame ends, inside a game tick (regress.py `near`): a sample may show
            # P1 before or after this tick's update; a sample matches when it equals KOF's at that frame or one either side
            near = lambda i: range(max(0, i - 1), min(n, i + 2))
            dfr = sum(1 for i in range(n) if all(rec(br[i]['frame']) != game_rows[j]['frame'] for j in near(i)))
            dx = max((min(abs(br[i]['x'] - (game_rows[j]['x'] - gx0)) for j in near(i)) for i in range(n)), default=0)
            dh = max((min(abs(br[i]['h'] - game_rows[j]['h']) for j in near(i)) for i in range(n)), default=0)
            bhits = [i for i in range(1, len(br)) if br[i]['hp2'] < br[i - 1]['hp2']]
            bp = next(((i, r['proj']) for i, r in enumerate(br) if r['proj']), None)
            s = {'case': case, 'input': inp, 'branch': branch, 'kof_frames': res['frames_game'], 'brawler_frames': len(br),
                 'frame_mismatch': dfr, 'max_dx': round(dx, 2), 'max_dh': round(dh, 2), 'kof_hits': res['hit_frames'],
                 'brawler_hits': bhits, 'kof_freeze_dropped': res['frozen_dropped'], 'kof_slowdown_dropped': res['slowdown_dropped'],
                 'kof_objects': res['objects_game'], 'brawler_proj_first': bp and [bp[0]] + [list(p) for p in bp[1]],
                 'brawler_proj_next': (br[bp[0] + 1]['proj'] if bp and bp[0] + 1 < len(br) else None)}
            summary.append(s); print(json.dumps(s), flush=True)
            pairs = []
            for i in range(0, min(len(br), res['frames_game']), EVERY):
                kp = os.path.join(shots, f'snap_{K.START + game_rows[i]["f"]}.ppm')
                pairs.append((i, kp, br[i]['shot']))
            sheet(pairs[:30], os.path.join(out, tag + '.png'), f'{name} {inp} ({role}) {branch}: KOF98 (our emulator, freezes dropped) | brawler (ROM program)')
    json.dump(summary, open(os.path.join(out, 'summary.json'), 'w'), indent=1)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or CASES)
