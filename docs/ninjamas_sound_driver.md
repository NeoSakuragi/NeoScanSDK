# Ninja Master's sound driver (ADK, "Operation System Program for Music & Effective Sound Ver. 8.8.9")

Fourth Neo Geo driver decoded, after SNK's KOF98 line (`kof98_sound_driver.md`, `kizuna_sound_driver.md`) and
MAKOTO v3 (`ff3_sound_driver.md`). Source: Ninja Master's M ROM (`/data/roms/ninjamas.neo`, M region, 128 KB; copy
`/data/neogeo_dict/sound/ninjamas/ninjamas_m1.bin`, disassembly `drv.asm` there, by `tools/z80disasm.py`), checked
against captures of the real driver in our emulator, music tick by music tick (tools/adksnd, see Validation). Nothing
of SNK's drivers carries over: this is ADK's own driver, and **its songs are MML text that the driver reads while it
plays** (note letters, `O` / `<` / `>` octaves, `V` volume, binary length codes). The songs are in
`ninjamas_songs.md`. Everything below is read from the code (addresses cited) or measured; *(inferred)* marks the
rest.

## Identity

The ID string at `$0070-$00FB` reads ` CD-DA  & Operation System Program for Music & Effective Sound  Ver. 8.8.9
(c) Copyright ADK Corporation   December 4, 1995  by M.C  (^_^)`. "CD-DA" and the routines at `$2D53-$2DE6` that
read port `$0E` and write ports `$0C` / `$0D` / `$0F` suggest the same source also serves the Neo Geo CD's CD audio
*(inferred; on the MVS these ports do nothing the music needs)*. `tools/adksnd/gamesadk.py` tells the build from this
string (`Ver. 8.8.9`).

## Z80 map

| Range | What |
|---|---|
| `$0000-$2DE6` | code, with small tables inside (length codes `$11AB`, octave blocks `$1560`, FM note bases `$12FA`, F-numbers `$1FF9`, ADPCM-B notes `$1C49` / delta-N `$2141`, tempo `$2BD7`) |
| `$2E00-$2E1B` | word table of the data tables (below), read at run time |
| `$2E20-$32A7` | mode-0 song headers, 24 bytes each (11 stream pointers + 2 unused bytes) |
| `$32A8` ... `$DFFF` | streams, sample tables, command tables, FM patches (all reached through `$2E00`) |
| `$E000-$EFFF` | 4 KB window, port `$09` (default bank `$0E`: the ROM itself) |
| `$F000-$F7FF` | 2 KB window, port `$08` (default bank `$1E`: the ROM itself) |
| `$F800-$FFFF` | RAM (stack top `$FFFD`) |

`$2E00` table: `$2E20` song headers, `$698D` FM effect streams, `$4A51` ADPCM-A effect samples, `$5DD1` ADPCM-B
samples, `$6536` SSG effect streams, `$7266` FM patches (40 bytes), `$6A66` command table 1, `$6401` sequenced
ADPCM-A effects, `$0000` ADPCM-A level envelopes (a null pointer, below), `$6E66` command table 2, `$5651` ADPCM-A
music samples, `$68DE` SSG envelopes, `$5051` ADPCM-A voice samples, `$5C4B` ADPCM-A music samples, second set.

Ports: `$00` read = command (NMI), write = acknowledge; `$0C` write = reply; `$04-$07` = YM2610; `$08` write = NMI
enable; `IN A,($08-$0B)` = bank select (bank in A).

## Clocks: everything runs in the main loop

The interrupt handler (`$0E1A`) only counts: timer A → `$F832` + 1, timer B → `$F81E` + 1 (and `$F811`), then the
flag reset (`$27` = `$F836` | `$1F` / `$2F`). The main loop (`$014D`) does the work:

    $036D command   $191E timer-B work   $036D command   $0E56 music   $036D command   $0868 $08D0 $092E effect ends

- **Music** (`$0E56`): when the timer-A count `$F832` is 2 or more it is cleared and one music tick runs: ADPCM-A 1-6
  (`$2472`), ADPCM-B (`$27F8`), FM 1-4 (`$0E76`, each followed by its pitch envelope `$1892`), fade (`$17A2`). So
  **one music tick per two timer-A interrupts**, and timer A is the tempo: command `T` n writes `$24` / `$25` from the
  word `$2BD7`[n - 50] (`$10E5`: n below 50 counts as 50; the table holds 50 ... 239, larger values read past it).
  The table is **n = beats per minute** with 48 ticks to a quarter note: ticks/s = 0.8 n (n 120: value `$2DF`,
  96.12 ticks/s). A tick that outlasts two interrupts leaves the count at 2 or more, so the next tick starts at once
  and the count's surplus is lost (measured: long ticks with several patch loads; regsadk.py models it).
  When no tick is due the pass runs `$1750` instead: the loop-exit scanner (below).
- **Timer B** (value `$C8`, 62.0 Hz, set at reset `$022F` and never changed): `$191E` runs the effect channels (ADPCM-A
  `$FE00-$FEC0`, SSG `$FF00-$FF80`, FM `$F880` / `$F8C0`) and the CD-DA polling.

## Command path

**NMI** (`$0D70`): reads port `$00`; `$01` → park the Z80 in a `JP $FFFD` loop written into RAM (silence first: what
the 68000 sends before swapping the Z80 ROM, *inferred*), `$03` → silence, then return into `JP $0100`, a warm
restart (RAM cleared, chip init, main loop at `$0142`). Anything else goes into a **4-entry ring** `$F804-$F807`
(write index `$F82F`), and the command is echoed on port `$0C`.

**Main loop** (`$036D`, three times a pass): the next ring byte. Below 4: `$01` park, `$02` → the table entry 2,
`$03` → bank reset and full stop (`$0CA8`). `$F0-$FF` → system commands (jump table `$0ABC`):

| Cmd | Handler | Effect |
|---|---|---|
| `$F0` / `$F1` | `$0AE5` | fade the music out (`$F808` = cmd): attenuation `$F80A` + 1 every 4 music ticks / every tick up to `$40` (`$17CA`), then stop |
| `$F2` / `$F3` | `$0AEA` / `$0B05` | pause the music (blocks `$F900-$FBBF` saved to `$FBC0`, all silenced) / resume it (restored, patches and pans rewritten, tempo restored) |
| `$F4` `$F5` / `$F8` `$F9` `$FA` | `$0B21` ... `$0B4F` | attenuation `$F80A` up to `$0C` / `$10` (a step per `$1C` / `$18` ticks) / back down to 0 (a step per `$12` / 2 / `$10` ticks, `$FA` from `$1C`) (`$17FB-$1858`): ducking the music *(inferred)* |
| `$F6` / `$F7` | `$0B3F` / `$0B46` | the next four command bytes are data: a voice bank tag and its 16-bit sample offset into `$F860` / `$F866` (`$03DF`) |
| `$FB` | `$0B67` | the next byte is a pan for an ADPCM-A effect channel (`$03B8`) |
| `$FC` / `$FD` / `$FE` | `$0B6D` / `$0B73` / `$0B79` | **command table 2** for the next command only / until `$FE` / back to table 1 (`$F81F`, `$0475`) |
| `$FF` | `$0B7E` | stop everything, re-init |

Any other byte indexes a **4-byte entry** of command table 1 (`$6A66`) or 2 (`$6E66`): `[kind][flags][a][b]`:

- kind `$40`: **music**, song `a`, mode `b` (`$04A5`): mode 0 = header `$2E20` + 24a, windows at their defaults;
  mode 1 = the 2 KB window (port `$08`) on bank a (header at `$F000`, a ≥ `$20`); mode 2 = the 4 KB window (port
  `$09`) on bank a (header at `$E000`, a ≥ `$10`). In modes 1 and 2 every header pointer is folded into the window
  (`$055F`: high byte = window | (high & (size - 1) >> 8)). Smaller bank numbers are refused, after the reset.
- kind with bits 0-5: **ADPCM-A effect** on channels A1-A6 (bit n = A n+1, `$05D8`), sample a of the effect table
  (`$4A51`, or the voice table `$5051` when flags bit 7 is set), priority b (a running effect with a higher value is
  kept). **The effect takes the music's channel** (`$F824`+n set), and while it plays `$2472` skips that channel
  entirely: its music stream stops advancing and resumes late *(read from the code; captures here never mix effects
  and music)*.
- kind `$30` / `$0C`: sequenced ADPCM-A effects (`$0794` / `$07D8`), streams from `$6401`, on `$FE80`/`$FEC0` or
  `$FE00`/`$FE40` (the latter takes A3 / A4).
- kind with bit 7: **ADPCM-B effect** (`$090B`, record `$5DD1` + 8a, priority b); at its end flag (`$092E`) the music's
  sample and volume are restored.
- kind 0: flags low nibble 4 / 8 / `$C` = **FM effect** on the music's FM3 / FM4 / both (`$0957`: stream from `$698D`,
  played on blocks `$F880` / `$F8C0` by the music's own FM interpreter at timer B; the music channel is muted by its
  port byte `+$11` = 8 and restored at the stream's end, `$168B`); high nibble `$10-$70` = **SSG effect** on SSG A / B
  / C combinations (`$09EE`: streams `$6536`, blocks `$FF00-$FF80`, an MML interpreter of their own at `$1A03`).

The game sends `FC D0` for its title (measured): table 2 holds the music (`$02`, `$C0-$EE`), table 1 the effects.

## Music

Song start (`$04A5`): `$0C86` resets: `$10` = 1, `$1B` = 0 (port A); TL `$41-$4E` = `$7F` on both ports; `$10` = 1,
`$1C` = `$BF`, `$1C` = 0, `$1B` = 0; key-off `$28` = 1, 2, 5, 6; the 11 channel blocks cleared and their chip
registers set (`$0289`, `$02B2`, `$030C`); then the header's 11 stream pointers into the blocks (`$057E`: start =
restart point, counters 0, channel on), and `b $01` = `$3F` (ADPCM-A master volume). Header order **FM1-4, ADPCM-A
1-6, ADPCM-B**; the FM parts play on the chip's channels with key-on codes 5, 6, 1, 2 (port B channels 1-2, then
port A channels 1-2, `$0346`). No SSG in the music.

### Channel block (64 bytes: FM `$F900` + 64n, ADPCM-A `$FA00` + 64n, ADPCM-B `$FB80`)

| Offset | Meaning |
|---|---|
| `+$00` / `+$02` | stream pointer / start (for `/`) |
| `+$04` | `$` mark; `+$06-$08` `*` loop; `+$09-$0B` `\|` loop; `+$0D-$0F` `[` loop; `+$15-$17` `{` loop; `+$18` `(` mark |
| `+$10` `+$11` `+$12` | FM register offset, port (4 = A, 6 = B; 8 = taken by an effect), key-on code |
| `+$1A-$1F` | FM: `e` target / counter, `a` byte, algorithm, `$B4` shadow, patch. ADPCM-A: the channel's start / end / level registers and key bit. ADPCM-B: `+$1F` sample |
| `+$20` | channel on |
| `+$22` / `+$28` | length counter / default length (ticks, 16-bit) |
| `+$24` `+$25` | last note letter (or sample) / accidental (ADPCM-A: second sample table) |
| `+$26` `+$27` | F-number high / low (ADPCM-B: delta-N low / high) |
| `+$2B` / `+$2C` | `Q` / gate countdown (16-bit) |
| `+$2E` `+$2F` | octave; FM: block << 3, ADPCM-B: note offset |
| `+$30-$37` | FM: carriers' TL relative to the last operator, the four SL/RR bytes (patch) |
| `+$38` | volume (ADPCM-A: pan in bits 7-6) |
| `+$39` | FM / ADPCM-B: detune (`g`) / pan + repeat flag; ADPCM-A: the sounding level |
| `+$3A-$3F` | patch pointer; pitch envelope (FM) / level envelope (ADPCM-A) / B volume shadow |

### The tick (`$0E9F` FM, `$24A4` ADPCM-A, `$280E` ADPCM-B)

Channel off: nothing. Length counter 0: **read events** until a note or rest (below), then count 1 off. Else count
down, then (FM) the `e` envelope step, then the gate: at 0 the note ends:

- FM: key-off (`$28` = code).
- ADPCM-A: dump (`b $00` = `$80` | bit) **only when the gate and the length end on the same tick** (Q 0); otherwise
  the level falls by 3 a tick from then on (`$253C`, written to `$08+ch`): a soft release.
- ADPCM-B: the volume steps down by 8 to 0 (`$2A95`: `$1B` = v, v - 8, ... then 0).

A note's length is the default (`+$28`) unless length codes come before it; it plays `length` ticks, the next event
being read on the tick its counter reaches 0. The gate (`$13DA`) from `Q`: 0 = length - 1, 1 = 7/8, 2 = 6/8, 3 = 5/8,
4 = 4/8, 5 = 3/8, 6 = 2/8, other = 4/8 (sums of length >> 1, >> 2, >> 3, rounded down each).

### The text (`$0F26` FM, `$2560` ADPCM-A, `$285C` ADPCM-B)

Lengths (`$1146`, every channel): **binary length codes** `$01` whole note (192 ticks), `$02` 96, `$04` 48, `$08` 24,
`$10` 12, `$20` 6, `$40` 3, triplets `$03` 64, `$06` 32, `$0C` 16, `$18` 8, `$30` 4, `$60` 2, `$C0` 1 (`$11AB`); each
following `.` adds half of the last value (then a quarter ...); `_` ties the next code; a lone `.` = the default x 1.5.
A length sets both the counter and the default. Shared commands: `[` n ... `]` repeat n times; `{` n ... `}` the
same with its own counter; `|` n ... `:` and `*` n ... `&`: loops whose n-th pass jumps past the matching `:` / `&`
(the exit is found by the main loop between ticks, `$1785`, CPIR 64 bytes a pass; modelled as found at once); `$` /
`%` mark / go to mark; `(` / `)` mark / go back to it, loop state cleared (FM: key-off first); `/` back to the channel's
start; `Q` n gate; `$FF` end (FM: key-off; ADPCM-A: dump; ADPCM-B: volume to 0). **An unknown byte ends the reading
without storing the pointer**: the counter wraps to 65535 ticks (the channel goes silent for ~11 minutes at 120).

FM:

| Text | Handler | What |
|---|---|---|
| `A`-`G` [`#` / `b`] [`o` `q` `t` `u` `+` `-`] [`p` n] | `$1216` | note: F-number word `$1FF9` + byte offset `$12FA`[letter] (C `$20`, D `$30`, E `$40`, F `$48`, G `$58`, A `$68`, B `$78`) ± 8 (`#` / `b`) ± 2 / 6 / 4 (fine steps: **4 table entries per semitone**) + detune `g`; block = octave `O` << 3. Writes: `$A4` (block, high), `$A0`, key-off, key-on, then the carriers' TL. `p` n: pitch envelope n (`$21D1`[n], a byte per tick: 1 hold, 2 up, `$FE` down by (4 x `$22B1`[letter] + carry) / 10, `$1892`) |
| `R` | `$1510` | rest: carriers' TL `$7F`, key-off |
| `d` hi lo | `$13AD` | note with a direct F-number (key-on without key-off) |
| `?` p | `$1131` | patch p (40 bytes `$7266` + 40p, `$22BD`): per operator in patch order (slots +0 +8 +4 +C) `$50` KS/AR, `$60` AM/DR (AM on every operator when `a` was set), `$70` SR, `$80` SL/RR, `$40` TL, `$30` DT/MUL, then `$B0` FB/ALG, `$B4` = patch byte 38; carriers muted (TL `$7F`) until the next note |
| `V` v | `$148D` | volume: carriers' TL = (127 - v) + (operator TL - last operator TL) (+ fade), capped at `$7F` (`$14B0`; carriers by algorithm `$14F0`: 1 1 1 1 2 3 3 4) |
| `O` n / `<` / `>` | `$1526` / `$152D` / `$1534` | octave 0-8 / up / down (`<` is up) |
| `l` `s` `r` | `$10A8` | pan left / both / right: `$B4` = (shadow & `$3C`) \| pan (this mask also clears the PMS low bits) |
| `T` n | `$10D6` | tempo, n BPM (timer A) |
| `f` n, `v` n, `a` n | `$100B`, `$1024`, `$1045` | LFO (`$22` = n & 7 \| 8, or 0), PMS, AMS + the AM bit of each operator's DR (n bits 0-3) |
| `e` r v | `$14F9` | crescendo: every r ticks (a length code) volume + 2 while below v |
| `g` d | `$13D1` | detune, signed, added to the F-number |
| `Z` n | `$1430` | carriers' release rate = n (0: the patch's) |
| `W` n | `$11EF` | FM3 special / CSM mode via `$27` (`$4F` / `$0F`); notes then set four operator frequencies (`$1278`). Not modelled (no song uses it) |
| `=` n, `$FE` | `$1701`, `$1712` | a global byte `$F801`; skip ahead to the next note with the last letter at the octave given (`O` / `<` / `>`) |

ADPCM-A: `?` n sample n (`?` `?` n: second table `$5C4B`), `X` play (start / end from the 6-byte record `$5651` +
6n, level, key-on `b $00` = bit; no dump before), `R` rest (dump, level 0), `V` v level (bits 0-4), `l` `s` `r` pan
(written at once), `U` v ADPCM-A master volume (`b $01`), `e` s n level envelope n at speed s (its pointer table is
`$2E10`'s value, **0**: the pointers come from the code at `$0000`; no song uses it), `Q`, lengths, loops.

ADPCM-B: `?` n sample n (8-byte record `$5DD1` + 8n: start, end, delta-N, volume, pan; a note uses start and end), `A`-`G` [`#` / `b`] note:
`$10` = 1, 0, `$1C` = `$80`, 0, `$10` = 0, start / end `$12-$15`, delta-N `$19` / `$1A` from `$2141` + 2 per semitone
(`$1C49`: C 0, D 4, E 8, F `$0A`, G `$0E`, A `$12`, B `$16`; octave `O` adds `$2962`[octave]: 0, 0, 24, 48 ...), volume `$1B` = v
(- 3.5 x fade), `$10` = `$80` \| repeat; `X` replay the loaded sample at its pitch; `R` volume to 0; `V` v volume;
`O` / `<` / `>` octave 0-7; `l` `s` `r` pan (`$11`, and it clears the repeat flag); `K` n repeat flag (`$10` bit 4);
`e` crescendo (+4 per step); `Q`, lengths, loops.

## Driver quirks

- The FM pan commands keep `$B4` bits 2-5 only: a song that sets PMS with `v` and then pans loses PMS bits 0-1.
- `?` on an FM channel silences its carriers until the next note's TL write; `a` sets the AM bit on all four
  operators at the next patch load (`$2381`), on the operators selected by its bits at once (`$1061`).
- The ADPCM-A `e` envelope's pointer table is address 0 (the reset code is read as pointers).
- An unknown text byte ends the reading and leaves the channel waiting 65535 ticks.
- A music ADPCM-A channel under an effect is not ticked, so it falls behind the other channels.
- Tempo values from 240 on read the code after the tempo table.

## Validation (tools/adksnd)

- `captureadk.py --songs`: our emulator's core (makoto3's Geolith with the Z80 port tap): power-on, the game's
  commands blocked from frame 845, `$FC` at frame 900, the music command at 901, length from the model to the loop
  point or the end + 15 %.
- `songadk.py`: the model, a port of the routines above with each channel's 64-byte block kept at the driver's own
  offsets; `regsadk.py`: the comparison. Because the music runs in the main loop, the capture is walked with the
  driver's own clock: the timer-A count goes up at each captured interrupt, a tick starts when the main loop finds it
  at 2 or more, a tick that outlasts two interrupts makes the next one start at once; tick k takes the next writes in
  the capture, and is identical when they are the model's (values and order) and its first write comes after its
  starting interrupt (at most one interrupt later). Left out: the interrupt's `$27` flag resets.
- **All 36 music commands: 57485 of 57485 ticks with writes identical, 394750 captured writes, no captured write
  left unaccounted** (per song in `ninjamas_songs.md`). The count at the command was 0 in every capture.
- Used by the songs and so validated: notes, rests, lengths with dots and ties, `?`, `V`, `O` `<` `>`, pans, `T`,
  `Q`, `f`, `v`, `a`, `g`, `e` (FM), `p` pitch envelopes, `[` `]` `{` `}` `|` `(` `)`, `$`, ADPCM-A `X` `U` `?` `?` `?`,
  ADPCM-B notes and `?` (static census of the events read by the model: FM 9070 notes, ADPCM-A 5084 samples, ADPCM-B
  766 notes). Not validated: `W`, `d`, `Z`, `*`, `%`, `/`, `=`, `$FE`, ADPCM-B `X` and `K`, ADPCM-A `e`, the fade and
  pause commands, the effects.

## Compared with SNK's drivers

- **Format**: SNK's drivers play compiled byte streams (KOF98: varlen lengths, MIDI-like notes; MAKOTO: fixed 3-byte
  notes with hex-letter note codes); ADK's plays **MML text**, parsed at every note (note letters, accidentals,
  `O` `<` `>`, binary length codes with dots and ties, loop brackets), in the order of MML compilers of the time.
- **Clock**: SNK's work in the interrupt (KOF98 one timer with a tempo accumulator, MAKOTO timer B = tempo); ADK's
  interrupt only counts, the main loop plays a tick per two timer-A interrupts with timer A = the tempo in BPM, and
  timer B (62 Hz) runs the effects.
- **Pitch**: four F-number entries per semitone (fine steps `o` `q` `t` `u` `+` `-` and `g` detune) against SNK's
  one per semitone.
- **Effects**: an effect takes a music channel outright (ADPCM-A, FM3 / FM4, ADPCM-B) and the music part waits (ADPCM-A)
  or is muted and restored (FM, ADPCM-B); KOF98 defends music channels by priority, MAKOTO always yields.
