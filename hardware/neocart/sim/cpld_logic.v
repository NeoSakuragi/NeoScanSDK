// EPM240 CPLD logic — address decode + bankswitch + DTACK
// Real gate delays: ~10ns propagation through CPLD macrocells
// This is what gets synthesized into the actual CPLD

`timescale 1ns / 1ps

module cpld_logic (
    // From MVS gold fingers (active-low accent)
    input  wire [18:0] ADDR,        // A1-A19 from CTRG2
    input  wire  [3:0] REGION,      // A20-A23 (upper address)
    input  wire [15:0] DATA_IN,     // D0-D15 for bankswitch writes
    input  wire        nAS,         // Address Strobe (active low)
    input  wire        ROMOEU,      // ROM Output Enable Upper (active low)
    input  wire        ROMOEL,      // ROM Output Enable Lower (active low)
    input  wire        nRW,         // Read/Write (low = write)
    input  wire        CLK_68K,     // 68K clock (8MHz)

    // To NOR Flash
    output wire [18:0] FLASH_ADDR,  // Address to NOR flash
    output wire        FLASH_CE_n,  // Chip Enable
    output wire        FLASH_OE_n,  // Output Enable

    // To MVS gold fingers
    output wire        DTACK_n,     // Data Transfer Acknowledge
    output wire        ROMWAIT      // ROM Wait (active low)
);

    // CPLD propagation delay
    localparam TPD = 10;  // 10ns through macrocell

    // ── Read cycle detection ──
    // Read = AS active AND ROM OE active AND RW=read
    wire is_read;
    assign #TPD is_read = ~nAS & ~ROMOEU & nRW;

    // ── Region decode ──
    wire is_p1 = (REGION == 4'h0);  // 0x000000-0x0FFFFF
    wire is_p2 = (REGION == 4'h2);  // 0x200000-0x2FFFFF

    // ── Bankswitch register ──
    // Latches D[2:0] when 68K writes to 0x2FFFF0
    wire is_bankswitch_write;
    assign #TPD is_bankswitch_write = ~nAS & ~nRW &
                                       (REGION == 4'h2) &
                                       (ADDR[18:3] == 16'hFFFE);

    reg [2:0] bank_reg;
    always @(posedge CLK_68K) begin
        if (is_bankswitch_write)
            bank_reg <= DATA_IN[2:0];
    end

    // ── Flash address mux ──
    // P1: direct address (first 1MB of flash)
    // P2: bank + address (subsequent 1MB blocks)
    reg [18:0] flash_addr_mux;
    always @(*) begin
        if (is_p2)
            flash_addr_mux = ADDR;  // bank selects which flash chip / upper address
        else
            flash_addr_mux = ADDR;  // P1 direct
    end
    assign #TPD FLASH_ADDR = flash_addr_mux;

    // ── Flash control ──
    assign #TPD FLASH_CE_n = ~(is_read & (is_p1 | is_p2));
    assign #TPD FLASH_OE_n = ~is_read;

    // ── DTACK generation ──
    // Assert DTACK (active low) when read is valid
    assign #TPD DTACK_n = ~is_read;

    // ── ROMWAIT ──
    assign ROMWAIT = 1'b1;  // No wait states

endmodule
