# Fatal Fury Special songs

The 28 music commands of Fatal Fury Special (SNK 1993), whose sound driver is KOF94's build of Fatal Fury 3's
"Ver 3.0 by MAKOTO" with other tables (`ff3_sound_driver.md`, section "Fatal Fury Special's build"): catalogue, where
each is heard, and the per-song validation of tools/makoto3's model against the real driver. Everything is decoded by
`tools/makoto3/song.py` from the M1 ROM; "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/fatfursp/fatfursp_m1.bin --catalog          one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/fatfursp/fatfursp_m1.bin 0x36 --list        the event listing
    python3 tools/makoto3/capture.py --game fatfursp --songs /data/neogeo_dict/sound/fatfursp/cap     capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/fatfursp/fatfursp_m1.bin 0x36 /data/neogeo_dict/sound/fatfursp/cap/cap_36.txt
    python3 tools/songlab/build_web.py --game fatfursp /data/neogeo_dict/sound/songlab/all/data/fatfursp

## Catalogue

Command map (`$74E2`): music `$20`, `$23-$25`, `$2D-$3B`, `$3D`, `$42-$48`, `$5F`. Captures: power-on, the game's own
commands blocked from frame 850 (it sends `$07` at 846 and the title `$47` at 860), the song sent at frame 900, length
from song.py to the loop point or the end + 15 %. Validation = interrupts whose register writes (minus timer-flag and
end-flag housekeeping) are identical in the capture and in the model, and the number of captured writes compared.

"Heard at" comes from runs in our emulator (command logs and screenshots in `/data/neogeo_dict/sound/fatfursp/`):
`attract` (power-on, no input, 8 minutes: only the title `$47`, every cycle), `play1` (two credits, buttons mashed,
lost the first match twice), `enemy5`/`enemy6` (one credit each: Terry, then each of the ten opponents of the enemy
select screen; the stage theme is the first music command after the map `$24`, the opponent read from the HUD).
The six boss themes are named from the 68K's stage table (`ff3_sound_driver.md`, "What the 68000 sends"): no run
reached them, and which boss has which index is not measured.

| Cmd | Header (bank) | TB (ticks/s) | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|
| `$20` | `$76E3` (0) | `$B0` (43.4) | stops (`$40`), 3 ticks | no channel plays a note: a silence (*inferred*) | 3 / 3, 158 |
| `$23` | `$7758` (0) | `$BD` (51.8) | loops | player select (measured) | 266 / 266, 4964 |
| `$24` | `$7C3F` (0) | `$C8` (62.0) | loops | map before a match, "The 1st stage" (measured) | 179 / 179, 3599 |
| `$25` | `$7EF5` (0) | `$B5` (46.3) | loops | not heard | 406 / 406, 5671 |
| `$2D` | `$83CC` (0) | `$C0` (54.3) | stops (`$40`), 194 ticks | continue / memory card save screen (measured) | 11 / 11, 299 |
| `$2E` | `$84C9` (0) | `$BE` (52.6) | stops (`$40`), 709 ticks | winner's quote after a lost match (measured) | 388 / 388, 5155 |
| `$2F` | `$8A8C` (0) | `$BC` (51.1) | loops | not heard | 3634 / 3634, 107285 |
| `$30` | `$8000` (1) | `$B9` (48.9) | loops | stage theme, Terry Bogard (measured, enemy select) | 1072 / 1072, 12764 |
| `$31` | `$8C2E` (1) | `$B2` (44.5) | loops | stage theme, Andy Bogard (measured) | 1129 / 1129, 13167 |
| `$32` | `$8C33` (0) | `$CA` (64.3) | loops | stage theme, Joe Higashi (measured) | 1122 / 1122, 21815 |
| `$33` | `$9747` (0) | `$CE` (69.4) | loops | stage theme, Big Bear (measured) | 1873 / 1873, 22195 |
| `$34` | `$A469` (0) | `$C4` (57.9) | loops | stage theme, Jubei Yamada (measured) | 688 / 688, 15931 |
| `$35` | `$B40B` (0) | `$BB` (50.3) | loops | stage theme, Mai Shiranui (measured) | 3687 / 3687, 39389 |
| `$36` | `$C057` (0) | `$BC` (51.1) | loops | stage theme, Cheng Sinzan (measured) | 1002 / 1002, 14641 |
| `$37` | `$E65C` (1) | `$BA` (49.6) | loops | stage theme, Kim Kaphwan (measured) | 1180 / 1180, 17133 |
| `$38` | `$97BD` (1) | `$C1` (55.1) | loops | stage theme, 68K table index 10 (a boss: not reached) | 2024 / 2024, 30209 |
| `$39` | `$A83E` (1) | `$D9` (89.0) | loops | stage theme, 68K table index 11 (a boss: not reached) | 740 / 740, 11963 |
| `$3A` | `$B135` (1) | `$BE` (52.6) | chains to `$3A` | stage theme, 68K table index 12 (a boss: not reached); restarts itself with opcode `$47` | 669 / 669, 22684 |
| `$3B` | `$E4FC` (1) | `$C0` (54.3) | loops | stage theme, 68K table index 14 (a boss: not reached) | 150 / 150, 903 |
| `$3D` | `$CD94` (0) | `$CC` (66.8) | loops | not heard | 180 / 180, 3642 |
| `$42` | `$D19D` (0) | `$C2` (56.0) | loops | stage theme, Duck King (measured) | 2273 / 2273, 33747 |
| `$43` | `$BD8D` (1) | `$C8` (62.0) | loops | stage theme, 68K table index 13 (a boss: not reached) | 2250 / 2250, 31783 |
| `$44` | `$CD38` (1) | `$8A` (29.4) | loops | stage theme, Tung Fu Rue (measured) | 1470 / 1470, 23763 |
| `$45` | `$D76C` (1) | `$C0` (54.3) | loops | stage theme, 68K table index 15 (the 68K sends `$FB` after it; not reached) | 1483 / 1483, 29975 |
| `$46` | `$E1D2` (0) | `$B0` (43.4) | stops (`$40`), 465 ticks | not heard | 119 / 119, 2702 |
| `$47` | `$E583` (0) | `$B0` (43.4) | stops (`$40`), 465 ticks | title, every attract cycle (measured) | 119 / 119, 2702 |
| `$48` | `$E934` (0) | `$D3` (77.2) | loops | not heard | 1160 / 1160, 16851 |
| `$5F` | `$F3E8` (0) | `$C0` (54.3) | stops (`$40`), 386 ticks | NEO-GEO logo jingle at boot, started by command `$02` (measured: the same writes) | 259 / 259, 1917 |
| all 28 | | | | | **29536 / 29536**, 497007 |

`$46` and `$47` are two copies of the title (other header addresses, the same writes). `$25`, `$2F`, `$3D`, `$46`,
`$48` have no reference found in our runs or in the stage table (*not heard*; a static scan of the 68K's sound
requests, as for KOF94, was not made).
