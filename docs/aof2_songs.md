# Art of Fighting 2 songs

The 42 music commands of Art of Fighting 2 (SNK 1994), whose sound driver is KOF94's build of "Ver 3.0 by MAKOTO"
instruction for instruction, with its own tables (`ff3_sound_driver.md`, section "Art of Fighting 2's build"):
catalogue, where each is heard, and the per-song validation of tools/makoto3's model against the real driver. Everything
is decoded by `tools/makoto3/song.py` from the M1 ROM; "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/aof2/aof2_m1.bin --catalog          one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/aof2/aof2_m1.bin 0x26 --list        the event listing
    python3 tools/makoto3/capture.py --game aof2 --songs /data/neogeo_dict/sound/aof2/cap     capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/aof2/aof2_m1.bin 0x26 /data/neogeo_dict/sound/aof2/cap/cap_26.txt
    python3 tools/songlab/build_web.py --game aof2 /data/neogeo_dict/sound/songlab/all/data/aof2

## Catalogue

Command map (`$6993`): music `$20-$36`, `$40-$4E`, `$50-$52`, `$5F` (42). Captures: power-on, the game's own commands
blocked from frame 850 (it sends `$07` at 843 and the opening `$29` at 1365), the song sent at frame 900, length from
song.py to the loop point or the end + 15 %. Validation = interrupts whose register writes (minus timer-flag and
end-flag housekeeping) are identical in the capture and in the model, and the number of captured writes compared.

"Heard at" comes from runs in our emulator (scripts and logs in `/data/neogeo_dict/sound/aof2/scratch`, screenshots in
`attract/` and `run/`): `attract` (power-on, no input, 8 minutes), `run/p1` (one credit, Ryo, lost the first match),
`run/opN` (one credit with the opponent's character, the word at `$1093E2`, held at N until the stage theme),
`run/win2` (the whole one-player mode with Ryo: player 1's life byte `$1092ED` held at 96 and player 2's `$1093ED` at
1, every match won on time; 13 opponents, three bonus games, Geese, the ending, the staff roll; then a second credit).
The 68K's sound requests go through `$09BA` (sound ID = a byte offset into the word table `$09DA`, queued as two bytes)
and `$098A` (only when the ID differs from the last one). The stage theme comes from the word table `$9F1A` by the
opponent's character (`$108400`, copied from `$1093E2`, 1-13: Ryo, Robert, Eiji, Jack, Lee, King, Micky, John, Mr. Big,
Takuma, Yuri, Temjin, Geese), with Robert's and Micky's intros `$45`, `$46` before them; the attract demos use the table
`$9F46` (`$28` and `$50` without the intros); at stage counter 17 (`$108428`) the 68K sends `$35` instead (`$F6D2C`). The
endings `$47-$4C` come from the table `$11092` by the player's character (`$11082`, after `$03` and `$07`).

| Cmd | Header (bank) | TB (ticks/s) | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|
| `$20` | `$6B94` (0) | `$B8` (48.2) | stops (`$40`), 1 ticks | no channel plays a note: a silence (*inferred*); sent before a bonus game (measured) | 2 / 2, 32 |
| `$21` | `$8000` (1) | `$B2` (44.5) | loops | stage theme, Mr. Big (opponent 9, measured) | 746 / 746, 16503 |
| `$22` | `$8DBD` (1) | `$BF` (53.4) | loops | stage theme, Lee Pai Long (opponent 5, measured) | 1142 / 1142, 18705 |
| `$23` | `$97CA` (1) | `$BA` (49.6) | loops | stage theme, Takuma Sakazaki (opponent 10, measured) | 569 / 569, 10284 |
| `$24` | `$A1AC` (1) | `$BD` (51.8) | loops | stage theme, John Crawley (opponent 8, measured) | 995 / 995, 20639 |
| `$25` | `$AC82` (1) | `$BC` (51.1) | loops | stage theme, Eiji Kisaragi (opponent 3, measured) | 648 / 648, 17370 |
| `$26` | `$B53D` (1) | `$C2` (56.0) | loops | stage theme, Ryo Sakazaki (opponent 1, measured; attract demo Ryo vs Takuma) | 1024 / 1024, 20855 |
| `$27` | `$6BFD` (0) | `$C0` (54.3) | loops | stage theme, Yuri Sakazaki (opponent 11, measured) | 2522 / 2522, 41028 |
| `$28` | `$C4E7` (1) | `$C2` (56.0) | loops | stage theme, Robert Garcia, after its intro `$45` (opponent 2, measured; attract demo Yuri vs Robert without the intro) | 1255 / 1255, 23242 |
| `$29` | `$77CB` (0) | `$B6` (46.9) | stops (`$40`), 1922 ticks | opening story, attract mode (measured every cycle) | 339 / 339, 6385 |
| `$2A` | `$8002` (0) | `$AA` (40.4) | stops (`$40`), 6620 ticks | staff roll ("Presented by SNK", measured after the ending) | 1316 / 1316, 25911 |
| `$2B` | `$8FB2` (0) | `$A4` (37.7) | loops | bonus game, Super Haoh Shoko-ken (measured) | 13 / 13, 1670 |
| `$2C` | `$9050` (0) | `$A4` (37.7) | loops | requested at `$18D2C`... (not identified) | 26 / 26, 1807 |
| `$2D` | `$9119` (0) | `$C8` (62.0) | stops (`$40`), 146 ticks | bonus game over (measured after the strength-training bonus game) | 14 / 14, 414 |
| `$2E` | `$920E` (0) | `$B8` (48.2) | stops (`$40`), 194 ticks | bonus game over (measured after the Haoh Shoko-ken bonus game) | 32 / 32, 669 |
| `$2F` | `$9343` (0) | `$B4` (45.7) | stops (`$40`), 98 ticks | game over (measured) | 8 / 8, 126 |
| `$30` | `$93DE` (0) | `$B1` (44.0) | loops | stage theme, Jack Turner (opponent 4, measured) | 1024 / 1024, 19810 |
| `$31` | `$A192` (0) | `$B5` (46.3) | loops | stage theme, King (opponent 6, measured) | 778 / 778, 14265 |
| `$32` | `$A722` (0) | `$80` (27.1) | loops | requested at `$1785E` (not identified) | 14 / 14, 623 |
| `$33` | `$A7AF` (0) | `$B8` (48.2) | stops (`$40`), 98 ticks | bonus game select (measured) | 8 / 8, 326 |
| `$34` | `$A879` (0) | `$BC` (51.1) | loops | ending scene, Geese ("I have invested too much...", measured) | 140 / 140, 1456 |
| `$35` | `$AA78` (0) | `$BD` (51.8) | loops | Geese defeated (stage counter 17, `$F6D2C`; measured) | 352 / 352, 2863 |
| `$36` | `$ABD1` (0) | `$B6` (46.9) | loops | title / how to play, after a coin and after a game over (measured) | 167 / 167, 3934 |
| `$40` | `$AE99` (0) | `$B6` (46.9) | loops | between matches, the South Town map (measured) | 124 / 124, 1695 |
| `$41` | `$B036` (0) | `$B9` (48.9) | loops | player select (measured) | 73 / 73, 1985 |
| `$42` | `$B227` (0) | `$C5` (58.9) | stops (`$40`), 625 ticks | continue (measured) | 77 / 77, 1792 |
| `$43` | `$B465` (0) | `$B6` (46.9) | loops | bonus game, strength training (measured) | 103 / 103, 1913 |
| `$44` | `$D6E8` (1) | `$B6` (46.9) | loops | not heard | 81 / 81, 1725 |
| `$45` | `$B68A` (0) | `$B5` (46.3) | loops | intro of Robert's stage theme (measured: `$28` follows 75 frames later) | 263 / 263, 4500 |
| `$46` | `$B87B` (0) | `$AE` (42.3) | loops | intro of Micky's stage theme (measured: `$50` follows 98 frames later) | 60 / 60, 878 |
| `$47` | `$B977` (0) | `$A8` (39.5) | loops | ending, Eiji's (68K table `$11092` by the player's character, *inferred*) | 63 / 63, 462 |
| `$48` | `$BAAC` (0) | `$CC` (66.8) | loops | ending, Ryo's (measured; also Robert's, Yuri's and Temjin's in the 68K table `$11092`, *inferred*) | 144 / 144, 3547 |
| `$49` | `$BD0C` (0) | `$AE` (42.3) | loops | ending, Jack's, Mr. Big's and Geese's (68K table `$11092`, *inferred*) | 92 / 92, 2236 |
| `$4A` | `$BE71` (0) | `$BF` (53.4) | loops | ending, Micky's and John's (68K table `$11092`, *inferred*) | 105 / 105, 2379 |
| `$4B` | `$BFC2` (0) | `$B0` (43.4) | loops | ending, King's and Takuma's (68K table `$11092`, *inferred*) | 153 / 153, 2728 |
| `$4C` | `$C274` (0) | `$B2` (44.5) | loops | ending, Lee's (68K table `$11092`, *inferred*) | 91 / 91, 1050 |
| `$4D` | `$C35A` (0) | `$B2` (44.5) | loops | scene before the Geese fight (measured) | 172 / 172, 2544 |
| `$4E` | `$C4C0` (0) | `$B8` (48.2) | loops | bonus game title card (measured) | 65 / 65, 1222 |
| `$50` | `$D888` (1) | `$BC` (51.1) | loops | stage theme, Micky Rogers, after its intro `$46` (opponent 7, measured) | 1144 / 1144, 22933 |
| `$51` | `$E9E4` (1) | `$B6` (46.9) | loops | stage theme, Temjin (opponent 12, measured) | 863 / 863, 13014 |
| `$52` | `$C642` (0) | `$CA` (64.3) | loops | stage theme, Geese Howard (opponent 13, measured) | 1199 / 1199, 30261 |
| `$5F` | `$D689` (0) | `$C0` (54.3) | stops (`$40`), 386 ticks | NEO-GEO logo jingle at boot, started by command `$02` (measured: the same writes) | 259 / 259, 1917 |
| all 42 | | | | | **18265 / 18265**, 347698 |

The one-player order measured with Ryo: Ryo, Yuri, Jack, bonus game (strength training: `$33` select, `$4E` title card,
`$20`, `$43`, `$2D`), Lee, Robert, King, bonus game, Micky, Eiji, John, bonus game (Haoh Shoko-ken: `$33`, `$4E`, `$20`,
`$2B`, `$2E`), Temjin, Takuma, Mr. Big, `$4D`, Geese, `$35`, `$34`, `$48`, `$2A`. `$40` plays between matches. `$2C` and
`$32` have constant requests (`$18D2C`, `$18D6C`, `$18DB2`; `$1785E`) not reached in our runs.
