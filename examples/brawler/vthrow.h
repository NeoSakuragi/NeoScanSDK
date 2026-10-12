/* The victim's own side of a paired throw (docs/throws_audit.md section 4, "throws part 1"): KOF keeps one throw list
 * per victim fighter (its +$C2 = table + victim id x size), because each fighter's frame for a posture sits differently
 * around its origin. tools/brawler/export_bm.py victim_tables writes, for every thrower x victim pair of the same game the
 * roster can meet (export96 victims_all: the source's own list for that victim; KOF98 Terry / Ralf x, KOF96 Geese: their
 * code walked for that victim, throwrom.build), the victim's rows against the thrower's script (bthrow_t rows: the
 * mirror match): per row its posture and what to add to the row's offsets. A victim of another game (SS2, DD, Kizuna,
 * WHP or another KOF) has no source rows: the fallback is its posture anchor (bm_vanch: the centre of its frame for each
 * posture, px from the feet, ROM orientation) against the thrower's own (the mirror victim's), the offset moved so the two
 * frames' centres meet. Kept out of bm_chars.h (the pack format's ABI): read by fighter.c vrow only. ---- */
#ifndef VTHROW_H
#define VTHROW_H
#include <stdint.h>
typedef struct { uint8_t vpose, flags; int8_t dx, dy; } bvrow_t;   /* vpose: the victim's posture (VP_*; 0xFE = the script
                                                                    row's own), flags bit 0: it faces the thrower's way, dx /
                                                                    dy: px added to the row's vx / vy */
typedef struct { uint8_t victim, pad; uint16_t n; const bvrow_t *rows; } bvthr_t;   /* victim: bchar_t.id; n rows (the
                                                                    script's later rows: its last); victim 0xFE: the
                                                                    anchors' source side, per row the centre of the
                                                                    frame the source showed (dx, dy; -128 none), what
                                                                    another game's victim is placed against; 0xFF ends */
extern const bvthr_t *const bm_vthr[][3];        /* by bchar_t.id: its throws C, D and its extra paired throw (BT_XTHROW) */
extern const int8_t *const bm_vanch[];           /* by bchar_t.id: VP_COUNT x [x, y] its posture frames' centres (0: none) */
#endif
