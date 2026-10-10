# Voice feedback from the NeoScan Player

Bruno plays the brawler on his tablet and says what is wrong. Each note arrives with an exact replay of the last
minute. Built 2026-10-06, Player 0.0.13.

## In the player (android/)

- **The mic button** sits next to the soft reset, labelled **Feedback** (0.0.26). Hold it and talk.
  - **First launch (0.0.26):** a tip card over the picture, once: "Hold to describe a problem. The game freezes while
    you talk. Release when you're done." The mic gets a pulsing white ring; the game waits. "Got it" (or a press on the
    mic itself) closes it for good (prefs `feedback` / `tipShown`).
  - While held, the sheet's top is a red banner "● Recording… release to finish" with the seconds.
  - At the press, the emulation thread writes the replay data between two frames (`Native.feedback`, player.c).
  - While the button is held, the voice records (AAC, 16 kHz mono, 32 kbps, `audio.m4a`).
- **The game freezes at the press** (0.0.14), not the release: the replay window and the screenshot end at the frame on screen
  when the button went down, and the game stays frozen while he talks and while the box is open.
- **Release:** The voice goes to the server, which transcribes it at once (about 2 s). The sheet shows numbered steps
  (0.0.26, for a first-time tester):
  - **① Your words:** the transcript, editable. Fix it or add to it with the keyboard.
  - **② Point at the problem (optional):** draw on the picture to circle what's wrong (one red pen), **Undo**, **Clear**.
  - **③ Send feedback** (the big button) sends the final text with the bundle; **Discard** (small) drops it. Either
    one resumes the game. The admin also has **Reply to...** there.
  - The keyboard: on Android 11+ the sheet shrinks above it (its height polled from the window insets: this
    full-screen window gets no IME dispatch), so ③ stays visible while typing; older Androids pan to the box.
  - **After Send:** a card over the picture, "Sending your note…", then "Thanks, your note was sent" or "Saved, will
    send when online" (queued), ~3 s; touches go through it.
- **A tap** (under 0.4 s) opens the box empty, for a typed note. That note carries the replay too.
- **Offline, or the server fails:** the box opens empty and says "transcription unavailable". The voice still goes
  with the bundle, and the server transcribes it when the bundle arrives.
  - A bundle that cannot be sent stays queued in `files/feedback/queue`. It is retried at start and every minute.
  - The card says "Thanks, your note was sent" or "Saved, will send when online".
- **Microphone permission:** asked once, on the first press; that press records nothing. If it is refused, bundles
  go without the voice.
- **Test hook:** push a file named `feedback_test_audio.(m4a|wav|mp3|ogg)` to the app's external files dir
  (`/sdcard/Android/data/com.neoscan.player/files/`). It is sent in place of the microphone; the emulator has no
  voice.

**What the player keeps running all the time (player.c):**

- Every frame's pads (port 0 and port 1) go into a ring of 8192 frames. Bit 15 of port 0 marks a soft reset that ran
  just before that frame.
- A save state is taken every 600 frames (about 10 s). The last 7 are kept, about 220 KB each.

**The bundle** is a zip. It is POSTed to `<ROM base>/../feedback/upload`, which is
`https://canneji.duckdns.org/brawler/feedback/upload`.

| File | What |
|---|---|
| `snap_<W>.state` | the oldest kept state: the replay starts here |
| `snap_<f>.state` | the other kept states, used as checkpoints |
| `inputs.bin` | `"NSIN"`, u32 1, u64 W, u64 P, then P - W frames of (u16 port0, u16 port1), little endian |
| `press.state` | the state at the press (frame P) |
| `screen.png` | the last frame's picture |
| `audio.m4a` | the voice |
| `meta.json` | versions: player name and code, game version, build and ROM sha256 (of the loaded file), the sha256 latest.json gave, BIOS sha256, hardware (mvs / aes), BIOS type, region, device, Android, install id, frames; `raw_transcript`, `final_text`, `kind` (voice or text) |

**The Oros login (Player 0.0.15).** Every player call needs an Oros account (the same as canneji.duckdns.org/oros/).
- **First start:** a sign-in screen (`LoginActivity`). The username and password go to `/oros/api/login`, which gives a
  JWT valid 30 days. `Auth.kt` keeps the token and the password in SharedPreferences `auth`, AES/GCM-encrypted with an
  Android Keystore key, the same way Oros's SecureStore does. Without a keystore, nothing is saved.
- **Refresh, as the Oros app does** (its server has no refresh call): a new login with the saved password when the
  token is within 7 days of expiry, or when a call is refused (401). A password the server rejects is dropped and the
  sign-in screen comes back. A network failure keeps everything, so the cached build still plays offline.
- **Logout:** in the settings (Account). It clears the stored sign-in and restarts on the sign-in screen.
- **Every call carries `Authorization: Bearer <token>`:** latest.json, the ROM, transcribe, upload and the note list.
  The server ties each note to the account. Notes an install sent before the login are claimed by the first account
  that calls from the same install id.
- **Queued bundles:** 0.0.15 sends again, once, the bundles an older player had marked `.rejected`.
- **Public:** only `/brawler/download/neoscan-player.apk`, so a new user can install the player.
- **Transition:** while `/data/brawler/feedback/legacy_open` exists on the VPS, players older than 0.0.15 may still
  upload, transcribe and fetch builds without a token (user "legacy"). Deleting the file ends the transition; no
  restart is needed.

**Origin of every note and transcription:**
- the user (Oros account or "legacy"), the install id, and the device and Android version (meta.json);
- the client IP as nginx saw it (`X-Real-IP`, set by the proxy over anything the client sends) and the user agent.

These are columns in `feedback` and `transcriptions`. Rows from before were filled from nginx's `brawler.log` by time
and install. They show in `fb.py show`, the Lab tab and the player's own list (its user's notes only). They never
appear on a public page.

**Scribble (0.0.15).** From the mic press (or the typed-note tap), the frozen screenshot fills the screen as a
drawing canvas (`Ink.kt`).
- One finger draws while another holds the mic. One red pen (0.0.26: the round red / green toggle, which looked like a
  record button, is gone), Undo, Clear.
- At the release, steps ① and ③ come up around the canvas, and the canvas stays live until Send or Discard.
- The bundle keeps `screen.png` clean (the replay checks it). `annotation.png` holds the strokes alone, on
  transparent. `screen_marked.png` is the screenshot with the strokes. Both are 4x the screenshot.
- pull.py's report and contact sheet use the marked picture, and so does the Lab tab, with the clean one linked.

**Tester mode (Player 0.0.26).** A second tester (another person, their own Oros account) sees only the game, the
pad and the Feedback button.
- **The rule:** the Oros account's role, which `/oros/api/login` already returns and every renewal refreshes
  (`Auth.admin`). Role `admin` (Oros `add-user --role=admin`; today bruno and gex) sees everything; any other account
  (role `viewer`, the default: brawler-test, paulina ...) is a tester. Make someone an admin on the Oros server, not
  in the player. No new endpoint.
- **Hidden for a tester:** the list button (his notes, the test queue, the decisions) and its badge, the update button
  (no blinking), Settings > My feedback notes, the note sheet's Reply to.... The player makes no `/mine` calls for a
  tester.
- **Still there:** updates download in the background as before; the launch screen offers "Player 0.0.x is ready"
  (Update / Play), the game build is fetched at launch, Settings > Updates works. Settings > Account shows "admin" or
  "tester".
- **Who sent it:** the server ties every note to the token's account (`feedback.user`, the `from` column of `fb.py
  list`, the Lab); meta.json also carries `user` and `tester` (0.0.26).
- **Proven 2026-10-09** in AVD JanusPhone (brawler-test, role viewer; admin by editing the stored role): the tip, the
  label, the recording banner, the steps sheet with a red stroke, the keyboard, "Saved, will send when online"
  (offline; the queued bundle's meta.json read `user` brawler-test, `tester` true, then deleted unsent), the tester pad
  in landscape and portrait, the admin pad + list, the test banner expanded / collapsed / dragged to the bottom /
  expanded there. Screenshots: `/data/feedback/proof_0026/`.

**My feedback (0.0.15, Settings > My feedback notes):** his notes, newest first, from `GET /brawler/feedback/mine`.
- Each card has the date, the versions, the origin, the note, category and fighters, and the status with its history
  and the developer's notes.
- The screenshot (the marked one; tap for full screen) and the voice (play / stop) come with the token.
- Pull down or press Refresh to reload.
- **From the game screen (0.0.18):** the list button (three lines) sits next to the mic in portrait and under START
  in landscape. A tap opens the list; the game pauses while it is open and resumes on back. Its red badge counts the
  notes of the test queue (0.0.23: only those; see "The test queue"), refreshed at launch, on every return to the game
  and after each verdict.
- **The game version he runs (0.0.19)** comes from the ROM file itself, not a pref: a file whose sha256 is the last
  download's takes that download's version and build; any other file (pushed by hand) takes the "V0.0.x" of its own
  title screen (P ROM), build "local". Worked out once per file (size + mtime). The list's top line, its filters, the
  badge and the bundle's `rom_version` (the note's game_version) all use it.

**Threads (0.0.17).** The list answers back.
- **At the top:** the build he runs (game version and build, player version).
- **Filters** (remembered): **Open** (every status but shipped, won't do, duplicate and verified: reopened notes stay
  here with their status), **Shipped: test it** (0.0.23: the test queue's notes, below) and **All**, each with its count.
- **Under each note:** his replies, oldest first (a voice reply plays), and three buttons:
  - **👍 Fixed** (after a confirmation): status `verified`.
  - **👎 Still broken:** a reply box opens (optional); Send sets status `reopened` with the text and voice.
  - **Reply:** hold "Hold to talk" (the voice records while held, then goes to `/transcribe`; the text lands in the box
    to edit) or type, then Send. No replay bundle.
- **From the game:** the note box (mic press or tap) has **Reply to...**: it lists his open notes and the shipped ones
  he can test; the one he picks gets the text and voice as a reply instead of a new note. The replay and the drawing
  are dropped.
- Everything goes to `POST /brawler/feedback/reply` (the Oros token only; no legacy access).

**Self-update (Player 0.0.21, PlayerUpdate.kt).** The player updates itself, as it updates the game.
- **Server:** `tools/brawler/publish_vps.sh` writes `player.json` = {version, code (the APK's versionCode, read with
  aapt2), file, size, sha256} beside `latest.json` whenever it publishes an APK (behind the same Oros token). `--apk-only
  APK VER` publishes the player without touching the ROM; `--channel test` writes `player-test.json` +
  `neoscan-player-test-<ver>.apk` and leaves the public `neoscan-player.apk` link alone. A player follows the test
  channel after `adb shell am start -n com.neoscan.player/.MainActivity --es channel test` (`--es channel live` back).
- **When:** at launch and every hour while the game runs, plus Settings > Updates > Check for update. A newer
  versionCode downloads in the background (Range-resumed from `files/update/player-<code>.apk.part`, size + sha256
  checked). Nothing pops up during play.
- **Shown:** the update button on the game screen (portrait: top row; landscape: left of START) pulses (a white ring
  on / off every 600 ms, not colour-only) whenever a newer player or game build is on the server; still and grey = up to
  date. A tap pauses the game and lists "Player 0.0.x is ready: Update" and / or "Game 0.0.x: download and restart"
  ("Up to date" + Check now otherwise). The launch screen shows "Player 0.0.x is ready" (Update / Play) when one is
  already downloaded; Settings > Updates has the same Update button.
- **Install:** a PackageInstaller session. The first time Android needs "Install unknown apps" for the player (a dialog
  explains it and opens the switch) and, on Android 13+, the notification permission (asked once). Android 12+:
  `USER_ACTION_NOT_REQUIRED`, so the update installs without a prompt (proved on Android 14). Android 10 / 11 (the
  Huawei) always shows Android's install confirmation.
- **After:** the new player starts at once where Android allows it (9 and older); Android 10+ blocks an app starting
  itself from the background (tested on 14), so a notification "NeoScan Player 0.0.x installed: Tap to play" comes up.
  App data stays: login, settings, queued notes, the ROM.
- **Signing:** every build so far, the published 0.0.21 included, is signed with the debug key of the build machine,
  `~/.android/debug.keystore` on brunux (CN=Android Debug, SHA-256 34:E0:28:AE:DA:36:62:AF:EA:47:BF:E2:3F:1C:17:25:E8:B2:6A:57:83:52:C8:BB:FA:8C:FB:88:88:85:F8:DD).
  An update must carry the same key. Back it up: if it is lost, or builds move to another machine or to a release
  key, every installed player must be uninstalled and reinstalled by hand once (losing its local data).

## On the VPS (tools/feedback/server.py, deploy_vps.sh)

- **Service:** the systemd unit `brawler-feedback`, on 127.0.0.1:8920. It runs nice'd with idle IO and uses only
  Python's standard library.
- **Data:** in `/data/brawler/feedback/`. The box has a single disk, so `/data` is the convention.
  - `bundles/<id>/` holds each bundle, unpacked.
  - `feedback.db` is the SQLite tracker.
  - `backups/` gets a daily copy of the DB; the last 14 are kept.
- **Transcription:** OpenAI's API, `gpt-4o-mini-transcribe`, falling back to `whisper-1` on error. The language is
  detected automatically. The prompt carries the game's terms.
  - The key is read from `/data/oros/secrets/openai.key` at each call. It is never copied, logged or stored.
  - Measured: a 60 s clip takes 2.0–2.5 s, from the upload to the text coming back.
- **nginx:** in `sites-enabled/kanji`, the block between the `brawler-feedback` markers. `deploy_vps.sh` rewrites it
  on every deploy.
  - `POST /brawler/feedback/upload` and `POST /brawler/feedback/transcribe` are size and rate capped. The service
    requires the Oros token (see the transition above). `GET /brawler/feedback/mine[/file/<id>/<name>]` is behind
    the Oros login.
  - `/brawler/download/` (the builds) uses `auth_request` to the service's `/dlauth` (the token, or a player older
    than 0.0.15 during the transition). The APK link is public.
  - `/brawler-lab/feedback-api/` maps to `/api/`, behind the Oros login (`auth_request /jlpt-auth`). The Lab's tab
    uses it.
- **Tracker tables:**
  - `feedback`: id, created, apk_version, game_version, rom_sha, device, raw_transcript, final_text, audio_path,
    bundle_path, status, release, notes, updated, category, fighters, duplicate_of, user, install_id, marked, ip,
    user_agent, android, title (0.0.20).
  - `status_history`: feedback_id, at, from_status, to_status, by, note.
  - `replies` (0.0.17): id, feedback_id, at, user, kind (voice / text / up / down), text, raw_transcript, audio_path
    (`reply_<id>.m4a` in the note's bundle dir), status_from, status_to, and the origin: apk_version, install_id,
    device, android, ip, user_agent. A thumbs up / down also writes its status change to `status_history`. A voice
    reply's transcription is linked to the note (its cost).
- **Statuses:** new → read (pulled) → in_progress → fixed (on the brawler branch, with its commit) → shipped (with a
  release, e.g. 0.0.71), wont_do, or duplicate (of another id); then the player's own verdict: verified (thumbs up) or
  reopened (thumbs down).
- **More tables (Player 0.0.22):** `scenarios` (feedback_id, recipe JSON), `scenario_states` (feedback_id, rom_sha,
  key, version, state_sha256), `tests` (one row per test attempt: who, when, source player / lab, result up / down /
  abandoned, build sha + version, system, seconds, the thumbs reply id, the attempt's replay id), `events` (timeline
  events: commits, releases, scenario states, backfills; unique per kind + ref). `feedback` gained todo, fix_commit,
  fix and rca.
- **Categories:** sound, graphics, gameplay, integration, scripting, other. They are set at triage; nothing is picked
  in the player.

## Cost

Every transcription's usage is stored as OpenAI returns it in the `transcriptions` table (tx_id, at, feedback_id,
model, audio_seconds, text / audio / output tokens, usage_json, cost_usd, cost_source, prices_checked, by). Its USD
cost comes from `tools/feedback/prices.json`, the price table with its source and the date it was checked.
- **Linking:** the player (0.0.14) sends back the `tx_id` it got from `/transcribe`. For an older player, the server
  links the unlinked transcription of the same audio duration.
- **Estimates:** older notes without usage are estimated from the audio duration (`cost_source` = `duration`).
- **Where it shows:** `fb.py list --cost` (per note, plus the running total), `fb.py show`, and the Lab tab.
- **Measured:** a 60 s clip used 600 audio + 61 prompt tokens in and 136 out, about $0.0015.

## On the desktop

- **`tools/feedback/pull.py`:**
  - Fetches the bundles into `/data/feedback/<id>/` and the DB backups into `/data/feedback/_server/backups/`.
  - Marks the new rows read.
  - Replays each new bundle and writes `report.md` (with his reply thread), then prints one line per bundle, reopened
    notes first.
  - Writes `/data/feedback/report.md`: every note with its thread, grouped reopened, shipped (to verify), open, closed.
- **How a replay runs:**
  - It finds the same ROM by sha256: the cache `/data/feedback/_roms`, then the repo build and `/data/roms`, then the
    VPS builds (only the last 3 are kept there, so pull often).
  - It loads the window state into `geolith/libretro/geolith_libretro.so`, built from the same tree the APK compiles,
    with the player's settings.
  - It feeds the logged inputs frame by frame.
  - It checks every checkpoint and the press state byte for byte. On a mismatch it names the first bad checkpoint and
    the byte.
  - It checks the last picture against `screen.png`.
  - It writes `sheet.png` (the last 4 s plus the press screenshot) and `clip.gif` (the last 3 s).
- **`tools/feedback/fb.py`:** the tracker from the shell. It goes through the service's API over ssh and never edits
  the DB directly.
  - `fb.py list [--status S] [--category C]`
  - `fb.py show ID` (with his reply thread)
  - `fb.py status ID in_progress|wont_do [--note ...]`
  - `fb.py status ID shipped --release 0.0.71`
  - `fb.py status ID duplicate --of ID2`
  - `fb.py set ID --category gameplay --fighters geese,terry [--notes ...]`
  - `fb.py set ID --title "Krauser: Kaiser Wave impact drawn at floor level"`
- **Titles (Player 0.0.20):** each note gets a one-line title (at most 70 characters), written by me when I pick the
  note up: a factual summary naming the fighter / feature and the problem; test-account notes start with "[test]".
  - Column `title` in `feedback`; set only with `fb.py set --title`; every change is a `status_history` entry
    (`set title: "..."`).
  - `fb.py list` shows it in place of the raw text, `fb.py show` prints it; pull.py's per-note `report.md` uses it
    as its heading and the overview `/data/feedback/report.md` lists it.
  - The Lab's Feedback tab shows it as the note's headline (and in the replay box's heading); the player's list
    shows it in bold at the top of each card, and the in-game "Reply to..." picker lists the titles. The full text
    stays below.
- **The Brawler Lab's Feedback tab** (`tools/brawler/chainlab/feedback.js`) lists the feedback. Each row shows the
  date, versions, the note as sent with the raw transcript under it, and the status and release as text. A play
  button plays the voice, and the screenshot opens from the row.
  - It filters by status and category. Reopened notes come first; each note shows his reply thread (voice playable).
  - Category and fighters can be edited in the row.

## Replay in the browser (the Brawler Lab's Feedback tab)

Each note's **Replay** button (or the link `brawler-lab/#fb=<id>`, with `&play` to start at once) plays the note in
the page.
- **The core:** Geolith compiled to WebAssembly (`tools/brawler/chainlab/build_wasm.sh`, the same tree, save states
  v3). `web_core.c` gained `wc_system` so the replay boots what the player booted.
- **The engine:** `chainlab/fbreplay.js`, shared with `tools/feedback/replay_node.js`, which runs the same proof in
  Node.
- **What the page loads:**
  - the note's game build by sha256, from `feedback-api/rom/<sha>` (gzip, 12 MB in transit, cached for good by the
    browser; one wasm instance per build);
  - the Lab's BIOS (SNK's MVS BIOS files);
  - the note's states and inputs.
- **How it plays:** the page fast-forwards silently from the latest kept state at or before press - 600 frames (at
  most 600 frames, about 20 ms), then plays the last ~10 s with sound.
  - Pause, step one frame, speed 1x / 1/2 / 1/4 / 1/10 (sound only at 1x), and restart.
  - The press screenshot is shown beside the replay.
- **The check at the press:** the state is compared byte for byte with `press.state`, and the SHA-256s are shown
  (https only). Kept states passed on the way are compared too.
- **ROMs and BIOS stay behind the Lab's login.** The service archives each build a note was played on, so
  publish_vps.sh's pruning to the last 3 builds never loses one.
- **Proven 2026-10-06:**
  - every pulled note was byte-identical in Node (wasm) from the window start, including Bruno's own Xiaomi notes;
  - note 20261006-154517-b3f3 was byte-identical at the press in desktop Chrome (headless) and in Android Chrome
    113 in the emulator, on a local copy of the page.

## Determinism

- **The Geolith fix:** save states v3 (geolith commit fa094e0) add the 68K's pending reset cycles and the YM2610's
  pacing counters. These are the SSG resampler index and the FM prepare sweep counters.
  - Before v3, a state loaded into a freshly loaded core drifted by a few cycles within a frame. The picture stayed
    the same, but the bytes did not.
  - v2 states still load.
- **Proven:** byte-identical replays from an x86_64 Android emulator to the x86_64 desktop.
- **Not yet proven:** an arm64 device (the tablet) replaying on the x86_64 desktop. The first real bundle will tell,
  in its report's Determinism line.

## Lifecycle (every note's timeline)

Every step of a note is a timestamped event with who did it; the tracker assembles them (server.py `timeline`) from
the note, its status history, the events table, the test attempts and the replies, oldest first.

| Event | Where it comes from |
|---|---|
| found | the note itself: player, game version, device, Android |
| triaged | `fb.py set` (title, category, fighters, `--todo 166`, `--fix`, `--rca`) |
| read / in_progress / wont_do / duplicate | `fb.py status` (pull.py sets read) |
| commit, fixed | `fb.py status ID fixed --commit SHA` (on the branch, not yet published); backfill: the TODO item's commits |
| released, shipped | `fb.py status ID shipped --release 0.0.78`; backfill: the "Brawler <version>:" commit |
| scenario | scenario.py: the recipe written / changed, a state generated on a build (version + sha) |
| test | each attempt from the player or the Lab: result 👍 / 👎 / left without a verdict, build, system, time spent, the replay id |
| verified / reopened | the thumbs (player list, test banner, Lab) |
| reply | his replies; Lab replies (Reply on a card) |

- **Shown in:** `fb.py show ID` / `fb.py timeline ID`, the Lab card's More, the player card's More (newest last),
  pull.py's per-note report.md (a Timeline table) and the overview.
- **Fix and root cause:** `fb.py set ID --fix "..." --rca "..."`, one or two plain sentences each, written when the fix
  ships; the cards show them under `[FIX 0.0.x]`.
- **Backfill:** `tools/feedback/backfill_history.py [--dry] [--only ID]`: each note's TODO item(s) (TODO.md items that
  quote its id, or "TODO #N" in its history), the item's commits on brawler, the fix commit (the last item commit that
  touches code before the release) and the release commit; posted as events, idempotent. Run 2026-10-06 over all 65
  notes; fix / rca written by hand for the 29 shipped ones.

## Scenarios: verify an issue (Player 0.0.22)

Bruno: "there is no save state for me to enter some sort of verify issue". Each fixed note gets a test scenario: a save
state of the published build set up to show the fix, with what to do and what to expect.

- **The recipe** (`tools/brawler/scenarios.json`, then the tracker's `scenarios` table): title, do, expect, setup, the
  "do" as inputs (`do_keys`) and the proof length. Setup modes:
  - `lab` (default): the Chain Lab through the lab mailbox (main.c lab_start: P1 against a standing dummy, no AI, P1's
    life refilled, the dummy gets up): fighter, dummy, gap (px), x, face, extra dummies (copies of the dummy at dx);
  - `stage`: campaign stage + wave (lab req 4: the enemies' AI on);
  - pokes: meter, P1's hp, lives[0], and `pre` inputs played before the save. Nothing else is touched.
- **`tools/brawler/scenario.py`** (our harness, the repo's Geolith core, the player's settings: region us, arcade =
  SNK's MVS BIOS without a card = key `mvs-mvs`, console = UniBIOS in AES mode with the card = `uni-aes`):
  - `gen ID [--upload]`: power on, setup, save the state for both systems, then play `do_keys` + `proof` frames:
    `clip.gif`, `sheet.png`, `<key>_start.png` in /data/feedback/scenarios/<id>/<sha12>/;
  - `verify ID`: two generations byte-identical, and the state loaded in a fresh core (after other frames) replays
    do + proof to the same end state;
  - `publish`: every shipped / reopened / fixed note with a recipe, on the current build, uploaded;
  - `backfill`: every recipe of scenarios.json; `put ID`, `show ID`.
  - The harness reads fighter_t's offsets and the symbols from the sources: scenario.py snapshots, per ROM sha,
    examples/brawler + sdk at the release commit + build/rom.elf and headers (`/data/feedback/scenarios/_builds/`),
    taken while the repo's brawler.neo is that build. A working tree that moved on cannot poke the wrong offsets.
- **Server:** states in `DATA/scenarios/<id>/<sha>/<key>.state` (+ the proof files); the player gets
  `/brawler/feedback/mine/scenario/<id>/<sha>/<key>.state` (404 = none for that build), the Lab `feedback-api/scenario/...`.
  `/test` (player) and `/api/test` (Lab) log the attempts; a 👎 attempt's replay goes to `DATA/attempts/<id>/`.
- **Publish routine:** after `tools/brawler/publish_vps.sh ROM VERSION`, run `python3 tools/brawler/scenario.py publish`
  (about 5 s per note) so every testable note has its state on the new build. Proven 2026-10-06 on 0.0.81 (29 notes).
- **Every fix ships with its scenario (2026-10-07).** A note marked shipped without a recipe never reaches his test
  queue (the queue serves only notes with a state for his build): 0.0.83-0.0.92 shipped 13 fixes that way and the player
  showed them as shipped with "no test yet". So, with each fix, before the release: write its recipe in
  `tools/brawler/scenarios.json` (setup, Do with the exact input, Expect what he should see / hear; select-screen and
  title cases use the `select` / `title` modes and start at that screen), `scenario.py put ID`, `scenario.py verify ID`
  (byte-identical twice, replayed the same in a fresh core), look at its `sheet.png`; the publish routine then generates
  and uploads it. `scenario.py lint` checks every shipped / reopened / fixed note's recipe (texts, roster names, stage,
  input syntax) and lists every shipped note without one; `publish` runs it first and prints each as a WARNING.
  Setup modes added for these: `select` (the title, a coin, START: the select screen as a player reaches it; `cursor`
  walks the cursor to a fighter with the stick, `unlock` shows every boss) and `title`; `stage` takes `cam` (the camera
  short of the wave's lock point, for a place in the scenery).
- **In the player (0.0.22):**
  - The card (Bruno's layout, the same in the Lab): title / "44 min ago on 0.0.17" (long press: the exact time) / the
    screenshot (a tap = VERIFY when a state exists for the build and system he runs: "▶ TEST IT" in its corner; else
    "no test yet" and a tap opens it full screen) / `[FIX 0.0.78]` / Fix and Cause / More (collapsed: his latest reply,
    the note, the voices, the timeline, the origin) / Fixed - Broken - Reply.
  - VERIFY mode (TestMode.kt): the state is downloaded (cached), loaded between frames (Native.loadState: the replay
    ring restarts at it), one frame shown, paused, under a banner: "TEST n of N: title / Do / Expect" with Play,
    Restart (the state again, running), 👍 Fixed, 👎 Broken (hold: the voice records and the attempt is captured;
    released: the transcript to correct, Send = status reopened + the voice + the attempt's replay), Next / Done, ✕.
    Leaving a loaded note without a verdict logs it as abandoned; leaving the mode soft-resets the game.
  - The test queue: the list's "▶ Test queue (N)" button, or the game screen's list button (a menu "My notes / Test
    queue (N)" whenever notes can be tested): every queue-eligible note that has a state for his build and system,
    oldest first, one after the other.
  - **The banner (0.0.26; Bruno: the Do / Expect box took too much room and could not be hidden):** inside the
    picture. One line always: the pill "ⓘ TEST n/N: title" and the controls ▶ / ❚❚, ⟲ Restart, 👍, 👎 (hold and talk),
    Next / Done, ✕. Under it, expanded: the title in full, Do, Expect, the status. In full for 3 s when a test loads,
    then the pill alone. A tap on the pill = expand / collapse; expanded it is ~60 % opaque (the game shows through);
    dragging the pill moves the banner to the picture's other edge (top / bottom, kept for the session). An error
    (no state, not sent) expands it; the 👎 note box stays open under the pill.
  - **The banner (0.0.27; Bruno: "the buttons are way too small: keep the buttons at the END of the feedback,
    occupying the full width with evenly proportioned buttons (no risk of mishap)"; "when collapsed, just keep it as a
    small [i] in the top-left corner of the Neo Geo canvas"):** expanded = a box at the picture's top, ~60 % opaque:
    [i] + "TEST n/N: title", Do, Expect, the status, a hint line, then the buttons as the LAST rows, full width, equal
    widths, labelled in words: ▶ Play / ❚❚ Pause, ⟲ Restart, Next / Done, ✕ Leave (48 dp), 16 dp of gap, then the
    verdict row 👍 Fixed (green) | 👎 Still broken (hold and talk) (red), 64 dp tall, 24 dp apart. Holding 👎 opens the
    note box in the buttons' place (they hide while it is open): the text to correct, then its own last row Cancel |
    👎 Send: still broken (56 dp). Collapsed = only a small [i] (34 dp, outlined) at the picture's top-left corner, the
    same spot as the expanded box's own [i]; no pill, no controls. A tap on [i] expands (and pauses the game); the [i]
    in the box collapses. A test loads expanded and paused; ▶ Play and ⟲ Restart collapse it so the game is free. The
    0.0.26 drag to the other edge and the 3 s auto-collapse are gone (the [i] has one fixed spot). Proven in AVD
    JanusPhone (test hook, fake note id, nothing sent): /data/feedback/proof_0027/ (portrait + landscape expanded and
    collapsed, the 👎 note box).
  - **Test hook (0.0.26):** `test_scenario.json` (a note row: id, title, scenario {title, do, expect}) +
    `test_scenario.state` pushed to the app's external files dir open that note in VERIFY mode on the next resume
    (admin only; both files consumed; read on the second resume, once the game runs: launch, Home, launch again).
    Banner proof without a server scenario.
  - **The test queue rule (0.0.23, server.py queue_info, every /mine and /api/list row's `to_test` + `tested_on`):** a
    note is eligible while its status is shipped and no verdict (a 👍 or 👎 test attempt, player or Lab) was given on
    its release or a later build (`tested_on` = the game version of the last verdict); the player adds "release at or
    before the build he runs". Any verdict takes it out at once (👍 verified, 👎 reopened: it stays in Open with its
    status); it comes back only when a later ship gives it a release newer than `tested_on`. The "Shipped: test it"
    filter and the badge are the queue (0.0.22 also served every reopened note, so a 👎 note came back on every run).
  - **Abandoned** = he left a loaded note without a verdict (Next, Done, ✕, or the list started another queue): logged
    once per note, never after a verdict or while one is being sent (0.0.22 logged Done twice). An abandoned note stays
    in the queue: it was never judged.
  - Proven in AVD JanusPhone on 0.0.81 (test account): the banner, Restart, 👎 (reply + attempt replay, replayed
    byte-identical on the desktop by pull.py --replay), the queue moving on, 👍 setting verified
    (/data/feedback/proof_0022/).
- **In the Lab:** a card's screenshot (or "▶ Test queue") runs the same state in the browser (the wasm core, arcade
  system) under the banner; keys WASD + U I O P or the arrows + Z X C V; Restart, Show expected (the recipe's own
  inputs), 👍 / 👎 (a Lab attempt: verified / reopened), Next. Its "▶ Test queue" and "Shipped: test it" use the same
  `to_test` (the Lab runs the newest build, so no version check).

## Decisions (Player 0.0.24)

Bruno: "what about serving the arti-feedback directly in the APK?" A visual choice (before / after of a fix, a pick
between options, one picture to ship or not) is a first-class tracker item, answered in the player or the Lab
instead of on a claude.ai artifact page.

**Clarity rules** (Bruno, 2026-10-07: "make sure it's not ambiguous, the questions have to be very clear"). The
server refuses a decision that breaks one (server.py `check_review`, so every path is held to them):
- **One question per decision:** a single concrete choice, one sentence ending in "?" (no second sentence, no "?" in
  the middle).
- **Every image labelled with what it is:** "BEFORE, title screen: 0.0.87, the old system font" / "AFTER, title
  screen: Kizuna's font" (two words at least).
- **Every answer button names its exact outcome in game terms:** "Kizuna's font (gradient + shadow), as shown", "The
  old font". Never Keep / Change / Yes / No / Ship it / Needs work alone. 2 to 5 buttons.
- **Each button carries its effect:** one line saying what changes in the game if he picks it. The card lists them
  under the question ("What each answer does"), and the confirmation repeats the picked one.
- A button whose label starts with "Needs work" needs his note (typed or spoken); the player and the server refuse
  it without one.

**The tracker (server.py):**
- `reviews`: id, created, updated, by, audience (the Oros account it is put to; '' = every account), title, question,
  kind (before_after | pick | single: the card's layout only), images (JSON [{label, file}], the files in
  `DATA/reviews/<id>/`), options (JSON [{label, effect}]), todo, notes (linked feedback ids), status (open | answered),
  answer, answer_text, answer_raw (the transcript), answer_audio (`answer_<n>.m4a`), answered_at, answered_by,
  answer_source (player | lab | artifact | chat), answer_origin (JSON: player version, install, device, Android, IP, UA).
- `review_history`: review_id, at, by, kind (created | answered), text, audio. A new answer replaces the current one;
  the history keeps every answer.
- Every linked note gets `decision` events in its timeline (asked, each answer).
- API: `POST /api/review` (create), `GET /api/reviews[?status=]`, `GET /api/review/<id>[/file/<name>]`,
  `POST /api/review_answer {id, answer, text?, source?}` (the Lab; over ssh an answer given elsewhere),
  `POST /api/review_delete {id}`. The player: `/mine` carries `reviews` (the decisions put to the user; older players
  ignore it), `GET /brawler/feedback/mine/review/<id>/<name>`, `POST /brawler/feedback/review {id, answer, text,
  raw_transcript?, tx_id?, audio_b64?, audio_name?}` (token only, size + rate capped like /reply).

**fb.py:**
- `fb.py review add --title T --question "...?" --kind before_after --image "LABEL=path" ... --option "LABEL=EFFECT" ...
  [--todo 182] [--note ID] [--for bruno]` (images in display order; for before_after give BEFORE, AFTER per pair)
- `fb.py review list [--status open|answered]`, `fb.py review show ID` (the answer, note, transcript, voice, origin,
  history), `fb.py review delete ID`
- `fb.py review answer ID --answer LABEL --by bruno --source artifact|chat [--text ...]`: an answer he gave elsewhere.

**In the player (0.0.24):**
- The game screen's feedback button: its badge counts the test queue plus the open decisions. When either is
  non-empty, the tap opens a menu: "Decisions (N): pictures waiting for your answer" / My notes / Test queue.
- The list has a second filter row: **Decisions to answer (N)** / **Answered (N)**.
- **The card:** DECISION #n: title / asked when, TODO / WAITING FOR YOU or ANSWERED / the question (large) / "What
  each answer does" / the images, each under its label.
  - Phone portrait: one per line, full width. Landscape: a before / after pair side by side. Every picture stays
    within 72 % of the screen height.
  - Pictures scale nearest-neighbour (`Decisions.PixelView`), so a game screenshot stays pixel-exact.
  - A tap opens it full screen (`Decisions.ZoomView`): pinch zoom up to 16x the fit, drag, double tap = fit / 4x.
    ◀ Previous / Next ▶ flip through the decision's images at the same zoom and position, so the BEFORE / AFTER
    pixels line up.
- **Answering:** a note box (type, or "Hold to talk": recorded and transcribed like a reply), then one big button per
  answer. A confirmation shows the effect and the note, then "Send this answer". The card moves to Answered, showing
  his answer, note, voice (play) and "Change my answer".
- **Lab (Feedback tab):** the same two filters. The card has the images full width (`image-rendering: pixelated`; a
  click opens one at full size), a note, the answer buttons and the history. Answered cards have "Change the answer".
- **Proven 2026-10-07** in AVD JanusPhone (test account, a separate test decision, deleted afterwards). The proof
  covered: the badge (1), the menu entry, the card with both pictures side by side, full screen with double-tap
  zoom, a pan, and ◀ keeping the zoom on the other picture. It then sent a "Needs work" answer with a note and a
  voice (the test-audio hook, transcribed). The card moved to Answered, the badge cleared, and `fb.py review show`
  read the answer, transcript, voice and origin back. Pinch itself was not driven (adb has no multi-touch);
  ScaleGestureDetector handles it. Screenshots: `/data/feedback/proof_0024/`.

## Character Lab: live fighter configs and the pack catalogue (2026-10-10)

Bruno's design: one Lab **shell** build + swappable **character packs** (Robert, Kim first). The web Assembly pages
(arbitrage.html, workshop.html, the Chain Lab's chain tool) write each fighter's live config; the Player's Character
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
- Later (noted, not done): the Chain Lab's chain-timing knob folds into the Assembly.

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
