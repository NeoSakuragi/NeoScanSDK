"""KOF95 ROM access from our .neo file (/data/roms/kof95.neo).

.neo layout: 4096-byte header (P@0x04 S@0x08 M@0x0C V1@0x10 V2@0x14 C@0x18, LE u32 sizes), data from 0x1000 in that order.
P is stored in 68000 address order with each 16-bit word little-endian (MAME region order), so one byte swap per word gives
the CPU view: prom[0x100:0x107] == b'NEO-GEO'. C is MAME's interleaved sprite region: 128 bytes per 16x16 tile.
The parsing library is tools/neosdk/neogeo (one implementation; this module only feeds it).
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'neosdk'))
NEO = os.environ.get('KOF95_NEO', '/data/roms/kof95.neo')

# The cast: character id = index into the state table ($080000), sprite-definition table ($080080), palette blocks
# and physics records. Id 25 is the final boss, Omega Rugal (KOF95 has no first-form Rugal fighter); ids 26-29 hold
# projectile and effect sprites, not fighters.
CAST = ['heidern', 'ralf', 'clark', 'athena', 'kensou', 'chin', 'kyo', 'benimaru', 'goro', 'iori', 'eiji', 'billy',
        'kim', 'chang', 'choi', 'terry', 'andy', 'joe', 'ryo', 'robert', 'takuma', 'yuri', 'mai', 'king',
        'saisyu', 'omega_rugal']
CHARS = {n: i for i, n in enumerate(CAST)}

def palettes(prom, cid):
    """(regular, mirror) 16-colour body palettes. Each character owns 32 palettes at $1D9000 + id*$400: 16 regular, then
    16 used by the second player in a mirror match (+$200). The body is palette 0 of each set. Colour 0 holds a tag
    word ($100 + id*$20, +$10 for the mirror set) that the game overwrites; it is transparent."""
    base = 0x1D9000 + cid * 0x400
    get = lambda a: [0] + [(prom[a + 2 * i] << 8) | prom[a + 2 * i + 1] for i in range(1, 16)]
    assert (prom[base] << 8 | prom[base + 1]) == 0x100 + cid * 0x20, f'palette tag mismatch for id {cid}'
    return get(base), get(base + 0x200)

def block_palettes(prom, cid):
    """all 16 palettes of the character's block, regular and mirror set: ([16][16], [16][16]), colour 0 = 0"""
    base = 0x1D9000 + cid * 0x400
    get = lambda a: [0] + [(prom[a + 2 * i] << 8) | prom[a + 2 * i + 1] for i in range(1, 16)]
    return [get(base + 32 * k) for k in range(16)], [get(base + 0x200 + 32 * k) for k in range(16)]

def physics(prom, cid):
    """px/frame from the 128-byte record at $7AF16 + id*128: +0 walk, +4 jump launch, +8 gravity (16.16).
    Walk back is 3/4 of walk and the jump drift equals walk (both measured in MAME on Terry, Kyo, Ryo and Robert)."""
    b = 0x7AF16 + cid * 128
    walk, vy0, g = (struct.unpack('>i', prom[b + o:b + o + 4])[0] / 65536 for o in (0, 4, 8))
    return {'walk_fwd': walk, 'walk_back': walk * 0.75, 'jump_vy0': vy0, 'gravity': g, 'jump_dx': walk}

def load(path=NEO):
    raw = open(path, 'rb').read()
    sizes = struct.unpack('<6I', raw[4:0x1C]); off = 0x1000; reg = {}
    for name, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes):
        reg[name] = raw[off:off + sz]; off += sz
    p = bytearray(reg['P'])
    p[0::2], p[1::2] = reg['P'][1::2], reg['P'][0::2]
    assert bytes(p[0x100:0x107]) == b'NEO-GEO', p[0x100:0x110]
    return bytes(p), reg['C']
