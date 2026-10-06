#!/usr/bin/env python3
"""Samurai Shodown II captures in our emulator (emu/neogeo_sdl --capture): per frame the 64 KB of work RAM (DUMP),
VRAM (VRAMDUMP), palette RAM, screenshots, sound commands (SNDLOG).
    run(outdir, seq1, seq2='', load=VS, vram=True, pal_every=0, snaps=(), pokes=None, frames=None, extra=None)
Frame f's files: outdir/ram{f}.bin, vram{f}.bin. The vblank draw shows the display list of frame f-1 (measured)."""
import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/samsho2.neo'
VS = '/data/neogeo_dict/samsho2/cap/vs.state'
P1, P2 = 0x104F40, 0x105A80          # the "0-PLAYER" / "1-PLAYER" tasks in vs.state (object +$64 table, +$66 animation,
                                     # +$6C step); other states: players(ram) finds them by their task names (+$04)
def players(r):
    """(P1, P2) object addresses: the tasks named '0-PLAYER' / '1-PLAYER' (name at +$04, $120-byte tasks from $102000)"""
    out = [None, None]
    for o in range(0x2000, 0xA000, 0x20):
        if r[o + 6:o + 12] == b'PLAYER' and r[o + 5] == 0x2D and r[o + 4] in b'01': out[r[o + 4] - 0x30] = 0x100000 + o
    return tuple(out)

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
    o = base - 0x100000
    return dict(table=u16(r, o + 0x64), anim=u16(r, o + 0x66), step=u32(r, o + 0x6C), nxt=u32(r, o + 0x70),
                x=s16(r, o + 0x5C), y=s16(r, o + 0x5E), wx=s16(r, o + 0x4E), wy=s16(r, o + 0x50),
                flags=u16(r, o + 0x74), facing=r[o + 0x7F], pals=(r[o + 0x81], r[o + 0x82], r[o + 0x83]), tick=r[o + 0x7D])

def display_list(r):
    """the display entries of a frame: walk the list from $101000 ($32D0): [def, x, y, flip, pal, zoom, prio, flags]"""
    out = []; a = 0x1000; seen = set()
    while True:
        a = u16(r, a + 2)
        if a in seen or not 0x1000 <= a < 0x2000: break
        seen.add(a)
        if u16(r, a + 4) == 0xFFFF: break
        out.append(dict(addr=0x100000 + a, prio=u16(r, a + 4), d=u16(r, a + 0x18), x=s16(r, a + 0x10), y=s16(r, a + 0x12),
                        flip=r[a + 0x1C], pal=r[a + 0x1D], zoom=u16(r, a + 0x1A), flags=r[a + 0x1F]))
    return out
