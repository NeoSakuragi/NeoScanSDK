NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = hello_neo

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(BUILD) -Wall

TERRY_ASE = /home/bruno/NeoGeo/output/kof95/sprites/15_terry_bogard/idle.aseprite
WAVS      = assets/beep.wav assets/hit.wav

all: $(ROM_NAME).zip

# --- Tiles ---
$(BUILD)/palette.h: assets/sprites.png
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/palette_encoder.py $< -o $@

$(BUILD)/tiles.h $(BUILD)/tiles_c1.bin $(BUILD)/tiles_c2.bin: assets/sprites.png
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/tile_encoder.py $< -o $(BUILD)

# --- Animation ---
$(BUILD)/anim_idle.h $(BUILD)/anim_palette.h $(BUILD)/anim_c1.bin $(BUILD)/anim_c2.bin: $(TERRY_ASE) $(BUILD)/tiles.h
	python3 $(TOOLS)/anim_encoder.py $(TERRY_ASE) -o $(BUILD) \
		--tile-base $$(grep 'define TILE_COUNT' $(BUILD)/tiles.h | awk '{print $$3}')

# --- Font ---
$(BUILD)/font.s1:
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/font_encoder.py -o $@

# --- Sound effects ---
$(BUILD)/sounds.h $(BUILD)/vrom.bin $(BUILD)/sound_table.bin: $(WAVS)
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/wav_encoder.py $(WAVS) -o $(BUILD)

# --- Music ---
$(BUILD)/music.bin $(BUILD)/music_samples.bin: assets/music.vgz
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/vgm_converter.py $< -o $(BUILD)/music.bin \
		--samples-out $(BUILD)/music_samples.bin

# --- Combine C ROMs ---
$(BUILD)/combined_c1.bin: $(BUILD)/tiles_c1.bin $(BUILD)/anim_c1.bin
	cat $^ > $@

$(BUILD)/combined_c2.bin: $(BUILD)/tiles_c2.bin $(BUILD)/anim_c2.bin
	cat $^ > $@

# --- Compile ---
$(BUILD)/main.o: main.c $(BUILD)/palette.h $(BUILD)/tiles.h $(BUILD)/anim_idle.h $(BUILD)/anim_palette.h $(BUILD)/sounds.h
	$(CC) $(CFLAGS) -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM ---
$(ROM_NAME).zip: $(BUILD)/rom.elf $(BUILD)/combined_c1.bin $(BUILD)/combined_c2.bin $(BUILD)/font.s1 $(BUILD)/vrom.bin $(BUILD)/sound_table.bin $(BUILD)/music.bin $(BUILD)/music_samples.bin
	python3 $(TOOLS)/neobuild.py \
		--elf $(BUILD)/rom.elf \
		--c1 $(BUILD)/combined_c1.bin \
		--c2 $(BUILD)/combined_c2.bin \
		--s1 $(BUILD)/font.s1 \
		--v1 $(BUILD)/vrom.bin \
		--v1-overlay $(BUILD)/music_samples.bin \
		--sound-table $(BUILD)/sound_table.bin \
		--music $(BUILD)/music.bin \
		--name $(ROM_NAME) \
		-o $@

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip roms/ hash/

.PHONY: all clean
