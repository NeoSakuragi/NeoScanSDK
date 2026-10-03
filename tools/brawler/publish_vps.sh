#!/bin/sh
# Publish a brawler build for the Android player's auto-fetch: canneji.duckdns.org/brawler/download/ =
# /data/brawler/builds/ on the VPS (nginx, shared secret, log /var/log/nginx/brawler.log; set up 2026-10-03, see
# examples/brawler/README.md). Uploads brawler-<VERSION>.neo, writes latest.json, points brawler.neo at it, keeps the
# last 3 builds; with an APK argument also publishes neoscan-player-<version>.apk (+ neoscan-player.apk link).
#   tools/brawler/publish_vps.sh examples/brawler/brawler.neo 0.0.1 [android/app/build/outputs/apk/debug/app-debug.apk 0.0.1]
set -e
ROM=$1; VER=$2; APK=$3; APKVER=$4
HOST=root@195.201.91.211; DIR=/data/brawler/builds
[ -f "$ROM" ] && [ -n "$VER" ] || { echo "usage: $0 ROM VERSION [APK APKVERSION]"; exit 1; }
SIZE=$(stat -c %s "$ROM"); SHA=$(sha256sum "$ROM" | cut -d' ' -f1); BUILD=$(date +%s)
rsync -q "$ROM" "$HOST:$DIR/brawler-$VER.neo.part"
ssh -o BatchMode=yes "$HOST" "set -e; cd $DIR; mv brawler-$VER.neo.part brawler-$VER.neo; ln -sfn brawler-$VER.neo brawler.neo
  printf '{\"version\": \"%s\", \"build\": %s, \"file\": \"brawler-%s.neo\", \"size\": %s, \"sha256\": \"%s\"}\n' $VER $BUILD $VER $SIZE $SHA > latest.json.part
  mv latest.json.part latest.json
  ls -t brawler-*.neo | tail -n +4 | xargs -r rm -f
  chmod 644 brawler-*.neo latest.json
  mkdir -p /var/www/kanji/brawler
  printf '{\"version\": \"%s\", \"date\": \"%s\", \"size\": %s}\n' $VER \$(date -u +%Y-%m-%d) $SIZE > /var/www/kanji/brawler/info.json"
if [ -n "$APK" ]; then
  rsync -q "$APK" "$HOST:$DIR/neoscan-player-$APKVER.apk"
  ssh -o BatchMode=yes "$HOST" "cd $DIR; ln -sfn neoscan-player-$APKVER.apk neoscan-player.apk; chmod 644 neoscan-player-*.apk; ls -t neoscan-player-*.apk | tail -n +4 | xargs -r rm -f"
fi
ssh -o BatchMode=yes "$HOST" "cat $DIR/latest.json; ls -la $DIR"
