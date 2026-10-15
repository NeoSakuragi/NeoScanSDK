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
#include "labslot.h"                                         /* (the Character Lab's shell: the slot's tables in RAM) */

/* the numbers are an AI row's (gamedata.h ai_preset_t, game.json "ai" and the enemies' "ai_over"): the presets minion,
 * minion_attract (the demo's: rests longer, no grabs, no specials), boss, then one row per enemy with overrides. Each
 * enemy slot reads its own row (ai_t.p, set at its spawn). ai_presets[] lives in RAM (copied from the ROM table at
 * boot): a lab may poke it; ai_tab points at it or at an installed pack's rows (main.c gd_apply) */
#define MAX_F      8
ai_preset_t ai_presets[AI_COUNT];
const ai_preset_t *ai_tab = ai_presets;
uint8_t ai_rank, ai_tokens;

enum { AM_FREE, AM_APPROACH, AM_READY, AM_ACT };                  /* ai_t.mode: no token; the three with one */
enum { K_PUNCH, K_GRAB, K_PROJ, K_JUMP, K_BSPEC, K_REV,          /* ai_t.kind: the attack it is making; */
       K_COMBO, K_FURY };                                          /* a boss's combo, its red period's fury (T9) */
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
    /* the boss layer (T9, "the boss layer" below): b = its data (0: none); the combo playing (cix, 0xFF none; cpos its
     * next op; cpressed: that op pressed, waiting for the move it starts; clanded: the move before it connected; cnode /
     * csix / csid / cst: what was playing at the press), the ones used this fight (cused) and the last; the guard's
     * clocks (gtm hold, grest rest), the target's attack seen (tsig, tst); gnear: its target near (the grab response
     * rolled); the red period (red, rtm the fury's rest, rcount furies), running (an approach run, 2: a combo's run op),
     * runroll (this approach's run rolled), ctm (the counter-hold's clock) */
    const gbossai_t *b;
    uint8_t cix, cpos, cpressed, clanded, cnode, csix, csid, clast, cgo;   /* cgo: the string picked (cix) has started */
    uint16_t cused, cst;
    uint8_t gtm, grest, gnear, red, rcount, running, runroll, ctm;
    uint16_t rtm;
    uint16_t tsig, tst;
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
static void combo_end(ai_t *a);
static void release(fighter_t *e, ai_t *a) {                    /* the token back */
    unpose(e, a);
    a->mode = AM_FREE; a->presses = 0; a->jumping = 0; a->moving = 1; a->running = 0; a->runroll = 0;
    if (a->b && a->cix != 0xFF && a->cgo) combo_end(a);         /* (a boss's string: over) */
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
/* (cpu budget F: the loops over fighters walk pointers; fs[i] multiplies i by sizeof(fighter_t), a 68000 mulu each) */
static void rank_tick(const fighter_t *fs, uint8_t nf, uint8_t np) {
    uint8_t p, n = 0;
    const fighter_t *f;
    for (f = fs + np; f < fs + nf; f++) if (f->state != S_OFF && f->state != S_DEAD) n++;
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
        a->b = 0;
        a->p = &ai_tab[preset]; a->mode = AM_FREE; a->jumping = 0; a->posed = 0; a->wound = 0; rest(a, a->p->rest_start);
        a->presses = 0; a->press_t = 0; a->moving = 0; a->slot = i & 7; a->tm = 0; a->target = 0xFF;
    }
}

void ai_set(uint8_t i, uint8_t preset) {
    ai_t *a = &AI[i];
    a->b = 0;
    a->p = &ai_tab[preset]; a->mode = AM_FREE; a->jumping = 0; a->posed = 0; a->wound = 0; a->presses = 0;
    a->target = 0xFF;                             /* (until its first think: nobody, ai_update) */
    rest(a, a->p->rest_start);
}

/* ---- tokens and formation ------------------------------------------------------------------------------------------- */
static uint8_t held(const fighter_t *fs, uint8_t nf, uint8_t np) {
    uint8_t n = 0;
    const fighter_t *f;
    const ai_t *a = AI + np;
    for (f = fs + np; f < fs + nf; f++, a++) if (a->mode != AM_FREE && f->state != S_OFF) n++;
    return n;
}
/* may enemy i take a token now: fewer than gai.attackers held; a minion leaves one free for each `token` enemy (the boss)
 * standing without one */
static uint8_t may_take(const fighter_t *fs, uint8_t nf, uint8_t np, uint8_t i) {
    uint8_t n = held(fs, nf, np), resv = 0;
    const fighter_t *f;
    const ai_t *a = AI + np;
    if (AI[i].p->flags & AIF_TOKEN) return n < gai.attackers;
    for (f = fs + np; f < fs + nf; f++, a++)
        if ((a->p->flags & AIF_TOKEN) && a->mode == AM_FREE && f->state != S_OFF && f->state != S_DEAD) resv++;
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
    if (a->b) w >>= a->b->ready_shift;                           /* (a boss: a shorter tell, boss_ai.ready_shift) */
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
    case K_PUNCH: case K_COMBO: return adz <= P->range_dz + 4 && adx + 6 >= P->range_min && adx <= P->range_max + 8;
    case K_GRAB:  return adz <= P->range_dz + 4 && adx <= P->range_max + 8;
    case K_PROJ:  return adz <= P->spec_dz + 4 && adx + 8 >= P->spec_min && adx <= P->spec_max + 8;
    case K_JUMP:  return adz <= P->jump_dz + 4 && adx + 8 >= P->jump_min && adx <= P->jump_max + 8;
    default:      return adz <= P->bspec_dz + 4 && adx + 8 >= P->bspec_min && adx <= P->bspec_max + 8;
    }
}

/* ---- the boss layer (T9, Bruno 2026-10-15: "the bosses more challenging than today, even at level 4") -----------------
 * A boss enemy (main.c boss_start: game.json enemies[].boss_ai -> gamedata.h gbossai_t) plays on top of its preset:
 *  GUARD     an attack of its target starting within guard_dx (on its line, facing it) is guarded guard_chance of 256
 *            times (rolled once per attack: the target's state / move / node changing): intent_t.guard held guard_hold
 *            frames at least and while the target's attack goes on, then guard_rest frames before the next. The engine
 *            blocks (fighter.c "guard": throws, furies, hits from behind and the guard's own limit gd_max beat it).
 *  RUN       an approach from farther than run_from runs in (S_RUN) run_chance of 256 times, to run_stop px; a combo may
 *            start with a run (its next press from the run: run + A = the dash attack / ff Blitz).
 *  GRAB      each time its target comes near (< 48 px; again every 64 frames it stays, and after it was hurt) a
 *            roll: grab_immune of 256 a grab on it does not take, then
 *            grab_counter of 256 it is reversed (fighter.c "grab response"): its counter-hold throws after counter_delay.
 *  COMBOS    its strings (op bytes, gamedata.h CO_* | CS_* << 3): each attack in punch range plays one, picked at random
 *            among the ones NOT used yet this fight (cused); all used, the list starts again (the last one excluded):
 *            every string is seen before one repeats. A press goes in when the move before it connected (in its hit-stop
 *            too: the engine buffers it, the chain / the cancel rule take it); a whiff or a hit taken ends the string.
 *            A string with a D is played only in the red period.
 *  RED       life <= red_low % of its full life: it blinks red (fighter_t.bred, the player's MAX-ready blink) and plays
 *            its fury (D) like a player at low life: within red_dx on its target's line, every red_rest x 4 frames, the
 *            first red_max of them as the MAX (down+D).
 * Every event goes to ai_blog (the proofs: the order of the combos, the guards, the reversals, the furies). */
ai_bev_t ai_blog[32];
uint8_t ai_blog_n;
static void blog(uint8_t kind, uint8_t a, uint8_t b, uint8_t c) {
    ai_bev_t *v = &ai_blog[ai_blog_n++ & 31];
    v->kind = kind; v->a = a; v->b = b; v->c = c; v->t = tick;
}
void ai_boss(uint8_t i, const gbossai_t *b) {
    ai_t *a = &AI[i];
    a->b = b; a->cix = 0xFF; a->cpos = 0; a->cpressed = 0; a->clanded = 0; a->cused = 0; a->clast = 0xFF; a->cgo = 0;
    a->gtm = a->grest = a->gnear = a->red = a->rtm = a->rcount = a->running = a->runroll = a->ctm = 0; a->tsig = 0; a->tst = 0;
}
static uint8_t has_d(const uint8_t *c) {                         /* a string with a D: the red period's */
    uint8_t k;
    for (k = 0; k < BC_OPS && c[k]; k++) if ((c[k] & 7) == CO_D) return 1;
    return 0;
}
static uint8_t combo_pick(ai_t *a) {                             /* the next string: one not used yet, at random */
    const gbossai_t *B = a->b;
    uint16_t ok = 0, free_;
    uint8_t k, n = 0, r;
    for (k = 0; k < B->ncombo; k++) if (a->red || !has_d(B->combo[k])) ok |= 1 << k;
    if (!ok) return 0xFF;
    free_ = ok & ~a->cused;
    if (!free_) {                                                /* all seen: again (the last one not first) */
        a->cused = a->clast < 16 ? 1 << a->clast : 0; free_ = ok & ~a->cused;
        if (!free_) { a->cused = 0; free_ = ok; }
    }
    for (k = 0; k < B->ncombo; k++) n += (free_ >> k) & 1;
    r = (uint8_t)(((uint16_t)rnd() * n) >> 8);
    for (k = 0; k < B->ncombo; k++) if ((free_ >> k) & 1) { if (!r) break; r--; }
    return k;                                                    /* (marked used when it starts: combo_go) */
}
static void combo_go(ai_t *a) {                                  /* the string picked starts: used, logged */
    a->cused |= 1 << a->cix; a->clast = a->cix; a->cgo = 1; a->cpos = 0; a->cpressed = 0; a->clanded = 0;
    blog(BE_COMBO, a->cix, (uint8_t)a->cused, (uint8_t)(a->cused >> 8));
}
static uint8_t combo_op(const ai_t *a) { return a->cix < BC_MAX && a->cpos < BC_OPS ? a->b->combo[a->cix][a->cpos] : CO_END; }
static void combo_end(ai_t *a) {
    if (a->cix != 0xFF && a->cgo) blog(BE_CEND, a->cix, a->cpos, a->clanded);
    a->cix = 0xFF; a->cpos = 0; a->cpressed = 0; a->clanded = 0; a->cgo = 0;
}
static void combo_next(ai_t *a) { a->cpos++; a->cpressed = 0; a->clanded = 0; }
/* an op's press: its button and its stick (forward = toward him) -> 0 when it may not play now (a D outside the red) */
static uint8_t op_press(fighter_t *e, ai_t *a, intent_t *o, uint8_t op, int16_t dx) {
    static const int8_t SX[7] = { 0, 1, -1, 0, 0, 1, 1 }, SZ[7] = { 0, 0, 0, -1, 1, 1, -1 };
    uint8_t k = op & 7, st = (op >> 3) & 7;
    if (k == CO_D && !a->red) return 0;
    o->press = k == CO_A ? IN_A : k == CO_C ? IN_C : IN_D;
    o->dx = SX[st] * sgn(dx); o->dz = SZ[st];
    a->cpressed = 1; a->cnode = e->state == S_ATTACK || e->state == S_AIR_ATTACK ? e->node : 0xFF;
    a->csix = e->spec_ix; a->csid = e->state == S_SPECIAL ? e->spec_id : 0xFF; a->cst = e->state_t;
    return 1;
}
static uint8_t attacking(const fighter_t *t) {
    return t->state == S_ATTACK || t->state == S_AIR_ATTACK || (t->state == S_SPECIAL && t->spec_id != BS_FURY);
}
static void boss_clocks(fighter_t *e, ai_t *a) {                 /* every tick: its rests, its guard's limit, the red period */
    const gbossai_t *B = a->b;
    uint16_t full = e->hp_max ? e->hp_max : 60, l, m;
    if (a->grest) a->grest--;
    if (a->rtm) a->rtm--;
    e->gd_max = B->guard_max;
    if (e->hp <= 0) { e->bred = 0; return; }
    l = (uint16_t)e->hp * (uint16_t)100; m = full * (uint16_t)B->red_low;   /* (16-bit products: no __mulsi3) */
    if (!a->red && B->red_low && l <= m) {
        a->red = 1; e->bred = 1; a->rtm = 0; blog(BE_RED, e->hp > 255 ? 255 : (uint8_t)e->hp, 0, 0);
    }
}
/* in one of its string's moves (an attack, an air attack, a special): the next press once this one connected */
static void combo_move(fighter_t *e, ai_t *a, intent_t *o, int16_t dx) {
    uint8_t op = combo_op(a), k = op & 7;
    if (a->cpressed) {                                           /* pressed: taken when another move started */
        if (e->state == S_SPECIAL ? e->spec_id != a->csid || e->spec_ix != a->csix || e->state_t < a->cst
                                  : e->node != a->cnode || e->state_t < a->cst) combo_next(a);
        return;
    }
    if (!k || k > CO_D || e->state == S_AIR_ATTACK || !e->landed) return;   /* (a grab: once it stands; an air move: its
                                                                    landing) */
    if (e->state == S_SPECIAL && (k == CO_A || !e->scancel)) return;   /* a special: only its cancels (C / D on contact) */
    if (!op_press(e, a, o, op, dx)) a->cpos = BC_OPS;            /* (a D outside the red period: the string ends here) */
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
    case K_COMBO: {                                              /* a boss's string (the boss layer): its first press */
        uint8_t op;
        combo_go(a); rest(a, P->rest_attack); a->tm = 0;
        op = combo_op(a);
        if ((op & 7) == CO_RUN) {                                /* (a run from this close: straight to its next press) */
            if (iabs(dx) >= a->b->run_stop + 8) { o->run = 1; o->dx = sgn(dx); a->running = 2; break; }
            combo_next(a); op = combo_op(a);
        }
        if ((op & 7) == CO_JUMP) { o->press = IN_B; o->hold = IN_B; o->dx = sgn(dx); a->jumping = 1; combo_next(a); break; }
        if ((op & 7) == CO_GRAB) { o->dx = sgn(dx); o->grab = 1; break; }
        if (!op_press(e, a, o, op, dx)) a->cpos = BC_OPS;
        break;
    }
    default:                                                     /* the boss: C, or forward + C (the rush) */
        o->press = IN_C; if (iabs(dx) < P->rush_dx && (rnd() & 1)) o->dx = sgn(dx);
        rest(a, P->rest_bspec); break;
    }
}

/* THE THINK SPLIT (cpu budget F, docs/brawler_cpu_budget.md; Bruno 2026-10-14: "AI reacts one frame later" accepted):
 * a minion THINKS (its target, then the decisions: ready, approach, formation, the chances of a jump-in / projectile /
 * hop) every other tick, slot parity against the AI's tick (slots 2 4 6 on even ticks, 3 5 7 on odd: half the crowd
 * each tick, deterministic); a boss (AIF_TOKEN) every tick. Every tick, everyone: the wind-up, the cooldown, the
 * reactions to being hurt, and what an attack under way needs on its own frames (a hold's hits, a combo's follow-up
 * presses, a jump-in's B / air attack). A tick it does not think, an able minion keeps its last intent's walk (dx, dz,
 * face, slow, grab: its presses are not repeated) and its decision clocks run (READY's wait to 1, APPROACH's and a grab
 * walk's tm, the tint pulse), so its waits keep their length; its per-tick chances are doubled for the ticks it skips
 * (a threshold x 2, a 2^k - 1 mask halved). */
static void off_clocks(ai_t *a) {                                /* a tick it does not think: its decision clocks */
    if (a->mode == AM_READY) {
        if (a->wait > 1) a->wait--;                              /* (its think tick takes the last one: execute) */
        if (a->pulse_t + 1 < gai.pulse) a->pulse_t++;            /* (show_ready wraps it) */
    } else if ((a->mode == AM_APPROACH || a->mode == AM_ACT) && a->tm < 0xFE) a->tm++;   /* (0xFF: a hold's mark) */
}
static uint8_t twice(uint8_t c, uint8_t on) { return !on ? c : c > 127 ? 255 : c << 1; }   /* a chance rnd() < c */
static uint8_t halve(uint8_t m, uint8_t on) { return on ? m >> 1 : m; }                    /* a chance !(rnd() & m) */
void ai_update(fighter_t *fs, uint8_t nf, uint8_t np, intent_t *in) {
    int16_t px[2], pz[2];                                    /* players in pixels, once a frame */
    uint8_t i, p, t = tick;
    uint8_t alive[2];
    rank_tick(fs, nf, np);
    for (p = 0; p < np; p++) {
        px[p] = INT(fs[p].x); pz[p] = INT(fs[p].z);
        alive[p] = fs[p].state != S_DEAD && fs[p].state != S_OFF;
    }
    for (i = np; i < nf; i++) {                              /* nearest player in play and distance, on its think ticks */
        const fighter_t *f = fs + i;
        ai_t *a = AI + i;
        int16_t ex, ez, bd = 0x7FFF;
        if (f->state == S_OFF) { a->mode = AM_FREE; a->target = 0xFF; continue; }   /* gone (or taken off): no token */
        if (((i ^ t) & 1) && !(a->p->flags & AIF_TOKEN)) continue;   /* (not its tick: last one's) */
        ex = INT(f->x); ez = INT(f->z);
        a->target = 0xFF;
        for (p = 0; p < np; p++) {
            if (!alive[p]) continue;
            int16_t d = iabs(px[p] - ex) + iabs(pz[p] - ez);
            if (d < bd) { bd = d; a->target = p; }
        }
        a->dist = bd;
#if LAB_BUILD
        if (ai_skip >> i & 1) a->target = 0xFF;                /* a practice dummy (ai.h): nobody to fight, its token given back */
#endif
    }
    if (!(tick++ & 15)) deal(fs, nf, np, px, pz);
    {
    fighter_t *e = fs + np;
    ai_t *a = AI + np;
    intent_t *o = in + np;
    for (i = np; i < nf; i++, e++, a++, o++) {
        const ai_preset_t *P = a->p;
        int16_t ex, ez, tx, tz, dx, dz, adx, adz, gx, gz;
        int8_t side, kdx = o->dx, kdz = o->dz, kface = o->face;
        uint8_t kslow = o->slow, kgrab = o->grab, skip = ((i ^ t) & 1) && !(P->flags & AIF_TOKEN), dbl = !(P->flags & AIF_TOKEN);
        if (skip && able(e) && !a->jumping && a->target != 0xFF) {   /* the common case of a tick it does not think, short:
                                                                    = the path below to its "skip" (intent kept, no press) */
            o->press = 0; o->run = 0; o->hold = 0; o->blitz = o->chord = 0; o->ai = 1; o->guard = 0;
            a->wound = 0;
            if (a->cooldown) a->cooldown--;
            off_clocks(a);
            continue;
        }
        o->dx = o->dz = 0; o->press = 0; o->run = 0; o->face = 0; o->grab = 0; o->ai = 1; o->slow = 0; o->hold = 0; o->blitz = o->chord = 0;
        o->guard = 0;
        if (e->state == S_OFF) continue;
        /* the wind-up: an attack starting now has its first frame held */
        if ((e->state == S_ATTACK || e->state == S_SPECIAL) && e->state_t == 0) {
            if (!a->wound && !e->freeze && !(a->mode == AM_ACT && (a->kind == K_FURY || (a->kind == K_COMBO && a->cpressed &&
                (a->cnode != 0xFF || a->csid != 0xFF))))) e->freeze = windup_hold(e);   /* (a boss's string: its first move
                                                                    only, the links / cancels come at once; its fury: the
                                                                    super flash is its tell) */
            a->wound = 1;
        } else a->wound = 0;
        if (a->cooldown) a->cooldown--;
        if (a->b) boss_clocks(e, a);
        if (a->target == 0xFF) { if (a->mode != AM_FREE) release(e, a); continue; }   /* nobody to fight */
        if (hurt(e)) { if (a->mode != AM_FREE) { release(e, a); if (a->cooldown < P->rest_start) rest(a, P->rest_start); } a->gnear = 0; continue; }
        ex = INT(e->x); ez = INT(e->z); tx = px[a->target]; tz = pz[a->target];
        dx = tx - ex; dz = tz - ez; adx = iabs(dx); adz = iabs(dz); side = dx > 0 ? -1 : 1;   /* side: the enemy's side of him */
        o->face = sgn(dx);
        if (a->b) {                                              /* the boss layer (above): its reactions first */
            const gbossai_t *B = a->b;
            fighter_t *t = &fs[a->target];
            uint16_t sig = attacking(t) ? ((uint16_t)t->state << 12) ^ ((uint16_t)t->anim << 4) ^ t->node ^ ((uint16_t)t->spec_ix << 8) : 0;
            uint8_t fresh = sig && (sig != a->tsig || t->state_t < a->tst);   /* an attack of his starting */
            a->tsig = sig; a->tst = t->state_t;
            if (adx < 48 && adz <= 14) {                         /* he comes near: what a grab on it does this time (again */
                if (!a->gnear) {                                 /* every 64 frames he stays: one roll an attempt or so) */
                    uint8_t r = rnd();
                    e->grsp = r < B->grab_immune ? GR_IMMUNE : (uint16_t)r < (uint16_t)B->grab_immune + B->grab_counter ? GR_COUNTER : GR_NONE;
                }
                if (++a->gnear >= 64) a->gnear = 0;
            } else if (adx > 64 || adz > 20) a->gnear = 0;
            if (a->mode == AM_ACT && a->kind == K_COMBO && !a->cpressed && e->landed &&
                (e->state == S_ATTACK || e->state == S_AIR_ATTACK || e->state == S_SPECIAL)) a->clanded = 1;
            if (e->state != S_GRAB) a->ctm = 0;
            else if (e->gctr) {                                  /* its counter-hold: its throw after counter_delay */
                if (++a->ctm >= B->counter_delay) { o->press = IN_A; o->dx = e->facing; e->gctr = 0; blog(BE_COUNTER, 0, 0, 0); rest(a, P->rest_throw); }
                continue;
            }
            if (e->state == S_GUARD) {                           /* guarding: while his attack goes on, its hold at least */
                if (a->gtm) a->gtm--;
                if (e->gd_stun || a->gtm || (attacking(t) && adx < B->guard_dx + 16)) o->guard = 1;
                else a->grest = B->guard_rest;
                continue;
            }
            if (fresh && B->guard_chance && !a->grest && able(e) && e->facing == sgn(dx) && adx < B->guard_dx && adz <= B->guard_dz &&
                rnd() < B->guard_chance) {
                release(e, a); o->guard = 1; a->gtm = B->guard_hold; blog(BE_GUARD, t->state, t->anim, 0);
                continue;
            }
            if (a->red && !a->rtm && able(e) && e->facing == sgn(dx) && adx <= B->red_dx && adz <= P->range_dz + 4 &&
                spec_ix(e->ch, BS_FURY) != 0xFF) {               /* the red period: its fury, the MAX first */
                uint8_t mx = a->rcount < B->red_max;
                release(e, a); o->press = IN_D; o->dz = mx; a->rcount++; a->rtm = (uint16_t)B->red_rest << 2; a->mode = AM_ACT; a->kind = K_FURY;
                blog(BE_SUPER, mx, e->hp > 255 ? 255 : (uint8_t)e->hp, 0);
                continue;
            }
            if (a->mode == AM_ACT && a->kind == K_COMBO && a->cgo && e->state == S_GRAB && (combo_op(a) & 7) == CO_GRAB) combo_next(a);
            if (a->mode == AM_ACT && a->kind == K_COMBO && a->cgo &&
                (e->state == S_ATTACK || e->state == S_AIR_ATTACK || e->state == S_SPECIAL)) { combo_move(e, a, o, dx); continue; }
            if (e->state == S_RUN && a->running) {               /* a run: on to run_stop px, on his line */
                o->dx = sgn(dx); if (adz > 2) o->dz = sgn(dz);
                if (adx <= B->run_stop || ++a->tm > 90) {
                    uint8_t op;
                    if (a->running == 2 && a->mode == AM_ACT && a->kind == K_COMBO) {   /* a string's run: its next press */
                        if ((combo_op(a) & 7) == CO_RUN) combo_next(a);   /* from the run (A: the dash attack; a grab: on */
                        op = combo_op(a);                                 /* into him) */
                        if ((op & 7) == CO_GRAB) { o->grab = 1; if (a->tm > 120) { o->dx = 0; a->running = 0; } }
                        else { a->running = 0; if (!op || !op_press(e, a, o, op, dx)) { o->dx = 0; a->cpos = BC_OPS; } else if (!o->dx) o->dx = sgn(dx); }
                    } else { o->dx = 0; a->running = 0; }        /* the approach's run: it walks on */
                }
                continue;
            }
        }
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
        if (skip) {                                              /* not its think tick: the last walk, the clocks run */
            o->dx = kdx; o->dz = kdz; o->face = kface; o->slow = kslow; o->grab = kgrab;
            off_clocks(a);
            continue;
        }
        if (a->mode == AM_ACT && a->kind == K_COMBO && a->cgo) { /* a boss's string, between two moves: its next press from */
            uint8_t op = combo_op(a), k = op & 7;                /* neutral, when the last move connected (or none yet: its */
            uint8_t prev = a->cpos ? a->b->combo[a->cix][a->cpos - 1] & 7 : 0;   /* first press, the one after a run / jump) */
            if (!a->cpressed && k && (!a->cpos || a->clanded || prev >= CO_RUN)) {
                if (k == CO_GRAB) { if (a->tm < 45 && adz <= P->range_dz + 6) { a->tm++; o->dx = sgn(dx); o->grab = 1; continue; } }
                else if (k <= CO_D && (k != CO_A || (adz <= P->range_dz + 4 && adx <= P->range_max + 8)) && op_press(e, a, o, op, dx)) continue;
            }
            combo_end(a);                                        /* (a press that took nothing, a whiff, out of reach, done) */
        }
        if (a->mode == AM_ACT) {                                 /* able again: the attack is over (a grab: still walking in) */
            if (a->kind == K_GRAB && a->tm < 45 && adx + 4 >= P->range_min) { a->tm++; o->dx = sgn(dx); o->grab = 1; continue; }
            release(e, a);
        }
        if ((P->flags & AIF_REVERSAL) && a->cooldown == 0 && (a->mode != AM_FREE || may_take(fs, nf, np, i))) {   /* boss: */
            fighter_t *t = &fs[a->target];                       /* an attack this close: down + C, the rising reversal */
            if ((t->state == S_ATTACK || t->state == S_AIR_ATTACK) && adx < P->rev_dx && adz <= P->rev_dz &&
                spec_ix(e->ch, BS_DOWN_D) != 0xFF && (rnd() & halve(P->rev_mask, dbl)) == 0) {
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
                e->facing == sgn(dx) && rnd() < twice(P->hop_chance, dbl)) {   /* resting close: a back-hop (B let go at once) */
                o->press = IN_B; o->dx = -sgn(dx); continue;
            }
        }
        if (a->mode != AM_READY && (P->flags & AIF_PROJECTILE) && a->cooldown == 0 && adz <= P->spec_dz && adx >= P->spec_min &&
            adx <= P->spec_max && spec_ix(e->ch, BS_D) != 0xFF && !(rnd() & halve(P->proj_mask, dbl && P->proj_mask)) &&
            (rnd() & halve(P->proj_mask2, dbl && !P->proj_mask)) == halve(P->proj_mask2, dbl && !P->proj_mask) &&
            (a->mode != AM_FREE || may_take(fs, nf, np, i))) {   /* mid range, any enemy: the projectile, 1 in (proj_mask + 1) (proj_mask2 + 1) a frame */
            ready(e, a, K_PROJ); continue;
        }
        if (a->mode == AM_FREE) {
            if ((P->flags & AIF_TOKEN) && a->cooldown == 0 && may_take(fs, nf, np, i)) { a->mode = AM_APPROACH; a->tm = 0; }
        }
        if (a->mode == AM_APPROACH) {
            if (++a->tm > gai.approach_max) { release(e, a); rest(a, P->rest_start); continue; }   /* could not get there */
            if (a->b && a->b->ncombo) {                          /* a boss's strings (the boss layer) */
                const gbossai_t *B = a->b;
                if (a->cix == 0xFF) { a->cix = combo_pick(a); a->cgo = 0; }
                if (a->cix != 0xFF && (B->combo[a->cix][0] & 7) == CO_RUN && adx >= B->run_stop + 24 && adz <= 12 && e->facing == sgn(dx)) {
                    unpose(e, a); combo_go(a); a->mode = AM_ACT; a->kind = K_COMBO; rest(a, P->rest_attack);   /* it opens */
                    o->run = 1; o->dx = sgn(dx); a->running = 2; a->tm = 0;                                      /* with a run */
                    continue;
                }
            }
            if (a->b && a->b->run_chance && !a->runroll && adx > a->b->run_from && adz <= 12 && e->facing == sgn(dx)) {   /* the */
                a->runroll = 1;                                                                          /* approach runs in */
                if (rnd() < a->b->run_chance) { o->run = 1; o->dx = sgn(dx); a->running = 1; a->tm = 0; blog(BE_RUN, adx > 255 ? 255 : (uint8_t)adx, 0, 0); continue; }
            }
            if ((P->flags & AIF_SPECIALS) && adz <= P->bspec_dz && adx >= P->bspec_min && adx <= P->bspec_max &&
                (rnd() & halve(P->bspec_mask, dbl)) == 0) { ready(e, a, K_BSPEC); continue; }   /* boss: a special on his line */
            if ((P->flags & AIF_JUMP_IN) && adz <= P->jump_dz && adx >= P->jump_min && adx <= P->jump_max &&
                rnd() < twice(P->jump_chance, dbl) && e->facing == sgn(dx)) { ready(e, a, K_JUMP); continue; }   /* the jump-in */
            if (adz <= P->range_dz && adx <= P->range_max) {
                if (a->b && a->cix != 0xFF) {                    /* a boss: its string, whatever it opens with (too close: */
                    if (adx + 4 >= P->range_min || (a->b->combo[a->cix][0] & 7) == CO_GRAB) {   /* a step back first, */
                        if (e->facing == sgn(dx)) ready(e, a, K_COMBO);                         /* a grab at once) */
                        continue;
                    }
                } else {
                    if (a->plan_grab && adx + 4 >= P->range_min) { ready(e, a, K_GRAB); continue; }   /* then walk into him */
                    if (adx + 4 < P->range_min) a->plan_grab = 0;    /* too close to walk in (he is busy): punch */
                    if (adx >= P->range_min) { if (e->facing == sgn(dx)) ready(e, a, K_PUNCH); continue; }   /* (turned first) */
                }
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
    o->guard = 0;
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
