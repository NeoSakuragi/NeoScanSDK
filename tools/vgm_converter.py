#!/usr/bin/env python3
"""Convert VGM files to a compact frame-based stream for the Neo Geo Z80.

Extracts embedded ADPCM sample data and produces a register write stream.
VGM files for YM2610 games typically embed ADPCM-A drum samples and
ADPCM-B voice data that must be placed in the V ROM.

Output files:
  - Stream binary: frame-based register writes for the Z80
  - Samples binary: ADPCM data to overlay onto V ROM at original addresses
  - Samples info: JSON with rom_size and chunk offsets
"""
import argparse
import gzip
import json
import os
import struct


VGM_MAGIC = b'Vgm '
SAMPLES_PER_FRAME = 735  # 44100 / 60


def load_vgm(path):
    data = open(path, 'rb').read()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    if data[:4] != VGM_MAGIC:
        raise ValueError("Not a VGM file")
    return data


def parse_header(data):
    version = struct.unpack_from('<I', data, 0x08)[0]
    total_samples = struct.unpack_from('<I', data, 0x18)[0]
    loop_offset_rel = struct.unpack_from('<I', data, 0x1C)[0]
    loop_samples = struct.unpack_from('<I', data, 0x20)[0]

    if version >= 0x150:
        data_offset_rel = struct.unpack_from('<I', data, 0x34)[0]
        data_start = 0x34 + data_offset_rel if data_offset_rel else 0x40
    else:
        data_start = 0x40

    loop_abs = (0x1C + loop_offset_rel) if loop_offset_rel else 0

    ym2610_clock = 0
    if len(data) > 0x50:
        ym2610_clock = struct.unpack_from('<I', data, 0x4C)[0]

    return {
        'version': version,
        'total_samples': total_samples,
        'loop_offset': loop_abs,
        'loop_samples': loop_samples,
        'data_start': data_start,
        'ym2610_clock': ym2610_clock,
    }


def extract_data_blocks(data, data_start):
    """Extract ADPCM data blocks (0x67 commands) from VGM data.

    Returns dict with 'adpcma' and 'adpcmb' entries, each a list of
    (rom_size, start_addr, chunk_data) tuples.
    """
    blocks = {'adpcma': [], 'adpcmb': []}
    pos = data_start

    while pos < len(data):
        cmd = data[pos]
        if cmd == 0x67:
            dtype = data[pos + 2]
            block_size = struct.unpack_from('<I', data, pos + 3)[0]
            payload = data[pos + 7:pos + 7 + block_size]

            if dtype in (0x82, 0x83) and block_size > 8:
                rom_size = struct.unpack_from('<I', payload, 0)[0]
                start_addr = struct.unpack_from('<I', payload, 4)[0]
                chunk_data = payload[8:]
                key = 'adpcma' if dtype == 0x82 else 'adpcmb'
                blocks[key].append((rom_size, start_addr, chunk_data))

            pos += 7 + block_size
        elif cmd == 0x66:
            break
        elif cmd in (0x58, 0x59):
            pos += 3
        elif cmd == 0x61:
            pos += 3
        elif cmd in (0x62, 0x63):
            pos += 1
        elif 0x70 <= cmd <= 0x7F:
            pos += 1
        else:
            pos += 1

    return blocks


def build_sample_rom(blocks, min_size=0):
    """Build a combined sample ROM from extracted data blocks.

    Places ADPCM-A and ADPCM-B data at their original addresses in a
    single ROM image (Neo Geo uses one V ROM for both).

    Returns (rom_bytes, info_dict).
    """
    max_addr = min_size
    chunks = []

    for key in ('adpcma', 'adpcmb'):
        for rom_size, start_addr, chunk_data in blocks[key]:
            end_addr = start_addr + len(chunk_data)
            max_addr = max(max_addr, end_addr)
            chunks.append((start_addr, chunk_data))

    if not chunks:
        return None, None

    # Round up to 256-byte boundary
    rom_size = (max_addr + 255) & ~255
    rom = bytearray([0x80] * rom_size)  # ADPCM silence fill

    for start_addr, chunk_data in chunks:
        rom[start_addr:start_addr + len(chunk_data)] = chunk_data

    total_sample_bytes = sum(len(c) for _, c in chunks)
    info = {
        'rom_size': rom_size,
        'num_chunks': len(chunks),
        'total_sample_bytes': total_sample_bytes,
        'adpcma_chunks': len(blocks['adpcma']),
        'adpcmb_chunks': len(blocks['adpcmb']),
    }
    return bytes(rom), info


def convert_vgm(data, header):
    """Convert VGM data to frame-based register write stream."""
    pos = header['data_start']
    loop_offset = header['loop_offset']
    end = len(data)

    frames = []
    current_frame = []
    wait_samples = 0
    loop_frame = 0xFFFF
    offset_to_frame = {}

    while pos < end:
        if pos == loop_offset and loop_frame == 0xFFFF:
            loop_frame = len(frames) + (1 if wait_samples >= SAMPLES_PER_FRAME else 0)

        offset_to_frame[pos] = len(frames)
        cmd = data[pos]

        if cmd == 0x58:  # YM2610 Port A
            reg = data[pos + 1]
            val = data[pos + 2]
            if reg in (0x24, 0x25, 0x26):
                pass  # Filter timer load/period registers
            elif reg == 0x27:
                # Preserve CH3 mode bits (6-7), drop timer control (0-5)
                ch3_bits = val & 0xC0
                if ch3_bits:
                    current_frame.append((0, reg, ch3_bits | 0x30))
            else:
                current_frame.append((0, reg, val))
            pos += 3

        elif cmd == 0x59:  # YM2610 Port B
            reg = data[pos + 1]
            val = data[pos + 2]
            current_frame.append((1, reg, val))
            pos += 3

        elif cmd == 0x61:
            n = struct.unpack_from('<H', data, pos + 1)[0]
            wait_samples += n
            pos += 3

        elif cmd == 0x62:
            wait_samples += 735
            pos += 1

        elif cmd == 0x63:
            wait_samples += 882
            pos += 1

        elif 0x70 <= cmd <= 0x7F:
            wait_samples += (cmd & 0x0F) + 1
            pos += 1

        elif cmd == 0x66:
            break

        elif cmd == 0x67:
            block_size = struct.unpack_from('<I', data, pos + 3)[0]
            pos += 7 + block_size

        else:
            pos += 1

        while wait_samples >= SAMPLES_PER_FRAME:
            frames.append(current_frame)
            current_frame = []
            wait_samples -= SAMPLES_PER_FRAME

    if current_frame:
        frames.append(current_frame)

    if loop_offset and loop_offset in offset_to_frame:
        loop_frame = offset_to_frame[loop_offset]

    return frames, loop_frame


ACTION_REGS = {
    (0, 0x28),  # FM key-on/off
    (0, 0x10),  # ADPCM-B control
    (1, 0x00),  # ADPCM-A key-on/off
}


def dedup_frames(frames):
    """Remove redundant register writes (same reg+val as current state).

    Skips dedup for action registers where re-writing the same value
    has side effects (key-on triggers, ADPCM control).
    """
    state = {}
    out = []
    for frame in frames:
        filtered = []
        for port, reg, val in frame:
            key = (port, reg)
            if key in ACTION_REGS or state.get(key) != val:
                filtered.append((port, reg, val))
                state[key] = val
        out.append(filtered)
    return out


def pack_stream(frames, loop_frame):
    """Pack frames into compact binary stream.

    Format v2:
      2 bytes: loop offset (relative to frame data start)
      Frame data:
        Count byte:
          $00-$7F: N register writes follow (2 bytes each: port_reg, val)
          $80-$FE: skip (N - $80) empty frames (1-126 frames)
          $FF: end marker
        Write format: 2 bytes per write
          Byte 0: bit 7 = port (0=A, 1=B), bits 6-0 = register
          Byte 1: value
    """
    frames = dedup_frames(frames)

    body = bytearray()
    loop_byte_offset = 0xFFFF
    empty_run = 0

    def flush_empties():
        nonlocal empty_run
        while empty_run > 0:
            n = min(empty_run, 126)
            body.append(0x80 + n)
            empty_run -= n

    for i, frame in enumerate(frames):
        if i == loop_frame and loop_frame != 0xFFFF:
            flush_empties()
            loop_byte_offset = len(body)

        if not frame:
            empty_run += 1
            continue

        flush_empties()
        n = min(len(frame), 127)
        body.append(n)
        for port, reg, val in frame[:127]:
            body.append(((port & 1) << 7) | (reg & 0x7F))
            body.append(val)

    flush_empties()
    body.append(0xFF)

    header = struct.pack('<H', loop_byte_offset)
    return bytes(header) + bytes(body)


def main():
    parser = argparse.ArgumentParser(
        description='Convert VGM to Neo Geo Z80 music stream')
    parser.add_argument('vgm', help='Input VGM or VGZ file')
    parser.add_argument('-o', '--output', required=True,
                        help='Output binary stream file')
    parser.add_argument('--samples-out', default=None,
                        help='Output ADPCM sample ROM file')
    args = parser.parse_args()

    data = load_vgm(args.vgm)
    header = parse_header(data)

    print(f"VGM version: {header['version']:08X}")
    print(f"YM2610 clock: {header['ym2610_clock']}")
    print(f"Total samples: {header['total_samples']} "
          f"({header['total_samples'] / 44100:.1f}s)")
    print(f"Loop: {'yes' if header['loop_offset'] else 'no'}")

    # Extract ADPCM sample data
    blocks = extract_data_blocks(data, header['data_start'])
    n_a = len(blocks['adpcma'])
    n_b = len(blocks['adpcmb'])
    a_bytes = sum(len(c) for _, _, c in blocks['adpcma'])
    b_bytes = sum(len(c) for _, _, c in blocks['adpcmb'])
    print(f"ADPCM-A blocks: {n_a} ({a_bytes:,} bytes)")
    print(f"ADPCM-B blocks: {n_b} ({b_bytes:,} bytes)")

    if args.samples_out and (n_a or n_b):
        sample_rom, info = build_sample_rom(blocks)
        if sample_rom:
            os.makedirs(os.path.dirname(os.path.abspath(args.samples_out)),
                        exist_ok=True)
            with open(args.samples_out, 'wb') as f:
                f.write(sample_rom)
            print(f"Sample ROM: {args.samples_out} "
                  f"({len(sample_rom):,} bytes, "
                  f"{info['num_chunks']} chunks)")

    # Convert register writes
    frames, loop_frame = convert_vgm(data, header)
    stream = pack_stream(frames, loop_frame)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'wb') as f:
        f.write(stream)

    total_writes = sum(len(f) for f in frames)
    print(f"Frames: {len(frames)} ({len(frames) / 60:.1f}s)")
    print(f"Loop frame: {loop_frame if loop_frame != 0xFFFF else 'none'}")
    print(f"Register writes: {total_writes}")
    print(f"Stream size: {len(stream)} bytes")


if __name__ == '__main__':
    main()
