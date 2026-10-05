#!/usr/bin/env python3
"""RAM traces of the brawler for build-to-build comparisons (harness, our emulator's core; never MAME).

    python3 ramtrace.py GAME_DIR attract|campaign OUT.json     record (GAME_DIR/brawler.neo, symbols from its build/rom.elf)
    python3 ramtrace.py GAME_DIR campaign OUT.json --replay BASE.json   the same inputs and test pokes as BASE, frame for frame
    python3 ramtrace.py --diff A.json B.json                   compare two recordings

attract   power on, three attract demos (8100 frames): every frame the flow (mode, attract, phase, wave, cam_x, lock_x)
          and every fighter's state, position, life, facing, animation step, fighter, colour set, power and tint
campaign  coin, START, fighter 0, then every stage: each wave 240 frames with P1 standing (life refilled) while the
          enemies come and fight, then cleared (test poke: enemies OFF), the walk to the next lock point; the boss and its
          minions 900 frames, then the boss set DEAD; STAGE CLEAR, BOSS UNLOCKED, the next stage. Everything else is the
          game's own code (spawns, picks, AI presets, tints, lock points). The run reacts to what it reads, so a second
          build is compared with --replay: the first run's inputs and pokes on the same frames, no reaction (a +-1 frame
          sampling difference would otherwise shift every later input)
The harness samples RAM at a video frame's end, inside the game's tick (regress.py `near`): a frame matches when it equals
the other trace's at that frame or one either side."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FIELDS = ['state', 'x', 'z', 'y', 'hp', 'hp_max', 'facing', 'anim', 'step', 'set', 'power', 'tint']


def record(game, what, out, replay=None):
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
    def poke(kind):
        pokes.setdefault(len(tr), []).append(kind)
        if kind == 'clear': [b.fset(i, 'state', OFF) for i in range(2, 8)]
        elif kind == 'boss': b.fset(2, 'hp', 0); b.fset(2, 'state', DEAD); b.fset(2, 'state_t', 0)
    def run(n, p1=''):
        for _ in range(n):
            b.run(1, p1=p1, each=keep if what != 'attract' else None); log.append(p1); tr.append(snap())
    keep = lambda bb: bb.fset(0, 'hp', 60)
    b.core.retro_reset(); b.frame = 0
    if replay:                                          # the recorded inputs and pokes, frame for frame (open loop)
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
    json.dump({'trace': tr, 'inputs': log, 'pokes': pokes}, open(out, 'w'))
    print(what, len(tr), 'frames ->', out)


def diff(a, b):
    A, B = [x if isinstance(x, list) else x['trace'] for x in (json.load(open(a)), json.load(open(b)))]
    n = min(len(A), len(B)); bad = []
    for i in range(n):
        if A[i] != B[i] and not any(0 <= j < len(B) and A[i] == B[j] for j in (i - 1, i + 1)):
            bad.append(i)
    print(f'{len(A)} / {len(B)} frames, {len(bad)} differ (beyond +-1 frame sampling)', 'first:' if bad else '', bad[:10])
    if bad: print(' A', A[bad[0]], '\n B', B[bad[0]])
    return not bad and len(A) == len(B)


if __name__ == '__main__':
    if sys.argv[1] == '--diff': sys.exit(0 if diff(sys.argv[2], sys.argv[3]) else 1)
    record(*sys.argv[1:4], replay=sys.argv[5] if len(sys.argv) > 5 and sys.argv[4] == '--replay' else None)
