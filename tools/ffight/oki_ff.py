#!/usr/bin/env python3
"""Final Fight's OKI MSM6295 samples (ff_18.11c + ff_19.12c, 256 KB) and the sound CPU's command -> phrase mapping.

OKI ROM: 128 phrase records of 8 bytes at $0000 (start 24 bits, end 24 bits, 2 unused); 4-bit OKI ADPCM (Dialogic),
high nibble first; CPS1's OKI runs at 1 MHz / 132 = 7576 Hz.
The 68000 sends one byte per sound to the Z80 (latch $800180: FF's ring at a5+388, rec_ff.py 'snd' per frame); the
Z80 driver (ff_09.12b) turns a command into an OKI phrase on a channel (table read below, `--map`).

    python3 oki_ff.py wav [OUTDIR]        every phrase as a WAV (default /data/tmp/ffight/oki)
    python3 oki_ff.py map                 the Z80's command table"""
import os, struct, sys, wave, zipfile
ZIP = '/data/emu/roms/cps1/ffight.zip'
RATE = 1000000 // 132

def rom():
    z = zipfile.ZipFile(ZIP)
    return z.read('ff_18.11c') + z.read('ff_19.12c'), z.read('ff_09.12b')

def phrases(o):
    out = {}
    for k in range(1, 128):
        r = o[8 * k:8 * k + 8]
        st, en = r[0] << 16 | r[1] << 8 | r[2], r[3] << 16 | r[4] << 8 | r[5]
        if 0 < st < en < len(o): out[k] = (st, en)
    return out

STEP = [16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190,
        209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552]
ADJ = [-1, -1, -1, -1, 2, 4, 6, 8]
def decode(data):
    """OKI ADPCM -> 12-bit samples (MAME okiadpcm: signal clamped to -2048..2047)"""
    sig, ix, out = -2, 0, []
    for b in data:
        for n in (b >> 4, b & 15):
            s = STEP[ix]; d = s >> 3
            if n & 1: d += s >> 2
            if n & 2: d += s >> 1
            if n & 4: d += s
            sig = sig - d if n & 8 else sig + d
            sig = max(-2048, min(2047, sig)); ix = max(0, min(48, ix + ADJ[n & 7]))
            out.append(sig)
    return out

def wav(path, pcm, rate=RATE):
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    w.writeframes(b''.join(struct.pack('<h', v << 4) for v in pcm)); w.close()

def commands(z=None):
    """the Z80's command table ($1000: count, $1003: a word per command -> its record; a record with bit 7 of byte 0 =
    an OKI sound [$80 | flags][phrase][level][channel mask][priority], $031B) -> {command: (phrase, channel mask)}"""
    z = z or rom()[1]; out = {}
    for c in range(z[0x1000]):
        p = z[0x1003 + 2 * c] << 8 | z[0x1004 + 2 * c]
        if p and z[p] & 0x80 and z[p + 1]: out[c] = (z[p + 1], z[p + 3])
    return out

# the brawler's FF sounds (the 68000's command -> its OKI phrase, rec_ff.py 'snd' per action, commands()): the effects
# (songs.json sfx "from" {"game": "ffight", "cmd": "00XX"}) and the fighters' voices (voices.py ffight_list)
USED = {0x2F: 'swing (jab)', 0x00: 'hit', 0x02: 'Guy finisher swing', 0x03: 'Cody / Haggar finisher swing, Cody finisher hit',
        0x09: 'Haggar finisher hit', 0x01: 'knee, Guy finisher hit', 0x06: 'headbutt', 0x04: 'Guy / Cody throw',
        0x07: 'backdrop', 0x0B: 'piledriver', 0x0D: 'body on the floor', 0x0C: 'Guy special', 0x1C: 'Cody special',
        0x1D: 'Haggar special', 0x05: 'Guy flying knee', 0x1B: 'Cody flying knee'}

_V = None
def vrom():
    """the USED commands' phrases as a YM2610 ADPCM-A bank (resampled 7576 -> 18518 Hz, linear; each sample on its own
    256-byte pages, page 0 empty): (bytes, {command: (first page, last page)}) for build_snd / voices.py"""
    global _V
    if _V is None:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        import wav_encoder as WE
        o, z = rom(); ph = phrases(o); cmd = commands(z)
        v = bytearray(256); idx = {}
        for c in sorted(USED):
            st, en = ph[cmd[c][0]]; pcm = decode(o[st:en + 1])
            n = len(pcm) * 18518 // RATE
            up = [pcm[min(len(pcm) - 1, int(i * RATE / 18518))] << 4 for i in range(n)]
            import numpy as np
            a = WE.encode_adpcma(np.array(up, dtype=np.int16))
            a = bytes(a) + bytes((-len(a)) % 256)
            idx[c] = (len(v) >> 8, (len(v) + len(a) >> 8) - 1); v += a
        _V = (bytes(v), idx)
    return _V

def main():
    o, z = rom()
    if sys.argv[1:2] == ['map']:
        for c, (p, ch) in sorted(commands(z).items()): print(f'{c:02X} -> phrase {p:02X} ch {ch:X}  {USED.get(c, "")}')
        return
    if sys.argv[1:2] == ['wav']:
        d = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/ffight/oki'; os.makedirs(d, exist_ok=True)
        for k, (st, en) in phrases(o).items():
            pcm = decode(o[st:en + 1]); wav(os.path.join(d, f'{k:02X}.wav'), pcm)
            print(f'{k:02X} {st:06X}-{en:06X} {len(pcm) / RATE:.2f} s')

if __name__ == '__main__': main()
