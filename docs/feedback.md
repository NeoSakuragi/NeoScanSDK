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
- **Public:** nothing since 2026-10-14 (the APKs carry the BIOS): Brawler Dev from `/brawler/download/` (admins), the Brawler app by the link its update notice opens (see "Roles and the two apps").
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
  date. A tap pauses the game and lists "App 0.0.x is ready: Update" (0.0.42: was "Player ...") and / or "Game 0.0.x: download and restart"
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

## Character Lab

The live fighter configs, the shell / pack catalogue, the Player's Character lab, Send to Player, the Fighter Lab
and the piece knobs (with their server API, `/api/lab/...`) are documented in **docs/character_lab.md**.

## Roles and the two apps (2026-10-14, replaces T2's "Shared players")

Every brawler account is an Oros account (canneji.duckdns.org/oros). Its brawler role is an Oros user tag:

- **brawler_admin**: everything (the Lab, the Factory, the Chain Lab / Fighter Lab, the dev builds, the decisions, the
  test queue, Brawler Dev).
- **brawler_tester**: the Brawler app only: the game, the pad, the Feedback button (upload, transcribe, reply and thumbs
  on his own notes, his own `/mine`), and his allowed build.
- **no tag**: an ordinary Oros user. Both apps refuse him ("This account has no access to the brawler").

**Setting a role** (on the VPS; Oros reads the tags from its DB at every check, so a change applies at once):
`cd /root/oros-server && ./oros-server user-tags --name=Wael --add=brawler_tester` (`--remove=` takes one off;
`list-users` shows the tags). A new account: `./oros-server add-user --name=X --password=- < file` (`-` = the password
from stdin, so it never shows in ps or a shell history).

**The gates.**
- Oros: `/api/authcheck?tag=a,b` = 204 only for a user with one of those tags, else 403 (plain `/api/authcheck` is
  unchanged for every other page); `/api/whoami` returns `tags`. Oros itself gates nothing on tags.
- nginx (`tools/feedback/deploy_vps.sh`): `/brawler-admin-auth` = `/api/authcheck?tag=brawler_admin`. It gates
  `/brawler-lab/` (Chain Lab, Fighter Lab), `/brawler-factory/` (not `/decisions/`, the SoccerFury page: plain Oros login), `/brawler-lab/feedback-api/`,
  `/brawler/lab/` (+ `dl/`). `/brawler/download/` (the dev ROMs and the Brawler Dev APK) goes through the service's
  `/dlauth`: admins only. Nothing under `/brawler/download/` is public any more.
- The feedback service (`server.py`, `brawler_role`): the role from `/api/whoami`'s tags (cached 1 min). Admin only:
  `/dlauth`, `/test`, `/review`, `/mine/scenario/...`, the decisions in `/mine`, the Lab (`lab/`, `api/lab/`), the
  signed-in API (`api/`). Tester: `upload`, `transcribe`, `reply` (his notes), `/mine` (his notes, no decisions), `me`,
  `share/`. No role: 403 everywhere.

**Two apps, one code base** (`android/app/build.gradle.kts`, flavor dimension "app"; one code path, `BuildConfig.DEV`):

| | Brawler Dev (flavor `dev`) | Brawler (flavor `brawler`) |
|---|---|---|
| Package | `com.neoscan.player` (the house Player: updates in place) | `com.neoscan.brawler` (installs beside it) |
| Who signs in | brawler admins only (a tester: "Brawler Dev is for brawler admins") | admins and testers; an admin gets the same app as a tester |
| What it has | everything as before: Character lab, Assembly WebView + JS bridge, live configs and pack swaps pushed into the game, test queue, decisions, notes list | the game, the pad, the Feedback button (mic) |
| Code only in it | `src/dev/`: `CharacterLab.kt`, `Assembly.kt` | `src/brawler/`: inert stubs of both, the icon, a manifest without the settings page |
| Permissions | INTERNET, RECORD_AUDIO, VIBRATE + the self-update's REQUEST_INSTALL_PACKAGES, UPDATE_PACKAGES_WITHOUT_USER_ACTION, POST_NOTIFICATIONS | the same (since 0.0.42); no cleartext HTTP |
| Builds | `/brawler/download/` (the newest) | `share/latest.json`: the newest build up to the account's allowed one |
| App updates | the same code (`src/main` `PlayerUpdate.kt`, 0.0.42): downloads and installs itself; may be flagged by antivirus apps (accepted). Offer: `player.json` | offer: `GET me` app {version, code, url, size, sha256}; the ticket link is also the browser fallback |
| Signing | the build machine's debug key, as before | `/data/brawler-share/shared-release.jks` (`signing.properties`), never the Oros key |
| Build | `./gradlew assembleDevDebug` | `./gradlew assembleBrawlerRelease` |
| Publish | `tools/brawler/publish_vps.sh --apk-only <app-dev-debug.apk> <version>` | `tools/brawler/publish_app.sh <app-brawler-release.apk>` |

- **The role in the apps:** after the Oros login, `Auth` asks the service's `GET /brawler/feedback/me` ->
  `{user, role, build, app {version, code, url}}` (403 = no role). It asks again at every renewal and every start
  (`Auth.recheck`); a refused role signs out with the reason on the sign-in screen. Offline, the last known role stands.
- **Allowed builds:** the Factory's **Players** tab (`?tab=players`, `players.js`, the `players` section, saved live, no
  ship): one row per Oros account with a brawler tag, a build picker, Save. A tester with nothing assigned gets
  nothing; an admin with nothing assigned ("Newest") gets the newest. Assigned builds are hard-linked into
  `/data/brawler/feedback/share/builds/` so publish_vps.sh's keep-3 pruning never removes them.
- **The Brawler APK:** `/data/brawler/feedback/share/app/brawler-<name>-<code>.apk` (last 3 kept). `GET me` offers the
  newest as `app/<file>?t=<ticket>`: an HMAC ticket (`share/secret`, 24 h, the user in it), because the phone's browser
  has no Oros token. Without a valid ticket: 404. The APK carries the BIOS, so it is never public. `me` also gives its
  `size` and `sha256` (0.0.42), which the app checks after its own download.
- **The app's self-update (both apps, 0.0.42; one path: `src/main` `PlayerUpdate.kt`, as Brawler Dev since 0.0.21, see
  "Self-update" below).** The launch screen shows "A new version of the app is available (0.0.x)" (Update / Play) as
  soon as `me` offers a higher versionCode, or "App 0.0.x is ready" once the background download (launch + every hour)
  finished. Update = the download in the app if it has not finished (progress on the banner; size + sha256 checked), then
  Android's installer (PackageInstaller session). The first time: one line ("Android asks once: turn on 'Allow from
  this source' for Brawler, then come back; the update goes on by itself") and Android's "Install unknown apps" screen
  for the app; back with it on, the install continues by itself. Android 12+ may install without a prompt; 10 / 11
  show Android's confirmation. If anything fails (download, Android's refusal), a dialog says why and offers **Open in
  the browser** (the ticket link: the old path) and Try again. Same release key as the installed app, so the update
  installs over it; app data (sign-in, save, notes, the game build) stays. Testers on 0.0.41 or older still get 0.0.42
  through the old browser link; from 0.0.42 on it is in-app. Proof 2026-10-16 (AVD NeoPhoneP40, Android 10, local
  stand-in Oros + server.py): `/data/brawler-share/proof_0042/` (0.0.41 -> offer -> Update -> download checked ->
  "Allow updates" -> Install unknown apps -> back -> Android's install prompt -> 0.0.42 installed, still signed in;
  a broken 0.0.43 -> INSTALL_PARSE_FAILED_NOT_APK -> the fallback dialog -> the browser).
- **Notes:** stored with user = the Oros account; `fb.py list` shows `Wael [tester]`, `fb.py list --user Wael` filters.
  `FB_LOCAL=1 FB_BASE=http://127.0.0.1:<port>/api/ fb.py ...` talks to a local service (proofs).
- **Proof builds:** `-PorosBase=http://10.0.2.2:<port>/ -PfeedbackBase=http://10.0.2.2:<port>/ [-PromBase=...]`
  (cleartext is allowed only then). Proof 2026-10-14: `/data/feedback/proof_0036/` (screens, HTTP codes, fb.py list,
  the Factory Players tab at 390 px).
- **Player 0.0.37 (the tester release):** the Brawler app has no settings page (SettingsActivity removed from its
  manifest; `Prefs` returns fixed values: landscape, 50 % scanlines, the rest at their defaults) and is landscape only
  (game + My tickets). Its launcher icon is the NEO·GEO wordmark of the MVS BIOS eye-catch
  (`tools/brawler/make_tester_icon.py`, `src/brawler/res`). Both apps: a PROFILE button (the account's initial; under
  START in landscape) opens the profile menu: account + role, game build + app version, My tickets (FeedbackListActivity,
  testers too; Decisions filters admins only), the admin's Decisions / Test queue / Character lab (Brawler Dev), Log out
  (confirmed; `Auth.signOut` drops the sign-in AND the downloaded build, so the next account gets its own). The update
  button (down arrow) is drawn only while a newer build / app is waiting or downloading, in both apps, for every role.
  Proof: `/data/brawler-share/proof_0037/` (Wael 0.10.92 -> log out -> Asenka 0.10.109).
- **Retired:** T2's separate share accounts (`share/login`, the `nsp1.` tokens, `share_accounts.py`,
  `share/accounts.json`): Wael and Asenka are Oros accounts with brawler_tester, under the same names, so their
  assignments in the `players` section still apply.

## Cloud saves (Player 0.0.39)

A game's save follows the Oros account: sign in on another phone (or after a reinstall) and the save is there. Any
`.neo` game, keyed by the ROM's name (`brawler`). Both apps, one code path (`android/.../SaveSync.kt`).

- **What is saved:** the emulator's backup files as player.c's `flushSaves` writes them: `<rom>.nv` (MVS backup RAM:
  the brawler's unlocks), `.srm`, `.mcr` (AES memory card), `.brm`. Small (the brawler: 66 KB), capped at 1 MB.
- **On the device:** one save dir per account, `files/save/<user>/` (the pre-0.0.39 shared files move into the first
  account that signs in). The next account after a log out never sees another's save.
- **At the game's start** (after the sign-in, before the core loads): GET the account's save. Used when it is a
  revision this device has not synced yet and the local save has not changed since its last sync. Both changed =
  newest wins (the time each save last changed); the other one goes to the server as a backup revision.
- **Sending:** after every flush (each pause / the app to the background, the emulation thread's end, and every 2 min
  while playing, so an unlock reaches the server without a pause), when the files changed. PUT with the last synced
  revision; 409 = another Player saved meanwhile: newest wins as above. Offline = the local save plays; it is sent at
  the next flush.
- **Reset game save** deletes the server's copy too (retried until it goes through). Another Player whose save was
  in sync erases its own at its next start.
- **Server** (`server.py`, nginx `/brawler/feedback/saves/`): `GET | PUT | DELETE saves/<game>`, the signed-in
  account's own save only (role admin or tester). `DATA/saves/<user>/<game>/state.json` + `r<rev>.json` (each
  revision in full; the last 8 kept as backups, a deleted or losing save among them).
- **Proven 2026-10-15** in AVD NeoPhoneP40 against local services (test accounts cs-a / cs-b): cs-a played, the app
  data was wiped, cs-a signed in again and got his save back byte for byte; cs-b on the same device got a fresh save;
  Reset game save deleted the server's copy. `/data/brawler-share/proof_0039/`.

## Session recording (Player 0.0.41; keyframes 0.0.43)

Every play session of the game build is recorded and sent to the server while it is played, so a tester's whole
session can be replayed in the Lab, or watched live, a few seconds behind. Both apps, one code path. The sign-in screen
says so under the Sign in button: "Your play sessions are recorded for the developers."

- **In the player** (`player.c` `Native.sessionChunk`, `Session.kt`, called by `EmuThread` before every frame and while
  paused):
  - A **chunk** = the pads of its ~300 frames (~5 s), the same pads as inputs.bin (bit 15 of port 0 = a soft reset
    before that frame) + the SHA-256 of the save state at its start (taken before its first frame, as the feedback
    snaps): the viewer's drift check every 5 s. A pause closes the chunk so far (a short chunk). A chunk is taken before
    a soft reset asked for that frame, so the reset is the next chunk's first frame's RESET bit.
  - **Keyframes (0.0.43, Bruno's scheme):** only a KEYFRAME chunk also carries that state (gzip'd: 222 789 bytes raw,
    ~30 KB packed): every 1800 frames (~30 s, every 6th chunk), the session's first chunk, after a jump in the frame
    count (a test state loaded, a raw chunk dropped by the packer) and after a chunk dropped or refused on the way out.
    Still sent every 5 s (the inputs are small), so live stays ~5 s behind. Chunks of 0.0.41 / 0.0.42 = every chunk a
    keyframe; the server and the viewer take both.
  - Measured in the AVD (0.0.43, 51 min, 608 chunks, 101 keyframes): keyframe chunk ~30.5 KB, input chunk ~1.9 KB
    (~0.8 KB of it the JSON meta), **4.7 MB per hour of play** (0.0.41: 20.8 MB per hour).
  - **A session** = `<install id, 8 hex>-<UTC start yyyymmdd-hhmmss>`. A new one starts when the next chunk comes more
    than 60 s after the last (a pause > 60 s), with another ROM / system (another EmuThread) and in a new process.
  - Only the game build (`files/brawler.neo`, RomFetch.romFile) and only signed in; never the Character lab's shell.
  - Never stalls the emulation: the emulation thread copies the chunk out of the core (JNI, one memcpy); the gzip runs
    on one worker (bounded queue of 6, the oldest dropped), the upload on another (up to 240 chunks waiting, ~20 min, the
    oldest dropped). Offline / server down / 5xx: retried with a growing wait (5 s doubling to 2 min), in order; a 4xx
    (not 401 / 408 / 429) drops the chunk. Memory only: a chunk not sent when the app is killed is lost.
  - The POST body (little endian): `"NSCK"`, u32 1, u32 n + JSON meta (session, seq, start_frame, frames, paused,
    key (0.0.43), state (gzip / none), state_size, state_sha256 (every chunk), started (ms), rom_sha256, rom_version, rom_build, system key (`mvs-mvs` / `uni-aes`),
    hw, system_type, memcard, app (dev / brawler), app_version, app_code, device, android, install_id, user), u32 n +
    inputs (NSIN v1: `"NSIN"`, u32 1, u64 W, u64 P, the pads), u32 n + the gzip'd state (n = 0: none = not a keyframe; the
    server then checks state_sha256 is a SHA-256).
- **Server** (`server.py`, nginx `location = /brawler/feedback/sessions/chunk`, 1 MB body cap, zone `brawler_sess`
  60 r/min + burst 120 per address):
  - `POST sessions/chunk`: signed in, a brawler admin or tester. Checked: NSCK v1, the session id, seq / frames
    (1..1200), the inputs = NSIN v1 for exactly those frames, the ROM sha, the system key, the state gunzips to its
    size and sha256. A session belongs to the account that sent its first chunk (another account: 403). A chunk sent
    again (a retry) replaces itself. The storage box must be mounted (else 503: the player retries).
  - **Files on the storage box** (the VPS root disk is near full): `/mnt/storagebox/brawler-sessions/<session>/meta.json`
    + `<seq>.nsin` + `<seq>.sha256` (since 0.0.43's server) + `<seq>.state.gz` (keyframes only). **Index** in the tracker DB: `sessions` (id, user, install, started, first / last
    chunk time, chunks, frames, bytes, ROM sha + version + build, system, memcard, app, app version, device, Android, IP,
    paused) and `session_chunks` (seq, start frame, frames, state y/n = a keyframe (indexed), state size + sha256 (every
    chunk), bytes, time, paused, the pads
    zlib'd: ~200 bytes a chunk, so the inputs list never reads the storage box).
  - The first chunk of a session archives its build (`roms/<sha>.neo.gz`, from the published builds or the testers'
    assigned builds `share/builds`), so the Lab can load it after publish_vps.sh's keep-3 pruning.
  - Admin API (`/brawler-lab/feedback-api/`, brawler admins): `GET sessions` (newest first, `live` = a chunk in the last
    15 s, + the storage totals and MB per hour), `GET session/<id>[?after=SEQ]` (+ `keys`: the keyframes' seqs), `GET session/<id>/inputs[?from=SEQ]`
    (per chunk u32 seq + NSIN v1), `GET session/<id>/state/<seq>` (Content-Encoding gzip).
  - **Retention:** everything is kept for now. At 4.7 MB per hour of play (0.0.43): 100 h = ~0.5 GB, 1000 h = ~4.7 GB
    (the box has 623 GB free); the DB grows ~150 KB per hour.
- **The Lab's Sessions tab** (`chainlab/sessions.js` + `sessreplay.js`; `brawler-lab/game.html#sessions`,
  `#sess=<id>` opens one): one row per session (● LIVE, player, build, start, length; device on wide screens), the
  list refreshed every 5 s. A tap = the player: the session's build (`feedback-api/rom/<sha>`) + the Lab's BIOS in the
  wasm core (one core per build, shared with the Feedback tab), seek bar, Play / Pause, ×1 (sound) / ×2 / ×4. A seek
  loads the nearest keyframe at or before the target and plays the inputs silently up to it (at most ~30 s of play,
  ~3 s at ~550 frames/s). A live session opens on its latest keyframe, fast-forwards silently to its newest chunk and
  plays the chunks as they arrive (polled every 2.5 s): measured 5-6.5 s behind the newest chunk's end. **The drift
  check:** at every chunk boundary that follows the chunk played, the SHA-256 of the replay's state is compared with
  the recorded one ("N chunk boundaries checked (state SHA-256): all identical to the recording"). A difference is
  shown, the replay plays on ("drifting") and resyncs at the next keyframe; a missing chunk (a gap in seq / frames) is
  shown ("missing chunks before N"), the chunks up to the next keyframe are skipped and the replay goes on from it. Console sessions (`uni-aes`)
  need UniBIOS, which the Lab's BIOS file lacks (testers play arcade only).
- **What a session shows (2026-10-16, `chainlab/sessinfo.js`):** the list has two sections, **LIVE NOW** then the past
  sessions, one row each: player, build, character (P1, + P2 when two play), screen (title / select / fight / demo /
  bonus / ending / game over; in a fight the stage and the wave or BOSS), life % and drive chunks per player, length
  (device on wide screens; on a phone only player, character, start, length). Read from the session's latest keyframe
  (fetched as for a seek; "(25 s)" = how old it is at the session's newest chunk; an ended session: the latest
  keyframe showing a fighter, up to 4 back; ended rows cached in the browser). The single view and the wall tiles read
  the same from the running core every frame. **Where the RAM is:** Geolith's state v3 of the deployed core holds the
  68000 RAM at byte 153 777 and the VRAM at 67 625 (measured; a state of another size = unknown). **The build's RAM
  map** = `brawler-lab/ramsyms/<rom sha256>.json` (`chainlab/ramsyms.py`: symbol addresses from `build/rom.elf`,
  fighter_t offsets, the fighters' HUD names and the stages' names / wave counts from the ROM, the drive chunk size),
  sent by `tools/brawler/publish_vps.sh` with every build. A build without one (all builds before 0.10.148) shows only
  what its HUD shows (the fix layer: P1's name, P2's when two play) and the difficulty (BIOS RAM $10FD8A, MVS); the rest
  "—". The difficulty: MVS = the soft DIP's LEVEL-n (BIOS RAM), AES = the game's `difficulty`.
- **The live wall** (`chainlab/wall.js` + `wall_worker.js`; `brawler-lab/game.html#wall`, or Sessions → Live wall):
  every LIVE session in a grid of tiles (Auto = 1 / 2×2 / 3×3 by how many play, or chosen; on a phone one column of at
  most 2). A new live session joins by itself; one that ended (no chunk for 15 s) leaves 5 s later unless pinned (Pin).
  One Web Worker per tile, its own wasm core (the page compiles core.wasm once and hands the module over), the picture
  drawn by the worker into the tile's canvas (OffscreenCanvas): the tiles run in parallel on the machine's cores.
  Per tile the single view's live path: the latest keyframe, silent fast-forward to the newest chunk, then the chunks
  as they arrive (each tile polls `session/<id>?after=` every 1 s; 120-frame and 300-frame chunks alike), and a
  silent catch-up at ×4 when it falls more than 8 s behind. Tile header: LIVE / ENDED, player, build, the drift check
  ("✓ N same" / "✗ differs at chunk N", gap, drifting), how far behind; then the info line. Tap = hear that tile (only
  one sounds; Mute), double-tap = the single view at full size ("← Back to the wall"; the tiles pause meanwhile and
  join live again on the way back). A hidden page pauses the tiles.
  **Measured 2026-10-16** (headless Chrome on brunux, 12 threads; fake live sessions = recorded pads re-run on 0.10.148
  in 120- and 300-frame chunks + 0.10.139's own recording, posted in real time to a LOCAL server copy by
  `chainlab/wall_feed.py`; `wall_synth_node.js` makes them, `wall_measure.js` measures, `wall_proof.js` the behaviour):
  the whole browser 0.18 cores / 486 MB PSS on the Sessions tab without the wall; 1 tile 0.39 cores / 587 MB; 4 tiles
  0.94 / 842 MB; 9 tiles 2.0 cores / 1146 MB = **~0.2 core and ~73 MB per tile** (each worker busy 15-19 % of a core,
  58-60 frames/s, 134 MB wasm heap reserved), every tile's drift check identical, 1-5 s behind the newest chunk.
  The grid stops at 3×3 (9 tiles: the readable size on a desktop screen); CPU and memory would allow far more on this
  desktop. A phone: at most 2. Files: `/data/tmp/livewall/` (bin/start.sh = the local stack, shots/, proof/).
- **Determinism, proven 2026-10-16** (AVD NeoPhoneP40, x86_64, the Brawler app 0.0.41 built against local services: a
  stand-in Oros + server.py, account role tester; build 0.10.139): a 3 min 14 s session (39 chunks: boot, title, select,
  fights, a 10 s pause = a 70-frame chunk, a soft reset at frame 9002) replayed in Node
  (`tools/feedback/session_replay_node.js SESSION_DIR [ROM]`): 38 / 38 chunk joins byte-identical, the last chunk's state
  SHA-256 7c2d6c04... = the recorded one. Headless Chrome on the page: live view, seek, ×4, 390 px. A pause of 70 s
  started a new session (replayed too: 18 / 18 joins identical); a 40 s server outage was bridged by the retries, the 8 chunks held back arrived in order, none lost. Files:
  `/data/tmp/sess_proof/` (screens, scripts). Not proven: an arm64 device (same open point as the feedback replays).
- **Keyframes, proven 2026-10-16** (AVD NeoPhoneP40, the Brawler app 0.0.43 against local services, build 0.10.139's
  ROM): a 51-min session (608 chunks, 101 keyframes, play + attract + a pause) replayed in Node from its first
  keyframe: 607 / 607 boundaries SHA-identical; from each of the 101 keyframes loaded into a fresh core, its chunk
  played: 101 / 101 identical at the next boundary. A chunk left out (`--drop 40`): "gaps [41], resyncs [42]"; pads
  flipped in chunk 20: "mismatches [21], resyncs [24]". The page (headless Chrome): live join mid-session (16 / 16
  boundaries identical over 60 s), seek, ×4, the same session re-posted without chunk 40 (gap shown, resync at 42,
  a seek into the gap starts at keyframe 42). **Found on the way, fixed in Geolith** (ed942fa, `ymfm_opn.c`
  `opn_state_load_ext`): a load ran a full FM prepare, which also clocks the key state, so a key-on pending in the
  state started its attack at the load instead of at the channel's next prepare: from a loaded state the FM operators
  drifted from the recording (from minute 8 on, every keyframe; 0.0.41's seeks had it too). A load now rebuilds only the
  operator caches. Files: `/data/tmp/sess_key_proof/` (scripts, page shots).
