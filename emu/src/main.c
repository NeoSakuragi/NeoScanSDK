#include "neogeo.h"
#include <SDL2/SDL.h>
#include <stdio.h>
#include <string.h>

#define DEFAULT_BIOS "/home/bruno/roms/neogeo/neogeo.zip"

int main(int argc, char **argv) {
    const char *rom  = NULL;
    const char *bios = DEFAULT_BIOS;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--bios") && i+1 < argc) bios = argv[++i];
        else if (argv[i][0] != '-') rom = argv[i];
    }
    if (!rom) { fprintf(stderr, "Usage: ngemu [--bios neogeo.zip] game.neo\n"); return 1; }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER) < 0) {
        fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 1;
    }

    ng_init();
    if (ng_load_bios(bios) < 0) { SDL_Quit(); return 1; }
    if (ng_load_neo(rom) < 0)   { ng_shutdown(); SDL_Quit(); return 1; }
    if (ng_display_init() < 0)  { ng_shutdown(); SDL_Quit(); return 1; }
    ng_input_init();
    ng_reset();

    while (ng.running) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) ng.running = false;
            if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_ESCAPE) ng.running = false;
        }
        ng_input_poll();
        ng_frame();
        ng_display_present();
    }

    ng_display_shutdown();
    ng_shutdown();
    SDL_Quit();
    return 0;
}
