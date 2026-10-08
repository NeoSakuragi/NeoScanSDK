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

**1C. Retiming** (done 2026-10-08, Bruno's design change: at run time, the data keeps the source timing; docs/brawler_data_model.md "Retiming")
- Segments per move from the exported data: startup, then each active window and the recovery after it (a single hit
  = 3, two hits = 5); the export adds them (bm_seg, chainlab.json), no frame data changes.
- game.json `retime` per move = target frames per segment; fighter.c plays each segment on its own clock (every source
  frame played in order: boxes, effects, sounds, program ops; each window's contact frame shown; travel unchanged);
  hit-stop and victim reactions not scaled; `fighter_retime()` for other systems (archetype defaults, situations).
- Bound 0.5x-2x (beyond: built, printed as a hand check). No behaviour change until a move is given a retime.

## Phase 2 — meter, breaker, damage tiers (after 1A; fighter.c meter + main.c HUD) (done 2026-10-08: docs/brawler_data_model.md "Meter, breaker, damage tiers"; with it 1C's collision limit fixed: rt_probe)
- Meter: 3 stocks = 300 points, HUD bar with 3 dots. Special 100. Breaker (a special out of hit-stun) 200 with the
  sprite blinking; no meter → life; neither → no breaker. Fury 300. MAX 300 + low life (red blinking state).
- Damage tiers unified across fighters: specials (±15 %), furies (±20 %), MAX (±20 %); special < fury < MAX.

## Phase 3 — throws (after 2; fighter.c throws, exporters) (done 2026-10-08: docs/brawler_data_model.md "Throws"; the placements for Bruno's review: /data/tmp/rv3/out/audit.md; 3b: Bruno's answers applied (hold mapping as is; Rugal / Yamazaki / Genjuro keep their grab as a provisional D fury, `fury_grab`))
- No command-grab inputs. Each fighter's throw scripts: forward + back; grab specials (Rosa 6246A / 214B, Iori 624D/B,
  Rugal God Press, Hanzo SS2 Mozu Otoshi, Cheng Fu's Super 623 catch, Ralf's KOF98 grab…) become throws, from the
  hold, the chain's back branch, or the meter super throw — case by case.

## Phase 4 — characters one by one (review pages on canneji)
- Per fighter: archetype, the tagged piece library (punch / kick, high / mid / low, launcher / sweep, reach, startup,
  appeal score), my proposed chain + finishers + throws, looping clips; Keep / Drop / None of these + mic notes.
- Order: a fast, a balanced and a heavy first (e.g. Kim, Terry, Krauser), then the rest.
- Built 2026-10-08 (generic, any roster fighter): `tools/brawler/pieces.py` (the catalogue: normals, command normals,
  jump normals, the C slots' specials' first hits played from their ROM programs (retime.Prog; segments equal to the
  export's for every program special), the back throw; tags from the data; the APPEAL formula in its docstring: 20
  points each for drawings, evenness, pose travel, a clear contact frame, joins with idle; the proposal: builders by
  appeal + flow (contact pose -> next start pose, victim in reach, never strong -> light, limb / height variety,
  archetype), finishers by stick with alternatives); `tools/brawler/review_build.py` (clips: one entry per game frame,
  sprite sheet per fighter; `REVIEW` = the fighters built); `tools/brawler/chainlab/review.html` + `review.js` (the
  page, answers in the decisions store, set `review-<fighter>`); `tools/brawler/review_proof.py` (frame counts vs the
  data, headless pages at phone / desktop width, 59.18 frames a second). Page: canneji.duckdns.org/brawler-lab/review.html.

## Phase 5 — the chain tool
- Lab preview (pieces, startup / active / recovery handles, live boxes / damage / advantage) and push into the running
  game; the same in the Player.
- Built 2026-10-08 (docs/brawler_data_model.md "The chain tool"): the Chain Lab tab's chain tool (chainlab/chaintool.js:
  archetype, links and finishers from the piece catalogue, hit-stop per link, segment handles 0.5x-2x, readouts, push,
  autoplay per finisher, a fight with it, Save to the feedback store -> tools/brawler/chain_save.py -> game.json); the
  game's one hook: `lab.load` 5 (fighter.c lab_install: tree + retime table in lab.buf -> route_tab, rt_tab). The Player:
  a written plan (same bytes, a writeRam JNI call + a service endpoint), not built.

## Proofs per phase
Build, bank_proof, regress no-bleed (the attract is expected to change in phase 1: a new baseline is recorded once,
then no-bleed again), controls / cancel / fury_inv for the whole roster (shared rules), campaign29, and per-rule
targeted proofs (chain advance, buffer, finisher by direction, juggle cap, attack tokens, retime round-trip).
