#!/usr/bin/env python3
"""The games running ADK's "Operation System Program for Music & Effective Sound" sound driver, one description per
build (docs/ninjamas_sound_driver.md): where each build keeps the tables songadk.py reads. The build is told from the
M1 ROM's ID string at $0070 ("... Ver. 8.8.9 (c) Copyright ADK Corporation December 4, 1995 by M.C (^_^)" in
Ninja Master's).

The driver keeps its table pointers in a word table at $2E00 (read through it at run time: `ptrs` names them); the
addresses here are those words' values for the build, checked against the ROM by check()."""

GAMES = {
    'ninjamas': dict(
        name="Ninja Master's", rom='/data/roms/ninjamas.neo', dir='/data/neogeo_dict/sound/ninjamas',
        m1='ninjamas_m1.bin', ident=b'Ver. 8.8.9',
        ptrs=0x2E00,
        headers=0x2E20,       # ($2E00) mode-0 song headers, 24 bytes each: 11 stream pointers + 2 unused
        cmd_tab=0x6A66,       # ($2E0C) command table, 4 bytes per command: [kind][flags][song][mode] (default, after $FE)
        cmd_tab2=0x6E66,      # ($2E12) the same for the command after $FC, or from $FD to $FE: the music commands
        patches=0x7266,       # ($2E0A) 40-byte FM patches
        a_smp=0x5651,         # ($2E14) ADPCM-A sample records, 6 bytes: start16 end16 + 2 unused
        a_smp2=0x5C4B,        # ($2E1A) the second set ('?' '?' n)
        b_smp=0x5DD1,         # ($2E06) ADPCM-B sample records, 8 bytes: start16 end16 delta-N16 pan level
        a_env=0x0000,         # ($2E10) ADPCM-A level envelope pointer table: 0 in this build (reads the code at $0000)
        fnum=0x1FF9,          # FM F-numbers, 4 per semitone, indexed by byte offset ($1246)
        note_base=0x12FA,     # FM note letter -> byte offset into fnum (A..G)
        b_note=0x1C49,        # ADPCM-B note letter -> byte offset into b_dn (A..G), 2 per semitone
        b_dn=0x2141,          # ADPCM-B delta-N, little-endian words, 12 per octave
        b_oct=0x2962,         # ADPCM-B octave -> byte offset ($2951)
        len_tab=0x11AB,       # length codes (14) then their tick counts at +16 ($119A)
        oct_tab=0x1560,       # FM octave -> block << 3 ($1554)
        penv=0x21D1,          # FM pitch envelope tables ('p' n)
        penv_rate=0x22B1,     # FM pitch envelope rate by note letter
        tempo=0x2BD7,         # tempo $32-$FF -> timer A value (10 bit), little-endian words
        fm_init=0x0346,       # per FM channel: [reg offset][port][key-on code][patch] ($0326)
        a_init=0x0844,        # per ADPCM-A channel: start lo/hi, end lo/hi, level registers, channel bit ($0289)
        carriers=0x14F0,      # number of carriers by algorithm ($14B0)
        block=845, send=900,  # the game's last boot command ($03) at frame 839, its first song (FC D0) at 856-857 (measured)
    ),
}

def game_of(data):
    for k, g in GAMES.items():
        if g['ident'] in data[0x70:0x140]: return k
    raise ValueError('not a known ADK sound driver build')

def m1_path(game):
    g = GAMES[game]; return g['dir'] + '/' + g['m1']

def check(data):
    """the build's table addresses against the word table at $2E00"""
    g = GAMES[game_of(data)]; w = lambda a: data[a] | data[a + 1] << 8
    for off, key in ((0, 'headers'), (6, 'b_smp'), (0xA, 'patches'), (0xC, 'cmd_tab'), (0x10, 'a_env'),
                     (0x12, 'cmd_tab2'), (0x14, 'a_smp'), (0x1A, 'a_smp2')):
        assert w(g['ptrs'] + off) == g[key], key

def music_cmds(data):
    """every music command of the second table (kind $40) with a song: [(cmd, song, mode)]; mode 0 = the song's
    header in the $2E20 table, 1 = header at $F000 with the 2 KB window ($08) on bank `song`, 2 = header at $E000
    with the 4 KB window ($09) on bank `song` ($046D)"""
    g = GAMES[game_of(data)]; t = g['cmd_tab2']
    out = []
    for c in range(0xF0):
        e = data[t + 4 * c:t + 4 * c + 4]
        if e[0] != 0x40: continue
        if e[3] == 0 or (e[3] == 1 and e[2] >= 0x20) or (e[3] == 2 and e[2] >= 0x10):
            if e[2] or e[3]: out.append((c, e[2], e[3]))
    return out
