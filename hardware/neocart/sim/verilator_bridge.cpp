// Verilator bridge — wraps prom_cart Verilog model for MAME integration
#include "Vprom_cart.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>

static Vprom_cart *cart = nullptr;
static vluint64_t sim_time = 0;
static uint64_t read_total = 0;

static void tick() {
    cart->clk = 0; cart->eval(); sim_time++;
    cart->clk = 1; cart->eval(); sim_time++;
}

extern "C" {

int cart_init(const char *rom_file) {
    const char *empty[] = {nullptr};
    Verilated::commandArgs(0, empty);
    cart = new Vprom_cart;
    cart->rst_n = 0; cart->as_n = 1; cart->romoe_n = 1; cart->rw_n = 1;
    for (int i = 0; i < 4; i++) tick();
    cart->rst_n = 1; tick();
    read_total = 0;
    printf("VERILATOR: cart initialized\n");
    return 0;
}

uint16_t cart_read(uint32_t byte_addr) {
    cart->addr = byte_addr >> 1;
    cart->rw_n = 1; cart->as_n = 0; cart->romoe_n = 0;
    tick();
    uint16_t data = cart->data_out;
    cart->as_n = 1; cart->romoe_n = 1;
    read_total++;
    if (read_total % 5000000 == 0)
        printf("VERILATOR: %luM reads\n", read_total / 1000000);
    return data;
}

void cart_write(uint32_t byte_addr, uint16_t data) {
    cart->addr = byte_addr >> 1;
    cart->data_in = data; cart->rw_n = 0; cart->as_n = 0; cart->romoe_n = 1;
    tick();
    cart->as_n = 1; cart->rw_n = 1;
}

void cart_reset() {
    if (!cart) return;
    cart->rst_n = 0;
    for (int i = 0; i < 4; i++) tick();
    cart->rst_n = 1; tick();
}

void cart_destroy() {
    if (cart) { delete cart; cart = nullptr; }
}

} // extern "C"

#ifndef NO_MAIN
int main(int argc, char **argv) {
    cart_init("");
    printf("  [0x000000] = 0x%04X (expect 0x0010)\n", cart_read(0x000000));
    printf("  [0x000002] = 0x%04X (expect 0xF300)\n", cart_read(0x000002));
    printf("  [0x40DC]   = 0x%04X (expect 0x9841 if modified)\n", cart_read(0x40DC));
    cart_destroy();
    return 0;
}
#endif
