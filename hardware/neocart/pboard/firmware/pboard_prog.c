/* NeoCart P board programmer firmware (RP2350B). Binary protocol over USB CDC (stdio).
 *
 * GPIO map = design.py: FD0-15 = GPIO0-15 (P flash DQ, x16), VA_DQ0-7 = GPIO16-23, VB_DQ0-7 = GPIO24-31,
 * SR_DATA 32, SR_CLK 33, SR_LATCH 34, nP_OE 35, nP_WE 36, nVA_OE 37, nVA_WE 38, nVB_OE 39, nVB_WE 40,
 * PROG_SENSE 41, VBUS_SENSE 42, LED 43. Addresses go out through nine 74HC595 (72 bits): chain order
 * P A0-7, A8-15, A16-21, VA 0-7, 8-15, 16-23, VB 0-7, 8-15, 16-23; the farthest register (VB 16-23) is shifted first.
 *
 * Flash: S29GL064N (Infineon), 8 MB. Group 0 = P in word mode (unlock 0x555/0x2AA word addresses),
 * groups 1/2 = two byte-mode chips each (unlock 0xAAA/0x555 byte addresses), address bit 23 selects the chip
 * through the board's /CE decode, so the programmer just sends a 24-bit address.
 *
 * Protocol (little-endian): host sends 1 command byte + args, device answers 'K' + payload or 'E' + errno.
 *   'I'                       -> 'K' ver(1) proto(1) prog_mode(1) vbus(1) then for g in 0..2: mfr(1) dev(2)   (autoselect ID)
 *   'C' g                     -> chip erase group g (both chips of a V group), 'K' when done (can take minutes)
 *   'S' g addr(4)             -> sector erase (64 KB sector containing addr; the 8 KB boot sectors at the bottom too)
 *   'W' g addr(4) len(2) data -> write-buffer program len bytes (len <= 4096, addr and len multiples of 32)
 *   'R' g addr(4) len(2)      -> 'K' + len bytes read back
 *   'M'                       -> 'K' prog_mode vbus
 */
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"

#define PIN_SR_DATA 32
#define PIN_SR_CLK  33
#define PIN_SR_LATCH 34
#define PIN_LED 43
static const uint PIN_OE[3] = {35, 37, 39};
static const uint PIN_WE[3] = {36, 38, 40};
static const uint DATA_BASE[3] = {0, 16, 24};      /* first GPIO of the group's data bus */
static const uint DATA_BITS[3] = {16, 8, 8};
#define PROTO 1
#define VERSION 1

static uint32_t addr_cur[3];

/* ---- 74HC595 chain --------------------------------------------------------------------------------------- */
static void sr_shift_byte(uint8_t b) {
    for (int i = 7; i >= 0; i--) {
        gpio_put(PIN_SR_DATA, (b >> i) & 1);
        gpio_put(PIN_SR_CLK, 1);
        gpio_put(PIN_SR_CLK, 0);
    }
}
static void addr_set(uint g, uint32_t a) {
    addr_cur[g] = a;
    /* bytes in chain order, farthest first: VB16-23, VB8-15, VB0-7, VA16-23, VA8-15, VA0-7, P16-21, P8-15, P0-7 */
    const uint32_t p = addr_cur[0], va = addr_cur[1], vb = addr_cur[2];
    uint8_t bytes[9] = { vb >> 16, vb >> 8, vb, va >> 16, va >> 8, va, p >> 16, p >> 8, p };
    for (int i = 0; i < 9; i++) sr_shift_byte(bytes[i]);
    gpio_put(PIN_SR_LATCH, 1);
    gpio_put(PIN_SR_LATCH, 0);
}

/* ---- data bus --------------------------------------------------------------------------------------------- */
static void bus_out(uint g, uint32_t v) {
    uint32_t mask = ((1u << DATA_BITS[g]) - 1) << DATA_BASE[g];
    gpio_set_dir_masked(mask, mask);
    gpio_put_masked(mask, v << DATA_BASE[g]);
}
static void bus_in(uint g) {
    uint32_t mask = ((1u << DATA_BITS[g]) - 1) << DATA_BASE[g];
    gpio_set_dir_masked(mask, 0);
}
static uint32_t bus_read(uint g) {
    return (gpio_get_all() >> DATA_BASE[g]) & ((1u << DATA_BITS[g]) - 1);
}
static inline void tiny_delay(void) { __asm volatile("nop\nnop\nnop\nnop\nnop\nnop\nnop\nnop"); }

/* ---- flash primitives -------------------------------------------------------------------------------------- */
static void fl_write(uint g, uint32_t a, uint32_t v) {          /* one write cycle: /OE high, /WE pulse */
    gpio_put(PIN_OE[g], 1);
    addr_set(g, a);
    bus_out(g, v);
    gpio_put(PIN_WE[g], 0); tiny_delay(); tiny_delay();          /* tWP >= 35 ns */
    gpio_put(PIN_WE[g], 1); tiny_delay();
}
static uint32_t fl_read(uint g, uint32_t a) {
    bus_in(g);
    addr_set(g, a);
    gpio_put(PIN_OE[g], 0);
    sleep_us(1);                                                  /* tACC 90 ns, plus 595 settling */
    uint32_t v = bus_read(g);
    gpio_put(PIN_OE[g], 1);
    return v;
}
/* unlock addresses: word mode 0x555/0x2AA, byte mode 0xAAA/0x555 */
static uint32_t ua1(uint g) { return g == 0 ? 0x555 : 0xAAA; }
static uint32_t ua2(uint g) { return g == 0 ? 0x2AA : 0x555; }
static uint32_t chipbase(uint g, uint32_t a) { return g == 0 ? 0 : (a & 0x800000); }   /* byte-mode chip select bit */

static void fl_reset(uint g, uint32_t a) { fl_write(g, chipbase(g, a), 0xF0); }
static int fl_wait(uint g, uint32_t a, uint32_t expect, uint32_t timeout_ms) {   /* DQ7 data polling */
    absolute_time_t t0 = get_absolute_time();
    for (;;) {
        uint32_t v = fl_read(g, a);
        if ((v & 0x80) == (expect & 0x80)) return 0;
        if (v & 0x20) {                                          /* DQ5 = timeout exceeded */
            v = fl_read(g, a);
            if ((v & 0x80) == (expect & 0x80)) return 0;
            fl_reset(g, a); return 2;
        }
        if (absolute_time_diff_us(t0, get_absolute_time()) > (int64_t)timeout_ms * 1000) { fl_reset(g, a); return 3; }
    }
}
static void fl_id(uint g, uint32_t base, uint8_t *mfr, uint16_t *dev) {
    fl_write(g, base + ua1(g), 0xAA); fl_write(g, base + ua2(g), 0x55); fl_write(g, base + ua1(g), 0x90);
    *mfr = fl_read(g, base + 0) & 0xFF;
    *dev = g == 0 ? fl_read(g, base + 1) : fl_read(g, base + 2);
    fl_reset(g, base);
}
static int fl_chip_erase(uint g, uint32_t base) {
    fl_write(g, base + ua1(g), 0xAA); fl_write(g, base + ua2(g), 0x55); fl_write(g, base + ua1(g), 0x80);
    fl_write(g, base + ua1(g), 0xAA); fl_write(g, base + ua2(g), 0x55); fl_write(g, base + ua1(g), 0x10);
    return fl_wait(g, base, 0xFF, 400000);                        /* tCE max ~ 4 min class */
}
static int fl_sector_erase(uint g, uint32_t a) {
    uint32_t base = chipbase(g, a);
    fl_write(g, base + ua1(g), 0xAA); fl_write(g, base + ua2(g), 0x55); fl_write(g, base + ua1(g), 0x80);
    fl_write(g, base + ua1(g), 0xAA); fl_write(g, base + ua2(g), 0x55); fl_write(g, a, 0x30);
    return fl_wait(g, a, 0xFF, 10000);
}
/* write-buffer program: up to 16 words / 32 bytes inside one 32-byte-aligned block */
static int fl_wb_program(uint g, uint32_t a, const uint8_t *d, uint n_units) {
    uint32_t base = chipbase(g, a);
    fl_write(g, base + ua1(g), 0xAA); fl_write(g, base + ua2(g), 0x55);
    fl_write(g, a, 0x25);                                          /* write to buffer, at the sector address */
    fl_write(g, a, n_units - 1);
    uint32_t last = 0;
    for (uint i = 0; i < n_units; i++) {
        uint32_t v = g == 0 ? (d[2 * i] | (d[2 * i + 1] << 8)) : d[i];   /* P image is little-endian words */
        fl_write(g, a + i, v); last = v;
    }
    fl_write(g, a, 0x29);                                          /* program buffer to flash */
    return fl_wait(g, a + n_units - 1, last, 100);
}

/* ---- protocol ---------------------------------------------------------------------------------------------- */
static int rd(void) { int c; while ((c = getchar_timeout_us(1000000)) == PICO_ERROR_TIMEOUT) {} return c; }
static uint32_t rd32(void) { uint32_t v = rd(); v |= rd() << 8; v |= rd() << 16; v |= (uint32_t)rd() << 24; return v; }
static uint16_t rd16(void) { uint16_t v = rd(); v |= rd() << 8; return v; }
static void ok(void) { putchar_raw('K'); }
static void err(int e) { putchar_raw('E'); putchar_raw(e); }

int main(void) {
    stdio_init_all();
    for (uint p = 0; p < 32; p++) { gpio_init(p); gpio_set_dir(p, GPIO_IN); }
    for (uint p = 32; p <= 40; p++) { gpio_init(p); gpio_set_dir(p, GPIO_OUT); gpio_put(p, p >= 35); }   /* /OE,/WE high; SR lines low */
    gpio_init(41); gpio_set_dir(41, GPIO_IN); gpio_init(42); gpio_set_dir(42, GPIO_IN);
    gpio_init(PIN_LED); gpio_set_dir(PIN_LED, GPIO_OUT);
    static uint8_t buf[4096];
    for (;;) {
        int c = getchar_timeout_us(100000);
        if (c == PICO_ERROR_TIMEOUT) { gpio_put(PIN_LED, gpio_get(41)); continue; }
        int prog = gpio_get(41), vbus = gpio_get(42);
        if (c == 'M') { ok(); putchar_raw(prog); putchar_raw(vbus); continue; }
        if (c == 'I') {
            ok(); putchar_raw(VERSION); putchar_raw(PROTO); putchar_raw(prog); putchar_raw(vbus);
            for (uint g = 0; g < 3; g++) { uint8_t m = 0; uint16_t d = 0; if (prog) fl_id(g, 0, &m, &d); putchar_raw(m); putchar_raw(d); putchar_raw(d >> 8); }
            continue;
        }
        if (!prog) { rd(); err(9); continue; }                    /* refuse flash ops unless the MODE jumper says PROG */
        gpio_put(PIN_LED, 1);
        if (c == 'C') { uint g = rd(); int r = fl_chip_erase(g, 0); if (!r && g) r = fl_chip_erase(g, 0x800000); r ? err(r) : ok(); }
        else if (c == 'S') { uint g = rd(); uint32_t a = rd32(); int r = fl_sector_erase(g, a); r ? err(r) : ok(); }
        else if (c == 'W') {
            uint g = rd(); uint32_t a = rd32(); uint16_t n = rd16();
            if (n > sizeof buf || (n & 31) || (a & 31)) { for (uint i = 0; i < n; i++) rd(); err(4); continue; }
            for (uint i = 0; i < n; i++) buf[i] = rd();
            int r = 0;
            for (uint off = 0; off < n && !r; off += 32) r = fl_wb_program(g, g == 0 ? (a + off) / 2 : a + off, buf + off, g == 0 ? 16 : 32);
            r ? err(r) : ok();
        }
        else if (c == 'R') {
            uint g = rd(); uint32_t a = rd32(); uint16_t n = rd16(); ok();
            for (uint i = 0; i < n; i += (g == 0 ? 2 : 1)) {
                uint32_t v = fl_read(g, g == 0 ? (a + i) / 2 : a + i);
                putchar_raw(v & 0xFF); if (g == 0) putchar_raw(v >> 8);
            }
        }
        else err(1);
        gpio_put(PIN_LED, 0);
    }
}
