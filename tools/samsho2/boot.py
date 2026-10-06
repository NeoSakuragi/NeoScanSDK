#!/usr/bin/env python3
"""Boot Samurai Shodown II into a 2P fight in our emulator (neogeo_sdl --capture) and optionally save a state.
coins 600/650, starts 720/760, then A on both sides every 20 frames from 801 (the SS4 / KOF boot timeline).
    python3 boot.py FRAMES [--save FRAME] [--snaps f,f,...] [--p2 SEQ-prefix]"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/samsho2.neo'
STA = '/data/neogeo_dict/samsho2/cap'

def rle(lane):
    runs = []
    for x in lane:
        if runs and runs[-1][1] == x: runs[-1][0] += 1
        else: runs.append([1, x])
    return ','.join(f'{n}:{x}' for n, x in runs)

def lanes(frames, p1_moves=(), p2_moves=(), a_from=801):
    """input lanes; p1_moves / p2_moves = [(frame, input)] cursor moves on the select screen before the A presses"""
    p1, p2 = ['-'] * frames, ['-'] * frames
    for f in range(600, 606): p1[f] = 'o'
    for f in range(650, 656): p2[f] = 'o'
    for f in range(720, 726): p1[f] = 's'
    for f in range(760, 766): p2[f] = 's'
    for lane, mv in ((p1, p1_moves), (p2, p2_moves)):
        for f, x in mv:
            for k in range(f, f + 3): lane[k] = x
    for f in range(a_from, frames):
        if f % 20 < 3: p1[f] = p2[f] = 'a'
    return p1, p2

def boot(frames, save=None, snaps=None, p1_moves=(), p2_moves=(), a_from=801, out='/data/tmp/samsho2/boot.txt', state=None, extra=None):
    p1, p2 = lanes(frames, p1_moves, p2_moves, a_from)
    env = dict(os.environ, SEQ=rle(p1), SEQ2=rle(p2), OUT=out, **(extra or {}))
    if save: env['SAVE'] = f'{save}:{state or STA + "/vs.state"}'
    if snaps: env.update(SNAPS=snaps, SNAPDIR=os.path.dirname(out))
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)

if __name__ == '__main__':
    a = sys.argv[1:]; n = int(a[0])
    boot(n, int(a[a.index('--save') + 1]) if '--save' in a else None, a[a.index('--snaps') + 1] if '--snaps' in a else None)
