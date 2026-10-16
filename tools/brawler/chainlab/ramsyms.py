#!/usr/bin/env python3
"""A brawler build's RAM map for the Lab's Sessions page (sessinfo.js: the character, the screen, the stage, the wave,
each player's life and drive read from a session's state): the symbol addresses (build/rom.elf), the fighter_t offsets
(harness._layout), the fighters' HUD names and the stages' names (read from the built ROM), the drive meter's chunk
size, keyed by the ROM's SHA-256 (= meta.json rom_sha256 of every session played on it).

    python3 ramsyms.py OUT_DIR [GAME_DIR [ROM]]   -> OUT_DIR/<sha256 of ROM (GAME_DIR/brawler.neo)>.json
    (GAME_DIR: examples/brawler, BUILT: brawler.neo + build/rom.elf + build/game_tables.h of the same make)

tools/brawler/publish_vps.sh runs it for every published build and sends the file to the Lab
(/data/brawler-lab/ramsyms/<sha>.json, behind the Oros login with the Lab). A build without one (published before
2026-10-16): the page reads what the HUD shows (the fix layer: the players' names) and leaves the rest "—"."""
import hashlib, json, os, re, struct, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness

FORMAT = 1
WANT = ['fighters', 'bm_chars', 'mode', 'attract', 'phase', 'wave', 'camp', 'bonus_on', 'drive_chunks', 'lives', 'cont_t',
        'difficulty', 'game_ticks', 'gstages', 'nf']
FIELDS = ['ch', 'hp', 'hp_max', 'drive', 'state', 'team', 'idx']


def offsetof(game, build, expr):
    """offsetof / sizeof expressions on the game's headers, from the compiler (as harness._layout)"""
    src = '#include <stddef.h>\n#include "fighter.h"\n#include "gamedata.h"\nvoid offs(void) {\n' + ''.join(
        f'asm volatile(".equ X{i}, %c0" :: "i"({e}));\n' for i, e in enumerate(expr)) + '}\n'
    with tempfile.NamedTemporaryFile('w', suffix='.c', delete=False) as t: t.write(src)
    try:
        asm = subprocess.run(['m68k-linux-gnu-gcc', '-m68000', '-O2', '-ffreestanding', '-nostdlib', '-I' + game,
                              '-I' + os.path.join(game, '..', '..', 'sdk', 'include'), '-I' + os.path.join(game, '..', '..', 'sdk', 'src'),
                              '-I' + os.path.join(game, build), '-S', '-o', '-', t.name], capture_output=True, text=True, check=True).stdout
    finally: os.unlink(t.name)
    eq = dict(re.findall(r'\.equ X(\d+), (-?\d+)', asm))
    return [int(eq[str(i)]) for i in range(len(expr))]


def make(game, build='build', rom=None):
    neo = open(rom or os.path.join(game, 'brawler.neo'), 'rb').read()
    psize = struct.unpack_from('<I', neo, 4)[0]
    def rb(a):                                     # the P ROM's first MB (the .neo keeps it word-swapped)
        if not 0 <= a < min(psize, 0x100000): raise ValueError('address %x outside P1' % a)
        return neo[0x1000 + (a ^ 1)]
    r16 = lambda a: rb(a) << 8 | rb(a + 1)
    r32 = lambda a: r16(a) << 16 | r16(a + 2)
    def rstr(a, n=24):
        s = ''
        while len(s) < n and rb(a + len(s)): s += chr(rb(a + len(s)))
        return s
    layout, fsize, states, syms = harness._layout(game, build)
    name_off, gst_size, gst_nw = offsetof(game, build, ['offsetof(bchar_t, name)', 'sizeof(gstage_t)', 'offsetof(gstage_t, nwaves)'])
    tab = open(os.path.join(game, build, 'game_tables.h')).read()
    nchars = int(re.search(r'#define BC_COUNT (\d+)', tab).group(1)) if re.search(r'#define BC_COUNT (\d+)', tab) else None
    if nchars is None: nchars = len(json.load(open(os.path.join(game, build, 'roster.json'))))
    rom_chars = syms.get('bm_chars_rom', syms['bm_chars'])
    chars = [rstr(r32(rom_chars + i * syms['sizeof_bchar'] + name_off), 16) for i in range(nchars)]
    m = re.search(r'#define GS_COUNT (\d+)', tab); ns = int(m.group(1)) if m else 0
    stages = [rstr(r32(syms['gstage_names'] + 4 * i), 24) for i in range(ns)] if 'gstage_names' in syms else []
    gr = syms.get('gstages_rom')                  # the campaign's stages as built (gstages points here outside a data pack)
    nwaves = [rb(gr + i * gst_size + gst_nw) for i in range(ns)] if gr is not None else []
    return {'format': FORMAT, 'rom_sha256': hashlib.sha256(neo).hexdigest(),
            'version': open(os.path.join(game, 'VERSION')).read().strip(),
            'syms': {k: syms[k] for k in WANT if k in syms}, 'fsize': fsize,
            'fields': {f: layout[f] for f in FIELDS if f in layout}, 'states': states, 'sizeof_bchar': syms['sizeof_bchar'],
            'chars': chars, 'stages': [{'name': n, 'nwaves': nwaves[i] if i < len(nwaves) else None} for i, n in enumerate(stages)],
            'meter': {'chunk': r16(syms['gmeter']), 'chunks': rb(syms['gmeter'] + 2)} if 'gmeter' in syms else None}


if __name__ == '__main__':
    out = sys.argv[1]; game = sys.argv[2] if len(sys.argv) > 2 else harness.GAME
    d = make(game, rom=sys.argv[3] if len(sys.argv) > 3 else None)
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, d['rom_sha256'] + '.json')
    json.dump(d, open(p, 'w'), separators=(',', ':'))
    print(p, d['version'], len(d['chars']), 'fighters', len(d['stages']), 'stages')
