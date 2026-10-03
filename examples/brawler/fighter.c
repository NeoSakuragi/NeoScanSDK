/* Beat 'em up fighter: state machine, combo routes, hit reactions, combat and rendering (see fighter.h).
 * Animation semantics are KOF's: a step shows a frame for N ticks; "hold" animations stop on their last step.
 * The 68000 has no 32-bit multiply/divide (and there is no libgcc here): only adds, shifts and dir_mul(). */
#include <neoscan.h>
#include "neo_internal.h"
#include "fighter.h"
#include "sound.h"

#define GRAVITY_KD  0x7800        /* knockdown gravity 0.47 px/frame^2 (measured on KOF95) */
#define DOWN_FRAMES 40
#define INV_GETUP   30
#define HITSTOP     13            /* hit-stop, the same for every hit: light ones land as hard as heavy ones (KOF98 ~10-12) */
#define STUN_LIGHT  36            /* hitstun frames: 3x a fighting game's, a beat 'em up keeps its victims in the chain */
#define STUN_HEAVY  54
#define CHAIN_WINDOW 30           /* frames after a route step that hit during which A / B continues the route (Final Fight) */
#define RUN_MUL     2             /* run = walk << 1 */
#define X_MIN 16
#define X_MAX (WORLD_W - 16)

static const char *NAMES[S_COUNT] = { "IDLE    ", "WALK    ", "RUN     ", "PREJUMP ", "AIR     ", "LAND    ", "ATTACK  ",
    "AIR ATK ", "HITSTUN ", "KNOCKDN ", "DOWN    ", "GETUP   ", "GRAB    ", "GRABBED ", "THROW   ", "THROWN  ", "SPECIAL ", "DEAD    ", "PROJ    ", "OFF     " };
const char *fighter_state_name(uint8_t st) { return NAMES[st]; }

/* ---- combo routes (one table for every fighter: the links are KOF normals every fighter has) -------------------
 * A1 -A-> A2 -A-> AAA (knockdown)        A1/A2 -B-> AB / AAB (launch)
 * B1 -B-> BB (knockdown)                 B1 -A-> BA -B-> BAB (sweep: trip)
 * finishers inside any window: forward+A = body toss (knockdown), down+B = sweep. Air: A / B.  D = special (body toss). */
enum { N_NONE, N_A1, N_A2, N_AAA, N_AB, N_AAB, N_B1, N_BB, N_BA, N_BAB, N_FWD_A, N_AIR_A, N_AIR_B };
const cnode_t COMBO[] = {
    /* anim            dmg rct          push nextA   nextB   fwdA     downB */
    { 0,                0,  0,           0,  0,      0,      0,       0 },
    { BA_ATK_A_CLOSE,   3,  R_LIGHT,     3,  N_A2,   N_AB,   N_FWD_A, N_BAB },
    { BA_ATK_A_FAR,     3,  R_LIGHT,     3,  N_AAA,  N_AAB,  N_FWD_A, N_BAB },
    { BA_ATK_C_CLOSE,   8,  R_KNOCKDOWN, 0,  0,      0,      0,       0 },
    { BA_ATK_D_CLOSE,   6,  R_HEAVY,     6,  0,      0,      N_FWD_A, N_BAB },
    { BA_ATK_D_FAR,     9,  R_LAUNCH,    0,  0,      0,      0,       0 },
    { BA_ATK_B_CLOSE,   4,  R_LIGHT,     3,  N_BA,   N_BB,   N_FWD_A, N_BAB },
    { BA_ATK_D_CLOSE,   8,  R_KNOCKDOWN, 0,  0,      0,      0,       0 },
    { BA_ATK_C_FAR,     5,  R_HEAVY,     5,  0,      N_BAB,  N_FWD_A, N_BAB },
    { BA_ATK_D_CROUCH,  7,  R_TRIP,      0,  0,      0,      0,       0 },
    { BA_BODY_TOSS,     10, R_KNOCKDOWN, 0,  0,      0,      0,       0 },
    { BA_ATK_C_JUMP,    6,  R_HEAVY,     4,  0,      0,      0,       0 },
    { BA_ATK_D_JUMP,    8,  R_KNOCKDOWN, 0,  0,      0,      0,       0 },
};

/* ---- animation player ------------------------------------------------------------------------------------- */
static void play(fighter_t *f, uint8_t anim) {
    f->anim = anim; f->step = 0; f->anim_done = 0;
    f->tick = f->ch->anims[anim].steps[0].ticks;
}
static void play_if_new(fighter_t *f, uint8_t anim) { if (f->anim != anim) play(f, anim); }
static void anim_tick(fighter_t *f) {
    const banim_t *an = &f->ch->anims[f->anim];
    if (f->tick > 1) { f->tick--; return; }
    if (f->step + 1 < an->nsteps) f->step++;
    else { f->anim_done = 1; if (an->hold) return; f->step = 0; }   /* loops report one pass done too */
    f->tick = an->steps[f->step].ticks;
    if (an->steps[f->step].flags & 4) f->hit_mask = 0;              /* multi-hit normals: a new hit window */
}
const bstep_t *fighter_step(const fighter_t *f) { return &f->ch->anims[f->anim].steps[f->step]; }
void fighter_play(fighter_t *f, uint8_t anim) { play(f, anim); }
void fighter_animate(fighter_t *f) { anim_tick(f); }

/* ---- helpers --------------------------------------------------------------------------------------------------- */
static int32_t dir_mul(int8_t d, int32_t v) { return d > 0 ? v : d < 0 ? -v : 0; }
static void enter(fighter_t *f, uint8_t st) { f->state = st; f->state_t = 0; }
static void clamp(fighter_t *f) {
    if (f->x < FIX(X_MIN)) f->x = FIX(X_MIN);
    if (f->x > FIX(X_MAX)) f->x = FIX(X_MAX);
    if (f->z < 0) f->z = 0;
    if (f->z > FIX(Z_DEPTH)) f->z = FIX(Z_DEPTH);
}
static void to_neutral(fighter_t *f, const intent_t *in) {
    if (in && (in->dx || in->dz)) { enter(f, S_WALK); play_if_new(f, BA_WALK_FWD); }
    else { enter(f, S_IDLE); play_if_new(f, BA_IDLE); }
}
static uint8_t hit_sound(uint8_t anim) {                       /* KOF98's hit sound per button */
    switch (anim) {
    case BA_ATK_A_CLOSE: case BA_ATK_A_FAR: return SFX_HIT_A;
    case BA_ATK_B_CLOSE: case BA_ATK_B_FAR: return SFX_HIT_B;
    case BA_ATK_C_CLOSE: case BA_ATK_C_FAR: case BA_ATK_C_JUMP: return SFX_HIT_C;
    case BA_ATK_D_CLOSE: case BA_ATK_D_FAR: case BA_ATK_D_CROUCH: case BA_ATK_D_JUMP: return SFX_HIT_D;
    default: return SFX_HIT_CD;
    }
}
static void start_node(fighter_t *f, uint8_t node) {
    uint8_t a = COMBO[node].anim;
    snd_sfx(a == BA_ATK_A_CLOSE || a == BA_ATK_A_FAR || a == BA_ATK_C_CLOSE || a == BA_ATK_C_FAR || a == BA_ATK_C_JUMP
            ? SFX_SWING_LIGHT : SFX_SWING_HEAVY);
    f->node = node; f->buffered = 0; f->hit_mask = 0; f->landed = 0; f->chain_t = 0;
    enter(f, node >= N_AIR_A ? S_AIR_ATTACK : S_ATTACK); play(f, COMBO[node].anim);
}
static uint8_t combo_input(const fighter_t *f, const intent_t *in) {     /* IN_* | 0x80 forward | 0x40 down */
    uint8_t b = in->press & (IN_A | IN_B);
    if (!b) return 0;
    if (in->dx == f->facing) b |= 0x80;
    if (in->dz > 0) b |= 0x40;
    return b;
}
static uint8_t next_node(const cnode_t *c, uint8_t b) {
    if ((b & 0x80) && (b & IN_A) && c->next_fwd_a) return c->next_fwd_a;
    if ((b & 0x40) && (b & IN_B) && c->next_down_b) return c->next_down_b;
    return (b & IN_A) ? c->next_a : (b & IN_B) ? c->next_b : 0;
}

void fighter_revive(fighter_t *f) {
    f->hp = 60; f->held = 0; f->frame_ovr = 0xFFFF; f->y = 0; f->vx = f->vy = f->vz = 0;
    enter(f, S_GETUP); play(f, BA_GETUP); f->inv = 90;
}

/* ---- reactions -------------------------------------------------------------------------------------------------------- */
static void release(fighter_t *a);
static void special_end(fighter_t *f);
static void react(fighter_t *v, int8_t away, uint8_t reaction, int8_t push) {   /* away: direction the victim is sent */
    if (v->state == S_SPECIAL) special_end(v);                   /* hit out of a special: its projectiles go */
    if (v->state == S_GRAB) release(v);                          /* hit while holding or while held: the hold ends */
    else if (v->state == S_GRABBED) release(v->held);
    v->facing = -away;                                           /* turn toward the attacker */
    if (v->y > 0 && reaction < R_KNOCKDOWN) {                    /* hit in the air: knocked down */
        enter(v, S_KNOCKDOWN); v->vy = FIX(2); v->vx = dir_mul(away, FIX(2)); play(v, BA_HIT_AIR); return;
    }
    switch (v->hp <= 0 ? R_KNOCKDOWN : reaction) {
    case R_LIGHT: case R_HEAVY:
        enter(v, S_HITSTUN); play(v, reaction == R_LIGHT ? BA_HIT_STAND_LIGHT : BA_HIT_STAND_HEAVY);
        v->vx = dir_mul(away, FIX(push) >> 2);
        break;
    case R_KNOCKDOWN: enter(v, S_KNOCKDOWN); v->vy = FIX(5); v->vx = dir_mul(away, FIX(2) + 0x8000); play(v, BA_BLOWBACK); break;
    case R_LAUNCH:    enter(v, S_KNOCKDOWN); v->vy = FIX(7); v->vx = dir_mul(away, FIX(3)); play(v, BA_KNOCKDOWN_FLIGHT); break;
    case R_TRIP:      enter(v, S_KNOCKDOWN); v->vy = FIX(3); v->vx = dir_mul(away, FIX(1)); play(v, BA_TRIP); break;
    }
}

/* ---- hold and throws -----------------------------------------------------------------------------------------------------
 * Walking into a standing opponent grabs it (combat). Hold pose = row 0 of the forward+C throw script for both. In the
 * hold: A = knee (close B, damage on its attack frame), the third sends the victim down; B / D = the KOF forward+C / forward+D throw, played from its
 * per-frame script (thrower frame + offset, victim posture + offset + facing + draw order); 90 frames: the victim breaks
 * free, or sooner by mashing ESCAPE_PRESSES buttons. Enemies grab too (AI intent `grab`). Postures are KOF's shared victim states; each fighter has its own frame for them (bchar_t.vposes). */
#define GRAB_DX      32
#define GRAB_TIME    90
#define GRAB_HITS    3
#define GRAB_DAMAGE  3
#define THROW_DAMAGE 12
#define ESCAPE_PRESSES 4

static void show_pose(fighter_t *v, uint8_t vp) {
    uint16_t fr = vp < VP_COUNT ? v->ch->vposes[vp] : 0xFFFF;
    if (fr != 0xFFFF) v->frame_ovr = fr;
    else { v->frame_ovr = 0xFFFF; play_if_new(v, BA_HIT_STAND_LIGHT); }   /* no frame for it: the light hit pose */
}
static void place_victim(const fighter_t *a, fighter_t *v, const bthrow_row_t *r) {
    v->x = a->x + dir_mul(a->facing, FIX(r->vx));
    v->y = a->y + FIX(r->vy); if (v->y < 0) v->y = 0;
    v->z = a->z;
    v->facing = (r->flags & 1) ? a->facing : -a->facing;
    v->zfront = (r->flags & 2) != 0;
}
static void grab(fighter_t *a, fighter_t *v) {
    const bthrow_row_t *r = a->ch->throws[BT_THROW_C].rows;
    enter(a, S_GRAB); a->held = v; a->target = v; a->grab_hits = 0;
    a->frame_ovr = r->tframe;
    if (a->team) stat_grabs++;
    enter(v, S_GRABBED); v->held = a; v->vx = v->vy = v->vz = 0; v->grab_hits = 0;   /* victim: presses mashed */
    show_pose(v, r->vpose); place_victim(a, v, r);
}
static void release(fighter_t *a) {                              /* both free where they stand */
    fighter_t *v = a->held;
    a->held = 0; a->frame_ovr = 0xFFFF; a->zfront = 0; a->y = 0; to_neutral(a, 0);
    if (v) { v->held = 0; v->frame_ovr = 0xFFFF; v->zfront = 0; to_neutral(v, 0); }
}
static void hold_update(fighter_t *f, const intent_t *in) {
    fighter_t *v = f->held;
    const bthrow_row_t *r = f->ch->throws[BT_THROW_C].rows;
    if (f->frame_ovr == 0xFFFF) {                                /* a knee is playing */
        if (f->buffered && ((fighter_step(f)->flags & 1) || f->anim_done)) {   /* it lands on its attack frame */
            f->buffered = 0; snd_sfx(SFX_HIT_B);
            v->hp -= GRAB_DAMAGE; v->frame_ovr = 0xFFFF; play(v, BA_HIT_STAND_LIGHT);
            f->freeze = v->freeze = 4;
            return;
        }
        if (!f->anim_done) return;
        if (f->grab_hits >= GRAB_HITS) { release(f); react(v, f->facing, R_KNOCKDOWN, 0); return; }
        f->frame_ovr = r->tframe; show_pose(v, r->vpose);
        return;
    }
    if (in->press & IN_A) {                                      /* knee: damage when its KOF attack box comes out */
        f->frame_ovr = 0xFFFF; play(f, BA_ATK_B_CLOSE); f->grab_hits++; f->buffered = 1;
        return;
    }
    if (in->press & (IN_B | IN_D)) {
        uint8_t t = (in->press & IN_B) ? BT_THROW_C : BT_THROW_D;
        if (!f->ch->throws[t].nrows) t = BT_THROW_C;
        f->throw_id = t; f->throw_x0 = f->x; enter(f, S_THROW); enter(v, S_THROWN);
        if (f->team) stat_throws++;
        return;
    }
    if (f->state_t >= GRAB_TIME) {                               /* the victim breaks free */
        release(f); v->x += dir_mul(f->facing, FIX(10)); clamp(v); v->inv = 20;
    }
}
static void throw_update(fighter_t *f) {
    const bthrow_t *th = &f->ch->throws[f->throw_id];
    fighter_t *v = f->held;
    const bthrow_row_t *r;
    if (f->state_t > th->nrows) {                                /* script over: the victim lies where it landed */
        release(f); clamp(f);
        v->hp -= THROW_DAMAGE; v->y = 0; clamp(v); enter(v, S_DOWN); play(v, BA_DOWN);
        return;
    }
    r = &th->rows[f->state_t - 1];
    f->frame_ovr = r->tframe;
    f->x = f->throw_x0 + dir_mul(f->facing, FIX(r->tx)); f->y = FIX(r->ty);
    if (r->vpose != 0xFF) show_pose(v, r->vpose);
    place_victim(f, v, r);
}

/* ---- specials ------------------------------------------------------------------------------------------------------------
 * D: the fighter's first ground special, forward+D (any direction held: the fighter faces it) the second (export_bm.py
 * picks them), played from the per-frame script captured in the game: fighter frame + offset, body attack box (KOF's,
 * from the move's own animation) and up to two objects (projectiles), each a pool entity with its frame, offset, facing
 * and sprite bounds as attack box. A new hit window (box after a row without) lets the same targets be hit again. */
#define SPECIAL_DAMAGE 8
fighter_t projectiles[NPJ];
uint16_t stat_grabs, stat_specials, stat_throws, stat_escapes;

void projectile_reset(fighter_t *p) {
    p->ch = &bm_chars[0]; p->anim = 0; p->step = 0; p->tick = 1;
    p->frame_ovr = 0xFFFF; p->shown_frame = 0xFFFF; p->state = S_OFF; p->spec_atk = 0; p->owner = 0;
    p->x = p->y = p->z = 0; p->facing = 1; p->zfront = 1; p->freeze = p->inv = 0; p->hit_mask = 0; p->held = 0; p->ncols = 0;
}
static fighter_t *proj_alloc(fighter_t *owner) {
    uint8_t i;
    for (i = 0; i < NPJ; i++) {
        fighter_t *p = &projectiles[i];
        if (p->state != S_OFF) continue;
        p->state = S_PROJ; p->ch = owner->ch; p->palbase = owner->palbase; p->team = owner->team; p->owner = owner;
        p->frame_ovr = 0xFFFF; p->spec_atk = 0; p->hit_mask = 0;
        return p;
    }
    return 0;                                                    /* pool empty: this special shows no objects */
}
static void special_end(fighter_t *f) {
    uint8_t k;
    for (k = 0; k < 2; k++) if (f->proj[k]) { projectile_reset(f->proj[k]); f->proj[k] = 0; }
    f->frame_ovr = 0xFFFF; f->spec_atk = 0; f->y = 0;
}
static void start_special(fighter_t *f, uint8_t k) {
    if (f->team) stat_specials++;
    f->spec_id = k; f->throw_x0 = f->x; f->hit_mask = 0; f->spec_prev_hit = 0; f->spec_atk = 0;
    f->proj[0] = proj_alloc(f); f->proj[1] = proj_alloc(f);
    enter(f, S_SPECIAL);
}
static void special_update(fighter_t *f) {
    const bspec_t *sp = &f->ch->specials[f->spec_id];
    const bspec_row_t *r;
    uint8_t k;
    if (f->state_t > sp->nrows) { special_end(f); to_neutral(f, 0); return; }
    r = &sp->rows[f->state_t - 1];
    if (f->state_t <= sp->inv_rows && f->inv < 2) f->inv = 2;    /* invincible move: from its first frame to its last hit */
    f->frame_ovr = r->frame;
    f->x = f->throw_x0 + dir_mul(f->facing, FIX(r->x)); f->y = r->y > 0 ? FIX(r->y) : 0; clamp(f);
    if (r->hit && !f->spec_prev_hit) f->hit_mask = 0;            /* a new hit window */
    f->spec_prev_hit = r->hit; f->spec_atk = r->hit ? &r->atk : 0;
    for (k = 0; k < 2; k++) {
        fighter_t *p = f->proj[k];
        const bsobj_t *o = &r->obj[k];
        if (!p) continue;
        if (o->frame == 0xFFFF) { p->frame_ovr = 0xFFFF; p->spec_atk = 0; continue; }
        if (p->frame_ovr == 0xFFFF) p->hit_mask = 0;             /* the object (re)appears: fresh hits */
        p->frame_ovr = o->frame;
        p->x = f->throw_x0 + dir_mul(f->facing, FIX(o->x)); p->y = o->y > 0 ? FIX(o->y) : 0; p->z = f->z;
        p->facing = o->same ? f->facing : -f->facing;
        p->spec_atk = o->box.w ? &o->box : 0;
    }
}

/* ---- state machine --------------------------------------------------------------------------------------------- */
void fighter_update(fighter_t *f, const intent_t *in) {
    const bphys_t *ph = &f->ch->phys;
    if (f->state == S_GRABBED && in->press && ++f->grab_hits >= ESCAPE_PRESSES) {   /* mash to break free (hit-stop too) */
        fighter_t *h = f->held;
        release(h); f->x += dir_mul(h->facing, FIX(10)); clamp(f); f->inv = 20; f->freeze = h->freeze = 0; stat_escapes++;
    }
    if (f->freeze) { f->freeze--; return; }                      /* hit-stop: nothing moves, nothing animates */
    if (f->inv) f->inv--;
    if (f->chain_t) f->chain_t--;
    f->state_t++;
    f->pushing = 0;
    switch (f->state) {
    case S_IDLE: case S_WALK: case S_RUN: {
        uint8_t b = in->press;
        if (in->dx) f->facing = in->dx;                          /* beat 'em up: face where you walk */
        else if (in->face) f->facing = in->face;
        if (b & IN_C) { enter(f, S_PREJUMP); play(f, BA_PREJUMP); f->vx = dir_mul(in->dx, ph->jump_dx); f->vz = dir_mul(in->dz, FIX(1)); break; }
        if (b & IN_D) {                                          /* special: D, or forward+D (facing follows the stick) */
            uint8_t k = in->dx ? BS_FWD_D : BS_D;
            if (f->ch->specials[k].nrows) start_special(f, k); else start_node(f, N_FWD_A);
            break;
        }
        if (b & (IN_A | IN_B)) {
            uint8_t ci = combo_input(f, in), nx = f->chain_t ? next_node(&COMBO[f->chain_node], ci) : 0;
            if (nx) { start_node(f, nx); break; }                  /* the route goes on (Final Fight: tap, wait, tap) */
            if (f->state == S_RUN && (b & IN_A)) { start_node(f, N_FWD_A); break; }   /* dash attack */
            if ((ci & 0x40) && (ci & IN_B)) { start_node(f, N_BAB); break; }
            start_node(f, (b & IN_A) ? N_A1 : N_B1); break;
        }
        if (f->state == S_RUN && in->dx == f->facing) {
            f->x += dir_mul(f->facing, ph->walk << RUN_MUL >> 1); f->z += dir_mul(in->dz, FIX(1)); clamp(f); break;
        }
        if (in->run && in->dx) { enter(f, S_RUN); play(f, BA_RUN); break; }
        to_neutral(f, in);
        if (f->state == S_WALK) {
            f->x += dir_mul(in->dx, ph->walk); f->z += dir_mul(in->dz, FIX(1)); clamp(f);
            f->pushing = in->dx != 0 && (!f->team || in->grab);   /* facing follows dx: walking forward; enemies on purpose */
        }
        break;
    }
    case S_PREJUMP:
        if (f->state_t >= 3) { f->vy = ph->jump_vy0 - (ph->jump_vy0 >> 2);   /* 3/4 take-off speed: 56 % of KOF's jump height */ enter(f, S_AIR); play(f, f->vx ? BA_JUMP_FWD_RISE : BA_JUMP_UP_RISE); }
        break;
    case S_AIR: case S_AIR_ATTACK:
        if (f->state == S_AIR && (in->press & (IN_A | IN_B))) start_node(f, (in->press & IN_A) ? N_AIR_A : N_AIR_B);
        f->y += f->vy; f->vy -= ph->gravity; f->x += f->vx; f->z += f->vz; clamp(f);
        if (f->state == S_AIR && f->vy < 0 && f->anim != BA_JUMP_FWD_FALL && f->anim != BA_JUMP_UP_FALL)
            play(f, f->vx ? BA_JUMP_FWD_FALL : BA_JUMP_UP_FALL);
        if (f->y <= 0) { f->y = 0; f->vx = f->vy = f->vz = 0; enter(f, S_LAND); play(f, BA_LAND); }
        break;
    case S_LAND:
        if (f->state_t >= 2) to_neutral(f, in);
        break;
    case S_ATTACK: {
        const cnode_t *c = &COMBO[f->node];
        uint8_t ci = combo_input(f, in);
        if (ci) f->buffered = ci;                                /* the last press inside the link wins */
        if (f->anim_done) {                                     /* a beat 'em up never cuts an attack: the next starts after it */
            uint8_t nx = f->buffered && f->landed ? next_node(c, f->buffered) : 0;   /* routes chain only on a hit */
            if (nx) { start_node(f, nx); break; }
            if (f->landed && (c->next_a | c->next_b | c->next_fwd_a | c->next_down_b)) { f->chain_node = f->node; f->chain_t = CHAIN_WINDOW; }   /* tap later: still the route */
            to_neutral(f, in);
        }
        break;
    }
    case S_HITSTUN:
        f->x += f->vx; f->vx -= f->vx >> 3; clamp(f);
        if (f->state_t >= (f->anim == BA_HIT_STAND_HEAVY ? STUN_HEAVY : STUN_LIGHT)) to_neutral(f, 0);
        break;
    case S_KNOCKDOWN:
        f->y += f->vy; f->vy -= GRAVITY_KD; f->x += f->vx; clamp(f);
        if (f->y <= 0) {
            f->y = 0;
            if (f->anim != BA_KNOCKDOWN_BOUNCE) { f->vy = FIX(3); f->vx >>= 1; play(f, BA_KNOCKDOWN_BOUNCE); }
            else { f->vx = f->vy = 0; enter(f, S_DOWN); play(f, BA_DOWN); }
        } else if (f->vy < 0 && f->anim == BA_BLOWBACK) play(f, BA_KNOCKDOWN_FALL);
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
    anim_tick(f);
}

/* ---- being hit ---------------------------------------------------------------------------------------------------- */
void fighter_hit(fighter_t *a, fighter_t *v, uint8_t damage, uint8_t reaction, int8_t push) {
    v->hp -= damage;
    v->freeze = HITSTOP;
    if (a->state != S_PROJ) a->freeze = v->freeze;               /* hit-stop; projectiles fly on (nothing updates them) */
    a->hit_mask |= 1 << v->idx; a->landed = 1; v->chain_t = 0;
    (a->owner ? a->owner : a)->target = v;
    react(v, INT(v->x) >= INT(a->x) ? 1 : -1, reaction, push);
}

/* ---- combat: every attacker's live attack box against every opponent's hurt box --------------------------------------- */
static int16_t box_x(const fighter_t *f, int8_t bx) { return INT(f->x) + (f->facing > 0 ? -bx : bx); }   /* sprites face left */
static uint8_t grabbable(const fighter_t *v) {
    return !v->inv && !v->y && (v->state == S_IDLE || v->state == S_WALK || v->state == S_HITSTUN);
}
void combat(fighter_t **fs, uint8_t n) {
    uint8_t i, j;
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
            if (v->team == a->team || (a->hit_mask & (1 << v->idx)) || v->inv) continue;
            if (v->state == S_KNOCKDOWN || v->state == S_DOWN || v->state == S_GETUP || v->state == S_THROW ||
                v->state == S_THROWN || v->state == S_PROJ || v->state == S_OFF || v->state == S_DEAD) continue;
            dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            sv = fighter_step(v);
            if (!(sv->flags & 2)) continue;
            dx = box_x(a, atk->x) - box_x(v, sv->hurt.x);
            dy = (atk->y - INT(a->y)) - (sv->hurt.y - INT(v->y));
            if (dx < 0) dx = -dx;
            if (dy < 0) dy = -dy;
            if (dx > atk->w + sv->hurt.w || dy > atk->h + sv->hurt.h) continue;
            {                                                /* spark: midway between the two boxes' centres */
                int16_t sx = (box_x(a, atk->x) + box_x(v, sv->hurt.x)) >> 1;
                int16_t sy = ((FLOOR_TOP + INT(a->z) - INT(a->y) + atk->y) + (FLOOR_TOP + INT(v->z) - INT(v->y) + sv->hurt.y)) >> 1;
                uint8_t sfx = SFX_HIT_CD;
                if (a->state == S_ATTACK || a->state == S_AIR_ATTACK) {
                    const cnode_t *c = &COMBO[a->node];
                    const banim_t *an = &a->ch->anims[a->anim];
                    uint8_t dmg = c->damage, rc = c->reaction, k, total = 0, later = 0;
                    for (k = 0; k < an->nsteps; k++)                 /* multi-hit normal: damage split over its hits, */
                        if (an->steps[k].flags & 4) { total++; if (k > a->step) later++; }   /* knockdown on the last */
                    if (total > 1) {
                        dmg = later ? dmg / total : dmg - dmg / total * (total - 1);
                        if (later && rc >= R_KNOCKDOWN) rc = R_HEAVY;
                    }
                    if (rc < R_KNOCKDOWN) sfx = hit_sound(c->anim);
                    snd_sfx(sfx);
                    fighter_hit(a, v, dmg, rc, c->push);
                } else { snd_sfx(sfx); fighter_hit(a, v, SPECIAL_DAMAGE, R_KNOCKDOWN, 0); }
                spark_hit(sx, sy, sfx >= SFX_HIT_C, a->facing);  /* KOF98: A / B small, C / D / C+D big */
            }
        }
    }
}

void fighter_init(fighter_t *f, const bchar_t *ch, uint8_t set, uint8_t palbase, uint8_t team, int16_t x, int16_t z) {
    uint8_t i;
    f->ch = ch; f->set = set; f->palbase = palbase; f->team = team;
    for (i = 0; i < ch->npal && i < MAX_PALS; i++) PAL_setPalette(palbase + i, ch->pals + ((set * ch->npal + i) << 4));
    f->x = FIX(x); f->z = FIX(z); f->y = 0; f->vx = f->vy = f->vz = 0;
    f->facing = team ? -1 : 1; f->hp = 60; f->freeze = f->inv = 0; f->held = 0;
    f->shown_frame = 0xFFFF; f->frame_ovr = 0xFFFF; f->zfront = 0; f->pushing = 0; f->target = 0; f->spec_atk = 0; f->proj[0] = f->proj[1] = 0; f->owner = 0; f->ncols = 0;
    enter(f, S_IDLE); play(f, BA_IDLE);
}
