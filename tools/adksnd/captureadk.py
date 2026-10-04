#!/usr/bin/env python3
"""ADK sound driver ground truth in our emulator (Ninja Master's): makoto3's capture core (the Geolith core with a Z80
port tap, driven from Python), the same line format (tools/makoto3/capture.py: "f", "a", "b", "i", "c", "s").

    python3 captureadk.py [--game ninjamas] OUT FRAMES [--send F:CMD,...] [--block F]
    python3 captureadk.py [--game ninjamas] --songs DIR [CMD ...]
                     every music command (or these): DIR/cap_XX.txt, power-on, the game's commands blocked from frame
                     BLOCK on, then $FC (next command from the music table) at SEND, the command one frame later; length from
                     songadk.py (to the loop point or the end + 15 %)

A music command is a byte of the second command table, which the driver uses for the one command after $FC, or for
every command from $FD to $FE ($0B6D-$0B79, $0475): the game sends "FC D0" for its title music (measured)."""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'makoto3'))
from gamesadk import GAMES, m1_path, music_cmds

GAME = 'ninjamas'

def capture(out, frames, send=(), block=None):
    import capture as mk                                     # makoto3's tap core
    g = GAMES[GAME]
    s = mk.Sound(g['rom'], work=g['dir'] + '/save')
    s.out = open(out, 'w'); s.block = block
    todo = sorted(send)
    while s.frame < frames:
        while todo and todo[0][0] <= s.frame: s.send(todo.pop(0)[1])
        s.run()
    s.out.close()

def frames_for(data, cmd):
    """capture length: songadk.py's ticks to the last channel's loop point (or the end), timer A from the song's
    tempo, + 15 %"""
    from songadk import Song
    s = Song(data, cmd).run(30000)
    n = s.tick if not s.running() else max((v[0] + v[1] for v in s.loop_at.values()), default=3000)
    s2 = Song(data, cmd).run(n)
    sec = 0; t, v = 0, 0x2DF                                 # ticks x 2 timer-A periods, the timer as 'T' sets it
    marks = s2.timer + [(n, None)]
    for tt, vv in marks:
        sec += (tt - t) * 2 * 18e-6 * (1024 - v); t = tt
        if vv is not None: v = vv
    return int(sec * 59.19 * 1.15) + 120

def capture_songs(out_dir, cmds=None):
    g = GAMES[GAME]
    m1 = open(m1_path(GAME), 'rb').read()
    os.makedirs(out_dir, exist_ok=True)
    for cmd in cmds or [c for c, _, _ in music_cmds(m1)]:
        n = g['send'] + 1 + frames_for(m1, cmd)
        subprocess.run([sys.executable, __file__, '--game', GAME, os.path.join(out_dir, f'cap_{cmd:02X}.txt'), str(n),
                        '--block', str(g['block']), '--send', f'{g["send"]}:FC,{g["send"] + 1}:{cmd:02X}'], check=True)
        print(f'${cmd:02X}: {n} frames', flush=True)

if __name__ == '__main__':
    a = sys.argv
    if a[1] == '--game': GAME = a[2]; a = a[:1] + a[3:]
    if a[1] == '--songs': capture_songs(a[2], [int(x, 16) for x in a[3:]]); sys.exit()
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    send = [(int(f), int(c, 16)) for f, c in (x.split(':') for x in opt('--send').split(','))] if opt('--send') else []
    capture(a[1], int(a[2]), send, int(opt('--block')) if opt('--block') else None)
