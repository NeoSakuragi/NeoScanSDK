// Multi-port SDRAM controller for W9825G6KH-6
// 4M x 4 banks x 16 bits = 32MB
// 100MHz clock, CAS latency 2
//
// 3 ports with fixed priority:
//   Port 0 (highest): PROG bus reads (68k + V ROM) — time critical
//   Port 1:           CHA bus reads (C/S/M ROM) — time critical
//   Port 2 (lowest):  SPI writes (ROM loading) — background task
//
// Auto-refresh handled internally (~64ms / 8192 rows = 7.8us per refresh)

module sdram_ctrl (
    input  wire        clk,         // 100MHz
    input  wire        rst_n,

    // SDRAM physical pins
    output reg         sd_cke,
    output reg         sd_cs_n,
    output reg         sd_ras_n,
    output reg         sd_cas_n,
    output reg         sd_we_n,
    output reg   [1:0] sd_ba,
    output reg  [12:0] sd_addr,
    inout  wire [15:0] sd_dq,
    output reg   [1:0] sd_dqm,

    // Port 0: PROG reads
    input  wire        p0_req,
    input  wire [24:0] p0_addr,
    output reg  [15:0] p0_rdata,
    output reg         p0_ready,

    // Port 1: CHA reads
    input  wire        p1_req,
    input  wire [24:0] p1_addr,
    output reg  [15:0] p1_rdata,
    output reg         p1_ready,

    // Port 2: SPI writes
    input  wire        p2_req,
    input  wire        p2_we,
    input  wire [24:0] p2_addr,
    input  wire [15:0] p2_wdata,
    output reg         p2_ready
);

    // SDRAM timing parameters at 100MHz (10ns period)
    localparam T_RP   = 2;   // precharge: 20ns
    localparam T_RCD  = 2;   // RAS-to-CAS: 20ns
    localparam T_RC   = 6;   // row cycle: 60ns
    localparam T_REF  = 750; // refresh interval: 7.5us

    // CAS latency
    localparam CAS_LAT = 2;

    // SDRAM commands {CS, RAS, CAS, WE}
    localparam CMD_NOP       = 4'b0111;
    localparam CMD_ACTIVE    = 4'b0011;
    localparam CMD_READ      = 4'b0101;
    localparam CMD_WRITE     = 4'b0100;
    localparam CMD_PRECHARGE = 4'b0010;
    localparam CMD_REFRESH   = 4'b0001;
    localparam CMD_LOADMODE  = 4'b0000;

    // Address decomposition: {bank[1:0], row[12:0], col[9:0]} = 25 bits
    wire  [1:0] active_bank;
    wire [12:0] active_row;
    wire  [9:0] active_col;

    reg [24:0] cur_addr;
    reg [15:0] cur_wdata;
    reg        cur_we;
    reg  [1:0] cur_port;   // which port is being served

    assign active_bank = cur_addr[24:23];
    assign active_row  = cur_addr[22:10];
    assign active_col  = cur_addr[9:0];

    // Data bus tristate
    reg [15:0] dq_out;
    reg        dq_oe;
    assign sd_dq = dq_oe ? dq_out : 16'hZZZZ;

    // Issue SDRAM command
    task issue_cmd(input [3:0] cmd);
        begin
            {sd_cs_n, sd_ras_n, sd_cas_n, sd_we_n} <= cmd;
        end
    endtask

    // ─── State machine ───
    localparam S_INIT      = 4'd0;
    localparam S_INIT_PRE  = 4'd1;
    localparam S_INIT_REF1 = 4'd2;
    localparam S_INIT_REF2 = 4'd3;
    localparam S_INIT_MODE = 4'd4;
    localparam S_IDLE      = 4'd5;
    localparam S_ACTIVATE  = 4'd6;
    localparam S_RD_CMD    = 4'd7;
    localparam S_RD_WAIT   = 4'd8;
    localparam S_RD_LATCH  = 4'd9;
    localparam S_WR_CMD    = 4'd10;
    localparam S_WR_DONE   = 4'd11;
    localparam S_PRECHARGE = 4'd12;
    localparam S_REFRESH   = 4'd13;

    reg  [3:0] state;
    reg  [3:0] wait_cnt;
    reg [15:0] init_cnt;
    reg  [9:0] refresh_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= S_INIT;
            init_cnt    <= 0;
            refresh_cnt <= 0;
            sd_cke      <= 1;
            sd_dqm      <= 2'b00;
            dq_oe       <= 0;
            p0_ready    <= 0;
            p1_ready    <= 0;
            p2_ready    <= 0;
            issue_cmd(CMD_NOP);
        end else begin
            // Default: deassert ready signals after one cycle
            p0_ready <= 0;
            p1_ready <= 0;
            p2_ready <= 0;

            // Refresh counter
            if (state != S_REFRESH && state != S_INIT)
                refresh_cnt <= refresh_cnt + 1;

            case (state)
                // ── Initialization sequence ──
                S_INIT: begin
                    issue_cmd(CMD_NOP);
                    init_cnt <= init_cnt + 1;
                    if (init_cnt == 20000) // 200us at 100MHz
                        state <= S_INIT_PRE;
                end

                S_INIT_PRE: begin
                    issue_cmd(CMD_PRECHARGE);
                    sd_addr[10] <= 1; // all banks
                    wait_cnt <= T_RP;
                    state <= S_INIT_REF1;
                end

                S_INIT_REF1: begin
                    if (wait_cnt) begin
                        wait_cnt <= wait_cnt - 1;
                        issue_cmd(CMD_NOP);
                    end else begin
                        issue_cmd(CMD_REFRESH);
                        wait_cnt <= T_RC;
                        state <= S_INIT_REF2;
                    end
                end

                S_INIT_REF2: begin
                    if (wait_cnt) begin
                        wait_cnt <= wait_cnt - 1;
                        issue_cmd(CMD_NOP);
                    end else begin
                        issue_cmd(CMD_REFRESH);
                        wait_cnt <= T_RC;
                        state <= S_INIT_MODE;
                    end
                end

                S_INIT_MODE: begin
                    if (wait_cnt) begin
                        wait_cnt <= wait_cnt - 1;
                        issue_cmd(CMD_NOP);
                    end else begin
                        issue_cmd(CMD_LOADMODE);
                        sd_ba   <= 2'b00;
                        sd_addr <= 13'b000_0_00_010_0_000;
                        // CAS=2, burst=1, sequential
                        wait_cnt <= 2;
                        state <= S_IDLE;
                    end
                end

                // ── Idle — arbitrate between ports ──
                S_IDLE: begin
                    issue_cmd(CMD_NOP);
                    dq_oe <= 0;

                    if (wait_cnt) begin
                        wait_cnt <= wait_cnt - 1;
                    end else if (refresh_cnt >= T_REF) begin
                        // Refresh needed
                        issue_cmd(CMD_REFRESH);
                        refresh_cnt <= 0;
                        wait_cnt <= T_RC;
                        state <= S_REFRESH;
                    end else if (p0_req) begin
                        cur_addr <= p0_addr;
                        cur_we   <= 0;
                        cur_port <= 0;
                        state    <= S_ACTIVATE;
                    end else if (p1_req) begin
                        cur_addr <= p1_addr;
                        cur_we   <= 0;
                        cur_port <= 1;
                        state    <= S_ACTIVATE;
                    end else if (p2_req) begin
                        cur_addr <= p2_addr;
                        cur_wdata <= p2_wdata;
                        cur_we   <= p2_we;
                        cur_port <= 2;
                        state    <= S_ACTIVATE;
                    end
                end

                S_REFRESH: begin
                    issue_cmd(CMD_NOP);
                    if (wait_cnt)
                        wait_cnt <= wait_cnt - 1;
                    else
                        state <= S_IDLE;
                end

                // ── Row activate ──
                S_ACTIVATE: begin
                    issue_cmd(CMD_ACTIVE);
                    sd_ba   <= active_bank;
                    sd_addr <= active_row;
                    wait_cnt <= T_RCD;
                    state <= cur_we ? S_WR_CMD : S_RD_CMD;
                end

                // ── Read ──
                S_RD_CMD: begin
                    if (wait_cnt) begin
                        wait_cnt <= wait_cnt - 1;
                        issue_cmd(CMD_NOP);
                    end else begin
                        issue_cmd(CMD_READ);
                        sd_addr <= {3'b001, active_col}; // auto-precharge
                        sd_ba   <= active_bank;
                        wait_cnt <= CAS_LAT;
                        state <= S_RD_WAIT;
                    end
                end

                S_RD_WAIT: begin
                    issue_cmd(CMD_NOP);
                    if (wait_cnt)
                        wait_cnt <= wait_cnt - 1;
                    else
                        state <= S_RD_LATCH;
                end

                S_RD_LATCH: begin
                    issue_cmd(CMD_NOP);
                    case (cur_port)
                        0: begin p0_rdata <= sd_dq; p0_ready <= 1; end
                        1: begin p1_rdata <= sd_dq; p1_ready <= 1; end
                    endcase
                    state <= S_IDLE;
                end

                // ── Write ──
                S_WR_CMD: begin
                    if (wait_cnt) begin
                        wait_cnt <= wait_cnt - 1;
                        issue_cmd(CMD_NOP);
                    end else begin
                        issue_cmd(CMD_WRITE);
                        sd_addr <= {3'b001, active_col}; // auto-precharge
                        sd_ba   <= active_bank;
                        dq_out  <= cur_wdata;
                        dq_oe   <= 1;
                        state   <= S_WR_DONE;
                    end
                end

                S_WR_DONE: begin
                    issue_cmd(CMD_NOP);
                    dq_oe    <= 0;
                    p2_ready <= 1;
                    state    <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
