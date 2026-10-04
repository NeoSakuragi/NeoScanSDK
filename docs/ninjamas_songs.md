# Ninja Master's songs

The 36 music commands of Ninja Master's (ADK / SNK 1996), whose sound driver is ADK's "Operation System Program for
Music & Effective Sound Ver. 8.8.9" (`ninjamas_sound_driver.md`): catalogue, where each is heard, and the per-song
validation of tools/adksnd's model against the real driver. Everything is decoded by `tools/adksnd/songadk.py` from the
M1 ROM; "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/adksnd/songadk.py /data/neogeo_dict/sound/ninjamas/ninjamas_m1.bin --catalog        one line per command
    python3 tools/adksnd/songadk.py /data/neogeo_dict/sound/ninjamas/ninjamas_m1.bin 0xC7 --list      the event listing
    python3 tools/adksnd/songadk.py /data/neogeo_dict/sound/ninjamas/ninjamas_m1.bin 0xC7 --writes    the model's writes
    python3 tools/adksnd/captureadk.py --songs /data/neogeo_dict/sound/ninjamas/cap                    capture every song
    python3 tools/adksnd/regsadk.py /data/neogeo_dict/sound/ninjamas/ninjamas_m1.bin 0xC7 /data/neogeo_dict/sound/ninjamas/cap/cap_C7.txt
    python3 tools/songlab/build_web.py --game ninjamas /data/neogeo_dict/sound/songlab/all/data/ninjamas

## Catalogue

The music commands are the entries of kind `$40` in command table 2 (`$6E66`), which the driver uses for the command
after `$FC` (the game sends `FC D0` for its title): `$02`, `$C0-$CB`, `$D0-$D9`, `$E0-$EB`, `$EE` (36; the entries
`$CC-$CF`, `$DC`, `$EC`, `$ED`, `$EF` name song 0 in mode 0, whose 11 streams are `$FF` at `$32A0`: a stop,
and `$DD` song 0 in mode 1, refused after the reset: also a stop). Song = the entry's song
number and mode (0: header table `$2E20`; 1: the 2 KB window on bank n, the song in `$n x $800`; 2: the 4 KB window on
bank n, `$n x $1000`): several song numbers exist in two modes with different music (`$10`, `$11`, `$14`, `$16`,
`$17`). Tempo = the `T` value in the song (beats per minute, 48 ticks a beat; 120 when no `T`), ticks/s = 0.8 x tempo.
"One pass" = ticks until the last channel goes back to its loop point; ends = every channel reached `$FF`.
Validation = music ticks whose register writes are identical in the capture and in the model (values and order, the
tick starting on the right interrupt), and the number of captured writes compared (`ninjamas_sound_driver.md`,
"Validation").

"Heard at" comes from runs in our emulator (command logs and screenshots in `/data/neogeo_dict/sound/ninjamas/`):
`attract3` (power-on, no input, 11 minutes: only the title `$D0`, every cycle: the attract demos have no music),
`play3` (two credits, buttons mashed: four matches, lost, continued, game over), `pick` (one credit for each of ten
cursor positions on the character select: the first opponent was Goemon every time). The opponent is read from the
HUD; stage themes of opponents not met are not named.

| Cmd | Song (mode) | Tempo (ticks/s) | End | Heard at | Validation: identical ticks, compared writes |
|---|---|---|---|---|---|
| `$02` | `$02` mode 0 | 136 (108.9) | ends, 781 ticks (7.2 s) | NEO-GEO logo jingle: the game sends `$02` at frame 377 of a power-on (measured), during the BIOS logo (*inferred*) | 132 / 132, 1279 |
| `$C0` | `$15` mode 2 | 143 (114.3) | loops, one pass 7681 ticks (67.2 s) | not heard | 2041 / 2041, 16054 |
| `$C1` | `$1C` mode 0 | 120 (96.1) | loops, one pass 12289 ticks (127.9 s) | not heard | 5749 / 5749, 33508 |
| `$C2` | `$10` mode 0 | 122 (97.5) | loops, one pass 6145 ticks (63.0 s) | not heard | 2423 / 2423, 8891 |
| `$C3` | `$16` mode 2 | 80 (60.0) | loops, one pass 6821 ticks (113.7 s) | not heard | 2895 / 2895, 16941 |
| `$C4` | `$10` mode 2 | 120 (96.1) | loops, one pass 14593 ticks (151.8 s) | not heard | 6066 / 6066, 31905 |
| `$C5` | `$14` mode 2 | 120 (96.1) | loops, one pass 19201 ticks (199.8 s) | stage theme, Houoh (measured) | 8731 / 8731, 56800 |
| `$C6` | `$19` mode 0 | 132 (105.6) | loops, one pass 9997 ticks (94.7 s) | not heard | 1641 / 1641, 19640 |
| `$C7` | `$17` mode 2 | 128 (102.5) | loops, one pass 6145 ticks (60.0 s) | stage theme, Goemon (measured: first opponent of every pick) | 1638 / 1638, 11374 |
| `$C8` | `$11` mode 0 | 121 (68.1) | loops, one pass 5761 ticks (84.6 s) | stage theme, Unzen (measured) | 1468 / 1468, 14429 |
| `$C9` | `$18` mode 0 | 122 (97.5) | loops, one pass 7873 ticks (80.8 s) | stage theme, Kasumi (measured) | 560 / 560, 4265 |
| `$CA` | `$20` mode 0 | 118 (94.5) | loops, one pass 6145 ticks (65.0 s) | not heard | 1669 / 1669, 10433 |
| `$CB` | `$06` mode 0 | 145 (116.2) | loops, one pass 21313 ticks (183.4 s) | not heard | 8954 / 8954, 71158 |
| `$D0` | `$12` mode 2 | 120 (96.1) | ends, 4615 ticks (48.0 s) | title / attract, every attract cycle (measured) | 999 / 999, 5931 |
| `$D1` | `$22` mode 0 | 114 (91.1) | loops, one pass 781 ticks (8.6 s) | how to play, after a coin (measured) | 162 / 162, 2250 |
| `$D2` | `$21` mode 0 | 110 (87.9) | loops, one pass 2305 ticks (26.2 s) | character select and the VS screen before each match (measured) | 193 / 193, 2026 |
| `$D3` | `$36` mode 1 | 110 (87.9) | ends, 577 ticks (6.6 s) | sent before the select screen of a continue, cut by `$D2` 2-3 frames later (measured) | 30 / 30, 459 |
| `$D4` | `$07` mode 0 | 145 (116.2) | ends, 274 ticks (2.4 s) | not heard | 35 / 35, 199 |
| `$D5` | `$23` mode 0 | 144 (115.3) | ends, 1537 ticks (13.3 s) | continue countdown (measured) | 497 / 497, 2442 |
| `$D6` | `$35` mode 1 | 122 (104.0) | ends, 433 ticks (4.2 s) | game over (measured) | 29 / 29, 704 |
| `$D7` | `$13` mode 2 | 100 (80.1) | ends, 7201 ticks (90.0 s) | not heard | 2231 / 2231, 16529 |
| `$D8` | `$30` mode 1 | 107 (85.5) | loops, one pass 793 ticks (9.3 s) | not heard | 136 / 136, 2044 |
| `$D9` | `$31` mode 1 | 112 (89.6) | loops, one pass 769 ticks (8.6 s) | title after a game over, 30 s countdown (measured) | 122 / 122, 1543 |
| `$E0` | `$0A` mode 0 | 143 (114.3) | loops, one pass 3649 ticks (31.9 s) | not heard | 474 / 474, 5090 |
| `$E1` | `$0E` mode 0 | 118 (94.5) | ends, 3127 ticks (33.1 s) | not heard | 1018 / 1018, 5456 |
| `$E2` | `$1A` mode 0 | 122 (97.5) | loops, one pass 1540 ticks (15.8 s) | not heard | 467 / 467, 2915 |
| `$E3` | `$33` mode 1 | 96 (76.7) | loops, one pass 769 ticks (10.0 s) | not heard | 224 / 224, 3237 |
| `$E4` | `$0F` mode 0 | 71 (56.8) | loops, one pass 121 ticks (2.1 s) | not heard | 21 / 21, 386 |
| `$E5` | `$0D` mode 0 | 99 (79.1) | ends, 3868 ticks (48.9 s) | not heard | 810 / 810, 4757 |
| `$E6` | `$14` mode 0 | 143 (114.3) | loops, one pass 3459 ticks (30.3 s) | not heard | 2612 / 2612, 12800 |
| `$E7` | `$34` mode 1 | 112 (89.6) | loops, one pass 2317 ticks (25.9 s) | not heard | 457 / 457, 9175 |
| `$E8` | `$32` mode 1 | 82 (65.7) | loops, one pass 397 ticks (6.0 s) | not heard | 182 / 182, 1115 |
| `$E9` | `$0B` mode 0 | 122 (97.5) | loops, one pass 1549 ticks (15.9 s) | not heard | 420 / 420, 4521 |
| `$EA` | `$16` mode 0 | 137 (114.3) | ends, 3521 ticks (30.8 s) | not heard | 453 / 453, 5186 |
| `$EB` | `$17` mode 0 | 97 (77.6) | ends, 3265 ticks (42.1 s) | not heard | 376 / 376, 2312 |
| `$EE` | `$11` mode 2 | 120 (96.1) | loops, one pass 6913 ticks (71.9 s) | not heard | 1570 / 1570, 6996 |
| all 36 | | | | | **57485 / 57485**, 394750 |
