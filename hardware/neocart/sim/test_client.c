#include <stdio.h>
#include <stdint.h>
extern int cart_init(const char*);
extern uint16_t cart_read(uint32_t);
extern void cart_destroy(void);
int main() {
    if (cart_init("") < 0) { printf("CONNECT FAILED\n"); return 1; }
    printf("word[0x000000] = 0x%04X\n", cart_read(0x000000));
    printf("word[0x000002] = 0x%04X\n", cart_read(0x000002));
    printf("word[0x000004] = 0x%04X\n", cart_read(0x000004));
    cart_destroy();
    return 0;
}
