# Throws review (T1, 2026-10-14, brawler 0.10.81)

Bruno: "the throws are still off and glitchy, trajectories when characters are ejected are off, certain throws are not
graphically tying the player and the victim properly." Follows docs/throws_audit.md (throws part 1, 0.10.70: one path,
the script owns the pair until the landing). Everything measured in our emulator (Geolith harness, `make AI_OFF=1`).

## How it was measured

- `tools/brawler/throws_audit.py OUT run CASE` (existing): each roster fighter's forward / back throw, hold hits and
  extra (up + A) throw on a KOF98 dummy (Terry; Ryo for Terry), per frame thrower + victim state, place, frame.
- `tools/brawler/throw_tie.py OUT --all` (new): draws both fighters' frames from their exports (the pixels on screen,
  flipped parts mirrored as draw.s does) and measures what the eye sees:
  - **gap**: px between the thrower's and the victim's pixels while the victim is in the hands (before the release
    row); **excess** = frames where the gap is > 6 px more than the source's own gap on that row (the mirror match
    drawn from the thrower's export = what the source game draws);
  - **centre jump**: the victim's largest one-frame move of its pixel centre;
  - **landing**: the victim's lowest pixel on its last thrown frames and after the hand-off (floating / dropping),
    the slide after the landing.
  - Proof sheets (line art, e-ink): `/data/tmp/throws_t1/{before,after6}/tie_<thrower>_<fwd|back|up|hold>.png`
    (thrower outlined, victim grey, the gap's two nearest pixels joined; under them the victim's path); tables
    `tie_table.txt`, `tie_summary.json`. Screenshots per frame: `<case>/NNN.png` (the screen shows the state of the
    frame before: one frame of video lag).
- `tools/brawler/anchor_check.py` (new): the cross-fighter "posture anchor" fallback against KOF's own per-victim lists.

55 throw cases (26 fighters x forward / back, + 5 up + A), 26 hold cases. billy_super is not on the select (a form):
same throw data as billy_lee.

## Defects found -> status

| # | class | throws | defect (before) | status |
|---|---|---|---|---|
| 1 | a | KOF throws whose flight / end uses KOF's shared knockdown states (287 falling, 309 floor, 326 / 312 / 331 / 334 / KOF96 359 lying): Kyo, Iori, Robert, Yashiro, Rugal fwd; Ralf C, Billy D, Mai C, Ralf 426B ends | those states have no posture: the victim kept the LAST posture (a lying frame drawn 40-70 px above its origin) through the flight, then dropped 35-45 px in one frame at the landing; script-end throws left it floating 30-37 px above the floor, then dropped into its down pose | **fixed** (export_bm KOF_FALL: they play BA_KNOCKDOWN_FLIGHT / BOUNCE / FALL / DOWN like a ROM-read throw); script-end lows 30-37 -> -7..-11 px |
| 2 | a | KOF98 own-list victims (each victim's KOF list): Ryo fwd / back, Ralf back, Robert back, Mai fwd / back, Terry back, Kyo back | the brawler draws ONE frame per posture, taken from another throw (another origin convention), placed with the offsets KOF uses for the frame it really shows: 10-30 px off the hands (Ryo fwd 36 frames at 10 px, Terry back 15 frames at 30 px) | **fixed** (export96 keeps each row's true frame centre and lowest pixel; export_bm.victim_rows puts the posture frame's centre there, its lowest pixel on the floor where KOF's frame lay on it, never under the floor in the air): excess 0 on all of them; Geese / Billy / Yamazaki fwd victims 7-13 px above -> on the floor |
| 3 | a | KOF96 bosses on KOF98 / 99 fighters (Krauser, Mr. Big, Geese, Goenitz throwing the player) | no per-victim list (other game): the boss's mirror rows on Terry's frames: Krauser's overhead lift 11-35 px off his hands, 56 frames | **fixed** (export_bm VICTIMS_FROM: KOF96's own list for its same fighters + #2): Krauser 56 -> 19 frames (the rest = his toss before the release row, the source's own gap); lifts held in the hands |
| 4 | b | throws whose row after the landing re-places the origin (K' back: 40 px in one row; Rugal, Kyo...) | the landing velocity was that step: K' back slid 156 px after landing (99 now) | **fixed** (fighter.c thrown_land: the motion the body landed with, row h-1 -> h, capped 6 px / frame, halved by the floor) |
| 5 | c | every throw with a landing row | the hand-off started BA_KNOCKDOWN_FLIGHT at the floor and relied on the same frame's floor test (shown one frame when the victim updates first or after the control return) | **fixed** (thrown_land: straight into BA_KNOCKDOWN_BOUNCE on the floor, impact already sounded) |
| 6 | c | KOF throws at 1.5x speed, swing rows (Billy back 163, Mai back 194, Robert back 154, Yashiro back 139 px) | the victim's pixel centre jumps 100-190 px in one frame on the over-the-head swings (rows skipped at 1.5x + KOF's own origin swaps on its list) | open (improvement 3) |
| 7 | a | other games' throwers on KOF victims (SS2 Haohmaru / Genjuro / Hanzo, WHP Hanzo, DD Billy Lee / Cheng-Fu, Kizuna Kim / Rosa, LB2 Moriya) | mirror rows + the victim's posture frames: mostly touching (gap 0); Billy Lee 2 frames 23 px, Kim 7 frames 8 px, Rosa 2 frames 7 px | open, minor (improvement 2) |
| 8 | b | Mr. Big back (KOF96 list on Terry) | flight 53 px off the mirror match during the toss (before the release row): not a tie problem, the own list's path vs the mirror's; not checked against KOF96 itself | open (check in KOF96, improvement 4) |
| 9 | - | any thrower on a NON-KOF victim (enemies throwing Haohmaru, Kim, Billy Lee... as the player) | not audited (the dummy is a KOF98 fighter) | open (improvement 4) |
| 10 | b | hold finisher (every fighter) | the engine's generic knockdown arc (82 px high, same for all): by design (R_KNOCKDOWN) | not a defect; improvement 5 |
| 11 | - | Rosa up + A (214B, frame list) | the tie metric does not read frame lists; screenshots: held in contact, the victim ends standing | open (improvement 6) |

Also checked: the cross-fighter posture anchor (export_bm.VICTIM_ANCHORS, off) stays worse than the mirror rows on KOF's
ground truth (21 744 rows: mirror mean |dx| + |dy| 12.5 px, centre anchor 20.0, with the flipped-part fix 21.1): a
pixel centre aligns the SAME fighter's two frames (#2), not two fighters. frame_centre now mirrors flipped parts as
draw.s does (it kept them in place: wrong centres for every flipped KOF frame).

Totals over the 55 throw cases: frames apart beyond the source 256 -> 90 (18 -> 12 cases; what is left: #3's toss,
#7, #8). Data cost: victim tables 103,300 -> 134,456 bytes (300 tables), MB1 843,748 used / 204,828 free (bank_proof
ALL OK).

## What changed (one path, data driven)

- export96 `frame_centre_rom`: each per-victim row (victims_all) carries the centre of the frame KOF shows there.
- export_bm `victim_rows`: the victim's posture frame placed so its centre is where KOF's frame's was (same fighter);
  floor rule: KOF's frame on the floor -> the posture frame's lowest pixel there (no deeper than the fighter's own down
  pose), KOF's frame in the air -> never under the floor.
- export_bm `KOF_FALL`: KOF's shared knockdown states in a captured throw play the brawler's knockdown animations
  (as ROM-read throws already did through throwrom roles).
- export_bm `VICTIMS_FROM`: KOF96 throwers carry the KOF98 / 99 roster's own lists (KOF96's same fighters).
- fighter.c `thrown_land`: the landing hand-off is the floor bounce, with the landing motion (capped).
- No new engine path; vrow / bm_vthr / the landing hand-off unchanged in shape.

## Further improvements (for Bruno to choose)

| # | what | gain | cost |
|---|---|---|---|
| 1 | Exact victim frames: export every KOF victim's own frame for each thrown state its game's throws use (no posture vocabulary for same-game pairs); bvrow vpose -> a per-victim frame index | the KOF victim looks exactly as in KOF in every throw (today: the nearest posture, lined up by its centre) | ~1 day; C ROM + 300-600 KB, P ROM small |
| 2 | Grip landmarks for cross-game pairs (the memory idea "throw landmarks"): per fighter and posture a grip spot on the victim (waist / collar) proposed from its silhouette, reviewed in the Lab; per thrower row the source's grip spot; vrow aligns them (the anchor path exists) | SS2 / DD / Kizuna / WHP / LB2 throws on KOF fighters, and KOF throws on those fighters, held at the right spot | 1-2 days (Lab page + review of ~26 x 36 postures, auto-proposed) |
| 3 | Throw swing smoothing: rows in the air at 1x, or the victim's place interpolated between script rows (vrow, by the row clock's fraction) | no 100-190 px one-frame jumps on the over-the-head swings (#6) | hours; changes the 1.5x feel on those rows: needs his call |
| 4 | Full victim matrix audit: every roster fighter as the victim of every thrower (26 x 26, throws_audit victim slot + throw_tie) and KOF96 side-by-side captures | finds the non-KOF victim cases (#9) and checks #8 against KOF96 | tooling ready; ~2 h machine time + a fix pass |
| 5 | Hold finisher as a scripted toss (the throw's own release motion) instead of the generic knockdown arc | each fighter's finisher sends the victim its own way | half a day |
| 6 | Victim lists (command grabs, Rosa's frame lists) in throw_tie (gap, landing) | the up + A grabs measured like the throws | hours |

## Proofs

- Audit before / after: `/data/tmp/throws_t1/before`, `/data/tmp/throws_t1/after6` (tie_*.png, tie_table.txt).
- bank_proof ALL OK (MB1 843,748 used); regress bleed True / True frame-exact (its facing loop now skips the
  non-selectable form billy_super, which crashed it since moriya joined); throw196_proof ALL OK; scenarios
  t1-landing-bounce, t1-kdash-back-landing, t1-own-frames-lying, t1-krauser-lift (scenarios.json, lint_recipe 0; not
  put to the tracker). No attract re-baseline taken.
