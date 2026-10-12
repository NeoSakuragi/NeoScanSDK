#!/bin/bash
# The Brawler Factory -> canneji.duckdns.org/brawler-factory/ (behind the Oros login, as /brawler-lab/: auth_request
# /jlpt-auth, 401 -> its login.html, a copy of the Lab's). Files on the box: /data/brawler-factory/ (index.html,
# factory.css, factory.js). Everything else the page uses is the Lab's (its <base> is /brawler-lab/): this also sends the
# Lab's arbitrage.js (the Assembly sheet the Factory embeds). The nginx block (between the "brawler-factory" markers in
# sites-enabled/kanji, after the /brawler-lab/ block) is written once, checked with nginx -t, else removed again.
#   tools/brawler/factory/deploy.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
HOST=root@195.201.91.211
ssh -o BatchMode=yes $HOST 'mkdir -p /data/brawler-factory && cp /data/brawler-lab/login.html /data/brawler-factory/login.html'
rsync -a "$HERE/index.html" "$HERE/factory.css" "$HERE/factory.js" $HOST:/data/brawler-factory/
rsync -a "$HERE/../chainlab/arbitrage.js" $HOST:/data/brawler-lab/
ssh -o BatchMode=yes $HOST 'set -e; F=/etc/nginx/sites-enabled/kanji
grep -q ">>> brawler-factory" $F && exit 0
cp $F /root/kanji.bak-factory
python3 - "$F" <<"PY"
import sys
p = sys.argv[1]; s = open(p).read()
anchor = "    location @brawlerlab_login {\n        return 302 /brawler-lab/login.html;\n    }\n"
assert anchor in s, "the /brawler-lab/ login block was not found"
block = """    # >>> brawler-factory (NeoScanSDK tools/brawler/factory/deploy.sh): behind the Oros login like /brawler-lab/
    location = /brawler-factory { return 301 /brawler-factory/; }
    location = /brawler-factory/login.html { alias /data/brawler-factory/login.html; add_header Cache-Control "no-cache" always; }
    location ^~ /brawler-factory/ {
        auth_request /jlpt-auth;
        error_page 401 = @brawlerfactory_login;
        alias /data/brawler-factory/;
        add_header Cache-Control "no-cache" always;
    }
    location @brawlerfactory_login { return 302 /brawler-factory/login.html; }
    # <<< brawler-factory
"""
open(p, "w").write(s.replace(anchor, anchor + block, 1))
PY
nginx -t 2>/dev/null || { cp /root/kanji.bak-factory $F; echo "nginx -t failed: block removed"; exit 1; }
systemctl reload nginx'
echo "deployed: https://canneji.duckdns.org/brawler-factory/ (Oros login)"
