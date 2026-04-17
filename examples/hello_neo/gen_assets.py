#!/usr/bin/env python3
"""Generate test sprite PNGs for hello_neo demo."""
from PIL import Image
import os

os.makedirs('assets', exist_ok=True)

palette_rgb = [
    (0, 0, 0),        # 0: transparent
    (255, 255, 255),   # 1: white
    (220, 50, 50),     # 2: red
    (50, 50, 220),     # 3: blue
    (50, 200, 50),     # 4: green
    (255, 200, 0),     # 5: yellow
    (180, 80, 220),    # 6: purple
    (255, 140, 0),     # 7: orange
    (0, 200, 200),     # 8: cyan
    (160, 160, 160),   # 9: gray
    (80, 80, 80),      # 10: dark gray
    (255, 180, 180),   # 11: pink
    (0, 100, 0),       # 12: dark green
    (100, 60, 20),     # 13: brown
    (0, 0, 120),       # 14: dark blue
    (200, 200, 200),   # 15: light gray
]

flat_pal = []
for r, g, b in palette_rgb:
    flat_pal.extend([r, g, b])
# Pad to 256 entries
flat_pal.extend([0, 0, 0] * (256 - 16))

# --- Sprite sheet: 64x16 = four 16x16 tiles side by side ---
# Tile 0: "N" letter (white on transparent)
# Tile 1: Heart (red)
# Tile 2: Arrow up (green)
# Tile 3: Star (yellow)

img = Image.new('P', (64, 16), 0)
img.putpalette(flat_pal)
px = img.load()

# Tile 0 (x=0..15): "N" letter
n_pattern = [
    "..1...........1.",
    "..11..........1.",
    "..111.........1.",
    "..1.11........1.",
    "..1..11.......1.",
    "..1...11......1.",
    "..1....11.....1.",
    "..1.....11....1.",
    "..1......11...1.",
    "..1.......11..1.",
    "..1........11.1.",
    "..1.........111.",
    "..1..........11.",
    "..1...........1.",
    "................",
    "................",
]
for y, row in enumerate(n_pattern):
    for x, ch in enumerate(row):
        if ch != '.':
            px[x, y] = int(ch)

# Tile 1 (x=16..31): Heart
heart = [
    "................",
    "..222....222....",
    ".22222..22222...",
    ".2222222222222..",
    ".2222222222222..",
    ".2222222222222..",
    "..22222222222...",
    "...222222222....",
    "....2222222.....",
    ".....22222......",
    "......222.......",
    ".......2........",
    "................",
    "................",
    "................",
    "................",
]
for y, row in enumerate(heart):
    for x, ch in enumerate(row):
        if ch != '.':
            px[16 + x, y] = int(ch)

# Tile 2 (x=32..47): Arrow up
arrow = [
    ".......4........",
    "......444.......",
    ".....44444......",
    "....4444444.....",
    "...444444444....",
    "..44444444444...",
    ".4444444444444..",
    "......444.......",
    "......444.......",
    "......444.......",
    "......444.......",
    "......444.......",
    "......444.......",
    "......444.......",
    "................",
    "................",
]
for y, row in enumerate(arrow):
    for x, ch in enumerate(row):
        if ch != '.':
            px[32 + x, y] = int(ch)

# Tile 3 (x=48..63): Star
star = [
    "................",
    ".......5........",
    "......555.......",
    "......555.......",
    ".5555555555555..",
    "..55555555555...",
    "...555555555....",
    "....5555555.....",
    "...555...555....",
    "..555.....555...",
    ".555.......555..",
    "................",
    "................",
    "................",
    "................",
    "................",
]
for y, row in enumerate(star):
    for x, ch in enumerate(row):
        if ch != '.':
            px[48 + x, y] = int(ch)

img.save('assets/sprites.png')
print("Generated assets/sprites.png (64x16, 4 tiles)")
