#!/usr/bin/env python3
"""The Brawler (tester) app's launcher icon: the NEO·GEO wordmark of the MVS BIOS eye-catch, stacked NEO / GEO, white
on black. Source = our emulator's snap of the boot (any .neo, frame 480: the white wordmark on black):

    ./emu/neogeo_sdl /data/roms/aof.neo --snap 480 --quit 500      # -> /tmp/neoscan_f480.ppm
    python3 tools/brawler/make_tester_icon.py /tmp/neoscan_f480.ppm android/app/src/brawler/res

Writes the adaptive foreground (108 dp canvas, the mark 50 dp wide: its corners inside the 66 dp safe circle) and the legacy square + round icons,
mdpi..xxxhdpi. The adaptive XML + background colour are checked in next to them."""
import os
import sys
from PIL import Image, ImageDraw

src = Image.open(sys.argv[1]).convert('L')
res = sys.argv[2]
neo = src.crop((40, 52, 151, 92))            # the wordmark: y 52..91, NEO x 40..150, the dot 152..158, GEO 160..266
geo = src.crop((160, 52, 267, 92))
WHITE = (255, 255, 255, 255)


def mark(size, frac):
    """the stacked wordmark as an alpha mask, centred, NEO's width = frac of size"""
    w = int(size * frac); s = w / neo.width
    a = neo.resize((w, round(neo.height * s)), Image.LANCZOS)
    b = geo.resize((round(geo.width * s), round(geo.height * s)), Image.LANCZOS)
    gap = round(a.height * 0.28); th = a.height + gap + b.height
    m = Image.new('L', (size, size), 0); y = (size - th) // 2
    m.paste(a, ((size - a.width) // 2, y)); m.paste(b, ((size - b.width) // 2, y + a.height + gap))
    return m


def on(base, m):
    base.paste(Image.new('RGBA', base.size, WHITE), (0, 0), m)
    return base


for d, k in (('mdpi', 1), ('hdpi', 1.5), ('xhdpi', 2), ('xxhdpi', 3), ('xxxhdpi', 4)):
    p = f'{res}/mipmap-{d}'; os.makedirs(p, exist_ok=True)
    n = round(108 * k)
    on(Image.new('RGBA', (n, n), (0, 0, 0, 0)), mark(n, 50 / 108)).save(f'{p}/ic_launcher_foreground.png')
    L = round(48 * k)
    sq = Image.new('RGBA', (L, L), (0, 0, 0, 0))
    ImageDraw.Draw(sq).rounded_rectangle((0, 0, L - 1, L - 1), radius=L // 6, fill=(0, 0, 0, 255))
    on(sq, mark(L, 0.70)).save(f'{p}/ic_launcher.png')
    rd = Image.new('RGBA', (L, L), (0, 0, 0, 0))
    ImageDraw.Draw(rd).ellipse((0, 0, L - 1, L - 1), fill=(0, 0, 0, 255))
    on(rd, mark(L, 0.62)).save(f'{p}/ic_launcher_round.png')
