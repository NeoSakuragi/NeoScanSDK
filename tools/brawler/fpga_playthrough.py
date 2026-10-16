#!/usr/bin/env python3
"""Whole-game playthrough of a brawler ROM on our emulator's core (harness.py; never MAME), for "it crashes on an FPGA"
reports (2026-10-16, Ismael's personalized ROM): power on, the attract demo (3 loops), coin, START, the select, every
stage with a simple bot as P1 (walks to the nearest enemy, A A B strings; P1's life kept up; a wave / boss the bot
cannot finish is cleared by the same test pokes as ramtrace.py campaign), the bonus games, the ending, back to the title.

    python3 fpga_playthrough.py --rom R.neo --game GAME_DIR [--build BUILD] --sys mvs-mvs|uni-aes --out DIR
           [--replay DIR/run.json]       the other run's inputs + pokes by tick (open loop: compare two builds)

Per frame it logs: game ticks, mode / phase / stage / wave, CRC32 of the picture and of the audio, the 68000's PC.
Faults flagged: ticks stalled (hang), PC outside cart ROM / work RAM / BIOS, a long stay in the BIOS after the game
started (BIOS error / exception screen), the attract or the play not reaching their screens. With a core built with
the odd-address and P2 hooks (BRAWLER_CORE: Musashi M68K_EMULATE_ADDRESS_ERROR logging instead of trapping,
retro_neoscan_aerr / _pstat / _bw) it also reports every odd-address word / long access (a real 68000 takes an
address error there; our normal core does not emulate it), the highest P ROM byte read through the $200000 window per
bank, and every write into $200000-$2FFFFF (bank register). Screenshots at each screen change: DIR/shots/.

That core: aerr_core.sh (aerr_core.patch on a copy of our Geolith tree, NEOSCAN_AERR=1) -> geolith_libretro_aerr.so,
taken here by default (BRAWLER_AERR=1; built when missing or older than the tree / the patch). --aerr 1 (default) LOGS
odd accesses and lets the access go on (a whole game is played); --aerr 2 does what a real 68000 does: the CPU takes
the address-error exception (UniBIOS: its ADDRESS ERROR screen; SNK's MVS BIOS: a reset). Found with it, 2026-10-16:
route nodes (rnode_t.speed, a word) read from the byte arrays export_bm.py wrote as `static const uint8_t
<f>_routes[]` (alignment 1: half of them landed on odd addresses; now aligned(2)). The release gate on top of it:
odd_access_proof.py (both BIOS, power-on + 3 attract loops + a short campaign, zero odd accesses)."""
import argparse, ctypes as C, json, os, subprocess, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)

if not os.environ.get('BRAWLER_CORE'): os.environ['BRAWLER_AERR'] = '1'   # (the address-error core, harness.aerr_core)
import harness
if not os.environ.get('BRAWLER_CORE'): harness.aerr_core()
from scenario import SYSTEMS

ap = argparse.ArgumentParser()
ap.add_argument('--rom', required=True); ap.add_argument('--game', default=os.path.join(HERE, '..', '..', 'examples', 'brawler'))
ap.add_argument('--build', default='build'); ap.add_argument('--sys', default='mvs-mvs'); ap.add_argument('--out', required=True)
ap.add_argument('--replay'); ap.add_argument('--attract', type=int, default=8100); ap.add_argument('--max', type=int, default=120000)
ap.add_argument('--aerr', type=int, default=1, help='1 log odd accesses, 2 also take the 68000 exception (a real CPU)')
ap.add_argument('--stop-after-stage', type=int, help='end the run when the campaign reaches this stage index (a short campaign)')
a = ap.parse_args()
os.makedirs(os.path.join(a.out, 'shots'), exist_ok=True)
harness.OPTIONS.update(SYSTEMS[a.sys])
b = harness.Brawler(rom=a.rom, game=a.game, build=a.build)
core = b.core; S = b.syms; OFF, DEAD = b.states.index('OFF'), b.states.index('DEAD')
core.retro_neoscan_m68k_reg.restype = C.c_uint32
hooks = b.aerr()
if hooks: b.aerr_mode(a.aerr)
else: print('fpga_playthrough: the stock core (BRAWLER_CORE): no odd-access log', flush=True)
aud = [0]
def _batch(d, n): aud[0] = zlib.crc32(C.string_at(d, n * 4), aud[0]); return n
_bcb = harness.BATCH_CB(_batch); core.retro_set_audio_sample_batch(_bcb)
b._want_video = True
_ap = C.POINTER(C.c_uint)()
if hooks: core.retro_neoscan_aerr.restype = C.c_uint
odd_n = lambda: core.retro_neoscan_aerr(C.byref(_ap)) if hooks else 0
first_odd = []
from PIL import Image

gt = S['game_ticks']
ticks = lambda: b.r(gt, 4)
rd = lambda n: b.r(S[n], 1)
log = []; faults = []; shots = []; in_tick = {}; tpokes = []
def shot(tag):
    data, w, h, pitch = b._video
    p = os.path.join(a.out, 'shots', '%06d_%s.png' % (b.frame, tag))
    Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(p); shots.append(p)
def poke(kind):
    tpokes.append((ticks(), kind))
    if kind == 'clear': [b.fset(i, 'state', OFF) for i in range(2, 8)]
    elif kind == 'boss': b.fset(2, 'hp', 0); b.fset(2, 'state', DEAD); b.fset(2, 'state_t', 0)
    elif kind == 'hp': b.fset(0, 'hp', 60)
last_t = [None, 0]; bios_streak = [0]; prev = [None]
def step(p1=''):
    t0 = ticks()
    b.pad = [set(p1), set()]; core.retro_run(); b.frame += 1; b.pad = [set(), set()]   # (not b.run: its hit log reads states from boot garbage)
    t1 = ticks()
    if 0 < t1 - t0 < 8:                                  # (boot: the counter is garbage until crt0 clears it)
        for k in range(t0 + 1, t1 + 1): in_tick[k] = p1
    pc = core.retro_neoscan_m68k_reg(16)
    vid = zlib.crc32(b._video[0]) if b._video else 0
    st = (rd('mode'), rd('phase'), rd('camp'), rd('wave'), rd('attract'))
    n_odd = odd_n()
    if n_odd and not first_odd:
        first_odd.append((b.frame, st, hex(_ap[3]), hex(_ap[0]))); shot('ODD'); faults.append((b.frame, 'first odd-address word access (address error on a 68000)', hex(_ap[3]), hex(_ap[0])))
    log.append([b.frame, t1, *st, vid, aud[0], pc, p1, n_odd]); aud[0] = 0
    if t1 == last_t[0]: last_t[1] += 1
    else: last_t[0] = t1; last_t[1] = 0
    if last_t[1] == 120: faults.append((b.frame, 'ticks stalled 120 frames', hex(pc))); shot('STALL')
    ok = pc < 0x100000 or 0x100000 <= pc < 0x110000 or 0x200000 <= pc < 0x300000 or 0xC00000 <= pc < 0xC20000
    if not ok: faults.append((b.frame, 'PC outside ROM/RAM/BIOS', hex(pc)))
    bios_streak[0] = bios_streak[0] + 1 if pc >= 0xC00000 and b.frame > 600 else 0
    if bios_streak[0] == 300: faults.append((b.frame, 'PC in BIOS 300 frames', hex(pc))); shot('BIOS')
    key = st[:4]
    if key != prev[0]: shot('m%d_p%d_s%d_w%d_a%d' % st); prev[0] = key
    return t1

# --- replay (open loop, by tick) ---
if a.replay:
    base = json.load(open(a.replay)); bin_ = {int(k): v for k, v in base['in_tick'].items()}
    bp = [list(x) for x in base['tick_pokes']]; last = base['log'][-1][1]
    core.retro_reset(); b.frame = 0
    while b.frame < len(base['log']) + 300 and not (b.frame > 1000 and ticks() >= last):   # (boot: the counter is garbage)
        live = b.frame > 400                            # (boot: the counter is garbage, and a poke would hit the BIOS's RAM test)
        while live and bp and bp[0][0] <= ticks(): poke(bp.pop(0)[1])
        step(bin_.get(ticks() + 1, '') if live else '')
else:
    core.retro_reset(); b.frame = 0
    for _ in range(a.attract): step()                       # power on + the attract demo (3 loops at 8100)
    for k in ('', 'o', '', 's', ''):                          # coin, START
        for _ in range(4 if k else 120): step(k)
    def enemies(): return [i for i in range(2, 8) if b.fget(i, 'state') not in (OFF, DEAD)]
    wave_t = 0; boss_t = 0; cur = None; f = 0; done = False; seen_end = False
    for _ in range(a.max):
        m, ph = rd('mode'), rd('phase'); f += 1; keys = ''
        if m == 0 or m == 3: keys = 'a' if f % 20 < 2 else ''
        elif m == 6: keys = 'a' if f % 37 < 2 else ''
        elif m == 5: keys = 'o' if f % 60 < 3 else 's' if 20 <= f % 60 < 23 else ''
        elif m == 4: seen_end = True
        elif m == 2:
            if seen_end: break
            keys = 's' if f % 60 < 3 else ''
        elif m == 1:
            if a.stop_after_stage is not None and rd('camp') > a.stop_after_stage: break
            if b.fget(0, 'hp') < 40: poke('hp')
            id_ = (rd('camp'), rd('wave'), ph)
            if id_ != cur: cur = id_; wave_t = 0
            wave_t += 1
            es = enemies()
            if ph in (3, 4): keys = ''
            elif ph == 1 or not es: keys = 'R'
            else:
                x, z = b.fget(0, 'x'), b.fget(0, 'z')
                e = min(es, key=lambda i: abs(b.fget(i, 'x') - x) + abs(b.fget(i, 'z') - z))
                dx, dz = b.fget(e, 'x') - x, b.fget(e, 'z') - z
                if abs(dz) > 6: keys += 'U' if dz < 0 else 'D'
                if abs(dx) > 60: keys += 'R' if dx > 0 else 'L'
                elif abs(dz) <= 10:
                    c = f % 30
                    keys = ('L' if dx < 0 else 'R') if c < 2 else 'a' if 4 <= c < 6 or 12 <= c < 14 else 'b' if 20 <= c < 22 else ''
                    if f % 400 < 2: keys = 'c'
                    if 200 <= f % 400 < 202: keys = 'Da'
            if ph == 0 and es and wave_t > 1800 and b.states[b.fget(0, 'state')] in ('IDLE', 'WALK'): poke('clear'); wave_t = 0
            if ph == 2 and wave_t > 3000 and b.states[b.fget(0, 'state')] in ('IDLE', 'WALK') and b.fget(2, 'state') not in (OFF, DEAD) \
                    and b.fget(2, 'hp') > 0 and b.fget(2, 'y') <= 0 and not rd('ko_seq'):
                poke('boss'); wave_t = 2400                     # once, then 600 frames for its KO / the clear
        step(keys)
    for _ in range(300): step()

out = dict(rom=a.rom, sys=a.sys, frames=b.frame, faults=faults, tick_pokes=tpokes, in_tick=in_tick, log=log)
modes = []
for r in log:
    k = tuple(r[2:6])
    if not modes or modes[-1][0] != k: modes.append([k, r[0]])
out['screens'] = modes
if hooks:
    p = C.POINTER(C.c_uint)(); core.retro_neoscan_aerr.restype = C.c_uint; n = core.retro_neoscan_aerr(C.byref(p))
    out['odd_access_count'] = n
    out['odd_access'] = sorted({(p[i*4], p[i*4+1], p[i*4+2], p[i*4+3]) for i in range(min(n, 4096))})
    core.retro_neoscan_pstat.restype = C.POINTER(C.c_uint32)
    pm = core.retro_neoscan_pstat(0); out['p2_max_read'] = {k: hex(pm[k]) for k in range(16) if pm[k]}
    q = C.POINTER(C.c_uint32)(); core.retro_neoscan_bw.restype = C.c_uint32; n = core.retro_neoscan_bw(C.byref(q))
    out['bank_writes'] = [(hex(q[i*3] >> 8), q[i*3] & 0xff, hex(q[i*3+1]), q[i*3+2]) for i in range(n)]
json.dump(out, open(os.path.join(a.out, 'run.json'), 'w'))
print('frames', b.frame, 'faults', faults[:10])
print('screens', [(m, f) for m, f in modes][:400])
for k in ('odd_access_count', 'p2_max_read', 'bank_writes'): print(k, out.get(k))
if out.get('odd_access'): print('odd (addr, write, fc, ppc):', [(hex(x[0]), x[1], x[2], hex(x[3])) for x in out['odd_access'][:40]])
