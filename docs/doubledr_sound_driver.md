# Double Dragon sound driver ("SDC_NGSS", R. Ashworth), and Super Dodge Ball's build

Sixth Neo Geo driver decoded, after SNK's line (`kof98_sound_driver.md` ...), MAKOTO v3 (`ff3_sound_driver.md`) and
ADK's (`ninjamas_sound_driver.md`). Source: Double Dragon's M ROM (Technos 1995, `/data/roms/doubledr.neo`, M region
128 KB; copy `/data/neogeo_dict/sound/doubledr/doubledr_m1.bin`, disassembly `drv.asm` there, by `tools/z80disasm.py`),
checked against captures of the real driver in our emulator, main-loop pass by pass (tools/ngss, see Validation).
Nothing of SNK's, MAKOTO's or ADK's drivers carries over. The songs are in `doubledr_songs.md`. Everything below is read
from the code (addresses cited) or measured; *(inferred)* marks the rest.

Of our 144 ROMs only **Super Dodge Ball** (Technos 1996, `/data/roms/sdodgeb.neo`) runs the same driver, a later
build (section "Super Dodge Ball's build").

## Identity

`$003C`: `SDC_NGSS` + `01 00` (Super Dodge Ball: `01 01`, version 1.0 / 1.1 *(inferred from the bytes)*) + `RCA`;
`$1E12`: `PROGRAMMED BY R. ASHWORTH YOROSHIKU NE!!`. `tools/ngss/games_ngss.py` tells the build from the 10 bytes at
`$003C`.

## Z80 map and ports

| Range | What |
|---|---|
| `$0000-$1871` | code |
| `$1872-$1BED` | tables: FM F-numbers `$1872` (4 bytes per semitone), ADPCM-B delta-N `$18A2`, SSG periods `$19CE`, carrier masks `$1B4E`, volume → attenuation `$1B56` (128), bit masks `$1BD6`, volume table `$1BDE` (16) |
| `$1BEE-$1E11` | the "SNK logo" jingle's FM patches and its streams (`$1C22`) |
| `$2000-$2CFF` | FM patches, 26 bytes |
| `$2D00-$38FF` | 6 ADPCM-A sample tables of 128 × 4 bytes |
| `$3900-$3BFF` | ADPCM-B instruments, 6 bytes |
| `$3C00-$3ECF` | sound table, 3 bytes per command `$00-$EF` |
| `$8000-$BFFF` | sound data through the 16 KB window (port `$0B`), banks 2-7 = M ROM `$8000-$1FFFF` |
| `$F800-$FFFF` | RAM: 14 channel blocks of `$4E` bytes from `$F800`, globals `$FC44-$FCA5` (ring `$FC66`), stack top `$FFFC` |

Ports: `$00` read = command (NMI), write = acknowledge; `$0C` write = reply; `$04-$07` = YM2610 (A addr/data, B
addr/data; writes through `$185C` port A, `$1867` port B: D = register, E = value); `$08` / `$18` write = NMI enable /
disable; `IN A,($08-$0B)` = bank select. `$1736` sets the windows to the ROM as is (`$08`←`$1E`, `$09`←`$0E`,
`$0A`←`$06`, `$0B`←`$02`); only `$0B` ever changes: `$1747` selects bank A + 2 for the sound being read.

## Reset and boot

`$00C8`: SP `$FFFC`, NMI off, `IM 1`, RAM test `$0D82` (fill `$55` / `$AA`, then an address pattern; result bits in A':
1 = fill error, 2 = address error), the result on port `$0C`, a non-zero result hangs (`$00DA`). `$165B`: RAM cleared,
windows `$1736`, everything silenced (`$1698`, below), timers `$174C`: `$27` = `$30`, **timer B `$26` = `$EB`**, `$27`
= `$2A` (timer B loaded, enabled, flag reset; timer A never used), NMI on, `EI`, main loop `$00E0`.

## The clock: one pass per timer-B interrupt

The interrupt handler (`$0038` → `$0236`) writes `$27` = `$2A` (timer B flag reset + reload) and counts in `$FC44`.
Nothing else: it reads no status. **Timer B `$EB` = 336 samples of 18 µs: 165.3 Hz** (measured: 2.792 interrupts per
frame = 165.25 Hz).

The main loop (`$00E0`) waits for the count, clears it (`$00EA`; a count above 1 first runs the channel updates that
many extra times, `$0189`: never seen, the work runs with interrupts off and a held interrupt counts once), then with
interrupts off: **one command** from the ring (`$16D4`), the **14 channel updates** in the order ADPCM-A 1-6 (`$0557`),
FM 1-4 (`$02A9`), ADPCM-B (`$02D8`), SSG A-C (`$0307`), the **fade** (`$08F5`), `EI`, and the reply on port `$0C`
(`$FC61` | `$80` while any channel plays).

**Every channel has its own tempo accumulator**: IX+`$11` += IX+`$12` each pass, a tick on the carry; default tempo
`$49`, set by opcode `$E0`. Ticks/s = 165.3 × tempo / 256. A song sets the same tempo on all its channels (every Double
Dragon song), so its channels tick together; the first tick comes 4 passes after the command at the default tempo
(73 × 4 ≥ 256).

## Command path

**NMI (`$0066`)**: reads port `$00`; `$00` is dropped; `$01` → `$024C` (silence, then park the Z80 in a `JR $` loop
copied to RAM `$F800`: before the 68000 swaps the Z80 ROM *(inferred)*), `$02` → `$026C` ("SNK LOGO": reset the
driver's state and start the built-in jingle `$1C22` on FM 1-4 with the patches at `$1BEE`), `$03` → `$0CE2`
("RESET": `$165B`), `$FF` → `$0CF1` ("ROM CHECK": sum of the `$8000-$BFFF` window over banks 7 .. 0 compared with the
word at `$0014`; the result, 1 = good or 4 = bad, goes to port `$0C` and is beeped that many times on SSG A (`$0D06`),
then `$165B`). Anything else goes into the **64-byte ring `$FC66`** (write index
`$FC4F`) and port `$00` is acknowledged. **Consequence (measured): an argument byte `$01`, `$02`, `$03` or `$FF` never
reaches the ring**: `F6 01` sent in a capture parked the driver.

**Ring (`$16D4`, one byte per pass)**: a byte below `$F0` is a **sound**: `$FC4E` = it, `$14CF` starts it. `$F0-$FF`
take the next ring byte as their argument (`$FC53` holds the prefix until it arrives), jump table `$1705`. The game's
sound test ("SOUND CODE HELP", P ROM `$1AF30`) names them:

| Cmd | Handler | Effect |
|---|---|---|
| `$F0` x | `$110D` | **CODE KILL**: stop every channel playing sound x (`$0FAD`) |
| `$F1` x | `$11C7` | **PRIORITY KILL**: stop every active channel of priority x |
| `$F2` x | `$12D4` | **GROUP KILL**: stop every active channel of class x |
| `$F3` x | `$1680` | **ALL STOP**: silence (`$1698`), every block inactive |
| `$F4` x, `$F8` x | `$0C24` | **VOLUME** (`04-7F`): master attenuation `$FC65` = (not x) & `$7F`, every block's level rewritten |
| `$F5` x | `$0C39` | **FADE OUT** (`04-7F`): fade speed `$FC4B` = x |
| `$F6` x | `$0C41` | **FADE STOP**: attenuation and speed 0, levels rewritten |
| `$F7` x | `$0C4F` | **ADPCM TEST** (`80-84`): stop all, then every sample of ADPCM-A table x & `$7F` on ADPCM-A 1, one after the other (each waited for on the end flag, port `$06`) |
| `$F9-$FF` x | `$0210` | silence, wait 35 passes, beep 6 times on SSG A (`$0D06`), reset |

**Starting a sound (`$14CF`)**: the table entry `$3C00` + 3 × cmd: `[offset hi][offset lo][bank]` (offset ≥ `$8000`:
no sound). The data at `$8000` + offset in bank + 2 starts with a 6-byte header **`[kill lo][kill hi][class][priority]
[mask hi][mask lo]`** and one big-endian word per mask bit: the channel's stream, relative to the word's own address.

1. **Kill** (`$1567`): every active block whose class is in `[kill lo, kill hi]` stops (key-off with fast release,
   `$07A4`). Music: kill 0-0 (the previous song); hits (class 4): kill 3-4 (whooshes and hits); footsteps (class 7):
   kill 7-7; voices: kill `$FF`-`$FF` (nothing).
2. **Claim** (`$1517`): for each mask bit, LSB first = block 0 (FM1) ... 13 (SSG C), the block is taken unless it is
   active with a higher priority (**priority: a higher value wins, equal takes over**; the stream word is skipped).
   Mask `$0100` is special (`$159E`): **one of ADPCM-A 4-6** (`$15C8`): the first free one, else the one with the lowest
   priority (ties: the lower block), refused when its priority is higher.
3. The block is initialised (`$15F6`, below) with the sound id, priority, class and bank; **a sound of class 0 (music)
   also resets the fade** (`$1554` → `$0C41`).

**Music and effects share the 14 blocks.** There is no separate music layer: a voice that takes ADPCM-A 4 from a song
replaces the song's channel for good (the song's stream for that channel is lost). Double Dragon's songs use FM 1-4,
ADPCM-B, ADPCM-A 1-3 (mask `$00FF`), the voices and effects ADPCM-A 4-6, so they never meet; songs `$EB` / `$EC` also
take ADPCM-A 4-6 (with priority `$45`, which no voice beats), `$E2` SSG B-C.

## Channel block (78 bytes, IX)

| Offset | Content |
|---|---|
| `+00-03` | loop counter stack (opcodes `$ED` / `$EE` / `$EF`; `+48` = depth) |
| `+04` | channel code: `$11 $12 $15 $16` FM 1-4 (key-on code + `$10`), `$20` ADPCM-B, `$40-$45` ADPCM-A 1-6, `$80-$82` SSG A-C (written at each tick) |
| `+05` / `+06` / `+07` | sound id (0 = inactive) / priority / class |
| `+08` | flags: 0 note on, 1 vibrato on, 2 portamento, 3 pitch slide, 4 tie (no gate countdown), 5 pitch dirty, 6 patch dirty, 7 level dirty |
| `+0A/0B` | stream address |
| `+0D/0E` | volume 8.8 (`+0E` 0-`$7F`) |
| `+11` / `+12` | tempo accumulator / tempo |
| `+13` / `+14` | octave base (12 × octave, default `$30`) / transpose |
| `+15` / `+16` | pitch: fine / note (semitones) |
| `+17` / `+18` | detune: fine / semitones (FM, SSG, ADPCM-B) |
| `+1A` | gate in eighths (default 8) |
| `+1B` / `+1C` / `+1D` | gate countdown / length / length countdown |
| `+1E/1F/23` | pitch slide step (24 bits) or portamento target (`+1E` fine, `+1F` note) |
| `+20/21/22` | pitch slide accumulator (`+21/22` = fine, note) |
| `+24` | portamento speed |
| `+25` / `+26/27` / `+28` | volume slide: target / step 8.8 / steps left |
| `+29`-`+36` | vibrato: delay, speed, ramp count, waveform, offset `+2D/2E`, depth `+2F/30`, depth step `+31/32`, delay counter `+33`, ramp counter `+34`, phase `+35/36` |
| `+37/38` | the patch's TL bytes (FM) / the ADPCM-B instrument record |
| `+3A` | bank |
| `+41` | instrument (FM patch, ADPCM-A table, ADPCM-B instrument) |
| `+42` | pan (`$C0` both, `$80` left, `$40` right) |
| `+43` / `+44` | reply bit / reply pulse countdown |
| `+45` | bit 0 pan dirty, bit 7 under the master attenuation (fade, `$F4`) |
| `+46` / `+47` | FB/ALG / carrier mask (`$1B4E`[alg]: bit 0 = `$40` S1, 1 = `$44` S3, 2 = `$48` S2, 3 = `$4C` S4) |
| `+49/4A` | ADPCM-B pitch offset (instrument bytes 1, 0) |
| `+4B` | `$F3` repeat counter |

Initialisation (`$15F6`): volume `$7F`, gate 8, tempo `$49`, octave base `$30`, pan `$C0`, reply bit 8, flags `$80`
(level dirty), length and gate counters 1, transpose / detune / vibrato delay / slides 0. **Not reset: the instrument,
the vibrato settings, the pan dirty bit aside**: they carry over from the block's previous sound.

## One tick (`$0347` FM / ADPCM-B / SSG, `$056B` ADPCM-A)

1. Unless tied (flag 4), the gate counts down; at 0 the note is keyed off (`$0750`).
2. The length counts down; not yet 0: the note goes on (`$04AD`: volume slide, then the pitch slide or the
   portamento).
3. At 0, events are read until a note or a rest:
   - **note** `0nnnnnnn` (< `$80`): bits 3-0 = semitone above the octave base: note = bits 3-0 + `+13` + `+14`
     (+ `+18`, FM / ADPCM-B / SSG; ADPCM-A: the note is the sample number); fine = `+17`. Bit 5 clear: a length byte
     follows (length = byte + 1); set: the previous length. Bit 4: tie (no gate countdown, so no key-off: the next
     note is legato). Bit 6: reply pulse (`$FC61` |= the reply bit for 8 passes: the 68000 can sync to a note).
     Gate = (length × `+1A`) >> 3, low byte, at least 1.
   - **rest** `1nnnnnnn` (`$80-$DF`): length = (n & `$7F`) + 1 (the gate counter too).
   - **opcode** `$E0-$FF` (table `$0401`, below).
4. A new note: slide accumulators cleared; if the previous note is still on (a tie): no key-on, the pitch is
   rewritten (legato). Otherwise vibrato restarted (flag 1), the patch loaded if dirty, the pan written if dirty, key-on
   (`$063A`).
5. After the tick (FM / ADPCM-B / SSG, `$02C0`): vibrato step (flag 1), pitch write (flag 5), level write (flag 7).
   ADPCM-A: level write only (`$061E`).

### Opcodes (`$E0` + n, jump table `$0401`)

| Op | Bytes | Handler | Effect |
|---|---|---|---|
| `$E0` | t | `$0E05` | tempo `+12` = t |
| `$E1` | i | `$0E0C` | instrument `+41` = i (FM patch / ADPCM-B instrument loaded at the next key-on; ADPCM-A sample table) |
| `$E2` | p | `$0E17` | pan from p >> 5 (signed): `$0E34` = `$80 $C0 $C0 $40` (0-31 left, 32-95 centre, 96-127 right) |
| `$E3` | a b | `$0E38` | nothing |
| `$E4` | v | `$0E3F` | volume `+0E` = v, slide off |
| `$E5` | n v | `$0E4E` | volume slide to v in n ticks (step = (v - volume) × 256 / n, `$1821`) |
| `$E6` | v | `$0E8D` | volume from table `$1BDE`[v] (v < `$80`) or v & `$7F` |
| `$E7` / `$E8` | - | `$0EA5` / `$0EAD` | volume + 1 / - 1 |
| `$E9` | o | `$0EB5` | octave base = 12 × o |
| `$EA` / `$EB` | - | `$0EC1` / `$0ECE` | octave base + 12 (up to `$54`) / - 12 |
| `$EC` | g | `$0EDA` | gate `+1A` = g (eighths of the length) |
| `$ED` | n | `$0EE1` | loop start: push n on the block's counter stack |
| `$EE` | d16 | `$0EF2` | loop end: decrement the top counter; not 0: jump d (big-endian, relative to the next event); 0: pop |
| `$EF` | d16 | `$0F11` | loop break: on the last pass (counter 1): pop, jump d + 2 |
| `$F0` | s f | `$0F34` | detune: semitones `+18` = s, fine `+17` = f |
| `$F1` | t | `$0F41` | transpose `+14` = t |
| `$F2` | hi lo | `$0F48` | pitch slide: (hi:lo) × 4 (sign-extended to 24 bits) added each tick to the pitch (fine units) |
| `$F3` | n d16 | `$0F71` | jump d (relative); d = 0 ends the channel; n > 0: n plays, then the channel ends (`$4B`) |
| `$F4`, `$F6`, `$FA`, `$FB` | - | | nothing |
| `$F5` | w s c d | `$0FC3` | vibrato: waveform w, speed s, depth c reached in d ramp steps (`$31/32` = c × 256 / d) |
| `$F7` | n | `$0FF2` | vibrato delay (ticks) |
| `$F8` / `$F9` | - | `$0FF9` / `$1017` | vibrato on (restarted) / off (offset 0) |
| `$FC` | s | `$1025` | portamento speed |
| `$FD` | n | `$102C` | portamento to note n (+ transpose + detune) |
| `$FE` | b | `$1043` | reply bit = `$1BD6`[b] |
| `$FF` | x ... | `$1052` | system: 0 + byte: SSG noise period (written with a stale register value: never used); 1 / 2: SSG mixer noise / tone for this SSG channel; 3 + c: push `F0 c` (stop sound c); 4 + c: push sound c (unless it is this one); 5 + v: push `F5 v` (fade); B + g: push `F2 g`; **C / D: the block follows / ignores the master attenuation** (every song starts with `FF 0C`) |

Opcodes that push commands (`$FF` 3/4/5/B) write into the same ring as the NMI, so the command runs one pass or more
later.

## Output stage

All writes for a channel happen inside its tick, in this order: patch (if dirty), pan (if dirty), key-on, pitch,
then (after the tick) vibrato pitch, level.

**FM** (codes `$11 $12 $15 $16`: key-on codes 1, 2, 5, 6; channels 5 / 6 on port B with register offset 1 / 2):
- **patch** (`$0944`, 26 bytes at `$2000` + 26 i; `$1BEE` while the last sound started was `$FF`, the logo jingle):
  `[FB/ALG][-][DT/MUL ×4][TL ×4][KS/AR ×4][AM/DR ×4][SR ×4][SL/RR ×4]`, operators in register order (S1, S3, S2, S4).
  Writes `$30`-`$3C`, `$40`-`$4C` (**carriers written as `$7F`**), `$50`-`$8C` (16), `$B0` = FB/ALG. No `$90`
  (SSG-EG) and no `$B4` AMS/PMS: never written by the driver.
- **key-on** `$28` = code | `$F0`, then the F-number (`$0A2D`); key-off `$28` = code; the stop key-off (`$07A4`: end
  of stream, kill) also writes `$80`-`$8C` = `$FF` (fastest release).
- **pitch** (`$0A2D`): p = note.fine + vibrato + slide (16-bit, 1/256 semitone); block = note / 12, F-number =
  `$1872`[semitone] + slope × fine >> 8 (`[slope][-][F-number word]`, C = 618); an F-number ≥ `$4D3` wraps to the next
  block (- `$4D3`, block + 1). `$A4` then `$A0`.
- **level** (`$0B4C`): v = volume - master attenuation (if `+45` bit 7, floor 0); B = `$1B56`[v] (v 0 → 0, `$7F` →
  `$7F`); each carrier: TL = patch TL - B when the patch TL is below B (8 bits, the chip keeps 7), else `$7F`.
- **pan** `$B4` = pan (no AMS/PMS bits).

**ADPCM-A** (codes `$40-$45`): key-on (`$0677`): instrument = table 0-5 (≥ 6: no sound), sample record `$2D00` +
512 × table + 4 × (2 × note & `$FF`): `[start hi][start lo][end hi][end lo]` (256-byte units); `$1C` flag reset,
start / end registers, `b $00` = bit. Level `b $08+c` = (volume - attenuation) >> 2 | pan, written after the key-on.
Key-off: dump (`b $00` = `$80` | bit). No loops, no end-of-sample poll (the driver never reads the status): a sample
plays to its end or to the gate.

**ADPCM-B** (code `$20`): instrument (`$0926`, 6 bytes at `$3900` + 6 i): `[pitch hi][pitch lo][start hi][start lo]
[end hi][end lo]`. Key-on (`$06E3`): `$1B` 0, reset (`$10` 1, `$1C` `$80` / 0, `$10` 0), `$11` pan, start / end, delta-N,
volume `$1B` = 2 × (volume - attenuation), `$10` = `$80` (no loop). Delta-N (`$0AA2`): p = note.fine + vibrato +
slide + the instrument's pitch; `$18A2`[note] = `[a][b][base word]`: delta-N = base + (a × note >> 8) + b × fine (the
code multiplies the first slope by the note number, not the fine part: kept as is). Key-off: `$1B` 0 + reset.

**SSG** (codes `$80-$82`): key-on (`$0660`): level `$08+ch` = volume >> 3 (no attenuation), then the period
(`$0AF7`: `$19CE`[note] = `[a][b][base word]`, period = base - (a × fine >> 8) - b × note); level writes later only
while the note is on; key-off: level 0. Mixer only through `$FF 1` / `$FF 2` (reset value `$F8`: tones on).

### Effects

- **Volume slide** (`$E5`): 8.8 step each tick of the note (`$04C3`), the target set exactly on the last step.
- **Pitch slide** (`$F2`): 24-bit step added each tick of the note to `+20/21/22` (`$04E4`); cleared at each note.
- **Portamento** (`$FC`/`$FD`): each tick the pitch moves by (distance × speed) >> 8, at least one fine unit when the
  move is under a semitone (`$0504`): an exponential approach.
- **Vibrato** (`$F5`/`$F7`/`$F8`, `$081A`): after the delay, each tick phase += speed × 128; at each phase wrap the
  depth grows by c / d for d wraps; waveform 0 / 1 = triangle (the driver keeps the phase byte as the offset's low
  byte: a bug kept by the model), 2 = triangle, 3+ = square (depth × 8). The offset is in 1/256 semitone and goes
  through the F-number table each tick, so the vibrato is even in cents across the scale.
- **Fade** (`$F5` command or `$FF 5`): `$FC64` += speed every pass, the attenuation is its high byte, all levels
  rewritten each pass; past `$7FFF` the fade ends and stops every block under the attenuation (`$13E1`).
- **Reply pulses** (note bit 6, `$FE`): port `$0C` bits for the 68000, no sound.

## Silence (`$1698`)

`$28` key-off ×4, `$22` LFO 0, release `$FF` on all FM operators (`$81`-`$8E` both ports), ADPCM-A dump all + master
`$3F`, ADPCM-B reset, SSG levels 0, mixer `$F8`.

## Sound map (Double Dragon)

From the sound test (P ROM `$1AF30`): **voices `$04-$9F`** (Abobo `$04-$0F`, Amon `$10-$1B`, **Billy `$1C-$2C`**,
Burnov `$2D-$38`, Cheng-Fu `$39-$44`, Duke `$45-$4F`, Dulton `$50-$5C`, Eddie `$5D-$68`, Jimmy `$69-$79`, Marian
`$7A-$86`, Rebecca `$87-$92`, Shuko `$93-$9F`), **narrator `$A0-$B5`**, **effects `$B6-$DB`**, **music `$DC-$EF`**,
control `$F0-$F7`, `$02` SNK logo, `$03` reset, `$FF` ROM check. `$00-$03` and `$EE` / `$EF` point at the same song
data (bank 0 offset 0, Amon's stage). Every voice and effect: one ADPCM-A sample on one of ADPCM-A 4-6 (mask `$0100`),
except the SSG effects `$7F`, `$B6`, `$DA` and the two-sample narrator calls `$AD-$B0`, `$B4` (ADPCM-A 4 + 5).
Voices: class 5, kill nothing, priority 3-9 (shouts 3, pain 5, specials 7-9); narrator priority `$0A`; sample table 2
(voices), 4 (narrator), 5 (effects).

**Narrator name calls** (68000 table `$1064E` by character): Abobo `$A0`, Amon `$A1`, Billy `$A2`, Burnov `$A3`,
Cheng-Fu `$A4`, Dulton `$A5`, Duke `$A6`, Eddie `$A7`, Jimmy `$A8`, Marian `$A9`, Rebecca `$AA`, Shuko `$AB`, `$AC`
(index 14). `$AD` / `$AE` start rounds 1 / 2 and `$B1` follows `$AD` by 104 frames (a 2P fight, measured: "round"
and "fight" calls *(inferred)*).

**Effects** (class / priority: whooshes 3 / 2, hits 4 / 6 kill classes 3-4, steps 7 / 2 kill class 7, others 6 / 4):

| Cmd | What | Evidence |
|---|---|---|
| `$CE` | light whoosh (A / B swing) | measured: Billy's A and B whiffs |
| `$CB` | heavy whoosh (C / D swing) | measured: Billy's C and D whiffs; Billy's steps of anims 19-25, 29, 36-39, 95-98, 100, 125 |
| `$CC` | whoosh | Billy's anims 26, 30, 34, 110-112 |
| `$C4` | hit (C) | measured: Billy's C landing on Jimmy; reaction anims 55-61, 66 |
| `$C6` | hit, heavy (D) | measured: Billy's D landing; reaction anims 51-53, 63-65, 118 |
| `$C5`, `$C7`, `$C8` | hits / falls | reaction anims 44-49 (`$C5`), 67-70, 119-120 (`$C7`, with the fall voices), 54 / 58 (`$C8`) |
| `$C9` | step *(inferred)* | anims 5-10 (walks), 99, 125; class 7 (each cuts the previous) |
| `$B7` | landing *(inferred)* | anims 11, 12, 41-43, 75, 100 |
| `$C2`, `$C3`, `$D5` | special-move effects | Billy's super (anim 82), 236 (83-86), 623 (87-90) |
| `$7F` | coin (SSG A-C) | measured: 13 frames after a coin |
| `$DA` | select cursor (SSG A-B) | measured: every cursor move on the player select |
| `$B6` | select (SSG A-B) *(inferred)* | measured on the player select |

**Billy's voices** (his animation steps' sound bytes, `tools/doubledr` `dd.steps`; A4-A6 samples of table 2):
`$1C` / `$1D` pain (light / heavy reactions, anims 52-65, 121), `$1F` / `$20` / `$21` attack shouts (normals: anims
19, 22, 23, 27, 31, 33, 42; `$21` measured with his C), `$1E` (anim 100), `$22` super (anim 82), `$23` / `$2C` falls
(anims 67-70, 119-120), `$24` 214 / jump 214 (anims 91-98), `$26` 236 (83-86), `$28` 623 (87-90), `$2B` (anim 81,
which also plays `$ED`); `$25`, `$27`, `$29`, `$2A` are not in his animations (played by the 68000's code
*(inferred)*). Jimmy's pain voices `$69` / `$6A` (measured on Billy's hits). WAVs as the real driver plays them (our
emulator, 3.4 s each): `/data/neogeo_dict/sound/doubledr/wav/XX.wav` for Billy's `$1C-$2C`, the hits / whooshes `$C2-$CE`,
`$D5`, `$B7`, his name call `$A2`, the coin `$7F` and the cursor `$DA`.

## Validation (tools/ngss)

`capture_ngss.py` drives the Geolith core with the Z80 port tap (makoto3's capture core): power-on, the game's own
commands blocked from frame 845 (its reset `$03` at 838, its first sound at 1173), the song at frame 900. Since the
driver reads no status, the interrupt marker is its handler's write `$27` = `$2A`; `regs_ngss.py` cuts the capture into
passes there and compares the model's writes pass by pass (same values, same order).

- **All 20 music commands `$DC-$EF` register-identical on every pass with writes** (each to its loop point + 15 %:
  `$DC` 3417 / 3417, `$E2` 8059 / 8059, `$EB` 4245 / 4245, ...; table in `doubledr_songs.md`).
- **All 216 voices and effects `$04-$DB`**, one every 150 frames: 562 / 562 passes.
- **Stress**: a song, then 478 commands 3-14 frames apart (voices and effects stealing ADPCM-A 4-6 by priority), volume
  `$F4`, group / code / priority kills, a fade then a new song, fade stop, the coin, all stop, another song:
  5967 / 5967 passes.
- **Super Dodge Ball**: all 15 songs, 69 000 passes each (several loops): every pass identical.

## Super Dodge Ball's build (version `01 01`)

The same engine, reworked in places (38 code differences, `tools/ngss` handles both: `games_ngss.py` `v11`):
- **blocks of `$4F` bytes**: `+4E` = the sound's **page**; sound ids are 16-bit: commands `$FA` x / `$FB` x start
  sound x of page 1 / 2 (table index page × 256 + x), `$F0` / `$FC` / `$FD` x stop sound x of page 0 / 1 / 2 (`$10AF`
  compares the page too); the globals moved (+`$0E`, +`$0F` from the ring index on).
- **volume**: 8.8 at `+0C/0D`; `$E4` with bit 7 set stores a **volume step** in `+0E` instead, and `$E7` / `$E8` add /
  subtract that step (clamped to `$7F` / 0) instead of 1.
- the **SSG key-on level** follows the master attenuation like the later level writes.
- no catch-up loop in the main loop; tables moved (+`$4E`: F-numbers `$18C0`, ..., patches of the logo `$1C3C`, pan
  table `$0DB8`).
- the songs are `$82-$90` (class 5, priority 4, mask `$38FF`: FM 1-4, ADPCM-B, ADPCM-A 1-3, SSG A-C), so a new song
  takes the channels by priority instead of killing the old one by class.

## Conversion to KOF98's driver (tools/port)

`tools/port/ngss_notes.py` turns a song into engine-neutral notes from the model's register writes (the path SNK-line
sources use: `snk_notes.from_writes`), the music tick = the channels' common tick; `port98.py` writes them in KOF98's
format, `compare_port.py` compares every key-on with its chip state, key-off and change of a sounding note.

What maps directly:
- **FM patches**: the 26-byte patch is 28 operator registers + `$B0` (SSG-EG never written: 0 on both sides) → KOF98's
  inline patch `$34`.
- **pitch**: every F-number word = a KOF98 note + detune `$2E` (exact). A tie into the same KOF98 note number writes
  nothing (`$2447`), so a slide step that lands on the previous note's number goes through the neighbouring note with
  the detune that gives the same F-number (`fm_note(avoid=)`, added for this source).
- **pitch slides and portamento** (`$F2`, `$FD`): every tick's F-number as a tied note: exact (`$E3`).
- **levels**: KOF98's direct mode takes the TL / ADPCM-A level / ADPCM-B volume the NGSS level stage computed.
- **ADPCM-A / ADPCM-B samples**: copied into the new V ROM, records relocated; ADPCM-B delta-Ns from KOF98's table or
  its kit records; ADPCM-B volume slides as slurs.
- **tempo**: NGSS 165.3 × T / 256 → KOF98 166.83 × T' / 208 / k (port98's pick, within 0.3 %).

What needs translation (measured on every song, each ported alone, `/data/neogeo_dict/sound/port/dd_all`):
- **unequal carrier TLs** (algorithms 4-7: the patch's TLs minus one attenuation) → KOF98 writes one velocity to every
  carrier: the other carriers' levels differ (`$DF`, `$E4`, `$E6`, `$EC`, `$ED`: 82-95 % of chip events identical).
- **FM volume slides inside a note** (`$E5`): no KOF98 event keeps the note: dropped, counted ('tl held').
- **vibrato** (`$F5`): exact only as one tied note per tick: `$E2` becomes 85 KB, `$EB` 40 KB, over the 30 KB bank
  window; the alternative is KOF98's type-2 pitch effect (F-number units, its own clock): approximate, not written.
- **SSG music** (`$E2`'s SSG B / C): no SSG music path in port98: left out.
- **F-numbers above KOF98's reach** (NGSS wraps at `$4D3`, so a block can hold `$4C0-$4D2`; `$DD`, `$E1`): same pitch as
  F / 2 in the next block, other register values: not written.
- **many ADPCM-B pitches** (`$DC`, `$EE`): out of KOF98 ADPCM-B records.
- **songs that end** (`$E5`, `$E7`): port98 loops every channel.

Proof (`/data/neogeo_dict/sound/port/dd_proof`, not in the brawler): **`$E3` Burnov's stage 6267 / 6267 and `$E9`
Jimmy's stage 6180 / 6180 chip events identical** (intro + 2 loops), and the real KOF98 driver in our emulator plays
both ports register-identical to song98.py's model on every interrupt (`capture_snd.py --check`, ROM
`dd_proof.neo`). `$DE` (Abobo), `$E8` (how to play) and `$EA` (Eddie) port identically too.
