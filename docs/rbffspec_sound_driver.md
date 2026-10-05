# Real Bout Fatal Fury Special sound driver (SNK "Sound Driver Ver 1.1 96/10/01 To SNK")

Real Bout Fatal Fury Special (SNK 1996, MAME `rbffspec`, `/data/roms/rbffspec.neo`, M1 128 KB). The M1 ROM carries
KOF97's ID string `Sound Driver Ver 1.1 96/10/01 To SNK` (`kof97_sound_driver.md`), and `$0000-$2E0D` is byte-identical
to KOF97's M1: the same build, only the data from the pointer table `$2E00` on differs. Modelled by KOF98's model
(`tools/kof98snd/games98.py` `rbffspec`, KOF97's table addresses), no model change for the build itself.

Two builds now share an ID string, so `games98.game_of()` takes a `sig` (address, bytes) per entry when the ID matches
several: `rbffspec` = `7B 45 7B 4B` at `$2E0E` (its pointer table), `kof97` the entry without one.

## Tables (games98.py `rbffspec` = `kof97`)

Songs `$3216`, all-off header `$2D36`, bank sets `$289C`, FM notes `$2D5C`, F-numbers `$2BFC`, levels `$3095` / `$3115` /
`$3195`, ADPCM-B delta-N `$2CBE`, ADPCM-B records via `$2E1A`, effect type 6 via `$2E2A`, modulator mask `$288B`,
sample table slot 5, guard `$FE6B`, type table `$2FB0`: music `$21-$2A`, `$2C-$38`, `$3A-$3D` (27). System commands with
parameters as KOF97 (`$14` takes two bytes: slot prefix and code).

## Validation

`capture98.py --game rbffspec --songs DIR` (the game sends `$07` at frame 873 and its first song `$35` at 1076; commands
blocked from 878, the song at 900), `regs98.py`: all 27 songs, 36573 / 36573 sequencer interrupts identical in order,
442533 captured writes. Two model fixes came out of it, both on the shared path:

1. **Vibrato writes the whole `$A4` byte.** The FM pitch effect adds its value to the F-number word and writes the high
   byte as is; a bend below F-number 0 writes `$FF` / `$FE` there (bits 6-7 set). The model wrote `block << 3 | fnum >> 8`;
   now it writes the word's high byte (`song98.py` `fx_tick`, event key `hi`). Seen in `$23` here and Real Bout 2's `$33`;
   KOF98, KOF97, Kizuna, Samurai Shodown IV and Garou results unchanged.
2. **A song that starts another (`$0C` command opcode).** `$3D` ends with `$0C $38`: the driver starts `$38` in the same
   interrupt. `regs98.compare()` now compares such a song up to that interrupt (the chained song is validated as itself);
   the Song Lab's real-driver stream keeps playing into `$38`.

Songs: `rbffspec_songs.md`.
