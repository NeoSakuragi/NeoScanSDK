/* NeoCart programmer v1: WeAct RP2350B core board (RP2350B, 16 MB QSPI flash, 12 MHz ABM8-272-T3).
 * No UART/I2C/SPI defaults: every GPIO is the cart bus (see ../design.py). */
#ifndef _BOARDS_NEOCART_PROGR_H
#define _BOARDS_NEOCART_PROGR_H
#define NEOCART_PROGR
#define PICO_RP2350A 0
#define PICO_BOOT_STAGE2_CHOOSE_W25Q080 1
#ifndef PICO_FLASH_SPI_CLKDIV
#define PICO_FLASH_SPI_CLKDIV 2
#endif
#ifndef PICO_FLASH_SIZE_BYTES
#define PICO_FLASH_SIZE_BYTES (16 * 1024 * 1024)
#endif
#ifndef PICO_RP2350_A2_SUPPORTED
#define PICO_RP2350_A2_SUPPORTED 1
#endif
#endif
