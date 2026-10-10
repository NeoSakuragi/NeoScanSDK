NEOSCAN  = $(realpath ../..)
SDK      = $(NEOSCAN)/sdk
TOOLS    = $(NEOSCAN)/tools
BUILD    = build
ROM_NAME = brawler
# the Brawler Lab's build of one fighter ("Try in game", Bruno 2026-10-10): make LAB_FIGHTER=robert -> lab-robert.neo from
# build_lab_robert/: every animation of his dictionary in one more special of his pool (tools/brawler/export_bm.py --lab,
# fighter.c "Lab: try in game"); the other fighters as usual. Lab-only: never published as the Player's game
LAB_FIGHTER ?=
ifneq ($(LAB_FIGHTER),)
BUILD    = build_lab_$(LAB_FIGHTER)
ROM_NAME = lab-$(LAB_FIGHTER)
endif
# the Character Lab's shell and packs (Bruno 2026-10-10: "one lab build and two exported data sets, two characters we could
# dynamically swap"; docs/feedback.md "Character Lab: shell and packs"): the game with one more roster fighter, the SLOT
# (the last index; build_tables.py add_slot), whose data sits in fixed regions: its first-MB tables in .labslot (linked
# at LABSLOT_AT), its banked tables in a P2 bank of its own, its tiles in a block of export_bm.SLOT_TILES, its voices in a
# V area + driver records of their own (build_snd.py), its HUD face in the S ROM. make LAB_SHELL=1 -> lab-shell.neo
# (build_shell/, the slot = SHELL_SLOT, so it boots into the practice with him); make LAB_PACK=<f> -> packs/<f>.pack +
# .json (build_pack_<f>/: the same game with <f> in the slot; tools/brawler/lab_pack.py takes the slot's regions and
# refuses a pack whose bytes differ from the shell's anywhere else, or that overflows a region). Lab-only builds.
SHELL_SLOT = robert
LABSLOT_AT = 0xE0000                       # .labslot: $E0000-$FFFFF (lab_pack.py LABSLOT_SIZE)
LAB_SHELL ?=
LAB_PACK ?=
SLOT =
ifneq ($(LAB_SHELL),)
SLOT = $(SHELL_SLOT)
endif
ifneq ($(LAB_PACK),)
SLOT = $(LAB_PACK)
endif
ifneq ($(SLOT),)
ifeq ($(SLOT),$(SHELL_SLOT))
BUILD    = build_shell
ROM_NAME = lab-shell
else
BUILD    = build_pack_$(SLOT)
ROM_NAME = pack-$(SLOT)
endif
export BRAWLER_SLOT = $(SLOT)
SLOT_CFLAGS = -DLAB_SHELL=1
SLOT_LDFLAGS = --section-start=.labslot=$(LABSLOT_AT)
else
unexport BRAWLER_SLOT
endif
# every Lab build (LAB_FIGHTER, LAB_SHELL or LAB_PACK) compiles the practice mode in (main.c "PRACTICE MODE"): -DLAB_BUILD=1; the
# Player's game 0 (none of that code is in it)
LAB_BUILD = $(if $(LAB_FIGHTER)$(LAB_SHELL)$(LAB_PACK),1,0)

CC       = m68k-linux-gnu-gcc
LD       = m68k-linux-gnu-ld
CFLAGS   = -m68000 -O2 -ffreestanding -nostdlib -I$(SDK)/include -I$(SDK)/src -I$(BUILD) -I. -Wall -fno-store-merging -DPROFILE_HUD=$(PROFILE) -DAI_OFF=$(AI_OFF) -DSTAGE=$(STAGE) -DLAB_BUILD=$(LAB_BUILD)
PROFILE ?= 0
AI_OFF ?= 0
STAGE ?= 0                # the stage the fight starts on (stage.h stages[], tools/brawler/make_stage_ra.py STAGES)
# -fno-store-merging (TODO #177): GCC 15's store merging joins byte stores at an odd offset into one word / long move
# (clr.w 97(a2)) even under -m68000 -mstrict-align; a real 68000 takes an address error there (an odd word access)
VERSION := $(shell cat VERSION)
CFLAGS += -DGAME_VERSION='"$(VERSION)"' $(SLOT_CFLAGS)

ifneq ($(LAB_PACK),)
all: packs/$(LAB_PACK).pack
else
all: $(ROM_NAME).zip
endif

# --- The game's data: game.json (docs/brawler_data_model.md) -> build/roster.json (the fighter export's inputs, rewritten
# only when they change) and build/game_tables.c / .h (stages, waves, enemies, AI presets, select slots, unlocks) ---
CHARS := $(shell BRAWLER_SLOT=$(SLOT) python3 $(TOOLS)/brawler/build_tables.py chars game.json)   # the roster's bank specs, bm_chars order
$(BUILD)/roster.json: game.json $(TOOLS)/brawler/build_tables.py
	@mkdir -p $(BUILD)
	python3 $(TOOLS)/brawler/build_tables.py roster game.json $@
$(BUILD)/game_tables.c $(BUILD)/game_tables.h &: game.json $(TOOLS)/brawler/build_tables.py $(TOOLS)/brawler/retime.py $(TOOLS)/brawler/damage_raw.json $(BUILD)/stage.h $(BUILD)/bm_chars.h $(TOOLS)/brawler/routes.py $(wildcard $(TOOLS)/brawler/routes/enemies/*.json)
	python3 $(TOOLS)/brawler/build_tables.py tables game.json $(CURDIR)/$(BUILD)

# --- Fighters: beat 'em up subset of the KOF dictionaries (needs /data/roms/kof96/98/99.neo) and of Samurai Shodown IV
# (tools/samsho4: /data/roms/samsho4.neo + /data/neogeo_dict/samsho4/haohmaru_capture.json) and of World Heroes Perfect
# (tools/whp: /data/roms/whp.neo + /data/neogeo_dict/whp/hanzo_capture.json) and of Kizuna Encounter (tools/kizuna:
# /data/roms/kizuna.neo + /data/neogeo_dict/kizuna/kim_capture.json) and of Double Dragon (tools/doubledr: /data/roms/doubledr.neo,
# its palette RAM /data/neogeo_dict/doubledr/palram.json) and of Samurai Shodown II (tools/samsho2: /data/roms/samsho2.neo;
# Haohmaru, Genjuro, Kuroko read from its ROM) ---
$(BUILD)/bm_chars.c $(BUILD)/bm_spec.c $(BUILD)/bm_chars.h $(BUILD)/voice_map.json $(BUILD)/bm_c1.bin $(BUILD)/bm_c2.bin $(BUILD)/stage.h $(BUILD)/land.h $(BUILD)/banner.h $(BUILD)/sparks.h $(BUILD)/superflash.h $(BUILD)/throwfx.h &: $(BUILD)/roster.json $(TOOLS)/brawler/export_bm.py $(wildcard $(TOOLS)/kof96/*.py) $(TOOLS)/brawler/retime.py $(wildcard $(TOOLS)/samsho4/*.py) $(wildcard $(TOOLS)/whp/*.py) $(wildcard $(TOOLS)/kizuna/*.py) $(wildcard $(TOOLS)/doubledr/*.py) $(wildcard $(TOOLS)/samsho2/*.py) $(TOOLS)/samsho2/victim_poses_ss2.json $(TOOLS)/doubledr/victim_poses_dd.json $(TOOLS)/brawler/routes.py $(wildcard $(TOOLS)/brawler/routes/*.json) $(TOOLS)/brawler/make_stage_ra.py $(TOOLS)/brawler/make_stage_land.py $(TOOLS)/brawler/make_banner.py $(TOOLS)/brawler/make_sparks.py $(TOOLS)/brawler/sparks98.json $(TOOLS)/brawler/voices.json $(TOOLS)/brawler/voices.py $(if $(LAB_FIGHTER),$(TOOLS)/brawler/arb_pieces/$(LAB_FIGHTER).json)
	mkdir -p $(BUILD)
	python3 $(TOOLS)/brawler/export_bm.py $(CURDIR)/$(BUILD) --roster $(CURDIR)/$(BUILD)/roster.json $(if $(LAB_FIGHTER),--lab $(LAB_FIGHTER))
	python3 $(TOOLS)/brawler/make_stage_ra.py $(CURDIR)/$(BUILD)   # needs /data/roms/roboarmy.neo
	python3 $(TOOLS)/brawler/make_stage_land.py $(CURDIR)/$(BUILD)   # the select screen: KOF95 stage 2 (/data/roms/kof95.neo, /data/neogeo_dict/kof95/stages)
	python3 $(TOOLS)/brawler/make_banner.py $(CURDIR)/$(BUILD)
	python3 $(TOOLS)/brawler/make_sparks.py $(CURDIR)/$(BUILD)

# --- Drama mode portraits: game.json "portraits" (tools/brawler/big_portraits.py capture -> /data/neogeo_dict/portraits)
# appended after the fighters' tiles: rom_c1/c2.bin = the C ROM the package takes ---
$(BUILD)/rom_c1.bin $(BUILD)/rom_c2.bin $(BUILD)/portraits_big.h &: $(BUILD)/bm_c1.bin game.json $(TOOLS)/brawler/big_portraits.py
	python3 $(TOOLS)/brawler/big_portraits.py build game.json $(CURDIR)/$(BUILD)

# --- S ROM: Kizuna Encounter's outlined font (needs /data/roms/kizuna.neo), life bar glyphs, HUD portraits ---
$(BUILD)/font.s1 $(BUILD)/hud.h &: $(TOOLS)/brawler/make_hud.py $(BUILD)/roster.json $(wildcard /data/neogeo_dict/portraits/*_square.png)   # (the roster: its portraits, TODO #212; their squares: a re-made face rebuilds it)
	mkdir -p $(BUILD)
	python3 $(TOOLS)/brawler/make_hud.py $(CURDIR)/$(BUILD) $(CHARS)

# --- Sound: songs.json -> KOF98's driver with only the songs the game plays (M ROM), only the samples they and the
# game's effects use (V ROM), build/snd/songs.h (MUS_* = driver commands, BOSS_SONGS); songs from other games are
# ported into KOF98's format (tools/port/build_snd.py; needs /data/roms/kof98.neo and each source game's ROM); the
# fighters' voices the ROM maps (build/voice_map.json, game.json roster[].voices) from their games' V ROMs
SND_TOOLS = $(addprefix $(TOOLS)/port/,build_snd.py port98.py ff3_notes.py snk_notes.py) $(TOOLS)/kof98snd/games98.py
$(BUILD)/snd/m1.bin $(BUILD)/snd/v1.bin $(BUILD)/snd/songs.h $(BUILD)/snd/voices.h &: songs.json $(SND_TOOLS) $(BUILD)/voice_map.json $(TOOLS)/brawler/voices.json
	python3 $(TOOLS)/port/build_snd.py songs.json $(CURDIR)/$(BUILD)/snd --map $(CURDIR)/$(BUILD)/voice_map.json

# --- Compile ---
$(BUILD)/stage_opt: FORCE                  # the -D options of the last build (STAGE, AI_OFF, PROFILE): every object is rebuilt
	@mkdir -p $(BUILD); echo "$(STAGE) $(AI_OFF) $(PROFILE) $(LAB_BUILD)" | cmp -s - $@ || echo "$(STAGE) $(AI_OFF) $(PROFILE) $(LAB_BUILD)" > $@   # when one changes (an AI_OFF build no longer leaves main.o stale)
$(BUILD)/%.o: %.c $(BUILD)/stage_opt $(BUILD)/bm_chars.h $(BUILD)/stage.h $(BUILD)/banner.h $(BUILD)/sparks.h $(BUILD)/superflash.h $(BUILD)/throwfx.h $(BUILD)/hud.h $(BUILD)/portraits_big.h $(BUILD)/game_tables.h fighter.h ai.h sound.h gamedata.h $(BUILD)/snd/songs.h $(BUILD)/snd/voices.h VERSION
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/game_tables.o: $(BUILD)/game_tables.c $(BUILD)/game_tables.h $(BUILD)/bm_chars.h gamedata.h $(BUILD)/snd/songs.h
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/main.o: main.c $(BUILD)/stage_opt $(BUILD)/bm_chars.h $(BUILD)/stage.h $(BUILD)/land.h $(BUILD)/banner.h $(BUILD)/sparks.h $(BUILD)/superflash.h $(BUILD)/throwfx.h $(BUILD)/hud.h $(BUILD)/portraits_big.h $(BUILD)/game_tables.h fighter.h ai.h sound.h gamedata.h $(BUILD)/snd/songs.h $(BUILD)/snd/voices.h VERSION
	$(CC) $(CFLAGS) -c $< -o $@
# the fighters' tables: one section per table (-fdata-sections), then tools/brawler/bank_pack.py sends each fighter's
# bulk (frames, tiles, special scripts and programs, projectile rows) to its P2 bank and keeps what every fighter and
# the engine read every frame in the first MB (docs/rom_packer_rules.md "P ROM"); objcopy renames the banked tables'
# sections .p2bankN (sdk/boot/neoscan.ld), bm_bank.c holds each fighter's bank
$(BUILD)/bm_chars.o: $(BUILD)/bm_chars.c
	$(CC) $(CFLAGS) -fdata-sections -c $< -o $@
$(BUILD)/bm_spec.o: $(BUILD)/bm_spec.c $(BUILD)/bm_chars.h
	$(CC) $(CFLAGS) -fdata-sections -c $< -o $@
$(BUILD)/bank_rename.txt $(BUILD)/bm_bank.c $(BUILD)/banks.txt &: $(BUILD)/bm_chars.o $(BUILD)/bm_spec.o $(TOOLS)/brawler/bank_pack.py
	python3 $(TOOLS)/brawler/bank_pack.py $(BUILD)
$(BUILD)/bm_chars_b.o: $(BUILD)/bm_chars.o $(BUILD)/bank_rename.txt
	m68k-linux-gnu-objcopy @$(BUILD)/bank_rename.txt $< $@
$(BUILD)/bm_spec_b.o: $(BUILD)/bm_spec.o $(BUILD)/bank_rename.txt
	m68k-linux-gnu-objcopy @$(BUILD)/bank_rename.txt $< $@
$(BUILD)/bm_bank.o: $(BUILD)/bm_bank.c
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD)/draw.o: draw.s
	$(CC) -m68000 -c $< -o $@

# --- Link ---
$(BUILD)/rom.elf: $(SDK)/lib/crt0.o $(BUILD)/main.o $(BUILD)/fighter.o $(BUILD)/ai.o $(BUILD)/sound.o $(BUILD)/draw.o $(BUILD)/bm_chars_b.o $(BUILD)/bm_spec_b.o $(BUILD)/bm_bank.o $(BUILD)/game_tables.o $(SDK)/lib/libneoscan.a
	$(LD) -T $(SDK)/boot/neoscan.ld $(SLOT_LDFLAGS) -o $@ $^

# --- Package ROM ---
$(ROM_NAME).zip: $(BUILD)/rom.elf $(BUILD)/rom_c1.bin $(BUILD)/font.s1 $(BUILD)/snd/m1.bin
	printf 'c1=$(BUILD)/rom_c1.bin\nc2=$(BUILD)/rom_c2.bin\ns1=$(BUILD)/font.s1\ndonor_m1=$(BUILD)/snd/m1.bin\ndonor_v1=$(BUILD)/snd/v1.bin\n' > $(BUILD)/manifest.txt
	python3 $(TOOLS)/neobuild_from_manifest.py $(BUILD)/manifest.txt --elf $(BUILD)/rom.elf --name $(ROM_NAME) -o $@

clean:
	rm -rf $(BUILD) $(ROM_NAME).zip $(ROM_NAME).neo roms/ hash/

# --- a character pack (make LAB_PACK=<f>): the shell first (its own make), then the slot's regions of this build ---
packs/$(LAB_PACK).pack: $(ROM_NAME).zip FORCE
	$(MAKE) LAB_SHELL=1 LAB_PACK=
	python3 $(TOOLS)/brawler/lab_pack.py make $(LAB_PACK) --shell build_shell lab-shell.neo --build $(BUILD) $(ROM_NAME).neo -o packs/$(LAB_PACK).pack

.PHONY: all clean publish publish-vps bump FORCE

# --- publish for the Android player's auto-fetch: brawler.neo + latest.json (build number, size, sha256) into DEST ---
publish: $(ROM_NAME).zip
	@test -z "$(LAB_FIGHTER)$(SLOT)" || (echo "a Lab build is never the Player's game"; exit 1)
	@test -n "$(DEST)" || (echo "make publish DEST=<dir served to the phone>"; exit 1)
	mkdir -p $(DEST)
	cp $(ROM_NAME).neo $(DEST)/$(ROM_NAME).neo.tmp && mv $(DEST)/$(ROM_NAME).neo.tmp $(DEST)/$(ROM_NAME).neo
	python3 -c "import hashlib, json, os, time; p = '$(DEST)/$(ROM_NAME).neo'; d = open(p, 'rb').read(); json.dump({'version': '$(VERSION)', 'build': int(time.time()), 'file': '$(ROM_NAME).neo', 'size': len(d), 'sha256': hashlib.sha256(d).hexdigest()}, open('$(DEST)/latest.json', 'w'))"
	cat $(DEST)/latest.json; echo

# --- publish to canneji.duckdns.org/brawler/download/ (the player's auto-fetch), with the Android APK when built ---
APK = ../../android/app/build/outputs/apk/debug/app-debug.apk
APKVER = $(shell sed -n 's/.*versionName = "\(.*\)".*/\1/p' ../../android/app/build.gradle.kts)   # the player's own version, not the game's
publish-vps: $(ROM_NAME).zip
	@test -z "$(LAB_FIGHTER)$(SLOT)" || (echo "a Lab build is never the Player's game"; exit 1)
	../../tools/brawler/publish_vps.sh $(ROM_NAME).neo $(VERSION)   # the game only: the player is published on its own (publish_vps.sh --apk-only)

# --- version (VERSION, 0.0.1 style, shown on the title screen): make bump = last number + 1 ---
bump:
	python3 -c "v = open('VERSION').read().split('.'); v[-1] = str(int(v[-1]) + 1); open('VERSION', 'w').write('.'.join(v) + '\\n')"
	cat VERSION
