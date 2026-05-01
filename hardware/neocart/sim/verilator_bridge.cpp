// Verilator bridge — wraps prom_cart Verilog model for MAME integration
// Compiles to a shared library that MAME's custom build can dlopen()
//
// API:
//   cart_init(rom_hex_file) — load ROM and initialize model
//   cart_read(addr) → data  — read a word from the cart
//   cart_write(addr, data)  — write (bankswitch)
//   cart_reset()            — reset the model

#include "Vprom_cart.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>

static Vprom_cart *cart = nullptr;
static vluint64_t sim_time = 0;

static void tick() {
    cart->clk = 0;
    cart->eval();
    sim_time++;
    cart->clk = 1;
    cart->eval();
    sim_time++;
}

extern "C" {

int cart_init(const char *rom_file) {
    // Verilator needs the ROM file path set via plusargs or parameter
    // For now, the ROM file is compiled into the model via ROM_FILE parameter
    const char *empty[] = {nullptr};
    Verilated::commandArgs(0, empty);
    cart = new Vprom_cart;

    // Reset
    cart->rst_n = 0;
    cart->as_n = 1;
    cart->romoe_n = 1;
    cart->rw_n = 1;
    for (int i = 0; i < 4; i++) tick();
    cart->rst_n = 1;
    tick();

    printf("VERILATOR: cart initialized\n");
    return 0;
}

uint16_t cart_read(uint32_t byte_addr) {
    cart->addr = byte_addr >> 1;  // word address (addr[23:1])
    cart->rw_n = 1;
    cart->as_n = 0;
    cart->romoe_n = 0;
    tick();
    uint16_t data = cart->data_out;
    cart->as_n = 1;
    cart->romoe_n = 1;
    return data;
}

void cart_write(uint32_t byte_addr, uint16_t data) {
    cart->addr = byte_addr >> 1;
    cart->data_in = data;
    cart->rw_n = 0;
    cart->as_n = 0;
    cart->romoe_n = 1;
    tick();
    cart->as_n = 1;
    cart->rw_n = 1;
}

void cart_reset() {
    if (!cart) return;
    cart->rst_n = 0;
    for (int i = 0; i < 4; i++) tick();
    cart->rst_n = 1;
    tick();
}

void cart_destroy() {
    if (cart) { delete cart; cart = nullptr; }
}

} // extern "C"

// Standalone test
#ifndef NO_MAIN
int main(int argc, char **argv) {
    cart_init("rbff2_prom.hex");

    printf("Read test:\n");
    printf("  [0x000000] = 0x%04X (expect 0x0010)\n", cart_read(0x000000));
    printf("  [0x000002] = 0x%04X (expect 0xF300)\n", cart_read(0x000002));
    printf("  [0x000004] = 0x%04X (expect 0x00C0)\n", cart_read(0x000004));

    // Test bankswitch
    printf("\nBankswitch test:\n");
    printf("  P2 bank 0 [0x200000] = 0x%04X\n", cart_read(0x200000));
    cart_write(0x2FFFF0, 1);  // switch to bank 1
    printf("  P2 bank 1 [0x200000] = 0x%04X\n", cart_read(0x200000));
    cart_write(0x2FFFF0, 2);  // switch to bank 2
    printf("  P2 bank 2 [0x200000] = 0x%04X\n", cart_read(0x200000));

    cart_destroy();
    printf("\nDone.\n");
    return 0;
}
#endif
