# Real Bout Fatal Fury 2 sound driver (SNK "Sound Driver(ROM)Ver 1.6 97/12/08 To SNK")

Real Bout Fatal Fury 2: The Newcomers (SNK 1998, MAME `rbff2`, `/data/roms/rbff2.neo`, M1 256 KB). The M1 ID string
`Sound Driver(ROM)Ver 1.6 97/12/08 To SNK` sits between KOF97's Ver 1.1 and KOF98's `(ROM)Ver 1.7 98/06/16`. Modelled by
KOF98's model (`tools/kof98snd/games98.py` `rbff2`), one code path.

## What it is: KOF98's v1.7 with Ver 1.0/1.1's operator level effects

Aligned instruction by instruction with KOF98's M1 (operands normalised), `$0000-$2DFF` differs in about 20 places, all
of them one feature that KOF98 dropped: the four **per-operator level effect records** per FM channel of Ver 1.0 / 1.1
(`op_fx`, records at `$F8A9`, `$195E-$1A3E`, record select `$14BB`, the effect calls in the note and tick paths at
`$2321`, `$2413`, `$2607`), with Ver 1.0 / 1.1's RAM layout around them (re-entry guard `$FE6B`, KOF98 `$FD9B`).
Everything else is KOF98's: opcode set `$00-$34`, sample table slot 7 with 11-byte records, KOF98's song start.
Small system-command differences (`$0FC7` call, `$0FE2` range check) are not reached by songs. The type table `$3038`
is Garou's address.

The NMI (`$0069`) advances the command ring before it tests for `$00`, as Garou's: a capture that blocks the game's
commands with `$00` makes the main loop replay the song command left in the slot (the song restarts). `nop=0x46`
(a type-0 command) is what blocked commands become in captures.

## Tables (games98.py `rbff2`; the instruction that loads each)

Songs `$329E` (`$10FF`), all-off header `$2CDA` (`$10F5`), bank sets `$2840` (`$1133`), FM notes `$2D00` (`$2655`),
F-numbers `$2BA0` (`$2666`), levels `$311D` / `$319D` / `$321D` (`$20F9`, `$20E3`, `$2120`), ADPCM-B delta-N `$2C62`
(`$0978`), ADPCM-B records via `$2E1E` (`$0810`), effect type 6 via `$2E32` (`$13ED`), modulator mask `$282F` (`$1539`),
sample table slot 7 (`$0EF2`), guard `$FE6B` (`$1C9D`), type table `$3038` (`$0183`): music `$21-$2B`, `$2D`, `$2F-$45` (35).
System commands with a parameter: `$0A`, `$0E`, `$14` (two bytes), `$15-$1E`.

## Validation

`capture98.py --game rbff2 --songs DIR` (the game sends `$07` at frame 912 and its first song `$21` at 925; commands
blocked from 914, the song at 940), `regs98.py`: all 35 songs, 42466 / 42467 sequencer interrupts identical in order
(the other is `$31`'s last, cut by the end of the capture), 511196 captured writes. The vibrato `$A4` fix
(`rbffspec_sound_driver.md`) came from `$33`. Songs: `rbff2_songs.md`.
