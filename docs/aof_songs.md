# Art of Fighting songs

The 38 music commands of Art of Fighting (SNK 1992), whose sound driver is "Ver 3.0 by MAKOTO" with KOF94's music
engine and an earlier command path (`ff3_sound_driver.md`, section "Art of Fighting's build"): catalogue, where each is
heard, and the per-song validation of tools/makoto3's model against the real driver. Everything is decoded by
`tools/makoto3/song.py` from the M1 ROM; "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/aof/aof_m1.bin --catalog          one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/aof/aof_m1.bin 0x21 --list        the event listing
    python3 tools/makoto3/capture.py --game aof --songs /data/neogeo_dict/sound/aof/cap     capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/aof/aof_m1.bin 0x21 /data/neogeo_dict/sound/aof/cap/cap_21.txt
    python3 tools/songlab/build_web.py --game aof /data/neogeo_dict/sound/songlab/all/data/aof

## Catalogue

Command map (`$565C`): music `$20-$3C`, `$40-$47`, `$5F` (38), all in bank map 0 (the M ROM is 64 KB, mirrored to
128 KB). Captures: power-on, the game's own commands blocked from frame 850 (it sends `$03` at 838, `$07` at 843 and
the opening `$29` at 1223), the song sent at frame 900, length from song.py to the loop point or the end + 15 %.
Validation = interrupts whose register writes (minus timer-flag and end-flag housekeeping) are identical in the capture
and in the model, and the number of captured writes compared.

"Heard at" comes from runs in our emulator (scripts and logs in `/data/neogeo_dict/sound/aof/scratch`, screenshots in
`attract/` and `run/`): `attract` (power-on, no input, 8 minutes), `run/p1` (one credit, Ryo, attacks mashed: beat Todoh,
lost to Jack), `run/sqN` (one credit with the 68K's stage counter, the word at `$108428`, held at N from the character
select until the next music command: the stage, its opponent and its theme start as stage N). The 68K's sound requests:
routine `$4532` (sound ID in `d0` = a byte offset into the word table `$4552`, queued as two bytes, `$00xx` sends `xx`),
`$450E` (the same, only when the ID differs from the last one). Stage themes come from the word table `$65EA` by the
stage number at `$108400`, the talk-scene themes `$30-$37` from `$FB04` by the stage counter `$108428`
(`$30 $31 $31 $32 $33 $33 $34 $35 $35 $36 $37` for counters 2-12). A static scan of the constant requests found
`$2B` (`$A108`...), `$2D` (`$F7AA`), `$2F` (`$611A`), `$3A` (`$AA92`), `$3C` (`$C5DA`), `$40` (`$ED7C`), `$43` (`$F75E`),
`$45` (`$6394`), `$29` or `$3B` by `REG_LSPCMODE` bit 3 (`$BC76`), `$2E` or `$2C` at stage counter 11 (`$10764`).

| Cmd | Header (bank) | TB (ticks/s) | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|
| `$20` | `$585D` (0) | `$B8` (48.2) | stops (`$40`), 1 ticks | no channel plays a note: a silence (*inferred*); sent before and during a bonus game (measured) | 2 / 2, 32 |
| `$21` | `$58C6` (0) | `$C0` (54.3) | loops | stage theme, Ryuhaku Todoh (stage 1; attract demo Ryo vs Todoh; measured) | 833 / 833, 13899 |
| `$22` | `$6321` (0) | `$C0` (54.3) | loops | stage theme, Jack Turner (stage 2, measured in play) | 1020 / 1020, 19536 |
| `$23` | `$6CEE` (0) | `$C0` (54.3) | loops | stage theme, Lee Pai Long (stage 4; attract demo Lee vs Robert; measured) | 763 / 763, 15755 |
| `$24` | `$75EE` (0) | `$C3` (56.9) | chains to `$24` | stage theme, King (stage 5, measured with the stage counter set) | 349 / 349, 8709 |
| `$25` | `$7CBE` (0) | `$B4` (45.7) | loops | stage theme, Micky Rogers (stage 7, measured with the stage counter set) | 1234 / 1234, 14178 |
| `$26` | `$837B` (0) | `$C2` (56.0) | loops | stage theme, John Crawley (stage 8, measured with the stage counter set) | 626 / 626, 13475 |
| `$27` | `$8C27` (0) | `$B2` (44.5) | loops | stage theme, Mr. Big (stage 10, measured with the stage counter set) | 562 / 562, 10561 |
| `$28` | `$9593` (0) | `$B9` (48.9) | loops | stage theme, Mr. Karate (stage 11, measured with the stage counter set) | 713 / 713, 13417 |
| `$29` | `$9F68` (0) | `$AB` (40.8) | stops (`$40`), 1472 ticks | opening story, attract mode (Ryo vs Jack in the bar; measured every cycle) | 307 / 307, 5607 |
| `$2A` | `$A466` (0) | `$AF` (42.9) | stops (`$40`), 2474 ticks | ending (stage counter 12, measured: "That man is our...") | 424 / 424, 6521 |
| `$2B` | `$AAE9` (0) | `$B8` (48.2) | loops | how to play, after START (measured) | 99 / 99, 1900 |
| `$2C` | `$AC69` (0) | `$BD` (51.8) | loops | map before stage 11 (Mr. Karate), instead of `$2E` (68K `$10764`, *inferred*) | 215 / 215, 4196 |
| `$2D` | `$AE17` (0) | `$B8` (48.2) | loops | bonus game (measured: the bottle cut) | 76 / 76, 1395 |
| `$2E` | `$AF5D` (0) | `$BC` (51.1) | loops | map between stages (measured) | 706 / 706, 10065 |
| `$2F` | `$B213` (0) | `$88` (28.9) | stops (`$40`), 314 ticks | continue (measured) | 73 / 73, 1947 |
| `$30` | `$B4D0` (0) | `$A6` (38.6) | loops | talk scene after beating Todoh (measured: stage counter 2) | 101 / 101, 1414 |
| `$31` | `$B61D` (0) | `$C3` (56.9) | loops | talk scene, Jack's (measured after Jack won a match); also measured before the King fight with the counter forced to 5 | 96 / 96, 1522 |
| `$32` | `$B79C` (0) | `$B8` (48.2) | loops | talk scene, 68K table `$FB04` at stage counter 5 (*inferred*: after the stage before it) | 69 / 69, 1665 |
| `$33` | `$B90B` (0) | `$B8` (48.2) | loops | talk scene, 68K table `$FB04` at stage counter 6, 7 (*inferred*: after the stage before it) | 47 / 47, 1312 |
| `$34` | `$BA7A` (0) | `$AC` (41.3) | loops | talk scene, 68K table `$FB04` at stage counter 8 (*inferred*: after the stage before it) | 145 / 145, 2576 |
| `$35` | `$BCEE` (0) | `$B8` (48.2) | loops | talk scene, 68K table `$FB04` at stage counter 9, 10 (*inferred*: after the stage before it) | 83 / 83, 998 |
| `$36` | `$BDE4` (0) | `$D0` (72.3) | loops | talk scene, 68K table `$FB04` at stage counter 11 (*inferred*: after the stage before it) | 130 / 130, 3200 |
| `$37` | `$BFAD` (0) | `$AC` (41.3) | loops | talk scene, 68K table `$FB04` at stage counter 12 (*inferred*: after the stage before it) | 99 / 99, 1134 |
| `$38` | `$C0C9` (0) | `$C8` (62.0) | stops (`$40`), 146 ticks | bonus game result, level 4 (68K table `$DF9A` by result, *inferred*) | 22 / 22, 639 |
| `$39` | `$C1E3` (0) | `$B0` (43.4) | stops (`$40`), 98 ticks | bonus game result, level 0 (68K table `$DF9A`, *inferred*) | 23 / 23, 487 |
| `$3A` | `$C2F3` (0) | `$CA` (64.3) | stops (`$40`), 194 ticks | requested at `$AA8E` (not identified) | 20 / 20, 324 |
| `$3B` | `$C406` (0) | `$AC` (41.3) | stops (`$40`), 1568 ticks | opening, played instead of `$29` when `REG_LSPCMODE` bit 3 is set (68K `$BC76`, *inferred*) | 322 / 322, 5822 |
| `$3C` | `$C949` (0) | `$AE` (42.3) | stops (`$40`), 1280 ticks | title, after a coin and after a game over (measured) | 277 / 277, 5087 |
| `$40` | `$CD76` (0) | `$A8` (39.5) | loops | requested at `$ED78` (not identified) | 93 / 93, 1740 |
| `$41` | `$CEBB` (0) | `$B8` (48.2) | loops | not heard | 127 / 127, 3035 |
| `$42` | `$D108` (0) | `$AC` (41.3) | stops (`$40`), 98 ticks | not heard | 10 / 10, 334 |
| `$43` | `$D1DD` (0) | `$B8` (48.2) | stops (`$40`), 98 ticks | bonus game select (measured) | 16 / 16, 136 |
| `$44` | `$D28D` (0) | `$C8` (62.0) | stops (`$40`), 194 ticks | bonus game over (measured; 68K table `$DF9A` levels 1-3) | 36 / 36, 521 |
| `$45` | `$D386` (0) | `$B0` (43.4) | stops (`$40`), 98 ticks | game over (measured) | 22 / 22, 359 |
| `$46` | `$D450` (0) | `$B2` (44.5) | loops | scene before the first fight (measured, every credit) | 90 / 90, 1162 |
| `$47` | `$D5C7` (0) | `$B6` (46.9) | loops | scene before the Micky fight (measured with the stage counter set to 7) | 91 / 91, 2334 |
| `$5F` | `$D6F1` (0) | `$C0` (54.3) | stops (`$40`), 386 ticks | NEO-GEO logo jingle at boot, started by command `$02` (measured: the same writes) | 259 / 259, 1917 |
| all 38 | | | | | **10180 / 10180**, 178911 |

The stage order (stage counter, measured): 1 Todoh, 2 Jack, 3 bonus game, 4 Lee, 5 King, 6 bonus game, 7 Micky, 8 John,
9 bonus game, 10 Mr. Big, 11 Mr. Karate, 12 the ending. A bonus stage plays `$20`, `$43` (select), `$2D`, `$20`, `$44`,
then `$2E` (the map) and the next stage's theme. `$24` (King) restarts itself with opcode `$47` (`capture.py` ends such a
capture after one pass + 15 %). `$41` and `$42` have no reference found in our runs or in the constant requests.
