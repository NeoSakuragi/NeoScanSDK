# Real Bout Fatal Fury songs

The 34 music commands of Real Bout Fatal Fury (SNK 1995, MAME `rbff1`), whose driver is the MAKOTO v3 build of Art of
Fighting 3 with other tables (`rbff1_sound_driver.md`): where each is heard, and the per-song validation of
tools/makoto3's model against the real driver. "measured" = seen in our emulator.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/rbff1/rbff1_m1.bin --catalog
    python3 tools/makoto3/capture.py --game rbff1 --songs /data/neogeo_dict/sound/rbff1/caps
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/rbff1/rbff1_m1.bin 0x2F /data/neogeo_dict/sound/rbff1/caps/cap_2F.txt
    python3 tools/songlab/build_web.py --game rbff1 /data/neogeo_dict/sound/songlab/all/data/rbff1

## Where the songs are heard

Runs in our emulator (`/data/neogeo_dict/sound/samsho/scratch/run.py`: Geolith with makoto3's port tap, pad input by frame, 68K RAM pokes, a screenshot after each music command); logs and screenshots in `/data/neogeo_dict/sound/rbff1/attract` (power-on, no input, 40000 frames: the attract demos play without music), `run/c1` (one credit, A through the selects, the match lost), `run/ch*` (the CPU fighter's id held), `run/win*` (the opponent's health held at 1 and the buttons mashed: every match won). Bytes that follow a system command with a parameter (`$0A`, `$0E`, `$15`, `$16`, `$18-$1E`; `$14` takes two) are arguments, not songs.

Measured: `$3E` opening and title (attract loop), `$4B` enemy select, `$59` / `$57` / `$5E` before a fight (the stage
intro: which one varies between runs), `$56` before the final fight with Geese, `$2A` that fight, `$55` continue, `$3D`
rank evaluation and name entry (after a game over and after the ending), `$3F` after the name entry, `$5D` Terry's
ending after Geese, `$47` the staff roll.

**The fight theme** (68K `$A736`): the word table `$A76A` indexed by the CPU fighter's id (`$106A26` when the mode word `$1041D6` is 1, `$109630` when 3, else `$106A24`;
the fighter record `$100411` / `$100511` holds the same id); all measured by
holding the id (`run/ch01-ch10`): 1 Terry `$2F`, 2 Andy `$2C`, 3 Joe `$29`, 4 Mai `$2B`, 5 Geese `$30`, 6 Sokaku `$2E`,
7 Bob `$26`, 8 Hon-Fu `$2D`, 9 Blue Mary `$28`, 10 Franco `$27`, 11 Yamazaki `$31`, 12 Jin Chonshu `$32`, 13 Jin Chonrei
`$33`, 14 Duck King `$5A`, 15 Kim `$5B`, 16 Billy `$5C`; entry 17 = `$2A` (Geese as the final boss, measured in a won
game). `$23` has the same header (`$745C`) as `$4B`: the same song.

Not identified: `$22`, `$38`, `$58`, `$5F` (not reached in these runs). `$20` is a 3-tick all-off.

## Catalogue

Captures: power-on, the game's commands blocked from frame 880, the song sent at frame 900, length from song.py to the
loop point or the end + 15 %. Validation = timer interrupts with writes identical in order.

| Cmd | Header (bank) | TB (ticks/s) | End | Heard at | Validation: identical interrupts, captured writes |
|---|---|---|---|---|---|
| `$20` | `$6F47` (0) | `$B0` (43.40) | ends, 3 ticks | All off (3 ticks) | 3 / 3, 162 |
| `$22` | `$6FBC` (0) | `$B9` (48.90) | loops | not identified | 319 / 319, 6620 |
| `$23` | `$745C` (0) | `$AB` (40.85) | loops | Enemy select (the same song data as $4B) | 308 / 308, 5217 |
| `$26` | `$8000` (2) | `$B6` (46.92) | loops | Theme: Bob | 468 / 468, 11667 |
| `$27` | `$8DA6` (2) | `$C0` (54.25) | loops | Theme: Franco | 1640 / 1640, 27136 |
| `$28` | `$8000` (1) | `$BA` (49.60) | loops | Theme: Blue Mary | 1302 / 1302, 19558 |
| `$29` | `$9E6B` (2) | `$B6` (46.92) | loops | Theme: Joe | 609 / 609, 14471 |
| `$2A` | `$A696` (2) | `$CA` (64.30) | loops | Final fight: Geese | 3646 / 3646, 36049 |
| `$2B` | `$B392` (2) | `$A5` (38.16) | loops | Theme: Mai | 2515 / 2515, 22818 |
| `$2C` | `$8FBC` (1) | `$B4` (45.69) | loops | Theme: Andy | 1719 / 1719, 21993 |
| `$2D` | `$BE2B` (2) | `$9F` (35.80) | loops | Theme: Hon-Fu | 1011 / 1011, 18826 |
| `$2E` | `$9F3B` (1) | `$B6` (46.92) | loops | Theme: Sokaku | 1608 / 1608, 19777 |
| `$2F` | `$B390` (1) | `$CC` (66.77) | loops | Theme: Terry | 1113 / 1113, 16664 |
| `$30` | `$CCCD` (2) | `$BA` (49.60) | loops | Theme: Geese | 642 / 642, 15110 |
| `$31` | `$D552` (1) | `$A9` (39.91) | loops | Theme: Yamazaki | 1677 / 1677, 20470 |
| `$32` | `$C6EE` (1) | `$A6` (38.58) | loops | Theme: Jin Chonshu | 1764 / 1764, 19483 |
| `$33` | `$DC2F` (2) | `$C3` (56.92) | loops | Theme: Jin Chonrei | 1374 / 1374, 18219 |
| `$38` | `$7A9F` (0) | `$C5` (58.85) | loops | not identified | 113 / 113, 1268 |
| `$3D` | `$7C9B` (0) | `$B0` (43.40) | loops | Rank / name entry | 772 / 772, 14621 |
| `$3E` | `$8996` (0) | `$C2` (56.00) | ends, 1402 ticks | Opening / title | 380 / 380, 2756 |
| `$3F` | `$9FE3` (0) | `$B0` (43.40) | ends, 182 ticks | After the name entry | 13 / 13, 88 |
| `$47` | `$9030` (0) | `$92` (31.57) | ends, 2758 ticks | Staff roll | 1062 / 1062, 10279 |
| `$4B` | `$745C` (0) | `$AB` (40.85) | loops | Enemy select | 308 / 308, 5217 |
| `$55` | `$A06A` (0) | `$B6` (46.92) | ends, 626 ticks | Continue | 202 / 202, 1779 |
| `$56` | `$EAFA` (1) | `$AE` (42.34) | ends, 566 ticks | Before the final fight (Geese) | 79 / 79, 1462 |
| `$57` | `$A431` (0) | `$CE` (69.44) | loops | Before a fight (stage intro) | 107 / 107, 1017 |
| `$58` | `$A61C` (0) | `$C2` (56.00) | ends, 1402 ticks | not identified | 380 / 380, 2756 |
| `$59` | `$ECF8` (1) | `$C7` (60.92) | loops | Before a fight (stage intro) | 224 / 224, 2493 |
| `$5A` | `$ACB6` (0) | `$B9` (48.90) | loops | Theme: Duck King | 1473 / 1473, 13959 |
| `$5B` | `$B5B0` (0) | `$94` (32.15) | loops | Theme: Kim | 1194 / 1194, 16486 |
| `$5C` | `$C8D6` (0) | `$BC` (51.06) | loops | Theme: Billy | 2864 / 2864, 23596 |
| `$5D` | `$EA00` (2) | `$89` (29.18) | ends, 744 ticks | Ending (Terry) | 260 / 260, 3328 |
| `$5E` | `$E09E` (0) | `$C6` (59.87) | loops | Before a fight (stage intro) | 243 / 243, 706 |
| `$5F` | `$E223` (0) | `$C0` (54.25) | ends, 386 ticks | not identified | 259 / 259, 1917 |
| all 34 | | | | | **31651 / 31651**, 397968 |
