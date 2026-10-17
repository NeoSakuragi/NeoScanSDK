#!/usr/bin/env python3
"""Whole-game playthrough of a brawler ROM on our emulator's core (harness.py; never MAME), for "it crashes on an FPGA"
reports (2026-10-16, Ismael's personalized ROM): power on, the attract demo (3 loops), coin, START, the select, every
stage with a simple bot as P1 (walks to the nearest enemy, A A B strings; P1's life kept up; a wave / boss the bot
cannot finish is cleared by the same test pokes as ramtrace.py campaign), the bonus games PLAYED TO A WIN (the pick:
the posts first, AOF2's SUPER DEATH BLOW: walk to each post, A, A, A, its clock kept off its end; then SS2's referee
walks in, and D in his held message = the D quirk: the fury on his body (Kuroko), his HORRIBLE ATMOSPHERE; the Ki
training after stage 3: A at the top grade's power), the ending's screens (A after each), back to the title.

    python3 fpga_playthrough.py --rom R.neo --game GAME_DIR [--build BUILD] --sys mvs-mvs|uni-aes --out DIR
           [--wave-limit 1800] [--boss-limit 3000]   frames before a wave / the boss is cleared by poke (the gate: less)
           [--replay DIR/run.json]       the other run's inputs + pokes by tick (open loop: compare two builds)

Per frame it logs: game ticks, mode / phase / stage / wave, CRC32 of the picture and of the audio, the 68000's PC.
Faults flagged: ticks stalled (hang), game ticks going BACK once the game ran (a reset), PC outside cart ROM / work RAM /
BIOS, a long stay in the BIOS after the game started (BIOS error / exception screen), the attract or the play not
reaching their screens. With the address-error core (aerr_core.sh -> geolith_libretro_aerr.so, taken by default:
BRAWLER_AERR=1; built when missing or older than the tree / the patch) it also checks what a real MVS / AES does and
our stock core does not: every odd-address word / long access (a 68000's ADDRESS ERROR; --aerr 1 (default) logs it
and lets the access go on, --aerr 2 takes the exception as the real CPU: SNK's MVS BIOS then shows garbage, a green
screen and the title = the RESET Ismael saw); every CPU exception taken (bus / address error, illegal instruction,
zero divide, CHK, TRAPV, privilege, line A / F, TRAP: vector + PPC); the WATCHDOG (Geolith emulates it as MAME: no
$300001 kick for 8 frames = a reset): its resets and the longest stretch without a kick after the boot; the STACK's
high-water mark (the RAM between .bss's end and the stack painted while the game runs, the lowest byte the stack
touched read back: headroom left); the highest P ROM byte read through the $200000 window per bank, and every write
into $200000-$2FFFFF (bank register). Screenshots at each screen change: DIR/shots/. DIR/run.json: the log, the
faults, `reached` (what the run went through: posts won, the referee's phases, the D quirk's hit, the Ki game, the
ending, back to the title), the strict stats. The release gate on top of it: hw_strict_proof.py.

Found with it, 2026-10-16: route nodes (rnode_t.speed, a word) read from the byte arrays export_bm.py wrote as
`static const uint8_t <f>_routes[]` (alignment 1: half of them landed on odd addresses; now aligned(2)) = 0.10.152's
crash; rf_draw's `(int16_t)(rf.y >> 8)`, which GCC 15 compiles into a word read at rf.y + 1 = 0.10.153's reset as
the referee walked in after the posts were won (main.c fx8_int; odd_static_lint.py at every link)."""
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
ap.add_argument('--wave-limit', type=int, default=1800, help='frames of a wave before its enemies are cleared by poke')
ap.add_argument('--boss-limit', type=int, default=3000, help='frames of a boss phase before the boss is KO\'d by poke')
a = ap.parse_args()
os.makedirs(os.path.join(a.out, 'shots'), exist_ok=True)
harness.OPTIONS.update(SYSTEMS[a.sys])
b = harness.Brawler(rom=a.rom, game=a.game, build=a.build)
core = b.core; S = b.syms; OFF, DEAD = b.states.index('OFF'), b.states.index('DEAD')
core.retro_neoscan_m68k_reg.restype = C.c_uint32
hooks = b.aerr()
strict = hooks and hasattr(core, 'retro_neoscan_wd')     # (the exception log / watchdog / stack checks: aerr_core.patch)
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
G = json.load(open(os.path.join(a.game, 'game.json')))
GAMES = G.get('bonus', {}).get('games', [])
POSTS = next((i for i, x in enumerate(GAMES) if x['kind'] == 'break'), None)
KI = next((i for i, x in enumerate(GAMES) if x['kind'] == 'gauge'), None)
BN_PICK, BN_PLAY, BN_END = 1, 2, 3                       # main.c bonus_on
BP_STAND = 2                                             # main.c bn_post: the post standing (bonus_proof.BP_STAND)
RF_PH = ['OFF', 'WALK', 'STAND', 'RISE', 'JUMP', 'LAND', 'OPEN', 'TYPE', 'HOLD', 'CLOSE', 'WAIT']   # main.c rf.ph
RF_QUIRK = 11                                            # main.c rf: ph .. w (11 bytes), quirk (RQ_NONE / RUN / FURY / HIT)
EXC = {2: 'bus error', 3: 'address error', 4: 'illegal instruction', 5: 'zero divide', 6: 'CHK', 7: 'TRAPV',
       8: 'privilege violation', 9: 'trace', 10: 'line A', 11: 'line F', 14: 'format error'}
MCYC_FRAME = 405504                                      # Geolith's master cycles a frame (the watchdog counts them)

gt = S['game_ticks']
ticks = lambda: b.r(gt, 4)
rd = lambda n: b.r(S[n], 1)
log = []; faults = []; shots = []; in_tick = {}; tpokes = []
reached = {'posts_won': False, 'referee': [], 'quirk_hit': False, 'ki_played': False, 'bonus_games': [], 'ending': False,
           'title_after_ending': False, 'stages': [], 'maps': [], 'finale': False, 'bonus_offered': []}
def shot(tag):
    data, w, h, pitch = b._video
    p = os.path.join(a.out, 'shots', '%06d_%s.png' % (b.frame, tag))
    Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(p); shots.append(p)
def poke(kind):
    tpokes.append((ticks(), kind))
    if kind == 'clear': [b.fset(i, 'state', OFF) for i in range(2, 8)]
    elif kind == 'boss': b.fset(2, 'hp', 0); b.fset(2, 'state', DEAD); b.fset(2, 'state_t', 0)
    elif kind == 'hp': b.fset(0, 'hp', 60)
    elif kind == 'clock': b.w(S['bn_clock'], 2, 99 * 60)

# --- the strict hardware checks (the aerr core's hooks) ---
_ep = C.POINTER(C.c_uint)(); _wd = (C.c_uint32 * 4)()
if strict: core.retro_neoscan_exc.restype = C.c_uint
exc_seen = [0]; wd_seen = [0]; wd_max = [0]; play_seen = [False]; last_ticks = [0]
STACK_TOP = 0x10F300                                     # crt0's initial SSP (the BIOS's RAM above it)
BSS_END = (S['__bss_end'] + 1) & ~1 if '__bss_end' in S else None
PAINT = 0xA5
stack = {'lowest': None, 'paints': 0}
def stack_paint():
    """the RAM from .bss's end to 1 KB below the stack pointer (free while the game runs) painted PAINT"""
    sp = core.retro_neoscan_m68k_reg(15)
    if BSS_END is None or not (BSS_END < sp <= STACK_TOP): return
    lo, hi = BSS_END - harness.RAM_BASE, sp - 1024 - harness.RAM_BASE
    if hi > lo: C.memset(C.addressof(b.ram) + lo, PAINT, hi - lo); stack['paints'] += 1; stack['hi'] = hi + harness.RAM_BASE
def stack_read():
    """the lowest byte the stack wrote since the last paint (what's below it still PAINT)"""
    if BSS_END is None or 'hi' not in stack: return
    o = BSS_END - harness.RAM_BASE; end = stack['hi'] - harness.RAM_BASE
    raw = bytes(b.ram[o:end]); k = len(raw) - len(raw.lstrip(bytes([PAINT])))
    low = BSS_END + k if k < len(raw) else stack['hi']
    if stack['lowest'] is None or low < stack['lowest']: stack['lowest'] = low
def strict_frame(pc, t1):
    if not strict: return
    n = core.retro_neoscan_exc(C.byref(_ep))
    for i in range(exc_seen[0], min(n, exc_seen[0] + 8)):
        j = i & 255; v = _ep[j * 3]
        faults.append((b.frame, f'CPU exception: vector {v} ({EXC.get(v, "TRAP #%d" % (v - 32) if 32 <= v < 48 else "?")})',
                       hex(_ep[j * 3 + 1]), hex(_ep[j * 3 + 2])))
        if i == exc_seen[0]: shot('EXC')
    exc_seen[0] = n
    core.retro_neoscan_wd(_wd)
    if _wd[2] > wd_seen[0]:
        faults.append((b.frame, f'WATCHDOG reset (no $300001 kick for {_wd[1] / MCYC_FRAME:.1f} frames)', hex(_wd[3]))); shot('WATCHDOG')
        wd_seen[0] = _wd[2]
    if b.frame > 600: wd_max[0] = max(wd_max[0], _wd[0])
last_t = [None, 0]; bios_streak = [0]; prev = [None]
def step(p1=''):
    t0 = ticks()
    if b.frame == 600 and strict:                        # (from here on: the game's own watchdog stretches)
        core.retro_neoscan_wd_clear()
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
    if st[0] == 1 and not st[4]: play_seen[0] = True
    if play_seen[0] and b.frame > 600 and t1 + 2 < last_ticks[0]:   # (crt0's counter only grows: back = a reset)
        faults.append((b.frame, f'game ticks went back {last_ticks[0]} -> {t1}: a RESET', hex(pc))); shot('RESET')
    last_ticks[0] = t1
    strict_frame(pc, t1)
    key = st[:4]
    if key != prev[0]:
        shot('m%d_p%d_s%d_w%d_a%d' % st)
        if strict and key[0] == 1 and (prev[0] is None or prev[0][0] != 1): stack_read(); stack_paint()   # (each fight's start)
        prev[0] = key
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
    def facing_ok(right):
        face = b.fget(0, 'facing'); face = face - 256 if face > 127 else face
        return (face > 0) == right
    wave_t = 0; cur = None; f = 0; seen_end = False; bn_prev = None; ki_pressed = False; d_sent = False
    map_prev = 0
    for _ in range(a.max):
        m, ph = rd('mode'), rd('phase'); f += 1; keys = ''
        mo = rd('map_on') if 'map_on' in S else 0          # (2026-10-17: the map at each stage's start (1) and clear (2))
        if mo and mo != map_prev: reached['maps'].append([rd('camp'), mo])
        map_prev = mo
        if 'fin_st' in S and rd('fin_st') == 2: reached['finale'] = True
        if m == 0 or m == 3: keys = 'a' if f % 20 < 2 else ''
        elif m == 6 or rd('bonus_on'):                   # the bonus screens (mode 6) and games (mode 1, bonus_on)
            bo, cur_g = rd('bonus_on'), rd('bn_cur')
            if bo != bn_prev:
                if bo == BN_PICK and 'bn_slot_game' in S:
                    reached['bonus_offered'].append([GAMES[g]['id'] for g in (b.r(S['bn_slot_game'] + k, 1) for k in range(3)) if g < len(GAMES)])
                if bo == BN_PLAY: reached['bonus_games'].append(GAMES[cur_g]['id'] if cur_g < len(GAMES) else cur_g); ki_pressed = False
                if bo == BN_END and cur_g == POSTS and rd('bn_left') == 0: reached['posts_won'] = True
                bn_prev = bo
            rph = RF_PH[b.r(S['rf'], 1)] if 'rf' in S and b.r(S['rf'], 1) < len(RF_PH) else 'OFF'
            if rph != 'OFF' and (not reached['referee'] or reached['referee'][-1] != rph): reached['referee'].append(rph)
            if 'rf' in S and b.r(S['rf'] + RF_QUIRK, 1) == 3: reached['quirk_hit'] = True
            if bo == BN_PICK:                            # the posts first (while they are offered), else the cursor's game
                slots = [b.r(S['bn_slot_game'] + k, 1) for k in range(3)] if 'bn_slot_game' in S else []
                if POSTS in slots and cur_g != POSTS: keys = 'R' if f % 10 < 2 else ''
                else: keys = 'a' if f % 20 < 2 else ''
            elif bo == BN_PLAY and cur_g == POSTS:       # walk to the post, A, A, A (bonus_proof.play_posts)
                if b.r(S['bn_clock'], 2) < 600: poke('clock')   # (its clock kept off its end: the WIN is the point)
                stn = b.states[b.fget(0, 'state')]
                if rd('bn_post') == BP_STAND and stn in ('IDLE', 'WALK', 'ATTACK'):
                    px = b.r(S['bn_px'], 2); px = px - 65536 if px > 32767 else px; fx = b.fget(0, 'x')
                    right = px + 32 > fx                  # (the front post / trunk: on his right or his left; a pile's
                    gap = px - fx if right else fx - (px + 64)   # bn_px = its floor trunk nearest him, main.c "the pile")
                    if stn != 'ATTACK' and gap > 12: keys = 'R' if right else 'L'
                    elif stn != 'ATTACK' and not facing_ok(right): keys = 'R' if right else 'L'
                    elif f & 7 == 0 and gap <= 12 and facing_ok(right): keys = 'a'
            elif bo == BN_PLAY and cur_g == KI:          # A at the top grade's power: a pass
                reached['ki_played'] = True
                if not ki_pressed and rd('bn_power') >= GAMES[KI]['grades'][-1] + 2: keys = 'a'; ki_pressed = True
            elif bo == BN_END:
                if rph == 'HOLD' and b.r(S['rf'] + RF_QUIRK, 1) == 0 and not d_sent: keys = 'd'; d_sent = True   # the D quirk
                elif rph == 'OFF' and f % 37 < 2: keys = 'a'
            if bo != BN_END: d_sent = False
        elif m == 5: keys = 'o' if f % 60 < 3 else 's' if 20 <= f % 60 < 23 else ''
        elif m == 4:
            seen_end = True; reached['ending'] = True
            keys = 'a' if f % 90 < 2 else ''             # (each screen: A after its min ticks)
        elif m == 7: keys = 'a' if f % 37 < 2 else ''
        elif m == 2:
            if seen_end: reached['title_after_ending'] = True; break
            keys = 's' if f % 60 < 3 else ''
        elif m == 1:
            if a.stop_after_stage is not None and rd('camp') > a.stop_after_stage: break
            if rd('camp') not in reached['stages']: reached['stages'].append(rd('camp'))
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
            if ph == 0 and es and wave_t > a.wave_limit and b.states[b.fget(0, 'state')] in ('IDLE', 'WALK'): poke('clear'); wave_t = 0
            if ph == 2 and wave_t > a.boss_limit and b.states[b.fget(0, 'state')] in ('IDLE', 'WALK') and b.fget(2, 'state') not in (OFF, DEAD) \
                    and b.fget(2, 'hp') > 0 and b.fget(2, 'y') <= 0 and not rd('ko_seq'):
                poke('boss'); wave_t = a.boss_limit - 600       # once, then 600 frames for its KO / the clear
            if ph == 3 and es and wave_t > 600: poke('clear'); wave_t = 0   # (STAGE CLEAR waits for every enemy gone)
        step(keys)
    for _ in range(300): step()
if strict: stack_read()

out = dict(rom=a.rom, sys=a.sys, frames=b.frame, faults=faults, tick_pokes=tpokes, in_tick=in_tick, log=log, reached=reached)
modes = []
for r in log:
    k = tuple(r[2:6])
    if not modes or modes[-1][0] != k: modes.append([k, r[0]])
out['screens'] = modes
if hooks:
    p = C.POINTER(C.c_uint)(); core.retro_neoscan_aerr.restype = C.c_uint; n = core.retro_neoscan_aerr(C.byref(p))
    out["odd_access_count"] = n
    out['odd_access'] = sorted({(p[i*4], p[i*4+1], p[i*4+2], p[i*4+3]) for i in range(min(n, 4096))})
    core.retro_neoscan_pstat.restype = C.POINTER(C.c_uint32)
    pm = core.retro_neoscan_pstat(0); out['p2_max_read'] = {k: hex(pm[k]) for k in range(16) if pm[k]}
    q = C.POINTER(C.c_uint32)(); core.retro_neoscan_bw.restype = C.c_uint32; n = core.retro_neoscan_bw(C.byref(q))
    out['bank_writes'] = [(hex(q[i*3] >> 8), q[i*3] & 0xff, hex(q[i*3+1]), q[i*3+2]) for i in range(n)]
if strict:
    out['exceptions'] = exc_seen[0]; out['watchdog_resets'] = wd_seen[0]
    out['watchdog_worst_frames'] = round(wd_max[0] / MCYC_FRAME, 2); out['watchdog_limit_frames'] = round(_wd[1] / MCYC_FRAME, 2)
    out['stack'] = {'bss_end': hex(BSS_END), 'top': hex(STACK_TOP), 'lowest': hex(stack['lowest']) if stack['lowest'] else None,
                    'headroom': stack['lowest'] - BSS_END if stack['lowest'] else None, 'paints': stack['paints']}
json.dump(out, open(os.path.join(a.out, 'run.json'), 'w'))
print('frames', b.frame, 'faults', faults[:10])
print('screens', [(m, f) for m, f in modes][:400])
for k in ('reached', 'odd_access_count', 'exceptions', 'watchdog_resets', 'watchdog_worst_frames', 'stack', 'p2_max_read', 'bank_writes'): print(k, out.get(k))
if out.get('odd_access'): print('odd (addr, write, fc, ppc):', [(hex(x[0]), x[1], x[2], hex(x[3])) for x in out['odd_access'][:40]])
