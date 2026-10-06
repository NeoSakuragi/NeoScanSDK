#!/usr/bin/env python3
"""Kizuna Encounter captures in our emulator (emu/neogeo_sdl --capture) from the 'vs' state (P1 Kim + Rosa vs P2
Hayate + Eagle, /data/neogeo_dict/kizuna/cap/vs.state): per frame the object pool $100000-$103FFF ($100 bytes each:
tasks with a name at +$10) and the fighters / globals $108000-$1085FF; optional VRAM + palette dumps.

    rows = run(seq1, seq2='', pokes=None, vram=False) -> [{'f', 'pool': bytes $4000, 'glb': bytes $600, 'vram', 'pal'}]

Objects (the same layout for the fighters $108200 / $108400 and the pool's tasks; read in the step loader $139EA and the
renderer $1491A): +$0F flags (bit 1 H flip), +$1E character, +$24 x (px, world), +$28 y (px, down; floor 224 [meas]),
+$30 / +$32 shrink x / y (0-255, $FF full size when the camera is close), +$40 animation id (char << 12 | n),
+$42 step count (animation loops), +$43 step index, +$44 next step pointer, +$48 tick accumulator (high byte = frames),
+$4A ticks of this step, +$4E draw flags of the step, +$5A/+$5E/+$62 parts' sprite data, +$72 the step's trailer word,
+$74 its box list pointer, +$94 this step's pointer."""
import os, subprocess, glob, shutil, tempfile
NGSDL = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'emu', 'neogeo_sdl')
NEO = '/data/roms/kizuna.neo'
VS = '/data/neogeo_dict/kizuna/cap/vs.state'
VS2 = '/data/neogeo_dict/kizuna/cap/vs2.state'                    # P1 Hayate + Rosa, P2 Kim + Eagle

def nframes(seq): return sum(int(x.split(':')[0]) for x in seq.split(',') if x)

def parse(txt):
    out = []
    for w in txt.split():
        if ':' in w: continue
        try: out.append(bytes.fromhex(w))
        except ValueError: pass
    return b''.join(out)

POOL = 0x8000                                                    # the whole task pool $100000-$107FFF (TODO #144: Kim's
                                                                 # Hienzan pillar '503 EFFE' lives at $106300)
def run(seq1, seq2='', extra=None, load=VS, pokes=None, keep=None, vram=False, n=None, pool=POOL):
    n = n or max(nframes(seq1), nframes(seq2) if seq2 else 0)
    os.makedirs('/data/tmp/kizuna', exist_ok=True)
    d = keep or tempfile.mkdtemp(dir='/data/tmp/kizuna')
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(f'{d}/cap.txt*') + glob.glob(f'{d}/vram*.bin') + glob.glob(f'{d}/pal*.bin'): os.remove(f)
    rd = ';'.join(f'{f}:100000:{pool:X};{f}:108000:600;{f}:109640:40' for f in range(1, n))
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2, OUT=f'{d}/cap.txt', LOAD=load, RAMDUMP=rd, **(extra or {}))
    if vram:
        env['VRAMDUMP'] = ';'.join(f'{f}:{d}/vram{f}.bin' for f in range(1, n))
        env['PALDUMP'] = ';'.join(f'{f}:{d}/pal{f}.bin' for f in range(1, n))
    if pokes: env['POKE'] = pokes
    env['SNDLOG'] = f'{d}/snd.txt'
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
    snd = {}                                                 # frame -> [byte written to REG_SOUND] (the log's frame
    for l in open(f'{d}/snd.txt') if os.path.exists(f'{d}/snd.txt') else []:      # n - 1 = during frame n)
        w = l.split()
        if len(w) >= 2 and w[0].isdigit(): snd.setdefault(int(w[0]) + 1, []).append(int(w[1], 16))
    rows = []
    for f in range(1, n):
        a = glob.glob(f'{d}/cap.txt.ram{f}_100000'); b = glob.glob(f'{d}/cap.txt.ram{f}_108000')
        g = glob.glob(f'{d}/cap.txt.ram{f}_109640')
        if not a or not b: continue
        rows.append({'f': f, 'pool': parse(open(a[0]).read()), 'glb': parse(open(b[0]).read()), 'cam': parse(open(g[0]).read()) if g else bytes(64),
                     'vram': f'{d}/vram{f}.bin' if vram else None, 'pal': f'{d}/pal{f}.bin' if vram else None,
                     'snd': snd.get(f, [])})
    if not keep: shutil.rmtree(d)
    return rows

def p1_anims(seq1, seq2='', load=VS, pokes=None):
    """P1's animation id per frame only (the OUT line's P1 object, $108100 + $200: its +$140 = $108240), no RAM dumps:
    the brute force's fast capture"""
    os.makedirs('/data/tmp/kizuna', exist_ok=True)
    d = tempfile.mkdtemp(dir='/data/tmp/kizuna')
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2, OUT=f'{d}/cap.txt', LOAD=load)
    if pokes: env['POKE'] = pokes
    subprocess.run([NGSDL, NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
    out = []
    for l in open(f'{d}/cap.txt'):
        w = l.split()
        if len(w) > 3 and len(w[3]) >= 0x284: out.append(int(w[3][0x280:0x284], 16))
    shutil.rmtree(d)
    return out

def u16(b, o): return b[o] << 8 | b[o + 1]
def s16(b, o): v = u16(b, o); return v - 65536 if v & 0x8000 else v
def u32(b, o): return u16(b, o) << 16 | u16(b, o + 2)

def obj_bytes(row, addr):
    if 0x108000 <= addr < 0x108600: return row['glb'][addr - 0x108000:addr - 0x108000 + 0x200]
    return row['pool'][addr - 0x100000:addr - 0x100000 + 0x100]

def obj(row, addr):
    o = obj_bytes(row, addr)
    return dict(name=o[0x10:0x18].decode('latin1'), ch=u16(o, 0x1E), x=s16(o, 0x24), y=s16(o, 0x28), sx=u16(o, 0x30),
                sy=u16(o, 0x32), flags=o[0x0F], anim=u16(o, 0x40), cnt=o[0x42], step=o[0x43], nxt=u32(o, 0x44),
                ticks=o[0x4A], ptr=u32(o, 0x94), trailer=u16(o, 0x72), boxes=u32(o, 0x74), raw=o)

def new_objects(rows, pool=POOL):
    """per row, the pool slots of the objects the capture made (TODO #144): a task alive now (name byte 0 not 0) that was
    not alive at the start, or one that died during the capture (its step pointer +$94 moved since the start: its death
    frames kept, name byte 0 = 0). Dead slots at the start keep stale animations and pointers (slot 12: Kim's $50A0)
    and live start tasks (stage, partners, shadows) are not the move's. The first captures (until 2026-10-06) read
    only $100000-$103FFF and dropped every slot with an animation at the start: the Hienzan pillar was lost.
    A task that took a dead slot and never loaded a step (its animation +$40 and step pointer +$94 still the slot's
    leftovers from the start) is no object of the move either (TODO #180): Kizuna's sound task 'SOUND' (code $1D270)
    in slot 12 keeps the dead PALETTE's Kim $50A0 / $AED1C at x 43, y 44 and draws nothing [meas: the screen scan
    kim_screen.json 'fol 6246A_h' attributes no tile to it], yet the Phoenix's export drew it as a second Kim."""
    r0 = rows[0]['pool']
    live0 = {k for k in range(pool >> 8) if r0[k * 0x100 + 0x10] and r0[k * 0x100 + 0x40:k * 0x100 + 0x42] != b'\0\0'}
    stale = {k: (r0[k * 0x100 + 0x40:k * 0x100 + 0x42], u32(r0, k * 0x100 + 0x94)) for k in range(pool >> 8)}
    out = []
    for r in rows:
        ks = []
        for k in range(pool >> 8):
            o = r['pool'][k * 0x100:(k + 1) * 0x100]
            if not u32(o, 0x94) or k in live0: continue
            if (o[0x40:0x42], u32(o, 0x94)) == stale[k]: continue        # no step of its own: leftovers (SOUND)
            if o[0x10] or u32(o, 0x94) != u32(r0, k * 0x100 + 0x94): ks.append(k)
        out.append(ks)
    return out
