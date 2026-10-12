# The King of Fighters 2000 songs

The 35 music commands of The King of Fighters 2000 (SNK 2000, MAME `kof2000`), whose sound driver is SNK's
`Sound Driver(ROM)Ver 1.9 00/03/22` (games98 `'kof2000'`): Garou's Ver 1.8 line one step on, the same code with the
tables moved (found by Garou's code references), Garou's two changes (FM level effect on the velocity, ADPCM-B slur
keys on again) kept. The `.neo`'s M1 is already decrypted (the CMC50 M1 scheme undone at conversion): the driver ID
sits at `$003E`. Catalogue, where each is heard, and the per-song validation of tools/kof98snd's model against the
real driver in our emulator. "measured" = seen in our emulator.

    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/kof2000/kof2000_m1.bin --catalog
    python3 tools/kof98snd/song98.py /data/neogeo_dict/sound/kof2000/kof2000_m1.bin 0x22 --list
    python3 tools/kof98snd/capture98.py --game kof2000 --songs /data/neogeo_dict/sound/kof2000/cap
    python3 tools/kof98snd/regs98.py /data/neogeo_dict/sound/kof2000/kof2000_m1.bin 0x22 /data/neogeo_dict/sound/kof2000/cap/cap_22.txt
    python3 tools/songlab/build_web.py --game kof2000 /data/neogeo_dict/sound/songlab/all/data/kof2000

(`kof2000_m1.bin` = the M1 slice of `/data/roms/kof2000.neo`.)

## Catalogue

Command map (`$307C`, index cmd - `$20`): music `$21-$2E`, `$31-$35`, `$38-$3C`, `$40-$4A` (35). Captures: power-on,
the game's own commands blocked from frame 410 (it sends `$07` at 408 and its first song `$21` at 429; blocked
commands become `$30`, type 0), the song sent at frame 431 (sent at 430 the command lands just before a timer
interrupt and every song starts one tick late), length from song98.py to the loop point or the end + 15 %.
Validation = sequencer interrupts whose register writes are identical in order; the two differences are `$25`'s and
`$27`'s last interrupt, which the capture cuts in the middle of the handler.

"Heard at": one attract run in our emulator (power-on, no input, 30000 frames, capture98.py without blocking): which
music commands the game sent and when. Screens not identified (no screenshots taken); commands sent several times
in a row (`$26`, `$3C`) are short cues rather than songs.

| Cmd | Header (bank set) | Tempo (ticks/s) | End | Heard at | Validation: identical sequencer interrupts, captured writes |
|---|---|---|---|---|---|
| `$21` | `$7693` (0) | 180 (144.4) | ends (`$06`), 3538 ticks | the game's first song at boot (frame 429); again at the start of every attract cycle (measured) | 9 / 9, 103 |
| `$22` | `$772B` (0) | 135 (108.3) | loops | attract, no input: sent 12x, first at frame 10321 (measured) | 1789 / 1789, 27315 |
| `$23` | `$8CC1` (0) | 105 (84.2) | loops | attract, no input: sent 8x, first at frame 2975 (measured) | 2293 / 2293, 34806 |
| `$24` | `$AA7F` (0) | 131 (105.1) | loops | attract, no input: sent 1x, first at frame 14027 (measured) | 1702 / 1702, 20630 |
| `$25` | `$C5BE` (0) | 142 (113.9) | loops | attract, no input: sent 3x, first at frame 18633 (measured) | 1737 / 1738, 24552 |
| `$26` | `$DBCB` (0) | 130 (104.3) | loops | attract, no input: sent 13x, first at frame 3839 (measured) | 1976 / 1976, 18214 |
| `$27` | `$8000` (1) | 140 (112.3) | loops | not identified | 2419 / 2420, 33828 |
| `$28` | `$A47B` (1) | 144 (115.5) | loops | attract, no input: sent 2x, first at frame 22597 (measured) | 1721 / 1721, 21278 |
| `$29` | `$C37D` (1) | 120 (96.2) | loops | attract, no input: sent 1x, first at frame 23816 (measured) | 1390 / 1390, 10258 |
| `$2A` | `$CB43` (1) | 105 (84.2) | loops | attract, no input: sent 2x, first at frame 28356 (measured) | 1134 / 1134, 10220 |
| `$2B` | `$D341` (1) | 144 (115.5) | loops | not identified | 1486 / 1486, 20859 |
| `$2C` | `$DA98` (1) | 118 (94.6) | loops | attract, no input: sent 7x, first at frame 2007 (measured) | 1778 / 1778, 19249 |
| `$2D` | `$8000` (2) | 120 (96.2) | loops | not identified | 2056 / 2056, 21301 |
| `$2E` | `$9074` (2) | 131 (105.1) | loops | attract, no input: sent 1x, first at frame 2059 (measured) | 1853 / 1853, 17478 |
| `$31` | `$AE15` (2) | 64 (51.3) | loops | attract, no input: sent 1x, first at frame 27686 (measured) | 1265 / 1265, 9096 |
| `$32` | `$B316` (2) | 80 (64.2) | loops | not identified | 2366 / 2366, 20707 |
| `$33` | `$B5EE` (2) | 120 (96.2) | loops | attract, no input: sent 3x, first at frame 23345 (measured) | 186 / 186, 1815 |
| `$34` | `$B7A0` (2) | 120 (96.2) | ends (`$06`), 241 ticks | attract, no input: sent 2x, first at frame 23968 (measured) | 6 / 6, 24 |
| `$35` | `$B7D8` (2) | 140 (112.3) | loops | not identified | 556 / 556, 6225 |
| `$38` | `$BB44` (2) | 143 (114.7) | loops | attract, no input: sent 2x, first at frame 2040 (measured) | 1075 / 1075, 16974 |
| `$39` | `$C304` (2) | 143 (114.7) | loops | attract, no input: sent 1x, first at frame 23137 (measured) | 82 / 82, 1526 |
| `$3A` | `$C46C` (2) | 100 (80.2) | ends (`$06`), 499 ticks | attract, no input: sent 3x, first at frame 27563 (measured) | 125 / 125, 1938 |
| `$3B` | `$C80D` (2) | 120 (96.2) | ends (`$06`), 1735 ticks | not identified | 326 / 326, 3052 |
| `$3C` | `$CCBD` (2) | 100 (80.2) | ends (`$06`), 391 ticks | attract, no input: sent 12x, first at frame 7285 (measured) | 105 / 105, 1443 |
| `$40` | `$D000` (2) | 144 (115.5) | ends (`$06`), 17147 ticks | attract, no input: sent 1x, first at frame 22699 (measured) | 1293 / 1293, 14902 |
| `$41` | `$DAF2` (2) | 144 (115.5) | ends (`$06`), 13027 ticks | attract, no input: sent 1x, first at frame 26775 (measured) | 931 / 931, 12416 |
| `$42` | `$E151` (2) | 144 (115.5) | ends (`$06`), 14799 ticks | attract, no input: sent 1x, first at frame 28915 (measured) | 984 / 984, 12843 |
| `$43` | `$E891` (2) | 144 (115.5) | ends (`$06`), 12013 ticks | attract, no input: sent 4x, first at frame 23974 (measured) | 874 / 874, 11984 |
| `$44` | `$EE46` (2) | 144 (115.5) | ends (`$06`), 15197 ticks | attract, no input: sent 5x, first at frame 7401 (measured) | 980 / 980, 12962 |
| `$45` | `$8000` (3) | 144 (115.5) | ends (`$06`), 14251 ticks | attract, no input: sent 1x, first at frame 24004 (measured) | 931 / 931, 12398 |
| `$46` | `$8645` (3) | 144 (115.5) | ends (`$06`), 16753 ticks | attract, no input: sent 1x, first at frame 23148 (measured) | 1476 / 1476, 17507 |
| `$47` | `$93D2` (3) | 144 (115.5) | ends (`$06`), 14893 ticks | not identified | 1087 / 1087, 15295 |
| `$48` | `$9E96` (3) | 144 (115.5) | ends (`$06`), 12097 ticks | not identified | 885 / 885, 12055 |
| `$49` | `$A4C6` (3) | 144 (115.5) | ends (`$06`), 16269 ticks | not identified | 1005 / 1005, 13513 |
| `$4A` | `$AC4F` (3) | 144 (115.5) | ends (`$06`), 14221 ticks | attract, no input: sent 1x, first at frame 11091 (measured) | 930 / 930, 12398 |
| all 35 | | | | | **40811 / 40813**, 491164 |
