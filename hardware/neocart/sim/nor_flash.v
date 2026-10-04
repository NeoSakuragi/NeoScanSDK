// S29GL064N NOR Flash — behavioral model with REAL timing
// 64Mbit (4M x 16-bit), TSOP-48
// Access time: 90ns from address valid to data valid
// CE# to output: 90ns
// OE# to output: 35ns

`timescale 1ns / 1ps

module nor_flash #(
    parameter ACCESS_TIME = 90,   // tACC: address to data valid
    parameter CE_TO_OUT   = 90,   // tCE: CE# low to data valid
    parameter OE_TO_OUT   = 35,   // tOE: OE# low to data valid
    parameter ROM_FILE    = "rom.hex",
    parameter ADDR_BITS   = 19,
    parameter DATA_BITS   = 16
) (
    input  wire [ADDR_BITS-1:0] A,      // Address pins A-1 through A17
    inout  wire [DATA_BITS-1:0] DQ,     // Data pins DQ0-DQ15
    input  wire                 CE_n,   // Chip Enable (active low) — pin 26
    input  wire                 OE_n,   // Output Enable (active low) — pin 28
    input  wire                 WE_n,   // Write Enable (active low) — pin 11
    input  wire                 BYTE_n  // Byte mode select — pin 15 (tied high for x16)
);

    // Internal ROM storage
    reg [DATA_BITS-1:0] mem [0:(1<<ADDR_BITS)-1];

    initial begin
        $readmemh(ROM_FILE, mem);
        $display("NOR_FLASH: loaded %s (%0d words)", ROM_FILE, 1<<ADDR_BITS);
    end

    // Internal signals with timing
    reg [DATA_BITS-1:0] data_out;
    reg output_valid;

    // Address change detection
    reg [ADDR_BITS-1:0] addr_latched;

    // Data output with access time delay
    always @(A or CE_n or OE_n) begin
        if (!CE_n && !OE_n && WE_n) begin
            // Read cycle: data appears after ACCESS_TIME
            output_valid = 0;
            data_out = {DATA_BITS{1'bx}};  // undefined during access
            addr_latched = A;
            #ACCESS_TIME;
            // Only output if address hasn't changed and CE/OE still active
            if (A == addr_latched && !CE_n && !OE_n) begin
                data_out = mem[A];
                output_valid = 1;
            end
        end else begin
            output_valid = 0;
            data_out = {DATA_BITS{1'bz}};  // high-Z when deselected
        end
    end

    // Tristate output
    assign DQ = (output_valid && !CE_n && !OE_n && WE_n) ? data_out : {DATA_BITS{1'bz}};

endmodule
