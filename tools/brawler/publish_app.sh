#!/bin/sh
# Publish the Brawler app (android flavor "brawler", the testers' app; docs/feedback.md "Roles and the two apps") for its
# update notice: the APK goes to /data/brawler/feedback/share/app/brawler-<versionName>-<versionCode>.apk on the VPS (the
# last 3 kept). The feedback service's GET me offers the newest one to every signed-in tester / admin whose app has a
# lower versionCode, as a download link with a 24 h ticket that the phone's browser opens. Never public otherwise.
#   cd android && ./gradlew assembleBrawlerRelease && cd .. && tools/brawler/publish_app.sh android/app/build/outputs/apk/brawler/release/app-brawler-release.apk
# (Brawler Dev, flavor dev, is still published by publish_vps.sh --apk-only <app-dev-debug.apk> <version>.)
set -e
APK=$1
[ -f "$APK" ] || { echo "usage: $0 APP-BRAWLER-RELEASE.APK"; exit 1; }
HOST=root@195.201.91.211; DIR=/data/brawler/feedback/share/app
AAPT=$(ls -d "${ANDROID_HOME:-$HOME/Android/Sdk}"/build-tools/*/aapt2 | tail -1)
B=$("$AAPT" dump badging "$APK" | sed -n 1p)
PKG=$(echo "$B" | sed -n "s/^package: name='\([^']*\)'.*/\1/p")
CODE=$(echo "$B" | sed -n "s/.*versionCode='\([0-9]*\)'.*/\1/p")
NAME=$(echo "$B" | sed -n "s/.* versionName='\([^']*\)'.*/\1/p")
[ "$PKG" = com.neoscan.brawler ] || { echo "$APK is $PKG, not the Brawler app (com.neoscan.brawler)"; exit 1; }
F=brawler-$NAME-$CODE.apk
ssh -o BatchMode=yes "$HOST" "mkdir -p $DIR"
rsync -q "$APK" "$HOST:$DIR/$F.part"
ssh -o BatchMode=yes "$HOST" "set -e; cd $DIR; mv $F.part $F; chmod 644 $F; ls -t brawler-*.apk | tail -n +4 | xargs -r rm -f; ls -la $DIR"
echo "published $F: offered by /brawler/feedback/me to every Brawler app below code $CODE"
# the web download page canneji /brawler/get/ (nginx: tools/feedback/deploy_vps.sh, testers + admins behind the Oros
# sign-in; also served alone at brawler27.duckdns.org, tools/feedback/nginx_brawler27.conf): the newest APK as
# brawler-<version>.apk, its page and its own sign-in page (tools/brawler/getpage/)
G=/data/brawler/get
HERE=$(cd "$(dirname "$0")" && pwd)
MB=$(awk "BEGIN{printf \"%.1f\", $(stat -c %s "$APK")/1048576}")
sed -e "s/@NAME@/$NAME/g" -e "s/@SIZE@/$MB/g" "$HERE/getpage/index.html" > /tmp/brawler_get_index.$$.html
rsync -q "$HERE/getpage/login.html" "$HOST:$G/login.html"
rsync -q /tmp/brawler_get_index.$$.html "$HOST:$G/index.html"; rm -f /tmp/brawler_get_index.$$.html
ssh -o BatchMode=yes "$HOST" "set -e; mkdir -p $G; rm -f $G/brawler-*.apk; cp $DIR/$F $G/brawler-$NAME.apk; chmod 644 $G/*"
echo "web page: https://brawler27.duckdns.org/ (brawler-$NAME.apk)"
