# Brawler CPU budget (analysis, 2026-10-14)

Bruno's note 20261014-170114-5d29 on 0.10.92: "the CPU constantly reaching 100%". Analysis only, no game change.
Decisions: https://canneji.duckdns.org/brawler-lab/decide.html?set=cpu-budget

## Method

- His bundle (Moriya, stage 4 boss wave: Rugal + 5 enemies, 71 s, frames 53400-57596) replayed in our emulator core,
  the 0.10.92 commit rebuilt byte-identical (sha256 f8f69682...) with `-g` for line info (same ROM).
- `tools/brawler/cpu_profile.py`: a Geolith core built with `tools/brawler/cpu_profile_core.patch` counts the 68000
  cycles of every instruction (exclusive per function, inclusive through a shadow call stack, a snapshot at every
  `game_tick` entry). One tick = one `game_tick` entry to the next; idle = crt0's wait loop. The per-tick totals are
  exactly 202,752 cycles (one frame) or a multiple: the accounting matches the core's frame clock.
- Not done: older builds. The bundle replays only on its own ROM; a scripted run (`bank_cpu.py`) would be the way.

## What the meter shows

`main.c hud()`: CPU = 100 - the fewest idle spins of the last 16 ticks (spins x 54 cycles). It shows the worst tick
that still fit. A tick that does not fit shows only what is left of its second frame, so it reads low. The
dropped frames never show on the meter.

| This run | |
|---|---|
| frames / game ticks | 4196 / 3546: **650 frames dropped** (15 %) |
| 6-enemy ticks | 2571, of which **644 overran** (25 %): those fights run at about 80 % speed |
| busy per tick, 6 enemies | median 92 %, p90 109 %, p99 148 %, max 430 % (the boss wave's spawn) |
| busy per tick, P1 alone | median 60 %, max 81 % |
| P1's state in overrun ticks | SPECIAL 57 %, ATTACK 12 % (busy 117 % on average while P1 is in a special) |

## Where a tick goes (% of one frame, mean per tick)

| Subsystem | P1 alone | 6 enemies, fits | 6 enemies, overrun |
|---|---:|---:|---:|
| Draw (sprite blocks, line guard, stage, sparks, shadows) | 14.1 | 25.1 | 30.7 |
| Fighters (`fighter_update`) | 9.8 | 13.6 | 21.6 |
| Collision (`combat`, `strike`) | 9.6 | 8.7 | 13.1 |
| HUD (life / drive bars) | 7.7 | 12.0 | 14.0 |
| AI (`ai_update`) | 3.2 | 5.4 | 8.6 |
| Game flow, camera, `close_marks` (in `game_tick`) | 4.4 | 6.5 | 6.7 |
| Screen edges (`screen_keep`, `wall_update`, twice a tick) | 3.1 | 4.9 | 5.5 |
| Depth sort | 3.6 | 3.6 | 3.7 |
| VRAM flush (vblank) | 1.7 | 3.1 | 3.8 |
| BIOS SYSTEM_IO + vblank IRQ + joypad | 2.3 | 2.3 | 2.3 |
| Projectiles, input, sound | 1.0 | 1.1 | 2.0 |
| **Total busy** | **60.5** | **86.1** | **112.1** |

Each extra enemy costs about 4 % of a frame across all subsystems. The overruns come on top of a crowd: P1's special
(program, pans, effects: +7), hits (collision +4), new animation frames (tile uploads +3).

## Top costs (6-enemy ticks, % of a frame)

| # | Cost | Mean | Peak | Why |
|---|---|---:|---:|---|
| 1 | `bar_draw` (HUD bars) | 10.2 | 23 | Every bar (2 life + target + up to 8 drive chunks + boss) recomputes every cell each tick, even when nothing changed. |
| 2 | `draw` itself + `fighter_place` + VRAM flush | 6 + 4.6 + 3.3 | 50 | All 25 blocks' Y / X words (SCB3 / SCB4) are rewritten every tick, moved or not. |
| 3 | Collision `combat` + `strike` | 6.6 + 3.2 | 46 | Several passes over all 16 entities (8 fighters + 8 projectile slots) with team / state tests per pair; `strike` is called for every attacker, mostly to return at once. |
| 4 | `fighter_update` (state machine) | 7.8 own, 15.6 incl | 61 | Spread over many lines, no single hotspot; specials add `prog_update` / `pan_fx` / `pan_advance`. |
| 5 | `ai_update` | 6.2 | 24 | 6 enemies x target search, ranks, slots every tick. |
| 6 | Line guard step c (`cols_add` / `bands_add`) | ~2 | 33 | Per column per 8-px band, only when 16-px bands overflow: the effects-heavy ticks (6 projectiles) cost a third of a frame. |
| 7 | Boss wave spawn (`tint_colour`) | — | 259 | 6 enemies' palettes tinted colour by colour (6 multiplies each): one tick of 4.3 frames (a ~70 ms freeze). |
| 8 | `depth_sort` | 3.6 | 6 | Insertion sort of 16 entries through `depth()` (32-bit) + block layout every tick. |
| 9 | `close_marks` | 2.2 | — | 8 x 8 pairs every tick, for enemies too. |
| 10 | `screen_keep` + `wall_update` | 5.0 | — | Run twice a tick for everyone (the second pass for who the combat moved). |

Small: `mark()` (the PROFILE_HUD section clock) still runs in normal builds (0.6 %), `char_index` per tick (0.6 %),
palette uploads (`PAL_setPalette` + loads + overlays, ~2 %).

## Options (savings in % of a frame at 6 enemies)

| Option | Saves | Risk | Effort |
|---|---:|---|---|
| A. HUD bars drawn only when a bar's value / trail changes | ~9 | low (same picture) | small |
| B. Spawn tints precomputed (build time or once per fighter + set + tint) | the 4-frame freeze | low | small |
| C. Line guard step c on cached spans per entity (recomputed when its frame changes) | spikes -25, mean ~1 | medium (sprite-per-line overflow) | medium |
| D. Sprite blocks: write Y / X only for blocks that moved or changed | ~5 | medium (VRAM state) | medium |
| E. Collision: live-entity lists per team once a tick, `strike` only for live boxes | ~5 | medium (hit order must stay: regress traces) | medium |
| F. AI: half the enemies think on even ticks, half on odd (movement every tick) | ~3 | feel (1-frame later reactions) | small |
| G. Small cleanups: `mark()` off, `close_marks` players only, sort 16-bit keys of live entities, second edge pass only for moved fighters, `char_index` cached | ~6 | low | small each |
| H. The meter shows dropped frames (vblanks per tick) instead of only the worst fitting tick | — | none | small |
| I. 68000 asm for the remaining hot C loops (after A-G) | 2x on those loops | medium | high |

A + D + E + F + G: about 28 % of a frame. 6-enemy mean 92 % -> ~64 %, overrun mean 112 % -> ~84 %: all but the
spikes fit; B and C remove the spikes.

## Reproduce

```
cp -r geolith /data/tmp/cpuprof/geolith && cd /data/tmp/cpuprof/geolith && patch -p1 < .../tools/brawler/cpu_profile_core.patch && make -C libretro
python3 tools/brawler/cpu_profile.py /data/feedback/<note> OUT.json --game <build dir with build/rom.elf> [--pc-window F0 F1]
```
OUT.json: per tick total / idle / busy + scene (fighters, enemies, projectiles, P1 state); OUT.npz: per tick per
function exclusive / inclusive cycles, per-PC cycles (map lines with `m68k-linux-gnu-addr2line -f -i` on a `-g` build).
