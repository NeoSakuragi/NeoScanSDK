#include "neogeo.h"
#include <SDL2/SDL.h>

static SDL_GameController *pad;

void ng_input_init(void) {
    ng.p1 = ng.p2 = ng.sys = 0;
    pad = NULL;
    for (int i = 0; i < SDL_NumJoysticks(); i++) {
        if (SDL_IsGameController(i)) {
            pad = SDL_GameControllerOpen(i);
            if (pad) { printf("NG-EMU: Pad: %s\n", SDL_GameControllerName(pad)); break; }
        }
    }
}

void ng_input_poll(void) {
    const uint8_t *k = SDL_GetKeyboardState(NULL);
    uint8_t p1 = 0, sys = 0;

    if (k[SDL_SCANCODE_UP])    p1 |= 0x01;
    if (k[SDL_SCANCODE_DOWN])  p1 |= 0x02;
    if (k[SDL_SCANCODE_LEFT])  p1 |= 0x04;
    if (k[SDL_SCANCODE_RIGHT]) p1 |= 0x08;
    if (k[SDL_SCANCODE_Z])     p1 |= 0x10;   /* A */
    if (k[SDL_SCANCODE_X])     p1 |= 0x20;   /* B */
    if (k[SDL_SCANCODE_A])     p1 |= 0x40;   /* C */
    if (k[SDL_SCANCODE_S])     p1 |= 0x80;   /* D */
    if (k[SDL_SCANCODE_5])     sys |= 0x01;   /* Coin */
    if (k[SDL_SCANCODE_1])     sys |= 0x02;   /* Start */

    if (pad) {
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_DPAD_UP))    p1 |= 0x01;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_DPAD_DOWN))  p1 |= 0x02;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_DPAD_LEFT))  p1 |= 0x04;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_DPAD_RIGHT)) p1 |= 0x08;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_A))          p1 |= 0x10;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_B))          p1 |= 0x20;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_X))          p1 |= 0x40;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_Y))          p1 |= 0x80;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_START))      sys |= 0x02;
        if (SDL_GameControllerGetButton(pad, SDL_CONTROLLER_BUTTON_BACK))       sys |= 0x01;
    }

    ng.p1  = p1;
    ng.sys = sys;
}
