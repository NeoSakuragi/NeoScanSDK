NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = sound_lab

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(BUILD) -Wall

all: $(ROM_NAME).neo

# --- Resources (reuse hello_neo's font + basic tiles) ---
$(BUILD)/resources.h:
	@mkdir -p $(BUILD)
	cp ../hello_neo/build/font.s1 $(BUILD)/font.s1 2>/dev/null || true
	cp ../hello_neo/build/combined_c1.bin $(BUILD)/combined_c1.bin 2>/dev/null || true
	cp ../hello_neo/build/combined_c2.bin $(BUILD)/combined_c2.bin 2>/dev/null || true
	cp ../hello_neo/build/resources.h $(BUILD)/resources.h 2>/dev/null || true
	@echo "c1=$(BUILD)/combined_c1.bin" > $(BUILD)/manifest.txt
	@echo "c2=$(BUILD)/combined_c2.bin" >> $(BUILD)/manifest.txt
	@echo "s1=$(BUILD)/font.s1" >> $(BUILD)/manifest.txt

# --- Z80 Sound Driver ---
$(BUILD)/neosynth_m1.bin: $(TOOLS)/neosynth_build.py
	python3 $(TOOLS)/neosynth_build.py -o $@

# --- Compile ---
$(BUILD)/main.o: main.c $(BUILD)/resources.h
	$(CC) $(CFLAGS) -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM ---
$(ROM_NAME).neo: $(BUILD)/rom.elf $(BUILD)/resources.h $(BUILD)/neosynth_m1.bin
	@echo "donor_m1=$(BUILD)/neosynth_m1.bin" >> $(BUILD)/manifest.txt
	python3 $(TOOLS)/neobuild_from_manifest.py $(BUILD)/manifest.txt \
		--elf $(BUILD)/rom.elf --name $(ROM_NAME) -o $(ROM_NAME).zip

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip $(ROM_NAME).neo roms/ hash/

.PHONY: all clean
