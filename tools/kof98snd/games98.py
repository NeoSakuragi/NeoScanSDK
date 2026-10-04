#!/usr/bin/env python3
"""The games running SNK's own "Sound Driver" (the line that leads to KOF98's "Sound Driver(ROM)Ver 1.7"), as one
description per game: where each build keeps the tables the song model reads, and the few behaviours that changed
between versions (docs/kof98_sound_driver.md; Kizuna Encounter's "Ver 0.0 95/08/11": docs/kizuna_sound_driver.md).
song98.py, regs98.py and capture98.py read everything game-specific from here; game_of() tells the build from the
driver's ID string at $003E of the M1 ROM.

Addresses are Z80 addresses in the M1 ROM. Behaviour keys (False / absent = KOF98's behaviour):
- overhang: a tied note (gate > length) keeps counting its overhang and keys off when it runs out ($1BE0, KOF98);
  Ver 0.0 has no overhang counter: a tied note sounds until the channel's next key-on or key-off ($1B99);
- untie_0e: opcode $0E clears the tie flags (KOF98); Ver 0.0: $0E is a no-op;
- ops: the opcode set ('v17' = $00-$34 of KOF98; 'v00' = $00-$2E, with $01 = 2 ignored bytes, $04 = 1 ignored byte,
  $1F / $20 = start a type 4 / 5 command, $29 = 1 byte, $2B = pan, no $2F-$34);
- vol_always: $2C rewrites the level even before the channel's first note (Ver 0.0), and on ADPCM-B only stores it
  (Ver 0.0, written at the next key-on); KOF98 rewrites only after a note and writes ADPCM-B's $1B at once;
- b_roots: ADPCM-B root notes: 'v17' = $FD20/$FD21 set to the opcode byte ($27, $29: split, high root);
  'v00' = $27 sets root = p - $18 and the split root = that rounded down to an octave, $29 = split note - $18 only,
  and notes below the split use the octave root, notes at or above it the plain root;
- op_fx: four per-operator level effect records per FM channel (opcode $12 bits 4-5, $14 selector 2: Ver 0.0);
  KOF98 has none."""

GAMES = {
    'kof98': dict(
        name="The King of Fighters '98", rom='/data/roms/kof98.neo', m1='/data/tmp/snd98/kof98_m1.bin',
        dir='/data/neogeo_dict/sound/kof98',
        id=b'Sound Driver(ROM)Ver 1.7',
        songs=0x329E, song20=0x2BA2,  # song pointer per command - $20 (cmd $20 = the all-off header)
        banksets=0x2708,              # 4-byte bank sets (ports $08-$0B), indexed by ($2E06)[song]
        notes=0x2BC8, fnum=0x2A68,    # FM note -> semitone<<4 | block, F-numbers (4 per semitone)
        lv_fm=0x311D, lv_a=0x319D, lv_b=0x321D,      # velocity x volume -> TL / ADPCM-A level / ADPCM-B volume
        b_dn=0x2B2A, b_rec=0x2E1E,    # ADPCM-B delta-N table; pointer to the 13-byte ADPCM-B sample records
        fx6=0x2E32,                   # pointer to effect type 6 tables (patch effects)
        big_slot=7,                   # ADPCM-A sample table with 11-byte looping records
        guard=0xFD9B,                 # ISR re-entry flag
        start=[('a', 0x10, 0x01), ('a', 0x10, 0x00), ('a', 0x28, 0x01), ('a', 0x28, 0x02), ('a', 0x28, 0x05),
               ('a', 0x28, 0x06), ('a', 0x10, 0x01), ('a', 0x10, 0x00), ('b', 0x00, 0x87), ('a', 0x1C, 0x87),
               ('a', 0x1C, 0x00)],
        overhang=True, untie_0e=True, ops='v17', vol_always=False, b_roots='v17', op_fx=False,
        music=list(range(0x21, 0x4C)) + list(range(0x50, 0x57)),
        block=410, send=430,  # our emulator (UniBIOS): the game sends $07 at frame 408 and its first song ($21) at 417
                              # (measured 2026-10-04; MAME's captures, MVS BIOS: block 255, send 260)
    ),
    'kizuna': dict(
        name='Kizuna Encounter: Super Tag Battle', rom='/data/roms/kizuna.neo',
        m1='/data/neogeo_dict/sound/kizuna/kizuna_m1.bin', dir='/data/neogeo_dict/sound/kizuna',
        id=b'Sound Driver Ver 0.0 95/08/11',
        songs=0x30D0, song20=0x2AE6, banksets=0x262D,           # ($101E)
        notes=0x2B0C, fnum=0x29AC,                              # ($2433)
        lv_fm=0x2F4F, lv_a=0x2FCF, lv_b=0x304F,                 # ($1F0F, $1EF4, $1F31)
        b_dn=0x2A6E, b_rec=0x2E1A,                              # ($07DD, $06BF)
        fx6=0x2E2A,                                             # ($12E5)
        seqfx=0x2E2C,                                           # sequenced effect records $F0-$FF ($04E3)
        modmask=0x261C,                                         # modulators by algorithm ($1427, $1E26)
        big_slot=5,                                             # ($2098)
        guard=0xFE6B,                                           # ($1991: incremented; 1 = this ISR runs)
        start=[('a', 0x10, 0x01), ('a', 0x10, 0x00), ('a', 0x28, 0x01), ('a', 0x28, 0x02), ('a', 0x28, 0x05),
               ('a', 0x28, 0x06)],                              # ($104B, $0AEE)
        overhang=False, untie_0e=False, ops='v00', vol_always=True, b_roots='v00', op_fx=True,
        types=0x2E6C,                                           # command -> type, $20-$FF ($0140)
        block=880, send=900,  # the game sends $07 at frame 872 and its first song ($3A, attract) at 935 (measured)
    ),
    'samsho4': dict(
        name='Samurai Shodown IV', rom='/data/roms/samsho4.neo',
        m1='/data/neogeo_dict/sound/samsho4/samsho4_m1.bin', dir='/data/neogeo_dict/sound/samsho4',
        id=b'Sound Driver Ver 1.0 96/08/09',
        songs=0x3216, song20=0x2D44, banksets=0x28AA,           # ($1182, $118C, $11C0)
        notes=0x2D6A, fnum=0x2C0A,                              # ($26C0, $26D1)
        lv_fm=0x3095, lv_a=0x3115, lv_b=0x3195,                 # ($2180, $216A, $21A7)
        b_dn=0x2CCC, b_rec=0x2E1A,                              # ($096A, $0815)
        fx6=0x2E2A,
        modmask=0x2899,                                         # ($207E)
        big_slot=5,                                             # ($230D)
        guard=0xFE6B,                                           # ($1B2B)
        start=[('a', 0x10, 0x01), ('a', 0x10, 0x00), ('a', 0x28, 0x01), ('a', 0x28, 0x02), ('a', 0x28, 0x05),
               ('a', 0x28, 0x06), ('a', 0x10, 0x01), ('a', 0x10, 0x00), ('b', 0x00, 0x87), ('a', 0x1C, 0x87),
               ('a', 0x1C, 0x00)],                              # ($1174: as KOF98)
        overhang=True, untie_0e=True, ops='v17', vol_always=False, b_roots='v17', op_fx=True,
        b_legato_keyon=True,
        types=0x2FB0,                                           # command -> type, $20-$FF ($017C)
        block=878, send=900,  # the game sends $07 at frame 876 and its first song ($21) at 880 (measured)
    ),
    'kof97': dict(
        name="The King of Fighters '97", rom='/data/roms/kof97.neo',
        m1='/data/neogeo_dict/sound/kof97/kof97_m1.bin', dir='/data/neogeo_dict/sound/kof97',
        id=b'Sound Driver Ver 1.1 96/10/01',                 # Samurai Shodown IV's Ver 1.0 less its ADPCM-B slur
        # restart (docs/kof97_sound_driver.md); every table below the song data moved by -$0E
        songs=0x3216, song20=0x2D36, banksets=0x289C,           # ($1189, $117F, $11BD)
        notes=0x2D5C, fnum=0x2BFC,                              # ($26B2, $26C3)
        lv_fm=0x3095, lv_a=0x3115, lv_b=0x3195,                 # ($2172, $215C, $2199)
        b_dn=0x2CBE, b_rec=0x2E1A, fx6=0x2E2A,                  # ($095C, $0815)
        modmask=0x288B,                                         # ($2070)
        big_slot=5, guard=0xFE6B,                               # ($22FF, $1B1D)
        start=[('a', 0x10, 0x01), ('a', 0x10, 0x00), ('a', 0x28, 0x01), ('a', 0x28, 0x02), ('a', 0x28, 0x05),
               ('a', 0x28, 0x06), ('a', 0x10, 0x01), ('a', 0x10, 0x00), ('b', 0x00, 0x87), ('a', 0x1C, 0x87),
               ('a', 0x1C, 0x00)],                              # ($1171: as KOF98)
        overhang=True, untie_0e=True, ops='v17', vol_always=False, b_roots='v17', op_fx=True,
        types=0x2FB0,                                           # command -> type, $20-$FF ($017C)
        block=878, send=900,  # the game sends $07 at frame 875 and its first song ($21, attract) at 1550 (measured)
    ),
    'garou': dict(
        name='Garou: Mark of the Wolves', rom='/data/roms/garou.neo',
        m1='/data/neogeo_dict/sound/garou/garou_m1.bin', dir='/data/neogeo_dict/sound/garou',
        id=b'Sound Driver(ROM)Ver 1.8',                      # 99/08/04: KOF98's v1.7 with two changes (below)
        songs=0x329E, song20=0x2BB2, banksets=0x2718,           # ($10FE, $10F4, $1132)
        notes=0x2BD8, fnum=0x2A78,                              # ($252E, $253F)
        lv_fm=0x311D, lv_a=0x319D, lv_b=0x321D,                 # ($2013, $1FFD, $203A)
        b_dn=0x2B3A, b_rec=0x2E1E, fx6=0x2E32,                  # ($0979, $0812, $13EA)
        big_slot=7, guard=0xFD9B,
        start=[('a', 0x10, 0x01), ('a', 0x10, 0x00), ('a', 0x28, 0x01), ('a', 0x28, 0x02), ('a', 0x28, 0x05),
               ('a', 0x28, 0x06), ('a', 0x10, 0x01), ('a', 0x10, 0x00), ('b', 0x00, 0x87), ('a', 0x1C, 0x87),
               ('a', 0x1C, 0x00)],
        overhang=True, untie_0e=True, ops='v17', vol_always=False, b_roots='v17', op_fx=False,
        b_legato_keyon=True,                                    # ($1E8F, as Samurai Shodown IV)
        fm_level_fx=True,                                       # ($1948: the FM level effect's value is added to the
        # velocity and the TL computed from it, $0AB6 / $1F8C; KOF98 recomputes the TL without it)
        types=0x3038,                                           # command -> type, $20-$FF ($0183)
        nop=0x63,             # blocked commands become $63 (type 0: ignored): the NMI ($007B) advances the ring
        # index on a $00 without writing the slot, and the main loop ($0146) would replay the byte left there
        block=431, send=500,  # the game sends $07 at frame 430 and its first song ($5D) at 431 (measured): $5D is
        # blocked, so every song starts from the driver's power-on state (its FM TL shadows carry over between songs)
    ),
}

def game_of(data):
    """the game key of an M1 ROM, from the driver's ID string"""
    for k, g in GAMES.items():
        if data[0x3E:0x3E + len(g['id'])] == g['id']: return k
    raise ValueError('not a known SNK Sound Driver build: ' + data[0x3E:0x66].decode('latin-1'))

def music_cmds(data):
    """every music command (type 2) of the build; KOF98: its validated list"""
    g = GAMES[game_of(data)]
    if 'types' not in g: return g['music']
    w = lambda a: data[a] | data[a + 1] << 8
    return [c for c in range(0x21, 0x100) if data[g['types'] + c - 0x20] == 2 and w(g['songs'] + 2 * (c - 0x20))]
    # (a type-2 command without a song pointer starts nothing, $1182: Garou's $5F)
