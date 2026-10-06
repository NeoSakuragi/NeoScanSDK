#!/usr/bin/env python3
"""Samurai Shodown II fighter data from the P ROM (study: /data/neogeo_dict/samsho2/README.md).

  animations   $220280[table] (long) -> longs[anim] -> first step                         (code $369E)
  step         [b0: layers-1 << 6 | command words][ticks][flags word][command words][sprite-definition word x layers]
               (code $3470-$3654; commands $34FC: 0 hold + end flag, 4 loop + end flag, 8 sound, C panned sound,
               10 event word -> +$78, 20 move dx/dy, 24 boxes)
  definition   word & $7FFF (bit 15 = H flip of this layer) -> long $72000[def]: format bits 28-31, rows-1 24-27,
               cols-1 19-23, data = $82004 + 2 * (bits 0-18)                                 (code $4120)
               placement: 3 bytes $208000[3 def]: x / y offsets (2 sign bits each in byte 0 + low bytes)  ($3604)
  formats      handlers $3A4C (no palette / flip) / $3A96 / $3AFC / $3B46; see sprite_cells()"""
import numpy as np
import neo2 as N
from neo2 import u8, s8, u16, s16, u32

ANIMS = 0x220280
DEFS, DATA, PLACE = 0x72000, 0x82004, 0x208000
NDEFS = (DATA - DEFS) // 4

# ---------------- animations ----------------
def anim_table(t): return u32(ANIMS + 4 * t)
def anim_addr(t, anim): return u32(anim_table(t) + 4 * anim)

def n_anims(t):
    """animations in table t: the pointer list runs up to the lowest step address above it (a few tables hold
    non-pointer words in unused slots, and Tam Tam's table 10 has two tiny animations inside its own list)"""
    base = anim_table(t); n = 0; lo = 1 << 30
    while base + 4 * n < lo and n < 2048:
        v = u32(base + 4 * n)
        if 0x200000 <= v < 0x300000 and v >= max(base + 4 * n + 4, base + 64): lo = min(lo, v)
        elif n == 0 and not 0x200000 <= v < 0x300000: return 0
        n += 1
    return n

CMD_LEN = {0: 1, 4: 1, 8: 1, 0xC: 1, 0x10: 1, 0x20: 2}      # words; $24 boxes: 1 + 3 per record

def parse_step(a):
    b0, ticks, flags = u8(a), u8(a + 1), u16(a + 2)
    nl, nw = (b0 >> 6) + 1, b0 & 63
    p = a + 4; cmds = []; end = None; boxes = []
    left = nw
    while left > 0:
        t = u8(p) & 0xFC
        if t in (0, 4):
            end = 'hold' if t == 0 else 'loop'; cmds.append(('end', end)); p += 2; left -= 1
            # the interpreter jumps to the drawing here ($3532): the definition words follow the end command
            break
        if t == 8 or t == 0xC: cmds.append(('sound' if t == 8 else 'sound_pan', u16(p) & 0x3FF)); p += 2; left -= 1
        elif t == 0x10: cmds.append(('event', u16(p) & 0x3FF)); p += 2; left -= 1
        elif t == 0x20:
            dx = u8(p + 2) | (0xFF00 if u8(p + 1) & 2 else 0); dy = u8(p + 3) | (0xFF00 if u8(p + 1) & 1 else 0)
            dx -= 0x10000 if dx & 0x8000 else 0; dy -= 0x10000 if dy & 0x8000 else 0
            cmds.append(('move', dx, dy)); p += 4; left -= 2
        elif t == 0x24:
            n = u8(p + 1) + 1; q = p + 2
            for k in range(n):
                w = u16(q); l = u32(q + 2)
                boxes.append((w, l)); q += 6
            cmds.append(('boxes', n)); left -= 3 * n + 1; p = q
        else:
            cmds.append(('?', t)); p += 2; left -= 1
    if end is None: p = a + 4 + 2 * nw
    layers = [u16(p + 2 * k) for k in range(nl)]
    return dict(addr=a, b0=b0, ticks=ticks, flags=flags, cmds=cmds, boxes=boxes, end=end, layers=layers,
                next=p + 2 * nl)

def parse_anim(t, anim, limit=120):
    a = anim_addr(t, anim); steps = []
    for _ in range(limit):
        st = parse_step(a); steps.append(st)
        if st['end']: break
        a = st['next']
    return steps

def place(d):
    """x / y offsets of definition d ($3604: byte 0 bits 7-6 / 5-4 = signed high bits of x / y)"""
    b0, b1, b2 = u8(PLACE + 3 * d), u8(PLACE + 3 * d + 1), u8(PLACE + 3 * d + 2)
    xh = (b0 >> 6) - (4 if b0 & 0x80 else 0); yh = (b0 >> 4 & 3) - (4 if b0 & 0x20 else 0)
    return xh * 256 + b1, yh * 256 + b2

# ---------------- sprite definitions ----------------
def sprite_def(d):
    e = u32(DEFS + 4 * (d & 0x7FFF))
    return dict(fmt=e >> 28, rows=(e >> 24 & 15) + 1, cols=(e >> 19 & 31) + 1, addr=DATA + 2 * (e & 0x7FFFF), raw=e)

def _inc6(t):
    """format 6 / 15 tile step ($4590): addq.b #1 on the low byte, a wrap to 00 adds $101 (tile low byte 00 skipped)"""
    lo = (t + 1) & 0xFF
    return (t & 0xFF00 | lo) if lo else ((t & 0xFF00) + 0x101) & 0xFFFF

def _overrides(a, cells, rows, attr_only=False):
    """[count word] then count x [a][b][word]: SCB1 word at column base + a*8 + b ($4060 / $408E)"""
    n = u16(a); a += 2
    for _ in range(n):
        o = u8(a) * 8 + u8(a + 1); w = u16(a + 2); a += 4
        c, r, k = o // 64, (o % 64) // 2, o & 1
        if c < len(cells) and r < rows:
            t0, at0 = cells[c][r] if cells[c][r] else (0, 0)
            cells[c][r] = (t0, w) if k else (w, at0)
    return a

def _fmt9(a, nc, nr):
    """the run-length cell stream ($45E8, op tables $4698 / $47D4 / $48AA / $498C / $4AB0): ops are bytes, x4;
    pairs = [tile][attr] words, words = tile words, bytes = tile low bytes (high byte from the last tile),
    repeat = the last tile again, inc = the last tile + 1; cells without an attribute take the last pair's."""
    total = nc * nr; out = []; tile = 0; attr = 0
    KIND = {0: ('pair', 'n'), 0x28: ('pair', 'n'), 0x14: ('pair', 'col'), 0x3C: ('pair', 'all'),
            4: ('word', 'n'), 0x2C: ('word', 'n'), 0x18: ('word', 'col'), 0x40: ('word', 'all'),
            8: ('byte', 'n'), 0x30: ('byte', 'n'), 0x1C: ('byte', 'col'), 0x44: ('byte', 'all'),
            0xC: ('rep', 'n'), 0x34: ('rep', 'n'), 0x20: ('rep', 'col'), 0x48: ('rep', 'all'),
            0x10: ('inc', 'n'), 0x38: ('inc', 'n'), 0x24: ('inc', 'col'), 0x4C: ('inc', 'all')}   # $4C: the code after table $4698
    guard = 0
    while len(out) < total and guard < 4096:
        guard += 1
        op = u8(a); a += 1
        if op not in KIND: raise ValueError(f'format 9: op {op:#x} at {a - 1:#x}')
        kind, how = KIND[op]
        arg = u8(a); a += 1                       # count, or a pad byte for 'col' / 'all'
        if how == 'n': n = arg + 1
        elif how == 'col': n = nr - len(out) % nr
        else: n = total - len(out)
        for _ in range(n):
            if kind == 'pair': tile, attr = u16(a), u16(a + 2); a += 4
            elif kind == 'word': tile = u16(a); a += 2
            elif kind == 'byte': tile = tile & 0xFF00 | u8(a); a += 1
            elif kind == 'inc': tile = (tile + 1) & 0xFFFF
            out.append((tile, attr))
    out = out[:total]
    return [out[c * nr:(c + 1) * nr] for c in range(nc)]

def sprite_cells(d):
    """definition d -> (sd, cols [[(tile, attr) | None] * rows]) as the no-palette, no-flip handlers write SCB1
    (table $3A4C); None = a cell written as tile 0 / attr 0"""
    sd = sprite_def(d)
    f, nc, nr, a = sd['fmt'], sd['cols'], sd['rows'], sd['addr']
    cells = [[None] * nr for _ in range(nc)]
    if f == 0:                                    # $3BD6: [tile][attr] per cell
        for c in range(nc):
            for r in range(nr): cells[c][r] = (u16(a), u16(a + 2)); a += 4
    elif f in (1, 10):                            # $3C3A: [attr]; a tile word per cell (10: + attribute overrides)
        at = u16(a); a += 2
        for c in range(nc):
            for r in range(nr): cells[c][r] = (u16(a), at); a += 2
        if f == 10: _overrides(a, cells, nr)
    elif f in (2, 3, 11):                         # 2 $3CC4: [palette][tile hi], 3 $3D62 / 11 $3F80: [attr][tile hi];
        w = u16(a); a += 2                        # then a tile low byte per cell
        if f == 2: at, hi = w & 0xFF00, w & 0xFF
        else: at, hi = w, u8(a); a += 1
        for c in range(nc):
            for r in range(nr): cells[c][r] = (hi << 8 | u8(a), at); a += 1
        if f == 11:                               # + tile overrides, + attribute overrides
            a = (a + 1) & ~1
            a = _overrides(a, cells, nr); _overrides(a, cells, nr)
    elif f in (4, 12):                            # $3D82: [attr][tile]; tile + 1 per cell (12: + attribute overrides)
        at, t = u16(a), u16(a + 2); a += 4
        for c in range(nc):
            for r in range(nr): cells[c][r] = (t, at); t = (t + 1) & 0xFFFF
        if f == 12: _overrides(a, cells, nr)
    elif f == 5:                                  # $3E6C: [attr lo][palette 0]; tile, then (tile, palette pair, tile) ...
        lo, pal = u8(a), u8(a + 1); a += 2; k = 0
        for c in range(nc):
            for r in range(nr):
                t = u16(a); a += 2
                if k % 2:
                    x = u16(a); a += 2; cells[c][r] = (t, (x >> 8) << 8 | lo); pal = x & 0xFF
                else: cells[c][r] = (t, pal << 8 | lo)
                k += 1
    elif f in (6, 15):                            # $4564 / $45A6: [attr][tile]; a mask byte / word per column, MSB = row 0;
        at, t = u16(a), u16(a + 2); a += 4        # a set bit = a cell (tile, then _inc6)
        for c in range(nc):
            if f == 6: m = u8(a) << 8; a += 1
            else: m = u16(a); a += 2
            for r in range(nr):
                if m >> (15 - r) & 1: cells[c][r] = (t, at); t = _inc6(t)
    elif f == 7:                                  # $3EDA: [tile hi | attr lo]; a [palette][tile lo] word per cell
        w = u16(a); a += 2
        for c in range(nc):
            for r in range(nr): y = u16(a); a += 2; cells[c][r] = (w & 0xFF00 | y & 0xFF, y & 0xFF00 | w & 0xFF)
    elif f == 8:                                  # $3F28: [tile][attr lo]; a palette byte per cell, tile + 1
        t, lo = u16(a), u8(a + 2); a += 3
        for c in range(nc):
            for r in range(nr): cells[c][r] = (t, u8(a) << 8 | lo); a += 1; t = (t + 1) & 0xFFFF
    elif f == 9:
        cells = _fmt9(a, nc, nr)
    else:
        raise ValueError(f'format {f} not decoded (handlers $4B00 / $4B28: a second bytecode, unused by the game data)')
    return sd, cells

# ---------------- rendering (pen-index images: palette * 16 + pen) ----------------
def blit(img, cells, x0, top, hflip=0, pal=0):
    H, W = img.shape
    cols = cells[::-1] if hflip else cells
    for ci, col in enumerate(cols):
        for ri, cell in enumerate(col):
            if cell is None: continue
            t, at = cell
            at = (at + (pal << 8)) & 0xFFFF ^ hflip
            code = t | (at >> 4 & 0xF) << 16
            if code == 0: continue
            tl = N.tile(code)
            if at & 1: tl = tl[:, ::-1]
            if at & 2: tl = tl[::-1]
            y, x = top + ri * 16, x0 + ci * 16
            ys, xs = slice(max(y, 0), min(y + 16, H)), slice(max(x, 0), min(x + 16, W))
            if ys.start >= ys.stop or xs.start >= xs.stop: continue
            sub = tl[ys.start - y:ys.stop - y, xs.start - x:xs.stop - x].astype(np.uint16)
            img[ys, xs] = np.where(sub > 0, ((at >> 8) << 4) | sub, img[ys, xs])

def layer_box(d, X, Y, flip):
    """screen rectangle of definition d drawn at object screen position (X, Y) ($3368): left = X - xoff (flip:
    X - cols*16 + xoff), SCB3 y = yoff - Y, top line = 496 - that (mod 512)"""
    sd = sprite_def(d); xo, yo = place(d & 0x7FFF)
    left = X - xo if not flip else X - sd['cols'] * 16 + xo
    top = (496 - ((yo - Y) & 0x1FF)) & 0x1FF
    if top >= 400: top -= 512
    return sd, left, top

ORDER = {False: [[0], [0, 1], [0, 1, 2], [3, 0, 1, 2]], True: [[0], [1, 0], [1, 0, 2], [3, 1, 0, 2]]}   # $365E / $367E

def render_step(img, step, X, Y, facing=0, pals=(0, 1, 2, 0)):
    """one step at object screen position (X, Y) into a pen-index image; facing = object +$7F; pals = the object's
    +$81 / +$82 / +$83 palette adds per layer (layer 3: none). Later layers are inserted after earlier ones in the
    display list at equal priority -> drawn later = on top [inf]; priority words $355E decide (not modelled)."""
    nl = len(step['layers'])
    order = ORDER[bool(step['flags'] & 0x4000)][nl - 1]
    for li in order:
        w = step['layers'][li]
        flip = facing ^ (w >> 15)
        sd, left, top = layer_box(w, X, Y, flip)
        _, cells = sprite_cells(w & 0x7FFF)
        blit(img, cells, left, top, flip, pals[li])

# ---------------- palettes ----------------
NAMES = ['Haohmaru', 'Nakoruru', 'Hanzo', 'Galford', 'Wan-Fu', 'Ukyo', 'Kyoshiro', 'Gen-an', 'Earthquake', 'Jubei',
         'Tam Tam', 'Charlotte', 'Genjuro', 'Cham Cham', 'Neinhalt Sieger', 'Nicotine', 'Mizuki', 'Kuroko']   # $2452E order

def fighter_palettes(char, colour=0):
    """8 palettes (16 words) loaded to palettes 16-23 (P1) / 24-31 (P2) ($FCB4): block = long $FD10[byte $FCA4[char]
    + 18 * colour]; colour 0 / 1 = the byte $1089FA[char] / $10890C[char] (0 or 18: the second player on the same
    character gets the other set [inf])"""
    blk = u32(0xFD10 + 4 * (u8(0xFCA4 + char) + 18 * colour))
    return [[u16(blk + 32 * p + 2 * k) for k in range(16)] for p in range(8)]

def colorize(img, pals, first=16, bg=(255, 255, 255)):
    """pen-index image -> RGB; pals = 8 palettes for palettes first..first+7, other palettes from palette RAM
    words `extra` if given (else grey)"""
    lut = np.full((4096, 3), 160, np.uint8)
    for p in range(112):                  # fixed effect palettes 32-143 ($FBD4: $216400 -> palette RAM $400400)
        for k in range(16): lut[(32 + p) * 16 + k] = N.color(u16(0x216400 + 32 * p + 2 * k))
    for p in range(16):                   # palettes 0-15 ($FBBA: $214000)
        for k in range(16): lut[p * 16 + k] = N.color(u16(0x214000 + 32 * p + 2 * k))
    lut[0::16] = bg
    for p, pal in enumerate(pals):
        for k in range(16): lut[(first + p) * 16 + k] = N.color(pal[k])
    out = lut[img]; out[(img & 15) == 0] = bg
    return out
