#!/usr/bin/env python3
"""TODO #182 proof: the brawler's fix-layer text in Kizuna Encounter's outlined font.

    python3 font182_proof.py [OUT]            (default /data/tmp/font182/out; examples/brawler built)
    python3 font182_proof.py --before ROM     a ROM to compare with (default: OUT/before.neo, a build of the old font)

1. shots: the same path on both ROMs (harness, our emulator's core): the title, the select screen, stage 1 (the
   brightest) and stage 5 (the darkest) in play with the HUD (the options screen is AES only: not on this MVS path), the CONTINUE? overlay (P1's last life
   gone), GAME OVER; before / after side by side, x2 -> OUT/before_after.png (+ each shot in OUT/shots/).
2. glyphs: Kizuna's tiles $D00 + ASCII in its own fix palette 11 (palette RAM read in our emulator on its title,
   /data/tmp/font182/work/kz/run.txt.pal700, kept as KZ_PAL) next to the brawler's S ROM tiles at the same ASCII codes
   in fix palette 0 / 1 as main.c loads them; every character the game's strings use, marked derived where Kizuna has
   no glyph -> OUT/glyphs.png; the S ROM tiles checked equal to Kizuna's (pens mapped) for $20-$5F.
3. strings: every character of every string the game draws (main.c FIX_print / centre / ov_put literals, fighter
   names, song / effect names, drama lines) -> OUT/strings.txt, each one's glyph source."""
import os, re, sys, json, struct, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
sys.path.insert(0, HERE)
from make_hud import sdecode, KIZUNA, KZ_FONT, KZ_PEN, TEXT_COLOURS, HILITE_RGB, EMPTY, BAR_PAL
from make_stage import neo_colour
from PIL import Image, ImageDraw

KZ_PAL = [0x0000, 0x7FFF, 0x79AB, 0x0357, 0x7FF8, 0x6FD0, 0x6F90, 0x6F60, 0x1014, 0x4FB0, 0x3014, 0x4F00, 0x0E00,
          0x4C00, 0x0B00, 0x0000]                     # Kizuna's fix palette 11 (its font), read on its title screen

def rgb(c):
    d = (c >> 15) & 1
    r = ((c >> 8) & 15) << 2 | ((c >> 14) & 1) << 1 | d
    g = ((c >> 4) & 15) << 2 | ((c >> 13) & 1) << 1 | d
    b = (c & 15) << 2 | ((c >> 12) & 1) << 1 | d
    return tuple(v * 255 // 63 for v in (r, g, b))

def shots(rom, out):
    """the path on one ROM (run in its own process: one core per process)"""
    from harness import Brawler
    b = Brawler(rom=rom); os.makedirs(out, exist_ok=True)
    S = lambda n: b.screenshot(os.path.join(out, n + '.png'))
    st = {n: i for i, n in enumerate(b.states)}
    b.core.retro_reset(); b.seq('600:-,4:o,120:-'); S('1_title')
    b.seq('4:s,90:-'); S('2_select')
    sel = b.save()
    b.seq('4:a,420:-'); S('3_stage1')
    b.load(sel); b.w(b.syms['camp_from'], 1, 4)           # the title's CONTINUE at stage 5: the darkest
    b.seq('4:a,420:-'); S('4_stage5')
    b.w(b.syms['lives'], 1, 0)                            # P1's last life gone: CONTINUE?
    b.fset(0, 'state', st['DEAD']); b.fset(0, 'state_t', 250)
    b.seq('90:-'); S('6_continue')
    for _ in range(12): b.seq('4:a,20:-')                 # A: the next number, down to 0
    b.seq('120:-'); S('7_gameover')

def glyph_img(tile, pal, scale=4):
    px = sdecode(tile); im = Image.new('RGB', (8, 8))
    for y in range(8):
        for x in range(8): im.putpixel((x, y), (40, 60, 150) if px[y][x] == 0 else rgb(pal[px[y][x]]))
    return im.resize((8 * scale, 8 * scale), Image.NEAREST)

def strings():
    """every string the game draws -> {char: [where]}"""
    out = {}
    def add(s, where):
        for ch in s: out.setdefault(ch, set()).add(where)
    src = re.sub(r'/\*.*?\*/', '', open(os.path.join(GAME, 'main.c')).read(), flags=re.S)
    for m in re.finditer(r'(FIX_print|centre|ov_put)\s*\(([^;]*?)"((?:[^"\\]|\\.)*)"', src): add(m.group(3), 'main.c')
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', src[src.index('TXT['):src.index('TXT[') + 400] if 'TXT[' in src else ''):
        add(m.group(1), 'main.c menus')
    for l in re.findall(r'"([^"]*)"', re.sub(r'/\*.*?\*/', '', open(os.path.join(GAME, 'build', 'snd', 'songs.h')).read(), flags=re.S)):
        add(l, 'songs.h')
    tables = re.sub(r'/\*.*?\*/', '', open(os.path.join(GAME, 'build', 'game_tables.c')).read(), flags=re.S)
    for l in re.findall(r'"((?:[^"\\]|\\.)*)"', tables):
        if 'build_tables.py' in l or l.endswith('.h'): continue
        add(l.replace('$P1', ''), 'game_tables (drama, enemies)')
    chars = re.sub(r'/\*.*?\*/', '', open(os.path.join(GAME, 'build', 'bm_chars.c')).read(), flags=re.S)
    for l in re.findall(r'"((?:[^"\\]|\\.)*)"', chars):
        if not l.endswith('.h'): add(l, 'fighter names')
    return out

def main():
    a = sys.argv[1:]
    if a and a[0] == '--shots': shots(a[1], a[2]); return
    out = a[0] if a and not a[0].startswith('--') else '/data/tmp/font182/out'
    before = a[a.index('--before') + 1] if '--before' in a else os.path.join(out, 'before.neo')
    os.makedirs(out, exist_ok=True); ok = True
    # 1. shots
    for tag, rom in (('before', before), ('after', os.path.join(GAME, 'brawler.neo'))):
        subprocess.run([sys.executable, __file__, '--shots', rom, os.path.join(out, 'shots', tag)], check=True)
    names = sorted(f[:-4] for f in os.listdir(os.path.join(out, 'shots', 'after')))
    W, H = Image.open(os.path.join(out, 'shots', 'after', names[0] + '.png')).size
    sheet = Image.new('RGB', (2 * W * 2 + 30, len(names) * (H * 2 + 24) + 24), 'white'); d = ImageDraw.Draw(sheet)
    d.text((10, 6), 'before (system font)', fill='black'); d.text((W * 2 + 30, 6), 'after (Kizuna font)', fill='black')
    for i, n in enumerate(names):
        y = 24 + i * (H * 2 + 24); d.text((10, y), n, fill='black')
        for k, tag in enumerate(('before', 'after')):
            im = Image.open(os.path.join(out, 'shots', tag, n + '.png')).resize((W * 2, H * 2), Image.NEAREST)
            sheet.paste(im, (10 + k * (W * 2 + 10), y + 14))
    sheet.save(os.path.join(out, 'before_after.png'))
    # 2. glyphs
    d = open(KIZUNA, 'rb').read(); p = struct.unpack_from('<I', d, 4)[0]; ksrom = d[0x1000 + p:0x1000 + p + 0x20000]
    bs = open(os.path.join(GAME, 'build', 'font.s1'), 'rb').read()
    pal0 = [0x8000, 0x7FFF] + TEXT_COLOURS + [neo_colour(*BAR_PAL[k]) for k in range(6, 16)]
    pal1 = pal0[:2] + [neo_colour(*c) for c in HILITE_RGB] + pal0[6:]
    for ch in range(0x20, 0x5F):                        # the S ROM = Kizuna's glyphs, pens mapped ('_' derived)
        k = [[KZ_PEN[v] for v in r] for r in sdecode(ksrom[(KZ_FONT + ch) * 32:(KZ_FONT + ch) * 32 + 32])]
        if sdecode(bs[ch * 32:ch * 32 + 32]) != k: ok = False; print('FAIL glyph', hex(ch))
    used = strings()
    codes = sorted(set(range(0x20, 0x60)) | {ord(c) for c in used} | {0x7F})
    cols = 8; cw = 4 * 32 + 40
    g = Image.new('RGB', (cols * cw + 20, ((len(codes) + cols - 1) // cols) * 64 + 60), 'white'); dg = ImageDraw.Draw(g)
    dg.text((10, 6), 'per cell: Kizuna $D00+code (its palette 11) | brawler S ROM code: palette 0 | palette 1 (highlight) '
            '| old system font', fill='black')
    dg.text((10, 20), 'D = derived (Kizuna has no glyph: lowercase = its capital; _ and $7F the select arrow drawn in its style); '
            '* = used by a game string', fill='black')
    old = open(os.path.join(out, 'old_font.s1'), 'rb').read() if os.path.exists(os.path.join(out, 'old_font.s1')) else None
    lines = []
    for i, c in enumerate(codes):
        x = 10 + (i % cols) * cw; y = 40 + (i // cols) * 64
        derived = c >= 0x5F
        lab = f'{c:02X} {chr(c) if 0x20 < c < 0x7F else ""}' + (' D' if derived else '') + (' *' if chr(c) in used else '')
        dg.text((x, y), lab, fill='black')
        if not derived: g.paste(glyph_img(ksrom[(KZ_FONT + c) * 32:(KZ_FONT + c) * 32 + 32], KZ_PAL), (x, y + 12))
        g.paste(glyph_img(bs[c * 32:c * 32 + 32], pal0), (x + 33, y + 12))
        g.paste(glyph_img(bs[c * 32:c * 32 + 32], pal1), (x + 66, y + 12))
        if old: g.paste(glyph_img(old[c * 32:c * 32 + 32], [0x8000, 0x7FFF] + [0] * 14), (x + 99, y + 12))
    g.save(os.path.join(out, 'glyphs.png'))
    for ch in sorted(used):
        c = ord(ch); src = 'Kizuna $%03X' % (KZ_FONT + c) if c < 0x5F else 'derived: capital %s' % ch.upper() if ch.isalpha() else 'derived: drawn' if ch == '_' else 'MISSING'
        if src == 'MISSING': ok = False
        lines.append(f'{ch!r:6} {src:22} {", ".join(sorted(used[ch]))}')
    open(os.path.join(out, 'strings.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('PASS' if ok else 'FAIL', f'{len(used)} characters used; sheets in {out}')

if __name__ == '__main__':
    main()
