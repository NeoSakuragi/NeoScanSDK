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
#include "hud.h"

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
#define SPR_BASE 60                  /* fighter blocks (stage 22-42, shadows 43-54 behind them; 1-21 free) */
static fighter_t fighters[NF];
static fighter_t *order[NE];                     /* back (small Z) to front, the nf entities in play */
static uint8_t nf;                               /* entities in play: the previews on the select screen, NE in the fight */
static uint8_t mode;                             /* 0 select, 1 fight, 2 title, 3 BOSS UNLOCKED, 4 the ending */
static uint8_t attract;                          /* the fight is the attract demo: P1 is ai_bot, enemies ai_weak */
static uint16_t attract_t;
static uint8_t tap_t[2], tap_dir[2];             /* double-tap run detection per player */
static void fight_fade(void);
static void scene_pals(uint8_t k);
static uint8_t fade_k;                           /* the fade level last written (0xFF: none yet) */
enum { PH_WAVE, PH_GO, PH_BOSS, PH_END, PH_CLEAR, PH_FADE };   /* campaign phases (see "campaign") */
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
 * time, stage_init(n) at each stage start (the campaign's CAMP_STAGE; the attract demo: STAGE, make STAGE=n). One plane of 21 sprites (22-42), a
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

static uint16_t col_scale(uint16_t c, uint8_t k);
static void stage_pals(uint8_t k) {                          /* the stage's palettes at k / 16 brightness */
    uint16_t buf[16];
    uint8_t p, i;
    for (p = 0; p < stg->npal; p++) {
        const uint16_t *src = stg->pal + p * 16;
        for (i = 0; i < 16; i++) buf[i] = i ? col_scale(src[i], k) : src[0];
        PAL_setPalette(STAGE_PAL + p, buf);
    }
}
static void stage_hide(void) {                              /* title, select: no stage */
    uint8_t i;
    for (i = 0; i < BG_N; i++) cmd_push(VRAM_SCB3 + BG_SPR + i, 0);
}
static void stage_init(uint8_t n) {
    uint8_t s;
    stg = &stages[n]; floor_top = stg->floor_top; world_w = stg->cols << 4;
    stage_pals(16);
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
static void depth_sort(void) {
    uint8_t i, j;
    for (i = 1; i < nf; i++)
        for (j = i; j > 0 && (order[j]->z < order[j - 1]->z ||
                              (order[j]->z == order[j - 1]->z && order[j]->zfront < order[j - 1]->zfront)); j--) {
            fighter_t *t = order[j]; order[j] = order[j - 1]; order[j - 1] = t;
        }
    for (i = 0; i < nf; i++)
        if (order[i]->spr != SPR_BASE + i * MAX_COLS) { order[i]->spr = SPR_BASE + i * MAX_COLS; order[i]->shown_frame = 0xFFFF; }
}

/* ---- per-line sprite guard: the LSPC shows at most 96 sprites on a line and drops the highest-numbered ones, i.e. the
 * fighters in front. All fighters are counted as sharing the same lines (standing bodies all cover y 100-150; counting
 * per band cost 2k cycles a fighter): the stage plane's 21 + every shown fighter's columns stay <= 96, and a fighter that
 * would go past is hidden this frame.
 * Priority: players, then enemies front to back, reversed every other frame so the dropped ones flicker in turn.
 * Conservative only when fighters are vertically apart (high jump vs lying down). ---- */
#define LINE_MAX 96
#define SH_RESERVE 12                    /* sprites per line kept for the ground shadows (half of 12 entities x 2) */
#define SPARK_RESERVE 6                  /* and for hit sparks (two 3-column sparks on one line) */
static uint8_t hidden[NE], guard_hidden;
static void line_guard(void) {
    static uint8_t parity;
    uint8_t prio[NE], n = 0, i, k, used = BG_N + SH_RESERVE + SPARK_RESERVE;
    for (i = 0; i < nf; i++) if (!order[i]->team) prio[n++] = i;
    parity ^= 1;
    for (i = 0; i < nf; i++) {
        uint8_t j = parity ? nf - 1 - i : i;                 /* order[] is back to front */
        if (order[j]->team) prio[n++] = j;
    }
    guard_hidden = 0;
    for (k = 0; k < nf; k++) {
        fighter_t *f = order[prio[k]];
        int16_t sx = INT(f->x) - cam_x;
        uint8_t cols;
        if (f->state == S_OFF || (f->state == S_PROJ && f->frame_ovr == 0xFFFF) ||
            (f->state == S_DEAD && (f->state_t & 4))) { hidden[prio[k]] = 1; continue; }   /* the dead blink */
        if (sx < -128 || sx > 448) { hidden[prio[k]] = 1; continue; }   /* well off screen: placed, its 9-bit X would
                                                             wrap it onto the screen (a wave walking in from 512 px) */
        cols = f->ncols;
        if (used + cols > LINE_MAX) { hidden[prio[k]] = 1; guard_hidden++; }
        else { hidden[prio[k]] = 0; used += cols; }
    }
}

/* draw: tiles for the frames that changed, then per entity block one SCB3 and one SCB4 run covering the columns its frame
 * uses and those the block showed last frame (to clear them); a hidden block is cleared once. */
static uint8_t block_placed[NE];                 /* columns each sprite block showed last frame */
/* ---- ground shadows: a dark ellipse (2 sprites, tiles SHADOW_TILE) at each entity's ground point (floor_top + Z, also
 * under jumps and projectiles), behind every fighter (sprites 43-54 < the blocks at 60+). Entities alternate frames by
 * draw order index: each shadow shows every other frame (flicker transparency), so the half shown on a frame (entities
 * 2j + parity) share 6 sprite pairs: pair j. ---- */
#define SH_SPR 43
_Static_assert((NE & 1) == 0, "shadow pairs: entities 2j and 2j + 1");
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
    static uint8_t parity;
    uint16_t *y = cmd_run(VRAM_SCB3 + SH_SPR, NE), *x = cmd_run(VRAM_SCB4 + SH_SPR, NE);
    uint8_t i;
    parity ^= 1;
    for (i = parity; i < NE; i += 2, y += 2, x += 2) {
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

/* ---- debug boxes (P2 START toggles): the corners of every hurt box (green) and attack box (red) the hit test uses,
 * 8x8 brackets on sprites 300-363 (the banner's, free in a fight): 32 for hurt boxes, 32 for attack boxes. ---- */
#define DBG_SPR 300
#define DBG_BOXES 8                      /* per kind (sprites 300-363; 364-375 = hit sparks) */
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

static void draw(void) {
    uint8_t i;
    if (mode == 1) stage_draw();                             /* only the fight has a stage */
    for (i = 0; i < nf; i++)
        if (order[i]->state != S_OFF && !(order[i]->state == S_PROJ && order[i]->frame_ovr == 0xFFFF)) fighter_tiles(order[i]);
    mark(P_TILES);
    line_guard();
    mark(P_GUARD);
    for (i = 0; i < NE; i++) {
        fighter_t *f = order[i];
        uint8_t vis = i < nf && !hidden[i], n = vis ? f->ncols : 0, m = n > block_placed[i] ? n : block_placed[i];
        uint16_t spr = SPR_BASE + i * MAX_COLS, *y, *x;
        if (m) {
            y = cmd_run(VRAM_SCB3 + spr, m); x = cmd_run(VRAM_SCB4 + spr, m);
            if (vis) fighter_place(f, y, x, cam_x, m);
            else { uint8_t c; for (c = 0; c < m; c++) y[c] = x[c] = 0; }
        }
        block_placed[i] = n;
    }
    shadows();
    sparks_draw();
    dbg_draw();
}

static intent_t in[NF];                          /* this frame's intent per fighter (player pad or AI) */
static void inputs_reset(void) {                 /* a select / fight starts: nothing of the demo or the last game */
    uint8_t i;
    for (i = 0; i < NF; i++) in[i] = (intent_t){ 0 };
    for (i = 0; i < 2; i++) { tap_t[i] = 255; tap_dir[i] = 0; }
}
static void read_player(uint8_t p, intent_t *in, const fighter_t *f) {
    uint16_t held = JOY_held(p), pressed = JOY_pressed(p);
    *in = (intent_t){ 0 };                                     /* from nothing every frame: a human's input carries nothing
                                                                  the AI wrote (the attract demo drives P1's slot) */
    in->dx = (held & JOY_RIGHT) ? 1 : (held & JOY_LEFT) ? -1 : 0;
    in->dz = (held & JOY_DOWN) ? 1 : (held & JOY_UP) ? -1 : 0;
    in->press = ((pressed & JOY_A) ? IN_A : 0) | ((pressed & JOY_B) ? IN_B : 0) | ((pressed & JOY_C) ? IN_C : 0) | ((pressed & JOY_D) ? IN_D : 0);
    if ((pressed & (JOY_A | JOY_B)) && (held & JOY_A) && (held & JOY_B)) in->press = (in->press & ~(IN_A | IN_B)) | IN_D;   /* A+B = D */
    in->hold = ((held & JOY_A) ? IN_A : 0) | ((held & JOY_B) ? IN_B : 0) | ((held & JOY_C) ? IN_C : 0) | ((held & JOY_D) ? IN_D : 0);
    if (pressed & (JOY_LEFT | JOY_RIGHT)) {                     /* forward tapped twice within 12 frames */
        uint8_t d = (pressed & JOY_RIGHT) ? 1 : 2;
        if (tap_dir[p] == d && tap_t[p] < 12) in->run = 1;
        tap_dir[p] = d; tap_t[p] = 0;
    } else if (tap_t[p] < 255) tap_t[p]++;
    (void)f;
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
typedef struct { uint8_t col, row, mirror, n, cell[BOSS_CELLS], wait; int16_t px, trail; } bar_t;
static uint8_t lives[2];
static uint16_t cont_t[2];                       /* continue countdown (frames), 0 = none */
/* bars: 0 P1, 1 right block (P2, or P1's target alone), 2 P1's target under P1, 3 P2's target under P2, 4 the boss */
static bar_t bars[5];
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
        if (b->cell[sc] != t) { b->cell[sc] = t; fix_put(b->col + sc, b->row, t); }
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
    for (p = 0; p < 5; p++) {
        bars[p].col = COL[p]; bars[p].row = ROW[p]; bars[p].mirror = p & 1 && p < 4; bars[p].px = bars[p].trail = -1; bars[p].wait = 0;
        bars[p].n = p < 4 ? BAR_CELLS : BOSS_CELLS;
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
        hud_name(right, name_row, t ? t->ch->name : 0);
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
        if (lives[p] != hud_lives[p]) { hud_lives[p] = lives[p]; FIX_print(lc, 2, "x ", 0); FIX_printNum(lc + 1, 2, lives[p], 0); }
        if (cont_t[p] / 60 != hud_cont[p]) {
            hud_cont[p] = cont_t[p] / 60;
            if (cont_t[p]) { FIX_print(cc, 2, "CONTINUE   ", 0); FIX_printNum(cc + 9, 2, hud_cont[p], 0); }
            else FIX_print(cc, 2, "           ", 0);
        }
        if (two) hud_target(2 + p, tgt(f), p, 5, 0);       /* each player's target under its own block: bar, name */
    }
    if (!two) hud_target(1, tgt(&fighters[0]), 1, 1, 1);  /* one player: its target is the right block */
    i = mode == 1 && !attract && (phase == PH_BOSS || phase == PH_END) && fighters[BOSS_IDX_HUD].state != S_OFF;
    if (i != boss_shown) {                                   /* the boss bar: name on row 6, bar on row 7 */
        boss_shown = i;
        FIX_print(5, 6, "              ", 0);
        if (i) FIX_print(5, 6, fighters[BOSS_IDX_HUD].ch->name, 0); else bar_clear(&bars[4]);
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

#define CAMP_N    5
#define WAVES_N   5
#define CONTINUE  600
#define BOSS_IDX  2                              /* the boss's fighter slot; minions 3.. */
static const uint8_t CAMP_STAGE[CAMP_N] = { 0, 1, 3, 4, 5 };
/* the bosses, one a stage. name: the export name in CHARS (Makefile); while it is missing, stand_in fights in its place
 * (Rugal and Goenitz are being exported, to be added at the end of CHARS: nothing here changes when they arrive, the
 * name is found). song: its theme, started when it comes in; placeholders = the fight music ($27) until the real songs
 * are converted (Mr Big: AOF2, Krauser: FF Special "Kaiser Wave", Geese: FF Special, Rugal: KOF98, Goenitz: KOF96):
 * put their command bytes here. A boss whose own fighter is in CHARS is locked on the select screen until beaten
 * (save.unlocked bit k = BOSS[k]). */
typedef struct { const char *name, *stand_in; uint8_t song; } boss_t;
static const boss_t BOSS[CAMP_N] = {
    { "MR_BIG",  "MR_BIG",  MUS_BOSS_MR_BIG },
    { "KRAUSER", "KRAUSER", MUS_BOSS_KRAUSER },
    { "GEESE",   "GEESE",   MUS_BOSS_GEESE },
    { "RUGAL",   "YASHIRO", MUS_BOSS_RUGAL },
    { "GOENITZ", "IORI",    MUS_BOSS_GOENITZ },
};
#define BOSS_HP(s)    (100 + (s) * 4)            /* 1.7-1.9 x a fighter's 60 (bar: 2 px a point, 30 cells = 238 px) */
#define BOSS_POWER(s) (1 + (((s) + 1) >> 1))
static uint8_t boss_ch[CAMP_N];                  /* bm_chars index of each boss (its stand-in while missing) */
static uint8_t boss_real;                        /* bit k: BOSS[k]'s own fighter is in CHARS */
static uint8_t streq(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }
static uint8_t char_named(const char *n) {
    uint8_t c;
    for (c = 0; c < BC_COUNT; c++) if (streq(bm_chars[c].name, n)) return c;
    return 0xFF;
}
static void bosses_find(void) {
    uint8_t k, c;
    boss_real = 0;
    for (k = 0; k < CAMP_N; k++) {
        c = char_named(BOSS[k].name);
        if (c != 0xFF) boss_real |= 1 << k;
        else if ((c = char_named(BOSS[k].stand_in)) == 0xFF) c = 0;
        boss_ch[k] = c;
    }
}
static uint8_t boss_of(uint8_t c) {              /* k + 1 when fighter c is boss k's own fighter, else 0 */
    uint8_t k;
    for (k = 0; k < CAMP_N; k++) if ((boss_real >> k & 1) && boss_ch[k] == c) return k + 1;
    return 0;
}

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
    if ((s->magic[3] != '1' && s->magic[3] != '2') || s->sum != save_sum(s) || s->furthest >= CAMP_N) return 0;
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
static uint8_t char_locked(uint8_t c) { uint8_t k = boss_of(c); return k && !(save.unlocked >> (k - 1) & 1); }
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
    mode = 2; nf = 0; title_t = 0; cam_x = 0; opt_on = 0;
    PAL_setBackdrop(COLOR_BLACK);
    stage_hide();
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    title_screen();
    bios_start = 0;
    snd_music(MUS_SELECT);
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
    snd_music(MUS_SELECT);
}
static void options_tick(void) {
    uint16_t pr = JOY_pressed(0), h = JOY_held(0);
    int8_t d = 0;
    bios_start = 0;
    if (pr & (JOY_UP | JOY_DOWN)) { opt_row = (opt_row + ((pr & JOY_DOWN) ? 1 : 3)) & 3; opt_cursor(); }
    if (pr & (JOY_LEFT | JOY_RIGHT)) { d = (pr & JOY_RIGHT) ? 1 : -1; opt_rep = 0; }
    else if (h & (JOY_LEFT | JOY_RIGHT)) { if (++opt_rep >= 20 && !(opt_rep & 3)) { d = (h & JOY_RIGHT) ? 1 : -1; opt_rep = 16; } }
    else opt_rep = 0;
    if (opt_row == 0 && (pr & JOY_A)) d = 1;
    if (d) {
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
        } else if (opt_row == 3) { options_exit(); return; }
    }
    if (pr & JOY_B) {
        if (opt_row == 1) { snd_cmd(0x04); snd_cmd(0x07); }  /* KOF98's driver: $04 stops the music, and the effects
                                                             too (timer A) until a $07 (measured: silent effects) */
        else options_exit();
    }
}

static void title_tick(void) {
    uint16_t pr, h;
    if (opt_on) { options_tick(); return; }
    pr = JOY_pressed(0); h = JOY_held(0);
    if (!(title_t & 31)) FIX_print(15, 18, (title_t & 32) ? "           " : "PRESS START", 0);
    title_t++;
    if (title_n > 1 && (pr & (JOY_UP | JOY_DOWN))) {
        if (pr & JOY_DOWN) { if (title_sel + 1 < title_n) title_sel++; } else if (title_sel) title_sel--;
        title_menu();
    }
    if ((h & (JOY_A | JOY_B | JOY_C | JOY_D)) == (JOY_A | JOY_B | JOY_C | JOY_D)) {   /* held 2 s: the save cleared */
        if (++title_hold == 120) { save_reset(); save_write(); difficulty = save.difficulty; title_menu(); FIX_print(12, 23, "SAVE DATA CLEARED", 0); }
        return;
    } else title_hold = 0;
    if (title_item[title_sel] == TI_OPT) {                   /* console only: no credit involved */
        if (bios_start || (pr & (JOY_START | JOY_A))) { bios_start = 0; options_start(); }
        return;
    }
    if (bios_start || (title_paid && (pr & (JOY_START | JOY_A)))) {   /* START with a credit (PLAYER_START), or START / A
                                                             when the credit was taken by the START that opened it */
        bios_start = 0; title_paid = 0; camp_from = title_item[title_sel] == TI_CONT ? save.furthest : 0;
        banner_hide(); select_start(); return;
    }
}

/* ---- character select: a police line-up (Bruno 2026-10-04). The roster stands left to right in its idle pose, LU_DX
 * apart, the camera panning to keep the selected fighter in the middle; it shows its colours, the others shades of
 * grey (their own palettes in luminance). "1P" / "2P" with an arrow above the selected one's head (fix layer). Stick
 * left / right moves; A/B/C/D picks that colour set (KOF style) and plays the win pose; then the others walk off the
 * screen, the scene fades to black and the fight's stage fades in. Only the fighters on screen use an entity (actor):
 * the fight's NF entities are the actors here, bound to whichever fighters the camera shows. ---- */
#define LU_X0  64                        /* world x of the first fighter */
#define LU_DX  84                        /* between two fighters (their idle frames are ~70 px wide) */
#define LU_W   (LU_X0 * 2 + (lu_n - 1) * LU_DX)
#define LU_Z   40                        /* feet at SELECT_FLOOR + LU_Z */
#define ARROW_ROW 7                      /* "1P" on this fix row, the arrow below it */
#define FADE_T 32                        /* frames of a fade (level = t / 2, 16 steps) */
enum { SEL_CHOOSE, SEL_LEAVE, SEL_FADE };
static uint8_t cursor[2], picked[2], pick_set[2];
static uint8_t sel_phase, fade_in;
static uint16_t sel_t;
static uint8_t act_of[BC_COUNT];         /* the actor showing a line-up slot, 0xFF none */
static uint8_t chr_of[NF];               /* the line-up slot an actor shows, 0xFF free */
/* the line-up: the unlocked fighters in CHARS order (campaign bosses join once beaten, see BOSS[]); cursor[] and the
 * actors count in slots, lu[slot] = the bm_chars index */
static uint8_t lu[BC_COUNT], lu_n;
static uint8_t char_locked(uint8_t c);
static void roster_build(void) {
    uint8_t c;
    lu_n = 0;
    for (c = 0; c < BC_COUNT; c++) if (!char_locked(c)) lu[lu_n++] = c;
}
static uint8_t arrow_col[2] = { 0xFF, 0xFF };

static uint16_t col_scale(uint16_t c, uint8_t k) {          /* a colour at k / 16 of its brightness */
    uint8_t r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
    return RGB((r * k) >> 4, (g * k) >> 4, (b * k) >> 4);
}
static uint16_t col_grey(uint16_t c) {                      /* luminance (5 R + 9 G + 2 B) / 16, a cold grey */
    uint8_t r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
    uint8_t l = (uint8_t)((r * 5 + g * 9 + b * 2) >> 4);
    return RGB(l, l, l + (l < 31));
}
/* an entity's palettes: its own colours (grey = 0) or greys, at k / 16 brightness */
static void fighter_pals(const fighter_t *f, uint8_t colour, uint8_t k) {
    uint16_t buf[16];
    uint8_t i, j;
    for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) {
        const uint16_t *src = f->ch->pals + ((f->set * f->ch->npal + i) << 4);
        buf[0] = src[0];
        for (j = 1; j < 16; j++) buf[j] = col_scale(colour ? fighter_colour(f, src[j]) : col_grey(src[j]), k);
        PAL_setPalette(f->palbase + i, buf);
    }
}
static uint8_t chosen(uint8_t c) { return c == cursor[0] || c == cursor[1]; }
static void actor_bind(uint8_t c, uint8_t a) {
    fighter_t *f = &fighters[a];
    const bchar_t *ch = &bm_chars[lu[c]];
    uint8_t set = (c == cursor[0]) ? pick_set[0] : (c == cursor[1]) ? pick_set[1] : 0;
    fighter_init(f, ch, set < ch->nsets ? set : 0, 16 + a * MAX_PALS, 0, LU_X0 + c * LU_DX, LU_Z);
    f->idx = a; f->facing = 1;
    fighter_pals(f, chosen(c), 16);
    act_of[c] = a; chr_of[a] = c;
}
static void actor_free(uint8_t a) {
    if (chr_of[a] != 0xFF) act_of[chr_of[a]] = 0xFF;
    chr_of[a] = 0xFF; fighters[a].state = S_OFF;
}
/* the fighters the camera shows get an actor, the others give theirs back */
static void lineup_bind(void) {
    uint8_t c, a;
    for (a = 0; a < NF; a++)
        if (chr_of[a] != 0xFF) {
            int16_t sx = LU_X0 + chr_of[a] * LU_DX - cam_x;
            if (sx < -56 || sx > 376) actor_free(a);
        }
    for (c = 0; c < lu_n; c++) {
        int16_t sx = LU_X0 + c * LU_DX - cam_x;
        if (act_of[c] != 0xFF || sx < -56 || sx > 376) continue;
        for (a = 0; a < NF && chr_of[a] != 0xFF; a++) ;
        if (a < NF) actor_bind(c, a);
    }
}
static void lineup_camera(void) {
    int16_t goal = LU_X0 + cursor[0] * LU_DX - 160, d;
    if (goal < 0) goal = 0;
    if (goal > LU_W - 320) goal = LU_W - 320;
    d = goal - cam_x;
    cam_x += d > 0 ? (d + 3) >> 2 : -((3 - d) >> 2);
}
static void select_arrows(void) {                           /* "1P" / "2P" + arrow over the selected head */
    uint8_t p;
    for (p = 0; p < 2; p++) {
        int16_t sx = LU_X0 + (cursor[p] == 0xFF ? 0 : cursor[p]) * LU_DX - cam_x;
        uint8_t col = cursor[p] == 0xFF || sel_phase == SEL_FADE || sx < 8 || sx > 312 ? 0xFF : (uint8_t)((sx - 8) >> 3);
        if (col == arrow_col[p]) continue;
        if (arrow_col[p] != 0xFF) { FIX_print(arrow_col[p], ARROW_ROW - p * 2, "  ", 0); FIX_print(arrow_col[p], ARROW_ROW + 1 - p * 2, "  ", 0); }
        if (col != 0xFF) { FIX_print(col, ARROW_ROW - p * 2, p ? "2P" : "1P", 0); FIX_setTile(col, ARROW_ROW + 1 - p * 2, ARROW_TILE, 0); }
        arrow_col[p] = col;
    }
}
static void select_name(void) {
    const char *n = bm_chars[lu[cursor[0]]].name;
    uint8_t len = 0;
    while (n[len]) len++;
    FIX_print(9, 5, "                      ", 0);
    FIX_print(20 - (len >> 1), 5, n, 0);
}
static void select_start(void) {
    uint8_t p, i;
    mode = 0; sel_t = 0; sel_phase = SEL_CHOOSE; attract = 0; ai_weak = 0;
    inputs_reset();
    snd_music(MUS_SELECT);
    FIX_clear(); arcade_line_reset();
    PAL_setBackdrop(RGB8(72, 76, 84));                       /* the line-up wall */
    stage_hide();                                            /* stage sprites hidden */
    floor_top = SELECT_FLOOR;
    dbg_init();
    FIX_print(10, 3, "SELECT YOUR FIGHTER", 0);
    FIX_print(3, 26, "STICK MOVES   A B C D PICK COLOURS", 0);   /* keyboard: WASD, U I O P */
    for (p = 0; p < 2; p++) { picked[p] = 0; pick_set[p] = 0; arrow_col[p] = 0xFF; }
    cursor[0] = 0; cursor[1] = 0xFF;                         /* P2 joins in the fight */
    roster_build();
    for (i = 0; i < BC_COUNT; i++) act_of[i] = 0xFF;
    for (i = 0; i < NF; i++) { chr_of[i] = 0xFF; fighters[i].state = S_OFF; order[i] = &fighters[i]; }
    for (i = 0; i < NPJ; i++) { projectile_reset(&projectiles[i]); order[NF + i] = &projectiles[i]; }
    nf = NF;
    cam_x = 0; lineup_bind(); select_name();
}
/* ---- campaign (Bruno 2026-10-05, Streets of Rage 2 / Golden Axe style): five stages, Robo Army's horizontal ones in
 * this order (stages[] 0, 1, 3, 4, 5; 2, the 512 px boss arena, is not used). Each stage scrolls end to end through
 * WAVES_N lock points spread evenly from its start (camera x 0) to its end (world_w - 320): at a lock point the camera
 * stops until the wave there is beaten, then GO blinks and the camera may scroll on to the next one (never back). Wave w
 * of stage s: 2 + s + w enemies (at most NF - 2 = 6), the fighters nobody picked and no boss, walking in from the right
 * (every other one from the left when there is room); stage s's enemies land (s + 1) / 2 extra damage a hit (`power`).
 * At the stage's end its boss (BOSS[s]) comes in with 2 + s minions (at most 5) in minion colours (fighter_colour's
 * tints: never a playable colour set); the boss bar under the HUD; boss beaten: the minions go down, STAGE CLEAR, the
 * save (furthest stage, boss unlocked), BOSS UNLOCKED when its fighter was locked, the fade to the next stage. After
 * the fifth: CONGRATULATIONS, then the title. Players: 3 lives, a 10 s continue (START with a credit); both out:
 * GAME OVER, back to the BIOS. The attract demo plays stage STAGE (make STAGE=n, stages[] index) without a boss. ---- */

static uint8_t unlock_k;                         /* the boss just unlocked + 1 (0 none) */
static uint16_t phase_t;
static int16_t lock_step;                        /* between two lock points */
static uint8_t power;                            /* this stage's enemies' extra damage */
static uint8_t pl_ch[2], pl_set[2], pl_on[2];   /* the players, carried from stage to stage (pl_on: in play) */
static uint8_t avail[BC_COUNT], navail;          /* the enemies: fighters nobody picked, no boss */
static uint16_t banner_t;                        /* GAME OVER on screen, frames left */

static uint8_t mod8(uint8_t a, uint8_t b) { while (a >= b) a -= b; return a; }   /* no libgcc: no 32-bit % */
static void hud_wave(void) {
    FIX_print(2, 26, "STAGE   WAVE   ", 0); FIX_printNum(8, 26, camp + 1, 0);
    if (phase >= PH_BOSS) FIX_print(10, 26, "BOSS ", 0); else FIX_printNum(15, 26, wave + 1, 0);
}
static void enemy_init(uint8_t slot, uint8_t c, uint8_t set, int16_t x, int16_t z, uint8_t tint) {
    fighter_t *e = &fighters[slot];
    if (x < 16) x = 16;
    if (x > world_w - 16) x = world_w - 16;
    fighter_init(e, &bm_chars[c], mod8(set, bm_chars[c].nsets), 16 + slot * MAX_PALS, 1, x, z);
    e->idx = slot; e->power = power; e->tint = tint;
    if (!attract) e->hp = e->hp_max = life(LIFE);         /* the campaign's difficulty (the demo: as it was) */
    if (tint) fighter_load_pals(e);
}
static int16_t walk_in_x(uint8_t k) {            /* off screen: the right, every other one the left when there is room */
    if ((k & 1) && cam_x >= 64) return cam_x - 24 - (k >> 1) * 36;
    return cam_x + 340 + (k >> 1) * 36;
}
static void spawn_wave(void) {
    uint8_t k, n = 2 + camp + wave;
    if (n > NF - 2) n = NF - 2;
    for (k = 0; k < NF - 2; k++) {
        if (k >= n) { fighters[2 + k].state = S_OFF; continue; }
        enemy_init(2 + k, avail[mod8(wave * 3 + k + camp, navail)], wave + k, wave ? walk_in_x(k) : 200 + k * 30, 6 + k * 11, 0);
    }
    ai_init(0x1D2B + wave + camp * 8);
    hud_wave();
}
static void boss_start(void) {
    uint8_t k, c = boss_ch[camp], n = 2 + camp, set = 0;
    phase = PH_BOSS; phase_t = 0;
    if (n > NF - 3) n = NF - 3;
    if (c == pl_ch[0] && !pl_set[0]) set = 1;           /* never in P1's colours */
    enemy_init(BOSS_IDX, c, set, world_w - 16, 30, 0);
    fighters[BOSS_IDX].hp = fighters[BOSS_IDX].hp_max = life(BOSS_HP(camp)); fighters[BOSS_IDX].power = BOSS_POWER(camp);
    for (k = 0; k < NF - 3; k++) {
        uint8_t m = mod8(k * 3 + camp, navail);
        if (avail[m] == c) m = mod8(m + 1, navail);         /* not the boss's own fighter (a stand-in is in the pool) */
        m = avail[m];
        if (k >= n) { fighters[3 + k].state = S_OFF; continue; }
        enemy_init(3 + k, m, k + camp, walk_in_x(k), 6 + k * 13, 1 + mod8(k + camp, 3));
    }
    ai_init(0x5B05 + camp);
    ai_set_boss(BOSS_IDX);
    snd_music(BOSS[camp].song);
    hud_wave();
}
static void go_sign(uint8_t on) { FIX_print(29, 3, on ? "GO -->" : "      ", 1); }   /* yellow, in the HUD's black band */
static void stage_begin(uint8_t s, uint8_t first) {
    uint8_t i;
    int16_t span;
    mode = 1; nf = NE; cam_x = 0; wave = 0; banner_t = 0; camp = s; phase = PH_WAVE; phase_t = 0;
    inputs_reset();
    snd_music(MUS_FIGHT);
    dbg_init();                                              /* the title's banner reused sprites 300-318 */
    sparks_init();
    FIX_clear(); arcade_line_reset();
    stage_init(attract ? STAGE : CAMP_STAGE[s]);             /* stage sprites back, every column rewritten */
    PAL_setBackdrop(stg->backdrop);
    span = world_w - 320; lock_step = 0;
    while (span >= WAVES_N) { span -= WAVES_N; lock_step++; }   /* (world_w - 320) / WAVES_N, no divide */
    lock_x = 0;
    power = (s + 1) >> 1;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    for (i = 0; i < 2; i++) {
        if (!pl_on[i]) { fighters[i].state = S_OFF; if (first) { lives[i] = 0; cont_t[i] = 0; } continue; }   /* out: its
                                                             continue countdown (if any) goes on */
        fighter_init(&fighters[i], &bm_chars[pl_ch[i]], pl_set[i], 16 + i * MAX_PALS, 0, i ? 40 : 60, i ? 10 : 40);
        fighters[i].idx = i;
        if (first) { lives[i] = 3; cont_t[i] = 0; }
    }
    navail = 0;
    for (i = 0; i < BC_COUNT; i++) if (!(pl_on[0] && i == pl_ch[0]) && !(pl_on[1] && i == pl_ch[1]) && !boss_of(i)) avail[navail++] = i;
    spawn_wave();
    if (fade_in) { fade_in++; fade_k = 0xFF; fight_fade(); } /* from black (the select screen, the last stage) */
    for (i = 0; i < NF; i++) order[i] = &fighters[i];
    for (i = 0; i < NPJ; i++) { projectiles[i].idx = NF + i; order[NF + i] = &projectiles[i]; }
    hud_reset();
    if (first) { BIOS_PLAYER_MOD[0] = attract ? 0 : 1; BIOS_PLAYER_MOD[1] = 0; }   /* BIOS: who plays (a START then joins) */
}
static void fight_start(void) {                  /* from the select screen: a new game at camp_from */
    pl_ch[0] = lu[cursor[0]]; pl_set[0] = mod8(pick_set[0], bm_chars[pl_ch[0]].nsets); pl_on[0] = 1; pl_on[1] = 0;
    stage_begin(attract ? 0 : camp_from, 1);
}
static void attract_start(void) {
    static uint8_t pick;
    banner_hide();
    roster_build();
    if (pick >= lu_n) pick = 0;
    cursor[0] = pick; cursor[1] = 0xFF; pick_set[0] = pick & 3;
    pick++;
    attract = 1; attract_t = 0; ai_weak = 1;
    fight_start();
}
static void select_start(void);
/* BIOS PLAYER_START filter (crt0): who may take a credit now. Title: anyone (the game starts); select, unlock and
 * ending screens: nobody; fight: a player not in play (P2 joins, a player continues or rejoins), not under GAME OVER
 * or once the stage's boss is beaten, never in the attract demo's fight (a coin ends the demo first). */
uint8_t game_start_accept(uint8_t flags) {
    if (mode == 2 || attract) return opt_on ? 0 : flags;
    if (mode != 1 || banner_t || phase >= PH_END) return 0;
    return flags & ((in_play(&fighters[0]) ? 0 : 1) | (in_play(&fighters[1]) ? 0 : 2));
}
static void unlock_start(uint8_t k);
static void ending_start(void);
static void campaign(uint8_t left) {
    uint8_t i;
    phase_t++;
    switch (phase) {
    case PH_WAVE:                                            /* camera held at lock_x until the wave is beaten */
        if (left) break;
        if (attract && wave + 1 >= WAVES_N) { spawn_wave(); break; }   /* the demo: no boss, the last wave again */
        wave++; phase = PH_GO; phase_t = 0;
        lock_x = wave < WAVES_N ? lock_x + lock_step : world_w - 320;
        break;
    case PH_GO:                                              /* GO: the camera may scroll to the next lock point */
        if ((phase_t & 15) == 1) go_sign(!(phase_t & 16));   /* blinking, on from its first frame */
        if (cam_x < lock_x) break;
        go_sign(0);
        if (wave < WAVES_N) { phase = PH_WAVE; spawn_wave(); } else boss_start();
        break;
    case PH_BOSS:
        if (fighters[BOSS_IDX].state != S_DEAD && fighters[BOSS_IDX].state != S_OFF) break;
        for (i = BOSS_IDX + 1; i < NF; i++) {                /* boss beaten: the minions go down with it */
            fighter_t *e = &fighters[i];
            if (e->state == S_OFF || e->state == S_DEAD || e->hp <= 0) continue;
            if (e->state == S_THROWN || e->state == S_DOWN || e->state == S_GETUP) { e->hp = 0; continue; }
            e->hp = 0; fighter_hit(&fighters[BOSS_IDX], e, 0, R_KNOCKDOWN, 0);
        }
        phase = PH_END; phase_t = 0;
        break;
    case PH_END:                                             /* every enemy gone: STAGE CLEAR, the save */
        if (left) break;
        FIX_print(14, 13, "STAGE CLEAR", 0); snd_music(MUS_JINGLE);
        phase = PH_CLEAR; phase_t = 0; unlock_k = 0;
        if (attract) break;
        if (camp + 1 < CAMP_N && save.furthest < camp + 1) save.furthest = camp + 1;
        if ((boss_real >> camp & 1) && !(save.unlocked >> camp & 1)) { save.unlocked |= 1 << camp; unlock_k = camp + 1; }
        save_write();
        break;
    case PH_CLEAR:
        if (phase_t >= 200) { phase = PH_FADE; phase_t = 0; fade_k = 0xFF; }
        break;
    case PH_FADE:                                            /* to black, then the next screen */
        scene_pals(phase_t >= FADE_T ? 0 : 16 - (uint8_t)(phase_t >> 1));
        if (phase_t < FADE_T + 8) break;
        for (i = 0; i < 2; i++)
            if ((pl_on[i] = in_play(&fighters[i]))) { pl_ch[i] = char_index(fighters[i].ch); pl_set[i] = fighters[i].set; }
        if (unlock_k) unlock_start(unlock_k - 1);
        else if (camp + 1 >= CAMP_N) ending_start();
        else { fade_in = FADE_T; stage_begin(camp + 1, 0); }
        break;
    }
}
static void flow(void) {
    uint8_t i, p, left = 0;
    if (banner_t) { if (!--banner_t) SYS_return(); return; }   /* back to the BIOS: demo, or title while credits remain */
    for (i = 2; i < NF; i++) {
        fighter_t *e = &fighters[i];
        if (e->state == S_DEAD && e->state_t > 60) e->state = S_OFF;      /* blinked out */
        if (e->state != S_OFF) left++;
    }
    if (!attract && in_play(&fighters[0]) && (JOY_pressed(0) & JOY_START)) dbg_on ^= 1;   /* box viewer: P1 START in play
                                                             (P2 START joins; a START that continues isn't in play yet) */
    if ((bios_start & 2) && !attract && !p2_in()) {           /* P2 joins mid-fight: START with a credit (PLAYER_START) */
        uint8_t c, used;
        for (c = 0; c < BC_COUNT; c++) {                     /* an unlocked fighter nobody on screen is */
            used = &bm_chars[c] == fighters[0].ch || char_locked(c);
            for (i = 2; i < NF && !used; i++) used = fighters[i].state != S_OFF && fighters[i].ch == &bm_chars[c];
            if (!used) break;
        }
        fighter_init(&fighters[1], &bm_chars[c < BC_COUNT ? c : 1], 1, 16 + MAX_PALS, 0, cam_x + 40, 20);
        fighters[1].idx = 1; fighter_revive(&fighters[1]); lives[1] = 2; BIOS_PLAYER_MOD[1] = 1;
    }
    for (p = 0; p < 2; p++) {
        fighter_t *f = &fighters[p];
        if (f->state == S_DEAD) {
            if (lives[p]) { lives[p]--; fighter_revive(f); }
            else { f->state = S_OFF; cont_t[p] = CONTINUE; BIOS_PLAYER_MOD[p] = 2; }
        }
        if (!in_play(f) && (bios_start & (1 << p))) {        /* START with a credit: continue, or P1 rejoins */
            cont_t[p] = 0; lives[p] = 2; BIOS_PLAYER_MOD[p] = 1;
            f->x = FIX(cam_x + (p ? 60 : 100)); fighter_revive(f);
        } else if (cont_t[p] && !--cont_t[p]) BIOS_PLAYER_MOD[p] = 3;
    }
    bios_start = 0;
    if (!in_play(&fighters[0]) && !in_play(&fighters[1]) && !cont_t[0] && !cont_t[1]) {
        FIX_print(15, 13, "GAME OVER", 0); banner_t = 240; return;
    }
    campaign(left);
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
    fighter_init(&fighters[0], &bm_chars[c], set, 16, 0, 160, LU_Z);
    fighters[0].idx = 0; fighters[0].facing = 1;
    fighter_play(&fighters[0], BA_WIN_A);
    for (i = 0; i < NF; i++) order[i] = &fighters[i];
    for (i = 0; i < NPJ; i++) order[NF + i] = &projectiles[i];
}
static void centre(uint8_t row, const char *t) { uint8_t n = 0; while (t[n]) n++; FIX_print(20 - (n >> 1), row, t, 0); }
static void unlock_start(uint8_t k) {
    uint8_t c = boss_ch[k];
    show_start(3, c, 0, RGB8(40, 8, 8));
    centre(3, "BOSS UNLOCKED");
    portrait(18, 5, c, 0);
    centre(10, bm_chars[c].name);
    centre(24, "NOW ON THE SELECT SCREEN");
    snd_music(MUS_SELECT);
}
static void ending_start(void) {
    show_start(4, pl_ch[0], pl_set[0], RGB8(8, 16, 40));
    centre(3, "CONGRATULATIONS!");
    centre(5, "ALL FIVE STAGES CLEARED");
    portrait(18, 7, pl_ch[0], 0);
    centre(24, "THANK YOU FOR PLAYING");
    snd_music(MUS_JINGLE);
}
static void show_tick(void) {
    uint16_t pr = JOY_pressed(0) | JOY_pressed(1);
    scr_t++;
    fighter_animate(&fighters[0]);
    if (scr_t < (mode == 3 ? 360 : 600) && !(scr_t >= 90 && (pr & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)))) return;
    if (mode == 4) SYS_return();                             /* the ending: back to the BIOS, which commits the MVS save
                                                                and shows the title (credits left) or the attract demo */
    else if (camp + 1 >= CAMP_N) ending_start();
    else { fade_in = FADE_T; stage_begin(camp + 1, 0); }
}
static void select_tick(void) {
    uint8_t a;
    uint16_t pr = JOY_pressed(0);
    sel_t++;
    if (sel_phase == SEL_CHOOSE) {
        int8_t c = cursor[0], was = c;
        if (pr & JOY_LEFT) c--;
        if (pr & JOY_RIGHT) c++;
        if (c < 0) c = 0;
        if (c >= lu_n) c = lu_n - 1;
        if (c != was) {                                      /* colours follow the cursor */
            cursor[0] = c;
            if (act_of[was] != 0xFF) fighter_pals(&fighters[act_of[was]], 0, 16);
            if (act_of[c] != 0xFF) fighter_pals(&fighters[act_of[c]], 1, 16);
            select_name();
        }
        lineup_camera(); lineup_bind();
        if (pr & (JOY_A | JOY_B | JOY_C | JOY_D)) {
            pick_set[0] = (pr & JOY_A) ? 0 : (pr & JOY_B) ? 1 : (pr & JOY_C) ? 2 : 3;
            a = act_of[cursor[0]];
            if (a == 0xFF) { lineup_bind(); a = act_of[cursor[0]]; }
            if (a != 0xFF) { actor_free(a); actor_bind(cursor[0], a); fighter_play(&fighters[a], BA_WIN_A); }
            picked[0] = 1; sel_phase = SEL_LEAVE; sel_t = 0;
        }
    } else if (sel_phase == SEL_LEAVE) {                     /* the others walk off the screen, outward */
        uint8_t left = 0;
        for (a = 0; a < NF; a++) {
            fighter_t *f = &fighters[a];
            int16_t sx;
            if (chr_of[a] == 0xFF || chr_of[a] == cursor[0]) continue;
            if (sel_t == 1 || f->anim != BA_WALK_FWD) { f->facing = chr_of[a] < cursor[0] ? -1 : 1; fighter_play(f, BA_WALK_FWD); }
            f->x += f->facing > 0 ? FIX(3) : -FIX(3);
            sx = INT(f->x) - cam_x;
            if (sx < -64 || sx > 384) actor_free(a); else left++;
        }
        if (!left && sel_t >= 60) { sel_phase = SEL_FADE; sel_t = 0; }
    } else {                                                 /* to black: the wall and the picked fighter */
        uint8_t k = sel_t >= FADE_T ? 0 : 16 - (uint8_t)(sel_t >> 1);
        PAL_setBackdrop(col_scale(RGB8(72, 76, 84), k));
        a = act_of[cursor[0]];
        if (a != 0xFF) fighter_pals(&fighters[a], 1, k);
        if (sel_t >= FADE_T + 8) { fade_in = FADE_T; fight_start(); return; }
    }
    for (a = 0; a < NF; a++) if (chr_of[a] != 0xFF) fighter_animate(&fighters[a]);
    select_arrows();
}
/* the fight fading in from black after the select screen: the stage, the backdrop, every fighter (k / 16); k steps every
 * other tick, and only a new k is written (scaling every palette each tick took ~5 frames a
 * tick: the fade-in lasted ~160 frames for its 32 ticks; with the 25 Robo Army stage palettes it lasts ~137) */
static void fight_fade(void) { scene_pals(16 - (uint8_t)(--fade_in >> 1)); }
static void scene_pals(uint8_t k) {              /* the fight at k / 16: stage, backdrop, fighters (also the fade out) */
    uint8_t i;
    if (k == fade_k) return;
    fade_k = k;
    stage_pals(k);
    PAL_setBackdrop(col_scale(stg->backdrop, k));
    for (i = 0; i < NF; i++) if (fighters[i].state != S_OFF) fighter_pals(&fighters[i], 1, k);   /* in play only: an
                                                             unused slot's stale fighter (the demo's, a line-up actor's) cost
                                                             the first tick a frame or not by history (regress bleed) */
}

void game_init(void) {
    uint8_t i;
    bosses_find();
    save_load();                                             /* MVS: the BIOS restored the block (a fresh one: reset) */
    PAL_setPalette(0, TEXT_PAL);
    PAL_setBackdrop(stg->backdrop);
    for (i = 0; i < NE * MAX_COLS; i++) cmd_push(VRAM_SCB2 + SPR_BASE + i, 0x0FFF);   /* full size, set once */
    for (i = 0; i < NE; i++) block_placed[i] = MAX_COLS;                              /* clear every block once */
    stage_init(STAGE);
    snd_cmd(0x07);                                           /* KOF98's driver: music unlock */
}

/* MVS protocol (sdk/boot/crt0.s): request 2 = attract demo, 3 = title (a coin went in) */
static void attract_start(void);
void game_enter(uint8_t request) {
    BIOS_USER_MODE = 1;                                      /* title / demo (game_init ran on request 0) */
    { uint8_t k; for (k = 0; k < 10; k++) TEXT_PAL[6 + k] = bar_colours[k];
      PAL_setPalette(0, TEXT_PAL);                           /* the BIOS's own screens overwrite palette 0 */
      TEXT_PAL[1] = RGB(31, 28, 0); PAL_setPalette(1, TEXT_PAL); TEXT_PAL[1] = COLOR_WHITE; }   /* 1: yellow text (GO);
                                                                 fix palettes 2-3: the shown portraits (portrait()) */
    shadow_init();
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
    arcade_line();
    if (mode == 2) { title_tick(); if (mode == 2) return; }
    if (!mode) { select_tick(); depth_sort(); draw(); return; }
    if (mode >= 3) { show_tick(); if (mode >= 3) { depth_sort(); draw(); } return; }
    if (attract) {                                           /* the demo: a coin, 40 s or a game over ends it */
        if (bios_demo_end || ++attract_t > 2400) { SYS_return(); }
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
    ai_update(fighters, NF, 2, in);
#endif
    mark(P_AI);
    for (i = 0; i < NF; i++) if (fighters[i].state != S_OFF) fighter_update(&fighters[i], &in[i]);
    flow();
    if (mode != 1) return;                                   /* back on the title screen */
    if (fade_in) fight_fade();
    camera();
    projectiles_update(cam_x);
    mark(P_UPDATE);
    combat(order, nf);
    mark(P_COMBAT);
    depth_sort();
    mark(P_SORT);
    draw();
    mark(P_PLACE);
    hud();
    mark(P_HUD);
}
