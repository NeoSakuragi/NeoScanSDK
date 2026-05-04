#!/usr/bin/env python3
"""NeoScan build orchestrator: compile, link, and package a Neo Geo ROM."""
import sys
import os
import struct
import subprocess
import zipfile
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SDK_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'sdk')


def pad_rom(data, target_size, fill=0x00):
    """Pad ROM data to target size."""
    if len(data) >= target_size:
        return data[:target_size]
    return data + bytes([fill] * (target_size - len(data)))


def byte_swap_16(data):
    """Swap every pair of bytes (for MAME load16_word_swap)."""
    out = bytearray(len(data))
    for i in range(0, len(data) - 1, 2):
        out[i] = data[i + 1]
        out[i + 1] = data[i]
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description='NeoScan ROM builder')
    parser.add_argument('--elf', required=True, help='Linked ELF file')
    parser.add_argument('--c1', required=True, help='C1 ROM tile data')
    parser.add_argument('--c2', required=True, help='C2 ROM tile data')
    parser.add_argument('--s1', default=None, help='S1 ROM font/fix data (default: empty)')
    parser.add_argument('--v1', default=None, help='V1 ROM ADPCM-A SFX data')
    parser.add_argument('--v1-overlay', default=None, help='ADPCM data to overlay onto V1 ROM (music samples)')
    parser.add_argument('--sound-table', default=None, help='Sound sample table for M ROM')
    parser.add_argument('--voice-table', default=None, help='Voice sample table for M ROM')
    parser.add_argument('--seq-blob',default=None)
    parser.add_argument('--fm-freq-table',default=None)
    parser.add_argument('--music', action='append', default=[], help='VGM music stream for M ROM (repeatable)')
    parser.add_argument('--donor-m1', default=None, help='Use donor M-ROM directly (skip driver build)')
    parser.add_argument('--donor-v1', default=None, help='Use donor V-ROM directly')
    parser.add_argument('--donor-s1', default=None, help='Use donor S-ROM directly')
    parser.add_argument('--name', default='neoscan', help='ROM set name')
    parser.add_argument('--ngh', default='999', help='NGH number string')
    parser.add_argument('-o', '--output', default='rom.zip', help='Output ZIP')
    parser.add_argument('--p-size', type=int, default=0x80000, help='P ROM size')
    parser.add_argument('--c-size', type=int, default=0x100000, help='C ROM size per chip')
    parser.add_argument('--s-size', type=int, default=0x20000, help='S ROM size')
    parser.add_argument('--m-size', type=int, default=0x20000, help='M ROM size')
    parser.add_argument('--v-size', type=int, default=0x80000, help='V ROM size')
    args = parser.parse_args()

    build_dir = os.path.dirname(os.path.abspath(args.output))
    rom_dir = os.path.join(build_dir, 'roms', args.name)
    hash_dir = os.path.join(build_dir, 'hash')
    os.makedirs(rom_dir, exist_ok=True)
    os.makedirs(hash_dir, exist_ok=True)

    ngh = args.ngh

    # --- P ROM ---
    p_bin = os.path.join(build_dir, 'rom.bin')
    subprocess.check_call([
        'm68k-linux-gnu-objcopy', '-O', 'binary', args.elf, p_bin
    ])
    p_data = pad_rom(open(p_bin, 'rb').read(), args.p_size)
    p_data = byte_swap_16(p_data)
    p_path = os.path.join(rom_dir, f'{ngh}-p1.p1')
    with open(p_path, 'wb') as f:
        f.write(p_data)

    # --- C ROMs ---
    c1_data = pad_rom(open(args.c1, 'rb').read(), args.c_size)
    c2_data = pad_rom(open(args.c2, 'rb').read(), args.c_size)
    c1_path = os.path.join(rom_dir, f'{ngh}-c1.c1')
    c2_path = os.path.join(rom_dir, f'{ngh}-c2.c2')
    with open(c1_path, 'wb') as f:
        f.write(c1_data)
    with open(c2_path, 'wb') as f:
        f.write(c2_data)

    # --- S ROM ---
    if args.donor_s1 and os.path.exists(args.donor_s1):
        s_data = pad_rom(open(args.donor_s1, 'rb').read(), args.s_size)
        print(f"Using donor S-ROM: {args.donor_s1}")
    elif args.s1:
        s_data = pad_rom(open(args.s1, 'rb').read(), args.s_size)
    else:
        s_data = bytes(args.s_size)
    s_path = os.path.join(rom_dir, f'{ngh}-s1.s1')
    with open(s_path, 'wb') as f:
        f.write(s_data)

    # --- M ROM ---
    if args.donor_m1 and os.path.exists(args.donor_m1):
        m_data = pad_rom(open(args.donor_m1, 'rb').read(), args.m_size)
        print(f"Using donor M-ROM: {args.donor_m1}")
    else:
        m_data = bytes(args.m_size)
    m_path = os.path.join(rom_dir, f'{ngh}-m1.m1')
    with open(m_path, 'wb') as f:
        f.write(m_data)

    # --- V ROM ---
    if args.donor_v1 and os.path.exists(args.donor_v1):
        v_data = open(args.donor_v1, 'rb').read()
        print(f"Using donor V-ROM: {args.donor_v1} ({len(v_data)//1024}KB)")
    else:
        v_data = bytes(args.v_size)
    v_path = os.path.join(rom_dir, f'{ngh}-v1.v1')
    with open(v_path, 'wb') as f:
        f.write(v_data)

    # --- Softlist XML ---
    from softlist import build_softlist_xml
    rom_files = {
        'p1': p_path, 's1': s_path, 'm1': m_path,
        'v1': v_path, 'c1': c1_path, 'c2': c2_path,
    }
    xml = build_softlist_xml(args.name, 'NeoScan Homebrew', rom_files)
    xml_path = os.path.join(hash_dir, 'neogeo.xml')
    with open(xml_path, 'w') as f:
        f.write(xml)

    # --- ZIP ---
    all_roms = [p_path, s_path, m_path, v_path, c1_path, c2_path]
    zip_path = args.output
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rom_file in all_roms:
            zf.write(rom_file, os.path.basename(rom_file))
    print(f"ROM: {zip_path}")

    # --- .neo file (flash cart / MiSTer format) ---
    neo_path = os.path.splitext(zip_path)[0] + '.neo'
    c1_raw = open(c1_path, 'rb').read()
    c2_raw = open(c2_path, 'rb').read()
    c_interleaved = bytearray(len(c1_raw) + len(c2_raw))
    for i in range(len(c1_raw)):
        c_interleaved[i * 2] = c1_raw[i]
        c_interleaved[i * 2 + 1] = c2_raw[i] if i < len(c2_raw) else 0

    # P ROM for .neo: word-swapped, same as commercial .neo files
    p_neo = p_data

    neo_header = bytearray(4096)
    neo_header[0:4] = b'NEO\x01'                              # magic
    struct.pack_into('<I', neo_header, 0x04, len(p_neo))       # P size
    struct.pack_into('<I', neo_header, 0x08, len(s_data))      # S size
    struct.pack_into('<I', neo_header, 0x0C, len(m_data))      # M size
    struct.pack_into('<I', neo_header, 0x10, len(v_data))      # V1 size
    struct.pack_into('<I', neo_header, 0x14, 0)                # V2 size
    struct.pack_into('<I', neo_header, 0x18, len(c_interleaved))  # C size
    struct.pack_into('<I', neo_header, 0x1C, 2026)             # year
    struct.pack_into('<I', neo_header, 0x20, 0)                # genre
    struct.pack_into('<I', neo_header, 0x24, 0)                # screenshot
    struct.pack_into('<I', neo_header, 0x28, int(ngh))         # NGH
    name_bytes = args.name.upper().encode('ascii')[:32]
    neo_header[0x2C:0x2C + len(name_bytes)] = name_bytes

    with open(neo_path, 'wb') as f:
        f.write(bytes(neo_header))
        f.write(p_neo)
        f.write(s_data)
        f.write(m_data)
        f.write(v_data)
        f.write(bytes(c_interleaved))
    print(f"NEO: {neo_path} ({os.path.getsize(neo_path):,} bytes)")

    # --- Summary ---
    print(f"  P ROM: {len(p_data):,} bytes")
    print(f"  C ROM: {len(c1_data):,} + {len(c2_data):,} bytes")
    print(f"  S ROM: {len(s_data):,} bytes")
    print(f"  M ROM: {len(m_data):,} bytes")
    print(f"  V ROM: {len(v_data):,} bytes")
    print(f"  Softlist: {xml_path}")


if __name__ == '__main__':
    main()
