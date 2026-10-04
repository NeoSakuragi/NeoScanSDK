# Samurai Shodown IV sound driver (SNK "Sound Driver Ver 1.0 96/08/09 To SNK")

Samurai Shodown IV: Amakusa's Revenge (SNK 1996, MAME `samsho4`, `/data/roms/samsho4.neo`, M1 128 KB, V 10 MB). The M1
ROM carries `Sound Driver Ver 1.0 96/08/09 To SNK` at `$003E`: SNK's own driver line, between Kizuna Encounter's
`Ver 0.0 95/08/11` (`kizuna_sound_driver.md`) and KOF98's `(ROM)Ver 1.7` (`kof98_sound_driver.md`). It is modelled by
KOF98's model, one code path (`tools/kof98snd/games98.py` `samsho4`). Everything below is read from the Z80 code
(`tools/z80disasm.py`, listing `/data/neogeo_dict/sound/samsho4/drv.asm`; instruction-level alignments with Kizuna's and
KOF98's drivers in `/data/neogeo_dict/sound/samsho4/scratch/kz_vs_ss4.txt`, `k98_vs_ss4.txt`) and checked against
captures of the real driver in our emulator; *(inferred)* marks what is not.

## What it shares

- **Kizuna's RAM layout** (channel blocks `$FAF4` + `$27`*n, `$FE6C` "last note-on was a tie", ADPCM-B roots
  `$FDF0` / `$FDF1`, re-entry guard `$FE6B`, command ring `$FDF5`), its NMI (`$00` ignored, `$006C`), its pointer table
  `$2E00` (`+$06` bank map, `+$08` / `+$0A` ADPCM-B instruments and split pairs, `+$0C` 41-byte FM patches, `+$0E`
  ADPCM-A sample tables, `+$1A` ADPCM-B records) and its operator level effects (records `$F8A9` + `$34`*(ch-1), engine
  in the interrupt `$19E6`, modulator mask `$2899`).
- **KOF98's music engine** for everything else: the opcode set `$00-$33` (jump table `$1E08`, 4-byte entries; `$34`,
  KOF98's inline patch, does not exist), `$01` / `$04` / `$1F` / `$20` / `$2B` no-ops, `$0E` clears the tie flags, pan by
  `$31-$33`, the tie overhang counter (`$1D42`), `$27` / `$29` ADPCM-B roots as KOF98, `$2C` writes the level only after
  a note and the ADPCM-B `$1B` at once, a patch's effects start the effect engine (`$14A7`, `$1521`), the delta-N test
  with its `OR A` (`$093D`), the song start (`$1174`: ADPCM-B stop, FM keys off, ADPCM-A 1-3 dump `b $00 = $87`), bend
  range `$AA`, roots `$3C` / `$24`.

## What differs from both

| Where | Ver 1.0 | KOF98 / Kizuna |
|---|---|---|
| ADPCM-B key-on (`$1FFC`) | a slur into a different note (`$FE6C` bit 1) on a channel outside note mode (block `+$08` bit 0 clear) is a full key-on (sample restart) | KOF98 and Kizuna: the tie path (volume, delta-N) |
| `$14` selector >= 2 (`$2494`) | four operator level effect records, each in KOF98's level-effect format `[type][delay][depth][count][speed]` + count words (`$244C`) | Kizuna: four 5-byte records; KOF98: nothing |
| `$12` bits 4-5 (`$23A2`) | switch the four operator records | Kizuna the same; KOF98 nothing |
| ADPCM-A 11-byte records | sample table slot 5 (`$230D`) | KOF98 slot 7 |
| music vs effects on ADPCM-B | an effect owning ADPCM-B (`$FAE9`) keeps a song's `$06` from stopping it (`$1EFD`) | KOF98 uses a priority `$FDDD` |

The first row is the one its songs use: `games98.py` `b_legato_keyon`. No SS4 song uses the operator effects, `$1E`
or `$34`: their parsing and running are modelled only as far as Kizuna's and KOF98's are (not measured).

Two model corrections came out of SS4, both shared: `$2C` on ADPCM-A / ADPCM-B now reads the build's level tables
(`lv_a`, `lv_b`; the code had KOF98's addresses), and the F-number high byte is written as the driver writes it,
every bit of the word (a pitch bend can read past the F-number table and set bit 6 of `$A4+ch`, `$30` in SS4). KOF98's
`$3E` gains from the second: 1406 of 1406 interrupts identical (was 1397); every other KOF98 and Kizuna result is
unchanged.

## Tables (games98.py `samsho4`)

Songs `$3216` (`$118C`), all-off header `$2D44`, bank sets `$28AA`, FM notes `$2D6A`, F-numbers `$2C0A`, levels FM
`$3095` / ADPCM-A `$3115` / ADPCM-B `$3195`, ADPCM-B delta-N `$2CCC`, type table `$2FB0` (index cmd - `$20`: 1 system,
2 song, 3 sample effect, 5; music `$20-$29`, `$2C-$3F`, `$50-$57`). System commands (word jump table `$0D5E`) with a
parameter byte (they call `$01A5` or `$0EE8`): `$0A`, `$0E`, `$14`, `$15`, `$18-$1E`.

## Validation

`capture98.py --game samsho4 --songs DIR`: power-on, the game's commands blocked from frame 878 (it sends `$07` at 876
and its first song `$21` at 880), the song at frame 900. `regs98.py`: all 37 songs, 27484 of the 27485 sequencer
interrupts with writes identical in order (the other is `$22`'s last, cut by the end of the capture), 236390 captured
writes. Songs: `samsho4_songs.md`.
