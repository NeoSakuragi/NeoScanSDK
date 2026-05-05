#!/bin/sh
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

pkill -f neogeo_sdl 2>/dev/null || true
sleep 0.3

# Build hello_neo first (for shared assets)
make -C "$SDK_DIR/examples/hello_neo" 2>/dev/null || true

cd "$SDK_DIR"
make -C examples/sound_lab clean
make -C examples/sound_lab

"$SDK_DIR/emu/neogeo_sdl" "$SCRIPT_DIR/sound_lab.neo"
