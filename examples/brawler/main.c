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
#include "game_tables.h"

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
#define NA 16                        /* sprite blocks: NE in a fight, NA actors on the select screen (blocks NE..NA-1 =
                                        sprites 300-379: the banner's, the debug boxes', the sparks', none in use there) */
#define SPR_BASE 60                  /* fighter blocks (stage 22-42, shadows 43-54 behind them; 1-21 free) */
static fighter_t fighters[NF];
static fighter_t *order[NA];                     /* back (small Z) to front, the nf entities in play */
static uint8_t nf;                               /* entities in play: the previews on the select screen, NE in the fight */
static uint8_t mode;                             /* 0 select, 1 fight, 2 title, 3 BOSS UNLOCKED, 4 the ending */
static uint8_t attract;                          /* the fight is the attract demo: P1 is ai_bot, enemies their attract_ai */
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
static uint8_t hidden[NA], guard_hidden;
static void line_guard(void) {
    static uint8_t parity;
    uint8_t prio[NA], n = 0, i, k, used = mode == 1 ? BG_N + SH_RESERVE + SPARK_RESERVE : 0;   /* the select: actors only */
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
static uint8_t block_placed[NA];                 /* columns each sprite block showed last frame */
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
    for (i = 0; i < NA; i++) {
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
    if ((pressed & (JOY_A | JOY_B)) && (held & JOY_A) && (held & JOY_B)) { in->press = (in->press & ~(IN_A | IN_B)) | IN_D; in->ab = 1; }   /* A+B = D (or a route's A+B link) */
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
static uint8_t gen_count = EN_COUNT;             /* enemies in genemies[] */
static void gdata_init(void) {
    uint8_t i, k;
    gstages = gstages_rom; genemies = genemies_rom;
    for (i = 0; i < AI_COUNT; i++)
        for (k = 0; k < sizeof(ai_preset_t); k++) ((uint8_t *)&ai_presets[i])[k] = ((const uint8_t *)&ai_presets_rom[i])[k];
}
/* ---- the Brawler Lab's write path (gamedata.h gdpack_t): a data pack in lab.pack, checked when the page sends it
 * (lab.load 3) and again as it is installed at the next safe point (gd_apply: a wave's spawn, the boss's, a stage start,
 * the lab's enemy respawn), copied into gd_live and its offsets turned into pointers. Same ROM as the release. ---- */
static uint8_t gd_live[GD_MAX] __attribute__((aligned(4)));
static uint8_t gd_want;                          /* 3: install lab.pack, 4: back to the ROM's tables, at the safe point */
#define GD_OFF(ptr) ((uint32_t)(ptr))            /* a pointer field of a pack: its offset */
static uint8_t gd_in(uint16_t size, uint32_t off, uint32_t len, uint8_t even) {   /* [off, off + len) inside the pack */
    return off >= sizeof(gdpack_t) && off + len <= size && !(even && (off & 1));
}
static uint8_t gd_tree(const uint8_t *p, uint16_t size, uint32_t off) {   /* a route tree (fighter.h rt_head_t) */
    const rt_head_t *t = (const rt_head_t *)(p + off);
    uint8_t n, i, k;
    if (!gd_in(size, off, sizeof(rt_head_t), 1) || t->magic[0] != 'R' || t->magic[1] != 'T' || t->version != 2) return 0;
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
static uint8_t gd_check(const uint8_t *p) {      /* 0, or the check that failed */
    const gdpack_t *h = (const gdpack_t *)p;
    const genemy_t *en;
    const gstage_t *st;
    uint16_t size = h->size, i, k;
    if (h->magic[0] != 'G' || h->magic[1] != 'D') return 1;
    if (h->version != GD_VERSION) return 2;
    if (size < sizeof(gdpack_t) || size > GD_MAX) return 3;
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
    return 0;
}
static void gd_apply(void) {                     /* at a safe point: the pack (or the ROM's tables) in use from now */
    if (gd_want == 4) { gstages = gstages_rom; genemies = genemies_rom; ai_tab = ai_presets; gen_count = EN_COUNT; lab.pack_stat = GD_ROM; }
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
    mode = 2; nf = 0; title_t = 0; cam_x = 0; opt_on = 0;
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

/* ---- character select: a group photo (Bruno 2026-10-05, TODO #51). The whole roster stands in rows like a school
 * photo, everyone at once: the front rows the playable fighters, the back row the campaign bosses (a locked boss is a
 * dark silhouette, not selectable; once beaten it is in colour / grey like the others). Each fighter holds its 'watch'
 * pose (export_bm.WATCH: a front-facing frame from its intros / win poses), turned toward the middle. The places are
 * slots (SEL_SLOT: x, z, row), independent of who stands in them (sel_fighter: the fighter of each slot), so moving
 * someone on screen is a change to game.json's select slots only. The cursor's fighter shows its colours, the others shades of grey
 * (their own palettes in luminance). "1P" / "2P" with an arrow above the selected head (fix layer). Stick left / right
 * moves within a row, up / down to the row behind / in front (the nearest fighter in x); A/B/C/D picks that colour set
 * (KOF style) and plays the win pose. P2 joins here with START (a credit) and picks too; the two can't pick the same
 * fighter. When everyone in has picked, the others walk off the screen outward, the scene fades to black and the
 * fight's stage fades in. Each fighter on screen is an entity (actor): the fight's NE entities + NA - NE more. ---- */
#define SEL_BACK 2                       /* the bosses' row */
#define SHOW_Z 40                        /* BOSS UNLOCKED / ending: feet at SELECT_FLOOR + SHOW_Z */
#define FADE_T 32                        /* frames of a fade (level = t / 2, 16 steps) */
_Static_assert(BC_COUNT <= SEL_NSLOT && BC_COUNT <= NA, "group photo: a slot and an actor per fighter");
/* the slots (game.json "select", gamedata.h sel_slot_t): x (px), z (feet at SELECT_FLOOR + z), row (0 front: low on the
 * screen, drawn in front; 2 back, SEL_BACK: higher, behind); sel_fighter[slot] = who stands there (the generator checks
 * every roster fighter has one). Today: front rows 48 px apart inside x 16-304 (the 304 px a TV shows; the watch poses
 * are 40-80 px wide: shoulders overlap, as in a photo), the middle row between the front row's fighters, the bosses in
 * stage order on the back row, spread wider. */
enum { SEL_CHOOSE, SEL_LEAVE, SEL_FADE };
static uint8_t cursor[2], picked[2], pick_set[2];   /* cursor: a slot (0xFF: that player isn't in) */
static uint8_t sel_phase, fade_in;
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

static uint16_t col_scale(uint16_t c, uint8_t k) {          /* a colour at k / 16 of its brightness */
    uint8_t r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
    return RGB((r * k) >> 4, (g * k) >> 4, (b * k) >> 4);
}
static uint16_t col_grey(uint16_t c) {                      /* luminance (5 R + 9 G + 2 B) / 16, a cold grey */
    uint8_t r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
    uint8_t l = (uint8_t)((r * 5 + g * 9 + b * 2) >> 4);
    return RGB(l, l, l + (l < 31));
}
#define SILHOUETTE RGB(4, 4, 5)
/* an entity's palettes: its own colours (1), greys (0) or a silhouette (2), at k / 16 brightness */
static void fighter_pals(const fighter_t *f, uint8_t colour, uint8_t k) {
    uint16_t buf[16];
    uint8_t i, j;
    for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) {
        const uint16_t *src = fighter_src_pal(f, i);
        buf[0] = src[0];
        for (j = 1; j < 16; j++)
            buf[j] = col_scale(colour == 2 ? SILHOUETTE : colour ? fighter_colour(f, src[j]) : col_grey(src[j]), k);
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
    fighter_pals(f, slot_look(s), 16);
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
        if (s != 0xFF && sel_phase != SEL_FADE) {
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
 * STAGE CLEAR, the save (furthest stage, boss unlocked), BOSS UNLOCKED when its fighter was locked, the fade to the next
 * stage. After the last: CONGRATULATIONS, then the title. Players: 3 lives, a 10 s continue (START with a credit); both
 * out: GAME OVER, back to the BIOS. The attract demo plays the first stage's waves on background STAGE (make STAGE=n,
 * stages[] index) without a boss, the last wave again and again. ---- */

static uint8_t unlock_k;                         /* the boss just unlocked + 1 (0 none) */
static uint16_t phase_t;
static const gstage_t *gs;                       /* the stage playing: gstages[camp] */
static uint8_t power;                            /* this stage's enemies' extra damage */
static uint8_t pl_ch[2], pl_set[2], pl_on[2];   /* the players, carried from stage to stage (pl_on: in play) */
static uint16_t banner_t;                        /* GAME OVER on screen, frames left */

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
    snd_music(gs->boss_song);
    hud_wave();
}
static void go_sign(uint8_t on) { FIX_print(29, 3, on ? "GO -->" : "      ", 1); }   /* yellow, in the HUD's black band */
static void stage_begin(uint8_t s, uint8_t first) {
    uint8_t i;
    if (gd_want) gd_apply();                                 /* a lab's pack */
    mode = 1; nf = NE; cam_x = 0; wave = 0; banner_t = 0; camp = s; phase = PH_WAVE; phase_t = 0; gs = &gstages[s];
    inputs_reset();
    snd_music(gs->music);
    dbg_init();                                              /* the title's banner reused sprites 300-318 */
    sparks_init();
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
    if (fade_in) { fade_in++; fade_k = 0xFF; fight_fade(); } /* from black (the select screen, the last stage) */
    for (i = 0; i < NF; i++) order[i] = &fighters[i];
    for (i = 0; i < NPJ; i++) { projectiles[i].idx = NF + i; order[NF + i] = &projectiles[i]; }
    hud_reset();
    if (first) { BIOS_PLAYER_MOD[0] = attract ? 0 : 1; BIOS_PLAYER_MOD[1] = pl_on[1]; }   /* BIOS: who plays (a START then joins) */
}
static void fight_start(void) {                  /* from the select screen (pl_* set): a new game at camp_from */
    stage_begin(attract ? 0 : camp_from, 1);
}
static void attract_start(void) {
    static uint8_t pick;
    banner_hide();
    roster_build();
    if (pick >= lu_n) pick = 0;
    pl_ch[0] = lu[pick]; pl_set[0] = mod8(pick & 3, bm_chars[pl_ch[0]].nsets); pl_on[0] = 1; pl_on[1] = 0;
    pick++;
    attract = 1; attract_t = 0;
    fight_start();
}
static void select_start(void);
/* BIOS PLAYER_START filter (crt0): who may take a credit now. Title: anyone (the game starts); select, unlock and
 * ending screens: nobody; fight: a player not in play (P2 joins, a player continues or rejoins), not under GAME OVER
 * or once the stage's boss is beaten, never in the attract demo's fight (a coin ends the demo first). */
uint8_t game_start_accept(uint8_t flags) {
    if (lab.active) return 0;                                /* the Chain Lab's training: nobody joins */
    if (mode == 2 || attract) return opt_on ? 0 : flags;
    if (mode == 0) return sel_phase == SEL_CHOOSE && cursor[1] == 0xFF ? flags & 2 : 0;   /* the select: P2 joins */
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
        if (attract && wave + 1 >= gs->nwaves) { spawn_wave(); break; }   /* the demo: no boss, the last wave again */
        wave++; phase = PH_GO; phase_t = 0;
        lock_x = lock_at(wave < gs->nwaves ? gs->waves[wave].lock : gs->boss_lock);
        break;
    case PH_GO:                                              /* GO: the camera may scroll to the next lock point */
        if ((phase_t & 15) == 1) go_sign(!(phase_t & 16));   /* blinking, on from its first frame */
        if (cam_x < lock_x) break;
        go_sign(0);
        if (wave < gs->nwaves) { phase = PH_WAVE; spawn_wave(); } else boss_start();
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
        FIX_print(14, 13, "STAGE CLEAR", 0); snd_music(GAME_MUS_CLEAR);
        phase = PH_CLEAR; phase_t = 0; unlock_k = 0;
        if (attract) break;
        if (camp + 1 < GS_COUNT && save.furthest < camp + 1) save.furthest = camp + 1;
        if (gs->unlock && !(save.unlocked >> camp & 1)) { save.unlocked |= 1 << camp; unlock_k = camp + 1; }
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
        else if (camp + 1 >= GS_COUNT) ending_start();
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
    attract = 0; opt_on = 0; banner_hide(); fade_in = 0; BIOS_USER_MODE = 2;
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
    if (scr_t < (mode == 3 ? 360 : 600) && !(scr_t >= 90 && (pr & (JOY_A | JOY_B | JOY_C | JOY_D | JOY_START)))) return;
    if (mode == 4) SYS_return();                             /* the ending: back to the BIOS, which commits the MVS save
                                                                and shows the title (credits left) or the attract demo */
    else if (camp + 1 >= GS_COUNT) ending_start();
    else { fade_in = FADE_T; stage_begin(camp + 1, 0); }
}
static void select_tick(void) {
    uint8_t a, p, s;
    sel_t++;
    if (sel_phase == SEL_CHOOSE) {
        if ((bios_start & 2) && cursor[1] == 0xFF) {         /* P2 joins: START with a credit (PLAYER_START) */
            for (s = SEL_NSLOT; s-- > 0 && !(selectable(s) && SEL_SLOT[s].row == SEL_SLOT[cursor[0]].row && s != cursor[0]); ) ;
            cursor[1] = s < SEL_NSLOT ? s : cursor[0];       /* the last fighter of P1's row */
            BIOS_PLAYER_MOD[1] = 1;
            fighter_pals(actor(slot_act[cursor[1]]), 1, 16);
            select_name();
        }
        bios_start = 0;
        for (p = 0; p < 2; p++) {
            uint16_t pr = JOY_pressed(p);
            uint8_t was = cursor[p];
            if (was == 0xFF || picked[p]) continue;
            s = sel_move(was, pr);
            if (s != was) {                                  /* colours follow the cursor */
                cursor[p] = s;
                fighter_pals(actor(slot_act[was]), slot_look(was), 16);
                fighter_pals(actor(slot_act[s]), 1, 16);
                select_name();
            }
            if ((pr & (JOY_A | JOY_B | JOY_C | JOY_D)) && !(picked[p ^ 1] && cursor[p ^ 1] == cursor[p])) {
                pick_set[p] = (pr & JOY_A) ? 0 : (pr & JOY_B) ? 1 : (pr & JOY_C) ? 2 : 3;
                slot_show(cursor[p], pick_set[p]);
                fighter_play(actor(slot_act[cursor[p]]), BA_WIN_A);
                actor(slot_act[cursor[p]])->team = 0;       /* the line guard keeps the picked ones first */
                picked[p] = 1;
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
        if (!left && sel_t >= 60) { sel_phase = SEL_FADE; sel_t = 0; }
    } else {                                                 /* to black: the wall and the picked fighters */
        uint8_t k = sel_t >= FADE_T ? 0 : 16 - (uint8_t)(sel_t >> 1);
        PAL_setBackdrop(col_scale(RGB8(72, 76, 84), k));
        for (p = 0; p < 2; p++) if (cursor[p] != 0xFF) fighter_pals(actor(slot_act[cursor[p]]), 1, k);
        if (sel_t >= FADE_T + 8) {
            for (p = 0; p < 2; p++) {
                pl_on[p] = cursor[p] != 0xFF;
                if (!pl_on[p]) continue;
                pl_ch[p] = slot_ch[cursor[p]]; pl_set[p] = mod8(pick_set[p], bm_chars[pl_ch[p]].nsets);
            }
            for (a = NE; a < NA; a++) actor(a)->state = S_OFF;
            fade_in = FADE_T; fight_start(); return;
        }
    }
    for (a = 0; a < NA; a++) if (actor(a)->state != S_OFF) fighter_animate(actor(a));
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
    uint16_t i;
    gdata_init();                                            /* the game's tables (game.json) */
    routes_init();                                           /* the fighters' chain route trees (fighter.h) */
    save_load();                                             /* MVS: the BIOS restored the block (a fresh one: reset) */
    PAL_setPalette(0, TEXT_PAL);
    PAL_setBackdrop(stg->backdrop);
    for (i = 0; i < NA * MAX_COLS; i++) cmd_push(VRAM_SCB2 + SPR_BASE + i, 0x0FFF);   /* full size, set once */
    for (i = 0; i < NA; i++) block_placed[i] = MAX_COLS;                              /* clear every block once */
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
    lab_tick();
    if (!lab.active) arcade_line();
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
    if (lab.active != 1) ai_update(fighters, NF, 2, in);   /* not against the Chain Lab's dummy */
#endif
    mark(P_AI);
    for (i = 0; i < NF; i++) if (fighters[i].state != S_OFF) fighter_update(&fighters[i], &in[i]);
    if (lab.active) lab_flow(); else flow();
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
