#!/usr/bin/env python3
"""Convert WAV files to Neo Geo ADPCM-A format for the V ROM.

Produces a V ROM binary and a C header with sample IDs and a
sample table for the Z80 sound driver.
"""

import argparse
import os
import struct
import wave
import numpy as np


ADPCM_RATE = 18500

STEP_TABLE = [
    16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
    73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253,
    279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876,
    963, 1060, 1166, 1282, 1411, 1552
]

INDEX_ADJ = [-1, -1, -1, -1, 2, 5, 7, 9]


def encode_adpcma(pcm_data):
    """Encode 16-bit signed PCM to ADPCM-A bytes (2 samples per byte)."""
    signal = (pcm_data.astype(np.int32) * 2048) // 32768
    predicted = 0
    step_idx = 0
    nibbles = []

    for sample in signal:
        step = STEP_TABLE[step_idx]
        diff = sample - predicted

        nibble = 0
        if diff < 0:
            nibble = 8
            diff = -diff

        if diff >= step:
            nibble |= 4
            diff -= step
        if diff >= (step >> 1):
            nibble |= 2
            diff -= (step >> 1)
        if diff >= (step >> 2):
            nibble |= 1

        delta = (step >> 3)
        if nibble & 4:
            delta += step
        if nibble & 2:
            delta += (step >> 1)
        if nibble & 1:
            delta += (step >> 2)
        if nibble & 8:
            predicted -= delta
        else:
            predicted += delta

        predicted = max(-2048, min(2047, predicted))

        step_idx += INDEX_ADJ[nibble & 7]
        step_idx = max(0, min(48, step_idx))

        nibbles.append(nibble & 0xF)

    result = bytearray()
    for i in range(0, len(nibbles), 2):
        hi = nibbles[i]
        lo = nibbles[i + 1] if i + 1 < len(nibbles) else 0
        result.append((hi << 4) | lo)

    return bytes(result)


def load_wav(path, target_rate=ADPCM_RATE):
    """Load a WAV file and return 16-bit mono PCM at target sample rate."""
    with wave.open(path, 'rb') as w:
        nch = w.getnchannels()
        sampwidth = w.getsampwidth()
        rate = w.getframerate()
        nframes = w.getnframes()
        raw = w.readframes(nframes)

    if sampwidth == 1:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128
        samples *= 256
    elif sampwidth == 2:
        samples = np.frombuffer(raw, dtype=np.int16)
    elif sampwidth == 4:
        samples = (np.frombuffer(raw, dtype=np.int32) >> 16).astype(np.int16)
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1).astype(np.int16)

    if rate != target_rate:
        n_out = int(len(samples) * target_rate / rate)
        x_old = np.arange(len(samples))
        x_new = np.linspace(0, len(samples) - 1, n_out)
        samples = np.interp(x_new, x_old, samples.astype(np.float64)).astype(np.int16)

    return samples


def main():
    parser = argparse.ArgumentParser(
        description='Convert WAV files to Neo Geo ADPCM-A V ROM')
    parser.add_argument('wavs', nargs='+', help='Input WAV files')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory')
    parser.add_argument('--vrom-size', type=int, default=0x80000,
                        help='V ROM size (default: 512KB)')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    vrom = bytearray(args.vrom_size)
    offset = 0
    samples = []

    for path in args.wavs:
        name = os.path.splitext(os.path.basename(path))[0]
        print(f"  Encoding {os.path.basename(path)}...")

        pcm = load_wav(path)
        adpcm = encode_adpcma(pcm)

        offset = (offset + 255) & ~255

        if offset + len(adpcm) > args.vrom_size:
            print(f"    WARNING: V ROM full, skipping {name}")
            continue

        start_256 = offset // 256
        end_offset = offset + len(adpcm) - 1
        end_256 = end_offset // 256

        vrom[offset:offset + len(adpcm)] = adpcm

        duration_ms = len(pcm) * 1000 // ADPCM_RATE
        print(f"    {len(pcm)} samples ({duration_ms}ms), "
              f"ADPCM {len(adpcm)} bytes, "
              f"addr ${start_256:04X}-${end_256:04X}")

        samples.append((name, start_256, end_256))
        offset = end_offset + 1

    vrom_path = os.path.join(args.output_dir, 'vrom.bin')
    with open(vrom_path, 'wb') as f:
        f.write(vrom)

    header_path = os.path.join(args.output_dir, 'sounds.h')
    with open(header_path, 'w') as f:
        f.write('#ifndef SOUNDS_H\n#define SOUNDS_H\n\n')
        for i, (name, start, end) in enumerate(samples):
            f.write(f'#define SND_{name.upper()} {i + 1}\n')
        f.write(f'\n#define SND_COUNT {len(samples)}\n')
        f.write('\n#endif\n')

    table_path = os.path.join(args.output_dir, 'sound_table.bin')
    with open(table_path, 'wb') as f:
        for _, start, end in samples:
            f.write(struct.pack('<HH', start, end))

    print(f"  V ROM: {vrom_path} ({len(vrom)} bytes, {len(samples)} samples)")
    print(f"  Header: {header_path}")
    print(f"  Table: {table_path}")


if __name__ == '__main__':
    main()
