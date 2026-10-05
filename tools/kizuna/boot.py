#!/usr/bin/env python3
"""Boot Kizuna Encounter into a 2P fight in our emulator (neogeo_sdl --capture), optionally save a state.
    python3 boot.py FRAMES [--save FRAME] [--snaps f,f,...]"""
import os, sys, subprocess
NGSDL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/kizuna.neo'
STA = '/data/neogeo_dict/kizuna/cap'

def rle(lane):
    runs = []
    for x in lane:
        if runs and runs[-1][1] == x: runs[-1][0] += 1
        else: runs.append([1, x])
    return ','.join(f'{n}:{x}' for n, x in runs)

def boot(frames, save=None, snaps=None, extra=None, p1=None, p2=None, name='vs'):
    if p1 is None:
        p1, p2 = ['-'] * frames, ['-'] * frames
        for f in range(600, 606): p1[f] = 'o'
        for f in range(650, 656): p2[f] = 'o'
        for f in range(720, 726): p1[f] = 's'
        for f in range(760, 766): p2[f] = 's'
        for f in range(801, frames):
            if f % 20 < 3: p1[f] = p2[f] = 'a'
    env = dict(os.environ, SEQ=rle(p1), SEQ2=rle(p2), OUT='/data/tmp/kizuna/boot.txt', **(extra or {}))
    if save: env['SAVE'] = f'{save}:{STA}/{name}.state'
    if snaps: env.update(SNAPS=snaps, SNAPDIR='/data/tmp/kizuna')
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)

if __name__ == '__main__':
    a = sys.argv[1:]; n = int(a[0])
    boot(n, int(a[a.index('--save') + 1]) if '--save' in a else None, a[a.index('--snaps') + 1] if '--snaps' in a else None)
