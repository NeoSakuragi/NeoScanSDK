# KOF99 animation dictionary

Gallery artifact: https://claude.ai/artifact/Y4g7uTUi1tCiNWBbmY2ZEK · data: `/data/neogeo_dict/` (`exports/kof99`,
`sites/kof99`, `captures/kof96/specials_kof99` + `throws_kof99`, `captures/kof98/wins_kof99`, `ngsdl_sta/kof99`).

KOF99 is captured in **our emulator** (`emu/neogeo_sdl --capture`, headless), like KOF96 and KOF98 since 2026-10-04,
through `tools/kof96/capture/emu.py` (RAM addresses, states). Re-captured 2026-10-04 with the recorder's `INPUT_LAG=1`
(the first captures read each input a frame earlier; old set in `/data/neogeo_dict/captures_ngsdl_lag0_old/`). ROM `/data/roms/kof99.neo` (P 9 MB, C 64 MB) is already
decrypted (SMA program scramble and CMC42 sprite encryption undone).

    python3 tools/kof96/capture/specials96.py --game kof99 --passes main,max,sdm,close ID...
    GAME=kof99 python3 tools/kof96/capture/throws96.py ID...
    GAME=kof99 python3 tools/kof98/capture/wins98.py ID...
    GAME=kof99 python3 tools/kof96/capture/labels.py
    python3 tools/kof96/export96.py --game kof99 OUT all && python3 tools/kof95/gallery.py --split OUT site/index.html

## KOF98's engine, reworked game
Same: animation engine ($4474), frames bank 1 `$200002[id]`, sprite definitions bank 1 `$240000[id]`, animations bank 2
`$200002[id]`, the 11 sprite formats, the recogniser (`$123E6`, KOF98's 12 step types), the throw routines (`$20302`,
lists read from bank 0, `turn` bit), object layout, most game states (checked in our emulator: jumps, crouch, run 45-47,
backstep 48-50, normals 80-115, C+D 116, hits, sweep 307->309->313->328->72, air hit 283->308->279).
Different:
- banks selected through the SMA chip: `$2FFFF0`, value unscrambled with bitswap(5,12,10,8,6,14) into MAME's kof99
  bankoffset table (`mame/src/devices/bus/neogeo/prot_sma.cpp`); the engine's banks 0, 1 and 2 are the plain 1 MB banks
- state map `$C1BCC`; walk `$B51C4`, jump (vy, gravity) `$B524C`, hop `vy -= vy >> 2` at `$E578` (jumps, hop normals 120-123
  as KOF98: KOF96 README, Jumps); command lists `$BA866 + id*8` (no EX lists)
- **palettes**: palette n at `$2D77F0 + n*32` (as KOF98), body n = `$100 + id*$20 + $10*set` — **two colour sets**
  (selecting with B gives set 2) — effects n = `$520 + id*$10`. Measured from palette RAM (bank 1) in our emulator.
- C+D blowback starts in 285 (KOF98 283); **three win poses** (A 336, B 338, C 340; holding D picks one of them)
- **throw victim states re-used with other meanings** than KOF98 (432 launched here, grabbed in 98):
  `tools/kof96/victim_poses99.json` names them by Terry's FRAME numbers (shared with KOF96/98) + 16 new frames
- power stocks: object +$15F (the fill reaches 2 stocks); SDMs = the DM motion with two buttons in counter mode
  (A+B+C first); counter-mode tries need a 320-frame window (the move starts 40 frames late)
- RAM: team record P1 `$10A7F6` (+4..+7 the four member ids: 3 fighters + striker, +8..+B colour sets), P2 `$10A80B`;
  timer `$10A7E6`; life `+$138/+$13E/+$146/+$150` (full = 101)

## Cast (name table $BCC88)
0 K' 1 Maxima 2 Benimaru 3 Shingo 4 Terry 5 Andy 6 Joe 7 Mai 8 Ryo 9 Robert 10 Yuri 11 Takuma 12 Leona 13 Ralf 14 Clark
15 Whip 16 Athena 17 Kensou 18 Chin 19 Bao 20 King 21 Mary 22 Kasumi 23 Xiangfei 24 Kim 25 Chang 26 Choi 27 Jhun 28 Kyo
29 Kyo-1 30 Iori 31 Krizalid 32 Krizalid (2nd form) 33 Kyo-2. 34+ effects.

## Results
34 fighters, 22,100 frames (every animation), 437 specials (121 supers, 5 counter-mode SDMs), 73 throws for any victim
(4153 / 4242 frames reproduce the lists; misses: the screen clamp, list hand-overs, and two throws with physics phases —
Whip lifts the victim on the whip, Bao rides — which are replayed from the capture), 3 win poses x 34, 165 named
victim poses. Captured on K' vs Shingo (state `vs`, victim = Shingo).
Open: most counter-mode SDMs share their DM's state path inside the window, so only 5 are listed separately.
