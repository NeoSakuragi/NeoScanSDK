#!/bin/sh
# Deploy the replay analysis worker (analysis/worker.py: token-free session statistics) to the VPS: unit
# brawler-analysis (Nice 19, idle IO, batch scheduling, CPUQuota 50 %, MemoryMax 700M: the VPS also serves Oros /
# ChessPuzzle), code in /data/brawler/analysis/app (harness.py + analysis/), our Geolith core built headless
# (headless_core.sh: the desktop replays' tree + no scanline drawing; generic x86-64, glibc <= 2.38) in core/, the Player's BIOS in bios/; data:
# stats.db, results/, aggregates.json, builds/<VERSION>/pack.json (publish_vps.sh, backfill_packs.sh) under
# /data/brawler/analysis, the unpacked ROMs on the storage box (/mnt/storagebox/brawler-analysis/roms). The admin
# page reads it through the feedback service (server.py api/stats/..., tools/feedback/deploy_vps.sh).
#   tools/brawler/analysis/deploy_vps.sh
set -e
HOST=root@195.201.91.211; A=/data/brawler/analysis
cd "$(dirname "$0")/.."
sh analysis/headless_core.sh
CORE=${HEADLESS_BUILD:-/data/tmp/geolith_headless}/libretro/geolith_libretro.so
ssh -o BatchMode=yes $HOST "mkdir -p $A/app/analysis $A/core $A/bios $A/builds $A/results $A/rerun $A/work /mnt/storagebox/brawler-analysis/roms"
rsync -q harness.py $HOST:$A/app/
rsync -q analysis/analyze.py analysis/worker.py $HOST:$A/app/analysis/
rsync -q $CORE $HOST:$A/core/geolith_libretro.so
[ ! -f /data/tmp/chainlab/site/neogeo.zip ] || rsync -q /data/tmp/chainlab/site/neogeo.zip $HOST:$A/bios/
ssh -o BatchMode=yes $HOST 'set -e
cat > /etc/systemd/system/brawler-analysis.service <<UNIT
[Unit]
Description=Brawler replay analysis (token-free session statistics; NeoScanSDK tools/brawler/analysis)
After=network.target brawler-feedback.service
RequiresMountsFor=/mnt/storagebox

[Service]
Environment=ANALYSIS=/data/brawler/analysis
Environment=BRAWLER_CORE=/data/brawler/analysis/core/geolith_libretro.so
Environment=HARNESS_WORK=/data/brawler/analysis/work
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /data/brawler/analysis/app/analysis/worker.py
Nice=19
IOSchedulingClass=idle
CPUSchedulingPolicy=batch
CPUQuota=50%
MemoryMax=700M
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload; systemctl enable -q brawler-analysis; systemctl restart brawler-analysis
sleep 2; systemctl is-active brawler-analysis; journalctl -u brawler-analysis -n 5 --no-pager'
