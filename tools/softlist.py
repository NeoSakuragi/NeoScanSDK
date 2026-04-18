#!/usr/bin/env python3
"""Generate MAME softlist XML for a Neo Geo homebrew ROM."""
import sys
import os
import zlib
import hashlib
import argparse


def file_checksums(path):
    """Compute CRC32 and SHA1 for a file."""
    data = open(path, 'rb').read()
    crc = zlib.crc32(data) & 0xFFFFFFFF
    sha1 = hashlib.sha1(data).hexdigest()
    return len(data), crc, sha1


def build_softlist_xml(name, description, rom_files):
    """Build MAME softlist XML string.

    rom_files: dict with keys 'p1', 's1', 'm1', 'v1', 'c1', 'c2' → file paths.
    """
    ngh = '999'

    roms = {}
    for key, path in rom_files.items():
        size, crc, sha1 = file_checksums(path)
        roms[key] = {
            'name': f'{ngh}-{key}.{key}',
            'size': size,
            'crc': f'{crc:08x}',
            'sha1': sha1,
        }

    xml = '<?xml version="1.0"?>\n'
    xml += '<!DOCTYPE softwarelist SYSTEM "softwarelist.dtd">\n'
    xml += '<softwarelist name="neogeo" description="Neo Geo cartridges">\n'
    xml += f'\t<software name="{name}">\n'
    xml += f'\t\t<description>{description}</description>\n'
    xml += '\t\t<year>2026</year>\n'
    xml += '\t\t<publisher>NeoScan</publisher>\n'
    xml += '\t\t<part name="cart" interface="neo_cart">\n'

    r = roms['p1']
    xml += f'\t\t\t<dataarea name="maincpu" width="16" endianness="big" size="0x{r["size"]:06x}">\n'
    xml += f'\t\t\t\t<rom name="{r["name"]}" size="{r["size"]}" crc="{r["crc"]}" sha1="{r["sha1"]}" offset="0x000000" loadflag="load16_word_swap"/>\n'
    xml += '\t\t\t</dataarea>\n'

    r = roms['s1']
    xml += f'\t\t\t<dataarea name="fixed" size="0x{r["size"]:06x}">\n'
    xml += f'\t\t\t\t<rom name="{r["name"]}" size="{r["size"]}" crc="{r["crc"]}" sha1="{r["sha1"]}"/>\n'
    xml += '\t\t\t</dataarea>\n'

    r = roms['m1']
    xml += f'\t\t\t<dataarea name="audiocpu" size="0x{r["size"]:06x}">\n'
    xml += f'\t\t\t\t<rom name="{r["name"]}" size="0x{r["size"]:06x}" crc="{r["crc"]}" sha1="{r["sha1"]}" offset="0x000000"/>\n'
    xml += '\t\t\t</dataarea>\n'

    r = roms['v1']
    xml += f'\t\t\t<dataarea name="ymsnd:adpcma" size="0x{r["size"]:06x}">\n'
    xml += f'\t\t\t\t<rom name="{r["name"]}" size="0x{r["size"]:06x}" crc="{r["crc"]}" sha1="{r["sha1"]}" offset="0x000000"/>\n'
    xml += '\t\t\t</dataarea>\n'

    if 'v2' in roms:
        r = roms['v2']
        xml += f'\t\t\t<dataarea name="ymsnd:adpcmb" size="0x{r["size"]:06x}">\n'
        xml += f'\t\t\t\t<rom name="{r["name"]}" size="0x{r["size"]:06x}" crc="{r["crc"]}" sha1="{r["sha1"]}" offset="0x000000"/>\n'
        xml += '\t\t\t</dataarea>\n'

    c1 = roms['c1']
    c2 = roms['c2']
    sprite_size = c1['size'] + c2['size']
    xml += f'\t\t\t<dataarea name="sprites" size="0x{sprite_size:06x}">\n'
    xml += f'\t\t\t\t<rom name="{c1["name"]}" size="{c1["size"]}" crc="{c1["crc"]}" sha1="{c1["sha1"]}" offset="0x000000" loadflag="load16_byte"/>\n'
    xml += f'\t\t\t\t<rom name="{c2["name"]}" size="{c2["size"]}" crc="{c2["crc"]}" sha1="{c2["sha1"]}" offset="0x000001" loadflag="load16_byte"/>\n'
    xml += '\t\t\t</dataarea>\n'

    xml += '\t\t</part>\n'
    xml += '\t</software>\n'
    xml += '</softwarelist>\n'
    return xml


def main():
    parser = argparse.ArgumentParser(description='Generate MAME softlist XML')
    parser.add_argument('--name', required=True, help='ROM set name')
    parser.add_argument('--description', default='NeoScan Homebrew')
    parser.add_argument('--p1', required=True)
    parser.add_argument('--s1', required=True)
    parser.add_argument('--m1', required=True)
    parser.add_argument('--v1', required=True)
    parser.add_argument('--c1', required=True)
    parser.add_argument('--c2', required=True)
    parser.add_argument('-o', '--output', required=True, help='Output XML file')
    args = parser.parse_args()

    rom_files = {
        'p1': args.p1, 's1': args.s1, 'm1': args.m1,
        'v1': args.v1, 'c1': args.c1, 'c2': args.c2,
    }
    xml = build_softlist_xml(args.name, args.description, rom_files)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        f.write(xml)
    print(f"Softlist XML: {args.output}")


if __name__ == '__main__':
    main()
