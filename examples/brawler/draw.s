| Fighter rendering hot paths in 68000 assembly (measured: these two were 60 % of the frame in C).
| Same contracts as the prototypes in fighter.h; the C structure offsets used here are pinned by _Static_assert in fighter.c (the build stops when fighter.h or bm_chars.h moves a field); was claimed before 2026-10-03 but missing, and an added field shifted ncols (glitched sprites) -
| fighter.c (change a structure and the build stops there).
|
| fighter_tiles(f): when the shown frame or the facing changed, one SCB1 run per sprite column: rows x {tile, attribute}.
|   Queue space is reserved once per part; rows are copied by a computed jump into an unrolled block (20 cycles a row).
| fighter_place(f, y, x, cam_x, n): SCB3/SCB4 words of n sprites (n >= ncols) into the caller's runs. Each part is a
|   sticky chain: the first column has Y, height and X, the others only the sticky bit; columns past the frame get height 0.
|   fighter_tiles stores the frame's column count in ncols, so the caller sizes the runs (and the line guard counts) without
|   looking the frame up again.

    .equ    MAX_COLS, 20
    .equ    FLOOR_TOP, 150
    .equ    CMD_BUF_SIZE, 4096
    .equ    STICKY, 0x40
    | fighter_t
    .equ    F_CH, 0
    .equ    F_PALBASE, 5
    .equ    F_SPR, 6
    .equ    F_X, 8
    .equ    F_Z, 12
    .equ    F_Y, 16
    .equ    F_FACING, 32
    .equ    F_ANIM, 38
    .equ    F_STEP, 39
    .equ    F_SHOWN_FRAME, 56
    .equ    F_SHOWN_FACING, 58
    .equ    F_FRAME_OVR, 60
    .equ    F_NCOLS, 94
    | bchar_t / banim_t (6 bytes) / bstep_t (14) / bframe_t (6) / bpart_t (14)
    .equ    CH_FRAMES, 10
    .equ    CH_ANIMS, 14
    .equ    CH_TILE_HI, 46
    .equ    AN_STEPS, 2
    .equ    FR_NPARTS, 0
    .equ    FR_PARTS, 2
    .equ    PT_DX, 0
    .equ    PT_DY, 2
    .equ    PT_COLS, 4
    .equ    PT_ROWS, 5
    .equ    PT_HFLIP, 6
    .equ    PT_VFLIP, 7
    .equ    PT_PAL, 8
    .equ    PT_TILES, 10
    .equ    PT_SIZE, 14

| frame lookup: a2 = fighter -> d0.l = frame index, a0 = ch (clobbers a1, d1). frame_ovr (holds, throw scripts) wins.
    .macro  CURRENT_FRAME
    movea.l F_CH(%a2), %a0
    moveq   #0, %d0
    move.w  F_FRAME_OVR(%a2), %d0
    cmp.w   #0xFFFF, %d0
    bne.s   .Lcf_done\@
    movea.l CH_ANIMS(%a0), %a1
    moveq   #0, %d0
    move.b  F_ANIM(%a2), %d0
    add.w   %d0, %d0
    move.w  %d0, %d1
    add.w   %d0, %d0
    add.w   %d1, %d0                | anim * 6
    movea.l AN_STEPS(%a1,%d0.w), %a1
    moveq   #0, %d0
    move.b  F_STEP(%a2), %d0
    add.w   %d0, %d0
    move.w  %d0, %d1
    lsl.w   #3, %d0
    sub.w   %d1, %d0                | step * 14
    move.w  (%a1,%d0.w), %d0        | bstep_t.frame (offset 0); upper word of d0 is 0
.Lcf_done\@:
    .endm

| a2 = fighter, d0.l = frame index -> a3 = first part, d2 = nparts (clobbers a1, d0, d1)
    .macro  FRAME_PARTS
    movea.l CH_FRAMES(%a0), %a1
    add.l   %d0, %d0
    move.l  %d0, %d1
    add.l   %d0, %d0
    add.l   %d1, %d0                | frame * 6
    adda.l  %d0, %a1
    moveq   #0, %d2
    move.b  FR_NPARTS(%a1), %d2
    movea.l FR_PARTS(%a1), %a3
    .endm

    .text
    .even
    .global fighter_tiles
| d1 columns left in the block, d2 parts left, d3 sprite id, d4 attribute, d5 rows, d6 column step (bytes, signed),
| d7 columns of this part, a3 part, a4 queue, a5 tile column
fighter_tiles:
    movem.l %d2-%d7/%a2-%a5, -(%sp)
    movea.l 44(%sp), %a2
    CURRENT_FRAME
    cmp.w   F_SHOWN_FRAME(%a2), %d0
    bne.s   1f
    move.b  F_FACING(%a2), %d1
    cmp.b   F_SHOWN_FACING(%a2), %d1
    beq     .Lt_ret
1:  move.w  %d0, F_SHOWN_FRAME(%a2)
    move.b  F_FACING(%a2), F_SHOWN_FACING(%a2)
    FRAME_PARTS
    moveq   #0, %d0                 | tile number bits 16-19 -> attribute bits 4-7, kept on the stack for every part
    move.b  CH_TILE_HI(%a0), %d0
    lsl.w   #4, %d0
    move.w  %d0, -(%sp)
    move.w  F_SPR(%a2), %d3
    moveq   #MAX_COLS, %d1
    subq.w  #1, %d2
    bmi     .Lt_done

.Lt_part:
    moveq   #0, %d7
    move.b  PT_COLS(%a3), %d7
    cmp.w   %d1, %d7                | clip to the block
    bls.s   1f
    move.w  %d1, %d7
1:  tst.w   %d7
    beq     .Lt_done
    sub.w   %d7, %d1
    moveq   #0, %d5
    move.b  PT_ROWS(%a3), %d5
    | attribute: (palbase + pal) << 8 | vflip << 1 | hflip ^ (facing > 0)   (ROM sprites face left)
    moveq   #0, %d4
    move.b  F_PALBASE(%a2), %d4
    add.b   PT_PAL(%a3), %d4
    lsl.w   #8, %d4
    move.b  PT_VFLIP(%a3), %d0
    add.b   %d0, %d0
    or.b    %d0, %d4
    move.b  PT_HFLIP(%a3), %d0
    tst.b   F_FACING(%a2)
    ble.s   1f
    eori.b  #1, %d0
1:  or.b    %d0, %d4
    or.w    (%sp), %d4              | tile_hi << 4
    | tile columns: column-major rows words each; flipped parts are walked from the last column
    movea.l PT_TILES(%a3), %a5
    move.w  %d5, %d6
    add.w   %d6, %d6                | rows * 2 bytes
    btst    #0, %d4
    beq.s   1f
    moveq   #0, %d0
    move.b  PT_COLS(%a3), %d0
    subq.w  #1, %d0
    mulu.w  %d6, %d0
    adda.l  %d0, %a5
    neg.w   %d6
1:  | reserve cols * (rows * 2 + 2) words; a1 = words already queued
    move.w  %d5, %d0
    add.w   %d0, %d0
    addq.w  #2, %d0
    mulu.w  %d7, %d0
    suba.l  %a1, %a1
    move.w  neo_cmd_count, %a1      | < CMD_BUF_SIZE: the sign extension of movea.w is harmless
    add.w   %a1, %d0
    cmp.w   #CMD_BUF_SIZE, %d0
    bls.s   2f
    sub.w   %a1, %d0
    movem.l %d0-%d1, -(%sp)
    jsr     SYS_vblankFlush         | full queue: written out now (in order), never dropped
    movem.l (%sp)+, %d0-%d1
    suba.l  %a1, %a1
2:  move.w  %d0, neo_cmd_count
    lea     neo_cmd_buf, %a4
    adda.l  %a1, %a4
    adda.l  %a1, %a4
    | per-row copy entry: 4 bytes of code per row, ending at 8f (straight) or 9f (vflip)
    lea     8f(%pc), %a0
    btst    #1, %d4
    beq.s   3f
    lea     9f(%pc), %a0
3:  move.w  %d5, %d0
    add.w   %d0, %d0
    add.w   %d0, %d0
    suba.w  %d0, %a0                | a0 = entry
    subq.w  #1, %d7
.Lt_col:
    move.w  %d3, %d0
    lsl.w   #6, %d0                 | SCB1 address = id * 64
    move.w  %d0, (%a4)+
    move.w  %d6, %d0
    bpl.s   4f
    neg.w   %d0
4:  move.w  %d0, (%a4)+             | run length = rows * 2
    movea.l %a5, %a1
    btst    #1, %d4
    beq.s   5f
    adda.w  %d0, %a1                | vflip: copy from the column end backwards
5:  jmp     (%a0)
    .rept   32
    move.w  (%a1)+, (%a4)+
    move.w  %d4, (%a4)+
    .endr
8:  bra.w   .Lt_next
    .rept   32
    move.w  -(%a1), (%a4)+
    move.w  %d4, (%a4)+
    .endr
9:
.Lt_next:
    adda.w  %d6, %a5
    addq.w  #1, %d3
    dbra    %d7, .Lt_col
    lea     PT_SIZE(%a3), %a3
    dbra    %d2, .Lt_part
.Lt_done:
    addq.l  #2, %sp                 | tile_hi word
    moveq   #MAX_COLS, %d0
    sub.w   %d1, %d0
    move.b  %d0, F_NCOLS(%a2)       | columns written for this frame
.Lt_ret:
    movem.l (%sp)+, %d2-%d7/%a2-%a5
    rts

    .global fighter_place
| d2 parts left, d3 columns left in the block, d4 ox, d5 oy, d6 rows, d7 columns of the part; a0 y run, a1 x run
fighter_place:
    movem.l %d2-%d7/%a2-%a3, -(%sp)
    movea.l 36(%sp), %a2
    move.w  50(%sp), %d4            | cam_x (int argument: low word)
    neg.w   %d4
    add.w   F_X(%a2), %d4           | ox = INT(x) - cam_x (INT = high word)
    move.w  #FLOOR_TOP, %d5
    add.w   F_Z(%a2), %d5
    sub.w   F_Y(%a2), %d5           | oy = FLOOR_TOP + INT(z) - INT(y)
    CURRENT_FRAME
    FRAME_PARTS
    movea.l 40(%sp), %a0
    movea.l 44(%sp), %a1
    moveq   #0, %d3
    move.w  54(%sp), %d3            | n (int argument: low word)
    beq     .Lp_done
    subq.w  #1, %d2
    bmi.w   .Lp_fill
.Lp_part:
    moveq   #0, %d7
    move.b  PT_COLS(%a3), %d7
    move.w  %d7, %d1
    lsl.w   #4, %d1                 | w = cols * 16
    | x0 = hflip ? ox - dx - w : ox + dx; facing right mirrors: x0 = 2 ox - x0 - w
    move.w  PT_DX(%a3), %d0
    tst.b   PT_HFLIP(%a3)
    beq.s   1f
    neg.w   %d0
    sub.w   %d1, %d0
1:  add.w   %d4, %d0
    tst.b   F_FACING(%a2)
    ble.s   2f
    neg.w   %d0
    sub.w   %d1, %d0
    add.w   %d4, %d0
    add.w   %d4, %d0
2:  and.w   #0x1FF, %d0
    lsl.w   #7, %d0
    move.w  %d0, (%a1)+             | SCB4: X
    | y0 = vflip ? oy - dy - rows * 16 : oy + dy; SCB3 = ((496 - y0) & 0x1FF) << 7 | rows
    moveq   #0, %d6
    move.b  PT_ROWS(%a3), %d6
    move.w  PT_DY(%a3), %d0
    tst.b   PT_VFLIP(%a3)
    beq.s   3f
    neg.w   %d0
    move.w  %d6, %d1
    lsl.w   #4, %d1
    sub.w   %d1, %d0
3:  add.w   %d5, %d0
    move.w  #496, %d1
    sub.w   %d0, %d1
    and.w   #0x1FF, %d1
    lsl.w   #7, %d1
    or.w    %d6, %d1
    move.w  %d1, (%a0)+             | SCB3: Y, height
    subq.w  #1, %d3
    beq.s   .Lp_done
    subq.w  #1, %d7                 | the rest of the part: sticky columns
    beq.s   5f
    cmp.w   %d3, %d7
    bls.s   4f
    move.w  %d3, %d7
4:  sub.w   %d7, %d3
    subq.w  #1, %d7
    moveq   #STICKY, %d0
    moveq   #0, %d1
6:  move.w  %d0, (%a0)+
    move.w  %d1, (%a1)+
    dbra    %d7, 6b
    tst.w   %d3
    beq.s   .Lp_done
5:  lea     PT_SIZE(%a3), %a3
    dbra    %d2, .Lp_part
.Lp_fill:                           | unused columns: height 0
    subq.w  #1, %d3
    bmi.s   .Lp_done
    moveq   #0, %d0
7:  move.w  %d0, (%a0)+
    move.w  %d0, (%a1)+
    dbra    %d3, 7b
.Lp_done:
    movem.l (%sp)+, %d2-%d7/%a2-%a3
    rts
