#!/usr/bin/env python3
"""Final Fight (CPS1, World 900112 'ffight') ROM decoder: program, graphics, palettes, animations, frames, boxes.

Study: /data/study/ffight/REPORT.md + ffight_framedata.json (frame data, harness /data/emu/harness/lr.py), prog.asm.
Everything below is read from the ROM set /data/emu/roms/cps1/ffight.zip:
- program: ff_36.11f / ff_42.11h (even / odd bytes, 0x00000), ff_37.12f / ffe_43.12h (0x40000), ff-32m.8h (0x80000,
  byte-swapped words) -> 1 MB, equal to /data/study/ffight/rom/prog.bin.
- graphics: ff-5m.7a / ff-7m.9a / ff-1m.3a / ff-3m.5a, ROM_LOAD64_WORD (64-bit groups, 2 bytes of each), 16x16 4bpp
  tiles of 128 bytes: a row = 8 bytes, bytes 0-3 the left 8 pixels, 4-7 the right 8, byte k = plane k (pen bit k),
  MSB = leftmost. Sprite code = tile number (2 MB = $4000 tiles). Pen 15 = transparent.
- animation ($3AE2): an entry = [s16 offset to its frame record from the entry][t ticks][at: game flag, $FF = the
  move's end]; t >= $80 = jump: entry += offset (the loop); the next entry after t ticks ($3B02).
- frame record ($168CC draw, $3AE2 load): b0 draw mode (x4 index: 4 = one attr for every tile, 8 = a tile + attr
  pair each), b2 shape (table $646A2: 8 bytes [n][0][ptr -> n (dx, dy) pairs: the first absolute, then steps]),
  b4 body box, b5 attack box, w6 x offset (fp@48), w8 height (raises the sprite), w10 attr (pal bits 0-4, x flip
  bit 5, y flip bit 6), then n tile words ($FFFF = none) [mode 8: tile, attr].
  Screen: tile x = X + w6 + dx (facing right = the art as drawn; facing left: mirrored about X, flip toggled),
  tile top y = feet - w8 + dy.
- boxes: per fighter table (study movetable.BOX) 16 bytes a record; body index b4, attack b5 (bit 7 = none)."""
import io, os, struct, zipfile
ZIP = '/data/emu/roms/cps1/ffight.zip'
_P = _G = None
CAST = {'guy': 0, 'cody': 1, 'haggar': 2}           # the player id byte (a6@(20)): the set-anim tables' order

def load():
    global _P, _G
    if _P is None:
        z = zipfile.ZipFile(ZIP); r = lambda n: z.read(n)
        p = bytearray(0x100000)
        for base, ev, od in ((0, 'ff_36.11f', 'ff_42.11h'), (0x40000, 'ff_37.12f', 'ffe_43.12h')):
            e, o = r(ev), r(od); p[base:base + 2 * len(e):2] = e; p[base + 1:base + 2 * len(o):2] = o
        w = r('ff-32m.8h'); p[0x80000:0x100000:2] = w[1::2]; p[0x80001:0x100000:2] = w[0::2]
        _P = bytes(p)
        roms = [r(n) for n in ('ff-5m.7a', 'ff-7m.9a', 'ff-1m.3a', 'ff-3m.5a')]
        g = bytearray(0x200000)
        for k, rm in enumerate(roms):
            for i in range(0, len(rm), 2): g[(i // 2) * 8 + 2 * k:(i // 2) * 8 + 2 * k + 2] = rm[i:i + 2]
        _G = bytes(g)
    return _P, _G

def u8(a): return load()[0][a]
def u16(a): return struct.unpack('>H', load()[0][a:a + 2])[0]
def s16(a): v = u16(a); return v - 65536 if v & 0x8000 else v
def u32(a): return struct.unpack('>I', load()[0][a:a + 4])[0]
def s8(v): return v - 256 if v & 0x80 else v

def tile_pixels(code):
    """16x16 pens (rows of 16) of graphics tile `code`"""
    g = load()[1]; o = (code & 0x3FFF) * 128; out = []
    for y in range(16):
        row = []
        for half in (0, 4):
            b = g[o + 8 * y + half:o + 8 * y + half + 4]
            for x in range(8):
                m = 0x80 >> x
                row.append((1 if b[0] & m else 0) | (2 if b[1] & m else 0) | (4 if b[2] & m else 0) | (8 if b[3] & m else 0))
        out.append(row)
    return out

PAL_BASE = 0xC0000                                    # the sprite palettes (32 x 16 words) the game uploads to $914000
def palette(p, base=PAL_BASE):
    return [u16(base + 32 * p + 2 * k) for k in range(16)]

def cps_rgb(w):
    """CPS1 colour word (brightness, R, G, B nibbles) -> RGB888 (MAME cps1: bright = $0F + 2 * nibble, / $2D)"""
    br = 0x0F + ((w >> 12) << 1)
    return tuple(min(255, ((w >> s) & 15) * 0x11 * br // 0x2D) for s in (8, 4, 0))

SHAPES = 0x646A2
def shape(i):
    a = SHAPES + 8 * i; n = u16(a); p = u32(a + 4)
    return [(s16(p + 4 * k), s16(p + 4 * k + 2)) for k in range(n)]

def frame(fa):
    """frame record at fa -> dict(mode, shape, body, atk, xoff, h, attr, tiles=[(code, attr, x, y)]) relative to the
    feet facing right as the art is drawn: x right, y down from the feet (y negative = up)"""
    mode, sh = u8(fa), u8(fa + 2)
    d = {'addr': fa, 'mode': mode, 'shape': sh, 'b1': u8(fa + 1), 'b3': u8(fa + 3), 'body': u8(fa + 4), 'atk': u8(fa + 5),
         'xoff': s16(fa + 6), 'h': s16(fa + 8), 'attr': u16(fa + 10), 'tiles': []}
    offs = shape(sh); x = d['xoff']; y = -d['h']
    p = fa + 12
    for k, (dx, dy) in enumerate(offs):
        x += dx; y += dy
        code = u16(p); p += 2
        at = d['attr']
        if mode == 8: at = u16(p); p += 2
        if code & 0x8000: continue
        d['tiles'].append((code, at, x, y))
    d['end'] = p
    return d

MODES_OK = (4, 8)
def valid_frame(fa):
    if fa < 0x400 or fa > 0xFFF00 or fa & 1: return False
    if u8(fa) not in MODES_OK or u8(fa + 1) != 0: return False
    sh = u8(fa + 2)
    n = u16(SHAPES + 8 * sh); p = u32(SHAPES + 8 * sh + 4)
    if not (0 < n <= 120) or u16(SHAPES + 8 * sh + 2) != 0 or not (0x60000 <= p < 0xFFFFF): return False
    return True

def anim(a, limit=200):
    """animation at a -> [(entry, frame addr, ticks, at)], loop index (the entry a jump goes to) or None"""
    out, seen, e = [], {}, a
    for _ in range(limit):
        if e in seen: return out, seen[e]
        off, t, at = s16(e), u8(e + 2), u8(e + 3)
        if t & 0x80:
            e = e + off
            if e in seen: return out, seen[e]
            continue
        seen[e] = len(out)
        out.append((e, e + off, t, at))
        if at == 0xFF: return out, None
        e += 4
    return out, None

def valid_anim(a):
    if a & 1 or not (0x400 <= a < 0xFFF00): return False
    try:
        ents, lp = anim(a, 80)
    except Exception: return False
    if not ents or len(ents) >= 80: return False
    return all(valid_frame(f) and 0 < t < 0x80 for _, f, t, _ in ents)

# set-anim call sites: `movel pc@(6,d0:w),a1; jmp/jsr $3AE2` followed by one long per player id (Guy, Cody, Haggar),
# `... $3AD6` (a word table of anims by direction byte fp@(54), relative to the table)
def set_anim_tables():
    P = load()[0]; out = []
    for pat in (bytes.fromhex('227b00064ef83ae2'), bytes.fromhex('227b00064eb83ae2')):
        i = P.find(pat)
        while i >= 0:
            out.append((i, [u32(i + 8 + 4 * k) for k in range(3)])); i = P.find(pat, i + 1)
    return out

# boxes ($328A): the fighter's box table fp@(56) (BOXES): body record = base + 8 * b4, attack record = base + word 0 +
# 16 * (b5 & $7F) (b5 bit 7: only while on the ground, fp@(14) == fp@(10)); a record = [cx][cy][hw][hh] words, centre
# from the feet (x forward as the art faces = right, y UP), half extents ($78F4: |d| <= hw1 + hw2); an attack record
# goes on: +8 its damage index (study movetable.DMG), more hit data
BOXES = {'guy': 0x10B32, 'cody': 0x128CC, 'haggar': 0x14CB6}   # fp@(56) [meas]
DMG = {'guy': 0x1101A, 'cody': 0x12BA0, 'haggar': 0x14F6E}     # fp@(92): damage by the attack record's word 4 [meas, study]
def boxes(f, name=None):
    """{'body': (cx, cy, hw, hh), 'atk': ...} of frame dict f (the fighter told by its palette when not given)"""
    name = name or {0: 'guy', 1: 'cody', 2: 'haggar'}.get(f['attr'] & 31)
    if name is None: return {}
    base = BOXES[name]; out = {}
    if f['body']: a = base + 8 * f['body']; out['body'] = tuple(s16(a + 2 * k) for k in range(4))
    if f['atk']:
        a = base + u16(base) + 16 * (f['atk'] & 0x7F); out['atk'] = tuple(s16(a + 2 * k) for k in range(4))
    return out

def atk_record(name, b5):
    base = BOXES[name]; a = base + u16(base) + 16 * (b5 & 0x7F)
    return [u16(a + 2 * k) for k in range(8)]

REGIONS = {'guy': (0xF600, 0x111B6), 'cody': (0x111B6, 0x12CFC), 'haggar': (0x12CFC, 0x14BD0)}   # his anims + frames
PAL = {'guy': 0, 'cody': 1, 'haggar': 2}            # his palette (attr bits 0-4 of his frames; $C0000 + 32 n)

def region_anims(name):
    """every animation head in the fighter's region: an entry run's start (a valid anim) + the set-anim tables'"""
    a, b = REGIONS[name]; heads = []
    p = a; inrun = False
    while p < b:
        off, t = s16(p), u8(p + 2)
        isent = (t & 0x80 and -0x400 < off < 0) or (t < 0x80 and valid_frame(p + off) and a <= p + off < b + 0x400)
        if isent and not inrun and valid_anim(p): heads.append(p)
        if isent: inrun = True; p += 4; continue
        if valid_frame(p): p = frame(p)['end']; inrun = False; continue
        inrun = False; p += 2
    k = CAST[name]
    for _, l in set_anim_tables():
        if l[k] not in heads and valid_anim(l[k]): heads.append(l[k])
    return sorted(heads)

def region_frames(name):
    fr = set()
    for h in region_anims(name):
        for _, f, _, _ in anim(h)[0]: fr.add(f)
    return sorted(fr)
