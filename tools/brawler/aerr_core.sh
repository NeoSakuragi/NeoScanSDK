#!/bin/sh
# The harness's ADDRESS-ERROR core (2026-10-16, the FPGA / MVS crash: odd-address word reads a real 68000 traps and our
# stock Geolith build ignores): our Geolith tree (NeoGeo/geolith, never edited here) copied to $AERR_BUILD
# (/data/tmp/geolith_aerr), aerr_core.patch applied, built with NEOSCAN_AERR=1, installed next to the stock core as
# geolith/libretro/geolith_libretro_aerr.so. harness.py takes it with BRAWLER_AERR=1 (odd_access_proof.py always).
# What it adds (aerr_core.patch, all under #ifdef NEOSCAN_AERR: the stock build is unchanged):
#   Musashi M68K_EMULATE_ADDRESS_ERROR on; every odd-address word / long access logged (retro_neoscan_aerr: count +
#   ring of 4096 [addr, write mode 16 read / 0 write, fc, PPC]); retro_neoscan_aerr_mode(m): 0 off, 1 log and let the
#   access go on (default: a whole run is logged), 2 log and take the 68000's address-error exception as the real CPU
#   (UniBIOS: ADDRESS ERROR screen; SNK MVS BIOS: garbage then a reset); retro_neoscan_aerr_clear; the P2 window /
#   bank-register stats fpga_playthrough.py reads (retro_neoscan_pstat, retro_neoscan_bw); every CPU exception taken
#   through a vector (bus / address error, illegal, zero divide, CHK, TRAPV, privilege, line A / F, TRAP: count + ring
#   of 256 [vector, PPC, A7], retro_neoscan_exc); the watchdog (Geolith emulates it as MAME: 8 frames without a $300001
#   kick = a reset): the longest stretch without a kick, its resets, the last one's PPC (retro_neoscan_wd, _wd_clear).
# Usage: sh tools/brawler/aerr_core.sh   (hw_strict_proof.py runs it when the .so is older than the tree or the patch)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(readlink -f "${GEOLITH:-$HERE/../../geolith}")
DST=${AERR_BUILD:-/data/tmp/geolith_aerr}
OUT="$SRC/libretro/geolith_libretro_aerr.so"
rm -rf "$DST"; mkdir -p "$DST"
(cd "$SRC" && tar --exclude=.git --exclude='*.o' --exclude='*.so' --exclude='*.d' -cf - .) | (cd "$DST" && tar xf -)
patch -s -d "$DST" -p1 < "$HERE/aerr_core.patch"
make -s -C "$DST/libretro" NEOSCAN_AERR=1 -j"$(nproc)" >/dev/null
cp "$DST/libretro/geolith_libretro.so" "$OUT.tmp" && mv -f "$OUT.tmp" "$OUT"   # (a new inode: running harnesses keep theirs)
echo "aerr core: $OUT"
