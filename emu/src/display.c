#include "neogeo.h"
#include <SDL2/SDL.h>
#include <stdio.h>

static SDL_Window   *win;
static SDL_Renderer *ren;
static SDL_Texture  *tex;

int ng_display_init(void) {
    win = SDL_CreateWindow("NG-EMU", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                           NG_SCREEN_W * 3, NG_SCREEN_H * 3,
                           SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE);
    if (!win) { fprintf(stderr, "SDL window: %s\n", SDL_GetError()); return -1; }

    ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);
    if (!ren) { fprintf(stderr, "SDL renderer: %s\n", SDL_GetError()); return -1; }

    SDL_RenderSetLogicalSize(ren, NG_SCREEN_W, NG_SCREEN_H);
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "nearest");

    tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
                            SDL_TEXTUREACCESS_STREAMING,
                            NG_SCREEN_W, NG_SCREEN_H);
    if (!tex) { fprintf(stderr, "SDL texture: %s\n", SDL_GetError()); return -1; }
    return 0;
}

void ng_display_present(void) {
    SDL_UpdateTexture(tex, NULL, ng.framebuf, NG_SCREEN_W * 4);
    SDL_RenderClear(ren);
    SDL_RenderCopy(ren, tex, NULL, NULL);
    SDL_RenderPresent(ren);
}

void ng_display_shutdown(void) {
    if (tex) SDL_DestroyTexture(tex);
    if (ren) SDL_DestroyRenderer(ren);
    if (win) SDL_DestroyWindow(win);
}
