/* NeoCart programmer v1 firmware (WeAct RP2350B core board). The board plays the console for an MVS PROG board in its slot.
 * Binary protocol over USB CDC. GPIO map = ../design.py GPIO_NET; every cycle below is the one sim_system.py runs
 * against the PROG board netlist (System.p_write, p_read, bank_write, ym_addr, v_read, v_write, power_on).
 *
 *   GPIO0-15   MD0-15     internal bus: U5 (D0-D15), U6 (SDRAD = MD0-7, SDPAD = MD8-15), latch inputs U10/U11
 *   GPIO26-40  strobes    RW nAS nROMOE nROMOEU nROMOEL nPORTOEU nPORTOEL nPORTWEU nPORTWEL nPORTADRS SDRMPX nSDROE SDPMPX nSDPOE CLK68K
 *   GPIO16-19  inputs     /ROMWAIT /PWAIT0 /PWAIT1 /PDTACK (cart outputs, 5 V tolerant pins, 1k series)
 *   GPIO20 XDIR (1 = programmer drives the cart)   21 /OE_D   22 /OE_VA   24 /OE_VB   41 /OE_OUT (strobes + latched lines)
 *   GPIO42 LCLK1 (A1-A16)   43 LCLK2 (A17-19, SDRA8/9/20-23, SDPA8-11, /RESET, 4 MHz, /SLOTCS)
 *   GPIO44 VCART_EN   45 /VCART_FAULT   46 VCART_SENSE (ADC6, 5 V -> 2.5 V)
 *   GPIO25 LED and GPIO23 KEY are on the WeAct module itself (KEY = start a flash of the last image, future use)
 *
 * Rules (each one is a scenario in sim_system.py):
 *   - MD0-15 are released BEFORE any transceiver turns toward the MCU (XDIR = 0 with an /OE low): no bus fight.
 *   - Power-up: strobes idle and latches loaded with every /OE high, then VCART on, then /OE_OUT low.
 *   - The 16T245 B ports are powered by VCART: with the cart off nothing reaches the slot.
 *
 * Flash groups: 0 = P (S29GL064N, word mode, 22-bit word address: MB 7 = P1 window, MB n = P2 bank n),
 *               1 = V (S29GL128P, byte mode, 24-bit byte address = YM2610 address; written through ADPCM-A).
 * Protocol (little-endian). Host: 1 command byte + args. Device: 'K' + payload, or 'E' + code.
 *   'I'                        -> K ver proto vcart fault inputs(1) vsense_mV(2) | P: mfr(2) id1(2) id2(2) id3(2) | V: mfr dev1 dev2 dev3 (1 each)
 *   'P' on                     -> K   cart power (0/1); 'E' 6 if the switch reports a fault
 *   'C' g                      -> K   chip erase (minutes)
 *   'S' g addr(4)              -> K   sector erase containing addr (flash units: words for P, bytes for V)
 *   'W' g addr(4) len(2) data  -> K   write-buffer program, len bytes (<= 4096, addr/len aligned to the buffer: 32 B)
 *   'R' g addr(4) len(2) bus   -> K + len bytes (bus: 0 = ADPCM-A, 1 = ADPCM-B; ignored for P)
 *   raw cycles for bench tests and agentic debugging:
 *   'L' which value(2)         -> K   load latch 1 or 2
 *   'G' mask(2) value(2)       -> K   set strobe GPIOs (bit i = STROBES[i])
 *   'T' what                   -> K + 2 bytes: 0 = read D0-D15 (U5), 1 = read SDRAD/SDPAD (U6 both halves)
 *   'O' value(2)               -> K   drive D0-D15 with value (XDIR = 1, /OE_D low) until the next 'T' or 'Z'
 *   'Z'                        -> K   release every bus toward the cart (all /OE high, MD inputs)
 */
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/adc.h"

#define VERSION 1
#define PROTO 2
enum { S_RW, S_AS, S_ROMOE, S_ROMOEU, S_ROMOEL, S_PORTOEU, S_PORTOEL, S_PORTWEU, S_PORTWEL, S_PORTADRS,
       S_SDRMPX, S_SDROE, S_SDPMPX, S_SDPOE, S_CLK68K };
#define STROBE_BASE 26
#define INPUT_BASE 16
#define PIN_XDIR 20
#define PIN_OE_D 21
#define PIN_OE_VA 22
#define PIN_OE_VB 24
#define PIN_OE_OUT 41
#define PIN_LCLK1 42
#define PIN_LCLK2 43
#define PIN_VCART_EN 44
#define PIN_FAULT 45
#define PIN_VSENSE 46
#define PIN_LED 25
#define PIN_KEY 23
#define MD_MASK 0xFFFFu
/* latch 2 bit positions = design.LAT2 order */
enum { L2_A17, L2_A18, L2_A19, L2_SDRA8, L2_SDRA9, L2_SDRA20, L2_SDRA21, L2_SDRA22, L2_SDRA23,
       L2_SDPA8, L2_SDPA9, L2_SDPA10, L2_SDPA11, L2_RESET, L2_CLK4M, L2_SLOTCS };

static uint16_t lat2;
static inline void settle(void) { busy_wait_us_32(1); }            /* PROGRAMMING.md: >= 1 us per phase, every part >= 10x faster */

/* ---- internal bus ------------------------------------------------------------------------------------------ */
static void md_release(void) { gpio_set_dir_masked(MD_MASK, 0); }
static void md_drive(uint16_t v) { gpio_put_masked(MD_MASK, v); gpio_set_dir_masked(MD_MASK, MD_MASK); }
static uint16_t md_get(void) { return gpio_get_all() & MD_MASK; }
static void strobe(uint s, bool v) { gpio_put(STROBE_BASE + s, v); }
static void latch(uint which, uint16_t v) {
    uint clk = which == 1 ? PIN_LCLK1 : PIN_LCLK2;
    md_drive(v); settle(); gpio_put(clk, 1); settle(); gpio_put(clk, 0);
    if (which == 2) lat2 = v;
}
static void lat2_bit(uint b, bool v) { latch(2, v ? (lat2 | (1u << b)) : (lat2 & ~(1u << b))); }
static void address(uint32_t word) {                                  /* 68K word address A1-A19 */
    latch(1, word & 0xFFFF);
    uint16_t l = lat2 & ~7u; l |= (word >> 16) & 7; latch(2, l);
}

/* ---- data paths (the release-first rule lives here) --------------------------------------------------------- */
static void data_out(uint16_t v) { md_drive(v); gpio_put(PIN_XDIR, 1); gpio_put(PIN_OE_D, 0); settle(); }
static void data_release(void) { gpio_put(PIN_OE_D, 1); gpio_put(PIN_XDIR, 0); md_release(); settle(); }
static uint16_t data_in(void) {
    md_release(); gpio_put(PIN_XDIR, 0); gpio_put(PIN_OE_D, 0); settle();
    uint16_t v = md_get(); gpio_put(PIN_OE_D, 1); return v;
}

/* ---- power ------------------------------------------------------------------------------------------------- */
static bool powered;
static void all_off(void) {
    gpio_put(PIN_OE_OUT, 1); gpio_put(PIN_OE_D, 1); gpio_put(PIN_OE_VA, 1); gpio_put(PIN_OE_VB, 1);
    gpio_put(PIN_XDIR, 0); md_release();
}
static int power(bool on) {
    all_off();
    if (!on) { gpio_put(PIN_VCART_EN, 0); powered = false; return 0; }
    for (uint s = 0; s <= S_CLK68K; s++) strobe(s, !(s == S_SDRMPX || s == S_SDPMPX || s == S_CLK68K));   /* idle levels */
    lat2 = (1u << L2_SLOTCS);                                          /* /RESET low, /SLOTCS high */
    address(0);
    gpio_put(PIN_VCART_EN, 1); sleep_ms(20);
    if (!gpio_get(PIN_FAULT)) { gpio_put(PIN_VCART_EN, 0); return 6; }
    gpio_put(PIN_OE_OUT, 0); settle();
    lat2_bit(L2_RESET, 1);                                            /* release /RESET: bank latch cleared */
    powered = true; return 0;
}
static uint16_t vsense_mv(void) { adc_select_input(PIN_VSENSE - 40);   /* ADC input n = GPIO40+n on the RP2350B */ return (uint32_t)adc_read() * 3300 * 2 / 4096; }

/* ---- 68K cycles ---------------------------------------------------------------------------------------------- */
static void p_write(uint32_t word, uint16_t v, bool p2) {
    address(word);
    if (p2) strobe(S_PORTADRS, 0);
    strobe(S_RW, 0); data_out(v); strobe(S_PORTWEU, 0); settle(); strobe(S_PORTWEU, 1); settle();
    data_release(); strobe(S_RW, 1); strobe(S_PORTADRS, 1);
}
static uint16_t p_read(uint32_t word, bool p2) {
    address(word);
    if (p2) { strobe(S_PORTADRS, 0); strobe(S_PORTOEL, 0); strobe(S_PORTOEU, 0); } else strobe(S_ROMOE, 0);
    uint16_t v = data_in();
    strobe(S_ROMOE, 1); strobe(S_PORTOEL, 1); strobe(S_PORTOEU, 1); strobe(S_PORTADRS, 1);
    return v;
}
static int bank_cur = -1;
static void bank_write(uint n) {
    address(0x7FFF8); strobe(S_PORTADRS, 0); strobe(S_RW, 0); data_out(n);
    strobe(S_PORTWEL, 0); settle(); strobe(S_PORTWEL, 1); settle(); data_release(); strobe(S_RW, 1); strobe(S_PORTADRS, 1);
    bank_cur = n;
}
/* P flash word address fa (22 bits): MB 7 is the P1 window, MB n (0..6) is P2 bank n */
static void pf_write(uint32_t fa, uint16_t v) {
    uint mb = fa >> 19;
    if (mb == 7) p_write(fa & 0x7FFFF, v, false);
    else { if (bank_cur != (int)mb) bank_write(mb); p_write(fa & 0x7FFFF, v, true); }
}
static uint16_t pf_read(uint32_t fa) {
    uint mb = fa >> 19;
    if (mb == 7) return p_read(fa & 0x7FFFF, false);
    if (bank_cur != (int)mb) bank_write(mb);
    return p_read(fa & 0x7FFFF, true);
}

/* ---- YM2610 sample cycles -------------------------------------------------------------------------------------- */
static void ym_addr(uint bus, uint32_t a) {
    if (bus == 0) {
        uint16_t l = lat2 & ~((1u << L2_SDRA8) | (1u << L2_SDRA9) | (0xFu << L2_SDRA20));
        latch(2, l | (((a >> 8) & 1) << L2_SDRA8) | (((a >> 9) & 1) << L2_SDRA9));
        md_drive(a & 0xFF); gpio_put(PIN_XDIR, 1); gpio_put(PIN_OE_VA, 0); settle(); strobe(S_SDRMPX, 1); settle();
        gpio_put(PIN_OE_VA, 1);
        l = lat2 & ~((1u << L2_SDRA8) | (1u << L2_SDRA9) | (0xFu << L2_SDRA20));
        latch(2, l | (((a >> 18) & 1) << L2_SDRA8) | (((a >> 19) & 1) << L2_SDRA9) | (((a >> 20) & 0xF) << L2_SDRA20));
        md_drive((a >> 10) & 0xFF); gpio_put(PIN_OE_VA, 0); settle(); strobe(S_SDRMPX, 0); settle();
        gpio_put(PIN_OE_VA, 1);
    } else {
        uint16_t l = lat2 & ~(0xFu << L2_SDPA8);
        latch(2, l | (((a >> 8) & 0xF) << L2_SDPA8));
        md_drive((a & 0xFF) << 8); gpio_put(PIN_XDIR, 1); gpio_put(PIN_OE_VB, 0); settle(); strobe(S_SDPMPX, 1); settle();
        gpio_put(PIN_OE_VB, 1);
        latch(2, (lat2 & ~(0xFu << L2_SDPA8)) | (((a >> 20) & 0xF) << L2_SDPA8));
        md_drive(((a >> 12) & 0xFF) << 8); gpio_put(PIN_OE_VB, 0); settle(); strobe(S_SDPMPX, 0); settle();
        gpio_put(PIN_OE_VB, 1);
    }
    gpio_put(PIN_XDIR, 0); md_release(); settle();
}
static uint8_t v_read(uint bus, uint32_t a) {
    ym_addr(bus, a);
    uint oe = bus ? PIN_OE_VB : PIN_OE_VA, st = bus ? S_SDPOE : S_SDROE;
    strobe(st, 0); md_release(); gpio_put(PIN_XDIR, 0); gpio_put(oe, 0); settle();
    uint16_t v = md_get(); gpio_put(oe, 1); strobe(st, 1);
    return bus ? v >> 8 : v & 0xFF;
}
static void v_write(uint32_t a, uint8_t d) {                           /* ADPCM-A path, /ROMOEU = V flash /WE */
    ym_addr(0, a);
    strobe(S_RW, 0); md_drive(d); gpio_put(PIN_XDIR, 1); gpio_put(PIN_OE_VA, 0); settle();
    strobe(S_ROMOEU, 0); settle(); strobe(S_ROMOEU, 1); settle();
    gpio_put(PIN_OE_VA, 1); gpio_put(PIN_XDIR, 0); md_release(); settle(); strobe(S_RW, 1);
}

/* ---- flash (S29GL064N word mode / S29GL128P byte mode, datasheet command tables) ----------------------------- */
static void fw(uint g, uint32_t a, uint16_t v) { if (g == 0) pf_write(a, v); else v_write(a, v); }
static uint16_t fr(uint g, uint32_t a) { return g == 0 ? pf_read(a) : v_read(0, a); }
/* command addresses only decode the low bits: issue them in the window the data address uses (P: MB 7 or the bank) */
static uint32_t ua1(uint g, uint32_t base) { return base | (g == 0 ? 0x555 : 0xAAA); }
static uint32_t ua2(uint g, uint32_t base) { return base | (g == 0 ? 0x2AA : 0x555); }
static uint32_t win(uint g, uint32_t a) { return g == 0 ? (a & ~0x7FFFFu) : 0; }
static void f_reset(uint g, uint32_t a) { fw(g, win(g, a), 0xF0); }
static int f_wait(uint g, uint32_t a, uint16_t expect, uint32_t timeout_ms) {          /* DQ7 data polling, DQ5 timeout */
    absolute_time_t t0 = get_absolute_time();
    for (;;) {
        uint16_t v = fr(g, a);
        if ((v & 0x80) == (expect & 0x80)) return 0;
        if (v & 0x20) { v = fr(g, a); if ((v & 0x80) == (expect & 0x80)) return 0; f_reset(g, a); return 2; }
        if (absolute_time_diff_us(t0, get_absolute_time()) > (int64_t)timeout_ms * 1000) { f_reset(g, a); return 3; }
        gpio_xor_mask64(1ull << PIN_LED);
    }
}
static void f_id(uint g, uint16_t id[4]) {
    uint32_t b = win(g, 7u << 19);
    fw(g, ua1(g, b), 0xAA); fw(g, ua2(g, b), 0x55); fw(g, ua1(g, b), 0x90);
    if (g == 0) { id[0] = fr(g, b + 0); id[1] = fr(g, b + 1); id[2] = fr(g, b + 0xE); id[3] = fr(g, b + 0xF); }
    else { id[0] = fr(g, 0); id[1] = fr(g, 2); id[2] = fr(g, 0x1C); id[3] = fr(g, 0x1E); }
    f_reset(g, b);
}
static int f_chip_erase(uint g) {
    uint32_t b = win(g, 7u << 19);
    fw(g, ua1(g, b), 0xAA); fw(g, ua2(g, b), 0x55); fw(g, ua1(g, b), 0x80);
    fw(g, ua1(g, b), 0xAA); fw(g, ua2(g, b), 0x55); fw(g, ua1(g, b), 0x10);
    return f_wait(g, b, 0xFF, 600000);
}
static int f_sector_erase(uint g, uint32_t a) {
    uint32_t b = win(g, a);
    fw(g, ua1(g, b), 0xAA); fw(g, ua2(g, b), 0x55); fw(g, ua1(g, b), 0x80);
    fw(g, ua1(g, b), 0xAA); fw(g, ua2(g, b), 0x55); fw(g, a, 0x30);
    return f_wait(g, a, 0xFF, 10000);
}
static int f_buffer(uint g, uint32_t a, const uint8_t *d, uint n) {     /* n units: 16 words (P) or 32 bytes (V) */
    uint32_t b = win(g, a);
    fw(g, ua1(g, b), 0xAA); fw(g, ua2(g, b), 0x55); fw(g, a, 0x25); fw(g, a, n - 1);
    uint16_t last = 0;
    for (uint i = 0; i < n; i++) { last = g == 0 ? (d[2 * i] << 8 | d[2 * i + 1]) : d[i]; fw(g, a + i, last); }   /* P image: big-endian 68K words */
    fw(g, a, 0x29);
    return f_wait(g, a + n - 1, last, 100);
}

/* ---- protocol ---------------------------------------------------------------------------------------------------- */
static int rd(void) { int c; while ((c = getchar_timeout_us(1000000)) == PICO_ERROR_TIMEOUT) {} return c; }
static uint32_t rd32(void) { uint32_t v = rd(); v |= rd() << 8; v |= rd() << 16; v |= (uint32_t)rd() << 24; return v; }
static uint16_t rd16(void) { uint16_t v = rd(); v |= rd() << 8; return v; }
static void put16(uint16_t v) { putchar_raw(v & 0xFF); putchar_raw(v >> 8); }
static void ok(void) { putchar_raw('K'); }
static void err(int e) { putchar_raw('E'); putchar_raw(e); }

int main(void) {
    stdio_init_all();
    for (uint p = 0; p < 16; p++) { gpio_init(p); gpio_set_dir(p, GPIO_IN); }                   /* MD0-15 */
    for (uint p = INPUT_BASE; p < INPUT_BASE + 4; p++) { gpio_init(p); gpio_set_dir(p, GPIO_IN); }
    for (uint p = STROBE_BASE; p <= STROBE_BASE + S_CLK68K; p++) { gpio_init(p); gpio_set_dir(p, GPIO_OUT); gpio_put(p, 1); }
    static const uint outs[] = {PIN_XDIR, PIN_OE_D, PIN_OE_VA, PIN_OE_VB, PIN_OE_OUT, PIN_LCLK1, PIN_LCLK2, PIN_VCART_EN, PIN_LED};
    for (uint i = 0; i < sizeof outs / sizeof outs[0]; i++) { gpio_init(outs[i]); gpio_set_dir(outs[i], GPIO_OUT); }
    gpio_init(PIN_FAULT); gpio_set_dir(PIN_FAULT, GPIO_IN); gpio_init(PIN_KEY); gpio_set_dir(PIN_KEY, GPIO_IN);
    adc_init(); adc_gpio_init(PIN_VSENSE);
    gpio_put(PIN_VCART_EN, 0); gpio_put(PIN_LCLK1, 0); gpio_put(PIN_LCLK2, 0); all_off();
    static uint8_t buf[4096];
    for (;;) {
        int c = getchar_timeout_us(100000);
        if (c == PICO_ERROR_TIMEOUT) { gpio_put(PIN_LED, 0); continue; }
        gpio_put(PIN_LED, 1);
        if (c == 'I') {
            ok(); putchar_raw(VERSION); putchar_raw(PROTO); putchar_raw(powered); putchar_raw(!gpio_get(PIN_FAULT));
            putchar_raw((gpio_get_all() >> INPUT_BASE) & 0xF); put16(vsense_mv());
            uint16_t id[4] = {0};
            for (uint g = 0; g < 2; g++) {
                if (powered) f_id(g, id);
                for (int i = 0; i < 4; i++) { if (g == 0) put16(id[i]); else putchar_raw(id[i] & 0xFF); }
            }
            continue;
        }
        if (c == 'P') { int r = power(rd()); r ? err(r) : ok(); continue; }
        if (c == 'Z') { all_off(); ok(); continue; }
        if (!powered) { err(7); continue; }                            /* everything below needs a powered cart */
        if (c == 'C') { int r = f_chip_erase(rd()); r ? err(r) : ok(); }
        else if (c == 'S') { uint g = rd(); uint32_t a = rd32(); int r = f_sector_erase(g, a); r ? err(r) : ok(); }
        else if (c == 'W') {
            uint g = rd(); uint32_t a = rd32(); uint16_t n = rd16();
            if (n > sizeof buf || (n & 31) || (a & (g == 0 ? 15 : 31))) { for (uint i = 0; i < n; i++) rd(); err(4); continue; }
            for (uint i = 0; i < n; i++) buf[i] = rd();
            int r = 0;
            for (uint off = 0; off < n && !r; off += 32) {
                bool blank = true; for (uint i = 0; i < 32; i++) blank &= buf[off + i] == 0xFF;
                if (!blank) r = f_buffer(g, g == 0 ? a + off / 2 : a + off, buf + off, g == 0 ? 16 : 32);
            }
            r ? err(r) : ok();
        }
        else if (c == 'R') {
            uint g = rd(); uint32_t a = rd32(); uint16_t n = rd16(); uint bus = rd(); ok();
            for (uint i = 0; i < n; i += (g == 0 ? 2 : 1)) {
                if (g == 0) { uint16_t v = pf_read(a + i / 2); putchar_raw(v >> 8); putchar_raw(v & 0xFF); }
                else putchar_raw(v_read(bus, a + i));
            }
        }
        else if (c == 'L') { uint w = rd(); latch(w, rd16()); md_release(); ok(); }
        else if (c == 'G') { uint16_t m = rd16(), v = rd16(); gpio_put_masked64((uint64_t)m << STROBE_BASE, (uint64_t)v << STROBE_BASE); ok(); }   /* strobes span GPIO26-40: 64-bit mask */
        else if (c == 'O') { uint16_t v = rd16(); strobe(S_RW, 0); data_out(v); ok(); }
        else if (c == 'T') {
            uint w = rd(); md_release(); gpio_put(PIN_OE_D, 1); gpio_put(PIN_XDIR, 0);
            if (w == 0) { ok(); put16(data_in()); }
            else { gpio_put(PIN_OE_VA, 0); gpio_put(PIN_OE_VB, 0); settle(); uint16_t v = md_get(); gpio_put(PIN_OE_VA, 1); gpio_put(PIN_OE_VB, 1); ok(); put16(v); }
        }
        else err(1);
    }
}
