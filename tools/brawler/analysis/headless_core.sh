#!/bin/sh
# The replay worker's HEADLESS core: our Geolith tree (NeoGeo/geolith, never edited here) copied to $HEADLESS_BUILD
# (/data/tmp/geolith_headless), headless_core.patch applied, built -> $HEADLESS_BUILD/libretro/geolith_libretro.so
# (deploy_vps.sh ships it to the VPS). The patch adds retro_neoscan_skip_render(1): the LSPC draws no scanline (no
# picture; nothing either CPU reads comes from the line buffers, so the machine and its save states are the same:
# Asenka's 0.10.150 session, 356 / 356 chunk-boundary SHA-256 identical to the phone's) — 40 % less time per frame.
# analyze.py calls it when the core has it; every other core (the stock one on the desktop) draws as before.
# Usage: sh tools/brawler/analysis/headless_core.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(readlink -f "${GEOLITH:-$HERE/../../../geolith}")
DST=${HEADLESS_BUILD:-/data/tmp/geolith_headless}
rm -rf "$DST"; mkdir -p "$DST"
(cd "$SRC" && tar --exclude=.git --exclude='*.o' --exclude='*.so' --exclude='*.d' -cf - .) | (cd "$DST" && tar xf -)
patch -s -d "$DST" -p1 < "$HERE/headless_core.patch"
make -s -C "$DST/libretro" -j"$(nproc)" >/dev/null 2>&1
echo "headless core: $DST/libretro/geolith_libretro.so"
