# Kizuna Encounter songs

The 23 music commands (type 2 in the command table `$2E6C`) of Kizuna Encounter: Super Tag Battle, as SNK's
"Sound Driver Ver 0.0" plays them (docs/kizuna_sound_driver.md). Command `$20` is the all-off header (the game sends it
to stop the music between screens).

Names are the screen the game sent the command on, measured in our emulator (attract mode over 60 000 frames, and a
credit played: coin, how to play, tag team select, one fight lost, continue, game over; screenshots in
`/data/neogeo_dict/sound/kizuna/attract`). The attract demos play only `$21-$24`; the stage songs are named by the
stage on screen, not by character: **no stage belongs to a fighter** except the two boss stages (code read
2026-10-11, below); the soundtrack's titles (SNK's own CD, PCCB-00236 / SNK Arcade Sound Digital Collection Vol.26)
name the stages by place, given in the table. `?` = not reached in
those runs. Songs `$37` / `$3A` and `$2F` / `$3B` have the same length and channel set and the same one-shot sample calls at the
same ticks; `$37` and `$2F` add the sequenced effects `$F2` / `$F3` at the end; *probably variants of the same
pieces*.

Columns: tempo = header byte (ticks/s = 166.83 × tempo / 208); channels the header enables; loop = the longest
channel loop period of the model (or "ends"); writes = captured / model writes (timer and end-flag writes excluded,
as regs98.py); identical = sequencer interrupts whose writes are identical in order and value / interrupts with writes.

| Cmd | Screen | Tempo (ticks/s) | Channels | Loop | Writes cap / model | Identical |
|---|---|---|---|---|---|---|
| `$21` | Stage 0 / 1 (dusk street, attract demo): スラム街 Slum Quarters | 115 (92.2) | FM1-4 A1-3 B | 9312 ticks | 16504 / 16504 | 1189/1189 |
| `$22` | Stage 2 / 3: the highway (高速道路料金所 Highway Tollgate, a broken elevated expressway, night / day; attract demo); the brawler's stage 2 (`STAGE_HIGHWAY`) | 102 (81.8) | FM1-4 A1-3 B | 6000 ticks | 17169 / 17169 | 900/900 |
| `$23` | Stage 6 / 7 (sunset / moonlit rooftop, attract demo): 建設中高層ビル 150階 Under Construction Skyscraper 150F | 132 (105.9) | FM1-4 A1-3 B | 8448 ticks | 21883 / 21883 | 1297/1297 |
| `$24` | Stage 4 / 5 (harbour market; the first stage of the played credit): 裏水路 Ura Suiro, Rear Waterway; the brawler's stage 3 and Kim's theme (`THEME_KIM`) | 86 (69.0) | FM1-4 A1-3 B | 5760 ticks | 16649 / 16649 | 920/920 |
| `$25` | Ranking (attract) | 120 (96.2) | FM1-4 A1-3 B | 4608 ticks | 10633 / 10633 | 580/580 |
| `$2B` | Stage 8 (temple hall): King Lion's palace (Shishioh, 獅子王, the 1P boss) | 130 (104.3) | FM1-4 A1-3 B | 8640 ticks | 36795 / 36795 | 1091/1091 |
| `$2C` | Stage 9 (bone cave): 異次元 Strange Dimension (Jyazu, the hidden last boss) | 110 (88.2) | FM1-4 A1-4 B | 11160 ticks | 14018 / 14018 | 1323/1323 |
| `$2D` | ? | 104 (83.4) | FM1-4 A1-6 B | 5376 ticks | 15150 / 15151 | 1324/1325 * |
| `$2E` | ? | 106 (85.0) | FM1-4 A1-6 B | 768 ticks | 3752 / 3752 | 230/230 |
| `$2F` | ? | 155 (124.3) | FM1-4 A1-5 B | ends | 6409 / 6409 | 433/433 |
| `$30` | ? | 80 (64.2) | FM1-4 A1-3 A5-6 B | 768 ticks | 2370 / 2370 | 214/214 |
| `$31` | ? | 108 (86.6) | FM1-4 A1-3 A6 B | 768 ticks | 1850 / 1850 | 110/110 |
| `$32` | Tag team select | 145 (116.3) | FM1-4 A1-3 B | 768 ticks | 1913 / 1913 | 153/153 |
| `$33` | ? | 175 (140.4) | FM1-4 A1-3 B | 1536 ticks | 3175 / 3175 | 263/263 |
| `$34` | ? | 105 (84.2) | FM1-4 A1-3 B | 1536 ticks | 3607 / 3607 | 321/321 |
| `$35` | ? | 145 (116.3) | FM1-4 A1-3 B | 1536 ticks | 3107 / 3107 | 241/241 |
| `$36` | Continue (sent 100 frames after `$39`, after a `$20`) | 160 (128.3) | FM1-4 A1-3 B | 768 ticks | 1364 / 1364 | 85/85 |
| `$37` | ? | 167 (133.9) | FM1-4 A1-5 B | ends | 6392 / 6392 | 411/411 |
| `$38` | ? | 155 (124.3) | FM1-4 A1-3 B | 384 ticks | 1688 / 1694 | 102/103 * |
| `$39` | Continue (its first song) | 180 (144.4) | FM1-4 A1-3 B | 1536 ticks | 2589 / 2589 | 214/214 |
| `$3A` | Title (power-on, every attract loop) | 167 (133.9) | FM1-4 A1-5 B | ends | 6359 / 6359 | 404/404 |
| `$3B` | How to play (after a coin) | 155 (124.3) | FM1-4 A1-5 B | ends | 6376 / 6376 | 426/426 |
| `$50` | Game over | 113 (90.6) | FM1-4 A1-3 A5-6 B | ends | 197 / 197 | 19/19 |

\* the one differing interrupt is the capture's last, cut in the middle of the handler.

Attract sequence (measured): `$3A` title at frame 935, fade (`$0A`), `$25` ranking, then a demo fight on `$21`, `$22`,
`$23` or `$24`, back to `$3A`. A credit: coin → `$3B` how to play, `$32` tag team select, `$24` first stage, (fight
lost) `$39` then `$36` continue, `$50` game over.

Stages (measured 2026-10-11): the stage is the word `$109658` (set at `$DF9A` from table `$DFA6`; song =
word[`$4DD18` + 2 stage] - 3, read at `$1CE28`). Forced to 0-9 in our emulator (mkvs.py's 2P boot, the word poked over
the select), each fight sent the table's song at its start: 0 / 1 `$21`, 2 / 3 `$22`, 4 / 5 `$24`, 6 / 7 `$23`,
8 `$2B`, 9 `$2C`; screenshots /data/tmp/kizuna_highway/stages/sheet.png.

Who owns a stage (code read 2026-10-11, P ROM `$DE9A`-`$E0C2`, `$EF7E`): nobody, apart from the bosses. The 1P mode
keeps a mask of the eight places played (`$6E54`, bits = location slots 0-7; slot *s* and *s* + 4 are the same place,
the two times of day: table `$DFB0` stage -> slot = 0 4 3 7 2 6 5 1, its inverse `$DFA6` slot -> stage); each fight
takes a random free slot (`$1359A` random, `$DFBA` the n-th clear bit) -> stage, and a won stage marks its place (both
times of day from the fifth fight on). The pick reads only that place mask, never a fighter (the attract demo's `$1FC0`
likewise draws four random distinct fighters of ten and, apart, a random stage of eight); the defeated fighters go to
their own mask `$090A`. With no place left the stage is 8 (King Lion's palace, the
boss Shishioh), or 9 (Jyazu's dimension) when bit 9 of `$1B2C` is set. Vs mode: a random unplayed stage of eight (`$E076`,
mask `$6E56`). So the "theme" of a regular fighter does not exist in Kizuna; songs.json's `THEME_KIM` is the harbour
song Kim was first matched with (`$24`), not a stage of his.

Voice note 20261011-155038-5d29 ("put the **Risuhiro** music from Kizuna" on the brawler's stage 3): the closest title
is 裏水路 *Ura Suiro* (u-ra-su-i-ro; the others: スラム街 Suramu-gai, 高速道路料金所 Kōsoku-dōro Ryōkinjo, 建設中高層ビル
Kensetsu-chū Kōsō Biru, and no fighter of the cast — Hayate, Eagle, Gozu, Mezu, Rosa, Kim, Joker, Chung, Gordon,
Shishioh, Jyazu — is near it), the `$24` song: the brawler's stage 3 plays `THEME_KIM` since then (no new M ROM bytes:
the song was already in it).

## Song features (song98.py census, first pass of every song)

Notes `$2A` 25 355 and `$00` 2 316; loops `$07`/`$08`, calls `$09`/`$0A`, goto `$0B`, restart `$16`; pan `$2B` 5 188
(the songs pan almost every phrase); `$0E` 545 (a no-op in this version, used as a timed wait); FM patches `$03` 476;
direct-level mode (`$25` level, `$24` octave, songs `$23`, `$2B`, `$2E`, `$31`, `$50`), the others scaled (`$26`);
detune `$2E` (echo voices, as KOF98); LFO `$11` (`$23`, `$2B`, `$2E`); one effect: ADPCM-B pitch effect type 1
(square, depth 256, speed 7: a trill) in `$34`, `$35`, `$36`. Sample effects from the stream (`$1E`): `$2F`, `$37`,
`$3A`, `$3B` (one-shots `$00`, `$CA`, `$EF` and the sequenced effects `$F2` / `$F3` on A5 / A6).

## Song Lab

`python3 tools/songlab/build_web.py --game kizuna /data/neogeo_dict/sound/songlab/all/data/kizuna` (all 23 songs,
names above), listed in `data/games.json` as "Kizuna Encounter".
