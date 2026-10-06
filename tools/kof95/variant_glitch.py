#!/usr/bin/env python3
"""KOF94 / KOF95 "variant flip" study (/data/neogeo_dict/kof95/variant_glitch.md): a special's weak / strong variant is
the bit +$E3 bit 0 of the fighter object, rewritten by the command recogniser ($B2C0 in KOF95) every time ANY of the
fighter's commands is recognised, also while a special is running; handlers that test the bit after their setup switch
variant mid-move. Runs scripted inputs in our emulator (emu/neogeo_sdl --capture, tools/kof96/capture/emu.py) from a
save state and prints the per-frame trace: P1 state, +$E3 bit 0, hit kind +$152, x, velocity +$50; P2 state, height,
life.

    python3 variant_glitch.py boot GAME              -> /data/neogeo_dict/ngsdl_sta/kof95/vs_kyo.state (Kyo vs Joe)
    python3 variant_glitch.py run GAME NAME          -> one scenario of SCENARIOS (trace + hit count)
    python3 variant_glitch.py corner GAME [STATE]    -> vs_kyo_corner.state (Kyo walks the opponent into the corner)
    python3 variant_glitch.py loop GAME MODE D PER N [norefill] -> the 75 Shiki Kai loop (MODE BqD = qcf B + 236D,
                                                       BB, DD), juggle hits; P2 life refilled unless norefill
    python3 variant_glitch.py scan GAME MODE          -> longest juggle over every timing of a loop"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
import emu
from boot_ngsdl import rle

NEO = {'kof95': '/data/roms/kof95.neo', 'kof94': '/data/roms/kof94.neo', 'kof98': '/data/roms/kof98.neo'}
TMP = '/data/tmp/variant'

def boot(game='kof95', save_at=820):
    """KOF95 vs_kyo.state from game_select.state (the GAME SELECT menu, saved from a title-screen boot: the cold boot
    of this core is not repeatable, the backup RAM changes the attract sequence): down = SINGLE VS, A, then A on both
    sides every 40 frames (character select on the default cursors: Kyo vs Joe, then the fight)"""
    ev1 = [(10, [('D', 4)]), (30, [('a', 4)])] + [(100 + 40 * i, [('a', 4)]) for i in range(18)]
    ev2 = [(110 + 40 * i, [('a', 4)]) for i in range(18)]
    lane = lambda ev: rle([x for x, n in timeline(ev, save_at + 10) for _ in range(n)])
    env = dict(os.environ, SEQ=lane(ev1), SEQ2=lane(ev2), OUT=f'{TMP}/boot.txt', INPUT_LAG='1',
               LOAD=emu.state_ref(game, 'game_select'), SAVE=f'{save_at}:{emu.state_ref(game, "vs_kyo")}')
    subprocess.run([emu.NGSDL, NEO[game], '--capture'], env=env, timeout=600, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

QCF = [('D', 3), ('DR', 3)]
def seq(*parts):
    """parts: (inputs, frames) -> recorder SEQ"""
    return ','.join(f'{n}:{i}' for i, n in parts)

def kai(first, second=None, gap=0):
    """75 Shiki Kai: qcf + first, then `second` pressed `gap` frames after the first button ('' = none)"""
    p = QCF + [('R' + first, 3)]
    if second: p += [('-', gap), (second, 3)]
    return p

APPROACH = [('R', 25), ('-', 10)]
SCENARIOS = {
    'kai_BB': APPROACH + kai('b', 'b', 14) + [('-', 80)],
    'kai_DD': APPROACH + kai('d', 'd', 30) + [('-', 80)],
    'kai_B': APPROACH + kai('b') + [('-', 80)],
}
def loop(n, second='d', gap=14, rest=0):
    p = list(APPROACH)
    for _ in range(n): p += kai('b', second, gap) + [('-', rest)]
    return p + [('-', 80)]

W = lambda o, off, n=2: int(o[off * 2:off * 2 + n * 2], 16)
S = lambda v, bits: v - (1 << bits) if v >> (bits - 1) else v

LIFE = {'kof95': 0x120, 'kof94': 0x120, 'kof98': 0x138}
VAR = {'kof95': (0xE3, 1), 'kof94': (0xE3, 1), 'kof98': (0x1A4, 0xF0)}   # the variant: KOF94/95 +$E3 bit 0, KOF98 +$1A4 (button)

def run(game, parts, start='vs_kyo', show=True, save=None, pokes=''):
    out = f'{TMP}/{game}_run{os.getpid()}.txt'
    env = dict(os.environ, SEQ=seq(*parts), SEQ2=f'{sum(n for _, n in parts)}:-', OUT=out, INPUT_LAG='1',
               LOAD=emu.state_ref(game, start))
    if pokes: env['POKE'] = pokes
    if save: env['SAVE'] = f'{save[0]}:{emu.state_ref(game, save[1])}'
    subprocess.run([emu.NGSDL, NEO[game], '--capture'], env=env, timeout=600, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows, hits, prev_life, prev = [], 0, None, None
    for line in open(out):
        q = line.split(); a, b = q[3], q[4]
        r = dict(f=int(q[0]), inp=q[1], st=W(a, 0x72), var=W(a, VAR[game][0], 1) & VAR[game][1], kind=W(a, 0x152), x=W(a, 0x18),
                 vx=S(W(a, 0x50, 4), 32) / 65536,
                 st2=W(b, 0x72), h2=S(W(b, 0x20), 16), x2=W(b, 0x18), life2=W(b, LIFE[game]))
        if prev_life is not None and r['life2'] < prev_life: hits += 1; r['hit'] = prev_life - r['life2']
        prev_life = r['life2']
        key = (r['st'], r['var'], r['kind'], r['st2'], r.get('hit'))
        if show and key != prev:
            print(f"{r['f']:5} in={r['inp']:3} P1 st={r['st']:3} var={r['var']} kind={r['kind']} x={r['x']} vx={r['vx']:+.2f}"
                  f"  P2 st={r['st2']:3} h={r['h2']:4} x={r['x2']} life={r['life2']}" + (f"  HIT -{r['hit']}" if 'hit' in r else ''))
        prev = key
        rows.append(r)
    return rows, hits

def timeline(events, n):
    """events [(frame, [(inputs, frames), ...])] -> parts for run()"""
    lane = ['-'] * n
    for f, s in events:
        for i, k in s:
            for _ in range(k): lane[f] = i; f += 1
    parts = []
    for x in lane:
        if parts and parts[-1][0] == x: parts[-1] = (x, parts[-1][1] + 1)
        else: parts.append((x, 1))
    return parts

QB = [('D', 2), ('DR', 2), ('Rb', 3)]           # 236B
QD = [('D', 2), ('DR', 2), ('Rd', 3)]           # 236D: the bogus command that rewrites the variant bit

MODES = {'BqD': (QB, QD), 'BB': (QB, [('b', 3)]), 'DD': (QD, [('d', 3)])}
LIFE_POKE = {'kof95': '108420=00,108421=CF', 'kof98': '108438=00,108439=67'}   # P2 life refilled every 30 frames

def loop_run(game, mode='BqD', d=21, per=67, n=12, start='vs_kyo_corner', refill=True, show=False):
    """the 75 Shiki Kai loop from the corner state: every `per` frames qcf + first button, `d` frames later the second
    input (BqD: the bogus 236D that rewrites the variant bit; BB / DD: the designed follow-ups). -> rows, hits"""
    first, second = MODES[mode]
    ev = []
    for k in range(n): ev += [(5 + k * per, first), (5 + k * per + d, second)]
    end = 5 + n * per + 60
    pk = ';'.join(f'{f}:{LIFE_POKE[game]}' for f in range(1, end, 30)) if refill else ''
    return run(game, timeline(ev, end), start=start, show=show, pokes=pk)

def juggle_hits(rows, special):
    """hits of the special landed one after another while the victim stayed airborne / juggled: the combo ends when
    the victim is back on its feet (state 0) or a hit lands on a grounded, not juggled victim"""
    out, prev = [], None
    for r in rows:
        if out and r['st2'] == 0: break
        if 'hit' in r:
            if r['st'] in special and (not out or prev[0] == 105 or prev[1] > 0): out.append(r)
            else: break
        prev = (r['st2'], r['h2'])
    return out

def _scan_one(a):
    game, mode, d, per, n, start = a
    rows, _ = loop_run(game, mode, d, per, n, start)
    return len(juggle_hits(rows, range(137, 141) if game != 'kof98' else range(141, 150))), d, per

def scan(game, mode, n=12, start='vs_kyo_corner'):
    """every timing of a loop (second input d frames after the first, period per) -> [(juggle hits, d, per)] best first"""
    from multiprocessing import Pool, set_start_method
    set_start_method('fork', force=True)
    dr, pr = (range(20, 46), range(60, 100)) if mode == 'DD' else (range(14, 30), range(58, 80))
    with Pool(10) as P: res = P.map(_scan_one, [(game, mode, d, p, n, start) for d in dr for p in pr])
    return sorted(res, reverse=True)

if __name__ == '__main__':
    cmd, game = sys.argv[1], sys.argv[2]
    if cmd == 'boot': boot(game)
    elif cmd == 'corner':          # Kyo walks Joe / Yuri into the right corner, both idle: state vs_kyo_corner
        run(game, [('R', 250), ('-', 20)], start=sys.argv[3] if sys.argv[3:] else 'vs_kyo', save=(268, 'vs_kyo_corner'))
    elif cmd == 'loop':            # python3 variant_glitch.py loop GAME MODE D PER N [norefill]
        mode, d, per, n = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
        rows, hits = loop_run(game, mode, d, per, n, refill='norefill' not in sys.argv)
        special = range(137, 141) if game == 'kof95' else range(141, 150)
        js = juggle_hits(rows, special)
        for r in js: print(f"{r['f']:5} P1 st {r['st']} var {r['var']} x {r['x']}  P2 st {r['st2']} h {r['h2']} x {r['x2']} -{r['hit']}")
        print('juggle hits', len(js), 'of', hits, 'hits')
    elif cmd == 'scan':            # python3 variant_glitch.py scan GAME MODE: the longest juggle over every timing
        print(scan(game, sys.argv[3])[:8])
    elif cmd == 'run':
        name = sys.argv[3]
        parts = SCENARIOS[name] if name in SCENARIOS else loop(int(name.split('_')[1]), *(name.split('_')[2:3] or ['d']))
        rows, hits = run(game, parts); print('hits', hits)

