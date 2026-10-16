#!/usr/bin/env python3
"""Samurai Shodown II's referee (Kuroko) coming to the front to speak (note 20261015-221208-e03d: "the referee creeping
in side to side and jumping on the foreground and deliver the message"), decoded from the 68000 code and measured in
our emulator; exported for the brawler's announcer (game.json "referee", main.c "the referee").

Where it lives in SS2 [code] (study /data/neogeo_dict/samsho2/README.md, section "The referee's speech"):
  KURO-SYS ($769A creates it, code $DC2C) = the referee in the background of every fight (table 19, y 200 = 24 px behind
  the fighters' floor 224). At a round's end ($DD9E: $100AD5 set) $E37A picks a list of end states from $E400[$100ADE]
  ($100ADE = 1 + 2 (winner +$BA = $80) + 1 (the loser's last round) + 6 (bit 7 of $100AD5)); state 12 = $E5D0 (jump table
  $E482) is the speech. It plays only in a one-player game ($100AED != 3, $100AED & $100AD5 = the human won) after the
  matches $E5C2[$100AEE] marks (1, 6, 10 -> messages 0-2 of $206FDC[language]: "HORRIBLE ATMOSPHERE.", ...):
    $E5D0  walk: $E32E dir 2 (right) / 3 (left) = table 19 anim $E33E[2 d + $100AD0] (56 / 35: the sidestep, the
           flags low), vx +-256 (8.8) until his screen x (& ~3) = 128 or 192 ($E61A: 192 when $106906 < 160)
    $E64E  one frame of the stand (anim 31), then $E668: Kuroko's own fighter table 17, anim 22 (the jump), palette add
           $98, vy -2432 (8.8), sound $2B panned; +$7A = $4040 written but never shown (no shrink measured)
    $E69E  every frame vy += 96; rising: behind the fighters (prio $41); falling: anim 26, prio $81 (in front);
           y >= 232 (8 px nearer the camera than the fighters' floor): anim 178 (the landing), y = 232, his
           shadow (KURO KAGE: table 19 anim 232), his landing voice ($278B8[char])
    $E724  the landing's end -> anim 1 (Kuroko's idle), MES-WIND: table 19 anim 625 (a 12 x 4 tile window, fixed
           palette 134) at (176, 112), or (144, 112) flipped ($106906 < 160); +$7B $E0 -> 0 by $20 a frame = the
           window opening (SCB2 vertical shrink $1F .. $FF, centred: measured in VRAM); MESSDISP types the message on
           the fix layer (8 x 16 font, a letter every 2 frames [meas], 16 px inside the window); closing: +$7B + $10
           a frame back to $E0, then gone.

    python3 referee_ss2.py capture      the speech played in our emulator (Haohmaru's vs state, a one-player match
                                        win poked) -> /data/neogeo_dict/samsho2/referee/capture.json (+ palette RAM)
    python3 referee_ss2.py check        the decoded model vs the capture (anims, x, y per frame, window, letters)
    python3 referee_ss2.py OUTDIR       the export: OUTDIR/referee.h, tiles appended to OUTDIR/bm_c1/c2.bin"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss2, neo2 as N

DATA = '/data/neogeo_dict/samsho2/referee'
STATE = '/data/neogeo_dict/samsho2/cap/p1_00.state'
CAPF = 1400
REF_PAL = 64                     # main.c REF_PAL: the fighter slots 6-7's palettes (a bonus game loads only its player's)
FLOOR = 224                      # SS2's fighters' floor (the landing test y > 224, study "The engine's frame")
FEET = 16                        # SS2's feet line = the object's Y - 16 (export_ss2.FEET, $3368)


def imm16(addr, op):
    """the 16-bit immediate of the instruction at addr whose first word is op (a decode that refuses a moved ROM)"""
    assert N.u16(addr) == op, (hex(addr), hex(N.u16(addr)), hex(op))
    return N.s16(addr + 2)


def decode():
    """the speech's numbers read in the code (see the docstring)"""
    t = lambda d: N.u16(0xE33E + 2 * d)                         # $E32E: anim = $E33E[(2 d + $100AD0) * 2], $100AD0 = 0
    d = dict(walk_vx=imm16(0xE616, 0x323C), walk_right=t(4), walk_left=t(6), stand=t(0),
             targets=(imm16(0xE61A, 0x343C), imm16(0xE628, 0x343C)),
             jump_table=imm16(0xE66E, 0x3D7C), jump_anim=imm16(0xE674, 0x3D7C), jump_pal=N.u8(0xE67D), jump_vy=imm16(0xE680, 0x3D7C),
             grav=imm16(0xE6AC, 0x066E), front_prio=imm16(0xE6BA, 0x3D7C), fall_anim=imm16(0xE6C0, 0x3D7C),
             land_y=imm16(0xE6C6, 0x0C6E), land_anim=imm16(0xE6D0, 0x3D7C), idle_anim=imm16(0xE72C, 0x3D7C),
             back_y=imm16(0xDC4E, 0x3D7C), shadow_anim=imm16(0xE7A8, 0x3D7C),
             win_anim=imm16(0xE7E0, 0x3D7C), win_zoom=N.u8(0xE7E9), win_open=N.u8(0xE825), win_close=N.u8(0xE8A9),
             win_x=(imm16(0xE7EC, 0x3D7C), imm16(0xE808, 0x3D7C)), win_y=imm16(0xE7F2, 0x3D7C))
    assert N.u16(0xE6A6) == 0x046E and N.u16(0xE822) == 0x042E and N.u16(0xE8A6) == 0x062E
    return d


# ---------------- capture ----------------
def capture():
    import shutil
    import cap_ss2 as C
    d = '/data/tmp/referee/cap'
    shutil.rmtree(d, ignore_errors=True)
    C.run(d, '4:-', load=STATE, vram=False, frames=[1], sndlog=False)
    r = C.ram(d, 1); a1, a2 = C.players(r)
    x = C.u16(r, a1 - 0x100000 + 0x4E) + 50                      # wins_ss2.play's setup: P2 50 px ahead, P1's A lands,
    pk = [f'{f}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}' for f in range(1, 4)] + ['40:100AC6=01']   # the clock at 1
    pk += [f'{f}:{a2 + 0xF1:X}=01' for f in (5, 100)]          # P2's last round (the decrement at the round's end -> 0)
    pk += [f'{f}:100AED=01,100AEE=01' for f in (5, 100, 199, 300)]   # a one-player game (P1 human), after match 1
    shutil.rmtree(d, ignore_errors=True)
    C.run(d, f'10:-,3:a,{CAPF - 13}:-', load=STATE, vram=True, frames=range(900, CAPF), pokes=';'.join(pk), sndlog=True,
          extra={'PALDUMP': '1030,1100'})
    tasks = {b'KURO-SYS': 'ref', b'MES-WIND': 'win', b'KUROKAGE': 'shadow'}
    rows = []
    for f in range(900, CAPF):
        r = C.ram(d, f); v = open(f'{d}/vram{f}.bin', 'rb').read()
        w = lambda a: v[a * 2] << 8 | v[a * 2 + 1]
        row = {'f': f}
        for o in range(0x2000, 0xA000, 0x120):
            n = tasks.get(bytes(r[o + 4:o + 12]))
            if not n: continue
            row[n] = dict(pc=C.u32(r, o), table=C.u16(r, o + 0x64), anim=C.u16(r, o + 0x66), step=C.u32(r, o + 0x6C),
                          x=C.s16(r, o + 0x5C), y=C.s16(r, o + 0x5E), vy=C.s16(r, o + 0x56), prio=C.u16(r, o + 0x76),
                          zoom=C.u16(r, o + 0x7A), facing=r[o + 0x7F], pal=r[o + 0x81])
        row['letters'] = sum(1 for c in range(40) if (w(0x7000 + c * 32 + 12) & 0xFFF) not in (0x20, 0xFF, 0)) if 'win' in row else 0
        rows.append(row)
    pals = {}
    for f in (1030, 1100):
        raw = open(f'{d}/cap.txt.pal{f}', 'rb').read()
        pals[f] = [[struct.unpack_from('>H', raw, (p * 16 + k) * 2)[0] for k in range(16)] for p in range(256)]
    os.makedirs(DATA, exist_ok=True)
    json.dump({'rows': rows, 'pal_walk': pals[1030], 'pal_front': pals[1100]}, open(f'{DATA}/capture.json', 'w'))
    first = next(x['f'] for x in rows if x.get('ref', {}).get('pc') == 0xE5D0)
    print(f'capture: the speech from frame {first}, {DATA}/capture.json')


# ---------------- the model (what main.c plays) vs the capture ----------------
def model(D, x0, target):
    """frames from the walk's first: (table, anim, x, y, front) per frame, then the landing frame index"""
    out = []; x = x0 << 8; y = D['back_y']; dx = D['walk_vx'] if target > x0 else -D['walk_vx']
    anim = D['walk_right'] if dx > 0 else D['walk_left']
    while True:                                                 # the walk ($E5D0): moved, then compared
        x += dx; out.append((19, anim, x >> 8, y, 0))
        if (x >> 8) & ~3 == target: break
    out.append((19, D['stand'], x >> 8, y, 0))                  # $E64E: the stand, one frame
    yy = (y << 8) + D['jump_vy']; vy = D['jump_vy']; front = 0; a = D['jump_anim']   # $E668: vy set, the move
    out.append((D['jump_table'], a, x >> 8, yy >> 8, front))
    while True:                                                 # $E69E: the routine first (vy + g, the landing test
        vy += D['grav']                                         # on the y it has), then the object moves
        if vy >= 0: front = 1; a = D['fall_anim']
        if front and (yy >> 8) >= D['land_y']: break
        yy += vy; out.append((D['jump_table'], a, x >> 8, yy >> 8, front))
    land = len(out)
    return out, land


def check():
    D = decode(); cap = json.load(open(f'{DATA}/capture.json'))
    rows = [r for r in cap['rows'] if 'ref' in r]
    i0 = next(i for i, r in enumerate(rows) if r['ref']['pc'] == 0xE5D0)
    m, land = model(D, rows[i0]['ref']['x'], D['targets'][1])   # (this capture: $106906 < 160 -> 192)
    bad = 0
    for k, (t, a, x, y, fr) in enumerate(m):
        r = rows[i0 + 1 + k]['ref']
        got = (r['table'], r['anim'], r['x'], r['y'], 1 if r['prio'] & 0x80 else 0)
        if got != (t, a, x, y, fr): bad += 1; print('frame', rows[i0 + 1 + k]['f'], 'model', (t, a, x, y, fr), 'SS2', got)
    lr = rows[i0 + 1 + land]['ref']
    ok_land = (lr['anim'], lr['y']) == (D['land_anim'], D['land_y'])
    print(f'walk + jump: {len(m) - bad} / {len(m)} frames = SS2 (table, anim, x, y, in front); landing frame: anim {lr["anim"]} y {lr["y"]}', 'OK' if ok_land else 'DIFF')
    wz = [r['win']['zoom'] & 0xFF for r in rows if 'win' in r]
    print('window +$7B per frame (changes):', ' '.join(f'{z:02X}' for i, z in enumerate(wz) if not i or z != wz[i - 1]))
    inc = [b['f'] for a, b in zip(rows, rows[1:]) if b['letters'] > a['letters']]
    full = next(r['f'] for r in rows if r.get('win', {}).get('zoom', 1) & 0xFF == 0)
    close = next(b['f'] for a, b in zip(rows, rows[1:]) if 'win' in a and 'win' in b and b['win']['zoom'] & 0xFF > a['win']['zoom'] & 0xFF)
    inc = [f for f in inc if f < close]
    print(f'window fully open at frame {full}; letters: the first at {inc[0]}, then every {sorted({b - a for a, b in zip(inc, inc[1:])})} '
          f'frames ({len(inc)} letters, the last at {inc[-1]}); closing from {close} ({close - inc[-1]} frames after the last letter)')
    print('decode:', D)
    return bad == 0 and ok_land


# ---------------- export ----------------
HIT_ANIMS = [('fly', 220), ('down', 222), ('getup', 138)]


def cells_of(t, anim, pal_add):
    """an animation -> its steps [(ticks, end, [(dx, dy, cols)] facing right / mirrored)]; cols = [[(tile code, attr)]]"""
    out = []
    for st in ss2.parse_anim(t, anim):
        assert not [c for c in st['cmds'] if c[0] not in ('end', 'boxes', 'sound', 'sound_pan')], (t, anim, st['cmds'])
        faces = []
        for flip0 in (0, 1):
            parts = []
            nl = len(st['layers'])
            for li in ss2.ORDER[bool(st['flags'] & 0x4000)][nl - 1]:
                w = st['layers'][li]; flip = flip0 ^ (w >> 15)
                sd, left, top = ss2.layer_box(w, 0, 0, flip)
                _, cells = ss2.sprite_cells(w & 0x7FFF)
                cols = cells[::-1] if flip else cells
                pc = []
                for col in cols:
                    cc = []
                    for cell in col:
                        if cell is None: cc.append(None); continue
                        tl, at = cell; at = (at + ((pal_add if li < 3 else 0) << 8)) & 0xFFFF ^ flip
                        cc.append((tl | (at >> 4 & 0xF) << 16, at))
                    pc.append(cc)
                parts.append((left, (top - 512 if top > 256 else top) + FEET, pc))   # (from his feet: SS2's Y - 16)
            faces.append(parts)
        out.append((st['ticks'], st['end'], faces))
    return out


WIN_EXTRA = 1   # the window's added middle columns (note: "HORRIBLE ATMOSPHERE." = 20 letters; SS2's 12 tiles fit 18)


def widen_window(steps, extra=WIN_EXTRA):
    """SS2's 12 x 4 window, `extra` plain middle columns repeated in (its corners, edges and pointer kept): on the side
    of the pointer away from him (face 0, the window on his left: before it, the part's x 16 px a column further left;
    mirrored, on his right: after it), so the pointer and the side over him stay where SS2 puts them"""
    out = []
    for ticks, end, faces in steps:
        nf = []
        for fi, parts in enumerate(faces):
            assert len(parts) == 1, 'the window: one part'
            dx, dy, cols = parts[0]
            mid = list(range(1, len(cols) - 1))
            tail = [i for i in mid if sum(cols[j] == cols[i] for j in mid) == 1]
            assert len(tail) == 1, 'the window: one pointer column'
            t = tail[0]; at = t if fi == 0 else t + 1
            rep = t - 1 if fi == 0 else t + 1
            assert rep in mid, 'the window: a plain column next to the pointer'
            cols = cols[:at] + [list(cols[rep]) for _ in range(extra)] + cols[at:]
            nf.append([(dx if fi else dx - 16 * extra, dy, cols)])
        out.append((ticks, end, nf))
    return out


def build(outdir):
    D = decode(); cap = json.load(open(f'{DATA}/capture.json'))
    c1p, c2p = os.path.join(outdir, 'bm_c1.bin'), os.path.join(outdir, 'bm_c2.bin')
    c1, c2 = bytearray(open(c1p, 'rb').read()), bytearray(open(c2p, 'rb').read())
    C = N.load()[1]; remap = {}; pals = []
    def tile(code):
        if not N.tile(code).any(): return 0
        if code not in remap:
            remap[code] = len(c1) // 64; tt = C[code * 128:(code + 1) * 128]; c1.extend(tt[0::2]); c2.extend(tt[1::2])
        return remap[code]
    def pal(p, src):
        k = (src, p)
        if k not in pals: pals.append(k)
        return REF_PAL + pals.index(k)
    anims = [('walk_r', 19, D['walk_right'], 0, 'walk'), ('walk_l', 19, D['walk_left'], 0, 'walk'), ('stand', 19, D['stand'], 0, 'walk'),
             ('rise', D['jump_table'], D['jump_anim'], D['jump_pal'], 'front'), ('fall', D['jump_table'], D['fall_anim'], D['jump_pal'], 'front'),
             ('land', D['jump_table'], D['land_anim'], D['jump_pal'], 'front'), ('idle', D['jump_table'], D['idle_anim'], D['jump_pal'], 'front'),
             ('shadow', 19, D['shadow_anim'], 0, 'front'), ('window', 19, D['win_anim'], 0, 'front')]
    # hit by the player's fury (note 20261015-221208-e03d, the quirk after his speech): Kuroko's own fighter reactions
    # in his table 17 (export_ss2 MOVES: the knockdown flight 220, its landing / lying 222, the get-up 138)
    anims += [(nm, D['jump_table'], a, D['jump_pal'], 'front') for nm, a in HIT_ANIMS]
    h = ['/* Generated by tools/samsho2/referee_ss2.py (Samurai Shodown II\'s referee coming to the front to speak:',
         ' * KURO-SYS state 12, $E5D0-$E772; MES-WIND $E7CE). Do not edit. */', '#ifndef REFEREE_H', '#define REFEREE_H',
         '/* a part (bonus.h bonus_obj_t): x, y of its top left from the object\'s feet, w x h tiles column-major (tile low word, attribute with',
         ' * its palette REF_PAL-based); a step: its parts as SS2 draws them (face 0) and mirrored, ticks: it shows ticks + 1',
         ' * frames (the object clock counts 1 .. ticks + 1, measured); an animation: its steps, loop (else it ends after the last) */',
         'typedef bonus_obj_t ref_part_t;   /* bonus.h\'s: x, y, w, h, map (main.c bn_put draws it) */',
         'typedef struct { uint8_t ticks, n; const ref_part_t *p[2]; } ref_step_t;',
         'typedef struct { uint8_t n, loop; const ref_step_t *s; } ref_anim_t;']
    names = []; maxw = {'walk': 0, 'front': 0}; nparts = 0
    for nm, t, a, pa, grp in anims:
        steps = cells_of(t, a, pa)
        if nm == 'window': steps = widen_window(steps)
        srows = []
        for si, (ticks, end, faces) in enumerate(steps):
            fp = []
            for fi, parts in enumerate(faces):
                pn = []
                for pi, (dx, dy, cols) in enumerate(parts):
                    words = []
                    for col in cols:
                        for cell in col:
                            if cell is None: words += [0, 0]; continue
                            code, at = cell; nt = tile(code)
                            if not nt: words += [0, 0]; continue
                            words += [nt & 0xFFFF, pal(at >> 8, 'walk' if t == 19 and nm != 'window' and nm != 'shadow' else 'front') << 8 | ((nt >> 16) & 0xF) << 4 | (at & 0xF)]
                    v = f'ref_{nm}{si}_{fi}_{pi}'
                    h.append(f'static const uint16_t {v}m[] = {{ {", ".join(f"0x{x:04X}" for x in words)} }};')
                    pn.append(f'{{ {dx}, {dy}, {len(cols)}, {len(cols[0])}, {v}m }}')
                    if nm != 'window': maxw[grp] = max(maxw[grp], len(cols) * len(parts))
                    nparts = max(nparts, len(parts))
                h.append(f'static const ref_part_t ref_{nm}{si}_{fi}[] = {{ {", ".join(pn)} }};')
                fp.append(f'ref_{nm}{si}_{fi}')
            srows.append(f'{{ {ticks}, {len(faces[0])}, {{ {fp[0]}, {fp[1]} }} }}')
        h.append(f'static const ref_step_t ref_{nm}_s[] = {{ {", ".join(srows)} }};')
        names.append(f'{{ {len(steps)}, {1 if steps[-1][1] == "loop" else 0}, ref_{nm}_s }}')
        h.append(f'#define REF_{nm.upper()} {len(names) - 1}')
    h.append(f'static const ref_anim_t ref_anims[] = {{ {", ".join(names)} }};')
    words = []
    for src, p in pals:
        words += cap['pal_walk' if src == 'walk' else 'pal_front'][p]
    h.append(f'#define REF_NPAL {len(pals)}   /* SS2 palettes {[p for _, p in pals]} (palette RAM in the speech) */')
    h.append(f'static const uint16_t ref_pals[] = {{ {", ".join(f"0x{x:04X}" for x in words)} }};')
    h += [f'#define REF_WALK_VX {D["walk_vx"]}   /* 8.8 px a frame ($E616) */',
          f'#define REF_JUMP_VY {D["jump_vy"]}   /* 8.8 ($E680) */', f'#define REF_GRAV {D["grav"]}   /* 8.8 a frame ($E6AC) */',
          f'#define REF_BACK_DY ({D["back_y"]} - {FLOOR})   /* his lane: px from the fighters\' floor (KURO-SYS y 200) */',
          f'#define REF_LAND_DY ({D["land_y"]} - {FLOOR})   /* the landing: px nearer the camera than the floor ($E6C6) */',
          f'#define REF_WIN_X ({D["win_x"][1]} - {D["targets"][1]})   /* the window object\'s x - his (SS2: at 192 the window at 144, flipped) */',
          f'#define REF_WIN_Y ({D["win_y"]} - {D["land_y"]})   /* its y - his landed feet */',
          f'#define REF_WIN_ZOOM 0x{D["win_zoom"]:02X}   /* +$7B at its start: SCB2 vertical shrink 0xFF - this */',
          f'#define REF_WIN_OPEN 0x{D["win_open"]:02X}   /* its step a frame opening */', f'#define REF_WIN_CLOSE 0x{D["win_close"]:02X}   /* closing */',
          f'#define REF_WIN_W {12 + WIN_EXTRA}   /* the window\'s columns: SS2\'s 12 + {WIN_EXTRA} plain middle one(s) repeated */',
          f'#define REF_LETTER 2   /* frames a letter (MESSDISP, measured) */',
          f'#define REF_MAXW_BACK {maxw["walk"]}', f'#define REF_MAXW_FRONT {maxw["front"]}', '#endif']
    open(c1p, 'wb').write(bytes(c1)); open(c2p, 'wb').write(bytes(c2))
    open(os.path.join(outdir, 'referee.h'), 'w').write('\n'.join(h) + '\n')
    print(f'referee: {len(remap)} SS2 tiles ({len(remap) * 128 // 1024} KB) appended, {len(pals)} palettes, C ROM now {len(c1) // 64} tiles')


if __name__ == '__main__':
    if len(sys.argv) != 2: sys.exit(__doc__)
    if sys.argv[1] == 'capture': capture()
    elif sys.argv[1] == 'check': sys.exit(0 if check() else 1)
    else: build(sys.argv[1])
