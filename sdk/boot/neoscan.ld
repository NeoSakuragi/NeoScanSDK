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
        . = ALIGN(2);
    } > rom

    /* the P2 window ($200000-$2FFFFF), bank-switched (neo_bank.h): sections named .p2bankN link at $200000 and load at
       $200000 + N MB, i.e. P ROM MB 1 + N once tools/neobuild.py drops the $100000-$1FFFFF gap; .p2data = bank 0 (the
       one mapped at reset). Data moves there by objcopy --rename-section (examples/brawler/Makefile,
       tools/brawler/bank_pack.py). The banks share their addresses: nothing checks a reference from one bank into
       another here (bank_pack.py does). A bank keeps its last 16 bytes free ($2FFFF0-$2FFFFF: the bank register). */
    .p2bank0 0x200000 : AT(0x200000) { *(.p2data .p2data.* .p2bank0 .p2bank0.*) }
    .p2bank1 0x200000 : AT(0x300000) { *(.p2bank1 .p2bank1.*) }
    .p2bank2 0x200000 : AT(0x400000) { *(.p2bank2 .p2bank2.*) }
    .p2bank3 0x200000 : AT(0x500000) { *(.p2bank3 .p2bank3.*) }
    .p2bank4 0x200000 : AT(0x600000) { *(.p2bank4 .p2bank4.*) }
    .p2bank5 0x200000 : AT(0x700000) { *(.p2bank5 .p2bank5.*) }
    .p2bank6 0x200000 : AT(0x800000) { *(.p2bank6 .p2bank6.*) }
    ASSERT(SIZEOF(.p2bank0) <= 0xFFFF0 && SIZEOF(.p2bank1) <= 0xFFFF0 && SIZEOF(.p2bank2) <= 0xFFFF0 &&
           SIZEOF(.p2bank3) <= 0xFFFF0 && SIZEOF(.p2bank4) <= 0xFFFF0 && SIZEOF(.p2bank5) <= 0xFFFF0 &&
           SIZEOF(.p2bank6) <= 0xFFFF0, "a P2 bank is over 1 MB - 16 bytes")

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

    /* the game's backup RAM block (SNK header $10E / $112): variables declared with NEO_BACKUP (neo_backup.h). The
       BIOS keeps it in battery RAM on MVS and copies it back here at power-on, so it is neither cleared nor copied
       by crt0. Its first 2 bytes are the debug dipswitches (SNK convention; neo_backup.h). None declared: size 0,
       header pointer 0 (the BIOS then keeps nothing). */
    .backup (NOLOAD) : {
        __backup_start = .;
        *(.backup .backup.*)
        . = ALIGN(2);
    } > wram
    __backup_size = SIZEOF(.backup);
    __backup_ptr = __backup_size ? __backup_start : 0;

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
