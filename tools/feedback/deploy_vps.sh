#!/bin/sh
# Deploy the voice-feedback service (tools/feedback/server.py, docs/feedback.md) to the VPS: unit brawler-feedback
# (127.0.0.1:8920, nice'd, idle IO), data + tracker DB in /data/brawler/feedback. nginx (the block between the
# "brawler-feedback" markers in sites-enabled/kanji, rewritten on each deploy, checked with nginx -t, else restored):
#   POST /brawler/feedback/upload, /brawler/feedback/transcribe    public (the player), size + rate capped
#   /brawler-lab/feedback-api/  -> /api/                            behind the Oros login (the Brawler Lab's Feedback tab)
set -e
HOST=root@195.201.91.211; APP=/data/brawler/feedback/app
cd "$(dirname "$0")"
ssh -o BatchMode=yes "$HOST" "mkdir -p $APP /data/brawler/feedback/bundles"
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
S=/etc/nginx/sites-enabled/kanji
cp $S /root/kanji.nginx.bak-feedback
python3 - $S <<PY
import re, sys; p = sys.argv[1]; s = open(p).read()
s = re.sub(r"    # >>> brawler-feedback.*?# <<< brawler-feedback\n", "", s, flags=re.S)
s = re.sub(r"    # Brawler voice feedback \(NeoScanSDK tools/feedback.*?\n    }\n", "", s, flags=re.S)   # the first version
pub = lambda path: """        limit_except POST { deny all; }
        limit_req zone=brawler_fb burst=10 nodelay;
        proxy_pass http://127.0.0.1:8920/%s;
        proxy_set_header X-Public 1;
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
    location ^~ /brawler-lab/feedback-api/ {
        auth_request /jlpt-auth;
        proxy_pass http://127.0.0.1:8920/api/;
        proxy_read_timeout 30s;
    }
    # <<< brawler-feedback
""" % (pub("upload"), pub("transcribe"))
i = s.index("    location / {")
open(p, "w").write(s[:i] + block + s[i:])
PY
if nginx -t 2>/dev/null; then systemctl reload nginx; else cp /root/kanji.nginx.bak-feedback $S; nginx -t; echo "nginx -t failed: restored"; exit 1; fi
sleep 1; systemctl is-active brawler-feedback
for u in brawler/feedback/upload brawler/feedback/transcribe brawler-lab/feedback-api/list; do curl -s -X POST -o /dev/null -w "$u: %{http_code}\n" https://canneji.duckdns.org/$u; done'
