# Voice feedback from the NeoScan Player

Bruno plays the brawler on his tablet and says what is wrong. Each note arrives with an exact replay of the last
minute. Built 2026-10-06, Player 0.0.13.

## In the player (android/)

- **The mic button** sits next to the soft reset. Hold it and talk.
  - At the press, the emulation thread writes the replay data between two frames (`Native.feedback`, player.c).
  - While the button is held, the voice records (AAC, 16 kHz mono, 32 kbps, `audio.m4a`).
- **Release:** the game pauses. The voice goes to the server, which transcribes it at once (about 2 s).
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

No login is needed, like the ROM download. The public calls are size capped and rate limited by nginx.

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
  - `POST /brawler/feedback/upload` and `POST /brawler/feedback/transcribe` are public.
  - `/brawler-lab/feedback-api/` maps to `/api/`, behind the Oros login (`auth_request /jlpt-auth`). The Lab's tab
    uses it.
- **Tracker tables:**
  - `feedback`: id, created, apk_version, game_version, rom_sha, device, raw_transcript, final_text, audio_path,
    bundle_path, status, release, notes, updated, category, fighters, duplicate_of.
  - `status_history`: feedback_id, at, from_status, to_status, by, note.
- **Statuses:** new → read (pulled) → in_progress → shipped (with a release, e.g. 0.0.71), wont_do, or duplicate (of
  another id).
- **Categories:** sound, graphics, gameplay, integration, scripting, other. They are set at triage; nothing is picked
  in the player.

## On the desktop

- **`tools/feedback/pull.py`:**
  - Fetches the bundles into `/data/feedback/<id>/` and the DB backups into `/data/feedback/_server/backups/`.
  - Marks the new rows read.
  - Replays each new bundle and writes `report.md`, then prints one line per bundle.
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
  - `fb.py show ID`
  - `fb.py status ID in_progress|wont_do [--note ...]`
  - `fb.py status ID shipped --release 0.0.71`
  - `fb.py status ID duplicate --of ID2`
  - `fb.py set ID --category gameplay --fighters geese,terry [--notes ...]`
- **The Brawler Lab's Feedback tab** (`tools/brawler/chainlab/feedback.js`) lists the feedback. Each row shows the
  date, versions, the note as sent with the raw transcript under it, and the status and release as text. A play
  button plays the voice, and the screenshot opens from the row.
  - It filters by status and category.
  - Category and fighters can be edited in the row.

## Determinism

- **The Geolith fix:** save states v3 (geolith commit fa094e0) add the 68K's pending reset cycles and the YM2610's
  pacing counters. These are the SSG resampler index and the FM prepare sweep counters.
  - Before v3, a state loaded into a freshly loaded core drifted by a few cycles within a frame. The picture stayed
    the same, but the bytes did not.
  - v2 states still load.
- **Proven:** byte-identical replays from an x86_64 Android emulator to the x86_64 desktop.
- **Not yet proven:** an arm64 device (the tablet) replaying on the x86_64 desktop. The first real bundle will tell,
  in its report's Determinism line.
