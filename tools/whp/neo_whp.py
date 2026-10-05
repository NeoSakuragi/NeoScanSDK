#!/usr/bin/env python3
"""World Heroes Perfect ROM access + Neo Geo sprite rendering (numpy).
P: 2 MB = P1 1 MB at $000000 + 1 MB at $200000 (no bank switch). C: 28 MB."""
import struct, numpy as np
NEO = '/data/roms/whp.neo'
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
    def __init__(self):
        self.p, self.c = load()
    def off(self, a):
        a &= 0xFFFFFF
        if a < 0x100000: return a
        if 0x200000 <= a < 0x300000: return 0x100000 + (a - 0x200000)
        raise ValueError(hex(a))
    def u8(self, a): return self.p[self.off(a)]
    def s8(self, a): v = self.p[self.off(a)]; return v - 256 if v & 0x80 else v
    def u16(self, a): return struct.unpack_from('>H', self.p, self.off(a))[0]
    def s16(self, a): return struct.unpack_from('>h', self.p, self.off(a))[0]
    def u32(self, a): return struct.unpack_from('>I', self.p, self.off(a))[0]

_tiles = {}
def tile(c, code):
    """16x16 pen indices of C-ROM tile `code` (.neo C = C1/C2 byte-interleaved)"""
    if code in _tiles: return _tiles[code]
    off = (code * 128) % len(c)
    b = np.frombuffer(c, np.uint8, 128, off).reshape(2, 16, 4)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    t = np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint8)
    _tiles[code] = t; return t

def color(raw):
    r = ((raw >> 14) & 1) | (((raw >> 8) & 0xF) << 1)
    g = ((raw >> 13) & 1) | (((raw >> 4) & 0xF) << 1)
    b = ((raw >> 12) & 1) | ((raw & 0xF) << 1)
    f = lambda v: (v << 3) | (v >> 2)
    return (f(r), f(g), f(b))

def vram_words(path):
    d = open(path, 'rb').read(); return struct.unpack(f'>{len(d) // 2}H', d)

def pal_bank(path, bank=0):
    d = open(path, 'rb').read(); w = struct.unpack(f'>{len(d) // 2}H', d)
    return w[bank * 4096:(bank + 1) * 4096]

def chains(v):
    """[(slot, x, top, rows, scb2)] per sprite slot (sticky chains resolved); top = screen row of the first tile"""
    out = []; sx = sy = sh = 0
    for s in range(381):
        scb3 = v[0x8200 + s]
        if scb3 & 0x40: sx = (sx + 16) & 0x1FF
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7
        top = (496 - sy) & 0x1FF
        out.append((s, sx, top, sh, v[0x8000 + s]))
    return out

def vram_index(v, slots=None, w=320, h=224):
    """VRAM sprites -> pen-index image (palette * 16 + pen, 0 transparent), full-size slots only"""
    img = np.zeros((h, w), np.uint16); c = load()[1]; skipped = []
    for s, sx, top, sh, scb2 in chains(v):
        if slots is not None and s not in slots: continue
        if sh == 0: continue
        if scb2 & 0xFFF != 0x0FFF: skipped.append(s); continue
        for r in range(min(sh, 32)):
            code = v[s * 64 + 2 * r]; at = v[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            if not code: continue
            t = tile(c, code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            Ys = (top + r * 16 + np.arange(16)) & 0x1FF; Xs = (sx + np.arange(16)) & 0x1FF
            yk, xk = Ys < h, Xs < w
            if not yk.any() or not xk.any(): continue
            sub = t[np.ix_(yk, xk)].astype(np.uint16)
            reg = img[np.ix_(Ys[yk], Xs[xk])]
            img[np.ix_(Ys[yk], Xs[xk])] = np.where(sub > 0, ((at >> 8) << 4) | sub, reg)
    return img, skipped

def colorize(img, pal):
    lut = np.full((4096, 3), 255, np.uint8)
    for i in range(4096):
        if i & 15: lut[i] = color(pal[i])
    return lut[img]
