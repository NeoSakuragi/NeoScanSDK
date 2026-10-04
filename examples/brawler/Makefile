NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = brawler

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(SDK)/src -I$(BUILD) -Wall -DPROFILE_HUD=$(PROFILE) -DAI_OFF=$(AI_OFF)
PROFILE ?= 0
AI_OFF ?= 0
VERSION := $(shell cat VERSION)
CFLAGS += -DGAME_VERSION='"$(VERSION)"'

all: $(ROM_NAME).zip

# --- Fighters: beat 'em up subset of the KOF dictionaries (needs /data/roms/kof96/98/99.neo) ---
CHARS = kof98:terry kof98:ryo kof98:ralf kof98:robert kof98:yamazaki kof98:billy kof98:kyo kof98:iori kof98:mai kof98:yashiro kof96:geese kof96:mr_big kof96:krauser kof99:k_dash
$(BUILD)/bm_chars.c $(BUILD)/bm_chars.h $(BUILD)/bm_c1.bin $(BUILD)/bm_c2.bin $(BUILD)/stage.h $(BUILD)/banner.h $(BUILD)/sparks.h &: $(TOOLS)/brawler/export_bm.py $(TOOLS)/brawler/make_stage_s2.py $(TOOLS)/brawler/make_banner.py $(TOOLS)/brawler/make_sparks.py $(TOOLS)/brawler/sparks98.json
	mkdir -p $(BUILD)
	python3 $(TOOLS)/brawler/export_bm.py $(CURDIR)/$(BUILD) $(CHARS)
	python3 $(TOOLS)/brawler/make_stage_s2.py $(CURDIR)/$(BUILD)   # needs /data/roms/sengoku2.neo
	python3 $(TOOLS)/brawler/make_banner.py $(CURDIR)/$(BUILD)
	python3 $(TOOLS)/brawler/make_sparks.py $(CURDIR)/$(BUILD)

$(BUILD)/font.s1 $(BUILD)/hud.h &: $(TOOLS)/brawler/make_hud.py
	mkdir -p $(BUILD)
	python3 $(TOOLS)/font_encoder.py -o $(BUILD)/font.s1
	python3 $(TOOLS)/brawler/make_hud.py $(CURDIR)/$(BUILD) $(CHARS)

# --- Sound: KOF98's driver and samples, plus Fatal Fury 3's Terry stage theme ported into them as command $27
# (tools/port: needs /data/roms/kof98.neo + fatfury3.neo; overwrites only V ROM that unplayed KOF98 stage themes use)
$(BUILD)/port/kof98_m1.bin $(BUILD)/port/kof98_v1.bin &: $(TOOLS)/port/ff3_to_kof98.py $(TOOLS)/port/ff3_notes.py
	python3 $(TOOLS)/port/ff3_to_kof98.py 0x2F $(CURDIR)/$(BUILD)/port

# --- Compile ---
$(BUILD)/%.o: %.c $(BUILD)/bm_chars.h $(BUILD)/stage.h $(BUILD)/banner.h $(BUILD)/sparks.h $(BUILD)/hud.h fighter.h ai.h sound.h VERSION
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/bm_chars.o: $(BUILD)/bm_chars.c
	$(CC) $(CFLAGS) -c $< -o $@
	m68k-linux-gnu-objcopy --rename-section .rodata=.p2data --rename-section .rodata.str1.1=.p2data.str $@   # tables -> $$200000
$(BUILD)/draw.o: draw.s
	$(CC) -m68000 -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(BUILD)/fighter.o $(BUILD)/ai.o $(BUILD)/sound.o $(BUILD)/draw.o $(BUILD)/bm_chars.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM ---
$(ROM_NAME).zip: $(BUILD)/rom.elf $(BUILD)/bm_c1.bin $(BUILD)/font.s1 $(BUILD)/port/kof98_m1.bin
	printf 'c1=$(BUILD)/bm_c1.bin\nc2=$(BUILD)/bm_c2.bin\ns1=$(BUILD)/font.s1\ndonor_m1=$(BUILD)/port/kof98_m1.bin\ndonor_v1=$(BUILD)/port/kof98_v1.bin\n' > $(BUILD)/manifest.txt
	python3 $(TOOLS)/neobuild_from_manifest.py $(BUILD)/manifest.txt --elf $(BUILD)/rom.elf --name $(ROM_NAME) -o $@

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip $(ROM_NAME).neo roms/ hash/

.PHONY: all clean publish publish-vps bump

# --- publish for the Android player's auto-fetch: brawler.neo + latest.json (build number, size, sha256) into DEST ---
publish: $(ROM_NAME).zip
	@test -n "$(DEST)" || (echo "make publish DEST=<dir served to the phone>"; exit 1)
	mkdir -p $(DEST)
	cp $(ROM_NAME).neo $(DEST)/$(ROM_NAME).neo.tmp && mv $(DEST)/$(ROM_NAME).neo.tmp $(DEST)/$(ROM_NAME).neo
	python3 -c "import hashlib, json, os, time; p = '$(DEST)/$(ROM_NAME).neo'; d = open(p, 'rb').read(); json.dump({'version': '$(VERSION)', 'build': int(time.time()), 'file': '$(ROM_NAME).neo', 'size': len(d), 'sha256': hashlib.sha256(d).hexdigest()}, open('$(DEST)/latest.json', 'w'))"
	cat $(DEST)/latest.json; echo

# --- publish to canneji.duckdns.org/brawler/download/ (the player's auto-fetch), with the Android APK when built ---
APK = ../../android/app/build/outputs/apk/debug/app-debug.apk
publish-vps: $(ROM_NAME).zip
	../../tools/brawler/publish_vps.sh $(ROM_NAME).neo $(VERSION) $(if $(wildcard $(APK)),$(APK) $(VERSION))

# --- version (VERSION, 0.0.1 style, shown on the title screen): make bump = last number + 1 ---
bump:
	python3 -c "v = open('VERSION').read().split('.'); v[-1] = str(int(v[-1]) + 1); open('VERSION', 'w').write('.'.join(v) + '\\n')"
	cat VERSION
