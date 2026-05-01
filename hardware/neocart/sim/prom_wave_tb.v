`timescale 1ns / 1ps
module prom_wave_tb;
    reg clk=0, rst_n=0;
    reg [23:1] addr;
    reg [15:0] data_in;
    wire [15:0] data_out;
    reg as_n=1, romoe_n=1, rw_n=1;
    wire dtack_n;

    prom_cart #(.ROM_FILE("test_tiny.hex"), .ROM_WORDS(16)) dut (
        .clk(clk), .rst_n(rst_n), .addr(addr), .data_in(data_in),
        .data_out(data_out), .as_n(as_n), .romoe_n(romoe_n),
        .rw_n(rw_n), .dtack_n(dtack_n));

    always #10 clk = ~clk;

    initial begin
        $dumpfile("cart_waveform.vcd");
        $dumpvars(0, prom_wave_tb);

        // Reset
        #100; rst_n = 1; #20;

        // === Read cycle 1: address 0x000000 ===
        addr = 23'h0; rw_n = 1; as_n = 0; romoe_n = 0;
        #40;  // wait for data
        // data_out should be 0x0010
        as_n = 1; romoe_n = 1;
        #20;

        // === Read cycle 2: address 0x000002 ===
        addr = 23'h1; as_n = 0; romoe_n = 0;
        #40;
        as_n = 1; romoe_n = 1;
        #20;

        // === Read cycle 3: address 0x000004 ===
        addr = 23'h2; as_n = 0; romoe_n = 0;
        #40;
        as_n = 1; romoe_n = 1;
        #20;

        // === Bankswitch write: set bank to 1 ===
        addr = 24'h2FFFF0 >> 1; data_in = 16'h0001;
        rw_n = 0; as_n = 0;
        #40;
        as_n = 1; rw_n = 1;
        #20;

        // === Read from banked region ===
        addr = 24'h200000 >> 1; rw_n = 1; as_n = 0; romoe_n = 0;
        #40;
        as_n = 1; romoe_n = 1;
        #40;

        $finish;
    end
endmodule
