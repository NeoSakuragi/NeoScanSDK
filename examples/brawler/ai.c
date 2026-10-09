/* Enemy AI, Final Fight / Captain Commando style, with the revamp's enemy rules (phase 1B, docs/brawler_feel.md 8h,
 * docs/brawler_data_model.md "Enemy rules"; the numbers: game.json ai.rules -> gamedata.h gairules_t gai).
 * Every enemy picks the nearest player. Its mode:
 *  FREE      no attack token: it stands at a formation slot around its player (8 slots, 4 a side, two rings; the slots
 *            are dealt every 16 frames, the closest enemy first), resting its cooldown; a FREE enemy with `projectile`
 *            in mid range may take a token there and then and shoot (READY first).
 *  APPROACH  it holds an attack token (at most gai.attackers enemies hold one; a `token` enemy, the boss, has one kept
 *            free for it): it closes in to attack_dx on the player's depth line (tokens are dealt every 16 frames to the
 *            closest rested enemies); in range it goes READY for its punch string (or, 1 approach in 8, a walk-in grab),
 *            a jump-in (jump_in), a boss special; after approach_max frames without getting there it gives the token back.
 *  READY     the random wait before the attack (gai.wait: Final Fight's table, 1-60 frames, mean 31, shorter with the
 *            rank) in a readable pose: a held stance frame of its own (ai_ready: close C's first frame by default, as
 *            frame_ovr), or a white tint pulse when it has none. The player leaving the range sends it back to APPROACH.
 *  ACT       the attack: the presses (A plus 0-follow_mask follow-ups at press_gap, C, B for a jump-in) and what they
 *            start; the token goes back when it ends (able again), when the enemy is hit, knocked down, grabbed or thrown.
 * Wind-up: the frame an enemy's attack starts (S_ATTACK / S_SPECIAL, state_t 0) its first frame is held (fighter_t.freeze,
 * the hit-stop's hold: nothing moves, nothing animates) so that the time to its first live frame follows its damage:
 * a normal of route damage < heavy_from light_lo-light_hi frames, heavier heavy_lo-heavy_hi (minus its own startup, read
 * from its animation's steps at its speed); a special its own startup plus spec_lo-spec_hi. Jump-ins (the prejump and the
 * flight are their wind-up) and walk-in grabs are not held.
 * Rank (ai_rank 0-31, hidden): rank_start at a new game; + 1 every rank_every frames of fighting without a hit taken,
 * + rank_fast for a wave cleared in under fast_clear frames, + rank_clean for one cleared untouched; - rank_death when a
 * player loses a life. It shortens the ready wait and the rests (x (1 - rank * k / 1024)) and adds rank / rank_dmg damage
 * to the enemies spawned (main.c enemy_init). */
#include "ai.h"
#include "game_tables.h"
#include <neo_palette.h>

/* the numbers are an AI row's (gamedata.h ai_preset_t, game.json "ai" and the enemies' "ai_over"): the presets minion,
 * minion_attract (the demo's: rests longer, no grabs, no specials), boss, then one row per enemy with overrides. Each
 * enemy slot reads its own row (ai_t.p, set at its spawn). ai_presets[] lives in RAM (copied from the ROM table at
 * boot): a lab may poke it; ai_tab points at it or at an installed pack's rows (main.c gd_apply) */
#define MAX_F      8
ai_preset_t ai_presets[AI_COUNT];
const ai_preset_t *ai_tab = ai_presets;
uint8_t ai_rank, ai_tokens;

enum { AM_FREE, AM_APPROACH, AM_READY, AM_ACT };                  /* ai_t.mode: no token; the three with one */
enum { K_PUNCH, K_GRAB, K_PROJ, K_JUMP, K_BSPEC, K_REV };         /* ai_t.kind: the attack it is making */
typedef struct {
    uint8_t mode, kind;           /* (first: the proofs read them) */
    uint8_t cooldown;             /* frames before it may take a token again */
    uint8_t presses, press_t;     /* A presses left in the current attack, frames to the next one */
    uint8_t slot;                 /* FREE: its formation slot (0-7) */
    uint8_t target;               /* nearest player this frame */
    uint8_t plan_grab;            /* this approach ends in a grab */
    uint8_t moving;               /* FREE: walking to its slot (walks until there, sets off again only when far) */
    uint8_t jumping;              /* a jump-in under way (B held through the prejump, air B when close) */
    uint8_t wait;                 /* READY: frames left */
    uint8_t tm;                   /* APPROACH: frames so far; ACT grab: frames walking in (0xFF: it held him) */
    uint8_t wound;                /* the wind-up hold was given to this attack's start */
    uint8_t posed, pulse_t;       /* READY: its stance frame is shown (frame_ovr = pose); the tint pulse's clock */
    uint16_t pose;                /* READY: the stance frame (0xFFFF: none, the tint pulse) */
    int16_t dist;                 /* |dx| + |dz| to him */
    const ai_preset_t *p;         /* its preset (ai_init, ai_set) */
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
static uint8_t hurt(const fighter_t *f) {                       /* hit, down, held, thrown, beaten: its attack is over */
    return f->state == S_HITSTUN || f->state == S_KNOCKDOWN || f->state == S_DOWN || f->state == S_GETUP ||
           f->state == S_GRABBED || f->state == S_THROWN || f->state == S_DEAD;
}
/* aggression by rank: v x (1 - rank * k / 1024), k = gai.rank_wait / rank_rest (16: rank 31 = x 0.52) */
static uint8_t by_rank(uint8_t v, uint8_t k) {
    uint16_t m = (uint16_t)ai_rank * k;
    return v - (uint8_t)(((uint32_t)(uint16_t)v * m) >> 10);
}
static uint8_t span(uint8_t lo, uint8_t hi) { return lo + (uint8_t)(((uint16_t)rnd() * (uint8_t)(hi - lo + 1)) >> 8); }
static void rest(ai_t *a, uint8_t base) {
    const ai_preset_t *p = a->p;
    a->cooldown = by_rank((base >> p->rest_shift) + (rnd() & p->rest_random) + p->rest_add, gai.rank_rest);
    a->plan_grab = (p->flags & AIF_GRAB) && (rnd() & 7) < p->grab_plan;
}
static void unpose(fighter_t *e, ai_t *a) {                     /* its stance frame off (unless something took frame_ovr) */
    if (a->posed && e->frame_ovr == a->pose) e->frame_ovr = 0xFFFF;
    a->posed = 0;
}
static void release(fighter_t *e, ai_t *a) {                    /* the token back */
    unpose(e, a);
    a->mode = AM_FREE; a->presses = 0; a->jumping = 0; a->moving = 1;
}

/* ---- the hidden difficulty rank ----------------------------------------------------------------------------------- */
static int16_t rk_hp[2];
static uint8_t rk_st[2], rk_primed, rk_alive, rk_hit;
static uint16_t rk_clean, rk_wave;
static void rank_add(int8_t d) {
    int16_t r = (int16_t)ai_rank + d;
    ai_rank = r < 0 ? 0 : r > gai.rank_max ? gai.rank_max : (uint8_t)r;
}
void ai_rank_reset(void) { ai_rank = gai.rank_start; rk_primed = 0; rk_alive = 0; rk_hit = 0; rk_clean = 0; rk_wave = 0; }
uint8_t ai_rank_power(void) {
    uint8_t r = ai_rank, n = 0;
    if (!gai.rank_dmg) return 0;
    while (r >= gai.rank_dmg) { r -= gai.rank_dmg; n++; }
    return n;
}
static void rank_tick(const fighter_t *fs, uint8_t nf, uint8_t np) {
    uint8_t p, i, n = 0;
    for (i = np; i < nf; i++) if (fs[i].state != S_OFF && fs[i].state != S_DEAD) n++;
    for (p = 0; p < np && p < 2; p++) {
        if (rk_primed && fs[p].state != S_OFF) {
            if (fs[p].hp < rk_hp[p]) { rk_clean = 0; rk_hit = 1; }             /* a hit taken */
            if (fs[p].state == S_DEAD && rk_st[p] != S_DEAD) rank_add(-(int8_t)gai.rank_death);   /* a life lost */
        }
        rk_hp[p] = fs[p].hp; rk_st[p] = fs[p].state;
    }
    rk_primed = 1;
    if (n) {                                                     /* fighting: the clean clock, the wave's */
        if (rk_wave < 0xFFFF) rk_wave++;
        if (++rk_clean >= gai.rank_every) { rk_clean = 0; rank_add(1); }
    } else if (rk_alive) {                                       /* the last enemy gone: a wave cleared */
        if (rk_wave < gai.fast_clear) rank_add(gai.rank_fast);
        if (!rk_hit) rank_add(gai.rank_clean);
        rk_wave = 0; rk_hit = 0;
    }
    rk_alive = n;
}

#if LAB_BUILD
uint8_t ai_skip;
#endif
void ai_init(uint16_t seed, uint8_t preset) {
    uint8_t i;
    lfsr = seed ? seed : 0xACE1;
    tick = 0;                                     /* the token deal's phase: not carried over from the attract demo */
    for (i = 0; i < MAX_F; i++) {
        ai_t *a = &AI[i];
        a->p = &ai_tab[preset]; a->mode = AM_FREE; a->jumping = 0; a->posed = 0; a->wound = 0; rest(a, a->p->rest_start);
        a->presses = 0; a->press_t = 0; a->moving = 0; a->slot = i & 7; a->tm = 0;
    }
}

void ai_set(uint8_t i, uint8_t preset) {
    ai_t *a = &AI[i];
    a->p = &ai_tab[preset]; a->mode = AM_FREE; a->jumping = 0; a->posed = 0; a->wound = 0; a->presses = 0;
    rest(a, a->p->rest_start);
}

/* ---- tokens and formation ------------------------------------------------------------------------------------------- */
static uint8_t held(const fighter_t *fs, uint8_t nf, uint8_t np) {
    uint8_t i, n = 0;
    for (i = np; i < nf; i++) if (AI[i].mode != AM_FREE && fs[i].state != S_OFF) n++;
    return n;
}
/* may enemy i take a token now: fewer than gai.attackers held; a minion leaves one free for each `token` enemy (the boss)
 * standing without one */
static uint8_t may_take(const fighter_t *fs, uint8_t nf, uint8_t np, uint8_t i) {
    uint8_t k, n = held(fs, nf, np), resv = 0;
    if (AI[i].p->flags & AIF_TOKEN) return n < gai.attackers;
    for (k = np; k < nf; k++)
        if ((AI[k].p->flags & AIF_TOKEN) && AI[k].mode == AM_FREE && fs[k].state != S_OFF && fs[k].state != S_DEAD) resv++;
    return n + resv < gai.attackers;
}
/* the formation (Final Fight's waiting spots, Captain Commando's slots): 4 a side of the player, near ring at hover_dx
 * above and below his depth line, far ring 36 px further out */
static const int8_t SLOT_DX[4] = { 0, 0, 36, 36 };
static const int8_t SLOT_DZ[4] = { -12, 12, -24, 24 };
static void slot_goal(const ai_preset_t *P, uint8_t s, int16_t tx, int16_t tz, int16_t *gx, int16_t *gz) {
    int16_t d = P->hover_dx + SLOT_DX[s & 3];
    *gx = s & 4 ? tx + d : tx - d;
    *gz = tz + SLOT_DZ[s & 3];
    if (*gz < z_back(*gx)) *gz = z_back(*gx);                   /* (not behind the floor's back edge, game.json depth) */
    if (*gz > Z_DEPTH) *gz = Z_DEPTH;
}
/* every 16 frames: the rested FREE minions closest to their player take the tokens left; then each player's FREE
 * enemies, the closest first, take the free slot nearest to them */
static void deal(fighter_t *fs, uint8_t nf, uint8_t np, const int16_t *px, const int16_t *pz) {
    uint8_t i, p, taken;
    for (;;) {
        int16_t bd = 0x7FFF; uint8_t bi = 0xFF;
        for (i = np; i < nf; i++) {
            const ai_t *a = &AI[i];
            if (a->mode != AM_FREE || a->cooldown || a->target == 0xFF || (a->p->flags & AIF_TOKEN) || !able(&fs[i])) continue;
            if (a->dist < bd) { bd = a->dist; bi = i; }
        }
        if (bi == 0xFF || !may_take(fs, nf, np, bi)) break;
        AI[bi].mode = AM_APPROACH; AI[bi].tm = 0;
    }
    for (p = 0; p < np; p++) {
        taken = 0;
        for (;;) {
            int16_t bd = 0x7FFF; uint8_t bi = 0xFF;
            for (i = np; i < nf; i++) {
                const ai_t *a = &AI[i];
                if (a->mode != AM_FREE || a->target != p || fs[i].state == S_OFF || (taken >> (i & 7) & 1)) continue;
                if (a->dist < bd) { bd = a->dist; bi = i; }
            }
            if (bi == 0xFF) break;
            taken |= 1 << (bi & 7);
            {   uint8_t used = 0, best = 0, s; int16_t sd = 0x7FFF, ex = INT(fs[bi].x), ez = INT(fs[bi].z);
                for (i = np; i < nf; i++) if (i != bi && AI[i].mode == AM_FREE && AI[i].target == p && (taken >> (i & 7) & 1)) used |= 1 << AI[i].slot;
                for (s = 0; s < 8; s++) {
                    int16_t gx, gz, d;
                    if (used >> s & 1) continue;
                    slot_goal(AI[bi].p, s, px[p], pz[p], &gx, &gz);
                    d = iabs(gx - ex) + iabs(gz - ez);
                    if (d < sd) { sd = d; best = s; }
                }
                if (AI[bi].slot != best) { AI[bi].slot = best; AI[bi].moving = 1; }
            }
        }
    }
}

/* ---- the ready pose and the wind-up --------------------------------------------------------------------------------- */
static uint16_t stance(const fighter_t *e) {                     /* its stance frame, 0xFFFF: none (the tint pulse) */
    const uint8_t *r = ai_ready[e->ch->id];
    if (r[0] == 0xFF) return 0xFFFF;                             /* game.json "tint": the pulse by choice */
    if (r[1] < e->ch->anims[r[0]].nsteps) return e->ch->anims[r[0]].steps[r[1]].frame;
    if (gai.ready_anim2 != 0xFF && gai.ready_step2 < e->ch->anims[gai.ready_anim2].nsteps)
        return e->ch->anims[gai.ready_anim2].steps[gai.ready_step2].frame;
    return 0xFFFF;
}
static void ready(fighter_t *e, ai_t *a, uint8_t kind) {
    uint8_t w = by_rank(gai.wait[rnd() & 31], gai.rank_wait);
    a->mode = AM_READY; a->kind = kind; a->wait = w ? w : 1; a->pose = stance(e); a->pulse_t = 0;
}
static const uint16_t WHITE[16] = { 0x8000, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF,
                                    0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF };
static void show_ready(fighter_t *e, ai_t *a) {
    if (a->pose != 0xFFFF) { e->frame_ovr = a->pose; a->posed = 1; return; }
    if (!a->pulse_t && !e->flash && !e->burn) {                 /* the tint pulse: white 3 frames (meter_tick restores) */
        uint8_t k;
        for (k = 0; k < e->ch->npal && k < MAX_PALS; k++) PAL_setPalette(e->palbase + k, WHITE);
        e->flash = 3;
    }
    if (++a->pulse_t >= gai.pulse) a->pulse_t = 0;
}
#define TREE(f) ((f)->tree ? (f)->tree : route_tab[(f)->ch->id])   /* (fighter.c's) */
/* the hold that brings the attack starting now to its wind-up: a normal's target by its route damage minus its own
 * startup (its animation's steps before the first live one, at the node's speed: fighter.c anim_tick's clock); a special
 * its own startup plus spec_lo-spec_hi */
uint8_t ai_wlog[16][4], ai_wlog_n;   /* the last wind-ups (a ring, ai_wlog_n counts them): enemy slot | class << 4 (0
                                       light, 1 heavy, 2 special), route damage (0: a special), own startup, hold (the proofs) */
static uint8_t windup_hold(const fighter_t *e) {
    const banim_t *an;
    uint16_t sum = 0, acc = 0, sp;
    uint8_t k, n = 0, want, cls = 2, dmg = 0, *w;
    if (e->state == S_SPECIAL) want = span(gai.spec_lo, gai.spec_hi);
    else {
        an = &e->ch->anims[e->anim];
        for (k = 0; k < an->nsteps && !(an->steps[k].flags & 1); k++) sum += an->steps[k].ticks + 1;
        if (k >= an->nsteps) return 0;                           /* nothing live: no hit to announce */
        dmg = RT_NODE(TREE(e), e->node)->damage; cls = dmg >= gai.heavy_from;
        want = cls ? span(gai.heavy_lo, gai.heavy_hi) : span(gai.light_lo, gai.light_hi);
        sp = e->speed ? e->speed : 0x100;
        sum <<= 8;
        while (acc < sum && n < 255) { acc += sp; n++; }         /* frames shown before the live step */
        want = want > n ? want - n : 0;
    }
    w = ai_wlog[ai_wlog_n++ & 15]; w[0] = e->idx | cls << 4; w[1] = dmg; w[2] = n; w[3] = want;
    return want;
}

/* in range for the attack it is ready to make (a margin past the range that made it ready) */
static uint8_t still_in_range(const ai_t *a, int16_t adx, int16_t adz) {
    const ai_preset_t *P = a->p;
    switch (a->kind) {
    case K_PUNCH: return adz <= P->range_dz + 4 && adx + 6 >= P->range_min && adx <= P->range_max + 8;
    case K_GRAB:  return adz <= P->range_dz + 4 && adx <= P->range_max + 8;
    case K_PROJ:  return adz <= P->spec_dz + 4 && adx + 8 >= P->spec_min && adx <= P->spec_max + 8;
    case K_JUMP:  return adz <= P->jump_dz + 4 && adx + 8 >= P->jump_min && adx <= P->jump_max + 8;
    default:      return adz <= P->bspec_dz + 4 && adx + 8 >= P->bspec_min && adx <= P->bspec_max + 8;
    }
}

/* ---- the update ----------------------------------------------------------------------------------------------------- */
static void walk_to(intent_t *o, const ai_t *a, int16_t gx, int16_t gz, int16_t ex, int16_t ez, uint8_t near_x, uint8_t near_z) {
    o->slow = !(a->p->flags & AIF_FULL_SPEED);                   /* half speed, every frame (no on/off walk intent) */
    if (iabs(gx - ex) > near_x) o->dx = sgn(gx - ex);
    if (iabs(gz - ez) > near_z) o->dz = sgn(gz - ez);
}
static void execute(fighter_t *e, ai_t *a, intent_t *o, int16_t dx) {   /* READY's wait is over: the attack's presses */
    const ai_preset_t *P = a->p;
    unpose(e, a);
    a->mode = AM_ACT;
    switch (a->kind) {
    case K_PUNCH:
        o->press = IN_A; a->presses = rnd() & P->follow_mask; a->press_t = P->press_gap;   /* 0-follow_mask follow-ups */
        rest(a, P->rest_attack); break;
    case K_GRAB:                                                 /* walk into him: contact grabs (fighter.c) */
        a->tm = 0; o->dx = sgn(dx); o->grab = 1; rest(a, P->rest_attack); a->plan_grab = 1; break;
    case K_PROJ:
        o->press = IN_C; rest(a, P->rest_special); break;       /* C: the projectile (o->face turns it to him) */
    case K_JUMP:                                                 /* a full forward jump: B held to the take-off */
        o->press = IN_B; o->hold = IN_B; o->dx = sgn(dx); a->jumping = 1; rest(a, P->rest_jump); break;
    default:                                                     /* the boss: C, or forward + C (the rush) */
        o->press = IN_C; if (iabs(dx) < P->rush_dx && (rnd() & 1)) o->dx = sgn(dx);
        rest(a, P->rest_bspec); break;
    }
}

void ai_update(fighter_t *fs, uint8_t nf, uint8_t np, intent_t *in) {
    int16_t px[2], pz[2];                                    /* players in pixels, once a frame */
    uint8_t i, p;
    uint8_t alive[2];
    rank_tick(fs, nf, np);
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
#if LAB_BUILD
        if (ai_skip >> i & 1) AI[i].target = 0xFF;             /* a practice dummy (ai.h): nobody to fight, its token given back */
#endif
        if (fs[i].state == S_OFF) AI[i].mode = AM_FREE;          /* gone (or taken off): no token */
    }
    if (!(tick++ & 15)) deal(fs, nf, np, px, pz);
    for (i = np; i < nf; i++) {
        fighter_t *e = &fs[i];
        ai_t *a = &AI[i];
        intent_t *o = &in[i];
        const ai_preset_t *P = a->p;
        int16_t ex, ez, tx, tz, dx, dz, adx, adz, gx, gz;
        int8_t side;
        o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = 0; o->grab = 0; o->ai = 1; o->slow = 0; o->hold = 0; o->blitz = o->chord = 0;
        if (e->state == S_OFF) continue;
        /* the wind-up: an attack starting now has its first frame held */
        if ((e->state == S_ATTACK || e->state == S_SPECIAL) && e->state_t == 0) {
            if (!a->wound && !e->freeze) { e->freeze = windup_hold(e); a->wound = 1; }
        } else a->wound = 0;
        if (a->cooldown) a->cooldown--;
        if (a->target == 0xFF) { if (a->mode != AM_FREE) release(e, a); continue; }   /* nobody to fight */
        if (hurt(e)) { if (a->mode != AM_FREE) { release(e, a); if (a->cooldown < P->rest_start) rest(a, P->rest_start); } continue; }
        ex = INT(e->x); ez = INT(e->z); tx = px[a->target]; tz = pz[a->target];
        dx = tx - ex; dz = tz - ez; adx = iabs(dx); adz = iabs(dz); side = dx > 0 ? -1 : 1;   /* side: the enemy's side of him */
        o->face = sgn(dx);
        if (e->state == S_GRAB) {                                /* holding: a hit every hold_gap frames, after two maybe a throw */
            a->tm = 0xFF;
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
            if (e->state == S_AIR) { if (e->vy < 0 && adx <= P->air_b_dx) { o->press = IN_A; o->dz = (P->flags & AIF_AIR_CD) ? -1 : 1; a->jumping = 0; } continue; }
            a->jumping = 0;
        }
        if (!able(e)) continue;                                  /* a special, a throw, a landing...: its own course */
        if (a->mode == AM_ACT) {                                 /* able again: the attack is over (a grab: still walking in) */
            if (a->kind == K_GRAB && a->tm < 45 && adx + 4 >= P->range_min) { a->tm++; o->dx = sgn(dx); o->grab = 1; continue; }
            release(e, a);
        }
        if ((P->flags & AIF_REVERSAL) && a->cooldown == 0 && (a->mode != AM_FREE || may_take(fs, nf, np, i))) {   /* boss: */
            fighter_t *t = &fs[a->target];                       /* an attack this close: down + C, the rising reversal */
            if ((t->state == S_ATTACK || t->state == S_AIR_ATTACK) && adx < P->rev_dx && adz <= P->rev_dz &&
                spec_ix(e->ch, BS_DOWN_D) != 0xFF && (rnd() & P->rev_mask) == 0) {
                unpose(e, a); o->press = IN_C; o->dz = 1; a->mode = AM_ACT; a->kind = K_REV; rest(a, P->rest_rev); continue;
            }
        }
        if (a->mode == AM_READY) {                               /* the random wait in the stance */
            if (!still_in_range(a, adx, adz)) {                  /* he went out of reach */
                unpose(e, a); a->mode = AM_APPROACH;
            } else {
                show_ready(e, a);
                if (a->wait) a->wait--;
                if (!a->wait && e->facing == sgn(dx)) execute(e, a, o, dx);   /* (o->face turns him first) */
                continue;
            }
        }
        if (a->mode == AM_FREE) {
            if ((P->flags & AIF_JUMP_IN) && P->hop_chance && a->cooldown && adx < P->hop_dx && adz <= P->jump_dz &&
                e->facing == sgn(dx) && rnd() < P->hop_chance) {   /* resting close: a back-hop (B let go at once) */
                o->press = IN_B; o->dx = -sgn(dx); continue;
            }
        }
        if (a->mode != AM_READY && (P->flags & AIF_PROJECTILE) && a->cooldown == 0 && adz <= P->spec_dz && adx >= P->spec_min &&
            adx <= P->spec_max && spec_ix(e->ch, BS_D) != 0xFF && !(rnd() & P->proj_mask) && (rnd() & P->proj_mask2) == P->proj_mask2 &&
            (a->mode != AM_FREE || may_take(fs, nf, np, i))) {   /* mid range, any enemy: the projectile, 1 in (proj_mask + 1) (proj_mask2 + 1) a frame */
            ready(e, a, K_PROJ); continue;
        }
        if (a->mode == AM_FREE) {
            if ((P->flags & AIF_TOKEN) && a->cooldown == 0 && may_take(fs, nf, np, i)) { a->mode = AM_APPROACH; a->tm = 0; }
        }
        if (a->mode == AM_APPROACH) {
            if (++a->tm > gai.approach_max) { release(e, a); rest(a, P->rest_start); continue; }   /* could not get there */
            if ((P->flags & AIF_SPECIALS) && adz <= P->bspec_dz && adx >= P->bspec_min && adx <= P->bspec_max &&
                (rnd() & P->bspec_mask) == 0) { ready(e, a, K_BSPEC); continue; }   /* boss: a special on his line */
            if ((P->flags & AIF_JUMP_IN) && adz <= P->jump_dz && adx >= P->jump_min && adx <= P->jump_max &&
                rnd() < P->jump_chance && e->facing == sgn(dx)) { ready(e, a, K_JUMP); continue; }   /* the jump-in */
            if (adz <= P->range_dz && adx <= P->range_max) {
                if (a->plan_grab && adx + 4 >= P->range_min) { ready(e, a, K_GRAB); continue; }   /* then walk into him */
                if (adx + 4 < P->range_min) a->plan_grab = 0;    /* too close to walk in (he is busy): punch */
                if (adx >= P->range_min) { if (e->facing == sgn(dx)) ready(e, a, K_PUNCH); continue; }   /* (turned first) */
            }
            gx = side > 0 ? tx + P->attack_dx : tx - P->attack_dx; gz = tz;
            walk_to(o, a, gx, gz, ex, ez, 6, 3);
            continue;
        }
        slot_goal(P, a->slot, tx, tz, &gx, &gz);                 /* FREE: to its formation slot, walk all the way or stand */
        if (a->moving) { if (iabs(gx - ex) <= 2 && iabs(gz - ez) <= 2) a->moving = 0; }
        else if (iabs(gx - ex) > P->hover_go_dx || iabs(gz - ez) > P->hover_go_dz) a->moving = 1;
        if (a->moving) walk_to(o, a, gx, gz, ex, ez, 2, 2);
    }
    ai_tokens = held(fs, nf, np);
}

/* ---- attract-mode player ------------------------------------------------------------------------------------------ */
static uint8_t bot_cd, bot_follow, bot_t;
static uint8_t standing(const fighter_t *f) { return f->state != S_OFF && f->state != S_DEAD && f->state != S_DOWN &&
                                                    f->state != S_KNOCKDOWN && f->state != S_GETUP; }
void ai_bot(fighter_t *fs, uint8_t nf, uint8_t p, intent_t *o) {
    fighter_t *me = &fs[p], *t = 0;
    int16_t mx = INT(me->x), mz = INT(me->z), bd = 0x7FFF, dx, dz;
    uint8_t i;
    o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = 0; o->grab = 0; o->ai = 1; o->slow = 0; o->hold = 0; o->blitz = o->chord = 0;
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
            o->press = IN_C; o->dz = 1; bot_cd = 40; return;    /* down + C: the rising reversal */
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
