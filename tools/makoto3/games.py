#!/usr/bin/env python3
"""The games running the "Ver 3.0 by MAKOTO.04/03/10 to SK" sound driver, as one description per game: where each
build keeps the tables the song model reads (docs/ff3_sound_driver.md; sections "KOF94's build", "KOF95's build",
"Fatal Fury Special's build").
song.py, regs.py and capture.py read everything game-specific from here; game_of() tells the build from the M1 ROM
(the interrupt vector at $0039: FF3 JP $212B, KOF94 JP $2096, KOF95 JP $1BCA).

Addresses are Z80 addresses in the M1 ROM; the FF3 names are the ones docs/ff3_sound_driver.md cites. KOF94's driver
is the same code shifted (-$6F around the song start, -$94 / -$95 from the output stage on); KOF95's is a reworked
build (other RAM layout, word jump tables, compacted code) whose music engine behaves the same except where a key
below says otherwise. Fatal Fury Special's is KOF94's code with other tables (section "Fatal Fury Special's build"):
the same interrupt vector, so game_of() also checks which type table the dispatch loads. The code comments cite
routines by their FF3 address.

stack_guard: KOF95 ignores a loop start or call at depth 4 ($23A7, $2434: the count / address bytes are skipped) and
a loop end with an empty stack ($2416); FF3 and KOF94 push without a check (5 entries fit the 16-byte stack)."""

GAMES = {
    'ff3': dict(
        name='Fatal Fury 3', rom='/data/roms/fatfury3.neo', dir='/data/neogeo_dict/sound/snd98/ff3', m1='ff3_m1.bin',
        irq=0x212B,
        types=0x7D8E,         # command -> type (1 system, 2 song, 3 sequenced ADPCM-A effect, 5 SSG effect)
        bank_tab=0x2E00,      # song -> bank map ($1151)
        banks={0: 0x8000, 1: 0x10000, 2: 0x18000},   # bank map -> M1 offset seen at $8000
        headers=0x3A70,       # song header pointers
        smp_tab=0x3B30,       # per-song ADPCM-A sample record tables ($118A -> $FEF8)
        smp_fixed=None,
        patches=0x2E40,       # 52-byte FM patches ($18A4)
        pitch=0x2113, gate=0x2CA3,   # pitch index table ($20CF), gate table ($2B21)
        fnum=0x7F0F,          # F-numbers ($14B5)
        brec=0x6FD6, brec_size=16,                    # ADPCM-B records ($0913)
        b_single=0x7C06, b_octtab=0x7CC6,             # opcode $46: one-sample numbers / per-octave sample tables
        b_dn_pitched=0x7C46, b_dn_oct=0x7CCE,         # ADPCM-B delta-N tables ($1856 / $1830)
        block=880, send=900,  # the game sends $07 (unlock) at frame 873 and its first song ($3E) at 896
    ),
    'kof94': dict(
        name="The King of Fighters '94", rom='/data/roms/kof94.neo', dir='/data/neogeo_dict/sound/kof94',
        m1='kof94_m1.bin', irq=0x2096,
        types=0x6907, bank_tab=0x2E00, banks={0: 0x8000, 1: 0x10000},   # no third map ($10EB: any non-zero byte = map 1)
        headers=0x3B40,
        smp_tab=None, smp_fixed=0x3E73,               # one ADPCM-A table for every song: effect slot 0's ($0447)
        patches=0x2E40, pitch=0x207E, gate=0x2C0E,
        fnum=0x6A88,          # entries 16-31: a second FM scale ~48 cents sharp (FF3: SSG periods)
        brec=0x5F23, brec_size=26,                    # 26-byte records: +$0D..+$19 ADPCM-B effect parameters ($08F8)
        b_single=0x6693, b_octtab=0x6757, b_dn_pitched=0x66D3, b_dn_oct=0x6807,
        block=850, send=900,  # the game sends $07 at frame 848 and its first song ($51) at 853 (measured)
    ),
    'fatfursp': dict(
        name='Fatal Fury Special', rom='/data/roms/fatfursp.neo', dir='/data/neogeo_dict/sound/fatfursp',
        m1='fatfursp_m1.bin', irq=0x2096,             # KOF94's code, instruction for instruction (types tell them apart)
        types=0x74E2, bank_tab=0x2E00, banks={0: 0x8000, 1: 0x10000},
        headers=0x3F1C,
        smp_tab=None, smp_fixed=0x470E,               # one ADPCM-A table for every song, as KOF94 ($0447)
        patches=0x2E40, pitch=0x207E, gate=0x2C0E,
        fnum=0x7663,          # KOF94's table, the sharp second scale included
        brec=0x6552, brec_size=26,                    # KOF94's 26-byte records
        b_single=0x7272, b_octtab=0x7332, b_dn_pitched=0x72B2, b_dn_oct=0x73E2,
        block=850, send=900,  # the game sends $07 at frame 846 and its first song ($47) at 860 (measured)
    ),
    'kof95': dict(
        name="The King of Fighters '95", rom='/data/roms/kof95.neo', dir='/data/neogeo_dict/sound/kof95',
        m1='kof95_m1.bin', irq=0x1BCA,
        types=0x72B4, bank_tab=0x2E00, banks={0: 0x8000, 1: 0x10000},   # two maps, as KOF94 ($0DD8)
        headers=0x3B40,       # ($0E01)
        smp_tab=0x3C00, smp_fixed=None,               # per-song ADPCM-A sample tables again ($0DF4 -> $FEDB)
        patches=0x2E40, pitch=0x1BB2, gate=0x2625,
        fnum=0x7435,
        brec=0x6BFB, brec_size=16,                    # FF3's 16-byte records ($0757)
        b_single=0x702B, b_octtab=0x70F3, b_dn_pitched=0x706B, b_dn_oct=0x71A3,
        stack_guard=True,
        block=870, send=900,  # the game sends $07 at frame 869 and its first song ($21) at 874 (measured)
    ),
}

def game_of(data):
    """the game key of an M1 ROM, from its interrupt vector and (KOF94 / Fatal Fury Special: one code, two builds)
    the command type table the dispatch loads ($01C1: LD HL,types)"""
    v = data[0x3A] | data[0x3B] << 8
    for k, g in GAMES.items():
        if data[0x39] == 0xC3 and g['irq'] == v and bytes((0x21, g['types'] & 0xFF, g['types'] >> 8)) in data[0x1B0:0x1E0]:
            return k
    raise ValueError(f'not a known MAKOTO v3 build (IRQ vector ${v:04X})')

def m1_path(game):
    g = GAMES[game]; return g['dir'] + '/' + g['m1']

def music_cmds(data):
    """every music command (type 2) of the build"""
    t = GAMES[game_of(data)]['types']
    return [c for c in range(0x20, 0x100) if data[t + c] == 2]
