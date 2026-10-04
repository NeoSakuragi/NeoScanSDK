#!/bin/bash
# Build the RP2040 flash programmer firmware
# Requires: pico-sdk, cmake, gcc-arm-none-eabi

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

export PICO_SDK_PATH="${PICO_SDK_PATH:-$HOME/pico-sdk}"

if [ ! -d "$PICO_SDK_PATH" ]; then
    echo "ERROR: Pico SDK not found at $PICO_SDK_PATH"
    echo "Clone it: git clone https://github.com/raspberrypi/pico-sdk.git $PICO_SDK_PATH"
    echo "Then: cd $PICO_SDK_PATH && git submodule update --init"
    exit 1
fi

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake "$SCRIPT_DIR" -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

echo ""
echo "Build complete!"
echo "Firmware: ${BUILD_DIR}/neocart_programmer.uf2"
echo ""
echo "To flash: hold BOOTSEL on RP2040, plug USB, copy .uf2 to the RPI-RP2 drive"
