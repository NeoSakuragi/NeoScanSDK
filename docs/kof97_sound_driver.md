# KOF97 sound driver (SNK "Sound Driver Ver 1.1 96/10/01 To SNK")

The King of Fighters '97 (SNK 1997, MAME `kof97`, `/data/roms/kof97.neo`, M1 128 KB, V 12 MB). The M1 ROM carries
`Sound Driver Ver 1.1 96/10/01 To SNK` at `$003E`: the build after Samurai Shodown IV's `Ver 1.0 96/08/09`
(`samsho4_sound_driver.md`) and before KOF98's `(ROM)Ver 1.7` (`kof98_sound_driver.md`). It is modelled by KOF98's
model, one code path (`tools/kof98snd/games98.py` `kof97`). Read from the Z80 code (`tools/z80disasm.py`, listing
`/data/neogeo_dict/sound/kof97/drv.asm`; instruction-level alignments in `/data/neogeo_dict/sound/kof97/scratch/`
`ss4_vs_k97.txt`, `k98_vs_k97.txt`) and checked against captures of the real driver in our emulator.

## What changed from Samurai Shodown IV's Ver 1.0

Aligned instruction by instruction, `$0000-$2DFF` is Ver 1.0's code with two deletions (everything after them moved
by `-$03`, then `-$0E`, with every table operand moved alike); RAM layout, NMI, opcode set, pointer table `$2E00`,
operator level effects and the type table at `$2FB0` are Ver 1.0's:

1. **No ADPCM-B slur restart** (Ver 1.0 `$1FFC`, 11 bytes: `BIT 0,(IX+$08) / JR NZ / BIT 1,A / JP NZ,$0828`): a slur
   into another note on ADPCM-B takes the tie path (volume, delta-N), as KOF98 and Kizuna. `b_legato_keyon` is off.
   So Ver 1.0's restart was dropped in 1.1 and came back in Garou's 1.8.
2. **Stop the music `$04`** (`$0FE9`, word jump table `$0D5E`) no longer calls Ver 1.0's `$1383` (YM `$27` = `$30`:
   timer flags reset) at its end; no song capture reaches it.

Everything else in KOF98's list of differences from Ver 1.0 holds for 1.1 too (KOF98's RAM layout, `$34` inline patch,
priority `$FDDD`, sample table slot 7, no operator effects are all later than 1.1).

## Tables (games98.py `kof97`)

Songs `$3216` (`$1189`), all-off header `$2D36`, bank sets `$289C`, FM notes `$2D5C`, F-numbers `$2BFC`, levels FM
`$3095` / ADPCM-A `$3115` / ADPCM-B `$3195`, ADPCM-B delta-N `$2CBE`, ADPCM-B records via `$2E1A`, effect type 6 via
`$2E2A`, modulator mask `$288B`, 11-byte ADPCM-A records = sample table slot 5, re-entry guard `$FE6B`, type table
`$2FB0` (index cmd - `$20`; music `$21-$3A`, `$40-$4C`, `$50`, `$51`: 41). System commands with a parameter as Ver 1.0
(`$0A`, `$0E`, `$14`, `$15`, `$18-$1E`); the game sends its voices and hits as `$1A` / `$1B` / `$1C` + code.

## Validation

`capture98.py --game kof97 --songs DIR` (power-on, the game's commands blocked from frame 878: it sends `$07` at 875
and its first song `$21` at 1550; the song at frame 900), `regs98.py`: all 41 songs, 30348 of the 30349 sequencer
interrupts with writes identical in order (the other is `$27`'s last, cut by the end of the capture), 340078 captured
writes. No model change was needed. Songs: `kof97_songs.md`.
