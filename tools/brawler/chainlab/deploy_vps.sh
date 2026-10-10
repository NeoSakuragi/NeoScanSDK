#!/bin/bash
# Chain Lab -> canneji.duckdns.org/brawler-lab/ (behind the Oros login: nginx auth_request /jlpt-auth, as /chesspuzzle/;
# the page serves SNK's BIOS and the ROM, it must never be public). Files on the box: /data/brawler-lab/.
#   tools/brawler/chainlab/deploy_vps.sh [GAME_DIR]     (GAME_DIR: examples/brawler, built; default the repo's)
#   env SITE=DIR: build the site there (default /data/tmp/chainlab/site); LAB_PUBLISH=0: never run the Character Lab's
#   publish (labpub.py all --if-changed: the shell + packs, only when the pack format or a fighter's data changed)
# Builds the site (make_site.py; the wasm core with build_wasm.sh when web/core.wasm is missing), gzips the big files
# (nginx gzip_static), rsyncs. The nginx block (in /etc/nginx/sites-enabled/kanji, after /chesspuzzle/) is set up once.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
GAME=${1:-$HERE/../../../examples/brawler}
SITE=${SITE:-/data/tmp/chainlab/site}           # (SITE=...: another site dir, e.g. a worktree building its own)
HOST=root@195.201.91.211
mkdir -p "$SITE"
# the wasm core is the desktop's Geolith source tree (P2 bank latch, save states): rebuilt when web_core.c or any of it is newer
GEO=${GEOLITH:-$HOME/CLProjects/geolith}
[ -f "$SITE/core.wasm" ] && [ "$SITE/core.wasm" -nt "$HERE/web_core.c" ] && [ -z "$(find "$GEO/src" "$GEO/libretro" -name '*.[ch]' -newer "$SITE/core.wasm" | head -1)" ] \
  || "$HERE/build_wasm.sh" "$SITE"
# the Character Lab's shell + packs ("Try in game" and the Player play them from the catalogue): published by the one
# command, which does nothing unless the pack format or a fighter's data changed (an engine change alone: nothing)
if [ "${LAB_PUBLISH:-1}" = 1 ]; then python3 "$HERE/../labpub.py" all --if-changed || { echo "labpub.py all failed"; exit 1; }; fi
python3 "$HERE/make_site.py" "$SITE" "$GAME"
for f in game.neo core.wasm core.js chainlab.json enemies.json chars.json select.json cast.json; do gzip -9 -k -f "$SITE/$f"; done
ssh $HOST 'mkdir -p /data/brawler-lab && test -f /data/brawler-lab/login.html || cp /var/www/kanji/jlpt/login.html /data/brawler-lab/login.html'
rsync -a --exclude login.html "$SITE/" $HOST:/data/brawler-lab/
echo "deployed: https://canneji.duckdns.org/brawler-lab/ (Oros login)"
