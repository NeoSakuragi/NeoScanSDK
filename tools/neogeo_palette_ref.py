#!/usr/bin/env python3
"""Generate Neo Geo color reference palette images and lookup tables.

Neo Geo 16-bit color format:
  Bit 15:    Dark bit (D)
  Bit 14:    Red LSB (R0)
  Bit 13:    Green LSB (G0)
  Bit 12:    Blue LSB (B0)
  Bits 11-8: Red[4:1]
  Bits 7-4:  Green[4:1]
  Bits 3-0:  Blue[4:1]

Each channel: 5-bit value (0-31)
Dark bit: when set, adds +1 to the 6-bit DAC level of ALL channels
  - D=0: DAC_level = val5 * 2     (even: 0, 2, 4, ..., 62)
  - D=1: DAC_level = val5 * 2 + 1 (odd:  1, 3, 5, ..., 63)

Total unique displayable colors: 32 * 32 * 32 * 2 = 65,536
(Compare: Genesis = 512, SNES = 32,768, Neo Geo = 65,536)
"""

import argparse
import os
import struct
import numpy as np
from PIL import Image


def neogeo_to_rgb888(r5, g5, b5, dark=0):
    """Convert Neo Geo 5-bit+dark channels to RGB888."""
    r6 = r5 * 2 + dark
    g6 = g5 * 2 + dark
    b6 = b5 * 2 + dark
    r8 = round(r6 * 255 / 63)
    g8 = round(g6 * 255 / 63)
    b8 = round(b6 * 255 / 63)
    return r8, g8, b8


def rgb888_to_neogeo(r8, g8, b8):
    """Find the closest Neo Geo color for an RGB888 value.
    Returns (r5, g5, b5, dark, neo_word)."""
    best_dist = float('inf')
    best = None
    r6_target = r8 * 63 / 255
    g6_target = g8 * 63 / 255
    b6_target = b8 * 63 / 255

    for dark in (0, 1):
        r5 = max(0, min(31, round((r6_target - dark) / 2)))
        g5 = max(0, min(31, round((g6_target - dark) / 2)))
        b5 = max(0, min(31, round((b6_target - dark) / 2)))
        r_out, g_out, b_out = neogeo_to_rgb888(r5, g5, b5, dark)
        dist = (r8 - r_out) ** 2 + (g8 - g_out) ** 2 + (b8 - b_out) ** 2
        if dist < best_dist:
            best_dist = dist
            word = encode_neogeo_word(r5, g5, b5, dark)
            best = (r5, g5, b5, dark, word)

    return best


def encode_neogeo_word(r5, g5, b5, dark=0):
    """Encode 5-bit RGB + dark to Neo Geo 16-bit word."""
    word = (((r5 & 1) << 14) | ((r5 >> 1) << 8) |
            ((g5 & 1) << 13) | ((g5 >> 1) << 4) |
            ((b5 & 1) << 12) | ((b5 >> 1) << 0))
    if dark:
        word |= 0x8000
    return word


def generate_swatch_image(output_path, cell_size=4):
    """Generate a reference swatch PNG showing all 65,536 Neo Geo colors.

    Layout: 2 panels (dark=0 top, dark=1 bottom)
    Each panel: 32 blue columns × (32×32 = 1024 rows of R×G)
    Organized as: for each blue level, a 32(R) × 32(G) block.
    """
    cols_per_panel = 32 * 32  # 32 blue levels × 32 red levels
    rows_per_panel = 32       # green levels

    w = cols_per_panel * cell_size
    h = rows_per_panel * 2 * cell_size  # 2 panels

    img = np.zeros((h, w, 3), dtype=np.uint8)

    for dark in (0, 1):
        y_offset = dark * rows_per_panel * cell_size
        for b5 in range(32):
            for r5 in range(32):
                col = (b5 * 32 + r5) * cell_size
                for g5 in range(32):
                    row = y_offset + g5 * cell_size
                    r8, g8, b8 = neogeo_to_rgb888(r5, g5, b5, dark)
                    img[row:row+cell_size, col:col+cell_size] = [r8, g8, b8]

    Image.fromarray(img).save(output_path)
    print(f"Swatch image saved: {output_path} ({w}x{h})")


def generate_gradient_strips(output_path, cell_w=8, cell_h=24):
    """Generate gradient strips showing the 64 effective levels per channel."""
    w = 64 * cell_w
    h = cell_h * 5  # R, G, B channels + dark=0 gray + dark=1 gray

    img = np.zeros((h, w, 3), dtype=np.uint8)

    labels = []

    for i in range(64):
        v5 = i // 2
        dark = i % 2
        x = i * cell_w

        # Red channel
        r8, _, _ = neogeo_to_rgb888(v5, 0, 0, dark)
        img[0:cell_h, x:x+cell_w] = [r8, 0, 0]

        # Green channel
        _, g8, _ = neogeo_to_rgb888(0, v5, 0, dark)
        img[cell_h:cell_h*2, x:x+cell_w] = [0, g8, 0]

        # Blue channel
        _, _, b8 = neogeo_to_rgb888(0, 0, v5, dark)
        img[cell_h*2:cell_h*3, x:x+cell_w] = [0, 0, b8]

        # Grayscale (dark=0 only)
        r8, g8, b8 = neogeo_to_rgb888(v5, v5, v5, 0)
        img[cell_h*3:cell_h*4, x:x+cell_w] = [r8, g8, b8]

        # Grayscale (with dark)
        r8, g8, b8 = neogeo_to_rgb888(v5, v5, v5, dark)
        img[cell_h*4:cell_h*5, x:x+cell_w] = [r8, g8, b8]

    Image.fromarray(img).save(output_path)
    print(f"Gradient strips saved: {output_path} ({w}x{h})")


def generate_gimp_palette(output_path):
    """Generate a GIMP .gpl palette file with all 65,536 Neo Geo colors."""
    with open(output_path, 'w') as f:
        f.write("GIMP Palette\n")
        f.write("Name: Neo Geo Full\n")
        f.write("Columns: 32\n")
        f.write("#\n")
        for dark in (0, 1):
            for b5 in range(32):
                for g5 in range(32):
                    for r5 in range(32):
                        r8, g8, b8 = neogeo_to_rgb888(r5, g5, b5, dark)
                        word = encode_neogeo_word(r5, g5, b5, dark)
                        d = "D" if dark else " "
                        f.write(f"{r8:3d} {g8:3d} {b8:3d}\tR{r5:02d}G{g5:02d}B{b5:02d}{d} 0x{word:04X}\n")
    print(f"GIMP palette saved: {output_path} (65,536 entries)")


def generate_act_palette(output_path):
    """Generate an Adobe .act palette file (256 colors max).
    Includes a perceptually-spaced subset of Neo Geo colors (6×7×6 cube = 252 colors)."""
    colors = []
    for r_idx in range(6):
        r5 = round(r_idx * 31 / 5)
        for g_idx in range(7):
            g5 = round(g_idx * 31 / 6)
            for b_idx in range(6):
                b5 = round(b_idx * 31 / 5)
                r8, g8, b8 = neogeo_to_rgb888(r5, g5, b5, 0)
                colors.append((r8, g8, b8))

    while len(colors) < 256:
        colors.append((0, 0, 0))

    with open(output_path, 'wb') as f:
        for r8, g8, b8 in colors:
            f.write(struct.pack('BBB', r8, g8, b8))
    print(f"ACT palette saved: {output_path} (252 representative colors)")


def generate_aseprite_palette(output_path):
    """Generate an Aseprite-compatible .gpl palette with a curated 256-color subset.
    Uses a 6×7×6 RGB cube from the Neo Geo color space (252 colors + 4 grays)."""
    colors = []

    for r_idx in range(6):
        r5 = round(r_idx * 31 / 5)
        for g_idx in range(7):
            g5 = round(g_idx * 31 / 6)
            for b_idx in range(6):
                b5 = round(b_idx * 31 / 5)
                r8, g8, b8 = neogeo_to_rgb888(r5, g5, b5, 0)
                word = encode_neogeo_word(r5, g5, b5, 0)
                colors.append((r8, g8, b8, word))

    extra_grays = [(5, 5, 5, 0), (10, 10, 10, 0), (21, 21, 21, 0), (26, 26, 26, 0)]
    for r5, g5, b5, dark in extra_grays:
        r8, g8, b8 = neogeo_to_rgb888(r5, g5, b5, dark)
        word = encode_neogeo_word(r5, g5, b5, dark)
        colors.append((r8, g8, b8, word))

    with open(output_path, 'w') as f:
        f.write("GIMP Palette\n")
        f.write("Name: Neo Geo 256\n")
        f.write("Columns: 16\n")
        f.write("#\n")
        for r8, g8, b8, word in colors:
            f.write(f"{r8:3d} {g8:3d} {b8:3d}\t0x{word:04X}\n")
    print(f"Aseprite palette saved: {output_path} ({len(colors)} colors)")


def print_color_info():
    """Print summary of Neo Geo color capabilities."""
    print("=" * 60)
    print("Neo Geo Color System Reference")
    print("=" * 60)
    print()
    print("Format:  16-bit scattered RGB5 + dark bit")
    print("Layout:  D R0 G0 B0 R4R3R2R1 G4G3G2G1 B4B3B2B1")
    print()
    print("Per channel: 5 bits = 32 levels (0-31)")
    print("Dark bit:    adds +1 to all channels' 6-bit DAC level")
    print("Effective:   64 intensity levels per channel (but LSBs tied)")
    print()
    print(f"Without dark bit:  32 x 32 x 32 = {32**3:,} colors")
    print(f"With dark bit:     32 x 32 x 32 = {32**3:,} colors")
    print(f"Total unique:      {32**3 * 2:,} colors")
    print()
    print("Comparison:")
    print(f"  Genesis/MD:   3-bit RGB = {8**3:>6,} colors")
    print(f"  SNES:         5-bit RGB = {32**3:>6,} colors")
    print(f"  Neo Geo:      5+D RGB   = {32**3*2:>6,} colors")
    print(f"  PC Engine:    3-bit RGB = {8**3:>6,} colors")
    print()
    print("Palette constraints:")
    print("  256 palettes x 16 colors each = 4,096 on-screen colors max")
    print("  Index 0 in each palette = transparent")
    print("  15 usable colors per palette")
    print()

    r8_min, g8_min, b8_min = neogeo_to_rgb888(0, 0, 0, 0)
    r8_max, g8_max, b8_max = neogeo_to_rgb888(31, 31, 31, 0)
    r8_d1, g8_d1, b8_d1 = neogeo_to_rgb888(0, 0, 0, 1)
    print(f"Black (no dark): RGB888 = ({r8_min}, {g8_min}, {b8_min})")
    print(f"White (no dark): RGB888 = ({r8_max}, {g8_max}, {b8_max})")
    print(f"Darkest w/dark:  RGB888 = ({r8_d1}, {g8_d1}, {b8_d1})")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Neo Geo color reference palette generator')
    parser.add_argument('--info', action='store_true',
                        help='Print color system info')
    parser.add_argument('--swatch', metavar='FILE',
                        help='Generate full 65K color swatch PNG')
    parser.add_argument('--gradient', metavar='FILE',
                        help='Generate channel gradient strips PNG')
    parser.add_argument('--gpl', metavar='FILE',
                        help='Generate GIMP/Aseprite .gpl palette (256 subset)')
    parser.add_argument('--gpl-full', metavar='FILE',
                        help='Generate GIMP .gpl with all 65,536 colors')
    parser.add_argument('--act', metavar='FILE',
                        help='Generate Adobe .act palette (256 subset)')
    parser.add_argument('--all', metavar='DIR',
                        help='Generate all reference files into directory')
    args = parser.parse_args()

    if not any([args.info, args.swatch, args.gradient, args.gpl,
                args.gpl_full, args.act, args.all]):
        args.info = True
        args.all = '.'

    if args.info:
        print_color_info()

    if args.all:
        os.makedirs(args.all, exist_ok=True)
        generate_swatch_image(os.path.join(args.all, 'neogeo_colors_full.png'))
        generate_gradient_strips(os.path.join(args.all, 'neogeo_gradients.png'))
        generate_aseprite_palette(os.path.join(args.all, 'neogeo_256.gpl'))
        generate_gimp_palette(os.path.join(args.all, 'neogeo_full.gpl'))
        generate_act_palette(os.path.join(args.all, 'neogeo_256.act'))
        return

    if args.swatch:
        generate_swatch_image(args.swatch)
    if args.gradient:
        generate_gradient_strips(args.gradient)
    if args.gpl:
        generate_aseprite_palette(args.gpl)
    if args.gpl_full:
        generate_gimp_palette(args.gpl_full)
    if args.act:
        generate_act_palette(args.act)


if __name__ == '__main__':
    main()
