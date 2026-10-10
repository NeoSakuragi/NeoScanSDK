/* The Character Lab's shell (make LAB_SHELL=1 / LAB_PACK=<f>; docs/character_lab.md "The pack format"): the SLOT
 * fighter's element of every per-fighter table comes from the pack, not from where the shell's linker put the table.
 *
 * A pack holds no address of the shell's code or tables: its regions are fixed by the pack format (the slot area at
 * LABHDR_AT .. 1 MB, its tiles, its voice samples) or relocated by the shell's anchor (its P2 bank, its HUD face, its
 * voice records). What the per-fighter tables (bm_chars[], bm_seg[], gblitz_rom[]...) hold for the slot is carried in
 * the slot HEADER at LABHDR_AT (tools/brawler/lab_pack.py seal writes it from the build's own tables): at power-on
 * lab_slot_init (main.c) copies each table into RAM and puts the header's element in the slot's place (the slot id and
 * its LAB special's fighter resolved to this shell's), so the shell's code and tables may move freely between builds.
 *
 * Included LAST by the engine's sources (main.c, fighter.c, ai.c): from here on the tables' names are the RAM copies.
 * Only Lab builds (-DLAB_SHELL); the Player's game never sees this. */
#ifndef LABSLOT_H
#define LABSLOT_H
#ifdef LAB_SHELL
#include "fighter.h"
#include "game_tables.h"

#define LAB_FORMAT  1          /* the pack format (lab_pack.py FORMAT): the header's layout, the tables' element sizes */
#define LABHDR_AT   0xE0000    /* the slot header (Makefile LABHDR_AT; lab_pack.py), then .labslot */
#define LAB_RT_MAX  96         /* gretime_rom rows the RAM copy holds (the shell's rows + the slot's 16 + the end row) */

extern bchar_t lab_bm_chars[BC_COUNT];
extern bseg_t lab_bm_seg[BC_COUNT];
extern bair_t lab_bm_air[BC_COUNT];
extern bair_t lab_bm_hsnd[BC_COUNT];
extern bxthr_t lab_bm_xthr[BC_COUNT];
extern bhspark_t lab_bm_hspark[BC_COUNT];
extern int8_t lab_bm_head[BC_COUNT][2];
extern uint8_t lab_ai_ready[BC_COUNT][2];
extern uint8_t lab_gblitz_rom[BC_COUNT][4];
extern uint8_t lab_gblitz_can[BC_COUNT][4];
extern const uint8_t *lab_grun_bob[BC_COUNT];
extern const uint8_t *lab_grun_dash[BC_COUNT];
extern uint8_t lab_gfury_area[BC_COUNT][3];
extern int32_t lab_gwalk_rom[BC_COUNT];
extern uint8_t lab_pb_of_fighter[BC_COUNT];
extern uint8_t lab_roster_unlock[BC_COUNT];
extern const uint16_t *lab_dtier_rom[BC_COUNT];
extern const gknob_t *lab_gknob_rom[BC_COUNT];
extern const gkcat_t *lab_gkcat_rom[BC_COUNT];
extern blab_t lab_bm_lab;
extern gretime_t lab_gretime_rom[LAB_RT_MAX];
extern uint16_t lab_portrait_pal[BC_COUNT][16];
extern uint8_t lab_slot_ok;    /* 1: the header was taken (0: the shell's own tables for the slot, its header refused) */
void lab_slot_init(void);
#endif
#endif

/* the names -> the RAM copies (main.c defines the copies first, with LABSLOT_NO_REMAP, then includes this again) */
#if defined(LAB_SHELL) && !defined(LABSLOT_NO_REMAP) && !defined(LABSLOT_REMAP)
#define LABSLOT_REMAP

#define bm_chars      lab_bm_chars
#define bm_seg        lab_bm_seg
#define bm_air        lab_bm_air
#define bm_hsnd       lab_bm_hsnd
#define bm_xthr       lab_bm_xthr
#define bm_hspark     lab_bm_hspark
#define bm_head       lab_bm_head
#define ai_ready      lab_ai_ready
#define gblitz_rom    lab_gblitz_rom
#define gblitz_can    lab_gblitz_can
#define grun_bob      lab_grun_bob
#define grun_dash     lab_grun_dash
#define gfury_area    lab_gfury_area
#define gwalk_rom     lab_gwalk_rom
#define pb_of_fighter lab_pb_of_fighter
#define roster_unlock lab_roster_unlock
#define dtier_rom     lab_dtier_rom
#define gknob_rom     lab_gknob_rom
#define gkcat_rom     lab_gkcat_rom
#define bm_lab        lab_bm_lab
#define gretime_rom   lab_gretime_rom
#ifdef PORTRAIT_TILE           /* (hud.h: main.c only) */
#define portrait_pal  lab_portrait_pal
#endif
#endif
