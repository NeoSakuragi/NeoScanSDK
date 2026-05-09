NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = danmaku

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(BUILD) -Wall

all: $(ROM_NAME).neo

# --- Generate assets ---
.PHONY: assets
assets:
	python3 gen_assets.py

# --- Resources ---
.PHONY: resources
resources: assets
	python3 $(TOOLS)/neores.py res/resources.res -o $(BUILD)

$(BUILD)/resources.h: resources
	@true

# --- Compile ---
$(BUILD)/main.o: main.c $(BUILD)/resources.h
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/neo_bullet.o: $(SDK)/src/neo_bullet.c
	$(CC) $(CFLAGS) -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(BUILD)/neo_bullet.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM ---
$(ROM_NAME).neo: $(BUILD)/rom.elf $(BUILD)/resources.h
	python3 $(TOOLS)/neobuild_from_manifest.py $(BUILD)/manifest.txt \
		--elf $(BUILD)/rom.elf --name $(ROM_NAME) -o $@

clean:
	rm -rf $(BUILD) $(ROM_NAME).neo

.PHONY: all clean
