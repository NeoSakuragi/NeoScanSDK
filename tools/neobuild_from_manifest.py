#!/usr/bin/env python3
"""Build a NeoScan ROM from a neores manifest file.

Reads the manifest.txt produced by neores and invokes neobuild with
the correct arguments and ordering.
"""
import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description='Build ROM from manifest')
    parser.add_argument('manifest', help='Manifest file from neores')
    parser.add_argument('--elf', required=True, help='Linked ELF file')
    parser.add_argument('--name', default='neoscan', help='ROM set name')
    parser.add_argument('-o', '--output', required=True, help='Output ZIP')
    args = parser.parse_args()

    manifest = {}
    with open(args.manifest) as f:
        for line in f:
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                manifest[k] = v

    tools = os.path.dirname(os.path.abspath(__file__))

    cmd = ['python3', os.path.join(tools, 'neobuild.py'),
           '--elf', args.elf,
           '--name', args.name,
           '-o', args.output]

    if 'c1' in manifest:
        cmd.extend(['--c1', manifest['c1']])
    if 'c2' in manifest:
        cmd.extend(['--c2', manifest['c2']])
    if 's1' in manifest:
        cmd.extend(['--s1', manifest['s1']])
    if 'sfx_vrom' in manifest:
        cmd.extend(['--v1', manifest['sfx_vrom']])
    if 'sfx_table' in manifest:
        cmd.extend(['--sound-table', manifest['sfx_table']])
    if 'voice_table' in manifest:
        cmd.extend(['--voice-table', manifest['voice_table']])
    if 'music_samples' in manifest:
        cmd.extend(['--v1-overlay', manifest['music_samples']])

    if 'music_stream_0' in manifest:
        cmd.extend(['--music', manifest['music_stream_0']])

    sys.exit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
