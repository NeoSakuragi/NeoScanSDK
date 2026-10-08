# Brawler gameplay revamp — implementation plan (2026-10-08)

Source of truth for WHAT: docs/brawler_feel.md (principles, the 8-game synthesis 8g, Bruno's decisions 8h).
Approach (Bruno): build the revamp as ONE standard system for all characters first, then review the characters one by
one. Each phase merges into `brawler` and ships as a release so Bruno can feel it; a phase never breaks the others.

## Phase 1 — the standard systems (three jobs in parallel, separate areas)

**1A. Chain core** (examples/brawler/fighter.c chain / hit code, game.json + build_tables.py schema, docs/brawler_data_model.md)
- A chain advances only on hit; a whiff or being hit restarts it.
- Next-link window ~35 f after the recoil; presses during hit-stop latched and fired on the first possible frame, plus a
  5-frame attack buffer.
- Archetype per fighter (game.json `archetype`: fast / balanced / heavy) setting the chain length 5 / 4 / 3.
- The last link picks its finisher by the stick: neutral finisher, forward, up, down (optional per fighter; launcher
  direction per fighter; down = ground slam + bounce or crumple sweep), back = throw backwards (invincible throw).
- The finisher launches (when the fighter's finisher is a launcher); juggles hard-capped at 5 air hits (then the victim
  is untouchable until it lands); downed enemies untouchable.
- Hit-stop per move on one scale: jab 6 → finisher 12 (by link index / move class), the same for every fighter.
- Player hit-stun short (~16 f) + an untouchable window (~20 f); enemy hit-stun ~28-32.
- Fixed damage. Chain damage totals by archetype (heavy most, fast least, Final Fight ratios ~42 / 46 / 54).
- Default chains generated from each fighter's existing pieces so every fighter plays under the new rules at once
  (authoring by appeal comes in phase 4).

**1B. Enemy behaviour** (examples/brawler/ai.c, enemy data)
- At most 3 enemies attacking at once (attack tokens).
- A readable "ready" pose during the random wait before an attack (a held stance frame or a tint pulse when no pose).
- Wind-up proportional to damage (light 3-6 f, heavy 12-15 f, special 20+ f).
- A hidden difficulty rank raising aggression / damage as the player does well.

**1C. Retiming** (tools/brawler exporter, game.json `retime` per move)
- Phase detection per move (startup / active windows / recovery) from the decoded data.
- Retime = remap each phase's frames: drawing order kept, durations scaled, motion scaled so travel is unchanged, boxes /
  effects / sounds attached to their drawing; hit-stop and victim reactions not scaled; ROM programs' counters scaled.
- Bound 0.5x-2x (beyond: flagged for a hand check). No behaviour change until a move is given a retime.

## Phase 2 — meter, breaker, damage tiers (after 1A; fighter.c meter + main.c HUD)
- Meter: 3 stocks = 300 points, HUD bar with 3 dots. Special 100. Breaker (a special out of hit-stun) 200 with the
  sprite blinking; no meter → life; neither → no breaker. Fury 300. MAX 300 + low life (red blinking state).
- Damage tiers unified across fighters: specials (±15 %), furies (±20 %), MAX (±20 %); special < fury < MAX.

## Phase 3 — throws (after 2; fighter.c throws, exporters)
- No command-grab inputs. Each fighter's throw scripts: forward + back; grab specials (Rosa 6246A / 214B, Iori 624D/B,
  Rugal God Press, Hanzo SS2 Mozu Otoshi, Cheng Fu's Super 623 catch, Ralf's KOF98 grab…) become throws, from the
  hold, the chain's back branch, or the meter super throw — case by case.

## Phase 4 — characters one by one (review pages on canneji)
- Per fighter: archetype, the tagged piece library (punch / kick, high / mid / low, launcher / sweep, reach, startup,
  appeal score), my proposed chain + finishers + throws, looping clips; Keep / Drop / None of these + mic notes.
- Order: a fast, a balanced and a heavy first (e.g. Kim, Terry, Krauser), then the rest.

## Phase 5 — the chain tool
- Lab preview (pieces, startup / active / recovery handles, live boxes / damage / advantage) and push into the running
  game; the same in the Player.

## Proofs per phase
Build, bank_proof, regress no-bleed (the attract is expected to change in phase 1: a new baseline is recorded once,
then no-bleed again), controls / cancel / fury_inv for the whole roster (shared rules), campaign29, and per-rule
targeted proofs (chain advance, buffer, finisher by direction, juggle cap, attack tokens, retime round-trip).
