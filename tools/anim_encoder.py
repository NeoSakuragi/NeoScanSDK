#!/usr/bin/env python3
"""Encode Aseprite animations for NeoScan: parse .aseprite → C ROM tiles + animation data header.

Handles 32bpp RGBA Aseprite files (the format used by sprite extraction tools).
Detects 2x scale, downsamples, extracts/quantizes palette(s), slices 16x16 tiles,
deduplicates, and outputs C1/C2 ROM binaries + C headers for the SDK's ANIM_ API.

Multi-palette support: when an animation uses > 15 unique colors, the encoder
splits them into 2 palettes (body + accessory pattern from fighting games) and
tracks per-tile palette assignments. Each tile is assigned to whichever palette
contains the majority of its visible pixels.
"""

import struct
import os
import sys
import argparse
import zlib
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ─── Aseprite parser ─────────────────────────────────────────────────

def parse_aseprite(path):
    """Parse an Aseprite file. Returns (width, height, palette_rgba, frames).
    Each frame: {'image': np.array(h,w,4 uint8), 'duration': int ms}.
    """
    with open(path, 'rb') as f:
        data = f.read()

    fsize, magic, nframes, w, h, bpp = struct.unpack_from('<IHHHHH', data, 0)
    if magic != 0xA5E0:
        raise ValueError(f"Not an Aseprite file: {path}")
    if bpp != 32:
        raise ValueError(f"Only 32bpp RGBA Aseprite files supported, got {bpp}bpp")

    palette = []
    frames = []
    off = 128

    for fi in range(nframes):
        frame_size, _, old_chunks, duration, _, new_chunks = struct.unpack_from(
            '<IHHH2sI', data, off)
        nchunks = new_chunks if new_chunks else old_chunks
        canvas = np.zeros((h, w, 4), dtype=np.uint8)

        chunk_off = off + 16
        for ci in range(nchunks):
            csize, ctype = struct.unpack_from('<IH', data, chunk_off)

            if ctype == 0x2019 and not palette:
                ncolors = struct.unpack_from('<I', data, chunk_off + 6)[0]
                col_off = chunk_off + 26
                for i in range(ncolors):
                    if col_off + 6 > chunk_off + csize:
                        break
                    flags_c = struct.unpack_from('<H', data, col_off)[0]
                    r, g, b, a = data[col_off+2:col_off+6]
                    palette.append((r, g, b, a))
                    col_off += 6
                    if flags_c & 1:
                        slen = struct.unpack_from('<H', data, col_off)[0]
                        col_off += 2 + slen

            elif ctype == 0x2005:
                cel_data = data[chunk_off+6:chunk_off+csize]
                cx, cy = struct.unpack_from('<hh', cel_data, 2)
                cel_type = struct.unpack_from('<H', cel_data, 7)[0]

                if cel_type == 2:
                    zlib_pos = -1
                    for sig in [b'\x78\x9c', b'\x78\x01', b'\x78\xda']:
                        p = cel_data.find(sig)
                        if p >= 0:
                            zlib_pos = p
                            break
                    if zlib_pos >= 0:
                        cw, ch = struct.unpack_from('<HH', cel_data, zlib_pos - 4)
                        pixels = zlib.decompress(cel_data[zlib_pos:])
                        img = np.frombuffer(pixels, dtype=np.uint8).reshape(ch, cw, 4)
                        y0 = max(0, cy); y1 = min(h, cy + ch)
                        x0 = max(0, cx); x1 = min(w, cx + cw)
                        src = img[y0-cy:y1-cy, x0-cx:x1-cx]
                        mask = src[:, :, 3] > 0
                        canvas[y0:y1, x0:x1][mask] = src[mask]

            chunk_off += csize

        frames.append({'image': canvas, 'duration': duration})
        off += frame_size

    return w, h, palette, frames


# ─── Color / palette ─────────────────────────────────────────────────

def rgb_to_neogeo_word(r, g, b):
    """Convert RGB888 to Neo Geo 16-bit color word (no dark bit)."""
    r5 = r >> 3; g5 = g >> 3; b5 = b >> 3
    return (((r5 & 1) << 14) | ((r5 >> 1) << 8) |
            ((g5 & 1) << 13) | ((g5 >> 1) << 4) |
            ((b5 & 1) << 12) | ((b5 >> 1) << 0))


def collect_unique_colors(frames):
    """Collect all unique non-transparent RGB tuples across frames."""
    color_set = set()
    for frame in frames:
        img = frame['image']
        mask = img[:, :, 3] > 0
        pixels = img[mask]
        for px in pixels:
            color_set.add((int(px[0]), int(px[1]), int(px[2])))
    return sorted(color_set)


def split_palettes(colors, max_per_palette=15):
    """Split colors into 1 or 2 palettes of up to 15 colors each.
    Returns list of palettes: [[(r,g,b), ...], ...] and a color→(pal_idx, color_idx) map.
    """
    if len(colors) <= max_per_palette:
        pal_map = {}
        for i, c in enumerate(colors):
            pal_map[c] = (0, i + 1)
        return [colors], pal_map

    arr = np.array(colors, dtype=np.float64)
    from_sklearn = False
    try:
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=2, n_init=10, random_state=42).fit(arr)
        labels = km.labels_
        from_sklearn = True
    except ImportError:
        labels = _simple_kmeans_2(arr)

    pal0 = [colors[i] for i in range(len(colors)) if labels[i] == 0]
    pal1 = [colors[i] for i in range(len(colors)) if labels[i] == 1]

    if len(pal0) > max_per_palette:
        pal0 = _quantize_median_cut(pal0, max_per_palette)
    if len(pal1) > max_per_palette:
        pal1 = _quantize_median_cut(pal1, max_per_palette)

    pal_map = {}
    for i, c in enumerate(pal0):
        pal_map[c] = (0, i + 1)
    for i, c in enumerate(pal1):
        pal_map[c] = (1, i + 1)

    return [pal0, pal1], pal_map


def _simple_kmeans_2(arr):
    """Simple 2-means clustering without sklearn."""
    n = len(arr)
    c0 = arr[0]
    c1 = arr[n // 2]
    for _ in range(20):
        d0 = np.sum((arr - c0) ** 2, axis=1)
        d1 = np.sum((arr - c1) ** 2, axis=1)
        labels = (d1 < d0).astype(int)
        labels = 1 - labels
        m0 = arr[labels == 0]
        m1 = arr[labels == 1]
        if len(m0) > 0:
            c0 = m0.mean(axis=0)
        if len(m1) > 0:
            c1 = m1.mean(axis=0)
    return labels


def _quantize_median_cut(colors, target):
    """Simple median-cut quantization."""
    colors = [list(c) for c in colors]
    buckets = [colors]
    while len(buckets) < target:
        longest_bucket = max(buckets, key=len)
        if len(longest_bucket) <= 1:
            break
        buckets.remove(longest_bucket)
        arr = np.array(longest_bucket)
        ranges = arr.max(axis=0) - arr.min(axis=0)
        split_ch = np.argmax(ranges)
        sorted_bucket = sorted(longest_bucket, key=lambda c: c[split_ch])
        mid = len(sorted_bucket) // 2
        buckets.append(sorted_bucket[:mid])
        buckets.append(sorted_bucket[mid:])
    result = []
    for bucket in buckets:
        arr = np.array(bucket)
        mean = arr.mean(axis=0).astype(int)
        result.append((int(mean[0]), int(mean[1]), int(mean[2])))
    return result[:target]


def nearest_color_in_palette(rgb, palette, color_map_for_pal):
    """Find the nearest color in a specific palette. Returns palette index (1-based)."""
    best_idx, best_dist = 1, float('inf')
    for c, (pal_id, idx) in color_map_for_pal.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb, c))
        if d < best_dist:
            best_dist = d
            best_idx = idx
    return best_idx


def pixel_to_index(px, pal_map, palettes):
    """Map an RGBA pixel to (palette_offset, color_index). (_, 0) = transparent."""
    if px[3] == 0:
        return 0, 0
    key = (int(px[0]), int(px[1]), int(px[2]))
    if key in pal_map:
        return pal_map[key]
    best_pal, best_idx, best_dist = 0, 1, float('inf')
    for pi, palette in enumerate(palettes):
        for ci, (r, g, b) in enumerate(palette):
            d = (key[0] - r) ** 2 + (key[1] - g) ** 2 + (key[2] - b) ** 2
            if d < best_dist:
                best_dist = d
                best_pal = pi
                best_idx = ci + 1
    return best_pal, best_idx


# ─── Tile encoding ───────────────────────────────────────────────────

def encode_crom_tile(pixels_16x16):
    """Encode a 16x16 indexed tile to C1/C2 ROM bytes (64 bytes each).
    C1 = bitplanes 0,1.  C2 = bitplanes 2,3.
    Right half first, then left half.
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


# ─── Main pipeline ───────────────────────────────────────────────────

def detect_scale(frames):
    """Detect if frames are at 2x scale by looking at content height."""
    for frame in frames:
        alpha = frame['image'][:, :, 3]
        rows = np.any(alpha > 0, axis=1)
        if rows.any():
            content_h = np.where(rows)[0][-1] - np.where(rows)[0][0] + 1
            return 2 if content_h > 150 else 1
    return 1


def compute_union_bbox(frames):
    """Compute the union bounding box across all frames."""
    min_r, min_c = 99999, 99999
    max_r, max_c = 0, 0
    for frame in frames:
        alpha = frame['image'][:, :, 3]
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


def process_animation(ase_path, tile_base, tile_cache, c1_data, c2_data):
    """Process a single .aseprite file into animation data.

    Returns dict with animation metadata, tile IDs, and per-tile palette offsets.
    """
    name = os.path.splitext(os.path.basename(ase_path))[0]
    print(f"Processing {name}...")

    w, h, pal, frames = parse_aseprite(ase_path)
    print(f"  {w}x{h}, {len(frames)} frames, {frames[0]['duration']}ms/frame")

    scale = detect_scale(frames)
    if scale > 1:
        print(f"  Detected {scale}x scale, downsampling...")
        for frame in frames:
            frame['image'] = frame['image'][::scale, ::scale]

    unique_colors = collect_unique_colors(frames)
    print(f"  Unique colors: {len(unique_colors)}")

    palettes, pal_map = split_palettes(unique_colors)
    num_palettes = len(palettes)
    print(f"  Palettes: {num_palettes} ({', '.join(str(len(p)) for p in palettes)} colors)")

    ds_h, ds_w = frames[0]['image'].shape[:2]

    bbox = compute_union_bbox(frames)
    r0, c0, r1, c1_coord = bbox

    grid_r0 = (r0 // 16) * 16
    grid_c0 = (c0 // 16) * 16
    grid_r1 = ((r1 + 16) // 16) * 16
    grid_c1 = ((c1_coord + 16) // 16) * 16

    n_cols = (grid_c1 - grid_c0) // 16
    n_rows = (grid_r1 - grid_r0) // 16
    print(f"  Grid: {n_cols} cols x {n_rows} rows ({n_cols * n_rows} tiles/frame)")

    center_xs = []
    bottom_ys = []
    for frame in frames:
        alpha = frame['image'][:, :, 3]
        rows_mask = np.any(alpha > 0, axis=1)
        cols_mask = np.any(alpha > 0, axis=0)
        if rows_mask.any():
            bottom_ys.append(np.where(rows_mask)[0][-1])
            cx0, cx1 = np.where(cols_mask)[0][[0, -1]]
            center_xs.append((cx0 + cx1) // 2)

    feet_x = int(np.median(center_xs)) if center_xs else ds_w // 2
    feet_y = max(bottom_ys) if bottom_ys else ds_h
    anchor_x = feet_x - grid_c0
    anchor_y = feet_y - grid_r0
    print(f"  Anchor: ({anchor_x}, {anchor_y}) in grid coords")

    next_tile = tile_base
    anim_frames = []
    uses_multi_pal = False

    for fi, frame in enumerate(frames):
        img = frame['image']
        sh, sw = img.shape[:2]

        indexed_pal = np.zeros((sh, sw), dtype=np.uint8)
        indexed_idx = np.zeros((sh, sw), dtype=np.uint8)
        alpha = img[:, :, 3]

        for y in range(sh):
            for x in range(sw):
                if alpha[y, x] > 0:
                    pal_off, ci = pixel_to_index(img[y, x], pal_map, palettes)
                    indexed_pal[y, x] = pal_off
                    indexed_idx[y, x] = ci

        pad_h = max(grid_r1, sh)
        pad_w = max(grid_c1, sw)
        padded_idx = np.zeros((pad_h, pad_w), dtype=np.uint8)
        padded_pal = np.zeros((pad_h, pad_w), dtype=np.uint8)
        padded_idx[:sh, :sw] = indexed_idx
        padded_pal[:sh, :sw] = indexed_pal

        tile_ids = []
        tile_pals = []

        for col in range(n_cols):
            for row in range(n_rows):
                ty = grid_r0 + row * 16
                tx = grid_c0 + col * 16
                tile_ci = padded_idx[ty:ty+16, tx:tx+16]
                tile_pi = padded_pal[ty:ty+16, tx:tx+16]

                if np.all(tile_ci == 0):
                    tile_ids.append(0)
                    tile_pals.append(0)
                    continue

                visible_pals = tile_pi[tile_ci > 0]
                if len(visible_pals) == 0:
                    majority_pal = 0
                elif num_palettes > 1:
                    counts = np.bincount(visible_pals, minlength=num_palettes)
                    majority_pal = int(np.argmax(counts))
                else:
                    majority_pal = 0

                if majority_pal != 0:
                    uses_multi_pal = True

                final_tile = np.zeros((16, 16), dtype=np.uint8)
                for y in range(16):
                    for x in range(16):
                        ci = tile_ci[y, x]
                        if ci == 0:
                            continue
                        pi = tile_pi[y, x]
                        if pi == majority_pal:
                            final_tile[y, x] = ci
                        else:
                            px_rgb = (int(img[ty+y-grid_r0, tx+x-grid_c0][0]) if (ty+y-grid_r0) < sh and (tx+x-grid_c0) < sw else 0,
                                      int(img[ty+y-grid_r0, tx+x-grid_c0][1]) if (ty+y-grid_r0) < sh and (tx+x-grid_c0) < sw else 0,
                                      int(img[ty+y-grid_r0, tx+x-grid_c0][2]) if (ty+y-grid_r0) < sh and (tx+x-grid_c0) < sw else 0)
                            best_ci, best_d = 1, float('inf')
                            for c_rgb, (p, c) in pal_map.items():
                                if p == majority_pal:
                                    d = sum((a-b)**2 for a,b in zip(px_rgb, c_rgb))
                                    if d < best_d:
                                        best_d = d
                                        best_ci = c
                            final_tile[y, x] = best_ci

                key = final_tile.tobytes()
                if key in tile_cache:
                    tile_ids.append(tile_cache[key])
                else:
                    tid = next_tile
                    tile_cache[key] = tid
                    tc1, tc2 = encode_crom_tile(final_tile)
                    c1_data.extend(tc1)
                    c2_data.extend(tc2)
                    next_tile += 1
                    tile_ids.append(tid)

                tile_pals.append(majority_pal)

        duration_ms = frame['duration']
        duration_vblanks = max(1, round(duration_ms / 16.67))

        anim_frames.append({
            'tiles': tile_ids,
            'pal_offsets': tile_pals,
            'duration_vblanks': duration_vblanks,
        })

    if not uses_multi_pal:
        for f in anim_frames:
            f['pal_offsets'] = None

    print(f"  Unique tiles: {next_tile - tile_base}")
    print(f"  VBlanks/frame: {anim_frames[0]['duration_vblanks']}")
    print(f"  Multi-palette: {'yes' if uses_multi_pal else 'no'}")

    return {
        'name': name,
        'palettes': palettes,
        'num_palettes': num_palettes,
        'uses_multi_pal': uses_multi_pal,
        'frames': anim_frames,
        'width': n_cols,
        'height': n_rows,
        'anchor_x': anchor_x,
        'anchor_y': anchor_y,
        'next_tile': next_tile,
    }


# ─── Output generators ───────────────────────────────────────────────

def write_palette_headers(palettes, output_dir, base_name='ANIM_PALETTE'):
    """Write Neo Geo palette headers for each palette slot."""
    paths = []
    for pi, pal_rgb in enumerate(palettes):
        suffix = f'_{pi}' if len(palettes) > 1 else ''
        var_name = f'{base_name}{suffix}'
        filename = f'anim_palette{suffix}.h'
        output_path = os.path.join(output_dir, filename)

        with open(output_path, 'w') as f:
            guard = var_name.upper() + '_H'
            f.write(f'#ifndef {guard}\n#define {guard}\n\n')
            f.write('#include <stdint.h>\n\n')
            f.write(f'static const uint16_t {var_name}[16] = {{\n')
            f.write('    0x0000,\n')
            for i, (r, g, b) in enumerate(pal_rgb):
                word = rgb_to_neogeo_word(r, g, b)
                comma = ',' if i < len(pal_rgb) - 1 or len(pal_rgb) < 15 else ''
                f.write(f'    0x{word:04X}{comma}  /* #{r:02X}{g:02X}{b:02X} */\n')
            for i in range(len(pal_rgb) + 1, 16):
                comma = ',' if i < 15 else ''
                f.write(f'    0x0000{comma}\n')
            f.write('};\n\n#endif\n')
        paths.append(output_path)
        print(f"  Palette {pi}: {output_path} ({len(pal_rgb)} colors)")
    return paths


def write_anim_header(anim, output_path):
    """Write animation data header for the SDK's ANIM_ API."""
    name = anim['name']
    name_upper = name.upper()
    name_lower = name.lower()
    uses_mp = anim['uses_multi_pal']

    with open(output_path, 'w') as f:
        f.write(f'#ifndef ANIM_{name_upper}_H\n')
        f.write(f'#define ANIM_{name_upper}_H\n\n')
        f.write('#include <neo_anim.h>\n\n')

        for fi, frame in enumerate(anim['frames']):
            tiles = frame['tiles']
            f.write(f'static const uint16_t _{name_lower}_f{fi}[] = {{')
            for ti, tid in enumerate(tiles):
                if ti % 12 == 0:
                    f.write('\n    ')
                f.write(f'{tid}')
                if ti < len(tiles) - 1:
                    f.write(', ')
            f.write('\n};\n\n')

            if uses_mp and frame['pal_offsets'] is not None:
                pals = frame['pal_offsets']
                f.write(f'static const uint8_t _{name_lower}_p{fi}[] = {{')
                for ti, po in enumerate(pals):
                    if ti % 20 == 0:
                        f.write('\n    ')
                    f.write(f'{po}')
                    if ti < len(pals) - 1:
                        f.write(', ')
                f.write('\n};\n\n')

        f.write(f'static const anim_frame_t _{name_lower}_frames[] = {{\n')
        for fi, frame in enumerate(anim['frames']):
            dur = frame['duration_vblanks']
            pal_ptr = f'_{name_lower}_p{fi}' if (uses_mp and frame['pal_offsets'] is not None) else '0'
            f.write(f'    {{ _{name_lower}_f{fi}, {pal_ptr}, {dur} }},\n')
        f.write('};\n\n')

        w = anim['width']
        h = anim['height']
        ax = anim['anchor_x']
        ay = anim['anchor_y']
        nf = len(anim['frames'])
        np_ = anim['num_palettes']
        f.write(f'static const anim_def_t ANIM_{name_upper} = {{\n')
        f.write(f'    _{name_lower}_frames,\n')
        f.write(f'    {nf},    /* num_frames */\n')
        f.write(f'    {w},     /* width (columns) */\n')
        f.write(f'    {h},     /* height (rows) */\n')
        f.write(f'    {ax},    /* anchor_x */\n')
        f.write(f'    {ay},    /* anchor_y */\n')
        f.write(f'    {np_}    /* num_palettes */\n')
        f.write('};\n\n')

        f.write(f'#endif\n')

    print(f"  Animation data: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Encode Aseprite animations for NeoScan SDK')
    parser.add_argument('aseprite', nargs='+', help='.aseprite files')
    parser.add_argument('-o', '--output', required=True, help='Output directory')
    parser.add_argument('--tile-base', type=int, default=1,
                        help='Starting tile ID (default: 1)')
    parser.add_argument('--palette-name', default='ANIM_PALETTE',
                        help='Palette variable name prefix')
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    tile_cache = {}
    c1_data = bytearray()
    c2_data = bytearray()
    next_tile = args.tile_base

    animations = []
    for ase_path in args.aseprite:
        anim = process_animation(ase_path, next_tile, tile_cache, c1_data, c2_data)
        next_tile = anim['next_tile']
        animations.append(anim)

    c1_path = os.path.join(args.output, 'anim_c1.bin')
    c2_path = os.path.join(args.output, 'anim_c2.bin')
    with open(c1_path, 'wb') as f:
        f.write(c1_data)
    with open(c2_path, 'wb') as f:
        f.write(c2_data)
    print(f"  C1: {c1_path} ({len(c1_data)} bytes, {len(c1_data)//64} tiles)")
    print(f"  C2: {c2_path} ({len(c2_data)} bytes)")

    if animations:
        write_palette_headers(animations[0]['palettes'], args.output, args.palette_name)

    for anim in animations:
        header_path = os.path.join(args.output, f'anim_{anim["name"]}.h')
        write_anim_header(anim, header_path)

    print(f"\nTotal: {next_tile - args.tile_base} unique tiles across {len(animations)} animation(s)")
    print(f"Tile ID range: {args.tile_base} - {next_tile - 1}")


if __name__ == '__main__':
    main()
