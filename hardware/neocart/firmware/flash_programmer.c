/*
 * Flash chip programmer — bit-bang driver for RP2040
 *
 * Drives 7 flash chips via:
 *   - 3x 74HC595 shift registers for 24-bit address bus
 *   - 8-bit data bus on GPIO3-GPIO10
 *   - Individual chip enables on GPIO13-GPIO17, GPIO22-GPIO23
 *   - Shared WE/OE on GPIO11-GPIO12
 *
 * All 16-bit flash chips (AM29F400) are programmed in byte mode
 * (BYTE# pin active) so we only need 8 data lines.
 *
 * Programming algorithms:
 *   AM29F400:    AMD standard — 0x555=0xAA, 0x2AA=0x55, 0x555=0xA0, addr=data
 *   SST39SF010:  SST standard — 0x5555=0xAA, 0x2AAA=0x55, 0x5555=0xA0, addr=data
 */

#include "flash_programmer.h"
#include "pico/stdlib.h"
#include "hardware/gpio.h"

// ─── GPIO Pin Assignments (match schematic) ───

#define PIN_SR_SER      0
#define PIN_SR_SRCLK    1
#define PIN_SR_RCLK     2

#define PIN_DATA_BASE   3   // GPIO3-GPIO10 = D0-D7
#define PIN_DATA_MASK   (0xFF << PIN_DATA_BASE)

#define PIN_nWE         11
#define PIN_nOE         12

#define PIN_nCE_P       13
#define PIN_nCE_S       14
#define PIN_nCE_M       15
#define PIN_nCE_C1      16
#define PIN_nCE_C2      17
#define PIN_nCE_V1      22
#define PIN_nCE_V2      23
#define PIN_nCE_V3      24
#define PIN_nCE_V4      25

#define PIN_nBYTE       18
#define PIN_BUS_DIR     19
#define PIN_SR_nOE      20
#define PIN_BUF_nOE     21

static const uint8_t ce_pins[] = {
    PIN_nCE_P, PIN_nCE_S, PIN_nCE_M, PIN_nCE_C1, PIN_nCE_C2,
    PIN_nCE_V1, PIN_nCE_V2, PIN_nCE_V3, PIN_nCE_V4
};

typedef enum {
    FLASH_TYPE_AMD,    // AM29F400 (P, C1, C2)
    FLASH_TYPE_SST     // SST39SF010 (S, M)
} flash_type_t;

static flash_type_t chip_type(chip_id_t chip) {
    switch (chip) {
        case CHIP_P:  case CHIP_C1: case CHIP_C2:
        case CHIP_V1: case CHIP_V2:
        case CHIP_V3: case CHIP_V4:               return FLASH_TYPE_AMD;
        case CHIP_S:  case CHIP_M:                return FLASH_TYPE_SST;
        default:                                  return FLASH_TYPE_SST;
    }
}

// ─── Low-level bus operations ───

static void shift_out_address(uint32_t addr) {
    for (int i = 23; i >= 0; i--) {
        gpio_put(PIN_SR_SER, (addr >> i) & 1);
        gpio_put(PIN_SR_SRCLK, 1);
        __asm volatile("nop; nop; nop; nop");
        gpio_put(PIN_SR_SRCLK, 0);
    }
    gpio_put(PIN_SR_RCLK, 1);
    __asm volatile("nop; nop; nop; nop");
    gpio_put(PIN_SR_RCLK, 0);
}

static void set_data_output(uint8_t data) {
    for (int i = 0; i < 8; i++) {
        gpio_set_dir(PIN_DATA_BASE + i, GPIO_OUT);
    }
    uint32_t current = gpio_get_all();
    current &= ~PIN_DATA_MASK;
    current |= ((uint32_t)data << PIN_DATA_BASE);
    gpio_put_all(current);
}

static void set_data_input(void) {
    for (int i = 0; i < 8; i++) {
        gpio_set_dir(PIN_DATA_BASE + i, GPIO_IN);
    }
}

static uint8_t read_data(void) {
    return (gpio_get_all() >> PIN_DATA_BASE) & 0xFF;
}

static void select_chip(chip_id_t chip) {
    for (int i = 0; i < 9; i++) {
        gpio_put(ce_pins[i], (i != chip));
    }
}

static void deselect_all(void) {
    for (int i = 0; i < 9; i++) {
        gpio_put(ce_pins[i], 1);
    }
}

static void enable_programming_bus(void) {
    gpio_put(PIN_SR_nOE, 0);    // enable shift register outputs
    gpio_put(PIN_BUF_nOE, 0);   // enable data buffer
    gpio_put(PIN_BUS_DIR, 1);   // RP2040 → flash direction
    gpio_put(PIN_nBYTE, 0);     // byte mode for 16-bit chips
}

static void disable_programming_bus(void) {
    set_data_input();
    gpio_put(PIN_SR_nOE, 1);    // tristate shift registers
    gpio_put(PIN_BUF_nOE, 1);   // tristate data buffer
    gpio_put(PIN_nBYTE, 1);     // word mode (default for Neo Geo)
    deselect_all();
}

// ─── Flash write/read cycles ───

static void flash_write_cycle(chip_id_t chip, uint32_t addr, uint8_t data) {
    shift_out_address(addr);
    set_data_output(data);
    select_chip(chip);
    gpio_put(PIN_nWE, 0);
    __asm volatile("nop; nop; nop; nop; nop; nop; nop; nop");
    gpio_put(PIN_nWE, 1);
    __asm volatile("nop; nop; nop; nop");
    deselect_all();
}

static uint8_t flash_read_cycle(chip_id_t chip, uint32_t addr) {
    shift_out_address(addr);
    set_data_input();
    select_chip(chip);
    gpio_put(PIN_nOE, 0);
    __asm volatile("nop; nop; nop; nop; nop; nop; nop; nop");
    uint8_t val = read_data();
    gpio_put(PIN_nOE, 1);
    deselect_all();
    return val;
}

static void wait_toggle(chip_id_t chip, uint32_t addr) {
    set_data_input();
    select_chip(chip);
    gpio_put(PIN_nOE, 0);

    uint8_t prev = read_data() & 0x40;
    for (int i = 0; i < 1000000; i++) {
        uint8_t curr = read_data() & 0x40;
        if (curr == prev) break;
        prev = curr;
        sleep_us(1);
    }

    gpio_put(PIN_nOE, 1);
    deselect_all();
}

// ─── Public API ───

void flash_programmer_init(void) {
    // Shift register pins
    gpio_init(PIN_SR_SER);   gpio_set_dir(PIN_SR_SER, GPIO_OUT);
    gpio_init(PIN_SR_SRCLK); gpio_set_dir(PIN_SR_SRCLK, GPIO_OUT);
    gpio_init(PIN_SR_RCLK);  gpio_set_dir(PIN_SR_RCLK, GPIO_OUT);

    gpio_put(PIN_SR_SER, 0);
    gpio_put(PIN_SR_SRCLK, 0);
    gpio_put(PIN_SR_RCLK, 0);

    // Data bus — start as input
    for (int i = 0; i < 8; i++) {
        gpio_init(PIN_DATA_BASE + i);
        gpio_set_dir(PIN_DATA_BASE + i, GPIO_IN);
    }

    // Control signals — active low, start deasserted (high)
    uint8_t ctrl_pins[] = {PIN_nWE, PIN_nOE, PIN_nCE_P, PIN_nCE_S,
                           PIN_nCE_M, PIN_nCE_C1, PIN_nCE_C2,
                           PIN_nBYTE, PIN_SR_nOE, PIN_BUF_nOE};
    for (int i = 0; i < sizeof(ctrl_pins); i++) {
        gpio_init(ctrl_pins[i]);
        gpio_set_dir(ctrl_pins[i], GPIO_OUT);
        gpio_put(ctrl_pins[i], 1);
    }

    // BUS_DIR — low by default (inactive)
    gpio_init(PIN_BUS_DIR);
    gpio_set_dir(PIN_BUS_DIR, GPIO_OUT);
    gpio_put(PIN_BUS_DIR, 0);
}

void flash_read_id(chip_id_t chip, uint16_t *mfr, uint16_t *dev) {
    enable_programming_bus();

    if (chip_type(chip) == FLASH_TYPE_AMD) {
        flash_write_cycle(chip, 0x555, 0xAA);
        flash_write_cycle(chip, 0x2AA, 0x55);
        flash_write_cycle(chip, 0x555, 0x90);
    } else {
        flash_write_cycle(chip, 0x5555, 0xAA);
        flash_write_cycle(chip, 0x2AAA, 0x55);
        flash_write_cycle(chip, 0x5555, 0x90);
    }

    sleep_us(10);

    *mfr = flash_read_cycle(chip, 0x00);
    *dev = flash_read_cycle(chip, 0x01);

    // Exit ID mode
    flash_write_cycle(chip, 0x000, 0xF0);
    sleep_us(10);

    disable_programming_bus();
}

void flash_chip_erase(chip_id_t chip) {
    enable_programming_bus();

    if (chip_type(chip) == FLASH_TYPE_AMD) {
        flash_write_cycle(chip, 0x555, 0xAA);
        flash_write_cycle(chip, 0x2AA, 0x55);
        flash_write_cycle(chip, 0x555, 0x80);
        flash_write_cycle(chip, 0x555, 0xAA);
        flash_write_cycle(chip, 0x2AA, 0x55);
        flash_write_cycle(chip, 0x555, 0x10);
    } else {
        flash_write_cycle(chip, 0x5555, 0xAA);
        flash_write_cycle(chip, 0x2AAA, 0x55);
        flash_write_cycle(chip, 0x5555, 0x80);
        flash_write_cycle(chip, 0x5555, 0xAA);
        flash_write_cycle(chip, 0x2AAA, 0x55);
        flash_write_cycle(chip, 0x5555, 0x10);
    }

    sleep_ms(200);
    wait_toggle(chip, 0);

    disable_programming_bus();
}

void flash_program_byte(chip_id_t chip, uint32_t addr, uint8_t data) {
    enable_programming_bus();

    if (chip_type(chip) == FLASH_TYPE_AMD) {
        flash_write_cycle(chip, 0x555, 0xAA);
        flash_write_cycle(chip, 0x2AA, 0x55);
        flash_write_cycle(chip, 0x555, 0xA0);
    } else {
        flash_write_cycle(chip, 0x5555, 0xAA);
        flash_write_cycle(chip, 0x2AAA, 0x55);
        flash_write_cycle(chip, 0x5555, 0xA0);
    }

    flash_write_cycle(chip, addr, data);

    if (chip_type(chip) == FLASH_TYPE_SST) {
        sleep_us(20);
    } else {
        wait_toggle(chip, addr);
    }

    disable_programming_bus();
}

uint8_t flash_read_byte(chip_id_t chip, uint32_t addr) {
    enable_programming_bus();

    // Ensure we're not in any special mode
    flash_write_cycle(chip, 0x000, 0xF0);
    sleep_us(1);

    uint8_t val = flash_read_cycle(chip, addr);

    disable_programming_bus();
    return val;
}
