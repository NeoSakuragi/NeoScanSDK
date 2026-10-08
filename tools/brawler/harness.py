#!/usr/bin/env python3
"""Brawler test harness: the Geolith libretro core driven frame by frame from Python (ctypes), so a test can read and
write the 68000 work RAM between frames, place fighters, force states, press buttons and log every hit.

    from harness import Brawler
    b = Brawler()                     # examples/brawler/brawler.neo (make AI_OFF=1 for enemies that stand still)
    b.to_fight()                      # coin, start, Terry, cached as a save state after the first run
    b.place(2, x=230, z=6)            # fighter 2 (first enemy) on P1's depth line
    b.run(10, p1='a')                 # frames with P1 holding A (keys U D L R a b c d s o)
    for f in b.fighters(): print(f)   # every field of fighter_t, decoded
    print(b.hits)                     # (frame, victim, hp lost, victim state) for every hit so far

Fighter fields and their offsets come from the compiler (offsetof on fighter.h, emitted into assembly), symbol
addresses from build/rom.elf, so the harness follows the struct when it changes. The core is the repo's Geolith build
(geolith/libretro/geolith_libretro.so, the one the feedback replays use; BRAWLER_CORE overrides): its save states (v3,
geolith fa094e0) carry the 68000's pending cycles and the YM2610 pacing. The installed retroarch core predates that:
a state loaded right after power-on and the same state loaded after any frame played differently (TODO #165). Saves go to a fresh scratch dir per instance
(WORK/save_*, removed at exit), never the user's.

Tick sync (Brawler(tick_sync=True), TODO #178): a video frame ends at a fixed cycle of the frame, which falls inside the
game's tick, so a RAM read between frames sees some fighters before and some after this tick's update, and a RAM write
lands in the middle of a tick (the rest of the tick sees it, the part before does not). Where in the tick the frame
ends moves with the tick's cycle count, i.e. with any code / data change: a build with 3000 idle cycles before each tick
(no logic change) moved 31 of 286 regress facing traces. With tick_sync the harness sees the game only at tick
boundaries: a write tap on crt0's `game_ticks` (written just before game_tick runs: the previous tick is complete)
copies work RAM there, and r() / fget() read that copy (the state after the last whole tick); w() / fset() / place()
queue their bytes and the tap writes them at that same boundary (reads see the queued bytes at once). Save states
carry the copy and the queue. Off by default: the existing proofs keep their frame-end semantics."""
import ctypes as C, os, re, struct, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
CORE = os.environ.get('BRAWLER_CORE') or os.path.normpath(os.path.join(HERE, '..', '..', 'geolith', 'libretro', 'geolith_libretro.so'))
SYSDIR = os.path.expanduser('~/.config/retroarch/system')
WORK = '/data/tmp/harness'                      # save dir (NVRAM, memory card) and the cached fight-start state
RAM_BASE = 0x100000

# libretro ---------------------------------------------------------------------------------------------------
ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
SAMPLE_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
class GameInfo(C.Structure): _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]
class Variable(C.Structure): _fields_ = [('key', C.c_char_p), ('value', C.c_char_p)]
OPTIONS = {'geolith_system_type': 'uni', 'geolith_unibios_hw': 'mvs', 'geolith_region': 'jp', 'geolith_memcard': 'on',
           'geolith_memcard_wp': 'off', 'geolith_freeplay': 'off', 'geolith_settingmode': 'off', 'geolith_4player': 'off',
           'geolith_overscan_t': '8', 'geolith_overscan_b': '8', 'geolith_overscan_l': '8', 'geolith_overscan_r': '8',
           'geolith_palette': 'resnet', 'geolith_aspect': '1:1', 'geolith_sprlimit': '96', 'geolith_oc': 'off',
           'geolith_disable_adpcm_wrap': 'off'}             # = emu/neogeo_sdl.c environ_cb
# Neo Geo A..D = retro B A Y X; s = START, o = coin (SELECT); same letters as neogeo_sdl's capture SEQ
KEYS = {'U': 4, 'D': 5, 'L': 6, 'R': 7, 'a': 0, 'b': 8, 'c': 1, 'd': 9, 's': 3, 'o': 2}

def _layout(game):
    """fighter_t offsets/sizes, the state names and symbol addresses, from the game's own sources and ELF"""
    fields = ['ch', 'set', 'palbase', 'spr', 'x', 'z', 'y', 'vx', 'vz', 'vy', 'facing', 'team', 'state', 'state_t', 'anim',
              'step', 'tick', 'anim_done', 'node', 'buffered', 'hit_mask', 'freeze', 'inv', 'hp', 'idx', 'held',
              'shown_frame', 'frame_ovr', 'zfront', 'pushing', 'throw_id', 'grab_hits', 'target', 'spec_id', 'owner',
              'ncols', 'landed', 'chain_node', 'chain_t', 'spec_fx', 'burn', 'jump_kind', 'jump_dir',
              'pdef', 'prow', 'pend', 'shot', 'power', 'tint', 'hp_max', 'acc', 'speed', 'srow', 'spec_atk', 'kmode', 'kdelay', 'spec_ix',
              'air_node', 'flash', 'meter', 'meter_t', 'spart', 'sarm', 'shrow', 'spend', 'plink', 'throw_x0', 'var', 'form_from', 'pstep',
              'pflags', 'pcatch', 'scancel', 'fury_buf', 'spec_buf', 'impact', 'drop', 'wall_by', 'vlist', 'vent', 'pheld', 'pcnt', 'zfront', 'fpose', 'pres', 'vph', 'ksr', 'ksn', 'pbd', 'dizzy', 'dtgt', 'dpin',
              'buf_age', 'jug_n', 'kfloor', 'kslam', 'guard', 'cthrow', 'guard_by',
              'pan', 'rt_p', 'rt_n', 'rt_flags', 'rt_debt', 'rt_hold', 'rt_nseg',
              'dsc', 'dacc', 'brk', 'ovl', 'fmax']
    hdr = open(os.path.join(game, 'fighter.h')).read()
    fields = [f for f in fields if re.search(r'\b%s\b' % f, hdr)]   # an older build may lack the newer fields
    src = '#include <stddef.h>\n#include "fighter.h"\nvoid offs(void) {\n' + ''.join(
        f'asm volatile(".equ OFF_{f}, %c0\\n.equ SZ_{f}, %c1" :: "i"(offsetof(fighter_t, {f})), "i"(sizeof(((fighter_t *)0)->{f})));\n'
        for f in fields) + 'asm volatile(".equ SIZEOF, %c0" :: "i"(sizeof(fighter_t)));\n' + \
        'asm volatile(".equ INTENT, %c0" :: "i"(sizeof(intent_t)));\n' + \
        'asm volatile(".equ CHSIZE, %c0" :: "i"(sizeof(bchar_t)));\n}\n'
    with tempfile.NamedTemporaryFile('w', suffix='.c', delete=False) as t: t.write(src)
    asm = subprocess.run(['m68k-linux-gnu-gcc', '-m68000', '-O2', '-ffreestanding', '-nostdlib', '-I' + game,
                          '-I' + os.path.join(game, '..', '..', 'sdk', 'include'), '-I' + os.path.join(game, '..', '..', 'sdk', 'src'),
                          '-I' + os.path.join(game, 'build'), '-S', '-o', '-', t.name], capture_output=True, text=True, check=True).stdout
    os.unlink(t.name)
    eq = {k: int(v) for k, v in re.findall(r'\.equ (\w+), (-?\d+)', asm)}
    layout = {f: (eq['OFF_' + f], eq['SZ_' + f]) for f in fields}
    body = open(os.path.join(game, 'fighter.h')).read()
    states = re.findall(r'\b(S_[A-Z_]+)\b', body[body.index('S_IDLE'):body.index('S_IDLE') + 600])
    states = [s[2:] for s in dict.fromkeys(states)]
    syms = {}
    for l in subprocess.run(['m68k-linux-gnu-nm', os.path.join(game, 'build', 'rom.elf')], capture_output=True, text=True).stdout.split('\n'):
        p = l.split()
        if len(p) == 3: syms[p[2]] = int(p[0], 16)
    syms['sizeof_intent'] = eq['INTENT']; syms['sizeof_bchar'] = eq['CHSIZE']
    return layout, eq['SIZEOF'], states, syms

TAP_CB = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_int)
SYNC_MAGIC = b'TICKSYNC'

class _Core:
    """the core's functions, with retro_reset / unserialize telling the harness (tick sync: the tick-boundary copy is
    stale until the next tick starts)"""
    def __init__(self, dll, on_reset): self.__dict__['_dll'] = dll; self.__dict__['_on_reset'] = on_reset
    def __getattr__(self, n): return getattr(self._dll, n)
    def __setattr__(self, n, v): setattr(self._dll, n, v)
    def retro_reset(self): self._on_reset(); return self._dll.retro_reset()

class Brawler:
    _core = None                                     # one core per process (libretro cores are global)

    def __init__(self, rom=None, game=GAME, tick_sync=False):
        self.rom = rom or os.path.join(game, 'brawler.neo')
        self.layout, self.fsize, self.states, self.syms = _layout(game)
        m = re.search(r'#define SEL_NSLOT (\d+)', open(os.path.join(game, 'build', 'game_tables.h')).read())
        self.nslot = int(m.group(1)) if m else 16              # select slots (game.json select.slots)
        os.makedirs(WORK, exist_ok=True)
        self.pad = [set(), set()]; self.frame = 0; self.hits = []; self._video = None
        self._opt = {k.encode(): C.c_char_p(v.encode()) for k, v in OPTIONS.items()}
        # a fresh save dir per instance (NVRAM = BIOS settings, credits, the game's backup block; memory card): runs
        # don't inherit each other's credits or saves; a test powers off / on inside it (save_dir, power_cycle)
        import tempfile, atexit, shutil
        self.save_dir = tempfile.mkdtemp(prefix='save_', dir=WORK); atexit.register(shutil.rmtree, self.save_dir, True)
        self._sys = C.c_char_p(SYSDIR.encode()); self._save = C.c_char_p(self.save_dir.encode())
        if Brawler._core is not None: raise RuntimeError('one Brawler per process (the core is a global)')
        core = Brawler._core = C.CDLL(CORE)
        self._cbs = [ENV_CB(self._env), VIDEO_CB(self._vid), SAMPLE_CB(lambda l, r: None), BATCH_CB(lambda d, n: n),
                     POLL_CB(lambda: None), STATE_CB(self._input)]
        core.retro_set_environment(self._cbs[0]); core.retro_init()
        core.retro_set_video_refresh(self._cbs[1]); core.retro_set_audio_sample(self._cbs[2])
        core.retro_set_audio_sample_batch(self._cbs[3]); core.retro_set_input_poll(self._cbs[4])
        core.retro_set_input_state(self._cbs[5])
        if not core.retro_load_game(C.byref(GameInfo(self.rom.encode(), None, 0, None))): raise RuntimeError('load failed: ' + self.rom)
        core.retro_get_memory_data.restype = C.c_void_p; core.retro_get_memory_size.restype = C.c_size_t
        core.retro_serialize_size.restype = C.c_size_t
        n = core.retro_get_memory_size(2)
        self.ram = (C.c_uint8 * n).from_address(core.retro_get_memory_data(2))   # live: writes land in the 68000's RAM
        self.core = core
        self.base = self.syms['fighters']
        self.tick_sync = tick_sync
        if tick_sync: self._sync_init()
        self._pin_clock()

    # tick sync (module docstring)
    def _sync_init(self):
        self._gt = self.syms['game_ticks']; n = len(self.ram)
        self._snap = (C.c_uint8 * n)(); self._snap_ok = False; self._queue = []
        self.core = _Core(self.core, self._sync_stale)
        def tap(addr, val, size):
            if addr != self._gt + 2: return                    # addql #1, game_ticks: high word, then this one
            try:
                for o, data in self._queue: self.ram[o:o + len(data)] = list(data)
                self._queue = []
                C.memmove(self._snap, self.ram, n)
                o = self._gt + 2 - RAM_BASE; self._snap[o] = (val >> 8) & 0xFF; self._snap[o + 1] = val & 0xFF
                self._snap_ok = True
            except Exception as e: print('harness tick tap:', e, flush=True)
        self._tap = TAP_CB(tap)
        self.core.retro_neoscan_m68k_write_tap(self._tap)
    def _sync_stale(self): self._snap_ok = False; self._queue = []

    # libretro callbacks
    def _env(self, cmd, data):
        if cmd in (9, 31):                                           # system / save directory
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(self._sys if cmd == 9 else self._save, C.c_void_p)   # our
            return True                                              # buffers (the core keeps the save dir until unload)
        if cmd == 10: return C.cast(data, C.POINTER(C.c_uint))[0] == 1   # XRGB8888
        if cmd == 15:
            v = C.cast(data, C.POINTER(Variable))[0]; val = self._opt.get(v.key)
            C.cast(data, C.POINTER(Variable))[0].value = val.value if val else None; return val is not None
        if cmd == 17: C.cast(data, C.POINTER(C.c_bool))[0] = False; return True
        if cmd == 52: C.cast(data, C.POINTER(C.c_uint))[0] = 2; return True
        if cmd == 39: C.cast(data, C.POINTER(C.c_uint))[0] = 0; return True
        return cmd in (11, 37, 55, 67, 68, 69, 0x10000 | 36)
    def _vid(self, data, w, h, pitch):
        if data and self._want_video: self._video = (C.string_at(data, pitch * h), w, h, pitch)
    def _input(self, port, dev, idx, id):
        if dev != 1 or port > 1: return 0
        return int(any(KEYS[k] == id for k in self.pad[port]))

    def power_cycle(self):
        """power off (the core writes NVRAM / memory card to save_dir) and on again (it loads them)"""
        if self.tick_sync: self._sync_stale()
        self.core.retro_unload_game()
        if not self.core.retro_load_game(C.byref(GameInfo(self.rom.encode(), None, 0, None))): raise RuntimeError('reload failed')
        self.ram = (C.c_uint8 * self.core.retro_get_memory_size(2)).from_address(self.core.retro_get_memory_data(2))
        self._pin_clock()

    CLOCK = (26, 1, 4, 1, 0, 0, 0)                    # 2026-01-01 (a Thursday) 00:00:00: year % 100, month, weekday, day, h, m, s
    def _pin_clock(self):
        """the MVS calendar chip (uPD4990) starts at the host's wall clock when the core loads the game (geo_rtc_init);
        the BIOS reads it every frame (SYSTEM_IO) and leaves it on the stack, where the game's code reads it back (a
        fight state made at another minute played differently: TODO #165). Pinned to CLOCK at every power-on, through
        the save state (geo_rtc_state_save: 7 big-endian words year, month, weekday, day, hour, minute, second)"""
        import time
        blob = bytearray(self._save_core())
        for dt in (0, -1, -2):                      # the core read the clock a moment ago (a second / minute may have turned)
            t = time.localtime(time.time() + dt)
            key = struct.pack('>4I', t.tm_year % 100, t.tm_mon, (t.tm_wday + 1) % 7, t.tm_mday)   # C: Sunday = 0
            at = [m.start() for m in re.finditer(re.escape(key), bytes(blob))]
            if len(at) == 1: break
        else: raise RuntimeError('calendar not found in the save state (geo_rtc_state_save layout changed?)')
        blob[at[0]:at[0] + 28] = struct.pack('>7I', *self.CLOCK)
        self._load_core(bytes(blob))

    # frames
    _want_video = False
    def run(self, n=1, p1='', p2='', each=None):
        """n frames with these keys held; each(self) after every frame"""
        self.pad = [set(p1.replace('-', '')), set(p2.replace('-', ''))]
        for _ in range(n):
            before = [(self.fget(i, 'hp'), self.fget(i, 'freeze')) for i in range(8)]
            self.core.retro_run(); self.frame += 1
            for i in range(8):
                hp, fz = self.fget(i, 'hp'), self.fget(i, 'freeze')
                if hp < before[i][0] or (fz > before[i][1] and fz >= 8):   # a hit: life lost or a fresh hit-stop
                    self.hits.append((self.frame, i, before[i][0] - hp, self.states[self.fget(i, 'state')]))
            if each: each(self)
        self.pad = [set(), set()]
    def seq(self, s, p=0):
        """'frames:keys,...' as neogeo_sdl's SEQ, for one player"""
        for part in s.split(','):
            n, k = part.split(':'); self.run(int(n), *(['', k] if p else [k]))

    # save states
    def _save_core(self):
        n = self.core.retro_serialize_size(); buf = C.create_string_buffer(n)
        assert self.core.retro_serialize(buf, C.c_size_t(n)); return buf.raw
    def _load_core(self, blob):
        buf = C.create_string_buffer(blob, len(blob)); assert self.core.retro_unserialize(buf, C.c_size_t(len(blob)))
    def save(self):
        blob = self._save_core()
        if not self.tick_sync: return blob
        q = b''.join(struct.pack('>IH', o, len(d)) + bytes(d) for o, d in self._queue)
        extra = bytes([self._snap_ok]) + bytes(self._snap) + struct.pack('>I', len(self._queue)) + q
        return blob + extra + SYNC_MAGIC + struct.pack('>I', len(extra))
    def load(self, blob):
        extra = None
        if blob[-12:-4] == SYNC_MAGIC:
            k = struct.unpack('>I', blob[-4:])[0]; extra = blob[-12 - k:-12]; blob = blob[:-12 - k]
        self._load_core(blob)
        if not self.tick_sync: return
        self._sync_stale()
        if extra:
            n = len(self.ram); self._snap_ok = bool(extra[0]); C.memmove(self._snap, extra[1:1 + n], n)
            p = 1 + n; cnt = struct.unpack('>I', extra[p:p + 4])[0]; p += 4
            for _ in range(cnt):
                o, ln = struct.unpack('>IH', extra[p:p + 6]); p += 6; self._queue.append((o, extra[p:p + ln])); p += ln
    def to_fight(self, cache=True):
        """power on -> coin -> START -> pick the cursor's fighter (Terry) -> the fight, 20 frames in"""
        path = os.path.join(WORK, 'fight_%08x%s.state' % (self._rom_id(), 't' if self.tick_sync else ''))
        if cache and os.path.exists(path): self.load(open(path, 'rb').read()); return
        self.core.retro_reset()
        self.seq('600:-,4:o,100:-,4:s,100:-,4:a,270:-')
        open(path, 'wb').write(self.save())

    # RAM
    def r(self, addr, size):
        o = addr - RAM_BASE
        if self.tick_sync and self._snap_ok:                  # the last tick boundary + the writes queued since
            v = bytearray(self._snap[o:o + size])
            for qo, d in self._queue:
                for i in range(len(d)):
                    if o <= qo + i < o + size: v[qo + i - o] = d[i]
            v = bytes(v)
        else: v = bytes(self.ram[o:o + size])
        return {1: lambda: v[0], 2: lambda: struct.unpack('>H', v)[0], 4: lambda: struct.unpack('>I', v)[0]}[size]()
    def w(self, addr, size, val):
        o = addr - RAM_BASE; data = struct.pack({1: '>B', 2: '>H', 4: '>I'}[size], val & (1 << 8 * size) - 1)
        if self.tick_sync: self._queue.append((o, data)); return     # written at the next tick boundary
        self.ram[o:o + size] = list(data)
    def fget(self, i, field):
        off, sz = self.layout[field]; v = self.r(self.base + i * self.fsize + off, sz)
        if field in ('x', 'z', 'y', 'vx', 'vz', 'vy'): return (v - (1 << 32) if v & 0x80000000 else v) / 65536
        if field in ('facing',) or field == 'hp': return v - (1 << 8 * sz) if v >> (8 * sz - 1) else v
        return v
    def fset(self, i, field, val):
        off, sz = self.layout[field]
        if field in ('x', 'z', 'y', 'vx', 'vz', 'vy'): val = int(round(val * 65536))
        self.w(self.base + i * self.fsize + off, sz, val)
    def place(self, i, x=None, z=None):
        if x is not None: self.fset(i, 'x', x)
        if z is not None: self.fset(i, 'z', z)
    def pget(self, i, field):
        """a field of projectile entity i (fighter.c projectiles[NPJ]: fighter_t too)"""
        off, sz = self.layout[field]; v = self.r(self.syms['projectiles'] + i * self.fsize + off, sz)
        if field in ('x', 'z', 'y', 'vx', 'vz', 'vy'): return (v - (1 << 32) if v & 0x80000000 else v) / 65536
        if field == 'facing': return v - (1 << 8 * sz) if v >> (8 * sz - 1) else v
        return v
    def intent(self, i, press=0, dx=0, dz=0, face=0):
        """the intent of fighter i for the next frame (main.c in[]; in an AI_OFF build nothing else writes the enemies'
        intents: the test drives them): press = IN_* bits (1 A attack, 2 B jump, 4 C special, 8 D fury), dx / dz stick, face = turn this way"""
        a = self.syms['in'] + i * self.syms['sizeof_intent']
        for off, v in ((0, dx), (1, dz), (2, press), (4, face)): self.w(a + off, 1, v)
    def _rom_id(self):
        """a stable id of the ROM build + the core (Python's hash() of bytes changes per process: the cache never hit; a
        state cached by another core build or another pinned clock must not be loaded: #165)"""
        import zlib
        if not hasattr(Brawler, '_core_crc'): Brawler._core_crc = zlib.crc32(open(CORE, 'rb').read() + repr(Brawler.CLOCK).encode())
        return zlib.crc32(open(self.rom, 'rb').read()) ^ Brawler._core_crc
    def unlock_all(self):
        """campaign builds: every boss on the select screen (save.unlocked poked after the title loaded the save; the
        sum is not updated, so it lasts until the next power-on)"""
        if 'save' in self.syms: self.w(self.syms['save'] + 7, 1, 0xFF)
    def sel_slots(self):
        """the select screen's slot table (main.c SEL_SLOT, P ROM, in the layout's slot order): [(x, y, z, face)], read from the
        .neo (P word-swapped)"""
        if not hasattr(self, '_slots'):
            d = open(self.rom, 'rb').read(); a = 0x1000 + self.syms['SEL_SLOT']; out = []
            for i in range(self.nslot):
                w = d[a + 6 * i:a + 6 * i + 6]; w = bytes([w[1], w[0], w[3], w[2], w[5], w[4]])
                out.append(struct.unpack('>hhBb', w))
            self._slots = out
        return self._slots
    def sel_stick(self):
        """the select screen's right / left loop (main.c sel_stick, build_tables.py select_stick: from the places, TODO
        #187), read from the .neo (P word-swapped): [(right, left)] per slot"""
        if not hasattr(self, '_stick'):
            d = open(self.rom, 'rb').read(); a = self.syms['sel_stick']
            b = bytes(d[0x1000 + ((a + i) ^ 1)] for i in range(2 * self.nslot))
            self._stick = [(b[2 * i], b[2 * i + 1]) for i in range(self.nslot)]
        return self._stick
    def sel_goto(self, k, p=0):
        """on the select screen: move player p's cursor to fighter k (bm_chars index) with the stick: right / left walk
        the select screen's loop (main.c sel_move: one loop through everyone, locked ones passed), the shorter way;
        returns the slot"""
        sc = [self.r(self.syms['slot_ch'] + i, 1) for i in range(self.nslot)]
        t = sc.index(k); st = self.sel_stick()
        def dist(c, d):
            n = 0
            while c != t and n <= self.nslot: c = st[c][d]; n += 1
            return n
        c = self.r(self.syms['cursor'] + p, 1)
        key = 'R' if dist(c, 0) <= dist(c, 1) else 'L'
        for _ in range(2 * self.nslot):
            c = self.r(self.syms['cursor'] + p, 1)
            if c == t: return t
            self.run(4, *([key] if not p else ['', key])); self.run(12)
        raise RuntimeError(f'cursor never reached fighter {k} (slot {t})')
    def pick(self, k, button='a', cache=True, unlock=False):
        """power on -> coin -> START -> the select screen's fighter k (bm_chars index = game.json roster order; the cursor walked
        there with the stick: the real select path) -> the fight, 20 frames in; unlock: every boss selectable"""
        path = os.path.join(WORK, 'fight_%08x_%d%s%s%s.state' % (self._rom_id(), k, button, 'u' if unlock else '',
                                                                  't' if self.tick_sync else ''))
        if cache and os.path.exists(path): self.load(open(path, 'rb').read()); return
        self.core.retro_reset()                       # from power on, whatever ran before in this process
        self.seq('600:-,4:o,100:-')
        if unlock: self.unlock_all()
        self.seq('4:s,100:-')
        self.sel_goto(k)
        self.seq(f'4:{button},270:-')
        open(path, 'wb').write(self.save())
    def char_of(self, i):
        """index in bm_chars (game.json roster order) of fighter i"""
        return (self.fget(i, 'ch') - self.syms['bm_chars']) // self.syms['sizeof_bchar']
    def fighter(self, i):
        d = {f: self.fget(i, f) for f in self.layout}
        d['state'] = self.states[d['state']] if d['state'] < len(self.states) else d['state']
        return d
    def fighters(self): return [self.fighter(i) for i in range(8)]
    def brief(self, ids=range(8)):
        return ' | '.join(f"{i}:{self.states[self.fget(i, 'state')]} x{self.fget(i, 'x'):.0f} z{self.fget(i, 'z'):.0f} hp{self.fget(i, 'hp')}"
                          for i in ids)

    # picture
    def screenshot(self, path):
        """the next frame's picture, as PNG"""
        from PIL import Image
        pad = self.pad                                  # the keys held now stay held for this frame
        self._want_video = True; self.run(1, ''.join(pad[0]), ''.join(pad[1])); self._want_video = False   # a frame like any other (its hits logged)
        data, w, h, pitch = self._video
        Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(path)
