/* The brawler's data layer (docs/brawler_data_model.md): the tables the game reads, generated from game.json by
 * tools/brawler/build_tables.py into build/game_tables.c / .h. The generator writes designated initialisers, so these
 * structs may change without touching it (a field it does not know stays 0).
 *
 * Live tables: gdata_init() (main.c) points the game at the ROM tables and copies the AI presets into RAM (ai_presets),
 * the same way route_tab points at the fighters' route trees: a lab can replace one by writing RAM. */
#ifndef GAMEDATA_H
#define GAMEDATA_H
#include <stdint.h>

/* ---- layer 2: AI presets (ai.c). Every distance is px, every rest frames, chances "1 in mask + 1" ---- */
enum { AIF_TOKEN = 1,             /* always holds an attack token (a boss), on top of the dealt ones */
       AIF_GRAB = 2,              /* an approach may end in a grab (grab_plan of 8) */
       AIF_PROJECTILE = 4,        /* fires its D special at mid range (spec_min-spec_max, 1 in proj_mask chance a frame) */
       AIF_REVERSAL = 8,          /* reaction to attacks: down+D (its rising reversal) against an attack (rev_*) */
       AIF_SPECIALS = 16,         /* D / forward+D (the rush) on the player's line (bspec_*) */
       AIF_JUMP_IN = 32,          /* forward jump-ins with an air B (jump_*) */
       AIF_FULL_SPEED = 64 };     /* walks at its full speed (the others walk at half speed while positioning) */
#define AIF_BOSS_MOVES (AIF_REVERSAL | AIF_SPECIALS | AIF_JUMP_IN)   /* game.json "boss_moves": the three, checked in this order */
typedef struct {
    uint8_t flags;
    uint8_t rest_shift, rest_random, rest_add;   /* a rest: (base >> rest_shift) + (random & rest_random) + rest_add */
    uint8_t rest_start, rest_attack, rest_special, rest_throw;   /* bases: at spawn, after a punch string, a D, a throw */
    uint8_t grab_plan;            /* approaches of 8 that walk in to grab */
    uint8_t attack_dx, hover_dx;  /* the token holder's distance to its player; the others' */
    uint8_t hover_go_dx, hover_go_dz;   /* a hoverer at its spot sets off again only when the spot is this far */
    uint8_t range_min, range_max, range_dz;   /* punches from range_min to range_max, on the depth line +- range_dz */
    uint8_t spec_min, spec_max, spec_dz;      /* the D projectile's range */
    uint8_t follow_mask;          /* follow-up A presses: random & follow_mask */
    uint8_t press_gap, hold_gap;  /* frames between presses in a string; between hits in a hold */
    uint8_t rev_dx, rev_dz, rev_mask, rest_rev;    /* boss: down+D against an attack this close, 1 in rev_mask + 1 */
    uint8_t bspec_min, bspec_max, bspec_dz, bspec_mask, rush_dx, rest_bspec;   /* boss: D / forward+D (closer than rush_dx: 1 in 2) */
    uint8_t jump_min, jump_max, jump_dz, jump_chance, rest_jump, air_b_dx;     /* boss: jump-in, jump_chance of 256; air B this close */
    uint8_t proj_mask, proj_mask2;    /* the projectile: (random & proj_mask) == 0 and (random & proj_mask2) == 0 in a frame
                                         (game.json proj_chance "1 in N a frame": 512 = 255 and 1) */
} ai_preset_t;

/* ---- the minion tints (fighter_colour): a colour pulled toward its luminance l = (5 R + 9 G + 2 B) / 16:
 * channel = ((l * mix + channel) * mul >> shift) + add[channel], clamped 0-31. Tint 0 = the colour set as it is. ---- */
typedef struct { uint8_t mix, mul, shift; int8_t add[3]; } gtint_t;

/* ---- layer 2: enemies. base = a roster fighter (bm_chars index) or 0xFF: one of the pool, picked per spawn ---- */
enum { GE_FIGHTER_NAME = 1 };     /* the HUD shows its fighter's name (today's minions and bosses), not the enemy's */
#define GE_SPAWN 0xFF             /* set / tint: the spawn's (gspawn_t) */
typedef struct {
    uint8_t base, ai, attract_ai; /* AI rows (ai_tab: the presets, then the enemies' own rows with their overrides merged);
                                     in the campaign; in the attract demo */
    uint8_t power;                /* extra damage a hit, on top of the stage's power */
    uint8_t npool;
    uint8_t set, tint;            /* its colour set (mod the fighter's sets) and gtint_t, GE_SPAWN = the spawn's */
    uint8_t flags;                /* GE_* */
    int16_t life;                 /* life at NORMAL difficulty (main.c life() scales it) */
    const uint8_t *pool;          /* base 0xFF: the fighters it may be (bm_chars indices), the players' fighters left out */
    const char *name;             /* shown in the HUD (unless GE_FIGHTER_NAME) */
    const uint16_t *pal;          /* 16 custom colours replacing its set's first palette (0 = the set's own) */
    const uint8_t *moves;         /* its route tree (fighter.h rt_head_t: a trimmed move list), 0 = its fighter's own */
} genemy_t;
_Static_assert(sizeof(genemy_t) == 26, "build_tables.py EN_SIZE");

/* ---- layer 3: stages ---- */
enum { SP_WALK_IN = 1,            /* x unused: walks in from off screen, rank (flags >> 4) * 36 px further out */
       SP_LEFT = 2,               /* walk in from the left when the camera has room (x >= 64), else the right */
       SP_NOT_BOSS = 4 };         /* a pool pick that is the stage boss's own fighter takes the next one */
typedef struct {
    uint8_t enemy, pick, set, tint;   /* genemy_t index; pool pick (mod the pool's size); colour set (mod its sets); gtint_t */
    int16_t x;                    /* world x when not SP_WALK_IN */
    uint8_t z, flags;
} gspawn_t;
typedef struct { int16_t lock; uint16_t seed; uint8_t first, n; } gwave_t;   /* camera lock x; AI random seed; spawns[first..+n) */
typedef struct {
    uint8_t bg, music, power, nwaves;  /* stages[] background (stage.h); driver command; enemies' extra damage */
    const gwave_t *waves;
    const gspawn_t *spawns;       /* the waves' spawns, then the boss's minions */
    uint8_t boss, boss_song;      /* genemy_t index; its theme */
    uint8_t unlock;               /* 1: beating the boss unlocks its fighter (roster_unlock) */
    uint8_t boss_z;
    int16_t boss_lock, boss_x;
    uint16_t boss_seed;
    uint8_t boss_first, nmin;     /* its minions: spawns[boss_first..+nmin) */
} gstage_t;

/* ---- layer 1: the select screen's group photo: slot places; sel_fighter[] = who stands there (0xFF: nobody) ---- */
typedef struct { int16_t x; uint8_t z, row; } sel_slot_t;

/* ---- a data pack (Brawler Lab write path, docs/brawler_data_model.md "Live install"): stages, enemies and AI rows in
 * one blob (version 2: + the fighters' specials by role) the page writes into lab.pack (fighter.h lab_t) with lab.load = 3. The structs as above, every pointer an
 * offset from the pack's start (0 = none); the game checks it (version, sizes, every offset and index), copies it into
 * its own RAM, turns the offsets into pointers and repoints gstages / genemies / ai_tab at the next safe point (a wave,
 * the boss, a stage start, the lab's enemy respawn). lab.load = 4: back to the ROM's tables (at the same point). ---- */
#define GD_VERSION 2              /* 2 (2026-10-05): + the roster section; version 1 packs are still read (no roster section) */
#define GD_MAX     4096           /* bytes, header included */
typedef struct {
    char     magic[2];            /* "GD" */
    uint8_t  version;             /* GD_VERSION */
    uint8_t  nstages, nenemies, nai;   /* nstages = GS_COUNT (the save's bits follow the stages) */
    uint16_t size;                /* bytes, this header included */
    uint16_t stages, enemies, ai; /* offsets of gstage_t[nstages], genemy_t[nenemies], ai_preset_t[nai] */
    uint16_t nspawns;             /* spawns per stage at most (bounds checks) */
    uint16_t roster;              /* version 2: offset of the roster section (0 = none; version 1: padding, ignored): per
                                   * fighter (BC_COUNT, bm_chars order) 4 bytes, the special each role plays (D, forward+D,
                                   * down+D, up+D: an index in its bchar_t.specials, 0xFF = none): fighter.c spec_tab */
} gdpack_t;
_Static_assert(sizeof(gdpack_t) == 18, "build_tables.py PACK_HEAD");
enum { GD_NONE, GD_PENDING, GD_INSTALLED, GD_ROM,            /* lab.pack_stat (game): waiting for the safe point; in use */
       GD_BAD = 0x80 };           /* | the check that failed (main.c gd_check) */

/* ---- the live tables (main.c) ---- */
extern const gstage_t *gstages;
extern const genemy_t *genemies;
extern ai_preset_t ai_presets[];  /* the ROM's AI rows in RAM (a lab may poke them) */
extern const ai_preset_t *ai_tab; /* the rows the AI reads: ai_presets, or an installed pack's */
#endif
