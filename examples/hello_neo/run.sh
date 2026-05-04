#!/bin/sh
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

pkill -f neogeo_sdl 2>/dev/null || true
sleep 0.3

cd "$SDK_DIR"
make -C examples/hello_neo clean
make -C examples/hello_neo

"$SDK_DIR/emu/neogeo_sdl" "$SCRIPT_DIR/hello_neo.neo"
