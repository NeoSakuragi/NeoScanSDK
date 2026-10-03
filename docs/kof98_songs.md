# KOF98 songs

Every music command of The King of Fighters '98, decoded and checked against MAME. The driver (stream format,
opcodes, output stage, effects) is in `kof98_sound_driver.md`; this file is the song side: catalogue, structure,
the techniques the songs use, and the per-song validation.

Tools (tools/kof98snd): `song98.py M1 CMD --list [ticks]` prints every event of every channel (tick, stream address,
length, opcode, decoded parameters: note names, patches, volumes, pans, effects); `song98.py M1 --catalog`;
`song98.py M1 CMD --keys IRQS` prints the predicted chip events; `validate98.py M1 CMD CAPTURE` compares them with a
`ymtap.lua` capture; `testsong98.py` plays synthetic songs for the opcodes no song uses. Listings of all songs (one
full loop or to the end): `/data/tmp/snd98/songs/list_XX.txt` (85 k lines, not in the repo); captures:
`/data/tmp/snd98/cap/cap_XX.txt` (`capall.sh`, `valall.py`, `stats.py` next to them).

How to read a listing line: `  769  $B6B8  +192 note_nogate  C3 ($3C) vel $7F` = at tick 769 the event at `$B6B8`
plays C3 (FM note `$3C`, `$48` = C4 = 261.6 Hz) at velocity `$7F`, and the channel's next event comes 192 ticks
later; `note ... gate 22` with `+24` = key-off after 22 ticks; `(slur ...)` = gate > length, the next note is
slurred (no new key-on). ADPCM-A notes are sample numbers in the channel's sample table (`$0D`), ADPCM-B notes count
from the instrument's root note (`$27`, default `$3C`).

## Catalogue

Command table `$3038` type 2: `$20-$4B`, `$50-$56`; pointers `$329E` (`$20`: `$2BA2`; `$27` has none). "Use" =
seen in MAME (attract mode and one credit played with button A mashed, a snapshot 1.5 s after each command:
`/data/tmp/snd98/attract.lua`, `play.lua`, `snap/`); team names for stage themes are *(inferred)* from the demo /
arcade fights each one played in (the home team in the demo, the CPU team in arcade). Blank = not reached by those
runs (the remaining stage themes, endings, boss, game over...). Tick rates = 166.83 × tempo / 208. "Loop from tick
a/b/c" = the channels' loop points (several values = channels that start a few ticks apart, see Echo voices).

| Cmd | Use (seen in MAME) | Bank | Tempo | Ticks/s | Channels | Length / loop |
|---|---|---|---|---|---|---|
| $20 | stop: every channel "+2 end" (sent before songs, thrice at attract end) | 0 | 208 | 166.83 | FM1-4 A1-6 B | 2 ticks, ends |
| $21 | opening / attract intro (boot, every attract cycle) | 0 | 129 | 103.47 | FM1-4 A1-6 B | ends at tick 4814 (46.5 s) |
| $22 | after a coin (title, credits waiting for Start) | 0 | 129 | 103.47 | FM1-4 A1-3 A4 B | loop 768 ticks (7.4 s) from tick 1/7/13 |
| $23 | team select screen | 0 | 140 | 112.29 | FM1-4 A1-3 A4 A5 B | loop 768 ticks (6.8 s) from tick 376/385/386/391; FM1 192, FM3 192 |
| $24 | win screen (winner's quote) | 0 | 98 | 78.60 | FM1 FM2 FM3 A1-6 B | ends at tick 579 (7.4 s) |
| $25 |  | 0 | 135 | 108.28 | FM1 FM2 A1-3 A4 B | loop 768 ticks (7.1 s) from tick 277/289/290 |
| $26 | continue countdown | 0 | 93 | 74.59 | FM1-4 A1-3 A6 B | ends at tick 1250 (16.8 s) |
| $28 | how to play (CONTROLS / JOYSTICK screen) | 0 | 134 | 107.48 | FM1-4 A1-3 A5 A6 B | loop 768 ticks (7.1 s) from tick 193/199/241/337; A1 1536, A2 1536 |
| $29 |  | 0 | 107 | 85.82 | FM1-4 A1-6 B | loop 768 ticks (8.9 s) from tick 193/961/1729; FM1 192, FM2 2304, FM3 2304, A4 1612; ended: FM4 A3 A5 A6 |
| $2A |  | 0 | 128 | 102.66 | FM1-4 A1-6 B | loop 9984 ticks (97.2 s) from tick 1535/1536/1537/1538 |
| $2B |  | 0 | 100 | 80.21 | FM1 A1-6 | loop 384 ticks (4.8 s) from tick 385/391/397 |
| $2C | VS screen jingle (ADPCM-A only) | 0 | 100 | 80.21 | A1-3 | ends at tick 387 (4.8 s) |
| $2D |  | 0 | 100 | 80.21 | FM1-4 A1-3 A4 A6 B | ends at tick 1873 (23.4 s) |
| $2E |  | 0 | 120 | 96.25 | A1-3 B | ends at tick 1165 (12.1 s) |
| $2F |  | 0 | 113 | 90.63 | A1-3 | ends at tick 1537 (17.0 s) |
| $30 |  | 0 | 163 | 130.74 | FM1-4 A1-3 B | loop 12672 ticks (96.9 s) from tick 3073/3083/3089 |
| $31 | stage theme: demo Joe (Terry/Andy/Joe) vs Athena | 1 | 120 | 96.25 | FM1-4 A1-3 B | loop 4992 ticks (51.9 s) from tick 385/577/579/581 |
| $32 | stage theme: AoF team (demo Robert, Yuri; arcade vs Ryo) | 1 | 127 | 101.86 | FM1-4 A1-3 B | loop 7680 ticks (75.4 s) from tick 817/821/825 |
| $33 | stage theme: demo Clark (Ikari) vs Kyo | 1 | 155 | 124.32 | FM1-4 A1-3 B | loop 9024 ticks (72.6 s) from tick 1729 |
| $34 |  | 1 | 120 | 96.25 | FM1-4 A1-3 B | loop 4992 ticks (51.9 s) from tick 1488/1489/1497/1505 |
| $35 | stage theme: demo Chizuru (Mai/King) x2 | 1 | 93 | 74.59 | FM1-4 A1-3 B | loop 9024 ticks (121.0 s) from tick 1 |
| $36 | stage theme: demo Choi (Kim team) vs Yamazaki | 1 | 156 | 125.12 | FM1-4 A1-3 B | loop 11520 ticks (92.1 s) from tick 1541/3073 |
| $37 |  | 2 | 120 | 96.25 | FM1-4 A1-3 B | loop 9408 ticks (97.7 s) from tick 1/769/771 |
| $38 |  | 2 | 117 | 93.84 | FM1-4 A1-3 B | loop 8832 ticks (94.1 s) from tick 193/577/769 |
| $39 |  | 2 | 110 | 88.23 | FM1-4 A1-3 B | loop 6912 ticks (78.3 s) from tick 24/25/26/29 |
| $3A |  | 2 | 112 | 89.83 | FM1-4 A1-3 B | loop 7296 ticks (81.2 s) from tick 1/769/772/775 |
| $3B |  | 2 | 140 | 112.29 | FM1-4 A1-3 B | loop 8064 ticks (71.8 s) from tick 1/3/7/769 |
| $3C | stage theme: demo Yamazaki (Mary/Billy) vs Robert | 2 | 97 | 77.80 | FM1-4 A1-3 B | loop 5376 ticks (69.1 s) from tick 961/970/973/1153 |
| $3D | stage theme: demo Mary (Billy/Yamazaki) vs Leona | 3 | 83 | 66.57 | FM1-4 A1-3 B | loop 7104 ticks (106.7 s) from tick 49/53 |
| $3E |  | 3 | 127 | 101.86 | FM1-4 A1-3 A4 A5 B | loop 7680 ticks (75.4 s) from tick 1921/1929/1937; ended: A4 |
| $3F |  | 3 | 120 | 96.25 | FM1-4 A1-3 B | loop 7680 ticks (79.8 s) from tick 73/1417/1425/1609 |
| $40 |  | 3 | 153 | 122.72 | FM1-4 A1-3 B | loop 8832 ticks (72.0 s) from tick 1225 |
| $41 |  | 3 | 110 | 88.23 | FM1-4 A1-3 B | loop 6528 ticks (74.0 s) from tick 1/97 |
| $42 |  | 3 | 136 | 109.08 | FM1-4 A1-3 B | loop 6336 ticks (58.1 s) from tick 1537/1736/1741/2497 |
| $43 |  | 3 | 84 | 67.37 | FM1-4 A1-3 B | loop 5376 ticks (79.8 s) from tick 1/4/5/7 |
| $44 |  | 4 | 97 | 77.80 | FM1-4 A1-3 B | loop 6336 ticks (81.4 s) from tick 2881/2887 |
| $45 |  | 4 | 100 | 80.21 | FM1-4 A1-3 B | loop 6720 ticks (83.8 s) from tick 1/9/769 |
| $46 |  | 4 | 142 | 113.89 | FM1-4 A1-3 B | loop 6528 ticks (57.3 s) from tick 1585/1593/1597 |
| $47 |  | 4 | 80 | 64.17 | FM1-4 A1-3 B | loop 5376 ticks (83.8 s) from tick 1537 |
| $48 |  | 5 | 120 | 96.25 | FM1-4 A1-3 B | loop 7680 ticks (79.8 s) from tick 1 |
| $49 |  | 5 | 98 | 78.60 | FM1 FM2 FM3 A1-6 B | ends at tick 387 (4.9 s) |
| $4A |  | 5 | 100 | 80.21 | FM1 FM2 A1-3 A4 B | loop 1536 ticks (19.2 s) from tick 1/6 |
| $4B | = $21 minus 3 ADPCM-A hits (A5/A6 at ticks 3597-3841) | 5 | 129 | 103.47 | FM1-4 A1-6 B | ends at tick 4814 (46.5 s) |
| $50 |  | 5 | 113 | 90.63 | B | ends at tick 1417 (15.6 s) |
| $51 | stage ambience (dark temple stage); = $2F looped, other sample | 5 | 113 | 90.63 | A1-3 | loop 1536 ticks (16.9 s) from tick 1; A2 1272 |
| $52 | stage ambience (palace/fountain stage) | 5 | 113 | 90.63 | A1-3 | loop 576 ticks (6.4 s) from tick 1/13/25 |
| $53 | stage ambience (river village stage) | 5 | 113 | 90.63 | A1-3 | loop 384 ticks (4.2 s) from tick 1; A2 768, A3 851 |
| $54 |  | 5 | 113 | 90.63 | A1 A3 | loop 384 ticks (4.2 s) from tick 1; A3 851 |
| $55 |  | 5 | 113 | 90.63 | A1-3 | loop 696 ticks (7.7 s) from tick 1; A3 703, A1 1536 |
| $56 | = $2E with the ADPCM-B note ungated | 5 | 120 | 96.25 | A1-3 B | ends at tick 1165 (12.1 s) |

Notes on the catalogue:
- Bank set 0 = the fixed 64 KB; sets 1-5 map the 2nd..6th 64 KB of the M ROM at `$8000-$FFFF` (all songs of a
  set share it).
- Menu / jingle songs (`$21-$30`, set 0) use the shared ADPCM-A channels 4-6; every stage theme (`$31-$48`) uses
  FM1-4, ADPCM-A 1-3 and ADPCM-B only, leaving ADPCM-A 4-6 to the fight effects.
- `$51-$55` (and `$2F`) are ambiences: ADPCM-A only, each channel looping on its own period (1536 / 1272, 384 /
  768 / 851, ...) so the mix never repeats exactly; `$2E`, `$52`, `$53`, `$56` hold looping samples (sample table
  7: intro, loop count `$FF`, the driver restarts the loop region at each sample end).
- One-shots (end with `$06`): `$20` (stop), `$21`/`$4B` (intro), `$24`, `$26`, `$2C`, `$2D`, `$2E`, `$2F`, `$49`,
  `$50`, `$56`. Everything else loops for ever (`$0B` goto or `$16`).
- `$29`: FM1 loops every 192 ticks, FM2/FM3 every 2304, A4 every 1612, the rest every 768; FM4, A3, A5, A6 end.

## Structure and techniques

| Cmd | FM patches | B instr. | A tables | Notes | Slurs | Bends | Pitch fx | Pan | Vol | Transp./detune | Calls | Loops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| $20 | - | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| $21 | 2 5 | 19 32 33 34 99 100 101 102 103 104 | 0 1 6 | 810 | 147 | 0 | 0 | 144 | 42 | 3 | 0 | 42 |
| $22 | 2 5 | 33 34 | 0 6 | 217 | 49 | 0 | 0 | 15 | 18 | 3 | 0 | 14 |
| $23 | 0 15 | 74 | 0 | 477 | 18 | 0 | 0 | 181 | 20 | 3 | 0 | 11 |
| $24 | 5 10 | 66 67 | 0 | 130 | 6 | 0 | 0 | 39 | 178 | 3 | 0 | 22 |
| $25 | 17 | 74 | 0 | 307 | 25 | 0 | 0 | 44 | 13 | 2 | 0 | 12 |
| $26 | 17 32 33 | 47 62 85 | 0 | 587 | 15 | 13 | 0 | 291 | 17 | 4 | 0 | 30 |
| $28 | 0 7 | 25 | 0 | 453 | 55 | 0 | 0 | 103 | 20 | 3 | 0 | 1 |
| $29 | 0 2 4 | 17 73 | 0 1 | 427 | 8 | 0 | 0 | 135 | 66 | 13 | 2 | 27 |
| $2A | 5 7 10 32 | 19 66 67 75 104 | 0 6 | 3433 | 377 | 0 | 0 | 525 | 42 | 3 | 85 | 91 |
| $2B | 5 | - | 0 | 228 | 0 | 0 | 0 | 110 | 14 | 0 | 0 | 11 |
| $2C | - | - | 1 | 3 | 0 | 0 | 0 | 3 | 6 | 0 | 0 | 0 |
| $2D | 0 2 | 32 59 | 0 | 316 | 28 | 0 | 0 | 57 | 21 | 4 | 0 | 39 |
| $2E | - | 19 | 7 | 4 | 0 | 0 | 0 | 4 | 8 | 1 | 0 | 1 |
| $2F | - | - | 1 | 4 | 0 | 0 | 0 | 3 | 6 | 0 | 0 | 0 |
| $30 | 2 5 10 11 | 33 34 | 0 1 | 2947 | 62 | 0 | 0 | 167 | 23 | 8 | 93 | 76 |
| $31 | 17 20 | 75 76 77 78 79 80 81 | 0 | 1267 | 0 | 0 | 0 | 94 | 27 | 4 | 1 | 50 |
| $32 | 0 36 37 38 39 | 18 93 94 95 97 98 | 0 1 2 3 | 1764 | 37 | 0 | 0 | 522 | 49 | 3 | 40 | 28 |
| $33 | 5 8 34 | 62 69 105 106 107 | 0 | 1623 | 84 | 0 | 16 | 77 | 22 | 16 | 0 | 137 |
| $34 | 17 21 26 | 54 55 | 0 | 2718 | 20 | 16 | 0 | 106 | 17 | 4 | 41 | 83 |
| $35 | 17 19 20 21 | 61 62 63 | 0 | 2253 | 134 | 0 | 0 | 77 | 19 | 3 | 0 | 99 |
| $36 | 2 5 8 10 | 33 61 62 63 | 0 | 1815 | 66 | 0 | 0 | 260 | 24 | 10 | 103 | 91 |
| $37 | 17 18 | 62 63 | 0 | 2302 | 307 | 0 | 0 | 111 | 21 | 3 | 87 | 107 |
| $38 | 17 22 23 | 49 50 64 | 0 | 2421 | 147 | 0 | 0 | 75 | 22 | 3 | 0 | 114 |
| $39 | 17 20 22 | 63 | 0 | 1266 | 333 | 0 | 0 | 251 | 18 | 8 | 18 | 56 |
| $3A | 5 6 7 8 | 20 21 22 23 24 25 | 0 | 2748 | 751 | 0 | 0 | 325 | 74 | 3 | 56 | 24 |
| $3B | 0 1 2 | 17 19 | 0 4 | 2141 | 269 | 0 | 0 | 111 | 174 | 25 | 52 | 155 |
| $3C | 10 14 | 66 67 | 0 | 1485 | 16 | 0 | 0 | 106 | 24 | 10 | 41 | 74 |
| $3D | 17 27 28 | 47 50 64 70 | 0 | 1871 | 83 | 0 | 0 | 106 | 20 | 8 | 0 | 23 |
| $3E | 11 17 24 | 47 48 51 52 | 0 | 2501 | 317 | 60 | 0 | 450 | 73 | 30 | 163 | 151 |
| $3F | 17 22 23 | 49 50 64 | 0 | 1252 | 94 | 0 | 0 | 15 | 16 | 4 | 0 | 66 |
| $40 | 8 10 12 13 | 61 62 63 65 | 0 | 1380 | 104 | 0 | 0 | 153 | 32 | 20 | 41 | 136 |
| $41 | 17 19 22 | 61 63 82 84 85 86 87 | 0 | 1976 | 21 | 2 | 0 | 160 | 31 | 9 | 43 | 71 |
| $42 | 0 2 9 | 17 18 26 27 28 29 30 31 32 | 0 6 | 2255 | 175 | 0 | 0 | 307 | 246 | 5 | 75 | 76 |
| $43 | 0 2 3 4 | 0 58 59 60 | 0 1 3 4 | 1377 | 91 | 0 | 0 | 137 | 314 | 11 | 55 | 120 |
| $44 | 0 2 3 30 | 17 58 59 71 72 | 0 | 1930 | 196 | 0 | 0 | 667 | 123 | 12 | 178 | 86 |
| $45 | 0 2 3 36 40 41 | 18 32 59 60 72 90 | 0 1 2 3 4 | 2027 | 144 | 0 | 0 | 326 | 684 | 7 | 28 | 66 |
| $46 | 0 14 17 23 35 | 25 75 91 92 94 | 0 1 | 2086 | 32 | 0 | 0 | 570 | 44 | 3 | 39 | 26 |
| $47 | 2 5 10 | 33 34 61 | 0 6 | 1990 | 72 | 0 | 0 | 156 | 30 | 6 | 26 | 103 |
| $48 | 17 22 28 | 50 64 | 0 6 | 1806 | 115 | 0 | 0 | 122 | 30 | 1 | 115 | 63 |
| $49 | 5 10 | 66 67 | 0 | 85 | 2 | 0 | 0 | 31 | 20 | 3 | 0 | 3 |
| $4A | 0 29 | 73 | 0 4 | 198 | 0 | 0 | 0 | 105 | 18 | 1 | 0 | 2 |
| $4B | 2 5 | 19 32 33 34 99 100 101 102 103 104 | 0 6 | 806 | 147 | 0 | 0 | 142 | 42 | 3 | 0 | 42 |
| $50 | - | 19 | - | 1 | 0 | 0 | 0 | 1 | 1 | 1 | 0 | 0 |
| $51 | - | - | 1 | 5 | 0 | 0 | 0 | 4 | 6 | 0 | 0 | 1 |
| $52 | - | - | 7 | 5 | 0 | 0 | 0 | 5 | 6 | 0 | 0 | 0 |
| $53 | - | - | 1 7 | 7 | 0 | 0 | 0 | 7 | 6 | 0 | 0 | 0 |
| $54 | - | - | 1 | 5 | 0 | 0 | 0 | 5 | 4 | 0 | 0 | 0 |
| $55 | - | - | 1 6 | 12 | 0 | 0 | 0 | 11 | 6 | 0 | 0 | 1 |
| $56 | - | 19 | 7 | 4 | 0 | 0 | 0 | 4 | 8 | 1 | 0 | 1 |

Columns: FM patches (`$03`, index into the 47-record table at `$34B2`), ADPCM-B instruments (`$03` on B), ADPCM-A
sample tables (`$0D` slots), then counts over the first pass (to the end of the longest loop): notes, slurs
(gate > length), pitch bends (`$05`), pitch-effect opcodes (`$12`/`$14`), pan changes (`$31-$33`), volume changes
(`$2C`/`$24`), transpose / detune / ADPCM-B mode (`$0F`, `$27`, `$2E`, `$1D`), subroutine calls (`$09`), loops
(`$07`).

Techniques, as the data shows them (listings in `/data/tmp/snd98/songs/`):
- **Scaled levels everywhere**: every channel starts `$26` (scaled mode) then `$2C` volume; note velocities are
  musical dynamics (`$64`-`$7F` typical) and `$2C` sets the mix per channel. Redundant writes are common (`$07 2`
  around one `$2C`, or `$2C` twice in a row): the songs were compiled, not hand-written *(inferred)*.
- **Echo voices**: one FM line doubled on other FM channels, delayed, detuned and panned. Song `$22`: FM2 plays the
  melody (patch 2, volume `$66`, L+R); FM3 the same an octave up 6 ticks later, panned left, F-number +6; FM4 12
  ticks later, panned right, F-number -6, volume `$5C`. The same in `$21`/`$4B`, `$43` (FM3 +4 ticks, FM4 +12,
  -6), `$45`, `$33` (FM3/FM4 6 and 12 ticks after FM2, ±6). Detune ±6 appears 76 times in the songs.
- **Slurs**: `gate = length + 1` on runs of notes (e.g. `$3A` FM1 tick 985: G#2 A2 B2 C3 D3 E3 F3 G3, `+3 gate 4`
  each): one key-on, the pitch glides by F-number writes.
- **Pan per note** on ADPCM-A: `$32`/`$33` before drum hits (3734 of the 4888 left / right pan events of the first
  passes are on ADPCM-A, 459 on ADPCM-B, 695 on FM): a stereo drum kit from mono samples.
- **Vibrato** only in `$33` (FM3/FM4: type 0 saw, depth 16 F-number units, step 5, every 2 ticks after a 2-tick
  delay, on for a few bars by `$12 $03`, off by `$12 $02`).
- **Pitch bends**: `$34` (FM1) and `$3E` (FM2-4) on FM, in a few 1-tick steps; `$26` (e.g. -8192, -5504, -2816,
  0) and `$41` bend the ADPCM-B channel, which the driver does not support (no effect on the sample, stray FM
  writes, see the driver's bugs).
- **Drum kits on ADPCM-B**: `$0F 1` (kit mode) in 17 channel set-ups: the note picks the sample record.
- **Tempo changes**: `$34` uses `$10` twice.
- **Sound effects from songs**: none (`$0C`, `$1E`, `$30` unused).

## Validation

Each song captured in MAME from power-on: the game's own commands blocked from frame 255 (after its `$07` unlock;
replaced by `$60`, see the driver's NMI note), the song command sent at frame 260, captured for one full loop (or to
the end) plus 3 s, every YM2610 write tagged with the number of the timer interrupt that ran the sequencer
(`ymtap.lua` IRQ=1). The model (`song98.py`) is run for the same number of interrupts; `validate98.py` compares, per
channel, events at the same interrupt with the same values. "a/b/c" = model / capture / matched.

- Key-ons: FM `$28` key-on writes; ADPCM-A key-ons with start, end, pan and level; ADPCM-B `$10`=`$80` with delta-N,
  start, end and volume. Key-offs: FM `$28` off, ADPCM-A dumps (every key-on dumps first, so about twice the
  key-ons), ADPCM-B `$11`=0.
- F-number: every `$A0`-`$A2` write (notes, slurs, bends, vibrato) with block and F-number.
- FM TL / pan, ADPCM-B delta-N / volume: the model's writes, found or not in the capture (the capture also has the
  patch loads and key-on preambles, which the model does not list).
- Nested IRQs dropped: timer interrupts the driver skipped because the previous ISR was still running (`q 2`).
- Offset: found by search over a few interrupts; for every song it is the interrupt count at the song command
  (`$21` shows +3 because the game's own, blocked, `$21` one frame earlier is logged first).

| Cmd | Ticks compared | Key-ons model/capture/same | Key-offs | F-num writes | FM TL (model found) | FM pan | B delta-N | B volume | Sample loop replays | Nested IRQs dropped |
|---|---|---|---|---|---|---|---|---|---|---|
| $20 | 520 | - | 6/13/0 | - | - | - | - | - | - | 0 of 559 |
| $21 | 5109 | 758/758/758 | 1184/1184/1184 | 251/251/251 | 251 of 251 | 4 of 4 | 13 of 13 | 15 of 15 | - | 45 of 8274 |
| $22 | 1087 | 247/247/247 | 349/349/349 | 142/142/142 | 142 of 142 | 4 of 4 | 12 of 12 | 12 of 12 | - | 22 of 1793 |
| $23 | 1480 | 619/619/619 | 707/707/707 | 465/465/465 | 465 of 465 | 127 of 127 | 7 of 7 | 7 of 7 | - | 38 of 2239 |
| $24 | 818 | 128/128/128 | 218/218/218 | 38/38/38 | 152 of 152 | 3 of 3 | 0 of 0 | 20 of 20 | - | 11 of 1776 |
| $25 | 1373 | 367/367/367 | 510/510/510 | 166/166/166 | 166 of 166 | 2 of 2 | 0 of 0 | 0 of 0 | - | 33 of 2155 |
| $26 | 1462 | 578/578/578 | 740/740/740 | 409/409/409 | 409 of 409 | 162 of 162 | 0 of 0 | 0 of 0 | - | 42 of 3310 |
| $28 | 2078 | 462/462/462 | 749/749/749 | 183/183/183 | 183 of 183 | 4 of 4 | 12 of 12 | 12 of 12 | - | 49 of 3265 |
| $29 | 2997 | 443/443/443 | 698/698/698 | 175/175/175 | 185 of 185 | 12 of 12 | 2 of 2 | 4 of 4 | - | 29 of 5865 |
| $2A | 11742 | 3142/3142/3142 | 4969/4969/4969 | 1376/1376/1376 | 1389 of 1389 | 4 of 4 | 89 of 89 | 97 of 97 | - | 180 of 19120 |
| $2B | 1015 | 325/325/325 | 635/635/635 | 9/9/9 | 9 of 9 | 1 of 1 | - | - | - | 31 of 2151 |
| $2C | 636 | 3/3/3 | 9/9/9 | - | - | - | - | - | - | 0 of 1362 |
| $2D | 2108 | 288/288/288 | 482/482/482 | 106/106/106 | 106 of 106 | 4 of 4 | 7 of 7 | 8 of 8 | - | 28 of 4425 |
| $2E | 1464 | 4/4/4 | 10/10/10 | - | - | - | 0 of 0 | 0 of 0 | 48 | 0 of 2577 |
| $2F | 1818 | 4/4/4 | 11/11/11 | - | - | - | - | - | - | 0 of 3386 |
| $30 | 15946 | 2929/2929/2929 | 4078/4078/4078 | 1672/1672/1672 | 1674 of 1674 | 6 of 6 | 29 of 29 | 29 of 29 | - | 282 of 20388 |
| $31 | 5816 | 1301/1301/1301 | 1861/1861/1861 | 569/569/569 | 569 of 569 | 3 of 3 | 0 of 0 | 0 of 0 | - | 97 of 10121 |
| $32 | 8754 | 1772/1772/1772 | 2822/2822/2822 | 552/552/552 | 560 of 560 | 15 of 15 | 30 of 30 | 40 of 40 | - | 112 of 14377 |
| $33 | 10999 | 1565/1565/1565 | 2363/2363/2363 | 2107/2107/2107 | 715 of 715 | 4 of 4 | 13 of 13 | 19 of 19 | - | 189 of 14799 |
| $34 | 6217 | 2641/2641/2641 | 3474/3474/3474 | 1513/1513/1513 | 1497 of 1497 | 11 of 11 | 10 of 10 | 10 of 10 | - | 253 of 11566 |
| $35 | 9170 | 2152/2152/2152 | 3250/3250/3250 | 991/991/991 | 999 of 999 | 10 of 10 | 58 of 58 | 60 of 60 | - | 193 of 20550 |
| $36 | 14840 | 1818/1818/1818 | 2820/2820/2820 | 587/587/587 | 591 of 591 | 6 of 6 | 35 of 35 | 35 of 35 | - | 190 of 19826 |
| $37 | 10397 | 2037/2037/2037 | 3298/3298/3298 | 952/952/952 | 955 of 955 | 4 of 4 | 44 of 44 | 44 of 44 | - | 141 of 18061 |
| $38 | 9797 | 2314/2314/2314 | 3598/3598/3598 | 881/881/881 | 891 of 891 | 11 of 11 | 104 of 104 | 108 of 108 | - | 170 of 17457 |
| $39 | 7399 | 969/969/969 | 1286/1286/1286 | 742/742/742 | 744 of 744 | 3 of 3 | 157 of 157 | 157 of 157 | - | 25 of 14030 |
| $3A | 8302 | 2046/2046/2046 | 2965/2965/2965 | 1576/1576/1576 | 1592 of 1592 | 4 of 4 | 0 of 0 | 28 of 28 | - | 87 of 15458 |
| $3B | 9153 | 1928/1928/1928 | 2550/2550/2550 | 1487/1487/1487 | 1634 of 1634 | 15 of 15 | 38 of 38 | 38 of 38 | - | 45 of 13638 |
| $3C | 6720 | 1512/1512/1512 | 2193/2193/2193 | 671/671/671 | 671 of 671 | 3 of 3 | 4 of 4 | 4 of 4 | - | 110 of 14450 |
| $3D | 7307 | 1830/1830/1830 | 2909/2909/2909 | 665/665/665 | 665 of 665 | 8 of 8 | 41 of 41 | 44 of 44 | - | 142 of 18353 |
| $3E | 9765 | 2305/2305/2305 | 3635/3635/3635 | 1135/1135/1135 | 1075 of 1075 | 166 of 166 | 10 of 10 | 19 of 19 | - | 277 of 16033 |
| $3F | 9568 | 1190/1190/1190 | 1475/1475/1475 | 761/761/761 | 761 of 761 | 8 of 8 | 0 of 0 | 0 of 0 | - | 36 of 16624 |
| $40 | 10348 | 1325/1325/1325 | 2009/2009/2009 | 618/618/618 | 624 of 624 | 7 of 7 | 15 of 15 | 29 of 29 | - | 122 of 14108 |
| $41 | 6839 | 2003/2003/2003 | 2928/2928/2928 | 892/892/892 | 892 of 892 | 10 of 10 | 21 of 21 | 21 of 21 | - | 113 of 12972 |
| $42 | 9072 | 2149/2149/2149 | 3015/3015/3015 | 1296/1296/1296 | 1300 of 1300 | 86 of 86 | 40 of 40 | 232 of 232 | - | 151 of 13914 |
| $43 | 6339 | 1351/1351/1351 | 2196/2196/2196 | 516/516/516 | 722 of 722 | 9 of 9 | 19 of 19 | 56 of 56 | - | 38 of 15737 |
| $44 | 9381 | 1791/1791/1791 | 2650/2650/2650 | 928/928/928 | 991 of 991 | 43 of 43 | 79 of 79 | 81 of 81 | - | 178 of 20156 |
| $45 | 7700 | 2085/2085/2085 | 2516/2516/2516 | 1499/1499/1499 | 1977 of 1977 | 46 of 46 | 7 of 7 | 168 of 168 | - | 78 of 16056 |
| $46 | 8385 | 2129/2129/2129 | 3063/3063/3063 | 885/885/885 | 901 of 901 | 107 of 107 | 12 of 12 | 17 of 17 | - | 138 of 12322 |
| $47 | 7026 | 1961/1961/1961 | 2908/2908/2908 | 845/845/845 | 855 of 855 | 9 of 9 | 27 of 27 | 27 of 27 | - | 223 of 18307 |
| $48 | 7899 | 1713/1713/1713 | 2564/2564/2564 | 710/710/710 | 718 of 718 | 11 of 11 | 3 of 3 | 5 of 5 | - | 138 of 13732 |
| $49 | 627 | 83/83/83 | 147/147/147 | 23/23/23 | 23 of 23 | 3 of 3 | 0 of 0 | 0 of 0 | - | 7 of 1371 |
| $4A | 1785 | 235/235/235 | 418/418/418 | 33/33/33 | 33 of 33 | 8 of 8 | 0 of 0 | 0 of 0 | - | 11 of 3753 |
| $4B | 5107 | 754/754/754 | 1176/1176/1176 | 251/251/251 | 251 of 251 | 4 of 4 | 13 of 13 | 15 of 15 | - | 45 of 8274 |
| $50 | 1698 | 1/1/1 | 1/1/1 | - | - | - | 0 of 0 | 0 of 0 | - | 0 of 3166 |
| $51 | 1818 | 6/6/6 | 10/10/10 | - | - | - | - | - | - | 0 of 3386 |
| $52 | 882 | 6/6/6 | 9/9/9 | - | - | - | - | - | 22 | 0 of 1664 |
| $53 | 1164 | 9/9/9 | 15/15/15 | - | - | - | - | - | 10 | 0 of 2182 |
| $54 | 1164 | 7/7/7 | 12/12/12 | - | - | - | - | - | - | 0 of 2182 |
| $55 | 1818 | 15/15/15 | 27/27/27 | - | - | - | - | - | - | 0 of 3386 |
| $56 | 1464 | 4/4/4 | 10/10/10 | - | - | - | 0 of 0 | 0 of 0 | 48 | 0 of 2577 |


`$20` (stop) has no notes to align on; its writes are the song start's silencing and the end dumps. Totals over
`$21-$56`: **55304/55304/55304 key-ons, 81522/81522/81522 key-offs, 28677/28677/28677 F-number writes**, FM TL
28337 of 28337, FM pan 947 of 947, ADPCM-B delta-N 951 of 951, volume 1461 of 1461, 128 loop replays (`$2E`,
`$52`, `$53`, `$56`: the slot-7 restarts every sample length, e.g. 121 interrupts = 0.725 s for sample `$1D` of
`$2E`, 6656 bytes = 0.72 s at 18.5 kHz).

Synthetic test songs (`testsong98.py`, written into the free ROM area `$2C56-$2DFF` and played as command `$27`):

| Test | Checks | Result |
|---|---|---|
| `fxtypes` | pitch effect types 1-6 (square, triangle, pseudo-random, one-shot saw, one-shot hump, table), delay, negative depth, switch off; effects running on after the end | 8/8 key-ons, 1692/1692/1692 F-number writes |
| `fm2` | level effect on FM (TL rewritten unchanged), `$2D`, `$11`, `$28` (port B), `$05` + `$23`, `$2E`, `$1D`, direct mode with `$24` / `$25` / `$0F` | 11/11/11 key-ons, 11 F-numbers, 17 TLs, all at the same interrupt |
| `flow` | `$0C` (tick abort: FM4 one tick late), `$34` inline patch, tie into the same / another note, `$0E`, a note without length, rests | 12 key-ons, 13 F-numbers, all matched |
| `adpcmb` | B pitch effect (triangle on delta-N) and level effect (table on `$1B`), kit and split modes, `$27`, `$29`, `$05` on B | 6/6/6 key-ons, 1803 delta-N and 901 volume writes matched |

What is not covered: names of the songs the attract mode and one credit did not reach; the effects-sequencer group
and the type-4 ADPCM-B effects (no data in KOF98).
