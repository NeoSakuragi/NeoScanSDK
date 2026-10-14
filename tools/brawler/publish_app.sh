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
