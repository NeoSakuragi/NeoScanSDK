# Golding Terry, Kim, Krauser (2026-10-08)

Bruno: focus on bringing these three to a finished "gold" reference state. The other 22 are then built to this bar.
Source: docs/brawler_review/{terry,kim,krauser}.md, the review answers on the VPS, docs/brawler_feel.md 8h.

A golded fighter has:
1. **Chain**: only kept pieces, >= 3 hits, good flow (end pose -> next start, spacing, rising intensity), a snappy
   first hit (principle 1). Length by archetype (fast 5 / balanced 4 / heavy 3), the finisher being the last link.
2. **Five directional finishers** chosen and each visually complete (neutral / forward / up launcher / down / back throw).
3. **Retimes** applied so every kept piece looks good and reads snappy: Bruno's explicit asks + any choppy piece tightened
   (within 0.5x-2x). Every animation independently pleasing; nothing choppy or too short ships.
4. **Specials / fury / MAX** per the decisions and the review notes.
5. **Throws** (phase 3) and **meter / damage tiers** (phase 2) already in.
6. Sign-off: a before/after clip set per fighter for Bruno (Ship AFTER / Stay with BEFORE / Needs work).

## Krauser (heavy, applied in 0.7.0)
- Chain close C > far D > crouch C; forward far C, up close D (launcher), down crouch D (crumple → plays as sweep KD),
  back throw. Open: his "neutral = far D" conflicts with the chain (far D is link 2) — pending.
- Grab fury (Gigantic Pressure) provisional. 236D "the dragon move". Later: his jumping command grab as a custom move.

## Terry (balanced, 4 links) — to apply (my picks where the follow-up is blank; Bruno retunes in the chain tool)
- Starter far A. Chain far A > down-forward C > far D > (neutral finisher). >= 3 hits held.
- Finishers: neutral close D, forward body toss (kept), up = **623C launcher** (he said the up MOVE is better mid-chain,
  so up finisher = Rising Tackle, a proper launcher), down his trip "at least 3 chain" (only after 3 hits), back throw.
- Retimes: jump CD startup faster; 623D play the end of the anim out (don't cut recovery); drop far B (choppy, done),
  close A, crouch A/B, jump A.
- Roles: close B = hold hit; 426B = the forward,forward+A dash attack.

## Kim (fast, 5 links) — to apply
- Starter close A. Chain close A > forward+B > close C > down-forward C > (neutral finisher). 4 hits + finisher.
- Finishers: neutral far D, up launcher (keep), down **down-forward D (crumple)**, back throw.
- Specials: [2]8C becomes **invincible**; 421A keep the animation (flagged as the future MAX-fury start, not wired yet).
- Dropped: far A, far B, close B, crouch A/B. Intermediates liked: down-forward C, forward+B, close C, close D.

All Terry/Kim chain-order and finisher picks here are my first pass, marked provisional: Bruno finalizes live in the
Lab chain tool or via the terry2 / kim2 follow-ups.

## Bruno's live redesign (2026-10-08) — supersedes phase 2's meter and the Blitz-name opens

### Inputs (four buttons, no fireball motions)
- A attack / chain. B jump. C special (+ direction). D fury (down+D MAX).
- **A+B = C**, everywhere: anything done with C (+ direction) can be done with A+B (+ the same direction), e.g.
  forward+C = forward+A+B. (Final Fight players reach for A+B when caught.)
- NEW: **Blitz** = a free, meterless special family on DOUBLE-DIRECTION + A: forward,forward+A / down,down+A /
  up,up+A / down,up+A. Genre-standard (TMNT, Battletoads, Golden Axe, SOR2 blitz). Free, spammable, a little recovery,
  NOT invincible. Not every fighter fills all four slots. (Name: still "Blitz" provisionally — Bruno to confirm.)

### The combo ladder (each step cancels into the next)
chain → chain finisher → **Blitz** (free) → **special** (1 cooldown chunk, invincible) → **another, different special**
(a 2nd chunk) → **fury** (fury bar full). A special cancels into any OTHER special (not itself); with the 2-chunk bar
that is two specials back to back, emptying it. The fury is the LAST rung: there is no fury → MAX cancel, because each
fighter has only ONE fury — the MAX is that same fury's empowered form when triggered in the red low-life state. No EX
specials (Bruno: overkill for now).

### Two meter bars (replaces the 3-stock / 300-point meter and the old breaker path)
- **Drive meter** (internal name, after KOF XIII's Drive gauge; the screen need not say "drive") **— 2 chunks, SOR3-style**, the one bar shown on the HUD: starts full, refills over time. Regular special = 1 chunk (two
  available). **Counter special** = the combo breaker: a special done while being hit (Final Fight's A+B escape) costs both
  chunks at once, and the fighter blinks WHITE for the whole move to show it was the special situation. With fewer than
  2 chunks: no drive is spent, it costs a bit of LIFE instead and the fighter flashes RED ("this one hurt you").
  Defaults until Bruno says otherwise: the life cost = phase 2's breaker cost (12), taken when the breaker starts, and
  it never takes the last point of life.
- **Fury gauge — HIDDEN** (like KOF98's guard-crush gauge: runs in the program, never drawn): fills as you DEAL and as you TAKE damage. Gauge full → D does the fury (gauge emptied). LOW LIFE → UNLIMITED fury: D is free (Bruno 2026-10-09, his
  0.9.0 note, reversing 2026-10-08). The MAX = DOWN + D with the gauge full AND low life (gauge emptied).
- **Signals — one meaning per place** (Bruno, confirmed):

  | State | Life bar | Fighter sprite |
  |---|---|---|
  | normal life, gauge not full | normal | normal |
  | normal life, gauge full (fury ready) | normal | blinks WHITE (1 frame normal, 1 frame shiny white palette, KOF95-style) |
  | low life, gauge not full (unlimited fury) | blinks RED | blinks WHITE |
  | low life + gauge full (MAX ready) | blinks red | blinks RED, same 1/1 rhythm |

  The sprite only ever says "D does something now"; danger lives on the HUD. On screen: the life bar + the drive
  meter's 2 chunks; the fury gauge itself is never drawn.
- Loose thread: the phase-3 super throw — keep it (cost a special chunk) or drop it. TBD.

### Terry (gold) — DONE: Bruno 2026-10-08 on 0.8.7, "Terry feels great"
- **Blitz**: ff+A Body Toss, dd+A Power Charge (= 426B), du+A Power Wave (= 236C), uu+A Crack Shoot (= 214D) (swapped by Bruno, 0.8.4 note).
- **Specials (C + dir)** — FINAL (Bruno 2026-10-08): forward + C = Power Dunk (623D), down + C = Burn Knuckle (214C),
  C in any other direction = Rising Tackle (623C, the upside-down spin; checked on the clips).
- Chain / finishers / roles / retimes: per the earlier Terry gold section + review (more changes may follow).

### Jumps (Bruno 2026-10-08)
- ONE jump for every fighter: Cody's Final Fight trajectory (Final Fight uses the same arc for Guy / Cody / Haggar:
  7 f crouch, 41 f in the air, peak 61 px — docs/brawler_feel.md 8d). One height only (no short / tall hop).
  To do: capture Cody's arc frame by frame from the ROM (/data/emu, FBNeo) — height and forward speed per frame — and
  replay it as data. Pixel default: same frames, same height in lines, forward distance converted by the CPS1 / Neo Geo
  pixel aspect so it looks the same on a TV.
- THREE air attacks only: A in a forward jump, A in a straight jump, down+A in either. Genre pattern: the standard jump
  attack is a kick and KNOCKS DOWN; down+A is a punch, a dive or similar and only FLINCHES. One can be cancelled
  into the other in the air, like Final Fight (order: question on the jumps page). Active frames (Bruno): the standard
  jump attack active ~12 frames or more; down+A active for the whole rest of the jump. Picked per fighter from its jump normals (Terry's review: jump
  A dropped, jump B and jump CD kept).

### Walk and run (Bruno 2026-10-08) — CONFIRMED: Terry = Cody, Kim = Guy, Krauser = Haggar, run = 2x walk
- Today: fighter.c moves whole pixels (`whole(ph->walk)`), run = walk x 2 (RUN_MUL). Terry walks 3 px/f (KOF 3.17
  rounded), Kim 2, Krauser 3; runs 6 / 4 / 6.
- Bruno: Terry walks at Cody's speed. Final Fight walk 2.10 / 1.95 / 1.85 CPS1 px/f (Guy / Cody / Haggar, 8d).
  Same time to cross the screen: x 320/384 → 1.75 / 1.625 / 1.54 Neo Geo px/f. Proposal: by archetype — fast (Kim) =
  Guy 1.75, balanced (Terry) = Cody 1.625, heavy (Krauser) = Haggar 1.54; sub-pixel movement (drop the whole-pixel
  rounding for the walk).
- Run: Final Fight has none; Bruno suggested 1.8x. My proposal 2x (Captain Commando's dash / walk = 3.875 / 1.9 = 2.04,
  the closest Capcom reference) → Terry runs 3.25 px/f.

### The dash, and the dash in the air (Kim 2026-10-09; Double Dragon 2026-10-11, note 20261011-114113-5d29)
- `roster[].run {"mode": "dash", "dash": {start, frames, dx, height}}`: forward,forward = one burst over a fixed course
  instead of a run (KOF94 / 95's, Kizuna's). `start` frames on the ground, then `frames` frames covering `dx` px at a
  steady speed on a parabola `height` px high, then the animation's landing, then neutral. Its height is drawn only:
  the dash is a ground move (y 0: its hurt box, throws, the ground rules). Kim (Kizuna 66); Billy Lee, Super Billy,
  Cheng-Fu (Double Dragon's 66 = their animation 2: Billy a crouch + a hop, Cheng-Fu two shuffle steps + the leap 39;
  landing 11; tools/doubledr/export_dd.py DASH).
- `"air_buttons": true` (the DD fighters): in the dash's airborne frames the buttons are a jump's. A (down+A) plays the
  forward jump's attack `air_cd` (the down attack `air_b`); C plays the stick's air special if the fighter has one
  (`air_specials`); B, D, and C without an air special do nothing (no second jump, no fury in the air). The press turns
  the dash into a forward jump on the rest of the dash's own course: y = the course's height (in the air everywhere the
  engine asks: air reaction if hit, not grabbable), the dash's travel kept (fighter.c dash_air, jump_frame jrun 2).
- Landing (note 20261011-114113-5d29's reopen, Bruno: "make sure that the character resets to stand at the end of the
  dash motion, even if an air animation is being played"): at the course's end the fighter stands at once (neutral,
  no landing recovery). An air move still playing there is cut on that frame (Cheng-Fu's j.D, which starts 19 frames
  in while his dash's air lasts 21, never plays on the floor): no air pose on the ground.
- Without a press the dash's hurt box and height stay ground-level from start to end; A in its crouch or its landing
  is the ground's run + A (the ff Blitz / the dash attack). Kim keeps the ground rules all through (no air_buttons).

### Terry's chain — Bruno 2026-10-08 (replaces the first-pass pick above)
- Chain: far A > far A > close C (2 hits) > close D (close D = the neutral last hit). 4 links, 5 hits.
- Last hit with forward: forward + A (2 hits). With down: crouch D sweep. With up: down-forward + C.
- Page feedback: the clip-per-move chain view needs too much scrolling on a phone → chains must render as ONE compact
  row (small looping clips with arrows), the whole sequence on one screen.
- Breaker (C or A+B while being hit) = ALWAYS the fighter's neutral C special, whatever the stick says (rule for every
  fighter). Terry: Rising Tackle.
- Fury = Power Geyser, MAX = the triple geyser. Super throw: dropped. Hold + C (any stick) = the C special for the stick, as standing (Bruno 2026-10-10, note 20261010-145638-b3f3; it threw until then); the throws are forward / back + A.
- Air: forward jump + A = jump D, straight jump + A = jump CD (startup sped up), down + A = jump A (flinch, active for
  the rest of the jump). Cancel: down + A first, then the jump attack. The chain always starts on the ground at link 1.

## Kim (fast) — Bruno's paper sheet, scanned 2026-10-08 (/data/scans/brawler/kim_notes_231734.png) + answers
Animation numbers = Kim's table in Kizuna Encounter (the dictionary: brawler-lab/anims.html?f=kim).
- Chain A x5: $48 (jab, close A) > $56 > $5A (far C) > $96 (triple hit) > $98 (stick + kick).
- Last hit + forward: $54. + up: $9A. + down: $4D then $57 played back to back (a 2-part finisher: new in the engine).
- Blitz: forward,forward + A = Hangetsuzan = the 214B lunge ($93; Bruno: "the lunge, like Kim Kaphwan in KOF, classic");
  down,down + A = $5C; up,up + A = $B6 (stick launcher); down,up + A = Hienzan ([2]8C).
- C (neutral, also the breaker) = Hienzan too — the same move as a free Blitz AND as the paid invincible C special
  (Bruno: "yes, let's have some fun").
- Air: jump + A = $59; jump + down + A = $60.
- Hold: hit = $6D; the throw-out finisher = $6E.
- forward + C = $101, the double kick that does NOT eject the enemy: a RESET — Kim lands back standing with the frame
  advantage to start another combo (a tribute to his Kizuna infinite; "comprendra qui pourra"). down + C = $4D, the same
  concept: a double hit that leaves Kim net positive for a reset.
- Fury = the Phoenix (6246A). MAX = the same Phoenix for now ("we'll build an even crazier custom dance" later).
- Size: 1.0 = Kizuna's own $CC size, ~115 px (Bruno 2026-10-09: "he feels very small, I want him bigger", picked 1.0 over 0.92 = ~106 px; Terry 100). Previously: Kept against the official-height 0.86 (docs/brawler_heights.md): Bruno, "Kizuna has this big SNK sprites feel anyways".

### Kim — queued changes (Bruno 2026-10-09; BUILT on gold/kim-q1: $53 reset +14, $5D, $96 retimed 72 -> 40 f)
- forward + C: $101 -> $53, keeping the RESET behaviour (no eject, Kim recovers with frame advantage; Bruno: yes).
- chain: the second A $56 -> $5D.
- $96 (the triple kick, chain link 4): keep the shape of each of its three kicks, but play them at the pace of three FAST
  attacks (retime: short startup / recovery per kick), each with a STRONG impact sound and the regular push back.

### Kim — Bruno's 0.9.2 notes (built in 0.9.3)
- Last hit + forward = $9A (the launcher), + up = $54 (swapped).
- down,down + A = Hienzan ([2]8C); $5C dropped ("we don't need it"). down,up + A stays Hienzan too.
- down,up + A: empty (no longer Hienzan; Bruno 2026-10-09). Built with the $6E fix.

### Meter — Bruno's 0.9.7 note (built in 0.9.8)
- The fury also costs 1 drive chunk, the MAX 2 (game.json meter.fury_drive / max_drive). The blinks only show when the drive is there too.
- **down + D falls back on the fury** (Bruno 2026-10-11, note 20261011-210011-5d29, every fighter): when the MAX's
  condition or cost is not met (not the red state, or fewer than max_drive chunks) but the fury's is, down + D plays the
  regular fury with the fury's cost (fighter.c fury_buy: neutral, hold, and the cancel into the fury alike). Before, it
  did nothing (e.g. one drive chunk at low life with the gauge full). Proof: tools/brawler/kyo_round3_proof.py fury
  (Kyo, Haohmaru, Cheng-Fu: one chunk + low life and two chunks + normal life -> the fury, one chunk paid; two chunks +
  low life -> the MAX, two paid; no chunk -> nothing).

## Krauser (heavy) — Bruno's arbitration sheet 2026-10-09
Decisions set krauser-arb (Lab arbitrage.html?f=krauser); animation numbers = Krauser's KOF96 animation table (his
dictionary: brawler-lab/anims.html?f=krauser, tools/brawler/animdict.py). BUILT on gold/krauser (size unchanged).
- Chain A x3 (heavy): $6A close C > $70 far D > $6E crouch C (the neutral last hit) — as before.
- Last hit + forward $6B far C, + up $6F close D (launcher), + down $73 crouch D, + back the throw $AE — as before.
- Blitz: forward,forward + A = $8F = 623B Kaiser Kick (its ROM program); down,down + A = $96 = 41236D Kaiser Duel Sobat
  (ROM program, added to handlers98.ROM_SPECIALS); up,up + A = $A9, a cartwheel of KOF96's unused Kaiser Inferno, played
  as an animation special (3 hits, the last knocks down; KOF96 marks its hits as fire: the victim burns); down,up + A empty.
- C (neutral, also the breaker) = $88: it IS the big Leg Tomahawk (236D: $88 the jump, $8A the axe kick, $8C the landing;
  236B is $87 / $89 / $8B), played as KOF96's 236D program. C up / up-forward / down-forward: the same.
- forward + C = Blitz Ball HIGH, down + C = Blitz Ball LOW: 214C / 214D (the C / D versions: the 7 px/f ball, A / B's
  is 4 px/f), ROM programs (added to ROM_SPECIALS).
- Air: jump + A $71 jump D (forward and straight jumps), jump + down + A $6C jump C; down,down + A in the air: empty.
- Hold: hit $65 close B, finisher $6F close D; throws forward and back both $AE (the back one = $AE turned:
  roster.throws.back "throw_c"; his forward + D throw $B1 is no longer played).
- Fury (D) = $98, 641236C Kaiser Wave, as now.
- MAX (down + D, low life) = KOF96's MAX Kaiser Wave (the handler's +$E4 bit 0 path: pose $9A, the bigger wave $9D,
  impact $9E), its wave PIERCING: 4 hits on every enemy it crosses (roster.max_hits 4; 45 damage per enemy = the MAX
  tier), victims sent away from him. Superseded 2026-10-11 (note 20261011-134041-5d29): every Kaiser Wave (the fury
  and its MAX) hits each enemy at most 2 times and 10 times in all, then vanishes (roster.proj_hits, "Projectile hit
  budget" under engine features). "Purple": no purple Kaiser Wave exists in KOF96's data — the MAX wave's frames
  ($9D) use palette 10 like the normal wave's ($9B), a blue ramp (KOF96's handler $4B5E8 changes only the states and
  the box for the MAX, no palette); KOF96's own Kaiser Wave in our emulator and Rugal's KOF98 one (every charge level)
  are blue too. A purple recolour of $9D would be a new feature (not built).

## Robert (5 presses) — Bruno's arbitration sheet 2026-10-09
Decisions set `robert-arb` (brawler-lab/arbitrage.html?f=robert); animation numbers = Robert's KOF98 animation table (his
dictionary: brawler-lab/anims.html?f=robert). Archetype fast: 5 presses (4 links + the neutral last hit).
- Chain A x5: $51 (far A) > $51 > $5B (far C) > $5F (close D) > $64 (the C+D body toss = the neutral last hit).
- Last hit + forward: $E5 (forward A, Kouryuu Koukyaku Geri). + up (the launcher): $D4, the kick of MAX 236236B played
  as a normal (game.json roster.robert.moves atk_cd_close = "$D4": export96 `slots`). + down: $63 (crouch D sweep).
  + back: the throw $E0.
- Blitz: forward,forward + A = $1E7 = EX 624D (Hien Senpuu Kyaku EX, from the ROM). down,down / up,up / down,up + A: empty.
- C specials (1 drive chunk, invincible): C (neutral, also the breaker) = $84 = 623A Ryuuga; forward + C = 624D ($8C > $8E >
  $90, as before); down + C = 623C ($85 > $87 > $88 > $8A, as before); C in any other direction = the neutral's (623A).
- Air: jump + A = $61 (jump D); jump + down + A = $57 (jump B, flinch). down,down + A in the air (Bruno: "the hien ryujin
  kyaku move done with D in KOF98") = air 214D Hien Ryuujin Kyaku, read from the ROM (Kim's air_specials ddA mechanism):
  the hang (146), the dive at 7.07 px a frame forward and down (KOF98 $3662: speed 10 at angle $E0), the landing slide
  (150); blocked it would bounce off (151).
- Hold: hit = $55 (close B); finisher (the throw-out) = $5E (crouch C). Throws forward / back = $E0.
- Fury (D) = 23624C Ryuuko Ranbu as before ($B1 > $B2 > $B5 > $B8 > $B9); MAX (down + D, low life) = its MAX, as before.
- Size: unchanged.

### Round 2, 2026-10-09 (Bruno changed the sheet; supersedes round 1 above where they differ)
Decisions set `robert-arb` again (round 1 kept as `robert-arb.round1-2026-10-09.json`). Unchanged: press 1 $51, press 4 $5F,
press 5 $64, + down $63, + back the throw $E0, up,up + A empty, the air, the hold, the throws, the fury, the MAX, the size.
- Chain A x5: $51 (far A) > $5B (far C) > $D4 (the kick of MAX 236236B, now a chain link: moves atk_cd_close = "$D4")
  > $5F (close D) > $64 (body toss = the neutral last hit).
- Last hit + forward: $E5 (forward A, Kouryuu Koukyaku Geri), a hop. Bruno: "consider Robert mid-air while executing it,
  it's a hopping motion. In general ALL hopping motions should be considered in-air." (see "Hops are in the air" below).
- Last hit + up (the launcher): $67, KOF98 state 119, unnamed in the tables (no input of the game we captured plays it):
  8 steps, one hit on step 5, played as a normal (moves atk_ab_far = "$67", export96 `slots`).
- Blitz: forward,forward + A = $8E = 624D Hien Senpuu Kyaku ($8C > $8E > $90, the ROM program; was forward + C);
  down,down + A = $1E7 = EX 624D (moved from forward,forward); down,up + A = $9C = 623D Ryuu Zanshou ($9A > $9C > $9E,
  the ROM program); up,up + A empty.
- C specials: C (neutral, also the breaker) = $85 = 623C Ryuuga ($85 > $87 > $88 > $8A); forward + C = $1EF = EX 646D Gen'ei
  Kyaku ($1EE > $1EF > $1F1 > $1F2 > $1F3, the ROM program; $1EF is shared by EX 646B / D, the D one is the longer kick
  barrage); down + C = $9F, KOF98's "426B Ryuuren Gen'ei Kyaku" of the close-range capture: the normal-move code plays it
  (handler $1E72A, the far B's), not a special program, so it is an animation special (anim_specials "$9F": "kof", its
  four hits with KOF's own box reactions, its +94 px travel from the animation); C in any other direction = the neutral's.

### Hops are in the air (Bruno 2026-10-09, every fighter)
The engine's "in the air" is the height: y > 0. A hop's height is data: KOF98 / KOF99's command normals that go through
several states were captured with their height per frame (tools/kof96/capture/cmdnormals.py -> cmdnormals_<game>.json,
export96.cmd_frames -> bstep_t.hy), and a normal's step sets y = hy (fighter.c step_move). So on every frame of a hop whose
height is above 0 the fighter already is airborne everywhere the engine asks: hit there it takes the air reaction (sent up
and falling, juggle-able: react), it cannot be held or thrown (grabbable, chain_throw: !y), a low box misses it by height,
the ground specials do not cancel out of it (y == 0 rule). Checked: no captured single-state command normal leaves the
floor, so no hop is missing its height. Moves in the roster with a hop: Robert forward + A ($E5, up to 14 px on 15 of its
20 steps), Billy forward + A (14 px) and forward + B (1 px), Mai forward + B (14 px), K' forward + B (14 px), and WHP
Cheng Fu's far D / body toss (14 px). The take-off and landing frames (height 0) stay on the ground, as in the game.
New in round 2: a ROM special's catch box (and a captured special's grab reach) no longer takes a victim in the air by its
own move (a jump or a hop; fighter.c combat); a reeling or juggled victim stays catchable as before.

## Engine features (generic, data driven: set by the importers, off by default)

- **World-anchored (placed) effects** — `bproj_t.air` bit 2 (`PJ_PLACED`, fighter.h; note 20261011-205309-5d29, Kyo's
  dragon punch fires: "they look tied to Kyo, in the real game they are spawned independently on the screen"). KOF's
  object code calls $24A02 (copy the owner's x / y / z + the object's +$D2 / +$D4 offset) either on every frame (pinned:
  it follows him, `follow` bit 1 as before) or only as it starts, before its first resume ($3DD86, Kyo's 623A / 623C
  fires): then it is PLACED once and stays where it was born. `handlers98.placed_once` reads that from the object's own
  code (the model: $24A02 on a frame after its first or not); such an object exports `follow` 0 + `placed`. The brawler
  places it at its owner's x and height as they are after his frame (fighter.c proj_update's first run, KOF's object
  running after its owner), then it plays its rows there and ends at its last row; it is no shot (KOF sets no +$E1 bit 5).
  Measured in our emulator (tools/kof96/capture/romspecials98.trace, /data/tmp/kyo_fire): KOF98 623C fire 1 at Kyo's
  (x, 8), fire 2 at his (x, 69) while he rises to 79 and lands, 623A at 6 / 30; the brawler now the same heights and
  constant places (tools/brawler/kyo_round3_proof.py fire). Changed across the roster (follow 35 -> 0, rows identical):
  Kyo 623A / 623C fires (states 245 / 246) and EX 236A's first flame (247), Yamazaki 623B / 623D (157 / 160), Yashiro
  426A (255), Goenitz 214B / 214D (142), Geese 1632143C (182 / 183), Mr. Big 23623C (138 / 141: no rows, nothing drawn);
  every other object byte-identical. An object that ends in place on its owner's P_FXOFF (`follow` 64) keeps the pin.

- **Pinned effect holds with its owner's hit-stop** — `bproj_t.follow` bit 128 (`FL_HSTOP`, fighter.h; note
  20261011-112545-5d29, Haohmaru's Tenha Fuujinzan: "the circling effect is now desynchronized from Haohmaru"). An effect
  pinned to its owner (follow bit 1) with this bit does not advance on the frames its owner holds in hit-stop
  (`fighter_t.hs_now`, set by fighter_update's hit-stop hold; fighter.c proj_update returns before its row / timer
  move): it stays on its row, in its place, so it stays in step with his body to the end. Unset, the effect animates on
  through his hit-stop (KOF / Kizuna / Double Dragon: unchanged). Set by `export_ss2.hold_pinned` on every SS2 object
  pinned to its owner (Tenha's wind, the Kogetsuzan crescent, Genjuro's card wind and second-phase cards, Kuroko's
  ghost). Another importer sets it the same way when its source game holds its pinned objects with the body. Proof:
  tools/samsho2/hstop_proof.py.

- **Projectile hit budget** — `game.json roster[].proj_hits` {special input: {`max_hits`, `hits_per_target`[, `rehit`][,
  `away`]}} (note 20261011-134041-5d29, Krauser's Kaiser Wave: "maximum 10 hits before disappearing, but it can hit every
  character twice"). The special's travelling objects (kind 1, not pinned) pierce: each enemy takes at most
  `hits_per_target` hits (1-4; the special's damage split over them, a reel R_HEAVY until the last, which plays the
  object's own reaction), the object freezes `rehit` frames after each hit (default handlers98.PROJ_REHIT = 7) and is then
  re-armed for every enemy it is not done with, flying on; after `max_hits` hits in all (1-15; 0 = no cap) it ends where
  the last one landed (its end rows; the enemies it did not reach are not hit); `away` (default true) sends its victims
  away from the thrower. A MAX special takes its DM's entry unless it has its own (`"MAX 641236C"`). Engine: `bproj_t.vhits`
  bits 0-3 = hits per target, bits 4-7 = the cap (fighter.h PJ_VPER / PJ_VMAX: packed, no struct change, the pack format
  stays 1); `fighter_t.vcnt` (2 bits a victim) / `vdone` / `vtot` (hits in all); fighter.c strike / proj_end. Unset
  (vhits 0): every other projectile as before, its first hit ends it (proof: the exported tables differ only in Krauser's
  two Kaiser Waves). Krauser: `{"641236C": {"max_hits": 10, "hits_per_target": 2}}` (his fury and MAX; was the MAX only,
  4 a victim, no cap). Exporter: export_bm.proj_hits (any game's projectiles go through projectile_c). Proof:
  tools/brawler/hitbudget_proof.py (crowd of 6 + single dummy, fury + MAX; recipe scenarios.json 20261011-134041-5d29).

- **A special whose victim stays juggle-able** — `game.json roster[].juggle` [special inputs] (note 20261011-201837-5d29,
  Kyo's down,down + A 623A: "it looks like there is a flag that prevents juggling"). The flag was KOF's own juggle rule:
  box_react packs a reaction without the hurt-kept bit 8 when KOF's reaction state has no $0200 hurt box (623A's launch,
  states 285 / 287: handlers98.react_hurt), so fighter.c kof_react leaves kmode without KM_HURT and combat skips the
  victim until it is down. Listed here, every body hit of the special's ROM program has bit 8 set on both packed nibbles
  (export_bm rom_c `hy`; an R_* nibble only, RK_HIGH / the hold's 0x80 / source reactions untouched): the victim flies
  the same arc with LAUNCH_BOX and takes later hits, the juggle cap (gchain.juggle_cap) still counting. Unset: the
  exported tables are byte-identical (checked: bm_spec.c differs only in kyo_sp0's rows). Its travelling objects keep
  their own reactions. Set: Kyo `623A` (its own second hit now lands too: 2 hits, the victim up to ~146 px instead of
  114; then C / forward + C / the fury cancelled into it hit him in the air). Recipe scenarios.json 20261011-201837-5d29.

- **A move that leaves the fighter airborne with his air attack** — `game.json roster[].keeps_air_attack` [special
  inputs] (Bruno 2026-10-11, decisions set open-2026-10-11 `hanzo-air-shuriken`: "after the shuriken Blitz, Hanzo is
  still in the air and he can still execute a regular air attack"). The special's `bspec_t.sflags` SF_AIRATK (64,
  export_bm vl_c). Once its program is in the part that waits for the landing (the part it resumes at opens on "landed ->
  go on", a handlers ('land', 'next') entry: fighter.c `air_free`), A plays the jump's attack (down + A its down attack,
  roster `air`) at the move's velocity, once, and he lands as from a jump; no A: the move lands as before. Unset: every
  other special as before (the exported tables differ only in that special's sflags). An SS2 multi-button input in the
  list ('j.4123S') names each of its button versions (export_bm same_special). Set: Hanzo SS2 `j.4123AB` (the A+B
  version, the Assembly's S-010 = what the export played for j.4123S), whose air shuriken is his air Blitz since
  2026-10-11 (`air_specials` `ddA`, was `dC` j.4123S: jump + down + C is empty again; the Assembly answer `air_bz_dd`
  S-010 in the decisions store). Export: air_specials values are among the inputs export_ss2 exports as button versions
  (arb_compile links an air Blitz piece as its version input, which did not export before). Check:
  /data/tmp/hanzo_go (airblitz.py: shuriken from down,down + A, A in the recoil -> atk_cd_jump hits 24 like a plain jump
  attack, LAND -> IDLE; recipe scenarios.json `dec-hanzo-air-shuriken`).

- **A sequence: several pieces back to back on one slot** — a Blitz or air special slot whose value is a LIST of inputs
  (`game.json roster[].blitz.<k>` / `air_specials.<key>` = `["j.4123A", "j.4123B", "j.4123AB"]`; Bruno 2026-10-11, notes
  20261011-164455-5d29 + 20261011-164801-5d29: "Hanzo throws all three shurikens in turn, first the A, then the B, then
  the A+B"). Export (export_bm `sequences`): each piece is a copy of its bank special, appended at the END of the pool
  (every other pool index as without it), consecutive; every piece but the last carries `bspec_t.sflags` SF_SEQ (128:
  the last free bit, append-only like SF_AIRATK: lab_pack feature `sf-seq`, pack format 1 unchanged); the slot points at
  the first (bm_air entry / gblitz_rom: build_tables reads the head from chainlab.json pool `seq` / `seq_i`). Engine
  (fighter.c `seq_next`): a SF_SEQ special hands over to specials[its index + 1], same role, at its end (prog_end, a
  script's end) or, in the air, as soon as its program waits for its landing (`land_wait`: its recovery fall), so the
  pieces play without landing; the next piece's first frame plays in that frame. Each piece is the special as it plays
  alone: its variant row (Hanzo: vdef 0 / 1 / 2), its projectile (one each: they fly together), its voices, its knobs;
  the last keeps its own flags (Hanzo's j.4123AB: SF_AIRATK, the jump attack in its recoil). Its speed: `retime` by the
  piece's input, which now applies to EVERY pool entry of that input (build_tables retime_tables). Unset (no list):
  tables byte-identical (table diff 0.10.56 -> this build: only hanzo_ss2's rows + the SF enum + the retime rows
  renumbered). The Assembly shows it already (several pieces on a slot: "A → B → C", "+ add after"); arb_compile links
  several S- ids on a Blitz / air special slot as the list (else unresolved, as before). Not yet: the C special slots,
  the fury (their maps are by input: spmap / spec_map would read the head the way blitz_rows does). Set: Hanzo SS2 `ddA`
  [j.4123A, j.4123B, j.4123AB] (S-008, S-009, S-010; Assembly answer `air_bz_dd` in the decisions store, backup
  `.bak-20261011-triple`), each with its startup halved (`retime` ["0.5x", null, null]: 15 -> 8 source frames).
  Measured in our emulator (/data/tmp/hanzo_triple, triple.py): the first shuriken 9 frames after the move starts (was
  16), the pieces at frames 0 / 22 / 42, all at height 30 (no landing between), paths A steepest (lands +32 px) / B
  (+36) / A+B flattest (+46); vs Ryo at 50 px: 3 hits of 24, then A in the A+B's recoil -> atk_cd_jump knocks down,
  LAND -> IDLE; without A it lands as before. regress: bleed True / True, facing traces = 0.10.56's for every fighter
  (regress.py now presses coin / START / A again when the attract swallowed the coin: a one-frame window, 0.10.56 at
  2599 frames, this build's boot a frame later at 2600).

- **A sequence played together: the pieces' projectiles at once** — `game.json roster[].together` = the slot labels of
  sequences whose pieces play TOGETHER (`["air_specials.ddA"]`; Bruno 2026-10-11, note 20261011-164455-5d29 reopened on
  0.10.57: "throw three shurikens at once, the A, the B and the A+B, at the same time"). Export only (export_bm
  `together`; no engine flag, no new op, fighter.c / bm_chars.h untouched, pack format 1 unchanged): the slot gets ONE
  pool entry, the first piece (its animation, voices, retime, flags), whose k-th object spawn also spawns every other
  piece's k-th object, each the object of that piece's own variant row, in the same frame. Its program is a copy: each
  P_SPAWN becomes a P_JMP to a tail before the P_END (its own spawn, the others', a P_JMP back), its P_END moved last
  with a P_JMP to it in its place (every other op keeps its index; main.c pj_measure still scans to the P_END); the
  others' objects are appended to its objects, their P_SPAWN index taken back by its own row's offset (robj[a + var *
  vobj]). Every piece must be a program special with as many spawns as the first (asserted). The other pieces are not in
  the pool; `retime` / `keeps_air_attack` name the first piece's input. Without `together` a list stays the back-to-back
  sequence above (SF_SEQ). Unset: tables byte-identical (diff 0.10.57 -> this build: hanzo_ss2's rows, its knob / damage
  tier rows, the retime rows renumbered). Pool cost: one projectile entity per piece (NPJ 8: Hanzo's three + their floor
  phase in the same entities; a hit mark needs 2 free entities, else none is drawn). Set: Hanzo SS2 `ddA` [j.4123A,
  j.4123B, j.4123AB] together, `retime` j.4123A "0.5x" startup, `keeps_air_attack` j.4123A; Assembly answer `air_bz_dd`
  unchanged (S-008 S-009 S-010: the list). Measured in our emulator (/data/tmp/hanzo_three, three.py): the three
  shurikens on the same frame, 9 frames after the move starts, from the same point; paths A steepest (floor +32 px) / B
  (+36) / A+B flattest (+46), as 0.10.57's; vs Ryo at 50 px: 3 hits of 24 on one frame; A in the recoil -> atk_cd_jump,
  LAND -> IDLE; without A it lands (65 frames). regress bleed True / True, facing traces = 0.10.57's for every fighter.
- **A pressed sequence (a rekka): each next piece on the slot's button again** — `game.json roster[].seq_press` lists
  the sequences (`"blitz.ff"`, `"air_specials.ddA"`) whose next piece waits for the press (Bruno 2026-10-11, note
  20261011-175657-5d29: "the forward,forward A Blitz will be the classic move, quarter circle forward + A in the game,
  and after that pressing A again does the follow-ups"). Export (export_bm `sequences`): every piece but the last
  carries ONE follow-up link, the slot's button (a Blitz / an `A` entry: IN_A; a `C` entry: IN_C), any stick, its whole
  play as the window (`bslink_t` {0, 0, LK_IN, button, LK_ANY, 0, 0, 0xFFFF}, nparts 0); a piece with follow-ups of
  its own is refused. Engine (fighter.c `special_input`, `seq_wait`, `seq_next`): the press inside the window arms it
  (plink bit 0, kept to the piece's end; cleared as each piece starts, so every piece needs its own press; a press in the hit-stop counts);
  armed, the next piece starts at the first step of the piece's follow-up point it enters (KOF's $0080 event step,
  PF_EVENT: where KOF98's handler switches from Aragami to Konokizu, from Konokizu to Yanosabi), else at its end; not
  armed, the move ends with this piece (the rest not played). A sequence without `seq_press` (no link) plays back to
  back as before: tables byte-identical (Hanzo's air shurikens unchanged). The pieces: a PART of a ROM special alone
  (handlers98 `'<input>>N'`: the part of its handler that starts state N, `part_entry`: the handler or one of its
  branch targets, decoded with its follow-up checks reading no command (`nofollow`) and its hit kind the handler set
  before it). Set: Kyo `blitz.ff` [236A>156 (114 Shiki Aragami), 236A>158 (128 Shiki Konokizu), 236A>162 (127 Shiki
  Yanosabi)] (S-009 / S-010 / S-011; Assembly answer `bz_ff` with flags {"press": true}).
- **The down-forward finisher** — `finishers.df_move` (2026-10-11, Kyo's note 20261011-175124-5d29: "the diagonal
  finisher is diagonal + D, the double sweep"): the last link + down-forward + A plays that move as a trip (routes.py
  chain_tree `dfA`, RI_DFA; the Lab's lab.js the same); absent: none (down-forward + A plays the forward finisher, as
  before). The Assembly's `fin_df` compiles to it.

## The arbitration sheet compiler, piece ids and the Workshop

Moved to **docs/character_lab.md** (2026-10-10). `arb_compile.py` still appends each shipped "sheet round" here.

## Hanzo (SS2): moved

His Character Lab round (the breaker warp, the pieces, the "decoded, not imported" list) is in **docs/character_lab.md**
"Hanzo (SS2) — Character Lab".

### HANZO: sheet round 2026-10-10 (tools/brawler/arb_compile.py, decisions set `hanzo_ss2-arb`, build 0.10.29)
Compiled from the sheet without an agent: 4 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- a2 (A press 2): $E6 -> chain.links[1] = "atk_a_close" — linked, class a: its own move
- a3 (A press 3): $15C -> chain.links[2] = "atk_cd_close" — linked, class a: spare name: moves "atk_cd_close": "$15C"
- a4 (A press 4): $FC -> chain.links[3] = "atk_b_far" — linked, class a: its own move
- a5 (A press 5): $114 -> finishers.neutral = "atk_ab_far" — linked, class a: spare name: moves "atk_ab_far": "$114"

### HANZO: sheet round 2026-10-10 (tools/brawler/arb_compile.py, decisions set `hanzo_ss2-arb`, build 0.10.30)
Compiled from the sheet without an agent: 4 slot(s) linked, 1 unresolved (listed for an agent, nothing guessed); slots whose pick = now not listed.
- a3 (A press 3): $FC -> chain.links[2] = "atk_b_far" — linked, class a: its own move
- a4 (A press 4): $114 -> chain.links[3] = "atk_ab_far" — linked, class a: roster moves
- fin_fwd (last hit + forward): $116 -> finishers.forward = "body_toss" — linked, class a: its own move
- fin_up (last hit + up): $15D -> finishers.up = "atk_ab_close" — linked, class a: spare name: moves "atk_ab_close": "$15D"
- presses (chain length): $4 — UNRESOLVED: chain length 4 (now 5, archetype fast): an agent
- chain timing: atk_a_far 4/1/16 (now 4/1/15, source 4/1/15) (roster chain.hitstop / retime, the build checked)

### HANZO: sheet round 2026-10-10 (tools/brawler/arb_compile.py, decisions set `hanzo_ss2-arb`, build 0.10.31)
Compiled from the sheet without an agent: 2 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- presses (chain length): $4 -> chain.length = 4 — linked, class a: chain length 5 -> 4
- bz_dd (down,down + A): S-007 -> blitz.dd = "WFT" — linked, class b: S-007 Ninpou Tenma Fukumetsu (rage) (registry)
- chain timing: atk_a_far 8/1/16 (now 4/1/16, source 4/1/15) (roster chain.hitstop / retime, the build checked)

### HANZO: sheet round 2026-10-10 (tools/brawler/arb_compile.py, decisions set `hanzo_ss2-arb`, build 0.10.32)
Compiled from the sheet without an agent: 0 slot(s) linked, 1 unresolved (listed for an agent, nothing guessed); slots whose pick = now not listed.
- bz_dd (down,down + A): $15A — UNRESOLVED: $15A has no move name and no known reaction (an animation special needs one: library anim_special)
- chain timing: hit-stops 57 8 10 12 (roster chain.hitstop / retime, the build checked)

### HANZO: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `hanzo_ss2-arb`, build 0.10.34)
Compiled from the sheet without an agent: 3 slot(s) linked, 1 unresolved (listed for an agent, nothing guessed); slots whose pick = now not listed.
- fin_up (last hit + up): $10F -> finishers.up = "atk_cd_crouch" — linked, class a: spare name: moves "atk_cd_crouch": "$10F"
- fin_down (last hit + down): $F5 -> finishers.down_move = "atk_ab_crouch" — linked, class a: spare name: moves "atk_ab_crouch": "$F5"
- air_a (jump + A): $11C -> air.forward + air.straight (+ moves atk_cd_jump_diag = $11C) = "atk_cd_jump" — linked, class a: its own move
- bz_dd (down,down + A): $15A — UNRESOLVED: $15A has no move name and no known reaction (an animation special needs one: library anim_special)
- chain timing: hit-stops 6 8 10 12 (roster chain.hitstop / retime, the build checked)

### HAOHMARU: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `haohmaru-arb`, build 0.10.37)
Compiled from the sheet without an agent: 3 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- a1 (A press 1): $FA -> chain.links[0] = "atk_b_close" — linked, class a: its own move
- a2 (A press 2): $FC -> chain.links[1] = "atk_b_far" — linked, class a: its own move
- a3 (A press 3): $114 -> finishers.neutral = "atk_cd_close" — linked, class a: spare name: moves "atk_cd_close": "$114"
- chain timing: hit-stops 6 9 10 (roster chain.hitstop / retime, the build checked)

### HAOHMARU: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `haohmaru-arb`, build 0.10.43)
Compiled from the sheet without an agent: 1 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- fin_down (last hit + down): $160 -> finishers.down_move = "atk_ab_close" — linked, class a: spare name: moves "atk_ab_close": "$160"

### HAOHMARU: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `haohmaru-arb`, build 0.10.45)
Compiled from the sheet without an agent: 1 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- fin_up (last hit + up): $FC -> finishers.up = "atk_b_far" — linked, class a: its own move

### HAOHMARU: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `haohmaru-arb`, build 0.10.54)
Compiled from the sheet without an agent: 1 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- fin_up (last hit + up): $118 -> finishers.up = "atk_cd_crouch" — linked, class a: spare name: moves "atk_cd_crouch": "$118"

### KYO: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `kyo-arb`, build 0.10.57)
Compiled from the sheet without an agent: 14 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- a1 (A press 1): $50 -> finishers.neutral = "atk_a_close" — linked, class a: its own move
- a2 (A press 2): $5A -> finishers.neutral = "atk_c_close" — linked, class a: its own move
- a3 (A press 3): $EC -> finishers.neutral = "cmd_fwd_b" — linked, class a: its own move
- a4 (A press 4): $60 -> finishers.neutral = "atk_d_far" — linked, class a: its own move
- fin_up (last hit + up): $5F -> finishers.up = "atk_d_close" — linked, class a: its own move
- fin_down (last hit + down): $63 -> finishers.down_move = "atk_d_crouch" — linked, class a: its own move
- fin_df (last hit + down-forward): $EB -> finishers.df_move = "cmd_df_d" — linked, class a: its own move
- bz_ff (forward,forward + A): S-009 then S-010 then S-011 -> blitz.ff = ["236A>156", "236A>158", "236A>162"] — linked, class b: a sequence, each next piece on the button again: S-009 236A>156 then S-010 236A>158 then S-011 236A>162
- bz_dd (down,down + A): S-013 -> blitz.dd = "623A" — linked, class b: S-013 623A (registry)
- bz_uu (up,up + A): S-004 -> blitz.uu = "421B" — linked, class b: S-004 421B (registry)
- sp_c (C): S-005 -> specials.D = "623C" — linked, class b: S-005 623C (registry)
- sp_dc (down + C): S-012 -> specials.dD = "236D" — linked, class b: S-012 236D (registry)
- air_a (jump + A): $61 -> air.forward + air.straight = "atk_d_jump" — linked, class a: its own move
- air_da (jump + down + A): $EE -> air.down (+ moves atk_ab_jump_diag = $EE) = "atk_ab_jump" — linked, class a: spare name: moves "atk_ab_jump": "$EE" (an air attack)

### KYO: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `kyo-arb`, build 0.10.57)
Compiled from the sheet without an agent: 14 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- a1 (A press 1): $50 -> chain.links[0] = "atk_a_close" — linked, class a: its own move
- a2 (A press 2): $5A -> chain.links[1] = "atk_c_close" — linked, class a: its own move
- a3 (A press 3): $EC -> chain.links[2] = "cmd_fwd_b" — linked, class a: its own move
- a4 (A press 4): $60 -> finishers.neutral = "atk_d_far" — linked, class a: its own move
- fin_up (last hit + up): $5F -> finishers.up = "atk_d_close" — linked, class a: its own move
- fin_down (last hit + down): $63 -> finishers.down_move = "atk_d_crouch" — linked, class a: its own move
- fin_df (last hit + down-forward): $EB -> finishers.df_move = "cmd_df_d" — linked, class a: its own move
- bz_ff (forward,forward + A): S-009 then S-010 then S-011 -> blitz.ff = ["236A>156", "236A>158", "236A>162"] — linked, class b: a sequence, each next piece on the button again: S-009 236A>156 then S-010 236A>158 then S-011 236A>162
- bz_dd (down,down + A): S-013 -> blitz.dd = "623A" — linked, class b: S-013 623A (registry)
- bz_uu (up,up + A): S-004 -> blitz.uu = "421B" — linked, class b: S-004 421B (registry)
- sp_c (C): S-005 -> specials.D = "623C" — linked, class b: S-005 623C (registry)
- sp_dc (down + C): S-012 -> specials.dD = "236D" — linked, class b: S-012 236D (registry)
- air_a (jump + A): $61 -> air.forward + air.straight = "atk_d_jump" — linked, class a: its own move
- air_da (jump + down + A): $EE -> air.down (+ moves atk_ab_jump_diag = $EE) = "atk_ab_jump" — linked, class a: spare name: moves "atk_ab_jump": "$EE" (an air attack)

### KYO: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `kyo-arb`, build 0.10.60)
Compiled from the sheet without an agent: 0 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- knobs: {"sp_fc": {"S-007": {"rise": 2.83, "travel": 8}}} (roster[].knobs, measured by knob_check)
- (note 20261011-201729-5d29, "divide the total height by two and reduce the total X distance by 20%": measured in our emulator, forward + C alone: peak 87.3 -> 44.1 px (0.505; the height goes with the rise squared, so rise 4 -> 2.83 = 4 / sqrt 2), travel 189.2 -> 151.2 px (0.799, travel 10 -> 8); recipe scenarios.json 20261011-201729-5d29)

### RUGAL: sheet 2026-10-11 (game.json directly: Rugal is not a Lab fighter, no Assembly answers / arb_pieces; build 0.10.61+)
- note 20261011-204652-5d29: finishers neutral = forward + B ($9F cmd_fwd_b, 2 hits), forward = far C, down = far D (the
  slam kept), up = C+D (body_toss); Blitz down,down + A = 624A God Press (KOF98's program; a rush that catches and
  carries the victim to the screen edge, the stage.wall rule, and slams him into it: in the brawler the wall is the
  screen's edge); up,up + A = none (A plays his normal); forward,forward + A = his dash attack, as before. 624A also
  stays his up + A hold throw (throws.extra.u).
- note 20261011-204335-5d29: fury_final_area front 143 / back 44 / depth 24, blows "all" (new field value: every blow of
  the victim lists, not only the last): the red column (drawn -4..+103 px from Rugal) knocks down every opponent around
  it; the MAX's two columns each do. Proof /data/tmp/rugal (proof.py): fury vs 4 clones = the caught Ryo + the two in
  reach hit, the one behind and the one 40 px deeper not; MAX = the second column hits the one now in front.
### KYO: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `kyo-arb`, build 0.10.61)
Compiled from the sheet without an agent: 0 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- knobs: {"sp_fc": {"S-007": {"rise": 2.83}}} (roster[].knobs, measured by knob_check)
- (notes 20261011-201729-5d29 reopened + 20261011-204904-5d29, "keep the half height as we have now, but reset the X distance to 100%": travel knob back to its default 10 (override dropped), rise stays 2.83; measured in our emulator, forward + C alone (dummy off): peak 44.1 px, travel 188.1 px (189.2 before round 2); recipes scenarios.json 20261011-201729-5d29 / 20261011-204904-5d29)

### KYO: sheet round 2026-10-11 (tools/brawler/arb_compile.py, decisions set `kyo-arb`, build 0.10.61)
Compiled from the sheet without an agent: 1 slot(s) linked, 0 unresolved; slots whose pick = now not listed.
- a1 (A press 1): $51 -> chain.links[0] = "atk_a_far" — linked, class a: its own move
- (note 20261011-205823-5d29, "replace the close A by the far A": chain = far A, close C, close forward B, far D; the
  other picks kept; answers backed up as kyo-arb.json.bak-20261011-round4; arb_compile's slot check: far A starts and
  hits the dummy; recipe scenarios.json 20261011-205823-5d29)
