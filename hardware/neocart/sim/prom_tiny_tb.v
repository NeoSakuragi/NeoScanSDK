`timescale 1ns / 1ps
module prom_tiny_tb;
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
        #100; rst_n = 1; #20;

        // Read word at 0x000000
        addr = 23'h0; rw_n = 1; as_n = 0; romoe_n = 0;
        #40;
        $display("P1[0x000000] = 0x%04X (expect 0x0010)", data_out);

        // Read word at 0x000002
        addr = 23'h1; #40;
        $display("P1[0x000002] = 0x%04X (expect 0xF300)", data_out);

        // Read word at 0x000004
        addr = 23'h2; #40;
        $display("P1[0x000004] = 0x%04X (expect 0x00C0)", data_out);

        as_n = 1; romoe_n = 1;
        $display("=== DONE ===");
        $finish;
    end
endmodule
