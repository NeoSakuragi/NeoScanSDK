# Real Bout Fatal Fury Special songs

The 27 music commands of Real Bout Fatal Fury Special (SNK 1996, MAME `rbffspec`), whose driver is SNK's `Sound Driver
Ver 1.1 96/10/01`, KOF97's build (`rbffspec_sound_driver.md`): where each is heard, and the per-song validation of
tools/kof98snd's model against the real driver. "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/rbffspec/rbffspec_m1.bin --catalog
    python3 tools/kof98snd/capture98.py --game rbffspec --songs /data/neogeo_dict/sound/rbffspec/caps
    python3 tools/kof98snd/regs98.py /data/neogeo_dict/sound/rbffspec/rbffspec_m1.bin 0x34 /data/neogeo_dict/sound/rbffspec/caps/cap_34.txt
    python3 tools/songlab/build_web.py --game rbffspec /data/neogeo_dict/sound/songlab/all/data/rbffspec

## Where the songs are heard

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`: Geolith with makoto3's port tap, pad input by frame, 68K RAM pokes, a screenshot after each music command); logs and screenshots in `/data/neogeo_dict/sound/rbffspec/attract` (power-on, no input, 40000 frames: the attract demos play without music), `run/c1` (one credit, A through the selects, the match lost), `run/ch*` (the CPU fighter's id held), `run/win*` (the opponent's health held at 1 and the buttons mashed: every match won). Bytes that follow a system command with a parameter (`$0A`, `$0E`, `$15`, `$16`, `$18-$1E`; `$14` takes two) are arguments, not songs.

The 68K's sound requests go through `$83480` (a word queue at `$10B002`, sent by `$834F0`). Measured: `$35` opening and
title, `$38` player select, `$3A` before each fight (the stage fade-in), `$37` after the final boss Krauser (Terry's
ending begins), `$32` during the ending, `$36` the ending's "Congratulation" screen, `$3B` continue, `$3C` game over.
`$3D` ends with opcode `$0C $38` (it starts the player select theme): a jingle before the select *(inferred: not heard
in these runs)*.

**The fight theme** (68K `$ADAE`): the word table `$ADEC` indexed by the CPU fighter's id (`$106A26` when the mode word
`$1041D6` is 1, `$109746` when 3, else `$106A24`); all measured by holding the id (`run/ch01-ch14`): 1 Terry `$34`,
2 Andy `$21`, 3 Joe `$22`, 4 Mai `$23`, 5 Geese `$32`, 6 Sokaku `$24`, 7 Bob `$25`, 8 Hon-Fu `$26`, 9 Blue Mary `$27`,
10 Franco `$28`, 11 Yamazaki `$29`, 12 Jin Chonshu and 13 Jin Chonrei `$2A`, 14 Duck King `$2C`, 15 Kim `$2D`, 16 Billy
`$2E`, 17 Cheng `$30`, 18 Tung `$2F`, 19 Laurence `$31`, 20 Krauser `$33`.

Every song is named.

## Catalogue

Captures: power-on, the game's commands blocked from frame 878, the song sent at frame 900, length from song98.py to
the loop point or the end + 15 %. Validation = sequencer interrupts whose register writes are identical in order.

| Cmd | Header (bank set) | Tempo (ticks/s) | End | Heard at | Validation: identical sequencer interrupts, captured writes |
|---|---|---|---|---|---|
| `$21` | `$7893` (0) | 113 (90.6) | loops | Theme: Andy | 1612 / 1612, 18510 |
| `$22` | `$88F2` (0) | 153 (122.7) | loops | Theme: Joe | 1258 / 1258, 27397 |
| `$23` | `$9705` (0) | 108 (86.6) | loops | Theme: Mai | 3605 / 3605, 24864 |
| `$24` | `$A7D1` (0) | 111 (89.0) | loops | Theme: Sokaku | 1507 / 1507, 19779 |
| `$25` | `$B708` (0) | 117 (93.8) | loops | Theme: Bob | 924 / 924, 19863 |
| `$26` | `$D9EB` (0) | 86 (69.0) | loops | Theme: Hon-Fu | 2134 / 2134, 19603 |
| `$27` | `$CBED` (0) | 83 (66.6) | loops | Theme: Blue Mary | 1249 / 1249, 16606 |
| `$28` | `$E535` (0) | 105 (84.2) | loops | Theme: Franco | 1646 / 1646, 12155 |
| `$29` | `$8000` (1) | 97 (77.8) | loops | Theme: Yamazaki | 1226 / 1226, 14549 |
| `$2A` | `$9040` (1) | 112 (89.8) | loops | Theme: Jin Chonshu / Jin Chonrei | 3706 / 3706, 29594 |
| `$2C` | `$A251` (1) | 123 (98.7) | loops | Theme: Duck King | 1309 / 1309, 10185 |
| `$2D` | `$A965` (1) | 160 (128.3) | loops | Theme: Kim | 795 / 795, 16260 |
| `$2E` | `$BB1E` (1) | 127 (101.9) | loops | Theme: Billy | 2937 / 2937, 43465 |
| `$2F` | `$D0B4` (1) | 72 (57.7) | loops | Theme: Tung | 2639 / 2639, 23008 |
| `$30` | `$DEAD` (1) | 125 (100.3) | loops | Theme: Cheng | 1414 / 1414, 14504 |
| `$31` | `$8000` (2) | 120 (96.2) | loops | Theme: Laurence | 2775 / 2775, 44567 |
| `$32` | `$8B7B` (2) | 165 (132.3) | loops | Theme: Geese (also in the ending) | 2138 / 2138, 32080 |
| `$33` | `$9B97` (2) | 27 (21.7) | loops | Theme: Krauser | 943 / 943, 8475 |
| `$34` | `$B1A0` (2) | 117 (93.8) | loops | Theme: Terry | 1100 / 1100, 19199 |
| `$35` | `$ABCF` (2) | 100 (80.2) | ends | Opening / title | 173 / 173, 2582 |
| `$36` | `$CB0F` (2) | 152 (121.9) | ends | Ending: Congratulation | 900 / 900, 17848 |
| `$37` | `$DD9C` (2) | 110 (88.2) | ends | Ending begins (after Krauser) | 63 / 63, 816 |
| `$38` | `$DF61` (2) | 110 (88.2) | loops | Player select | 235 / 235, 2617 |
| `$3A` | `$E27D` (2) | 110 (88.2) | loops | Before a fight | 125 / 125, 1563 |
| `$3B` | `$E483` (2) | 125 (100.3) | ends | Continue | 109 / 109, 1670 |
| `$3C` | `$E6F4` (2) | 125 (100.3) | ends | Game over | 16 / 16, 349 |
| `$3D` | `$E7CC` (2) | 110 (88.2) | ends | Jingle that leads into the player select ($38) | 35 / 35, 425 (chains into `$38`: compared up to it) |
| all 27 | | | | | **36573 / 36573**, 442533 |
