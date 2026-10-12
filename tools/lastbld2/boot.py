#!/usr/bin/env python3
"""The Last Blade 2 into a fight in our emulator: coins 600 / 650, starts 720 / 760, P1's cursor one square right at
905 (Kaede -> Moriya; P2's cursor starts on Moriya), A on both sides every 20 frames outside 815-960 (the select
screen's cursor window) and before 1300 (both idle at 1700), the style screen's first choice (Power) taken by those A presses. Frame 1700 = round 1, both
idle. Two states, one per core build (a state does not load in the other):
  vs_sdl.state  emu/neogeo_sdl --capture (the captures: RAM / VRAM / palette / sound per frame)
  vs.state      the repo's Geolith build driven from Python (core_lb2.LB2: the write tap, frame stepping)
    python3 boot.py [--style power|speed|ex]"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util
_spec = importlib.util.spec_from_file_location('boot_ss2', os.path.join(HERE, '..', 'samsho2', 'boot.py'))
B2 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(B2)      # its lanes() / rle()
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/lastbld2.neo'
STA = '/data/neogeo_dict/lastbld2/cap'
N = 1700

def lanes(style=0, p1_col=1):
    p1, p2 = B2.lanes(N)
    for f in list(range(815, 960)) + list(range(1300, N)): p1[f] = p2[f] = '-'
    for c in range(p1_col):
        for k in range(905 + 16 * c, 913 + 16 * c): p1[k] = 'R'
    if style:                                   # the style screen (Power / Speed / EX): the stick moves down
        for f in range(960, 1100): p1[f] = '-' if p1[f] == 'a' else p1[f]
        f = 1000
        for _ in range(style):
            for k in range(f, f + 8): p1[k] = 'D'
            f += 16
        for k in range(f + 8, f + 12): p1[k] = 'a'
    return p1, p2

def make(style=0, name='vs'):
    p1, p2 = lanes(style)
    os.makedirs(STA, exist_ok=True)
    env = dict(os.environ, SEQ=B2.rle(p1), SEQ2=B2.rle(p2), OUT='/data/tmp/lastbld2/boot.txt',
               SAVE=f'{N}:{STA}/{name}_sdl.state', SNAPS=str(N), SNAPDIR='/data/tmp/lastbld2')
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    sys.path.insert(0, HERE)
    from core_lb2 import LB2
    g = LB2()
    for f in range(N):
        g.pad = [set(p1[f].replace('-', '')), set(p2[f].replace('-', ''))]
        g.core.retro_run(); g.frame += 1
    open(f'{STA}/{name}.state', 'wb').write(g.save())
    g.screenshot(f'/data/tmp/lastbld2/{name}.png')

if __name__ == '__main__':
    a = sys.argv[1:]
    st = a[a.index('--style') + 1] if '--style' in a else 'power'
    k = ['power', 'speed', 'ex'].index(st)
    make(k, 'vs' if k == 0 else 'vs_' + st)
