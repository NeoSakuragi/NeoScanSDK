#!/usr/bin/env python3
"""Encode 8-way player sprites from PNG sequences for NeoScan SDK.

Input directory structure:
    root/
        player_idle/
            down/0000.png, 0001.png, ...
            downright/...
            right/...
            upright/...
            up/...
        player_run/
            down/...
            ...

Output: C1/C2 ROM binaries + C header with anim_def_t[num_anims][NUM_ANGLES] lookup.
The 3 mirrored directions (left, upleft, downleft) are handled by H-flip at runtime.

Usage:
    python3 player8_encoder.py /data/SFExport \
        --name alex \
        --anims idle=alex_idle,run=alex_runbefore,pass=alex_pass,shoot=alex_shoot,wobble=alex_wobble \
        --tile-base 1 --duration 3 -o build/_player8_alex
"""

import argparse
import os
import sys
import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from anim_encoder import rgb_to_neogeo_word, encode_crom_tile

ANGLES = ['down', 'downright', 'right', 'upright', 'up']


def load_png_sequence(folder):
    """Load all numbered PNG files from a folder as RGBA numpy arrays."""
    files = sorted(f for f in os.listdir(folder) if f.endswith('.png'))
    if not files:
        raise ValueError(f"No PNG files in {folder}")
    frames = []
    for f in files:
        img = Image.open(os.path.join(folder, f)).convert('RGBA')
        frames.append(np.array(img))
    return frames


def quantize_palette(all_frames, num_colors=15):
    """Build a palette by quantizing all visible pixels using PIL.

    Returns (palette_rgb, lut) where lut maps (r,g,b) → 1-based palette index.
    """
    pixel_rows = []
    for key, frames in all_frames.items():
        for img in frames:
            mask = img[:, :, 3] > 0
            pixels = img[mask][:, :3]
            if len(pixels) > 0:
                pixel_rows.append(pixels)

    all_pixels = np.concatenate(pixel_rows)

    stride = max(1, len(all_pixels) // 200000)
    sampled = all_pixels[::stride]
    h = len(sampled)
    strip = Image.fromarray(sampled.reshape(h, 1, 3), 'RGB')
    quantized = strip.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT)
    pal_data = quantized.getpalette()
    palette_rgb = []
    for i in range(num_colors):
        palette_rgb.append((pal_data[i*3], pal_data[i*3+1], pal_data[i*3+2]))

    print(f"  Quantized palette ({num_colors} colors):")
    for i, (r, g, b) in enumerate(palette_rgb):
        print(f"    [{i+1:2d}] #{r:02X}{g:02X}{b:02X}")

    pal_arr = np.array(palette_rgb, dtype=np.int32)

    lut = {}
    unique_colors = set()
    for key, frames in all_frames.items():
        for img in frames:
            mask = img[:, :, 3] > 0
            pixels = img[mask][:, :3]
            for px in pixels:
                unique_colors.add((int(px[0]), int(px[1]), int(px[2])))

    for rgb in unique_colors:
        arr = np.array(rgb, dtype=np.int32)
        dists = np.sum((pal_arr - arr) ** 2, axis=1)
        best = int(np.argmin(dists))
        lut[rgb] = best + 1

    return palette_rgb, lut


def compute_union_bbox(all_frames):
    """Compute union bounding box across ALL frames, ALL angles, ALL anims."""
    min_r, min_c = 99999, 99999
    max_r, max_c = 0, 0
    for key, frames in all_frames.items():
        for img in frames:
            alpha = img[:, :, 3]
            rows = np.any(alpha > 0, axis=1)
            cols = np.any(alpha > 0, axis=0)
            if not rows.any():
                continue
            r0, r1 = np.where(rows)[0][[0, -1]]
            c0, c1 = np.where(cols)[0][[0, -1]]
            min_r = min(min_r, r0)
            max_r = max(max_r, r1)
            min_c = min(min_c, c0)
            max_c = max(max_c, c1)
    return min_r, min_c, max_r, max_c


def compute_anchor(all_frames, grid_r0, grid_c0):
    """Compute anchor point (feet center) from all frames."""
    center_xs = []
    bottom_ys = []
    for key, frames in all_frames.items():
        for img in frames:
            alpha = img[:, :, 3]
            rows_mask = np.any(alpha > 0, axis=1)
            cols_mask = np.any(alpha > 0, axis=0)
            if rows_mask.any():
                bottom_ys.append(np.where(rows_mask)[0][-1])
                cx0, cx1 = np.where(cols_mask)[0][[0, -1]]
                center_xs.append((cx0 + cx1) // 2)
    feet_x = int(np.median(center_xs)) if center_xs else 48
    feet_y = max(bottom_ys) if bottom_ys else 128
    return feet_x - grid_c0, feet_y - grid_r0


def main():
    parser = argparse.ArgumentParser(
        description='Encode 8-way player sprites from PNG sequences')
    parser.add_argument('root', help='Root directory with animation folders')
    parser.add_argument('--name', required=True, help='Player name (e.g. alex)')
    parser.add_argument('--anims', required=True,
                        help='Comma-separated anim=folder mappings')
    parser.add_argument('-o', '--output', required=True, help='Output directory')
    parser.add_argument('--tile-base', type=int, default=1,
                        help='Starting tile ID (default: 1)')
    parser.add_argument('--duration', type=int, default=3,
                        help='VBlanks per frame (default: 3)')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    name = args.name
    name_upper = name.upper()
    name_lower = name.lower()

    tile_base = max(1, args.tile_base)

    anim_names = []
    anim_folders = []
    for pair in args.anims.split(','):
        anim_name, folder = pair.split('=')
        anim_names.append(anim_name)
        anim_folders.append(folder)

    num_anims = len(anim_names)
    print(f"Player '{name}': {num_anims} animations x {len(ANGLES)} angles")

    # --- Load all PNG sequences ---
    all_frames = {}
    for ai, (anim_name, folder) in enumerate(zip(anim_names, anim_folders)):
        for gi, angle in enumerate(ANGLES):
            path = os.path.join(args.root, folder, angle)
            if not os.path.isdir(path):
                print(f"  WARNING: missing {path}")
                continue
            frames = load_png_sequence(path)
            all_frames[(ai, gi)] = frames
            print(f"  [{anim_name}/{angle}] {len(frames)} frames, "
                  f"{frames[0].shape[1]}x{frames[0].shape[0]}")

    if not all_frames:
        print("ERROR: No frames loaded")
        sys.exit(1)

    # --- Compute union bounding box ---
    r0, c0, r1, c1_coord = compute_union_bbox(all_frames)
    grid_r0 = (r0 // 16) * 16
    grid_c0 = (c0 // 16) * 16
    grid_r1 = ((r1 + 16) // 16) * 16
    grid_c1 = ((c1_coord + 16) // 16) * 16
    n_cols = (grid_c1 - grid_c0) // 16
    n_rows = (grid_r1 - grid_r0) // 16
    print(f"  Union grid: {n_cols} cols x {n_rows} rows "
          f"({n_cols * 16}x{n_rows * 16}px, {n_cols * n_rows} tiles/frame)")

    # --- Compute anchor ---
    anchor_x, anchor_y = compute_anchor(all_frames, grid_r0, grid_c0)
    print(f"  Anchor: ({anchor_x}, {anchor_y})")

    # --- Build palette using PIL quantize ---
    palette_rgb, color_lut = quantize_palette(all_frames)

    # --- Encode all tiles with global deduplication ---
    tile_cache = {}
    c1_data = bytearray()
    c2_data = bytearray()

    # Reserve tile 0 as empty (prepend blank tile)
    c1_data.extend(b'\x00' * 64)
    c2_data.extend(b'\x00' * 64)
    next_tile = tile_base

    results = [[None] * len(ANGLES) for _ in range(num_anims)]

    for ai, anim_name in enumerate(anim_names):
        for gi, angle in enumerate(ANGLES):
            key = (ai, gi)
            if key not in all_frames:
                continue

            frames = all_frames[key]
            anim_frames = []

            for fi, img in enumerate(frames):
                sh, sw = img.shape[:2]
                pad_h = max(grid_r1, sh)
                pad_w = max(grid_c1, sw)
                indexed = np.zeros((pad_h, pad_w), dtype=np.uint8)

                alpha = img[:, :, 3]
                for y in range(sh):
                    for x in range(sw):
                        if alpha[y, x] > 0:
                            rgb = (int(img[y, x, 0]),
                                   int(img[y, x, 1]),
                                   int(img[y, x, 2]))
                            indexed[y, x] = color_lut.get(rgb, 1)

                tile_ids = []

                for col in range(n_cols):
                    for row in range(n_rows):
                        ty = grid_r0 + row * 16
                        tx = grid_c0 + col * 16
                        tile = indexed[ty:ty+16, tx:tx+16]

                        if np.all(tile == 0):
                            tile_ids.append(0)
                            continue

                        tkey = tile.tobytes()
                        if tkey in tile_cache:
                            tile_ids.append(tile_cache[tkey])
                        else:
                            tid = next_tile
                            tile_cache[tkey] = tid
                            tc1, tc2 = encode_crom_tile(tile)
                            c1_data.extend(tc1)
                            c2_data.extend(tc2)
                            next_tile += 1
                            tile_ids.append(tid)

                anim_frames.append({
                    'tiles': tile_ids,
                    'duration': args.duration,
                })

            results[ai][gi] = {
                'frames': anim_frames,
                'num_frames': len(anim_frames),
            }
            print(f"  [{anim_name}/{angle}] {len(anim_frames)} frames encoded")

    total_tiles = next_tile - tile_base
    print(f"\n  Total unique tiles: {total_tiles} "
          f"(tile IDs {tile_base}-{next_tile - 1})")

    # --- Write C1/C2 ROM data ---
    c1_path = os.path.join(args.output, 'player8_c1.bin')
    c2_path = os.path.join(args.output, 'player8_c2.bin')
    with open(c1_path, 'wb') as f:
        f.write(c1_data)
    with open(c2_path, 'wb') as f:
        f.write(c2_data)
    print(f"  C1: {c1_path} ({len(c1_data)} bytes)")
    print(f"  C2: {c2_path} ({len(c2_data)} bytes)")

    # --- Write C header ---
    header_path = os.path.join(args.output, f'player8_{name_lower}.h')
    with open(header_path, 'w') as f:
        guard = f'PLAYER8_{name_upper}_H'
        f.write(f'#ifndef {guard}\n#define {guard}\n\n')
        f.write('#include <neo_anim.h>\n\n')

        for i, angle in enumerate(ANGLES):
            f.write(f'#define ANGLE_{angle.upper():<12s} {i}\n')
        f.write(f'#define NUM_ANGLES        {len(ANGLES)}\n\n')

        for i, anim_name in enumerate(anim_names):
            f.write(f'#define {name_upper}_ANIM_{anim_name.upper():<8s} {i}\n')
        f.write(f'#define {name_upper}_NUM_ANIMS    {num_anims}\n\n')

        # Palette
        f.write(f'static const uint16_t {name_upper}_PALETTE[16] = {{\n')
        f.write('    0x0000,\n')
        for i, (r, g, b) in enumerate(palette_rgb):
            word = rgb_to_neogeo_word(r, g, b)
            comma = ',' if i < len(palette_rgb) - 1 or len(palette_rgb) < 15 else ''
            f.write(f'    0x{word:04X}{comma}  /* #{r:02X}{g:02X}{b:02X} */\n')
        for i in range(len(palette_rgb) + 1, 16):
            comma = ',' if i < 15 else ''
            f.write(f'    0x0000{comma}\n')
        f.write('};\n\n')

        # Per-animation, per-angle data
        for ai, anim_name in enumerate(anim_names):
            for gi, angle in enumerate(ANGLES):
                r = results[ai][gi]
                if r is None:
                    continue

                prefix = f'_{name_lower}_{anim_name}_{angle}'

                for fi, frame in enumerate(r['frames']):
                    tiles = frame['tiles']
                    f.write(f'static const uint16_t {prefix}_f{fi}[] = {{')
                    for ti, tid in enumerate(tiles):
                        if ti % 12 == 0:
                            f.write('\n    ')
                        f.write(f'{tid}')
                        if ti < len(tiles) - 1:
                            f.write(', ')
                    f.write('\n};\n\n')

                f.write(f'static const anim_frame_t {prefix}_frames[] = {{\n')
                for fi, frame in enumerate(r['frames']):
                    dur = frame['duration']
                    f.write(f'    {{ {prefix}_f{fi}, 0, {dur} }},\n')
                f.write('};\n\n')

                nf = r['num_frames']
                f.write(f'static const anim_def_t {prefix} = {{\n')
                f.write(f'    {prefix}_frames,\n')
                f.write(f'    {nf},     /* num_frames */\n')
                f.write(f'    {n_cols},     /* width */\n')
                f.write(f'    {n_rows},     /* height */\n')
                f.write(f'    {anchor_x},    /* anchor_x */\n')
                f.write(f'    {anchor_y},    /* anchor_y */\n')
                f.write(f'    1      /* num_palettes */\n')
                f.write('};\n\n')

        f.write(f'static const anim_def_t * const '
                f'{name_upper}_ANIMS[{num_anims}][{len(ANGLES)}] = {{\n')
        for ai, anim_name in enumerate(anim_names):
            f.write(f'    /* {name_upper}_ANIM_{anim_name.upper()} */\n')
            f.write('    { ')
            for gi, angle in enumerate(ANGLES):
                prefix = f'_{name_lower}_{anim_name}_{angle}'
                f.write(f'&{prefix}')
                if gi < len(ANGLES) - 1:
                    f.write(', ')
            f.write(' },\n')
        f.write('};\n\n')

        f.write('#endif\n')

    print(f"  Header: {header_path}")
    print(f"\nDone: {total_tiles} tiles, {num_anims} anims x {len(ANGLES)} angles")


if __name__ == '__main__':
    main()
