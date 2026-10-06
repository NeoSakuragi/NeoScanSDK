/* Beat 'em up fighter: one state machine for every character and every controller (player or AI); a character only
 * supplies data (bm_chars.c, exported from the KOF dictionaries by tools/brawler/export_bm.py).
 *
 * Coordinates (16.16 fixed point): X left/right on the floor, Z depth (0 = back edge of the walkable band, grows
 * toward the camera), Y height above the floor. Screen: x = X - camera, feet y = floor_top + Z - Y.
 * Hits: attack box vs hurt box overlap in X/Y, and |Z difference| <= Z_HIT. Draw order: by Z. */
#ifndef FIGHTER_H
#define FIGHTER_H
#include <stdint.h>
#include <neo_bank.h>
#include "bm_chars.h"
#include "gamedata.h"

/* banks (TODO #174, docs/rom_packer_rules.md "P ROM"): a fighter's bulk lives in its P2 bank (bm_bank[id], written by
 * tools/brawler/bank_pack.py): its frames (bframe_t, bpart_t, the tile numbers), its specials' script rows (bspec_row_t
 * with their objects), programs (bprim_t), parts, links and variant columns, its projectiles' rows (bprow_t, bpend_t).
 * Everything another fighter, combat, the AI or the HUD reads stays in the first MB: bchar_t, the animations and their
 * steps (boxes), throws, postures, palettes, routes, voices, the bspec_t / bproj_t headers. So the bank is needed only
 * where a fighter's own bulk is read: its update (fighter_update), its projectiles' (projectiles_update, proj_row), its
 * drawing (main.c draw: draw.s), and an attacker's box from a script row (combat, main.c dbg_draw: copied out under its
 * bank). Every switch is BANK_set(CH_BANK(ch)) ... BANK_set(old): no reader leaves the bank changed for its caller. */
extern const uint8_t bm_bank[BC_COUNT];
#define CH_BANK(ch) (bm_bank[(ch)->id])

#define FIX(v)   ((int32_t)(v) << 16)
#define INT(v)   ((int16_t)((v) >> 16))
extern int16_t floor_top;         /* screen y of the feet at Z = 0: the stage's (stage_t.floor_top, measured on its art; main.c
                                     stage_init), SELECT_FLOOR on the select screen; draw.s reads it too */
#define Z_DEPTH   64              /* walkable band depth in px */
#define Z_HIT     12              /* max depth difference for a hit / a grab */
#define CLOSE_X   40              /* an opponent this close (|dX|, |dZ| <= Z_HIT): A takes a route's close link (KOF's close normals) */
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
enum { R_LIGHT, R_HEAVY, R_KNOCKDOWN, R_LAUNCH, R_TRIP, R_BLOWBACK, R_SLAM, R_LIFT };   /* hit reactions (R_BLOWBACK: KOF's
                                     C+D, sent far); a special's body hit: R_HEAVY / R_KNOCKDOWN / R_LAUNCH / R_TRIP /
                                     R_SLAM / R_LIFT = KOF98's 258 reel / 283-285 blowback / 286 launch / 276 sweep /
                                     303 slam down / the launch straight up (fighter.c kof_react). A special's reaction
                                     may come packed: standing | juggled << 4 (KOF's reaction table by attack box,
                                     tools/kof96/handlers98.box_react; fighter_hit picks by the victim's height) */
/* buttons by meaning (TODO #71, Bruno 2026-10-05; 2026-10-06: C / D): A attack (every normal: the route trees, stick +
 * position pick the move), B jump (stick = direction; a route's B link = a jump-cancel on hit), C the special (the stick
 * picks the slot: neutral, forward, down, up, down-forward, up-forward; the A+B chord is gone), D the fury (the
 * fighter's desperation move). Tag mode (reserved, not built) has no button any more. Every press acts the frame it
 * comes. */
enum { IN_A = 1, IN_B = 2, IN_C = 4, IN_D = 8 };

typedef struct {                  /* what the controller wants this frame (player input or AI) */
    int8_t dx, dz;                /* stick: -1/0/1 (dz -1 = away from the camera) */
    uint8_t press;                /* IN_* pressed this frame */
    uint8_t run;                  /* forward double tap */
    int8_t  face;                 /* standing still: turn this way (AI faces its target; players leave 0) */
    uint8_t grab;                 /* AI: walking forward grabs on contact (players always grab) */
    uint8_t ai;                   /* the AI drives this fighter (enemies, the attract demo's P1) */
    uint8_t slow;                 /* walk at half speed (16.16: sub-pixel steps every frame; the AI's positioning walk) */
    uint8_t hold;                 /* IN_* held this frame (B held through the prejump = the regular jump, released = a hop) */
    uint8_t close;                /* an opponent within CLOSE_X (main.c close_marks): A picks the route's close link */
} intent_t;

/* ---- chain routes (Chain Lab, 2026-10-05): one route tree per fighter, data only ---------------------------------------
 * A tree blob (tools/brawler/export_bm.py from tools/brawler/routes/<fighter>.json, or the default tree = the old single
 * COMBO table; the Chain Lab page writes one into lab.buf): an rt_head_t, then nnodes rnode_t. Node 0 is "none"; a link
 * is a node index (0 = no link). A node is one hit: the move it plays (BA_*, or BS_* for a special), the hit weight and
 * the effect on the victim (the reaction), damage and push, its speed, the keep flag, and its links by input (RI_*). The game
 * reads the trees through route_tab[] (RAM, set at boot from bchar_t.routes), so a tree can be replaced while it runs. */
enum { RI_A, RI_B, RI_DA, RI_CA, RI_FA, RI_BA, RI_DFA,             /* normal links: A, B (a jump-cancel: its node is the air
                                                                              attack A plays in that jump), down+A, close A
                                                                              (an opponent within CLOSE_X), forward+A, back+A,
                                                                              down-forward+A (tree version 4) */
       RI_S = 9, RI_FS, RI_DS, RI_US, RI_DFS, RI_UFS,                      /* special links (enders): C, forward / down / up /
                                                                              down-forward / up-forward + C (slots 7, 8 unused) */
       RI_N = 15 };
enum { RF_SPECIAL = 1, RF_AIR = 2, RF_KEEP = 4 };     /* rnode_t.flags: anim is a BS_*; an air normal (anim: BA_ATK_C_JUMP /
                                                         D_JUMP / CD_JUMP = KOF's air C / D / C+D, the jump picks the
                                                         animation; its A links chain in the same jump, on hit);
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
_Static_assert(sizeof(rnode_t) == 24, "routes.py NODE_SIZE");
typedef struct {
    char    magic[2];             /* "RT" */
    uint8_t version, nnodes;      /* version 4 (TODO #71: one attack button; older trees are refused) */
    uint8_t root;                 /* the links from neutral (its own move unused) */
    uint8_t dash, nospec, hold;   /* run + A; C when the fighter has no special for it; the hold's third hit (C+D) */
    uint8_t air_a, air_b, air_cd; /* air normals: A, down+A, up+A in a jump (a jump-cancel: its B link's node instead) */
    uint8_t pad[5];
} rt_head_t;
#define TREE_VERSION 4
#define RT_NODE(t, i) ((const rnode_t *)((const uint8_t *)(t) + sizeof(rt_head_t) + (uint16_t)(i) * sizeof(rnode_t)))
extern const rt_head_t *route_tab[BC_COUNT];
/* specials by role (Brawler Lab Characters tab, 2026-10-05): every fighter's whole special pool is in the ROM
 * (bchar_t.specials); spec_tab[fighter] (RAM, set at boot from bchar_t.spmap; a data pack's roster section repoints it,
 * main.c gd_apply) maps the six C slots (BS_*, BS_COUNT = 6; named D, fD, dD, uD, dfD, ufD after their old D inputs: neutral,
 * forward, down, up, down-forward, up-forward + C today) to one of them (0xFF = none). BS_FURY: the fury (D), bchar_t.fury (game.json roster fury). */
#define BS_FURY BS_COUNT
#define BS_FURY_MAX (BS_COUNT + 1)   /* spec_ix only (down+D): the fury's MAX version, bchar_t.fury_max (0xFF: none -> the fury);
                                     played with spec_id BS_FURY (a fury in every respect) */
#define BS_FORM (BS_COUNT + 2)       /* the form link's transition (vocabulary form.change): bchar_t.form_spec, started by
                                     its trigger (FT_*), untouchable while it plays, ended by its P_FORM (fighter.c "form") */
enum { FT_NONE, FT_DOWN_D_FULL };    /* bchar_t.form_trig: down+D on the ground with a full meter */
enum { FX_NONE, FX_LIFE, FX_STAGE }; /* bchar_t.form_exit: back to the base form when a life is lost (and at a stage's
                                     start, as every player), or only at a stage's start */
extern const uint8_t *spec_tab[BC_COUNT];
uint8_t spec_ix(const bchar_t *ch, uint8_t role);   /* role -> index in ch->specials, 0xFF = none */
void specs_init(void);
/* voices (TODO #55, fighter.c): voice_tab[fighter] (RAM, set at boot from bchar_t.voices; a data pack's voices section
 * repoints it, main.c gd_apply) = its voice table, [voice id, at] per VK_* key (bm_chars.h) */
extern const uint8_t *voice_tab[BC_COUNT];
void voices_init(void);
void voice_play(const bchar_t *ch, uint8_t team, uint8_t key);   /* a key's voice now (events: the select screen's pick) */
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
    uint8_t  req;                 /* page: 1 = start training (fighter vs dummy), 2 = reset positions, 3 = enemy test
                                     (fighter vs the enemy definition `dummy`, its AI on), 4 = play campaign stage `dummy`
                                     from wave `wave` (>= its waves: the boss) with P1 = `fighter`, 5 = play the music
                                     command `dummy` (the Stages tab); the game clears it */
    uint8_t  fighter, dummy;      /* bm_chars indices (req 1); req 3: dummy = a genemies index (EN_*); req 4: a stage */
    uint8_t  load;                /* page: 1 = buf holds a tree for `fighter`: install it (the game clears it); 2 = back to
                                     the fighter's own tree; 3 = pack holds a data pack (gamedata.h gdpack_t): checked
                                     now, installed at the next safe point (pack_stat); 4 = back to the ROM's tables */
    uint8_t  active;              /* game: 1 while the training runs, 2 the enemy test */
    uint8_t  nev;                 /* game: events written (ring index = nev % LAB_NEV) */
    uint16_t frame;               /* game: training frames */
    uint8_t  combo_hits;          /* game: the readout on screen */
    uint8_t  wave;                /* page: req 4's first wave */
    uint16_t combo_dmg;
    lab_ev_t ev[LAB_NEV];
    uint8_t  buf[LAB_BUF];
    uint8_t  pack_stat, pack_pad; /* game: GD_* (gamedata.h) of the last load 3 / 4 */
    uint8_t  pack[GD_MAX];        /* page: a data pack (load 3) */
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
    uint8_t  buffered;            /* next combo input pressed during the current link (IN_* | 0x80 forward | 0x40 down | 0x20 back | 0x10 close) */
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
    uint8_t  spec_id, spec_prev_hit;   /* the special playing: its role (BS_*; spec_ix: its index in ch->specials);
                                        * spec_prev_hit: hit bits of its current row (bspec_row_t.hit) */
    const bbox_t *spec_atk;       /* special / projectile: attack box of the current script row (0 = none) */
    struct fighter *proj[2];      /* projectiles of the special playing */
    struct fighter *owner;        /* projectile: who threw it */
    uint8_t  ncols;               /* sprite columns of the shown frame (written by fighter_tiles) */
    uint8_t  landed;              /* the current attack connected (routes chain only on a hit) */
    uint8_t  chain_node, chain_t; /* Final Fight chain: the route step that hit, frames left to continue it from neutral */
    uint8_t  spec_buf;            /* C pressed during a normal: 0x80 | RI_S.. (its direction): the special it cancels into once it hits */
    uint8_t  still;               /* AI: frames walking without a walk intent (the walk holds AI_IDLE_DELAY frames) */            /* thrower X when the throw started (script X is relative to it) */
    uint8_t  spec_dmg, spec_react; /* special: damage and victim reaction (R_*) of the hit window open (bspec_row_t) */
    uint8_t  spec_fx;             /* special: KOF98 hit effect of the hit window open (bspec_row_t.fx: kind | burn << 6) */
    uint8_t  burn;                /* burnt by a fire hit: 1 purple, 2 orange (its palettes show KOF98's burn ramp) */
    int8_t   throw_face;          /* throw: the thrower's facing at the grab (the script's offsets are in it) */
    uint8_t  jump_kind;           /* the jump in progress: 0 regular (C held), 1 hop (C tapped) */
    uint8_t  jump_dir;            /* its direction: 0 vertical, 1 forward, 2 back (facing kept) */
    /* independent projectile (S_PROJ entity spawned by a special's bspec_t.proj; fields added at the end: draw.s pins
     * the ones above). pdef: its definition; prow: row of its flight (or of its end); pend: 1 its end rows play (a
     * travelling one hit), 2 its attack is spent (an eruption that clashed plays on), 3 an eruption that hit a fighter:
     * its attack box hits every other target it touches, each once (hit_mask: the crowd rule), its clash box spent;
     * pown: the clash box of the row */
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
    /* an enemy's definition (main.c enemy_init, genemy_t): its HUD name (0 = its fighter's), 16 custom colours for its
     * first palette (0 = its set's), its route tree (0 = route_tab's, its fighter's own) */
    const char *name;
    const uint16_t *cpal;
    const rt_head_t *tree;
    uint8_t  spec_ix;             /* the special playing: its index in ch->specials (spec_tab when it started); last, so
                                   * draw.s's offsets stay */
    /* a special read from the ROM (bspec_t.prog, fighter.c prog_update): its current animation and step (frames left
     * in it), op index / resume point, flags PF_*, the damage / reaction / effect of the hits it opens, its counter,
     * friction (0.16) and gravity (16.16; vx / vy are the fighter's) */
    const banim_t *pan;
    uint8_t  pstep, pleft, ppc, pres, pflags, pdmg, preact, pfx;
    int16_t  pcnt;
    uint16_t pfric;
    int32_t  pg;
    /* KOF98's reaction to a special's body hit (fighter.c kof_react, measured in our emulator): kmode 1 rising, 2
     * falling (0: the brawler's own knockdown physics); kdelay frames the victim stays put after the hit-stop; kg the
     * gravity (16.16), kgfr its decay per frame (0.16, 0 none), kgf the fall's gravity, kvfr the friction on vx (0.16, 0
     * none) applied while |vx| >= kvmin */
    int32_t  kg, kgf, kvmin;
    uint16_t kgfr, kvfr;
    uint8_t  kmode, kdelay;
    int8_t   spec_slide;          /* special: the reel slide of the hit window open (px, bspec_row_t.vx; -128: KOF98's 258, 65 px) */
    uint8_t  air_node;            /* a jump-cancel in progress: the route node A plays in this jump (0 = the tree's air entries) */
    uint8_t  flash;               /* frames left of the white flash (a special out of a hit spent double meter) */
    uint16_t meter;               /* the special meter (players; gmeter: full at the start, specials and furies spend it) */
    uint8_t  meter_t, pad_m;      /* frames toward the next point regained */
    uint8_t  spart, sarm;         /* special: the part playing (bspec_t.parts), the follow-up link armed + 1 (0 = none;
                                   * fighter.c "follow-ups") */
    uint16_t shrow;               /* special: the script row its last hit landed on + 1 (0 = none yet): a hit link's window */
    uint8_t  spend, plink;        /* a ROM special's follow-ups (prog_update P_CHECK / PC_LINK): the link presses of this
                                   * frame (bit k = bslink_t k; kept through hit-stop), the links armed in this part */
    uint8_t  phl;                 /* the link presses made in its hit-stops (KOF +$1AC: P_CHECK b = 1, TODO #140) */
    uint8_t  phit, pcatch;        /* a ROM special's catch (TODO #139, KOF +$19C): its routine's op (0xFF none); 3..1 the
                                   * frames after a catch box hit (a normal one, a dead one, then the routine), 0xFE spent */
    int16_t  phold;               /* the caught victim (target) held this many px in front (P_PLACE), 0 = where it stands */
    struct fighter *popp;         /* a ROM special's nearest opponent on its lane (PC_FAR before a hit sets target) */
    uint8_t  pdead, pdeadn;       /* a catch's dead frames left / to come (P_ONHIT a + 1: KOF counts the catching step's
                                   * hit-stop down at $1B402 before +$19C; TODO #79 / #84) */
    struct fighter *dance;        /* the fury that hit this fighter (fighter.c "dance"): while it plays the victim stays
                                   * in its reel (no recovery, no fall on death) and inside the screen (the wall rule: wall_update) */
    uint8_t  fury_buf, scancel;   /* the cancel rule (fighter.c "cancels", TODO #143): D pressed during a normal or a
                                   * special that may cancel (0x80 | 1 = down+D, the MAX); scancel: the special playing
                                   * landed a hit (its own or its projectile's) = a fury may cancel it */
    uint8_t  var;                 /* the special playing: its variant row (bspec_t.vars), latched at its start */
    uint8_t  form_from;           /* the form link: the base form's bm_chars index + 1 while in another form (0 = none) */
    const bthrow_t *thr;          /* a thrown victim's paired script (TODO #146): it plays its rows itself once its */
    struct fighter *thr_by;       /* thrower let go (fighter.c thrown_update); thr_by: who threw it (or holds it: a */
    uint8_t  thr_skip, cnc_buf;   /* hold hit); thr_skip: the frame of the hand-over, its update came after the thrower's;
                                   * cnc_buf: frames a C / D buffered in a throw / the hold finisher stays (fighter.c
                                   * "cancels" rule 4, CANCEL_BUF), 0 = gone; */
    uint32_t thr_pos;             /* thr_pos: its place in the script alone, 8.8 rows (acc is its animation's: its flight plays one) */
    uint8_t  drop, ko_voice;      /* the respawn (fighter.c "death and respawn", TODO #166 e): 1 dropping from the air
                                   * (untouchable, no control), 2 just landed (main.c knocks every enemy on screen down);
                                   * ko_voice: its death voice (VK_KO) already played (main.c's boss death sequence plays
                                   * it at the fall, TODO #172): none again at S_DEAD */
    uint8_t  pvl_id, pvl_n;       /* a ROM special's voice sent later (P_VOICE b > 0, KOF +$1B4 / +$1B6; TODO #163): its id,
                                   * the frames left (0 = none; counted down by its program's frames, then by the
                                   * fighter's own once the move ended; dropped when it is hit) */
    struct fighter *wall_by;      /* the wall rule (vocabulary stage.wall, TODO #173): the special (or its projectile)
                                   * whose hit this fighter reels / flies from; until it is down it stays inside the
                                   * walls and that special's attacker is held back with it (wall_update) */
    uint8_t  vlist, vent;         /* a ROM special's caught victim script (vocabulary hold.victim_list, TODO #173): the
                                   * list its target follows + 1 (0 none; bspec_t.vlists), the attacker step whose entry
                                   * was taken last (0xFF: none yet in this list) */
    uint8_t  pheld, wpad;         /* a special's button held this frame (PC_HELD: KOF's charge, Rugal's Kaiser Wave) */
    int32_t  py0;                 /* a projectile's height at its hit: its end rows' heights are from it (TODO #164) */
    const banim_t *fx_pan;        /* a step effect (bproj_t follow 8, anim.step_spawn): its owner's animation and step */
    uint8_t  fx_step, fx_pad;     /* when it was born; it ends when they change (KOF98 $3751A) */
} fighter_t;
extern int16_t wall_lo, wall_hi;  /* the walls (vocabulary stage.wall): world x of the screen edges' walls this frame
                                     (WALL_EDGE px in; wall_update), PC_WALL's test */



extern uint16_t stat_grabs, stat_specials, stat_throws, stat_escapes;   /* by enemies (escapes: by players); HUD */
#define NPJ 8                     /* projectile entities: fighter_t too, so one renderer / sort / guard / hit test; 8 = a
                                     Blitz Ball and its 4 live trail objects (KOF96 measured) + 3 for other throwers */
#define PJ_COLS 10                /* the projectile pool's sprites per entity on average: NPJ * PJ_COLS shared by width (main.c block_w) */
extern fighter_t projectiles[NPJ];
void projectile_reset(fighter_t *p);
void projectiles_update(int16_t cam_x);   /* the independent projectiles' flight, after the fighters' update */

void fighter_init(fighter_t *f, const bchar_t *ch, uint8_t set, uint8_t palbase, uint8_t team, int16_t x, int16_t z);
void fighter_update(fighter_t *f, const intent_t *in);
void fighter_hit(fighter_t *atk, fighter_t *vic, uint8_t damage, uint8_t reaction, int8_t push);   /* attack connected */
void spark_hit(int16_t wx, int16_t sy, uint8_t big, int8_t facing);   /* main.c: KOF98 hit spark at world x, screen y */
void combat(fighter_t **fs, uint8_t n, const fighter_t *only);   /* attack boxes vs hurt boxes, every pair; only (not
                                                               0): that attacker's own boxes and pushes alone (the super
                                                               flash: its fury hits the frozen world, nothing else does) */
void fighter_tiles(fighter_t *f);                           /* pass 1: tile runs when the frame changed */
void fighter_place(const fighter_t *f, uint16_t *y, uint16_t *x, int16_t cam_x, uint8_t n);   /* pass 2: SCB3/SCB4 of n sprites (>= ncols; the rest height 0) */
void wall_update(fighter_t **fs, uint8_t n, int16_t cam_x);   /* after the camera: the wall rule (a special's victims and
                                                                  their attacker inside the screen's walls) */
void super_flash(fighter_t *f);      /* main.c: the fury's super flash starts (fx.super_flash: the game freezes except f) */
const char *fighter_state_name(uint8_t st);
const bstep_t *fighter_step(const fighter_t *f);
void fighter_play(fighter_t *f, uint8_t anim);              /* outside the state machine (select screen previews) */
void fighter_animate(fighter_t *f);
void fighter_revive(fighter_t *f);
void fighter_respawn(fighter_t *f);  /* a life used: full life, dropping from above the screen where it is (TODO #166 e) */
void fighter_quake(const fighter_t *by, fighter_t *v);   /* the respawn's landing: v knocked down, away from by, no damage */
void throw_fx(int16_t wx, int16_t sy, int8_t facing);    /* main.c: the throw-start effect (fx.throw_start) at world x,
                                                            screen y (its anchor), mirrored for a thrower facing right */
/* a colour of f's palettes as shown: its tint applied (minions, main.c): 1 shade (half desaturated, 69 %), 2 ash (3/4
 * desaturated, 88 %, cold), 3 rust (half desaturated, 75 %, warm); never one of the playable colour sets */
uint16_t fighter_colour(const fighter_t *f, uint16_t c);
const uint16_t *fighter_src_pal(const fighter_t *f, uint8_t i);   /* its palette i as defined (set, custom colours) */
#define FIGHTER_NAME(f) ((f)->name ? (f)->name : (f)->ch->name)
void fighter_load_pals(const fighter_t *f);                 /* its colour set through its tint into its hardware palettes */                          /* full life, getting up, invulnerable a moment */

#endif
