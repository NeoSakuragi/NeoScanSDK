# KOF98 animation dictionary

Data (exports, gallery pages, MAME save states, capture recordings): `/data/neogeo_dict/` (see its README.md);
the `capture/` recording folders here are symlinks into it.

Gallery artifact: https://claude.ai/artifact/LV1o7UFThpXTRhj3HLDaYe

KOF98 runs KOF96's engine, extended. The code is shared, not copied: `tools/kof96/rom96.py` describes both games
(`GAMES`), and `export96.py --game kof98`, `capture/specials96.py --game kof98`, `GAME=kof98 capture/throws96.py`,
`GAME=kof98 capture/labels.py` do the KOF98 work. Read `tools/kof96/README.md` first; this file lists the differences.
ROM `/data/roms/kof98.neo` (P = 2 MB P1 + 4 MB P2, identical to what MAME's CPU sees after its kof98 decryption).
MAME set `~/Downloads/kof98.zip`; save states in `~/.mame/sta/kof98/` (`vs` = Kyo vs Yuri, `c<id>` / `c<id>x` per fighter).
**Always `-noplugin cart_bridge`** (see the KOF96 README).

    python3 tools/kof96/export96.py --game kof98 OUT all
    python3 tools/kof95/gallery.py --split OUT site/index.html

## Cast (38)
0 Kyo 1 Benimaru 2 Daimon 3 Terry 4 Andy 5 Joe 6 Ryo 7 Robert 8 Yuri 9 Leona 10 Ralf 11 Clark 12 Athena 13 Kensou
14 Chin 15 Chizuru 16 Mai 17 King 18 Kim 19 Chang 20 Choi 21 Yashiro 22 Shermie 23 Chris 24 Yamazaki 25 Mary 26 Billy
27 Iori 28 Mature 29 Vice 30 Heidern 31 Takuma 32 Saisyu 33 Heavy D! 34 Lucky 35 Brian 36 Rugal 37 Shingo.
38-40 effect / stage tables. The Orochi forms of 21-23 and Omega Rugal are the EX versions of those ids.

## Engine differences from KOF96
| What | KOF98 | KOF96 |
|---|---|---|
| banks | P2 = 4 x 1 MB; bank 0 throw lists, 1 frames + sprite defs, 2 animations + palettes (default) | 2 banks |
| animation engine | `$5BB0` (same code), state map `$5DA2` | `$4D50`, `$4F24` |
| state -> slot | one map per fighter: `$B9536 + id*4` -> words | one shared map |
| animations | bank 2 `$200002 + id*4` | `$080000` |
| frames / sprite defs | bank 1 `$200002[id]` / `$240000[id]`, same 11 formats | bank 0 |
| palettes | bank 2 `$2D77F0 + n*32`; body n = `$100 + id*$40 + $10*set + k` (4 colour sets = the button A-D pressed at character select, team record +7..9 = 0-3; checked in MAME for sets 2 and 3; the gallery shows all four), effects n = `$B80 + id*$10 + k`; sprite palette byte 16+k body, 32+k effects | 2 sets, one block |
| physics | walk `$ABFC8 + id*4`, jump vy/gravity `$AC060 + id*8` (copied per fighter by `$1683A`); hop = `vy -= vy >> 2` at `$13E2A` (no table; KOF96 README, Jumps) | `$6E8EE`, `$6E96E`, hop `$EF24` |
| recogniser | `$1720E`, lists `$B14A2 + (id*2 + ex)*8`; new step types 10 (stick exact, no button) and 11 (button, stick off the value's directions) | `$11C76`, 10 types |
| throws | victim side `$25372`, thrower side `$253E6`, stage edge `$255B0`; lists read from bank 0; dy bit 7 = victim's facing ('turn') | `$1AF72`, `$1B008`, `$1B134` |
| RAM | team record P1 `$10A84A` (+4..6 ids, +7..9 colour sets, +$10 EX bits -> object +$1D6), P2 `$10A85B`; timer `$10A83A`; power stocks object +$15E | `$10A843`, `$10A836` |

## Game states (Kyo vs Yuri, all fighters)
KOF96's numbers except: hop normals 120-123 (A-D, every hop direction; KOF96's hops use the jump normals), run 45-47, backstep 48-50, roll 51-53, specials from 128,
knockdowns blowback 283 -> 287, trip 307 -> 309 -> 313 -> down 328 -> get-up 72, air hit 308 -> 279; **win poses**
(button held at the KO): A 336->337, B 338->339, C 340->341, D 342->343 (`capture/wins98.py`, same for all 38).
`export96.MOVES98`. Every other slot of each table is exported as `slot_<n>` with the states that select it.

## Specials, supers, MAX, EX
Captures reload `c<id>` before every try (`capture/prep98.lua`: swap, then 3 power stocks earned in play; poking the
stock bytes did not enable supers). Passes: main (ground + air), MAX (A+B+C, then each command that gave a super: SDMs),
close range (P2 next to P1), EX (`c<id>x`, team record EX bit). A super = a try that spends a stock. Result: 590 moves
incl. 206 supers, 59 MAX SDMs, 10 EX-only (Omega Rugal, Orochi team...). The close pass found nothing new by first
state: a command grab starts in the same state whether it connects or whiffs.

## Throws
81 throws, every fighter. 5189 / 5219 frames reproduce the lists exactly; the rest: the screen clamp (victims carried
behind a thrower at x ~ 400 follow the camera, 8 px per frame), Chris after his release, Kim's list hand-over frame.
Victim facing: KOF98 uses the 'turn' bit per entry (KOF96 keeps the victim facing the thrower).
`tools/kof96/victim_poses98.json`: posture + angle for all 148 list poses.
