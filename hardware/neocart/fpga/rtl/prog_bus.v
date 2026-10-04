// PROG bus interface — serves P ROM and V ROM reads
//
// When the 68k reads from P ROM space:
//   1. ROMOE goes low
//   2. We see address on prog_addr
//   3. We fetch from SDRAM at offset 0x000000 + addr
//   4. Drive data onto prog_data
//
// When YM2610 reads V ROM:
//   1. SDROE goes low
//   2. We see address on vrom_addr
//   3. We fetch from SDRAM at offset 0x200000 + addr
//   4. Drive data onto vrom_data

module prog_bus (
    input  wire        clk,
    input  wire        rst_n,

    // 68k bus
    input  wire [19:1] addr,
    inout  wire [15:0] data,
    input  wire        romoe_n,
    input  wire        romoeu_n,
    input  wire        romoel_n,
    input  wire        rw,

    // V ROM bus
    input  wire [23:0] vrom_addr,
    inout  wire  [7:0] vrom_data,
    input  wire        vrom_oe_n,

    // SDRAM port
    output reg         mem_req,
    output reg  [24:0] mem_addr,
    input  wire [15:0] mem_rdata,
    input  wire        mem_ready
);

    // SDRAM base addresses
    localparam PROM_BASE = 25'h000_0000;
    localparam VROM_BASE = 25'h010_0000;  // 1MB offset (word addressed)

    // ─── P ROM read ───
    reg [15:0] prom_latch;
    reg        prom_oe;

    // Active when ROMOE is asserted and 68k is reading
    wire prom_active = ~romoe_n & rw;

    // Data bus drive: only when we're outputting P ROM data
    assign data = prom_oe ? prom_latch : 16'hZZZZ;

    // ─── V ROM read ───
    reg [7:0] vrom_latch;
    reg       vrom_out_en;

    wire vrom_active = ~vrom_oe_n;

    assign vrom_data = vrom_out_en ? vrom_latch : 8'hZZ;

    // ─── State machine ───
    localparam S_IDLE    = 3'd0;
    localparam S_PROM_RD = 3'd1;
    localparam S_PROM_OK = 3'd2;
    localparam S_VROM_RD = 3'd3;
    localparam S_VROM_OK = 3'd4;

    reg [2:0] state;

    // Synchronize async bus signals to clk domain
    reg [1:0] romoe_sync;
    reg [1:0] vromoe_sync;
    always @(posedge clk) begin
        romoe_sync  <= {romoe_sync[0], romoe_n};
        vromoe_sync <= {vromoe_sync[0], vrom_oe_n};
    end

    wire prom_req = ~romoe_sync[1] & rw;
    wire vrom_req = ~vromoe_sync[1];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state      <= S_IDLE;
            mem_req    <= 0;
            prom_oe    <= 0;
            vrom_out_en <= 0;
        end else begin
            case (state)
                S_IDLE: begin
                    prom_oe     <= 0;
                    vrom_out_en <= 0;
                    mem_req     <= 0;

                    if (prom_req) begin
                        mem_addr <= PROM_BASE + {6'b0, addr[19:1]};
                        mem_req  <= 1;
                        state    <= S_PROM_RD;
                    end else if (vrom_req) begin
                        mem_addr <= VROM_BASE + {1'b0, vrom_addr};
                        mem_req  <= 1;
                        state    <= S_VROM_RD;
                    end
                end

                S_PROM_RD: begin
                    if (mem_ready) begin
                        prom_latch <= mem_rdata;
                        prom_oe    <= 1;
                        mem_req    <= 0;
                        state      <= S_PROM_OK;
                    end
                end

                S_PROM_OK: begin
                    if (romoe_sync[1]) begin
                        // ROMOE deasserted, release bus
                        prom_oe <= 0;
                        state   <= S_IDLE;
                    end
                end

                S_VROM_RD: begin
                    if (mem_ready) begin
                        vrom_latch  <= mem_rdata[7:0];
                        vrom_out_en <= 1;
                        mem_req     <= 0;
                        state       <= S_VROM_OK;
                    end
                end

                S_VROM_OK: begin
                    if (vromoe_sync[1]) begin
                        vrom_out_en <= 0;
                        state       <= S_IDLE;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
