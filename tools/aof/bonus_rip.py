#!/usr/bin/env python3
"""Art of Fighting 2's bonus objects for the brawler's bonus stages (TODO T7, Bruno 2026-10-14: "the wooden prop from
Art of Fighting 2 and the big tree also from Art of Fighting 2 key training"): VRAM + palette RAM dumps of AOF2's
Spirit Training (the tree) and Initiate Super Death Blow (the wooden posts, intact and breaking), taken in OUR emulator
(emu/neogeo_sdl --capture) from the bonus-select state of tools/aof/bonus_cap.py (/data/tmp/t7/aof2_sel.state).

    bonus_rip.py capture      -> /data/neogeo_dict/aof/rip/{spirit,posts}_<frame>.{vram,pal}, <name>_snaps/snap_<frame>.ppm
    bonus_rip.py sprites NAME FRAME   the frame's sprite chains (index, x, y, height, first tiles, palette) on stdout
    bonus_rip.py screens      -> /data/neogeo_dict/aof/rip/{intro_<frame>,select_*,card_*}.{vram,pal}: AOF2's own screens
                              around a bonus game (notes 20261014-085447-5d29 / -085507-5d29: "BONUS GAME", SELECT BONUS
                              GAME, the title card), from power-on (bonus_cap.py's keys: one credit, Ryo, the stage
                              counter $108428 held at 4 = the first bonus stage)

AOF2's order (measured in our emulator, frames of the `screens` run; sound commands from SNDLOG): the fight's end, then
  "BONUS GAME" (black; sprites 1-15 = 2 chains, palette $D4) from 2964: the text zooms in 2966-2980 (SCB2 $011F..$0FFF, a
  step a frame), $1C $AE (the announcer: "bonus game!") + song $33 at 2971; held to 3085 (122 frames);
  SELECT BONUS GAME from 3086 (song $4E, loops): grass sprites 1-20, the pictures 21-59 (slot 0 Spirit Training, 1
  Strength Training, 2 Initiate Super Death Blow), the cursor frame 60-64 (on every other frame: a 30 Hz flicker), the
  message box 65-81, the texts in the fix layer (title rows 4-5, TIME row 20, message rows 23-26): the general message
  until the stick moves or 180 frames pass, then the cursor's game's; TIME 9 counts down a step per 60 frames, stays at 0
  60 more frames, then the cursor's game; the stick: SSG $60; a pick: SSG $61 and the frame steady 60 frames; then
  the title card (white, the game's kanji + English name in the fix layer) with $20 (silence), $1C $CD / $CE (the
  announcer reads the kanji: Spirit Training / Super Death Blow) and $1A $20 (a gong): 186 frames, then the game.

tools/brawler/make_bonus.py reads the dumps (and aof2.neo's C ROM) and builds the brawler's bonus.h + tiles."""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
EMU = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
ROM = '/data/roms/aof2.neo'
STATE = '/data/tmp/t7/aof2_sel.state'
OUT = '/data/neogeo_dict/aof/rip'
HSK = ['R', 'L', 'DL', 'D', 'DR', 'Ra']             # the Super Haoh Shoko-ken: forward, back, down-back, down, down-forward, forward + A
GAMES = {                                             # name: (choice on the select screen, frames dumped, P1's inputs after the choice)
    'spirit': (0, list(range(200, 1000, 50)), '600:-,4:a,3000:-'),   # (a failed run: grade 0, the tree stands)
    # the top grade (note 20261014-133606-5d29): A at 541 = power >= 120 (grade 5, BONUS 10000, song $2D): the punch mark
    # at 700 / 714, the cracked tree (sprites 225-237) from 730, its top falling (225-239) from 760, the fallen crown
    # (225-243) squashed at 790 / 796 and swaying from 798 (make_bonus.py 'fall'); A at 537 = grade 4: the tree stands
    'spirit_top': (0, list(range(690, 1000, 2)), '537:-,4:a,3000:-'),
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


BOOT = '1500:-,6:o,54:-,6:o,34:-,6:s,194:-,6:a,94:-,6:a,94:-,6:a,'   # to frame 2006 (bonus_cap.py state's keys)
SCREENS = {                                  # run: R pressed that many times (3200, 3240), A at 3360; dump name: frame
    0: dict({f'intro_{f}': f for f in range(2964, 2984)}, select_gen=3100, select_0=3300, card_0=3800),   # (no A: the clock)
    2: dict(select_1=3220, select_2=3300, card_2=3500),
}


def screens():
    for c, dumps in SCREENS.items():
        seq = BOOT + '1194:-,' + ('4:R,36:-,' * c + f'{160 - 40 * c}:-,4:a,1000:-' if c else '1500:-')
        poke = ';'.join(f'{f}:108428=00,108429=04' for f in range(1721, 4100))
        env = dict(os.environ, SEQ=seq, POKE=poke, VRAMDUMP=';'.join(f'{f}:{OUT}/{n}.vram' for n, f in dumps.items()),
                   PALDUMP=';'.join(f'{f}:{OUT}/{n}.pal' for n, f in dumps.items()))
        subprocess.run(['timeout', '900', EMU, ROM, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print('screens', c, sum(os.path.exists(f'{OUT}/{n}.vram') for n in dumps), '/', len(dumps), 'dumps')


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
    elif a and a[0] == 'screens': screens()
    elif len(a) == 3 and a[0] == 'sprites':
        for s in sprites(open(f'{OUT}/{a[1]}_{a[2]}.vram', 'rb').read()):
            nz = [t for t, _ in s['tiles'] if t]
            print(s['i'], s['x'], s['y'], s['h'], 'S' if s['sticky'] else ' ', len(nz), hex(nz[0]) if nz else '-', (s['tiles'][0][1] >> 8) if s['tiles'] else '')
    else: sys.exit(__doc__)
