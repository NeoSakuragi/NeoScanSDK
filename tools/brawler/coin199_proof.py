#!/usr/bin/env python3
"""TODO #199 proof: the coin sound = KOF94's. KOF94 (measured in our emulator, SNDLOG: every coin in the attract demo /
title sends $7F from its sound routine $6556) plays $7F as an SSG effect song (makoto3 driver); the brawler's SSG cue
COIN ($78, songs.json "ssg", ssg_cues.py raw periods) must write the same SSG states (period, level per voice, in
order) with each step's start within one cue tick; the four former cues write the same SSG registers as before (the
streams now use running status: BASE_ROM = a build without #199); and the game sends $78 at every credit: the coin
that ends the attract demo, a coin on the title, on the select screen, in the fight and on the CONTINUE? screen
(harness, MVS hardware, the Z80 port tap: the command read and the SSG writes that follow).

    python3 coin199_proof.py OUTDIR BASE_ROM      -> OUTDIR/coin199.json + kof94_7F.wav / brawler_78.wav"""
import ctypes as C, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(TOOLS, 'port'))
import harness, ssg_cues as S
harness.CORE = '/data/neogeo_dict/sound/snd98/ff3/geolith_tap.so'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
GAME = harness.GAME

def states_ms(cap, start):
    """per voice: [(state, start ms from the first audible step)] (state = (period, level) or None)"""
    lines = open(cap).read().split('\n'); i = next(k for k, l in enumerate(lines) if l.startswith(start))
    f0 = next((int(l.split()[1]) for l in reversed(lines[:i]) if l.startswith('f ')), 0)
    tmp = cap + '.from'; open(tmp, 'w').write(f'f {f0}\n' + '\n'.join(lines[i:]))
    st = S.ssg_states(tmp); fr = [f for _, f, _ in st]
    busy = [n for n, _, s in st if any(S.audible(s))]
    t_int = (fr[busy[-1]] - fr[busy[0]]) / (busy[-1] - busy[0]) / S.FRAME_HZ * 1000
    out = []
    for c in range(3):
        k, steps = 0, []
        for a, n in S.runs(st, c):
            if k + n > busy[0] and k <= busy[-1]: steps.append([a, round((max(k, busy[0]) - busy[0]) * t_int, 1)])
            k += n
        while steps and steps[-1][0] is None: steps.pop()
        while steps and steps[0][0] is None: steps.pop(0)
        m = []                                             # equal neighbours = one audible state
        for a, t in steps:
            if not m or m[-1][0] != a: m.append([a, t])
        out.append(m)
    return out, t_int

def ssg_writes(cap):
    return [l for l in open(cap) if l.startswith('a ') and int(l.split()[1], 16) <= 0x0D]

def main(out, base):
    os.makedirs(out, exist_ok=True); res = {}
    # 1. KOF94's $7F vs the brawler's $78
    k94 = os.path.join(out, 'kof94_7F')
    subprocess.run([sys.executable, os.path.join(TOOLS, 'makoto3', 'capture.py'), '--game', 'kof94', k94 + '.txt', '1100',
                    '--block', '880', '--send', '900:7F', '--wav', k94 + '.wav'], check=True, stdout=subprocess.DEVNULL)
    S.capture('78', 1.5, os.path.join(out, 'brawler_78'), os.path.join(GAME, 'brawler.neo'))
    a, ta = states_ms(k94 + '.txt', 's 7F'); b, tb = states_ms(os.path.join(out, 'brawler_78.txt'), 'c 78')
    same = [[x for x, _ in va] == [x for x, _ in vb] for va, vb in zip(a, b)]
    dt = max(abs(x[1] - y[1]) for va, vb in zip(a, b) for x, y in zip(va, vb))
    res['kof94_vs_brawler'] = {'states_identical_per_voice': same, 'max_step_start_diff_ms': dt, 'kof94_interrupt_ms': round(ta, 3),
                               'brawler_interrupt_ms': round(tb, 3), 'kof94': a, 'brawler': b}
    print('KOF94 $7F vs brawler $78: states identical', same, 'step starts within', dt, 'ms', flush=True)
    # 2. the former cues: SSG writes as before
    res['former_cues'] = {}
    for cmd in ('74', '75', '76', '77'):
        S.capture(cmd, 1.5, os.path.join(out, f'new_{cmd}'), os.path.join(GAME, 'brawler.neo'))
        S.capture(cmd, 1.5, os.path.join(out, f'base_{cmd}'), base)
        ok = ssg_writes(os.path.join(out, f'new_{cmd}.txt')) == ssg_writes(os.path.join(out, f'base_{cmd}.txt'))
        res['former_cues'][cmd] = ok; print(f'cue ${cmd}: SSG writes identical to the base build: {ok}', flush=True)
    # 3. in the game: a coin on every screen
    bw = harness.Brawler(game=GAME); Y = bw.syms
    log = []
    def tap(write, port, v):
        if not write and port & 0xFF == 0 and v: log.append((bw.frame, 'c', v))
        if write and port & 0xFF == 4: tap.r = v
        if write and port & 0xFF == 5 and tap.r <= 0x0D: log.append((bw.frame, 'ssg', tap.r))
        return v
    tap.r = 0xFF
    cb = TAP(tap); bw.core.retro_neoscan_z80_tap(cb)
    bw.core.retro_reset()
    def coin(where, wait=240):
        log.clear(); f0 = bw.frame; bw.seq(f'4:o,{wait}:-')
        cmds = [(f - f0, v) for f, k, v in log if k == 'c']
        heard = next((f for f, v in cmds if v == 0x78), None)
        ssg = sum(1 for f, k, _ in log if k == 'ssg' and heard is not None and f - f0 >= heard)
        r = {'z80_read_78_at': heard, 'ssg_writes_after': ssg, 'commands': [f'{v:02X}@{f}' for f, v in cmds][:12],
             'ok': heard is not None and ssg > 20}
        res.setdefault('game', {})[where] = r
        print(where, 'OK' if r['ok'] else 'FAIL', r, flush=True)
    bw.seq('600:-')
    coin('attract demo -> title')
    coin('title')
    bw.seq('4:s,100:-')
    coin('select')
    bw.seq('4:a,300:-')
    coin('fight')
    bw.w(Y['lives'], 1, 0); bw.fset(0, 'hp', 0)                   # P1 out of lives, dead: the CONTINUE? screen
    bw.fset(0, 'state', bw.states.index('DEAD')); bw.fset(0, 'state_t', 0)
    for _ in range(900):
        bw.run(1)
        if bw.r(Y['cont_ov'], 1) == 1: break
    res['continue_screen_reached'] = bw.r(Y['cont_ov'], 1) == 1
    bw.run(30); coin('continue')
    json.dump(res, open(os.path.join(out, 'coin199.json'), 'w'), indent=1)
    return all(same) and all(res['former_cues'].values()) and all(r['ok'] for r in res['game'].values()) and \
        res['continue_screen_reached']

if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1], sys.argv[2]) else 1)
