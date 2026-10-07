# KOF98 sound driver (SNK "Sound Driver(ROM)Ver 1.7 98/06/16")

Deep dive for building our own engine. Source: KOF98's M ROM (`/data/roms/kof98.neo`, M region, 256 KB), read with
`tools/z80disasm.py`, then checked against MAME captures interrupt by interrupt (tools/kof98snd, see Validation).
Code `$0000-$2C48` is byte-identical in KOF98, the jukebox and soccerfury_player M1. This file is the driver: protocol,
dispatch, sequencer clock, channel state machine, stream format and every opcode, output stage, effects, instruments.
The songs themselves (catalogue, structure, per-song validation) are in `kof98_songs.md`.
**It supersedes `v17_bytecode.md` and `v17_opcodes_complete.md`**: their stream encoding, most parameter counts and
several opcode meanings are wrong (corrections listed under Opcodes). Everything below is read from KOF98's code;
*(inferred)* marks what is not.

## Z80 map and ports

| Range | What |
|---|---|
| `$0000-$7FFF` | fixed ROM (driver code `$0000-$2C48`, tables `$2C4C-$3C4B`, sample tables, song data) |
| `$8000-$F7FF` | four switchable windows (bank select: `IN A,($08-$0B)` with the bank number in A's upper byte) |
| `$F800-$FFFF` | RAM (cleared `$F800-$FDDD` at reset; stack top `$FFFC`) |

Ports: `$00` read = command from the 68000 (written to REG_SOUND `$320000`), `$00` write = acknowledge,
`$0C` write = reply latch (the 68000 reads it back), `$04-$07` = YM2610 (A addr/data, B addr/data), `$08` write =
enable NMI. Default banks set at `$0164`: `$08`←`$1E`, `$09`←`$0E`, `$0A`←`$06`, `$0B`←`$02`.
(`z80disasm.py` labels ports `$00`, `$08-$0C` as YM2610 / bank switch: those comments are wrong for this driver.)

## Vectors

- `$0000` reset → `$00B0`: `IM 1`, clear RAM, defaults (`$FD11` = `$FD12` = `$FF`: music muted until `$07`;
  `$FDA0` = `$00AA`), YM2610 init (timer A = `$2B3` at `$2695`: regs `$24`=`$AC`, `$25`=`$03`; `$27`=`$30`, ...),
  main loop at `$011D`.
- `$0038` IRQ → `$194C`: the timer ISR (below).
- `$0066` NMI: a command from the 68000.

## Command path

NMI (`$0066`): advances the ring's write index `$FD67` **first**, then reads port `$00`: `$00` returns without
storing (so the main loop later executes whatever stale byte is in that ring slot: **never send `$00`**; measured: a
blocked command replaced by `$00` in MAME replayed an old `$02` and silenced the song); `$03` = hard reset at once
(`$0DC9` → `$0FFE`); `$01` = soft reset at once while `$FDBA` = 0 (`$0DBB` → `$0E20`); anything else goes into the
64-entry ring at `$FD25`. Every stored command is echoed on port `$0C` (the 68000 can read it back), then port `$00`
is written. So commands are never lost when the 68000 sends one per frame, and the heavy work runs in the main loop.

Main loop (`$011D`): `$012B` increments `$FDCA` (a free-running counter: the driver's only random source), takes the
next byte from the driver's own 16-entry queue (`$FDCB`, indices `$FDDB`/`$FDDC`: commands the songs queue with
opcode `$0C` / `$30`) or else from the ring; `$0175` dispatches:
- `< $20`: system command, jump table at `$0D7B` (below);
- `>= $20`: type byte from the table at `$3038` (one per command `$20-$FF`):
  0 = ignored, 1 = system, 2 = `$01A4` (song), 3 = `$01D3`, 4 = `$06CD`, 5 = `$0AC0`.
  KOF98's map: `$20-$4B` and `$50-$56` type 2 (music), `$65`, `$70-$73`, `$7A`, `$7F` type 5, `$C0-$FF` type 3,
  the rest 0 (so `$60` is a harmless filler: queued, then ignored; ymtap.lua's BLOCK uses it).

### System commands (`$0D7B`)

| Cmd | Handler | Effect |
|---|---|---|
| `$01` | `$0E20` | soft reset (banks, state) |
| `$02` | `$0DD8` | reset the music: plays the all-off header at `$2724` (`$110E`) and loads default FM patches (table `$2A0E`) on FM1-4 |
| `$03` | `$0FFE` | hard reset: banks, YM key-offs, ... |
| `$04` | `$1019` | stop the music (clears `$FA19`, `$FD10`, `$FD0F`; YM `$B5`/`$B6` writes) |
| `$05` / `$06` | `$104A` / `$1057` | set music mute flag `$FD11` / `$FD12` = `$FF` |
| `$07` | `$1064` | **music unlock**: clear `$FD11` and `$FD12`, re-arm timer A (`$12EF`) |
| `$08` / `$09` | `$1070` / `$1079` | clear `$FD11` / `$FD12` only, re-arm timer A |
| `$0A` + byte | `$1082` | fade out: byte → `$F8AF+2` (speed), `$FD0E` = 1 (the fade, `$15AF`, below) |
| `$0D` | `$10A2` | clear the ADPCM-A state block `$F9EF` |
| `$0E` + byte | `$10D8` | tempo of the music group: byte → `$2656` (accumulator increment, below) |
| `$0F` | `$10B2` | *(not read)* |
| `$11` | `$1096` | end the `$0A` fade |
| `$14` + byte | `$0F43` | byte - `$16` (< `$0A`) indexes `$2C4C` |
| `$15` + byte | `$0FC7` | slot 8, compared with `$311C` |
| `$18` + byte | `$0E98` | slot 0 → `$01DD` |
| `$19` + byte | `$0F0D` | slot 8 → `$06D7` (the type 4 path) |
| `$1A` `$1C` `$1E` `$1B` `$17` `$16` `$1D` + code | `$0EAA` ... | **effect in slot 1, 2, 3, 4, 5, 6, 7** |

The prefix commands read the next byte through `$0F1A` / `$01AC` (from the ring), take the slot's channel block
from the word table `$2E10` (slot 1 = `$2E10`, 2 = `$2E12`, ... 7 = `$2E1C`), store the slot in `$FD68` and
`$FD19` = `$18`, then start the code on that channel (`$0EB6`). **The 68000 chooses the channel of every sound
effect by its prefix**: KOF98 sends hits / swings as `$1A`+code and voices as `$1C`+code (brawler's
tools/brawler/sound_tap.lua, measured in MAME), so a voice never cuts a hit sound and vice versa.

## Sample effects (ADPCM-A): records, priorities, channel stealing

Command type 3 (`$C0-$FF`, handler `$01D3`) and the prefix commands (`$0EB6` → `$0204`) end in the same code:
`code` indexes a 256-entry table of 6-byte records for the slot (pointer table `$2E0E` + 2*slot: slot 0 `$3C4C`,
1 `$424C`, 2 `$484C`, 3 `$4E4C`, 4 `$544C`, 5 `$5A4C`, 6 `$604C`, 7 `$65FA`; codes at or above the limit at `$311B`
(`$F0`) take another path, `$0618`).

Record = `[priority][start:16 LE][end:16 LE][pan|level]`, addresses in 256-byte units of the ADPCM-A V ROM, the last
byte written as is to the channel's pan/level register (`$C0` = left + right, low 5 bits = level). Examples, slot 1
(the `$1A` prefix, KOF98's hit sounds): `$11` = `53 0B0F 180F D9` (start `$0F0B`, end `$0F18`: 3.3 KB, ~0.18 s at
18.5 kHz, priority `$53`, level `$19`); swings `$1E` / `$1F` priority `$A0`; empty codes `01 0000 0000 DC`.
Slot 7 (`$65FA`) has **11-byte records** `[priority][start][end][loop count][loop start][loop end][pan|level]`: the
sample plays start → loop end, then the ADPCM end interrupt (`$0306`) replays loop start → loop end `count` times
(`$FF` = for ever), then the tail loop end + 1 → end. The songs use the same tables for their ADPCM-A notes (opcode
`$0D` picks the slot; songs `$2E`, `$52`, `$53`, `$56` use slot 7 loops: measured, see kof98_songs.md).

Channel choice (`$0439` → `$0463`):
1. a 2-bit entry per (slot, code), packed at `$2E38` + slot*64 (4 codes a byte), can pin the sound to one channel;
2. otherwise the driver looks at three ADPCM-A effect channels (ids `$0B`, `$0C`, `$0D`; state `$F9E0`, `$F9E5`,
   `$F9EA`: busy flag, then the priority playing): a free one wins; else the one playing the lowest priority, and
   only if that is lower than the new sound's; a channel the music is using (music blocks `$FB35` / `$FB5C` /
   `$FB83` active = blocks 7-9 = **ADPCM-A 4-6**) counts with the music's priority (`$FD9D` / `$FD9E` / `$FD9F`).
   Nothing lower: the sound is dropped (carry).
3. the chosen channel's state gets the sound's priority, slot and code (`$044A`). While an effect owns ADPCM-A 4-6,
   the music's notes on that channel are skipped (`$035D` → `$03C4`) and so are its level writes (`$05F4`).

So KOF98's mix rule is: **every sample carries a priority; a new sound takes a free channel, else steals the
quietest-ranked one below it, else is dropped; music on a shared channel defends itself with its own priority.**

## The sequencer clock (timer A ISR `$194C`)

- **Timer A** is the only clock: value `$2B3` (regs `$24`=`$AC`, `$25`=`$03`), period 18 µs × (1024 - 691) =
  5.994 ms = **166.83 Hz** (measured in MAME: 166.85 interrupts/s). `$12EF` re-arms it (`$27`=`$35`) in every ISR.
  (The old notes' "Timer B = the sequencer tick" is wrong: the ISR tests status bit 0 = timer A; timer-B-only
  interrupts, about 1 a second in the captures, do nothing.)
- ISR order: read status (`$FD13`) and ADPCM end flags (`$FD14`); ADPCM-B end → `$0799` (looped B effects),
  ADPCM-A 6..1 ends → `$0306` (looped slot-7 samples, effect channel release); then, timer A only: re-arm, re-entry
  guard `$FD9B` (**an interrupt that arrives while the previous ISR still runs is dropped**: no tick for it; measured
  4099 of 487233 timer interrupts over all song captures, 0.8 %, most in heavy ticks), `EI`, then four groups, each
  with its own tempo accumulator (`$2605`/`$2620`/`$263B`/`$25EA`):
  1. music (`$FD10` set): fade step (`$15AF`, while `$FD0E`), the 11 music channels in block order FM1-4
     (`$FA24`...), ADPCM-A 1-6, ADPCM-B (`$FBAA`), each followed by its output refresh during a fade; then the
     effect engine (`$16DB`, `$18D3`, `$0A3E`, `$0A76`) when `$FDB8` is set;
  2. sequenced ADPCM-A effects (blocks `$FC6D`/`$FC94`/`$FCBB`; none in KOF98);
  3. ADPCM-B effects (`$FCE2`);
  4. SSG generated sounds (blocks `$FBD1`...`$FC46`) and their SSG effects (`$127A`).
- **Tempo** (`$2656`): per group, `acc += tempo`; when `acc >= 208` (`$D0`): `acc -= 208` and one tick runs. So
  **ticks/s = 166.83 × tempo / 208** (song `$21`, tempo 129: 103.47 ticks/s; the old "102.7 Hz" was a fit on 60 Hz
  frames, the Neo Geo runs at 59.19). Tempo ≥ 208: one tick per interrupt, never two. Setting a tempo (song start,
  `$0E` command, opcode `$10`) also clears the accumulator.
- A song's tick 1 runs at the first interrupt whose accumulator reaches 208 after the song start (`$10E5`).

## Songs

Music commands (type 2) → `$01A4` → `$10E5`: refused while `$FD11` (music mute) is set; song pointer = word table
`$329E` + 2*(cmd - `$20`) (cmd `$20` uses `$2BA2`; a 0 pointer = no song: `$27`). Before reading it the driver maps
the song's banks: byte `($2E06)[song]` → 4-byte bank set at `$2708` + 4*n, written to the four windows
(`IN A,($08..$0B)`; set 0 = identity, set n = the n-th 64 KB block at `$8000-$FFFF`).

Header (IX = song pointer), 36 bytes:
- `+$00..+$0A`: 11 channel enable bytes, in the channel-block order **FM 1-4, ADPCM-A 1-6, ADPCM-B** (blocks of
  `$27` bytes from `$FA24`; `$FD17` channel numbers 1-4, 8-13, 14). No SSG in music;
- `+$0B`: tempo (accumulator increment, above);
- `+$0C`: FM attenuation added to every FM TL (`$F8AF+1`); `+$0D`: added to every ADPCM-B volume (`$F8AF+4`);
- `+$0E..`: 11 stream pointers (16-bit LE, Z80 addresses in the song's bank map); an enabled channel with a non-zero
  pointer gets status 1 and its stream pointer (`IX+$0A/$0B`, also kept as the loop start `IX+$0C/$0D`).

Song start also: flags `IX+8` = `$C1` (pan L+R, direct-level mode), note = `$FF`, running opcode = `$FF`, loop and
call stacks empty, `IX+9/$0F/$10/$11` = 0; ADPCM-A sample table = slot 0 for all six; `$FD20`=`$3C`,
`$FD21`=`$24` (ADPCM-B root notes); bend range `$FDA0` = `$00AA`; the 10 effect records of FM1-4 / ADPCM-B
cleared; `$FDB8` (effects active) = 0.

### Channel block (`$27` bytes)

| Offset | Meaning |
|---|---|
| `+$00` | status: 0 off, 1 read at the next tick, 3 rest after a note's gate, 4 note sounding, 5 other event waiting |
| `+$01` | running opcode (`$FF` until the first opcode byte) |
| `+$02` / `+$03` | current note / velocity |
| `+$04/$05` | length countdown (16-bit) |
| `+$06/$07` | second countdown: the rest after the gate (status 3), or the tie overhang (flag bit 5) |
| `+$08` | flags: bit 0 direct-level mode, bit 4 tie pending, bit 5 overhang running, bits 7-6 pan (L, R) |
| `+$09` | FM: transpose (semitones, `$0F` / `$1D`); ADPCM-B: sample mode (`$0F`) |
| `+$0A/$0B`, `+$0C/$0D` | stream pointer, loop start (= stream start) |
| `+$0E` | last level written (TL / ADPCM level / B volume; the fade works on it) |
| `+$0F` | FM F-number detune (signed, `$2E`) |
| `+$10` | scaled mode: channel volume (`$2C` / `$24`); direct mode: octave (FM) / note offset (ADPCM-B) |
| `+$11` | direct mode: level offset; scaled mode: FM transpose (`$25` / `$27`) |
| `+$12..$1B` | loop stack: depth byte + 3 entries `[count][address]` |
| `+$1E..$26` | call stack: depth byte + 4 return addresses |

### The tick state machine (`$1BB5`)

Per channel and tick: status 1 → read events. Status 3 → count `+6/7` down, read when it expires. Status 4/5 → if
flag bit 5, count the overhang `+6/7` down and key the note off when it expires (`$1BE0`); then count the length
`+4/5` down; when it expires: status 5 → read; status 4 → if tie pending (bit 4): set bit 5, read (no key-off);
else key off, and if a rest remains (`+6/7` ≠ 0) status 3, else read. Expired counters are not written back (they
stay 1).

Reading (`$1C4F`): events are executed until one has a non-zero length; each event sets status 5 before its handler.

### Stream encoding (`$1C4F`; this corrects v17_bytecode.md's "$C0-$FE = duration")

An event is `[length, optional][opcode byte, optional][parameters]`:
- length (`$25C5`): `$00-$7F` one byte; `$80-$BF` two bytes, value `(b0 & $3F) << 7 | (b1 & $7F)` (max 8191);
  a byte `>= $C0` is not a length (not consumed: the event has no length and the counter keeps its old value).
  **The length is the time from this event to the channel's next event** (the wait after executing it): 0 or no
  length = the next event runs in the same tick;
- opcode (`$1C77`): a byte `11xxxxxx` sets the opcode to its low 6 bits (kept in `IX+$01`) and is consumed; any
  other byte means **running status**: the previous opcode again, the byte being its first parameter (KOF98's songs
  write runs of notes this way);
- dispatch: jump table `$1C8A` + 4*opcode (4-byte entries, `EX DE,HL; JP handler`), opcodes `$00-$34` (`$35-$3F`
  would jump into code: never used).

### Notes, gates, ties (`$1DCB`)

`$00` = `[gate varlen][note][velocity]`, `$2A` = `[note][velocity]` (gate = length). With length L and gate G:
- G < L: the counter becomes G, the rest L-G goes to `+6/7`: key-off after G ticks, then status 3 for L-G;
- G = L: key-off at the next event's tick, just before it;
- G > L: **tie**: no key-off at L, the overhang G-L keeps counting (flag bit 5) and keys off when it expires unless a
  note-on comes first. The next note-on while the overhang runs sets `$FD9C` = 1 (same note) or 3 (another note):
  - same note: FM: carrier TL rewritten, nothing else (no F-number, no key-on); ADPCM-A: nothing; ADPCM-B: volume
    only;
  - another note: FM: F-number written, **no key-on** (a slur / legato: the envelope continues); ADPCM-B: delta-N
    written without restarting the sample; ADPCM-A: the new sample starts normally.
  KOF98's songs slur with G = L + 1 (e.g. `+24 note gate 25`). `$0E` clears the tie flags (used at loop points and
  as a timed no-op).
- A note-on also restarts the channel's effects (FM, ADPCM-B: `$18BB`, below).

## Opcodes (jump table `$1C8A`)

Parameter counts are bytes after the opcode. "v17" = what `v17_opcodes_complete.md` claimed, where it was wrong.
Use counts: events executed over the 50 songs' first passes (song98.py census).

| Op | Params | Handler | What | v17 said |
|---|---|---|---|---|
| `$00` | gate (varlen), note, velocity | `$1DCB` | note on with gate (above) | 2 params |
| `$01` `$02` `$04` `$19` `$1C` `$1F` `$20` `$2B` | 0 | `$1D67` | no-op (`RET`): a rest is just an event with a length | |
| `$03` | 1 | `$2050` | instrument: FM = patch n (41 bytes at `($2E0C)`+41n, below); ADPCM-B = instrument n (`$0929`/`$091F`); others: ignored | |
| `$05` | 2 | `$2090` | pitch bend, 14-bit `lo7 \| hi7<<7`, centre `$2000`: see Pitch; **not guarded**: on ADPCM channels it writes FM registers (bug, below) | "set volume" |
| `$06` | 0 | `$1D68` | end of channel: status 0; ADPCM-A dumped, ADPCM-B reset; FM is not keyed off | |
| `$07` | count | `$20E8` | loop start: push (count, here); 0 = no loop | "effect setup", 4 |
| `$08` | 0 | `$2100` | loop end: count down the top entry, jump back while not 0, else pop | "effect tick", 3 |
| `$09` | addr16 | `$211E` | call (call stack `IX+$1E`, 4 deep) | "effect setup 2", 4 |
| `$0A` | 0 | `$2135` | return | "effect tick 2", 2 |
| `$0B` | addr16 | `$216B` | goto | 1 |
| `$0C` | cmd | `$2170` | queue a driver command (`$FDCB`), then **abort the rest of this tick** (`LD SP,($FD0C)`): the channels after this one and the effects skip the tick (measured, test `flow`) | "call_sub" |
| `$0D` | slot | `$2191` | ADPCM-A channel: sample table = slot (`$2E0E`+2*slot); slot 7 = 11-byte looping records | 2 params |
| `$0E` | 0 | `$1D5E` | clear the tie flags (bits 4, 5) | |
| `$0F` | 1 | `$21D1` | `IX+9`: FM transpose (raw, semitones); ADPCM-B sample mode (0 one sample, 1 kit, 2+ split) | "set pan" |
| `$10` | 1 | `$21D7` | tempo of the channel's group (`$2656`) | |
| `$11` | 1 | `$21DF` | YM reg `$22` (LFO enable/frequency) | |
| `$12` `$13` `$21` | 1 | `$21E6` | effect switch: bit 0 = change the pitch effect, bit 1 = its new state; bit 2 / bit 3 = the level effect | 0 params, "vibrato on" |
| `$14` `$15` `$22` | 1 + 7 / 5 + table | `$2244` | effect setup: `[0][type][delay][depth16][step16][speed]` (type 6: `[0][6][delay][-][-][n][-][speed]` + n words) = pitch effect; `[1][type][delay][depth][n][speed]` + n words = level effect; selector ≥ 2: nothing | 0 params, "portamento" |
| `$16` | 0 | `$23BD` | go to the channel's start (`IX+$0C/$0D`) | |
| `$17` | 0 | `$23C4` | `$FA1D` = 0 (stop an ADPCM-B effect's loop count) | |
| `$18` | 0 | `$23C9` | clear the six ADPCM-A loop states `$F9EF` | |
| `$1A` | 1 | `$23D9` | SSG mixer (YM `$07`): noise-enable bits OR'ed in | "loop start" |
| `$1B` | 3 | `$23FC` | SSG envelope: YM `$0D`, `$0B`, `$0C` | "loop end" |
| `$1D` | 1 | `$2412` | FM transpose, signed 6-bit (bit 6 = minus) → `IX+9` | |
| `$1E` | code | `$2420` | play sample effect `code` (slot 0, through the allocator, `$01DD`) | |
| `$23` | 2 | `$230F` | bend range `$FDA0` (16-bit, global): bend units per quarter semitone (default `$AA`: ±`$2000` = ±12 semitones) | |
| `$24` | 1 | `$2318` | `IX+$10` (volume / octave) without writing | |
| `$25` | 1 | `$231E` | `IX+$11` = p - `$88` (FM), - `$80` (ADPCM-A), - `$B8` (ADPCM-B) | |
| `$26` | 0 | `$2341` | **scaled mode**: clear flag bit 0. Every KOF98 channel starts with it | "key off" |
| `$27` | 1 | `$2346` | FM: `IX+$11` = p - `$18` (transpose; KOF98 uses `$24` = +12, `$30` = +24); ADPCM-B: root note `$FD20` = p | |
| `$28` | 1 | `$2373` | OR p into the FM channel's `$B4` shadow (AMS/PMS) and write it — **always to port B** (bug: FM1/FM2's value lands in port B `$B5`/`$B6` = FM3/FM4; measured, test `fm2`) | "set pan" |
| `$29` | 2 | `$23A6` | ADPCM-B split: split note (p1 - `$18` → `$FD22`), high root `$FD21` = p2 | |
| `$2A` | note, velocity | `$1DCB` | note on, gate = length | |
| `$2C` | 1 | `$1F57` | volume `IX+$10` and rewrite the level now (FM TL, ADPCM-B `$1B`) | "volume slide" |
| `$2D` | 1 | `$1EFE` | FM modulators' TL = p (the operators the algorithm does not output; mask table `$26F7`) | "bank switch" |
| `$2E` | 1 | `$1EA4` | FM F-number detune `IX+$0F` = p - `$40` (KOF98: ±6, the echo voices) | "transpose" |
| `$2F` | slot, low, high | `$1EAC` | random range: `$FDBB`+3*(slot-1) = [low, count, mask] | 6 params |
| `$30` | slot | `$1EDD` | queue a random command low + (`$FDCA` & mask, < count), abort the tick like `$0C` | 3 params |
| `$31` / `$32` / `$33` | 0 | `$1F12` | **pan** L+R / L / R: flag bits 7-6; FM writes `$B4` now, ADPCM-A at its next note, ADPCM-B at its next key-on | "tie / legato on / off" |
| `$34` | 41 bytes | `$2430` | inline FM patch (same format as the patch table) | "play subsong" |

Opcodes the 50 songs use (census): notes `$2A` 45105, `$00` 23280; `$08` 6784, `$07` 2586; pan `$32` 4130,
`$33` 3628, `$31` 3002; `$2C` 2768; `$0D` 2506; `$0A` 1669, `$09` 1265; `$03` 981; `$0B` 892; `$0E` 524; `$26` 364;
`$2E` 160; `$06` 91; `$05` 91; `$0F` 83; `$27` 34; `$12` 12; `$14` 2; `$10` 2. Never used by a song: `$01-$02`,
`$04`, `$0C`, `$11`, `$16-$1E`, `$23-$25`, `$28-$29`, `$2D`, `$2F-$30`, `$34` (all exercised by
tools/kof98snd/testsong98.py and checked in MAME, see Validation).

## Output stage

### Levels (`$1FD5` → `$1F79`)

Two modes, flag bit 0:
- **direct** (song default, until `$26`): level = velocity + `IX+$11` (8-bit wrap);
- **scaled** (all KOF98 songs): level = `table[(velocity × volume × 2 >> 8) - 1]` (velocity 0: `table[0]`), volume
  = `IX+$10` (`$2C`/`$24`). Tables: FM `$311D` (TL `$33` falling to `$01` over the 128 entries, 2 entries per step),
  ADPCM-A `$319D` (`$00` → `$1F`, 4 entries per step), ADPCM-B `$321D` (`$00`, `$02` ... `$FE`).

Then per chip:
- FM (`$2003`): TL = level + header `+$0C`, clamped to `$7F`, written to the **carriers only** (`$2546`, mask table
  `$26EF` by algorithm: alg 0-3 `$08` = S4; 4 `$0C` = S2, S4; 5-6 `$0E` = S3, S2, S4; 7 `$0F` = all). The patch's
  own carrier TLs are never used; modulators keep the patch's TL (or `$2D`'s);
- ADPCM-A (`$05D5`): reg `$08+ch` = pan bits (flag 7-6) | (level + `$F8B2`) & `$1F`;
- ADPCM-B: reg `$1B` = level + header `+$0D` (not clamped: wraps).

### Pitch

- FM (`$2447`): n = note + `IX+9` (+ `IX+$11` in scaled mode), `& $7F`; `$2BC8[n]` = semitone<<4 | block
  (valid n `$18-$77`: block (n-`$18`)/12, i.e. `$18` = C0, `$48` = C4 = 261.6 Hz; others: no write at all);
  F-number = word `$2A68` + semitone*8 + fine (bytes; 4 words per semitone: quarter-semitone steps; C = 618) +
  signed `IX+$0F`; in direct mode block += `IX+$10` (≥ 8: no write). Written `$A4+ch` then `$A0+ch`, shadowed
  (`$F8C9`/`$F950` + `$70`/`$74`); then key-on `$28` = `$F0` | channel (1, 2, 5, 6) unless a slur.
- Bend `$05` (`$20A9`): signed value v = 14-bit - `$2000`; k = ceil(|v| / `$FDA0`) quarter-semitone steps, applied as
  note ± k div 4 and fine ± 2*(k mod 4) (the F-number table index); `$05` re-runs the note-on pitch path, so it
  **also writes a key-on** (`$28`) unless the channel is in a slur state (`$FD9C` bit 1).
- ADPCM-B (`$0825`): mode `IX+9`: 0 = one sample (instrument's record, root `$FD20`); 1 = kit: note = sample record
  number, its own delta-N (record +10); 2+ = split at `$FD22` between two records (low root `$FD20`, high `$FD21`).
  Scaled mode: index = note - root + 12 (- 12 / + 0 for samples whose own delta-N is `$375A` / `$6EB3`), `& $7F`,
  octave = index / 12 (& 7), delta-N = word `$2B2A` + 24*octave + 2*semitone (index 24 = `$375A`); direct mode: note
  = octave<<4 | semitone into the same table. Key-on writes `$11`=0, `$14`=`$15`=0, `$10`=1, flags, `$10`=0,
  delta-N `$19`/`$1A`, start `$12`/`$13`, end `$14`/`$15`, volume `$1B` (unless the level effect runs), `$10`=`$80`,
  pan `$11` = flag bits 7-6. Key-off = `$11` = 0 (in direct mode skipped while `$FD9C` bit 1 is set: `$FD9C` is
  global, the last note-on of any channel).
- ADPCM-A (`$035D`): note = sample number in the channel's table (`$0D`); key-on: dump the channel, flag reset,
  start / end regs, `$01`=`$3F` when no song runs, then key bit; key-off = dump (`$00` = `$80` | bit).

### Effects (`$1775`; records of 13 bytes at `$F7F3` / `$F85B` + 13*index)

Two effects per channel, the same engine: the **pitch effect** (FM: F-number offset; ADPCM-B: delta-N offset) and
the **level effect** (ADPCM-B: volume = value + velocity; FM: see bug). Index (`$149E`): FM1-4 = 1-4, ADPCM-B = 5;
other channels land on unrelated records (bug, never used). Set from the FM patch (bytes 30-40) or `$14`, switched by
`$12`, processed once per tick after the channels, in the order FM pitch, FM level, B pitch, B level, while `$FDB8`.

Record: `+0` flags (0 on, 1 delay done, 2 direction, 3 finished, 4 negate output, 5 wait for the first note),
`+1` random pointer, `+2` type, `+3/4` depth (or table address), `+5/6` step (type 6: index, count), `+7` delay,
`+8` delay counter, `+9/A` value, `+B` speed, `+C` speed counter.

Each tick: nothing if depth = 0, finished or waiting; count the delay down (once); count the speed down; on 0 reload
it and step the value:

| Type | Step (`$17B0`) |
|---|---|
| 0 | saw: value += step; past +depth → -depth |
| 1 | square: ±depth alternately |
| 2 | triangle: value ± step between -depth and +depth (vibrato) |
| 3 | triangle, but value 0 on ticks where bit 1 of ROM byte `$00xx` (xx = `+1`, incrementing) is set (pseudo-random) |
| 4 | one-shot saw: as 0, finished (value 0) at the first wrap |
| 5 | one-shot hump: as 2, finished (value 0) when it comes back to ≤ 0 |
| 6+ | table: words `depth[index]`, index ping-pongs 0..count-1, output sign flips every full cycle |

Output: FM pitch → `$A4`/`$A0` = shadow F-number word + value (16-bit add: overflow walks into the block bits; the
shadow is not updated); ADPCM-B pitch → `$19`/`$1A` = note delta-N + value; ADPCM-B level → `$1B` = (value low byte)
+ velocity. Note-on (`$18BB`): an enabled effect restarts (value 0, delay and speed counters reloaded) on the first
note after it was set, and on every note if it has a delay; with delay 0 it free-runs. Effects keep running after
the song's channels end (the music tick never stops by itself: measured, test `fxtypes`).

KOF98's songs use only type 0 (song `$33`, FM3/FM4: `$14` type 0 delay 2 depth 16 step 5 speed 2, switched on and
off by `$12`); no patch of the songs enables an effect.

### FM patch (41 bytes, `$130C` / `$132A`)

| Bytes | Content |
|---|---|
| 0-27 | register values in YM order, 4 operators each (S1, S3, S2, S4): `$30` DT/MUL ×4, `$40` TL ×4, `$50` KS/AR ×4, `$60` AM/DR ×4, `$70` SR ×4, `$80` SL/RR ×4, `$90` SSG-EG ×4. Carrier TLs are skipped (`$1350`) |
| 28 | `$B0` FB/ALG |
| 29 | `$B4` AMS/PMS (pan bits kept from the shadow) |
| 30 | effect types: low nibble = pitch effect, high nibble = level effect |
| 31-36 | pitch effect: delay, depth16 (bit 15 = negate flag, the value is not negated), step16 (0 = off), speed; type 6: table number (pointer table `($2E32)`, which is 0 in KOF98), count, -, speed |
| 37-40 | level effect: delay, depth (bit 7 = negate flag), step (0 = off), speed; type 6: table number, count, speed |

KOF98: patch table `$34B2`, 47 records; the songs use patches 0-15, 17-24, 26-30, 32-41. (The old note "7 per
operator" is wrong: the 28 bytes are grouped by register.) `$FDA3` (the patch's 4 TLs per channel) and `$FDB4`/
`$FDB6` (modulator masks) are written and never read.

### ADPCM-B instruments

`$2E08` → `$341E`: instrument → sample record number; `$2E0A` → `$34AE`: split pairs (2 instruments); `$2E1E` →
`$711A`: 13-byte records `[priority][start16][end16][loop count][loop start16][loop end16][delta-N16][-]` (256-byte
units). KOF98's songs use modes 0 (pitched sample, 68 channel set-ups) and 1 (kit, 17).

### Fade (`$0A` command, `$15AF`)

Every time `$FD15` += speed overflows: FM `+$0E` += 2 (channel stops at `$78`), ADPCM-A `+$0E` -= 2 (stops at 0),
ADPCM-B -= 5; when all are down the music stops (`$169F`). During a fade the per-channel output refresh after each
tick writes these levels and the normal level writes are skipped.

## Driver bugs and quirks (all measured unless marked)

- NMI with `$00`: the ring index advances, the main loop replays a stale command (above).
- Nested timer interrupts are dropped (0.8 % of ticks over the song captures): real tempo is slightly below
  166.83 × tempo / 208, and two songs with the same tempo do not stay in lock-step.
- `$05` on an ADPCM channel runs the FM pitch path with channel number - 2: port B regs `$A4+n`/`$A0+n` and a key-on
  `$28` = `$F0 | (n & 3) | 4` for a non-existent FM channel (song `$26` does it 13 times on ADPCM-B: `b B0`, `b AC`,
  `a 28 FC` in the capture), and restarts the effect records it maps to.
- `$28` writes AMS/PMS to port B even for FM1/FM2 (lands on FM3/FM4).
- The FM level effect recomputes the TL from the velocity and writes it unchanged (`$1924` passes the value in B,
  `$2003` overwrites B): no tremolo; measured: TL `$18` rewritten every 3 ticks (test `fm2`).
- A patch's negative effect depth sets the negate flag without negating the depth (`$13CA`), unlike `$14` (`$2278`).
- Effect type 6 from a patch reads its table pointer from `($2E32)` = 0, i.e. from the code at `$0000`.
- `$0C` / `$30` abort the tick: the channels after the queuing one lose a tick for good (test `flow`: FM4 one tick
  late after FM3's `$0C`).

## Validation (tools/kof98snd)

- `ymtap.lua` (MAME): every YM2610 write of the sound CPU, every 68000 command, `q 1` per timer interrupt that runs
  the sequencer (write tap on `$FD9B`; `q 2` = dropped nested one), `i` = the ISR's status read, BLOCK (game
  commands → `$60`), SEND, PATCH (test songs into the free ROM area `$2C56-$2DFF`).
- `song98.py`: decoder + tick-exact model of everything above; `validate98.py`: model vs capture at the same timer
  interrupt with the same register values; `testsong98.py`: synthetic songs for the unused opcodes.
- All 49 songs `$21-$56` from power-on (game commands blocked after its `$07`, song sent at frame 260), one full
  loop or to the end: **55304 key-ons, 81522 key-offs / dumps, 28677 FM F-number writes (incl. 1392 vibrato
  steps), 947 FM pan writes, 951 ADPCM-B delta-N and 1461 volume writes predicted, every one found at the same
  timer interrupt with the same values; no unpredicted key-on or F-number write** (table in kof98_songs.md). Only
  extra writes: patch loads (TL, `$B4`) and the key-on preambles, which the model does not list one by one, and
  the slot-7 loop replays (128, driven by the sample length).
- Test songs (all match): `fxtypes` (effect types 1-6, delay, negative depth: 1692 F-number writes), `fm2` (level
  effect, `$2D`, `$11`, `$28`, `$05`+`$23`, `$2E`, `$1D`, direct mode `$24`/`$25`/`$0F`), `flow` (`$0C` abort,
  `$34`, ties into same / other note, `$0E`, no-length note, rests), `adpcmb` (B pitch / level effects: 1803 + 901
  writes, kit and split modes, `$27`, `$29`, `$05` on B).

## What our engine should take from it

Measured or read above, in order of value for a brawler:

1. **One command ring, never lose a command.** NMI only queues (64 entries) and echoes the byte back on port `$0C`;
   the main loop does the work. Our 68000 side can then send one byte a frame without handshakes (the brawler's
   sound.c already paces one byte a frame, the KOF98 pace). Unlike KOF98, ignore `$00` before advancing the index.
2. **Effects pick their slot by prefix, then fight for a channel by priority.** Seven prefixes = seven sample
   tables (hits, voices, ...). Within the three ADPCM-A effect channels: free channel first, else steal the lowest
   priority below the new sound, else drop it; music on a shared channel defends with its own priority. Cheap and it
   is why KOF98's hit storms never cut a voice. Copy it as is.
3. **6-byte sample records** `[priority][start][end][pan|level]` in 256-byte units: the whole effect list is a
   table, no code per sound; 11-byte records add an intro / loop / tail for ambiences.
4. **Songs are byte streams per channel**, 11 channels (FM 1-4, ADPCM-A 1-6, ADPCM-B; SSG unused), MIDI-like:
   length varlen + running-status opcode + parameters, loops / calls on small per-channel stacks, slurs by gate >
   length. Compact (song `$21` = a few KB for 46 s) and decodable: song98.py turns it into events and predicts every
   register write; the same model is the reference for a converter from our own sequences.
5. **Tempo = one fixed timer (A, 166.83 Hz) + a fractional accumulator per group**: any tempo without reprogramming
   the timer, music and effects at independent tempos in the same ISR.
6. **Velocity × channel volume through a table per chip**, TL on carriers only: one volume opcode works for FM and
   both ADPCM kinds.
7. **Echo voices instead of an effect**: KOF98's songs double a line on another FM channel, delayed 6-12 ticks,
   detuned ±6 F-number, panned L / R, quieter (kof98_songs.md): free stereo chorus.

Do differently:
- **Don't share the music's ADPCM-A channels with effects by default**: KOF98 does (ADPCM-A 4-6 carry both), which
  is why it needs priorities on the music too. With 6 ADPCM-A channels, give music 3 and effects 3 (KOF98's stage
  themes do exactly that: A1-3 only).
- **Keep the ISR short or count missed interrupts**: KOF98 drops nested timer interrupts (tempo drift).
- **Fix the unguarded paths**: per-chip opcode checks (`$05`, `$28`), a working level effect.
- **Document the stream format before writing data**: SNK's own notes are lost; ours are this file + song98.py.
- **SSG**: KOF98's music never uses it; a brawler can leave it to effects (UI blips) and keep it out of the music.

## Effects during music, measured (tools/kof98snd/diffcap.py)

Two MAME runs from the same fight state (`vs`), 1200 frames each: quiet (the stage music only) and fighting (P1
attacking: `$1A`+`$11-$14` hits, `$1A`+`$1E`/`$1F` swings, `$1C`+`$C4`/`$C5`/`$C7`, `$1D`+`$AE`/`$AF`, `$16`+
`$32`/`$39`). MAME replays a state identically, so the writes present only in the fighting run are the effects':
- **all effects are ADPCM-A samples**: 413 ADPCM-A writes + 221 end-flag resets (port A `$1C`: the channel's bit,
  then 0); **no FM, no SSG, no ADPCM-B** write was added;
- **they land on ADPCM-A 4, 5, 6 only** (key-ons: 25 / 22 / 12; every prefix, voices included), the channels the
  allocator shares with the music's blocks 7-9;
- **the music lost nothing**: no music write disappeared from the fighting run (only two timer re-arms moved a
  frame). In this stage track the music's ADPCM-A 4-6 lines were idle or lower priority whenever an effect came.

## The three sound families, by chip (measured)

| Family | Commands | Engine path | Chip | Measured |
|---|---|---|---|---|
| Music | type 2: `$20-$4B`, `$50-$56` | 11 channel streams (`$FA24`) | FM 1-4, ADPCM-A 1-6, ADPCM-B | all 49 songs: every note and pitch write predicted (kof98_songs.md) |
| Fight effects | prefixes `$1A $1C $1E $1B $17 $16 $1D` + code, type 3 `$C0-$FF` | 6-byte sample records + priority allocator | ADPCM-A 4-6 only | fight capture: 59 key-ons, music untouched |
| Generated sounds | type 5: `$65`, `$70-$73`, `$7A`, `$7F` | song-like headers (`($2E00)`, priority at +4) played on 4 extra channel blocks at `$FBD1` | **SSG** (tones only; `$7F` also the envelope) | each sent alone in MAME: SSG writes only |

- Type 5 = the only synthesized effects: three-voice SSG tone patterns, noise never enabled (mixer `$38-$3F`).
  Lengths: `$7A` 0.05 s, `$70` 0.2 s, `$72` 0.4 s, `$71` 0.7 s, `$7F` 1.0 s, `$65` 2.7 s; `$73` writes nothing
  (a stop, *inferred*); `$7F` also shifts the music's own writes (equal numbers added and removed: a pause/hold of
  the music, *inferred*). Approximate WAVs: tools/kof98snd/ssgwav.py (`/data/tmp/snd98/wav/kof98_ssg_*.wav`).
- Sequenced effects on the ADPCM-A effect channels (sample codes `>= $F0`, table `($2E34)`, 3 channel blocks at
  `$FC6D`): supported by the engine (record = [priority][channel group][stream]), **empty in KOF98** (16 null
  pointers).

So KOF98's split is by chip: **FM + ADPCM for music, ADPCM-A 4-6 for fight sounds, SSG for the generated cues**;
the only sharing (ADPCM-A 4-6, music vs effects) is arbitrated by priority.

## SSG cues (type 5, `$0AC0`): the brawler's menu sounds (TODO #63)

What the driver leaves free on the SSG: **all of it**. No KOF98 song writes an SSG register (all 49, song98.py census
and captures), the fight effects are ADPCM-A only (diffcap above), so SSG A-C and the noise generator belong to the
type-5 cues alone. The path, read from `$0AC0` and measured in our emulator (tools/port/capture_snd.py):
- command → type 5 (`$3038`) → index cmd - `($3118)` (= `$60`) into the word table `($2E00)` = `$331E` (32 entries,
  `$60-$7F`); a 0 pointer = nothing. Refused while the effects mute `$FD12` is set (`$06`; `$07` clears it), except
  cmd `($329D)` = `$7F`.
- header, 14 bytes: `[4 enables][priority][noise mixer bits → $FD09][4 stream pointers]`, the four channel blocks
  (`$27` bytes, the music's layout) `$FBD1` / `$FBF8` / `$FC1F` = SSG A / B / C (channel ids 5-7), `$FC46` = id 0, the
  noise channel (its note = noise period, reg 6, `$0C0D`). An enable of 0 skips that block.
- one cue at a time: a new cue plays when its priority value is **≤** the running one's (`$0AFF`: lower = stronger;
  `$FD0B` keeps the last one, `$FD0A` = busy), `$0C6D` silences the SSG first (levels 0, mixer `$3F`).
- clock: group 4 of the timer A ISR, tempo `$5A` set by every cue start (`$0B5B`): 72.2 ticks/s, 13.9 ms a tick.
- streams: the song format (length, opcode, running status); notes = `$2A` note velocity (gate = length) or `$00`;
  **velocity = the SSG volume register as is** (0-15); key-off = the channel's tone bit off in reg 7 (level kept).
  Note byte (`$0B74`): bits 7-5 octave shift o, bit 4 half a semitone, bits 3-0 semitone n: period = word(`$2AC8` +
  8n (+4)) >> o, the table being C1 = 32.7 Hz at 125 kHz / period. Opcodes `$1A` (noise bits into reg 7) and `$1B`
  (hardware envelope `$0D`, `$0B`, `$0C`) are the cue-only ones.
- **the first channel to reach its end (`$06`) ends the cue on every channel** (measured: a 21-tick voice lost its
  last step when the other voice ended at tick 18), so the voices of a cue have one length.
- KOF98's own cues: `$65`, `$70-$72`, `$7A`, `$7F` (data `$774B-$7B2D`); `$7F` holds the music (*inferred*).

**Fatal Fury Special / KOF94 (MAKOTO v3, docs/ff3_sound_driver.md):** the same design one generation earlier: header
`[priority][4 streams][4 flags][noise bits]` (KOF94 table `$3BC0`, cues `$60 $61 $6A $7F`; Fatal Fury Special `$3F9C`,
cues `$60-$69 $7F`), blocks SSG A-C + a noise block, the song interpreter at timer A's rate. How a blip is written
there (read from the data, levels *inferred* from the `$8v` bytes): **no envelope generator and no pitch sweep, only
volume steps**: each note struck loud then repeated quiet (`$8B` then `$84`, 2 ticks each: a pluck), notes in
arpeggio by octave jumps (`$8A` → `$AA`), the three voices playing a chord of three such lines; longer cues decay
by stepping the level of a held note down (FFS `$65`: 12, 10, 8, 7, 6, 5, 4, 2); the noise block only rests. Only
`$7F` (both games) sets the hardware envelope (`$53`) and noise bits (`$51`). FF3's pitch sweep opcode `$5F` is
unused by these cues.

**The brawler's cues** (songs.json "ssg", tools/port/ssg_cues.py, built into the M ROM by build_snd.py; no driver
code changed): commands `$74-$77` (type 0 in KOF98, now 5), data in the fixed area's free bytes `$2C56-$2DFF`,
priority 1, KOF98's own cues kept. Written in the MAKOTO idiom (struck note, quieter repeats; a second voice an
octave down one tick late): CURSOR `$74` (E7, 69 ms), CONFIRM `$75` (C7 G7 C8 rising, 291 ms), CANCEL `$76` (G6 D6
G5 falling, 236 ms), UNLOCK `$77` (C6-C8 arpeggio over a C5 / G5 bass, 637 ms). Sent by the game with `snd_ssg()`
(sound.c): title (cursor, start, options), options (rows, values, EXIT / B back), select (cursor, pick), BOSS
UNLOCKED. A cue sent just before a song start has its first note stretched ~4 interrupts by the song start's work,
so the game sends the cue after the song command.
COIN `$78` (TODO #199) = KOF94's coin sound, its SSG effect song `$7F` (KOF94 sends it at every credit, from its
sound routine `$6556`; measured in our emulator) brought over by `ssg_cues.py --import` of its capture: a 3-voice
chord stepping 226 / 165 / 126 -> 103 / 102 / 79 -> 47 / 56 / 41 (periods), struck at level 11 then decaying, the
voices 4 KOF94 interrupts apart, 1.04 s. Its periods are not on the note table, so they are **raw periods** ("P226"):
each takes a table word (`$2AC8` + 8n (+4)) that no named note of any cue uses, written with the period itself and
read with octave shift 0 (no KOF98 song nor port writes the SSG: the table is the cues' alone; KOF98's own cues, never
sent by the brawler, would read those words). Its steps start on the nearest cue tick (13.85 ms; KOF94's interrupt is
9.12 ms): every step within 9.7 ms of KOF94's in our emulator, the same SSG states in the same order. To fit, the
streams use running status (a note after a note leaves out its `$EA` when the note byte is < `$C0`: the four former
cues write the same SSG registers as before) and the COIN header sits in the cue table's words for `$66-$6F` (type-0
commands: those words are never read). The game sends it (main.c `coin_in`) whenever a credit count in backup RAM
goes up (MVS), on every screen; the coin that ends the attract demo sounds after the title's song start.
Measured (`ssg_cues.py --check`): each cue alone writes SSG registers only, its notes / levels / periods in order,
each step within 2 interrupts of its length. `--mix` (song + `$1A` hits with and without the 8 cues over them): every
song and effect write identical in value and order; in the select song's run one more timer interrupt dropped by the
re-entry guard (6 with cues, 5 without: the music 6 ms later from there), the fight song's run none. The game's
songs stay register-identical to song98.py's model (`capture_snd.py --check`).
