# Samurai Shodown III songs

The 34 music commands of Samurai Shodown III (SNK 1995, MAME `samsho3`), whose sound driver is Art of Fighting 3's build of "Ver 3.0 by MAKOTO" with KOF95's per-octave ADPCM-B mode back (`ff3_sound_driver.md`, section "Samurai Shodown III's build"): catalogue, where each is heard, and the per-song validation of tools/makoto3's model against the real driver. "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/samsho3/samsho3_m1.bin --catalog          one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/samsho3/samsho3_m1.bin 0x21 --list        the event listing
    python3 tools/makoto3/capture.py --game samsho3 --songs /data/neogeo_dict/sound/samsho3/caps     capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/samsho3/samsho3_m1.bin 0x21 /data/neogeo_dict/sound/samsho3/caps/cap_21.txt
    python3 tools/songlab/build_web.py --game samsho3 /data/neogeo_dict/sound/songlab/all/data/samsho3


## Catalogue

Command map (`$60F7`): music `$20-$40`, `$5F` (34). Captures: power-on, the game's own commands blocked from frame 880 (it sends `$03 $03 $07` at 864-872 and its first song `$3C` at 930), the song sent at frame 900, length from song.py to the loop point or the end + 15 %.

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`: the Geolith core with makoto3's port tap, pad input by frame,
68K RAM pokes and watches, a screenshot 90 and 400 frames after each music command; logs and screenshots in
`/data/neogeo_dict/sound/samsho3/attract` (power-on, no input, 43000 frames) and `/data/neogeo_dict/sound/samsho3/run/*` (one credit, the first character, no
input after the select: the match is lost; `st*`: the same with the stage byte forced)). Bytes that follow a system
command taking a parameter (`$0A`, `$0E`, `$14`, `$15`, `$16`, `$18-$1E`) are that command's argument, not a song: the logs mark them.

The 68K's sound requests go through the word table `$185A4` (`$18582`; `$1853E` only when the ID differs from the
last). **Before a fight** (`$622BE`): `$31`, or `$3A` when the stage word `$109068` is 13; then **the stage theme**: the
word table `$622FE` indexed by `$109068 & 15`. Index order = the ROM's name list (`$31B00`): Haohmaru, Nakoruru,
Rimururu, Hanzo, Galford, Kyoshiro, Ukyo, Genjuro, Basara, Yaiba (Shizumaru), Gaira, Amakusa, Kuroko, Zankuro,
Mamahaha, Shikite. Measured: 4 (the credit's opponent, Galford, set at the pre-fight screen), 6 (attract demo), and with
the low byte `$109069` forced 0, 2, 9, 11, 13 (14 plays nothing; 15's entry is `$20`). Not reached: a won match.


| Cmd | Header (bank) | TB (ticks/s) | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|
| `$20` | `$62F8` (0) | `$B0` (43.4) | stops (`$40`), 2 ticks | silence: sent at the KO (measured; no channel plays a note, *inferred*) | 3 / 3, 33 |
| `$21` | `$8000` (1) | `$B9` (48.9) | loops | stage theme, stage 0 (Haohmaru) (measured) | 1752 / 1752, 16149 |
| `$22` | `$8F60` (1) | `$60` (21.7) | loops | stage theme, stage 6 (Ukyo) (measured); the attract demo (Ukyo vs Galford) (measured) | 1027 / 1027, 8722 |
| `$23` | `$9430` (1) | `$B6` (46.9) | loops | stage theme, stage 4 (Galford) (measured) | 1203 / 1203, 25321 |
| `$24` | `$6355` (0) | `$B7` (47.6) | loops | stage theme, stage 1 (Nakoruru) (stage table) | 1224 / 1224, 18280 |
| `$25` | `$70C7` (1) | `$95` (32.5) | loops | stage theme, stage 7 (Genjuro) (stage table) | 834 / 834, 9791 |
| `$26` | `$77AA` (0) | `$71` (24.3) | loops | stage theme, stage 5 (Kyoshiro) (stage table) | 653 / 653, 5427 |
| `$27` | `$A688` (1) | `$87` (28.7) | loops | stage theme, stage 3 (Hanzo) (stage table) | 1648 / 1648, 14494 |
| `$28` | `$7DE3` (0) | `$B9` (48.9) | loops | stage theme, stage 8 (Basara) (stage table) | 1281 / 1281, 22346 |
| `$29` | `$B064` (1) | `$90` (31.0) | loops | stage theme, stage 10 (Gaira) (stage table) | 336 / 336, 2935 |
| `$2A` | `$915A` (0) | `$AB` (40.8) | loops | stage theme, stage 9 (Shizumaru ("YAIBA")) (measured) | 1114 / 1114, 7005 |
| `$2B` | `$9507` (0) | `$B9` (48.9) | loops | stage theme, stage 2 (Rimururu) (measured) | 898 / 898, 14200 |
| `$2C` | `$A411` (0) | `$BF` (53.4) | loops | stage theme, stage 12 (Kuroko) (stage table) | 1764 / 1764, 23916 |
| `$2D` | `$B3A2` (1) | `$B1` (44.0) | loops | stage theme, stage 11 (Amakusa) (measured) | 950 / 950, 11584 |
| `$2E` | `$B16E` (0) | `$A1` (36.5) | loops | stage theme, stage 13 (Zankuro) (measured) | 630 / 630, 4618 |
| `$2F` | `$B5E1` (0) | `$B9` (48.9) | loops | requested at `$D30E` (not identified) | 788 / 788, 11336 |
| `$30` | `$BB4C` (1) | `$B6` (46.9) | loops | player select and level choice (measured); ID `$30D` | 294 / 294, 3244 |
| `$31` | `$C0E8` (0) | `$B9` (48.9) | stops (`$40`), 377 ticks | before each fight, the "En garde" screen; also in the attract demo (measured); ID `$30E` | 104 / 104, 1030 |
| `$32` | `$C312` (0) | `$B9` (48.9) | stops (`$40`), 775 ticks | result of a round ("Conclusion") (measured) | 95 / 95, 1007 |
| `$33` | `$C474` (0) | `$C5` (58.9) | stops (`$40`), 769 ticks | winner's quote after a lost match (measured); ID `$310` | 353 / 353, 4349 |
| `$34` | `$C7C3` (0) | `$B9` (48.9) | stops (`$40`), 448 ticks | requested at `$B316` (not identified) | 100 / 100, 1152 |
| `$35` | `$BD7C` (1) | `$B6` (46.9) | stops (`$40`), 1044 ticks | requested at `$B9EA` (not identified) | 162 / 162, 1564 |
| `$36` | `$C9B8` (0) | `$A3` (37.3) | stops (`$40`), 1298 ticks | requested at `$C7EA` (not identified) | 222 / 222, 2873 |
| `$37` | `$C0A0` (1) | `$86` (28.5) | stops (`$40`), 1095 ticks | requested at `$C11A` (not identified) | 312 / 312, 3180 |
| `$38` | `$CD76` (0) | `$C5` (58.9) | stops (`$40`), 290 ticks | not identified | 29 / 29, 201 |
| `$39` | `$CE93` (0) | `$A1` (36.5) | stops (`$40`), 578 ticks | not identified | 78 / 78, 976 |
| `$3A` | `$D021` (0) | `$B9` (48.9) | stops (`$40`), 307 ticks | before the fight with Zankuro instead of `$31` (code `$622C2`; measured with the stage word at 13) | 101 / 101, 1074 |
| `$3B` | `$C3DC` (1) | `$BC` (51.1) | loops | requested at `$E50E` (not identified) | 2125 / 2125, 39756 |
| `$3C` | `$D1B1` (0) | `$B9` (48.9) | stops (`$40`), 1220 ticks | opening ("To have no fear...") and title, every attract cycle; title after a game over (measured) | 268 / 268, 2735 |
| `$3D` | `$D610` (0) | `$B9` (48.9) | stops (`$40`), 194 ticks | requested from the per-character code at `$62000-$6DD00` (endings, *inferred*) | 16 / 16, 132 |
| `$3E` | `$D713` (0) | `$B9` (48.9) | stops (`$40`), 98 ticks | continue, through the game over (measured); ID `$341` | 16 / 16, 168 |
| `$3F` | `$D800` (0) | `$B9` (48.9) | stops (`$40`), 98 ticks | requested at `$83C4`, `$AAAE`, `$11FD0` (not identified) | 12 / 12, 103 |
| `$40` | `$D8AE` (0) | `$73` (24.6) | stops (`$40`), 2114 ticks | requested at `$DFA0` (not identified) | 751 / 751, 9729 |
| `$5F` | `$DD8D` (0) | `$C0` (54.3) | stops (`$40`), 386 ticks | NEO-GEO logo jingle at boot: system command `$02` plays it (measured: all 1915 of its writes, in order, in the boot capture, plus SSG writes) | 259 / 259, 1917 |
| all 34 | | | | | **21402 / 21402**, 271347 |

