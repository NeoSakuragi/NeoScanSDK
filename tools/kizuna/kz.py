#!/usr/bin/env python3
"""Kizuna Encounter (SNK 1996) ROM decoder: animations, steps, sprite definitions, tiles.
P = 2 MB flat (P1 $000000, P2 $200000, no bank switch). C = 28 MB.
Code read in the disassembly (dis.sh): step loader $139EA, sprite def lookup $13A40, renderer $1491A / $156F0
(13 formats, jump table $1586E), positioning $14F88."""
import struct
import numpy as np
NEO = '/data/roms/kizuna.neo'
_c = {}

def load(path=NEO):
    if path in _c: return _c[path]
    raw = open(path, 'rb').read()
    sizes = struct.unpack('<6I', raw[4:0x1C]); off = 0x1000; reg = {}
    for name, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes):
        reg[name] = raw[off:off + sz]; off += sz
    p = bytearray(reg['P']); p[0::2], p[1::2] = reg['P'][1::2], reg['P'][0::2]
    assert bytes(p[0x100:0x107]) == b'NEO-GEO'
    _c[path] = (bytes(p), reg['C']); return _c[path]

P, C = load()
def off(a):
    a &= 0xFFFFFF
    if a < 0x100000: return a
    if 0x200000 <= a < 0x300000: return 0x100000 + a - 0x200000
    raise ValueError(hex(a))
def u8(a): return P[off(a)]
def s8(a): v = P[off(a)]; return v - 256 if v & 0x80 else v
def u16(a): return struct.unpack_from('>H', P, off(a))[0]
def s16(a): return struct.unpack_from('>h', P, off(a))[0]
def u32(a): return struct.unpack_from('>I', P, off(a))[0]

# ---- animations ($138F0): id = char << 12 | n; table T = $80000 + long[$80000 + 4 char]; word T = count;
#      animation n (1 <= n < count) at T + 2 * word[T + 2n]
def anim_table(ch): return 0x80000 + u32(0x80000 + 4 * ch)
def anim_count(ch): return u16(anim_table(ch))
def anim_addr(aid):
    T = anim_table(aid >> 12); n = aid & 0xFFF
    if n >= u16(T): return None
    return T + 2 * u16(T + 2 * n)

# ---- sprite definitions ($13A40): def word w: sel = w >> 12, index = w & $FFF;
#      entry long[$200000 + (long[$200000 + 4 sel] & $FFFFFE) + 4 index]; data = $200000 + (long[$200040 + 4 sel] & $FFFFFE)
#      + (entry & $7FFFF); entry high word: format = bits 12-15, rows - 1 = bits 8-11, cols - 1 = bits 3-7
def sdef_entry(w):
    sel = (w >> 12) * 4
    ib = 0x200000 + (u32(0x200000 + sel) & 0xFFFFFE)
    db = 0x200000 + (u32(0x200040 + sel) & 0xFFFFFE)
    a = ib + (w & 0xFFF) * 4
    if a >= db: return None
    e = u32(a); hi = e >> 16
    return {'data': db + (e & 0x7FFFF), 'format': hi >> 12, 'rows': (hi >> 8 & 15) + 1, 'cols': (hi >> 3 & 31) + 1}

def sdef(w):
    """-> {'format', 'cols': [[(code, attr) | None] * rows]} as the renderer writes SCB1 (no flip, palette offset 0);
    attr = the SCB1 attribute word: palette << 8 | code bits 16-19 << 4 | auto-anim << 2 | V << 1 | H"""
    e = sdef_entry(w)
    if e is None: return None
    fmt, nc, nr, p = e['format'], e['cols'], e['rows'], e['data']
    cells = [[None] * nr for _ in range(nc)]
    def W():
        nonlocal p; v = u16(p); p += 2; return v
    def B():
        nonlocal p; v = u8(p); p += 1; return v
    def put(c, r, code, attr):
        cells[c][r] = (code | (attr >> 4 & 15) << 16, attr) if code or attr >> 4 & 15 else None
    if fmt in (0,):                                     # $159AC: per cell [code w][attr w]
        for c in range(nc):
            for r in range(nr): code = W(); put(c, r, code, W())
    elif fmt in (1, 2, 3, 4, 7, 10):                    # first cell [code w][attr w], then per format
        code = W(); attr = W(); k = 0; first = (code, attr); cur = code
        for c in range(nc):
            for r in range(nr):
                if c == 0 and r == 0: put(0, 0, code, attr); continue
                k += 1
                if fmt == 1:                            # $15A36: alternating [code w][attr lo b] / [attr lo b][code w]
                    if k % 2: code = W(); lo = B()
                    else: lo = B(); code = W()
                    put(c, r, code, (first[1] & 0xFF00) | lo)
                elif fmt == 2:                          # $15BB0: alternating [code w][attr hi b] / [attr hi b][code w]
                    if k % 2: code = W(); hi = B()
                    else: hi = B(); code = W()
                    put(c, r, code, ((hi << 8) | (first[1] & 0xFF)) & 0xFFFF)
                elif fmt == 3: put(c, r, W(), first[1])                       # $15D46: code words, attr constant
                elif fmt == 4: put(c, r, (first[0] & 0xFF00) | B(), first[1]) # $15E24: code low bytes
                elif fmt == 7:                          # $161CE: consecutive codes, attr hi byte per cell
                    cur = (cur + 1) & 0xFFFF; put(c, r, cur, ((B() << 8) | (first[1] & 0xFF)) & 0xFFFF)
                elif fmt == 10: cur = (cur + 1) & 0xFFFF; put(c, r, cur, first[1])   # $165D8: consecutive, attr constant
    elif fmt in (5, 6, 8, 9, 11, 12):                   # masks (5/8/11 bytes, 6/9/12 words; MSB = top row), then a
        mp = p                                          # long [code][attr], then per format
        p += ((nc + 1) & ~1) if fmt in (5, 8, 11) else nc * 2
        code = W(); attr = W()
        for c in range(nc):
            m = u8(mp) << 8 if fmt in (5, 8, 11) else u16(mp); mp += 1 if fmt in (5, 8, 11) else 2
            for r in range(nr):
                if not (m << r) & 0x8000: continue
                put(c, r, code, attr)
                if fmt in (5, 6): code = (code & 0xFF00) | B()               # $15F12: next code's low byte
                elif fmt in (8, 9): code = (code + 1) & 0xFFFF; attr = ((B() << 8) | (attr & 0xFF)) & 0xFFFF  # $162DC
                else: code = (code + 1) & 0xFFFF                             # $166C6: consecutive
    else:
        raise ValueError(f'format {fmt}')
    return {'format': fmt, 'cols': cells, 'end': p}

# ---- steps ($139EA): [flags b][ticks b][def w x n][x b][y b] x n [attr w][trailer w][boxes 6 x k][sound w][command args]
#      flags bit 2: part 1, bit 3: part 2; bits 7/6 part 0 H/V flip, 5/4 part 1; part 2 H flip = ticks byte bit 7
CMD_ARGS = [0, 0, 0, 4, 4, 4, 4, 6, 6, 4, 6, 6, 8, 2, 2, 4, 0, 4, 4, 0] + [0] * 12   # $14062: argument bytes per command
# step commands (attr bits 0-4; handlers $14082[cmd]): 1 stop (velocities 0); 3 / 4 stop + spawn [x b][y b][id w]
# ($3E14A: effects, projectiles); 5 / 6 stop + move [dx w][dy w] px (dx forward); 7 / 8 stop + move [dx b][dy b]
# + spawn [x b][y b][id w]; 9 velocity [vx w][vy w] (1/256 px a frame); 10 [vx][ax][vy]; 11 [vx][vy][ay];
# 12 [vx][ax][vy][ay] (accelerations << 4); 13 [ax]; 14 [ay]; 15 [ax][ay]; 17 / 18 spawn [x b][y b][id w];
# 2, 4, 6, 8, 16, 18 also set $109683 = $10
CMD_NAMES = {1: 'stop', 3: 'spawn', 4: 'spawn', 5: 'move', 6: 'move', 7: 'move+spawn', 8: 'move+spawn', 9: 'vel',
             10: 'vel+ax', 11: 'vel+ay', 12: 'vel+acc', 13: 'ax', 14: 'ay', 15: 'acc', 17: 'spawn', 18: 'spawn'}

def sb(v): return v - 256 if v & 0x80 else v
def sw(v): return v - 65536 if v & 0x8000 else v

def parse_step(a):
    """one step -> dict, next step's address. Trailer word (+$72): bits 0-2 box count, bit 4 = keep the previous
    step's boxes, bit 3 = a sound command word follows the boxes ($1D1B0), bit 6 (read by the hit test).
    Box = [type][b1][x left][x right][y top][y bottom], signed bytes x 4 px (type < $10 body, >= $10 attack; $20D58)"""
    f, t, parts, defs, xy, attr, q = step_at(a)
    tr = u16(q); q += 2
    boxes = None
    n = tr & 7
    if n and not tr & 0x10:
        boxes = [tuple([u8(q + 6 * i), u8(q + 6 * i + 1)] + [sb(u8(q + 6 * i + k)) for k in (2, 3, 4, 5)]) for i in range(n)]
        q += 6 * n
    snd = None
    if tr & 8: snd = u16(q); q += 2
    cmd = attr & 31; args = bytes(P[off(q):off(q) + CMD_ARGS[cmd]]); q += CMD_ARGS[cmd]
    return {'addr': a, 'flags': f, 'ticks': t & 0x7F, 'parts': parts, 'defs': defs, 'offs': offsets(attr, parts, xy),
            'attr': attr, 'trailer': tr, 'nboxes': n, 'boxes': boxes, 'sound': snd, 'cmd': cmd, 'args': args,
            'end': 'loop' if f & 2 else ('hold' if f & 1 else None)}, q

def parse_anim(aid, limit=200):
    a = anim_addr(aid)
    if a is None: return None
    out = []
    for i in range(limit):
        s, a = parse_step(a); out.append(s)
        if s['end']: return out
    raise ValueError(f'{aid:04X}: no end')

def step_at(a):
    f, t = u8(a), u8(a + 1)
    parts = [0] + ([1] if f & 4 else []) + ([2] if f & 8 else [])
    q = a + 2
    defs = []
    for i in parts: defs.append(u16(q)); q += 2
    xy = []
    for i in parts: xy.append((s8(q), s8(q + 1))); q += 2
    attr = u16(q); q += 2
    return f, t, parts, defs, xy, attr, q

def offsets(attr, parts, xy):
    """the parts' x / y offsets in px as the loader computes them (byte * 2, bit 0 from attr bits 15, 14, 13, ...)"""
    out, k = [], 15
    for (x, y) in xy:
        out.append((x * 2 | attr >> k & 1, y * 2 | attr >> (k - 1) & 1)); k -= 2
    return out

_tiles = {}
def tile(code):
    if code in _tiles: return _tiles[code]
    o = (code * 128) % len(C)
    b = np.frombuffer(C, np.uint8, 128, o).reshape(2, 16, 4)
    bits = np.unpackbits(b[..., None], axis=-1, bitorder='little')
    pen = bits[:, :, 0] | bits[:, :, 2] << 1 | bits[:, :, 1] << 2 | bits[:, :, 3] << 3
    t = np.concatenate([pen[1], pen[0]], axis=1).astype(np.uint8)
    _tiles[code] = t; return t

def draw_def(img, w, X, Y, hf=0, vf=0, pal_add=0):
    """draw def w with its top-left at (X, Y) into img (uint16: palette * 16 + pen)"""
    d = sdef(w)
    if not d: return
    nc, nr = len(d['cols']), len(d['cols'][0])
    for c in range(nc):
        for r in range(nr):
            cell = d['cols'][c][r]
            if not cell: continue
            code, at = cell
            t = tile(code)
            h = (at & 1) ^ hf; v = (at >> 1 & 1) ^ vf
            if h: t = t[:, ::-1]
            if v: t = t[::-1]
            cc = nc - 1 - c if hf else c; rr = nr - 1 - r if vf else r
            x0, y0 = X + cc * 16, Y + rr * 16
            pal = ((at >> 8) + pal_add) & 0xFF
            H, Wd = img.shape
            for yy in range(16):
                if not 0 <= y0 + yy < H: continue
                for xx in range(16):
                    if 0 <= x0 + xx < Wd and t[yy, xx]: img[y0 + yy, x0 + xx] = pal << 4 | int(t[yy, xx])
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
    img = np.zeros((h, w), np.uint16); c = C; skipped = []
    for s, sx, top, sh, scb2 in chains(v):
        if slots is not None and s not in slots: continue
        if sh == 0: continue
        if scb2 & 0xFFF != 0x0FFF: skipped.append(s); continue
        for r in range(min(sh, 32)):
            code = v[s * 64 + 2 * r]; at = v[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            if not code: continue
            t = tile(code)
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
def color(raw):
    r = ((raw >> 14) & 1) | (((raw >> 8) & 0xF) << 1)
    g = ((raw >> 13) & 1) | (((raw >> 4) & 0xF) << 1)
    b = ((raw >> 12) & 1) | ((raw & 0xF) << 1)
    f = lambda v: (v << 3) | (v >> 2)
    return (f(r), f(g), f(b))
def colorize(img, pal):
    lut = np.full((4096, 3), 255, np.uint8)
    for i in range(4096):
        if i & 15: lut[i] = color(pal[i])
    return lut[img]

def render_step(img, a, X, Y, face_left=0, pal_add=0):
    """draw the step at a as the game does at full size: X / Y = the object's screen position (Y = the floor line for
    y 0); part offsets (dx, dy): left = X + dx, top = Y - dy; facing left (+$0F bit 1): left = X - dx - 16 cols + 1 and
    every part's H flip toggled ($149E4, $15020)"""
    f, t, parts, defs, xy, attr, q = step_at(a)
    hflags = {0: f >> 7 & 1, 1: f >> 5 & 1, 2: t >> 7 & 1}
    vflags = {0: f >> 6 & 1, 1: f >> 4 & 1, 2: 0}
    for i, w, (dx, dy) in zip(parts, defs, offsets(attr, parts, xy)):
        e = sdef_entry(w)
        if e is None: continue
        left = X - dx - 16 * e['cols'] + 1 if face_left else X + dx
        draw_def(img, w, left, Y - dy, hflags[i] ^ face_left, vflags[i], pal_add)

# ---- the LSPC's shrink (Geolith src/geo_lspc.c: lut_hshrink, the L0 ROM 000-lo.lo of the BIOS set) ----
HSHRINK = [[0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0], [0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0], [0,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0],
           [0,0,1,0,1,0,0,0,1,0,0,0,1,0,0,0], [0,0,1,0,1,0,0,0,1,0,0,0,1,0,1,0], [0,0,1,0,1,0,1,0,1,0,0,0,1,0,1,0],
           [0,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0], [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0], [1,0,1,0,1,0,1,0,1,1,1,0,1,0,1,0],
           [1,0,1,1,1,0,1,0,1,1,1,0,1,0,1,0], [1,0,1,1,1,0,1,0,1,1,1,0,1,0,1,1], [1,0,1,1,1,0,1,1,1,1,1,0,1,0,1,1],
           [1,0,1,1,1,0,1,1,1,1,1,0,1,1,1,1], [1,1,1,1,1,0,1,1,1,1,1,0,1,1,1,1], [1,1,1,1,1,0,1,1,1,1,1,1,1,1,1,1],
           [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]]
_l0 = []
def l0():
    if not _l0:
        import zipfile, os
        _l0.append(zipfile.ZipFile(os.path.expanduser('~/.config/retroarch/system/neogeo.zip')).read('000-lo.lo')[:0x10000])
    return _l0[0]

def draw_sprite(img, x, top, cells, h, v, size):
    """one hardware sprite as the LSPC draws it: cells = [(code, attr)|None] top to bottom (attr bit 0 H, 1 V flip,
    bits 8-15 palette), hshrink h (h + 1 px wide), vshrink v, size tiles tall (SCB3); returns its width"""
    L = l0(); H, W = img.shape
    cols = [p for p in range(16) if HSHRINK[h][p]]
    for i in range(size * 16):
        y = top + i
        if not 0 <= y < H: continue
        srow = L[v * 256 + i] if i < 256 else L[v * 256 + (i & 255 ^ 255)] ^ 0x1FF
        t, line = srow >> 4, srow & 15
        if t >= len(cells) or not cells[t]: continue
        code, at = cells[t]
        tl = tile(code)
        if at & 2: line = 15 - line
        row = tl[line, ::-1] if at & 1 else tl[line]
        for k, p in enumerate(cols):
            if 0 <= x + k < W and row[p]: img[y, x + k] = (at >> 8) << 4 | int(row[p])
    return h + 1

def render_step_zoom(img, a, X, Y, z=0xFF):
    """the step at a as Kizuna draws it facing right with the camera's shrink z ($10966A, 0-255): part offsets scaled
    by (z + 1) / 256 ($15038, $1510C), each part's columns sticky with hshrink z >> 4 or one less by the pattern word
    $4D0C0[z & 15] (rol per column, $14FC8), vshrink z, size ceil(rows (z + 1) / 256) tiles ($15122). z = $FF: full size"""
    f, t, parts, defs, xy, attr, q = step_at(a)
    hfl = {0: f >> 7 & 1, 1: f >> 5 & 1, 2: t >> 7 & 1}; vfl = {0: f >> 6 & 1, 1: f >> 4 & 1, 2: 0}
    pat = u16(0x4D0C0 + 2 * (z & 15)); h0 = z >> 4
    for i, w, (dx, dy) in zip(parts, defs, offsets(attr, parts, xy)):
        d = sdef(w)
        if not d: continue
        nc, nr = len(d['cols']), len(d['cols'][0])
        if z != 0xFF: dx = (dx * (z + 1)) >> 8; dy = (dy * (z + 1)) >> 8
        size = (nr * (z + 1) + 255) >> 8
        x = X + dx
        for k in range(nc):
            c = nc - 1 - k if hfl[i] else k
            col = d['cols'][c]
            if vfl[i]: col = col[::-1]
            cells = [(cl[0], cl[1] ^ hfl[i] ^ (vfl[i] << 1)) if cl else None for cl in col]
            h = h0 if (pat >> (15 - k % 16)) & 1 else h0 - 1
            x += draw_sprite(img, x, Y - dy, cells, h, z, size)

def vram_index_shrink(v, w=320, h=224, slots=None):
    """VRAM sprites -> pen-index image like vram_index, shrunk sprites included (hshrink, vshrink through L0)"""
    img = np.zeros((h, w), np.uint16); sx = sy = sh = 0; hs = 15; vs = 255
    for s in range(381):
        scb3 = v[0x8200 + s]; scb2 = v[0x8000 + s]
        if scb3 & 0x40: sx = (sx + hs + 1) & 0x1FF
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7; vs = scb2 & 0xFF
        hs = scb2 >> 8 & 15
        if not sh or (slots is not None and s not in slots): continue
        top = (496 - sy) & 0x1FF
        if top >= 0x100: top -= 0x200
        cells = []
        for r in range(32):
            code = v[s * 64 + 2 * r]; at = v[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            cells.append((code, at) if code else None)
        x = sx if sx < 0x1F0 else sx - 0x200
        draw_sprite(img, x, top, cells, hs, vs, min(sh, 32))
    return img
