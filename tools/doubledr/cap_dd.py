#!/usr/bin/env python3
"""Double Dragon (Technos 1995) captures in our emulator (emu/neogeo_sdl --capture) from the 'vs' state
(P1 Billy vs P2 Jimmy, /data/neogeo_dict/doubledr/cap/vs.state, saved by boot.py at frame 1150).

    rows = run(seq1, seq2='', vram=False, wlog=None) -> [{'f', 'ram': 64 KB work RAM after frame f, 'vram', 'pal', 'snd'}]
    wlog = ['10xxxx', ...]: every 68000 write to those words, with its pc (-> rows[0]['wlog'] lines)

Sequence syntax: 'frames:keys,...' with keys U D L R a b c d s o (- = nothing)."""
import os, subprocess, glob, shutil, tempfile
NGSDL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/doubledr.neo'
VS = '/data/neogeo_dict/doubledr/cap/vs.state'

def nframes(seq): return sum(int(x.split(':')[0]) for x in seq.split(',') if x)

def run(seq1, seq2='', load=VS, vram=False, wlog=None, n=None, pokes=None, snaps=None, ram=True):
    n = n or max(nframes(seq1), nframes(seq2) if seq2 else 0)
    os.makedirs('/data/tmp/dd95', exist_ok=True)
    d = tempfile.mkdtemp(dir='/data/tmp/dd95')
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2, OUT=f'{d}/cap.txt', LOAD=load, SNDLOG=f'{d}/snd.txt')
    if ram: env['DUMP'] = ';'.join(f'{f}:{d}/ram{f}.bin' for f in range(1, n))
    if vram:
        env['VRAMDUMP'] = ';'.join(f'{f}:{d}/vram{f}.bin' for f in range(1, n))
        env['PALDUMP'] = ';'.join(f'{f}:{d}/pal{f}.bin' for f in range(1, n))
    if wlog: env['WLOG'] = ','.join(wlog)
    if pokes: env['POKE'] = pokes
    if snaps: env.update(SNAPS=snaps, SNAPDIR=d)
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
    snd = {}
    for l in open(f'{d}/snd.txt') if os.path.exists(f'{d}/snd.txt') else []:
        w = l.split()
        if len(w) >= 2 and w[0].isdigit(): snd.setdefault(int(w[0]) + 1, []).append(int(w[1], 16))
    wl = open(f'{d}/cap.txt.wlog').read().splitlines() if os.path.exists(f'{d}/cap.txt.wlog') else []
    rows = []
    for f in range(1, n):
        r = {'f': f, 'snd': snd.get(f, []), 'wlog': wl if f == 1 else None}
        if ram and os.path.exists(f'{d}/ram{f}.bin'): r['ram'] = open(f'{d}/ram{f}.bin', 'rb').read()
        if vram:
            r['vram'] = open(f'{d}/vram{f}.bin', 'rb').read()
            r['pal'] = open(f'{d}/pal{f}.bin', 'rb').read()
        rows.append(r)
    if snaps:
        for s in snaps.split(','):
            p = f'{d}/snap_{s}.ppm'
            if os.path.exists(p): shutil.copy(p, f'/data/tmp/dd95/snap_{s}.ppm')
    shutil.rmtree(d)
    return rows

def u16(b, a): o = a - 0x100000; return b[o] << 8 | b[o + 1]
def s16(b, a): v = u16(b, a); return v - 65536 if v & 0x8000 else v
def u32(b, a): return u16(b, a) << 16 | u16(b, a + 2)
