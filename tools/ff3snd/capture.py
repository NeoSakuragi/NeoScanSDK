#!/usr/bin/env python3
"""Fatal Fury 3 sound ground truth in our emulator: the Geolith core driven from Python (ctypes, as
tools/brawler/harness.py) with a Z80 port tap, logging what tools/kof98snd/ymtap.lua logs in MAME.

    python3 capture.py OUT FRAMES [--send F:CMD,...] [--block F] [--rom PATH] [--wav PATH]
    python3 capture.py --songs DIR [CMD ...]       every music command (or these): DIR/cap_XX.txt, power-on, the
                                                   game's commands blocked from frame BLOCK on, the song sent at SEND,
                                                   length from song_ff3.py (to the loop / end + 15 %)

Lines (the ymtap.lua format): "f <frame>" before the first line of a frame with activity; "a <reg> <val>" /
"b <reg> <val>" = YM2610 port A / B write; "i <status>" = the sound CPU reads YM status port $04, which only the
interrupt handler does ($218A, once per interrupt: bit 0 = timer A, bit 1 = timer B, the sequencer clock);
"c <cmd>" = the Z80 reads a sound command (port $00, in the NMI handler); "c <cmd> blocked" = a command the
game sent after frame BLOCK, replaced by $00 (which the FF3 NMI handler ignores before storing it, $007C);
"s <cmd>" = a SEND command written at the start of that frame.

The core: a build of ~/CLProjects/geolith with the port tap (geo_z80.c geo_z80_port_tap, exported by libretro.c
as retro_neoscan_z80_tap / retro_neoscan_z80_ram / retro_neoscan_sound_cmd), at CORE below; it is not installed
as the RetroArch core."""
import ctypes as C, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'brawler'))
from harness import ENV_CB, VIDEO_CB, SAMPLE_CB, BATCH_CB, POLL_CB, STATE_CB, GameInfo, Variable, OPTIONS, SYSDIR, KEYS

CORE = '/data/tmp/snd98/ff3/geolith_tap.so'
ROM = '/data/roms/fatfury3.neo'
WORK = '/data/tmp/snd98/ff3/save'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)

class Sound:
    """the core with the tap; one per process (libretro cores are global)"""
    def __init__(self, rom=ROM, core=CORE):
        os.makedirs(WORK, exist_ok=True)
        self.frame = 0; self.out = None; self.block = None; self.allow = []; self.pad = set()
        self.wav = None
        self._opt = {k.encode(): C.c_char_p(v.encode()) for k, v in OPTIONS.items()}
        self._sys = C.c_char_p(SYSDIR.encode()); self._save = C.c_char_p(WORK.encode())
        self.core = c = C.CDLL(core)
        self._video = None; self._want_video = False
        self._cbs = [ENV_CB(self._env), VIDEO_CB(self._vid), SAMPLE_CB(lambda l, r: None),
                     BATCH_CB(self._audio), POLL_CB(lambda: None), STATE_CB(self._input), TAP(self._tap)]
        c.retro_set_environment(self._cbs[0]); c.retro_init()
        c.retro_set_video_refresh(self._cbs[1]); c.retro_set_audio_sample(self._cbs[2])
        c.retro_set_audio_sample_batch(self._cbs[3]); c.retro_set_input_poll(self._cbs[4])
        c.retro_set_input_state(self._cbs[5])
        if not c.retro_load_game(C.byref(GameInfo(rom.encode(), None, 0, None))): raise RuntimeError('load failed: ' + rom)
        c.retro_neoscan_z80_ram.restype = C.POINTER(C.c_uint8 * 0x800)
        self.zram = c.retro_neoscan_z80_ram().contents          # live: Z80 $F800-$FFFF
        c.retro_serialize_size.restype = C.c_size_t
        c.retro_neoscan_z80_tap(self._cbs[6])
        self._a = [0, 0]; self._lastf = -1

    def _env(self, cmd, data):                                   # as harness.Brawler._env
        if cmd in (9, 31):
            C.cast(data, C.POINTER(C.c_char_p))[0] = (self._sys if cmd == 9 else self._save).value; return True
        if cmd == 10: return C.cast(data, C.POINTER(C.c_uint))[0] == 1
        if cmd == 15:
            v = C.cast(data, C.POINTER(Variable))[0]; val = self._opt.get(v.key)
            C.cast(data, C.POINTER(Variable))[0].value = val.value if val else None; return val is not None
        if cmd == 17: C.cast(data, C.POINTER(C.c_bool))[0] = False; return True
        if cmd == 52: C.cast(data, C.POINTER(C.c_uint))[0] = 2; return True
        if cmd == 39: C.cast(data, C.POINTER(C.c_uint))[0] = 0; return True
        return cmd in (11, 37, 55, 67, 68, 69, 0x10000 | 36)
    def _vid(self, data, w, h, pitch):
        if data and self._want_video: self._video = (C.string_at(data, pitch * h), w, h, pitch)
    def screenshot(self, path):
        """the next frame's picture, as PNG (as harness.Brawler.screenshot)"""
        from PIL import Image
        self._want_video = True; self.run(); self._want_video = False
        data, w, h, pitch = self._video
        Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(path)
    def _input(self, port, dev, idx, id):
        return int(dev == 1 and port == 0 and any(KEYS[k] == id for k in self.pad))
    def _audio(self, data, n):
        if self.wav: self.wav.write(C.string_at(data, 4 * n))
        return n

    def _line(self, s):
        if self.out is None: return
        if self._lastf != self.frame: self.out.write(f'f {self.frame}\n'); self._lastf = self.frame
        self.out.write(s)
    def _tap(self, write, port, v):
        p = port & 0xFF
        if write:
            if p == 4: self._a[0] = v
            elif p == 6: self._a[1] = v
            elif p == 5: self._line(f'a {self._a[0]:02X} {v:02X}\n')
            elif p == 7: self._line(f'b {self._a[1]:02X} {v:02X}\n')
            return v
        if p == 4: self._line(f'i {v:02X}\n')
        elif p == 0 and v:
            if self.block is not None and self.frame >= self.block and v not in self.allow:
                self._line(f'c {v:02X} blocked\n'); return 0
            if v in self.allow: self.allow.remove(v)
            self._line(f'c {v:02X}\n')
        return v

    def run(self, n=1, keys=''):
        self.pad = set(keys.replace('-', ''))
        for _ in range(n): self.core.retro_run(); self.frame += 1
        self.pad = set()
    def send(self, cmd):
        """a sound command now, as the 68000's write to REG_SOUND"""
        self.allow.append(cmd); self._line(f's {cmd:02X}\n')
        self.core.retro_neoscan_sound_cmd(cmd)
    def save(self):
        n = self.core.retro_serialize_size(); buf = C.create_string_buffer(n)
        assert self.core.retro_serialize(buf, C.c_size_t(n)); return buf.raw
    def load(self, blob):
        buf = C.create_string_buffer(blob, len(blob)); assert self.core.retro_unserialize(buf, C.c_size_t(len(blob)))
    def z(self, addr): return self.zram[addr - 0xF800]

def capture(out, frames, send=(), block=None, rom=ROM, wav=None):
    """power on, log every frame up to `frames`; send = [(frame, cmd)]; block = frame from which the game's own
    commands are replaced by $00"""
    s = Sound(rom)
    s.out = open(out, 'w'); s.block = block
    if wav: s.wav = open(wav, 'wb')
    todo = sorted(send)
    while s.frame < frames:
        while todo and todo[0][0] <= s.frame: s.send(todo.pop(0)[1])
        s.run()
    s.out.close()
    if s.wav: s.wav.close()
    return s

BLOCK, SEND = 880, 900        # the game sends $07 (unlock) at frame 873 and its first song ($3E) at 896

def frames_for(data, cmd):
    """capture length: song_ff3.py's ticks to the loop point or the end (a chained song: its intro + the next song)"""
    from song_ff3 import Song, tick_hz
    s = Song(data, cmd).run(ticks=30000)
    if s.queued:
        intro = s.queued[0][0]; nxt = s.queued[0][2]
        return frames_for(data, nxt) + int(intro / tick_hz(Song(data, cmd).tempo) * 59.19) + 60
    n = s.tick if not s.running else max((v[0] + v[1] for v in s.loop_at.values()), default=s.tick)
    s2 = Song(data, cmd).run(ticks=n)
    return int(s2.irq / (54.3 + tick_hz(s2.tempo)) * 59.19 * 1.15) + 120

def capture_songs(out_dir, cmds=None):
    import subprocess
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    m1 = open(os.path.join(os.path.dirname(WORK), 'ff3_m1.bin'), 'rb').read()
    os.makedirs(out_dir, exist_ok=True)
    for cmd in cmds or [c for c in range(0x20, 0x60) if m1[0x7D8E + c] == 2]:
        n = SEND + frames_for(m1, cmd)
        subprocess.run([sys.executable, __file__, os.path.join(out_dir, f'cap_{cmd:02X}.txt'), str(n), '--block', str(BLOCK),
                        '--send', f'{SEND}:{cmd:02X}'], check=True)
        print(f'${cmd:02X}: {n} frames', flush=True)

if __name__ == '__main__':
    a = sys.argv
    if a[1] == '--songs': capture_songs(a[2], [int(x, 16) for x in a[3:]]); sys.exit()
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    send = [(int(f), int(c, 16)) for f, c in (x.split(':') for x in opt('--send').split(','))] if opt('--send') else []
    capture(a[1], int(a[2]), send, int(opt('--block')) if opt('--block') else None, opt('--rom') or ROM, opt('--wav'))
