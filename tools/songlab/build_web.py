#!/usr/bin/env python3
"""Data for the Song Lab page (song_lab.html): per song, the two YM2610 write streams (A = the real driver, captured
while the game's own Z80 driver played it; B = our model of that driver), the track blocks from the model's event
listing, and the V ROM sample ranges both streams play. One page, one builder, every game:

    python3 build_web.py OUT_DIR 0x23 0x36 ...               KOF98 (song98.py / regs98.py, MAME captures)
    python3 build_web.py --game ff3 OUT_DIR [0x26 ...]       Fatal Fury 3 (tools/makoto3, captures in our emulator);
    python3 build_web.py --game kof94 OUT_DIR [0x25 ...]     KOF94 (same driver family, tools/makoto3);
    python3 build_web.py --game kof95 OUT_DIR [0x22 ...]     KOF95 (same driver family, tools/makoto3);
    python3 build_web.py --game kizuna OUT_DIR [0x21 ...]    Kizuna Encounter (SNK Sound Driver Ver 0.0, KOF98's model:
                                                             song98.py / regs98.py, captures in our emulator, capture98.py);
    python3 build_web.py --game fatfursp OUT_DIR [0x36 ...]  Fatal Fury Special (KOF94's MAKOTO v3 build, tools/makoto3);
    python3 build_web.py --game aof OUT_DIR [0x21 ...]       Art of Fighting (KOF94's MAKOTO v3 music engine, tools/makoto3);
    python3 build_web.py --game aof2 OUT_DIR [0x26 ...]      Art of Fighting 2 (KOF94's MAKOTO v3 build, tools/makoto3);
    python3 build_web.py --game aof3 OUT_DIR [0x24 ...]      Art of Fighting 3 (KOF95's MAKOTO v3 build extended, tools/makoto3);
    python3 build_web.py --game samsho|samsho2|samsho3 OUT_DIR   Samurai Shodown 1-3 (MAKOTO v3 builds, tools/makoto3);
    python3 build_web.py --game samsho4 OUT_DIR [0x50 ...]   Samurai Shodown IV (SNK Sound Driver Ver 1.0, tools/kof98snd);
    python3 build_web.py --game kof97 OUT_DIR [0x30 ...]     KOF97 (SNK Sound Driver Ver 1.1, tools/kof98snd);
    python3 build_web.py --game rbff1 OUT_DIR                Real Bout Fatal Fury (MAKOTO v3, Art of Fighting 3's code, tools/makoto3);
    python3 build_web.py --game rbffspec|rbff2 OUT_DIR       Real Bout Special (SNK Ver 1.1 = KOF97's) / Real Bout 2 (SNK Ver 1.6), tools/kof98snd;
    python3 build_web.py --game garou OUT_DIR [0x34 ...]     Garou: Mark of the Wolves (SNK Sound Driver Ver 1.8, tools/kof98snd);
    python3 build_web.py --game ninjamas OUT_DIR [0xD0 ...]  Ninja Master's (ADK's driver, tools/adksnd: songadk.py /
                                                             regsadk.py, captures in our emulator, captureadk.py);
                                                             no commands = every music command

OUT_DIR gets one JSON per song (XX.json), index.json (the song list) and game.json (the page's title and notes).
Time is in samples at 8 MHz / 144 = 55555.6 Hz (18 us: one timer-A count). Within an interrupt both streams space
the writes alike: the handler starts ISR_START samples after the interrupt and each register write costs WRITE_COST.

KOF98 and Kizuna: a timer-A interrupt every 333 samples (166.83 Hz). Stream A knows which interrupt each write fell in (the
capture's "i" lines); stream B runs the model's ticks back to back on that clock, so a long tick runs past the next
interrupt, which the driver then loses (an interrupt arriving while the handler still runs is dropped). Fitted on the
drops of 10 captured songs: the rule predicts the number of interrupts lost after 95% of the ticks with 20 writes or
more.

FF3, KOF94, KOF95, Fatal Fury Special and Art of Fighting 1-3 (MAKOTO v3 driver): two timers, nothing lost (a pending flag waits for the handler, docs/ff3_sound_driver.md). Timer A every 1023
samples, timer B every 16 * (256 - TB) samples, TB = the song's tempo byte (reg $26, changed by opcode $33). The
captured interrupt order (A or B) is replayed on that schedule; the one unknown, the phase between the two timers, is
the one that reproduces the captured order best. The model runs on the same interrupts, so both streams share one
clock. Fatal Fury Special runs the same driver (KOF94's build).

Ninja Master's (ADK driver): the music runs in the main loop, one tick per two timer-A interrupts, timer A from the
song's tempo. Both streams are placed on the captured timer-A interrupts (1024 - value samples apart, the value from
the captured $24 / $25 writes): stream A at the interrupt each write followed, stream B at the interrupt regsadk.py
finds each model tick starting on."""
import base64, json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))

PERIOD, ISR_START, WRITE_COST = 333, 100, 6.4
SNKSND = ('kof98', 'kof97', 'kizuna', 'samsho4', 'garou', 'rbffspec', 'rbff2')           # games on tools/kof98snd's model

GAMES = {
    'kof98': {
        'm1': '/data/tmp/snd98/kof98_m1.bin', 'cap': '/data/tmp/snd98/cap/cap_%02X.txt', 'neo': '/data/roms/kof98.neo',
        'names': {0x23: 'Team select', 0x21: 'Opening', 0x22: 'Coin', 0x24: 'Win screen', 0x26: 'Continue',
                  0x28: 'How to play', 0x2C: 'VS jingle', 0x31: 'Stage theme (demo Joe vs Athena)',
                  0x32: 'Stage theme (AoF team)', 0x33: 'Stage theme (demo Clark vs Kyo)',
                  0x35: 'Stage theme (demo Chizuru)', 0x36: 'Stage theme (demo Choi vs Yamazaki)',
                  0x3C: 'Stage theme (demo Yamazaki vs Robert)', 0x3D: 'Stage theme (demo Mary vs Leona)'},
        'page': {'title': 'KOF98 Song Lab', 'bar': 384, 'beat': 96, 'start': 0x36,
                 'intro': "The King of Fighters '98 songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write SNK's Z80 sound driver made in MAME, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
                 'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the KOF98 V ROM. Nothing here is a recording.",
                           "<b>Real driver</b>: the register writes captured in MAME while the game's own Z80 driver played the song, placed at the timer interrupt they happened in.",
                           "<b>Model</b>: tools/kof98snd/song98.py + regs98.py, the driver re-implemented from its disassembly, reading the song data from the M1 ROM. For each song the facts line says on how many sequencer ticks its register writes are identical to the real driver's, same values, same order.",
                           "<b>Timing.</b> The capture only knows which interrupt (6 ms) a write fell in, so both sources space the writes of a tick by an estimated 6.4 samples each. The real driver loses an interrupt when a tick has too many writes; the model estimates those losses, so its clock can drift by a fraction of a second over a long song. A/B switching jumps to the same tick, not the same second."],
                 'capture': 'MAME capture', 'unit': 'ticks'}},
    'ff3': {
        'm1': '/data/neogeo_dict/sound/snd98/ff3/ff3_m1.bin', 'cap': '/data/neogeo_dict/sound/snd98/ff3/cap/cap_%02X.txt', 'neo': '/data/roms/fatfury3.neo',
        # measured in our emulator (docs/ff3_songs.md): the game's own commands at these screens
        'names': {0x3E: 'Title / attract', 0x23: 'Player select', 0x24: 'Enemy select', 0x26: 'Stage (vs Bob Wilson)',
                  0x27: 'Stage (vs Franco Bash)', 0x28: 'Stage (vs Blue Mary)', 0x29: 'Stage (vs Joe Higashi)',
                  0x34: 'Win screen', 0x3B: 'Continue', 0x3F: 'Game over'},
        'page': {'title': 'Fatal Fury 3 Song Lab', 'bar': 96, 'beat': 24, 'start': 0x26,
                 'intro': "Fatal Fury 3 songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\") made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
                 'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Fatal Fury 3 V ROM. Nothing here is a recording.",
                           "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                           "<b>Model</b>: tools/makoto3/song.py + regs.py, the driver re-implemented from its disassembly, reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                           "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples. The model does not replay looping ADPCM-A samples when they end (the driver's end-of-sample poll does): song $2A's looped samples stop early in the model."],
                 'capture': 'capture', 'unit': 'interrupts'}},
    'kof94': {
        'm1': '/data/neogeo_dict/sound/kof94/kof94_m1.bin', 'cap': '/data/neogeo_dict/sound/kof94/cap/cap_%02X.txt', 'neo': '/data/roms/kof94.neo',
        # measured in our emulator (docs/kof94_songs.md); the stage themes by the stage on screen
        'names': {0x21: 'Stage: Brazil', 0x22: 'Stage: England', 0x23: 'Stage: Mexico', 0x24: 'Stage: USA',
                  0x25: 'Stage: Italy', 0x26: 'Stage: Japan', 0x27: 'Stage: Korea', 0x28: 'Stage: China',
                  0x29: 'Rugal', 0x2B: 'Rugal, second stage', 0x2C: 'Team ending (Italy)', 0x2D: 'After a coin',
                  0x30: 'Winners\' quote', 0x31: 'Continue', 0x32: 'Team select / VS map', 0x34: 'Cutscene',
                  0x35: 'World map', 0x51: 'Opening', 0x54: 'Ending (Rugal defeated)', 0x5F: 'NEO-GEO logo'},
        'page': {'title': 'KOF94 Song Lab', 'bar': 96, 'beat': 24, 'start': 0x25,
                 'intro': "The King of Fighters '94 songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (a build of Fatal Fury 3's \"Ver 3.0 by MAKOTO\") made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
                 'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the KOF94 V ROM. Nothing here is a recording.",
                           "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                           "<b>Model</b>: tools/makoto3/song.py + regs.py, the same model as Fatal Fury 3's with KOF94's table addresses, reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                           "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
                 'capture': 'capture', 'unit': 'interrupts'}},
    'kof95': {
        'm1': '/data/neogeo_dict/sound/kof95/kof95_m1.bin', 'cap': '/data/neogeo_dict/sound/kof95/cap/cap_%02X.txt', 'neo': '/data/roms/kof95.neo',
        # measured in our emulator (docs/kof95_songs.md); stage themes by the team whose stage it is
        'names': {0x21: 'Opening', 0x22: 'Stage: Hero Team', 0x23: 'Stage: Korea Team', 0x24: 'Stage: Ikari Team',
                  0x25: 'Stage: Psycho Soldier Team (intro)', 0x26: 'Stage: Fatal Fury Team', 0x27: 'Stage: Art of Fighting Team',
                  0x28: 'Stage: Women Fighters Team', 0x29: 'Stage: Rival Team', 0x2A: 'Saisyu Kusanagi',
                  0x2B: 'Staff roll', 0x2C: 'Team select', 0x2D: 'Between matches (KOF94 Rugal theme arranged)',
                  0x2E: 'Between matches ($2D without its intro)', 0x30: "Winners' quote", 0x31: 'Game over',
                  0x33: 'Saisyu defeated', 0x36: 'Team ending (Hero Team)', 0x37: 'Omega Rugal', 0x38: 'After START',
                  0x39: 'Omega Rugal defeated', 0x3A: 'After a coin', 0x50: 'Stage: Psycho Soldier Team (main part)',
                  0x5F: 'NEO-GEO logo'},
        'page': {'title': 'KOF95', 'bar': 96, 'beat': 24, 'start': 0x22,
                 'intro': "The King of Fighters '95 songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (a build of Fatal Fury 3's \"Ver 3.0 by MAKOTO\") made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
                 'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the KOF95 V ROM. Nothing here is a recording.",
                           "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                           "<b>Model</b>: tools/makoto3/song.py + regs.py, the same model as Fatal Fury 3's and KOF94's with KOF95's table addresses, reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                           "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
                 'capture': 'capture', 'unit': 'interrupts'}},
}

GAMES['kizuna'] = {
    'm1': '/data/neogeo_dict/sound/kizuna/kizuna_m1.bin', 'cap': '/data/neogeo_dict/sound/kizuna/cap/cap_%02X.txt',
    'neo': '/data/roms/kizuna.neo',
    # measured in our emulator (docs/kizuna_songs.md): the game's own commands at these screens
    'names': {0x3A: 'Title', 0x3B: 'How to play', 0x32: 'Tag team select', 0x21: 'Stage (dusk street, attract demo)',
                  0x22: 'Stage (night harbour, attract demo)', 0x23: 'Stage (moonlit rooftop, attract demo)',
                  0x24: 'Stage (harbour market)', 0x25: 'Ranking', 0x39: 'Continue', 0x36: 'Continue (after $39)',
                  0x50: 'Game over'},
    'page': {'title': 'Kizuna Encounter', 'bar': 96, 'beat': 24, 'start': 0x24,
             'intro': "Kizuna Encounter: Super Tag Battle songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (SNK's \"Sound Driver Ver 0.0 95/08/11\", the ancestor of KOF98's) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Kizuna Encounter V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/kof98snd/capture98.py) while the game's own driver played the song, placed at the timer interrupt they happened in.",
                       "<b>Model</b>: tools/kof98snd/song98.py + regs98.py, KOF98's driver model with Kizuna's table addresses and the behaviours of this earlier version, reading the song data from the M1 ROM. The facts line says on how many sequencer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One timer-A clock (166.8 Hz) and a tempo accumulator, as KOF98. The capture only knows which interrupt a write fell in, so both sources space the writes of a tick by an estimated 6.4 samples each; the model estimates the interrupts the driver loses during long ticks, so its clock can drift slightly over a long song."],
             'capture': 'capture', 'unit': 'ticks'}}

GAMES['fatfursp'] = {
    'm1': '/data/neogeo_dict/sound/fatfursp/fatfursp_m1.bin', 'cap': '/data/neogeo_dict/sound/fatfursp/cap/cap_%02X.txt',
    'neo': '/data/roms/fatfursp.neo',
    # measured in our emulator (docs/fatfursp_songs.md): the game's own commands at these screens
    'names': {0x47: 'Title', 0x5F: 'NEO-GEO logo', 0x23: 'Player select', 0x24: 'Map before a match ("The 1st stage")',
              0x30: 'Stage: Terry Bogard', 0x31: 'Stage: Andy Bogard', 0x32: 'Stage: Joe Higashi', 0x33: 'Stage: Big Bear',
              0x34: 'Stage: Jubei Yamada', 0x35: 'Stage: Mai Shiranui', 0x36: 'Stage: Cheng Sinzan', 0x37: 'Stage: Kim Kaphwan',
              0x42: 'Stage: Duck King', 0x44: 'Stage: Tung Fu Rue', 0x2E: "Winner's quote (after a lost match)",
              0x2D: 'Continue / card save'},
    'page': {'title': 'Fatal Fury Special', 'bar': 96, 'beat': 24, 'start': 0x36,
             'intro': "Fatal Fury Special songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\", the build KOF94 also runs) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Fatal Fury Special V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/makoto3/song.py + regs.py, the model of Fatal Fury 3, KOF94 and KOF95 with Fatal Fury Special's table addresses (its driver code is KOF94's instruction for instruction), reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
             'capture': 'capture', 'unit': 'interrupts'}}

GAMES['aof'] = {
    'm1': '/data/neogeo_dict/sound/aof/aof_m1.bin', 'cap': '/data/neogeo_dict/sound/aof/cap/cap_%02X.txt',
    'neo': '/data/roms/aof.neo',
    # measured in our emulator (docs/aof_songs.md): the game's own commands at these screens; the stage themes with
    # the 68K's stage counter ($108428) set before the stage
    'names': {0x29: 'Opening (attract story)', 0x3C: 'Title', 0x2B: 'How to play', 0x46: 'Scene before the first fight',
              0x21: 'Stage: Ryuhaku Todoh', 0x22: 'Stage: Jack Turner', 0x23: 'Stage: Lee Pai Long', 0x24: 'Stage: King',
              0x25: 'Stage: Micky Rogers', 0x26: 'Stage: John Crawley', 0x27: 'Stage: Mr. Big', 0x28: 'Stage: Mr. Karate',
              0x30: 'Talk scene after beating Todoh', 0x31: 'Talk scene (Jack, after a lost match)',
              0x47: 'Scene before the Micky fight', 0x2E: 'Map between stages', 0x2F: 'Continue', 0x45: 'Game over',
              0x43: 'Bonus game select', 0x2D: 'Bonus game', 0x44: 'Bonus game over', 0x2A: 'Ending',
              0x5F: 'NEO-GEO logo'},
    'page': {'title': 'Art of Fighting', 'bar': 96, 'beat': 24, 'start': 0x21,
             'intro': "Art of Fighting songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\", the build of KOF94's music engine) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Art of Fighting V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/makoto3/song.py + regs.py, the model of Fatal Fury 3, KOF94, KOF95 and Fatal Fury Special with Art of Fighting's table addresses (its music engine is KOF94's code, its command path an earlier one), reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
             'capture': 'capture', 'unit': 'interrupts'}}

GAMES['aof2'] = {
    'm1': '/data/neogeo_dict/sound/aof2/aof2_m1.bin', 'cap': '/data/neogeo_dict/sound/aof2/cap/cap_%02X.txt',
    'neo': '/data/roms/aof2.neo',
    # measured in our emulator (docs/aof2_songs.md): the game's own commands at these screens; the stage themes by the
    # opponent on screen
    'names': {0x29: 'Opening (attract story)', 0x36: 'Title / how to play', 0x41: 'Player select',
              0x26: 'Stage: Ryo Sakazaki', 0x45: 'Stage: Robert Garcia (intro)', 0x28: 'Stage: Robert Garcia',
              0x25: 'Stage: Eiji Kisaragi', 0x30: 'Stage: Jack Turner', 0x22: 'Stage: Lee Pai Long', 0x31: 'Stage: King',
              0x46: 'Stage: Micky Rogers (intro)', 0x50: 'Stage: Micky Rogers', 0x24: 'Stage: John Crawley',
              0x21: 'Stage: Mr. Big', 0x23: 'Stage: Takuma Sakazaki', 0x27: 'Stage: Yuri Sakazaki', 0x51: 'Stage: Temjin',
              0x52: 'Stage: Geese Howard', 0x4D: 'Scene before Geese', 0x35: 'Geese defeated', 0x34: 'Ending scene (Geese)',
              0x48: "Ending (Ryo's)", 0x2A: 'Staff roll', 0x40: 'Between matches (South Town map)', 0x42: 'Continue',
              0x2F: 'Game over', 0x33: 'Bonus game select', 0x4E: 'Bonus game title card',
              0x43: 'Bonus game: strength training', 0x2B: 'Bonus game: Haoh Shoko-ken', 0x2D: 'Bonus game over',
              0x2E: 'Bonus game over (Haoh Shoko-ken)', 0x5F: 'NEO-GEO logo'},
    'page': {'title': 'Art of Fighting 2', 'bar': 96, 'beat': 24, 'start': 0x26,
             'intro': "Art of Fighting 2 songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\", the build KOF94 also runs) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Art of Fighting 2 V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/makoto3/song.py + regs.py, the model of Fatal Fury 3, KOF94 and KOF95 with Art of Fighting 2's table addresses (its driver code is KOF94's instruction for instruction), reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
             'capture': 'capture', 'unit': 'interrupts'}}

GAMES['aof3'] = {
    'm1': '/data/neogeo_dict/sound/aof3/aof3_m1.bin', 'cap': '/data/neogeo_dict/sound/aof3/cap/cap_%02X.txt',
    'neo': '/data/roms/aof3.neo',
    # measured in our emulator (docs/aof3_songs.md); a stage theme depends on the player's character and the stage
    'names': {0x21: 'Opening (attract)', 0x3D: 'Title / how to play', 0x30: 'Player select',
              0x24: 'Stage (Robert vs Rody, train yard)', 0x28: 'Stage (Robert vs Wang; Ryo vs Rody)',
              0x2A: 'Stage (Robert vs Jin)', 0x2C: 'Stage (Robert vs Sinclair)', 0x2E: 'Stage (Robert vs Kasumi)',
              0x26: 'Stage (Robert vs Lenny)', 0x2D: 'Stage (Robert vs Karman)', 0x23: 'Stage (Robert vs Ryo; Ryo vs Wang)',
              0x25: 'Stage (Ryo vs Jin; demo Kasumi vs Jin)', 0x27: 'Stage (Ryo vs Robert)', 0x2B: 'Final stage (vs Wyler)',
              0x36: 'Scene before the final stage', 0x32: 'Jingle before a stage', 0x2F: 'Scene after a match',
              0x33: 'Continue', 0x3C: 'Game over', 0x5F: 'NEO-GEO logo'},
    'page': {'title': 'Art of Fighting 3', 'bar': 96, 'beat': 24, 'start': 0x24,
             'intro': "Art of Fighting 3 songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\", KOF95's build extended) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Art of Fighting 3 V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/makoto3/song.py + regs.py, the model of Fatal Fury 3, KOF94 and KOF95 with Art of Fighting 3's tables and its two extensions (a sample table per ADPCM-A channel, set by opcode $3C; 6-byte sample records), reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
             'capture': 'capture', 'unit': 'interrupts'}}

GAMES['ninjamas'] = {
    'm1': '/data/neogeo_dict/sound/ninjamas/ninjamas_m1.bin', 'cap': '/data/neogeo_dict/sound/ninjamas/cap/cap_%02X.txt',
    'neo': '/data/roms/ninjamas.neo',
    # measured in our emulator (docs/ninjamas_songs.md): the game's own commands at these screens
    'names': {0x02: 'NEO-GEO logo', 0xD0: 'Title / attract', 0xD1: 'How to play', 0xD2: 'Character select',
              0xC7: 'Stage: Goemon', 0xC5: 'Stage: Houoh', 0xC8: 'Stage: Unzen', 0xC9: 'Stage: Kasumi',
              0xD3: 'Cue before a continue (cut by $D2)', 0xD5: 'Continue', 0xD6: 'Game over',
              0xD9: 'Title after a game over'},
    'page': {'title': "Ninja Master's", 'bar': 192, 'beat': 48, 'start': 0xD0,
             'intro': "Ninja Master's songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (ADK's \"Operation System Program for Music & Effective Sound Ver. 8.8.9\") made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Ninja Master's V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/adksnd/captureadk.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/adksnd/songadk.py, the driver re-implemented from its disassembly. The songs are MML text (note letters, octave and volume commands, binary length codes) that the driver reads as it plays; the model reads the same text from the M1 ROM. The facts line says on how many music ticks its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> The driver plays the music in its main loop, one tick per two timer-A interrupts, timer A set by the song's tempo (192 ticks to a whole note). Both sources are placed on the captured interrupts, writes spaced by an estimated 6.4 samples. Tracks are named by chip channel: the driver's first two FM parts play on FM3 and FM4 (port B), its last two on FM1 and FM2."],
             'capture': 'capture', 'unit': 'ticks'}}

GAMES['samsho'] = {
    'm1': '/data/neogeo_dict/sound/samsho/samsho_m1.bin', 'cap': '/data/neogeo_dict/sound/samsho/caps/cap_%02X.txt',
    'neo': '/data/roms/samsho.neo',
    # measured in our emulator (docs/samsho_songs.md): the game's own commands at these screens; the stage themes from
    # the 68K's stage table (several measured with the stage byte set)
    'names': {39: 'Title / attract', 33: 'Stage: Haohmaru (attract demo)', 66: 'Stage: Nakoruru', 65: 'Stage: Hanzo', 64: 'Stage: Galford', 37: 'Stage: Wan-Fu', 34: 'Stage: Ukyo', 68: 'Stage: Kyoshiro', 35: 'Stage: Gen-an', 40: 'Stage: Earthquake', 36: 'Stage: Jubei', 67: 'Stage: Tam Tam', 69: 'Stage: Charlotte', 42: 'Stage: Amakusa', 38: 'Bonus stage', 53: 'Player select (after a coin)', 45: 'Journey map (character chosen)', 49: "Opponent's challenge on the map", 44: "Winner's scene (after a lost match)", 83: 'Continue', 84: 'Game over'},
    'page': {'title': 'Samurai Shodown', 'bar': 96, 'beat': 24, 'start': 0x21,
             'intro': "Samurai Shodown songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\", the build KOF94 also runs) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Samurai Shodown V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/makoto3/song.py + regs.py, the model of Fatal Fury 3, KOF94 and KOF95 with Samurai Shodown's table addresses (its driver code is KOF94's instruction for instruction), reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
             'capture': 'capture', 'unit': 'interrupts'}}

GAMES['samsho2'] = {
    'm1': '/data/neogeo_dict/sound/samsho2/samsho2_m1.bin', 'cap': '/data/neogeo_dict/sound/samsho2/caps/cap_%02X.txt',
    'neo': '/data/roms/samsho2.neo',
    # measured in our emulator (docs/samsho2_songs.md): the game's own commands at these screens; the stage themes from
    # the 68K's stage table (several measured with the stage byte set)
    'names': {45: 'Title / attract', 56: 'Player select / opening story', 60: 'Opening story', 46: 'Before a fight ("En garde")', 33: 'Stage: Haohmaru (attract demo)', 37: 'Stage: Nakoruru', 49: 'Stage: Hanzo', 38: 'Stage: Galford', 43: 'Stage: Wan-Fu', 34: 'Stage: Ukyo', 48: 'Stage: Kyoshiro', 44: 'Stage: Gen-an', 35: 'Stage: Earthquake', 41: 'Stage: Jubei', 50: 'Stage: Charlotte', 40: 'Stage: Genjuro', 52: 'Stage: Cham Cham', 51: 'Stage: Neinhalt Sieger', 42: 'Stage: Nicotine', 36: 'Stage: Mizuki', 39: 'Stage: Kuroko', 47: 'End of a round', 53: "Winner's quote", 66: 'Continue', 70: 'Game over'},
    'page': {'title': 'Samurai Shodown II', 'bar': 96, 'beat': 24, 'start': 0x2b,
             'intro': "Samurai Shodown II songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\", KOF94's music engine with more effect slots) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Samurai Shodown II V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/makoto3/song.py + regs.py, the model of Fatal Fury 3, KOF94 and KOF95 with Samurai Shodown II's table addresses (its music engine is KOF94's code, moved), reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
             'capture': 'capture', 'unit': 'interrupts'}}

GAMES['samsho3'] = {
    'm1': '/data/neogeo_dict/sound/samsho3/samsho3_m1.bin', 'cap': '/data/neogeo_dict/sound/samsho3/caps/cap_%02X.txt',
    'neo': '/data/roms/samsho3.neo',
    # measured in our emulator (docs/samsho3_songs.md): the game's own commands at these screens; the stage themes from
    # the 68K's stage table (several measured with the stage byte set)
    'names': {60: 'Opening / title', 48: 'Player select', 49: 'Before a fight', 58: 'Before the fight with Zankuro', 33: 'Stage: Haohmaru', 36: 'Stage: Nakoruru', 43: 'Stage: Rimururu', 39: 'Stage: Hanzo', 35: 'Stage: Galford', 38: 'Stage: Kyoshiro', 34: 'Stage: Ukyo (attract demo)', 37: 'Stage: Genjuro', 40: 'Stage: Basara', 42: 'Stage: Shizumaru', 41: 'Stage: Gaira', 45: 'Stage: Amakusa', 44: 'Stage: Kuroko', 46: 'Stage: Zankuro', 50: 'Result of a round', 51: "Winner's quote", 62: 'Continue / game over'},
    'page': {'title': 'Samurai Shodown III', 'bar': 96, 'beat': 24, 'start': 0x22,
             'intro': "Samurai Shodown III songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\", Art of Fighting 3's build) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Samurai Shodown III V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/makoto3/song.py + regs.py, the model of Fatal Fury 3, KOF94, KOF95 and Art of Fighting 3 with Samurai Shodown III's tables (a sample table per ADPCM-A channel, set by opcode $3C, as Art of Fighting 3), reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
             'capture': 'capture', 'unit': 'interrupts'}}

GAMES['samsho4'] = {
    'm1': '/data/neogeo_dict/sound/samsho4/samsho4_m1.bin', 'cap': '/data/neogeo_dict/sound/samsho4/caps/cap_%02X.txt',
    'neo': '/data/roms/samsho4.neo',
    # measured in our emulator (docs/samsho4_songs.md): the game's own commands at these screens; the stage themes from
    # the 68K's stage table (several measured with the stage byte set)
    'names': {33: 'Opening / title', 57: 'Player select', 54: 'Scene before the first stage', 44: 'Map', 58: 'Scene before a fight (attract demo)', 34: 'Theme: Haohmaru', 82: 'Theme: Nakoruru', 83: 'Theme: Rimururu', 48: 'Theme: Galford', 80: 'Theme: Ukyo', 35: 'Theme: Genjuro', 50: 'Theme: Amakusa', 51: 'Theme: Zankuro', 84: 'Theme: Charlotte', 81: 'Theme: Kazuki', 49: 'Theme: Sogetsu', 39: 'Stage: Hanzo', 40: 'Stage: Kyoshiro', 55: 'Stage: Basara', 56: 'Stage: Shizumaru / Gaira', 59: 'Result of a round', 60: "Winner's scene", 61: 'Continue / game over'},
    'page': {'title': 'Samurai Shodown IV', 'bar': 96, 'beat': 24, 'start': 0x50,
             'intro': "Samurai Shodown IV songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (SNK's \"Sound Driver Ver 1.0 96/08/09\", between Kizuna Encounter's and KOF98's) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Samurai Shodown IV V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/kof98snd/capture98.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/kof98snd/song98.py + regs98.py, KOF98's driver model with Samurai Shodown IV's table addresses and the one behaviour of this version that differs in its songs (an ADPCM-B slur into another note keys the sample on again), reading the song data from the M1 ROM. The facts line says on how many sequencer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One timer-A clock (166.8 Hz) and a tempo accumulator, as KOF98. The capture only knows which interrupt a write fell in, so both sources space the writes of a tick by an estimated 6.4 samples each; the model estimates the interrupts the driver loses during long ticks, so its clock can drift slightly over a long song."],
             'capture': 'capture', 'unit': 'ticks'}}

GAMES['kof97'] = {
    'm1': '/data/neogeo_dict/sound/kof97/kof97_m1.bin', 'cap': '/data/neogeo_dict/sound/kof97/caps/cap_%02X.txt',
    'neo': '/data/roms/kof97.neo',
    # measured in our emulator (docs/kof97_songs.md): the game's own commands at these screens; the fight themes from
    # the 68K's tables $69F78 / $69FB8 (the opponent's fighter) and $69FCE (the stage number $10A7EA)
    'names': {0x21: 'Opening / title', 0x3A: 'How to play (after a coin)', 0x23: 'Team and order select', 0x25: 'World map before a stage',
              0x2C: 'Continue', 0x30: 'Stage 0: arena (attract demo)', 0x35: 'Stage 1: amusement park (attract demo)',
              0x31: 'Stage 2: Bali village (attract demo)', 0x32: 'Stage 3: Chinese street festival (attract demo)',
              0x33: 'Stage 4: Korean palace (attract demo)', 0x34: 'Stage 5: seaside city', 0x4A: 'Stage 6: lava ring',
              0x4B: 'Stage 7: dark stone ring', 0x40: 'Theme: Kyo', 0x41: 'Theme: Iori', 0x42: 'Theme: Shingo',
              0x43: 'Theme: Athena', 0x44: 'Theme: Yashiro / Shermie / Chris (New Face team)', 0x45: 'Theme: Terry',
              0x46: 'Theme: Yamazaki', 0x47: 'Theme: Blue Mary', 0x48: 'Theme: Billy'},
    'page': {'title': "The King of Fighters '97", 'bar': 96, 'beat': 24, 'start': 0x30,
             'intro': "KOF97 songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (SNK's \"Sound Driver Ver 1.1 96/10/01\", the build after Samurai Shodown IV's 1.0, before KOF98's 1.7) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the KOF97 V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/kof98snd/capture98.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/kof98snd/song98.py + regs98.py, KOF98's driver model with KOF97's table addresses (Samurai Shodown IV's driver without its ADPCM-B slur restart), reading the song data from the M1 ROM. The facts line says on how many sequencer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One timer-A clock (166.8 Hz) and a tempo accumulator, as KOF98. The capture only knows which interrupt a write fell in, so both sources space the writes of a tick by an estimated 6.4 samples each; the model estimates the interrupts the driver loses during long ticks, so its clock can drift slightly over a long song."],
             'capture': 'capture', 'unit': 'ticks'}}

GAMES['rbff1'] = {
    'm1': '/data/neogeo_dict/sound/rbff1/rbff1_m1.bin', 'cap': '/data/neogeo_dict/sound/rbff1/caps/cap_%02X.txt',
    'neo': '/data/roms/rbff1.neo',
    # measured in our emulator (docs/rbff1_songs.md); the fight themes from the 68K's table $A76A by the CPU fighter's id
    'names': {0x3E: 'Opening / title', 0x4B: 'Enemy select', 0x23: 'Enemy select (the same song data as $4B)',
              0x59: 'Before a fight (stage intro)', 0x57: 'Before a fight (stage intro)', 0x5E: 'Before a fight (stage intro)',
              0x56: 'Before the final fight (Geese)', 0x2F: 'Theme: Terry', 0x2C: 'Theme: Andy', 0x29: 'Theme: Joe', 0x2B: 'Theme: Mai',
              0x30: 'Theme: Geese', 0x2E: 'Theme: Sokaku', 0x26: 'Theme: Bob', 0x2D: 'Theme: Hon-Fu', 0x28: 'Theme: Blue Mary',
              0x27: 'Theme: Franco', 0x31: 'Theme: Yamazaki', 0x32: 'Theme: Jin Chonshu', 0x33: 'Theme: Jin Chonrei',
              0x5A: 'Theme: Duck King', 0x5B: 'Theme: Kim', 0x5C: 'Theme: Billy', 0x2A: 'Final fight: Geese',
              0x55: 'Continue', 0x5D: 'Ending (Terry)', 0x47: 'Staff roll', 0x3D: 'Rank / name entry',
              0x3F: 'After the name entry', 0x20: 'All off (3 ticks)'},
    'page': {'title': 'Real Bout Fatal Fury', 'bar': 96, 'beat': 24, 'start': 0x2F,
             'intro': "Real Bout Fatal Fury songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (\"Ver 3.0 by MAKOTO\", Art of Fighting 3's code with other tables) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Real Bout Fatal Fury V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/makoto3/capture.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/makoto3/song.py + regs.py with Real Bout's tables (Art of Fighting 3's build: a sample table per ADPCM-A channel, set by opcode $3C), reading the song data from the M1 ROM. The facts line says on how many timer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One music tick per timer-B interrupt; both sources are placed on the same timer schedule (timer A 54.3 Hz, timer B from the song's tempo byte), writes spaced by an estimated 6.4 samples."],
             'capture': 'capture', 'unit': 'interrupts'}}

GAMES['rbffspec'] = {
    'm1': '/data/neogeo_dict/sound/rbffspec/rbffspec_m1.bin', 'cap': '/data/neogeo_dict/sound/rbffspec/caps/cap_%02X.txt',
    'neo': '/data/roms/rbffspec.neo',
    # measured in our emulator (docs/rbffspec_songs.md); the fight themes from the 68K's table $ADEC by the CPU fighter's id
    'names': {0x35: 'Opening / title', 0x38: 'Player select', 0x3D: 'Jingle that leads into the player select ($38)',
              0x3A: 'Before a fight', 0x34: 'Theme: Terry', 0x21: 'Theme: Andy', 0x22: 'Theme: Joe', 0x23: 'Theme: Mai',
              0x32: 'Theme: Geese (also in the ending)', 0x24: 'Theme: Sokaku', 0x25: 'Theme: Bob', 0x26: 'Theme: Hon-Fu',
              0x27: 'Theme: Blue Mary', 0x28: 'Theme: Franco', 0x29: 'Theme: Yamazaki', 0x2A: 'Theme: Jin Chonshu / Jin Chonrei',
              0x2C: 'Theme: Duck King', 0x2D: 'Theme: Kim', 0x2E: 'Theme: Billy', 0x30: 'Theme: Cheng', 0x2F: 'Theme: Tung',
              0x31: 'Theme: Laurence', 0x33: 'Theme: Krauser', 0x37: 'Ending begins (after Krauser)', 0x36: 'Ending: Congratulation',
              0x3B: 'Continue', 0x3C: 'Game over'},
    'page': {'title': 'Real Bout Fatal Fury Special', 'bar': 96, 'beat': 24, 'start': 0x34,
             'intro': "Real Bout Fatal Fury Special songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (SNK's \"Sound Driver Ver 1.1 96/10/01\", byte for byte KOF97's driver code) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Real Bout Fatal Fury Special V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/kof98snd/capture98.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/kof98snd/song98.py + regs98.py, KOF98's driver model with KOF97's table addresses (the same driver build), reading the song data from the M1 ROM. The facts line says on how many sequencer interrupts its register writes are identical to the real driver's, same values, same order ($3D: up to its last byte, a command that starts $38).",
                       "<b>Timing.</b> One timer-A clock (166.8 Hz) and a tempo accumulator, as KOF98. The capture only knows which interrupt a write fell in, so both sources space the writes of a tick by an estimated 6.4 samples each; the model estimates the interrupts the driver loses during long ticks, so its clock can drift slightly over a long song."],
             'capture': 'capture', 'unit': 'ticks'}}

GAMES['rbff2'] = {
    'm1': '/data/neogeo_dict/sound/rbff2/rbff2_m1.bin', 'cap': '/data/neogeo_dict/sound/rbff2/caps/cap_%02X.txt',
    'neo': '/data/roms/rbff2.neo',
    # measured in our emulator (docs/rbff2_songs.md); the fight themes from the 68K's table $F6F4 by the CPU fighter's id
    'names': {0x21: 'Opening / title', 0x22: 'Title after a coin', 0x23: 'How to play', 0x24: 'Player select',
              0x26: 'Before a fight (Terry vs Andy)', 0x2A: 'Before a fight (mirror match)',
              0x30: 'Theme: Terry', 0x31: 'Theme: Andy', 0x32: 'Theme: Joe', 0x33: 'Theme: Mai', 0x34: 'Theme: Geese',
              0x35: 'Theme: Sokaku', 0x36: 'Theme: Bob', 0x37: 'Theme: Hon-Fu', 0x38: 'Theme: Blue Mary', 0x39: 'Theme: Franco',
              0x3A: 'Theme: Yamazaki', 0x3B: 'Theme: Jin Chonshu / Jin Chonrei', 0x3C: 'Theme: Duck King', 0x3D: 'Theme: Kim',
              0x3E: 'Theme: Billy', 0x3F: 'Theme: Cheng', 0x40: 'Theme: Tung', 0x41: 'Theme: Laurence', 0x42: 'Theme: Krauser',
              0x43: 'Theme: Rick', 0x44: 'Theme: Li Xiangfei', 0x45: 'Theme: Alfred',
              0x2B: 'Continue', 0x29: 'Game over', 0x2F: 'Ending (Terry)'},
    'page': {'title': 'Real Bout Fatal Fury 2', 'bar': 96, 'beat': 24, 'start': 0x30,
             'intro': "Real Bout Fatal Fury 2 songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (SNK's \"Sound Driver(ROM)Ver 1.6 97/12/08\": KOF98's v1.7 code with the operator level effects of Ver 1.0/1.1) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Real Bout Fatal Fury 2 V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/kof98snd/capture98.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/kof98snd/song98.py + regs98.py, KOF98's driver model with Real Bout 2's table addresses and the operator level effects switched on, reading the song data from the M1 ROM. The facts line says on how many sequencer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One timer-A clock (166.8 Hz) and a tempo accumulator, as KOF98. The capture only knows which interrupt a write fell in, so both sources space the writes of a tick by an estimated 6.4 samples each; the model estimates the interrupts the driver loses during long ticks, so its clock can drift slightly over a long song."],
             'capture': 'capture', 'unit': 'ticks'}}

GAMES['garou'] = {
    'm1': '/data/neogeo_dict/sound/garou/garou_m1.bin', 'cap': '/data/neogeo_dict/sound/garou/caps/cap_%02X.txt',
    'neo': '/data/roms/garou.neo',
    # measured in our emulator (docs/garou_songs.md): the game's own commands at these screens; the stage themes from
    # the 68K's table $1A40C by the opponent ($107434; several measured with it set)
    'names': {93: 'Intro ("Certainly, they existed...")', 33: 'Title (night city)', 63: 'How to play', 34: 'Player select', 97: 'End of a match (K.O.)', 44: 'Continue', 76: 'Game over / saving', 48: 'Stage: Terry Bogard', 49: 'Stage: Rock Howard (attract demo)', 50: 'Stage: Kim Dong Hwan', 51: 'Stage: Kim Jae Hoon', 52: 'Stage: Hotaru Futaba', 53: 'Stage: Gato', 54: 'Stage: B. Jenet', 55: 'Stage: Marco Rodriguez (attract demo)', 56: 'Stage: Hokutomaru (attract demo)', 57: 'Stage: Freeman', 58: 'Stage: Griffon', 59: 'Stage: Kevin Rian (attract demo)', 60: 'Stage: Grant', 61: 'Stage: Kain R. Heinlein', 64: 'Versus: Terry Bogard', 65: 'Versus: Rock Howard', 66: 'Versus: Kim Dong Hwan', 67: 'Versus: Kim Jae Hoon', 68: 'Versus: Hotaru Futaba', 69: 'Versus: Gato', 70: 'Versus: B. Jenet', 71: 'Versus: Marco Rodriguez', 72: 'Versus: Hokutomaru', 73: 'Versus: Freeman', 74: 'Versus: Griffon', 75: 'Versus: Kevin Rian'},
    'page': {'title': 'Garou: Mark of the Wolves', 'bar': 96, 'beat': 24, 'start': 0x34,
             'intro': "Garou: Mark of the Wolves songs played two ways through the same YM2610 emulator: <b>Real driver</b> is every register write the game's Z80 sound driver (SNK's \"Sound Driver(ROM)Ver 1.8\", the build after KOF98's 1.7) made in our emulator, <b>Model</b> is our reading of that driver re-playing the song data from the M1 ROM. Switch between them while it plays; the playhead keeps its place in the music.",
             'notes': ["<b>Chip.</b> Both sources run through ymfm's YM2610 (Geolith's C port, the core our emulator uses), compiled to WebAssembly and running in this page, with the ADPCM samples from the Garou V ROM. Nothing here is a recording.",
                       "<b>Real driver</b>: the register writes captured in our emulator (Geolith core with a Z80 port tap, tools/kof98snd/capture98.py) while the game's own driver played the song.",
                       "<b>Model</b>: tools/kof98snd/song98.py + regs98.py, KOF98's driver model with Garou's table addresses and its two changes (the FM level effect works on the velocity; an ADPCM-B slur into another note keys on again), reading the song data from the M1 ROM. The facts line says on how many sequencer interrupts its register writes are identical to the real driver's, same values, same order.",
                       "<b>Timing.</b> One timer-A clock (166.8 Hz) and a tempo accumulator, as KOF98. The capture only knows which interrupt a write fell in, so both sources space the writes of a tick by an estimated 6.4 samples each; the model estimates the interrupts the driver loses during long ticks, so its clock can drift slightly over a long song."],
             'capture': 'capture', 'unit': 'ticks'}}

def vrom(neo):
    d = open(neo, 'rb')
    h = struct.unpack('<7I', d.read(28))
    off = 4096 + h[1] + h[2] + h[3]
    d.seek(off); return d.read(h[4])

# ---------------------------------------------------------------------------------------------- KOF98 and Kizuna
def cmd_of(field):
    """MAME's captures log the 68000's word ($2300), capture98.py the Z80's byte ($23) (as regs98.cmd_of)"""
    v = int(field, 16)
    return v >> 8 if len(field) > 2 else v

def kof98_cap_times(path, cmd):
    """capture writes from the command on -> ([(sample, port, reg, val)], sample of each sequencer interrupt): interrupt boundary + ISR_START (if a new
    handler starts there; not for the nested interrupt that lands during a long one) + WRITE_COST per write since"""
    lines = [l.split() for l in open(path)]
    out = []; started = False; tim = 0; j = 0; fresh = True; seq = [0]
    for i, p in enumerate(lines):
        if not p: continue
        if p[0] == 'c' and not started and p[-1] != 'blocked' and cmd_of(p[1]) == cmd: started = True; continue
        if not started: continue
        if p[0] == 'i' and int(p[1], 16) & 1:
            tim += 1; j = 0
            q = next((x for x in lines[i + 1:i + 40] if x and x[0] in ('q', 'i')), None)
            fresh = q is not None and q[0] == 'q' and q[1] == '1'
            continue
        if p[0] == 'q' and p[1] == '1': seq.append(tim * PERIOD); continue
        if p[0] in ('a', 'b'):
            out.append((int(tim * PERIOD + (ISR_START if fresh else 0) + j * WRITE_COST), p[0], int(p[1], 16), int(p[2], 16)))
            j += 1
    return out, seq

def kof98_tracks(s):
    tracks = []
    for name in CHANNELS:
        ev = [l for l in s.log if l[1] == name]
        if not ev: continue
        blocks, lines = [], []
        inst = ''
        for tick, _, pos, txt in ev:
            lines.append([tick, pos, txt])
            m = re.match(r'(?:\+(\d+) )?(\S+)\s*(.*)', txt.strip())
            ln, op, args = int(m.group(1) or 0), m.group(2), m.group(3)
            if op == 'instrument' or op == 'sampletable': inst = args.split(' ')[0]
            if op.startswith('note'):
                g = re.search(r'gate (\d+)', args)
                dur = int(g.group(1)) if g else ln
                lab = args.split(' (')[0]
                blocks.append([tick, tick + max(dur, 1), lab, inst, len(lines) - 1])
        tracks.append({'name': name, 'blocks': blocks, 'lines': lines})
    return tracks

def kof98_song(g, data, cmd):
    global CHANNELS
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'kof98snd'))
    from song98 import Song, CHANNELS
    from regs98 import writes, capture, compare
    path = g['cap'] % cmd
    cap, pre = capture(path, cmd)
    nseq = cap[-1][0]
    ca, irqA = kof98_cap_times(path, cmd)
    A = [[t, 0 if p == 'a' else 1, r, val] for t, p, r, val in ca]
    s = Song(data, cmd, listing=True).run(irqs=nseq)
    B = writes(s)
    count = {}
    for q, p, r, val in B: count[q] = count.get(q, 0) + 1
    real = {}; free = 0                          # sequencer interrupt -> timer interrupt; free: handler done (samples)
    tim = 0
    for q in range(0, nseq + 2):
        while tim * PERIOD < free: tim += 1           # interrupts that arrive while the handler runs
        real[q] = tim
        n = count.get(q, 0)
        free = tim * PERIOD + (ISR_START + n * WRITE_COST if n else 0)
        tim += 1
    Bw = []; j = 0; prev = None
    for q, p, r, val in B:
        if q > nseq: break
        j = j + 1 if q == prev else 0; prev = q
        Bw.append([int(real[q] * PERIOD + ISR_START + j * WRITE_COST), 0 if p == 'a' else 1, r, val])
    acc = 0; irq = 0; tick_irq = {0: 0}; nt = 0      # sequencer tick -> sequencer interrupt (the tempo accumulator)
    while irq <= nseq:
        irq += 1; acc += s.tempo
        if acc >= 0xD0: acc -= 0xD0; nt += 1; tick_irq[nt] = irq
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()): same, total = compare(data, cmd, path)
    print(f'${cmd:02X}: {nseq} seq irqs, measured drops {cap[-1][1] - nseq}', end=', ')
    return dict(A=A, B=Bw, pre=[[0 if p == 'a' else 1, r, val] for p, r, val in pre], match=[same, total],
                tempo=s.tempo, ticks_per_s=166.83 * s.tempo / 208, ticks=nt, tick_irq=[tick_irq[k] for k in range(nt + 1)],
                irqA=irqA, irqB=[real[q] * PERIOD for q in range(nseq + 1)], tracks=kof98_tracks(s))

# ------------------------------------------------------------------------------ FF3 and KOF94 (MAKOTO v3 driver)
def ff3_schedule(kinds, tbs):
    """sample time of each interrupt: timer A every 1023 samples, timer B every 16 * (256 - TB) with TB in effect at
    the previous B (the value reloads at the overflow); the A phase that reproduces the captured order best"""
    tb = [0]
    for k, t in zip(kinds, tbs):
        if k == 'B': tb.append(tb[-1] + 16 * (256 - t))
    tb = tb[:-1] if len(tb) > 1 else tb
    def order(ph, n=3000):
        ia = ib = 0; out = []
        while len(out) < min(n, len(kinds)):
            ta = ph + 1023 * ia; t_b = tb[ib] if ib < len(tb) else 10 ** 12
            if t_b <= ta: out.append(('B', t_b)); ib += 1
            else: out.append(('A', ta)); ia += 1
        return out
    best = max(range(-1023, 1024, 3), key=lambda ph: sum(x[0] == k for x, k in zip(order(ph), kinds)))
    best = max(range(best - 3, best + 4), key=lambda ph: sum(x[0] == k for x, k in zip(order(ph), kinds)))
    ia = ib = 0; times = []
    for k in kinds:                                  # the captured order, each kind on its own schedule
        if k == 'A': times.append(best + 1023 * ia); ia += 1
        else: times.append(tb[ib] if ib < len(tb) else tb[-1]); ib += 1
    t0 = min(times[:2]) if times else 0
    return [t - t0 + PERIOD for t in times]

def ff3_tracks(s):
    tracks = []
    for name in CHANNELS:
        ev = [l for l in s.log if l[1] == name]
        if not ev: continue
        blocks, lines = [], []
        inst = ''
        for tick, _, pos, txt in ev:
            lines.append([tick, pos, txt])
            w = txt.split()
            if w[0] == 'inst': inst = w[1]
            if w[0] == 'note':
                ln = int(re.search(r'len (\d+)', txt).group(1))
                g = re.search(r'gate (\d+)', txt)
                dur = int(g.group(1)) if g else ln
                blocks.append([tick, tick + max(dur, 1), ' '.join(w[1:3]) if name.startswith('A') else w[1], inst, len(lines) - 1])
        tracks.append({'name': name, 'blocks': blocks, 'lines': lines})
    return tracks

def ff3_song(g, data, cmd):
    global CHANNELS
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'makoto3'))
    from song import Song, CHANNELS, tick_hz
    from regs import writes, capture, compare
    path = g['cap'] % cmd
    cap, kinds, pre = capture(path, cmd)
    n = len(kinds) - 1                               # the capture stops inside its last interrupt
    tbs = []; tb = None                              # timer B value in effect at each interrupt
    wi = 0
    for i in range(1, n + 1):
        while wi < len(cap) and cap[wi][0] < i:
            if cap[wi][1:3] == ('a', 0x26): tb = cap[wi][3]
            wi += 1
        tbs.append(tb if tb is not None else 0)
    times = [0] + ff3_schedule(kinds[:n], tbs)       # index = interrupt (0 = the command, in the main loop)
    def place(ws):
        out = []; j = 0; prev = None
        for q, p, r, v in ws:
            if q > n: break
            j = j + 1 if q == prev else 0; prev = q
            out.append([int(times[q] + (ISR_START if q else 0) + j * WRITE_COST), 0 if p == 'a' else 1, r, v])
        return sorted(out, key=lambda x: x[0])
    s = Song(data, cmd, listing=True).run(irqs=n, seq=kinds)
    A, B = place(cap), place(writes(s))
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()): same, total, _, _ = compare(data, cmd, path)
    bt = [times[i + 1] for i, k in enumerate(kinds[:n]) if k == 'B']
    nt = s.tick
    seq = [0] + bt[:nt]
    return dict(A=A, B=B, pre=[[0 if p == 'a' else 1, r, v] for p, r, v in pre], match=[same, total],
                tempo=s.head[0x17], ticks_per_s=tick_hz(s.head[0x17]), ticks=nt, tick_irq=list(range(nt + 1)),
                irqA=seq, irqB=seq, tracks=ff3_tracks(s))

# ---------------------------------------------------------------------------------- Ninja Master's (ADK driver)
ADK_TRACK = {'FM1': 'FM3', 'FM2': 'FM4', 'FM3': 'FM1', 'FM4': 'FM2'}   # header part -> chip channel (key-on code)

def adk_song(g, data, cmd):
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'adksnd'))
    from songadk import Song, tick_hz
    from regsadk import capture, compare
    import io, contextlib
    path = g['cap'] % cmd
    cap, kinds, pre = capture(path, cmd)
    with contextlib.redirect_stdout(io.StringIO()): same, total, _, p, _, r, _ = compare(data, cmd, path)
    s = Song(data, cmd, listing=True).run(max(r) + 1)
    # sample time of each timer-A interrupt: (1024 - value) samples, the value from the captured $24 / $25 writes
    ta = [0]; v = 0x2DF; hi = None; wi = 0; t = 0
    for n in range(1, sum(1 for k in kinds if k & 1) + 2):
        while wi < len(cap) and cap[wi][0] < n:
            _, port, reg, val = cap[wi]; wi += 1
            if port == 'a' and reg == 0x24: hi = val
            if port == 'a' and reg == 0x25 and hi is not None: v = hi << 2 | val & 3
        t += 1024 - v; ta.append(t)
    T = lambda n: ta[min(n, len(ta) - 1)] + PERIOD
    A = []; j = 0; prev = None
    for na, port, reg, val in cap:
        j = j + 1 if na == prev else 0; prev = na
        A.append([int(T(na) + ISR_START + j * WRITE_COST), 0 if port == 'a' else 1, reg, val])
    starts = [r[k][1] for k in sorted(r)]
    B = []
    for k, ws in sorted(s.by_tick().items()):
        if k >= len(starts): break
        for j, (port, reg, val) in enumerate(ws):
            B.append([int(T(starts[k]) + ISR_START + j * WRITE_COST), 0 if port == 'a' else 1, reg, val])
    A.sort(key=lambda x: x[0]); B.sort(key=lambda x: x[0])
    tracks = []
    for c in s.ch:
        if not c.log: continue
        blocks, lines = [], []
        inst = ''
        for tick, pos, txt in c.log:
            lines.append([tick, pos, txt])
            w = txt.split()
            if w[0] in ('patch', 'sample'): inst = w[1]
            if w[0] in ('note', 'play', 'replay', 'fnum'):
                ln = int(re.search(r'len (\d+)', txt).group(1))
                gm = re.search(r'gate (\d+)', txt)
                dur = int(gm.group(1)) if gm else ln
                lab = w[1] if w[0] == 'note' else (w[1] if w[0] == 'play' else w[0])
                blocks.append([tick, tick + max(min(dur, ln), 1), lab, inst, len(lines) - 1])
        tracks.append({'name': ADK_TRACK.get(c.name, c.name), 'blocks': blocks, 'lines': lines})
    order = ['FM1', 'FM2', 'FM3', 'FM4', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'B']
    tracks.sort(key=lambda t: order.index(t['name']))
    tv = s.timer[0][1] if s.timer else 0x2DF
    nt = len(starts) - 1
    seq = [T(x) for x in starts]
    return dict(A=A, B=B, pre=[[0 if q == 'a' else 1, rr, vv] for q, rr, vv in pre], match=[same, total],
                tempo=s.f833, ticks_per_s=tick_hz(tv), ticks=nt, tick_irq=list(range(nt + 1)),
                irqA=seq, irqB=seq, tracks=tracks)

# --------------------------------------------------------------------------------------------------------- shared
def song(game, data, v, cmd):
    g = GAMES[game]
    d = (kof98_song if game in SNKSND else adk_song if game == 'ninjamas' else ff3_song)(g, data, cmd)
    A, B = d['A'], d['B']
    ranges = set()                                   # V ROM ranges keyed by either stream (256-byte units, end inclusive)
    for stream in (A, B):
        lat = {}
        for t, p, r, val in stream:
            lat[(p, r)] = val
            if p == 1 and r == 0 and not val & 0x80:
                for c in range(6):
                    if val >> c & 1:
                        st = lat.get((1, 0x10 + c), 0) | lat.get((1, 0x18 + c), 0) << 8
                        en = lat.get((1, 0x20 + c), 0) | lat.get((1, 0x28 + c), 0) << 8
                        ranges.add((st, en))
            if p == 0 and r == 0x10 and val & 0x80:
                st = lat.get((0, 0x12), 0) | lat.get((0, 0x13), 0) << 8
                en = lat.get((0, 0x14), 0) | lat.get((0, 0x15), 0) << 8
                ranges.add((st, en))
    merged = []
    for st, en in sorted(ranges):
        if en < st: continue
        if merged and st <= merged[-1][1] + 1: merged[-1][1] = max(merged[-1][1], en)
        else: merged.append([st, en])
    samples = [[st << 8, base64.b64encode(v[st << 8:(en + 1) << 8]).decode()] for st, en in merged]
    nbytes = sum((en - st + 1) << 8 for st, en in merged)
    print(f'A {len(A)} writes, B {len(B)} writes, {len(d["tracks"])} tracks, '
          f'{sum(len(t["blocks"]) for t in d["tracks"])} blocks, samples {nbytes >> 10} KB, identical {d["match"][0]}/{d["match"][1]}')
    return dict(d, cmd=cmd, name=g['names'].get(cmd, ''), samples=samples,
                length=max(A[-1][0] if A else 0, B[-1][0] if B else 0) + PERIOD)

if __name__ == '__main__':
    a = sys.argv[1:]
    game = 'kof98'
    if a[0] == '--game': game = a[1]; a = a[2:]
    g = GAMES[game]
    data = open(g['m1'], 'rb').read(); v = vrom(g['neo'])
    out = a[0]; os.makedirs(out, exist_ok=True)
    cmds = [int(c, 16) for c in a[1:]]
    if not cmds and game == 'ninjamas':
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'adksnd'))
        from gamesadk import music_cmds as adk_cmds
        cmds = [c for c, _, _ in adk_cmds(data)]
    elif not cmds and game in SNKSND and game != 'kof98':
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'kof98snd'))
        from games98 import music_cmds
        cmds = music_cmds(data)
    elif not cmds and game != 'kof98':
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'makoto3'))
        from games import music_cmds
        cmds = music_cmds(data)
    index = []
    for c in cmds:
        d = song(game, data, v, c)
        open(f'{out}/{d["cmd"]:02X}.json', 'w').write(json.dumps(d, separators=(',', ':')))
        index.append({k: d[k] for k in ('cmd', 'name', 'tempo', 'ticks_per_s', 'match', 'ticks')}
                     | {'seconds': round(d['length'] / 55555.56, 1), 'tracks': [t['name'] for t in d['tracks']]})
    json.dump(index, open(f'{out}/index.json', 'w'), separators=(',', ':'))
    json.dump(g['page'], open(f'{out}/game.json', 'w'), separators=(',', ':'))
