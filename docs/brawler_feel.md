# Brawler: the feel revamp (chain system and beyond)

Bruno's direction, 2026-10-07. Goal: revamp the whole chain system around "what makes a fun experience playing a
character", run without babysitting. This file holds the agreed principles; each section separates **Bruno's words**
from my **proposals** (proposals are not requirements until he agrees).

## 1. The first hit carries the feel

**Bruno:** if the first jab is snappy, visually pleasing and has a good hit box, the character feels good. References:
Cody (Final Fight), Axel (Streets of Rage 2).

## 2. Speed vs. reward: the archetype trade-off

**Bruno:** a character with a slow starter jab gets shorter chains overall but more damage per hit. References: Haggar
(Final Fight), Max (SOR2). In contrast to Cody / Axel: fast starter, longer chains.

## 3. Every animation stands on its own

**Bruno:** every animation has to be independently visually pleasing. No tolerance for sub-par animations: nothing that
looks unfinished, out of place, etc.

## 4. Variety

**Bruno:** variety in what is seen, and variety in some of the commands that need to be input.

## 5. Consistency (within the one game)

**Bruno:** sounds like the opposite of variety, but within the same game all characters need some consistency: timings,
base damage, animation style, character height. Reference: KOF94 nailed the merge of Art of Fighting 2's and Fatal Fury
Special's radically different graphics; same goes for unifying the gameplay.

## 6. Retiming: the unifying technique

**Bruno:** the game data is fed animation data as resolved in the source games, but we must be able to "adapt" certain
aspects almost dynamically. Every move is startup / active / recovery; the animation system must stretch any of the
three at will: a 10f / 12f / 10f move must be scalable to any A / B / C frames (as long as it creates no artifacts).
That is our unifying technique.

**Proposals (mine, to agree):**
- Phases come from the data: startup = press to the first frame with an attack box; active = frames with an attack box;
  recovery = the rest to the first cancellable / neutral frame. Multi-hit moves have several active windows (each
  with its own gap): treat "active" as a list of windows, each retimed.
- Retime = remap each phase's source frames onto target frames: the drawings keep their order, each drawing's
  duration scales (fixed point); motion scales with it so each phase's total travel is unchanged (a stretched lunge
  covers the same distance, slower), and hit boxes, effect spawns, sounds and voice cues move with their drawing.
- Artifact rules: compressing below one frame per drawing drops drawings (pick which: keep the key poses, contact
  frame never dropped); stretching far holds drawings long (a stutter); a ratio bound per phase (e.g. 0.5x-2x) flags
  the move for a hand look instead of shipping it.
- What doesn't scale with the move: hit-stop, the victim's reaction, the global timing of the engine.
- ROM-decoded programs (KOF handlers with their own frame counters, SS2 timers) need their counters scaled too: the
  exporter does it per program at build time, not the engine at run time.

## 7. Chains are authored, not imported

**Bruno:** don't rely too much on the source game's chaining system. A great chain combo = each individual piece is very
appealing on its own, and put together they make a great sequence. It doesn't have to be what the original game did —
most of these games had no chain combos at all (Kizuna is the exception).

**Proposals (mine, to agree):**
- The source games give a *library of pieces* (every normal, command normal, special, with its drawings, boxes,
  sounds); the chain is a sequence *we compose* from that library per fighter.
- A piece qualifies on its own merit first (principle 3: visually complete, readable contact frame, good box).
- A sequence is judged on flow between pieces: the end pose of one leads into the start pose of the next (no pop),
  spacing keeps the victim in reach, rhythm and intensity rise toward the finisher, some variety of height / limb.
- Composition is proposed by me from measurable criteria and judged by Bruno visually (tap-to-judge, outcome-named
  buttons), not hand-tuned frame by frame.

## 8. Bread and butter first, specials as side branches

**Bruno:** we could be creative and use animations of special moves in side-chain combos, but the bread and butter must
be regular hits players often see, so they feel at home with these moves. Visual appeal drives the selection of each
piece. Every piece scalable (slow down / speed up) to fit a frame-data adjustment.

## 8b. Every chain serves a purpose

**Bruno:** good chains serve a purpose. Some start facing one way and end facing the other, to deal with enemies both in
front and behind. Some include a throw: in Final Fight, punch, punch, then back + punch makes the third action a throw
backwards; that helps escape difficult situations, because the player is usually invincible during the throw animation.

**Proposals (mine, to agree):**
- Each fighter's chain set covers a small list of *purposes*, and each branch is tagged with one: damage (the plain
  string), crowd clear (wide / multi-hit finisher), turn-around (ends facing back, or hits behind), escape (a throw or
  move with invincibility, e.g. back + A at link 3 = throw backwards), reposition (carries the victim / the player).
- The direction held at a link picks the branch (neutral = damage finisher, back = throw backwards / turn-around,
  forward = push or launcher), the same scheme for every fighter (consistency) with each fighter's own pieces (variety).
- The throw branch grants invincibility for its whole animation (as the existing fury rule does), and its thrown body
  knocks down enemies it meets (spawn.body).
- The Lab tool shows which purposes a fighter's chains cover, so gaps are visible.

## 8c. The recipe, archetypes, juggles (Bruno, 2026-10-07, thinking aloud)

**Bruno:**
- The revamp is about finding the magic recipe for a good beat 'em up: a blend of good combos, good eye candy for the
  characters, something fun and challenging, with depth in the routes, without becoming too crazy like Killer Instinct
  (the game).
- Archetypes: a character doesn't have to cover every purpose; what matters is coherence within one character. A very
  fast one: lower damage, faster startup on every move, maybe faster movement too. A bigger one, e.g. Krauser, is a
  good candidate for a wrestler type: slow moves, big damage, impacts very satisfying to land.
- Juggles are fun: eject the opponent into the air, follow up with nice juggle moves, then finish with special moves
  or into a super.
- Best example of the recipe well executed: Streets of Rage 2. Axel balanced; Blaze faster, a bit less damage, more
  agility; Max much slower, much heavier, many more startup frames per move, yet smooth and a joy to play, deals a ton
  of damage — Bruno's personal favourite.

**Data extracted (to use as targets):**
- Three archetypes on SOR2's model: **balanced** (Axel), **fast** (Blaze: faster startup + movement, less damage),
  **heavy** (Max / Krauser as a wrestler: slow startup, big damage, big impact feedback: hit-stop, shake, sound).
- Heavy must still feel *smooth*: slow startup does not mean stiff — animation quality and responsiveness of inputs
  (buffering, no dropped presses) carry it.
- Depth = routes (branches, juggles, finishers into specials / supers), bounded: no KI-style combo breakers / long
  memorised strings.
- Juggle route: launcher -> juggle follow-ups -> special or super finisher.

## 8d. Measured reference: Final Fight (CPS1, World 900112)

Full report + frame sheets: /data/study/ffight/REPORT.md, ffight_framedata.json, sheets/.
- One global hit-stop (6 f strikes, 5 f knees / throws) and one hit-stun (28 f) for everyone: the heavy feel comes
  from startup and damage only.
- Chain: advances only on hit; a whiff or getting hit resets to link 1; a 45-frame "chain credit" after a hit (counts
  only while not attacking); no input buffer (presses in hit-stop / startup / recovery are dropped).
- Lengths: Guy 5 links, Cody 4, Haggar 3. Jab first active frame 4 / 4 / 10, damage 6 / 10 / 18; full chain damage
  42 / 46 / 54 (close), Haggar's whole chain lands fastest (43 f vs 54 / 44).
- Final press + back / up / down = throw the enemy you hit (Guy / Cody turn and throw behind, Haggar backdrops), no
  hurtbox for the whole throw (42 f, Haggar 58 f); thrown body = 8 damage + knockdown to others.
- Same jump arc for all (7 f crouch, 41 f air, 61 px); walk 2.10 / 1.95 / 1.85 px/f; Haggar's reward is the grab game
  (backdrop 50, piledriver 70, long invincibility).
- Special (attack + jump): invincible from frame 1, 20 damage, costs 8 HP only on hit.
- Emergent route (Bruno's "jab, jab, throw, then jab, throw" with Haggar): the throw resets the chain, but the thrown
  body's hit on another enemy / object is credited to the thrower and refills his 45-frame chain credit, so the next
  jab on a fresh enemy counts as link 2 and the following press is the throw. Same enemy: never (no credit, the
  downed enemy is untouchable ~150 f). Haggar's backdrop drops the body ~70 px behind (often onto someone); Guy / Cody
  throw ~186 px (rarer). Proposal: keep it on purpose — "a hit by your thrown body counts as your hit".

## 8e. Measured reference: Final Fight enemies

Report data: /data/study/ffight/enemies/ (enemy_attacks.json, tele_*.png sheets). 21 enemy types + Damnd, Sodom.
- Bruno's "the hit can take half a second": mostly not a long wind-up — the enemy holds its ordinary stance for a random
  wait (table at ROM $2245E: 1..60 f, mean ~31) before a short wind-up.
- Wind-up follows damage: 3-6 f for 4-29 damage (as fast as Guy / Cody's jab), 12-15 f for knives / charges (30-60),
  20-50 f for specials (Damnd 25, Andore's 49-f clinch before a 40-damage throw).
- Player hit-stun 27 f (knockdown 75-140 f); enemy hit-stun 28 f and chain gaps < 21 f, so a chain can't be broken.
- No attack-token limit: up to 5 enemies with live attack boxes on one frame.
- Proposals (mine): wind-up proportional to damage; keep the random wait but show a readable "ready" pose during it;
  an attack-token limit (e.g. 2 attackers at once).

## 8f. Measured reference: Streets of Rage 2 (Axel / Max / Blaze / Skate)

Data + sheets: /data/study/sor2/ (sor2_framedata.json, sheets/).
- Hit-stop scales with damage: 4 + damage/4, capped at 8 (jab 5, 16-damage hit 8); the attacker holds its impact
  frame, the victim reacts at once.
- Hit-stun: enemies 31 f (refreshed by each hit), players only 12 f → jabs are +23 (Axel) / +18 (Max).
- Same 4-link combo for everyone, advances on hit only, 16 idle frames to press again, no attack buffer; the special
  button is buffered 20 f. Axel: a fast 4th press = 2-hit finisher.
- Max (Bruno's favourite) is smooth because: same 4 links, 1.5x damage (combo 66 vs Axel 44 / Blaze 36 / Skate 28),
  a 3-hit link 3, long hit-stop on every hit, range-adaptive jab, short recovery, fast invincible blitz (hits frame 2),
  same jump as Axel, +18 on hit.
- Move set grammar shared by all: invincible neutral special (8 HP, only on hit), forward special, blitz (f,f + A),
  back attack (attack + jump), charge attack (hold 60 f), grab tree (knees / neutral move / throw / vault + back throw),
  throws fully invincible, thrown body 16 to others.
- Vs Final Fight: SOR2 keeps chain length equal and makes the heavy hit harder and more often; FF shortens the
  heavy's chain. Proposals (mine): damage-scaled hit-stop; equal combo length with multi-hit heavy links; long enemy
  / short player hit-stun; buffer specials ~20 f + a 4-6 f attack buffer; a rhythm reward finisher; one input grammar
  for every archetype (Max's jump-with-enemy slam as the model for Krauser).

## 8g. Synthesis: what 8 classic brawlers agree on (studied 2026-10-07/08)

Games: Final Fight (1989), Captain Commando (1991), Warriors of Fate (1992), Streets of Rage 2 (1992), The Punisher (1993),
Cadillacs and Dinosaurs (1993), Alien vs. Predator (1994), D&D Shadow over Mystara (1996). Data: /data/study/encyclopedia
(one JSON per game, the Lab's Exposé tab), lessons in KNOWLEDGE.md.

**Universal (all 8):**
- A chain advances ONLY on hit; a whiff (or being hit) restarts it. → principle 1 holds everywhere: the first hit gates
  everything.
- The special (desperation) costs life ONLY on contact (6-12), is invincible, and in the later games never kills.
- Throws are invincible for their whole animation; a thrown body hits other enemies.
- Enemies: no attack token in any Capcom game (3-5 attackers at once happen); aggression rises with a hidden
  difficulty rank (FF, CC, WoF, Punisher, Dino).

**How Capcom evolved (1989 → 1996):**
| Topic | Early (FF 1989) | Later (1992-96) |
|---|---|---|
| Heavy archetype | shorter chain (Haggar 3 links) | same length, more damage (SOR2 Max 1.5x, Dino Mess +10-20 %) |
| Fast archetype | — | LONGER chain (AvP Linn 5, Mystara Elf 6) |
| Chain length | 5 / 4 / 3 | 4 for all (CC, SOR2, Punisher, Dino); WoF 3 for all |
| Link window | 45 f while idle | 16-50 f (CC 16, Mystara 24, AvP 30, Dino 40, Punisher 50) |
| Input buffer | none | presses latched during hit-stop (WoF, Dino); SOR2 buffers the special 20 f; FF/CC/Punisher/Mystara none |
| Hit-stop | flat 6 | per move, heavier = longer (AvP 3-13, WoF 3-11, Punisher 7/9/10 + 6-f shake, Dino 9 / 12-13); SOR2 4 + damage/4 cap 8; CC 7 / Mystara 8 flat |
| Enemy hit-stun | 28 | 23-36 |
| Player hit-stun | 28 | 12 (SOR2), 17 (Punisher), 26 + untouchable (CC, AvP) |
| Chain branches | last link + back = throw | throw on link 2 (WoF) / link 4 (Punisher, Dino), stepping turns (CC), command cancels (AvP, Mystara) |
| Juggles | none (downed = untouchable) | none in the CPS1 line; AvP stun meter → launch, juggle cap 3; Mystara cancel matrix ending in a dead-end move |
| Movement | per character | shared walk + jump (CC, WoF walk, Mystara), per character again in SOR2 / Dino |
| Damage | fixed, victim-class table | random spread (WoF, Dino), rank-scaled enemy damage |

**The brakes on depth (no Killer Instinct):** AvP caps juggles at 3 and speeds up the get-up; Mystara lets you cancel
anything but every route ends in ↓↑A, the chain restarts only from standing, air victims hang then drift out of reach,
downed enemies can't be hit. Everyone else simply makes downed enemies untouchable.

**Numbers proposed for the brawler (mine, to agree):**
1. Advance on hit only; link window ~30-40 f after recovery; presses during hit-stop latched (plus 4-6 f buffer) — the
   later-Capcom way, and what keeps a slow heavy smooth.
2. Chain length the same for every archetype (4); heavy = ~1.5x damage per hit and longer hit-stop; fast may get +1
   link (AvP / Mystara pattern).
3. Hit-stop per move, heavier hit = longer: ~6 (jab) to ~12 (finisher), the same scale for every fighter (consistency).
4. Enemy hit-stun ~28-32; player hit-stun short (~12-20) plus a brief untouchable window, so crowds can't juggle you.
5. Juggles with a brake: a launch (finisher or a stun meter) and a hard cap (AvP's 3), or a route that ends in a
   dead-end move (Mystara); downed enemies untouchable.
6. Special: invincible, costs life only on contact, never kills.
7. Throws invincible; the thrown body's hit refills your chain credit (FF's accident, kept on purpose).
8. Enemies: random wait in a readable "ready" pose, wind-up proportional to damage; a small attack token (2) — a
   deliberate departure, none of the 8 games has one.

## 8h. Decisions (Bruno, 2026-10-08, decisions page "revamp", answers in /data/brawler/feedback/decisions/revamp.json)

- Chains: a whiff restarts the chain; next-link window ~30-40 f; presses in the hit freeze are kept and fire on the
  first possible frame (+4-6 f buffer).
- Length per archetype like Final Fight: fast 5, balanced 4, heavy 3. Three archetypes (fast / balanced / heavy); heavy
  = fewer, slower, stronger hits (Haggar).
- Finishers by direction as a built-in feature: neutral, forward, up, down (up / down optional per character). Last link:
  back = throw backwards, forward = launcher or push, neutral = finisher.
- Thrown body hitting others: NO chain effect (FF's credit refill not kept).
- Hit freeze per move on one scale (~6 jab to ~12 finisher). Fixed damage (no random spread).
- Player hit: short stun (~12-20 f) + brief untouchable window.
- The chain finisher launches; juggles hard-capped at 5 air hits.
- Special (invincible): costs meter if you have it, else life; with no life to spend you cannot use it.
- No command-grab inputs, ever. Each fighter has throw scripts (Terry: forward + back; Ralf also KOF98's command
  grab as an extra throw); command-grab animations are used as throws in particular cases (e.g. with meter the throw
  becomes a super throw). A chain may end in a throw.
- Enemies: at most 3 attack at once; a readable "ready" pose during their random wait; wind-up proportional to damage;
  a hidden difficulty rank.
- Tools: explore chains on both the PC and the Player app. Retiming 0.5x-2x, beyond that a hand check.
- Open (his question): how to assess visual appeal and classify moves (punch / kick, high / mid / low, launcher).

## 9. Iterate fast: an exploration tool, no build in the loop

**Bruno:** we want to iterate quickly. "I want a tool that allows me to explore new things, so I don't want to wait for
a new build to be created for a new combo."

**Proposals (mine, to agree):**
- Two layers, one data format:
  1. **Preview in the Lab (browser, instant):** pick pieces from a fighter's library, drag the startup / active /
     recovery handles, see the chain play at once from the exported frames (the Lab already draws our sprites with
     the game's palettes), with boxes, spacing against a dummy, damage and frame advantage computed live.
  2. **Push to the running game (seconds):** the same chain data written into the running emulator's RAM (a debug
     override table the game reads before its ROM tables), so it plays in a real fight, no rebuild. A build only
     bakes what was kept.
- The same format feeds the exporter, so what you tuned is exactly what ships.

## Open: to discuss with Bruno

(filled as the discussion goes on)

## Process

**Bruno:** "I don't want to babysit the process."
