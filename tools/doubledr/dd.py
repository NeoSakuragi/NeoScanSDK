#!/usr/bin/env python3
"""Double Dragon (Technos 1995) ROM decoder: animations, steps, sprite definitions, tiles.
P = 2 MB (P1 $000000-$0FFFFF, the second MB at $200000, never switched). C = 14 MB.

Code (read in the disassembly, /data/tmp/dd95/p1.dis, p2.dis):
  animation step loader $20B1A, sprite definition walker $8440 (normal $84D4 / H-flipped $8626 column writers),
  SCB1 column copy jump tables $86D0 / $89D6, SCB2 zoom table $8C8E, sprite buffer -> VRAM copy $8000.
Object (fighters: P1 $10042A, P2 $10052A; a0 in the code): +$00 flags (bit 7 = screen-fixed), +$01 bit 4 facing,
  +$02 the step's attribute byte, +$03 palette, +$04 sprite definition word, +$06 x (16.16, world), +$0A y (16.16,
  world, down positive, floor 488), +$1B character, +$1C animation, +$1E step index, +$1F step flags, +$20 tick
  counter, +$22 previous definition, +$24 palette base, +$2C step word 3, +$39 animation flags,
  +$D8 / +$DA screen x / SCB3 y, +$DC / +$DD shrink x / y (0 = full size), +$DE / +$E0 the group's y / x offsets."""
import struct
import numpy as np
NEO = '/data/roms/doubledr.neo'
_c = {}

def load(path=NEO):
    if path in _c: return _c[path]
    raw = open(path, 'rb').read()
    sizes = struct.unpack('<6I', raw[4:0x1C]); off = 0x1000; reg = {}
    for name, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes):
        reg[name] = raw[off:off + sz]; off += sz
    p = bytearray(reg['P']); p[0::2], p[1::2] = reg['P'][1::2], reg['P'][0::2]
    assert bytes(p[0x100:0x107]) == b'NEO-GEO'
    _c[path] = (bytes(p), reg['C'], reg['M'], reg['V1']); return _c[path]

P, C, M, V = load()
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

# Characters: the object's +$1B; names from the sound test / ending credits tables, order = the palette base table
# $20C1E (12 entries) and the animation table $2C0000 (14 entries: 12 fighters + 2 extra sets)
NAMES = {}

# ---- animations ($20B1A): A = $2C0002 + 2 word[$2C0000 + 2 char]; animation n at A + word[A + 2n];
#      8-byte header [0][flags][..6] then 8-byte steps [left][attr][def w][ticks][b5][w6]; left = steps still to come
#      (0 = last step). The header's byte 1 is copied to +$39 (bit 4: ...).
ANIM_BASE = 0x2C0000
def anim_table(ch): return ANIM_BASE + 2 * u16(ANIM_BASE + 2 * ch) + 2
def anim_count(ch): return u16(anim_table(ch)) // 2
def anim_addr(ch, n): A = anim_table(ch); return A + u16(A + 2 * n)
def steps(ch, n, limit=64):
    """-> header bytes, [{'addr', 'left', 'attr', 'def', 'ticks', 'b5', 'w6'}]"""
    a = anim_addr(ch, n); hdr = P[off(a):off(a) + 8]; out = []
    s = a + 8
    for _ in range(limit):
        b = P[off(s):off(s) + 8]
        out.append(dict(addr=s, left=b[0], attr=b[1], def_=b[2] << 8 | b[3], ticks=b[4], b5=b[5], w6=b[6] << 8 | b[7]))
        if b[0] == 0: break
        s += 8
    return hdr, out

# ---- sprite definitions ($8440): w < $8000: ptr = long[$200020 + 4 w] (w < word[$200004]); data = [n w: low byte =
#      columns, high byte flags], then groups: [hdr w (bits 0-5 rows, bit 6 = sticky to the previous column)]
#      [rows x (code w, attr w)] and, after a group's FIRST column only, [y off w][x off w]; the next columns of the
#      group carry bit 6. Attr: low byte = code bits 16-19 << 4 | auto-anim << 2 | V << 1 | H; high byte = palette,
#      replaced by the object's +$03 when that is non-zero, in the FIRST group only ($8492: d2 is cleared after the
#      first group unless the palette is $FE): later groups keep their own palettes (effects drawn with the body).
#      Position ($84D4): SCB3 y = +$DA - y off (x zoom), SCB4 x = +$D8 + x off, columns 16 px apart.
def sdef(w):
    if w & 0x8000 or w >= u16(0x200004): return None
    p = u32(0x200020 + 4 * w)
    n = u16(p) & 0xFF; flags = u16(p) >> 8; p += 2
    cols = []; yo = xo = 0; k = 0; grp = -1
    while k < n:
        h = u16(p); rows = h & 63; p += 2
        tiles = [(u16(p + 4 * r), u16(p + 4 * r + 2)) for r in range(rows)]; p += 4 * rows
        if not (h & 0x40):
            yo, xo = s16(p), s16(p + 2); p += 4; gi = 0; grp += 1
        else: gi += 1
        cols.append(dict(rows=rows, tiles=tiles, yo=yo, xo=xo + 16 * gi, sticky=bool(h & 0x40), group=grp))
        k += 1
    return dict(flags=flags, cols=cols)

_tiles = {}
def tile(code):
    if code in _tiles: return _tiles[code]
    o = (code * 128) % len(C)
    b = np.frombuffer(C, np.uint8, 128, o).reshape(2, 16, 4)
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

def draw_def(w, pal_words, palette=None, hflip=False, size=(512, 512), origin=(256, 400), groups=None):
    """the definition at full size into an RGBA canvas; origin = (x, y) of the object's anchor (SCB4 x = +$D8,
    screen row = 496 - SCB3 y). hflip mirrors the columns about the anchor (the $8626 writer). -> RGBA array"""
    d = sdef(w); img = np.zeros((size[1], size[0], 4), np.uint8)
    if d is None: return img
    ox, oy = origin
    for c in d['cols']:
        if groups is not None and c['group'] not in groups: continue
        x = ox + (-(c['xo']) - 16 if hflip else c['xo']); top = oy + c['yo']
        for r, (code, at) in enumerate(c['tiles']):
            code |= (at >> 4 & 0xF) << 16
            if (code & 0xFFFF) == 0xFF and not (at >> 4 & 0xF): pass
            t = tile(code)
            h = bool(at & 1) ^ hflip
            if h: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            pn = palette if palette is not None and (c['group'] == 0 or palette == 0xFE) else at >> 8
            pl = np.array([color(pal_words[pn * 16 + k]) for k in range(16)], np.uint8)
            Y0 = top + 16 * r
            for yy in range(16):
                Y = Y0 + yy
                if not 0 <= Y < size[1]: continue
                row = t[yy]; m = row != 0
                xs = np.arange(x, x + 16)
                ok = m & (xs >= 0) & (xs < size[0])
                img[Y, xs[ok], :3] = pl[row[ok]]; img[Y, xs[ok], 3] = 255
    return img

# ---- VRAM side (proofs): the frame as the LSPC shows it, full-size slots only
def vram_words(b): return struct.unpack(f'>{len(b) // 2}H', b)
def slots_with_palette(v, pal):
    return {s for s in range(1, 381) if any(v[s * 64 + 2 * t + 1] >> 8 == pal and (v[s * 64 + 2 * t] != 0xFF or v[s * 64 + 2 * t + 1] & 0xF0) for t in range(32))}
def render_vram(v, pal_words, slots, w=320, h=224):
    img = np.zeros((h, w, 4), np.uint8); sx = sy = sh = 0
    for s in range(381):
        scb3 = v[0x8200 + s]
        if scb3 & 0x40: sx += 16
        else: sy, sh, sx = scb3 >> 7, scb3 & 63, v[0x8400 + s] >> 7
        if s not in slots or sh == 0: continue
        top = (496 - sy) & 0x1FF
        for r in range(min(sh, 32)):
            code = v[s * 64 + 2 * r]; at = v[s * 64 + 2 * r + 1]
            code |= (at >> 4 & 0xF) << 16
            t = tile(code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            pl = np.array([color(pal_words[(at >> 8) * 16 + k]) for k in range(16)], np.uint8)
            for yy in range(16):
                Y = (top + r * 16 + yy) & 0x1FF
                if not 0 <= Y < h: continue
                for xx in range(16):
                    X = (sx + xx) & 0x1FF
                    if X < w and t[yy, xx]: img[Y, X, :3] = pl[t[yy, xx]]; img[Y, X, 3] = 255
    return img

def fighter_fields(R, base):
    g = lambda o: R[base + o - 0x100000]
    w = lambda o: g(o) << 8 | g(o + 1)
    sw = lambda o: w(o) - 65536 if w(o) & 0x8000 else w(o)
    return dict(flags=g(0), dir=g(1), pal=g(3), def_=w(4), x=sw(6), y=sw(0xA), ch=g(0x1B), anim=w(0x1C), step=g(0x1E),
                sx=sw(0xD8), sy=sw(0xDA), zx=g(0xDC), zy=g(0xDD))

# ---- boxes ($26AC2 / $26AE8): set w (the step's word 3, object +$2C) at B = $2E0002 + 2 word[$2E0002 + 2 w]; 10-byte
#      records [type w][x][y][half w][half h] (centre + half extents, x in the art's facing = left, y up negative from
#      the feet); a set runs to the next set's start [inf]. type bit 7 attack ($81: +bit 0), bit 6 body / hurt,
#      bit 8 push [inf]; the attack record's byte 1: bits 2-3 -> +$E0 (hit height class), bits 0-1 -> +$E1 (reaction)
BOX_BASE = 0x2E0002
def boxes(w):
    a = BOX_BASE + 2 * dd_u16(BOX_BASE + 2 * w); b = BOX_BASE + 2 * dd_u16(BOX_BASE + 2 * (w + 1))
    n = max(0, min((b - a) // 10, 8)) if b > a else 1
    return [dict(type=u16(a + 10 * i), x=s16(a + 10 * i + 2), y=s16(a + 10 * i + 4), hw=s16(a + 10 * i + 6),
                 hh=s16(a + 10 * i + 8)) for i in range(n)]
def dd_u16(a): return u16(a)

# ---- move parameters (hit code $258EC..$25DB4):
#   category = (anim header byte 1 & $60) >> 5 (-> +$DF: 0 normal, 1 special, 2 / 3 stronger classes)
#   level    = (step attr & $30) >> 4 (0..3 = the button A..D of the command entry)
#   damage   = word[$266AA + 64 char + 8 category + 2 level] x ((104 - (D - D / 4) + def[victim]) >> 3), D = the
#              victim's damage-taken high byte, def = byte[$2669A + char]; KO when the victim's +$26 reaches $6800
#   gauge    = word[$266CA + 64 char + 8 category + 2 level] (the attacker's power, $254FE)
#   pushback = word[$2664A (hit) / $2662A (guarded) + 8 category + 2 level] / 256 px per frame
#   header   = [b0][b1 flags][vx w 8.8, art facing][vy w 8.8, up][b6: low nibble = friction shift][b7]; the velocity
#              is set once at the first step with attr bit 2, attr bit 3 clear -> v -= v >> shift every frame
DAMAGE, GAUGE, PUSH_HIT, PUSH_GUARD, DEFENCE = 0x266AA, 0x266CA, 0x2664A, 0x2662A, 0x2669A
def anim_params(ch, n, victim=2):
    h, st = steps(ch, n)
    cat = (h[1] & 0x60) >> 5
    vx = int.from_bytes(h[2:4], 'big', signed=True) / 256; vy = int.from_bytes(h[4:6], 'big', signed=True) / 256
    levels = sorted({(s['attr'] & 0x30) >> 4 for s in st})
    frames = sum(s['ticks'] + 1 for s in st)
    act = []; t = 0; prev = False
    for s in st:
        atk = any(b['type'] & 0x80 for b in boxes(s['w6']))
        if atk and not prev: act.append([t, t + s['ticks'] + 1])
        elif atk: act[-1][1] = t + s['ticks'] + 1
        prev = atk; t += s['ticks'] + 1
    lv = levels[-1] if levels else 0
    mult = (104 + u8(DEFENCE + victim)) >> 3
    base = u16(DAMAGE + 64 * ch + 8 * cat + 2 * lv)
    if not any(s['attr'] & 4 for s in st): vx = vy = 0      # no moving step: the header words are not velocities
    return dict(anim=n, cat=cat, level=lv, levels=levels, vx=vx, vy=vy, friction=h[6] & 15, steps=len(st),
                frames=frames, active=act, dmg_base=base, dmg_vs=base * mult, gauge=u16(GAUGE + 64 * ch + 8 * cat + 2 * lv),
                push=u16(PUSH_HIT + 8 * cat + 2 * lv) / 256, hdr=h.hex())
