# KOF94 songs

The 28 music commands of The King of Fighters '94, whose sound driver is a build of Fatal Fury 3's "Ver 3.0 by
MAKOTO" (`ff3_sound_driver.md`; KOF94's differences in its section "KOF94's build"): catalogue, where each is heard,
structure, techniques, and the per-song validation of tools/makoto3's model against the real driver. Everything is
decoded by `tools/makoto3/song.py` from the M1 ROM; "measured" = seen in our emulator; *(inferred)* marks the rest.

    python3 tools/makoto3/song.py /data/neogeo_dict/sound/kof94/kof94_m1.bin --catalog       one line per command
    python3 tools/makoto3/song.py /data/neogeo_dict/sound/kof94/kof94_m1.bin 0x25 --list     the event listing
    python3 tools/makoto3/capture.py --game kof94 --songs /data/neogeo_dict/sound/kof94/cap  capture every song
    python3 tools/makoto3/regs.py /data/neogeo_dict/sound/kof94/kof94_m1.bin 0x25 /data/neogeo_dict/sound/kof94/cap/cap_25.txt

## Catalogue

Command map (`$6907`): music `$20-$2D`, `$30-$32`, `$34`, `$35`, `$40`, `$41`, `$50-$55`, `$5F`; SSG effect songs `$60`,
`$61`, `$6A`, `$7F`. Columns as in `ff3_songs.md`: "One pass" = music ticks to the point where the last channel
jumps back (looping songs) or to the end, seconds from the timer-B period including `$33` tempo changes; validation =
interrupts whose register writes (minus timer-flag and end-flag housekeeping) are identical in the capture and in the
model, and the number of captured writes compared.

"Heard at" comes from three runs in our emulator (screenshots and command logs in `/data/neogeo_dict/sound/kof94/`):
`attract`, `attract2`, `attract3` (power-on, no input, 11 + 11 + 25 minutes: 33 demo fights), `play1` (a credit,
button A mashed, lost the first match) and `play2` (a credit with the second player's health held at 1 by a RAM write
(`$108421`/`$108423`; the first player's at `$108221`/`$108223`), Italy team, every match won through Rugal and
the ending). Stage themes are named by the stage on screen while the song plays (the second player's home stage),
and the teams by their country as KOF94 names them. The emulator's real-time clock makes each run take other demo
fights, so a run's screenshots and its command log are always read together.

| Cmd | Header (bank) | TB (ticks/s) | Channels | One pass | End | Heard at | Validation: identical interrupts, compared writes |
|---|---|---|---|---|---|---|---|
| `$20` | `$6B08` (0) | `$B8` (48.2) | none | — | no channel on | never heard; no channel on: a silence (*inferred*) | 1 / 1, 7 |
| `$21` | `$8000` (1) | `$B9` (48.9) | FM1-4 A1-3 B | 3829 ticks, 78.3 s | loops | stage theme, Brazil (Ikari team; attract demo, measured) | 830 / 830, 14937 |
| `$22` | `$91B3` (1) | `$C3` (56.9) | FM1-4 A1-3 B | 3361 ticks, 59.0 s | loops | stage theme, England (Women Fighters; attract demo, measured) | 1163 / 1163, 16026 |
| `$23` | `$AF4F` (1) | `$B8` (48.2) | FM1-4 A1-3 B | 2884 ticks, 59.8 s | loops | stage theme, Mexico (Art of Fighting team; attract demo, arcade, measured) | 1499 / 1499, 14069 |
| `$24` | `$A396` (1) | `$B6` (46.9) | FM3 FM4 A1-3 B | 3841 ticks, 81.9 s | loops | stage theme, USA (Sports team; attract demo, arcade, measured) | 785 / 785, 16049 |
| `$25` | `$B858` (1) | `$D7` (84.7) | FM1-4 A1-3 B | 5979 ticks, 70.6 s | loops | stage theme, Italy (Fatal Fury team; attract demo, arcade, measured) | 1386 / 1386, 10386 |
| `$26` | `$C72A` (1) | `$C0` (54.3) | FM1-4 A1-3 B | 3842 ticks, 70.8 s | loops | stage theme, Japan (Kyo's team; attract demo, arcade, measured) | 1032 / 1032, 15805 |
| `$27` | `$6B73` (0) | `$AB` (40.8) | FM1-4 A1-3 B | 2905 ticks, 71.1 s | loops | stage theme, Korea (Kim's team; attract demo, arcade, measured) | 797 / 797, 12925 |
| `$28` | `$75E8` (0) | `$B2` (44.5), `$33` changes | FM1-4 A1-3 B | 4177 ticks, 75.0 s | loops | stage theme, China (Psycho Soldier team; attract demo, arcade, measured) | 1394 / 1394, 17671 |
| `$29` | `$8987` (0) | `$9F` (35.8) | FM1-4 A1-3 B | 2384 ticks, 66.6 s | loops | Rugal, first fight (measured) | 577 / 577, 7686 |
| `$2A` | `$A01A` (0) | `$C2` (56.0) | FM1-4 A1-6 B | 1826 ticks, 32.6 s | stops (`$40`) | opening for region 0 (Japan, *inferred*: 68K table `$39374`), not heard | 208 / 208, 3962 |
| `$2B` | `$A7ED` (0) | `$C2` (56.0) | FM1-4 A1-3 B | 4033 ticks, 72.0 s | loops | Rugal, second fight (red stage, after `$34`; measured) | 870 / 870, 17465 |
| `$2C` | `$CB64` (0) | `$B3` (45.1) | FM1-4 A1-3 B | 4429 ticks, 98.2 s | loops | team ending (Italy team's epilogue, measured) | 570 / 570, 13810 |
| `$2D` | `$DCD7` (0) | `$C2` (56.0) | FM1-4 A12356 B | 1561 ticks, 27.9 s | loops | after a coin (measured) | 306 / 306, 5546 |
| `$30` | `$9441` (0) | `$A8` (39.5) | FM1-4 A1-3 B | 301 ticks, 7.6 s | stops (`$40`) | after each match: the winners' quote screen (measured, won and lost matches) | 56 / 56, 854 |
| `$31` | `$966D` (0) | `$B2` (44.5) | FM1-4 A1-3 B | 625 ticks, 14.0 s | stops (`$40`) | continue countdown (measured) | 277 / 277, 3612 |
| `$32` | `$9A90` (0) | `$AD` (41.8) | A12 B | 97 ticks, 2.3 s | loops | team select / VS map screen (measured: attract and arcade) | 11 / 11, 61 |
| `$34` | `$9B3A` (0) | `$98` (33.4) | FM1-4 A1-3 B | 385 ticks, 11.5 s | loops | cutscene cue: before Rugal's second fight, Geese in the Italy ending (measured) | 183 / 183, 2609 |
| `$35` | `$9DC7` (0) | `$AD` (41.8) | FM1-4 A1-3 B | 385 ticks, 9.2 s | loops | world map between matches (beaten teams greyed; measured twice) | 159 / 159, 1927 |
| `$40` | `$B1A1` (0) | `$B9` (48.9) | FM1-4 A1236 B | 938 ticks, 19.2 s | stops (`$40`) | not heard (68K ID `$1C`, no constant reference) | 180 / 180, 3613 |
| `$41` | `$B747` (0) | `$A2` (36.9) | FM1-4 A1-6 B | 2769 ticks, 75.0 s | loops | not heard (68K IDs `$1D`, `$23`; `$23` referenced in the ending code, *inferred*) | 1116 / 1116, 16026 |
| `$50` | `$DFE8` (0) | `$C2` (56.0) | FM1-4 A1-6 B | 2018 ticks, 36.0 s | stops (`$40`) | opening for region 3 (*inferred*: table `$39374`), not heard | 216 / 216, 4080 |
| `$51` | `$E83F` (0) | `$C2` (56.0) | FM1-4 A1-6 B | 2306 ticks, 41.2 s | stops (`$40`) | opening, attract start (measured, every attract cycle; our BIOS region) | 228 / 228, 4254 |
| `$52` | `$DA7B` (1) | `$C2` (56.0) | FM1-4 A12356 B | 2330 ticks, 41.6 s | stops (`$40`) | opening on PAL hardware (*inferred*: `$38936` tests REG_LSPCMODE bit 3), not heard | 220 / 220, 4185 |
| `$53` | `$E398` (1) | `$B9` (48.9), `$33` changes | FM1-4 A1236 B | 2906 ticks, 59.9 s | stops (`$40`) | ending / Rugal's defeat, copy 1 (68K ID `$28`); not heard | 416 / 416, 7424 |
| `$54` | `$E996` (1) | `$B9` (48.9), `$33` changes | FM1-4 A1236 B | 2906 ticks, 59.9 s | stops (`$40`) | ending: Rugal's defeat, "I... impossible" (measured, Italy team) | 416 / 416, 7424 |
| `$55` | `$EF94` (1) | `$B9` (48.9), `$33` changes | FM1-4 A1236 B | 2906 ticks, 59.9 s | stops (`$40`) | ending, copy 3 (68K ID `$2A`, no constant reference); not heard | 416 / 416, 7424 |
| `$5F` | `$F15C` (0) | `$C0` (54.3) | FM1-4 | 386 ticks, 7.1 s | stops (`$40`) | NEO-GEO logo jingle at boot, started by command `$02` (measured); the same notes as FF3's `$5F` | 259 / 259, 1917 |
| all 28 | | | | | | | **15571 / 15571**, 231754 |

Order of a power-on (measured, every attract cycle): `$03` resets, `$02` under the NEO-GEO logo (= `$5F`), `$07`
(unlock) at frame 848, `$51` at 853 (the opening), `$32` for the VS map of the demo match (with SSG effects `$60` /
`$61` as the map moves), the demo's stage theme, `$0A $D0` (fade) at its end, then `$03` again. A credit: `$2D`
at the coin, `$32` at team select, the stage theme; after each match `$30` (winners' quote) then `$32` (next
opponent) or `$35` (the world map: after the fourth and the eighth match). The eight matches were the seven other teams and a mirror match against Italy (Italy stage, `$25`), in the order Japan, Mexico, China, Brazil, England, Korea, USA, Italy; `$31` for a continue. The final:
`$29` (Rugal), `$34` (cutscene), `$2B` (Rugal's second stage, red), then `$04` `$07` `$07` and the ending
`$54`, the team epilogue `$2C` and `$34` again (Geese) during it.

Shared data: `$53`, `$54` and `$55` are three copies of one song (identical event streams at `$E398`, `$E996`,
`$EF94`, bank 1): only `$54` was heard (Italy team's ending; which teams send `$53` / `$55` is not known). The
four openings `$2A`, `$50`, `$51`, `$52` (one per region / video standard by the 68K's table, *inferred*) and
the coin song `$2D` share tempo (`$C2`), the FM voicing (FM2 detune -8 left, FM3 +7 right) and ADPCM-B setup (`$46`
`$54` / `$7C`), with different lengths and notes: versions of one arrangement *(inferred)*. `$40` has the
instrumentation and channel set of the ending `$53` (19 s, stops): a short version *(inferred)*.

**Shared with Fatal Fury 3: only `$5F`**, the NEO-GEO logo jingle started by command `$02`: the same notes and
structure as FF3's `$5F`, other patch numbers (KOF94 0 / 1 = FF3 13 / 14, byte-identical patches) and volume bytes 2
higher (2 steps quieter). No other KOF94 song shares a 16-note run with any FF3 song (all channels, all songs
compared). 19 of FF3's 60 patches have a byte-identical KOF94 patch.

Channel use: FM 1-4 + ADPCM-A 1-3 + ADPCM-B in 14 of the 28 (every stage theme but USA `$24`, which has FM3 FM4 only, Rugal's two, the epilogue `$2C`, `$30`, `$31`, `$34`, `$35`). ADPCM-A
4-6 (the sound-effect channels) only in songs played outside fights: the openings, the coin song, the endings
`$40`, `$53-$55` (A6) and `$41`. No song uses SSG.

## Techniques in the data

- **Echo voices** (the FF3 technique): two channels play the same subroutine a few ticks apart, detuned in opposite
  directions and panned apart. KOF94 mostly pairs FM3 and FM4, 4 ticks apart (`$27`, `$28`, `$30`, `$31`, `$34`;
  `$30` and `$31`: detune -4 / +5, panned left / right); `$26` puts FM2 and FM3 13 and 15 ticks behind FM4 (panned right / left); `$21` FM2 / FM3 / FM4 at
  0 / +4 / +6 ticks with detune +13 / +6 / +11.
- **Unison doubling with detune** at the same tick: the openings and `$2D` (FM2 -8, FM3 +7), `$5F` (FM2 and FM4 -6).
- **Ties for held notes and volume shapes** (as FF3): hundreds per stage theme (`$23`: 1404 in 6000 ticks).
- **Tempo moves**: `$28` (China) goes from TB `$B2` to `$C3`; the ending `$53`-`$55` has a ritardando
  `$B9` → `$B6` → ... → `$A2` and back to `$B9`; FM1-4 call one shared block at tick 889.
- **Gate mode** (`$3D`): only `$28` (mode 2). **Hardware LFO** (`$4E`): only `$23` (`$00`, `$08`, `$09`). No
  patch sets a software-vibrato depth (as FF3).
- **ADPCM-B** as a pitched instrument (`$46` `$40-$7F`, 25 songs) or a drum kit (`$46` < `$40`, the note byte is
  the record number, up to `$1x`: `$24` and `$2B`); the per-octave mode is never selected.
- **ADPCM-A**: every song draws from the one table `$3E73` (also the slot-0 effect table): 158 different records,
  no looping ones (no loop replays in any capture).
- **Octave and detune per patch change**, as FF3 (`oct` bytes in 26 songs).
- **A stream without an end**: the ADPCM-B streams of `$2A`, `$50` and `$52` run on into the next song's header
  (`$A7F2`: `$69`, a byte that would hang the driver; `$E850`: `$4C`, `$41` halt; `$E39F`: `$68`); the song
  stops (`$40` on another channel) before B reaches the bad byte (`$2A`: B's next read would be 23 ticks later; `$52`'s B
  already plays `$53`'s header bytes `$00 $C9 ...` as a rest of 201 ticks, one tick before the stop). Validated: the captures stop there too.

## Validation

All 28 commands captured in our emulator (`tools/makoto3/capture.py --game kof94 --songs`): power-on, the game's own
commands blocked from frame 850 (after its `$07` at 848; its first song, `$51`, comes at 853), the song sent at
frame 900, captured for its pass + 15 %. The model runs on the captured interrupt order (timer A / timer B, measured)
from the command on and its register writes are compared interrupt by interrupt (`regs.compare`).

- **15571 of 15571 interrupts with writes identical, 231754 captured writes compared, no difference in any song**,
  on the first run of the generalized model (the KOF94 build needed table addresses, the 26-byte ADPCM-B record
  stride and the fixed ADPCM-A table, nothing else).
- Left out on both sides, as for FF3: `$27` (timer flags), `$1C` (ADPCM end-flag resets), ADPCM-B `$10` = 0, and
  the capture's last interrupt.
- Not exercised by any song (so not validated in KOF94 either): software vibrato, the ADPCM-B pitch / level effects
  (their record parameters are all 0), fades (no `$3F`; the game's `$0A` fade was not captured), chains (`$47`).
- Song Lab: `tools/songlab/build_web.py --game kof94` → `/data/neogeo_dict/sound/songlab/kof94/` (page, wasm,
  data). Rendered through the WebAssembly YM2610 by render.js, the first 20 s of `$25`, `$26`, `$51` and `$5F` give
  identical audio from both streams.
