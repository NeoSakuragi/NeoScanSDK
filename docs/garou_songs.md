# Garou: Mark of the Wolves songs

The 64 music commands of Garou: Mark of the Wolves (SNK 1999, MAME `garou`), whose sound driver is SNK's
`Sound Driver(ROM)Ver 1.8 99/08/04` (`garou_sound_driver.md`): catalogue, where each is heard, and the per-song
validation of tools/kof98snd's model against the real driver. "measured" = seen in our emulator; *(inferred)* marks the
rest.

    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/garou/garou_m1.bin --catalog
    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/garou/garou_m1.bin 0x34 --list
    python3 tools/kof98snd/capture98.py --game garou --songs /data/neogeo_dict/sound/garou/caps
    python3 tools/kof98snd/regs98.py /data/neogeo_dict/sound/garou/garou_m1.bin 0x34 /data/neogeo_dict/sound/garou/caps/cap_34.txt
    python3 tools/songlab/build_web.py --game garou /data/neogeo_dict/sound/songlab/all/data/garou

## Catalogue

Command map (`$3038`, index cmd - `$20`): music `$21-$54`, `$56-$5E`, `$60-$62` (64; `$5F` is type 2 without a song
pointer: it starts nothing). Captures: power-on, the game's own commands blocked from frame 431 (it sends `$07` at 430
and its first song `$5D` at 431; blocked commands become `$63`, see the driver doc), the song sent at frame 500,
length from song98.py to the loop point or the end + 15 %. Validation = sequencer interrupts whose register writes are
identical in order; the one difference is `$3B`'s last interrupt, which the capture cuts in the middle of the handler.

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`; logs and screenshots in `/data/neogeo_dict/sound/garou/attract` (power-on, no input,
43000 frames) and `/data/neogeo_dict/sound/garou/run/*` (one credit, Rock, no input after the select: the match is lost; `st*`: the same
with the opponent forced)). Bytes after a system command with a parameter (`$0A`, `$0E`, `$14-$1E`) are its argument.

The 68K's sound requests (`$59EAA` queue, `$59F96` via the word table `$C7000`, whose music IDs equal the commands).
**The stage theme** (`$1A3F6`): the word table `$1A40C` = `$30-$3D`, indexed by the opponent's character, the word
`$107434` (set at the versus screen). Character order from the ROM's name list (`$68046`): Terry, Rock, Dong Hwan,
Jae Hoon, Hotaru, Gato, Jenet, Marco, Hokutomaru, Freeman, Griffon, Kevin, Grant, Kain. Measured: 4 (the credit's
opponent, Hotaru) and with `$107435` forced 0, 7, 10, 13; the versus screen's song is `$40` + the opponent in those
runs (`$40`, `$44`, `$47`, `$4A`; none for Kain). Not reached: a won match (scenes after a win, endings, the boss
fights' own songs).

| Cmd | Header (bank set) | Tempo (ticks/s) | End | Heard at | Validation: identical sequencer interrupts, captured writes |
|---|---|---|---|---|---|
| `$21` | `$7480` (0) | 128 (102.7) | ends (`$06`), 6169 ticks | title over the night city, every attract cycle; after a game over (measured) | 868 / 868, 11367 |
| `$22` | `$CFAA` (2) | 135 (108.3) | loops | player select (measured) | 448 / 448, 7389 |
| `$23` | `$DA16` (2) | 142 (113.9) | ends (`$06`), 391 ticks | requested at `$40C3A` (not identified) | 61 / 61, 1064 |
| `$24` | `$9A61` (3) | 126 (101.1) | ends (`$06`), 2306 ticks | not identified | 287 / 287, 2193 |
| `$25` | `$9D58` (3) | 130 (104.3) | ends (`$06`), 3841 ticks | not identified | 401 / 401, 3664 |
| `$26` | `$A2D1` (3) | 134 (107.5) | ends (`$06`), 2113 ticks | not identified | 216 / 216, 1748 |
| `$27` | `$A6D1` (3) | 134 (107.5) | ends (`$06`), 5213 ticks | not identified | 972 / 972, 3737 |
| `$28` | `$ABA1` (3) | 128 (102.7) | loops | not identified | 73 / 73, 854 |
| `$29` | `$AD68` (3) | 128 (102.7) | loops | not identified | 395 / 395, 4330 |
| `$2A` | `$B434` (3) | 116 (93.0) | loops | not identified | 652 / 652, 6257 |
| `$2B` | `$BAEA` (3) | 104 (83.4) | loops | not identified | 227 / 227, 2901 |
| `$2C` | `$8937` (3) | 122 (97.9) | loops | continue (measured) | 134 / 134, 5256 |
| `$2D` | `$DC82` (2) | 115 (92.2) | loops | not identified | 562 / 562, 5969 |
| `$2E` | `$83BB` (0) | 128 (102.7) | ends (`$06`), 7251 ticks | not identified | 961 / 961, 12589 |
| `$2F` | `$E7B6` (2) | 172 (138.0) | loops | not identified | 262 / 262, 4259 |
| `$30` | `$93AC` (0) | 143 (114.7) | loops | stage theme of Terry Bogard (table `$1A40C` [0]; measured with the opponent `$107434` set) | 1261 / 1261, 20811 |
| `$31` | `$A47A` (0) | 150 (120.3) | loops | stage theme of Rock Howard (table `$1A40C` [1]; stage table); an attract demo on this stage (measured) | 1813 / 1813, 18282 |
| `$32` | `$B729` (0) | 179 (143.6) | loops | stage theme of Kim Dong Hwan (table `$1A40C` [2]; stage table) | 4396 / 4396, 43147 |
| `$33` | `$CBCB` (0) | 150 (120.3) | loops | stage theme of Kim Jae Hoon (table `$1A40C` [3]; stage table) | 1419 / 1419, 15472 |
| `$34` | `$DB94` (0) | 124 (99.5) | loops | stage theme of Hotaru Futaba (table `$1A40C` [4]; measured with the opponent `$107434` set) | 1879 / 1879, 18803 |
| `$35` | `$8000` (1) | 66 (52.9) | loops | stage theme of Gato (table `$1A40C` [5]; stage table) | 604 / 604, 7848 |
| `$36` | `$8C07` (1) | 105 (84.2) | loops | stage theme of B. Jenet (table `$1A40C` [6]; stage table) | 2194 / 2194, 26231 |
| `$37` | `$A1D3` (1) | 126 (101.1) | loops | stage theme of Marco Rodriguez (table `$1A40C` [7]; measured with the opponent `$107434` set); an attract demo on this stage (measured) | 1574 / 1574, 17538 |
| `$38` | `$B771` (1) | 146 (117.1) | loops | stage theme of Hokutomaru (table `$1A40C` [8]; stage table); an attract demo on this stage (measured) | 3091 / 3091, 36044 |
| `$39` | `$CFA2` (1) | 170 (136.4) | loops | stage theme of Freeman (table `$1A40C` [9]; stage table) | 2246 / 2246, 16171 |
| `$3A` | `$E029` (1) | 115 (92.2) | loops | stage theme of Griffon (table `$1A40C` [10]; measured with the opponent `$107434` set) | 743 / 743, 13272 |
| `$3B` | `$8000` (2) | 118 (94.6) | loops | stage theme of Kevin Rian (table `$1A40C` [11]; stage table); an attract demo on this stage (measured) | 3407 / 3408, 36609 |
| `$3C` | `$9D8E` (2) | 108 (86.6) | loops | stage theme of Grant (table `$1A40C` [12]; stage table) | 1590 / 1590, 20110 |
| `$3D` | `$B171` (2) | 80 (64.2) | loops | stage theme of Kain R. Heinlein (table `$1A40C` [13]; measured with the opponent `$107434` set) | 1369 / 1369, 7341 |
| `$3E` | `$BC21` (2) | 122 (97.9) | loops | not identified | 1609 / 1609, 15424 |
| `$3F` | `$E3C1` (2) | 123 (98.7) | loops | how to play, after a coin (measured) | 348 / 348, 3690 |
| `$40` | `$C541` (3) | 60 (48.1) | ends (`$06`), 437 ticks | versus screen before a fight with Terry Bogard, *inferred* from `$40` + opponent (measured) | 7 / 7, 25 |
| `$41` | `$C586` (3) | 100 (80.2) | loops | versus screen before a fight with Rock Howard, *inferred* from `$40` + opponent | 84 / 84, 430 |
| `$42` | `$C683` (3) | 109 (87.4) | loops | versus screen before a fight with Kim Dong Hwan, *inferred* from `$40` + opponent | 412 / 412, 1574 |
| `$43` | `$C8B8` (3) | 109 (87.4) | loops | versus screen before a fight with Kim Jae Hoon, *inferred* from `$40` + opponent | 32 / 32, 260 |
| `$44` | `$C92A` (3) | 100 (80.2) | ends (`$06`), 775 ticks | versus screen before a fight with Hotaru (measured: Rock x Hotaru) | 22 / 22, 90 |
| `$45` | `$C9B2` (3) | 93 (74.6) | loops | versus screen before a fight with Gato, *inferred* from `$40` + opponent | 8 / 8, 60 |
| `$46` | `$CA0E` (3) | 85 (68.2) | ends (`$06`), 1059 ticks | versus screen before a fight with B. Jenet, *inferred* from `$40` + opponent | 9 / 9, 34 |
| `$47` | `$CA66` (3) | 100 (80.2) | loops | versus screen before a fight with Marco Rodriguez, *inferred* from `$40` + opponent (measured) | 36 / 36, 294 |
| `$48` | `$CAEA` (3) | 60 (48.1) | loops | versus screen before a fight with Hokutomaru, *inferred* from `$40` + opponent | 34 / 34, 87 |
| `$49` | `$CB9B` (3) | 100 (80.2) | loops | versus screen before a fight with Freeman, *inferred* from `$40` + opponent | 10 / 10, 76 |
| `$4A` | `$CC0A` (3) | 85 (68.2) | loops | versus screen before a fight with Griffon, *inferred* from `$40` + opponent (measured) | 5 / 5, 37 |
| `$4B` | `$CC53` (3) | 100 (80.2) | loops | versus screen before a fight with Kevin Rian, *inferred* from `$40` + opponent | 47 / 47, 367 |
| `$4C` | `$8E11` (3) | 109 (87.4) | loops | game over and the save screen (measured) | 10 / 10, 150 |
| `$4D` | `$8ED8` (3) | 109 (87.4) | loops | not identified | 27 / 27, 203 |
| `$4E` | `$EAD0` (2) | 108 (86.6) | ends (`$06`), 1177 ticks | not identified | 138 / 138, 2082 |
| `$4F` | `$8000` (3) | 135 (108.3) | loops | not identified | 376 / 376, 7428 |
| `$50` | `$CCF6` (3) | 93 (74.6) | loops | not identified | 5 / 5, 37 |
| `$51` | `$CD3F` (3) | 100 (80.2) | loops | not identified | 26 / 26, 230 |
| `$52` | `$CDBE` (3) | 109 (87.4) | loops | not identified | 338 / 338, 1380 |
| `$53` | `$CF4E` (3) | 109 (87.4) | loops | not identified | 10 / 10, 84 |
| `$54` | `$CFA6` (3) | 100 (80.2) | loops | not identified | 34 / 34, 263 |
| `$56` | `$D031` (3) | 73 (58.6) | loops | not identified | 5 / 5, 37 |
| `$57` | `$D07A` (3) | 100 (80.2) | loops | not identified | 30 / 30, 261 |
| `$58` | `$D0EE` (3) | 100 (80.2) | loops | not identified | 41 / 41, 380 |
| `$59` | `$D168` (3) | 100 (80.2) | loops | not identified | 8 / 8, 68 |
| `$5A` | `$D1C0` (3) | 85 (68.2) | loops | not identified | 5 / 5, 37 |
| `$5B` | `$D209` (3) | 100 (80.2) | loops | not identified | 46 / 46, 359 |
| `$5C` | `$BFF1` (3) | 150 (120.3) | loops | not identified | 392 / 392, 3269 |
| `$5D` | `$7FD1` (0) | 80 (64.2) | ends (`$06`), 2401 ticks | intro ("Certainly, they existed...") after the SNK logo, every attract cycle; the game's first song at boot (measured) | 144 / 144, 1978 |
| `$5E` | `$8FB9` (0) | 80 (64.2) | ends (`$06`), 2785 ticks | not identified | 148 / 148, 2000 |
| `$60` | `$8FCC` (3) | 130 (104.3) | loops | not identified | 594 / 594, 6605 |
| `$61` | `$94B2` (3) | 111 (89.0) | loops | end of a match: the K.O. and the winner's scene (measured) | 270 / 270, 3578 |
| `$62` | `$9984` (3) | 100 (80.2) | loops | requested at `$1A4E8` (not identified) | 71 / 71, 412 |
| all 64 | | | | | **39486 / 39487**, 424545 |
