#!/bin/sh
# Publish a brawler build for the Android player's auto-fetch: canneji.duckdns.org/brawler/download/ =
# /data/brawler/builds/ on the VPS (nginx, shared secret, log /var/log/nginx/brawler.log; set up 2026-10-03, see
# examples/brawler/README.md). Uploads brawler-<VERSION>.neo, writes latest.json, points brawler.neo at it, keeps the
# last 3 builds (a build that has feedback is archived by the feedback service when the note arrives:
# /data/brawler/feedback/roms/<sha>.neo.gz, tools/feedback/server.py, so this pruning never loses one); with an APK argument also publishes neoscan-player-<version>.apk (+ neoscan-player.apk link).
#   tools/brawler/publish_vps.sh examples/brawler/brawler.neo 0.0.1 [android/app/build/outputs/apk/debug/app-debug.apk 0.0.1]
#   tools/brawler/publish_vps.sh --apk-only android/app/build/outputs/apk/debug/app-debug.apk 0.0.21     (no ROM touched)
#   tools/brawler/publish_vps.sh --channel test --apk-only <apk> 0.0.22                                   (test channel)
# The player's self-update (Player 0.0.21, android/.../PlayerUpdate.kt) reads player.json = {version, code, file, size,
# sha256} (the APK's versionCode from aapt2). The test channel writes player-test.json + neoscan-player-test-<ver>.apk
# instead and never moves the public neoscan-player.apk link: only a player switched to it
# (adb shell am start -n com.neoscan.player/.MainActivity --es channel test) follows it.
set -e
CHANNEL=live; APKONLY=
while [ $# -gt 0 ]; do case $1 in
  --channel) CHANNEL=$2; shift 2;;
  --apk-only) APKONLY=1; shift;;
  *) break;;
esac; done
if [ -n "$APKONLY" ]; then ROM=; VER=; APK=$1; APKVER=$2; else ROM=$1; VER=$2; APK=$3; APKVER=$4; fi
HOST=root@195.201.91.211; DIR=/data/brawler/builds
usage="usage: $0 [--channel live|test] ROM VERSION [APK APKVERSION] | $0 [--channel live|test] --apk-only APK APKVERSION"
[ "$CHANNEL" = live ] || [ "$CHANNEL" = test ] || { echo "$usage"; exit 1; }
if [ -n "$APKONLY" ]; then [ -f "$APK" ] && [ -n "$APKVER" ] || { echo "$usage"; exit 1; }
else [ -f "$ROM" ] && [ -n "$VER" ] || { echo "$usage"; exit 1; }; fi
[ "$CHANNEL" = live ] || [ -n "$APKONLY" ] || { echo "the test channel is for the APK only (--apk-only)"; exit 1; }
if [ -n "$ROM" ]; then
SIZE=$(stat -c %s "$ROM"); SHA=$(sha256sum "$ROM" | cut -d' ' -f1); BUILD=$(date +%s)
# the same ROM is already the latest: keep its build number (a new one made every player fetch it again)
if ssh -o BatchMode=yes "$HOST" "cat $DIR/latest.json" 2>/dev/null | grep -q "\"sha256\": \"$SHA\""; then
  echo "ROM unchanged (sha256 $SHA): not republished"
else
rsync -q "$ROM" "$HOST:$DIR/brawler-$VER.neo.part"
ssh -o BatchMode=yes "$HOST" "set -e; cd $DIR; mv brawler-$VER.neo.part brawler-$VER.neo; ln -sfn brawler-$VER.neo brawler.neo
  printf '{\"version\": \"%s\", \"build\": %s, \"file\": \"brawler-%s.neo\", \"size\": %s, \"sha256\": \"%s\"}\n' $VER $BUILD $VER $SIZE $SHA > latest.json.part
  mv latest.json.part latest.json
  ls -t brawler-*.neo | tail -n +4 | xargs -r rm -f
  chmod 644 brawler-*.neo latest.json
  mkdir -p /var/www/kanji/brawler
  printf '{\"version\": \"%s\", \"date\": \"%s\", \"size\": %s}\n' $VER \$(date -u +%Y-%m-%d) $SIZE > /var/www/kanji/brawler/info.json"
fi
fi
if [ -n "$APK" ]; then
  AAPT=$(ls -d "${ANDROID_HOME:-$HOME/Android/Sdk}"/build-tools/*/aapt2 | tail -1)
  CODE=$("$AAPT" dump badging "$APK" | sed -n "1s/.*versionCode='\([0-9]*\)'.*/\1/p")
  NAME=$("$AAPT" dump badging "$APK" | sed -n "1s/.*versionName='\([^']*\)'.*/\1/p")
  [ "$NAME" = "$APKVER" ] || { echo "the APK is $NAME (code $CODE), not $APKVER"; exit 1; }
  ASIZE=$(stat -c %s "$APK"); ASHA=$(sha256sum "$APK" | cut -d' ' -f1)
  if [ "$CHANNEL" = live ]; then F=neoscan-player-$APKVER.apk; J=player.json; else F=neoscan-player-test-$APKVER.apk; J=player-test.json; fi
  rsync -q "$APK" "$HOST:$DIR/$F.part"
  ssh -o BatchMode=yes "$HOST" "set -e; cd $DIR; mv $F.part $F; chmod 644 $F
    printf '{\"version\": \"%s\", \"code\": %s, \"file\": \"%s\", \"size\": %s, \"sha256\": \"%s\"}\n' $APKVER $CODE $F $ASIZE $ASHA > $J.part
    mv $J.part $J; chmod 644 $J
    if [ $CHANNEL = live ]; then ln -sfn $F neoscan-player.apk; ls -t neoscan-player-[0-9]*.apk | tail -n +4 | xargs -r rm -f
    else ls -t neoscan-player-test-*.apk | tail -n +3 | xargs -r rm -f; fi
    cat $J"
fi
ssh -o BatchMode=yes "$HOST" "cat $DIR/latest.json; ls -la $DIR"
