// Testbench for prom_cart — verifies ROM read + bankswitching
`timescale 1ns / 1ps

module prom_cart_tb;
    reg         clk = 0;
    reg         rst_n = 0;
    reg  [23:1] addr;
    reg  [15:0] data_in;
    wire [15:0] data_out;
    reg         as_n = 1;
    reg         romoe_n = 1;
    reg         rw_n = 1;
    wire        dtack_n;

    prom_cart #(
        .ROM_FILE("rbff2_prom.hex"),
        .ROM_WORDS(2621440)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .addr(addr), .data_in(data_in), .data_out(data_out),
        .as_n(as_n), .romoe_n(romoe_n), .rw_n(rw_n),
        .dtack_n(dtack_n)
    );

    always #10 clk = ~clk;  // 50MHz

    // Read a word from the cart
    task read_word(input [23:0] byte_addr, output [15:0] result);
        begin
            addr = byte_addr[23:1];
            rw_n = 1;
            as_n = 0;
            romoe_n = 0;
            @(posedge clk);
            @(posedge clk);
            result = data_out;
            as_n = 1;
            romoe_n = 1;
            @(posedge clk);
        end
    endtask

    // Write to bankswitch register
    task write_bank(input [2:0] bank_num);
        begin
            addr = 24'h2FFFF0 >> 1;
            data_in = {13'b0, bank_num};
            rw_n = 0;
            as_n = 0;
            romoe_n = 1;
            @(posedge clk);
            @(posedge clk);
            as_n = 1;
            rw_n = 1;
            @(posedge clk);
        end
    endtask

    reg [15:0] result;
    integer pass_count = 0;
    integer fail_count = 0;

    task check(input [23:0] byte_addr, input [15:0] expected, input [79:0] label);
        begin
            read_word(byte_addr, result);
            if (result === expected) begin
                $display("PASS: %s addr=0x%06X got=0x%04X", label, byte_addr, result);
                pass_count = pass_count + 1;
            end else begin
                $display("FAIL: %s addr=0x%06X expected=0x%04X got=0x%04X",
                         label, byte_addr, expected, result);
                fail_count = fail_count + 1;
            end
        end
    endtask

    initial begin
        $dumpfile("prom_cart_tb.vcd");
        $dumpvars(0, prom_cart_tb);

        // Reset
        rst_n = 0;
        #100;
        rst_n = 1;
        #20;

        // Test P1 reads (first 1MB)
        // RB2 P-ROM word[0] = 0x0010 (68K initial SP high word)
        check(24'h000000, 16'h0010, "P1[0x000000]");
        check(24'h000002, 16'hF300, "P1[0x000002]");

        // Test P2 bank 0 (offset 0x100000 in ROM = bank 0 at 0x200000)
        write_bank(3'd0);
        read_word(24'h200000, result);
        $display("INFO: P2 bank0 [0x200000] = 0x%04X", result);

        // Test P2 bank 1
        write_bank(3'd1);
        read_word(24'h200000, result);
        $display("INFO: P2 bank1 [0x200000] = 0x%04X", result);

        // Test P2 bank 2
        write_bank(3'd2);
        read_word(24'h200000, result);
        $display("INFO: P2 bank2 [0x200000] = 0x%04X", result);

        // Summary
        $display("");
        $display("=== %0d PASS, %0d FAIL ===", pass_count, fail_count);
        $finish;
    end
endmodule
