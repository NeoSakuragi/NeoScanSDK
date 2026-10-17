# Brawler admin

`index.html` = https://canneji.duckdns.org/brawler-admin/ : one page with every Brawler admin tool as tabs
(Players, Live wall, Sessions, Stats, Tickets, Throws, Factory, Lab, Decisions), each tab the existing page in a frame.
Behind the Oros login + the `brawler_admin` tag (nginx `auth_request /brawler-admin-auth`, block
`# >>> brawler-admin` in sites-enabled/kanji; login page = the Factory's copy). Deploy:
`scp index.html stats.html root@195.201.91.211:/data/brawler-admin/`.

Stats (`stats.html`, 2026-10-17): the token-free replay statistics. The VPS unit `brawler-analysis`
(tools/brawler/analysis/worker.py, deployed by tools/brawler/analysis/deploy_vps.sh) replays every finished session in our
Geolith core with its build's analysis pack and measures it (analyze.py); the page reads feedback-api/stats... (server.py
stats_api, admins only): Sessions (one row each, tap = summary + wave timeline, tap a wave = its numbers; Re-run analysis),
Players and Builds (aggregates: median wave times, death hotspots, moves used / never used, where sessions end). The badge
on a session = the feedback notes recorded during it (chainlab/sessnotes.js, also on the Live wall and the Sessions list).
