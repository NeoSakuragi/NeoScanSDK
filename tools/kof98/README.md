# KOF98 animation dictionary

Data (exports, gallery pages, save states, capture recordings): `/data/neogeo_dict/` (see its README.md);
the `capture/` recording folders here are symlinks into it.

Gallery artifact: https://claude.ai/artifact/LV1o7UFThpXTRhj3HLDaYe

KOF98 runs KOF96's engine, extended. The code is shared, not copied: `tools/kof96/rom96.py` describes both games
(`GAMES`), and `export96.py --game kof98`, `capture/specials96.py --game kof98`, `GAME=kof98 capture/throws96.py`,
`GAME=kof98 capture/labels.py` do the KOF98 work. Read `tools/kof96/README.md` first; this file lists the differences.
ROM `/data/roms/kof98.neo` (P = 2 MB P1 + 4 MB P2, identical to what MAME's CPU sees after its kof98 decryption).
Captured in our emulator (`tools/kof96/capture/emu.py`, see the KOF96 README); save states in
`/data/neogeo_dict/ngsdl_sta/kof98/` (`vs` = Kyo vs Yuri, `boot_ngsdl.py kof98 --save 1593`; `c<id>` / `c<id>x` per fighter).

    python3 tools/kof96/export96.py --game kof98 OUT all
    python3 tools/kof95/gallery.py OUT site/index.html

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
Captures reload `c<id>` before every try (`tools/kof96/capture/specials96.prep`, KOF98's timeline in `emu.GAMES`: swap, then 3 power stocks earned in play; poking the
stock bytes did not enable supers). Passes: main (ground + air), MAX (A+B+C, then each command that gave a super: SDMs),
close range (P2 next to P1), EX (`c<id>x`, team record EX bit). A super = a try that spends a stock. Result: 590 moves
incl. 206 supers, 59 MAX SDMs, 10 EX-only (Omega Rugal, Orochi team...). EX versions play their own moves in states
480-511 and stand in state 79, not 0 (`specials96.special_state`, `END_EX98`; until 2026-10-04 `specials96.load` only
took states below 256, so EX Terry's / Ryo's / Robert's travelling 236 projectiles were not loaded). The close pass found nothing new by first
state: a command grab starts in the same state whether it connects or whiffs.

## Throws
81 throws, every fighter. 5189 / 5219 frames reproduce the lists exactly; the rest: the screen clamp (victims carried
behind a thrower at x ~ 400 follow the camera, 8 px per frame), Chris after his release, Kim's list hand-over frame.
Victim facing: KOF98 uses the 'turn' bit per entry (KOF96 keeps the victim facing the thrower).
`tools/kof96/victim_poses98.json`: posture + angle for all 148 list poses.

## Projectiles (2026-10-04; `../kof96/capture/projectiles.py` + `../kof96/projectiles96.py`)
Decoded on Terry (Power Wave $42A9A, EX Power Wave $4396E), measured on every brawler roster fighter and the EX
Terry / Ryo / Robert in our emulator with the object pool dumped every frame (RAMDUMP). Inferences are marked.
- **Pool**: objects $100100 + n*$200. Alloc `$3434` (pops a free slot, links it into the run list by priority, clears
  +$10..+$1FF); free `$34A8` (unlinks, writes $FFFF to +$06; nothing else is cleared, so a dead projectile keeps its last
  fields: what the old captures saw as "finished objects lingering"). Alive = +$06 != $FFFF.
- **Spawn**: the thrower's move code sets its states (+$D2 its own, +$D4 the projectile's, +$D8 the projectile's end),
  the speed +$50 (16.16, negated facing left: Terry 236A/C 2.5/5, EX 236A/C 4/7) and, on the step whose flags carry
  $0080 (object +$7D bit 7, the animation's event bit), calls the spawner `$24944` (a0 = the projectile's routine, d2 =
  table = the thrower's id, d3 = state, d5/d6 = offset): owner +$84 = the thrower, table +$70, state +$72, facing +$31,
  x/y from the thrower plus the offset (+$D2/+$D4), the thrower's hit kind +$1B8 and other fields copied, +$AE = `$1B2C4`
  (the hit dispatcher). **Identity** = owner +$84, table +$70, state +$72, kind +$F5 (set by the routine: 1 = a travelling
  projectile, 3 = an eruption in front of the thrower) - never the pool slot (it depends on the free-slot order).
- **Animation and boxes**: the projectile's own state animation on the thrower's table (EX Terry 482 flight loop, 483
  end; Ryo's Haoh Shoukou Ken 170 / 171; Terry's Round-Wave-like 236 eruption 163, hold). Its attack box is box slot 0
  (+$90: type x y w h, live while +$7C bit 0); its own box is slot 1 (+$95, ROM key '31'): what another projectile's
  attack meets. One collision pass `$3A1A` for every object: attackers (registered by `$39F0`) against victims (`$3A08`),
  teams +$170, box type masks from `$3C54`; a hit clears the attacker's slot bit (`$3B1C`): **one hit**.
- **Motion**: a travelling one adds +$50 to x every frame (`$4396E`), animation looping; an eruption moves until its own
  event step, then stands (`$42BD2` -> `$42BEA`). Measured: 4 or 7 px/frame for A / C (Ryo's / Robert's 6426C 16 / 7).
- **Death**: its animation ends (+$7C bit 7: eruptions, end animations) or it leaves the screen: `$180B6` x - camera
  ($10B084) <= -64 or >= 384 (the same routine in KOF96 `$129B0` / camera $10B07E and KOF99 `$1328C` / $10B038); a
  travelling one ends on its hit: hit handler +$19C (EX Terry `$439B6`) plays its end state in place, then frees it.
  An eruption plays on after its hit with its attack spent.
- **Hit**: victim hit-stop 11 frames (KOF96 10), the thrower and the projectile do not freeze (travelling: end animation
  at once). Hits measured with P2 standing 60 / 120 / 200 px ahead: always 1 per projectile (Billy's 23624 super: 6).
- **Thrower**: the flying routine never reads its owner: hit out of its recovery, the projectile flies on (measured: Ryo
  hit at frame 24 while his Ko-ou-ken went on and hit Yuri at 27); the thrower is back in control while it flies (Ryo
  idle at frame 106, his Haoh Shoukou Ken alive until 122). One at a time: the projectile sets the owner's +$E1 bit 5
  every frame (`$24A7C`), its death clears it (`$24A5E`); the move dispatcher skips the command while it is set (`$1F262`).
- **Clashes** (measured, c6x vs Yuri): EX Ryo's Ko-ou-ken (kind 1) met Yuri's Ko-ou-ken eruption: Ryo's played its end,
  Yuri's eruption lost its attack bit and hit nobody; two eruptions (Ryo 236C, Yuri 236A) pass through each other and
  both hit. (Inference: the projectile-against-projectile case is the attacker-is-a-projectile path `$3E50`-`$3ECE`,
  victim box types 12-15.)
- **Several objects**: a move can spawn more than one projectile from the thrower (KOF96 Geese's 236C Double Reppuken:
  eruptions 130 and 131, 24 frames and 30 px apart, each hits once), and a projectile can spawn objects of its own (owner
  +$84 = the projectile, its table): trails without boxes (KOF96 Krauser's Blitz Ball 133 on its frames 0, 1, then every
  6; Iori's Yami Barai 156 on 11, then every 12; both 7 px behind it, i.e. where it was the frame before). Objects on
  table 0 / state 0 owned by projectiles carry no animation (left out). K''s KOF99 236A/C Eins Trigger is one object
  (states 132/133 then 252) standing at the hand: its frames are drawn up to ~110 px ahead (sprite offsets -34 to -106),
  its box reaches ~80 px. `projectiles96.definitions` returns every projectile of a move with its child.
- **KOF96 / KOF99**: the same object kinds and rules measured (Krauser's Blitz Ball kind 1 4 / 7 px, ends on its hit; K''s
  23624 kind 1; Geese's / Mr. Big's 236 eruptions kind 3); their spawner and hit handlers are not decoded (inference: the
  KOF96 engine, the off-screen routine is byte-identical).

Projectile specials (normal = no stock spent; px/frame; life in free flight, frames; hits at 60/120/200 px):
| fighter | move | kind | speed | life / death | hits |
|---|---|---|---|---|---|
| Terry | 236A / 236C eruption | 3 | 2.5 / 5 then 0 | 25 / anim | 1,1,0 / 1,1,1 |
| Terry EX | EX 236A / EX 236C Power Wave | 1 | 4 / 7 | 71 / 41 off screen | 1,1,1 |
| Ryo | 236A / 236C Ko-ou-ken (short) | 3 | 2.5 / 5 then 0 | 33 / anim | 1,1,0 |
| Ryo EX | EX 236A / EX 236C Ko-ou-ken | 1 | 4 / 7 | 70 / 40 off screen | 1,1,1 |
| Robert | 236A / 236C Ryuu Geki Ken (short) | 3 | 0 (stands) | 44 / 56 anim | 1,1,0 |
| Robert EX | EX 236A / EX 236C | 1 | 4 / 7 | 71 / 41 off screen | 1,1,1 |
| Iori | 236A / 236C Yami Barai | 1 | 4 / 7 | 76 / 43 off screen | 1,1,1 |
| Mai | 236A / 236C Kachousen | 1 | 4 / 7 | 79 / 45 off screen | 1,1,1 |
| Mai | 214A / 214C, 623D (flames) | 3 | 0 | 32, 31 / anim | 1,1,0; 1,0,0 |
Supers with projectiles (not picked): Ryo / Robert 6426 Haoh Shoukou Ken (kind 1, 4 / 16 and 4 / 7 px), Terry 21416
(eruption), Kyo 21426 / 236236, Mai 236236, Billy 23624 (6 hits), Iori 21426. None: Ralf, Yamazaki (214A's object
never hits), Yashiro, Billy and Kyo (normal moves). KOF96 Geese 236A/C eruption (kind 3, 17 frames), Mr. Big 236A/C
eruption (kind 3, 36), Krauser 214A-D Blitz Ball (kind 1, 4 / 7 px, A/C high y 88, B/D low y 40); KOF99 K' 236A/C
eruption (kind 3, 31), 23624 (kind 1, super).
