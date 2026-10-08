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

### Terry's chain — Bruno 2026-10-08 (replaces the first-pass pick above)
- Chain: far A > far A > close C (2 hits) > close D (close D = the neutral last hit). 4 links, 5 hits.
- Last hit with forward: forward + A (2 hits). With down: crouch D sweep. With up: down-forward + C.
- Page feedback: the clip-per-move chain view needs too much scrolling on a phone → chains must render as ONE compact
  row (small looping clips with arrows), the whole sequence on one screen.
- Breaker (C or A+B while being hit) = ALWAYS the fighter's neutral C special, whatever the stick says (rule for every
  fighter). Terry: Rising Tackle.
- Fury = Power Geyser, MAX = the triple geyser. Super throw: dropped (forward / back + C in the hold = the normal throw).
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
- Size: 0.92 of today's (115 -> ~106 px; Terry 100). Kept against the official-height 0.86 (docs/brawler_heights.md): Bruno, "Kizuna has this big SNK sprites feel anyways".

### Kim — queued changes (Bruno 2026-10-09; BUILT on gold/kim-q1: $53 reset +14, $5D, $96 retimed 72 -> 40 f)
- forward + C: $101 -> $53, keeping the RESET behaviour (no eject, Kim recovers with frame advantage; Bruno: yes).
- chain: the second A $56 -> $5D.
- $96 (the triple kick, chain link 4): keep the shape of each of its three kicks, but play them at the pace of three FAST
  attacks (retime: short startup / recovery per kick), each with a STRONG impact sound and the regular push back.

### Kim — Bruno's 0.9.2 notes (built in 0.9.3)
- Last hit + forward = $9A (the launcher), + up = $54 (swapped).
- down,down + A = Hienzan ([2]8C); $5C dropped ("we don't need it"). down,up + A stays Hienzan too.
