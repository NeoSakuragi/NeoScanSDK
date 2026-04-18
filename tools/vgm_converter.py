#!/usr/bin/env python3
"""Convert VGM files to a compact frame-based stream for the Neo Geo Z80.

Output format (binary):
  Header (6 bytes):
    uint16 LE: total frames
    uint16 LE: loop frame (0xFFFF = no loop)
    uint16 LE: data start offset (relative to stream start)

  Frame stream:
    Per frame: 1 byte count + count * 3 bytes of (port, reg, data)
      port: 0 = Port A ($04/$05), 1 = Port B ($06/$07)
      count 0: empty frame (just wait)
    End marker: 0xFF byte
"""
import argparse
import gzip
import os
import struct


VGM_MAGIC = b'Vgm '
SAMPLES_PER_FRAME = 735  # 44100 / 60


def load_vgm(path):
    """Load a VGM or VGZ file, return raw bytes."""
    data = open(path, 'rb').read()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    if data[:4] != VGM_MAGIC:
        raise ValueError("Not a VGM file")
    return data


def parse_header(data):
    """Parse VGM header, return dict of relevant fields."""
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
    if len(data) > 0x48:
        ym2610_clock = struct.unpack_from('<I', data, 0x44)[0]

    return {
        'version': version,
        'total_samples': total_samples,
        'loop_offset': loop_abs,
        'loop_samples': loop_samples,
        'data_start': data_start,
        'ym2610_clock': ym2610_clock,
    }


def convert_vgm(data, header):
    """Convert VGM data to frame-based register write stream.

    Returns (frames, loop_frame) where frames is a list of lists of
    (port, reg, val) tuples, and loop_frame is the frame index to loop to.
    """
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
            if reg not in (0x24, 0x25, 0x26, 0x27):
                current_frame.append((0, reg, val))
            pos += 3

        elif cmd == 0x59:  # YM2610 Port B
            reg = data[pos + 1]
            val = data[pos + 2]
            current_frame.append((1, reg, val))
            pos += 3

        elif cmd == 0x61:  # Wait N samples
            n = struct.unpack_from('<H', data, pos + 1)[0]
            wait_samples += n
            pos += 3

        elif cmd == 0x62:  # Wait 735 samples (1/60s)
            wait_samples += 735
            pos += 1

        elif cmd == 0x63:  # Wait 882 samples (1/50s)
            wait_samples += 882
            pos += 1

        elif 0x70 <= cmd <= 0x7F:  # Wait 1-16 samples
            wait_samples += (cmd & 0x0F) + 1
            pos += 1

        elif cmd == 0x66:  # End of data
            break

        elif cmd == 0x67:  # Data block (skip)
            block_size = struct.unpack_from('<I', data, pos + 3)[0]
            pos += 7 + block_size

        else:
            # Skip unknown commands
            pos += 1

        # Emit frames for accumulated wait
        while wait_samples >= SAMPLES_PER_FRAME:
            frames.append(current_frame)
            current_frame = []
            wait_samples -= SAMPLES_PER_FRAME

    # Final frame
    if current_frame:
        frames.append(current_frame)

    # Fix loop_frame if it was set at the loop offset
    if loop_offset and loop_offset in offset_to_frame:
        loop_frame = offset_to_frame[loop_offset]

    return frames, loop_frame


def pack_stream(frames, loop_frame):
    """Pack frames into compact binary stream.

    Format: 2 bytes loop offset (relative to frame data start), then frames, then 0xFF.
    """
    body = bytearray()
    loop_byte_offset = 0xFFFF

    for i, frame in enumerate(frames):
        if i == loop_frame and loop_frame != 0xFFFF:
            loop_byte_offset = len(body)
        n = min(len(frame), 127)
        body.append(n)
        for port, reg, val in frame[:127]:
            body.append(port & 1)
            body.append(reg)
            body.append(val)

    body.append(0xFF)  # End marker

    header = struct.pack('<H', loop_byte_offset)
    return bytes(header) + bytes(body)


def main():
    parser = argparse.ArgumentParser(
        description='Convert VGM to Neo Geo Z80 music stream')
    parser.add_argument('vgm', help='Input VGM or VGZ file')
    parser.add_argument('-o', '--output', required=True,
                        help='Output binary stream file')
    args = parser.parse_args()

    data = load_vgm(args.vgm)
    header = parse_header(data)

    print(f"VGM version: {header['version']:08X}")
    print(f"YM2610 clock: {header['ym2610_clock']}")
    print(f"Total samples: {header['total_samples']} "
          f"({header['total_samples'] / 44100:.1f}s)")
    print(f"Loop: {'yes' if header['loop_offset'] else 'no'}")

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
