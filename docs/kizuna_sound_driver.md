# Kizuna Encounter sound driver (SNK "Sound Driver Ver 0.0 95/08/11 To SNK")

Kizuna Encounter: Super Tag Battle (SNK 1996, MAME `kizuna`, `/data/roms/kizuna.neo`, M1 128 KB, V 8 MB). The M1 ROM
carries the ID string `Sound Driver Ver 0.0 95/08/11 To SNK` at `$003E`. It is the earliest build we have of SNK's own
"Sound Driver" line: KOF96 has `Ver 0.1 96/07/03`, Samurai Shodown IV `Ver 1.0`, KOF97 / RBFF Special `Ver 1.1`,
Last Blade `1.3`, RBFF2 `1.6`, KOF98 `Sound Driver(ROM)Ver 1.7` (ID strings read from the M1 ROMs). It is **not** a
MAKOTO v3 build (that one says `Ver 3.0 by MAKOTO.04/03/10 to SK`, FF3 / KOF94 / KOF95).

It is the same architecture as KOF98's driver (docs/kof98_sound_driver.md): NMI command ring, command type table,
timer-A clock with a 208 tempo accumulator, 11 music channel blocks of `$27` bytes (FM 1-4, ADPCM-A 1-6, ADPCM-B),
the same stream encoding (varlen length, `11xxxxxx` opcode byte, running status), the same opcode numbers up to `$2E`,
the same 41-byte FM patches, effect records and output stage. So it is modelled by KOF98's model, one code path:
`tools/kof98snd/games98.py` holds each build's table addresses and the behaviours that differ, `song98.py` /
`regs98.py` read them (the build is told from the ID string). Everything below was read from the Z80 code
(`tools/z80disasm.py`, disassembly in `/data/neogeo_dict/sound/kizuna/kizuna.asm`) and checked against captures of
the real driver in our emulator; *(inferred)* marks what is not.

## Map, ports, clock

- Z80: `$0000-$7FFF` fixed, `$8000-$F7FF` banked windows (bank sets at `$262D`, 4 bytes for ports `$08-$0B`; set 0 =
  identity, set 1 = the second 64 KB), RAM `$F800-$FFFF`.
- Vectors: reset `$00B0`, IRQ `$0038` → `$192D`, NMI `$0066`.
- NMI: reads port `$00`; **`$00` is ignored before touching the ring** (`$006C`, unlike KOF98); `$01`, `$03`, `$10`
  act at once; anything else goes into the 64-entry ring `$FDF5` (write index `$FE37`), echoed on port `$0C`.
- Main loop `$0107` → `$0140`: `< $20` system commands (jump table `$0C17`), else the type byte at `$2E6C + cmd - $20`:
  1 system, 2 song (`$016F` → `$101E`), 3 sample effect (`$018B`), 4 (`$0588`), 5 (`$095C`). Kizuna's map: type 2 =
  `$20-$25`, `$2B-$3B`, `$50`; type 5 = `$70-$76`, `$7F`; type 4 = `$80-$A6`; type 3 = `$F0-$F4`.
  The game sends its fight sounds as prefix + code (measured: `$1A`, `$1C`, `$1E`, `$18`, `$1B`, `$1D` + byte; `$0A`
  + fade speed); a code byte can look like a song number, so a song log must skip the byte after a prefix.
- Timer A = `$2B3` (`$25BA`: regs `$24`=`$AC`, `$25`=`$03`), 166.83 Hz, re-armed every interrupt (`$11EC`: `$27`=`$35`).
- ISR `$192D`: status (`$FDE3`) and ADPCM end flags (`$FDE4`, handlers `$0656` B, `$02BB` A); timer-B-only interrupts
  stop there (`$198B`). Re-entry guard `$FE6B` (incremented, `$1991`): an interrupt that arrives while the previous ISR
  runs is **dropped** (measured: 2102 of 228 268 timer-A interrupts over the 23 song captures, power-on included, 0.9 %).
  Then four groups, each with its own accumulator (`acc += tempo` per interrupt, a tick when `>= 208`):
  music (`$252A`, tempo `$FE59`) with the effect engine after the channels (`$1AB3`, while `$FE88`); group 1 =
  sequenced ADPCM-A effects (`$2545`, blocks `$FD3D` / `$FD64` / `$FD8B`); group 2 = ADPCM-B effects (`$2560`);
  group 3 = SSG (`$250F`).

## Songs

Song pointer = word `$30D0 + 2*(cmd - $20)` (cmd `$20` = all-off header `$2AE6`), bank set = byte
`($2E06)[cmd - $20]`. Header as KOF98: 11 enable bytes, tempo `+$0B`, FM attenuation `+$0C`, ADPCM-B volume add
`+$0D`, 11 stream pointers. Song start (`$101E`): ADPCM-B stop (`$10`=1, 0, unless a B effect plays), FM keys off
(`$0AEE`: `$28` = 1, 2, 5, 6); no ADPCM-A dump (KOF98 dumps A1-3). Blocks at `$FAF4` + `$27`*n, same layout as
KOF98's. ADPCM-B roots `$FDF0` = `$FDF1` = `$3C`.

Tables: FM notes `$2B0C`, F-numbers `$29AC`, levels FM `$2F4F` / ADPCM-A `$2FCF` / ADPCM-B `$304F`, ADPCM-B delta-N
`$2A6E`, pointer table `$2E00`: `+$06` bank map, `+$08` ADPCM-B instrument → record, `+$0A` split pairs, `+$0C` FM
patches (41 bytes), `+$0E` ADPCM-A sample tables (slot 0 `$3B04` ... slot 5 `$5546` = 11-byte looping records),
`+$1A` ADPCM-B 13-byte records (`$5663`), `+$2A` effect type 6 tables; `$2E2C` sequenced effect records `$F0-$F4`.

## What differs from KOF98's v1.7 (all in games98.py / song98.py)

Opcodes (jump table `$1C3E`, `$00-$2E`; `$2F-$34` do not exist):

| Op | Ver 0.0 | KOF98 |
|---|---|---|
| `$01` | 2 bytes, ignored (`$1E17`) | no-op, no bytes |
| `$04` | 1 byte, ignored (`$1F96`) | no-op |
| `$0E` | no-op (`$1CFA`) | clear the tie flags |
| `$1F` / `$20` | start a type 4 / type 5 command (`$232B` / `$233B`) | no-op |
| `$27` | FM transpose p-`$18`; ADPCM-B: root `$FDF0` = p-`$18`, `$FDF1` = that rounded down to an octave (`$2241`) | B root = p |
| `$29` | 1 byte: ADPCM-B split note p-`$18` (`$22A5`) | 2 bytes, split + high root |
| `$2B` | **pan**: p bits 1-0 → L/R (3 = both); FM writes `$B4` at once (`$1E38`). The songs' only pan opcode | no-op |
| `$2C` | volume, then the level at once even before the first note (FM TL, ADPCM-A `$08+ch`); ADPCM-B: only stored (`$FAAD`), written at the next key-on (`$1E78`) | only after a note; B written at once |
| `$14` | selector 0: as KOF98 but no inline type-6 table; 1: level effect `[type][delay][depth8][step][speed]` (`$21B7`); 2+: four 5-byte records, the **operator level effects** (`$21F7`) | 1: table-driven; 2+: nothing |
| `$12` | bits 4-5 also switch the four operator level effects (`$212E`) | bits 0-3 only |
| `$05` | bend: the quarter-semitone count stops only below 0 and restarts at 2 (`$1FB2`) | stops at <= 0, restarts at 0 |

Behaviour:
- **No tie overhang counter** (`$1B99`): a note with gate > length sets the tie flags at its length and keeps
  sounding until the channel's next key-on or key-off; KOF98 counts the overhang down and keys off.
- `$FE6C` (KOF98's `$FD9C`, "the last note-on anywhere was a tie", global): while its bit 0 is set, ADPCM-A key-ons
  *and key-offs* of every channel are skipped (`$1DE5`), and an ADPCM-B key-off runs the tie path instead (volume, and
  delta-N if bit 1: `$1E12` → `$079B`). It is cleared only by an ADPCM-B tie.
- ADPCM-B split: notes at or above the split use the second record with the plain root `$FDF0`, below it the first
  record with the octave root `$FDF1` (`$0714`; KOF98: high root for the high record).
- **Delta-N bug** (`$07F0`): the test for the two sample rates the driver singles out (`$375A`: -12, `$6EB3`: 0, else
  +12) lacks KOF98's `OR A` before the second `SBC HL,DE`, so the borrow of the first one counts: a `$6EB3` sample gets
  +12 (all of Kizuna's B instruments are `$6EB3`: they play one octave above the plain reading; measured).
- FM effects: a patch's effects do not start the effect engine (`$FE88` is set only by `$12` / `$14`, `$178A`); the
  key-on restarts also the operator records (`$23FA`).
- Operator level effects (`$184C`, records `$F8A9` + `$34`*(ch-1) + 13*op): on the patch's modulators (mask
  `$261C`[alg]), TL = the patch's TL + value, written to `$40/$48/$44/$4C` for records 0-3. Modelled from the code;
  **no Kizuna song uses them**, so not measured.
- ADPCM-A 11-byte records are sample table slot 5 (KOF98: 7); their key-on also writes the record's own pan|level
  over the music level (`$0277`).
- ADPCM-A level / end: the music's notes on A4-A6 are skipped while an effect owns the channel, and so is the dump at
  the end of a channel (`$1D3B`; KOF98's music defends with a priority instead).

## Sample effects from the songs (opcode `$1E`, `$0195`)

Four songs (`$2F`, `$37`, `$3A`, `$3B`) start sounds from their streams:
- code `< $F0`: a one-shot, slot 0's 6-byte record `[priority][start][end][pan|level]` on an effect channel;
- code `$F0-$F4`: a **sequenced effect**, record `[priority][level add][stream16]` at word `$2E2C + 2*(code-$F0)`: a
  little stream (tempo `$1E`, notes, `$06`) played on the effect channel's block in group 1 with its own tempo (set
  to `$5A` at start, `$10` changes it), sample tables `$FE48`.
Channel choice (`$0413`) among A4, A5, A6 (state `$FAB0` + 5*i: bit 0 one-shot, bit 1 sequence; priority `+1`): the
first free one in that order, else the busy one whose priority value is the highest of those not below the new
one's; none: dropped. The music does not defend its A4-A6 here. A one-shot's channel is freed by its end-of-sample
flag (`$02BB` → `$0303`, state 1 only); the model frees it after the sample's length at 18.5 kHz *(inferred timing,
it matches every capture)*. A sequence frees its bit at its `$06`.

## Validation (tools/kof98snd)

- `capture98.py --game kizuna --songs DIR`: our emulator (Geolith core with the Z80 port tap of
  `tools/makoto3/capture.py`), power-on, the game's commands blocked from frame 880 (it sends `$07` at 872 and its
  first song `$3A` at 935), the song sent at frame 900, to the loop point or the end + 15 %; `q 1` / `q 2` lines from
  the re-entry guard `$FE6B` read at the ISR's status read. Captures in `/data/neogeo_dict/sound/kizuna/cap`.
- `regs98.py M1 CMD CAP`: all 23 songs, **every sequencer interrupt with writes identical in order and values**
  (12 250 of the 12 252 interrupts with writes, 199 949 captured writes); the two others are the capture's last
  interrupt in `$2D` and `$38`, which the capture cuts in the middle of the handler. Per song: docs/kizuna_songs.md.
- `validate98.py`: 23 770 key-ons, 36 283 key-offs / dumps, 9 710 F-number writes, 147 ADPCM-B delta-N, 144 FM pan
  and 68 ADPCM-B volume writes predicted, every one at the same interrupt with the same values.
- KOF98 results are unchanged by the shared code (regs98 and validate98 outputs identical on its 50 captures).

Not measured (no song uses them): the operator level effects, `$1F` / `$20`, `$05` bends, `$29` splits, effect
types other than 1. The fight sound effects (prefix commands) and the SSG / ADPCM-B effect groups are not modelled.
