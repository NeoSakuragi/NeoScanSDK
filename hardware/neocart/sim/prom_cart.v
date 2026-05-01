// NOR Flash P-ROM Cart — CPLD + Flash simulation
// Synthesizable for EPM240. Simulatable with Verilator.
//
// Memory map (68K view):
//   0x000000-0x0FFFFF : P1 fixed (1MB)
//   0x200000-0x2FFFFF : P2 banked (1MB window into P2)
//   0x2FFFF0 write    : bankswitch register (D[2:0] = bank number)
//
// ROM is one contiguous array: P1 at [0..P1_WORDS-1], P2 follows.
// Bank N maps to ROM offset P1_WORDS + N * 0x80000.

module prom_cart #(
    parameter ROM_FILE  = "rbff2_prom.hex",
    parameter ROM_WORDS = 2621440  // 5MB / 2 = 2621440 words for RB2
) (
    input  wire        clk,
    input  wire        rst_n,

    // 68K bus
    input  wire [23:1] addr,
    input  wire [15:0] data_in,
    output reg  [15:0] data_out,
    input  wire        as_n,       // address strobe
    input  wire        romoe_n,    // ROM output enable
    input  wire        rw_n,       // 1=read, 0=write
    output wire        dtack_n
);

    // ROM storage
    reg [15:0] rom [0:ROM_WORDS-1];
    initial $readmemh(ROM_FILE, rom);

    // Bankswitch register
    reg [2:0] bank;

    wire is_read  = ~as_n & rw_n & ~romoe_n;
    wire is_write = ~as_n & ~rw_n;

    // Bankswitch decode: write to 0x2FFFF0-0x2FFFFF
    wire bankswitch_wr = is_write & (addr[23:4] == 20'h2FFFF);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            bank <= 3'd0;
        else if (bankswitch_wr)
            bank <= data_in[2:0];
    end

    // Address decode
    wire in_p1 = (addr[23:20] == 4'h0);  // 0x000000-0x0FFFFF
    wire in_p2 = (addr[23:20] == 4'h2);  // 0x200000-0x2FFFFF

    // ROM address calculation
    // P1: word index = addr[19:1]
    // P2: word index = P1_size/2 + bank*0x80000 + addr[19:1]
    //   P1 is 0x80000 words (1MB/2). Bank 0 = ROM[0x80000..0xFFFFF], etc.
    wire [31:0] p1_word_addr = {13'b0, addr[19:1]};
    wire [31:0] p2_word_addr = {13'b0, addr[19:1]} + {10'b0, bank + 3'd1, 19'd0};
    // bank+1 because bank 0 = second 1MB block (offset 0x80000 words)

    // Data output
    always @(*) begin
        data_out = 16'hFFFF;
        if (is_read) begin
            if (in_p1 && p1_word_addr < ROM_WORDS)
                data_out = rom[p1_word_addr];
            else if (in_p2 && p2_word_addr < ROM_WORDS)
                data_out = rom[p2_word_addr];
        end
    end

    assign dtack_n = is_read ? 1'b0 : 1'b1;

endmodule
