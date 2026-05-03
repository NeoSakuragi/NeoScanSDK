NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = jukebox

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -Os -ffreestanding -nostdlib -I$(SDK)/include -I$(BUILD) -Wall

all: $(ROM_NAME).zip

.PHONY: resources
resources:
	python3 $(TOOLS)/neores.py res/resources.res -o $(BUILD)

$(BUILD)/resources.h: resources
	@true

$(BUILD)/main.o: main.c $(BUILD)/resources.h
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# Build ROM with standard pipeline, then swap M1
$(ROM_NAME).zip: $(BUILD)/rom.elf $(BUILD)/resources.h
	python3 $(TOOLS)/neobuild_from_manifest.py $(BUILD)/manifest.txt \
		--elf $(BUILD)/rom.elf --name $(ROM_NAME) -o $@
	# Now swap the M1 ROM with KOF98's v1.7 driver (truncated to 128KB)
	python3 -c "\
	import zipfile, os; \
	m1 = open('/home/bruno/Downloads/neo-soccer/soccerfury.m1','rb').read()[:0x20000]; \
	zin = zipfile.ZipFile('$(ROM_NAME).zip','r'); \
	zout = zipfile.ZipFile('$(ROM_NAME)_v17.zip','w'); \
	[zout.writestr(n, m1 if n.endswith('-m1.m1') else zin.read(n)) for n in zin.namelist()]; \
	zin.close(); zout.close(); \
	os.rename('$(ROM_NAME)_v17.zip','$(ROM_NAME).zip')"
	# Update softlist XML with new M1 checksum
	python3 $(TOOLS)/softlist.py \
		--name $(ROM_NAME) --description 'KOF98 Jukebox' \
		--p1 roms/$(ROM_NAME)/999-p1.p1 \
		--s1 roms/$(ROM_NAME)/999-s1.s1 \
		--m1 /dev/stdin \
		--v1 roms/$(ROM_NAME)/999-v1.v1 \
		--c1 roms/$(ROM_NAME)/999-c1.c1 \
		--c2 roms/$(ROM_NAME)/999-c2.c2 \
		-o hash/neogeo.xml < /dev/null 2>/dev/null || true
	# Extract M1 to roms dir for softlist verification
	python3 -c "\
	m1 = open('/home/bruno/Downloads/neo-soccer/soccerfury.m1','rb').read()[:0x20000]; \
	open('roms/$(ROM_NAME)/999-m1.m1','wb').write(m1)"
	# Regenerate softlist with correct checksums
	python3 $(TOOLS)/softlist.py \
		--name $(ROM_NAME) --description 'KOF98 Jukebox' \
		--p1 roms/$(ROM_NAME)/999-p1.p1 \
		--s1 roms/$(ROM_NAME)/999-s1.s1 \
		--m1 roms/$(ROM_NAME)/999-m1.m1 \
		--v1 roms/$(ROM_NAME)/999-v1.v1 \
		--c1 roms/$(ROM_NAME)/999-c1.c1 \
		--c2 roms/$(ROM_NAME)/999-c2.c2 \
		-o hash/neogeo.xml
	# Repackage ZIP with the swapped M1
	cd roms/$(ROM_NAME) && zip -j ../../$(ROM_NAME).zip *

run: $(ROM_NAME).zip
	/usr/games/mame neogeo $(ROM_NAME) \
		-hashpath "hash;/usr/share/games/mame/hash" \
		-rompath "roms;/home/bruno/NeoGeo/roms" \
		-noautosave -skip_gameinfo -window \
		-wavwrite jukebox_capture.wav

screenshot: $(ROM_NAME).zip
	mkdir -p snap
	/usr/games/mame neogeo $(ROM_NAME) \
		-hashpath "hash;/usr/share/games/mame/hash" \
		-rompath "roms;/home/bruno/NeoGeo/roms" \
		-noautosave -skip_gameinfo -window \
		-seconds_to_run 8 \
		-snapname jukebox_test \
		-snapshot_directory snap \
		-autoboot_script ../hello_neo/test_screenshot.lua

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip $(ROM_NAME).neo roms/ hash/ snap/

.PHONY: all clean run screenshot
