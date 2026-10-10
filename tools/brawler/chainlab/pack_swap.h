/* The Character Lab's pack swap (docs/feedback.md "Character Lab: shell and packs"): a character pack (tools/brawler/
 * lab_pack.py) copied into the shell ROM a Geolith core has loaded. One C path for every front end: the Lab's wasm core
 * (web_core.c wc_swap_pack) and the Android Player (android/app/src/main/cpp/player.c Native.swapPack). */
#ifndef PACK_SWAP_H
#define PACK_SWAP_H
#include <stddef.h>
#include <stdint.h>

/* the loaded ROM region by number (0 P, 1 S, 2 M, 3 V1, 4 V2, 5 C) and its size, as the core keeps it: Geolith's
   retro_neoscan_rom (libretro.c) */
typedef uint8_t *(*ngpk_rom_fn)(int region, size_t *size);

enum { NGPK_OK = 0, NGPK_SHORT = -1, NGPK_MAGIC = -2, NGPK_VERSION = -3, NGPK_SIZES = -4, NGPK_BOUNDS = -5, NGPK_ODD = -6,
       NGPK_NOROM = -7 };

/* checks the whole pack first (magic, version 1, the ROM sizes it was made for = the loaded ones, every region inside its
   ROM, P regions on whole words), then copies every region (P word-swapped as Geolith keeps it); nothing is written
   unless all of it is good. The caller resets the system afterwards (retro_reset): a swap restarts the practice. */
int ngpk_apply(const uint8_t *pk, size_t n, ngpk_rom_fn rom);
const char *ngpk_error(int e);
#endif
