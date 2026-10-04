#!/usr/bin/env python3
"""Boot a KOF game into a 2-player versus fight in our emulator and save state 'vs' (replaces the MAME boot.lua's):
coins (frames 600 / 650), both starts (720 / 760), then A on both sides every 20 frames (from 801: team, order, fight).
With the recorder's INPUT_LAG=1 this is the MAME boot frame for frame: KOF96 and KOF98 reach Kyo vs Yuri at the same
frame as in MAME (checked on P1's object counter +$1D2), and the MAME 'vs' states were the fight at frame 1590 (KOF96) /
1593 (KOF98), mid-press of an A (both fighters in state 81).

    python3 boot_ngsdl.py GAME                 -> prints when the fighters (P1 / P2 id, state) change, up to frame 2000
    python3 boot_ngsdl.py GAME --save FRAME    -> /data/neogeo_dict/ngsdl_sta/GAME/vs.state at that frame"""
import os, sys, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import emu

SAVE_AT = {'kof96': 1590, 'kof98': 1593}

def rle(lane):
    runs = []
    for x in lane:
        if runs and runs[-1][1] == x: runs[-1][0] += 1
        else: runs.append([1, x])
    return ','.join(f'{n}:{x}' for n, x in runs)

def boot(game, frames, save=None):
    p1, p2 = ['-'] * frames, ['-'] * frames
    for f in range(600, 606): p1[f] = 'o'
    for f in range(650, 656): p2[f] = 'o'
    for f in range(720, 726): p1[f] = 's'
    for f in range(760, 766): p2[f] = 's'
    for f in range(801, frames):
        if f % 20 < 3: p1[f] = p2[f] = 'a'
    out = tempfile.mktemp(suffix='.txt', dir='/data/tmp')
    env = dict(os.environ, SEQ=rle(p1), SEQ2=rle(p2), OUT=out, INPUT_LAG='1')
    if save: env['SAVE'] = f'{save}:{emu.state_ref(game, "vs")}'
    subprocess.run([emu.NGSDL, emu.GAMES[game]['neo'], '--capture'], env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=600)
    W = lambda o, off: int(o[off * 2:off * 2 + 4], 16)
    prev = None
    for line in open(out):
        q = line.split()
        cur = tuple((W(o, 0x70), W(o, 0x72)) for o in (q[3], q[4]))
        if cur != prev: print(int(q[0]), 'P1 id/state', cur[0], 'P2', cur[1]); prev = cur
    os.unlink(out)

if __name__ == '__main__':
    game = sys.argv[1]
    if sys.argv[2:3] == ['--save']: f = int(sys.argv[3]); boot(game, f + 2, f)
    else: boot(game, 2000)
