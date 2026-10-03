#!/usr/bin/env python3
"""Render the SSG part of a ymtap.lua capture to WAV (approximate: square tones, no noise / envelope shapes beyond
a fixed level, the AY log volume curve, SSG clock 2 MHz = YM2610 8 MHz / 4: f = 125000 / period).
    python3 ssgwav.py TAP.txt OUT.wav FROM_FRAME TO_FRAME"""
import struct, sys, math, wave

RATE, FPS = 44100, 59.185
VOL = [0] + [10 ** ((v - 15) * 1.5 / 10) for v in range(1, 16)]   # ~1.5 dB a step

def render(path, f0, f1):
    regs = [0] * 16; regs[7] = 0x3F
    per_frame = {}
    f = 0
    for l in open(path):
        p = l.split()
        if p[0] == 'f': f = int(p[1]); continue
        if p[0] == 'a' and int(p[1], 16) <= 0x0D: per_frame.setdefault(f, []).append((int(p[1], 16), int(p[2], 16)))
    out, phase = [], [0.0, 0.0, 0.0]
    for fr in range(f0, f1):
        for r, v in per_frame.get(fr, []): regs[r] = v
        n = int(RATE / FPS)
        for _ in range(n):
            s = 0.0
            for ch in range(3):
                if regs[7] >> ch & 1: continue                   # tone disabled for this channel
                tp = regs[2 * ch] | (regs[2 * ch + 1] & 0x0F) << 8
                if not tp: continue
                lvl = regs[8 + ch] & 0x0F if not regs[8 + ch] & 0x10 else 12
                phase[ch] = (phase[ch] + 125000 / tp / RATE) % 1.0
                s += VOL[lvl] * (1 if phase[ch] < 0.5 else -1)
            out.append(max(-1, min(1, s / 3)))
    return out

if __name__ == '__main__':
    path, wav, f0, f1 = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    s = render(path, f0, f1)
    w = wave.open(wav, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(b''.join(struct.pack('<h', int(x * 30000)) for x in s)); w.close()
    print(wav, f'{len(s) / RATE:.2f} s')
