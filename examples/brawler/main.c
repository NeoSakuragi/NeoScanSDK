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
#define SPR_BASE 60                  /* fighter blocks (stage 1-21 and shadows 22-45 behind them) */
static fighter_t fighters[NF];
static fighter_t *order[NE];                     /* back (small Z) to front, the nf entities in play */
static uint8_t nf;                               /* entities in play: the previews on the select screen, NE in the fight */
static uint8_t mode;                             /* 0 select, 1 fight, 2 title */
static uint8_t attract;                          /* the fight is the attract demo: P1 is ai_bot, enemies ai_weak */
static uint16_t attract_t;
static uint8_t tap_t[2], tap_dir[2];             /* double-tap run detection per player */
_Static_assert(STAGE_W == WORLD_W, "stage width");

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
static uint8_t level(void) { uint8_t l = BIOS_GAME_DIP[6]; return l > 7 ? 4 : l + 1; }
static uint8_t shown_level, shown_credits;               /* 0 / 0xFF after a FIX_clear: rewrite */
static void arcade_line_reset(void) { shown_level = 0; shown_credits = 0xFF; }
static void arcade_line(void) {                               /* bottom line, every screen; writes only changes */
    uint8_t l = level(), c = CREDITS_P1;
    char t[3];
    if (l != shown_level) { FIX_print(16, 27, "LEVEL-", 0); t[0] = '0' + l; t[1] = 0; FIX_print(22, 27, t, 0); shown_level = l; }
    if (c != shown_credits) {
        FIX_print(28, 27, "CREDIT", 0);
        t[0] = '0' + (c >> 4); t[1] = '0' + (c & 15); t[2] = 0; FIX_print(35, 27, t, 0); shown_credits = c;
    }
}

/* ---- stage: 21 sprites of 14 tiles; sprite s shows the stage column c with c mod 21 = s, so scrolling rewrites one
 * column's tiles each time a new column comes into view; X of all 21 is one run per frame. Behind the fighters. ---- */
#define BG_SPR 1
#define BG_N   21
#define BG_PAL 1
static uint8_t bg_shown[BG_N];
static int16_t cam_x;

static void stage_init(void) {
    uint8_t s;
    PAL_setPalette(BG_PAL, stage_pal);
    for (s = 0; s < BG_N; s++) {
        cmd_push(VRAM_SCB2 + BG_SPR + s, 0x0FFF);
        cmd_push(VRAM_SCB3 + BG_SPR + s, (496 << 7) | STAGE_ROWS);        /* top of the screen, 14 tiles */
        bg_shown[s] = 0xFF;
    }
}
static void stage_draw(void) {
    uint8_t first = (uint8_t)(cam_x >> 4), s = first, k, r;
    uint16_t *x = cmd_run(VRAM_SCB4 + BG_SPR, BG_N);
    while (s >= BG_N) s -= BG_N;
    for (k = 0; k < BG_N; k++) {
        uint8_t c = first + k;
        if (c >= STAGE_COLS) { x[s] = 320 << 7; }                         /* past the end: off screen */
        else {
            if (bg_shown[s] != c) {
                const uint16_t *t = stage_map + c * STAGE_ROWS;
                uint16_t *w = cmd_run(VRAM_SCB1 + (BG_SPR + s) * 64, STAGE_ROWS * 2);
                for (r = 0; r < STAGE_ROWS; r++) { *w++ = t[r]; *w++ = BG_PAL << 8; }
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
    if (goal < 0) goal = 0;
    if (goal > STAGE_W - 320) goal = STAGE_W - 320;
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
 * per band cost 2k cycles a fighter): the stage's 21 + every shown fighter's columns stay <= 96, and a fighter that
 * would go past is hidden this frame. Priority: players, then enemies front to back, reversed every other frame so the
 * dropped ones flicker in turn. Conservative only when fighters are vertically apart (high jump vs lying down). ---- */
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
        cols = sx < -128 || sx > 448 ? 0 : f->ncols;     /* well off screen: no sprites on any visible line */
        if (used + cols > LINE_MAX) { hidden[prio[k]] = 1; guard_hidden++; }
        else { hidden[prio[k]] = 0; used += cols; }
    }
}

/* draw: tiles for the frames that changed, then per entity block one SCB3 and one SCB4 run covering the columns its frame
 * uses and those the block showed last frame (to clear them); a hidden block is cleared once. */
static uint8_t block_placed[NE];                 /* columns each sprite block showed last frame */
/* ---- ground shadows: a dark ellipse (2 sprites, tiles SHADOW_TILE) at each entity's ground point (FLOOR_TOP + Z, also
 * under jumps and projectiles), behind every fighter (sprites 22-45 < the blocks at 60+). Entities alternate frames by
 * draw order index: each shadow shows every other frame (flicker transparency) and at most half of them (12 sprites)
 * cost sprites on a frame. ---- */
#define SH_SPR 22
#define SH_PAL 251
static const uint16_t SHADOW_PAL[16] = { 0x8000, RGB(2, 2, 5) };
static void shadow_init(void) {
    uint8_t i;
    PAL_setPalette(SH_PAL, SHADOW_PAL);
    for (i = 0; i < NE * 2; i++) {
        uint16_t *w = cmd_run(VRAM_SCB1 + (SH_SPR + i) * 64, 2);
        w[0] = SHADOW_TILE + (i & 1); w[1] = SH_PAL << 8;
        cmd_push(VRAM_SCB2 + SH_SPR + i, 0x0FFF);
    }
}
static void shadows(void) {
    static uint8_t parity;
    uint16_t *y = cmd_run(VRAM_SCB3 + SH_SPR, NE * 2), *x = cmd_run(VRAM_SCB4 + SH_SPR, NE * 2);
    uint8_t i;
    parity ^= 1;
    for (i = 0; i < NE; i++, y += 2, x += 2) {
        fighter_t *f = order[i];
        int16_t sx, gy;
        if (mode != 1 || i >= nf || hidden[i] || (i & 1) != parity || f->state == S_OFF ||
            (f->state == S_PROJ && f->frame_ovr == 0xFFFF)) { y[0] = y[1] = x[0] = x[1] = 0; continue; }
        sx = INT(f->x) - cam_x - 16; gy = FLOOR_TOP + INT(f->z) - 8;
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
    PAL_setPalette(DBG_HURT_PAL, DBG_HURT_COL); PAL_setPalette(DBG_ATK_PAL, DBG_ATK_COL);
    for (i = 0; i < DBG_BOXES * 8; i++) {
        uint16_t *w = cmd_run(VRAM_SCB1 + (DBG_SPR + i) * 64, 2);
        w[0] = CORNER_TILE + (i & 3); w[1] = (i < DBG_BOXES * 4 ? DBG_HURT_PAL : DBG_ATK_PAL) << 8;
        cmd_push(VRAM_SCB2 + DBG_SPR + i, 0x0FFF);
    }
}
static void dbg_box(uint16_t *y, uint16_t *x, const fighter_t *f, const bbox_t *b) {   /* 4 corner sprites */
    int16_t cx = INT(f->x) + (f->facing > 0 ? -b->x : b->x) - cam_x;          /* sprites face left: mirror */
    int16_t cy = FLOOR_TOP + INT(f->z) - INT(f->y) + b->y;
    int16_t l = cx - b->w, r = cx + b->w - 15, t = cy - b->h, bt = cy + b->h - 15;
    int16_t X[4] = { l, r, l, r }, Y[4] = { t, t, bt, bt };
    uint8_t k;
    for (k = 0; k < 4; k++) { y[k] = (uint16_t)((((496 - Y[k]) & 0x1FF) << 7) | 1); x[k] = (uint16_t)(X[k] & 0x1FF) << 7; }
}
static void dbg_draw(void) {
    uint16_t *y, *x;
    uint8_t i, nh = 0, na = 0;
    if (!dbg_on && !dbg_shown) return;
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
    if (mode) stage_draw();                                  /* the select screen has no stage (black) */
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

static void read_player(uint8_t p, intent_t *in, const fighter_t *f) {
    uint16_t held = JOY_held(p), pressed = JOY_pressed(p);
    in->dx = (held & JOY_RIGHT) ? 1 : (held & JOY_LEFT) ? -1 : 0;
    in->dz = (held & JOY_DOWN) ? 1 : (held & JOY_UP) ? -1 : 0;
    in->press = ((pressed & JOY_A) ? IN_A : 0) | ((pressed & JOY_B) ? IN_B : 0) | ((pressed & JOY_C) ? IN_C : 0) | ((pressed & JOY_D) ? IN_D : 0);
    if ((pressed & (JOY_A | JOY_B)) && (held & JOY_A) && (held & JOY_B)) in->press = (in->press & ~(IN_A | IN_B)) | IN_D;   /* A+B = D */
    in->run = 0; in->ai = 0; in->slow = 0;
    if (pressed & (JOY_LEFT | JOY_RIGHT)) {                     /* forward tapped twice within 12 frames */
        uint8_t d = (pressed & JOY_RIGHT) ? 1 : 2;
        if (tap_dir[p] == d && tap_t[p] < 12) in->run = 1;
        tap_dir[p] = d; tap_t[p] = 0;
    } else if (tap_t[p] < 255) tap_t[p]++;
    (void)f;
}

/* ---- HUD on the fix layer (tools/brawler/make_hud.py): P1 top left = 32x32 portrait (fix palette 2 + fighter), name,
 * KOF94-style life bar (1 px steps, red damage trail that holds 20 frames then shrinks), lives; the enemy P1 fights in
 * the same layout on the right; P2 (2-player builds) under P1. Only changed cells are written. ---- */
#define BAR_CELLS 15
#define BAR_PX    118                    /* inside the caps: 7 + 13 x 8 + 7 */
#define LIFE      60
typedef struct { uint8_t col, row, cell[BAR_CELLS], wait; int16_t px, trail; } bar_t;
static uint8_t lives[2];
static uint16_t cont_t[2];                       /* continue countdown (frames), 0 = none */
/* bars: 0 P1, 1 right block (P2, or P1's target alone), 2 P1's target under P1, 3 P2's target under P2 */
static bar_t bars[4];
static fighter_t *hud_tgt[4];
static int8_t hud_lives[2];
static uint16_t hud_cont[2];
static uint8_t hud_face[2], hud_two = 0xFF;      /* portraits shown left / right; layout (0 = one player, 1 = two) */
static uint16_t hud_tick, hud_min_spins = 0xFFFF;
static uint8_t wave;
static void fix_put(uint8_t col, uint8_t row, uint16_t v) { cmd_push(VRAM_FIX + col * 32 + row + 2, v); }
static uint8_t char_index(const bchar_t *ch) { uint8_t i; for (i = 0; i < BC_COUNT; i++) if (&bm_chars[i] == ch) return i; return 0; }
static void portrait(uint8_t col, uint8_t row, uint8_t ch) {      /* ch 0xFF = clear */
    uint8_t r, c;
    for (r = 0; r < 4; r++)
        for (c = 0; c < 4; c++)
            fix_put(col + c, row + r, ch == 0xFF ? 0x20 : (uint16_t)((2 + ch) << 12 | (PORTRAIT_TILE + ch * 16 + r * 4 + c)));
}
static void bar_draw(bar_t *b, int16_t hp) {
    int16_t px = hp <= 0 ? 0 : hp * 2 > BAR_PX ? BAR_PX : hp * 2, x0 = 0;
    uint8_t c;
    if (px < b->px && b->trail < b->px) b->trail = b->px;          /* a new hit: the trail starts at the old life */
    if (px < b->px) b->wait = 20;
    b->px = px;
    if (b->trail > px) { if (b->wait) b->wait--; else b->trail--; } else b->trail = px;
    for (c = 0; c < BAR_CELLS; c++) {
        uint8_t kind = c == 0 ? 0 : c == BAR_CELLS - 1 ? 2 : 1, w = kind == 1 ? 8 : 7, t;
        int16_t f = px - x0;
        if (f < 0) f = 0;
        if (f > w) f = w;
        t = BAR_TILE + kind * 18 + (b->trail > x0 + f ? 9 : 0) + f;
        if (b->cell[c] != t) { b->cell[c] = t; fix_put(b->col + c, b->row, t); }
        x0 += w;
    }
}
static void bar_clear(bar_t *b) {
    uint8_t c;
    for (c = 0; c < BAR_CELLS; c++) { b->cell[c] = 0; fix_put(b->col + c, b->row, 0x20); }
    b->px = b->trail = -1; b->wait = 0;
}
static void hud_reset(void) {
    static const uint8_t COL[4] = { 5, 20, 5, 20 }, ROW[4] = { 2, 2, 6, 6 };
    uint8_t p, c;
    for (p = 0; p < 4; p++) {
        bars[p].col = COL[p]; bars[p].row = ROW[p]; bars[p].px = bars[p].trail = -1; bars[p].wait = 0; hud_tgt[p] = 0;
        for (c = 0; c < BAR_CELLS; c++) bars[p].cell[c] = 0;
    }
    for (p = 0; p < 2; p++) { hud_lives[p] = -1; hud_cont[p] = 0xFFFF; hud_face[p] = 0xFE; }
    hud_two = 0xFF;
}
/* a target: name (+ portrait when it is the right block) and bar, drawn when it changes; 0 = clear */
static void hud_target(uint8_t slot, fighter_t *t, uint8_t name_col, uint8_t name_row, uint8_t face_side) {
    if (t && t->state == S_OFF) t = 0;
    if (t != hud_tgt[slot]) {
        hud_tgt[slot] = t;
        FIX_print(name_col, name_row, "          ", 0); if (t) FIX_print(name_col, name_row, t->ch->name, 0);
        if (face_side) { uint8_t f = t ? char_index(t->ch) : 0xFF; if (hud_face[1] != f) { hud_face[1] = f; portrait(35, 1, f); } }
        if (!t) bar_clear(&bars[slot]);
    }
    if (t) bar_draw(&bars[slot], t->hp);
}
#define BIOS_PLAYER_MOD ((volatile uint8_t *)0x10FDB6)   /* per player: 0 never played, 1 playing, 2 continue, 3 over */
static uint8_t p2_in(void) { return in_play(&fighters[1]) || cont_t[1]; }
static void hud(void) {
    uint8_t p, i, two = p2_in();
    if (two != hud_two) {                                    /* layout change: clear the HUD rows, redraw all */
        for (i = 0; i < 8; i++) FIX_print(1, i, "                                      ", 0);
        hud_reset(); hud_two = two;
    }
    for (p = 0; p < 1 + two; p++) {                          /* the players' blocks: P1 left, P2 right */
        fighter_t *f = &fighters[p];
        uint8_t face = char_index(f->ch), pc = p ? 35 : 1, nc = p ? 21 : 5;
        if (hud_face[p] != face) { hud_face[p] = face; portrait(pc, 1, face); FIX_print(nc, 1, "          ", 0); FIX_print(nc, 1, f->ch->name, 0); }
        bar_draw(&bars[p], in_play(f) ? f->hp : 0);
        if (lives[p] != hud_lives[p]) { hud_lives[p] = lives[p]; FIX_print(nc, 3, "x ", 0); FIX_printNum(nc + 1, 3, lives[p], 0); }
        if (cont_t[p] / 60 != hud_cont[p]) {
            hud_cont[p] = cont_t[p] / 60;
            if (cont_t[p]) { FIX_print(nc + 4, 3, "CONTINUE   ", 0); FIX_printNum(nc + 13, 3, hud_cont[p], 0); }
            else FIX_print(nc + 4, 3, "           ", 0);
        }
        if (two) hud_target(2 + p, f->target, nc, 5, 0);   /* each player's target under its own bar */
    }
    if (!two) hud_target(1, fighters[0].target, 21, 1, 1);  /* one player: its target is the right block */
    /* SNK join prompt above the empty side, and above a player who is out: INSERT COIN / PRESS START, blinking */
    if (!(hud_tick & 31)) {
        uint8_t on = !(hud_tick & 32), cr = CREDITS_P1 != 0;
        const char *msg = !on ? "           " : cr ? "PRESS START" : "INSERT COIN";
        if (!two) FIX_print(23, 0, msg, 0); else FIX_print(23, 0, "           ", 0);
        FIX_print(7, 0, in_play(&fighters[0]) ? "           " : msg, 0);
    }
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

static uint16_t title_t;
static void select_start(void);
static void title_start(void) {
    uint8_t i;
    mode = 2; nf = 0; title_t = 0; cam_x = 0;
    FIX_clear(); arcade_line_reset();
    PAL_setBackdrop(COLOR_BLACK);
    for (i = 0; i < BG_N; i++) cmd_push(VRAM_SCB3 + BG_SPR + i, 0);
    for (i = 0; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    banner_show((320 - BANNER_COLS * 16) / 2, 56);
    FIX_print(14, 24, "(C) 2027 NEOSAKURAGI", 0);
    FIX_print(17, 15, "V" GAME_VERSION, 0);                 /* VERSION, from the Makefile */
    bios_start = 0;
    snd_music(MUS_SELECT);
}
static void title_tick(void) {
    if (!(title_t & 31)) FIX_print(15, 18, (title_t & 32) ? "           " : "PRESS START", 0);
    title_t++;
    if (bios_start) { bios_start = 0; banner_hide(); select_start(); }   /* START with a credit (PLAYER_START) */
}

/* ---- character select: names on the fix layer (4 columns), each player's cursor fighter previewed on the stage. Stick
 * moves, A/B/C/D picks that colour set (KOF style) and plays the win pose; both picked: the fight starts 90 frames later
 * with the six first unpicked fighters as the enemies. ---- */
#define SEL_COLS 7                       /* portrait grid: 7 x 2 faces of 4 x 4 fix cells, a cell apart */
#define GRID_COL 3
#define GRID_ROW 17
static uint8_t cursor[2], picked[2], pick_set[2];
static uint16_t sel_t;

static void preview(uint8_t p) {
    const bchar_t *ch = &bm_chars[cursor[p]];
    fighter_init(&fighters[p], ch, pick_set[p] % ch->nsets, 16 + p * MAX_PALS, 0, p ? 230 : 90, 0);
    fighters[p].y = FIX(16);                                  /* feet above the portrait grid */
    fighters[p].facing = p ? -1 : 1; fighters[p].idx = p;
    FIX_print(p ? 26 : 3, 6, "          ", 0); FIX_print(p ? 26 : 3, 6, ch->name, 0);
}
static void grid_cell(uint8_t i, uint8_t *col, uint8_t *row) {
    uint8_t r = 0;
    while (i >= SEL_COLS) { i -= SEL_COLS; r++; }
    *col = GRID_COL + i * 5; *row = GRID_ROW + r * 5;
}
/* cursor brackets: the debug viewer's corner sprites (P1 = 340-343 red, P2 = 300-303 green), hugging the face from
 * outside (the fix layer covers sprites, so the brackets show in the gap around it) */
static void select_cursor(uint8_t p) {
    uint16_t spr = p ? DBG_SPR : DBG_SPR + DBG_BOXES * 4;
    uint8_t col, row, k;
    int16_t px, py;
    if (cursor[p] == 0xFF) { for (k = 0; k < 4; k++) cmd_push(VRAM_SCB3 + spr + k, 0); return; }
    grid_cell(cursor[p], &col, &row);
    px = col * 8; py = row * 8;
    for (k = 0; k < 4; k++) {
        int16_t x = (k & 1) ? px + 20 : px - 4, y = (k & 2) ? py + 20 : py - 4;
        cmd_push(VRAM_SCB3 + spr + k, (uint16_t)((((496 - y) & 0x1FF) << 7) | 1));
        cmd_push(VRAM_SCB4 + spr + k, (uint16_t)(x & 0x1FF) << 7);
    }
}
static void select_cursors_hide(void) {
    uint8_t k;
    for (k = 0; k < 4; k++) { cmd_push(VRAM_SCB3 + DBG_SPR + k, 0); cmd_push(VRAM_SCB3 + DBG_SPR + DBG_BOXES * 4 + k, 0); }
}
static void select_start(void) {
    uint8_t p, i, col, row;
    mode = 0; nf = 1; sel_t = 0; cam_x = 0; attract = 0; ai_weak = 0;
    snd_music(MUS_SELECT);
    FIX_clear(); arcade_line_reset();
    PAL_setBackdrop(COLOR_BLACK);
    for (i = 0; i < BG_N; i++) cmd_push(VRAM_SCB3 + BG_SPR + i, 0);                 /* stage sprites hidden */
    dbg_init();                                                                      /* corner sprites (the banner used 300-318) */
    FIX_print(10, 3, "SELECT YOUR FIGHTER", 0);
    FIX_print(3, 26, "STICK MOVES   A B C D PICK COLOURS", 0);   /* keyboard: WASD, U I O P */
    for (i = 0; i < BC_COUNT; i++) { grid_cell(i, &col, &row); portrait(col, row, i); }
    for (p = 0; p < 2; p++) { cursor[p] = p; picked[p] = 0; pick_set[p] = 0; preview(p); order[p] = &fighters[p]; }
    cursor[1] = 0xFF; fighters[1].state = S_OFF; FIX_print(26, 6, "          ", 0);   /* P2 joins in the fight */
    for (i = 2; i < NF; i++) fighters[i].state = S_OFF;
    for (i = 0; i < NPJ; i++) projectile_reset(&projectiles[i]);
    select_cursor(0); select_cursor(1);
}
/* ---- the fight: WAVES waves of six enemies (the fighters nobody picked, in turn) walking in from the right; a dead
 * enemy blinks out; a dead player uses a life, then gets a 10 s continue (any button); all enemies of the last wave
 * gone: STAGE CLEAR; both players out: GAME OVER. Both end back on the select screen. ---- */
#define WAVES     3
#define CONTINUE  600
static uint8_t avail[BC_COUNT], navail;          /* fighters nobody picked: the enemies */
static uint16_t banner_t;                        /* STAGE CLEAR / GAME OVER on screen, frames left */

static uint8_t mod8(uint8_t a, uint8_t b) { while (a >= b) a -= b; return a; }   /* no libgcc: no 32-bit % */
static void spawn_wave(void) {
    uint8_t k;
    for (k = 0; k < NF - 2; k++) {
        fighter_t *e = &fighters[2 + k];
        const bchar_t *ch = &bm_chars[avail[mod8(wave * 3 + k, navail)]];
        int16_t x = (wave ? cam_x + 340 : 230) + k * (wave ? 36 : 70);
        if (x > WORLD_W - 16) x = WORLD_W - 16 - (k & 3) * 20;
        fighter_init(e, ch, mod8(wave + k, ch->nsets), 16 + (2 + k) * MAX_PALS, 1, x, 6 + k * 11);
        e->idx = 2 + k;
    }
    ai_init(0x1D2B + wave);
    FIX_print(2, 26, "WAVE   ", 0); FIX_printNum(7, 26, wave + 1, 0);
}
static void fight_start(void) {
    uint8_t i, c;
    mode = 1; nf = NE; cam_x = 0; wave = 0; banner_t = 0; navail = 0;
    snd_music(MUS_FIGHT);
    select_cursors_hide();
    dbg_init();                                              /* the title's banner reused sprites 300-318 */
    sparks_init();
    FIX_clear(); arcade_line_reset();
    PAL_setBackdrop(RGB8(40, 60, 90));
    stage_init();                                            /* stage sprites back, every column rewritten */
    if (cursor[0] == cursor[1] && pick_set[0] % bm_chars[cursor[0]].nsets == pick_set[1] % bm_chars[cursor[1]].nsets)
        pick_set[1]++;                                       /* same fighter, same colours: P2 takes the next set */
    for (i = 0; i < 2; i++) {
        const bchar_t *ch = &bm_chars[i == 0 ? cursor[0] : 0];
        fighter_init(&fighters[i], ch, pick_set[i] % ch->nsets, 16 + i * MAX_PALS, 0, i ? 40 : 60, i ? 10 : 40);
        fighters[i].idx = i; lives[i] = 3; cont_t[i] = 0;
        if (i) { fighters[i].state = S_OFF; lives[i] = 0; }  /* P2 joins with START (in the fight) */
    }
    for (c = 0; c < BC_COUNT; c++) if (c != cursor[0] && c != cursor[1]) avail[navail++] = c;
    spawn_wave();
    for (i = 0; i < NF; i++) order[i] = &fighters[i];
    for (i = 0; i < NPJ; i++) { projectile_reset(&projectiles[i]); projectiles[i].idx = NF + i; order[NF + i] = &projectiles[i]; }
    hud_reset();
    BIOS_PLAYER_MOD[0] = attract ? 0 : 1; BIOS_PLAYER_MOD[1] = 0;   /* BIOS: who plays (a START then joins, not restarts) */
}
static void attract_start(void) {
    static uint8_t pick;
    banner_hide();
    cursor[0] = pick; cursor[1] = 0xFF; pick_set[0] = pick & 3;
    if (++pick >= BC_COUNT) pick = 0;
    attract = 1; attract_t = 0; ai_weak = 1;
    fight_start();
}
static void select_start(void);
/* BIOS PLAYER_START filter (crt0): who may take a credit now. Title: anyone (the game starts); select: nobody; fight:
 * a player not in play (P2 joins, a player continues or rejoins), not under a STAGE CLEAR / GAME OVER banner, never
 * in the attract demo's fight (a coin ends the demo first). */
uint8_t game_start_accept(uint8_t flags) {
    if (mode == 2 || attract) return flags;
    if (mode == 0 || banner_t) return 0;
    return flags & ((in_play(&fighters[0]) ? 0 : 1) | (in_play(&fighters[1]) ? 0 : 2));
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
        for (c = 0; c < BC_COUNT; c++) {                     /* a fighter nobody on screen is */
            used = &bm_chars[c] == fighters[0].ch;
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
    if (!left) {
        if (++wave < WAVES) spawn_wave();
        else { FIX_print(14, 13, "STAGE CLEAR", 0); banner_t = 240; snd_music(MUS_JINGLE); }
    }
}
static void select_tick(void) {
    uint8_t p, moved = 0;
    for (p = 0; p < 1; p++) {
        uint16_t pr = JOY_pressed(p);
        if (!picked[p]) {
            int8_t c = cursor[p];
            if (pr & JOY_LEFT) c--;
            if (pr & JOY_RIGHT) c++;
            if (pr & JOY_UP) c -= SEL_COLS;
            if (pr & JOY_DOWN) c += SEL_COLS;
            while (c < 0) c += BC_COUNT;
            while (c >= BC_COUNT) c -= BC_COUNT;
            if (c != cursor[p]) { cursor[p] = c; preview(p); moved = 1; }
            if (pr & (JOY_A | JOY_B | JOY_C | JOY_D)) {
                pick_set[p] = (pr & JOY_A) ? 0 : (pr & JOY_B) ? 1 : (pr & JOY_C) ? 2 : 3;
                preview(p); fighter_play(&fighters[p], BA_WIN_A); picked[p] = 1;
                FIX_print(p ? 30 : 4, 7, "OK", 0);
            }
        }
        fighter_animate(&fighters[p]);
    }
    if (moved) { select_cursor(0); select_cursor(1); }
    if (picked[0] && ++sel_t >= 90) fight_start();
}

void game_init(void) {
    uint8_t i;
    PAL_setPalette(0, TEXT_PAL);
    PAL_setBackdrop(RGB8(40, 60, 90));
    for (i = 0; i < NE * MAX_COLS; i++) cmd_push(VRAM_SCB2 + SPR_BASE + i, 0x0FFF);   /* full size, set once */
    for (i = 0; i < NE; i++) block_placed[i] = MAX_COLS;                              /* clear every block once */
    stage_init();
    snd_cmd(0x07);                                           /* KOF98's driver: music unlock */
}

/* MVS protocol (sdk/boot/crt0.s): request 2 = attract demo, 3 = title (a coin went in) */
static void attract_start(void);
void game_enter(uint8_t request) {
    BIOS_USER_MODE = 1;                                      /* title / demo (game_init ran on request 0) */
    { uint8_t k; for (k = 0; k < 10; k++) TEXT_PAL[6 + k] = bar_colours[k];
      PAL_setPalette(0, TEXT_PAL);                           /* the BIOS's own screens overwrite palette 0 */
      for (k = 0; k < BC_COUNT; k++) PAL_setPalette(2 + k, portrait_pal[k]); }   /* fix palettes 2-15: portraits */
    shadow_init();
    dbg_init();
    if (request == 3) title_start(); else attract_start();
    depth_sort();
    draw();
    SYS_vblankFlush();
}

void game_tick(void) {
    static intent_t in[NF];
    uint8_t i;
    prof_t = LINE();
    SYS_vblankFlush();              /* we are in vblank: last tick's VRAM commands go out now, tear-free (1 frame latency) */
    mark(P_FLUSH);
    SYS_kickWatchdog();
    snd_tick();
    arcade_line();
    if (mode == 2) { title_tick(); if (mode == 2) return; }
    if (!mode) { select_tick(); depth_sort(); draw(); return; }
    if (attract) {                                           /* the demo: a coin, 40 s or a game over ends it */
        if (bios_demo_end || ++attract_t > 2400) { SYS_return(); }
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
    camera();
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
