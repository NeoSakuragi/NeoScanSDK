#!/usr/bin/env python3
"""The Last Blade 2 in our emulator's core (the repo's Geolith build, as tools/brawler/harness.py drives it), frame by
frame from Python: pads, work RAM read / write, save states, and the 68000 write tap with the writing instruction's
address (retro_neoscan_m68k_reg 16), which is how the study names the code that writes a RAM field.

    from core_lb2 import LB2
    g = LB2(); g.load_state(VS)           # /data/neogeo_dict/lastbld2/cap/vs.state (P1 Moriya, P2 Kaede)
    g.watch(0x10E3B8, 2)                  # log (frame, pc, addr, value) of every write to it
    g.run(10, p1='a')                     # keys U D L R a b c d s o (neogeo_sdl's SEQ letters)
"""
import ctypes as C, os, struct, sys, tempfile, atexit, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import harness as H

NEO = '/data/roms/lastbld2.neo'
STA = '/data/neogeo_dict/lastbld2/cap'

class LB2:
    _core = None
    def __init__(self, rom=NEO):
        if LB2._core is not None: raise RuntimeError('one core per process')
        self.rom = rom; self.pad = [set(), set()]; self.frame = 0; self.log = []; self._watch = []; self._pcw = None
        os.makedirs(H.WORK, exist_ok=True)
        self.save_dir = tempfile.mkdtemp(prefix='save_', dir=H.WORK); atexit.register(shutil.rmtree, self.save_dir, True)
        self._opt = {k.encode(): C.c_char_p(v.encode()) for k, v in H.OPTIONS.items()}
        self._sys = C.c_char_p(H.SYSDIR.encode()); self._save = C.c_char_p(self.save_dir.encode())
        core = LB2._core = C.CDLL(H.CORE)
        self._cbs = [H.ENV_CB(self._env), H.VIDEO_CB(self._vid), H.SAMPLE_CB(lambda l, r: None),
                     H.BATCH_CB(lambda d, n: n), H.POLL_CB(lambda: None), H.STATE_CB(self._input)]
        core.retro_set_environment(self._cbs[0]); core.retro_init()
        core.retro_set_video_refresh(self._cbs[1]); core.retro_set_audio_sample(self._cbs[2])
        core.retro_set_audio_sample_batch(self._cbs[3]); core.retro_set_input_poll(self._cbs[4])
        core.retro_set_input_state(self._cbs[5])
        if not core.retro_load_game(C.byref(H.GameInfo(rom.encode(), None, 0, None))): raise RuntimeError('load failed')
        core.retro_get_memory_data.restype = C.c_void_p; core.retro_get_memory_size.restype = C.c_size_t
        core.retro_serialize_size.restype = C.c_size_t
        core.retro_neoscan_m68k_reg.restype = C.c_uint32; core.retro_neoscan_m68k_read.restype = C.c_uint32
        n = core.retro_get_memory_size(2)
        self.ram = (C.c_uint8 * n).from_address(core.retro_get_memory_data(2))
        self.core = core
        self._tap = H.TAP_CB(self._on_write); core.retro_neoscan_m68k_write_tap(self._tap)
        self._video = None

    # libretro callbacks (harness.Brawler's)
    _env = H.Brawler._env
    def _vid(self, data, w, h, pitch):
        if data and self._want_video: self._video = (C.string_at(data, h * pitch), w, h, pitch)
    _want_video = False
    def _input(self, port, dev, idx, id):
        if dev != 1 or port > 1: return 0
        return int(any(H.KEYS.get(k) == id for k in self.pad[port]))

    def _on_write(self, addr, val, size):
        if not self._watch: return
        for lo, hi in self._watch:
            if lo <= addr < hi:
                self.log.append((self.frame, self.core.retro_neoscan_m68k_reg(16), addr, val, size)); return

    def watch(self, addr, n=2): self._watch.append((addr, addr + n))
    def unwatch(self): self._watch = []

    def run(self, n=1, p1='', p2='', each=None):
        self.pad = [set(p1.replace('-', '')), set(p2.replace('-', ''))]
        for _ in range(n):
            self.core.retro_run(); self.frame += 1
            if each: each(self)
        self.pad = [set(), set()]
    def seq(self, s, p2=''):
        for part in s.split(','):
            n, k = part.split(':'); self.run(int(n), k)

    def save(self):
        n = self.core.retro_serialize_size(); buf = C.create_string_buffer(n)
        assert self.core.retro_serialize(buf, C.c_size_t(n)); return buf.raw
    def load(self, blob):
        buf = C.create_string_buffer(blob, len(blob)); assert self.core.retro_unserialize(buf, C.c_size_t(len(blob)))
    def load_state(self, path): self.load(open(path, 'rb').read())

    def r(self, addr, size=2):
        o = addr - H.RAM_BASE
        return int.from_bytes(bytes(self.ram[o:o + size]), 'big')
    def rs(self, addr, size=2):
        v = self.r(addr, size); b = 8 * size
        return v - (1 << b) if v >> (b - 1) else v
    def w(self, addr, size, val):
        o = addr - H.RAM_BASE
        self.ram[o:o + size] = list(int(val).to_bytes(size, 'big'))
    def ramcopy(self): return bytes(self.ram)
    def read(self, addr, size=2): return self.core.retro_neoscan_m68k_read(addr, size)
    def screenshot(self, path):
        self._want_video = True; self.core.retro_run(); self.frame += 1; self._want_video = False
        data, w, h, pitch = self._video
        from PIL import Image
        Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(path)
