# KOF97 songs

The 41 music commands of The King of Fighters '97 (SNK 1997, MAME `kof97`), whose sound driver is SNK's
`Sound Driver Ver 1.1 96/10/01 To SNK` (`kof97_sound_driver.md`): catalogue, where each is heard, and the per-song
validation of tools/kof98snd's model against the real driver. "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/kof97/kof97_m1.bin --catalog
    python3 tools/kof98snd/capture98.py --game kof97 --songs /data/neogeo_dict/sound/kof97/caps
    python3 tools/kof98snd/regs98.py /data/neogeo_dict/sound/kof97/kof97_m1.bin 0x40 /data/neogeo_dict/sound/kof97/caps/cap_40.txt
    python3 tools/songlab/build_web.py --game kof97 /data/neogeo_dict/sound/songlab/all/data/kof97

## Where the songs are heard

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`): `/data/neogeo_dict/sound/kof97/attract`
(power-on, no input, 43000 frames), `run/c1` (one credit, A pressed through the selects, the match lost), `run/ch*`
(the CPU team's fighters held at one character id), `run/st*` (the stage number held). Measured: `$21` opening and
title, `$3A` how-to-play screen after a coin, `$23` team and order select, `$25` world map before a stage, `$2C`
continue, `$30-$35` in the attract demo and the credit, `$41`, `$42`, `$34`, `$4A`, `$4B` with the RAM held.

The 68K: a sound ID indexes the word table `$A15C6` (IDs `$21-$51` send the music command of the same number; `$1A` /
`$1B` / `$1C` + code are voice and hit effects), queued at `$108000+$593E` and sent at `$76CE`. **The fight theme**
(`$69B8A`, by the mode byte `$10A846`): the CPU side's team record (`$10A847` / `$10A858` by bit 0 of `$10A7F2`;
`+4..+6` fighters, `+3` the current one via the order at `+$0A`) gives the current fighter's id; the byte table `$69F78`
(`$69F98` when the team byte `+1` is not 7, New Face) maps it to an entry of the word table `$69FB8`: Kyo `$40`,
Iori `$41` (measured), Shingo `$42` (measured), Athena `$43`, Yashiro / Shermie / Chris `$44` (`$4A` when the record's
`+$10` is set), Terry `$45`, Yamazaki `$46`, Mary `$47`, Billy `$48`. Any other fighter: the stage number `$10A7EA` indexes
`$69FCE`: 0 `$30`, 1 `$35`, 2 `$31`, 3 `$32`, 4 `$33`, 5 `$34`, 6 `$4A`, 7 `$4B` (all measured). With `$10EC35` set the
theme is `$2F` (`$10A846` < 5) or `$49` *(inferred: the mode it stands for is not identified)*.

## Catalogue

Command map (`$2FB0`, index cmd - `$20`): music `$21-$3A`, `$40-$4C`, `$50`, `$51`. Captures: power-on, the game's own
commands blocked from frame 878, the song sent at frame 900, length from song98.py to the loop point or the end + 15 %.
Validation = sequencer interrupts whose register writes are identical in order; the one difference is `$27`'s last
interrupt, which the capture cuts in the middle of the handler.

| Cmd | Header (bank set) | Tempo (ticks/s) | End | Heard at | Validation: identical sequencer interrupts, captured writes |
|---|---|---|---|---|---|
| `$21` | `$DCDE` (0) | 81 (65.0) | ends (`$06`), 3087 ticks | Opening / title | 535 / 535, 6435 |
| `$22` | `$7C25` (0) | 110 (88.2) | ends (`$06`), 673 ticks | not identified | 68 / 68, 801 |
| `$23` | `$92D3` (0) | 140 (112.3) | loops | Team and order select | 168 / 168, 2209 |
| `$24` | `$7F2D` (0) | 120 (96.2) | loops | not identified | 98 / 98, 680 |
| `$25` | `$7E03` (0) | 120 (96.2) | ends (`$06`), 387 ticks | World map before a stage | 62 / 62, 482 |
| `$26` | `$CF19` (1) | 100 (80.2) | loops | not identified | 83 / 83, 812 |
| `$27` | `$982D` (0) | 100 (80.2) | loops | not identified | 1434 / 1435, 14196 |
| `$28` | `$E781` (1) | 90 (72.2) | loops | not identified | 904 / 904, 5309 |
| `$29` | `$DF4C` (1) | 80 (64.2) | loops | not identified | 841 / 841, 6733 |
| `$2A` | `$D8DA` (1) | 138 (110.7) | loops | not identified | 566 / 566, 5767 |
| `$2B` | `$D149` (1) | 84 (67.4) | loops | not identified | 880 / 880, 9122 |
| `$2C` | `$9521` (0) | 115 (92.2) | ends (`$06`), 1165 ticks | Continue | 186 / 186, 1799 |
| `$2D` | `$F31E` (0) | 120 (96.2) | loops | not identified | 494 / 494, 3683 |
| `$2E` | `$D079` (1) | 110 (88.2) | loops | not identified | 8 / 8, 59 |
| `$2F` | `$D0EC` (1) | 120 (96.2) | loops | not identified | 13 / 13, 100 |
| `$30` | `$8BE9` (2) | 110 (88.2) | loops | fight theme, stage 0 (arena; attract demo, measured) | 230 / 230, 969 |
| `$31` | `$8E21` (2) | 110 (88.2) | loops | fight theme, stage 2 (Bali village; attract demo, measured) | 403 / 403, 4351 |
| `$32` | `$918A` (2) | 110 (88.2) | loops | fight theme, stage 3 (Chinese street festival; attract demo, measured) | 128 / 128, 786 |
| `$33` | `$92BC` (2) | 120 (96.2) | loops | fight theme, stage 4 (Korean palace; attract demo, measured) | 1704 / 1704, 2748 |
| `$34` | `$973C` (2) | 90 (72.2) | loops | fight theme, stage 5 (seaside city) | 42 / 42, 415 |
| `$35` | `$9805` (2) | 84 (67.4) | loops | fight theme, stage 1 (amusement park; attract demo, measured) | 40 / 40, 347 |
| `$36` | `$9882` (2) | 110 (88.2) | loops | not identified | 172 / 172, 1116 |
| `$37` | `$9A25` (2) | 89 (71.4) | ends (`$06`), 2505 ticks | not identified | 324 / 324, 2582 |
| `$38` | `$9F96` (2) | 110 (88.2) | loops | not identified | 120 / 120, 905 |
| `$39` | `$BAFD` (2) | 81 (65.0) | ends (`$06`), 1729 ticks | not identified | 274 / 274, 3238 |
| `$3A` | `$C026` (2) | 81 (65.0) | loops | How to play (after a coin) | 252 / 252, 3145 |
| `$40` | `$99EE` (1) | 80 (64.2) | loops | Theme: Kyo | 1841 / 1841, 23663 |
| `$41` | `$B493` (1) | 120 (96.2) | loops | Theme: Iori | 1131 / 1131, 17183 |
| `$42` | `$D5AD` (2) | 153 (122.7) | loops | Theme: Shingo | 1270 / 1270, 13224 |
| `$43` | `$C31E` (2) | 122 (97.9) | loops | Theme: Athena | 2421 / 2421, 16482 |
| `$44` | `$C239` (1) | 120 (96.2) | loops | Theme: Yashiro / Shermie / Chris (New Face team) | 1296 / 1296, 19416 |
| `$45` | `$AFB8` (0) | 117 (93.8) | loops | Theme: Terry | 1100 / 1100, 19199 |
| `$46` | `$9F80` (0) | 97 (77.8) | loops | Theme: Yamazaki | 1226 / 1226, 14549 |
| `$47` | `$8000` (1) | 83 (66.6) | loops | Theme: Blue Mary | 1244 / 1244, 16550 |
| `$48` | `$8021` (0) | 127 (101.9) | loops | Theme: Billy | 2967 / 2967, 43173 |
| `$49` | `$A126` (2) | 126 (101.1) | loops | not identified | 1195 / 1195, 20420 |
| `$4A` | `$E6E9` (0) | 84 (67.4) | loops | fight theme, stage 6 (lava ring) | 1656 / 1656, 13691 |
| `$4B` | `$8000` (2) | 96 (77.0) | loops | fight theme, stage 7 (dark stone ring) | 846 / 846, 15310 |
| `$4C` | `$C8FA` (0) | 71 (56.9) | loops | not identified | 1413 / 1413, 19340 |
| `$50` | `$9CF7` (2) | 84 (67.4) | loops | not identified | 108 / 108, 1870 |
| `$51` | `$E4FD` (2) | 100 (80.2) | loops | not identified | 605 / 605, 7219 |
| all 41 | | | | | **30348 / 30349**, 340078 |
