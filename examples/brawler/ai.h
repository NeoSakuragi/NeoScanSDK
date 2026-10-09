/* Enemy AI: writes the same intent a joystick gives a player (fighter.h), so one state machine runs everybody. */
#ifndef AI_H
#define AI_H
#include "fighter.h"

/* every enemy slot gets AI preset `preset` (gamedata.h, game.json "ai"; AI_* in game_tables.h) and rests its rest_start;
 * the tokens of the slots are given back (a new wave) */
void ai_init(uint16_t seed, uint8_t preset);
/* fs: all fighters, the first np are the players; in[i] receives fighter i's intent (enemies only) */
void ai_update(fighter_t *fs, uint8_t nf, uint8_t np, intent_t *in);

/* fighter i plays preset `preset` from now (a rest of its rest_start). The boss preset (campaign): its attack token is
 * kept free for it (the minions share the others) and it rests a quarter as long; when ready, 20-160 px away on the
 * player's line, 1 time in 4 it fires a special (D, or forward+D: the rush), else 1 in 4 it jumps in (a forward regular
 * jump, air B on the way down), else it closes in and punches like the others; a player attack within 56 px is answered
 * 1 time in 4 by down+D (its rising reversal). */
void ai_set(uint8_t i, uint8_t preset);
/* the attract-mode player: closes in on the nearest enemy, combos, grabs on contact (knees, then a throw), answers an
 * enemy attack in range with D (Terry: the invincible Rising Tackle) */
void ai_bot(fighter_t *fs, uint8_t nf, uint8_t p, intent_t *in);

/* the hidden difficulty rank (revamp 1B, gamedata.h gairules_t; 0-31): set to rank_start by a new game (main.c
 * stage_begin), up while the players do well, down when one loses a life; shown only in the Brawler Lab's readout */
extern uint8_t ai_rank;
extern uint8_t ai_tokens;         /* attack tokens held this frame (<= gai.attackers): the Lab's readout, the proofs */
extern uint8_t ai_wlog[16][4], ai_wlog_n;   /* the last wind-ups given (ai.c windup_hold): the proofs */
#if LAB_BUILD
extern uint8_t ai_skip;           /* practice mode (main.c): bit i = fighter i is driven by the practice code, not the AI (no
                                     target, never holds an attack token) */
#endif
void ai_rank_reset(void);
uint8_t ai_rank_power(void);      /* extra damage a hit for an enemy spawned now (main.c enemy_init): rank / rank_dmg */
#endif
