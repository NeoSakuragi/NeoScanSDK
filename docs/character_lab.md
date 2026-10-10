# The Character Lab

Bruno's workbench for the brawler's fighters (2026-10-10): pick a fighter, unlock his moves, assemble what each input
plays, try it in the game in the page, send it to the Player on the tablet, ship it to the game. One template for the
whole cast, one data path from the page to the ROM. This document is the reference; the plain-words page for Bruno is
`brawler-lab/howto.html` (linked from every Lab page).

- Site: https://canneji.duckdns.org/brawler-lab/ (behind the Oros login; files on the VPS in `/data/brawler-lab/`).
- Source: `tools/brawler/chainlab/` (pages and scripts), `tools/brawler/` (compiler, CLIs), `tools/feedback/server.py`
  (the service behind `feedback-api/`), `android/.../CharacterLab.kt` + `Assembly.kt` (the Player).
- Build + publish the site: `tools/brawler/chainlab/deploy_vps.sh [GAME_DIR]` (make_site.py into `SITE`, default
  `/data/tmp/chainlab/site`; `LAB_MAKE=0` uses the Lab builds as they are), then rsync. It never deletes on the VPS.

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
| `&tab=assembly` | **Assembly** (`arbitrage.js`): the arbitration sheet: the chain and its **timing**, finishers, Blitz, air Blitz, specials, air specials, air, grab, fury; piece knobs; Try this sheet in game; Send to Player (and the live auto-send); Ship to game. |
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
  game plays now: his tree's hit-stops and the build's retime targets (`TryIt.plan`: the chain data of his pack or Lab
  build, `rom/pack-<f>-<sha12>.json` / `rom/lab-<f>.json`). A move pressed twice has one timing (retime is per move:
  every use of it takes it). Saved as the sheet answer `chain_timing`, its note = JSON `{hitstop: {a1..aN: frames},
  retime: {move: [frames per segment]}}` (overrides only; "Reset the chain timing" clears it). His presses that cannot
  play as a chain (several pieces in a press, a non-move animation, a length no archetype has) leave the game's own
  chain, which is still timed.

## Live config, auto-send, apply at neutral

The **live config** is one blob per fighter on the server (`feedback-api/lab/config/<f>`): `lab.js liveBlob` = the TRY
blob (`encodeTry`: the queue, the 27 arbitration slots, knob rows) + an optional chain override (`'L' 'C'` + u16 n + the
bytes of `encodeOverride`: the chain tree, then the retime table; load 5). The Assembly writes it **by itself** 1.5 s
after the last change (admin accounts; a viewer sees why not), and once on opening when the answers are newer than the
live config; "Send to Player" resends by hand. The sheet's chain override carries the presses (when each is one brawler
move) **and the timing** (`tryit.js chainOf`: the hit-stops in the tree's nodes, the retime rows after it, the ROM's rows
of the other fighters kept since the table replaces `rt_tab` whole). The Player writes the chain first (lab.buf, load 5,
its retime rows of the blob's fighter renamed to the pack's slot: `CharacterLab.kt chainFor`), then the TRY blob (load
6); the game applies the TRY part when P1 is next in neutral (standing / walking) unless "Apply now". Every PUT is a
revision; History and Revert on the "Live config" line. Details: "Send to Player" and "Live config per fighter" below.

## Try in game

"Try in game" (`tryit.js`) runs the game in the page: the Character Lab **shell** with the fighter's **pack** swapped in
(the Player's own files from the catalogue, sha256 checked, `wc_swap_pack`; P1 = the slot fighter vs Ryo), else his
per-fighter Lab build `rom/lab-<f>.neo`. "Try this sheet in game" applies the whole sheet now: its slots, its knobs, its
chain with its timing (load 5 + load 6), as the Player will. Keys: W A S D stick, U A, I B jump, O C, P D, Enter the
practice menu, `.` a frame while paused; gamepad and touch pad too. Details: "The Fighter Lab" and "The Chain Lab, the practice mode, the live
config / Try in game" below.

## Ship to game

"Ship to game" (admin, end of the Assembly) queues `POST lab/ship/<f>` naming the live config's revision. On the
desktop `arb_compile.py <f>` compiles the sheet (`<f>-arb`) into his game.json roster entry: picks (classes a / b / c),
piece knobs (`roster[].knobs`), chain timing (`chain.hitstop`, left out at the archetype's scale, + `retime {move:
targets}`: the form `chain_save.py` wrote for the old chain tool), then builds, runs bank_proof, plays every linked slot
in our emulator, measures every knob (`knob_check`) and checks the timing in the build (`timing_check`: the tree's
hit-stops in build/chainlab.json, the rows in build/retime.json). Anything refused or failed: nothing shipped, game.json
and brawler_gold.md restored and rebuilt, the reasons printed, exit 2. A shipped round appends a dated "sheet round" to
docs/brawler_gold.md. `labcfg.py ship-pending` / `ship-done` close the queue.

## The server API

The pages and the Player talk to the feedback service (`tools/feedback/server.py`, unit `brawler-feedback`): the pages
at `brawler-lab/feedback-api/` (the Oros cookie), the Player at `/brawler/lab/` (its Oros token), the desktop over ssh.
- `GET lab/me`, `GET|PUT lab/config/<f>` (+ `/hash` the poll, `/history`, `/rev/<n>`, `POST /revert`), `POST lab/ship/<f>`,
  `GET lab/ship`, `POST lab/ship_done`, `GET lab/catalogue`, downloads `/brawler/lab/dl/...`: "Where it answers, who may
  call it", "Live config per fighter", "Ship to game (the staging rule)", "Catalogue" below. Writes need the Oros
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
| `tools/brawler/labcfg.py list / show / history / revert / export / put / ship-pending / ship / ship-done` | the live configs and the ship queue (over ssh) |
| `tools/brawler/labpub.py list / publish-shell / publish-pack / publish-face / remove-*` | the shell / pack catalogue |
| `tools/brawler/lab_pack.py make / info / apply` (`make LAB_SHELL=1`, `make LAB_PACK=<f>`) | the shell and the packs |
| `tools/brawler/knobs.py`, `tools/brawler/piece_ids.py` | the knob catalogue, the piece ids (run by `arb_compile.py pieces`) |
| `tools/brawler/chain_save.py` | the retired chain tool's save path (decisions set `chain-tool`): old saved entries only |

Proofs (headless Chrome, puppeteer-core with `NODE_PATH=/home/bruno/CLProjects/NeoGeo/node_modules`):
`chainlab/consolidate_proof.js SITE|URL OUT` (this layout: the cast, the five tabs, the embed, the Game tools' tabs,
every old URL, the chain timing measured in the game), `fighterlab_proof.js`, `knobs_page_proof.js`, `tryit_proof.js`,
`packs_proof_node.js`; `knobs_proof.py`, `practice_proof.py` on the desktop core.

## Proven 2026-10-10: the consolidated Lab

PROOF_PLACEHOLDER

## Hanzo (SS2) — Character Lab, 2026-10-10: the first Samurai Shodown II fighter in the Lab (Bruno: the warp "is going to be his BREAKER special")
- C (neutral, also the breaker) = 63214BCD Ninpou Utsusemi (S-013): gone in smoke, P_WARP onto the one he hit (else the
  nearest opponent on his lane), the spinning drop from 128 px (SS2's 195, fitted), the bounce back on a hit. Breaker:
  2 drive chunks, white blink; without the drive 12 life, red blink (tools/samsho2/hanzo_breaker_proof.py, 4 / 4 PASS).
- forward + C = 6321S Ninpou Bakuen Ryuu (the fire; was the neutral C until then).
- Throws: forward + A slash throw (T-001), back + A kick throw (T-002); SS2's Earthquake throw (class 4 action 4) is the
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

**The Lab config is a STAGING area** (Bruno 2026-10-10, binding): editing it never changes the real game or git. The
"Ship to game" action only queues a request; the export to game.json, arb_compile, the build and the publish run on the
desktop, by hand (`labcfg.py ship-pending`).

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

### Ship to game (the staging rule)

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
