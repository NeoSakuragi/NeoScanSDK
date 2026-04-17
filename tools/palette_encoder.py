#!/usr/bin/env python3
"""Extract palette from indexed-color PNG and encode to Neo Geo format."""
import sys
import os
import argparse
from PIL import Image


def rgb_to_neogeo(r, g, b):
    """Convert RGB888 to Neo Geo 16-bit color word."""
    r5 = r >> 3
    g5 = g >> 3
    b5 = b >> 3
    return (((r5 & 1) << 14) | ((r5 >> 1) << 8) |
            ((g5 & 1) << 13) | ((g5 >> 1) << 4) |
            ((b5 & 1) << 12) | ((b5 >> 1) << 0))


def main():
    parser = argparse.ArgumentParser(description='Extract palette from indexed PNG')
    parser.add_argument('png', help='Indexed-color PNG file')
    parser.add_argument('-o', '--output', required=True, help='Output .h file')
    parser.add_argument('--name', default='PALETTE', help='Array name in header')
    args = parser.parse_args()

    img = Image.open(args.png)
    if img.mode != 'P':
        raise ValueError(f"{args.png}: expected indexed-color (mode P), got {img.mode}")

    palette_raw = img.getpalette()
    colors = []
    colors.append(0x0000)  # index 0 = transparent
    for i in range(1, 16):
        if i * 3 + 2 < len(palette_raw):
            r, g, b = palette_raw[i*3], palette_raw[i*3+1], palette_raw[i*3+2]
            colors.append(rgb_to_neogeo(r, g, b))
        else:
            colors.append(0x0000)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        f.write(f'#ifndef {args.name}_H\n#define {args.name}_H\n\n')
        f.write('#include <stdint.h>\n\n')
        f.write(f'static const uint16_t {args.name}[16] = {{\n')
        for i, c in enumerate(colors):
            comma = ',' if i < 15 else ''
            f.write(f'    0x{c:04X}{comma}\n')
        f.write('};\n\n')
        f.write('#endif\n')

    print(f"Palette extracted: {args.output}")


if __name__ == '__main__':
    main()
