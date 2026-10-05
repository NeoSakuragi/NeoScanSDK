#!/usr/bin/env python3
"""One song as a ROM really plays it, in our emulator (the Geolith core with the Z80 port tap, tools/makoto3/capture.py):
power on, the game's own sound commands blocked from the game's 'block' frame, then the unlock $07 and the song's
command; every YM2610 write logged (capture98.py's format) and the audio from the command on saved as a WAV.

    python3 capture_snd.py GAME CMD SECONDS OUT [--rom ROM.neo]
        CMD = a music command, or a prefix pair (1A11 = $1A then $11: KOF98's slot-1 effect $11)
        GAME = a key of tools/makoto3/games.py or tools/kof98snd/games98.py (its ROM, frames, re-entry guard),
               or 'brawler' (examples/brawler/brawler.neo: KOF98's driver, --rom for another build)
        -> OUT.txt (register log), OUT.wav (16-bit stereo, 55,555 Hz: the MVS rate of the core)

    python3 capture_snd.py --check SND_DIR [--rom ROM.neo] [--seconds S] [--wav-dir DIR]
        every song of build_snd.py's output (SND_DIR/snd_report.json) captured in the brawler ROM and compared with
        song98.py's model of SND_DIR/m1.bin, timer interrupt by interrupt (regs98.compare)"""
import json, os, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(TOOLS, 'kof98snd')); sys.path.insert(0, os.path.join(TOOLS, 'makoto3'))
import games98, capture98, games as makoto_games
import capture as mk

BRAWLER = os.path.join(os.path.dirname(TOOLS), 'examples', 'brawler', 'brawler.neo')
RATE = 55555
BRAWLER_G = dict(block=1, send=440)       # every command of the game blocked (its attract demo plays music and
                                          # effects): the driver idles until the capture's own $07 + command

def capture(game, cmd, seconds, out, rom=None):
    if game == 'brawler' or game in games98.GAMES:
        g = dict(games98.GAMES['kof98' if game == 'brawler' else game])
        if game == 'brawler': g.update(BRAWLER_G, rom=rom or BRAWLER, nop=0x60)   # $60: KOF98's harmless filler
        elif rom: g['rom'] = rom
        if game == 'kof98': g.setdefault('nop', 0x60)   # KOF98 replays a stale ring slot on a $00
        capture98.GAME = 'kof98' if game == 'brawler' else game
        s = mk.Sound(rom=g['rom'], work=os.path.dirname(out) + '/save')
        guard = g['guard']; s.nop = g.get('nop', 0)            # the byte a blocked command becomes
        orig = s._tap
        def tap(write, port, v):
            r = orig(write, port, v)
            if not write and port & 0xFF == 4 and v & 1: s._line('q 1\n' if s.z(guard) == 0 else 'q 2\n')
            return r
        s._keep = mk.TAP(tap); s.core.retro_neoscan_z80_tap(s._keep)
    else:
        g = makoto_games.GAMES[game]
        mk.GAME = game
        s = mk.Sound(rom=rom or g['rom'], work=os.path.dirname(out) + '/save')
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    s.block = g['block']
    while s.frame < g['send']: s.run()
    s.out = open(out + '.txt', 'w')                     # the log starts at the unlock: the game's own earlier
    s.send(0x07); s.run()
    if cmd > 0xFF: s.send(cmd >> 8); s.run()            # a prefix pair: $1A + code = a sound effect in slot 1
    s.send(cmd & 0xFF)                                  # commands (the brawler's attract music) stay out of it
    pcm = open(out + '.raw', 'wb'); s.wav = pcm
    s.run(int(seconds * 59.1856) + 1)
    s.out.close(); pcm.close()
    data = open(out + '.raw', 'rb').read(); os.remove(out + '.raw')
    with wave.open(out + '.wav', 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(data)

def check(snd_dir, rom=None, seconds=None, wav_dir=None):
    import subprocess
    rep = json.load(open(f'{snd_dir}/snd_report.json'))
    for s in rep['songs']:
        cmd = int(s['cmd'], 16) if isinstance(s['cmd'], str) else s['cmd']
        if seconds: sec = seconds
        elif 'loops' in s: sec = max(a + 2 * b for a, b in s['loops'].values()) / s['kof98_hz_after_losses'] + 1
        else: sec = 60
        out = f"{wav_dir or snd_dir + '/cap'}/{s['name'].lower()}"
        # one process per song: the libretro core is global to the process
        subprocess.run([sys.executable, __file__, 'brawler', f'{cmd:02X}', str(sec), out] + (['--rom', rom] if rom else []), check=True)
        import regs98
        print(f"{s['name']:14s} ${cmd:02X}", end=' ', flush=True)
        regs98.compare(open(f'{snd_dir}/m1.bin', 'rb').read(), cmd, out + '.txt', 0)

if __name__ == '__main__':
    a = sys.argv
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    if a[1] == '--check': check(a[2], opt('--rom'), float(opt('--seconds')) if opt('--seconds') else None, opt('--wav-dir'))
    else: capture(a[1], int(a[2], 16), float(a[3]), a[4], opt('--rom'))
