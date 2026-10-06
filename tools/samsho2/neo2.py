#!/usr/bin/env python3
"""Samurai Shodown II ROM access + Neo Geo sprite rendering (numpy).
P = 2 MB: the first MB at $000000, the second at $200000 (no bank switching, no protection)."""
import struct, numpy as np
NEO = '/data/roms/samsho2.neo'
_cache = {}
def load(path=NEO):
    if path in _cache: return _cache[path]
    raw = open(path, 'rb').read()
    sizes = struct.unpack('<6I', raw[4:0x1C]); off = 0x1000; reg = {}
    for name, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes):
        reg[name] = raw[off:off + sz]; off += sz
    p = bytearray(reg['P']); p[0::2], p[1::2] = reg['P'][1::2], reg['P'][0::2]
    assert bytes(p[0x100:0x107]) == b'NEO-GEO'
    _cache[path] = (bytes(p), reg['C'], reg); return _cache[path]

def off(a):
    a &= 0xFFFFFF
    if a < 0x100000: return a
    if 0x200000 <= a < 0x300000: return a - 0x100000
    raise ValueError(hex(a))
P = load()[0]
def u8(a): return P[off(a)]
def s8(a): v = P[off(a)]; return v - 256 if v & 0x80 else v
def u16(a): return struct.unpack_from('>H', P, off(a))[0]
def s16(a): return struct.unpack_from('>h', P, off(a))[0]
def u32(a): return struct.unpack_from('>I', P, off(a))[0]

_tiles = {}
def tile(code):
    """16x16 pen indices of C-ROM tile `code` (.neo C = C1/C2 byte-interleaved)"""
    if code in _tiles: return _tiles[code]
    c = load()[1]
    o = (code * 128) % len(c)
    b = np.frombuffer(c, np.uint8, 128, o).reshape(2, 16, 4)   # [half: 0 = right 8 px, 1 = left][row][bp0 bp2 bp1 bp3]
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

def words(path):
    d = open(path, 'rb').read(); return struct.unpack(f'>{len(d) // 2}H', d)

def vram_index(v, w=320, h=224, slots=None):
    """VRAM sprites -> pen-index image (palette * 16 + pen, 0 = transparent) and the slot that drew each pixel
    (-1 none); full-size slots only (SCB2 $0FFF), others listed in `skipped`. Screen row = sprite line (496 - SCB3 y)."""
    img = np.zeros((h, w), np.uint16); who = np.full((h, w), -1, np.int16); skipped = []
    sx = sy = sh = 0
    for s in range(1, 381):
        scb3 = v[0x8200 + s]
        if scb3 & 0x40: sx += 16
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7
        if slots is not None and s not in slots: continue
        if sh == 0: continue
        if v[0x8000 + s] != 0x0FFF: skipped.append(s); continue
        top = (496 - sy) & 0x1FF
        for r in range(min(sh, 32)):
            code = v[s * 64 + 2 * r]; at = v[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            if code == 0: continue
            t = tile(code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            for yy in range(16):
                Y = (top + r * 16 + yy) & 0x1FF
                if Y >= h: continue
                row = t[yy]
                for xx in range(16):
                    X = (sx + xx) & 0x1FF
                    if X >= w or not row[xx]: continue
                    img[Y, X] = (at >> 8) * 16 + int(row[xx]); who[Y, X] = s
    return img, who, skipped

def colorize(img, pal_words, bg=(255, 255, 255)):
    """pen-index image -> RGB with a 4096-word palette bank"""
    lut = np.zeros((4096, 3), np.uint8)
    for i in range(4096): lut[i] = color(pal_words[i])
    out = lut[img]; out[(img & 15) == 0] = bg
    return out
