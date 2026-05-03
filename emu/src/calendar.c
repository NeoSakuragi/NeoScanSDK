#include "neogeo.h"
#include <time.h>

/* UPD4990A calendar chip — minimal implementation.
   The BIOS sends serial commands and reads back date/time bits.
   We just need to respond with valid data so the BIOS proceeds. */

static int cal_clk_prev;
static int cal_strobe_prev;
static int cal_cmd;
static int cal_cmd_bits;
static uint64_t cal_shift_reg;
static int cal_shift_pos;
static int cal_tp;
static int cal_tp_counter;

/* Pack current time into the 48-bit shift register format:
   seconds(7) minutes(7) hours(6) day(6) weekday(3) month(5) year(8) = 42 bits
   The BIOS reads these out serially via DATA_OUT. */
static uint64_t pack_time(void) {
    time_t t = time(NULL);
    struct tm *tm = localtime(&t);
    uint64_t v = 0;
    int sec = tm->tm_sec / 10 * 16 + tm->tm_sec % 10;  /* BCD */
    int min = tm->tm_min / 10 * 16 + tm->tm_min % 10;
    int hr  = tm->tm_hour / 10 * 16 + tm->tm_hour % 10;
    int day = tm->tm_mday / 10 * 16 + tm->tm_mday % 10;
    int wk  = tm->tm_wday;
    int mon = (tm->tm_mon + 1) / 10 * 16 + (tm->tm_mon + 1) % 10;
    int yr  = (tm->tm_year % 100) / 10 * 16 + (tm->tm_year % 100) % 10;

    /* LSB first in the shift register */
    v |= (uint64_t)(sec & 0x7F);
    v |= (uint64_t)(min & 0x7F) << 7;
    v |= (uint64_t)(hr  & 0x3F) << 14;
    v |= (uint64_t)(day & 0x3F) << 20;
    v |= (uint64_t)(wk  & 0x07) << 26;
    v |= (uint64_t)(mon & 0x1F) << 29;
    v |= (uint64_t)(yr  & 0xFF) << 34;
    return v;
}

void ng_cal_write(uint8_t data) {
    int din = data & 1;
    int clk = (data >> 1) & 1;
    int stb = (data >> 2) & 1;

    /* Initialize shift register on first call */
    static int inited;
    if (!inited) { cal_shift_reg = pack_time(); inited = 1; }

    /* Rising edge of STB: latch command and execute */
    if (stb && !cal_strobe_prev) {
        int cmd = cal_cmd & 0x0F;
        if (cmd == 0x01 || cmd == 0x03) {
            cal_shift_reg = pack_time();
            cal_shift_pos = 0;
        }
        cal_cmd_bits = 0;
        cal_cmd = 0;
    }

    /* Rising edge of CLK */
    if (clk && !cal_clk_prev) {
        if (stb) {
            /* Command mode: shift in command bit */
            cal_cmd = (cal_cmd >> 1) | (din << 3);
            cal_cmd_bits++;
        } else {
            /* Data mode: advance shift register output */
            cal_shift_pos++;
        }
    }

    cal_clk_prev = clk;
    cal_strobe_prev = stb;
}

uint8_t ng_cal_read(void) {
    return 0x40;  /* TP=1, DATA_OUT=0 */
}
