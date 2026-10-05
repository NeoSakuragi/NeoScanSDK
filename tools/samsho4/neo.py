#!/usr/bin/env python3
"""Samurai Shodown IV ROM access + Neo Geo sprite rendering (numpy).
P: 1 MB P1 at $000000 + 4 MB P2 in four 1 MB banks at $200000 (bank n = P bytes (n+1) MB on)."""
import struct, numpy as np
NEO = '/data/roms/samsho4.neo'
_cache = {}
def load(path=NEO):
    if path in _cache: return _cache[path]
    raw = open(path, 'rb').read()
    sizes = struct.unpack('<6I', raw[4:0x1C]); off = 0x1000; reg = {}
    for name, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes):
        reg[name] = raw[off:off + sz]; off += sz
    p = bytearray(reg['P']); p[0::2], p[1::2] = reg['P'][1::2], reg['P'][0::2]
    assert bytes(p[0x100:0x107]) == b'NEO-GEO'
    _cache[path] = (bytes(p), reg['C']); return _cache[path]

class Mem:
    def __init__(self, bank=0):
        self.p, self.c = load(); self.bank = bank
    def off(self, a, bank=None):
        a &= 0xFFFFFF
        if a < 0x100000: return a
        if 0x200000 <= a < 0x300000: return 0x100000 + (self.bank if bank is None else bank) * 0x100000 + (a - 0x200000)
        raise ValueError(hex(a))
    def u8(self, a, bank=None): return self.p[self.off(a, bank)]
    def u16(self, a, bank=None): return struct.unpack_from('>H', self.p, self.off(a, bank))[0]
    def s16(self, a, bank=None): return struct.unpack_from('>h', self.p, self.off(a, bank))[0]
    def s8(self, a, bank=None): v = self.p[self.off(a, bank)]; return v - 256 if v & 0x80 else v
    def u32(self, a, bank=None): return struct.unpack_from('>I', self.p, self.off(a, bank))[0]

YOFF = 0   # geolith frame row 0 = sprite line 0 [meas]
_tiles = {}
def tile(c, code):
    """16x16 pen indices of C-ROM tile `code` (.neo C = C1/C2 byte-interleaved)"""
    if code in _tiles: return _tiles[code]
    off = (code * 128) % len(c)
    b = np.frombuffer(c, np.uint8, 128, off).reshape(2, 16, 4)   # [half: 0 = right 8 px, 1 = left][row][bp0 bp2 bp1 bp3]
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')  # [half][row][plane][x]
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    t = np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint8)
    _tiles[code] = t; return t

def color(raw):
    dark = (raw >> 15) & 1
    r = ((raw >> 14) & 1) | (((raw >> 8) & 0xF) << 1)
    g = ((raw >> 13) & 1) | (((raw >> 4) & 0xF) << 1)
    b = ((raw >> 12) & 1) | ((raw & 0xF) << 1)
    f = lambda v: (v << 3) | (v >> 2)
    return (f(r), f(g), f(b))

def vram_words(path):
    d = open(path, 'rb').read(); return struct.unpack(f'>{len(d) // 2}H', d)

def pal_bank(path, bank=1):
    """PALDUMP file (2 banks x 4096 BE words) -> one bank as a list of 4096 words (SS4 displays bank 1 in the fight)"""
    d = open(path, 'rb').read(); w = struct.unpack(f'>{len(d) // 2}H', d)
    return w[bank * 4096:(bank + 1) * 4096]

def render_vram(v, pal, slots=None, w=320, h=224, bg=None):
    """VRAM sprites -> RGB image (screen 320 x 224: x as SCB4, row = (496 - y) - 16), full size only
    (SCB2 must be $0FFF for the slots drawn; others are skipped and reported)"""
    img = np.zeros((h, w, 3), np.uint8)
    if bg is not None: img[:] = bg
    c = load()[1]; skipped = []
    sx = sy = sh = 0
    for s in range(381):
        scb3 = v[0x8200 + s]
        if scb3 & 0x40: sx += 16                          # sticky: chained to the previous slot
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7
        if slots is not None and s not in slots: continue
        if sh == 0: continue
        if v[0x8000 + s] != 0x0FFF: skipped.append(s); continue
        top = (496 - sy) & 0x1FF
        for r in range(min(sh, 32)):
            code = v[s * 64 + 2 * r]; at = v[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            t = tile(c, code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            pl = [color(pal[(at >> 8) * 16 + k]) for k in range(16)]
            for yy in range(16):
                Y = ((top + r * 16 + yy) & 0x1FF) - YOFF
                if not 0 <= Y < h: continue
                for xx in range(16):
                    X = ((sx + xx) & 0x1FF)
                    if X >= 320 or X >= w: continue
                    p = t[yy, xx]
                    if p: img[Y, X] = pl[p]
    return img, skipped
