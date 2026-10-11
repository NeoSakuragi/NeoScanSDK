#!/usr/bin/env python3
"""Proof of the random win poses (voice note 20261011-132148-5d29, Bruno: "there are multiple win poses in Samurai Shodown
2. Integrate them in the game, and in general, for fighters with multiple win poses, play a random one at the end").

    python3 winposes_proof.py OUT [--only name,...] [--tries N]

Per fighter (default: SS2 Haohmaru / Genjuro / Hanzo, KOF98 Terry, KOF99 K', KOF96 Geese = one pose): campaign stage 1
cleared again and again (win184_proof.stage_run: its boss alone, life 1, P1 mashing A, then everything pressed through the
clear), each run started a frame later than the one before (the setup's wait), until every pose of the fighter
(fighter_win_poses: BA_WIN + bm_wins) was played, at most --tries runs. Per run, from the build's own tables: the pose
picked (fighter_t.wpose), the frames it showed (frame_ovr) against its animation's steps in order (BA_WIN, or
bm_wins[id].anims[k - 1], read from the ROM), the voices of its list sent at their steps (sound.c's queue), a step
effect's entity (Haohmaru's sword: its rows' heights while it lives, gone at the catch), the next screen after
the pose + WIN_HOLD (a pose longer than the clear's WIN_MAX: cut there). The pick = (game_ticks + P1's index 0) % its poses
at its frame (game_ticks read the frame it starts: the tick it was picked on or the one before): a replay, which repeats
the ticks, repeats the pose (the harness's own runs jitter by lag frames: regress.py).
Out: OUT/results.json, OUT/<fighter>.png (one row per pose: 10 frames spread from its start to its end, P1 cropped)."""
import json, os, re, sys
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H, scenario as SC, win184_proof as W

GAME = H.GAME
DEFAULT = ['haohmaru', 'genjuro', 'hanzo_ss2', 'terry', 'k_dash', 'geese']
WIN_HOLD = 45
WIN_MAX = 720                                            # main.c

_P = None
class Rom:
    """the first program MB of the built .neo (its P region is word-swapped: neobuild.py)"""
    def __init__(self):
        global _P
        if _P is None:
            raw = open(os.path.join(GAME, 'brawler.neo'), 'rb').read()
            n = int.from_bytes(raw[4:8], 'little'); p = raw[0x1000:0x1000 + n]
            _P = bytes(p[i ^ 1] for i in range(0x100000))
        self.p = _P
    def r(self, a, n): return int.from_bytes(self.p[a:a + n], 'big')

def tables(b, name):
    """(BA_WIN's step frames, [each other pose's step frames], vox, fx) read from the ROM through the build's symbols"""
    syms = b.syms; b = Rom(); b.syms = syms
    k = W.roster().index(name)
    chs = b.syms.get('bm_chars_rom') or b.syms['bm_chars']
    ch = chs + k * b.syms['sizeof_bchar']
    anims = b.r(ch + 14, 4)                                          # bchar_t.anims (draw.s CH_ANIMS)
    def steps(an):
        n = b.r(an, 1); st = b.r(an + 2, 4)
        return [(b.r(st + 14 * i, 2), b.r(st + 14 * i + 2, 1)) for i in range(n)]   # (frame, ticks)
    ba = W.ba_win()
    poses = [steps(anims + 6 * ba)]
    w = b.syms['bm_wins'] + 18 * k                                   # bwin_t: n, anims, vox, fx, obj (18 bytes)
    n = b.r(w, 1)
    for i in range(n): poses.append(steps(b.r(w + 2, 4) + 6 * i))
    def lst(a):
        out = []
        while a and b.r(a, 1) != 0xFF: out.append((b.r(a, 1), b.r(a + 1, 1), b.r(a + 2, 1))); a += 3
        return out
    return poses, lst(b.r(w + 6, 4)) if n else [], lst(b.r(w + 10, 4)) if n else [], b.r(w + 14, 4) if n else 0

HOOK = {'obj': 0}
def run_one(name, wait):
    b, log, shots = None, None, None
    SC_setup = SC.setup
    def setup(bb, rec):                                              # the same run, started `wait` frames later
        rec['setup']['wait'] = wait
        return SC_setup(bb, rec)
    SC.setup = setup
    def hook(bb, row):
        row['sword'] = None; row['ticks'] = bb.r(bb.syms['game_ticks'], 4)
        if not HOOK['obj']: return
        off = bb.states.index('OFF')
        for i in range(8):
            if bb.pget(i, 'pdef') == HOOK['obj'] and bb.pget(i, 'state') != off:
                row['sword'] = (bb.pget(i, 'prow'), round(bb.pget(i, 'y'), 1), bb.pget(i, 'frame_ovr')); break
    try: b, log, shots = W.stage_run(name, shots_every=2, extra=('wan', 'wpose', 'frame_ovr'), hook=hook)
    finally: SC.setup = SC_setup
    return b, log, shots

def proj_rows(b, obj):
    """a projectile entity on the definition obj: (its row, height px) per frame"""
    for i in range(8):
        if b.pget(i, 'pdef') == obj and b.pget(i, 'state') != 0: return i
    return None

def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    a = sys.argv[2:]
    only = a[a.index('--only') + 1].split(',') if '--only' in a else DEFAULT
    tries = int(a[a.index('--tries') + 1]) if '--tries' in a else 12
    W.BA = W.ba_win()
    res = {}
    ok_all = True
    for name in only:
        seen, rows, r_ = {}, {}, []
        n_poses = None
        for t in range(tries):
            wait = 150 + t
            b, log, shots = run_one(name, wait)
            poses, vox, fx, obj = tables(b, name)
            if obj and not HOOK['obj']: HOOK['obj'] = obj; b, log, shots = run_one(name, wait)   # (again, watching it)
            n_poses = len(poses)
            pr = [r for r in log if r['phase'] == 4 and r['mode'] == 1 and r['p0'].get('wan')]
            if not pr: r_.append({'wait': wait, 'posed': False}); ok_all = False; continue
            k = pr[0]['p0']['wpose']; t0 = pr[0]['t']
            want = poses[k]
            shown = [r['p0']['frame_ovr'] for r in pr]
            seq = [want[r['p0']['step']][0] for r in pr]
            steps = [r['p0']['step'] for r in pr]
            done = next((r['t'] for r in pr if r['p0']['anim_done']), None)
            # the step frames, in order, each as long as its ticks + 1 (the last held)
            exp = [f for f, tk in want for _ in range(tk + 1)]
            timing = shown[:len(exp) - 1] == exp[:len(exp) - 1][:len(shown)]
            stream = [(r['t'], x) for r in log if r['t'] >= t0 for x in r['snd']]
            tk0 = pr[0]['ticks']                                  # the pick: fighter.c fighter_win_pose, at its frame
            item = {'wait': wait, 'pose': k, 'of': n_poses, 'start_t': t0, 'game_ticks': tk0,
                    'pick_rule': any((((tk0 - d) & 0xFF) + 0) % n_poses == k for d in (0, 1)), 'done_t': done, 'next_t': log[-1]['t'],
                    'frames_match': shown == seq, 'timing_match': timing, 'steps_in_order': steps == sorted(steps),
                    'last_step': steps[-1], 'nsteps': len(want), 'voices_listed': [(s, v) for p, s, v in vox if p == k],
                    'sound_bytes': len(stream)}
            if obj and any(p == k for p, _, _ in fx):
                hs = [(r['t'] - t0, r['sword']) for r in log if r.get('sword') is not None and r['t'] >= t0]
                item['effect'] = {'frames_alive': len(hs), 'first': hs[:3], 'last': hs[-3:]}
            clr = next(r['t'] for r in log if r['phase'] == 4)
            item['cut_at_win_max'] = done is None and sum(tk + 1 for _, tk in want) > WIN_MAX - (t0 - clr) and \
                log[-1]['t'] - clr >= WIN_MAX - 2   # (a pose longer than the clear's WIN_MAX: SS2 Hanzo's 202, 844 frames)
            item['ok'] = item['pick_rule'] and item['frames_match'] and item['timing_match'] and item['steps_in_order'] and \
                (item['cut_at_win_max'] or item['last_step'] == len(want) - 1 and (log[-1]['t'] - (done or 0)) >= WIN_HOLD - 1)
            ok_all &= item['ok']
            r_.append(item)
            if k not in seen:                                         # its contact sheet row: every 6th frame
                seen[k] = wait
                crops = []
                span = (done or pr[-1]['t']) + 8 - t0                         # 10 frames spread over the pose
                for tt in sorted({t0 + span * j // 9 for j in range(10)}):
                    im = shots.get(tt) or shots.get(tt + 1) or shots.get(tt - 1)
                    if im is None: continue
                    row = next(r for r in log if r['t'] == tt)
                    cam = row['cam'] - 65536 if row['cam'] > 32767 else row['cam']
                    crops.append(W.crop_player(im, row['p0']['x'], cam))
                rows[k] = crops
            print(name, 'wait', wait, 'pose', k, '/', n_poses, 'OK' if item['ok'] else 'FAIL', {x: item[x] for x in ('frames_match', 'timing_match', 'last_step', 'nsteps')},
                  item.get('effect', ''), flush=True)
            if len(seen) == n_poses and t >= 1: break
        res[name] = {'poses': n_poses, 'seen': sorted(seen), 'runs': r_}
        ok_all &= len(seen) == n_poses
        print(name, f'{len(seen)}/{n_poses} poses seen in {len(r_)} runs; every pick = (game_ticks + 0) % {n_poses}: '
              f'{all(x.get("pick_rule") for x in r_ if "pose" in x)}', flush=True)
        W_, Hh = 160, 200
        ncol = max((len(v) for v in rows.values()), default=1)
        sheet = Image.new('RGB', (100 + W_ * ncol, (Hh + 4) * max(1, len(rows))), 'white'); d = ImageDraw.Draw(sheet)
        for j, k in enumerate(sorted(rows)):
            d.text((4, j * (Hh + 4) + 4), f'{name}\npose {k}\n(wait {seen[k]})', fill='black')
            for c, im in enumerate(rows[k]): sheet.paste(im, (100 + c * W_, j * (Hh + 4)))
        sheet.save(os.path.join(out, f'{name}.png'))
    json.dump(res, open(os.path.join(out, 'results.json'), 'w'), indent=1)
    print('ALL OK' if ok_all else 'FAILED')
    sys.exit(0 if ok_all else 1)

if __name__ == '__main__':
    main()
