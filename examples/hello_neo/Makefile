NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = hello_neo

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(BUILD) -Wall

all: $(ROM_NAME).zip

# --- Resources (always runs, uses internal cache for incremental) ---
.PHONY: resources
resources:
	python3 $(TOOLS)/neores.py resources.res -o $(BUILD)

$(BUILD)/resources.h: resources
	@true

# --- Compile ---
$(BUILD)/main.o: main.c $(BUILD)/resources.h
	$(CC) $(CFLAGS) -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM ---
$(ROM_NAME).zip: $(BUILD)/rom.elf $(BUILD)/manifest.txt
	python3 $(TOOLS)/neobuild.py \
		--elf $(BUILD)/rom.elf \
		--c1 $(BUILD)/combined_c1.bin \
		--c2 $(BUILD)/combined_c2.bin \
		--s1 $(BUILD)/font.s1 \
		--v1 $(BUILD)/_sfx/vrom.bin \
		--v1-overlay $(BUILD)/_music_mus_theme/samples.bin \
		--sound-table $(BUILD)/_sfx/sound_table.bin \
		--music $(BUILD)/_music_mus_theme/stream.bin \
		--name $(ROM_NAME) \
		-o $@

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip $(ROM_NAME).neo roms/ hash/

.PHONY: all clean
