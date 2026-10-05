#!/usr/bin/env python3
"""World Heroes Perfect captures in our emulator (emu/neogeo_sdl --capture) from the 'vs' state (Hanzou P1 vs Fuuma P2,
/data/neogeo_dict/whp/cap/vs.state): per frame the display objects $100000-$1007FF ($80 bytes each; P1 = $100000,
P2 = $100100, $100 apart) and their animation records $106000-$1067FF (object + $6000, fields at +$C0-$FF), and the
camera x ($108232, px [meas]): object x are screen-relative (the game shifts every object when the camera scrolls), so a
world x = object x / 128 + camera.

    rows = run(seq1, seq2='', extra={}, pokes=None, vram=False) -> [{'obj': bytes $800, 'anim': bytes $800, 'vram': path}]"""
import os, subprocess, glob, shutil, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/whp.neo'
VS = '/data/neogeo_dict/whp/cap/vs.state'

def nframes(seq): return sum(int(x.split(':')[0]) for x in seq.split(',') if x)

def parse(txt):
    out = []
    for w in txt.split():
        if ':' in w: continue
        try: out.append(bytes.fromhex(w))
        except ValueError: pass
    return b''.join(out)

def run(seq1, seq2='', extra=None, load=VS, pokes=None, keep=None, vram=False, n=None, span=0x800):
    n = n or max(nframes(seq1), nframes(seq2) if seq2 else 0)
    d = keep or tempfile.mkdtemp(dir='/data/tmp')
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(f'{d}/cap.txt*') + glob.glob(f'{d}/vram*.bin') + glob.glob(f'{d}/pal*.bin'): os.remove(f)
    rd = ';'.join(f'{f}:100000:{span:X};{f}:106000:{span:X};{f}:108200:40' for f in range(1, n))
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2, OUT=f'{d}/cap.txt', LOAD=load, RAMDUMP=rd, **(extra or {}))
    if vram:
        env['VRAMDUMP'] = ';'.join(f'{f}:{d}/vram{f}.bin' for f in range(1, n))
        env['PALDUMP'] = ';'.join(f'{f}:{d}/pal{f}.bin' for f in range(1, n))
    if pokes: env['POKE'] = pokes
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
    rows = []
    for f in range(1, n):
        a = glob.glob(f'{d}/cap.txt.ram{f}_100000'); b = glob.glob(f'{d}/cap.txt.ram{f}_106000')
        g = glob.glob(f'{d}/cap.txt.ram{f}_108200')
        if not a or not b: continue
        glb = parse(open(g[0]).read()) if g else bytes(0x40)
        rows.append({'f': f, 'obj': parse(open(a[0]).read()), 'anim': parse(open(b[0]).read()), 'cam': s16(glb, 0x32),
                     'vram': f'{d}/vram{f}.bin' if vram else None, 'pal': f'{d}/pal{f}.bin' if vram else None})
    if not keep: shutil.rmtree(d)
    return rows

def u16(b, o): return b[o] << 8 | b[o + 1]
def s16(b, o): v = u16(b, o); return v - 65536 if v & 0x8000 else v
def u32(b, o): return u16(b, o) << 16 | u16(b, o + 2)
def objects(row):
    """live display objects in the dump: k -> obj(row, k) for those with a def and an animation pointer"""
    out = {}
    for k in range(len(row['obj']) // 0x100):
        o = obj(row, k)
        if o['ptr'] and o['defw']: out[k] = o
    return out

def obj(row, k):
    """display object k ($100000 + k * $100) and its animation record ($1060C0 + k * $100): position, def, flip, animation, step"""
    o = row['obj'][k * 0x100:(k + 1) * 0x100]; a = row['anim'][k * 0x100:(k + 1) * 0x100]
    return dict(y=u16(o, 0), x=u16(o, 2), defw=u16(o, 8), flags=o[0x21], pal=o[0x20], add=u16(o, 0x2C), base=u16(o, 0x64),
                offs=(s16(o, 0x14), s16(o, 0x16)),
                anim=u16(a, 0xDA), step=a[0xDC], ptr=u32(a, 0xD0), tick=u16(a, 0xE0))
