OUTPUT_FORMAT("elf32-m68k")
OUTPUT_ARCH(m68k)
ENTRY(_start)

MEMORY
{
    rom (rx)   : ORIGIN = 0x000000, LENGTH = 1M
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
        *(.data .data.*)
    } > rom

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
