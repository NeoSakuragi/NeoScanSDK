#!/usr/bin/env python3
"""Generate a simple test VGM file with a melody on YM2610 SSG channels."""
import struct
import os

# YM2610 clock on Neo Geo
YM_CLOCK = 8000000

# SSG tone period: period = clock / (16 * freq)
def note_period(freq):
    return int(YM_CLOCK / (16 * freq))

# Note frequencies (octave 4-5)
NOTES = {
    'C4': 262, 'D4': 294, 'E4': 330, 'F4': 349,
    'G4': 392, 'A4': 440, 'B4': 494,
    'C5': 523, 'D5': 587, 'E5': 659, 'F5': 698,
    'G5': 784, 'A5': 880, 'R': 0,
}

# Simple melody (note, duration in frames at 60Hz)
MELODY = [
    ('E4', 15), ('E4', 15), ('R', 5), ('E4', 15), ('R', 5),
    ('C4', 15), ('E4', 15), ('G4', 30), ('R', 10),
    ('G4', 15), ('R', 15),
    ('C5', 15), ('R', 5), ('G4', 15), ('R', 10),
    ('E4', 15), ('R', 5), ('A4', 15), ('B4', 15),
    ('A4', 8), ('G4', 15), ('E5', 15), ('G5', 15),
    ('A5', 15), ('R', 5), ('F5', 15), ('G5', 15),
    ('R', 5), ('E5', 15), ('C5', 15), ('D5', 15),
    ('B4', 15), ('R', 15),
]


def build_vgm(melody, loop=True):
    """Build a VGM byte stream for the melody."""
    cmds = bytearray()

    # Init: SSG mixer = enable tone on channel A only
    cmds.append(0x58)  # Port A write
    cmds.append(0x07)  # Mixer register
    cmds.append(0x3E)  # Tone A on, rest off

    # Channel A volume = 12 (0-15)
    cmds.append(0x58)
    cmds.append(0x08)
    cmds.append(0x0C)

    loop_offset_pos = None

    for i, (note_name, dur) in enumerate(melody):
        if i == 0 and loop:
            loop_offset_pos = len(cmds)

        if note_name == 'R':
            # Silence: set volume to 0
            cmds.append(0x58)
            cmds.append(0x08)
            cmds.append(0x00)
        else:
            freq = NOTES[note_name]
            period = note_period(freq)
            # Set tone period
            cmds.append(0x58)
            cmds.append(0x00)  # Fine tune
            cmds.append(period & 0xFF)
            cmds.append(0x58)
            cmds.append(0x01)  # Coarse tune
            cmds.append((period >> 8) & 0x0F)
            # Set volume
            cmds.append(0x58)
            cmds.append(0x08)
            cmds.append(0x0C)

        # Wait for duration (in frames, each = 735 samples)
        for _ in range(dur):
            cmds.append(0x62)  # Wait 1/60s

    # End
    cmds.append(0x66)

    # Build VGM header
    data_offset = 0x80
    data_size = len(cmds)
    eof_offset = data_offset + data_size - 4

    total_samples = sum(dur for _, dur in melody) * 735

    if loop and loop_offset_pos is not None:
        loop_abs = data_offset + loop_offset_pos
        loop_rel = loop_abs - 0x1C
    else:
        loop_rel = 0
        total_samples_loop = 0

    header = bytearray(data_offset)  # 0x80 bytes to fit YM2610 clock at $44
    header[0:4] = b'Vgm '
    struct.pack_into('<I', header, 0x04, eof_offset)
    struct.pack_into('<I', header, 0x08, 0x00000171)  # Version 1.71
    struct.pack_into('<I', header, 0x18, total_samples)
    struct.pack_into('<I', header, 0x1C, loop_rel)
    struct.pack_into('<I', header, 0x20, total_samples if loop else 0)
    struct.pack_into('<I', header, 0x34, data_offset - 0x34)  # Data offset relative to 0x34
    struct.pack_into('<I', header, 0x44, YM_CLOCK)  # YM2610 clock

    return bytes(header) + bytes(cmds)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate test VGM melody')
    parser.add_argument('-o', '--output', required=True, help='Output VGM file')
    args = parser.parse_args()

    vgm = build_vgm(MELODY, loop=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'wb') as f:
        f.write(vgm)

    duration = sum(dur for _, dur in MELODY) / 60.0
    print(f"Test VGM: {args.output} ({len(vgm)} bytes, {duration:.1f}s)")


if __name__ == '__main__':
    main()
