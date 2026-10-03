#!/usr/bin/env python3
"""Export KOF95 characters for our engine: tiles, palette, frames (sprite parts with hotspot offsets and flips),
animations (durations, loop/hold, collision boxes) and measured physics. Source of truth for which animation does what:
moves.json (captured from the running game).

    python3 export.py OUTDIR [kyo terry ryo robert]

Writes OUTDIR/kof95_chars.c / .h (const data for the 68000) and OUTDIR/kof95_c1.bin, kof95_c2.bin (sprite tiles, our
numbering from TILE_BASE). Also OUTDIR/kof95_export.json, the same data in readable form, used by preview.py.

KOF95 formats (P ROM, big-endian):
  animation step  6 bytes: [ticks:8][frame record:24][flags:16]; steps with ticks >= $80 are 6-byte commands ($FD xx = box,
                  fd 30 / fd 40 / fd 41 + 4 bytes; $FA = other); $FFxx ends a looping animation, $FExx one that holds (2 bytes).
  frame record    chain of 6-byte parts: [dx:s16][dy:s16][word:16]; word bits 0-8 = sprite definition index,
                  bit 13 = another part follows, bits 14-15 = flip (bit 14 horizontal, bit 15 vertical; checked on the
                  somersault frames, see preview sheets).
  sprite def      [cols:8][rows:8][pal:4|tile bits 16-19:4][pad:8][tile:16] then one bitmask per column (8-bit when
                  rows <= 8, else 16-bit), MSB = top row; tiles are numbered consecutively over the set bits, column-major.
"""
import json, os, sys
import rom
from neogeo.sprite_decode import r16, r32, rs16, read_palette
from neogeo.animation import read_sprite_def

HERE = os.path.dirname(os.path.abspath(__file__))
TILE_BASE = 256          # our tiles 0-255 are reserved for the game's own graphics; tile 0 must stay blank

def parse_anim(prom, addr):
    """-> (steps [(ticks, frame_record, flags, boxes)], mode 'loop'|'hold')"""
    steps, boxes, attack, pos = [], {}, {}, addr
    for _ in range(200):
        w = prom[pos:pos + 6]
        if w[0] == 0xFF: return steps, 'loop'               # $FFxx / $FExx: 2-byte terminators, xx = parameter (e.g. $FE30 on Terry's slot 59)
        if w[0] == 0xFE: return steps, 'hold'
        if w[0] >= 0x80:
            if w[0] == 0xFD:                                 # box: hurtboxes ($3x/$4x) persist; an attack box ($1x) is live
                (attack if w[1] >> 4 == 1 else boxes)[w[1]] = list(w[2:6])   # only on the step right after it
            pos += 6; continue
        steps.append((w[0], (w[1] << 16) | (w[2] << 8) | w[3], (w[4] << 8) | w[5], {**boxes, **attack}))
        attack = {}
        pos += 6
    raise ValueError(f'animation at {addr:06X} has no terminator')

def state_slot(prom, cid, state):
    """game state -> animation slot through the character's map ($57D0A id remap -> $7C948 pointer, 2 bytes/state)"""
    return prom[r32(prom, 0x7C948 + r16(prom, 0x57D0A + cid * 2) * 4) + 2 * state + 1]

VICTIM_POSES_DOC = json.load(open(os.path.join(HERE, 'victim_poses.json')))

def frame_at(prom, addr, raw_index):
    """frame record shown at raw record `raw_index` of the animation at addr (the engine's +$74 / 6): commands count
    as records; on a command the last frame shown stays"""
    rec = None
    for i in range(raw_index + 1):
        w = prom[addr + 6 * i:addr + 6 * i + 6]
        if w[0] in (0xFE, 0xFF): break
        if w[0] < 0x80: rec = (w[1] << 16) | (w[2] << 8) | w[3]
    return rec

def sdef_columns(sdef):
    """-> list of columns, each a list of KOF tile codes (None = empty row), top row first"""
    code, cols = sdef['base_tile'], []
    bits = 16 if sdef['tiles_per_col'] > 8 else 8
    for c in range(sdef['cols']):
        bm = sdef['bitmasks'][c] if c < len(sdef['bitmasks']) else (1 << bits) - 1
        col = []
        for t in range(sdef['tiles_per_col']):
            if t >= bits or (bm >> (bits - 1 - t)) & 1: col.append(code); code += 1
            else: col.append(None)
        cols.append(col)
    return cols

def frame_parts(prom, rec, sd):
    parts, pos = [], rec
    for _ in range(8):
        dx, dy, word = rs16(prom, pos), rs16(prom, pos + 2), r16(prom, pos + 4)
        sdef = read_sprite_def(prom, sd, word & 0x1FF)
        if sdef is None: raise ValueError(f'frame {rec:06X}: sprite definition {word & 0x1FF} unreadable')
        parts.append({'dx': dx, 'dy': dy, 'hflip': (word >> 14) & 1, 'vflip': (word >> 15) & 1, 'columns': sdef_columns(sdef)})
        if not (word >> 13) & 1: break
        pos += 6
    return parts

def load_throws(cid):
    """{'throw': ..., 'air_throw': ...} from capture/throws/<id>.json: the first ground throw and the first air throw"""
    path = os.path.join(HERE, 'capture', 'throws', f'{cid}.json')
    if not os.path.exists(path): return {}
    found = {}
    for t in json.load(open(path)):
        key = 'air_throw' if t['try'].startswith('air') and t['p1_air'] else 'throw' if t['try'].startswith('ground') else None
        if key and key not in found and t['thrower_slot'] is not None and t['victim'] and 'step' in t['victim'][0]:
            found[key] = {**t, 'inputs': {'ground_c': 'forward+C', 'ground_d': 'forward+D'}.get(t['try'], 'jump forward, C or D')}
    return found

def palette_of_slot(slot):
    """palette RAM slot of a spawned object -> ('body'|'char'|'global', index). Slots 16-111 hold the six fighters'
    blocks (16 per fighter, P1's team at 16-63, P2's at 64-111); the rest are fixed effect palettes in ROM at
    $1D7000 + slot*32."""
    if slot is None: return ('body', None)
    if 16 <= slot < 112: return ('body', None) if (slot - 16) % 16 == 0 else ('char', (slot - 16) % 16)
    return ('global', slot)

def load_specials(prom, cid, add_frame, add_effect_frame):
    """capture/specials/<id>.json (command-driven run) -> moves with per-frame replay scripts:
    row = [fighter frame, x, height, [[object frame, x, height, same facing], ...]]"""
    path = os.path.join(HERE, 'capture', 'specials', f'{cid}.json')
    if not os.path.exists(path): return [], {}
    moves, pals = [], {}
    for t in json.load(open(path)):
        if not t.get('command') or not t.get('script'): continue
        rows = []
        for rec, x, h, objs in t['script']:
            r = int(rec, 16)
            if not 0x080000 <= r < len(prom): continue
            orow = []
            for orec, ox, oy, table, pslot, same in objs:
                o = int(orec, 16)
                if table is None or not 0x080000 <= o < len(prom): continue
                pal = palette_of_slot(pslot)
                if pal[0] == 'global': pals[pal[1]] = [0] + [r16(prom, 0x1D7000 + pal[1] * 32 + 2 * i) for i in range(1, 16)]
                try: orow.append([add_effect_frame(o, table, pal), ox, oy, same])
                except ValueError: pass
            rows.append([add_frame(r), x, h, orow])
        c = t['command']
        moves.append({'slot': c['slot'], 'input': c['input'], 'condition': c['condition'], 'button': t['input'].split(':')[-1],
                      'states': t['states'], 'script': rows})
    return moves, pals

def export(names, outdir):
    prom, crom = rom.load(); mv = json.load(open(os.path.join(HERE, 'moves.json')))
    slot_names = sorted(mv['slots'].items(), key=lambda kv: kv[1])
    tile_map, out = {}, {'tile_base': TILE_BASE, 'characters': {}}
    adders = {}
    def our_tile(code):
        if code is None: return 0
        if code not in tile_map: tile_map[code] = TILE_BASE + len(tile_map)
        return tile_map[code]
    for name in names:
        cid = rom.CHARS[name]
        st, sd = r32(prom, 0x080000 + cid * 4), r32(prom, 0x080080 + cid * 4)
        palette, mirror = rom.palettes(prom, cid)
        frames, frame_index, anims = [], {}, {}
        def add_frame(rec, frames=frames, frame_index=frame_index, sd=sd):   # bound now: also used after the loop
            if rec not in frame_index:
                frame_index[rec] = len(frames)
                parts = frame_parts(prom, rec, sd)
                for p in parts: p['tiles'] = [[our_tile(t) for t in col] for col in p['columns']]; del p['columns']
                frames.append({'record': f'{rec:06X}', 'parts': parts})
            return frame_index[rec]
        def add_effect_frame(rec, table, palette):
            """a spawned object's frame: parts from its own table's sprite definitions; palette = ('body', None) for the
            fighter's body palette, ('char', i) for palette i of the fighter's block, ('global', slot) for a fixed slot"""
            key = (rec, table, palette)
            if key not in frame_index:
                frame_index[key] = len(frames)
                parts = frame_parts(prom, rec, r32(prom, 0x080080 + table * 4))
                for p in parts: p['tiles'] = [[our_tile(t) for t in col] for col in p['columns']]; del p['columns']
                frames.append({'record': f'{rec:06X}', 'table': table, 'palette': list(palette), 'parts': parts})
            return frame_index[key]
        for move, slot in slot_names:
            steps, mode = parse_anim(prom, r32(prom, st + slot * 4))
            seq = []
            for ticks, rec, flags, boxes in steps:
                if rec not in frame_index:
                    frame_index[rec] = len(frames)
                    parts = frame_parts(prom, rec, sd)
                    for p in parts: p['tiles'] = [[our_tile(t) for t in col] for col in p['columns']]; del p['columns']
                    frames.append({'record': f'{rec:06X}', 'parts': parts})
                seq.append({'frame': frame_index[rec], 'ticks': ticks, 'boxes': {f'{k:02X}': v for k, v in boxes.items()}})
            anims[move] = {'slot': slot, 'mode': mode, 'steps': seq}
        # throws captured in MAME (capture/throws.py): the thrower's own slot + a per-frame script for the victim
        throws = load_throws(cid)
        for key, t in throws.items():
            steps, mode = parse_anim(prom, r32(prom, st + t['thrower_slot'] * 4))
            anims[key] = {'slot': t['thrower_slot'], 'mode': mode, 'steps': [
                {'frame': add_frame(rec), 'ticks': ticks, 'boxes': {f'{k:02X}': v for k, v in boxes.items()}}
                for ticks, rec, flags, boxes in steps]}
        adders[name] = add_frame
        specials, extra_pals = load_specials(prom, cid, add_frame, add_effect_frame)
        out['characters'][name] = {'id': cid, 'throws': {}, 'specials': specials, 'effect_palettes': extra_pals,
                                   'block_palettes': rom.block_palettes(prom, cid), 'palette': palette, 'palette_mirror': mirror, 'frames': frames, 'anims': anims,
                                   'physics': rom.physics(prom, cid)}
    # throws, every thrower x every exported victim, from the ROM tables (throwscripts.py); frames go into each
    # character's own frame list (thrower frames into the thrower's, victim frames into the victim's)
    import throwscripts
    tables = json.load(open(os.path.join(HERE, 'throw_tables.json')))
    for name in names:
        cid = rom.CHARS[name]
        for key, info in (tables.get(name) or {}).items():
            if not info or info[0] == 'strike': continue
            fmt, tabs = info[0], [int(t, 16) for t in info[1:]]
            built = throwscripts.build(prom, cid, key, fmt, tabs, [rom.CHARS[v] for v in names])
            if not built: continue
            first = next(iter(built.values()))
            timeline = [[adders[name](int(r[0], 16)), round(r[1]), round(r[2])] for r in first]
            victims = {}
            for v, rows in built.items():
                vn = rom.CAST[v]
                victims[vn] = [[adders[vn](int(r[3], 16)) if r[3] else -1, round(r[4]), round(r[5]), r[6], r[7], r[10]] for r in rows]
            caps = load_throws(cid).get(key, {})
            out['characters'][name]['throws'][key] = {'slot': caps.get('thrower_slot'), 'inputs': caps.get('inputs', ''),
                                                      'table': info, 'timeline': timeline, 'victims': victims}
    out['tiles'] = len(tile_map)
    os.makedirs(outdir, exist_ok=True)
    # sprite tiles: our numbering, 128 bytes each; .neo/MAME order interleaves C1 (even bytes) and C2 (odd bytes)
    region = bytearray(128 * (TILE_BASE + len(tile_map)))
    for code, ours in tile_map.items(): region[ours * 128:(ours + 1) * 128] = crom[code * 128:(code + 1) * 128]
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'), indent=1)
    write_c(out, outdir, mv)
    return out

def write_c(out, outdir, mv):
    """Const tables for the 68000. Layout documented in kof95_chars.h."""
    h, c = [], []
    h.append('/* Generated by tools/kof95/export.py from the KOF95 ROM + moves.json. Do not edit. */')
    h.append('#ifndef KOF95_CHARS_H\n#define KOF95_CHARS_H\n#include <stdint.h>\n')
    h.append('typedef struct { int16_t dx, dy; uint8_t cols, rows, hflip, vflip; const uint16_t *tiles; } kpart_t;   /* tiles: cols*rows, column-major, 0 = empty */')
    h.append('typedef struct { uint8_t nparts; const kpart_t *parts; } kframe_t;')
    h.append('typedef struct { uint16_t frame; uint8_t ticks; } kstep_t;')
    h.append('typedef struct { uint8_t nsteps, hold; const kstep_t *steps; } kanim_t;   /* hold: 1 = stop on the last step, 0 = loop */')
    h.append('typedef struct { int32_t walk_fwd, walk_back, jump_vy0, gravity, jump_dx; } kphys_t;   /* 16.16 px per frame */')
    h.append('typedef struct { const char *name; const uint16_t *palette, *palette_mirror; const kframe_t *frames; const kanim_t *anims; kphys_t phys; } kchar_t;   /* palette_mirror: second player colours in a mirror match */\n')
    moves = [m for m, _ in sorted(mv['slots'].items(), key=lambda kv: kv[1])]
    h.append('enum { ' + ', '.join(f'KA_{m.upper()}' for m in moves) + ', KA_COUNT };')
    names = list(out['characters'])
    h.append('enum { ' + ', '.join(f'KC_{n.upper()}' for n in names) + ', KC_COUNT };')
    h.append('extern const kchar_t kof95_chars[KC_COUNT];\n#endif')
    c.append('/* Generated by tools/kof95/export.py. Do not edit. */\n#include "kof95_chars.h"\n')
    fx = lambda v: str(int(round(v * 65536)))
    for n in names:
        ch = out['characters'][n]
        c.append(f'static const uint16_t {n}_pal[16] = {{' + ', '.join(f'0x{v:04X}' for v in ch['palette']) + '};')
        c.append(f'static const uint16_t {n}_palm[16] = {{' + ', '.join(f'0x{v:04X}' for v in ch['palette_mirror']) + '};')
        for fi, fr in enumerate(ch['frames']):
            for pi, p in enumerate(fr['parts']):
                flat = [t for col in p['tiles'] for t in col]
                c.append(f'static const uint16_t {n}_f{fi}_p{pi}[] = {{' + ', '.join(map(str, flat)) + '};')
            c.append(f'static const kpart_t {n}_f{fi}[] = {{' + ', '.join(
                f'{{{p["dx"]}, {p["dy"]}, {len(p["tiles"])}, {len(p["tiles"][0])}, {p["hflip"]}, {p["vflip"]}, {n}_f{fi}_p{pi}}}'
                for pi, p in enumerate(fr['parts'])) + '};')
        c.append(f'static const kframe_t {n}_frames[] = {{' + ', '.join(f'{{{len(fr["parts"])}, {n}_f{fi}}}' for fi, fr in enumerate(ch['frames'])) + '};')
        for m in moves:
            a = ch['anims'][m]
            c.append(f'static const kstep_t {n}_{m}[] = {{' + ', '.join(f'{{{s["frame"]}, {s["ticks"]}}}' for s in a['steps']) + '};')
        c.append(f'static const kanim_t {n}_anims[KA_COUNT] = {{' + ', '.join(
            f'{{{len(ch["anims"][m]["steps"])}, {1 if ch["anims"][m]["mode"] == "hold" else 0}, {n}_{m}}}' for m in moves) + '};')
    c.append('const kchar_t kof95_chars[KC_COUNT] = {')
    for n in names:
        p = out['characters'][n]['physics']
        c.append(f'  {{"{n}", {n}_pal, {n}_palm, {n}_frames, {n}_anims, {{{fx(p["walk_fwd"])}, {fx(p["walk_back"])}, {fx(p["jump_vy0"])}, {fx(p["gravity"])}, {fx(p["jump_dx"])}}}}},')
    c.append('};')
    open(os.path.join(outdir, 'kof95_chars.h'), 'w').write('\n'.join(h) + '\n')
    open(os.path.join(outdir, 'kof95_chars.c'), 'w').write('\n'.join(c) + '\n')

if __name__ == '__main__':
    outdir = sys.argv[1]; names = sys.argv[2:] or ['terry', 'kyo', 'ryo', 'robert']
    if names == ['all']: names = rom.CAST
    o = export(names, outdir)
    for n, ch in o['characters'].items():
        print(f'{n}: {len(ch["frames"])} frames, {sum(len(a["steps"]) for a in ch["anims"].values())} steps')
    print(f'tiles {o["tiles"]} ({o["tiles"] * 128 // 1024} KB), C1/C2 {(o["tiles"] + TILE_BASE) * 64 // 1024} KB each')
