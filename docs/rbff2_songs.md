# Real Bout Fatal Fury 2 songs

The 35 music commands of Real Bout Fatal Fury 2: The Newcomers (SNK 1998, MAME `rbff2`), whose driver is SNK's `Sound
Driver(ROM)Ver 1.6 97/12/08` (`rbff2_sound_driver.md`): where each is heard, and the per-song validation of
tools/kof98snd's model against the real driver. "measured" = seen in our emulator.

    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/rbff2/rbff2_m1.bin --catalog
    python3 tools/kof98snd/capture98.py --game rbff2 --songs /data/neogeo_dict/sound/rbff2/caps
    python3 tools/kof98snd/regs98.py /data/neogeo_dict/sound/rbff2/rbff2_m1.bin 0x30 /data/neogeo_dict/sound/rbff2/caps/cap_30.txt
    python3 tools/songlab/build_web.py --game rbff2 /data/neogeo_dict/sound/songlab/all/data/rbff2

## Where the songs are heard

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`: Geolith with makoto3's port tap, pad input by frame, 68K RAM pokes, a screenshot after each music command); logs and screenshots in `/data/neogeo_dict/sound/rbff2/attract` (power-on, no input, 40000 frames: the attract demos play without music), `run/c1` (one credit, A through the selects, the match lost), `run/ch*` (the CPU fighter's id held), `run/win*` (the opponent's health held at 1 and the buttons mashed: every match won). Bytes that follow a system command with a parameter (`$0A`, `$0E`, `$15`, `$16`, `$18-$1E`; `$14` takes two) are arguments, not songs.

The game sends `$20` (all off) before each song. Measured: `$21` opening and title (attract loop), `$22` the title after
a coin, `$23` how to play, `$24` player select, `$26` before the first fight of the credit (Terry against Andy; not heard in
the one-credit run, which pressed A at that moment), `$2A` before a fight with both sides the same fighter (the `run/ch*` runs), `$2B` continue,
`$29` game over, `$2F` Terry's ending ("Congratulations").

**The fight theme** (68K `$F6C0`): the word table `$F6F4` indexed by the CPU fighter's id (`$107BA6` when the mode word
`$1041D6` is 1, `$10A8D4` when 3, else `$107BA4`); all measured by holding the id (`run/ch01-ch17`): 1 Terry `$30`, 2 Andy
`$31`, 3 Joe `$32`, 4 Mai `$33`, 5 Geese `$34`, 6 Sokaku `$35`, 7 Bob `$36`, 8 Hon-Fu `$37`, 9 Blue Mary `$38`, 10 Franco
`$39`, 11 Yamazaki `$3A`, 12 Jin Chonshu and 13 Jin Chonrei `$3B`, 14 Duck King `$3C`, 15 Kim `$3D`, 16 Billy `$3E`,
17 Cheng `$3F`, 18 Tung `$40`, 19 Laurence `$41`, 20 Krauser `$42`, 21 Rick `$43`, 22 Li Xiangfei `$44`, 23 Alfred `$45`.

Not identified: `$25`, `$27`, `$28`, `$2D` (not reached in these runs).

## Catalogue

Captures: power-on, the game's commands blocked from frame 914 (blocked commands become `$46`), the song sent at frame
940, length from song98.py to the loop point or the end + 15 %. Validation = sequencer interrupts whose register writes
are identical in order.

| Cmd | Header (bank set) | Tempo (ticks/s) | End | Heard at | Validation: identical sequencer interrupts, captured writes |
|---|---|---|---|---|---|
| `$21` | `$7F92` (0) | 90 (72.2) | ends | Opening / title | 263 / 263, 1455 |
| `$22` | `$82B9` (0) | 90 (72.2) | loops | Title after a coin | 110 / 110, 488 |
| `$23` | `$83CA` (0) | 105 (84.2) | loops | How to play | 98 / 98, 914 |
| `$24` | `$8532` (0) | 145 (116.3) | loops | Player select | 216 / 216, 3447 |
| `$25` | `$8768` (0) | 171 (137.2) | loops | not identified | 178 / 178, 4545 |
| `$26` | `$8B49` (0) | 190 (152.4) | ends | Before a fight (Terry vs Andy) | 76 / 76, 787 |
| `$27` | `$8D1D` (0) | 190 (152.4) | ends | not identified | 61 / 61, 661 |
| `$28` | `$8EB9` (0) | 129 (103.5) | loops | not identified | 136 / 136, 1621 |
| `$29` | `$920F` (0) | 134 (107.5) | ends | Game over | 19 / 19, 130 |
| `$2A` | `$92A3` (0) | 190 (152.4) | ends | Before a fight (mirror match) | 65 / 65, 684 |
| `$2B` | `$9444` (0) | 134 (107.5) | ends | Continue | 185 / 185, 2272 |
| `$2D` | `$9935` (0) | 145 (116.3) | loops | not identified | 253 / 253, 4016 |
| `$2F` | `$9C6D` (0) | 151 (121.1) | loops | Ending (Terry) | 1193 / 1193, 16834 |
| `$30` | `$B252` (0) | 117 (93.8) | loops | Theme: Terry | 1101 / 1101, 19239 |
| `$31` | `$CC5D` (0) | 106 (85.0) | loops | Theme: Andy | 1687 / 1688, 19373 (the capture ends inside the last interrupt) |
| `$32` | `$8000` (1) | 153 (122.7) | loops | Theme: Joe | 1258 / 1258, 27397 |
| `$33` | `$8E11` (1) | 108 (86.6) | loops | Theme: Mai | 2704 / 2704, 22906 |
| `$34` | `$9F6C` (1) | 165 (132.3) | loops | Theme: Geese | 2138 / 2138, 32175 |
| `$35` | `$AF1C` (1) | 111 (89.0) | loops | Theme: Sokaku | 1507 / 1507, 19742 |
| `$36` | `$C02A` (1) | 117 (93.8) | loops | Theme: Bob | 925 / 925, 19869 |
| `$37` | `$CD8A` (1) | 86 (69.0) | loops | Theme: Hon-Fu | 2134 / 2134, 19603 |
| `$38` | `$8000` (2) | 83 (66.6) | loops | Theme: Blue Mary | 1400 / 1400, 18710 |
| `$39` | `$9F4D` (2) | 105 (84.2) | loops | Theme: Franco | 1645 / 1645, 12181 |
| `$3A` | `$B0E4` (2) | 97 (77.8) | loops | Theme: Yamazaki | 1224 / 1224, 14533 |
| `$3B` | `$C133` (2) | 112 (89.8) | loops | Theme: Jin Chonshu / Jin Chonrei | 3712 / 3712, 29639 |
| `$3C` | `$D27C` (2) | 123 (98.7) | loops | Theme: Duck King | 1307 / 1307, 10095 |
| `$3D` | `$D978` (2) | 160 (128.3) | loops | Theme: Kim | 796 / 796, 16268 |
| `$3E` | `$8000` (3) | 127 (101.9) | loops | Theme: Billy | 2940 / 2940, 43430 |
| `$3F` | `$93E5` (3) | 125 (100.3) | loops | Theme: Cheng | 1420 / 1420, 14554 |
| `$40` | `$B5F0` (3) | 72 (57.7) | loops | Theme: Tung | 2643 / 2643, 23039 |
| `$41` | `$A959` (3) | 120 (96.2) | loops | Theme: Laurence | 2777 / 2777, 44576 |
| `$42` | `$D143` (3) | 27 (21.7) | loops | Theme: Krauser | 943 / 943, 8443 |
| `$43` | `$8000` (4) | 123 (98.7) | loops | Theme: Rick | 1353 / 1353, 14022 |
| `$44` | `$99E1` (4) | 141 (113.1) | loops | Theme: Li Xiangfei | 2736 / 2736, 26117 |
| `$45` | `$B653` (4) | 136 (109.1) | loops | Theme: Alfred | 1263 / 1263, 17431 |
| all 35 | | | | | **42466 / 42467**, 511196 |
