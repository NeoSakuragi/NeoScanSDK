#!/usr/bin/env python3
"""Big portraits for the brawler's drama mode (docs/brawler_data_model.md "Drama mode"): the large win-screen portrait
of a KOF96 / KOF98 fighter, found in our emulator, then put into the brawler's C ROM.

    python3 big_portraits.py capture OUTDIR kof96:geese kof98:rugal ...   -> OUTDIR/big_<game>_<name>.json + .png
    python3 big_portraits.py build GAME.json BUILD_DIR                     -> BUILD_DIR/rom_c1/c2.bin (bm_c1/c2.bin + the
                                                                             portraits' tiles), BUILD_DIR/portraits_big.h

capture: the fighter's fight state c<id> (/data/neogeo_dict/ngsdl_sta/<game>, P1 = that fighter), P2's life poked to 1
every 20 frames and the round timer to 01 every 400 frames, so P1 wins each round on time; after P2's third member the
win screen shows P1's portrait (KOF96: a 12-column chain of 16-tile sprites at the right on a blue screen). VRAM and
palette RAM dumped every 50 frames; the portrait = the widest chain of sticky sprites at least 8 tiles high on the right
half, taken at the first dump where it stands still (same place 50 frames later). Each tile keeps its own palette
(KOF96's use two): the JSON lists the palettes and, per column, [tile, palette index, flip bits] per row (0 = empty row).

build: the portraits game.json's "portraits" lists (name -> "game:fighter" file), trimmed to their non-empty rows /
columns, identical tiles stored once, appended at the end of the C ROM (tile numbers past the fighters); one header with
per portrait: columns, rows, palettes (at most PB_MAXPAL), its tile map column-major ((palette << 20 | tile), 0 =
empty) as the game writes SCB1."""
import json, os, struct, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
sys.path.insert(0, os.path.join(HERE, '..'))
import numpy as np
from PIL import Image
import portraits as P
PORTRAITS = '/data/neogeo_dict/portraits'
PB_MAXPAL = 8                                  # palettes per portrait (main.c PB_PAL .. + 7)
PB_MAXCOLS = 20                                # sprites per portrait (main.c PB_SPR ..)


def chain(v):
    """the portrait: the widest run of tall sprites side by side (sticky, or masters at the same y and height 16 px
    apart: KOF98) with at least 10 columns, not a background (every column full in one palette)"""
    sp = P.sprites(v); best = None
    def nz(run): return sum(1 for s in run for t, a in s['tiles'] if t)
    for i, s in enumerate(sp):
        if v[0x8200 + s['i']] & 0x40 or s['h'] < 10 or s['y'] > 200: continue
        if i and sp[i - 1]['h'] == s['h'] and sp[i - 1]['y'] == s['y'] and sp[i - 1]['x'] + 16 == s['x']: continue   # not a run's start
        run = [s]
        for t in sp[i + 1:]:
            if not (v[0x8200 + t['i']] & 0x40 or (t['y'] == s['y'] and t['h'] == s['h'] and t['x'] == run[-1]['x'] + 16)): break
            run.append(t)
        pals = {a >> 8 for c in run for t, a in c['tiles'] if t}
        if len(run) < 10 or (len(pals) == 1 and nz(run) == len(run) * s['h']): continue
        if best is None or nz(run) > nz(best): best = run
    return best


def capture(outdir, specs):
    import emu, export96, rom96
    casts = {'kof96': export96.CAST, 'kof98': export96.CAST98}
    os.makedirs(outdir, exist_ok=True)
    for spec in specs:
        game, name = spec.split(':'); cid = casts[game].index(name)
        d = os.path.join('/data/tmp/big_portraits', f'{game}_{name}'); os.makedirs(d, exist_ok=True)
        n, frames = 6000, list(range(1500, 6000, 50))
        timer = emu.GAMES[game]['timer']
        pokes = [f'{f}:' + emu.life_pokes(game, 0x108300, 1) + (f',{timer:X}=01' if f % 400 == 5 else '') for f in range(5, n, 20)]
        emu.run(game, os.path.join(d, 'out'), ','.join(['3:a', '5:-'] * (n // 8)), '', pokes, start=f'c{cid}',
                extra={'VRAMDUMP': ';'.join(f'{f}:{d}/v{f}.bin' for f in frames), 'PALDUMP': ','.join(map(str, frames)),
                       'SNAPS': ','.join(map(str, frames)), 'SNAPDIR': d})
        found = None
        for a, b in zip(frames, frames[1:]):
            ca, cb = chain(P.words(f'{d}/v{a}.bin')), chain(P.words(f'{d}/v{b}.bin'))
            if ca and cb and [(s['x'], s['y'], s['tiles']) for s in ca] == [(s['x'], s['y'], s['tiles']) for s in cb]:
                found = a, ca; break
        if not found: print(spec, 'no win-screen portrait found'); continue
        fr, cols = found
        pal = P.words(os.path.join(d, f'out.pal{fr}'))
        crom = rom96.load(rom96.GAMES[game]['neo'])[1]
        pns = sorted({a >> 8 for c in cols for t, a in c['tiles'] if t})
        assert len(pns) <= PB_MAXPAL, f'{spec}: {len(pns)} palettes'
        h = max(c['h'] for c in cols)
        img = Image.new('RGB', (16 * len(cols), 16 * h), (0, 0, 0))
        out = []
        for c, col in enumerate(cols):
            rows = []
            for r, (t, a) in enumerate(col['tiles']):
                if not t: rows.append(0); continue
                rows.append([t, pns.index(a >> 8), a & 3])
                px = P.decode(crom, t)
                for y in range(16):
                    for x in range(16):
                        k = px[y][x]
                        if not k: continue
                        sx = 15 - x if a & 1 else x; sy = 15 - y if a & 2 else y
                        img.putpixel((c * 16 + sx, r * 16 + sy), P.rgb(pal[(a >> 8) * 16 + k]))
            out.append(rows)
        img.save(os.path.join(outdir, f'big_{game}_{name}.png'))
        json.dump({'game': game, 'name': name, 'cid': cid, 'frame': fr, 'x': cols[0]['x'], 'y': cols[0]['y'],
                   'palettes': [list(pal[p * 16:p * 16 + 16]) for p in pns], 'palette_slots': pns, 'cols': out},
                  open(os.path.join(outdir, f'big_{game}_{name}.json'), 'w'))
        print(spec, f'frame {fr}: {len(cols)} columns x {h} tiles at ({cols[0]["x"]}, {cols[0]["y"]}), palettes', [hex(p) for p in pns])


def build(game_json, build_dir):
    import rom96
    from tile_encoder import encode_crom_tile
    g = json.load(open(game_json))
    ports = g.get('portraits', {})
    c1p, c2p = os.path.join(build_dir, 'bm_c1.bin'), os.path.join(build_dir, 'bm_c2.bin')
    c1, c2 = bytearray(open(c1p, 'rb').read()), bytearray(open(c2p, 'rb').read())
    base = len(c1) // 64
    croms, index, order, rows_h = {}, {}, [], []
    h = ['/* Generated by tools/brawler/big_portraits.py from game.json "portraits". Do not edit. */', '#ifndef PORTRAITS_BIG_H',
         '#define PORTRAITS_BIG_H', f'#define PB_COUNT {len(ports)}', f'#define PB_MAXPAL {PB_MAXPAL}', f'#define PB_MAXCOLS {PB_MAXCOLS}',
         'typedef struct { uint8_t cols, rows, npal, pad; const uint16_t *pal; const uint32_t *map; } pbig_t;   /* map: cols x rows '
         'column-major (the entry format below), 0 = empty */']
    for pi, (pname, src) in enumerate(ports.items()):
        game, fighter = src.split(':')
        d = json.load(open(os.path.join(PORTRAITS, f'big_{game}_{fighter}.json')))
        if game not in croms: croms[game] = rom96.load(rom96.GAMES[game]['neo'])[1]
        cols = [c for c in d['cols'] if any(c)]
        top = min(r for c in cols for r, x in enumerate(c) if x); bot = max(r for c in cols for r, x in enumerate(c) if x)
        assert len(cols) <= PB_MAXCOLS, f'{pname}: {len(cols)} columns (at most {PB_MAXCOLS})'
        m = []
        for c in cols:
            for r in range(top, bot + 1):
                x = c[r] if r < len(c) else 0
                if not x: m.append(0); continue
                t, p, fl = x
                key = (game, t)
                if key not in index:
                    index[key] = base + len(order); order.append(key)
                    px = np.array(P.decode(croms[game], t), np.uint8)
                    a, b = encode_crom_tile(px)
                    c1.extend(a); c2.extend(b)
                v = index[key]
                m.append(p << 24 | fl << 20 | v)
        nm = pname.lower()
        h.append(f'static const uint16_t pb_pal_{nm}[] = {{' + ', '.join(f'0x{w:04X}' for p in d['palettes'] for w in [0x8000] + p[1:]) + '};')
        h.append(f'static const uint32_t pb_map_{nm}[] = {{' + ', '.join(f'0x{w:07X}' for w in m) + '};')
        rows_h.append(f'    {{ {len(cols)}, {bot - top + 1}, {len(d["palettes"])}, 0, pb_pal_{nm}, pb_map_{nm} }},   /* {pi}: {pname} ({src}) */')
    h.append('/* map entry: palette index (0-3) << 24 | SCB1 flip bits (1 h, 2 v) << 20 | tile (20 bits) */')
    h.append(f'static const pbig_t pbig[PB_COUNT ? PB_COUNT : 1] = {{\n' + ('\n'.join(rows_h) if rows_h else '    { 0 }') + '\n};')
    h.append('enum { ' + ', '.join(f'PB_{n.upper()}' for n in ports) + (', ' if ports else '') + 'PB_NONE = 0xFF };')
    h.append('#endif')
    open(os.path.join(build_dir, 'rom_c1.bin'), 'wb').write(bytes(c1)); open(os.path.join(build_dir, 'rom_c2.bin'), 'wb').write(bytes(c2))
    open(os.path.join(build_dir, 'portraits_big.h'), 'w').write('\n'.join(h) + '\n')
    print(f'big portraits: {len(ports)}, {len(order)} tiles from {base} ({len(order) * 128 // 1024} KB), C ROM {2 * len(c1) / 1048576:.2f} MB')


if __name__ == '__main__':
    if sys.argv[1] == 'capture': capture(sys.argv[2], sys.argv[3:])
    elif sys.argv[1] == 'build': build(sys.argv[2], sys.argv[3])
    else: sys.exit(__doc__)
