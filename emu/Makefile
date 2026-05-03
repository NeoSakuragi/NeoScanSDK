CC      := gcc
CFLAGS  := -O2 -march=native -Wall -Wextra -Wno-unused-parameter \
           $(shell pkg-config --cflags sdl2)
LDFLAGS := $(shell pkg-config --libs sdl2) -lzip -lm

BUILD_DIR := build

EMU_SRC := src/main.c src/neogeo.c src/cpu68k.c src/memory.c src/video.c \
           src/rom_loader.c src/input.c src/display.c src/calendar.c

ALL_OBJ := $(patsubst %.c,$(BUILD_DIR)/%.o,$(EMU_SRC))
TARGET  := ngemu

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(ALL_OBJ)
	$(CC) -o $@ $^ $(LDFLAGS)
	@echo "=== NG-EMU built ==="

$(BUILD_DIR)/%.o: %.c | dirs
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

dirs:
	@mkdir -p $(BUILD_DIR)/src

clean:
	rm -rf $(BUILD_DIR) $(TARGET)
