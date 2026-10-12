# The Character Lab

Bruno's workbench for the brawler's fighters (2026-10-10): pick a fighter, unlock his moves, assemble what each input
plays, try it in the game in the page, send it to the Player on the tablet, ship it to the game. One template for the
whole cast, one data path from the page to the ROM. This document is the reference; the plain-words page for Bruno is
`brawler-lab/howto.html` (linked from every Lab page).

- Site: https://canneji.duckdns.org/brawler-lab/ (behind the Oros login; files on the VPS in `/data/brawler-lab/`).
- Source: `tools/brawler/chainlab/` (pages and scripts), `tools/brawler/` (compiler, CLIs), `tools/feedback/server.py`
  (the service behind `feedback-api/`), `android/.../CharacterLab.kt` + `Assembly.kt` (the Player).
- Build + publish the site: `tools/brawler/chainlab/deploy_vps.sh [GAME_DIR]` (make_site.py into `SITE`, default
  `/data/tmp/chainlab/site`, then rsync; it never deletes on the VPS). It runs `labpub.py all --if-changed` first
  (`LAB_PUBLISH=0`: not): the shell + packs are published only when the pack format or a fighter's data changed.
- **The shell + packs: ONE command, `make lab-publish`** (= `tools/brawler/labpub.py all`, below "The pack format").

## Two halves: the Workshop (tokens) and the Assembly (token free)

Binding (Bruno 2026-10-10): the **Workshop** is the only place that talks to Claude. It holds the conversation, the
unlock requests and the decoding, which cost tokens. The **Assembly** has no channel to Claude. Every change made there
is compiled by the tooling alone (`arb_compile.py`). The compiler links what exists and **refuses** with a reason
otherwise; it never guesses. A question about a slot goes to the Workshop: "Ask in the Workshop" opens the piece's
thread with a request already filled in.

## The pages (one front page)

| URL | What |
|---|---|
| `lab.html` = `index.html` | **The cast**: every roster fighter (`cast.json`, `chainlab/fighterlab.py`: game.json's roster + what the site holds for him) as his HUD face, name, source game, archetype, dictionary / Workshop / knob counts, his pack and live config revision (read live from `lab/catalogue`, `lab/config`). A search box. Header: The cast, **Game tools**, **How to**. |
| `lab.html?f=<f>&tab=info` | **Info**: facts (source game + bank, scale, archetype, chain length, music theme, select screen, dictionary, S / T piece counts, knobs, pack, shell, the site's build, live config), HUD and win portraits, links, "Play him in game", the live config line. |
| `&tab=dictionary` | **Dictionary**: every animation of his source game's table as a looping clip (`anims.js`, data `review/<f>_anims.json` from `animdict.py`), filters, flags, "I want this one", a queue to Try in game. |
| `&tab=workshop` | **Workshop** (`workshop.js`): unlocked / locked specials and throws, hit classes, a thread per piece. |
| `&tab=assembly` | **Assembly** (`arbitrage.js`, live clips `liveclips.js`; compact rows, see "The compact Assembly"): the arbitration sheet: the chain and its **timing**, finishers, Blitz, air Blitz, specials, air specials, air, grab, fury; piece knobs; Try this sheet in game; Send to Player (and the live auto-send); Ship to game. |
| `&tab=review` | **Review** (`review.js`, revamp phase 4): pieces ranked, the chain proposal, Keep / Drop; `&q=<set>` = a visual follow-up set (`decisions.json`). |
| `&embed=1` | The Player's WebView beside the game (~360-420 px): no site chrome, compact, the Assembly only, the page's own Try hidden. |
| `game.html#<tab>` | **Game tools** (not one fighter's; the game runs in the page, `app.js`): `#stages`, `#enemies` (its move-list editor opens the route-tree editor of the old Chain Lab), `#chars`, `#select`, `#feedback` (`#fb=<id>[&play]` = one note's replay), `#quirks`, `#expose`, `#decide`, `#impacts` (impact sound library), `#sounds` (`?f=<f>`: a fighter's hit sounds). `game.js` routes the hash. |
| `howto.html` | The five steps in plain words. |

One template: each tab's script is loaded once, on the tab's first opening, into its panel (`#dict`, `#ws`, `#arb`,
`#rev`); a fighter whose source game has no dictionary builder (cast.json `engine_note`) gets one honest sentence in
those tabs. Each tab's CSS sits in `lab.html`, scoped by its panel id or by `body[data-tab=...]` (pop-ups are appended
to body). A link to another tab of the same fighter switches tabs without a reload.

**Old URLs** (every one redirects; queries and hashes kept): `anims.html?f=` -> Dictionary; `review.html?f=[&q=]` (and
`#f=`) -> Review; `arbitrage.html?f=` -> Assembly; `workshop.html?f=` (`ask=`, `text=`, `#piece`) -> Workshop;
`decide.html` -> `game.html#decide`; `impacts.html` -> `#impacts`; `sounds.html?f=` -> `game.html?f=#sounds`;
`index.html#fb=...`, `#decide`, `#stages`... (the old Chain Lab front page's tabs) -> `game.html` with the same hash. The
**Chain Lab tab is retired**: its chain tool is the Assembly's chain section (below); `chaintool.js` is gone.

## Pieces: `$NN`, `S-`, `T-`

What a slot can hold. An **animation** keeps its `$NN` (the source game's animation number; saved `anim-<hex>`). A
**decoded program** gets a per-fighter id in decode order, never renumbered or reused: `S-001`... = special VERSIONS
(light / heavy / EX / MAX, ground and air: each its own piece), `T-001`... = throws / grabs / command grabs. The registry
is the source of truth: `tools/brawler/arb_pieces/<f>_ids.json` (details: "Piece ids and the Workshop" below).

## Knobs

Two kinds, one panel (`knobui.js`): steppers, a slider and a number; the default and the range written out; an
override shown by text and shape (bold value, "changed from N", a solid 3 px border), "Back to default" per knob,
"Reset all knobs" per panel.

- **Piece knobs**: each decoded special's key parameters (speed, rise, dive, projectile speed / hits, damage), from
  `knobs.py` into `arb_pieces/<f>.json` "knobs". Under each picked S- piece of a sheet slot, and under each unlocked
  special in the Workshop. Saved in the slot's answer `knobs` `{S- id: {knob: value}}`. Details: "Piece knobs and the
  token-free sheet" below.
- **Chain timing** (the old Chain Lab's chain tool, folded into the Assembly 2026-10-10): under the chain's presses,
  one panel per press: its **hit-stop** (1-60 frames, both fighters freeze on contact; the last press's is every
  finisher's) and its move's **segments**: startup, each active window and the recovery after it, from 0.5x to 2x of
  the source (`gretime_t`, retime.BOUND; a value the game already plays is always allowed). The defaults are what the
  game plays now: his tree's hit-stops and the build's retime targets (`TryIt.plan`: the chain data of his pack's
  manifest, the shell's retime rows from its anchor). A move pressed twice has one timing (retime is per move:
  every use of it takes it). Saved as the sheet answer `chain_timing`, its note = JSON `{hitstop: {a1..aN: frames},
  retime: {move: [frames per segment]}}` (overrides only; "Reset the chain timing" clears it). A press that is not one
  of his moves (an animation `$NN`, an S- piece) has its hit-stop only (no segments). A press that cannot go live
  (several pieces, a throw, more presses than his chain has, a shell without `try3`) says so next to it and plays the
  game's own press ("The chain" below).

## Live clips (the Assembly, 2026-10-10)

Bruno: "take the rendering of animations and specials in the assembly to the next level"; "pre-rendering is no good: I
can't adjust parameters". Every clip of the Assembly is played by the real engine in the page, again ~300 ms after a
change to its pick, its knobs or the chain timing (only clips on screen; "Re-rendering…" meanwhile). The game is not
changed: the page drives the practice mode through RAM and reads back RAM, the picture and the video RAM.

- **Where**: `liveclips_worker.js` (a Web Worker: its own core instance, the shell + his pack from the catalogue, the same
  files as Try in game and the Player) runs `liveclips_core.js` (`LiveSim`; Node proofs run it directly). `liveclips.js`
  makes each clip's TRY blob with tryit.js's own pieces (`TryIt.entry`, `knobsOf`, `chainOf`, `plan`; one encoder:
  `encodeTry`), queues the simulations (visible clips first, the newest change first, one at a time), plays the clips and
  draws the strips. `arbitrage.js`: every slot = one clip (his pieces, or the game's own move when the slot is "now"),
  every chain press, and **the whole chain**. No pack / no worker / a shell without `try3`: the dictionary's static clips
  stay (`&live=0` forces them). The core is built with `-sENVIRONMENT=web,worker,node` and exports `wc_vram`.
- **A clip**: the baseline save state (practice: 1 standing dummy, infinite dummy life, P1's life refilled, drive
  infinite, fury gauge full, the box viewer ON), P1 placed `gap` px from the dummy, the TRY blob written with apply now,
  the input pressed frame by frame (P1 faces right: forward = R): a slot its own input (`liveclips.js scriptOf`: Blitz
  double taps, C specials, jump + air moves, walk-in grab + the hold's buttons, D / down + D with MAX ready); a chain
  press = a chain blob whose press 1 is that press's piece (its hit-stop, every retime row), one A; the whole chain and the
  finishers = A every other frame, the finisher's stick held from the last press on. It ends when P1 is back in neutral,
  his projectiles are gone and the dummy recovered (cap 300 / 420 frames).
- **Boxes**: the game's own box viewer (prac HIT BOXES, `main.c dbg_draw`: the hit test's boxes, 4 corner sprites each,
  300-347) read from video RAM after each frame, then hidden (SCB3 height 0) before the next frame is drawn: the picture
  never shows them. Picture x = sprite x - 8, y = 496 - the y field (calibrated against the brackets). Owners: an attack
  box goes to P1 or his nearest projectile, a hurt box to P1 or the dummy.
- **The strip** (all from the simulation): a bar, one cell a frame (white startup, black active, hatched recovery,
  dotted after his move; ▼ a hit, ▲ the frame shown), startup / active (windows; hit-stop frames are counted) / recovery /
  total, hits + damage (the combo counter), reach (his body's attack box ahead of him), the projectile's px a frame and
  travel, the dummy's reaction (its states and their lengths, its height), the hit class from the data (the Workshop's).
  **Gap** per clip: auto (melee 44 px / others 80, then 150 when there is a projectile, or the reach + 12 when it
  whiffed), near 44, far 150. **Hit boxes on the clips**: one toggle (localStorage), solid + "ATK" = attack, dashed =
  hurt, ACTIVE / HIT tags, black on white.
- **Cost**: ~3.3 ms a frame in the worker on the desktop (a press ~150 ms, Robert's S-012 ~580 ms for 187 frames, the
  whole chain ~0.8 s), boot ~0.95 s once; the shell (52 MB) is fetched once per page. Frames are kept as 8-bit colour
  indexes; past 160 MB (40 MB on a phone) the clips off screen are dropped and simulated again when seen.
- **Proof** `chainlab/liveclips_proof.js SITE|URL OUT` (local: `--stub-dl --catalogue --decisions --core`; `--serve PORT`
  the stub alone; LIVE: `LOGIN_FILE`, decision POSTs answered by the proof, every other write aborted). 2026-10-10, local
  and LIVE (temporary Oros admin, deleted after; robert-arb unchanged): 16 / 16. Robert S-012 on forward + C, speed 7 ->
  12: the projectile measured 7 -> 12 px a frame, active 4 -> 3, hit frame 59 -> 58; press 1's hit-stop 6 -> 26: the whole
  chain 155 -> 175 frames (7 hits both); Hanzo $15C (press 3, picked by the proof: his sheet had moved on to $FC) whiffs at
  the far gap (148 px, reach 41) and hits at 44 px. Screens /data/tmp/liveclips/live, local3.

## The compact Assembly (2026-10-10)

Bruno: "it works but it's really unusable. I spend my time scrolling and scrolling… Curate the information shown… Make it
compact and usable, even on the split mobile phone that is only 6 inches. Cut the fluff out." One template, every fighter:

- **Sticky bar**: his name, ONE status line (saving · `Live r23` (✓ after a send) · `In game 0.10.32`, a failure in bold
  with "see ⋯"), **⋯** = the sheet's tools (Try this sheet in game, Send to Player and the auto-send's message, the live
  config line with History / Revert, the full "In the game" line, reset all knobs, reset the chain timing, links), and a
  one-line section jump bar (Chain · Finishers · Blitz · Air Blitz · Specials · Air specials · Air · Grab · Fury).
- **Sections**: collapsible headers (remembered in the browser). The Chain header holds the length (− N presses +, 2-8,
  the `presses` answer: live and shipped like any pick) and **▶ chain** (the whole-chain clip, inline).
- **One row a slot**: its input (`A2`, `f,f+A`, `C`, `last+u`, `hold A`), the pick as a chip (`$5B atk c far`,
  `S-012 Haoh Shoukou Ken`; the game's S- piece by its id; `— empty` with **+**), **pick** (the picker; it says what the
  game plays now). ● + bold = yours (or a press whose timing you changed). "Can't go live: why" stays on the row.
- **Tap a row**: it opens in place, one at a time: the live clip (fits the width, ≤ ~190 px high on a phone; tiny **gap**
  and **boxes** controls), ONE line of frame data (`8/18/20 f · 1 hit · 2 dmg · reach 93`, `· proj 12 px/f`; the full
  strip text in its tooltip), the bar, "now: …" when yours differs, its knobs (compact: name − value + unit, def N,
  reset), a chain press's **timing** in the same card (hit-stop, startup / active / recovery), **⋯ more** = + add after,
  Clear, Back to now, Reset knobs, Ask in the Workshop. `window.arbOpen(id)` opens one (proofs).
- Measured (headless, same data): Robert 19 721 px (30.8 screens at 360 x 640, embed) -> 1 334 px (2.1); at 1280:
  17 742 -> 1 125 px; Hanzo 19 624 -> 1 298 (LIVE, 4 presses). An open press ~500 px (< 1 phone screen), a special ~320.
  `liveclips_proof.js` (updated for the rows) 16 / 16 local and LIVE (temporary admin, deleted; no answer or live config
  changed). Screens /data/tmp/compact.

## Live config, auto-send, apply at neutral

The **live config** is one blob per fighter on the server (`feedback-api/lab/config/<f>`): the TRY blob (`lab.js
encodeTry`: the queue, the 27 arbitration slots, knob rows and, since 2026-10-10, **the chain**: version 3 below). The
Assembly writes it **by itself** 1.5 s after the last change (admin accounts; a viewer sees why not), and once on opening
when the answers are newer than the live config; "Send to Player" resends by hand. The Player writes it (load 6); the
game applies it when P1 is next in neutral (standing / walking) unless "Apply now". Every PUT is a revision; History and
Revert on the "Live config" line. **Nothing is dropped silently** (Bruno's note 20261010-210158-5d29: his Hanzo chain of
dictionary animations went live as an empty blob): every pick that cannot go live shows "Can't go live: why" next to its
slot (`TryIt.issues`, the same checks the Send makes), and the Send's line and the revision's note list what was left
out (`json.lab_try.try.left_out`). Details: "Send to Player" and "Live config per fighter" below.

### The chain (TRY blob version 3, 2026-10-10)

Bruno (binding): "There is no tree. We simplified the design: there is 1 chain with a bunch of finishers." The live path
says exactly that: the TRY blob carries `[LS_CHAIN 0x81][2n][n entries][n words: hit-stop << 8]` = presses 1..n (n = his
chain's length, the archetype's; the last press = the neutral finisher) and per retimed move `[LS_RETIME 0x82][1 + k]
[move BA_*][k targets]` (0 = the source's segment). A press entry is `LE_MOVE | m` (0x4000: his standard move m, played
as a normal: its segments, its retime), an animation `$NN` of his dictionary (his pack's LAB special) or `LE_SPEC | k`
(an S- piece), or `LE_NONE` (the game's own press); hit-stop 0 = the game's; the last press's hit-stop is every
finisher's. The finishers by stick are the slots `fin_*`, the hold the `grab_*` slots (as before). Both records have the
slot records' shape (`[id][n][n words]`), so a reader of version 1 / 2 walks over them (the Player's parse is unchanged).
`lab.js encodeTry` (cfg `chain: {entries, hitstop}`, `retime: [{move, targets}]`) is the one encoder; a blob without them
is byte for byte version 1 / 2 as before. `tryit.js chainOf` makes it from the sheet's presses and timing (a picked
animation that is one of his moves becomes `LE_MOVE`).

The game (`fighter.c lab_chain`, Lab builds and the normal build alike: only the Lab writes it): his exported tree is
copied into RAM, the main line's nodes (root, A, A...) cloned to its end and given the presses (a lab entry: rnode flag
`RF_LAB`, the entry in anim | weight << 8), `route_tab[his fighter]` pointed at it; a blob without a chain puts his
exported tree back. An `RF_LAB` node plays its entry as the Try queue does (`lab_node` -> `lab_entry`: free, not
invincible, the Blitz's role) and stays a link of the chain: on a hit a buffered A takes the node's links (after the
hit-stop, once its hits came, within the attack buffer), its end after a hit opens the chain window, its hits freeze
for the node's hit-stop. The chain advances only on a hit, as every chain does: a press that whiffs ends it (Hanzo's
$15C, SS2's close C+D, is an anti-air whose box sits 88-108 px up and 12-40 px ahead: it whiffs on a standing dummy).
lstat refusals 10 (a chain length not his chain's), 11 (a press that cannot be one), 12 (a retime row). TRY_MAX 1280.
The shell declares the feature `try3`; packs need nothing new (no pack rebuilt).

**Load 5** (the chain override `'L' 'C'` after the TRY blob, `encodeOverride`) is legacy: no page writes it any more;
the game and the Player still take one (an old live config, e.g. Iori's r5), and load 1 (a whole tree into lab.buf)
stays for the Game tools' route-tree editor (enemies). Player 0.0.34 shows "+ CHAIN" for a version-3 chain too.

## Try in game

"Try in game" (`tryit.js`) runs the game in the page: the Character Lab **shell** with the fighter's **pack** swapped in
(the Player's own files from the catalogue, sha256 checked, `wc_swap_pack`; P1 = the slot fighter vs Ryo): his newest
pack the shell can load. The one path: the per-fighter Lab builds (`make LAB_FIGHTER`, `rom/lab-<f>.neo`) are retired. "Try this sheet in game" applies the whole sheet now: its slots, its knobs, its
chain with its timing (load 5 + load 6), as the Player will. Keys: W A S D stick, U A, I B jump, O C, P D, Enter the
practice menu, `.` a frame while paused; gamepad and touch pad too. Details: "The Fighter Lab" and "The Chain Lab, the practice mode, the live
config / Try in game" below.

## The pack format (2026-10-10)

Bruno (binding): "why would the packs need a rebuild? that's insane". An engine or game change rebuilds and publishes the
SHELL only; every pack already published keeps loading into it. Before, a pack's data held absolute addresses of the
shell's own tables, `lab_pack.py` refused any byte difference outside the slot and the "engine" string was the version +
a fingerprint of the whole shell: any change forced every pack to be rebuilt.

**What a pack may reference outside its slot** (scanned 2026-10-10: every relocation of the slot's sections and of its
elements in the robert / kim / iori / hanzo_ss2 builds): no address of the shell's code or tables at all, except
- the slot's **element of every per-fighter table** (`bm_chars[]`, `bm_seg[]`, `bm_air[]`, `bm_hsnd[]`, `bm_xthr[]`,
  `bm_hspark[]`, `bm_head[]`, `ai_ready[]`, `gblitz_rom[]`, `gblitz_can[]`, `grun_bob[]`, `grun_dash[]`, `gfury_area[]`,
  `gwalk_rom[]`, `pb_of_fighter[]`, `roster_unlock[]`, `dtier_rom[]`, `portrait_pal[]`, `gknob_rom[]`, `gkcat_rom[]`,
  `bm_lab`, its 16 `gretime_rom` rows): wherever the linker put those tables. Now the slot **HEADER** at a fixed place
  carries them (`lab_pack.py HDR_ARRAYS`), and the shell copies the tables into RAM at every reset with the header's
  element in the slot's place (`examples/brawler/labslot.h`, `main.c lab_slot_init`; the slot id and its LAB special's
  fighter resolved to the shell's). Lab builds only: the Player's game has none of it.
- **numbered game-wide tables** the data indexes: the victim postures (`bchar_t.vposes` is indexed by the whole list),
  the source reactions (`bm_sreact`) and the shared effect palettes (`bm_sfx_pals`): the "shared ids" (below).
Everything else a pack's data points at is its own (the slot's sections, its bank).

**The slot's throws, victim side** (2026-10-12, after 0.10.70's per-victim offsets, `examples/brawler/vthrow.h`): the
thrower x victim tables (`bm_vthr`) never name the slot, as a thrower or as a victim, so no address outside the slot
depends on who fills it (0.10.70 broke STRICT: the slot took its source fighter's bank spec in the victim lookup, so the
roster's copy of the slot fighter lost its victim rows and every table after them moved, per slot fighter). The slot's
own rows are its pack's, in `.labslot`: `slot_vthr` (`bvslot_t`, export_bm.py `slot_tables`): its row (his throws
against every victim of his game) and his column (his rows as the victim of every thrower of his game), naming the
pack build's fighter ids with their keys (`bm_rkey`: the bank spec's CRC-32), resolved to the shell's ids at power-on
(`main.c lab_vslot_init` -> `lab_vmap`; a fighter the shell does not have: none); a thrower whose script's row count
changed since the pack: the script's rows. The header's word at +12 (4 zeros before) points to it: a pack from before
it has 0 there and plays the script's rows, as it always did, so the format stays 1 (its structs are guarded apart:
`lab_pack.py VTHR_ABI`). The mirror match (the slot vs its source fighter) plays the script's rows, as in the roster.
Proven 2026-10-12: the shell + all 15 Lab packs pass `--strict` (the slot's tables: 4-23 KB of .labslot; the KOF ones
41-50 pairs, SS2 / Kizuna none, as in the roster); `tools/brawler/labthrow_proof.py` (our emulator): Terry's pack in
the shell throws Ryo forward / back and is thrown by him frame for frame as the roster's Terry, from .labslot rows
(`--old`: the header word zeroed, the script's rows both ways); the Player's game byte-identical.

**The regions** (the shell's ANCHOR says where; `lab_pack.py anchor lab-shell.neo` prints it):

| Region | Where | Kind |
|---|---|---|
| P: the slot header + `.labslot` (its first-MB tables) | $E0000-$E03FF + $E0400-$FFFFF | fixed |
| P: its P2 bank (its banked tables; addresses in the bank window) | any bank (the shell's last) | relocated |
| S: its HUD face | `PORTRAIT_TILE` + slot x 16 | relocated |
| M: its voice records (both overflow slots) + enable bits | the KOF98 driver's tables | relocated |
| V: its voice samples (the records name absolute V addresses) | $C00000, 512 KB (`build_snd.py SLOT_V_AT`) | fixed |
| C: its tiles (its frames name absolute tiles) | tile 2048, 24,576 tiles (`export_bm.py SLOT_TILE_FIRST`, placed first) | fixed |

**The anchor** (P $DC000, 16 KB, written by `lab_pack.py seal` after every shell / pack link, as the header): `NGLA`, the
format, the slot id, each region (kind, ROM, offset, size), the **features** string, then a JSON for the Player and the
pages: the RAM map (`ram`: the lab mailbox, prac, P1's state, the neutral states), the layout (fighter_t fields, the
symbols), the roster order, the throws, the chain rules, the retime rows. The Player and `tryit.js` read the RAM map and
the slot from the SHELL now (a pack's own copy, kept for Players before 0.0.33, is its build shell's).

**Compatibility = format + features.** The shell declares `{format N, features}`: every program op it plays (`P_*`
names: `warp`, `lanim`, `catch`...), the knob kinds (`knob-set`, `knob-pspeed`, `knob-phits`, `knob-dmg`), `lab` (the
LAB special), `try2` (TRY blob v2: knob rows), and its shared ids (`vp:<hash of the postures>`, `sr<i>:<hash>`,
`sp<i>:<game:key>`). A pack declares `{format N, needs}` computed from its data (`lab_pack.py needs`: the ops of its
programs, its knob catalogue's kinds, its LAB special, the shared ids it uses). **A pack loads iff the same format and
needs ⊆ features**: `pack_swap.c` (the wasm core and the Player, from the shell's anchor in the loaded ROM), the Player
(`CharacterLab.kt`, before the download), `tryit.js` (`lab.js packCompat`), `lab_pack.py check` / `labpub.py`. A refusal
says why in plain words ("it needs warp, which this shell does not have"; "a pack from before the pack format: rebuild
it"). The format changes only when the slot's ABI does (a header table's element size, a struct its data is made of, a
fixed region's place, an op or knob kind renumbered): `lab_pack.py abi_signature` is checked at every seal against
`FORMATS`, so such a change stops the build until FORMAT is bumped (labslot.h `LAB_FORMAT`, `pack_swap.h NGPK_FORMAT`,
`lab.js PACK_FORMAT`; then every pack is rebuilt once). New ops and knob kinds are appended (features), never renumbered.

**The file**: the container the Players 0.0.28+ read ('NGPK' 1; its region records now carry the kind and a relocated
flag in bytes the old reader ignored); the manifest starts `{"ngpk":{"format":N,"needs":"..."}` (the C reads it there)
and holds the pack's page data (`page`: his LAB special's animations, moves, his chain entry and retime rows: the site no
longer ships `rom/shell-*.json` / `rom/pack-*.json`; `tryit_site.py` is gone) and `data_sha` (its sidecar: the hash of
its data alone, what `labpub.py` compares). `lab_pack.py make`'s old "identical outside the slot" check is the DEBUG
option `--strict` (`make LAB_PACK=f STRICT=1`; `labpub.py all` uses it: it catches a per-fighter table the header misses).

**The one command**: `make lab-publish` = `labpub.py all`: builds the shell and the full pack of EVERY roster fighter with
a dictionary and a piece library (`animdict.DICTS` + `arb_pieces/<f>.json`), then publishes the shell if its bytes
changed and each pack whose data (`data_sha`) differs from his newest published pack the shell can load. `--if-changed`
(deploy_vps.sh): nothing at all unless the format or a fighter's inputs changed (`packs/stamps.json`: his roster entry,
piece library, routes, voices, the exporters). `--only f,g`, `--dry-run`, `--no-build`. The catalogue (`GET
lab/catalogue`) gives the shell's `format` + `features` and per fighter `all` his versions with `format` + `needs`: the
Player and the pages pick his newest compatible one.

**Proven 2026-10-10** (`/data/tmp/pf/proof/`): shell + robert / kim / iori / hanzo_ss2 packs built (all 13 dictionary
fighters' packs pass `--strict`); then fighter.c changed (4 KB of tables + 6 bytes of RAM added: the code, the tables and
the lab mailbox moved) + VERSION 0.10.28, the SHELL alone rebuilt: the 4 old packs `lab_pack.py check` "loads"; in the
wasm core (`packfmt_proof_node.js`) each old pack swapped into the new shell plays his chain (A every 6 frames) and his
C special frame for frame identical (226 frames) to the pack rebuilt for that shell, and to the roster's own copy of him
in the same shell; the rebuilt packs' data are byte-identical to the old ones (`data_sha`: only the legacy fields
differ). Refused in plain words: an old-format pack ("a pack from before the pack format ...: rebuild it", -8) and
hanzo_ss2 by a shell without `warp` ("it needs what this shell does not have: warp", -11). The normal game build is
byte-identical to the one before the change (brawler.neo, bank_proof ALL OK). Published with `labpub.py all`: shell
20261010-175736 + 13 packs (format 1); `--if-changed` then: "nothing to do". LIVE (temporary Oros admin through the real
login, deleted after; writes aborted): consolidate_proof.js 61 / 61, Try in game in "pack" mode, the chain timing frames
as before (0 / 11 / 26 / 65 / 104; press 1 startup 4 -> 8 and hit-stop -> 18: 8 / 27). Player 0.0.33 (AVD JanusPhone,
release APK signed as 0.0.32, not published): the old catalogue's packs shown "the shell cannot load it" with the reason;
the new one: 13 faces, Hanzo swapped in (practice), Iori's live config r5 + chain applied (IN SYNC r5 + CHAIN) through
the shell's RAM map. Players 0.0.32 still load this set (same container, the legacy engine / ram fields); after a
shell-only publish they refuse the packs (engine differs) until 0.0.33 is installed.

## In the game: Ship to the game + the ship service (2026-10-12)

Bruno 2026-10-12: "Can it build, increase the revision, and deploy on the VPS for each new change that I deem ready to
ship?" Live saves still go to the Player's Character lab at once (unchanged); the GAME (the Player's brawler, the VPS
download) changes only on his word: the **"Ship to the game"** button in each fighter sheet's top bar (the Assembly,
`lab.html?f=<fighter>&tab=assembly`) queues `POST lab/ship/<f>` (admin; the live revision). The 60 s auto-ship is gone.
The bar says `Queued` / `Building 0.10.N…` / `Shipped 0.10.N` / `FAILED ✗`; ⋯ shows the full line (the step and its
one-line reason). The button is disabled while a request of his is queued or building.

### Ship service

`brawler-ship.service` (systemd --user on brunux; unit `tools/brawler/brawler-ship.service`, nice 10,
Restart=on-failure) runs `labcfg.py ship-worker --conf /data/brawler-ship/ship.json` from the **ship checkout**
`/data/brawler-ship/repo` (a detached git worktree nobody edits; `geolith` + `tools/neosdk` symlinked in). Every host
path is in the conf (`tools/brawler/ship.example.json`: repo, logs, jobs, nice, poll, lab_host, env BRAWLER_CORE /
PATH); `lab_host ""` = the feedback service by local curl (the service running on the VPS itself). It polls every 30 s;
one request at a time, a fighter's newer request supersedes his queued older one (`dropped`). Each request, stopping at
the first failure (`failed`: "<step>: <reason>", the checkout reset; nothing reaches the VPS before the checks pass):

reset + `git fetch origin brawler` + `merge --ff-only` -> VERSION +1 -> `arb_compile.py <f>` (sheet -> game.json, build,
every linked slot checked; "game.json roster changes: none" = `done` "nothing changed", no new version) -> `rm build/*.o`,
`make -C sdk`, `make -j4` -> `bank_proof.py` ALL OK -> `regress.py --bleed-only` (bleed True / True) -> `git
commit` (game.json, VERSION, docs/brawler_gold.md: "Brawler 0.10.N: <f> shipped from the Assembly (rev R)"; scenario.py
finds the build by it) -> `make publish-vps` -> `scenario.py publish` -> `labpub.py all --if-changed` -> `git push origin
HEAD:brawler` (a failure: the checkout reset to what it pulled, the local commit dropped) ->
`done` "shipped 0.10.N". The main tree's `brawler` then lags origin: `git pull --rebase` before committing there.

    systemctl --user status brawler-ship            # state + last lines
    systemctl --user stop brawler-ship              # stop (requests stay queued)
    systemctl --user start brawler-ship             # start (enable --now: also at login)
    systemctl --user restart brawler-ship           # after editing ship.json
    journalctl --user -u brawler-ship -f            # the service's log
    ls -t /data/brawler-ship/logs | head            # one log per request: <id>.log (every step's output)
    python3 tools/brawler/labcfg.py ship-pending    # the queue; `ship F` queues one from the shell

First setup on a host: `git worktree add --detach /data/brawler-ship/repo origin/brawler`, symlink `geolith` and
`tools/neosdk` into it, copy ship.example.json to /data/brawler-ship/ship.json and fit it, a first `make -C sdk && make
-C examples/brawler` there (full export), then install the unit. Needs: ssh key to root@195.201.91.211 (labcfg / arb_compile
answers / publish), `gh auth` for the push, the ROM / dictionary inputs at their /data paths.

### The Factory's Levels (2026-10-12)

`/brawler-factory/?tab=levels`: each campaign stage's name (1-12 characters A-Z 0-9 space . ! -, shown in the HUD
before WAVE and on GAME OVER: `gstage_names`), background (a stage of the build wide enough for its lock points) and song
(a songs.json song, with a 20 s MP3 preview). Waves are not edited there. Saves go to the Levels draft (`GET|POST
lab/levels`, `LAB/levels.json` + `levels.history.jsonl`); "Ship pending changes" sends `ship_batch {levels: true}` and
the ship service runs `levels.py merge` (only those three game.json lines per stage; a refusal = `failed` "levels:
REFUSED: <reason>") before the build; the history shows `levels: stage 2 music STAGE_HIGHWAY -> THEME_KIM`. At start and
after each shipped version the service runs `levels.py previews` (missing MP3s, played by the ship ROM in our emulator,
cached in /data/brawler-ship/previews, rsync'd to the VPS /data/brawler-factory/songs/) and posts `levels.py state` to
`lab/levels_game` (what the page shows as "the game"). In-game check: `levels_check.py GAME_DIR OUT`.

### The Factory's Game tab and the draft sections (2026-10-12)

`/brawler-factory/?tab=game` (`factory/game.js`): the game-wide numbers and texts of game.json that recompile with no
token (`tools/brawler/gamecfg.py`: Meter, Combat (damage tiers, Blitz, chain window / buffer / juggle limit / stuns, the
super flash), Physics (walk / run, jump timings), Throws (throw_swap, throw_handoff), Texts (each fighter's ending story,
the thanks line)), each with its range (build_tables.py's asserts + their cross rules), its default (the value of
2026-10-12), "changed from", reset. Levels and Game are both a **draft section**, one mechanism: `server.py SECTIONS`
(name -> its shape check; `GET|POST lab/<name>`, `LAB/<name>.json` + `.history.jsonl`, `POST lab/<name>_game` = the ship
service's report), `labcfg.py SECTIONS` (name -> its tool: `<tool> merge GAME DRAFT.json` writes it into game.json with
"<name>: ..." change lines or `REFUSED`, `<tool> state GAME` is reported after each ship), `ship_batch {<name>: true}`.
A new section = one entry in each table + its tool.

## The server API

The pages and the Player talk to the feedback service (`tools/feedback/server.py`, unit `brawler-feedback`): the pages
at `brawler-lab/feedback-api/` (the Oros cookie), the Player at `/brawler/lab/` (its Oros token), the desktop over ssh.
- `GET lab/me`, `GET|PUT lab/config/<f>` (+ `/hash` the poll, `/history`, `/rev/<n>`, `POST /revert`), `POST lab/ship/<f>`,
  `GET lab/ship[?status=&fighter=]`, `POST lab/ship_done {id, status building | done | failed | dropped, note}`, `GET lab/catalogue`, downloads `/brawler/lab/dl/...`: "Where it answers, who may
  call it", "Live config per fighter", "The ship queue", "Catalogue" below. Writes need the Oros
  `admin` role.
- The sheets' and the Workshop's answers: the decisions store, `POST decision` `{set, id, choice?, label?, note?,
  question?, pieces?, knobs?, flags?}` merged into `DATA/decisions/<set>.json`, `GET decisions/<set>`. Sets: `<f>-arb`
  (the Assembly: one id per slot, `presses`, `chain_timing`), `<f>-workshop` (threads, the Workshop's knob values),
  `<f>-anims` (the dictionary's flags / wants), `review-<f>`, `<f>-sounds`, `impact-sounds`.

## CLIs (desktop)

| Tool | What |
|---|---|
| `tools/brawler/arb_compile.py <f> [--dry-run] [--answers FILE] [--no-build] [--no-check] [--compare GAME_JSON]` | the sheet compiler (above); `arb_compile.py pieces <f>` regenerates the piece library `arb_pieces/<f>.json` (+ ids, + knobs) |
| `tools/brawler/workshop.py list [f] / reply <f> <piece> "<text>" / unlock <f> <piece> / publish <f>` | the Workshop threads and unlocks |
| `tools/brawler/labcfg.py list / show / history / revert / export / put / ship-pending / ship / ship-done / ship-worker` | the live configs, the ship queue and the ship service ("Ship service") |
| `make lab-publish` = `tools/brawler/labpub.py all [--if-changed] [--only f,g] [--dry-run]` | THE ONE COMMAND: the shell + every fighter's pack, built and published where changed |
| `tools/brawler/labpub.py list / publish-shell / publish-pack / publish-face / remove-*` | the shell / pack catalogue (format / features / needs from the files) |
| `tools/brawler/lab_pack.py seal / make [--strict] / info / anchor / check / apply / abi` (`make LAB_SHELL=1`, `make LAB_PACK=<f>`) | the shell and the packs, the pack format |
| `tools/brawler/knobs.py`, `tools/brawler/piece_ids.py` | the knob catalogue, the piece ids (run by `arb_compile.py pieces`) |
| `tools/brawler/chain_save.py` | the retired chain tool's save path (decisions set `chain-tool`): old saved entries only |

Proofs (headless Chrome, puppeteer-core with `NODE_PATH=/home/bruno/CLProjects/NeoGeo/node_modules`):
`chainlab/packfmt_proof_node.js SITE SHELL OUT f:OLD.pack:NEW.pack[:IX] [--old P] [--lacks P:feature]` (the pack
format: old packs in a new shell vs rebuilt ones, frame for frame, + the refusals),
`chainlab/consolidate_proof.js SITE|URL OUT` (this layout: the cast, the five tabs, the embed, the Game tools' tabs,
every old URL, the chain timing measured in the game), `fighterlab_proof.js`, `knobs_page_proof.js`, `tryit_proof.js`,
`packs_proof_node.js`; `knobs_proof.py`, `practice_proof.py` on the desktop core.

## Proven 2026-10-10: the consolidated Lab

`chainlab/consolidate_proof.js` in headless Chrome at 1280 and 400 px, against a local site + stub service and LIVE on
canneji (a temporary Oros admin through the real login page, deleted afterwards; every decision POST answered by the
proof, every other write aborted: 6 PUTs of the auto-send blocked, `robert-arb` and the live configs untouched): 61 / 61
checks. The cast at lab.html and index.html; Robert's Info / Dictionary (433 animations) / Workshop / Assembly (5 timing
panels) / Review; Haohmaru's Dictionary note; the embed (no chrome, the timing shown); the Game tools' ten tabs filled and
hash-routed; 14 old URLs landing on their tab. The chain timing measured in the game (Try this sheet in game, Robert's
pack on the shell, A every other frame, the game's own event log): at the game's timing press 1 connects 4 frames after
its start and press 2 starts 11 frames after press 1; with press 1's startup 4 -> 8 and hit-stop 6 -> 18 set through the
page's knobs: 8 and 27 (+4, +16 = the added frames exactly); "Back to default": the same frames as before (0 / 11 / 26 /
65 / 104 from the first press). Found and fixed on the way: a load written while the game had not taken the last one was
lost (a pending TRY blob applied at neutral answered "taken" before the new one was read; the chain's load 5 then
overwrote that load 6): tryit.js now waits for `lab.load` to clear before every write. Screens: /data/tmp/consolidate/
(local3, live).

## Hanzo (SS2) — Character Lab, 2026-10-10: the first Samurai Shodown II fighter in the Lab (Bruno: the warp "is going to be his BREAKER special")
- C (neutral, also the breaker) = 63214BCD Ninpou Utsusemi (S-013): gone in smoke, P_WARP onto the one he hit (else the
  nearest opponent on his lane), the spinning drop from 128 px (SS2's 195, fitted), the bounce back on a hit. Breaker:
  2 drive chunks, white blink; without the drive 12 life, red blink (tools/samsho2/hanzo_breaker_proof.py, 4 / 4 PASS).
- forward + C = 6321S Ninpou Bakuen Ryuu (the fire; was the neutral C until then).
- Throws (2026-10-11: SS2's throws all land IN FRONT; the slot plays a T- piece the brawler's way round: forward + A in
  front, back + A turned, behind; docs/brawler_data_model.md "Throw direction"; body_toss = SS2's CLOSE A+B 276, the far
  278 whiffed at chain range and so was never cancellable, export_ss2 MOVES):
  forward + A slash throw (T-001), back + A kick throw (T-002); SS2's Earthquake throw (class 4 action 4) is the
  plain piece T-003 (his pack's extra paired throw), no automatic choice by the victim (Bruno: "the engine doesn't need
  that"); the air throw Kuutengeki (T-004) is decoded, not playable (no air grab).
- Pieces (arb_pieces/hanzo_ss2_ids.json): S-001..S-003 6321 A / B / A+B, S-004..S-006 623 C / D / C+D, S-007 WFT,
  S-008..S-010 j.4123 A / B / A+B, S-011 / S-012 Kage Bunshin A / B (P_WARP screen mode + the clone), S-013 Utsusemi,
  S-014 Kagemai, S-015..S-017 Mozu Otoshi out of a run (its backward leap: pure data); T-001..T-004 above.
- Decoded, NOT imported (Bruno decides; /data/neogeo_dict/samsho2/README.md "Character Lab"):
  - Kagemai's invisibility (S-014 plays only its two animations): needs an engine "hidden" state on fighter_t: the
    sprite not drawn for 440 frames, cleared by his attack / a hit after a 9-frame every-other-frame blink, or by the
    move again; and (a design choice) whether the enemies' AI should ignore a hidden player.
  - The SD pose (6 4 6 4 6 4 2 + A, every SS2 fighter's anim 82 for 300 frames; handlers_ss2.han_sd decodes it): its
    drawing uses SS2's palettes 68 / 69 (+ a flicker key), past the 8 a fighter loads: needs a 9th / 10th palette
    for the fighter (bchar_t npal, MAX_PALS) or the SD sprite recoloured into his 8; then it is pure data (anim 82
    held). Its toggle (the input again ends it), the puff (effect 71) and the white flash are extras.
  - The air throw T-004: needs an air grab (both airborne, close, B / A+B) or a fourth paired-throw slot.
  - Kage Bunshin's stance follow-ups (a button = far A / far B / far A+B / crouch C / crouch D) and the clone's log.

## Haohmaru and Genjuro (SS2) — Character Lab, 2026-10-11 (Bruno: "create Genjuro and Haohmaru full pack")
Hanzo's path for the next two SS2 fighters (roster `haohmaru` / `genjuro`, banks `samsho2:haohmaru` / `samsho2:genjuro`):
animdict DICTS (647 / 644 animations), every recogniser result decoded as a program (handlers_ss2.SPECIALS), each button
version its own S- piece, SS2's three throws as T- pieces, knobs from the programs (knobs.derive_ss2), SNK's SS2 names
(snk.fandom.com "Samurai Shodown II/Move List", read through its API). The normal game build is byte-identical (its
specials are the same programs; the new ones are LAB_ONLY).
- **Haohmaru** (arb_pieces/haohmaru_ids.json): S-001 214A Sake Kougeki, S-002 / S-004 / S-003 236 A / B / A+B Ougi Senpuu
  Retsuzan, S-005 236K the feint (2 3 6 + C / D / C+D: one descriptor $35536, one piece; anim 293 has no attack record),
  S-006 3 4 1 2 3 4 2 1 + B+C Tenha Fuujinzan (the secret move, NEW: result 53 $357DE, anim 336 2 px a frame + object 47
  = anim 337 pinned to him, then 623S A+B's jump, LAB_ONLY), S-007 / S-009 / S-008 623 A / B / A+B Ougi Kogetsuzan,
  S-010 / S-012 / S-011 623 C / D / C+D Ougi Resshinzan, S-013 WFT Tenha Seikouzan; T-001 slash throw (B / A+B, anim 274),
  T-002 kick throw (D / C+D, 346), T-003 the Earthquake throw (class 4 action 4, anim 270: a plain piece). 33 knobs.
- **Genjuro** (arb_pieces/genjuro_ids.json): S-001 / S-003 / S-002 214 A / B / A+B Oukazan (the card), S-004 / S-006 /
  S-005 236 A / B / A+B Sanrensatsu (three parts, the next part = C again), S-007 / S-009 / S-008 623 A / B / A+B Kirihaku
  Kouyokujin, S-010 WFT Gokouzan, S-011..S-013 / S-014..S-016 the slash chain's AUTOMATIC versions (NEW, LAB_ONLY: results
  53-55 two parts, 56-58 three parts; SS2's player reaches 53 / 54 only by 2 1 4 + A / B with his card on screen, the rest
  is the CPU's: handlers_ss2.gen_auto): the next part with no press once the part connected and a window step shows
  (`auto` condition: P_BR window / hit), P_HITOFF per part, turned to face the opponent when he is behind ($56A26: P_BR
  passed v -1 + P_TURN); T-001 slash throw, T-002 the same throw (SS2 gives him one: B / A+B and D / C+D both play 274),
  T-003 the Earthquake throw. 38 knobs.
- Packs (format 1, published 2026-10-11 against the live shell 20261010-222951, no shell change: every op they use is a
  feature already): haohmaru 1,778,200 B (.labslot 74,208 / 130,048, bank 307,000, tiles 10,044 / 24,576, voices 11 / 48),
  genjuro 1,707,996 B (80,120, 343,468, 9,314, 12); their LAB specials hold 617 / 647 and 610 / 644 dictionary animations
  (the rest need palettes past his 8, as Hanzo's).
- Check (`tools/samsho2/ss2_lab_proof.py <f>`: every S- / T- piece from a slot override in the shell + his pack, our
  emulator, a training dummy): Haohmaru 16 / 16, Genjuro 19 / 19, in this branch's shell and in the published one.
  `handlers_ss2.py check haohmaru genjuro`: the game's programs unchanged; 53-55's captures played the card (another
  entry won), so the automatic chain has no SS2 capture to compare.
- The Assembly's "now" (arbitrage.py): an SS2 roster special named by its base input (`623S`) resolves to the version
  the game plays (roster variant, else the heaviest), so the slot shows its animations and S- id.
- Decoded, NOT imported:
  - The SD pose ("Toy Transformation", 6 3 2 1 4 6 4 + B for both, result 45, anim 82; handlers_ss2.han_sd is generic):
    Haohmaru's drawing needs palettes 64 / 1065, Genjuro's 36 / 116 / 1117, past the 8 a fighter loads (bchar_t npal /
    MAX_PALS, or the SD sprite recoloured into his 8).
  - Tenha Fuujinzan's screen flash ($358B0: object 47 hits a non-guarding opponent high up -> the backdrop $6A66A) and
    object 47's end on its first hit ($301CA): the brawler plays it pinned for its whole animation (the crescent's rule).
  - The weapon loss on the WFT hit (+$B8) and the unarmed throws (class 4 actions 11-13, anims 275 / 347): no weapon
    state in the engine (TODO #175).

## SS2 move standard + Haohmaru's picks — 2026-10-11 (voice notes 112029, 112056, 112545, 112722 -> 113641)
- **The SS2 air standard** (112029: "as a standard for all Samurai Shodown 2 characters"): jump + A (straight and
  forward) = SS2's air A+B, jump + down + A = SS2's air C+D (the high kick). The importer's default, not per-fighter
  edits: `build_tables.AIR_BANK['samsho2']` (`air_of(r)`: AIR_DEFAULT < the bank game's < roster[].air; build_tables,
  arb_compile's "now", arbitrage.py) with `export_ss2.air_moves`: the animations read from each fighter's class 1
  actions (subs 13 / 14 air A+B straight / forward -> atk_cd_jump / atk_cd_jump_diag, 28 / 29 air C+D -> atk_ab_jump /
  atk_ab_jump_diag): Haohmaru 284 / 356, Genjuro 284 + 288 forward / 356, Hanzo 284 / 356 + 361 forward. (The brawler's
  `cd` names are SS2's A+B, its heavy slash, as body_toss; `ab_jump` = SS2's C+D.) Hanzo's air shuriken j.4123S moved
  from air_specials dA (it took the down + A normal's place) to dC (jump + down + C, a C special's meter).
- **Haohmaru**: C (and the breaker) = 623AB, S-008 (112056); MAX (down + D, red) = 34123421BC Tenha Fuujinzan, S-006
  (112545; damage_raw.json max = its source 8 -> the MAX tier 180; the flash / object-end quirks above stay); Blitz
  (113641, replaces 112722's ff): ff = his far A+B (`moves.atk_ab_far = $116`, anim 278), dd = 214A S-001, uu = 623C
  S-010, du none.
- Engine / export paths added: a button version named by a roster slot (specials, Blitz, fury, max) is exported as its
  own special (export_ss2 `extra.inputs`, handlers_ss2.special vdef), a LAB_ONLY special a slot names likewise; a Blitz
  slot naming a ground normal (arb_compile's "a normal as the Blitz") is played by the tree's dash entry
  (build_tables.blitz_normal -> chain_cfg 'dash' -> routes.chain_tree; blitz_rows 0xFE); roster_export carries `blitz`
  (named_specials takes a Blitz's piece into the pool).
- Check (our emulator, training dummy Ryo): Haohmaru C fires 623AB and knocks down, the breaker with / without drive
  plays it; ff -> atk_ab_far, dd -> 214A, uu -> 623C, MAX -> 34123421BC, each hits; all three SS2 fighters' straight /
  forward jump + A -> atk_cd_jump(_diag), jump + down + A -> atk_ab_jump(_diag), each hits (16 / 16 rows).


## Haohmaru round 2 + the SS2 hit standard — 2026-10-11 (notes 112056 / 112545 reopened, 120326, 115835)
- **Voices of every SS2 piece** (112056: "the sound of Haohmaru's voice when doing Kogetsuzan is missing"): voices.py
  `samsho2_list` lists the voice uses of EVERY special piece (each button version, 623AB, and the Lab-only ones,
  34123421BC), so whatever special / fury / MAX a slot names keys the voice SS2 sends for it (its step sound >= $100
  at the move's start). Haohmaru C 623AB -> voice 14 ($1A93, his Kogetsuzan shout), MAX -> 16 ($1A95); likewise every
  version piece of Genjuro / Hanzo SS2 (Hanzo's breaker 63214BCD now speaks too). Voice ids unchanged.
- **Tenha Fuujinzan** (112545) measured in SS2 (`tools/samsho2/tenha_ss2.py`): 12 hits, all by the wind (object 47),
  landing while Haohmaru shows his own 336 steps 2 10 12 20 22 30 32 40 42 52 53 and his rise's (264) step 0; P2 reels
  standing (class 3 action 4) after the first 11, is launched (action 73) after the 12th. The brawler adjudicates them
  as HIT BOXES ON HIS OWN STEPS (no engine change): `handlers_ss2.TENHA_HITS` {his step: the wind's step} -> the
  importer's `E(hits={step: SS2 records})` adds the wind's attack records to those steps (each its own hit), the wind
  is drawn only. Per hit: the engine's hit-stop of a program's own step (both held 7 frames), reactions from the hit
  standard below (336's hits reel, 264's `react=R_LAUNCH` launches); damage: 12 openings x 1 unit, damage_raw.json max
  12 -> the MAX tier 180 = 15 a hit.
- **The SS2 hit standard** (120326: "in the brawler we want a hitstop for each impact and juggle abilities"): every
  attack step of an SS2 program (specials, versions, fury, MAX, the Lab's LAB special) gets the packed reaction KOF's
  imports carry (bstep_t hy, `export_ss2.hit_react` / `standard_reacts`): standing = the program's own (a knockdown
  state's earlier hits reel) | 8 (hittable), juggled = R_LAUNCH | 8. Before, its knockdowns were KOF's blowback 283
  without a hurt box (the note's replay: dd Blitz 214A knocked Ryo down, kmode 1, and 623AB passed through him); now
  the victim is hittable in the air and every later hit relaunches it. Hit-stop: a hit of the fighter's own step holds
  both (HITSTOP 7, unchanged); an object's hit (the Kogetsuzan crescent) holds the victim only, the engine's rule for
  every object. Data only, no engine change; other fighters' tables unchanged (only tile numbers +36 after Haohmaru's
  new frames, Hanzo WHP's 236 row table un-deduplicated).
- **Low finisher** (115835): last hit + down = SS2's crouching C+D (anim 352, `moves.atk_ab_close = "$160"`,
  finishers.down_move), compiled from the Assembly answer `fin_down` (decisions set `haohmaru-arb`) by arb_compile.py.
- Proof: `tools/samsho2/hao2_proof.py ROM OUT` (our emulator, the Z80 tap): voices byte-equal to SS2's samples at C and
  at the MAX's first program frame, Tenha's 12 hits on SS2's steps (11 standing, the 12th launches, 180 total, both held
  each hit), the juggle (214A then 623AB hits Ryo in the air), 623C / 623AB hit-stops, the low finisher.

## Hanzo (SS2): air shuriken Blitz, far A+B Blitz — 2026-10-11 (decisions set open-2026-10-11, note 20261011-154500-5d29)
- Air down,down + A = the air shuriken j.4123AB (S-010; was jump + down + C), then a jump attack in its recoil
  (`keeps_air_attack`, docs/brawler_gold.md "Engine features"); jump + down + C is empty.
- Ground down,down + A = his far A+B, SS2 state 278 = anim $116 (`moves.cmd_fwd_c`, a normal as the Blitz like
  Haohmaru's ff; was WFT, which stays his fury on D). Measured: hits Ryo at 60 / 80 px (30, knockdown), whiffs at 40 px
  (SS2's far A+B reaches from ~64 px). Assembly answers `bz_dd` anim-116 and `air_bz_dd` S-010 in the decisions store
  (arb_compile links both to exactly these fields; its other pending difference, fin_fwd anim-116 -> finishers.forward,
  is older and left alone).
- 2026-10-11 later (notes 20261011-164455-5d29, 20261011-164801-5d29): air down,down + A = the A, B and A+B shurikens
  in turn (`air_specials` `ddA` [j.4123A, j.4123B, j.4123AB], a sequence: docs/brawler_gold.md "A sequence"), each
  startup halved (`retime` "0.5x"), still the jump attack after the last; Assembly answer `air_bz_dd` S-008 S-009 S-010.

## Kyo (KOF98): his move sheet — 2026-10-11 (notes 20261011-175124 / 175350 / 175657 / 175806-5d29, Lab shell 20261011-153020 + kyo pack 20261011-130334)
- Assembly answers (decisions set `kyo-arb`, new: no earlier answers), compiled by arb_compile.py: chain close A $50,
  close C $5A, forward + B $EC (cmd_fwd_b), far D $60 (the neutral finisher); last hit + up close D $5F (the launcher),
  + down crouch D $63, + down-forward 88 Shiki $EB (cmd_df_d, the "double sweep": `finishers.df_move`, new);
  ff + A = 236A three times on A again (S-009 / S-010 / S-011, `seq_press`: docs/brawler_gold.md "A pressed sequence"),
  dd + A = 623A small Oniyaki (S-013), uu + A = 421B R.E.D. Kick (S-004); C = 623C big Oniyaki (S-005), forward + C =
  EX 421D (S-007, unchanged), down + C = 236D 75 Shiki Kai, both kicks (S-012); jump + A = jump D $61 (both jumps),
  jump + down + A = j.2C Naraku Otoshi $EE (spare air name `atk_ab_jump`, new in arb_compile AIR_SPARE).
- Decoded 2026-10-11 (handlers98 ROM_SPECIALS + ROM_DEMAND, programs from the ROM): 623A ($3C078), 236D ($3C7D6: its
  second kick read as pressed, FOLLOW_PRESSED $3C90E: 142, 143, 145, then 148 on the event step, landing 149), and
  the parts of 236A's handler $3C9D8: `236A>156` Aragami (156, 157), `236A>158` Konokizu ($3CB84: 158, 159),
  `236A>162` Yanosabi ($3CC9E: 162). The first ff + A note (body toss C + D) was replaced by the third note.

## Iori (KOF98): his move sheet — 2026-10-11 (notes 20261011-210422 / 210524 / 210904 / 211010-5d29, game 0.10.61)
- Assembly answers (decisions set `iori-arb`, backup `iori-arb.json.bak-20261011-sheet`; his earlier a2 $55 kept),
  compiled by arb_compile.py: C = 623C big Oniyaki (S-003), forward + C = 624D (S-007, half circle back + D: the dash,
  catch and purple explosion; still his super throw), down + C = 236A Yami Barai (S-002); dd + A = 214A Aoi Hana's three
  parts on A again (S-009 / S-010 / S-011, `seq_press`); jump + A = jump D $61 (both jumps), jump + down + A = jump C
  $5C, jump back + A = jump B $57 (new: `air.back`, the Assembly row `air_ba`; docs/brawler_gold.md "The back jump's
  attack"). a2 $55 (his 2026-10-10 pick, never shipped: unresolved then) ships with it: chain far A, close B, close C,
  close D, then the generator's body toss.
- Decoded 2026-10-11: the parts of 214A's handler $70E42: `214A>141` ($70E42 alone: 141, 143), `214A>145` ($70F5E:
  145, 147), `214A>149` ($70FE0: 149, 150 in the air, 151 landing; hit kind 3), the states from the handler's table
  (part_entry's scratch fields). MAX 23624C: the victim lies (413.0 = lying 90) and the strikes keep it there.

## Billy (KOF98): the diagonal cane — 2026-10-12 (note 20261006-160912-b3f3, game 0.10.66)
- Bruno (chat, binding): "the diagonal cane is qcb + P with EX Billy". KOF98 has an EX Billy (recogniser list
  $B25EA, not $B2582): `capture/specials96.py --game kof98 --passes ex 26` (state c26x) found EX 214A / C on the
  EX-only handler $70156. Decoded (handlers98 ROM_SPECIALS + ROM_DEMAND): S-009 EX 214A (states 480, 482), S-010
  EX 214C (481, 483); both spawn the staff object 484 at +80 / 128 (frames 845..857, its attack box at the tip). A and
  C are the same frames: C starts 3 frames later, recovers 2 later, damage id 49 vs 48 -> C (S-010) on up-forward + C
  (roster specials.ufD, was 214B). No Assembly set billy-arb and no sheet slot for ufD: game.json directly.
- Checked in our emulator: romspecials_check billy:ufD = KOF98's EX Billy frame for frame (58 frames, 0 mismatch,
  object 484 same spawn / end), KOF98 0 hits on a standing Terry at 48 / 80 / 112 px: an anti-air;
  `billy_qcb_proof.py`: starts at every gap, knocks down Ryo held 70 px up at 80 / 100 / 120 px (8 damage).
---

The sections below were the Character Lab's notes in docs/feedback.md, docs/brawler_gold.md and
examples/brawler/README.md until 2026-10-10, moved here whole (dated records of what was built and proven). Where they
name `arbitrage.html`, `workshop.html` or the Chain Lab's chain tool, read the Fighter Lab's tabs above.

## Character Lab: live fighter configs and the pack catalogue (2026-10-10)

Bruno's design: one Lab **shell** build + swappable **character packs** (Robert, Kim first). The Fighter Lab's pages
(the Assembly; the Workshop's and the Dictionary's Try queues) write each fighter's live config; the Player's Character
lab polls it every 2-3 s and injects the RAM loads, or swaps the pack / shell when the catalogue changes. The VPS is
the source of truth for the live config. Same service (`tools/feedback/server.py`, unit `brawler-feedback`), no new
one.

~~The Lab config is a STAGING area~~ (superseded 2026-10-10 by Bruno: "forget about staging for now, remove that
step"): every live send of a sheet queues a ship, the desktop's worker builds it into the game ("In the game: no
staging" above).

### Where it answers, who may call it

| Caller | Base URL | Auth |
|---|---|---|
| The Player | `https://canneji.duckdns.org/brawler/lab/` | `Authorization: Bearer <Oros JWT>` (the token `Auth.kt` already keeps; the same as `/brawler/feedback/mine` and the builds) |
| The web pages | `https://canneji.duckdns.org/brawler-lab/feedback-api/lab/` | the Oros login cookie (`oros_token`), like the rest of the Lab's feedback-api |
| The desktop CLIs | `http://127.0.0.1:8920/api/lab/` over ssh | the ssh key (user `ssh`, admin) |

- No token / cookie: **401** (nginx `auth_request /jlpt-auth`, then the service checks again with Oros's `/api/whoami`).
- **Reads** (config, hash, history, catalogue, downloads, ship queue): any signed-in Oros account.
- **Writes** (PUT config, revert, ship, publish): the Oros role `admin` (today bruno, gex); any other account gets **403**.
  The role is the one in the token, as the Player's tester mode reads it.
- Downloads: `/brawler/lab/dl/shell|packs|faces/...` are static files served by nginx (HTTP Range, `206`), behind the
  same login (token or cookie). Every URL the catalogue gives is a path on canneji.duckdns.org.

### Live config per fighter

`<f>` = the roster name (`[a-z0-9_]{1,24}`). A config record:

```
{fighter, version (the revision number, 1, 2, ...), hash (sha256 hex of the blob bytes), updated (UTC ISO), by (Oros user),
 size (blob bytes), note, blob (base64 of the RAM-loads bytes: opaque to the server), json (the human-readable config it
 was encoded from: the fighter's game.json roster entry), reverted_from? (the revision a revert copied)}
```

| Call | What |
|---|---|
| `GET me` | `{user, role}`: who the page is (Send to Player and Revert need `admin`) |
| `GET config` | every fighter's live head (the record without blob / json) |
| `GET config/<f>` | the live record in full. `ETag: "v<version>-<hash16>"`; 404 = no config yet |
| `GET config/<f>/hash` | `{hash, version, updated}`: **the 2-3 s poll**. `ETag: "<hash>"`; send `If-None-Match: "<hash>"` and get **304** (no body) while it is unchanged |
| `PUT config/<f>` | body `{blob, json, hash?, note?}` (POST works too; at most 4 MB). The server sets version, updated, by. `hash`, when given, must be the blob's sha256 (400 otherwise). `If-Match: "<hash>"` = only if the live config still has that hash, else **412** with the current head (two pages editing the same fighter). The same blob + json again = no new revision. Answer: the head + `changed` |
| `GET config/<f>/history` | every revision's head, oldest first |
| `GET config/<f>/rev/<n>` | revision n in full |
| `POST config/<f>/revert` | `{rev, note?}`: a **new** revision with revision rev's blob + json (`reverted_from`). Nothing is ever deleted |

The poll: the hash changes only when the blob's bytes change (that is what the Player injects); a json-only edit makes a
new revision with the same hash.

### The ship queue (no staging since 2026-10-10: "In the game" above)

| Call | What |
|---|---|
| `POST ship/<f>` | `{rev?, note?}` (rev defaults to the live one; admin): queues `{id, fighter, rev, hash, by, at, note, status: pending}` |
| `GET ship[?status=pending]` | the queue |
| `POST ship_done` | `{id, status: done or dropped, note?}`: closes it (the note: release, commit) |

### Catalogue

`GET catalogue` (ETag + `If-None-Match` -> 304, so it can ride the same poll):

```
{shell: {version, url, sha256, engine, size, published} | null,
 packs: [{fighter, display, face (URL of the HUD portrait PNG, or null), version, url, sha256, engine, size, published,
          versions (how many were published)}]}
```

- The newest *published* shell, and each fighter's newest published pack, is the one served. A rollback = publish the
  old file again under a new version.
- `engine`: the engine version a file is built for; the Player loads a pack only into a shell of the same engine.
- The Player checks `sha256` after the download (as it does for the builds) and resumes with Range.

### Files on the VPS (`/data/brawler/lab/`)

| Path | What |
|---|---|
| `config/<f>.json` | the live config (replaced atomically) |
| `config/<f>.history.jsonl` | every revision in full, one JSON per line, append-only (fsync'd before the live file changes) |
| `ship.json` | the ship queue |
| `shell/<version><ext>` + `<version>.json` | the shell builds and their sidecars |
| `packs/<f>/<version>.pack` + `<version>.json` | the packs and their sidecars |
| `faces/<f>.png` | the HUD portraits (the face make_site.py puts in the Lab: `/data/neogeo_dict/portraits/<bank>.png`, else `_select`, `_square`) |
| `incoming/` | labpub.py's uploads before the publish call moves them |

Only `shell/`, `packs/` and `faces/` are served (nginx `/brawler/lab/dl/`); `config/` is not.

### Desktop CLIs

- `tools/brawler/labcfg.py list | show F [--rev N] [--blob] | history F | revert F REV | export F [--rev N] [--dry-run]
  | put F --blob FILE [--json FILE] | ship-pending | ship F | ship-done ID [--dropped] [--note ...]`.
  `export` writes the config's json as the fighter's roster entry in `examples/brawler/game.json` (key by key, as
  arb_compile writes it: unchanged keys keep their text), so git keeps the history; then build, check, publish, commit and
  `ship-done`.
- `tools/brawler/labpub.py list | publish-shell FILE --engine E [--version V] | publish-pack F FILE --engine E [--version V]
  [--display D] [--face PNG | --no-face] | publish-face F [PNG] | remove-shell V | remove-pack F V | remove-face F`.
  scp to `incoming/`, then the service checks the sha256 and moves it; a version is published once (400 otherwise).
  `--version` defaults to the UTC time.

### Proven 2026-10-10 (live, on canneji)

Signed out: 401 on every Lab URL (player and web paths, the downloads). Tester (viewer) token: reads 200, PUT / ship 403.
Admin token: PUT rev 1, the hash poll 200 then **304** with If-None-Match (token and cookie), a stale If-Match 412, PUT
rev 2 by cookie, poll 200 with the new hash, revert to rev 1 = rev 3 with rev 1's bytes and json, history 1-2-3, a ship
request and ship-done; labcfg.py list / history / show / revert / ship-pending / ship-done and export into a copy of
game.json. labpub.py: a dummy shell, a dummy Kim pack and Kim's face published, the catalogue (and its 304), full
downloads matching sha256, Range `bytes=10-19` -> 206, a duplicate version refused (its upload removed). Every test entry and
dummy file removed afterwards; the existing endpoints answered the same before and after the deploy.

## Character Lab: shell and packs (2026-10-10)

One Lab **shell** build + swappable **character packs** (Bruno: "one lab build and two exported data sets, two characters
we could dynamically swap"). Built on the existing pipeline: the shell is the brawler with one more roster fighter, the
**slot** (the last bm_chars index), exported, banked and linked by the same tools; only where the slot's data lands is
fixed.

| Region | Where (the shell's .neo) | Kept | Robert (LAB export) | Kim |
|---|---|---|---|---|
| P `.labslot`: the slot's first-MB tables (steps, throws, postures, palettes, routes, voices, headers; its game_tables rows: damage tiers, retime targets, dash) | $E0000-$FFFFF (Makefile LABSLOT_AT) | 128 KB | 48,016 | 14,856 |
| P2 bank 3: its banked tables (frames, tile lists, special scripts / programs, projectile rows) | P MB 4 | 1 MB - 16 | 143,112 | 124,450 |
| its element of every per-fighter table (bm_chars[], bm_seg[], dtier_rom[], gblitz_rom[], portrait_pal[]..., bm_lab, its 16 gretime_rom rows) | in place | fixed | | |
| C tiles | tile_first of build_shell/slot.json, one page | 24,576 tiles (3 MB) | 9,280 | 6,012 |
| V voices (ADPCM-A) | $A00000 (the first MB past every other sample) | 512 KB | 148,480 | 128,512 |
| M voice records: codes $C0-$EF of the overflow slots 4 / 5 ($1B players, $17 enemies) + their enable bits | KOF98 driver tables | 48 voice ids | 18 | 19 |
| S HUD face | fix tiles PORTRAIT_TILE + 25 x 16 | 16 tiles | | |

Every roster fighter fits (largest: Rugal 13,204 tiles, Iori 17.5 KB first MB / 222 KB of voices, Rugal 125 KB banked,
voice ids up to 31, 2 retimed moves) except Billy Lee: a form link (his other form is another roster index) is refused.
A KOF96 / 98 / 99 fighter with a piece library (`tools/brawler/arb_pieces/<f>.json`: Robert, Krauser) is exported with his
LAB special (every animation of his dictionary, bm_lab: the TRY blob's $NN entries); the others without. Krauser's
LAB pack: 32,036 / 111,362 / 7,842 tiles / 19 voices (158,208 bytes).

- `make LAB_SHELL=1` -> `lab-shell.neo` (build_shell/: the slot = Robert, so it boots; `-DLAB_SHELL`: game_enter starts
  the practice, P1 = the slot vs Ryo, unless a page already drives the mailbox). `python3 tools/brawler/bank_proof.py --shell`.
- `make LAB_PACK=<f>` -> `packs/<f>.pack` + `packs/<f>.json` (build_pack_<f>/: the same game with f in the slot; the shell is
  made first). `tools/brawler/lab_pack.py make` takes the slot's regions and **refuses** a pack whose build differs from the
  shell's anywhere else (naming the symbols: a pointer or a table the slot does not own) or that overflows a region;
  `lab_pack.py info PACK`, `lab_pack.py apply SHELL.neo PACK OUT.neo` (what a swap gives).
- Manifest (inside the pack and beside it): fighter, display, bank, `engine` = `<VERSION>-<shell fingerprint>` (sha256 of the
  shell with every slot region zeroed: any pack built against that shell carries the same), the slot (id, P2 bank), the
  constants the pages need (pool, specials, nvoice, LAB special), `ram` (Player 0.0.28, `lab_pack.ram_map`: the shell's
  `lab` mailbox + lab.js's offsets + the Try-in-game fields, `prac`, P1's state byte, the neutral states), usage per region, the piece registry
  (`arb_pieces/<f>_ids.json`), the face's PNG, each region's offset / size / sha256.
- The swap: `tools/brawler/chainlab/pack_swap.c` (one C path): checks the whole pack (magic, version, the ROM sizes = the
  loaded shell's, every region in bounds) then copies each region into Geolith's ROM buffers (P word-swapped as Geolith
  keeps it; a region's blank end written as zeros) and the caller resets: the shell boots into the practice with the new
  fighter. Geolith decodes / caches nothing from its ROMs (tiles, ADPCM, the M ROM's banks are read as they are), so no
  invalidation is needed; its only change is `retro_neoscan_rom(region, &size)` (libretro.c). Callers: the wasm core
  `wc_swap_pack(ptr, n)` (+ `wc_rom`, `wc_rom_size` for the proofs), the Player `Native.swapPack(path)` (JNI in
  player.c; the Player's Character lab, below).
- Publish: `labpub.py publish-shell examples/brawler/lab-shell.neo --engine <engine>` and
  `labpub.py publish-pack <f> examples/brawler/packs/<f>.pack --engine <engine>` (the engine string from the pack's .json).

Proven 2026-10-10 (`tools/brawler/chainlab/packs_proof_node.js`, the wasm core headless; screens /data/tmp/packs/): the
shell boots into the practice with Robert (P1 = index 25), his chain (5 hits) and C special (spec 4) play, his voice goes
out on $1B $C8; `wc_swap_pack(kim.pack)` -> after the reset the core's P / S / M / V / C equal pack-kim.neo byte for byte,
P1 = Kim with his frames, face and name, chain 6 hits, his C special ([2]8C, spec 2) with his voices ($1B $C2, $D4, $17 $C0);
`wc_swap_pack(robert.pack)` -> the shell's bytes again, Robert as before. Each slot run is frame for frame identical (state,
animation, step, x, height, the dummy's life and state, 226 frames) to the same run with the roster's own Robert / Kim.
The normal build (`make`) is byte-identical to before.
Published 2026-10-10 to the catalogue (engine 0.10.23-70201b3a0953): shell 20261010-000745, packs robert 20261010-000752 and kim 20261010-000757 (faces included). The web "Try in game" panel still loads rom/lab-robert.neo (the LAB_FIGHTER build); it can move to the shell + a pack (wc_swap_pack; P1 = index 25, lab.json of build_shell) when the Player's Character lab does.

## Character Lab: the Player (0.0.28)

`android/.../CharacterLab.kt`, admin only: the list button's menu has "Character lab" (also `adb shell am start -n
com.neoscan.player/.MainActivity --ez lab true`).

- **Faces:** `GET catalogue` -> each pack's face (pixel-exact), name, pack version, the shell version. A tap downloads the
  shell (once) and the pack into `files/lab/<sha256>.neo|.pack` (Range resume, size + sha256 checked as RomFetch does),
  switches the core to the shell (`MainActivity.playRom`: the process's emulation thread is replaced) and swaps the pack in
  at once (`Native.swapPack`, the shell resets into the practice with him). Another face = another swap, no reboot.
  "Leave the lab" = the core back on brawler.neo. The practice menu is the game's START.
- **Live config:** every 2 s `GET config/<f>/hash` + `GET catalogue`, both with If-None-Match (304 = nothing). A new hash
  -> `GET config/<f>`; its blob is written between frames (`EmuThread.hook`, `Native.ramWrite`) exactly as lab.js
  `installTry` does (tblob, lstat 0, tnow 0, "LAB1", fighter, load 6), once `lab.active` = 1 (after every boot / swap it
  is written again). The blob's fighter byte is set to the pack's slot id (P1 in the shell). The RAM addresses come from
  the pack's manifest `ram` (a pack without it: configs off, said on the strip); a TRY blob longer than `ram.tblob_size`
  is refused on the strip (0.0.30).
- **New versions:** a newer pack of the fighter on screen (or a newer shell, if his pack for it is published) is
  downloaded, then loaded when P1 is next in neutral (`ram.p1_state` in `ram.neutral`), or at once on the badge's tap.
- **Strip** (0.0.29: OFF the picture, it hid the practice's HITS / DAMAGE row; 0.0.31: OFF the pad too, Bruno's P40 Pro
  in landscape had it over the d-pad): one row, between the picture and the pad's buttons in portrait (the badge under
  the row while it shows); in landscape ABOVE the picture, between the top corners' buttons, the badge in the row, the
  picture shrinking to the height left under it (`Screen.labTop`; on a 20:9 phone the gutters are too narrow for it).
  `PadView.labH` / `labArea` keep the room; PadView logs its layout (`NeoScanPad: layout`, every control's touch box)
  and the strip its screen rect (`NeoScanLab: strip`) for the geometry check: a light + a word label: green IN SYNC rN, blinking amber NEW CONFIG rN:
  applies at neutral (lstat 2), a white / green flash APPLIED rN (lstat 1), red REFUSED rN: why (lstat 0x80 | n), grey NO
  LIVE CONFIG / OFFLINE; a blue badge NEW PACK / NEW SHELL <version> (tap: now); buttons Apply now (lab.tnow = 1 while
  pending) and Faces.

Player 0.0.31 proven 2026-10-10 in AVD JanusPhone at its own 2560x1600 / 320 dpi and at the P40 Pro's 1200x2640 /
480 dpi (`wm size` / `wm density`, reset after), portrait and landscape, Robert with a test config pending (`labcfg.py
put robert`: a looping queue, then a plain blob): the strip's logged rect matches its white border in the screenshot
and intersects no control's touch box nor the picture in all four. `/data/feedback/proof_0031/` (README.txt, before =
0.0.30's landscape strip over the d-pad). The test configs were removed afterwards.

Proven 2026-10-10 in AVD JanusPhone (brawler-test, role set to admin locally, then back to viewer), screenshots
`/data/feedback/proof_0028/`: the faces; Robert in the practice (shell 20261010-002046 + his pack); swapped to Kim without
a reboot; `labcfg.py put kim` r1-r4 (r2 / r4 = a looping 214B queue so P1 is never neutral): r3 amber pending, Apply now
-> APPLIED flash -> green; a new Kim pack published -> blue badge, waits while P1 is busy, tap -> swapped, the config
written again after the reset. Poll traffic over ~4 min: 170 x 304, 12 x 200 (the changes), 44 x 404 (Robert had no
config), 0 errors. The test configs and pack versions were removed afterwards.

## Character Lab: Send to Player (web pages + Player 0.0.29, 2026-10-10)

The last link: the web pages write the live config the Player applies.

- **The blob** (`lab.js liveBlob` / `liveParts`): the TRY blob exactly as `encodeTry` gives it (the preview's bytes), and
  when a chain is set, after it `'L' 'C'` + u16 BE n + the n bytes of a chain override (`encodeOverride`, load 5). No chain
  = the TRY blob alone. The fighter byte is the Lab build's index; the Player sets it (and every retime row of that
  fighter in the chain) to the pack's slot.
- **The buttons** (`tryit.js`, `TryIt.button(f, label, fn, send)`): a dashed "Send to Player" beside every "Try in game",
  "Try this sheet in game", "Try the queue in game" (Workshop, dictionary, sheet) and in the chain tool (beside "Push to
  the game"). A queue Send keeps the live config's chain, the chain tool keeps its TRY blob, a sheet sets both (a sheet
  without a chain override clears it, as the preview does). PUT `feedback-api/lab/config/<f>` with `If-Match` = the hash
  the page last read: **412** -> the page reloads the live config and says who changed it, Send again goes through. The
  answer: "Sent: ROBERT live config rN (...). The Player applies it at neutral." Non-admin (`GET lab/me`): the button is
  dotted and explains it needs the Oros admin role (the server would answer 403). The JSON stored is
  `{name, lab_try: {page, try, chain}}` (what the page played): `labcfg.py show` prints it, `export` refuses it (ship a
  sheet with arb_compile.py, a chain with chain_save.py).
- **The "Live config" line** (Workshop, sheet): rN, updated when / by whom, "History" (every revision: size, hash, note,
  "Revert to rN"), "Revert to r(N-1)" (POST revert: a new revision); kept current by a 15 s hash poll (If-None-Match).
- **The Player** writes the chain first (lab.buf, magic, fighter = slot, load 5), the TRY blob once the game took it
  (load 6); a config without a chain after one with: load 2 first (the ROM's tree back). The strip says "+ CHAIN".
- **Notes in the lab** (0.0.29): `meta.json` records the shell, not brawler.neo: `rom_file` lab-shell-<v>.neo,
  `rom_sha256` the shell's, `rom_version` "lab <shell> + <fighter> <pack>", `rom_build` lab, and `lab` = {shell_version,
  shell_sha256, engine, pack_fighter, pack_version, pack_sha256, config_rev, config_hash}.
- The site: make_site.py now copies `tryit.js` and `gameplay.js` (they were missing from the live Lab: "Try in game" and
  the Chain Lab's player could not load there).

Proven 2026-10-10 (temporary Oros accounts labproof-admin / labproof-viewer, deleted afterwards), screens
`/data/feedback/proof_0029/`: the sheet's Send (admin) -> r1, its blob = `encodeTry` of the sheet byte for byte (44 B,
9 slots; its chain = the ROM's, so no chain part); another editor's PUT then the stale page's Send -> 412 explained, Send
again -> r3; viewer: the button explains, a PUT -> 403; Workshop line + History + "Revert to r8" -> r10. AVD JanusPhone
(Player 0.0.29, brawler-test): the strip under the picture (HITS / DAMAGE clear), r1 / r4 applied at once, a looping
queue then a sheet -> amber NEW CONFIG r7 -> Apply now -> APPLIED -> IN SYNC; a sheet with a 4-press chain (r9, 550 B)
-> "chain 534 bytes (load 5)", then load 6, IN SYNC r9 + CHAIN; the revert to r8 -> load 2 then load 6; landscape: the
strip in the left gutter. The same r9 bytes through the Player's path on the wasm core (shell 20261010-002046 + robert
pack): route_tab[25] = lab.buf, the chain plays differently (7 -> 5 hits). The test configs were removed afterwards (the
config directory was empty before); not exercised: a real feedback note from the lab (the meta path is built, no note
was sent).

## The Fighter Lab: one page for the whole cast (2026-10-10)

Bruno: "the Chain Lab is obsolete; the Workshop and the Assembly for the whole cast, data driven: pick a character, then
Workshop tab, Assembly tab, a general Info tab"; "the template must be standard". `brawler-lab/lab.html` (lab.html +
fighterlab.js; the canneji hub card opens it, the Chain Lab's index.html links to it):

- `lab.html`: the cast grid, every game.json roster fighter from `cast.json` (fighterlab.py, run last by make_site.py:
  roster facts, the HUD face exactly as the game draws it = labpub.hud_face, the big win / drama portrait, the music
  theme = roster `music` else the songs.json THEME_* naming him, and what the site holds: dictionary, Workshop counts,
  knobs, sheet, review, Lab build). The pack and the live config revision are read live (`lab/catalogue`, `lab/config`).
- `lab.html?f=<f>&tab=info|workshop|assembly`: Info (the facts, faces, pack / shell / site build versions, live config
  line, "Play him in game"); Workshop = workshop.js loaded into `#ws`; Assembly = arbitrage.js loaded into `#arb` (each
  script once, on the tab's first opening; its CSS lives in lab.html scoped to `#ws` / `#arb` / `.pmodal`). A fighter
  whose source game has no dictionary builder (animdict.DICTS; SS2, WHP, Double Dragon today) gets Info and an honest
  sentence in the other two tabs. `workshop.html?f=` / `arbitrage.html?f=` redirect to the tabs (ask= / text= / #piece kept).
- `&embed=1`: the Player's WebView beside the game (~360-420 px): no chrome, compact, the Assembly only, the page's own
  "Try in game" hidden (Send to Player and the live auto-send stay).
- "Try in game" (tryit.js) plays the **Character Lab shell + the fighter's pack** from the catalogue (the Player's files,
  sha256 checked, `wc_swap_pack`; P1 = the slot), with `rom/shell-<engine>.json` (layout, roster order, throws, chain rules)
  and `rom/pack-<f>-<sha12>.json` (LAB animations, chain data) from tryit_site.py; a pack whose engine is not the shell's is
  refused (as the Player does); `rom/lab-<f>.neo` stays the fallback. A shell this site has no layout for uses
  `rom/shell-latest.json` of the same game version (the RAM map is the code's; only ROM addresses such as bm_chars move).
  A pack without a LAB special plays his decoded specials and throws only (a $NN says so).
- Done the same day: the Chain Lab's chain timing is the Assembly's chain section ("Knobs" above).

## Character Lab: piece knobs and the token-free sheet (2026-10-10)

Bruno: "each special move comes with its key params and default values, adjustable in the Assembly; clearly surface
where values are overridden and offer going back to default". The decode side (tokens) finds the knobs, the Assembly
tunes them (no tokens), the compiler ships them (no tokens).

- **The catalogue is data** (`tools/brawler/knobs.py`, run by `arb_compile.py pieces <f>`): `arb_pieces/<f>.json`
  `"knobs": {S- id: [{id, name, unit, default, min, max, step, rows, from, judgment}]}`, read by the pages (Workshop
  JSON `specials[].knobs`), the compiler and `build_tables.py`; a knob a later decode adds needs no code change. Today
  (KOF fighters, from `handlers98.export_rom`): Travel speed (the piece's own P_SET vx with a move op), Rise speed (its
  P_SET vy with a fall op), Dive speed (a 45-degree vx / vy pair), Projectile speed (its travelling object's px a frame),
  Projectile hits (an uncounted object), Damage %. Ranges: speeds 1 .. 3x default (at least default + 3), integers by 1
  when the default is one (0.25 steps otherwise); hits 1-10; damage 10-300 % by 10. One formula turns a value into
  engine rows: `val = round(base * value / default)` (knobs.py `knob_rows` = lab.js `knobRows`).
- **The game** (fighter.h `gknob_t` / `gkcat_t`, fighter.c "knobs"): rows {slot, pool special, kind, a, match, val}
  per SLOT (the same piece on three slots at three values). KN_SET: the P_SET of register a whose value is `match`
  plays `val`; KN_PSPEED: its travelling objects' rows (x from row 0, rounded) and wrap scaled val / 256; KN_PHITS: they
  hit val times (KN_STOP 4 frames apart when the data has no stop; the hits before the last reel the victim standing,
  KOF's counted-object rule); KN_DMG: its hits' damage x val / 256. Two sources, one path: the shipped rows
  `gknob_rom[fighter]` (game.json `roster[].knobs`) and, for P1 while the Lab drives it, the TRY blob's rows (the whole
  config: the shipped rows are not read then). The catalogue `gkcat_rom[fighter]` (the build's own bounds) is the
  gate: a TRY blob's knob row it lacks is refused (lstat `0x80 | 9`), a value past its bounds is clamped. No row = the
  game as before: the normal build's attract trace is identical to the build without knobs (7651 / 7651 ticks; only
  the power-on sample differs, an uninitialised word).
- **The TRY blob v2** (`lab.js encodeTry`, `knobs: [...]`): knob records ride as slot records `[0x80][6][slot][spec]
  [kind][a][match i32][val i32]` (slot 0xFE = the Try queue), so a v1 reader (the Player's `liveParts`) walks over
  them; a blob without knobs keeps version 1, byte for byte. TRY_MAX 1024 in the game (the fullest config, a full queue +
  every slot full + 32 knob rows, is 1006 bytes; fighter.c asserts it). The Player (0.0.30) takes any TRY blob up to the
  pack manifest's `ram.tblob_size` (sizeof lab_t.tblob, lab_pack.py ram_map; a pack published before it lacks the key:
  576, version 1's limit) and leaves the checks and clamps to the game.
- **The pages**: `knobui.js` (one panel): under each picked S- piece of a sheet slot (`arbitrage.js`, saved in the slot's
  answer `knobs`) and under each unlocked special in the Workshop (saved as `knobs-<S- id>` in `<f>-workshop`, the Try
  queue's values); steppers + slider + number, the default and range written out; an override = bold value, "changed
  from N", a solid 3 px border, "Back to default"; "Reset all knobs" per piece, per slot, for the sheet. The decisions
  service keeps `knobs` ({S- id: {knob: number}}, shape only).
- **The sheet is token free** (Bruno 2026-10-10, binding): no note box, no mic, no "Done — send to Claude". Each slot has
  "Ask in the Workshop" (workshop.html with `ask=<piece>&text=<the slot, its pieces>`: the request pre-filled in that
  piece's thread, the Workshop keeps its mic); the page ends with **Ship to game** (admin): POST `lab/ship/<f>` naming
  the live config's revision ("queued: the compiler builds, checks every slot and publishes, or says why it refused").
  Old notes stay in `<f>-arb` on the server, never shown or read; `arb_compile.py` no longer makes a typed note
  unresolved (an undecoded pick says "unlock it in the Workshop").
- **Ship** (`arb_compile.py`): the slot answers' knobs -> `roster[].knobs` `{slot: {S- id: {knob: value}}}` (defaults
  left out; only slots in `knobs.SHIP_SLOTS`: the C specials, the Blitz, the air specials). A knob the catalogue lacks,
  a value out of range, a slot that cannot ship: REFUSED before anything is written. Then build + bank_proof + the slot
  check + `knob_check` (each knob measured in our emulator: projectile px a frame, its hits, the P_SET value seen in the
  fighter's speed, damage against the same move with no knob); any failure: game.json and brawler_gold.md restored, the
  game rebuilt from them, the reason printed, exit 2.
- Proofs: `tools/brawler/knobs_proof.py` (Lab build, TRY blob by lab.js), `chainlab/knobs_page_proof.js` (420 px, stub
  service), screens and logs in `/data/tmp/knobs/`.

## The arbitration sheet compiler (2026-10-10, tools/brawler/arb_compile.py)
Bruno: "once a game is analysed and its specials decoded and converted, every piece — animation, special, code — should
just be linked in the new version without tokens". A finished sheet (decisions set `<f>-arb`) is compiled into the
roster entry without an agent wherever the pieces already exist; the rest is listed for an agent, never guessed.
- `python3 tools/brawler/arb_compile.py <f> --dry-run` prints per slot: pick, class, linked / unchanged / unresolved, the
  roster field and value. Without `--dry-run` it writes game.json (only the fighter's entry, key by key: unchanged keys
  keep their text) + a dated "sheet round" section here, builds (make -C sdk; rm build/*.o; make -j2; bank_proof.py) and
  plays every linked slot in our emulator (Chain Lab training mode, 2-frame presses, one process): the move / special it
  starts, the picked animation's ROM frames on screen (build/bm_frames.json), a hit on the dummy -> PASS / FAIL.
  `--compare GAME_JSON` diffs the compiled entry against another game.json (an agent's round).
- Classes: **a** normal (the fighter's own move name, the roster's `moves`, else a spare six-button name with
  `moves "<name>": "$XX"`); **b** an animation of ONE decoded special (handlers98.ROM_SPECIALS programs; Kizuna's
  export_kz programs) -> its input; **c** an animation special (`anim_specials "$NN": how`) when the library knows its
  reaction; **d** unresolved: an undecoded special, a variant choice (an animation two specials play), a pick the
  library cannot place, a slot the engine has no field for (fin_df, air_bz_ff / uu / du), the throws, a changed chain
  length, and every slot with a typed note. Slot -> field map: the module doc.
- The PIECE LIBRARY: tools/brawler/arb_pieces/<f>.json (`arb_compile.py pieces <f>`; refreshed on every real run):
  per dictionary animation its move names, the specials that play it, hop_of (a hop's later state), the state that
  addresses it, anim_special (a known reaction) and note; the specials (decoded or captured) with their animations; the
  spare names; `handled` = noted answers an agent already implemented (not listed again while unchanged). A new decode
  (a ROM_SPECIALS entry, an anim_special reaction) just adds entries: the next sheet links them for free.
- Validated on history: Robert's round-2 answers against the tree before 74e5a04 linked 7 slots (a2 $5B, a3 $D4,
  fin_up $67 -> spare atk_ab_far, Blitz ff $8E 624D, dd $1E7 EX 624D, du $9C 623D, C $85 623C + its three
  directions), all 7 PASS in the emulator, game.json = 74e5a04's except exactly the 3 unresolved: forward + C $1EF (EX
  646B / D variant choice), down + C $9F (426B undecoded -> the agent's anim_specials "kof") and $E5's hop note.
  Kim / Krauser / Robert's current sheets (and "now" fed back as a sheet) compile to no change.

## Piece ids and the Workshop (2026-10-10, tools/brawler/piece_ids.py, tools/brawler/workshop.py)
The Lab in two parts: WORKSHOP (token-bound: conversation, unlock requests, decoding) and ASSEMBLY (the arbitration
sheet + arb_compile.py, zero tokens).
- Piece ids (Bruno's naming, binding): animations keep their `$NN`; decoded programs get per-fighter ids in decode
  order, never renumbered or reused: `S-001`… = special VERSIONS (light / heavy / EX / MAX, ground and air: each its own
  piece), `T-001`… = throws / grabs / command grabs. The input and a display name ("Ryuuga, C version") are data on the
  piece, never in the id. Registry = source of truth: tools/brawler/arb_pieces/<f>_ids.json. `arb_compile.py pieces <f>`
  (every real run) gives ids to newly decoded pieces; a piece the library loses is marked `gone`, its id kept.
- The compiler takes `S-004` in a sheet answer (class b: that special's input in the slot, no variant question);
  `T-` picks, an S- id in a normal slot, a ground special in an air slot or a non-MAX one in the MAX slot are unresolved.
- Robert (2026-10-10): S-001 23624C Ryuuko Ranbu C, S-002 623A Ryuuga A, S-003 623C Ryuuga C, S-004 623D Ryuu Zanshou D,
  S-005 624D Hien Senpuu Kyaku D, S-006 EX 236C Ryuugeki Ken EX C, S-007 EX 624D, S-008 EX 646D Gen'ei Kyaku EX D,
  S-009 MAX 23624C, S-010 air 214D Hien Ryuujin Kyaku D; T-001 forward + C Ryuuchou Kyaku, T-002 forward + D Kubikiri
  Nage; 17 special versions locked. First Workshop unlock (thread sp-6426A): S-011 6426A / S-012 6426C / S-013 MAX 6426A
  Haoh Shoukou Ken, read from the handler $49F24 (handlers98 ROM_SPECIALS + ROM_DEMAND: in the Lab builds' pool and a
  sheet's slot, not in the normal game's export). A: state $A8, the fireball $AA at 4 px a frame; C: $A9, 7 px; MAX: $AC,
  $AD at 16 px, 5 hits 4 frames apart (its hit routine counts +$138: handlers98.counted_states, bproj_t hitnext phases,
  the last one $AE with box $2D), end $AB / $AF; the victim stays standing through the MAX's hits (R_HEAVY), the last
  knocks down. Krauser S-001..S-011 + T-001/2 (2 locked), Kim S-001..S-007 + T-001.
- Workshop page brawler-lab/workshop.html?f=<f> (review/<f>_workshop.json from workshop.py, built by make_site.py):
  Specials (unlocked with id / name / input / clips / what it does; locked greyed with "Unlock this" + mic), Throws,
  Animations (each attack step's hit class: KOF98/99 attack box id -> KOF's REACT tables, situation 2 standing (light /
  heavy from situation 0) and 6 juggled; other games "class not decoded"), a thread per piece (decisions set
  `<f>-workshop`, one entry per message). The arbitration picker offers the unlocked S- / T- pieces, lists the locked
  specials with a Workshop link, and "Now" names the S- ids a slot plays.
- CLI: `workshop.py list [f]` (OPEN = his request is the last message), `reply <f> <piece> "<text>"`,
  `unlock <f> <piece>` (only a piece decoded in the library: id + reply + the page data republished), `publish <f>`.

## The Chain Lab, the practice mode, the live config / Try in game (the game side; from examples/brawler/README.md)

**Chain Lab** (`tools/brawler/chainlab/`, live at canneji.duckdns.org/brawler-lab/ behind the Oros login): the Geolith core
compiled to WebAssembly (`build_wasm.sh`, emsdk in /data/emsdk; `web_core.c`) runs this ROM with SNK's MVS BIOS in the
page; the page edits a fighter's tree, "Build" writes it into the game's RAM (`lab.buf`, live), and the player plays it on
a dummy. Training mode (main.c "Chain Lab training", entered when the page writes `lab.req = 1`, so the release ROM is
the lab's): P1 against one dummy that never attacks and gets up, no waves, camera fixed, the last combo's hits / damage on
the fix layer. P1's route steps are logged in `lab.ev[]` (start: from neutral / after the move ended / cancel / chain
window; hit; end) for the page's per-link readout. `labdrive.py` drives the same mailbox from the desktop core (harness);
`proof.sh` plays Terry's AAB→A route in both cores and compares the traces (identical); `deploy_vps.sh` publishes. Enemy test (`lab.req = 3`) and
data packs (`lab.load = 3 / 4`): see examples/brawler/README.md "Data".

**Practice mode** (2026-10-10; Lab builds only: `make LAB_FIGHTER=<f>` / `LAB_SHELL=1` compile with `-DLAB_BUILD=1`, the
Player's build has none of it, byte-identical ROM; main.c "PRACTICE MODE"): a Lab build boots straight into the training
(P1 = its LAB fighter, stage 1, the dummies) and START opens a menu on the fix layer, the game paused (stick: line /
value, A set, B or START close): FURY GAUGE game / full / empty, MAX READY (P1's life held at `meter.low`: the red bar,
gauge and drive full), DRIVE normal / infinite, P1 LIFE refill / normal / low, DUMMIES 0-4, DUMMY MODE stand / AI on /
attack (walk in, A), WAVES (stage 1's waves in turn, after the dummies' slots), DUMMY LIFE infinite / normal, HIT BOXES,
RESET POSITIONS, APPLY CONFIG NOW (`lab.tnow`), EXIT. The settings live in the RAM block `prac` (fighter.h `prac_t`: "PRC1"
+ one byte a setting; symbol in the build's rom.elf, in the Try-in-game manifest's `syms`; `.noinit`: kept across a reset
and a pack swap) that the Player and the page read / write too. Proof: `tools/brawler/practice_proof.py [f]` (screenshots
in /data/tmp/practice).

**The live config / "Try in game"** (2026-10-10; fighter.c "Lab: try in game", `chainlab/tryit.js`): P1 plays **lab
entries** back to back: an animation `$NN` of the fighter's dictionary (u16 < `0x1000`; needs a build with his LAB special,
below), `0x1000 | k` = special k of his pool (an S- piece), `0x2000 | t` = his throw BT_* t (a T- piece; a grab slot's
first entry only). One **TRY blob**, version 1, carries the whole config: the **queue** (A from neutral plays it, `LQ_NOW`
once at once, `LQ_LOOP` again from its start) and the **arbitration slots** (27, `LS_*` = arbitrage.js ids: finishers + a
direction, Blitz, air Blitz, C specials, air specials, air normals, the hold's hit / finisher / throws, fury, MAX: the
slot's press plays its entries instead of the game's move, as a special of the slot's role, nothing paid). Bytes
(big-endian): `[0] 'L' [1] 'T' [2] 1 [3] fighter (bm_chars index) [4] LQ_* [5] qn [6] ns [7] 0`, qn queue entries (u16),
then ns records `[slot][n <= 8][n entries]`; at most 576 bytes (`TRY_MAX`); a slot not named = the game's own, qn 0 = no
queue. ONE encoder: `chainlab/lab.js encodeTry` (the pages, Node on the server, whatever feeds the Player). The writer
puts it in `lab.tblob`, `lab.load = 6`: checked at once (`lab.lstat` 0x80 | n refused, nothing changed), else PENDING
(`lstat` 2) and **applied the next time P1 is in neutral** (standing / walking, never mid-move nor in a hit stun:
`lstat` 1); `lab.tnow = 1` with the load = **apply now** (the next tick whatever P1 does; the move playing finishes,
nothing resets). `lab.cur` / `lab.qpos`: the entry playing. The export option `export_bm.py --lab F` (`make
LAB_FIGHTER=F` -> `lab-F.neo`, `build_lab_F/`) puts every animation of F's dictionary (`arb_pieces/F.json`) into one more
special of his pool (`LAB`: one program block per animation, `P_LANIM`), his complete animation block; `bm_lab` names it
(0xFF in every other build). `tryit_site.py` copies such builds into the Lab site's `rom/` for the web preview;
`tryit_proof_node.js` / `tryit_proof.js` (headless Chrome) are the proofs.
