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

## Open: to discuss with Bruno

(filled as the discussion goes on)

## Process

**Bruno:** "I don't want to babysit the process."
