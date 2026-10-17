#!/usr/bin/env python3
"""CPS1 frame renderer from an FBNeo (libretro) Final Fight save state: GFX RAM + CPS-A registers -> layers + objects.

FBNeo's CPS1 state blob (fbneo_libretro, ffight, 269189 bytes) starts with a 4-byte header, then
- GFX RAM $900000-$92FFFF (0x30000 bytes, 68k words little-endian = byte-swapped),
- 68k work RAM $FF0000-$FFFFFF (0x10000, same swap),
- CPS-A registers $800100-$8001FF (0x100, same swap), then the rest of the machine.
Offsets were found by matching the live RAM and the scroll base words $9080/$90C0/$9100 the game writes ($21F6).

CPS-A (Final Fight, vblank $53E): +00 object base, +02/04/06 scroll1/2/3 base, +0A palette base ($9140 fixed),
+0C/0E scroll1 x/y, +10/12 scroll2 x/y, +14/16 scroll3 x/y. CPS-B (CPS_B_04): +6E layer control
(draw order: bits 6-7 bottom ... 12-13 top; 0 = objects, 1/2/3 = scroll1/2/3; enable bits 1/2/3 = scroll1/2/3).
Visible screen = hardware x 64..447, y 16..239 (384 x 224).
Palette RAM: 6 pages of 32 x 16 words from the palette base: objects, scroll1, scroll2, scroll3.
Graphics (ff.load()[1], S224B mapper = identity): 8x8 scroll1 tile n = 64 bytes at n*64, rows of 8 bytes, the left
(bytes 0-3) or right (4-7) half chosen by tilemap column parity; 16x16 objects / scroll2 = 128 bytes;
32x32 scroll3 = 512 bytes, rows of 16 bytes (4 groups of 4 plane bytes).
"""
import struct, sys
from PIL import Image
sys.path.insert(0, __file__.rsplit('/', 1)[0])
import ff

GFX_OFF, RAM_OFF, REG_OFF = 4, 4 + 0x30000, 4 + 0x40000

def unswap(b): return bytes(b[i ^ 1] for i in range(len(b)))

class State:
    def __init__(self, path):
        s = open(path, 'rb').read()
        self.gfx = unswap(s[GFX_OFF:GFX_OFF + 0x30000])
        self.ram = unswap(s[RAM_OFF:RAM_OFF + 0x10000])
        self.reg = unswap(s[REG_OFF:REG_OFF + 0x100])
        self.G = ff.load()[1]
    def r(self, o): return struct.unpack('>H', self.reg[o:o + 2])[0]
    def gw(self, a): a -= 0x900000; return struct.unpack('>H', self.gfx[a:a + 2])[0]
    def mw(self, a): a -= 0xFF0000; return struct.unpack('>H', self.ram[a:a + 2])[0]
    def base(self, o): return (self.r(o) << 8) & 0xFFFF00 | 0x900000 if self.r(o) < 0x100 else self.r(o) << 8
    def pal(self, page, p):
        b = self.r(0x0A) << 8
        return [ff.cps_rgb(self.gw(b + page * 0x400 + p * 32 + 2 * k)) for k in range(16)]
    def palwords(self, page, p):
        b = self.r(0x0A) << 8
        return [self.gw(b + page * 0x400 + p * 32 + 2 * k) for k in range(16)]

    # --- pixels -------------------------------------------------------------------------------------------------
    def px8(self, code, half):
        o = (code & 0x7FFF) * 64; out = []
        for y in range(8):
            b = self.G[o + 8 * y + 4 * half:o + 8 * y + 4 * half + 4]
            out.append([sum(((b[k] >> (7 - x)) & 1) << k for k in range(4)) for x in range(8)])
        return out
    def px16(self, code): return ff.tile_pixels(code)
    def px32(self, code):
        o = (code & 0xFFF) * 512; out = []
        for y in range(32):
            row = []
            for g in range(4):
                b = self.G[o + 16 * y + 4 * g:o + 16 * y + 4 * g + 4]
                row += [sum(((b[k] >> (7 - x)) & 1) << k for k in range(4)) for x in range(8)]
            out.append(row)
        return out

    # --- layers -------------------------------------------------------------------------------------------------
    def tilemap(self, layer):
        """[(col, row, code, attr)] of scroll layer 1/2/3 (64 x 64 tiles)"""
        b = self.r(2 * layer) << 8; out = []
        for col in range(64):
            for row in range(64):
                if layer == 1: i = (row & 0x1F) + ((col & 0x3F) << 5) + ((row & 0x20) << 6)
                elif layer == 2: i = (row & 0x0F) + ((col & 0x3F) << 4) + ((row & 0x30) << 6)
                else: i = (row & 0x07) + ((col & 0x3F) << 3) + ((row & 0x38) << 6)
                out.append((col, row, self.gw(b + 4 * i), self.gw(b + 4 * i + 2)))
        return out
    def layer_image(self, layer, empty=None):
        """full 64x64-tile layer as RGBA (transparent pen 15), plus the tile list"""
        ts = {1: 8, 2: 16, 3: 32}[layer]; im = Image.new('RGBA', (64 * ts, 64 * ts), (0, 0, 0, 0)); px = im.load()
        used = []
        for col, row, code, attr in self.tilemap(layer):
            if empty is not None and code == empty: continue
            pens = self.px8(code, col & 1) if layer == 1 else self.px16(code) if layer == 2 else self.px32(code)
            if all(p == 15 for r in pens for p in r): continue
            pal = self.pal(layer, attr & 0x1F); fx, fy = attr & 0x20, attr & 0x40
            for y in range(ts):
                for x in range(ts):
                    p = pens[ts - 1 - y if fy else y][ts - 1 - x if fx else x]
                    if p != 15: px[col * ts + x, row * ts + y] = pal[p] + (255,)
            used.append((col, row, code, attr))
        return im, used
    def scroll(self, layer): return self.r(0x0C + 4 * (layer - 1)), self.r(0x0E + 4 * (layer - 1))
    def layer_on_screen(self, layer):
        full, _ = self.layer_image(layer); sx, sy = self.scroll(layer); n = full.size[0]
        out = Image.new('RGBA', (384, 224), (0, 0, 0, 0))
        for y in range(224):
            for x in range(384):
                out.putpixel((x, y), full.getpixel(((x + 64 + sx) % n, (y + 16 + sy) % n)))
        return out

    # --- objects ------------------------------------------------------------------------------------------------
    def objects(self):
        """[(index, x, y, code, attr)] until the end marker (attr $FF00)"""
        b = self.r(0) << 8; out = []
        for i in range(256):
            x, y, code, attr = (self.gw(b + 8 * i + 2 * k) for k in range(4))
            if attr & 0xFF00 == 0xFF00: break
            out.append((i, x, y, code, attr))
        return out
    def obj_tiles(self, o):
        """an object's 16x16 cells: [(code, sx, sy, fx, fy, pal)] in visible-screen coords"""
        i, x, y, code, attr = o; nx, ny = (attr >> 8 & 15) + 1, (attr >> 12 & 15) + 1
        fx, fy = bool(attr & 0x20), bool(attr & 0x40); out = []
        for by in range(ny):
            for bx in range(nx):
                c = (code & ~0xF) + ((code + bx) & 0xF) + 0x10 * by
                cx = (nx - 1 - bx) if fx else bx; cy = (ny - 1 - by) if fy else by
                sx = ((x + 16 * cx) & 0x1FF) - 64; sy = ((y + 16 * cy) & 0x1FF) - 16
                out.append((c & 0xFFFF, sx, sy, fx, fy, attr & 0x1F))
        return out
    def draw_objects(self, img, objs, origin=(0, 0)):
        px = img.load(); W, H = img.size
        for o in reversed(objs):                       # index 0 on top
            for c, sx, sy, fx, fy, p in self.obj_tiles(o):
                pens = self.px16(c); pal = self.pal(0, p)
                for y in range(16):
                    for x in range(16):
                        v = pens[15 - y if fy else y][15 - x if fx else x]
                        X, Y = sx + x - origin[0], sy + y - origin[1]
                        if v != 15 and 0 <= X < W and 0 <= Y < H: px[X, Y] = pal[v] + (255,)
        return img
    def layer_order(self):
        lc = self.r(0x6E); return [(lc >> s) & 3 for s in (6, 8, 10, 12)], lc

if __name__ == '__main__':
    s = State(sys.argv[1])
    print('regs', ' '.join('%02x:%04x' % (o, s.r(o)) for o in range(0, 0x18, 2)), 'layer', s.layer_order())
    objs = s.objects(); print(len(objs), 'objects')
    for o in objs: print('%3d x%4d y%4d code %04x attr %04x' % o)
