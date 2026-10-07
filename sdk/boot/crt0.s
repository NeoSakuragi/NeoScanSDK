| NeoScan CRT0 — Bootstrap and BIOS glue (GAS syntax, m68k-linux-gnu)
| Calls into C: game_init() and game_tick()

    .section .text.vectors, "ax"
    .global _start

| =====================================================================
| Vector table ($000000)
| =====================================================================
_start:
    .long   0x0010F300          /* Initial SSP */
    .long   0x00C00402          /* Reset PC -> BIOS init */
    .long   0x00C00408          /* Bus error */
    .long   0x00C0040E          /* Address error */
    .long   0x00C00414          /* Illegal instruction */
    .long   0x00C0041A          /* Divide by zero */
    .long   0x00C0041A          /* CHK instruction */
    .long   0x00C0041A          /* TRAPV instruction */
    .long   0x00C0041A          /* Privilege violation */
    .long   0x00C00420          /* Trace */
    .long   0x00C00426          /* Line-A */
    .long   0x00C00426          /* Line-F */
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF  /* Reserved */
    .long   0x00C0042C          /* Uninitialized interrupt */
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF  /* Reserved */
    .long   0x00C00432          /* Spurious interrupt */
    .long   vblank_handler      /* Level 1 = VBlank */
    .long   0x00C0043E          /* Level 2 = Timer -> BIOS */
    .long   0x00000000          /* Level 3 (unused) */
    .long   0, 0, 0, 0         /* Level 4-7 */
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF  /* TRAP 0-15 */
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF  /* FPU + Reserved */
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF
    .long   0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF

| =====================================================================
| Game header ($000100)
| =====================================================================
    .org    0x100
    .ascii  "NEO-GEO\0"        /* Magic */
    .word   0x0999              /* NGH number (patched by build tool) */
    .long   0x00100000          /* P ROM size (1 MB) */
    .long   __backup_ptr        /* backup RAM block in work RAM (neoscan.ld .backup; 0 = none) */
    .word   __backup_size       /* its size in bytes */
    .byte   2                   /* Eye catcher mode 2 = skip */
    .byte   0                   /* Logo sprite bank */
    .long   soft_dip            /* JP DIP */
    .long   soft_dip            /* US DIP */
    .long   soft_dip            /* EU DIP */

    .org    0x122
    .word   0x4EF9              /* JMP abs.l opcode */
    .long   user_handler        /* USER callback ($122-$127) */
    .word   0x4EF9
    .long   player_start        /* PLAYER_START ($128-$12D) */
    .word   0x4EF9
    .long   demo_end            /* DEMO_END ($12E-$133) */
    .word   0x4EF9
    .long   stub_rts            /* COIN_SOUND ($134-$139) */

    .org    0x13A
    .fill   70, 1, 0xFF         /* Required padding */
    .word   0x0000              /* Reserved */
    .long   security_code       /* Pointer to security code */

    .org    0x186
security_code:
    .word   0x7600, 0x4A6D, 0x0A14, 0x6600, 0x003C, 0x206D, 0x0A04, 0x3E2D
    .word   0x0A08, 0x13C0, 0x0030, 0x0001, 0x3210, 0x0C01, 0x00FF, 0x671A
    .word   0x3028, 0x0002, 0xB02D, 0x0ACE, 0x6610, 0x3028, 0x0004, 0xB02D
    .word   0x0ACF, 0x6606, 0xB22D, 0x0AD0, 0x6708, 0x5088, 0x51CF, 0xFFD4
    .word   0x3607, 0x4E75, 0x206D, 0x0A04, 0x3E2D, 0x0A08, 0x3210, 0xE049
    .word   0x0C01, 0x00FF, 0x671A, 0x3010, 0xB02D, 0x0ACE, 0x6612, 0x3028
    .word   0x0002, 0xE048, 0xB02D, 0x0ACF, 0x6606, 0xB22D, 0x0AD0, 0x6708
    .word   0x5888, 0x51CF, 0xFFD8, 0x3607, 0x4E75

| =====================================================================
| Code section
| =====================================================================
    .org    0x200
    .align  2

stub_rts:
    rts

    .align  2
| PLAYER_START: the BIOS calls it (from SYSTEM_IO) when a player presses START with a credit. BIOS_CREDIT_DEC +
| CREDIT_CHECK keep the players who have a credit; the credit itself is already taken (measured with Unibios 4.0: an
| extra CREDIT_DOWN took two; to recheck with an SNK MVS BIOS). USER_MODE = 2 (game); who started -> bios_start
| (C: extern volatile uint8_t bios_start).
| The game first filters the request (game_start_accept, weak, default all): a player it refuses (already playing, a
| screen where nobody may join) gets its START_FLAG bit cleared, and the BIOS keeps that credit.
player_start:
    moveml  %d0-%d7/%a0-%a6, -(%sp)
    moveq   #0, %d0
    moveb   0x10FDB4, %d0       /* BIOS_START_FLAG: bit 0 P1, bit 1 P2 */
    movel   %d0, -(%sp)
    jsr     game_start_accept   /* C: uint8_t game_start_accept(uint8_t flags) */
    addql   #4, %sp
    andb    0x10FDB4, %d0
    moveb   %d0, 0x10FDB4
    clrl    0x10FDB0            /* BIOS_CREDIT_DEC1-4 */
    tstb    %d0
    beq.s   3f
    btst    #0, %d0
    beq.s   1f
    moveb   #1, 0x10FDB0
1:  btst    #1, %d0
    beq.s   2f
    moveb   #1, 0x10FDB1
2:  jsr     0xC00450            /* CREDIT_CHECK: clears the START_FLAG bits of players short of credits */
    moveb   0x10FDB4, %d0
    beq.s   3f
    orb     %d0, bios_start
    moveb   #2, 0x10FDAF        /* USER_MODE = 2 (game) */
3:  moveml  (%sp)+, %d0-%d7/%a0-%a6
    rts

| DEMO_END: the BIOS calls it (from SYSTEM_IO) when the attract must stop (a coin went in). It does not expect it back:
| returning left the game inside SYSTEM_IO for good (measured with Unibios 4.0). So the demo ends here: control goes
| back to the BIOS, which then calls USER with request 3 (title). bios_demo_end is kept for the game to read.
demo_end:
    moveb   #1, bios_demo_end
    bra     SYS_return

| SYS_return (C: void SYS_return(void)): hand control back to the BIOS (end of the demo, game over). USER_MODE 0 unless
| a game is still on; the BIOS resets the stack.
    .global SYS_return
SYS_return:
    movew   #0x2700, %sr
    clrb    game_active
    andib   #0x7F, 0x10FD80     /* the BIOS handles vblank again */
    jmp     0xC00444            /* SYSTEM_RETURN */

| game_enter (C: void game_enter(uint8_t request)): called on USER request 2 (demo) and 3 (title) before the frame loop.
| Weak default: game_init (the old behaviour: the game starts at once). A game with an attract / title defines its own.
    .weak   game_enter
game_enter:
    jmp     game_init

    .weak   game_start_accept
game_start_accept:
    movel   4(%sp), %d0
    rts

| Software DIP table (the BIOS's game settings menu; the chosen values land in BIOS RAM $10FD84: +0/+2 timers,
| +4/+5 counters, +6.. list settings). Layout: 16-byte name, 2 + 2 timer bytes ($FFFF unused), 2 counter bytes ($FF
| unused), 10 list bytes (high nibble default choice, low nibble choice count, 0 = unused), then 12-char texts: each
| list setting's name and its choices. Weak: a game defines its own `soft_dip` (examples/brawler/main.c).
    .align  2
    .weak   soft_dip
soft_dip:
    .ascii  "NEOSCAN GAME    "
    .byte   0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
    .fill   10, 1, 0

| --- Copy .data initial values from ROM to work RAM ---------------------
    .align  2
copy_data:
    lea     __data_load, %a0
    lea     __data_start, %a1
    lea     __data_end, %a2
.Lcopy_loop:
    cmpa.l  %a2, %a1
    bge.s   .Lcopy_done
    move.w  (%a0)+, (%a1)+
    bra.s   .Lcopy_loop
.Lcopy_done:
    rts

| --- Zero BSS ---------------------------------------------------------
    .align  2
zero_bss:
    lea     __bss_start, %a0
    lea     __bss_end, %a1
.Lzero_loop:
    cmpa.l  %a1, %a0
    bge.s   .Lzero_done
    clr.w   (%a0)+
    bra.s   .Lzero_loop
.Lzero_done:
    rts

| --- VBlank handler ---------------------------------------------------
    .align  2
    .global vblank_flag
vblank_handler:
    btst    #7, 0x10FD80        /* BIOS_SYSTEM_MODE */
    bne.s   .Lgame_vblank
    | During BIOS init — let BIOS handle it. game_active is .bss: until boot_init has cleared it (init_magic set
    | after zero_bss) it holds whatever the RAM held (TODO #171: read here at power-on before the game's first USER
    | call; 0 only because the BIOS happened to clear it)
    cmpil   #0x4E454F21, init_magic
    bne.s   .Lbios_vblank
    tstb    game_active
    beq.s   .Lbios_vblank
    | Game was running but BIOS stole mode bit — take it back
    orib    #0x80, 0x10FD80
.Lgame_vblank:
    moveml  %d0-%d1/%a0-%a3, %sp@-
    movew   #4, 0x3C000C        /* ACK VBlank */
    moveb   #0, 0x300001        /* Watchdog */
    moveb   #1, vblank_flag
    addw    #1, vblank_count
    moveml  %sp@+, %d0-%d1/%a0-%a3
    rte
.Lbios_vblank:
    jmp     0xC00438            /* SYSTEM_INT1 — BIOS handles it */

| --- USER handler (dispatches to C) ----------------------------------
    .align  2
    .global user_handler
user_handler:
    moveb   0x10FDAE, %d0       /* BIOS_USER_REQUEST */
    moveb   %d0, 0x10F208       /* Log request to debug RAM */
    andiw   #0x00FF, %d0
    cmpib   #0, %d0
    beq     do_init
    cmpib   #2, %d0
    beq     do_game
    cmpib   #3, %d0
    beq     do_game
    moveb   #0xDD, 0x10F209     /* Log unhandled request */
    jmp     0xC00444            /* SYSTEM_RETURN */

    .align  2
do_init:
    moveb   #0, 0x300001        /* Watchdog */
    bsr     boot_init
    jsr     0xC00444            /* SYSTEM_RETURN */

| One-time init since power-on: .bss cleared, .data copied, game_init. The BIOS sends USER request 0 only while the
| game's backup RAM is uninitialised (in practice: the first boot), so the demo / title entry runs it too when the magic
| in .noinit (not cleared by zero_bss, random at power-on) says it hasn't happened yet.
boot_init:
    jsr     zero_bss
    jsr     copy_data
    movel   #0x4E454F21, init_magic
    jsr     0xC004C8            /* LSP_1ST (clear sprites) */
    jsr     0xC004C2            /* FIX_CLEAR */
    jsr     game_init           /* C function */
    rts

    .align  2
do_game:                        /* d0 = USER request (2 demo, 3 title) */
    cmpil   #0x4E454F21, init_magic
    beq.s   1f
    movel   %d0, -(%sp)
    bsr     boot_init           /* no request 0 since power-on (backup RAM already set up) */
    movel   (%sp)+, %d0
1:  orib    #0x80, 0x10FD80     /* Set system mode bit 7 */
    moveb   #1, game_active     /* Mark game as running for VBlank guard */
    clrb    bios_demo_end
    clrb    bios_start
    movew   #0x2000, %sr        /* Enable interrupts */
    movel   %d0, -(%sp)
    jsr     game_enter
    addql   #4, %sp

.Lmain_loop:
    clrb    vblank_flag
    clrl    wait_cycles         /* reset spin counter */
.Lwait:
    addl    #1, wait_cycles     /* count each spin: tstb+beq+addl = ~20 cycles */
    tstb    vblank_flag
    beq.s   .Lwait
    jsr     0xC0044A            /* SYSTEM_IO */
    orib    #0x80, 0x10FD80
    jsr     JOY_update
    addql   #1, game_ticks      /* ticks started (tests key replays and traces by it: a lag frame shifts frames, not ticks) */
    jsr     game_tick
    bra.s   .Lmain_loop

| --- not cleared by zero_bss ----------------------------------------------
    .section .noinit, "aw", @nobits
    .align  2
init_magic:
    .skip   4

| --- BSS --------------------------------------------------------------
    .section .bss
    .align  2
vblank_flag:
    .skip   2
    .global vblank_count
vblank_count:
    .skip   2
game_active:
    .skip   2
    .global bios_demo_end, bios_start
bios_demo_end:
    .skip   1
bios_start:
    .skip   1
    .global wait_cycles
    .align  4
wait_cycles:
    .skip   4
    .global game_ticks
game_ticks:
    .skip   4
