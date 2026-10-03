# Fatal Fury 3 songs

The 40 music commands of Fatal Fury 3's sound driver (`ff3_sound_driver.md`): catalogue, structure, the techniques the
song data uses, and the per-song validation of tools/makoto3's model against the real driver. Everything is decoded
by `tools/makoto3/song.py` from the M1 ROM; "measured" = seen in our emulator.

    python3 tools/makoto3/song.py /data/tmp/snd98/ff3/ff3_m1.bin --catalog              one line per command
    python3 tools/makoto3/song.py /data/tmp/snd98/ff3/ff3_m1.bin 0x26 --list            the event listing
    python3 tools/makoto3/capture.py --songs /data/tmp/snd98/ff3/cap                    capture every song
    python3 tools/makoto3/regs.py /data/tmp/snd98/ff3/ff3_m1.bin 0x26 /data/tmp/snd98/ff3/cap/cap_26.txt

## Catalogue

"One pass": music ticks to the point where the last channel jumps back (looping songs), to the end, or to the chain;
seconds from the timer-B period (including `$33` tempo changes). "Heard at": the screen when the game itself sent
the command, from power-on with no input (attract), and from coin, start, the first character, and each of the four
opponents of the enemy-select screen (screenshots in `/data/tmp/snd98/ff3/play*`, `attract`). In 11 minutes of
attract mode the game sends one song only, `$3E`, six times; its demo fights have no music, only effects. Songs not
heard there are left unnamed. Validation: interrupts whose register writes (minus timer-flag and end-flag
housekeeping) are identical in the capture and in the model, same values, same order; and the number of captured
writes compared.

| Cmd | Header (bank) | TB (ticks/s) | Channels | One pass | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|---|---|
| `$20` | `$7F6F` (0) | `$B0` (43.4) | FM1-4 A1-6 B | 3 ticks, 0.1 s | stops (`$40`) | 3 ticks of rests on every channel: a silence (*inferred*) | 3 / 3, 162 |
| `$21` | `$7FE4` (0) | `$C6` (59.9) | FM4 A1-6 B | 2450 ticks, 40.9 s | stops (`$40`) | — | 253 / 253, 4031 |
| `$22` | `$8540` (0) | `$B9` (48.9) | FM1-4 A1-6 B | 385 ticks, 7.9 s | loops | — | 319 / 319, 6620 |
| `$23` | `$89D4` (0) | `$AB` (40.8) | FM1-4 A1-3 B | 865 ticks, 21.2 s | loops | player select (measured) | 308 / 308, 5217 |
| `$24` | `$8EA9` (0) | `$B4` (45.7) | FM1-4 A12356 | 795 ticks, 17.4 s | loops | enemy select (measured) | 239 / 239, 3402 |
| `$25` | `$9456` (0) | `$B0` (43.4) | FM4 A1236 B | 481 ticks, 11.1 s | loops | — | 198 / 198, 3532 |
| `$26` | `$8000` (2) | `$B6` (46.9) | FM1-4 A1-3 B | 3169 ticks, 67.5 s | loops | stage, vs Bob Wilson (measured) | 468 / 468, 11571 |
| `$27` | `$8D94` (2) | `$C0` (54.3) | FM1-4 A1-3 B | 4777 ticks, 88.0 s | loops | stage, vs Franco Bash (measured) | 1658 / 1658, 27321 |
| `$28` | `$8000` (1) | `$BA` (49.6) | FM1-4 A1-3 B | 3889 ticks, 78.4 s | loops | stage, vs Blue Mary (measured) | 1302 / 1302, 19558 |
| `$29` | `$9EB9` (2) | `$B6` (46.9) | FM1-4 A1-3 B | 3457 ticks, 73.7 s | loops | stage, vs Joe Higashi (measured) | 609 / 609, 14471 |
| `$2A` | `$A6DE` (2) | `$CA` (64.3) | FM1-4 A1-6 B | 6353 ticks, 98.8 s | loops | — | 3646 / 3646, 36514, 88 loop replays as predicted |
| `$2B` | `$B3D0` (2) | `$A5` (38.2) | FM1-4 A1-3 B | 3841 ticks, 100.7 s | loops | — | 2515 / 2515, 22818 |
| `$2C` | `$8FB2` (1) | `$B4` (45.7) | FM1-4 A1-3 B | 3529 ticks, 77.2 s | loops | — | 1719 / 1719, 21993 |
| `$2D` | `$9865` (0) | `$9F` (35.8) | FM1-4 A1-3 B | 3181 ticks, 88.9 s | loops | — | 1011 / 1011, 18826 |
| `$2E` | `$9F2B` (1) | `$B6` (46.9) | FM1-4 A1-3 B | 3841 ticks, 81.9 s | loops | — | 1608 / 1608, 19765 |
| `$2F` | `$B370` (1) | `$CC` (66.8) | FM1-4 A1-3 B | 4687 ticks, 70.2 s | loops | — | 1113 / 1113, 16664 |
| `$30` | `$BE63` (2) | `$BA` (49.6) | FM1-4 A1-3 B | 4237 ticks, 85.4 s | loops | — | 642 / 642, 15110 |
| `$31` | `$D526` (1) | `$A9` (39.9) | FM1-4 A1-3 B | 4039 ticks, 101.2 s | loops | — | 1677 / 1677, 20470 |
| `$32` | `$C6C8` (1) | `$A6` (38.6) | FM1-4 A1-3 B | 2883 ticks, 74.7 s | loops | — | 1764 / 1764, 19483 |
| `$33` | `$D547` (2) | `$C3` (56.9), `$33` changes | FM1-4 A1-3 B | 4225 ticks, 74.8 s | loops | — | 1374 / 1374, 18219 |
| `$34` | `$8EA9` (0) | `$B4` (45.7) | FM1-4 A12356 | 795 ticks, 17.4 s | loops | win screen (measured) | 239 / 239, 3402 |
| `$36` | `$A701` (0) | `$C2` (56.0), `$33` changes | FM1-4 A1-3 B | 1249 ticks, 22.4 s | chains to `$33` at tick 1249 | — | 1505 / 1505, 20511 |
| `$37` | `$A8C4` (0) | `$BB` (50.3), `$33` changes | FM1-4 A1-3 B | 1513 ticks, 32.8 s | chains to `$32` at tick 1513 | — | 2138 / 2138, 23376 |
| `$3A` | `$D2FD` (2) | `$AE` (42.3), `$33` changes | FM1-4 A1-3 B | 1080 ticks, 23.2 s | stops (`$40`) | — | 307 / 307, 2927 |
| `$3B` | `$ABC5` (0) | `$9D` (35.1) | FM1-4 A1236 B | 542 ticks, 15.5 s | stops (`$40`) | continue (measured) | 182 / 182, 2110 |
| `$3D` | `$AE80` (0) | `$B0` (43.4) | FM1-4 A1236 B | 2017 ticks, 46.5 s | loops | — | 772 / 772, 14621 |
| `$3E` | `$BB73` (0) | `$C6` (59.9) | FM4 A1-6 B | 2570 ticks, 42.9 s | stops (`$40`) | title / attract (measured) | 235 / 235, 4044 |
| `$3F` | `$C09F` (0) | `$B0` (43.4) | A1-6 B | 170 ticks, 3.9 s | stops (`$40`) | game over (measured) | 13 / 13, 181 |
| `$40` | `$8EA9` (0) | `$B4` (45.7) | FM1-4 A12356 | 795 ticks, 17.4 s | loops | same data as `$24` | 239 / 239, 3402 |
| `$41` | `$C189` (0) | `$AB` (40.8) | FM4 A1234 B | 97 ticks, 2.4 s | chains to `$42` at tick 97 | — | 206 / 206, 2510 |
| `$42` | `$C263` (0) | `$AB` (40.8) | FM4 A1234 B | 770 ticks, 18.8 s | loops | — | 174 / 174, 2095 |
| `$43` | `$C43D` (0) | `$95` (32.5) | FM4 A12345 | 386 ticks, 11.9 s | loops | — | 114 / 114, 1264 |
| `$44` | `$D16E` (2) | `$A8` (39.5), `$33` changes | FM1-4 A1-3 B | 674 ticks, 18.6 s | fades out (`$3F`), stops | — | 334 / 334, 5140 |
| `$45` | `$C659` (0) | `$B5` (46.3) | FM4 A1234 | 386 ticks, 8.3 s | loops | — | 118 / 118, 1452 |
| `$46` | `$CDBF` (2) | `$89` (29.2), `$33` changes | FM1-4 A1-6 B | 744 ticks, 28.0 s | stops (`$40`) | — | 260 / 260, 3328 |
| `$47` | `$C801` (0) | `$85` (28.2) | FM1-4 A12356 B | 5762 ticks, 204.1 s | stops (`$40`) | — | 1816 / 1816, 17439 |
| `$4A` | `$DAC9` (0) | `$B0` (43.4) | FM1-4 A1-3 B | 2017 ticks, 46.5 s | loops | — | 745 / 745, 12282 |
| `$4B` | `$E612` (0) | `$CF` (70.9) | FM1-4 A12345 B | 820 ticks, 11.6 s | loops | — | 322 / 322, 3451 |
| `$4C` | `$E9C1` (0) | `$B0` (43.4) | A1-3 | 182 ticks, 4.2 s | stops (`$40`) | — | 13 / 13, 88 |
| `$5F` | `$EA46` (0) | `$C0` (54.3) | FM1-4 | 386 ticks, 7.1 s | stops (`$40`) | boot: started by command `$02` under the NEO-GEO logo (measured) | 259 / 259, 1917 |
| all 40 | | | | | | | **32417 / 32417**, 431287 |

Shared data: `$24`, `$34` and `$40` are one song (header `$8EA9`): the enemy-select and win screens play the same
music. `$36` and `$37` are intros that end in opcode `$47` and continue as `$33` and `$32`; `$41` (2.4 s) continues
as `$42`. `$21` and `$3E` (title) have the same tempo and channel set and different data (`$21` not heard).
Songs stopping by themselves (`$40`): jingles `$3B` continue, `$3F` game over, `$4C`, `$5F`, and the longer `$21`,
`$3A`, `$3E`, `$46` (ends with a ritardando), `$47` (204 s, the longest).

Channel use: FM 1-4 + ADPCM-A 1-3 + ADPCM-B is the norm (the four measured stage songs and 15 others): the music
leaves ADPCM-A 4-6 to the sound effects. Sixteen use ADPCM-A 4, 5 or 6 too (`$21`, `$22`, `$24` (= `$34`, `$40`),
`$25`, `$2A`, `$3B`, `$3D`, `$3E`, `$3F`, `$41`-`$43`, `$45`-`$47`, `$4B`), where the effects' priorities decide. No song uses SSG
(the driver has no SSG music channel).

## Techniques in the data

- **Echo voices by subroutine.** In 14 songs (`$23`, `$27`, `$28`, `$2D`, `$30`, `$31`, `$3A`, `$3B`, `$3D`, `$44`,
  `$46`, `$47`, `$4A`, `$4B`) FM2 and FM3 replay FM1's line, one 3-12 ticks late and the other twice as late (mostly
  6 and 12), detuned a few F-number units in opposite directions (`$B4`-`$BD`: -4 to +5) and panned to opposite sides
  (FM1 centre; `$44`: both right): FM2 and FM3 `call` **the very bytes** FM1 plays (`$47`: FM1 centre; FM2 right,
  detune -1, `call $C83A` at tick 5; FM3 left, detune +1, the same call at tick 9). The shared stream's patch changes
  carry no detune byte, so each voice keeps its own. Shorter copies: `$24`, `$2A`, `$32`, `$33`, `$37`; unison
  doubling at the same tick with detune: `$29` (FM1/FM2 -6, FM3/FM4 -2), `$2F`, `$5F`.
- **One block, inline and called.** A block ending in `$36` (return) runs inline inside a loop, then is `call`ed
  later: a return with an empty call stack does nothing (`$27` FM4 at `$935F`).
- **Panned echo on one channel**: `$27` FM4 plays each note twice, `pan 3` attenuation 1, then `pan 2` (left)
  attenuation 7, 6 ticks later.
- **Volume shapes through ties**: a note, then the same note tied with a higher attenuation: the tie rewrites the
  level only, no new attack (`$26` ADPCM-B: `A2 att 0 len 5`, `A2 att $10 len 1 tie`). Held notes are the same tie
  with the same attenuation (`A2 len 48`, `A2 len 48 tie`).
- **Staccato by gate mode** (`$3D` 4 or 5: gates of 5/8 or 6/8 of each length): `$25`, `$2A`, `$2D`, `$31`, `$32`,
  `$37`, `$3D`, `$4A`.
- **Tempo moves**: `$33` slows from TB `$C3` to `$C0` / `$C1` for a section and comes back; `$46` closes with a
  ritardando (TB `$89` → `$84` → `$82` → `$60` → `$70` → `$62`, 29 → 22 ticks/s); `$44` slows then fades out by its
  own `$3F`. Every channel carries the same `$33`, the first to reach it changes the tempo.
- **Hardware LFO** (`$4E`): `$27` (`$0A`, `$0B`), `$2A` (`$09`), `$2F` (`$08`), `$47` (`$07`), with the patches'
  AMS/PMS; the driver's software vibrato is never used (no patch sets a depth).
- **ADPCM-B** as a pitched instrument (`$46` mode 2, one sample transposed by delta-N: 30 songs) or as a drum kit
  (`$46` < `$40`, the note picks the sample: `$21`, `$25`, `$27`, `$2F`, `$30`, `$31`, `$37`, `$3D`, `$3E`, `$4A`,
  switching between the two inside a song).
- **ADPCM-A samples** come from the sound-effect tables: slot 0 (`$41EA`, 25 commands) or slot 4 (`$69A9`, 13); notes are
  sample numbers. `$2A` uses looping records (88 loop replays in its capture).
- **Octave and detune per patch change**: the modifier bytes after a patch change set the volume, an octave shift
  (`oct $82` = +1 octave) and the detune, so one patch serves several registers.

## Validation

All 40 commands captured in our emulator (Geolith core with a Z80 port tap, `tools/makoto3/capture.py`): power-on,
the game's own commands blocked from frame 880 (after its `$07`), the song sent at frame 900, captured for its pass
+ 15 % (chains: the intro + the next song's pass). The model runs on the captured interrupt order (which interrupt
was timer A, which timer B; measured), from the command on, and its register writes are compared interrupt by
interrupt (`regs.compare`).

- **32417 of 32417 interrupts with writes identical, 431287 captured writes compared, no difference in any song.**
  Left out on both sides: `$27` (timer flags, every interrupt), `$1C` (ADPCM end-flag resets) and ADPCM-B `$10` = 0
  (the end-of-sample poll writes them, timed by the samples), and the capture's last interrupt (cut by the end of
  the capture).
- Song `$2A`'s 88 ADPCM-A loop replays (start / end + key-on written by the end-of-sample poll `$03F3` when a looping
  sample ends) are each the loop region of the sample the model last keyed on that channel; their timing follows the
  sample length, which the model does not compute.
- The fade (`$44`) is validated, including the per-tick level refreshes and the stop it ends with.
- What no song exercises is not validated: software vibrato, ADPCM-B pitch / level effects, and the opcodes listed
  without uses in `ff3_sound_driver.md`.
- Playback check: `tools/songlab/build_web.py --game ff3` builds Song Lab data (`/data/tmp/ymweb/ff3/data`) and
  render.js plays both streams through the WebAssembly YM2610: over the first 20 s, `$3E` renders identical audio,
  `$26` differs by 0.1 % RMS (write spacing inside an interrupt), `$2A` loses its looped samples in the model stream
  (the replays above are not generated).
