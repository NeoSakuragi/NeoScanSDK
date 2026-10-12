#!/usr/bin/env python3
"""The Last Blade 2 captures in our emulator (emu/neogeo_sdl --capture, from vs_sdl.state): per frame the work RAM
(DUMP), VRAM (VRAMDUMP), palette RAM (PALDUMP), screenshots, sound commands (SNDLOG).
    run(outdir, seq1, seq2='', load=VS, ...)   frame f's files: outdir/ram{f}.bin, vram{f}.bin, pal{f}.bin
Player tasks ($200 bytes, name 'PLAYER' at +$10): P1 $105E00, P2 $106000 (README "Objects")."""
import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/lastbld2.neo'
VS = '/data/neogeo_dict/lastbld2/cap/vs_sdl.state'
P1, P2 = 0x105E00, 0x106000

def nframes(seq): return sum(int(x.split(':')[0]) for x in seq.split(',') if x)

def run(out, seq1, seq2='', load=VS, vram=True, ram=True, pal_every=0, snaps=(), pokes=None, frames=None, extra=None, sndlog=True):
    os.makedirs(out, exist_ok=True)
    n = nframes(seq1)
    fr = list(frames) if frames is not None else list(range(1, n))
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2 or f'{n}:-', OUT=f'{out}/cap.txt', **(extra or {}))
    if load: env['LOAD'] = load
    if ram: env['DUMP'] = ';'.join(f'{f}:{out}/ram{f}.bin' for f in fr)
    if vram: env['VRAMDUMP'] = ';'.join(f'{f}:{out}/vram{f}.bin' for f in fr)
    if pal_every: env['PALDUMP'] = ';'.join(f'{f}:{out}/pal{f}.bin' for f in fr if f % pal_every == 0)
    if snaps: env.update(SNAPS=','.join(map(str, snaps)), SNAPDIR=out)
    if pokes: env['POKE'] = pokes
    if sndlog: env['SNDLOG'] = f'{out}/snd.txt'
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
    return out

def ram(out, f):
    p = f'{out}/ram{f}.bin'
    return open(p, 'rb').read() if os.path.exists(p) else None

def u16(b, o): return b[o] << 8 | b[o + 1]
def s16(b, o): v = u16(b, o); return v - 65536 if v & 0x8000 else v
def u32(b, o): return u16(b, o) << 16 | u16(b, o + 2)

def obj(r, base):
    """a player / effect task: +$60 character, +$72 animation, +$78 script, +$7C script offset, +$80 x, +$84 z,
    +$88 height, +$B6 / +$B7 tick count / ticks, +$B8 step, +$C6 frame, +$41 facing (1 = left)"""
    o = base - 0x100000
    return dict(char=u16(r, o + 0x60), anim=u16(r, o + 0x72), script=u32(r, o + 0x78), off=u32(r, o + 0x7C),
                x=s16(r, o + 0x80), z=s16(r, o + 0x84), h=s16(r, o + 0x88), tick=r[o + 0xB6], ticks=r[o + 0xB7],
                step=u16(r, o + 0xB8), frame=u16(r, o + 0xC6), facing=r[o + 0x41], pal=r[o + 0x68])
