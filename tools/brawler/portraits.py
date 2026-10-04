#!/usr/bin/env python3
"""HUD portraits (the 32x32 face next to the life bar) of KOF96/98/99 fighters, found in a running fight:
VRAM of a fight frame -> P1's portrait sprites (2 columns x 2 tiles at the top left) -> 4 C-ROM tiles + palette.

    python3 portraits.py capture OUTDIR kof98:terry kof99:k_dash ...   -> OUTDIR/<game>_<name>.json + .png

KOF98 / KOF99 in our emulator (neogeo_sdl --capture VRAMDUMP + PALDUMP, states /data/neogeo_dict/ngsdl_sta/<game>/c<id>,
made by tools/kof96/capture/specials96.prep).

    python3 portraits.py table OUTDIR kof96:geese ...                  -> the same files, from KOF96's ROM tables

KOF96 (one fight state only): the HUD portrait pointer list at ROM $1F5370 (29 longs, cast order; found from Terry's
portrait in a rendered VRAM dump) points at 3x3 sprite definitions; colours = ROM palette $16C + id (list at $7897C),
ROM palettes at $200002 + n * 32 (word 0 = n). Checked: Terry's matches palette RAM slot $1F in his fight."""
import json, os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import export96, rom96
from PIL import Image
NGSDL = os.path.join(HERE, '..', '..', 'emu', os.environ.get('NGSDL_BIN', 'neogeo_sdl'))
CASTS = {'kof96': export96.CAST, 'kof98': export96.CAST98, 'kof99': export96.CAST99}

def words(path): d = open(path, 'rb').read(); return struct.unpack(f'>{len(d) // 2}H', d)

def dump(game, cid, outdir):
    """VRAM (VRAMDUMP) and the palette bank the 68000 sees ($400000, PALDUMP's frame-list form) at frame 20 of the
    fighter's state c<id> in our emulator"""
    v, o = os.path.join(outdir, f'{game}_{cid}_vram.bin'), os.path.join(outdir, f'{game}_{cid}')
    env = dict(os.environ, LOAD=f'/data/neogeo_dict/ngsdl_sta/{game}/c{cid}.state', SEQ='30:-', VRAMDUMP=f'20:{v}',
               PALDUMP='20', OUT=o)
    subprocess.run([NGSDL, rom96.GAMES[game]['neo'], '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    return words(v), words(o + '.pal20')

def sprites(v):
    out, x, y, h = [], 0, 0, 0
    for i in range(1, 381):
        s3, s4 = v[0x8200 + i], v[0x8400 + i]
        if s3 & 0x40: x += 16
        else: y, h, x = 496 - (s3 >> 7), s3 & 0x3F, s4 >> 7
        xs = x - 0x200 if x >= 0x1E0 else x
        tiles = [(v[i * 64 + 2 * r] | ((v[i * 64 + 2 * r + 1] >> 4) & 0xF) << 16, v[i * 64 + 2 * r + 1]) for r in range(min(h, 32))]
        out.append({'i': i, 'x': xs, 'y': y, 'h': h, 'tiles': tiles})
    return out

def p1_portrait(v):
    """the two 2-tile-high columns 16 px apart nearest the screen's top left"""
    cand = [s for s in sprites(v) if s['h'] == 2 and 0 <= s['x'] < 48 and all(t for t, a in s['tiles'])]
    cand.sort(key=lambda s: (s['y'], s['x']))
    for a in cand:
        b = next((s for s in cand if s['x'] == a['x'] + 16 and s['y'] == a['y']), None)
        if b: return [a, b]
    return None

def decode(crom, tile):
    t = crom[tile * 128:(tile + 1) * 128]; c1, c2 = t[0::2], t[1::2]
    px = [[0] * 16 for _ in range(16)]
    for half, x0 in ((0, 8), (1, 0)):
        for y in range(16):
            o = half * 32 + y * 2; b0, b1, b2, b3 = c1[o], c1[o + 1], c2[o], c2[o + 1]
            for x in range(8):
                px[y][x0 + x] = ((b0 >> x) & 1) | ((b1 >> x) & 1) << 1 | ((b2 >> x) & 1) << 2 | ((b3 >> x) & 1) << 3
    return px

def rgb(w):
    r = ((w >> 7) & 0x1E) | ((w >> 14) & 1); g = ((w >> 3) & 0x1E) | ((w >> 13) & 1); b = ((w << 1) & 0x1E) | ((w >> 12) & 1)
    return (r * 255 // 31, g * 255 // 31, b * 255 // 31)

def capture(outdir, specs):
    os.makedirs(outdir, exist_ok=True)
    crom = {}
    for spec in specs:
        game, name = spec.split(':'); cid = CASTS[game].index(name)
        v, pal = dump(game, cid, outdir)
        cols = p1_portrait(v)
        if not cols: print(spec, 'no portrait found'); continue
        if game not in crom: crom[game] = rom96.load(rom96.GAMES[game]['neo'])[1]
        attr = cols[0]['tiles'][0][1]; pn = attr >> 8
        colours = [rgb(pal[pn * 16 + k]) for k in range(16)]
        img = Image.new('RGB', (32, 32), (0, 0, 0)); idx = Image.new('P', (32, 32), 0)
        for c, col in enumerate(cols):
            for r, (tile, a) in enumerate(col['tiles']):
                px = decode(crom[game], tile)
                for y in range(16):
                    for x in range(16):
                        sx = 15 - x if a & 1 else x; sy = 15 - y if a & 2 else y
                        idx.putpixel((c * 16 + sx, r * 16 + sy), px[y][x])
        idx.putpalette([v_ for col in colours for v_ in col])
        idx.save(os.path.join(outdir, f'{game}_{name}.png'))
        json.dump({'game': game, 'name': name, 'cid': cid, 'tiles': [[t for t, a in c['tiles']] for c in cols],
                   'attrs': [[a for t, a in c['tiles']] for c in cols], 'palette_index': pn, 'palette': pal[pn * 16:pn * 16 + 16]},
                  open(os.path.join(outdir, f'{game}_{name}.json'), 'w'))
        print(spec, 'tiles', [[hex(t) for t, a in c['tiles']] for c in cols], 'flip', attr & 3, 'palette', hex(pn))

def table96(outdir, specs):
    """KOF96 HUD portraits from ROM: sprite definitions [palette slot, format $01, cols, rows, first tile (long), one
    row-mask byte per column ($80 = top row)], tiles in column order over the rows present"""
    prom, crom = rom96.load(rom96.GAMES['kof96']['neo'])
    ptrs = struct.unpack('>29I', prom[0x1F5370:0x1F5370 + 29 * 4])
    for spec in specs:
        game, name = spec.split(':'); assert game == 'kof96'
        cid = export96.CAST.index(name); o = ptrs[cid] - 0x100000            # CPU $2xxxxx = P2 bank 0 = ROM $1xxxxx
        slot, fmt, cols, rows = prom[o:o + 4]; tile = struct.unpack('>I', prom[o + 4:o + 8])[0]; masks = prom[o + 8:o + 8 + cols]
        assert fmt == 1, f'{name}: portrait format {fmt:02X}'
        pid = 0x16C + cid                                                    # its colours: ROM palette $16C + id
        pal = struct.unpack('>16H', prom[0x200002 + pid * 32:0x200002 + pid * 32 + 32])
        idx = Image.new('P', (cols * 16, rows * 16), 0); tiles = []
        for c in range(cols):
            col = []
            for r in range(rows):
                if not masks[c] & (0x80 >> r): col.append(0); continue
                px = decode(crom, tile); col.append(tile)
                for y in range(16):
                    for x in range(16): idx.putpixel((c * 16 + x, r * 16 + y), px[y][x])
                tile += 1
            tiles.append(col)
        idx.putpalette([v_ for w in (0,) + pal[1:] for v_ in rgb(w)])
        idx.save(os.path.join(outdir, f'{game}_{name}.png'))
        json.dump({'game': game, 'name': name, 'cid': cid, 'tiles': tiles, 'palette_index': slot, 'rom_palette': pid,
                   'palette': [0] + list(pal[1:]), 'note': 'top tile row sits above the screen in the HUD'},
                  open(os.path.join(outdir, f'{game}_{name}.json'), 'w'))
        print(spec, cols, 'x', rows, 'first tile', hex(tiles[0][0]), 'palette', hex(pid))

def table94(outdir, specs):
    """KOF94 HUD portraits from ROM (found from King's in a demo fight, VRAM at the top left): 2x2 sprite definitions
    of effect table 28 ($080080 + 28*4), two per fighter in groups of 12 (sdef = (k // 12) * 24 + k % 12, k = 2 * id;
    King id 23 -> 82); colours = palette 8 of the fighter's set (palette slot 24 = ROM palette $604 + 8 for King)"""
    sys.path.insert(0, os.path.join(HERE, '..', 'kof95')); sys.path.insert(0, os.path.join(HERE, '..', 'kof94'))
    import rom
    from neogeo.animation import read_sprite_def
    from ids94 import NEO, PAL_ROM, palette_base
    from export94 import CAST
    prom, crom = rom.load(NEO)
    sd = struct.unpack('>I', prom[0x080080 + 28 * 4:0x080080 + 28 * 4 + 4])[0]
    for spec in specs:
        game, name = spec.split(':'); assert game == 'kof94'
        cid = CAST.index(name); k = 2 * cid
        d = read_sprite_def(prom, sd, 96 if cid >= 24 else (k // 12) * 24 + k % 12, bitmask_mode='word')   # both Rugals: 96
        assert d and d['cols'] == 2 and d['tiles_per_col'] == 2, f'{name}: no 2x2 portrait ({d})'
        pid = palette_base(prom, cid) + 8
        pal = struct.unpack('>16H', prom[PAL_ROM + pid * 32:PAL_ROM + pid * 32 + 32])
        idx = Image.new('P', (32, 32), 0); tiles, tile = [], d['base_tile']
        for c in range(2):
            col = []
            for r in range(2):
                px = decode(crom, tile); col.append(tile)
                for y in range(16):
                    for x in range(16): idx.putpixel((c * 16 + x, r * 16 + y), px[y][x])
                tile += 1
            tiles.append(col)
        idx.putpalette([v_ for w in (0,) + pal[1:] for v_ in rgb(w)])
        idx.save(os.path.join(outdir, f'{game}_{name}.png'))
        json.dump({'game': game, 'name': name, 'cid': cid, 'tiles': tiles, 'rom_palette': pid, 'palette': [0] + list(pal[1:])},
                  open(os.path.join(outdir, f'{game}_{name}.json'), 'w'))
        print(spec, 'first tile', hex(tiles[0][0]), 'palette', hex(pid))

def table97(outdir, specs):
    """KOF97 HUD portraits from ROM (found from Andy's in a demo fight: VRAM top left -> tile $C2C7): effect table 34,
    sprite definition 302 + id (3x2 tiles, palette byte 31 = the fighter's body palette 15, set A: ROM palette
    $100 + id*$40 + 15, checked against palette RAM slot 31 = $20F for Andy)"""
    m = rom96.Mem(rom96.load(rom96.GAMES['kof97']['neo'])[0], 'kof97'); crom = rom96.load(rom96.GAMES['kof97']['neo'])[1]
    for spec in specs:
        game, name = spec.split(':'); assert game == 'kof97'
        cid = export96.CAST97.index(name); sd = rom96.sdef(m, 34, 302 + cid)
        assert sd['pal'] == 31, f'{name}: portrait palette byte {sd["pal"]}'
        pal = export96.pal_rom98(m, 0x100 + cid * 0x40 + 15)
        cols = sd['cols']; idx = Image.new('P', (16 * len(cols), 16 * len(cols[0])), 0)
        for c, col in enumerate(cols):
            for r, t in enumerate(col):
                if not t: continue
                px = decode(crom, t)
                for y in range(16):
                    for x in range(16): idx.putpixel((c * 16 + x, r * 16 + y), px[y][x])
        idx.putpalette([v_ for w in pal for v_ in rgb(w)])
        idx.save(os.path.join(outdir, f'{game}_{name}.png'))
        json.dump({'game': game, 'name': name, 'cid': cid, 'tiles': cols, 'palette': pal},
                  open(os.path.join(outdir, f'{game}_{name}.json'), 'w'))
        print(spec, len(cols), 'x', len(cols[0]), 'first tile', hex(next(t for col in cols for t in col if t)))

# KOF96's member-select squares of the boss team (Geese, Krauser, Mr. Big: the grid's bottom-middle block; drawn as
# part of the full-screen select picture, so taken from the screen): our emulator from power-on, two coins, START; the
# select screen shows ~frame 2400 (after How to play). Square = (x0, y0) of a 28x28 window on the 304x224 screen.
SQUARES96 = {'geese': (106, 146), 'krauser': (137, 146), 'mr_big': (168, 146)}

def select96(outdir):
    """-> OUTDIR/kof96_<name>_square.png (28x28 RGB, make_hud.py takes it as is). The frame used: the first of
    2300-2700 (every 20) that, with the next, shows the grid (block borders white at y 160, x 135 / 167 / 197, the
    squares' centres not white)."""
    import tempfile
    d = tempfile.mkdtemp(dir='/data/tmp')
    frames = list(range(2300, 2701, 20))
    env = dict(os.environ, SEQ='300:-,10:o,60:-,10:o,80:-,10:s,2600:-', OUT='/dev/null', SNAPDIR=d,
               SNAPS=','.join(map(str, frames)))
    subprocess.run([NGSDL, rom96.GAMES['kof96']['neo'], '--capture'], env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=600)
    white = lambda im, x, y: sum(im.getpixel((x, y))) > 650
    def grid(fr):                                       # block borders white, the faces' centres not
        im = Image.open(os.path.join(d, f'snap_{fr}.ppm')).convert('RGB')
        return im if all(white(im, x, 160) for x in (135, 167, 197)) and \
            not any(white(im, x + 14, y + 14) for x, y in SQUARES96.values()) else None
    fr = next((a for a, b in zip(frames, frames[1:]) if grid(a) and grid(b)), None)   # two in a row: settled
    if fr is None: raise SystemExit('KOF96 select screen not found')
    im = grid(fr)
    for name, (x0, y0) in SQUARES96.items():
        im.crop((x0, y0, x0 + 28, y0 + 28)).save(os.path.join(outdir, f'kof96_{name}_square.png'))
        print(f'kof96:{name} square from frame {fr} at ({x0}, {y0})')

if __name__ == '__main__':
    if sys.argv[1] == 'select96': select96(sys.argv[2])
    if sys.argv[1] == 'capture': capture(sys.argv[2], sys.argv[3:])
    if sys.argv[1] == 'table': table96(sys.argv[2], sys.argv[3:])
    if sys.argv[1] == 'table94': table94(sys.argv[2], sys.argv[3:])
    if sys.argv[1] == 'table97': table97(sys.argv[2], sys.argv[3:])
