/* Brawler POC: Final Fight style beat 'em up on KOF data (fighter.c), character select then the fight.
 * P1 / P2: stick = walk on the floor (up/down = depth), double tap forward = run, A punch, B kick, C jump, D special.
 * Combo routes: AAA, AAB, BB, BAB, finishers forward+A / down+B; air A / B. Two dummy enemies (Terry's other colour sets).
 * HUD: P1 state and combo link, P1's target (fighter number, life), CPU = worst frame of the last 16 (crt0 counts idle spins of 54 cycles;
 * a frame is 202,752 cycles at 12 MHz, so idle % = spins * 54 / 2027.52 ~ spins * 7 / 256), LAG n = the frames dropped over
 * those 16 ticks (ticks that overran: CPU never shows them). */
#include <neoscan.h>
#include "neo_internal.h"
#include "fighter.h"
#include "ai.h"
#include "stage.h"
#include "land.h"
#include "sound.h"
#include "banner.h"
#include "sparks.h"
#include "superflash.h"
#include "throwfx.h"
#include "hud.h"
#include "game_tables.h"
#include "portraits_big.h"
#include "staff_roll.h"
#include "bm_wins.h"
#include "bonus.h"
#include "referee.h"
#include "bigfont.h"
#ifdef LAB_SHELL
#define LABSLOT_NO_REMAP
#include "labslot.h"
/* ---- the Character Lab's slot (labslot.h; docs/character_lab.md "The pack format") --------------------------------
 * The shell's ANCHOR (LABANCHOR_AT, the Makefile's; lab_pack.py seal fills it after the link: the shell's format,
 * features, where its relocatable slot regions are, the RAM map and the layout the Player / the pages read) and the slot
 * HEADER (LABHDR_AT, the pack's: the slot's element of every per-fighter table). Reserved here as plain bytes the
 * compiler knows nothing about (no constant folding of the zeros the link leaves in them). */
__asm__(".section .labanchor,\"a\"\n.globl lab_anchor\nlab_anchor: .space 0x4000\n"
        ".section .labhdr,\"a\"\n.globl lab_hdr\nlab_hdr: .space 0x400\n.text");
extern const uint8_t lab_hdr[];
bchar_t lab_bm_chars[BC_COUNT];
bseg_t lab_bm_seg[BC_COUNT];
bair_t lab_bm_air[BC_COUNT];
bair_t lab_bm_hsnd[BC_COUNT];
bxthr_t lab_bm_xthr[BC_COUNT];
bhspark_t lab_bm_hspark[BC_COUNT];
int8_t lab_bm_head[BC_COUNT][2];
uint8_t lab_ai_ready[BC_COUNT][2];
uint8_t lab_gblitz_rom[BC_COUNT][4];
uint8_t lab_gblitz_can[BC_COUNT][4];
const uint8_t *lab_grun_bob[BC_COUNT];
const uint8_t *lab_grun_dash[BC_COUNT];
uint8_t lab_gfury_area[BC_COUNT][3];
int32_t lab_gwalk_rom[BC_COUNT];
uint8_t lab_pb_of_fighter[BC_COUNT];
uint8_t lab_roster_unlock[BC_COUNT];
const uint16_t *lab_dtier_rom[BC_COUNT];
const gknob_t *lab_gknob_rom[BC_COUNT];
const gkcat_t *lab_gkcat_rom[BC_COUNT];
blab_t lab_bm_lab;
gretime_t lab_gretime_rom[LAB_RT_MAX];
uint16_t lab_portrait_pal[BC_COUNT][16];
uint8_t lab_slot_ok;
const bvslot_t *lab_vslot;
uint8_t lab_vmap[LAB_VMAP_MAX];
/* the slot's victim side (vthrow.h bvslot_t, the header's word at +12, an address in .labslot): its fighter ids
   resolved to this shell's by their keys (bm_rkey); none (0, or not a VSLT block): the script's rows */
static void lab_vslot_init(const uint8_t *h) {
    const uint32_t a = (uint32_t)h[12] << 24 | (uint32_t)h[13] << 16 | h[14] << 8 | h[15];
    const bvslot_t *s = (const bvslot_t *)a;
    uint8_t i, j;
    lab_vslot = 0;
    for (i = 0; i < LAB_VMAP_MAX; i++) lab_vmap[i] = 0xFF;
    if (a < LABSLOT_AT || a >= 0x100000 || (a & 1) || s->magic != VSLOT_MAGIC || s->nkey > LAB_VMAP_MAX) return;
    for (i = 0; i < s->nkey; i++)
        for (j = 0; s->keys[i] && j < BC_COUNT - 1; j++)
            if (bm_rkey[j] == s->keys[i]) { lab_vmap[i] = j; break; }
    lab_vslot = s;
}
/* the header's tables, in lab_pack.py HDR_ARRAYS order: each [u16 element size][the slot's element] (even), then
   [u16 sizeof blab_t][bm_lab], then the slot's retime rows (gretime_t, its 16) */
static const struct { void *ram; const void *rom; uint16_t esz; } lab_arrs[] = {
    { lab_bm_chars, bm_chars, sizeof bm_chars[0] }, { lab_bm_seg, bm_seg, sizeof bm_seg[0] },
    { lab_bm_air, bm_air, sizeof bm_air[0] }, { lab_bm_hsnd, bm_hsnd, sizeof bm_hsnd[0] },
    { lab_bm_xthr, bm_xthr, sizeof bm_xthr[0] }, { lab_bm_hspark, bm_hspark, sizeof bm_hspark[0] },
    { lab_bm_head, bm_head, sizeof bm_head[0] }, { lab_ai_ready, ai_ready, sizeof ai_ready[0] },
    { lab_gblitz_rom, gblitz_rom, sizeof gblitz_rom[0] }, { lab_gblitz_can, gblitz_can, sizeof gblitz_can[0] },
    { lab_grun_bob, grun_bob, sizeof grun_bob[0] }, { lab_grun_dash, grun_dash, sizeof grun_dash[0] },
    { lab_gfury_area, gfury_area, sizeof gfury_area[0] }, { lab_gwalk_rom, gwalk_rom, sizeof gwalk_rom[0] },
    { lab_pb_of_fighter, pb_of_fighter, sizeof pb_of_fighter[0] }, { lab_roster_unlock, roster_unlock, sizeof roster_unlock[0] },
    { lab_dtier_rom, dtier_rom, sizeof dtier_rom[0] }, { lab_portrait_pal, portrait_pal, sizeof portrait_pal[0] },
    { lab_gknob_rom, gknob_rom, sizeof gknob_rom[0] }, { lab_gkcat_rom, gkcat_rom, sizeof gkcat_rom[0] },
};
#define LAB_NARR (sizeof lab_arrs / sizeof lab_arrs[0])
static void lab_copy(void *to, const void *from, uint16_t n) { uint8_t *d = to; const uint8_t *s = from; while (n--) *d++ = *s++; }
/* power-on / every reset (a pack swap resets): the tables into RAM, the slot's element of each from the header */
void lab_slot_init(void) {
    const uint8_t *h = lab_hdr, *p;
    const uint8_t sid = BC_COUNT - 1;
    uint16_t k, n, nrt;
    for (k = 0; k < LAB_NARR; k++) lab_copy(lab_arrs[k].ram, lab_arrs[k].rom, lab_arrs[k].esz * BC_COUNT);
    lab_copy(&lab_bm_lab, &bm_lab, sizeof lab_bm_lab);
    for (n = 0; gretime_rom[n].fighter != 0xFF; n++) {}       /* the ROM's rows (+ the end row) */
    lab_slot_ok = 0; lab_vslot = 0;
    if (n + 1 > LAB_RT_MAX || n < 16) { lab_copy(lab_gretime_rom, gretime_rom, sizeof(gretime_t)); lab_gretime_rom[0].fighter = 0xFF; return; }
    lab_copy(lab_gretime_rom, gretime_rom, (n + 1) * sizeof(gretime_t));
    if (h[0] != 'N' || h[1] != 'G' || h[2] != 'S' || h[3] != 'H' || (h[4] << 8 | h[5]) != LAB_FORMAT ||
        (h[6] << 8 | h[7]) != LAB_NARR + 1) return;           /* not this format: the shell's own slot tables */
    nrt = h[9];
    for (k = 0, p = h + 16; k < LAB_NARR; k++) {               /* every element's size first: nothing taken unless all fit */
        if ((p[0] << 8 | p[1]) != lab_arrs[k].esz) return;
        p += 2 + ((lab_arrs[k].esz + 1) & ~1);
    }
    if ((p[0] << 8 | p[1]) != sizeof(blab_t) || nrt != 16) return;
    for (k = 0, p = h + 16; k < LAB_NARR; k++) {
        lab_copy((uint8_t *)lab_arrs[k].ram + sid * lab_arrs[k].esz, p + 2, lab_arrs[k].esz);
        p += 2 + ((lab_arrs[k].esz + 1) & ~1);
    }
    lab_copy(&lab_bm_lab, p + 2, sizeof(blab_t)); p += 2 + ((sizeof(blab_t) + 1) & ~1);
    lab_copy(&lab_gretime_rom[n - 16], p, 16 * sizeof(gretime_t));   /* the slot's rows: the last 16 before the end */
    for (k = n - 16; k < n; k++) if (lab_gretime_rom[k].fighter != 0xFE) lab_gretime_rom[k].fighter = sid;
    lab_bm_chars[sid].id = sid;                                /* the ids: this shell's */
    if (lab_bm_lab.fighter != 0xFF) lab_bm_lab.fighter = sid;
    lab_vslot_init(h);
    lab_slot_ok = 1;
}
#undef LABSLOT_NO_REMAP
#include "labslot.h"                                         /* from here on: the RAM tables */
#endif

static uint16_t TEXT_PAL[16] = { 0x8000, COLOR_WHITE };   /* 2-5: the font's gradient, 6-15: life bar (hud.h text_colours / bar_colours; 14 = the font's shadow) */
#ifndef GAME_VERSION
#define GAME_VERSION "0.0.0"
#endif
#ifndef AI_OFF
#define AI_OFF 0                     /* 1: enemies stand still (test builds: make AI_OFF=1) */
#endif
#ifndef PROFILE_HUD
#define PROFILE_HUD 0                /* 1: the per-section profiler and the AI counters on the right (make PROFILE=1) */
#endif
extern volatile uint32_t wait_cycles;

/* Profiler: the LSPC raster line counter ($3C0006 bits 15-7, lines $F8-$1FF, 264 per frame) is the clock; 1 line =
 * 768 68000 cycles. prof[] holds the worst line count of each section over the last 16 frames. */
#define LINE() ((*(volatile uint16_t *)0x3C0006) >> 7)
enum { P_FLUSH, P_AI, P_UPDATE, P_COMBAT, P_SORT, P_TILES, P_GUARD, P_PLACE, P_HUD, P_N };
#if PROFILE_HUD
static uint16_t prof[P_N], prof_max[P_N], prof_t;
static void mark(uint8_t sec) {
    uint16_t now = LINE(), d = now >= prof_t ? now - prof_t : now + 264 - prof_t;
    if (d > prof[sec]) prof[sec] = d;
    prof_t = now;
}
#define PROF_START() (prof_t = LINE())
#else
#define mark(sec) ((void)0)          /* (a normal build: the section clock is compiled out, cpu budget G) */
#define PROF_START() ((void)0)
#endif

#define NF 8                         /* 2 players + 6 enemies: the POC target */
#define NE (NF + NPJ)                /* entities drawn: fighters + projectiles */
#define FIGHT_SPRS (NF * MAX_COLS + NPJ * PJ_COLS)   /* a fight's blocks: a fighter's MAX_COLS, the projectile pool's
                                        PJ_SPRS = NPJ * PJ_COLS shared by width (block_w) */
#define NA 25                        /* sprite blocks: NE in a fight, NA actors on the select screen (a block per roster
                                        fighter: the group photo); 25 = the most the select screen's sprites hold
                                        (SEL_SPR 57 + 25 x 12 + the barriers' 21 = 378 of 381; build_tables.MAX_SLOTS,
                                        the Factory's Roster & select: LB2's Moriya the 25th, 2026-10-12) */
#define SEL_COLS 12                  /* sprites per block on the select screen (MAX_COLS in a fight): NA blocks of 12 =
                                        sprites SEL_SPR 57-344 there (16 until NA 20, Billy Lee; 15 until NA 21, Genjuro; NA 22:
                                        Kuroko; 14 at NA 23: SS2's Hanzo; 13 at NA 24: Rosa, TODO #213; 12 with the Neo Geo
                                        Land behind them (2026-10-09): its far layer, lights, facade and crowd in 1-56, its
                                        barriers in 345-365) (the banner's, the debug boxes', the sparks' and the throw effect's 300-379
                                        are not in use on that screen: sparks_draw / tfx_draw return there); the watch /
                                        win poses and the walk-offs are narrower (2026-10-07, build/bm_chars.c ncols of every
                                        selectable fighter's BA_WATCH / BA_WIN / BA_WALK_FWD frames: widest 11, Haohmaru's
                                        watch and Genjuro's win; Rosa 7 / 9 / 9) */
uint8_t blk_cols = MAX_COLS;         /* sprites per block now (draw.s fighter_tiles clips a frame to it) */
/* palettes: 0-15 text and fix portraits; the select screen: its actors back to back from 16 at their fighters' own counts
 * (game_tables sel_palbase, SEL_NPAL in all), the Neo Geo Land's SNK palettes LAND_PAL .. (land.h, up to SFX_PAL); a fight:
 * the fighters from 16 (MAX_PALS each), its stage's from STAGE_PAL; KOF's shared effects SFX_PAL ..; the big portraits
 * PB_PALN 240-249 (248-249 shared with the super flash: a drama never runs during one); 248+ the flash, shadows, sparks */
_Static_assert(16 + SEL_NPAL <= LAND_PAL && LAND_PAL + LAND_NPAL <= SFX_PAL && 16 + NF * MAX_PALS <= STAGE_PAL &&
               STAGE_PAL + STAGE_MAXPAL <= SFX_PAL && SFX_PAL + SFX_NPAL_MAX <= 240,
               "palettes: the select screen's actors, the Neo Geo Land, the stages, KOF's shared effects (TODO #214), the big portraits (PB_PALN)");
#define SPR_BASE 59                  /* fighter blocks (stage 22-42, shadows 43-58 behind them; 1-21 free) (60 until
                                        NA 23, TODO #193: SH_SPR + NE = 59 is the lowest it can be) */
/* the select screen's sprites (main.c "the select screen's backdrop"): the Neo Geo Land's far layer, its lights, the
 * facade + street ring and the crowd ring behind the actors, the actors' blocks from SEL_SPR, the barriers' ring in front */
#define LAND_RING      21                                   /* a scrolling layer's sprites: 320 / 16 + 1 */
#define LAND_TOP_SPR   1
#define LAND_LT_SPR    (LAND_TOP_SPR + LAND_TOP_COLS)
#define LAND_MAIN_SPR  (LAND_LT_SPR + LAND_LIGHTS_COLS)
#define LAND_MID_SPR   (LAND_MAIN_SPR + LAND_RING)
#define SEL_SPR        (LAND_MID_SPR + LAND_RING)           /* 57 */
#define LAND_FRONT_SPR (SEL_SPR + NA * SEL_COLS)            /* 345 */
_Static_assert(SEL_SPR <= SPR_BASE && LAND_FRONT_SPR + LAND_RING <= 381, "the select screen's sprites: the land's, the actors' blocks, the barriers");
static fighter_t fighters[NF];
static fighter_t *order[NA];                     /* back (small Z) to front, the nf entities in play */
static uint8_t nf;                               /* entities in play: the previews on the select screen, NE in the fight */
static uint8_t mode;                             /* 0 select, 1 fight, 2 title, 3 BOSS UNLOCKED, 4 the ending, 5 GAME OVER,
                                                    6 the bonus screens, 7 the unlock ladder (MODE_LADDER) */
#define MODE_LADDER 7
static uint8_t attract;                          /* the fight is the attract demo: P1 is ai_bot, enemies their attract_ai */
static uint16_t attract_t;
static uint8_t tap_t[2], tap_dir[2];             /* double-tap run detection per player */
static uint8_t bz_x[2][2], bz_xa[2][2], bz_z[2][2], bz_za[2][2];   /* the Blitz (read_player): per player the last two taps
                                                    of each axis (x: 1 right 2 left, z: 1 down 2 up) and their ages */
static uint8_t ab_age[2][2];                     /* A+B = C (read_player): frames since A / B was pressed */
enum { PH_WAVE, PH_GO, PH_BOSS, PH_END, PH_CLEAR };   /* campaign phases (see "campaign") */
static uint8_t phase;
enum { BN_OFF, BN_PICK, BN_PLAY, BN_END, BN_INTRO, BN_CARD };           /* the bonus stages (see "bonus stages"): bonus_on; bn_won = bit per
                                                          game won this credit; sh_n = the entities shadows() handles */
static uint8_t bonus_on, bn_won, sh_n = NE;
static uint8_t bn_clr[GB_MAX_GAMES];     /* passes of each bonus game this credit (gbonus_game_t.pass_chunks: the reward by clear) */

/* ---- SNK MVS conventions: the game (not the BIOS) shows "LEVEL-n" and "CREDIT nn" on the bottom line. LEVEL = the
 * DIFFICULTY setting of the soft DIP table below (BIOS game menu; value at BIOS RAM $10FD84 + 6, 0-7); CREDIT = P1's
 * credits in backup RAM ($D00034, BCD). ---- */
const uint8_t soft_dip[] = {
    'B','R','A','W','L','E','R',' ','\'','2','7',' ',' ',' ',' ',' ',   /* 16-byte name */
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,                                 /* no timers, no counters */
    0x38, 0, 0, 0, 0, 0, 0, 0, 0, 0,                                    /* DIFFICULTY: 8 choices, default 4 */
    'D','I','F','F','I','C','U','L','T','Y',' ',' ',
    'L','E','V','E','L',' ','1',' ',' ',' ',' ',' ',  'L','E','V','E','L',' ','2',' ',' ',' ',' ',' ',
    'L','E','V','E','L',' ','3',' ',' ',' ',' ',' ',  'L','E','V','E','L',' ','4',' ',' ',' ',' ',' ',
    'L','E','V','E','L',' ','5',' ',' ',' ',' ',' ',  'L','E','V','E','L',' ','6',' ',' ',' ',' ',' ',
    'L','E','V','E','L',' ','7',' ',' ',' ',' ',' ',  'L','E','V','E','L',' ','8',' ',' ',' ',' ',' ',
};
#define BIOS_GAME_DIP ((volatile uint8_t *)0x10FD84)
#define CREDITS_P1    (*(volatile uint8_t *)0xD00034)
#define CREDITS_P2    (*(volatile uint8_t *)0xD00035)   /* SNK's MVS BIOS: P2's own (coin slot 2); UniBIOS shares P1's */
/* difficulty 0-3 (EASY NORMAL HARD MANIAC): enemies' and bosses' life x0.5 x1 x1.5 x2 (`life`). Arcade (MVS): the soft
 * DIP's LEVEL 1-8 in pairs (1-2 EASY, 3-4 NORMAL = the default LEVEL-4, 5-6 HARD, 7-8 MANIAC), set by the operator in
 * the BIOS game settings; console (AES): the OPTIONS screen, kept in the save (memory card), shown as LEVEL-2/4/6/8 */
static uint8_t difficulty = 1;                           /* AES: save.difficulty (save_load, the OPTIONS screen) */
static uint8_t level(void) {
    uint8_t l = BIOS_GAME_DIP[6];
    if (!BIOS_MVS_FLAG) return (difficulty << 1) + 2;
    return l > 7 ? 4 : l + 1;
}
static uint8_t diff(void) { return BIOS_MVS_FLAG ? (level() - 1) >> 1 : difficulty; }
static int16_t life(int16_t b) {                         /* a spawn's life at this difficulty: shifts and adds only */
    switch (diff()) { case 0: return b >> 1; case 2: return b + (b >> 1); case 3: return b << 1; }
    return b;
}
/* the coin sound (TODO #199): KOF94's $7F (SSG cue COIN, songs.json), sent by KOF94 at every credit; here whenever
 * a player's credit count goes up (MVS: the BIOS counts the coins in backup RAM), on every screen; a coin taken while
 * the BIOS ran (the attract demo's coin: request 3) sounds once the title's song started (game_enter) */
static uint8_t seen_credits[2];
static uint8_t coin_in(void) {                                /* 1: a credit came in since the last call */
    uint8_t c1 = CREDITS_P1, c2 = CREDITS_P2, up;
    if (!BIOS_MVS_FLAG) return 0;
    up = c1 > seen_credits[0] || c2 > seen_credits[1];         /* (BCD: the byte order is the count's) */
    seen_credits[0] = c1; seen_credits[1] = c2;
    return up;
}
static uint8_t shown_level, shown_credits;               /* 0 / 0xFF after a FIX_clear: rewrite */
static void arcade_line_reset(void) { shown_level = 0; shown_credits = 0xFF; }
static void arcade_line(void) {                               /* bottom line, every screen; writes only changes */
    uint8_t l = level(), c = CREDITS_P1;
    char t[3];
    if (l != shown_level) {
        FIX_print(1, 27, "V" GAME_VERSION, 0);                /* the build (VERSION): the bottom-left corner (TODO #167) */
        FIX_print(16, 27, "LEVEL-", 0); t[0] = '0' + l; t[1] = 0; FIX_print(22, 27, t, 0); shown_level = l;
    }
    if (c != shown_credits) {
        FIX_print(28, 27, "CREDIT", 0);
        t[0] = '0' + (c >> 4); t[1] = '0' + (c & 15); t[2] = 0; FIX_print(35, 27, t, 0); shown_credits = c;
    }
}

/* ---- stages (tools/brawler/make_stage_ra.py: Robo Army's horizontal parts, placeholders; stage.h stages[]): one at a
 * time, stage_init(n) at each stage start (the campaign's gstages[].bg; the attract demo: STAGE, make STAGE=n). One plane of 21 sprites (22-42), a
 * ring: sprite s shows the plane column c with c mod 21 = s, so scrolling rewrites one column's tiles when a new one
 * comes into view; X of all 21 is one run per frame. stg->rows tiles from screen y stg->y, at the camera (Robo Army has
 * no parallax); above it the backdrop (stg->backdrop, Robo Army's black). Palettes STAGE_PAL .. STAGE_PAL + stg->npal - 1
 * (the tile words carry them and their tile bits 16-19), loaded by stage_init; some tiles are LSPC auto-animated
 * (attribute bits 2-3, speed stg->lspcmode as Robo Army). The walkable band starts at stg->floor_top (floor_top), the
 * world is stg->cols * 16 px wide (world_w). Behind the fighters. Sprites 1-21 are free. ---- */
#ifndef STAGE
#define STAGE 0                                  /* the stage the attract demo plays (make STAGE=n) */
#endif
_Static_assert(STAGE < STAGE_COUNT, "make STAGE=n: no such stage");
#define SELECT_FLOOR 158                         /* the select screen's floor (no stage there) */
#define BG_SPR 22
#define BG_N   21
static uint8_t bg_shown[BG_N];
/* (CPU budget D, the stage's share) the plane's tiles and X words depend on the camera only: stage_draw rewrites them
 * when cam_x moved since the last fight frame; another screen (draw outside mode 1, the bonus screens' sprites 1-116), a
 * new stage (stage_use) or the BIOS's (game_enter) clear bg_ok */
static int16_t bg_cam;
static uint8_t bg_ok;
int16_t cam_x;                                    /* (fighter.h: P_WARP's screen mode reads it) */
static int16_t lock_x;                    /* lock_x: how far right the camera may go now (campaign) */
static const stage_t *stg = &stages[STAGE];
int16_t floor_top = SELECT_FLOOR, world_w;

static uint8_t cyc_t, cyc_k;                    /* the stage's palette cycle: frames left on this step, the step */
static void stage_pals(void) {                               /* the stage's palettes */
    uint8_t p;
    for (p = 0; p < stg->npal; p++) PAL_setPalette(STAGE_PAL + p, stg->pal + p * 16);
    cyc_t = stg->cyc_ticks; cyc_k = 0;
    if (stg->cyc_pal != 0xFF) PAL_setPalette(STAGE_PAL + stg->cyc_pal, stg->cyc);
}
static void stage_cycle(void) {      /* Robo Army's palette cycle (make_stage_ra.py cycles, TODO #159): the next step */
    if (stg->cyc_pal == 0xFF || --cyc_t) return;
    cyc_t = stg->cyc_ticks;
    if (++cyc_k == stg->cyc_n) cyc_k = 0;
    PAL_setPalette(STAGE_PAL + stg->cyc_pal, stg->cyc + cyc_k * 16);
}
static uint8_t bd_on, bd_t;                      /* screen_fx: the stage hidden for a special's effect; its frames */
/* the backdrop ($401FFE, TODO #217): every change in the game goes through bd_set and is written by vblank_flush,
 * right after the VRAM queue in vblank. Written at once (mid-frame: game_tick runs into the active display) the frame
 * showed the old colour above that line and the new one below it (Kim's Phoenix strobe: half red / half white) */
static uint16_t bd_next;
static uint8_t bd_pend;
static void bd_set(uint16_t c) { bd_next = c; bd_pend = 1; }
static const uint16_t *bt_pal_next;              /* the big text's palette to write in vblank (bt_pal: its blink's white
                                                    frame, note 20261016-133635-e03d round 2; written at once it changed
                                                    mid-frame and the next tick put it back before a whole frame showed it) */
static void vblank_flush(void) {
    SYS_vblankFlush();
    if (bd_pend) { PAL_setBackdrop(bd_next); bd_pend = 0; }
    if (bt_pal_next) { PAL_setPalette(250, bt_pal_next); bt_pal_next = 0; }   /* (BT_PAL) */
}
static void land_off(void);
static void stage_off(void) {                               /* the stage's sprites hidden, the stage kept (a screen
                                                                effect's backdrop: its floor edge stays, note
                                                                20261016-162209-e03d: a super flash dropped it) */
    uint8_t i;
    for (i = 0; i < BG_N; i++) cmd_push(VRAM_SCB3 + BG_SPR + i, 0);
}
static void stage_hide(void) {                              /* title, select: no stage (nor the select's Neo Geo Land) */
    bd_on = 0;
    land_off();
    zback = 0;                                                      /* (no stage: no floor edge) */
    stage_off();
}
static void stage_show(void) {
    uint8_t s;
    for (s = 0; s < BG_N; s++) cmd_push(VRAM_SCB3 + BG_SPR + s, ((496 - stg->y) << 7) | stg->rows);
}
static void stage_use(const stage_t *st, const uint8_t *zb) {   /* a stage (stage.h) or a bonus scene (bonus.h) */
    uint8_t s;
    bd_on = 0; bighit_red = bighit_slow = 0; hitflash = 0;
    land_off();                                                     /* from the select screen: its land's sprites go */
    stg = st; floor_top = stg->floor_top; world_w = stg->cols << 4;
    zback = zb; zback_n = (uint8_t)stg->cols;                     /* the floor's back edge (game.json depth; 0: none) */
    stage_pals();
    *(volatile uint16_t *)0x3C0006 = stg->lspcmode;                /* REG_LSPCMODE: auto-animation speed */
    for (s = 0; s < BG_N; s++) {
        cmd_push(VRAM_SCB2 + BG_SPR + s, 0x0FFF);
        cmd_push(VRAM_SCB3 + BG_SPR + s, ((496 - stg->y) << 7) | stg->rows);
        bg_shown[s] = 0xFF;
    }
    bg_ok = 0;
}
static void stage_init(uint8_t n) { stage_use(&stages[n], gback_rom[n]); }
static void stage_draw(void) {
    uint8_t first = (uint8_t)(cam_x >> 4), s = first, k, r, n = stg->rows * 2;
    uint16_t *x, *w;
    stage_cycle();
    if (bg_ok && cam_x == bg_cam) return;
    bg_ok = 1; bg_cam = cam_x;
    x = cmd_run(VRAM_SCB4 + BG_SPR, BG_N);
    while (s >= BG_N) s -= BG_N;
    for (k = 0; k < BG_N; k++) {
        uint8_t c = first + k;
        if (c >= stg->cols) { x[s] = 320 << 7; }                          /* past the end: off screen */
        else {
            if (bg_shown[s] != c) {
                const uint16_t *t = stg->map + c * n;
                w = cmd_run(VRAM_SCB1 + (BG_SPR + s) * 64, n);
                for (r = 0; r < n; r++) *w++ = *t++;
                bg_shown[s] = c;
            }
            x[s] = (uint16_t)(((c << 4) - cam_x) & 0x1FF) << 7;
        }
        if (++s == BG_N) s = 0;
    }
}
/* the camera never moves vertically (TODO #185, Bruno 2026-10-07: "Why is the camera going up? That is weird."): the
 * 0.0.91 rise during furies is gone; a move that goes high fits the fixed framing itself (Genjuro's spin: its carry
 * height, handlers_ss2 gen_wft) */
/* camera: toward the players' midpoint, 4 px a frame at most, inside the stage; players stay in view */
static uint8_t in_play(const fighter_t *f) { return f->state != S_OFF; }
static void camera(void) {
    uint8_t p, n = 0;
    int16_t sum = 0, goal;
    for (p = 0; p < 2; p++) if (in_play(&fighters[p])) { sum += INT(fighters[p].x); n++; }
    if (!n) return;
    goal = (n == 2 ? sum >> 1 : sum) - 160;
    if (goal < cam_x) goal = cam_x;                          /* never back (Streets of Rage) */
    if (goal > lock_x) goal = lock_x;                        /* the campaign's lock point (stage end at most) */
    if (goal > cam_x + 4) goal = cam_x + 4;
    if (goal < cam_x - 4) goal = cam_x - 4;
    cam_x = goal;
    for (p = 0; p < 2; p++) {
        fighter_t *f = &fighters[p];
        if (f->inb == INB_LEAVE) continue;                   /* (walking off the screen: main.c clear_walk "off") */
        if (f->x < FIX(cam_x + 16)) f->x = FIX(cam_x + 16);
        if (f->x > FIX(cam_x + 304)) f->x = FIX(cam_x + 304);
    }
}

/* Neo Geo draws higher sprite numbers on top: fighters further back get the lower blocks. A fighter whose block changed
 * gets its tiles rewritten into the new block (the position pass covers every block every frame, so nothing to hide). */
static uint8_t block_placed[NA];                 /* columns each sprite block showed last frame */
static uint16_t block_spr[NA];                   /* where it showed them (a block's place moves with the widths before it) */
static uint16_t slot_spr[NA];                    /* each depth slot's first sprite this frame (depth_sort) */
/* (CPU budget D, docs/brawler_cpu_budget.md) what each block's SCB3 / SCB4 words were last written from: draw rewrites a
 * block only when one of these changed: its entity, fighter_place's inputs (the frame shown + facing, its screen x and
 * feet y: x - cam_x, floor_top + z - y) and its sprites (first, count); the columns' trims come with the frame, so a
 * frame rewritten in place (shown_frame 0xFFFF before the tiles: thinned, re-clipped, a new form) is never kept
 * (blk_new). Only in a fight (mode 1, no Neo Geo Land); any other screen, or anything that writes the blocks' sprites
 * itself (blocks_layout, the bonus screens), resets it: blk_key_reset */
static const fighter_t *bk_f[NA];
static uint32_t bk_pos[NA], bk_frm[NA], bk_sm[NA];
static uint8_t blk_new[NA];                      /* per entity (idx): its tiles were rewritten from 0xFFFF this tick */
static void blk_key_reset(void) { uint8_t i; for (i = 0; i < NA; i++) bk_f[i] = 0; }
/* a block's width: in a fight a fighter's MAX_COLS; a projectile / effect entity's the widest projectile or effect frame
 * of its thrower's character (pj_cols: measured from the data at boot) while it is in use, 0 when free, so the pool's
 * PJ_SPRS sprites go to the entities alive by their real widths (Kim's Phoenix flames 13, Rugal's / Haohmaru's 10,
 * Krauser's Blitz Ball and its 4 trails 5 each); an entity that would take the pool past PJ_SPRS gets no block this
 * frame (not drawn). On the select screen every actor's SEL_COLS (draw.s fighter_tiles clips to it) */
#define PJ_SPRS (NPJ * PJ_COLS)                  /* the projectile pool's sprites, shared by width: 80 */
static uint8_t pj_cols[BC_COUNT];                /* per character: its widest projectile / effect frame (pj_measure) */
static uint8_t pj_w[NPJ];                        /* per pool entity: its block this frame (0: free, or no room) */
static const bproj_t *pj_def[NPJ];               /* per pool entity: the definition pj_dw was measured for (TODO #214) */
static uint8_t pj_dw[NPJ];                       /* its widest frame (its definition's cols: the export's pj_scan of
                                                    its rows, end rows and trail) */
static uint8_t pj_scan(const bchar_t *c, const bproj_t *d) {   /* a projectile's rows, end rows and its trail's */
    uint8_t w = 0, k;
    for (; d; d = d->child) {
        for (k = 0; k < d->nrows; k++) if (d->rows[k].frame != 0xFFFF && c->frames[d->rows[k].frame].ncols > w) w = c->frames[d->rows[k].frame].ncols;
        if (d->end) for (k = 0; k < d->nend; k++) if (d->end[k].frame != 0xFFFF && c->frames[d->end[k].frame].ncols > w) w = c->frames[d->end[k].frame].ncols;
        if (d->child == d) break;
    }
    return w;
}
static void pj_measure(void) {
    uint8_t i, s, k, w;
    uint16_t r;
    for (i = 0; i < BC_COUNT; i++) {
        const bchar_t *c = &bm_chars[i];
        uint8_t m = 0, ob = BANK_set(CH_BANK(c));               /* its rows, programs, frames: its bank (fighter.h) */
        for (s = 0; s < c->nspec; s++) {
            const bspec_t *sp = &c->specials[s];
            for (r = 0; r < sp->nrows; r++)                  /* the script's objects (effects: Kim's flames) */
                for (k = 0; k < 2; k++) {
                    uint16_t fr = sp->rows[r].obj[k].frame;
                    if (fr != 0xFFFF && c->frames[fr].ncols > m) m = c->frames[fr].ncols;
                }
            for (k = 0; k < sp->nproj; k++) if ((w = pj_scan(c, &sp->proj[k])) > m) m = w;
            if (sp->prog) {                                  /* a ROM special's objects: its P_SPAWNs */
                const bprim_t *p;
                for (p = sp->prog; p->op != P_END; p++) if (p->op == P_SPAWN && (w = pj_scan(c, &sp->robj[p->a])) > m) m = w;
            }
        }
        if (bm_hspark[i].map) {                              /* its source's hit sparks (TODO #215): each kind once */
            const uint8_t *e;
            uint8_t n = 0;
            for (e = bm_hspark[i].map; *e != 0xFF; e += 4) if ((e[3] & 0x3F) > n) n = e[3] & 0x3F;
            for (k = 0; k < n; k++) if ((w = pj_scan(c, &bm_hspark[i].sparks[k])) > m) m = w;
        }
        if (bm_wins[i].obj) {                                /* its win poses' step effects (bm_wins fx) */
            const uint8_t *e;
            for (e = bm_wins[i].fx; *e != 0xFF; e += 3) if ((w = pj_scan(c, &bm_wins[i].obj[e[2]])) > m) m = w;
        }
        pj_cols[i] = m > MAX_COLS ? MAX_COLS : m;
        BANK_set(ob);
    }
    for (i = 0; i < NPJ; i++) projectiles[i].idx = NF + i;   /* block_w's index (also set by the fight's setup) */
}
static uint8_t block_w(const fighter_t *f) {
    if (blk_cols != MAX_COLS || f < projectiles || f >= projectiles + NPJ) return blk_cols;
    return pj_w[f->idx - NF];                    /* (idx: a pointer difference would divide by sizeof) */
}
/* the select screen's NA actors need narrower blocks than a fight's NE entities (SEL_COLS / MAX_COLS sprites): a change
 * of width hides every block's sprites once (SCB3 height 0) and re-places the blocks from scratch */
#define BLK_END (SEL_SPR + NA * SEL_COLS > SPR_BASE + FIGHT_SPRS ? SEL_SPR + NA * SEL_COLS : SPR_BASE + FIGHT_SPRS)
static void blocks_layout(uint8_t cols) {                    /* (the select's blocks start at SEL_SPR, a fight's at SPR_BASE) */
    uint16_t i, *y;
    if (cols == blk_cols) return;
    blk_cols = cols;
    y = cmd_run(VRAM_SCB3 + SEL_SPR, BLK_END - SEL_SPR);
    for (i = 0; i < BLK_END - SEL_SPR; i++) y[i] = 0;
    for (i = 0; i < NA; i++) block_placed[i] = 0;
    blk_key_reset();
}
static uint8_t sel_rank[NA];                     /* the select screen: each actor's draw order (SEL_SLOT z, 0 the back) */
static int32_t depth(const fighter_t *f) { return nf > NE ? sel_rank[f->idx] : f->z; }   /* the select: its layout's order */
static void depth_sort(void) {
    uint8_t i, j;
    if (nf <= NE)                                /* a fight: by z, then zfront (an insertion sort: the list is nearly */
        for (i = 1; i < nf; i++) {               /* sorted, one compare per entity most ticks; cpu budget G) */
            fighter_t *t = order[i], *p;
            int32_t z = t->z;
            int8_t zf = t->zfront;
            for (j = i; j > 0; j--) {
                p = order[j - 1];
                if (z > p->z || (z == p->z && zf >= p->zfront)) break;
                order[j] = p;
            }
            order[j] = t;
        }
    else
        for (i = 1; i < nf; i++)
            for (j = i; j > 0 && (depth(order[j]) < depth(order[j - 1]) ||
                                  (depth(order[j]) == depth(order[j - 1]) && order[j]->zfront < order[j - 1]->zfront)); j--) {
                fighter_t *t = order[j]; order[j] = order[j - 1]; order[j - 1] = t;
            }
    blocks_layout(nf > NE ? SEL_COLS : MAX_COLS);
    if (blk_cols == MAX_COLS) {                  /* the pool's widths: in use = its own widest frame, within PJ_SPRS */
        uint8_t used = 0;
        for (i = 0; i < NPJ; i++) {
            const fighter_t *p = &projectiles[i];
            uint8_t w = 0;
            /* (TODO #214) an object's own widest frame, measured when its definition changes: KOF's shared effects come
               several at once (Iori 624D's 7, Ralf [2]8A's 8, up to 8 columns), past PJ_SPRS at their thrower's widest;
               the step effects (bchar_t.pfx) were not in pj_cols at all */
            if (p->state != S_OFF) {
                if (p->pdef != pj_def[i]) {              /* (TODO #216: measured by the export, bproj_t cols; scanning
                                                            its rows here cost the tick 8 effects are born on 46 raster
                                                            lines, Ralf [2]8A's landing: 252 of the frame's 256) */
                    pj_def[i] = p->pdef; pj_dw[i] = p->pdef ? p->pdef->cols : 0;
                    if (pj_dw[i] > MAX_COLS) pj_dw[i] = MAX_COLS;
                }
                w = pj_dw[i] ? pj_dw[i] : pj_cols[p->ch->id];   /* (a script's effect, no definition: its thrower's widest) */
            }
            if (used + w > PJ_SPRS) w = 0;               /* no room left in the pool's sprites: not drawn */
            used += w;
            if (w != pj_w[i]) { pj_w[i] = w; projectiles[i].shown_frame = 0xFFFF; }   /* re-clipped: tiles again */
        }
    }
    {
        uint16_t s = blk_cols == SEL_COLS ? SEL_SPR : SPR_BASE;   /* blocks back to front, each its entity's width */
        uint8_t n = nf < NA ? nf : NA;
        for (i = 0; i < n; i++) {
            fighter_t *f = order[i];
            slot_spr[i] = s;
            if (f->spr != s) { f->spr = s; f->shown_frame = 0xFFFF; }
            s += blk_cols != MAX_COLS ? blk_cols : f->idx >= NF ? pj_w[f->idx - NF] : MAX_COLS;   /* = block_w (a fight's
                                                                    fighters idx < NF, its projectiles NF + i) */
        }
        for (; i < NA; i++) { slot_spr[i] = s; s += blk_cols; }
    }
}

/* ---- the sprite budget (TODO #158 / #170, docs/brawler_move_vocabulary.md "Sprite budget"): line_guard, before draw().
 * hidden[i]: order[i] is not drawn this frame; noshadow[i]: drawn without its ground shadow (its band was full);
 * guard_hidden: how many the budget hid. ---- */
#define LINE_MAX 96
static uint8_t hidden[NA], noshadow[NA], guard_hidden, guard_thinned;
static uint8_t dr_cols;                  /* the drama portrait's sprites on screen (main.c "drama mode"): kept per line */
static uint8_t guard_parity, shadow_parity;   /* the frame alternations (line_guard's order inside a tier, shadows' halves):
                                            set at a stage's start (stage_begin), not left by whatever ran before (regress bleed) */

/* draw: tiles for the frames that changed, then per entity block one SCB3 and one SCB4 run covering the columns its frame
 * uses and those the block showed last frame (to clear them); a hidden block is cleared once. */
/* ---- ground shadows: a dark ellipse (2 sprites, tiles SHADOW_TILE) at each entity's ground point (floor_top + Z, also
 * under jumps and projectiles), behind every fighter (sprites 43-54 < the blocks at 60+). Entities alternate frames by
 * draw order index: each shadow shows every other frame (flicker transparency), so the half shown on a frame (entities
 * 2j + parity) share 6 sprite pairs: pair j. ---- */
#define SH_SPR 43
_Static_assert((NE & 1) == 0, "shadow pairs: entities 2j and 2j + 1");
_Static_assert(SH_SPR + NE <= SPR_BASE, "shadows below the blocks");
#define SH_PAL 251
static const uint16_t SHADOW_PAL[16] = { 0x8000, RGB(2, 2, 5) };
static void shadow_init(void) {
    uint8_t i;
    PAL_setPalette(SH_PAL, SHADOW_PAL);
    for (i = 0; i < NE; i++) {
        uint16_t *w = cmd_run(VRAM_SCB1 + (SH_SPR + i) * 64, 2);
        w[0] = SHADOW_TILE + (i & 1); w[1] = SH_PAL << 8;
        cmd_push(VRAM_SCB2 + SH_SPR + i, 0x0FFF);
    }
}
static void shadows(void) {
    uint16_t *y, *x;
    uint8_t i;
    if (blk_cols == SEL_COLS) {                                  /* the select-width blocks start at SEL_SPR (57), inside
                                                             the shadows' sprites: only the ones below it cleared (the
                                                             ladder screen: its back actor lost its first 2 columns,
                                                             Terry cut at the left edge) */
        y = cmd_run(VRAM_SCB3 + SH_SPR, SEL_SPR - SH_SPR);
        for (i = 0; i < SEL_SPR - SH_SPR; i++) y[i] = 0;
        return;
    }
    y = cmd_run(VRAM_SCB3 + SH_SPR, sh_n); x = cmd_run(VRAM_SCB4 + SH_SPR, sh_n);
    shadow_parity ^= 1;
    for (i = shadow_parity; i < sh_n; i += 2, y += 2, x += 2) {
        fighter_t *f = order[i];
        int16_t sx, gy;
        if (mode != 1 || i >= nf || hidden[i] || noshadow[i] || f->state == S_OFF ||
            (f->state == S_PROJ && (f->frame_ovr == 0xFFFF || (f->pdef && f->pdef->kind == PK_FX)))) {   /* (a hit spark: */
            y[0] = y[1] = x[0] = x[1] = 0; continue;             /* none, TODO #215) */
        }
        sx = INT(f->x) - cam_x - 16; gy = floor_top + INT(f->z) - 8;
        y[0] = (uint16_t)((((496 - gy) & 0x1FF) << 7) | 1); y[1] = 0x40;      /* 1 tile high, second column sticky */
        x[0] = (uint16_t)(sx & 0x1FF) << 7; x[1] = 0;
    }
}

/* ---- hit sparks (tools/brawler/make_sparks.py: KOF98's, small for A / B, big for C / D / C+D): up to 4 at once on
 * sprites 364-375 (3 columns each, in front of everything), palette 254; each plays its frames once at the contact
 * point (world x, screen y), mirrored when the attacker faces right (the ROM's frames face left, like the fighters). */
#define SPARK_SPR 364
#define SPARK_N   4
#define SPARK_PAL 254
#define GSPARK_PAL 247                                       /* the guard spark's (T9): one of the big portraits' palettes
                                                                (a drama never shows during a fight's hit), loaded with
                                                                each guard spark */
typedef struct { uint8_t on, kind, frame, t; int16_t x, y; int8_t facing; uint8_t pal; } spark_state_t;
static spark_state_t spk[SPARK_N];
static uint16_t gspark_pal[16];                              /* KOF98's small spark in cold blue-white (sparks_init) */
/* big: 0 small, 1 big, 2 the guard spark (a blocked hit, fighter.c "guard"): the small spark's frames in a blue-white
 * palette (a stand-in until KOF's own guard spark is captured) */
void spark_hit(int16_t wx, int16_t sy, uint8_t big, int8_t facing) {
    uint8_t i, best = 0;
    for (i = 0; i < SPARK_N; i++) {                          /* a free slot, else the oldest */
        if (!spk[i].on) { best = i; break; }
        if (spk[i].frame > spk[best].frame) best = i;
    }
    spk[best].on = 1; spk[best].kind = big == 1 ? SPARK_BIG : SPARK_SMALL; spk[best].frame = 0; spk[best].t = 0;
    spk[best].x = wx; spk[best].y = sy; spk[best].facing = facing; spk[best].pal = big == 2 ? GSPARK_PAL : SPARK_PAL;
    if (big == 2) PAL_setPalette(GSPARK_PAL, gspark_pal);
}
static void sparks_init(void) {
    uint8_t i;
    PAL_setPalette(SPARK_PAL, spark_pal);
    for (i = 0; i < 16; i++) {                               /* the guard spark's: each colour's light, cold */
        uint16_t c = spark_pal[i];
        int16_t r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
        int16_t l = (r * 5 + g * 9 + b * 2) >> 4;
        gspark_pal[i] = i ? RGB(((l * 3) >> 2) + 6, ((l * 7) >> 3) + 7, l + 12 > 31 ? 31 : l + 12) : c;   /* (no dark
                                                                    blues: a light burst) */
    }
    for (i = 0; i < SFX_NPAL; i++) PAL_setPalette(SFX_PAL + i, bm_sfx_pals + (i << 4));   /* KOF's shared effects bank's
                                                                    palettes (TODO #214: Iori 624D's explosion, Rugal's slam) */
    for (i = 0; i < SPARK_N * 3; i++) { cmd_push(VRAM_SCB2 + SPARK_SPR + i, 0x0FFF); cmd_push(VRAM_SCB3 + SPARK_SPR + i, 0); }
    for (i = 0; i < SPARK_N; i++) spk[i].on = 0;
}
static void sparks_draw(void) {
    uint8_t i, c, r;
    if (!mode || mode == MODE_LADDER) return;                /* the select's / ladder's actors use sprites 300-379 */
    for (i = 0; i < SPARK_N; i++) {
        spark_state_t *k = &spk[i];
        uint16_t spr = SPARK_SPR + i * 3;
        const spark_frame_t *f;
        int16_t x, y;
        if (k->on && ++k->t > sparks[k->kind].f[k->frame].dur) { k->t = 1; if (++k->frame >= sparks[k->kind].n) k->on = 0; }
        if (!k->on || mode != 1) { for (c = 0; c < 3; c++) cmd_push(VRAM_SCB3 + spr + c, 0); continue; }
        f = &sparks[k->kind].f[k->frame];
        x = k->x - cam_x + (k->facing > 0 ? -(f->dx + f->cols * 16) : f->dx); y = k->y + f->dy;
        cmd_push(VRAM_SCB4 + spr, (uint16_t)(x & 0x1FF) << 7);   /* every frame: the camera moves */
        if (k->t != 1) continue;                              /* a new frame: tiles + height */
        for (c = 0; c < 3; c++) {
            uint8_t col = k->facing > 0 ? f->cols - 1 - c : c;   /* mirrored: columns right to left, tiles h-flipped */
            if (c >= f->cols) { cmd_push(VRAM_SCB3 + spr + c, 0); continue; }
            {
                uint16_t *w = cmd_run(VRAM_SCB1 + (spr + c) * 64, f->rows * 2);
                for (r = 0; r < f->rows; r++) {
                    w[r * 2] = f->tiles[col * f->rows + r];
                    w[r * 2 + 1] = (uint16_t)(k->pal << 8) | (k->facing > 0 ? 1 : 0);
                }
            }
            cmd_push(VRAM_SCB3 + spr + c, c ? 0x40 : (uint16_t)((((496 - y) & 0x1FF) << 7) | f->rows));
        }
    }
}

/* ---- the super flash (fx.super_flash, TODO #139; tools/kof96/handlers98.md "Super flash"): an engine rule, every fury
 * (D) and MAX fury (down+D) of every fighter, timings and colours game-wide (game.json super_flash -> gamedata.h
 * gflash). From the fury's frame gflash.start (fighter.c) for gflash.freeze frames the game freezes except the attacker
 * (game_tick: no other fighter, projectile, camera, wave or timer moves; only the attacker's own boxes hit), its charge
 * sound gflash.sound plays (KOF98's $1A $3A), the stage is hidden and the
 * backdrop is gflash.white_col for gflash.white frames, then gflash.dark_col (KOF98's controller $37120: $10A788 bit 7 =
 * stage planes blank, $10D936 = backdrop); KOF98's concentration (the effects library: make_sparks.py build_flash ->
 * superflash.h) plays at the anchor, following the attacker: the glow behind everything (sprites 1-10, its palette
 * cycled), the rays in front of the fighters (sprites 348-363), blue for a fury, orange for its MAX version (the
 * fighter's bchar_t.fury_max: KOF98 effect ids $38 + $3C / $3E + $5A). The anchor: the special's own (bspec_t.sf_anchor:
 * read from its KOF animation's $FA command), else gflash.dx / dy; a fighter with a flash pose (bchar_t.nfpose, TODO
 * #145: a fury from a source without a flash step; fighter.c "flash pose" shows it through the freeze, the fury after)
 * has the glow on the pose's head point (bchar_t.fhead). The concentration's frames start a frame after the
 * dark stage: in KOF98's pictures the white backdrop shows with the fury's first pose and its effect sprites a frame
 * after; the brawler's pictures lag both the same (tools/brawler/superflash_proof.py: the same pictures at the same
 * fury frames as KOF98, start 1). ---- */
#define SF_GLOW_SPR 1
#define SF_RAYS_SPR 348
#define SF_GLOW_PAL 249
#define SF_RAYS_PAL 248
_Static_assert(SF_GLOW_SPR + SF_GLOW_COLS <= BG_SPR && SF_RAYS_SPR + SF_RAYS_COLS <= SPARK_SPR,
               "super flash sprites: the glow in 1-21, the rays between the debug boxes and the sparks");
_Static_assert(SF_GLOW_COLS + SF_RAYS_COLS <= BG_N, "super flash: its columns per line fit in the hidden stage's");
static fighter_t *sf_who;                /* the attacker while the flash runs (0: none) */
static uint8_t sf_flash_t, sf_col, sf_glow_on, sf_ray;   /* frames since it started; 0 DM blue / 1 MAX orange; shown frames */
static uint8_t sf_frozen;                /* the projectile entities alive when it started: frozen through it (TODO #202) */
/* the MAX cancel (game.json max_cancel, note 20261016-133443-e03d; KOF 2002's MAX CANCEL / KOF XI's DREAM CANCEL screen,
 * simple): a fury cancelled into its MAX (fighter.c fury_cancel) plays the MAX from its first frame as any MAX, its own
 * super flash its freeze; from the cancel to that flash's end the stage is hidden behind gmaxcan.backdrop with the
 * fighters on it (screen_fx, over the flash's own white / black), MAX CANCEL in the big font (big_text.max_cancel),
 * gmaxcan.sound sent. Round 2 (Bruno: "no weird light-punch frame"): the 0.10.143 freeze of its own held the game
 * BEFORE the MAX's first frame ran (start_special sets no frame; its program's first P_ANIM does), so the fighter
 * showed a stale normal's frame (a jab) for 40 ticks; there is no such freeze any more */
static fighter_t *mc_who;                /* the MAX cancel's fighter, until its MAX's flash ends (0: none) */
static int16_t sf_dx, sf_dy;
void super_flash(fighter_t *f) {
    const bspec_t *sp = f->state == S_SPECIAL ? &f->ch->specials[f->spec_ix] : 0;   /* (a paired super throw, revamp 3: none) */
    if (mode != 1) return;
    sf_who = f; sf_flash_t = 0; sf_glow_on = 0; sf_ray = 0xFF; sf_frozen = projectiles_alive();
    sf_col = f->fmax || (sp && f->ch->fury_max < f->ch->nspec && f->spec_ix == f->ch->fury_max);   /* MAX: orange + the
                                                                whistle; fmax: the MAX role, whatever plays it (note
                                                                20261015-150000-a8c1: Haggar's MAX = his fury's pieces,
                                                                spec_ix never his fury_max, so it flashed as a fury) */
    if (f->ch->nfpose) { sf_dx = f->ch->fhead[0]; sf_dy = f->ch->fhead[1]; }   /* a flash pose (TODO #145): its head */
    else if (sp && sp->sf_anchor) { sf_dx = sp->sf_dx; sf_dy = sp->sf_dy; } else { sf_dx = gflash.dx; sf_dy = gflash.dy; }
    PAL_setPalette(SF_RAYS_PAL, sf_ray_pal[sf_col]);
    snd_sfx(sf_col ? gflash.sound_max : gflash.sound);      /* a fury: KOF98's charge sound ($370F0 -> $3906E: index
                                                                $99 = $1A $3A, DM and SDM alike); a MAX: KOF2000's
                                                                SDM flash whistle ($1E $8F there, $1A $8F here: TODO #155) */
}
static void bt_show(const char *t, uint8_t use);
void max_cancel_fx(fighter_t *f) {
    if (mode != 1) return;
    mc_who = f;
    if (gmaxcan.sound) snd_sfx(gmaxcan.sound);
    if (gbig[BIG_MAX_CANCEL].on) bt_show(0, BIG_MAX_CANCEL);
}
static void mc_end(void);
static void sf_reset(void) {
    uint8_t c;
    mc_end();                                                /* (its MAX's flash over: the MAX CANCEL screen too) */
    sf_who = 0; sf_glow_on = 0; sf_ray = 0xFF;
    for (c = 0; c < SF_GLOW_COLS; c++) { cmd_push(VRAM_SCB2 + SF_GLOW_SPR + c, 0x0FFF); cmd_push(VRAM_SCB3 + SF_GLOW_SPR + c, 0); }
    for (c = 0; c < SF_RAYS_COLS; c++) { cmd_push(VRAM_SCB2 + SF_RAYS_SPR + c, 0x0FFF); cmd_push(VRAM_SCB3 + SF_RAYS_SPR + c, 0); }
}
/* one frame of the effect: columns at spr (SCB1 written when new), placed from the anchor; KOF draws them facing left */
static void sf_place(const sf_frame_t *fr, uint16_t spr, uint8_t pal, uint8_t ncols, uint8_t newf, int16_t ax, int16_t ay, int8_t facing) {
    uint8_t c, r, flip = facing > 0;
    int16_t x = ax + (flip ? -(fr->dx + fr->cols * 16) : fr->dx), y = ay + fr->dy;
    for (c = 0; c < ncols; c++) {
        if (c >= fr->cols) { cmd_push(VRAM_SCB3 + spr + c, 0); continue; }
        if (newf) {
            uint8_t col = flip ? fr->cols - 1 - c : c;                /* mirrored: columns right to left, tiles h-flipped */
            uint16_t *w = cmd_run(VRAM_SCB1 + (spr + c) * 64, fr->rows * 2);
            for (r = 0; r < fr->rows; r++) {
                uint32_t t = fr->tiles[col * fr->rows + r];
                w[r * 2] = (uint16_t)t;
                w[r * 2 + 1] = (uint16_t)(pal << 8) | (uint16_t)((t >> 16) & 15) << 4 | flip;
            }
        }
        cmd_push(VRAM_SCB3 + spr + c, c ? 0x40 : (uint16_t)((((496 - y) & 0x1FF) << 7) | fr->rows));
    }
    cmd_push(VRAM_SCB4 + spr, (uint16_t)(x & 0x1FF) << 7);
}
static void sf_draw(void) {
    uint8_t c, k, newf, sf_t;
    int16_t ax, ay;
    if (!sf_who) return;
    sf_t = (uint8_t)(sf_flash_t - 1);                       /* the concentration: from the frame after (see super_flash) */
    fighter_pose_head(sf_who, &sf_dx, &sf_dy);               /* a flash pose: its step's head (TODO #191: the glow moves
                                                                with the pose, Haohmaru dropping into his stance) */
    ax = INT(sf_who->x) - cam_x + (sf_who->facing > 0 ? -sf_dx : sf_dx);   /* follows the attacker (KOF $37556) */
    ay = floor_top + INT(sf_who->z) - INT(sf_who->y) + sf_dy;
    if (sf_t >= sf_glow[0].at && sf_t < sf_glow[0].at + sf_glow[0].dur) {      /* the glow, its palette cycled: the first */
        k = sf_t - sf_glow[0].at;                                          /* 5 frames palette 0, then one on a frame */
        PAL_setPalette(SF_GLOW_PAL, sf_glow_pal[sf_col][(k < 5 ? 0 : k - 4) & 15]);   /* ($372FE) */
        sf_place(&sf_glow[0], SF_GLOW_SPR, SF_GLOW_PAL, SF_GLOW_COLS, !sf_glow_on, ax, ay, sf_who->facing); sf_glow_on = 1;
    } else if (sf_glow_on) { for (c = 0; c < SF_GLOW_COLS; c++) cmd_push(VRAM_SCB3 + SF_GLOW_SPR + c, 0); sf_glow_on = 0; }
    for (k = 0; k < SF_RAYS_N && !(sf_t >= sf_rays[k].at && sf_t < sf_rays[k].at + sf_rays[k].dur); k++) ;
    newf = k != sf_ray; sf_ray = k < SF_RAYS_N ? k : 0xFF;
    if (k < SF_RAYS_N) sf_place(&sf_rays[k], SF_RAYS_SPR, SF_RAYS_PAL, SF_RAYS_COLS, newf, ax, ay, sf_who->facing);
    else if (newf) for (c = 0; c < SF_RAYS_COLS; c++) cmd_push(VRAM_SCB3 + SF_RAYS_SPR + c, 0);
}
static void sf_tick(void) {                                  /* after the frame's draw: the flash's time */
    if (sf_who && ++sf_flash_t >= gflash.freeze) sf_reset();
}

/* ---- the throw-start effect (fx.throw_start, TODO #166 a; tools/brawler/make_sparks.py -> throwfx.h): KOF96/98's
 * effect state 61 (blue streaks, palette 90 -> TFX_PAL), spawned by a throw's start row (fighter.c paired_update,
 * bthrow_t.fx_*) at a point fixed in the world, played once (TFX_LEN frames); one at a time (a new throw takes it over),
 * sprites 376-379 in front of everything; it stands still while a super flash freezes the world. ---- */
#define TFX_SPR 376
#define TFX_PAL 255
_Static_assert(SPARK_SPR + SPARK_N * 3 <= TFX_SPR && TFX_SPR + TFX_COLS <= 381, "throw effect: after the sparks");
static uint8_t tfx_on, tfx_t, tfx_k, tfx_wait;
static int16_t tfx_x, tfx_y;
static int8_t tfx_face;
void throw_fx(int16_t wx, int16_t sy, int8_t facing) {
    if (mode != 1) return;
    tfx_on = 1; tfx_t = 0; tfx_k = 0xFF; tfx_x = wx; tfx_y = sy; tfx_face = facing;
    tfx_wait = 1;                                            /* KOF draws its new object the frame after (measured: the
                                                                source's pictures show it one frame after the spawn) */
}
static void tfx_reset(void) {
    uint8_t c;
    tfx_on = 0; tfx_k = 0xFF;
    PAL_setPalette(TFX_PAL, tfx_pal);
    for (c = 0; c < TFX_COLS; c++) { cmd_push(VRAM_SCB2 + TFX_SPR + c, 0x0FFF); cmd_push(VRAM_SCB3 + TFX_SPR + c, 0); }
}
static void tfx_draw(void) {
    uint8_t c, k;
    if (!mode || mode == MODE_LADDER) { tfx_on = 0; return; }   /* the select's / ladder's actors use sprites 300-379 */
    if (!tfx_on) return;
    if (tfx_wait) { tfx_wait = 0; return; }
    for (k = 0; k < TFX_N && !(tfx_t >= tfx_frames[k].at && tfx_t < tfx_frames[k].at + tfx_frames[k].dur); k++) ;
    if (k >= TFX_N || mode != 1) {                               /* over */
        for (c = 0; c < TFX_COLS; c++) cmd_push(VRAM_SCB3 + TFX_SPR + c, 0);
        tfx_on = 0; tfx_k = 0xFF; return;
    }
    sf_place(&tfx_frames[k], TFX_SPR, TFX_PAL, TFX_COLS, k != tfx_k, tfx_x - cam_x, tfx_y, tfx_face);
    tfx_k = k;
    if (!sf_who) tfx_t++;
}

/* ---- debug boxes (P2 START toggles): the corners of every hurt box (green) and attack box (red) the hit test uses,
 * 8x8 brackets on sprites 300-347 (the banner's, free in a fight): 24 for hurt boxes, 24 for attack boxes. ---- */
#define DBG_SPR 300
#define DBG_BOXES 6                      /* per kind (sprites 300-347; 348-363 = the super flash's rays, 364-375 = hit sparks) */
_Static_assert(DBG_SPR + DBG_BOXES * 8 <= SF_RAYS_SPR, "debug boxes below the super flash's rays");
#define DBG_HURT_PAL 252
#define DBG_ATK_PAL 253
static const uint16_t DBG_HURT_COL[16] = { 0x8000, RGB(4, 31, 12), 0x0000 };
static const uint16_t DBG_ATK_COL[16] = { 0x8000, RGB(31, 6, 4), 0x0000 };
static uint8_t dbg_on, dbg_shown;
static uint8_t bt_n;                     /* the big text's sprites on screen (main.c "big text"): the boxes wait meanwhile */
static void dbg_init(void) {
    uint8_t i;
    for (i = 0; i < DBG_BOXES * 8; i++) cmd_push(VRAM_SCB3 + DBG_SPR + i, 0);   /* hidden, the viewer's boxes too */
    dbg_shown = 0;
    PAL_setPalette(DBG_HURT_PAL, DBG_HURT_COL); PAL_setPalette(DBG_ATK_PAL, DBG_ATK_COL);
    for (i = 0; i < DBG_BOXES * 8; i++) {
        uint16_t *w = cmd_run(VRAM_SCB1 + (DBG_SPR + i) * 64, 2);
        w[0] = CORNER_TILE + (i & 3); w[1] = (i < DBG_BOXES * 4 ? DBG_HURT_PAL : DBG_ATK_PAL) << 8;
        cmd_push(VRAM_SCB2 + DBG_SPR + i, 0x0FFF);
    }
}
static void dbg_box(uint16_t *y, uint16_t *x, const fighter_t *f, const bbox_t *b) {   /* 4 corner sprites */
    int16_t cx = INT(f->x) + (f->facing > 0 ? -b->x : b->x) - cam_x;          /* sprites face left: mirror */
    int16_t cy = floor_top + INT(f->z) - INT(f->y) + b->y;
    int16_t l = cx - b->w, r = cx + b->w - 15, t = cy - b->h, bt = cy + b->h - 15;
    int16_t X[4] = { l, r, l, r }, Y[4] = { t, t, bt, bt };
    uint8_t k;
    for (k = 0; k < 4; k++) { y[k] = (uint16_t)((((496 - Y[k]) & 0x1FF) << 7) | 1); x[k] = (uint16_t)(X[k] & 0x1FF) << 7; }
}
static void dbg_draw(void) {
    uint16_t *y, *x;
    uint8_t i, nh = 0, na = 0;
    if (!(dbg_on && mode == 1) && !dbg_shown) return;            /* fights only: the select cursor shares 300-343 */
    if (bt_n) return;                                            /* a big message on 324-347 ("big text") */
    y = cmd_run(VRAM_SCB3 + DBG_SPR, DBG_BOXES * 8); x = cmd_run(VRAM_SCB4 + DBG_SPR, DBG_BOXES * 8);
    for (i = 0; i < DBG_BOXES * 8; i++) y[i] = x[i] = 0;
    dbg_shown = dbg_on && mode == 1;
    if (!dbg_shown) return;
    for (i = 0; i < nf; i++) {
        fighter_t *f = order[i];
        const bstep_t *st;
        const bbox_t *atk = 0;
        bbox_t ab;
        if (f->state == S_OFF || hidden[i] || (f->state == S_PROJ && f->frame_ovr == 0xFFFF)) continue;
        st = fighter_step(f);
        { const bstep_t *sh = fighter_hurt_step(f);              /* (a ROM special: its own step, #205) */
          if (f->state != S_PROJ && (sh->flags & 2) && nh < DBG_BOXES) { dbg_box(y + nh * 4, x + nh * 4, f, &sh->hurt); nh++; } }
        if ((f->state == S_ATTACK || f->state == S_AIR_ATTACK) && (st->flags & 1)) atk = &st->atk;
        else if ((f->state == S_SPECIAL || f->state == S_PROJ) && f->spec_atk) {   /* a script row's: its bank */
            uint8_t ob = BANK_set(CH_BANK(f->ch)); ab = *f->spec_atk; BANK_set(ob); atk = &ab;
        }
        if (atk && na < DBG_BOXES) { dbg_box(y + DBG_BOXES * 4 + na * 4, x + DBG_BOXES * 4 + na * 4, f, atk); na++; }
    }
}

/* ---- big text (Bruno 2026-10-14: "a BIG bitmap font, for big messages on the screen. I like the one from SAVAGE
 * REIGN"): a screen's headline in Savage Reign's round-call letters, completed to A-Z / 0-9 / ! . - ' : ? in their
 * construction (tools/brawler/make_bigfont.py -> bigfont.h: per character its advance and 16 px columns, each column 3
 * tiles = 48 px, Savage Reign's palette $BD). Which screens use it and how: game.json big_text (build_tables.py
 * big_tables -> gbig[]): stage_intro, stage_clear, game_over, time_over, bonus_won; a screen not listed keeps its
 * fix-layer line. bt_show(text, use): centred, a line wider than BT_W breaks at its first double space (two lines,
 * `pitch` apart); a sprite per glyph column (BT_SPR.., BT_MAX: the debug boxes' last 24, hidden while a message shows;
 * the bonus game's splinters / chips stay below 324), palette BT_PAL (the title banner's / staff roll's: never on
 * screen with a message); the line guard counts its columns on every band (bt_n, as the drama portrait's). bt_draw (in
 * draw(), a tick): THE headline animation every message plays (big_text.headline -> gbig_anim, note
 * 20261016-133635-e03d): slide_in ticks in from the right edge, blink ticks of its cycle (a frame each: shown / hidden /
 * white = BT_PAL all white, Savage Reign's round call measured: its own palette and an all-white one on alternate frames
 * while its letters move), hold ticks shown, slide_out ticks out to the left, then gone (bt_hide); a use with exit 0
 * stays after its hold, a still one shows in place until its screen hides it. bt_hide: gone, the debug boxes' tiles
 * back. ---- */
#define BT_SPR (DBG_SPR + 24)
#define BT_MAX 24
#define BT_PAL 250                       /* (vblank_flush's 250) BN_PAL / SR_PAL: the title banner's, the staff roll's */
#define BT_W 304                         /* the widest line */
_Static_assert(BT_SPR + BT_MAX <= DBG_SPR + DBG_BOXES * 8, "big text: inside the debug boxes' sprites");
enum { BT_SHOWN, BT_HIDDEN, BT_WHITE };   /* gbig_anim.cyc */
static uint8_t bt_white, bt_k;          /* BT_PAL is all white now; the blink's place in its cycle */
static uint16_t bt_t, bt_in, bt_out;     /* ticks since shown; px a tick sliding in / out */
static const uint16_t BT_WHITE_PAL[16] = { 0x8000, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF,
                                           0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF };
static const gbig_t *bt_s;
static int16_t bt_x[BT_MAX], bt_y[BT_MAX];
static uint8_t bt_glyph(char c) {                            /* a character -> its bigf_* index (0: a space) */
    uint8_t u = (uint8_t)c;
    if (u >= 'a' && u <= 'z') u -= 32;
    return u >= BIGF_FIRST && u < BIGF_FIRST + BIGF_N && bigf_adv[u - BIGF_FIRST] ? u - BIGF_FIRST : 0;
}
static int16_t bt_width(const char *t, uint8_t n) { int16_t w = 0; while (n--) w += bigf_adv[bt_glyph(*t++)]; return w; }
static void bt_hide(void) {
    uint8_t i;
    bt_pal_next = 0;                                         /* (no white write after it: BT_PAL is the banner's too) */
    if (!bt_n) return;
    for (i = 0; i < bt_n; i++) {
        uint16_t *w = cmd_run(VRAM_SCB1 + (BT_SPR + i) * 64, 2);   /* the debug boxes' corner tile back (dbg_init's) */
        cmd_push(VRAM_SCB3 + BT_SPR + i, 0);
        w[0] = CORNER_TILE + ((BT_SPR - DBG_SPR + i) & 3); w[1] = DBG_ATK_PAL << 8;
    }
    bt_n = 0;
}
static void mc_end(void) {                                  /* the MAX cancel's screen over */
    if (!mc_who) return;
    mc_who = 0;
    if (bt_s == &gbig[BIG_MAX_CANCEL]) bt_hide();
}
static void bt_line(const char *t, uint8_t n, int16_t y) {   /* one line, centred: its glyphs' columns as sprites */
    int16_t x = (320 - bt_width(t, n)) >> 1;
    while (n--) {
        uint8_t g = bt_glyph(*t++), c;
        for (c = 0; g && c < bigf_ncol[g] && bt_n < BT_MAX; c++) {
            const uint16_t *m = bigf_map + (bigf_col0[g] + c) * (BIGF_ROWS * 2);
            uint16_t *w = cmd_run(VRAM_SCB1 + (BT_SPR + bt_n) * 64, BIGF_ROWS * 2);
            uint8_t r;
            for (r = 0; r < BIGF_ROWS; r++) { *w++ = m[r * 2]; *w++ = m[r * 2 + 1] | (BT_PAL << 8); }
            cmd_push(VRAM_SCB2 + BT_SPR + bt_n, 0x0FFF);
            bt_x[bt_n] = x + (c << 4); bt_y[bt_n] = y; bt_n++;
        }
        x += bigf_adv[g];
    }
}
static void bt_show(const char *t, uint8_t use) {           /* t: the text (gbig[use].text first, when it has one) */
    const gbig_t *s = &gbig[use];
    uint8_t n = 0, b = 0, e;
    bt_hide();
    if (s->text) t = s->text;
    if (!t) return;
    while (t[n]) n++;
    while (n && t[n - 1] == ' ') n--;
    bt_s = s; bt_t = 0; bt_white = 0; bt_k = 0;
    bt_pal_next = bigf_pal;
    if (bt_width(t, n) > BT_W)                               /* two lines: at the first double space */
        for (b = 1; b + 1 < n && !(t[b] == ' ' && t[b + 1] == ' '); b++) ;
    if (b && b + 1 < n) {
        for (e = b; e < n && t[e] == ' '; e++) ;
        bt_line(t, b, s->y); bt_line(t + e, n - e, s->y + s->pitch);
    } else bt_line(t, n, s->y);
    bt_in = bt_out = 0;
    if (s->still) return;
    if (gbig_anim.slide_in) { uint16_t a = 0; while (a < 336) { a += gbig_anim.slide_in; bt_in++; } }   /* px a tick: 336 / ticks, up */
    if (gbig_anim.slide_out) { uint16_t a = 0; while (a < 336) { a += gbig_anim.slide_out; bt_out++; } }
}
static void bt_draw(void) {                                  /* a tick: the headline animation (see above) */
    const gbig_anim_t *a = &gbig_anim;
    uint16_t *y, *x, t = bt_t, e1 = a->slide_in + a->blink, e2 = e1 + a->hold, e3 = e2 + a->slide_out;
    uint8_t i, look = BT_SHOWN;
    int16_t d = 0;
    if (!bt_n) return;
    if (bt_s->still) { if (t) return; }                      /* (in place: written once) */
    else if (t < a->slide_in) d = (int16_t)(a->slide_in - t) * (int16_t)bt_in;   /* in from the right */
    else if (t < e1) { look = a->cyc[bt_k]; if (++bt_k >= a->ncyc) bt_k = 0; }   /* the blink: one look a frame */
    else if (t >= e2) {
        if (!bt_s->exit) { if (t > e2) return; }             /* (held for good: shown once more, then left) */
        else if (t >= e3) { bt_hide(); return; }             /* out: gone */
        else d = -(int16_t)(t - e2 + 1) * (int16_t)bt_out;   /* out to the left */
    }
    if (bt_t < 0xFFFF) bt_t++;
    if ((look == BT_WHITE) != bt_white) { bt_white = look == BT_WHITE; bt_pal_next = bt_white ? BT_WHITE_PAL : bigf_pal; }   /* (in vblank,
                                                                    with this tick's sprites: bt_pal_next) */
    y = cmd_run(VRAM_SCB3 + BT_SPR, bt_n); x = cmd_run(VRAM_SCB4 + BT_SPR, bt_n);
    for (i = 0; i < bt_n; i++) {
        int16_t px = bt_x[i] + d;
        y[i] = look == BT_HIDDEN ? 0 : (uint16_t)((((496 - bt_y[i]) & 0x1FF) << 7) | BIGF_ROWS);
        x[i] = (uint16_t)((px > 320 || px < -16 ? 320 : px) & 0x1FF) << 7;   /* (past an edge: parked off the right) */
    }
}

/* a special's screen effect (bspec_t.bd_*, Kizuna's Phoenix): while a fighter's special shows a row in [bd_first,
 * bd_end) (bd_first 0xFFFF: while its program has it on, P_SCREEN) the stage is hidden and the backdrop alternates bd_col[0] / bd_col[1] every frame (Kizuna $1FC46: $27E6 /
 * $27E4 by bit 0 of its counter $27E1); after, the stage and its backdrop come back */
static void screen_fx(void) {
    uint8_t i;
    const bspec_t *sp = 0;
    uint8_t mode = 1;
    for (i = 0; i < nf && !sp; i++) {
        fighter_t *f = &fighters[i];
        if (f->state == S_SPECIAL && f->srow) {
            const bspec_t *s = &f->ch->specials[f->spec_ix];
            if (s->bd_end && (s->bd_first == 0xFFFF ? f->pbd : f->srow - 1 >= s->bd_first && f->srow - 1 < s->bd_end)) sp = s;   /* (bd_first
                                                                 0xFFFF: its program switches it, P_SCREEN, TODO #136) */
            if (sp && s->bd_first == 0xFFFF) {           /* P_SCREEN's value (TODO #213, Kizuna $27E1): 1 the strobe, 2 its */
                mode = f->pbd;                           /* first colour held (Rosa's 6246A: black from her dive's hit), */
                if (f->pbd & 0x80) f->pbd = (f->pbd & 0x7F) ? f->pbd - 1 : 0;   /* $80 | n: the strobe n frames more */
            }                                            /* (her kicks' $27E1 = $10: 16 frames from each hit) */
        }
    }
    /* (TODO #217) every colour here goes through bd_set: written at the next vblank with the stage's sprites (cmd
       queue), so the stage and its backdrop change on the same frame and no frame shows two backdrops */
    if (mc_who && !sf_who && (mc_who->state != S_SPECIAL || !mc_who->fmax)) mc_end();   /* (its MAX gone before a flash) */
    if (mc_who) {                                            /* the MAX cancel: the stage hidden, its backdrop (over every
                                                                other screen effect, the MAX's flash included) */
        if (!bd_on) { stage_off(); bd_on = 1; bd_t = 0; }
        bd_set(gmaxcan.backdrop);
    } else if (bighit_red) {                                 /* SS2's big hit (fighter.c big_hit): red, no stage */
        if (!bd_on) { stage_off(); bd_on = 1; bd_t = 0; }
        bd_set(bighit_col); bighit_red--;
    } else if (hitflash) {                                   /* Double Dragon's super hit (fighter.c hit_spark, TODO #215;
                                                                DD $3A8A: every 2 frames the stage's palettes and the
                                                                backdrop filled red / restored; on DD's screen red 2, 3, 6
                                                                and 7 frames after its spark shows, tools/doubledr/
                                                                spark215_proof.py): the red backdrop (under the stage)
                                                                the frame before the stage's sprites go, kept until they
                                                                are back */
        uint8_t k = HITFLASH - hitflash--;
        if (k == 1 || k == 5) bd_set(BIGHIT_COL);
        else if (k == 2 || k == 6) { stage_off(); bd_on = 1; }
        else if (k == 4 || k == 8) { stage_show(); bd_set(stg->backdrop); bd_on = 0; }
    } else if (sf_who) {                                     /* the super flash: the stage hidden, white then black (the */
        if (!bd_on) { stage_off(); bd_on = 1; bd_t = 0; }       /* colour of the frame shown: sf_tick counts after) */
        bd_set((uint8_t)(sf_flash_t + 1) <= gflash.white ? gflash.white_col : gflash.dark_col);
    } else if (sp) {                                         /* Kizuna's strobe, bd_col[0] first (measured) */
        if (!bd_on) { stage_off(); bd_on = 1; bd_t = 0; }
        bd_set(mode == 2 ? sp->bd_col[0] : sp->bd_col[bd_t++ & 1]);
    } else if (bd_on) { stage_show(); bd_set(stg->backdrop); bd_on = 0; }   /* after: the stage and its backdrop back */
}

/* ---- the sprite budget (TODO #158 / #170, Bruno 2026-10-06: the select screen's actors and Geese's Raging Storm
 * blinked). The LSPC shows at most 96 sprites on a line and drops the highest-numbered ones (the front). Measured
 * (tools/brawler/budget_proof.py, the LSPC's own per-line count): the Raging Storm with 6 enemies never reached 96 on a
 * real line, the blink was this guard, which counted every actor as sharing one line; the select screen's 22 actors did
 * pass it (108 on the lines of the bodies). Two rules:
 * 1. Trimmed columns (draw.s): each sprite column shows only its rows from its first to its last non-empty tile (its
 *    trim: 3 words after the part's tiles, export_bm.py; fighter_tiles copies it to col_trim[f->idx]: t[c] for the
 *    SCB3, top[c] from the feet): a sprite counts on a line only when the line is in its height, so the empty tops
 *    and bottoms of the columns no longer count (the select's worst line 108 -> 93, the Raging Storm's 87 -> 82).
 * 2. The guard counts per band of the screen what each band will show: each entity's shown columns, a ground shadow 2
 *    on the band(s) under the feet when it shows this frame, and what the guard does not place: the stage plane's BG_N
 *    (or the super flash's glow + rays, which replace it), the throw effect and the drama portrait (every band), the
 *    hit sparks alive (their frame's span +-16 px). Three steps, each only when the one before is past LINE_MAX:
 *    a. the whole scene as one line (the sum of everything);
 *    b. per 16-px band, each entity as a box (its columns' highest top to lowest bottom) with all its columns:
 *       conservative, cheap (a crowd of 6 enemies under a fury passes here);
 *    c. per 8-px band (16 px: the select screen one sprite over), each column on the bands its trim covers, the
 *       entities by priority: an entity is hidden only when a band it covers would pass LINE_MAX; a fury's effect that
 *       does not fit is first thinned (every other column, the others the next frame: their t[] zeroed, the tiles and
 *       trims rewritten the next frame); a
 *       shadow that does not fit is left out (its entity stays).
 * Priority (placed first; the hidden ones come from the end): 0 the players, 1 their held / hit victims (GRABBED,
 * THROWN, HITSTUN, KNOCKDOWN), 2 the players' objects and the effects of a fury playing (anyone's), 3 the other enemies
 * and objects, in order[] (back to front) one frame and reversed the next, so that a crowd past the budget flickers in
 * turn (the select screen's actors are all tier 3). ---- */
#define BANDS 28                          /* c: 224 visible lines / 8 */
#define BOXES 14                          /* b: / 16 */
typedef struct { uint16_t t[MAX_COLS]; int16_t top[MAX_COLS]; } col_trim_t;   /* draw.s: t then top, MAX_COLS each */
static col_trim_t col_trim[NA];
col_trim_t *trim_cur;                     /* draw.s fighter_tiles / fighter_place: the entity's columns */
static uint8_t band_used[BANDS];
#if BLK_CHECK
uint16_t blk_bad, blk_checked;                   /* (the CPU budget C / D proof: band counts / kept blocks that differ, checked) */
#endif
static uint8_t span(int16_t top, int16_t bot, uint8_t sh, uint8_t *b1) {   /* screen y [top, bot) -> bands of 1 << sh
                                                                            px: b0 (returned) - *b1, b0 > *b1: none */
    if (top < 0) top = 0;
    if (bot > 224) bot = 224;
    if (bot <= top) { *b1 = 0; return 1; }
    *b1 = (uint8_t)((bot - 1) >> sh);
    return (uint8_t)(top >> sh);
}
static void bands_add(uint8_t b0, uint8_t b1, int8_t n) { uint8_t *u = band_used + b0; for (; b0 <= b1; b0++) *u++ += n; }
static uint8_t bands_over(uint8_t b0, uint8_t b1) {
    const uint8_t *u = band_used + b0;
    for (; b0 <= b1; b0++) if (*u++ > LINE_MAX) return 1;
    return 0;
}

/* ---- the select screen's backdrop (Bruno 2026-10-09: "use the Neo Geo Land as our select screen"): KOF95's stage 2,
 * the Esaka street in front of SNK's Neo Geo Land (tools/brawler/make_stage_land.py -> land.h: SNK's own sprite words
 * re-tiled into our C ROM, its palettes at LAND_PAL), its layers as SNK drew them, back to front: the far skyline (the
 * columns that can show through the facade's gap, a sprite each, scroll 64 + 5/7 of the camera), the city lights (6 x 2
 * tiles on the far layer, 4 images of 18 / 20 / 18 / 20 frames, each shown every other frame: SNK's 30 Hz flicker), the
 * facade + street and the crowd (1:1 with the camera, rings of LAND_RING sprites like the fight's stage), the actors,
 * then the barriers in front of them (10/7 of the camera, a ring). Every column has its own Y and height (its rows from
 * its first to its last tile); the tiles' auto-animation runs at KOF95's speed (LAND_LSPCMODE). land_band: the land's
 * sprites on each 8-px band this frame (what the line guard places the actors on top of). ---- */
extern volatile uint16_t vblank_count;           /* crt0: frames */
static uint8_t land_on, land_lt_k, land_lt_t, land_lt_ph;
static uint16_t land_lt_vb;                      /* vblank_count at the last draw: the lights' cycle runs in frames */
static uint8_t land_shown[3][LAND_RING];         /* main, mid, front: the column each ring sprite shows (0xFF none) */
static uint8_t land_band[BANDS];
static void land_count(int16_t y, uint8_t n, uint8_t k) {     /* n tiles from screen y: k sprites on their bands */
    uint8_t b0, b1;
    b0 = span(y, y + ((int16_t)n << 4), 3, &b1);
    for (; b0 <= b1; b0++) land_band[b0] += k;
}
static void land_col(const land_layer_t *L, uint16_t spr, uint8_t c) {   /* column c of L into sprite spr: tiles, Y, height */
    uint8_t n = L->n[c], r;
    if (n) {
        const uint16_t *s = L->w + L->off[c];
        uint16_t *w = cmd_run(VRAM_SCB1 + spr * 64, n * 2);
        for (r = 0; r < n * 2; r++) *w++ = *s++;
    }
    cmd_push(VRAM_SCB3 + spr, n ? (uint16_t)((((496 - (L->y + (L->first[c] << 4))) & 0x1FF) << 7) | n) : 0);
}
static void land_ring(const land_layer_t *L, uint16_t spr0, uint8_t *shown, int16_t sc) {   /* scroll sc (L's world x) */
    uint8_t first = (uint8_t)(sc >> 4), s0 = first, s, k;
    uint16_t *x;
    while (s0 >= LAND_RING) s0 -= LAND_RING;
    for (k = 0, s = s0; k < LAND_RING; k++) {                /* the columns that came into view: tiles first (a full */
        uint8_t c = first + k;                               /* queue flushes: no run left half written) */
        if (c >= L->cols) { if (shown[s] != 0xFE) { cmd_push(VRAM_SCB3 + spr0 + s, 0); shown[s] = 0xFE; } }
        else {
            if (shown[s] != c) { land_col(L, spr0 + s, c); shown[s] = c; }
            if (L->n[c]) land_count(L->y + (L->first[c] << 4), L->n[c], 1);
        }
        if (++s == LAND_RING) s = 0;
    }
    x = cmd_run(VRAM_SCB4 + spr0, LAND_RING);
    for (k = 0, s = s0; k < LAND_RING; k++) {
        x[s] = (uint16_t)((((first + k) << 4) - sc) & 0x1FF) << 7;
        if (++s == LAND_RING) s = 0;
    }
}
static void land_lights_load(uint8_t k) {                          /* lights image k into its 6 sprites */
    uint8_t c, r;
    for (c = 0; c < LAND_LIGHTS_COLS; c++) {
        const uint16_t *s = land_lights[k] + c * LAND_LIGHTS_ROWS * 2;
        uint16_t *w = cmd_run(VRAM_SCB1 + (LAND_LT_SPR + c) * 64, LAND_LIGHTS_ROWS * 2);
        for (r = 0; r < LAND_LIGHTS_ROWS * 2; r++) *w++ = *s++;
    }
}
static void land_start(void) {                                /* the select screen starts: palettes, tiles, sizes */
    uint8_t i;
    land_on = 1; land_lt_k = 0; land_lt_t = 0; land_lt_ph = 0; land_lt_vb = vblank_count;
    for (i = 0; i < LAND_NPAL; i++) PAL_setPalette(LAND_PAL + i, land_pal + (i << 4));
    *(volatile uint16_t *)0x3C0006 = LAND_LSPCMODE;           /* REG_LSPCMODE: KOF95's auto-animation speed */
    bd_set(LAND_BACKDROP);
    for (i = LAND_TOP_SPR; i < SEL_SPR; i++) cmd_push(VRAM_SCB2 + i, 0x0FFF);
    for (i = 0; i < LAND_RING; i++) cmd_push(VRAM_SCB2 + LAND_FRONT_SPR + i, 0x0FFF);
    for (i = 0; i < LAND_TOP_COLS; i++) land_col(&land_top, LAND_TOP_SPR + i, i);
    land_lights_load(0);
    for (i = 1; i < LAND_LIGHTS_COLS; i++) cmd_push(VRAM_SCB3 + LAND_LT_SPR + i, 0x40);   /* a chain on the first */
    for (i = 0; i < LAND_RING; i++) land_shown[0][i] = land_shown[1][i] = land_shown[2][i] = 0xFF;
}
static void land_off(void) {                                  /* leaving the select screen: its sprites hidden */
    uint16_t i;
    if (!land_on) return;
    land_on = 0;
    for (i = LAND_TOP_SPR; i < SEL_SPR; i++) cmd_push(VRAM_SCB3 + i, 0);
    for (i = 0; i < LAND_RING; i++) cmd_push(VRAM_SCB3 + LAND_FRONT_SPR + i, 0);
    shadow_init();                                            /* the crowd's ring held the shadows' sprites */
}
static void land_draw(void) {                                 /* every frame at the camera (cam_x: the main layer's) */
    int16_t st = 64 + (int16_t)(((uint32_t)(uint16_t)cam_x * 731) >> 10), sf = (int16_t)(((uint32_t)(uint16_t)cam_x * 1463 + 512) >> 10);
    int16_t x;                                                /* the far layer 5/7, the barriers 10/7 (KOF95's, measured) */
    uint8_t i;
    uint16_t y[LAND_TOP_COLS], xr[LAND_TOP_COLS], *w;
    for (i = 0; i < BANDS; i++) land_band[i] = 0;
    for (i = 0; i < LAND_TOP_COLS; i++) {                     /* the far skyline: the columns on screen */
        x = land_top.x0 + (i << 4) - st;
        if (x > -16 && x < 320 && land_top.n[i]) {
            y[i] = (uint16_t)((((496 - (land_top.y + (land_top.first[i] << 4))) & 0x1FF) << 7) | land_top.n[i]);
            land_count(land_top.y + (land_top.first[i] << 4), land_top.n[i], 1);
        } else y[i] = 0;
        xr[i] = (uint16_t)(x & 0x1FF) << 7;
    }
    w = cmd_run(VRAM_SCB3 + LAND_TOP_SPR, LAND_TOP_COLS); for (i = 0; i < LAND_TOP_COLS; i++) *w++ = y[i];
    w = cmd_run(VRAM_SCB4 + LAND_TOP_SPR, LAND_TOP_COLS); for (i = 0; i < LAND_TOP_COLS; i++) *w++ = xr[i];
    {                                                         /* the lights: their images by frames (the select's tick */
        uint8_t k0 = land_lt_k;                               /* can take two), shown on every other tick */
        land_lt_t += (uint8_t)(vblank_count - land_lt_vb); land_lt_vb = vblank_count;
        while (land_lt_t >= land_lights_t[land_lt_k]) { land_lt_t -= land_lights_t[land_lt_k]; if (++land_lt_k == LAND_LIGHTS_N) land_lt_k = 0; }
        if (land_lt_k != k0) land_lights_load(land_lt_k);
    }
    land_lt_ph ^= 1;
    x = LAND_LIGHTS_X - st;
    if (land_lt_ph && x > -LAND_LIGHTS_COLS * 16 && x < 320) {
        cmd_push(VRAM_SCB3 + LAND_LT_SPR, (uint16_t)((((496 - LAND_LIGHTS_Y) & 0x1FF) << 7) | LAND_LIGHTS_ROWS));
        cmd_push(VRAM_SCB4 + LAND_LT_SPR, (uint16_t)(x & 0x1FF) << 7);
        land_count(LAND_LIGHTS_Y, LAND_LIGHTS_ROWS, LAND_LIGHTS_COLS);
    } else cmd_push(VRAM_SCB3 + LAND_LT_SPR, 0);
    land_ring(&land_main, LAND_MAIN_SPR, land_shown[0], cam_x);
    land_ring(&land_mid, LAND_MID_SPR, land_shown[1], cam_x);
    land_ring(&land_front, LAND_FRONT_SPR, land_shown[2], sf);
}
/* the select's actors along the street: an actor's columns off the screen get height 0 for the frame (the LSPC counts a
 * sprite on its lines wherever its X is, and a 9-bit X past -512 / 512 would wrap it onto the screen): its trims t[]
 * saved and zeroed before the line guard (on 1), put back after the placement (on 0). A column's X from a dry placement,
 * unwrapped around the actor's own screen x. */
static uint16_t clip_t[NA][SEL_COLS];
static uint8_t clip_n[NA];                       /* columns saved per actor (0: untouched) */
static void land_clip(uint8_t on) {
    uint8_t i, c;
    for (i = 0; i < nf; i++) {
        fighter_t *f = order[i];
        col_trim_t *t = &col_trim[f->idx];
        if (!on) { for (c = 0; c < clip_n[f->idx]; c++) t->t[c] = clip_t[f->idx][c]; clip_n[f->idx] = 0; continue; }
        if (f->state == S_OFF || !f->ncols) continue;
        {
            int16_t sx = INT(f->x) - cam_x, w = f->ncols << 4, cx;
            uint8_t all = sx + w <= -16 || sx - w >= 320;     /* (its columns lie within its x +- its width) */
            if (!all && sx - w > -16 && sx + w < 320) continue;   /* surely all on the screen: as it is */
            for (c = 0; c < f->ncols; c++) clip_t[f->idx][c] = t->t[c];
            clip_n[f->idx] = f->ncols;
            if (all) { for (c = 0; c < f->ncols; c++) t->t[c] = 0; continue; }
            {
                uint16_t y[SEL_COLS], x[SEL_COLS];
                uint8_t ob = BANK_set(CH_BANK(f->ch));
                trim_cur = t; fighter_place(f, y, x, cam_x, f->ncols);
                BANK_set(ob);
                for (c = 0; c < f->ncols; c++) {
                    cx = (int16_t)(x[c] >> 7) - sx;
                    cx = sx + (((cx + 256) & 511) - 256);
                    if (cx <= -16 || cx >= 320) t->t[c] = 0;
                }
            }
        }
    }
}
/* step c: an entity's shown columns on the 8-px bands (sign -1: taken back; th: thinned, its columns th - 1, th + 1,
 * ...); its band range in *lo / *hi */
/* (CPU budget C, docs/brawler_cpu_budget.md: the columns added band by band cost up to a third of a frame on the
 * effects-heavy ticks, an effect tried, taken back, thinned) each column's band span as two marks in a difference array
 * (+1 at its first band, -1 after its last), then one pass over the entity's bands adds the running count: the same
 * counts as adding every column on every band it covers, in columns + bands steps instead of columns x bands */
static void cols_add(const fighter_t *f, int16_t oy, int8_t sign, uint8_t th, uint8_t *lo, uint8_t *hi) {
    const col_trim_t *c = &col_trim[f->idx];
    uint32_t dl[(BANDS + 4) / 4];                            /* the marks, bands 0 .. BANDS (one past the last) */
    int8_t *d = (int8_t *)dl, run = 0;
    uint8_t k, b0, b1, rows, l = BANDS, h = 0, *u;
    for (k = 0; k < (BANDS + 4) / 4; k++) dl[k] = 0;
    for (k = th ? th - 1 : 0; k < f->ncols; k += th ? 2 : 1) {
        if (!(rows = c->t[k] & 63)) continue;
        b0 = span(oy + c->top[k], oy + c->top[k] + (int16_t)(rows << 4), 3, &b1);
        if (b0 > b1) continue;
        d[b0]++; d[b1 + 1]--;
        if (b0 < l) l = b0;
        if (b1 > h) h = b1;
    }
    *lo = l; *hi = h;
#if BLK_CHECK
    {   uint8_t ref[BANDS], rl = BANDS, rh = 0;                  /* the proof: the column-by-band walk it replaces */
        for (k = 0; k < BANDS; k++) ref[k] = band_used[k];
        for (k = th ? th - 1 : 0; k < f->ncols; k += th ? 2 : 1) {
            if (!(rows = c->t[k] & 63)) continue;
            b0 = span(oy + c->top[k], oy + c->top[k] + (int16_t)(rows << 4), 3, &b1);
            if (b0 > b1) continue;
            for (u = ref + b0; b0 <= b1; b0++) *u++ += sign;
        }
        for (k = th ? th - 1 : 0; k < f->ncols; k += th ? 2 : 1) {
            if (!(rows = c->t[k] & 63)) continue;
            b0 = span(oy + c->top[k], oy + c->top[k] + (int16_t)(rows << 4), 3, &b1);
            if (b0 > b1) continue;
            if (b0 < rl) rl = b0;
            if (b1 > rh) rh = b1;
        }
        if (l <= h) { u = band_used + l; for (k = l; k <= h; k++) { run += d[k]; *u++ += sign > 0 ? run : -run; } }
        blk_checked++;
        if (rl != l || rh != h) blk_bad++;
        else for (k = 0; k < BANDS; k++) if (ref[k] != band_used[k]) { blk_bad++; break; }
        return;
    }
#endif
    if (l > h) return;
    u = band_used + l;
    if (sign > 0) for (k = l; k <= h; k++) { run += d[k]; *u++ += run; }
    else for (k = l; k <= h; k++) { run += d[k]; *u++ -= run; }
}
static uint8_t guard_tier(const fighter_t *f) {
    const fighter_t *o;
    if (f < projectiles || f >= projectiles + NPJ) {
        if (mode != 1) return 3;                                 /* the select screen's actors */
        if (!f->team) return 0;
        return f->state == S_GRABBED || f->state == S_THROWN || f->state == S_HITSTUN || f->state == S_KNOCKDOWN ? 1 : 3;
    }
    o = f->owner;
    return o && (!o->team || (o->state == S_SPECIAL && o->spec_id == BS_FURY)) ? 2 : 3;
}
/* what the guard does not place, on bands of 1 << sh px: base on all, the sparks alive on theirs */
static void bands_base(uint8_t base, uint8_t sh, uint8_t nb) {
    uint8_t k, b0, b1;
    for (k = 0; k < nb; k++) band_used[k] = base;
    if (land_on)                                             /* the select's Neo Geo Land: its sprites on each band */
        for (k = 0; k < nb; k++)
            band_used[k] += sh == 3 ? land_band[k] : land_band[2 * k] > land_band[2 * k + 1] ? land_band[2 * k] : land_band[2 * k + 1];
    if (mode == 1)
        for (k = 0; k < SPARK_N; k++)
            if (spk[k].on) {
                const spark_frame_t *sf = &sparks[spk[k].kind].f[spk[k].frame];
                b0 = span(spk[k].y + sf->dy - 16, spk[k].y + sf->dy + sf->rows * 16 + 16, sh, &b1);
                if (b0 <= b1) bands_add(b0, b1, sf->cols);
            }
}
static void line_guard(void) {
    uint8_t prio[NA], n = 0, i, k, t, base, sh = shadow_parity ^ 1;   /* sh: the shadows' half shown this frame */
    uint16_t total;
    guard_parity ^= 1;
    guard_hidden = guard_thinned = 0;
    base = mode == 1 ? BG_N + dr_cols + bt_n + (tfx_on ? TFX_COLS : 0) : 0;
    total = base;
    if (land_on) { uint8_t m = 0; for (k = 0; k < BANDS; k++) if (land_band[k] > m) m = land_band[k]; total += m; }
    for (i = 0; i < nf; i++) {                                    /* who is drawn at all; the scene's columns */
        fighter_t *f = order[i];
        int16_t sx = INT(f->x) - cam_x;
        hidden[i] = 1; noshadow[i] = 0;
        if (f->state == S_OFF || (f->state == S_PROJ && f->frame_ovr == 0xFFFF) ||
            (f->state == S_DEAD && (f->state_t & 4)) || !block_w(f)) continue;   /* the dead blink; a pool entity
                                                             without a block (no room) */
        if (sx < -128 || sx > 448) continue;                     /* well off screen: placed, its 9-bit X would wrap it
                                                             onto the screen (a wave walking in from 512 px) */
        if (floor_top + INT(f->z) - INT(f->y) < 0) continue;     /* feet above the screen's top (Kim's Phoenix flies
                                                             out): its 9-bit Y would wrap it onto the screen */
        hidden[i] = 0; prio[n++] = i;
        total += f->ncols + (mode == 1 && (i & 1) == sh ? 2 : 0);
    }
    if (mode == 1)
        for (k = 0; k < SPARK_N; k++) if (spk[k].on) total += sparks[spk[k].kind].f[spk[k].frame].cols;
    if (total <= LINE_MAX) return;                                /* a: everything fits even on one line */
    bands_base(base, 4, BOXES);                                   /* b: boxes on 16-px bands */
    for (k = 0; k < n; k++) {
        const fighter_t *f = order[i = prio[k]];
        const col_trim_t *c = &col_trim[f->idx];
        int16_t oy = floor_top + INT(f->z) - INT(f->y), lo = 0x7FFF, hi = -0x7FFF, e;
        uint8_t j, b0, b1;
        for (j = 0; j < f->ncols; j++)
            if (c->t[j] & 63) {
                if (c->top[j] < lo) lo = c->top[j];
                if ((e = c->top[j] + (int16_t)((c->t[j] & 63) << 4)) > hi) hi = e;
            }
        b0 = span(oy + lo, oy + hi, 4, &b1);
        if (b0 <= b1) bands_add(b0, b1, f->ncols);
        if (mode == 1 && (i & 1) == sh) {
            int16_t gy = floor_top + INT(f->z) - 8;
            b0 = span(gy, gy + 16, 4, &b1);
            if (b0 <= b1) bands_add(b0, b1, 2);
        }
    }
    if (!bands_over(0, BOXES - 1)) return;
    bands_base(base, 3, BANDS);                                   /* c: columns on 8-px bands, by priority */
    {                                                             /* by tier; tier 3 in order[] or reversed */
        uint8_t m = 0, tmp[NA];
        for (t = 0; t < 4; t++)
            for (k = 0; k < n; k++) {
                i = prio[guard_parity && t == 3 ? n - 1 - k : k];
                if (guard_tier(order[i]) == t) tmp[m++] = i;
            }
        for (k = 0; k < n; k++) prio[k] = tmp[k];
    }
    for (k = 0; k < n; k++) {
        fighter_t *f = order[i = prio[k]];
        int16_t oy = floor_top + INT(f->z) - INT(f->y);
        uint8_t lo, hi;
        cols_add(f, oy, 1, 0, &lo, &hi);                          /* tried: taken back when a band passes */
        if (lo <= hi && bands_over(lo, hi)) {
            uint8_t th = 0;
            cols_add(f, oy, -1, 0, &lo, &hi);
            if (guard_tier(f) == 2) {                             /* a fury's effect: thinned before it is hidden, */
                th = 1 + ((guard_parity ^ i) & 1);                 /* every other column, the others the next frame */
                cols_add(f, oy, 1, th, &lo, &hi);
                if (lo <= hi && bands_over(lo, hi)) { cols_add(f, oy, -1, th, &lo, &hi); th = 0; }
            }
            if (!th) { hidden[i] = 1; guard_hidden++; continue; }
            {                                                     /* the other columns: height 0 this frame (their */
                col_trim_t *c = &col_trim[f->idx];                /* trims come back with the tiles rewritten next frame) */
                uint8_t j;
                for (j = 2 - th; j < f->ncols; j += 2) c->t[j] = 0;
                f->shown_frame = 0xFFFF; guard_thinned++;
            }
        }
        if (mode == 1 && (i & 1) == sh) {                         /* its shadow, this frame */
            int16_t gy = floor_top + INT(f->z) - 8;
            uint8_t b0, b1;
            b0 = span(gy, gy + 16, 3, &b1);
            if (b0 <= b1) { bands_add(b0, b1, 2); if (bands_over(b0, b1)) { bands_add(b0, b1, -2); noshadow[i] = 1; } }
        }
    }
}

/* the run's float (Bruno 2026-10-09, note 20261009-102625-5d29: "a floating motion just for Kim, so that he goes up and
 * down a few pixels as he moves"): game.json roster[].run.float -> grun_bob[fighter] = [period, px a frame...], from 0
 * as the run starts; the body drawn that high, its shadow and boxes where they are */
static int32_t run_bob(const fighter_t *f) {
    const uint8_t *t;
    uint32_t r;
    if (f->state != S_RUN || f->ch->id >= BC_COUNT) return 0;
    if ((t = fighter_dash(f))) {                             /* a dash: its arc (drawn only, like the float) */
        r = f->state_t;
        return r >= t[0] && r < t[0] + t[1] ? FIX(t[2 + t[1] + r - t[0]]) : 0;
    }
    if (!(t = grun_bob[f->ch->id])) return 0;
    r = f->state_t;
    __asm__("divu.w %1,%0" : "+d"(r) : "d"((uint16_t)t[0]));   /* (state_t mod period: the remainder, high word) */
    return FIX(t[1 + (r >> 16)]);
}
static void pal_pend_tick(void);
#if BLK_CHECK
/* (make PROFILE="0 -DBLK_CHECK=1": the CPU budget D proof) a block left as it was: placed again into scratch words and
 * compared with the words last written there; blk_bad counts the blocks that would have changed */
static uint16_t blk_sy[NA][MAX_COLS], blk_sx[NA][MAX_COLS];
static void blk_check(uint8_t i, fighter_t *f, uint8_t m, int32_t b) {
    uint16_t y[MAX_COLS], x[MAX_COLS]; uint8_t c, ob = BANK_set(CH_BANK(f->ch));
    int32_t fy = f->y;
    f->y += b; trim_cur = &col_trim[f->idx]; fighter_place(f, y, x, cam_x, m); f->y = fy; BANK_set(ob);
    blk_checked++;
    for (c = 0; c < m; c++) if (y[c] != blk_sy[i][c] || x[c] != blk_sx[i][c]) { blk_bad++; break; }
}
#endif
static void draw(void) {
    uint8_t i;
    int16_t shk = mode == 1 ? fighter_shake() : 0;           /* a throw's impact shakes the screen (fighter.c THE THROW
                                                                EVENTS): the camera moved while drawing only */
    cam_x += shk;
    if (mode == 1) { screen_fx(); stage_draw(); }            /* only the fight has a stage */
    {   uint8_t bc = blk_cols, ob = neo_bank, w;             /* (CPU budget D: one pass, the bank put back once) */
        fighter_t **o = order, **oe = order + nf;
        for (; o < oe; o++) {
            fighter_t *f = *o;
            if (f->state == S_OFF || (f->state == S_PROJ && f->frame_ovr == 0xFFFF)) continue;
            w = bc != MAX_COLS || f < projectiles || f >= projectiles + NPJ ? bc : pj_w[f->idx - NF];   /* (block_w) */
            if (!w) continue;
            BANK_set(CH_BANK(f->ch));                            /* its frames: its bank (fighter.h) */
            blk_new[f->idx] = f->shown_frame == 0xFFFF;          /* (CPU budget D: rewritten in place) */
            blk_cols = w; trim_cur = &col_trim[f->idx]; fighter_tiles(f);   /* clipped to its block */
        }
        blk_cols = bc; BANK_set(ob);
    }
    mark(P_TILES);
    if (pal_pend) pal_pend_tick();                           /* (after the tiles: their columns) */
    if (land_on) { land_draw(); land_clip(1); }             /* the select: the Neo Geo Land, the actors' columns off screen */
    line_guard();
    mark(P_GUARD);
    {   uint8_t moved = 0;
        for (i = 0; i < NA; i++)                             /* a block that moved: its old place cleared first */
            if (block_placed[i] && block_spr[i] != slot_spr[i]) {
                uint16_t *y = cmd_run(VRAM_SCB3 + block_spr[i], block_placed[i]); uint8_t c;
                for (c = 0; c < block_placed[i]; c++) y[c] = 0;
                block_placed[i] = 0; moved = 1;
            }
        /* (note 20261011-225104-5d29, Kyo vanished in his win pose) those sprites may be another slot's now, and its key
           can say "written" from an older frame (a slot that wrote nothing keeps no key, below, but the entity itself
           sits there again: Kyo back in slot 14 at sprite 199, the move of slot 13 off 199 cleared him): every key
           dropped, the blocks rewritten this frame (order changes only) */
        if (moved) blk_key_reset();
    }
    if (mode != 1 || land_on) { blk_key_reset(); bg_ok = 0; }   /* (the caches: the fight's blocks and stage only) */
    {   uint8_t ob = neo_bank, keep = mode == 1 && !land_on;
        for (i = 0; i < NA; i++) {
            fighter_t *f = order[i];
            uint8_t n = 0, m;
            uint16_t spr = slot_spr[i], *y, *x;
            if (i < nf && !hidden[i]) {                          /* visible */
                int32_t fy = f->y, b = f->state == S_RUN ? run_bob(f) : 0;
                uint32_t pos, frm, sm;
                n = f->ncols; m = n > block_placed[i] ? n : block_placed[i];
                if (!m) { bk_f[i] = 0; goto next; }              /* (nothing written: no key kept) */
                pos = (uint32_t)(uint16_t)(INT(f->x) - cam_x) << 16 | (uint16_t)(floor_top + INT(f->z) - INT(fy + b));
                frm = (uint32_t)f->shown_frame << 8 | (uint8_t)f->facing; sm = (uint32_t)spr << 8 | m;
                if (bk_f[i] == f && bk_pos[i] == pos && bk_frm[i] == frm && bk_sm[i] == sm) {
#if BLK_CHECK
                    blk_check(i, f, m, b);
#endif
                    goto next;
                }
                y = cmd_run(VRAM_SCB3 + spr, m); x = cmd_run(VRAM_SCB4 + spr, m);
                BANK_set(CH_BANK(f->ch));
                f->y += b;                                       /* (the run's float: drawn only, the shadow on the floor) */
                trim_cur = &col_trim[f->idx]; fighter_place(f, y, x, cam_x, m);
                f->y = fy;
                bk_f[i] = keep && f->shown_frame != 0xFFFF && !blk_new[f->idx] ? f : 0;   /* (thinned this frame: its
                                                                    trims come back next frame) */
                bk_pos[i] = pos; bk_frm[i] = frm; bk_sm[i] = sm;
#if BLK_CHECK
                { uint8_t c; for (c = 0; c < m; c++) { blk_sy[i][c] = y[c]; blk_sx[i][c] = x[c]; } }
#endif
            } else {                                             /* hidden or none: its sprites height 0 */
                uint8_t c;
                if ((m = block_placed[i])) {
                    y = cmd_run(VRAM_SCB3 + spr, m); x = cmd_run(VRAM_SCB4 + spr, m);
                    for (c = 0; c < m; c++) y[c] = x[c] = 0;
                }
                bk_f[i] = 0;
            }
        next:
            block_placed[i] = n; block_spr[i] = spr;
        }
        BANK_set(ob);
    }
    if (land_on) land_clip(0);                               /* their trims back */
    else if (mode != 6) shadows();                           /* (the select's land holds the shadows' sprites; AOF2's bonus screens, mode 6, theirs) */
    sparks_draw();
    if (mode == 1) sf_draw();
    tfx_draw();
    dbg_draw();
    bt_draw();
    cam_x -= shk;
}

static intent_t in[NF];                          /* this frame's intent per fighter (player pad or AI) */
static void inputs_reset(void) {                 /* a select / fight starts: nothing of the demo or the last game */
    uint8_t i;
    for (i = 0; i < NF; i++) in[i] = (intent_t){ 0 };
    for (i = 0; i < 2; i++) {
        uint8_t k;
        tap_t[i] = 255; tap_dir[i] = 0;
        for (k = 0; k < 2; k++) { bz_x[i][k] = bz_z[i][k] = 0; bz_xa[i][k] = bz_za[i][k] = ab_age[i][k] = 255; }
    }
}
static void close_marks(void) {                 /* intent.close: an opponent within CLOSE_X (A takes a route's close link); */
    static fighter_t *op0[NF + 1], *op1[NF + 1];   /* intent.lie: the nearest opponent lying within DOWN_REACH (up / */
    fighter_t **p0 = op0, **p1 = op1, *f;          /* down + A: the down attack at it, TODO #218). The opponents (not */
    intent_t *it = in;                             /* OFF / DEAD) are listed once by team, in slot order, 0-ended */
    for (f = fighters; f < fighters + NF; f++) {   /* (cpu budget G: 64 pair tests -> 2 x 6 + 6 x 2) */
        if (f->state == S_OFF || f->state == S_DEAD) continue;
        if (f->team) *p1++ = f; else *p0++ = f;
    }
    *p0 = 0; *p1 = 0;
    for (f = fighters; f < fighters + NF; f++, it++) {
        fighter_t **pp = f->team ? op0 : op1, *o, *lie = 0;   /* (its opponents) */
        uint8_t close = 0;
        int16_t best = DOWN_REACH + 1, x = INT(f->x), z = INT(f->z);
        if (f->state != S_OFF)
            while ((o = *pp++)) {
                int16_t dx = INT(o->x) - x, dz = INT(o->z) - z;
                if ((uint16_t)(dx + CLOSE_X) <= 2 * CLOSE_X && (uint16_t)(dz + Z_HIT) <= 2 * Z_HIT) close = 1;   /* |dx| <= */
                if (o->state == S_DOWN && o->hp > 0) {                                               /* CLOSE_X, |dz| <= Z_HIT */
                    if (dx < 0) dx = -dx;
                    if (dx < best) { best = dx; lie = o; }
                }
            }
        it->close = close; it->lie = lie;
    }
}
static void read_player(uint8_t p, intent_t *in, const fighter_t *f) {
    uint16_t held = JOY_held(p), pressed = JOY_pressed(p);
    *in = (intent_t){ 0 };                                     /* from nothing every frame: a human's input carries nothing
                                                                  the AI wrote (the attract demo drives P1's slot) */
    in->dx = (held & JOY_RIGHT) ? 1 : (held & JOY_LEFT) ? -1 : 0;
    in->dz = (held & JOY_DOWN) ? 1 : (held & JOY_UP) ? -1 : 0;
    in->press = ((pressed & JOY_A) ? IN_A : 0) | ((pressed & JOY_B) ? IN_B : 0) |   /* A attack, B jump, C special, */
                ((pressed & JOY_C) ? IN_C : 0) | ((pressed & JOY_D) ? IN_D : 0);   /* D fury: each at once */
    in->hold = ((held & JOY_A) ? IN_A : 0) | ((held & JOY_B) ? IN_B : 0) | ((held & JOY_C) ? IN_C : 0) | ((held & JOY_D) ? IN_D : 0);
    if (pressed & (JOY_LEFT | JOY_RIGHT)) {                     /* forward tapped twice within 12 frames */
        uint8_t d = (pressed & JOY_RIGHT) ? 1 : 2;
        if (tap_dir[p] == d && tap_t[p] < 12) in->run = 1;
        tap_dir[p] = d; tap_t[p] = 0;
    } else if (tap_t[p] < 255) tap_t[p]++;
    /* A+B = C everywhere (Bruno 2026-10-08): both on the same frame, or the second while the first is held and pressed at
     * most gblitz.chord frames before (intent_t.chord: the first one acted already, fighter.c gives its start to the C) */
    {   uint8_t k, w = gblitz.chord;
        for (k = 0; k < 2; k++) if (ab_age[p][k] < 255) ab_age[p][k]++;
        if ((pressed & JOY_A) && (pressed & JOY_B)) { in->press = (in->press & ~(IN_A | IN_B)) | IN_C; ab_age[p][0] = ab_age[p][1] = 255; }
        else if (((pressed & JOY_A) && (held & JOY_B) && ab_age[p][1] <= w) || ((pressed & JOY_B) && (held & JOY_A) && ab_age[p][0] <= w)) {
            in->press = (in->press & ~(IN_A | IN_B)) | IN_C; in->chord = 1; ab_age[p][0] = ab_age[p][1] = 255;
        } else {
            if (pressed & JOY_A) ab_age[p][0] = 0;
            if (pressed & JOY_B) ab_age[p][1] = 0;
        }
        if ((held & (JOY_A | JOY_B)) == (JOY_A | JOY_B)) in->hold |= IN_C;   /* (a held chord holds C: PC_HELD charges) */
    }
    /* the Blitz (Bruno 2026-10-08, fighter.c "Blitz"): the last two taps of the stick on each axis (a direction newly
     * pressed: depth walking and a held up / down are untouched), each within gblitz.window frames of the one before, and A
     * within gblitz.window of the second: forward,forward (forward = the way the fighter faces at the A), down,down,
     * down,up, up,up -> intent_t.blitz = BZ_* + 1; the most recent second tap wins; the history is then cleared */
    {   uint8_t k, w = gblitz.window, best = 255, slot = 0;
        for (k = 0; k < 2; k++) { if (bz_xa[p][k] < 255) bz_xa[p][k]++; if (bz_za[p][k] < 255) bz_za[p][k]++; }
        if (pressed & (JOY_LEFT | JOY_RIGHT)) { bz_x[p][0] = bz_x[p][1]; bz_xa[p][0] = bz_xa[p][1]; bz_x[p][1] = (pressed & JOY_RIGHT) ? 1 : 2; bz_xa[p][1] = 0; }
        if (pressed & (JOY_UP | JOY_DOWN)) { bz_z[p][0] = bz_z[p][1]; bz_za[p][0] = bz_za[p][1]; bz_z[p][1] = (pressed & JOY_DOWN) ? 1 : 2; bz_za[p][1] = 0; }
        if (in->press & IN_A) {
            if (bz_x[p][0] == bz_x[p][1] && bz_x[p][1] == (f->facing > 0 ? 1 : 2) && bz_xa[p][1] <= w && bz_xa[p][0] - bz_xa[p][1] <= w)
                { best = bz_xa[p][1]; slot = BZ_FF + 1; }
            if (bz_za[p][1] <= w && bz_za[p][0] - bz_za[p][1] <= w && bz_za[p][1] < best) {
                uint8_t a = bz_z[p][0], b = bz_z[p][1];
                if (a == 1 && b == 1) slot = BZ_DD + 1; else if (a == 1 && b == 2) slot = BZ_DU + 1; else if (a == 2 && b == 2) slot = BZ_UU + 1;
            }
            if (slot) { in->blitz = slot; for (k = 0; k < 2; k++) bz_xa[p][k] = bz_za[p][k] = 255; }
        }
    }
}

/* ---- HUD on the fix layer (tools/brawler/make_hud.py), fighting-game layout: top row = the life bars, KOF94-style (1 px
 * steps, red damage trail that holds 20 frames then shrinks), the left one anchored at the left edge, the right one at the
 * right edge (mirrored glyphs), so both empty from the middle outward; row below = the names, pinned to the corners next
 * to the 32x32 portraits (fix palette 2 + side, rows 0-3 at the screen edges); then lives / continue. P1 left; right =
 * the enemy P1 fights, or P2 (2-player builds: each player's target under its block). Only changed cells are written. ---- */
#define BAR_CELLS 15
#define BAR_PX    118                    /* inside the caps: 7 + 13 x 8 + 7 */
#define LIFE      60
#define BOSS_CELLS 30                    /* the boss bar: 7 + 28 x 8 + 7 = 238 px, fix row 7 under the HUD */
typedef struct { uint8_t col, row, mirror, n, cell[BOSS_CELLS], wait, pal, open; int16_t px, trail; } bar_t;   /* open: no
                                            inner cap, its last cell a middle one (a drive chunk joined to the next) */
static uint8_t lives[2];
static uint16_t cont_t[2];                       /* continue countdown (frames), 0 = none */
static uint8_t cont_ov;                          /* the CONTINUE? overlay: 0 off, 1 on (the fight frozen), 2 fading out */
static uint8_t cont_digit(uint8_t p) {           /* 9 .. 0 */
    uint32_t r = (uint16_t)(cont_t[p] - 1);
    if (!cont_t[p]) return 0;
    __asm__("divu.w %1,%0" : "+d"(r) : "d"((uint16_t)60));
    return (uint8_t)r;
}
/* bars: 0 P1, 1 right block (P2, or P1's target alone), 2 P1's target under P1, 3 P2's target under P2, 4 the boss,
 * 5 .. 5 + MAX_CHUNKS - 1 P1's drive chunks, then P2's (Bruno's redesign 2026-10-08, fighter.c "the meter"): row 3 under
 * the name, one short bar per chunk (CHUNK_CELLS cells, the life bar's glyphs in METER_PAL; P2's mirrored from the right
 * edge), side by side as ONE bar (Bruno 2026-10-09, note 20261009-114418-5d29: "link them so there is no space"): a chunk
 * followed by another has no inner cap (bar_t.open), the next one's outer cap is the 1 px divider; each filled with its
 * share of the drive (the first chunk first), no label; the fury gauge is never drawn. A player's life bar has its own fix palette (LIFE_PAL + player): at low life (fighter_low) it blinks red,
 * KOF95's (measured in our emulator, /data/tmp/newsys/scripts/kof_bar.py: 8 frames red, 8 frames its colours; the life
 * left pure red #FF0000 with a darker top / bottom row, the emptied part #C93616 instead of its dark) */
#define MAX_CHUNKS  GM_MAX_CHUNKS        /* game.json meter.max_chunks: the bar's most chunks (a bonus game's reward up to it) */
#define CHUNK_CELLS (BAR_CELLS / MAX_CHUNKS)   /* a chunk's cells, whatever the bar holds: MAX_CHUNKS of them span the life
                                    bar exactly (note 20261016-152232-e03d: 5 x 3 cells = its 15) */
_Static_assert(CHUNK_CELLS * MAX_CHUNKS == BAR_CELLS, "meter.max_chunks: the life bar's cells / max_chunks, whole");
#define METER_PAL 4                      /* fix palette 4: palette 0 with the bar colours' red and blue swapped */
#define LIFE_PAL  5                      /* fix palettes 5 / 6: P1's / P2's life bar (palette 0's colours; red at low life) */
static bar_t bars[5 + 2 * MAX_CHUNKS];
static uint8_t boss_shown;
static uint8_t hud_red[2];                       /* the life bar's palette shown per player: 0 its colours, 1 red, 0xFF none yet */
static fighter_t *hud_tgt[4];
static int8_t hud_lives[2];
static uint16_t hud_cont[2];
static uint8_t hud_face[2], hud_two = 0xFF;      /* portraits shown left / right; layout (0 = one player, 1 = two) */
static uint16_t hud_tick, hud_min_spins = 0xFFFF;
static uint16_t hud_lag, hud_lag_v, hud_lag_t;   /* (CPU budget H) frames dropped this window; vblank_count / game_ticks at the last hud */
extern volatile uint32_t game_ticks;             /* (crt0) */
static uint8_t wave;
static void fix_put(uint8_t col, uint8_t row, uint16_t v) { cmd_push(VRAM_FIX + col * 32 + row + 2, v); }
static uint8_t char_index(const bchar_t *ch) { return ch->id < BC_COUNT ? ch->id : 0; }   /* (bchar_t.id: its index in bm_chars) */
/* a portrait in HUD slot `side` (0 left, 1 right) uses fix palette 2 + side, loaded with the fighter's colours when it
 * is drawn: fix palettes are 4-bit (0-15), so 16 roster fighters cannot each keep one (2026-10-05: the bosses made 16) */
static void portrait(uint8_t col, uint8_t row, uint8_t ch, uint8_t side) {      /* ch 0xFF = clear */
    uint8_t r, c;
    if (ch != 0xFF) PAL_setPalette(2 + side, portrait_pal[ch]);
    for (r = 0; r < 4; r++)
        for (c = 0; c < 4; c++)
            fix_put(col + c, row + r, ch == 0xFF ? 0x20 : (uint16_t)((2 + side) << 12 | (PORTRAIT_TILE + ch * 16 + r * 4 + c)));
}
static uint16_t div16(uint16_t n, uint16_t d) { uint32_t r = n; __asm__("divu.w %1,%0" : "+d"(r) : "d"(d)); return (uint16_t)r; }
/* 2 px a life point (60 = a full fighter bar); a life that would not fit (hp_max: difficulty HARD / MANIAC enemies,
 * bosses) is drawn to scale, max = the full bar */
static void bar_draw(bar_t *b, int16_t hp, int16_t max) {
    int16_t full = (b->n << 3) - 2 + b->open, px, x0 = 0, opx = b->px, otr = b->trail;
    if (!max) max = LIFE;
    px = hp <= 0 ? 0 : max * 2 > full ? (int16_t)div16((uint16_t)hp * (uint16_t)full, max) : hp * 2;
    if (px > full) px = full;
    uint8_t c;
    if (px < b->px && b->trail < b->px) b->trail = b->px;          /* a new hit: the trail starts at the old life */
    if (px < b->px) b->wait = 20;
    b->px = px;
    if (b->trail > px) { if (b->wait) b->wait--; else b->trail--; } else b->trail = px;
    if (px == opx && b->trail == otr) return;                   /* (CPU budget A: the cells show this life and trail
                                                                   already; px -1 = never drawn / cleared) */
    for (c = 0; c < b->n; c++) {                                 /* c counts from the bar's outer edge */
        uint8_t kind = c == 0 ? 0 : c == b->n - 1 && !b->open ? 2 : 1, w = kind == 1 ? 8 : 7, t, sc = b->mirror ? b->n - 1 - c : c;
        int16_t f = px - x0;
        if (f < 0) f = 0;
        if (f > w) f = w;
        t = (b->mirror ? BAR_TILE_R : BAR_TILE) + kind * 18 + (b->trail > x0 + f ? 9 : 0) + f;
        if (b->cell[sc] != t) { b->cell[sc] = t; fix_put(b->col + sc, b->row, (uint16_t)b->pal << 12 | t); }
        x0 += w;
    }
}
static void bar_clear(bar_t *b) {
    uint8_t c;
    for (c = 0; c < b->n; c++) { b->cell[c] = 0; fix_put(b->col + c, b->row, 0x20); }
    b->px = b->trail = -1; b->wait = 0;
}
static void hud_reset(void) {
    static const uint8_t COL[5] = { 5, 20, 5, 20, 5 }, ROW[5] = { 1, 1, 5, 5, 7 };   /* the name above its bar (Bruno 2026-10-09, note 20261009-234250-b3f3) */
    uint8_t p, c, cc = CHUNK_CELLS;                          /* a chunk's cells: the life bar / MAX_CHUNKS (P1's and P2's never meet) */
    for (p = 0; p < 5 + 2 * MAX_CHUNKS; p++) {
        uint8_t two = p >= 5 + MAX_CHUNKS, k = (uint8_t)(p - 5 - (two ? MAX_CHUNKS : 0));   /* (a chunk: its index, P2's;
                                                                    no %: MAX_CHUNKS 5 would call __modsi3) */
        bars[p].col = p < 5 ? COL[p] : two ? 35 - cc - cc * k : 5 + cc * k;   /* (the chunks side by side: one bar, note
                                                                    20261009-114418-5d29) */
        bars[p].open = p >= 5 && k + 1 < drive_chunks && k + 1 < MAX_CHUNKS;   /* (a chunk before another: no inner cap;
                                                                    the next one's outer cap = the 1 px divider) */
        bars[p].row = p < 5 ? ROW[p] : 3;
        bars[p].mirror = (p & 1 && p < 4) || two; bars[p].px = bars[p].trail = -1; bars[p].wait = 0;
        bars[p].n = p < 4 ? BAR_CELLS : p == 4 ? BOSS_CELLS : cc; bars[p].pal = p >= 5 ? METER_PAL : p == 0 ? LIFE_PAL : 0;
        if (p < 4) hud_tgt[p] = 0;
        for (c = 0; c < BOSS_CELLS; c++) bars[p].cell[c] = 0;
    }
    boss_shown = 0;
    for (p = 0; p < 2; p++) { hud_lives[p] = -1; hud_cont[p] = 0xFFFF; hud_face[p] = 0xFE; hud_red[p] = 0xFF; }
    hud_two = 0xFF;
}
static void hud_name(uint8_t right, uint8_t row, const char *name) {   /* pinned to its corner, beside the portrait */
    uint8_t n = 0;
    FIX_print(right ? 25 : 5, row, "          ", 0);
    if (!name) return;
    while (name[n]) n++;
    FIX_print(right ? 35 - n : 5, row, name, 0);
}
/* a target: name (+ portrait when it is the right block) and bar, drawn when it changes; 0 = clear */
static void hud_target(uint8_t slot, fighter_t *t, uint8_t right, uint8_t name_row, uint8_t face_side) {
    if (t && t->state == S_OFF) t = 0;
    if (t != hud_tgt[slot]) {
        hud_tgt[slot] = t;
        hud_name(right, name_row, t ? FIGHTER_NAME(t) : 0);
        if (face_side) { uint8_t f = t ? char_index(t->ch) : 0xFF; if (hud_face[1] != f) { hud_face[1] = f; portrait(35, 0, f, 1); } }
        if (!t) bar_clear(&bars[slot]);
    }
    if (t) bar_draw(&bars[slot], t->hp, t->hp_max);
}
#define BIOS_PLAYER_MOD ((volatile uint8_t *)0x10FDB6)   /* per player: 0 never played, 1 playing, 2 continue, 3 over */
static uint8_t p2_in(void) { return in_play(&fighters[1]) || cont_t[1]; }
#define BOSS_IDX_HUD 2                   /* = BOSS_IDX (campaign) */
static const fighter_t *hud_hide;        /* a fighter that is not an opponent (the referee's body, main.c "the referee"):
                                            no name, face or bar as a player's target */
static fighter_t *tgt(fighter_t *f) {    /* a player's target for the right block: the boss has its own bar */
    if (hud_hide && f->target == hud_hide) return 0;
    return f->target == &fighters[BOSS_IDX_HUD] && (phase == PH_BOSS || phase == PH_END) ? 0 : f->target;
}
static void hud(void) {
    uint8_t p, i, two = p2_in();
    if (two != hud_two) {                                    /* layout change: clear the HUD rows, redraw all */
        for (i = 0; i < 8; i++) FIX_print(1, i, "                                      ", 0);
        hud_reset(); hud_two = two;
        bars[1].pal = two ? LIFE_PAL + 1 : 0;                /* (the right block: P2's life, or P1's target's) */
    }
    for (p = 0; p < 1 + two; p++) {                          /* the players' blocks: P1 left, P2 right */
        fighter_t *f = &fighters[p];
        uint8_t face = char_index(f->ch), pc = p ? 35 : 1, lc = p ? 32 : 5, cc = p ? 20 : 9;   /* lives / continue cols */
        if (hud_face[p] != face) { hud_face[p] = face; portrait(pc, 0, face, p); hud_name(p, 0, f->ch->name); }
        bar_draw(&bars[p], in_play(f) ? f->hp : 0, f->hp_max);
        {   uint8_t k;                                       /* the drive: one bar per chunk, the first filled first */
            int16_t d = in_play(f) ? (int16_t)f->drive : 0;
            for (k = 0; k < drive_chunks && k < MAX_CHUNKS; k++) {
                int16_t c = d > (int16_t)gmeter.chunk ? (int16_t)gmeter.chunk : d < 0 ? 0 : d;
                bar_draw(&bars[5 + p * MAX_CHUNKS + k], c, (int16_t)gmeter.chunk);
                d -= (int16_t)gmeter.chunk;
            }
        }
        {   uint8_t red = in_play(f) && fighter_low(f) && !(hud_tick & 8);   /* low life: the life bar blinks red (8 / 8) */
            if (red != hud_red[p]) {
                uint16_t pal[16];
                uint8_t k;
                hud_red[p] = red;
                for (k = 0; k < 16; k++) pal[k] = TEXT_PAL[k];
                for (k = 0; k < 10; k++) pal[6 + k] = bar_colours[k];
                if (red) {                                   /* KOF95's: the life left red, the emptied part dark red */
                    pal[6] = pal[7] = pal[8] = pal[9] = RGB(31, 0, 0); pal[10] = RGB(29, 1, 0); pal[14] = RGB(25, 6, 2);
                }
                PAL_setPalette(LIFE_PAL + p, pal);
            }
        }
        if (lives[p] != hud_lives[p]) { hud_lives[p] = lives[p]; FIX_print(lc, 2, "x ", 0); FIX_printNum(lc + 1, 2, lives[p], 0); }
        i = cont_t[p] && !cont_ov ? cont_digit(p) + 1 : 0;   /* the count here while the other player fights on */
        if (i != hud_cont[p]) {
            hud_cont[p] = i;
            if (i) { FIX_print(cc, 2, "CONTINUE   ", 0); FIX_printNum(cc + 9, 2, i - 1, 0); }
            else FIX_print(cc, 2, "           ", 0);
        }
        if (two) hud_target(2 + p, tgt(f), p, 4, 0);       /* each player's target under its own block: bar, name */
    }
    if (!two) hud_target(1, tgt(&fighters[0]), 1, 0, 1);  /* one player: its target is the right block */
    i = mode == 1 && !attract && (phase == PH_BOSS || phase == PH_END) && fighters[BOSS_IDX_HUD].state != S_OFF;
    if (i != boss_shown) {                                   /* the boss bar: name on row 6, bar on row 7 */
        boss_shown = i;
        FIX_print(5, 6, "              ", 0);
        if (i) FIX_print(5, 6, FIGHTER_NAME(&fighters[BOSS_IDX_HUD]), 0); else bar_clear(&bars[4]);
    }
    if (boss_shown) bar_draw(&bars[4], fighters[BOSS_IDX_HUD].hp, fighters[BOSS_IDX_HUD].hp_max);
    if ((hud_tick & 15) != 0 && (uint16_t)wait_cycles < hud_min_spins) hud_min_spins = (uint16_t)wait_cycles;  /* skip the print tick */
    {   /* (CPU budget H) the frames dropped: a tick that overran takes 2+ vblanks, which the idle spins never show (CPU
           reads the worst tick that fit); LAG = the frames dropped over the last 16 ticks (from one hud to the next:
           vblanks - ticks; a stretch without the HUD in between, a scene or a pause, is not counted) */
        uint16_t v = vblank_count, t = (uint16_t)game_ticks;
        if ((uint16_t)(t - hud_lag_t) == 1 && (uint16_t)(v - hud_lag_v) > 1) hud_lag += (uint16_t)(v - hud_lag_v) - 1;
        hud_lag_v = v; hud_lag_t = t;
    }
    if (!(++hud_tick & 15)) {
        uint16_t idle = (uint16_t)(((uint32_t)hud_min_spins * 7) >> 8);
        FIX_print(30, 26, "CPU    %", 0); FIX_printNum(34, 26, idle >= 100 ? 0 : 100 - idle, 0);
        FIX_print(22, 26, "      ", 0);
        if (hud_lag) { FIX_print(22, 26, "LAG", 0); FIX_printNum(26, 26, hud_lag > 99 ? 99 : hud_lag, 0); }
        hud_min_spins = 0xFFFF; hud_lag = 0;
#if PROFILE_HUD
        {
            static const char *PN[P_N] = { "FLUSH", "AI", "UPDATE", "COMBAT", "SORT", "TILES", "GUARD", "PLACE", "HUD" };
            for (i = 0; i < P_N; i++) {             /* worst raster lines per section (1 line = 768 cycles) */
                FIX_print(28, 11 + i, PN[i], 0); FIX_print(35, 11 + i, "   ", 0); FIX_printNum(35, 11 + i, prof[i], 0);
                prof_max[i] = prof[i]; prof[i] = 0;
            }
            FIX_print(28, 21, "EG    ", 0); FIX_printNum(31, 21, stat_grabs, 0);   /* enemy grabs, specials, throws */
            FIX_print(28, 22, "ES    ", 0); FIX_printNum(31, 22, stat_specials, 0);
            FIX_print(28, 23, "ET    ", 0); FIX_printNum(31, 23, stat_throws, 0);
            FIX_print(28, 24, "PE    ", 0); FIX_printNum(31, 24, stat_escapes, 0); /* player escapes */
        }
#endif
    }
}

#define CONTINUE  600
#define BOSS_IDX  2                              /* the boss's fighter slot; minions 3.. */
/* the game's data (gamedata.h, generated from game.json by tools/brawler/build_tables.py): the campaign's stages with
 * their waves and bosses, the enemies, the AI presets. Read through these pointers / the RAM copy (gdata_init), so a
 * lab can swap a table while the game runs, as route_tab does for the chain routes. */
const gstage_t *gstages;
const genemy_t *genemies;
const gstagex_t *gstagex;
static gstagex_t gsx_old[GS_COUNT];              /* a pack before version 4: the ROM's boss scenes, no triggers */
static uint8_t gen_count = EN_COUNT;             /* enemies in genemies[] */
static void gdata_init(void) {
    uint8_t i, k;
    gstages = gstages_rom; genemies = genemies_rom; gstagex = gstagex_rom;
    for (i = 0; i < AI_COUNT; i++)
        for (k = 0; k < sizeof(ai_preset_t); k++) ((uint8_t *)&ai_presets[i])[k] = ((const uint8_t *)&ai_presets_rom[i])[k];
}
/* ---- the Brawler Lab's write path (gamedata.h gdpack_t): a data pack in lab.pack, checked when the page sends it
 * (lab.load 3) and again as it is installed at the next safe point (gd_apply: a wave's spawn, the boss's, a stage start,
 * the lab's enemy respawn), copied into gd_live and its offsets turned into pointers. Same ROM as the release. ---- */
static uint8_t gd_live[GD_MAX] __attribute__((aligned(4)));
static uint8_t gd_want;                          /* 3: install lab.pack, 4: back to the ROM's tables, at the safe point */
#define GD_OFF(ptr) ((uint32_t)(ptr))            /* a pointer field of a pack: its offset */
static uint8_t gd_head = sizeof(gdpack_t);      /* the header's size: 18 bytes before version 4 */
static uint8_t gd_in(uint16_t size, uint32_t off, uint32_t len, uint8_t even) {   /* [off, off + len) inside the pack */
    return off >= gd_head && off + len <= size && !(even && (off & 1));
}
static uint8_t gd_tree(const uint8_t *p, uint16_t size, uint32_t off) {   /* a route tree (fighter.h rt_head_t) */
    const rt_head_t *t = (const rt_head_t *)(p + off);
    uint8_t n, i, k;
    if (!gd_in(size, off, sizeof(rt_head_t), 1) || t->magic[0] != 'R' || t->magic[1] != 'T' || t->version != TREE_VERSION) return 0;
    n = t->nnodes;
    if (!n || n > 128 || !gd_in(size, off, sizeof(rt_head_t) + n * sizeof(rnode_t), 1)) return 0;
    if (t->root >= n || t->dash >= n || t->nospec >= n || t->hold >= n || t->air_a >= n || t->air_b >= n || t->air_cd >= n || t->pad[0] >= n || t->pad[1] >= n) return 0;
    for (i = 1; i < n; i++) {                       /* node 0: "none" (zeros) */
        const rnode_t *d = RT_NODE(t, i);
        if (d->anim >= ((d->flags & RF_SPECIAL) ? BS_COUNT : BA_COUNT) || d->speed < 0x40 || d->speed > 0x400) return 0;
        for (k = 0; k < RI_N; k++) if (d->next[k] >= n) return 0;
    }
    return 1;
}
static uint16_t gd_voice_off(const uint8_t *p, uint8_t i) {   /* version 3: fighter i's voice table offset (0: none) */
    const gdpack_t *h = (const gdpack_t *)p;
    const uint8_t *q = p + h->roster + BC_COUNT * GD_ROLES(h->version) + 2 * i;
    return (uint16_t)(q[0] << 8 | q[1]);
}
static uint8_t gd_check(const uint8_t *p) {      /* 0, or the check that failed */
    const gdpack_t *h = (const gdpack_t *)p;
    const genemy_t *en;
    const gstage_t *st;
    uint16_t size = h->size, i, k;
    if (h->magic[0] != 'G' || h->magic[1] != 'D') return 1;
    if (h->version != GD_VERSION) return 2;     /* 8: AI rows of 52 bytes (7: route trees version 4; an older pack's trees read the old buttons) */
    gd_head = h->version >= 4 ? sizeof(gdpack_t) : sizeof(gdpack_t) - 2;
    if (size < gd_head || size > GD_MAX) return 3;
    if (h->nstages != GS_COUNT || !h->nenemies || !h->nai) return 4;
    if (!gd_in(size, h->stages, h->nstages * sizeof(gstage_t), 1) || !gd_in(size, h->enemies, h->nenemies * sizeof(genemy_t), 1) ||
        !gd_in(size, h->ai, h->nai * sizeof(ai_preset_t), 0)) return 5;
    en = (const genemy_t *)(p + h->enemies);
    for (i = 0; i < h->nenemies; i++, en++) {
        if (en->base == 0xFF) {
            if (!en->npool || !gd_in(size, GD_OFF(en->pool), en->npool, 0)) return 6;
            for (k = 0; k < en->npool; k++) if (p[GD_OFF(en->pool) + k] >= BC_COUNT) return 6;
        } else if (en->base >= BC_COUNT) return 6;
        if (en->ai >= h->nai || en->attract_ai >= h->nai) return 7;
        if (en->tint != GE_SPAWN && en->tint >= TINT_COUNT) return 8;
        if (en->name) {                          /* a name: 1-10 characters */
            if (!gd_in(size, GD_OFF(en->name), 1, 0)) return 9;
            for (k = 0; k < 11 && GD_OFF(en->name) + k < size && p[GD_OFF(en->name) + k]; k++) ;
            if (!k || k > 10 || GD_OFF(en->name) + k >= size) return 9;
        }
        if (en->pal && !gd_in(size, GD_OFF(en->pal), 32, 1)) return 10;
        if (en->moves && !gd_tree(p, size, GD_OFF(en->moves))) return 11;
    }
    st = (const gstage_t *)(p + h->stages);
    for (i = 0; i < h->nstages; i++, st++) {
        const gwave_t *w = (const gwave_t *)(p + GD_OFF(st->waves));
        const gspawn_t *sp = (const gspawn_t *)(p + GD_OFF(st->spawns));
        if (st->bg >= STAGE_COUNT || !st->nwaves || !gd_in(size, GD_OFF(st->waves), st->nwaves * sizeof(gwave_t), 1) ||
            !gd_in(size, GD_OFF(st->spawns), h->nspawns * sizeof(gspawn_t), 1)) return 12;
        for (k = 0; k < st->nwaves; k++) if (!w[k].n || w[k].n > NF - 2 || w[k].first + w[k].n > h->nspawns) return 13;
        if (st->boss >= h->nenemies || st->nmin > NF - 3 || st->boss_first + st->nmin > h->nspawns) return 14;
        for (k = 0; k < h->nspawns; k++) if (sp[k].enemy >= h->nenemies || sp[k].tint >= TINT_COUNT) return 15;
    }
    if (h->version >= 2 && h->roster) {         /* the specials by role: each an index in its fighter's pool, or none */
        uint8_t nr = GD_ROLES(h->version);
        if (!gd_in(size, h->roster, BC_COUNT * nr, 0)) return 16;
        for (i = 0; i < BC_COUNT; i++)
            for (k = 0; k < nr; k++) if (p[h->roster + i * nr + k] != 0xFF && p[h->roster + i * nr + k] >= bm_chars[i].nspec) return 16;
    }
    if (h->version >= 3 && h->roster) {         /* the voices: per fighter a table offset (0: the ROM's), ids within its list */
        if (!gd_in(size, h->roster + BC_COUNT * GD_ROLES(h->version), BC_COUNT * 2, 0)) return 17;
        for (i = 0; i < BC_COUNT; i++) {
            uint16_t o = gd_voice_off(p, i), n = VK_SPEC + bm_chars[i].nspec;
            if (!o) continue;
            if (!gd_in(size, o, n * 2, 0)) return 17;
            for (k = 0; k < n; k++) if (p[o + 2 * k] > bm_chars[i].nvoice) return 17;
        }
    }
    if (h->version >= 4) {                       /* the stages' triggers and boss scenes */
        const gstagex_t *x = (const gstagex_t *)(p + h->stagex);
        if (!gd_in(size, h->stagex, h->nstages * sizeof(gstagex_t), 1)) return 18;
        for (i = 0; i < h->nstages; i++, x++) {
            const gtrigger_t *t = (const gtrigger_t *)(p + GD_OFF(x->trig));
            if (x->ntrig > 32 || (x->drama != 0xFF && x->drama >= DR_COUNT)) return 18;
            if (x->ntrig && !gd_in(size, GD_OFF(x->trig), x->ntrig * sizeof(gtrigger_t), 1)) return 19;
            for (k = 0; k < x->ntrig; k++, t++)
                if (!t->when || t->when > TW_TIME || !t->action || t->action > TA_END ||
                    (t->action == TA_SPAWN && (!t->n || t->n > NF - 2 || t->sp.enemy >= h->nenemies || t->sp.tint >= TINT_COUNT)) ||
                    (t->action == TA_DRAMA && t->arg >= DR_COUNT)) return 19;
        }
    }
    return 0;
}
static void gd_apply(void) {                     /* at a safe point: the pack (or the ROM's tables) in use from now */
    if (gd_want == 4) { gstages = gstages_rom; genemies = genemies_rom; gstagex = gstagex_rom; ai_tab = ai_presets; gen_count = EN_COUNT; specs_init(); voices_init(); lab.pack_stat = GD_ROM; }
    else if (gd_want == 3) {
        uint8_t e = gd_check(lab.pack);
        if (e) lab.pack_stat = GD_BAD | e;
        else {
            const gdpack_t *h = (const gdpack_t *)gd_live;
            uint32_t base = (uint32_t)gd_live;
            genemy_t *en; gstage_t *st;
            uint16_t i;
            for (i = 0; i < ((const gdpack_t *)lab.pack)->size; i++) gd_live[i] = lab.pack[i];
            en = (genemy_t *)(gd_live + h->enemies);
            for (i = 0; i < h->nenemies; i++, en++) {
                if (en->pool) en->pool = (const uint8_t *)(base + GD_OFF(en->pool));
                if (en->name) en->name = (const char *)(base + GD_OFF(en->name));
                if (en->pal) en->pal = (const uint16_t *)(base + GD_OFF(en->pal));
                if (en->moves) en->moves = (const uint8_t *)(base + GD_OFF(en->moves));
            }
            st = (gstage_t *)(gd_live + h->stages);
            for (i = 0; i < h->nstages; i++, st++) {
                st->waves = (const gwave_t *)(base + GD_OFF(st->waves)); st->spawns = (const gspawn_t *)(base + GD_OFF(st->spawns));
            }
            gstages = (const gstage_t *)(gd_live + h->stages); genemies = (const genemy_t *)(gd_live + h->enemies);
            ai_tab = (const ai_preset_t *)(gd_live + h->ai); gen_count = h->nenemies;
            if (h->roster) for (i = 0; i < BC_COUNT; i++) spec_tab[i] = gd_live + h->roster + i * BS_COUNT;
            else specs_init();                   /* version 1: the ROM's specials by role */
            voices_init();                       /* version 3: a fighter's voice table from the pack (0: the ROM's) */
            if (h->version >= 3 && h->roster)
                for (i = 0; i < BC_COUNT; i++) { uint16_t o = gd_voice_off(gd_live, i); if (o) voice_tab[i] = gd_live + o; }
            if (h->version >= 4) {               /* version 4: the pack's triggers */
                gstagex_t *x = (gstagex_t *)(gd_live + h->stagex);
                for (i = 0; i < h->nstages; i++) if (x[i].trig) x[i].trig = (const gtrigger_t *)(base + GD_OFF(x[i].trig));
                gstagex = x;
            } else {
                for (i = 0; i < GS_COUNT; i++) { gsx_old[i] = gstagex_rom[i]; gsx_old[i].trig = 0; gsx_old[i].ntrig = 0; }
                gstagex = gsx_old;
            }
            lab.pack_stat = GD_INSTALLED;
        }
    }
    gd_want = 0;
}
static uint8_t boss_fighter(uint8_t s) { return genemies[gstages[s].boss].base; }   /* bm_chars index of stage s's boss */

/* ---- save data (SNK conventions, sdk neo_backup.h): MVS = the header's backup RAM block (this struct, NEO_BACKUP):
 * the BIOS copies it into battery RAM (its area for our NGH) each time the game hands control back (SYSTEM_RETURN:
 * game over, the ending, the attract's end; measured in our emulator: a change made in a fight and powered off
 * before any return is lost, after one it is there) and restores it at power-on. AES = the memory card through the
 * BIOS CARD call (FCB = NGH $0B00 (crt0.s), sub 0): loaded on the title, written at once after each stage. Checked by magic +
 * sum: anything else (a blank block, another build's) = a fresh save. ---- */
typedef struct {
    uint8_t  dips[2];                            /* SNK: the backup block starts with the debug dipswitches */
    char     magic[4];                           /* "BRW2" (format 2; "BRW1" = format 1, read and upgraded) */
    uint8_t  furthest;                           /* the campaign stage reached, 0-4 (the title's CONTINUE until 2026-10-15:
                                                    Bruno "there is no resume: every new game starts from stage 1"; kept
                                                    for the format, no longer written or read) */
    uint8_t  unlocked;                           /* bit k: BOSS[k] beaten (selectable) */
    uint8_t  difficulty;                         /* format 2: AES OPTIONS difficulty 0-3 (format 1: 0, a spare) */
    uint8_t  rungs;                              /* the unlock ladder's rungs unlocked (game.json unlocks: one a game clear;
                                                    a spare 0 before 2026-10-15: same format, nothing unlocked) */
    uint8_t  cheat;                              /* bit 0: the select screen's cheat entered (note 20261016-100558-e03d: every
                                                    game then starts with the meter at its maximum and the fury unlocked;
                                                    a spare 0 before: same format) */
    uint8_t  pad[3];
    uint16_t sum;
} save_t;
NEO_BACKUP save_t save;
uint8_t card_answer;                             /* AES: the last CARD answer (CARD_OK, CARD_NONE, ...) */
static const char SAVE_MAGIC[4] = { 'B', 'R', 'W', '2' };   /* format 1 = "BRW1": same layout, difficulty was a 0 spare */
static uint16_t save_sum(const save_t *s) {
    const uint8_t *p = (const uint8_t *)s + 2;
    uint16_t v = 0x5A5A;
    uint8_t i;
    for (i = 0; i < sizeof(save_t) - 4; i++) v = (uint16_t)((v << 1) | (v >> 15)) + p[i];
    return v;
}
static uint8_t save_ok(save_t *s) {                      /* a format 1 save is upgraded in place (difficulty NORMAL) */
    uint8_t i;
    for (i = 0; i < 3; i++) if (s->magic[i] != SAVE_MAGIC[i]) return 0;
    if ((s->magic[3] != '1' && s->magic[3] != '2') || s->sum != save_sum(s) || s->furthest >= GS_COUNT) return 0;
    if (s->magic[3] == '1') s->difficulty = 1;
    if (s->difficulty > 3) s->difficulty = 1;
    s->magic[3] = '2'; s->sum = save_sum(s);
    return 1;
}
static void save_write(void) {
    save.sum = save_sum(&save);
    if (!BIOS_MVS_FLAG) card_answer = CARD_call(CARD_SAVE, &save, sizeof(save_t), 0);
}
static void save_reset(void) {
    uint8_t i;
    for (i = 0; i < 4; i++) save.magic[i] = SAVE_MAGIC[i];
    save.furthest = 0; save.unlocked = 0; save.difficulty = 1; save.rungs = 0; save.cheat = 0;
    for (i = 0; i < 3; i++) save.pad[i] = 0;
    save.sum = save_sum(&save);
}
static void save_load(void) {
    if (!BIOS_MVS_FLAG) {                        /* AES: the card's copy, when there is one */
        save_t t;
        uint8_t i;
        card_answer = CARD_call(CARD_LOAD, &t, sizeof(save_t), 0);
        if (card_answer == CARD_OK && save_ok(&t))
            for (i = 2; i < sizeof(save_t); i++) ((uint8_t *)&save)[i] = ((const uint8_t *)&t)[i];
    }
    if (!save_ok(&save)) save_reset();
    difficulty = save.difficulty;
}
/* the select screen's cheat (Bruno 2026-10-15, note 20261015-210806-e03d): hold down CHEAT_HOLD frames (a flag), hold up
 * CHEAT_HOLD frames (another flag), either order, either player; both flags = the whole unlock ladder unlocked IN THE
 * SAVE (note 20261015-224121-e03d: 2 s each, "it unlocks the whole ladder and is saved directly, so it's already there;
 * to reset, the player's Reset game save"): save.rungs = every rung, written at once (AES: the memory card; MVS: the
 * backup block, which the BIOS keeps in battery RAM from the next return to it, as the stage clears' rungs) */
#define CHEAT_HOLD 120
static uint8_t cheat_flags;
/* the cheat's game (note 20261016-100558-e03d, "once activated, I also want the player to automatically have maximum
 * meter and the fury unlocked"): saved with the ladder (save.cheat), every new game then has the drive bar at its most
 * chunks (MAX_CHUNKS, as the gauge games' rewards at their cap), both bars full at each stage's start and the fury never
 * locked (fury_lock off, as after the posts); never the attract demo; the player app's Reset game save clears it */
#define CHEAT_GAME (!attract && (save.cheat & 1))
static uint16_t cheat_t[2];
static uint8_t rungs_now(void) { return save.rungs; }
static uint8_t char_locked(uint8_t c) {          /* 0xFF: never picked (a form link's target; with the unlock ladder,
                                                    a fighter off the select screen); $80 + k: the ladder's rung k, until
                                                    k game clears (save.rungs); k: the boss of stage k, until beaten */
    uint8_t k = roster_unlock[c];
    if (k == 0xFF) return 1;
    if (k & 0x80) return (k & 0x7F) > rungs_now();
    return k && !(save.unlocked >> (k - 1) & 1);
}
static uint8_t camp, camp_from;                  /* the stage in play; the one a new game starts at (title CONTINUE) */

/* ---- title banner (tools/brawler/make_banner.py): one sticky sprite chain, BANNER_COLS columns of BANNER_ROWS tiles,
 * its own palette; title screen = banner on black + blinking PRESS START. ---- */
#define BN_SPR 300
#define BN_PAL 250
static void banner_show(int16_t x, int16_t y) {
    uint8_t c, r;
    PAL_setPalette(BN_PAL, banner_pal);
    for (c = 0; c < BANNER_COLS; c++) {
        uint16_t *w = cmd_run(VRAM_SCB1 + (BN_SPR + c) * 64, BANNER_ROWS * 2);
        for (r = 0; r < BANNER_ROWS; r++) { *w++ = banner_map[c * BANNER_ROWS + r]; *w++ = BN_PAL << 8; }
        cmd_push(VRAM_SCB2 + BN_SPR + c, 0x0FFF);
        cmd_push(VRAM_SCB3 + BN_SPR + c, c ? 0x40 : (uint16_t)((((496 - y) & 0x1FF) << 7) | BANNER_ROWS));
        if (!c) cmd_push(VRAM_SCB4 + BN_SPR, (uint16_t)(x & 0x1FF) << 7);
    }
}
static void banner_hide(void) { uint8_t c; for (c = 0; c < BANNER_COLS; c++) cmd_push(VRAM_SCB3 + BN_SPR + c, 0); }

/* title: banner, PRESS START, no menu (START -> the select; console = AES: SELECT opens OPTIONS, see options_tick); A+B+C+D held 2 s clears the save. No CONTINUE STAGE (Bruno 2026-10-15: "There is no
 * resume: every new game starts from stage 1"; the Lab's and the scenarios' starts keep their stage), no ladder line
 * (the unlock ladder shows only after a clear that unlocked a rung). */
static uint16_t title_t, title_hold;
static uint8_t title_sel;                        /* the menu line */
static uint8_t title_paid;                       /* the START that opened the title already took the credit */
enum { TI_NEW, TI_OPT };
static uint8_t title_item[2], title_n;           /* the menu's lines */
static uint16_t title_go;                        /* MVS: ticks of the credit's countdown (title_go_tick) */
static uint8_t title_clr;                        /* MVS: ticks since SAVE DATA CLEARED (then SYSTEM_RETURN commits it) */
static uint8_t opt_on;                           /* the OPTIONS screen is up (a part of the title, mode 2) */
static void select_start(void);
static void ladder_start(void);
static void save_load(void);
static void save_reset(void);
static void save_write(void);
/* a personalized build (make OWNER="..."; tools/brawler/watermark.py header -> owner.h, -include'd): the owner's name
 * under the banner, on the title and the attract logo (rows 20-21, the empty menu rows: title_menu wipes them, so it
 * writes them again). The Player's plain build has no OWNER_NAME: none of this is in it. */
#ifdef OWNER_NAME
static void owner_lines(void) { FIX_print(OWNER_COL1, 20, OWNER_LINE1, 0); FIX_print(OWNER_COL, 21, OWNER_NAME, 0); }
#define OWNER_LINES() owner_lines()
#else
#define OWNER_LINES() ((void)0)
#endif
static void title_menu(void) {
    static const char *const TXT[2] = { "NEW GAME", "OPTIONS" };
    uint8_t i;
    for (i = 0; i < 4; i++) FIX_print(12, 20 + i, "                  ", 0);   /* (4: CONTINUE STAGE and UNLOCKS, until 2026-10-15) */
    OWNER_LINES();
    title_n = 0; title_item[title_n++] = TI_NEW;   /* no menu at all (Bruno 2026-10-15: "when you play Final Fight there
                                                     is no NEW GAME"): PRESS START -> the select; the console's OPTIONS
                                                     open with SELECT on the title (title_tick) */
    title_sel = 0;
    if (title_n == 1) return;
    for (i = 0; i < title_n; i++) {
        FIX_print(12, 20 + i, i == title_sel ? "> " : "  ", 0); FIX_print(14, 20 + i, TXT[title_item[i]], 0);
    }
}
static void title_screen(void) {
    FIX_clear(); arcade_line_reset();
    banner_show((320 - BANNER_COLS * 16) / 2, 56);
    FIX_print(14, 24, "(C) 2027 NEOSAKURAGI", 0);
    FIX_print(17, 15, "V" GAME_VERSION, 0);                 /* VERSION, from the Makefile */
    OWNER_LINES();
}
static void title_start(void) {
    uint8_t i;
    mode = 2; nf = 0; attract = 0; title_t = 0; cam_x = 0; opt_on = 0;
    bd_set(COLOR_BLACK);
    stage_hide();
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    title_screen();
    bios_start = 0;
    snd_music(GAME_MUS_TITLE);                               /* a credit is in: KOF94's coin song (game.json music.title;
                                                             voice note 20261011-114853-5d29) */
    save_load();
    title_sel = 0; title_hold = 0; title_paid = 0; title_clr = 0; title_go = 0;
    title_menu();
}

/* ---- OPTIONS (console only: the AES; an arcade's difficulty is the operator's soft DIP), a 90s SNK options screen on
 * the fix layer: stick up / down picks a line, left / right changes it (held: repeats), A selects / plays, B back
 * (MUSIC PLAYER: B stops the music).
 *   DIFFICULTY    EASY NORMAL HARD MANIAC (life x0.5 x1 x1.5 x2, `life`), saved on leaving (memory card)
 *   MUSIC PLAYER  every song of the build (songs.json -> songs.h SONG_LIST), its driver command
 *   SOUND PLAYER  every effect of the build (SFX_LIST, sent $1A + code), then RAW $01-$FF: C picks the prefix sent
 *                 before the code ($1A effect, $1C voice, none = the bare driver command), for sound debugging
 *   EXIT ---- */
#define OPT_ROW(r) (8 + (r) * 4)
static uint8_t opt_row, opt_song, opt_pfx, opt_rep, opt_diff0;
static uint16_t opt_snd;                         /* < N_SFX: snd_effects[], else RAW code opt_snd - N_SFX + 1 */
#define RAW_N 255                                /* RAW $01-$FF: never $00 (KOF98's NMI drops it and the main loop
                                                    replays a stale ring byte, docs/kof98_sound_driver.md) */
static const char *const DIFF_NAME[4] = { "EASY  ", "NORMAL", "HARD  ", "MANIAC" };
static void hex2(uint8_t col, uint8_t row, uint8_t v) {
    static const char H[] = "0123456789ABCDEF";
    char t[4] = { '$', H[v >> 4], H[v & 15], 0 };
    FIX_print(col, row, t, 0);
}
static void opt_value(uint8_t r) {
    uint8_t y = OPT_ROW(r) + 1;
    if (r == 0) { FIX_print(20, OPT_ROW(0), DIFF_NAME[difficulty], 0); return; }
    if (r == 1) {
        FIX_print(8, y, "                ", 0); FIX_print(8, y, snd_songs[opt_song].name, 0);
        FIX_print(28, y, "CMD", 0); hex2(32, y, snd_songs[opt_song].cmd); return;
    }
    if (r == 2) {
        uint8_t raw = opt_snd >= N_SFX, code = raw ? (uint8_t)(opt_snd - N_SFX + 1) : snd_effects[opt_snd].cmd;
        FIX_print(8, y, "                ", 0); FIX_print(8, y, raw ? "RAW" : snd_effects[opt_snd].name, 0);
        if (!raw || opt_pfx < 2) hex2(28, y, raw && opt_pfx ? 0x1C : SFX_PREFIX); else FIX_print(28, y, "   ", 0);
        hex2(32, y, code);
    }
}
static void opt_cursor(void) {
    uint8_t r;
    for (r = 0; r < 4; r++) FIX_print(4, OPT_ROW(r), r == opt_row ? ">" : " ", 0);
}
static void options_start(void) {
    static const char *const LBL[4] = { "DIFFICULTY", "MUSIC PLAYER", "SOUND PLAYER", "EXIT" };
    uint8_t r;
    opt_on = 1; opt_row = 0; opt_rep = 0; opt_diff0 = difficulty;
    banner_hide(); FIX_clear(); arcade_line_reset();
    FIX_print(16, 4, "OPTIONS", 1);
    for (r = 0; r < 4; r++) { FIX_print(6, OPT_ROW(r), LBL[r], 0); if (r < 3) opt_value(r); }
    FIX_print(4, 23, "STICK CHOOSE / CHANGE   A SELECT", 0);
    FIX_print(4, 24, "B BACK / STOP MUSIC  C RAW PREFIX", 0);
    opt_cursor();
}
static void options_exit(void) {
    opt_on = 0;
    if (difficulty != opt_diff0) { save.difficulty = difficulty; save_write(); }   /* AES: CARD_SAVE at once */
    title_screen(); title_menu();
    snd_music(GAME_MUS_TITLE);
}
static void options_tick(void) {
    uint16_t pr = JOY_pressed(0), h = JOY_held(0);
    int8_t d = 0;
    bios_start = 0;
    if (pr & (JOY_UP | JOY_DOWN)) { opt_row = (opt_row + ((pr & JOY_DOWN) ? 1 : 3)) & 3; opt_cursor(); snd_ssg(SSG_CURSOR); }
    if (pr & (JOY_LEFT | JOY_RIGHT)) { d = (pr & JOY_RIGHT) ? 1 : -1; opt_rep = 0; }
    else if (h & (JOY_LEFT | JOY_RIGHT)) { if (++opt_rep >= 20 && !(opt_rep & 3)) { d = (h & JOY_RIGHT) ? 1 : -1; opt_rep = 16; } }
    else opt_rep = 0;
    if (opt_row == 0 && (pr & JOY_A)) d = 1;
    if (d) {
        if (opt_row < 3) snd_ssg(SSG_CURSOR);
        if (opt_row == 0) difficulty = (difficulty + d) & 3;
        else if (opt_row == 1) opt_song = d > 0 ? (opt_song + 1 < N_SONGS ? opt_song + 1 : 0) : (opt_song ? opt_song - 1 : N_SONGS - 1);
        else if (opt_row == 2) opt_snd = d > 0 ? (opt_snd + 1 < N_SFX + RAW_N ? opt_snd + 1 : 0) : (opt_snd ? opt_snd - 1 : N_SFX + RAW_N - 1);
        if (opt_row < 3) opt_value(opt_row);
    }
    if (opt_row == 2 && (pr & JOY_C)) { opt_pfx = opt_pfx < 2 ? opt_pfx + 1 : 0; opt_value(2); }
    if (pr & JOY_A) {
        if (opt_row == 1) snd_music(snd_songs[opt_song].cmd);
        else if (opt_row == 2) {
            if (opt_snd < N_SFX) { snd_cmd(SFX_PREFIX); snd_cmd(snd_effects[opt_snd].cmd); }
            else { if (opt_pfx < 2) snd_cmd(opt_pfx ? 0x1C : SFX_PREFIX); snd_cmd((uint8_t)(opt_snd - N_SFX + 1)); }
        } else if (opt_row == 3) { options_exit(); snd_ssg(SSG_CANCEL); return; }
    }
    if (pr & JOY_B) {
        if (opt_row == 1) { snd_cmd(0x04); snd_cmd(0x07); }  /* KOF98's driver: $04 stops the music, and the effects
                                                             too (timer A) until a $07 (measured: silent effects) */
        else { options_exit(); snd_ssg(SSG_CANCEL); }
    }
}

/* the credit's countdown (note 20261016-174640-e03d, "just like KOF94"; game.json credit): on an arcade (MVS) the title
 * with a credit in waits at most GAME_CREDIT_START_TICKS, the seconds left shown steady beside the blinking PRESS START
 * (credit.shown), then the game starts as if P1 pressed START: the credit taken (SYS_credit_take: P1's, else P2's coin
 * slot on SNK's BIOS; none when the START that opened the title took it, title_paid), the select. Console (AES): no
 * credits, no timer (credit.mvs_only). Counted in title_go (title_start zeroes it), held while the save is being
 * cleared (title_clr). */
static uint8_t title_go_s, title_go_f;           /* the seconds left (shown), the ticks into this second */
static uint8_t title_go_on(void) {
    return GAME_CREDIT_START_TICKS && (BIOS_MVS_FLAG || !GAME_CREDIT_MVS_ONLY) && !title_clr && !lab.active;
}
static void title_go_show(void) {
    char t[3];
    uint8_t s = title_go_s, d = 0;
    while (s >= 10) { s -= 10; d++; }                    /* (no divide: no libgcc) */
    t[0] = d ? '0' + d : ' '; t[1] = '0' + s; t[2] = 0;
    FIX_print(28, 18, t, 0);
}
static uint8_t title_go_tick(void) {
    if (!title_go_on()) return 0;
    if (!title_go) { title_go_s = (GAME_CREDIT_START_TICKS + 59) / 60; title_go_f = (GAME_CREDIT_START_TICKS - 1) % 60 + 1;
                     if (GAME_CREDIT_START_SHOWN) title_go_show(); }   /* (constants: folded) */
    if (++title_go >= GAME_CREDIT_START_TICKS) {
        if (!title_paid && !SYS_credit_take(CREDITS_P1 ? 1 : 2)) { title_go = 0; return 0; }   /* no credit after all: wait */
        if (GAME_CREDIT_START_SHOWN) FIX_print(28, 18, "  ", 0);
        bios_start = 0; title_paid = 0; camp_from = 0;
        banner_hide(); select_start(); snd_ssg(SSG_CONFIRM); return 1;
    }
    if (!--title_go_f) { title_go_s--; title_go_f = 60; if (GAME_CREDIT_START_SHOWN) title_go_show(); }
    return 0;
}
static void attract_logo_tick(void);
static void title_tick(void) {
    uint16_t pr, h;
    if (attract) { attract_logo_tick(); return; }
    if (opt_on) { options_tick(); return; }
    pr = JOY_pressed(0); h = JOY_held(0);
    if (!(title_t & 31)) FIX_print(15, 18, (title_t & 32) ? "           " : "PRESS START", 0);
    title_t++;
    if (title_n > 1 && (pr & (JOY_UP | JOY_DOWN))) {
        uint8_t was = title_sel;
        if (pr & JOY_DOWN) { if (title_sel + 1 < title_n) title_sel++; } else if (title_sel) title_sel--;
        if (title_sel != was) snd_ssg(SSG_CURSOR);
        title_menu();
    }
    if ((h & (JOY_A | JOY_B | JOY_C | JOY_D)) == (JOY_A | JOY_B | JOY_C | JOY_D)) {   /* held 2 s: the save cleared */
        if (++title_hold == 120) { save_reset(); save_write(); difficulty = save.difficulty; title_menu(); FIX_print(12, 16, "SAVE DATA CLEARED", 0); title_clr = 1; }
        return;
    } else title_hold = 0;
    if (title_clr && ++title_clr >= 90 && BIOS_MVS_FLAG) { title_clr = 0; SYS_return(); return; }   /* MVS: the BIOS writes
                                                             the cleared block to battery RAM when the game hands back
                                                             (the title again while credits remain) */
    if (!BIOS_MVS_FLAG && (pr & JOY_SELECT)) {         /* console only, no credit involved: SELECT = OPTIONS */
        snd_ssg(SSG_CONFIRM); options_start(); return;
    }
    if (title_go_tick()) return;                       /* MVS: the credit's countdown ran out: the game starts */
    if (bios_start || (title_paid && (pr & (JOY_START | JOY_A)))) {   /* START with a credit (PLAYER_START), or START / A
                                                             when the credit was taken by the START that opened it */
        bios_start = 0; title_paid = 0; camp_from = 0;   /* (every new game: stage 1) */
        banner_hide(); select_start(); snd_ssg(SSG_CONFIRM); return;   /* the cue after the song start: queued
                                                             before it, the driver's song start stretches its first note */
    }
}

/* ---- character select: a group photo (Bruno 2026-10-05, TODO #51), since 2026-10-09 out in the street in front of
 * SNK's Neo Geo Land (KOF95's stage 2, "the select screen's backdrop" above): the whole roster stands along the street
 * (game.json select_layout: world x 0-767, three depth rows, facings mixed), the camera following the cursor (sel_camera),
 * everyone at once (a locked boss is a
 * dark silhouette, not selectable; once beaten it is in colour / dark like the others). Each fighter holds its 'watch'
 * pose (export_bm.WATCH: a front-facing frame from its intros / win poses), facing as the layout says. The places are
 * slots (SEL_SLOT: x, y, z, face), independent of who stands in them (sel_fighter: the fighter of each slot), so moving
 * someone on screen is a change to game.json's select_layout only. The cursor's fighter shows its colours, the others their own
 * colours at half brightness (col_dark). "1P" / "2P" with an arrow above the selected head (fix layer). The stick follows
 * the cursor graph computed from the places (sel_stick, TODO #187; select.stick "order": left / right along the street, up / down to the
 * nearest row above / below); A/B/C/D picks that colour set
 * (KOF style) and plays the win pose. P2 joins here with START (a credit) and picks too; the two can't pick the same
 * fighter. When everyone in has picked, the others walk off the screen outward, then the
 * fight cuts in (no fades: a palette fade cost ticks frames). Each fighter on screen is an entity (actor): the fight's NE entities + NA - NE more. ---- */
#define SHOW_Z 40                        /* BOSS UNLOCKED / ending: feet at SELECT_FLOOR + SHOW_Z */
_Static_assert(SEL_NSLOT <= NA, "group photo: an actor per slot (every selectable fighter has one: build_tables.py)");
_Static_assert(SPR_BASE + FIGHT_SPRS <= 300, "sprite blocks: fight below the banner (the select's: SEL_SPR, with the Neo Geo Land around them)");
/* the slots (game.json select_layout, placed by Bruno in the Brawler Lab's Select screen tab; build_tables.py
 * select_layout, gamedata.h sel_slot_t), in the stick's order: x, y (the feet, px), z (the draw order, 0 the back:
 * depth_sort), face (1 right, -1 left), sel_fighter[slot] = who stands there (the generator checks every selectable
 * roster fighter has one). No select_layout block: the first layout (rows, everyone facing the middle). */
enum { SEL_CHOOSE, SEL_LEAVE };
static uint8_t cursor[2], picked[2], pick_set[2];   /* cursor: a slot (0xFF: that player isn't in) */
static uint8_t sel_phase;
static uint16_t sel_t;
static uint8_t slot_ch[SEL_NSLOT];       /* the fighter (bm_chars index) in each slot, 0xFF empty */
static uint8_t slot_act[SEL_NSLOT];      /* the actor showing it */
static uint8_t sel_lay, sel_base, sel_cnt;   /* the layout in use (build_tables.py select_layers; Bruno 2026-10-15: "only the
                                            available characters show up"): with the unlock ladder layer save.rungs, its
                                            sel_cnt fighters = slots 0 .. sel_cnt - 1 (the unlocked ones: the others are not
                                            drawn), slot s at the place SEL_SLOT[sel_base + s] (the layer's own places: game.json select.auto spreads them, no overlap; the camera inside sel_lay_cam);
                                            without it one layer, every slot (a locked boss: a silhouette) */
static fighter_t sel_extra[NA - NE];     /* actors NE.. (the fight's entities are actors 0..NE-1) */
static fighter_t *actor(uint8_t a) { return a < NF ? &fighters[a] : a < NE ? &projectiles[a - NF] : &sel_extra[a - NE]; }
/* the unlocked fighters in CHARS order (the attract demo's players): the select screen's own set, char_locked (with the
 * unlock ladder: the starters + the rungs save.rungs unlocked, the cheat's included; note 20261016-173135-e03d, "only
 * show playable characters that have been unlocked — Haggar [...] must stay a surprise until unlocked in the ladder") */
static uint8_t lu[BC_COUNT], lu_n;
static uint8_t char_locked(uint8_t c);
static void roster_build(void) {
    uint8_t c;
    lu_n = 0;
    for (c = 0; c < BC_COUNT; c++) if (!char_locked(c)) lu[lu_n++] = c;
}
static void slots_build(void) {
    uint8_t s;
    for (s = 0; s < SEL_NSLOT; s++) slot_ch[s] = sel_fighter[s];
}
static uint8_t selectable(uint8_t s) { return s < sel_cnt && slot_ch[s] != 0xFF && !char_locked(slot_ch[s]); }
static uint8_t arrow_col[2] = { 0xFF, 0xFF }, arrow_row[2];

static uint16_t col_dark(uint16_t c) {                      /* its own colour at half brightness: each 5-bit channel
                                                             halved (TODO #210, Bruno: "their real colors, but just much
                                                             darker"; was half way to the luminance grey). Kizuna's
                                                             waiting partner, measured in our emulator: its palette RAM
                                                             = its active palette (no transform to copy) */
    uint8_t r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
    return RGB(r >> 1, g >> 1, b >> 1);
}
#define SILHOUETTE RGB(4, 4, 5)
#define SILHOUETTE_B RGB(8, 8, 10)                   /* the ladder's every other silhouette: overlapping ones stay apart */
/* an entity's palettes: its own colours (1), darkened (0), a silhouette (2; 4 a lighter one) or white (3: the ladder's reveal flash) */
static void fighter_pals(const fighter_t *f, uint8_t colour) {
    uint16_t buf[16];
    uint8_t i, j;
    for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) {
        const uint16_t *src = fighter_src_pal(f, i);
        buf[0] = src[0];
        for (j = 1; j < 16; j++)
            buf[j] = colour == 3 ? RGB(31, 31, 31) : colour == 2 ? SILHOUETTE : colour == 4 ? SILHOUETTE_B : colour ? fighter_colour(f, src[j]) : col_dark(src[j]);
        PAL_setPalette(f->palbase + i, buf);
    }
}
static uint8_t chosen(uint8_t s) { return s == cursor[0] || s == cursor[1]; }
static uint8_t slot_look(uint8_t s) { return char_locked(slot_ch[s]) ? 2 : chosen(s); }
static void slot_show(uint8_t s, uint8_t set) {             /* (re)binds slot s's actor: its fighter, colour set, pose */
    uint8_t a = slot_act[s];
    fighter_t *f = actor(a);
    const bchar_t *ch = &bm_chars[slot_ch[s]];
    fighter_init(f, ch, set < ch->nsets ? set : 0, sel_palbase[s], 1, SEL_SLOT[sel_base + s].x, SEL_SLOT[sel_base + s].y - SELECT_FLOOR);
    f->idx = a; f->facing = SEL_SLOT[sel_base + s].face; sel_rank[a] = SEL_SLOT[sel_base + s].z;
    fighter_play(f, BA_WATCH);
    fighter_pals(f, slot_look(s));
}
/* the cursor from slot s (TODO #187): the build's cursor graph, from the fighters' places (build_tables.py
 * select_stick: rows by body centre). Right / left: sel_stick[s] = the next / previous along the row and on to the next
 * row (one loop through everyone), followed on past a locked slot. Up / down: sel_vert[s] = the slots of the rows that
 * way in preference (the nearest row first, each by x distance; wrapping), the first selectable one. None: stay. */
static uint8_t sel_move(uint8_t s, uint16_t pr) {
    uint8_t d = (pr & JOY_RIGHT) ? 0 : (pr & JOY_LEFT) ? 1 : (pr & JOY_UP) ? 2 : (pr & JOY_DOWN) ? 3 : 4, t = s, n;
    if (d < 2) {
        for (n = 0; n < SEL_NSLOT; n++) {
            t = sel_stick[sel_lay][t][d];
            if (t == s) break;
            if (selectable(t)) return t;
        }
    } else if (d < 4) {
        for (n = 0; n < SEL_NSLOT - 1; n++) {
            t = sel_vert[sel_lay][s][d - 2][n];
            if (t == 0xFF) break;
            if (selectable(t)) return t;
        }
    }
    return s;
}
static void select_arrows(void) {                           /* "1P" / "2P" + arrow over the selected head */
    uint8_t p, col[2], row[2];
    for (p = 0; p < 2; p++) {
        uint8_t s = cursor[p];
        col[p] = 0xFF; row[p] = 0;
        if (s != 0xFF) {
            /* the pose's head point (bm_head, TODO #157: export_bm.py / head_point.py, facing left; the actor faces
             * the middle: mirrored when it faces right); the arrow's 8 px cell centred on it, ending 2 px above it */
            const int8_t *hd = bm_head[slot_ch[s]];
            int16_t sx = SEL_SLOT[sel_base + s].x - cam_x + (SEL_SLOT[sel_base + s].face > 0 ? -hd[0] : hd[0]) - 4 + (p && cursor[0] == s ? 16 : 0);   /* both on one fighter: 2P to the right */
            int16_t sy = SEL_SLOT[sel_base + s].y + hd[1] - 10;
            if (sx < 0 || sx > 304) continue;                  /* off the screen (the street scrolls): none */
            col[p] = (uint8_t)((sx + 4) >> 3);                 /* FIX_print col c / row r = screen x c * 8, y r * 8 */
            row[p] = sy < 32 ? 4 : (uint8_t)((sy + 4) >> 3);       /* (rows 1-2: the title and the name; "1P" one row above) */
        }
    }
    if (col[0] == arrow_col[0] && row[0] == arrow_row[0] && col[1] == arrow_col[1] && row[1] == arrow_row[1]) return;
    for (p = 0; p < 2; p++)
        if (arrow_col[p] != 0xFF) { FIX_print(arrow_col[p], arrow_row[p] - 1, "  ", 0); FIX_print(arrow_col[p], arrow_row[p], " ", 0); }
    for (p = 0; p < 2; p++) {
        if (col[p] != 0xFF) { FIX_print(col[p], row[p] - 1, p ? "2P" : "1P", 0); FIX_setTile(col[p], row[p], ARROW_TILE, 0); }
        arrow_col[p] = col[p]; arrow_row[p] = row[p];
    }
}
static void name_at(uint8_t col, uint8_t row, uint8_t right, uint8_t s) {
    const char *n = s == 0xFF ? "" : bm_chars[slot_ch[s]].name;
    uint8_t len = 0;
    while (n[len]) len++;
    FIX_print(right ? 39 - len : col, row, n, 0);
}
static void select_name(void) {                             /* top: P1's fighter (centred, or left with P2 in), P2's right */
    FIX_print(0, 2, "                                        ", 0);
    if (cursor[1] == 0xFF) { const char *n = bm_chars[slot_ch[cursor[0]]].name; uint8_t len = 0; while (n[len]) len++; FIX_print(20 - (len >> 1), 2, n, 0); }
    else { name_at(1, 2, 0, cursor[0]); name_at(0, 2, 1, cursor[1]); }
}
/* the camera along the street (Bruno 2026-10-09: "make the camera follow the highlighted character"): P1's cursor
 * centred, the two cursors' midpoint once P2 is in (when the two fit on the screen: SEL_BOTH_W apart at most; else the
 * cursor that moved last), inside the stage (0 .. LAND_CAM_MAX); eased, 1/4 of the way a tick. P2 joins on the
 * selectable fighter nearest P1's. */
#define SEL_BOTH_W 224
static uint8_t sel_last;                                  /* the player whose cursor moved last */
static int16_t sel_cam_goal(void) {
    int16_t a = SEL_SLOT[sel_base + cursor[0]].x, b = cursor[1] == 0xFF ? a : SEL_SLOT[sel_base + cursor[1]].x, g;
    g = (b > a ? b - a : a - b) <= SEL_BOTH_W ? (a + b) >> 1 : SEL_SLOT[sel_base + cursor[sel_last]].x;   /* too far apart for one */
    g -= 160;                                                                                  /* screen: the last mover's */
    if (g < sel_lay_cam[sel_lay][0]) g = sel_lay_cam[sel_lay][0];   /* the layer's range (build_tables select_cams: inside the */
    if (g > sel_lay_cam[sel_lay][1]) g = sel_lay_cam[sel_lay][1];   /* street, along the group; lo = hi: it fits, fixed) */
    return g;
}
static void sel_camera(void) {
    int16_t d = sel_cam_goal() - cam_x, st = d >> 2;
    if (!d) return;
    if (!st) st = d > 0 ? 1 : -1;
    cam_x += st;
}
static void select_start(void) {
    uint8_t p, i, s, a = 0;
    mode = 0; sel_t = 0; sel_phase = SEL_CHOOSE; attract = 0;
    inputs_reset();
    snd_music(GAME_MUS_SELECT);
    FIX_clear(); arcade_line_reset();
    stage_hide();                                            /* stage sprites hidden */
    land_start();                                            /* the Neo Geo Land behind (its backdrop, palettes, speed) */
    floor_top = SELECT_FLOOR;
    dbg_init();
    FIX_print(10, 1, "SELECT YOUR FIGHTER", 0);           /* FIX_print row r = screen y r * 8 (rows 0-27) */
    FIX_print(3, 26, "STICK MOVES   A B C D PICK COLOURS", 0);   /* under the front row's feet (y 206) */   /* keyboard: WASD, U I O P */
    for (p = 0; p < 2; p++) { picked[p] = 0; pick_set[p] = 0; arrow_col[p] = 0xFF; }
    sel_lay = LAD_N ? (rungs_now() < LAD_RUNGS ? rungs_now() : LAD_RUNGS) : 0;   /* (LAD_RUNGS + 1 layers: select_layers) */
    sel_cnt = sel_lay_n[sel_lay]; sel_base = sel_lay_base[sel_lay];
    slots_build(); roster_build();
    for (s = 0; s < SEL_NSLOT && !selectable(s); s++) ;
    cursor[0] = s; cursor[1] = 0xFF; sel_last = 0;           /* the first selectable slot (Terry); P2: START joins */
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    for (i = 0; i < NA; i++) { actor(i)->state = S_OFF; order[i] = actor(i); }
    for (s = 0; s < SEL_NSLOT; s++) { slot_act[s] = 0xFF; if (s < sel_cnt && slot_ch[s] != 0xFF) { slot_act[s] = a++; slot_show(s, 0); } }   /* (only the layer's) */
    nf = NA;
    cam_x = sel_cam_goal(); select_name();                  /* the camera on the cursor at once, then eased (sel_camera) */
}
/* ---- campaign (Bruno 2026-10-05, Streets of Rage 2 / Golden Axe style): the stages of game.json in order (gstages[]:
 * today Robo Army's horizontal ones, stages[] 0, 1, 3, 4, 5; 2, the 512 px boss arena, is not used). Each stage scrolls
 * through its waves' lock points (camera x): at a lock point the camera stops until the wave there is beaten, then GO
 * blinks and the camera may scroll on to the next one (never back), the last one the boss's. A wave's spawns (at most
 * NF - 2 = 6) are enemies (genemies[]): a fixed fighter or one of a pool (the fighters nobody picked: pick mod the pool
 * left), at a world x or walking in from off screen (the right, or the left when there is room); the stage's enemies
 * land `power` extra damage a hit. At the stage's end its boss comes in with its minions (at most 5, in minion colours:
 * fighter_colour's tints, never a playable colour set); the boss bar under the HUD; boss beaten: the minions go down,
 * STAGE CLEAR, the save (boss unlocked, the ladder's rung), BOSS UNLOCKED when its fighter was locked, a cut to the next
 * stage. After the last: the ending ("the ending"), then the title. Players: 3 lives, then the continue ("continue and GAME OVER"
 * below). The attract demo plays the first stage's waves on background STAGE (make STAGE=n,
 * stages[] index) without a boss, the last wave again and again. ---- */

static uint8_t unlock_k;                         /* the boss just unlocked + 1 (0 none) */
static uint8_t lad_new;                          /* the unlock ladder's rung this game clear unlocked (0 none) */
static void ladder_start(void);
static uint16_t phase_t;
static const gstage_t *gs;                       /* the stage playing: gstages[camp] */
static uint8_t power;                            /* this stage's enemies' extra damage */
static uint8_t pl_ch[2], pl_set[2], pl_on[2];   /* the players, carried from stage to stage (pl_on: in play) */

static uint8_t mod8(uint8_t a, uint8_t b) { while (a >= b) a -= b; return a; }   /* no libgcc: no 32-bit % */
static void hud_wave(void) {
    const char *n = gstage_names[camp];                  /* game.json stages[].name, 1-12 characters (the Factory's Levels) */
    uint8_t x = 2;
    FIX_print(2, 26, n, 0);
    while (*n++) x++;                                    /* "STAGE 1 WAVE 1": the wave after the name */
    FIX_print(x, 26, " WAVE   ", 0);
    if (phase >= PH_BOSS) FIX_print(x + 1, 26, "BOSS ", 0); else FIX_printNum(x + 6, 26, wave + 1, 0);
}
static int16_t lock_at(int16_t x) { int16_t m = world_w - 320; return x > m ? m : x; }   /* inside the background shown */
static uint8_t ai_of(const genemy_t *en) { return attract ? en->attract_ai : en->ai; }
/* a boss's own AI layer (T9, game.json enemies[].boss_ai -> gbossai_rom): its definition's, by its index in the ROM's
 * enemies; a pack's enemy (the Lab) takes the ROM boss of the same fighter's. The attract demo: none (it has no boss) */
static const gbossai_t *boss_ai_of(const genemy_t *en) {
    uint8_t k;
    if (attract) return 0;
    for (k = 0; k < EN_COUNT; k++) if (en == &genemies_rom[k]) return gbossai_rom[k];   /* (no pointer division: no __mulsi3) */
    for (k = 0; k < EN_COUNT; k++) if (gbossai_rom[k] && en->base != 0xFF && genemies_rom[k].base == en->base) return gbossai_rom[k];
    return 0;
}
/* an enemy from its definition: its fighter c, its colours (its own set / tint when it has one, else the spawn's; its
 * custom colours), its HUD name, its route tree, life and power */
static void enemy_init(uint8_t slot, uint8_t c, uint8_t set, int16_t x, int16_t z, uint8_t tint, const genemy_t *en) {
    fighter_t *e = &fighters[slot];
    if (x < 16) x = 16;
    if (x > world_w - 16) x = world_w - 16;
    if (en->set != GE_SPAWN) set = en->set;
    if (en->tint != GE_SPAWN) tint = en->tint;
    fighter_init(e, &bm_chars[c], mod8(set, bm_chars[c].nsets), 16 + slot * MAX_PALS, 1, x, z);
    e->idx = slot; e->power = power + en->power + (attract ? 0 : ai_rank_power()); e->tint = tint;   /* (+ the rank's) */
    e->dout = (en->flags & GE_DOUT) >> GE_DOUT_SH;            /* (its damage_out: every hit, throw, chip and thrown body) */
    e->name = en->flags & GE_FIGHTER_NAME ? 0 : en->name; e->cpal = en->pal; e->tree = (const rt_head_t *)en->moves;
    if (!attract) e->hp = e->hp_max = life(en->life);     /* the campaign's difficulty (the demo: as it was) */
    if (tint || e->cpal) pal_pend |= 1 << slot;             /* (its colours: pal_pend_tick, before it can show) */
}
/* (CPU budget B, docs/brawler_cpu_budget.md: the boss's 5 tinted minions loaded at once took 4 frames) a spawned enemy's
 * tinted / custom palettes load in draw, after its tiles: at once when one of its columns would show on the screen this
 * frame (its placement's X words; the line guard places nothing beyond -128 .. 448) or one of its effects is out, else
 * one waiting enemy a tick: its palettes are never seen before they are its own (the walk-ins wait 24-96 px off the
 * screen through the boss's scene). A burn, a flash or an overlay meanwhile owns them (its end loads them) */
static uint8_t on_screen(fighter_t *f) {
    uint16_t y[MAX_COLS], x[MAX_COLS];
    uint8_t c, n = f->ncols, ob;
    int16_t sx = INT(f->x) - cam_x, cx;
    if (f->state == S_OFF || !n || sx < -128 || sx > 448) return 0;
    ob = BANK_set(CH_BANK(f->ch)); trim_cur = &col_trim[f->idx]; fighter_place(f, y, x, cam_x, n); BANK_set(ob);
    for (c = 0; c < n; c++)
        if (y[c] & 63) {
            cx = (int16_t)(x[c] >> 7) - sx;
            cx = sx + (((cx + 256) & 511) - 256);                /* (9-bit X, unwrapped around the fighter, as land_clip) */
            if (cx > -16 && cx < 320) return 1;
        }
    return 0;
}
static void pal_pend_tick(void) {
    uint8_t i, done = 0, k, near;
    for (i = 2; i < NF; i++) {
        fighter_t *f = &fighters[i];
        if (!(pal_pend & (1 << i))) continue;
        if (f->burn || f->flash || f->ovl) { pal_pend &= ~(1 << i); continue; }
        near = on_screen(f);
        for (k = 0; k < NPJ && !near; k++)
            if (projectiles[k].state != S_OFF && projectiles[k].owner == f) near = 1;
        if (near || !done) { fighter_load_pals(f); done = 1; }
    }
}
static int16_t spawn_x(const gspawn_t *sp) {     /* off screen: the right, or the left (SP_LEFT) when there is room */
    int16_t r = (sp->flags >> 4) * 36;
    if (!(sp->flags & SP_WALK_IN)) return sp->x;
    if ((sp->flags & SP_LEFT) && cam_x >= 64) return cam_x - 24 - r;
    return cam_x + 340 + r;
}
static uint8_t pool_pick(const genemy_t *en, uint8_t pick, uint8_t avoid) {   /* the pool without the players' fighters */
    uint8_t av[BC_COUNT], n = 0, i, c, m;
    for (i = 0; i < en->npool; i++) {
        c = en->pool[i];
        if (!(pl_on[0] && c == pl_ch[0]) && !(pl_on[1] && c == pl_ch[1])) av[n++] = c;
    }
    m = mod8(pick, n);
    if (av[m] == avoid) m = mod8(m + 1, n);                /* SP_NOT_BOSS: not the boss's own fighter */
    return av[m];
}
/* (CPU budget B) on the way to the boss: the colour sets boss_start will give the boss and its minions (enemy_init's
 * set / tint / custom colours, spawn's pool pick), tinted one palette a tick (fighter.c fighter_pretint) */
static uint8_t bp_keyed;                         /* the keys named for this walk (boss_start clears it) */
static void boss_pretint(void) {
    const genemy_t *be = &genemies[gs->boss], *en;
    uint8_t k, c = be->base, ch, set;
    if (!bp_keyed) {
        bp_keyed = 1;
        set = c == pl_ch[0] && !pl_set[0] ? 1 : 0;
        if (be->set != GE_SPAWN) set = be->set;
        fighter_pretint(0, &bm_chars[c], mod8(set, bm_chars[c].nsets), be->tint != GE_SPAWN ? be->tint : 0, be->pal);
        for (k = 0; k < gs->nmin && k < NF - 3; k++) {
            const gspawn_t *sp = &gs->spawns[gs->boss_first + k];
            en = &genemies[sp->enemy];
            ch = en->base != 0xFF ? en->base : pool_pick(en, sp->pick, sp->flags & SP_NOT_BOSS ? c : 0xFF);
            set = en->set != GE_SPAWN ? en->set : sp->set;
            fighter_pretint(1 + k, &bm_chars[ch], mod8(set, bm_chars[ch].nsets), en->tint != GE_SPAWN ? en->tint : sp->tint, en->pal);
        }
    }
    fighter_pretint_step();
}
static void spawn(uint8_t slot, const gspawn_t *sp, uint8_t boss_c) {
    const genemy_t *en = &genemies[sp->enemy];
    uint8_t c = en->base != 0xFF ? en->base : pool_pick(en, sp->pick, sp->flags & SP_NOT_BOSS ? boss_c : 0xFF);
    enemy_init(slot, c, sp->set, spawn_x(sp), sp->z, sp->tint, en);
}
/* the spawns' AI: every slot the first spawn's preset (ai_init, the RNG seeded), then any other spawn's its own; an enemy
 * with an AI layer (game.json enemies[].boss_ai: its guard, runs, strings) plays it, a wave's too (2026-10-16: the enemies'
 * wide range of moves) */
static void spawns_ai(uint16_t seed, const gspawn_t *sp, uint8_t n, uint8_t slot0) {
    uint8_t k, p0 = n ? ai_of(&genemies[sp[0].enemy]) : AI_MINION, p;
    const gbossai_t *b;
    ai_init(seed, p0);
    for (k = 0; k < n; k++) {
        if ((p = ai_of(&genemies[sp[k].enemy])) != p0) ai_set(slot0 + k, p);
        if ((b = boss_ai_of(&genemies[sp[k].enemy])) != 0) ai_boss(slot0 + k, b);
    }
}
/* ---- drama mode (docs/brawler_data_model.md "Drama mode"): black bars slide in from the top and the bottom (fix rows
 * 0-3 and 20-27, DRAMA_FONT's opaque cells), the fight held (no AI, no update, no flow: game_tick only draws), each scene's
 * big portrait (portraits_big.h: sprites PB_SPR.., the box viewer's, palettes PB_PALN..) slides in on its speaker's side
 * (left: mirrored), the name plate and the lines typed on the bottom bar; A-D / START: the rest of the text at once, then
 * the next scene; else each scene goes on after its wait. Then the bars slide out, the HUD comes back, the song (a
 * boss's) starts. ---- */
#define PB_SPR  300
#define PB_PALN 240                      /* palettes 240-249 (PB_MAXPAL 10: KOF99's portraits; 248-249 = SF_RAYS_PAL /
                                            SF_GLOW_PAL, set again by each super flash) */
#define DR_PY   24                       /* the portrait's top on screen (its first rows under the top bar) */
enum { DR_OFF, DR_IN, DR_SCENE, DR_OUT };
static uint8_t dr_on, dr_scene, dr_music, dr_rows, dr_pb, dr_side, dr_slide;
static const gdrama_t *dr;
static uint16_t dr_t, dr_chars, dr_len;
static void dr_row(uint8_t row, uint16_t v) { uint8_t c; for (c = 0; c < 40; c++) fix_put(c, row, v); }
static void dr_bar(uint8_t st, uint8_t on) {    /* step 1-8: bottom row 28 - st, on even steps top row st / 2 - 1 */
    uint16_t v = on ? DRAMA_FONT + ' ' : 0x20;
    dr_row(28 - st, v);
    if (!(st & 1)) dr_row((st >> 1) - 1, v);
}
static void pb_hide(void) {
    uint8_t c;
    for (c = 0; c < dr_cols; c++) cmd_push(VRAM_SCB3 + PB_SPR + c, 0);
    dr_cols = 0;
}
static void pb_place(int16_t off) {              /* off: px still to slide in from the speaker's edge */
    uint16_t *w;
    int16_t x0 = dr_side ? 312 - dr_cols * 16 + off : 8 - off;
    uint8_t c;
    w = cmd_run(VRAM_SCB3 + PB_SPR, dr_cols);
    for (c = 0; c < dr_cols; c++) w[c] = (uint16_t)(((496 - DR_PY) & 0x1FF) << 7) | dr_rows;
    w = cmd_run(VRAM_SCB4 + PB_SPR, dr_cols);
    for (c = 0; c < dr_cols; c++) w[c] = (uint16_t)((x0 + c * 16) & 0x1FF) << 7;
}
static void pb_show(uint8_t pb, uint8_t side) {  /* its palettes and tiles; placed off screen (pb_place slides it) */
    const pbig_t *b = &pbig[pb];
    uint8_t c, r;
    const uint32_t *m0 = b->map, *m;
    for (c = 0; c < b->npal; c++) PAL_setPalette(PB_PALN + c, b->pal + (c << 4));
    if (!side) for (c = 1; c < b->cols; c++) m0 += b->rows;              /* left: the columns mirrored, from the last */
    for (c = 0; c < b->cols; c++) {
        m = m0;
        if (side) m0 += b->rows; else m0 -= b->rows;
        uint16_t *w = cmd_run(VRAM_SCB1 + (PB_SPR + c) * 64, b->rows * 2);
        for (r = 0; r < b->rows; r++) {
            uint32_t e = m[r];
            *w++ = (uint16_t)e;
            *w++ = e ? (uint16_t)(((PB_PALN + (uint16_t)(e >> 24)) << 8) | ((uint16_t)(e >> 12) & 0xF0) | (((uint16_t)(e >> 20) & 3) ^ (side ? 0 : 1))) : 0;
        }
    }
    dr_cols = b->cols; dr_rows = b->rows; dr_side = side; dr_slide = 16;
    pb_place(160);
}
static void dr_put(uint8_t col, uint8_t row, char ch, uint8_t pal) { fix_put(col, row, (uint16_t)(pal << 12) | (DRAMA_FONT + (uint8_t)ch)); }
static const char *const *dr_lines;              /* the scene's lines as played (a player's own: gscene_t.by) */
static uint8_t dr_nl;
static void dr_text(uint16_t upto) {             /* the scene's characters dr_chars..upto - 1 (lines from row 23, column 3) */
    uint16_t n = 0;
    uint8_t l, c;
    for (l = 0; l < dr_nl; l++)
        for (c = 0; dr_lines[l][c]; c++, n++) if (n >= dr_chars && n < upto) dr_put(3 + c, 23 + l, dr_lines[l][c], 0);
    dr_chars = upto;
}
static const fighter_t *dr_who(const gscene_t *sc) {   /* "$P1": P1, or P2 when P1 is out; "$P2": P2; 0 = skip the scene
                                                          (SC_IF_PORTRAIT: also when that fighter has no big portrait) */
    const fighter_t *f = &fighters[0];
    if (sc->who == DW_P1) f = in_play(&fighters[0]) ? &fighters[0] : in_play(&fighters[1]) ? &fighters[1] : 0;
    else if (sc->who == DW_P2) f = in_play(&fighters[1]) && in_play(&fighters[0]) ? &fighters[1] : 0;
    if (f && (sc->flags & SC_IF_PORTRAIT) && pb_of_fighter[char_index(f->ch)] >= PB_COUNT) f = 0;
    return f;
}
static uint8_t dr_next(uint8_t k) {              /* the first scene from k someone can play (dr->n: none) */
    while (k < dr->n && !dr_who(&dr->scene[k])) k++;
    return k;
}
static void dr_scene_start(void) {
    const gscene_t *sc = &dr->scene[dr_scene];
    const fighter_t *f = dr_who(sc);
    const char *name = sc->speaker;
    uint8_t l, n, pb = sc->portrait;
    dr_lines = sc->line; dr_nl = sc->nlines;
    if (sc->who) {                               /* a player: its fighter's name, big portrait (none: text only), lines */
        uint8_t c = char_index(f->ch);
        name = f->ch->name; pb = pb_of_fighter[c];
        for (l = 0; l < sc->nby; l++) if (sc->by[l].fighter == c) { dr_lines = sc->by[l].line; dr_nl = sc->by[l].nlines; }
    }
    for (l = 21; l < 26; l++) dr_row(l, DRAMA_FONT + ' ');
    if (pb != dr_pb || sc->side != dr_side) {
        pb_hide(); dr_pb = pb;
        if (dr_pb < PB_COUNT) pb_show(dr_pb, sc->side); else dr_side = sc->side;
    }
    for (n = 0; name[n] && n < 16; n++) ;
    for (l = 0; l < n; l++) dr_put((sc->side ? 37 - n : 3) + l, 21, name[l], 1);   /* the name plate, highlighted (palette 1) */
    for (dr_len = 0, l = 0; l < dr_nl; l++) for (n = 0; dr_lines[l][n]; n++) dr_len++;
    dr_chars = 0; dr_t = 0;
}
static void drama_start(uint8_t d, uint8_t music) {
    uint8_t i;
    dr = &gdramas[d]; dr_music = music; dr_on = DR_IN; dr_t = 0; dr_pb = 0xFE; dr_side = 0xFE; dr_cols = 0;
    if (music != 0xFF) snd_music(music);           /* the boss's music starts with the bars (Bruno), not after the scene */
    dr_music = 0xFF;
    for (i = 0; i < DBG_BOXES * 8; i++) cmd_push(VRAM_SCB3 + DBG_SPR + i, 0);   /* the box viewer gives its sprites */
    dbg_shown = 0;
    for (i = 4; i < 8; i++) dr_row(i, 0x20);       /* the HUD's target and boss bars (rows 4-7, under the top bar) */
}
static void hud_wave(void);
static void drama_tick(void) {
    uint16_t pr = JOY_pressed(0) | JOY_pressed(1);
    uint8_t btn = (pr & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)) != 0;
    const gscene_t *sc;
    dr_t++;
    switch (dr_on) {
    case DR_IN:                                  /* a bar step every 2 ticks */
        if (!(dr_t & 1)) dr_bar((uint8_t)(dr_t >> 1), 1);
        if (dr_t < 16) break;
        if ((dr_scene = dr_next(0)) < dr->n) { dr_on = DR_SCENE; dr_scene_start(); } else { dr_on = DR_OUT; dr_t = 0; }
        break;
    case DR_SCENE:
        sc = &dr->scene[dr_scene];
        if (dr_slide) { dr_slide--; pb_place(dr_slide * 10); }
        if (dr_chars < dr_len) { dr_text(btn ? dr_len : dr_chars + 1); dr_t = 0; break; }   /* typed, a character a tick */
        if (!btn && dr_t < sc->wait) break;
        if ((dr_scene = dr_next(dr_scene + 1)) < dr->n) { dr_scene_start(); break; }
        pb_hide();
        for (dr_t = 21; dr_t < 26; dr_t++) dr_row((uint8_t)dr_t, DRAMA_FONT + ' ');
        dr_on = DR_OUT; dr_t = 0;
        break;
    case DR_OUT:
        if (!(dr_t & 1)) dr_bar(9 - (uint8_t)(dr_t >> 1), 0);
        if (dr_t < 16) break;
        dr_on = DR_OFF;
        dbg_init();                              /* the box viewer's sprites back */
        hud_two = 0xFF; arcade_line_reset(); hud_wave();   /* the HUD redrawn whole */
        if (dr_music != 0xFF) snd_music(dr_music);
        break;
    }
}

/* ---- triggers (gamedata.h gtrigger_t; game.json stages[].triggers): checked every campaign tick (not in the attract
 * demo), each fires once a stage. Spawns wait in a queue for their tick and a free enemy slot; a lock holds the camera
 * until every enemy on screen (and queued) is beaten. ---- */
static uint32_t trig_fired;
static uint16_t stage_tk, wave_t;                /* ticks since the stage start; since the wave (or the boss) came */
static uint8_t wave_on, waves_cleared, trig_held; /* the last wave spawned (nwaves: the boss); waves beaten; a lock on */
#define TQ_N 6
static struct { const gtrigger_t *t; uint8_t k; uint16_t at; } tq[TQ_N];
static uint8_t tq_n;
/* ---- the boss's death (TODO #172, docs/brawler_move_vocabulary.md stage.boss_death; Bruno 2026-10-06: "as soon as he
 * is being hit, that's the end", Final Fight / Streets of Rage): one rule for every stage's boss. The tick its life runs
 * out (its killing hit, a throw's impact, a projectile) the fight is over: every intent is off from then on (players and
 * enemies act no more, the players untouchable), the game logic runs one tick in KO_RATE frames for KO_SLOW frames (slow
 * motion: the music, the voices and the drawing at full rate, snd_tick every frame), the KO sound at once (game.json
 * hit_sounds.boss_ko: KOF94's KO blow, Bruno 2026-10-09) and the boss's death voice (its VK_KO) scream_delay frames later
 * (120: the two never overlap; a fall due before KO_FIRST frames after it waits for then), then every enemy still up is knocked down with no life left, one every KO_GAP frames from KO_FIRST, each with
 * its own death voice as it falls (never a chorus; none again at its S_DEAD: fighter_t.ko_voice); at KO_SLOW full rate
 * again (anyone still up goes down then), PH_END: the bodies blink out, STAGE CLEAR as before. No P2 join, no trigger,
 * no queued spawn from the killing hit on. ---- */
#define KO_SLOW  300                             /* frames of slow motion (5 s) */
#define KO_RATE  3                               /* the logic's one tick in KO_RATE frames */
#define KO_FIRST 45                              /* the first enemy falls this many frames after the scream */
#define KO_GAP   40                              /* then one every KO_GAP frames (5 minions: the last at 205) */
enum { KO_OFF, KO_SLOWMO, KO_DONE };
static uint8_t ko_seq, ko_sub;                   /* KO_*; frames to the next logic tick */
static uint16_t ko_t, ko_next;                   /* frames since the killing hit; the next fall */
/* the stage clear's music (note 20261014-172113-5d29, Bruno: "the music must not depend on anything else than: has the
 * boss really fallen completely on the floor -- then start the music"): one event, the KO'd boss at rest (ko_at_rest:
 * its final landing after every bounce, S_DOWN on the floor, or already dead / gone), then game.json
 * hit_sounds.rest_music frames (the landing sample's length: its sound has finished) + the bytes still queued ahead of
 * it, then the music. Nothing else starts it: no timer from the killing hit, not the slow motion's end, not PH_END;
 * the next screen waits for it (PH_CLEAR). Was: 60 frames after the second floor contact + fallbacks at the slow
 * motion's end and at STAGE CLEAR (note 20261009-231937-b3f3) -> the clear song over the landing sound's tail. */
static uint8_t ko_win;                           /* 1: the clear music started by the KO sequence */
static uint8_t ko_rest;                          /* 1: the boss has come to rest, ko_wt counting */
static uint8_t ko_wt;                            /* frames left to the clear music once at rest */
static uint8_t win_dr;                           /* PH_CLEAR: 1 once the win drama (DR_WIN) played or was passed */
static uint8_t ko_scream;                        /* 1: the boss's death voice still to come (ghitsnd.scream_delay) */
/* ---- the stage clear's win pose (TODO #184, Bruno 2026-10-07: "a little winning pose here at the end of the stage"):
 * when every enemy is gone (after the boss's death sequence), STAGE CLEAR and the input off as before; each player in
 * play (both in a 2-player game) first finishes what he is doing with no input (an attack, a fall, a landing: until
 * he stands, S_IDLE), then turns toward the middle of the screen (the source games' winner faces the opponent he
 * beat, who stood toward the middle) and plays his fighter's 'win' animation once, its voices as the source sends
 * them (export_bm MOVES 'win': each source game's round-win animation, read in our emulator: tools/kof98/capture/
 * wins98.py, tools/brawler/wins184.py), held on its last frame; the next screen comes WIN_HOLD frames after the last
 * pose ended (and never before STAGE CLEAR's 200 frames; at most WIN_MAX). The fighter's state machine is not run
 * while it poses (fighter_win_pose_tick only), the players untouchable. Several win poses (voice note 20261011-
 * 132148-5d29: "for fighters with multiple win poses, play a random one at the end"): fighter.c fighter_win_pose picks
 * one of its source's (BA_WIN + bm_wins), deterministic (the tick counter). ---- */
#define WIN_HOLD   45                            /* frames held on the pose's last frame before the next screen */
#define WIN_SETTLE 180                           /* a player not standing by then does not pose */
#define WIN_MAX    720                           /* the next screen at the latest (Iori's KOF98 win: 305 frames; SS2
                                                    Hanzo's 202: 844, cut here as SS2's round end cuts it at 485) */
enum { WIN_NONE, WIN_WAIT, WIN_POSE, WIN_WALK, WIN_WALKED };   /* WIN_WALK / WIN_WALKED: a fighter's stage-clear walk
                                                    instead of the pose (game.json roster[].clear_walk -> gclear_walk, note
                                                    20261015-224745-e03d, Final Fight's tribute: Haggar walks slowly off to
                                                    the right part of the screen at his own walk, input off; then he stands
                                                    there WIN_HOLD frames as a pose's end is held; CLEAR_WALK_OFF, the
                                                    reopen: out of the screen, fighter_t.inb INB_LEAVE, walk_there) */
static uint8_t win_st[2];                        /* WIN_* per player */
static uint16_t win_t[2];                        /* WIN_WAIT: frames waited; WIN_POSE: frames since the pose ended */
static uint8_t win_step[2];                      /* the pose's step last applied (0xFF: none yet) */
static void win_start(void) {
    uint8_t i;
    for (i = 0; i < 2; i++) {
        const fighter_t *f = &fighters[i];
        win_st[i] = f->state != S_OFF && f->state != S_DEAD && f->hp > 0 ? WIN_WAIT : WIN_NONE; win_t[i] = 0;
    }
}
static int16_t frame_left(const fighter_t *f, uint16_t fr) {   /* screen x of the left edge of frame fr drawn at f (draw.s's
                                                    part placement: x0 = hflip ? ox - dx - w : ox + dx, facing right
                                                    mirrored about ox) */
    const bframe_t *b = &f->ch->frames[fr];
    int16_t ox = INT(f->x) - cam_x, m = 0x7FFF, x0, w;
    uint8_t k;
    for (k = 0; k < b->nparts; k++) {
        const bpart_t *p = &b->parts[k];
        w = p->cols << 4;
        x0 = p->hflip ? ox - p->dx - w : ox + p->dx;
        if (f->facing > 0) x0 = 2 * ox - x0 - w;
        if (x0 < m) m = x0;
    }
    return m;
}
static uint8_t walk_there(const fighter_t *f) {  /* a clear_walk's end: at its screen x, or for "off" (CLEAR_WALK_OFF, note
                                                    20261015-224745-e03d reopen: "walk all the way out of the screen, like
                                                    he's going to the next stage") his whole picture past the screen's
                                                    right edge, the walk's frame shown and every idle frame he stands in
                                                    after it (none peeks back in) */
    uint16_t to = gclear_walk[f->ch->id];
    const banim_t *a = &f->ch->anims[BA_IDLE];
    uint8_t k;
    if (to != CLEAR_WALK_OFF) return INT(f->x) - cam_x >= (int16_t)to;
    if (f->shown_frame != 0xFFFF && frame_left(f, f->shown_frame) < 320) return 0;
    for (k = 0; k < a->nsteps; k++) if (a->steps[k].frame != 0xFFFF && frame_left(f, a->steps[k].frame) < 320) return 0;
    return 1;
}
static uint8_t win_posing(uint8_t i) { return i < 2 && win_st[i] == WIN_POSE; }
static void win_tick(void) {                     /* every fight frame after the fighters' update */
    uint8_t i;
    for (i = 0; i < 2; i++) {
        fighter_t *f = &fighters[i];
        if (win_st[i] == WIN_NONE) continue;
        if (f->inv < 2) f->inv = 2;
        if (win_st[i] == WIN_WAIT) {
            if (f->state == S_IDLE && f->y == 0 && f->ch->id < BC_COUNT && gclear_walk[f->ch->id]) {
                win_st[i] = !walk_there(f) ? WIN_WALK : WIN_WALKED; win_t[i] = 0;
                f->facing = 1;                               /* (already there: he stands, facing it) */
                if (gclear_walk[f->ch->id] == CLEAR_WALK_OFF) f->inb = INB_LEAVE;   /* (off: no edge holds him) */
            } else if (f->state == S_IDLE && f->y == 0) {
                f->facing = INT(f->x) - cam_x < 160 ? 1 : -1;
                f->frame_ovr = 0xFFFF; f->vx = f->vz = 0;
                fighter_win_pose(f); win_st[i] = WIN_POSE; win_t[i] = 0; win_step[i] = 0xFF;
            } else if (++win_t[i] >= WIN_SETTLE || f->state == S_DEAD || f->state == S_OFF) win_st[i] = WIN_NONE;
        } else if (win_st[i] == WIN_WALK) {              /* the walk (win_input: forward held) to the screen x */
            if (walk_there(f) || ++win_t[i] >= WIN_MAX) { win_st[i] = WIN_WALKED; win_t[i] = 0; }
        } else if (win_st[i] == WIN_WALKED) { if (win_t[i] < 0xFFFF) win_t[i]++; }
        else if (f->anim_done && win_t[i] < 0xFFFF) win_t[i]++;
        if (win_st[i] == WIN_POSE) {                 /* the source's own motion: each step's travel as it starts (KOF's
                                                        $FB), its height (Billy Lee's back flip, export_dd air_steps) */
            const bstep_t *s = fighter_step(f);
            if (f->step != win_step[i]) {
                win_step[i] = f->step;
                if (s->dx) {                         /* kept inside the screen, 24 px in (the camera is held at the stage end) */
                    int16_t sx;
                    f->x += f->facing > 0 ? FIX(s->dx) : -FIX(s->dx); sx = INT(f->x) - cam_x;
                    if (sx < 24) f->x = FIX(cam_x + 24); else if (sx > 296) f->x = FIX(cam_x + 296);
                }
            }
            f->y = FIX(s->hy);
        }
    }
}
static uint8_t win_done(void) {                  /* every pose played and held WIN_HOLD frames */
    uint8_t i;
    for (i = 0; i < 2; i++) if (win_st[i] == WIN_WAIT || win_st[i] == WIN_WALK || ((win_st[i] == WIN_POSE || win_st[i] == WIN_WALKED) && win_t[i] < WIN_HOLD)) return 0;
    return 1;
}
static void win_input(void) {                    /* the stage clear's walk (WIN_WALK): forward held, the input off else */
    uint8_t i;
    for (i = 0; i < 2; i++) if (win_st[i] == WIN_WALK) in[i].dx = 1;
}
static void triggers_reset(void) { trig_fired = 0; stage_tk = wave_t = 0; wave_on = 0; waves_cleared = 0; trig_held = 0; tq_n = 0; ko_seq = KO_OFF; ko_scream = 0; ko_win = 0; ko_rest = 0; ko_wt = 0; win_st[0] = win_st[1] = WIN_NONE; }
static void enemies_down(fighter_t *by) {        /* every enemy still up goes down (a boss beaten, TA_END) */
    uint8_t i;
    for (i = 2; i < NF; i++) {
        fighter_t *e = &fighters[i];
        if (e == by || e->state == S_OFF || e->state == S_DEAD || e->hp <= 0) continue;
        if (e->state == S_THROWN || e->state == S_DOWN || e->state == S_GETUP) { e->hp = 0; continue; }
        e->hp = 0; fighter_hit(by, e, 0, R_KNOCKDOWN, 0);
    }
}
static void ko_fall(fighter_t *e) {              /* an enemy goes down with no life, its death voice now */
    e->hp = 0;
    if (e->state != S_THROWN && e->state != S_DOWN && e->state != S_GETUP && e->state != S_KNOCKDOWN)
        fighter_quake(&fighters[in_play(&fighters[0]) ? 0 : 1], e);   /* knocked down away from the player */
    voice_play(e->ch, e->team, VK_KO); e->ko_voice = 1;
}
static void boss_ko_start(void) {                /* the boss's killing hit */
    fighter_t *b = &fighters[BOSS_IDX];
    ko_seq = KO_SLOWMO; ko_t = 0; ko_sub = 0; ko_next = KO_FIRST; tq_n = 0;
    snd_stop_music();                            /* the music first, then this tick's sounds (the killing hit's), then
                                                    the KO blow (note 20261009-120007-5d29: $04 after the blow cut it) */
    snd_cmd(0x1A); snd_cmd(ghitsnd.boss_ko); b->ko_voice = 1; ko_scream = 1; ko_win = 0; ko_rest = 0; ko_wt = 0;   /* (ko_voice: none at its S_DEAD, boss_ko_tick screams) */
    b->kthud = 1;                                /* its fall's floor contacts: hit_sounds.bounce (fighter.c floor_thud) */
}
static uint8_t ko_at_rest(const fighter_t *b) { /* its fall over: lying on the floor (after every bounce), dead, gone */
    return (b->state == S_DOWN || b->state == S_DEAD || b->state == S_OFF) && b->y <= 0;
}
static uint8_t boss_ko_tick(void) {              /* every frame of the sequence; 1: a logic tick this frame */
    uint8_t i;
    for (i = 0; i < 2; i++) if (fighters[i].inv < 2) fighters[i].inv = 2;   /* the players: untouchable to the clear (2: still
                                                             set in combat after their update counted one down) */
    if (!ko_win) {                               /* the clear music: only once the boss is at rest + rest_music */
        if (!ko_rest) { if (ko_at_rest(&fighters[BOSS_IDX])) { ko_rest = 1; ko_wt = ghitsnd.rest_music + snd_pending(); } }
        else if (!ko_wt || !--ko_wt) { snd_music(GAME_MUS_CLEAR); ko_win = 1; }
    }
    if (ko_seq != KO_SLOWMO) return 1;
    if (++ko_t >= ghitsnd.scream_delay && ko_scream) {      /* the death voice, after the KO sound */
        fighter_t *b = &fighters[BOSS_IDX];
        voice_play(b->ch, b->team, VK_KO); ko_scream = 0;
        if (ko_next < ko_t + KO_FIRST) ko_next = ko_t + KO_FIRST;
    }
    if (ko_t >= KO_SLOW) {                     /* full rate again: PH_END (campaign) */
        ko_seq = KO_DONE;
        for (i = 2; i < NF; i++) { fighter_t *e = &fighters[i]; if (e->state != S_OFF && e->state != S_DEAD && e->hp > 0) ko_fall(e); }
        return 1;
    }
    if (ko_t >= ko_next) {                       /* the next enemy still up falls */
        for (i = 2; i < NF; i++) {
            fighter_t *e = &fighters[i];
            if (i == BOSS_IDX || e->state == S_OFF || e->state == S_DEAD || e->hp <= 0) continue;
            ko_fall(e); ko_next = ko_t + KO_GAP; break;
        }
    }
    if (ko_sub) { ko_sub--; return 0; }
    ko_sub = KO_RATE - 1; return 1;
}
static void trig_fire(const gtrigger_t *t) {
    uint8_t i;
    int16_t x;
    switch (t->action) {
    case TA_SPAWN:
        for (i = 0, x = 0; i < t->n && tq_n < TQ_N; i++, x += t->delay) { tq[tq_n].t = t; tq[tq_n].k = i; tq[tq_n].at = stage_tk + x; tq_n++; }
        break;
    case TA_LOCK:                                /* never back left of the camera, never past the lock already there */
        x = lock_at((int16_t)t->arg);
        if (x > lock_x) x = lock_x;
        lock_x = x < cam_x ? cam_x : x; trig_held = 1;
        break;
    case TA_MUSIC: snd_music((uint8_t)t->arg); break;
    case TA_DRAMA: drama_start((uint8_t)t->arg, 0xFF); break;
    case TA_END: tq_n = 0; enemies_down(&fighters[0]); phase = PH_END; phase_t = 0; break;
    }
}
static void triggers(void) {
    const gstagex_t *x = &gstagex[camp];
    uint8_t k, slot;
    stage_tk++; wave_t++;
    for (k = 0; k < x->ntrig && !dr_on; k++) {
        const gtrigger_t *t = &x->trig[k];
        uint32_t bit = 1UL << k;
        if (trig_fired & bit) continue;
        if (t->when == TW_CAMERA ? cam_x < t->at : t->when == TW_WAVE_CLEAR ? waves_cleared <= t->wave :
            t->wave == TW_STAGE ? (int16_t)stage_tk < t->at : wave_on != t->wave || (int16_t)wave_t < t->at) continue;
        trig_fired |= bit;
        trig_fire(t);
    }
    for (k = 0; k < tq_n; ) {                    /* queued spawns: due, and a free slot */
        const gtrigger_t *t = tq[k].t;
        gspawn_t sp;
        if ((int16_t)(stage_tk - tq[k].at) < 0) { k++; continue; }
        for (slot = 2; slot < NF && fighters[slot].state != S_OFF; slot++) ;
        if (slot == NF) break;
        sp = t->sp; sp.pick += tq[k].k;
        for (slot = 0; slot < tq[k].k; slot++) { sp.z += 11; if (sp.z > 61) sp.z -= 55; }   /* z + 11 k, kept on the floor */
        for (slot = 2; slot < NF && fighters[slot].state != S_OFF; slot++) ;
        spawn(slot, &sp, genemies[gs->boss].base);
        ai_set(slot, ai_of(&genemies[sp.enemy]));
        if (boss_ai_of(&genemies[sp.enemy])) ai_boss(slot, boss_ai_of(&genemies[sp.enemy]));   /* (its layer, if any) */
        for (slot = k; slot + 1 < tq_n; slot++) tq[slot] = tq[slot + 1];
        tq_n--;
    }
}
static void spawn_wave(void) {
    const gwave_t *w;
    uint8_t k;
    if (gd_want) { gd_apply(); gs = &gstages[camp]; if (wave >= gs->nwaves) wave = gs->nwaves - 1; }   /* a lab's pack */
    w = &gs->waves[wave];
    for (k = 0; k < NF - 2; k++) {
        if (k >= w->n) { fighters[2 + k].state = S_OFF; continue; }
        spawn(2 + k, &gs->spawns[w->first + k], 0xFF);
    }
    spawns_ai(w->seed, &gs->spawns[w->first], w->n, 2);
    wave_on = wave; wave_t = 0;
    hud_wave();
}
static void boss_start(void) {
    const genemy_t *be;
    uint8_t k, c, set = 0;
    if (gd_want) { gd_apply(); gs = &gstages[camp]; }   /* a lab's pack */
    be = &genemies[gs->boss]; c = be->base;
    phase = PH_BOSS; phase_t = 0; ko_seq = KO_OFF; bp_keyed = 0;
    if (c == pl_ch[0] && !pl_set[0]) set = 1;           /* never in P1's colours */
    enemy_init(BOSS_IDX, c, set, gs->boss_x, gs->boss_z, 0, be);
    for (k = 0; k < NF - 3; k++) {
        if (k >= gs->nmin) { fighters[3 + k].state = S_OFF; continue; }
        spawn(3 + k, &gs->spawns[gs->boss_first + k], c);
    }
    spawns_ai(gs->boss_seed, &gs->spawns[gs->boss_first], gs->nmin, 3);
    ai_set(BOSS_IDX, ai_of(be));
    ai_boss(BOSS_IDX, boss_ai_of(be));                  /* (T9: its own layer, game.json enemies[].boss_ai) */
    wave_on = gs->nwaves; wave_t = 0;
    k = gstagex[camp].drama;                         /* its scene first (the fight held), then its song */
    if (k < DR_COUNT && !attract) drama_start(k, gs->boss_song); else snd_music(gs->boss_song);
    hud_wave();
}
static void go_sign(uint8_t on) {                       /* highlighted (palette 1), in the HUD's black band */
    FIX_print(29, 3, on ? "GO -->" : "      ", 1);
    if (on) snd_ssg(SSG_GO);                             /* each time it shows: the SSG buzz (songs.json ssg GO; voice
                                                            note 20261011-114459-5d29), over the music */
}
/* the stage's music: stage 1 plays the selected fighter's theme when he has one (game.json roster[].music ->
 * roster_music; voice note 20261011-160158-5d29: Robert -> KOF96's Kamikirimushi), else the stage's own song. The
 * selected fighter = P1's (P2's when he plays alone); a P2 joining later changes nothing (the song started here). */
static uint8_t stage_song(uint8_t s) {
    uint8_t m = s == 0 ? roster_music[pl_ch[pl_on[0] ? 0 : 1]] : 0;
    return m ? m : gs->music;
}
/* ---- the stage intro (voice note 20261014-192343-5d29: "at the start of the level nobody on the screen: a fade-in of
 * the background with STAGE 1 START, then the hero walks in, scripted, and as soon as he is on the screen the wave can
 * start"). game.json stage_intro / stages[].intro -> gintro[] (build_tables.py intro_of). From stage_begin, every
 * campaign stage (a new game, stage 2+, after a bonus game, CONTINUE on the title's new game):
 *   IN_FADE  black, the stage's palettes and backdrop fade in over `fade` ticks; nobody on screen (the players and the
 *            enemies S_OFF), no HUD (the fix layer holds only the title and the arcade line, as Final Fight's start);
 *            the title from title_at for title_hold ticks (it may run on into the walk)
 *   IN_WALK  from walk_at: the players (both in 2P) put `from` px outside the `side` edge, their input replaced by the
 *            script's (forward, their own walk or run animation and speed) until each stands on its mark; the HUD back
 *   IN_WAIT  control given; wave_delay ticks later the first wave spawns (spawn_wave) and the campaign runs (flow)
 * The walk outside the world's edge: fighter.c's clamp holds x >= 16 and main.c camera() keeps a player inside the
 * camera, so the walk runs at the mark's x (no clamp there) and the script carries the real x (in_x): the fighter's own
 * motion each tick, added to it. The attract demo and the Lab's starts (no_intro) keep their immediate start. ---- */
enum { IN_OFF, IN_FADE, IN_WALK, IN_WAIT };
static void centre(uint8_t row, const char *t);
static uint8_t in_ph, no_intro, in_at[2];
static uint16_t in_t;
static int32_t in_x[2];
static const gintro_t *gi;
static uint8_t fade_lut[32];                                 /* a 5-bit level at this tick's k / 16 (stage_fade) */
static uint16_t col_scale(uint16_t c) {                      /* a colour at fade_lut's level (the dark bit dropped) */
    uint8_t r = fade_lut[((c >> 7) & 0x1E) | ((c >> 14) & 1)], g = fade_lut[((c >> 3) & 0x1E) | ((c >> 13) & 1)],
            b = fade_lut[((c << 1) & 0x1E) | ((c >> 12) & 1)];
    return ((uint16_t)(r & 1) << 14) | ((uint16_t)(r >> 1) << 8) | ((uint16_t)(g & 1) << 13) | ((uint16_t)(g >> 1) << 4) |
           ((uint16_t)(b & 1) << 12) | (b >> 1);
}
static void stage_fade(uint8_t k, uint8_t part) {            /* the stage's palettes + backdrop at k / 16 (16: as they are);
                                                                part 0-3: only every fourth palette (a quarter a tick: the
                                                                whole stage's 28 palettes a tick cost a frame), 0xFF all */
    uint16_t t[16];
    uint8_t p, c;
    for (c = 0; c < 32; c++) fade_lut[c] = (uint8_t)((c * k) >> 4);
    for (p = 0; p < stg->npal; p++) {
        if (part != 0xFF && (p & 3) != part) continue;
        const uint16_t *src = p == stg->cyc_pal ? stg->cyc + cyc_k * 16 : stg->pal + p * 16;   /* (the cycle's step) */
        if (k >= 16) { PAL_setPalette(STAGE_PAL + p, src); continue; }
        for (c = 0; c < 16; c++) t[c] = col_scale(src[c]);
        PAL_setPalette(STAGE_PAL + p, t);
    }
    bd_set(k >= 16 ? stg->backdrop : col_scale(stg->backdrop));
}
static int16_t in_mark(uint8_t p) { return gi->side ? 320 - gi->mark_x[p] : gi->mark_x[p]; }   /* screen x */
static void intro_title(void) {                              /* the title's line: shown, then cleared */
    uint8_t n = 0;
    char sp[40];
    if (!gi->title[0]) return;
    if (gbig[BIG_STAGE_INTRO].on) {                          /* in the big font (game.json big_text.stage_intro) */
        if (in_t == gi->title_at) bt_show(gi->title, BIG_STAGE_INTRO);   /* (it leaves by itself: the headline
                                                                animation's slide out, big_text.headline; title_hold is
                                                                the fix layer's) */
        return;
    }
    if (in_t == gi->title_at) centre(13, gi->title);
    else if (in_t == gi->title_at + gi->title_hold) { while (gi->title[n] && n < 39) sp[n++] = ' '; sp[n] = 0; centre(13, sp); }
}
static void intro_walk_start(void) {
    uint8_t i;
    for (i = 0; i < 2; i++) {
        fighter_t *f = &fighters[i];
        if (!pl_on[i]) continue;
        fighter_init(f, &bm_chars[pl_ch[i]], pl_set[i], 16 + i * MAX_PALS, 0, cam_x + in_mark(i), gi->mark_z[i]);   /* (its
                                                             depth checked at the mark) */
        f->idx = i; f->facing = gi->side ? -1 : 1;
        if (CHEAT_GAME) fighter_meter_fill(f);               /* (the cheat: both bars full, as stage_begin) */
        in_x[i] = FIX(cam_x + (gi->side ? 320 + gi->from : -(int16_t)gi->from)); f->x = in_x[i]; in_at[i] = 0;
    }
    hud_reset();                                             /* the HUD back, with the players */
    in_ph = IN_WALK;
}
static void intro_fade_tick(void) {                          /* IN_FADE: the game's tick stops here */
    in_t++;
    if (in_t < gi->fade) stage_fade((uint8_t)div16(in_t << 4, gi->fade), in_t & 3);
    else if (in_t == gi->fade) stage_fade(16, 0xFF);
    intro_title();
    if (in_t >= gi->walk_at) intro_walk_start();
}
static void intro_input(void) {                              /* IN_WALK: the script's intents for the players */
    uint8_t p;
    for (p = 0; p < 2; p++) {
        if (!pl_on[p]) continue;
        in[p] = (intent_t){ 0 };
        if (!in_at[p]) { in[p].dx = gi->side ? -1 : 1; in[p].run = gi->run; }
    }
}
static void intro_pre(void) {                                /* IN_WALK, before the update: each walker at its mark */
    uint8_t p;
    for (p = 0; p < 2; p++) if (pl_on[p] && !in_at[p]) fighters[p].x = FIX(cam_x + in_mark(p));
}
static void intro_post(void) {                               /* after it: its motion added to its real x */
    uint8_t p, all = 1;
    in_t++;
    intro_title();
    for (p = 0; p < 2; p++) {
        fighter_t *f = &fighters[p];
        int32_t m = FIX(cam_x + in_mark(p));
        if (!pl_on[p] || in_at[p]) continue;
        in_x[p] += f->x - m;
        if (gi->side ? in_x[p] <= m : in_x[p] >= m) { in_x[p] = m; in_at[p] = 1; }
        else all = 0;
        f->x = in_x[p];
    }
    if (all || in_t > gi->walk_at + 600) { in_ph = IN_WAIT; in_t = 0; }   /* (a walk that never gets there: 10 s at most) */
}
static void intro_wait(void) {                               /* IN_WAIT: control given; then the first wave */
    if (++in_t < gi->wave_delay) return;
    in_ph = IN_OFF;
    spawn_wave(); phase_t = 0;
}
static void stage_begin(uint8_t s, uint8_t first) {
    uint8_t i;
    if (gd_want) gd_apply();                                 /* a lab's pack */
    mode = 1; nf = NE; cam_x = 0; wave = 0; cont_ov = 0; camp = s; phase = PH_WAVE; phase_t = 0; gs = &gstages[s]; bp_keyed = 0;
    triggers_reset(); dr_on = DR_OFF; dr_cols = 0; guard_parity = shadow_parity = 0;      /* a drama cut short (the lab): dbg_init below hides its sprites */
    inputs_reset();
    if (!attract) snd_music(stage_song(s));                  /* the attract demo: no music (voice note 20261011-114853-5d29:
                                                                no music before a credit, as an arcade's attract) */
    bt_hide();                                               /* (a message of the screen before) */
    dbg_init();                                              /* the title's banner reused sprites 300-318 */
    sparks_init();
    sf_reset();
    tfx_reset();
    FIX_clear(); arcade_line_reset();
    stage_init(attract ? STAGE : gs->bg);             /* stage sprites back, every column rewritten */
    bd_set(stg->backdrop);
    lock_x = lock_at(gs->waves[0].lock);
    power = gs->power;
    if (first) { ai_rank_reset(); fighter_game_reset(); }    /* a new game: the hidden rank from rank_start (revamp 1B), fighter.c's statics */
    if (first && CHEAT_GAME) drive_chunks = MAX_CHUNKS;      /* the cheat: the bar at its most chunks (see CHEAT_GAME) */
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    for (i = 0; i < 2; i++) {
        if (!pl_on[i]) { fighters[i].state = S_OFF; if (first) { lives[i] = 0; cont_t[i] = 0; } continue; }   /* out: its
                                                             continue countdown (if any) goes on */
        fighter_init(&fighters[i], &bm_chars[pl_ch[i]], pl_set[i], 16 + i * MAX_PALS, 0, i ? 40 : 60, i ? 10 : 40);
        fighters[i].idx = i;
        if (CHEAT_GAME) fighter_meter_fill(&fighters[i]);    /* the cheat: both bars full at each stage's start */
        if (first) { lives[i] = 3; cont_t[i] = 0; }
    }
    gi = &gintro[s]; in_ph = IN_OFF; in_t = 0;
    if (!attract && !no_intro) {                             /* the stage intro: nobody on screen, the stage black */
        in_ph = IN_FADE;
        for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
        stage_fade(gi->fade ? 0 : 16, 0xFF); intro_title();
        if (!gi->fade && !gi->walk_at) intro_walk_start();
    } else spawn_wave();
    for (i = 0; i < NF; i++) order[i] = &fighters[i];
    for (i = 0; i < NPJ; i++) { projectiles[i].idx = NF + i; order[NF + i] = &projectiles[i]; }
    if (in_ph != IN_WALK) hud_reset();
    if (first) { BIOS_PLAYER_MOD[0] = attract ? 0 : 1; BIOS_PLAYER_MOD[1] = pl_on[1]; }   /* BIOS: who plays (a START then joins) */
}
static void bonus_off(void);
static void fight_start(void) {                  /* from the select screen (pl_* set): a new game at camp_from */
    bonus_off();                                 /* (a bonus cut short by the BIOS: its sprites given back) */
    fury_lock = !attract && gbonus.fury_lock && !(save.cheat & 1);   /* (the cheat: never locked) a new credit: the fury locked until the posts are won (the
                                                        attract demo never: its bot plays as before) */
    bn_won = 0; bonus_on = BN_OFF; bn_clr[0] = bn_clr[1] = bn_clr[2] = 0;
    stage_begin(attract ? 0 : camp_from, 1);
}
static void fight_start_at(uint8_t s) { uint8_t c = camp_from; camp_from = s; fight_start(); camp_from = c; }   /* (lab_bonus) */
/* the attract cycle (TODO #25), KOF98's measured in our emulator (power on, no coin, 24 000 frames, BIOS USER_REQUEST
 * writes + snapshots): its intro, the title logo 1020 frames (17 s), the demo fight 1800 (30 s, ROUND 1 to the KO),
 * the ranking 240, then SYSTEM_RETURN; the BIOS's eye-catcher 466 frames and request 2 again. Here: the logo, then the
 * demo fight, then SYSTEM_RETURN (no intro or ranking to show). */
#define ATTRACT_LOGO 1020
#define ATTRACT_DEMO 1800
static void attract_fight(void) {
    static uint8_t pick;
    banner_hide();
    roster_build();
    if (pick >= lu_n) pick = 0;
    pl_ch[0] = lu[pick]; pl_set[0] = mod8(pick & 3, bm_chars[pl_ch[0]].nsets); pl_on[0] = 1; pl_on[1] = 0;
    pick++;
    attract = 1; attract_t = 0;
    fight_start();
}
static void attract_start(void) {                      /* the logo: the title screen without its menu, INSERT COIN */
    uint8_t i;
    mode = 2; nf = 0; title_t = 0; cam_x = 0; opt_on = 0;
    bd_set(COLOR_BLACK);
    stage_hide();
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    title_screen();
    bios_start = 0;
    /* no music (voice note 20261011-114853-5d29: before a credit, silence, as an arcade's attract; the BIOS reset the
       sound CPU before handing over): the title's song starts with the credit (title_start) */
    attract = 2; attract_t = 0;
}
/* the attract (logo or demo) ends on the title (TODO #209): START with a credit (AES: START; MVS: the BIOS took the
 * credit: NEW GAME / CONTINUE then confirmed with START or A, no second credit; 2026-10-05: on SNK's MVS BIOS the title
 * waited for another coin), or a credit in the BIOS's count (MVS): the title's PRESS START. KOF98, measured in our
 * emulator on SNK's MVS BIOS: a coin on its attract logo or in its demo -> its title, PRESS 1P START. Our MVS BIOS
 * calls DEMO_END on a coin (UniBIOS: request 3 = the title anyway), SNK's does not: the credit count decides. */
static uint8_t attract_leave(void) {
    uint8_t paid = bios_start != 0;
    if (!attract || !(paid || (BIOS_MVS_FLAG && (CREDITS_P1 || CREDITS_P2)))) return 0;
    BIOS_USER_MODE = 1; title_start(); title_paid = paid;
    return 1;
}
static void attract_logo_tick(void) {
    if (bios_demo_end) { SYS_return(); return; }
    if (!title_t) banner_show((320 - BANNER_COLS * 16) / 2, 56);   /* again: power-on's first draw clears every block's
                                                             sprites once (game_init), the banner's 300-379 among them */
    if (!(title_t & 31)) FIX_print(15, 18, (title_t & 32) ? "           " : "INSERT COIN", 0);   /* = the title's
                                                             PRESS START: a credit swaps the words in place */
    if (++title_t >= ATTRACT_LOGO) { FIX_clear(); arcade_line_reset(); banner_hide(); attract_fight(); }
}
static void select_start(void);
/* BIOS PLAYER_START filter (crt0): who may take a credit now. Title: anyone (the game starts); select, unlock and
 * ending screens: nobody; fight: a player not in play (P2 joins, a player continues or rejoins), not once the count ran out
 * or once the stage's boss is beaten, never in the attract demo's fight (a coin ends the demo first). */
uint8_t game_start_accept(uint8_t flags) {
    if (lab.active) return 0;                                /* the Chain Lab's training: nobody joins */
    if (mode == 2 || attract) return opt_on ? 0 : flags;
    if (mode == 0) return sel_phase == SEL_CHOOSE && cursor[1] == 0xFF ? flags & 2 : 0;   /* the select: P2 joins */
    if (mode != 1 || cont_ov == 2 || phase >= PH_END || ko_seq || bonus_on) return 0;   /* (a bonus game: nobody joins) */
    return flags & ((in_play(&fighters[0]) ? 0 : 1) | (in_play(&fighters[1]) ? 0 : 2));
}
/* ---- bonus stages (TODO T7, Bruno 2026-10-14, decision sets bonus-game + bonus-followup; game.json "bonus",
 * gamedata.h gbonus_t, AOF2's scenes: tools/brawler/make_bonus.py -> bonus.h). After a stage with gbonus.after set (and
 * its BOSS UNLOCKED screen), mode 6: AOF2's own BONUS GAME screen, SELECT BONUS GAME and the game's title card (see "AOF2's own
 * screens" below: data in game.json bonus intro / pick / card / games[].slot + voice). Then the game, played in the
 * fight's tick (mode 1, bonus_on): its scene as the stage (stage_use, the camera fixed at its cam), the leading player
 * alone (P1, else P2), no enemies, the HUD up:
 *   BK_GAUGE (the tree, AOF2 Spirit Training): the gauge (fix row 9) sweeps 0-127, step a tick, wrapping; one A (no
 *     press in `seconds`: grade 0) freezes it, grade = how many of grades[] it reached (AOF2's table $17EF8, default
 *     row); the fighter throws the grade's blow (blows[grade], fighter_blow: jab / forward finisher), the tree shakes, the bark mark shows, grade x 3 leaves fall; chunks[grade]
 *     drive chunks are added to the bar (drive_chunks, both players, for the credit, up to MAX_CHUNKS).
 *   BK_BREAK (the posts, AOF2 Initiate Super Death Blow): `count` posts, one at a time at AOF2's place, before `seconds`
 *     run out. BB_ANY (Bruno 2026-10-14, "bonus-pillars-normals"): any strike (fighter_strike_box) is a hit each time one
 *     starts touching the post, `hp` hits break it (a shake + a chip each, the splinters at the last), the fury lock kept
 *     (the prize). BB_FURY: only a fury (D) or its MAX (class 2: its body or its objects) breaks one (burnt, then its
 *     splinters fly), any other hit shakes it and the lesson shows again; his gauge and drive held full, the lock lifted
 *     for the game. All broken: `unlock` (BU_FURY: fury_lock off for the credit; the first time the won_text box held
 *     won_ticks); else it stays as it was.
 * A game already won this credit shows its bonus only (the game has no score). The objects: behind the fighter on the
 * shadows' last sprites (shadows() handles sh_n entities: 47-57 the tree, 55-58 the post), in front on the box viewer's
 * 300-347 (dbg_init and shadow_init give both back after). ---- */
_Static_assert(BONUS_TREE == 0 && BONUS_POSTS == 1, "build_tables.py BONUS_SCENES = make_bonus.py SCENES, in order");
#define BN_FRONT    DBG_SPR                      /* in front of the fighters: the pick pictures, splinters, leaves, mark */
#define BN_TREE_SPR (SPR_BASE - 12)              /* behind: the tree (11 columns, 47-57; the shadows then 43-44) */
#define BN_POST_SPR (SPR_BASE - 4)               /* behind: the post (4 columns, 55-58; the shadows then 43-52) */
#define BN_LEAVES   15
#define BN_PIECES   BONUS_N_PIECE
#define BN_FALL_SPR BN_FRONT                     /* the tree game's falling tree (BONUS_FALL_MAXW columns, in front of
                                                    the fighter as AOF2's 225-243; the posts game's splinters there) */
#define BN_LEAF_SPR (BN_FRONT + (2 * BN_PIECES > BONUS_FALL_MAXW ? 2 * BN_PIECES : BONUS_FALL_MAXW))   /* 319-333 */
#define BN_FEET_Z   10                           /* the fighter's lane: feet at the scene's floor_top + 10 (AOF2's) */
#define BN_TREE_X   124                          /* the fighter's world x in front of the tree / before the posts */
#define BN_TREE_STOP 146                         /* the trunk's face: the blow never carries his feet past it
                                                    (a rush finisher, Kim's flip kick: he stops at the tree, results-1014) */
#define BN_POSTS_X  90
#define BN_POST_BIT 0x80                         /* the post's bit in a striker's hit_mask (fighter_t: one bit per fighter
                                                    index; the bonus games run only the players 0 / 1: index 7 is free) */
#define BN_END_T    300                          /* ticks of the result before the next stage */
#define BN_FALL_LEAP 62                          /* the fall's tick the fighter leaps back (AOF2: Ryo at ~762, mark 700) */
#define BN_FALL_RESULT 150                       /* a passed gauge game's result: the blow (12) + the fall to the crown's
                                                    landing (AOF2: 98 frames) + 40 */
static uint8_t bn_game, bn_cur, bn_lead, bn_lock0;
static void centre(uint8_t row, const char *t);
static uint16_t bn_t, bn_clock, bn_shown_clock;
static const gbonus_game_t *bn_g;
static uint8_t bn_power, bn_grade, bn_gain;     /* the gauge game: power, grade */
static uint16_t bn_hit_t, bn_chg_t;             /* ticks since the blow started (0: none); since the press while he
                                                    concentrates (0: none; games[].charge, note 20261014-133606-5d29) */
static uint8_t bn_pass;                          /* the gauge game: the grade passed (>= win_grade): the tree falls */
static uint16_t bn_fall_t;                       /* ticks since the blow while the tree falls (0: not falling) */
static bar_t bn_bar;
static uint8_t bn_left, bn_post, bn_img, bn_thud, bn_lesson;   /* the break game: posts left, the post's state BP_*, ... */
static uint8_t bn_hp, bn_chip_t;                 /* the break game: the post's hits left, its
                                                    chip's ticks left (a hit that does not break it) */
static uint16_t bn_hold, bn_skip;                /* the result: its ticks, a button ends it from bn_skip */
static uint16_t bn_pt;                           /* ticks in the post's state */
enum { BP_NONE, BP_DROP, BP_STAND, BP_HIT };
static uint8_t bn_split;                         /* ticks left of the last post's splinters */
static struct { int16_t x, y, vx, vy; } bn_pc[BN_LEAVES];   /* splinters (BN_PIECES) / leaves: 1/16 px */
static uint8_t bn_pc_n;
static void bn_put(uint16_t spr, const bonus_obj_t *o, int16_t sx, int16_t sy, uint8_t paloff, uint8_t hs, uint8_t vs, uint8_t tiles) {
    uint8_t c, r, h = o->h;                      /* o's columns at screen sx, sy (hs / vs: SCB2's shrink); tiles: its words */
    if (vs != 0xFF) h = (uint8_t)(((uint16_t)o->h * (vs + 1) + 255) >> 8);   /* (shrunk: the lines it fills) */
    for (c = 0; c < o->w; c++) {
        if (tiles) {
            uint16_t *w = cmd_run(VRAM_SCB1 + (spr + c) * 64, o->h * 2);
            const uint16_t *m = o->map + c * o->h * 2;
            for (r = 0; r < o->h; r++, m += 2) { *w++ = m[0]; *w++ = m[1] ? m[1] + (paloff << 8) : 0; }
            cmd_push(VRAM_SCB2 + spr + c, (uint16_t)hs << 8 | vs);
        }
        cmd_push(VRAM_SCB3 + spr + c, c ? 0x40 : (uint16_t)((((496 - sy) & 0x1FF) << 7) | h));
        if (!c) cmd_push(VRAM_SCB4 + spr, (uint16_t)(sx & 0x1FF) << 7);
    }
}
/* the punch mark (note 20261015-195132-e03d, Terry drawn behind the tree): AOF2 draws it on the sprites right after the
 * tree's, behind the fighter; ours has no free sprites there (shadows 43-44, tree 47-57, Terry from 59), so the mark's
 * tiles are written into the tree's own columns (the cells it covers: make_bonus.py asserts it sits on the tree's 16 px
 * grid). It then shakes with the tree and goes with it; the tree's put at the game's start writes the clean bark back. */
static void bn_decal(const bonus_obj_t *t, const bonus_obj_t *o) {
    uint8_t c, r, row = (uint8_t)((o->y - t->y) >> 4), col = (uint8_t)((o->x - t->x) >> 4);
    for (c = 0; c < o->w; c++) {
        uint16_t *w = cmd_run(VRAM_SCB1 + (BN_TREE_SPR + col + c) * 64 + row * 2, o->h * 2);
        const uint16_t *m = o->map + c * o->h * 2;
        for (r = 0; r < o->h; r++, m += 2) { *w++ = m[0]; *w++ = m[1]; }
    }
}
static void bn_hide(uint16_t spr, uint8_t n) { while (n--) cmd_push(VRAM_SCB3 + spr++, 0); }
static void bn_text(uint8_t row, const char *t, uint8_t pal) { FIX_print(1, row, "                                      ", 0); if (t) { uint8_t n = 0; while (t[n]) n++; FIX_print(20 - (n >> 1), row, t, pal); } }
/* ---- the referee (note 20261015-221208-e03d; game.json "referee", gamedata.h gref_t): Samurai Shodown II's Kuroko
 * coming to the front to speak, as SS2 plays it after certain one-player matches (KURO-SYS state 12 $E5D0, MES-WIND
 * $E7CE; tools/samsho2/referee_ss2.py decodes it and exports referee.h: his frames, the window, SS2's numbers; study
 * /data/neogeo_dict/samsho2/README.md "The referee's speech"). Screen coordinates, his feet: on the back lane
 * (REF_BACK_DY above the player's floor rf.g) he sidesteps in from gref.from px outside the screen edge farther from the
 * player (REF_WALK_VX: 1 px a tick, SS2's sidestep for the way he goes), reaches gref.mark px from it, stands one tick,
 * jumps (Kuroko's own jump: REF_JUMP_VY, REF_GRAV; behind the player rising, in front falling), lands REF_LAND_DY
 * under the floor (his landing, his shadow), stands (his idle); the next tick SS2's window opens (SCB2 vertical shrink
 * 0xFF - zoom, centred, REF_WIN_OPEN a tick), his lines are typed on the fix layer a letter every REF_LETTER ticks,
 * held gref.hold ticks after the last (a button ends it sooner), the text goes and the window closes (REF_WIN_CLOSE a
 * tick). He is drawn as SS2 draws him (face 0); the window as SS2 shows it on his left (flipped) when he comes from the
 * right, mirrored when he comes from the left. Its rows: SS2's top, a middle row per line (SS2's two at least: its 16 px
 * font, our 8 px lines centred in theirs), its bottom. Sprites: behind 53-58 (a bonus game's shadows take 43-52, the
 * post's 55-58 are free at its end), in front the box viewer's 300..323: his shadow (300-303), him (304-310), the window (311-323, REF_WIN_W). Palettes REF_PAL..
 * (fighter slots 6-7: a bonus game loads only its player's).
 * The D quirk (gref.hit, note 20261016-045652-e03d reopen, Bruno: "the fury is triggered, but somehow it doesn't
 * connect: all the hits are not done... have the real fury play start to finish"): as the fury fires, the drawn referee
 * becomes his BODY, the roster fighter gref.fighter (game.json referee.fighter: SS2's Kuroko, the samsho2:kuroko export)
 * in fighter slot RF_IDX where he stands (his landed feet, facing the player), a team-1 victim that never acts (no AI,
 * no attack: bonus_input clears his intent) with gref.life (never KO'd); the whole fury lands on him as on any enemy,
 * with his own reactions and get-up; up again, his window opens over the body with hit_text. ---- */
#define REF_PAL     64
#define RF_IDX      2                            /* the body's fighter slot (palettes 32-39, a fighter block, shadow) */
#define REF_WIN_ROWS 16                          /* the window's columns: its rows, then blank ones to the 16th (a shrunk
                                                    sprite of 16 rows or fewer shows rows past its size: rows a sprite there
                                                    before left showed under the opening window, note 20261016-045652-e03d) */
#define REF_TXT_MID  (98 + 8 * (REF_WIN_W - 12))  /* the window's inside, its centre px from its left (SS2's graphic: the
                                                    inner border at 18 / 178, + 16 a column referee_ss2.py adds): the lines
                                                    centred there, 18 letters at most in SS2's 12 columns, 20 in our 13
                                                    (build_tables.py REF_LINE: 6 px each side, note 20261016-045652-e03d) */
#define RF_BACK_SPR (SH_SPR + 10)
#define RF_SH_SPR   BN_FRONT
#define RF_SPR      (RF_SH_SPR + 4)
#define RF_WIN_SPR  (RF_SPR + 7)                 /* (him: REF_MAXW_FRONT columns, 6; the window 311-323) */
_Static_assert(REF_PAL >= 16 + 2 * MAX_PALS && REF_PAL + REF_NPAL <= 16 + NF * MAX_PALS, "the referee's palettes: fighter slots past the players'");
_Static_assert(RF_BACK_SPR + REF_MAXW_BACK <= SPR_BASE && RF_BACK_SPR + REF_MAXW_FRONT <= SPR_BASE && REF_MAXW_FRONT <= 7 &&
               RF_WIN_SPR + REF_WIN_W <= BT_SPR, "the referee's sprites: 53-58 behind, 300-323 in front");
enum { RF_OFF, RF_WALK, RF_STAND, RF_RISE, RF_JUMP, RF_LAND, RF_OPEN, RF_TYPE, RF_HOLD, RF_CLOSE, RF_WAIT };
enum { RQ_NONE, RQ_RUN, RQ_FURY, RQ_HIT };       /* rf.quirk: the D quirk (gref.hit): none, the fighter running at him,
                                                    his fury fired (the body in play), the referee hit (his second
                                                    speech: D ends it) */
static struct {
    uint8_t ph, anim, step, tick, front, wface, nl, line, col, zoom, w;   /* w: the columns he took last tick */
    uint8_t quirk, body;                         /* body: fighters[RF_IDX] is him (the D quirk's fury) */
    int16_t x, tx, g, wx, wy;                    /* his x, its target, the player's floor; the window's left / top */
    int32_t xs, y, vy, vx;                       /* 8.8: his x, his feet's y, the jump's speed, the walk's */
    uint16_t t, key;                             /* ticks in the phase; the step drawn last (its tiles written) */
    const char *const *text;
} rf;
static void rf_set(uint8_t a) { if (a != rf.anim) { rf.anim = a; rf.step = 0; rf.tick = 0; } }
static uint8_t rf_anim_tick(void) {              /* a tick of his animation: a step shows ticks + 1 ticks (SS2's object
                                                    clock, measured); 1 when a non-looping one has shown its last */
    const ref_anim_t *a = &ref_anims[rf.anim];
    if (++rf.tick <= a->s[rf.step].ticks) return 0;
    if (rf.step + 1 < a->n) { rf.step++; rf.tick = 0; return 0; }
    if (a->loop) { rf.step = 0; rf.tick = 0; return 0; }
    rf.tick = a->s[rf.step].ticks; return 1;
}
static void rf_draw(void) {                      /* him (behind or in front) as his step shows (his body: drawn as a fighter) */
    const ref_step_t *s = &ref_anims[rf.anim].s[rf.step];
    if (rf.body) return;
    uint16_t base = rf.front ? RF_SPR : RF_BACK_SPR, key = (uint16_t)(rf.anim << 8 | rf.step | rf.front << 7), c = 0;
    uint8_t i, tiles = key != rf.key;
    if (tiles && rf.key != 0xFFFF && (rf.key >> 7 & 1) != rf.front) { bn_hide(rf.front ? RF_BACK_SPR : RF_SPR, rf.w); rf.w = 0; }
    for (i = 0; i < s->n; i++) {
        const ref_part_t *p = &s->p[0][i];
        bn_put(base + c, p, rf.x + p->x, (int16_t)(rf.y >> 8) + p->y, 0, 0xF, 0xFF, tiles);
        c += p->w;
    }
    if (c < rf.w) bn_hide(base + c, rf.w - c);
    rf.w = (uint8_t)c; rf.key = key;
}
static void rf_window(uint8_t tiles) {           /* SS2's window at rf.zoom (+$7B): vertical shrink 0xFF - zoom, centred */
    const ref_part_t *o = &ref_window_s[0].p[rf.wface][0];
    uint8_t c, r, n = (uint8_t)(rf.nl > 2 ? rf.nl + 2 : 4), vs = (uint8_t)(0xFF - rf.zoom);
    int16_t lines = (int16_t)(((uint16_t)n * 16 * (vs + 1)) >> 8), y = rf.wy + ((n * 16 - lines) >> 1);
    for (c = 0; c < o->w; c++) {
        if (tiles) {                             /* its column: SS2's top row, middle rows (its first, then its second:
                                                    the frame's two halves), its bottom row */
            uint16_t *w = cmd_run(VRAM_SCB1 + (RF_WIN_SPR + c) * 64, REF_WIN_ROWS * 2);
            const uint16_t *m = o->map + c * o->h * 2;
            for (r = 0; r < n; r++) {
                uint8_t k = r == 0 ? 0 : r == n - 1 ? 3 : r <= (n - 2 + 1) / 2 ? 1 : 2;
                *w++ = m[k * 2]; *w++ = m[k * 2 + 1];
            }
            for (; r < REF_WIN_ROWS; r++) { *w++ = 0; *w++ = 0; }   /* (the rows past its last blank: the shrink
                                                    reads them, note 20261016-045652-e03d) */
        }
        cmd_push(VRAM_SCB2 + RF_WIN_SPR + c, 0x0F00 | vs);
        cmd_push(VRAM_SCB3 + RF_WIN_SPR + c, c ? 0x40 : (uint16_t)((((496 - y) & 0x1FF) << 7) | n));
        if (!c) cmd_push(VRAM_SCB4 + RF_WIN_SPR, (uint16_t)(rf.wx & 0x1FF) << 7);
    }
}
#define RF_BLANK "                      "      /* the window's inside: a space a fix column */
_Static_assert(sizeof RF_BLANK == 2 * (REF_WIN_W - 2) + 1, "the referee's blank line: the window's inside");
static void rf_text(uint8_t clear) {             /* the lines typed so far (rf.line, rf.col), or the window's rows cleared */
    uint8_t k, n;
    for (k = 0; k < rf.nl; k++) {
        uint8_t row = (uint8_t)((rf.wy + 16 * (k + 1) + 4) >> 3);   /* (fix row r = sprite y 8 r: measured) */
        if (clear) { FIX_print((uint8_t)((rf.wx + 16) >> 3), row, RF_BLANK, 0); continue; }
        if (k != rf.line) continue;
        n = 0; while (rf.text[k][n]) n++;
        { char ch[2] = { rf.text[k][rf.col], 0 };   /* centred on the box's inside (REF_TXT_MID) */
          FIX_print((uint8_t)(((rf.wx + REF_TXT_MID - 4 * n) >> 3) + rf.col), row, ch, 0); }
    }
}
static void rf_win_place(const char *const *text, int16_t x) {   /* his lines and their window, him standing at x */
    int16_t wox = rf.wface ? x + REF_WIN_X : x - REF_WIN_X, wy;   /* the window object (SS2's x / y from him) */
    const ref_part_t *o = &ref_window_s[0].p[rf.wface][0];
    rf.text = text; rf.nl = 0; while (rf.nl < 3 && text[rf.nl][0]) rf.nl++;
    rf.wx = wox + o->x;
    rf.wx = ((rf.wx + 4 + REF_TXT_MID) & ~7) - REF_TXT_MID;     /* (its inside's centre on the fix grid, the nearest) */
    while (rf.wx < 0) rf.wx += 8;                                /* (knocked back: on screen) */
    while (rf.wx > 320 - 16 * o->w) rf.wx -= 8;
    wy = rf.g + REF_LAND_DY + REF_WIN_Y + o->y - 16 * (rf.nl > 2 ? rf.nl - 2 : 0);   /* (taller: it grows upwards) */
    rf.wy = (int16_t)(((wy + 4) & ~7) - 4);      /* (a line's 8 px centred in a 16 px row on a fix row: top = 4 mod 8) */
}
static void rf_start(const char *const *text, int16_t px) {   /* px: the player's screen x */
    uint8_t i;
    for (i = 0; i < REF_NPAL; i++) PAL_setPalette(REF_PAL + i, ref_pals + i * 16);
    rf.wface = px < 160;                         /* (the player on the left: he comes from the right, SS2's own case) */
    rf.g = floor_top + BN_FEET_Z;
    rf.x = rf.wface ? 320 + gref.from : -(int16_t)gref.from;
    rf.tx = rf.wface ? 320 - gref.mark : gref.mark;
    rf.xs = (int32_t)rf.x << 8; rf.vx = rf.tx > rf.x ? REF_WALK_VX : -REF_WALK_VX;
    rf.y = (int32_t)(rf.g + REF_BACK_DY) << 8; rf.front = 0; rf.w = 0; rf.key = 0xFFFF; rf.anim = 0xFF;
    rf_set(rf.vx > 0 ? REF_WALK_R : REF_WALK_L);
    rf_win_place(text, rf.tx);
    rf.ph = RF_WALK; rf.t = 0; rf.quirk = RQ_NONE; rf.body = 0;
    FIX_print(17, 9, "                    ", 0);   /* (the game's TIME / POSTS line: under the window) */
}
static void rf_body_on(void) {                   /* the fury fires: the drawn referee becomes his body (fighters[RF_IDX]) */
    fighter_t *e = &fighters[RF_IDX];
    bn_hide(rf.front ? RF_SPR : RF_BACK_SPR, rf.w); rf.w = 0; rf.key = 0xFFFF;
    bn_hide(RF_SH_SPR, ref_shadow_s[0].p[0][0].w);   /* (his shadow: the body's own ground shadow) */
    fighter_init(e, &bm_chars[gref.fighter], 0, 16 + RF_IDX * MAX_PALS, 1, rf.x + cam_x, BN_FEET_Z + REF_LAND_DY);
    e->idx = RF_IDX; e->hp = e->hp_max = (int16_t)gref.life;
    e->facing = INT(fighters[bn_lead].x) < INT(e->x) ? -1 : 1;
    order[nf++] = e; rf.body = 1; hud_hide = e;
}
static void rf_body_off(void) {                  /* (its block cleared by draw: S_OFF in order[] until the next stage) */
    if (rf.body) fighters[RF_IDX].state = S_OFF;
    rf.body = 0; hud_hide = 0;
}
static uint8_t rf_tick(void) {                   /* a tick of the speech (bonus_flow); 0 when it is over */
    rf.t++;
    switch (rf.ph) {
    case RF_WALK:                                /* $E5D0: moved, then compared */
        if (rf.t <= gref.delay) { rf_draw(); return 1; }   /* (off screen, still: game.json referee.delay ticks first,
                                                    note 20261016-180759-e03d) */
        rf_anim_tick(); rf.xs += rf.vx; rf.x = (int16_t)(rf.xs >> 8);
        if (rf.x == rf.tx) rf.ph = RF_STAND;
        rf_draw(); return 1;
    case RF_STAND:                               /* $E64E: one tick */
        rf_set(REF_STAND); rf_draw(); rf.ph = RF_RISE; return 1;
    case RF_RISE:                                /* $E668: Kuroko's jump, the speed set and the move */
        rf_set(REF_RISE); rf.vy = REF_JUMP_VY; rf.y += rf.vy; rf_draw(); rf.ph = RF_JUMP;
        if (gref.jump_sound) snd_sfx(gref.jump_sound);   /* SS2's jump sound ($E668 sends $2B: driver $DA) */
        return 1;
    case RF_JUMP:                                /* $E69E: the speed, the landing test, then the move */
        rf_anim_tick(); rf.vy += REF_GRAV;
        if (rf.vy >= 0) { rf.front = 1; rf_set(REF_FALL); }
        if (rf.front && (rf.y >> 8) >= rf.g + REF_LAND_DY) {
            rf.y = (int32_t)(rf.g + REF_LAND_DY) << 8; rf_set(REF_LAND); rf.ph = RF_LAND;
            if (gref.land_sound) snd_sfx(gref.land_sound);   /* his landing voice ($278B8[char]: driver $1A $73) */
            bn_put(RF_SH_SPR, &ref_shadow_s[0].p[0][0], rf.x + ref_shadow_s[0].p[0][0].x, rf.g + REF_LAND_DY + ref_shadow_s[0].p[0][0].y, 0, 0xF, 0xFF, 1);
        } else rf.y += rf.vy;
        rf_draw(); return 1;
    case RF_LAND:                                /* $E724: the landing played, his idle; the window from the next tick */
        if (rf_anim_tick()) { rf_set(REF_IDLE); rf.ph = RF_OPEN; rf.zoom = REF_WIN_ZOOM; rf.t = 0; }
        rf_draw(); return 1;
    case RF_OPEN:                                /* MES-WIND $E822 */
        rf_anim_tick(); rf_draw();
        rf.zoom -= REF_WIN_OPEN; rf_window(rf.t == 1);
        if (!rf.zoom) { rf.ph = RF_TYPE; rf.t = 0; rf.line = 0; rf.col = 0; }
        return 1;
    case RF_TYPE:                                /* MESSDISP: a letter every REF_LETTER ticks (measured) */
        rf_anim_tick(); rf_draw();
        if (rf.t % REF_LETTER) return 1;
        rf_text(0);
        if (!rf.text[rf.line][++rf.col]) { rf.col = 0; if (++rf.line >= rf.nl) { rf.ph = RF_HOLD; rf.t = 0; } }
        return 1;
    case RF_HOLD:
        rf_anim_tick(); rf_draw();
        if (gref.hit && rf.quirk == RQ_NONE && (JOY_pressed(bn_lead) & JOY_D)) {   /* the quirk: D, his fury into
                                                    the referee (bonus_input runs him there and fires it) */
            rf_text(1); rf.ph = RF_CLOSE; rf.quirk = RQ_RUN; rf.t = 0;
            return 1;
        }
        if (rf.t >= gref.hold || (rf.t > 20 && (JOY_pressed(bn_lead) & (JOY_A | JOY_B | JOY_C | JOY_START |
                                                                      (gref.hit && rf.quirk == RQ_NONE ? 0 : JOY_D))))) {
            rf_text(1); rf.ph = RF_CLOSE;
        }
        return 1;
    case RF_CLOSE:                               /* MES-WIND $E8A6 */
        rf_anim_tick(); rf_draw();
        rf.zoom += REF_WIN_CLOSE;
        if (rf.zoom >= REF_WIN_ZOOM) {
            bn_hide(RF_WIN_SPR, REF_WIN_W);
            if (rf.quirk == RQ_RUN || rf.quirk == RQ_FURY) { rf.ph = RF_WAIT; rf.t = 0; return 1; }   /* (the fury coming) */
            rf.ph = RF_OFF; return 0;
        }
        rf_window(0); return 1;
    case RF_WAIT: {                              /* the fighter runs at him and fires: the fury plays on his body
                                                    to its end, he lies and gets up as any enemy (his own reactions);
                                                    up again: his window over the body with hit_text. A fury that never
                                                    touched him (or never fired): the speech ends as without D */
        const fighter_t *f = &fighters[bn_lead], *e = &fighters[RF_IDX];
        uint8_t i, busy = sf_who || (f->state != S_IDLE && f->state != S_WALK) || (rf.body && e->state != S_IDLE);
        for (i = 0; i < NPJ; i++) busy |= projectiles[i].state != S_OFF;
        rf_anim_tick(); rf_draw();
        if (rf.quirk == RQ_FURY && !busy && rf.t > 1) {
            if (e->hp >= (int16_t)gref.life) { rf.ph = RF_OFF; return 0; }
            rf.quirk = RQ_HIT; rf_win_place(gref.hit_text, INT(e->x) - cam_x);
            rf.ph = RF_OPEN; rf.zoom = REF_WIN_ZOOM; rf.t = 0;
            return 1;
        }
        if (rf.t > (rf.quirk == RQ_FURY ? 1800 : 600)) { rf.ph = RF_OFF; return 0; }
        return 1;
    }
    }
    return 0;
}
/* AOF2's own screens before a game (notes 20261014-085447-5d29 / -085507-5d29, Bruno 2026-10-14 "AOF2's ORIGINAL bonus
 * select screen"; bonus.h bscr_*: make_bonus.py "screens", AOF2's order and timing: tools/aof/bonus_rip.py), mode 6,
 * on sprites 1..BSCR_SPRS - 1 (cleared when one ends; bonus_play gives the stage, shadows and fighters theirs back):
 *   BN_INTRO "BONUS GAME" (black): AOF2's two chains zooming in (bscr_zoom, a step a tick), at gbonus.intro_at its song +
 *     the announcer (intro_music / intro_voice), the select after intro_ticks;
 *   BN_PICK SELECT BONUS GAME: AOF2's three pictures in its slots 0-2, a slot without a game (game.json games[].slot)
 *     greyed and skipped by the stick; the cursor's frame on every other tick, the general message until the stick
 *     moves or 180 ticks pass, then the cursor's game's; TIME counts pick_seconds down a step per 60 ticks, 60 more at 0,
 *     then the cursor's game; A (any button, START) picks: the frame steady 60 ticks;
 *   BN_CARD the game's title card (its slot's: the kanji + the English name), the music off, the game's voice + the
 *     card's sound (card_sound), card_ticks, then the game. */
static uint8_t bn_slot, bn_moved, bn_conf, bn_msg, bn_slot_game[3];
static void bscr_put(const bscr_obj_t *b, int16_t x, int16_t y, uint8_t hs, uint8_t vs) { bn_put(b->spr, &b->o, x, y, 0, hs, vs, 1); }
static void bscr_clear(void) { uint16_t i, *y = cmd_run(VRAM_SCB3 + 1, BSCR_SPRS - 1); for (i = 0; i < BSCR_SPRS - 1; i++) y[i] = 0; blk_key_reset(); bg_ok = 0; }
static void bscr_pals(const uint16_t *p, uint8_t n) { uint8_t i; for (i = 0; i < n; i++) PAL_setPalette(BSCR_PAL + i, p + i * 16); }
static void bn_msg_show(uint8_t k) {             /* the message box's text: 0 the general one, 1-3 slot 0-2's */
    const bscr_obj_t *m = &bscr_msg[k];
    bn_msg = k; bscr_put(m, m->o.x, m->o.y, 0xF, 0xFF);
    if (m->o.w < BSCR_MSG_W) bn_hide(m->spr + m->o.w, BSCR_MSG_W - m->o.w);
}
static void bn_frame_show(uint8_t on) {
    if (on) bscr_put(&bscr_frame, bscr_frame_x[bn_slot], bscr_frame.o.y, 0xF, 0xFF); else bn_hide(bscr_frame.spr, bscr_frame.o.w);
}
static void bonus_start(void) {                  /* after stage camp: AOF2's BONUS GAME screen */
    uint8_t i;
    mode = 6; bonus_on = BN_INTRO; bn_t = 0; bn_cur = 0; nf = 0; cam_x = 0; bn_shown_clock = 0xFFFF;
    snd_stop_music();                            /* (AOF2: silence until its BONUS GAME jingle) */
    bn_lead = pl_on[0] ? 0 : 1;
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    FIX_clear(); arcade_line_reset();
    stage_hide(); dbg_init(); bscr_clear();
    bd_set(COLOR_BLACK);
    bscr_pals(bscr_intro_pal, BSCR_INTRO_NPAL);
    for (i = 0; i < 3; i++) bn_slot_game[i] = 0xFF;
    for (i = 0; i < gbonus.ngames; i++)          /* a game whose reward is the fury, the fury already free (won this
                                                    credit, the cheat): its slot greyed and skipped like an empty one
                                                    (note 20261016-132535-e03d) */
        if (!(gbonus.games[i].unlock == BU_FURY && !fury_lock)) bn_slot_game[gbonus.games[i].slot] = i;
}
static void bonus_play(uint8_t k);
static void bn_select_start(void) {
    uint8_t i, k;
    bonus_on = BN_PICK; bn_t = 0; bn_moved = 0; bn_conf = 0; bn_shown_clock = 0xFFFF;
    bscr_clear(); bscr_pals(bscr_sel_pal, BSCR_SEL_NPAL); bd_set(COLOR_BLACK);
    for (i = 0; i < BSCR_SEL_N; i++) bscr_put(&bscr_sel[i], bscr_sel[i].o.x, bscr_sel[i].o.y, 0xF, 0xFF);
    for (k = 0; k < 3; k++) {                    /* the pictures: a slot without a game greyed */
        const bscr_obj_t *p = bn_slot_game[k] != 0xFF ? bscr_pics[k].on : bscr_pics[k].off;
        for (i = 0; i < bscr_pics[k].n; i++) bscr_put(&p[i], p[i].o.x, p[i].o.y, 0xF, 0xFF);
    }
    for (bn_slot = 0; bn_slot < 2 && bn_slot_game[bn_slot] == 0xFF; bn_slot++) ;   /* AOF2's cursor: the first slot */
    bn_cur = bn_slot_game[bn_slot];
    bn_msg_show(0);
    snd_music(gbonus.pick_music);
}
static void bn_card_start(void) {
    const bscr_card_t *c = &bscr_cards[bn_slot];
    uint8_t i;
    bonus_on = BN_CARD; bn_t = 0;
    bscr_clear(); bscr_pals(c->pal, c->npal); bd_set(c->backdrop);
    for (i = 0; i < c->n; i++) bscr_put(&c->objs[i], c->objs[i].o.x, c->objs[i].o.y, 0xF, 0xFF);
    snd_stop_music();                            /* (AOF2's $20: silence) */
    if (gbonus.games[bn_cur].voice) snd_sfx(gbonus.games[bn_cur].voice);
    if (gbonus.card_sound) snd_sfx(gbonus.card_sound);
}
static void bonus_screen_tick(void) {
    uint16_t pr = JOY_pressed(bn_lead), t = bn_t++;
    if (bonus_on == BN_INTRO) {
        if (t < BSCR_ZOOM_N) {
            uint8_t j;
            for (j = 0; j < BSCR_INTRO_N; j++) {
                const int16_t *z = bscr_zoom[t][j];
                if (z[3] < 0) bn_hide(bscr_intro[j].spr, bscr_intro[j].o.w);
                else bscr_put(&bscr_intro[j], z[0], z[1], (uint8_t)z[2], (uint8_t)z[3]);
            }
        }
        if (t == gbonus.intro_at) { if (gbonus.intro_voice) snd_sfx(gbonus.intro_voice); snd_music(gbonus.intro_music); }
        if (t + 1 >= gbonus.intro_ticks) bn_select_start();
        return;
    }
    if (bonus_on == BN_CARD) {
        if (t + 2 == gbonus.card_ticks) { bscr_clear(); bd_set(COLOR_BLACK); }   /* the card goes first (its last tick black), */
        if (t + 1 >= gbonus.card_ticks) bonus_play(bn_cur);   /* then the game: its texts never over the card (bonus_play's
                                                             stage load spans frames: the card stayed with them, 0.10.87) */
        return;
    }
    {                                            /* BN_PICK */
        uint16_t secs = div16(t, 60);
        uint8_t left = secs < gbonus.pick_seconds ? (uint8_t)(gbonus.pick_seconds - secs) : 0, s;
        if (left != bn_shown_clock) { bn_shown_clock = left; bscr_put(&bscr_digit[left], bscr_digit[left].o.x, bscr_digit[left].o.y, 0xF, 0xFF); }
        if (bn_conf) { if (++bn_conf > 60) bn_card_start(); return; }
        bn_frame_show(!(t & 1));                 /* (AOF2: the frame on every other frame while picking) */
        s = bn_slot;
        if (t && (pr & JOY_RIGHT)) { do s++; while (s < 3 && bn_slot_game[s] == 0xFF); if (s >= 3) s = bn_slot; }
        if (t && (pr & JOY_LEFT)) { uint8_t q = bn_slot; while (q && bn_slot_game[--q] == 0xFF) ; if (bn_slot_game[q] != 0xFF) s = q; }
        if (s != bn_slot) { bn_slot = s; bn_cur = bn_slot_game[s]; bn_moved = 1; snd_ssg(SSG_CURSOR); bn_msg_show(1 + s); bn_frame_show(!(t & 1)); }
        if (!bn_moved && t == 180) bn_msg_show(1 + bn_slot);
        if (t >= (uint16_t)(gbonus.pick_seconds + 1) * 60 || (t > 20 && (pr & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)))) {
            bn_conf = 1; snd_ssg(SSG_CONFIRM); bn_frame_show(1);
            if (bn_msg != 1 + bn_slot) bn_msg_show(1 + bn_slot);
        }
    }
}
static void bn_lesson_show(uint8_t on) {         /* the break game's lesson box: what breaks the posts, how (AOF2's
                                                    "FOR SUPER HAOHSHOKO-KEN" box) */
    bn_lesson = on;                              /* (game.json games[].lesson: 3 lines) */
    bn_text(20, on ? bn_g->lesson[0] : 0, 1);
    bn_text(22, on ? bn_g->lesson[1] : 0, 0);
    bn_text(24, on ? bn_g->lesson[2] : 0, 0);
}
static void bonus_play(uint8_t k) {
    uint8_t i;
    fighter_t *f = &fighters[bn_lead];
    bscr_clear(); shadow_init();                 /* (AOF2's screens: their sprites go, the shadows' tiles back) */
    bn_game = k; bn_g = &gbonus.games[k]; bonus_on = BN_PLAY; bn_t = 0; bn_clock = bn_g->seconds * 60; bn_shown_clock = 0xFFFF;
    mode = 1; phase = PH_WAVE; phase_t = 0; cont_ov = 0; wave = 0;
    triggers_reset(); dr_on = DR_OFF; dr_cols = 0; guard_parity = shadow_parity = 0;
    inputs_reset(); sparks_init(); sf_reset(); tfx_reset(); dbg_on = 0; dbg_init();
    FIX_clear(); arcade_line_reset();
    stage_use(&bonus_scenes[bn_g->scene].st, 0); cam_x = lock_x = bonus_scenes[bn_g->scene].cam;
    bd_set(stg->backdrop);
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    fighter_init(f, &bm_chars[pl_ch[bn_lead]], pl_set[bn_lead], 16 + bn_lead * MAX_PALS, 0,
                 bn_g->kind == BK_GAUGE ? BN_TREE_X : BN_POSTS_X, BN_FEET_Z);
    f->idx = bn_lead; f->facing = 1;
    order[0] = f; for (i = 0; i < NPJ; i++) { projectiles[i].idx = NF + i; order[1 + i] = &projectiles[i]; }
    hud_reset();
    snd_music(bn_g->music);
    if (bn_g->show_name) centre(13, bn_g->name);   /* (games[].show_name: note 20261015-221208-e03d, none: just go) */
    if (bn_g->kind == BK_GAUGE) {
        nf = 1; sh_n = 2;                        /* the fighter alone: the tree behind him on 47-57 */
        bn_power = 0; bn_grade = 0; bn_hit_t = 0; bn_chg_t = 0; bn_gain = 0; bn_pass = 0; bn_fall_t = 0;
        bn_put(BN_TREE_SPR, &bonus_tree[0], bonus_tree[0].x, bonus_tree[0].y, 0, 0xF, 0xFF, 1);   /* (objects: AOF2's screen = ours) */
        bn_bar = (bar_t){ .col = 12, .row = 9, .n = 16, .pal = METER_PAL, .px = -1, .trail = -1 };
        bn_text(20, "PRESS A WHEN THE GAUGE IS FULL!", 1);
    } else {
        nf = 1 + NPJ; sh_n = 10;                 /* the fighter and his objects: the post behind on 55-58 */
        bn_left = bn_g->count; bn_post = BP_NONE; bn_pt = 0; bn_thud = 0; bn_pc_n = 0; bn_split = 0; bn_chip_t = 0;
        bn_lock0 = fury_lock;
        if (bn_g->breaks == BB_FURY) fury_lock = 0;   /* the fury works here (the lesson); BB_ANY: the regular attacks
                                                    break the posts, the fury stays as it is (locked: the prize) */
        if (bn_g->lesson[0][0]) bn_lesson_show(1);   /* (games[].lesson [] : no box at the start) */
    }
}
static void bonus_off(void) {                    /* out of a bonus: its sprites hidden, the shadows' back */
    if (sh_n != NE) { bn_hide(BN_TREE_SPR, 12); bn_hide(BN_POST_SPR, 4); sh_n = NE; shadow_init(); }
    if (bonus_on) bn_hide(BN_FRONT, 48);
    bt_hide();                                   /* (TIME OVER, the won headline: on 324-347) */
    if (rf.ph) { rf_text(1); rf.ph = RF_OFF; }   /* (the referee cut short: his sprites went with 47-58 / 300-347) */
    rf.quirk = RQ_NONE; rf_body_off();
    if (bonus_on == BN_PICK || bonus_on >= BN_INTRO) { bscr_clear(); shadow_init(); }   /* (cut short on one of AOF2's screens) */
    bonus_on = BN_OFF;
}
static void bonus_end(void) {                    /* the result shown: the next stage */
    bonus_off();
    stage_begin(camp + 1, 0);
}
static void bn_result(const char *l1, const char *l2, uint16_t bonus, uint8_t won, uint8_t big) {   /* big: its gbig use (l1 in
                                                    the big font when game.json big_text lists it), 0xFF none */
    bonus_on = BN_END; bn_t = 0; bn_hold = BN_END_T; bn_skip = 90;
    uint8_t r = 16;                              /* its detail line's row, BONUS 2 rows under it */
    if (big < BIG_USES && gbig[big].on) {        /* the big headline covers row 9: its TIME / POSTS line cleared; the
                                                    detail lines right under it (note 20261014-231446-5d29: up with it,
                                                    above the fighters' heads) */
        bn_text(13, 0, 0); FIX_print(17, 9, "                    ", 0); bt_show(l1, big);
        r = (uint8_t)((gbig[big].y + 48 + 7) >> 3);
    } else bn_text(13, l1, 1);
    bn_text(r, l2, 0);
    FIX_print(13, r + 2, "BONUS", 0); FIX_printNum(20, r + 2, bonus, 1);
    snd_music(won ? gbonus.win_music : gbonus.over_music);   /* (AOF2: $2D a passed game, $2E a failed one) */
}
static void bn_result_big(const char *l1, uint8_t big) {   /* a result told by its big headline alone (gbig[big]): every
                                                    fix line of the game (its name, the gauge bar, the prompt) cleared */
    bonus_on = BN_END; bn_t = 0; bn_hold = BN_END_T; bn_skip = 90;
    bar_clear(&bn_bar); bn_text(13, 0, 0); bn_text(20, 0, 0);
    bt_show(l1, big);
    snd_music(gbonus.win_music);
}
/* the top grade's tree (note 20261014-133606-5d29, AOF2 measured: tools/aof/bonus_rip.py spirit_top): AOF2 only passes
 * Spirit Training at the top grade, and then the tree breaks: its cracked trunk, its top falling, the crown squashed
 * as it lands and swaying (bonus.h bonus_fall_seq, ticks from the blow = AOF2's frames from the punch mark); a lower
 * grade leaves it standing (a few leaves, "FAILED THE TRAINING", the fail song). One step a tick, on into the result */
static void bn_fall_step(void) {
    uint8_t k;
    if (!bn_fall_t) return;
    for (k = 0; k < BONUS_N_FALLSEQ; k++) {
        const bonus_fall_t *e = &bonus_fall_seq[k];
        const bonus_obj_t *o;
        if (e->t != bn_fall_t - 1) continue;
        o = &bonus_fall[e->img];
        if (!k) bn_hide(BN_TREE_SPR, 12);         /* the standing tree (its mark in it) goes: the
                                                    cracked one in its place */
        bn_put(BN_FALL_SPR, o, o->x + e->dx, o->y + e->dy, 0, 0xF, e->vs, 1);
        if (o->w < BONUS_FALL_MAXW) bn_hide(BN_FALL_SPR + o->w, BONUS_FALL_MAXW - o->w);
    }
    for (k = 0; k < bn_g->nfall; k++)            /* its sounds (game.json fall_sounds, note 20261014-171700-5d29: AOF2's
                                                    crack and fall, sent on its frames from the punch mark) */
        if (bn_g->fall_t[k] == bn_fall_t - 1) snd_sfx(bn_g->fall_sfx[k]);
    if (bn_fall_t < 0xFFFF) bn_fall_t++;
}
static void bn_leaves(uint8_t n) {               /* n leaves from the canopy (a fixed spread, no random draw) */
    uint8_t k;
    bn_pc_n = n > BN_LEAVES ? BN_LEAVES : n;
    for (k = 0; k < bn_pc_n; k++) {
        bn_pc[k].x = (int16_t)(130 + mod8((uint8_t)(k * 37), 150)) << 4; bn_pc[k].y = (int16_t)(mod8((uint8_t)(k * 23), 70) + 4) << 4;
        bn_pc[k].vx = (k & 1) ? 6 : -6; bn_pc[k].vy = 10 + (k & 3) * 3;
    }
}
static void bn_gauge_flow(fighter_t *f) {
    uint8_t k;
    if (bn_chg_t) {                              /* (note 20261014-133606-5d29, AOF2's Ryo: he stands, concentrates, then
                                                    punches; games[].charge, ticks from the press) */
        bn_chg_t++;
        if (bn_chg_t == bn_g->chg_stand + 1) fighter_pose(f, BA_CHARGE);   /* his charge / power-up / rage (export) */
        if (bn_chg_t > bn_g->chg_blow[bn_pass]) {   /* the blow: from the next tick (bonus_input) */
            bn_chg_t = 0; bn_hit_t = 1;
            if (bn_g->punch_sfx) snd_sfx(bn_g->punch_sfx);
        }
        return;
    }
    if (bn_hit_t) {                              /* after the press: the punch, the shake, the leaves */
        bn_hit_t++;
        if (f->x > FIX(BN_TREE_STOP)) f->x = FIX(BN_TREE_STOP);   /* (the trunk stops a blow that travels) */
        if (bn_hit_t == 12 && bn_pass) bn_fall_t = 1;   /* (the top grade: the tree falls from here) */
        bn_fall_step();
        if (bn_hit_t == 12) {                    /* the blow lands */
            bn_decal(&bonus_tree[0], &bonus_mark[0]);
            bn_leaves(bn_grade * 3);
            snd_sfx(bn_grade >= 4 ? SFX_HIT_CD : ghitsnd.guard);
        }
        if (bn_hit_t >= 12 && bn_hit_t < 36)    /* the tree shakes: 2 px either side, every 2 ticks */
            bn_put(BN_TREE_SPR, &bonus_tree[0], bonus_tree[0].x + (bn_hit_t >= 34 ? 0 : (bn_hit_t & 2) ? 2 : -2), bonus_tree[0].y, 0, 0xF, 0xFF, 0);
        if (bn_hit_t == 20) bn_decal(&bonus_tree[0], &bonus_mark[1]);
        for (k = 0; k < bn_pc_n; k++) {          /* the leaves: falling, swaying */
            bn_pc[k].y += bn_pc[k].vy; bn_pc[k].x += bn_pc[k].vx; if (!((bn_hit_t + k * 5) & 31)) bn_pc[k].vx = -bn_pc[k].vx;
            if ((bn_pc[k].y >> 4) > 224) { bn_hide(BN_LEAF_SPR + k, 1); continue; }
            bn_put(BN_LEAF_SPR + k, &bonus_leaf[((bn_hit_t >> 3) + k) & 1], bn_pc[k].x >> 4, bn_pc[k].y >> 4, 0, 0xF, 0xFF, !((bn_hit_t + k) & 7));
        }
        if (!bn_pass && bn_hit_t >= 12)          /* a failed grade's sounds (games[].fail_sounds: AOF2's, from the punch
                                                    mark; GB_VOICE_HIT his own hurt voice where Ryo hurts his hand) */
            for (k = 0; k < bn_g->nfail; k++)
                if (bn_g->fail_t[k] == bn_hit_t - 12) {
                    if (bn_g->fail_sfx[k] == GB_VOICE_HIT) voice_play(f->ch, f->team, VK_HIT); else snd_sfx(bn_g->fail_sfx[k]);
                }
        if (bn_hit_t == (bn_pass ? BN_FALL_RESULT : 12 + bn_g->fail_result)) {   /* the result: the grade, its reward (a pass: the crown
                                                    down; a fail: AOF2's jingle frame, fail_result) */
            static const char *const GRADE[6] = { "MISS", "WEAK", "FAIR", "GOOD", "GREAT", "PERFECT!" };
            uint8_t add = bn_g->chunks[bn_grade], room = MAX_CHUNKS - drive_chunks, i, byclr = bn_pass && bn_g->pass_n;
            if (byclr) {                         /* (games[].pass_reward: the chunks of this credit's n-th pass) */
                add = bn_clr[bn_game] < bn_g->pass_n ? bn_g->pass_chunks[bn_clr[bn_game]] : 0;
                if (bn_clr[bn_game] < 255) bn_clr[bn_game]++;
            } else if (bn_won >> bn_game & 1) add = 0;   /* (won before: its bonus only) */
            if (add > room) add = room;
            if (add) {
                bn_won |= 1 << bn_game; drive_chunks += add; bn_gain = add;
                for (i = 0; i < 2; i++) fighters[i].drive = (uint16_t)(gmeter.chunk * drive_chunks);
                hud_reset(); hud_two = 0xFF;     /* the bar's new chunks drawn */
            }
            if (byclr) {                         /* a pass: its headline alone (notes 20261016-133045 / -135212-e03d:
                                                    "announce that the player was given more meter with the big font
                                                    and display nothing else"): no grade, no BONUS, the gauge bar gone */
                bn_won |= 1 << bn_game;
                bn_result_big(bn_g->pass_text[add], BIG_BONUS_METER);
            } else
            bn_result(GRADE[bn_grade], !bn_pass ? "TRAINING FAILED" : add == 2 ? "METER +2" : add == 1 ? "METER +1" :
                      bn_g->chunks[bn_grade] && !room ? "METER ALREADY FULL" : 0, (uint16_t)bn_grade * 2000, bn_pass, 0xFF);
        }
        return;
    }
    bn_power += bn_g->step; if (bn_power > 127) bn_power -= 128;   /* (0-127, wrapping: AOF2's) */
    if (bn_bar.px > (int16_t)bn_power * 2) bn_bar.px = bn_bar.trail = -1;   /* (wrapped: no damage trail) */
    bar_draw(&bn_bar, bn_power, 127);
    if (bn_t > 30 && ((JOY_pressed(bn_lead) & JOY_A) || !bn_clock)) {
        bn_grade = 0;
        while (bn_grade < 5 && bn_power >= bn_g->grades[bn_grade]) bn_grade++;
        bn_pass = bn_grade >= bn_g->win_grade;
        if (bn_g->chg_blow[bn_pass]) bn_chg_t = 1; else bn_hit_t = 1;   /* (his concentration first: games[].charge) */
        bn_text(20, 0, 0);
        (void)f;
    }
}
static int16_t bn_px;                            /* the post's screen x: AOF2's place (right), or the left edge when he
                                                    stands on the right half as it drops (a rush carried him past it) */
static void bn_post_show(uint8_t img, int16_t dx, int16_t dy, uint8_t tiles) {
    const bonus_obj_t *o = &bonus_post[img];
    bn_put(BN_POST_SPR, o, bn_px + o->x - bonus_post[0].x + dx, o->y + dy, 0, 0xF, 0xFF, tiles);
}
static void bn_break_flow(fighter_t *f) {
    uint8_t i, k;
    int16_t px0 = bn_px + cam_x + 8, px1 = px0 + 48, py0 = bonus_post[0].y + 8, py1 = 224;   /* (world x, screen y) */
    if (bn_g->breaks == BB_FURY) fighter_meter_fill(f);   /* the fury always payable (its lock lifted: bonus_play) */
    if (bn_post == BP_STAND || bn_post == BP_DROP || bn_post == BP_HIT) {   /* a solid post: he stops at it (a rush too) */
        if (bn_px > 160) { int32_t lim = FIX(px0 - 12); if (f->x > lim) f->x = lim; }
        else { int32_t lim = FIX(px1 + 12); if (f->x < lim) f->x = lim; }
    }
    bn_pt++;
    if (bn_split) {                              /* the last post's splinters: flying, falling */
        for (k = 0; k < BN_PIECES; k++) {
            bn_pc[k].x += bn_pc[k].vx; bn_pc[k].y += bn_pc[k].vy; bn_pc[k].vy += 4;
            bn_put(BN_FRONT + 2 * k, &bonus_piece[k], bn_pc[k].x >> 4, bn_pc[k].y >> 4, 0, 0xF, 0xFF, 0);
        }
        if (!--bn_split) bn_hide(BN_FRONT, 2 * BN_PIECES);
    }
    if (bn_chip_t) {                             /* a hit's chip: flying, falling, gone */
        bn_pc[BN_PIECES].x += bn_pc[BN_PIECES].vx; bn_pc[BN_PIECES].y += bn_pc[BN_PIECES].vy; bn_pc[BN_PIECES].vy += 6;
        if (--bn_chip_t) bn_put(BN_LEAF_SPR, &bonus_piece[bn_hp % BN_PIECES], bn_pc[BN_PIECES].x >> 4, bn_pc[BN_PIECES].y >> 4, 0, 0xF, 0xFF, 0);
        else bn_hide(BN_LEAF_SPR, 2);
    }
    switch (bn_post) {
    case BP_NONE:                                /* the next post drops in */
        if (bn_left && bn_pt >= (bn_t < 100 ? 60 : 24)) {
            bn_post = BP_DROP; bn_pt = 0; bn_hp = bn_g->hp; bn_img = 0;
            bn_px = INT(f->x) - cam_x < 160 ? bonus_post[0].x : 320 - 64 - bonus_post[0].x + 16;   /* (AOF2's 241, mirrored: 31) */
        }
        break;
    case BP_DROP:
        bn_post_show(0, 0, (int16_t)(bn_pt - 8) * 16, bn_pt == 1);
        if (bn_pt >= 8) { bn_post = BP_STAND; bn_pt = 0; snd_sfx(ghitsnd.bounce); }
        break;
    case BP_STAND:
        if (bn_thud) { bn_thud--; bn_post_show(bn_img, (bn_thud & 2) ? 2 : -2, 0, 0); if (!bn_thud) bn_post_show(bn_img, 0, 0, 0); }
        for (i = 0; i < nf; i++) {               /* the fighter and his objects: what strikes the post now */
            int16_t x0, x1, y0, y1;
            uint8_t cls = fighter_strike_box(order[i], &x0, &x1, &y0, &y1);
            if (!cls || order[i]->team || x1 <= px0 || x0 >= px1 || y1 <= py0 || y0 >= py1) continue;
            if (bn_g->breaks == BB_ANY) {        /* any strike (note bonus-pillars-normals): a hit each time one starts
                                                    touching it (a strike held on it counts once), bn_hp hits break it.
                                                    Note 20261016-111341-e03d (Terry's two-hit link 4, anim 13: "why only
                                                    one hit on the trunk and not two?"): its second hit's step touched the
                                                    post without a gap, so the touch rule counted the move once. Now the
                                                    post is a target like a fighter: each HIT of a move counts once (its
                                                    hit_mask bit BN_POST_BIT, cleared by the move's next hit window:
                                                    fighter.c's multi-hit steps, a new move) */
                if (order[i]->hit_mask & BN_POST_BIT) continue;
                order[i]->hit_mask |= BN_POST_BIT;
                spark_hit(x0 > px0 ? (x0 + px1) >> 1 : (px0 + x1) >> 1, (y0 > py0 ? y0 : py0) + 16, 0, f->facing);
                fighter_prop_hit(order[i], bn_hp > 1);   /* a hit for the chain as on a fighter (note 20261014-231537-5d29:
                                                    its hit-stop, chain credit, cancel windows, its hit sound) */
                if (bn_hp > 1) {                 /* it holds: it shakes, a chip flies off */
                    uint8_t d = 0, taken;
                    bn_hp--; bn_thud = 16; bn_pt = 0;
                    taken = bn_g->hp - bn_hp;    /* its damage shown (games[].damage_at, note 20261015-221208-e03d
                                                    round 2): AOF2's cracked pictures 1-3 from those hits taken */
                    while (d < 3 && taken >= bn_g->dmg_at[d]) d++;
                    if (d != bn_img) { bn_img = d; bn_post_show(bn_img, 0, 0, 1); }
                    bn_chip_t = 30; bn_pc[BN_PIECES].x = (bn_px + 24) << 4; bn_pc[BN_PIECES].y = (py0 + 40 + 8 * (bn_hp & 3)) << 4;
                    bn_pc[BN_PIECES].vx = bn_px < 160 ? -24 : 24; bn_pc[BN_PIECES].vy = -48;
                    bn_put(BN_LEAF_SPR, &bonus_piece[bn_hp % BN_PIECES], bn_pc[BN_PIECES].x >> 4, bn_pc[BN_PIECES].y >> 4, 0, 0xF, 0xFF, 1);
                    break;
                }
                bn_hp = 0; bn_post = BP_HIT; bn_pt = 17; bn_img = 0;   /* the last: straight to its splinters */
                snd_sfx(SFX_HIT_CD);
                break;
            }
            if (cls == 2) {                      /* a fury: burnt, then broken */
                bn_post = BP_HIT; bn_pt = 0; bn_img = 1;
                spark_hit(x0 > px0 ? (x0 + px1) >> 1 : (px0 + x1) >> 1, (y0 > py0 ? y0 : py0) + 16, 1, f->facing);
                snd_sfx(SFX_HIT_CD);
                break;
            }
            if (!bn_thud) { bn_thud = 16; fighter_guard_sound(); if (!bn_lesson) bn_lesson_show(1); bn_pt = 0; }
        }
        if (bn_lesson && bn_t > 150 && bn_pt > 120 && !bn_thud) bn_lesson_show(0);
        break;
    case BP_HIT:                                 /* AOF2's burnt post, its three pictures by turns */
        if (bn_g->breaks == BB_ANY) bn_pt = 18;  /* (no fury: no burn, the splinters at once) */
        else if (!(bn_pt & 3)) { bn_img = bn_img == 3 ? 1 : bn_img + 1; bn_post_show(bn_img, 0, 0, 1); }
        if (bn_pt == 1 && bn_g->breaks == BB_FURY) bn_post_show(1, 0, 0, 1);
        if (bn_pt >= 18) {                       /* the splinters fly (bn_split), the next post may come meanwhile */
            bn_post = BP_NONE; bn_pt = 0; bn_hide(BN_POST_SPR, 4); bn_left--; bn_split = 48;
            FIX_print(34, 9, "  ", 0); FIX_printNum(34, 9, bn_left, 1);
            for (k = 0; k < BN_PIECES; k++) {
                const bonus_obj_t *o = &bonus_piece[k];
                bn_pc[k].x = (o->x - bonus_post[0].x + bn_px) << 4; bn_pc[k].y = o->y << 4;
                bn_pc[k].vx = (int16_t)((k * 13) & 15) + 8 + (k & 1) * 10; bn_pc[k].vy = -(int16_t)(40 + ((k * 7) & 15) * 4);
                if (bn_px < 160) bn_pc[k].vx = -bn_pc[k].vx;   /* (away from him) */
                bn_put(BN_FRONT + 2 * k, o, bn_pc[k].x >> 4, o->y, 0, 0xF, 0xFF, 1);
            }
            snd_sfx(SFX_HIT_CD);
        }
        break;
    }
    {   uint16_t s = div16(bn_clock + 59, 60);       /* the clock, the posts left (AOF2: top right) */
        if (s != bn_shown_clock) { bn_shown_clock = s; FIX_print(17, 9, "TIME   ", 0); FIX_printNum(22, 9, s, 1); FIX_print(28, 9, "POSTS   ", 0); FIX_printNum(34, 9, bn_left, 1); }
    }
    if (!bn_left && bn_post == BP_NONE && !bn_split) {   /* every post broken (its splinters landed) */
        uint8_t first = !(bn_won >> bn_game & 1);
        bn_won |= 1 << bn_game;
        if (bn_g->unlock == BU_FURY) bn_lock0 = 0;
        fury_lock = bn_lock0; bn_lesson_show(0);
        if (first && bn_g->referee) {            /* SS2's referee tells it (games[].won_by "referee", note
                                                    20261015-221208-e03d): no result box, his speech, then the next stage */
            bonus_on = BN_END; bn_t = 0; bn_hold = 0xFFFF; bn_skip = 0xFFFF;
            snd_music(gbonus.win_music);
            rf_start(bn_g->won_text, INT(f->x) - cam_x);
            return;
        }
        bn_result("CONGRATULATIONS!", 0, (uint16_t)bn_g->count * 1000, 1, 0xFF);
        if (first && bn_g->unlock == BU_FURY) {  /* the unlock's message box (games[].won_text), held won_ticks */
            if (gbig[BIG_BONUS_WON].on) {        /* its headline in the big font (big_text.bonus_won: y, its two
                                                    lines pitch px apart): CONGRATULATIONS and BONUS on the two rows over
                                                    it, the detail lines on the two under it (note 20261014-231446-5d29:
                                                    the block above the fighters, under the top HUD) */
                const gbig_t *g = &gbig[BIG_BONUS_WON];
                uint8_t r0 = (uint8_t)(g->y >> 3), r1 = (uint8_t)((g->y + g->pitch + 48 + 7) >> 3);
                bn_text(13, 0, 0); bn_text(16, 0, 0); bn_text(18, 0, 0);
                bn_text(r0 - 2, "CONGRATULATIONS!", 1);
                FIX_print(13, r0 - 1, "BONUS", 0); FIX_printNum(20, r0 - 1, (uint16_t)bn_g->count * 1000, 1);
                FIX_print(17, 9, "                    ", 0); bt_show(bn_g->won_text[0], BIG_BONUS_WON); bn_text(r1, bn_g->won_text[1], 0); bn_text(r1 + 1, bn_g->won_text[2], 0);
            } else { bn_text(20, bn_g->won_text[0], 1); bn_text(22, bn_g->won_text[1], 0); bn_text(24, bn_g->won_text[2], 0); }
            bn_hold = bn_g->won_ticks; bn_skip = bn_hold >> 1;
        }
    } else if (!bn_clock) {                      /* time over: as it was (locked stays locked) */
        fury_lock = bn_lock0; bn_lesson_show(0); bn_hide(BN_POST_SPR, 4); bn_hide(BN_FRONT, 2 * BN_PIECES); bn_split = 0;
        bn_result("TIME OVER", fury_lock ? "THE FURY STAYS LOCKED" : 0, (uint16_t)(bn_g->count - bn_left) * 1000, 0, BIG_TIME_OVER);
    }
}
static void bonus_input(void) {                  /* this tick's intents: the gauge game plays his A for him; the posts
                                                    game keeps him on his lane; the result: nothing */
    intent_t *i = &in[bn_lead];
    if (bn_fall_t >= BN_FALL_LEAP && bn_fall_t < BN_FALL_LEAP + 10) {   /* the tree's top falls on him: he leaps back out
                                                    of its way (AOF2: Ryo from frame ~762, landing ~80 px back) */
        *i = (intent_t){ 0 }; i->dx = -1; i->hold = IN_B; if (bn_fall_t == BN_FALL_LEAP) i->press = IN_B; return;
    }
    if (rf.body) in[RF_IDX] = (intent_t){ 0 };   /* the referee's body: never acts (after the AI's intents) */
    if (bonus_on == BN_END && rf.quirk == RQ_RUN) {   /* the referee's D quirk: run at him (onto his lane), then the fury */
        fighter_t *f = &fighters[bn_lead];
        int16_t dx = rf.x + cam_x - INT(f->x), ad = dx < 0 ? -dx : dx, dz = BN_FEET_Z + REF_LAND_DY - INT(f->z);
        int8_t s = dx < 0 ? -1 : 1;
        *i = (intent_t){ 0 };
        if (f->state != S_IDLE && f->state != S_WALK && f->state != S_RUN) return;   /* (his run's stop first) */
        if (dz && rf.t < 240) i->dz = dz < 0 ? -1 : 1;
        if (ad > gref.fury_dx && rf.t < 180) { i->dx = s; i->run = 1; return; }
        if (f->state != S_IDLE || (dz && rf.t < 240)) return;
        i->face = s; fighter_meter_fill(f); i->press = IN_D; rf.quirk = RQ_FURY;
        rf_body_on();
        return;
    }
    if (bonus_on == BN_END || (bn_g->kind == BK_GAUGE && bn_hit_t != 1)) { *i = (intent_t){ 0 }; return; }
    if (bn_g->kind == BK_GAUGE) { *i = (intent_t){ 0 }; fighter_blow(&fighters[bn_lead], bn_g->blows[bn_grade]); return; }   /* the
                                                    press: the grade's blow at the tree (games[].blows: his jab, his forward finisher) */
    if (!(i->press & (IN_A | IN_C | IN_D)) || (i->press & IN_B)) i->dz = 0;   /* his lane: no depth walk or jump; a
                                                    button's tick keeps the stick (note 20261016-044016-e03d: down + C
                                                    is the slot pick, SS2 Hanzo's projectile; down + D the MAX, down +
                                                    A the down finisher) */
}
static void bonus_flow(void) {                   /* the fight tick's flow() for a bonus game (after the fighters' update) */
    fighter_t *f = &fighters[bn_lead];
    bn_t++;
    if (bonus_on == BN_END) {
        if (rf.ph) { if (!rf_tick()) bonus_end(); return; }   /* the referee's speech (the result's place) */
        bn_fall_step();                          /* (the fallen crown sways on under the result) */
        if (bn_t >= bn_hold || (bn_t > bn_skip && (JOY_pressed(bn_lead) & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)))) bonus_end();
        return;
    }
    if (bn_g->show_name && (bn_t == 1 || bn_t == 60)) centre(13, bn_t == 1 ? bn_g->name : "                  ");
    if (bn_clock && !sf_who && !(bn_g->kind == BK_GAUGE && (bn_hit_t || bn_chg_t))) bn_clock--;
    if (bn_g->kind == BK_GAUGE) bn_gauge_flow(f); else bn_break_flow(f);
}
static void unlock_start(uint8_t k);
static void ending_start(void);
static void stage_next(void) {                   /* the stage after camp: a bonus first when the data has one there */
    bt_hide();                                   /* (STAGE CLEAR) */
    if (!attract && !lab.active && gbonus.ngames && gbonus.after[camp] && bonus_on == BN_OFF) bonus_start();
    else stage_begin(camp + 1, 0);
}
static void campaign(uint8_t left) {
    uint8_t i;
    phase_t++;
    if (!attract && !ko_seq) {                               /* (the boss's death: no trigger any more) */
        triggers();
        left += tq_n;                                        /* queued spawns count as enemies */
        if (dr_on) return;                                   /* a trigger's scene: the campaign waits for it */
        if (trig_held && !left) { trig_held = 0; lock_x = lock_at(wave < gs->nwaves ? gs->waves[wave].lock : gs->boss_lock); }
    }
    switch (phase) {
    case PH_WAVE:                                            /* camera held at lock_x until the wave is beaten */
        if (left) break;
        if (attract && wave + 1 >= gs->nwaves) { spawn_wave(); break; }   /* the demo: no boss, the last wave again */
        waves_cleared = wave + 1;
        wave++; phase = PH_GO; phase_t = 0;
        lock_x = lock_at(wave < gs->nwaves ? gs->waves[wave].lock : gs->boss_lock);
        break;
    case PH_GO:                                              /* GO: the camera may scroll to the next lock point */
        if ((phase_t & 15) == 1) go_sign(!(phase_t & 16));   /* blinking, on from its first frame */
        if (wave >= gs->nwaves) boss_pretint();              /* (CPU budget B: the boss's tinted colours made ahead) */
        if (cam_x < lock_x || trig_held || left) break;     /* a trigger's lock or enemies: they first */
        go_sign(0);
        if (wave < gs->nwaves) { phase = PH_WAVE; spawn_wave(); } else boss_start();
        break;
    case PH_BOSS:                                            /* its death sequence played (boss_ko_tick), or gone */
        if (ko_seq != KO_DONE && fighters[BOSS_IDX].state != S_OFF) break;
        enemies_down(&fighters[BOSS_IDX]);                   /* boss beaten: the minions go down with it */
        tq_n = 0; waves_cleared = gs->nwaves + 1;
        phase = PH_END; phase_t = 0;
        break;
    case PH_END:                                             /* every enemy gone: STAGE CLEAR, the save */
        if (left) break;
        if (gbig[BIG_STAGE_CLEAR].on) bt_show(0, BIG_STAGE_CLEAR); else FIX_print(14, 13, "STAGE CLEAR", 0);   /* (big_text) */
        if (!ko_seq) snd_music(GAME_MUS_CLEAR);   /* (a boss KO: boss_ko_tick starts it, at rest) */
        phase = PH_CLEAR; phase_t = 0; unlock_k = 0; win_dr = 0; lad_new = 0;
        win_start();                                         /* the players' win poses (#184) */
        if (attract) break;
        if (LAD_N && camp + 1 >= GS_COUNT && save.rungs < LAD_RUNGS) lad_new = ++save.rungs;   /* the game clear: the
                                                             ladder's next rung (shown after the ending: ladder_start) */
        if (gs->unlock && !(save.unlocked >> camp & 1)) { save.unlocked |= 1 << camp; unlock_k = camp + 1; }
        save_write();
        break;
    case PH_CLEAR:
        if (phase_t < 200 || (!win_done() && phase_t < WIN_MAX) || (ko_seq && !ko_win)) break;   /* the win poses played (and a
                                                                boss KO's clear music started), then the next screen: a
                                                                cut (no fades) */
        if (!win_dr) {                                       /* first the winner's big portrait, KOF's win screen in drama
                                                                mode (game.json win_drama; note 20261009-230403-b3f3): its
                                                                scenes skip a player whose fighter has none (if_portrait) */
            win_dr = 1;                                      /* (the last stage: none, the ending shows the portrait) */
            if (DR_WIN < DR_COUNT && !attract && camp + 1 < GS_COUNT && (dr = &gdramas[DR_WIN], dr_next(0) < dr->n)) {
                FIX_print(14, 13, "           ", 0); bt_hide(); drama_start(DR_WIN, 0xFF); break;
            }
        }
        if (snd_song == GAME_MUS_CLEAR && snd_song_t < GAME_MUS_CLEAR_FRAMES) break;   /* the clear song played to its end
                                                                (note 20261015-145350-e03d: a fighter without a big
                                                                portrait skipped the drama and cut it) */
        for (i = 0; i < 2; i++)
            if ((pl_on[i] = in_play(&fighters[i]))) { pl_ch[i] = fighter_next_stage_ch(&fighters[i]); pl_set[i] = fighters[i].set; }   /* (its base form) */
        if (camp + 1 >= GS_COUNT) ending_start();          /* the last stage: the ending (BOSS UNLOCKED after it) */
        else if (unlock_k) unlock_start(unlock_k - 1);
        else stage_next();                                   /* (a bonus stage first: game.json bonus.after) */
        break;
    }
}
/* ---- continue and GAME OVER (SNK convention, TODO #57): a player whose last life is gone counts 9 -> 0, a number a
 * second (60 ticks); A-D jump to the next number. START (MVS: with a credit, the BIOS's PLAYER_START; AES: START, free
 * continues as SNK's home carts) brings him back where he fell, full life, the lives reset. While the other player is
 * in play the count shows in his HUD block and the fight goes on; with nobody in play the fight freezes under the
 * CONTINUE? overlay, KOF98's continue song ($2F) playing. Every count at 0: a cut to the GAME OVER screen
 * (KOF98's loser theme $26), then back to the BIOS (MVS: SYSTEM_RETURN commits the save; title while credits remain,
 * else the demo; AES: the demo). The attract demo's bot has no continue: its last life ends the demo. ---- */
static void show_start(uint8_t m, uint8_t c, uint8_t set, uint16_t wall);
static void centre(uint8_t row, const char *t);
static uint8_t cont_mus, cont_txt[2], cont_prompt;
static uint16_t cont_ft;
static void p2_join(void) {                      /* P2 joins mid-fight: START with a credit (PLAYER_START) */
    uint8_t c, i, used;
    for (c = 0; c < BC_COUNT; c++) {                         /* an unlocked fighter nobody on screen is */
        used = &bm_chars[c] == fighters[0].ch || fighters[0].form_from == c + 1 || char_locked(c);   /* (P1's base form too) */
        for (i = 2; i < NF && !used; i++) used = fighters[i].state != S_OFF && fighters[i].ch == &bm_chars[c];
        if (!used) break;
    }
    if (c >= BC_COUNT)                                       /* every unlocked one on screen (the ladder's first rungs):
                                                                an unlocked one other than P1's, an enemy may share it */
        for (c = 0; c < BC_COUNT && (char_locked(c) || &bm_chars[c] == fighters[0].ch); c++) ;
    fighter_init(&fighters[1], &bm_chars[c < BC_COUNT ? c : 1], 1, 16 + MAX_PALS, 0, cam_x + 40, 20);
    fighters[1].idx = 1; fighter_revive(&fighters[1]); lives[1] = 2; BIOS_PLAYER_MOD[1] = 1;
    if (CHEAT_GAME) fighter_meter_fill(&fighters[1]);        /* (the cheat: as P1, both bars full) */
    bios_start &= ~2;
}
#define DEATH_BLINK 60            /* frames a dead fighter blinks (players: with its death voice) before it goes */
static void respawn(fighter_t *f) {              /* a life used or a continue: it drops back in where it fell,
                                                    inside the screen (fighter.c "death and respawn", TODO #166 e) */
    int16_t x = INT(f->x);
    if (x < cam_x + 24) x = cam_x + 24;
    if (x > cam_x + 296) x = cam_x + 296;
    f->x = FIX(x);
    fighter_respawn(f);
}
static void cont_player(uint8_t p) {             /* one player: START continues (or rejoins), the count, A-D */
    fighter_t *f = &fighters[p];
    if (p && !p2_in()) return;
    if (!in_play(f) && (bios_start & (1 << p))) {            /* where he fell, inside the screen */
        cont_t[p] = 0; lives[p] = 3; BIOS_PLAYER_MOD[p] = 1;
        respawn(f);
        return;
    }
    if (!cont_t[p]) return;
    if (JOY_pressed(p) & (JOY_A | JOY_B | JOY_C | JOY_D)) cont_t[p] = (uint16_t)cont_digit(p) * 60 + 1;   /* the next
                                                             number at once (at 0: the count ends) */
    if (!--cont_t[p]) BIOS_PLAYER_MOD[p] = 3;
}
static void ov_put(uint8_t col, uint8_t row, const char *t, uint8_t pal) { while (*t) dr_put(col++, row, *t++, pal); }
#define OV_R0 10                                 /* the overlay box: fix rows 10-17, columns 9-30 */
#define OV_R1 17
static void cont_box(uint8_t on) {
    uint8_t r, c;
    for (r = OV_R0; r <= OV_R1; r++) for (c = 9; c <= 30; c++) fix_put(c, r, on ? DRAMA_FONT + ' ' : 0x20);
    cont_txt[0] = cont_txt[1] = 0xFF; cont_prompt = 0xFF;
    if (on) ov_put(15, 11, "CONTINUE?", 1);
}
static void cont_draw(void) {
    uint8_t p, two = p2_in() || in_play(&fighters[1]), v;
    char t[3] = { 0, 0, 0 };
    for (p = 0; p < 1 + two; p++) {
        v = cont_t[p] ? cont_digit(p) : 0xFE;                /* 0xFE: this player's count is over */
        if (v == cont_txt[p]) continue;
        cont_txt[p] = v;
        t[0] = v == 0xFE ? '-' : '0' + v; t[1] = v == 0xFE ? '-' : ' ';
        if (two) { ov_put(p ? 23 : 12, 14, p ? "2P" : "1P", 0); ov_put(p ? 26 : 15, 14, t, 0); }
        else ov_put(19, 14, t, 0);
    }
    v = BIOS_MVS_FLAG && !CREDITS_P1 && !(cont_t[1] && CREDITS_P2) ? 1 : 0;   /* MVS without a credit: INSERT COIN (SNK's
                                                             BIOS keeps each player's credits, his own coin slot) */
    v |= (cont_ft & 32) ? 2 : 0;                             /* blinking */
    if (v != cont_prompt) { cont_prompt = v; ov_put(14, 16, v & 2 ? "           " : v & 1 ? "INSERT COIN" : "PRESS START", 0); }
}
static void gameover_start(void) {
    fighter_t *f = &fighters[0];
    show_start(5, char_index(f->ch), f->set, RGB8(0, 0, 0));
    fighter_play(&fighters[0], BA_DOWN);                     /* the player lies on the floor */
    if (gbig[BIG_GAME_OVER].on) bt_show(0, BIG_GAME_OVER); else centre(10, "GAME OVER");   /* (big_text) */
    centre(13, gstage_names[camp]);                          /* the stage's name (game.json stages[].name) */
    if (GAME_MUS_OVER) snd_music(GAME_MUS_OVER);             /* (0: KOF98's way, the continue song fading out: cont_tick) */
}
static void cont_tick(void) {                    /* the fight frozen under the overlay */
    uint8_t p;
    cont_ft++;
    if (cont_ov == 2) { gameover_start(); return; }          /* every count at 0: GAME OVER (a cut) */
    if ((bios_start & 2) && !p2_in()) p2_join();
    for (p = 0; p < 2; p++) cont_player(p);
    bios_start = 0;
    if (in_play(&fighters[0]) || in_play(&fighters[1])) {    /* a continue: the fight goes on, its music back */
        cont_box(0); cont_ov = 0; hud_two = 0xFF; arcade_line_reset(); hud_wave();
        snd_music(cont_mus);
        return;
    }
    if (!cont_t[0] && !cont_t[1]) {                          /* $20: stop; game.json music.gameover FADE: KOF98's GAME OVER,
                                                                $0A + speed fades the continue song out (TODO #154) */
        cont_box(0); cont_ov = 2; cont_ft = 0;
        if (GAME_MUS_OVER) snd_cmd(0x20); else { snd_cmd(0x0A); snd_cmd(GAME_OVER_FADE); }
        return;
    }
    cont_draw();
}
static void flow(void) {
    uint8_t i, p, left = 0;
    for (i = 2; i < NF; i++) {
        fighter_t *e = &fighters[i];
        if (e->state == S_DEAD && e->state_t > DEATH_BLINK) e->state = S_OFF;   /* blinked out */
        if (e->state != S_OFF) left++;
    }
    if (!attract && in_play(&fighters[0]) && (JOY_pressed(0) & JOY_START)) dbg_on ^= 1;   /* box viewer: P1 START in play
                                                             (P2 START joins; a START that continues isn't in play yet) */
    if ((bios_start & 2) && !attract && !p2_in()) p2_join();
    for (p = 0; p < 2; p++) {
        fighter_t *f = &fighters[p];
        if (f->state == S_DEAD && f->state_t > DEATH_BLINK) {   /* blinked out (fighter.c "death and respawn") */
            if (lives[p]) { lives[p]--; respawn(f); }            /* a life: it drops back in */
            else if (attract) SYS_return();                  /* the demo's bot: no continue */
            else { f->state = S_OFF; cont_t[p] = CONTINUE; BIOS_PLAYER_MOD[p] = 2; }
        }
        if (f->drop == 2) {                                      /* its drop landed: every enemy on screen goes down */
            f->drop = 0; snd_sfx(SFX_HIT_CD);
            for (i = 2; i < NF; i++) {
                fighter_t *e = &fighters[i];
                int16_t sx = INT(e->x) - cam_x;
                if (e->team == f->team || sx < -16 || sx > 336) continue;
                if (e->state == S_OFF || e->state == S_DEAD || e->state == S_PROJ || e->state == S_DOWN ||
                    e->state == S_GETUP || e->state == S_KNOCKDOWN || e->state == S_THROWN) continue;
                fighter_quake(f, e);
            }
        }
        cont_player(p);
    }
    bios_start = 0;
    if (!in_play(&fighters[0]) && !in_play(&fighters[1])) {  /* nobody in play: the fight freezes, CONTINUE? */
        cont_ov = 1; cont_ft = 0; cont_mus = snd_song; snd_music(GAME_MUS_CONTINUE); cont_box(1); cont_draw();
        return;
    }
    campaign(left);
}

/* ---- Chain Lab training (examples/brawler/README.md "Chain Lab"): the page (tools/brawler/chainlab) drives the game
 * through the lab mailbox (fighter.h lab_t): req 1 = P1 (lab.fighter) against one standing dummy (lab.dummy) on the
 * first stage, no waves, no timer, the camera fixed; the dummy never attacks, gets up after a knockdown and its life
 * refills when it stands; req 2 = both back to their marks. The fix layer shows the last combo's hits and damage (a
 * combo: P1's hits while the dummy has not recovered). The game itself (fighter.c) is the normal one. ---- */
#define LAB_DUMMY 2
static uint8_t lab_seen, lab_recovered = 1, lab_shown_hits = 0xFF;
static uint16_t lab_shown_dmg = 0xFFFF;
#if LAB_BUILD
/* ---- PRACTICE MODE (Lab builds only: -DLAB_BUILD=1, make LAB_FIGHTER=<f> / LAB_SHELL=1; Bruno 2026-10-10) -------------
 * The Chain Lab's training (req 1) grown into a practice mode: a Lab build boots straight into it (game_enter: P1 = the
 * build's LAB fighter, stage 1, the dummies) and START opens a menu on the fix layer (the game paused; the stick picks a
 * line, left / right / A change it, B or START closes). The settings are the RAM block `prac` (fighter.h prac_t: its
 * layout; the Player and the page read / write the same bytes), kept across a reset and a pack swap. The holds (P1's
 * life, the fury gauge, the drive) are written after every tick's update; the dummies are fighter slots 2.. (a minion's
 * power, life 60, the lab's dummy fighter in successive colour sets); the waves' enemies take the slots after them. */
prac_t prac __attribute__((section(".noinit")));
static const uint8_t PS_N[PS_COUNT] = { 3, 2, 2, 3, 5, 3, 2, 2, 2 };   /* values per setting (fighter.h PS_*) */
static uint8_t pm_on, pm_row, pm_nd = 0xFF, pm_mode = 0xFF, pm_waves, pw_wave, pw_t;
static void lab_place(void);
static void lab_start(uint8_t kind);
static void prac_check(void) {                               /* power-on garbage or a bad write: the defaults */
    uint8_t k, ok = prac.magic[0] == 'P' && prac.magic[1] == 'R' && prac.magic[2] == 'C' && prac.magic[3] == '1';
    for (k = 0; ok && k < PS_COUNT; k++) if (prac.set[k] >= PS_N[k]) ok = 0;
    if (ok && prac.fighter < BC_COUNT && prac.dummy < BC_COUNT) return;
    prac.magic[0] = 'P'; prac.magic[1] = 'R'; prac.magic[2] = 'C'; prac.magic[3] = '1';
    for (k = 0; k < sizeof prac.set; k++) prac.set[k] = 0;
    prac.set[PS_DUMMIES] = 1;                                /* = the Chain Lab's training: one standing dummy */
    prac.menu = 0; prac.fighter = 0; prac.dummy = BC_COUNT > 1 ? 1 : 0; prac.pad = 0;
}
static const int16_t PD_X[4] = { 190, 240, 240, 50 };        /* the dummies' marks: camera x + PD_X, z PD_Z (P1's: 110, */
static const int8_t  PD_Z[4] = { 34, 18, 50, 34 };           /* 34; the fourth stands behind him) */
static void prac_dummy(uint8_t k) {                          /* dummy k at its mark, its behaviour */
    uint8_t c = lab.dummy < BC_COUNT ? lab.dummy : 0, slot = LAB_DUMMY + k;
    const genemy_t *en = &genemies_rom[EN_MINION];
    fighter_t *d = &fighters[slot];
    enemy_init(slot, c, k + (c == pl_ch[0]), cam_x + PD_X[k], PD_Z[k], 0, en);
    d->hp = LIFE; d->hp_max = 0;                             /* (the Chain Lab dummy's life) */
    if (prac.set[PS_MODE] == 1) { ai_set(slot, en->ai); ai_skip &= (uint8_t)~(1 << slot); }
    else ai_skip |= 1 << slot;                               /* stand / walk in: prac_input drives it */
}
static void prac_dummies(void) {                             /* the dummies at their marks (and no wave enemies: the next wave comes) */
    uint8_t k;
    for (k = LAB_DUMMY; k < NF; k++) fighters[k].state = S_OFF;
    ai_skip = 0; pm_nd = prac.set[PS_DUMMIES]; pm_mode = prac.set[PS_MODE]; pw_t = 0;
    for (k = 0; k < pm_nd; k++) prac_dummy(k);
    fighters[0].target = pm_nd ? &fighters[LAB_DUMMY] : 0;   /* the HUD shows the first one */
    lab_recovered = 1;
}
static void prac_wave(void) {                                /* the first stage's next wave, in the slots after the dummies */
    const gwave_t *w;
    uint8_t k, slot = LAB_DUMMY + pm_nd;
    if (pw_wave >= gs->nwaves) pw_wave = 0;
    w = &gs->waves[pw_wave++];
    for (k = 0; k < w->n && slot < NF; k++, slot++) {
        const gspawn_t *sp = &gs->spawns[w->first + k];
        spawn(slot, sp, 0xFF); ai_set(slot, ai_of(&genemies[sp->enemy])); ai_skip &= (uint8_t)~(1 << slot);
    }
}
static uint8_t prac_ai(void) { return prac.set[PS_MODE] == 1 || prac.set[PS_WAVES]; }   /* ai_update runs */
static void prac_input(void) {                               /* the dummies' intents (after the AI's): stand, or walk in and attack */
    fighter_t *p = &fighters[0];
    uint8_t k, m = prac.set[PS_MODE];
    if (m == 1 || lab.active != 1) return;
    for (k = 0; k < pm_nd; k++) {
        uint8_t i = LAB_DUMMY + k;
        fighter_t *d = &fighters[i];
        int16_t dx = INT(p->x) - INT(d->x), dz = INT(p->z) - INT(d->z), adx = dx < 0 ? -dx : dx, adz = dz < 0 ? -dz : dz;
        in[i] = (intent_t){ 0 };
        in[i].face = dx < 0 ? -1 : 1;                        /* standing: it turns to face P1 */
        if (m != 2 || !in_play(p) || p->state == S_DEAD || d->state == S_OFF) continue;
        in[i].ai = 1;                                        /* walk in: to P1's line, within 48 px, then A every 32 frames */
        if (adz > 3) in[i].dz = dz < 0 ? -1 : 1;
        if (adx > 48) in[i].dx = dx < 0 ? -1 : 1;
        else if (adz <= 6 && !((lab.frame + k * 11) & 31)) in[i].press = IN_A;
    }
}
/* the START menu: an opaque box (the drama font's blank cells, as CONTINUE?) on fix rows PM_R0-PM_R1, columns 5-34 */
#define PM_R0 8
#define PM_R1 25
#define PM_N  (PS_COUNT + 3)
enum { PM_RESET = PS_COUNT, PM_APPLY, PM_EXIT };
static const char *const PM_LBL[PM_N] = { "FURY GAUGE", "MAX READY", "DRIVE", "P1 LIFE", "DUMMIES", "DUMMY MODE", "WAVES",
                                          "DUMMY LIFE", "HIT BOXES", "RESET POSITIONS", "APPLY CONFIG NOW", "EXIT" };
static const char *const PM_VAL[PS_COUNT][3] = { { "GAME", "FULL", "EMPTY" }, { "OFF", "ON" }, { "NORMAL", "INFINITE" },
    { "REFILL", "NORMAL", "LOW" }, { "0", "1", "2" }, { "STAND", "AI ON", "ATTACK" }, { "OFF", "ON" },
    { "INFINITE", "NORMAL" }, { "OFF", "ON" } };
static void pm_line(uint8_t r) {
    uint8_t row = PM_R0 + 3 + r;
    ov_put(7, row, r == pm_row ? ">" : " ", 1);
    ov_put(9, row, PM_LBL[r], r == pm_row ? 1 : 0);
    if (r >= PS_COUNT) return;
    ov_put(26, row, "        ", 0);
    if (r == PS_DUMMIES) { char t[2] = { (char)('0' + prac.set[r]), 0 }; ov_put(26, row, t, 1); }
    else ov_put(26, row, PM_VAL[r][prac.set[r]], 1);
}
static void pm_box(uint8_t on) {
    uint8_t r, c;
    for (r = PM_R0; r <= PM_R1; r++) for (c = 5; c <= 34; c++) fix_put(c, r, on ? DRAMA_FONT + ' ' : 0x20);
}
static void pm_open(void) {
    uint8_t r;
    pm_on = 1; prac.menu = 1;
    pm_box(1);
    ov_put(16, PM_R0 + 1, "PRACTICE", 1);
    for (r = 0; r < PM_N; r++) pm_line(r);
    ov_put(7, PM_R1 - 1, "STICK  CHOOSE / CHANGE", 0);
    ov_put(7, PM_R1, "A SET   B / START CLOSE", 0);
    snd_ssg(SSG_CONFIRM);
}
static void pm_close(void) { pm_on = 0; prac.menu = 0; pm_box(0); }
static void pm_tick(void) {                                  /* the game paused: game_tick only draws */
    uint16_t pr = JOY_pressed(0);
    uint8_t r = pm_row, v, n;
    bios_start = 0;
    if (pr & (JOY_B | JOY_START)) { pm_close(); snd_ssg(SSG_CANCEL); return; }
    if (pr & (JOY_UP | JOY_DOWN)) {
        pm_row = (pr & JOY_DOWN) ? (pm_row + 1 < PM_N ? pm_row + 1 : 0) : (pm_row ? pm_row - 1 : PM_N - 1);
        pm_line(r); pm_line(pm_row); snd_ssg(SSG_CURSOR); return;
    }
    if (r < PS_COUNT && (pr & (JOY_LEFT | JOY_RIGHT | JOY_A))) {   /* a setting: right / A next value, left the previous */
        v = prac.set[r]; n = PS_N[r];
        prac.set[r] = (pr & JOY_LEFT) ? (v ? v - 1 : n - 1) : (v + 1 < n ? v + 1 : 0);
        pm_line(r); snd_ssg(SSG_CURSOR);
    } else if (r >= PS_COUNT && (pr & JOY_A)) {               /* an action, then back to the game */
        if (r == PM_RESET) lab_place();
        else if (r == PM_APPLY) lab.tnow = 1;                /* the TRY blob pending: applied on the next tick ("apply now") */
        pm_close(); snd_ssg(SSG_CONFIRM);
    }
}
static void prac_flow(fighter_t *p) {                        /* lab_flow's practice part, after the tick's update */
    uint8_t k, rec = 1;
    int16_t full = p->hp_max ? p->hp_max : LIFE, lo;
    prac_check();
    if (prac.set[PS_DUMMIES] != pm_nd || prac.set[PS_MODE] != pm_mode) prac_dummies();   /* (the menu, the page) */
    lo = (int16_t)div16((uint16_t)full * gmeter.low, 100); if (lo < 1) lo = 1;   /* fighter_low's threshold */
    if (!lab.p1_life) {                                      /* (lab.p1_life: the proofs' "left to the game") */
        if (prac.set[PS_MAX] || prac.set[PS_LIFE] == 2) { if (p->hp > 0) p->hp = lo; }   /* the red blinking bar */
        else if (prac.set[PS_LIFE] == 0) p->hp = LIFE;       /* nobody hurts P1 (the Chain Lab's) */
    }
    if (p->state == S_DEAD && p->state_t > DEATH_BLINK) fighter_revive(p);   /* the game's life: a KO, then up again */
    if (prac.set[PS_MAX] || prac.set[PS_FURY] == 1) p->fgauge = gmeter.fury_max;
    else if (prac.set[PS_FURY] == 2) p->fgauge = 0;
    if (prac.set[PS_MAX] || prac.set[PS_DRIVE]) p->drive = (uint16_t)(gmeter.chunk * gmeter.chunks);
    for (k = 0; k < pm_nd; k++) {
        fighter_t *d = &fighters[LAB_DUMMY + k];
        if (d->state == S_OFF) continue;
        if (!prac.set[PS_DLIFE]) {                           /* infinite: never dies (the Chain Lab's dummy) */
            if (d->state == S_IDLE || d->state == S_WALK) d->hp = LIFE;
            else if (d->hp < 20) d->hp += 40;
            if (d->state == S_DEAD) { fighter_revive(d); d->inv = 0; }
        } else if (d->state == S_DEAD && d->state_t > DEATH_BLINK + 30) prac_dummy(k);   /* beaten: back at its mark */
        if (d->x < FIX(cam_x + 24)) d->x = FIX(cam_x + 24);   /* on screen: the camera does not follow it */
        if (d->x > FIX(cam_x + 296)) d->x = FIX(cam_x + 296);
    }
    for (k = LAB_DUMMY; k < NF; k++) {                       /* a combo ends once every enemy has recovered */
        uint8_t s = fighters[k].state;
        if (s == S_HITSTUN || s == S_KNOCKDOWN || s == S_DOWN || s == S_GETUP || s == S_GRABBED || s == S_THROWN) rec = 0;
    }
    if (rec) lab_recovered = 1;
    if (prac.set[PS_WAVES]) {                                /* the waves: the next one when the last is beaten */
        uint8_t alive = 0;
        for (k = LAB_DUMMY + pm_nd; k < NF; k++) {
            fighter_t *e = &fighters[k];
            if (e->state == S_DEAD && e->state_t > DEATH_BLINK) e->state = S_OFF;   /* blinked out */
            if (e->state != S_OFF) alive++;
        }
        if (alive) pw_t = 0; else if (++pw_t >= 60) { pw_t = 0; prac_wave(); }
    } else if (pm_waves) for (k = LAB_DUMMY + pm_nd; k < NF; k++) fighters[k].state = S_OFF;
    pm_waves = prac.set[PS_WAVES];
    dbg_on = prac.set[PS_BOXES];
    if (in_play(p) && (JOY_pressed(0) & JOY_START)) pm_open();
    bios_start = 0;
}
static void prac_boot(void) {                                /* power-on / a BIOS hand-over: the practice at once */
    prac_check();
#ifdef LAB_SHELL                                             /* the Character Lab's shell / a pack: P1 = the slot fighter (the
                                                                last roster index, the swapped-in pack's; Makefile LAB_SHELL) */
    lab.fighter = BC_COUNT - 1;
#else
    lab.fighter = bm_lab.fighter < BC_COUNT ? bm_lab.fighter : prac.fighter;
#endif
    lab.dummy = prac.dummy;
    pm_nd = pm_mode = 0xFF;
    lab_start(1);
}
#endif
static void lab_place(void) {
    fighter_t *p = &fighters[0], *d = &fighters[LAB_DUMMY];
    fighter_init(p, p->ch, p->set, 16, 0, cam_x + 110, 34); p->idx = 0;
#if LAB_BUILD
    (void)d; prac_dummies();                                  /* practice: every dummy at its mark */
#else
    fighter_init(d, d->ch, d->set, 16 + LAB_DUMMY * MAX_PALS, 1, cam_x + 190, 34); d->idx = LAB_DUMMY;
#endif
    for (uint8_t i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    lab_recovered = 1;
}
/* the enemy test (req 3): the enemy definition lab.dummy (genemies[], a pool enemy as its first fighter) with its own
 * AI, at the dummy's place; dead, it comes again (a safe point: a pack sent meanwhile is installed first) */
static void lab_enemy(void) {
    const genemy_t *en;
    uint8_t c;
    if (gd_want) gd_apply();
    en = &genemies[lab.dummy < gen_count ? lab.dummy : 0];
    c = en->base != 0xFF ? en->base : en->pool[0];
    enemy_init(LAB_DUMMY, c, c == pl_ch[0], cam_x + 190, 34, 0, en);
    ai_init(0x1D2B, en->ai);
    ai_boss(LAB_DUMMY, boss_ai_of(en));                     /* (a boss: its own layer, T9) */
    fighters[0].target = &fighters[LAB_DUMMY];              /* the HUD shows it from the start */
}
static void lab_start(uint8_t kind) {
    uint8_t i, c = lab.fighter < BC_COUNT ? lab.fighter : 0, dm = lab.dummy < BC_COUNT ? lab.dummy : 1;
    attract = 0; opt_on = 0; banner_hide(); BIOS_USER_MODE = 2;
    bonus_off(); fury_lock = 0;                               /* the Lab: never a bonus's lock */
    pl_ch[0] = c; pl_set[0] = 0; pl_on[0] = 1; pl_on[1] = 0;
    no_intro = 1; stage_begin(0, 1); no_intro = 0;           /* (the Lab: no stage intro) */
    for (i = 1; i < NF; i++) fighters[i].state = S_OFF;
#if LAB_BUILD
    ai_skip = 0; pm_nd = pm_mode = 0xFF;                      /* (the enemy test: its AI; the practice: prac_dummies) */
#endif
    lab.active = kind;
    if (kind == 2) { fighter_t *p = &fighters[0]; fighter_init(p, p->ch, p->set, 16, 0, cam_x + 110, 34); p->idx = 0; lab_enemy(); }
    else {
#if LAB_BUILD
        lab.dummy = dm;                                       /* practice: prac_dummies' fighter */
#else
        enemy_init(LAB_DUMMY, dm, dm == c, 0, 34, 0, &genemies_rom[EN_MINION]);   /* life and power of a minion */
#endif
        lab_place();
    }
    lab.frame = 0; lab.nev = 0; lab_seen = 0; lab.combo_hits = 0; lab.combo_dmg = 0;
    lab_shown_hits = 0xFF; lab_shown_dmg = 0xFFFF;
#if LAB_BUILD
    FIX_print(0, 26, "                                        ", 0); FIX_print(2, 26, kind == 2 ? "ENEMY TEST" : "PRACTICE", 0);
    pm_on = 0; prac.menu = 0;                                 /* (stage_begin cleared the fix layer: the menu's box too) */
#else
    FIX_print(0, 26, "                                        ", 0); FIX_print(2, 26, kind == 2 ? "ENEMY TEST" : "CHAIN LAB", 0);
#endif
}
/* req 4 (the Brawler Lab's Stages tab, "play from here"): P1 alone (lab.fighter) in campaign stage lab.dummy as a new
 * game, the camera at wave lab.wave's lock point and that wave spawned (or the boss, past the last wave); a pack sent
 * with it is installed first (stage_begin is a safe point). From there the game is the normal campaign. */
static void lab_stage(void) {
    uint8_t w = lab.wave, i;
    attract = 0; opt_on = 0; banner_hide(); BIOS_USER_MODE = 2; lab.active = 0;
    bonus_off(); fury_lock = 0; bn_won = 0; bn_clr[0] = bn_clr[1] = bn_clr[2] = 0;                   /* (the fury free, as before the bonus stages: a recipe
                                                                 that tests it starts here; req 6 is the bonus's own) */
    pl_ch[0] = lab.fighter < BC_COUNT ? lab.fighter : 0; pl_set[0] = 0; pl_on[0] = 1; pl_on[1] = 0;
    no_intro = 1; stage_begin(lab.dummy < GS_COUNT ? lab.dummy : 0, 1); no_intro = 0;
#if LAB_BUILD
    ai_skip = 0; pm_on = 0; prac.menu = 0;                    /* the campaign's enemies: every one its AI */
#endif
    if (!w) return;
    if (w > gs->nwaves) w = gs->nwaves;
    wave = w; waves_cleared = w; cam_x = lock_x = lock_at(w < gs->nwaves ? gs->waves[w].lock : gs->boss_lock);
    fighters[0].x = FIX(cam_x + 60);
    if (w < gs->nwaves) spawn_wave();
    else { for (i = 2; i < NF; i++) fighters[i].state = S_OFF; boss_start(); }
}
/* req 6 (scenario.py mode "bonus", the bonus proofs): P1 alone (lab.fighter), a new game as from the select screen
 * (the fury locked when game.json bonus.fury_lock; lab.wave bit 7: unlocked, as after the posts), then the bonus after
 * stage lab.dummy + 1: its pick screen (lab.wave & 0x7F = 0) or game k straight away (k + 1) */
static void lab_bonus(void) {
    uint8_t w = lab.wave;
    attract = 0; opt_on = 0; banner_hide(); BIOS_USER_MODE = 2; lab.active = 0;
    pl_ch[0] = lab.fighter < BC_COUNT ? lab.fighter : 0; pl_set[0] = 0; pl_on[0] = 1; pl_on[1] = 0;
    no_intro = 1; fight_start_at(lab.dummy + 1 < GS_COUNT ? lab.dummy : 0); no_intro = 0;
    if (w & 0x80) fury_lock = 0;
    bonus_start();
    if ((w & 0x7F) && (w & 0x7F) <= gbonus.ngames) bonus_play((w & 0x7F) - 1);
}
static void lab_flow(void) {
    fighter_t *p = &fighters[0], *d = &fighters[LAB_DUMMY];
#if LAB_BUILD
    if (lab.active == 1) prac_flow(p);                        /* the practice: P1's holds, the dummies, the waves, START */
    else
#endif
    if (!lab.p1_life) p->hp = LIFE;                           /* nobody hits P1 (lab.p1_life: its life left alone, the
                                                                 meter proofs); a dummy never dies */
    if (lab.active == 2) {                                    /* the enemy test: it fights; beaten, it comes again */
        if (d->state == S_DEAD && d->state_t > 60) lab_enemy();
        if (in_play(p) && (JOY_pressed(0) & JOY_START)) dbg_on ^= 1;
        bios_start = 0;
        return;
    }
#if !LAB_BUILD                                                /* (the practice: prac_flow, prac_input) */
    if (d->state == S_IDLE || d->state == S_WALK) { d->hp = LIFE; lab_recovered = 1; }
    else if (d->hp < 20) d->hp += 40;
    if (d->state == S_DEAD) { fighter_revive(d); d->inv = 0; }
    if (d->x < FIX(cam_x + 24)) d->x = FIX(cam_x + 24);       /* on screen: the camera does not follow it */
    if (d->x > FIX(cam_x + 296)) d->x = FIX(cam_x + 296);
    in[LAB_DUMMY] = (intent_t){ 0 };
    in[LAB_DUMMY].face = INT(p->x) < INT(d->x) ? -1 : 1;      /* standing: it turns to face P1 */
#endif
    while (lab_seen != lab.nev) {                             /* P1's hits since the last frame */
        const lab_ev_t *e = &lab.ev[lab_seen & (LAB_NEV - 1)];
        if (e->kind == LE_HIT) {
            if (lab_recovered) { lab.combo_hits = 0; lab.combo_dmg = 0; lab_recovered = 0; }
            lab.combo_hits++; lab.combo_dmg += e->val;
        }
        lab_seen++;
    }
    if (lab.combo_hits != lab_shown_hits || lab.combo_dmg != lab_shown_dmg) {
        lab_shown_hits = lab.combo_hits; lab_shown_dmg = lab.combo_dmg;
        FIX_print(13, 26, "HITS    DAMAGE    ", 0); FIX_printNum(18, 26, lab.combo_hits, 0); FIX_printNum(28, 26, lab.combo_dmg, 0);
    }
#if !LAB_BUILD                                                /* (the practice: START opens its menu, prac_flow) */
    if (in_play(p) && (JOY_pressed(0) & JOY_START)) dbg_on ^= 1;   /* the box viewer, as in a fight */
#endif
    bios_start = 0;
}
static void lab_tick(void) {                                  /* the page's requests, before the frame's game logic */
    if (lab.magic[0] != 'L' || lab.magic[1] != 'A' || lab.magic[2] != 'B' || lab.magic[3] != '1') return;
    if (lab.load == 3 || lab.load == 4) {                   /* a data pack (3) or the ROM's tables (4): at the safe point (5: lab_install) */
        uint8_t e = lab.load == 3 ? gd_check(lab.pack) : 0;
        lab.pack_stat = e ? GD_BAD | e : GD_PENDING; gd_want = e ? 0 : lab.load; lab.load = 0;
    }
    lab_install();
    if (lab.active) lab.frame++;                              /* this tick's events carry this frame */
    if (lab.req == 1 || lab.req == 3) lab_start(lab.req == 3 ? 2 : 1);
    else if (lab.req == 4) lab_stage();
    else if (lab.req == 5) snd_music(lab.dummy);
    else if (lab.req == 6) lab_bonus();
    else if (lab.req == 2 && lab.active == 2) { fighter_t *p = &fighters[0]; fighter_init(p, p->ch, p->set, 16, 0, cam_x + 110, 34); p->idx = 0; lab_enemy(); }
    else if (lab.req == 2 && lab.active) lab_place();
    lab.req = 0;
}

/* ---- BOSS UNLOCKED (a boss beaten for the first time) and the ending: the fighter alone in its win pose on a dark
 * wall, its portrait and name on the fix layer; A/B/C/D/START (after a moment) or the time goes on. ---- */
static uint16_t scr_t;
static void show_start(uint8_t m, uint8_t c, uint8_t set, uint16_t wall) {
    uint8_t i;
    mode = m; scr_t = 0; nf = NE; cam_x = 0;
    FIX_clear(); arcade_line_reset(); bt_hide();
    stage_hide();
    floor_top = SELECT_FLOOR;
    bd_set(wall);
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    fighter_init(&fighters[0], &bm_chars[c], set, 16, 0, 160, SHOW_Z);
    fighters[0].idx = 0; fighters[0].facing = 1;
    fighter_play(&fighters[0], BA_WIN);
    for (i = 0; i < NF; i++) order[i] = &fighters[i];
    for (i = 0; i < NPJ; i++) order[NF + i] = &projectiles[i];
}
static void centre(uint8_t row, const char *t) { uint8_t n = 0; while (t[n]) n++; FIX_print(20 - (n >> 1), row, t, 0); }
static void unlock_start(uint8_t k) {
    uint8_t c = boss_fighter(k);
    show_start(3, c, 0, RGB8(40, 8, 8));
    centre(3, "BOSS UNLOCKED");
    portrait(18, 5, c, 0);
    centre(10, bm_chars[c].name);
    centre(24, "NOW ON THE SELECT SCREEN");
    snd_music(GAME_MUS_SELECT);
    snd_ssg(SSG_UNLOCK);                                     /* the fanfare blip over the music (SSG) */
}
/* ---- the ending (game.json "ending"; Bruno 2026-10-11, decisions open-2026-10-11 card ending-music): after the last
 * stage's boss and the win poses, mode 4 plays three screens, each a cut, each passed with START / A-D after its `min`
 * ticks or by itself:
 *   EN_STORY  the winner (P1, or P2 when P1 is out) on black: his big portrait sliding in on the right (drama mode's,
 *             portraits_big.h; a fighter without one: his win pose + his HUD face), under it a box (fix rows
 *             EN_BOX0-27) with his name and his story (gend_story: 4-5 sentences wrapped to END_COLS) typed a character
 *             every END_STORY_TYPE ticks, scrolling up a row when its EN_ROWS rows are full; KOF95's team ending
 *   EN_STAFF  the staff roll on black, scrolling up a pixel at a time (a line = 8 px every END_STAFF_STEP ticks) until
 *             its last line reaches the middle row (13), then END_STAFF_HOLD ticks; KOF95's staff roll. Sprites, not the
 *             fix layer (it moves in 8 px rows only; Bruno 2026-10-11, note 20261006-173249-5d29: "pixel-by-pixel"):
 *             staff_roll.h (tools/brawler/staff_roll.py: game.json's lines in the S ROM font, the fix roll's layout)
 *   EN_THANKS the winner in his win pose, THANK YOU FOR PLAYING; the staff roll's song fades out ($0A + END_THANKS_FADE)
 * then BOSS UNLOCKED when this boss was beaten for the first time (unlock_k), then back to the BIOS (title / demo). ---- */
enum { EN_STORY, EN_STAFF, EN_THANKS };
#define EN_BOX0  19                              /* the story box: fix rows 19-27, opaque */
#define EN_TXT0  21                              /* its text rows 21 .. 21 + EN_ROWS - 1 (row 20: the name) */
#define EN_ROWS  5
#define EN_COL0  3                               /* the text's first column (END_COLS wide) */
#define EN_FEET  148                             /* a fighter shown on the story / thanks screen: his feet's screen y */
static uint8_t en_st, en_w, en_line, en_col;    /* the screen; the winner (bm_chars index); the story's line + column typed
                                                    (the staff roll: en_col 1 = rolled away, the thanks screen next tick) */
static uint16_t en_t, en_px, en_hold;            /* ticks on this screen; the staff roll's pixels scrolled; ticks since
                                                    the story typed / the roll stopped */
static uint16_t en_sub;                          /* ticks to the next character typed; the roll's sub-pixel (8 a tick,
                                                    a pixel per END_STAFF_STEP) */
static void en_row(uint8_t row, const char *t, uint8_t col0) {   /* a box row: blank cells, then t from col0 */
    uint8_t c, pal = 0;
    if (t && *t == '^') { t++; pal = 1; }       /* a heading: highlighted */
    for (c = 0; c < 40; c++) fix_put(c, row, DRAMA_FONT + ' ');
    if (t) for (c = 0; t[c]; c++) dr_put(col0 + c, row, t[c], pal);
}
static void en_winner_pose(uint8_t m) {          /* the winner alone in his win pose on black, feet at EN_FEET */
    show_start(m, en_w, pl_set[pl_on[0] || !pl_on[1] ? 0 : 1], RGB8(0, 0, 0));
    floor_top = EN_FEET - SHOW_Z;
}
static void ending_start(void) {
    uint8_t i, pb, r;
    const char *name;
    en_w = pl_on[0] || !pl_on[1] ? pl_ch[0] : pl_ch[1];
    en_winner_pose(4);
    en_st = EN_STORY; en_t = en_hold = 0; en_sub = 0; en_line = en_col = 0;
    for (i = 0; i < DBG_BOXES * 8; i++) cmd_push(VRAM_SCB3 + DBG_SPR + i, 0);   /* (the box viewer's sprites = PB_SPR's) */
    dbg_shown = 0; dr_cols = 0;
    pb = pb_of_fighter[en_w];
    if (pb < PB_COUNT) { fighters[0].state = S_OFF; pb_show(pb, 1); }   /* the big portrait, sliding in on the right */
    else portrait(4, 4, en_w, 0);                                        /* none: the win pose + the HUD face */
    for (r = EN_BOX0; r < 28; r++) en_row(r, 0, 0);
    name = bm_chars[en_w].name;
    for (i = 0; name[i] && i < 16; i++) dr_put(EN_COL0 + i, EN_TXT0 - 1, name[i], 1);   /* the name plate, highlighted */
    snd_music(GAME_MUS_ENDING);
}
/* the roll's sprites: SR_COLS columns side by side from x 0 (a sticky chain), SR_H tiles each, showing the roll's tile
 * rows sr_top ..; line k (8 px) at screen y 216 + 8 k - en_px (en_px 0: line 0 on fix row 27, as the fix roll began).
 * The big portrait's sprites (hidden during the roll) and the banner's palette (never on in the ending; banner_show
 * loads its own again): pens 1-5 / 14 = fix palette 0's, 6-9 = fix palette 1's highlighted gradient (headings). All
 * through the VRAM queue: the new Y and the new tile rows go out in the same vblank (no tearing). */
#define SR_SPR PB_SPR
#define SR_PAL BN_PAL
#define SR_H   15                                /* 224 px + up to 15 px of a tile row above the screen */
_Static_assert(SR_COLS == 20 && SR_COLS <= PB_MAXCOLS, "the staff roll: the big portrait's sprites; staff_place's row * 20");
static int16_t sr_top;
static void staff_place(void) {
    int16_t y = 216 - (int16_t)en_px, t = (int16_t)(-y) >> 4;   /* the roll's top on screen; the first tile row shown */
    uint8_t c, r;
    if (t != sr_top) {                           /* a new tile row: the columns' tiles */
        sr_top = t;
        for (c = 0; c < SR_COLS; c++) {
            uint16_t *w = cmd_run(VRAM_SCB1 + (SR_SPR + c) * 64, SR_H * 2);
            const uint16_t *m = sr_map + c + (t << 4) + (t << 2);   /* row t (* SR_COLS) */
            for (r = 0; r < SR_H; r++, m += SR_COLS) {
                uint32_t k = t + r >= 0 && t + r < SR_ROWS && *m ? SR_TILE0 + *m : 0;
                *w++ = (uint16_t)k;
                *w++ = k ? (uint16_t)(SR_PAL << 8) | ((uint16_t)(k >> 12) & 0xF0) : 0;
            }
        }
    }
    cmd_push(VRAM_SCB3 + SR_SPR, (uint16_t)(((496 - y - (t << 4)) & 0x1FF) << 7) | SR_H);
}
static void staff_show(uint8_t on) {             /* on: palette, full size, the chain at x 0; off: hidden */
    uint8_t c;
    if (on) {
        uint16_t pal[16];
        for (c = 0; c < 16; c++) pal[c] = TEXT_PAL[c];
        for (c = 0; c < 4; c++) pal[6 + c] = hilite_colours[c];
        PAL_setPalette(SR_PAL, pal);
        for (c = 0; c < SR_COLS; c++) cmd_push(VRAM_SCB2 + SR_SPR + c, 0x0FFF);
        cmd_push(VRAM_SCB4 + SR_SPR, 0);
        sr_top = 0x7FFF;
        staff_place();
    }
    for (c = 1; c < SR_COLS; c++) cmd_push(VRAM_SCB3 + SR_SPR + c, on ? 0x40 : 0);   /* sticky: the master's Y */
    if (!on) cmd_push(VRAM_SCB3 + SR_SPR, 0);
}
static void staff_start(void) {
    pb_hide();
    fighters[0].state = S_OFF;
    FIX_clear();
    bd_set(RGB8(0, 0, 0));
    en_st = EN_STAFF; en_t = en_hold = 0; en_sub = 0; en_px = 0; en_col = 0;
    staff_show(1);
    snd_music(GAME_MUS_STAFF);
}
static void thanks_start(void) {
    uint8_t k;
    en_winner_pose(4);
    en_st = EN_THANKS; en_t = 0;
    for (k = 0; k < END_THANKS_N; k++) centre(21 + 2 * k, gend_thanks[k]);   /* under his feet (EN_FEET) */
    if (END_THANKS_FADE) { snd_cmd(0x0A); snd_cmd(END_THANKS_FADE); }   /* the staff roll's song fades out */
}
static void ending_tick(void) {
    uint16_t pr = JOY_pressed(0) | JOY_pressed(1);
    uint8_t skip = (pr & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)) != 0, r;
    const char *const *s = gend_story[en_w], *t;
    en_t++;
    switch (en_st) {
    case EN_STORY:
        if (dr_slide) { dr_slide--; pb_place(dr_slide * 10); }
        else if (fighters[0].state != S_OFF) fighter_animate(&fighters[0]);
        if ((skip && en_t >= END_STORY_MIN) || (!s[en_line] && ++en_hold >= END_STORY_HOLD)) { staff_start(); break; }
        if (!s[en_line] || ++en_sub < END_STORY_TYPE) break;
        en_sub = 0; t = s[en_line];
        if (!t[en_col]) {                            /* the line typed: the next one, on the next row or the box scrolled */
            en_line++; en_col = 0;
            if (en_line >= EN_ROWS && s[en_line])
                for (r = 0; r < EN_ROWS; r++) en_row(EN_TXT0 + r, r + 1 < EN_ROWS ? s[en_line - EN_ROWS + 1 + r] : 0, EN_COL0);
            break;
        }
        dr_put(EN_COL0 + en_col, EN_TXT0 + (en_line < EN_ROWS ? en_line : EN_ROWS - 1), t[en_col], 0);
        en_col++;
        break;
    case EN_STAFF:
        if (en_col) { thanks_start(); break; }      /* the roll hidden last tick: its sprites are off this frame, the
                                                       thanks screen's fix text (written at once) never over them */
        if ((skip && en_t >= END_STAFF_MIN) || (en_px >= (END_STAFF_N - 1 + 14) * 8 && ++en_hold >= END_STAFF_HOLD)) {
            staff_show(0); en_col = 1; break;
        }
        if (en_px < (END_STAFF_N - 1 + 14) * 8) {   /* until the last line is on the middle row (13) */
            for (en_sub += 8; en_sub >= END_STAFF_STEP && en_px < (END_STAFF_N - 1 + 14) * 8; en_sub -= END_STAFF_STEP) en_px++;
            staff_place();
        }
        break;
    case EN_THANKS:
        fighter_animate(&fighters[0]);
        if (!((skip && en_t >= END_THANKS_MIN) || en_t >= END_THANKS_TIME)) break;
        if (unlock_k) unlock_start(unlock_k - 1);   /* a boss beaten for the first time: BOSS UNLOCKED, then the BIOS */
        else if (lad_new) ladder_start();            /* this clear unlocked a rung: the unlock ladder (it revealed), then
                                                        the BIOS; nothing unlocked (all unlocked already): no ladder */
        else SYS_return();                           /* back to the BIOS: it commits the MVS save, shows the title
                                                        (credits left) or the attract demo */
        break;
    }
}
static void show_tick(void) {
    uint16_t pr = JOY_pressed(0) | JOY_pressed(1);
    if (mode == 4) { ending_tick(); return; }
    scr_t++;
    fighter_animate(&fighters[0]);
    if (scr_t < (mode == 3 ? 360 : mode == 5 ? 480 : 600) && !(scr_t >= 90 && (pr & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)))) return;
    if (mode == 3 && camp + 1 >= GS_COUNT && lad_new) ladder_start();   /* the last stage's BOSS UNLOCKED: then the
                                                                ladder when this clear unlocked a rung */
    else if (mode >= 4 || camp + 1 >= GS_COUNT) SYS_return();   /* GAME OVER, the last stage's BOSS UNLOCKED (after the
                                                                ending): back to the BIOS, which commits the MVS save and
                                                                shows the title (credits left) or the attract demo */
    else stage_next();
}
/* ---- the unlock ladder (Bruno 2026-10-15, decisions set unlocks: the beta build): game.json unlocks = the starters, then
 * the ladder's fighters in order, a rung each (lad_rung: each rung its own size); each game clear (the last stage's boss beaten, PH_END) unlocks the next
 * rung (save.rungs, kept in the save: MVS backup RAM, AES memory card) and the select screen shows only these fighters
 * (only the unlocked ones are drawn there: select_layers). This screen shows them all at once on ONE line (Bruno
 * 2026-10-15: "every character on the same horizontal axis"; build_tables.py ladder_places: lad_pos, feet on one y, in
 * ladder order left to right at a fixed pitch: game.json unlocks.screen.pitch), each in its select pose at full size
 * (Bruno 2026-10-15, the select screen's idea: "make them spaced enough, from left to right; if the characters are too
 * far to the right, just scroll": a row wider than the TV pans the camera, 0 .. LAD_CAM_MAX, over the plain backdrop
 * to the rung just unlocked, lad_camera), unlocked in colour,
 * locked as a dark silhouette (SILHOUETTE / SILHOUETTE_B every other one: LAD_SIL), so the player sees what comes next. After a game clear (the ending's last
 * screen): the rung just unlocked starts as silhouettes, then LAD_FLASH ticks of white / silhouette flashes, its
 * fighters in colour playing their win pose with their select voice, NEW CHALLENGERS! (big_text.ladder) and their names;
 * A-D / START after LAD_MIN ticks or LAD_TIME: back to the BIOS (SYSTEM_RETURN commits the MVS save). Shown ONLY after a
 * game clear that unlocked a rung (Bruno 2026-10-15: "only show this at the end of the game when there is an unlocking";
 * no title entry since then; all unlocked: the clear hands back to the BIOS without it). The actors are the
 * select screen's (NA blocks of SEL_COLS from SEL_SPR; palettes: each fighter's select slot's, sel_palbase). ---- */
#define LAD_REVEAL 60                            /* ticks before the new rung's flash */
#define LAD_FLASH  24                            /* its white / silhouette flashes, 4 ticks each */
#define LAD_MIN    240                           /* after a game clear: a button passes it from here */
#define LAD_TIME   720                           /* ... or by itself */
#define LAD_SIL(i) ((i) & 1 ? 4 : 2)              /* a locked one's silhouette: two tones, every other one lighter (they overlap) */
static uint16_t lad_t;
static void lad_info(void) {                     /* the line under the front row's feet: the progress, what unlocks more */
    uint8_t i, n = 0, row = 26, c, m = 0;
    for (i = 0; i < LAD_N; i++) { if (lad_rung[i] <= save.rungs) n++; if (lad_rung[i] == save.rungs + 1) m++; }   /* m: the
                                                             next rung's size (rungs have their own sizes: the beta's last
                                                             is Haggar alone) */
    FIX_print(0, row, "                                        ", 0);
    if (save.rungs >= LAD_RUNGS) { FIX_print(10, row, "ALL", 0); FIX_printNum(14, row, LAD_N, 0); FIX_print(LAD_N >= 10 ? 17 : 16, row, "FIGHTERS UNLOCKED", 0); return; }
    c = 3;                                       /* "n/N - BEAT THE GAME FOR m MORE" (columns 3-35: the TV shows 1-38) */
    FIX_printNum(c, row, n, 0); c += n >= 10 ? 2 : 1;
    FIX_print(c++, row, "/", 0); FIX_printNum(c, row, LAD_N, 0); c += LAD_N >= 10 ? 3 : 2;
    FIX_print(c, row, "- BEAT THE GAME FOR", 0); FIX_printNum(c + 20, row, m, 0); FIX_print(c + 22, row, "MORE", 0);
}
static void lad_names(uint8_t rung) {            /* the new rung's names, side by side under the headline */
    char t[41];
    uint8_t i, k = 0, j;
    for (i = 0; i < LAD_N && k < 38; i++) {
        const char *n = bm_chars[lad_fighter[i]].name;
        if (lad_rung[i] != rung) continue;
        if (k) { t[k++] = ' '; t[k++] = ' '; }
        for (j = 0; n[j] && k < 40; j++) t[k++] = n[j];
    }
    t[k] = 0;
    centre(8, t);
}
static int16_t lad_goal;                         /* the camera's goal: the new rung's fighters centred (0: none new) */
static void lad_camera(void) {                   /* eased toward lad_goal (the select's sel_camera feel) */
    int16_t d = lad_goal - cam_x, st = d >> 3;
    if (!st && d) st = d > 0 ? 1 : -1;
    cam_x += st;
}
static void ladder_start(void) {
    uint8_t i;
    mode = MODE_LADDER; lad_t = 0; cam_x = 0; attract = 0;
    FIX_clear(); arcade_line_reset(); bt_hide(); pb_hide();
    stage_hide();
    floor_top = SELECT_FLOOR;
    bd_set(RGB8(8, 8, 32));
    snd_music(GAME_MUS_SELECT);
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    for (i = 0; i < NA; i++) { actor(i)->state = S_OFF; actor(i)->idx = i; order[i] = actor(i); sel_rank[i] = 0xFF; }   /* (the unused ones
                                                             drawn last: the fighters' blocks from SEL_SPR, clear of the big text's; idx = i: a stale idx
                                                             from the select ranked an unused one among them, the fighters
                                                             then sat in blocks past the shrunk ones) */
    for (i = 0; i < LAD_N; i++) {
        fighter_t *f = actor(i);
        fighter_init(f, &bm_chars[lad_fighter[i]], 0, sel_palbase[lad_slot[i]], 1, lad_pos[i].x, lad_pos[i].y - SELECT_FLOOR);
        f->idx = i; f->facing = lad_pos[i].face; sel_rank[i] = lad_pos[i].z;
        fighter_play(f, BA_WATCH);
        fighter_pals(f, lad_rung[i] > save.rungs || (lad_new && lad_rung[i] == lad_new) ? LAD_SIL(i) : 1);
    }
    nf = NA;
    {   int16_t lo = 0x7FFF, hi = -0x7FFF;           /* the new rung's feet x: the camera pans to centre them */
        for (i = 0; i < LAD_N; i++) if (lad_new && lad_rung[i] == lad_new) { if (lad_pos[i].x < lo) lo = lad_pos[i].x; if (lad_pos[i].x > hi) hi = lad_pos[i].x; }
        lad_goal = lo <= hi ? ((lo + hi) >> 1) - 160 : 0;
        if (lad_goal < 0) lad_goal = 0;
        if (lad_goal > LAD_CAM_MAX) lad_goal = LAD_CAM_MAX; }
    FIX_print(14, 2, "GAME CLEAR!", 1);
    lad_info();
}
static void lad_hide(void) {                     /* the hand-back: the actors' sprites off */
    uint16_t i, *y = cmd_run(VRAM_SCB3 + SEL_SPR, BLK_END - SEL_SPR);
    for (i = 0; i < BLK_END - SEL_SPR; i++) y[i] = 0;
    for (i = 0; i < NA; i++) { actor(i)->state = S_OFF; block_placed[i] = 0; }
    blk_key_reset();
    nf = 0;
}
static void ladder_tick(void) {
    uint16_t pr = JOY_pressed(0) | JOY_pressed(1);
    uint8_t i, btn = (pr & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)) != 0;
    lad_t++;
    bios_start = 0;
    if (lad_t >= 20) lad_camera();               /* a beat on the start, then the pan (done before the flash) */
    if (lad_new && lad_t >= LAD_REVEAL && lad_t <= LAD_REVEAL + LAD_FLASH && !((lad_t - LAD_REVEAL) & 3)) {
        uint8_t k = (uint8_t)((lad_t - LAD_REVEAL) >> 2), look = k == LAD_FLASH / 4 ? 1 : (k & 1) ? 2 : 3;   /* white,
                                                             silhouette, ... then the colours */
        for (i = 0; i < LAD_N; i++) {
            if (lad_rung[i] != lad_new) continue;
            fighter_pals(actor(i), look == 2 ? LAD_SIL(i) : look);
            if (look == 1) { fighter_play(actor(i), BA_WIN); voice_play(actor(i)->ch, 0, VK_SELECT); }
        }
        if (!k) snd_ssg(SSG_UNLOCK);
        if (look == 1) {
            FIX_print(0, 2, "                                        ", 0);
            if (gbig[BIG_LADDER].on) bt_show(0, BIG_LADDER); else centre(4, "NEW CHALLENGERS!");
            lad_names(lad_new);
        }
    }
    for (i = 0; i < LAD_N; i++) if (actor(i)->state != S_OFF) fighter_animate(actor(i));
    if ((lad_t >= LAD_MIN && btn) || lad_t >= LAD_TIME) { bt_hide(); lad_hide(); SYS_return(); }   /* back to the BIOS: it commits the
                                                             MVS save, shows the title (credits left) or the attract demo */
}
/* the select's time limit (note 20261016-174702-e03d; game.json select.time_limit_s): on an arcade (MVS) after
 * GAME_SEL_TIME_TICKS of the choice (sel_t) every joined player who has not picked takes the fighter under his cursor in
 * colour set A (sel_pick, as the button); on the other's pick: the first other selectable fighter. Hidden for now (no
 * timer font: select.time_limit_shown). Console (AES): none (select.time_limit_mvs_only). */
static uint8_t sel_time_on(void) {
    return GAME_SEL_TIME_TICKS && (BIOS_MVS_FLAG || !GAME_SEL_TIME_MVS_ONLY) && !lab.active;
}
static void sel_pick(uint8_t p, uint8_t set) {           /* player p takes his cursor's fighter in colour set `set` */
    pick_set[p] = set;
    slot_show(cursor[p], pick_set[p]);
    fighter_play(actor(slot_act[cursor[p]]), BA_WIN);
    voice_play(actor(slot_act[cursor[p]])->ch, 0, VK_SELECT);   /* its select voice (KOF's intro line) */
    actor(slot_act[cursor[p]])->team = 0;               /* the line guard keeps the picked ones first */
    picked[p] = 1; snd_ssg(SSG_CONFIRM);
}
static void select_tick(void) {
    uint8_t a, p, s;
    sel_t++;
    if (sel_phase == SEL_CHOOSE) {
        if (LAD_N && (save.rungs < LAD_RUNGS || !(save.cheat & 1))) {   /* the cheat: down held 2 s, up held 2 s */
            uint16_t h = JOY_held(0) | JOY_held(1);
            uint8_t d = (h & JOY_DIR_MASK) == JOY_DOWN ? 0 : (h & JOY_DIR_MASK) == JOY_UP ? 1 : 2;
            if (d < 2) { if (++cheat_t[d] == CHEAT_HOLD) cheat_flags |= 1 << d; cheat_t[d ^ 1] = 0; }
            else cheat_t[0] = cheat_t[1] = 0;
            if (cheat_flags == 3) {                          /* the whole ladder, saved */
                cheat_flags = 0; cheat_t[0] = cheat_t[1] = 0;
                save.rungs = LAD_RUNGS; save.cheat |= 1; save_write();
                snd_ssg(SSG_CONFIRM); select_start(); return;
            }
        }
        if ((bios_start & 2) && cursor[1] == 0xFF) {         /* P2 joins: START with a credit (PLAYER_START) */
            uint8_t t = cursor[0];                           /* the selectable fighter nearest P1's along the street */
            uint16_t best = 0xFFFF, d;
            for (s = 0; s < SEL_NSLOT; s++) {
                if (!selectable(s) || s == cursor[0]) continue;
                d = SEL_SLOT[sel_base + s].x > SEL_SLOT[sel_base + cursor[0]].x ? SEL_SLOT[sel_base + s].x - SEL_SLOT[sel_base + cursor[0]].x : SEL_SLOT[sel_base + cursor[0]].x - SEL_SLOT[sel_base + s].x;
                if (d < best) { best = d; t = s; }
            }
            cursor[1] = t; sel_last = 1;                     /* (none: both on P1's fighter) */
            BIOS_PLAYER_MOD[1] = 1;
            fighter_pals(actor(slot_act[cursor[1]]), 1);
            select_name();
        }
        bios_start = 0;
        for (p = 0; p < 2; p++) {
            uint16_t pr = JOY_pressed(p);
            uint8_t was = cursor[p];
            if (was == 0xFF || picked[p]) continue;
            s = sel_move(was, pr);
            if (s != was) {                                  /* colours follow the cursor */
                cursor[p] = s; sel_last = p; snd_ssg(SSG_CURSOR);
                fighter_pals(actor(slot_act[was]), slot_look(was));
                fighter_pals(actor(slot_act[s]), 1);
                select_name();
            }
            if ((pr & (JOY_A | JOY_B | JOY_C | JOY_D)) && !(picked[p ^ 1] && cursor[p ^ 1] == cursor[p]))
                sel_pick(p, (pr & JOY_A) ? 0 : (pr & JOY_B) ? 1 : (pr & JOY_C) ? 2 : 3);
        }
        if (sel_time_on() && sel_t >= GAME_SEL_TIME_TICKS)  /* the time limit: the highlighted fighters, colour set A */
            for (p = 0; p < 2; p++) {
                if (cursor[p] == 0xFF || picked[p]) continue;
                if (picked[p ^ 1] && cursor[p ^ 1] == cursor[p]) {   /* on the other's pick: the first other selectable one */
                    uint8_t was = cursor[p];
                    for (s = 0; s < SEL_NSLOT && (!selectable(s) || s == cursor[p ^ 1]); s++) ;
                    if (s == SEL_NSLOT) continue;
                    cursor[p] = s; fighter_pals(actor(slot_act[was]), slot_look(was)); fighter_pals(actor(slot_act[s]), 1);
                    select_name();
                }
                sel_pick(p, 0);
            }
        if (picked[0] && (cursor[1] == 0xFF || picked[1])) { sel_phase = SEL_LEAVE; sel_t = 0; }
    } else if (sel_phase == SEL_LEAVE) {                     /* the others walk off the screen, outward */
        uint8_t left = 0;
        for (s = 0; s < SEL_NSLOT; s++) {
            fighter_t *f;
            int16_t sx;
            if (slot_act[s] == 0xFF || chosen(s)) continue;
            f = actor(slot_act[s]);
            if (f->state == S_OFF) continue;
            if (sel_t == 1) { f->facing = SEL_SLOT[sel_base + s].x - cam_x < 160 ? -1 : 1; fighter_play(f, BA_WALK_FWD); }
            f->x += f->facing > 0 ? FIX(3) : -FIX(3);
            sx = INT(f->x) - cam_x;
            if (sx < -64 || sx > 384) f->state = S_OFF; else left++;
        }
        if (!left && sel_t >= 60) {                          /* then the fight: a cut (no fades) */
            for (p = 0; p < 2; p++) {
                pl_on[p] = cursor[p] != 0xFF;
                if (!pl_on[p]) continue;
                pl_ch[p] = slot_ch[cursor[p]]; pl_set[p] = mod8(pick_set[p], bm_chars[pl_ch[p]].nsets);
            }
            for (a = NE; a < NA; a++) actor(a)->state = S_OFF;
            fight_start(); return;
        }
    }
    if (sel_phase == SEL_CHOOSE) sel_camera();
    for (a = 0; a < NA; a++) if (actor(a)->state != S_OFF) fighter_animate(actor(a));
    select_arrows();
}

void game_init(void) {
    uint16_t i;
#ifdef LAB_SHELL
    lab_slot_init();                                         /* the slot's tables (labslot.h): before anything reads them */
#endif
    BANK_init();                                             /* P2 bank 0, its copy agrees (neo_bank.h) */
    coin_in();                                               /* the credits kept from before the power-on: no sound */
    gdata_init();                                            /* the game's tables (game.json) */
    drive_chunks = gmeter.chunks;                            /* the drive bar's chunks (a bonus adds to them: fighter.c) */
    routes_init();                                           /* the fighters' chain route trees (fighter.h) */
    specs_init();                                            /* their specials by role (fighter.h spec_tab) */
    voices_init();                                           /* their voices (fighter.h voice_tab) */
    save_load();                                             /* MVS: the BIOS restored the block (a fresh one: reset) */
    for (i = 0; i < 4; i++) TEXT_PAL[2 + i] = text_colours[i];   /* the font's colours (Kizuna's, TODO #182) */
    PAL_setPalette(0, TEXT_PAL);
    bd_set(stg->backdrop);
    for (i = SEL_SPR; i < BLK_END; i++) cmd_push(VRAM_SCB2 + i, 0x0FFF);   /* full size, set once */
    for (i = 0; i < NA; i++) { block_placed[i] = blk_cols; block_spr[i] = slot_spr[i] = SPR_BASE + i * blk_cols; }   /* clear every block once */
    blk_key_reset();
    stage_init(STAGE);
    snd_cmd(0x07);                                           /* KOF98's driver: music unlock */
}

/* MVS protocol (sdk/boot/crt0.s): request 2 = attract demo, 3 = title (a coin went in) */
static void attract_start(void);
void game_enter(uint8_t request) {
    BIOS_USER_MODE = 1;                                      /* title / demo (game_init ran on request 0) */
    BANK_init();                                             /* the BIOS ran in between: the register and its copy agree */
    bt_hide();                                               /* (GAME OVER's big text: the BIOS ran in between) */
    { uint8_t k; for (k = 0; k < 10; k++) TEXT_PAL[6 + k] = bar_colours[k];
      PAL_setPalette(0, TEXT_PAL);                           /* the BIOS's own screens overwrite palette 0 */
      for (k = 0; k < 4; k++) TEXT_PAL[2 + k] = hilite_colours[k];   /* 1: highlighted text (GO, OPTIONS, drama names) */
      PAL_setPalette(1, TEXT_PAL); for (k = 0; k < 4; k++) TEXT_PAL[2 + k] = text_colours[k];
      for (k = 6; k < 16; k++) { uint16_t c = bar_colours[k - 6];                        /* 4: the meter (red <-> blue) */
          TEXT_PAL[k] = (c & 0xA0F0) | ((c >> 8) & 0xF) | ((c & 0xF) << 8) | ((c >> 2) & 0x1000) | ((c << 2) & 0x4000); }
      PAL_setPalette(METER_PAL, TEXT_PAL);
      for (k = 0; k < 10; k++) TEXT_PAL[6 + k] = bar_colours[k]; }   /* fix palettes 2-3: the shown portraits (portrait()) */
    shadow_init();
    blk_key_reset(); bg_ok = 0;                              /* (CPU budget D: the BIOS's screens wrote the sprites) */
    pj_measure();                                            /* the projectile blocks' widths (block_w) */
    dbg_init();
    snd_reset();                                             /* the BIOS reset the sound CPU before handing over */
#if LAB_BUILD
    (void)request; (void)attract_start; prac_boot();         /* a Lab build: straight into the practice */
#else
    if (request == 3) title_start(); else attract_start();
#endif
    if (coin_in()) snd_ssg(SSG_COIN);                       /* the coin that ended the demo: after the song start */
    depth_sort();
    draw();
    vblank_flush();
}

void game_tick(void) {
    uint8_t i;
    PROF_START();
    vblank_flush();                 /* we are in vblank: last tick's VRAM commands and backdrop go out now, tear-free (1 frame latency) */
    mark(P_FLUSH);
    SYS_kickWatchdog();
    snd_tick(); snd_mark();
    i = coin_in();                                           /* KOF94's coin sound (TODO #199) */
    if (attract_leave()) { if (i) snd_ssg(SSG_COIN); depth_sort(); draw(); return; }   /* the coin after the title's
                                                             song start, as game_enter's */
    if (i) snd_ssg(SSG_COIN);
    lab_tick();
#if LAB_BUILD
    if (pm_on && mode == 1 && lab.active == 1) { pm_tick(); depth_sort(); draw(); hud(); return; }   /* the practice menu: paused */
#endif
    if (!lab.active && !dr_on && mode != 4) arcade_line();   /* (the ending: its own screens, no bottom line) */
    if (sf_who && mode != 1) sf_reset();                     /* the fight left mid-flash: its sprites go */
    if (mc_who && mode != 1) mc_end();                       /* (the MAX cancel's screen: the same) */
    if (mode == 2) { title_tick(); if (mode == 2) return; }
    if (!mode) { select_tick(); depth_sort(); draw(); return; }
    if (mode == 6) { bonus_screen_tick(); if (mode == 6) { depth_sort(); draw(); return; } }   /* the bonus screens (AOF2's) */
    if (mode == MODE_LADDER) { ladder_tick(); if (mode == MODE_LADDER) { depth_sort(); draw(); } return; }
    if (mode >= 3) { show_tick(); if (mode >= 3) { depth_sort(); draw(); } return; }
    if (dr_on) { drama_tick(); depth_sort(); draw(); return; }   /* drama mode: the fight held, drawn as it stands */
    if (cont_ov) { cont_tick(); if (mode == 1) { depth_sort(); draw(); hud(); } return; }   /* CONTINUE?: the fight frozen */
    if (ko_seq && !boss_ko_tick()) { depth_sort(); draw(); hud(); return; }   /* the boss's death: slow motion (#172) */
    if (in_ph == IN_FADE) { intro_fade_tick(); depth_sort(); draw(); if (in_ph == IN_WALK) hud(); return; }   /* the stage
                                                             intro: the fade and the title, nobody on screen, no HUD */
    if (attract) {                                           /* the demo: a coin, 30 s or a game over ends it */
        if (bios_demo_end || ++attract_t > ATTRACT_DEMO) { SYS_return(); }   /* (START or a credit: attract_leave) */
        ai_bot(fighters, NF, 0, &in[0]);
        if (!(attract_t & 31)) FIX_print(14, 13, (attract_t & 32) ? "           " : "INSERT COIN", 0);
    } else read_player(0, &in[0], &fighters[0]);
    if (p2_in()) read_player(1, &in[1], &fighters[1]);
    if (in_ph == IN_WALK) intro_input();                     /* the stage intro's walk: the script's intents */
#if !AI_OFF
#if LAB_BUILD
    if (lab.active != 1 || prac_ai()) ai_update(fighters, NF, 2, in);   /* the practice: dummies with AI on, the waves */
#else
    if (lab.active != 1) ai_update(fighters, NF, 2, in);   /* not against the Chain Lab's dummy */
#endif
#endif
    if (bonus_on) bonus_input();                             /* a bonus game: its intents (after the AI's: the
                                                                referee's body cleared) */
#if LAB_BUILD
    prac_input();                                            /* the practice dummies that stand / walk in */
#endif
    if (ko_seq || (!attract && !lab.active && phase >= PH_END))
        for (i = 0; i < NF; i++) { in[i].dx = in[i].dz = 0; in[i].press = in[i].hold = in[i].run = in[i].grab = 0; in[i].face = 0; in[i].blitz = in[i].chord = 0; }
                                                          /* the boss's death: nobody acts any more (#172); the stage
                                                             clear: the input off (#184) */
    if (!attract && !lab.active && phase == PH_CLEAR) win_input();   /* (but a clear_walk's forward) */
    mark(P_AI);
    close_marks();
    if (bighit_slow && --bighit_slow < BIGHIT_SLOW && (bighit_slow & 1)) { depth_sort(); draw(); hud(); return; }
                                                          /* SS2's big hit's slow motion: every other tick held */
    if (in_ph == IN_WALK) intro_pre();
    for (i = 0; i < NF; i++)                                 /* a super flash: only its attacker moves */
        if (win_posing(i)) fighter_win_pose_tick(&fighters[i]);  /* the stage clear's win pose (#184) */
        else if (bonus_on == BN_PLAY && bn_chg_t > bn_g->chg_stand && i == bn_lead) fighter_pose_tick(&fighters[i]);   /* the Ki
                                                                    training's concentration (bn_gauge_flow) */
        else if (fighters[i].state != S_OFF && (!sf_who || sf_who == &fighters[i])) fighter_update(&fighters[i], &in[i]);
    if (!attract && !lab.active && phase == PH_CLEAR) win_tick();
    if (bonus_on) bonus_flow();                              /* a bonus game (its clock holds through a super flash) */
    else if (!sf_who) { if (lab.active) lab_flow(); else if (in_ph == IN_WALK) intro_post(); else if (in_ph) intro_wait(); else flow(); }
    if (mode != 1) return;                                   /* back on the title screen */
    if (dr_on) { depth_sort(); draw(); return; }             /* a scene starts: held from this tick, no HUD */
    if (!sf_who) {
        fighter_t *fl[NF];                                   /* the fighters in order[]'s order: the edges' entities */
        uint8_t n = 0;                                       /* (projectiles have none; cpu budget G) */
        for (i = 0; i < nf; i++) if (order[i] >= fighters && order[i] < fighters + NF && n < NF) fl[n++] = order[i];
        if (!bonus_on && in_ph != IN_WALK) camera();   /* (the stage intro's walk: its own x) */
        wall_update(fl, n, cam_x); screen_keep(fl, n, cam_x, 0); projectiles_update(cam_x, 0);
        mark(P_UPDATE);
        combat(order, nf, sf_who);
        if (!ko_seq && phase == PH_BOSS && !attract && !lab.active && fighters[BOSS_IDX].state != S_OFF && fighters[BOSS_IDX].hp <= 0)
            boss_ko_start();                                 /* its killing hit: the death sequence (#172) */
        wall_update(fl, n, cam_x); screen_keep(fl, n, cam_x, 1);   /* (again: a catch / a hit this frame placed its
                                                                victim; screen_keep: those it moved) */
    } else {
        projectiles_update(cam_x, 0x100 | sf_frozen);       /* the flash: only its attacker's effects born in it
                                                                (KOF98: P1 runs at the flash's priority $5001 and so do the
                                                                objects it spawns, $5D1C; the rest hold: Kyo's hand fire, #202) */
        mark(P_UPDATE);
        combat(order, nf, sf_who);                           /* a super flash: its attacker's own boxes only */
        if (!ko_seq && phase == PH_BOSS && !attract && !lab.active && fighters[BOSS_IDX].state != S_OFF && fighters[BOSS_IDX].hp <= 0)
            boss_ko_start();
    }
    mark(P_COMBAT);
    depth_sort();
    mark(P_SORT);
    draw();
    mark(P_PLACE);
    if (in_ph != IN_FADE) hud();                            /* (a stage intro begun this tick: no HUD yet) */
    mark(P_HUD);
    sf_tick();
}
