/* Beat 'em up fighter: one state machine for every character and every controller (player or AI); a character only
 * supplies data (bm_chars.c, exported from the KOF dictionaries by tools/brawler/export_bm.py).
 *
 * Coordinates (16.16 fixed point): X left/right on the floor, Z depth (0 = back edge of the walkable band, grows
 * toward the camera), Y height above the floor. Screen: x = X - camera, feet y = floor_top + Z - Y.
 * Hits: attack box vs hurt box overlap in X/Y, and |Z difference| <= Z_HIT. Draw order: by Z. */
#ifndef FIGHTER_H
#define FIGHTER_H
#include <stdint.h>
#include "bm_chars.h"

#define FIX(v)   ((int32_t)(v) << 16)
#define INT(v)   ((int16_t)((v) >> 16))
extern int16_t floor_top;         /* screen y of the feet at Z = 0: the stage's (stage_t.floor_top, measured on its art; main.c
                                     stage_init), SELECT_FLOOR on the select screen; draw.s reads it too */
#define Z_DEPTH   64              /* walkable band depth in px */
#define Z_HIT     12              /* max depth difference for a hit / a grab */
#define MAX_COLS  20              /* hardware sprites reserved per fighter (Billy's widest frame: 19) */
#define MAX_PALS  8               /* palettes reserved per fighter (Terry with his effects: 5) */
extern int16_t world_w;           /* the stage's width in px (stage_t.cols * 16); fighters stay 16 px inside it */

enum {                            /* states: the state machine alone decides what happens next */
    S_IDLE, S_WALK, S_RUN, S_PREJUMP, S_AIR, S_LAND,
    S_ATTACK, S_AIR_ATTACK,
    S_HITSTUN, S_KNOCKDOWN, S_DOWN, S_GETUP,
    S_GRAB, S_GRABBED,            /* hold: holder / held */
    S_THROW, S_THROWN,            /* a throw script playing: thrower / victim */
    S_SPECIAL,                    /* a special's script playing */
    S_DEAD,                       /* life out, lying down (enemies blink and go, players use a life) */
    S_PROJ, S_OFF,                /* projectile entities (pool): in use / free */
    S_COUNT
};
enum { R_LIGHT, R_HEAVY, R_KNOCKDOWN, R_LAUNCH, R_TRIP, R_BLOWBACK };   /* hit reactions (R_BLOWBACK: KOF's C+D, sent far) */
enum { IN_A = 1, IN_B = 2, IN_C = 4, IN_D = 8 };           /* buttons: punch, kick, jump, special */

typedef struct {                  /* what the controller wants this frame (player input or AI) */
    int8_t dx, dz;                /* stick: -1/0/1 (dz -1 = away from the camera) */
    uint8_t press;                /* IN_* pressed this frame */
    uint8_t run;                  /* forward double tap */
    int8_t  face;                 /* standing still: turn this way (AI faces its target; players leave 0) */
    uint8_t grab;                 /* AI: walking forward grabs on contact (players always grab) */
    uint8_t ai;                   /* the AI drives this fighter (enemies, the attract demo's P1) */
    uint8_t slow;                 /* walk at half speed (16.16: sub-pixel steps every frame; the AI's positioning walk) */
    uint8_t hold;                 /* IN_* held this frame (C held through the prejump = the regular jump, released = a hop) */
    uint8_t ab;                   /* the D in press is A+B pressed together (a route's A+B link takes it, else it is D) */
} intent_t;

/* ---- chain routes (Chain Lab, 2026-10-05): one route tree per fighter, data only ---------------------------------------
 * A tree blob (tools/brawler/export_bm.py from tools/brawler/routes/<fighter>.json, or the default tree = the old single
 * COMBO table; the Chain Lab page writes one into lab.buf): an rt_head_t, then nnodes rnode_t. Node 0 is "none"; a link
 * is a node index (0 = no link). A node is one hit: the move it plays (BA_*, or BS_* for a special), the hit weight and
 * the effect on the victim (the reaction), damage and push, its speed, the keep flag, and its links by input (RI_*). The game
 * reads the trees through route_tab[] (RAM, set at boot from bchar_t.routes), so a tree can be replaced while it runs. */
enum { RI_A, RI_B, RI_DA, RI_DB, RI_FA, RI_FB, RI_DFA, RI_DFB, RI_AB,      /* normal links: A B, down+, forward+, down-forward+, A+B */
       RI_D, RI_FD, RI_DD, RI_UD,                                          /* special links (enders): D, forward+D, down+D, up+D */
       RI_N = 13 };
enum { RF_SPECIAL = 1, RF_AIR = 2, RF_KEEP = 4 };     /* rnode_t.flags: anim is a BS_*; an air normal (anim: BA_ATK_C_JUMP /
                                                         D_JUMP / CD_JUMP = air A / B / C+D, the jump picks the animation);
                                                         keep the full animation on hit: the move plays to its end, the
                                                         buffered input then takes its link (clear, the default since
                                                         2026-10-05: on hit the next link starts as soon as its input comes,
                                                         after the hit-stop) */
enum { RE_NONE, RE_KNOCKDOWN, RE_LAUNCH, RE_TRIP, RE_BLOWBACK };   /* rnode_t.effect */
typedef struct {
    uint8_t anim, flags;
    uint8_t weight, effect;       /* weight 0 light / 1 strong (the victim's hit animation and stun, effect none) */
    uint8_t damage;
    int8_t  push;                 /* px the victim slides back on hit (effect none) */
    uint16_t speed;               /* playback speed, 8.8 fixed point (0x0100 = KOF's own timing; 0x0040-0x0400): the move's
                                     animation, or the special's script, advances by it every frame (fighter.c anim_tick) */
    uint8_t next[RI_N];           /* links by RI_* */
    uint8_t pad;
} rnode_t;
_Static_assert(sizeof(rnode_t) == 22, "routes.py NODE_SIZE");
typedef struct {
    char    magic[2];             /* "RT" */
    uint8_t version, nnodes;      /* version 2 (22-byte nodes with speed) */
    uint8_t root;                 /* the links from neutral (its own move unused) */
    uint8_t dash, nospec, hold;   /* run + A; D when the fighter has no special for it; the hold's third hit (C+D) */
    uint8_t air_a, air_b, air_cd; /* air normals */
    uint8_t pad[5];
} rt_head_t;
#define RT_NODE(t, i) ((const rnode_t *)((const uint8_t *)(t) + sizeof(rt_head_t)) + (i))
extern const rt_head_t *route_tab[BC_COUNT];
void routes_init(void);

/* Chain Lab mailbox (examples/brawler/README.md "Chain Lab"): the page writes it from JavaScript, the game reads it at the
 * start of a tick; the game logs P1's route steps into ev[] (a ring) for the page's per-link readout. */
enum { LE_START, LE_HIT, LE_END, LE_SPECIAL, LE_CHAINWIN };   /* lab_ev_t.kind */
enum { LH_NEUTRAL, LH_AFTER_END, LH_CANCEL, LH_WINDOW };      /* LE_START: how the node started */
typedef struct { uint16_t frame; uint8_t kind, node, how, val; } lab_ev_t;   /* val: LE_HIT damage, LE_SPECIAL BS_*,
                                                                                 LE_END 1 = it had hit */
#define LAB_NEV  64
#define LAB_BUF  (sizeof(rt_head_t) + 128 * sizeof(rnode_t))
typedef struct {
    char     magic[4];            /* "LAB1" while the page drives the game */
    uint8_t  req;                 /* page: 1 = start training (fighter vs dummy), 2 = reset positions; the game clears it */
    uint8_t  fighter, dummy;      /* bm_chars indices (req 1) */
    uint8_t  load;                /* page: 1 = buf holds a tree for `fighter`: install it (the game clears it); 2 = back to
                                     the fighter's own tree */
    uint8_t  active;              /* game: 1 while the training runs */
    uint8_t  nev;                 /* game: events written (ring index = nev % LAB_NEV) */
    uint16_t frame;               /* game: training frames */
    uint8_t  combo_hits, pad;     /* game: the readout on screen */
    uint16_t combo_dmg;
    lab_ev_t ev[LAB_NEV];
    uint8_t  buf[LAB_BUF];
} lab_t;
extern lab_t lab;
void lab_install(void);           /* lab.load handled (routes_init's table, main.c calls it every tick) */

typedef struct fighter {
    const bchar_t *ch;
    uint8_t  set, palbase;        /* colour set, first hardware palette */
    uint16_t spr;                 /* first hardware sprite of the block (depth sorting reassigns it) */
    int32_t  x, z, y, vx, vz, vy;
    int8_t   facing;              /* +1 right, -1 left */
    uint8_t  team;                /* 0 players, 1 enemies */
    uint8_t  state;
    uint16_t state_t;
    uint8_t  anim, step, tick, anim_done;
    uint8_t  node;                /* combo node while attacking */
    uint8_t  buffered;            /* next combo input pressed during the current link (IN_* | 0x80 forward | 0x40 down | 0x20 A+B) */
    uint8_t  hit_mask;            /* fighters already hit by the current attack (bit per index) */
    uint8_t  freeze;              /* hit-stop frames */
    uint8_t  inv;                 /* invulnerable frames */
    int16_t  hp;
    uint8_t  idx;                 /* index in the fighter table */
    struct fighter *held;         /* grab partner */
    uint16_t shown_frame; int8_t shown_facing;   /* what the sprite block's tiles show (0xFFFF = rewrite) */
    uint16_t frame_ovr;           /* frame shown instead of the animation's (holds and throw scripts), 0xFFFF = none */
    uint8_t  zfront;              /* drawn in front of a fighter at the same Z (throw victims) */
    uint8_t  pushing;             /* walked forward this frame (grabs on contact) */
    uint8_t  throw_id, grab_hits; /* grab_hits: hits in the hold; during a throw, the throw's impacts */
    uint8_t  throw_dealt, impact; /* throw damage dealt at its impacts; an impact this frame (combat() resolves it) */
    int32_t  throw_x0;
    struct fighter *target;       /* last opponent this fighter hit or grabbed (the HUD shows its life) */
    uint8_t  spec_id, spec_prev_hit;   /* spec_prev_hit: hit bits of the special's current row (bspec_row_t.hit) */
    const bbox_t *spec_atk;       /* special / projectile: attack box of the current script row (0 = none) */
    struct fighter *proj[2];      /* projectiles of the special playing */
    struct fighter *owner;        /* projectile: who threw it */
    uint8_t  ncols;               /* sprite columns of the shown frame (written by fighter_tiles) */
    uint8_t  landed;              /* the current attack connected (routes chain only on a hit) */
    uint8_t  chain_node, chain_t; /* Final Fight chain: the route step that hit, frames left to continue it from neutral */
    uint8_t  spec_buf;            /* D pressed during a normal: 0x80 | RI_D.. (its direction), the node's special link cancels once it hits */
    uint8_t  still;               /* AI: frames walking without a walk intent (the walk holds AI_IDLE_DELAY frames) */            /* thrower X when the throw started (script X is relative to it) */
    uint8_t  spec_dmg, spec_react; /* special: damage and victim reaction (R_*) of the hit window open (bspec_row_t) */
    uint8_t  spec_fx;             /* special: KOF98 hit effect of the hit window open (bspec_row_t.fx: kind | burn << 6) */
    uint8_t  burn;                /* burnt by a fire hit: 1 purple, 2 orange (its palettes show KOF98's burn ramp) */
    int8_t   throw_face;          /* throw: the thrower's facing at the grab (the script's offsets are in it) */
    uint8_t  jump_kind;           /* the jump in progress: 0 regular (C held), 1 hop (C tapped) */
    uint8_t  jump_dir;            /* its direction: 0 vertical, 1 forward, 2 back (facing kept) */
    /* independent projectile (S_PROJ entity spawned by a special's bspec_t.proj; fields added at the end: draw.s pins
     * the ones above). pdef: its definition; prow: row of its flight (or of its end); pend: 1 its end rows play (a
     * travelling one hit), 2 its attack is spent (an eruption that hit plays on); pown: the clash box of the row */
    const bproj_t *pdef;
    const bbox_t *pown;
    uint8_t  prow, pend;
    struct fighter *shot;         /* thrower: its projectile in flight (KOF: one at a time, owner +$E1 bit 5) */
    uint8_t  power;               /* extra damage every hit it lands (campaign: later stages and bosses hit harder) */
    uint8_t  tint;                /* minion colours (fighter_colour): gtints[] index, 0 = its own colour set */
    int16_t  hp_max;              /* its life at spawn when not 60 (campaign difficulty: enemies, bosses); 0 = 60 */
    /* playback (fighter.c "animation player"): acc = time spent in the current step (animation) or row (special / throw
     * script) in 1/256 frames, speed = 8.8 frames per frame (play() sets 0x0100, a route node / a throw its own), srow =
     * the script row shown + 1 (specials, throws) */
    uint32_t acc;
    uint16_t speed, srow;
} fighter_t;


extern uint16_t stat_grabs, stat_specials, stat_throws, stat_escapes;   /* by enemies (escapes: by players); HUD */
#define NPJ 4                     /* projectile entities: fighter_t too, so one renderer / sort / guard / hit test */
extern fighter_t projectiles[NPJ];
void projectile_reset(fighter_t *p);
void projectiles_update(int16_t cam_x);   /* the independent projectiles' flight, after the fighters' update */

void fighter_init(fighter_t *f, const bchar_t *ch, uint8_t set, uint8_t palbase, uint8_t team, int16_t x, int16_t z);
void fighter_update(fighter_t *f, const intent_t *in);
void fighter_hit(fighter_t *atk, fighter_t *vic, uint8_t damage, uint8_t reaction, int8_t push);   /* attack connected */
void spark_hit(int16_t wx, int16_t sy, uint8_t big, int8_t facing);   /* main.c: KOF98 hit spark at world x, screen y */
void combat(fighter_t **fs, uint8_t n);                     /* attack boxes vs hurt boxes, every pair */
void fighter_tiles(fighter_t *f);                           /* pass 1: tile runs when the frame changed */
void fighter_place(const fighter_t *f, uint16_t *y, uint16_t *x, int16_t cam_x, uint8_t n);   /* pass 2: SCB3/SCB4 of n sprites (>= ncols; the rest height 0) */
const char *fighter_state_name(uint8_t st);
const bstep_t *fighter_step(const fighter_t *f);
void fighter_play(fighter_t *f, uint8_t anim);              /* outside the state machine (select screen previews) */
void fighter_animate(fighter_t *f);
void fighter_revive(fighter_t *f);
/* a colour of f's palettes as shown: its tint applied (minions, main.c): 1 shade (half desaturated, 69 %), 2 ash (3/4
 * desaturated, 88 %, cold), 3 rust (half desaturated, 75 %, warm); never one of the playable colour sets */
uint16_t fighter_colour(const fighter_t *f, uint16_t c);
void fighter_load_pals(const fighter_t *f);                 /* its colour set through its tint into its hardware palettes */                          /* full life, getting up, invulnerable a moment */

#endif
