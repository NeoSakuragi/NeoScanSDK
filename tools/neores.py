#!/usr/bin/env python3
"""NeoScan resource compiler.

Reads a .res manifest and invokes the appropriate encoders to produce
all ROM data and a unified C header.

Resource types:
  PALETTE  name  "file.png|.aseprite"
  TILES    name  "file.png"
  ANIM     name  "file.aseprite"  [anim_name]
  SFX      name  "file.wav"
  VOICE    name  "file.wav"
  MUSIC    name  "file.vgm|.vgz"

Example .res file:
  PALETTE   pal_terry   "sprites/terry.aseprite"
  ANIM      anim_idle   "sprites/terry.aseprite"
  TILES     tiles_test  "gfx/sprites.png"
  SFX       sfx_hit     "sounds/hit.wav"
  SFX       sfx_beep    "sounds/beep.wav"
  MUSIC     mus_theme   "music/theme.vgz"
"""
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys


CACHE_FILE = '.neores_cache.json'


def file_hash(path):
    """SHA256 of file contents."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def load_cache(out_dir):
    path = os.path.join(out_dir, CACHE_FILE)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_cache(out_dir, cache):
    path = os.path.join(out_dir, CACHE_FILE)
    with open(path, 'w') as f:
        json.dump(cache, f, indent=2)


def needs_rebuild(cache, key, input_files):
    """Check if a resource needs rebuilding based on input file hashes."""
    if key not in cache:
        return True
    cached = cache[key]
    for path in input_files:
        if not os.path.exists(path):
            return True
        h = file_hash(path)
        if cached.get(path) != h:
            return True
    return False


def mark_built(cache, key, input_files):
    """Record current file hashes in cache."""
    cache[key] = {path: file_hash(path) for path in input_files}


def parse_res(path):
    """Parse a .res file into a list of (type, name, file, args) tuples."""
    entries = []
    base_dir = os.path.dirname(os.path.abspath(path))

    with open(path) as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue

            parts = shlex.split(line)
            if len(parts) < 3:
                print(f"WARNING: {path}:{line_no}: skipping malformed line")
                continue

            rtype = parts[0].upper()
            name = parts[1]
            filepath = os.path.join(base_dir, parts[2])
            args = parts[3:]
            entries.append((rtype, name, filepath, args))

    return entries


def run(cmd, desc=None):
    """Run a command, print output, raise on failure."""
    if desc:
        print(f"  {desc}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            print(f"    {line}")
    if result.returncode != 0:
        print(f"  ERROR: {' '.join(cmd)}")
        if result.stderr:
            print(result.stderr)
        sys.exit(1)
    return result


def main():
    parser = argparse.ArgumentParser(description='NeoScan resource compiler')
    parser.add_argument('res', help='Input .res file')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory')
    parser.add_argument('--tools-dir', default=None,
                        help='Tools directory (default: same as this script)')
    parser.add_argument('--force', action='store_true',
                        help='Force rebuild all resources (ignore cache)')
    parser.add_argument('--only', default=None,
                        help='Only rebuild specific types (comma-separated: tiles,anim,sfx,voice,music)')
    args = parser.parse_args()

    tools = args.tools_dir or os.path.dirname(os.path.abspath(__file__))
    out = args.output_dir
    os.makedirs(out, exist_ok=True)

    cache = {} if args.force else load_cache(out)
    only_types = set(args.only.upper().split(',')) if args.only else None

    entries = parse_res(args.res)
    if not entries:
        print("No resources found")
        return

    # Group by type
    palettes = [(n, f, a) for t, n, f, a in entries if t == 'PALETTE']
    tiles = [(n, f, a) for t, n, f, a in entries if t == 'TILES']
    anims = [(n, f, a) for t, n, f, a in entries if t == 'ANIM']
    sfx = [(n, f, a) for t, n, f, a in entries if t == 'SFX']
    voices = [(n, f, a) for t, n, f, a in entries if t == 'VOICE']
    music = [(n, f, a) for t, n, f, a in entries if t == 'MUSIC']

    header_lines = [
        '#ifndef RESOURCES_H',
        '#define RESOURCES_H',
        '',
        '#include <neoscan.h>',
        '',
    ]

    tile_base = 0
    tile_c1_parts = []
    tile_c2_parts = []
    palette_index = 1

    # --- TILES ---
    for name, filepath, extra_args in tiles:
        cache_key = f'tiles_{name}'
        tile_dir = os.path.join(out, f'_tiles_{name}')
        skip = (only_types and 'TILES' not in only_types) or \
               not needs_rebuild(cache, cache_key, [filepath])

        if skip and os.path.exists(os.path.join(tile_dir, 'tiles.h')):
            print(f"[TILES] {name} (cached)")
        else:
            print(f"[TILES] {name} <- {os.path.basename(filepath)}")
            os.makedirs(tile_dir, exist_ok=True)

            run(['python3', os.path.join(tools, 'tile_encoder.py'),
                 filepath, '-o', tile_dir],
                f"Encoding tiles...")

            run(['python3', os.path.join(tools, 'palette_encoder.py'),
                 filepath, '-o', os.path.join(tile_dir, 'palette.h')],
                f"Extracting palette...")

            mark_built(cache, cache_key, [filepath])

        # Read tile count from generated header
        tiles_h = os.path.join(tile_dir, 'tiles.h')
        tile_count = 0
        with open(tiles_h) as f:
            for line in f:
                if 'TILE_COUNT' in line:
                    tile_count = int(line.split()[-1])
                elif line.startswith('#define TILE_'):
                    parts = line.split()
                    header_lines.append(
                        f'#define {name.upper()}_{parts[1].split("_", 1)[1]} '
                        f'{int(parts[2]) + tile_base}')

        # Read palette
        pal_h = os.path.join(tile_dir, 'palette.h')
        with open(pal_h) as f:
            content = f.read()
            # Extract the palette array
            import re
            m = re.search(r'(static const uint16_t PALETTE\[\d+\] = \{[^}]+\})', content)
            if m:
                pal_def = m.group(1).replace('PALETTE', f'{name.upper()}_PALETTE')
                header_lines.append(pal_def + ';')

        header_lines.append(f'#define {name.upper()}_TILE_BASE {tile_base}')
        header_lines.append(f'#define {name.upper()}_TILE_COUNT {tile_count}')
        header_lines.append('')

        tile_c1_parts.append(os.path.join(tile_dir, 'tiles_c1.bin'))
        tile_c2_parts.append(os.path.join(tile_dir, 'tiles_c2.bin'))
        tile_base += tile_count

    # --- ANIM ---
    for name, filepath, extra_args in anims:
        cache_key = f'anim_{name}'
        anim_dir = os.path.join(out, f'_anim_{name}')
        skip = (only_types and 'ANIM' not in only_types) or \
               not needs_rebuild(cache, cache_key, [filepath])

        if skip and os.path.exists(os.path.join(anim_dir, 'anim_c1.bin')):
            print(f"[ANIM] {name} (cached)")
        else:
            print(f"[ANIM] {name} <- {os.path.basename(filepath)}")
            os.makedirs(anim_dir, exist_ok=True)

            cmd = ['python3', os.path.join(tools, 'anim_encoder.py'),
                   filepath, '-o', anim_dir,
                   '--tile-base', str(tile_base)]
            if extra_args:
                cmd.extend(extra_args)

            run(cmd, f"Encoding animation...")
            mark_built(cache, cache_key, [filepath])

        # Read generated headers
        anim_h = os.path.join(anim_dir, 'anim_idle.h')
        for f in os.listdir(anim_dir):
            if f.startswith('anim_') and f.endswith('.h'):
                rel = os.path.relpath(os.path.join(anim_dir, f), out)
                header_lines.append(f'#include "{rel}"')
            elif f == 'anim_palette.h':
                rel = os.path.relpath(os.path.join(anim_dir, f), out)
                header_lines.append(f'#include "{rel}"')

        # Count tiles
        for f in os.listdir(anim_dir):
            if f.endswith('.h') and 'anim_' in f and 'palette' not in f:
                with open(os.path.join(anim_dir, f)) as fh:
                    for line in fh:
                        if 'tile_count' in line and '=' in line:
                            # Parse .tile_count = N from the struct
                            import re
                            m = re.search(r'\.tile_count\s*=\s*(\d+)', line)
                            if m:
                                tile_count = int(m.group(1))

        c1 = os.path.join(anim_dir, 'anim_c1.bin')
        c2 = os.path.join(anim_dir, 'anim_c2.bin')
        if os.path.exists(c1):
            tile_c1_parts.append(c1)
            tile_c2_parts.append(c2)
            anim_tiles = os.path.getsize(c1) // 64
            tile_base += anim_tiles

        header_lines.append('')

    # --- PALETTE (standalone) ---
    for name, filepath, extra_args in palettes:
        if any(n == name for n, _, _ in tiles):
            continue  # Already handled by TILES
        print(f"[PALETTE] {name} <- {os.path.basename(filepath)}")
        pal_out = os.path.join(out, f'{name}.h')
        run(['python3', os.path.join(tools, 'palette_encoder.py'),
             filepath, '-o', pal_out])
        rel = os.path.relpath(pal_out, out)
        header_lines.append(f'#include "{rel}"')
        header_lines.append('')

    # --- SFX ---
    sfx_wavs = [f for _, f, _ in sfx]
    if sfx_wavs:
        cache_key = 'sfx'
        sfx_dir = os.path.join(out, '_sfx')
        skip = (only_types and 'SFX' not in only_types) or \
               not needs_rebuild(cache, cache_key, sfx_wavs)

        if skip and os.path.exists(os.path.join(sfx_dir, 'sounds.h')):
            print(f"[SFX] {len(sfx_wavs)} files (cached)")
        else:
            print(f"[SFX] {len(sfx_wavs)} files")
            os.makedirs(sfx_dir, exist_ok=True)
            run(['python3', os.path.join(tools, 'wav_encoder.py')]
                + sfx_wavs + ['-o', sfx_dir],
                "Encoding ADPCM-A...")
            mark_built(cache, cache_key, sfx_wavs)

        # Map generated SND_xxx defines to resource names
        with open(os.path.join(sfx_dir, 'sounds.h')) as f:
            for line in f:
                if line.startswith('#define SND_'):
                    header_lines.append(line.rstrip())
                elif line.startswith('#define') and 'COUNT' in line:
                    header_lines.append(line.rstrip())
        header_lines.append('')

    # --- VOICE ---
    voice_wavs = [f for _, f, _ in voices]
    if voice_wavs:
        cache_key = 'voice'
        voice_dir = os.path.join(out, '_voice')
        skip = (only_types and 'VOICE' not in only_types) or \
               not needs_rebuild(cache, cache_key, voice_wavs)

        if skip and os.path.exists(os.path.join(voice_dir, 'voices.h')):
            print(f"[VOICE] {len(voice_wavs)} files (cached)")
        else:
            print(f"[VOICE] {len(voice_wavs)} files")
            os.makedirs(voice_dir, exist_ok=True)
            run(['python3', os.path.join(tools, 'wav_encoder.py'),
                 '--mode', 'b'] + voice_wavs + ['-o', voice_dir],
                "Encoding ADPCM-B...")
            mark_built(cache, cache_key, voice_wavs)

        with open(os.path.join(voice_dir, 'voices.h')) as f:
            for line in f:
                if line.startswith('#define VOX_'):
                    header_lines.append(line.rstrip())
                elif line.startswith('#define') and 'COUNT' in line:
                    header_lines.append(line.rstrip())
        header_lines.append('')

    # --- MUSIC ---
    music_entries = []
    for name, filepath, extra_args in music:
        cache_key = f'music_{name}'
        music_dir = os.path.join(out, f'_music_{name}')
        skip = (only_types and 'MUSIC' not in only_types) or \
               not needs_rebuild(cache, cache_key, [filepath])

        if skip and os.path.exists(os.path.join(music_dir, 'stream.bin')):
            print(f"[MUSIC] {name} (cached)")
        else:
            print(f"[MUSIC] {name} <- {os.path.basename(filepath)}")
            os.makedirs(music_dir, exist_ok=True)

            cmd = ['python3', os.path.join(tools, 'vgm_converter.py'),
                   filepath, '-o', os.path.join(music_dir, 'stream.bin'),
                   '--samples-out', os.path.join(music_dir, 'samples.bin')]
            run(cmd, "Converting VGM...")
            mark_built(cache, cache_key, [filepath])

        music_entries.append((name, music_dir))
        header_lines.append(f'/* Music: {name} */')
        header_lines.append('')

    # --- Combine C ROMs ---
    if tile_c1_parts:
        c1_combined = os.path.join(out, 'combined_c1.bin')
        c2_combined = os.path.join(out, 'combined_c2.bin')
        with open(c1_combined, 'wb') as f:
            for part in tile_c1_parts:
                f.write(open(part, 'rb').read())
        with open(c2_combined, 'wb') as f:
            for part in tile_c2_parts:
                f.write(open(part, 'rb').read())

    # --- Font ---
    font_path = os.path.join(out, 'font.s1')
    run(['python3', os.path.join(tools, 'font_encoder.py'),
         '-o', font_path], "Generating font...")

    # --- Write combined header ---
    header_lines.extend(['', '#endif'])
    header_path = os.path.join(out, 'resources.h')
    with open(header_path, 'w') as f:
        f.write('\n'.join(header_lines) + '\n')
    print(f"Header: {header_path}")

    # --- Write manifest for neobuild ---
    manifest = {
        'c1': os.path.join(out, 'combined_c1.bin') if tile_c1_parts else None,
        'c2': os.path.join(out, 'combined_c2.bin') if tile_c2_parts else None,
        's1': font_path,
        'sfx_vrom': os.path.join(out, '_sfx', 'vrom.bin') if sfx_wavs else None,
        'sfx_table': os.path.join(out, '_sfx', 'sound_table.bin') if sfx_wavs else None,
        'voice_vrom': os.path.join(out, '_voice', 'vrom_b.bin') if voice_wavs else None,
        'voice_table': os.path.join(out, '_voice', 'voice_table.bin') if voice_wavs else None,
    }

    if music_entries:
        name, mdir = music_entries[0]
        manifest['music_stream'] = os.path.join(mdir, 'stream.bin')
        manifest['music_samples'] = os.path.join(mdir, 'samples.bin')

    manifest_path = os.path.join(out, 'manifest.txt')
    with open(manifest_path, 'w') as f:
        for key, val in manifest.items():
            if val and os.path.exists(val):
                f.write(f'{key}={val}\n')
    print(f"Manifest: {manifest_path}")

    save_cache(out, cache)
    print(f"Total sprite tiles: {tile_base}")


if __name__ == '__main__':
    main()
