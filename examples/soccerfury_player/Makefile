NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = soccerfury_player

# SoccerFury ROM source
SF_DIR   = /home/bruno/Downloads/neo-soccer

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -Os -ffreestanding -nostdlib -I$(SDK)/include -I$(BUILD) -Wall

all: $(ROM_NAME).zip

# --- Minimal resources (just font, no sprites needed) ---
$(BUILD)/resources.h:
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/font_encoder.py -o $(BUILD)/font.s1
	@echo '#ifndef RESOURCES_H' > $@
	@echo '#define RESOURCES_H' >> $@
	@echo '#include <neoscan.h>' >> $@
	@echo '#endif' >> $@

# --- Compile ---
$(BUILD)/main.o: main.c $(BUILD)/resources.h
	$(CC) $(CFLAGS) -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM using SoccerFury's M1 and V-ROMs directly ---
$(ROM_NAME).zip: $(BUILD)/rom.elf $(BUILD)/resources.h
	@mkdir -p $(BUILD)/roms/$(ROM_NAME) $(BUILD)/hash
	# P ROM (68K program)
	m68k-linux-gnu-objcopy -O binary $(BUILD)/rom.elf $(BUILD)/rom.bin
	python3 -c "\
	data = open('$(BUILD)/rom.bin','rb').read(); \
	data += b'\x00' * (0x80000 - len(data)); \
	out = bytearray(len(data)); \
	[out.__setitem__(i, data[i^1]) for i in range(len(data))]; \
	open('$(BUILD)/roms/$(ROM_NAME)/999-p1.p1','wb').write(bytes(out))"
	# S ROM (font)
	cp $(BUILD)/font.s1 $(BUILD)/roms/$(ROM_NAME)/999-s1.s1
	python3 -c "\
	data = open('$(BUILD)/roms/$(ROM_NAME)/999-s1.s1','rb').read(); \
	data += b'\x00' * (0x20000 - len(data)); \
	open('$(BUILD)/roms/$(ROM_NAME)/999-s1.s1','wb').write(data)"
	# M ROM — truncate to 128KB (softlist driver lacks ZMC2 banking)
	python3 -c "open('$(BUILD)/roms/$(ROM_NAME)/999-m1.m1','wb').write(open('$(SF_DIR)/soccerfury.m1','rb').read()[:0x20000])"
	# V ROM — concatenate all 4 SoccerFury V-ROMs into one ADPCM-A bank
	cat $(SF_DIR)/242-v1.v1 $(SF_DIR)/242-v2.v2 \
	    $(SF_DIR)/242-v3.v3 $(SF_DIR)/242-v4.v4 \
	    > $(BUILD)/roms/$(ROM_NAME)/999-v1.v1
	# C ROMs (empty — no sprites needed for this player)
	python3 -c "open('$(BUILD)/roms/$(ROM_NAME)/999-c1.c1','wb').write(b'\x00'*0x100000)"
	python3 -c "open('$(BUILD)/roms/$(ROM_NAME)/999-c2.c2','wb').write(b'\x00'*0x100000)"
	# Softlist XML
	python3 $(TOOLS)/softlist.py \
	    --name $(ROM_NAME) --description "SoccerFury Sound Player" \
	    --p1 $(BUILD)/roms/$(ROM_NAME)/999-p1.p1 \
	    --s1 $(BUILD)/roms/$(ROM_NAME)/999-s1.s1 \
	    --m1 $(BUILD)/roms/$(ROM_NAME)/999-m1.m1 \
	    --v1 $(BUILD)/roms/$(ROM_NAME)/999-v1.v1 \
	    --c1 $(BUILD)/roms/$(ROM_NAME)/999-c1.c1 \
	    --c2 $(BUILD)/roms/$(ROM_NAME)/999-c2.c2 \
	    -o $(BUILD)/hash/neogeo.xml
	# ZIP
	cd $(BUILD)/roms/$(ROM_NAME) && zip -j ../../../$@ *

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip roms/ hash/

.PHONY: all clean
