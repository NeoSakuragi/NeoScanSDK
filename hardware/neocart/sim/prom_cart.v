// NOR Flash P-ROM Cart Model
// Simulates the CPLD + NOR flash for PROG slot
//
// Neo Geo P-ROM memory map:
//   0x000000-0x0FFFFF : P1 fixed bank (1MB)
//   0x100000-0x1FFFFF : P1 upper (1MB, for 2MB+ P1 ROMs)
//   0x200000-0x2FFFFF : P2 switchable bank (1MB window)
//   0x2FFFF0          : bankswitch register (active on write)
//
// This models: address decode + bankswitch latch + NOR flash lookup

module prom_cart #(
    parameter P1_SIZE_BYTES = 2*1024*1024,  // P1 ROM size
    parameter P2_SIZE_BYTES = 4*1024*1024,  // P2 ROM size
    parameter P1_FILE = "p1.bin",
    parameter P2_FILE = "p2.bin"
) (
    input  wire        clk,
    input  wire        rst_n,

    // 68K bus interface
    input  wire [23:1] addr,       // byte address, active on word boundary
    input  wire [15:0] data_in,    // for bankswitch writes
    output wire [15:0] data_out,   // ROM data output
    input  wire        romoe_n,    // ROM output enable (active low)
    input  wire        rw_n,       // read/write (active low = write)
    input  wire        as_n,       // address strobe (active low)

    output wire        dtack_n     // data acknowledge (active low)
);

    // ─── NOR Flash arrays (word-addressed) ───
    localparam P1_WORDS = P1_SIZE_BYTES / 2;
    localparam P2_WORDS = P2_SIZE_BYTES / 2;

    reg [15:0] p1_rom [0:P1_WORDS-1];
    reg [15:0] p2_rom [0:P2_WORDS-1];

    initial begin
        $readmemh(P1_FILE, p1_rom);
        $readmemh(P2_FILE, p2_rom);
    end

    // ─── Bankswitch register ───
    reg [3:0] bank_reg;

    wire is_bankswitch_write = ~as_n & ~rw_n &
                               (addr[23:5] == 19'h17FFF);  // 0x2FFFF0-0x2FFFFF

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            bank_reg <= 4'd0;
        else if (is_bankswitch_write)
            bank_reg <= data_in[3:0];
    end

    // ─── Address decode ───
    wire [19:0] word_addr = {addr[23:1], 1'b0} >> 1;  // word address

    wire in_p1_range = (addr[23:20] == 4'h0);           // 0x000000-0x0FFFFF
    wire in_p1_upper = (addr[23:20] == 4'h1);           // 0x100000-0x1FFFFF
    wire in_p2_range = (addr[23:20] == 4'h2);           // 0x200000-0x2FFFFF

    wire rom_active = ~romoe_n & ~as_n & rw_n;          // valid read cycle

    // ─── Data output mux ───
    reg [15:0] rom_data;

    always @(*) begin
        rom_data = 16'hFFFF;
        if (in_p1_range)
            rom_data = p1_rom[addr[19:1]];
        else if (in_p1_upper && P1_SIZE_BYTES > 20'h100000)
            rom_data = p1_rom[{1'b1, addr[19:1]}];
        else if (in_p2_range)
            rom_data = p2_rom[{bank_reg, addr[19:1]}];
    end

    assign data_out = rom_active ? rom_data : 16'hFFFF;
    assign dtack_n  = rom_active ? 1'b0 : 1'b1;

endmodule
