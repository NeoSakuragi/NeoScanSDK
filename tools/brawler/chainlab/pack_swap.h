/* The Character Lab's pack swap (docs/character_lab.md "The pack format"): a character pack (tools/brawler/lab_pack.py)
 * copied into the shell ROM a Geolith core has loaded. One C path for every front end: the Lab's wasm core
 * (web_core.c wc_swap_pack) and the Android Player (android/app/src/main/cpp/player.c Native.swapPack). */
#ifndef PACK_SWAP_H
#define PACK_SWAP_H
#include <stddef.h>
#include <stdint.h>

#define NGPK_FORMAT 1          /* the pack format this code reads (lab_pack.py FORMAT, examples/brawler/labslot.h) */

/* the loaded ROM region by number (0 P, 1 S, 2 M, 3 V1, 4 V2, 5 C) and its size, as the core keeps it: Geolith's
   retro_neoscan_rom (libretro.c) */
typedef uint8_t *(*ngpk_rom_fn)(int region, size_t *size);

enum { NGPK_OK = 0, NGPK_SHORT = -1, NGPK_MAGIC = -2, NGPK_VERSION = -3, NGPK_SIZES = -4, NGPK_BOUNDS = -5, NGPK_ODD = -6,
       NGPK_NOROM = -7, NGPK_OLD = -8, NGPK_SHELL = -9, NGPK_FORMATS = -10, NGPK_NEEDS = -11, NGPK_KIND = -12,
       NGPK_PLACE = -13 };

/* checks the whole pack first: its container, its format = the loaded shell's (the shell's anchor), its needs covered
   by the shell's features, every region a kind the shell's anchor has, the fixed ones at the shell's place, each inside
   the shell's room for it; then copies every region where the shell's anchor puts it (P word-swapped as Geolith keeps
   it); nothing is written unless all of it is good. The caller resets the system afterwards (retro_reset). */
int ngpk_apply(const uint8_t *pk, size_t n, ngpk_rom_fn rom);
/* the refusal in plain words (NGPK_NEEDS / NGPK_FORMATS: with what is missing, from the last ngpk_apply) */
const char *ngpk_error(int e);
#endif
