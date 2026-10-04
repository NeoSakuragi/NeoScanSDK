# Samurai Shodown II songs

The 39 music commands of Samurai Shodown II (SNK 1994, MAME `samsho2`), whose sound driver is KOF94's music engine of "Ver 3.0 by MAKOTO", moved, with more effect code (`ff3_sound_driver.md`, section "Samurai Shodown II's build"): catalogue, where each is heard, and the per-song validation of tools/makoto3's model against the real driver. "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/samsho2/samsho2_m1.bin --catalog          one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/samsho2/samsho2_m1.bin 0x21 --list        the event listing
    python3 tools/makoto3/capture.py --game samsho2 --songs /data/neogeo_dict/sound/samsho2/caps     capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/samsho2/samsho2_m1.bin 0x21 /data/neogeo_dict/sound/samsho2/caps/cap_21.txt
    python3 tools/songlab/build_web.py --game samsho2 /data/neogeo_dict/sound/songlab/all/data/samsho2


## Catalogue

Command map (`$6C4A`): music `$20-$3D`, `$40-$47`, `$5F` (39). Captures: power-on, the game's own commands blocked from frame 850 (it sends `$07` at 847 and its first song `$2D` at 861), the song sent at frame 900, length from song.py to the loop point or the end + 15 %. Several songs keep A4-A6 in a rest loop of 12240 ticks, which sets their capture length (`$41`: 204283 interrupts); the music itself loops sooner (`$23`: 3816 ticks).

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`: the Geolith core with makoto3's port tap, pad input by frame,
68K RAM pokes and watches, a screenshot 90 and 400 frames after each music command; logs and screenshots in
`/data/neogeo_dict/sound/samsho2/attract` (power-on, no input, 43000 frames) and `/data/neogeo_dict/sound/samsho2/run/*` (one credit, the first character, no
input after the select: the match is lost; `st*`: the same with the stage byte forced)). Bytes that follow a system
command taking a parameter (`$0A`, `$0E`, `$14`, `$15`, `$18-$1E`) are that command's argument, not a song: the logs mark them.

The 68K's sound requests go through the word table `$5FD2` (`$5FB0`; `$5F8A` only when the ID differs from the last).
**The stage theme** (`$DCB2`): the byte table `$DCF8` (18 IDs) indexed by the stage byte `$100AD9`, which the game sets
at the player select to the CPU opponent's character. Character order from the ROM's name list (`$2452E`): Haohmaru,
Nakoruru, Hanzo, Galford, Wan-Fu, Ukyo, Kyoshiro, Gen-an, Earthquake, Jubei, Tam Tam, Charlotte, Genjuro, Cham Cham,
Neinhalt Sieger, Nicotine, Mizuki, Kuroko. Measured: 4 (the credit's opponent, Wan-Fu), and with the byte forced at the
select 0, 9, 12, 15, 16, 17; Tam Tam's entry is 0 (ID 0 is `$03 $01`, two system commands: no stage theme). Not
reached: a won match (scenes after a win, endings).


| Cmd | Header (bank) | TB (ticks/s) | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|
| `$20` | `$6E4B` (0) | `$B0` (43.4) | stops (`$40`), 2 ticks | silence: sent at a coin and at a KO (measured; no channel plays a note, *inferred*) | 3 / 3, 33 |
| `$21` | `$6EA8` (0) | `$B9` (48.9) | loops | stage theme, stage 0 (Haohmaru) (measured); the attract demo (Haohmaru vs Genjuro) (measured) | 4940 / 4940, 42751 |
| `$22` | `$7B26` (0) | `$B2` (44.5) | loops | stage theme, stage 5 (Ukyo) (stage table) | 3241 / 3241, 22335 |
| `$23` | `$8180` (0) | `$AB` (40.8) | loops | stage theme, stage 8 (Earthquake) (stage table) | 4531 / 4531, 75447 |
| `$24` | `$9256` (0) | `$B0` (43.4) | loops | stage theme, stage 16 (Mizuki) (measured) | 3333 / 3333, 58065 |
| `$25` | `$A2B6` (0) | `$B9` (48.9) | loops | stage theme, stage 1 (Nakoruru) (stage table) | 2542 / 2542, 45301 |
| `$26` | `$B06E` (0) | `$C4` (57.9) | loops | stage theme, stage 3 (Galford) (stage table) | 3236 / 3236, 52012 |
| `$27` | `$C30A` (0) | `$A9` (39.9) | loops | stage theme, stage 17 (Kuroko) (measured) | 3680 / 3680, 85660 |
| `$28` | `$8000` (1) | `$B9` (48.9) | loops | stage theme, stage 12 (Genjuro) (measured) | 3048 / 3048, 23216 |
| `$29` | `$D0A9` (0) | `$A8` (39.5) | loops | stage theme, stage 9 (Jubei) (measured) | 2496 / 2496, 17188 |
| `$2A` | `$D559` (0) | `$A1` (36.5) | loops | stage theme, stage 15 (Nicotine) (measured) | 1810 / 1810, 15224 |
| `$2B` | `$DC98` (0) | `$D3` (77.2) | loops | stage theme, stage 4 (Wan-Fu) (measured) | 2457 / 2457, 31076 |
| `$2C` | `$87F6` (1) | `$B6` (46.9) | loops | stage theme, stage 7 (Gen-an) (stage table) | 4479 / 4479, 28453 |
| `$2D` | `$E8C2` (0) | `$B9` (48.9) | stops (`$40`), 2744 ticks | title and attract mode, every cycle (measured); ID `$0C9` | 585 / 585, 4996 |
| `$2E` | `$8CE9` (1) | `$B9` (48.9) | stops (`$40`), 225 ticks | before each fight, under "En garde" (measured) | 58 / 58, 596 |
| `$2F` | `$8E38` (1) | `$B9` (48.9) | stops (`$40`), 775 ticks | end of a round (the "Victory" scene) (measured); ID `$0D0`, `$7764` | 107 / 107, 1020 |
| `$30` | `$8F85` (1) | `$A8` (39.5) | loops | stage theme, stage 6 (Kyoshiro) (stage table) | 899 / 899, 12112 |
| `$31` | `$992D` (1) | `$95` (32.5) | loops | stage theme, stage 2 (Hanzo) (stage table) | 278 / 278, 2986 |
| `$32` | `$9E55` (1) | `$9E` (35.4) | loops | stage theme, stage 11 (Charlotte) (stage table) | 772 / 772, 13454 |
| `$33` | `$AA19` (1) | `$C4` (57.9) | loops | stage theme, stage 14 (Neinhalt Sieger) (stage table) | 921 / 921, 14758 |
| `$34` | `$B774` (1) | `$B9` (48.9) | loops | stage theme, stage 13 (Cham Cham) (stage table) | 1171 / 1171, 25311 |
| `$35` | `$CA3A` (1) | `$B9` (48.9) | stops (`$40`), 352 ticks | winner's quote after a lost match (measured); ID `$0D1`, `$170FC` | 76 / 76, 1190 |
| `$36` | `$CBC2` (1) | `$B9` (48.9) | stops (`$40`), 1189 ticks | requested at `$185E8` (not identified) | 253 / 253, 2354 |
| `$37` | `$CEDC` (1) | `$B9` (48.9) | stops (`$40`), 590 ticks | requested at `$196B6` (not identified) | 177 / 177, 1509 |
| `$38` | `$D0B5` (1) | `$B6` (46.9) | loops | player select, then the opening story text (measured); ID `$0D4`, requested at `$1C76`, `$1D5E` | 3886 / 3886, 41696 |
| `$39` | `$EF8D` (0) | `$94` (32.2) | loops | not identified | 72 / 72, 587 |
| `$3A` | `$D2BB` (1) | `$B4` (45.7) | loops | not identified | 153 / 153, 1782 |
| `$3B` | `$D42A` (1) | `$A0` (36.2) | loops | requested at `$1A3F4`, `$1BA10` (not identified) | 162 / 162, 2480 |
| `$3C` | `$D612` (1) | `$9C` (34.7) | stops (`$40`), 386 ticks | the opening story over flames, after the player select (measured) | 75 / 75, 1178 |
| `$3D` | `$D7E5` (1) | `$A7` (39.0) | loops | not identified | 85 / 85, 1022 |
| `$40` | `$F05C` (0) | `$A1` (36.5) | loops | not identified | 1915 / 1915, 19296 |
| `$41` | `$F19B` (0) | `$B6` (46.9) | loops | requested at `$1C430` (not identified) | 10322 / 10322, 204283 |
| `$42` | `$D92B` (1) | `$C5` (58.9) | stops (`$40`), 769 ticks | continue (measured); ID `$307`, `$11CB2` | 355 / 355, 4715 |
| `$43` | `$F2FE` (0) | `$B7` (47.6) | stops (`$40`), 597 ticks | requested at `$1C280` (not identified) | 68 / 68, 753 |
| `$44` | `$DC54` (1) | `$C1` (55.1) | loops | requested at `$22FB0` (not identified) | 2186 / 2186, 44572 |
| `$45` | `$E79D` (1) | `$B9` (48.9) | stops (`$40`), 1285 ticks | requested at `$21C9A` (not identified) | 256 / 256, 2329 |
| `$46` | `$F465` (0) | `$C5` (58.9) | stops (`$40`), 193 ticks | game over (measured) | 10 / 10, 193 |
| `$47` | `$EA43` (1) | `$C5` (58.9) | stops (`$40`), 217 ticks | not identified | 42 / 42, 721 |
| `$5F` | `$F525` (0) | `$C0` (54.3) | stops (`$40`), 386 ticks | NEO-GEO logo jingle at boot: system command `$02` plays it (measured: all 1915 of its writes, in order, in the boot capture, plus SSG writes) | 259 / 259, 1917 |
| all 39 | | | | | **64939 / 64939**, 904571 |

