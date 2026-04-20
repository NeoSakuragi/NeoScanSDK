    .module crt0_z80
    .globl _z80_init
    .globl _z80_timer_isr
    .globl _z80_nmi
    .area _HEADER (ABS)

    .org 0x0000
    di
    jp  _startup

    .org 0x0038
    di
    push af
    push bc
    push de
    push hl
    call _z80_timer_isr
    pop  hl
    pop  de
    pop  bc
    pop  af
    ei
    reti

    .org 0x0066
    push af
    push de
    push hl
    call _z80_nmi
    pop  hl
    pop  de
    pop  af
    retn

    .org 0x0080
_startup:
    ld   sp, #0xFFFC
    im   1
    xor  a
    ld   hl, #0xF800
    ld   de, #0xF801
    ld   bc, #0x07FE
    ld   (hl), a
    ldir
    call _z80_init
    ei
.idle:
    halt
    jr   .idle

    .area _CODE
    .area _DATA
    .area _BSS
