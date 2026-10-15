#!/usr/bin/env python3
"""Proof of note 20261011-225104-5d29 (Bruno: "a lot of win poses of Yuri and Kyo embed flames, but I don't see them
here ... Terry throwing his cap"): the win poses' effect objects (export96 win_objects, captured in KOF by
tools/kof98/capture/winfx98.py) in real stage clears of the brawler (harness.py, winposes_proof's run), against the
source game's own pose (winfx98's snapshots, our emulator).

    python3 winfx5d29_proof.py OUT [--only name,...]

Per fighter, per pose that has effects (bm_wins fx): the stage clear is run with the pose forced (game_ticks set while
the winner waits to pose: fighter.c fighter_win_pose picks (game_ticks + index) % poses), and logged from the pose's
start: the effect entities alive (a pool entity whose bproj_t is one of the fighter's bm_wins obj), their rows / place /
frame. Checks: each listed effect is born on its step (its entity alive from that frame), lives its rows' count, ends;
and the fighter stays drawn on every frame of the pose (reopen 2026-10-15, "in the middle of the animation, Kyo
disappears": his block's SCB3 words in VRAM, some column with a height, unless the line guard hid him).
Out: OUT/results.json, OUT/<fighter>_pose<k>.png (source above, brawler below: every 6th frame from the pose start)."""
import ctypes as C, json, os, sys
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H, win184_proof as W, winposes_proof as WP

FIGHTERS = {   # brawler fighter -> (game, cid): the KOF roster fighters whose source win poses spawn objects
    'kyo': ('kof98', 0), 'terry': ('kof98', 3), 'robert': ('kof98', 7), 'mai': ('kof98', 16), 'yashiro': ('kof98', 21),
    'iori': ('kof98', 27), 'rugal': ('kof98', 36), 'k_dash': ('kof99', 0)}
SRC = '/data/tmp/winfx/src'                                   # winfx98.py OUTDIR
SIZEOF_BPROJ = 64                                             # (upper bound for the obj array test below: one table)

def pose_buttons(game, cid):
    """the brawler's pose k -> the button whose state list it is (export96 win_state_lists' order)"""
    sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); import export96 as E
    out, seen = [], []
    for b in 'ABCD':
        sts = E.win_states(game, cid, b)
        if sts in seen: continue
        seen.append(sts); out.append(b)
    return out

def run_pose(name, k, n, delta):
    """one stage clear, pose k forced (game_ticks written while the winner waits, shifted by delta)"""
    def hook(bb, row):
        row['ticks'] = bb.r(bb.syms['game_ticks'], 4)
        if row['phase'] >= 3 and not row['p0'].get('wan'):
            bb.w(bb.syms['game_ticks'], 4, (row['ticks'] & ~0xFF) | ((k - delta) % n + n * 8))
        ents = []
        for i in range(8):
            if bb.pget(i, 'state') and HOOK['obj'] <= bb.pget(i, 'pdef') < HOOK['obj'] + HOOK['span']:
                ents.append([i, bb.pget(i, 'pdef'), bb.pget(i, 'prow'), bb.pget(i, 'frame_ovr'), round(bb.pget(i, 'x'), 1), round(bb.pget(i, 'y'), 1)])
        row['fx'] = ents
        if VRAM['v'] is None:
            bb.core.retro_get_memory_data.restype = C.c_void_p
            VRAM['v'] = (C.c_uint16 * 0x8800).from_address(bb.core.retro_get_memory_data(3))   # (RETRO_MEMORY_VIDEO_RAM)
        v, spr, nc = VRAM['v'], bb.fget(0, 'spr'), bb.fget(0, 'ncols')
        row['drawn'] = [nc, sum(1 for c in range(nc) if v[0x8200 + spr + c] & 63), bb.r(bb.syms['guard_hidden'], 1)]
    return W.stage_run(name, shots_every=2, extra=('wan', 'wpose', 'frame_ovr'), hook=hook)

HOOK = {'obj': 1 << 30, 'span': 0}
VRAM = {'v': None}                                           # the core's VRAM words (one core per process)

def src_row(game, cid, b, offsets):
    """the source's snapshots from its pose start (winfx98: snap every 3 frames from START + FROM), P1 cropped"""
    r = json.load(open(os.path.join(SRC, f'{game}_{cid}.json')))[b.lower()]
    t0 = next(row[0] for row in r['p1'] if row[1]) + r['ko']        # the pose's first frame (absolute)
    d = os.path.join(SRC, f'{game}_{cid}_{b.lower()}')
    fr = sorted(int(f[5:-4]) for f in os.listdir(d) if f.startswith('snap_'))
    out = []
    for o in offsets:
        f = min(fr, key=lambda v: abs(v - (t0 + o)))
        im = Image.open(os.path.join(d, f'snap_{f}.ppm')).convert('RGB')
        out.append(im.crop((0, 24, im.width, 224)))                 # (the whole screen: a thrown cap flies far)
    return out

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    a = sys.argv[2:]
    only = a[a.index('--only') + 1].split(',') if '--only' in a else list(FIGHTERS)
    W.BA = W.ba_win()
    res, ok_all = {}, True
    for name in only:
        game, cid = FIGHTERS[name]
        buttons = pose_buttons(game, cid)
        res[name] = {}
        poses = fx = obj = None
        delta = 0
        for k, btn in enumerate(buttons):
            for attempt in range(len(buttons) + 2):
                b, log, shots = run_pose(name, k, len(buttons), delta)
                poses, vox, fx, obj = WP.tables(b, name)
                if not fx or not any(p == k for p, _, _ in fx): break
                if HOOK['obj'] != obj: HOOK['obj'], HOOK['span'] = obj, 64 * 64; continue   # (again, watching it)
                pr = [r for r in log if r['phase'] == 4 and r['mode'] == 1 and r['p0'].get('wan')]
                if pr and pr[0]['p0']['wpose'] == k: break
                delta += 1
            if not fx or not any(p == k for p, _, _ in fx): continue
            t0 = pr[0]['t']
            want = poses[k]
            starts = {s: sum(tk + 1 for _, tk in want[:s]) for s in range(len(want))}   # each step's first frame
            births = sorted(starts[s] for p, s, _ in fx if p == k)
            alive = [(r['t'] - t0, len(r['fx'])) for r in log if r['t'] >= t0]
            first = next((t for t, c in alive if c), None)
            last = max((t for t, c in alive if c), default=None)
            item = {'pose': k, 'button': btn, 'wpose': pr[0]['p0']['wpose'], 'effects': len(births), 'births_at': births,
                    'first_alive': first, 'last_alive': last, 'max_at_once': max(c for _, c in alive)}
            # the fighter drawn on every frame of the pose (VRAM lags the tick by one frame: from its second frame)
            gone = [r['t'] - t0 for r in log if r['t'] > t0 and r['p0'].get('wan') and r['drawn'][0] and not r['drawn'][1] and not r['drawn'][2]]
            item['fighter_gone_frames'] = len(gone); item['fighter_gone_first'] = gone[:5]
            item['ok'] = item['wpose'] == k and first is not None and first == births[0] and not gone
            ok_all &= item['ok']
            res[name][str(k)] = item
            print(name, 'pose', k, btn, 'OK' if item['ok'] else 'FAIL', item, flush=True)
            offs = list(range(0, 6 * 12, 6)) if last is None else sorted({min(last + 6, o) for o in range(0, last + 7, max(6, (last + 6) // 11 // 6 * 6))})[:12]
            srow = src_row(game, cid, btn, offs)
            brow = []
            for o in offs:
                tt = t0 + o; im = shots.get(tt) or shots.get(tt + 1) or shots.get(tt - 1)
                if im is None: brow.append(Image.new('RGB', (160, 200), 'white')); continue
                row = next(r for r in log if r['t'] == tt)
                brow.append(im.crop((0, 24, im.width, 224)))
            W.grid([[W.label(i, f'+{o}') for i, o in zip(srow, offs)], [W.label(i, f'+{o}') for i, o in zip(brow, offs)]],
                   [f'{name}: {game.upper()} win pose {btn} (source, our emulator)', f'{name}: brawler pose {k} (stage clear)'],
                   os.path.join(out, f'{name}_pose{k}.png'), cell=(304, 200))
        HOOK['obj'] = 1 << 30
    json.dump(res, open(os.path.join(out, 'results.json'), 'w'), indent=1)
    print('ALL OK' if ok_all else 'FAILED')

if __name__ == '__main__':
    main()
