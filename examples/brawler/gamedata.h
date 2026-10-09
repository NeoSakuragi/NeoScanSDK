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
enum { AIF_TOKEN = 1,             /* a boss: one of the gai.attackers tokens is kept free for it, it takes it when rested */
       AIF_GRAB = 2,              /* an approach may end in a grab (grab_plan of 8) */
       AIF_PROJECTILE = 4,        /* fires its D special at mid range (spec_min-spec_max, 1 in proj_mask chance a frame) */
       AIF_REVERSAL = 8,          /* reaction to attacks: down+D (its rising reversal) against an attack (rev_*) */
       AIF_SPECIALS = 16,         /* D / forward+D (the rush) on the player's line (bspec_*) */
       AIF_JUMP_IN = 32,          /* forward jump-ins with an air B (jump_*): any enemy, as the token's attack */
       AIF_FULL_SPEED = 64,       /* walks at its full speed (the others walk at half speed while positioning) */
       AIF_AIR_CD = 128 };        /* the jump-in's air attack is C+D (else B) */
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
    uint8_t jump_min, jump_max, jump_dz, jump_chance, rest_jump, air_b_dx;     /* jump-in (any enemy), jump_chance of 256; air B this close */
    uint8_t hop_dx, hop_chance;   /* jump_in: resting closer than hop_dx, a back-hop (hop_chance of 256 a frame, 0 = never) */
    uint8_t proj_mask, proj_mask2;    /* the projectile: (random & proj_mask) == 0 and (random & proj_mask2) == 0 in a frame
                                         (game.json proj_chance "1 in N a frame": 512 = 255 and 1) */
} ai_preset_t;

/* ---- layer 2: the enemies' shared rules (revamp 1B, docs/brawler_data_model.md "Enemy rules"; game.json ai.rules, ROM
 * only, ai.c): attack tokens, the ready pose and its random wait, wind-up by damage, the hidden difficulty rank ---- */
typedef struct {
    uint8_t attackers;            /* at most this many enemies hold an attack token (approach, ready, attack) at once */
    uint8_t approach_max;         /* frames a token holder may take to reach its range; then it gives the token back */
    uint8_t pulse;                /* the ready pose's tint pulse (a fighter with no stance frame): a white flash every pulse frames */
    uint8_t ready_anim2, ready_step2;   /* the stance frame when the fighter's own (ai_ready) has no such step: BA_*, step */
    uint8_t light_lo, light_hi;   /* wind-up targets (frames from the attack's first frame to its first live frame) */
    uint8_t heavy_lo, heavy_hi, heavy_from;   /* a normal of route damage >= heavy_from is heavy */
    uint8_t spec_lo, spec_hi;     /* a special's hold (its first frame held this long on top of its own startup) */
    uint8_t rank_start, rank_max; /* the rank at a new game; its ceiling (0-31) */
    uint8_t rank_death;           /* rank lost when a player loses a life */
    uint8_t rank_fast, rank_clean;   /* rank gained by a wave cleared in under fast_clear frames; by one cleared untouched */
    uint8_t rank_wait, rank_rest; /* aggression: the ready wait and the rests shrink by rank * k / 1024 (k 16: rank 31 = x0.52) */
    uint8_t rank_dmg;             /* damage: a spawned enemy hits rank / rank_dmg harder (0 = never) */
    uint16_t rank_every;          /* rank + 1 every this many frames of fighting without a hit taken */
    uint16_t fast_clear;
    uint8_t wait[32];             /* the ready wait (frames), random & 31 picks one: Final Fight's table $2245E */
} gairules_t;
extern const gairules_t gai;      /* (game_tables.h: ai_ready[BC_COUNT][2], each fighter's ready stance: BA_*, step; 0xFF the tint pulse) */

/* ---- layer 2: the two bars (Bruno's live redesign 2026-10-08, docs/brawler_gold.md; fighter.c "the meter"): game.json
 * "meter"; players only. DRIVE (shown: the HUD's chunks): chunks x chunk points, one back a frame; a C special costs
 * `special` chunks (short: it does not come out), the breaker (C / A+B while hit: the neutral C special) `breaker` chunks,
 * short of them life_breaker life (never the last point). The FURY GAUGE (hidden): fury_max points, filled fury_dealt a
 * point of damage dealt, fury_taken a point taken; full: D = the fury, full + low life (<= low % of the full life): the MAX ---- */
typedef struct {
    uint16_t chunk;               /* drive points a chunk (= frames to refill one) */
    uint8_t  chunks;              /* chunks in the bar (full at the start and at a new life) */
    uint8_t  special, breaker;    /* chunks a C special / a breaker costs */
    uint8_t  life_breaker;        /* life a breaker costs short of the chunks (never the last point) */
    uint8_t  blink;               /* the breaker's blink: frames white (red when paid in life), then as many in its colours */
    uint8_t  infinite;            /* 1: nothing is spent, both bars full (a test switch) */
    uint16_t fury_max;            /* the hidden fury gauge: full */
    uint8_t  fury_dealt, fury_taken;   /* gauge points a life point dealt / taken */
    uint8_t  low;                 /* low life: life <= low % of the full life (and > 0): the life bar blinks red, the MAX */
    uint8_t  fury_drive, max_drive;   /* drive chunks the fury / the MAX also cost (Bruno 2026-10-09: 1 / 2) */
} gmeter_t;
extern const gmeter_t gmeter;

/* ---- layer 2: the Blitz and the A+B chord (Bruno 2026-10-08; game.json "blitz"; main.c read_player, fighter.c "Blitz"):
 * window = frames allowed between the two taps of a double direction and from the second tap to A; chord = frames the
 * second of A / B may come after the first and still make C; scale = a special played as a Blitz: its damage (8.8 of its
 * special tier). gblitz_rom[fighter] (game_tables.c): its four slots BZ_FF .. BZ_UU = a special's pool index, BZ_DASH its
 * tree's dash entry, BZ_NONE ---- */
typedef struct { uint8_t window, chord; uint16_t scale; } gblitz_t;
extern const gblitz_t gblitz;
enum { BZ_FF, BZ_DD, BZ_DU, BZ_UU, BZ_COUNT };
#define BZ_DASH 0xFE
#define BZ_NONE 0xFF

/* ---- layer 2: the one jump (Bruno 2026-10-08: Cody's Final Fight arc; game.json "jump"; fighter.c "jumps"): crouch
 * frames on the ground, then n air frames at h[i] lines above the floor, a forward jump travelling dx[i] (8.8 Neo Geo px)
 * a frame and land_dx on the landing; the rise animation turns into the fall at apex; the landing lasts `land` frames, any
 * input ends it from land_cancel on. Air attacks: the jump attack (forward / straight + A) active active_min frames at
 * least, down + A active to the landing, down + A -> the jump attack on hit (down_any 1: at any time) ---- */
typedef struct {
    uint8_t  crouch, n, apex, land, land_cancel, active_min, down_any, jpad;
    uint16_t land_dx, run_dx;    /* run_dx: a jump out of a run travels x this (8.8) forward (Bruno 2026-10-08) */
    const uint8_t *h;
    const uint16_t *dx;
} gjump_t;
extern const gjump_t gjump;

/* ---- the chain core (revamp 1A, docs/brawler_feel.md 8h; game.json "chain"; fighter.c "chain core"): engine rules for
 * every fighter. window: frames after a link's recovery to press the next one (the chain advances only on hit; a whiff or
 * being hit restarts it); buffer: a player's press made this many frames (hit-stop not counted) before the next link may
 * start still fires (AI presses: kept whatever their age); juggle_cap: air hits a juggled fighter takes, then nothing
 * reaches it until it lands (a fury's excepted); stun_player / guard_player: a player's hit stun and its untouchable
 * window from the hit (only the attacker that hit it reaches it meanwhile); stun_light / stun_heavy: an enemy's. The
 * archetypes' lengths, damage totals and the hit-stop scale are build-time (routes.py chain_tree writes them into the
 * trees). ---- */
typedef struct {
    uint8_t window, buffer, juggle_cap;
    uint8_t stun_player, guard_player, stun_light, stun_heavy, pad;
} gchain_t;
extern const gchain_t gchain;

/* ---- layer 2: the super flash (fx.super_flash, TODO #139; game.json "super_flash"): an engine rule, every fury (D) and
 * MAX fury (down+D) of every fighter: from the fury's frame `start` the game freezes except the attacker for `freeze`
 * frames, the stage is hidden, the backdrop `white_col` for `white` frames then `dark_col`; the concentration (the
 * effects library, superflash.h: KOF98's) plays at the anchor, blue for a fury, orange for a MAX fury. The anchor: the
 * special's bspec_t.sf_dx / sf_dy when it has one (sf_anchor), else dx / dy here (px from the feet, KOF orientation). */
typedef struct {
    uint8_t  start, freeze, white, sound;   /* sound: the effect code ($1A prefix) played at the start: KOF98's charge */
    uint8_t  sound_max;                     /* the MAX fury's instead (TODO #155: KOF2000's SDM flash whistle) */
    int16_t  dx, dy;
    uint16_t white_col, dark_col;
} gflash_t;
extern const gflash_t gflash;

/* ---- layer 2: the hit sounds (game.json "hit_sounds", Bruno's impact-sound picks 2026-10-09): cycle[0] / [1] the light /
 * strong hit cycles (n entries each, $1A codes: every A / B hit plays the attacker's next light entry, every C / D hit
 * its next strong one, unless the fighter's own sound is set: fighter.c btn_sound); guard: the guard sound
 * (fighter_guard_sound, no guard yet); boss_ko: the boss's killing hit, its death voice scream_delay frames later
 * (main.c boss_ko_start) ---- */
typedef struct {
    uint8_t n[2], guard, boss_ko;
    uint16_t scream_delay;
    const uint8_t *cycle[2];
} ghitsnd_t;
extern const ghitsnd_t ghitsnd;

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

/* ---- layer 3: triggers (a stage's `triggers`, game.json; main.c triggers()): when -> do, each once per stage ---- */
enum { TW_CAMERA = 1,             /* at: the camera's x reached it */
       TW_WAVE_CLEAR,             /* wave: that wave beaten (nwaves = the boss) */
       TW_TIME };                 /* at: ticks since the stage start (wave TW_STAGE) or since wave `wave` came (nwaves = the boss) */
#define TW_STAGE 0xFF
enum { TA_SPAWN = 1,              /* n enemies like sp (pick + k, z + 11 k), one every `delay` ticks, into free slots */
       TA_LOCK,                   /* arg: the camera stops at x = arg until every enemy on screen is beaten */
       TA_MUSIC,                  /* arg: a driver command (MUS_*) */
       TA_DRAMA,                  /* arg: a drama scene (gdramas index) */
       TA_END };                  /* the stage is cleared (its enemies go down) */
typedef struct {
    uint8_t when, wave;           /* TW_*; the wave for TW_WAVE_CLEAR / TW_TIME */
    int16_t at;                   /* camera x or ticks */
    uint8_t action, n;            /* TA_*; TA_SPAWN: how many */
    uint16_t arg, delay;          /* the action's argument; TA_SPAWN: ticks between two */
    gspawn_t sp;                  /* TA_SPAWN: the first one (walk-in side in its flags) */
} gtrigger_t;
typedef struct {                  /* per stage, beside gstage_t (whose layout old packs keep) */
    const gtrigger_t *trig;
    uint8_t ntrig;                /* at most 32 */
    uint8_t drama;                /* played as the boss walks in, before its song (0xFF: none) */
    uint16_t pad;
} gstagex_t;

/* ---- drama mode (main.c drama_*): letterbox bars, the action held, a big portrait (portraits_big.h) and text ---- */
#define DR_LINES 3                /* text lines a scene */
#define DR_COLS  34               /* characters a line (fix columns 3-36) */
typedef struct {                  /* a player's lines when it is that fighter (game.json lines_by) */
    uint8_t fighter, nlines, pad[2];   /* bm_chars index */
    const char *line[DR_LINES];
} gsceneby_t;
enum { DW_FIXED, DW_P1, DW_P2 };  /* gscene_t.who: the speaker as written; "$P1" / "$P2": whoever plays (P1: the one in play) */
typedef struct {
    uint8_t portrait, side, nlines, who;   /* PB_* (0xFF none; DW_P*: the player's own, pb_of_fighter); 0 left (mirrored), 1 right */
    uint16_t wait;                /* ticks the scene stays once its text is out (then the next; a button skips) */
    uint8_t nby, pad;             /* by[]: per-fighter lines (DW_P*), else line[] */
    const char *speaker;          /* the name plate (DW_P*: the fighter's name) */
    const char *line[DR_LINES];
    const gsceneby_t *by;
} gscene_t;
typedef struct { uint8_t n, pad; uint16_t pad2; const gscene_t *scene; } gdrama_t;

/* ---- layer 1: the select screen's group photo (game.json select_layout, the Brawler Lab's Select screen tab): one slot
 * per selectable fighter, in the layout's slot order (the cursor starts on the first; the stick: sel_stick / sel_vert,
 * the cursor graph build_tables.py computes from the places); x, y = its feet on the screen (px), z = its draw order
 * (0 the back), face = 1 facing right, -1 left; sel_fighter[] = who stands there ---- */
typedef struct { int16_t x, y; uint8_t z; int8_t face; } sel_slot_t;

/* ---- a data pack (Brawler Lab write path, docs/brawler_data_model.md "Live install"): stages, enemies and AI rows in
 * one blob (version 2: + the fighters' specials by role) the page writes into lab.pack (fighter.h lab_t) with lab.load = 3. The structs as above, every pointer an
 * offset from the pack's start (0 = none); the game checks it (version, sizes, every offset and index), copies it into
 * its own RAM, turns the offsets into pointers and repoints gstages / genemies / ai_tab at the next safe point (a wave,
 * the boss, a stage start, the lab's enemy respawn). lab.load = 4: back to the ROM's tables (at the same point). ---- */
#define GD_VERSION 7              /* 2 (2026-10-05): + the roster section; 3: + its voices part; 4: + the stages' triggers
                                     (header 20 bytes); 5: AI rows + hop_dx, hop_chance (42 bytes); 6: the roster section
                                     6 bytes per fighter (+ down-forward+D, up-forward+D), route trees version 3; 7 (TODO
                                     #71): route trees version 4 (one attack button). Only version 7 loads. */
#define GD_ROLES(v) ((v) >= 6 ? BS_COUNT : 4)   /* roster section bytes per fighter */
#define GD_MAX     4096           /* bytes, header included */
typedef struct {
    char     magic[2];            /* "GD" */
    uint8_t  version;             /* GD_VERSION */
    uint8_t  nstages, nenemies, nai;   /* nstages = GS_COUNT (the save's bits follow the stages) */
    uint16_t size;                /* bytes, this header included */
    uint16_t stages, enemies, ai; /* offsets of gstage_t[nstages], genemy_t[nenemies], ai_preset_t[nai] */
    uint16_t nspawns;             /* spawns per stage at most (bounds checks) */
    uint16_t roster;              /* version 2: offset of the roster section (0 = none; version 1: padding, ignored): per
                                   * fighter (BC_COUNT, bm_chars order) GD_ROLES bytes, the special each role plays (D,
                                   * forward+D, down+D, up+D, version 6: down-forward+D, up-forward+D: an index in its
                                   * bchar_t.specials, 0xFF = none): fighter.c spec_tab;
                                   * version 3: then per fighter a big-endian uint16, the offset of its voice table
                                   * (VK_SPEC + nspec entries of [voice id, at], fighter.c voice_tab; 0 = the ROM's) */
    uint16_t stagex;              /* version 4: offset of gstagex_t[nstages] (their triggers inside the pack); older
                                   * packs end their header before this field */
} gdpack_t;
_Static_assert(sizeof(gdpack_t) == 20, "build_tables.py PACK_HEAD");
_Static_assert(sizeof(gtrigger_t) == 18 && sizeof(gstagex_t) == 8 && sizeof(gscene_t) == 28 && sizeof(gsceneby_t) == 16, "build_tables.py TRIG_SIZE / SX_SIZE");
enum { GD_NONE, GD_PENDING, GD_INSTALLED, GD_ROM,            /* lab.pack_stat (game): waiting for the safe point; in use */
       GD_BAD = 0x80 };           /* | the check that failed (main.c gd_check) */

/* ---- the live tables (main.c) ---- */
extern const gstage_t *gstages;
extern const genemy_t *genemies;
extern const gstagex_t *gstagex;  /* the stages' triggers and boss scenes: the ROM's, or an installed pack's (version 4) */
extern ai_preset_t ai_presets[];  /* the ROM's AI rows in RAM (a lab may poke them) */
extern const ai_preset_t *ai_tab; /* the rows the AI reads: ai_presets, or an installed pack's */
#endif
