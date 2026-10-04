#!/bin/sh
# Publish the Song Lab site (every game built by build_web.py) to canneji.duckdns.org/neogeo-songlab/.
#   tools/songlab/publish_vps.sh [SITE_DIR]      default /data/neogeo_dict/sound/songlab/all
# The VPS serves /data/songlab through an nginx alias (sites-enabled/kanji, location /neogeo-songlab/); the hub card
# lives in Oros/CannejiSite. rsync --delete: the server mirrors the local site exactly.
set -e
SITE=${1:-/data/neogeo_dict/sound/songlab/all}
test -f "$SITE/song_lab.html" && test -f "$SITE/data/games.json" || { echo "$SITE: not a Song Lab site" >&2; exit 1; }
rsync -a --delete "$SITE/" root@195.201.91.211:/data/songlab/
curl -sf -o /dev/null https://canneji.duckdns.org/neogeo-songlab/data/games.json && echo "https://canneji.duckdns.org/neogeo-songlab/"
