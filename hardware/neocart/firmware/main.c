/*
 * Neo Geo MVS Flash Cart — RP2040 Firmware
 *
 * USB CDC serial interface for programming 5 flash chips:
 *   P ROM  (AM29F400, 16-bit, byte-mode programming)
 *   S ROM  (SST39SF010, 8-bit)
 *   M ROM  (SST39SF010, 8-bit)
 *   C1 ROM (AM29F400, 16-bit, byte-mode programming)
 *   C2 ROM (AM29F400, 16-bit, byte-mode programming)
 *
 * Protocol (over USB CDC serial, 115200 baud):
 *   PC→Cart: "ERASE <chip>\n"          — erase entire chip
 *   PC→Cart: "PROG <chip> <len>\n"     — program <len> bytes, then send raw data
 *   PC→Cart: "VERIFY <chip> <len>\n"   — read back <len> bytes for verification
 *   PC→Cart: "DUMP <chip> <len>\n"     — read <len> bytes and stream to PC
 *   PC→Cart: "SCAN <chip> <len>\n"     — program + immediate read-back verify
 *   PC→Cart: "ID <chip>\n"             — read chip manufacturer/device ID
 *   PC→Cart: "PING\n"                  — returns "PONG\n"
 *
 *   <chip> = P | S | M | C1 | C2
 *
 *   Cart→PC: "OK\n"                    — success
 *   Cart→PC: "ERR <message>\n"         — error
 *   Cart→PC: "PROGRESS <pct>\n"        — progress update during long ops
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/binary_info.h"
#include "tusb.h"
#include "flash_programmer.h"

#define CMD_BUF_SIZE 64

static char cmd_buf[CMD_BUF_SIZE];
static int cmd_pos = 0;

static chip_id_t parse_chip(const char *s) {
    if (strcmp(s, "P") == 0)  return CHIP_P;
    if (strcmp(s, "S") == 0)  return CHIP_S;
    if (strcmp(s, "M") == 0)  return CHIP_M;
    if (strcmp(s, "C1") == 0) return CHIP_C1;
    if (strcmp(s, "C2") == 0) return CHIP_C2;
    if (strcmp(s, "V1") == 0) return CHIP_V1;
    if (strcmp(s, "V2") == 0) return CHIP_V2;
    if (strcmp(s, "V3") == 0) return CHIP_V3;
    if (strcmp(s, "V4") == 0) return CHIP_V4;
    return CHIP_INVALID;
}

static void send_response(const char *msg) {
    printf("%s\n", msg);
}

static void handle_ping(void) {
    send_response("PONG");
}

static void handle_id(const char *chip_str) {
    chip_id_t chip = parse_chip(chip_str);
    if (chip == CHIP_INVALID) {
        send_response("ERR invalid chip");
        return;
    }

    uint16_t mfr, dev;
    flash_read_id(chip, &mfr, &dev);
    printf("ID mfr=0x%04X dev=0x%04X\n", mfr, dev);
}

static void handle_erase(const char *chip_str) {
    chip_id_t chip = parse_chip(chip_str);
    if (chip == CHIP_INVALID) {
        send_response("ERR invalid chip");
        return;
    }

    send_response("PROGRESS 0");
    flash_chip_erase(chip);
    send_response("PROGRESS 100");
    send_response("OK");
}

static void handle_prog(const char *chip_str, uint32_t len) {
    chip_id_t chip = parse_chip(chip_str);
    if (chip == CHIP_INVALID) {
        send_response("ERR invalid chip");
        return;
    }

    send_response("READY");

    uint32_t addr = 0;
    uint32_t received = 0;
    uint8_t buf[256];
    int last_pct = -1;

    while (received < len) {
        uint32_t chunk = len - received;
        if (chunk > sizeof(buf)) chunk = sizeof(buf);

        uint32_t got = 0;
        while (got < chunk) {
            int c = getchar_timeout_us(1000000);
            if (c == PICO_ERROR_TIMEOUT) {
                send_response("ERR timeout");
                return;
            }
            buf[got++] = (uint8_t)c;
        }

        for (uint32_t i = 0; i < chunk; i++) {
            flash_program_byte(chip, addr++, buf[i]);
        }

        received += chunk;
        int pct = (int)((uint64_t)received * 100 / len);
        if (pct != last_pct && pct % 10 == 0) {
            printf("PROGRESS %d\n", pct);
            last_pct = pct;
        }
    }

    send_response("OK");
}

static void handle_verify(const char *chip_str, uint32_t len) {
    chip_id_t chip = parse_chip(chip_str);
    if (chip == CHIP_INVALID) {
        send_response("ERR invalid chip");
        return;
    }

    send_response("READY");

    for (uint32_t addr = 0; addr < len; addr++) {
        uint8_t val = flash_read_byte(chip, addr);
        putchar(val);
    }
}

static void handle_dump(const char *chip_str, uint32_t len) {
    chip_id_t chip = parse_chip(chip_str);
    if (chip == CHIP_INVALID) {
        send_response("ERR invalid chip");
        return;
    }

    printf("DUMP %u\n", len);

    uint8_t buf[256];
    uint32_t sent = 0;

    while (sent < len) {
        uint32_t chunk = len - sent;
        if (chunk > sizeof(buf)) chunk = sizeof(buf);

        for (uint32_t i = 0; i < chunk; i++) {
            buf[i] = flash_read_byte(chip, sent + i);
        }

        for (uint32_t i = 0; i < chunk; i++) {
            putchar(buf[i]);
        }

        sent += chunk;
    }
}

static void handle_scan(const char *chip_str, uint32_t len) {
    chip_id_t chip = parse_chip(chip_str);
    if (chip == CHIP_INVALID) {
        send_response("ERR invalid chip");
        return;
    }

    send_response("READY");

    uint32_t addr = 0;
    uint32_t received = 0;
    uint32_t mismatches = 0;
    uint32_t first_bad = 0xFFFFFFFF;
    uint8_t buf[256];

    while (received < len) {
        uint32_t chunk = len - received;
        if (chunk > sizeof(buf)) chunk = sizeof(buf);

        uint32_t got = 0;
        while (got < chunk) {
            int c = getchar_timeout_us(1000000);
            if (c == PICO_ERROR_TIMEOUT) {
                send_response("ERR timeout");
                return;
            }
            buf[got++] = (uint8_t)c;
        }

        for (uint32_t i = 0; i < chunk; i++) {
            flash_program_byte(chip, addr, buf[i]);

            uint8_t readback = flash_read_byte(chip, addr);
            if (readback != buf[i]) {
                mismatches++;
                if (first_bad == 0xFFFFFFFF) first_bad = addr;
            }
            addr++;
        }

        received += chunk;
        int pct = (int)((uint64_t)received * 100 / len);
        if (pct % 10 == 0) {
            printf("PROGRESS %d\n", pct);
        }
    }

    if (mismatches == 0) {
        send_response("SCAN OK 0");
    } else {
        printf("SCAN FAIL %u first=0x%06X\n", mismatches, first_bad);
    }
}

static void process_command(const char *cmd) {
    char arg1[8] = {0};
    uint32_t arg2 = 0;

    if (strcmp(cmd, "PING") == 0) {
        handle_ping();
    } else if (sscanf(cmd, "ID %7s", arg1) == 1) {
        handle_id(arg1);
    } else if (sscanf(cmd, "ERASE %7s", arg1) == 1) {
        handle_erase(arg1);
    } else if (sscanf(cmd, "PROG %7s %u", arg1, &arg2) == 2) {
        handle_prog(arg1, arg2);
    } else if (sscanf(cmd, "VERIFY %7s %u", arg1, &arg2) == 2) {
        handle_verify(arg1, arg2);
    } else if (sscanf(cmd, "DUMP %7s %u", arg1, &arg2) == 2) {
        handle_dump(arg1, arg2);
    } else if (sscanf(cmd, "SCAN %7s %u", arg1, &arg2) == 2) {
        handle_scan(arg1, arg2);
    } else {
        send_response("ERR unknown command");
    }
}

int main(void) {
    stdio_init_all();
    flash_programmer_init();

    while (true) {
        int c = getchar_timeout_us(100000);
        if (c == PICO_ERROR_TIMEOUT) continue;

        if (c == '\n' || c == '\r') {
            if (cmd_pos > 0) {
                cmd_buf[cmd_pos] = '\0';
                process_command(cmd_buf);
                cmd_pos = 0;
            }
        } else if (cmd_pos < CMD_BUF_SIZE - 1) {
            cmd_buf[cmd_pos++] = (char)c;
        }
    }

    return 0;
}
