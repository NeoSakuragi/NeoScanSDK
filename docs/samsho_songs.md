# Samurai Shodown songs

The 33 music commands of Samurai Shodown (SNK 1993, MAME `samsho`), whose sound driver is KOF94's build of "Ver 3.0 by MAKOTO" with other tables (`ff3_sound_driver.md`, section "Samurai Shodown's build"): catalogue, where each is heard, and the per-song validation of tools/makoto3's model against the real driver. Everything is decoded by `tools/makoto3/song.py` from the M1 ROM; "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/samsho/samsho_m1.bin --catalog          one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/samsho/samsho_m1.bin 0x21 --list        the event listing
    python3 tools/makoto3/capture.py --game samsho --songs /data/neogeo_dict/sound/samsho/caps     capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/samsho/samsho_m1.bin 0x21 /data/neogeo_dict/sound/samsho/caps/cap_21.txt
    python3 tools/songlab/build_web.py --game samsho /data/neogeo_dict/sound/songlab/all/data/samsho


## Catalogue

Command map (`$59C2`): music `$20-$2A`, `$2C`, `$2D`, `$2F`, `$31`, `$35`, `$40-$46`, `$50-$58`, `$5F` (33). Captures: power-on, the game's own commands blocked from frame 850 (it sends `$07` at 847 and its first song `$27` at 858), the song sent at frame 900, length from song.py to the loop point or the end + 15 %. Validation = interrupts whose register writes (minus timer-flag and end-flag housekeeping) are identical in the capture and in the model, and the number of captured writes compared.

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`: the Geolith core with makoto3's port tap, pad input by frame,
68K RAM pokes and watches, a screenshot 90 and 400 frames after each music command; logs and screenshots in
`/data/neogeo_dict/sound/samsho/attract` (power-on, no input, 43000 frames) and `/data/neogeo_dict/sound/samsho/run/*` (one credit, the first character, no
input after the select: the match is lost; `st*`: the same with the stage byte forced)). Bytes that follow a system
command taking a parameter (`$0A`, `$0E`, `$14`, `$15`, `$18-$1C`) are that command's argument, not a song: the logs mark them.

The 68K's sound requests: a sound ID (word) indexes the table `$2B816` (words `[byte][byte]`, sent in that order, 0 and
1 skipped) through `$2B7F4`; `$2B7A0` requests only when the ID differs from the last one (`$10F100`). **The stage
theme** (`$2B760`) is the word table `$2B744` indexed by the stage byte `$100A8A` (index 13 when the stage is 12,
Amakusa, `$100A8E` is set and the player block's round count is below 2). The game's own debug stage menu (`$20420`)
names the stages: pointers `$204C8`, `HAOHMARU STAGE` ... `AMAKUSA STAGE`, `BONUS STAGE` (0-13). Measured: stage 1
(the first credit's opponent, Nakoruru) and, with the byte forced at the map screen, 0, 5, 11, 12, 13; stage 7 came in
another credit. Not reached: a won match (the life value was not found: the bytes that follow the life bar are copies the
game rewrites), so the scenes after a win, the endings and the bonus game are named from their request sites only.


| Cmd | Header (bank) | TB (ticks/s) | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|
| `$20` | `$5BC3` (0) | `$B0` (43.4) | stops (`$40`), 3 ticks | no channel plays a note: a silence (*inferred*) | 3 / 3, 154 |
| `$21` | `$5C38` (0) | `$B9` (48.9) | loops | stage theme, stage 0 "HAOHMARU STAGE"; the attract demo (Haohmaru vs Ukyo) (measured) | 1389 / 1389, 10325 |
| `$22` | `$6948` (0) | `$B9` (48.9) | loops | stage theme, stage 5 "UKYO STAGE" (measured) | 1253 / 1253, 8903 |
| `$23` | `$7249` (0) | `$C0` (54.3) | loops | stage theme, stage 7 "GENAN STAGE" (measured) | 541 / 541, 4518 |
| `$24` | `$78B2` (0) | `$B0` (43.4) | loops | stage theme, stage 9 "JUBEI STAGE" (stage table) | 196 / 196, 1165 |
| `$25` | `$7C0A` (0) | `$D3` (77.2) | loops | stage theme, stage 4 "OHKOU STAGE" (Wan-Fu) (stage table) | 888 / 888, 10907 |
| `$26` | `$8804` (0) | `$CE` (69.4) | loops | stage theme, stage 13 "BONUS STAGE" (measured with the stage byte at 13); also Amakusa's stage when `$100A8E` is set and the player's round count is below 2 (code `$2B774`, *inferred*) | 3196 / 3196, 40842 |
| `$27` | `$9560` (0) | `$CF` (70.9) | stops (`$40`), 2690 ticks | title and attract mode, every cycle (measured); ID `$1DD`, requested at `$2DAAE` | 434 / 434, 3156 |
| `$28` | `$9C02` (0) | `$D0` (72.3) | loops | stage theme, stage 8 "EARTHQUAKE STAGE" (stage table) | 1129 / 1129, 16866 |
| `$29` | `$AB32` (0) | `$D2` (75.5) | loops | requested by the game-flow state at `$1472` (not identified) | 596 / 596, 6482 |
| `$2A` | `$B2C6` (0) | `$C1` (55.1) | loops | stage theme, stage 12 "AMAKUSA STAGE" (measured) | 593 / 593, 8296 |
| `$2C` | `$B349` (0) | `$A5` (38.2) | stops (`$40`), 385 ticks | winner's scene after a lost match (measured); `$2FB6C` | 33 / 33, 486 |
| `$2D` | `$8000` (1) | `$BA` (49.6) | stops (`$40`), 7681 ticks | character chosen: the journey map (measured); requested at `$137A`, `$13D0` | 1012 / 1012, 15165 |
| `$2F` | `$B493` (0) | `$C1` (55.1) | stops (`$40`), 660 ticks | requested by the game-flow states at `$1426` and `$14B2` (`$56` instead when the stage counter `$100A93` is 12: before Amakusa, *inferred*) | 74 / 74, 692 |
| `$31` | `$B768` (0) | `$C3` (56.9) | stops (`$40`), 401 ticks | the opponent's challenge on the map before a fight (measured) | 33 / 33, 384 |
| `$35` | `$81CC` (1) | `$CF` (70.9) | stops (`$40`), 2258 ticks | after a coin, over the player select (measured); ID `$233`, `$2F514` | 359 / 359, 2648 |
| `$40` | `$B87B` (0) | `$C7` (60.9) | loops | stage theme, stage 3 "GALFORD STAGE" (stage table) | 1003 / 1003, 21008 |
| `$41` | `$CF72` (0) | `$95` (32.5) | loops | stage theme, stage 2 "HANZO STAGE" (stage table) | 206 / 206, 6884 |
| `$42` | `$8696` (1) | `$BE` (52.6) | loops | stage theme, stage 1 "NAKORURU STAGE" (measured) | 1053 / 1053, 14179 |
| `$43` | `$DB80` (0) | `$B9` (48.9) | loops | stage theme, stage 10 "TAM-TAM STAGE" (stage table) | 1214 / 1214, 19654 |
| `$44` | `$E543` (0) | `$C9` (63.1) | loops | stage theme, stage 6 "KYOSIRO STAGE" (stage table; also requested at `$40104`) | 548 / 548, 11484 |
| `$45` | `$9215` (1) | `$9E` (35.4) | loops | stage theme, stage 11 "CHARLOTTE STAGE" (measured) | 386 / 386, 10605 |
| `$46` | `$9B84` (1) | `$90` (31.0) | stops (`$40`), 1538 ticks | requested at `$43634` (not identified) | 247 / 247, 6781 |
| `$50` | `$A1FF` (1) | `$C1` (55.1) | loops | requested at `$339C0` (not identified) | 2073 / 2073, 28147 |
| `$51` | `$AE74` (1) | `$B9` (48.9) | stops (`$40`), 956 ticks | requested at `$3B01E` (not identified) | 213 / 213, 2031 |
| `$52` | `$B172` (1) | `$B6` (46.9) | loops | in the ID table (`$21C`), no request found (not identified) | 627 / 627, 8678 |
| `$53` | `$B95B` (1) | `$C5` (58.9) | stops (`$40`), 770 ticks | continue (measured); `$2CC3E` | 356 / 356, 4653 |
| `$54` | `$BD9C` (1) | `$C5` (58.9) | stops (`$40`), 194 ticks | game over (measured); `$162C` | 24 / 24, 496 |
| `$55` | `$EE2A` (0) | `$C5` (58.9) | stops (`$40`), 566 ticks | requested by the game-flow state at `$15C0` (not identified) | 50 / 50, 558 |
| `$56` | `$F052` (0) | `$C1` (55.1) | stops (`$40`), 492 ticks | requested at `$14C0` instead of `$2F` when the stage counter `$100A93` is 12 (not identified) | 57 / 57, 1050 |
| `$57` | `$BEF1` (1) | `$B9` (48.9) | stops (`$40`), 1473 ticks | requested at `$30388` (`$58` there when `$100AB2` is set; not identified) | 399 / 399, 6594 |
| `$58` | `$C287` (1) | `$B9` (48.9) | stops (`$40`), 1526 ticks | requested at `$3037C` (not identified) | 415 / 415, 6603 |
| `$5F` | `$F414` (0) | `$C0` (54.3) | stops (`$40`), 386 ticks | NEO-GEO logo jingle at boot: system command `$02` plays it (measured: all 1915 of its writes, in order, in the boot capture, plus SSG writes) | 259 / 259, 1917 |
| all 33 | | | | | **20859 / 20859**, 282311 |

