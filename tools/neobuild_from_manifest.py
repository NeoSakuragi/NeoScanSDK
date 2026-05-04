#!/usr/bin/env python3
import argparse, os, subprocess, sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest')
    parser.add_argument('--elf', required=True)
    parser.add_argument('--name', default='neoscan')
    parser.add_argument('-o', '--output', required=True)
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
           '--elf', args.elf, '--name', args.name, '-o', args.output]
    for k, flag in [('c1','--c1'),('c2','--c2'),('s1','--s1'),
                     ('sfx_vrom','--v1'),('sfx_table','--sound-table'),
                     ('voice_table','--voice-table'),('music_samples','--v1-overlay'),
                     ('seq_blob','--seq-blob'),('fm_freq_table','--fm-freq-table'),
                     ('donor_m1','--donor-m1'),('donor_v1','--donor-v1')]:
        if k in manifest:
            cmd.extend([flag, manifest[k]])
    for i in range(16):
        k = f'music_stream_{i}'
        if k in manifest:
            cmd.extend(['--music', manifest[k]])
    sys.exit(subprocess.call(cmd))

if __name__ == '__main__':
    main()
