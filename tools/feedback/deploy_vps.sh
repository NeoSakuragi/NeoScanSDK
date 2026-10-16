#!/bin/sh
# Deploy the voice-feedback service (tools/feedback/server.py, docs/feedback.md) to the VPS: unit brawler-feedback
# (127.0.0.1:8920, nice'd, idle IO), data + tracker DB in /data/brawler/feedback. nginx (the block between the
# "brawler-feedback" markers in sites-enabled/kanji, rewritten on each deploy, checked with nginx -t, else restored):
#   POST /brawler/feedback/upload, /brawler/feedback/transcribe    the player, size + rate capped; the service itself
#                                                                   requires the Oros token (players < 0.0.15: allowed while
#                                                                   /data/brawler/feedback/legacy_open exists, user "legacy")
#   POST /brawler/feedback/reply                                   a reply / thumbs up / down to one of the user's notes
#                                                                   (Player 0.0.17; token only, no legacy), size + rate capped
#   POST /brawler/feedback/test                                    a test attempt of a note (Player 0.0.22: test.json + the
#                                                                   attempt's replay), token only, size + rate capped
#   POST /brawler/feedback/review                                  (Player 0.0.24) his answer to a decision (token only), size + rate capped
#   GET  /brawler/feedback/mine[/file/<id>/<name>]                  the player's list of the user's notes (the Oros token,
#                                                                   checked by the service: a brawler admin or tester);
#        /brawler/feedback/mine/scenario/<id>/<sha>/<key>.state     a note's test state for a build (Player 0.0.22)
#   GET  /brawler/feedback/me, share/latest.json | build/brawler-<V>.neo   the Brawler app (docs/feedback.md "Roles and
#                               the two apps"): the account's role + its allowed build (the service checks the token)
#   GET|PUT|DELETE /brawler/feedback/saves/<game>                  (Player 0.0.39) the account's cloud save of a game
#   POST /brawler/feedback/sessions/chunk                          (Player 0.0.41) a 5 s chunk of the play session (token, role),
#                                                                   files on the storage box /mnt/storagebox/brawler-sessions/
#   GET  /brawler/feedback/app/brawler-<name>-<code>.apk?t=<ticket>    the Brawler APK for the phone's browser (ticket from me)
# ROLES: the Oros tags (oros-server user-tags). /brawler-admin-auth = Oros's /api/authcheck?tag=brawler_admin (403 for
# any other account) gates the admin pages: /brawler-lab/ (Chain Lab, Fighter Lab), /brawler-factory/ (never /decisions/: the SoccerFury page, plain Oros login),
# /brawler-lab/feedback-api/, /brawler/lab/ (+ dl/), and /brawler/download/ goes through the service's /dlauth (admins).
#   /brawler-lab/feedback-api/  -> /api/                            behind the Oros login (the Brawler Lab's Feedback tab)
#   /brawler/lab/               -> /lab/                            the Character Lab for the player (Oros token, X-Public):
#                                                                   live configs, ship queue, catalogue (docs/feedback.md)
#   /brawler/lab/dl/shell|packs|faces/                              the Lab's shell / packs / faces (/data/brawler/lab/...),
#                                                                   static with Range, behind the Oros login (token or cookie)
#   /brawler/download/          the dev builds (ROM, latest.json, the Brawler Dev APK neoscan-player.apk): brawler admins
#                               only (auth_request to the service's /dlauth: the token or cookie, or a player < 0.0.15
#                               while legacy_open exists). Nothing under /brawler/download/ is public any more.
# (auth_request /jlpt-auth = Oros's /api/authcheck: a Bearer token or the oros_token cookie; 401 otherwise)
set -e
HOST=root@195.201.91.211; APP=/data/brawler/feedback/app
cd "$(dirname "$0")"
ssh -o BatchMode=yes "$HOST" "mkdir -p $APP /data/brawler/feedback/share/app /data/brawler/feedback/bundles /data/brawler/lab/shell /data/brawler/lab/packs /data/brawler/lab/faces /data/brawler/lab/config /data/brawler/lab/incoming"
rsync -q server.py prices.json "$HOST:$APP/"
ssh -o BatchMode=yes "$HOST" 'set -e
cat > /etc/systemd/system/brawler-feedback.service <<UNIT
[Unit]
Description=Brawler voice feedback + tracker (canneji.duckdns.org/brawler/feedback/, NeoScanSDK tools/feedback)
After=network.target oros.service

[Service]
Environment=FEEDBACK_DATA=/data/brawler/feedback
Environment=FEEDBACK_PORT=8920
ExecStart=/usr/bin/python3 /data/brawler/feedback/app/server.py
Nice=15
IOSchedulingClass=idle
MemoryMax=300M
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload; systemctl enable -q brawler-feedback; systemctl restart brawler-feedback
grep -q "zone=brawler_fb" /etc/nginx/brawler.conf || printf "%s\n" "# brawler voice feedback (tools/feedback): the public upload / transcribe calls, per address" "limit_req_zone \$binary_remote_addr zone=brawler_fb:1m rate=10r/m;" >> /etc/nginx/brawler.conf
grep -q "zone=brawler_sess" /etc/nginx/brawler.conf || printf "%s\n" "# brawler session recording (Player 0.0.41): a chunk every 5 s per player, bursts after an offline spell" "limit_req_zone \$binary_remote_addr zone=brawler_sess:1m rate=60r/m;" >> /etc/nginx/brawler.conf
S=/etc/nginx/sites-enabled/kanji
cp $S /root/kanji.nginx.bak-feedback
python3 - $S <<PY
import re, sys; p = sys.argv[1]; s = open(p).read()
s = re.sub(r"    # >>> brawler-feedback.*?# <<< brawler-feedback\n", "", s, flags=re.S)
s = re.sub(r"    # Brawler voice feedback \(NeoScanSDK tools/feedback.*?\n    }\n", "", s, flags=re.S)   # the first version
s = re.sub(r"    # Brawler POC \(examples/brawler in NeoScanSDK\): info page.*?\n    location = /brawler \{ return 301 /brawler/; \}\n", "", s, flags=re.S)
s = re.sub(r"    location \^~ /brawler/download/ \{.*?\n    }\n", "", s, count=1, flags=re.S)   # the public builds (before 0.0.15)
pub = lambda path: """        limit_except POST { deny all; }
        limit_req zone=brawler_fb burst=10 nodelay;
        proxy_pass http://127.0.0.1:8920/%s;
        proxy_set_header X-Public 1;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 150s;
        access_log /var/log/nginx/brawler.log brawler;""" % path
block = """    # >>> brawler-feedback (NeoScanSDK tools/feedback/deploy_vps.sh, docs/feedback.md; rewritten on deploy)
    location = /brawler/feedback/upload {
        client_max_body_size 32M;
%s
    }
    location = /brawler/feedback/transcribe {
        client_max_body_size 8M;
%s
    }
    location = /brawler/feedback/reply {
        client_max_body_size 12M;
%s
    }
    location = /brawler/feedback/test {
        client_max_body_size 32M;
%s
    }
    location = /brawler/feedback/review {
        client_max_body_size 12M;
%s
    }
    # session recording, Player 0.0.41: one 5 s chunk of the play session per call (the service checks the token
    # and the role; files on the storage box)
    location = /brawler/feedback/sessions/chunk {
        limit_except POST { deny all; }
        limit_req zone=brawler_sess burst=120 nodelay;
        client_max_body_size 1m;
        proxy_pass http://127.0.0.1:8920/sessions/chunk;
        proxy_set_header X-Public 1;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }
    location ^~ /brawler/feedback/mine {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8920/mine;
        proxy_set_header X-Public 1;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }
    # the Brawler app (docs/feedback.md "Roles and the two apps"): its role, its allowed build, its APK; the service
    # checks the token (the APK: the ticket GET me made)
    location = /brawler/feedback/me {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8920/me;
        proxy_set_header X-Public 1;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }
    # cloud saves, Player 0.0.39: GET, PUT, DELETE saves/GAME, the signed-in account own save only: the service
    # checks the token and the role
    location ^~ /brawler/feedback/saves/ {
        limit_except GET PUT DELETE { deny all; }
        client_max_body_size 2m;
        proxy_pass http://127.0.0.1:8920/saves/;
        proxy_set_header X-Public 1;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }
    location ^~ /brawler/feedback/app/ {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8920/app/;
        proxy_set_header X-Public 1;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 300s;
        access_log /var/log/nginx/brawler.log brawler;
    }
    location ^~ /brawler/feedback/share/ {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8920/share/;
        proxy_set_header X-Public 1;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        access_log /var/log/nginx/brawler.log brawler;
    }
    # Brawler POC (examples/brawler in NeoScanSDK): info page = static /var/www/kanji/brawler/ (CannejiSite);
    # builds = /data/brawler/builds/, every request logged with the device headers. Behind the Oros login since
    # Player 0.0.15 (the player sends its Bearer token); the APK alone stays public so a new user can install it.
    location = /brawler { return 301 /brawler/; }
    location = /brawler-admin-auth {
        internal;
        proxy_pass http://127.0.0.1:8900/api/authcheck?tag=brawler_admin;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
    }
    location = /brawler-player-auth {
        internal;
        proxy_pass http://127.0.0.1:8900/api/authcheck?tag=brawler_tester,brawler_admin;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
    }
    # the Brawler app for the web (Bruno 2026-10-15): /brawler/get/ = a download page + the tester APK
    # (/data/brawler/get, filled by tools/brawler/publish_app.sh), behind the Oros sign-in, testers and admins only
    location = /brawler/get { return 301 /brawler/get/; }
    location = /brawler/get/login.html { alias /data/brawler/get/login.html; add_header Cache-Control "no-cache" always; }
    location ^~ /brawler/get/ {
        auth_request /brawler-player-auth;
        error_page 401 = @brawlerget_login;
        alias /data/brawler/get/;
        add_header Cache-Control "no-cache" always;
        types { text/html html; application/vnd.android.package-archive apk; }
    }
    location @brawlerget_login { return 302 /brawler/get/login.html; }
    location = /brawler-dl-auth {
        internal;
        proxy_pass http://127.0.0.1:8920/dlauth;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
    }
    location ^~ /brawler/download/ {
        auth_request /brawler-dl-auth;
        alias /data/brawler/builds/;
        access_log /var/log/nginx/brawler.log brawler;
        add_header Cache-Control "no-store";
        types { application/vnd.android.package-archive apk; application/json json; }
    }
    location ^~ /brawler-lab/feedback-api/ {
        auth_request /brawler-admin-auth;
        proxy_pass http://127.0.0.1:8920/api/;
        client_max_body_size 8m;
        proxy_read_timeout 130s;
    }
    # Character Lab (docs/feedback.md "Character Lab"): the API for the player, then the files (nginx serves Range)
    location ^~ /brawler/lab/ {
        limit_except GET PUT POST { deny all; }
        auth_request /brawler-admin-auth;
        proxy_pass http://127.0.0.1:8920/lab/;
        proxy_set_header X-Public 1;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        client_max_body_size 4m;
        proxy_read_timeout 30s;
    }
    location ^~ /brawler/lab/dl/shell/ { auth_request /brawler-admin-auth; alias /data/brawler/lab/shell/; add_header Cache-Control "private, no-cache"; }
    location ^~ /brawler/lab/dl/packs/ { auth_request /brawler-admin-auth; alias /data/brawler/lab/packs/; add_header Cache-Control "private, no-cache"; }
    location ^~ /brawler/lab/dl/faces/ { auth_request /brawler-admin-auth; alias /data/brawler/lab/faces/; add_header Cache-Control "private, no-cache"; }
    # <<< brawler-feedback
""" % (pub("upload"), pub("transcribe"), pub("reply"), pub("test"), pub("review"))
i = s.index("    location / {")
s = s[:i] + block + s[i:]
# the admin pages written by other scripts (Chain Lab / Fighter Lab, the Factory, the decisions page): brawler admins only
for loc in ("/brawler-lab/", "/brawler-factory/"):
    k = s.index("    location ^~ %s {" % loc); e = s.index("\n    }\n", k)
    s = s[:k] + s[k:e].replace("auth_request /jlpt-auth;", "auth_request /brawler-admin-auth;") + s[e:]
open(p, "w").write(s)
PY
if nginx -t 2>/dev/null; then systemctl reload nginx; else cp /root/kanji.nginx.bak-feedback $S; nginx -t; echo "nginx -t failed: restored"; exit 1; fi
sleep 1; systemctl is-active brawler-feedback
echo "signed out (expect 401 / 302 / 404 for every one):"
for u in brawler/feedback/upload brawler/feedback/transcribe brawler/feedback/reply brawler/feedback/test brawler/feedback/review brawler/feedback/sessions/chunk; do curl -s -X POST -o /dev/null -w "POST $u: %{http_code}\n" https://canneji.duckdns.org/$u; done
for u in brawler-lab/feedback-api/sessions brawler/feedback/me brawler/feedback/saves/brawler brawler/feedback/share/latest.json brawler/feedback/app/brawler-0.1.0-1.apk brawler/feedback/mine brawler/download/latest.json brawler/download/brawler.neo brawler-lab/feedback-api/list brawler/lab/catalogue brawler/lab/dl/packs/x brawler/download/neoscan-player.apk brawler-lab/ brawler-factory/; do curl -s -o /dev/null -w "GET $u: %{http_code}\n" https://canneji.duckdns.org/$u; done'
