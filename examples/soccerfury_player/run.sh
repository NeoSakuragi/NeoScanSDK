#!/bin/sh
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIOS_DIR="/home/bruno/NeoGeo/roms"

echo "Building SoccerFury Sound Player..."
make -C "$SCRIPT_DIR"

echo "Launching MAME..."
/usr/games/mame neogeo soccerfury_player \
    -hashpath "$SCRIPT_DIR/build/hash;/usr/share/games/mame/hash" \
    -rompath "$SCRIPT_DIR/build/roms;$BIOS_DIR" \
    -noautosave -skip_gameinfo \
    -window \
    -wavwrite "$SCRIPT_DIR/soccerfury_capture.wav" \
    "$@"

echo ""
echo "Audio captured to: $SCRIPT_DIR/soccerfury_capture.wav"
echo "Convert to MP3:  ffmpeg -i soccerfury_capture.wav -b:a 192k soccerfury_capture.mp3"
