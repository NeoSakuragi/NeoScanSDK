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
typedef struct { uint8_t thrower, k; uint16_t n; const bvrow_t *rows; } bvcol_t;   /* the Lab slot as a victim: thrower
                                                                    (its pack build's id), throw k (as bm_vthr's), n rows
                                                                    (the thrower's script's count when built: another
                                                                    count = its script changed, the script's rows);
                                                                    0xFF ends */
typedef struct { uint32_t magic; uint8_t nkey, pad[3]; const uint32_t *keys; const bvthr_t *row[3]; const bvcol_t *col; } bvslot_t;
/* ---- the Character Lab's slot (LAB_SHELL builds; docs/character_lab.md "The pack format"): the shell's bm_vthr has no
 * entry for the slot, as a thrower or a victim, so nothing outside the slot depends on who fills it; the slot's own
 * rows are its pack's (export_bm.py slot_tables: slot_vthr in .labslot, its header's word at +12 points to it, 0 = none:
 * the script's rows). magic 'VSLT'; row[k]: its throw k's victims (bvthr_t, victim = the pack build's id), col: its
 * throwers; keys[nkey]: the pack build's fighters by id, their bm_rkey (0: the slot), which lab_slot_init resolves to
 * this shell's ids (lab_vmap). ---- */
extern const bvthr_t *const bm_vthr[][3];        /* by bchar_t.id: its throws C, D and its extra paired throw (BT_XTHROW) */
extern const int8_t *const bm_vanch[];           /* by bchar_t.id: VP_COUNT x [x, y] its posture frames' centres (0: none) */
#ifdef LAB_SHELL
#define VSLOT_MAGIC 0x56534C54UL                 /* 'VSLT' (export_bm.py) */
extern const uint32_t bm_rkey[];                 /* by bchar_t.id: its bank spec's CRC-32 (export_bm.py rkey; 0: the slot) */
#endif
#endif
