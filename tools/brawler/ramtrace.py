#!/usr/bin/env python3
"""RAM traces of the brawler for build-to-build comparisons (harness, our emulator's core; never MAME).

    python3 ramtrace.py GAME_DIR attract|campaign OUT.json     record (GAME_DIR/brawler.neo, symbols from its build/rom.elf)
    python3 ramtrace.py GAME_DIR campaign OUT.json --replay BASE.json   the same inputs and test pokes as BASE, frame for frame
    python3 ramtrace.py --diff A.json B.json [--from-stage]    compare two recordings (--from-stage: from each one's first
                                                               campaign sample on, ticks counted from there: a page whose core
                                                               ran before its reset boots warm, its BIOS a few ticks longer)
    ... --pack PACK.bin                                        send a Brawler Lab data pack (build_tables.py pack) at tick 100
                                                               (installed at the next safe point): the game must play the same
    python3 ramtrace.py GAME_DIR stage OUT.json --stage S --wave W [--pack PACK.bin] [--fighter F] [--frames N]
                                                               the Stages tab's "play from here" (lab req 4 with the pack) on the
                                                               desktop core, SNK's MVS BIOS as in the page: chainlab/stage_proof.sh
    python3 ramtrace.py GAME_DIR lab OUT.json --dummy D [--pack PACK.bin] [--fighter F] [--frames N]
                                                               the Characters tab's "Test on the dummy" (lab req 1, the Chain
                                                               Lab training, with the pack, the same frame), P1 plays
                                                               CHAR_SCRIPT (the four specials): chainlab/char_proof.sh
    python3 ramtrace.py GAME_DIR enemy OUT.json --enemy E [--pack PACK.bin] [--fighter F] [--frames N]
                                                               the Enemies tab's "Test it" (lab req 3, enemy E with the pack, the
                                                               same frame); OUT also holds the enemy's palettes (palette RAM
                                                               slots 32-39) at the end: chainlab/enemy_proof.sh

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

STAGE_SCRIPT = '40:R,2:a,8:-,2:a,8:-,2:b,16:-,20:L,2:Da,30:-'   # P1 in the Stages tab's proof, repeated (frames:keys)
CHAR_SCRIPT = '30:-,2:Ud,100:-,2:d,100:-,2:Rd,100:-,2:Dd,100:-,2:Ud,100:-'   # the Characters tab's proof: up+D, D, fwd+D, down+D, up+D
BOOT_FRAMES = 400                                                 # = lab.js BOOT_FRAMES
FIELDS = ['state', 'x', 'z', 'y', 'hp', 'hp_max', 'facing', 'anim', 'step', 'set', 'power', 'tint']


def record(game, what, out, replay=None, pack=None, stage=None):
    import harness
    from harness import Brawler
    if what == 'enemy': what, enemy = 'stage', True
    else: enemy = False
    labr = what == 'lab'                                # the Characters tab's test: the Chain Lab training (req 1) with the pack
    if labr: what = 'stage'
    if what == 'stage': harness.OPTIONS.update({'geolith_system_type': 'mvs', 'geolith_region': 'us'})   # = web_core.c
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
            if pack and what != 'stage' and t0 >= 100 and not sent:             # the lab's data pack, at tick 100: installed at the next safe point
                for i, v in enumerate(b'LAB1'): b.w(S['lab'] + i, 1, v)
                for i, v in enumerate(pack): b.w(S['lab'] + PACK_OFF + i, 1, v)
                b.w(S['lab'] + 7, 1, 3); sent.append(t0)
            b.run(1, p1=p1, each=keep if what == 'campaign' else None); log.append(p1); tr.append(snap())
            t1 = ticks(); tk.append(t1)
            for k in range(t0 + 1, t1 + 1): in_tick[k] = p1   # the ticks that started in this frame read its input
    keep = lambda bb: bb.fset(0, 'hp', 60)
    b.core.retro_reset(); b.frame = 0
    def stage_start():                                  # boot, then the page's "play from here": pack + req 4, the same frame
        s_, w_, f_, n_ = stage
        b.core.retro_reset()
        for _ in range(BOOT_FRAMES): b.core.retro_run()
        L = S['lab']
        if pack:
            from chainlab.labdrive import PACK_OFF
            for i, v in enumerate(pack): b.w(L + PACK_OFF + i, 1, v)
        for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
        if pack: b.w(L + 7, 1, 3)
        if enemy: b.w(L + 5, 1, f_); b.w(L + 6, 1, s_); b.w(L + 4, 1, 3)       # req 3: P1 f_ against enemy s_
        elif labr: b.w(L + 5, 1, f_); b.w(L + 6, 1, s_); b.w(L + 4, 1, 1)      # req 1: P1 f_ against the dummy s_
        else: b.w(L + 13, 1, w_); b.w(L + 5, 1, f_); b.w(L + 6, 1, s_); b.w(L + 4, 1, 4)
        run(1)                                          # the page's play() steps one frame with no key (stages.js)
    if what == 'stage': stage_start()
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
    elif what == 'stage':                               # P1: STAGE_SCRIPT repeated, by frame (a second run: --replay, by tick)
        parts = [p.split(':') for p in (CHAR_SCRIPT if labr else STAGE_SCRIPT).split(',')]
        while len(tr) < stage[3]:
            for k, keys in parts:
                for _ in range(int(k)):
                    if len(tr) < stage[3]: run(1, keys.replace('-', ''))
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
    if pack and what != 'stage': print('pack sent at tick', sent, 'status', b.r(S['lab'] + PACK_STAT_OFF, 1), '(2 = installed)')
    if what == 'stage': print('pack status', b.r(S['lab'] + 3488, 1), '(2 = installed, 0 = none sent)')
    palram = None
    if enemy:                                           # the enemy's palettes as the game wrote them (bank 0, slot 16 + 2 * MAX_PALS)
        import ctypes as C
        b.core.retro_get_memory_data.restype = C.c_void_p
        w = (C.c_uint16 * 8192).from_address(b.core.retro_get_memory_data(104))
        palram = [[w[(32 + i) * 16 + k] for k in range(16)] for i in range(8)]
    json.dump({'trace': tr, 'inputs': log, 'palram': palram, 'pokes': pokes, 'ticks': tk if gt else None, 'in_tick': in_tick if gt else None,
               'tick_pokes': tpokes}, open(out, 'w'))
    print(what, len(tr), 'frames ->', out)


def by_tick(x):
    """tick -> the sample at the end of the first frame that ended inside it"""
    d = {}
    for t, s in zip(x['ticks'], x['trace']): d.setdefault(t, s)
    return d


def from_stage(x):
    """the samples from the first tick after the stage start on (the first campaign sample, mode 1 and not the attract
    demo, is the request's own tick: sampled mid-tick, its fighters still the demo's), ticks relative to it"""
    i = next(k for k, s in enumerate(x['trace']) if s[0][0] == 1 and s[0][1] == 0)
    i = next(k for k in range(i, len(x['ticks'])) if x['ticks'][k] > x['ticks'][i])
    return dict(x, trace=x['trace'][i:], ticks=[t - x['ticks'][i] for t in x['ticks'][i:]])


def diff(a, b, stage_start=False):
    X, Y = json.load(open(a)), json.load(open(b))
    if stage_start: X, Y = from_stage(X), from_stage(Y)
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
    if sys.argv[1] == '--diff': sys.exit(0 if diff(sys.argv[2], sys.argv[3], '--from-stage' in sys.argv) else 1)
    a = sys.argv[1:]
    pk = open(a[a.index('--pack') + 1], 'rb').read() if '--pack' in a else None
    opt = lambda k, d: int(a[a.index(k) + 1]) if k in a else d
    record(*a[:3], replay=a[a.index('--replay') + 1] if '--replay' in a else None, pack=pk,
           stage=(opt('--enemy', 0) if a[1] == 'enemy' else opt('--dummy', 1) if a[1] == 'lab' else opt('--stage', 0), opt('--wave', 0), opt('--fighter', 0), opt('--frames', 1800)))
