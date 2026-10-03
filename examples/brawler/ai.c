/* Enemy AI, Final Fight style.
 * Every enemy picks the nearest player and keeps to its own side of him. Two attack tokens: every 16 frames they go to
 * the able enemy closest to its player (one token); the holder closes in to ATTACK_DX on the player's depth line and, in
 * range and facing him, presses A one to three times (the combo chains only if the hits land), then waits a random
 * cooldown (120-247 frames); 1 approach in 8 instead walks into him to grab (knees every 24 frames, after two maybe a throw); in
 * mid range near his depth line any enemy sometimes fires its forward+D special (the projectile one when it has one), so the
 * hoverers shoot. The others hover around HOVER_DX at a random depth offset, so the crowd surrounds instead of stacking. */
#include "ai.h"

#define TOKENS     1              /* attackers at a time (2 swarmed the player) */
#define ATTACK_DX  36
#define HOVER_DX   90
#define HOVER_GO_DX 16            /* a hoverer at its spot sets off again only when the spot is this far (x) ... */
#define HOVER_GO_DZ 8             /* ... or this far in depth */
#define RANGE_MIN  20             /* attack when the player is this close ... */
#define RANGE_MAX  52             /* ... to this far, and on the same depth line */
#define RANGE_DZ   6
#define MAX_F      8
#define GRAB_PLAN  1              /* of 8 approaches end in a grab instead of punches */
#define SPEC_MIN   70             /* special (forward+D) from this far ... */
#define SPEC_MAX   140            /* ... to this far, near the player's depth line, about once a second in range (any enemy) */

typedef struct {
    uint8_t token;
    uint8_t cooldown;             /* frames before the next attack */
    uint8_t presses, press_t;     /* A presses left in the current attack, frames to the next one */
    int8_t  hover_dz;             /* depth offset while waiting */
    uint8_t retarget;             /* frames before hover_dz changes */
    uint8_t target;               /* nearest player this frame */
    uint8_t plan_grab;            /* this approach ends in a grab */
    uint8_t moving;               /* hovering: walking to its spot (walks until there, sets off again only when far) */
    int16_t dist;                 /* |dx| + |dz| to him */
} ai_t;

static ai_t AI[MAX_F];
static uint16_t lfsr = 0xACE1;
static uint16_t tick;

static uint8_t rnd(void) {                                       /* 16-bit Galois LFSR */
    lfsr = (lfsr >> 1) ^ (-(int16_t)(lfsr & 1) & 0xB400);
    return (uint8_t)lfsr;
}
static int16_t iabs(int16_t v) { return v < 0 ? -v : v; }
static int8_t sgn(int16_t v) { return v > 0 ? 1 : v < 0 ? -1 : 0; }
static uint8_t able(const fighter_t *f) { return f->state == S_IDLE || f->state == S_WALK; }
uint8_t ai_weak;
static void rest(ai_t *a, uint8_t base) {
    a->cooldown = base + (rnd() & 127) + (ai_weak ? 100 : 0);
    a->plan_grab = !ai_weak && (rnd() & 7) < GRAB_PLAN;
}

void ai_init(uint16_t seed) {
    uint8_t i;
    lfsr = seed ? seed : 0xACE1;
    for (i = 0; i < MAX_F; i++) { AI[i].token = 0; rest(&AI[i], 30); AI[i].presses = 0; AI[i].retarget = 0; AI[i].press_t = 0; }
}

/* the closest able enemies (by this frame's distances) without a token get the tokens */
static void deal_tokens(fighter_t *fs, uint8_t nf, uint8_t np) {
    uint8_t i, k;
    for (i = np; i < nf; i++) AI[i].token = 0;
    for (k = 0; k < TOKENS; k++) {
        int16_t bd = 0x7FFF; uint8_t bi = 0xFF;
        for (i = np; i < nf; i++) {
            if (AI[i].token || !(able(&fs[i]) || fs[i].state == S_ATTACK)) continue;
            if (AI[i].dist < bd) { bd = AI[i].dist; bi = i; }
        }
        if (bi != 0xFF) AI[bi].token = 1;
    }
}

void ai_update(fighter_t *fs, uint8_t nf, uint8_t np, intent_t *in) {
    int16_t px[2], pz[2];                                    /* players in pixels, once a frame */
    uint8_t i, p;
    uint8_t alive[2];
    for (p = 0; p < np; p++) {
        px[p] = INT(fs[p].x); pz[p] = INT(fs[p].z);
        alive[p] = fs[p].state != S_DEAD && fs[p].state != S_OFF;
    }
    for (i = np; i < nf; i++) {                              /* nearest player in play and distance, once a frame */
        int16_t ex = INT(fs[i].x), ez = INT(fs[i].z), bd = 0x7FFF;
        AI[i].target = 0xFF;
        for (p = 0; p < np; p++) {
            if (!alive[p]) continue;
            int16_t d = iabs(px[p] - ex) + iabs(pz[p] - ez);
            if (d < bd) { bd = d; AI[i].target = p; }
        }
        AI[i].dist = bd;
    }
    if (!(tick++ & 15)) deal_tokens(fs, nf, np);
    for (i = np; i < nf; i++) {
        fighter_t *e = &fs[i];
        ai_t *a = &AI[i];
        intent_t *o = &in[i];
        int16_t ex, ez, tx, tz;
        if (a->target == 0xFF) { o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = 0; o->grab = 0; o->ai = 1; o->slow = 0; continue; }   /* nobody to fight */
        ex = INT(e->x); ez = INT(e->z); tx = px[a->target]; tz = pz[a->target];
        int16_t dx, dz;
        int8_t side;
        int16_t gx, gz;
        dx = tx - ex; dz = tz - ez; side = dx > 0 ? -1 : 1;  /* side: the enemy's side of the player */
        o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = sgn(dx); o->grab = 0; o->ai = 1; o->slow = 0;
        if (a->cooldown) a->cooldown--;
        if (e->state == S_GRAB) {                                /* holding: knee every 24 frames, after two maybe throw */
            if (!a->press_t || a->press_t > 24) a->press_t = 24;
            if (!--a->press_t) { o->press = e->grab_hits >= 2 && (rnd() & 1) ? IN_B : IN_A; a->press_t = 24; }
            if (o->press == IN_B || e->grab_hits >= 3) rest(a, 60);
            continue;
        }
        if (e->state == S_ATTACK) {                              /* follow-up presses of the current attack */
            if (a->presses && !--a->press_t) { o->press = IN_A; a->presses--; a->press_t = 10; }
            continue;
        }
        if (!able(e)) { a->presses = 0; continue; }
        if (!a->retarget--) { a->hover_dz = (int8_t)((rnd() & 31) - 16); a->retarget = 60 + (rnd() & 63); }
        if (a->cooldown == 0 && iabs(dz) <= RANGE_DZ + 4 && iabs(dx) >= SPEC_MIN && iabs(dx) <= SPEC_MAX &&   /* any enemy: the hoverers stand in this range */
            !ai_weak && e->ch->specials[BS_FWD_D].nrows && !rnd() && (rnd() & 1)) {   /* 1 in 512 a frame in range */
            o->dx = sgn(dx); o->press = IN_D;                    /* forward+D: the projectile special when it has one */
            rest(a, 180);
            continue;
        }
        if (a->token && a->cooldown == 0 && iabs(dz) <= RANGE_DZ && iabs(dx) <= RANGE_MAX) {
            if (a->plan_grab && iabs(dx) >= RANGE_MIN - 4) {    /* walk into him: contact grabs */
                o->dx = sgn(dx); o->grab = 1;
                continue;
            }
            if (iabs(dx) < RANGE_MIN - 4) a->plan_grab = 0;      /* too close to walk in (he is busy): punch */
            if (iabs(dx) >= RANGE_MIN) {
                if (e->facing != sgn(dx)) continue;              /* o->face turns him this frame, attack next */
                o->press = IN_A;
                a->presses = rnd() & 1;                                      /* 0-1 follow-up */
                a->press_t = 10;
                rest(a, 120);
                continue;
            }
        }
        gx = a->token ? (side > 0 ? tx + ATTACK_DX : tx - ATTACK_DX) : (side > 0 ? tx + HOVER_DX : tx - HOVER_DX);
        gz = tz + (a->token ? 0 : a->hover_dz);
        if (!a->token) {                                         /* hoverers: walk all the way, or stand (no step-stop-step) */
            if (a->moving) { if (iabs(gx - ex) <= 2 && iabs(gz - ez) <= 2) a->moving = 0; }
            else if (iabs(gx - ex) > HOVER_GO_DX || iabs(gz - ez) > HOVER_GO_DZ) a->moving = 1;
            if (!a->moving) continue;
        }
        o->slow = 1;                                             /* half speed, every frame (no on/off walk intent) */
        if (iabs(gx - ex) > (a->token ? 6 : 2)) o->dx = sgn(gx - ex);
        if (iabs(gz - ez) > (a->token ? 3 : 2)) o->dz = sgn(gz - ez);
    }
}

/* ---- attract-mode player ------------------------------------------------------------------------------------------ */
static uint8_t bot_cd, bot_follow, bot_t;
static uint8_t standing(const fighter_t *f) { return f->state != S_OFF && f->state != S_DEAD && f->state != S_DOWN &&
                                                    f->state != S_KNOCKDOWN && f->state != S_GETUP; }
void ai_bot(fighter_t *fs, uint8_t nf, uint8_t p, intent_t *o) {
    fighter_t *me = &fs[p], *t = 0;
    int16_t mx = INT(me->x), mz = INT(me->z), bd = 0x7FFF, dx, dz;
    uint8_t i;
    o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = 0; o->grab = 0; o->ai = 1; o->slow = 0;
    if (bot_cd) bot_cd--;
    bot_t++;
    if (me->state == S_GRAB) {                                   /* knee, knee, throw */
        if (!(bot_t & 15)) o->press = me->grab_hits >= 2 ? IN_B : IN_A;
        return;
    }
    if (me->state == S_ATTACK) {                                 /* follow-up presses: the combo route */
        if (bot_follow && !(bot_t & 7)) { o->press = IN_A; bot_follow--; }
        return;
    }
    if (me->state != S_IDLE && me->state != S_WALK) return;
    for (i = 2; i < nf; i++) {
        fighter_t *e = &fs[i];
        int16_t d;
        if (!standing(e)) continue;
        d = iabs(INT(e->x) - mx) + iabs(INT(e->z) - mz);
        if (e->state == S_ATTACK && d < 56 && !bot_cd && (rnd() & 1)) {   /* threatened: invincible special */
            o->press = IN_D; bot_cd = 40; return;
        }
        if (d < bd) { bd = d; t = e; }
    }
    if (!t) { o->dx = 1; return; }                              /* nobody standing: advance */
    dx = INT(t->x) - mx; dz = INT(t->z) - mz;
    o->face = sgn(dx);
    if (iabs(dz) > 3) o->dz = sgn(dz);
    if (iabs(dx) > 44 || (iabs(dz) <= 3 && iabs(dx) > 26 && (rnd() & 7) == 0)) o->dx = sgn(dx);   /* close in; sometimes walk in: grab */
    else if (iabs(dx) < 14) o->dx = -sgn(dx);
    else if (iabs(dz) <= 6 && !bot_cd && me->facing == sgn(dx)) {
        o->press = IN_A; bot_follow = 2; bot_cd = 24;
    }
}
