# Garou: Mark of the Wolves sound driver (SNK "Sound Driver(ROM)Ver 1.8 99/08/04 To SNK")

Garou: Mark of the Wolves (SNK 1999, MAME `garou`, `/data/roms/garou.neo`, M1 256 KB, V 16 MB). The cartridge's M1 is
encrypted on the board (CMC50 generation, as KOF99), but our `.neo` already holds the decrypted M1 (the ID string reads in
clear at `$003E`; copy `/data/neogeo_dict/sound/garou/garou_m1.bin`), and our emulator runs the `.neo` as it is. The
driver is the build after KOF98's `Sound Driver(ROM)Ver 1.7` (`kof98_sound_driver.md`) and is modelled by that model,
one code path (`tools/kof98snd/games98.py` `garou`). Everything below is read from the Z80 code (`tools/z80disasm.py`,
listing `/data/neogeo_dict/sound/garou/drv.asm`; instruction-level alignment with KOF98's in
`/data/neogeo_dict/sound/garou/scratch/k98_vs_garou.txt`) and checked against captures of the real driver in our
emulator; *(inferred)* marks what is not.

## What changed from KOF98's v1.7

Aligned instruction by instruction, the two drivers differ in two places only (the rest is the same code, from `$1948`
on moved by `+$05` to `+$10`, with every table operand moved alike):

1. **The FM level effect works** (`$1948`). KOF98 ends the level effect's tick with `LD B,A / JP $2003`, which recomputes
   the TL from the velocity and drops the effect's value (the model's "the TL is recomputed without it"). Garou adds the
   value to the velocity (`$0AB6`) and enters the level lookup with it (`LD BC,$311D / CALL $1F8C`, the body of the
   routine `$1F89` after its `LD A,(IX+$03)`), then the usual TL output (`$2019`): TL = level table [velocity + value] +
   the song's FM attenuation, at most `$7F`. `games98.py` `fm_level_fx`.
2. **ADPCM-B slur into another note** (`$1E8F`): when the last note-on was a slur into a different note (`$FD9C` bit 1)
   and the channel is not in note mode (block `+$08` bit 0 clear), the key-on is a full one (sample restart) instead of
   the tie path. The same insertion as Samurai Shodown IV's Ver 1.0 (`samsho4_sound_driver.md`). `b_legato_keyon`.

## Model corrections that came out of Garou (shared)

- **A note outside the note table** (`$2533`: a note byte `$78-$7F`, table byte `$FF`): `CP $C0 / RET NC` returns with
  the carry clear, so the caller does not give up: it reads the F-number word from the note table entry itself
  (`$FFFF`), adds the detune, ORs the note byte's low 3 bits in as the block, writes `$A4`/`$A0` and keys on. The model
  skipped the note (the same code is in KOF98 and Kizuna: no capture of theirs reaches it; their results are unchanged).
- **The FM pitch path on the ADPCM-B channel** (a `$05` bend there: `$A4`/`$A0` + channel - 2 on port B = `$B0`/`$AC`,
  and `$28` = `$FC`): the model emitted it but `regs98.py` wrote it only for ADPCM-A channels; now for any channel.
  KOF98's `$26` (551 of 551 interrupts identical, was 538) and `$41` (1382 of 1382, was 1380) gain from it and from the
  off-table note path; Kizuna's and Samurai Shodown IV's results are unchanged.
- Captures: Garou's NMI (`$007B`) advances the command ring index on a `$00` without writing the slot, and the main loop
  (`$0146`) does not clear slots, so a blocked command replaced by `$00` would replay the byte left 64 commands earlier.
  `capture98.py` replaces blocked commands with `$63` (type 0, ignored) for Garou (`games98.py` `nop`; makoto3's
  `capture.Sound.nop`, default `$00`).
- The driver's FM TL shadows carry over from song to song, so the game's own first song (`$5D` at frame 431, right after
  `$07` at 430) is blocked: every capture starts from the power-on state.

## Tables (games98.py `garou`)

Songs `$329E` (`$10FE`), all-off header `$2BB2`, bank sets `$2718`, FM notes `$2BD8`, F-numbers `$2A78`, levels FM
`$311D` / ADPCM-A `$319D` / ADPCM-B `$321D`, ADPCM-B delta-N `$2B3A`, ADPCM-B records via `$2E1E`, effect type 6 via
`$2E32`, 11-byte ADPCM-A records = sample table slot 7 (as KOF98), re-entry guard `$FD9B`, type table `$3038` (index cmd
- `$20`; music `$21-$54`, `$56-$62`). System commands (word jump table `$0D7B`) with a parameter byte (they call `$01AC`
or `$0F1A`): `$0A`, `$0E`, `$14-$1E`.

## Validation

`capture98.py --game garou --songs DIR`, `regs98.py`: all 64 songs, 39486 of the 39487 sequencer interrupts with writes identical in order (the other is `$3B`'s last, cut by the end of the capture), 424545 captured writes; the FM level effect (`$32`), off-table notes (`$22`, `$2C`, `$32`, `$38`) and the FM pitch path on ADPCM-B (`$38`) all measured. Per song: `garou_songs.md`.
