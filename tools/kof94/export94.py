#!/usr/bin/env python3
"""KOF94 fighters in the export96 layout (the brawler's export_bm.py reads it like a KOF96/98/99 export).

    python3 export94.py OUTDIR heavy_d lucky brian rugal rugal2

KOF94 = KOF95's engine one year earlier (tools/kof95/README.md): animations $080000 + id*4 (256 slots), sprite
definitions $080080 + id*4, 6-byte animation steps with $FD boxes / $FB moves, frame chains of parts. Differences,
each checked against the running game (our emulator) or the ROM's own code:
  - sprite definitions always use 16-bit column bitmasks (KOF95: 8-bit when a column has <= 8 rows);
  - palettes: palette n at $6F000 + n*32; a fighter's colour set s starts at the word table $33D2 + (2*id + s)*2
    (loader $330E / $336A, 14 palettes copied); a sprite part uses palette (sdef byte 2 >> 4) - 1 of the set;
  - physics record $6D2B8 + id*128: +$24 walk, +$28 jump launch, +$2C gravity (16.16; Terry = KOF95's);
  - hurt boxes are box types 3 and 4, attack boxes type 1; steps have the active flag $0100 but no $4000 "same hit"
    bit, so a run of active steps is exported as one hit;
  - no run, no C+D attack: 'run' plays the walk, 'body_toss' (the brawler's C+D) plays far D.
Slots for the brawler's moves: KOF95's numbering where Terry's frames match it, the rest read off Terry's slot sheet
(ids94.py); hit_stand_light 57, win_a 36, knockdown flight / bounce / fall 72 / 74 / 75 to be confirmed in play."""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof95')); sys.path.insert(0, HERE)
import rom
from neogeo.sprite_decode import r16, r32, rs16
from ids94 import NEO, PAL_ROM, palette_base, frame_parts

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = ['heidern', 'ralf', 'clark', 'athena', 'kensou', 'chin', 'kyo', 'benimaru', 'goro', 'heavy_d', 'lucky', 'brian',
        'kim', 'chang', 'choi', 'terry', 'andy', 'joe', 'ryo', 'robert', 'takuma', 'yuri', 'mai', 'king', 'rugal', 'rugal2']
SLOTS = {'idle': 0, 'walk_fwd': 1, 'run': 1, 'prejump': 3, 'jump_up_rise': 5, 'jump_up_fall': 6, 'jump_fwd_rise': 7,
         'jump_fwd_fall': 8, 'land': 4, 'atk_a_close': 82, 'atk_a_far': 83, 'atk_b_close': 87, 'atk_b_far': 88,
         'atk_c_close': 92, 'atk_c_far': 93, 'atk_d_close': 97, 'atk_d_far': 98, 'atk_d_crouch': 101, 'atk_c_jump': 94,
         'atk_d_jump': 99, 'body_toss': 98, 'hit_stand_light': 57, 'hit_stand_heavy': 60, 'hit_air': 65, 'blowback': 66,
         'knockdown_flight': 72, 'knockdown_bounce': 74, 'knockdown_fall': 75, 'down': 78, 'getup': 80, 'trip': 67,
         'win_a': 36}
NPAL = 14                                         # palettes per colour set (the loader copies 14)
STATE_MAP = 0x7BF48                               # long per id -> words per game state, low byte = slot (code $4860)

def state_map(prom, cid):
    t = r32(prom, STATE_MAP + cid * 4); return [r16(prom, t + 2 * st) & 0xFF for st in range(256)]

def move_slots(prom, cid):
    """the brawler's moves -> this fighter's slots: SLOTS are Terry's (id 15); each move's game state is the first
    state Terry's map sends to that slot, and the fighter's own map gives its slot (the bosses' normals are compacted:
    Rugal's close C = slot 85, Rugal 2's = 87)"""
    terry, own = state_map(prom, 15), state_map(prom, cid)
    return {m: own[terry.index(sl)] if sl in terry else sl for m, sl in SLOTS.items()}

def parse_anim(prom, addr):
    """-> (steps [{ticks, rec, flags, dx, boxes}], 'loop'|'hold'). Boxes keyed '1x' attack / '3x' '4x' hurt, as rom96;
    hurt boxes persist, an attack box lives on the step after it ($0100 steps keep it, export_bm); $FB dx summed onto
    the next step. Flags: KOF94's $0100 kept, $4000 added on active steps (a run of active steps = one hit)."""
    steps, boxes, attack, dx, pos = [], {}, {}, 0, addr
    for _ in range(300):
        w = prom[pos:pos + 6]
        if w[0] == 0xFF: return steps, 'loop'
        if w[0] == 0xFE: return steps, 'hold'
        if w[0] >= 0x80:
            if w[0] == 0xFD:
                (attack if w[1] >> 4 == 1 else boxes)[f'{w[1]:02X}'] = list(w[2:6])
            elif w[0] == 0xFB:
                v = (w[2] << 8) | w[3]; dx += v - 0x10000 if v & 0x8000 else v
            pos += 6; continue
        fl = (w[4] << 8) | w[5]
        if fl & 0x100: fl |= 0x4000
        steps.append({'ticks': w[0], 'rec': (w[1] << 16) | (w[2] << 8) | w[3], 'flags': fl, 'dx': dx, 'boxes': {**boxes, **attack}})
        attack, dx = {}, 0
        pos += 6
    raise ValueError(f'animation at {addr:06X} has no terminator')

def palettes(prom, cid):
    """[set][palette][16 colours] for both colour sets, colour 0 = 0"""
    return [[[0] + [r16(prom, PAL_ROM + (palette_base(prom, cid, s) + k) * 32 + 2 * i) for i in range(1, 16)]
             for k in range(NPAL)] for s in (0, 1)]

def physics(prom, cid):
    b = 0x6D2B8 + cid * 128
    walk, vy0, g = (struct.unpack('>i', prom[b + o:b + o + 4])[0] / 65536 for o in (0x24, 0x28, 0x2C))
    return {'walk_fwd': walk, 'walk_back': walk * 0.75, 'jump_vy0': vy0, 'gravity': g, 'jump_dx': walk}

def export(names, outdir, only=None):
    prom, crom = rom.load(NEO)
    tile_map, out = {}, {'game': 'kof94', 'tile_base': TILE_BASE, 'characters': {}}
    def our_tile(code):
        if code is None: return 0
        if code not in tile_map: tile_map[code] = TILE_BASE + len(tile_map)
        return tile_map[code]
    for name in names:
        cid = CAST.index(name)
        st, sd = r32(prom, 0x080000 + cid * 4), r32(prom, 0x080080 + cid * 4)
        frames, index, anims = [], {}, {}
        def add_frame(rec):
            if rec not in index:
                index[rec] = len(frames)
                parts = []
                for p in frame_parts(prom, rec, sd):
                    parts.append({'dx': p['dx'], 'dy': p['dy'], 'hflip': p['hflip'], 'vflip': p['vflip'], 'pal': (p['pal'] - 1) & 15,
                                  'tiles': [[our_tile(t) for t in col] for col in p['columns']]})
                    assert parts[-1]['pal'] < NPAL, f'{name} frame {rec:06X}: palette {parts[-1]["pal"]} past the set'
                frames.append({'record': f'{rec:06X}', 'parts': parts})
            return index[rec]
        for move, slot in move_slots(prom, cid).items():
            if only is not None and move not in only: continue
            steps, mode = parse_anim(prom, r32(prom, st + slot * 4))
            anims[move] = {'slot': slot, 'mode': mode, 'steps': [
                {'frame': add_frame(s['rec']), 'ticks': s['ticks'], 'flags': s['flags'], 'dx': s['dx'], 'boxes': s['boxes']} for s in steps]}
        out['characters'][name] = {'id': cid, 'frames': frames, 'anims': anims, 'block_palettes': palettes(prom, cid),
                                   'physics': physics(prom, cid), 'throws': {}, 'specials': []}
    out['tiles'] = len(tile_map)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * (TILE_BASE + len(tile_map)))
    for code, ours in tile_map.items(): region[ours * 128:(ours + 1) * 128] = crom[code * 128:(code + 1) * 128]
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    ex = export(sys.argv[2:] or ['heavy_d', 'lucky', 'brian', 'rugal', 'rugal2'], sys.argv[1])
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', {m: len(a['steps']) for m, a in ch['anims'].items() if not a['steps']} or 'all anims have steps', ch['physics'])
    print(ex['tiles'], 'tiles')
