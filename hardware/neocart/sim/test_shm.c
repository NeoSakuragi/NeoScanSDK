#include <stdio.h>
#include <stdint.h>
extern int cart_init(const char*);
extern uint16_t cart_read(uint32_t);
int main() {
    if (cart_init("") < 0) { printf("FAILED\n"); return 1; }
    uint16_t w0 = cart_read(0x000000);
    uint16_t w1 = cart_read(0x000002);
    uint16_t w2 = cart_read(0x000004);
    printf("0x%04X 0x%04X 0x%04X\n", w0, w1, w2);
    printf("%s\n", (w0 == 0x0010 && w1 == 0xF300 && w2 == 0x00C0) ? "CORRECT" : "WRONG BYTE ORDER");
    return 0;
}
