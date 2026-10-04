# Art of Fighting 3 songs

The 30 music commands of Art of Fighting 3: The Path of the Warrior (SNK 1996), whose sound driver is KOF95's reworked
build of "Ver 3.0 by MAKOTO" extended with per-channel ADPCM-A sample tables (opcode `$3C`), 6-byte sample records and
FF3's three bank maps (`ff3_sound_driver.md`, section "Art of Fighting 3's build"): catalogue, where each is heard, and
the per-song validation of tools/makoto3's model against the real driver. Everything is decoded by
`tools/makoto3/song.py` from the M1 ROM; "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/aof3/aof3_m1.bin --catalog          one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/aof3/aof3_m1.bin 0x24 --list        the event listing
    python3 tools/makoto3/capture.py --game aof3 --songs /data/neogeo_dict/sound/aof3/cap     capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/aof3/aof3_m1.bin 0x24 /data/neogeo_dict/sound/aof3/cap/cap_24.txt
    python3 tools/songlab/build_web.py --game aof3 /data/neogeo_dict/sound/songlab/all/data/aof3

## Catalogue

Command map (`$5F5E`): music `$20-$28`, `$2A-$3D`, `$5F` (30; `$29` has type 0). Captures: power-on, the game's own
commands blocked from frame 880 (it sends `$03 $03 $07` at 864-869 and again at 870-874, the opening `$21` at 1116),
the song sent at frame 900, length from song.py to the loop point or the end + 15 %. Validation = interrupts whose
register writes (minus timer-flag and end-flag housekeeping) are identical in the capture and in the model, and the
number of captured writes compared.

"Heard at" comes from runs in our emulator (scripts and logs in `/data/neogeo_dict/sound/aof3/scratch`, screenshots in
`attract/` and `run/`): `attract` (power-on, no input, 8 minutes), `run/p1`, `run/t1`, `run/win` (one credit, Robert,
attacks mashed; the runs are not repeatable, *inferred*: the game reads the calendar), `run/stN` (one credit with the
stage number, the word at `$104BEA`, held at N from the player select until the next music command: stage N + 1 of
Robert's path, its opponent and its theme), `run/ryoN` (the same with the player's character `$104C0C` set to 1, Ryo).
The 68K's sound requests go through `$30404` (sound ID in `d0`, a long of up to four command bytes from the table
`$3051C`, zero bytes skipped), `$303E2` (only when the ID differs from the last one) and `$303F4`. **A stage's theme
depends on the player's character and the stage number**: the long table `$CE28` (by the player's character: `$104C0C` when the byte
`$104BD6` is 1, else `$104C0E`) points at a row of nine theme IDs in `$CE50`, indexed by the stage number
`$104BEA` (stub `$CDE4`); Robert's row (character 0) is `$24 $28 $2A $2C $2E $26 $2D $23 $2B` against Rody, Wang, Jin,
Sinclair, Kasumi, Lenny, Karman, Ryo, Wyler (measured), Ryo's `$28 $23 $2E $26 $25 $2A $24 $27 $2B`; when the word
`$104BD6` is `$0101` the theme comes from the table `$CE0C` by `$104BE8` instead (both players in, *inferred*). Characters (`$104C0E` measured on screen): 0
Robert, 1 Ryo, 2 Karman, 3 Kasumi, 4 Rody, 5 Lenny, 6 Wang, 7 Jin, 8 Sinclair, 9 Wyler.

| Cmd | Header (bank) | TB (ticks/s) | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|
| `$20` | `$615F` (0) | `$80` (27.1) | stops (`$40`), 98 ticks | no channel plays a note: a silence (*inferred*) | 5 / 5, 71 |
| `$21` | `$6204` (0) | `$B0` (43.4) | stops (`$40`), 986 ticks | opening, attract mode (measured every cycle) | 312 / 312, 5267 |
| `$22` | `$674A` (0) | `$8B` (29.7) | loops | requested by the 68K's scene stub `$CD06` (not identified) | 358 / 358, 5636 |
| `$23` | `$8000` (1) | `$B9` (48.9) | loops | stage theme: Robert's stage 8 (vs Ryo), Ryo's stage 2 (vs Wang) (measured) | 798 / 798, 13852 |
| `$24` | `$8CEF` (1) | `$B7` (47.6) | loops | stage theme: Robert's stage 1 (vs Rody, the train yard) (measured) | 560 / 560, 16150 |
| `$25` | `$9D1B` (1) | `$B0` (43.4) | loops | stage theme: Ryo's stage 5 (vs Jin, railway at night); attract demo Kasumi vs Jin (measured) | 440 / 440, 6974 |
| `$26` | `$A59C` (1) | `$CB` (65.5) | loops | stage theme: Robert's stage 6 (vs Lenny) (measured) | 661 / 661, 11417 |
| `$27` | `$AC2A` (1) | `$BA` (49.6) | loops | stage theme: Ryo's stage 8 (vs Robert) (measured) | 2137 / 2137, 27489 |
| `$28` | `$C003` (1) | `$AF` (42.9) | loops | stage theme: Robert's stage 2 (vs Wang), Ryo's stage 1 (vs Rody); attract demo Robert vs Ryo (measured) | 1803 / 1803, 26414 |
| `$2A` | `$D573` (1) | `$B8` (48.2) | loops | stage theme: Robert's stage 3 (vs Jin) (measured) | 2482 / 2482, 31505 |
| `$2B` | `$6CD1` (0) | `$BF` (53.4) | loops | stage theme: the final stage (vs Wyler) (measured) | 1127 / 1127, 15991 |
| `$2C` | `$7A83` (0) | `$BF` (53.4) | loops | stage theme: Robert's stage 4 (vs Sinclair) (measured); in attract mode from the end of the first demo over "Today's Ranking" (measured) | 952 / 952, 18221 |
| `$2D` | `$8675` (0) | `$9A` (34.0) | loops | stage theme: Robert's stage 7 (vs Karman) (measured) | 1285 / 1285, 20428 |
| `$2E` | `$93A6` (0) | `$A0` (36.2) | loops | stage theme: Robert's stage 5 (vs Kasumi) (measured) | 498 / 498, 2680 |
| `$2F` | `$97EE` (0) | `$B0` (43.4) | stops (`$40`), 248 ticks | scene after a match, won or lost (measured) | 32 / 32, 327 |
| `$30` | `$992A` (0) | `$A5` (38.2) | loops | player select (measured) | 460 / 460, 7847 |
| `$31` | `$9F4E` (0) | `$B7` (47.6) | loops | requested by the 68K's pre-fight stub `$CD52` before stages 1-8 (`$2E` instead when `$104BE6` = 5; not heard in our runs) | 123 / 123, 957 |
| `$32` | `$A0C3` (0) | `$A3` (37.3) | loops | jingle before stages 2 and up, cut by the stage theme (measured) | 82 / 82, 860 |
| `$33` | `$A1CC` (0) | `$7C` (26.3) | stops (`$40`), 482 ticks | continue (measured) | 44 / 44, 810 |
| `$34` | `$A3CF` (0) | `$B9` (48.9) | stops (`$40`), 146 ticks | requested at `$15F8E` (not identified) | 48 / 48, 416 |
| `$35` | `$A557` (0) | `$8B` (29.7) | stops (`$40`), 2594 ticks | requested by the scene stub `$CD10` (`$39` instead when `$104BD8` is set; not identified) | 745 / 745, 8492 |
| `$36` | `$AC05` (0) | `$C0` (54.3) | loops | scene before the final stage, Robert's (measured; the 68K table `$CD86` by the player's character: `$36` for 7 of 10) | 50 / 50, 973 |
| `$37` | `$AD8E` (0) | `$B9` (48.9) | loops | scene before the final stage, Kasumi's and Jin's (68K table `$CD86` by the player's character, *inferred*) | 167 / 167, 3738 |
| `$38` | `$B14C` (0) | `$C0` (54.3) | loops | scene before the final stage, Karman's (68K table `$CD86`, *inferred*) | 103 / 103, 2061 |
| `$39` | `$B3D7` (0) | `$8B` (29.7) | stops (`$40`), 2978 ticks | requested by the scene stub `$CD10` instead of `$35` (not identified) | 833 / 833, 9444 |
| `$3A` | `$BAB9` (0) | `$B0` (43.4) | stops (`$40`), 1178 ticks | requested at `$42DD8` (not identified) | 367 / 367, 6107 |
| `$3B` | `$C0A4` (0) | `$B9` (48.9) | stops (`$40`), 290 ticks | requested at `$15C9E` (not identified) | 31 / 31, 586 |
| `$3C` | `$C23F` (0) | `$7C` (26.3) | stops (`$40`), 98 ticks | game over (measured) | 12 / 12, 226 |
| `$3D` | `$C30D` (0) | `$B0` (43.4) | loops | title / how to play, after a coin and after a game over (measured) | 160 / 160, 2671 |
| `$5F` | `$C627` (0) | `$C0` (54.3) | stops (`$40`), 386 ticks | NEO-GEO logo jingle at boot, started by command `$02` (measured: the same writes) | 259 / 259, 1917 |
| all 30 | | | | | **16934 / 16934**, 249527 |

Not reached in our runs: the ending (every run lost to Wyler or earlier: player 1's life was not found in RAM), so
`$22`, `$31`, `$34`, `$35`, `$37-$3B` are named only from their requests in the 68K code, where at all. Every song but
`$20` and `$5F` starts its ADPCM-A channels with opcode `$3C $1A` (table `$440F`, 6-byte records); since the driver
keeps a channel's table across songs, `$20` would play with whatever table the song before it set (it plays no note).
