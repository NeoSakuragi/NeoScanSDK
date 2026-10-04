// NeoCart PROG testbench — simulates MVS bus cycles hitting the cart
// Generates VCD waveform showing every signal with real timing

`timescale 1ns / 1ps

module cart_tb;

    // MVS bus signals
    reg  [18:0] ADDR;
    reg   [3:0] REGION;
    reg  [15:0] DATA_IN;
    reg         nAS, ROMOEU, ROMOEL, nRW;
    reg         CLK_68K;

    // Wires between CPLD and NOR Flash
    wire [18:0] FLASH_ADDR;
    wire        FLASH_CE_n, FLASH_OE_n;
    wire [15:0] FLASH_DQ;
    wire        DTACK_n, ROMWAIT;

    // CPLD
    cpld_logic cpld (
        .ADDR(ADDR), .REGION(REGION), .DATA_IN(DATA_IN),
        .nAS(nAS), .ROMOEU(ROMOEU), .ROMOEL(ROMOEL), .nRW(nRW),
        .CLK_68K(CLK_68K),
        .FLASH_ADDR(FLASH_ADDR), .FLASH_CE_n(FLASH_CE_n), .FLASH_OE_n(FLASH_OE_n),
        .DTACK_n(DTACK_n), .ROMWAIT(ROMWAIT)
    );

    // NOR Flash
    nor_flash #(
        .ACCESS_TIME(90),
        .ROM_FILE("test_rom.hex"),
        .ADDR_BITS(19),
        .DATA_BITS(16)
    ) flash (
        .A(FLASH_ADDR),
        .DQ(FLASH_DQ),
        .CE_n(FLASH_CE_n),
        .OE_n(FLASH_OE_n),
        .WE_n(1'b1),
        .BYTE_n(1'b1)
    );

    // 68K clock: 8MHz = 125ns period
    initial CLK_68K = 0;
    always #62.5 CLK_68K = ~CLK_68K;

    // Bus idle state
    task bus_idle;
        begin
            nAS = 1; ROMOEU = 1; ROMOEL = 1; nRW = 1;
            REGION = 4'h0; ADDR = 19'h0;
        end
    endtask

    // 68K read cycle: ~4 clock cycles (500ns)
    task read_word;
        input [3:0] region;
        input [18:0] addr;
        begin
            $display("--- READ 0x%01X%05X ---", region, addr);

            // S0: Address valid
            REGION = region;
            ADDR = addr;
            nRW = 1;  // read
            #30;

            // S1: Assert AS and OE
            nAS = 0;
            ROMOEU = 0;
            #30;

            // Wait for DTACK (or timeout after 500ns)
            fork
                begin
                    wait (DTACK_n == 0);
                    $display("  DTACK at %0t ns", $time);
                end
                begin
                    #500;
                    $display("  TIMEOUT waiting for DTACK at %0t ns", $time);
                end
            join_any
            disable fork;

            // S4-S5: Data valid, sample it
            #20;
            $display("  DATA = 0x%04X at %0t ns", FLASH_DQ, $time);

            // S6-S7: Release bus
            nAS = 1;
            ROMOEU = 1;
            #60;
        end
    endtask

    initial begin
        $dumpfile("cart_sim.vcd");
        $dumpvars(0, cart_tb);

        $display("=== NeoCart PROG Simulation ===");
        $display("CPLD propagation: 10ns");
        $display("NOR Flash access: 90ns");
        $display("68K clock: 8MHz (125ns)");
        $display("");

        bus_idle;
        #100;

        // P1 Read cycles — RB2 reset vectors
        read_word(4'h0, 19'h00000);  // 0x000000: expect 0x0010
        read_word(4'h0, 19'h00001);  // 0x000002: expect 0xF300
        read_word(4'h0, 19'h00002);  // 0x000004: expect 0x00C0
        read_word(4'h0, 19'h00003);  // 0x000006: expect 0x0402

        // Bus idle
        bus_idle;
        #200;

        // Write cycle (bus idle, no ROM response expected)
        $display("--- WRITE (bus idle) ---");
        ADDR = 19'h7FFF8;
        REGION = 4'h2;
        nRW = 0;
        DATA_IN = 16'h0001;
        nAS = 0;
        #125;
        nAS = 1;
        nRW = 1;
        #100;

        // P2 banked read
        read_word(4'h2, 19'h00000);  // Banked read

        bus_idle;
        #200;

        $display("");
        $display("=== Simulation complete ===");
        $finish;
    end

endmodule
