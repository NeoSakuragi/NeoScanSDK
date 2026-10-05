#!/usr/bin/env python3
"""Samurai Shodown IV fighter data from the P ROM (see ../README.md).
  animations:  char table $1C14[char & 63] -> words[anim] (bit 15: bank 2 else bank 1, bit 14: slot + 1, bits 0-10 index);
               slot = byte $1CC4[char]; bank 1/2 $200000 + slot*4 -> offset of [count][offsets*2 ...]   (code $1AA0)
  steps:       [flags][ticks][sprite word x nlayers][x y bytes x nlayers][misc word: cmd bits 0-4][box word]
               [boxes 6 bytes x (n & 7) unless bit 4][extra word if bit 3][cmd args, size $29E0[cmd]]  (code $1CF0-$29DE)
  sprite word: group = bits 11-15, index = bits 0-10 -> bank 0 $200000 tables (code $1DB4)
Copied from the study (/data/neogeo_dict/samsho4/tools, README.md there) for tools/samsho4/export_ss4.py; steps_of and
step_index added."""
import neo
m = neo.Mem()
ARGSZ = [m.u8(0x29E0 + i) for i in range(32)]

_steps = {}
def steps_of(char, anim):
    """parsed steps of an animation (cached); [] when the slot is empty"""
    k = (char, anim)
    if k not in _steps:
        a, bank, w = anim_addr(char, anim)
        _steps[k] = parse_anim(a, bank) if a is not None else []
    return _steps[k]

def step_index(char, anim, ptr):
    """the step an object shows: +$4E points to the step after it (the step's 'addr' in parse_anim); None if not found"""
    p = ptr & 0xFFFFF
    for i, s in enumerate(steps_of(char, anim)):
        if s['addr'] & 0xFFFFF == p: return i
    return None

def anim_addr(char, anim):
    t = m.u32(0x1C14 + (char & 63 if (char & 63) <= 43 else 0) * 4)
    w = m.u16(t + 2 * anim)
    bank = 2 if w & 0x8000 else 1
    slot = m.u8(0x1CC4 + char) + (1 if w & 0x4000 else 0)
    base = 0x200000 + m.u32(0x200000 + slot * 4, bank)
    idx = w & 0x7FF
    if idx >= m.u16(base, bank): return None, bank, w
    return base + 2 * m.u16(base + 2 * idx, bank), bank, w

_ends = {}
def anim_end(addr, bank):
    """the next animation's start in the same bank table (animations have no terminator: ticks 0 = hold until the
    state code moves on, +$0E bit 1; the data runs on into the next steps)"""
    key = (bank, addr)
    if key not in _ends:
        starts = set()
        for slot in range(64):
            off = m.u32(0x200000 + slot * 4, bank)
            if not 0 < off < 0x100000: break
            base = 0x200000 + off; n = m.u16(base, bank)
            if n > 0x800: break
            starts.update(base + 2 * m.u16(base + 2 * i, bank) for i in range(n))
        _ends[bank] = sorted(starts)
    import bisect
    lst = _ends[bank]; i = bisect.bisect_right(lst, addr)
    return lst[i] if i < len(lst) else addr + 0x400

def sprite_def(word):
    """-> dict(fmt, cols, rows, addr) in bank 0"""
    g, i = word >> 11 & 31, word & 0x7FF
    T = 0x200000 + (m.u32(0x200000 + g * 4, 0) & 0xFFFFFE)
    D = 0x200000 + (m.u32(0x200000 + g * 4 + 128, 0) & 0xFFFFFE)
    if T + 4 * i >= D: return None
    e = m.u32(T + 4 * i, 0)
    return dict(word=word, fmt=e >> 28 & 15, rows=(e >> 24 & 15) + 1, cols=(e >> 19 & 31) + 1, addr=D + (e & 0x7FFFF))

def parse_anim(addr, bank, limit=200):
    """-> steps: dict(flags, ticks, layers [(sprite word, x, y)], misc, cmd, boxword, boxes [(b0,b1,x,y,w,h)], extra, args)
    stops at the next animation's start (anim_end)"""
    steps = []; a = addr; end = anim_end(addr, bank)
    s8 = lambda o: m.s8(o, bank)
    for _ in range(limit):
        if a >= end: break
        flags, ticks = m.u8(a, bank), m.u8(a + 1, bank); a += 2
        n = 1 + (flags >> 2 & 1) + (flags >> 3 & 1)
        words = [m.u16(a + 2 * k, bank) for k in range(n)]; a += 2 * n
        raw = [s8(a + k) for k in range(2 * n)]; a += 2 * n
        misc = m.u16(a, bank); a += 2
        # each offset = byte * 2 + the next misc bit from bit 15 down (roll #1 of the long whose high word is misc)
        v = [b * 2 + (misc >> (15 - k) & 1) for k, b in enumerate(raw)]
        offs = [(v[2 * k], v[2 * k + 1]) for k in range(n)]
        bw = m.u16(a, bank); a += 2
        boxes = None
        if bw & 7 and not bw & 0x10:
            boxes = [tuple(m.u8(a + 6 * k + j, bank) for j in range(6)) for k in range(bw & 7)]; a += 6 * (bw & 7)
        extra = None
        if bw & 8: extra = m.u16(a, bank); a += 2
        cmd = misc & 31
        args = bytes(m.u8(a + k, bank) for k in range(ARGSZ[cmd])); a += ARGSZ[cmd]
        steps.append(dict(addr=a, flags=flags, ticks=ticks, layers=[(w, x, y) for w, (x, y) in zip(words, offs)],
                          misc=misc, cmd=cmd, boxword=bw, boxes=boxes, extra=extra, args=args.hex()))
        if a >= end: break
    return steps

def sprite_cells(word):
    """sprite definition -> (sd, cols [[(tile, attr) | None] * rows]) as the format handlers write SCB1 (table $3B84,
    no-flip set; attr before the object's palette is added). None = a cell written as tile 0 / attr 0."""
    sd = sprite_def(word)
    if sd is None: return None, []
    f, nc, nr, a = sd['fmt'], sd['cols'], sd['rows'], sd['addr']
    u8 = lambda o: m.u8(o, 0); u16 = lambda o: m.u16(o, 0)
    cells = []
    if f in (0, 15, 13, 14):              # $3CC2: [tile][attr] per cell
        for c in range(nc):
            cells.append([(u16(a + 4 * (c * nr + r)), u16(a + 4 * (c * nr + r) + 2)) for r in range(nr)])
    elif f in (1, 3, 4, 10):              # first cell [tile][attr]; then 1: tile+attr byte (alternating), 3: tile word,
        t0, at0 = u16(a), u16(a + 2); p = a + 4; k = 0     # 4: tile low byte, 10: tile + 1 each cell
        tile, attr = t0, at0
        for c in range(nc):
            col = []
            for r in range(nr):
                if k:
                    if f == 1:
                        if k % 2: tile = u16(p); attr = at0 & 0xFF00 | u8(p + 2)
                        else: attr = at0 & 0xFF00 | u8(p); tile = u16(p + 1)
                        p += 3
                    elif f == 3: tile = u16(p); p += 2
                    elif f == 4: tile = t0 & 0xFF00 | u8(p); p += 1
                    else: tile = (tile + 1) & 0xFFFF
                col.append((tile, attr)); k += 1
            cells.append(col)
    elif f in (5, 6, 11, 12):             # masks (5/11 bytes, (cols+1)&~1 of them; 6/12 words), [tile][attr]; set bit =
        wide = f in (6, 12)                # a cell: 5/6 then read a byte into the tile low byte, 11/12 tile + 1
        nm = nc * 2 if wide else (nc + 1) & ~1
        masks = [u16(a + 2 * c) if wide else u8(a + c) << 8 for c in range(nc)]
        p = a + nm; tile, attr = u16(p), u16(p + 2); p += 4
        for c in range(nc):
            col = []
            for r in range(nr):
                if masks[c] >> (15 - r) & 1:
                    col.append((tile, attr))
                    if f in (5, 6): tile = tile & 0xFF00 | u8(p); p += 1
                    else: tile = (tile + 1) & 0xFFFF
                else: col.append(None)
            cells.append(col)
    else:
        raise ValueError(f'format {f} not decoded (handlers $3EC6 / $44E4 / $45F2 / $4774)')
    return sd, cells

# ---- rendering (pen-index images: value = palette * 16 + pen, 0 = transparent) ----
def layer_cells(word, hflip, vflip, pal_add):
    """cells as the flipped handlers write them: columns reversed for H, rows reversed for V, attr bits 0/1 toggled"""
    sd, cols = sprite_cells(word)
    if sd is None: return None, []
    out = []
    for col in (cols[::-1] if hflip else cols):
        col = col[::-1] if vflip else col
        out.append([None if c is None else (c[0], (c[1] + (pal_add << 8)) & 0xFFFF ^ (hflip | vflip << 1)) for c in col])
    return sd, out

def blit_cells(img, cells, x0, top):
    """cells -> img (2-D uint16 pen-index array) with the left column at x0 and the first row at top"""
    import numpy as np
    c = neo.load()[1]; H, W = img.shape
    for ci, col in enumerate(cells):
        for ri, cell in enumerate(col):
            if cell is None: continue
            tile, at = cell
            code = tile | (at >> 4 & 0xF) << 16
            if code == 0: continue
            t = neo.tile(c, code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            y, x = top + ri * 16, x0 + ci * 16
            ys, xs = slice(max(y, 0), min(y + 16, H)), slice(max(x, 0), min(x + 16, W))
            if ys.start >= ys.stop or xs.start >= xs.stop: continue
            sub = t[ys.start - y:ys.stop - y, xs.start - x:xs.stop - x].astype(np.uint16)
            v = ((at >> 8) << 4) | sub
            img[ys, xs] = np.where(sub > 0, v, img[ys, xs])

def render_step(img, step, ox, oy, obj_hflip=0, obj_vflip=0, pal=0, pal2=None, draw_layer2=True):
    """one animation step at the object position: (ox, oy) = screen x / sprite line of the object's origin
    (SCB4 x = ox + xoff, SCB3 y = 496 - oy + yoff; code $330A-$3560). Layer order: $59 bit 2 clear -> layer 0 first
    (below), else layers 1-2 first ($31BC); layer 2 uses palette +$55 only and blinks ($32A6)."""
    fl = step['flags']
    flips = [(fl >> 7 & 1, fl >> 6 & 1), (fl >> 5 & 1, fl >> 4 & 1), (fl >> 5 & 1, fl >> 4 & 1)]
    order = [0, 1, 2] if not (step['misc'] >> 5 & 4) else [1, 2, 0]
    for li in order:
        if li >= len(step['layers']): continue
        if li == 2 and not draw_layer2: continue
        w, xo, yo = step['layers'][li]
        hf, vf = flips[li][0] ^ obj_hflip, flips[li][1] ^ obj_vflip
        sd, cells = layer_cells(w, hf, vf, pal if li < 2 or pal2 is None else pal2)
        if sd is None: continue
        x = ox - (xo + sd['cols'] * 16) if obj_hflip else ox + xo
        yy = ~(yo - sd['rows'] * 16) & 0xFFFF if obj_vflip else yo
        if obj_vflip and yy & 0x8000: yy -= 0x10000         # (study copy: a negative offset without V flip was dropped)
        blit_cells(img, cells, x, oy - yy)

# ---- palettes ----
def fighter_palettes(char, mode=0, colour=0):
    """32 palettes (16 words each) loaded to $80-$9F (P1) / $A0-$BF (P2): index = word $1298[char*4 + mode*2 + colour],
    source $C0000 + index*32 (code $11CC / $121E -> queue $F862 -> copy $F7C8). mode = byte $108324/5 [inf: Slash / Bust],
    colour = byte $10832A/B (A / B)."""
    idx = m.u16(0x1298 + 2 * (char * 4 + mode * 2 + colour))
    base = 0xC0000 + idx * 32
    return [[m.u16(base + p * 32 + 2 * k) for k in range(16)] for p in range(32)]

def colorize(img, pals, first=0x80):
    """pen-index image -> RGB with palettes `pals` covering first..first+31 (transparent -> white)"""
    import numpy as np
    lut = np.full((4096, 3), 255, np.uint8)
    for p, pal in enumerate(pals):
        for k in range(1, 16): lut[(first + p) * 16 + k] = neo.color(pal[k])
    return lut[img]
