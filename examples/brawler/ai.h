/* Enemy AI: writes the same intent a joystick gives a player (fighter.h), so one state machine runs everybody. */
#ifndef AI_H
#define AI_H
#include "fighter.h"

void ai_init(uint16_t seed);
/* fs: all fighters, the first np are the players; in[i] receives fighter i's intent (enemies only) */
void ai_update(fighter_t *fs, uint8_t nf, uint8_t np, intent_t *in);

extern uint8_t ai_weak;                 /* attract mode: enemies rest longer and skip specials and grabs */
/* the attract-mode player: closes in on the nearest enemy, combos, grabs on contact (knees, then a throw), answers an
 * enemy attack in range with D (Terry: the invincible Rising Tackle) */
void ai_bot(fighter_t *fs, uint8_t nf, uint8_t p, intent_t *in);
#endif
