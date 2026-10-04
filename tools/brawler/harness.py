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
addresses from build/rom.elf, so the harness follows the struct when it changes. The core is the same .so our
emulator loads (~/.config/retroarch/cores/geolith_libretro.so); saves go to a scratch dir, never the user's."""
import ctypes as C, os, re, struct, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
CORE = os.path.expanduser('~/.config/retroarch/cores/geolith_libretro.so')
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
              'pdef', 'prow', 'pend', 'shot']
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

class Brawler:
    _core = None                                     # one core per process (libretro cores are global)

    def __init__(self, rom=None, game=GAME):
        self.rom = rom or os.path.join(game, 'brawler.neo')
        self.layout, self.fsize, self.states, self.syms = _layout(game)
        os.makedirs(WORK, exist_ok=True)
        self.pad = [set(), set()]; self.frame = 0; self.hits = []; self._video = None
        self._opt = {k.encode(): C.c_char_p(v.encode()) for k, v in OPTIONS.items()}
        self._sys = C.c_char_p(SYSDIR.encode()); self._save = C.c_char_p(WORK.encode())
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

    # libretro callbacks
    def _env(self, cmd, data):
        if cmd in (9, 31):                                           # system / save directory
            C.cast(data, C.POINTER(C.c_char_p))[0] = (self._sys if cmd == 9 else self._save).value; return True
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
    def save(self):
        n = self.core.retro_serialize_size(); buf = C.create_string_buffer(n)
        assert self.core.retro_serialize(buf, C.c_size_t(n)); return buf.raw
    def load(self, blob):
        buf = C.create_string_buffer(blob, len(blob)); assert self.core.retro_unserialize(buf, C.c_size_t(len(blob)))
    def to_fight(self, cache=True):
        """power on -> coin -> START -> pick the cursor's fighter (Terry) -> the fight, 20 frames in"""
        path = os.path.join(WORK, 'fight_%08x.state' % self._rom_id())
        if cache and os.path.exists(path): self.load(open(path, 'rb').read()); return
        self.core.retro_reset()
        self.seq('600:-,4:o,100:-,4:s,100:-,4:a,270:-')
        open(path, 'wb').write(self.save())

    # RAM
    def r(self, addr, size):
        o = addr - RAM_BASE; v = bytes(self.ram[o:o + size])
        return {1: lambda: v[0], 2: lambda: struct.unpack('>H', v)[0], 4: lambda: struct.unpack('>I', v)[0]}[size]()
    def w(self, addr, size, val):
        o = addr - RAM_BASE; self.ram[o:o + size] = list(struct.pack({1: '>B', 2: '>H', 4: '>I'}[size], val & (1 << 8 * size) - 1))
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
        intents: the test drives them): press = IN_* bits (1 A, 2 B, 4 C, 8 D), dx / dz stick, face = turn this way"""
        a = self.syms['in'] + i * self.syms['sizeof_intent']
        for off, v in ((0, dx), (1, dz), (2, press), (4, face)): self.w(a + off, 1, v)
    def _rom_id(self):
        """a stable id of the ROM build (Python's hash() of bytes changes per process: the cache never hit)"""
        import zlib
        return zlib.crc32(open(self.rom, 'rb').read())
    def pick(self, k, button='a', cache=True):
        """power on -> coin -> START -> the select screen's fighter k (stick right k times: the real select path)
        -> the fight, 20 frames in"""
        path = os.path.join(WORK, 'fight_%08x_%d%s.state' % (self._rom_id(), k, button))
        if cache and os.path.exists(path): self.load(open(path, 'rb').read()); return
        self.core.retro_reset()                       # from power on, whatever ran before in this process
        self.seq('600:-,4:o,100:-,4:s,100:-' + ',4:R,16:-' * k + f',4:{button},270:-')
        open(path, 'wb').write(self.save())
    def char_of(self, i):
        """index in bm_chars (the Makefile's CHARS order) of fighter i"""
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
        self._want_video = True; self.core.retro_run(); self.frame += 1; self._want_video = False
        data, w, h, pitch = self._video
        Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(path)
