# Real Bout Fatal Fury sound driver ("Ver 3.0 by MAKOTO", Art of Fighting 3's code)

Real Bout Fatal Fury (SNK 1995, MAME `rbff1`, `/data/roms/rbff1.neo`, M1 128 KB; `rbff1a` has the same M1). The M1 ROM
carries `Ver 3.0 by MAKOTO.04/03/10 to SK` and the interrupt vector `JP $1C9C` of Art of Fighting 3 and Samurai
Shodown III (`ff3_sound_driver.md`, section "Art of Fighting 3's build"). Modelled by `tools/makoto3` (`games.py`
`rbff1`), one code path, no model change.

## Identity

Compared byte for byte with Art of Fighting 3's M1 over `$0000-$2DFF`, every difference is a 16-bit table operand
(or AOF3 data that sits at `$2891-$2DFF`, where Real Bout has zeros): the code is AOF3's, instruction for instruction,
with its tables moved. So AOF3's switches hold: per-channel ADPCM-A sample tables set by opcode `$3C`
(`a_chan`), 16-byte ADPCM-B records, no per-octave ADPCM-B mode (`b_octave` False), the stack guard.

## Tables (games.py `rbff1`, AOF3's value in brackets)

Type table `$6D46` (`$5F5E`), bank map `$2E00` (`$2891`, three maps), song headers `$3C78` (`$3841`), FM patches `$2E40`
(`$28D1`), F-numbers `$6EC7` (`$60DF`), ADPCM-B records `$65B6` (`$51E6`), one-sample numbers `$6B46` (`$5CE6`),
pitched delta-N `$6BC6` (`$5D26`; the second operand AOF3 points at `$5DAE` also reads `$6BC6` here), per-octave delta-N
`$6C46` (`$5E5E`), default ADPCM-A table `$40F6` (`$3E0F`); pitch `$1C84`, gate `$2745`, channel words `$2570` / flags
`$2580` unchanged. Music (type 2): `$20`, `$22`, `$23`, `$26-$33`, `$38`, `$3D-$3F`, `$47`, `$4B`, `$55-$5F` (34).

## Validation

`capture.py --game rbff1 --songs DIR` (power-on, the game's commands blocked from frame 880: it sends `$07` at 873 and
its first song `$3E` at 894; the song at frame 900), `regs.py`: all 34 songs, 31651 / 31651 interrupts with writes
identical, 397968 captured writes. Songs: `rbff1_songs.md`.
