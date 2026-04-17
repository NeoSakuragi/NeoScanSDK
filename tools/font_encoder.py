#!/usr/bin/env python3
"""Generate a Neo Geo S ROM with an 8x8 bitmap font for the fix layer.

Each S ROM tile is 32 bytes with this bitplane layout:
  Bytes  0-7:  Bitplane 2, rows 0-7
  Bytes  8-15: Bitplane 3, rows 0-7
  Bytes 16-23: Bitplane 0, rows 0-7
  Bytes 24-31: Bitplane 1, rows 0-7

Bit 0 = leftmost pixel within each byte.
Font tiles are placed at indices matching ASCII codes (tile 0x41 = 'A').
"""

import argparse
import os
import numpy as np
from PIL import Image, ImageFont, ImageDraw

FONT_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
    '/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf',
]

SROM_TILE_SIZE = 32
SROM_DEFAULT_SIZE = 0x20000


def find_system_font():
    for p in FONT_PATHS:
        if os.path.exists(p):
            return p
    return None


def render_glyph(ch, font, cell_w=8, cell_h=8):
    """Render a character into an 8x8 bitmap. Returns list of 8 bytes."""
    img = Image.new('L', (cell_w * 4, cell_h * 4), 0)
    draw = ImageDraw.Draw(img)
    draw.text((0, 0), ch, fill=255, font=font)

    bbox = img.getbbox()
    if bbox is None:
        return [0] * cell_h

    gw = bbox[2] - bbox[0]
    gh = bbox[3] - bbox[1]
    glyph = img.crop(bbox)

    final = Image.new('L', (cell_w, cell_h), 0)
    ox = (cell_w - gw) // 2
    oy = (cell_h - gh) // 2
    if oy < 0: oy = 0
    if ox < 0: ox = 0
    paste_w = min(gw, cell_w - ox)
    paste_h = min(gh, cell_h - oy)
    final.paste(glyph.crop((0, 0, paste_w, paste_h)), (ox, oy))

    rows = []
    for y in range(cell_h):
        byte = 0
        for x in range(cell_w):
            if final.getpixel((x, y)) > 64:
                byte |= (1 << x)
        rows.append(byte)
    return rows


def encode_srom_tile(bitmap_rows, color_index=1):
    """Encode an 8-row bitmap into 32-byte S ROM tile format.
    bitmap_rows: list of 8 bytes (1bpp, bit 0 = leftmost).
    color_index: palette index for visible pixels (1-15).

    S ROM packed nibble format with scrambled column order:
      Bytes  0-7:  columns 4,5 (rows 0-7)
      Bytes  8-15: columns 6,7 (rows 0-7)
      Bytes 16-23: columns 0,1 (rows 0-7)
      Bytes 24-31: columns 2,3 (rows 0-7)
    Each byte: lo nibble = left pixel, hi nibble = right pixel.
    """
    tile = bytearray(32)
    col_groups = [(4, 5, 0), (6, 7, 8), (0, 1, 16), (2, 3, 24)]

    for cl, cr, base in col_groups:
        for row in range(8):
            px = bitmap_rows[row] if row < len(bitmap_rows) else 0
            pl = color_index if (px >> cl) & 1 else 0
            pr = color_index if (px >> cr) & 1 else 0
            tile[base + row] = (pr << 4) | pl

    return bytes(tile)


def generate_font_srom(font_path=None, font_size=8, color_index=1):
    """Generate S ROM data with a bitmap font at ASCII tile positions."""
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        sys_font = find_system_font()
        if sys_font:
            font = ImageFont.truetype(sys_font, font_size)
        else:
            font = ImageFont.load_default()

    max_tile = 0x80
    srom = bytearray(max_tile * SROM_TILE_SIZE)

    for code in range(0x20, 0x7F):
        bitmap = render_glyph(chr(code), font)
        tile_data = encode_srom_tile(bitmap, color_index)
        offset = code * SROM_TILE_SIZE
        srom[offset:offset + SROM_TILE_SIZE] = tile_data

    return bytes(srom)


def main():
    parser = argparse.ArgumentParser(
        description='Generate Neo Geo S ROM with bitmap font')
    parser.add_argument('-o', '--output', required=True,
                        help='Output S ROM file')
    parser.add_argument('--font', help='TTF font file (default: system mono)')
    parser.add_argument('--size', type=int, default=8,
                        help='Font point size (default: 8)')
    parser.add_argument('--color-index', type=int, default=1,
                        help='Palette color index for text (default: 1)')
    parser.add_argument('--srom-size', type=int, default=SROM_DEFAULT_SIZE,
                        help='Total S ROM size in bytes (default: 128KB)')
    parser.add_argument('--preview', metavar='FILE',
                        help='Save a preview PNG of the font')
    args = parser.parse_args()

    font_data = generate_font_srom(args.font, args.size, args.color_index)

    srom = bytearray(args.srom_size)
    srom[:len(font_data)] = font_data

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'wb') as f:
        f.write(srom)

    print(f"S ROM: {args.output} ({len(srom)} bytes)")
    print(f"  Font tiles: 0x20-0x7E (95 characters)")
    print(f"  Color index: {args.color_index}")

    if args.preview:
        cols = 16
        rows = (0x7F - 0x20 + cols - 1) // cols
        img = Image.new('RGB', (cols * 9, rows * 9), (0, 0, 40))
        col_groups = [(4, 5, 0), (6, 7, 8), (0, 1, 16), (2, 3, 24)]
        for code in range(0x20, 0x7F):
            idx = code - 0x20
            cx = (idx % cols) * 9
            cy = (idx // cols) * 9
            off = code * SROM_TILE_SIZE
            for cl, cr, base in col_groups:
                for y in range(8):
                    b = srom[off + base + y]
                    if b & 0x0F:
                        img.putpixel((cx + cl, cy + y), (255, 255, 255))
                    if b & 0xF0:
                        img.putpixel((cx + cr, cy + y), (255, 255, 255))
        img.save(args.preview)
        print(f"  Preview: {args.preview}")


if __name__ == '__main__':
    main()
