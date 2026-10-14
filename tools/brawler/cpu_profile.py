#!/usr/bin/env python3
"""68000 CPU profile of a brawler run (docs/brawler_cpu_budget.md): a voice note's bundle replayed in a Geolith core built
with the profiler patch (tools/brawler/cpu_profile_core.patch: cycles per instruction, exclusive per function and
inclusive through a shadow call stack, snapshots at every game_tick entry), the build's symbols from GAME/build/rom.elf.

    python3 cpu_profile.py BUNDLE_DIR OUT.json [--game GAME_DIR] [--core PROFILING_CORE.so] [--pc-window F0 F1]

The core: copy geolith/, `patch -p1 < cpu_profile_core.patch`, `make -C libretro`. GAME_DIR = the build the note was
played on (its brawler.neo sha256 = meta.json rom_sha256; else the profile is of another program). Per tick (one
game_tick entry to the next): every function's exclusive / inclusive cycles, the wait loop's cycles (crt0 do_game's
spin = idle), the game's own CPU % (hud_min_spins as main.c computes it), and the scene (fighters on, projectiles on)."""
import ctypes as C, json, os, struct, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(REPO, 'tools', 'feedback'))
import harness as H

FRAME = 202752                                    # 68000 cycles per video frame (12 MHz / 59.1856 Hz)
NFN = 8192; BANKWIN, BIOS = 8190, 8191

def symbols(elf):
    out = subprocess.run(['m68k-linux-gnu-nm', '-n', elf], capture_output=True, text=True, check=True).stdout
    syms = []
    for ln in out.splitlines():
        a, t, n = ln.split()[:3] if len(ln.split()) >= 3 else (None, None, None)
        if t in ('t', 'T', 'W') and int(a, 16) < 0x200000 and not n.startswith('.'): syms.append((int(a, 16), n))
    syms.sort(); names = []; mp = np.zeros(0x100000, np.uint16); ent = np.zeros(0x100000, np.uint16); last = -1
    for i, (a, n) in enumerate(syms):
        if a == last: continue
        last = a; k = len(names); names.append(n)
        end = syms[i + 1][0] if i + 1 < len(syms) else 0x200000
        mp[a >> 1:end >> 1] = k; ent[a >> 1] = k + 1
    return names, mp, ent

def main():
    a = sys.argv[1:]; bundle, out = a[0], a[1]
    game = a[a.index('--game') + 1] if '--game' in a else H.GAME
    core_path = a[a.index('--core') + 1] if '--core' in a else '/data/tmp/cpuprof/geolith/libretro/geolith_libretro.so'
    import pull
    pull.CORE = core_path
    names, mp, ent = symbols(os.path.join(game, 'build', 'rom.elf'))
    names += [''] * (NFN - len(names)); names[8189] = '(interrupt entry)'; names[BANKWIN] = '(P2 bank window)'; names[BIOS] = '(BIOS)'
    layout, fsize, states, syms = H._layout(game)
    meta = json.load(open(os.path.join(bundle, 'meta.json')))
    rom = pull.find_rom(meta)
    core = pull.Core(rom, meta.get('system_type', 'mvs'), meta.get('hw', 'mvs'), meta.get('memcard', 'on'))
    dll = core.core
    for f in ('retro_neoscan_prof_snap', 'retro_neoscan_prof_incl', 'retro_neoscan_prof'): getattr(dll, f).restype = C.POINTER(C.c_uint32)
    dll.retro_neoscan_prof_ticks.restype = C.c_uint32
    mp_c = mp.ctypes.data_as(C.POINTER(C.c_uint16)); ent_c = ent.ctypes.data_as(C.POINTER(C.c_uint16))
    dll.retro_neoscan_prof_setup(mp_c, ent_c, C.c_uint32(syms['game_tick']))
    snap = np.ctypeslib.as_array(dll.retro_neoscan_prof_snap(), shape=(4, 2, NFN))
    dll.retro_get_memory_data.restype = C.c_void_p; dll.retro_get_memory_size.restype = C.c_size_t
    raw = open(os.path.join(bundle, 'inputs.bin'), 'rb').read()
    _, _, W, P = struct.unpack_from('<4sIQQ', raw)
    pads = [struct.unpack_from('<HH', raw, 24 + 4 * i) for i in range(P - W)]
    core.load(open(os.path.join(bundle, 'snap_%d.state' % W), 'rb').read())
    ram = (C.c_uint8 * dll.retro_get_memory_size(2)).from_address(dll.retro_get_memory_data(2))
    def rd(addr, n): v = bytes(ram[addr - 0x100000:addr - 0x100000 + n]); return int.from_bytes(v, 'big')
    S_OFF, S_PROJ = states.index('S_OFF') if 'S_OFF' in states else states.index('OFF'), None
    try: S_PROJ = states.index('PROJ')
    except ValueError: pass
    so, ss = layout['state']
    def scene():
        f = [rd(syms['fighters'] + i * fsize + so, ss) for i in range(8)]
        p = [rd(syms['projectiles'] + i * fsize + so, ss) for i in range(8)] if 'projectiles' in syms else []
        return {'fighters': sum(1 for s in f if s != S_OFF), 'enemies': sum(1 for s in f[2:] if s != S_OFF),
                'proj': sum(1 for s in p if s != S_OFF), 'p1': states[f[0]] if f[0] < len(states) else f[0],
                'hit': sum(1 for s in f[2:] if s != S_OFF and states[s] in ('HITSTUN', 'KNOCKDOWN', 'THROWN', 'GRABBED', 'DOWN'))}
    use = [n for n in ('hud_min_spins', 'hud_tick', 'mode', 'phase', 'sf_who') if n in syms]
    win = [int(a[a.index('--pc-window') + 1]), int(a[a.index('--pc-window') + 2])] if '--pc-window' in a else None
    pcarr = np.ctypeslib.as_array(dll.retro_neoscan_prof(0), shape=(0x100000,)); pc0 = None
    ticks = []; prev = None; seen = 0; game_cpu = []
    lastt = {'t': None, 's': None}
    for i, (p0, p1) in enumerate(pads):
        if win and W + i == win[0]: pc0 = pcarr.copy()
        if win and W + i == win[1]: pcw = pcarr - pc0
        core.frame(p0, p1)
        n = dll.retro_neoscan_prof_ticks()
        sc = scene()
        t = rd(syms['hud_tick'], 2); s = rd(syms['hud_min_spins'], 2)
        if lastt['t'] is not None and t != lastt['t'] and (t & 15) == 0 and lastt['s'] not in (None, 0xFFFF):
            idle = (lastt['s'] * 7) >> 8; game_cpu.append((W + i, 0 if idle >= 100 else 100 - idle))
        lastt['t'], lastt['s'] = t, s
        for k in range(max(seen, n - 3), n):
            cur = snap[k & 3].astype(np.int64)
            if prev is not None:
                d = cur - prev
                ticks.append({'frame': W + i, 'scene': sc, 'excl': d[0], 'incl': d[1]})
            prev = cur.copy()
        seen = n
    # summary: exclusive / inclusive per function, per tick
    idle_id = names.index('do_game')
    rows = []
    for tk in ticks:
        tot = int(tk['excl'].sum()); idle = int(tk['excl'][idle_id])
        rows.append({'frame': tk['frame'], 'total': tot, 'idle': idle, 'busy': tot - idle, **tk['scene']})
    E = np.array([tk['excl'] for tk in ticks]); I = np.array([tk['incl'] for tk in ticks])
    busy = np.array([r['busy'] for r in rows])
    res = {'bundle': bundle, 'game': game, 'frames': len(pads), 'ticks': len(ticks), 'names': names,
           'rows': rows, 'game_cpu': game_cpu}
    pc = np.ctypeslib.as_array(dll.retro_neoscan_prof(0), shape=(0x100000,)).copy()   # whole run, per word address
    if win: pc = pcw                                   # --pc-window F0 F1: the per-PC cycles of those frames only
    np.savez_compressed(os.path.splitext(out)[0] + '.npz', excl=E, incl=I, busy=busy, pc=pc)
    json.dump(res, open(out, 'w'))
    print('ticks', len(ticks), 'busy mean', int(busy.mean()), 'max', int(busy.max()), 'frame', FRAME)
    m = E.mean(0); o = np.argsort(-m)[:25]
    for k in o: print('excl %-32s %8d  %5.1f%%' % (names[k], m[k], 100 * m[k] / FRAME))
    m = I.mean(0); o = np.argsort(-m)[:40]
    for k in o: print('incl %-32s %8d  %5.1f%%' % (names[k], m[k], 100 * m[k] / FRAME))

if __name__ == '__main__': main()
