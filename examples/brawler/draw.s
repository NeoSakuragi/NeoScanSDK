| Fighter rendering hot paths in 68000 assembly (measured: these two were 60 % of the frame in C).
| Same contracts as the prototypes in fighter.h; the C structure offsets used here are pinned by _Static_assert in fighter.c (the build stops when fighter.h or bm_chars.h moves a field); was claimed before 2026-10-03 but missing, and an added field shifted ncols (glitched sprites) -
| fighter.c (change a structure and the build stops there).
|
| fighter_tiles(f): when the shown frame or the facing changed, one SCB1 run per sprite column: rows x {tile, attribute}.
|   Queue space is reserved once per part; rows are copied by a computed jump into an unrolled block (20 cycles a row).
|   Each column is trimmed (the sprite budget, TODO #158 / #170; its trim words from export_bm.py, after the part's
|   tiles): only its rows from the first to the last non-empty tile
|   are queued (an empty column: none), and its trim goes to trim_cur (main.c col_trim[f->idx]): t[c] = (-top << 7) |
|   rows (top: from the feet), top[c] (the line guard counts each column on the lines it really covers; the LSPC counts
|   a sprite only on the lines of its height: fewer sprites per line, Bruno's select screen fits 96). The queue keeps
|   the words really written (the part reserved its untrimmed size).
| fighter_place(f, y, x, cam_x, n): SCB3/SCB4 words of n sprites (n >= ncols) into the caller's runs: each column its
|   own Y, height (SCB3 = ((496 - oy) << 7) + t[c]) and X (no sticky chains: a trimmed column starts lower than its
|   neighbours); columns past the frame and empty columns get height 0. trim_cur = the table fighter_tiles filled
|   (the line guard may have zeroed some of its t[]: a thinned effect).
|   fighter_tiles stores the frame's column count in ncols, so the caller sizes the runs (and the line guard counts) without
|   looking the frame up again.

    .equ    MAX_COLS, 20
    .equ    CMD_BUF_SIZE, 4096
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
    .equ    CH_TILE_HI, 60
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
| d1 columns left in the block, d2 parts left (in the column loop: the trims' step), d3 SCB1 address of the column,
| d4 attribute, d5 rows, d6 column step (bytes, signed), d7 columns of this part, a0 the copy block's end, a2 fighter (in
| the column loop: the trims), a3 part, a4 queue, a5 tile column, a6 trim_cur
fighter_tiles:
    movem.l %d2-%d7/%a2-%a6, -(%sp)
    movea.l 48(%sp), %a2
    movea.l trim_cur, %a6           | main.c: this entity's column trims (t[MAX_COLS], then top[MAX_COLS])
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
    lsl.w   #6, %d3                 | d3 = SCB1 address of the column (id * 64)
    lea     neo_cmd_buf, %a4        | a4 = the queue's end (neo_cmd_count is written back at the end)
    move.w  neo_cmd_count, %d0
    add.w   %d0, %d0
    adda.w  %d0, %a4
    moveq   #0, %d1
    move.b  blk_cols, %d1           | sprites per block (main.c: MAX_COLS in a fight, SEL_COLS on the select screen)
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
    | queue room for the part: cols * (rows * 2 + 2) words at most (trimmed columns take less)
    move.w  %d5, %d0
    add.w   %d0, %d0
    addq.w  #2, %d0
    mulu.w  %d7, %d0
    add.l   %d0, %d0
    add.l   %a4, %d0
    cmp.l   #neo_cmd_buf + 2 * CMD_BUF_SIZE, %d0
    bls.s   2f
    move.l  %a4, %d0                | full queue: written out now (in order), never dropped
    sub.l   #neo_cmd_buf, %d0
    lsr.l   #1, %d0
    move.w  %d0, neo_cmd_count
    move.l  %d1, -(%sp)
    jsr     SYS_vblankFlush
    move.l  (%sp)+, %d1
    lea     neo_cmd_buf, %a4
2:  | tile columns: column-major rows words each; flipped parts are walked from the last column
    movea.l PT_TILES(%a3), %a5
    move.w  %d5, %d6
    add.w   %d6, %d6                | rows * 2 bytes
    moveq   #0, %d0
    move.b  PT_COLS(%a3), %d0
    move.w  %d0, %a1
    mulu.w  %d6, %d0
    add.l   %a5, %d0                | the column trims (export_bm.py: 3 words a column after the part's tiles: t, top, the
    move.w  %d2, -(%sp)             | first tile's offset), walked with the columns; d2 (parts left) kept on the stack
    moveq   #0, %d2                 | step after a column's 3 words: 0, flipped -12
    lea     8f(%pc), %a0            | the copy block: 4 bytes of code a row, ending at 8f (straight) or 9f (vflip)
    btst    #1, %d4
    beq.s   3f
    lea     9f(%pc), %a0
3:  btst    #0, %d4
    beq.s   4f
    adda.w  %a1, %a1                | flipped: from the last column (its tiles, its trim)
    add.l   %a1, %d0
    adda.w  %a1, %a1
    add.l   %a1, %d0
    subq.l  #6, %d0                 | + (cols - 1) * 6
    moveq   #0, %d2
    move.b  PT_COLS(%a3), %d2
    subq.w  #1, %d2
    mulu.w  %d6, %d2
    adda.l  %d2, %a5
    neg.w   %d6
    moveq   #-12, %d2
4:  movea.l %d0, %a2
    subq.w  #1, %d7
.Lt_col:
    move.w  (%a2)+, %d0             | t = (-top << 7) | rows shown
    bne.s   2f
    addq.l  #4, %a2                 | an empty column: nothing queued, height 0
    adda.w  %d2, %a2
    clr.w   2 * MAX_COLS(%a6)
    clr.w   (%a6)+
    bra.w   .Lt_next
2:  move.w  %d0, (%a6)+             | trim_cur->t[c]: fighter_place adds (496 - oy) << 7
    move.w  (%a2)+, 2 * MAX_COLS - 2(%a6)   | trim_cur->top[c] (the line guard)
    movea.w (%a2)+, %a1
    adda.w  %d2, %a2
    adda.l  %a5, %a1                | the first tile copied (vflip: backwards from it)
    and.w   #63, %d0
    move.w  %d3, (%a4)+             | SCB1 address
    add.w   %d0, %d0
    move.w  %d0, (%a4)+             | run length = shown rows * 2
    add.w   %d0, %d0
    neg.w   %d0
    jmp     0(%a0,%d0.w)            | the copy's last (rows shown) entries
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
    add.w   #64, %d3
    dbra    %d7, .Lt_col
    move.w  (%sp)+, %d2
    movea.l 50(%sp), %a2            | the fighter again (48 + the tile_hi word)
    lea     PT_SIZE(%a3), %a3
    dbra    %d2, .Lt_part
.Lt_done:
    addq.l  #2, %sp                 | tile_hi word
    move.l  %a4, %d0                | the queue's words
    sub.l   #neo_cmd_buf, %d0
    lsr.l   #1, %d0
    move.w  %d0, neo_cmd_count
    moveq   #0, %d0
    move.b  blk_cols, %d0
    sub.w   %d1, %d0
    move.b  %d0, F_NCOLS(%a2)       | columns written for this frame
.Lt_ret:
    movem.l (%sp)+, %d2-%d7/%a2-%a6
    rts

    .global fighter_place
| d2 parts left, d3 columns left in the block, d4 ox, d5 oy, d6 scratch, d7 columns of the part; a0 y run, a1 x run, a6 trims
fighter_place:
    movem.l %d2-%d7/%a2-%a3/%a6, -(%sp)
    movea.l 40(%sp), %a2
    movea.l trim_cur, %a6           | the column trims fighter_tiles wrote
    move.w  54(%sp), %d4            | cam_x (int argument: low word)
    neg.w   %d4
    add.w   F_X(%a2), %d4           | ox = INT(x) - cam_x (INT = high word)
    move.w  floor_top, %d5          | fighter.h: the stage's (main.c)
    add.w   F_Z(%a2), %d5
    sub.w   F_Y(%a2), %d5           | oy = floor_top + INT(z) - INT(y)
    CURRENT_FRAME
    FRAME_PARTS
    movea.l 44(%sp), %a0
    movea.l 48(%sp), %a1
    moveq   #0, %d3
    move.w  58(%sp), %d3            | n (int argument: low word)
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
2:  move.w  %d0, %d1
    lsl.w   #7, %d1                 | d1 = SCB4 of this column: (x & 0x1FF) << 7, + 16 px = + $800 a column
    cmp.w   %d3, %d7                | columns of the part, clipped to the run
    bls.s   3f
    move.w  %d3, %d7
3:  sub.w   %d7, %d3
    subq.w  #1, %d7
    bmi.s   5f
    move.w  #496, %d0
    sub.w   %d5, %d0
    lsl.w   #7, %d0                 | (496 - oy) << 7
4:  move.w  (%a6)+, %d6             | SCB3 = ((496 - oy - top) & 0x1FF) << 7 | rows = this + the trim's t (an empty
    add.w   %d0, %d6                | column: rows 0)
    move.w  %d6, (%a0)+
    move.w  %d1, (%a1)+
    add.w   #0x800, %d1
    dbra    %d7, 4b
5:  tst.w   %d3
    beq.s   .Lp_done
    lea     PT_SIZE(%a3), %a3
    dbra    %d2, .Lp_part
.Lp_fill:                           | unused columns: height 0
    subq.w  #1, %d3
    bmi.s   .Lp_done
    moveq   #0, %d0
7:  move.w  %d0, (%a0)+
    move.w  %d0, (%a1)+
    dbra    %d3, 7b
.Lp_done:
    movem.l (%sp)+, %d2-%d7/%a2-%a3/%a6
    rts
