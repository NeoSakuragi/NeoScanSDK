#!/usr/bin/env python3
"""World Heroes Perfect (ADK 1995) fighter data from the P ROM (the study: /data/neogeo_dict/whp/README.md).
Labels as there: [code] read in the disassembly, [meas] measured in our emulator, [inf] inferred.

  animations   [code $15448] global table long[$5D500] = $5D52C: one long per animation number; a fighter's animations
               are base + n, base = word $2D104[char] = $180 * (char + 1) (display object +$64)
  steps        [code $1568E] [def word < $FF00][long flags][command words < 0, with their argument bytes][ticks word]
               ($FFFD: a step without a new def; $FFFE [count][step]: loop; $FFFF: end; other $FFxx: [anim][step] go to)
               a step shows ticks + 1 frames [meas]; flags byte 2 bit 3 (long & $0800) = attack live [code $4BCA0]
  commands     [code $1568E] word -4k: handler long $1573C + 4k, argument bytes word $15552 + 4k; k 8 = attack box set
               (+$60F8), k 13 = pose by vertical speed (table long[$5D51C]), k 14 = a sub-animation (long[$5D520]:
               [def][ticks << 8] pairs, $FFxx: loop, ticks + 1 frames each)
  defs         [code $BC18 / $C1A6] long[$262800 + def] -> [x off w][y off w][cols-1][rows-1][type][mask size]
               [attr w][tile w][data ptr l]; offsets in 1/128 px (left = x - x off, top = y + y off above the feet);
               type 3: a mask per column (byte / word / long), a set bit = the next tile ($C3F0); type 2: a word per
               cell, a tile offset, $80xx pp = attr change (sticky), $C0xx = xx + 1 blank cells ($C39A)
  hurt boxes   [code $AD56 / $AE94] long[$242800 + def] -> 4-byte boxes [y][h][x][w] (signed bytes x 2 px; y = -top),
               0-terminated; box 0 is the broad box tested first, boxes 1.. the body
  attack boxes [code $4BCA0 / $B3C6] long[long[$200074] + 4 * set] -> [-top][height][x][width] words (1/128 px),
               0-terminated
  palettes     [code $D600, meas] the palette RAM image $1000 + 32 * palette: Hanzou $10 (colour A), $11 (colour B
               [inf: the navy costume]); effects $80, $8A, $9E, $08"""
import neo_whp as neo
m = neo.Mem()
ANIMS = m.u32(0x5D500)
SUBS = m.u32(0x5D520)
CMD_ARGS = {k: m.u16(0x15552 + 4 * k) for k in range(48)}
BLANK = 0x000C                                    # the 1x1 empty def (flickering objects, the collision object)

def base(char): return m.u16(0x2D104 + 2 * char)
def anim_addr(char, rel): return m.u32(ANIMS + 4 * (base(char) + rel))

_steps = {}
def steps_of(char, rel):
    """parsed steps of an animation (cached): dict(addr, defw (None: keeps the previous one), flags, cmds [(k, args)],
    ticks, box (the attack box set live from cmd 8, None before)); the list ends with a control entry (ctrl 'end' /
    'loop' / 'goto')"""
    k = (char, rel)
    if k in _steps: return _steps[k]
    a = anim_addr(char, rel); out = []; last_def = None; box = None
    for _ in range(200):
        start = a
        w = m.u16(a); a += 2
        if w >= 0xFF00:
            if w == 0xFFFD: d = last_def
            elif w == 0xFFFF: out.append(dict(addr=start, ctrl='end')); break
            elif w == 0xFFFE: out.append(dict(addr=start, ctrl='loop', count=m.u8(a), step=m.u8(a + 1))); break
            else:
                an = m.u16(a); out.append(dict(addr=start, ctrl='goto', anim=None if an == 0xFFFF else an, step=m.u16(a + 2))); break
        else: d = w
        last_def = d
        fl = m.u32(a); a += 4
        cmds = []
        while True:
            c = m.s16(a); a += 2
            if c >= 0: ticks = c & 0xFF; break
            kk = -c // 4; n = CMD_ARGS.get(kk, 0)
            args = bytes(m.u8(a + i) for i in range(n)); a += n
            cmds.append((kk, args.hex()))
            if kk == 8: box = int.from_bytes(args, 'big')
        out.append(dict(addr=start, ctrl=None, defw=d, flags=fl, cmds=cmds, ticks=ticks, box=box))
    _steps[k] = out
    return out

def sub_steps(n):
    """sub-animation n (command 14): [(def, ticks)] and the loop control word"""
    a = m.u32(SUBS + 4 * n); out = []
    for _ in range(64):
        d = m.u16(a); a += 2
        if d >= 0xFF00: return out, d
        t = m.s16(a); a += 2
        while t < 0: t = m.s16(a); a += 2
        out.append((d, t >> 8))
    return out, None

def sprite_def(w):
    a = m.u32(0x262800 + w)
    return dict(addr=a, xoff=m.s16(a), yoff=m.s16(a + 2), cols=m.u8(a + 4) + 1, rows=m.u8(a + 5) + 1, type=m.u8(a + 6),
                msize=m.u8(a + 7), attr=m.u16(a + 8), tile=m.u16(a + 10), ptr=m.u32(a + 12))

def def_cells(w):
    """-> (sd, cols [[(tile code, attr) | None] * rows]) as the type handler writes SCB1 (unflipped)"""
    sd = sprite_def(w)
    if sd['type'] == 2: return sd, type2_cells(sd)
    if sd['type'] != 3: raise ValueError(f'def {w:04X}: type {sd["type"]} not decoded')
    nb = (1, 2, 4)[sd['msize']]; p = sd['ptr']; tile = sd['tile']; at = sd['attr']; cols = []
    for c in range(sd['cols']):
        mask = int.from_bytes(bytes(m.u8(p + i) for i in range(nb)), 'big'); p += nb
        col = []
        for r in range(sd['rows']):
            if mask >> (nb * 8 - 1 - r) & 1:
                col.append(((tile | (at >> 4 & 0xF) << 16), at)); tile = (tile + 1) & 0xFFFF
            else: col.append(None)
        cols.append(col)
    return sd, cols

def type2_cells(sd):
    p = sd['ptr']; base_t = sd['tile']; at = sd['attr']; cols = []
    for c in range(sd['cols']):
        col = []
        while len(col) < sd['rows']:
            b = m.u8(p)
            if b & 0xC0 == 0xC0:
                n = (m.u16(p) & 0xFF) + 1; p += 2
                col.extend([None] * n); del col[sd['rows']:]
                continue
            if b & 0x80:
                at = ((sd['attr'] ^ (b & 0x3F)) + (m.u8(p + 1) << 8)) & 0xFFFF; p += 2
            tile = (base_t + m.u16(p)) & 0xFFFF; p += 2
            col.append((tile | (at >> 4 & 0xF) << 16, at))
        cols.append(col)
    return cols

def hurt_boxes(w):
    """the def's body boxes (box 0, the broad box, left out): [(top, height, x, width)] px, top above the feet,
    x forward (facing right)"""
    a = m.u32(0x242800 + w); out = []
    if not a or m.u8(a) == 0: return out
    a += 4
    while m.u8(a):
        y, h, x, ww = (m.s8(a + i) for i in range(4))
        out.append((-2 * y, 2 * h, 2 * x, 2 * ww)); a += 4
    return out

def attack_boxes(n):
    """attack box set n: [(top, height, x, width)] px (top above the feet, x forward facing right)"""
    if n is None: return []
    a = m.u32(m.u32(0x200074) + 4 * n); out = []
    for _ in range(16):
        d1 = m.s16(a)
        if d1 == 0: break
        out.append((-d1 / 128, m.s16(a + 2) / 128, m.s16(a + 4) / 128, m.s16(a + 6) / 128)); a += 8
    return out

def palette(n):
    """palette n as the game loads it (RAM image $1000 + 32 n)"""
    return [m.u16(0x1000 + 32 * n + 2 * k) for k in range(16)]

# ---- rendering (pen-index images: palette * 16 + pen, 0 = transparent) ----
def blit_cells(img, cells, x0, top):
    import numpy as np
    c = neo.load()[1]; H, W = img.shape
    for ci, col in enumerate(cells):
        for ri, cell in enumerate(col):
            if cell is None: continue
            code, at = cell
            if not code & 0xFFFFF: continue
            t = neo.tile(c, code)
            if at & 1: t = t[:, ::-1]
            if at & 2: t = t[::-1]
            y, x = top + ri * 16, x0 + ci * 16
            ys, xs = slice(max(y, 0), min(y + 16, H)), slice(max(x, 0), min(x + 16, W))
            if ys.start >= ys.stop or xs.start >= xs.stop: continue
            sub = t[ys.start - y:ys.stop - y, xs.start - x:xs.stop - x].astype(np.uint16)
            img[ys, xs] = np.where(sub > 0, ((at >> 8) << 4) | sub, img[ys, xs])

def render_def(img, w, X, Y, hflip=0, pal_add=0, offs=None):
    """def w at object position X, Y (object words +$02 / +$00, 1/128 px, Y up) as the game draws it [code $BC38-$BDF4,
    meas]: left = (X - x off) / 128 - 128, top = 352 - (Y + y off) / 128; H flip ($BDFA): columns right to left, cells
    H-flipped, left = (X + x off) / 128 - 128 - 16 cols + 1. offs: the object's own offsets (+$14 / +$16), used instead of
    the def's when the object's +$21 bit 0 is clear ($BC22: the hit shake moves x off by +-1 px)"""
    sd, cols = def_cells(w)
    if offs is not None: sd = dict(sd, xoff=offs[0], yoff=offs[1])
    cols = [[None if c is None else (c[0], (c[1] + (pal_add << 8)) & 0xFFFF) for c in col] for col in cols]
    top = 352 - ((Y + sd['yoff']) >> 7)
    if hflip:
        cols = [[None if c is None else (c[0], c[1] ^ 1) for c in col] for col in cols[::-1]]
        left = ((X + sd['xoff']) >> 7) - 128 - sd['cols'] * 16 + 1
    else:
        left = ((X - sd['xoff']) >> 7) - 128
    blit_cells(img, cols, left, top)
    return sd
