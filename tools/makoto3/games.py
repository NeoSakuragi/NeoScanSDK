#!/usr/bin/env python3
"""The games running the "Ver 3.0 by MAKOTO.04/03/10 to SK" sound driver, as one description per game: where each
build keeps the tables the song model reads (docs/ff3_sound_driver.md; sections "KOF94's build", "KOF95's build",
"Fatal Fury Special's build", "Art of Fighting's build").
song.py, regs.py and capture.py read everything game-specific from here; game_of() tells the build from the M1 ROM
(the interrupt vector at $0039: FF3 JP $212B, KOF94 JP $2096, KOF95 JP $1BCA, Art of Fighting JP $2041, Art of Fighting 3 JP $1C9C;
Art of Fighting 2 = KOF94's vector, told by its type table).

Addresses are Z80 addresses in the M1 ROM; the FF3 names are the ones docs/ff3_sound_driver.md cites. KOF94's driver
is the same code shifted (-$6F around the song start, -$94 / -$95 from the output stage on); KOF95's is a reworked
build (other RAM layout, word jump tables, compacted code) whose music engine behaves the same except where a key
below says otherwise. Fatal Fury Special's is KOF94's code with other tables (section "Fatal Fury Special's build"):
the same interrupt vector, so game_of() also checks which type table the dispatch loads. The code comments cite
routines by their FF3 address.

stack_guard: KOF95 ignores a loop start or call at depth 4 ($23A7, $2434: the count / address bytes are skipped) and
a loop end with an empty stack ($2416); FF3 and KOF94 push without a check (5 entries fit the 16-byte stack).

a_chan (Art of Fighting 3): no per-song or fixed ADPCM-A table; each music ADPCM-A channel has its own table pointer
($FEDF + 2c, `default` after reset) and a flag byte ($FEEB + c: bit 0 = 11-byte records, else 6-byte records
[priority][start16][end16][?] without a loop), both set by opcode $3C p (p - $18 = 0..7: words[i], flags[i]; a zero word
changes nothing) and kept across songs. b_octave False: opcode $46 has no per-octave ADPCM-B mode."""

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
    'aof': dict(
        name='Art of Fighting', rom='/data/roms/aof.neo', dir='/data/neogeo_dict/sound/aof',
        m1='aof_m1.bin', irq=0x2041,                  # KOF94's music engine, other command path (section "Art of Fighting's build")
        types=0x565C, bank_tab=0x2C10, banks={0: 0x8000, 1: 0x10000},   # 64 KB M ROM (mirrored to 128 KB); every song map 0
        headers=0x34A4,
        smp_tab=None, smp_fixed=0x3CBF,               # one ADPCM-A table for every song: effect slot 0's ($0395), as KOF94
        patches=0x2C50, pitch=0x2029, gate=0x2BB3,
        fnum=0x57DD,          # KOF94's table, the sharp second scale included
        brec=0x5054, brec_size=26,                    # KOF94's 26-byte records ($085D)
        b_single=0x53E8, b_octtab=0x54AC, b_dn_pitched=0x5428, b_dn_oct=0x555C,
        block=850, send=900,  # the game sends $03 at frame 838, $07 at 843 and its first song ($29) at 1223 (measured)
    ),
    'aof2': dict(
        name='Art of Fighting 2', rom='/data/roms/aof2.neo', dir='/data/neogeo_dict/sound/aof2',
        m1='aof2_m1.bin', irq=0x2096,                 # KOF94's code, instruction for instruction ("Art of Fighting 2's build")
        types=0x6993, bank_tab=0x2E00, banks={0: 0x8000, 1: 0x10000},
        headers=0x3B0C,
        smp_tab=None, smp_fixed=0x4190,               # one ADPCM-A table for every song: effect slot 0's ($0447), as KOF94
        patches=0x2E40, pitch=0x207E, gate=0x2C0E,
        fnum=0x6B14,          # KOF94's table, the sharp second scale included
        brec=0x60EB, brec_size=26,                    # KOF94's 26-byte records
        b_single=0x6723, b_octtab=0x67E3, b_dn_pitched=0x6763, b_dn_oct=0x6893,
        block=850, send=900,  # the game sends $07 at frame 843 and its first song ($29) at 1365 (measured)
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
    'aof3': dict(
        name='Art of Fighting 3', rom='/data/roms/aof3.neo', dir='/data/neogeo_dict/sound/aof3',
        m1='aof3_m1.bin', irq=0x1C9C,                 # KOF95's reworked build, extended ("Art of Fighting 3's build")
        types=0x5F5E, bank_tab=0x2891, banks={0: 0x8000, 1: 0x10000, 2: 0x18000},   # FF3's three maps again ($0EB3)
        headers=0x3841,
        smp_tab=None, smp_fixed=None,
        a_chan=dict(default=0x3E0F, words=0x2570, flags=0x2580),   # music ADPCM-A samples per channel ($046D, opcode $3C)
        patches=0x28D1, pitch=0x1C84, gate=0x2745,
        fnum=0x60DF,
        brec=0x51E6, brec_size=16,                    # KOF95's 16-byte records ($07C9)
        b_single=0x5CE6, b_octtab=0x5DAE, b_dn_pitched=0x5D26, b_dn_oct=0x5E5E,
        b_octave=False,       # opcode $46: every p >= $40 is one pitched sample ($233F), no per-octave mode
        stack_guard=True,
        block=880, send=900,  # the game sends $07 at frames 869 and 874 (each after $03 $03) and its first song ($21) at 1116 (measured)
    ),
}

def game_of(data):
    """the game key of an M1 ROM, from its interrupt vector and (KOF94 / Fatal Fury Special: one code, two builds)
    the command type table the dispatch loads (FF3 $01C1: LD HL,types; Art of Fighting $0188, Art of Fighting 3 $01F7)"""
    v = data[0x3A] | data[0x3B] << 8
    for k, g in GAMES.items():
        if data[0x39] == 0xC3 and g['irq'] == v and bytes((0x21, g['types'] & 0xFF, g['types'] >> 8)) in data[0x180:0x200]:
            return k
    raise ValueError(f'not a known MAKOTO v3 build (IRQ vector ${v:04X})')

def m1_path(game):
    g = GAMES[game]; return g['dir'] + '/' + g['m1']

def music_cmds(data):
    """every music command (type 2) of the build"""
    t = GAMES[game_of(data)]['types']
    return [c for c in range(0x20, 0x100) if data[t + c] == 2]
