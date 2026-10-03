"""KOF96 / KOF98 ROM access from the .neo files (KOF96: P = 1 MB P1 + 2 MB P2; KOF98: P = 2 MB P1 + 4 MB P2).

CPU view: $000000-$0FFFFF = P1; $200000-$2FFFFF = one 1 MB bank (bank n = .neo P bytes (n+1) MB on), selected by
writing n to $2FFFFE (the word at $200000 is the bank number). Same engine family (KOF95 -> 96 -> 98, see
tools/kof95/README.md); what moved is described per game in GAMES:
  KOF96: animations $080000[id] (P1), one state->slot map shared by every character ($78624[remap $5C2C[id]]),
         frame records $23C008[id] + index*6 and sprite definitions $26C000[id] in bank 0, default bank 1.
  KOF98: animations bank 2 $200002[id], a state->slot map per character ($B9536[id] -> words), frame records
         bank 1 $200002[id] + index*6, sprite definitions bank 1 $240000[id], default bank 2 (engine $5BB0, $5DA2)."""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'neosdk'))

GAMES = {
    'kof96': {'neo': os.environ.get('KOF96_NEO', '/data/roms/kof96.neo'), 'bank': 1, 'anims': 0x080000,
              'frames': (0x23C008, 0), 'sdefs': (0x26C000, 0), 'map': 'shared'},
    'kof98': {'neo': os.environ.get('KOF98_NEO', '/data/roms/kof98.neo'), 'bank': 2, 'anims': 0x200002,
              'frames': (0x200002, 1), 'sdefs': (0x240000, 1), 'map': 0xB9536},
    # KOF99: KOF98's layout; banks are selected through the SMA chip ($2FFFF0, scrambled value -> MAME's
    # kof99 bankoffset table), and the engine's banks 1 and 2 are the plain 1 MB banks. State map $C1BCC.
    # KOF97: KOF98's layout (banks 1 / 2 as KOF98, found by probing the bank words and tables); state map $AFBCA
    # (the same code as KOF98's $5DAC map access, at $5A48); sprite definitions bank 1 $250000 (code $5A6E)
    'kof97': {'neo': os.environ.get('KOF97_NEO', '/data/roms/kof97.neo'), 'bank': 2, 'anims': 0x200002,
              'frames': (0x200002, 1), 'sdefs': (0x250000, 1), 'map': 0xAFBCA},
    'kof99': {'neo': os.environ.get('KOF99_NEO', '/data/roms/kof99.neo'), 'bank': 2, 'anims': 0x200002,
              'frames': (0x200002, 1), 'sdefs': (0x240000, 1), 'map': 0xC1BCC},
}
NEO = GAMES['kof96']['neo']

def load(path=NEO):
    raw = open(path, 'rb').read()
    sizes = struct.unpack('<6I', raw[4:0x1C]); off = 0x1000; reg = {}
    for name, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes):
        reg[name] = raw[off:off + sz]; off += sz
    p = bytearray(reg['P']); p[0::2], p[1::2] = reg['P'][1::2], reg['P'][0::2]
    assert bytes(p[0x100:0x107]) == b'NEO-GEO'
    return bytes(p), reg['C']

class Mem:
    """CPU-address reads with the P2 bank (default: the game's normal bank)"""
    def __init__(self, prom, game='kof96'):
        self.p = prom; self.game = game; self.g = GAMES[game]; self.bank = self.g['bank']
    def off(self, a, bank=None):
        if a < 0x100000: return a
        if 0x200000 <= a < 0x300000: return 0x100000 + (self.bank if bank is None else bank) * 0x100000 + (a - 0x200000)
        raise ValueError(hex(a))
    def u8(self, a, bank=None): return self.p[self.off(a, bank)]
    def u16(self, a, bank=None): return struct.unpack_from('>H', self.p, self.off(a, bank))[0]
    def s16(self, a, bank=None): return struct.unpack_from('>h', self.p, self.off(a, bank))[0]
    def u32(self, a, bank=None): return struct.unpack_from('>I', self.p, self.off(a, bank))[0]
    def p2(self): return self.p[0x100000:0x300000]          # neosdk's p2rom (bank 0 first)

def anim_addr(m, cid, slot): return m.u32(m.u32(m.g['anims'] + cid * 4) + slot * 4)
def state_slot(m, cid, state):
    if m.g['map'] == 'shared': return m.u16(m.u32(0x78624 + m.u16(0x5C2C + cid * 2) * 4) + state * 2)
    return m.u16(m.u32(m.g['map'] + cid * 4) + state * 2)
def frame_record(m, cid, index): t, b = m.g['frames']; return m.u32(t + cid * 4, bank=b) + index * 6
def sdef_table(m, cid): t, b = m.g['sdefs']; return m.u32(t + cid * 4, bank=b)
def frame_bank(m): return m.g['frames'][1]

def sdef(m, cid, idx):
    """KOF96 sprite definition (renderer at $5254, format handlers via the jump table at $54E0), bank 0.
    Header [palette offset][format][columns][rows], then per format; returns {'pal': offset, 'cols': [[tile|None]*rows]}.
    Tile codes are 20 bits: bits 16-19 come from an attribute byte (bits 4-7) or the base."""
    B = m.g['sdefs'][1]
    a = m.u32(sdef_table(m, cid) + idx * 4, bank=B)
    pal, fmt, ncol, nrow = m.u8(a, B), m.u8(a + 1, B), m.u8(a + 2, B), m.u8(a + 3, B)
    if m.u16(a + 2, B) == 0: return {'pal': pal, 'format': fmt, 'cols': []}
    p = a + 4
    u8 = lambda o: m.u8(o, B); u16 = lambda o: m.u16(o, B)
    cols = []
    def masks(width):
        nonlocal p
        out = []
        for c in range(ncol):
            out.append(u16(p) if width == 16 else u8(p) << 8); p += 2 if width == 16 else 1
        return out
    def bits(mask): return [(mask >> (15 - r)) & 1 for r in range(nrow)]
    if fmt in (0, 4, 1):
        base = (u16(p) & 0xF) << 16 | u16(p + 2); p += 4; n = 0
        for mk in masks(16 if fmt != 1 else 8):
            col = []
            for b in bits(mk):
                col.append(base + n if b else None); n += b
            cols.append(col)
    elif fmt in (2, 3):
        hi = 0
        if fmt == 3: hi = (u16(p) & 0xF0) << 12; p += 2
        k = 0
        for c in range(ncol):
            col = []
            for r in range(nrow):
                if fmt == 3: col.append(hi | u16(p)); p += 2
                else:
                    if k % 2 == 0: lo = u16(p); h = u8(p + 2); p += 3
                    else: h = u8(p); lo = u16(p + 1); p += 3
                    col.append((h & 0xF0) << 12 | lo); k += 1
            cols.append(col)
    elif fmt in (5, 6):
        mk = masks(16 if fmt == 5 else 8)
        if fmt == 6 and p & 1: p += 1
        k = 0
        for c in range(ncol):
            col = []
            for b in bits(mk[c]):
                if not b: col.append(None); continue
                if k % 2 == 0: lo = u16(p); h = u8(p + 2); p += 3     # same alternation as format 2: code first
                else: h = u8(p); lo = u16(p + 1); p += 3
                col.append((h & 0xF0) << 12 | lo); k += 1
            cols.append(col)
    elif fmt in (7, 8):
        hi = (u16(p) & 0xF0) << 12; p += 2
        mk = masks(16 if fmt == 7 else 8)
        if fmt == 8 and p & 1: p += 1
        for c in range(ncol):
            col = []
            for b in bits(mk[c]):
                if b: col.append(hi | u16(p)); p += 2
                else: col.append(None)
            cols.append(col)
    elif fmt in (9, 10):
        base = u16(p); p += 2; hi = (base & 0xF0) << 12
        mk = masks(16 if fmt == 9 else 8)
        for c in range(ncol):
            col = []
            for b in bits(mk[c]):
                if b: col.append(hi | (base & 0xFF00) | u8(p)); p += 1
                else: col.append(None)
            cols.append(col)
    else:
        raise ValueError(f'sprite format {fmt}')
    return {'pal': pal, 'format': fmt, 'cols': cols}

def frame_parts(m, cid, index):
    """frame record parts: [x][y][word]; word bits 0-9 sprite definition, 13 = another part follows, 14/15 = H/V flip"""
    a = frame_record(m, cid, index); out = []
    for _ in range(16):
        B = frame_bank(m); x, y, w = m.s16(a, B), m.s16(a + 2, B), m.u16(a + 4, B)
        out.append({'dx': x, 'dy': y, 'sdef': w & 0x3FF, 'hflip': (w >> 15) & 1, 'vflip': (w >> 14) & 1})
        if not (w >> 13) & 1: break
        a += 6
    return out

def parse_anim(m, addr, limit=300):
    """-> (steps [(ticks, frame index, flags, boxes, raw index, dx)], 'loop'|'hold'). Step = [ticks][byte][index:16][flags:16];
    commands (b0 >= $80): $FF loop, $FE hold, $FD box [slot | type<<2][x][y][w][h] (handler $4EF8), $FB move [00][x:16][00 00]
    (the object's x moves by x px, sprite orientation: negative = forward; applied as the next step starts, KOF98 Terry
    C+D measured in MAME), others skipped. raw index = the engine's +$74 / 6 (commands count). dx = the moves before
    the step, summed."""
    steps, boxes, attack, dx = [], {}, {}, 0
    for i in range(limit):
        a = addr + 6 * i
        b0, b1 = m.u8(a), m.u8(a + 1)
        if b0 == 0xFF: return steps, 'loop'
        if b0 == 0xFE: return steps, 'hold'
        if b0 >= 0x80:
            if b0 == 0xFB:                         # move: signed x (byte 1 and bytes 4-5 are 0 in every KOF98 normal)
                v = m.u16(a + 2); dx += v - 0x10000 if v & 0x8000 else v
            if b0 == 0xFD:                         # box: byte 1 bits 0-1 = slot (object +$90 + slot*5), bits 2-7 = type;
                slot = b1 & 3                      # slot 0 = attack box (live on the next step), 1-3 hurtboxes
                # stored with KOF95-style keys: first hex digit 1 = attack, 3 = hurt. The attack type runs 0-63
                # (KOF96/98/99 census 2026-10-03): types 0-15 keep their two-digit keys '10'-'1F', types 16-63 get
                # three digits '110'-'13F' (0x100 | type; 0x10 | type read types 32-63 as hurt keys '3x': Krauser's
                # dropkick, Ryo's Ko-hou never hit). Tell kinds apart by the key's first character
                t = b1 >> 2
                key = (0x10 | t if t < 16 else 0x100 | t) if slot == 0 else 0x30 + slot
                (attack if slot == 0 else boxes)[key] = [m.u8(a + 2), m.u8(a + 3), m.u8(a + 4), m.u8(a + 5)]
            continue
        steps.append((b0, m.u16(a + 2), m.u16(a + 4), {**boxes, **attack}, i, dx)); attack = {}; dx = 0
    raise ValueError(f'animation at {addr:06X} has no terminator')

def shared_map(m, nstates=512):
    """the state -> slot map (one for every character)"""
    base = m.u32(0x78624 + m.u16(0x5C2C) * 4)
    return [m.u16(base + 2 * s) for s in range(nstates)]
