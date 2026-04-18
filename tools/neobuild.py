#!/usr/bin/env python3
"""NeoScan build orchestrator: compile, link, and package a Neo Geo ROM."""
import sys
import os
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
    parser.add_argument('--music', default=None, help='VGM music stream for M ROM')
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
    if args.s1:
        s_data = pad_rom(open(args.s1, 'rb').read(), args.s_size)
    else:
        s_data = bytes(args.s_size)
    s_path = os.path.join(rom_dir, f'{ngh}-s1.s1')
    with open(s_path, 'wb') as f:
        f.write(s_data)

    # --- M ROM ---
    from mrom_builder import build_mrom
    table_bin = None
    if args.sound_table and os.path.exists(args.sound_table):
        table_bin = open(args.sound_table, 'rb').read()
    voice_bin = None
    if args.voice_table and os.path.exists(args.voice_table):
        voice_bin = open(args.voice_table, 'rb').read()
    music_bin = None
    if args.music and os.path.exists(args.music):
        music_bin = open(args.music, 'rb').read()
    m_data = build_mrom(table_bin, music_bin, voice_bin)
    m_path = os.path.join(rom_dir, f'{ngh}-m1.m1')
    with open(m_path, 'wb') as f:
        f.write(m_data)

    # --- V ROM (merged: SFX + music samples overlay) ---
    # Start with the overlay (music ADPCM samples at original addresses) if present
    overlay = None
    if getattr(args, 'v1_overlay', None) and os.path.exists(args.v1_overlay):
        overlay = open(args.v1_overlay, 'rb').read()

    if overlay:
        v_rom = bytearray(overlay)
    else:
        v_rom = bytearray([0x80] * args.v_size)

    # Copy SFX data on top (SFX is at address 0, small, won't overlap music)
    if args.v1 and os.path.exists(args.v1):
        sfx = open(args.v1, 'rb').read()
        # Only copy actual SFX data (non-silence prefix)
        sfx_end = len(sfx)
        while sfx_end > 0 and sfx[sfx_end - 1] == 0x80:
            sfx_end -= 1
        sfx_end = (sfx_end + 255) & ~255  # round up to 256
        if sfx_end > 0:
            if len(v_rom) < sfx_end:
                v_rom.extend(b'\x80' * (sfx_end - len(v_rom)))
            v_rom[:sfx_end] = sfx[:sfx_end]

    v_data = bytes(v_rom)
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

    # --- Summary ---
    print(f"  P ROM: {len(p_data):,} bytes")
    print(f"  C ROM: {len(c1_data):,} + {len(c2_data):,} bytes")
    print(f"  S ROM: {len(s_data):,} bytes")
    print(f"  M ROM: {len(m_data):,} bytes")
    print(f"  V ROM: {len(v_data):,} bytes")
    print(f"  Softlist: {xml_path}")


if __name__ == '__main__':
    main()
