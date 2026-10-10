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
extern const uint8_t *zback;      /* the walkable floor's back edge along the stage (Bruno 2026-10-09, note 20261009-102742-5d29:
                                     "the maximum depth the players can be in this particular area, otherwise we start
                                     stepping over the background pixels"): the smallest Z a fighter may have, one byte per
                                     16 px of world x (game.json depth -> game_tables gback_rom[background], zback_n
                                     columns; main.c stage_init), 0 = none (the select screen, a stage without a table) */
extern uint8_t zback_n;
int16_t z_back(int16_t x);        /* the smallest Z at world x (0 without a table; x past either end: the end column's) */
#define Z_HIT     12              /* max depth difference for a hit / a grab */
#define CLOSE_X   40              /* an opponent this close (|dX|, |dZ| <= Z_HIT): A takes a route's close link (KOF's close normals) */
#define MAX_COLS  20              /* hardware sprites reserved per fighter (Billy's widest frame: 19) */
#define MAX_PALS  8               /* palettes reserved per fighter (Terry with his effects: 5) */
#define SFX_PAL   224             /* KOF's shared effects bank (TODO #214): its palettes SFX_PAL .. + SFX_NPAL - 1 (bm_chars.h,
                                     at most SFX_NPAL_MAX; main.c sparks_init loads bm_sfx_pals), absolute like KOF98's
                                     palette RAM 80-127: a frame part's pal | 0x80 draws with SFX_PAL + (pal & 0x7F)
                                     (draw.s), never with its owner's palettes (the white flash, the burn leave them) */
#define SFX_NPAL_MAX 16           /* (224-239: past the select screen's 23 actors x MAX_PALS from 16, below the big
                                     portraits' 240; TODO #216: 11 with Ralf's AAAA, Iori's and Yamazaki's furies) */
extern int16_t cam_x;             /* main.c: the camera's left edge (world px; P_WARP's screen mode) */
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
/* buttons by meaning (TODO #71, Bruno 2026-10-05; 2026-10-06: C / D; 2026-10-08 the new system, docs/brawler_gold.md): A
 * attack (every normal: the chain, stick + position pick the move; a double direction + A: the Blitz), B jump (stick =
 * direction), C the special (the stick picks the slot: neutral, forward, down, up, down-forward, up-forward), D the fury.
 * A+B = C everywhere (main.c read_player turns the chord into C; intent_t.chord: its second button came late). Every press
 * acts the frame it comes. */
enum { IN_A = 1, IN_B = 2, IN_C = 4, IN_D = 8 };

struct fighter;
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
    struct fighter *lie;          /* the nearest opponent lying (S_DOWN, alive) within DOWN_REACH (main.c close_marks): up /
                                     down + A leaps at it with the fighter's down attack (BS_DOWNATK, TODO #218) */
    uint8_t blitz;                /* the Blitz (main.c read_player, fighter.c "Blitz"): A pressed this frame after a double
                                     direction, its slot BZ_* + 1 (forward,forward / down,down / down,up / up,up); 0 none */
    uint8_t chord;                /* A+B = C this frame with its second button up to gblitz.chord frames after the first
                                     (the first one already acted: fighter.c turns a prejump / a normal's start into the C) */
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
       RI_UA = 7,                                                          /* up+A (revamp 1A: the chain's up finisher; a tree
                                                                              without it: 0, the fallback below) */
       RI_THEN = 8,                                                        /* not an input (Kim gold, 2026-10-08): the node
                                                                              played as this one's move ends, whatever
                                                                              happened: a finisher of several moves back to
                                                                              back (routes.py: a finisher named as a list) */
       RI_S = 9, RI_FS, RI_DS, RI_US, RI_DFS, RI_UFS,                      /* special links (enders): C, forward / down / up /
                                                                              down-forward / up-forward + C (slot 8: RI_THEN) */
       RI_N = 15 };
enum { RF_SPECIAL = 1, RF_AIR = 2, RF_KEEP = 4, RF_THROW = 8, RF_HEAVY_SFX = 16, RF_LAB = 32 };   /* RF_LAB (2026-10-10, the
                                                         Character Lab's chain presses, fighter.c lab_node): the node plays the
                                                         LAB ENTRY in its speed word (an animation $NN of the Lab build's
                                                         fighter, LE_SPEC | k a special of his pool) instead of a move, P1
                                                         only, as the Try queue plays it (free, not invincible); its links go
                                                         on from it on a hit as from a normal; its hit-stop is the node's.
                                                         Only the game sets it, in P1's Lab chain (the TRY blob's LS_CHAIN
                                                         record, fighter.c lab_chain): no exported tree has it */   /* (RF_HEAVY_SFX: its hits sound
                                                         as a heavy normal's, routes.py "sound": "heavy": Kim's $96) */   /* rnode_t.flags (RF_THROW, revamp 1A: the chain's back
                                                         finisher, the fighter's back throw on the victim the last link hit,
                                                         fighter.c chain_throw; no throw: the neutral finisher); anim is a BS_*; an air normal (anim: BA_ATK_C_JUMP /
                                                         D_JUMP / CD_JUMP = KOF's air C / D / C+D, the jump picks the
                                                         animation; its A links chain in the same jump, on hit);
                                                         keep the full animation on hit: the move plays to its end, the
                                                         buffered input then takes its link (clear, the default since
                                                         2026-10-05: on hit the next link starts as soon as its input comes,
                                                         after the hit-stop) */
enum { RE_NONE, RE_KNOCKDOWN, RE_LAUNCH, RE_TRIP, RE_BLOWBACK, RE_SLAM };   /* rnode_t.effect (RE_SLAM, revamp 1A: the
                                                         down finisher's ground slam: knocked to the floor at once, it bounces
                                                         up high, juggle-able, fighter.c "chain core") */
typedef struct {
    uint8_t anim, flags;
    uint8_t weight, effect;       /* weight 0 light / 1 strong (the victim's hit animation and stun, effect none) */
    uint8_t damage;
    int8_t  push;                 /* px the victim slides back on hit (effect none) */
    uint16_t speed;               /* playback speed, 8.8 fixed point (0x0100 = KOF's own timing; 0x0040-0x0400): the move's
                                     animation, or the special's script, advances by it every frame (fighter.c anim_tick) */
    uint8_t next[RI_N];           /* links by RI_* */
    uint8_t hitstop;              /* its hit-stop frames (revamp 1A: one scale for every fighter, jab 6 -> finisher 12 by link
                                     index / move class, routes.py chain_tree); 0 = the engine's HITSTOP */
} rnode_t;
_Static_assert(sizeof(rnode_t) == 24, "routes.py NODE_SIZE");
typedef struct {
    char    magic[2];             /* "RT" */
    uint8_t version, nnodes;      /* version 4 (TODO #71: one attack button; older trees are refused) */
    uint8_t root;                 /* the links from neutral (its own move unused) */
    uint8_t dash, nospec, hold;   /* run + A; C when the fighter has no special for it; the hold's third hit (C+D) */
    uint8_t air_a, air_b, air_cd; /* air normals: A, down+A, up+A in a jump (a jump-cancel: its B link's node instead) */
    uint8_t arch, links;          /* revamp 1A: the fighter's archetype + 1 (1 fast, 2 balanced, 3 heavy; 0 = a tree not made
                                     by routes.py chain_tree) and its chain's length (links from neutral to the finisher) */
    uint8_t pad[3];
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
#define BS_AIR (BS_COUNT + 3)        /* an air special (vocabulary air.special, TODO #200 / #221: game.json roster
                                     air_specials, bm_air[id]): a press in a jump, its button (A or C) and the stick's
                                     slot (the ground's six C slots) as its table entry says (fighter.c air_pick); an A one
                                     in the air normal's place (no meter), a C one a C special's meter; its program plays
                                     from the jump and lands (Kizuna's j.2B / j.2C / j.623C / j.421C; SS2 Hanzo's shuriken,
                                     TODO #211: one projectile at a time, else the air normal); no cancels out of it;
                                     fighter_t.spec_ix = the entry's special (spec_ix(ch, BS_AIR) = 0xFF) */
#define BS_DOWNATK (BS_COUNT + 4)    /* the down attack (vocabulary attack.down, TODO #218: game.json roster down_attack,
                                     bchar_t.down_spec): up / down + A on the ground with an opponent lying in reach
                                     (intent_t.lie) plays it at that opponent (fighter_t.dtgt): its program's P_HOME leaps
                                     at it, its hit reaches it lying (combat: LIE_BOX) and pops it off the floor (react);
                                     the target stays down while it comes (dpin); no meter, no cancels out of it */
#define BS_THROW (BS_COUNT + 5)      /* a throw played from a grab special's ROM program (revamp phase 3, docs/brawler_feel.md 8h:
                                     no command-grab inputs; game.json roster[].throws, bm_xthr): the hold's up / down + A
                                     (bxthr_t up / down) on the held victim, released into a reel the special's catch takes;
                                     no meter, untouchable to its end, no cancels out of it; fighter_t.spec_ix = the entry's
                                     special (spec_ix(ch, BS_THROW) = 0xFF). The super throw plays its special as a fury
                                     (BS_FURY, fighter_t.sthr 2: its flash, its flash pose, its tier) */
#define BS_BLITZ (BS_COUNT + 6)      /* the Blitz (Bruno 2026-10-08, fighter.c "Blitz"): a special of the pool played free from
                                     a double direction + A (gblitz_rom), not invincible, its own recovery, its damage scaled
                                     (gblitz.scale); cancels on hit into a C special or the fury; fighter_t.spec_ix = the
                                     slot's special (spec_ix(ch, BS_BLITZ) = 0xFF) */
#define DOWN_REACH 160               /* px (x) to a lying opponent the down attack leaps at (any lane of the band); Double
                                     Dragon has no limit (one opponent, its leap = 64 frames whatever the distance) */
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
void fighter_guard_sound(void);              /* the guard sound (game.json hit_sounds.guard): unused, the brawler has no guard yet */
void routes_init(void);

/* Chain Lab mailbox (examples/brawler/README.md "Chain Lab"): the page writes it from JavaScript, the game reads it at the
 * start of a tick; the game logs P1's route steps into ev[] (a ring) for the page's per-link readout. */
enum { LE_START, LE_HIT, LE_END, LE_SPECIAL, LE_CHAINWIN };   /* lab_ev_t.kind */
enum { LH_NEUTRAL, LH_AFTER_END, LH_CANCEL, LH_WINDOW };      /* LE_START: how the node started */
typedef struct { uint16_t frame; uint8_t kind, node, how, val; } lab_ev_t;   /* val: LE_HIT damage, LE_SPECIAL BS_*,
                                                                                 LE_END 1 = it had hit */
#define LAB_NEV  64
#define LAB_BUF  (sizeof(rt_head_t) + 128 * sizeof(rnode_t))
/* "Try in game" lab entries (u16): an animation $NN of the Lab build's fighter (< LE_SPEC: his LAB special plays it,
 * bm_lab), LE_SPEC | k = special k of the fighter's pool, LE_THROW | t = his throw BT_* t (a grab slot's first entry: the
 * held victim thrown); LE_NONE ends a list */
#define LE_SPEC  0x1000
#define LE_THROW 0x2000
#define LE_MOVE  0x4000         /* LE_MOVE | m = his standard move BA_* m played as a normal (a chain press only) */
#define LE_NONE  0xFFFF
#define LQ_MAX   32               /* a queue's entries */
#define LO_MAX   8                /* a slot's entries */
#define TRY_VERSION 3             /* lab.tblob's format (fighter.h lab_t; lab.js encodeTry): 1 without knobs, 2 with them, 3
                                     with the chain (LS_CHAIN / LS_RETIME records) */
#define LC_MAX   8                /* a chain's presses (LS_CHAIN) */
#define LRT_MAX  8                /* retimed moves (LS_RETIME records) */
#define LRT_SEG  12               /* a retimed move's segments */
#define KN_MAX   32               /* knob rows a TRY blob carries (LS_KNOB records) */
#define TRY_MAX  1280             /* lab.tblob: 8 + 2 LQ_MAX + LS_COUNT (2 + 2 LO_MAX) = 558, + KN_MAX knob records of 14
                                     = 1006, + the chain (2 + 4 LC_MAX) + LRT_MAX retime records (4 + 2 LRT_SEG) = 1264
                                     (fighter.c asserts it); its size reaches the Player as the shell anchor's
                                     ram.tblob_size (lab_pack.py ram_map) */
/* PIECE KNOBS (Bruno 2026-10-10: "each special move comes with its key params and default values, adjustable in the
 * Assembly"; fighter.c "knobs"): a decoded special's key parameters overridden per SLOT (the same piece fast on one slot,
 * slow on another). A row: the sheet slot (LS_*, LS_QUEUE the Try queue) and the pool special it applies to, its kind
 * and operand, a match and a value (both 16.16 or plain, by kind). Two sources, one path: the shipped table
 * (game.json roster[].knobs -> gknob_rom[fighter], build_tables.py knob_tables) and, for P1 while the Lab's TRY blob is
 * on, the blob's own rows (LS_KNOB records, version 2). No row = the special as the export made it (byte for byte). */
typedef struct { uint8_t slot, spec, kind, a; int32_t match, val; } gknob_t;   /* kind 0 ends a table */
enum { KN_END, KN_SET,            /* P_SET of register a whose value is match (16.16) plays val instead (speed, rise, dive) */
       KN_PSPEED,                 /* its travelling objects fly val / 256 times as fast (their rows' x from row 0, wrap_x) */
       KN_PHITS,                  /* its travelling objects hit val times (re-armed every stop frames, KN_STOP if none) */
       KN_DMG };                  /* its hits deal val / 256 of their damage (the body's and its objects') */
#define KN_STOP 4                 /* a knobbed object's frames between hits when its data has none (KOF98's counted objects) */
#define LS_KNOB  0x80             /* a TRY blob v2 record of 6 words: one knob row (slot, spec, kind, a, match, val; BE) */
#define LS_QUEUE 0xFE             /* a knob row's slot: the Try queue's entries */
/* THE CHAIN (TRY blob version 3, 2026-10-10, Bruno: "there is no tree: 1 chain with a bunch of finishers"; fighter.c
 * lab_chain): [LS_CHAIN][2 n][n entries][n words hit-stop << 8] = presses 1..n of P1's chain (the last one the neutral
 * finisher), each an animation $NN, LE_SPEC | k, LE_MOVE | m or LE_NONE (the game's own press), each with its hit-stop
 * (0: the game's; the last press's is every finisher's); n = the length of his chain. [LS_RETIME][1 + k][move BA_*]
 * [k targets] = a move's segment targets (0: the source's), gretime_t's, read before rt_tab for his fighter. The
 * finishers by stick and the hold are the slots (LS_FIN_*, LS_GRAB_*). Both records have the slot records' shape
 * ([id][n][n words]): a reader of version 1 / 2's shape walks over them. */
#define LS_CHAIN  0x81
#define LS_RETIME 0x82
extern const gknob_t *const gknob_rom[];   /* game_tables.c: per fighter (bm_chars order) its shipped knob rows */
typedef struct { uint8_t spec, kind, a, pad; int32_t match, vmin, vmax; } gkcat_t;   /* the knob CATALOGUE (build_tables.py
                                     knob tables, from arb_pieces/<f>.json "knobs"): per fighter every knob row its pool's
                                     specials accept and its value bounds (the Assembly's min / max as engine values); kind 0
                                     ends. A TRY blob's knob rows are checked against it (unknown: refused, lstat 9) and their
                                     values clamped into it: the page's / the Player's bytes are never trusted */
extern const gkcat_t *const gkcat_rom[];   /* game_tables.c: per fighter (bm_chars order) */
enum { LQ_LOOP = 1, LQ_NOW = 2 }; /* the TRY blob's queue flags: the queue plays again from its start; it starts now (once; A from neutral
                                     plays it whenever a queue is set) */
enum { LS_FIN_FWD, LS_FIN_UP, LS_FIN_DOWN, LS_FIN_DF, LS_FIN_BACK,   /* the arbitration sheet's slots (chainlab/arbitrage.js */
       LS_BZ_FF, LS_BZ_DD, LS_BZ_UU, LS_BZ_DU,                       /* ids, in its order): the chain's last hit + a direction, */
       LS_ABZ_FF, LS_ABZ_DD, LS_ABZ_UU, LS_ABZ_DU,                   /* the Blitz, the air Blitz, the C specials (C in a */
       LS_SP_C, LS_SP_FC, LS_SP_DC, LS_ASP_C, LS_ASP_FC, LS_ASP_DC,  /* direction without a slot: the neutral's), the air */
       LS_AIR_A, LS_AIR_DA, LS_GRAB_HIT, LS_GRAB_FIN, LS_GRAB_FWD,   /* specials, the air normals, the hold (its hit, its */
       LS_GRAB_BACK, LS_FURY, LS_MAX, LS_COUNT };                    /* finisher, the throws), the fury, the MAX */
typedef struct {
    char     magic[4];            /* "LAB1" while the page drives the game */
    uint8_t  req;                 /* page: 1 = start training (fighter vs dummy), 2 = reset positions, 3 = enemy test
                                     (fighter vs the enemy definition `dummy`, its AI on), 4 = play campaign stage `dummy`
                                     from wave `wave` (>= its waves: the boss) with P1 = `fighter`, 5 = play the music
                                     command `dummy` (the Stages tab); the game clears it */
    uint8_t  fighter, dummy;      /* bm_chars indices (req 1); req 3: dummy = a genemies index (EN_*); req 4: a stage */
    uint8_t  load;                /* page: 1 = buf holds a tree for `fighter`: install it (the game clears it); 2 = back to
                                     the fighter's own tree; 3 = pack holds a data pack (gamedata.h gdpack_t): checked
                                     now, installed at the next safe point (pack_stat); 4 = back to the ROM's tables;
                                     5 = buf holds a chain override for `fighter` (revamp 5, the chain tool): its tree,
                                     then a retime table (gretime_t rows, t = an offset from buf): route_tab[fighter]
                                     and rt_tab point at them (fighter.c lab_install; 2 = both back to the ROM's);
                                     6 = tblob holds a TRY blob (the queue and the arbitration slots of P1; lstat;
                                     fighter.c "Lab: try in game") */
    uint8_t  active;              /* game: 1 while the training runs, 2 the enemy test */
    uint8_t  nev;                 /* game: events written (ring index = nev % LAB_NEV) */
    uint16_t frame;               /* game: training frames */
    uint8_t  combo_hits;          /* game: the readout on screen */
    uint8_t  wave;                /* page: req 4's first wave */
    uint16_t combo_dmg;
    lab_ev_t ev[LAB_NEV];
    uint8_t  buf[LAB_BUF];
    uint8_t  pack_stat;           /* game: GD_* (gamedata.h) of the last load 3 / 4 */
    uint8_t  p1_life;             /* page / proofs: 1 = P1's life left to the game (0: held full, nobody hurts P1) */
    uint8_t  pack[GD_MAX];        /* page: a data pack (load 3) */
    /* "Try in game" / the live config (Bruno 2026-10-10; tools/brawler/chainlab/lab.js encodeTry, the ONE encoder the
       pages, the server and the Player use; fighter.c "Lab: try in game"): load 6 = tblob holds a TRY blob, version 1
       or 2, big-endian: [0] 'L' [1] 'T' [2] version [3] fighter (bm_chars index, P1's) [4] queue flags LQ_* [5] qn, the
       queue's entries (<= LQ_MAX) [6] ns, the slot records [7] 0; then qn entries (u16 LE_* words); then ns records
       [slot LS_*][n <= LO_MAX][n entries]. Version 2 adds knob records among them (any order, <= KN_MAX): [LS_KNOB][6]
       [slot LS_* / LS_QUEUE][pool index][kind KN_*][a][match i32][val i32] (a reader of version 1's shape walks over
       them as slot records: the Player's parse is unchanged). The whole config at once: a slot not named plays the game's own move, qn 0 = no
       queue. WHEN: checked at the load, PENDING (lstat 2) until P1 is next in neutral (standing / walking; never mid-move
       nor in a hit stun), then applied (lstat 1); tnow = 1 written with the load: applied on the next tick whatever P1
       does ("apply now": the move playing finishes as it is, nothing resets) */
    uint8_t  tnow;                /* page: 1 = apply the TRY blob now (the game clears it as it applies) */
    uint8_t  lstat;               /* game: the last load 6: 2 pending, 1 applied, 0x80 | n refused (nothing changed): 1 an animation
                                     the build lacks (not its LAB fighter, or no such $NN), 2 a special the pool lacks, 3 a
                                     throw the fighter lacks, 4 a throw outside a grab slot (or not its first entry), 5 a
                                     list too long, 6 not a TRY blob of version 1 / 2 / 3, 7 the blob runs past TRY_MAX, 8 no such
                                     slot, 9 a knob row its catalogue lacks, 10 a chain whose length is not his chain's
                                     (or two chains), 11 a chain press that cannot be one (a throw, a move he lacks), 12 a
                                     retime row it cannot take (a move without segments, a wrong count, too many) */
    uint8_t  qpos;                /* game: the entry playing (its index in its list) */
    uint16_t cur;                 /* game: P1's lab entry playing (LE_NONE: none) */
    uint8_t  tblob[TRY_MAX];      /* page (load 6): the TRY blob */
} lab_t;
extern lab_t lab;
/* PRACTICE MODE settings (Lab builds only, -DLAB_BUILD=1: make LAB_FIGHTER=<f> / LAB_SHELL=1; main.c "PRACTICE MODE";
 * Bruno 2026-10-10). The RAM block `prac` (symbol `prac` in the build's rom.elf, section .noinit: crt0 never clears it,
 * so it survives a reset, a pack swap, a new lab request; at power-on it is random until the game finds no "PRC1"
 * and writes the defaults). The START menu, the Player and the page all read / write the same bytes:
 *   +0  magic "PRC1"
 *   +4  set[PS_COUNT]: one byte a setting, PS_* below; a value out of range = the whole block back to the defaults
 *       (default first in each list = today's Chain Lab training)
 *   +16 menu      game: 1 while the START menu is open (the game paused)
 *   +17 fighter   P1 at boot when the build has no LAB fighter (bm_chars index; a LAB_FIGHTER build boots his)
 *   +18 dummy     the dummies' fighter at boot (bm_chars index; later the lab's lab.dummy)
 *   +19 pad
 * A write takes effect on the next tick: the holds (life, gauge, drive) every tick; a new dummy count / behaviour
 * respawns the dummies at their marks; waves off takes the wave's enemies off. */
enum { PS_FURY,                   /* the hidden fury gauge: 0 the game's, 1 held full, 2 held empty */
       PS_MAX,                    /* 0 off, 1 MAX ready: P1's life held low (gmeter.low: the red blinking bar), gauge + drive full */
       PS_DRIVE,                  /* 0 the game's, 1 infinite (held full) */
       PS_LIFE,                   /* P1's life: 0 refilled (held full), 1 the game's (a KO revives), 2 held low */
       PS_DUMMIES,                /* 0-4 dummies (fighter slots 2..) */
       PS_MODE,                   /* the dummies: 0 stand, 1 their AI (the minion preset), 2 walk in and attack (A) */
       PS_WAVES,                  /* 0 off, 1 the first stage's waves come in turn, one after the other is beaten (the slots after the dummies) */
       PS_DLIFE,                  /* the dummies' life: 0 infinite (refilled), 1 normal (beaten: back at the mark) */
       PS_BOXES,                  /* the box viewer: 0 off, 1 on (START used to toggle it) */
       PS_COUNT };
typedef struct {
    char    magic[4];
    uint8_t set[12];              /* PS_COUNT used */
    uint8_t menu, fighter, dummy, pad;
} prac_t;
#if LAB_BUILD
extern prac_t prac;
#endif
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
    int8_t   zfront;              /* drawn in front of a fighter at the same Z (throw victims, 1), behind (-1: an effect
                                     KOF draws behind its owner, bproj_t back, TODO #214) */
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
    uint8_t  burn_t;              /* the burn cycle's step its palettes show (fighter.c burn_show) */
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
    uint8_t  pstep, pleft, pflags, pdmg, preact, pfx;
    uint16_t ppc, pres;           /* (16 bits since TODO #136: the Phoenix's program has 300+ ops) */
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
    uint8_t  flash;               /* frames left of a white flash (ai.c's ready pulse; meter_tick gives the colours back) */
    uint16_t drive;               /* the drive meter (players; gmeter: chunks x chunk points, full at the start, a point back
                                     a frame; C specials and breakers spend it) */
    uint16_t fgauge;              /* the hidden fury gauge (players; gmeter.fury_max = full: D plays the fury / the MAX) */
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
    uint8_t  kthud, kthud_pad;    /* kthud >= 1: its floor contacts in a knockdown play game.json hit_sounds.bounce (fighter.c
                                   * floor_thud; main.c boss_ko_start: the boss's death fall, both bounces), each one
                                   * counted (kthud = 1 + the contacts so far: 3 = the second, main.c boss_ko_tick) */
    uint8_t  pvl_id, pvl_n;       /* a ROM special's voice sent later (P_VOICE b > 0, KOF +$1B4 / +$1B6; TODO #163): its id,
                                   * the frames left (0 = none; counted down by its program's frames, then by the
                                   * fighter's own once the move ended; dropped when it is hit) */
    struct fighter *wall_by;      /* the wall rule (vocabulary stage.wall, TODO #173): the special (or its projectile)
                                   * whose hit this fighter reels / flies from; until it is down it stays inside the
                                   * walls and that special's attacker is held back with it (wall_update) */
    struct fighter *jug_by;       /* the juggle window (branch.cancel rule 5): the fighter that cancelled a throw's
                                   * impact / a catch's slam into a special or fury: its follow-up (body or projectile)
                                   * may hit this victim while it is thrown or airborne, until it lands (0 none) */
    uint8_t  vlist, vent;         /* a ROM special's caught victim script (vocabulary hold.victim_list, TODO #173): the
                                   * list its target follows + 1 (0 none; bspec_t.vlists), the attacker step whose entry
                                   * was taken last (0xFF: none yet in this list) */
    uint8_t  pheld, vfr;          /* a special's button held this frame (PC_HELD: KOF's charge, Rugal's Kaiser Wave);
                                   * vfr: the frames its victim list has run (VL_FRAMES: the entry, TODO #213) */
    int32_t  py0;                 /* a projectile's height at its hit: its end rows' heights are from it (TODO #164); an air
                                     projectile's (bproj_t air) thrower's height at its spawn: its rows' heights count from it (TODO #211) */
    const banim_t *fx_pan;        /* a step effect (bproj_t follow 8, anim.step_spawn): its owner's animation and step */
    uint8_t  fx_step, vfly;       /* when it was born; it ends when they change (KOF98 $3751A); vfly: a caught victim
                                   * a flying victim list moves (VL_FLY, fighter.c vlist_apply): its own S_HITSTUN update
                                   * leaves its body alone while it counts down (refreshed every frame of the list) */
    uint8_t  fpose, phh;          /* the fury's flash pose (TODO #145, fighter.c "flash pose"): 0 not started, 1 + the
                                   * frame of the freeze it shows, 0xFF over (the fury plays from its first frame); phh:
                                   * its hold (PF_HOLD) came from a hold hit or a standing release (HY_HOLD / VL_STAND,
                                   * TODO #220): a hit by another box lets the victim go with that hit's reaction */
    uint16_t dizzy;               /* a stun strike's victim (bthrow_t.stun, TODO #212: Cheng-Fu's throw): its S_HITSTUN
                                   * lasts this many frames, open to any hit; a hit (enter) ends it (0 none) */
    int32_t  kax;                 /* a source reaction (TODO #136, vocabulary reaction.source_motion, fighter.c src_react):
                                   * the reel's x acceleration (16.16, world) */
    uint8_t  ksr, ksn;            /* the source reaction playing (bm_sreact index + 1, 0 none), the frames its reel still
                                   * slides / its landing still pauses */
    uint8_t  vph, pbd;            /* vph: the victim phases a special's P_VPHASE holds this fighter in (VPH_*, fighter.c
                                   * vphase; Kizuna's +$1AF); pbd: its special's screen effect on (P_SCREEN) */
    struct fighter *vph_by, *vtgt;  /* vph_by: the special that holds it in them (they end when it no longer plays);
                                   * vtgt: the victim its own P_VPHASE took first (its later phases go to that one, not
                                   * to a crowd member hit since) */
    uint8_t  spec_sr, pstill;     /* special: the source reactions of the hit window open (bstep_t.hy under SF_SREACT);
                                   * pstill: the first frame after its hit-stop, its program's P_MOVE / P_FALL skipped
                                   * (Kizuna's: the attacker, as its victim, still that frame [meas: kim136]) */
    struct fighter *dtgt;         /* its down attack's target (BS_DOWNATK, TODO #218): P_HOME's aim, PC_TDOWN's test, the
                                   * one lying fighter its hit reaches; cleared by its hit and special_end */
    uint8_t  dpin;                /* down attacks coming at this lying fighter: it stays down meanwhile (S_DOWN, at most
                                   * DOWN_PIN frames more: Double Dragon's victim lies dizzy) */
    uint8_t  mash, spmash;        /* a mash (vocabulary input.mash, TODO #220, fighter.c MASH_GAP): frames left for the
                                   * next press to count as one (from the special's start, again from each one read);
                                   * spmash: this frame's link presses made inside that window (P_CHECK b 2) */
    uint8_t  vsigp, vspad;        /* its P_VSIG signals this frame, taken by vlist_apply after its placement (TODO #220) */
    /* the chain core (revamp 1A, fighter.c "chain core"): buf_age = frames since the buffered press (hit-stop frames not
     * counted: a press in the freeze is latched), the attack buffer's age; jug_n = air hits taken in this juggle (the cap,
     * gchain.juggle_cap: then untouchable until it lands); kfloor = 1 once its knockdown touched the floor (downed:
     * untouchable until it stands; a slam's bounce excepted: kslam); guard / guard_by = a player's untouchable window
     * after a hit (only guard_by, the one that hit it, reaches it meanwhile); cthrow = its back throw out of a chain
     * plays (invincible to its control return) */
    uint8_t  buf_age, jug_n;
    uint8_t  kfloor, kslam;
    uint8_t  guard, cthrow;
    uint8_t  ldmg, lpad;          /* the normal playing: the victims its damage was dealt to (bit per fighter_t.idx; its node's
                                     damage once per victim, on the first hit: fixed damage, "chain core") */
    struct fighter *guard_by;
    const uint16_t *rt_S, *rt_T;  /* retiming (fighter.c "retiming"): the move's segments' source lengths (bm_seg) and
                                   * targets (0 = the source's), rt_nseg of them; rt_p the segment playing, rt_n its game
                                   * frames so far, rt_err its clock; rt_debt source frames due, not played yet (a hit
                                   * window stopped the frame); rt_hold / rt_dx / rt_dy a stretched ROM program's motion
                                   * still to spread over the frames its source frame shows; rt_flags RT_* (0: no retime) */
    uint16_t rt_n, rt_err;
    uint8_t  rt_nseg, rt_p, rt_debt, rt_flags, rt_hold, rt_pad;
    int32_t  rt_dx, rt_dy;
    /* the meter and the damage tiers (revamp 2, fighter.c "the meter", "damage tiers"): dsc = the tier scale (8.8) of the
     * special playing (a projectile: its thrower's at its spawn); dacc = the fraction of a scaled hit carried to the next
     * (the owner's, for its objects too); brk = a breaker plays (it blinks white); ovl = the palette overlay shown (0 its
     * colours, OVL_WHITE the breaker's blink, OVL_RED the red state's); fmax = the fury playing started as the MAX */
    uint16_t dsc;
    uint8_t  dacc, brk, ovl, fmax;
    uint8_t  sfl, sfl_pad;        /* sfl: a paid C special's blue flash, frames left (fighter.c pal_overlay, gmeter.sflash) */
    /* throws (revamp phase 3, fighter.c "hold and throws"): sthr = the special playing is a throw (1: an extra throw,
     * BS_THROW; 2: the super throw, played as a fury) and xix its special's index (start_special takes it); thr_dmg = a
     * paired throw's whole damage on its victim (THROW_DAMAGE, the super throw's gmeter.sthrow_dmg); tb_by = the throw
     * special that caught this fighter: falling from it, it is a thrown body (spawn.body) until it lands */
    uint8_t  sthr, xix, thr_dmg, xwait;   /* xwait: a paired super throw's flash frames left in the hold (xix: its BT_*) */
    struct fighter *tb_by;
    /* the new system (Bruno 2026-10-08, docs/brawler_gold.md; fighter.c "the meter", "Blitz", "jumps"): sinv = the special
     * playing was bought with drive (a C special: untouchable to its end); brkr = the breaker was paid in life (it blinks red,
     * not white); blz_buf = a Blitz press during a normal (its slot + 1: fires when the normal lands, or as it ends); jt = the
     * jump table frame to play next + 1 (0: no table jump: gravity, a fall after a special); aact = active frames of the air
     * attack so far (gjump.active_min); wspd = its walk (16.16, gwalk_rom), wrate = its walk / run animation's rate (8.8:
     * wspd / its KOF walk, the feet don't slide) */
    uint8_t  sinv, brkr, blz_buf, jt, aact, jrun;   /* jrun: the jump started from a run (gjump.run_dx) */
    uint8_t  hcyc[2];             /* the hit cycles (fighter.c btn_sound, game.json hit_sounds): the next entry of the light / strong list */
    uint16_t wrate;
    int32_t  wspd;
    /* Bruno's 0.10.1 notes (2026-10-09): inb = it has fully entered the camera's view (fighter.c screen_keep: kept inside
     * from then on, note 20261009-114826-5d29); blz_slot = the Blitz playing (its slot BZ_*: gblitz_can, Terry's dd -> uu
     * cancel, note 20261009-114542-5d29); wdz = the walk's depth direction this frame (-1 / 0 / +1: the depth grab, note
     * 20261009-114751-5d29) */
    uint8_t  inb, blz_slot;
    int8_t   wdz, pad_n;
    /* a piercing object (bproj_t vhits, Krauser's MAX Kaiser Wave, 2026-10-09; fighter.c strike): vcnt = its hits landed
     * on each victim (2 bits per fighter_t.idx), vdone = the victims it is done with (bit per idx) */
    uint16_t vcnt;
    uint8_t  vdone, vpad;
    /* piece knobs (fighter.c "knobs"): kn = the special playing's rows (kn_n of them; 0: none), set at its start; a
     * projectile: kspd its speed (8.8, 0 = its rows as they are), khit its knobbed hit count (0: its data's) */
    const gknob_t *kn;
    uint8_t  kn_n, khit;
    uint16_t kspd;
} fighter_t;
enum { OVL_WHITE = 1, OVL_RED = 2, OVL_SHINY = 3, OVL_BLUE = 4 };   /* (OVL_SHINY: the fury ready's shiny white, fighter.c pal_overlay) */
uint8_t fighter_fury_ready(const fighter_t *f);   /* the hidden fury gauge is full (a player; the sprite's blink) */
uint8_t fighter_low(const fighter_t *f);   /* low life (gmeter.low): the life bar blinks red; with the gauge full: the MAX */
enum { RT_ON = 1, RT_FIRST = 2, RT_END = 4 };   /* rt_flags: retimed; a program's first frame (one source frame, not
                                   * counted); a segment ended this frame */
typedef struct { uint8_t fighter, nseg; uint16_t move; const uint16_t *t; } gretime_t;   /* a move's targets (build_tables.py
                                   * from game.json roster[].retime): fighter = bchar_t.id (0xFF ends the table), move = BA_*
                                   * or BA_COUNT + its special's index, t = nseg target frames (0 = the source's) */
extern const gretime_t gretime_rom[];   /* game_tables.c */
extern const gretime_t *rt_tab;   /* the table the moves read (0 = gretime_rom; a lab writes one in RAM and points here) */
uint8_t fighter_retime(fighter_t *f, const uint16_t *targets, uint8_t n);   /* the move playing (its start) given these
                                   * targets, one per segment (n = its segments, bm_seg); 0 = refused (no segments, wrong
                                   * n); targets 0 = back to the source's timing */
extern int16_t wall_lo, wall_hi;  /* the walls (vocabulary stage.wall): world x of the screen edges' walls this frame
                                     (WALL_EDGE px in; wall_update), PC_WALL's test */



#define BIGHIT_STOP 7              /* SS2's big hit (fighter.c big_hit): both held (the brawler's HITSTOP; SS2 40, TODO #195), */
#define BIGHIT_SLOW 0              /* then the game at half speed (SS2 30: none since TODO #195); the red backdrop from the */
#define BIGHIT_RED  8              /* hit (SS2 48: a short flash since TODO #195) */
#define BIGHIT_HOLD (BIGHIT_STOP + 21)   /* the victim: held in its hit pose until the slash throws it (SS2 [meas]: 76 frames
                                      after the hit = 40 stopped + 30 at half speed (15 ticks) + 6: 21 ticks of the slash) */
#define BIGHIT_COL  0x4F00         /* SS2 $2B9DE: (31, 0, 0) through its table $2BA16 */
extern uint8_t bighit_red, bighit_slow;   /* frames left of them (main.c screen_fx / game_tick) */
extern uint16_t bighit_col;               /* its backdrop colour (fighter.c big_hit) */
#define HITFLASH 10                /* Double Dragon's super hit strobe (fighter.c hit_spark, TODO #215): its frames from the */
extern uint8_t hitflash;           /* hit (main.c screen_fx: red 2, 3, 6, 7 frames after the spark shows, as DD's screen),
                                      frames left; BIGHIT_COL = DD's red */
#define PK_FX 6                    /* bproj_t kind: a source game's hit spark (vocabulary fx.hit_spark, TODO #215): no box, no
                                      shadow, its rows from the hit point (fighter.c hit_spark: x, height py0) */
extern uint16_t stat_grabs, stat_specials, stat_throws, stat_escapes;   /* by enemies (escapes: by players); HUD */
#define NPJ 8                     /* projectile entities: fighter_t too, so one renderer / sort / guard / hit test; 8 = a
                                     Blitz Ball and its 4 live trail objects (KOF96 measured) + 3 for other throwers */
#define PJ_COLS 10                /* the projectile pool's sprites per entity on average: NPJ * PJ_COLS shared by width (main.c block_w) */
extern fighter_t projectiles[NPJ];
void projectile_reset(fighter_t *p);
void projectiles_update(int16_t cam_x, uint16_t skip);   /* the independent projectiles' flight, after the fighters' update;
                                     skip: entities not updated, bit k = projectiles[k], bit 8 = in a super flash (the ones alive
                                     when it started, frozen; its attacker's effects born in it run, KOF98's priority $5001 objects) */
uint8_t projectiles_alive(void);          /* bit k: projectiles[k] is in use */

void fighter_init(fighter_t *f, const bchar_t *ch, uint8_t set, uint8_t palbase, uint8_t team, int16_t x, int16_t z);
void fighter_update(fighter_t *f, const intent_t *in);
void fighter_hit(fighter_t *atk, fighter_t *vic, uint8_t damage, uint8_t reaction, int8_t push);   /* attack connected */
void spark_hit(int16_t wx, int16_t sy, uint8_t big, int8_t facing);   /* main.c: KOF98 hit spark at world x, screen y */
void combat(fighter_t **fs, uint8_t n, const fighter_t *only);   /* attack boxes vs hurt boxes, every pair; only (not
                                                               0): that attacker's own boxes and pushes alone (the super
                                                               flash: its fury hits the frozen world, nothing else does) */
void fighter_tiles(fighter_t *f);                           /* pass 1: tile runs when the frame changed */
void fighter_place(const fighter_t *f, uint16_t *y, uint16_t *x, int16_t cam_x, uint8_t n);   /* pass 2: SCB3/SCB4 of n sprites (>= ncols; the rest height 0) */
void screen_keep(fighter_t **fs, uint8_t n, int16_t cam_x);   /* after the camera: a fighter that has fully entered the view
                                     stays inside it (note 20261009-114826-5d29; fighter.c "the screen's edges") */
void wall_update(fighter_t **fs, uint8_t n, int16_t cam_x);   /* after the camera: the wall rule (a special's victims and
                                                                  their attacker inside the screen's walls) */
void super_flash(fighter_t *f);      /* main.c: the fury's super flash starts (fx.super_flash: the game freezes except f) */
const char *fighter_state_name(uint8_t st);
const bstep_t *fighter_step(const fighter_t *f);
const bstep_t *fighter_hurt_step(const fighter_t *f);       /* the step whose hurt box counts (a ROM special's own step) */
void fighter_play(fighter_t *f, uint8_t anim);              /* outside the state machine (select screen previews) */
void fighter_animate(fighter_t *f);
void fighter_pose(fighter_t *f, uint8_t anim);             /* fighter_play / fighter_animate with the animation's voices */
void fighter_pose_tick(fighter_t *f);                       /* (main.c: the stage clear's win pose, TODO #184) */
void fighter_revive(fighter_t *f);
void fighter_respawn(fighter_t *f);  /* a life used: full life, dropping from above the screen where it is (TODO #166 e) */
void fighter_quake(const fighter_t *by, fighter_t *v);   /* the respawn's landing: v knocked down, away from by, no damage */
void throw_fx(int16_t wx, int16_t sy, int8_t facing);    /* main.c: the throw-start effect (fx.throw_start) at world x,
                                                            screen y (its anchor), mirrored for a thrower facing right */
/* a colour of f's palettes as shown: its tint applied (minions, main.c): 1 shade (half desaturated, 69 %), 2 ash (3/4
 * desaturated, 88 %, cold), 3 rust (half desaturated, 75 %, warm); never one of the playable colour sets */
uint16_t fighter_colour(const fighter_t *f, uint16_t c);
const uint8_t *fighter_dash(const fighter_t *f);   /* game_tables grun_dash: [start, frames, x..., height...] or 0 */
uint8_t fighter_pose_head(const fighter_t *f, int16_t *dx, int16_t *dy);   /* the flash pose step's head (TODO #191) */
const uint16_t *fighter_src_pal(const fighter_t *f, uint8_t i);   /* its palette i as defined (set, custom colours) */
#define FIGHTER_NAME(f) ((f)->name ? (f)->name : (f)->ch->name)
void fighter_load_pals(const fighter_t *f);                 /* its colour set through its tint into its hardware palettes */                          /* full life, getting up, invulnerable a moment */

#endif
