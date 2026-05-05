#!/usr/bin/env python3
"""Generate a synthetic drum and bass sample kit as WAV files.

All output files are mono, 16-bit signed, 18500 Hz — ready for the
NeoScan ADPCM-A pipeline (wav_encoder.py).

Usage:
    python3 gen_drum_kit.py -o examples/sound_lab/res/
"""
import argparse
import os
import struct
import wave

import numpy as np


RATE = 18500  # ADPCM-A native sample rate


def write_wav(path, samples):
    """Write mono 16-bit WAV at RATE Hz."""
    pcm = np.clip(samples, -32768, 32767).astype(np.int16)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    dur_ms = len(pcm) * 1000 // RATE
    print(f"  {os.path.basename(path):24s}  {len(pcm):6d} samples  {dur_ms:4d}ms")


def gen_kick(duration=0.3):
    """Bass drum: pitch-dropping sine with fast exponential decay."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # Frequency sweeps from 150 Hz down to 45 Hz
    freq = 150 * np.exp(-t * 12) + 45
    phase = 2 * np.pi * np.cumsum(freq / RATE)
    env = np.exp(-t * 10)
    # Add a click transient at the start
    click = np.zeros(n)
    click_len = min(int(RATE * 0.003), n)
    click[:click_len] = np.exp(-np.linspace(0, 6, click_len)) * 0.6
    signal = np.sin(phase) * env + click
    signal = signal / np.max(np.abs(signal))
    return (signal * 30000).astype(np.int16)


def gen_snare(duration=0.2):
    """Snare drum: filtered noise burst + body tone."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(n) * np.exp(-t * 18)
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t * 25)
    signal = noise * 0.65 + tone * 0.35
    signal = signal / np.max(np.abs(signal))
    return (signal * 30000).astype(np.int16)


def gen_hihat_closed(duration=0.08):
    """Closed hi-hat: very short high-frequency noise burst."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    # Crude high-pass: difference filter
    hp = np.diff(noise, prepend=0)
    hp = np.diff(hp, prepend=0)
    signal = hp * np.exp(-t * 40)
    signal = signal / np.max(np.abs(signal))
    return (signal * 28000).astype(np.int16)


def gen_hihat_open(duration=0.3):
    """Open hi-hat: longer high-frequency noise with slower decay."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    rng = np.random.default_rng(13)
    noise = rng.standard_normal(n)
    hp = np.diff(noise, prepend=0)
    hp = np.diff(hp, prepend=0)
    signal = hp * np.exp(-t * 8)
    signal = signal / np.max(np.abs(signal))
    return (signal * 28000).astype(np.int16)


def gen_crash(duration=0.6):
    """Crash cymbal: wide-band noise with long decay and metallic resonance."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    rng = np.random.default_rng(99)
    noise = rng.standard_normal(n)
    # Mix raw noise + high-passed noise for shimmer
    hp = np.diff(noise, prepend=0)
    # Add some metallic ring at ~3kHz and ~5kHz
    ring1 = np.sin(2 * np.pi * 3100 * t) * np.exp(-t * 4) * 0.15
    ring2 = np.sin(2 * np.pi * 5200 * t) * np.exp(-t * 5) * 0.10
    signal = (noise * 0.4 + hp * 0.4 + ring1 + ring2) * np.exp(-t * 3.5)
    signal = signal / np.max(np.abs(signal))
    return (signal * 28000).astype(np.int16)


def gen_tom(duration=0.25, base_freq=100):
    """Tom drum: pitch-dropping sine (higher base freq than kick)."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    freq = base_freq * np.exp(-t * 6) + base_freq * 0.4
    phase = 2 * np.pi * np.cumsum(freq / RATE)
    env = np.exp(-t * 10)
    signal = np.sin(phase) * env
    signal = signal / np.max(np.abs(signal))
    return (signal * 28000).astype(np.int16)


def gen_clap(duration=0.15):
    """Hand clap: multiple short noise bursts layered."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    rng = np.random.default_rng(77)
    noise = rng.standard_normal(n)
    # Three quick bursts at 0ms, 10ms, 20ms, then a longer tail
    signal = np.zeros(n)
    for offset_ms in [0, 8, 16]:
        start = int(RATE * offset_ms / 1000)
        burst_len = min(int(RATE * 0.012), n - start)
        if start + burst_len <= n:
            burst_t = np.linspace(0, 0.012, burst_len, endpoint=False)
            signal[start:start + burst_len] += noise[start:start + burst_len] * np.exp(-burst_t * 80)
    # Tail
    tail_start = int(RATE * 0.025)
    if tail_start < n:
        tail_t = np.linspace(0, duration - 0.025, n - tail_start, endpoint=False)
        signal[tail_start:] += noise[tail_start:] * np.exp(-tail_t * 20) * 0.6
    signal = signal / np.max(np.abs(signal))
    return (signal * 28000).astype(np.int16)


def gen_bass_hit(duration=0.4):
    """Bass guitar pluck: low sine with harmonics and fast attack."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    f0 = 55  # A1
    # Fundamental + harmonics with decreasing amplitude
    signal = np.sin(2 * np.pi * f0 * t) * 0.6
    signal += np.sin(2 * np.pi * f0 * 2 * t) * 0.25 * np.exp(-t * 6)
    signal += np.sin(2 * np.pi * f0 * 3 * t) * 0.10 * np.exp(-t * 10)
    signal += np.sin(2 * np.pi * f0 * 4 * t) * 0.05 * np.exp(-t * 15)
    # Pluck envelope: fast attack, moderate decay
    env = np.exp(-t * 5) * 0.8 + 0.2 * np.exp(-t * 1.5)
    signal = signal * env
    signal = signal / np.max(np.abs(signal))
    return (signal * 30000).astype(np.int16)


def gen_bass_slide(duration=0.5):
    """Bass slide: pitch sweeping upward with vibrato."""
    n = int(RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # Slide from E1 (41Hz) up to A1 (55Hz)
    freq = 41 + (55 - 41) * (t / duration)
    # Add subtle vibrato
    freq = freq + np.sin(2 * np.pi * 5 * t) * 1.5
    phase = 2 * np.pi * np.cumsum(freq / RATE)
    signal = np.sin(phase) * 0.7
    signal += np.sin(phase * 2) * 0.2 * np.exp(-t * 3)
    env = np.exp(-t * 2.5) * 0.7 + 0.3 * np.exp(-t * 0.8)
    signal = signal * env
    signal = signal / np.max(np.abs(signal))
    return (signal * 30000).astype(np.int16)


INSTRUMENTS = [
    ("kick",         gen_kick),
    ("snare",        gen_snare),
    ("hihat_closed", gen_hihat_closed),
    ("hihat_open",   gen_hihat_open),
    ("crash",        gen_crash),
    ("tom_low",      lambda: gen_tom(base_freq=80)),
    ("tom_mid",      lambda: gen_tom(base_freq=130)),
    ("clap",         gen_clap),
    ("bass_hit",     gen_bass_hit),
    ("bass_slide",   gen_bass_slide),
]


def main():
    parser = argparse.ArgumentParser(
        description='Generate synthetic drum+bass WAV samples for Neo Geo ADPCM-A')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory for WAV files')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"Generating drum kit ({RATE} Hz, mono, 16-bit):")

    for name, gen_fn in INSTRUMENTS:
        path = os.path.join(args.output_dir, f'{name}.wav')
        samples = gen_fn()
        write_wav(path, samples)

    print(f"\nDone: {len(INSTRUMENTS)} WAV files in {args.output_dir}")


if __name__ == '__main__':
    main()
