#ifndef FLASH_PROGRAMMER_H
#define FLASH_PROGRAMMER_H

#include <stdint.h>

typedef enum {
    CHIP_P = 0,
    CHIP_S,
    CHIP_M,
    CHIP_C1,
    CHIP_C2,
    CHIP_V1,
    CHIP_V2,
    CHIP_V3,
    CHIP_V4,
    CHIP_INVALID
} chip_id_t;

void flash_programmer_init(void);
void flash_read_id(chip_id_t chip, uint16_t *mfr, uint16_t *dev);
void flash_chip_erase(chip_id_t chip);
void flash_program_byte(chip_id_t chip, uint32_t addr, uint8_t data);
uint8_t flash_read_byte(chip_id_t chip, uint32_t addr);

#endif
