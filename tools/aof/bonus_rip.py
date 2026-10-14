#!/usr/bin/env python3
"""Art of Fighting 2's bonus objects for the brawler's bonus stages (TODO T7, Bruno 2026-10-14: "the wooden prop from
Art of Fighting 2 and the big tree also from Art of Fighting 2 key training"): VRAM + palette RAM dumps of AOF2's
Spirit Training (the tree) and Initiate Super Death Blow (the wooden posts, intact and breaking), taken in OUR emulator
(emu/neogeo_sdl --capture) from the bonus-select state of tools/aof/bonus_cap.py (/data/tmp/t7/aof2_sel.state).

    bonus_rip.py capture      -> /data/neogeo_dict/aof/rip/{spirit,posts}_<frame>.{vram,pal}, <name>_snaps/snap_<frame>.ppm
    bonus_rip.py sprites NAME FRAME   the frame's sprite chains (index, x, y, height, first tiles, palette) on stdout

tools/brawler/make_bonus.py reads the dumps (and aof2.neo's C ROM) and builds the brawler's bonus.h + tiles."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
EMU = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
ROM = '/data/roms/aof2.neo'
STATE = '/data/tmp/t7/aof2_sel.state'
OUT = '/data/neogeo_dict/aof/rip'
HSK = ['R', 'L', 'DL', 'D', 'DR', 'Ra']             # the Super Haoh Shoko-ken: forward, back, down-back, down, down-forward, forward + A
GAMES = {                                             # name: (choice on the select screen, frames dumped, P1's inputs after the choice)
    'spirit': (0, list(range(200, 1000, 50)), '600:-,4:a,3000:-'),
    'posts': (2, list(range(150, 1500, 6)), '300:-,' + ','.join(f'4:{k}' for k in HSK) + ',40:-,' + (','.join(f'4:{k}' for k in HSK) + ',60:-,') * 14 + '3000:-'),
}


def capture():
    for name, (choice, frames, keys) in GAMES.items():
        os.makedirs(f'{OUT}/{name}_snaps', exist_ok=True)
        seq = '4:R,8:-,' * choice + '4:a,' + keys
        dump = ';'.join(f'{f}:{OUT}/{name}_{f}.vram' for f in frames)
        pal = ';'.join(f'{f}:{OUT}/{name}_{f}.pal' for f in frames)
        poke = ';'.join(f'{f}:1092ED=10' for f in range(0, max(frames) + 1)) if name == 'posts' else ''   # P1's life low:
        env = dict(os.environ, LOAD=STATE, SEQ=seq, VRAMDUMP=dump, PALDUMP=pal, POKE=poke,   # AOF2's desperation rule
                   SNAPS=','.join(map(str, frames)), SNAPDIR=f'{OUT}/{name}_snaps')
        subprocess.run(['timeout', '900', EMU, ROM, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(name, len([f for f in os.listdir(OUT) if f.startswith(name + '_') and f.endswith('.vram')]), 'dumps')


def sprites(v):
    """the VRAM words -> [{i, x, y, h, sticky, tiles: [(tile, attr)]}] for every sprite with a height (SCB3)"""
    w = lambda a: v[a * 2] << 8 | v[a * 2 + 1]
    out = []; x = y = h = 0
    for i in range(1, 381):
        s3 = w(0x8200 + i); s4 = w(0x8400 + i)
        if s3 & 0x40: x = (x + 16) & 0x1FF                 # sticky: the chain's next column
        else: h = s3 & 0x3F; y = 496 - (s3 >> 7); x = s4 >> 7
        if not h: continue
        tiles = []
        for r in range(min(h, 32)):
            lo = w(i * 64 + r * 2); at = w(i * 64 + r * 2 + 1)
            tiles.append((lo | ((at >> 4) & 0xF) << 16, at))
        out.append({'i': i, 'x': x if x < 448 else x - 512, 'y': y if y < 256 else y - 512, 'h': h, 'sticky': bool(s3 & 0x40), 'tiles': tiles})
    return out


if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == 'capture': capture()
    elif len(a) == 3 and a[0] == 'sprites':
        for s in sprites(open(f'{OUT}/{a[1]}_{a[2]}.vram', 'rb').read()):
            nz = [t for t, _ in s['tiles'] if t]
            print(s['i'], s['x'], s['y'], s['h'], 'S' if s['sticky'] else ' ', len(nz), hex(nz[0]) if nz else '-', (s['tiles'][0][1] >> 8) if s['tiles'] else '')
    else: sys.exit(__doc__)
