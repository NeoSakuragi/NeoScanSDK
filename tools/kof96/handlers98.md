# KOF98 specials read from the ROM (state handlers -> primitives)

Study 2026-10-05. Code: `handlers98.py` (decoder + model + export), `capture/romspecials98.py` (traces / game vs model
in our emulator), `../brawler/romspecials_check.py` (game vs brawler, contact sheets), brawler `fighter.c prog_update`.
Proof artifacts: `/data/tmp/romspecials/out` (`summary.json`, one KOF98 | brawler sheet per special and branch).

## How KOF98 runs a special
A fighter object is a coroutine: `+$00` is the address its code resumes at each frame. The move code (Terry `$1F7xx`,
one block per fighter) matches the recogniser bits and the buttons and installs the handler with `move.l #h, $198(a4)`
(Terry 214A/C Burn Knuckle `$428BE`, 214B/D Crack Shoot `$42C12`, 236A/C Power Wave `$42A9A`, EX 236A/C `$4382A`,
623A/C Rising Tackle `$42D5E`; Ralf AAAA Vulcan Punch `$4FD46`, [4]6A/C Gatling Attack `$4FEE2`, [4]6B/D Ralf Kick
`$506A6`, [2]8A/C Kyuukouka Bakudan Punch `$500A4` (air version `$50318`), 426B/D grab `$50648`). The handler is
straight-line code: fields, a state's animation, `move.l #R, (a4)`, a frame loop at R whose conditional branches to the
fighter's yield routine (Terry `$427CC`, Ralf `$4FC54`: `jsr $5BA6` animate, `jsr $16F98` / `$1718E`, boxes `$39F0` /
`$3A08`, `jmp $600E`) end the frame; the next part starts when the loop's condition holds, in the same frame.
Button / EX variants are field values chosen at the start (`btst #4, $1A4(a4)` = A pressed, `tst.b $1D6(a4)` = EX).
The hit-stop is the engine's: on a hit it swaps the attacker's `+$00` to `$1B2C4` / `$1B37A` / `$1B388` for the frames
(11 per hit here) and resumes the handler after; nothing in the handler knows about it.

## Engine routines and fields (the catalogue)
| primitive | ROM | arguments / meaning |
|---|---|---|
| anim *state* | `move.w s, $72(a4)` (+ `move.w #-1, $78(a4)` forces a restart), `jsr $5BA6` -> engine `$5BB0` | state animation from step 0. A step shows ticks + 1 frames; the frame it starts counts as the first frame of step 0; past the last step `+$7C` bit 7 (end) is set and a hold stays; `+$7B` non-zero holds the step (slowdown) |
| set vx / vy / g / fric | `+$50` (16.16) / `+$58` / `+$5C` / `+$54` (word, 0.16) | forward + (the code negates them when facing left: `btst #0, $31(a4)`) |
| move | `move.l $50(a4), d0; add.l d0, $18(a4)` | x += vx |
| mul k | `$36A0` (d0 * d1 / 65536) on vx | Rising Tackle's friction 0.854 |
| fricmove | `$24A2A` | vx *= fric, x += vx (Gatling Attack) |
| fall | `$37E0` | height += vy, vy -= g; returns 0 landed (height 0), d1 = -1 once vy < 0 |
| nudge dx, dy | `add.w #n, $18(a4)` / `$20(a4)` | Rising Tackle starts 8 px forward |
| dec / cnt | `subq.w #1, $C2(a4)` | Rising Tackle's rise lasts at most +$C2 (12 / 32) frames |
| spawn *routine*, state, dx, dy | `lea routine, a0`, d3 state, d5 / d6 offset (d5 < 0 = forward), `jsr $24944` | object: owner +$84, table, facing, x / y copied, offset to +$D2 / +$D4 (the routine adds it); after it the thrower writes `a1`: vx `+$50`, hit routine `+$19C`, end state `+$D8` |
| follow | `$24A02` | an effect pinned to its owner + offset (Burn Knuckle's flame, state 250) |
| inflight / release | `$24A7C` / `$24A5E` | owner +$E1 bit 5: one projectile at a time |
| offscreen | `$180B6` | x - camera <= -64 or >= 384: the object frees itself |
| fxoff | `ori.b #$80, $D1(a4)` | the attached effects end (the flame tests owner `+$D1` bit 7 / `+$E2` bit 2) |
| end / free | `jmp $25182` (neutral routine `$13AA2`) / `jmp $34A8` | |
| bookkeeping (dropped by the brawler) | `$248A8` / `$24926` init, `$7A98` sound / voice, `$155F4` gauge, `$18C1C` damage-table stats (+$108 / +$EF / +$F6), `$15F2C` landing dust, `$24FE4` cancel check, `$16B26` face the opponent, `$1B03C` voice, `$33A8` random, `$1EB20` / `$3F8A` / `$1813A` super flash | |

Conditions a frame loop waits on: **end** (`tst.b $7C(a4)`, animation over), **event** (`$7D` bit 7: a step with flag
`$0080` was entered; `bclr` consumes it: the projectile spawn), **land** / **falling** (`$37E0`), **cnt** (counter
negative), **hit** (`+$E1` bit 7: this attack connected; Burn Knuckle / Ralf Kick only flag `+$E2` bit 7 then: a
cancel window, no change of motion), objects: **off** (off screen), owner's `+$D1` bit 7. Hits are not in the code:
the animation's attack box is live while the step flag `$0100` is set (the last box loaded), and an active step opens a
new hit unless the active step before it carries `$4000`.

## The studied specials as programs (button C; `python3 handlers98.py CID INPUT [ex]` prints them)
- **Burn Knuckle 214C**: vx 9, vy 2, g 0.219; anim 129, wait end; spawn flame (250, pinned); anim 131: move + fall
  until land (hit: flag only); fxoff; anim 133, wait end; end. 1 hit window.
- **Rising Tackle 623C**: vx 8, vy 11, g 0.512, nudge 8; anim 141 wait end; anim 143 loop: vx *= 0.854, move, fall
  until falling or 32 frames; vy 0; anim 144: fall until land; anim 146 wait end; end. 2 + 6 hit windows (KOF: 7 hits).
- **Power Wave 236C**: vx 5; anim 162, on its event spawn the wave (163, kind 3: moves at vx until its own event, then
  stands; dies with its animation); wait end. **EX 236C** (EX Terry, roster D): vx 7; anim 481, on its event spawn at
  +64 px (482, kind 1: inflight, move, off screen -> free; hit routine plays 483 in place); wait end.
- **Gatling Attack [4]6C** (Bruno's 1 hit, 1 hit, 2 hits): fric 0.797; anim 134 at vx 16, anim 136 at vx 12, anim 138
  at vx 4 (each part: fricmove until end), anim 140 wait end. Windows 1 + 1 + 2 (138's second active step has no `$4000`).
- **Kyuukouka Bakudan Punch [2]8C**: vx 3.5, vy 11.5, g 0.703; 142 wait end; 144 move + fall until falling; 146 wait
  end (hangs at the apex); vx 9, vy -9: 147 move + fall until land; 148 wait end; vx -2, vy 7, g 0.5625: 149 move +
  fall until land; 150 wait end.
- **Ralf Kick [4]6D**: Burn Knuckle's shape (152 / 154 hop / 156), vx 5, vy 6.5, g 0.344.

## Validation (our emulator, `capture/romspecials98.py compare`)
Game frames inside the engine's hit-stop and frames the game lost to slowdown (P1 `+$1D2` not advancing: 19 at
Bakudan Punch's landing, where its rocks spawn) are dropped. The model of each decoded program against the game:
all 7 whiffs identical on every frame (state, ROM frame, x within 1 px, height within 0.5 px: 59 + 68 + 57 + 53 + 83 +
93 + 70 frames); the hit versions identical in state, frame and height, x off only by the game's push-back (the
opponent's body stops the attacker). Spawns: Power Wave frame 18, EX frame 14, flame frame 20, positions within 1 px.

## Generality (`python3 handlers98.py --census`)
415 handlers are installed through `$198` in KOF98. With this catalogue (about 25 routines, 8 conditions) 103 decode
with nothing unknown; the rest still decode and list what they need: calls into per-character subroutines (170: to be
inlined), loops back (94: mash loops, repeated parts), states read from ROM tables (60: Vulcan Punch), effects that
watch their owner's flags (owner +$E2 / +$D1, ~90), compare / random branches (~100), 57 still stop on a test not
modelled. KOF96 and KOF99 run the same engine family (KOF98's animation engine is KOF96's byte for byte, the off-screen
routine is identical): the decoder is the same walk with each game's routine addresses (`ROUTINES`) and yield
routines; not done.

## Extended walk (TODO #69, 2026-10-05): every fighter, KOF96 / KOF99
The decoder stays one walk; what it learned:
- **Unrolled loops / ROM state tables**: a field stepped once per pass (a repeat count `subq; bne` reached after the frame
  loop ended, a state-list pointer `+$32` / `+$C2` read with `move.w (a0), $72(a4)` then `addq #2`) is concrete at
  decode time, so each pass is its own copy of the code. An op's place is (address, the loop fields, the scratch fields
  `$C2-$DF`, the call stack): the same code reached with other states / speeds is walked again (Yashiro 623A's hit
  path lands into its own state 137, not the whiff's 130). A counter decremented every frame (Rising Tackle's `+$C2`)
  stays the runtime `cnt`.
- **Inlined calls**: `jsr` into the fighter's own code (>= $30000: follow-up checks, shared parts) is walked inline with a
  return stack; `rts` returns.
- **No follow-up input**: the brawler has none, so the walk assumes a human player (`+$170` bit 7 clear: no CPU random
  follow-up), no motion recognised during the move (`+$1AC-$1AF` 0) and, past the first `move.l #R, (a4)`, no new
  press (input record `a3` / `fp` reads 0). `andi` / `ori` on an unknown byte keep the bits they fix (`+$D1` bit 7, the
  follow-up-requested flag, is cleared at the start of the move). KOF99's cancel / follow-up checks (`$1FA32`, `$1ADBE`)
  return 0; a yield behind such a check (`jsr check; beq yield`) is a yield.
- **Converging branches**: a branch on an unmodelled test whose two ways reach the same op past bookkeeping is dropped
  (`prune`: Kyo 236C's and Billy 426C's follow-up windows, `+$7C` bit 5).
- **Bookkeeping added**: KOF98 `$24FF6-$25026` (button-dependent damage tables), `$24F2C-$24F3C` (+$F6), `$250C6`
  (flags), `$24F52` (input clear).
- **KOF96 / KOF99**: `GAME_ROUTINES` / `YIELD2` per game (KOF96 animate `$4D50`, yield `$11A54` (objects `$11C16`),
  spawn `$1A7CA`, fall `$2F34`, end `$1ADE2`, voices `$10C04` / `$10CCC` / `$17316`, afterimage trail `$13AB2`; KOF99
  animate `$446A`, yield `$12092`, spawn `$1F660`, fall `$21BE`, fricmove `$1F7B4`, end `$200A8`), hit-stop PCs
  (`romspecials98.HITSTOP`: KOF96 `$14B9E-`, KOF99 `$164E0-`), captures `capture/specials` / `specials_kof99`.

Census now: 157 of KOF98's 415 handlers decode with nothing unknown (the census also counts effects watching their
owner, which export anyway). Played from the ROM in the brawler (`ROM_SPECIALS`, `ROM_GAME`): 65 of the roster's KOF
slot specials (46 KOF98, 19 KOF96; since #73 / #74 also Billy 214B, Iori 214A, K''s six (KOF99): 73; with Terry 236C / Ralf [4]6C 67 programs), each 0 frame mismatches against the game, whiff and hit
(`../brawler/romspecials_check.py`, /data/tmp/romspec69/out). Still captured scripts: Ralf AAAA (Vulcan Punch, mash
loop), EX Ryo 646A / Robert EX 646D (they place the opponent: `$25032`, a hold), Robert 426B / Billy CCCC / Iori MAX
23624D (no handler capture), Kyo 421B (`addi` on height), Kyo EX 421D / Goenitz 214C / Geese 63214A/C (frame
drift not found yet), Billy 623D (`cmp` on speed), Iori 624B (`$1603A` / `$16AC0`), Iori 623C (a state list read through `a1`),
Yamazaki 214A, Rugal 624A / 6426A/C (compares, ROM tables through `d0`), Krauser 623B/D (allocates an object itself,
`$2BB8`), every fury (supers: super
flash, stock, `cmp` / `$E4` branches).

## What did not fit primitives
- Vulcan Punch: a loop over a state table in ROM (`+$C2` points at it) re-armed by button presses (`btst` on the
  recogniser bits): needs a table op and an input condition.
- Ralf's 426B/D grab: its handler is only the whiff (207, end); the catch is the throw system (states 208-210 entered
  from the hit dispatcher with the victim's throw list): the throw tables, not a special program.
- The game's reactions stay outside: push-back between bodies, hit registration one frame after the box goes live
  (brawler: the same frame). The victim's reaction is in since 2026-10-05 (the brawler held its target in front of the
  move between hits, `carry`, and left it hanging in the air: Ralf's [2]8C): measured on P2 in the close traces, every
  hit gives the victim one of three reactions, the same again on each later hit (a juggle re-launches it):
  **258** reel (after 5 frames in place: slide vx 11.18, x 0.828 a frame), **283 / 285** blowback (2 frames, then vx
  11.375 x 0.8125 down to ~4, vy 7, gravity 0.5, falling 287: vx x 0.8125), **286** launch (2 frames, then vy 17.25,
  gravity 2.6875 x 0.871 a frame, vx 2; falling 293 at gravity 0.625; hurt box $31 0, 192, 28, 28 in 286 / 293, none
  in 283 / 285 / 287). Brawler: `fighter.c kof_react` / `kof_fall`, reactions per hit from `export_bm.ROM_REACT`
  (Rising Tackle, Bakudan Punch: 286 on every hit) or the default (the last hit knocks down). Proof
  `../brawler/romspecials_check.py` (victim x / height per frame against these traces).
- Supers / MAX: the furies since TODO #139, their MAX versions and the super flash since 2026-10-06 ("Super flash").

## Follow-ups read from the ROM (TODO #74, 2026-10-06)
Iori's 214A/C Aoi Hana (KOF98 `$70E42`) and K''s 236A/C Ein Trigger (`$38F22`) / 623C Crow Bites (`$393A0`, KOF99)
continue on more input. The decoder now models the input check itself (`FOLLOW_CHECKS`): Iori's `$710F2` (214 + A or C
latches `+$D1` bit 7; `FOLLOW_LATCH`: the handler tests the bit, `andi #$7F` clears it at each part start = `('part',)`),
KOF99's `$1ADBE` (forward + B or D this frame: d0, d1 bit 7 = D). The check becomes `('check', mask)`, the tests
`('br', 'link:<mask>', ...)`; link bit k = `FOLLOW_INPUTS` (Iori 'again' = up-forward + A+B, the slot; K' 'fA' = forward
+ A for B, 'fAB' = forward + A+B for D). Brawler: `P_CHECK` (this frame's presses of those links join `fighter_t.plink`),
`PC_LINK`, `P_PART`; `special_input` sets `spend` from the `bslink_t` inputs. Also new: `('adv',)` (the animate call on
the state already playing advances it: K' 214D's fall, KOF99 `$446A` compares +$72 / +$78), `evstep` (`tst.b +$7D`:
the current step has $0080, not consumed; Iori's event), `window` (`+$7C` bit 5 = step flag $2000: K''s follow-up
window), `jmp (a0)` after `move.l X, (a4)` = X in the same frame (Iori's part switch through +$36, now part of the
walk's place key), the KOF99 object yield `$12366` (K''s projectiles: the blocker of all six of his slots).
Brute force in our emulator (`../brawler/followups_proof.py` part A, 184 runs): the handler reads a press 4 (KOF98) / 5
(KOF99) game ticks after its button (`FOLLOW_LAG`), on exactly the frames it calls the check: Iori presses 3..19 of part
1 (switch at its event step, frame 9, or at a later press + 4, or at its end 23), 11..27 for part 3 after a press at 5;
K' 236C presses 7..21 (the $2000 steps 11..25 + 1: the check reads the step flags of the frame before; the switch at
the animation's end, B -> 134, D -> 135), 623C 13..30 (the rise, until the apex: C version only, 146 / 147). Every other
button / direction changes nothing. With a hit, KOF99's slowdown frames can move a window edge by a frame.

## Every follow-up of Kyo, Iori and K' (TODO #140, 2026-10-06)
Search: the walk logs every read of player input (`PROBE`: the input record `fp` / `a3`, the recogniser's latched bits
`+$1AC-$1AF`, KOF99's `zero` checks) past the first frame, per slot special and fury; brute force in our emulator
(`/data/tmp/fu140/brute.py`: 13 motions / sticks x 4 buttons at every 2nd frame of each special, whiff and hit, block
every 4th, the game's states against the no-press run). New checks (`FOLLOW_CHECKS`; bit k of a mask = `prog['links']`
[k], the names in the order the walk meets them, so one program can have several kinds):
- `hcbP` Kyo `$3CB1C`: recogniser command 7 (`6 2 4` + button, KOF98 bit pair 2k: `+$1AD` bit 6 or this frame's
  `fp@(5)`) with A or C (`a3@(125) & $50`); Kyo 236C Dokugami's part 1 (states 168 / 169) -> Tsumi Yomi (170 / 171)
  at its event step; 214 + A / C counts too while 236C's own forward is still in the recogniser's window.
- `fP` the engine's `$1ED30` (forward exactly + A or C, `fp` / `fp@(1)`), scoped (`FOLLOW_SCOPE`) to Kyo 236C: Tsumi
  Yomi -> Batsu Yomi (172 / 173 / 174). Read 6 frames after the button (`FOLLOW_LAG_KIND`), the stick still forward then;
  the part's input clear (`$24F52`, op `clrinput`) drops a press made more than a frame before it.
- `hitlatch` Iori `$71466`: 623D Kototsuki In's landing (`FOLLOW_LATCH` `$712F4`): 214 + A / C (`+$1AD` bit 6) sets
  `+$D1` bit 7, the handler then jumps into 214A Aoi Hana's handler, whose own `$710F2` checks follow (2 more parts).
  `+$1AC-$1AF` is filled only in the attacker's hit-stop (`$1B3A2`, cleared at each one's start `$1B364`): a
  hit-confirm, on hit or block, never on a whiff (`('check', mask, 'hl')`: the model latches the presses read in a
  hit-stop on the hit's frame, romspecials98 maps them there; the brawler: `fighter_t.phl`, the presses made in its
  hit-stop, P_CHECK b = 1). The jump reads Aoi Hana's button from 214's command (`$70E48`): `FOLLOW_BTN` gives A.
- On hit, a 6A press read inside KOF's hit-stop is lost (`$1ED30` reads this frame's press): romspecials98 drops it;
  presses read within ~2 frames after a hit-stop also miss in KOF and not in the model (Kyo 236C, 6A at 50 / 52 / 58
  after 63214A at 24): left as is, the proofs press outside them.
Model: a part starts at the first animation after any link test found its link armed (`pmask`: which link);
`follow_parts` runs every set of links pressed throughout (Kyo's second link exists only in the part the first starts)
and drops a run that plays what the no-press run plays (K' 623A: the check runs, the A version has no follow-up).
No follow-up input in Kyo EX 236A / 623C / 421B / 214A / EX 421D, Iori 236A / 624D / 623C / 624B, K' 214D / 236B / 236D
/ 623A or the three furies (Kyo's 21426C reads the held button: holding A / C delays the release, not a follow-up:
TODO #198, "Kyo's Orochinagi: the hold" below).
Brute force results: /data/tmp/fu140/out/brute_<fighter>.json (summary `summ.py`: the divergences whose states are not
the move's own; the rest were the press overlapping the special's own input, normals after its end, or the hit / block
branches' run-to-run jitter, which a rerun does not reproduce).

## Furies (desperation moves) read from the ROM (TODO #139, 2026-10-06)
Every KOF-banked fighter's C fury (game.json roster `fury`) goes through the same walk. What the DMs added:
- **Power check**: the handler opens with `jsr $24D80` (KOF96 `$1AB70`, KOF99 `$1FC48`): d0 0 = no power (`jmp` out),
  1 = a CPU's fallback special, 2 = DM, 3 = SDM (+$E4 bit 0). The walk takes 2 (`dmcheck`), so `btst #0, +$E4` picks the
  DM side; `cmpi #1, d0` on the known register is concrete. A button's state pair is one long (`swap` picks C's word).
- **Super flash**: not in the handler (`$19AB4` / `$19AE0` / `$25088` are the afterimage trail, op `trail`): the DM's
  first animation starts it with a `$FA` command (section "Super flash" below). P1 keeps animating during it; P2 freezes.
- **Catch routine** (+$19C): the hit-stop routine `$1B2C4` sends the attacker to its +$19C after the hit when the
  attack box (attacker +$AA) is `$37` on a step with `$4000` (`$1B9F6`) and +$E1 bit 6 is clear (the handler clears
  it; the catch sets it). Boxes `$38` / `$39` clear the attacker's +$AA at the hit (`$3C00`): no routine (Kyo's 214A).
  Op `('onhit', place)`; the model: the catch frame as usual, one dead frame (no code, no animation), then the routine.
  Brawler: `P_ONHIT`, bstep_t flag 64 = a catch box, `fighter_t.pcatch` 3..1 (that frame's code does not see the hit:
  KOF registers it after the code ran), the catch deals no damage (KOF's life does not drop).
- **The caught victim**: `$25032` puts it d0 px in front, facing the attacker (`('place', px)`, `P_PUT`); +$E4 bit 4
  (`ori` / `andi`: `('hold',)` / `('unhold',)`, `P_HOLD` / `P_UNHOLD`) keeps it reeling in place (the victim states
  404-407; its reactions are a standing reel while held); the attacker walking into it shares the push (half its
  forward move: KOF's bodies), as Ryo's rush measured (P1 and P2 both +1.25 a frame at vx 2.5).
- **+$E3 bit 7**: a hit landed since the code cleared it (`andi #$7F`): `('hitclr',)` / condition `hitany`
  (`P_HITCLR`, `PC_HITANY`). The rush's end tests it (finisher or the miss ending).
- **Hit-stop classes**: a step's flags bits 4-6 pick the attacker / victim hit-stop from a table (KOF98 `$1DCCC` via
  `$1DC52`, KOF96 `$16E20`, KOF99 `$19832`); class 4 is 0 / 0 (KOF96 also 6): barrage hits, nobody stops and the
  victim reels in place (Ralf's 164, Ryo's 181). bstep_t flag 128; the brawler skips its HITSTOP for them.
- **Reel without slide**: a hit by a step whose byte 1 (+$7E) bits 0-1 are 3 sets the victim's +$12C bit 2 (KOF98
  `$1AF0E`) and its reel (`$1BBD2`) keeps vx 0 (Yashiro's 173 / 174, Ryo's 184, Ralf's 164): bstep_t flag 4.
- **Mash latch read as no mash**: a `bclr` on a bit the walk knows (Yashiro's +$D1 bit 7, set only by A / C pressed
  again) is concrete.
- **Event latch** (+$7D bit 7): the engine copies a step's flags to +$7C / +$7D at each step (`$5C4A`); code consumes
  the event with `bclr` or `tst` + `andi #$7F` (`('evclr',)`, `P_EVCLR`). The model and the brawler keep the latch
  (set or cleared per step, cleared when consumed): Mr. Big's Blaster Wave spawned a wave every frame of its step
  before, and Terry's 236C, Geese's 236A / 236C, Iori's, Kyo's EX 236A, Mr. Big's / Ryo's 236A spawned extra objects
  (their KOF traces have one).
- **Loops on events**: a field stepped on an event (Blaster Wave's wave count and offset table, Power Geyser's pillar
  table) re-keys the resume point at the yield (`yres`), at most once per event step of the state playing; a table read
  through a1 / a2 (`move.w n(a1), d5`, `lea 12(a2), a2`) is concrete. A small count (<= 8) is unrolled.
- **The yield's own animate**: a state written to +$72 and left to the yield routine's animate call (Ryo's 178) becomes
  an `anim` at the resume point. A height write (`clr.l +$20`) is `('set', 'h', v)`.
- **Object -> owner signals** (+$D1 bits 7 / 6): an object's code ORs them into its owner (Raging Storm's side effects
  at their end start the pillars; K''s shot sets bit 7 on its hit, bit 6 when gone): `('ownersig', bits)` in the object,
  those bits unknown to the owner's walk after the spawn, conditions `sig7` (tst), `sig7c` (bclr), `sig6` (btst), `andi`
  on +$D1 `('sigclr', kept)`. Brawler: bproj_t.sig (bits 7 / 6 at its end, 5 / 4 at its hit), PC_SIG7 / PC_SIG7C /
  PC_SIG6, P_SIGCLR; a pinned object that frees itself ends at its last row (bproj_t.follow 3). The model plays a
  travelling object's hit routine from the frame after the game's hit.
- **Distance** (KOF98 `$16AC0`, KOF99 `$11B52` -> +$BC): `cmpi #N, +$BC; bhi` = `far:N` (K''s dash runs while the
  opponent is farther than 224 px); brawler PC_FAR (the target). `andi #$7F, +$E1` = `('hitoff',)`, P_HITOFF. The
  opponent's own flags (a0 = +$B6) read as a normal opponent's (clear).
- **The yield's second half** (`jsr` the yield's tail, then `jmp` / `rts`: KOF99 `$38E7C` / `$38E88`) ends the frame
  without the animate call: target `yieldn` (the model holds the animation that frame; K''s shot's end at half speed).
- **A ROM object's victim**: its reaction from KOF's table by its attack box (packed, like a body hit) instead of a
  knockdown (K''s shot leaves the victim reeling in reach of the lunge).
- **Traces** (`capture/romspecials98.py dm=True`): KOF96 gives DMs from low life (life 24, +$E2 bit 1 as specials96's
  capture had it), Mr. Big's 23623C needs its last down-forward held 2 frames longer (`DM_EVENTS`); a fury's whiff in
  KOF: P2 jumps over it (`whiff_jump`: the first jump start with no hit and no catch, cached in
  `/data/tmp/romspecials/traces/whiff_jump.json`); where none exists (Robert's rush catches P2 anywhere, airborne too)
  `romspecials_check.py` compares the brawler with the decoded model, which matched KOF frame for frame on the hit side.

Furies played from the ROM: Terry, Ryo, Robert, Ralf, Billy, Kyo, Mai, Yashiro (KOF98), Geese, Mr. Big, Krauser (KOF96),
K' (KOF99): `romspecials_check.py ... fighter:C`, 0 frame mismatches whiff + close each, hits equal (/data/tmp/fury/out,
out96). Still captured: Iori and Goenitz (their finisher is the engine's cinematic hit: KOF98 `$1EB20` box, `$3F8A`
test, `$1E7E8` by +$F8; KOF96 `$17796` / `$3676`), Rugal (the catch grinds to the stage wall `$18092`, which a beat 'em
up does not have), Yamazaki (a command grab whose hits come from the victim's own scripted states 433-442).

## Slot specials read from the ROM (TODO #79-#119, 2026-10-06)
Ten more slot specials play from the ROM, each 0 frame mismatches whiff + close with KOF's hit count on the same frames
(`../brawler/romspecials_check.py`, /data/tmp/slot20/out*): Ryo EX 646A, Robert EX 646D, Billy 623D, Kyo 421B / EX 421D,
Iori 623C (KOF98), Geese 63214A / C, Krauser 623B / D (KOF96). What they added:
- **A catch's dead frames**: the hit-stop routine's catch path ($1B3D6) loads the attacker's hit-stop of the catching
  step's class (`stop_frames`, the class table's first byte, zeroed by +$E5 bit 7) and counts it down at `$1B402` before
  jumping to +$19C: 1 + that hit-stop dead frames (`catch_dead`; the furies' class 4: 1, Ryo / Robert EX class 2: 3).
  Export: `('onhit', target, hit-stop)`; brawler P_ONHIT a, `fighter_t.pdead` / `pdeadn`.
- **The held victim's hurt box**: KOF's held states 404-407 have one box, $31 0, 192, 48, 64, on every step; the
  brawler's held victim (PF_HOLD, the target) uses it (`HOLD_BOX`) instead of its reel's (Ryo EX's barrage: 10 / 12 -> 12).
- **Height compare**: `cmpi.w #N, +$20; bcs` = `low:N` (Billy 623D rises to 192 px), PC_LOW. `addi #N, +$20` = a nudge.
- **Near**: `cmpi #N, +$BC; bcs / bcc` = `far:N-1` negated / taken (Iori 624B / D); the brawler's PC_FAR measures the target,
  before any hit the nearest opponent on its lane (`fighter_t.popp`, the combat pass).
Still captured, with the reason (Iori 624B / D since TODO #94 / #96: section below): Goenitz 214C (wind objects from the animate
routine's step-effect table `$249E8`), Rugal 6426A / C (Kaiser Wave's multi-hit routine through +$C2 / +$138), Rugal
624A (stage wall `$18092`, a branch on vx), Yamazaki 214A (`f-1`), Ralf AAAA / Billy CCCC (mash: no KOF trace of the
repeat), Robert 426B (no capture try enters it).

## Super flash (TODO #139 / brawler `fx.super_flash`, 2026-10-06)
Correction first: `$19AB4` / `$19AE0` (and `$25088`, which picks `$19AB4` when +$E4 bit 0 is set, else `$19AE0`; `$19A88`
/ `$19B06` the same with a lifetime +$D6 8 / 16) are **not** the flash: they allocate the afterimage object `$19898`
(three delayed copies of the owner drawn from its position history, palette +$1AB, +29 for the MAX one; it frees itself
when the owner sets +$E2 bit 1). They are op `trail` now (dropped, presentation). The power check `$24D80` spends the
stock (`$15908`) and sets +$E4 bit 0 for an SDM; it starts nothing visible either.

**The flash comes from the DM's first animation**, an animation command `$FA [id][dx:16][dy:16]` (animate engine
`$5C28` table, entry `$5D1C`: an effect object from the init / routine tables `$36782[id]` / `$36382[id]`, owner +$84 =
the fighter, its x / y = the fighter's +$18 / +$1C + dx / dy each frame (`$37556`: dx negated with the facing, like a frame
part's dx: negative = forward), height copied). Every KOF98 DM / SDM state has it on its second step (after a first step
of 2 frames), two commands at the same offset:
| id | effect | what it does |
|---|---|---|
| `$38` | state 58 (table 38), priority +16 (in front) | routine `$370F0`: sound $99 (`$3906E`: index $99 of the `$7A98` word table `$A9BCE` = $1A $3A, the fury charge; $6E5 = $17 $AB instead when the owner's +$70 is 37 (a character table: not a roster fighter); `$373FC` for `$3E` and `$371A2` for `$39` call the same; measured in our emulator 2026-10-06, QLOG: Terry / Ryo / Ralf / Kyo DM and SDM send $1A $3A on the flash's frame, the DM voice the frame before; the brawler plays it: game.json super_flash sound), then the controller `$37120` (priority $5001): `$10A787` bit 2 + the opponent's player bit ((+$170 & 3) + 1: bit 0 P1, bit 1 P2), `$10A782` = $5001, `$10A840` bit 4; every frame `$10A788` bit 7 (the stage planes drawn blank, `$7FB2` / `$8232`) and `$10D936` (the backdrop, written to `$401FFE` at `$A41A`) = $0000, or $FFFF (white) while state 58 shows its event step ($0080); it ends (bits cleared) when state 58's animation ends |
| `$3E` | state 78 | the same with the SDM's animation |
| `$3C` / `$5A` | state 72, priority -16 (behind) | the glow: one 10 x 10 frame ($291, palette 102) after a 3-frame placeholder; `$3729E` cycles palette 102 through 16 palettes of the ROM table (bank 2 `$2D77F0 + 32 n + 2`, n = 5152 + k blue for `$3C`, 5168 + k orange for `$5A`): k = 0 for 5 frames, then one further each frame (the rings shrink) |
| `$39` / `$3F` | state 58 / 78 + controller `$371D2` | the same flash without the opponent bit (nothing but the objects freeze): Yamazaki 187 / 193, Yashiro 207 / 208 (second parts) |

What freezes (`$A2C0`, `$332CA` / `$33332`): while `$10A787` bit 2 is set the object loop runs only the objects of
priority `$10A782` ($5001: the flash's) and sets +$7B (hold the animation step) on every other object with +$3B bit 5;
the player whose bit is set skips its code (draw only `$600E`). The attacker's own code runs: Terry keeps animating
(state 166's steps advance through the flash). The animate routine itself (`$5BA6`) returns at once when `$10A787` bit 6
is set (a separate, global freeze). State 58 / 78: an event step of 3 frames (white), 8 frames of a placeholder, then
16 one-frame rays frames ($1E8-$1F7 palette 106 blue / $2A0-$2AF palette 107 orange: the same tiles), then holds;
measured in our emulator (Terry 21416C, `/data/tmp/superflash`): the effects spawn on the DM's frame 1, the backdrop is
white 4 frames, black 24 (the stage gone), the stage is back 28 frames after the spawn; P2 frozen throughout; the DM's
rays are white-blue, the SDM's orange-yellow, the glow blue / orange; nothing else differs (same anchor, same timing).
KOF99 (`$329EC` routine table): ids `$F1` DM / `$F2` SDM (+ `$F3`), the same `$3C` / `$5A` glows; screens identical in
structure (black stage, blue glow + rays). **KOF96** (`$4ED0` -> `$24976[id]`): one id `$38` for DM and SDM (sound $91,
effect state 58 of table 29: the glow + rays), no controller: nothing freezes, the stage stays (Geese 1632143C traced).

Per move (`handlers98.super_flash`, the program's whiff model gives the state's start; dx / dy px, KOF orientation;
at = the move's frame the effect spawns; colour 1 DM blue / 2 MAX orange). MAX versions: `decode_variants` finds a
MAX path in every fury handler; Terry's tests +$E4 bit 0 (`$432AC`) before the button (`$432E2`), so 21416A and 21416C
reach the same MAX path (one MAX version: three pillars 171-173, tables `$433A2` / `$433B0`, count 3, damage id 39);
every other handler tests the button inside or after the MAX branch and has two MAX versions (MAX A / MAX C, or B / D
for Mai) with the same states, differing in timings (Ryo / Robert whiff 95 vs 108 frames, Geese 71 / 98, Mr. Big 81 /
99, Goenitz MAX A plays 158 / 171 / 160, MAX C 159 / 172 / 161). **Rule for the brawler (down+D)**: the MAX version
with the fury's own button (the roster's C / D: the heavy one), as D picks the fury's own button.

| fighter | fury (state, anchor dx, dy, at) | MAX version played (state, anchor, at) | MAX versions in the handler |
|---|---|---|---|
| Terry | 21416C (166, 0, -112, 1) | MAX 21416C (168, 0, -112, 1) | one (A and C share it) |
| Ryo | 23624C (177, -12, -76, 1) | MAX 23624C (188, -12, -76, 1) | MAX A, MAX C |
| Ralf | 23624C (161, -35, -80, 1) | MAX 23624C (167, -35, -80, 1) | MAX A, MAX C |
| Robert | 23624C (177, 8, -100, 1) | MAX 23624C (188, 8, -100, 1) | MAX A, MAX C |
| Yamazaki | 236236C (169, 18, -48, 1) | (captured fury: no MAX in the bank) | MAX A, MAX C (179) |
| Billy | 236236C (179, 0, -104, 1) | MAX 236236C (183, 0, -104, 1) | MAX A, MAX C |
| Kyo | 21426C (185, -24, -112, 1) | MAX 21426C (194, -24, -112, 1) | MAX A, MAX C |
| Iori | 23624C (161, -20, -120, 1) | (captured fury) | MAX A, MAX C (167: 24, -88) |
| Mai | 21426D (169, -4, -65, 1) | MAX 21426D (174, 0, -64, 1) | MAX B, MAX D |
| Yashiro | 21426C (171, 26, -104, 1) | MAX 21426C (177, 26, -104, 1) | MAX A, MAX C |
| Rugal | 23624C (195, 48, -104, 1) | (captured fury) | MAX A / C, EX too (203) |
| Geese (KOF96) | 1632143C (177, 6, -124, 3) | MAX 1632143C (203, 6, -124, 3) | MAX A (202, at 2), MAX C |
| Mr. Big (KOF96) | 23623C (133, 12, -68, 5) | MAX 23623C (135, 12, -68, 5) | MAX A (134), MAX C |
| Krauser (KOF96) | 641236C (152, 8, -108, 7) | MAX 641236C (154, 8, -108, 7) | MAX A (153, at 5), MAX C |
| Goenitz (KOF96) | 2141236C (148, -26, -134, 8) | (captured fury) | MAX A (158), MAX C (159) |
| K' (KOF99) | 23624C (193, -1, -90, 2) | MAX 23624C (206, -1, -90, 2) | MAX A, MAX C |
| Haohmaru (SS4), Kim (Kizuna) | no ROM flash: the game-wide anchor (game.json super_flash: 0, -96) | - | - |

The brawler (`fx.super_flash`, docs/brawler_move_vocabulary.md, Bruno's design 2026-10-06): an **engine rule**, not
per-move data. Every fury (D) and MAX fury (down+D) of every fighter flashes: game.json `super_flash` holds the timing
and the colours once (start 1, freeze 28, white 4: KOF98's above; blue for a fury, orange for a MAX fury by role); the
concentration is KOF98's (`make_sparks.py build_flash` -> `superflash.h`, the effects library: the glow frames 3-14, the
rays 11-26, each +2 frames of the object's life). Per move only an **optional anchor**: `export96` stores `flash`
(`super_flash` on its states), `export_bm` writes only its dx / dy into `bspec_t.sf_dx / sf_dy / sf_anchor`; a move
without one (SS4, Kizuna, WHP, future fighters) plays at game.json's anchor. The export adds the MAX moves once:
`MAX <fury>` (`export_rom` with the 'MAX ' prefix: `decode(sdm=True)`) for every ROM fury with a MAX path, `bchar_t.fury_max`.

## Kyo's Orochinagi: the hold, the MAX's burning body (TODO #198, 2026-10-07)

Handler $3D4EA (21426A / C; the MAX version = the same code with +$E4 bit 0, `decode(sdm=True)`):

| what | ROM | decoded as | brawler |
|---|---|---|---|
| the hold | +$CA = 90 at the start ($3D586; a CPU player, +$170 bit 7: a random 0-63, $3D676); after the start animation (185, MAX 194) the hold state (187, MAX 195) starts and from its first frame `move.b +$1A4, d0; andi #$50, d0; and.b (fp), d0; beq release` then `subq #1, +$CA; bpl yield`: held, it stays up to 90 frames; released, the release (188, MAX 196) starts that frame | `set cnt 90`, `br held False -> release`, `dec`, `br cnt False yield`: every `and.b (fp)` past a move's first frame is the run-time test `held` (it was read as released: a tap). Measured in our emulator: the pad reaches the handler's (fp) 2 frames later (`romspecials98.compare(hold=)`) | PC_HELD (D held: a fury's button), P_SET / P_DEC cnt, PC_CNT |
| the burning body (MAX) | state 195 (frames 481-488) has attack box $23 live on every other step (flags $1F21 / $1E21, no $4000: a new hit each time); damage table +$EF = 55 while held, 56 from the release ($3D6CA) | the hold's states are counted with the button held throughout (`openings(held=300)`: 195 opens 16 hits) | `bstep_t` attack box: an enemy that walks in burns (KOF98: 11 life of 103, P2 launched, state 286); the brawler's rule: SPECIAL_DAMAGE split over the openings -> 1 a hit |
| the flames | object 2 ($3D83E, state 193, frames 469-480) in Kyo's effect palette 33 ($B81); +$34 (1, MAX 3) = how many flames chain (`spawndeep`) | - | (colours: TODO #198 c, the ground flame of EX 236A, palette 37: export_bm `pal_slots`) |

KOF96 (Bruno's note cites "Kyo 96"): Orochinagi $298CA is the same code (+$CA = 90, the hold test, start 188, hold 190,
release 191), decoded the same way now; neither 190 nor its hand flame (object state 286) has an attack box: the
burning body is KOF98's MAX only (state 195; KOF96 has no MAX version).

KOF98 vs model (`romspecials98.compare(0, '21426C', ..., dm=True, hold=H)`), whiff and close, DM and MAX, H = 30 / 60 /
89 / 200: 0 frame mismatches (x mismatches only where the hold changes nothing: the whiff's screen edge, the close
push, as with H = 0); the hold caps at 90 frames of 187 (DM whiff: 125 / 154 / 184 frames at H = 60 / 89 / 200).

## Kyo's flames: their lifetimes, the MAX chain, the hand fire (TODO #202, 2026-10-07)

Bruno's notes on 0.1.8 (the Orochinagi's flame gone too fast, 236C's punch without its fire). KOF98 in our emulator
(`../brawler/romspecials_check.py`, every object P1 owns) against the brawler showed what was missing:

| what | ROM | decoded as | brawler |
|---|---|---|---|
| the flame's life | object $3D83E (state 193, MAX 199 / 200 / 201) frees itself at its animation's end or when its owner is hit (`btst #2, owner +$E2`: set by the victim hit routine `$1B48A`); it never reads owner +$D1 bit 7, the handler's `fxoff` at 189's end | export_rom: a pinned object without `br owner_fxoff` = follow bit 32 | `prog_fxoff` leaves it: 43 frames ([46, 88] in KOF98, [46, 89]); it was cut at the fxoff, 9 frames |
| the release's glow | object $3D7E6 (243) reads +$D1 bit 7 and then plays 244 in place to its end | `object_rows(fxoff_at=FXOFF_AT)`: the rows after the bit = its end rows when they are another animation, follow bit 64 (Rugal 6426B's $7F1CC only stops following and plays on: unchanged, it ends at the bit as before, = KOF98) | `prog_fxoff` -> pend 6 / 7: the end rows in place from the next frame ([43, 70] / [43, 71]) |
| the MAX chain | +$C2 = owner +$34 (3); each flame `subq #1, +$C2`, at its event step (step 5, frame 10) spawns $3D83E again 16 px ahead (`d5 = -16`) in +$D6 (200) when +$C2 = 2, else +$D8 (201); only the first follows Kyo (`cmpi #2, +$C2`) | `cmpi` on a field an object knows is concrete (`CMP_KNOWN`, depth > 0: only Kyo's MAX changes among the 210 ROM programs); `obj_chain`: the copy as the object's child (births = its event frame, dx 16) | bproj_t child, child of its own (export_bm `child_c`); an eruption that hit (pend 2 / 3) keeps spawning: 3 flames [47, 77], [57, 87], [67, 109] = KOF98's (whiff, within a frame); close: KOF98 3 hits, the brawler 2 (its victim, launched by the second, is out of the third's reach: the reaction, not the flames) |
| the hand fire | animation records `$FA` kinds $40 / $41 (pinned, states 253 / 254), $42 (once, 255), $45-$48 (once, 249-252) on Kyo's 168 / 170 (236C), 185 / 188-192 (the fury's charge and release), EX 236A's 205 / 213 | `fx_routine` follows the kinds' tails ($37488 falls into $37494; $3770C -> `bra $36C12`, the 'once' placement inline); `STEP_FX` + Kyo (0) | `pan_fx` spawns them as effect objects of their own (never the shot, never ended by P_FXOFF); in a super flash the attacker's effects born in it run (KOF98 runs P1 and what it spawns at the flash's priority $5001), the rest stay frozen (`projectiles_update` skip mask), and they hit (combat's flash filter takes its objects: K''s Heat Drive shot's first hit at 19, KOF99 21, was 28; Geese's Raging Storm objects all within a frame now, 14 off before) |

Measured (whiff, KOF98 | brawler, spawn / end frame of the move): DM 21426C all 16 objects within a frame; MAX 18 / 18;
236C's fist fire [17, 43] / [17, 44] at KOF's x (0.25 px). Found, not changed: in a ROM special the brawler's victim
test uses the hurt box of the animation the fighter played before the special (combat `fighter_step`, not the program's
step): KOF98's steps without a hurt box (EX 421D's first 11 frames, 491 and 493's first step) are hittable in the
brawler (Kyo hit at frames 2-9 on 0.1.9); Kyo's EX 421D is now invincible throughout by Bruno's call (game.json roster
`invincible`), which covers them.

## The victim's burn: the hit's element (TODO #206, 2026-10-07)

Bruno's note on Kyo's fury ("the opponent should be on fire whenever hit by the Fury of Kyo"): KOF98's Orochinagi hits
with kind 7 ($1A $37, the flame roar; its charge sets 21 first) and its victim burns, so the hit kind (+$1B8, the
sounds) does not decide the burn. Read in the code and measured in our emulator:

| what | where | |
|---|---|---|
| the element | animation step byte 1 -> the object's +$7E; bits 4-6 | Kyo: $20 on 623C 129 / 131, 236C 168-173, the fury flame 193, MAX body 195, MAX flames 199 / 201, $50 on 200 (the chain's middle flame), EX 236A's ground flame 482; Iori $30 |
| the hit | `$1AF44`: victim +$132 = hitter +$7E & $70 | (the hitter: the object that hit, a flame for the fury) |
| the colours | `$17764`: index = element / 4 (+2 in MAX mode, +1 in a no-effect case) into one of four byte tables by reaction group (`$17E2A` / `$17E4A` / `$17E6A` / `$17E8A`), -> `$177F4` handlers | $20: `$17896` palette byte +$3A = $F8 (orange) + the flame object; $30: `$17910` $F9 (purple); $50: `$178FE` $F8 in the `$17E8A` group only; $10 / $40: other effects (no burn) |
| the sound | `$1E28C` by +$132 / 16 (elements $20 / $30 / $50: index 110 = $1A $2E) besides the kind's | the brawler plays KOF96's fire hit ($2E, TODO #197) on every burning hit |

`handlers98.fire_element(m, cid, state)` = the first burning element (`BURN_OF`: $20 / $50 orange, $30 purple) of a
state's live attack steps; `export_rom` gives it per body state (`elements`) and per object (`element`: copies and
phases too); export_bm `move_fx` burns a P_ANIM / object hit by it (else by the fire kinds 11 / 13 / 21 as before).
Measured over every KOF98 ROM special (`tools/brawler/burn206_kof.py`, P2 48 / 112 px ahead, P2's +$3A after the hits):
the moves whose states carry a burning element burn in KOF98 (victim +$3A $F8 / $F9) and the others never do.
Newly burning in the brawler: Kyo 21426C / MAX (the flames), EX 236A (its ground flame), Ralf [2]8A / [2]8C, 23624C /
MAX (the last punch), Billy MAX 236236C, Mai 21426D / MAX, 214C, 623D; already burning by their kinds: Kyo 623C /
236C, Iori 236A / 623C / 623D, Billy 23624C / MAX.

## Rugal: the wall slams, the charge, the step effects (TODO #173, 2026-10-06)

Rugal's four recorded moves are read from his handlers now; what they needed:

| feature | ROM | decoded as | brawler |
|---|---|---|---|
| the stage wall | `jsr $18092; beq yield` (d0 0 inside, -1 / -2 at x <= 32 / >= 736) | `br wall` (was misread as a branch on vx: the cc of the call) | PC_WALL: the screen-edge walls (stage.wall, wall_lo / wall_hi) |
| a frame counter at the resume point | `move #3, +$D2; move.l #R, (a4); R: subq #1, +$D2; bpl yield` | `set cnt`, `dec`, `br cnt` (only in the wall-slam handlers: `A3_RECORD`'s; elsewhere a small count at a resume point stays a decode-time repeat) | P_SET / P_DEC / PC_CNT |
| the victim signal | `movea.l +$B6, a0; ori.b #$80, $D1(a0)` | `vsig` | P_VSIG: the victim's next list |
| the victim's script | the catch installs the attacker's +$1A0 on the victim (`move.l #R, $1A0(a4)` before the catch); R: `lea list, a0; move #size, d0; jsr $24B22` then `jsr $25372` each frame until its +$D1 bit 7; a MAX test `btst #0, $E4(a0)` on the attacker | `victim_lists` (the lists in order, the MAX path by sdm), `victim_entries` (throwtables96.entries for the fighter itself as the victim: the brawler's throw rule) | bspec_t.vlists, fighter.c vlist_apply (entry of the attacker's step: offset, height, posture, facing, front; $01 a blow, $40 the release) |
| the jump back | `move.l 30(a3), +$50` .. `42(a3), +$5C` | `set vx / fric / vy / g` from `A3_RECORD` (a3 is not a pointer the walk sees: the record measured in our emulator, $AC870: vx -10.3125, friction $E900, vy 4.125, gravity 0.6055) | P_SET |
| the turn (MAX fury) | `eori.b #1, $31(a4)` (+ the victim's), `neg.l +$50` | `turn`; the speeds after it stay forward + | P_TURN |
| the charge (Kaiser Wave $7EDAA) | `clr +$D2` at $7EE78, then while `move.b +$1A4, d0; andi #$50, d0; and.b (fp), d0` is not zero (its button held) each event step `addq #1, +$D2`; at the release `tst +$D2; beq`, `cmpi #1, +$D2; bls` pick the level's state list (+$C2) and damage (+$C6) | `CHARGE`: `set cnt 0`, `br held`, `add cnt 1`, `br cntle:0`, `br cntle:1`; each level's path walked with the count known (0, 1, 2) | PC_HELD (fighter_t.pheld), P_ADD, PC_CNTLE |
| the multi-hit wave | its hit routine $7F004: `movea.l +$C2, a0; addq.l #2, +$C2; move.w (a0), +$72` (the list's next state), `subq #1, +$138` (hits left: frozen +$124 frames, then flies on in that state; none: the state plays in place, freed at its end) | export_rom: the object's `clist` + `f138` -> a phase per hit (`hitnext`), the last state as its end rows | bproj_t hitnext / next / stop (object.phase at hit) |
| step effects | animation records `$FA kind x y` -> `$5D1C`: routine table `$36382[kind]` | `step_effects` / `fx_routine`: 'pinned' (`bra $37494`: kept at the owner + (x, y), freed when the owner's state / step changes from the one it saw on its first run) and 'once' (`bsr $36BAA; bra $36C54`: placed once, freed at its animation's end + 2 frames); the fighter's own table only; `STEP_FX` gates them (Rugal) | bchar_t.pfx, bproj_t follow 8, fighter.c pan_fx |

Rugal's states: God Press 161 (start) 162 (rush, its catch box) 163 (recovery) / 167 push, 168 slam, 169 jump back, 170;
Gigantic Pressure 195 / 196 / 198 / 201 push, 202 slam (+ object state 252, the explosion), 210, 211; its MAX 203-205,
207 push, 208 the hits (list $29B128), the turn, 207 again, 209, 210, 211. Kaiser Wave 132 / 133 (A / C), 134 the
charge, 135 / 136 the release; the wave 137 / 138 / 140 by level (A 4 px a frame, C 16), its hit states 139 / 141 / 142,
its ends 143 / 144; the hand charge state 246 (kind $DF). Not exported: the effects of the shared bank (God Press's
slam explosion kind $32, the fury's start $38 / $3C: table 38).

## Iori's 624B / 624D: the catch's victim script and its own release (TODO #94 / #96, 2026-10-07)

Handler $70A6C (B: dash 16 frames, D: 24; both button variants exported). Its catch was the blocker of 2026-10-06 (the
victim held in states 432-435, placed each frame by a table); that is the victim-script model Rugal's moves brought in
(TODO #173: the catch installs +$1A0 = $70CBC on the victim, `lea $283528, a0; move #20, d0; jsr $24B22`, then `jsr
$25372` each frame until the release entry). What was still missing was the routine's own release:

| what | ROM | decoded as | brawler |
|---|---|---|---|
| the program | 134 start; 135 dash (`move`, cnt 16 / 24) until `cmpi #88, +$BC; bcs` (near) -> 137 the strike (a normal hit, P2 262) whose `+$E1` hit test -> 138 (its catch box $37) -> catch routine $70C6A: 140 the explosion; cnt out -> 136 | as before (0 frame mismatches whiff + close since #95) | ROM program, `P_ONHIT`, `bspec_t.vlists` |
| the blow at the release | past `btst #6, +$D4` the victim's routine calls `$18C6C` + `$1ACD8` (the pair `$25372` calls for a blow entry): KOF98 P2 life 98 -> 86 | `victim_release`: 'blow' -> the release entry gets flag 1 | VE_BLOW + VE_REL on one entry: damage then the flight |
| its burn | `jsr $17AC0`: victim +$3A = $F9 (purple; measured: from the release to the landing) | `RELEASE_BURN` -> entry key 'burn' | bvent_t flags bits 4-5 (VE_BURN): `set_burn` with the blow |
| its own flight | `move.l #$70E32, +$C6`: vx 4 (away), gravity 0.5, vy 6 (+$50 / +$5C / +$58), states $70E28 (313, 309, 313 bounce at vy 2.5, 326, 72) | 'fly' -> the last list `{'e', 'rel': (vx, vy, g)}` 8.8 | VL_VEL with g: `kmode` 2, `kg` = g (kof_fall), not KOF's blowback |

Rugal's victim routines have neither (their release jumps to the blowback): unchanged. Not exported: state 140's
explosion effects ($FA kinds $18-$5D: the shared bank, as Rugal's slam). KOF98 vs brawler (`../brawler/romspecials_check.py`,
/data/tmp/iori94/out): 0 frame mismatches whiff, close (48 px) and mid (112 px: the dash first), hits 2 / 2 on both
(KOF [18, 61], brawler [17, 62]: the strike, the release blow); the victim's flight height identical frame for frame
(one frame later: the release follows the attacker's step), its x off by the victim row (the brawler plays every victim
with the attacker's own row, KOF P2's own) and the screen edge. 624D's whiff never exists in KOF (its 24-frame dash
reaches P2 from any distance on KOF's one screen): its reference is the decoded model (`WHIFF_MODEL`), the same code as
624B's whiff, which matches KOF.
