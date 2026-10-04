// CHA bus interface — serves C ROM, S ROM, and M ROM reads
//
// C ROM: LSPC puts address on P0-P23, clocks data out on PCK1B/PCK2B
//   CR0-CR15 served on PCK1B falling edge, CR16-CR31 on PCK2B
//   SDRAM base: 0xA00000
//
// S ROM: Fix layer hardware reads via SDA0-15, data on SDD0-7
//   Active when SDMRD goes low
//   SDRAM base: 0x1A00000
//
// M ROM: Z80 reads via mrom_addr, data on mrom_data
//   Active when mrom_oe goes low
//   SDRAM base: 0x1A20000

module cha_bus (
    input  wire        clk,
    input  wire        rst_n,

    // C ROM bus
    input  wire [23:0] crom_addr,
    output reg  [31:0] crom_data,
    input  wire        pck1b,
    input  wire        pck2b,

    // S ROM bus
    input  wire [15:0] srom_addr,
    output wire  [7:0] srom_data,
    input  wire        srom_oe_n,

    // M ROM bus
    input  wire [16:0] mrom_addr,
    inout  wire  [7:0] mrom_data,
    input  wire        mrom_oe_n,

    // SDRAM port
    output reg         mem_req,
    output reg  [24:0] mem_addr,
    input  wire [15:0] mem_rdata,
    input  wire        mem_ready
);

    localparam CROM_BASE = 25'h050_0000;  // 0xA00000 byte = 0x500000 word
    localparam SROM_BASE = 25'h0D0_0000;  // 0x1A00000 byte
    localparam MROM_BASE = 25'h0D1_0000;  // 0x1A20000 byte

    // ─── S ROM (active when SDMRD low) ───
    reg [7:0] srom_latch;
    reg       srom_active;

    assign srom_data = srom_active ? srom_latch : 8'hZZ;

    // ─── M ROM ───
    reg [7:0] mrom_latch;
    reg       mrom_active;

    assign mrom_data = mrom_active ? mrom_latch : 8'hZZ;

    // ─── C ROM — latched on pixel clock edges ───
    // The LSPC reads C ROM data in two 16-bit halves:
    //   PCK1B falling: latch lower 16 bits (CR0-CR15)
    //   PCK2B falling: latch upper 16 bits (CR16-CR31)
    // We prefetch the full 32-bit word when address changes.

    reg [23:0] crom_addr_prev;
    reg [31:0] crom_prefetch;
    reg        crom_pending;

    // Sync async signals
    reg [1:0] srom_oe_sync;
    reg [1:0] mrom_oe_sync;
    reg [1:0] pck1_sync;

    always @(posedge clk) begin
        srom_oe_sync <= {srom_oe_sync[0], srom_oe_n};
        mrom_oe_sync <= {mrom_oe_sync[0], mrom_oe_n};
        pck1_sync    <= {pck1_sync[0], pck1b};
    end

    // Detect PCK1B falling edge (new C ROM access)
    wire pck1_fall = pck1_sync[1] & ~pck1_sync[0];

    // ─── State machine ───
    localparam S_IDLE     = 4'd0;
    localparam S_CROM_RD1 = 4'd1;  // read first 16 bits
    localparam S_CROM_RD2 = 4'd2;  // read second 16 bits
    localparam S_CROM_OK  = 4'd3;
    localparam S_SROM_RD  = 4'd4;
    localparam S_SROM_OK  = 4'd5;
    localparam S_MROM_RD  = 4'd6;
    localparam S_MROM_OK  = 4'd7;

    reg [3:0] state;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_IDLE;
            mem_req     <= 0;
            srom_active <= 0;
            mrom_active <= 0;
            crom_data   <= 32'hFFFFFFFF;
        end else begin
            case (state)
                S_IDLE: begin
                    mem_req     <= 0;
                    srom_active <= 0;
                    mrom_active <= 0;

                    if (pck1_fall) begin
                        // C ROM read: fetch 32 bits as two 16-bit reads
                        mem_addr <= CROM_BASE + {1'b0, crom_addr};
                        mem_req  <= 1;
                        state    <= S_CROM_RD1;
                    end else if (~srom_oe_sync[1]) begin
                        mem_addr <= SROM_BASE + {9'b0, srom_addr};
                        mem_req  <= 1;
                        state    <= S_SROM_RD;
                    end else if (~mrom_oe_sync[1]) begin
                        mem_addr <= MROM_BASE + {8'b0, mrom_addr};
                        mem_req  <= 1;
                        state    <= S_MROM_RD;
                    end
                end

                // C ROM: two sequential reads for 32 bits
                S_CROM_RD1: begin
                    if (mem_ready) begin
                        crom_data[15:0] <= mem_rdata;
                        mem_addr <= mem_addr + 1;
                        mem_req  <= 1;
                        state    <= S_CROM_RD2;
                    end
                end

                S_CROM_RD2: begin
                    if (mem_ready) begin
                        crom_data[31:16] <= mem_rdata;
                        mem_req <= 0;
                        state   <= S_IDLE;
                    end
                end

                // S ROM read
                S_SROM_RD: begin
                    if (mem_ready) begin
                        srom_latch  <= mem_rdata[7:0];
                        srom_active <= 1;
                        mem_req     <= 0;
                        state       <= S_SROM_OK;
                    end
                end

                S_SROM_OK: begin
                    if (srom_oe_sync[1]) begin
                        srom_active <= 0;
                        state       <= S_IDLE;
                    end
                end

                // M ROM read
                S_MROM_RD: begin
                    if (mem_ready) begin
                        mrom_latch  <= mem_rdata[7:0];
                        mrom_active <= 1;
                        mem_req     <= 0;
                        state       <= S_MROM_OK;
                    end
                end

                S_MROM_OK: begin
                    if (mrom_oe_sync[1]) begin
                        mrom_active <= 0;
                        state       <= S_IDLE;
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
