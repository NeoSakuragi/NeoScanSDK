OUTPUT_FORMAT("elf32-m68k")
OUTPUT_ARCH(m68k)
ENTRY(_start)

MEMORY
{
    rom (rx)   : ORIGIN = 0x000000, LENGTH = 1M
    p2 (rx)    : ORIGIN = 0x200000, LENGTH = 1M    /* second program MB: bank 0 of the P2 window, mapped at reset */
    wram (rwx) : ORIGIN = 0x100000, LENGTH = 64K
}

SECTIONS
{
    .vectors 0x000000 : {
        *(.text.vectors)
    } > rom

    .text : {
        *(.text .text.*)
        *(.rodata .rodata.*)
        . = ALIGN(2);
    } > rom

    /* big read-only data (a game's tables): sections named .p2data go to $200000 (objcopy --rename-section on an
       object, see examples/brawler/Makefile); tools/neobuild.py appends it after the first MB of the P ROM */
    .p2data : {
        *(.p2data .p2data.*)
    } > p2

    /* initialised variables: live in work RAM, initial values stored in ROM, copied by crt0 (copy_data) */
    .data : {
        __data_start = .;
        *(.data .data.*)
        . = ALIGN(2);
        __data_end = .;
    } > wram AT > rom
    __data_load = LOADADDR(.data);

    /* survives zero_bss: crt0's "initialised since power-on" magic (random at power-on) */
    .noinit (NOLOAD) : {
        *(.noinit)
    } > wram

    .bss : {
        __bss_start = .;
        *(.bss .bss.*)
        *(COMMON)
        __bss_end = .;
    } > wram

    /DISCARD/ : {
        *(.comment)
        *(.note*)
        *(.eh_frame*)
        *(.gnu.attributes)
    }
}
