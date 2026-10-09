/* Brawler POC: Final Fight style beat 'em up on KOF data (fighter.c), character select then the fight.
 * P1 / P2: stick = walk on the floor (up/down = depth), double tap forward = run, A punch, B kick, C jump, D special.
 * Combo routes: AAA, AAB, BB, BAB, finishers forward+A / down+B; air A / B. Two dummy enemies (Terry's other colour sets).
 * HUD: P1 state and combo link, P1's target (fighter number, life), CPU = worst frame of the last 16 (crt0 counts idle spins of 54 cycles;
 * a frame is 202,752 cycles at 12 MHz, so idle % = spins * 54 / 2027.52 ~ spins * 7 / 256). */
#include <neoscan.h>
#include "neo_internal.h"
#include "fighter.h"
#include "ai.h"
#include "stage.h"
#include "sound.h"
#include "banner.h"
#include "sparks.h"
#include "superflash.h"
#include "throwfx.h"
#include "hud.h"
#include "game_tables.h"
#include "portraits_big.h"

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
static uint16_t prof[P_N], prof_max[P_N], prof_t;
static void mark(uint8_t sec) {
    uint16_t now = LINE(), d = now >= prof_t ? now - prof_t : now + 264 - prof_t;
    if (d > prof[sec]) prof[sec] = d;
    prof_t = now;
}

#define NF 8                         /* 2 players + 6 enemies: the POC target */
#define NE (NF + NPJ)                /* entities drawn: fighters + projectiles */
#define FIGHT_SPRS (NF * MAX_COLS + NPJ * PJ_COLS)   /* a fight's blocks: a fighter's MAX_COLS, the projectile pool's
                                        PJ_SPRS = NPJ * PJ_COLS shared by width (block_w) */
#define NA 24                        /* sprite blocks: NE in a fight, NA actors on the select screen (a block per roster
                                        fighter: the group photo) */
#define SEL_COLS 13                  /* sprites per block on the select screen (MAX_COLS in a fight): NA blocks of 13 =
                                        sprites 59-370 there (16 until NA 20, Billy Lee; 15 until NA 21, Genjuro; NA 22:
                                        Kuroko; 14 at NA 23: SS2's Hanzo, the blocks from sprite 59, the last one 380; 13 at
                                        NA 24: Rosa, TODO #213) (the banner's, the debug boxes', the sparks' and the throw effect's 300-379
                                        are not in use on that screen: sparks_draw / tfx_draw return there); the watch /
                                        win poses and the walk-offs are narrower (2026-10-07, build/bm_chars.c ncols of every
                                        selectable fighter's BA_WATCH / BA_WIN / BA_WALK_FWD frames: widest 11, Haohmaru's
                                        watch and Genjuro's win; Rosa 7 / 9 / 9) */
uint8_t blk_cols = MAX_COLS;         /* sprites per block now (draw.s fighter_tiles clips a frame to it) */
_Static_assert(16 + NA * MAX_PALS <= SFX_PAL && STAGE_PAL + STAGE_MAXPAL <= SFX_PAL && SFX_PAL + SFX_NPAL_MAX <= 240, "palettes: the select screen's actors, the stages, KOF's shared effects (TODO #214), the big portraits (PB_PALN)");
#define SPR_BASE 59                  /* fighter blocks (stage 22-42, shadows 43-58 behind them; 1-21 free) (60 until
                                        NA 23, TODO #193: SH_SPR + NE = 59 is the lowest it can be) */
static fighter_t fighters[NF];
static fighter_t *order[NA];                     /* back (small Z) to front, the nf entities in play */
static uint8_t nf;                               /* entities in play: the previews on the select screen, NE in the fight */
static uint8_t mode;                             /* 0 select, 1 fight, 2 title, 3 BOSS UNLOCKED, 4 the ending, 5 GAME OVER */
static uint8_t attract;                          /* the fight is the attract demo: P1 is ai_bot, enemies their attract_ai */
static uint16_t attract_t;
static uint8_t tap_t[2], tap_dir[2];             /* double-tap run detection per player */
static uint8_t bz_x[2][2], bz_xa[2][2], bz_z[2][2], bz_za[2][2];   /* the Blitz (read_player): per player the last two taps
                                                    of each axis (x: 1 right 2 left, z: 1 down 2 up) and their ages */
static uint8_t ab_age[2][2];                     /* A+B = C (read_player): frames since A / B was pressed */
enum { PH_WAVE, PH_GO, PH_BOSS, PH_END, PH_CLEAR };   /* campaign phases (see "campaign") */
static uint8_t phase;

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
static int16_t cam_x, lock_x;                    /* lock_x: how far right the camera may go now (campaign) */
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
static void vblank_flush(void) {
    SYS_vblankFlush();
    if (bd_pend) { PAL_setBackdrop(bd_next); bd_pend = 0; }
}
static void stage_hide(void) {                              /* title, select: no stage */
    uint8_t i;
    bd_on = 0;
    for (i = 0; i < BG_N; i++) cmd_push(VRAM_SCB3 + BG_SPR + i, 0);
}
static void stage_show(void) {
    uint8_t s;
    for (s = 0; s < BG_N; s++) cmd_push(VRAM_SCB3 + BG_SPR + s, ((496 - stg->y) << 7) | stg->rows);
}
static void stage_init(uint8_t n) {
    uint8_t s;
    bd_on = 0; bighit_red = bighit_slow = 0; hitflash = 0;
    stg = &stages[n]; floor_top = stg->floor_top; world_w = stg->cols << 4;
    stage_pals();
    *(volatile uint16_t *)0x3C0006 = stg->lspcmode;                /* REG_LSPCMODE: auto-animation speed */
    for (s = 0; s < BG_N; s++) {
        cmd_push(VRAM_SCB2 + BG_SPR + s, 0x0FFF);
        cmd_push(VRAM_SCB3 + BG_SPR + s, ((496 - stg->y) << 7) | stg->rows);
        bg_shown[s] = 0xFF;
    }
}
static void stage_draw(void) {
    uint8_t first = (uint8_t)(cam_x >> 4), s = first, k, r, n = stg->rows * 2;
    uint16_t *x = cmd_run(VRAM_SCB4 + BG_SPR, BG_N), *w;
    stage_cycle();
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
        if (f->x < FIX(cam_x + 16)) f->x = FIX(cam_x + 16);
        if (f->x > FIX(cam_x + 304)) f->x = FIX(cam_x + 304);
    }
}

/* Neo Geo draws higher sprite numbers on top: fighters further back get the lower blocks. A fighter whose block changed
 * gets its tiles rewritten into the new block (the position pass covers every block every frame, so nothing to hide). */
static uint8_t block_placed[NA];                 /* columns each sprite block showed last frame */
static uint16_t block_spr[NA];                   /* where it showed them (a block's place moves with the widths before it) */
static uint16_t slot_spr[NA];                    /* each depth slot's first sprite this frame (depth_sort) */
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
static void blocks_layout(uint8_t cols) {
    uint16_t i, *y;
    if (cols == blk_cols) return;
    blk_cols = cols;
    y = cmd_run(VRAM_SCB3 + SPR_BASE, NA * SEL_COLS > FIGHT_SPRS ? NA * SEL_COLS : FIGHT_SPRS);
    for (i = 0; i < (NA * SEL_COLS > FIGHT_SPRS ? NA * SEL_COLS : FIGHT_SPRS); i++) y[i] = 0;
    for (i = 0; i < NA; i++) block_placed[i] = 0;
}
static uint8_t sel_rank[NA];                     /* the select screen: each actor's draw order (SEL_SLOT z, 0 the back) */
static int32_t depth(const fighter_t *f) { return nf > NE ? sel_rank[f->idx] : f->z; }   /* the select: its layout's order */
static void depth_sort(void) {
    uint8_t i, j;
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
        uint16_t s = SPR_BASE;                   /* blocks back to front, each its entity's width */
        for (i = 0; i < NA; i++) {
            slot_spr[i] = s;
            if (i < nf && order[i]->spr != s) { order[i]->spr = s; order[i]->shown_frame = 0xFFFF; }
            s += i < nf ? block_w(order[i]) : blk_cols;
        }
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
    uint16_t *y = cmd_run(VRAM_SCB3 + SH_SPR, NE), *x = cmd_run(VRAM_SCB4 + SH_SPR, NE);
    uint8_t i;
    shadow_parity ^= 1;
    for (i = shadow_parity; i < NE; i += 2, y += 2, x += 2) {
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
typedef struct { uint8_t on, kind, frame, t; int16_t x, y; int8_t facing; } spark_state_t;
static spark_state_t spk[SPARK_N];
void spark_hit(int16_t wx, int16_t sy, uint8_t big, int8_t facing) {
    uint8_t i, best = 0;
    for (i = 0; i < SPARK_N; i++) {                          /* a free slot, else the oldest */
        if (!spk[i].on) { best = i; break; }
        if (spk[i].frame > spk[best].frame) best = i;
    }
    spk[best].on = 1; spk[best].kind = big ? SPARK_BIG : SPARK_SMALL; spk[best].frame = 0; spk[best].t = 0;
    spk[best].x = wx; spk[best].y = sy; spk[best].facing = facing;
}
static void sparks_init(void) {
    uint8_t i;
    PAL_setPalette(SPARK_PAL, spark_pal);
    for (i = 0; i < SFX_NPAL; i++) PAL_setPalette(SFX_PAL + i, bm_sfx_pals + (i << 4));   /* KOF's shared effects bank's
                                                                    palettes (TODO #214: Iori 624D's explosion, Rugal's slam) */
    for (i = 0; i < SPARK_N * 3; i++) { cmd_push(VRAM_SCB2 + SPARK_SPR + i, 0x0FFF); cmd_push(VRAM_SCB3 + SPARK_SPR + i, 0); }
    for (i = 0; i < SPARK_N; i++) spk[i].on = 0;
}
static void sparks_draw(void) {
    uint8_t i, c, r;
    if (!mode) return;                                       /* the select's actors use sprites 300-379 */
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
                    w[r * 2 + 1] = (uint16_t)(SPARK_PAL << 8) | (k->facing > 0 ? 1 : 0);
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
static int16_t sf_dx, sf_dy;
void super_flash(fighter_t *f) {
    const bspec_t *sp = f->state == S_SPECIAL ? &f->ch->specials[f->spec_ix] : 0;   /* (a paired super throw, revamp 3: none) */
    if (mode != 1) return;
    sf_who = f; sf_flash_t = 0; sf_glow_on = 0; sf_ray = 0xFF; sf_frozen = projectiles_alive();
    sf_col = sp && f->ch->fury_max < f->ch->nspec && f->spec_ix == f->ch->fury_max;   /* MAX: orange */
    if (f->ch->nfpose) { sf_dx = f->ch->fhead[0]; sf_dy = f->ch->fhead[1]; }   /* a flash pose (TODO #145): its head */
    else if (sp && sp->sf_anchor) { sf_dx = sp->sf_dx; sf_dy = sp->sf_dy; } else { sf_dx = gflash.dx; sf_dy = gflash.dy; }
    PAL_setPalette(SF_RAYS_PAL, sf_ray_pal[sf_col]);
    snd_sfx(sf_col ? gflash.sound_max : gflash.sound);      /* a fury: KOF98's charge sound ($370F0 -> $3906E: index
                                                                $99 = $1A $3A, DM and SDM alike); a MAX: KOF2000's
                                                                SDM flash whistle ($1E $8F there, $1A $8F here: TODO #155) */
}
static void sf_reset(void) {
    uint8_t c;
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
    if (!mode) { tfx_on = 0; return; }                      /* the select's actors use sprites 300-379 */
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
    if (bighit_red) {                                        /* SS2's big hit (fighter.c big_hit): red, no stage */
        if (!bd_on) { stage_hide(); bd_on = 1; bd_t = 0; }
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
        else if (k == 2 || k == 6) { stage_hide(); bd_on = 1; }
        else if (k == 4 || k == 8) { stage_show(); bd_set(stg->backdrop); bd_on = 0; }
    } else if (sf_who) {                                     /* the super flash: the stage hidden, white then black (the */
        if (!bd_on) { stage_hide(); bd_on = 1; bd_t = 0; }       /* colour of the frame shown: sf_tick counts after) */
        bd_set((uint8_t)(sf_flash_t + 1) <= gflash.white ? gflash.white_col : gflash.dark_col);
    } else if (sp) {                                         /* Kizuna's strobe, bd_col[0] first (measured) */
        if (!bd_on) { stage_hide(); bd_on = 1; bd_t = 0; }
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
/* step c: an entity's shown columns on the 8-px bands (sign -1: taken back; th: thinned, its columns th - 1, th + 1,
 * ...); its band range in *lo / *hi */
static void cols_add(const fighter_t *f, int16_t oy, int8_t sign, uint8_t th, uint8_t *lo, uint8_t *hi) {
    const col_trim_t *c = &col_trim[f->idx];
    uint8_t k, b0, b1, rows;
    *lo = BANDS; *hi = 0;
    for (k = th ? th - 1 : 0; k < f->ncols; k += th ? 2 : 1) {
        if (!(rows = c->t[k] & 63)) continue;
        b0 = span(oy + c->top[k], oy + c->top[k] + (int16_t)(rows << 4), 3, &b1);
        if (b0 > b1) continue;
        bands_add(b0, b1, sign);
        if (b0 < *lo) *lo = b0;
        if (b1 > *hi) *hi = b1;
    }
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
    base = mode == 1 ? BG_N + dr_cols + (tfx_on ? TFX_COLS : 0) : 0;
    total = base;
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

static void draw(void) {
    uint8_t i;
    if (mode == 1) { screen_fx(); stage_draw(); }            /* only the fight has a stage */
    for (i = 0; i < nf; i++)
        if (order[i]->state != S_OFF && !(order[i]->state == S_PROJ && order[i]->frame_ovr == 0xFFFF) && block_w(order[i])) {
            uint8_t bc = blk_cols, ob = BANK_set(CH_BANK(order[i]->ch));   /* its frames: its bank (fighter.h) */
            blk_cols = block_w(order[i]); trim_cur = &col_trim[order[i]->idx]; fighter_tiles(order[i]); blk_cols = bc;   /* clipped to its block */
            BANK_set(ob);
        }
    mark(P_TILES);
    line_guard();
    mark(P_GUARD);
    for (i = 0; i < NA; i++)                                 /* a block that moved: its old place cleared first */
        if (block_placed[i] && block_spr[i] != slot_spr[i]) {
            uint16_t *y = cmd_run(VRAM_SCB3 + block_spr[i], block_placed[i]); uint8_t c;
            for (c = 0; c < block_placed[i]; c++) y[c] = 0;
            block_placed[i] = 0;
        }
    for (i = 0; i < NA; i++) {
        fighter_t *f = order[i];
        uint8_t vis = i < nf && !hidden[i], n = vis ? f->ncols : 0, m = n > block_placed[i] ? n : block_placed[i];
        uint16_t spr = slot_spr[i], *y, *x;
        if (m) {
            y = cmd_run(VRAM_SCB3 + spr, m); x = cmd_run(VRAM_SCB4 + spr, m);
            if (vis) { uint8_t ob = BANK_set(CH_BANK(f->ch)); trim_cur = &col_trim[f->idx]; fighter_place(f, y, x, cam_x, m); BANK_set(ob); }
            else { uint8_t c; for (c = 0; c < m; c++) y[c] = x[c] = 0; }
        }
        block_placed[i] = n; block_spr[i] = spr;
    }
    shadows();
    sparks_draw();
    if (mode == 1) sf_draw();
    tfx_draw();
    dbg_draw();
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
    uint8_t i, j;                               /* intent.lie: the nearest opponent lying within DOWN_REACH (up / down + A: */
    for (i = 0; i < NF; i++) {                  /* the down attack at it, TODO #218) */
        const fighter_t *f = &fighters[i];
        int16_t best = DOWN_REACH + 1;
        in[i].close = 0; in[i].lie = 0;
        if (f->state == S_OFF) continue;
        for (j = 0; j < NF; j++) {
            fighter_t *o = &fighters[j];
            int16_t dx = INT(o->x) - INT(f->x), dz = INT(o->z) - INT(f->z);
            if (o->team == f->team || o->state == S_OFF || o->state == S_DEAD) continue;
            if (dx >= -CLOSE_X && dx <= CLOSE_X && dz >= -Z_HIT && dz <= Z_HIT) in[i].close = 1;
            if (dx < 0) dx = -dx;
            if (o->state == S_DOWN && o->hp > 0 && dx < best) { best = dx; in[i].lie = o; }
        }
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
typedef struct { uint8_t col, row, mirror, n, cell[BOSS_CELLS], wait, pal; int16_t px, trail; } bar_t;
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
 * the name, one short bar per chunk (CHUNK_CELLS cells, the life bar's glyphs in METER_PAL, a cell apart; P2's mirrored
 * from the right edge), each filled with its share of the drive (the first chunk first), no label; the fury gauge is never
 * drawn. A player's life bar has its own fix palette (LIFE_PAL + player): at low life (fighter_low) it blinks red,
 * KOF95's (measured in our emulator, /data/tmp/newsys/scripts/kof_bar.py: 8 frames red, 8 frames its colours; the life
 * left pure red #FF0000 with a darker top / bottom row, the emptied part #C93616 instead of its dark) */
#define CHUNK_CELLS 4
#define MAX_CHUNKS  4                    /* (gmeter.chunks: build_tables allows 1-4) */
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
static uint8_t wave;
static void fix_put(uint8_t col, uint8_t row, uint16_t v) { cmd_push(VRAM_FIX + col * 32 + row + 2, v); }
static uint8_t char_index(const bchar_t *ch) { uint8_t i; for (i = 0; i < BC_COUNT; i++) if (&bm_chars[i] == ch) return i; return 0; }
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
    int16_t full = (b->n << 3) - 2, px, x0 = 0;
    if (!max) max = LIFE;
    px = hp <= 0 ? 0 : max * 2 > full ? (int16_t)div16((uint16_t)hp * (uint16_t)full, max) : hp * 2;
    if (px > full) px = full;
    uint8_t c;
    if (px < b->px && b->trail < b->px) b->trail = b->px;          /* a new hit: the trail starts at the old life */
    if (px < b->px) b->wait = 20;
    b->px = px;
    if (b->trail > px) { if (b->wait) b->wait--; else b->trail--; } else b->trail = px;
    for (c = 0; c < b->n; c++) {                                 /* c counts from the bar's outer edge */
        uint8_t kind = c == 0 ? 0 : c == b->n - 1 ? 2 : 1, w = kind == 1 ? 8 : 7, t, sc = b->mirror ? b->n - 1 - c : c;
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
    static const uint8_t COL[5] = { 5, 20, 5, 20, 5 }, ROW[5] = { 0, 0, 4, 4, 7 };
    uint8_t p, c;
    for (p = 0; p < 5 + 2 * MAX_CHUNKS; p++) {
        uint8_t k = (p - 5) % MAX_CHUNKS, two = p >= 5 + MAX_CHUNKS;   /* (a chunk: its index, P2's) */
        bars[p].col = p < 5 ? COL[p] : two ? 35 - CHUNK_CELLS - (CHUNK_CELLS + 1) * k : 5 + (CHUNK_CELLS + 1) * k;
        bars[p].row = p < 5 ? ROW[p] : 3;
        bars[p].mirror = (p & 1 && p < 4) || two; bars[p].px = bars[p].trail = -1; bars[p].wait = 0;
        bars[p].n = p < 4 ? BAR_CELLS : p == 4 ? BOSS_CELLS : CHUNK_CELLS; bars[p].pal = p >= 5 ? METER_PAL : p == 0 ? LIFE_PAL : 0;
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
static fighter_t *tgt(fighter_t *f) {    /* a player's target for the right block: the boss has its own bar */
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
        if (hud_face[p] != face) { hud_face[p] = face; portrait(pc, 0, face, p); hud_name(p, 1, f->ch->name); }
        bar_draw(&bars[p], in_play(f) ? f->hp : 0, f->hp_max);
        {   uint8_t k;                                       /* the drive: one bar per chunk, the first filled first */
            int16_t d = in_play(f) ? (int16_t)f->drive : 0;
            for (k = 0; k < gmeter.chunks && k < MAX_CHUNKS; k++) {
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
        if (two) hud_target(2 + p, tgt(f), p, 5, 0);       /* each player's target under its own block: bar, name */
    }
    if (!two) hud_target(1, tgt(&fighters[0]), 1, 1, 1);  /* one player: its target is the right block */
    i = mode == 1 && !attract && (phase == PH_BOSS || phase == PH_END) && fighters[BOSS_IDX_HUD].state != S_OFF;
    if (i != boss_shown) {                                   /* the boss bar: name on row 6, bar on row 7 */
        boss_shown = i;
        FIX_print(5, 6, "              ", 0);
        if (i) FIX_print(5, 6, FIGHTER_NAME(&fighters[BOSS_IDX_HUD]), 0); else bar_clear(&bars[4]);
    }
    if (boss_shown) bar_draw(&bars[4], fighters[BOSS_IDX_HUD].hp, fighters[BOSS_IDX_HUD].hp_max);
    if ((hud_tick & 15) != 0 && (uint16_t)wait_cycles < hud_min_spins) hud_min_spins = (uint16_t)wait_cycles;  /* skip the print tick */
    if (!(++hud_tick & 15)) {
        uint16_t idle = (uint16_t)(((uint32_t)hud_min_spins * 7) >> 8);
        FIX_print(30, 26, "CPU    %", 0); FIX_printNum(34, 26, idle >= 100 ? 0 : 100 - idle, 0);
        hud_min_spins = 0xFFFF;
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
#else
        for (i = 0; i < P_N; i++) { prof_max[i] = prof[i]; prof[i] = 0; }
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
    if (t->root >= n || t->dash >= n || t->nospec >= n || t->hold >= n || t->air_a >= n || t->air_b >= n || t->air_cd >= n) return 0;
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
    if (h->version != GD_VERSION) return 2;     /* 7 (TODO #71): route trees version 4; an older pack's trees read the old buttons */
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
 * BIOS CARD call (FCB = NGH $0999, sub 0): loaded on the title, written at once after each stage. Checked by magic +
 * sum: anything else (a blank block, another build's) = a fresh save. ---- */
typedef struct {
    uint8_t  dips[2];                            /* SNK: the backup block starts with the debug dipswitches */
    char     magic[4];                           /* "BRW2" (format 2; "BRW1" = format 1, read and upgraded) */
    uint8_t  furthest;                           /* the campaign stage reached, 0-4 (the title's CONTINUE) */
    uint8_t  unlocked;                           /* bit k: BOSS[k] beaten (selectable) */
    uint8_t  difficulty;                         /* format 2: AES OPTIONS difficulty 0-3 (format 1: 0, a spare) */
    uint8_t  pad[5];
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
    save.furthest = 0; save.unlocked = 0; save.difficulty = 1;
    for (i = 0; i < 5; i++) save.pad[i] = 0;
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
static uint8_t char_locked(uint8_t c) { uint8_t k = roster_unlock[c]; return k == 0xFF || (k && !(save.unlocked >> (k - 1) & 1)); }   /* 0xFF: a form link's target, never picked */
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

/* title: banner, PRESS START; a menu when there is a choice (stick up / down, then START): NEW GAME, CONTINUE STAGE n
 * (a save past stage 1), OPTIONS (console = AES only, see options_tick); A+B+C+D held 2 s clears the save. */
static uint16_t title_t, title_hold;
static uint8_t title_sel;                        /* the menu line */
static uint8_t title_paid;                       /* the START that opened the title already took the credit */
enum { TI_NEW, TI_CONT, TI_OPT };
static uint8_t title_item[3], title_n;           /* the menu's lines */
static uint8_t opt_on;                           /* the OPTIONS screen is up (a part of the title, mode 2) */
static void select_start(void);
static void save_load(void);
static void save_reset(void);
static void save_write(void);
static void title_menu(void) {
    static const char *const TXT[3] = { "NEW GAME", "CONTINUE STAGE", "OPTIONS" };
    uint8_t i;
    for (i = 0; i < 3; i++) FIX_print(12, 20 + i, "                  ", 0);
    title_n = 0; title_item[title_n++] = TI_NEW;
    if (save.furthest) title_item[title_n++] = TI_CONT;
    if (!BIOS_MVS_FLAG) title_item[title_n++] = TI_OPT;
    if (title_sel >= title_n) title_sel = 0;
    if (title_n == 1) return;
    for (i = 0; i < title_n; i++) {
        FIX_print(12, 20 + i, i == title_sel ? "> " : "  ", 0); FIX_print(14, 20 + i, TXT[title_item[i]], 0);
        if (title_item[i] == TI_CONT) FIX_printNum(29, 20 + i, save.furthest + 1, 0);
    }
}
static void title_screen(void) {
    FIX_clear(); arcade_line_reset();
    banner_show((320 - BANNER_COLS * 16) / 2, 56);
    FIX_print(14, 24, "(C) 2027 NEOSAKURAGI", 0);
    FIX_print(17, 15, "V" GAME_VERSION, 0);                 /* VERSION, from the Makefile */
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
    snd_music(GAME_MUS_SELECT);
    save_load();
    title_sel = save.furthest != 0; title_hold = 0; title_paid = 0;   /* line 1 = CONTINUE when there is one */
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
    snd_music(GAME_MUS_SELECT);
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
        if (++title_hold == 120) { save_reset(); save_write(); difficulty = save.difficulty; title_menu(); FIX_print(12, 23, "SAVE DATA CLEARED", 0); }
        return;
    } else title_hold = 0;
    if (title_item[title_sel] == TI_OPT) {                   /* console only: no credit involved */
        if (bios_start || (pr & (JOY_START | JOY_A))) { bios_start = 0; snd_ssg(SSG_CONFIRM); options_start(); }
        return;
    }
    if (bios_start || (title_paid && (pr & (JOY_START | JOY_A)))) {   /* START with a credit (PLAYER_START), or START / A
                                                             when the credit was taken by the START that opened it */
        bios_start = 0; title_paid = 0; camp_from = title_item[title_sel] == TI_CONT ? save.furthest : 0;
        banner_hide(); select_start(); snd_ssg(SSG_CONFIRM); return;   /* the cue after the song start: queued
                                                             before it, the driver's song start stretches its first note */
    }
}

/* ---- character select: a group photo (Bruno 2026-10-05, TODO #51). The whole roster stands in rows like a school
 * photo, everyone at once: the front rows the playable fighters, the back row the campaign bosses (a locked boss is a
 * dark silhouette, not selectable; once beaten it is in colour / dark like the others). Each fighter holds its 'watch'
 * pose (export_bm.WATCH: a front-facing frame from its intros / win poses), facing as the layout says. The places are
 * slots (SEL_SLOT: x, y, z, face), independent of who stands in them (sel_fighter: the fighter of each slot), so moving
 * someone on screen is a change to game.json's select_layout only. The cursor's fighter shows its colours, the others their own
 * colours at half brightness (col_dark). "1P" / "2P" with an arrow above the selected head (fix layer). The stick follows
 * the cursor graph computed from the places (sel_stick, TODO #187: left / right along the row, up / down to the
 * nearest row above / below); A/B/C/D picks that colour set
 * (KOF style) and plays the win pose. P2 joins here with START (a credit) and picks too; the two can't pick the same
 * fighter. When everyone in has picked, the others walk off the screen outward, then the
 * fight cuts in (no fades: a palette fade cost ticks frames). Each fighter on screen is an entity (actor): the fight's NE entities + NA - NE more. ---- */
#define SHOW_Z 40                        /* BOSS UNLOCKED / ending: feet at SELECT_FLOOR + SHOW_Z */
_Static_assert(SEL_NSLOT <= NA, "group photo: an actor per slot (every selectable fighter has one: build_tables.py)");
_Static_assert(SPR_BASE + FIGHT_SPRS <= 300 && SPR_BASE + NA * SEL_COLS <= 381, "sprite blocks: fight below the banner, select within the 381 sprites (sparks / throw effect idle there)");
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
static fighter_t sel_extra[NA - NE];     /* actors NE.. (the fight's entities are actors 0..NE-1) */
static fighter_t *actor(uint8_t a) { return a < NF ? &fighters[a] : a < NE ? &projectiles[a - NF] : &sel_extra[a - NE]; }
/* the unlocked fighters in CHARS order (the attract demo's players) */
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
static uint8_t selectable(uint8_t s) { return slot_ch[s] != 0xFF && !char_locked(slot_ch[s]); }
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
/* an entity's palettes: its own colours (1), darkened (0) or a silhouette (2) */
static void fighter_pals(const fighter_t *f, uint8_t colour) {
    uint16_t buf[16];
    uint8_t i, j;
    for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) {
        const uint16_t *src = fighter_src_pal(f, i);
        buf[0] = src[0];
        for (j = 1; j < 16; j++)
            buf[j] = colour == 2 ? SILHOUETTE : colour ? fighter_colour(f, src[j]) : col_dark(src[j]);
        PAL_setPalette(f->palbase + i, buf);
    }
}
static uint8_t chosen(uint8_t s) { return s == cursor[0] || s == cursor[1]; }
static uint8_t slot_look(uint8_t s) { return char_locked(slot_ch[s]) ? 2 : chosen(s); }
static void slot_show(uint8_t s, uint8_t set) {             /* (re)binds slot s's actor: its fighter, colour set, pose */
    uint8_t a = slot_act[s];
    fighter_t *f = actor(a);
    const bchar_t *ch = &bm_chars[slot_ch[s]];
    fighter_init(f, ch, set < ch->nsets ? set : 0, 16 + a * MAX_PALS, 1, SEL_SLOT[s].x, SEL_SLOT[s].y - SELECT_FLOOR);
    f->idx = a; f->facing = SEL_SLOT[s].face; sel_rank[a] = SEL_SLOT[s].z;
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
            t = sel_stick[t][d];
            if (t == s) break;
            if (selectable(t)) return t;
        }
    } else if (d < 4) {
        for (n = 0; n < SEL_NSLOT - 1; n++) {
            t = sel_vert[s][d - 2][n];
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
            int16_t sx = SEL_SLOT[s].x + (SEL_SLOT[s].face > 0 ? -hd[0] : hd[0]) - 4 + (p && cursor[0] == s ? 16 : 0);   /* both on one fighter: 2P to the right */
            int16_t sy = SEL_SLOT[s].y + hd[1] - 10;
            col[p] = sx < 0 ? 0 : (uint8_t)((sx + 4) >> 3);        /* FIX_print col c / row r = screen x c * 8, y r * 8 */
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
static void select_start(void) {
    uint8_t p, i, s, a = 0;
    mode = 0; sel_t = 0; sel_phase = SEL_CHOOSE; attract = 0;
    inputs_reset();
    snd_music(GAME_MUS_SELECT);
    FIX_clear(); arcade_line_reset();
    bd_set(RGB8(72, 76, 84));                                /* the photo's wall */
    stage_hide();                                            /* stage sprites hidden */
    floor_top = SELECT_FLOOR;
    dbg_init();
    FIX_print(10, 1, "SELECT YOUR FIGHTER", 0);           /* FIX_print row r = screen y r * 8 (rows 0-27) */
    FIX_print(3, 26, "STICK MOVES   A B C D PICK COLOURS", 0);   /* under the front row's feet (y 206) */   /* keyboard: WASD, U I O P */
    for (p = 0; p < 2; p++) { picked[p] = 0; pick_set[p] = 0; arrow_col[p] = 0xFF; }
    slots_build(); roster_build();
    for (s = 0; s < SEL_NSLOT && !selectable(s); s++) ;
    cursor[0] = s; cursor[1] = 0xFF;                         /* the first selectable slot (Terry); P2: START joins */
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    for (i = 0; i < NA; i++) { actor(i)->state = S_OFF; order[i] = actor(i); }
    for (s = 0; s < SEL_NSLOT; s++) { slot_act[s] = 0xFF; if (slot_ch[s] != 0xFF) { slot_act[s] = a++; slot_show(s, 0); } }
    nf = NA;
    cam_x = 0; select_name();
}
/* ---- campaign (Bruno 2026-10-05, Streets of Rage 2 / Golden Axe style): the stages of game.json in order (gstages[]:
 * today Robo Army's horizontal ones, stages[] 0, 1, 3, 4, 5; 2, the 512 px boss arena, is not used). Each stage scrolls
 * through its waves' lock points (camera x): at a lock point the camera stops until the wave there is beaten, then GO
 * blinks and the camera may scroll on to the next one (never back), the last one the boss's. A wave's spawns (at most
 * NF - 2 = 6) are enemies (genemies[]): a fixed fighter or one of a pool (the fighters nobody picked: pick mod the pool
 * left), at a world x or walking in from off screen (the right, or the left when there is room); the stage's enemies
 * land `power` extra damage a hit. At the stage's end its boss comes in with its minions (at most 5, in minion colours:
 * fighter_colour's tints, never a playable colour set); the boss bar under the HUD; boss beaten: the minions go down,
 * STAGE CLEAR, the save (furthest stage, boss unlocked), BOSS UNLOCKED when its fighter was locked, a cut to the next
 * stage. After the last: CONGRATULATIONS, then the title. Players: 3 lives, then the continue ("continue and GAME OVER"
 * below). The attract demo plays the first stage's waves on background STAGE (make STAGE=n,
 * stages[] index) without a boss, the last wave again and again. ---- */

static uint8_t unlock_k;                         /* the boss just unlocked + 1 (0 none) */
static uint16_t phase_t;
static const gstage_t *gs;                       /* the stage playing: gstages[camp] */
static uint8_t power;                            /* this stage's enemies' extra damage */
static uint8_t pl_ch[2], pl_set[2], pl_on[2];   /* the players, carried from stage to stage (pl_on: in play) */

static uint8_t mod8(uint8_t a, uint8_t b) { while (a >= b) a -= b; return a; }   /* no libgcc: no 32-bit % */
static void hud_wave(void) {
    FIX_print(2, 26, "STAGE   WAVE   ", 0); FIX_printNum(8, 26, camp + 1, 0);
    if (phase >= PH_BOSS) FIX_print(10, 26, "BOSS ", 0); else FIX_printNum(15, 26, wave + 1, 0);
}
static int16_t lock_at(int16_t x) { int16_t m = world_w - 320; return x > m ? m : x; }   /* inside the background shown */
static uint8_t ai_of(const genemy_t *en) { return attract ? en->attract_ai : en->ai; }
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
    e->name = en->flags & GE_FIGHTER_NAME ? 0 : en->name; e->cpal = en->pal; e->tree = (const rt_head_t *)en->moves;
    if (!attract) e->hp = e->hp_max = life(en->life);     /* the campaign's difficulty (the demo: as it was) */
    if (tint || e->cpal) fighter_load_pals(e);
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
static void spawn(uint8_t slot, const gspawn_t *sp, uint8_t boss_c) {
    const genemy_t *en = &genemies[sp->enemy];
    uint8_t c = en->base != 0xFF ? en->base : pool_pick(en, sp->pick, sp->flags & SP_NOT_BOSS ? boss_c : 0xFF);
    enemy_init(slot, c, sp->set, spawn_x(sp), sp->z, sp->tint, en);
}
/* the spawns' AI: every slot the first spawn's preset (ai_init, the RNG seeded), then any other spawn's its own */
static void spawns_ai(uint16_t seed, const gspawn_t *sp, uint8_t n, uint8_t slot0) {
    uint8_t k, p0 = n ? ai_of(&genemies[sp[0].enemy]) : AI_MINION, p;
    ai_init(seed, p0);
    for (k = 0; k < n; k++) if ((p = ai_of(&genemies[sp[k].enemy])) != p0) ai_set(slot0 + k, p);
}
/* ---- drama mode (docs/brawler_data_model.md "Drama mode"): black bars slide in from the top and the bottom (fix rows
 * 0-3 and 20-27, DRAMA_FONT's opaque cells), the fight held (no AI, no update, no flow: game_tick only draws), each scene's
 * big portrait (portraits_big.h: sprites PB_SPR.., the box viewer's, palettes PB_PALN..) slides in on its speaker's side
 * (left: mirrored), the name plate and the lines typed on the bottom bar; A-D / START: the rest of the text at once, then
 * the next scene; else each scene goes on after its wait. Then the bars slide out, the HUD comes back, the song (a
 * boss's) starts. ---- */
#define PB_SPR  300
#define PB_PALN 240                      /* palettes 240-247 */
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
static const fighter_t *dr_who(const gscene_t *sc) {   /* "$P1": P1, or P2 when P1 is out; "$P2": P2; 0 = skip the scene */
    if (sc->who == DW_P1) return in_play(&fighters[0]) ? &fighters[0] : in_play(&fighters[1]) ? &fighters[1] : 0;
    if (sc->who == DW_P2) return in_play(&fighters[1]) && in_play(&fighters[0]) ? &fighters[1] : 0;
    return &fighters[0];
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
static uint8_t ko_scream;                        /* 1: the boss's death voice still to come (ghitsnd.scream_delay) */
/* ---- the stage clear's win pose (TODO #184, Bruno 2026-10-07: "a little winning pose here at the end of the stage"):
 * when every enemy is gone (after the boss's death sequence), STAGE CLEAR and the input off as before; each player in
 * play (both in a 2-player game) first finishes what he is doing with no input (an attack, a fall, a landing: until
 * he stands, S_IDLE), then turns toward the middle of the screen (the source games' winner faces the opponent he
 * beat, who stood toward the middle) and plays his fighter's 'win' animation once, its voices as the source sends
 * them (export_bm MOVES 'win': each source game's round-win animation, read in our emulator: tools/kof98/capture/
 * wins98.py, tools/brawler/wins184.py), held on its last frame; the next screen comes WIN_HOLD frames after the last
 * pose ended (and never before STAGE CLEAR's 200 frames; at most WIN_MAX). The fighter's state machine is not run
 * while it poses (fighter_pose_tick only), the players untouchable. ---- */
#define WIN_HOLD   45                            /* frames held on the pose's last frame before the next screen */
#define WIN_SETTLE 180                           /* a player not standing by then does not pose */
#define WIN_MAX    720                           /* the next screen at the latest (Iori's KOF98 win: 305 frames) */
enum { WIN_NONE, WIN_WAIT, WIN_POSE };
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
static uint8_t win_posing(uint8_t i) { return i < 2 && win_st[i] == WIN_POSE; }
static void win_tick(void) {                     /* every fight frame after the fighters' update */
    uint8_t i;
    for (i = 0; i < 2; i++) {
        fighter_t *f = &fighters[i];
        if (win_st[i] == WIN_NONE) continue;
        if (f->inv < 2) f->inv = 2;
        if (win_st[i] == WIN_WAIT) {
            if (f->state == S_IDLE && f->y == 0) {
                f->facing = INT(f->x) - cam_x < 160 ? 1 : -1;
                f->frame_ovr = 0xFFFF; f->vx = f->vz = 0;
                fighter_pose(f, BA_WIN); win_st[i] = WIN_POSE; win_t[i] = 0; win_step[i] = 0xFF;
            } else if (++win_t[i] >= WIN_SETTLE || f->state == S_DEAD || f->state == S_OFF) win_st[i] = WIN_NONE;
        } else if (f->anim_done && win_t[i] < 0xFFFF) win_t[i]++;
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
    for (i = 0; i < 2; i++) if (win_st[i] == WIN_WAIT || (win_st[i] == WIN_POSE && win_t[i] < WIN_HOLD)) return 0;
    return 1;
}
static void triggers_reset(void) { trig_fired = 0; stage_tk = wave_t = 0; wave_on = 0; waves_cleared = 0; trig_held = 0; tq_n = 0; ko_seq = KO_OFF; ko_scream = 0; win_st[0] = win_st[1] = WIN_NONE; }
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
    snd_sfx(ghitsnd.boss_ko); b->ko_voice = 1; ko_scream = 1;   /* (ko_voice: none at its S_DEAD, boss_ko_tick screams) */
}
static uint8_t boss_ko_tick(void) {              /* every frame of the sequence; 1: a logic tick this frame */
    uint8_t i;
    for (i = 0; i < 2; i++) if (fighters[i].inv < 2) fighters[i].inv = 2;   /* the players: untouchable to the clear (2: still
                                                             set in combat after their update counted one down) */
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
    phase = PH_BOSS; phase_t = 0; ko_seq = KO_OFF;
    if (c == pl_ch[0] && !pl_set[0]) set = 1;           /* never in P1's colours */
    enemy_init(BOSS_IDX, c, set, gs->boss_x, gs->boss_z, 0, be);
    for (k = 0; k < NF - 3; k++) {
        if (k >= gs->nmin) { fighters[3 + k].state = S_OFF; continue; }
        spawn(3 + k, &gs->spawns[gs->boss_first + k], c);
    }
    spawns_ai(gs->boss_seed, &gs->spawns[gs->boss_first], gs->nmin, 3);
    ai_set(BOSS_IDX, ai_of(be));
    wave_on = gs->nwaves; wave_t = 0;
    k = gstagex[camp].drama;                         /* its scene first (the fight held), then its song */
    if (k < DR_COUNT && !attract) drama_start(k, gs->boss_song); else snd_music(gs->boss_song);
    hud_wave();
}
static void go_sign(uint8_t on) { FIX_print(29, 3, on ? "GO -->" : "      ", 1); }   /* highlighted (palette 1), in the HUD's black band */
static void stage_begin(uint8_t s, uint8_t first) {
    uint8_t i;
    if (gd_want) gd_apply();                                 /* a lab's pack */
    mode = 1; nf = NE; cam_x = 0; wave = 0; cont_ov = 0; camp = s; phase = PH_WAVE; phase_t = 0; gs = &gstages[s];
    triggers_reset(); dr_on = DR_OFF; dr_cols = 0; guard_parity = shadow_parity = 0;      /* a drama cut short (the lab): dbg_init below hides its sprites */
    inputs_reset();
    snd_music(gs->music);
    dbg_init();                                              /* the title's banner reused sprites 300-318 */
    sparks_init();
    sf_reset();
    tfx_reset();
    FIX_clear(); arcade_line_reset();
    stage_init(attract ? STAGE : gs->bg);             /* stage sprites back, every column rewritten */
    bd_set(stg->backdrop);
    lock_x = lock_at(gs->waves[0].lock);
    power = gs->power;
    if (first) ai_rank_reset();                              /* a new game: the hidden rank from rank_start (revamp 1B) */
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    for (i = 0; i < 2; i++) {
        if (!pl_on[i]) { fighters[i].state = S_OFF; if (first) { lives[i] = 0; cont_t[i] = 0; } continue; }   /* out: its
                                                             continue countdown (if any) goes on */
        fighter_init(&fighters[i], &bm_chars[pl_ch[i]], pl_set[i], 16 + i * MAX_PALS, 0, i ? 40 : 60, i ? 10 : 40);
        fighters[i].idx = i;
        if (first) { lives[i] = 3; cont_t[i] = 0; }
    }
    spawn_wave();
    for (i = 0; i < NF; i++) order[i] = &fighters[i];
    for (i = 0; i < NPJ; i++) { projectiles[i].idx = NF + i; order[NF + i] = &projectiles[i]; }
    hud_reset();
    if (first) { BIOS_PLAYER_MOD[0] = attract ? 0 : 1; BIOS_PLAYER_MOD[1] = pl_on[1]; }   /* BIOS: who plays (a START then joins) */
}
static void fight_start(void) {                  /* from the select screen (pl_* set): a new game at camp_from */
    stage_begin(attract ? 0 : camp_from, 1);
}
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
    snd_music(GAME_MUS_SELECT);
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
    if (mode != 1 || cont_ov == 2 || phase >= PH_END || ko_seq) return 0;
    return flags & ((in_play(&fighters[0]) ? 0 : 1) | (in_play(&fighters[1]) ? 0 : 2));
}
static void unlock_start(uint8_t k);
static void ending_start(void);
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
        FIX_print(14, 13, "STAGE CLEAR", 0); snd_music(GAME_MUS_CLEAR);
        phase = PH_CLEAR; phase_t = 0; unlock_k = 0;
        win_start();                                         /* the players' win poses (#184) */
        if (attract) break;
        if (camp + 1 < GS_COUNT && save.furthest < camp + 1) save.furthest = camp + 1;
        if (gs->unlock && !(save.unlocked >> camp & 1)) { save.unlocked |= 1 << camp; unlock_k = camp + 1; }
        save_write();
        break;
    case PH_CLEAR:
        if (phase_t < 200 || (!win_done() && phase_t < WIN_MAX)) break;   /* the win poses played, then the next screen: a
                                                                cut (no fades) */
        for (i = 0; i < 2; i++)
            if ((pl_on[i] = in_play(&fighters[i]))) { pl_ch[i] = char_index(fighters[i].ch); pl_set[i] = fighters[i].set; }
        if (unlock_k) unlock_start(unlock_k - 1);
        else if (camp + 1 >= GS_COUNT) ending_start();
        else stage_begin(camp + 1, 0);
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
        used = &bm_chars[c] == fighters[0].ch || char_locked(c);
        for (i = 2; i < NF && !used; i++) used = fighters[i].state != S_OFF && fighters[i].ch == &bm_chars[c];
        if (!used) break;
    }
    fighter_init(&fighters[1], &bm_chars[c < BC_COUNT ? c : 1], 1, 16 + MAX_PALS, 0, cam_x + 40, 20);
    fighters[1].idx = 1; fighter_revive(&fighters[1]); lives[1] = 2; BIOS_PLAYER_MOD[1] = 1;
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
    centre(10, "GAME OVER");
    { char t[] = "STAGE  "; t[6] = '1' + camp; centre(13, t); }
    snd_music(GAME_MUS_OVER);
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
    if (!cont_t[0] && !cont_t[1]) { cont_box(0); cont_ov = 2; cont_ft = 0; snd_cmd(0x20); return; }   /* $20: stop */
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
static void lab_place(void) {
    fighter_t *p = &fighters[0], *d = &fighters[LAB_DUMMY];
    fighter_init(p, p->ch, p->set, 16, 0, cam_x + 110, 34); p->idx = 0;
    fighter_init(d, d->ch, d->set, 16 + LAB_DUMMY * MAX_PALS, 1, cam_x + 190, 34); d->idx = LAB_DUMMY;
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
    fighters[0].target = &fighters[LAB_DUMMY];              /* the HUD shows it from the start */
}
static void lab_start(uint8_t kind) {
    uint8_t i, c = lab.fighter < BC_COUNT ? lab.fighter : 0, dm = lab.dummy < BC_COUNT ? lab.dummy : 1;
    attract = 0; opt_on = 0; banner_hide(); BIOS_USER_MODE = 2;
    pl_ch[0] = c; pl_set[0] = 0; pl_on[0] = 1; pl_on[1] = 0;
    stage_begin(0, 1);
    for (i = 1; i < NF; i++) fighters[i].state = S_OFF;
    lab.active = kind;
    if (kind == 2) { fighter_t *p = &fighters[0]; fighter_init(p, p->ch, p->set, 16, 0, cam_x + 110, 34); p->idx = 0; lab_enemy(); }
    else {
        enemy_init(LAB_DUMMY, dm, dm == c, 0, 34, 0, &genemies_rom[EN_MINION]);   /* life and power of a minion */
        lab_place();
    }
    lab.frame = 0; lab.nev = 0; lab_seen = 0; lab.combo_hits = 0; lab.combo_dmg = 0;
    lab_shown_hits = 0xFF; lab_shown_dmg = 0xFFFF;
    FIX_print(0, 26, "                                        ", 0); FIX_print(2, 26, kind == 2 ? "ENEMY TEST" : "CHAIN LAB", 0);
}
/* req 4 (the Brawler Lab's Stages tab, "play from here"): P1 alone (lab.fighter) in campaign stage lab.dummy as a new
 * game, the camera at wave lab.wave's lock point and that wave spawned (or the boss, past the last wave); a pack sent
 * with it is installed first (stage_begin is a safe point). From there the game is the normal campaign. */
static void lab_stage(void) {
    uint8_t w = lab.wave, i;
    attract = 0; opt_on = 0; banner_hide(); BIOS_USER_MODE = 2; lab.active = 0;
    pl_ch[0] = lab.fighter < BC_COUNT ? lab.fighter : 0; pl_set[0] = 0; pl_on[0] = 1; pl_on[1] = 0;
    stage_begin(lab.dummy < GS_COUNT ? lab.dummy : 0, 1);
    if (!w) return;
    if (w > gs->nwaves) w = gs->nwaves;
    wave = w; waves_cleared = w; cam_x = lock_x = lock_at(w < gs->nwaves ? gs->waves[w].lock : gs->boss_lock);
    fighters[0].x = FIX(cam_x + 60);
    if (w < gs->nwaves) spawn_wave();
    else { for (i = 2; i < NF; i++) fighters[i].state = S_OFF; boss_start(); }
}
static void lab_flow(void) {
    fighter_t *p = &fighters[0], *d = &fighters[LAB_DUMMY];
    if (!lab.p1_life) p->hp = LIFE;                           /* nobody hits P1 (lab.p1_life: its life left alone, the
                                                                 meter proofs); a dummy never dies */
    if (lab.active == 2) {                                    /* the enemy test: it fights; beaten, it comes again */
        if (d->state == S_DEAD && d->state_t > 60) lab_enemy();
        if (in_play(p) && (JOY_pressed(0) & JOY_START)) dbg_on ^= 1;
        bios_start = 0;
        return;
    }
    if (d->state == S_IDLE || d->state == S_WALK) { d->hp = LIFE; lab_recovered = 1; }
    else if (d->hp < 20) d->hp += 40;
    if (d->state == S_DEAD) { fighter_revive(d); d->inv = 0; }
    if (d->x < FIX(cam_x + 24)) d->x = FIX(cam_x + 24);       /* on screen: the camera does not follow it */
    if (d->x > FIX(cam_x + 296)) d->x = FIX(cam_x + 296);
    in[LAB_DUMMY] = (intent_t){ 0 };
    in[LAB_DUMMY].face = INT(p->x) < INT(d->x) ? -1 : 1;      /* standing: it turns to face P1 */
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
    if (in_play(p) && (JOY_pressed(0) & JOY_START)) dbg_on ^= 1;   /* the box viewer, as in a fight */
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
    FIX_clear(); arcade_line_reset();
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
static void ending_start(void) {
    show_start(4, pl_ch[0], pl_set[0], RGB8(8, 16, 40));
    centre(3, "CONGRATULATIONS!");
    centre(5, "ALL FIVE STAGES CLEARED");
    portrait(18, 7, pl_ch[0], 0);
    centre(24, "THANK YOU FOR PLAYING");
    snd_music(GAME_MUS_CLEAR);
}
static void show_tick(void) {
    uint16_t pr = JOY_pressed(0) | JOY_pressed(1);
    scr_t++;
    fighter_animate(&fighters[0]);
    if (scr_t < (mode == 3 ? 360 : mode == 5 ? 480 : 600) && !(scr_t >= 90 && (pr & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)))) return;
    if (mode >= 4) SYS_return();                             /* the ending, GAME OVER: back to the BIOS, which commits the MVS save
                                                                and shows the title (credits left) or the attract demo */
    else if (camp + 1 >= GS_COUNT) ending_start();
    else stage_begin(camp + 1, 0);
}
static void select_tick(void) {
    uint8_t a, p, s;
    sel_t++;
    if (sel_phase == SEL_CHOOSE) {
        if ((bios_start & 2) && cursor[1] == 0xFF) {         /* P2 joins: START with a credit (PLAYER_START) */
            for (s = SEL_NSLOT; s-- > 0 && !(selectable(s) && SEL_SLOT[s].y == SEL_SLOT[cursor[0]].y && s != cursor[0]); ) ;
            if (s >= SEL_NSLOT) for (s = SEL_NSLOT; s-- > 0 && !(selectable(s) && s != cursor[0]); ) ;
            cursor[1] = s < SEL_NSLOT ? s : cursor[0];       /* the last fighter (stick order) on P1's feet line, else the last */
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
                cursor[p] = s; snd_ssg(SSG_CURSOR);
                fighter_pals(actor(slot_act[was]), slot_look(was));
                fighter_pals(actor(slot_act[s]), 1);
                select_name();
            }
            if ((pr & (JOY_A | JOY_B | JOY_C | JOY_D)) && !(picked[p ^ 1] && cursor[p ^ 1] == cursor[p])) {
                pick_set[p] = (pr & JOY_A) ? 0 : (pr & JOY_B) ? 1 : (pr & JOY_C) ? 2 : 3;
                slot_show(cursor[p], pick_set[p]);
                fighter_play(actor(slot_act[cursor[p]]), BA_WIN);
                voice_play(actor(slot_act[cursor[p]])->ch, 0, VK_SELECT);   /* its select voice (KOF's intro line) */
                actor(slot_act[cursor[p]])->team = 0;       /* the line guard keeps the picked ones first */
                picked[p] = 1; snd_ssg(SSG_CONFIRM);
            }
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
            if (sel_t == 1) { f->facing = SEL_SLOT[s].x < 160 ? -1 : 1; fighter_play(f, BA_WALK_FWD); }
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
    for (a = 0; a < NA; a++) if (actor(a)->state != S_OFF) fighter_animate(actor(a));
    select_arrows();
}

void game_init(void) {
    uint16_t i;
    BANK_init();                                             /* P2 bank 0, its copy agrees (neo_bank.h) */
    coin_in();                                               /* the credits kept from before the power-on: no sound */
    gdata_init();                                            /* the game's tables (game.json) */
    routes_init();                                           /* the fighters' chain route trees (fighter.h) */
    specs_init();                                            /* their specials by role (fighter.h spec_tab) */
    voices_init();                                           /* their voices (fighter.h voice_tab) */
    save_load();                                             /* MVS: the BIOS restored the block (a fresh one: reset) */
    for (i = 0; i < 4; i++) TEXT_PAL[2 + i] = text_colours[i];   /* the font's colours (Kizuna's, TODO #182) */
    PAL_setPalette(0, TEXT_PAL);
    bd_set(stg->backdrop);
    for (i = 0; i < NA * SEL_COLS || i < FIGHT_SPRS; i++) cmd_push(VRAM_SCB2 + SPR_BASE + i, 0x0FFF);   /* full size, set once */
    for (i = 0; i < NA; i++) { block_placed[i] = blk_cols; block_spr[i] = slot_spr[i] = SPR_BASE + i * blk_cols; }   /* clear every block once */
    stage_init(STAGE);
    snd_cmd(0x07);                                           /* KOF98's driver: music unlock */
}

/* MVS protocol (sdk/boot/crt0.s): request 2 = attract demo, 3 = title (a coin went in) */
static void attract_start(void);
void game_enter(uint8_t request) {
    BIOS_USER_MODE = 1;                                      /* title / demo (game_init ran on request 0) */
    BANK_init();                                             /* the BIOS ran in between: the register and its copy agree */
    { uint8_t k; for (k = 0; k < 10; k++) TEXT_PAL[6 + k] = bar_colours[k];
      PAL_setPalette(0, TEXT_PAL);                           /* the BIOS's own screens overwrite palette 0 */
      for (k = 0; k < 4; k++) TEXT_PAL[2 + k] = hilite_colours[k];   /* 1: highlighted text (GO, OPTIONS, drama names) */
      PAL_setPalette(1, TEXT_PAL); for (k = 0; k < 4; k++) TEXT_PAL[2 + k] = text_colours[k];
      for (k = 6; k < 16; k++) { uint16_t c = bar_colours[k - 6];                        /* 4: the meter (red <-> blue) */
          TEXT_PAL[k] = (c & 0xA0F0) | ((c >> 8) & 0xF) | ((c & 0xF) << 8) | ((c >> 2) & 0x1000) | ((c << 2) & 0x4000); }
      PAL_setPalette(METER_PAL, TEXT_PAL);
      for (k = 0; k < 10; k++) TEXT_PAL[6 + k] = bar_colours[k]; }   /* fix palettes 2-3: the shown portraits (portrait()) */
    shadow_init();
    pj_measure();                                            /* the projectile blocks' widths (block_w) */
    dbg_init();
    snd_reset();                                             /* the BIOS reset the sound CPU before handing over */
    if (request == 3) title_start(); else attract_start();
    if (coin_in()) snd_ssg(SSG_COIN);                       /* the coin that ended the demo: after the song start */
    depth_sort();
    draw();
    vblank_flush();
}

void game_tick(void) {
    uint8_t i;
    prof_t = LINE();
    vblank_flush();                 /* we are in vblank: last tick's VRAM commands and backdrop go out now, tear-free (1 frame latency) */
    mark(P_FLUSH);
    SYS_kickWatchdog();
    snd_tick();
    i = coin_in();                                           /* KOF94's coin sound (TODO #199) */
    if (attract_leave()) { if (i) snd_ssg(SSG_COIN); depth_sort(); draw(); return; }   /* the coin after the title's
                                                             song start, as game_enter's */
    if (i) snd_ssg(SSG_COIN);
    lab_tick();
    if (!lab.active && !dr_on) arcade_line();
    if (sf_who && mode != 1) sf_reset();                     /* the fight left mid-flash: its sprites go */
    if (mode == 2) { title_tick(); if (mode == 2) return; }
    if (!mode) { select_tick(); depth_sort(); draw(); return; }
    if (mode >= 3) { show_tick(); if (mode >= 3) { depth_sort(); draw(); } return; }
    if (dr_on) { drama_tick(); depth_sort(); draw(); return; }   /* drama mode: the fight held, drawn as it stands */
    if (cont_ov) { cont_tick(); if (mode == 1) { depth_sort(); draw(); hud(); } return; }   /* CONTINUE?: the fight frozen */
    if (ko_seq && !boss_ko_tick()) { depth_sort(); draw(); hud(); return; }   /* the boss's death: slow motion (#172) */
    if (attract) {                                           /* the demo: a coin, 30 s or a game over ends it */
        if (bios_demo_end || ++attract_t > ATTRACT_DEMO) { SYS_return(); }   /* (START or a credit: attract_leave) */
        ai_bot(fighters, NF, 0, &in[0]);
        if (!(attract_t & 31)) FIX_print(14, 13, (attract_t & 32) ? "           " : "INSERT COIN", 0);
    } else read_player(0, &in[0], &fighters[0]);
    if (p2_in()) read_player(1, &in[1], &fighters[1]);
#if !AI_OFF
    if (lab.active != 1) ai_update(fighters, NF, 2, in);   /* not against the Chain Lab's dummy */
#endif
    if (ko_seq || (!attract && !lab.active && phase >= PH_END))
        for (i = 0; i < NF; i++) { in[i].dx = in[i].dz = 0; in[i].press = in[i].hold = in[i].run = in[i].grab = 0; in[i].face = 0; in[i].blitz = in[i].chord = 0; }
                                                          /* the boss's death: nobody acts any more (#172); the stage
                                                             clear: the input off (#184) */
    mark(P_AI);
    close_marks();
    if (bighit_slow && --bighit_slow < BIGHIT_SLOW && (bighit_slow & 1)) { depth_sort(); draw(); hud(); return; }
                                                          /* SS2's big hit's slow motion: every other tick held */
    for (i = 0; i < NF; i++)                                 /* a super flash: only its attacker moves */
        if (win_posing(i)) fighter_pose_tick(&fighters[i]);  /* the stage clear's win pose (#184) */
        else if (fighters[i].state != S_OFF && (!sf_who || sf_who == &fighters[i])) fighter_update(&fighters[i], &in[i]);
    if (!attract && !lab.active && phase == PH_CLEAR) win_tick();
    if (!sf_who) { if (lab.active) lab_flow(); else flow(); }
    if (mode != 1) return;                                   /* back on the title screen */
    if (dr_on) { depth_sort(); draw(); return; }             /* a scene starts: held from this tick, no HUD */
    if (!sf_who) { camera(); wall_update(order, nf, cam_x); projectiles_update(cam_x, 0); }
    else projectiles_update(cam_x, 0x100 | sf_frozen);   /* the flash: only its attacker's effects born in it
                                                                (KOF98: P1 runs at the flash's priority $5001 and so do the
                                                                objects it spawns, $5D1C; the rest hold: Kyo's hand fire, #202) */
    mark(P_UPDATE);
    combat(order, nf, sf_who);                               /* a super flash: its attacker's own boxes only */
    if (!ko_seq && phase == PH_BOSS && !attract && !lab.active && fighters[BOSS_IDX].state != S_OFF && fighters[BOSS_IDX].hp <= 0)
        boss_ko_start();                                     /* its killing hit: the death sequence (#172) */
    if (!sf_who) wall_update(order, nf, cam_x);              /* (again: a catch / a hit this frame placed its victim) */
    mark(P_COMBAT);
    depth_sort();
    mark(P_SORT);
    draw();
    mark(P_PLACE);
    hud();
    mark(P_HUD);
    sf_tick();
}
