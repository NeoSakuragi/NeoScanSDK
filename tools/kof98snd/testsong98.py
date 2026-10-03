#!/usr/bin/env python3
"""Synthetic KOF98 songs that exercise the opcodes no KOF98 song uses (effect types, level effect, ADPCM-B effects and
modes, direct-level mode, bends, the command-queue abort...), played in MAME and compared with song98.py's model.

    python3 testsong98.py M1.bin OUTDIR [test ...]

Each test song is written into the free $2C56-$2DFF area of the M1 ROM (ymtap.lua PATCH) and hooked on command $27
(a null entry in the song table): pointer $329E + 2*7 -> $2C60, bank byte ($2E06)[7] = 0 (fixed ROM)."""
import sys, os, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import song98, validate98

BASE = 0x2C60
MAME = ['mame', 'kof98', '-rompath', '/home/bruno/roms/neogeo;/home/bruno/Downloads', '-video', 'none', '-sound', 'none',
        '-nothrottle', '-skip_gameinfo', '-noplugin', 'cart_bridge', '-autoboot_script',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ymtap.lua')]

def vl(d):
    return bytes([d]) if d < 0x80 else bytes([0x80 | d >> 7, d & 0x7F])

def ev(delta, op, *p):
    """one event: delta (None = no delta byte), opcode, parameter bytes"""
    return (vl(delta) if delta is not None else b'') + bytes([0xC0 | op]) + bytes(p)

def note(delta, n, vel, gate=None):
    return ev(delta, 0x00, *vl(gate), n, vel) if gate is not None else ev(delta, 0x2A, n, vel)

def w(v): return [v & 0xFF, v >> 8 & 0xFF]

def fx1(t, delay, depth, step, speed, table=()):
    if t == 6: return ev(None, 0x14, 0, 6, delay, 0, 0, len(table), 0, speed) + b''.join(bytes(w(x)) for x in table)
    return ev(None, 0x14, 0, t, delay, *w(depth), *w(step), speed)

def fx2(t, delay, depth, speed, table):
    return ev(None, 0x14, 1, t, delay, depth, len(table), speed) + b''.join(bytes(w(x)) for x in table)

def build(chans, tempo=208, fm_att=0, b_att=0):
    """chans: {header index: stream bytes} -> song bytes at BASE"""
    head = bytearray(14 + 22)
    for k in chans: head[k] = 1
    head[11], head[12], head[13] = tempo, fm_att, b_att
    out = bytearray(head); pos = BASE + len(head)
    for k in sorted(chans):
        out[14 + 2 * k:16 + 2 * k] = bytes(w(pos)); out += chans[k]; pos += len(chans[k])
    if BASE + len(out) > 0x2E00: raise ValueError(f'test song too long: {len(out)} bytes')
    return bytes(out)

C4, D4, E4, G4 = 0x48, 0x4A, 0x4C, 0x4F

TESTS = {
    # FM1: every pitch-effect type on one channel, direct-level mode (no $26): TL = velocity
    'fxtypes': {0: ev(0, 0x03, 5) + ev(0, 0x31) +
                fx1(1, 3, 8, 1, 4) + ev(None, 0x12, 3) + note(40, C4, 0x10) +
                fx1(2, 0, 20, 3, 1) + note(40, D4, 0x10) +
                fx1(3, 1, 12, 4, 1) + note(40, E4, 0x10) +
                fx1(4, 2, 30, 4, 1) + note(40, G4, 0x10) +
                fx1(5, 0, 24, 6, 1) + note(40, C4, 0x10) +
                fx1(6, 0, 0, 0, 2, (0, 10, 20, 30)) + note(48, D4, 0x10) +
                fx1(2, 0, 0xFFEC, 5, 1) + note(40, E4, 0x10) +
                ev(None, 0x12, 2) + note(20, G4, 0x10) + ev(4, 0x06)},
    # FM2: level effect (bug: TL rewritten unchanged), modulator TL, LFO, AMS/PMS ($28, port bug), bend + range,
    # detune, transpose, octave and level offset in direct mode
    'fm2': {1: ev(0, 0x03, 5) + ev(0, 0x11, 0x0A) + ev(0, 0x28, 0x37) +
            fx2(6, 0, 0, 3, (0, 4, 8)) + ev(None, 0x12, 0x0C) + note(30, C4, 0x18) +
            ev(None, 0x12, 0x04) + ev(None, 0x2D, 0x20) + note(20, C4, 0x18) +
            ev(None, 0x05, 0x00, 0x60) + ev(6, 0x05, 0x00, 0x20) + ev(6, 0x23, *w(0x55)) + ev(None, 0x05, 0x00, 0x60) +
            ev(6, 0x05, 0x00, 0x40) + ev(6, 0x2E, 0x48) + note(20, D4, 0x18) + ev(None, 0x1D, 0x42) + note(20, D4, 0x18) +
            ev(None, 0x24, 1) + note(20, D4, 0x18) + ev(None, 0x25, 0x90) + ev(None, 0x24, 0) + note(20, D4, 0x18) +
            ev(None, 0x0F, 0x02) + ev(None, 0x25, 0x88) + note(20, D4, 0x18) + ev(4, 0x06)},
    # scaled mode ($26) volume / transpose; queue command (aborts the tick: FM4 after FM3 shifts by one tick);
    # inline patch; tie into the same / another note; untie; no-delta note; rest after gate
    'flow': {2: ev(0, 0x26) + ev(0, 0x2C, 0x60) + ev(0, 0x03, 5) + note(20, C4, 0x70, 10) + ev(0, 0x27, 0x1A) +
             note(20, C4, 0x40, 30) + note(20, C4, 0x40) + note(10, D4, 0x40, 25) + note(10, E4, 0x40) +
             ev(10, 0x0C, 0x60) + note(20, C4, 0x50, 5) + ev(0, 0x2C, 0x30) + note(20, C4, 0x50) + ev(4, 0x06),
             3: ev(0, 0x26) + ev(0, 0x24, 0x7F) + ev(0, 0x34, *range(0x00, 0x1C), 0x02, 0xC0, *([0] * 11)) +
             ev(0, 0x07, 3) + note(10, G4, 0x60, 4) + ev(None, 0x08) + note(None, C4, 0x60) + ev(30, 0x01) +
             note(20, E4, 0x60) + ev(0, 0x0E) + note(15, E4, 0x60, 40) + ev(15, 0x0E) + note(15, G4, 0x60) +
             ev(4, 0x06)},
    # ADPCM-B: pitch and level effects, kit mode, split mode, base note, bend on B (unguarded FM write)
    'adpcmb': {10: ev(0, 0x26) + ev(0, 0x2C, 0x60) + ev(0, 0x0F, 0) + ev(0, 0x03, 0x13) + ev(0, 0x31) +
               fx1(2, 2, 0x200, 0x80, 1) + fx2(6, 0, 0, 2, (0, 0x10, 0x20)) + ev(None, 0x12, 0x0F) +
               note(60, 0x48, 0x60) + ev(None, 0x12, 0x0A) + ev(None, 0x27, 0x30) + note(30, 0x48, 0x60) +
               ev(None, 0x0F, 1) + note(30, 0x02, 0x60) + note(30, 0x05, 0x60) +
               ev(None, 0x0F, 2) + ev(None, 0x29, 0x48, 0x40) + ev(None, 0x03, 0x00) + note(30, 0x40, 0x60) +
               note(30, 0x50, 0x60) + ev(None, 0x05, 0x00, 0x60) + ev(10, 0x05, 0x00, 0x40) + ev(4, 0x06)},
}

def patched(data, song):
    d = bytearray(data)
    d[BASE:BASE + len(song)] = song
    d[0x329E + 14:0x329E + 16] = bytes(w(BASE))
    d[(data[0x2E06] | data[0x2E07] << 8) + 7] = 0
    return bytes(d)

def run(data, name, outdir, frames=900):
    song = build(TESTS[name])
    d = patched(data, song)
    bankb = (data[0x2E06] | data[0x2E07] << 8) + 7
    patch = f'{BASE:X}:{song.hex()},{0x329E + 14:X}:{BASE & 0xFF:02X}{BASE >> 8:02X},{bankb:X}:00'
    out = os.path.join(outdir, f'test_{name}.txt')
    env = dict(os.environ, OUT=out, FRAMES=str(frames), IRQ='1', BLOCK='255', SEND='260:27', PATCH=patch)
    subprocess.run(MAME, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return d, out

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    outdir = sys.argv[2]
    for name in (sys.argv[3:] or TESTS):
        d, cap = run(data, name, outdir)
        print(f'== {name} ({len(build(TESTS[name]))} bytes)')
        validate98.compare(d, 0x27, cap)
