#!/usr/bin/env python3
"""RAM traces of the brawler for build-to-build comparisons (harness, our emulator's core; never MAME).

    python3 ramtrace.py GAME_DIR attract|campaign OUT.json     record (GAME_DIR/brawler.neo, symbols from its build/rom.elf)
    python3 ramtrace.py GAME_DIR campaign OUT.json --replay BASE.json   the same inputs and test pokes as BASE, frame for frame
    python3 ramtrace.py --diff A.json B.json                   compare two recordings
    ... --pack PACK.bin                                        send a Brawler Lab data pack (build_tables.py pack) at tick 100
                                                               (installed at the next safe point): the game must play the same

attract   power on, three attract demos (8100 frames): every frame the flow (mode, attract, phase, wave, cam_x, lock_x)
          and every fighter's state, position, life, facing, animation step, fighter, colour set, power and tint
campaign  coin, START, fighter 0, then every stage: each wave 240 frames with P1 standing (life refilled) while the
          enemies come and fight, then cleared (test poke: enemies OFF), the walk to the next lock point; the boss and its
          minions 900 frames, then the boss set DEAD; STAGE CLEAR, BOSS UNLOCKED, the next stage. Everything else is the
          game's own code (spawns, picks, AI presets, tints, lock points). The run reacts to what it reads, so a second
          build is compared with --replay: the first run's inputs and pokes on the same frames, no reaction (a +-1 frame
          sampling difference would otherwise shift every later input)
The harness samples RAM at a video frame's end, inside the game's tick (regress.py `near`): a frame matches when it equals
the other trace's at that frame or one either side.

Tick-keyed (2026-10-05): every sample carries the game's tick counter (crt0 `game_ticks`: ticks started), so a lag frame
(a tick longer than a frame) shifts frames, not ticks. A recording keeps P1's input per tick (the input of the frame in
which that tick started: the tick reads the pads as it starts) and each test poke at the tick in progress; --replay
feeds them by tick (the next tick to start gets its recorded input; a poke is made once its tick is in progress), and
--diff compares the samples tick for tick (the sample at the end of a frame is mid-tick, between two fighters' updates:
the flow and each fighter equal to the other trace's at that tick or one either side). A build without the counter is compared frame by frame as before."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FIELDS = ['state', 'x', 'z', 'y', 'hp', 'hp_max', 'facing', 'anim', 'step', 'set', 'power', 'tint']


def record(game, what, out, replay=None, pack=None):
    from harness import Brawler
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    S = b.syms; OFF, DEAD = b.states.index('OFF'), b.states.index('DEAD')
    def s16(n): v = b.r(S[n], 2); return v - 65536 if v > 32767 else v
    def snap():
        flow = [b.r(S['mode'], 1), b.r(S['attract'], 1), b.r(S['phase'], 1), b.r(S['wave'], 1), s16('cam_x'), s16('lock_x')]
        fs = []
        for i in range(8):
            st = b.fget(i, 'state')
            fs.append(None if st == OFF else [round(b.fget(i, f), 2) if f in ('x', 'z', 'y') else b.fget(i, f) for f in FIELDS] + [b.char_of(i)])
        return [flow, fs]
    tr = []; log = []                                   # log: P1's input each frame, and the test pokes made before it
    pokes = {}
    gt = S.get('game_ticks')
    ticks = lambda: b.r(gt, 4) if gt else len(tr)
    tk = []; in_tick = {}; tpokes = []                  # tick at each sample; P1's input per tick; (tick, poke)
    sent = []
    if pack: from chainlab.labdrive import PACK_OFF, PACK_STAT_OFF
    def poke(kind):
        pokes.setdefault(len(tr), []).append(kind); tpokes.append((ticks(), kind))
        if kind == 'clear': [b.fset(i, 'state', OFF) for i in range(2, 8)]
        elif kind == 'boss': b.fset(2, 'hp', 0); b.fset(2, 'state', DEAD); b.fset(2, 'state_t', 0)
    def run(n, p1=''):
        for _ in range(n):
            t0 = ticks()
            if pack and t0 >= 100 and not sent:             # the lab's data pack, at tick 100: installed at the next safe point
                for i, v in enumerate(b'LAB1'): b.w(S['lab'] + i, 1, v)
                for i, v in enumerate(pack): b.w(S['lab'] + PACK_OFF + i, 1, v)
                b.w(S['lab'] + 7, 1, 3); sent.append(t0)
            b.run(1, p1=p1, each=keep if what != 'attract' else None); log.append(p1); tr.append(snap())
            t1 = ticks(); tk.append(t1)
            for k in range(t0 + 1, t1 + 1): in_tick[k] = p1   # the ticks that started in this frame read its input
    keep = lambda bb: bb.fset(0, 'hp', 60)
    b.core.retro_reset(); b.frame = 0
    if replay and 'in_tick' in json.load(open(replay)) and gt:   # by tick: the recorded inputs and pokes (open loop)
        base = json.load(open(replay))
        bin_ = {int(k): v for k, v in base['in_tick'].items()}; bp = list(base['tick_pokes']); last = base['ticks'][-1]
        while ticks() < last:
            while bp and bp[0][0] <= ticks(): poke(bp.pop(0)[1])
            run(1, bin_.get(ticks() + 1, ''))
    elif replay:                                        # the recorded inputs and pokes, frame for frame (open loop)
        base = json.load(open(replay))
        for i, p1 in enumerate(base['inputs']):
            for k in base['pokes'].get(str(i), []): poke(k)
            run(1, p1)
    elif what == 'attract':
        run(8100)
    else:
        enemies = lambda: [i for i in range(2, 8) if b.fget(i, 'state') != OFF]
        phase = lambda: b.r(S['phase'], 1)
        def until(cond, n, p1='', what=''):
            for _ in range(n):
                if cond(): return
                run(1, p1)
            raise RuntimeError('timeout: ' + what)
        run(600); run(4, 'o'); run(100); run(4, 's'); run(100); run(4, 'a')   # coin, START, the first fighter (Terry)
        for st in range(5):                                     # the five stages
            until(lambda: b.r(S['mode'], 1) == 1 and b.r(S['fade_in'], 1) == 0, 900, what='fight')
            while phase() in (0, 1):
                until(lambda: phase() == 0 and enemies(), 2000, 'R', 'wave')
                run(240)
                until(lambda: b.states[b.fget(0, 'state')] in ('IDLE', 'WALK'), 900, what='P1 free')
                poke('clear')                                   # test poke: the wave beaten
                until(lambda: phase() != 0, 10, what='GO')
                until(lambda: phase() != 1, 2000, 'R', 'next lock')
            run(900)
            until(lambda: b.states[b.fget(0, 'state')] in ('IDLE', 'WALK') and b.states[b.fget(2, 'state')] in ('IDLE', 'WALK'), 900, what='free')
            poke('boss')                                        # test poke: the boss beaten
            until(lambda: phase() == 4, 900, what='clear')
            until(lambda: b.r(S['mode'], 1) != 1 or b.r(S['camp'], 1) != st, 900, what='after clear')
            if b.r(S['mode'], 1) == 3:                          # BOSS UNLOCKED: on to the next stage
                run(100); run(4, 'a'); until(lambda: b.r(S['mode'], 1) != 3, 400, what='unlock end')
        run(300)
    if pack: print('pack sent at tick', sent, 'status', b.r(S['lab'] + PACK_STAT_OFF, 1), '(2 = installed)')
    json.dump({'trace': tr, 'inputs': log, 'pokes': pokes, 'ticks': tk if gt else None, 'in_tick': in_tick if gt else None,
               'tick_pokes': tpokes}, open(out, 'w'))
    print(what, len(tr), 'frames ->', out)


def by_tick(x):
    """tick -> the sample at the end of the first frame that ended inside it"""
    d = {}
    for t, s in zip(x['ticks'], x['trace']): d.setdefault(t, s)
    return d


def diff(a, b):
    X, Y = json.load(open(a)), json.load(open(b))
    if isinstance(X, dict) and isinstance(Y, dict) and X.get('ticks') and Y.get('ticks'):
        A, B = by_tick(X), by_tick(Y)
        common = sorted(set(A) & set(B)); bad = []
        def parts(x): return [x[0]] + list(x[1])                # the flow, then each fighter
        def near(t):                                            # each part equal to the other's at t or one tick either side:
            for k, (pa, pb) in enumerate(zip(parts(A[t]), parts(B[t]))):   # the sample cuts the tick between two fighters'
                if pa != pb and not any(u in B and pa == parts(B[u])[k] or u in A and pb == parts(A[u])[k] for u in (t - 1, t + 1)):
                    return False                                # updates, so one fighter may be a tick ahead of another
            return True
        for t in common:
            if A[t] != B[t] and not near(t): bad.append(t)
        lagA, lagB = len(X['ticks']) - len(A), len(Y['ticks']) - len(B)
        print(f'by tick: {len(A)} / {len(B)} ticks ({len(X["ticks"])} / {len(Y["ticks"])} frames, frames without a new tick {lagA} / {lagB}), '
              f'{len(common)} common, {len(bad)} differ (beyond +-1 tick sampling)', 'first:' if bad else '', bad[:10])
        if bad: print(' A', A[bad[0]], '\n B', B[bad[0]])
        return not bad and abs(len(A) - len(B)) <= 2
    A, B = [x if isinstance(x, list) else x['trace'] for x in (X, Y)]
    n = min(len(A), len(B)); bad = []
    for i in range(n):
        if A[i] != B[i] and not any(0 <= j < len(B) and A[i] == B[j] for j in (i - 1, i + 1)):
            bad.append(i)
    print(f'{len(A)} / {len(B)} frames, {len(bad)} differ (beyond +-1 frame sampling)', 'first:' if bad else '', bad[:10])
    if bad: print(' A', A[bad[0]], '\n B', B[bad[0]])
    return not bad and len(A) == len(B)


if __name__ == '__main__':
    if sys.argv[1] == '--diff': sys.exit(0 if diff(sys.argv[2], sys.argv[3]) else 1)
    a = sys.argv[1:]
    pk = open(a[a.index('--pack') + 1], 'rb').read() if '--pack' in a else None
    record(*a[:3], replay=a[a.index('--replay') + 1] if '--replay' in a else None, pack=pk)
