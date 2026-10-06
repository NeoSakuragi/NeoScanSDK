# Voice feedback from the NeoScan Player

Bruno plays the brawler on his tablet and says what is wrong. Each note arrives with an exact replay of the last
minute. Built 2026-10-06, Player 0.0.13.

## In the player (android/)

- **The mic button** sits next to the soft reset. Hold it and talk.
  - At the press, the emulation thread writes the replay data between two frames (`Native.feedback`, player.c).
  - While the button is held, the voice records (AAC, 16 kHz mono, 32 kbps, `audio.m4a`).
- **The game freezes at the press** (0.0.14), not the release: the replay window and the screenshot end at the frame on screen
  when the button went down, and the game stays frozen while he talks and while the box is open.
- **Release:** The voice goes to the server, which transcribes it at once (about 2 s).
  - The text comes back into an editable box. Fix it or add to it with the keyboard.
  - **Send** sends the final text with the bundle. **Cancel** drops the bundle. Either one resumes the game.
- **A tap** (under 0.4 s) opens the box empty, for a typed note. That note carries the replay too.
- **Offline, or the server fails:** the box opens empty and says "transcription unavailable". The voice still goes
  with the bundle, and the server transcribes it when the bundle arrives.
  - A bundle that cannot be sent stays queued in `files/feedback/queue`. It is retried at start and every minute.
  - The toast says "Feedback sent" or "Queued".
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
- One finger draws while another holds the mic. Pen: red / green (the round button), Undo, Clear.
- At the release, the note box comes up under the canvas, and the canvas stays live until Send or Cancel.
- The bundle keeps `screen.png` clean (the replay checks it). `annotation.png` holds the strokes alone, on
  transparent. `screen_marked.png` is the screenshot with the strokes. Both are 4x the screenshot.
- pull.py's report and contact sheet use the marked picture, and so does the Lab tab, with the clean one linked.

**My feedback (0.0.15, Settings > My feedback notes):** his notes, newest first, from `GET /brawler/feedback/mine`.
- Each card has the date, the versions, the origin, the note, category and fighters, and the status with its history
  and the developer's notes.
- The screenshot (the marked one; tap for full screen) and the voice (play / stop) come with the token.
- Pull down or press Refresh to reload.
- **From the game screen (0.0.18):** the list button (three lines) sits next to the mic in portrait and under START
  in landscape. A tap opens the list; the game pauses while it is open and resumes on back. Its red badge counts the
  notes in "Shipped: test it" plus the reopened ones, refreshed at launch and on every return to the game.
- **The game version he runs (0.0.19)** comes from the ROM file itself, not a pref: a file whose sha256 is the last
  download's takes that download's version and build; any other file (pushed by hand) takes the "V0.0.x" of its own
  title screen (P ROM), build "local". Worked out once per file (size + mtime). The list's top line, its filters, the
  badge and the bundle's `rom_version` (the note's game_version) all use it.

**Threads (0.0.17).** The list answers back.
- **At the top:** the build he runs (game version and build, player version).
- **Filters** (remembered): **Open** (every status but shipped, won't do, duplicate and verified), **Shipped: test it**
  (shipped in a release at or before the game version he runs) and **All**, each with its count.
- **Under each note:** his replies, oldest first (a voice reply plays), and three buttons:
  - **👍 Fixed** (after a confirmation): status `verified`.
  - **👎 Still broken:** a reply box opens (optional); Send sets status `reopened` with the text and voice.
  - **Reply:** hold "Hold to talk" (the voice records while held, then goes to `/transcribe`; the text lands in the box
    to edit) or type, then Send. No replay bundle.
- **From the game:** the note box (mic press or tap) has **Reply to...**: it lists his open notes and the shipped ones
  he can test; the one he picks gets the text and voice as a reply instead of a new note. The replay and the drawing
  are dropped.
- Everything goes to `POST /brawler/feedback/reply` (the Oros token only; no legacy access).

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
- **Statuses:** new → read (pulled) → in_progress → shipped (with a release, e.g. 0.0.71), wont_do, or duplicate (of
  another id); then the player's own verdict: verified (thumbs up) or reopened (thumbs down).
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
