// TCP client for Digital simulator — replaces ROM buffer in MAME
// Connects to Digital's CLI serve on port 41114
// Provides cart_read() that sends set:ADDR + measure over TCP

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

static int sock = -1;

static void send_cmd(const char *cmd) {
    uint16_t len = htons(strlen(cmd));
    send(sock, &len, 2, 0);
    send(sock, cmd, strlen(cmd), 0);
}

static char* recv_resp(void) {
    static char buf[4096];
    uint16_t len;
    recv(sock, &len, 2, MSG_WAITALL);
    len = ntohs(len);
    recv(sock, buf, len, MSG_WAITALL);
    buf[len] = 0;
    return buf;
}

int cart_init(const char *unused) {
    sock = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in addr = {
        .sin_family = AF_INET,
        .sin_port = htons(41114),
        .sin_addr.s_addr = inet_addr("127.0.0.1")
    };
    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("DIGITAL_CART: connect failed");
        return -1;
    }
    // Enable CS
    send_cmd("set:CS=1");
    recv_resp();
    printf("DIGITAL_CART: connected to Digital simulator on port 41114\n");
    return 0;
}

uint16_t cart_read(uint32_t byte_addr) {
    uint32_t word_addr = byte_addr / 2;
    char cmd[64];
    snprintf(cmd, sizeof(cmd), "set:ADDR=%u", word_addr);
    send_cmd(cmd);
    recv_resp();

    send_cmd("measure");
    char *resp = recv_resp();

    // Parse DATA value from: ok:{"ADDR":...,"CS":...,"DATA":12345}
    char *p = strstr(resp, "\"DATA\":");
    if (!p) return 0xFFFF;
    return (uint16_t)atoi(p + 7);
}

void cart_write(uint32_t byte_addr, uint16_t data) {
    // For bankswitch — not implemented in simple ROM circuit
    (void)byte_addr;
    (void)data;
}

void cart_reset(void) {}
void cart_destroy(void) {
    if (sock >= 0) close(sock);
}
