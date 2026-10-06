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
- Supers / MAX (super flash, stock spend) not tried.

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
/ 623A or the three furies (Kyo's 21426C reads the held button: holding A / C delays the release, not a follow-up).
Brute force results: /data/tmp/fu140/out/brute_<fighter>.json (summary `summ.py`: the divergences whose states are not
the move's own; the rest were the press overlapping the special's own input, normals after its end, or the hit / block
branches' run-to-run jitter, which a rerun does not reproduce).

## Furies (desperation moves) read from the ROM (TODO #139, 2026-10-06)
Every KOF-banked fighter's C fury (game.json roster `fury`) goes through the same walk. What the DMs added:
- **Power check**: the handler opens with `jsr $24D80` (KOF96 `$1AB70`, KOF99 `$1FC48`): d0 0 = no power (`jmp` out),
  1 = a CPU's fallback special, 2 = DM, 3 = SDM (+$E4 bit 0). The walk takes 2 (`dmcheck`), so `btst #0, +$E4` picks the
  DM side; `cmpi #1, d0` on the known register is concrete. A button's state pair is one long (`swap` picks C's word).
- **Super flash** (`$19AB4` / `$19AE0` / `$25088`, screen darkening object): bookkeeping. P1 keeps animating during it
  in the traces; only P2 freezes.
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
Still captured, with the reason: Iori 624B / D (the catch puts the victim into KOF's held victim states 432-435, placed
each frame from a table by `$25376` / `$25396`: the throw-victim model), Goenitz 214C (wind objects from the animate
routine's step-effect table `$249E8`), Rugal 6426A / C (Kaiser Wave's multi-hit routine through +$C2 / +$138), Rugal
624A (stage wall `$18092`, a branch on vx), Yamazaki 214A (`f-1`), Ralf AAAA / Billy CCCC (mash: no KOF trace of the
repeat), Robert 426B (no capture try enters it).
