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
#include "hud.h"
#include "game_tables.h"
#include "portraits_big.h"

static uint16_t TEXT_PAL[16] = { 0x8000, COLOR_WHITE, RGB(20, 25, 31), RGB(31, 31, 0), RGB(31, 6, 4), RGB(6, 6, 10) };   /* 6-15: life bar (hud.h) */
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
#define NA 19                        /* sprite blocks: NE in a fight, NA actors on the select screen (a block per roster
                                        fighter: the group photo) */
#define SEL_COLS 16                  /* sprites per block on the select screen (MAX_COLS in a fight): NA blocks of 16 =
                                        sprites 60-363 there (the banner's, the debug boxes' and the sparks' 300-379 are
                                        not in use on that screen); the watch / win poses and the walk-offs are narrower
                                        (2026-10-05: widest 13, a walk; win 11, watch 8) */
uint8_t blk_cols = MAX_COLS;         /* sprites per block now (draw.s fighter_tiles clips a frame to it) */
#define SPR_BASE 60                  /* fighter blocks (stage 22-42, shadows 43-54 behind them; 1-21 free) */
static fighter_t fighters[NF];
static fighter_t *order[NA];                     /* back (small Z) to front, the nf entities in play */
static uint8_t nf;                               /* entities in play: the previews on the select screen, NE in the fight */
static uint8_t mode;                             /* 0 select, 1 fight, 2 title, 3 BOSS UNLOCKED, 4 the ending, 5 GAME OVER */
static uint8_t attract;                          /* the fight is the attract demo: P1 is ai_bot, enemies their attract_ai */
static uint16_t attract_t;
static uint8_t tap_t[2], tap_dir[2];             /* double-tap run detection per player */
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
static uint8_t shown_level, shown_credits;               /* 0 / 0xFF after a FIX_clear: rewrite */
static void arcade_line_reset(void) { shown_level = 0; shown_credits = 0xFF; }
static void arcade_line(void) {                               /* bottom line, every screen; writes only changes */
    uint8_t l = level(), c = CREDITS_P1;
    char t[3];
    if (l != shown_level) {
        FIX_print(8, 27, "V" GAME_VERSION, 0);                /* the build (VERSION), left of the level */
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

static void stage_pals(void) {                               /* the stage's palettes */
    uint8_t p;
    for (p = 0; p < stg->npal; p++) PAL_setPalette(STAGE_PAL + p, stg->pal + p * 16);
}
static uint8_t bd_on, bd_t;                      /* screen_fx: the stage hidden for a special's effect; its frames */
static const uint16_t *bd_cols;                  /* its two colours */
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
    bd_on = 0;
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
        uint8_t m = 0;
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
        pj_cols[i] = m > MAX_COLS ? MAX_COLS : m;
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
static void depth_sort(void) {
    uint8_t i, j;
    for (i = 1; i < nf; i++)
        for (j = i; j > 0 && (order[j]->z < order[j - 1]->z ||
                              (order[j]->z == order[j - 1]->z && order[j]->zfront < order[j - 1]->zfront)); j--) {
            fighter_t *t = order[j]; order[j] = order[j - 1]; order[j - 1] = t;
        }
    blocks_layout(nf > NE ? SEL_COLS : MAX_COLS);
    if (blk_cols == MAX_COLS) {                  /* the pool's widths: in use = its thrower's widest, within PJ_SPRS */
        uint8_t used = 0;
        for (i = 0; i < NPJ; i++) {
            const fighter_t *p = &projectiles[i];
            uint8_t w = p->state == S_OFF ? 0 : pj_cols[p->ch->id];
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

/* ---- per-line sprite guard: the LSPC shows at most 96 sprites on a line and drops the highest-numbered ones, i.e. the
 * fighters in front. All fighters are counted as sharing the same lines (standing bodies all cover y 100-150; counting
 * per band cost 2k cycles a fighter): the stage plane's 21 + every shown fighter's columns stay <= 96, and a fighter that
 * would go past is hidden this frame.
 * Priority: players, then enemies front to back, reversed every other frame so the dropped ones flicker in turn.
 * Conservative only when fighters are vertically apart (high jump vs lying down). ---- */
#define LINE_MAX 96
#define SH_RESERVE NE                    /* sprites per line kept for the ground shadows (half of NE entities x 2) */
#define SPARK_RESERVE 6                  /* and for hit sparks (two 3-column sparks on one line) */
static uint8_t hidden[NA], guard_hidden;
static uint8_t dr_cols;                  /* the drama portrait's sprites on screen (main.c "drama mode"): kept per line */
static uint8_t guard_parity, shadow_parity;   /* the frame alternations (line_guard's team order, shadows' halves): set
                                            at a stage's start (stage_begin), not left by whatever ran before (regress bleed) */
static void line_guard(void) {
    uint8_t prio[NA], n = 0, i, k, used = mode == 1 ? BG_N + SH_RESERVE + SPARK_RESERVE + dr_cols : 0;   /* the select: actors only */
    for (i = 0; i < nf; i++) if (!order[i]->team) prio[n++] = i;
    guard_parity ^= 1;
    for (i = 0; i < nf; i++) {
        uint8_t j = guard_parity ? nf - 1 - i : i;                 /* order[] is back to front */
        if (order[j]->team) prio[n++] = j;
    }
    guard_hidden = 0;
    for (k = 0; k < nf; k++) {
        fighter_t *f = order[prio[k]];
        int16_t sx = INT(f->x) - cam_x;
        uint8_t cols;
        if (f->state == S_OFF || (f->state == S_PROJ && f->frame_ovr == 0xFFFF) ||
            (f->state == S_DEAD && (f->state_t & 4)) || !block_w(f)) { hidden[prio[k]] = 1; continue; }   /* the dead
                                                             blink; a pool entity without a block (no room) */
        if (sx < -128 || sx > 448) { hidden[prio[k]] = 1; continue; }   /* well off screen: placed, its 9-bit X would
                                                             wrap it onto the screen (a wave walking in from 512 px) */
        if (floor_top + INT(f->z) - INT(f->y) < 0) { hidden[prio[k]] = 1; continue; }   /* feet above the screen's top
                                                             (Kim's Phoenix flies out): its 9-bit Y would wrap it onto the screen */
        cols = f->ncols;
        if (used + cols > LINE_MAX) { hidden[prio[k]] = 1; guard_hidden++; }
        else { hidden[prio[k]] = 0; used += cols; }
    }
}

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
        if (mode != 1 || i >= nf || hidden[i] || f->state == S_OFF ||
            (f->state == S_PROJ && f->frame_ovr == 0xFFFF)) { y[0] = y[1] = x[0] = x[1] = 0; continue; }
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
 * read from its KOF animation's $FA command), else gflash.dx / dy. The concentration's frames start a frame after the
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
static int16_t sf_dx, sf_dy;
static const uint16_t SF_BD[2] = { 0x0000, 0x0000 };    /* the backdrop it leaves: black (screen_fx restores the stage's) */
void super_flash(fighter_t *f) {
    const bspec_t *sp = &f->ch->specials[f->spec_ix];
    if (mode != 1) return;
    sf_who = f; sf_flash_t = 0; sf_glow_on = 0; sf_ray = 0xFF;
    sf_col = f->ch->fury_max < f->ch->nspec && f->spec_ix == f->ch->fury_max;   /* MAX: orange */
    if (sp->sf_anchor) { sf_dx = sp->sf_dx; sf_dy = sp->sf_dy; } else { sf_dx = gflash.dx; sf_dy = gflash.dy; }
    PAL_setPalette(SF_RAYS_PAL, sf_ray_pal[sf_col]);
    snd_sfx(gflash.sound);                                   /* KOF98's charge sound ($370F0 -> $3906E: index $99 =
                                                                $1A $3A, DM and SDM alike) */
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
        if (f->state == S_OFF || hidden[i] || (f->state == S_PROJ && f->frame_ovr == 0xFFFF)) continue;
        st = fighter_step(f);
        if (f->state != S_PROJ && (st->flags & 2) && nh < DBG_BOXES) { dbg_box(y + nh * 4, x + nh * 4, f, &st->hurt); nh++; }
        if ((f->state == S_ATTACK || f->state == S_AIR_ATTACK) && (st->flags & 1)) atk = &st->atk;
        else if ((f->state == S_SPECIAL || f->state == S_PROJ) && f->spec_atk) atk = f->spec_atk;
        if (atk && na < DBG_BOXES) { dbg_box(y + DBG_BOXES * 4 + na * 4, x + DBG_BOXES * 4 + na * 4, f, atk); na++; }
    }
}

/* a special's screen effect (bspec_t.bd_*, Kizuna's Phoenix): while a fighter's special shows a row in [bd_first,
 * bd_end) the stage is hidden and the backdrop alternates bd_col[0] / bd_col[1] every frame (Kizuna $1FC46: $27E6 /
 * $27E4 by bit 0 of its counter $27E1); after, the stage and its backdrop come back */
static void screen_fx(void) {
    uint8_t i;
    const bspec_t *sp = 0;
    for (i = 0; i < nf && !sp; i++) {
        const fighter_t *f = &fighters[i];
        if (f->state == S_SPECIAL && f->srow) {
            const bspec_t *s = &f->ch->specials[f->spec_ix];
            if (s->bd_end && f->srow - 1 >= s->bd_first && f->srow - 1 < s->bd_end) sp = s;
        }
    }
    if (sf_who) {                                            /* the super flash: the stage hidden, white then black */
        if (!bd_on) { stage_hide(); bd_on = 1; bd_t = 0; }       /* the stage's sprites go at the next vblank: the */
        else PAL_setBackdrop(sf_flash_t <= gflash.white ? gflash.white_col : gflash.dark_col);   /* backdrop (at once) from the frame after */
        bd_cols = SF_BD;
    } else if (sp) {                                         /* the stage's sprites go at the next vblank (cmd */
        if (!bd_on) { stage_hide(); bd_on = 1; bd_t = 0; }       /* queue): the strobe starts the frame after, */
        else PAL_setBackdrop(sp->bd_col[bd_t++ & 1]);            /* bd_col[0] first as Kizuna (measured) */
        bd_cols = sp->bd_col;
    } else if (bd_on == 1) { stage_show(); PAL_setBackdrop(bd_cols[bd_t & 1]); bd_on = 2; }   /* back the same way: the stage first, */
    else if (bd_on == 2) { PAL_setBackdrop(stg->backdrop); bd_on = 0; }   /* its backdrop the frame after */
}

static void draw(void) {
    uint8_t i;
    if (mode == 1) { screen_fx(); stage_draw(); }            /* only the fight has a stage */
    for (i = 0; i < nf; i++)
        if (order[i]->state != S_OFF && !(order[i]->state == S_PROJ && order[i]->frame_ovr == 0xFFFF) && block_w(order[i])) {
            uint8_t bc = blk_cols;
            blk_cols = block_w(order[i]); fighter_tiles(order[i]); blk_cols = bc;   /* clipped to its block */
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
            if (vis) fighter_place(f, y, x, cam_x, m);
            else { uint8_t c; for (c = 0; c < m; c++) y[c] = x[c] = 0; }
        }
        block_placed[i] = n; block_spr[i] = spr;
    }
    shadows();
    sparks_draw();
    if (mode == 1) sf_draw();
    dbg_draw();
}

static intent_t in[NF];                          /* this frame's intent per fighter (player pad or AI) */
static void inputs_reset(void) {                 /* a select / fight starts: nothing of the demo or the last game */
    uint8_t i;
    for (i = 0; i < NF; i++) in[i] = (intent_t){ 0 };
    for (i = 0; i < 2; i++) { tap_t[i] = 255; tap_dir[i] = 0; }
}
static void close_marks(void) {                 /* intent.close: an opponent within CLOSE_X (A takes a route's close link) */
    uint8_t i, j;
    for (i = 0; i < NF; i++) {
        const fighter_t *f = &fighters[i];
        in[i].close = 0;
        if (f->state == S_OFF) continue;
        for (j = 0; j < NF; j++) {
            const fighter_t *o = &fighters[j];
            int16_t dx = INT(o->x) - INT(f->x), dz = INT(o->z) - INT(f->z);
            if (o->team == f->team || o->state == S_OFF || o->state == S_DEAD) continue;
            if (dx >= -CLOSE_X && dx <= CLOSE_X && dz >= -Z_HIT && dz <= Z_HIT) { in[i].close = 1; break; }
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
 * 5 / 6 P1's / P2's special meter (TODO #71: row 3 under the name, 8 cells, the life bar's glyphs in METER_PAL) */
#define METER_CELLS 8
#define METER_PAL 4                      /* fix palette 4: palette 0 with the bar colours' red and blue swapped */
static bar_t bars[7];
static uint8_t boss_shown;
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
    static const uint8_t COL[7] = { 5, 20, 5, 20, 5, 5, 35 - METER_CELLS }, ROW[7] = { 0, 0, 4, 4, 7, 3, 3 };
    uint8_t p, c;
    for (p = 0; p < 7; p++) {
        bars[p].col = COL[p]; bars[p].row = ROW[p]; bars[p].mirror = (p & 1 && p < 4) || p == 6; bars[p].px = bars[p].trail = -1; bars[p].wait = 0;
        bars[p].n = p < 4 ? BAR_CELLS : p == 4 ? BOSS_CELLS : METER_CELLS; bars[p].pal = p >= 5 ? METER_PAL : 0;
        if (p < 4) hud_tgt[p] = 0;
        for (c = 0; c < BOSS_CELLS; c++) bars[p].cell[c] = 0;
    }
    boss_shown = 0;
    for (p = 0; p < 2; p++) { hud_lives[p] = -1; hud_cont[p] = 0xFFFF; hud_face[p] = 0xFE; }
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
    }
    for (p = 0; p < 1 + two; p++) {                          /* the players' blocks: P1 left, P2 right */
        fighter_t *f = &fighters[p];
        uint8_t face = char_index(f->ch), pc = p ? 35 : 1, lc = p ? 32 : 5, cc = p ? 20 : 9;   /* lives / continue cols */
        if (hud_face[p] != face) { hud_face[p] = face; portrait(pc, 0, face, p); hud_name(p, 1, f->ch->name); }
        bar_draw(&bars[p], in_play(f) ? f->hp : 0, f->hp_max);
        bar_draw(&bars[5 + p], in_play(f) ? (int16_t)f->meter : 0, (int16_t)gmeter.max);   /* the special meter */
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
static uint8_t char_locked(uint8_t c) { uint8_t k = roster_unlock[c]; return k && !(save.unlocked >> (k - 1) & 1); }
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
    PAL_setBackdrop(COLOR_BLACK);
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
 * dark silhouette, not selectable; once beaten it is in colour / grey like the others). Each fighter holds its 'watch'
 * pose (export_bm.WATCH: a front-facing frame from its intros / win poses), turned toward the middle. The places are
 * slots (SEL_SLOT: x, z, row), independent of who stands in them (sel_fighter: the fighter of each slot), so moving
 * someone on screen is a change to game.json's select slots only. The cursor's fighter shows its colours, the others shades of grey
 * (their own palettes in luminance). "1P" / "2P" with an arrow above the selected head (fix layer). Stick left / right
 * moves within a row, up / down to the row behind / in front (the nearest fighter in x); A/B/C/D picks that colour set
 * (KOF style) and plays the win pose. P2 joins here with START (a credit) and picks too; the two can't pick the same
 * fighter. When everyone in has picked, the others walk off the screen outward, then the
 * fight cuts in (no fades: a palette fade cost ticks frames). Each fighter on screen is an entity (actor): the fight's NE entities + NA - NE more. ---- */
#define SEL_BACK 2                       /* the bosses' row */
#define SHOW_Z 40                        /* BOSS UNLOCKED / ending: feet at SELECT_FLOOR + SHOW_Z */
_Static_assert(BC_COUNT <= SEL_NSLOT && BC_COUNT <= NA, "group photo: a slot and an actor per fighter");
_Static_assert(SPR_BASE + FIGHT_SPRS <= 300 && SPR_BASE + NA * SEL_COLS <= 364, "sprite blocks: fight below the banner, select below the sparks");
/* the slots (game.json "select", gamedata.h sel_slot_t): x (px), z (feet at SELECT_FLOOR + z), row (0 front: low on the
 * screen, drawn in front; 2 back, SEL_BACK: higher, behind); sel_fighter[slot] = who stands there (the generator checks
 * every roster fighter has one). Today: front rows 48 px apart inside x 16-304 (the 304 px a TV shows; the watch poses
 * are 40-80 px wide: shoulders overlap, as in a photo), the middle row between the front row's fighters, the bosses in
 * stage order on the back row, spread wider. */
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

static uint16_t col_grey(uint16_t c) {                      /* luminance (5 R + 9 G + 2 B) / 16, a cold grey */
    uint8_t r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
    uint8_t l = (uint8_t)((r * 5 + g * 9 + b * 2) >> 4);
    return RGB(l, l, l + (l < 31));
}
#define SILHOUETTE RGB(4, 4, 5)
/* an entity's palettes: its own colours (1), greys (0) or a silhouette (2) */
static void fighter_pals(const fighter_t *f, uint8_t colour) {
    uint16_t buf[16];
    uint8_t i, j;
    for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) {
        const uint16_t *src = fighter_src_pal(f, i);
        buf[0] = src[0];
        for (j = 1; j < 16; j++)
            buf[j] = colour == 2 ? SILHOUETTE : colour ? fighter_colour(f, src[j]) : col_grey(src[j]);
        PAL_setPalette(f->palbase + i, buf);
    }
}
static uint8_t chosen(uint8_t s) { return s == cursor[0] || s == cursor[1]; }
static uint8_t slot_look(uint8_t s) { return char_locked(slot_ch[s]) ? 2 : chosen(s); }
static void slot_show(uint8_t s, uint8_t set) {             /* (re)binds slot s's actor: its fighter, colour set, pose */
    uint8_t a = slot_act[s];
    fighter_t *f = actor(a);
    const bchar_t *ch = &bm_chars[slot_ch[s]];
    fighter_init(f, ch, set < ch->nsets ? set : 0, 16 + a * MAX_PALS, 1, SEL_SLOT[s].x, SEL_SLOT[s].z);
    f->idx = a; f->facing = SEL_SLOT[s].x < 160 ? 1 : -1;   /* turned toward the middle */
    fighter_play(f, BA_WATCH);
    fighter_pals(f, slot_look(s));
}
/* the cursor from slot s: left / right = the nearest selectable slot that way in its row; up / down = the row behind /
 * in front (further if that row has nobody selectable), the selectable slot nearest in x */
static uint8_t sel_move(uint8_t s, uint16_t pr) {
    int8_t dx = (pr & JOY_RIGHT) ? 1 : (pr & JOY_LEFT) ? -1 : 0, dr = (pr & JOY_UP) ? 1 : (pr & JOY_DOWN) ? -1 : 0;
    int8_t row = SEL_SLOT[s].row;
    uint8_t t, best = 0xFF;
    int16_t bd = 0x7FFF, d;
    if (dx) {
        for (t = 0; t < SEL_NSLOT; t++) {
            if (!selectable(t) || SEL_SLOT[t].row != row) continue;
            d = (SEL_SLOT[t].x - SEL_SLOT[s].x) * dx;
            if (d > 0 && d < bd) { bd = d; best = t; }
        }
    } else if (dr) {
        for (row += dr; row >= 0 && row <= SEL_BACK && best == 0xFF; row += dr)
            for (t = 0; t < SEL_NSLOT; t++) {
                if (!selectable(t) || SEL_SLOT[t].row != row) continue;
                d = SEL_SLOT[t].x - SEL_SLOT[s].x; if (d < 0) d = -d;
                if (d < bd) { bd = d; best = t; }
            }
    }
    return best == 0xFF ? s : best;
}
static void select_arrows(void) {                           /* "1P" / "2P" + arrow over the selected head */
    uint8_t p, col[2], row[2];
    for (p = 0; p < 2; p++) {
        uint8_t s = cursor[p];
        col[p] = 0xFF; row[p] = 0;
        if (s != 0xFF) {
            int16_t sx = SEL_SLOT[s].x - 8 + (p && cursor[0] == s ? 16 : 0);   /* both on one fighter: 2P to the right */
            col[p] = sx < 0 ? 0 : (uint8_t)(sx >> 3);
            row[p] = (uint8_t)((SELECT_FLOOR + SEL_SLOT[s].z - 120) >> 3);   /* FIX_print row r is screen y r * 8:
                                                                 the arrow ends 120 px above the feet (tallest head) */
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
    PAL_setBackdrop(RGB8(72, 76, 84));                       /* the photo's wall */
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
    e->idx = slot; e->power = power + en->power; e->tint = tint;
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
    for (l = 0; l < n; l++) dr_put((sc->side ? 37 - n : 3) + l, 21, name[l], 1);   /* the name plate, yellow */
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
static void triggers_reset(void) { trig_fired = 0; stage_tk = wave_t = 0; wave_on = 0; waves_cleared = 0; trig_held = 0; tq_n = 0; }
static void enemies_down(fighter_t *by) {        /* every enemy still up goes down (a boss beaten, TA_END) */
    uint8_t i;
    for (i = 2; i < NF; i++) {
        fighter_t *e = &fighters[i];
        if (e == by || e->state == S_OFF || e->state == S_DEAD || e->hp <= 0) continue;
        if (e->state == S_THROWN || e->state == S_DOWN || e->state == S_GETUP) { e->hp = 0; continue; }
        e->hp = 0; fighter_hit(by, e, 0, R_KNOCKDOWN, 0);
    }
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
    phase = PH_BOSS; phase_t = 0;
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
static void go_sign(uint8_t on) { FIX_print(29, 3, on ? "GO -->" : "      ", 1); }   /* yellow, in the HUD's black band */
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
    FIX_clear(); arcade_line_reset();
    stage_init(attract ? STAGE : gs->bg);             /* stage sprites back, every column rewritten */
    PAL_setBackdrop(stg->backdrop);
    lock_x = lock_at(gs->waves[0].lock);
    power = gs->power;
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
    PAL_setBackdrop(COLOR_BLACK);
    stage_hide();
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    title_screen();
    bios_start = 0;
    snd_music(GAME_MUS_SELECT);
    attract = 2; attract_t = 0;
}
static void attract_logo_tick(void) {
    if (bios_start) { BIOS_USER_MODE = 1; attract = 0; title_start(); title_paid = 1; return; }   /* as in the demo */
    if (bios_demo_end) { SYS_return(); return; }
    if (!title_t) banner_show((320 - BANNER_COLS * 16) / 2, 56);   /* again: power-on's first draw clears every block's
                                                             sprites once (game_init), the banner's 300-379 among them */
    if (!(title_t & 31)) FIX_print(14, 18, (title_t & 32) ? "           " : "INSERT COIN", 0);
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
    if (mode != 1 || cont_ov == 2 || phase >= PH_END) return 0;
    return flags & ((in_play(&fighters[0]) ? 0 : 1) | (in_play(&fighters[1]) ? 0 : 2));
}
static void unlock_start(uint8_t k);
static void ending_start(void);
static void campaign(uint8_t left) {
    uint8_t i;
    phase_t++;
    if (!attract) {
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
    case PH_BOSS:
        if (fighters[BOSS_IDX].state != S_DEAD && fighters[BOSS_IDX].state != S_OFF) break;
        enemies_down(&fighters[BOSS_IDX]);                   /* boss beaten: the minions go down with it */
        tq_n = 0; waves_cleared = gs->nwaves + 1;
        phase = PH_END; phase_t = 0;
        break;
    case PH_END:                                             /* every enemy gone: STAGE CLEAR, the save */
        if (left) break;
        FIX_print(14, 13, "STAGE CLEAR", 0); snd_music(GAME_MUS_CLEAR);
        phase = PH_CLEAR; phase_t = 0; unlock_k = 0;
        if (attract) break;
        if (camp + 1 < GS_COUNT && save.furthest < camp + 1) save.furthest = camp + 1;
        if (gs->unlock && !(save.unlocked >> camp & 1)) { save.unlocked |= 1 << camp; unlock_k = camp + 1; }
        save_write();
        break;
    case PH_CLEAR:
        if (phase_t < 200) break;                            /* then the next screen: a cut (no fades) */
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
static void cont_player(uint8_t p) {             /* one player: START continues (or rejoins), the count, A-D */
    fighter_t *f = &fighters[p];
    if (p && !p2_in()) return;
    if (!in_play(f) && (bios_start & (1 << p))) {            /* where he fell, inside the screen */
        int16_t x = INT(f->x);
        if (x < cam_x + 24) x = cam_x + 24;
        if (x > cam_x + 296) x = cam_x + 296;
        f->x = FIX(x);
        cont_t[p] = 0; lives[p] = 3; BIOS_PLAYER_MOD[p] = 1;
        fighter_revive(f);
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
        if (e->state == S_DEAD && e->state_t > 60) e->state = S_OFF;      /* blinked out */
        if (e->state != S_OFF) left++;
    }
    if (!attract && in_play(&fighters[0]) && (JOY_pressed(0) & JOY_START)) dbg_on ^= 1;   /* box viewer: P1 START in play
                                                             (P2 START joins; a START that continues isn't in play yet) */
    if ((bios_start & 2) && !attract && !p2_in()) p2_join();
    for (p = 0; p < 2; p++) {
        fighter_t *f = &fighters[p];
        if (f->state == S_DEAD) {
            if (lives[p]) { lives[p]--; fighter_revive(f); }
            else if (attract) SYS_return();                  /* the demo's bot: no continue */
            else { f->state = S_OFF; cont_t[p] = CONTINUE; BIOS_PLAYER_MOD[p] = 2; }
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
    p->hp = LIFE;                                             /* nobody hits P1; a dummy never dies */
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
    if (lab.load >= 3) {                                      /* a data pack (3) or the ROM's tables (4): at the safe point */
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
    PAL_setBackdrop(wall);
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    fighter_init(&fighters[0], &bm_chars[c], set, 16, 0, 160, SHOW_Z);
    fighters[0].idx = 0; fighters[0].facing = 1;
    fighter_play(&fighters[0], BA_WIN_A);
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
            for (s = SEL_NSLOT; s-- > 0 && !(selectable(s) && SEL_SLOT[s].row == SEL_SLOT[cursor[0]].row && s != cursor[0]); ) ;
            cursor[1] = s < SEL_NSLOT ? s : cursor[0];       /* the last fighter of P1's row */
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
                fighter_play(actor(slot_act[cursor[p]]), BA_WIN_A);
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
    gdata_init();                                            /* the game's tables (game.json) */
    routes_init();                                           /* the fighters' chain route trees (fighter.h) */
    specs_init();                                            /* their specials by role (fighter.h spec_tab) */
    voices_init();                                           /* their voices (fighter.h voice_tab) */
    save_load();                                             /* MVS: the BIOS restored the block (a fresh one: reset) */
    PAL_setPalette(0, TEXT_PAL);
    PAL_setBackdrop(stg->backdrop);
    for (i = 0; i < NA * SEL_COLS || i < FIGHT_SPRS; i++) cmd_push(VRAM_SCB2 + SPR_BASE + i, 0x0FFF);   /* full size, set once */
    for (i = 0; i < NA; i++) { block_placed[i] = blk_cols; block_spr[i] = slot_spr[i] = SPR_BASE + i * blk_cols; }   /* clear every block once */
    stage_init(STAGE);
    snd_cmd(0x07);                                           /* KOF98's driver: music unlock */
}

/* MVS protocol (sdk/boot/crt0.s): request 2 = attract demo, 3 = title (a coin went in) */
static void attract_start(void);
void game_enter(uint8_t request) {
    BIOS_USER_MODE = 1;                                      /* title / demo (game_init ran on request 0) */
    { uint8_t k; for (k = 0; k < 10; k++) TEXT_PAL[6 + k] = bar_colours[k];
      PAL_setPalette(0, TEXT_PAL);                           /* the BIOS's own screens overwrite palette 0 */
      TEXT_PAL[1] = RGB(31, 28, 0); PAL_setPalette(1, TEXT_PAL); TEXT_PAL[1] = COLOR_WHITE;   /* 1: yellow text (GO); */
      for (k = 6; k < 16; k++) { uint16_t c = bar_colours[k - 6];                        /* 4: the meter (red <-> blue) */
          TEXT_PAL[k] = (c & 0xA0F0) | ((c >> 8) & 0xF) | ((c & 0xF) << 8) | ((c >> 2) & 0x1000) | ((c << 2) & 0x4000); }
      PAL_setPalette(METER_PAL, TEXT_PAL);
      for (k = 0; k < 10; k++) TEXT_PAL[6 + k] = bar_colours[k]; }   /* fix palettes 2-3: the shown portraits (portrait()) */
    shadow_init();
    pj_measure();                                            /* the projectile blocks' widths (block_w) */
    dbg_init();
    snd_reset();                                             /* the BIOS reset the sound CPU before handing over */
    if (request == 3) title_start(); else attract_start();
    depth_sort();
    draw();
    SYS_vblankFlush();
}

void game_tick(void) {
    uint8_t i;
    prof_t = LINE();
    SYS_vblankFlush();              /* we are in vblank: last tick's VRAM commands go out now, tear-free (1 frame latency) */
    mark(P_FLUSH);
    SYS_kickWatchdog();
    snd_tick();
    lab_tick();
    if (!lab.active && !dr_on) arcade_line();
    if (sf_who && mode != 1) sf_reset();                     /* the fight left mid-flash: its sprites go */
    if (mode == 2) { title_tick(); if (mode == 2) return; }
    if (!mode) { select_tick(); depth_sort(); draw(); return; }
    if (mode >= 3) { show_tick(); if (mode >= 3) { depth_sort(); draw(); } return; }
    if (dr_on) { drama_tick(); depth_sort(); draw(); return; }   /* drama mode: the fight held, drawn as it stands */
    if (cont_ov) { cont_tick(); if (mode == 1) { depth_sort(); draw(); hud(); } return; }   /* CONTINUE?: the fight frozen */
    if (attract) {                                           /* the demo: a coin, 30 s or a game over ends it */
        if (bios_demo_end || ++attract_t > ATTRACT_DEMO) { SYS_return(); }
        if (bios_start) { BIOS_USER_MODE = 1; attract = 0; title_start(); title_paid = 1; depth_sort(); draw(); return; }
                                                          /* START in the demo (AES: no coin; MVS: the BIOS took the
                                                             credit): the title, NEW GAME / CONTINUE confirmed with
                                                             START or A, no second credit (2026-10-05: on SNK's MVS BIOS
                                                             the title waited for another coin) */
        ai_bot(fighters, NF, 0, &in[0]);
        if (!(attract_t & 31)) FIX_print(14, 13, (attract_t & 32) ? "           " : "INSERT COIN", 0);
    } else read_player(0, &in[0], &fighters[0]);
    if (p2_in()) read_player(1, &in[1], &fighters[1]);
#if !AI_OFF
    if (lab.active != 1) ai_update(fighters, NF, 2, in);   /* not against the Chain Lab's dummy */
#endif
    mark(P_AI);
    close_marks();
    for (i = 0; i < NF; i++)                                 /* a super flash: only its attacker moves */
        if (fighters[i].state != S_OFF && (!sf_who || sf_who == &fighters[i])) fighter_update(&fighters[i], &in[i]);
    if (!sf_who) { if (lab.active) lab_flow(); else flow(); }
    if (mode != 1) return;                                   /* back on the title screen */
    if (dr_on) { depth_sort(); draw(); return; }             /* a scene starts: held from this tick, no HUD */
    if (!sf_who) { camera(); dance_update(order, nf, cam_x); projectiles_update(cam_x); }
    mark(P_UPDATE);
    combat(order, nf, sf_who);                               /* a super flash: its attacker's own boxes only */
    mark(P_COMBAT);
    depth_sort();
    mark(P_SORT);
    draw();
    mark(P_PLACE);
    hud();
    mark(P_HUD);
    sf_tick();
}
