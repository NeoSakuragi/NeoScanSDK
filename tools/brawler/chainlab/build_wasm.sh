#!/bin/bash
# Chain Lab: the Geolith core + web_core.c -> core.js / core.wasm (Emscripten; emsdk lives in /data/emsdk, see README)
#   tools/brawler/chainlab/build_wasm.sh [OUTDIR]          (default: /data/tmp/chainlab/site)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
GEO=${GEOLITH:-$HOME/CLProjects/geolith}
OUT=${1:-/data/tmp/chainlab/site}
source /data/emsdk/emsdk_env.sh > /dev/null 2>&1
mkdir -p "$OUT"
SRC=$(sed -n '/^SOURCES_C/,$p' "$GEO/libretro/Makefile.common" | grep -o '\$(CORE_DIR)/[^ ]*\.c' | sed "s#\$(CORE_DIR)#$GEO#")
emcc -O3 -flto -DHAVE_ZLIB -DHAVE_7ZIP -DHAVE_DR_FLAC -DHAVE_FLAC -DHAVE_ZSTD -DZSTD_DISABLE_ASM -DHAVE_CHDR -DNDEBUG -D_7ZIP_ST -DZ7_ST \
  -I"$GEO/deps" -I"$GEO/deps/libretro-common/include" -I"$GEO/deps/miniz" -I"$GEO/deps/lzma/include" -I"$GEO/deps/zstd/lib" \
  -I"$GEO/src" -I"$GEO/libretro" -sUSE_ZLIB=1 \
  $SRC "$HERE/web_core.c" -o "$OUT/core.js" \
  -sMODULARIZE=1 -sEXPORT_NAME=GeoCore -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=134217728 -sENVIRONMENT=web,node \
  -sEXPORTED_RUNTIME_METHODS='["FS","HEAPU8","HEAP16","HEAPU32"]' -sEXPORTED_FUNCTIONS='["_malloc","_free"]' \
  -sFILESYSTEM=1 -sFORCE_FILESYSTEM=1 -Wno-everything
ls -la "$OUT/core.js" "$OUT/core.wasm"
