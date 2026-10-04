# Fatal Fury 3 sound driver ("Ver 3.0 by MAKOTO.04/03/10 to SK"), and the builds of KOF94, KOF95, Fatal Fury Special and Art of Fighting 1-3

Second deep dive into a classic SNK driver, after KOF98 (`kof98_sound_driver.md`). Source: Fatal Fury 3's M ROM
(`/data/roms/fatfury3.neo`, M region, 128 KB; copy `/data/tmp/snd98/ff3/ff3_m1.bin`, disassembly `drv.asm` there, by
`tools/z80disasm.py`), checked against captures of the real driver in our emulator, interrupt by interrupt
(tools/makoto3, see Validation). The signature at `$003E` reads `Ver 3.0 by MAKOTO.04/03/10 to SK`: a different
driver line from KOF98's SNK v1.7, and nothing of KOF98's layout carries over. This file is the driver: protocol,
dispatch, the two clocks, channel state machine, stream format and every opcode, output stage, effects. The songs
(catalogue, structure, per-song validation) are in `ff3_songs.md`. The King of Fighters '94 runs a slightly different build of the same driver: its
differences are in "KOF94's build" below, its songs in `kof94_songs.md`. The King of Fighters '95 runs a reworked
build (other RAM layout, word jump tables, new effect commands, the same music engine): "KOF95's build", songs in
`kof95_songs.md`. Fatal Fury Special (1993) runs KOF94's build with its own tables: "Fatal Fury Special's build", songs in
`fatfursp_songs.md`. Art of Fighting (1992), Art of Fighting 2 (1994) and Art of Fighting 3 (1996) run three more
builds: AOF1 = KOF94's music engine with an older command path, AOF2 = KOF94's build with its own tables, AOF3 =
KOF95's build with per-channel ADPCM-A sample tables ("Art of Fighting's build", "Art of Fighting 2's build", "Art of
Fighting 3's build"; songs in `aof_songs.md`, `aof2_songs.md`, `aof3_songs.md`); Samurai Shodown 1-3 ("Samurai Shodown's
build", "... II's build", "... III's build"; songs in `samsho_songs.md`, `samsho2_songs.md`, `samsho3_songs.md`). Everything below is read from the code
(addresses cited) or measured; *(inferred)* marks the rest.

## Z80 map and ports

| Range | What |
|---|---|
| `$0000-$2CE8` | driver code |
| `$2C8D-$2E3F` | small tables (carrier masks, timer values, gate table, ADPCM-A channel bits `$2CE3`, reply table `$2CE9`, song bank bytes `$2E00`) |
| `$2E40-$3A6F` | 60 FM patches of 52 bytes |
| `$3A70` / `$3AF0` / `$3B30` | song header pointers / SSG effect headers / per-song ADPCM-A sample table (word tables, index = command - `$20` or - `$60`) |
| `$41EA` ... `$7FFF` | sample effect records, enable bitmaps, ADPCM-B records `$6FD6`, pitch tables, type table `$7D8E`, songs |
| `$8000-$FFFF` | song data through one of three bank maps (below), or RAM from `$F800` |
| `$F800-$FFFF` | RAM (`$F800-$FEB2` cleared at reset; stack top `$FFFC`) |

Ports: `$00` read = command from the 68000 (REG_SOUND `$320000`), `$00` write = acknowledge, `$0C` write = reply
latch, `$04-$07` = YM2610 (A addr/data, B addr/data), `$08` write = enable NMI, `IN A,($08-$0B)` = bank select (bank
in the upper address byte = A). Register writes go through `$2BAD` (port A, D = reg, E = value) and `$2BB8` (port B);
`RST $08` / `RST $10` between address and data are busy-wait stubs (`$189C`: three NOPs).

Bank maps (`$1151`, byte `$2E00`[song]): 0 = `$01B0`'s default (`$08`←`$1E`, `$09`←`$0E`, `$0A`←`$06`, `$0B`←`$02`:
the M ROM's first 64 KB as is); 1 = `$2E`/`$16`/`$0A`/`$04`: `$8000-$FFFF` shows `$10000-$17FFF`; 2 = `$3E`/`$1E`/
`$0E`/`$06`: `$18000-$1FFFF`. Every window moves together, so a song sees one contiguous 32 KB above `$8000`.

## Reset (`$00B0`)

`IM 1`, RAM cleared, `$FE30`/`$FE34`/`$FE35` = `$FF` (**music and effects muted until `$07`**), `$FEB6` = 3; FM keys
off, SSG volumes 0, ADPCM resets (`$0B2E`, `$0B60`, `$0B47`); ADPCM-A master volume `b $01` = `$3F`, `$10` = 1,
`$1C` = 0; a bank-switch self-test (`$00F4`: windows `$C000` and `$F000` both mapped to `$12000`, 32 bytes compared)
whose result is not used (both outcomes set `$FEB3` = 1, so `$0194`'s jump into bank `$1E` never runs); timer A = 1
(`$2B87` entry 3 of `$2C95`: reg `$25` ← `$51`, `$24` ← `$00`: (`$00` << 2) | (`$51` & 3)); `$1871`: `$27` = `$3F`
(both timers loaded, enabled, flags reset); `EI`, main loop `$0137`.

## Command path

**NMI (`$0066`)**: reads port `$00`; `$01`, `$03`, `$10` are acted on at once, before anything is stored: `$01` →
`$0D00` → `$0D31` (silence everything, then park the Z80 in a `JP $FFFD` loop written into RAM, reply 1: what the
68000 sends before it swaps the Z80 ROM, *inferred*), `$03` → `$0F39` (pans off, `JP $0000`), `$10` → `$1062` (sum of
`$0000-$EFFF` compared with `$0014`, RAM tests, result on port `$0C`, then `JP $0000`). `$00` is dropped (`$007C`,
before the ring index moves: unlike KOF98, `$00` is harmless). Anything else goes into the 64-entry ring `$FE4A`
(write index `$FEB1`), is echoed on port `$0C`, and port `$00` is acknowledged. **Measured consequence: a prefix
command's argument cannot be `$01`, `$03` or `$10`**: sent as `$19` `$01`, the `$01` parked the Z80 (fx capture).

**Main loop (`$0137`)**: takes the next ring byte (`$FEB0`) into `$FE3D`, dispatches on the type byte `$7D8E`[cmd]
(`$01C1`): 1 → system command (jump table `$0CA3`), 2 → song (`$01F2` → `$111B`), 3 → `$029F` (ADPCM-A effect), 4 →
`$0657` (ADPCM-B effect; no command has type 4), 5 → `$0A05` (SSG effect song), 0 → ignored. FF3's map: `$00-$1E`
type 1; music `$20-$34`, `$36-$37`, `$3A-$3B`, `$3D-$47`, `$4A-$4C`, `$5F` (40 commands); SSG effects `$60-$65`, `$7F`;
`$F0-$F4` type 3; the rest 0. After each command the reply `$FEB8` (= the command; + 1 on every 128th command, `$01F9`
counts in `$FEB6` by 2 and carries into `$FEB5`; purpose unknown) is written to port `$0C`, and every interrupt
writes it again (`$213F`). A prefix's argument is read by `$0207`, which waits in a loop for the next ring byte.

### System commands (`$0CA3`, command = index)

| Cmd | Handler | Effect |
|---|---|---|
| `$00`, `$16` | `$0D25` / `$0EAA` | nothing |
| `$01` / `$03` / `$10` | NMI (above) | park for a ROM swap / hard reset / ROM sum + RAM test |
| `$02` | `$0D26` | starts song `$5F` **without the mute check** (`JP $1133`); the game sends it under the NEO-GEO logo (frame 404, measured) |
| `$04` | `$0F58` | stop everything: music off (`$FE2D`), FM keys off, ADPCM-A/B reset, SSG off, timer A only (`$1886`), mute music and effects (`$FE34` = `$FE35` = `$FF`) |
| `$05` | `$0F8F` | stop the music and mute it |
| `$06` | `$0F9F` | stop the effects and mute them |
| `$07` | `$0FAC` | **unlock**: `$FE34` = `$FE35` = 0, both timers on (`$1871`). Sent by the game at frame 873 of a power-on (measured) |
| `$08` / `$09` | `$0FB8` / `$0FC1` | unmute the music / the effects only |
| `$0A` + byte | `$0FCA` | fade out the music at speed byte (`$FE27` = 1, `$FABE+2`; the fade, below); byte 0 = ignored |
| `$0B` / `$0C` | `$0FFA` / `$1006` | `$FC36` = 1 / 0 (the music's ADPCM-B pitch effect on / off) |
| `$0D` | `$1030` | clear the six ADPCM-A loop states `$FC0A` |
| `$0E` + byte | `$1053` | timer B = byte (the music's tempo); byte 0 = ignored |
| `$0F` | `$1044` | end the SSG effect song (unless it is `$7F`) |
| `$11` | `$0FE9` | end a fade |
| `$12` / `$13` | `$1000` / `$100B` | `$FC37` = 1 / 0 |
| `$14` + code / `$15` + code | `$0EAB` / `$0EF2` | stop the ADPCM-A effect `code` of slot 0 / of any other slot |
| `$17` | `$0E9D` | toggle `$FE42` (direction of the SSG pitch sweep) |
| `$18` `$1A` `$1C` `$1E` `$1B` + code | `$0DBD` `$0DD8` `$0DF8` `$0E18` `$0E38` | **ADPCM-A effect** `code` from slot 0 / 1 / 2 / 3 / 4 |
| `$19` + code | `$0E71` | **ADPCM-B effect** `code` |
| `$1D` + code | `$0E87` | ADPCM-B effect, enable bitmap `$6FB6` empty: never plays (and would use a stale IX: `JP $066E` skips `$0913`) |

## Sound effects

**ADPCM-A one-shots** (prefix commands, `$02A9`-`$034B`). Each slot has an enable bitmap (`$0E58`: bit 7-(code & 7)
of byte code >> 3; slot 0 `$4178`, 1 `$4198`, 2 and 3 `$41B8`, 4 `$41D8`; codes below `$10` are refused, `$01EA`) and
a table of 11-byte records, slot 0 `$41EA`, 1 `$4BA0`, 2 `$5509`, 3 `$5F59`, 4 `$69A9` (+ 11 × code):
`[priority][start16][end16][loop count][loop start16][loop end16][pan|level]`, addresses in 256-byte units. Example
`$18` `$B9` (slot 0): `70 2800 28E8 00 0000 FFFF DA`. Allocation (`$0504`): three effect channels, ADPCM-A 4-6
(states `$FBEC`/`$FBF6`/`$FC00`, 10 bytes: one-shot busy + priority at +0/+2, sequenced busy + priority at +7/+8):
a free channel wins (in the order A4, A5, A6); else the first channel whose running sound has a priority **value
greater than or equal to** the new one's (`$0531`: `JR C` skips the channel when the running value is lower): **a
lower value is the stronger sound** (records hold `$01` ... `$70`); else the sound is dropped. The music has no say:
the allocator looks at the effect states only, and an effect always takes ADPCM-A 4-6 from the music. The key-on
(`$034B`): level `$08+ch` = record +10, dump, flag reset, start / end (with a loop count: start → loop end, and the
end-of-sample poll `$03F3` replays loop start → loop end, then the tail; `$FF` = for ever), ADPCM-A master volume
`b $01` = `$3F` when no song runs (`$FE2C`), key-on. Music notes on ADPCM-A 4-6 are skipped while an effect owns the
channel (`$162F`). In 11 minutes of attract mode the game sent `$1A` 425 times, `$1C` 91, `$1E` 69, `$18` 37 (measured).

**Sequenced ADPCM-A effects** (type 3, `$F0-$F4` → `$056F`): header `$6F8C`[cmd - `$F0`]: `[priority][stream16]
[flags]`; allocated like the one-shots, then played by the song interpreter on channel blocks `$FDEC`/`$FDFC`/`$FE0C`
(ids `$0B-$0D`) at timer A's rate. Measured `$F0`: ADPCM-A 4, a sample re-keyed every ~2 s with its level stepped
`$C3` → `$DF` over 2 s.

**ADPCM-B effects** (`$19` + code → `$0661`): 16-byte records at `$6FD6` + 16 × code `[priority][start16][end16]
[loop count][loop start16][loop end16][delta-N16][volume]`; refused when the running one's priority value is lower (`$068B`, `$FCD3`); key-on
`$11` = `$C0`, `$1B` = volume, reset, delta-N, start / end, `$10` = `$80` (measured `$19` `$40`: those writes, then
`$10` = 0 when it ended 2 s later). The sequenced ADPCM-B path (`$0973`, `$FC38`) is never called.

**SSG effect songs** (type 5, `$60-$65`, `$7F` → `$0A05`): header `$3AF0`[cmd - `$60`]: `[priority][4 stream16]
[4 flags][noise bits]`, played on blocks `$FD9C`/`$FDAC`/`$FDBC` (SSG A-C, ids 5-7) and `$FDCC` (id 0, the noise
period) by the song interpreter at timer A's rate; refused when the running one's priority value is lower (`$0A3F`). `$7F` is
exempt from the effects mute (`$7F0E` = `$7F`, compared in every effect path) and marks itself `$FE44` = 4.
Measured: each of `$60-$65`, `$7F` sent alone writes SSG registers only, for 0.15 s (`$60`, `$63`) to 1.8 s (`$65`).
Opcode `$5F` adds a pitch sweep on SSG A-C (`$1403`, records `$F806`/`$F811`/`$F81C`).

So FF3's split is KOF98's: **FM + ADPCM for music, ADPCM-A 4-6 for fight sounds (shared with the music: the
effect always wins), ADPCM-B one-shots, SSG for generated cues**.

## The two clocks (interrupt handler `$212B`)

The handler reads the ADPCM end flags (port `$06`, `$2144`): ADPCM-B end → `$0870` (loop replay or `$10` = 0),
ADPCM-A 6..1 ends → `$03F3` (`$1C` flag reset, loop replay or tail, effect channel release). Then the timer status
(port `$04`, `$218A`): **bit 1 (timer B) → the music**, else timer A:

- **Timer B = the music's tempo.** Its value is the song header's tempo byte (`$11F3` → `$2B75`: reg `$26`), changed
  by opcode `$33` or command `$0E`. One music tick per timer-B interrupt, no accumulator: **ticks/s = 1 / (288 µs ×
  (256 - TB))**. Songs use TB `$62-$CF`: 21.98 to 70.86 ticks/s (`$3E`, TB `$C6`: 59.87/s; measured 59.886/s).
  `$2243`: if the music runs (`$FE2D`): fade step (`$1AFC`, while `$FE27`), then the 11 music channels in block
  order FM1-4 (`$FCEC`...), ADPCM-A 1-6 (`$FD2C`...), ADPCM-B (`$FD8C`) through `$2334`, each followed by its fade
  refresh while fading. Ends with `$27` = `$2F` (`$1894`: timer B flag reset).
- **Timer A = 54.3 Hz** (value 1: 1023 × 18 µs = 18.41 ms; measured 54.32/s) for everything else (`$2194`): SSG
  sweeps (`$1403`), the music's ADPCM-B pitch / level effects (`$1F2B`, `$1E6F`), a dead ADPCM-B volume slide (`$209A`),
  the FM software vibrato of FM1-4 (`$1C8E`), then the SSG effect song (`$FD9C`...`$FDCC`, while `$FE1C`), the
  sequenced ADPCM-A effects (`$FDEC`...) and a sequenced ADPCM-B effect (`$FDDC`, never started). Ends with `$27` =
  `$1F` (timer A flag reset). Opcode `$37` could change timer A; no song does.
- **No interrupt is lost.** The handler runs with interrupts off and resets only the flag it served; when both flags
  are set (status 3), timer B is served and the still-set timer-A flag raises the next interrupt at once. Measured over
  all 40 song captures: 151153 timer-A, 125672 timer-B and 2082 both-set interrupts, every both-set one followed by
  a timer-A one; music ticks / s match 1 / (288 µs × (256 - TB)) to 0.03 %. (KOF98 drops nested interrupts.)

## Songs

Music command → `$111B`: refused while `$FE34` (music mute); if no ADPCM-B effect plays, ADPCM-B reset (`$10` = 1, 0);
`$FE2D` = `$FE2C` = `$FF`; bank map `$2E00`[song]; `$FEF8` = word `$3B30`[song] (the song's ADPCM-A sample records);
header IX = word `$3A70`[song]; FM keys off (`$0B2E`); loop and call depths of the 11 channels cleared; timer B =
header `+$17`; per channel gate mode 7 (`$2B63`), status 0, flags, stream pointer (also the restart point); FM pan
shadows `$B5`/`$B6` = `$C0` (no write); unless fading: `$FABE+1` = header `+$18`, `+7` = `+$1A`, `+6` = `+$19` and
`b $01` = `+$19`; fade accumulator cleared; `$27` = `$2F`. **Volume, attenuation, transposition, octave shift, detune
and the ADPCM-B mode of each channel are not reset: they carry over from the previous song** (after a reset: 0).

Header (48 bytes, IX = song pointer):

| Offset | Content |
|---|---|
| `+$00` | not read |
| `+$01..+$16` | 11 stream pointers (16-bit LE), channel order FM1-4, ADPCM-A 1-6, ADPCM-B |
| `+$17` | tempo = timer B value |
| `+$18` | FM attenuation added to every TL (`$FABE+1`) |
| `+$19` | ADPCM-A master volume, reg `$01` (`$FABE+6`; `$3F` in the songs) |
| `+$1A` | ADPCM-B volume base (`$FABE+7`) |
| `+$1B, +$1D ... +$2F` | per channel: bit 0 = channel on (OR `$C0`: pan L+R); the bytes between are not read |

### Channel block (16 bytes, `$FCEC` + 16 × n)

| Offset | Meaning |
|---|---|
| `+$00` | status: bit 0 note running, bit 1 gate running, bit 2 rest, bit 3 tie (no key-off / no restart), bits 7-4 = key-on bits (`$F0` after a note) |
| `+$01` | bit 0 channel on, bits 7-6 pan |
| `+$02` | volume (patch-change byte 1, or `$56`) |
| `+$03` | attenuation of the current note (note flag byte & `$3F`) |
| `+$04` / `+$05` | gate countdown / the rest after it |
| `+$06` | note code (low nibble of the note byte) |
| `+$07` | transposition, semitones (`$3A`) |
| `+$08` | ADPCM-B mode (`$46`) |
| `+$09/$0A`, `+$0B/$0C` | stream pointer, restart point |
| `+$0D` | note byte & `$F0` (FM / ADPCM-B: octave), or the whole note byte (ADPCM-A: sample number) |
| `+$0E` | octave shift (patch-change byte 2) |
| `+$0F` | F-number detune (patch-change byte 3) |

Loop stacks at `$F827` + 16 × id (depth byte + five 3-byte entries `[count][address]`), call stacks at `$F957` +
16 × id (depth + five return addresses in 3-byte slots); id = channel id (FM 1-4, ADPCM-A 8-13, ADPCM-B 14; the
timer-A channels `$0B-$0D` use ids `$12`, `$11`, `$0F`: `$2A54`).

### The tick state machine (`$2334`)

Channel off (`+1` bit 0 clear): nothing. Note running (bit 0): if the gate runs (bit 1), count `+4` down; at 0 clear
bit 1, and if a rest follows (`+5` ≠ 0) key off (unless tie) and wait; else go on as below. Rest running: count `+5`
down; at 0: clear bit 0 and read the next events (**no key-off at the end of the length**: the gate already did it, or
there was none). Reading (`$234C`): status = (status & 8) | `$F3`, events through `$24EC` until a note or a rest, then
the output (`$2366`). Expired counters are 0 (DEC to 0), unlike KOF98's.

### Stream encoding (`$24EC`)

| First byte | Event |
|---|---|
| `$01-$30` | note or rest of that length; `$00` = escape: the next byte is the length (0-255) |
| `$31-$5F` | opcode (jump table `$25FA`, 3-byte JPs) |
| `$60-$7F` | **hangs** the driver: `$24EC` jumps back to itself without advancing, inside the interrupt (never used) |
| `$80-$FF` | patch change, then up to three modifier bytes **with bit 7 set**, positional (`$250A`) |

Note / rest: `[length][flags][note]`:
- flags bit 6 = **rest** (`$25CF`: status = (status & `$0F`) | 4; the note byte is skipped);
- flags bit 7 clear = **tie** (status bit 3; `$2591`): no key-off before this note, FM key-on without key-off (a slur:
  the envelope continues), ADPCM-A level only (the sample keeps playing), ADPCM-B pitch + volume only (`$083E`);
- flags bits 5-0 = attenuation (`+3`);
- note byte, FM and ADPCM-B: bits 7-5 = octave (the YM block), bits 3-0 = note code, bit 4 never set; ADPCM-A: the
  sample number.

Note codes are the F-number table's own index (`$7F0F`): **the natural notes A-F are the hex digits A-F, G = 0, and
the sharps C# D# F# G# A# = 1 2 4 5 6** (3, 7-9 unused). So `$4C` = C2 (block 2, code C), `$40` = G2,
`$2A` = A1.

**Length → gate** (`$2B21`, gate mode = `$FCDD`[id], opcode `$3D`, 7 after a song start): mode 7: gate = length;
else gate = (length >> 3) × (mode + 1) (8-bit), and for lengths below 8 the table `$2CA3`[length][mode]; rest =
length - gate. So mode m plays (m + 1) / 8 of each note (quantize / staccato). A note's whole length is gate + rest:
the next event is read when both have run.

Patch change `$80+p` (`$18A4`, `$1A8C`): FM channels load patch p (below); other channels nothing. Modifier bytes, in
this order, each only if bit 7 is set: (1) volume `+2` = b - `$88` (FM), b - `$80` (ADPCM-A; ignored while fading),
b - `$B8` (ADPCM-B); (2) octave shift `+E` = ±(b & `$0E`) / 2 octaves (bit 0 = minus), in `$20` units; (3) detune
`+F` = b - `$B8`, signed F-number units (the songs write `$B8` = 0, `$BB` = +3 ...). A following patch-change byte
would be taken as a modifier (bit 7 set): the songs never put two in a row.

## Opcodes (`$25FA`, opcode - `$30`)

Static census: events in the song data reachable from the 40 music commands, each byte once (12235 notes, 1852
rests, 713 patch changes).

| Op | Params | Handler | What | Uses |
|---|---|---|---|---|
| `$3C` `$3E` `$48` `$49` `$4A` | 0 | `$268A` | no-op (the table's entry for `$30` is unreachable: `$30` is a length) | |
| `$31` `$32` | count | `$2A3B` | loop start: push (count, here); 5 deep | 436 + 12 |
| `$34` `$38` | 0 | `$2A93` | loop end: count down the top entry, jump back while ≠ 0, else pop | 423 + 8 |
| `$33` | TB | `$281E` | tempo: timer B (reg `$26`) | 39 |
| `$35` | addr16 | `$2AAF` | call (5 deep) | 351 |
| `$36` | 0 | `$2AC8` | return; **with an empty call stack: nothing** (the songs use one block both inline and as a subroutine) | 215 |
| `$37` | lo, hi | `$2827` | timer A: reg `$25` = lo, `$24` = hi | |
| `$39` | addr16 | `$2A35` | goto | 75 |
| `$3A` | p | `$2B18` | transposition `+7` = p - `$88` semitones | |
| `$3B` | code | `$2AE0` | ADPCM-A effect `code`, slot 0 (`$02A9`) | |
| `$3D` | mode | `$2B02` | gate mode & 7 | 20 |
| `$3F` | speed | `$2B0C` | **fade out** (as command `$0A`) | 1 |
| `$40` | 0 | `$29F3` | **end of song**: FM keys off, ADPCM-B reset, `b $00` = `$87` (dump ADPCM-A 1-3), `b $01` = `$3F`, music off, **end of the interrupt** (`LD SP,($FE24)`: the channels after it skip the tick) | 67 |
| `$41` | 0 | `$29EF` | `DI` + `HALT`: stops the sound CPU | |
| `$42` | 0 | `$2A27` | go to the channel's start | 27 |
| `$43` | code | `$2AF1` | ADPCM-B effect `code` (`$0661`) | |
| `$44` | p | `$294F` | pan, p & 3: 1 right, 2 left, 3 both. FM: `$B4` shadow & `$3F` \| pan written now; ADPCM-A: the level shadow only (next key-on); ADPCM-B: `+1` (next key-on) | 1002 |
| `$45` | 0 | `$2949` | `$FC41` = 0 (ADPCM-B loop count) | |
| `$46` | p | `$2902` | ADPCM-B mode: p < `$40` kit; `$40-$7F` one sample (number `$7C06`[p - `$40`]), pitched; `$80-$BF` one sample per octave (table `$7CC6` + 8 (p - `$80`)); p ≥ `$C0` nothing | 203 |
| `$47` | song | `$28F6` | **start song** (`$111F`; the channels' settings carry over), end of the interrupt | 16 |
| `$4B` | 8 bytes | `$2898` | ADPCM-B pitch effect parameters (`$FA8F`-`$FA97`) | |
| `$4C` | p | `$288A` | `$FC36` = p: ADPCM-B pitch effect on | 1 (song `$2A`; no effect follows: `$FA96` = 0) |
| `$4D` | 0 | `$293A` | clear the ADPCM-A loop counts | |
| `$4E` | p | `$2881` | reg `$22` (LFO) | 55 |
| `$4F` | p | `$286D` | `$FC3D`[id - 1] = p: FM software vibrato off (≠ 0) | |
| `$50` | reg, val | `$2864` | any port-A register | |
| `$51` | p | `$285D` | `$FE1E` = SSG noise bits | |
| `$52` `$5D` | p | `$2891` `$26FC` | `$FC37` = p | |
| `$53` | 3 | `$2845` | SSG envelope regs `$0D`, `$0B`, `$0C` | |
| `$54` | p | `$280D` | SSG effect song p (`$0A0C`) | |
| `$55` | 0 | `$27F3` | end of an SSG effect song, end of the interrupt | |
| `$56` | p | `$27EA` | volume `+2` = p - `$80` | |
| `$57` | 5 bytes | `$279E` | ADPCM-B level effect parameters | |
| `$58` | p | `$278B` | `$FC34` (or `$FC35`) = p | |
| `$59` | 0 | `$276A` | ADPCM-B effect off, reset | |
| `$5A` | 0 | `$2714` | end of a sequenced ADPCM-A effect (ids `$0B-$0D`; on any other channel it releases ADPCM-A 4) | |
| `$5B` | p | `$270A` | `$FA88` = `$FC3C` = p: ADPCM-B level effect on | |
| `$5C` | p | `$2703` | `$FA89` = p | |
| `$5E` | p | `$26F5` | `$FE22` = p (speed of the dead volume slide) | |
| `$5F` | p | `$268C` | SSG pitch sweep (SSG A-C only; **on other channels p is not consumed**: it is read as the next event) | |

47 opcodes `$31-$5F`: 5 no-ops and 40 other handler addresses (`$31`/`$32` and `$34`/`$38` share one; `$52` and `$5D`
are two copies of the same code). Songs use 17 of them (the "Uses" column), all in the
validated captures. song.py models those and `$37`, `$3A`, `$41`, `$4F`, `$50`, `$55`, `$56`; the others it
lists as events without effect on its writes.

## Output stage (`$2366`, after the events of a tick)

### FM (`$2372`)

1. TL = `$FABE+1` (header `+$18`) + volume `+2` + attenuation `+3` (the first add's carry is lost), `$7F` if the
   second add carries or reaches `$7F`; written to the **carriers only** (`$2BC3`, masks `$2C8D` by algorithm: alg 0-3
   S4; 4 S2, S4; 5-6 S2, S3, S4; 7 all), order `$40`, `$48`, `$44`, `$4C`. Also for a rest.
2. Unless tie: key-off `$28` = channel (`$17A8` → `$14B5` with D = 0).
3. `$14B5`: `$28` = channel | D (D = status & `$F0`: `$F0` for a note, 0 for a rest: a rest writes key-off twice).
   On a key-on, **then** the F-number: `$A4+ch` = block << 3 | F-number high, `$A0+ch` = low (shadowed `+$70`/`+$74`
   for the vibrato), then the vibrato restart (`$1E3D`).

Pitch (`$2459` → `$20CF`): semitone = `$20EB`[code]; index = semitone + transposition, signed, into `$2113`
(48 bytes: octaves -2 ... +1, each entry octave << 5 | F-number index); byte = octave shift + (note & `$F0`) + entry;
block = byte >> 5, F-number = `$7F0F`[byte & `$1F`] + detune (signed). F-numbers C 618, C# 655, D 694, D# 735, E 779,
F 825, F# 874, G 926, G# 981, A 1040, A# 1102, B 1167 (C4 = block 4 = 261.6 Hz, as KOF98). Entries 16-31 of
`$7F0F` are SSG periods (the table is shared with `$7F2F`).

### FM patch (52 bytes at `$2E40` + 52p, `$18A4`)

| Bytes | Content (operators 1-4 = S1-S4) |
|---|---|
| 0, 1 | feedback, algorithm → `$B0` = FB << 3 \| ALG |
| 2-5 / 6-9 | DT (-1..-3 stored as `$FF..$FD`, written 5-7: `$1A27`) / MUL → `$30` |
| 10-13 | TL (modulators only; carriers keep the TL last written) |
| 14-17 / 18-21 | KS / AR → `$50` |
| 22-25 | DR → `$60`, with AM from byte 51 |
| 26-29 | SR → `$70` |
| 30-33 / 34-37 | SL / RR → `$80` |
| 38-41 | SSG-EG → `$90` |
| 42-48 | software vibrato: type, delay, step16, count, signed step (depth = count × step), speed (`$1A2C`) |
| 49 | not read |
| 50 | AMS/PMS → `$B4` (pan bits kept from the shadow) |
| 51 | AM enable, bit n = operator n + 1 |

The fields are unpacked into a register shadow (`$FADE` port A / `$FB65` port B, + reg - `$30`) and the 30 registers
written from it (`$1A8C`: `$30`-`$9C` by register, slots S1 S3 S2 S4, then `$B0`, `$B4`). No patch of the 60 sets a
vibrato depth: the songs' only modulation is the hardware LFO (`$4E` + AMS/PMS, patches 0, 2, 4, 10, 11, 20, 24, ...).

### ADPCM-A (`$23C9` → `$162F`)

Level = volume `+2` - attenuation `+3` (0 if negative; not masked to 5 bits) | pan → `b $08+ch` (skipped while
fading). Rest → dump (`b $00` = `$80` | bit, `$1C` = bit, `$1C` = 0). Tie → nothing more. Note → record
`$FEF8` + 11 × sample (the effect record format; the songs use the tables of slot 0, `$41EA`, and slot 4, `$69A9`):
dump, flag reset, start, end (or loop end), key-on (`$0359`). Gate end → dump; no key-off at the end of the length.

### ADPCM-B (`$23EA` → `$1683`)

Volume = header `+$1A` + volume `+2` (carry lost) - 3 × attenuation, floor 0 (`$2404`). By mode (`$46`): kit (1): the
note byte is the record number, delta-N from the record (`+$0A`); one pitched sample (2): delta-N `$7C46`[((octave -
2) × 16) + code]; per-octave samples (0, the reset default; no song keys a note in it): sample from the octave's table byte, delta-N `$7CCE`[octave × 16 +
code]. Records `$6FD6` + 16n. Key-on (`$077D`): `$11`, `$14`, `$15` = 0, `$10` = 1, `$1C` = `$80`, 0, `$10` = 0,
delta-N `$19`/`$1A`, start `$12`/`$13`, end `$14`/`$15` (+ loop end again for a looping record), `$1B` = volume
(unless the level effect runs), `$10` = `$80`; then pan `$11` = `+1` & `$C0` (`$2437`). Tie: `$1B`, `$19`, `$1A`,
pan. Rest or gate end: `$11` = 0.

### Effects

- **FM software vibrato** (`$1C8E`, timer A, record `$FC83` + 16 × channel): types 0 saw, 1 square, 2 triangle,
  3 triangle gated by ROM bytes `$00xx`, 4 jump to depth then ramp down once, 5+ one hump; delay, speed; output
  `$A4`/`$A0` = shadow F-number + value. Unused (no patch depth).
- **ADPCM-B pitch / level effects** (`$1F2B`, `$1E6F`, timer A, parameters by `$4B` / `$57`): unused by the songs.
- **Fade** (command `$0A`, opcode `$3F`; `$1AFC` at each music tick): `$FE38` += speed; on each carry `$FE39` -= 1,
  and a step when it was not 0 (so the first carry does nothing): FM attenuation `$FABE+1` + 1 (past `$3C`: the six
  ADPCM-A channels are switched off; past `$5A`: `$7E`, FM done), ADPCM-A volumes - 1 (channel off at 0), ADPCM-B
  volume - 5 and base - 6 (B done at 0); when FM and B are done the song stops (`$1C7F` → `$29F4`, end of the
  interrupt). While fading, every channel's level is rewritten after its tick (FM TL `$1BE5`, channel off at `$7F`;
  ADPCM-A level `$1C07`, floor 1; ADPCM-B volume `$1C46`). Song `$44` fades itself (validated).

## Driver bugs and quirks

- Prefix arguments `$01`, `$03`, `$10` act as system commands (NMI, measured).
- `$60-$7F` in a stream hangs the interrupt handler; `$41` halts the CPU; `$5F` on a non-SSG channel leaves its byte
  to be read as an event (`$269C`). None occurs in the songs.
- `$1D` (ADPCM-B effect, bitmap empty) would use a stale IX; the sequenced ADPCM-B effect `$0973` is unreachable;
  the ADPCM-B volume slide `$209A` is dead (`$FE21` is only ever cleared); type 4 has no command.
- `$5A` outside a sequenced ADPCM-A effect falls into the ADPCM-A 4 release (`$2724`).
- SSG sweep step: `$1465` loads `+5`, then overwrites it with 3.
- The patch's vibrato type-3 randomness reads the code at `$0000-$00FF` (as KOF98).
- A song start does not reset the channels' volume, transposition, octave shift, detune or ADPCM-B mode: a song that
  does not set them inherits the previous song's. In the three chains it only changes a few TL writes of the first
  tick (model: `$33` after `$36`: 2 writes differ from `$33` alone, `$32` after `$37`: 13, `$42` after `$41`: 0).
- Reply byte = command, + 1 on every 128th command (`$01F9`, purpose unknown).

## Validation (tools/makoto3)

- `capture.py`: our emulator's core (Geolith) driven from Python with a Z80 port tap added to the core
  (`geo_z80.c`: `geo_z80_port_tap`; `libretro.c`: `retro_neoscan_z80_tap`, `retro_neoscan_z80_ram`,
  `retro_neoscan_sound_cmd`; built to `/data/tmp/snd98/ff3/geolith_tap.so`, not installed): every YM2610 write,
  every command the Z80 reads, an `i` line per interrupt (the handler's status read), the game's own commands blocked
  after its `$07`, a song sent at frame 900. `--songs` captures every music command to its loop point or end + 15 %.
- `song.py`: decoder + model (the code above), driven by the captured interrupt order (A / B); `regs.py`:
  the model's register writes and the comparison, interrupt by interrupt, same values, same order (left out on both
  sides: `$27` timer flags, `$1C` end-flag resets and ADPCM-B `$10` = 0, which the end-of-sample poll also writes).
- **All 40 music commands: every interrupt with writes identical (32417 of 32417), 0 differing**; song `$2A`'s 88
  ADPCM-A loop replays (written by the end-of-sample poll, timed by the sample length) are each the predicted loop
  region of the sample playing on that channel. Per song in `ff3_songs.md`.
- Not validated: the opcodes no song uses, the software vibrato, the ADPCM-B effects (no song runs them).

## KOF94's build

The King of Fighters '94's M ROM (`/data/roms/kof94.neo`, 128 KB; copy `/data/neogeo_dict/sound/kof94/kof94_m1.bin`,
disassembly `drv.asm` there) carries the same signature, `Ver 3.0 by MAKOTO.04/03/10 to SK`, and is the same driver:
an instruction-by-instruction diff of `$0000-$2E3F` (both disassembled, absolute operands below `$F800` masked, then
aligned) leaves only the differences below; every matched instruction's code operands point to the matching
instruction. **The music engine is the same code**: from the song start on (`$111B`) every routine is FF3's, shifted
by a constant, with the same RAM layout (`$F800-$FFFF` addresses identical), the same tables in the code area
(semitones `$20EB`, pitch `$2113`, carriers `$2C8D`, timers `$2C95`, gate `$2CA3`, reply `$2CE9`: byte-identical) and
the same opcode table; the model runs both builds from one code path (tools/makoto3, `games.py` lists each build's
table addresses) and matches KOF94's real driver on every interrupt (below).

Address map (FF3 → KOF94): `$0000-$0133` same; `$0137` → `$0133`; system commands `$0CA3` → `$0C7A`; song start
`$111B` → `$10AC` (-`$6F`); `$13D6`-`$189B` -`$94` (`$14B5` → `$1421`, `$162F` → `$159B`, `$1683` → `$15EF`); from
`$18A4` on -`$95` (`$18A4` → `$180F`, interrupt handler `$212B` → `$2096`, music tick `$2243` → `$21AE`, channel
`$2334` → `$229F`, events `$24EC` → `$2457`, opcode table `$25FA` → `$2565`, register writes `$2BAD` → `$2B18`).
NMI `$0066` is the same routine; its system-command trampolines moved with the code (`$0D00`/`$0D0E`/`$0D1C` →
`$0CD1`/`$0CDF`/`$0CED`).

Tables (FF3 → KOF94): command types `$7D8E` → `$6907`; song headers `$3A70` → `$3B40`; song bank bytes `$2E00` (same);
FM patches `$2E40` (same address, 64 slots up to `$3B3F`; FF3 60); SSG effect headers `$3AF0` → `$3BC0`; ADPCM-A
effect bitmaps `$4178`/`$4198`/`$41B8` → `$3E13`/`$3E33`/`$3E53`, records `$41EA`/`$4BA0`/`$5509` → `$3E73`/`$4973`/
`$5473`; sequenced ADPCM-A effect headers `$6F8C` → `$5EC3`; ADPCM-B effect bitmaps `$6F96`/`$6FB6` → `$5EE3`/`$5F03`;
ADPCM-B records `$6FD6` → `$5F23` (26 bytes, below) and `$6659`; opcode `$46` tables `$7C06` → `$6693`, `$7CC6` →
`$6757`; delta-N `$7C46` → `$66D3`, `$7CCE` → `$6807`; mute exemption `$7F0E` → `$6A87` (`$7F` in both); F-numbers
`$7F0F` → `$6A88`; SSG periods `$7F2F` → `$6AC8`.

Functional differences, all read from the code:

| Area | FF3 | KOF94 |
|---|---|---|
| Music ADPCM-A samples | per-song table: `$111B` sets `$FEF8` = word `$3B30`[song] | **one table for every song**: the note key-on calls `$0447` (FF3's `$04EF` read `$FEF8`) = effect slot 0's records `$3E73`; `$3B30` / `$FEF8` gone |
| Bank maps | three: byte 0 identity, 1 `$10000`, 2 `$18000` (`$1161` `CP $02`) | two: 0 identity, any other byte `$10000-$17FFF` (the `CP $02` branch is gone) |
| ADPCM-B records | 16 bytes; a music note clears the B pitch / level effect parameters (`$16FB` → `$0949`: zeros to `$FA8F-$FAA1`) | **26 bytes**: + `$0D..$19` = those parameters, and a music note loads them from the record (`$1667` → `$08F8`). Every KOF94 record holds 0 there (and `$30` at `+$0E`), so the effects stay off: validated, no effect writes |
| ADPCM-B effect (`$19` + code) | key-on pan `$11` = `$C0` (`$06C6`); the sequenced B effect `$0973` unreachable | pan from record `+$0E` bits 5-4 (`$0655`); code ≥ `$F0` starts a sequenced B effect (header table `$6673`, `$05E0` → `$094A`). The 68K never sends `$19` (no `$19xx` word in its command table, below) |
| ADPCM-A effect slots | five: prefixes `$18` `$1A` `$1C` `$1E` `$1B` | **three**: `$18` `$1A` `$1C` (bitmaps / records above); `$1B` has type 0 (ignored) |
| Commands `$1D`, `$1E` | `$1D` dead B effect, `$1E` slot-3 effect | type 1, but the jump table `$0C7A` has 29 entries (`$00-$1C`): `JP (HL)` lands on the NMI trampolines, `$1D` at `$0CD1` (the `$01` path: park the Z80), `$1E` at `$0CD4` (the same minus the port-`$0C` write). *(inferred, not run)* |
| Sequenced ADPCM-A effects | type 3 = `$F0-$F4`, `CP $F0` / `SUB $F0` | `CP $FF` / `SUB $FF`, and no command has type 3: unreachable |
| ROM check at reset | the bank self-test result is overwritten: `$FEB3` = 1 (`$0113`, `$011D`, `$01AA` `LD A,$01`), so `$0194`'s jump into bank `$1E` never runs; bank `$1E` at `$EEDC` is `$FF` | `$FEB3` keeps the result, and when it is 0 `$0190` jumps into bank `$1E` (`$1EEDC`): 13 code bytes at word `$00AC` (= `$0195`) compared with a copy stored there, the result (`SBC HL,DE`) back in `$FEB3` (`$01A2`). Measured `$FEB3` = 0 after boot |
| Reply byte | `$FEB3` = 1, so the reply is always the command (+1 every 128th) | with `$FEB3` = 0 (measured) the reply is the table byte `$2C54`[cmd] (`$016C`, `$0216`, `$0276`): a check the 68K can read *(purpose inferred)* |
| `RST $08` / `$10` busy-wait | `$189C`: three `NOP`s, `RET` | `$1807` / `$1808`: `PUSH HL`, `POP HL`, `RET` (timing only) |
| F-number table entries 16-31 | SSG periods (the table is shared with `$7F2F`) | a second FM scale ~48 cents sharp (926 → 952 ...; SSG periods at `$6AC8`): reachable by an FM note byte with bit 4 set, which no song has |
| Command map | music `$20-$34`, `$36-$37`, `$3A-$3B`, `$3D-$47`, `$4A-$4C`, `$5F` (40) | music `$20-$2D`, `$30-$32`, `$34`, `$35`, `$40`, `$41`, `$50-$55`, `$5F` (28); SSG effect songs `$60`, `$61`, `$6A`, `$7F`; system `$00-$1E` except `$1B` |

The model needed only the table addresses, the 26-byte ADPCM-B record stride and the fixed ADPCM-A table
(`tools/makoto3/games.py`). Validation: **all 28 KOF94 music commands, 15571 of 15571 interrupts with writes
identical, 231754 captured writes, 0 differing** (per song in `kof94_songs.md`); FF3 re-captured with the renamed tools
still 32417 / 32417.

The song data has nothing in common with FF3's except the boot jingle `$5F` (same notes and structure, other patch
numbers for identical patches and a 2-step lower volume byte); 19 of the 60 FF3 patches have a byte-identical
KOF94 patch.

### What the 68000 sends (KOF94)

The sound routine `$6536` (once per frame) takes the next byte of a queue at `$108000` + `$38C4`
(`a5` = `$108000`; write index `$38BC`, read index `$38BD`), skips `$00`, drops `$01` (never sent), and writes it to
`REG_SOUND` (`move.b d0,$320000`, `$6556`): **one byte per frame**. Requests go through `$6588`: sound ID in `d0`,
the word `$51924`[ID] is queued as two bytes (high, low), so a word `$00xx` sends `xx` and `$1Axx` sends the effect
prefix `$1A` and its code. ID table: music IDs `$0C` → `$20`, `$10-$18` → `$21-$29`, `$19-$1B` → `$30-$32`, `$1C` →
`$40`, `$1D` → `$41`, `$1E`/`$1F` → `$34`/`$35`, `$20-$22` → `$2A-$2C`, `$23` → `$41`, `$24` → `$2D`, `$25-$2A` →
`$50-$55`; `$00` = `$03` (hard reset), `$06` = `$07`, `$0B` = `$02`, `$0D-$0F` = `$0A $F0` / `$D0` / `$C0` (fades).
Feeders found by a static scan of the first MB (521 calls of `$6588`, 256 distinct constant IDs in `d0`, 30 calls with
`d0` from elsewhere): stage themes from the 9-word table `$3569E` indexed by `$1087DE` (`$10 $17 $15 $13 $16 $14 $12
$11 $18`: measured stage order Brazil, China, Japan, USA, Korea, Italy, Mexico, England, then `$29` = Rugal); the
opening from `$39374` by `$108836` (`$20 $26 $26 $25` → `$2A`, `$51`, `$51`, `$50`), or ID `$27` (`$52`) when
`REG_LSPCMODE` bit 3 is set (`$38936`); constant IDs for `$2B`-`$2D`, `$30`-`$32`, `$34`, `$35`, `$41` (`$23`), `$53`
(`$28`). **No constant or table reference found** for IDs `$0C` (`$20`), `$1C` (`$40`), `$1D` (`$41` through its first
ID), `$29`, `$2A` (`$54`, `$55`). That is not "unused": `$54` was measured (an ending, ID `$29`), so it is reached by an
ID computed at run time. Blind spots: IDs computed in registers (e.g. `$22236`: `$113` / `$228` + 3), IDs read from RAM
structures (`a4@(218)`, `a4@(112)`-indexed tables `$513A2`-`$516CC`, all effect IDs), the second P-ROM MB, and direct
`$320000` writes outside `$6556` (none found as instructions). Three ID-table words would send `$1E` (IDs `$2BA`,
`$2BC`, `$2BE`), none referenced by a constant.

## KOF95's build

The King of Fighters '95's M ROM (`/data/roms/kof95.neo`, 128 KB; copy `/data/neogeo_dict/sound/kof95/kof95_m1.bin`,
disassembly `drv.asm` there) carries the same signature, `Ver 3.0 by MAKOTO.04/03/10 to SK`, but is a more
reworked build than KOF94's: the code ends at `$266A` (FF3 `$2CE8`), 5004 instructions against KOF94's 5638.
Method: both builds disassembled, every 16-bit operand masked (RAM included), aligned instruction by instruction
(`/data/neogeo_dict/sound/kof95/scratch/codediff.py`, diffs against KOF94 and FF3 there): 431 differing blocks
against KOF94; those of the command path, the effects allocator and the music path read one by one, those of the
timer-A ADPCM-B pitch / level effects (unused by the songs) only skimmed. Most are rewrites with the same effect (`XOR A` → `LD A,$00`, `JR` → `JP`, `PUSH`/`POP` pairs dropped,
three-way branches folded into a shared subroutine, channel pointers loaded as constants instead of `ADD IY,DE`); the
functional differences are listed below. **The music engine (song start, tick state machine, events, every opcode
the songs use, output stage, patch load) behaves as FF3's**: the model needed table addresses and nothing else
to match all 27 songs on every interrupt (Validation, below; per song in `kof95_songs.md`).

Address map (FF3 → KOF95): NMI `$0066` (same); main loop `$0137` → `$0136` (ring read moved to a subroutine `$017D`,
also used by prefix arguments `$020A`); dispatch `$01C1` → `$01C4`; system commands `$0CA3` → word table `$0A11`;
song start `$111B` → `$0DA1` (`$1133` → `$0DB5`); ADPCM-A one-shot `$02A9` → `$0296`/`$02CD`, allocator `$0504` →
`$0417`/`$0446`; ADPCM-B effect `$0661` → `$0564`; FM keys off `$0B2E` → `$08D3`; FM key `$14B5` → `$10FB`; music
ADPCM-A note `$162F` → `$125A`; ADPCM-B note `$1683` → `$12C2`; patch load `$18A4` → `$1440`, register output `$1A8C`
→ `$1615`; fade step `$1AFC` → `$167B`; FM vibrato `$1C8E` → `$17BA`; pitch `$20CF` → `$1B74` (semitones `$1B8A`,
pitch table `$1BB2`); interrupt handler `$212B` → `$1BCA` (the music tick `$2243` is inline at `$1CA8`); channel
`$2334` → `$1D72`, output `$2366` → `$1DA6`; events `$24EC` → `$1F22`; opcode table `$25FA` → word table `$2014`;
end of song `$29F3` → `$235B`; loop / call `$2A3B` / `$2AAF` → `$23A1` / `$242E`; gate `$2B21` → `$24A9`;
register writes `$2BAD` / `$2BB8` → `$252D` / `$2538`.

Tables (FF3 → KOF95): command types `$7D8E` → `$72B4`; song headers `$3A70` → `$3B40`; per-song ADPCM-A sample
tables `$3B30` → `$3C00`; song bank bytes `$2E00` (same); FM patches `$2E40` (same, 64 slots); SSG effect headers
`$3AF0` → `$3BC0`; carriers `$2C8D` → `$260F`, timers `$2C95` → `$2617`, gate `$2CA3` → `$2625`, reply `$2CE9` →
`$2671` (all byte-identical); ADPCM-B records `$6FD6` → `$6BFB` (16 bytes, FF3's layout); opcode `$46` tables `$7C06`
→ `$702B`, `$7CC6` → `$70F3`; delta-N `$7C46` → `$706B`, `$7CCE` → `$71A3`; mute exemption `$7F0E` → `$7434` (`$7F`);
F-numbers `$7F0F` → `$7435` (byte-identical to KOF94's, the sharp second scale included); new: one-byte effect code
tables `$73B4` (ADPCM-B) and `$73F4` (ADPCM-A), both the identity 0-`$3F`.

RAM: the music state moved, the stacks did not. Command ring `$FE4A` → `$FE34` (write index `$FEB1` → `$FE94`, read
index `$FEB0` → `$FE93`); current command `$FE3D` → `$FE2A`; channel id `$FE3C` → `$FE29`; music running `$FE2D` →
`$FE1A`, song started `$FE2C` → `$FE19`, fade `$FE27` → `$FE17`; mutes `$FE34` / `$FE35` → `$FE21` / `$FE22`; saved
SP `$FE24` → `$FE15`; level block `$FABE` → `$FABD`; patch shadows `$FADE` / `$FB65` → `$FADD` / `$FB64`; effect
states `$FBEC` → `$FBEB`; channel blocks `$FCEC` + 16n → `$FCE0` + 16n (FM1 `$FCE0` ... ADPCM-B `$FD80`, SSG
`$FD90`-`$FDC0`, sequenced ADPCM-A `$FDE0`-`$FE00`); gate modes `$FCDD` → `$FCD1`; vibrato records `$FC83` → `$FC77`;
loop / call stacks `$F827` / `$F957` (same). Reply `$FEB8` → `$FE9B`, stored also at `$FEA3`, `$FEB3`, `$FEC3`,
`$FED3`: the main loop sends `$FEB3` to port `$0C` (`$0175`, `$0285`), the interrupt and the prefix read `$FE9B`
(`$1BD6`, `$023B`); `$FEA3`, `$FEC3`, `$FED3` are never read.

Functional differences, all read from the code:

| Area | FF3 / KOF94 | KOF95 |
|---|---|---|
| NMI | stores anything but `$00`, `$01`, `$03`, `$10`, tests `$00` last | tests `$00` first (`$006C`), same effect |
| Jump tables | system commands and opcodes: 3-byte `JP` tables, indexed without a range check | 2-byte word tables (`$0A11`, `$2014`); system commands `CP $20` / `RET NC` (`$0A01`), table of 32 |
| Command map | FF3: music 40, SSG `$60-$65` `$7F`, sequenced A `$F0-$F4`; KOF94: music 28 | music `$20-$2E`, `$30`, `$31`, `$33-$3A`, `$50`, `$5F` (27); SSG effect songs `$60-$65`, `$6A`, `$7F` (type 5); **`$80-$BF` one-byte ADPCM-B effects** (type 4); **`$C0-$FF` one-byte ADPCM-A effects** (type 3); `$32` type 0 |
| One-byte ADPCM-A effects | (prefix commands only) | `$C0-$FF` (`$028C`): code = `$73F4`[cmd - `$C0`] = 0-`$3F`, records of slot 0 (`$425B` + 11 × code), **no enable bitmap and no "code ≥ `$10`" test**; the game sends them all the time (4877 in our five runs, 51 of the 64 commands) |
| One-byte ADPCM-B effects | | `$80-$BF` (`$0557`): code = `$73B4`[cmd - `$80`], record `$6BFB` + 16 × code, played as the `$19` prefix's effect (`$0564`); never sent in our runs |
| Prefix effects | FF3: `$18 $1A $1C $1E $1B` + code (slots 0-4), `$19` B; KOF94: `$18 $1A $1C` | FF3's five slots and `$19` again (`$0ADC`-`$0B32`), through one bitmap test `$0B3F` (table `$0B71`): slot 0 bitmap `$41BB` / records `$425B` (147 codes enabled), 1 `$41DB` / `$4D5B` (238), 2 `$41FB` / `$5850` (none: these are the music's sample records), 3 `$421B` / `$6350` (136), 4 `$423B` / `$6B90` (none), `$19` `$6BBB` (none). In our runs the game used `$18`, `$1A`, `$1E` |
| Effect stop `$14` / `$15` + code | KOF94: slot 0 / any other slot | slot 0 / slot 1 only (`$0B9C`, `$0BC2`: state `+9` = slot) |
| `$1D`, `$1F` | FF3 `$1D` dead B effect; KOF94 `$1D` `$1E` past the table end (park the Z80) | nothing (`$0A76` `RET`) |
| ADPCM-A effect channel | the effect always wins: a free channel of A4-A6, else the first whose running priority value is ≥ the new one's (`$0504`) | **the music keeps its channels**: `$0446` first masks out every A4-A6 channel whose music block is on (`+1` bit 0, from the song header); all three on → the effect is refused. Among the rest: a free channel at once (order A4, A5, A6), else the one with the greatest running priority value ≥ the new one's (the weakest sound; the later channel on a tie) |
| Sequenced ADPCM-A effects | FF3 `$F0-$F4` (`$056F`); KOF94 unreachable | path kept (`$04B8`, headers `$6B9B`, all zero) but unreachable: the one-byte codes stop at `$3F`, and slot 0's bitmap (the only path with the `CP $F0` test, `$0296`) has no code ≥ `$F0` |
| Music ADPCM-A samples | FF3 per song (`$FEF8` = `$3B30`[song]); KOF94 one fixed table | per song again: `$0DF4` stores `$3C00`[song] in `$FEDB`, the note copies it to `$FEE2` (`$129E`). 25 songs point at `$5850`, `$20` and `$5F` (no ADPCM-A notes) at `$425B` |
| Timer-A channels | ids `$0B-$0D` share the music's note code; separate stack ids `$12 $11 $0F` | the same, with an explicit context flag: `$FC3A` = 1 while the timer-A part runs, 0 in the music tick (`$1C2B`, `$1CA8`); in timer-A context `$125A` keys a sequenced effect's notes from `$3C80`[effect - `$F0`] |
| Loop / call stacks | no depth check (FF3 doc: "5 deep"); stack index `id × 16` computed in 8 bits (`ADD A,A` × 4), so the timer-A ids `$10-$12` wrap to the stacks of ids 0-2 *(read from the code, not run: no song or reachable effect uses them)*; loop end with an empty stack: `DEC` from 0, then a jump through a stale entry | **depth limited to 4**: a loop start or call at depth 4 is skipped with its parameter bytes (`$23A7`, `$2434`); a loop end with an empty stack does nothing (`$2416`); the index is 16-bit (`RL D`, `$23CB`). Song `$29` has an unmatched loop end (ADPCM-A 3, `$B6A9`, ticks 3097 and 6937): harmless in KOF95, validated |
| ADPCM-B records | FF3 16 bytes; KOF94 26 (effect parameters per record) | 16 bytes; a music note clears the B pitch / level effect parameters (`$078C`, FF3's behaviour); a B effect key-on first saves them (`$077F`: `$FA89` → `$FAA3`, 16 bytes) |
| ADPCM-B effect key-on | FF3 pan `$C0`; KOF94 pan from the record | pan `$C0` (`$05B7`), volume record `+$0C` |
| Song start: ADPCM-B reset | when no ADPCM-B effect plays | when neither `$FE20` (B effect playing) nor `$FC37` is set (`$0DAB`) |
| Bank maps | FF3 three; KOF94 two | two (`$0DD8`: any non-zero byte = `$10000-$17FFF`) |
| Reset ROM check, reply | FF3: result overwritten (`$FEB3` = 1); KOF94: kept, reply from the table `$2C54` | FF3's: both outcomes set `$FE96` = 1 (`$0117`, `$0121`), so `$0197`'s jump into bank `$1E` never runs and the reply is the command (+1 every 128th, `$01FC`); the reply table `$2671` (KOF94's check table) is all 0 here |
| Opcode `$5E` | `$FE22` = p (speed of the dead ADPCM-B volume slide) | skips its byte, nothing else (`$20DC`); the slide `$209A` is gone from timer A |
| `RST $08` / `$10` | FF3 three `NOP`s; KOF94 `PUSH HL` / `POP HL` | `RST $08` = `RET` (no wait after the address write); `RST $10` → `$1433` (`PUSH IX`, `PUSH AF`, `POP AF`, `POP IX`: a wait after the data write) |
| `$0F`, `$7F` | end the SSG effect song unless `$7F` | the same (`$0CC6`, `$FE31` = 4 marks `$7F`) |

The model needed the table addresses (`tools/makoto3/games.py`) and, for faithfulness only, the depth-4 stack guard
(`stack_guard`: no song nests deeper than 2, so it changes no write). Validation: **all 27 KOF95 music commands, 17683 of
17683 interrupts with writes identical, 277711 captured writes, 0 differing**, including the chain `$25` → `$50`
(opcode `$47`) and `$24`'s tempo changes (the fade, rewritten as a loop over the six ADPCM-A channels at `$16B4`, is
not exercised: no KOF95 song fades itself); FF3 (32417 / 32417) and KOF94 (15571 / 15571) re-compared with the
extended tools, and FF3 `$2A` `$3E` and KOF94 `$25` `$51` re-captured: identical.

The M ROM's last 35438 bytes (`$17592-$1FFFF`) are byte-identical with KOF94's at the same offsets: KOF94's song data
left in place. KOF95's banks reach `$17FFF` and RAM covers `$F800` up, so only `$17592-$177FF` is visible to the Z80
(bank 1 `$F592-$F7FF`), and no KOF95 song points there *(inferred from the header table and the bank map)*.

### What the 68000 sends (KOF95)

The sound routine `$62F0` (called from `$39460`) takes the next byte of a queue at `$108000` + `$56B6` (write index
`$56AE`, read index `$56AF`), skips `$00`, drops `$01`, and writes it to `REG_SOUND` (`$6310`). Requests: `$6342`
(sound ID in `d0`: the word `$59A10`[ID] is queued as two bytes, high then low, so `$00xx` sends `xx` and `$1Axx`
sends a prefix and its code), `$6318` (only when the ID differs from the last one requested, `$56B0`), `$6328` (ID,
ID + 1 or ID + 2 by the object's distance across the screen: positional variants of an effect), `$6366` (per
character, table `$5967C`). Music IDs: `$478-$485` → `$21-$2E`, `$486` → `$2D`, `$487` → `$30`, `$488` → `$31`, `$489`
→ `$32` (type 0: the driver ignores it), `$48A` → `$0A $E0` (fade), `$48B` → `$20`, `$492-$499` → `$33-$3A`; `$06` =
`$07`, `$0B` = `$02`, `$00` = `$03`. Fight sounds go both ways: one-byte `$C0-$FF` commands (e.g. IDs `$0C-$25`; 4877 sent in our runs) and prefix pairs `$18` / `$1A` / `$1E` + code (5108).

A static scan of the first MB (811 calls with a constant `d0`, 29 without) finds constant references for every music
ID but `$479-$481`, `$489` and `$48B`. The stage themes `$479-$481` come from the 11-word table `$3B36C` indexed by
`$10A7E8`: `$24 $25 $22 $29 $23 $26 $27 $28 $2A $2A $2A`; measured in an arcade run, the index is the team of the
opponent's first fighter in the cast order (`tools/kof95/rom.py` CAST / 3: 0 Ikari, 1 Psycho Soldier, 2 Hero, 3
Rival, 4 Korea, 5 Fatal Fury, 6 Art of Fighting, 7 Women Fighters, 8 Saisyu / Omega Rugal), all 8 matches and the
Saisyu fight. So: **`$20` (ID `$48B`) has no reference** and is an empty song (no channel on): unused *(inferred)*;
**`$32` (ID `$489`)** is not a music command in this build and has no reference; `$50` has no ID: it is reached only
by `$25`'s chain. Blind spots: IDs computed in registers or read from RAM (the 29 calls), the second P-ROM MB, and
direct `$320000` writes (none found as instructions).

## Fatal Fury Special's build

Fatal Fury Special's M ROM (`/data/roms/fatfursp.neo`, 128 KB; copy `/data/neogeo_dict/sound/fatfursp/fatfursp_m1.bin`,
disassembly `drv.asm` there) carries the same signature, `Ver 3.0 by MAKOTO.04/03/10 to SK`, and its interrupt vector
is KOF94's (`JP $2096`). It is **KOF94's driver code with other tables**: the two code areas `$0000-$2BFF`
disassembled and aligned instruction by instruction with every 16-bit operand masked
(`/data/neogeo_dict/sound/kof95/scratch/codediff.py`, output in `/data/neogeo_dict/sound/fatfursp/scratch/k94_*`) give
5580 instructions on both sides and five differing instructions; every matched code or RAM operand is the same
address in both builds. So the 1993 game does not run an earlier MAKOTO version than KOF94 (1994): the two are one
build, differing in data (*inferred*: the code was carried over unchanged between the two games).

The five differences, all read from the code:

| Address | KOF94 | Fatal Fury Special | Effect |
|---|---|---|---|
| `$0014` | word `$59A7` | `$F907` | the ROM sum the `$10` self-test compares with (`$1062`) |
| `$02B9` / `$04EE` | `CP $FF` / `SUB $FF` | `CP $F0` / `SUB $F0` | an ADPCM-A effect code `$F0-$FF` starts a sequenced ADPCM-A effect (headers `$64F6`), as FF3 (KOF94: unreachable) |
| `$05E0` / `$094A` | `CP $F0` / `SUB $F0` | `CP $80` / `SUB $80` | an ADPCM-B effect code `$80-$FF` starts a sequenced ADPCM-B effect (headers `$7252`) |

Tables (KOF94 → Fatal Fury Special): command types `$6907` → `$74E2`; song headers `$3B40` → `$3F1C`; SSG effect
headers `$3BC0` → `$3F9C`; song bank bytes `$2E00` and FM patches `$2E40` (same addresses; 83 patches up to `$3F1B`);
ADPCM-A effect bitmaps `$3E13`/`$3E33`/`$3E53` → `$46AE`/`$46CE`/`$46EE`, records `$3E73`/`$4973`/`$5473` →
`$470E`/`$5111`/`$5B61` (`$470E`, slot 0's, is also the music's sample table: the note key-on `$0447`, as KOF94);
sequenced ADPCM-A effect headers `$5EC3` → `$64F6`; ADPCM-B effect bitmaps `$5EE3`/`$5F03` → `$6512`/`$6532`;
ADPCM-B records `$5F23` → `$6552` (KOF94's 26-byte layout); sequenced ADPCM-B headers `$6659`/`$6673` → `$7252`;
opcode `$46` tables `$6693` → `$7272`, `$6757` → `$7332`; delta-N `$66D3` → `$72B2`, `$6807` → `$73E2`; one-byte
effect code tables `$6A07` (ADPCM-B) → `$75E2`, `$6A47` (ADPCM-A) → `$7622`; mute exemption `$6A87` → `$7662`
(`$7F`); F-numbers `$6A88` → `$7663` (byte-identical, the sharp second scale included); SSG periods `$6AC8` → `$76A3`.

Command map (`$74E2`), the one functional difference that matters to the game: system `$00-$1E` except `$1B` (as
KOF94); **music** `$20`, `$23-$25`, `$2D-$3B`, `$3D`, `$42-$48`, `$5F` (28); SSG effect songs `$60-$69`, `$7F`;
**one-byte ADPCM-A effects** (type 3) `$C0-$E4`, `$FA-$FD`: code = `$7622`[cmd - `$C0`] (`$A0-$B7`, `$E5`, `$E8`,
`$64`, `$65`; `$FA` → `$F2`, a sequenced effect), records of slot 0; **one-byte ADPCM-B effects** (type 4) `$80-$90`,
`$A0`, `$B0-$BF`: code = `$75E2`[cmd - `$80`] (`$80-$8C` from `$B0`, `$BE`, `$BF` are sequenced effects). KOF94 has
the same one-byte paths (`$029F` → `$043C`, `$05D6` → `$08D5`) but no command of type 3 or 4.

The model needed the table addresses only (`tools/makoto3/games.py`; `game_of()` now also checks the type table the
dispatch loads at `$01C1`, since the interrupt vector alone cannot tell the two builds apart). Validation: **all 28
music commands, 29536 of 29536 interrupts with writes identical, 497007 captured writes, 0 differing**, including
`$3A`, which restarts itself with opcode `$47` (`capture.py` now ends such a capture after one pass + 15 %); per song
in `fatfursp_songs.md`. FF3 (32417 / 32417), KOF94 (15571 / 15571) and KOF95 (17683 / 17683) re-compared with the
changed tools: identical.

### What the 68000 sends (Fatal Fury Special)

Measured in our emulator: `$02` at frame 377 of a power-on (the NEO-GEO logo jingle `$5F`), `$07` (unlock) at 846,
the title `$47` at 860; the sound effects are prefix pairs (`$18`/`$1A`/`$1C` + code, as KOF94). The stage themes come
from the 16-word table at P ROM `$4B3C` (`$4B0E`: `jsr $2389E` with the word): `$30 $31 $32 $33 $34 $36 $37 $35 $42
$44 $38 $39 $3A $43 $3B $45`, the opponent's number in the order Terry, Andy, Joe, Big Bear, Jubei, Cheng, Kim, Mai,
Duck King, Tung Fu Rue, then six bosses (index 15 is followed by command `$FB`, `$4B30`). Measured: choosing each of
the ten opponents on the enemy select screen starts that opponent's entry (`docs/fatfursp_songs.md`); the word at
`$10B2EC` (`a5` = `$108000`, offset 13036) read when the theme starts holds the index + 1 (4 picks measured; *inferred*:
the code advances it after the read).

## Art of Fighting's build

Art of Fighting's M ROM (`/data/roms/aof.neo`, 64 KB mirrored to 128 KB; copy `/data/neogeo_dict/sound/aof/aof_m1.bin`,
disassembly `drv.asm` there) carries the same signature, `Ver 3.0 by MAKOTO.04/03/10 to SK`, with the interrupt vector
`JP $2041`. Method as for KOF95 (`/data/neogeo_dict/sound/kof95/scratch/codediff.py`, output in
`/data/neogeo_dict/sound/aof/scratch/k94_*`, `ff3_*`): 5613 instructions, 104 differing blocks against KOF94, 122
against FF3. **The music engine is KOF94's**: from the song start on, every routine matches KOF94's instruction for
instruction, shifted, with the same RAM layout and the same tables in the code area; the differences there are
equivalent rewrites (`INC A` / `LD A,$01` after `XOR A`, `RETI` / `RET`, a `BIT 0,A` / `JR NZ` to the next
instruction in the interrupt handler, the SSG sweep start storing 0 instead of A = 0). The 1992 game therefore runs
KOF94's (1994) music engine, and the differences are in the command path (*inferred*: the music engine was settled by
1992, the command path reworked by the time of FF3 and KOF94).

Address map (KOF94 → AOF): song start `$10AC` → `$1045`; interrupt handler `$2096` → `$2041`; music tick `$21AE` →
`$2159`; channel `$229F` → `$224A`; events `$2457` → `$23F9`; opcode table `$2565` → `$2507`; FM key `$1421` → `$13CA`;
music ADPCM-A note `$159B` → `$1546` (records through `$0395`, KOF94 `$0447`); patch load `$180F` → `$17BA`; ADPCM-B
records `$0913` → `$085D`; register writes `$2B18` → `$2ABD`.

Tables (KOF94 → AOF): command types `$6907` → `$565C`; song bank bytes `$2E00` → `$2C10`; FM patches `$2E40` → `$2C50`;
song headers `$3B40` → `$34A4`; SSG effect headers `$3BC0` → `$3524`; ADPCM-A effect records of slot 0 `$3E73` →
`$3CBF` (also the music's sample table, as KOF94); sequenced ADPCM-A effect headers `$5EC3` → `$4FDE`; ADPCM-B records
`$5F23` → `$5054` (KOF94's 26-byte layout); opcode `$46` tables `$6693` → `$53E8`, `$6757` → `$54AC`; delta-N `$66D3`
→ `$5428`, `$6807` → `$555C`; one-byte effect code tables `$6A07` → `$575C` (ADPCM-B), `$6A47` → `$579C` (ADPCM-A);
mute exemption `$6A87` → `$57DC`; F-numbers `$6A88` → `$57DD` (byte-identical, the sharp second scale included); pitch
`$207E` → `$2029`, gate `$2C0E` → `$2BB3` (byte-identical).

Functional differences, all read from the code:

| Area | KOF94 | Art of Fighting |
|---|---|---|
| Dispatch | `$01C1`: type byte, then a `DEC A` / `JP Z` chain | `$0185`: `LD HL,$565C`, then a `CP 1` ... `CP 5` chain (1 `$0BB7` system, 2 `$01B6` → `$1045` song, 3 `$01FC`, 4 `$0512`, 5 `$0926`); `game_of()` looks for the type table load from `$0180` on |
| Reply to the 68K | the command (+1 every 128th) or the check table `$2C54`[cmd], written by the main loop and by every interrupt | the NMI writes `$FEDD` OR `$80` to port `$0C` after storing a command (`$0091`); the main loop sets `$FEDD` = the refresh register R while `$FED9` is non-zero (`$015B`); no command echo, no write in the interrupt handler |
| Reset | bank self-test, ROM check in bank `$1E` | neither; `OUT ($C0),A` with A = 1 (`$0105`, purpose unknown) |
| Command map | music 28 | music `$20-$3C`, `$40-$47`, `$5F` (38), every song in bank map 0; SSG effect songs `$60-$62`, `$65`, `$68-$6A`, `$7F`; one-byte ADPCM-A effects `$C0-$CE`, `$D0-$E4`, `$E6-$EE` (type 3, `$01FC`: code = `$579C`[cmd - `$C0`], slot 0's records; a code ≥ `$E4` starts a sequenced effect, headers `$4FDE`, `$042A`) |

The model needed the table addresses only (`tools/makoto3/games.py`). Validation: **all 38 music commands, 10180 of
10180 interrupts with writes identical, 178911 captured writes, 0 differing**, including `$24`, which restarts itself
with opcode `$47`; per song in `aof_songs.md`.

### What the 68000 sends (Art of Fighting)

The sound routine `$44E6` (once per frame) takes the next byte of a queue at `$107000` (`a5` = `$108000`, write index
`$108104`, read index `$108105`), skips `$00`, drops `$01`, and writes it to `REG_SOUND` (`$4506`). Requests: `$4532`
(sound ID in `d0` = a byte offset into the word table `$4552`, queued as two bytes, so `$00xx` sends `xx` and `$1Axx`
an effect prefix and its code), `$450E` (only when the ID differs from the last one, `$10818A`), `$451E` (ID + 2 or + 4
by the object's distance across the screen). Measured in our emulator: `$03` at frame 368 and 838, `$02` at 377 (the
NEO-GEO logo jingle `$5F`), `$07` at 843, the opening `$29` at 1223. Stage themes and talk scenes come from 68K tables
by the stage counter `$108428` (`aof_songs.md`).

## Art of Fighting 2's build

Art of Fighting 2's M ROM (`/data/roms/aof2.neo`, 128 KB; copy `/data/neogeo_dict/sound/aof2/aof2_m1.bin`) carries the
same signature and KOF94's interrupt vector (`JP $2096`). Aligned with KOF94 and with Fatal Fury Special
(`/data/neogeo_dict/sound/aof2/scratch/k94_*`, `ffs_*`): 5580 instructions on all three sides, three differing
instructions against each, every matched code or RAM operand the same address. So it is **KOF94's driver code with
other tables**, as Fatal Fury Special:

| Address | KOF94 | Fatal Fury Special | Art of Fighting 2 |
|---|---|---|---|
| `$0014` | word `$59A7` | `$F907` | `$8F71` (the ROM sum of the `$10` self-test) |
| `$02B9` / `$04EE` | `CP $FF` / `SUB $FF` | `CP $F0` / `SUB $F0` | `CP $F0` / `SUB $F0`: ADPCM-A effect codes `$F0-$FF` are sequenced effects, as Fatal Fury Special |
| `$05E0` / `$094A` | `CP $F0` / `SUB $F0` | `CP $80` / `SUB $80` | `CP $F0` / `SUB $F0`: ADPCM-B effect codes `$F0-$FF` sequenced, as KOF94 |

Tables (KOF94 → AOF2): command types `$6907` → `$6993` (`game_of()` tells it from KOF94 by this table); song headers
`$3B40` → `$3B0C`; SSG effect headers `$3BC0` → `$3B8C`; song bank bytes `$2E00` and FM patches `$2E40` (same); ADPCM-A
effect bitmaps `$3E13`/`$3E33`/`$3E53` → `$4130`/`$4150`/`$4170`, records `$3E73`/`$4973`/`$5473` → `$4190`/`$4C90`/
`$5790` (`$4190`, slot 0's, is the music's sample table); sequenced ADPCM-A effect headers `$5EC3` → `$608B`; ADPCM-B
effect bitmaps `$5EE3`/`$5F03` → `$60AB`/`$60CB`; ADPCM-B records `$5F23` → `$60EB` (26 bytes); sequenced ADPCM-B
headers `$6673` → `$6703`; opcode `$46` tables `$6693` → `$6723`, `$6757` → `$67E3`; delta-N `$66D3` → `$6763`, `$6807`
→ `$6893`; one-byte effect code tables `$6A07` → `$6A93`, `$6A47` → `$6AD3`; mute exemption `$6A87` → `$6B13`;
F-numbers `$6A88` → `$6B14`; SSG periods `$6AC8` → `$6B54`.

Command map (`$6993`): system `$00-$1E` except `$1B`; music `$20-$36`, `$40-$4E`, `$50-$52`, `$5F` (42); SSG effect
songs `$60-$62`, `$65`, `$68-$6A`, `$7F`; one-byte ADPCM-A effects (type 3) `$C0-$DC`, `$F0-$F9`; one-byte ADPCM-B
effects (type 4) `$99-$A6`.

The M ROM's last 35438 bytes (`$17592-$1FFFF`) are byte-identical with KOF94's at the same offsets, the block the
KOF95 section calls "KOF94's song data left in place"; Art of Fighting 2 came out before KOF94 (both 1994),
and no song of either game reads the block (model runs of every song) (*inferred*: it comes from an earlier game or
work in progress, carried from ROM image to ROM image).

The model needed the table addresses only. Validation: **all 42 music commands, 18265 of 18265 interrupts with writes
identical, 347698 captured writes, 0 differing**; per song in `aof2_songs.md`.

### What the 68000 sends (Art of Fighting 2)

The sound routine `$0962` takes the next byte of a queue at `$106B00` (write index `$108284`, read index `$108285`),
skips `$00`, drops `$01`, and writes it to `REG_SOUND` (`$0982`). Requests: `$09BA` (sound ID = a byte offset into the
word table `$09DA`, two bytes queued), `$098A` (only when the ID differs from the last one, `$10830A`). Measured: `$03`
at 368, `$02` at 377 (the logo jingle `$5F`), `$07` at 843, the opening `$29` at 1365. Stage themes from the table
`$9F1A` by the opponent, endings from `$11092` by the player's character (`aof2_songs.md`).

## Art of Fighting 3's build

Art of Fighting 3's M ROM (`/data/roms/aof3.neo`, 128 KB; copy `/data/neogeo_dict/sound/aof3/aof3_m1.bin`, disassembly
`drv.asm` there) carries the same signature, with the interrupt vector `JP $1C9C`. Aligned with KOF95
(`/data/neogeo_dict/sound/aof3/scratch/k95_*`): 5284 instructions against KOF95's 5004, 71 differing blocks (446
against KOF94). It is **KOF95's reworked build** (word jump tables, KOF95's RAM layout, the depth-4 stack guard) with three changes
to the music engine; the differences in the effect and system-command paths (`$02AF-$0475`, `$0A11-$0BEE` in KOF95's
numbering) were not read one by one.

Address map (KOF95 → AOF3): interrupt handler `$1BCA` → `$1C9C`; music tick `$1CA8` → `$1D7A`; song start `$0DA1` →
`$0E7D`; channel `$1D72` → `$1E44`, output `$1DA6` → `$1E78`; events `$1F22` → `$1FF4`; opcode table `$2014` → `$20E6`;
music ADPCM-A note `$125A` → `$133F`; ADPCM-B note `$12C2` → `$1393`; patch load `$1440` → `$1512`; register output
`$1615` → `$16E7`; fade step `$167B` → `$174D`; pitch `$1B74` → `$1C46` (table `$1BB2` → `$1C84`); end of song `$235B` →
`$2425`; gate `$24A9` → `$25C9` (table `$2625` → `$2745`); register writes `$252D` → `$264D`.

Tables (KOF95 → AOF3): command types `$72B4` → `$5F5E` (loaded at `$01F7`); song bank bytes `$2E00` → `$2891`; FM
patches `$2E40` → `$28D1`; song headers `$3B40` → `$3841`; SSG effect headers `$3BC0` → `$38C1`; sequenced ADPCM-A
effect headers `$6B9B` → `$501B`; ADPCM-B records `$6BFB` → `$51E6` (16 bytes); opcode `$46` tables `$702B` → `$5CE6`,
`$70F3` → `$5DAE`; delta-N `$706B` → `$5D26`, `$71A3` → `$5E5E`; F-numbers `$7435` → `$60DF` (byte-identical).

Functional differences in the music engine, all read from the code:

| Area | KOF95 | Art of Fighting 3 |
|---|---|---|
| Music ADPCM-A samples | per song: `$0DF4` stores `$3C00`[song] in `$FEDB`, the note copies it to `$FEE2` | **per channel**: a table pointer `$FEDF` + 2c and a flag byte `$FEEB` + c for ADPCM-A channel c, set at reset to `$3E0F` and 0 (`$00E6`) and changed only by opcode `$3C`: **kept across songs**. The note (`$046D`): flag bit 0 set → 11-byte records `$FEDF`[c] + 11 × sample (KOF95's key-on, `$03A8`), else 6-byte records `$FEDF`[c] + 6 × sample, keyed by `$0311` with the loop count forced to 0: `[?][start16][end16][?]`, played once |
| Opcode `$3C` | no-op | **sample table** p (`$2532`): i = p - `$18`, 0-7 (else nothing, the byte consumed); word `$2570`[i] and byte `$2580`[i] (`$3E0F` 0, `$0000`, `$440F` 0, `$5015` 0, `$4A0F` 0, `$505B` 1, `$500F` 0, `$0000`); a zero word changes nothing; for a channel id ≥ 8 (c = id - 8) the word goes to `$FEDF` + 2c, the byte to `$FEEB` + c (on ADPCM-B, c = 6, that is `$FEEB`/`$FEEC` and `$FEF1`: ADPCM-A 1's and 2's flags; no song does it). Every song with ADPCM-A notes sets `$1A` (`$440F`, 6-byte records) on its ADPCM-A channels |
| Opcode `$46` | p < `$40` kit, `$40-$7F` one pitched sample, `$80-$BF` one sample per octave, ≥ `$C0` nothing | p < `$40` kit; **every p ≥ `$40`** one pitched sample `$5CE6`[p - `$40`] (`$233F`: the per-octave mode and the "nothing" case are gone; no song uses p ≥ `$80`) |
| Bank maps | two | three, as FF3 (`$0EB3`: 0 identity, 2 → `$18000-$1FFFF`, any other → `$10000-$17FFF`); the songs use 0 and 1 |

Command map (`$5F5E`): system `$01-$14`, `$17-$1E`; music `$20-$28`, `$2A-$3D`, `$5F` (30); SSG effect songs `$60-$63`,
`$66`, `$7F`; one-byte ADPCM-A effects `$C0-$FF` (type 3); no type 4.

The model gained these three switches (`games.py`: `a_chan`, `b_octave`; the bank map), read from the code and
exercised by the songs except the 11-byte records and `$46` p ≥ `$80`. Validation: **all 30 music commands, 16934 of
16934 interrupts with writes identical, 249527 captured writes, 0 differing**; per song in `aof3_songs.md`. FF3
(32417 / 32417), KOF94 (15571 / 15571), KOF95 (17683 / 17683) and Fatal Fury Special (29536 / 29536) re-compared with
the extended tools: identical.

### What the 68000 sends (Art of Fighting 3)

The sound routine `$303B8` takes the next byte of a queue at `$10E12E` (write index `$10E124`, read index `$10E125`),
skips `$00`, drops `$01`, and writes it to `REG_SOUND` (`$303D8`). Requests: `$30404` (sound ID in `d0`, a long from the
table `$3051C` holding up to four command bytes, zero bytes skipped; negative IDs go through a per-character table
`$3113C`), `$303E2` (only when the ID differs from the last one), `$303F4` (registers saved). Measured: `$03 $03 $07`
twice (frames 864-874), `$02` at 404 (the logo jingle `$5F`), the opening `$21` at 1116. Stage themes from the table
`$CE50` by the player's character and the stage number (`aof3_songs.md`).

## Samurai Shodown's build

Samurai Shodown's M ROM (`/data/roms/samsho.neo`, 128 KB; copy `/data/neogeo_dict/sound/samsho/samsho_m1.bin`) carries
the signature `Ver 3.0 by MAKOTO.04/03/10 to SK` and KOF94's interrupt vector (`JP $2096`). Byte-aligned with KOF94
over `$0000-$2DFF`, the two differ only in 37 two-byte operands: **KOF94's driver code with other tables**, as Fatal
Fury Special and Art of Fighting 2. The game's tables (`games.py` `samsho`; each found at the operand KOF94 uses):
type table `$59C2` (`$01C6`), song headers `$362C` (`$1109`), ADPCM-A records `$3D1F` (`$0453`, effect slot 0's, as
KOF94), F-numbers `$5B43`, ADPCM-B records `$556C` (26 bytes), `$5752` / `$5812` / `$5792` / `$58C2` (opcode `$46`
tables); bank bytes `$2E00` (maps 0 and 1), patches `$2E40`, pitch `$207E` and gate `$2C0E` as KOF94. Music: `$20-$2A`,
`$2C`, `$2D`, `$2F`, `$31`, `$35`, `$40-$46`, `$50-$58`, `$5F` (33). Songs: `samsho_songs.md`.

## Samurai Shodown II's build

Samurai Shodown II's M ROM (`/data/roms/samsho2.neo`, copy `/data/neogeo_dict/sound/samsho2/samsho2_m1.bin`): the same
signature, interrupt vector `JP $20EF`. Aligned with KOF94 instruction by instruction
(`/data/neogeo_dict/sound/samsho4/scratch/insdiff.py`, `z80disasm.py` listings in `/data/neogeo_dict/sound/samsho2/drv.asm`),
the music engine (song start to output stage, `$10AC-$2DAF` in KOF94) is KOF94's code moved by `+$59` with every operand
moved alike (the opcode jump table `$25BE` = KOF94's `$2565` + `$59`). What was added is effect code before it:
- a third ADPCM-A effect sample table: routines `$0466` / `$047A` / `$048E` / `$04A2` (tables `$3EED`, `$49ED`, `$54ED`,
  `$5FE2`) where KOF94 has three, and the effect start `$030A` that uses the new one;
- system commands `$1D` and `$1E` (the type-1 jump table `$0CAD` has 34 entries, KOF94's 31), both with a parameter
  byte (like `$18-$1C`); handlers `$0E02`, `$0E22` set `$FEB2` = 2 / 3 (the effect slot).
Music ADPCM-A samples are still effect slot 0's table (`$3EED`, via `$0466`). Tables (`games.py` `samsho2`): types
`$6C4A`, headers `$3800`, F-numbers `$6DCB`, ADPCM-B records `$656A` (26 bytes), `$69DA` / `$6A9A` / `$6A1A` / `$6B4A`,
pitch `$20D7`, gate `$2C67`; bank bytes `$2E00`, patches `$2E40`. Music: `$20-$3D`, `$40-$47`, `$5F` (39). Songs:
`samsho2_songs.md`. Opcodes `$4C` and `$5B` (ADPCM-B effect switches) appear in 68 places of its songs; the model lists
them without running them, and every interrupt still matches.

## Samurai Shodown III's build

Samurai Shodown III's M ROM (`/data/roms/samsho3.neo`, copy `/data/neogeo_dict/sound/samsho3/samsho3_m1.bin`): the same
signature and Art of Fighting 3's interrupt vector (`JP $1C9C`); aligned with Art of Fighting 3 it is that build
(KOF95's reworked code, per-channel ADPCM-A tables set by opcode `$3C`, 6- or 11-byte records, three bank maps) with
three changes:
- **opcode `$46` has the per-octave ADPCM-B mode again** (`$233F`: `p < $40` kit, `< $80` one pitched sample
  (`$1494`), `< $C0` per-octave sample tables (`$1487`, 8 bytes per entry), else nothing), as KOF95. `games.py` leaves
  `b_octave` at its default. No SS3 song uses `$80-$BF` (all 721 `$46` events are `$40-$7F`): read from the code, not
  measured;
- `$0C6C`: an ADPCM-A effect started on channel `$0C` now clears the music block of `$FDE1` (A4) instead of `$FDF1`
  (effects only);
- the tables moved back to KOF95's places: bank bytes `$2E00`, patches `$2E40`.
Tables (`games.py` `samsho3`): types `$60F7`, headers `$36C8`, per-channel ADPCM-A default `$3D03` (`$00E6`), opcode
`$3C` words `$2578` / flags `$2588` (`$2542`), pitch `$1C84`, gate `$274D`, F-numbers `$6278`, ADPCM-B records `$5CFF`
(16 bytes), `$5E7F` / `$5EBF` / `$5F6F` / `$5FF7`. Music: `$20-$40`, `$5F` (34). Its system commands with a
parameter byte (`$0A70` jump table; handlers that call `$0232` or `$0BD0`): `$0A`, `$0E`, `$14`, `$15`, `$16`,
`$18-$1E`. Songs: `samsho3_songs.md`.

## Compared with KOF98

Same ideas:
- the command path: NMI ring of 64, echo on port `$0C`, the work in the main loop, a type byte per command; system
  commands below `$20` with the same core numbers (`$07` unlock after a mute-at-reset, `$0A` + byte fade, `$0E` + byte
  tempo, `$01` / `$03` resets);
- effects choose a sample table by prefix (`$18 $1A $1C $1E $1B`, the same prefix bytes), records with a priority, and
  fight for ADPCM-A 4-6, which the music also uses (KOF98's music defends them with its own priority; FF3's always
  yields, and a lower value is the stronger sound);
- 11 music channels in the same order (FM 1-4, ADPCM-A 1-6, ADPCM-B), no SSG in music; SSG for generated cues;
- streams with loops, calls, gotos; TL to the carriers only with the same carrier sets; patches through a register
  shadow; the same F-number scale (C = 618); 256-byte-unit sample records with loop regions replayed by the
  end-of-sample poll.

What differs:
- **Clock**: KOF98 runs everything on timer A (166.83 Hz) with a fractional tempo accumulator per group; FF3 gives the
  music its own timer: **timer B = the tempo, one tick per interrupt**, timer A (54.3 Hz) for vibrato and effects. No
  accumulator, and no lost interrupts (KOF98 drops nested ones).
- **Events**: KOF98 = varlen length + running-status opcodes `$C0+` + MIDI-like note and velocity; FF3 = fixed
  3-byte notes `[length][tie/rest/attenuation][octave|code]` with **hex-letter note codes** (A-F = A-F, G = 0, sharps
  1 2 4 5 6), a per-channel **gate mode** instead of a per-note gate, and patch changes that carry volume / octave /
  detune bytes.
- **Levels**: KOF98 maps velocity × volume through a table per chip; FF3 adds attenuations (TL = song + volume + note),
  ADPCM-A level = volume - attenuation, ADPCM-B = base + volume - 3 × attenuation.
- **Patches**: KOF98 41 bytes in register order; FF3 52 bytes, one byte per operator parameter, unpacked by the driver.
- **Song control**: FF3 songs chain (`$47`), fade themselves (`$3F`), change tempo mid-song (`$33`), and a song start
  keeps the channels' settings; KOF98 resets them.
- **Write order**: KOF98 writes the F-number then the key-on; FF3 the key-on then the F-number.
- **Banking**: three fixed 32 KB maps chosen per song (KOF98: 4-byte bank sets).
