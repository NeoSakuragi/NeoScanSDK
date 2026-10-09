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
_Static_assert(SFX_PAL == 224 && SFX_NPAL <= SFX_NPAL_MAX, "draw.s SFX_PAL (KOF's shared effects bank, TODO #214)");
_Static_assert(offsetof(bchar_t, frames) == 10 && offsetof(bchar_t, anims) == 14 && offsetof(bchar_t, tile_hi) == 60, "draw.s CH_*");
_Static_assert(offsetof(banim_t, steps) == 2 && offsetof(bframe_t, nparts) == 0 && offsetof(bframe_t, parts) == 2, "draw.s AN_STEPS/FR_*");
_Static_assert(offsetof(bpart_t, dx) == 0 && offsetof(bpart_t, dy) == 2 && offsetof(bpart_t, cols) == 4 && offsetof(bpart_t, rows) == 5 &&
               offsetof(bpart_t, hflip) == 6 && offsetof(bpart_t, vflip) == 7 && offsetof(bpart_t, pal) == 8 &&
               offsetof(bpart_t, tiles) == 10 && sizeof(bpart_t) == 14, "draw.s PT_*");

#define GRAVITY_KD  0x5000        /* knockdown gravity 0.31 px/frame^2 (KOF95: 0.47): higher, slower falls to juggle */
#define DOWN_FRAMES 40
#define DANCE_DROP  (2 * GRAVITY_KD)   /* a dance's caught airborne victim falls at twice the knockdown gravity (TODO #150) */
#define INV_GETUP   30
#define DOWN_PIN    96            /* frames a lying fighter may wait past DOWN_FRAMES for a down attack coming at it (dpin;
                                     TODO #218: DD's shortest dizzy, +$FE 96) */
#define POP_VX      0x1F000       /* a lying fighter hit by a down attack (react, TODO #218): DD's 119 header, vx 2 away and */
#define POP_VY      0x3A000       /* vy 4 up, gravity 0.375 (b6 $6x), friction >> 5 (b6 $x5); vx / vy here after DD's first */
#define POP_G       0x6000        /* frame's vy += g / vx -= vx >> 5 (its order: before the move; kof_fall's after) */
#define INV_FURY    0xFF          /* a fury: untouchable (hits, grabs, pushes) from its trigger until it ends (Bruno
                                     2026-10-06; start_special) */
enum { PF_END = 1, PF_EVENT = 2, PF_LAND = 4, PF_FALL = 8, PF_HITANY = 16, PF_HOLD = 32, PF_SIG6 = 64, PF_SIG7 = 128 };   /* PF_EVENT: KOF's +$7D bit 7
                                     (the step's $0080 until consumed), PF_HITANY +$E3 bit 7, PF_HOLD +$E4 bit 4, PF_SIG7 /
                                     PF_SIG6 +$D1 bits 7 / 6: its objects' signals (bproj_t sig) and P_FXOFF (TODO #139) */
enum { VPH_FREEZE = 1, VPH_MIRROR = 2 };   /* fighter_t.vph: a special's victim phases (P_VPHASE, fighter.c vphase) */
#define HITSTOP     7             /* hit-stop frames of a special's / a fury's / a throw's hit (Bruno 2026-10-04; KOF98 counts +$124
                                     from 7 to 11 by move); a normal's is its route node's (rnode_t.hitstop, revamp 1A: 6 jab -> 12
                                     finisher, routes.py chain_tree), this when the node has none */
#define CATCH_STOP  1             /* a ROM special's catch (a catch box's hit, TODO #220): KOF's hit-stop routine runs one
                                     frame ($1B2C4), then the catch's dead frames ($1B402: the catching step's hit-stop
                                     counted down, prog_update pcatch 2, pdeadn) are its pause. The brawler's: its HITSTOP
                                     and the dead frames past KOF's first, at least HITSTOP in all (Bruno's every-hit rule),
                                     KOF's own when longer: the hit-stop is max(CATCH_STOP, HITSTOP - (pdeadn - 1)). A catch
                                     with one dead frame (the furies', class 4) keeps HITSTOP; Yamazaki 236236C's (12) held
                                     7 + 12 frames where KOF holds 1 + 12: his swirl ended 7 frames before he moved again */
/* hit stun (revamp 1A): gchain.stun_light / stun_heavy for an enemy (Final Fight 28, the later Capcom games 23-36), a short
 * gchain.stun_player for a player plus its untouchable window (gchain.guard_player; SOR2 12, Punisher 17) */
#define AI_IDLE_DELAY 10          /* AI fighters stop walking into idle only after this many frames without a walk intent */
#define CHAIN_WINDOW (gchain.window)   /* frames after a route step that hit during which A / B continues the route (Final
                                     Fight 45 while idle; revamp 1A: game.json chain.window, ~35) */
/* walk / run (Bruno 2026-10-08: by archetype, Final Fight's speeds; game.json "walk" -> gwalk_rom, gwalk_run): sub-pixel
 * (16.16; the whole-pixel rounding of KOF's speeds is gone), run = walk x gwalk_run; the walk / run animations play at
 * wspd / the fighter's KOF walk (fighter_t.wrate, walk_rate) so the feet keep their KOF stride on the floor */
static uint16_t div16(uint32_t n, uint16_t d) { __asm__("divu.w %1,%0" : "+d"(n) : "d"(d)); return (uint16_t)n; }   /* (68000
                                                                    divu: quotient < 65536, no libgcc) */
static int32_t mul88(int32_t v, uint16_t k) {                    /* v * k / 256 (16.16 x 8.8; no 32-bit multiply) */
    uint32_t a = v < 0 ? (uint32_t)-v : (uint32_t)v, lo = (uint32_t)(uint16_t)a * (uint16_t)k;
    uint32_t r = (uint32_t)(uint16_t)(a >> 16) * (uint16_t)k + (lo >> 16);
    r <<= 8; r += (lo >> 8) & 0xFF;
    return v < 0 ? -(int32_t)r : (int32_t)r;
}
static void walk_rate(fighter_t *f) {                           /* wspd, wrate from the fighter's data */
    uint32_t kof = (uint32_t)f->ch->phys.walk;                   /* its KOF walk (16.16) */
    f->wspd = gwalk_rom[f->ch->id];
    f->wrate = kof >= 0x1000 ? div16((uint32_t)f->wspd >> 4, (uint16_t)(kof >> 12)) : 0x100;   /* (8.8: wspd / kof, in
                                                                    1/4096 px units) */
    f->wrate = (uint16_t)(((uint32_t)f->wrate * gwalk_anim) >> 8);   /* x game.json walk.anim (Bruno 2026-10-08: the frames
                                                                    1.5x faster, the movement speed unchanged) */
    if (f->wrate < 0x40) f->wrate = 0x40;
    if (f->wrate > 0x400) f->wrate = 0x400;
}
#define X_MIN 16
#define X_MAX (world_w - 16)

static const char *NAMES[S_COUNT] = { "IDLE    ", "WALK    ", "RUN     ", "PREJUMP ", "AIR     ", "LAND    ", "ATTACK  ",
    "AIR ATK ", "HITSTUN ", "KNOCKDN ", "DOWN    ", "GETUP   ", "GRAB    ", "GRABBED ", "THROW   ", "THROWN  ", "SPECIAL ", "DEAD    ", "PROJ    ", "OFF     " };
const char *fighter_state_name(uint8_t st) { return NAMES[st]; }

/* ---- chain routes (fighter.h "chain routes"): each fighter's tree, through route_tab[] (RAM) ------------------------
 * The default tree (routes.py default_tree, every fighter without a routes file; TODO #71: one attack button): far A -A->
 * far A -A-> close C -A-> close D -A-> C+D (knockdown); far A, far A -down-forward+A-> far D (launch); far A -B-> a
 * jump-cancel (air C -A-> air C+D); close A: close B -A-> far C -A-> sweep (trip); forward+A = body toss, down+A = sweep
 * inside any window; the six C slots = the special the input picks, cancelling a normal that hit. Air: A / down+A /
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
static const uint16_t *const vcodes[BC_COUNT] = VOICE_CODES;   /* code | $100: the overflow slots (VOICE_PREFIX2_*) */
static const uint8_t vncodes[BC_COUNT] = VOICE_NCODES;
static uint8_t mute;                                         /* fighter_play / fighter_animate: previews */
void voices_init(void) { uint8_t i; for (i = 0; i < BC_COUNT; i++) voice_tab[i] = bm_chars[i].voices; }
/* id bit 7: an effect of its game (voices.py fx_bit): the other voice slot, so it plays over the fighter's voice */
static void voice_id(const bchar_t *ch, uint8_t team, uint8_t id) {
    if (id & 0x80) { team ^= 1; id &= 0x7F; }
    if (id && id < vncodes[ch->id]) {
        uint16_t c = vcodes[ch->id][id];
        snd_voice(c >> 8 ? (team ? VOICE_PREFIX2_ENEMY : VOICE_PREFIX2_PLAYER) : (team ? VOICE_PREFIX_ENEMY : VOICE_PREFIX_PLAYER), (uint8_t)c);
    }
}
void voice_play(const bchar_t *ch, uint8_t team, uint8_t key) { voice_id(ch, team, voice_tab[ch->id][key * 2]); }
static void voice_at(const fighter_t *f, uint8_t key, uint16_t from, uint16_t to) {   /* `at` in [from, to] */
    const uint8_t *e = voice_tab[f->ch->id] + key * 2;
    if (mute || f->state == S_PROJ) return;
    if (e[0] && e[1] >= from && e[1] <= to) voice_play(f->ch, f->team, key);
    if (voice_tab[f->ch->id] != f->ch->voices) return;           /* a pack's table: its own voices only */
    for (e = f->ch->vmore; *e != 0xFF; e += 3)                   /* the key's further voices (bchar_t.vmore) */
        if (e[0] == key && e[2] >= from && e[2] <= to) voice_id(f->ch, f->team, e[1]);
}
/* a ROM special's voices (TODO #163, one rule for every KOF program): sent where the source's code sends them (P_VOICE:
 * now, or b frames later as KOF's +$1B4 / +$1B6 countdown) and where its animation's steps carry KOF's $FC record
 * (bspec_t.pvox: as the program enters the step), in the order the program reaches them; ids resolved by the export
 * (the roster's mapping, export_bm prog_voice_res). A data pack's voice table plays its own voice for the key in place
 * of the special's first (the ROM table's entry for the key), the others stay silent. */
static void prog_voice(const fighter_t *f, uint8_t id) {
    uint8_t key = VK_SPEC + f->spec_ix;
    if (mute || !id) return;
    if (voice_tab[f->ch->id] != f->ch->voices) {
        if (id != f->ch->voices[key * 2]) return;
        id = voice_tab[f->ch->id][key * 2];
    }
    voice_id(f->ch, f->team, id);
}
uint8_t spec_ix(const bchar_t *ch, uint8_t role) {
    uint8_t k = role == BS_FURY_MAX ? (ch->fury_max < ch->nspec ? ch->fury_max : ch->fury) : role == BS_FURY ? ch->fury :
                role == BS_FORM ? (ch->form_trig ? ch->form_spec : 0xFF) : role == BS_AIR || role == BS_THROW ? 0xFF :   /* (the air specials: a
                                                                    table, air_pick; start_special keeps the pick) */
                role == BS_DOWNATK ? ch->down_spec : spec_tab[ch->id][role];
    return k < ch->nspec ? k : 0xFF;
}
/* the air specials (TODO #221, vocabulary air.special, game.json roster[].air_specials): bm_air[id] (bchar_t.nair entries), [input, special
 * index] each, 0xFF ends; input = the stick's slot as the ground's six C slots read it (BS_D .. BS_UF_D: neutral,
 * forward, down, up, down-forward, up-forward; d_input) | AIR_A when the button is A (else C). A press in a jump plays the
 * entry of its button and the stick's slot, a diagonal without one its vertical's (down-forward -> down, up-forward ->
 * up; down-back = down as on the ground). An A entry takes the air normal's place (no meter; not while a jump-cancel's
 * node waits: air_node); a C entry costs a C special's meter (spend). A projectile special while the fighter's
 * projectile flies: none (special_pick's rule; the press is then the air normal / nothing). -> the special's index in
 * specials, 0xFF = none */
static uint8_t d_input(const fighter_t *f, const intent_t *in);
static uint8_t air_pick(const fighter_t *f, const intent_t *in) {
    const uint8_t *e;
    uint8_t d = d_input(f, in) - RI_S, v = d == BS_DF_D ? BS_DOWN_D : d == BS_UF_D ? BS_UP_D : d, k = 0xFF, q = 0;
    for (e = bm_air[f->ch->id]; *e != 0xFF; e += 2) {
        uint8_t a = e[0] & AIR_A, s = e[0] & 15, m = s == d ? 2 : s == v ? 1 : 0;
        if (!(in->press & (a ? IN_A : IN_C)) || (a && f->air_node) || m <= q || e[1] >= f->ch->nspec) continue;
        if (f->ch->specials[e[1]].proj && f->shot) continue;
        k = e[1]; q = m;
    }
    return k;
}
static uint8_t air_button(const bchar_t *ch, uint8_t ix) {      /* the button of the air special ix (PC_HELD) */
    const uint8_t *e;
    for (e = bm_air[ch->id]; *e != 0xFF; e += 2) if (e[1] == ix) return e[0] & AIR_A ? IN_A : IN_C;
    return IN_A;
}
/* the special playing may be cancelled ("cancels" rules 2 / 3): a special (not a form's transition), or a fury (not a
 * MAX) when the fighter has a MAX fury of its own (bchar_t.fury_max: the cancel's only target then) */
static uint8_t may_cancel(const fighter_t *f) {
    if (f->spec_id == BS_FORM || f->spec_id == BS_AIR || f->spec_id == BS_DOWNATK || f->spec_id == BS_THROW || f->sthr) return 0;   /* (a
                                                                    throw, its super: no cancel, revamp 3) */
    return f->spec_id != BS_FURY;                                /* a fury: never (Bruno 2026-10-08: the fury is the ladder's
                                                                    last rung, no fury -> MAX cancel) */
}
void routes_init(void) { uint8_t i; for (i = 0; i < BC_COUNT; i++) route_tab[i] = (const rt_head_t *)bm_chars[i].routes; }
/* lab.load 5 (revamp phase 5, the chain tool: fighter.h lab_t, tools/brawler/chainlab/chaintool.js): buf = a chain
 * override, the fighter's tree (chain, finishers, per-node hit-stop) and after it a retime table (gretime_t rows, each
 * t an offset from buf, fixed up here into a pointer; fighter 0xFF ends it). Checked, then route_tab[fighter] and rt_tab
 * point into buf; refused (lab.pack_stat untouched, both back to the ROM's) when the tree or a row falls outside buf.
 * Any tree load (1, 2, 5) first drops a load 5's rt_tab (its table lives in buf); 2 or a refused 5 puts the ROM's
 * tree back. Without a load 5 nothing here touches rt_tab (retime_proof.py's own tables stay as they were). */
static uint8_t rt_lab;                                    /* rt_tab points into lab.buf (a load 5) */
static const gretime_t *lab_retime(const rt_head_t *t) {
    uint16_t at = sizeof(rt_head_t) + (uint16_t)t->nnodes * sizeof(rnode_t), n = 0;
    gretime_t *e;
    if (at + sizeof(gretime_t) > LAB_BUF) return 0;
    for (e = (gretime_t *)(lab.buf + at); ; e++, n++) {
        uint32_t o;
        if ((uint8_t *)(e + 1) > lab.buf + LAB_BUF) return 0;
        if (e->fighter == 0xFF) return (const gretime_t *)(lab.buf + at);
        o = (uint32_t)e->t;
        if (o < at || o + 2u * e->nseg > LAB_BUF || (o & 1)) return 0;
        e->t = (const uint16_t *)(lab.buf + o);
    }
}
void lab_install(void) {
    const rt_head_t *t = (const rt_head_t *)lab.buf;
    uint8_t ok;
    if (!lab.load) return;
    if (lab.fighter < BC_COUNT) {
        if (rt_lab) { rt_tab = 0; rt_lab = 0; }              /* buf is rewritten: a load 5's table goes with it */
        ok = (lab.load == 1 || lab.load == 5) && t->magic[0] == 'R' && t->magic[1] == 'T' && t->version == TREE_VERSION;
        if (ok && lab.load == 5) { const gretime_t *r = lab_retime(t); ok = r != 0; if (ok) { rt_tab = r; rt_lab = 1; } }
        if (ok) route_tab[lab.fighter] = t;
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
static void rt_arm(fighter_t *f, uint16_t move);
static void play(fighter_t *f, uint8_t anim) {
    f->anim = anim; f->step = 0; f->anim_done = 0; f->acc = 0; f->speed = 0x100;
    step_move(f); voice_at(f, anim, 0, 0);
    rt_arm(f, anim);                                             /* its targets, if it has some (retiming) */
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
/* the step whose hurt box the fighter has now (TODO #205): a special read from the ROM shows its program's animation
 * step (pan / pstep, from its first frame played: srow), with that step's own hurt box or none (KOF98's steps without
 * $0200: Kyo's EX 421D frames 0-10); everything else its brawler animation's step. Steps are in the first MB: no bank */
const bstep_t *fighter_hurt_step(const fighter_t *f) {
    if (f->state == S_SPECIAL && f->srow && f->pan && f->ch->specials[f->spec_ix].prog) return &f->pan->steps[f->pstep];
    return fighter_step(f);
}
void fighter_play(fighter_t *f, uint8_t anim) { mute = 1; play(f, anim); mute = 0; }
void fighter_animate(fighter_t *f) { mute = 1; anim_tick(f); mute = 0; }
void fighter_pose(fighter_t *f, uint8_t anim) { play(f, anim); }       /* the same, with the animation's voices (the */
void fighter_pose_tick(fighter_t *f) { anim_tick(f); }                 /* stage clear's win pose, main.c win_tick) */

/* ---- retiming (revamp 1C; docs/brawler_data_model.md "Retiming", tools/brawler/retime.py) ----------------------------
 * The data keeps every move's source timing; a move given targets (game.json roster[].retime -> gretime_rom, a lab's
 * table at rt_tab, or fighter_retime) plays its segments (bm_seg: startup, then each active window and the recovery
 * after it) in its target lengths. One clock per segment of S source frames played in T game frames: each game frame
 * err += S, one source frame due each time err passes T, so the segment ends exactly on its T-th frame with its S
 * source frames played, and every segment's first frame shows its own first source frame (each window's contact frame
 * is shown). Source frames are played whole and in order by the move's own player (anim_tick at 1x, prog_update), so
 * every step entry, step move, box, effect, sound and program op of them happens: several in one game frame when
 * T < S (a frame that enters a new hit window stops there, the rest carried as rt_debt and paid by the segment's last
 * frame at the latest; every source frame passed runs its hit test: rt_probe), none when T > S (a ROM program's motion is then spread over the frames its source frame shows:
 * rt_hold, rt_dx, rt_dy; a step animation's moves are its steps' own, at their entry). The route node's speed does not
 * apply to a retimed move. Hit-stop (freeze) stops the clock; the victim's reaction, projectiles, the catch of a ROM
 * special (its dead frames and routine: 1x from the catch on) and the engine keep their own time. rt_flags 0: none of
 * this runs. */
const gretime_t *rt_tab;
static const uint16_t *rt_segs(const fighter_t *f, uint16_t move) {   /* [n, source frames...] or 0 */
    const uint16_t *t = bm_seg[f->ch->id];
    if (move >= t[0] || !t[1 + move]) return 0;
    return t + t[1 + move];
}
static void rt_skip(fighter_t *f) {                              /* the next segment with frames */
    while (f->rt_p < f->rt_nseg && !f->rt_S[f->rt_p]) f->rt_p++;
    f->rt_n = f->rt_err = 0;
}
static uint8_t rt_set(fighter_t *f, uint16_t move, const uint16_t *targets, uint8_t n) {
    const uint16_t *s = rt_segs(f, move);
    f->rt_flags = 0; f->rt_hold = 0; f->rt_debt = 0;
    if (!s || !targets || n != s[0]) return 0;
    f->rt_S = s + 1; f->rt_T = targets; f->rt_nseg = n; f->rt_p = 0;
    f->rt_flags = RT_ON | (move >= BA_COUNT ? RT_FIRST : 0); rt_skip(f);
    return 1;
}
uint8_t fighter_retime(fighter_t *f, const uint16_t *targets, uint8_t n) {
    return rt_set(f, f->state == S_SPECIAL ? BA_COUNT + f->spec_ix : f->anim, targets, n);
}
static void rt_arm(fighter_t *f, uint16_t move) {                /* a move starts: its targets from the table */
    const gretime_t *e = rt_tab ? rt_tab : gretime_rom;
    f->rt_flags = 0; f->rt_hold = 0;
    for (; e->fighter != 0xFF; e++)
        if (e->fighter == f->ch->id && e->move == move) { rt_set(f, move, e->t, e->nseg); return; }
}
static uint8_t rt_adv(fighter_t *f) {                            /* source frames due this game frame */
    uint8_t k = 0;
    uint16_t S, T;
    f->rt_flags &= ~RT_END;
    if (f->rt_flags & RT_FIRST) { f->rt_flags &= ~RT_FIRST; return 1; }   /* a program's first frame plays its first */
    if (f->rt_p >= f->rt_nseg) return 1;                         /* past its segments: 1x */
    S = f->rt_S[f->rt_p]; T = f->rt_T[f->rt_p] ? f->rt_T[f->rt_p] : S;
    f->rt_n++; f->rt_err += S;
    while (f->rt_err >= T) { f->rt_err -= T; k++; }
    if (f->rt_n >= T) { f->rt_p++; rt_skip(f); f->rt_flags |= RT_END; }
    return k;
}
/* a squeezed segment (T < S) passes several source frames in one game frame: each one passed (not the one shown, which
 * combat() tests) runs the hit test with its own box at once (strike), so a squeezed hit connects where the source's
 * did; a hit stops the frame there (its hit-stop then stops the clock) */
static void strike(fighter_t *a, fighter_t **fs, uint8_t n);
static fighter_t **cb_fs;         /* the entities combat() last tested (main.c order[]) and their count: rt_probe's */
static uint8_t cb_n;
uint8_t rt_probe_off;              /* (RAM, a test switch: 1 = revamp 1C's rule, only the frame shown is tested;
                                     tools/brawler/retime_hit_proof.py) */
static uint8_t rt_probe(fighter_t *f) {
    if (!cb_fs || f->freeze || rt_probe_off) return 0;
    strike(f, cb_fs, cb_n);
    return f->freeze != 0;
}
static void rt_anim(fighter_t *f) {                              /* anim_tick, retimed */
    uint8_t end;
    f->rt_debt += rt_adv(f); end = f->rt_flags & RT_END;
    while (f->rt_debt) {
        uint8_t st = f->step, an = f->anim;
        f->speed = 0x100; anim_tick(f); f->rt_debt--;
        if (!f->rt_flags) { f->rt_debt = 0; break; }
        if (f->rt_debt && !end && an == f->anim && st != f->step && (fighter_step(f)->flags & 4)) break;   /* a new hit
                                                                    window: shown, the rest carried */
        if (f->rt_debt && rt_probe(f)) break;                    /* a source frame passed: its box tested, a hit stops
                                                                    the clock there (the rest carried) */
    }
}

/* ---- helpers --------------------------------------------------------------------------------------------------- */
static int32_t dir_mul(int8_t d, int32_t v) { return d > 0 ? v : d < 0 ? -v : 0; }
static void enter(fighter_t *f, uint8_t st) {
    f->state = st; f->state_t = 0; f->dizzy = 0;                 /* (a stun strike's dizziness: a new state ends it) */
    if (st != S_AIR_ATTACK) f->jt = 0;                           /* (the jump table: only its own take-off and its air
                                                                    attacks keep it, "jumps"; any other air: gravity) */
    if (st != S_KNOCKDOWN) {                                     /* (the chain core: a juggle and a downed body end when it */
        f->kfloor = f->kslam = 0;                                /* is out of its knockdown; a reel keeps the juggle's count) */
        if (st != S_HITSTUN) f->jug_n = 0;
    }
    if (st != S_KNOCKDOWN && st != S_HITSTUN) { f->kmode = f->kdelay = 0; f->kvfr = 0; f->ksr = 0; f->vph = 0; }   /* KOF's
                                                                    reaction (kof_react) ends, a source reaction (src_react)
                                                                    and the victim phases of a special (vphase) too */
}
static void clamp(fighter_t *f) {
    if (f->x < FIX(X_MIN)) f->x = FIX(X_MIN);
    if (f->x > FIX(X_MAX)) f->x = FIX(X_MAX);
    if (f->z < 0) f->z = 0;
    if (f->z > FIX(Z_DEPTH)) f->z = FIX(Z_DEPTH);
}
/* ---- dance (Bruno 2026-10-06, docs/brawler_move_vocabulary.md "dance"): a fury's victims. fighter_hit marks every
 * fighter a fury hits (fighter_t.dance = the attacker). While that fury plays, its victim stays in its reel: no recovery
 * (S_HITSTUN holds), no special out of it, no fall when its life runs out (a hit whose reaction is a reel keeps it
 * standing; the knockdown / launch comes only with the hit that has one: the finisher), and when the fury ends a victim
 * still reeling with no life left falls then. A fury holding a caught victim (KOF +$E4 bit 4, PF_HOLD) holds the whole
 * crowd it hits: every hit a reel in place, its target (the caught one) kept. From the first hit until the victim is
 * down, it and the fury stay inside the screen (the wall rule, wall_update: every special's). ---- */
static uint8_t dancing(const fighter_t *v) {                    /* its fury still plays */
    const fighter_t *a = v->dance;
    return a && a->state == S_SPECIAL && a->spec_id == BS_FURY;
}
/* a dead body (TODO #150, KOF's way): a fighter whose life is out is no target any more, its fall and its death play
 * untouched; only the fury still dancing it (its reel, no life left: the finisher fells it) hits it on */
static uint8_t dead_body(const fighter_t *v, const fighter_t *a) {
    return v->hp <= 0 && !(dancing(v) && v->dance == (a->owner ? a->owner : a));
}
static void to_neutral(fighter_t *f, const intent_t *in) {
    if (in && (in->dx || in->dz)) { f->still = 0; enter(f, S_WALK); play_if_new(f, in->dx && in->dx == -f->facing ? BA_WALK_BACK : BA_WALK_FWD); f->speed = f->wrate; }   /* (its
                                                                    stride at the walk's speed: walk_rate) */
    else if (in && in->ai && f->state == S_WALK && ++f->still < AI_IDLE_DELAY) { }   /* AI: no walk/idle flicker */
    else { enter(f, S_IDLE); play_if_new(f, BA_IDLE); }
}
enum { SX_A, SX_B, SX_C, SX_D, SX_CD, SX_THROW_C, SX_THROW_D };   /* bchar_t.sfx (export_bm SFX_KEYS) */
static uint8_t hit_btn(uint8_t anim) {                         /* the button a normal's hit sounds as */
    switch (anim) {
    case BA_ATK_A_CLOSE: case BA_ATK_A_FAR: case BA_ATK_A_CROUCH: case BA_CMD_FWD_A: case BA_ATK_A_JUMP: case BA_ATK_A_JUMP_DIAG:
    case BA_ATK_A_RUN: case BA_ATK_A_RUN_LOW: return SX_A;
    case BA_ATK_B_CLOSE: case BA_ATK_B_FAR: case BA_ATK_B_CROUCH: case BA_CMD_FWD_B: case BA_ATK_B_JUMP: case BA_ATK_B_JUMP_DIAG:
    case BA_ATK_B_RUN: case BA_ATK_B_RUN_LOW:
    case BA_ATK_AB_CLOSE: case BA_ATK_AB_FAR: case BA_ATK_AB_CROUCH: case BA_ATK_AB_JUMP: case BA_ATK_AB_JUMP_DIAG:
    case BA_ATK_AB_RUN: case BA_ATK_AB_RUN_LOW: return SX_B;   /* WHP's strong punch: the heavy punch's sound */
    case BA_ATK_C_CLOSE: case BA_ATK_C_FAR: case BA_ATK_C_JUMP: case BA_ATK_C_CROUCH: case BA_CMD_DF_C: case BA_CMD_FWD_C:
    case BA_ATK_C_RUN: case BA_ATK_C_RUN_LOW: return SX_C;
    case BA_ATK_D_CLOSE: case BA_ATK_D_FAR: case BA_ATK_D_CROUCH: case BA_ATK_D_JUMP: case BA_CMD_DF_D: case BA_ATK_D_RUN:
    case BA_ATK_D_RUN_LOW: return SX_D;
    default: return SX_CD;
    }
}
/* a normal's hit sound: KOF98's per button ($11 A .. $14 D; $15 C+D and every knockdown), unless the fighter's
 * bchar_t.sfx sets the button's (TODO #75, game.json roster[].hit_sfx: Haohmaru's sword slashes $2B) */
static uint8_t hit_sound(const fighter_t *f, uint8_t anim, uint8_t knockdown) {
    uint8_t b = hit_btn(anim);
    return f->ch->sfx[b] ? f->ch->sfx[b] : knockdown ? SFX_HIT_CD : SFX_HIT_A + b;
}
/* a hit's own sound (Bruno's picks, Kim 2026-10-09: a route node's "sound" list, game.json throws.hold.sound; export_bm
 * bm_hsnd): key = the move (BA_*) or HS_HOLD + the hold script's index, idx = the hit's index in it (0 the first);
 * 0 = none given (the rules above) */
static uint8_t own_sound(const fighter_t *f, uint8_t key, uint8_t idx) {
    const uint8_t *e;
    for (e = bm_hsnd[f->ch->id]; *e != 0xFF; e += 2 + e[1])
        if (*e == key) return idx < e[1] ? e[2 + idx] : 0;
    return 0;
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
    f->node = node; f->buffered = 0; f->hit_mask = 0; f->landed = 0; f->chain_t = 0; f->spec_buf = 0; f->fury_buf = 0; f->ldmg = 0; f->blz_buf = 0;
    if (c->flags & RF_AIR) {                                     /* the jump in progress picks the air normal */
        if (a == BA_ATK_CD_JUMP) a = f->jump_kind ? BA_ATK_CD_HOP : f->jump_dir ? BA_ATK_CD_JUMP_DIAG : BA_ATK_CD_JUMP;   /* KOF's
                                                                    117, a KOF98 / 99 hop's 124; WHP's diagonal C+D (a KOF
                                                                    fighter's is its 117: export_bm SOURCES) */
        else if (a == BA_ATK_A_JUMP || a == BA_ATK_B_JUMP || a == BA_ATK_AB_JUMP) a += f->jump_dir != 0;   /* WHP's air A / B /
                                                                    A+B: the vertical one, its diagonal next (BA_* order) */
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
    if (in->dz > 0) b |= 0x40; else if (in->dz < 0) b |= 0x08;   /* (up: revamp 1A, the chain's up finisher) */
    if (in->close) b |= 0x10;
    return b;
}
/* the link an input takes: B its B link; A the exact one, else down-forward -> up -> forward -> down -> back -> close ->
 * plain (a plain A always continues a route whatever the stick does) */
static uint8_t next_node(const rnode_t *c, uint8_t b) {
    if (b & IN_B) return c->next[RI_B];
    if ((b & 0xC0) == 0xC0 && c->next[RI_DFA]) return c->next[RI_DFA];
    if ((b & 0x08) && c->next[RI_UA]) return c->next[RI_UA];
    if ((b & 0x80) && c->next[RI_FA]) return c->next[RI_FA];
    if ((b & 0x40) && c->next[RI_DA]) return c->next[RI_DA];
    if ((b & 0x20) && c->next[RI_BA]) return c->next[RI_BA];
    if ((b & 0x10) && c->next[RI_CA]) return c->next[RI_CA];
    return c->next[RI_A];
}
static uint8_t has_links(const rnode_t *c) { uint8_t k, n = 0; for (k = RI_A; k <= RI_UA; k++) n |= c->next[k]; return n; }
static uint8_t d_input(const fighter_t *f, const intent_t *in) {  /* C's direction, as special_for reads it: a diagonal */
    uint8_t fwd = in->dx == f->facing;                           /* only with the stick toward the facing (down-back = down) */
    return in->dz > 0 ? (fwd ? RI_DFS : RI_DS) : in->dz < 0 ? (fwd ? RI_UFS : RI_US) : in->dx ? RI_FS : RI_S;
}
/* B: the jump, the stick picks the direction (pressed away from the facing: KOF's back jump; the fighter keeps facing);
 * air_node: a jump-cancel's route node (fighter_t.air_node), 0 a plain jump */
static void jump_start(fighter_t *f, const intent_t *in, uint8_t air_node) {
    f->jump_dir = !in->dx ? 0 : in->dx == f->facing ? 1 : 2;
    f->jrun = f->state == S_RUN && f->jump_dir == 1;            /* out of a run, forward: gjump.run_dx x the travel */
    f->jump_kind = 0; f->vx = 0; f->vz = dir_mul(in->dz, FIX(1)); f->air_node = air_node;
    enter(f, S_PREJUMP); play(f, BA_PREJUMP);
    f->speed = div16((uint32_t)(f->ch->phys.prejump ? f->ch->phys.prejump : 1) << 8, gjump.crouch);   /* its crouch drawn over
                                                                    the one jump's crouch frames ("jumps") */
}
/* ---- jumps (Bruno 2026-10-08: ONE jump for every fighter, Cody's Final Fight arc; game.json "jump" -> gjump) ---------
 * B: gjump.crouch frames crouching (the prejump), then the table: frame i of the air at gjump.h[i] lines above the floor,
 * a forward jump travelling gjump.dx[i] (8.8 px) a frame the way it goes (a back jump the other way, a straight jump none),
 * the depth as the stick held at the press (1 px a frame); the rise animation turns into the fall at gjump.apex; past the
 * table it lands (gjump.land_dx more on that frame): S_LAND, gjump.land frames, any input ends it from gjump.land_cancel
 * on (Final Fight's landing cancels at once). One height (no hop), no per-fighter KOF physics. A fall that is not this
 * jump (after a special in the air, the respawn's drop) keeps the gravity (fighter_t.jt 0). Returns 1 on the landing. */
static uint8_t jump_frame(fighter_t *f) {
    uint8_t i = f->jt - 1;
    int8_t d = f->jump_dir == 1 ? f->facing : f->jump_dir == 2 ? -f->facing : 0;
    if (i >= gjump.n) {                                          /* the table played: the landing frame */
        f->x += dir_mul(d, f->jrun ? mul88((int32_t)gjump.land_dx << 8, gjump.run_dx) : (int32_t)gjump.land_dx << 8); f->z += f->vz; clamp(f);
        return 1;
    }
    f->y = FIX(gjump.h[i]); f->x += dir_mul(d, f->jrun ? mul88((int32_t)gjump.dx[i] << 8, gjump.run_dx) : (int32_t)gjump.dx[i] << 8); f->z += f->vz; clamp(f);
    f->jt++;
    if (f->state == S_AIR && i == gjump.apex && f->anim == JUMP_ANIM[0][f->jump_dir][0]) play(f, JUMP_ANIM[0][f->jump_dir][1]);
    return 0;
}
/* the air attacks' active frames (Bruno 2026-10-08, "jumps"): on the move's last active step the animation is held (the
 * step stays shown, its box live) while the jump attack (air_a / air_cd: knocking down) has been active fewer than
 * gjump.active_min frames, and for the down attack (air_b: a flinch) until the landing. Returns 1 to hold this frame */
static uint8_t air_hold(fighter_t *f) {
    const banim_t *an;
    uint8_t k;
    if (f->state != S_AIR_ATTACK) return 0;
    an = &f->ch->anims[f->anim];
    if (!(an->steps[f->step].flags & 1)) return 0;
    if (f->aact < 255) f->aact++;
    for (k = f->step + 1; k < an->nsteps; k++) if (an->steps[k].flags & 1) return 0;   /* (a later window: not its last) */
    if (f->node == TREE(f)->air_b) return 1;
    return (f->node == TREE(f)->air_a || f->node == TREE(f)->air_cd) && f->aact < gjump.active_min;
}
/* ---- the chain core (revamp 1A, Bruno's decisions docs/brawler_feel.md 8h; game.json "chain" -> gchain, the trees from
 * routes.py chain_tree) -------------------------------------------------------------------------------------------------
 * One system for every fighter: a chain = links from neutral, its length the fighter's archetype's (fast 5, balanced 4,
 * heavy 3: the tree's depth). It advances ONLY on a hit (the link's `landed`); a whiff or being hit restarts it at link 1
 * (start_node / fighter_hit clear the window). The next press is taken from the end of the hit-stop through the link's
 * recovery (a cancel) and gchain.window frames after it (chain_t, from neutral). A press made in the hit-stop is latched
 * (the freeze does not age it) and fires on the first possible frame; a player's press older than gchain.buffer frames
 * (hit-stop frames not counted: buf_age) is dropped, the AI's are kept whatever their age; a press in a whiffing link's
 * last gchain.buffer frames starts link 1 as it ends. The last link's stick picks the finisher (the tree's links: A
 * neutral, forward, up, down; down-forward -> forward; missing ones fall back to A): back = RF_THROW, the fighter's back
 * throw on the victim the link before hit (chain_throw: invincible to the throw's control return, the thrown body knocks
 * others down, no chain credit; no throw / no victim in reach: the neutral finisher). Hit-stop per node (rnode_t.hitstop),
 * hit stun and juggles in fighter_hit / combat ("juggle cap", "guard"). */
static uint8_t throw_ok(const fighter_t *f);
static void chain_throw(fighter_t *f, uint8_t node, uint8_t how);
static uint8_t hits_to_come(const fighter_t *f) {               /* a normal's hits (steps opening one) after this step */
    const banim_t *an = &f->ch->anims[f->anim];
    uint8_t k;
    if ((an->steps[f->step].flags & 4) && !f->hit_mask) return 1;   /* (Kim gold) the step just entered opens a hit not
                                                                    tested yet (anim_tick runs before combat): $96's third */
    for (k = f->step + 1; k < an->nsteps; k++) if (an->steps[k].flags & 4) return 1;
    return 0;
}
#define BUF_OK(f, in) ((in)->ai || (f)->buf_age <= gchain.buffer)
static uint8_t chain_next(const fighter_t *f, const rnode_t *c, uint8_t b) {   /* next_node + the back throw's fallback */
    uint8_t nx = next_node(c, b);
    if (nx && !(b & IN_B) && (RT_NODE(TREE(f), nx)->flags & RF_THROW) && !throw_ok(f)) nx = c->next[RI_A];
    return nx;
}
static uint8_t special_pick(const fighter_t *f, uint8_t want);   /* (fwd) */
static void start_special(fighter_t *f, uint8_t k);              /* (fwd) */
/* a special played as a chain finisher or the dash entry (revamp gold, from revamp/gold-tk): the node is RF_SPECIAL, its
 * anim the special's slot (BS_*, the C-cancel's encoding); played free, like the built-in finishers (no drive: it is part
 * of the chain, not a C press). 0 = the fighter has no special there (special_pick 0xFF): the caller plays the node as a
 * normal instead. */
static uint8_t node_special(fighter_t *f, uint8_t node, uint8_t how) {
    uint8_t k = special_pick(f, NODE(f, node)->anim);
    if (k == 0xFF) return 0;
    lab_note(f, LE_SPECIAL, node, how, k); start_special(f, k);
    return 1;
}
/* a route's next node: B's is a jump-cancel (its node waits for A in the air), a back throw (RF_THROW) grabs, a special
 * (RF_SPECIAL: a named special finisher) plays free, any other starts now */
static void route_go(fighter_t *f, uint8_t node, uint8_t b, const intent_t *in, uint8_t how) {
    const rnode_t *c = NODE(f, node);
    if (b & IN_B) jump_start(f, in, node);
    else if (c->flags & RF_THROW) chain_throw(f, node, how);
    else if ((c->flags & RF_SPECIAL) && node_special(f, node, how)) return;
    else start_node(f, node, how);
}
/* ---- the Blitz (Bruno 2026-10-08, docs/brawler_gold.md; game.json roster[].blitz -> gblitz_rom, "blitz" -> gblitz) -------
 * A double direction + A (main.c read_player: forward,forward / down,down / down,up / up,up, the taps and the A within
 * gblitz.window frames; run + A = the ff slot): the slot's move, free (no drive), NOT invincible, its own recovery: a
 * special of the pool (role BS_BLITZ, its damage gblitz.scale of its special tier: dtier) or the tree's dash entry
 * (BZ_DASH: a normal; a special dash node plays free: node_special). The ladder: a normal that hit (a chain link, a
 * finisher) cancels into it (S_ATTACK, blz_buf); it cancels on hit into a C special or the fury (may_cancel, the special
 * cancels). Empty slot: 0, the press is a plain A. Depth walking and the finishers' held up / down are untouched (a Blitz
 * needs two taps). */
static uint8_t blitz_dash(fighter_t *f, uint8_t how) {
    uint8_t dn = TREE(f)->dash;
    if ((NODE(f, dn)->flags & RF_SPECIAL) && node_special(f, dn, how)) return 1;
    start_node(f, dn, how);
    return 1;
}
static uint8_t blitz_go(fighter_t *f, uint8_t slot, uint8_t how) {
    uint8_t v = slot < BZ_COUNT ? gblitz_rom[f->ch->id][slot] : BZ_NONE;
    f->blz_buf = 0;
    if (v == BZ_DASH) return blitz_dash(f, how);
    if (v >= f->ch->nspec || !f->ch->specials[v].nrows) return 0;
    if (f->ch->specials[v].proj && f->shot) return 0;            /* (a projectile while its own flies: none, special_pick's rule) */
    lab_note(f, LE_SPECIAL, 0, how, BS_BLITZ);
    f->spec_ix = v; start_special(f, BS_BLITZ);
    return 1;
}

/* ---- the meter (Bruno's live redesign 2026-10-08, docs/brawler_gold.md; gamedata.h gmeter_t <- game.json "meter") ------
 * Players only (enemies pay nothing). Two bars:
 *   DRIVE (fighter_t.drive; the HUD's chunks): gmeter.chunks x gmeter.chunk points, full at the start and at a new life,
 *     one point back a frame (a chunk in gmeter.chunk frames). PAY_SPECIAL = a C special (C + the stick, the hold's C, a
 *     normal's / a Blitz's / a special's cancel into one, an air special on C): gmeter.special chunks, else it does not
 *     come out; it is invincible to its end (cspecial). The BREAKER (C or A+B in a hit stun or held: always the fighter's
 *     neutral C special, update): gmeter.breaker chunks, the fighter blinking WHITE for the whole move; short of them
 *     gmeter.life_breaker life (never the last point), the fighter blinking RED (breaker_pay; pal_overlay).
 *   FURY GAUGE (fighter_t.fgauge, hidden: never drawn): filled by damage dealt (gmeter.fury_dealt a point) and taken
 *     (fury_taken a point; the fury's own hits not counted: gauge_add), empty at the start, kept at a new life. Full: D
 *     (PAY_FURY) = the fury, the gauge emptied; full and low life (fighter_low: life <= gmeter.low % of the full life)
 *     = the MAX (PAY_MAX); low life alone grants nothing. PAY_FORM: the form link's transition (down+D, its trigger
 *     FT_DOWN_D_FULL: the gauge full).
 * Signals (pal_overlay, once a frame; one meaning per place): the sprite blinks 1 frame its colours / 1 frame a shiny white
 * palette while the fury is ready (fighter_fury_ready), red instead while the MAX is ready (red beats white); a breaker's
 * WHITE / RED blink (gmeter.blink frames on, as many off) owns the sprite while it plays; never over a burn, a white flash
 * (ai.c's pulse) or a fury's flash pose. The life bar's red blink at low life is the HUD's (main.c hud). gmeter.infinite
 * (a test switch): nothing spent, both bars full. */
enum { PAY_SPECIAL, PAY_FURY, PAY_MAX, PAY_FORM };
static const uint16_t WHITE_PAL[16] = { 0x8000, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF,
                                        0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF };
static void set_burn(fighter_t *f, uint8_t burn);
static void burn_show(fighter_t *f);
#define DRIVE_FULL ((uint16_t)(gmeter.chunk * gmeter.chunks))
uint8_t fighter_low(const fighter_t *f) {
    int16_t full = f->hp_max ? f->hp_max : 60;
    return f->hp > 0 && f->hp * 100 <= full * (int16_t)gmeter.low;
}
static uint8_t gauge_full(const fighter_t *f) { return gmeter.infinite || f->fgauge >= gmeter.fury_max; }
/* Bruno 2026-10-09 (his 0.9.0 note): low life = UNLIMITED fury (D, nothing spent); the MAX = down+D with the gauge full
 * AND low life (the gauge emptied); at normal life D = the fury with the gauge full (emptied) */
uint8_t fighter_fury_ready(const fighter_t *f) { return !f->team && (gauge_full(f) || fighter_low(f)); }
static uint8_t max_ready(const fighter_t *f) { return !f->team && gauge_full(f) && fighter_low(f); }
static uint8_t pay(fighter_t *f, uint8_t kind, uint8_t dry) {   /* dry: only whether it could -> 1 paid (or payable) */
    if (f->team) return 1;
    if (kind == PAY_SPECIAL) {
        uint16_t cost = gmeter.special * gmeter.chunk;
        if (gmeter.infinite) { f->drive = DRIVE_FULL; return 1; }
        if (f->drive < cost) return 0;
        if (!dry) f->drive -= cost;
        return 1;
    }
    if (kind == PAY_MAX) { if (!max_ready(f)) return 0; }
    else if (kind == PAY_FURY && fighter_low(f)) return 1;      /* low life: the fury is free (unlimited) */
    else if (!gauge_full(f)) return 0;
    if (!dry && !gmeter.infinite) f->fgauge = 0;
    return 1;
}
static uint8_t breaker_pay(fighter_t *f) {                      /* the breaker's price -> 1 drive (it blinks white), 2 life
                                                                    (it blinks red), 0 an enemy (nothing) */
    uint16_t cost = gmeter.breaker * gmeter.chunk;
    if (f->team) return 0;
    if (gmeter.infinite) { f->drive = DRIVE_FULL; return 1; }
    if (f->drive >= cost) { f->drive -= cost; return 1; }
    f->hp -= f->hp > gmeter.life_breaker ? gmeter.life_breaker : f->hp - 1;   /* (never the last point) */
    return 2;
}
static void gauge_add(fighter_t *f, uint16_t n) {               /* the hidden fury gauge fills (players) */
    if (f->team || f->state == S_PROJ || !n) return;
    f->fgauge = f->fgauge + n >= gmeter.fury_max ? gmeter.fury_max : f->fgauge + n;
}
static void start_special(fighter_t *f, uint8_t k);
static void cspecial(fighter_t *f, uint8_t k) {                 /* a C special, paid: invincible to its end (Bruno: "special
                                                                    (1 chunk, invincible)"; players: sinv keeps INV_FURY) */
    start_special(f, k);
    if (!f->team) { f->sinv = 1; f->inv = INV_FURY; }
}
/* the overlays' palettes, kept per player (computed when the fighter / colour set changes, not every blink frame) */
static struct { const bchar_t *ch; uint8_t set, tint; uint16_t pal[2][MAX_PALS][16]; } ovl_cache[2];
static const uint16_t *ovl_pal(const fighter_t *f, uint8_t kind, uint8_t i) {   /* kind 0 red, 1 shiny white */
    uint8_t p = f->idx & 1, n, j, k;
    if (ovl_cache[p].ch != f->ch || ovl_cache[p].set != f->set || ovl_cache[p].tint != f->tint) {
        ovl_cache[p].ch = f->ch; ovl_cache[p].set = f->set; ovl_cache[p].tint = f->tint;
        for (n = 0; n < f->ch->npal && n < MAX_PALS; n++) {
            const uint16_t *src = fighter_src_pal(f, n);
            for (k = 0; k < 2; k++) ovl_cache[p].pal[k][n][0] = src[0];
            for (j = 1; j < 16; j++) {
                uint16_t c = fighter_colour(f, src[j]);
                int16_t r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
                int16_t l = (r * 5 + g * 9 + b * 2) >> 4;
                ovl_cache[p].pal[0][n][j] = RGB(l + 10 > 31 ? 31 : l + 10, l >> 2, l >> 2);   /* red: reds of its light */
                ovl_cache[p].pal[1][n][j] = RGB(r + (((31 - r) * 5) >> 4) + 4 > 31 ? 31 : r + (((31 - r) * 5) >> 4) + 4,   /* shiny:
                                                                    each channel a third of the way to white and a
                                                                    little more (KOF95's MAX glow, measured: +6..+8 of 31
                                                                    on the darks, +1..+3 on the lights) */
                                                g + (((31 - g) * 5) >> 4) + 4 > 31 ? 31 : g + (((31 - g) * 5) >> 4) + 4,
                                                b + (((31 - b) * 5) >> 4) + 4 > 31 ? 31 : b + (((31 - b) * 5) >> 4) + 4);
            }
        }
    }
    return ovl_cache[p].pal[kind][i];
}
static uint16_t burn_clock;
static void pal_overlay(fighter_t *f) {
    uint8_t want = 0;
    if (f->brk && f->state != S_SPECIAL) f->brk = f->brkr = 0;   /* the breaker over */
    if (!f->team && !f->burn && !f->flash && !(f->state == S_SPECIAL && f->fpose) && f->state != S_PROJ) {
        if (f->brk) {                                            /* the breaker: white (red: paid in life) for the move */
            if (++f->brk > 2 * gmeter.blink) f->brk = 1;         /* (brk: 1 + its frame in the blink's period) */
            if (f->brk <= gmeter.blink) want = f->brkr ? OVL_RED : OVL_WHITE;
        }
        else if (fighter_fury_ready(f) && f->state != S_DEAD && (burn_clock & 1))   /* D does something now: 1 frame */
            want = max_ready(f) ? OVL_RED : OVL_SHINY;           /* normal, 1 frame red (the MAX ready) / shiny white (the fury) */
    }
    if (want == f->ovl) return;
    f->ovl = want;
    if (want == OVL_WHITE) { uint8_t i; for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) PAL_setPalette(f->palbase + i, WHITE_PAL); }
    else if (want == OVL_RED || want == OVL_SHINY) {
        uint8_t i;
        for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) PAL_setPalette(f->palbase + i, ovl_pal(f, want == OVL_SHINY, i));
    }
    else if (f->burn) burn_show(f);
    else fighter_load_pals(f);
}
static void meter_tick(fighter_t *f) {
    if (f->flash && !--f->flash) { uint8_t b = f->burn; f->burn = 0xFF; set_burn(f, b); }   /* its colours back (burnt: the burn's) */
    if (!f->team) {
        if (gmeter.infinite) { f->drive = DRIVE_FULL; f->fgauge = gmeter.fury_max; }   /* both bars stay full */
        else if (f->drive < DRIVE_FULL) f->drive++;              /* the drive: a point back a frame */
    }
    pal_overlay(f);
}

/* ---- damage tiers (revamp phase 2, Bruno 2026-10-08: "specials about equal across all characters (+-15 %), furies
 * (+-20 %), MAX (+-20 %); special < fury < MAX"; game.json "tiers", build_tables.py dtier_tables) ------------------------
 * dtier_rom[fighter] = 8.8 scales: [its special's pool index], then [nspec] its fury, [nspec + 1] its MAX: the tier's
 * total / the move's own total on a full connect, measured in our emulator (tools/brawler/damage_tiers.py ->
 * damage_raw.json). A special's, a fury's or a MAX's hits (its body, its objects; a projectile with its thrower's scale
 * at its spawn: dsc) deal their damage x the scale, the fraction carried on the thrower (dacc, from one half at the
 * move's start: the total rounded to nearest), so the move's total is its tier's. Normals (the chain core's totals),
 * throws and holds keep theirs. dtier_off (RAM, a test switch: damage_tiers.py --raw): every scale 1. */
uint8_t dtier_off;
static uint16_t dtier(const fighter_t *f) {
    const uint16_t *t = dtier_rom[f->ch - bm_chars];
    if (dtier_off || f->ch < bm_chars || f->ch >= bm_chars + BC_COUNT) return 0x100;
    if (f->sthr == 2) return t[f->ch->nspec + 2];                /* the super throw (revamp 3): its own tier */
    if (f->spec_id == BS_BLITZ) return (uint16_t)(((uint32_t)(uint16_t)t[f->spec_ix] * (uint16_t)gblitz.scale) >> 8);   /* a
                                                                    Blitz: its special's tier x gblitz.scale (the Blitz's
                                                                    whole damage, game.json blitz.damage) */
    return f->spec_id == BS_FURY ? t[f->ch->nspec + f->fmax] : t[f->spec_ix];
}
static void form_set(fighter_t *f, const bchar_t *to) {   /* the fighter's character data replaced (the form link) */
    f->ch = to; if (f->set >= to->nsets) f->set = 0;
    fighter_load_pals(f); f->ovl = 0; f->shown_frame = 0xFFFF; f->frame_ovr = 0xFFFF;
    f->node = 0; f->buffered = 0; f->spec_buf = f->fury_buf = 0; f->chain_t = 0; f->air_node = 0; f->landed = 0;
    walk_rate(f);                                                /* (its walk: the new form's archetype) */
}
static void react(fighter_t *v, int8_t away, uint8_t reaction, int8_t push);
void fighter_revive(fighter_t *f) {
    if (f->form_from && bm_chars[f->form_from - 1].form_exit == FX_LIFE) {   /* a life lost: back to the base form */
        form_set(f, &bm_chars[f->form_from - 1]); f->form_from = 0;
    }
    f->hp = 60; f->held = 0; f->thr = 0; f->frame_ovr = 0xFFFF; f->y = 0; f->vx = f->vy = f->vz = 0; f->drop = 0;
    f->drive = DRIVE_FULL;                                       /* a new life: the drive full (the fury gauge kept) */
    enter(f, S_GETUP); play(f, BA_GETUP); f->inv = 90;
}
/* ---- death and respawn (TODO #166 e, Bruno 2026-10-06: Final Fight's sequence; an engine rule for every player) ------
 * A player whose life is out falls and lies down like anyone (S_KNOCKDOWN, S_DOWN), then S_DEAD: it blinks for
 * DEATH_BLINK frames (main.c draw) with its death voice (VK_KO, at S_DEAD's start); then main.c flow: no life left ->
 * the continue; else a life is used: fighter_respawn drops it from above the screen where it lay (inside the screen),
 * untouchable and without control while it falls (drop 1, S_AIR, its jump's falling pose), and its landing knocks every
 * enemy on screen down (drop 2: main.c calls fighter_quake for each, no damage), RESPAWN_INV frames untouchable after. */
#define RESPAWN_Y   FIX(224)      /* the drop's start: px above its feet' line (above the screen's top for any fighter) */
#define RESPAWN_INV 60            /* untouchable frames after the landing (Final Fight: a moment) */
void fighter_respawn(fighter_t *f) {
    fighter_revive(f);
    enter(f, S_AIR); play(f, BA_JUMP_UP_FALL); f->jump_kind = 0; f->jump_dir = 0; f->air_node = 0;
    f->y = RESPAWN_Y; f->vx = f->vy = f->vz = 0; f->drop = 1; f->inv = 2;
}
void fighter_quake(const fighter_t *by, fighter_t *v) {
    v->freeze = 0;
    react(v, INT(v->x) >= INT(by->x) ? 1 : -1, R_KNOCKDOWN, 0);
}

/* SS2's big hit (TODO #188 c, Haohmaru's WFT: handlers_ss2 BIGHIT, bspec_t.sflags SF_BIGHIT): on its connect both hold
 * BIGHIT_STOP frames, the stage goes and the backdrop is red for BIGHIT_RED frames (main.c screen_fx), then the whole
 * game plays at half speed for BIGHIT_SLOW frames (main.c game_tick: every other logic tick skipped). TODO #195 (Bruno
 * 2026-10-07: "the red screen is too much and there shouldn't be so much freeze on impact"): a short flash and the
 * brawler's own hit-stop, no slow motion; the victim still held to the slash's throw (21 frames of it after the stop) */
uint8_t bighit_red, bighit_slow;
uint16_t bighit_col;                                             /* its backdrop: the special's bd_col[0] (SS2 $2B9DE's colour:
                                                                    Hanzo's flame $0002, TODO #193), 0 = Haohmaru's red */
static void big_hit(fighter_t *a, fighter_t *v) {
    const bspec_t *sp = &a->ch->specials[a->spec_ix];
    a->freeze = BIGHIT_STOP; v->freeze = BIGHIT_HOLD;          /* SS2: the victim in its hit pose to the slash's end */
    bighit_red = BIGHIT_RED; bighit_slow = BIGHIT_STOP + BIGHIT_SLOW;
    bighit_col = sp->bd_end == 0 && sp->bd_col[0] ? sp->bd_col[0] : BIGHIT_COL;
}
/* ---- reactions -------------------------------------------------------------------------------------------------------- */
static void release(fighter_t *a);
static void special_end(fighter_t *f);
static void special_update(fighter_t *f);
static void fpose_pal(fighter_t *f, uint8_t on);
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
    uint8_t c0 = s[0], c1 = s[1];                                /* $2E = KOF96's fire hit (TODO #197: its kind 11 = */
    if (fx >> 6 && c0 != SFX_FIRE && c1 != SFX_FIRE) {           /* $13 + $1F, 21 = $1F alone: the Blitz Ball) */
        if (c0 >= SFX_HIT_A && c0 <= SFX_HIT_CD) c0 = SFX_FIRE;  /* a burning hit of another kind: the plain hit */
        else c1 = SFX_FIRE;                                      /* becomes the fire hit, a kind's own sound gets it */
    }
    snd_sfx(c0); if (c1) snd_sfx(c1);
}
/* burn (TODO #188 b, decoded from KOF98 in our emulator: Kyo's 623C on Terry / Yuri, VRAM + palette RAM every frame):
 * the burnt victim keeps its own frames and draws them, every part, with palette $F8 (orange) / $F9 (purple, Iori),
 * not its own: a 5-colour flame ramp repeated over pens 1-15 (pen k = ramp[(k - 1 - step) mod 5]), and a global task
 * (object $101100) copies the next step every 4 frames (the ROM's steps: palettes $3F0-$3F4 at $3FF5F0 orange, $400-
 * at $3FF7F0 purple; the cycle stops with the game in a super flash). Burnt through its hit reaction and its fall,
 * its own colours back at the floor (states 262 / 285 / 287 burnt, 309 not). Here: BURN_RAMP = step 0's pens 1-5; the
 * step = burn_clock / BURN_TICKS mod 5 (burn_clock: projectiles_update, once a frame outside the super flash); every
 * burnt fighter reloads its palettes when the step changes (burn_show). 0.0.92 and before showed the flames' own
 * palette $58 colour index for colour index (a static dark ramp: "looks nothing like Terry engulfed in flame") */
#define BURN_TICKS 4
static const uint16_t BURN_RAMP[2][5] = {
    { 0x1FDF, 0x1DAF, 0x796E, 0x065C, 0x7349 },                  /* 1 purple ($3FF7F0, Iori) */
    { 0x6FFC, 0x7FD6, 0x4FA3, 0x0E61, 0x0B30 } };                /* 2 orange ($3FF5F0) */
static uint8_t burn_step(void) { uint16_t t = burn_clock / BURN_TICKS; return t % 5; }
static void burn_show(fighter_t *f) {
    uint16_t pal[16];
    const uint16_t *r = BURN_RAMP[f->burn - 1];
    uint8_t i, k = 5 - burn_step();                              /* pen 1 = ramp[(0 - step) mod 5] */
    pal[0] = 0;
    for (i = 1; i < 16; i++) { if (k >= 5) k -= 5; pal[i] = r[k++]; }
    for (i = 0; i < f->ch->npal && i < MAX_PALS; i++) PAL_setPalette(f->palbase + i, pal);
    f->burn_t = burn_step();
}
static void set_burn(fighter_t *f, uint8_t burn) {
    if (f->burn == burn) return;
    f->burn = burn;
    if (f->flash) return;                                        /* white: its colours come back when the flash ends */
    if (!burn) { fighter_load_pals(f); return; }
    burn_show(f);
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
                                                             untinted path stays as cheap as before (the select screen calls it per colour) */
const uint16_t *fighter_src_pal(const fighter_t *f, uint8_t i) {
    return i == 0 && f->cpal ? f->cpal : f->ch->pals + ((f->set * f->ch->npal + i) << 4);
}
/* SS2's second-layer flicker (TODO #193, export_ss2 "the second layer's flicker"): Samurai Shodown II draws a step's
 * second layer with palette p and p + 1 on alternate frames (the object's +$82 = the frame counter's bit 0, $25D3E):
 * Hanzo's blade glints. The fighter's palette flk_ix shows its own colours on even frames of the burn clock (once a
 * frame, held in a super flash) and bchar_t.flk's on odd ones; a white flash or a burn owns the palettes meanwhile */
static void flicker(const fighter_t *f) {
    const bchar_t *ch = f->ch;
    uint16_t buf[16];
    const uint16_t *src;
    uint8_t j;
    if (ch->flk_ix == 0xFF || ch->flk_ix >= MAX_PALS || f->flash || f->burn || f->ovl) return;
    src = (burn_clock & 1) ? ch->flk + (f->set << 4) : fighter_src_pal(f, ch->flk_ix);
    buf[0] = src[0];
    for (j = 1; j < 16; j++) buf[j] = fighter_colour(f, src[j]);
    PAL_setPalette(f->palbase + ch->flk_ix, buf);
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
    v->kmode = v->kdelay = 0; v->kvfr = 0; v->ksr = 0;           /* the brawler's own physics (kof_react sets KOF's,
                                                                    src_react a source's) */
    if (v->state == S_DOWN) {                                    /* lying (only a down attack reaches it, TODO #218): */
        enter(v, S_KNOCKDOWN); play(v, BA_KNOCKDOWN_BOUNCE);     /* popped off the floor, DD's 119 (its header: 2 px a */
        v->vx = dir_mul(away, POP_VX); v->vy = POP_VY;           /* frame away, 4 up, gravity 0.375, friction 1/32, the */
        v->kg = v->kgf = POP_G; v->kgfr = 0; v->kvfr = 0xF800; v->kvmin = 0;   /* order of DD's handler 2: vy += g and */
        v->kmode = 2; return;                                    /* vx -= vx >> 5 before the move, kof_fall after it), */
    }                                                            /* then the brawler's bounce and get-up (DD: 71, 73, 75) */
    if (v->y > 0 && reaction <= R_HEAVY && dancing(v)) {         /* the dance's catch (TODO #150): an airborne victim a */
        enter(v, S_HITSTUN); play(v, reaction == R_LIGHT ? BA_HIT_STAND_LIGHT : BA_HIT_STAND_HEAVY);   /* fury's reel hits */
        v->vx = v->vy = 0; return;                               /* stops in its flight and drops to the floor in its reel */
    }                                                            /* (S_HITSTUN: DANCE_DROP), the dance rules from there */
    if (v->y > 0) {                                              /* hit in the air (a juggle when falling): sent up again */
        enter(v, S_KNOCKDOWN); v->vy = reaction >= R_KNOCKDOWN ? FIX(5) : FIX(4); v->vx = dir_mul(away, FIX(1) + 0x8000);
        play(v, reaction == R_SLAM ? BA_KNOCKDOWN_FLIGHT : BA_BLOWBACK); return;   /* KOF's hit_air ends on standing frames (KOF96: none) */
    }
    switch (v->hp <= 0 && !dancing(v) ? R_KNOCKDOWN : reaction) {   /* (a dance's reel: its finisher fells it) */
    case R_LIGHT: case R_HEAVY:
        enter(v, S_HITSTUN); play(v, reaction == R_LIGHT ? BA_HIT_STAND_LIGHT : BA_HIT_STAND_HEAVY);
        v->vx = dir_mul(away, FIX(push) >> 2);
        break;
    case R_KNOCKDOWN: case R_SLAM: enter(v, S_KNOCKDOWN); v->vy = FIX(7); v->vx = dir_mul(away, FIX(2)); play(v, blow); break;
    case R_LAUNCH: case R_LIFT: enter(v, S_KNOCKDOWN); v->vy = FIX(9); v->vx = dir_mul(away, FIX(2) + 0x8000); play(v, blow); break;   /* KOF98 launches rise in it too (Burn Knuckle) */
    case R_TRIP:      enter(v, S_KNOCKDOWN); v->vy = FIX(3); v->vx = dir_mul(away, FIX(1)); play(v, BA_TRIP); break;
    case R_BLOWBACK:  enter(v, S_KNOCKDOWN); v->vy = FIX(4); v->vx = dir_mul(away, FIX(5)); play(v, blow); break;   /* KOF's C+D: low and far */
    }
}

/* ---- hold and throws (TODO #146) ---------------------------------------------------------------------------------------
 * Walking into a standing opponent grabs it (combat; grabbable: its current state). The hold, Final Fight's rule: the
 * grabber holds the victim in its forward+C script's row 0 poses, the victim ALWAYS drawn behind the grabber, catch to
 * release (a row's flag 2 = a data override, game.json roster[].throws.front). A = a hold hit (bchar_t.holds: the
 * fighter's own blow with a 2-3 frame startup, a paired script like a throw), the third the finisher (it knocks the
 * victim down, the hold ends); hits keep the hold: the victim breaks free GRAB_TIME frames after the grab or after the
 * last hit ended, never during one (a held player may also mash ESCAPE_PRESSES buttons, counted from the last hit);
 * forward+A / back+A = the forward / reverse throw (KOF's forward+C / forward+D) at any time, in a hit too; C = a
 * special out of the hold. Enemies grab too (AI intent `grab`).
 * A throw or a hold hit is a PAIRED SCRIPT (bthrow_t, vocabulary hold.paired_script): per row the thrower's frame and
 * offset, the victim's posture (or a BA_* animation it plays: its flight) and offset from the thrower, impacts. The
 * thrower plays its rows up to the CONTROL RETURN row (bthrow_t.ret: the pilot's chosen from the throw's code,
 * tools/kof96/throwrom.py) and acts again; the victim plays its rows on alone (thrown_update) to its RELEASE row
 * (bthrow_t.rel), then it is the engine's knocked-down body (thrown_release: S_KNOCKDOWN with its script's velocity there;
 * no release row: to the end, then it lies down, S_DOWN). From the release to its landing it is a THROWN BODY (spawn.body,
 * tb_by): combat() knocks down every other enemy it touches, each once (BODY_DAMAGE, falling the throw's way). A throw's
 * damage is shared by its impact rows before the release (the landing is no impact: thrown_release). Postures are KOF's shared victim states; each fighter has its own frame for
 * them (bchar_t.vposes).
 * Revamp phase 3 (Bruno 2026-10-08, docs/brawler_feel.md 8h: no command-grab inputs ever; grab specials become throws;
 * with meter a throw becomes a super throw). A throw is invincible for its whole animation (the thrower: INV_FURY + cthrow
 * to its control return; a throw special: to its end) and its thrown body knocks others down (no chain credit). Beyond
 * forward / back + A, each fighter's throws are data (game.json roster[].throws -> bm_xthr[id], export_bm xthr_c):
 *   up / down + A in the hold: an extra throw (bxthr_t up / down): its paired throw_x (BT_XTHROW: a command grab decoded
 *     from its source's code, KOF98 Ralf's 426B) or a grab special's ROM program (role BS_THROW: the hold lets go, the
 *     victim reels where it stood and the special's catch takes it), no meter; none: the hold hit, as before;
 *   forward / back + C in the hold: the super throw with gmeter.sthrow meter (one stock): the fighter's strongest grab
 *     script (bxthr_t sup: a special played as a fury: its super flash, flash pose, invincibility; or its throw_x), else
 *     the throw pressed (XT_FWD) at the super tier with the super flash; damage gmeter.sthrow_dmg (a special's through
 *     dtier_rom's super scale); short of the meter: the plain throw (no life paid). C with up / down / no stick: the
 *     slot's special out of the hold, as before. */
#define GRAB_DX      32
#define GRAB_TIME    90               /* frames without a hit before the victim breaks free (~1.5 s, Final Fight) */
#define GRAB_HITS    3                /* hold hits; the third is the finisher */
#define GRAB_DAMAGE  3
#define THROW_DAMAGE 12
#define BODY_DAMAGE  6                /* a thrown body knocking another enemy down (TODO #146 rule 9) */
#define ESCAPE_PRESSES 4
#define THROW_FREEZE 21           /* KOF98 Ryo's forward+C: step 10 held 21 frames past its ticks (the only throw freeze
                                     among the roster's: every other throw step lasts its ROM ticks + 1, KOF96/98/99) */
enum { BT_HOLD_HIT = BT_COUNT, BT_HOLD_FIN, BT_XTHROW };        /* throw_id of a hold hit: bchar_t.holds[0] / [1]; the
                                                                    extra paired throw: bm_xthr[id].x (revamp 3) */
#define IS_THROW(id) ((id) < BT_COUNT || (id) == BT_XTHROW)        /* a throw (damage, voice, effect), not a hold hit */
#define IS_HOLD(id)  ((id) == BT_HOLD_HIT || (id) == BT_HOLD_FIN)
static const bbox_t BODY_BOX = { 0, -32, 32, 24 };              /* a thrown body as an attack box (centre, half extents) */

static const bthrow_t *thr_of(const fighter_t *f, uint8_t id) {
    return id < BT_COUNT ? &f->ch->throws[id] : id == BT_XTHROW ? bm_xthr[f->ch->id].x : &f->ch->holds[id - BT_COUNT];
}
/* a hold hit's move (bthrow_t.hanim: game.json roster[].throws.hold, default the fastest close normal; TODO #166 c) and
 * the attack box of its active step (hstep), which hits the crowd around the held victim (combat, "hold crowd") */
static uint8_t hold_anim(const fighter_t *a) {
    const bthrow_t *th = thr_of(a, a->throw_id);
    return th->hanim != 0xFF ? th->hanim : a->throw_id == BT_HOLD_FIN ? BA_ATK_D_CLOSE : BA_ATK_C_CLOSE;
}
static const bbox_t *hold_box(const fighter_t *a) {
    const bthrow_t *th;
    const bstep_t *st;
    if (a->throw_id < BT_COUNT) return 0;
    th = thr_of(a, a->throw_id);
    if (th->hanim == 0xFF || th->hstep >= a->ch->anims[th->hanim].nsteps) return 0;
    st = &a->ch->anims[th->hanim].steps[th->hstep];
    return (st->flags & 1) ? &st->atk : 0;
}
static void hold_spark(fighter_t *a, fighter_t *v);
/* a hold script's impacts (rows with flag 4): their count, and the last one's row (0xFFFF none). A finisher with
 * several (game.json throws.hold.multi: Kim's $6E, two kicks) reels the victim at each and knocks it down only at the
 * last; its damage is shared: damage / n at each earlier one, the rest at the knockdown (the total unchanged) */
static uint8_t hold_nimp(const bthrow_t *th) {
    uint8_t n = 0; uint16_t i;
    for (i = 0; i < th->nrows; i++) if (th->rows[i].flags & 4) n++;
    return n;
}
static uint16_t hold_last(const bthrow_t *th) {
    uint16_t i = th->nrows;
    while (i--) if (th->rows[i].flags & 4) return i;
    return 0xFFFF;
}
static void show_pose(fighter_t *v, const bthrow_row_t *r) {
    if (r->flags & 32) {                                         /* a brawler animation (its flight, a hold hit's reel) */
        v->frame_ovr = 0xFFFF;
        if (r->flags & 4) play(v, r->vpose); else play_if_new(v, r->vpose);   /* an impact restarts it */
        return;
    }
    {
        uint16_t fr = r->vpose < VP_COUNT ? v->ch->vposes[r->vpose] : 0xFFFF;
        if (fr != 0xFFFF) v->frame_ovr = fr;
        else { v->frame_ovr = 0xFFFF; play_if_new(v, BA_HIT_STAND_LIGHT); }   /* no frame for it: the light hit pose */
    }
}
static void place_at(fighter_t *v, int32_t x, int32_t y, int32_t z, int8_t face, const bthrow_row_t *r) {
    v->vx = x - v->x;                                            /* its motion: a thrown body knocks others its way */
    v->x = x; v->y = y + FIX(r->vy); if (v->y < 0) v->y = 0;
    v->z = z;
    v->facing = (r->flags & 1) ? face : -face;
    v->zfront = (r->flags & 2) != 0;                             /* behind the grabber unless the data says otherwise */
}
static void thrown_place(fighter_t *v, const bthrow_row_t *r) {   /* a thrown victim's place from the throw's origin */
    place_at(v, v->throw_x0 + dir_mul(v->throw_face, FIX(r->tx + r->vx)), FIX(r->ty), v->z, v->throw_face, r);
    clamp(v);
}
static void place_victim(const fighter_t *a, fighter_t *v, const bthrow_row_t *r, int8_t face) {   /* face: the */
    place_at(v, a->x + dir_mul(face, FIX(r->vx)), a->y, a->z, face, r);   /* thrower's facing the offsets are in */
}
/* the thrower's hold pose: its forward throw's first frame, or its own (bthrow_t.gframe: SS2's grab is drawn turned
 * with the victim swapped behind; the brawler's hold is that picture mirrored, both kept as they met, TODO #188 a) */
static uint16_t grab_frame(const fighter_t *a) {
    const bthrow_t *th = &a->ch->throws[BT_THROW_C];
    return th->gframe != 0xFFFF ? th->gframe : th->rows->tframe;
}
static void grab(fighter_t *a, fighter_t *v) {
    const bthrow_row_t *h = a->ch->holds[0].rows;                /* the victim's pose: the hold hit's first row */
    enter(a, S_GRAB); a->held = v; a->target = v; a->grab_hits = 0; a->srow = 0; a->zfront = 1; a->buffered = 0; a->xwait = 0;
    a->spec_buf = a->fury_buf = 0; a->cnc_buf = 0;               /* (presses before the hold: not for it) */
    a->frame_ovr = grab_frame(a);                                /* silent: the throw's sound comes with its start (#166) */
    if (a->team) stat_grabs++;
    enter(v, S_GRABBED); v->held = a; v->vx = v->vy = v->vz = 0; v->grab_hits = 0; v->thr = 0;   /* victim: presses mashed */
    show_pose(v, h); place_victim(a, v, h, a->facing);
}
static void release(fighter_t *a) {                              /* both free where they stand */
    fighter_t *v = a->held;
    a->held = 0; a->frame_ovr = 0xFFFF; a->zfront = 0; a->y = 0; a->srow = 0; a->xwait = 0; to_neutral(a, 0);
    if (v) { v->held = 0; v->thr = 0; v->frame_ovr = 0xFFFF; v->zfront = 0; to_neutral(v, 0); }
}
static void victim_end(fighter_t *v) {                           /* its script over: it lies where it landed */
    const bthrow_t *th = v->thr;
    if (th && th->stun && IS_THROW(v->throw_id)) {              /* a stun strike (bthrow_t.stun, TODO #212: Double */
        v->held = 0; v->thr = 0; v->frame_ovr = 0xFFFF; v->zfront = 0; v->vx = 0; v->y = 0; clamp(v);   /* Dragon's */
        enter(v, S_HITSTUN); play(v, BA_HIT_STAND_HEAVY);        /* Cheng-Fu, $23B74: no damage, the victim stands */
        v->dizzy = th->stun;                                     /* dizzy, its +$FE frames, open to any hit; a hit ends */
        return;                                                  /* it: enter) */
    }
    if (IS_THROW(v->throw_id)) {
        uint8_t d = v->thr_dmg - v->throw_dealt;
        v->hp -= d;
        if (v->thr_by) gauge_add(v->thr_by, (uint16_t)d * gmeter.fury_dealt);   /* (the fury gauge, "the meter") */
        gauge_add(v, (uint16_t)d * gmeter.fury_taken);
    }
    v->held = 0; v->thr = 0; v->frame_ovr = 0xFFFF; v->zfront = 0; v->vx = 0; v->y = 0; clamp(v);
    enter(v, S_DOWN); play(v, BA_DOWN);
}
/* THE RELEASE (Bruno 2026-10-08, every throw: "as soon as the victim goes out of the hands, give it back to the regular
 * physics of the engine"): a throw's script for its victim ends at its release row (bthrow_t.rel): from there it is an
 * ordinary knocked-down body (S_KNOCKDOWN with the velocity its script had at the release: it flies, lands, bounces,
 * lies and gets up as any knockdown), a thrown body (tb_by, spawn.body) until it touches the floor. Its impact rows
 * after the release (the landing) are no impacts any more: the throw's damage is shared by its impacts before the
 * release; a throw whose only impacts came after it (the landing: Ryo's / Geese's back throw, Billy Lee's) has its
 * release row as its impact. impacts_before: the impact rows before the release (all of them without one). */
static uint16_t impacts_before(const bthrow_t *th) {
    uint16_t i, n = 0, end = th->rel < th->nrows ? th->rel : th->nrows;
    for (i = 0; i < end; i++) if (th->rows[i].flags & 4) n++;
    return n;
}
static uint8_t thr_impact(const bthrow_t *th, uint16_t i, uint8_t moved) {   /* moved: the release is the impact */
    if (th->rel == 0xFFFF || i < th->rel) return (th->rows[i].flags & 4) != 0;
    return i == th->rel && moved;
}
static uint8_t release_moved(const bthrow_t *th) {             /* its landing impact moves onto the release row */
    uint16_t i;
    if (th->rel == 0xFFFF || impacts_before(th)) return 0;
    for (i = th->rel; i < th->nrows; i++) if (th->rows[i].flags & 4) return 1;
    return 0;
}
/* its launch: the engine's knockdown velocity that lands it where and when the script did (its landing row, else its
 * last), from where it is at the release: vx = the distance / the flight's frames, vy = the gravity's (GRAVITY_KD) for that
 * flight from that height. (The script's own speed at the release row overshoots: Terry's forward throw left at 10 px a
 * frame, a 600 px flight under the knockdown's gravity, which has no air drag; KOF's throw flights slow down.) */
static void thrown_release(fighter_t *v, const bthrow_t *th) {
    uint16_t le = th->land < th->nrows && th->land > th->rel ? th->land : th->nrows - 1;   /* its landing row */
    const bthrow_row_t *r = &th->rows[th->rel], *e = &th->rows[le];
    int16_t dx = (e->tx + e->vx) - (r->tx + r->vx), y0 = r->ty + r->vy;   /* px */
    uint16_t t = le > th->rel ? div16((uint32_t)(le - th->rel) << 8, th->speed ? th->speed : 0x100) : 1;   /* its flight, frames */
    int32_t vx, vy;
    if (!t) t = 1;
    vx = (int32_t)div16((uint32_t)(dx < 0 ? -dx : dx) << 8, t) << 8; if (dx < 0) vx = -vx;   /* (16.16; divu.w, mulu.w: */
    vy = (int32_t)((uint32_t)t * (uint16_t)(GRAVITY_KD >> 1));                              /*  no libgcc) */
    if (y0 > 0) vy -= (int32_t)div16((uint32_t)y0 << 8, t) << 8;
    if (IS_THROW(v->throw_id) && v->thr_dmg > v->throw_dealt) {  /* (the impacts' division's rest) */
        uint8_t d = v->thr_dmg - v->throw_dealt;
        v->hp -= d; v->throw_dealt += d;
        if (v->thr_by) gauge_add(v->thr_by, (uint16_t)d * gmeter.fury_dealt);
        gauge_add(v, (uint16_t)d * gmeter.fury_taken);
    }
    thrown_place(v, r);
    v->held = 0; v->thr = 0; v->zfront = 0;
    enter(v, S_KNOCKDOWN);
    v->vx = dir_mul(v->throw_face, vx); v->vy = vy;
    if (v->frame_ovr != 0xFFFF || (v->anim != BA_BLOWBACK && v->anim != BA_BLOWBACK_N && v->anim != BA_KNOCKDOWN_FLIGHT)) {
        v->frame_ovr = 0xFFFF; play(v, v->vy > 0 ? BA_BLOWBACK : BA_KNOCKDOWN_FLIGHT);
    }
    if (v->thr_by && v->thr_by != v) v->tb_by = v->thr_by;       /* a thrown body until it lands (combat) */
}
/* the victim's side of rows j..i (passed or reached this frame): postures, impacts (damage, sound, spark, freeze);
 * returns bit 0 when an impact was passed, bit 1 when the victim was released (it is no longer in the script), bit 2
 * when a hold finisher's last impact was passed (its knockdown) */
static uint8_t victim_rows(fighter_t *v, const bthrow_t *th, uint16_t j, uint16_t i) {
    fighter_t *by = v->thr_by;
    uint8_t hit = 0, moved = IS_THROW(v->throw_id) && release_moved(th);
    if (i >= th->nrows) i = th->nrows - 1;
    if (IS_THROW(v->throw_id) && th->rel != 0xFFFF && i > th->rel) i = th->rel;
    for (; j <= i; j++) {
        const bthrow_row_t *r = &th->rows[j];
        if (r->vpose != 0xFF) show_pose(v, r);                   /* a pose set on a passed row still applies */
        if (IS_THROW(v->throw_id) ? !thr_impact(th, j, moved) : !(r->flags & 4)) continue;
        hit = 1;                                                 /* impact: the blow lands / the victim hits the floor */
        if (IS_HOLD(v->throw_id)) {                              /* a hold hit: the victim reels in place */
            if (by) { by->impact = 1; hold_spark(by, v); }       /* its spark; its box hits the crowd (combat) */
            {
            uint8_t dmg = GRAB_DAMAGE;
            if (v->throw_id == BT_HOLD_FIN) {                    /* the finisher: its thrower knocks it down at its */
                if (j == hold_last(th)) { hit |= 4; continue; }  /* last impact; an earlier one reels it in place */
                dmg = by ? NODE(by, TREE(by)->hold)->damage / hold_nimp(th) : 0;   /* (its share, hold_nimp) */
            }
            v->hp -= dmg; v->grab_hits = 0;                      /* a hit: the escape count starts again */
            if (by) gauge_add(by, dmg * gmeter.fury_dealt);      /* (the fury gauge, "the meter") */
            gauge_add(v, dmg * gmeter.fury_taken);
            }
            if (by) {                                            /* its sound: a button's (bthrow_t.hsfx, Terry's kick */
                uint8_t hx = thr_of(by, by->throw_id)->hsfx;     /* sounds as a punch: Bruno 2026-10-08) or its move's */
                uint8_t k, n = 0, s;                             /* (its own for this impact first: own_sound) */
                for (k = 0; k < j; k++) if (th->rows[k].flags & 4) n++;
                s = own_sound(by, HS_HOLD + by->throw_id - BT_HOLD_HIT, n);
                if (s) snd_sfx(s); else
                snd_sfx(hx ?(by->ch->sfx[hx - 1] ? by->ch->sfx[hx - 1] : SFX_HIT_A + hx - 1) : hit_sound(by, hold_anim(by), 0));
                by->freeze = 4;
            }
            v->freeze = 4;
            continue;
        }
        {
            uint8_t d = 0, rest = v->thr_dmg;                    /* its damage / impacts (no divide here) */
            while (v->grab_hits && rest >= v->grab_hits) { rest -= v->grab_hits; d++; }
            v->hp -= d; v->throw_dealt += d;
            if (by) gauge_add(by, (uint16_t)d * gmeter.fury_dealt);   /* (the fury gauge, "the meter") */
            gauge_add(v, (uint16_t)d * gmeter.fury_taken);
        }
        if (!mute && v->hp > 0) voice_play(v->ch, v->team, VK_HIT);   /* the KO voice: at the death (S_DEAD) */
        if (r->flags & 16) { v->freeze = THROW_FREEZE; if (by && by->held == v) by->freeze = THROW_FREEZE; }   /* only where KOF froze (Ryo's forward+C) */
        if (by) { uint8_t sx = SX_THROW_C + (v->throw_id == BT_XTHROW ? 0 : v->throw_id);   /* (the extra throw: C's) */
            snd_sfx(by->ch->sfx[sx] ? by->ch->sfx[sx] : SFX_HIT_CD); }   /* Krauser's back breaker: $3D */
        spark_hit(INT(v->throw_x0) + dir_mul(v->throw_face, r->vx + r->tx), floor_top + INT(v->z) - r->ty - r->vy - 40, 1, v->throw_face);
    }
    v->srow = i + 1;
    if (IS_THROW(v->throw_id) && th->rel != 0xFFFF && i == th->rel) { thrown_release(v, th); return hit | 2; }
    return hit;
}
static void start_node(fighter_t *f, uint8_t node, uint8_t how);
static uint8_t special_for(const fighter_t *f, const intent_t *in);
static uint8_t special_pick(const fighter_t *f, uint8_t want);
static uint8_t fury_cancel(fighter_t *f);
static void start_special(fighter_t *f, uint8_t k);
/* script rows (specials, throws): one row = one frame at 1x; f->srow = the row shown + 1, f->acc the time in it.
 * Advanced by f->speed like the animation player; stop(row) = a row the advance must not pass (a special's hit
 * row with its box live or opening a hit, its continuation point): it stops there. Returns the first row newly shown (rows from it to srow - 1 were
 * passed or reached this frame). */
static uint16_t part_end(const fighter_t *f, const bspec_t *sp) { return sp->nparts ? sp->parts[f->spart].end : sp->nrows; }
static uint16_t script_advance(fighter_t *f, uint16_t nrows, const bspec_t *sp) {
    uint16_t from = f->srow, end = sp ? part_end(f, sp) : nrows;
    if (!f->srow) { f->srow = 1; f->acc = 0; return 0; }         /* its first frame: row 0 */
    f->acc += f->speed;
    while (f->acc >= 0x100) {
        f->acc -= 0x100; f->srow++;
        if (f->srow > end) break;                                /* past its part: special_update goes on */
        if (sp && (sp->rows[f->srow - 1].hit & 3)) {
            if (f->acc >= 0x100) f->acc = 0xFF;                  /* a live row: shown */
            break;
        }
    }
    return from;
}
/* a paired script's frame, the thrower's side (a throw: S_THROW; a hold hit: S_GRAB with srow set). Rows advance at
 * the script's speed (bthrow_t.speed, 8.8; per throw in data); an impact row passed over still lands on the frame that
 * passes it. The attached victim follows (victim_rows, placed from the thrower). Returns 0 once the thrower's part is
 * over (its control return row reached). */
static uint8_t paired_update(fighter_t *f) {
    const bthrow_t *th = thr_of(f, f->throw_id);
    fighter_t *v = f->held;
    const bthrow_row_t *r;
    uint16_t j = script_advance(f, th->nrows, 0), i = f->srow - 1;
    if (IS_THROW(f->throw_id)) voice_at(f, VK_THROW + (f->throw_id == BT_XTHROW ? 0 : f->throw_id), j, i);
    if (IS_THROW(f->throw_id) && th->fx_row != 0xFFFF && th->fx_row >= j && th->fx_row <= i && !mute) {   /* the throw
                                                                    starts: KOF96/98's effect + its sound (#166 a) */
        throw_fx(INT(f->throw_x0) + (f->throw_face > 0 ? th->fx_dx : -th->fx_dx), floor_top + INT(f->z) - th->fx_dy, f->throw_face);
        snd_sfx(SFX_THROW);
    }
    if (v && v->held == f) {
        uint8_t hit = victim_rows(v, th, j, i);
        if (hit & 2) { f->held = 0; v = 0; }                    /* released: the engine's knockdown from here */
        else if ((hit & 1) && ((hit & 4) || v->hp <= 0)) { /* the finisher's last impact lands, or a hold hit took the last life
                                                                    (TODO #204: held on, it broke free standing with none,
                                                                    and nothing could hit or grab it): the victim goes */
            uint8_t fin = f->throw_id == BT_HOLD_FIN;            /* down, the hold is over */
            uint8_t n = fin ? hold_nimp(th) : 1, dm = fin ? NODE(f, TREE(f)->hold)->damage : 0;
            f->held = 0; v->held = 0; v->thr = 0; v->frame_ovr = 0xFFFF; v->zfront = 0; enter(v, S_IDLE);
            if (fin) { uint8_t s = own_sound(f, HS_HOLD + BT_HOLD_FIN - BT_HOLD_HIT, n - 1);   /* (a hold hit's sound and */
                snd_sfx(s ? s : hit_sound(f, hold_anim(f), 1)); }                              /* damage: already dealt) */
            fighter_hit(f, v, dm - (n > 1 ? (n - 1) * (dm / n) : 0), R_KNOCKDOWN, 0);   /* (the rest of its damage) */
            v = 0; enter(f, S_THROW);                            /* its follow-through plays on (srow kept): a normal
                                                                    hit, cancellable into a special / the fury (#166 d) */
        } else if (i >= th->nrows && IS_THROW(f->throw_id)) { victim_end(v); f->held = 0; v = 0; }   /* (a hold hit: held on) */
    }
    if (i >= th->ret) {                                          /* the control return: the victim still in the script */
        if (v && i < th->nrows) thrown_place(v, &th->rows[i]);   /* shows this row's place with its pose, then plays on */
        return 0;                                                /* alone from it (throw_free); unplaced, it held last */
    }                                                            /* row's place a frame: a hitch in its flight (#196) */
    r = &th->rows[i];
    f->frame_ovr = r->tframe;
    f->x = f->throw_x0 + dir_mul(f->throw_face, FIX(r->tx)); f->y = FIX(r->ty);
    f->facing = (r->flags & 8) ? -f->throw_face : f->throw_face;   /* turned around in the game (Terry's reverse throw) */
    if (v) place_victim(f, v, r, f->throw_face);
    return 1;
}
/* the fury a D press buys (down: down+D; "the meter"): the MAX (bchar_t.fury_max; none: the fury played as the MAX) in
 * the red state, else the fury; a fury playing cancels only into its MAX ("cancels" rule 3). Pays (dry: only whether
 * it could) -> BS_FURY / BS_FURY_MAX, 0xFF: nothing (no fury, not payable) */
static uint8_t fury_buy(fighter_t *f, uint8_t down, uint8_t dry) {
    uint8_t k = spec_ix(f->ch, BS_FURY) == 0xFF || (f->state == S_SPECIAL && f->spec_id == BS_FURY) ? 0xFF :
                down ? BS_FURY_MAX : BS_FURY;                     /* (Bruno 2026-10-09: D = the fury, down+D = the MAX) */
    if (k == 0xFF || !pay(f, k == BS_FURY_MAX ? PAY_MAX : PAY_FURY, dry)) return 0xFF;
    return k;
}
/* D pressed from neutral or in a hold (TODO #208: one rule): down+D with a full meter: the form link's transition when
 * the fighter's trigger is FT_DOWN_D_FULL (all of the meter); else fury_buy. -> the role to start (BS_FORM / BS_FURY /
 * BS_FURY_MAX), paid; 0xFF: nothing */
static uint8_t fury_press(fighter_t *f, uint8_t max) {         /* max: down held (down+D) */
    if (max && f->ch->form_trig == FT_DOWN_D_FULL && spec_ix(f->ch, BS_FORM) != 0xFF && pay(f, PAY_FORM, 0)) return BS_FORM;
    return fury_buy(f, max, 0);
}
static void throw_start(fighter_t *f, uint8_t t) {               /* forward+A / back+A in the hold (any BT_*: the extra */
    fighter_t *v = f->held;                                      /* paired throw too, revamp 3) */
    const bthrow_t *th;
    if (t < BT_COUNT && !f->ch->throws[t].nrows) t = BT_THROW_C;
    th = thr_of(f, t);
    f->throw_id = t; f->throw_x0 = f->x; f->throw_face = f->facing; enter(f, S_THROW); f->srow = 0; f->speed = th->speed; f->zfront = 1;
    enter(v, S_THROWN); v->throw_id = t; v->thr = th; v->thr_by = f; v->throw_x0 = f->x; v->throw_face = f->facing;
    v->srow = 0; v->speed = th->speed; v->hit_mask = 0; v->grab_hits = 0; v->throw_dealt = 0; v->thr_skip = 0;
    f->spec_buf = f->fury_buf = 0; f->cnc_buf = 0;              /* (a press before it: not for its cancel) */
    v->thr_dmg = THROW_DAMAGE;                                   /* (the super throw: its tier, super_throw) */
    f->inv = INV_FURY; f->cthrow = 1;                            /* invincible to its control return (revamp 3: every
                                                                    throw, as the chain's back throw was) */
    v->grab_hits = impacts_before(th);                           /* its impacts share the throw's damage (the release */
    if (!v->grab_hits && release_moved(th)) v->grab_hits = 1;    /* rule: those before it, else the release row) */
    if (f->team) stat_throws++;
    paired_update(f);                                            /* its first row now */
}
static uint8_t pend_sthr;          /* the next start_special plays a throw's special (fighter_t.sthr; its index: xix) */
/* the hold lets go into a special (role k; sthr: a throw's, revamp 3, its special xix): the victim reels in its held
 * pose, free (only throws hold a victim), until its stun ends or the move hits it */
static void hold_special(fighter_t *f, uint8_t k, uint8_t sthr, uint8_t xix) {
    fighter_t *v = f->held;
    f->held = 0; f->frame_ovr = 0xFFFF; f->zfront = 0; f->y = 0; f->buffered = 0; f->srow = 0;
    v->held = 0; v->zfront = 0; v->vx = v->vy = v->vz = 0; v->y = 0;
    enter(v, S_HITSTUN); play(v, BA_HIT_STAND_LIGHT);            /* STUN_LIGHT frames; frame_ovr: the held pose */
    lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, k == BS_FURY_MAX ? BS_FURY : k);
    pend_sthr = sthr; f->xix = xix; start_special(f, k);
}
/* the super throw (revamp 3) is DROPPED (Bruno 2026-10-08): hold + forward / back + C = the normal throw pressed, for
 * everyone (bm_xthr sup and tiers.super_throw stay in the data, unused; Rugal / Yamazaki / Genjuro keep their grab fury on
 * D: fury_grab) */
static void hold_update(fighter_t *f, const intent_t *in) {
    fighter_t *v = f->held;
    if (f->srow && f->throw_id == BT_HOLD_FIN && !f->team) {     /* the finisher on its way: C / D are buffered */
    } else if ((in->press & IN_C) || (f->fury_buf & 0x80)) {     /* (fighter_update, "cancels" rule 4); else C: the hold
                                                                    ends, the special at once (Bruno 2026-10-05); D (its
                                                                    press kept through a hold hit's hit-stop: fury_buf,
                                                                    fighter_update): the fury (down+D its MAX) as from
                                                                    neutral, fury_press (TODO #208, every fighter); the
                                                                    victim reels in its held pose, free (only throws hold
                                                                    a victim), until its stun ends or the move hits it */
        uint8_t d = (f->fury_buf & 0x80) != 0, k;
        if (!d && in->dx) { f->fury_buf = 0; throw_start(f, in->dx == f->facing ? BT_THROW_C : BT_THROW_D); return; }   /* forward /
                                                                    back + C: the normal throw (the super throw dropped) */
        k = d ? fury_press(f, f->fury_buf & 1) : special_for(f, in);
        f->fury_buf = 0;
        if (k != 0xFF && (d || pay(f, PAY_SPECIAL, 0))) {
            hold_special(f, k, 0, 0);
            if (!d && !f->team) { f->sinv = 1; f->inv = INV_FURY; }   /* (a C special: invincible, cspecial's rule) */
            return;
        }
    }
    if ((in->press & IN_A) && in->dx) {                          /* forward+A / back+A: throw forward / backward, at */
        throw_start(f, in->dx == f->facing ? BT_THROW_C : BT_THROW_D);   /* any time (a hold hit playing too) */
        return;
    }
    if ((in->press & IN_A) && in->dz) {                          /* up / down + A: the extra throw, when it has one */
        const bxthr_t *x = &bm_xthr[f->ch->id];                  /* (revamp 3; none: the hold hit below) */
        uint8_t e = in->dz < 0 ? x->up : x->down;
        if (e == XT_PAIRED && x->x) { throw_start(f, BT_XTHROW); return; }
        if (e < f->ch->nspec) { hold_special(f, BS_THROW, 1, e); return; }
    }
    if (f->srow) {                                               /* a hold hit playing (its paired script): an A now */
        if (in->press & IN_A) f->buffered = 1;                   /* is the next hit, as soon as this one ends */
        if (paired_update(f)) return;
        if (f->state != S_GRAB) {                                /* the finisher's follow-through ended: free */
            f->held = 0; f->frame_ovr = 0xFFFF; f->zfront = 0; f->y = 0; f->srow = 0; to_neutral(f, 0); return;
        }
        f->srow = 0; f->state_t = 0;                             /* back to the hold; the escape time starts again */
        f->x = f->throw_x0; f->y = 0; f->facing = f->throw_face;
        f->frame_ovr = grab_frame(f); show_pose(v, f->ch->holds[0].rows); place_victim(f, v, f->ch->holds[0].rows, f->facing);
        if (!f->buffered) return;
    }
    if (((in->press & IN_A) || f->buffered) && f->grab_hits < GRAB_HITS) {   /* A: a hold hit, the third the finisher */
        f->buffered = 0; f->grab_hits++; f->spec_buf = f->fury_buf = 0;
        f->hit_mask = 1 << v->idx;                               /* the crowd rule: each other enemy once per hit */
        f->throw_id = f->grab_hits >= GRAB_HITS ? BT_HOLD_FIN : BT_HOLD_HIT;
        f->throw_x0 = f->x; f->throw_face = f->facing; f->speed = thr_of(f, f->throw_id)->speed;
        v->throw_id = f->throw_id; v->thr_by = f; v->throw_x0 = f->x; v->throw_face = f->facing;
        paired_update(f);                                        /* its first row now */
        return;
    }
    if (f->state_t >= GRAB_TIME) {                               /* the victim breaks free */
        release(f); v->x += dir_mul(f->facing, FIX(10)); clamp(v); v->inv = 20;
    }
}
/* the chain's back throw (revamp 1A, "chain core"): the victim the link before hit (target), reeling on the ground within
 * reach, is grabbed where it stands and thrown backwards: the fighter's throw whose victim ends behind it (its last row's
 * place: BT_THROW_D first, KOF's forward+D / a reverse throw, then BT_THROW_C), else its throw played mirrored (the
 * thrower turned away: the victim goes over to its back at the grab); a stun strike (bthrow_t.stun, Cheng-Fu's) is no
 * throw. The thrower is untouchable (INV_FURY, cthrow) until the throw's control return; the chain is over (no credit
 * from the throw nor from its thrown body). No throw / no victim in reach: the neutral finisher (chain_next). */
#define CTHROW_DX 96              /* px: the farthest victim the back throw takes (a chain's push leaves it 40-70 px ahead) */
static uint8_t cthrow_pick(const bchar_t *ch, uint8_t *mirror) {   /* -> BT_* (0xFF none); mirror: play it turned */
    uint8_t t, first = 0xFF;
    for (t = BT_THROW_D + 1; t-- > 0;) {                         /* (D, then C) */
        const bthrow_t *th = &ch->throws[t];
        const bthrow_row_t *r;
        if (!th->nrows || th->stun) continue;
        if (first == 0xFF) first = t;
        r = &th->rows[th->nrows - 1];
        if (r->tx + r->vx < 0) { *mirror = 0; return t; }       /* its victim ends behind the thrower */
    }
    *mirror = 1; return first;
}
static uint8_t throw_ok(const fighter_t *f) {
    const fighter_t *v = f->target;
    int16_t dx, dz;
    uint8_t m;
    if (!v || v->team == f->team || v->state != S_HITSTUN || v->hp <= 0 || v->y || v->held || v->inv || dancing(v)) return 0;
    if (!f->ch->throws[BT_THROW_C].nrows || cthrow_pick(f->ch, &m) == 0xFF) return 0;   /* (no throw; the hold needs C's) */
    dx = INT(v->x) - INT(f->x); dz = INT(v->z) - INT(f->z);
    return dx >= -CTHROW_DX && dx <= CTHROW_DX && dz >= -Z_HIT && dz <= Z_HIT;
}
static void chain_throw(fighter_t *f, uint8_t node, uint8_t how) {
    fighter_t *v = f->target;
    uint8_t m, t = cthrow_pick(f->ch, &m);
    lab_note(f, LE_START, node, how, 0);
    f->freeze = v->freeze = 0; f->facing = v->x >= f->x ? 1 : -1;
    grab(f, v);
    if (m) f->facing = -f->facing;                               /* mirrored: its forward throw sends the victim behind */
    throw_start(f, t);
    f->inv = INV_FURY; f->cthrow = 1; f->node = 0; f->chain_t = 0; f->buffered = 0;
}
/* the thrower lets go (its control return, or a cancel): a victim still in its script plays its rows on alone
 * (thrown_update) from the row shown; done: this frame's row already played (paired_update), else it plays it itself */
static void throw_free(fighter_t *f, uint8_t done) {
    fighter_t *v = f->held;
    if (v && v->held == f) {                                     /* its part goes on: row, time, speed */
        v->held = 0; v->thr_pos = ((uint32_t)(f->srow - 1) << 8) + f->acc; v->speed = f->speed;
        v->thr_skip = done && v->idx > f->idx;                   /* it updates later this frame: not twice */
    }
    f->held = 0; f->frame_ovr = 0xFFFF; f->zfront = 0; f->y = 0; f->srow = 0; clamp(f);
}
static uint8_t cancel_pick(fighter_t *f);
static uint16_t last_impact(const bthrow_t *th) {               /* a throw's cancel row ("cancels" rule 4): its last */
    uint16_t i = th->nrows, last = 0xFFFF;                       /* impact row before the control return (the blow: */
    uint8_t moved = release_moved(th);                           /* (the release rule's impacts) */
    while (i--) if (thr_impact(th, i, moved)) {                     /* Terry's / Geese's victim lands after it, a cancel */
        if (i < th->ret) return i;                               /* there would come from neutral, feedback */
        if (last == 0xFFFF) last = i;                            /* 20261006-194211-5d29), else its last impact row; */
    }                                                            /* 0xFFFF none (Yamazaki's back throw) */
    return last;
}
/* the juggle window ("cancels" rule 5): a throw's impact / a catch's slam cancelled into a special or fury opens it on
 * that victim, for the canceller's follow-up only (combat: hittable while thrown or airborne, until it lands) */
static void juggle_open(fighter_t *f, fighter_t *v) { if (v && v != f && v->team != f->team) v->jug_by = f; }
/* the thrower's side after the grab (TODO #146): the paired script up to the control return, then it acts again; a
 * throw's last impact / the hold finisher's landing cancel ("cancels" rule 4) */
static void cancel_go(fighter_t *f, uint8_t k) {                /* a throw's buffered C / D (cancel_pick's role): the fury, or
                                                                    a C special (invincible: cspecial) */
    if (k == BS_FURY || k == BS_FURY_MAX) start_special(f, k); else cspecial(f, k);
}
static void throw_update(fighter_t *f, const intent_t *in) {
    uint8_t k;
    fighter_t *jv;
    (void)in;
    if (!f->team && (f->fury_buf || f->spec_buf) &&               /* the impact shown (srow: the row shown + 1): */
        (f->throw_id == BT_HOLD_FIN ? !f->held : IS_THROW(f->throw_id) && f->srow > last_impact(thr_of(f, f->throw_id))) &&
        (k = cancel_pick(f)) != 0xFF) {                          /* a buffered C / D fires now */
        juggle_open(f, f->held ? f->held : f->target);           /* rule 5: its follow-up may hit the victim in flight */
        throw_free(f, 0); lab_note(f, LE_SPECIAL, 0, LH_CANCEL, k); cancel_go(f, k); return;
    }
    if (paired_update(f)) return;
    jv = f->held ? f->held : f->target;
    throw_free(f, 1);
    if (!f->team && (f->fury_buf || f->spec_buf) && (IS_HOLD(f->throw_id) || last_impact(thr_of(f, f->throw_id)) != 0xFFFF) &&
        (k = cancel_pick(f)) != 0xFF) {                          /* the control return before the last impact (a throw
                                                                    whose only impact comes after it): the press fires */
        juggle_open(f, jv); lab_note(f, LE_SPECIAL, 0, LH_CANCEL, k); cancel_go(f, k); return;
    }
    f->spec_buf = f->fury_buf = 0; f->cnc_buf = 0; to_neutral(f, 0);
}
static void thrown_update(fighter_t *v) {                        /* a thrown victim whose thrower let go */
    const bthrow_t *th = v->thr;
    uint16_t j, i;
    if (!th || v->held) return;                                  /* its thrower plays it */
    if (v->thr_skip) { v->thr_skip = 0; return; }
    j = v->srow; v->thr_pos += th->speed; i = v->thr_pos >> 8;   /* (v->srow: the row shown + 1, victim_rows) */
    if (j > i) return;
    if (victim_rows(v, th, j, i) & 2) return;                    /* released: the engine's knockdown from here */
    if (i >= th->nrows) { victim_end(v); return; }
    thrown_place(v, &th->rows[i]);
}

/* ---- specials ------------------------------------------------------------------------------------------------------------
 * D: the fighter's first ground special, forward+D (any direction held: the fighter faces it) the second (export_bm.py
 * picks them), played from the per-frame script captured in the game: fighter frame + offset, body attack box (KOF's,
 * from the move's own animation) and up to two objects (effects: pool entities with their frame, offset and facing, no
 * box); a projectile is an entity of its own (bspec_t.proj, see "projectiles" below). Per row hit bits (export_bm special_rows): a row opening a new hit lets the same
 * targets be hit again, with its damage (SPECIAL_DAMAGE split over the move's hits) and the victim's reaction measured
 * in the game (bits 5-7: R_HEAVY keeps it on the ground until the part that ejects it); contact rows (a running grab's
 * reach) only catch the victim.
 * Follow-ups (one mechanism, data: bspec_t.parts / links, export_bm special_play): a special's script is made of parts
 * (row ranges); a part that ends goes on to its `next` part (0xFF: the move ends) unless a link from it fired: a link
 * fires on a hit landed inside its window (LK_HIT; fighter_t.shrow), on a press (LK_IN: the button IN_* + the stick as C's role, d_input; LK_AGAIN = the
 * role the move started with) or both, inside its window (script rows [lo, hi)), and switches to its part at once
 * (LK_NOW) or when the current part ends. A new part plays from where the fighter is. Kim's 236C (236C again: 98, again:
 * 9A), [2]8C (down+A on hit: the dive), 421A / 6246A (the hit's sequence), the KOF continuations (Geese's Jaei-ken,
 * Kyo's grab + explosion: a hit before `cont` jumps there now, a whiff ends there). A special read from the ROM decides
 * in its program (TODO #74: Iori's 214A, K''s 236C / 623C): a press of link k sets spend bit k, the program's P_CHECK
 * (the frames the game's handler reads its input) arms it into plink, PC_LINK branches on it, P_PART clears it. */
enum { LK_HIT = 1, LK_IN = 2, LK_NOW = 1, LK_AGAIN = 0xFE, LK_ANY = 0xFF };
static void part_go(fighter_t *f, const bspec_t *sp, uint8_t k) {   /* part k from here; 0xFF: past the script (over) */
    f->sarm = 0;
    if (k == 0xFF) { f->srow = sp->nrows + 1; return; }
    f->spart = k; f->srow = sp->parts[k].first + 1; f->throw_x0 = f->x;
}
static uint8_t link_in(const fighter_t *f, const bslink_t *l, const intent_t *in) {
    uint8_t d;
    if (!(in->press & l->in)) return 0;
    if (l->dir == LK_ANY) return 1;
    d = d_input(f, in) - RI_S;
    return l->dir == LK_AGAIN ? d == f->spec_id || f->spec_id == BS_FURY : d == l->dir;
}
/* a mash (vocabulary input.mash, TODO #220; KOF98 Ralf's AAAA $4FD46: `btst #2, fp@(5)` in the punch's frame loop
 * replays it): the move's button pressed again while its program checks (P_CHECK b 2) counts only within MASH_GAP frames
 * of the press before (KOF's tap chain: the recogniser takes a tap 20 frames after the last one, not 21; measured in
 * our emulator, a press at the special's frame 16 replays the punch, 17 does not: the command's last tap is 4 frames
 * before the special starts; the brawler's window from start_special, calibrated on romspecials_check ralf:D+again@T,
 * T 16 replays, 17 does not, as in KOF) and, in its hit-stop, only one made in its last MASH_LAG frames (the handler
 * reads this frame's press, which reaches it MASH_LAG frames after it was made: KOF98's input path, handlers98
 * FOLLOW_LAG; one made earlier in the hit-stop is read inside it, never); the window counts real frames from the
 * special's start, again from each press read */
#define MASH_GAP 22
#define MASH_LAG 4
static void special_input(fighter_t *f, const intent_t *in) {    /* a press during a special: a follow-up link armed */
    const bspec_t *sp = &f->ch->specials[f->spec_ix];
    uint16_t row = f->srow ? f->srow - 1 : 0;
    uint8_t k;
    if (sp->prog) {                                              /* a ROM special: its program reads the press (P_CHECK)
                                                                    on the frames the game's handler calls its check */
        for (k = 0; k < sp->nlinks && k < 8; k++) if (link_in(f, &sp->links[k], in)) {
            f->spend |= 1 << k;
            if (f->mash && f->freeze <= MASH_LAG) f->spmash |= 1 << k;   /* (inside the mash window) */
            if (f->freeze) f->phl |= 1 << k;                     /* made in a hit-stop: latched (P_CHECK b) */
        }
        return;
    }
    for (k = 0; k < sp->nlinks; k++) {
        const bslink_t *l = &sp->links[k];
        if (l->from != f->spart || !(l->trig & LK_IN) || row < l->lo || row >= l->hi) continue;
        if ((l->trig & LK_HIT) && !(f->shrow > l->lo && f->shrow <= l->hi)) continue;   /* a hit landed in the window */
        if (link_in(f, l, in)) { f->sarm = k + 1; return; }
    }
}
#define SPECIAL_DAMAGE 8
fighter_t projectiles[NPJ];
uint16_t stat_grabs, stat_specials, stat_throws, stat_escapes;

enum { PK_BOOM = 4, PK_SEG = 5 };    /* bproj_t kind: spawn.boomerang (TODO #176) and its pole segments (boom_update) */
enum { BM_OUT, BM_HOVER, BM_BACK, BM_HELD };   /* a boomerang's phase (its fighter_t pstep; pcnt its count, vx its velocity) */
void projectile_reset(fighter_t *p) {
    if (p->owner && p->owner->shot == p) p->owner->shot = 0;   /* KOF: the thrower may throw again (+$E1 bit 5 off) */
    if (p->pdef && p->pdef->kind == PK_BOOM) {                   /* a boomerang: its pole segments end with it */
        uint8_t k;
        for (k = 0; k < 2; k++) {                                /* (still its own: not reset and taken since) */
            fighter_t *s = p->proj[k];
            p->proj[k] = 0;
            if (s && s->state == S_PROJ && s->pdef == p->pdef->child) projectile_reset(s);
        }
    }
    if (p->owner && p->pdef) {                                   /* its end signals its thrower (bproj_t sig, TODO #139; */
        if (p->pdef->kind != PK_BOOM) p->owner->pflags |= p->pdef->sig & (PF_SIG7 | PF_SIG6);   /* a boomerang: at its catch) */
        if (p->owner->proj[0] == p) p->owner->proj[0] = 0;       /* a pinned effect that ended itself */
        if (p->owner->proj[1] == p) p->owner->proj[1] = 0;
    }
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
        p->dsc = owner->state == S_SPECIAL ? owner->dsc : 0x100; /* its thrower's damage tier ("damage tiers") */
        p->frame_ovr = 0xFFFF; p->spec_atk = 0; p->hit_mask = 0; p->pdef = 0; p->pown = 0; p->prow = p->pend = 0;
        return p;
    }
    return 0;                                                    /* pool empty: this special shows no objects */
}
static void special_end(fighter_t *f) {
    uint8_t k;
    if (f->dtgt) { if (f->dtgt->dpin) f->dtgt->dpin--; f->dtgt = 0; }   /* its down attack's target: free to get up */
    if (f->inv == INV_FURY) f->inv = 0;                          /* the fury's invincibility: hittable again at once */
    f->sinv = 0;                                                 /* (a C special's: the same) */
    if (f->vtgt && f->vtgt->vph_by == f) { f->vtgt->vph = 0; f->vtgt->vph_by = 0; }   /* its victim phases end with it */
    f->vtgt = 0;
    f->pbd = 0; f->spec_sr = 0; f->pstill = 0;                   /* its screen effect (P_SCREEN), its source reactions */
    for (k = 0; k < 2; k++) if (f->proj[k]) { projectile_reset(f->proj[k]); f->proj[k] = 0; }
    f->frame_ovr = 0xFFFF; f->spec_atk = 0;                      /* height kept: hit out of a rising move = an air hit */
    if (f->fpose) { f->fpose = 0xFF; fpose_pal(f, 0); }       /* the fury over (or ended in its flash pose): its colours
                                                                    back (TODO #195: SS2's rage colours stay through the
                                                                    fury's motion, as SS2's rage lasts through the WFT) */
}
static void start_special(fighter_t *f, uint8_t k) {   /* k: the role (BS_*), special_pick: it has a special */
    if (f->team) stat_specials++;
    f->sthr = pend_sthr; pend_sthr = 0;                         /* a throw's special (revamp 3): hold_special's pick */
    if (k != BS_AIR && k != BS_BLITZ) f->spec_ix = f->sthr ? f->xix : spec_ix(f->ch, k);   /* (an air special: air_pick's, a
                                                                    Blitz: blitz_go's, set by the caller; a throw's:
                                                                    hold_special's, revamp 3) */
    f->fmax = k == BS_FURY_MAX; f->brk = f->brkr = 0; f->sinv = 0;   /* (a breaker: its caller sets brk after; a C special:
                                                                    sinv, cspecial) */
    f->spec_buf = 0; f->blz_buf = 0;                             /* (the presses of what it cancelled: not its own) */
    if (k == BS_FURY_MAX) k = BS_FURY;                           /* the MAX fury: the fury's role, its own special */
    f->spec_id = k; f->throw_x0 = f->x; f->hit_mask = 0; f->spec_prev_hit = 0; f->spec_atk = 0; f->landed = 0;
    f->var = f->ch->specials[f->spec_ix].vdef;                   /* its variant row: the rule's, latched for the whole move
                                                                    (vocabulary "variants are latched at move start") */
    if (k == BS_FORM) f->inv = INV_FURY;                         /* the transition: untouchable (no hurt box either) */
    f->spec_dmg = SPECIAL_DAMAGE; f->spec_react = R_KNOCKDOWN; f->spec_slide = 0; f->spec_sr = 0; f->pbd = 0; f->vtgt = 0;
    f->dsc = dtier(f); f->dacc = 0x80;                           /* its damage tier ("damage tiers"; rounded to nearest) */
    f->proj[0] = f->proj[1] = 0;                                 /* script objects: taken when a row shows one */
    if (k == BS_FURY || k == BS_THROW) f->inv = INV_FURY;        /* every fury, every fighter: invincible from the trigger
                                                                    to its end (special_end, fighter_update); a throw's
                                                                    special too (revamp 3: a throw is invincible) */
    if (f->ch->specials[f->spec_ix].sflags & SF_INV) f->inv = INV_FURY;   /* a move the roster makes invincible (game.json
                                                                    roster[].invincible, Bruno: Kyo's EX 421D, TODO #202):
                                                                    the fury's rule, from its first frame to its end */
    f->spart = 0; f->sarm = 0; f->shrow = 0; f->spend = f->plink = f->phl = 0;   /* its first part, no follow-up armed, no hit */
    f->scancel = 0; f->fury_buf = 0;                             /* nothing landed yet: no fury cancel ("cancels") */
    f->fpose = 0;                                                /* a fury's flash pose: not yet ("flash pose") */
    enter(f, S_SPECIAL); f->srow = 0; f->speed = 0x100;          /* a route ender: its node's speed (S_ATTACK) */
    rt_arm(f, BA_COUNT + f->spec_ix);                            /* its targets, if it has some (retiming) */
    if (f->ch->specials[f->spec_ix].prog) {                      /* a ROM special: its program from its first op */
        f->pres = 0; f->pflags = 0; f->pcnt = 0; f->pfric = 0; f->pg = 0; f->vx = f->vy = f->vz = 0;   /* (vz: P_MOVE's
                                                                    depth, only P_HOME sets it) */
        f->phit = 0xFF; f->pcatch = 0; f->phold = 0; f->pdead = 0; f->pvl_n = 0; f->vlist = 0; f->vsigp = 0; f->phh = 0; f->mash = MASH_GAP; f->spmash = 0;
        if ((f->ch->specials[f->spec_ix].sflags & SF_NOW) && k != BS_FURY) {   /* SF_NOW (SS2): its first frame is this
                                                                    one (the action routine runs in the frame the action
                                                                    is set; else every SS2 move ran a frame long, TODO
                                                                    #191); a fury starts after its flash pose */
            f->pheld = 0; special_update(f);
        }
    }
}

/* ---- projectiles (tools/kof98/README.md "Projectiles"; tools/kof96/projectiles96.py) ----------------------------------
 * KOF96/98/99 spawn a projectile as an object of its own on the thrower's event step: its own animation, boxes and
 * motion, owner +$84, one at a time per thrower (+$E1 bit 5). It lives on whatever the thrower does (its routine never
 * reads the owner) and dies when its animation ends, when it leaves the screen (x - camera <= -64 or >= 384, the shared
 * test KOF98 $180B6) or, a travelling one (kind 1), on its first hit, into its end animation; an eruption (kind 3)
 * hits once and plays on (KOF's 1v1; the brawler's crowd rule: it hits every target it touches, each once). Neither it nor its thrower freezes on its hit (the victim does). Two projectiles that meet
 * (one's attack box on the other's own box) both spend their hit. Here: a pool entity driven by its bproj_t rows. */
static const fighter_t *pin_of(const fighter_t *p) {            /* what a pinned effect is pinned to: its thrower, */
    const fighter_t *o = p->owner;                               /* or (follow 16) its thrower's caught victim (SS2's */
    return (p->pdef->follow & 16) && o->target ? o->target : o;  /* WFT card wind on the victim, object 27) */
}
static void proj_row(fighter_t *p) {                            /* its rows: its fighter's bank (called from */
    const bproj_t *d = p->pdef;                                  /* its owner's update, the projectiles' and combat) */
    uint8_t ob = BANK_set(CH_BANK(p->ch));
    if (p->pend == 1) {                                          /* its end after the hit, in place */
        const bpend_t *e = &d->end[p->prow];
        p->frame_ovr = e->frame; p->x = p->throw_x0 + dir_mul(p->facing, (int32_t)e->x << 13); p->y = p->py0 + FIX(e->y);   /* (at
                                                                    the hit's place and height, TODO #164) */
        p->spec_atk = 0; p->pown = 0;
    } else {
        const bprow_t *r = &d->rows[p->prow];
        p->frame_ovr = r->frame; p->x = p->throw_x0 + dir_mul(p->facing, (int32_t)r->x << 13); p->y = FIX(r->y) + (d->air || d->kind == PK_FX ? p->py0 : 0);
        p->spec_atk = (r->flags & 1) && (!p->pend || p->pend == 3) ? &r->atk : 0;   /* (3: an eruption that hit: live) */
        p->pown = (r->flags & 2) && !p->pend ? &r->own : 0;
    }
    if (d->follow && p->owner) p->y += pin_of(p)->y;             /* pinned to its thrower (Burn Knuckle's flame) */
    BANK_set(ob);
}
/* spawn.boomerang (TODO #176; SS2 Kuroko's flag, object 27 $4C274, measured: tools/samsho2/boomerang_ss2.py): its pole
 * segments (SS2's effect objects 40, $4EC50) gap, 2 gap.. px behind it on its line, never nearer its thrower than
 * bsegmin px: placed by it every frame, after its move */
static void boom_segs(fighter_t *p) {
    const bproj_t *d = p->pdef;
    uint8_t k;
    for (k = 0; k < 2; k++) {
        fighter_t *s = p->proj[k];
        int32_t x, lo;
        if (!s) continue;
        x = p->x - dir_mul(p->facing, FIX((int16_t)d->bgap * (k + 1)));
        lo = p->owner->x + dir_mul(p->facing, FIX(d->bsegmin));
        if (dir_mul(p->facing, x - lo) < 0) x = lo;
        s->throw_x0 = x; s->facing = p->facing; s->z = p->z;
        proj_row(s);
    }
}
static void boom_start(fighter_t *p) {                           /* placed spawn_x px ahead of its thrower, flying out */
    const bproj_t *d = p->pdef;                                  /* at wrap_x (1/8 px) a frame; bseg pole segments */
    uint8_t k;
    p->throw_x0 += dir_mul(p->facing, FIX(d->spawn_x)); proj_row(p);
    p->vx = dir_mul(p->facing, (int32_t)d->wrap_x << 13); p->pstep = BM_OUT; p->pcnt = d->bhover;
    for (k = 0; k < 2; k++) {
        fighter_t *s = k < d->bseg && d->child ? proj_alloc(p->owner) : 0;
        p->proj[k] = s;
        if (!s) continue;
        s->pdef = d->child; s->prow = 0; s->pend = 2; s->facing = p->facing; s->z = p->z; s->tick = 1;
    }
    boom_segs(p);
}
/* one frame of a boomerang (SS2's routines $4C2F8 / $4C358 / $4C398 / $4C410, their tests on its next place |x + vx - his
 * x|): out until brange px from its thrower (placed there), hover its count, back at the same speed until bcatch px from
 * him (placed there: the catch, its signal sent), bheld more frames in his hand; its rows play on (their last held) */
static void boom_update(fighter_t *p) {
    const bproj_t *d = p->pdef;
    int32_t nx = p->x + p->vx, dist = nx - p->owner->x;
    if (dist < 0) dist = -dist;
    switch (p->pstep) {
    case BM_OUT:
        if (dist >= FIX(d->brange)) { p->x = p->owner->x + dir_mul(p->facing, FIX(d->brange)); p->vx = 0; p->pstep = BM_HOVER; }
        else p->x = nx;
        break;
    case BM_HOVER:                                               /* (its count: decremented, < 0 = back, moving that frame) */
        if (--p->pcnt < 0) { p->vx = dir_mul(p->facing, -((int32_t)d->wrap_x << 13)); p->x += p->vx; p->pstep = BM_BACK; }
        break;
    case BM_BACK:
        if (dist <= FIX(d->bcatch)) {
            p->x = p->owner->x + dir_mul(p->facing, FIX(d->bcatch)); p->vx = 0; p->pstep = BM_HELD; p->pcnt = d->bheld;
            p->owner->pflags |= d->sig & (PF_SIG7 | PF_SIG6);    /* caught: its thrower goes on (SS2: his +$D4) */
        } else p->x = nx;
        break;
    default:
        if (--p->pcnt < 0) { projectile_reset(p); return; }
    }
    if (++p->prow >= d->nrows) p->prow = d->loop == 0xFF ? d->nrows - 1 : d->loop;
    p->throw_x0 = p->x; proj_row(p);
    boom_segs(p);
}
static fighter_t *proj_start(fighter_t *owner, const bproj_t *d, int32_t x0, int8_t facing, int32_t z) {
    fighter_t *p;
    if (!d->nrows) { if (owner) owner->pflags |= d->sig & (PF_SIG7 | PF_SIG6); return 0; }   /* no rows (Mr. Big's
                                                                    23623C objects 0 / 1): over at once, its end signals
                                                                    sent; its row 0 read past its table (a crash once the
                                                                    tables moved, TODO #139) */
    p = proj_alloc(owner);
    if (!p) return 0;                                            /* pool full: no entity for it */
    p->pdef = d; p->prow = 0; p->pend = 0; p->facing = facing; p->z = z; p->throw_x0 = x0;
    p->zfront = d->back ? -1 : 1;                                /* behind its owner (KOF +$2C < 0, TODO #214) or in front */
    p->py0 = d->air && owner ? owner->y : 0;                     /* an air projectile: its rows count from its thrower's
                                                                    height (bproj_t air, TODO #211) */
    p->spec_dmg = SPECIAL_DAMAGE; p->spec_react = d->react; p->spec_fx = d->fx; p->spec_prev_hit = 0;
    p->pcnt = d->hits; p->freeze = 0;                            /* its hits left (object.phase) */
    p->tick = 0; p->state_t = 0; p->node = d->child_b0;          /* tick 0: shown at row 0 this frame (the update after
                                                                    the fighters' advances it from the next); state_t:
                                                                    its frames alive; node: the next frame its child is born */
    proj_row(p);
    if (d->kind == PK_BOOM) boom_start(p);
    return p;
}
static void proj_spawn(fighter_t *f, const bproj_t *d) {         /* spawn point: the script's origin + offset */
    fighter_t *p = proj_start(f, d, (d->follow & 4) ? f->x : f->throw_x0 + dir_mul(f->facing, FIX(d->spawn_x)), f->facing, f->z);
    if (p && !(d->follow & 4)) f->shot = p;                      /* (a pinned effect of the script is no shot) */
}
static void proj_launch(fighter_t *p);
static void proj_hit(fighter_t *p) {                             /* its hit landed (a fighter or a clash) */
    if (p->owner) p->owner->pflags |= (p->pdef->sig << 2) & (PF_SIG7 | PF_SIG6);   /* its hit signals its thrower */
    if (p->pdef->kind == PK_BOOM) {                              /* a boomerang stops where it hit, its attack spent; */
        p->vx = 0; p->pend = 2; p->spec_atk = 0; p->pown = 0;    /* it hovers the count it has left, then flies back */
        if (p->pstep == BM_OUT) p->pstep = BM_HOVER;             /* (SS2 $4C47E / $4C440 -> $4C358) */
        return;
    }
    if (p->pdef->hitnext && p->pdef->next) {                     /* its next phase at its hit (Rugal's Kaiser Wave: the */
        uint8_t m = p->hit_mask, st = p->pdef->stop;             /* list's next state, TODO #173): from where it is, */
        proj_launch(p);                                          /* frozen its hit-stop, then re-armed (proj_update) */
        p->hit_mask = m; p->freeze = st;
        return;
    }
    if (p->pdef->kind == 1 && p->pcnt > 1) {                     /* hits left (bproj_t hits, KOF +$138): frozen, then */
        p->pcnt--; p->freeze = p->pdef->stop; return;            /* re-armed (projectiles_update) */
    }
    if (p->pdef->kind == 1) {                                    /* travelling: its end animation where it hit */
        if (!p->pdef->nend) { projectile_reset(p); return; }
        p->pend = 1; p->prow = 0; p->throw_x0 = p->x; p->py0 = p->y; if (p->pdef->follow && p->owner) p->py0 -= p->owner->y;
        proj_row(p);
    } else { p->pend = 2; p->spec_atk = 0; p->pown = 0; }       /* an eruption plays on, its attack spent */
}
static void proj_crowd(fighter_t *p) {                          /* an eruption's hit on a fighter (crowd rule, Bruno
                                                                    2026-10-06): its thrower signalled, its clash box
                                                                    spent as KOF's (pend 3), its attack box live for
                                                                    the others (combat: hit_mask, each target once) */
    if (p->owner) p->owner->pflags |= (p->pdef->sig << 2) & (PF_SIG7 | PF_SIG6);
    p->pend = 3; p->pown = 0; p->freeze = p->pdef->stop;        /* (stop: KOF's frame on the hit, object.phase) */
}
static void proj_child(fighter_t *p) {                           /* its trail: an object it spawns where it is */
    const bproj_t *d = p->pdef;                                  /* (its rows hold their own height) */
    uint8_t i, nfree = 0;
    if (!d->child || p->pend == 1 || p->pend >= 4 || p->state_t != p->node || d->kind == PK_BOOM) return;   /* (a boomerang's
                                                                    child: its segments; an eruption that hit (pend 2 / 3)
                                                                    spawns on: Kyo's MAX flames, TODO #202) */
    for (i = 0; i < NPJ; i++) nfree += projectiles[i].state == S_OFF;
    if (nfree < 2) { p->node = p->state_t < d->child_b1 && d->child_b1 != 255 ? d->child_b1 : p->node + d->child_period; return; }
                                                                 /* a trail never takes the last free entity (a thrown
                                                                    projectile needs it) */
    fighter_t *c = proj_start(p->owner, d->child, p->x + dir_mul(p->facing, (int32_t)d->child_dx << 13), p->facing, p->z);
    if (c && c < p) c->tick = 1;                                 /* this update pass is past it: row 0 already counted */
    p->node = p->state_t < d->child_b1 && d->child_b1 != 255 ? d->child_b1 : p->node + d->child_period;
    if (!d->child_period && p->state_t >= d->child_b1) p->node = 255;
}
static void proj_launch(fighter_t *p) {                          /* its next phase from where it is (object.phase) */
    const bproj_t *d = p->pdef->next;
    p->pdef = d; p->prow = 0; p->pend = 0; p->tick = 1; p->throw_x0 = p->x;
    p->spec_react = d->react; p->spec_fx = d->fx; p->hit_mask = 0; p->pcnt = d->hits; p->freeze = 0;
    proj_row(p);
}
static void proj_update(fighter_t *p, int16_t cam_x) {          /* one frame of an entity (its bank mapped) */
    const bproj_t *d = p->pdef;
    int16_t sx;
    if (d->kind == PK_SEG) return;                               /* a boomerang's pole segment: placed by it */
    if (!p->tick) {                                              /* its first frame: row 0; a step effect takes its */
        p->tick = 1;                                             /* owner's animation and step as they are now, after */
        if ((d->follow & 8) && p->owner) { p->fx_pan = p->owner->pan; p->fx_step = p->owner->pstep; }   /* the owner's code
                                                                    (KOF98 $374B0 on its first run: an effect born as
                                                                    the state ends lives through the next one's step) */
        proj_child(p); return;
    }
    if (p->freeze) {                                             /* after a hit (bproj_t stop): frozen, it moves on */
        if (--p->freeze) return;                                 /* stop frames after it; with hits left it may hit */
        if (d->kind == 1) p->hit_mask = 0;                       /* again then (object.phase; an eruption waits for */
    }                                                            /* a re-arming row) */
    p->state_t++;
    if (d->kind == PK_BOOM) { boom_update(p); return; }          /* (no off-screen end: it comes back) */
    if (p->pend == 4) p->pend = 5;                               /* its thrower's signal: one more pinned frame (KOF */
    else if (p->pend == 5) { proj_launch(p); proj_child(p); return; }   /* runs the object before its thrower), */
    if (p->pend == 6) p->pend = 7;                               /* (follow 64: the same frame, then its end rows */
    else if (p->pend == 7) {                                     /* in place: KOF's object plays its end animation, */
        p->pend = 1; p->prow = 0; p->throw_x0 = p->x; p->py0 = p->y - pin_of(p)->y;   /* no longer pinned) */
        proj_row(p); return;
    }
    if (p->pend == 1) {                                          /* then its next phase */
        if (++p->prow >= d->nend) { projectile_reset(p); return; }
    } else if (d->follow && p->owner) {                          /* pinned: its rows cycle at the thrower's place */
        if ((d->follow & 8) && (p->owner->state != S_SPECIAL || p->owner->pan != p->fx_pan || p->owner->pstep != p->fx_step)) {
            projectile_reset(p); return;                         /* a step effect: its owner's step is over (KOF98 $3751A) */
        }
        if (d->follow & 4) {                                     /* or run with its thrower's script rows (frozen with
                                                                    its hit-stop; Kizuna's Hienzan pillar, TODO #144) */
            const fighter_t *o = p->owner;
            int16_t k = o->state == S_SPECIAL ? (int16_t)o->srow - 1 - d->spawn_row : -1;
            if (k < 0 || k >= d->nrows) { projectile_reset(p); return; }   /* the special left its rows */
            p->prow = k;
        } else if (++p->prow >= d->nrows) {
            if (d->follow & 2) { projectile_reset(p); return; }  /* (or end there: it frees itself) */
            p->prow = d->loop == 0xFF ? 0 : d->loop;
        }
        p->throw_x0 = pin_of(p)->x; p->facing = p->owner->facing;
    } else if (d->air && !p->pend && p->y <= 0) {                /* an air projectile on the floor (SS2's shuriken, TODO
                                                                    #211: $30404 tests y >= 224 before its move, so the
                                                                    frame that reached the floor shows it there or below):
                                                                    its next phase from where it is, on the floor */
        if (!d->next) { projectile_reset(p); return; }
        proj_launch(p); return;
    } else if (++p->prow >= d->nrows) {
        if (d->loop == 0xFF) { projectile_reset(p); return; }    /* its animation is over */
        p->prow = d->loop; p->throw_x0 += dir_mul(p->facing, (int32_t)d->wrap_x << 13);   /* the flight goes on */
    }
    proj_row(p);
    if ((p->pend == 0 || p->pend == 3) && (d->rows[p->prow].flags & 4)) {   /* a re-arming row */
        p->hit_mask = 0; if (p->pend == 3) p->pend = 0;          /* (KOF: +$E2 bit 7 cleared on an event step) */
    }
    sx = INT(p->x) - cam_x;
    if (sx <= -64 || sx >= 384) { projectile_reset(p); return; }   /* off screen (KOF's test, its 320 px screen) */
    proj_child(p);
}
uint8_t projectiles_alive(void) {
    uint8_t i, m = 0;
    for (i = 0; i < NPJ; i++) if (projectiles[i].state != S_OFF) m |= 1 << i;
    return m;
}
void projectiles_update(int16_t cam_x, uint16_t skip) {
    uint8_t i;
    if (!(skip & 0x100)) burn_clock++;                                     /* the burn cycle's clock (once a frame, not in a super flash) */
    for (i = 0; i < NPJ; i++) {
        fighter_t *p = &projectiles[i];
        uint8_t ob;
        if (p->state != S_PROJ || !p->pdef || (skip >> i & 1)) continue;
        ob = BANK_set(CH_BANK(p->ch));                           /* its rows: its fighter's bank (fighter.h "banks") */
        proj_update(p, cam_x);
        BANK_set(ob);
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
/* C, forward / down / up / down-forward / up-forward + C (down / up = toward / away from the camera) -> BS_*, 0xFF = none */
static uint8_t special_for(const fighter_t *f, const intent_t *in) { return special_pick(f, d_input(f, in) - RI_S); }
/* ---- cancels (TODO #143, Bruno 2026-10-06; docs/brawler_move_vocabulary.md "cancel"): engine rules, every fighter,
 * no per-move data. (1) A ground normal (any route node) that made contact (landed; the brawler has no guard, so a
 * hit) cancels, from the end of its hit-stop to its last frame, into a special (C + the stick: the route's own special
 * link when it has one, else the slot special_for picks) or the fury (D, down+D its MAX), each the moment its press
 * is read (presses during the normal are buffered: spec_buf / fury_buf). (2) A special (not a fury) whose first hit
 * landed (its body's or its projectile's, or its catch: scancel) cancels into the fury on D, on the ground and not
 * while it holds a caught victim (PF_HOLD: its routine owns the victim); a catch's final impact (its slam: Rugal's God
 * Press grinding the victim into the wall, a ground slam) lets the victim go, and from that frame the special cancels
 * like any hit (a D pressed since its first hit fires then, feedback 20261006-175700-5d29); a D before that first hit does nothing. The fury
 * plays as from neutral: its meter, super flash, charge sound and invincibility. (3) A fury (not a MAX) whose first hit
 * landed cancels the same way into the fighter's MAX fury on down+D (TODO #151; D alone does nothing): the MAX from its
 * start, its own flash (orange), charge sound, invincibility and meter; a MAX is never cancelled (may_cancel), nor a
 * fury of a fighter without a MAX. (4) A throw's last impact before its control return (forward / back + A: the blow
 * or the victim hitting the floor, bthrow_row_t flags 4: last_impact) and the hold finisher's landing are normal hits: from the frame after
 * the impact (after its hit-stop, Ryo's freeze) to the thrower's control return, C + the stick cancels into the special,
 * D into the fury (down+D the MAX); the thrower lets go, a victim still in the script plays it on alone. A C / D pressed
 * up to CANCEL_BUF frames before the first legal frame (hit-stop frames not counted) is buffered and fires on it. The
 * victim landing after the control return (Terry's and Geese's throws) is not the cancel point: the blow before it is
 * (feedback 20261006-194211-5d29: a cancel at the landing came from neutral, after Ryo had flown away); a throw whose
 * only impact comes after the control return cancels from the control return. A throw
 * without an impact row (Yamazaki's back throw, Mai's forward throw: the damage at the script's end) has no cancel.
 * (5) The juggle window (Bruno: "considered a regular hit so that I could cancel with a special or even a fury"): a
 * throw cancelled (rule 4) or a catch's slam cancelled (rule 2) opens it on that victim (fighter_t.jug_by, juggle_open):
 * the canceller's follow-up special / fury (its body or projectiles) hits it while it is still thrown (its script ends
 * there, the throw's damage dealt) or in the air with no hurt box of its own (JUG_BOX); it closes when the victim lands.
 * Every other attacker keeps the usual rules.
 * KOF98, measured (Kyo vs Yuri, close B / close C then 236A, every press frame: tools/brawler/throws166_proof.py k): a
 * normal's special cancel takes a press from the normal's startup until 8 (close C) / 9 (close B) frames after the
 * impact and fires at the end of the hit-stop. Air normals have no special cancel
 * (no special starts in the air). Players only: enemies keep their routes' special links, nothing more. ---- */
#define CANCEL_BUF 24                 /* frames a C / D pressed before a throw's last impact stays buffered (rule 4) */
static uint8_t cancel_pick(fighter_t *f) {                       /* a throw's buffered C / D: the role it cancels into,
                                                                    its meter spent (0xFF: none, or no meter: dropped) */
    uint8_t k = (f->fury_buf & 0x80) ? fury_buy(f, f->fury_buf & 1, 0) : 0xFF;
    if (k == 0xFF && f->spec_buf) {
        uint8_t s = special_pick(f, (f->spec_buf & 0x7F) - RI_S);
        if (s != 0xFF && pay(f, PAY_SPECIAL, 0)) k = s;
    }
    f->spec_buf = f->fury_buf = 0; f->cnc_buf = 0;
    return k;
}
static uint8_t fury_cancel(fighter_t *f) {                       /* a buffered D: the fury (its MAX) now, paid -> 1 */
    uint8_t k = (f->fury_buf & 0x80) ? fury_buy(f, f->fury_buf & 1, 0) : 0xFF;
    f->fury_buf = 0;
    if (k == 0xFF) return 0;
    lab_note(f, LE_SPECIAL, 0, LH_CANCEL, BS_FURY); start_special(f, k);
    return 1;
}
/* ---- specials read from the ROM (tools/kof96/handlers98.py, handlers98.md) ---------------------------------------------
 * KOF98 runs a special as straight-line 68000 code: set speeds, start a state's animation, then a frame loop (the
 * coroutine resumes at +$00) that moves the body and waits for the animation's end / an event step / the landing.
 * export_bm.rom_c turns that code into bprim_t ops; this plays them: each frame the ops run from the resume point until
 * a P_BR to the frame's end, then the animation advances (KOF98's engine: a step shows ticks + 1 frames, the frame a
 * state starts counts as the first of its first step, past the last step the end flag is set, a hold stays on it).
 * Hits come from the animation (an attack box while the step is active, a new hit unless the active step before it
 * carries KOF's same-hit flag); the brawler's own hit-stop freezes it (fighter_update), no freeze is in the data. */

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
#define KM_HURT 4                 /* kmode: KOF's reaction state keeps a hurt box (286 / 288 / 293: LAUNCH_BOX); without
                                     it (283 / 285 / 287 blowback and launch, 303 slam) nothing hits the victim until it
                                     is down (KOF's juggle rule: the reaction's steps have no $0200; handlers98.react_hurt) */
static const struct { int32_t vx, vy, g, gf, vmin; uint16_t gfr, vfr; uint8_t delay; } KOF_REACT[R_LIFT + 1] = {   /* by R_* */
    [R_HEAVY] =     { 0xB2E00, 0, 0, 0, 0, 0, 0xD400, 5 },                       /* 258: $1BCA6 13.5 px x 0.828 */
    [R_KNOCKDOWN] = { 0xB6000, 0x70000, 0x8000, 0x8000, 0x48000, 0, 0xD000, 2 }, /* 283-286: $1D618 vx 14 x 0.8125, vy 7 */
    [R_LAUNCH] =    { 0x20000, 0x114000, 0x2B000, 0xA000, 0, 0xDF00, 0, 2 },     /* 286: $1BF76 */
    [R_SLAM] =      { 0x60000, -0xA0000, 0, 0, 0, 0, 0, 2 },                     /* 303: $1CD4C vx 6, vy -10 to the floor */
    [R_LIFT] =      { 0, 0x114000, 0x2B000, 0xA000, 0, 0xDF00, 0, 2 },           /* 286: $1BFA2, the launch without vx */
};
#define RK_HIGH 8                 /* a packed reaction nibble (R_LIGHT | 8: never a KOF one): KOF98's high launch (TODO
                                     #220, reactions 56 / 57, state 299: handlers98.HIGH_LAUNCH), R_LAUNCH on KOF_HIGH */
static const struct { int32_t vx, vy, g, gf, vmin; uint16_t gfr, vfr; uint8_t delay; } KOF_HIGH =
    { 0x20000, 0x1E0000, 0x4A000, 0xA000, 0, 0xDF00, 0, 2 };                     /* 299: $1C17A vx 2, vy 30, g 4.625 */
static void kof_react(fighter_t *v, int8_t away, uint8_t rc, int8_t slide) {   /* rc: R_* | 8 hittable */
    uint8_t hurt = rc & 8 ? KM_HURT : 0;
    if ((rc == (R_TRIP | 8) || rc == (R_BLOWBACK | 8)) && v->state == S_KNOCKDOWN) {   /* Double Dragon's knockdown hop */
        if (v->wall_by) away = v->wall_by->facing;               /* (TODO #192, export_dd brawler_react): its reaction 69 */
        v->facing = -away; play(v, BA_TRIP);                     /* ($26076), on the floor or again in the air, sent the */
        v->vy = v->y <= 0 ? FIX(3) + 0x8000 : rc == (R_TRIP | 8) ? 0 : FIX(1) + 0x8000;   /* attacker's facing way ($25AD0), */
        v->vx = dir_mul(away, FIX(5) + (rc == (R_TRIP | 8) ? 0x44000 : 0xB4000));   /* up 3.5 px (its header; in the air the */
        v->kg = v->kgf = 0x6000; v->kgfr = 0; v->kvfr = 0xE000; v->kvmin = FIX(5); v->kdelay = 0;   /* hit's down knock */
        v->kmode = 1 | KM_HURT; return;                          /* $25B3A eats the rise), gravity 0.375, 5 px a frame away */
    }                                                            /* (its header) + the push (4.25 / 11.25 x 7/8, $204DE) */
    {   uint8_t hi = (rc & 16) && (rc & 7) == R_LAUNCH;       /* the high launch (RK_HIGH, fighter_hit) */
        rc &= 7;
        if (hi && v->state == S_KNOCKDOWN) {
            v->vx = dir_mul(away, KOF_HIGH.vx); v->kvfr = KOF_HIGH.vfr; v->kvmin = KOF_HIGH.vmin; v->kdelay = KOF_HIGH.delay;
            v->vy = KOF_HIGH.vy; v->kg = KOF_HIGH.g; v->kgf = KOF_HIGH.gf; v->kgfr = KOF_HIGH.gfr;
            v->kmode = 1 | hurt; return;
        }
    }
    if (v->hp <= 0 && rc < R_KNOCKDOWN && !dancing(v)) rc = R_KNOCKDOWN;
    if (rc < R_HEAVY || rc > R_LIFT || !KOF_REACT[rc].delay) return;   /* the brawler's own (react): R_TRIP, R_BLOWBACK */
    if (rc == R_HEAVY && v->y > 0 && v->state != S_HITSTUN) rc = R_KNOCKDOWN;   /* no reel in the air: KOF's air hit sends
                                                                    it off (a dance's catch reels: react) */
    if (rc == R_HEAVY && v->state != S_HITSTUN) return;
    v->vx = dir_mul(away, rc == R_HEAVY && slide != -128 ? fmul16(FIX(slide), 0x10000 - KOF_REACT[R_HEAVY].vfr) : KOF_REACT[rc].vx); v->kvfr = KOF_REACT[rc].vfr; v->kvmin = KOF_REACT[rc].vmin; v->kdelay = KOF_REACT[rc].delay;
    if (rc == R_HEAVY) return;
    if (v->state != S_KNOCKDOWN) return;
    v->vy = KOF_REACT[rc].vy; v->kg = KOF_REACT[rc].g; v->kgf = KOF_REACT[rc].gf; v->kgfr = KOF_REACT[rc].gfr;
    v->kmode = 1 | hurt;
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
/* a source reaction (TODO #136, vocabulary reaction.source_motion; bm_sreact, export_kz.sr_motion): the motion the
 * source game's reaction code gives the victim of a SF_SREACT special's hit, Kizuna's: the attack box's type picks the
 * victim's reaction animation ($2D4F2: $5FBEE by type and standing / airborne, the group-4 handler's state) and that
 * animation's step commands move it (the physics $2B644). A reel slides n frames (vx += ax), a flight rises and falls
 * (vy -= g) to the floor: it lands where its next move would take it under, without moving ($29432 before the move),
 * pauses land frames, bounces (bvx / bvy / bg) and lies down; it stands still the frame after the hit-stop (kdelay 1)
 * [meas: kim136_proof, 214B_h / 28C_h / 421A_h / 6246A_h]. The posture is the brawler's own (reel, blowback, flight). */
static void src_react(fighter_t *v, int8_t away, uint8_t k) {
    const bsreact_t *r = &bm_sreact[k - 1];
    v->ksr = k; v->kdelay = 1; v->kvfr = 0; v->kgfr = 0; v->facing = -away;
    v->vx = dir_mul(away, r->vx); v->kax = dir_mul(away, r->ax);
    if (v->state == S_HITSTUN) { v->ksn = r->n; v->kmode = 0; v->vy = 0; return; }
    if (v->state != S_KNOCKDOWN || !r->vy) { v->ksr = 0; return; }   /* (a reel's motion on a falling victim: the brawler's) */
    v->vy = r->vy; v->kg = v->kgf = r->g; v->ksn = 0;
    v->kmode = 1 | (r->r & 8 ? KM_HURT : 0);                     /* (hittable in its flight when its source's reaction
                                                                    steps carry boxes: Kizuna's 32 / 33 / 9B, not 2C) */
}
static uint8_t src_fall(fighter_t *f) {                          /* S_KNOCKDOWN in a source reaction: one frame; 0 = its */
    const bsreact_t *r = &bm_sreact[f->ksr - 1];                 /* landing is the brawler's own (no bounce in the data) */
    if (f->anim == BA_KNOCKDOWN_BOUNCE) {                        /* on the floor: the pause, then the bounce */
        if (f->ksn) { f->ksn--; return 1; }
        f->vx = dir_mul(-f->facing, r->bvx); f->vy = r->bvy; f->kg = r->bg; play(f, BA_KNOCKDOWN_FALL);
        f->kmode = 1;                                            /* (its bounce: no box, Kizuna's lying steps) */
    }
    if (f->y + f->vy <= 0) {                                     /* the floor */
        f->y = 0; f->vy = 0; f->kmode = 0; f->kfloor = 1;
        if (r->land == 0xFF) { f->ksr = 0; return 0; }
        f->vx = 0;
        if (f->anim == BA_KNOCKDOWN_FALL) { f->ksr = 0; enter(f, S_DOWN); play(f, BA_DOWN); return 1; }
        f->ksn = r->land ? r->land - 1 : 0; play(f, BA_KNOCKDOWN_BOUNCE); set_burn(f, 0);
        return 1;
    }
    f->x += f->vx; f->y += f->vy; f->vy -= f->kg; clamp(f);
    if (f->vy < 0 && (f->anim == BA_BLOWBACK || f->anim == BA_BLOWBACK_N)) play(f, BA_KNOCKDOWN_FLIGHT);
    return 1;
}
static void pan_enter(fighter_t *f, uint8_t prev) {              /* a step starts: its $FB move, event, hit */
    const bstep_t *s = &f->pan->steps[f->pstep];
    if (s->dx) { f->x += dir_mul(f->facing, FIX(s->dx)); clamp(f); }
    f->pflags = (f->pflags & ~PF_EVENT) | (s->flags & 8 ? PF_EVENT : 0);   /* the engine copies the step's flags ($5C4A) */
    if ((s->flags & 1) && !((prev & 1) && (prev & 16))) {        /* a new hit window */
        uint8_t k;
        f->hit_mask = 0; f->spec_dmg = f->pdmg; f->spec_react = f->preact & 7; f->spec_fx = f->pfx; f->spec_slide = -128;
        f->spec_sr = 0;
        if (s->hy && f->state == S_SPECIAL && (f->ch->specials[f->spec_ix].sflags & SF_SREACT)) {   /* its source's */
            f->spec_sr = s->hy;                                  /* reactions (src_react), its postures packed as KOF's */
            f->spec_react = (s->hy & 15 ? bm_sreact[(s->hy & 15) - 1].r : R_HEAVY) | (s->hy >> 4 ? bm_sreact[(s->hy >> 4) - 1].r : R_KNOCKDOWN) << 4;
        }
        else if (s->hy == HY_HOLD) f->spec_react = R_HEAVY;     /* KOF's hold hit (box $36, TODO #220): a reel, held */
        else if (s->hy) f->spec_react = s->hy;                   /* KOF's own reaction to this step's attack box (packed) */
        else if (f->spec_react == R_KNOCKDOWN)                   /* a knockdown state's earlier hits keep the victim */
            for (k = f->pstep + 1; k < f->pan->nsteps; k++)      /* standing (KOF98 Gatling Attack 138: 258, then 283) */
                if ((f->pan->steps[k].flags & 1) && !((f->pan->steps[k - 1].flags & 1) && (f->pan->steps[k - 1].flags & 16))) { f->spec_react = R_HEAVY; break; }
    }
}
static void pan_voices(fighter_t *f) {                           /* the step entered: its $FC voices (bchar_t.pvox) */
    const bspec_t *sp;
    const uint8_t *e;
    if (f->state != S_SPECIAL) return;
    sp = &f->ch->specials[f->spec_ix];
    for (e = f->ch->pvox; *e != 0xFF; e += 4)
        if (e[0] == f->spec_ix && e[2] == f->pstep && &sp->anims[e[1]] == f->pan) prog_voice(f, e[3]);
}
static void prog_spawn(fighter_t *f, const bproj_t *d);
static void pan_fx(fighter_t *f) {                               /* the step entered: its effects (bchar_t.pfx: KOF's $FA */
    const bspec_t *sp;                                           /* records, vocabulary anim.step_spawn, TODO #173) */
    const uint8_t *e;
    if (f->state != S_SPECIAL || !f->ch->pfx) return;
    sp = &f->ch->specials[f->spec_ix];
    for (e = f->ch->pfx; *e != 0xFF; e += 4)
        if (e[0] == f->spec_ix && e[2] == f->pstep && &sp->anims[e[1]] == f->pan)
            proj_start(f, &sp->robj[e[3]], f->x, f->facing, f->z);   /* an effect object of its own: never the shot nor
                                                                    one P_FXOFF ends (KOF's $FA effects: no +$E1 bit 5;
                                                                    Kyo's hand fire, TODO #202) */
}
static void pan_play(fighter_t *f, const banim_t *an) {
    f->pan = an; f->pstep = 0; f->pleft = an->steps[0].ticks + 1; f->pflags &= ~(PF_END | PF_EVENT);
    pan_enter(f, 0); pan_voices(f); pan_fx(f);
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
    pan_enter(f, prev); pan_voices(f); pan_fx(f);
}
static uint8_t pcond(fighter_t *f, uint8_t c, int32_t v) {
    switch (c) {
    case PC_STEPEV: return f->pflags & PF_EVENT ? 1 : 0;        /* the step's KOF $0080, not consumed (tst) */
    case PC_HITANY: return f->pflags & PF_HITANY ? 1 : 0;       /* a hit landed since P_HITCLR (KOF +$E3 bit 7) */
    case PC_SIG7: return f->pflags & PF_SIG7 ? 1 : 0;           /* its object's signal (KOF +$D1 bit 7: tst) */
    case PC_SIG7C: { uint8_t e = f->pflags & PF_SIG7 ? 1 : 0; f->pflags &= ~PF_SIG7; return e; }   /* (bclr) */
    case PC_SIG6: return f->pflags & PF_SIG6 ? 1 : 0;
    case PC_FAR: { int16_t d; fighter_t *t = f->target ? f->target : f->popp; if (!t) return 1; d = INT(t->x) - INT(f->x); return (d < 0 ? -d : d) > v; }   /* (KOF +$BC; before a hit the nearest opponent on its lane) */
    case PC_LOW: return INT(f->y) < v;                           /* the height below v px (KOF cmpi.w #v, +$20; bcs) */
    case PC_WINDOW: return f->pan->steps[f->pstep].flags & 32 ? 1 : 0;  /* the step has KOF's $2000 (+$7C bit 5) */
    case PC_LINK: return f->plink & v ? 1 : 0;                   /* a follow-up of these links was pressed in the part */
    case PC_END: return f->pflags & PF_END ? 1 : 0;
    case PC_EVENT: { uint8_t e = f->pflags & PF_EVENT ? 1 : 0; f->pflags &= ~PF_EVENT; return e; }
    case PC_LAND: return f->pflags & PF_LAND ? 1 : 0;
    case PC_FALL: return f->pflags & PF_FALL ? 1 : 0;
    case PC_CNT: return f->pcnt < 0;
    case PC_HIT: return f->landed && f->pcatch != 2;            /* (a catch: KOF registers it after this frame's code) */
    case PC_OFF: return 0;
    case PC_WALL: return INT(f->x) >= wall_hi || INT(f->x) <= wall_lo;   /* at a wall (KOF98 $18092: either side) */
    case PC_HELD: return f->pheld;                               /* its button held (KOF and.b (fp): a charge) */
    case PC_CNTLE: return f->pcnt <= v;                          /* the counter at most v (KOF's charge level tests) */
    case PC_PASSED: { fighter_t *t = f->target ? f->target : f->popp; if (!t) return 0;   /* its opponent no longer ahead */
        return dir_mul(f->facing, INT(t->x) - INT(f->x)) <= v; }     /* (SS2 $563F4: Genjuro's slide stops at it) */
    case PC_THIGH: { fighter_t *t = f->vtgt ? f->vtgt : f->target;   /* its (phased) target above v px, not held by a */
        return t && !t->vph && INT(t->y) > v; }                  /* victim phase (Kizuna $3AC92, the Phoenix's ceiling) */
    case PC_TDOWN: return f->dtgt && f->dtgt->state == S_DOWN;   /* its down attack's target still lies (DD $230FA:
                                                                    the opponent no longer dizzy -> the fall) */
    case PC_CAUGHT: return f->pcatch != 0 && f->pcatch != 0xFE;   /* its catch box caught, its routine not started yet
                                                                    (SS2 Hanzo's Mozu Otoshi: the grab outranks the whiff's
                                                                    end, TODO #193) */
    }
    return 1;
}
static void prog_fxoff(fighter_t *f) {                           /* its pinned effects end (KOF: owner +$D1 bit 7), */
    uint8_t k;                                                   /* or launch: an object with a next phase becomes it */
    for (k = 0; k < 2; k++) {                                    /* where it is (vocabulary object.phase: Billy's fire */
        fighter_t *p = f->proj[k];                               /* ring, pinned, then flying, TODO #152) */
        if (!p || !p->pdef || !p->pdef->follow) continue;
        if (p->pdef->follow & 32) continue;                      /* it never reads the bit: it plays on (KOF98 Kyo's
                                                                    Orochinagi flame $3D83E, TODO #202) */
        if (p->pdef->next) p->pend = 4;                          /* launched from the next frame (proj_launch) */
        else if (p->pdef->follow & 64) p->pend = 6;              /* its end animation in place from the next frame (the
                                                                    release's glow $3D7E6: 244, TODO #202) */
        else projectile_reset(p);
        f->proj[k] = 0;
    }
}
static void prog_spawn(fighter_t *f, const bproj_t *d) {
    fighter_t *p = proj_start(f, d, f->x, f->facing, f->z);      /* rows: from the thrower's place now */
    if (!p) return;
    if (d->follow & 8) return;                                   /* a step effect: it ends itself (proj_update) */
    if (d->follow || d->kind == PK_BOOM) { if (!f->proj[0]) f->proj[0] = p; else if (!f->proj[1]) f->proj[1] = p; }   /* (a
                                                                    boomerang ends with the special: SS2 $4C434) */
    else f->shot = p;
}
static void prog_end(fighter_t *f) {
    special_end(f);
    if (f->y > 0) { f->vx = f->vy = f->vz = 0; f->jump_kind = f->jump_dir = 0; enter(f, S_AIR); play(f, BA_JUMP_UP_FALL); } else to_neutral(f, 0);
}
static void hold_apply(fighter_t *f) {                           /* a caught victim held (KOF +$E4 bit 4): in front of the */
    fighter_t *t = f->target;                                    /* attacker (P_PUT's distance, else where it stands), */
    if (!(f->pflags & PF_HOLD) || !t || t->state != S_HITSTUN) return;   /* reeling, facing it (a command grab: no stick rule) */
    if (f->phold) { t->x = f->x + dir_mul(f->facing, FIX(f->phold)); t->y = 0; clamp(t); }
    if (!t->vfly) t->vx = 0;                                     /* (a flying victim list keeps its flight) */
    t->kdelay = 0; t->state_t = 0; t->facing = -f->facing;
}
/* a catch's victim script (vocabulary hold.victim_list, TODO #173; KOF98 $25372): the caught target placed every frame
 * at the attacker + the entry of the attacker's current step (offset its facing's way, height, posture, facing,
 * drawn in front or behind); a step's first frame on a blow entry deals the move's hit (no hit-stop: KOF's victim
 * routine strikes, the attacker plays on), a release entry lets it go into its flight (KOF's 283: the blowback, its
 * x then held by the wall rule). The attacker's P_VSIG moves the victim to its next list (KOF +$D1 bit 7).
 * A frame list (VL_FRAMES, TODO #213: Kizuna's command grabs, the victim's thrown animation decoded frame by frame,
 * tools/kizuna/rosa_kz.py) takes entry k on the k-th frame since the P_VPHASE VA_LIST that started it; its release
 * lays the victim down (VL_DOWN) or sends it into a source reaction (VL_SREACT: Kizuna's thrown flight). */
/* the list's wall (vocabulary stage.wall "a victim list at the wall", TODO #216; KOF98 $255B0, the end of every list
 * place $25372): an entry that would put the victim at or past a wall ($18092 on the VICTIM: KOF's stage x 32 / 736,
 * the brawler's wall_lo / wall_hi) moves the ATTACKER instead, to the wall minus the list's farthest offset on that
 * side (the entries whose dx has this entry's sign), and places the victim again from there: every entry of the list
 * then fits inside the walls, the farthest one on the wall. Rugal's God Press slam: he stops at the wall, the slam's
 * list reaches 92 px ahead, so he stands 92 px from it (KOF: 736 -> 644) and the burst at +104 shows on screen. */
static void vlist_wall(fighter_t *f, fighter_t *t, const bvlist_t *l, const bvent_t *e) {
    int16_t x = INT(t->x);
    int32_t off, w, d0;
    uint8_t k, m = 0;
    if (x > wall_lo && x < wall_hi) return;
    for (k = 0; k < l->n; k++) {                                 /* the farthest entry on this entry's side */
        int8_t d = l->e[k].dx;
        if ((d < 0) != (e->dx < 0)) continue;
        if (d < 0) d = -d;
        if ((uint8_t)d > m) m = d;
    }
    off = dir_mul(f->facing, FIX(e->dx));                        /* (the victim's side of the attacker, world x) */
    w = FIX(x >= wall_hi ? wall_hi : wall_lo);
    d0 = (off >= 0 ? w - FIX(m) : w + FIX(m)) - f->x;
    f->x += d0; f->throw_x0 += d0;                               /* (its objects' anchor moves with it) */
    t->x = f->x + off;
}
static void vlist_place(fighter_t *f, const bspec_t *sp);
static void vlist_apply(fighter_t *f, const bspec_t *sp) {      /* KOF's victim routine (Yamazaki 236236C $6AF14, TODO
                                                                    #220): each frame the place ($25372) by the list it
                                                                    follows at the attacker's step (this frame's: a new
                                                                    animation's first), then the attacker's signal: the
                                                                    next list and its place at once (the routine falls
                                                                    into it), its entry's flags again (+$D2 = -1): the
                                                                    old list's and the new one's blows on the same frame */
    vlist_place(f, sp);
    while (f->vsigp) {
        f->vsigp--;
        if (f->vlist && !(f->vlist & 0x80)) { f->vlist++; f->vent = 0xFF; vlist_place(f, sp); }
    }
}
static void vlist_place(fighter_t *f, const bspec_t *sp) {
    fighter_t *t = f->target;
    const bvlist_t *l;
    const bvent_t *e;
    uint8_t k;
    if (!f->vlist || (f->vlist & 0x80) || !t || !(f->pflags & PF_HOLD)) return;   /* (0x80: P_CATCH's, from its routine) */
    l = &sp->vlists[f->vlist - 1];
    if (!l->n) { f->vlist = 0; return; }                         /* (past its last list: n 0 ends the table) */
    k = (l->flags & VL_FRAMES) ? f->vfr : f->pstep;              /* its entry: this frame's of the list, else the step's */
    if ((l->flags & VL_FRAMES) && f->vfr < 255) f->vfr++;
    e = &l->e[k < l->n ? k : l->n - 1];
    if (!(l->flags & VL_FLY) || f->vent == 0xFF) {               /* placed at the attacker + its entry (a flying list: */
        t->x = f->x + dir_mul(f->facing, FIX(e->dx)); t->y = f->y + FIX(e->dy); t->z = f->z;   /* once) */
        vlist_wall(f, t, l, e); clamp(t);                        /* (past a wall: the attacker steps back, KOF's rule) */
    }
    if (l->flags & VL_FLY) {                                     /* it flies on its own (SS2's rage victims): its */
        if (f->vent == 0xFF) { t->vx = dir_mul(f->facing, (int32_t)l->vx << 8); t->vy = (int32_t)l->vy << 8; }   /* velocities */
        else { t->x += t->vx; t->y += t->vy; t->vy -= (int32_t)l->g << 8; if (t->y < 0) t->y = t->vy = 0; clamp(t); }
        t->vfly = 2;                                             /* (its own update leaves the body to this list) */
    }
    t->facing = (e->flags & VE_TURN) ? f->facing : -f->facing;
    t->frame_ovr = e->pose < VP_COUNT && t->ch->vposes[e->pose] != 0xFFFF ? t->ch->vposes[e->pose] : 0xFFFF;
    t->zfront = (e->flags & VE_FRONT) ? 1 : 0;
    if (!(l->flags & VL_FLY)) t->vx = t->vy = 0;
    t->kdelay = 0; t->state_t = 0; if (t->state == S_KNOCKDOWN) enter(t, S_HITSTUN);
    if (f->vent == k) return;                                    /* (KOF: the flags act when the attacker's step changes) */
    f->vent = k;
    if (e->flags & VE_BLOW) {                                    /* the blow: the move's damage, its hit sound */
        fighter_hit(f, t, f->pdmg, R_HEAVY, 0);
        f->freeze = t->freeze = 0; t->vx = 0; t->kdelay = 0;
        hit_sfx(f->pfx);
        if (e->flags & VE_BURN) set_burn(t, (e->flags & VE_BURN) >> 4);   /* its burn (KOF $17AC0: Iori 624's purple) */
    }
    if ((e->flags & VE_REL) && (l->flags & VL_STAND)) {          /* a release that leaves it standing (TODO #220, KOF98
                                                                    Yamazaki MAX 236236C: 329 until the strike's hold
                                                                    hit takes it): still held, reeling in place, until
                                                                    a hit by another box (phh) */
        f->vlist = 0; f->phh = 1; f->phold = 0;
        t->frame_ovr = 0xFFFF; t->zfront = 0;
    } else if (e->flags & VE_REL) {                              /* the release: its flight (KOF 283, the blowback) */
        f->pflags &= ~PF_HOLD; f->phold = 0; f->vlist = 0;
        t->frame_ovr = 0xFFFF; t->zfront = 0;
        if (l->flags & VL_DOWN) {                                /* laid down where it is (Kizuna's thrown victim at its */
            t->vx = t->vy = 0; t->y = 0; enter(t, S_DOWN); play(t, BA_DOWN); return;   /* animation's end, $33BA6) */
        }
        react(t, f->facing, R_KNOCKDOWN, 0);
        if (l->flags & VL_SREACT) src_react(t, f->facing, (uint8_t)l->vx);   /* its source's flight (Kizuna's thrown */
        else if (l->flags & VL_VEL) {                            /* animation's motion); its */
            t->vx = dir_mul(f->facing, (int32_t)l->vx << 8); t->vy = (int32_t)l->vy << 8;
            if (l->g) { t->kmode = 2; t->kg = t->kgf = (int32_t)l->g << 8; t->kgfr = 0; t->kvfr = 0; t->kdelay = 0; }   /* g: */
        }                                                        /* its own gravity (KOF's routine, Iori 624: kof_fall) */
        else kof_react(t, f->facing, R_KNOCKDOWN, -128);         /* game's flight (SS2: the victim's velocity entry), */
    }                                                            /* the brawler's fall and landing from there */
}
/* ---- form (vocabulary form.change, Double Dragon's transformation; game.json roster[].form): a fighter declares a
 * trigger, a transition (one of its specials, role BS_FORM: untouchable while it plays) and a target roster entry; the
 * transition's P_FORM replaces the fighter's character data (bchar_t: frames, moves, specials, routes, palettes, HUD face
 * and name) in place: life, place, facing, meter, its slot and the enemies' targeting (fighter_t pointers) are kept; the
 * special ends there (its effects with it), the new form falls / stands with its own animations. Back to the base form
 * by its exit rule (fighter_revive; every player at a stage's start). Generic: any roster entry, any target. */
static void form_swap(fighter_t *f) {
    const bchar_t *to = &bm_chars[f->ch->form_to];
    if (!f->form_from) f->form_from = f->ch->id + 1;
    special_end(f); f->pflags = 0;
    if (f->inv == INV_FURY) f->inv = 0;
    form_set(f, to);
    f->vx = f->vy = f->vz = 0; f->jump_kind = f->jump_dir = 0;
    if (f->y > 0) { enter(f, S_AIR); play(f, BA_JUMP_UP_FALL); } else to_neutral(f, 0);
}
/* victim phases (TODO #136, vocabulary hold.victim_phase; Kizuna's +$1AF bits 4-7 + $1AE bit 0 on the victim, read by
 * its $2CD06 every frame): a special's P_VPHASE acts on its target while it reels or flies: VA_SNAP puts it at the
 * attacker's place ($2CE56: x / y copied), VA_FREEZE holds its body still (its +$106 bit 3: no move, no recovery, its
 * reaction's velocity kept for after), VA_MIRROR moves it by the attacker's own moves mirrored in x (+$107 bit 2,
 * $37A20: its velocity = -the attacker's) instead of its own; VA_THAW / VA_UNMIRROR end them; they end with the special
 * too (special_end) and when the victim leaves its reaction (enter). Its hits keep them [meas: 421A_h, 6246A_h].
 * VA_LIST (TODO #213, Kizuna's command grabs: the victim's request $043B / $043C, its handler places it from the grab
 * on): the target follows the special's victim list b from now, held (vlist_apply). */
static void vphase(fighter_t *f, uint8_t a, int16_t b) {
    fighter_t *t = f->vtgt ? f->vtgt : f->target;               /* (the one it took first: Kizuna's a3, the caught victim) */
    if (!t || (t->state != S_HITSTUN && t->state != S_KNOCKDOWN)) return;
    if (a & VA_LIST) { f->target = t; t->vph = 0; f->vlist = (uint8_t)b; f->vent = 0xFF; f->vfr = 0; f->pflags |= PF_HOLD; return; }
    f->vtgt = t; t->vph_by = f;
    if (a & VA_SNAP) { t->x = f->x; t->y = f->y; t->z = f->z; clamp(t); }
    if (a & VA_FREEZE) t->vph |= VPH_FREEZE;
    if (a & VA_THAW) t->vph &= ~VPH_FREEZE;
    if (a & VA_MIRROR) t->vph |= VPH_MIRROR;
    if (a & VA_UNMIRROR) t->vph &= ~VPH_MIRROR;
}
static void prog_update(fighter_t *f, const bspec_t *sp) {
    const bstep_t *s;
    uint8_t n;
    int32_t x0;
    if (f->pcatch == 2) {                                        /* a catch: KOF's dead frames ($1B402: the catching */
        if (!f->pdead) f->pdead = f->pdeadn;                     /* step's hit-stop + 1) */
        if (!--f->pdead) f->pcatch = 1;
        f->srow++; hold_apply(f); return;
    }
    if (f->pcatch == 1) {                                        /* then its routine (+$19C); its victim runs the */
        f->pcatch = 0xFE; f->pres = f->phit;                     /* routine the catch gave it (+$1A0): the first */
        if (f->vlist & 0x80) {                                   /* (P_CATCH: the list it named, held by it from */
            f->vlist &= 0x7F; f->vent = 0xFF; f->pflags |= PF_HOLD; f->phold = 0;   /* now: KOF's throw routine) */
        } else if (sp->vlists && !(sp->vlists[0].flags & VL_CATCH)) { f->vlist = 1; f->vent = 0xFF; }   /* list of its
                                                                    script (bspec_t.vlists; VL_CATCH: P_CATCH's alone) */
    }
    if (f->pcatch == 3) f->pcatch = 2;                           /* (the frame after the hit-stop runs as it was) */
    x0 = f->x;
    f->srow++;                                                   /* frames played (the reversal's invincibility) */
    if (f->spec_id == BS_DOWN_D && f->srow <= sp->inv_rows && f->inv < 2) f->inv = 2;
    f->ppc = f->pres;
    for (n = 0; n < 255; n++) {                                  /* (a frame's op budget: 255 since TODO #136, a Kizuna
                                                                    hit ending a 23-tick step runs its ticks out in one
                                                                    frame, 4 ops a tick: 421A's 100.3; was 96) */
        const bprim_t *p = &sp->prog[f->ppc++];
        int32_t v = p->v;
        uint8_t op = p->op;
        if (op & 0x80) { op &= 0x7F; v = sp->vars[(uint16_t)f->var * sp->vcols + p->b]; }   /* a variant column */
        switch (op) {
        case P_ANIM:
            f->pdmg = sp->vdmg ? (uint8_t)sp->vars[(uint16_t)f->var * sp->vcols + sp->vdmg - 1] : p->b & 0xFF;
            f->preact = p->b >> 8; f->pfx = v; pan_play(f, &sp->anims[p->a + (sp->nvar ? f->var * sp->vanim : 0)]); break;
        case P_SET:
            if (p->a == 0) f->vx = v; else if (p->a == 1) f->vy = v; else if (p->a == 2) f->pg = v;
            else if (p->a == 3) f->pfric = v; else if (p->a == 5) f->y = v; else f->pcnt = v;
            break;
        case P_MUL: if (p->a == 1) f->vy = fmul16(f->vy, v); else f->vx = fmul16(f->vx, v); break;
        case P_ADD: if (p->a == 0) f->vx += v; else if (p->a == 1) f->vy += v; else f->pcnt += v; break;
        case P_VOICE: if (p->b) { f->pvl_id = p->a; f->pvl_n = (uint8_t)p->b; } else prog_voice(f, p->a); break;
        case P_FORM: form_swap(f); return;                       /* the form link: the fighter is its other form now */
        case P_FRICMOVE: f->vx = fmul16(f->vx, f->pfric);        /* fall through: then x += vx */
        case P_MOVE: if (!f->pstill) { f->x += dir_mul(f->facing, f->vx); f->z += f->vz; clamp(f); } break;
        case P_HOME: {                                           /* the down attack's leap (vocabulary attack.down, TODO
                                                                    #218; DD $23070): vx = the distance to its target
                                                                    (whole px) >> a a frame (DD's << 10: a = 6), the fighter
                                                                    turned to face it; vz its depth >> a (the brawler's
                                                                    band: DD has none). 2^a frames of flight land on it */
            fighter_t *t = f->dtgt;
            int16_t d;
            if (!t) break;
            d = INT(t->x) - INT(f->x); f->facing = d >= 0 ? 1 : -1;
            f->vx = FIX(d < 0 ? -d : d) >> p->a; f->vz = (t->z - f->z) >> p->a;
            break;
        }
        case P_FALL: {
            int32_t v0 = f->vy;
            if (f->pstill) break;
            f->vy -= f->pg; f->y += v0; f->pflags &= ~(PF_LAND | PF_FALL);
            if (f->y <= 0 && p->a && f->y > -FIX(1)) f->y = 0;   /* a 1: SS2's floor ($27802 cmpi #224 / beq: a body on */
                                                                 /* the floor line itself has not landed; the next whole */
                                                                 /* pixel down lands it, TODO #191) */
            else if (f->y <= 0) { f->y = 0; f->pflags |= PF_LAND; }
            if (!(f->pflags & PF_LAND) && f->vy < 0) f->pflags |= PF_FALL;
            break;
        }
        case P_NUDGE: f->x += dir_mul(f->facing, FIX(p->b)); f->y += FIX(p->v); clamp(f); break;
        case P_DEC: f->pcnt--; break;
        case P_BR:
            if (pcond(f, p->a & 0x7F, p->v) == (p->a >> 7)) {
                if (p->b < 0) goto frame_done;
                f->ppc = p->b;
            }
            break;
        case P_RESUME: f->pres = f->ppc; break;
        case P_RESUMEAT: f->pres = p->b; break;
        case P_JMP: f->ppc = p->b; break;
        case P_SPAWN: prog_spawn(f, &sp->robj[p->a + (sp->nvar ? f->var * sp->vobj : 0)]); break;
        case P_FXOFF: prog_fxoff(f); f->pflags |= PF_SIG7; break;   /* KOF: +$D1 bit 7 */
        case P_SIGCLR: f->pflags &= ~(~p->v & (PF_SIG7 | PF_SIG6)); break;
        case P_HITOFF: f->landed = 0; break;                     /* KOF +$E1 bit 7 cleared */
        case P_ADV: pan_advance(f); break;                       /* the engine called again on the same state: one more step tick */
        case P_CHECK:                                            /* (b 2, a mash: KOF's fp@(5), this frame's press: */
            if (p->b == 2) {                                     /* one made early in its hit-stop is never read, nor */
                uint8_t m = f->spmash & p->a;                    /* one past the mash window, TODO #220) */
                f->plink |= m;
                if (m) f->mash = MASH_GAP;
                break;
            }
            f->plink |= (p->b ? f->phl : f->spend) & p->a; break;   /* the follow-up check: this frame's presses
                                                                    of links a (b: those made in its last hit-stop, KOF
                                                                    +$1AC: Iori 623D's landing, TODO #140) */
        case P_PART: f->plink = 0; break;                        /* the handler cleared its request: a new part */
        case P_EVCLR: f->pflags &= ~PF_EVENT; break;             /* the step's event consumed */
        case P_ONHIT: if (!f->pcatch) { f->phit = p->b; f->pdeadn = p->a + 1; } break;   /* its catch routine (KOF +$19C) */
        case P_PUT: f->phold = p->v; hold_apply(f); break;     /* the caught victim put in front of it */
        case P_HITCLR: f->pflags &= ~PF_HITANY; break;
        case P_HOLD: f->pflags |= PF_HOLD; break;
        case P_VSIG: if (f->vlist) f->vsigp++; break;            /* its caught victim's next list (KOF +$D1 bit 7; taken
                                                                    by vlist_apply after this frame's place) */
        case P_CATCH:                                            /* the engine's throw on its held victim (TODO #216, */
            f->pcatch = p->a ? 2 : 1; f->phit = p->b; f->pdeadn = p->a; f->pdead = 0;   /* KOF98 $3F8A: Iori 23624C's */
            f->vlist = 0x80 | (uint8_t)v; break;                 /* finisher): a dead frames, then routine b, list v
                                                                    (KOF98: the frame of the call is the throw's hit-stop
                                                                    frame, the routine runs the next: a 0) */
        case P_TURN: f->facing = -f->facing; break;              /* turned around: forward is the other way (KOF eori +$31) */
        case P_UNHOLD: f->pflags &= ~PF_HOLD; f->phold = 0; break;
        case P_VPHASE: vphase(f, p->a, p->b); break;             /* its target's victim phases (TODO #136; VA_LIST: TODO #213) */
        case P_SCREEN: f->pbd = p->a; break;                     /* its screen effect on / off (main.c screen_fx) */
        default:                                                 /* P_END (this frame still counts a voice to come) */
            if (f->pvl_n && !--f->pvl_n) prog_voice(f, f->pvl_id);
            prog_end(f); return;
        }
    }
frame_done:
    f->pstill = 0;
    if (f->pvl_n && !--f->pvl_n) prog_voice(f, f->pvl_id);    /* a voice sent later: KOF counts +$1B6 down after the
                                                                    code, the frame it was set included (KOF98 $17074) */
    f->spend = f->spmash = 0;                                    /* a press counts on the frame it is read */
    for (n = 0; n < 2; n++) {                                    /* its pinned effects follow this frame's move */
        fighter_t *p = f->proj[n];
        if (p && p->pdef && p->pdef->follow) { p->throw_x0 = pin_of(p)->x; p->facing = f->facing; proj_row(p); }
    }
    pan_advance(f);
    s = &f->pan->steps[f->pstep];
    f->frame_ovr = s->frame;
    f->spec_atk = (s->flags & 1) ? &s->atk : 0;
    f->spec_prev_hit = (s->flags & 1) ? 1 | (s->flags & 64 ? 16 : 0) | (s->flags & 128 ? 32 : 0) | ((s->flags & 4) && !(sp->sflags & SF_SREACT) ? 64 : 0)
                                        | (s->hy == HY_HOLD && !(sp->sflags & SF_SREACT) ? 128 : 0) : 0;   /* 16 a catch box, 32 no hit-stop, 64 no slide (under SF_SREACT flag 4 is its push box) */
    if ((f->pflags & PF_HOLD) && f->phold && f->target && f->target->state == S_HITSTUN && (f->x - x0) && ((f->x > x0) == (f->facing > 0)))
        f->x -= (f->x - x0) / 2;                                 /* walking into the held victim: KOF's bodies share the push */
    hold_apply(f);
    vlist_apply(f, sp);
    if (f->vtgt && f->vtgt->vph_by == f && (f->vtgt->vph & VPH_MIRROR) && !(f->vtgt->vph & VPH_FREEZE)) {   /* a mirrored */
        f->vtgt->x -= dir_mul(f->facing, f->vx); clamp(f->vtgt);   /* victim: the attacker's velocity, the other way (its */
    }                                                            /* steps' moves and pushes are no velocity: Kizuna $37A20) */
}
static void carry_drop(fighter_t *f) {                           /* a grab's carry ended: a target it left in the air */
    fighter_t *v = f->target;                                    /* falls (Ralf's 426B left it 4 px up for good) */
    if (!(f->spec_prev_hit & 4) || !v || v->y <= 0 || (v->state != S_HITSTUN && v->state != S_KNOCKDOWN)) return;
    enter(v, S_KNOCKDOWN); v->vx = v->vy = 0; play(v, BA_KNOCKDOWN_FLIGHT);
}
static int32_t rt_div(int32_t v, uint8_t d) {                   /* v / d (no libgcc: a long division) */
    uint32_t a = v < 0 ? -v : v, q = 0, r = 0;
    int8_t i;
    for (i = 31; i >= 0; i--) { r = (r << 1) | ((a >> i) & 1); if (r >= d) { r -= d; q |= 1UL << i; } }
    return v < 0 ? -(int32_t)q : (int32_t)q;
}
static void rt_prog(fighter_t *f, const bspec_t *sp) {           /* a ROM special's frame, retimed (see "retiming") */
    int32_t x0, y0;
    uint8_t end, h = 0;
    f->rt_debt += rt_adv(f); end = f->rt_flags & RT_END;
    if (!f->rt_debt) {                                           /* its source frame shown again: a share of its motion */
        if (f->rt_hold) { f->rt_hold--; f->x += f->rt_dx; f->y += f->rt_dy; clamp(f); }
        return;
    }
    while (f->rt_hold) { uint8_t k = f->rt_hold - 1; __asm__("" : "+d"(k)); f->rt_hold = k; f->x += f->rt_dx; f->y += f->rt_dy; }   /* (the last frame's share left: now) */
    x0 = f->x; y0 = f->y;
    while (f->rt_debt) {
        const banim_t *an = f->pan;
        uint8_t ps = f->pstep, prev = an ? an->steps[ps].flags : 0;
        prog_update(f, sp);
        if (sp->pvoice && f->state == S_SPECIAL) voice_at(f, VK_SPEC + f->spec_ix, f->srow - 1, f->srow - 1);
        f->rt_debt--;
        if (f->state != S_SPECIAL || f->pcatch) { f->rt_flags = 0; f->rt_debt = 0; return; }   /* over, or its catch: 1x */
        if (f->rt_debt && !end && (an != f->pan || ps != f->pstep) && (f->pan->steps[f->pstep].flags & 1) &&
            !((prev & 1) && (prev & 16))) break;                 /* a new hit window: shown, the rest carried */
        if (f->rt_debt && rt_probe(f)) break;                    /* (a source frame passed: its box tested) */
    }
    if (!end && !f->rt_debt && f->rt_p < f->rt_nseg) {           /* stretched: this source frame shows 1 + h frames, */
        uint16_t S = f->rt_S[f->rt_p], T = f->rt_T[f->rt_p] ? f->rt_T[f->rt_p] : S, e = f->rt_err;   /* its motion */
        while (e + S < T) { e += S; h++; }                       /* spread over them (the first takes the remainder) */
        if (h) {
            int32_t dx = f->x - x0, dy = f->y - y0;
            uint8_t i;
            f->rt_dx = rt_div(dx, h + 1); f->rt_dy = rt_div(dy, h + 1); f->rt_hold = h;
            for (i = 0; i < h; i++) { __asm__("" : "+d"(i)); f->x -= f->rt_dx; f->y -= f->rt_dy; }   /* (no __mulsi3) */
        }
    }
}
static void special_update(fighter_t *f) {
    const bspec_t *sp = &f->ch->specials[f->spec_ix];
    const bspec_row_t *r;
    uint8_t k;
    uint16_t from;
    if (sp->prog) {                                              /* read from the ROM: its program */
        if (f->rt_flags) { rt_prog(f, sp); return; }            /* retimed (see "retiming") */
        prog_update(f, sp);
        if (sp->pvoice && f->state == S_SPECIAL) voice_at(f, VK_SPEC + f->spec_ix, f->srow - 1, f->srow - 1);   /* its
                                                                    voices by its frames (bspec_t.pvoice: Double Dragon's) */
        return;
    }
    from = script_advance(f, sp->nrows, sp);                     /* rows from..srow-1 reached this frame */
    if (sp->nparts) {                                            /* follow-ups: a hit in a link's window arms it, */
        for (k = 0; k < sp->nlinks && !f->sarm; k++) {          /* an armed LK_NOW link switches at once, a part's
                                                                    end goes to the armed link's part or its next */
            const bslink_t *l = &sp->links[k];
            if (l->from == f->spart && l->trig == LK_HIT && f->shrow > l->lo && f->shrow <= l->hi) f->sarm = k + 1;
        }
        if (f->sarm && (sp->links[f->sarm - 1].at & LK_NOW)) part_go(f, sp, sp->links[f->sarm - 1].to);
        else if (f->srow > sp->parts[f->spart].end)
            part_go(f, sp, f->sarm ? sp->links[f->sarm - 1].to : sp->parts[f->spart].next);
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

/* ---- the flash pose (TODO #145, vocabulary fx.super_flash "flash pose") -----------------------------------------------
 * A fury whose source game has no flash step of its own (bchar_t.nfpose: Kizuna, SS2, WHP, Double Dragon; KOF's furies
 * start with their $FA flash step and play under the flash as before) shows the fighter's flash pose for the whole
 * freeze: the super flash starts on the fury's frame gflash.start, the pose's steps (export_bm fpose_steps: its taunt /
 * charge / win animation cut to gflash.freeze frames) show one by one, nothing of the fury runs; on the first frame
 * after the freeze the fury starts from its first frame (state_t gflash.start again, as it had under the flash) with
 * the world moving. A step that carries a voice (bfpose_t.voice, TODO #189) sends it as it shows. Returns 1 while the
 * pose shows (special_update waits). */
static void fpose_pal(fighter_t *f, uint8_t on) {               /* the pose's own colours (bchar_t.fpal, TODO #191: */
    const bchar_t *ch = f->ch;                                   /* SS2's rage palette) on its palette while it shows */
    uint16_t buf[16];
    uint8_t j;
    if (ch->fpal_ix == 0xFF || f->flash || f->burn) return;     /* (a white flash / a burn own the colours) */
    if (!on) { fighter_load_pals(f); return; }
    if (f->ovl) { f->ovl = 0; fighter_load_pals(f); }            /* (the red state's blink: off for the fury's pose) */
    buf[0] = 0;
    for (j = 1; j < 16; j++) buf[j] = fighter_colour(f, ch->fpal[(f->set << 4) + j]);
    PAL_setPalette(f->palbase + ch->fpal_ix, buf);
}
static uint8_t flash_pose(fighter_t *f) {
    const bchar_t *ch = f->ch;
    uint8_t k, i, at;
    if (f->spec_id != BS_FURY || !ch->nfpose || f->fpose == 0xFF) return 0;
    if (!f->fpose) {
        if (f->state_t != gflash.start) return 0;
        super_flash(f); f->fpose = 1; f->vx = f->vy = f->vz = 0;
        fpose_pal(f, 1);
    }
    k = f->fpose - 1;
    if (k >= gflash.freeze) {                                    /* the freeze is over: the fury from its first frame */
        f->fpose = 0xFF; f->frame_ovr = 0xFFFF; f->state_t = gflash.start;   /* (its colours kept to the fury's end:
                                                                    special_end, TODO #195) */
        return 0;
    }
    for (i = 0, at = 0; i + 1 < ch->nfpose && k >= at + ch->fpose[i].n; i++) at += ch->fpose[i].n;
    f->frame_ovr = ch->fpose[i].frame; f->fpose++;
    if (k == at && ch->fpose[i].voice && !mute) voice_id(ch, f->team, ch->fpose[i].voice);   /* its source's voice on this
                                                                    step (TODO #189: SS2's rage shout) */
    return 1;
}

/* the head point of the flash pose step showing now (bfpose_t hx / hy, TODO #191: the super flash's glow follows it;
 * main.c sf_draw): 0 when no pose shows. flash_pose shows step i for pose frame k = fpose - 2 after its update. */
uint8_t fighter_pose_head(const fighter_t *f, int16_t *dx, int16_t *dy) {
    const bchar_t *ch = f->ch;
    uint8_t i, at, k, ob;
    if (f->state != S_SPECIAL || f->spec_id != BS_FURY || !ch->nfpose || f->fpose < 2 || f->fpose == 0xFF) return 0;
    k = f->fpose - 2;
    ob = BANK_set(CH_BANK(ch));                                  /* (its pose table: wherever bank_pack put it) */
    for (i = 0, at = 0; i + 1 < ch->nfpose && k >= at + ch->fpose[i].n; i++) at += ch->fpose[i].n;
    *dx = ch->fpose[i].hx; *dy = ch->fpose[i].hy;
    BANK_set(ob);
    return 1;
}

/* ---- state machine --------------------------------------------------------------------------------------------- */
static void update(fighter_t *f, const intent_t *in);
void fighter_update(fighter_t *f, const intent_t *in) {         /* its bank mapped (fighter.h "banks"): its special's */
    uint8_t ob = BANK_set(CH_BANK(f->ch));                       /* rows, program, parts, links, its objects' rows; a */
    update(f, in);                                               /* form link swaps f->ch for a fighter of the same bank */
    BANK_set(ob);                                                /* (bank_pack.py) */
    flicker(f);
}
static void update(fighter_t *f, const intent_t *in) {
    const bphys_t *ph = &f->ch->phys;
    if (f->state == S_GRABBED && in->press && f->held && !f->held->srow && ++f->grab_hits >= ESCAPE_PRESSES) {   /* mash to
                                                                    break free (hit-stop too; never while a hold hit plays) */
        fighter_t *h = f->held;
        release(h); f->x += dir_mul(h->facing, FIX(10)); clamp(f); f->inv = 20; f->freeze = h->freeze = 0; stat_escapes++;
    }
    if (f->state == S_ATTACK || f->state == S_AIR_ATTACK) {      /* presses in hit-stop count */
        uint8_t ci = combo_input(f, in);
        if (ci) { f->buffered = ci; f->buf_age = 0; f->blz_buf = (ci & IN_A) && in->blitz && f->state == S_ATTACK ? in->blitz : 0; }   /* (a
                                                                    Blitz press: its slot, "Blitz"; the attack buffer's
                                                                    age, "chain core": the hit-stop */
        else if (f->buffered && !f->freeze && f->buf_age < 255 && !(f->landed && hits_to_come(f))) f->buf_age++;   /* does
                                                                    not age it (a latched press), nor a multi-hit link's
                                                                    hits still to come (the press waits for them) */
        if (in->press & IN_C) f->spec_buf = 0x80 | d_input(f, in);
        if ((in->press & IN_D) && !f->team) f->fury_buf = 0x80 | (in->dz > 0);   /* the cancel rule: D (down+D its MAX) */
    }
    if (f->state == S_GRAB && !(f->srow && f->throw_id == BT_HOLD_FIN) && (in->press & IN_D))   /* the hold: D for the */
        f->fury_buf = 0x80 | (in->dz > 0);                       /* fury (hold_update; presses in hit-stop count, TODO #208) */
    if ((f->state == S_THROW || (f->state == S_GRAB && f->srow && f->throw_id == BT_HOLD_FIN)) && !f->team) {   /* a throw /
                                                                    the hold finisher: C / D buffered for its last
                                                                    impact ("cancels" rule 4; presses in hit-stop count) */
        if (in->press & IN_C) { f->spec_buf = 0x80 | d_input(f, in); f->cnc_buf = CANCEL_BUF; }
        if (in->press & IN_D) { f->fury_buf = 0x80 | (in->dz > 0); f->cnc_buf = CANCEL_BUF; }
        if (!(in->press & (IN_C | IN_D)) && !f->freeze && f->cnc_buf && !--f->cnc_buf) f->spec_buf = f->fury_buf = 0;   /* too
                                                                    early: gone (a hit-stop does not age it) */
    }
    if (f->state == S_SPECIAL && may_cancel(f) && f->scancel && (in->press & IN_D) && !f->team)
        f->fury_buf = 0x80 | (in->dz > 0);                       /* a special that landed: D buffers its fury (a press
                                                                    before its first hit does nothing) */
    if (f->state == S_SPECIAL && may_cancel(f) && f->scancel && (in->press & IN_C) && !f->team)
        f->spec_buf = 0x80 | d_input(f, in);                     /* the ladder (Bruno 2026-10-08): a special / a Blitz that
                                                                    landed: C buffers ANOTHER special (special_cancel) */
    if (f->mash && (f->state != S_SPECIAL || !--f->mash)) f->mash = 0;   /* the mash window (real frames, MASH_GAP) */
    if (f->state == S_SPECIAL && in->press && f->ch->specials[f->spec_ix].nlinks) special_input(f, in);   /* a follow-up
                                                                    (presses in hit-stop count) */
    meter_tick(f);
    if (f->tb_by && f->state != S_KNOCKDOWN && f->state != S_HITSTUN) f->tb_by = 0;   /* a throw special's body: landed */
    if (f->jug_by && f->state != S_THROWN && f->state != S_KNOCKDOWN && f->state != S_HITSTUN) f->jug_by = 0;   /* landed:
                                                                    the juggle window (rule 5) closes */
    if (f->burn && f->state != S_HITSTUN && f->state != S_KNOCKDOWN) set_burn(f, 0);   /* landed or recovered */
    else if (f->burn && !f->flash && f->burn_t != burn_step()) burn_show(f);   /* the flame cycle's next step */
    if (f->freeze) {                                             /* hit-stop: nothing moves, nothing animates */
        if (!--f->freeze && f->state == S_SPECIAL && (f->ch->specials[f->spec_ix].sflags & SF_SREACT)) f->pstill = 1;   /* (a
                                                                    source reaction's game: Kizuna's attacker stands the
                                                                    frame after too, $2B644 not run [meas: 6246A_h 86.56,
                                                                    214B_h 93.5]) */
        return;
    }
    if (f->pvl_n && f->state != S_SPECIAL && !--f->pvl_n) prog_voice(f, f->pvl_id);   /* a ROM special's voice sent
                                                                    later counts on once the move ended (KOF $17074 runs
                                                                    every frame; in the special: prog_update's frames) */
    if (f->cthrow && f->state != S_THROW) { f->cthrow = 0; if (f->inv == INV_FURY) f->inv = 0; }   /* the chain's back throw
                                                                    returned control: untouchable no more */
    if (f->inv == INV_FURY) {                                    /* held for the fury's script (and a form's transition, */
        if (!f->cthrow && (f->state != S_SPECIAL || (f->spec_id != BS_FURY && f->spec_id != BS_FORM && f->spec_id != BS_THROW &&   /* a move with */
                                      !(f->ch->specials[f->spec_ix].sflags & SF_INV) && !f->brk && !f->sinv))) f->inv = 0;   /* SF_INV; */
    }                                                            /* a breaker; a C special (sinv); a chain's back throw) */
    else if (f->inv) f->inv--;
    if (f->guard && !--f->guard) f->guard_by = 0;                /* a player's untouchable window after a hit ("guard") */
    if (f->chain_t) f->chain_t--;
    if ((f->state == S_HITSTUN || f->state == S_GRABBED) && (in->press & IN_C) && !dancing(f)) {   /* the breaker (Bruno
                                                                    2026-10-08): C or A+B while hit (not in a fury's dance)
                                                                    = ALWAYS the fighter's neutral C special, whatever the
                                                                    stick; its price: breaker_pay ("the meter") */
        uint8_t k = special_pick(f, BS_D);
        if (k != 0xFF) {
            uint8_t how = breaker_pay(f);
            if (f->state == S_GRABBED && f->held) release(f->held);
            f->frame_ovr = 0xFFFF; f->vx = f->vy = f->vz = 0; f->y = 0;
            lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, k); start_special(f, k);
            if (!f->team) { f->brk = 1; f->brkr = how == 2; f->inv = INV_FURY; }   /* it blinks white (red: paid in life)
                                                                    to its end (pal_overlay), untouchable to its end */
            return;
        }
    }
    if (in->chord && (in->press & IN_C) && (f->state == S_PREJUMP ||   /* A+B = C with its second button late: the first */
        (f->state == S_ATTACK && !f->landed && f->state_t <= gblitz.chord + 1))) {   /* one's prejump / normal (its first
                                                                    frames, no hit) gives way to the C, from neutral now */
        f->spec_buf = f->fury_buf = 0; f->buffered = 0; f->blz_buf = 0; f->rt_flags = 0; f->vx = f->vz = 0; f->y = 0;
        enter(f, S_IDLE); play(f, BA_IDLE);
    }
    f->state_t++;
    f->pushing = 0;
    if (f->state != S_SPECIAL && f->state != S_THROW && f->state != S_GRAB && !air_hold(f)) { if (f->rt_flags) rt_anim(f); else anim_tick(f); }   /* this frame's time first (see the animation player;
                                                                    an air attack's last active step held: air_hold);
                                                                    a script (special, throw) keeps its own in acc */
    switch (f->state) {
    case S_IDLE: case S_WALK: case S_RUN: neutral: {
        uint8_t b = in->press;
        if (b & IN_B) { jump_start(f, in, f->chain_t ? NODE(f, f->chain_node)->next[RI_B] : 0); break; }   /* inside a chain
                                                                    window: the route's B link (a jump-cancel; the chain
                                                                    trees have none since 2026-10-08) */
        if (in->ai && in->face) f->facing = in->face;            /* an AI fighter faces its target, always: moving away it */
        else if (in->dx) f->facing = in->dx;                     /* walks backwards (Bruno 2026-10-08); a player: beat 'em */
        else if (in->face) f->facing = in->face;                 /* up, face where you walk */
        if (b & IN_D) {                                          /* D: the fury (fury_press) */
            uint8_t k = fury_press(f, in->dz > 0);
            if (k != 0xFF) { lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, k == BS_FORM ? BS_FORM : BS_FURY); start_special(f, k); }
            break;
        }
        if (b & IN_C) {                                          /* C: the slot's special (the stick picks the slot): a drive
                                                                    chunk, invincible (cspecial); none left: nothing */
            uint8_t k = special_for(f, in);
            if (k == 0xFF) start_node(f, TREE(f)->nospec, LH_NEUTRAL);
            else if (pay(f, PAY_SPECIAL, 0)) { lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, k); cspecial(f, k); }
            break;
        }
        if ((b & IN_A) && (in->blitz || f->state == S_RUN) &&    /* the Blitz: a double direction + A (run + A: its ff */
            blitz_go(f, in->blitz ? in->blitz - 1 : BZ_FF, LH_NEUTRAL)) break;   /* slot, the dash attack) */
        if ((b & IN_A) && in->dz && in->lie && spec_ix(f->ch, BS_DOWNATK) != 0xFF) {   /* up / down + A, an opponent */
            fighter_t *t = in->lie;                              /* lying in reach: the down attack at it (DD's 8 / 2 + a */
            lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, BS_DOWNATK);  /* button, TODO #218) */
            start_special(f, BS_DOWNATK); f->dtgt = t; t->dpin++;
            break;
        }
        if (b & IN_A) {
            uint8_t ci = combo_input(f, in), nx = f->chain_t ? chain_next(f, NODE(f, f->chain_node), ci) : 0;
            if (nx) { route_go(f, nx, ci, in, LH_WINDOW); break; }   /* the route goes on (Final Fight: tap, wait, tap) */
            if (f->state == S_RUN) { blitz_dash(f, LH_NEUTRAL); break; }   /* dash attack (a fighter without an ff Blitz) */
            nx = next_node(NODE(f, TREE(f)->root), ci);          /* a route starts: the root's links */
            if (nx) start_node(f, nx, LH_NEUTRAL);
            break;
        }
        if (f->state == S_RUN && in->dx == f->facing) {          /* run = walk x gwalk_run (sub-pixel) */
            f->x += dir_mul(f->facing, mul88(f->wspd, gwalk_run)); f->z += dir_mul(in->dz, FIX(1)); clamp(f); break;
        }
        if (in->run && in->dx) { enter(f, S_RUN); play(f, BA_RUN); f->speed = f->wrate; break; }   /* (its stride: walk_rate) */
        to_neutral(f, in);
        if (f->state == S_WALK) {                                /* the walk by archetype, sub-pixel (walk_rate) */
            f->x += dir_mul(in->dx, in->slow ? f->wspd >> 1 : f->wspd); f->z += dir_mul(in->dz, in->slow ? FIX(1) >> 1 : FIX(1)); clamp(f);
            f->pushing = in->dx != 0 && (!f->team || in->grab);   /* facing follows dx: walking forward; enemies on purpose */
        }
        break;
    }
    case S_PREJUMP:                                              /* the one jump's crouch ("jumps"): the press frame + */
        if (f->state_t > gjump.crouch) {                         /* gjump.crouch frames on the ground (Final Fight: 1 + 7) */
            f->vx = f->vy = 0; f->jump_kind = 0;
            enter(f, S_AIR); play(f, JUMP_ANIM[0][f->jump_dir][0]); f->jt = 1; f->aact = 0;
            jump_frame(f);                                       /* its first air frame now */
        }
        break;
    case S_AIR: case S_AIR_ATTACK:
        if (f->drop) {                                           /* the respawn's drop: no control, untouchable */
            f->inv = 2; f->y += f->vy; f->vy -= ph->gravity;
            if (f->y <= 0) { f->y = 0; f->vy = 0; f->drop = 2; f->inv = RESPAWN_INV; enter(f, S_LAND); play(f, BA_LAND); }
            break;
        }
        if (f->state == S_AIR && (in->press & (IN_A | IN_C))) {  /* an air special (air_pick, TODO #221): A / C with the */
            uint8_t k = air_pick(f, in);                         /* stick's slot (TODO #200: Kim's j.2B dive, #211: Hanzo */
            if (k != 0xFF && (air_button(f->ch, k) == IN_A || pay(f, PAY_SPECIAL, 0))) {   /* SS2's shuriken,
                                                                    #213 / #221: Rosa's j.2C, j.623C, j.421C; its program
                                                                    from here) */
                lab_note(f, LE_SPECIAL, 0, LH_NEUTRAL, BS_AIR);
                f->spec_ix = k; start_special(f, BS_AIR); break;
            }
        }
        if (f->state == S_AIR && (in->press & IN_A)) {           /* A: the air attacks (Bruno 2026-10-08, "jumps"): down+A
                                                                    its down attack (air_b: a flinch, active to the landing),
                                                                    else the jump's attack: a straight jump's (air_a), a
                                                                    forward / back jump's (air_cd), both knocking down */
            uint8_t nx = f->air_node ? f->air_node : in->dz > 0 ? TREE(f)->air_b : f->jump_dir ? TREE(f)->air_cd : TREE(f)->air_a;
            start_node(f, nx, f->air_node ? LH_CANCEL : LH_NEUTRAL); f->air_node = 0; f->aact = 0;
        } else if (f->state == S_AIR_ATTACK && f->node == TREE(f)->air_b && (in->press & IN_A) && in->dz <= 0 &&
                   (f->landed || gjump.down_any)) {              /* down+A -> the jump's attack (on hit; Final Fight's
                                                                    order: the down attack first) */
            start_node(f, f->jump_dir ? TREE(f)->air_cd : TREE(f)->air_a, LH_CANCEL); f->aact = 0;
        } else if (f->state == S_AIR_ATTACK && f->buffered && !(NODE(f, f->node)->flags & RF_KEEP) && !BUF_OK(f, in)) {
            f->buffered = 0;                                     /* a player's press too old (the attack buffer) */
        } else if (f->state == S_AIR_ATTACK && f->landed && f->buffered &&   /* an air route: A on hit, its next air hit */
                   (!(NODE(f, f->node)->flags & RF_KEEP) || f->anim_done)) {
            uint8_t nx = next_node(NODE(f, f->node), f->buffered);
            if (nx) start_node(f, nx, LH_CANCEL);
        }
        if (f->jt) {                                             /* the one jump: its table ("jumps") */
            if (jump_frame(f)) { f->y = 0; f->vx = f->vy = f->vz = 0; f->air_node = 0; enter(f, S_LAND); play(f, BA_LAND); }
            break;
        }
        f->y += f->vy; f->vy -= f->jump_kind ? ph->hop_gravity : ph->gravity; f->x += f->vx; f->z += f->vz; clamp(f);   /* (a
                                                                    fall that is not the jump: gravity) */
        if (f->state == S_AIR && f->vy < 0 && f->anim == JUMP_ANIM[f->jump_kind][f->jump_dir][0])
            play(f, JUMP_ANIM[f->jump_kind][f->jump_dir][1]);
        if (f->y <= 0) { f->y = 0; f->vx = f->vy = f->vz = 0; f->air_node = 0; enter(f, S_LAND); play(f, BA_LAND); }
        break;
    case S_LAND:                                                 /* the one jump's landing ("jumps"): gjump.land frames; */
        if (f->state_t >= gjump.land) { to_neutral(f, in); break; }
        if (f->state_t >= gjump.land_cancel && (in->press || in->dx || in->dz)) { to_neutral(f, in); goto neutral; }   /* any
                                                                    input ends it from land_cancel on and acts now (Final
                                                                    Fight's landing cancels at once) */
        break;
    case S_ATTACK: {
        const rnode_t *c = NODE(f, f->node);
        if (f->landed && !(c->flags & RF_AIR) && fury_cancel(f)) break;   /* the cancel rule: D on contact, the fury */
        if (f->landed && f->spec_buf && !(c->flags & RF_AIR)) {  /* a special cancels a normal that hit: cut short */
            uint8_t d = f->spec_buf & 0x7F, nx = c->next[d], k;    /* the route's link for the input, else (a diagonal) */
            if (!nx && d >= RI_DFS) nx = c->next[d == RI_DFS ? RI_DS : RI_US];   /* down / up's, else plain C's */
            if (!nx) nx = c->next[RI_S];
            f->spec_buf = 0;
            k = nx ? special_pick(f, NODE(f, nx)->anim) : f->team ? 0xFF : special_pick(f, d - RI_S);   /* no link: the
                                                                    cancel rule, the special C + this stick picks
                                                                    (players; enemies keep their routes' links) */
            if (k != 0xFF && pay(f, PAY_SPECIAL, 0)) { lab_note(f, LE_SPECIAL, nx, LH_CANCEL, k); cspecial(f, k); if (nx) f->speed = NODE(f, nx)->speed; break; }
        }
        if (f->node == TREE(f)->dash) f->blz_buf = f->buffered = 0;   /* a Blitz played as the dash entry cancels only into a
                                                                    special: never into a Blitz (Bruno 2026-10-08: ff+A
                                                                    into ff+A was an infinite) nor back into the chain */
        if (f->landed && f->blz_buf && !(c->flags & RF_AIR)) {   /* the ladder (Bruno 2026-10-08): a normal that hit (a link,
                                                                    a finisher) cancels into the Blitz ("Blitz") */
            uint8_t s = f->blz_buf - 1;
            f->blz_buf = 0;
            if (blitz_go(f, s, LH_CANCEL)) break;
        }
        if (f->buffered && !(c->flags & RF_KEEP) && !BUF_OK(f, in)) f->buffered = 0;   /* a player's press too old: dropped
                                                                    (the attack buffer) */
        if (f->landed && f->buffered && !(c->flags & RF_KEEP) && !hits_to_come(f)) {   /* cancel on hit: the next link now
                                                                    (after the hit-stop; a multi-hit link once its last
                                                                    hit came: the link's whole damage, "chain core") */
            uint8_t nx = chain_next(f, c, f->buffered);
            if (nx) { lab_note(f, LE_END, f->node, LH_CANCEL, 1); route_go(f, nx, f->buffered, in, LH_CANCEL); break; }
        }
        if (f->anim_done && c->next[RI_THEN]) {                  /* (Kim gold) a finisher of several moves: the next one
                                                                    now, back to back, hit or not (RI_THEN) */
            lab_note(f, LE_END, f->node, LH_AFTER_END, f->landed);
            start_node(f, c->next[RI_THEN], LH_AFTER_END); break;
        }
        if (f->anim_done) {                                     /* played to its end (keep flag, or no input yet) */
            uint8_t nx = f->buffered && f->landed ? chain_next(f, c, f->buffered) : 0;   /* routes chain only on a hit */
            lab_note(f, LE_END, f->node, LH_AFTER_END, f->landed);
            if (nx) { route_go(f, nx, f->buffered, in, LH_AFTER_END); break; }
            if (!f->landed && f->blz_buf && BUF_OK(f, in) && blitz_go(f, f->blz_buf - 1, LH_NEUTRAL)) break;   /* a whiff: a
                                                                    Blitz pressed in its last frames comes out as it ends */
            if (!f->landed && (f->buffered & IN_A) && !in->ai && BUF_OK(f, in) &&
                (nx = next_node(NODE(f, TREE(f)->root), f->buffered)) != 0) {   /* a whiff: a press in its last frames */
                start_node(f, nx, LH_NEUTRAL); break;            /* starts the chain again at link 1 (the attack buffer) */
            }
            if (f->landed && has_links(c)) { f->chain_node = f->node; f->chain_t = CHAIN_WINDOW + 1; lab_note(f, LE_CHAINWIN, f->node, 0, CHAIN_WINDOW); }   /* tap later: still the route
                                                                    (+ 1: counted down before it is read, so a press on
                                                                    each of the CHAIN_WINDOW frames after this one takes it) */
            to_neutral(f, in);
        }
        break;
    }
    case S_HITSTUN:
        if (f->vph && (!f->vph_by || f->vph_by->state != S_SPECIAL)) f->vph = 0;   /* (its holder's special over) */
        if (f->vph) break;                                       /* held by a special's victim phase (vphase): still, no recovery */
        if (f->vfly) { f->vfly--; break; }                       /* a victim list flies it (vlist_apply, VL_FLY) */
        if (f->y > 0) {                                          /* a dance's catch (TODO #150): down to the floor fast */
            f->y += f->vy; f->vy -= DANCE_DROP;
            if (f->y <= 0) f->y = f->vy = 0;
        }
        if (f->kdelay) f->kdelay--;                              /* KOF's shake after a special's hit: in place */
        else if (f->ksr) {                                       /* a source reaction's reel: its slide, n frames */
            if (f->ksn) { f->ksn--; f->x += f->vx; f->vx += f->kax; clamp(f); } else f->vx = 0;
        }
        else { f->x += f->vx; f->vx = f->kvfr ? fmul16(f->vx, f->kvfr) : f->vx - (f->vx >> 3); clamp(f); }
        if (dancing(f)) break;                                   /* a fury's victim: in its reel until the fury ends */
        if (f->hp <= 0) { react(f, f->facing > 0 ? -1 : 1, R_KNOCKDOWN, 0); break; }   /* its dance over, no life: it falls */
        if (f->state_t >= (f->dizzy ? f->dizzy : !f->team ? gchain.stun_player : f->anim == BA_HIT_STAND_HEAVY ? gchain.stun_heavy : gchain.stun_light) && !f->y) { f->frame_ovr = 0xFFFF; to_neutral(f, 0); }   /* a hold's pose ends (a stun strike's dizziness: f->dizzy) */
        break;
    case S_KNOCKDOWN:
        if (f->vph && (!f->vph_by || f->vph_by->state != S_SPECIAL)) f->vph = 0;
        if (f->vph) break;                                       /* held by a special's victim phase (vphase) */
        if ((f->kmode || f->ksr) && f->kdelay) { f->kdelay--; break; }   /* KOF's shake after the hit-stop: in place */
        if (f->ksr) { if (src_fall(f)) break; }                  /* a source reaction (src_react) */
        else if (f->kmode) kof_fall(f);                          /* a special's hit: KOF98's reaction */
        else { f->y += f->vy; f->vy -= GRAVITY_KD; f->x += f->vx; clamp(f); }
        /* KOF98's fall (a C+D captured on Yuri: 285 / 283 counter rising 26 frames, 287 falling 13, 309 hitting the floor
         * 4, 313 a 2 px bounce 10, 328 down): blowback up, flight down, bounce on the floor, the small hop, down */
        if (f->y <= 0 && f->kslam) {                             /* a slam (the chain's down finisher, RE_SLAM): it */
            f->y = 0; f->kslam = 0; f->kmode = 0; f->vy = FIX(6); f->vx = dir_mul(-f->facing, FIX(1));   /* bounces up off */
            play(f, BA_BLOWBACK_N); break;                       /* the floor at once, juggle-able ("chain core") */
        }
        if (f->y <= 0) {
            f->y = 0; f->kmode = 0; f->kvfr = 0; f->kfloor = 1;  /* (downed: untouchable from here, "juggle cap") */
            if (f->anim == BA_KNOCKDOWN_BOUNCE) {                /* on the floor until it played, then the hop */
                f->vy = 0; f->vx -= f->vx >> 2;
                if (f->anim_done) { f->vy = FIX(1); play(f, BA_KNOCKDOWN_FALL); }
            } else if (f->anim == BA_KNOCKDOWN_FALL) { f->vx = f->vy = 0; enter(f, S_DOWN); play(f, BA_DOWN); }
            else { f->vy = 0; f->vx >>= 1; play(f, BA_KNOCKDOWN_BOUNCE); set_burn(f, 0); }   /* KOF98: a burn ends at the floor */
        } else if (f->vy < 0 && (f->anim == BA_BLOWBACK || f->anim == BA_BLOWBACK_N)) play(f, BA_KNOCKDOWN_FLIGHT);
        break;
    case S_DOWN:
        if (f->state_t >= DOWN_FRAMES && (!f->dpin || f->state_t >= DOWN_FRAMES + DOWN_PIN)) {   /* (a down attack coming:
                                                                    it lies on, TODO #218) */
            if (f->hp <= 0) {                                    /* the death: main decides (blink out, a life, or */
                enter(f, S_DEAD); if (!f->ko_voice) voice_play(f->ch, f->team, VK_KO);   /* continue); its KO voice, once, every death */
                f->ko_voice = 0;
                break;
            }
            enter(f, S_GETUP); play(f, BA_GETUP); f->inv = INV_GETUP;
        }
        break;
    case S_GETUP:
        if (f->anim_done) to_neutral(f, 0);
        break;
    case S_GRAB: hold_update(f, in); break;
    case S_THROW: throw_update(f, in); break;
    case S_THROWN: thrown_update(f); break;                      /* its thrower let go: it plays its rows on alone */
    case S_SPECIAL:
        if (may_cancel(f) && f->scancel && f->y == 0 && !(f->pflags & PF_HOLD) && f->fury_buf &&
            (f->pcatch == 0 || f->pcatch == 0xFE) && fury_buy(f, f->fury_buf & 1, 1) == 0xFF)
            f->fury_buf = 0;                                     /* not payable (the meter, the red state): it plays on */
        if (may_cancel(f) && f->scancel && f->y == 0 && !(f->pflags & PF_HOLD) && f->fury_buf &&
            (f->pcatch == 0 || f->pcatch == 0xFE)) {             /* a catch: once its routine lets the victim go
                                                                    (PF_HOLD off: its final impact), rules 2 / 3 */
            if (f->spec_id == BS_FURY) {                         /* a fury -> its MAX (rule 3): the fury's objects go */
                uint8_t i;                                       /* with it (shots, eruptions, pinned effects), so the */
                for (i = 0; i < NPJ; i++)                        /* MAX spawns whole (feedback 20261006-174005-5d29) */
                    if (projectiles[i].state == S_PROJ && projectiles[i].owner == f) projectile_reset(&projectiles[i]);
            }
            if (f->pcatch == 0xFE) juggle_open(f, f->target);   /* a catch's slam: rule 5, its victim juggled */
            carry_drop(f); special_end(f); f->pflags = 0;        /* the super cancel ("cancels"): the special stops, */
            if (fury_cancel(f)) break;                           /* the fury starts this frame */
            to_neutral(f, 0); break;                             /* (payable above: not reached) */
        }
        if (may_cancel(f) && f->scancel && f->y == 0 && !(f->pflags & PF_HOLD) && f->spec_buf &&
            (f->pcatch == 0 || f->pcatch == 0xFE)) {             /* the ladder: a special / Blitz that landed -> ANOTHER */
            uint8_t k = special_pick(f, (f->spec_buf & 0x7F) - RI_S);   /* special (C + the stick), on the ground, a drive
                                                                    chunk; the same special, or none payable: the press
                                                                    is dropped, it plays on */
            f->spec_buf = 0;
            if (k != 0xFF && spec_ix(f->ch, k) != f->spec_ix && pay(f, PAY_SPECIAL, 0)) {
                if (f->pcatch == 0xFE) juggle_open(f, f->target);   /* (a catch's slam: rule 5, its victim juggled) */
                carry_drop(f); special_end(f); f->pflags = 0;
                lab_note(f, LE_SPECIAL, 0, LH_CANCEL, k); cspecial(f, k);
                break;
            }
        }
        f->pheld = in && (in->hold & (f->spec_id == BS_AIR ? air_button(f->ch, f->spec_ix) : f->spec_id == BS_BLITZ ? IN_A :
                                      f->spec_id >= BS_FURY ? IN_D : IN_C)) ? 1 : 0;   /* its button held (PC_HELD) */
        if (flash_pose(f)) break;                                /* a fury's flash pose: the freeze shows it ("flash pose") */
        special_update(f);
        if (f->state == S_SPECIAL && f->spec_id == BS_FURY && f->state_t == gflash.start && !f->ch->nfpose)
            super_flash(f);                                      /* every fury, MAX or not (fx.super_flash, game.json
                                                                    super_flash: state_t 1 = its first frame) */
        break;
    default: break;
    }
}

/* ---- being hit ---------------------------------------------------------------------------------------------------- */
void fighter_hit(fighter_t *a, fighter_t *v, uint8_t damage, uint8_t reaction, int8_t push) {
    uint8_t rk;                                                  /* R_* | 8 when KOF's reaction keeps a hurt box */
    uint8_t caught = 0;                                          /* a ROM special's catch box took it (CATCH_STOP) */
    uint8_t sr = a->state == S_SPECIAL && a->spec_sr ? (v->y > 0 ? a->spec_sr >> 4 : a->spec_sr & 15) : 0;   /* its source
                                                                    reaction (standing / airborne: Kizuna's situation) */
    if (reaction > 15) reaction = v->y > 0 && (sr || !(a->state == S_SPECIAL && a->spec_id == BS_FURY && (reaction & 7) <= R_HEAVY))
                                  ? reaction >> 4 : reaction & 15;   /* packed: standing | juggled << 4 (a fury's reel: the
                                                                    standing one, its dance catches the airborne, TODO #150;
                                                                    a source reaction: its own airborne one) */
    else if (reaction == R_LAUNCH) reaction |= 8;                /* a bare R_*: KOF's defaults (only the launch, 286) */
    rk = reaction == RK_HIGH ? R_LAUNCH | 16 : reaction;         /* (KOF's high launch, 299: kof_react) */
    reaction = reaction == RK_HIGH ? R_LAUNCH : reaction & 7;
    v->pvl_n = 0;                                                /* its voice to come: dropped (KOF $170D8 clears +$1B6) */
    if (a->state == S_SPECIAL && (a->spec_id == BS_THROW || a->sthr) && v->tb_by != a) { v->tb_by = a; v->hit_mask = 0; }   /* a
                                                                    throw special's victim: a thrown body (revamp 3) */
    if (v->state == S_THROWN) {                                  /* rule 5: hit in its throw's flight: the script ends */
        if (IS_THROW(v->throw_id)) v->hp -= v->thr_dmg - v->throw_dealt;   /* (the throw's damage still dealt) */
        v->held = 0; v->thr = 0; v->frame_ovr = 0xFFFF; v->zfront = 0;
    }
    if (a->state == S_SPECIAL && a->ch->specials[a->spec_ix].prog) {   /* a ROM special (TODO #139): */
        a->pflags |= PF_HITANY;
        if ((a->spec_prev_hit & 16) && a->phit != 0xFF && !a->pcatch) {   /* a catch box: no damage, the victim held, */
            a->pcatch = 3; a->pflags |= PF_HOLD; a->phold = 0; damage = 0; caught = 1;   /* its routine after the hit-stop */
        }
        if (a->spec_prev_hit & 128) {                            /* a hold hit (KOF's box $36, TODO #220): its victim */
            a->pflags |= PF_HOLD; a->phold = 0; a->phh = 1;      /* held by the attacker's victim routine (+$1A0) */
        } else if (a->phh && (a->pflags & PF_HOLD) && v == a->target && !caught) {   /* another box on it: let go, its */
            a->pflags &= ~PF_HOLD; a->phh = 0;                   /* own reaction (Yamazaki MAX's last strike: the launch) */
        }
        if ((a->pflags & PF_HOLD) && (v == a->target || a->pcatch == 3 || a->spec_id == BS_FURY)) rk = reaction = R_HEAVY;
                                                                 /* held: a reel in place (a fury's hold: its whole crowd) */
    }
    if (a->state == S_SPECIAL && a->spec_id == BS_FURY) v->dance = a;   /* a fury's victim (dance) */
    if (a->state == S_SPECIAL || a->state == S_PROJ) v->wall_by = a;   /* a special's victim: the wall rule (wall_update) */
    if (a->state == S_PROJ || a->state == S_SPECIAL) {          /* the damage tier of a special, a fury, a MAX and their
                                                                    objects ("damage tiers"; the fighter's roster[].damage
                                                                    on a special not measured); normals (their route
                                                                    nodes: routes.py chain_tree), throws and holds as they are */
        fighter_t *o = a->owner ? a->owner : a;
        uint32_t d = (uint32_t)(uint16_t)damage * (uint16_t)a->dsc + o->dacc;
        damage = (uint8_t)(d >> 8); o->dacc = (uint8_t)d;
    }
    v->hp -= damage + (a->owner ? a->owner : a)->power;
    {   fighter_t *o = a->owner ? a->owner : a;                  /* the hidden fury gauge ("the meter"): the damage dealt (not
                                                                    a fury's own) and taken */
        uint8_t d = damage + o->power;
        if (o->team != v->team && !(o->state == S_SPECIAL && o->spec_id == BS_FURY)) gauge_add(o, (uint16_t)d * gmeter.fury_dealt);
        gauge_add(v, (uint16_t)d * gmeter.fury_taken);
    }
    if (v->hp > 0) voice_play(v->ch, v->team, VK_HIT);          /* the KO voice: once, at the death (S_DEAD) */
    {   uint8_t hs = (a->state == S_ATTACK || a->state == S_AIR_ATTACK) && NODE(a, a->node)->hitstop ? NODE(a, a->node)->hitstop : HITSTOP;
        v->freeze = !caught ? hs : a->pdeadn > HITSTOP - CATCH_STOP + 1 ? CATCH_STOP : HITSTOP + 1 - a->pdeadn;   /* a normal:
                                                                    its node's (the chain core's scale) */
    }
    {   fighter_t *o = a->owner ? a->owner : a;                  /* the chain core: an air hit counts toward the juggle cap */
        if (v->y > 0 && v->state == S_KNOCKDOWN && !(o->state == S_SPECIAL && o->spec_id == BS_FURY) && v->jug_n < 255) v->jug_n++;
        if (!v->team && v->state != S_PROJ) { v->guard = gchain.guard_player; v->guard_by = o; }   /* a player: untouchable
                                                                    to all but this attacker a moment ("guard") */
    }
    if (a->state != S_PROJ) a->freeze = v->freeze;               /* hit-stop; projectiles fly on (nothing updates them) */
    a->hit_mask |= 1 << v->idx; a->landed = 1; v->chain_t = 0;
    {   fighter_t *o = a->owner ? a->owner : a;                  /* the cancel rule: a special that landed (its body, */
        if (o->state == S_SPECIAL && may_cancel(o) && (o == a || o->proj[0] == a || o->proj[1] == a || o->shot == a ||
                                                       (o->spec_id == BS_FURY && a->owner == o)))
            o->scancel = 1;                                      /* or a projectile it threw) may cancel into the fury
                                                                    (a fury: into its MAX, its program's objects too:
                                                                    Raging Storm's pillars) */
    }
    if (a->state == S_SPECIAL) a->shrow = a->srow;               /* the special's row it landed on + 1 (follow-up windows) */
    if (!(a->state == S_SPECIAL && (a->pflags & PF_HOLD) && a->target && a->target != v && a->target->dance == a &&
          a->target->state == S_HITSTUN))
        (a->owner ? a->owner : a)->target = v;                   /* (a hold keeps its caught victim: a crowd hit on the way) */
    lab_note(a->owner ? a->owner : a, LE_HIT, a->state == S_ATTACK || a->state == S_AIR_ATTACK ? a->node : 0xFF, v->idx, damage);
    if (a->dtgt == v) { if (v->dpin) v->dpin--; a->dtgt = 0; }   /* its down attack landed: the target is free (TODO #218) */
    {   const fighter_t *from = a->pdef && (a->pdef->ppad & 1) && a->owner ? a->owner : a;   /* (an object whose victims fly
                                                                    away from its thrower: bproj_t.ppad 1, TODO #193) */
        react(v, INT(v->x) >= INT(from->x) ? 1 : -1, reaction, push);
    }
    if (a->state == S_SPECIAL) kof_react(v, INT(v->x) >= INT(a->x) ? 1 : -1, rk, a->spec_slide);   /* a special's body hit: KOF98's */
    if (sr) src_react(v, a->facing, sr);                         /* or its source's (SF_SREACT): sent the way the
                                                                    attacker faces, facing it (Kizuna: the victim behind
                                                                    Kim at the Phoenix's 86.55 flies on forward) */
    if (a->state == S_SPECIAL && a->ch->specials[a->spec_ix].prog) {
        if (a->spec_prev_hit & 32) {                             /* KOF's class 4 hit (a barrage): nobody stops, the */
            v->freeze = a->freeze = 0;                           /* victim reels in place */
            if (v->state == S_HITSTUN) { v->vx = 0; v->kdelay = 0; }
        }
        if ((a->spec_prev_hit & 64) && v->state == S_HITSTUN) v->vx = 0;   /* KOF's reel without its slide (step byte 1 = 3) */
        if ((a->pflags & PF_HOLD) && a->spec_id == BS_FURY && v->state == S_HITSTUN) v->vx = 0;   /* a fury holding its caught
                                                                    one: the crowd it hits reels in place (hold.dance (a): no
                                                                    slide out of the dance's reach) */
        if (a->pflags & PF_HOLD) hold_apply(a);
    }
}

/* ---- combat: every attacker's live attack box against every opponent's hurt box --------------------------------------- */
static const bbox_t JUGGLE_BOX = { 0, -24, 28, 20 };       /* a falling fighter's body: KOF boxes (x, y up -, half w, h) */
static const bbox_t LAUNCH_BOX = { 0, -64, 28, 28 };       /* KOF98's launched body (states 286 / 293: box $31 0, 192, 28, 28) */
static const bbox_t JUG_BOX = { 0, -40, 32, 40 };          /* rule 5's victim, thrown or flying: a whole body */
static const bbox_t LIE_BOX = { 0, -12, 40, 12 };          /* a lying body, as the down attack's hit reaches it (TODO #218:
                                                                    DD's lying record, Billy's set 58; DD tests the
                                                                    victim's first record whatever its type: +$F3 bit 7) */
/* "cancels" rule 5: attacker a is the follow-up (the special / fury or its projectile) of the fighter that opened v's
 * juggle window (juggle_open), and v is still thrown (before its script's landing row) or in the air */
static uint8_t juggled(const fighter_t *a, const fighter_t *v) {
    const fighter_t *o = a->owner ? a->owner : a;
    if (!v->jug_by || v->jug_by != o || o->state != S_SPECIAL) return 0;
    if (v->state == S_THROWN) return v->thr && (v->thr->land == 0xFFFF || v->srow <= v->thr->land);
    return v->y > 0;
}
static const bbox_t HOLD_BOX = { 0, -64, 48, 64 };         /* a victim a ROM special holds: KOF98's held states 404-407, one
                                                              * box $31 0, 192, 48, 64 on every step (Ryo EX 646A's barrage) */
static int16_t box_x(const fighter_t *f, int8_t bx) { return INT(f->x) + (f->facing > 0 ? -bx : bx); }   /* sprites face left */
static uint8_t boxes_meet(const fighter_t *a, const bbox_t *ab, const fighter_t *v, const bbox_t *vb) {
    int16_t dx = box_x(a, ab->x) - box_x(v, vb->x), dy = (ab->y - INT(a->y)) - (vb->y - INT(v->y));
    if (dx < 0) dx = -dx;
    if (dy < 0) dy = -dy;
    return dx < ab->w + vb->w && dy < ab->h + vb->h;           /* KOF98 $4366: strictly inside */
}
/* a hit's spark point: the centre of the boxes' overlap, where they touch (the centres' midpoint drifted toward a long
 * box's middle); world x, screen y */
static void overlap_xy(const fighter_t *a, const bbox_t *atk, const fighter_t *v, const bbox_t *hb, int16_t *sx, int16_t *sy) {
    int16_t ax = box_x(a, atk->x), vx = box_x(v, hb->x);
    int16_t ay = floor_top + INT(a->z) - INT(a->y) + atk->y, vy = floor_top + INT(v->z) - INT(v->y) + hb->y;
    *sx = ((ax - atk->w > vx - hb->w ? ax - atk->w : vx - hb->w) + (ax + atk->w < vx + hb->w ? ax + atk->w : vx + hb->w)) >> 1;
    *sy = ((ay - atk->h > vy - hb->h ? ay - atk->h : vy - hb->h) + (ay + atk->h < vy + hb->h ? ay + atk->h : vy + hb->h)) >> 1;
}
/* a source game's own hit spark (vocabulary fx.hit_spark, TODO #215; bm_hspark: Double Dragon's, read in its code:
 * tools/doubledr/sparks_dd.py, = DD frame for frame): a hit landing on a step its table names spawns that spark, an effect
 * object (bproj_t kind PK_FX: no box, no shadow, its own frames / palettes and motion in its rows) where its game puts it:
 * DD $26AE8, x = the victim's body box's centre + half its half width toward the attacker, the height of the attack box's
 * centre; the attacker's facing (spark 0x40: the other way, DD's height class 3); in front of both. Spark 0x80: the
 * screen strobes red (DD's super hits, $25EF2: main.c screen_fx). 0: the step has none (the engine's KOF98 spark). A
 * spark never takes the last free entity (a projectile needs it); no entity: no spark (the hit stays). */
uint8_t hitflash;
static uint8_t hit_spark(fighter_t *a, const fighter_t *v, const bbox_t *atk, const bbox_t *hb) {
    const bhspark_t *hs = &bm_hspark[a->ch->id];
    const uint8_t *e;
    const banim_t *pa = 0;
    uint8_t where, an = 0, st, code = 0, ob, i, nfree = 0;
    if (!hs->map || a->pdef) return 0;                       /* (a projectile's hit: its own end plays, DD's too) */
    if (a->state == S_ATTACK || a->state == S_AIR_ATTACK) { where = 0xFE; an = a->anim; st = a->step; }
    else if (a->state == S_SPECIAL && a->ch->specials[a->spec_ix].prog && a->pan) {
        where = a->spec_ix; pa = a->ch->specials[a->spec_ix].anims; st = a->pstep;   /* (its animation by address, as */
    } else return 0;                                                                 /* pan_fx: no division) */
    ob = BANK_set(CH_BANK(a->ch));                               /* (its table: its bank) */
    for (e = hs->map; *e != 0xFF; e += 4)
        if (e[0] == where && e[2] == st && (pa ? &pa[e[1]] == a->pan : e[1] == an)) { code = e[3]; break; }
    BANK_set(ob);
    if (!code) return 0;
    if (code & 0x80) hitflash = HITFLASH;
    for (i = 0; i < NPJ; i++) nfree += projectiles[i].state == S_OFF;
    if (nfree >= 2) {
        int16_t hx = box_x(v, hb->x) - (a->facing > 0 ? hb->w >> 1 : -(hb->w >> 1));
        fighter_t *p = proj_start(a, &hs->sparks[(code & 0x3F) - 1], FIX(hx), code & 0x40 ? -a->facing : a->facing,
                                  v->z > a->z ? v->z : a->z);
        if (p) {
            p->py0 = FIX(INT(a->y) - atk->y); proj_row(p);       /* (its rows from the hit's height) */
            p->zfront = 1; p->tick = 1;                          /* combat runs after the entities' update: its row 0 is */
        }                                                        /* this frame's, row 1 the next */
    }
    return 1;
}
static const bbox_t HELD_BOX = { 0, -56, 24, 40 };         /* a held victim's body when its pose has no hurt box */
/* a hold hit lands (TODO #166 b): the standard hit spark on the held victim, where its move's attack box meets the
 * victim's body (big: KOF98's C / D / C+D spark, the finisher always) */
static void hold_spark(fighter_t *a, fighter_t *v) {
    const bbox_t *atk = hold_box(a), *hb = &HELD_BOX;
    const bstep_t *sv = fighter_step(v);
    int16_t sx, sy;
    if (v->frame_ovr == 0xFFFF && (sv->flags & 2)) hb = &sv->hurt;
    if (atk) overlap_xy(a, atk, v, hb, &sx, &sy);
    else { sx = INT(v->x) + (a->facing > 0 ? -16 : 16); sy = floor_top + INT(v->z) - INT(v->y) - 64; }
    spark_hit(sx, sy, a->throw_id == BT_HOLD_FIN || hit_btn(hold_anim(a)) >= SX_C, a->facing);
}
static uint8_t grabbable(const fighter_t *v) {
    return !v->inv && !v->guard && !v->y && v->hp > 0 && (v->state == S_IDLE || v->state == S_WALK || v->state == S_HITSTUN);
}
#define AIR_BLOCK_Y 64            /* a special in the air below this height (px) is held by a standing body ahead */
#define PUSH_DX 32                /* a special pushes an opponent standing in its path to keep it this far ahead (KOF's push
                                     boxes: the captured opponent stood 27-49 px ahead at the moves' first impacts) */
/* hold crowd (TODO #166 b; Final Fight / Streets of Rage): a hold hit's blow (its move's attack box on its impact
 * frame, fighter_t.impact) also hits every other enemy it reaches, each once per hit (hit_mask, the held victim's bit
 * set at the hit's start): a hold hit's damage and a light reel, the finisher's a knockdown, a spark each */
static void hold_crowd(fighter_t **fs, uint8_t n, const fighter_t *only) {
    uint8_t i, j;
    for (i = 0; i < n; i++) {
        fighter_t *a = fs[i];
        const bbox_t *atk;
        uint8_t fz, fin;
        fighter_t *tg;
        if (!a->impact) continue;
        a->impact = 0;
        if ((only && a != only) || !(atk = hold_box(a))) continue;
        fz = a->freeze; tg = a->target; fin = a->throw_id == BT_HOLD_FIN;
        for (j = 0; j < n; j++) {
            fighter_t *v = fs[j];
            const bstep_t *sv;
            const bbox_t *hb;
            int16_t dz, sx, sy;
            if (v == a || v->team == a->team || (a->hit_mask & (1 << v->idx)) || v->inv || v == a->held || v->hp <= 0) continue;
            if (v->state != S_IDLE && v->state != S_WALK && v->state != S_RUN && v->state != S_ATTACK &&
                v->state != S_HITSTUN && v->state != S_SPECIAL && v->state != S_LAND && v->state != S_PREJUMP) continue;
            dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            sv = fighter_hurt_step(v);
            if (!(sv->flags & 2)) continue;
            hb = &sv->hurt;
            if (!boxes_meet(a, atk, v, hb)) continue;
            overlap_xy(a, atk, v, hb, &sx, &sy);
            fighter_hit(a, v, GRAB_DAMAGE, fin ? R_KNOCKDOWN : R_LIGHT, 8);
            spark_hit(sx, sy, fin || hit_btn(hold_anim(a)) >= SX_C, a->facing);
        }
        a->freeze = fz; a->target = tg;                          /* the hold's own rhythm and victim stay */
    }
}
/* an attacker's live box (a step's, a special's or a projectile's) against every opponent's hurt box: the hits it lands
 * now. combat() runs it once a frame for each attacker; a retimed move squeezed (several source frames in one game
 * frame, "retiming") runs it for each source frame passed (rt_probe) */
static void strike(fighter_t *a, fighter_t **fs, uint8_t n) {
    const bbox_t *atk;
    bbox_t abox;                                                 /* a script row's box: in the attacker's bank, copied */
    uint8_t sounded = 0, j;                                      /* one hit sound per attack, however many it hits */
    if (a->state == S_ATTACK || a->state == S_AIR_ATTACK) {
        const bstep_t *sa = fighter_step(a);
        if (!(sa->flags & 1)) return;
        atk = &sa->atk;
    } else if ((a->state == S_SPECIAL || a->state == S_PROJ) && a->spec_atk) {
        uint8_t ob = BANK_set(CH_BANK(a->ch)); abox = *a->spec_atk; BANK_set(ob); atk = &abox;
    }
    else return;
    for (j = 0; j < n; j++) {
        fighter_t *v = fs[j];
        const bstep_t *sv;
        int16_t dz, dx, dy;
        uint8_t jug;
        const bbox_t *hb;
        if (v->team == a->team || (a->hit_mask & (1 << v->idx)) || v->inv || dead_body(v, a)) continue;
        jug = juggled(a, v);                                 /* rule 5: the canceller's follow-up on its victim */
        if ((v->state == S_DOWN && (a->dtgt != v || a->state != S_SPECIAL)) || v->state == S_GETUP ||   /* (lying: */
            v->state == S_THROW || (v->state == S_THROWN && !jug) ||   /* only its down attack's target, TODO #218) */
            v->state == S_PROJ || v->state == S_OFF || v->state == S_DEAD) continue;
        if (v->state == S_KNOCKDOWN && v->y <= 0) continue;  /* juggle: hittable while it falls (the chain core: */
        if (v->guard && v->guard_by != (a->owner ? a->owner : a)) continue;   /* a player's guard after a hit; */
        if (v->state == S_KNOCKDOWN && !jug && !(a->state == S_SPECIAL && a->spec_id == BS_FURY) &&   /* at most */
            !(a->owner && a->owner->state == S_SPECIAL && a->owner->spec_id == BS_FURY) &&   /* juggle_cap air hits, */
            (v->kfloor || v->jug_n >= gchain.juggle_cap)) continue;   /* none once it touched the floor; a fury's
                                                                own hits and a cancel's juggle window excepted) */
        dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
        sv = fighter_hurt_step(v);
        if (v->state == S_DOWN) hb = &LIE_BOX;               /* lying: its down attack's (TODO #218) */
        else if (jug && v->state == S_THROWN) hb = &JUG_BOX;   /* thrown (rule 5): its body */
        else if ((a->pflags & PF_HOLD) && v == a->target && v->state == S_HITSTUN) hb = &HOLD_BOX;
        else if (v->state == S_KNOCKDOWN && v->kmode) {      /* KOF's reaction: its box or none (rule 5: a body) */
            if (!(v->kmode & KM_HURT)) { if (!jug) continue; hb = &JUG_BOX; } else hb = &LAUNCH_BOX;
        }
        else if (sv->flags & 2) hb = &sv->hurt;
        else if (v->state == S_KNOCKDOWN) hb = &JUGGLE_BOX;          /* the brawler's falls: KOF's have no hurt box */
        else continue;
        dx = box_x(a, atk->x) - box_x(v, hb->x);
        dy = (atk->y - INT(a->y)) - (hb->y - INT(v->y));
        if (dx < 0) dx = -dx;
        if (dy < 0) dy = -dy;
        if (dx >= atk->w + hb->w || dy >= atk->h + hb->h) continue;   /* KOF98 $4366: strictly inside */
        {
            int16_t sx, sy;
            uint8_t big = 1;
            overlap_xy(a, atk, v, hb, &sx, &sy);
            if (a->state == S_ATTACK || a->state == S_AIR_ATTACK) {
                const rnode_t *c = NODE(a, a->node);
                const banim_t *an = &a->ch->anims[a->anim];
                static const uint8_t EFFECT_R[6] = { 0, R_KNOCKDOWN, R_LAUNCH, R_TRIP, R_BLOWBACK, R_KNOCKDOWN };
                uint8_t dmg = c->damage, rc = c->effect ? EFFECT_R[c->effect] : c->weight ? R_HEAVY : R_LIGHT, k, total = 0, later = 0;
                for (k = 0; k < an->nsteps; k++)                 /* multi-hit normal: the knockdown on its last */
                    if (an->steps[k].flags & 4) { total++; if (k > a->step) later++; }   /* hit */
                if (total > 1 && later && rc >= R_KNOCKDOWN) rc = R_HEAVY;
                dmg = (a->ldmg & (1 << v->idx)) ? 0 : dmg;      /* fixed damage (revamp 1A): the node's whole damage on */
                a->ldmg |= 1 << v->idx;                          /* its first hit on each victim, its later hits none */
                big = rc >= R_KNOCKDOWN || hit_btn(c->anim) >= SX_C;
                if (!sounded++) {                                /* its own sound for this hit of the move, else the rule */
                    uint8_t s = own_sound(a, a->anim, total - later - 1);
                    snd_sfx(s ? s : hit_sound(a, (c->flags & RF_HEAVY_SFX) ? BA_ATK_D_CLOSE : c->anim, rc >= R_KNOCKDOWN));
                }
                fighter_hit(a, v, dmg, rc, c->push);
                if (c->effect == RE_SLAM && !later && v->state == S_KNOCKDOWN) {   /* the slam (the chain's down */
                    v->vy = v->y > 0 ? -FIX(6) : 0; v->kslam = 1;    /* finisher): to the floor now, then its */
                    play(v, BA_KNOCKDOWN_FLIGHT);                    /* bounce (S_KNOCKDOWN, kslam) */
                }
            } else if (a->spec_prev_hit & 8) {       /* a running grab's reach: it catches, the continuation hits */
                a->hit_mask |= 1 << v->idx; a->landed = 1; a->shrow = a->srow; a->target = v; v->freeze = HITSTOP;
                if (!sounded++) snd_sfx(SFX_GRAB);           /* the command grab connects: KOF98's grab start */
                if (v->state == S_WALK) to_neutral(v, 0);
                continue;
            } else {
                if (!sounded++) { if (a->state == S_SPECIAL || a->pdef) hit_sfx(a->spec_fx); else snd_sfx(SFX_HIT_CD); }
                fighter_hit(a, v, a->spec_dmg, a->spec_react, 0);
                if ((a->state == S_SPECIAL || a->pdef) && a->spec_fx >> 6) set_burn(v, a->spec_fx >> 6);
                if (a->state == S_SPECIAL && (a->ch->specials[a->spec_ix].sflags & SF_BIGHIT)) big_hit(a, v);
                else if (a->pdef && a->owner && a->owner->state == S_SPECIAL && (a->owner->ch->specials[a->owner->spec_ix].sflags & SF_BIGHIT))
                    big_hit(a->owner, v);                    /* its object's hit (SS2 Hanzo's rage flame, object 7 $30752) */
            }
            if (!hit_spark(a, v, atk, hb)) spark_hit(sx, sy, big, a->facing);  /* KOF98: A / B small, C / D / C+D big;
                                                                its source's own (DD, TODO #215) */
            if (a->pdef) {                                   /* a travelling projectile ends on its first hit (a */
                if (a->pdef->kind == 1 || a->pdef->kind == PK_BOOM) { proj_hit(a); break; }   /* fireball, a boomerang); any other (an eruption) hits every */
                proj_crowd(a);                                /* target it touches, each once (hit_mask): crowd */
            }
        }
    }
}
void combat(fighter_t **fs, uint8_t n, const fighter_t *only) {
    uint8_t i, j;
    hold_crowd(fs, n, only);
    for (i = 0; i < n; i++) {                                    /* specials push who stands in their path: a rush */
        fighter_t *a = fs[i];                                    /* reaches its hit as in the game, not past it */
        if (a->state != S_SPECIAL || INT(a->y) >= AIR_BLOCK_Y || (only && a != only)) continue;
        if (a->ch->specials[a->spec_ix].sflags & SF_NOPUSH) continue;   /* its source has no push box then (SS2 +$FF) */
        for (j = 0; j < n; j++) {
            fighter_t *v = fs[j];
            int16_t d, dz, pd;
            if (v->team == a->team || v->y || v->inv == INV_FURY || (v->state != S_IDLE && v->state != S_WALK && v->state != S_HITSTUN &&
                v->state != S_ATTACK && v->state != S_SPECIAL)) continue;
            if (v == a->target && (a->spec_prev_hit & 4) && a->landed) continue;   /* its carried target: held where the game had it */
            if (v == a->target && a->vlist && (a->pflags & PF_HOLD)) continue;   /* its caught one: where its victim list puts it */
            dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            d = a->facing > 0 ? INT(v->x) - INT(a->x) : INT(a->x) - INT(v->x);
            pd = PUSH_DX;
            if (v->vph && v->vph_by == a && a->pan) {            /* its victim in a phase (vphase, TODO #136): Kizuna's
                                                                    push, to its body box's front + the victim's 12 px
                                                                    (Kizuna 15) [meas: 421A_h 47, 6246A_h 35 / 51 px] */
                const bstep_t *sa = &a->pan->steps[a->pstep];
                if (!(sa->flags & 4) || !(a->ch->specials[a->spec_ix].sflags & SF_SREACT)) continue;   /* (its push box: flag 4) */
                pd = -sa->hurt.x + sa->hurt.w + 12;
            }
            if (d <= -8 || d >= pd) continue;
            if (v->vph && v->vph_by == a) {                      /* (that victim: half the overlap a side, 8 px a frame
                                                                    at most, a frozen body not moved: $2B644 skipped)
                                                                    [meas: 421A_h 101.0 Kim -8 x5 -4 -2 -1, 6246A_h
                                                                    86.2 -9 / +8, 86.16 -8 / +8] */
                int32_t over = FIX(pd - d), mine = (v->vph & VPH_FREEZE) ? over : over >> 1;
                if (mine > FIX(8)) mine = FIX(8);
                if (over - mine > FIX(8)) over = mine + FIX(8);
                a->throw_x0 -= dir_mul(a->facing, mine); a->x -= dir_mul(a->facing, mine); clamp(a);
                if (!(v->vph & VPH_FREEZE)) { v->x += dir_mul(a->facing, over - mine); clamp(v); }
            }
            else if (a->ch->specials[a->spec_ix].sflags & SF_SHARE) {   /* the bodies share the push (Kizuna: Kim's j.2B */
                int32_t over = FIX(PUSH_DX - d), back = over >> 1;      /* goes on diving, its victim pushed ahead, */
                a->throw_x0 -= dir_mul(a->facing, back); a->x -= dir_mul(a->facing, back); clamp(a);   /* TODO #200; on */
                v->x += dir_mul(a->facing, over - back); clamp(v);      /* the ground too, TODO #136: the Phoenix's rush */
            }                                                    /* 85 pushes at half its speed [meas: 6246A_h, +2 a frame] */
            else if (!a->y) { v->x = a->x + dir_mul(a->facing, FIX(PUSH_DX)); clamp(v); }
            else if (a->spec_id != BS_FURY || !a->landed) {      /* a low leap stops at the body (SS4's 421C: P1 */
                int32_t back = dir_mul(a->facing, FIX(PUSH_DX - d));   /* held 30 px before P2 at y 10-51, then */
                a->throw_x0 -= back; a->x -= back; clamp(a);     /* its landing slash hits), never carries it */
            }
        }
    }
    for (i = 0; i < n; i++) {                                    /* (Kim queue 2026-10-09) a normal that travels (its step's */
        fighter_t *a = fs[i];                                    /* forward move) pushes the victim it hit ahead, as a */
        if (a->state != S_ATTACK || a->y || !a->landed || a->ch->anims[a->anim].steps[a->step].dx <= 0 ||   /* special's */
            (only && a != only)) continue;                       /* rush: $96's three kicks with the regular push back */
        for (j = 0; j < n; j++) {                                /* are not walked through */
            fighter_t *v = fs[j];
            int16_t d, dz;
            if (v->team == a->team || v->y || v->state != S_HITSTUN || v->inv == INV_FURY) continue;
            dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            d = a->facing > 0 ? INT(v->x) - INT(a->x) : INT(a->x) - INT(v->x);
            if (d <= -8 || d >= PUSH_DX) continue;
            v->x = a->x + dir_mul(a->facing, FIX(PUSH_DX)); clamp(v);
        }
    }
    for (i = 0; i < n; i++) {                                    /* a ROM special's opponent (KOF +$BC, PC_FAR before any hit): */
        fighter_t *a = fs[i];                                    /* the nearest one on its lane */
        int16_t best = 0x7FFF;
        if (a->state != S_SPECIAL || (only && a != only)) continue;
        a->popp = 0;
        for (j = 0; j < n; j++) {
            fighter_t *o = fs[j];
            int16_t dx, dz;
            if (o->team == a->team || o->state == S_PROJ || o->state == S_OFF || o->state == S_DEAD || dead_body(o, a)) continue;
            dx = INT(o->x) - INT(a->x); dz = INT(o->z) - INT(a->z);
            if (dx < 0) dx = -dx;
            if (dz < -Z_HIT || dz > Z_HIT || dx >= best) continue;
            best = dx; a->popp = o;
        }
    }
    for (i = 0; i < n; i++) {                                    /* thrown bodies (TODO #146 rule 9, spawn.body): from */
        fighter_t *v = fs[i];                                    /* the release to the landing a thrown victim knocks down */
        const bthrow_t *th = v->thr;                             /* every other enemy it touches (its teammates), each */
        uint16_t row;                                            /* once, falling the throw's way (Final Fight, Streets */
        if (only || v->freeze) continue;                         /* of Rage 2); a throw special's victim (revamp 3, tb_by) */
        if (v->tb_by) {                                          /* from its catch while it falls, until it touches the */
            if (v->state != S_KNOCKDOWN || v->y <= 0 || v->kfloor) continue;   /* floor (no chain credit: its thrower */
        } else {                                                 /* keeps its target) */
            if (v->state != S_THROWN || !th || th->rel == 0xFFFF) continue;
            row = v->srow ? v->srow - 1 : 0;
            if (row < th->rel || row >= th->land) continue;
        }
        for (j = 0; j < n; j++) {
            fighter_t *o = fs[j];
            const bstep_t *so;
            const bbox_t *hb;
            int16_t dz;
            int8_t dir;
            if (o == v || o->team != v->team || (v->hit_mask & (1 << o->idx)) || o->inv || o->hp <= 0) continue;
            if (o->state != S_IDLE && o->state != S_WALK && o->state != S_RUN && o->state != S_ATTACK && o->state != S_HITSTUN &&
                o->state != S_PREJUMP && o->state != S_LAND && o->state != S_SPECIAL && o->state != S_AIR && o->state != S_AIR_ATTACK) continue;
            dz = INT(o->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            so = fighter_hurt_step(o);
            hb = (so->flags & 2) ? &so->hurt : &JUGGLE_BOX;
            if (!boxes_meet(v, &BODY_BOX, o, hb)) continue;
            dir = v->vx > 0 ? 1 : v->vx < 0 ? -1 : (INT(o->x) >= INT(v->x) ? 1 : -1);   /* the throw's way */
            v->hit_mask |= 1 << o->idx;
            o->hp -= BODY_DAMAGE; o->freeze = HITSTOP;
            if (v->tb_by) v->tb_by->target = o; else if (v->thr_by) v->thr_by->target = o;   /* (the HUD's life; no chain credit) */
            if (o->state == S_SPECIAL) { carry_drop(o); special_end(o); }
            react(o, dir, R_KNOCKDOWN, 0);
            snd_sfx(SFX_HIT_CD);
            spark_hit(INT(o->x), floor_top + INT(o->z) - INT(o->y) - 48, 1, dir);
        }
    }
    for (i = 0; i < n; i++) {                                    /* grabs: walking forward into a standing opponent */
        fighter_t *a = fs[i];
        if (!a->pushing || a->state != S_WALK || !a->ch->throws[BT_THROW_C].nrows || only) continue;
        for (j = 0; j < n; j++) {
            fighter_t *v = fs[j];
            int16_t dz, d;
            if (v->team == a->team || !grabbable(v)) continue;
            dz = INT(a->z) - INT(v->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            d = a->facing > 0 ? INT(v->x) - INT(a->x) : INT(a->x) - INT(v->x);
            if (d > 0 && d <= GRAB_DX) { grab(a, v); break; }
        }
    }
    cb_fs = fs; cb_n = n;
    for (i = 0; i < n; i++) {
        fighter_t *a = fs[i];
        if (a->freeze || (only && a != only && a->owner != only)) continue;   /* (a super flash: its attacker and its
                                                                    objects, which run through it: K''s Heat Drive shot, #202) */
        strike(a, fs, n);
    }
    for (i = 0; i < NPJ && !only; i++) {                         /* projectiles meeting: both hits spent (KOF98 */
        fighter_t *a = &projectiles[i];                          /* measured: EX Ryo's Ko-ou-ken ended on Yuri's */
        bbox_t ab, bb;                                           /* (both boxes copied out under their banks) */
        uint8_t ob;
        if (a->state != S_PROJ || !a->pdef || !a->spec_atk || a->pend == 3) continue;   /* eruption, whose attack went off;
                                                                    one that hit a fighter: spent for clashes, as KOF's) */
        ob = BANK_set(CH_BANK(a->ch)); ab = *a->spec_atk; BANK_set(ob);
        for (j = 0; j < NPJ; j++) {
            fighter_t *b = &projectiles[j];
            int16_t dz;
            if (b->state != S_PROJ || !b->pdef || b->team == a->team || !b->pown) continue;
            dz = INT(a->z) - INT(b->z); if (dz < -Z_HIT || dz > Z_HIT) continue;
            ob = BANK_set(CH_BANK(b->ch)); bb = *b->pown; BANK_set(ob);
            if (!boxes_meet(a, &ab, b, &bb)) continue;
            proj_hit(a); proj_hit(b);
            break;
        }
    }
}

/* the wall rule (vocabulary stage.wall, Bruno 2026-10-06, TODO #173: "as soon as we're on the edge, actually push the
 * character on the wall, and we should be able to actually see the victim being pushed on the wall"): the screen's
 * edges are walls WALL_EDGE px in, for every special and every fury (its dance, "dance", is the same wall). From a
 * special's hit (its body's or its projectile's: fighter_hit sets wall_by) until its victim is down, the victim stays
 * inside the walls: a reel's slide, a blowback or a carry that would take it out stops at the wall, its whole body on
 * screen (KOF's corner). While the special plays, its attacker is held back by what its reeling target (the victim
 * it holds / hit last) was held back: a rush or a catch's push stops at the victim pinned on the wall (a launched
 * victim's flight into the wall moves nobody); a fury's attacker also stays inside the walls itself (its dance). A
 * catch that grinds its victim to the wall (KOF98 $18092, the stage's x 32 / 736: Rugal's God Press and Gigantic
 * Pressure) tests the same walls (PC_WALL). The camera does not follow instead: the campaign locks it in the waves. */
#define WALL_EDGE 40               /* px from the screen edge to a pinned victim's feet: its whole body shows (a fighter's
                                     body is about 60 px wide; the players' own limit, 16 px, shows half of it) */
int16_t wall_lo = WALL_EDGE, wall_hi = 320 - WALL_EDGE;
void wall_update(fighter_t **fs, uint8_t n, int16_t cam_x) {
    uint8_t i;
    int32_t lo, hi;
    wall_lo = cam_x + WALL_EDGE; wall_hi = cam_x + 320 - WALL_EDGE;
    lo = FIX(wall_lo); hi = FIX(wall_hi);
    for (i = 0; i < n; i++) {
        fighter_t *v = fs[i], *a = v->wall_by;
        int32_t x;
        if (!a) continue;
        if (v->state != S_HITSTUN && v->state != S_KNOCKDOWN) { v->wall_by = 0; v->dance = 0; continue; }   /* down (or
                                                                    free): over */
        x = v->x < lo ? lo : v->x > hi ? hi : v->x;
        if (a->state != S_SPECIAL) { v->x = x; continue; }       /* its special over (or a projectile): the victim alone */
        if (x != v->x && a->target == v && v->state == S_HITSTUN) { a->x += x - v->x; a->throw_x0 += x - v->x; }   /* the
                                                                    attacker held back (not by its finisher's launch) */
        v->x = x;
        if (!dancing(v)) continue;                               /* a fury (its dance) keeps its attacker inside too; */
        if (a->x < lo) { a->throw_x0 += lo - a->x; a->x = lo; }  /* a special's attacker is only held back by its */
        if (a->x > hi) { a->throw_x0 += hi - a->x; a->x = hi; }  /* victim (no snap from the players' 16 px margin) */
    }
}

void fighter_init(fighter_t *f, const bchar_t *ch, uint8_t set, uint8_t palbase, uint8_t team, int16_t x, int16_t z) {
    uint8_t i;
    *f = (fighter_t){ 0 };                                       /* nothing left from the demo or the last fight */
    f->ch = ch; f->set = set; f->palbase = palbase; f->team = team;
    for (i = 0; i < ch->npal && i < MAX_PALS; i++) PAL_setPalette(palbase + i, ch->pals + ((set * ch->npal + i) << 4));
    f->x = FIX(x); f->z = FIX(z); f->y = 0; f->vx = f->vy = f->vz = 0;
    f->facing = team ? -1 : 1; f->hp = 60; f->freeze = f->inv = 0; f->held = 0;
    f->shown_frame = 0xFFFF; f->frame_ovr = 0xFFFF; f->zfront = 0; f->pushing = 0; f->target = 0; f->popp = 0; f->spec_atk = 0; f->proj[0] = f->proj[1] = 0; f->owner = 0; f->ncols = 0; f->burn = 0; f->spec_fx = 0;
    f->jump_kind = f->jump_dir = 0; f->drive = DRIVE_FULL; f->fgauge = 0; f->dsc = 0x100; f->dacc = 0x80;   /* (the drive full,
                                                                    the fury gauge empty: "the meter") */
    walk_rate(f);
    enter(f, S_IDLE); play(f, BA_IDLE);
}
