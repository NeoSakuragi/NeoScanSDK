# Throws audit (2026-10-12, brawler 0.10.67)

Bruno: "The weak spot of the game engine is still the throws ... a mix-up between the game engine's mechanics / physics
and the decoded scripted mechanics / physics; somehow they can conflict. Also some of the sprites are not always stuck
the same way properly." Investigation only: no game code changed. Everything measured in our emulator (Geolith
harness, `make AI_OFF=1` build of `audit/throws` = brawler 0.10.67; KOF98 itself through `neogeo_sdl --capture`).

Tool: `tools/brawler/throws_audit.py` (run / ana / static / src98 / side98, see its docstring). Output, sheets and
per-frame JSON: `/data/tmp/throws_audit/` (`summary.json`, `static.json`, `rep_<case>.json`, `sheet_<case>.png`,
`side_<kof98 id>_<throw>_<case>.png`). The "source path" below is the decoded script the brawler holds (paired rows:
thrower frame / offset, victim posture / offset per frame; victim lists: per-step entries), checked against the raw KOF98
captures (`tools/kof96/capture/throws98/<id>.txt`, Yuri as the victim) with `src98`.

## 1. Inventory: who owns what, per phase

| path | grab | held | release | flight | landing |
|---|---|---|---|---|---|
| **hold** (walk-in grab, `grab`) | script: thrower `grab_frame`, victim `holds[0].rows[0]` place / pose | script (`place_victim`) + ENGINE `screen_keep` / `wall_update` clamps both bodies each frame | - | - | - |
| **hold hits** (A x3, `BT_HOLD_*`) | - | script (`paired_update`); impacts freeze both 4 frames | finisher: ENGINE `fighter_hit(R_KNOCKDOWN)` | ENGINE (std / react) | ENGINE |
| **paired throws** fwd / back + A, chain back throw, `throw_x` (Ralf 426B) | script row 0; ENGINE direction rule may turn the thrower (`throw_start`, `lands_behind`) | script (`paired_update` -> `place_victim`, `thrown_update` -> `thrown_place` after the control return) + ENGINE: `place_at` floor clamp y >= 0, `clamp`, `screen_keep` on S_THROW / S_THROWN (adds to `throw_x0`) | ENGINE `thrown_release`: velocity RE-DERIVED (lands on the landing row's place, GRAVITY_KD), pose replaced by BA_BLOWBACK / BA_KNOCKDOWN_FLIGHT | ENGINE (S_KNOCKDOWN kmode 0: gravity, no drag), thrown body `tb_by` | ENGINE bounce / hop / down (`update` S_KNOCKDOWN) |
| throws with no release (Kim, Rosa, Cheng-Fu stun) | as above | script to the end | - | script | `victim_end` (ENGINE lies it down, y = 0) |
| **grab specials / command grabs** (up + A extra: Iori 624B, Rugal 624A, Hanzo-SS2 623K, Rosa 214B; fury grabs: Rugal 23624C, Yamazaki 236236C, Genjuro WFT; any special with a catch) | hold lets go (`hold_special`); ENGINE special push (PUSH_DX) + `hold_apply` until the catch | script: victim lists (`vlist_place`, entry per attacker step or per frame VL_FRAMES), no floor clamp; ENGINE: `vlist_wall` moves the ATTACKER per entry, `clamp`, `screen_keep` / `wall_update`; blows run `fighter_hit` -> `react` | `vlist_fly`: DECODED velocity + gravity (VL_VEL), Kizuna source reaction (VL_SREACT), or `kof_react` | ENGINE `kof_fall` with the list's g | ENGINE |
| air throws | none in the brawler (`grabbable` needs y = 0) | | | | |

Three different release rules coexist: paired throws re-derive a parabola under GRAVITY_KD, victim lists keep the
decoded velocity and gravity, free hits use `std_flight` (0.10.64). Two different floor rules: paired scripts clamp
y >= 0 (`place_at`), victim lists do not.

## 2. Cases measured (brawler vs the decoded source, per frame)

18 runs (`summary.json`), the held phase indexed by the script's own row (hit-stops excluded):

| case | held phase | release / flight | after landing |
|---|---|---|---|
| Terry fwd / back (KOF98) | exact (27 / 47 rows) | path off by up to 10 / 19 px (fwd), 8 / 12 px (back); pose pop | +15 px (fwd), pinned at the screen edge (back) |
| Terry fwd, screen edge ~100 px ahead | exact | +94 px | +124 px |
| Ryo fwd (KOF98, freeze row) | exact | 20 / 25 px | 17 px |
| Kyo fwd / back | exact | 7 / 37 px, 17 / 25 px | 23 / 31 px |
| Krauser back (KOF96, C throw turned) | 3 frames off 15 px (edge) | 29 px + 12 px y | lies 12 px high |
| Ralf up + A (`throw_x`) | exact | +91 px (edge) | |
| Hanzo-SS2 fwd | 3 frames clamped (-35 vs -66 px) | **+92.5 px teleport at row 36** | thrower pinned at the edge |
| Billy Lee fwd (DD) | 7 frames clamped (9.8 px) | **+73 px teleport at row 25** | |
| Kim fwd (Kizuna, no release) | 15 frames off: edge 4-12 px, lying rows +11 px y (floor clamp) | - | |
| Haohmaru fwd (SS2) on Ryo / on WHP Hanzo | exact | 0 / 12 px | 4 px |
| Iori up + A (624B list) | entries exact; victim at y = -40 for 2 frames (list data, not clamped) | | |
| Rugal up + A (God Press lists) | entries exact but f44: victim y 11 vs 4 (one engine-fall frame); f42 Rugal moved 287 -> 200 px in one frame (wall rule) | | |
| Hanzo-SS2 623K, Terry chain back throw | exact | chain = Terry back | |

Side-by-side KOF98 vs brawler: `side_3_throw_d_terry_back.png` (k = 47 -> 50: KOF's victim still tumbles head-down near
the floor, the brawler's Ryo is upright in his blowback pose mid-air), `side_3_throw_c_terry_fwd.png`,
`side_6_throw_c_ryo_fwd.png` (Ryo's throw plays at speed 1.5x, so frames k do not line up after row 30).

## 3. Engine / script conflicts found

1. **Screen clamp drifts a held victim's throw origin -> release teleport.** `screen_keep` (fighter.c 4382) adds the
   clamp to `throw_x0` of every S_THROW / S_THROWN fighter, every frame. While held, the victim is re-placed from the
   thrower each frame (`place_victim`), so the clamp repeats and `v->throw_x0` accumulates; at the release
   `thrown_place` / `thrown_release` (1236 / 1306) place it from that drifted origin. Hanzo-SS2 fwd: 3 x 30.5 px ->
   92.5 px jump at row 36 (`sheet_hanzo_ss2_fwd.png` f23 / f40); Billy Lee 7 x 9.8 -> 73 px (row 25); Terry fwd at the
   edge 94 px; Ralf 426B 91 px. Any throw whose victim swings past a screen edge (KOF throws reach 170-320 px on a
   304 px screen: `static.json` reach).
2. **Per-frame clamps break the hold itself.** `screen_keep` / `wall_update` / `clamp` act on the thrower and the victim
   separately, so near an edge the victim is pushed off its script offset (Hanzo-SS2 -35.5 px instead of -66, Kim 35.5
   instead of 40, Krauser 225 instead of 240). The two are one body in the source.
3. **Release velocity re-derived, not decoded** (`thrown_release`): the flight lands on the landing row's place but
   its shape is the engine's (GRAVITY_KD, no drag). Static deviation over every throw: up to 51 px y (Mai C), 47 px
   (Ryo D), 41 px (Ralf C / Yashiro C / Rugal C); measured Terry 10 / 19 px, Kyo 7 / 37 px. The release frame also
   jumps 7.8 px (two steps of the derived vx) past the release row and keeps that lead (Terry back f47). The decoded
   release velocity cannot simply replace it under GRAVITY_KD: KOF's throw flights slow down, so the decoded speed
   overshoots by a median 254 px, up to 1070 px (Ryo D: 15 px / frame, 10.5 up).
4. **Pose pop at the release**: `thrown_release` drops the script's posture and plays the victim's own BA_BLOWBACK /
   BA_KNOCKDOWN_FLIGHT: an inverted / horizontal victim becomes an upright blowback in one frame (Terry back f47 -> f50,
   frames 140 / 141 / 144 instead of 209 / 211 / 212 every flight frame).
5. **Two floor rules.** `place_at` clamps y >= 0 (1231); the sources put lying / slammed victims below 0 on purpose
   (their frame origins): Hanzo-SS2 C 48 rows down to -63, Hanzo-WHP -28, Rugal C -20, Yashiro C -16, Krauser -12,
   Kim -11, Ryo D -8: those victims float. `vlist_place` does not clamp (Iori 624B entry 0: y = -40, as KOF98 itself
   draws its victims at y -24 in the 27_close capture). Same posture, two heights depending on the path.
6. **A blow on a held victim runs the engine's reaction.** `vlist_place` VE_BLOW calls `fighter_hit(R_HEAVY)` (2968):
   with the entry's dy > 0, `react` takes the "hit in the air" branch (S_KNOCKDOWN, vy 4), the victim's own update
   applies one fall frame, the next `vlist_place` snaps it back (Rugal God Press f44: y 11 vs the list's 4).
7. **The wall rule moves the attacker mid-move.** `vlist_wall` shifts the attacker per entry when an entry would cross
   `wall_lo / wall_hi` (KOF's $255B0, built for a 640 px stage): Rugal jumps 87 px in one frame (f42).
8. **Throw start swaps.** The hold shows the victim at `holds[0]` row 0; the throw's row 0 can be on the other side:
   the direction rule's turned plays (56-106 px across the thrower, every fighter's back / forward slot), SS2 / DD
   throws whose source swaps the victim behind at the grab (Haohmaru 33 -> -33, Genjuro 40 -> -66, Billy Lee 32 -> -32),
   Krauser's turned back throw (39 -> -48). Thrower pose pop too (Ralf 426B: hold frame 170 -> row-0 frame 62).

## 4. Why the victim's sprite is "not stuck the same way"

1. **One offset table for every victim.** `export_bm.throw_rows` (1551) takes the thrower's MIRROR MATCH list
   (`victims[thrower]`). KOF keeps a list per victim (+$C2 = table + victim id x size) because each fighter's frame for
   a posture sits differently around its origin. KOF98 exports, the roster's throwers x the enemy pool: per-victim
   lists differ from the mirror by 8-32 px in x and up to 76 px in y (Robert D vs Ralf), victim state different for up
   to 43 rows (`static.json` `_mirror_kof98`, `_mirror_kof96`). The raw KOF98 capture (Terry D on Yuri) differs from the
   exported rows by +4 / +12, 0 / +12, -8 / +24, +12 / +4 px over rows 3-31 (`src98_terry_throw_d.json`). A per-posture
   anchor per victim would not fix it: only 46 % of rows share one delta per (victim, state) (anchor check, 12 020 rows).
2. **Borrowed postures.** The victim's frame for a posture comes from any throw of its own game (`poses`, nearest
   angle, family, else a brawler animation), while the offset is the mirror victim's state (Terry D row 20: mirror state
   462 vs Yuri's 451).
3. **Cross-game victims have no source offsets at all.** Every enemy is a KOF fighter; SS2 / DD / Kizuna / WHP throws
   carry offsets measured on their own game's victims, postures matched by name.
4. Plus conflicts 1, 2, 4 and 5 above (edge clamps, release pose pop, floor clamp).

## 5. Proposed plan: one path for every scripted pair

Rule: from the grab to the hand-off the decoded script owns the position and pose of BOTH fighters; the engine runs
nothing on them but damage / sound / spark at the script's impacts. Data driven, every importer the same.

1. **The pair is one body for the world.** At the throw start (and at a victim list's catch) shift the throw origin
   once so the script's whole x range up to its hand-off row fits the screen (the generalisation of `vlist_wall`,
   computed from the rows / entries: min / max of tx and tx + vx). During the script: no `screen_keep`, `wall_update`,
   `clamp`, special push on either fighter, and no separate victim `throw_x0` (it reads the thrower's). Fixes 1, 2, 7.
2. **Hand-off at the landing, not the release.** The release row starts the thrown body (`tb_by`, knock-downs) as now;
   the victim keeps playing its rows (posture, place) through the flight; the engine takes over at the landing row
   (the brawler's standard bounce / down / get-up), or earlier on an interrupting hit (juggle rule 5) with the script's
   current per-frame velocity (row k+1 minus row k) into `std_flight`, the 0.10.64 standard launch. Victim lists the
   same (their VL_VEL flight is already decoded). Fixes 3, 4. This reverses Bruno's 2026-10-08 release rule ("give it
   back to the engine as soon as it leaves the hands"): the literal alternative, the decoded release velocity under
   GRAVITY_KD, overshoots by a median 254 px (conflict 3), so it needs his call.
3. **No floor clamp inside a script** (`place_at`): y is the data's, paired rows and victim lists alike. Fixes 5.
4. **Blows on a held victim do not react** (`vlist_place` VE_BLOW and hold hits: damage, sound, spark, burn only; the
   list or row decides posture and place). Fixes 6.
5. **Per-victim offsets.** Export the victim side of each KOF throw for every fighter of the same game in the roster /
   enemy pool (`victims[name]`: offset, state -> posture), the engine picks the victim's own rows by its fighter id;
   cross-game victims keep the mirror rows plus an exporter-computed posture anchor (the victim frame's body box centre
   vs the source victim's, per posture) as the fallback. Fixes section 4.
6. **Start swaps as data**: a short swap segment (the hold offset to row 0 over a few rows) for turned plays and for
   SS2 / DD grabs drawn turned, so the victim travels instead of teleporting. Fixes 8.

Per game: KOF96 / 98 / 99: per-victim lists (export_bm.throw_rows), negative y kept (Krauser, Rugal, Yashiro), flights
scripted to their landing rows (all have one but Ralf C, Yamazaki D, Billy D, Mai C: script to the end, as Kim now).
SS2 / DD / WHP / Kizuna: rows already decoded (handlers_ss2, throw_dd 0 mismatches, rosa_kz), only the anchor
fallback for KOF victims, their below-floor rows kept, the start swap segment. Victim lists: the pre-shift instead of
the per-entry wall move, no reaction on blows.

Risks: per-victim rows cost P ROM (about 2 throws x ~100 rows x 5 bytes per thrower-victim pair: ~250 KB for the 16
KOF throwers x 16 victims, banked); a scripted flight near a camera lock still needs the pre-shift to be right at
the start (the thrower may visibly step in from an edge, as KOF does at its walls); enemy throwers on the player (not
measured here) and every proof that pinned the 2026-10-08 release behaviour (throws_rv3_proof, throw196_proof,
chain_proof's Mr. Big back throw) need re-baselining; Rosa's frame lists (VL_FRAMES) were not compared entry by entry
(the harness does not read `vfr`).
