NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = brawler

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(SDK)/src -I$(BUILD) -I. -Wall -DPROFILE_HUD=$(PROFILE) -DAI_OFF=$(AI_OFF) -DSTAGE=$(STAGE)
PROFILE ?= 0
AI_OFF ?= 0
STAGE ?= 0                # the stage the fight starts on (stage.h stages[], tools/brawler/make_stage_ra.py STAGES)
VERSION := $(shell cat VERSION)
CFLAGS += -DGAME_VERSION='"$(VERSION)"'

all: $(ROM_NAME).zip

# --- The game's data: game.json (docs/brawler_data_model.md) -> build/roster.json (the fighter export's inputs, rewritten
# only when they change) and build/game_tables.c / .h (stages, waves, enemies, AI presets, select slots, unlocks) ---
CHARS := $(shell python3 $(TOOLS)/brawler/build_tables.py chars game.json)   # the roster's bank specs, bm_chars order
$(BUILD)/roster.json: game.json $(TOOLS)/brawler/build_tables.py
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/brawler/build_tables.py roster game.json $@
$(BUILD)/game_tables.c $(BUILD)/game_tables.h &: game.json $(TOOLS)/brawler/build_tables.py $(BUILD)/stage.h $(BUILD)/bm_chars.h $(TOOLS)/brawler/routes.py $(wildcard $(TOOLS)/brawler/routes/enemies/*.json)
	python3 $(TOOLS)/brawler/build_tables.py tables game.json $(CURDIR)/$(BUILD)

# --- Fighters: beat 'em up subset of the KOF dictionaries (needs /data/roms/kof96/98/99.neo) and of Samurai Shodown IV
# (tools/samsho4: /data/roms/samsho4.neo + /data/neogeo_dict/samsho4/haohmaru_capture.json) ---
$(BUILD)/bm_chars.c $(BUILD)/bm_spec.c $(BUILD)/bm_chars.h $(BUILD)/voice_map.json $(BUILD)/bm_c1.bin $(BUILD)/bm_c2.bin $(BUILD)/stage.h $(BUILD)/banner.h $(BUILD)/sparks.h &: $(BUILD)/roster.json $(TOOLS)/brawler/export_bm.py $(wildcard $(TOOLS)/samsho4/*.py) $(TOOLS)/brawler/routes.py $(wildcard $(TOOLS)/brawler/routes/*.json) $(TOOLS)/brawler/make_stage_ra.py $(TOOLS)/brawler/make_banner.py $(TOOLS)/brawler/make_sparks.py $(TOOLS)/brawler/sparks98.json $(TOOLS)/brawler/voices.json $(TOOLS)/brawler/voices.py
	mkdir -p $(BUILD)
	python3 $(TOOLS)/brawler/export_bm.py $(CURDIR)/$(BUILD) --roster $(CURDIR)/$(BUILD)/roster.json
	python3 $(TOOLS)/brawler/make_stage_ra.py $(CURDIR)/$(BUILD)   # needs /data/roms/roboarmy.neo
	python3 $(TOOLS)/brawler/make_banner.py $(CURDIR)/$(BUILD)
	python3 $(TOOLS)/brawler/make_sparks.py $(CURDIR)/$(BUILD)

$(BUILD)/font.s1 $(BUILD)/hud.h &: $(TOOLS)/brawler/make_hud.py
	mkdir -p $(BUILD)
	python3 $(TOOLS)/font_encoder.py -o $(BUILD)/font.s1
	python3 $(TOOLS)/brawler/make_hud.py $(CURDIR)/$(BUILD) $(CHARS)

# --- Sound: songs.json -> KOF98's driver with only the songs the game plays (M ROM), only the samples they and the
# game's effects use (V ROM), build/snd/songs.h (MUS_* = driver commands, BOSS_SONGS); songs from other games are
# ported into KOF98's format (tools/port/build_snd.py; needs /data/roms/kof98.neo and each source game's ROM); the
# fighters' voices the ROM maps (build/voice_map.json, game.json roster[].voices) from their games' V ROMs
SND_TOOLS = $(addprefix $(TOOLS)/port/,build_snd.py port98.py ff3_notes.py snk_notes.py) $(TOOLS)/kof98snd/games98.py
$(BUILD)/snd/m1.bin $(BUILD)/snd/v1.bin $(BUILD)/snd/songs.h $(BUILD)/snd/voices.h &: songs.json $(SND_TOOLS) $(BUILD)/voice_map.json $(TOOLS)/brawler/voices.json
	python3 $(TOOLS)/port/build_snd.py songs.json $(CURDIR)/$(BUILD)/snd

# --- Compile ---
$(BUILD)/stage_opt: FORCE                  # the STAGE option of the last build: main.o is rebuilt when it changes
	@mkdir -p $(BUILD); echo $(STAGE) | cmp -s - $@ || echo $(STAGE) > $@
$(BUILD)/main.o: $(BUILD)/stage_opt
$(BUILD)/%.o: %.c $(BUILD)/bm_chars.h $(BUILD)/stage.h $(BUILD)/banner.h $(BUILD)/sparks.h $(BUILD)/hud.h $(BUILD)/game_tables.h fighter.h ai.h sound.h gamedata.h $(BUILD)/snd/songs.h $(BUILD)/snd/voices.h VERSION
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/game_tables.o: $(BUILD)/game_tables.c $(BUILD)/game_tables.h $(BUILD)/bm_chars.h gamedata.h $(BUILD)/snd/songs.h
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/bm_chars.o: $(BUILD)/bm_chars.c
	$(CC) $(CFLAGS) -c $< -o $@
	m68k-linux-gnu-objcopy --rename-section .rodata=.p2data --rename-section .rodata.str1.1=.p2data.str $@   # tables -> $$200000
$(BUILD)/bm_spec.o: $(BUILD)/bm_spec.c $(BUILD)/bm_chars.h      # every fighter's specials: plain .rodata, the first MB
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/draw.o: draw.s
	$(CC) -m68000 -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(BUILD)/fighter.o $(BUILD)/ai.o $(BUILD)/sound.o $(BUILD)/draw.o $(BUILD)/bm_chars.o $(BUILD)/bm_spec.o $(BUILD)/game_tables.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld -o $@ $^

# --- Package ROM ---
$(ROM_NAME).zip: $(BUILD)/rom.elf $(BUILD)/bm_c1.bin $(BUILD)/font.s1 $(BUILD)/snd/m1.bin
	printf 'c1=$(BUILD)/bm_c1.bin\nc2=$(BUILD)/bm_c2.bin\ns1=$(BUILD)/font.s1\ndonor_m1=$(BUILD)/snd/m1.bin\ndonor_v1=$(BUILD)/snd/v1.bin\n' > $(BUILD)/manifest.txt
	python3 $(TOOLS)/neobuild_from_manifest.py $(BUILD)/manifest.txt --elf $(BUILD)/rom.elf --name $(ROM_NAME) -o $@

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip $(ROM_NAME).neo roms/ hash/

.PHONY: all clean publish publish-vps bump FORCE

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
