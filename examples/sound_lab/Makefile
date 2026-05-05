NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = sound_lab

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(BUILD) -Wall

all: $(ROM_NAME).neo

# --- Generate WAV samples (if not present) ---
res/kick.wav:
	python3 $(TOOLS)/gen_drum_kit.py -o res/

# --- Resources (neores pipeline: WAV -> ADPCM, font) ---
$(BUILD)/resources.h: res/resources.res res/kick.wav
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/neores.py res/resources.res -o $(BUILD) --force
	@# Ensure C ROMs exist (neores only creates them when TILES are present)
	@test -f $(BUILD)/combined_c1.bin || dd if=/dev/zero bs=64 count=1 of=$(BUILD)/combined_c1.bin 2>/dev/null
	@test -f $(BUILD)/combined_c2.bin || dd if=/dev/zero bs=64 count=1 of=$(BUILD)/combined_c2.bin 2>/dev/null

# --- Z80 Sound Driver (with custom sample table) ---
$(BUILD)/neosynth_m1.bin: $(TOOLS)/neosynth_build.py $(BUILD)/resources.h
	python3 $(TOOLS)/neosynth_build.py -o $@ \
		--sample-table $(BUILD)/_sfx/sound_table.bin

# --- Compile ---
$(BUILD)/main.o: main.c $(BUILD)/resources.h
	$(CC) $(CFLAGS) -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM ---
$(ROM_NAME).neo: $(BUILD)/rom.elf $(BUILD)/resources.h $(BUILD)/neosynth_m1.bin
	@# Build manifest: font + C ROMs + custom VROM + neosynth driver
	@echo "c1=$(BUILD)/combined_c1.bin" > $(BUILD)/manifest.txt
	@echo "c2=$(BUILD)/combined_c2.bin" >> $(BUILD)/manifest.txt
	@echo "s1=$(BUILD)/font.s1" >> $(BUILD)/manifest.txt
	@echo "donor_m1=$(BUILD)/neosynth_m1.bin" >> $(BUILD)/manifest.txt
	@echo "donor_v1=$(BUILD)/_sfx/vrom.bin" >> $(BUILD)/manifest.txt
	python3 $(TOOLS)/neobuild_from_manifest.py $(BUILD)/manifest.txt \
		--elf $(BUILD)/rom.elf --name $(ROM_NAME) -o $(ROM_NAME).zip

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip $(ROM_NAME).neo roms/ hash/

.PHONY: all clean
