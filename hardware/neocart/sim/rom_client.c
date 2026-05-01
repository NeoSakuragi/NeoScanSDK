/* ROM TCP client — MAME calls cart_read(), we send to rom_server.py */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <unistd.h>

static int sock = -1;

int cart_init(const char *unused) {
    (void)unused;
    sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) { perror("socket"); return -1; }

    int flag = 1;
    setsockopt(sock, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(flag));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(41114);
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("ROM_CLIENT: connect");
        sock = -1;
        return -1;
    }
    printf("ROM_CLIENT: connected to rom_server on port 41114\n");
    return 0;
}

uint16_t cart_read(uint32_t byte_addr) {
    if (sock < 0) return 0xFFFF;
    uint8_t buf[6];
    /* cmd=0x0001 (READ), addr high 16, addr low 16 */
    buf[0] = 0x00; buf[1] = 0x01;
    buf[2] = (byte_addr >> 24) & 0xFF;
    buf[3] = (byte_addr >> 16) & 0xFF;
    buf[4] = (byte_addr >> 8) & 0xFF;
    buf[5] = byte_addr & 0xFF;
    send(sock, buf, 6, 0);

    uint16_t word;
    recv(sock, &word, 2, MSG_WAITALL);
    return ntohs(word);
}

void cart_write(uint32_t byte_addr, uint16_t data) {
    if (sock < 0) return;
    uint8_t buf[8];
    buf[0] = 0x00; buf[1] = 0x02;
    buf[2] = (byte_addr >> 24) & 0xFF;
    buf[3] = (byte_addr >> 16) & 0xFF;
    buf[4] = (byte_addr >> 8) & 0xFF;
    buf[5] = byte_addr & 0xFF;
    buf[6] = (data >> 8) & 0xFF;
    buf[7] = data & 0xFF;
    send(sock, buf, 8, 0);

    uint16_t ack;
    recv(sock, &ack, 2, MSG_WAITALL);
}

void cart_reset(void) {}
void cart_destroy(void) { if (sock >= 0) close(sock); }
