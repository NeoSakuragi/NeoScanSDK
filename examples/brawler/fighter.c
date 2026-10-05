/* Beat 'em up fighter: state machine, combo routes, hit reactions, combat and rendering (see fighter.h).
 * Animation semantics are KOF's: a step shows a frame for N ticks; "hold" animations stop on their last step.
 * The 68000 has no 32-bit multiply/divide (and there is no libgcc here): only adds, shifts and dir_mul(). */
#include <neoscan.h>
#include "neo_internal.h"
#include "fighter.h"
#include "sound.h"
#include "game_tables.h"
#include "snd/voices.h"

/* draw.s reads these structures at fixed offsets (its .equ list): the build stops if a field moves */
#include <stddef.h>
_Static_assert(offsetof(fighter_t, ch) == 0 && offsetof(fighter_t, palbase) == 5 && offsetof(fighter_t, spr) == 6, "draw.s F_CH/F_PALBASE/F_SPR");
_Static_assert(offsetof(fighter_t, x) == 8 && offsetof(fighter_t, z) == 12 && offsetof(fighter_t, y) == 16, "draw.s F_X/F_Z/F_Y");
_Static_assert(offsetof(fighter_t, facing) == 32 && offsetof(fighter_t, anim) == 38 && offsetof(fighter_t, step) == 39, "draw.s F_FACING/F_ANIM/F_STEP");
_Static_assert(offsetof(fighter_t, shown_frame) == 56 && offsetof(fighter_t, shown_facing) == 58 && offsetof(fighter_t, frame_ovr) == 60, "draw.s F_SHOWN_*/F_FRAME_OVR");
_Static_assert(offsetof(fighter_t, ncols) == 94, "draw.s F_NCOLS");
_Static_assert(offsetof(bchar_t, frames) == 10 && offsetof(bchar_t, anims) == 14 && offsetof(bchar_t, tile_hi) == 60, "draw.s CH_*");
_Static_assert(offsetof(banim_t, steps) == 2 && offsetof(bframe_t, nparts) == 0 && offsetof(bframe_t, parts) == 2, "draw.s AN_STEPS/FR_*");
_Static_assert(offsetof(bpart_t, dx) == 0 && offsetof(bpart_t, dy) == 2 && offsetof(bpart_t, cols) == 4 && offsetof(bpart_t, rows) == 5 &&
               offsetof(bpart_t, hflip) == 6 && offsetof(bpart_t, vflip) == 7 && offsetof(bpart_t, pal) == 8 &&
               offsetof(bpart_t, tiles) == 10 && sizeof(bpart_t) == 14, "draw.s PT_*");

#define GRAVITY_KD  0x5000        /* knockdown gravity 0.31 px/frame^2 (KOF95: 0.47): higher, slower falls to juggle */
#define DOWN_FRAMES 40
#define INV_GETUP   30
#define HITSTOP     7             /* hit-stop frames, the same for every hit (Bruno 2026-10-04; KOF98 counts +$124 from 7 to 11 by move) */
#define STUN_LIGHT  36            /* hitstun frames: 3x a fighting game's, a beat 'em up keeps its victims in the chain */
#define STUN_HEAVY  54
#define AI_IDLE_DELAY 10          /* AI fighters stop walking into idle only after this many frames without a walk intent */
#define CHAIN_WINDOW 30           /* frames after a route step that hit during which A / B continues the route (Final Fight) */
#define RUN_MUL     2             /* run = walk << 1 */
/* KOF's walk / run / jump speeds rounded to whole pixels a frame (Terry walks 3.17 -> 3): the Neo Geo scrolls in whole
 * pixels, so a fractional speed made the camera step 3,3,3,4,3,... and the background lurch every ~6 frames (very
 * visible on a tablet, 7 screen pixels per game pixel); at least 1 px */
static int32_t whole(int32_t v) { int32_t w = (v + 0x8000) & ~0xFFFFL; return w ? w : 0x10000; }
#define X_MIN 16
#define X_MAX (world_w - 16)

static const char *NAMES[S_COUNT] = { "IDLE    ", "WALK    ", "RUN     ", "PREJUMP ", "AIR     ", "LAND    ", "ATTACK  ",
    "AIR ATK ", "HITSTUN ", "KNOCKDN ", "DOWN    ", "GETUP   ", "GRAB    ", "GRABBED ", "THROW   ", "THROWN  ", "SPECIAL ", "DEAD    ", "PROJ    ", "OFF     " };
const char *fighter_state_name(uint8_t st) { return NAMES[st]; }

/* ---- chain routes (fighter.h "chain routes"): each fighter's tree, through route_tab[] (RAM) ------------------------
 * The default tree (routes.py default_tree, every fighter without a routes file; TODO #71: one attack button): far A -A->
 * far A -A-> close C -A-> close D -A-> C+D (knockdown); far A, far A -down-forward+A-> far D (launch); far A -B-> a
 * jump-cancel (air C -A-> air C+D); close A: close B -A-> far C -A-> sweep (trip); forward+A = body toss, down+A = sweep
 * inside any window; the six A+B slots = the special the input picks, cancelling a normal that hit. Air: A / down+A /
 * up+A. */
const rt_head_t *route_tab[BC_COUNT];
lab_t lab;
const uint8_t *spec_tab[BC_COUNT];
void specs_init(void) { uint8_t i; for (i = 0; i < BC_COUNT; i++) spec_tab[i] = bm_chars[i].spmap; }
/* voices (TODO #55): voice_tab[fighter] = its voice table (bchar_t.voices, or a data pack's: main.c gd_apply), [id, at]
 * per VK_* key; snd/voices.h (tools/port/build_snd.py) turns an id into the driver code of the sample in this V ROM (0:
 * not in it, silent). A key fires where its move reaches `at`: an animation step entered (KOF's $FC record sits before
 * it), a special's or a throw's script row reached; the events at once. Players send VOICE_PREFIX_PLAYER, enemies
 * VOICE_PREFIX_ENEMY: two effect slots, so an enemy's voice never cuts the player's. The select screen's previews are mute. */
const uint8_t *voice_tab[BC_COUNT];
static const uint8_t *const vcodes[BC_COUNT] = VOICE_CODES;
static const uint8_t vncodes[BC_COUNT] = VOICE_NCODES;
static uint8_t mute;                                         /* fighter_play / fighter_animate: previews */
void voices_init(void) { uint8_t i; for (i = 0; i < BC_COUNT; i++) voice_tab[i] = bm_chars[i].voices; }
void voice_play(const bchar_t *ch, uint8_t team, uint8_t key) {
    uint8_t id = voice_tab[ch->id][key * 2];
    if (id && id < vncodes[ch->id]) snd_voice(team ? VOICE_PREFIX_ENEMY : VOICE_PREFIX_PLAYER, vcodes[ch->id][id]);
}
static void voice_at(const fighter_t *f, uint8_t key, uint16_t from, uint16_t to) {   /* `at` in [from, to] */
    const uint8_t *e = voice_tab[f->ch->id] + key * 2;
    if (!mute && e[0] && f->state != S_PROJ && e[1] >= from && e[1] <= to) voice_play(f->ch, f->team, key);
}
uint8_t spec_ix(const bchar_t *ch, uint8_t role) { uint8_t k = role == BS_FURY ? ch->fury : spec_tab[ch->id][role]; return k < ch->nspec ? k : 0xFF; }
void routes_init(void) { uint8_t i; for (i = 0; i < BC_COUNT; i++) route_tab[i] = (const rt_head_t *)bm_chars[i].routes; }
void lab_install(void) {
    const rt_head_t *t = (const rt_head_t *)lab.buf;
    if (!lab.load) return;
    if (lab.fighter < BC_COUNT) {
        if (lab.load == 1 && t->magic[0] == 'R' && t->magic[1] == 'T' && t->version == TREE_VERSION) route_tab[lab.fighter] = t;
        else route_tab[lab.fighter] = (const rt_head_t *)bm_chars[lab.fighter].routes;
    }
    lab.load = 0;
}
#define TREE(f)    ((f)->tree ? (f)->tree : route_tab[(f)->ch->id])   /* an enemy's own tree, else its fighter's */
#define NODE(f, i) RT_NODE(TREE(f), i)
static void lab_note(const fighter_t *f, uint8_t kind, uint8_t node, uint8_t how, uint8_t val) {   /* P1's route steps */
    lab_ev_t *e;
    if (!lab.active || f->idx || f->team || f->state == S_PROJ) return;
    e = &lab.ev[lab.nev & (LAB_NEV - 1)];
    e->frame = lab.frame; e->kind = kind; e->node = node; e->how = how; e->val = val;
    lab.nev++;
}

/* ---- animation player (2026-10-05: KOF-exact, with a speed) ---------------------------------------------------------
 * KOF shows a step for its ticks + 1 frames (measured: the brawler showed ticks, the first step ticks - 1: Terry's
 * normals 17-43 % fast). Time is kept in 1/256 frames: f->acc = time spent in the current step, f->speed added once a
 * frame (8.8: 0x0100 = KOF's timing; play() sets it, a route node its own), a step left when acc reaches its
 * (ticks + 1) << 8, the remainder carried (no drift). The time is added at the start of the fighter's update, so the
 * frame an animation starts on is its first frame, whatever started it (the state machine, or a hit in combat()); a
 * hold animation's anim_done comes the frame after its last step's last frame: the state machine leaves it then, as
 * KOF does. Impact protection: an active step (bstep_t flags & 1; the ones opening a hit, flags & 4, among them) is
 * never skipped: an advance that would pass it within one frame stops on it, so it shows and combat() checks its box
 * that frame (measured: stopping only on the openers lost Terry's Crack Shoot's first hit at 4x, which lands on a
 * later live row of its window). Hit-stop
 * (f->freeze) stops time; it is not scaled. Below 1x the steps just last longer. */
static void clamp(fighter_t *f);
static void step_move(fighter_t *f) {                         /* KOF's per-step move ($FB): attacks travel as in KOF */
    int8_t dx = f->ch->anims[f->anim].steps[f->step].dx;
    if (dx && (f->state == S_ATTACK || f->state == S_AIR_ATTACK)) { f->x += f->facing > 0 ? FIX(dx) : -FIX(dx); clamp(f); }
    if (f->state == S_ATTACK) f->y = FIX(f->ch->anims[f->anim].steps[f->step].hy);   /* ground attacks: 0, hops: the game's */
}
static void play(fighter_t *f, uint8_t anim) {
    f->anim = anim; f->step = 0; f->anim_done = 0; f->acc = 0; f->speed = 0x100;
    step_move(f); voice_at(f, anim, 0, 0);
}
static void play_if_new(fighter_t *f, uint8_t anim) { if (f->anim != anim) play(f, anim); }
static void anim_tick(fighter_t *f) {
    const banim_t *an = &f->ch->anims[f->anim];
    f->acc += f->speed;
    for (;;) {
        uint32_t d = (uint32_t)(an->steps[f->step].ticks + 1) << 8;
        if (f->acc < d) return;
        if (f->step + 1 < an->nsteps) { f->acc -= d; f->step++; }
        else {                                                   /* loops report one pass done too */
            f->anim_done = 1;
            if (an->hold) { f->acc = d; return; }                /* held on its last step */
            f->acc -= d; f->step = 0;
        }
        step_move(f); voice_at(f, f->anim, f->step, f->step);
        if (an->steps[f->step].flags & 4) f->hit_mask = 0;       /* multi-hit normals: a new hit window */
        if (an->steps[f->step].flags & 1) {                      /* an active step is never skipped: shown, its box checked */
            d = (uint32_t)(an->steps[f->step].ticks + 1) << 8;
            if (f->acc >= d) f->acc = d - 1;
            return;
        }
    }
}
const bstep_t *fighter_step(const fighter_t *f) { return &f->ch->anims[f->anim].steps[f->step]; }
void fighter_play(fighter_t *f, uint8_t anim) { mute = 1; play(f, anim); mute = 0; }
void fighter_animate(fighter_t *f) { mute = 1; anim_tick(f); mute = 0; }

/* ---- helpers --------------------------------------------------------------------------------------------------- */
static int32_t dir_mul(int8_t d, int32_t v) { return d > 0 ? v : d < 0 ? -v : 0; }
static void enter(fighter_t *f, uint8_t st) {
    f->state = st; f->state_t = 0;
    if (st != S_KNOCKDOWN && st != S_HITSTUN) { f->kmode = f->kdelay = 0; f->kvfr = 0; }   /* KOF's reaction (kof_react) ends */
}
static void clamp(fighter_t *f) {
    if (f->x < FIX(X_MIN)) f->x = FIX(X_MIN);
    if (f->x > FIX(X_MAX)) f->x = FIX(X_MAX);
    if (f->z < 0) f->z = 0;
    if (f->z > FIX(Z_DEPTH)) f->z = FIX(Z_DEPTH);
}
static void to_neutral(fighter_t *f, const intent_t *in) {
    if (in && (in->dx || in->dz)) { f->still = 0; enter(f, S_WALK); play_if_new(f, BA_WALK_FWD); }
    else if (in && in->ai && f->state == S_WALK && ++f->still < AI_IDLE_DELAY) { }   /* AI: no walk/idle flicker */
    else { enter(f, S_IDLE); play_if_new(f, BA_IDLE); }
}
static uint8_t hit_sound(uint8_t anim) {                       /* KOF98's hit sound per button */
    switch (anim) {
    case BA_ATK_A_CLOSE: case BA_ATK_A_FAR: case BA_ATK_A_CROUCH: case BA_CMD_FWD_A: return SFX_HIT_A;
    case BA_ATK_B_CLOSE: case BA_ATK_B_FAR: case BA_ATK_B_CROUCH: case BA_CMD_FWD_B: return SFX_HIT_B;
    case BA_ATK_C_CLOSE: case BA_ATK_C_FAR: case BA_ATK_C_JUMP: case BA_ATK_C_CROUCH: case BA_CMD_DF_C: return SFX_HIT_C;
    case BA_ATK_D_CLOSE: case BA_ATK_D_FAR: case BA_ATK_D_CROUCH: case BA_ATK_D_JUMP: case BA_CMD_DF_D: return SFX_HIT_D;
    default: return SFX_HIT_CD;
    }
}
/* ---- jumps (tools/kof96/capture/jumps.py, KOF96/98/99 measured 2026-10-04) ------------------------------------------
 * Two heights, KOF's: C held through the prejump = the regular jump, C released before take-off = the hop (3/4 of the
 * launch speed, same gravity and horizontal speed: bphys_t, from the ROM). Each kind and direction has its own animations
 * (Terry's forward / back jump is a somersault, his hops are the tuck), and its own air normals: a regular jump plays the
 * vertical normal straight up, the diagonal one forward or back; a hop plays KOF98/99's hop normals (KOF96: the jump's). */
static const uint8_t JUMP_ANIM[2][3][2] = {                   /* [kind][up, forward, back][rise, fall] */
    { { BA_JUMP_UP_RISE, BA_JUMP_UP_FALL }, { BA_JUMP_FWD_RISE, BA_JUMP_FWD_FALL }, { BA_JUMP_BACK_RISE, BA_JUMP_BACK_FALL } },
    { { BA_HOP_UP_RISE, BA_HOP_UP_FALL }, { BA_HOP_FWD_RISE, BA_HOP_FWD_FALL }, { BA_HOP_BACK_RISE, BA_HOP_BACK_FALL } } };
static const uint8_t AIR_NORMAL[2][2][2] = {                  /* [kind][vertical, diagonal][air A = C, air B = D] */
    { { BA_ATK_C_JUMP, BA_ATK_D_JUMP }, { BA_ATK_C_JUMP_DIAG, BA_ATK_D_JUMP_DIAG } },
    { { BA_ATK_C_HOP, BA_ATK_D_HOP }, { BA_ATK_C_HOP_DIAG, BA_ATK_D_HOP_DIAG } } };

static void start_node(fighter_t *f, uint8_t node, uint8_t how) {
    const rnode_t *c = NODE(f, node);
    uint8_t a = c->anim;
    snd_sfx(a == BA_ATK_A_CLOSE || a == BA_ATK_A_FAR || a == BA_ATK_A_CROUCH || a == BA_ATK_C_CLOSE || a == BA_ATK_C_FAR ||
            a == BA_ATK_C_JUMP ? SFX_SWING_LIGHT : SFX_SWING_HEAVY);
    f->node = node; f->buffered = 0; f->hit_mask = 0; f->landed = 0; f->chain_t = 0; f->spec_buf = 0;
    if (c->flags & RF_AIR) {                                     /* the jump in progress picks the air normal */
        if (a == BA_ATK_CD_JUMP) a = f->jump_kind ? BA_ATK_CD_HOP : BA_ATK_CD_JUMP;   /* KOF's 117, a KOF98 / 99 hop's 124 */
        else a = AIR_NORMAL[f->jump_kind][f->jump_dir != 0][a == BA_ATK_D_JUMP];
    }
    lab_note(f, LE_START, node, how, 0);
    enter(f, (c->flags & RF_AIR) ? S_AIR_ATTACK : S_ATTACK); play(f, a);
    f->speed = c->speed;                                         /* the node's speed (play() set 1x) */
}
/* a press as a route reads it (TODO #71): IN_A | 0x80 forward | 0x40 down | 0x20 back | 0x10 close (an opponent within
 * CLOSE_X), or IN_B (the jump-cancel link) */
static uint8_t combo_input(const fighter_t *f, const intent_t *in) {
    uint8_t b = (in->press & IN_A) ? IN_A : (in->press & IN_B) ? IN_B : 0;
    if (b != IN_A) return b;
    if (in->dx == f->facing) b |= 0x80; else if (in->dx) b |= 0x20;
    if (in->dz > 0) b |= 0x40;
    if (in->close) b |= 0x10;
    return b;
}
/* the link an input takes: B its B link; A the exact one, else down-forward -> forward -> down -> back -> close -> plain
 * (a plain A always continues a route whatever the stick does) */
static uint8_t next_node(const rnode_t *c, uint8_t b) {
    if (b & IN_B) return c->next[RI_B];
    if ((b & 0xC0) == 0xC0 && c->next[RI_DFA]) return c->next[RI_DFA];
    if ((b & 0x80) && c->next[RI_FA]) return c->next[RI_FA];
    if ((b & 0x40) && c->next[RI_DA]) return c->next[RI_DA];
    if ((b & 0x20) && c->next[RI_BA]) return c->next[RI_BA];
    if ((b & 0x10) && c->next[RI_CA]) return c->next[RI_CA];
    return c->next[RI_A];
}
static uint8_t has_links(const rnode_t *c) { uint8_t k, n = 0; for (k = RI_A; k <= RI_DFA; k++) n |= c->next[k]; return n; }
static uint8_t d_input(const fighter_t *f, const intent_t *in) {  /* A+B's direction, as special_for reads it: a diagonal */
    uint8_t fwd = in->dx == f->facing;                           /* only with the stick toward the facing (down-back = down) */
    return in->dz > 0 ? (fwd ? RI_DFS : RI_DS) : in->dz < 0 ? (fwd ? RI_UFS : RI_US) : in->dx ? RI_FS : RI_S;
}
/* B: the jump, the stick picks the direction (pressed away from the facing: KOF's back jump; the fighter keeps facing);
 * air_node: a jump-cancel's route node (fighter_t.air_node), 0 a plain jump */
static void jump_start(fighter_t *f, const intent_t *in, uint8_t air_node) {
    f->jump_dir = !in->dx ? 0 : in->dx == f->facing ? 1 : 2;
    f->jump_kind = 0; f->vx = 0; f->vz = dir_mul(in->dz, FIX(1)); f->air_node = air_node;
    enter(f, S_PREJUMP); play(f, BA_PREJUMP);
}
/* a route's next node: B's is a jump-cancel (its node waits for A in the air), any other starts now */
static void route_go(fighter_t *f, uint8_t node, uint8_t b, const intent_t *in, uint8_t how) {
    if (b & IN_B) jump_start(f, in, node); else start_node(f, node, how);
}

/* ---- the special meter (TODO #71, Bruno 2026-10-05; gamedata.h gmeter_t <- game.json "meter") -----------------------
 * Players only (enemies spend nothing): full at the start and at a new life, a point back every gmeter.refill frames.
 * An A+B special costs gmeter.special, a fury (C) gmeter.fury and needs gmeter.fury_min; a special out of a hit (in
 * hitstun, or held: "get out of trouble") costs gmeter.hit_mul times as much and the fighter's palettes flash fully
 * white for gmeter.flash frames. Not enough meter: the press does nothing. */
static const uint16_t WHITE_PAL[16] = { 0x8000, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF,
                                        0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF };
static void set_burn(fighter_t *f, uint8_t burn);
static uint8_t spend(fighter_t *f, uint16_t cost, uint16_t need, uint8_t hit) {
    uint8_t i;
    if (f->team) return 1;
    if (hit) { uint16_t c = cost; for (i = 1; i < gmeter.hit_mul; i++) cost += c; }
    if (need < cost) need = cost;
    if (f->meter < need) return 0;
    f->meter -= cost; f->meter_t = 0;
    if (hit && gmeter.flash) {
        for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) PAL_setPalette(f->palbase + i, WHITE_PAL);
        f->flash = gmeter.flash;
    }
    return 1;
}
static void meter_tick(fighter_t *f) {
    if (f->flash && !--f->flash) { uint8_t b = f->burn; f->burn = 0xFF; set_burn(f, b); }   /* its colours back (burnt: the burn's) */
    if (!f->team && f->meter < gmeter.max && ++f->meter_t >= gmeter.refill) { f->meter++; f->meter_t = 0; }
}

void fighter_revive(fighter_t *f) {
    f->hp = 60; f->held = 0; f->frame_ovr = 0xFFFF; f->y = 0; f->vx = f->vy = f->vz = 0; f->meter = gmeter.max;
    enter(f, S_GETUP); play(f, BA_GETUP); f->inv = 90;
}

/* ---- reactions -------------------------------------------------------------------------------------------------------- */
static void release(fighter_t *a);
static void special_end(fighter_t *f);
/* KOF98's hit effects (P-ROM, decoded 2026-10-04): a move sets its hit kind in the attacker (+$1B8) and the victim
 * plays the kind's handler (jump table $1E208) on the hit: sound indices through the table at $A9BCE, all $1A + code.
 * Two codes (the second 0: one); kinds 4, 5, 17 pick one of two at random in the game (the first kept here); 0, 6
 * and 13 go through further tables (not decoded: the heavy hit, 13 adds the fire crackle). Fire: kind 11 = $13 + $2E. */
static const uint8_t HIT_SFX[33][2] = {
    {0x13, 0}, {0x13, 0}, {0x14, 0}, {0x15, 0}, {0x11, 0}, {0x12, 0}, {0x13, 0}, {0x37, 0}, {0x7A, 0}, {0x7C, 0},
    {0x12, 0}, {0x13, 0x2E}, {0x61, 0}, {0x13, 0x2E}, {0x13, 0x3D}, {0x19, 0}, {0x3D, 0}, {0x2A, 0}, {0x15, 0x42},
    {0x69, 0}, {0x2B, 0}, {0x2E, 0}, {0x31, 0}, {0x4D, 0}, {0x17, 0}, {0x15, 0x42}, {0x15, 0x42}, {0x15, 0x42},
    {0x42, 0}, {0x9C, 0}, {0x42, 0}, {0x42, 0}, {0xEB, 0} };
static void hit_sfx(uint8_t fx) {
    const uint8_t *s = HIT_SFX[(fx & 0x3F) < 33 ? fx & 0x3F : 1];
    snd_sfx(s[0]); if (s[1]) snd_sfx(s[1]);
}
/* burn: the victim of a fire hit shows KOF98's burn palette in its attacker's flame colour (palette RAM $5F purple,
 * Iori; $58 orange, Kyo; both loaded for the whole fight: VRAM during their Oniyaki hits) in place of its own, colour
 * index for colour index, through its hit reaction and its fall until it hits the floor (screenshots: burnt in 262,
 * 285, 287, its own colours from 309 on) */
static const uint16_t BURN_PAL[2][16] = {
    { 0x0000, 0x2CA9, 0x7975, 0x3864, 0x0764, 0x1653, 0x4443, 0x4332, 0x5221, 0x6111, 0x4011, 0x7FFF, 0x3FCF, 0x7C9F, 0x385F, 0x143A },
    { 0x0000, 0x7FC7, 0x0A85, 0x1974, 0x1863, 0x5652, 0x4542, 0x4431, 0x5320, 0x4210, 0x6100, 0x7FFF, 0x4FF9, 0x0FA4, 0x6C60, 0x6830 } };
static void set_burn(fighter_t *f, uint8_t burn) {
    uint8_t i;
    if (f->burn == burn) return;
    f->burn = burn;
    if (f->flash) return;                                        /* white: its colours come back when the flash ends */
    if (!burn) { fighter_load_pals(f); return; }
    for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) PAL_setPalette(f->palbase + i, BURN_PAL[burn - 1]);
}
/* minion tints (Bruno 2026-10-05: minions never in a playable colour set): the set's colour pulled toward its luminance
 * (5 R + 9 G + 2 B) / 16 by the tint's numbers (gamedata.h gtint_t, game.json "tints": shade, ash, rust); colour 0
 * (transparent) untouched */
static __attribute__((noinline)) uint16_t tint_colour(uint8_t tint, uint16_t c) {
    int16_t v[3], l;
    uint8_t k;
    const gtint_t *t = &gtints[tint];
    v[0] = ((c >> 7) & 0x1E) | ((c >> 14) & 1); v[1] = ((c >> 3) & 0x1E) | ((c >> 13) & 1); v[2] = ((c << 1) & 0x1E) | ((c >> 12) & 1);
    l = (v[0] * 5 + v[1] * 9 + v[2] * 2) >> 4;
    for (k = 0; k < 3; k++) {
        int16_t m = l * (int16_t)t->mix + v[k];                     /* 16 x 16 multiplies: muls, no libgcc */
        v[k] = ((int16_t)(m * (int16_t)t->mul) >> t->shift) + t->add[k];
        if (v[k] < 0) v[k] = 0;
        if (v[k] > 31) v[k] = 31;
    }
    return RGB(v[0], v[1], v[2]);
}
uint16_t fighter_colour(const fighter_t *f, uint16_t c) { return f->tint ? tint_colour(f->tint, c) : c; }   /* the
                                                             untinted path stays as cheap as before (fades call it per colour) */
const uint16_t *fighter_src_pal(const fighter_t *f, uint8_t i) {
    return i == 0 && f->cpal ? f->cpal : f->ch->pals + ((f->set * f->ch->npal + i) << 4);
}
void fighter_load_pals(const fighter_t *f) {
    uint16_t buf[16];
    uint8_t i, j;
    for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) {
        const uint16_t *src = fighter_src_pal(f, i);
        buf[0] = src[0];
        for (j = 1; j < 16; j++) buf[j] = fighter_colour(f, src[j]);
        PAL_setPalette(f->palbase + i, buf);
    }
}

static void carry_drop(fighter_t *f);
static void react(fighter_t *v, int8_t away, uint8_t reaction, int8_t push) {   /* away: direction the victim is sent */
    uint8_t blow = (v->state == S_ATTACK || v->state == S_AIR_ATTACK || v->state == S_SPECIAL)
                   ? BA_BLOWBACK : BA_BLOWBACK_N;               /* KOF98: a counter hit (hit in its own attack) 283, else 285 */
    if (v->state == S_SPECIAL) { carry_drop(v); special_end(v); }   /* hit out of a special: its projectiles go, a carried target falls */
    v->frame_ovr = 0xFFFF;                                       /* released from a hold by a special: its held pose ends */
    if (v->state == S_GRAB) release(v);                          /* hit while holding or while held: the hold ends */
    else if (v->state == S_GRABBED) release(v->held);
    v->facing = -away;                                           /* turn toward the attacker */
    v->kmode = v->kdelay = 0; v->kvfr = 0;                       /* the brawler's own physics (kof_react sets KOF's) */
    if (v->y > 0) {                                              /* hit in the air (a juggle when falling): sent up again */
        enter(v, S_KNOCKDOWN); v->vy = reaction >= R_KNOCKDOWN ? FIX(5) : FIX(4); v->vx = dir_mul(away, FIX(1) + 0x8000);
        play(v, BA_BLOWBACK); return;                            /* KOF's hit_air ends on standing frames (KOF96: none) */
    }
    switch (v->hp <= 0 ? R_KNOCKDOWN : reaction) {
    case R_LIGHT: case R_HEAVY:
        enter(v, S_HITSTUN); play(v, reaction == R_LIGHT ? BA_HIT_STAND_LIGHT : BA_HIT_STAND_HEAVY);
        v->vx = dir_mul(away, FIX(push) >> 2);
        break;
    case R_KNOCKDOWN: enter(v, S_KNOCKDOWN); v->vy = FIX(7); v->vx = dir_mul(away, FIX(2)); play(v, blow); break;
    case R_LAUNCH:    enter(v, S_KNOCKDOWN); v->vy = FIX(9); v->vx = dir_mul(away, FIX(2) + 0x8000); play(v, blow); break;   /* KOF98 launches rise in it too (Burn Knuckle) */
    case R_TRIP:      enter(v, S_KNOCKDOWN); v->vy = FIX(3); v->vx = dir_mul(away, FIX(1)); play(v, BA_TRIP); break;
    case R_BLOWBACK:  enter(v, S_KNOCKDOWN); v->vy = FIX(4); v->vx = dir_mul(away, FIX(5)); play(v, blow); break;   /* KOF's C+D: low and far */
    }
}

/* ---- hold and throws -----------------------------------------------------------------------------------------------------
 * Walking into a standing opponent grabs it (combat). Hold pose = row 0 of the forward+C throw script for both. In the hold
 * (Bruno 2026-10-03): A = down+C, B = close D (damage on the move's attack frame, the victim reels in place); the third hit
 * is always C+D, which knocks the victim down and ends the hold; forward+A = the forward throw (KOF's forward+C), forward+B
 * = the reverse throw (KOF98 throws backward with forward+D). Throws play their per-frame script (thrower frame + offset,
 * victim posture + offset + facing + draw order); 90 frames: the victim breaks free, or sooner by mashing ESCAPE_PRESSES
 * buttons. Enemies grab too (AI intent `grab`). Postures are KOF's shared victim states; each fighter has its own frame
 * for them (bchar_t.vposes). */
#define GRAB_DX      32
#define GRAB_TIME    90
#define GRAB_HITS    3
#define GRAB_DAMAGE  3
#define THROW_DAMAGE 12
#define SPLASH_DX    48               /* a throw's impact also knocks down the victim's teammates this close to it (Final Fight) */
#define SPLASH_DAMAGE 6
#define ESCAPE_PRESSES 4

static void show_pose(fighter_t *v, uint8_t vp) {
    uint16_t fr = vp < VP_COUNT ? v->ch->vposes[vp] : 0xFFFF;
    if (fr != 0xFFFF) v->frame_ovr = fr;
    else { v->frame_ovr = 0xFFFF; play_if_new(v, BA_HIT_STAND_LIGHT); }   /* no frame for it: the light hit pose */
}
static void place_victim(const fighter_t *a, fighter_t *v, const bthrow_row_t *r, int8_t face) {   /* face: the */
    v->x = a->x + dir_mul(face, FIX(r->vx));                    /* thrower's facing the script's offsets are in */
    v->y = a->y + FIX(r->vy); if (v->y < 0) v->y = 0;
    v->z = a->z;
    v->facing = (r->flags & 1) ? face : -face;
    v->zfront = (r->flags & 2) != 0;
}
static void grab(fighter_t *a, fighter_t *v) {
    const bthrow_row_t *r = a->ch->throws[BT_THROW_C].rows;
    enter(a, S_GRAB); a->held = v; a->target = v; a->grab_hits = 0;
    a->frame_ovr = r->tframe;
    if (a->team) stat_grabs++;
    enter(v, S_GRABBED); v->held = a; v->vx = v->vy = v->vz = 0; v->grab_hits = 0;   /* victim: presses mashed */
    show_pose(v, r->vpose); place_victim(a, v, r, a->facing);
}
static void release(fighter_t *a) {                              /* both free where they stand */
    fighter_t *v = a->held;
    a->held = 0; a->frame_ovr = 0xFFFF; a->zfront = 0; a->y = 0; to_neutral(a, 0);
    if (v) { v->held = 0; v->frame_ovr = 0xFFFF; v->zfront = 0; to_neutral(v, 0); }
}
static void start_node(fighter_t *f, uint8_t node, uint8_t how);
static uint8_t special_for(const fighter_t *f, const intent_t *in);
static void start_special(fighter_t *f, uint8_t k);
static void hold_update(fighter_t *f, const intent_t *in) {
    fighter_t *v = f->held;
    const bthrow_row_t *r = f->ch->throws[BT_THROW_C].rows;
    if (in->press & IN_SP) {                                     /* A+B: the hold ends, the special at once (Bruno
                                                                    2026-10-05); the victim reels in its held pose, free */
        uint8_t k = special_for(f, in);                          /* (only throws hold a victim), until its stun ends or */
        if (k != 0xFF && spend(f, gmeter.special, 0, 0)) {       /* the special hits it */
            f->held = 0; f->frame_ovr = 0xFFFF; f->zfront = 0; f->y = 0; f->buffered = 0;
            v->held = 0; v->zfront = 0; v->vx = v->vy = v->vz = 0; v->y = 0;
            enter(v, S_HITSTUN); play(v, BA_HIT_STAND_LIGHT);    /* STUN_LIGHT frames; frame_ovr: the held pose */
            lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, k); start_special(f, k);
            return;
        }
    }
    if (f->frame_ovr == 0xFFFF) {                                /* a hold hit is playing */
        if (f->buffered && ((fighter_step(f)->flags & 1) || f->anim_done)) {   /* it lands on its attack frame */
            f->buffered = 0;
            if (f->grab_hits >= GRAB_HITS) {                     /* C+D: the victim goes down, the hold is over */
                f->held = 0; v->held = 0; v->frame_ovr = 0xFFFF; v->zfront = 0; enter(v, S_IDLE);
                f->node = TREE(f)->hold; f->landed = 1; enter(f, S_ATTACK);   /* the C+D plays on as a normal attack */
                snd_sfx(SFX_HIT_CD); fighter_hit(f, v, NODE(f, f->node)->damage, R_KNOCKDOWN, 0);
                return;
            }
            snd_sfx(f->anim == BA_ATK_D_CLOSE ? SFX_HIT_D : SFX_HIT_C);
            v->hp -= GRAB_DAMAGE; v->frame_ovr = 0xFFFF; play(v, BA_HIT_STAND_LIGHT);
            f->freeze = v->freeze = 4;
            return;
        }
        if (!f->anim_done) return;
        f->frame_ovr = r->tframe; show_pose(v, r->vpose);
        return;
    }
    if (in->press & IN_A) {
        if (in->dx) {                                            /* forward+A / back+A: throw forward / backward */
            uint8_t t = in->dx == f->facing ? BT_THROW_C : BT_THROW_D;
            if (!f->ch->throws[t].nrows) t = BT_THROW_C;
            f->throw_id = t; f->throw_x0 = f->x; f->throw_face = f->facing; enter(f, S_THROW); enter(v, S_THROWN);
            f->srow = 0; f->speed = f->ch->throws[t].speed;
            {                                                    /* its impacts share the throw's damage */
                const bthrow_t *th = &f->ch->throws[t]; uint16_t i;
                f->grab_hits = 0; f->throw_dealt = 0;
                for (i = 0; i < th->nrows; i++) if (th->rows[i].flags & 4) f->grab_hits++;
            }
            if (f->team) stat_throws++;
            return;
        }
        f->grab_hits++;                                          /* A: down+C, close D, the third: C+D */
        f->frame_ovr = 0xFFFF; f->buffered = 1;
        play(f, f->grab_hits >= GRAB_HITS ? BA_BODY_TOSS : (f->grab_hits & 1) ? BA_ATK_C_CROUCH : BA_ATK_D_CLOSE);
        return;
    }
    if (f->state_t >= GRAB_TIME) {                               /* the victim breaks free */
        release(f); v->x += dir_mul(f->facing, FIX(10)); clamp(v); v->inv = 20;
    }
}
#define THROW_FREEZE 21           /* KOF98 Ryo's forward+C: step 10 held 21 frames past its ticks (the only throw freeze
                                     among the roster's: every other throw step lasts its ROM ticks + 1, KOF96/98/99) */
/* script rows (specials, throws): one row = one frame at 1x; f->srow = the row shown + 1, f->acc the time in it.
 * Advanced by f->speed like the animation player; stop(row) = a row the advance must not pass (a special's hit
 * row with its box live or opening a hit, its continuation point): it stops there. Returns the first row newly shown (rows from it to srow - 1 were
 * passed or reached this frame). */
static uint16_t script_advance(fighter_t *f, uint16_t nrows, const bspec_t *sp) {
    uint16_t from = f->srow;
    if (!f->srow) { f->srow = 1; f->acc = 0; return 0; }         /* its first frame: row 0 */
    f->acc += f->speed;
    while (f->acc >= 0x100) {
        f->acc -= 0x100; f->srow++;
        if (f->srow > nrows) break;
        if (sp && ((sp->rows[f->srow - 1].hit & 3) || (sp->cont && f->srow == sp->cont + 1))) {
            if (f->acc >= 0x100) f->acc = 0xFF;                  /* a live row / the continuation point: shown */
            break;
        }
    }
    return from;
}
/* throws play at their own speed (bthrow_t.speed: 1.5x for every throw, Bruno 2026-10-04: frame n shows row
 * (n - 1) * 3 / 2); an impact row passed over still lands (damage, spark, sound, freeze) on the frame that passes it */
static void throw_update(fighter_t *f) {
    const bthrow_t *th = &f->ch->throws[f->throw_id];
    fighter_t *v = f->held;
    const bthrow_row_t *r;
    uint16_t j = script_advance(f, th->nrows, 0), i = f->srow - 1;
    if (i >= th->nrows) {                                        /* script over: the victim lies where it landed */
        release(f); clamp(f);
        v->hp -= THROW_DAMAGE - f->throw_dealt; v->y = 0; clamp(v); enter(v, S_DOWN); play(v, BA_DOWN);
        return;
    }
    voice_at(f, VK_THROW + f->throw_id, j, i);
    for (; j <= i; j++) {
        r = &th->rows[j];
        if (r->vpose != 0xFF) show_pose(v, r->vpose);           /* a pose set on a passed row still applies */
        if (r->flags & 4) {                                      /* impact: the blow lands / the victim hits the floor */
            uint8_t d = 0, rest = THROW_DAMAGE;                 /* THROW_DAMAGE / impacts (no divide here) */
            while (rest >= f->grab_hits) { rest -= f->grab_hits; d++; }
            v->hp -= d; f->throw_dealt += d;
            if (!mute) voice_play(v->ch, v->team, v->hp > 0 ? VK_HIT : VK_KO);
            if (r->flags & 16) f->freeze = v->freeze = THROW_FREEZE;   /* only where KOF froze (Ryo's forward+C) */
            f->impact = 1;                                       /* combat() hits the victim's teammates around it */
            snd_sfx(SFX_HIT_CD);
            spark_hit(INT(f->throw_x0) + dir_mul(f->throw_face, r->vx + r->tx), floor_top + INT(f->z) - r->vy - 40, 1, f->throw_face);
        }
    }
    r = &th->rows[i];
    f->frame_ovr = r->tframe;
    f->x = f->throw_x0 + dir_mul(f->throw_face, FIX(r->tx)); f->y = FIX(r->ty);
    f->facing = (r->flags & 8) ? -f->throw_face : f->throw_face;   /* turned around in the game (Terry's reverse throw) */
    if (r->vpose != 0xFF) show_pose(v, r->vpose);
    place_victim(f, v, r, f->throw_face);
}

/* ---- specials ------------------------------------------------------------------------------------------------------------
 * D: the fighter's first ground special, forward+D (any direction held: the fighter faces it) the second (export_bm.py
 * picks them), played from the per-frame script captured in the game: fighter frame + offset, body attack box (KOF's,
 * from the move's own animation) and up to two objects (effects: pool entities with their frame, offset and facing, no
 * box); a projectile is an entity of its own (bspec_t.proj, see "projectiles" below). Per row hit bits (export_bm special_rows): a row opening a new hit lets the same
 * targets be hit again, with its damage (SPECIAL_DAMAGE split over the move's hits) and the victim's reaction measured
 * in the game (bits 5-7: R_HEAVY keeps it on the ground until the part that ejects it); contact rows (a running grab's
 * reach) only catch the victim. Hit-confirmed continuations (bspec_t.cont, one code path): a hit on a row with bit 16
 * jumps to row `cont` (Geese's Jaei-ken follow-up, Kyo's grab + explosion), placed from where the fighter is; playing
 * into `cont` without a hit ends the move (the whiff). */
#define SPECIAL_DAMAGE 8
fighter_t projectiles[NPJ];
uint16_t stat_grabs, stat_specials, stat_throws, stat_escapes;

void projectile_reset(fighter_t *p) {
    if (p->owner && p->owner->shot == p) p->owner->shot = 0;   /* KOF: the thrower may throw again (+$E1 bit 5 off) */
    p->state_t = 0; p->node = 0;
    p->ch = &bm_chars[0]; p->anim = 0; p->step = 0; p->tick = 1;
    p->frame_ovr = 0xFFFF; p->shown_frame = 0xFFFF; p->state = S_OFF; p->spec_atk = 0; p->owner = 0;
    p->x = p->y = p->z = 0; p->facing = 1; p->zfront = 1; p->freeze = p->inv = 0; p->hit_mask = 0; p->held = 0; p->ncols = 0;
    p->pdef = 0; p->pown = 0; p->prow = p->pend = 0;
}
static fighter_t *proj_alloc(fighter_t *owner) {
    uint8_t i;
    for (i = 0; i < NPJ; i++) {
        fighter_t *p = &projectiles[i];
        if (p->state != S_OFF) continue;
        p->state = S_PROJ; p->ch = owner->ch; p->palbase = owner->palbase; p->team = owner->team; p->owner = owner;
        p->frame_ovr = 0xFFFF; p->spec_atk = 0; p->hit_mask = 0; p->pdef = 0; p->pown = 0; p->prow = p->pend = 0;
        return p;
    }
    return 0;                                                    /* pool empty: this special shows no objects */
}
static void special_end(fighter_t *f) {
    uint8_t k;
    for (k = 0; k < 2; k++) if (f->proj[k]) { projectile_reset(f->proj[k]); f->proj[k] = 0; }
    f->frame_ovr = 0xFFFF; f->spec_atk = 0;                      /* height kept: hit out of a rising move = an air hit */
}
static void start_special(fighter_t *f, uint8_t k) {   /* k: the role (BS_*), special_pick: it has a special */
    if (f->team) stat_specials++;
    f->spec_id = k; f->spec_ix = spec_ix(f->ch, k); f->throw_x0 = f->x; f->hit_mask = 0; f->spec_prev_hit = 0; f->spec_atk = 0; f->landed = 0;
    f->spec_dmg = SPECIAL_DAMAGE; f->spec_react = R_KNOCKDOWN; f->spec_slide = 0;
    f->proj[0] = f->proj[1] = 0;                                 /* script objects: taken when a row shows one */
    enter(f, S_SPECIAL); f->srow = 0; f->speed = 0x100;          /* a route ender: its node's speed (S_ATTACK) */
    if (f->ch->specials[f->spec_ix].prog) {                      /* a ROM special: its program from its first op */
        f->pres = 0; f->pflags = 0; f->pcnt = 0; f->pfric = 0; f->pg = 0; f->vx = f->vy = 0;
    }
}

/* ---- projectiles (tools/kof98/README.md "Projectiles"; tools/kof96/projectiles96.py) ----------------------------------
 * KOF96/98/99 spawn a projectile as an object of its own on the thrower's event step: its own animation, boxes and
 * motion, owner +$84, one at a time per thrower (+$E1 bit 5). It lives on whatever the thrower does (its routine never
 * reads the owner) and dies when its animation ends, when it leaves the screen (x - camera <= -64 or >= 384, the shared
 * test KOF98 $180B6) or, a travelling one (kind 1), on its first hit, into its end animation; an eruption (kind 3)
 * hits once and plays on. Neither it nor its thrower freezes on its hit (the victim does). Two projectiles that meet
 * (one's attack box on the other's own box) both spend their hit. Here: a pool entity driven by its bproj_t rows. */
static void proj_row(fighter_t *p) {
    const bproj_t *d = p->pdef;
    if (p->pend == 1) {                                          /* its end after the hit, in place */
        const bpend_t *e = &d->end[p->prow];
        p->frame_ovr = e->frame; p->x = p->throw_x0 + dir_mul(p->facing, (int32_t)e->x << 13); p->y = FIX(e->y);
        p->spec_atk = 0; p->pown = 0;
    } else {
        const bprow_t *r = &d->rows[p->prow];
        p->frame_ovr = r->frame; p->x = p->throw_x0 + dir_mul(p->facing, (int32_t)r->x << 13); p->y = FIX(r->y);
        p->spec_atk = (r->flags & 1) && !p->pend ? &r->atk : 0;
        p->pown = (r->flags & 2) && !p->pend ? &r->own : 0;
    }
    if (d->follow && p->owner) p->y += p->owner->y;              /* pinned to its thrower (Burn Knuckle's flame) */
}
static fighter_t *proj_start(fighter_t *owner, const bproj_t *d, int32_t x0, int8_t facing, int32_t z) {
    fighter_t *p = proj_alloc(owner);
    if (!p) return 0;                                            /* pool full: no entity for it */
    p->pdef = d; p->prow = 0; p->pend = 0; p->facing = facing; p->z = z; p->throw_x0 = x0;
    p->spec_dmg = SPECIAL_DAMAGE; p->spec_react = d->react; p->spec_fx = d->fx; p->spec_prev_hit = 0;
    p->tick = 0; p->state_t = 0; p->node = d->child_b0;          /* tick 0: shown at row 0 this frame (the update after
                                                                    the fighters' advances it from the next); state_t:
                                                                    its frames alive; node: the next frame its child is born */
    proj_row(p);
    return p;
}
static void proj_spawn(fighter_t *f, const bproj_t *d) {         /* spawn point: the script's origin + offset */
    fighter_t *p = proj_start(f, d, f->throw_x0 + dir_mul(f->facing, FIX(d->spawn_x)), f->facing, f->z);
    if (p) f->shot = p;
}
static void proj_hit(fighter_t *p) {                             /* its hit landed (a fighter or a clash) */
    if (p->pdef->kind == 1) {                                    /* travelling: its end animation where it hit */
        if (!p->pdef->nend) { projectile_reset(p); return; }
        p->pend = 1; p->prow = 0; p->throw_x0 = p->x; proj_row(p);
    } else { p->pend = 2; p->spec_atk = 0; p->pown = 0; }       /* an eruption plays on, its attack spent */
}
static void proj_child(fighter_t *p) {                           /* its trail: an object it spawns where it is */
    const bproj_t *d = p->pdef;                                  /* (its rows hold their own height) */
    uint8_t i, nfree = 0;
    if (!d->child || p->pend || p->state_t != p->node) return;
    for (i = 0; i < NPJ; i++) nfree += projectiles[i].state == S_OFF;
    if (nfree < 2) { p->node = p->state_t < d->child_b1 && d->child_b1 != 255 ? d->child_b1 : p->node + d->child_period; return; }
                                                                 /* a trail never takes the last free entity (a thrown
                                                                    projectile needs it) */
    fighter_t *c = proj_start(p->owner, d->child, p->x + dir_mul(p->facing, (int32_t)d->child_dx << 13), p->facing, p->z);
    if (c && c < p) c->tick = 1;                                 /* this update pass is past it: row 0 already counted */
    p->node = p->state_t < d->child_b1 && d->child_b1 != 255 ? d->child_b1 : p->node + d->child_period;
    if (!d->child_period && p->state_t >= d->child_b1) p->node = 255;
}
void projectiles_update(int16_t cam_x) {
    uint8_t i;
    for (i = 0; i < NPJ; i++) {
        fighter_t *p = &projectiles[i];
        const bproj_t *d = p->pdef;
        int16_t sx;
        if (p->state != S_PROJ || !d) continue;
        if (!p->tick) { p->tick = 1; proj_child(p); continue; }  /* its first frame: row 0 */
        p->state_t++;
        if (p->pend == 1) {
            if (++p->prow >= d->nend) { projectile_reset(p); continue; }
        } else if (d->follow && p->owner) {                      /* pinned: its rows cycle at the thrower's place */
            if (++p->prow >= d->nrows) p->prow = d->loop == 0xFF ? 0 : d->loop;
            p->throw_x0 = p->owner->x; p->facing = p->owner->facing;
        } else if (++p->prow >= d->nrows) {
            if (d->loop == 0xFF) { projectile_reset(p); continue; }   /* its animation is over */
            p->prow = d->loop; p->throw_x0 += dir_mul(p->facing, (int32_t)d->wrap_x << 13);   /* the flight goes on */
        }
        proj_row(p);
        sx = INT(p->x) - cam_x;
        if (sx <= -64 || sx >= 384) { projectile_reset(p); continue; }   /* off screen (KOF's test, its 320 px screen) */
        proj_child(p);
    }
}
static uint8_t special_pick(const fighter_t *f, uint8_t want) {   /* a role (BS_*) -> the BS_* it plays, 0xFF = none */
    static const uint8_t order[BS_COUNT][BS_COUNT] = {           /* an empty diagonal: down / up's own order (what the */
        { BS_D, BS_FWD_D, BS_DOWN_D, BS_UP_D, BS_DF_D, BS_UF_D },  /* input read before the six slots), then the other */
        { BS_FWD_D, BS_D, BS_UP_D, BS_DOWN_D, BS_DF_D, BS_UF_D },  /* diagonal */
        { BS_DOWN_D, BS_UP_D, BS_FWD_D, BS_D, BS_DF_D, BS_UF_D }, { BS_UP_D, BS_FWD_D, BS_DOWN_D, BS_D, BS_UF_D, BS_DF_D },
        { BS_DF_D, BS_DOWN_D, BS_UP_D, BS_FWD_D, BS_D, BS_UF_D }, { BS_UF_D, BS_UP_D, BS_FWD_D, BS_DOWN_D, BS_D, BS_DF_D } };
    uint8_t k;
    for (k = 0; k < BS_COUNT; k++) {                                    /* missing: the nearest; a projectile special not */
        uint8_t ix = spec_ix(f->ch, order[want][k]);              /* while the fighter's projectile flies (KOF skips */
        const bspec_t *sp = &f->ch->specials[ix];                 /* the command: owner +$E1 bit 5) */
        if (ix != 0xFF && sp->nrows && !(sp->proj && f->shot)) return order[want][k];
    }
    return 0xFF;
}
/* A+B, forward / down / up / down-forward / up-forward + A+B (down / up = toward / away from the camera) -> BS_*, 0xFF = none */
static uint8_t special_for(const fighter_t *f, const intent_t *in) { return special_pick(f, d_input(f, in) - RI_S); }
/* ---- specials read from the ROM (tools/kof96/handlers98.py, handlers98.md) ---------------------------------------------
 * KOF98 runs a special as straight-line 68000 code: set speeds, start a state's animation, then a frame loop (the
 * coroutine resumes at +$00) that moves the body and waits for the animation's end / an event step / the landing.
 * export_bm.rom_c turns that code into bprim_t ops; this plays them: each frame the ops run from the resume point until
 * a P_BR to the frame's end, then the animation advances (KOF98's engine: a step shows ticks + 1 frames, the frame a
 * state starts counts as the first of its first step, past the last step the end flag is set, a hold stays on it).
 * Hits come from the animation (an attack box while the step is active, a new hit unless the active step before it
 * carries KOF's same-hit flag); the brawler's own hit-stop freezes it (fighter_update), no freeze is in the data. */
enum { PF_END = 1, PF_EVENT = 2, PF_LAND = 4, PF_FALL = 8 };
static int32_t fmul16(int32_t v, uint16_t k) {                   /* v * k / 65536 (KOF98 $36A0), sign kept */
    uint32_t a = v < 0 ? -v : v;
    a = (a >> 16) * k + (((a & 0xFFFF) * k + 0x8000) >> 16);
    return v < 0 ? -(int32_t)a : (int32_t)a;
}
/* KOF98's reaction to a special's body hit, measured in our emulator (tools/kof96/capture/romspecials98.py, close
 * traces: P2 +$50 vx, +$54 friction, +$58 vy, +$5C gravity after Ralf's [4]6C and [2]8C, Terry's 214C and 623C hits):
 * 258 the standing reel (a slide at 11.18 px, x 0.828 a frame: 65 px; a captured special: the slide its capture
 * shows, bspec_row_t.vx), 283 / 285 the blowback (vx 11.375 x 0.8125 down to
 * ~4, up at 7 px, gravity 0.5; falling: vx x 0.8125 once), 286 the launch (up at 17.25 px, gravity 2.6875 decaying x
 * 0.871 a frame, falling at gravity 0.625). The victim stays put the frames KOF shakes it (after the hit-stop), and is
 * re-launched the same way by every later hit (a juggle). Each frame: height += vy, gravity *= decay, vy -= gravity,
 * x += vx, vx *= friction; the frame vy reaches 0 the fall starts (vy -= the fall's gravity at once, as KOF) */
#define KM_LAUNCH 4               /* kmode: KOF's 286 launch (its 286 / 293 frames have a hurt box: LAUNCH_BOX) */
static const struct { int32_t vx, vy, g, gf, vmin; uint16_t gfr, vfr; uint8_t delay; } KOF_REACT[3] = {
    { 0xB2E00, 0, 0, 0, 0, 0, 0xD400, 5 },                       /* R_HEAVY: 258 */
    { 0xB6000, 0x70000, 0x8000, 0x8000, 0x48000, 0, 0xD000, 2 }, /* R_KNOCKDOWN: 283 / 285 */
    { 0x20000, 0x114000, 0x2B000, 0xA000, 0, 0xDF00, 0, 2 },     /* R_LAUNCH: 286 */
};
static void kof_react(fighter_t *v, int8_t away, uint8_t rc, int8_t slide) {
    uint8_t k;
    if (v->hp <= 0 && rc < R_KNOCKDOWN) rc = R_KNOCKDOWN;
    if (rc < R_HEAVY || rc > R_LAUNCH) return;                   /* the brawler's own (react) */
    if (rc == R_HEAVY && v->y > 0) rc = R_KNOCKDOWN;             /* no reel in the air: KOF's air hit sends it off */
    if (rc == R_HEAVY && v->state != S_HITSTUN) return;
    k = rc - R_HEAVY;
    v->vx = dir_mul(away, rc == R_HEAVY && slide != -128 ? fmul16(FIX(slide), 0x10000 - KOF_REACT[0].vfr) : KOF_REACT[k].vx); v->kvfr = KOF_REACT[k].vfr; v->kvmin = KOF_REACT[k].vmin; v->kdelay = KOF_REACT[k].delay;
    if (rc == R_HEAVY) return;
    if (v->state != S_KNOCKDOWN) return;
    v->vy = KOF_REACT[k].vy; v->kg = KOF_REACT[k].g; v->kgf = KOF_REACT[k].gf; v->kgfr = KOF_REACT[k].gfr;
    v->kmode = rc == R_LAUNCH ? 1 | KM_LAUNCH : 1;
}
static void kof_fall(fighter_t *f) {                             /* S_KNOCKDOWN in KOF's reaction: one frame */
    f->y += f->vy;
    if (f->kgfr) f->kg = fmul16(f->kg, f->kgfr);
    f->vy -= f->kg;
    f->x += f->vx; clamp(f);
    if (f->kvfr && (f->vx >= f->kvmin || f->vx <= -f->kvmin)) f->vx = fmul16(f->vx, f->kvfr);
    if ((f->kmode & 3) == 1 && f->vy <= 0) {                     /* the top: the fall */
        f->kmode += 1; f->kg = f->kgf; f->kgfr = 0; f->vy -= f->kg;
        if (f->kvfr) f->vx = fmul16(f->vx, f->kvfr);
    }
}
static void pan_enter(fighter_t *f, uint8_t prev) {              /* a step starts: its $FB move, event, hit */
    const bstep_t *s = &f->pan->steps[f->pstep];
    if (s->dx) { f->x += dir_mul(f->facing, FIX(s->dx)); clamp(f); }
    if (s->flags & 8) f->pflags |= PF_EVENT;
    if ((s->flags & 1) && !((prev & 1) && (prev & 16))) {        /* a new hit window */
        uint8_t k;
        f->hit_mask = 0; f->spec_dmg = f->pdmg; f->spec_react = f->preact & 7; f->spec_fx = f->pfx; f->spec_slide = -128;
        if (f->spec_react == R_KNOCKDOWN)                        /* a knockdown state's earlier hits keep the victim */
            for (k = f->pstep + 1; k < f->pan->nsteps; k++)      /* standing (KOF98 Gatling Attack 138: 258, then 283) */
                if ((f->pan->steps[k].flags & 1) && !((f->pan->steps[k - 1].flags & 1) && (f->pan->steps[k - 1].flags & 16))) { f->spec_react = R_HEAVY; break; }
    }
}
static void pan_play(fighter_t *f, const banim_t *an) {
    f->pan = an; f->pstep = 0; f->pleft = an->steps[0].ticks + 1; f->pflags &= ~(PF_END | PF_EVENT);
    pan_enter(f, 0);
}
static void pan_advance(fighter_t *f) {
    uint8_t prev = f->pan->steps[f->pstep].flags;
    if (--f->pleft) return;
    if (f->pstep + 1 < f->pan->nsteps) f->pstep++;
    else {
        f->pflags |= PF_END;
        if (f->pan->hold) { f->pleft = 1; return; }
        f->pstep = 0;
    }
    f->pleft = f->pan->steps[f->pstep].ticks + 1;
    pan_enter(f, prev);
}
static uint8_t pcond(fighter_t *f, uint8_t c) {
    switch (c) {
    case PC_END: return f->pflags & PF_END ? 1 : 0;
    case PC_EVENT: { uint8_t e = f->pflags & PF_EVENT ? 1 : 0; f->pflags &= ~PF_EVENT; return e; }
    case PC_LAND: return f->pflags & PF_LAND ? 1 : 0;
    case PC_FALL: return f->pflags & PF_FALL ? 1 : 0;
    case PC_CNT: return f->pcnt < 0;
    case PC_HIT: return f->landed;
    case PC_OFF: return 0;
    }
    return 1;
}
static void prog_fxoff(fighter_t *f) {                           /* its pinned effects end (KOF: owner +$D1 bit 7) */
    uint8_t k;
    for (k = 0; k < 2; k++) if (f->proj[k] && f->proj[k]->pdef && f->proj[k]->pdef->follow) { projectile_reset(f->proj[k]); f->proj[k] = 0; }
}
static void prog_spawn(fighter_t *f, const bproj_t *d) {
    fighter_t *p = proj_start(f, d, f->x, f->facing, f->z);      /* rows: from the thrower's place now */
    if (!p) return;
    if (d->follow) { if (!f->proj[0]) f->proj[0] = p; else if (!f->proj[1]) f->proj[1] = p; }
    else f->shot = p;
}
static void prog_end(fighter_t *f) {
    special_end(f);
    if (f->y > 0) { f->vx = f->vy = f->vz = 0; f->jump_kind = f->jump_dir = 0; enter(f, S_AIR); play(f, BA_JUMP_UP_FALL); } else to_neutral(f, 0);
}
static void prog_update(fighter_t *f, const bspec_t *sp) {
    const bstep_t *s;
    uint8_t n;
    f->srow++;                                                   /* frames played (the reversal's invincibility) */
    if (f->spec_id == BS_DOWN_D && f->srow <= sp->inv_rows && f->inv < 2) f->inv = 2;
    f->ppc = f->pres;
    for (n = 0; n < 96; n++) {
        const bprim_t *p = &sp->prog[f->ppc++];
        switch (p->op) {
        case P_ANIM: f->pdmg = p->b & 0xFF; f->preact = p->b >> 8; f->pfx = p->v; pan_play(f, &sp->anims[p->a]); break;
        case P_SET:
            if (p->a == 0) f->vx = p->v; else if (p->a == 1) f->vy = p->v; else if (p->a == 2) f->pg = p->v;
            else if (p->a == 3) f->pfric = p->v; else f->pcnt = p->v;
            break;
        case P_MUL: f->vx = fmul16(f->vx, p->v); break;
        case P_FRICMOVE: f->vx = fmul16(f->vx, f->pfric);        /* fall through: then x += vx */
        case P_MOVE: f->x += dir_mul(f->facing, f->vx); clamp(f); break;
        case P_FALL: {
            int32_t v0 = f->vy;
            f->vy -= f->pg; f->y += v0; f->pflags &= ~(PF_LAND | PF_FALL);
            if (f->y <= 0) { f->y = 0; f->pflags |= PF_LAND; } else if (f->vy < 0) f->pflags |= PF_FALL;
            break;
        }
        case P_NUDGE: f->x += dir_mul(f->facing, FIX(p->b)); f->y += FIX(p->v); clamp(f); break;
        case P_DEC: f->pcnt--; break;
        case P_BR:
            if (pcond(f, p->a & 0x7F) == (p->a >> 7)) {
                if (p->b < 0) goto frame_done;
                f->ppc = p->b;
            }
            break;
        case P_RESUME: f->pres = f->ppc; break;
        case P_RESUMEAT: f->pres = p->b; break;
        case P_JMP: f->ppc = p->b; break;
        case P_SPAWN: prog_spawn(f, &sp->robj[p->a]); break;
        case P_FXOFF: prog_fxoff(f); break;
        default: prog_end(f); return;                            /* P_END */
        }
    }
frame_done:
    for (n = 0; n < 2; n++) {                                    /* its pinned effects follow this frame's move */
        fighter_t *p = f->proj[n];
        if (p && p->pdef && p->pdef->follow) { p->throw_x0 = f->x; p->facing = f->facing; proj_row(p); }
    }
    pan_advance(f);
    s = &f->pan->steps[f->pstep];
    f->frame_ovr = s->frame;
    f->spec_atk = (s->flags & 1) ? &s->atk : 0;
    f->spec_prev_hit = (s->flags & 1) ? 1 : 0;
}
static void carry_drop(fighter_t *f) {                           /* a grab's carry ended: a target it left in the air */
    fighter_t *v = f->target;                                    /* falls (Ralf's 426B left it 4 px up for good) */
    if (!(f->spec_prev_hit & 4) || !v || v->y <= 0 || (v->state != S_HITSTUN && v->state != S_KNOCKDOWN)) return;
    enter(v, S_KNOCKDOWN); v->vx = v->vy = 0; play(v, BA_KNOCKDOWN_FLIGHT);
}
static void special_update(fighter_t *f) {
    const bspec_t *sp = &f->ch->specials[f->spec_ix];
    const bspec_row_t *r;
    uint8_t k;
    uint16_t from;
    if (sp->prog) { prog_update(f, sp); return; }                /* read from the ROM: its program */
    from = script_advance(f, sp->nrows, sp);                     /* rows from..srow-1 reached this frame */
    if (sp->cont && f->srow <= sp->cont + 1) {
        if (f->landed && (f->spec_prev_hit & 16)) {              /* it hit: on to the continuation, from here */
            f->srow = sp->cont + 1; f->throw_x0 = f->x;
        } else if (f->srow == sp->cont + 1) f->srow = sp->nrows + 1;   /* a whiff: the move ends */
    }
    if (f->srow > sp->nrows) {                                /* over; ended in the air (a rising move): fall */
        carry_drop(f);
        special_end(f);
        if (f->y > 0) { f->vx = f->vy = f->vz = 0; f->jump_kind = f->jump_dir = 0; enter(f, S_AIR); play(f, BA_JUMP_UP_FALL); } else to_neutral(f, 0);
        return;
    }
    voice_at(f, VK_SPEC + f->spec_ix, from, f->srow - 1);
    r = &sp->rows[f->srow - 1];
    if (f->spec_id == BS_DOWN_D && f->srow <= sp->inv_rows && f->inv < 2) f->inv = 2;   /* the rising reversal: invincible from its first frame to its last hit */
    f->frame_ovr = r->frame;
    f->x = f->throw_x0 + dir_mul(f->facing, FIX(r->x)); f->y = r->y > 0 ? FIX(r->y) : 0; clamp(f);
    if (r->hit & 2) {                                            /* a new hit; its reel slide as the capture's (px) */
        f->hit_mask = 0; f->spec_dmg = r->dmg; f->spec_react = r->hit >> 5; f->spec_fx = r->fx; f->spec_slide = (r->hit & 4) ? 0 : r->vx;
    }
    if ((r->hit & 4) && f->landed && f->target && (f->target->state == S_KNOCKDOWN || f->target->state == S_HITSTUN)) {
        fighter_t *v = f->target;                                /* between its hits the move holds its target where */
        v->x = f->x + dir_mul(f->facing, FIX(r->vx)); v->z = f->z;   /* the game's opponent was (launched: kept 1 px */
        v->y = FIX(r->vy ? r->vy : v->state == S_KNOCKDOWN);             /* up, a knockdown at 0 would land) */
        v->vx = v->vy = v->vz = 0; clamp(v);
    }
    if (!(r->hit & 4)) carry_drop(f);
    f->spec_prev_hit = r->hit; f->spec_atk = (r->hit & 1) ? &r->atk : 0;
    for (k = 0; k < sp->nproj; k++)                              /* the game's event steps (Geese's Double */
        if (sp->proj[k].spawn_row >= from && sp->proj[k].spawn_row < f->srow) proj_spawn(f, &sp->proj[k]);   /* Reppuken: two; a passed row spawns too) */
    for (k = 0; k < 2; k++) {
        fighter_t *p = f->proj[k];
        const bsobj_t *o = &r->obj[k];
        if (!p && o->frame != 0xFFFF) p = f->proj[k] = proj_alloc(f);   /* an effect of the script (no box) */
        if (!p) continue;
        if (o->frame == 0xFFFF) { projectile_reset(p); f->proj[k] = 0; continue; }   /* gone: the entity is free again */
        if (p->frame_ovr == 0xFFFF) p->hit_mask = 0;             /* the object (re)appears: fresh hits */
        p->frame_ovr = o->frame;
        p->x = f->throw_x0 + dir_mul(f->facing, FIX(o->x)); p->y = o->y > 0 ? FIX(o->y) : 0; p->z = f->z;
        p->facing = o->same ? f->facing : -f->facing;
        p->spec_atk = o->box.w ? &o->box : 0;
        p->spec_prev_hit = 0; p->spec_dmg = SPECIAL_DAMAGE; p->spec_react = o->react ? o->react - 1 : R_KNOCKDOWN;
    }
}

/* ---- state machine --------------------------------------------------------------------------------------------- */
void fighter_update(fighter_t *f, const intent_t *in) {
    const bphys_t *ph = &f->ch->phys;
    if (f->state == S_GRABBED && in->press && ++f->grab_hits >= ESCAPE_PRESSES) {   /* mash to break free (hit-stop too) */
        fighter_t *h = f->held;
        release(h); f->x += dir_mul(h->facing, FIX(10)); clamp(f); f->inv = 20; f->freeze = h->freeze = 0; stat_escapes++;
    }
    if (f->state == S_ATTACK || f->state == S_AIR_ATTACK) {      /* presses in hit-stop count */
        uint8_t ci = combo_input(f, in);
        if (ci) f->buffered = ci;
        if (in->press & IN_SP) f->spec_buf = 0x80 | d_input(f, in);
    }
    meter_tick(f);
    if (f->burn && f->state != S_HITSTUN && f->state != S_KNOCKDOWN) set_burn(f, 0);   /* landed or recovered */
    if (f->freeze) { f->freeze--; return; }                      /* hit-stop: nothing moves, nothing animates */
    if (f->inv) f->inv--;
    if (f->chain_t) f->chain_t--;
    if ((f->state == S_HITSTUN || f->state == S_GRABBED) && (in->press & IN_SP)) {   /* out of trouble: a special while hit */
        uint8_t k = special_for(f, in);                          /* costs double and flashes white (spend) */
        if (k != 0xFF && spend(f, gmeter.special, 0, 1)) {
            if (f->state == S_GRABBED && f->held) release(f->held);
            f->frame_ovr = 0xFFFF; f->vx = f->vy = f->vz = 0; f->y = 0;
            lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, k); start_special(f, k);
            return;
        }
    }
    f->state_t++;
    f->pushing = 0;
    if (f->state != S_SPECIAL && f->state != S_THROW) anim_tick(f);   /* this frame's time first (see the animation player);
                                                                    a script (special, throw) keeps its own in acc */
    switch (f->state) {
    case S_IDLE: case S_WALK: case S_RUN: {
        uint8_t b = in->press;
        if (b & IN_B) { jump_start(f, in, f->chain_t ? NODE(f, f->chain_node)->next[RI_B] : 0); break; }   /* inside a chain
                                                                    window: the route's B link (a jump-cancel) */
        if (in->dx) f->facing = in->dx;                          /* beat 'em up: face where you walk */
        else if (in->face) f->facing = in->face;
        if (b & IN_C) {                                          /* C: the fury, from half a gauge (gmeter) */
            if (spec_ix(f->ch, BS_FURY) != 0xFF && spend(f, gmeter.fury, gmeter.fury_min, 0)) { lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, BS_FURY); start_special(f, BS_FURY); }
            break;
        }
        if (b & IN_SP) {                                         /* A+B: the slot's special (the stick picks the slot) */
            uint8_t k = special_for(f, in);
            if (k == 0xFF) start_node(f, TREE(f)->nospec, LH_NEUTRAL);
            else if (spend(f, gmeter.special, 0, 0)) { lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, k); start_special(f, k); }
            break;
        }
        if (b & IN_A) {
            uint8_t ci = combo_input(f, in), nx = f->chain_t ? next_node(NODE(f, f->chain_node), ci) : 0;
            if (nx) { start_node(f, nx, LH_WINDOW); break; }       /* the route goes on (Final Fight: tap, wait, tap) */
            if (f->state == S_RUN) { start_node(f, TREE(f)->dash, LH_NEUTRAL); break; }   /* dash attack */
            nx = next_node(NODE(f, TREE(f)->root), ci);          /* a route starts: the root's links */
            if (nx) start_node(f, nx, LH_NEUTRAL);
            break;
        }
        if (f->state == S_RUN && in->dx == f->facing) {
            f->x += dir_mul(f->facing, whole(ph->walk) << RUN_MUL >> 1); f->z += dir_mul(in->dz, FIX(1)); clamp(f); break;
        }
        if (in->run && in->dx) { enter(f, S_RUN); play(f, BA_RUN); break; }
        to_neutral(f, in);
        if (f->state == S_WALK) {
            f->x += dir_mul(in->dx, in->slow ? whole(ph->walk) >> 1 : whole(ph->walk)); f->z += dir_mul(in->dz, in->slow ? FIX(1) >> 1 : FIX(1)); clamp(f);
            f->pushing = in->dx != 0 && (!f->team || in->grab);   /* facing follows dx: walking forward; enemies on purpose */
        }
        break;
    }
    case S_PREJUMP:                                              /* KOF's prejump frames decide the height: B let go */
        if (!(in->hold & IN_B)) f->jump_kind = 1;                /* before take-off = a hop */
        if (f->state_t >= ph->prejump) {                         /* take-off (frames on the ground: the fighter's own) */
            int32_t dx = whole(f->jump_kind ? ph->hop_dx : ph->jump_dx);
            f->vy = f->jump_kind ? ph->hop_vy0 : ph->jump_vy0;
            f->vx = f->jump_dir == 1 ? dir_mul(f->facing, dx) : f->jump_dir == 2 ? dir_mul(-f->facing, dx) : 0;
            enter(f, S_AIR); play(f, JUMP_ANIM[f->jump_kind][f->jump_dir][0]);
        }
        break;
    case S_AIR: case S_AIR_ATTACK:
        if (f->state == S_AIR && (in->press & IN_A)) {           /* A: a jump-cancel's node, else the stick: air A (KOF's */
            uint8_t nx = f->air_node ? f->air_node : in->dz > 0 ? TREE(f)->air_b : in->dz < 0 ? TREE(f)->air_cd : TREE(f)->air_a;
            start_node(f, nx, f->air_node ? LH_CANCEL : LH_NEUTRAL); f->air_node = 0;   /* C), down+A air B (D), up+A air C+D */
        } else if (f->state == S_AIR_ATTACK && f->landed && f->buffered &&   /* an air route: A on hit, its next air hit */
                   (!(NODE(f, f->node)->flags & RF_KEEP) || f->anim_done)) {
            uint8_t nx = next_node(NODE(f, f->node), f->buffered);
            if (nx) start_node(f, nx, LH_CANCEL);
        }
        f->y += f->vy; f->vy -= f->jump_kind ? ph->hop_gravity : ph->gravity; f->x += f->vx; f->z += f->vz; clamp(f);
        if (f->state == S_AIR && f->vy < 0 && f->anim == JUMP_ANIM[f->jump_kind][f->jump_dir][0])
            play(f, JUMP_ANIM[f->jump_kind][f->jump_dir][1]);
        if (f->y <= 0) { f->y = 0; f->vx = f->vy = f->vz = 0; f->air_node = 0; enter(f, S_LAND); play(f, BA_LAND); }
        break;
    case S_LAND:
        if (f->state_t >= ph->land) to_neutral(f, in);         /* KOF's landing: the fighter's own frames (4, Terry 5) */
        break;
    case S_ATTACK: {
        const rnode_t *c = NODE(f, f->node);
        if (f->landed && f->spec_buf && !(c->flags & RF_AIR)) {  /* a special link cancels a normal that hit: cut short */
            uint8_t d = f->spec_buf & 0x7F, nx = c->next[d], k;    /* the input's link, else (a diagonal) */
            if (!nx && d >= RI_DFS) nx = c->next[d == RI_DFS ? RI_DS : RI_US];   /* down / up's, else plain A+B's */
            if (!nx) nx = c->next[RI_S];
            f->spec_buf = 0;
            k = nx ? special_pick(f, NODE(f, nx)->anim) : 0xFF;
            if (k != 0xFF && spend(f, gmeter.special, 0, 0)) { lab_note(f, LE_SPECIAL, nx, LH_CANCEL, k); start_special(f, k); f->speed = NODE(f, nx)->speed; break; }
        }
        if (f->landed && f->buffered && !(c->flags & RF_KEEP)) {   /* cancel on hit: the next link now (after the hit-stop) */
            uint8_t nx = next_node(c, f->buffered);
            if (nx) { lab_note(f, LE_END, f->node, LH_CANCEL, 1); route_go(f, nx, f->buffered, in, LH_CANCEL); break; }
        }
        if (f->anim_done) {                                     /* played to its end (keep flag, or no input yet) */
            uint8_t nx = f->buffered && f->landed ? next_node(c, f->buffered) : 0;   /* routes chain only on a hit */
            lab_note(f, LE_END, f->node, LH_AFTER_END, f->landed);
            if (nx) { route_go(f, nx, f->buffered, in, LH_AFTER_END); break; }
            if (f->landed && has_links(c)) { f->chain_node = f->node; f->chain_t = CHAIN_WINDOW; lab_note(f, LE_CHAINWIN, f->node, 0, CHAIN_WINDOW); }   /* tap later: still the route */
            to_neutral(f, in);
        }
        break;
    }
    case S_HITSTUN:
        if (f->kdelay) f->kdelay--;                              /* KOF's shake after a special's hit: in place */
        else { f->x += f->vx; f->vx = f->kvfr ? fmul16(f->vx, f->kvfr) : f->vx - (f->vx >> 3); clamp(f); }
        if (f->state_t >= (f->anim == BA_HIT_STAND_HEAVY ? STUN_HEAVY : STUN_LIGHT)) { f->frame_ovr = 0xFFFF; to_neutral(f, 0); }   /* a hold's pose ends */
        break;
    case S_KNOCKDOWN:
        if (f->kmode && f->kdelay) { f->kdelay--; break; }       /* KOF's shake after the hit-stop: in place */
        if (f->kmode) kof_fall(f);                               /* a special's hit: KOF98's reaction */
        else { f->y += f->vy; f->vy -= GRAVITY_KD; f->x += f->vx; clamp(f); }
        /* KOF98's fall (a C+D captured on Yuri: 285 / 283 counter rising 26 frames, 287 falling 13, 309 hitting the floor
         * 4, 313 a 2 px bounce 10, 328 down): blowback up, flight down, bounce on the floor, the small hop, down */
        if (f->y <= 0) {
            f->y = 0; f->kmode = 0; f->kvfr = 0;
            if (f->anim == BA_KNOCKDOWN_BOUNCE) {                /* on the floor until it played, then the hop */
                f->vy = 0; f->vx -= f->vx >> 2;
                if (f->anim_done) { f->vy = FIX(1); play(f, BA_KNOCKDOWN_FALL); }
            } else if (f->anim == BA_KNOCKDOWN_FALL) { f->vx = f->vy = 0; enter(f, S_DOWN); play(f, BA_DOWN); }
            else { f->vy = 0; f->vx >>= 1; play(f, BA_KNOCKDOWN_BOUNCE); set_burn(f, 0); }   /* KOF98: a burn ends at the floor */
        } else if (f->vy < 0 && (f->anim == BA_BLOWBACK || f->anim == BA_BLOWBACK_N)) play(f, BA_KNOCKDOWN_FLIGHT);
        break;
    case S_DOWN:
        if (f->state_t >= DOWN_FRAMES) {
            if (f->hp <= 0) { enter(f, S_DEAD); break; }         /* main decides: blink out, a life, or continue */
            enter(f, S_GETUP); play(f, BA_GETUP); f->inv = INV_GETUP;
        }
        break;
    case S_GETUP:
        if (f->anim_done) to_neutral(f, 0);
        break;
    case S_GRAB: hold_update(f, in); break;
    case S_THROW: throw_update(f); break;
    case S_SPECIAL: special_update(f); break;
    default: break;
    }
}

/* ---- being hit ---------------------------------------------------------------------------------------------------- */
void fighter_hit(fighter_t *a, fighter_t *v, uint8_t damage, uint8_t reaction, int8_t push) {
    v->hp -= damage + (a->owner ? a->owner : a)->power;
    voice_play(v->ch, v->team, v->hp > 0 ? VK_HIT : VK_KO);
    v->freeze = HITSTOP;
    if (a->state != S_PROJ) a->freeze = v->freeze;               /* hit-stop; projectiles fly on (nothing updates them) */
    a->hit_mask |= 1 << v->idx; a->landed = 1; v->chain_t = 0;
    (a->owner ? a->owner : a)->target = v;
    lab_note(a->owner ? a->owner : a, LE_HIT, a->state == S_ATTACK || a->state == S_AIR_ATTACK ? a->node : 0xFF, v->idx, damage);
    react(v, INT(v->x) >= INT(a->x) ? 1 : -1, reaction, push);
    if (a->state == S_SPECIAL) kof_react(v, INT(v->x) >= INT(a->x) ? 1 : -1, reaction, a->spec_slide);   /* a special's body hit: KOF98's */
}

/* ---- combat: every attacker's live attack box against every opponent's hurt box --------------------------------------- */
static const bbox_t JUGGLE_BOX = { 0, -24, 28, 20 };       /* a falling fighter's body: KOF boxes (x, y up -, half w, h) */
static const bbox_t LAUNCH_BOX = { 0, -64, 28, 28 };       /* KOF98's launched body (states 286 / 293: box $31 0, 192, 28, 28) */
static int16_t box_x(const fighter_t *f, int8_t bx) { return INT(f->x) + (f->facing > 0 ? -bx : bx); }   /* sprites face left */
static uint8_t boxes_meet(const fighter_t *a, const bbox_t *ab, const fighter_t *v, const bbox_t *vb) {
    int16_t dx = box_x(a, ab->x) - box_x(v, vb->x), dy = (ab->y - INT(a->y)) - (vb->y - INT(v->y));
    if (dx < 0) dx = -dx;
    if (dy < 0) dy = -dy;
    return dx <= ab->w + vb->w && dy <= ab->h + vb->h;
}
static uint8_t grabbable(const fighter_t *v) {
    return !v->inv && !v->y && (v->state == S_IDLE || v->state == S_WALK || v->state == S_HITSTUN);
}
#define AIR_BLOCK_Y 64            /* a special in the air below this height (px) is held by a standing body ahead */
#define PUSH_DX 32                /* a special pushes an opponent standing in its path to keep it this far ahead (KOF's push
                                     boxes: the captured opponent stood 27-49 px ahead at the moves' first impacts) */
void combat(fighter_t **fs, uint8_t n) {
    uint8_t i, j;
    for (i = 0; i < n; i++) {                                    /* specials push who stands in their path: a rush */
        fighter_t *a = fs[i];                                    /* reaches its hit as in the game, not past it */
        if (a->state != S_SPECIAL || INT(a->y) >= AIR_BLOCK_Y) continue;
        for (j = 0; j < n; j++) {
            fighter_t *v = fs[j];
            int16_t d, dz;
            if (v->team == a->team || v->y || (v->state != S_IDLE && v->state != S_WALK && v->state != S_HITSTUN &&
                v->state != S_ATTACK && v->state != S_SPECIAL)) continue;
            dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            d = a->facing > 0 ? INT(v->x) - INT(a->x) : INT(a->x) - INT(v->x);
            if (d <= -8 || d >= PUSH_DX) continue;
            if (!a->y) { v->x = a->x + dir_mul(a->facing, FIX(PUSH_DX)); clamp(v); }
            else {                                               /* a low leap stops at the body (SS4's 421C: P1 */
                int32_t back = dir_mul(a->facing, FIX(PUSH_DX - d));   /* held 30 px before P2 at y 10-51, then */
                a->throw_x0 -= back; a->x -= back; clamp(a);     /* its landing slash hits), never carries it */
            }
        }
    }
    for (i = 0; i < n; i++) {                                    /* throw impacts: the victim's teammates close to it go down */
        fighter_t *a = fs[i], *v = a->held;
        if (!a->impact) continue;
        a->impact = 0;
        if (!v) continue;
        for (j = 0; j < n; j++) {
            fighter_t *o = fs[j];
            int16_t dx, dz;
            if (o == v || o->team != v->team || o->inv || o->state == S_KNOCKDOWN || o->state == S_DOWN || o->state == S_GETUP ||
                o->state == S_THROWN || o->state == S_PROJ || o->state == S_OFF || o->state == S_DEAD) continue;
            dx = INT(o->x) - INT(v->x); dz = INT(o->z) - INT(v->z);
            if (dx < -SPLASH_DX || dx > SPLASH_DX || dz < -Z_HIT || dz > Z_HIT) continue;
            o->hp -= SPLASH_DAMAGE; o->freeze = HITSTOP; a->target = o;
            react(o, dx >= 0 ? 1 : -1, R_KNOCKDOWN, 0);
        }
    }
    for (i = 0; i < n; i++) {                                    /* grabs: walking forward into a standing opponent */
        fighter_t *a = fs[i];
        if (!a->pushing || a->state != S_WALK || !a->ch->throws[BT_THROW_C].nrows) continue;
        for (j = 0; j < n; j++) {
            fighter_t *v = fs[j];
            int16_t dz, d;
            if (v->team == a->team || !grabbable(v)) continue;
            dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            d = a->facing > 0 ? INT(v->x) - INT(a->x) : INT(a->x) - INT(v->x);
            if (d > 0 && d <= GRAB_DX) { grab(a, v); break; }
        }
    }
    for (i = 0; i < n; i++) {
        fighter_t *a = fs[i];
        const bbox_t *atk;
        uint8_t sounded = 0;                                     /* one hit sound per attack, however many it hits */
        if (a->freeze) continue;
        if (a->state == S_ATTACK || a->state == S_AIR_ATTACK) {
            const bstep_t *sa = fighter_step(a);
            if (!(sa->flags & 1)) continue;
            atk = &sa->atk;
        } else if ((a->state == S_SPECIAL || a->state == S_PROJ) && a->spec_atk) atk = a->spec_atk;
        else continue;
        for (j = 0; j < n; j++) {
            fighter_t *v = fs[j];
            const bstep_t *sv;
            int16_t dz, dx, dy;
            const bbox_t *hb;
            if (v->team == a->team || (a->hit_mask & (1 << v->idx)) || v->inv) continue;
            if (v->state == S_DOWN || v->state == S_GETUP || v->state == S_THROW ||
                v->state == S_THROWN || v->state == S_PROJ || v->state == S_OFF || v->state == S_DEAD) continue;
            if (v->state == S_KNOCKDOWN && v->y <= 0) continue;  /* juggle: hittable while it falls, no limit */
            dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            sv = fighter_step(v);
            if (sv->flags & 2) hb = &sv->hurt;
            else if (v->state == S_KNOCKDOWN) hb = (v->kmode & KM_LAUNCH) ? &LAUNCH_BOX : &JUGGLE_BOX;   /* KOF's falls have no hurt box */
            else continue;
            dx = box_x(a, atk->x) - box_x(v, hb->x);
            dy = (atk->y - INT(a->y)) - (hb->y - INT(v->y));
            if (dx < 0) dx = -dx;
            if (dy < 0) dy = -dy;
            if (dx > atk->w + hb->w || dy > atk->h + hb->h) continue;
            {                                                /* spark: the centre of the boxes' overlap, where they */
                int16_t ax = box_x(a, atk->x), vx = box_x(v, hb->x);    /* touch (the centres' midpoint drifted toward */
                int16_t ay = floor_top + INT(a->z) - INT(a->y) + atk->y, vy = floor_top + INT(v->z) - INT(v->y) + hb->y;   /* a long box's middle) */
                int16_t sx = ((ax - atk->w > vx - hb->w ? ax - atk->w : vx - hb->w) + (ax + atk->w < vx + hb->w ? ax + atk->w : vx + hb->w)) >> 1;
                int16_t sy = ((ay - atk->h > vy - hb->h ? ay - atk->h : vy - hb->h) + (ay + atk->h < vy + hb->h ? ay + atk->h : vy + hb->h)) >> 1;
                uint8_t sfx = SFX_HIT_CD;
                if (a->state == S_ATTACK || a->state == S_AIR_ATTACK) {
                    const rnode_t *c = NODE(a, a->node);
                    const banim_t *an = &a->ch->anims[a->anim];
                    static const uint8_t EFFECT_R[5] = { 0, R_KNOCKDOWN, R_LAUNCH, R_TRIP, R_BLOWBACK };
                    uint8_t dmg = c->damage, rc = c->effect ? EFFECT_R[c->effect] : c->weight ? R_HEAVY : R_LIGHT, k, total = 0, later = 0;
                    for (k = 0; k < an->nsteps; k++)                 /* multi-hit normal: damage split over its hits, */
                        if (an->steps[k].flags & 4) { total++; if (k > a->step) later++; }   /* knockdown on the last */
                    if (total > 1) {
                        dmg = later ? dmg / total : dmg - dmg / total * (total - 1);
                        if (later && rc >= R_KNOCKDOWN) rc = R_HEAVY;
                    }
                    if (rc < R_KNOCKDOWN) sfx = hit_sound(c->anim);
                    if (!sounded++) snd_sfx(sfx);
                    fighter_hit(a, v, dmg, rc, c->push);
                } else if (a->spec_prev_hit & 8) {       /* a running grab's reach: it catches, the continuation hits */
                    a->hit_mask |= 1 << v->idx; a->landed = 1; a->target = v; v->freeze = HITSTOP;
                    if (v->state == S_WALK) to_neutral(v, 0);
                    continue;
                } else {
                    if (!sounded++) { if (a->state == S_SPECIAL || a->pdef) hit_sfx(a->spec_fx); else snd_sfx(sfx); }
                    fighter_hit(a, v, a->spec_dmg, a->spec_react, 0);
                    if ((a->state == S_SPECIAL || a->pdef) && a->spec_fx >> 6) set_burn(v, a->spec_fx >> 6);
                }
                spark_hit(sx, sy, sfx >= SFX_HIT_C, a->facing);  /* KOF98: A / B small, C / D / C+D big */
                if (a->pdef) { proj_hit(a); break; }             /* a projectile hits once */
            }
        }
    }
    for (i = 0; i < NPJ; i++) {                                  /* projectiles meeting: both hits spent (KOF98 */
        fighter_t *a = &projectiles[i];                          /* measured: EX Ryo's Ko-ou-ken ended on Yuri's */
        if (a->state != S_PROJ || !a->pdef || !a->spec_atk) continue;   /* eruption, whose attack went off) */
        for (j = 0; j < NPJ; j++) {
            fighter_t *b = &projectiles[j];
            int16_t dz;
            if (b->state != S_PROJ || !b->pdef || b->team == a->team || !b->pown) continue;
            dz = INT(a->z) - INT(b->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            if (!boxes_meet(a, a->spec_atk, b, b->pown)) continue;
            proj_hit(a); proj_hit(b);
            break;
        }
    }
}

void fighter_init(fighter_t *f, const bchar_t *ch, uint8_t set, uint8_t palbase, uint8_t team, int16_t x, int16_t z) {
    uint8_t i;
    *f = (fighter_t){ 0 };                                       /* nothing left from the demo or the last fight */
    f->ch = ch; f->set = set; f->palbase = palbase; f->team = team;
    for (i = 0; i < ch->npal && i < MAX_PALS; i++) PAL_setPalette(palbase + i, ch->pals + ((set * ch->npal + i) << 4));
    f->x = FIX(x); f->z = FIX(z); f->y = 0; f->vx = f->vy = f->vz = 0;
    f->facing = team ? -1 : 1; f->hp = 60; f->freeze = f->inv = 0; f->held = 0;
    f->shown_frame = 0xFFFF; f->frame_ovr = 0xFFFF; f->zfront = 0; f->pushing = 0; f->target = 0; f->spec_atk = 0; f->proj[0] = f->proj[1] = 0; f->owner = 0; f->ncols = 0; f->burn = 0; f->spec_fx = 0;
    f->jump_kind = f->jump_dir = 0; f->meter = gmeter.max;
    enter(f, S_IDLE); play(f, BA_IDLE);
}
