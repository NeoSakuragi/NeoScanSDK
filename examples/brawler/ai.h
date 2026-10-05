/* Enemy AI: writes the same intent a joystick gives a player (fighter.h), so one state machine runs everybody. */
#ifndef AI_H
#define AI_H
#include "fighter.h"

/* every enemy slot gets AI preset `preset` (gamedata.h, game.json "ai"; AI_* in game_tables.h) and rests its rest_start */
void ai_init(uint16_t seed, uint8_t preset);
/* fs: all fighters, the first np are the players; in[i] receives fighter i's intent (enemies only) */
void ai_update(fighter_t *fs, uint8_t nf, uint8_t np, intent_t *in);

/* fighter i plays preset `preset` from now (a rest of its rest_start). The boss preset (campaign): always holds an attack
 * token besides the minions' one and rests a quarter as long; when ready, 20-160 px away on the player's line, 1 time in
 * 4 it fires a special (D, or forward+D: the rush), else 1 in 4 it jumps in (a forward regular jump, air B on the way
 * down), else it closes in and punches like the others; a player attack within 56 px is answered 1 time in 4 by down+D
 * (its rising reversal). Measured over 900 frames per boss (campaign proof): 3-8 specials, 1-5 jumps, 5-12 punch strings. */
void ai_set(uint8_t i, uint8_t preset);
/* the attract-mode player: closes in on the nearest enemy, combos, grabs on contact (knees, then a throw), answers an
 * enemy attack in range with D (Terry: the invincible Rising Tackle) */
void ai_bot(fighter_t *fs, uint8_t nf, uint8_t p, intent_t *in);
#endif
