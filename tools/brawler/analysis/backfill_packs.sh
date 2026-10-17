#!/bin/sh
# Analysis packs (pack.py) for the builds stored sessions were played on that were published before packs existed:
# each version's commit ("Brawler <VERSION>:" in git log) rebuilt in /data/tmp/bpack/<VERSION>/src (git archive + the
# tools/neosdk and geolith links; never on the root drive), its ROM checked byte for byte against the sessions' build
# (rom_sha in the VPS session index), the pack written and sent to /data/brawler/analysis/builds/<VERSION>/, the tree
# removed. A version whose rebuild differs from the played ROM is skipped (reported), never packed.
#   tools/brawler/analysis/backfill_packs.sh [VERSION ...]     (default: every session build without a pack on the VPS)
set -u
HOST=root@195.201.91.211; REPO=$(cd "$(dirname "$0")/../../.." && pwd); WORK=/data/tmp/bpack
MAIN=/home/bruno/CLProjects/NeoGeo
mkdir -p $WORK/packs
ssh -o BatchMode=yes $HOST "sqlite3 /data/brawler/feedback/feedback.db 'SELECT DISTINCT rom_version, rom_sha FROM sessions'" > $WORK/shas.txt
if [ $# -eq 0 ]; then
  HAVE=$(ssh -o BatchMode=yes $HOST "ls /data/brawler/analysis/builds 2>/dev/null")
  set -- $(cut -d'|' -f1 $WORK/shas.txt | sort -uV | while read v; do echo "$HAVE" | grep -qx "$v" || echo $v; done)
fi
for V in "$@"; do
  WANT=$(grep "^$V|" $WORK/shas.txt | head -1 | cut -d'|' -f2)
  C=$(git -C "$REPO" log --all --format='%h %s' | grep -m1 " Brawler $V[: ]" | cut -d' ' -f1)
  [ -n "$C" ] || { echo "$V: SKIP no commit 'Brawler $V:' in git log"; continue; }
  D=$WORK/$V; S=$D/src
  if [ ! -f "$S/examples/brawler/brawler.neo" ]; then
    rm -rf "$S"; mkdir -p "$S"
    git -C "$REPO" archive "$C" | tar -x -C "$S"
    rm -rf "$S/tools/neosdk" "$S/geolith"; ln -s $MAIN/tools/neosdk "$S/tools/neosdk"; ln -s /home/bruno/CLProjects/geolith "$S/geolith"
    make -C "$S/sdk" -j8 > $D/sdk.log 2>&1 || { echo "$V: SKIP sdk build failed ($D/sdk.log)"; continue; }
    make -C "$S/examples/brawler" -j8 > $D/build.log 2>&1 || { echo "$V: SKIP build failed ($D/build.log)"; continue; }
  fi
  GOT=$(sha256sum "$S/examples/brawler/brawler.neo" | cut -d' ' -f1)
  if [ -n "$WANT" ] && [ "$GOT" != "$WANT" ]; then echo "$V: SKIP rebuild $GOT is not the played ROM $WANT"; continue; fi
  python3 "$REPO/tools/brawler/analysis/pack.py" $WORK/packs "$S/examples/brawler" --commit "$C" > $D/pack.log 2>&1 || { echo "$V: SKIP pack failed ($D/pack.log)"; continue; }
  ssh -o BatchMode=yes $HOST "mkdir -p /data/brawler/analysis/builds/$V" && rsync -q --chmod=F644 $WORK/packs/$V/pack.json "$HOST:/data/brawler/analysis/builds/$V/pack.json.part" \
    && ssh -o BatchMode=yes $HOST "mv /data/brawler/analysis/builds/$V/pack.json.part /data/brawler/analysis/builds/$V/pack.json" \
    && { echo "$V: OK $C ${GOT%${GOT#????????????}} pack sent"; rm -rf "$S"; }
done
