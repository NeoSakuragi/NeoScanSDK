#!/usr/bin/env python3
"""Garou: Mark of the Wolves (SNK 1999) fighter data from the P ROM (study /data/neogeo_dict/garou/README.md).

ROM /data/roms/garou.neo: P 9 MB already decrypted (the SMA program scramble undone), C 64 MB already decrypted
(CMC42 undone). The NEO-SMA KF (MVS) chip maps a bank at $200000: register $2FFFC0, value unscrambled with
bitswap(12, 14, 6, 7, 9, 5) into MAME's garou bankoffset table (prot_sma.cpp): P[$100000 + bankoffset[n] + a - $200000]."""
import struct

NEO = '/data/roms/garou.neo'
OFF = [0x000000, 0x100000, 0x200000, 0x300000, 0x280000, 0x380000, 0x2d0000, 0x3d0000, 0x2f0000, 0x3f0000,
       0x400000, 0x500000, 0x420000, 0x520000, 0x440000, 0x540000, 0x498000, 0x598000, 0x4a0000, 0x5a0000,
       0x4a8000, 0x5a8000, 0x4b0000, 0x5b0000, 0x4b8000, 0x5b8000, 0x4c0000, 0x5c0000, 0x4c8000, 0x5c8000,
       0x4d0000, 0x5d0000, 0x458000, 0x558000, 0x460000, 0x560000, 0x468000, 0x568000, 0x470000, 0x570000,
       0x478000, 0x578000, 0x480000, 0x580000, 0x488000, 0x588000, 0x490000, 0x590000, 0x5d0000, 0x5d8000,
       0x5e0000, 0x5e8000, 0x5f0000, 0x5f8000, 0x600000]

def bank_base(v):
    """the SMA register value -> the P offset seen at $200000"""
    n = 0
    for i, b in enumerate((12, 14, 6, 7, 9, 5)): n |= ((v >> b) & 1) << (5 - i)
    return 0x100000 + OFF[n]

_raw = None
def load():
    global _raw
    if _raw is None:
        raw = open(NEO, 'rb').read()
        sizes = struct.unpack('<6I', raw[4:0x1C]); off = 0x1000; reg = {}
        for name, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes):
            reg[name] = raw[off:off + sz]; off += sz
        p = bytearray(reg['P']); p[0::2], p[1::2] = reg['P'][1::2], reg['P'][0::2]
        _raw = (bytes(p), reg['C'], reg)
    return _raw
P = load()[0]

def off(a, bank=0x100000):
    """68000 address -> P offset; bank = the P offset mapped at $200000 (bank_base of the register value)"""
    a &= 0xFFFFFF
    if a < 0x100000: return a
    if 0x200000 <= a < 0x300000: return bank + (a - 0x200000)
    raise ValueError(hex(a))
def u8(a, b=0x100000): return P[off(a, b)]
def s8(a, b=0x100000): v = P[off(a, b)]; return v - 256 if v & 0x80 else v
def u16(a, b=0x100000): return struct.unpack_from('>H', P, off(a, b))[0]
def s16(a, b=0x100000): return struct.unpack_from('>h', P, off(a, b))[0]
def u32(a, b=0x100000): return struct.unpack_from('>I', P, off(a, b))[0]

CHARS = ['terry', 'rock', 'dong', 'jae', 'hotaru', 'gato', 'jenet', 'marco', 'hokutomaru', 'freeman', 'griffon',
         'kevin', 'grant', 'kain']                          # the ROM's name list $68046
ROCK = 1

# ---- animations [code: $11C9E player, $11D44 set, $11EA0 step load] ----
def bank_anim(ch): return bank_base(u16(0x11E5C + 2 * ch))       # the step durations' bank
def bank_step(ch): return bank_base(u16(0x11A44 + 4 * ch))        # the step records' bank

def anim_rec(ch, anim):
    """$11DA8[char] -> word [anim]: the 34-byte record index (+$62 / +$64)"""
    return u16(u32(0x11DA8 + 4 * ch) + 2 * anim)

def durations_addr(ch, anim):
    """$11AC4[char] = [offset][table]: the anim's duration words at table + offset + 2 * table[anim] (bank_anim)"""
    o, t = u32(0x11AC4 + 8 * ch), u32(0x11AC8 + 8 * ch)
    return t + o + 2 * u16(t + 2 * anim, bank_anim(ch))

def step_addr(ch, anim, step):
    """$11F86: $11804[char] = [offset][table]; record index + step // 32 -> 34-byte record [base word][32 offset
    bytes]; the step record at table + offset + 4 * base + 4 * byte[step % 32] (bank_step)"""
    r = anim_rec(ch, anim) + step // 32; k = step % 32
    o, t = u32(0x11804 + 16 * ch), u32(0x11808 + 16 * ch); b = bank_step(ch)
    rec = t + 34 * r
    return t + o + 4 * s16(rec, b) + 4 * u8(rec + 2 + k, b)

def step(ch, anim, k):
    """a step record ($11EE2): [w: bits 0-10 frame id][long -> +$54][flags +$6A][flags +$76][pad if flags & 3]
    [boxes: (flags76 & 7) x 5 bytes [type][y1][y2][x1][x2] (x4 px) when flags76 & $18 == 0]"""
    b = bank_step(ch); a = step_addr(ch, anim, k)
    w = u16(a, b); l = u32(a + 2, b); f6a = u8(a + 6, b); f76 = u8(a + 7, b); a += 8
    if f6a & 3: a += 1
    boxes = []
    if not f76 & 0x18:
        for i in range(f76 & 7):
            boxes.append(tuple([u8(a + 5 * i, b)] + [s8(a + 5 * i + j, b) * 4 for j in range(1, 5)]))
    dur = u16(durations_addr(ch, anim) + 2 * k, bank_anim(ch))
    return dict(addr=a, w=w, fid=w & 0x7FF, l=l, f6a=f6a, f76=f76, boxes=boxes, dur=dur)

def steps(ch, anim, limit=64):
    """the steps until the end flag ($6A bit 4) or the loop flag (bit 5)"""
    out = []
    for k in range(limit):
        s = step(ch, anim, k); out.append(s)
        if s['f6a'] & 0x30: break
    return out

# ---- sprite definitions [code: $11F2E; bank $100000 = register $011A] ----
SDEF = 0x200100
def sprite_def(ch, fid):
    """$200100 + long[$200102 + 4 char] -> a1; a2 = $200100 + long[a1]; def = $200100 + long[a2 + 4 fid]:
    [palette add (+$81)][format (+$67 bits 2-5)][cols][rows][word +$82][data...]"""
    a1 = SDEF + u32(SDEF + 2 + 4 * ch); a2 = SDEF + u32(a1); d = SDEF + u32(a2 + 4 * fid)
    return dict(fid=fid, addr=d, paladd=u8(d), fmt=u8(d + 1) & 15, cols=u8(d + 2), rows=u8(d + 3), w82=u16(d + 4),
                data=d + 6)

def sprite_cells(sd):
    """-> cols x rows of tile codes (0 / None = empty) as the format handlers write SCB1 unflipped ($4868: the 13
    formats x 4 flip variants; the ones Garou's fighters use are LB2's: 0 / 1 word / byte masks + a base tile counting
    up (long & $FFFFF), 3 a tile word per cell under byte 1's high tile nibble, 7 / 8 word / byte masks (8: padded to
    even) + tile words, 9 / 10 word / byte masks + tile low bytes under byte 0)"""
    f, nc, nr, a = sd['fmt'], sd['cols'], sd['rows'], sd['data']
    cells = [[None] * nr for _ in range(nc)]
    if f in (0, 1, 4):
        tile = u32(a) & 0xFFFFF; p = a + 4
        for c in range(nc):
            if f == 1: m = u8(p) << 8; p += 1
            else: m = u16(p); p += 2
            for r in range(nr):
                if m >> (15 - r) & 1: cells[c][r] = tile; tile += 1
    elif f == 3:
        at = u16(a); p = a + 2
        for c in range(nc):
            for r in range(nr):
                cells[c][r] = u16(p) | ((at >> 4) & 15) << 16; p += 2
    elif f in (7, 8, 9, 10):
        at = u16(a); p = a + 2
        hi = (at >> 4 & 15) << 16
        if f in (7, 9): masks = [u16(p + 2 * c) for c in range(nc)]; q = p + 2 * nc
        else: masks = [u8(p + c) << 8 for c in range(nc)]; q = p + nc + (nc & 1 if f == 8 else 0)
        for c in range(nc):
            for r in range(nr):
                if masks[c] >> (15 - r) & 1:
                    if f in (7, 8): t = u16(q); q += 2
                    else: t = (at & 0xFF00) | u8(q); q += 1
                    cells[c][r] = t | hi
    else:
        raise ValueError(f'sprite format {f} not decoded')
    return cells

# ---- tiles / colours (lb2's: .neo C = C1/C2 byte-interleaved) ----
import numpy as np
_tiles = {}
def tile(code):
    if code in _tiles: return _tiles[code]
    c = load()[1]
    o = (code * 128) % len(c)
    b = np.frombuffer(c, np.uint8, 128, o).reshape(2, 16, 4)
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

def render_step(ch, st, img, ox, oy, hflip=0, palbase=0):
    """a step drawn as $3328 places it: top-left x = ox - xoff (+$54), mirrored (cols * 16) - xoff from the right;
    y = oy - yoff (+$56), y up on the game's side: the sprite's top at oy + yoff in screen rows (yoff negative = above
    the feet). Pen-index image palette * 16 + pen."""
    sd = sprite_def(ch, st['fid'])
    cells = sprite_cells(sd)
    xo, yo = st['l'] >> 16, st['l'] & 0xFFFF
    xo -= 0x10000 if xo & 0x8000 else 0; yo -= 0x10000 if yo & 0x8000 else 0
    fl = (st['f6a'] >> 7 & 1) ^ hflip
    W = sd['cols'] * 16
    x = ox - (W - xo) if fl else ox - xo
    y = oy + yo
    pal = (palbase + sd['paladd']) & 0xFF
    H_, W_ = img.shape
    cols = cells[::-1] if fl else cells
    for ci, col in enumerate(cols):
        for ri, t in enumerate(col):
            if not t: continue
            tt = tile(t)
            if fl: tt = tt[:, ::-1]
            yy, xx = y + ri * 16, x + ci * 16
            ys, xs = slice(max(yy, 0), min(yy + 16, H_)), slice(max(xx, 0), min(xx + 16, W_))
            if ys.start >= ys.stop or xs.start >= xs.stop: continue
            sub = tt[ys.start - yy:ys.stop - yy, xs.start - xx:xs.stop - xx].astype(np.uint16)
            img[ys, xs] = np.where(sub > 0, (pal << 4) | sub, img[ys, xs])
    return img
