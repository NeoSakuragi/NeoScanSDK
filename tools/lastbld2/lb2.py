#!/usr/bin/env python3
"""The Last Blade 2 (SNK 1998) fighter data from the P ROM (study /data/neogeo_dict/lastbld2/README.md).

P = 5 MB: the first MB at $000000, four 1 MB banks at $200000 (register $2FFFF0, read back at $2FFFEF: $2A776).
  animations   char table long $76134[char] (bank byte $76114[char] & 3: all 0) -> long [anim] offsets from the
               table -> the script ($2BA00: +$78 = script, +$7C = offset)
  script       words: bit 15 clear = a frame word (bits 0-11 frame id -> +$C6, bit 12 -> +$71 bit 3, bits 13-14
               flips); $FFFF = end (hold); else a command byte $80-$BF (handler table $762B4, length below) + args
               (interpreter $2BE36; the frame shows +$B7 ticks, set by command $81 [P ticks][S ticks]: Power / Speed)
  frames       bank 3, long $E40C[char] -> 8-byte records [frame]: [w0: bits 14-15 flips, bit 13 player-only,
               bits 0-11 sprite delta (bit 12 = minus)][x off][y off][w3: bit 15 = another layer: bits 12-14
               priority, bits 0-11 its frame id] ($E48C, up to 6 layers)
  sprites      bank 1 at $200008: [count][long offset per group] (group = char via $E5AC: Moriya 1); a group =
               [long index offset][word count]; index[sprite] long -> [w0: high byte palette add, low nibble format]
               [cols][rows][word] then the format's data ($D4B4, handlers $E14E: 0 / 1 word / byte masks + a long
               base tile counting up, 3 attr word + every cell's tile word, 7 / 8 word / byte masks + tile words,
               9 / 10 word / byte masks + tile low bytes under the attr word's high byte)"""
import struct, numpy as np

NEO = '/data/roms/lastbld2.neo'
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

def off(a, bank=0):
    a &= 0xFFFFFF
    if a < 0x100000: return a
    if 0x200000 <= a < 0x300000: return 0x100000 + bank * 0x100000 + (a - 0x200000)
    raise ValueError(hex(a))
def u8(a, b=0): return P[off(a, b)]
def s8(a, b=0): v = P[off(a, b)]; return v - 256 if v & 0x80 else v
def u16(a, b=0): return struct.unpack_from('>H', P, off(a, b))[0]
def s16(a, b=0): return struct.unpack_from('>h', P, off(a, b))[0]
def u32(a, b=0): return struct.unpack_from('>I', P, off(a, b))[0]

CHARS = ['kaede', 'moriya', 'yuki', 'okina', 'shigen', 'lee', 'kaori', 'zantetsu', 'shikyoh', 'juzoh', 'akari',
         'hyo', 'washizuka', 'genbu', 'byakko', 'suzaku', 'seiryu']          # (README: ids read in the select data)
MORIYA = 1

# ---- animation scripts ----
# command lengths (bytes incl. the command word), read from each handler's +$7C advance ($762B4[cmd & 63])
CMDLEN = {0x80: 2, 0x81: 4, 0x82: 2, 0x83: 6, 0x84: 14, 0x85: 10, 0x86: 4, 0x87: 4, 0x88: 4, 0x89: 2, 0x8A: 2,
          0x8B: 4, 0x8C: 2, 0x8D: 2, 0x8E: 2, 0x8F: 2, 0x90: 8, 0x91: 14, 0x92: 4, 0x93: 4, 0x94: 2, 0x95: 4,
          0x96: 2, 0x97: 2, 0x98: 2, 0x99: 22, 0x9A: 22, 0x9B: 14, 0x9C: 10, 0x9D: 14, 0x9E: 10, 0x9F: 2, 0xA0: 4,
          0xA1: 2, 0xA2: 4, 0xA3: 22, 0xA4: 2, 0xA5: 2, 0xA6: 4, 0xA7: 22, 0xA8: 22, 0xA9: 22, 0xAA: 22, 0xAB: 2,
          0xAC: 6, 0xAD: 10, 0xAE: 10, 0xAF: 10, 0xB0: 10, 0xB1: 10, 0xB2: 10, 0xB3: 10, 0xB4: 2, 0xB5: 8, 0xB6: 2,
          0xB7: 2, 0xB8: 4, 0xB9: 4, 0xBA: 2, 0xBB: 2, 0xBC: 2, 0xBD: 2, 0xBE: 2, 0xBF: 2}

def anim_table(char): return u32(0x76134 + 4 * (char & 31))
def anim_addr(char, anim):
    t = anim_table(char)
    return t + u32(t + 4 * anim, 0)

def nanims(char):
    """the table's length: the first script starts right after the offsets"""
    t = anim_table(char); first = min(u32(t + 4 * i) for i in range(4))
    return first // 4

def parse(char, anim, limit=400):
    """-> list of items: ('frame', off, fid, flags) / ('cmd', off, op, bytes) / ('end', off); stops at $FFFF or a
    restart ($9F)"""
    a0 = anim_addr(char, anim); a = a0; out = []
    for _ in range(limit):
        w = u16(a)
        if w == 0xFFFF: out.append(('end', a - a0)); break
        if not w & 0x8000:
            out.append(('frame', a - a0, w & 0xFFF, w >> 12)); a += 2; continue
        op = w >> 8 | 0x80 if False else (w >> 8) & 0xFF
        op = 0x80 | (op & 0x3F)
        n = CMDLEN[op]
        out.append(('cmd', a - a0, op, bytes(u8(a + k) for k in range(n))))
        a += n
        if op == 0x9F: break
    return out

def tick_of(cmd, mode=0):
    """$81: [81][Power ticks][Speed ticks][-] (EX: Speed unless +$194, $2C47A); the speed factor +$B4 = $100"""
    b = cmd[3]
    return b[1 + (1 if mode == 1 else 0)]

def steps(char, anim, mode=0):
    """the frames an animation shows: [(frame id, ticks, offset, commands before it)]; ticks from the last $81"""
    ticks = 1; out = []; pend = []
    for it in parse(char, anim):
        if it[0] == 'cmd':
            pend.append(it)
            if it[2] == 0x81: ticks = tick_of(it, mode)
        elif it[0] == 'frame':
            out.append(dict(fid=it[2], flags=it[3], ticks=ticks, off=it[1], cmds=pend)); pend = []
    return out

# ---- frames: layers ----
def frame_base(char): return u32(0xE40C + 4 * (char & 31))
def frame_layers(char, fid):
    """[(sprite id, x off, y off, flips, prio, player_only)] in drawing order ($E48C: the first record's sprite
    = fid + delta, each next layer's id from w3)"""
    out = []; base = frame_base(char); cur = fid; prio = 0; fl = 0
    for _ in range(6):
        a = base + 8 * cur
        w0, x, y, w3 = u16(a, 3), s16(a + 2, 3), s16(a + 4, 3), u16(a + 6, 3)
        fl ^= ((w0 >> 15) & 1) | ((w0 >> 13) & 2)           # roxl / rol / roxl: bit 15 -> 0, bit 14 -> 1; eor'd into
                                                             # the object's flip word: a layer's flips accumulate
        d = w0 & 0xFFF
        if w0 & 0x1000: d = -d
        out.append(dict(sid=(cur + d) & 0xFFFF, x=x, y=y, flips=fl, prio=prio, ponly=bool(w0 & 0x2000), raw=w0))
        if not w3 & 0x8000: break
        prio = (w3 >> 12) & 7; cur = w3 & 0xFFF
    return out

# ---- sprite definitions (bank 1) ----
SBASE = 0x200008
GROUP = list(range(17)) + [0, 4, 11] + list(range(20, 32))          # $E5AC
def sprite_def(char, sid):
    g = GROUP[char & 31]
    ga = SBASE + u32(SBASE + 2 + 4 * g, 1)
    idx = SBASE + u32(ga, 1); n = u16(ga + 4, 1)
    if sid >= n: return None
    d = SBASE + u32(idx + 4 * sid, 1)
    w0 = u16(d, 1)
    return dict(sid=sid, addr=d, fmt=w0 & 15, paladd=w0 >> 8, flags=w0 & 0xFF, cols=u8(d + 2, 1), rows=u8(d + 3, 1),
                w2=u16(d + 4, 1), data=d + 6)

def sprite_cells(sd):
    """-> cols x rows of (tile, attr nibble 4-7 replaced) or None, as the format handlers write SCB1 (unflipped)"""
    f, nc, nr, a = sd['fmt'], sd['cols'], sd['rows'], sd['data']
    U8 = lambda o: u8(o, 1); U16 = lambda o: u16(o, 1); U32 = lambda o: u32(o, 1)
    cells = [[None] * nr for _ in range(nc)]
    if f in (0, 4, 11, 12, 13, 14, 15, 1):      # long base tile, masks (0: words, 1: bytes), tile + 1 per set bit
        tile = U32(a); p = a + 4
        for c in range(nc):
            if f == 1: m = U8(p) << 8; p += 1
            else: m = U16(p); p += 2
            for r in range(nr):
                if m >> (15 - r) & 1: cells[c][r] = (tile & 0xFFFFF); tile += 1
    elif f == 3:                                # attr word (its nibble 4-7 = tile bits 16-19), a tile word per cell
        at = U16(a); p = a + 2
        for c in range(nc):
            for r in range(nr):
                cells[c][r] = U16(p) | ((at >> 4) & 15) << 16; p += 2
        return cells, at
    elif f in (7, 8, 9, 10):
        at = U16(a); p = a + 2
        hi = (at >> 4 & 15) << 16
        if f in (7, 9): masks = [U16(p + 2 * c) for c in range(nc)]; q = p + 2 * nc
        else: masks = [U8(p + c) << 8 for c in range(nc)]; q = p + nc + (nc & 1 if f == 8 else 0)
        for c in range(nc):
            for r in range(nr):
                if masks[c] >> (15 - r) & 1:
                    if f in (7, 8): t = U16(q); q += 2
                    else: t = (at & 0xFF00) | U8(q); q += 1
                    cells[c][r] = t | hi
        return cells, at
    else:
        raise ValueError(f'sprite format {f} not decoded')
    return cells, None

# ---- tiles / colours (the samsho2 neo2 decoder: .neo C = C1/C2 byte-interleaved) ----
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

def render_frame(char, fid, img, ox, oy, hflip=0, palbase=0, layers=None):
    """a frame drawn the way $E48C / $D4B4 place it: (ox, oy) = the object's screen point (x, feet line), the
    layers' x / y offsets (y down), H flip mirrors x as -(cols * 16 + x off); pen-index image palette * 16 + pen"""
    H, W = img.shape
    lay = layers or frame_layers(char, fid)
    order = sorted(range(len(lay)), key=lambda k: (-lay[k]['prio'], k))   # the display list: priority P0 - prio, ascending
    for L in [lay[k] for k in order]:
        sd = sprite_def(char, L['sid'])
        if sd is None or not sd['cols'] or not sd['rows']: continue
        cells, at = sprite_cells(sd)
        fl = L['flips'] ^ (hflip & 1)
        xo = L['x']; yo = L['y']
        x = ox + (-(sd['cols'] * 16 + xo) if fl & 1 else xo)
        y = oy + (-(sd['rows'] * 16 + yo) if fl & 2 else yo)
        pal = (palbase + sd['paladd']) & 0xFF
        cols = cells[::-1] if fl & 1 else cells
        for ci, col in enumerate(cols):
            col = col[::-1] if fl & 2 else col
            for ri, t in enumerate(col):
                if t is None or t == 0: continue
                tt = tile(t)
                if fl & 1: tt = tt[:, ::-1]
                if fl & 2: tt = tt[::-1]
                yy, xx = y + ri * 16, x + ci * 16
                ys, xs = slice(max(yy, 0), min(yy + 16, H)), slice(max(xx, 0), min(xx + 16, W))
                if ys.start >= ys.stop or xs.start >= xs.stop: continue
                sub = tt[ys.start - yy:ys.stop - yy, xs.start - xx:xs.stop - xx].astype(np.uint16)
                img[ys, xs] = np.where(sub > 0, (pal << 4) | sub, img[ys, xs])
    return img

def words(path):
    d = open(path, 'rb').read(); return struct.unpack(f'>{len(d) // 2}H', d)

def vram_index(v, w=320, h=224, slots=None):
    """VRAM sprites -> pen-index image (palette * 16 + pen) and the slot of each pixel; full-size slots only
    (SCB2 $0FFF; the others listed in `skipped`); screen row = sprite line (496 - SCB3 y) (samsho2/neo2.py)"""
    img = np.zeros((h, w), np.uint16); who = np.full((h, w), -1, np.int16); skipped = []
    sx = sy = sh = 0
    for s in range(1, 381):
        scb3 = v[0x8200 + s]
        if scb3 & 0x40: sx += 16
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7
        if slots is not None and s not in slots: continue
        if sh == 0: continue
        if v[0x8000 + s] & 0xFFF != 0x0FFF: skipped.append(s); continue
        top = (496 - sy) & 0x1FF
        for r in range(min(sh, 32)):
            code = v[s * 64 + 2 * r]; at = v[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            if code == 0: continue
            t = tile(code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            Y0 = top + r * 16
            for yy in range(16):
                Y = (Y0 + yy) & 0x1FF
                if Y >= h: continue
                row = t[yy]
                for xx in range(16):
                    X = (sx + xx) & 0x1FF
                    if X >= w or not row[xx]: continue
                    img[Y, X] = (at >> 8) * 16 + int(row[xx]); who[Y, X] = s
    return img, who, skipped
