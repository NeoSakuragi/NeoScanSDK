#!/bin/sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIOS_DIR="/home/bruno/NeoGeo/roms"
mame neogeo hello_neo \
    -hashpath "$SCRIPT_DIR/hash;/usr/share/games/mame/hash" \
    -rompath "$SCRIPT_DIR/roms;$BIOS_DIR" \
    -noautosave -skip_gameinfo "$@"
