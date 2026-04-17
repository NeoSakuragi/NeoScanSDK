#!/usr/bin/env python3
"""Encode indexed-color PNGs into Neo Geo C ROM tile data (C1/C2)."""
import sys
import os
import argparse
import numpy as np
from PIL import Image


def encode_crom_tile(pixels_16x16):
    """Encode a 16x16 tile (palette indices 0-15) to C1/C2 ROM bytes.

    Returns (c1_bytes, c2_bytes), 64 bytes each.
    C1 = bitplanes 0,2.  C2 = bitplanes 1,3.
    Right half (x=8..15) first, then left half (x=0..7).
    """
    c1 = bytearray(64)
    c2 = bytearray(64)
    for half_idx, x_start in enumerate([8, 0]):
        base_off = half_idx * 32
        for y in range(16):
            bp0 = bp1 = bp2 = bp3 = 0
            for x in range(8):
                ci = int(pixels_16x16[y, x_start + x]) & 0xF
                bp0 |= ((ci >> 0) & 1) << x
                bp1 |= ((ci >> 1) & 1) << x
                bp2 |= ((ci >> 2) & 1) << x
                bp3 |= ((ci >> 3) & 1) << x
            off = base_off + y * 2
            c1[off] = bp0
            c1[off + 1] = bp1
            c2[off] = bp2
            c2[off + 1] = bp3
    return bytes(c1), bytes(c2)


def load_indexed_png(path):
    """Load an indexed-color PNG. Returns (pixel_array, palette_list)."""
    img = Image.open(path)
    if img.mode != 'P':
        raise ValueError(f"{path}: expected indexed-color (mode P), got {img.mode}")
    pixels = np.array(img)
    palette_raw = img.getpalette()
    palette = []
    for i in range(min(16, len(palette_raw) // 3)):
        r, g, b = palette_raw[i*3], palette_raw[i*3+1], palette_raw[i*3+2]
        palette.append((r, g, b))
    while len(palette) < 16:
        palette.append((0, 0, 0))
    return pixels, palette


def slice_tiles(pixels):
    """Slice a pixel array into 16x16 tiles. Returns list of 16x16 arrays."""
    h, w = pixels.shape
    pad_w = ((w + 15) // 16) * 16
    pad_h = ((h + 15) // 16) * 16
    padded = np.zeros((pad_h, pad_w), dtype=np.uint8)
    padded[:h, :w] = pixels

    tiles = []
    for ty in range(pad_h // 16):
        for tx in range(pad_w // 16):
            tile = padded[ty*16:(ty+1)*16, tx*16:(tx+1)*16]
            tiles.append(tile)
    return tiles


def main():
    parser = argparse.ArgumentParser(description='Encode PNGs to Neo Geo C ROM tiles')
    parser.add_argument('pngs', nargs='+', help='Indexed-color PNG files')
    parser.add_argument('-o', '--output', required=True, help='Output directory')
    parser.add_argument('--header', default='tiles.h', help='Generated header filename')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    c1_data = bytearray(64)  # tile 0 = transparent (all zeros)
    c2_data = bytearray(64)
    tile_cache = {}
    next_tile_id = 1
    tile_defs = []

    for png_path in args.pngs:
        pixels, _ = load_indexed_png(png_path)
        tiles = slice_tiles(pixels)
        name = os.path.splitext(os.path.basename(png_path))[0].upper()

        for i, tile_pixels in enumerate(tiles):
            key = tile_pixels.tobytes()
            if key in tile_cache:
                tid = tile_cache[key]
            else:
                tid = next_tile_id
                tile_cache[key] = tid
                c1, c2 = encode_crom_tile(tile_pixels)
                c1_data.extend(c1)
                c2_data.extend(c2)
                next_tile_id += 1
            tile_defs.append((f"TILE_{name}_{i}", tid))

    c1_path = os.path.join(args.output, 'tiles_c1.bin')
    c2_path = os.path.join(args.output, 'tiles_c2.bin')
    with open(c1_path, 'wb') as f:
        f.write(c1_data)
    with open(c2_path, 'wb') as f:
        f.write(c2_data)

    header_path = os.path.join(args.output, args.header)
    with open(header_path, 'w') as f:
        f.write('#ifndef TILES_H\n#define TILES_H\n\n')
        f.write(f'#define TILE_COUNT {next_tile_id}\n\n')
        for name, tid in tile_defs:
            f.write(f'#define {name} {tid}\n')
        f.write('\n#endif\n')

    print(f"Encoded {next_tile_id - 1} unique tiles from {len(args.pngs)} PNG(s)")
    print(f"  C1: {c1_path} ({len(c1_data)} bytes)")
    print(f"  C2: {c2_path} ({len(c2_data)} bytes)")
    print(f"  Header: {header_path}")


if __name__ == '__main__':
    main()
