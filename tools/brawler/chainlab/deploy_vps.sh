#!/bin/bash
# Chain Lab -> canneji.duckdns.org/brawler-lab/ (behind the Oros login: nginx auth_request /jlpt-auth, as /chesspuzzle/;
# the page serves SNK's BIOS and the ROM, it must never be public). Files on the box: /data/brawler-lab/.
#   tools/brawler/chainlab/deploy_vps.sh [GAME_DIR]     (GAME_DIR: examples/brawler, built; default the repo's)
# Builds the site (make_site.py; the wasm core with build_wasm.sh when web/core.wasm is missing), gzips the big files
# (nginx gzip_static), rsyncs. The nginx block (in /etc/nginx/sites-enabled/kanji, after /chesspuzzle/) is set up once.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
GAME=${1:-$HERE/../../../examples/brawler}
SITE=/data/tmp/chainlab/site
HOST=root@195.201.91.211
mkdir -p "$SITE"
# the wasm core is the desktop's Geolith source tree (P2 bank latch, save states): rebuilt when web_core.c or any of it is newer
GEO=${GEOLITH:-$HOME/CLProjects/geolith}
[ -f "$SITE/core.wasm" ] && [ "$SITE/core.wasm" -nt "$HERE/web_core.c" ] && [ -z "$(find "$GEO/src" "$GEO/libretro" -name '*.[ch]' -newer "$SITE/core.wasm" | head -1)" ] \
  || "$HERE/build_wasm.sh" "$SITE"
python3 "$HERE/make_site.py" "$SITE" "$GAME"
for f in game.neo core.wasm core.js chainlab.json enemies.json chars.json select.json; do gzip -9 -k -f "$SITE/$f"; done
for f in "$SITE"/rom/*.neo "$SITE"/rom/*.json; do [ -f "$f" ] && gzip -9 -k -f "$f"; done   # the Lab builds ("Try in game", tryit_site.py)
ssh $HOST 'mkdir -p /data/brawler-lab && test -f /data/brawler-lab/login.html || cp /var/www/kanji/jlpt/login.html /data/brawler-lab/login.html'
rsync -a --exclude login.html "$SITE/" $HOST:/data/brawler-lab/
echo "deployed: https://canneji.duckdns.org/brawler-lab/ (Oros login)"
