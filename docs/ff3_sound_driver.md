# Fatal Fury 3 sound driver ("Ver 3.0 by MAKOTO.04/03/10 to SK")

Second deep dive into a classic SNK driver, after KOF98 (`kof98_sound_driver.md`). Source: Fatal Fury 3's M ROM
(`/data/roms/fatfury3.neo`, M region, 128 KB; copy `/data/tmp/snd98/ff3/ff3_m1.bin`, disassembly `drv.asm` there, by
`tools/z80disasm.py`), checked against captures of the real driver in our emulator, interrupt by interrupt
(tools/ff3snd, see Validation). The signature at `$003E` reads `Ver 3.0 by MAKOTO.04/03/10 to SK`: a different
driver line from KOF98's SNK v1.7, and nothing of KOF98's layout carries over. This file is the driver: protocol,
dispatch, the two clocks, channel state machine, stream format and every opcode, output stage, effects. The songs
(catalogue, structure, per-song validation) are in `ff3_songs.md`. Everything below is read from the code (addresses
cited) or measured; *(inferred)* marks the rest.

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
validated captures. song_ff3.py models those and `$37`, `$3A`, `$41`, `$4F`, `$50`, `$55`, `$56`; the others it
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

## Validation (tools/ff3snd)

- `capture.py`: our emulator's core (Geolith) driven from Python with a Z80 port tap added to the core
  (`geo_z80.c`: `geo_z80_port_tap`; `libretro.c`: `retro_neoscan_z80_tap`, `retro_neoscan_z80_ram`,
  `retro_neoscan_sound_cmd`; built to `/data/tmp/snd98/ff3/geolith_tap.so`, not installed): every YM2610 write,
  every command the Z80 reads, an `i` line per interrupt (the handler's status read), the game's own commands blocked
  after its `$07`, a song sent at frame 900. `--songs` captures every music command to its loop point or end + 15 %.
- `song_ff3.py`: decoder + model (the code above), driven by the captured interrupt order (A / B); `regs_ff3.py`:
  the model's register writes and the comparison, interrupt by interrupt, same values, same order (left out on both
  sides: `$27` timer flags, `$1C` end-flag resets and ADPCM-B `$10` = 0, which the end-of-sample poll also writes).
- **All 40 music commands: every interrupt with writes identical (32417 of 32417), 0 differing**; song `$2A`'s 88
  ADPCM-A loop replays (written by the end-of-sample poll, timed by the sample length) are each the predicted loop
  region of the sample playing on that channel. Per song in `ff3_songs.md`.
- Not validated: the opcodes no song uses, the software vibrato, the ADPCM-B effects (no song runs them).

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
