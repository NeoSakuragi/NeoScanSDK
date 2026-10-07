#!/usr/bin/env python3
"""TODO #214 proof: the effects of KOF's shared effects bank (KOF98 table 38: handlers98.SHARED_FX) colour-exact in the
brawler, harness.py on a `make AI_OFF=1` build.

    python3 fx214_proof.py GAME_DIR [OUT]          every roster move that spawns one (CASES), P2 48 px ahead

Per move, KOF98 side (our emulator, tools/kof96/capture/romspecials98.trace with PALDUMP): palette RAM during the move;
the effect frames the move's states spawn (handlers98.step_effects) drawn from KOF's own data: every tile of the frame's
sprite definitions (KOF98's C ROM bytes) with the palette RAM slot its definition names. Brawler side, every frame of
the move: each of P1's effect entities showing a frame of the shared bank (build/bm_frames.json record '38:n'): the
sprites draw.s wrote for it (LSPC VRAM: SCB1 tile + attribute of each shown row, SCB3 heights), each tile's bytes in the
brawler's C ROM with the palette RAM words its attribute names. Colour-exact = the two multisets of (tile bytes, 16
palette words) equal for every shown effect frame, and palette RAM SFX_PAL.. = KOF's slots word for word. A frame on
which the sprite-per-line guard acted (main.c guard_hidden / guard_thinned: an entity hidden, a fury's effect thinned)
may show a part of the frame: there every drawn (tile, palette) must be one of KOF's ('budget' frames, counted apart;
a wrong tile or colour fails anywhere). The flush (TODO #216): the harness frame ends at scanline 0 (geolith); the
vblank IRQ comes at 249 and the tick (after the BIOS's SYSTEM_IO) flushes the last tick's VRAM queue from 257; the LSPC
reads the sprite tables for the first time on scanline 6 (geo_lspc.c LSPC_LINE_BUFSTART). A flush still running when
the frame ends (neo_cmd_count > 0: the rest of the queue, the positions, not written yet; the frames several entities
spawn on and every block moves: 300-440 words, done by scanline 5) is read from the rows its tiles were written with (main.c
col_trim, RAM), and a tap on the CPU's writes reads the line counter ($3C0006) where it ends (neo_cmd_count cleared):
ended before scanline 6 = drawn on time ('flush_past_frame_end'), at 6 or later = the frame's first lines show the
last frame's sprites ('late_flush', must be 0). A tick that missed its vblank ('tick_overruns': the move's video
frames minus its ticks) must not happen either. OUT/colours.json (per move: frames checked, mismatches, palettes)."""
import ctypes as C, json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
import rom96, handlers98 as H

OUT = '/data/tmp/fx214/out'
CASES = ['iori:fD', 'iori:dfD', 'rugal:fD', 'ralf:dD', 'ralf:dfD', 'ralf:uD', 'ralf:ufD', 'terry:C']
ROLES = {'D': '4:c', 'fD': '4:Rc', 'dD': '4:Dc', 'uD': '4:Uc', 'dfD': '4:DRc', 'ufD': '4:URc', 'C': '4:d'}   # romspecials_check
KOF = {'iori': 27, 'rugal': 36, 'ralf': 10, 'terry': 3}
NPJ, NF, MAX_COLS = 8, 8, 20                         # fighter.h NPJ, main.c NF, fighter.h MAX_COLS (col_trim_t)
SFX_PAL = int(re.search(r'#define SFX_PAL\s+(\d+)', open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'fighter.h')).read()).group(1))

def neo_c(path):
    raw = open(path, 'rb').read(); sizes = struct.unpack('<6I', raw[4:0x1C])
    return raw[0x1000 + sum(sizes[:5]):0x1000 + sum(sizes)]

def kof_side(m, crom, cid, inp, out):
    """KOF98: palette RAM during the move (PALDUMP every 8 frames of the trace) and each shared effect frame's
    expected (tile bytes, palette) multiset"""
    import romspecials98 as R, emu
    frames = list(range(R.START, R.START + 200, 8))
    orig = emu.run
    def run(*a, **k):
        k['extra'] = dict(k.get('extra') or {}, PALDUMP=','.join(map(str, frames))); return orig(*a, **k)
    R.C.emu.run = run
    try: rows, _, path = R.trace(cid, inp, 'close', inp.startswith('EX '), 200)
    finally: R.C.emu.run = orig
    pals = []
    for f in frames:
        d = open(f'{path}.pal{f}', 'rb').read()
        pals.append([list(struct.unpack('>16H', d[s * 32:s * 32 + 32])) for s in range(256)])
    k0 = next(i for i, r in enumerate(rows) if R.special(r['state']))
    states = sorted({r['state'] for r in rows[k0:] if R.special(r['state'])})
    eff = [e for e in H.step_effects(m, cid, states) if e['table'] == H.SHARED_FX['kof98']]
    seen = {(o['table'], o['state']) for r in rows[k0:] for o in r['objs']}
    expect, slots = {}, set()
    for e in eff:
        steps, _ = rom96.parse_anim(m, rom96.anim_addr(m, e['table'], rom96.state_slot(m, e['table'], e['fstate'])))
        for t, fi, fl, bx, raw, dx in steps:
            ms = []
            for p in rom96.frame_parts(m, e['table'], fi):
                sd = rom96.sdef(m, e['table'], p['sdef'])
                for col in sd['cols']:
                    for code in col:
                        if code is not None: ms.append((crom[code * 128:(code + 1) * 128], tuple(pals[0][sd['pal']])))
                if sd['cols']: slots.add(sd['pal'])
            expect[fi] = sorted(ms)
    const = all(p[s] == pals[0][s] for p in pals for s in slots)
    return {'effects': [{k: e[k] for k in ('state', 'step', 'kind', 'fstate', 'dx', 'dy', 'back')} for e in eff],
            'kof_spawned': sorted(st for tb, st in seen if tb == H.SHARED_FX['kof98'] and st in {e['fstate'] for e in eff}),
            'slots': sorted(slots), 'slots_constant': const, 'pal': {s: pals[0][s] for s in slots}}, expect

SPRITE_LINE = 6                                      # geolith geo_lspc.c LSPC_LINE_BUFSTART: the LSPC's first read of
                                                     # the sprite tables in a frame (scanline 0 = the harness frame's start)
FLUSH_EV = []                                        # this frame's flush ends: their scanlines
def flush_tap(b):
    """a tap on the 68000's writes: the scanline ($3C0006 >> 7, $F8 = scanline 0) at which each tick's vblank flush ends
    (SYS_vblankFlush clears neo_cmd_count)"""
    import harness
    core = b.core; core.retro_neoscan_m68k_read.restype = C.c_uint32
    cnt = b.syms['neo_cmd_count']
    def tap(addr, val, size):
        if addr == cnt and val == 0 and size == 2:
            FLUSH_EV.append(((core.retro_neoscan_m68k_read(0x3C0006, 2) >> 7) - 0xF8) % 264)
    b._flush_cb = harness.TAP_CB(tap)
    core.retro_neoscan_m68k_write_tap(b._flush_cb)

def brawler_side(b, game, name, role, expect, vram, palram, crom, recs):
    """every frame of the move: P1's shared-bank effect entities as drawn (VRAM) against KOF's expected multiset"""
    roster = [r['name'] for r in json.load(open(os.path.join(game, 'game.json')))['roster']]
    meter = json.load(open(os.path.join(game, 'game.json')))['meter']['max']
    b.pick(roster.index(name), unlock=True); b.run(10)
    for i in range(1, 8): b.place(i, x=1000, z=0)
    b.place(0, x=60, z=30); b.place(2, x=108, z=30); b.run(2); w = 0
    while b.states[b.fget(0, 'state')] != 'IDLE' and w < 300: b.run(1); w += 1
    b.fset(0, 'meter', meter)
    n, keys = ROLES[role].split(':')
    checked, bad, shown, budget, late, pending = 0, [], set(), 0, 0, []
    past, flush_lines, waiting, tk0 = 0, [], 0, 0
    def drawn(spr, nc, trims=None):
        ms = []
        for c, s in enumerate(range(spr, spr + nc)):
            h = (vram[0x8200 + s] if trims is None else trims[c]) & 0x3F
            for r in range(h):
                t, a = vram[s * 64 + 2 * r], vram[s * 64 + 2 * r + 1]
                code = t | ((a >> 4) & 0xF) << 16
                if code: ms.append((crom[code * 128:(code + 1) * 128], tuple(palram[(a >> 8) * 16:(a >> 8) * 16 + 16])))
        return sorted(ms)
    tk = lambda: b.r(b.syms['game_ticks'], 4)
    for f in range(400):
        b.pad = [set(keys), set()] if f < int(n) else [set(), set()]
        FLUSH_EV.clear()
        t0 = tk(); b.run(1, ''.join(b.pad[0]), ''); ticks = tk() - t0
        if f == 0: tk0 = t0
        if waiting:                                      # last frame's flush, still running at its end: where it ended
            ln = FLUSH_EV[0] if FLUSH_EV and FLUSH_EV[0] < 128 else None   # (this frame's first write of 0: the flush
                                                                    # crossing the boundary ends before anything else)
            flush_lines.append(ln)
            if ln is None or ln >= SPRITE_LINE: late += waiting
            else: past += waiting
            waiting = 0
        guard = b.r(b.syms['guard_hidden'], 1) + b.r(b.syms['guard_thinned'], 1)
        queued = b.r(b.syms['neo_cmd_count'], 2)        # VRAM words still queued: the flush runs past the frame's end
        for p in pending: bad.append(p)
        pending = []
        for i in range(NPJ):
            if b.states[b.pget(i, 'state')] != 'PROJ' or b.pget(i, 'owner') != b.base: continue
            sf = b.pget(i, 'shown_frame')
            if sf >= len(recs) or not recs[sf].startswith('38:'): continue
            fi = int(recs[sf].split(':')[1]); spr = b.pget(i, 'spr'); nc = b.pget(i, 'ncols')
            ms = drawn(spr, nc)
            checked += 1; shown.add(fi)
            if ms == expect.get(fi): continue
            if guard:                                    # the guard's frame: a part of it, every piece KOF's
                left = list(expect.get(fi) or [])
                if all(left.remove(x) is None if x in left else False for x in ms): budget += 1; continue
            if queued:                                   # an over-long tick (the queue's rest written at the next vblank:
                tr = [b.r(b.syms['col_trim'] + (NF + i) * 4 * MAX_COLS + 2 * c, 2) for c in range(nc)]   # its positions);
                if drawn(spr, nc, tr) == expect.get(fi): waiting += 1; continue   # its tiles as written, by its trims (RAM):
                                                                    # on time if the flush ends before SPRITE_LINE
            pending.append({'frame': f, 'entity': i, 'kof_frame': fi, 'tiles': len(ms), 'kof_tiles': len(expect.get(fi) or []),
                            'guard': guard, 'ticks': ticks, 'spr': spr, 'nc': nc})
        if f > 30 and b.states[b.fget(0, 'state')] != 'SPECIAL' and not any(
                b.states[b.pget(i, 'state')] == 'PROJ' and b.pget(i, 'owner') == b.base for i in range(NPJ)): break
    bad += pending
    overruns = max(0, (f + 1) - (tk() - tk0) - 1)        # vblanks without a tick start (a tick past its vblank loses
                                                         # one; the tick's start may fall either side of a frame's end)
    return {'entity_frames_checked': checked, 'mismatches': len(bad), 'bad': bad[:8], 'budget_frames': budget, 'late_flush': late,
            'flush_past_frame_end': past, 'flush_end_lines': sorted(set(flush_lines), key=lambda v: (v is None, v or 0)),
            'tick_overruns': overruns,
            'kof_frames_shown': sorted(shown),
            'kof_frames_all': sorted(expect)}

def main(game, out):
    from harness import Brawler
    os.makedirs(out, exist_ok=True)
    m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98'); kcrom = rom96.load(rom96.GAMES['kof98']['neo'])[1]
    gj = {r['name']: r for r in json.load(open(os.path.join(game, 'game.json')))['roster']}
    recs = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))
    hdr = open(os.path.join(game, 'build', 'bm_chars.h')).read()
    sfx = [int(k) for k in re.findall(r'kof98 (\d+)', re.search(r'#define SFX_NPAL .*', hdr).group(0))]
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    flush_tap(b)
    vram = (C.c_uint16 * 0x8800).from_address(b.core.retro_get_memory_data(3))
    palram = (C.c_uint16 * 8192).from_address(b.core.retro_get_memory_data(104))
    bcrom = neo_c(os.path.join(game, 'brawler.neo'))
    res = []
    for case in CASES:
        name, role = case.split(':')
        sp = gj[name]['specials']; inp = gj[name]['fury'] if role == 'C' else sp[role]
        k, expect = kof_side(m, kcrom, KOF[name], inp, out)
        r = brawler_side(b, game, name, role, expect, vram, palram, bcrom, recs[name])
        pal_eq = {s: list(palram[(SFX_PAL + sfx.index(s)) * 16:(SFX_PAL + sfx.index(s)) * 16 + 16]) == k['pal'][s] for s in k['slots']}
        row = {'case': case, 'input': inp, **{kk: v for kk, v in k.items() if kk != 'pal'}, 'palettes_equal': pal_eq, **r,
               'ok': r['mismatches'] == 0 and r['entity_frames_checked'] > 0 and all(pal_eq.values()) and k['slots_constant']
                     and r['late_flush'] == 0 and r['tick_overruns'] == 0
                     and set(r['kof_frames_shown']) == set(r['kof_frames_all'])}
        res.append(row); print(json.dumps({kk: v for kk, v in row.items() if kk not in ('effects', 'kof_frames_all')}), flush=True)
        json.dump(res, open(os.path.join(out, 'colours.json'), 'w'), indent=1)
    print('all ok' if all(r['ok'] for r in res) else 'FAIL', flush=True)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else OUT)
