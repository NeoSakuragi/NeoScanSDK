NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = hello_neo

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(BUILD) -Wall

all: $(ROM_NAME).zip

# --- Asset pipeline ---
$(BUILD)/palette.h: assets/sprites.png
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/palette_encoder.py $< -o $@

$(BUILD)/tiles.h $(BUILD)/tiles_c1.bin $(BUILD)/tiles_c2.bin: assets/sprites.png
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/tile_encoder.py $< -o $(BUILD)

# --- Compile ---
$(BUILD)/main.o: main.c $(BUILD)/palette.h $(BUILD)/tiles.h
	$(CC) $(CFLAGS) -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM ---
$(ROM_NAME).zip: $(BUILD)/rom.elf $(BUILD)/tiles_c1.bin $(BUILD)/tiles_c2.bin
	python3 $(TOOLS)/neobuild.py \
		--elf $(BUILD)/rom.elf \
		--c1 $(BUILD)/tiles_c1.bin \
		--c2 $(BUILD)/tiles_c2.bin \
		--name $(ROM_NAME) \
		-o $@

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip roms/ hash/

.PHONY: all clean
