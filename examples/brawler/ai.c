/* Enemy AI, Final Fight style.
 * Every enemy picks the nearest player and keeps to its own side of him. Two attack tokens: every 16 frames they go to
 * the able enemy closest to its player (one token); the holder closes in to attack_dx on the player's depth line and, in
 * range and facing him, presses A one to three times (the combo chains only if the hits land), then waits a random
 * cooldown (120-247 frames); 1 approach in 8 instead walks into him to grab (a hit every 24 frames, after two maybe a throw);
 * in mid range near his depth line any enemy sometimes fires its A+B special (the projectile), so the
 * hoverers shoot; with jump_in the token holder may jump in from jump_min-jump_max (air B or air C+D). The others hover around hover_dx at a random depth offset, so the crowd surrounds instead of stacking. */
#include "ai.h"
#include "game_tables.h"

/* the numbers are an AI row's (gamedata.h ai_preset_t, game.json "ai" and the enemies' "ai_over"): the presets minion,
 * minion_attract (the demo's: rests longer, no grabs, no specials), boss, then one row per enemy with overrides. Each
 * enemy slot reads its own row (ai_t.p, set at its spawn). ai_presets[] lives in RAM (copied from the ROM table at
 * boot): a lab may poke it; ai_tab points at it or at an installed pack's rows (main.c gd_apply) */
#define MAX_F      8
ai_preset_t ai_presets[AI_COUNT];
const ai_preset_t *ai_tab = ai_presets;

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
    const ai_preset_t *p;         /* its preset (ai_init, ai_set) */
    uint8_t jumping;              /* a jump-in under way (C held through the prejump, air B when close) */
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
static void rest(ai_t *a, uint8_t base) {
    const ai_preset_t *p = a->p;
    a->cooldown = (base >> p->rest_shift) + (rnd() & p->rest_random) + p->rest_add;
    a->plan_grab = (p->flags & AIF_GRAB) && (rnd() & 7) < p->grab_plan;
}

void ai_init(uint16_t seed, uint8_t preset) {
    uint8_t i;
    lfsr = seed ? seed : 0xACE1;
    tick = 0;                                     /* the token deal's phase: not carried over from the attract demo */
    for (i = 0; i < MAX_F; i++) { AI[i].p = &ai_tab[preset]; AI[i].jumping = 0; AI[i].token = 0; rest(&AI[i], AI[i].p->rest_start); AI[i].presses = 0; AI[i].retarget = 0; AI[i].press_t = 0; }
}

void ai_set(uint8_t i, uint8_t preset) { AI[i].p = &ai_tab[preset]; rest(&AI[i], AI[i].p->rest_start); }

/* the closest able enemies (by this frame's distances) without a token get the tokens; a boss always has one */
static void deal_tokens(fighter_t *fs, uint8_t nf, uint8_t np) {
    uint8_t i, k;
    for (i = np; i < nf; i++) AI[i].token = AI[i].p->flags & AIF_TOKEN ? 1 : 0;
    for (k = 0; k < AI_TOKENS; k++) {
        int16_t bd = 0x7FFF; uint8_t bi = 0xFF;
        for (i = np; i < nf; i++) {
            if (AI[i].token || (AI[i].p->flags & AIF_TOKEN) || !(able(&fs[i]) || fs[i].state == S_ATTACK)) continue;
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
        const ai_preset_t *P = a->p;
        int16_t ex, ez, tx, tz;
        if (a->target == 0xFF) { o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = 0; o->grab = 0; o->ai = 1; o->slow = 0; o->hold = 0; continue; }   /* nobody to fight */
        ex = INT(e->x); ez = INT(e->z); tx = px[a->target]; tz = pz[a->target];
        int16_t dx, dz;
        int8_t side;
        int16_t gx, gz;
        dx = tx - ex; dz = tz - ez; side = dx > 0 ? -1 : 1;  /* side: the enemy's side of the player */
        o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = sgn(dx); o->grab = 0; o->ai = 1; o->slow = 0; o->hold = 0;
        if (a->cooldown) a->cooldown--;
        if (e->state == S_GRAB) {                                /* holding: a hit every 24 frames, after two maybe a throw */
            if (!a->press_t || a->press_t > P->hold_gap) a->press_t = P->hold_gap;
            if (!--a->press_t) {
                o->press = IN_A; a->press_t = P->hold_gap;
                if (e->grab_hits >= 2 && (rnd() & 1)) { o->dx = e->facing; rest(a, P->rest_throw); }   /* forward+A: a throw */
                else if (e->grab_hits >= 2) rest(a, P->rest_throw);         /* the third hit: C+D, the hold ends */
            }
            continue;
        }
        if (e->state == S_ATTACK) {                              /* follow-up presses of the current attack */
            if (a->presses && !--a->press_t) { o->press = IN_A; a->presses--; a->press_t = P->press_gap; }
            continue;
        }
        if (a->jumping) {                                        /* jump-in: hold B to the take-off (the full jump), */
            if (e->state == S_PREJUMP) { o->hold = IN_B; continue; }   /* down+A (air B; air_cd: up+A, the air C+D) once close on the way down */
            if (e->state == S_AIR) { if (e->vy < 0 && iabs(dx) <= P->air_b_dx) { o->press = IN_A; o->dz = (P->flags & AIF_AIR_CD) ? -1 : 1; a->jumping = 0; } continue; }
            a->jumping = 0;
        }
        if (!able(e)) { a->presses = 0; continue; }
        if ((P->flags & AIF_BOSS_MOVES) && a->cooldown == 0) {                       /* boss: reversal, specials */
            fighter_t *t = &fs[a->target];
            if ((P->flags & AIF_REVERSAL) && (t->state == S_ATTACK || t->state == S_AIR_ATTACK) && iabs(dx) < P->rev_dx && iabs(dz) <= P->rev_dz &&
                spec_ix(e->ch, BS_DOWN_D) != 0xFF && (rnd() & P->rev_mask) == 0) {
                o->press = IN_SP; o->dz = 1; rest(a, P->rest_rev); continue;   /* down + A+B: the rising reversal */
            }
            if ((P->flags & AIF_SPECIALS) && iabs(dz) <= P->bspec_dz && iabs(dx) >= P->bspec_min && iabs(dx) <= P->bspec_max && (rnd() & P->bspec_mask) == 0) {
                if (e->facing != sgn(dx)) continue;              /* o->face turns him, the special next frame */
                o->press = IN_SP; if (iabs(dx) < P->rush_dx && (rnd() & 1)) o->dx = sgn(dx);   /* A+B, or forward + A+B: the rush */
                rest(a, P->rest_bspec); continue;
            }
        }
        if ((P->flags & AIF_JUMP_IN) && a->cooldown == 0 && (a->token || (P->flags & AIF_TOKEN)) &&   /* any enemy: the jump-in, */
            iabs(dz) <= P->jump_dz && iabs(dx) >= P->jump_min && iabs(dx) <= P->jump_max && rnd() < P->jump_chance && e->facing == sgn(dx)) {
            o->press = IN_B; o->hold = IN_B; o->dx = sgn(dx); a->jumping = 1; rest(a, P->rest_jump); continue;   /* an attack: the token's */
        }
        if ((P->flags & AIF_JUMP_IN) && P->hop_chance && a->cooldown && (a->token || (P->flags & AIF_TOKEN)) &&   /* resting close: */
            iabs(dx) < P->hop_dx && iabs(dz) <= P->jump_dz && e->facing == sgn(dx) && rnd() < P->hop_chance) {
            o->press = IN_B; o->dx = -sgn(dx); continue;         /* B let go at once, pressed away: a back-hop (then the jump-in range) */
        }
        if (!a->retarget--) { a->hover_dz = (int8_t)((rnd() & 31) - 16); a->retarget = 60 + (rnd() & 63); }
        if (a->cooldown == 0 && iabs(dz) <= P->spec_dz && iabs(dx) >= P->spec_min && iabs(dx) <= P->spec_max &&   /* any enemy: the hoverers stand in this range */
            (P->flags & AIF_PROJECTILE) && spec_ix(e->ch, BS_D) != 0xFF && !(rnd() & P->proj_mask) &&
            (rnd() & P->proj_mask2) == P->proj_mask2) {         /* 1 in (proj_mask + 1) (proj_mask2 + 1) a frame in range */
            o->press = IN_SP;                                    /* A+B: the projectile (o->face turns it to the player) */
            rest(a, P->rest_special);
            continue;
        }
        if (a->token && a->cooldown == 0 && iabs(dz) <= P->range_dz && iabs(dx) <= P->range_max) {
            if (a->plan_grab && iabs(dx) >= P->range_min - 4) {    /* walk into him: contact grabs */
                o->dx = sgn(dx); o->grab = 1;
                continue;
            }
            if (iabs(dx) < P->range_min - 4) a->plan_grab = 0;      /* too close to walk in (he is busy): punch */
            if (iabs(dx) >= P->range_min) {
                if (e->facing != sgn(dx)) continue;              /* o->face turns him this frame, attack next */
                o->press = IN_A;
                a->presses = rnd() & P->follow_mask;                                      /* 0-1 follow-up */
                a->press_t = P->press_gap;
                rest(a, P->rest_attack);
                continue;
            }
        }
        gx = a->token ? (side > 0 ? tx + P->attack_dx : tx - P->attack_dx) : (side > 0 ? tx + P->hover_dx : tx - P->hover_dx);
        gz = tz + (a->token ? 0 : a->hover_dz);
        if (!a->token) {                                         /* hoverers: walk all the way, or stand (no step-stop-step) */
            if (a->moving) { if (iabs(gx - ex) <= 2 && iabs(gz - ez) <= 2) a->moving = 0; }
            else if (iabs(gx - ex) > P->hover_go_dx || iabs(gz - ez) > P->hover_go_dz) a->moving = 1;
            if (!a->moving) continue;
        }
        o->slow = !(P->flags & AIF_FULL_SPEED);                  /* half speed, every frame (no on/off walk intent) */
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
    o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = 0; o->grab = 0; o->ai = 1; o->slow = 0; o->hold = 0;
    if (bot_cd) bot_cd--;
    bot_t++;
    if (me->state == S_GRAB) {                                   /* down+C, close D, then a throw (forward+A) */
        if (!(bot_t & 15)) { o->press = IN_A; if (me->grab_hits >= 2) o->dx = me->facing; }
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
            o->press = IN_SP; o->dz = 1; bot_cd = 40; return;    /* down + A+B: the rising reversal */
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
