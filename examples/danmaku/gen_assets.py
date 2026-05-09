#!/usr/bin/env python3
"""Generate danmaku sprite tiles: player, bullets, enemies, explosions."""
import math, os
from PIL import Image, ImageDraw

os.makedirs('res/gfx', exist_ok=True)

PAL = [
    (0, 0, 0),        # 0: transparent
    (255, 255, 255),   # 1: white
    (200, 220, 255),   # 2: light blue
    (100, 160, 255),   # 3: blue
    (40, 80, 200),     # 4: dark blue
    (255, 60, 60),     # 5: red
    (255, 160, 40),    # 6: orange
    (255, 255, 60),    # 7: yellow
    (60, 255, 60),     # 8: green
    (255, 80, 200),    # 9: pink
    (180, 60, 255),    # 10: purple
    (60, 255, 220),    # 11: cyan
    (140, 140, 140),   # 12: gray
    (80, 80, 80),      # 13: dark gray
    (40, 40, 40),      # 14: very dark
    (220, 200, 180),   # 15: warm white
]

flat_pal = []
for r, g, b in PAL:
    flat_pal.extend([r, g, b])
flat_pal.extend([0, 0, 0] * (256 - 16))


def make_img(w, h):
    img = Image.new('P', (w, h), 0)
    img.putpalette(flat_pal)
    return img


def draw_circle(px, cx, cy, r, color, fill=True):
    for y in range(-r, r + 1):
        for x in range(-r, r + 1):
            if fill:
                if x * x + y * y <= r * r:
                    if 0 <= cx + x < 16 and 0 <= cy + y < 16:
                        px[cx + x, cy + y] = color
            else:
                if abs(x * x + y * y - r * r) < r * 2:
                    if 0 <= cx + x < 16 and 0 <= cy + y < 16:
                        px[cx + x, cy + y] = color


# === SPRITES SHEET: 128x16 = 8 tiles ===
# Tile 0: Player ship (blue arrow pointing up)
# Tile 1: Small bullet (white dot)
# Tile 2: Medium bullet (red circle)
# Tile 3: Large bullet (purple orb)
# Tile 4: Enemy A (green diamond)
# Tile 5: Enemy B (orange hexagon)
# Tile 6: Explosion frame 1 (yellow burst)
# Tile 7: Explosion frame 2 (orange burst)

img = make_img(128, 16)
px = img.load()

# Tile 0: Player ship
ship = [
    "........",
    "....3...",
    "...333..",
    "...333..",
    "..23332.",
    "..23332.",
    ".2233322",
    ".2243422",
    "12243221",
    "12244221",
    ".2244421",
    ".2244421",
    "..2442..",
    "..2442..",
    "..1441..",
    "...44...",
]
for y, row in enumerate(ship):
    for x, ch in enumerate(row):
        if ch != '.':
            px[4 + x, y] = int(ch)

# Tile 1: Small bullet (4px white dot, centered)
for y in range(6, 10):
    for x in range(6, 10):
        d = abs(x - 7.5) + abs(y - 7.5)
        if d < 2.5:
            px[16 + x, y] = 1
        elif d < 3.5:
            px[16 + x, y] = 2

# Tile 2: Medium bullet (red circle, 6px)
draw_circle(px, 32 + 7, 7, 5, 5)
draw_circle(px, 32 + 7, 7, 4, 6)
draw_circle(px, 32 + 7, 7, 2, 7)
px[32 + 6, 5] = 1  # highlight

# Tile 3: Large bullet (purple orb, 7px)
draw_circle(px, 48 + 7, 7, 6, 10)
draw_circle(px, 48 + 7, 7, 5, 9)
draw_circle(px, 48 + 7, 7, 3, 1)
draw_circle(px, 48 + 7, 7, 1, 2)

# Tile 4: Enemy A (green diamond)
diamond = [
    "........",
    ".......8",
    "......88",
    ".....888",
    "....8888",
    "...88888",
    "..888188",
    ".8881188",
    "..888188",
    "...88888",
    "....8888",
    ".....888",
    "......88",
    ".......8",
    "........",
    "........",
]
for y, row in enumerate(diamond):
    for x, ch in enumerate(row):
        if ch != '.':
            px[64 + x, y] = int(ch)

# Tile 5: Enemy B (orange/red shape)
for y in range(2, 14):
    for x in range(2, 14):
        dx = abs(x - 7.5)
        dy = abs(y - 7.5)
        if dx + dy < 6:
            px[80 + x, y] = 6
        elif dx + dy < 7:
            px[80 + x, y] = 5
for y in range(5, 10):
    for x in range(5, 10):
        px[80 + x, y] = 7

# Tile 6: Explosion 1 (small yellow burst)
for a in range(0, 360, 30):
    for r in range(2, 6):
        xx = int(7.5 + r * math.cos(math.radians(a)))
        yy = int(7.5 + r * math.sin(math.radians(a)))
        if 0 <= xx < 16 and 0 <= yy < 16:
            px[96 + xx, yy] = 7 if r < 4 else 6

# Tile 7: Explosion 2 (bigger orange burst)
for a in range(0, 360, 20):
    for r in range(1, 7):
        xx = int(7.5 + r * math.cos(math.radians(a)))
        yy = int(7.5 + r * math.sin(math.radians(a)))
        if 0 <= xx < 16 and 0 <= yy < 16:
            px[112 + xx, yy] = 7 if r < 3 else 6 if r < 5 else 5

# Tile 8: Hitbox debug dot (2x2 red pixel centered)
# Tile 9: Blue orb bullet (16x16, uses all 15 indices in radial gradient)
# Tile 10: Pink orb bullet (16x16, will be shrunk to 8x8 by hardware)

img2 = make_img(176, 16)  # 11 tiles
px2 = img2.load()
for y in range(16):
    for x in range(128):
        px2[x, y] = px[x, y]

# Tile 8: hitbox dot
px2[128 + 7, 7] = 5
px2[128 + 8, 7] = 5
px2[128 + 7, 8] = 5
px2[128 + 8, 8] = 5

# Tile 9 (x=144): Blue orb — radial gradient using indices 1-15
# 1=brightest (white center), 15=darkest (deep navy edge)
cx9, cy9 = 144 + 7.5, 7.5
for y in range(16):
    for x in range(16):
        d = math.sqrt((x + 144 - cx9)**2 + (y - cy9)**2)
        if d > 7.5:
            px2[144 + x, y] = 0  # transparent
        else:
            # Map distance 0-7.5 to palette 1-15
            idx = int(d * 14.0 / 7.5) + 1
            if idx > 15: idx = 15
            px2[144 + x, y] = idx

# Tile 10 (x=160): Pink orb — same radial gradient
cx10, cy10 = 160 + 7.5, 7.5
for y in range(16):
    for x in range(16):
        d = math.sqrt((x + 160 - cx10)**2 + (y - cy10)**2)
        if d > 7.5:
            px2[160 + x, y] = 0
        else:
            idx = int(d * 14.0 / 7.5) + 1
            if idx > 15: idx = 15
            px2[160 + x, y] = idx

img2.save('res/gfx/sprites.png')
print("Generated res/gfx/sprites.png (176x16, 11 tiles)")

# === Generate dedicated palette PNGs ===
# These are 16x1 images — each pixel IS the palette color

# Blue orb palette: white center → cyan → royal blue → deep navy
blue_pal_rgb = [
    (0, 0, 0),          # 0: transparent
    (255, 255, 255),     # 1: white hot center
    (220, 240, 255),     # 2:
    (180, 220, 255),     # 3:
    (140, 200, 255),     # 4: bright cyan-blue
    (100, 170, 255),     # 5:
    (60, 140, 255),      # 6: vivid blue
    (40, 110, 240),      # 7:
    (30, 90, 220),       # 8: royal blue
    (20, 70, 200),       # 9:
    (15, 55, 175),       # 10:
    (10, 40, 150),       # 11: deep blue
    (8, 30, 120),        # 12:
    (5, 20, 90),         # 13:
    (3, 12, 60),         # 14: navy
    (1, 6, 35),          # 15: darkest edge
]

pink_pal_rgb = [
    (0, 0, 0),          # 0: transparent
    (255, 255, 255),     # 1: white hot center
    (255, 230, 245),     # 2:
    (255, 200, 240),     # 3:
    (255, 160, 230),     # 4: bright pink
    (255, 120, 220),     # 5:
    (255, 80, 200),      # 6: hot magenta
    (240, 50, 180),      # 7:
    (220, 30, 160),      # 8: fuchsia
    (200, 20, 140),      # 9:
    (175, 15, 120),      # 10:
    (150, 10, 100),      # 11: deep pink
    (120, 8, 80),        # 12:
    (90, 5, 60),         # 13:
    (60, 3, 40),         # 14:
    (35, 1, 25),         # 15: darkest edge
]

for name, pal_rgb in [('blue_orb', blue_pal_rgb), ('pink_orb', pink_pal_rgb)]:
    fp = []
    for r, g, b in pal_rgb:
        fp.extend([r, g, b])
    fp.extend([0, 0, 0] * (256 - 16))
    pal_img = Image.new('P', (16, 1), 0)
    pal_img.putpalette(fp)
    ppx = pal_img.load()
    for i in range(16):
        ppx[i, 0] = i
    pal_img.save(f'res/gfx/{name}_pal.png')
    print(f"Generated res/gfx/{name}_pal.png")
