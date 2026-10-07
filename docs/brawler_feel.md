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
