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
    return [c for c in range(0x21, 0x100) if data[g['types'] + c - 0x20] == 2]
