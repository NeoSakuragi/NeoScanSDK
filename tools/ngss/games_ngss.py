#!/usr/bin/env python3
"""The games running Technos' "SDC_NGSS" sound driver ("PROGRAMMED BY R. ASHWORTH YOROSHIKU NE!!"): Double Dragon
(1995) and Super Dodge Ball (1996), one description per build (docs/doubledr_sound_driver.md). song_ngss.py,
regs_ngss.py and capture_ngss.py read everything game-specific from here; game_of() tells the build from the M1 ROM
(the ID at $003C: "SDC_NGSS" + version bytes: Double Dragon 01 00, Super Dodge Ball 01 01).

Addresses are Z80 addresses in the M1 ROM. Both builds keep the same layout: sound table $3C00 (3 bytes per command:
offset hi, offset lo, bank), FM patches $2000 (26 bytes), ADPCM-A sample tables $2D00 (6 x 128 x 4 bytes), ADPCM-B
instruments $3900 (6 bytes); the code differs in places (version.md: "Super Dodge Ball's build")."""

GAMES = {
    'doubledr': dict(
        name='Double Dragon', rom='/data/roms/doubledr.neo', dir='/data/neogeo_dict/sound/doubledr',
        m1='doubledr_m1.bin', ident=b'SDC_NGSS\x01\x00',
        table=0x3C00, patches=0x2000, patches_ff=0x1BEE, a_tabs=0x2D00, b_inst=0x3900,
        fnum=0x1872, b_dn=0x18A2, ssg=0x19CE, carriers=0x1B4E, vol=0x1B56, bits=0x1BD6, voltab=0x1BDE,
        pan_tab=0x0E34, v11=False,
        music=range(0xDC, 0xF0),
        block=845, send=900,  # the game's reset ($03) at frame 838, its first sound ($E2) at 1173 (measured)
    ),
    'sdodgeb': dict(
        name='Super Dodge Ball', rom='/data/roms/sdodgeb.neo', dir='/data/neogeo_dict/sound/sdodgeb',
        m1='sdodgeb_m1.bin', ident=b'SDC_NGSS\x01\x01',
        table=0x3C00, patches=0x2000, patches_ff=0x1C3C, a_tabs=0x2D00, b_inst=0x3900,
        fnum=0x18C0, b_dn=0x18F0, ssg=0x1A1C, carriers=0x1B9C, vol=0x1BA4, bits=0x1C24, voltab=0x1C2C,
        pan_tab=0x0DB8, v11=True,     # version 1.1: docs/doubledr_sound_driver.md "Super Dodge Ball's build"
        music=range(0x82, 0x91),      # the 15 entries with their own channels (class 5, priority 4, mask $38FF)
        block=845, send=900,  # the game's reset ($03) at frame 840, its first sounds (F8 70, $90) at 1031 (measured)
    ),
}

def game_of(data):
    for k, g in GAMES.items():
        if data[0x3C:0x46] == g['ident']: return k
    raise ValueError('not a known SDC_NGSS build: %r' % data[0x3C:0x46])

def m1_path(game):
    g = GAMES[game]; return g['dir'] + '/' + g['m1']

def entry(data, cmd):
    """the sound table entry of cmd (Super Dodge Ball: page << 8 | cmd, pages 0-2) -> None or dict(bank, addr (Z80),
    phys, kill (lo, hi), cls, prio, mask, streams [(block index, Z80 address)])"""
    g = GAMES[game_of(data)]
    t = (g['table'] + 3 * cmd) & 0xFFFF
    e = data[t:t + 3]
    off = e[0] << 8 | e[1]
    if off >= 0x8000: return None
    bank = e[2]; phys = (bank + 2) * 0x4000 + off
    h = data[phys:phys + 6]
    mask = h[4] << 8 | h[5]
    blocks = [i for i in range(14) if mask >> i & 1] if mask != 0x100 else [8]
    streams = []
    for k, b in enumerate(blocks):
        w = phys + 6 + 2 * k
        streams.append((b, 0x8000 + off + 6 + 2 * k + (data[w] << 8 | data[w + 1])))
    return dict(bank=bank, addr=0x8000 + off, phys=phys, kill=(h[0], h[1]), cls=h[2], prio=h[3], mask=mask,
                streams=streams)

def music_cmds(data):
    """the music commands: class 0 (the start resets the fade, $1554), their own data (not the $00-$03 / $EE-$EF
    duplicates of bank 0 offset 0 unless listed by the build)"""
    g = GAMES[game_of(data)]
    if g['music'] is not None: return list(g['music'])
    out = []
    for c in [p << 8 | c for p in range(3 if g['v11'] else 1) for c in range(0xF0)]:
        e = entry(data, c)
        if e and e['cls'] == 0 and e['mask'] != 0x100 and e['prio']: out.append(c)
    return out
